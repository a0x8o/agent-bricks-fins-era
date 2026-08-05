"""
The slow tier: You.com Research and Finance Research.

Both endpoints take minutes. Neither belongs in a SQL function, and neither may block
a chat turn. The two are NOT symmetric, and the asymmetry drives the design:

    /v1/research          supports `background: true`, returning {task_id, status,
                          stream_url}. Poll GET /v1/research/{task_id} until the
                          status settles. `research_effort: frontier` REQUIRES
                          background - a synchronous frontier request returns 422.
                          p50 ~300s, tail to 12000s.

    /v1/finance_research  documents only `input` and `research_effort` (deep |
                          exhaustive). There is NO background flag, so You.com will
                          never hand us a task id. It is a slow synchronous call, and
                          the non-blocking behaviour has to come from an ERA-side
                          worker driving the LangGraph checkpoint resume instead.

Verified against the live API reference on 2026-08-03.

HOW THE NON-BLOCKING TURN WORKS
-------------------------------
Adapted from the banking accelerator's pattern (see era/agent/_ref_banking_async_resume.py):

    turn 1   submit() -> task_id, checkpoint it into the graph state, answer the user
             with what internal data already supports and note that research is running
    worker   poll until settled, then graph.aupdate_state(config, {research_result: ...})
    turn 2   the graph resumes from the checkpoint with the result in state

Nothing here waits on the result inside the request that started it.

Every call passes the egress gate first. Note that Research and Finance Research are
NOT covered by You.com's zero-data-retention term - only /v1/search is - so with the
shipped default posture the gate refuses anything above `public` sensitivity. That is
intentional: a 40,000-character research question is the most sensitive payload ERA
sends anywhere.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from era.tools.redaction import AuditSink, GateDecision, Sensitivity, audit, require

logger = logging.getLogger("era.you.research")

RESEARCH_HOST = "https://api.you.com"
RESEARCH_PATH = "/v1/research"
FINANCE_PATH = "/v1/finance_research"

SECRET_ENV = "YOU_API_KEY"  # injected from the Databricks secret scope at deploy time

MAX_INPUT_CHARS = 40_000


class Effort(str, Enum):
    LITE = "lite"
    STANDARD = "standard"
    DEEP = "deep"
    EXHAUSTIVE = "exhaustive"
    FRONTIER = "frontier"


# Only these two are accepted by Finance Research.
FINANCE_EFFORTS = {Effort.DEEP, Effort.EXHAUSTIVE}

# frontier is background-only; a synchronous request returns 422.
BACKGROUND_ONLY = {Effort.FRONTIER}


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def settled(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


@dataclass(frozen=True)
class Citation:
    n: int
    url: str
    title: str
    retrieved_at: str
    snippets: tuple[str, ...] = ()


@dataclass
class ResearchResult:
    """Normalised shape shared by Research and Finance Research."""

    answer_md: str
    citations: tuple[Citation, ...]
    effort: str
    endpoint: str
    cost_usd: float | None = None
    warnings: tuple[str, ...] = ()

    @property
    def urls(self) -> set[str]:
        """Feed straight into provenance.Evidence.external_urls."""
        return {c.url for c in self.citations}


@dataclass
class ResearchTask:
    task_id: str
    status: TaskStatus
    endpoint: str
    effort: str
    submitted_at: str
    result: ResearchResult | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def settled(self) -> bool:
        return self.status.settled


class ResearchError(RuntimeError):
    pass


def _http_error(label: str, status_code: int, payload) -> ResearchError:
    """Build an error that names the cause, not just the status code."""
    message = f"{label} failed: HTTP {status_code} {str(payload)[:300]}"
    if status_code == 402:
        message += (
            " | payment_required: the key is valid and the request reached You.com, "
            "but the prepaid balance is depleted. Add credits at you.com/platform."
        )
    return ResearchError(message)


# ---------------------------------------------------------------------------
# Transport
#
# Injectable so the whole module is testable without network, an API key, or a
# five-minute wait. The default implementation is the only place httpx appears.
# ---------------------------------------------------------------------------


class Transport(Protocol):
    def post(self, url: str, json: dict, headers: dict, timeout: float) -> tuple[int, dict]: ...
    def get(self, url: str, headers: dict, timeout: float) -> tuple[int, dict]: ...


class HttpxTransport:
    def _client(self):
        import httpx

        return httpx.Client(follow_redirects=False)

    def post(self, url: str, json: dict, headers: dict, timeout: float) -> tuple[int, dict]:
        with self._client() as client:
            resp = client.post(url, json=json, headers=headers, timeout=timeout)
            return resp.status_code, _safe_json(resp)

    def get(self, url: str, headers: dict, timeout: float) -> tuple[int, dict]:
        with self._client() as client:
            resp = client.get(url, headers=headers, timeout=timeout)
            return resp.status_code, _safe_json(resp)


def _safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:2000]}


_default_transport: Transport = HttpxTransport()


def set_transport(transport: Transport) -> None:
    global _default_transport
    _default_transport = transport


def _headers() -> dict:
    """
    You.com REST authenticates with X-API-Key, NOT a bearer token - the MCP endpoint
    is the one that takes a bearer. Getting this wrong produces a 401 that looks like
    a bad key rather than a bad header.
    """
    key = os.environ.get(SECRET_ENV, "")
    if not key:
        raise ResearchError(
            f"{SECRET_ENV} is not set. It is injected from the Databricks secret "
            f"scope at deploy time; for local runs export it from your own secret store."
        )
    return {"X-API-Key": key, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _to_result(payload: dict, *, endpoint: str, effort: str, retrieved_at: str | None = None) -> ResearchResult:
    """
    Map a You.com response onto ResearchResult.

    The retrieval timestamp is stamped by US, not returned by You.com. The provenance
    format requires a retrieved_at on every external citation, and "when we received
    it" is the honest answer - a source's own publication date says nothing about when
    we actually read it.
    """
    stamp = retrieved_at or _now()
    output = payload.get("output") or {}
    content = output.get("content")
    if isinstance(content, dict):
        # output_schema was used; keep the structured form as JSON text.
        import json

        content = json.dumps(content, indent=2)

    citations = tuple(
        Citation(
            n=i,
            url=(src.get("url") or "").strip(),
            title=(src.get("title") or "").strip() or (src.get("url") or ""),
            retrieved_at=stamp,
            snippets=tuple(src.get("snippets") or ()),
        )
        for i, src in enumerate(output.get("sources") or [], start=1)
        if src.get("url")
    )

    return ResearchResult(
        answer_md=content or "",
        citations=citations,
        effort=effort,
        endpoint=endpoint,
        warnings=tuple(payload.get("warnings") or ()),
    )


# ---------------------------------------------------------------------------
# Research (async-capable)
# ---------------------------------------------------------------------------


def submit_research(
    query: str,
    *,
    effort: Effort = Effort.STANDARD,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    source_control: dict | None = None,
    transport: Transport | None = None,
    sink: AuditSink | None = None,
    request_id: str | None = None,
) -> ResearchTask:
    """
    Start a background research task and return immediately.

    Raises PolicyError if the egress gate refuses. Callers must not catch that and
    retry against a different endpoint - the refusal is about the data, not the route.
    """
    if len(query) > MAX_INPUT_CHARS:
        raise ResearchError(f"input exceeds You.com's {MAX_INPUT_CHARS} character limit")

    decision = require(
        query, "research", sensitivity=sensitivity, sink=sink, request_id=request_id
    )

    body: dict[str, Any] = {
        "input": decision.scrubbed_query,
        "research_effort": effort.value,
        # Always background. Even for efforts that permit a synchronous call, holding
        # a chat turn open for a p50 of 300s is not a behaviour worth having.
        "background": True,
    }
    if source_control:
        body["source_control"] = source_control

    status_code, payload = (transport or _default_transport).post(
        f"{RESEARCH_HOST}{RESEARCH_PATH}", json=body, headers=_headers(), timeout=60.0
    )
    if status_code >= 400:
        raise _http_error("research submit", status_code, payload)

    task_id = payload.get("task_id")
    if not task_id:
        raise ResearchError(f"research submit returned no task_id: {str(payload)[:300]}")

    return ResearchTask(
        task_id=task_id,
        status=TaskStatus(payload.get("status", "queued")),
        endpoint="research",
        effort=effort.value,
        submitted_at=_now(),
        raw=payload,
    )


def poll_research(
    task_id: str,
    *,
    effort: str = Effort.STANDARD.value,
    transport: Transport | None = None,
) -> ResearchTask:
    """
    Check a background task once. Never blocks or sleeps.

    Deliberately not a wait loop: the caller is either a worker with its own schedule
    or a graph resume, and neither wants this function deciding how long to sleep.
    """
    status_code, payload = (transport or _default_transport).get(
        f"{RESEARCH_HOST}{RESEARCH_PATH}/{task_id}", headers=_headers(), timeout=30.0
    )
    if status_code >= 400:
        raise _http_error("research poll", status_code, payload)

    status = TaskStatus(payload.get("status", "running"))
    task = ResearchTask(
        task_id=task_id,
        status=status,
        endpoint="research",
        effort=effort,
        submitted_at=payload.get("created_at", ""),
        error=payload.get("error"),
        raw=payload,
    )

    if status is TaskStatus.COMPLETED:
        result_payload = payload.get("result") or {}
        task.result = _to_result(result_payload, endpoint="research", effort=effort)
    return task


# ---------------------------------------------------------------------------
# Finance Research (synchronous only)
# ---------------------------------------------------------------------------


def finance_research(
    query: str,
    *,
    effort: Effort = Effort.DEEP,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    transport: Transport | None = None,
    sink: AuditSink | None = None,
    request_id: str | None = None,
    timeout: float = 900.0,
) -> ResearchResult:
    """
    Run a Finance Research query. BLOCKS for minutes - never call this on a chat turn.

    You.com documents no `background` flag for this endpoint, so there is no task id
    to poll. The only way to keep a turn responsive is to run this in an ERA-side
    worker and resume the graph when it returns; see the module docstring.
    """
    if effort not in FINANCE_EFFORTS:
        raise ResearchError(
            f"finance_research accepts only {sorted(e.value for e in FINANCE_EFFORTS)}; "
            f"got {effort.value}"
        )
    if len(query) > MAX_INPUT_CHARS:
        raise ResearchError(f"input exceeds You.com's {MAX_INPUT_CHARS} character limit")

    decision = require(
        query, "finance_research", sensitivity=sensitivity, sink=sink, request_id=request_id
    )

    status_code, payload = (transport or _default_transport).post(
        f"{RESEARCH_HOST}{FINANCE_PATH}",
        json={"input": decision.scrubbed_query, "research_effort": effort.value},
        headers=_headers(),
        timeout=timeout,
    )
    if status_code >= 400:
        raise _http_error("finance_research", status_code, payload)

    return _to_result(payload, endpoint="finance_research", effort=effort.value)


def record_completion(
    task: ResearchTask,
    original_query: str,
    *,
    latency_ms: int | None = None,
    cost_usd: float | None = None,
    sink: AuditSink | None = None,
) -> None:
    """
    Audit the completion of a background task.

    The submit was audited when it left; this closes the loop with cost and latency,
    which is the only point at which either is known. Still hashes only.
    """
    decision = GateDecision(
        allowed=task.status is TaskStatus.COMPLETED,
        reason=task.error or task.status.value,
        endpoint=task.endpoint,
        scrubbed_query="",
    )
    audit(
        decision,
        original_query,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        request_id=task.task_id,
        sink=sink,
    )
