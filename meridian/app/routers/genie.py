"""Genie Conversation API endpoints + SSE status stream + audit logging."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import resolve_identity
from ..config import get_settings
from ..models.schemas import Column, GenieAskRequest, GenieMessageOut, ResultSet
from ..services import chart_inference
from ..services.genie_client import GenieClient, GenieError, extract_answer, tables_used

router = APIRouter(tags=["genie"])


def _augment(q: str, ctx: GenieAskRequest) -> str:
    bits = []
    if ctx.as_of:
        bits.append(f"answer using data on or before {ctx.as_of}")
    if ctx.context_symbol:
        bits.append(f"the question is about symbol {ctx.context_symbol}")
    return f"{q}\n\n(Context: {'; '.join(bits)}.)" if bits else q


async def _finish_message(client: GenieClient, cid: str, mid: str, msg: dict,
                          as_of: str | None, started: float, question: str, identity) -> GenieMessageOut:
    """Normalize a terminal message: extract answer, pull tabular result, audit."""
    ans = extract_answer(msg)
    status = msg.get("status", "UNKNOWN")
    result = None
    lookahead = False
    if status == "COMPLETED" and ans["attachment_id"]:
        try:
            qr = await client.get_query_result(cid, mid, ans["attachment_id"])
            sr = qr.get("statement_response") or {}
            manifest = sr.get("manifest") or {}
            cols = [
                Column(name=c.get("name", f"c{i}"), type=str(c.get("type_name", "STRING")))
                for i, c in enumerate((manifest.get("schema") or {}).get("columns") or [])
            ]
            rows = (sr.get("result") or {}).get("data_array") or []
            truncated = bool((sr.get("result") or {}).get("truncated")) or (sr.get("total_row_count") or 
                0) > len(rows)
            result = ResultSet(columns=cols, rows=rows, row_count=len(rows), truncated=truncated)
            if as_of and result.rows:
                # look-ahead check: max date-ish cell must be <= cursor
                for i, c in enumerate(cols):
                    if "DATE" in c.type.upper() or "TIMESTAMP" in c.type.upper():
                        mx = max(str(r[i])[:10] for r in result.rows if r[i])
                        if mx > as_of:
                            lookahead = True
        except GenieError:
            result = None
    _audit(identity, question, cid, mid, status, time.monotonic() - started,
           result.row_count if result else 0, ans["sql"])
    specs = chart_inference.infer(result.columns, result.rows) if result else []
    out = GenieMessageOut(
        conversation_id=cid, message_id=mid, status=status,
        text=ans["text"], sql=ans["sql"], query_description=ans["query_description"],
        result=result, suggested=ans["suggested"], attachment_id=ans["attachment_id"],
        tables_used=tables_used(ans["sql"]), as_of=as_of, lookahead_warning=lookahead,
    )
    out_dict = out.model_dump()
    out_dict["chart_specs"] = [s.model_dump() for s in specs]
    return out


@router.post("/api/genie/conversations")
async def start_conversation(request: Request, body: GenieAskRequest) -> Any:
    identity = resolve_identity(request)
    if get_settings().mock:
        return _mock_answer(body)
    client = GenieClient(identity)
    t0 = time.monotonic()
    try:
        started = await client.start_conversation(_augment(body.question, body))
        cid = started.get("conversation_id") or (started.get("conversation") or {}).get("id")
        mid = started.get("message_id") or (started.get("message") or {}).get("id")
        async for msg in client.poll_until_done(cid, mid):
            last = msg
        return await _finish_message(client, cid, mid, last, body.as_of, t0, body.question, identity)
    except GenieError as e:
        raise _http_error(e) from e


@router.post("/api/genie/conversations/{cid}/messages")
async def follow_up(request: Request, cid: str, body: GenieAskRequest) -> Any:
    identity = resolve_identity(request)
    if get_settings().mock:
        return _mock_answer(body, cid)
    client = GenieClient(identity)
    t0 = time.monotonic()
    try:
        created = await client.create_message(cid, _augment(body.question, body))
        mid = created.get("message_id") or (created.get("message") or {}).get("id") or created.get("id")
        async for msg in client.poll_until_done(cid, mid):
            last = msg
        return await _finish_message(client, cid, mid, last, body.as_of, t0, body.question, identity)
    except GenieError as e:
        raise _http_error(e) from e


@router.get("/api/genie/conversations/{cid}/messages/{mid}")
async def get_message(request: Request, cid: str, mid: str) -> Any:
    identity = resolve_identity(request)
    if get_settings().mock:
        return _mock_answer(GenieAskRequest(question="(poll)"), cid)
    client = GenieClient(identity)
    try:
        msg = await client.get_message(cid, mid)
        if msg.get("status") in {"COMPLETED", "FAILED", "CANCELLED"}:
            return await _finish_message(client, cid, mid, msg, None, time.monotonic(), "", identity)
        return GenieMessageOut(conversation_id=cid, message_id=mid,
                               status=msg.get("status", "UNKNOWN"))
    except GenieError as e:
        raise _http_error(e) from e


@router.get("/api/genie/conversations/{cid}/messages/{mid}/stream")
async def stream_message(request: Request, cid: str, mid: str) -> StreamingResponse:
    """SSE relay of Genie status transitions (FEATURE_STREAMING gated)."""
    identity = resolve_identity(request)

    async def gen():
        if get_settings().mock or not get_settings().feature_streaming:
            yield f"data: {json.dumps({'status': 'COMPLETED'})}\n\n"
            return
        client = GenieClient(identity)
        try:
            async for msg in client.poll_until_done(cid, mid):
                yield f"data: {json.dumps({'status': msg.get('status')})}\n\n"
        except GenieError as e:
            yield f"data: {json.dumps({'status': 'ERROR', 'code': e.code, 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


class RunSqlBody(BaseModel):
    sql: str


@router.post("/api/genie/run-sql")
async def run_sql(request: Request, body: RunSqlBody) -> ResultSet:
    """Pinned-insight refresh: stored SQL, SELECT/WITH only, caller's identity."""
    from ..services.sql_exec import run_readonly_sql

    identity = resolve_identity(request)
    if get_settings().mock:
        from ..auth import Identity
        from ..services import market_data as md

        rs, _ = md.get_screener(None, Identity(mode="mock", user="mock", token=None))
        rs.rows = rs.rows[:20]
        rs.row_count = len(rs.rows)
        return rs
    return run_readonly_sql(body.sql, identity)


