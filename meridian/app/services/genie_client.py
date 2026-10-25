"""Genie Conversation API client — runs under the caller's identity (OBO or SP).

REST calls with the user token (OBO) or SDK Config credentials (SP). No PATs.
Polls with exponential backoff; statuses surfaced to the UI verbatim.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from ..auth import Identity
from ..config import get_settings

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


class GenieError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class GenieClient:
    def __init__(self, identity: Identity):
        self.identity = identity
        self.settings = get_settings()
        self.base = f"{self.settings.host}/api/2.0/genie/spaces/{self.settings.genie_space_id}"

    async def _headers(self) -> dict[str, str]:
        if self.identity.mode == "obo" and self.identity.token:
            return {"Authorization": f"Bearer {self.identity.token}"}
        from databricks.sdk.core import Config

        cfg = Config()
        return dict(cfg.authenticate())

    async def _request(self, method: str, path: str, **kw) -> dict[str, Any]:
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, f"{self.base}{path}", headers=headers, **kw)
        if resp.status_code == 429:
            retry = resp.headers.get("retry-after", "30")
            raise GenieError("RATE_LIMITED", f"Genie rate limit — retry in ~{retry}s", retryable=True)
        if resp.status_code == 403:
            raise GenieError("PERMISSION_DENIED", "No access to this Genie space or its tables.", 
                retryable=False)
        if resp.status_code >= 400:
            raise GenieError("GENIE_HTTP", f"Genie {resp.status_code}: {resp.text[:300]}", 
                retryable=resp.status_code >= 500)
        return resp.json()

    async def start_conversation(self, question: str) -> dict:
        return await self._request("POST", "/start-conversation", json={"content": question})

    async def create_message(self, conversation_id: str, question: str) -> dict:
        return await self._request("POST", f"/conversations/{conversation_id}/messages", 
            json={"content": question})

    async def get_message(self, conversation_id: str, message_id: str) -> dict:
        return await self._request("GET", f"/conversations/{conversation_id}/messages/{message_id}")

    async def get_query_result(self, conversation_id: str, message_id: str, attachment_id: str) -> dict:
        return await self._request(
            "GET",
            f"/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result",
        )

    async def poll_until_done(self, conversation_id: str, message_id: str,
                              timeout: int | None = None) -> AsyncIterator[dict]:
        """Yield each message payload as status changes; ends on terminal."""
        timeout = timeout or self.settings.genie_poll_timeout
        delay = 1.0
        start = time.monotonic()
        last_status = None
        while True:
            msg = await self.get_message(conversation_id, message_id)
            status = msg.get("status", "UNKNOWN")
            if status != last_status:
                yield msg
                last_status = status
            if status in TERMINAL:
                return
            if time.monotonic() - start > timeout:
                raise GenieError("GENIE_TIMEOUT", f"Genie did not finish within {timeout}s.", retryable=True)
            await asyncio.sleep(delay)
            delay = min(delay * 1.6, 5.0)


def extract_answer(msg: dict) -> dict[str, Any]:
    """Normalize a Genie message payload → text, sql, description, suggestions."""
    text = None
    sql = None
    description = None
    suggested: list[str] = []
    attachment_id = None
    for att in msg.get("attachments") or []:
        if att.get("query"):
            sql = att["query"].get("query")
            description = att["query"].get("description")
            attachment_id = att.get("attachment_id") or att.get("id")
            suggested = att.get("suggested_questions") or suggested
        if att.get("text"):
            text = att["text"].get("content")
        if att.get("suggested_questions"):
            suggested = att["suggested_questions"]
    return {
        "text": text,
        "sql": sql,
        "query_description": description,
        "suggested": suggested,
        "attachment_id": attachment_id,
    }


def tables_used(sql: str | None) -> list[str]:
    import re

    if not sql:
        return []
    return sorted(set(re.findall(r"(?:from|join)\s+([`a-zA-Z0-9_.]+)", sql, re.IGNORECASE)))
