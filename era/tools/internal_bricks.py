"""
Internal evidence: the Knowledge Assistant and the Genie space, called as tools.

These wrap the bricks era already builds in `setup_instructor/01` and `02`. They are
not rebuilt here - the KA is queried through its serving endpoint and Genie through
the Conversations API, exactly as the low-code path does.

WHAT THIS ADDS OVER CALLING THEM DIRECTLY: LINEAGE
--------------------------------------------------
Provenance validation resolves every `[IV:<lineage>]` tag back to something a tool
actually returned. That only works if the tool reports *what it read*, not just what
it concluded. So both wrappers return an `InternalResult` carrying explicit lineage:

    Genie  -> the fully-qualified tables its generated SQL touched
    KA     -> the document identifiers behind its citations

Without that, an internal claim is unverifiable in exactly the way an uncited web
claim is, and tagging it `internal-verified` would be a promise the system cannot
keep. A KA that returns no citations therefore yields no lineage, and the synthesis
step must fall back to `[INF]` rather than claim verification it does not have.

No egress gate here: none of this leaves the Databricks boundary. That asymmetry is
the point of the whole architecture.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger("era.internal")


@dataclass(frozen=True)
class InternalResult:
    """One internal tool call: what it said, and what it read to say it."""

    answer: str
    lineage: tuple[str, ...]
    source: str                      # "knowledge_assistant" | "genie"
    sql: str | None = None
    rows: tuple[tuple[Any, ...], ...] = ()
    columns: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)

    @property
    def has_lineage(self) -> bool:
        """
        False means any claim built on this must be tagged [INF], not [IV].

        Callers should check this rather than assuming an answer implies verification.
        """
        return bool(self.lineage)


class InternalToolError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Knowledge Assistant
# ---------------------------------------------------------------------------


class ServingClient(Protocol):
    def query(self, endpoint: str, messages: list[dict]) -> dict: ...


class WorkspaceServingClient:
    """Queries a Knowledge Assistant endpoint through the Responses API."""

    def __init__(self, workspace_client=None):
        self._w = workspace_client

    def _client(self):
        if self._w is None:
            from databricks.sdk import WorkspaceClient

            self._w = WorkspaceClient()
        return self._w

    def query(self, endpoint: str, messages: list[dict]) -> dict:
        """
        USES THE RESPONSES API, NOT `messages`.

        Agent Bricks endpoints (KA and MAS) speak Responses and reject
        chat-completions payloads outright: "Invalid request: 'messages' field is
        not supported. Please use 'input' field instead." Foundation Model endpoints
        are the mirror image - they reject Responses and want chat completions (see
        EraSupervisor._llm, which hit exactly that).

        Both errors only surface against a live endpoint and they point in opposite
        directions, so the rule worth remembering is: agent endpoints take `input`,
        model endpoints take `messages`.
        """
        client = self._client().serving_endpoints.get_open_ai_client()
        resp = client.responses.create(
            model=endpoint,
            input=[
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages
            ],
        )
        return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)


# Citation shapes vary across Agent Bricks versions, so probe several rather than
# binding to one. Returning no lineage is safe (claims degrade to [INF]); guessing a
# document id would not be.
_DOC_ID_KEYS = ("doc_uri", "document_id", "doc_id", "source", "chunk_id", "url", "path")


def _compact_lineage(value: str) -> str:
    """
    Reduce a KA citation URI to a short, stable document reference.

    The KA returns fully-qualified signed URLs carrying a page anchor AND a
    percent-encoded `:~:text=` fragment of the quoted passage - routinely 1-2 KB
    each. A lineage identifier ends up inside an `[IV:...]` tag in the answer, so
    the model would have to reproduce two kilobytes of URL-encoded text verbatim
    for the citation to validate. It will not, and provenance would fail on every
    correctly-sourced internal claim.

    So keep the part that identifies the document - the volume path and page - and
    drop the quotation fragment and host. `/Volumes/cat/schema/vol/10k/nvidia.pdf#page=13`
    is short enough to echo, stable across runs, and still resolves for a reader.
    """
    text = (value or "").strip()
    if "/Volumes/" in text:
        text = "/Volumes/" + text.split("/Volumes/", 1)[1]
    # Drop the highlight fragment but keep a page anchor if present.
    if ":~:text=" in text:
        text = text.split(":~:text=", 1)[0]
    return text.rstrip("#").rstrip()


def _extract_ka_lineage(payload: dict) -> tuple[str, ...]:
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in _DOC_ID_KEYS:
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    found.append(value.strip())
                    break
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    # Compact first, then dedupe: several citations often point at the same page
    # with different highlight fragments, which are the same source.
    return tuple(dict.fromkeys(_compact_lineage(f) for f in found if _compact_lineage(f)))


def _extract_text(payload: dict) -> str:
    """Pull assistant text from either a Responses or a chat-completions payload."""
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for chunk in item.get("content") or []:
            if isinstance(chunk, dict) and chunk.get("text"):
                parts.append(chunk["text"])
    if parts:
        return "\n".join(parts)

    choices = payload.get("choices") or []
    if choices:
        text = ((choices[0] or {}).get("message") or {}).get("content", "") or ""
        if text:
            return text
    return payload.get("output_text") or payload.get("content") or ""


def ask_documents(
    question: str,
    *,
    endpoint: str,
    client: ServingClient | None = None,
) -> InternalResult:
    """
    Ask the Knowledge Assistant. Authoritative for what a company has formally stated.

    Returns document lineage where the KA provides citations. When it does not, the
    result carries no lineage and `has_lineage` is False - the caller must not tag
    the resulting claim as verified.
    """
    payload = (client or WorkspaceServingClient()).query(
        endpoint, [{"role": "user", "content": question}]
    )

    # Responses shape first (what an Agent Bricks endpoint returns), then the
    # chat-completions shape, so this keeps working if the KA is ever fronted by a
    # plain model endpoint.
    answer = _extract_text(payload)

    if not answer:
        raise InternalToolError(f"knowledge assistant returned no content: {str(payload)[:200]}")

    lineage = _extract_ka_lineage(payload)
    if not lineage:
        logger.info("KA returned no citations; claims from this result cannot be tagged [IV]")

    return InternalResult(
        answer=answer, lineage=lineage, source="knowledge_assistant", raw=payload
    )


# ---------------------------------------------------------------------------
# Genie
# ---------------------------------------------------------------------------


class GenieClient(Protocol):
    def start(self, space_id: str, content: str) -> dict: ...
    def get_message(self, space_id: str, conversation_id: str, message_id: str) -> dict: ...
    def get_result(self, space_id: str, conversation_id: str, message_id: str, attachment_id: str) -> dict: ...


class WorkspaceGenieClient:
    def __init__(self, workspace_client=None):
        self._w = workspace_client

    def _client(self):
        if self._w is None:
            from databricks.sdk import WorkspaceClient

            self._w = WorkspaceClient()
        return self._w

    def start(self, space_id: str, content: str) -> dict:
        return self._client().api_client.do(
            "POST",
            f"/api/2.0/genie/spaces/{space_id}/start-conversation",
            body={"content": content},
        )

    def get_message(self, space_id: str, conversation_id: str, message_id: str) -> dict:
        return self._client().api_client.do(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}",
        )

    def get_result(self, space_id, conversation_id, message_id, attachment_id) -> dict:
        return self._client().api_client.do(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}"
            f"/messages/{message_id}/attachments/{attachment_id}/query-result",
        )


# Matches FROM / JOIN targets, including backticked identifiers.
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(`?[\w]+`?(?:\.`?[\w]+`?){1,2})", re.I
)
_SQL_KEYWORDS = {"select", "lateral", "unnest", "values", "table"}


def extract_tables(sql: str) -> tuple[str, ...]:
    """
    Pull fully-qualified table names out of Genie's generated SQL.

    Deliberately conservative: this feeds provenance lineage, so a name invented by a
    loose regex would let a claim cite a table that was never read. Missing a table is
    recoverable (the claim degrades to [INF]); inventing one is not.
    """
    if not sql:
        return ()
    found: list[str] = []
    for match in _TABLE_RE.finditer(sql):
        name = match.group(1).replace("`", "")
        if name.split(".")[0].lower() in _SQL_KEYWORDS:
            continue
        # Only fully-qualified names are trustworthy lineage. A bare table name
        # cannot be resolved to a catalog and schema without guessing.
        if name.count(".") >= 1 and name not in found:
            found.append(name)
    return tuple(found)


def query_data(
    question: str,
    *,
    space_id: str,
    client: GenieClient | None = None,
    poll_interval: float = 2.0,
    timeout: float = 120.0,
    sleep=time.sleep,
) -> InternalResult:
    """
    Ask Genie a natural-language question over governed tables.

    Authoritative for numbers. Returns the generated SQL plus the tables it touched,
    so a numeric claim can be traced to its source table rather than merely asserted.
    """
    genie = client or WorkspaceGenieClient()
    started = genie.start(space_id, question)

    conversation_id = started.get("conversation_id") or (started.get("conversation") or {}).get("id")
    message = started.get("message") or {}
    message_id = message.get("id") or started.get("message_id")
    if not conversation_id or not message_id:
        raise InternalToolError(f"genie start-conversation returned no ids: {str(started)[:200]}")

    deadline = time.monotonic() + timeout
    status = message.get("status")
    while status not in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
        if time.monotonic() > deadline:
            raise InternalToolError(f"genie did not settle within {timeout}s (last status {status})")
        sleep(poll_interval)
        message = genie.get_message(space_id, conversation_id, message_id)
        status = message.get("status")

    if status != "COMPLETED":
        raise InternalToolError(f"genie query {status}: {message.get('error') or ''}")

    attachments = message.get("attachments") or []
    text_parts: list[str] = []
    sql = None
    rows: tuple[tuple[Any, ...], ...] = ()
    columns: tuple[str, ...] = ()

    for attachment in attachments:
        if attachment.get("text"):
            text_parts.append(attachment["text"].get("content", ""))
        query = attachment.get("query")
        if not query:
            continue
        sql = query.get("query") or sql
        if query.get("description"):
            text_parts.append(query["description"])
        result = genie.get_result(space_id, conversation_id, message_id, attachment.get("attachment_id"))
        manifest = ((result.get("statement_response") or {}).get("manifest") or {})
        schema = (manifest.get("schema") or {}).get("columns") or []
        columns = tuple(c.get("name", "") for c in schema)
        data = ((result.get("statement_response") or {}).get("result") or {}).get("data_array") or []
        rows = tuple(tuple(r) for r in data)

    return InternalResult(
        answer="\n\n".join(p for p in text_parts if p).strip(),
        lineage=extract_tables(sql or ""),
        source="genie",
        sql=sql,
        rows=rows,
        columns=columns,
        raw=message,
    )
