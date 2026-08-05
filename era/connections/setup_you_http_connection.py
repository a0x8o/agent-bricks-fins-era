"""
Provision the Unity Catalog HTTP connections ERA uses to reach You.com.

Run this once per workspace before creating the UC functions in
``you_uc_functions.sql``.

WHY TWO CONNECTIONS
-------------------
You.com does not serve its REST API from a single host. Verified against the live
API reference on 2026-08-03:

    GET  https://ydc-index.io/v1/search
    POST https://ydc-index.io/v1/contents
    POST https://api.you.com/v1/research
    GET  https://api.you.com/v1/research/{task_id}
    POST https://api.you.com/v1/finance_research

A Unity Catalog HTTP connection pins exactly one host, so the split is structural:
``you_search_http`` covers the fast endpoints, ``you_research_http`` the slow ones.
Anything that assumes one YOU_HTTP_BASE will silently 404 against half the surface.

WHY THE KEY IS A SECRET REFERENCE, NOT A VALUE
----------------------------------------------
The DDL passes ``secret('<scope>','<key>')`` rather than the key itself. Unity
Catalog resolves the reference server-side, so the credential never appears in this
file, in your shell history, in the statement text sent over the wire, or in the
audit record of the statement. Nothing here is safe to commit *because* nothing
here contains a key.

Create the scope and key first::

    databricks secrets create-scope era_you
    databricks secrets put-secret era_you api_key   # paste the You.com key

AUTH HEADER CAVEAT
------------------
You.com's REST API documents ``X-API-Key`` as its auth header, but a Unity Catalog
connection only knows how to inject ``Authorization: Bearer``. ERA therefore does
both: the connection carries ``bearer_token`` (so UC has a credential attached and
the connection is governable), and each UC function additionally passes an explicit
``X-API-Key`` header sourced from the same secret. You.com reads the header it
recognises and ignores the other. See ``you_uc_functions.sql``.

Usage::

    python era/connections/setup_you_http_connection.py --warehouse-id <id>
    python era/connections/setup_you_http_connection.py --warehouse-id <id> --dry-run
    python era/connections/setup_you_http_connection.py --warehouse-id <id> --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass

from databricks.sdk import WorkspaceClient

logger = logging.getLogger("era.connections")

DEFAULT_SECRET_SCOPE = "era_you"
DEFAULT_SECRET_KEY = "api_key"


@dataclass(frozen=True)
class HttpConnection:
    name: str
    host: str
    port: str
    purpose: str


CONNECTIONS: tuple[HttpConnection, ...] = (
    HttpConnection(
        name="you_search_http",
        host="https://ydc-index.io",
        port="443",
        purpose="Fast tier: /v1/search (web + news) and /v1/contents.",
    ),
    HttpConnection(
        name="you_research_http",
        host="https://api.you.com",
        port="443",
        purpose="Slow tier: /v1/research, /v1/research/{task_id}, /v1/finance_research.",
    ),
)


def build_ddl(conn: HttpConnection, scope: str, key: str) -> str:
    """
    Render CREATE CONNECTION DDL.

    IF NOT EXISTS keeps this idempotent: re-running is a no-op rather than an error,
    which matters because this script is meant to be safe to run from a setup
    notebook that may be executed more than once.
    """
    return (
        f"CREATE CONNECTION IF NOT EXISTS {conn.name} TYPE HTTP\n"
        f"OPTIONS (\n"
        f"  host '{conn.host}',\n"
        f"  port '{conn.port}',\n"
        f"  base_path '/',\n"
        f"  bearer_token secret('{scope}','{key}')\n"
        f")"
    )


def _execute(w: WorkspaceClient, warehouse_id: str, statement: str, timeout_s: int = 120):
    """Run one SQL statement and return its result, raising on failure."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="30s",
    )
    deadline = time.time() + timeout_s
    while resp.status and resp.status.state and resp.status.state.value in ("PENDING", "RUNNING"):
        if time.time() > deadline:
            raise TimeoutError(f"statement did not settle within {timeout_s}s")
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)

    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        detail = ""
        if resp.status and resp.status.error:
            detail = f": {resp.status.error.message}"
        raise RuntimeError(f"statement {state}{detail}")
    return resp


