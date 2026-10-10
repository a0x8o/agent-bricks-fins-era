"""
Grant the ERA serving endpoint principals everything the live tools need.

WHY THIS EXISTS
---------------
``agents.deploy`` auto-grants only the MLflow resources declared at log time.
Secrets, Genie's ``ticker_data`` table, warehouse ACLs, and KA/Genie object
ACLs are easy to omit. The chatbot then gets a fully [OPS] answer even though
the bricks themselves are healthy.

Serving principals are discovered from Unity Catalog EXECUTE grants on
``era_you_search`` (one SP per deployed model version). The KA endpoint, Genie
space and warehouse are read from the deployed endpoint's environment (what ERA
actually calls), falling back to ``config.py``; flags override both.

Usage::

    python resources/grant_era_serving_permissions.py
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_config() -> dict:
    ns: dict = {}
    exec((REPO_ROOT / "config.py").read_text(encoding="utf-8"), ns)
    return ns


def app_full_name(cfg: dict) -> str:
    return f"{cfg['app_name']}-{cfg['app_resource_suffix']}"[:30].rstrip("-")


def _wait_sql(w, resp, timeout_s: int = 120):
    deadline = time.time() + timeout_s
    while resp.status and resp.status.state and resp.status.state.value in (
        "PENDING",
        "RUNNING",
    ):
        if time.time() > deadline:
            raise TimeoutError("SQL statement timed out")
        time.sleep(1)
        resp = w.statement_execution.get_statement(resp.statement_id)
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        detail = ""
        if resp.status and resp.status.error:
            detail = resp.status.error.message or ""
        raise RuntimeError(f"SQL {state}: {detail}")
    return resp


def _sql(w, warehouse_id: str, statement: str, timeout_s: int = 120):
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="30s",
    )
    return _wait_sql(w, resp, timeout_s=timeout_s)


def _rows(resp) -> list[list]:
    if not resp.result or not resp.result.data_array:
        return []
    return list(resp.result.data_array)


def discover_serving_sps(w, warehouse_id: str, catalog: str, schema: str) -> list[str]:
    resp = _sql(
        w,
        warehouse_id,
        f"""
        SELECT DISTINCT grantee
        FROM system.information_schema.routine_privileges
        WHERE routine_catalog = '{catalog}'
          AND routine_schema = '{schema}'
          AND routine_name = 'era_you_search'
          AND privilege_type = 'EXECUTE'
        """,
    )
    return sorted({r[0] for r in _rows(resp) if r and r[0]})


def _patch_acl(w, path: str, service_principal: str, permission: str) -> None:
    w.api_client.do(
        "PATCH",
        path,
        body={
            "access_control_list": [
                {
                    "service_principal_name": service_principal,
                    "permission_level": permission,
                }
            ]
        },
    )


def era_endpoint_env(w, name: str) -> dict:
    """Environment of the deployed ERA endpoint - the resources it really calls."""
    try:
        ep = w.serving_endpoints.get(name)
    except Exception as exc:  # noqa: BLE001
        print(f"could not read endpoint {name}: {exc}")
        return {}
    for entity in (ep.config.served_entities if ep.config else None) or []:
        if entity.environment_vars:
            return dict(entity.environment_vars)
    return {}


def _endpoint_id(w, name: str) -> str:
    ep = w.serving_endpoints.get(name)
    return ep.id


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="era-supervisor")
    parser.add_argument("--warehouse-id", default="")
    parser.add_argument("--ka-endpoint", default="")
    parser.add_argument("--genie-space-id", default="")
    parser.add_argument("--secret-scope", default="era_you")
    parser.add_argument(
        "--app-sp",
        default="",
        help="Also grant the chatbot app SP (auto-discovered if omitted).",
    )
    args = parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    catalog, schema = cfg["catalog"], cfg["schema"]
    env = era_endpoint_env(w, args.endpoint)
    warehouse_id = (
        args.warehouse_id
        or env.get("ERA_WAREHOUSE_ID")
        or (cfg.get("sql_warehouse_id") or "").strip()
    )
    ka_endpoint = args.ka_endpoint or env.get("ERA_KA_ENDPOINT", "")
    genie_space_id = (
        args.genie_space_id
        or env.get("ERA_GENIE_SPACE_ID")
        or (cfg.get("genie_space_id") or "").strip()
    )
    if not warehouse_id:
        raise SystemExit(
            "no warehouse: pass --warehouse-id or set sql_warehouse_id in config.py"
        )
    print(f"warehouse={warehouse_id} ka={ka_endpoint or '-'} genie={genie_space_id or '-'}")

    serving = discover_serving_sps(w, warehouse_id, catalog, schema)
    app_sp = args.app_sp.strip()
    if not app_sp:
        try:
            app = w.api_client.do(
                "GET", f"/api/2.0/apps/{app_full_name(cfg)}"
            )
            app_sp = app.get("service_principal_client_id") or ""
        except Exception as exc:  # noqa: BLE001
            print(f"could not read app SP: {exc}")
    principals = list(dict.fromkeys([*serving, *([app_sp] if app_sp else [])]))
    if not principals:
        raise SystemExit("no serving principals discovered")
    print(f"principals: {principals}")

    grants = [
        f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{{p}}`",
        f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{{p}}`",
        f"GRANT SELECT ON TABLE `{catalog}`.`{schema}`.ticker_data TO `{{p}}`",
        f"GRANT SELECT, MODIFY ON TABLE `{catalog}`.`{schema}`.egress_audit TO `{{p}}`",
        f"GRANT EXECUTE ON FUNCTION `{catalog}`.`{schema}`.era_you_search TO `{{p}}`",
        f"GRANT EXECUTE ON FUNCTION `{catalog}`.`{schema}`.era_you_contents TO `{{p}}`",
        f"GRANT EXECUTE ON FUNCTION `{catalog}`.`{schema}`.you_web_search TO `{{p}}`",
        f"GRANT EXECUTE ON FUNCTION `{catalog}`.`{schema}`.you_content_extract TO `{{p}}`",
        "GRANT USE CONNECTION ON CONNECTION you_search_http TO `{p}`",
        "GRANT USE CONNECTION ON CONNECTION you_research_http TO `{p}`",
    ]
    for p in principals:
        for tmpl in grants:
            stmt = tmpl.format(p=p)
            try:
                _sql(w, warehouse_id, stmt)
                print(f"ok  {stmt}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip {stmt}: {exc}")

    ka_id = _endpoint_id(w, ka_endpoint) if ka_endpoint else None
    if not ka_id:
        print("skip KA grants: no KA endpoint (pass --ka-endpoint)")
    if not genie_space_id:
        print("skip Genie grants: no Genie space (pass --genie-space-id)")
    for p in principals:
        try:
            from databricks.sdk.service.workspace import AclPermission

            w.secrets.put_acl(
                scope=args.secret_scope,
                principal=p,
                permission=AclPermission.READ,
            )
            print(f"ok  secret ACL READ {args.secret_scope} -> {p}")
        except Exception as exc:  # noqa: BLE001
            print(f"skip secret ACL {p}: {exc}")
        try:
            _patch_acl(
                w,
                f"/api/2.0/permissions/sql/warehouses/{warehouse_id}",
                p,
                "CAN_USE",
            )
            print(f"ok  warehouse CAN_USE -> {p}")
        except Exception as exc:  # noqa: BLE001
            print(f"skip warehouse {p}: {exc}")
        if ka_id:
            try:
                _patch_acl(
                    w,
                    f"/api/2.0/permissions/serving-endpoints/{ka_id}",
                    p,
                    "CAN_QUERY",
                )
                print(f"ok  KA CAN_QUERY -> {p}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip KA {p}: {exc}")
        if genie_space_id:
            try:
                _patch_acl(
                    w,
                    f"/api/2.0/permissions/genie/{genie_space_id}",
                    p,
                    "CAN_RUN",
                )
                print(f"ok  Genie CAN_RUN -> {p}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip Genie {p}: {exc}")

    # era_you_search itself comes from era/connections/render_uc_functions.py, the
    # one place its domain policy is defined. Do not redefine it here.
    for p in principals:
        _sql(
            w,
            warehouse_id,
            f"GRANT EXECUTE ON FUNCTION `{catalog}`.`{schema}`.era_you_search TO `{p}`",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
