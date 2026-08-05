"""
The fast tier: web + news search and page extraction.

These call the Milestone B Unity Catalog functions (`era_you_search`,
`era_you_contents`) rather than hitting You.com directly.

WHY GO THROUGH THE UC FUNCTIONS INSTEAD OF httpx
------------------------------------------------
Direct HTTP would be a little faster and would avoid the warehouse dependency. It
would also mean the domain allow/deny policy exists twice - once in the generated SQL
that Milestone B deploys, and once in Python here - with nothing keeping them
identical. Two copies of an egress policy is how an egress policy stops being true.

So the SQL function stays the single enforcement point for *which domains*, and this
module adds what SQL cannot do: redaction, sensitivity-based refusal, and an audit
row per call. The layers compose rather than duplicate.

The gate runs before the statement is ever built, so a refused call never reaches the
warehouse, let alone You.com.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from era.tools.redaction import AuditSink, Sensitivity, require

logger = logging.getLogger("era.you.fast")


@dataclass(frozen=True)
class WebResult:
    url: str
    title: str
    description: str
    retrieved_at: str
    section: str = "web"          # "web" or "news"
    published: str | None = None
    markdown: str | None = None


@dataclass
class SearchResponse:
    results: tuple[WebResult, ...]
    query_sent: str
    domain_mode: str

    @property
    def urls(self) -> set[str]:
        """Feed straight into provenance.Evidence.external_urls."""
        return {r.url for r in self.results}

    @property
    def news(self) -> tuple[WebResult, ...]:
        return tuple(r for r in self.results if r.section == "news")


class ToolError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# SQL execution, injectable for tests
# ---------------------------------------------------------------------------


class SqlExecutor(Protocol):
    def scalar(self, statement: str, params: list[dict]) -> str: ...


class WarehouseExecutor:
    """Runs the UC function on a SQL warehouse via the Statement Execution API."""

    def __init__(self, warehouse_id: str, workspace_client=None):
        self.warehouse_id = warehouse_id
        self._w = workspace_client

    def _client(self):
        if self._w is None:
            from databricks.sdk import WorkspaceClient

            self._w = WorkspaceClient()
        return self._w

    def scalar(self, statement: str, params: list[dict]) -> str:
        w = self._client()
        resp = w.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=statement,
            parameters=params,
            wait_timeout="50s",
        )
        state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
        if state != "SUCCEEDED":
            detail = resp.status.error.message if resp.status and resp.status.error else ""
            raise ToolError(f"statement {state}: {detail}")
        if not resp.result or not resp.result.data_array:
            raise ToolError("statement returned no rows")
        return resp.result.data_array[0][0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ToolError(f"tool returned non-JSON: {str(raw)[:200]}") from exc

    # The UC functions wrap transport failures in an era_error envelope rather than
    # returning an empty string, precisely so this can be surfaced instead of read as
    # "the web had nothing to say".
    if isinstance(payload, dict) and "era_error" in payload:
        message = f"{payload['era_error']}: {str(payload.get('body'))[:200]}"
        # 402 is a billing state, not a misconfiguration. Saying so here stops the
        # next person debugging the connection, the secret, or the header.
        if "402" in str(payload.get("era_error", "")):
            message += (
                " | The API key is valid and the connection works - the You.com "
                "prepaid balance is depleted. Add credits at you.com/platform."
            )
        raise ToolError(message)
    return payload


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(
    query: str,
    *,
    catalog: str,
    schema: str,
    executor: SqlExecutor,
    freshness: str | None = None,
    count: int = 5,
    include_domains: str | None = None,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    sink: AuditSink | None = None,
    request_id: str | None = None,
) -> SearchResponse:
    """
    Web and news search. One call returns both sections - there is no separate news
    endpoint, and looking for one is a common wrong turn.

    Raises PolicyError if the gate refuses, ToolError if You.com or the warehouse
    fails. Neither is swallowed: a silent empty result would invite the model to
    answer from memory and present it as retrieved fact.
    """
    decision = require(
        query,
        "search",
        sensitivity=sensitivity,
        domain_mode="allow" if include_domains else None,
        sink=sink,
        request_id=request_id,
    )

    statement = f"SELECT {catalog}.{schema}.era_you_search(:q, :freshness, :n, :include)"
    params = [
        {"name": "q", "value": decision.scrubbed_query},
        {"name": "freshness", "value": freshness},
        {"name": "n", "value": str(count)},
        {"name": "include", "value": include_domains},
    ]
    payload = _parse(executor.scalar(statement, params))

    stamp = _now()
    results: list[WebResult] = []
    sections = payload.get("results") or {}
    for section in ("web", "news"):
        for item in sections.get(section) or []:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            contents = item.get("contents") or {}
            results.append(
                WebResult(
                    url=url,
                    title=(item.get("title") or url).strip(),
                    description=(item.get("description") or "").strip(),
                    retrieved_at=stamp,
                    section=section,
                    published=item.get("page_age"),
                    markdown=contents.get("markdown"),
                )
            )

    return SearchResponse(
        results=tuple(results),
        query_sent=decision.scrubbed_query,
        domain_mode=decision.domain_mode,
    )


def contents(
    urls: list[str],
    *,
    catalog: str,
    schema: str,
    executor: SqlExecutor,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    sink: AuditSink | None = None,
    request_id: str | None = None,
) -> tuple[WebResult, ...]:
    """
    Fetch full page text for specific URLs.

    NOT ZDR-covered - the gate refuses anything above `public` under the shipped
    posture. The URLs themselves are the payload here, so a URL carrying an internal
    identifier in its query string is a leak even though the question was innocuous.
    """
    if not urls:
        return ()

    # The URL list IS the outbound payload, so that is what gets scrubbed and audited.
    decision = require(
        " ".join(urls), "contents", sensitivity=sensitivity, sink=sink, request_id=request_id
    )

    array_sql = ", ".join(f":u{i}" for i in range(len(urls)))
    statement = (
        f"SELECT {catalog}.{schema}.era_you_contents(array({array_sql}))"
    )
    params = [{"name": f"u{i}", "value": u} for i, u in enumerate(urls)]
    payload = _parse(executor.scalar(statement, params))

    stamp = _now()
    items = payload if isinstance(payload, list) else payload.get("results") or []
    return tuple(
        WebResult(
            url=(item.get("url") or "").strip(),
            title=(item.get("title") or "").strip(),
            description="",
            retrieved_at=stamp,
            markdown=item.get("markdown"),
        )
        for item in items
        if item.get("url")
    )
