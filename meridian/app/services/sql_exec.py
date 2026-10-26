"""Statement Execution API wrapper — named parameters only, TTL-cached.

Queries live in app/queries/*.sql with :named parameters. Table FQNs are
interpolated from config (catalog/schema) — the only non-parameter substitution,
and it comes from server-side config, never user input.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..auth import Identity, user_workspace_client
from ..config import get_settings
from ..models.schemas import Column, ResultSet
from . import cache

_QUERIES = Path(__file__).resolve().parent.parent / "queries"
_query_cache: dict[str, str] = {}

_PARAM_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def load_query(name: str, table_prefix: str) -> str:
    if name not in _query_cache:
        text = (_QUERIES / f"{name}.sql").read_text()
        # {t} is the trusted table prefix injected from server config
        _query_cache[name] = text.replace("{t}", table_prefix)
    return _query_cache[name]


def run_query(
    query_name: str,
    params: dict[str, Any],
    identity: Identity,
    ttl: int | None = None,
) -> tuple[ResultSet, bool]:
    """Execute a named query. Returns (result, cache_hit)."""
    settings = get_settings()
    ttl = settings.cache_ttl_seconds if ttl is None else ttl
    ck = (identity.user, query_name, _stable(params))
    hit, val = cache.get(ck, ttl)
    if hit:
        return val, True

    sql = load_query(query_name, settings.fq_prefix)
    from databricks.sdk.service.sql import StatementParameterListItem

    named = set(_PARAM_RE.findall(sql))
    missing = named - set(params)
    if missing:
        raise ValueError(f"missing params for {query_name}: {sorted(missing)}")
    extra = set(params) - named
    if extra:
        raise ValueError(f"unused params for {query_name}: {sorted(extra)}")

    w = user_workspace_client(identity)
    resp = w.statement_execution.execute_statement(
        warehouse_id=settings.warehouse_id,
        statement=sql,
        catalog=settings.uc_catalog,
        schema=settings.uc_schema,
        parameters=[
            StatementParameterListItem(name=k, value=str(v)) for k, v in params.items()
        ],
        wait_timeout="50s",
    )
    cols = []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        cols = [
            Column(name=c.name, type=_typename(c))
            for c in resp.manifest.schema.columns
        ]
    rows: list[list[Any]] = []
    truncated = False
    row_count = 0
    if resp.result:
        rows = [list(r) for r in (resp.result.data_array or [])]
        truncated = bool(resp.result.next_chunk_index or resp.result.external_links)
        row_count = resp.result.row_count if resp.result.row_count is not None else len(rows)
    out = ResultSet(columns=cols, rows=rows, row_count=row_count, truncated=truncated)
    cache.put(ck, out)
    return out, False


def _stable(params: dict[str, Any]) -> str:
    raw = "|".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_SELECT_GUARD = re.compile(r"^\s*(select|with)\b", re.IGNORECASE | re.DOTALL)


def _typename(c) -> str:
    t = getattr(c, "type_name", None)
    return str(getattr(t, "value", t) or "STRING")


def run_readonly_sql(sql: str, identity: Identity) -> ResultSet:
    """Pinned-insight refresh: user-supplied (stored) SQL, SELECT/WITH only."""
    stripped = sql.strip().rstrip(";")
    if not _SELECT_GUARD.match(stripped) or ";" in stripped:
        raise ValueError("only a single SELECT/WITH statement may be refreshed")
    settings = get_settings()
    w = user_workspace_client(identity)
    resp = w.statement_execution.execute_statement(
        warehouse_id=settings.warehouse_id,
        statement=stripped,
        wait_timeout="50s",
    )
    cols = []
    if resp.manifest and resp.manifest.schema and resp.manifest.schema.columns:
        cols = [
            Column(name=c.name, type=_typename(c))
            for c in resp.manifest.schema.columns
        ]
    rows = [list(r) for r in (resp.result.data_array or [])] if resp.result else []
    return ResultSet(
        columns=cols, rows=rows,
        row_count=(resp.result.row_count if resp.result and resp.result.row_count is not None else len(rows)),
        truncated=bool(resp.result and (resp.result.next_chunk_index or resp.result.external_links)),
    )
