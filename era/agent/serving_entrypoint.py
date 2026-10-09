"""
Model-from-code entrypoint for the ERA supervisor.

This is the file MLflow logs and the serving container executes. Everything the
agent needs at request time is resolved here from environment variables, because a
serving replica has no repo, no config.py and no notebook context - only the env
its deployment was given.

WHAT CHANGES BETWEEN OFFLINE AND SERVED
---------------------------------------
Offline the supervisor is driven through `run_turn` with injected fakes. Served, the
same node functions run against real tools, so this module is entirely about wiring:
building a ToolBundle from env, adapting return types, and choosing an audit sink
that works without Spark.

THE AUDIT SINK IS THE PART THAT MUST NOT BE LEFT ON ITS DEFAULT
--------------------------------------------------------------
`redaction.py` defaults to an in-memory sink so the gate stays testable. In a serving
container that default silently discards every audit row: the gate would appear to
work, refusals would be enforced, and nothing would be recorded. So this module
installs a warehouse-backed sink at import and refuses to pretend otherwise if it
cannot - see `_install_audit_sink`.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Generator
from typing import Any

from mlflow.models import set_model
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from era.agent.supervisor import ToolBundle, new_state, run_turn
from era.tools.redaction import Sensitivity

logger = logging.getLogger("era.serving")


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ENV_CATALOG = "ERA_CATALOG"
ENV_SCHEMA = "ERA_SCHEMA"
ENV_LLM = "ERA_LLM_ENDPOINT"
ENV_KA = "ERA_KA_ENDPOINT"
ENV_GENIE = "ERA_GENIE_SPACE_ID"
ENV_WAREHOUSE = "ERA_WAREHOUSE_ID"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _install_audit_sink() -> None:
    """
    Point the gate at a durable sink.

    A warehouse id is required rather than optional: without it the gate would fall
    back to the in-memory sink and every egress decision this agent makes would be
    lost. An agent that enforces policy but cannot prove it did is not the product.
    """
    from era.tools.redaction import SqlWarehouseAuditSink, set_audit_sink

    warehouse = _env(ENV_WAREHOUSE)
    catalog, schema = _env(ENV_CATALOG), _env(ENV_SCHEMA)
    if not (warehouse and catalog and schema):
        logger.error(
            "%s/%s/%s are not all set - egress decisions will NOT be persisted. "
            "Set them on the endpoint before treating the audit trail as complete.",
            ENV_WAREHOUSE, ENV_CATALOG, ENV_SCHEMA,
        )
        return
    set_audit_sink(SqlWarehouseAuditSink(catalog, schema, warehouse))
    logger.info("audit sink -> %s.%s.egress_audit", catalog, schema)


# ---------------------------------------------------------------------------
# Tool adapters
#
# The node functions consume plain dicts so they stay testable without importing
# any Databricks SDK. These adapters are the only place the dataclasses returned by
# the tool modules get flattened.
# ---------------------------------------------------------------------------


def _documents_tool(question: str) -> dict:
    from era.tools import internal_bricks

    endpoint = _env(ENV_KA)
    if not endpoint:
        raise RuntimeError(f"{ENV_KA} is not set")
    return dataclasses.asdict(internal_bricks.ask_documents(question, endpoint=endpoint))


def _data_tool(question: str) -> dict:
    from era.tools import internal_bricks

    space_id = _env(ENV_GENIE)
    if not space_id:
        raise RuntimeError(f"{ENV_GENIE} is not set")
    return dataclasses.asdict(internal_bricks.query_data(question, space_id=space_id))


def _search_tool(question: str, sensitivity: Sensitivity) -> list[dict]:
    from era.tools import you_fast

    warehouse = _env(ENV_WAREHOUSE)
    if not warehouse:
        raise RuntimeError(f"{ENV_WAREHOUSE} is not set")
    response = you_fast.search(
        question,
        catalog=_env(ENV_CATALOG),
        schema=_env(ENV_SCHEMA),
        executor=you_fast.WarehouseExecutor(warehouse),
        sensitivity=sensitivity,
    )
    return [dataclasses.asdict(r) for r in response.results]


def _contents_tool(urls: list[str], sensitivity: Sensitivity) -> list[dict]:
    from era.tools import you_fast

    warehouse = _env(ENV_WAREHOUSE)
    if not warehouse:
        raise RuntimeError(f"{ENV_WAREHOUSE} is not set")
    pages = you_fast.contents(
        urls,
        catalog=_env(ENV_CATALOG),
        schema=_env(ENV_SCHEMA),
        executor=you_fast.WarehouseExecutor(warehouse),
        sensitivity=sensitivity,
    )
    return [dataclasses.asdict(r) for r in pages]


def _research_tool(question: str, sensitivity: Sensitivity) -> str:
    from era.tools import you_research

    task = you_research.submit_research(question, sensitivity=sensitivity)
    return task.task_id


def build_tools() -> ToolBundle:
    """
    Assemble only the tools this deployment is actually configured for.

    Each is gated on its own env var so a partial deployment degrades to fewer
    tools rather than failing at request time - the supervisor already handles a
    missing tool by noting it, which is a better failure than a 500.
    """
    return ToolBundle(
        ask_documents=_documents_tool if _env(ENV_KA) else None,
        query_data=_data_tool if _env(ENV_GENIE) else None,
        search=_search_tool if _env(ENV_WAREHOUSE) else None,
        contents=_contents_tool if _env(ENV_WAREHOUSE) else None,
        submit_research=_research_tool if os.environ.get("YOU_API_KEY") else None,
    )


# ---------------------------------------------------------------------------
# The served agent
# ---------------------------------------------------------------------------

# One message item per turn. The streamed deltas and the completed item share this id
# on purpose: that is how a client tells "these deltas became this item" from "here is
# a second answer", and it is what keeps the app from rendering the text twice.
_ITEM_ID = "era-answer"


def _last_user_message(request: ResponsesAgentRequest) -> str:
    """Pull the current question out of the Responses input list."""
    for item in reversed(list(request.input or [])):
        data = item if isinstance(item, dict) else item.model_dump()
        if data.get("role") != "user":
            continue
        content = data.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("text")
            ]
            if parts:
                return "\n".join(parts)
    return ""


class EraResponsesAgent(ResponsesAgent):
    """ResponsesAgent facade over the plan/act/synthesize/critique pipeline."""

    def __init__(self):
        from era.agent.supervisor import EraSupervisor

        _install_audit_sink()
        self._supervisor = EraSupervisor(model=_env(ENV_LLM) or None, tools=build_tools())

    def _run(self, request: ResponsesAgentRequest) -> tuple[str, dict[str, Any]]:
        """Run one turn and return (answer, custom_outputs). Shared by both entrypoints."""
        question = _last_user_message(request)
        if not question:
            return "I did not receive a question.", {}

        custom = dict(getattr(request, "custom_inputs", None) or {})
        sensitivity = str(custom.get("sensitivity", "public"))

        state = new_state(question, sensitivity=sensitivity)
        # A resumed thread arrives with the background research already injected.
        if custom.get("research_result"):
            state["research_result"] = custom["research_result"]

        state = run_turn(state, llm=self._supervisor._llm, tools=self._supervisor.tools)

        report = state.get("report")
        from era.agent.supervisor import build_evidence

        evidence = build_evidence(state)
        return state.get("answer") or "I was unable to produce an answer.", {
            "provenance_ok": bool(report.ok) if report else None,
            "citation_coverage": report.citation_coverage if report else None,
            "provenance_violations": [str(v) for v in (report.violations if report else ())],
            "notices": state.get("notices", []),
            "research_task_id": state.get("research_task_id"),
            # The evidence the answer was built from. Returned because a caller -
            # the evaluation harness above all - cannot otherwise tell a real
            # citation from an invented one: validating [EC:n] means resolving it
            # against URLs a tool actually returned, and only the agent knows those.
            "evidence": {
                "internal_lineage": sorted(evidence.internal_lineage),
                "external_urls": sorted(evidence.external_urls),
            },
        }

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        text, custom_outputs = self._run(request)
        return self._respond(text, custom_outputs)

    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Streaming entrypoint - required, not optional.

        The chatbot app calls the endpoint through the Vercel AI SDK, which always
        requests a stream; without this method serving raises NotImplementedError and
        every message in the app fails, however healthy `predict` is.

        The pipeline itself is not incremental: plan/act/synthesize/critique has to
        finish before any of the answer can be trusted (the critique step can rewrite
        it), so there is nothing honest to emit early. The turn is run to completion and
        replayed as one delta followed by the completed item. Consumers that render
        deltas and consumers that reduce over `response.output_item.done` - MLflow's own
        trace reducer among them - both see exactly one copy of the answer.
        """
        text, custom_outputs = self._run(request)
        yield ResponsesAgentStreamEvent(**self.create_text_delta(text, item_id=_ITEM_ID))
        yield ResponsesAgentStreamEvent(
            type="response.output_item.done",
            output_index=0,
            item=self.create_text_output_item(text, _ITEM_ID),
            custom_outputs=custom_outputs,
        )

    def _respond(self, text: str, custom_outputs: dict[str, Any]) -> ResponsesAgentResponse:
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text, _ITEM_ID)],
            custom_outputs=custom_outputs,
        )


set_model(EraResponsesAgent())