def check_balance(w: WorkspaceClient, warehouse_id: str, scope: str, key: str) -> float | None:
    """
    Read the account's prepaid credit balance, in USD. None if it cannot be read.

    WHY this runs before the search probe: an exhausted balance returns HTTP 402,
    which is easy to misread as a broken key or a broken connection. It is neither -
    auth succeeded, the connection worked, there is simply no credit. Checking the
    balance first turns a confusing failure into a one-line diagnosis.

    Note this is on api.you.com, not ydc-index.io, so it goes through the research
    connection rather than the search one.
    """
    stmt = f"""
    SELECT http_request(
      conn    => 'you_research_http',
      method  => 'GET',
      path    => '/v1/billing/account_balance',
      headers => map('X-API-Key', secret('{scope}','{key}'))
    ) AS response
    """
    try:
        resp = _execute(w, warehouse_id, stmt)
        raw = resp.result.data_array[0][0]
        parsed = json.loads(raw)
        if int(parsed.get("status_code", 0)) != 200:
            return None
        body = json.loads(parsed.get("text") or "{}")
        cents = ((body.get("data") or {}).get("attributes") or {}).get("balance")
        return None if cents is None else float(cents) / 100.0
    except Exception as exc:  # noqa: BLE001 - diagnostic only, never fatal
        logger.debug("balance check unavailable: %s", exc)
        return None


def verify(w: WorkspaceClient, warehouse_id: str, scope: str, key: str) -> bool:
    """
    Prove the connection actually reaches You.com and the key is accepted.

    WHY this is a separate step: CREATE CONNECTION succeeds without ever contacting
    the remote host, so a "successful" setup tells you nothing about whether the
    credential works. This issues a real, cheap search and checks the HTTP status.
    """
    balance = check_balance(w, warehouse_id, scope, key)
    if balance is not None:
        logger.info("You.com prepaid balance: $%.2f", balance)
        if balance <= 0:
            logger.error(
                "The credential is VALID but the account has no prepaid credit "
                "($%.2f). Every paid endpoint will return HTTP 402 until credits "
                "are added at you.com/platform. This is a billing state, not a "
                "configuration problem - do not go looking for a bad key.",
                balance,
            )
            return False

    stmt = f"""
    SELECT http_request(
      conn    => 'you_search_http',
      method  => 'GET',
      path    => '/v1/search',
      headers => map('X-API-Key', secret('{scope}','{key}')),
      params  => map('query', 'databricks', 'count', '1')
    ) AS response
    """
    try:
        resp = _execute(w, warehouse_id, stmt)
    except Exception as exc:
        logger.error("verification call failed: %s", exc)
        return False

    rows = resp.result.data_array if resp.result else None
    if not rows:
        logger.error("verification returned no rows")
        return False

    raw = rows[0][0]
    # http_request returns STRUCT<status_code INT, text STRING>; the Statement
    # Execution API hands it back as a JSON-encoded string.
    try:
        parsed = json.loads(raw)
        status = int(parsed.get("status_code", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.error("could not parse http_request result: %r", raw[:200])
        return False

    if status == 200:
        logger.info("verification OK - You.com returned 200")
        return True
    if status in (401, 403):
        logger.error(
            "You.com rejected the credential (HTTP %s). Check that the secret "
            "%s/%s holds a valid key and that your plan covers /v1/search.",
            status, scope, key,
        )
        return False
    if status == 402:
        # Distinct from 401/403 and worth its own message: the key is fine, the
        # connection is fine, the account is simply out of credit. Reported as
        # "unexpected" this reads as a setup fault and sends people to debug the
        # wrong layer.
        logger.error(
            "HTTP 402 payment_required - the credential is VALID and the "
            "connection works, but the prepaid balance is depleted. Add credits at "
            "you.com/platform. Nothing in this repo needs changing.",
        )
        return False
    logger.error("unexpected HTTP %s from You.com: %s", status, str(parsed)[:300])
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--warehouse-id", help="SQL warehouse used to run the DDL. Required unless --dry-run.")
    p.add_argument("--secret-scope", default=DEFAULT_SECRET_SCOPE)
    p.add_argument("--secret-key", default=DEFAULT_SECRET_KEY)
    p.add_argument("--dry-run", action="store_true", help="Print the DDL and exit without touching the workspace.")
    p.add_argument("--verify", action="store_true", help="After creating, issue a live You.com call to prove the key works.")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.dry_run:
        for conn in CONNECTIONS:
            print(f"-- {conn.name}: {conn.purpose}")
            print(build_ddl(conn, args.secret_scope, args.secret_key) + ";\n")
        return 0

    if not args.warehouse_id:
        p.error("--warehouse-id is required unless --dry-run is set")

    w = WorkspaceClient()

    for conn in CONNECTIONS:
        logger.info("creating connection %s -> %s", conn.name, conn.host)
        _execute(w, args.warehouse_id, build_ddl(conn, args.secret_scope, args.secret_key))
        logger.info("  ok")

    if args.verify:
        if not verify(w, args.warehouse_id, args.secret_scope, args.secret_key):
            logger.error("connections were created but verification FAILED - do not "
                         "proceed to you_uc_functions.sql until this passes")
            return 1

    logger.info("done. next: run era/connections/you_uc_functions.sql")
    return 0


if __name__ == "__main__":
    sys.exit(main())
