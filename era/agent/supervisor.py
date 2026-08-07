"""
The code-first supervisor: plan -> act -> synthesize -> critique.

Two structural decisions worth stating up front.

1. THE NODE LOGIC IS PLAIN FUNCTIONS, NOT LANGGRAPH CALLBACKS
   Each node is a module-level function over a plain dict. `build_graph` wires them
   into a StateGraph, but nothing in the reasoning depends on LangGraph being
   importable. That keeps the interesting behaviour - what gets tagged, when the gate
   refuses, what happens when research is still running - testable without a graph
   runtime, a checkpointer, or a workspace. LangGraph is an execution detail and is
   imported lazily.

2. RESEARCH NEVER BLOCKS A TURN
   When the plan calls for deep external research, `act` submits the task, records
   the id in state, and returns. The turn completes using whatever internal evidence
   exists, telling the user research is running. A worker polls and injects the
   result via `graph.aupdate_state`, and the next turn resumes with it present -
   the pattern taken from the banking accelerator (see _ref_banking_async_resume.py).
   Nothing waits on a 300-second p50 inside a request.

The class subclasses the hardened `SimpleResponsesAgent` so it inherits the
trace/feedback correlation contract that era/tests/test_*.py already validate. That
base class was not thread-safe upstream; per-request state now lives in ContextVars,
which is what makes it usable behind a concurrent serving endpoint at all.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from era.agent import prompts
from era.agent.provenance import Evidence, ProvenanceReport, check
from era.tools.redaction import PolicyError, Sensitivity

logger = logging.getLogger("era.supervisor")

LLM_ENDPOINT_ENV = "ERA_LLM_ENDPOINT"
DEFAULT_LLM_ENDPOINT = "databricks-claude-sonnet-4-5"

# Stages, used by the router so a resumed thread re-enters at the right place.
STAGE_PLAN = "plan"
STAGE_ACT = "act"
STAGE_SYNTHESIZE = "synthesize"
STAGE_CRITIQUE = "critique"
STAGE_DONE = "done"

MAX_CRITIQUE_PASSES = 1


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def new_state(question: str, *, sensitivity: str = "public") -> dict[str, Any]:
    return {
        "question": question,
        "sensitivity": sensitivity,
        "stage": STAGE_PLAN,
        "plan": {},
        "internal": [],          # list[InternalResult-like dicts]
        "external": [],          # list of {url, title, retrieved_at}
        "notices": [],           # user-visible operational notes (refusals, pending work)
        "research_task_id": None,
        "research_result": None,
        "draft": "",
        "answer": "",
        "critique_passes": 0,
        "report": None,
    }


def build_evidence(state: dict[str, Any]) -> Evidence:
    """Collect everything the tools actually returned, for provenance validation."""
    evidence = Evidence()
    for item in state.get("internal") or []:
        for lineage in item.get("lineage") or ():
            evidence.add_internal(lineage)
    for item in state.get("external") or []:
        if item.get("url"):
            evidence.add_external(item["url"])
    result = state.get("research_result") or {}
    for citation in result.get("citations") or ():
        if citation.get("url"):
            evidence.add_external(citation["url"])
    return evidence


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def plan_node(state: dict[str, Any], *, llm: Callable[[str, str], str]) -> dict[str, Any]:
    """
    Decide which tools to use. Never answers the question.

    The plan is advisory - `act` still applies its own guards - but it is what keeps
    the agent from reaching for slow external research on a question the filings
    already answer.
    """
    raw = llm(prompts.PLANNER_PROMPT, state["question"])
    lowered = raw.lower()
    plan = {
        "internal_documents": "internal_documents" in lowered,
        "internal_data": "internal_data" in lowered,
        "web_search": "web_search" in lowered,
        "web_research": "web_research" in lowered,
        "rationale": raw.strip(),
    }
    # A plan that selects nothing is a planning failure, not a decision to answer
    # from memory. Fall back to internal sources, which are always permissible.
    if not any(plan[k] for k in ("internal_documents", "internal_data", "web_search", "web_research")):
        plan["internal_documents"] = True
        plan["internal_data"] = True
    return {"plan": plan, "stage": STAGE_ACT}


def act_node(
    state: dict[str, Any],
    *,
    tools: "ToolBundle",
) -> dict[str, Any]:
    """
    Run the planned tools.

    Every failure mode here degrades rather than aborts: a refused web call, a Genie
    timeout or a KA with no citations all leave the turn able to answer from whatever
    else succeeded. What must never happen is silently proceeding as though a tool
    had returned nothing to say.
    """
    plan = state.get("plan") or {}
    internal = list(state.get("internal") or [])
    external = list(state.get("external") or [])
    notices = list(state.get("notices") or [])
    research_task_id = state.get("research_task_id")
    sensitivity = Sensitivity(state.get("sensitivity", "public"))

    if plan.get("internal_documents") and tools.ask_documents:
        try:
            result = tools.ask_documents(state["question"])
            internal.append(result)
            if not result.get("lineage"):
                notices.append(
                    "The document assistant answered without citations, so those points "
                    "are marked inferred rather than verified."
                )
        except Exception as exc:
            logger.warning("document tool failed: %s", exc)
            notices.append(f"Internal document search failed: {exc}")

    if plan.get("internal_data") and tools.query_data:
        try:
            internal.append(tools.query_data(state["question"]))
        except Exception as exc:
            logger.warning("data tool failed: %s", exc)
            notices.append(f"Internal data query failed: {exc}")

    if plan.get("web_search") and tools.search:
        try:
            external.extend(tools.search(state["question"], sensitivity))
        except PolicyError as exc:
            # Governance refusal, not a technical error. The user is told plainly;
            # the agent does not retry against another endpoint.
            notices.append(f"External search was blocked by policy: {exc}")
        except Exception as exc:
            logger.warning("web search failed: %s", exc)
            notices.append(f"External search failed: {exc}")

    # Submit deep research only once per thread, and only if nothing is in flight.
    if plan.get("web_research") and tools.submit_research and not research_task_id and not state.get("research_result"):
        try:
            research_task_id = tools.submit_research(state["question"], sensitivity)
            notices.append(
                "Deep external research is running in the background; ask again shortly "
                "for the fuller answer."
            )
        except PolicyError as exc:
            notices.append(f"External research was blocked by policy: {exc}")
        except Exception as exc:
            logger.warning("research submit failed: %s", exc)
            notices.append(f"External research could not be started: {exc}")

    return {
        "internal": internal,
        "external": external,
        "notices": notices,
        "research_task_id": research_task_id,
        "stage": STAGE_SYNTHESIZE,
    }


def _format_tool_context(state: dict[str, Any]) -> str:
    """Render tool results for the synthesis prompt, lineage and URLs made explicit."""
    lines: list[str] = []

    for item in state.get("internal") or []:
        lineage = ", ".join(item.get("lineage") or ()) or "NO LINEAGE - claims must be [INF]"
        lines.append(f"[INTERNAL {item.get('source', '?')}] lineage: {lineage}\n{item.get('answer', '')}")
        if item.get("sql"):
            lines.append(f"  SQL: {item['sql']}")

    externals = list(state.get("external") or [])
    result = state.get("research_result") or {}
    for citation in result.get("citations") or ():
        externals.append(citation)

    for n, item in enumerate(externals, start=1):
        lines.append(
            f"[EXTERNAL {n}] {item.get('title', '')} - {item.get('url', '')} "
            f"(retrieved {item.get('retrieved_at', '')})\n{item.get('description') or item.get('markdown') or ''}"
        )

    if result.get("answer_md"):
        lines.append(f"[EXTERNAL RESEARCH]\n{result['answer_md']}")

    if state.get("notices"):
        lines.append("[OPERATIONAL NOTES - tell the user about these]\n" + "\n".join(state["notices"]))

    return "\n\n".join(lines) if lines else "(no tool results)"


def synthesize_node(state: dict[str, Any], *, llm: Callable[[str, str], str]) -> dict[str, Any]:
    """Write the answer, then validate its provenance before anyone sees it."""
    user_block = f"QUESTION\n{state['question']}\n\nTOOL RESULTS\n{_format_tool_context(state)}"
    draft = llm(prompts.SYNTHESIS_PROMPT, user_block)

    report = check(draft, build_evidence(state), require_full_coverage=True)
    return {"draft": draft, "report": report, "stage": STAGE_CRITIQUE}


def critique_node(state: dict[str, Any], *, llm: Callable[[str, str], str]) -> dict[str, Any]:
    """
    Repair a draft that failed provenance validation.

    Bounded to MAX_CRITIQUE_PASSES: if the model cannot produce a well-sourced answer
    in one correction, looping will not help, and the honest outcome is to ship the
    answer with its violations attached rather than to keep spending tokens.
    """
    report: ProvenanceReport | None = state.get("report")
    passes = state.get("critique_passes", 0)

    if report is None or report.ok or passes >= MAX_CRITIQUE_PASSES:
        return {"answer": state.get("draft", ""), "stage": STAGE_DONE}

    violations = "\n".join(f"- {v}" for v in report.violations)
    user_block = (
        f"QUESTION\n{state['question']}\n\n"
        f"TOOL RESULTS\n{_format_tool_context(state)}\n\n"
        f"DRAFT\n{state.get('draft', '')}\n\n"
        f"PROVENANCE VIOLATIONS\n{violations}"
    )
    corrected = llm(prompts.CRITIQUE_PROMPT, user_block)
    recheck = check(corrected, build_evidence(state), require_full_coverage=True)

    return {
        "draft": corrected,
        "answer": corrected,
        "report": recheck,
        "critique_passes": passes + 1,
        "stage": STAGE_DONE,
    }


def route_by_stage(state: dict[str, Any]) -> str:
    """
    Entry router. A resumed thread re-enters where it left off.

    Specifically: when a worker has injected `research_result` into a checkpointed
    thread, the graph must resume at synthesis rather than re-planning and
    re-submitting the research it just finished.
    """
    if state.get("research_result") and state.get("stage") != STAGE_DONE:
        return STAGE_SYNTHESIZE
    stage = state.get("stage") or STAGE_PLAN
    return stage if stage in (STAGE_PLAN, STAGE_ACT, STAGE_SYNTHESIZE, STAGE_CRITIQUE) else STAGE_PLAN


# ---------------------------------------------------------------------------
# Tool bundle
# ---------------------------------------------------------------------------


class ToolBundle:
    """
    The tools `act` may call, injected rather than imported.

    Every callable is optional so a deployment without a warehouse, without a Genie
    space, or without a You.com contract still runs - it just has less evidence.
    """

    def __init__(
        self,
        ask_documents: Callable[[str], dict] | None = None,
        query_data: Callable[[str], dict] | None = None,
        search: Callable[[str, Sensitivity], list[dict]] | None = None,
        submit_research: Callable[[str, Sensitivity], str] | None = None,
    ):
        self.ask_documents = ask_documents
        self.query_data = query_data
        self.search = search
        self.submit_research = submit_research


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph(*, llm: Callable[[str, str], str], tools: ToolBundle, checkpointer=None):
    """
    Wire the nodes into a LangGraph StateGraph.

    LangGraph is imported here rather than at module scope so the node logic above
    stays importable - and therefore testable - in environments that do not have it.
    """
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(dict)
    builder.add_node(STAGE_PLAN, lambda s: plan_node(s, llm=llm))
    builder.add_node(STAGE_ACT, lambda s: act_node(s, tools=tools))
    builder.add_node(STAGE_SYNTHESIZE, lambda s: synthesize_node(s, llm=llm))
    builder.add_node(STAGE_CRITIQUE, lambda s: critique_node(s, llm=llm))

    builder.add_conditional_edges(
        START,
        route_by_stage,
        {
            STAGE_PLAN: STAGE_PLAN,
            STAGE_ACT: STAGE_ACT,
            STAGE_SYNTHESIZE: STAGE_SYNTHESIZE,
            STAGE_CRITIQUE: STAGE_CRITIQUE,
        },
    )
    builder.add_edge(STAGE_PLAN, STAGE_ACT)
    builder.add_edge(STAGE_ACT, STAGE_SYNTHESIZE)
    builder.add_edge(STAGE_SYNTHESIZE, STAGE_CRITIQUE)
    builder.add_edge(STAGE_CRITIQUE, END)

    return builder.compile(checkpointer=checkpointer)


def run_turn(
    state: dict[str, Any],
    *,
    llm: Callable[[str, str], str],
    tools: ToolBundle,
) -> dict[str, Any]:
    """
    Execute one turn without LangGraph.

    Used by tests and by anything that wants the pipeline without a graph runtime.
    The sequence mirrors build_graph exactly; if one changes, so must the other -
    which is why a test asserts they produce the same answer.
    """
    entry = route_by_stage(state)
    if entry == STAGE_PLAN:
        state.update(plan_node(state, llm=llm))
    if entry in (STAGE_PLAN, STAGE_ACT):
        state.update(act_node(state, tools=tools))
    state.update(synthesize_node(state, llm=llm))
    state.update(critique_node(state, llm=llm))
    return state


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


def llm_endpoint() -> str:
    return os.environ.get(LLM_ENDPOINT_ENV) or DEFAULT_LLM_ENDPOINT


class EraSupervisor:
    """
    ResponsesAgent wrapper around the graph.

    Subclasses the grafted SimpleResponsesAgent lazily (its import pulls in mlflow's
    serving stack) so this module stays importable for unit tests.
    """

    def __init__(self, model: str | None = None, tools: ToolBundle | None = None):
        self.model = model or llm_endpoint()
        self.tools = tools or ToolBundle()
        self._openai = None

    def _client(self):
        """Cached OpenAI-compatible client for the Foundation Model endpoint."""
        if self._openai is None:
            from databricks.sdk import WorkspaceClient

            self._openai = WorkspaceClient().serving_endpoints.get_open_ai_client()
        return self._openai

    def _llm(self, system: str, user: str) -> str:
        """
        One system+user completion against the configured model endpoint.

        USES CHAT COMPLETIONS, NOT THE RESPONSES API, AND THAT IS DELIBERATE.
        A Foundation Model endpoint rejects Responses-API calls outright:
        "Responses API passthrough is not supported for model
        databricks-claude-sonnet-4-5". The Responses API is for *agent* endpoints
        (the MAS speaks it); chat completions is what a raw FM endpoint speaks.

        SimpleResponsesAgent is therefore the wrong tool for this call even though
        ERA still uses it elsewhere - it is a client for an endpoint that already
        speaks Responses, which is what the app talks to, not what the planner and
        synthesiser talk to. The X-Client-Request-ID header is kept because that is
        the genuinely valuable half of its contract: it lets a trace be correlated
        back to the request that produced it.
        """
        import uuid

        response = self._client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_headers={"X-Client-Request-ID": f"era-{uuid.uuid4().hex[:8]}"},
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        return getattr(choices[0].message, "content", "") or ""

    def answer(self, question: str, *, sensitivity: str = "public") -> dict[str, Any]:
        state = new_state(question, sensitivity=sensitivity)
        return run_turn(state, llm=self._llm, tools=self.tools)


def _first_text(response: Any) -> str:
    """Pull assistant text out of a Responses API payload without assuming one shape."""
    for attr in ("output_text", "content"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value:
            return value
    output = getattr(response, "output", None) or []
    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else None) or []
        for part in content:
            text = getattr(part, "text", None) or (part.get("text") if isinstance(part, dict) else None)
            if text:
                parts.append(text)
    return "\n".join(parts)