class FeedbackBody(BaseModel):
    rating: int  # +1 / -1
    comment: str | None = None


@router.post("/api/genie/conversations/{cid}/messages/{mid}/feedback")
def feedback(request: Request, cid: str, mid: str, body: FeedbackBody) -> dict:
    identity = resolve_identity(request)
    _audit(identity, "", cid, mid, f"FEEDBACK_{body.rating}", 0, 0, body.comment)
    return {"ok": True}


def _mock_answer(body: GenieAskRequest, cid: str | None = None) -> dict:
    """Deterministic mock answer so the UI is fully exercisable without Genie."""
    import uuid

    from ..auth import Identity
    from ..services import market_data as md

    rs, _ = md.get_screener(None, Identity(mode="mock", user="mock", token=None))
    rs.rows = rs.rows[:10]
    rs.row_count = len(rs.rows)
    specs = chart_inference.infer(rs.columns, rs.rows)
    return {
        "conversation_id": cid or f"mock-{uuid.uuid4().hex[:8]}",
        "message_id": f"m-{uuid.uuid4().hex[:8]}",
        "status": "COMPLETED",
        "text": (
            f"Mock answer for: “{body.question}”. Based on synthetic data, "
            "here are the top securities by market cap with returns."
        ),
        "sql": (
            "SELECT r.symbol, d.name, d.sector, r.last, r.ret_1y "
            "FROM fins.meridian.v_returns r "
            "JOIN fins.meridian.dim_security d USING (symbol) "
            "ORDER BY d.market_cap DESC LIMIT 10"
        ),
        "query_description": "Top 10 securities by market cap with latest price and 1Y return",
        "result": rs.model_dump(),
        "suggested": ["Break that down by sector", "Show only Technology names", "Sort by 1M return instead"],
        "attachment_id": "mock-att",
        "tables_used": ["fins.meridian.v_returns", "fins.meridian.dim_security"],
        "as_of": body.as_of,
        "lookahead_warning": False,
        "chart_specs": [s.model_dump() for s in specs],
    }


def _audit(identity, question: str, cid: str, mid: str, status: str,
           latency: float, row_count: int, sql: str | None) -> None:
    """Best-effort background audit write — never blocks the response."""
    settings = get_settings()
    if settings.mock:
        return

    def _write() -> None:
        try:
            from databricks.sdk import WorkspaceClient
            from databricks.sdk.service.sql import StatementParameterListItem

            w = WorkspaceClient()  # audit is app-internal → service principal
            sql_hash = hashlib.sha256((sql or "").encode()).hexdigest()[:16]
            w.statement_execution.execute_statement(
                warehouse_id=settings.warehouse_id,
                statement=(
                    f"INSERT INTO {settings.fq_prefix}.app_genie_audit "
                    "(user_email, question, conversation_id, message_id, status, "
                    "latency_s, row_count, sql_hash, created_at) VALUES "
                    "(:user, :q, :cid, :mid, :status, :lat, :rc, :sh, current_timestamp())"
                ),
                parameters=[
                    StatementParameterListItem(name="user", value=identity.user),
                    StatementParameterListItem(name="q", value=question[:4000]),
                    StatementParameterListItem(name="cid", value=cid),
                    StatementParameterListItem(name="mid", value=mid),
                    StatementParameterListItem(name="status", value=status),
                    StatementParameterListItem(name="lat", value=f"{latency:.1f}"),
                    StatementParameterListItem(name="rc", value=str(row_count)),
                    StatementParameterListItem(name="sh", value=sql_hash),
                ],
                wait_timeout="10s",
            )
        except Exception:
            pass  # audit must never break the request path

    try:
        asyncio.get_running_loop().run_in_executor(None, _write)
    except RuntimeError:
        pass


def _http_error(e: GenieError):
    from fastapi import HTTPException

    code = {"RATE_LIMITED": 429, "PERMISSION_DENIED": 403, "GENIE_TIMEOUT": 504}.get(e.code, 502)
    return HTTPException(status_code=code, detail={"code": e.code, "message": str(e), "retryable": 
        e.retryable})
