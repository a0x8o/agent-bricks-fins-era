"""
Re-bind the chatbot Databricks App resources so the app service principal
can run every query path: MAS + sub-agents, UC functions, Genie, warehouse,
and the You.com connection when present.

WHY THIS IS A SCRIPT, NOT ONLY BUNDLE YAML
------------------------------------------
Agent Bricks allocates KA/MAS endpoint names at create time. chatbot-app/
databricks.yml can only declare the supervisor (plus user_api_scopes). A later
`databricks bundle deploy` of the app drops the sub-agent resources notebook
06 PATCHed on. This script puts them back using the Apps API.

Workshop default remains the Agent Bricks MAS (Layer A).

Usage::

    python resources/grant_app_mas_permissions.py
    python resources/grant_app_mas_permissions.py --app-name agent-bricks-chatbot-workshop
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

USER_API_SCOPES = [
    "serving.serving-endpoints",
    "sql",
    "dashboards.genie",
]


def load_config() -> dict:
    ns: dict = {}
    exec((REPO_ROOT / "config.py").read_text(encoding="utf-8"), ns)
    return ns


def app_full_name(cfg: dict) -> str:
    return f"{cfg['app_name']}-{cfg['app_resource_suffix']}"[:30].rstrip("-")


def find_mas(w, sa_name: str) -> dict:
    from urllib.parse import quote

    filt = quote(f'name=\'{sa_name}\' AND tile_type=\'MAS\'')
    tiles = w.api_client.do("GET", f"/api/2.0/tiles?filter={filt}")
    for tile in tiles.get("tiles") or []:
        if tile.get("title") == sa_name or tile.get("name") == sa_name:
            return tile
    raise SystemExit(f"MAS tile {sa_name!r} not found")


def mas_endpoint_name(mas: dict) -> str:
    status = mas.get("status") or {}
    tile = mas.get("tile") or mas
    for candidate in (
        mas.get("endpoint_name"),
        mas.get("serving_endpoint_name"),
        status.get("endpoint_name"),
        tile.get("endpoint_name"),
    ):
        if candidate:
            return candidate
    tile_id = mas.get("id") or tile.get("id") or ""
    if tile_id:
        return f"mas-{tile_id[:8]}-endpoint"
    raise SystemExit("MAS has no serving endpoint name")


def collect_from_mas(mas: dict) -> tuple[list[str], list[str], list[dict]]:
    endpoints: list[str] = []
    functions: list[str] = []
    genies: list[dict] = []
    for agent in mas.get("agents") or []:
        serving = agent.get("serving_endpoint") or {}
        if serving.get("name"):
            endpoints.append(serving["name"])
        uc = agent.get("unity_catalog_function") or {}
        path = uc.get("uc_path") or {}
        if path.get("catalog") and path.get("schema") and path.get("name"):
            functions.append(
                f"{path['catalog']}.{path['schema']}.{path['name']}"
            )
        genie = agent.get("genie_space") or {}
        if genie.get("id"):
            genies.append({
                "id": genie["id"],
                "name": genie.get("name") or agent.get("name") or "genie",
            })
    return endpoints, functions, genies


def _is_managed_name(name: str | None) -> bool:
    n = str(name or "")
    return (
        n in {
            "serving-endpoint",
            "sql-warehouse",
            "genie-space",
            "you-mcp",
        }
        or n.startswith("sub-agent-")
        or n.startswith("uc-fn-")
        or n.startswith("genie-space-")
    )


def merge_app_resources(
    existing: list[dict],
    mas_endpoint: str,
    sub_agent_endpoints: list[str],
    *,
    uc_functions: list[str] | None = None,
    genie_spaces: list[dict] | None = None,
    warehouse_id: str | None = None,
    connection_name: str | None = None,
) -> list[dict]:
    """Replace query-path bindings; keep Lakebase and any unknown extras."""
    kept = [
        r for r in existing
        if "serving_endpoint" not in r
        and "function" not in r
        and "genie_space" not in r
        and "sql_warehouse" not in r
        and "connection" not in r
        and not _is_managed_name(r.get("name"))
    ]
    existing_warehouse = next((r for r in existing if "sql_warehouse" in r), None)
    existing_connection = next((r for r in existing if "connection" in r), None)
    resources: list[dict] = [
        {
            "name": "serving-endpoint",
            "description": "Multi-Agent Supervisor serving endpoint",
            "serving_endpoint": {
                "name": mas_endpoint,
                "permission": "CAN_QUERY",
            },
        }
    ]
    for i, ep_name in enumerate(sub_agent_endpoints):
        resources.append({
            "name": f"sub-agent-{i + 1}",
            "description": f"Sub-agent endpoint: {ep_name}",
            "serving_endpoint": {"name": ep_name, "permission": "CAN_QUERY"},
        })
    for i, fn in enumerate(uc_functions or ()):
        resources.append({
            "name": f"uc-fn-{i + 1}",
            "description": f"UC function {fn}",
            "function": {"name": fn, "permission": "CAN_EXECUTE"},
        })
    for i, space in enumerate(genie_spaces or ()):
        body = {"space_id": space["id"], "permission": "CAN_RUN"}
        if space.get("name"):
            body["name"] = space["name"]
        resources.append({
            "name": "genie-space" if i == 0 else f"genie-space-{i + 1}",
            "description": "Genie space for ticker_data",
            "genie_space": body,
        })
    if warehouse_id:
        resources.append({
            "name": "sql-warehouse",
            "description": "SQL warehouse for graph/ticker queries",
            "sql_warehouse": {"id": warehouse_id, "permission": "CAN_USE"},
        })
    elif existing_warehouse:
        resources.append(existing_warehouse)
    if connection_name:
        resources.append({
            "name": "you-mcp",
            "description": "You.com MCP connection",
            "connection": {
                "name": connection_name,
                "permission": "CAN_USE",
            },
        })
    elif existing_connection:
        resources.append(existing_connection)
    resources.extend(kept)
    return resources


def _connection_exists(w, name: str) -> bool:
    try:
        w.api_client.do(
            "GET",
            f"/api/2.1/unity-catalog/connections/{name}",
        )
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-name", default=app_full_name(cfg))
    parser.add_argument("--sa-name", default=cfg["sa_name"])
    parser.add_argument(
        "--warehouse-id",
        default=(cfg.get("sql_warehouse_id") or "").strip() or None,
    )
    parser.add_argument("--you-connection", default="you-mcp")
    args = parser.parse_args(argv)

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    app = w.api_client.do("GET", f"/api/2.0/apps/{args.app_name}")
    mas = find_mas(w, args.sa_name)
    mas_ep = mas_endpoint_name(mas)
    sub_eps, functions, genies = collect_from_mas(mas)
    you_conn = (
        args.you_connection
        if args.you_connection and _connection_exists(w, args.you_connection)
        else None
    )
    payload = {
        "name": args.app_name,
        "resources": merge_app_resources(
            app.get("resources") or [],
            mas_ep,
            sub_eps,
            uc_functions=functions,
            genie_spaces=genies,
            warehouse_id=args.warehouse_id,
            connection_name=you_conn,
        ),
        "user_api_scopes": USER_API_SCOPES,
    }
    try:
        w.api_client.do("PATCH", f"/api/2.0/apps/{args.app_name}", body=payload)
    except Exception as exc:
        # Workspaces without user-authorization preview reject the scopes field.
        if "user_api_scopes" in str(exc) or "user authorization" in str(exc).lower():
            payload.pop("user_api_scopes", None)
            w.api_client.do(
                "PATCH", f"/api/2.0/apps/{args.app_name}", body=payload
            )
            print(
                "Patched resources; user_api_scopes skipped "
                "(enable user authorization in the workspace to consent SQL/Genie/serving)."
            )
        else:
            raise
    else:
        print(
            f"Patched {args.app_name}: MAS {mas_ep}, "
            f"{len(sub_eps)} sub-agent(s), {len(functions)} function(s), "
            f"{len(genies)} Genie space(s)"
            + (f", warehouse {args.warehouse_id}" if args.warehouse_id else "")
            + (f", connection {you_conn}" if you_conn else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
