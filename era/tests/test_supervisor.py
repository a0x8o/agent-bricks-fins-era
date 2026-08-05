"""
Tests for the supervisor pipeline.

Runs without LangGraph, without a workspace and without an LLM: the nodes are plain
functions over a dict, and both the model and the tools are injected. What is being
tested is the behaviour that governance depends on - that a policy refusal degrades
instead of aborting, that research never blocks a turn, and that a resumed thread
does not re-submit work it already did.
"""

from __future__ import annotations

import pytest

from era.agent import supervisor as sup
from era.agent.provenance import check
from era.tools.redaction import PolicyError, Sensitivity

QUESTION = "How does NVIDIA's latest guidance compare to what the market expects?"

GOOD_DRAFT = """\
Data centre revenue was $47.5B [IV:alexxx.era_research.ticker_data].
Coverage described guidance as conservative [EC:1].
The two together suggest supply is the constraint [INF].

## Sources
[1] Nvidia beats - https://reuters.com/a (retrieved 2026-08-04T09:15:00Z)
"""


def make_llm(plan="internal_documents internal_data web_search", answer=GOOD_DRAFT):
    """Fake LLM: returns the plan for the planner prompt, the answer for the rest."""
    calls: list[str] = []

    def llm(system: str, user: str) -> str:
        calls.append(system[:40])
        if system.startswith(sup.prompts.PLANNER_PROMPT[:40]):
            return plan
        return answer

    llm.calls = calls  # type: ignore[attr-defined]
    return llm


def internal_doc(lineage=("doc-1",)):
    return {"source": "knowledge_assistant", "answer": "The filing cites supply.", "lineage": lineage}


def genie_row():
    return {
        "source": "genie",
        "answer": "Revenue was 47.5B.",
        "lineage": ("alexxx.era_research.ticker_data",),
        "sql": "SELECT revenue FROM alexxx.era_research.ticker_data",
    }


def web_hit():
    return [{
        "url": "https://reuters.com/a", "title": "Nvidia beats",
        "description": "d", "retrieved_at": "2026-08-04T09:15:00Z",
    }]


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_planner_selects_the_tools_it_names():
    state = sup.new_state(QUESTION)
    state.update(sup.plan_node(state, llm=make_llm(plan="use internal_data and web_search")))

    assert state["plan"]["internal_data"]
    assert state["plan"]["web_search"]
    assert not state["plan"]["web_research"]


def test_a_plan_selecting_nothing_falls_back_to_internal_sources():
    """
    An empty plan is a planning failure. Falling back to internal sources is always
    permissible; falling back to "answer from memory" is not.
    """
    state = sup.new_state(QUESTION)
    state.update(sup.plan_node(state, llm=make_llm(plan="I am not sure.")))

    assert state["plan"]["internal_documents"]
    assert state["plan"]["internal_data"]
    assert not state["plan"]["web_search"]


# ---------------------------------------------------------------------------
# Acting - degradation
# ---------------------------------------------------------------------------

def test_policy_refusal_degrades_to_internal_only_with_a_notice():
    """
    The governance path. A blocked web call must not fail the turn, must not be
    retried elsewhere, and must be visible to the user.
    """
    def refusing_search(q, sensitivity):
        raise PolicyError("refusing confidential query to a non-ZDR endpoint")

    tools = sup.ToolBundle(
        ask_documents=lambda q: internal_doc(),
        search=refusing_search,
    )
    state = sup.new_state(QUESTION)
    state["plan"] = {"internal_documents": True, "web_search": True}
    state.update(sup.act_node(state, tools=tools))

    assert state["internal"], "internal evidence should still have been gathered"
    assert state["external"] == []
    assert any("blocked by policy" in n for n in state["notices"])


def test_a_failing_internal_tool_does_not_abort_the_turn():
    def broken(q):
        raise RuntimeError("genie exploded")

    tools = sup.ToolBundle(ask_documents=lambda q: internal_doc(), query_data=broken)
    state = sup.new_state(QUESTION)
    state["plan"] = {"internal_documents": True, "internal_data": True}
    state.update(sup.act_node(state, tools=tools))

    assert len(state["internal"]) == 1
    assert any("genie exploded" in n for n in state["notices"])


def test_missing_ka_citations_produce_a_visible_notice():
    """Honest degradation: the user learns why those points are only inferred."""
    tools = sup.ToolBundle(ask_documents=lambda q: internal_doc(lineage=()))
    state = sup.new_state(QUESTION)
    state["plan"] = {"internal_documents": True}
    state.update(sup.act_node(state, tools=tools))

    assert any("without citations" in n for n in state["notices"])


# ---------------------------------------------------------------------------
# Research never blocks
# ---------------------------------------------------------------------------

def test_research_is_submitted_and_the_turn_continues():
    submitted: list[str] = []

    def submit(q, sensitivity):
        submitted.append(q)
        return "task-123"

    tools = sup.ToolBundle(ask_documents=lambda q: internal_doc(), submit_research=submit)
    state = sup.new_state(QUESTION)
    state["plan"] = {"internal_documents": True, "web_research": True}
    state.update(sup.act_node(state, tools=tools))

    assert submitted, "research was never submitted"
    assert state["research_task_id"] == "task-123"
    assert state["stage"] == sup.STAGE_SYNTHESIZE, "the turn must proceed, not wait"
    assert any("background" in n for n in state["notices"])


def test_research_is_not_resubmitted_while_one_is_in_flight():
    """Re-entering act with a task already running must not start a second one."""
    calls: list[str] = []
    tools = sup.ToolBundle(submit_research=lambda q, s: calls.append(q) or "t2")

    state = sup.new_state(QUESTION)
    state["plan"] = {"web_research": True}
    state["research_task_id"] = "task-already-running"
    state.update(sup.act_node(state, tools=tools))

    assert calls == []
    assert state["research_task_id"] == "task-already-running"


def test_a_thread_with_an_injected_result_resumes_at_synthesis():
    """
    The resume path. A worker has written research_result into the checkpoint; the
    graph must not re-plan and re-submit the research it just paid for.
    """
    state = sup.new_state(QUESTION)
    state["stage"] = sup.STAGE_PLAN
    state["research_result"] = {"answer_md": "findings", "citations": []}

    assert sup.route_by_stage(state) == sup.STAGE_SYNTHESIZE


def test_research_citations_become_provenance_evidence():
    state = sup.new_state(QUESTION)
    state["research_result"] = {
        "answer_md": "x",
        "citations": [{"url": "https://ft.com/deep", "title": "Deep", "retrieved_at": "2026-08-04T09:00:00Z"}],
    }
    assert "https://ft.com/deep" in sup.build_evidence(state).external_urls


# ---------------------------------------------------------------------------
# Synthesis and critique
# ---------------------------------------------------------------------------

def test_a_well_sourced_draft_passes_and_skips_correction():
    state = sup.new_state(QUESTION)
    state["internal"] = [genie_row()]
    state["external"] = web_hit()

    llm = make_llm()
    state.update(sup.synthesize_node(state, llm=llm))
    assert state["report"].ok

    state.update(sup.critique_node(state, llm=llm))
    assert state["answer"] == GOOD_DRAFT
    assert state["critique_passes"] == 0, "a passing draft must not be rewritten"


def test_a_fabricated_citation_triggers_correction():
    state = sup.new_state(QUESTION)
    state["internal"] = [genie_row()]
    state["external"] = web_hit()

    bad = GOOD_DRAFT.replace("https://reuters.com/a", "https://invented.example/x")
    llm = make_llm(answer=bad)
    state.update(sup.synthesize_node(state, llm=llm))

    assert not state["report"].ok

    # The critique pass returns a corrected draft.
    state.update(sup.critique_node(state, llm=make_llm(answer=GOOD_DRAFT)))
    assert state["critique_passes"] == 1
    assert state["report"].ok


def test_critique_is_bounded():
    """If one correction cannot fix it, looping will not - ship it with violations."""
    state = sup.new_state(QUESTION)
    state["internal"] = [genie_row()]
    state["external"] = web_hit()
    state["critique_passes"] = sup.MAX_CRITIQUE_PASSES

    bad = GOOD_DRAFT.replace("https://reuters.com/a", "https://invented.example/x")
    state.update(sup.synthesize_node(state, llm=make_llm(answer=bad)))
    state.update(sup.critique_node(state, llm=make_llm(answer=bad)))

    assert state["stage"] == sup.STAGE_DONE
    assert state["answer"], "an answer must still be produced"


def test_tool_context_marks_results_that_cannot_support_verified_claims():
    state = sup.new_state(QUESTION)
    state["internal"] = [internal_doc(lineage=())]
    rendered = sup._format_tool_context(state)
    assert "NO LINEAGE" in rendered and "[INF]" in rendered


def test_operational_notices_reach_the_synthesis_prompt():
    """A blocked search the user is never told about is a silent failure."""
    state = sup.new_state(QUESTION)
    state["notices"] = ["External search was blocked by policy: nope"]
    assert "blocked by policy" in sup._format_tool_context(state)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def test_full_turn_produces_a_validated_answer():
    tools = sup.ToolBundle(
        ask_documents=lambda q: internal_doc(),
        query_data=lambda q: genie_row(),
        search=lambda q, s: web_hit(),
    )
    state = sup.run_turn(sup.new_state(QUESTION), llm=make_llm(), tools=tools)

    assert state["stage"] == sup.STAGE_DONE
    assert state["answer"]
    assert state["report"].ok
    assert state["report"].citation_coverage == 1.0

    # And the answer really does validate against what the tools returned.
    assert check(state["answer"], sup.build_evidence(state)).ok


def test_full_turn_survives_every_external_path_being_blocked():
    def refuse(*a, **k):
        raise PolicyError("blocked")

    tools = sup.ToolBundle(
        ask_documents=lambda q: internal_doc(),
        query_data=lambda q: genie_row(),
        search=refuse,
        submit_research=refuse,
    )
    internal_only = """\
Revenue was $47.5B [IV:alexxx.era_research.ticker_data].
External corroboration was unavailable [INF].
"""
    state = sup.run_turn(
        sup.new_state(QUESTION),
        llm=make_llm(plan="internal_data web_search web_research", answer=internal_only),
        tools=tools,
    )

    assert state["answer"]
    assert state["report"].ok, state["report"].violations
    assert any("blocked" in n for n in state["notices"])


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------

def test_graph_matches_the_inline_pipeline():
    """
    build_graph and run_turn describe the same sequence. If they drift, behaviour
    differs between the deployed agent and everything tested here.
    """
    langgraph = pytest.importorskip("langgraph", reason="langgraph not installed locally")
    assert langgraph

    tools = sup.ToolBundle(
        ask_documents=lambda q: internal_doc(),
        query_data=lambda q: genie_row(),
        search=lambda q, s: web_hit(),
    )
    graph = sup.build_graph(llm=make_llm(), tools=tools)
    out = graph.invoke(sup.new_state(QUESTION))
    inline = sup.run_turn(sup.new_state(QUESTION), llm=make_llm(), tools=tools)

    assert out["answer"] == inline["answer"]
