"""
Tests for the MAS tool-swap logic (ERA addition, not grafted).

`plan_agents` is deliberately a pure function over the supervisor's agent list, so
the risky part of Milestone B - "which tools end up attached to the supervisor" -
is verifiable without a workspace, an API key, or a live MAS.

The failure this guards against is not a crash. It is a supervisor that still has an
ungoverned web-search tool attached and therefore quietly bypasses conf/ at the
moment someone asks it a question.
"""

from __future__ import annotations

import pytest

from era.connections.register_mas_tools import (
    FALLBACK_FUNCTIONS,
    GOVERNED_TOOLS,
    agent_function_name,
    plan_agents,
)

CATALOG, SCHEMA = "alexxx", "era_research"


def _fn_agent(name: str, func: str) -> dict:
    return {
        "name": name,
        "description": "x",
        "agent_type": "function",
        "unity_catalog_function": {"uc_path": {"catalog": CATALOG, "schema": SCHEMA, "name": func}},
    }


@pytest.fixture
def baseline() -> list[dict]:
    """A supervisor as Milestone A leaves it: KA + Genie + chart + the 03b tools."""
    return [
        {"name": "Financial_Documents_Assistant", "agent_type": "ka",
         "serving_endpoint": {"name": "ka-endpoint"}},
        {"name": "Ticker_Data_Explorer", "agent_type": "genie",
         "genie_space": {"id": "space-123"}},
        _fn_agent("Chart_Generator", "generate_vega_lite_spec"),
        _fn_agent("Web_Search", "you_web_search"),
        _fn_agent("Web_Content_Extractor", "you_content_extract"),
        _fn_agent("Web_Researcher", "you_research"),
    ]


def _funcs(agents: list[dict]) -> set[str]:
    return {f for f in (agent_function_name(a) for a in agents) if f}


# ---------------------------------------------------------------------------

def test_replace_detaches_every_ungoverned_web_tool(baseline):
    """The whole point: no ungoverned egress path is left attached."""
    planned = plan_agents(baseline, CATALOG, SCHEMA, "replace")
    leftover = _funcs(planned) & FALLBACK_FUNCTIONS
    assert not leftover, f"ungoverned tools still attached to the supervisor: {leftover}"
    assert _funcs(planned) >= set(GOVERNED_TOOLS)


def test_replace_preserves_the_internal_bricks(baseline):
    """
    KA, Genie and the chart function are how the agent reaches governed internal
    data. Dropping one would silently turn a blended answer into a web-only answer.
    """
    planned = plan_agents(baseline, CATALOG, SCHEMA, "replace")
    names = {a["name"] for a in planned}
    assert {"Financial_Documents_Assistant", "Ticker_Data_Explorer", "Chart_Generator"} <= names

    kinds = {a.get("agent_type") for a in planned}
    assert "ka" in kinds and "genie" in kinds


def test_replace_is_idempotent(baseline):
    """Re-running must not duplicate tools or drift the list."""
    once = plan_agents(baseline, CATALOG, SCHEMA, "replace")
    twice = plan_agents(once, CATALOG, SCHEMA, "replace")
    assert once == twice

    names = [a["name"] for a in twice]
    assert len(names) == len(set(names)), f"duplicate agent names after re-run: {names}"


def test_add_mode_keeps_both_but_disambiguates_names(baseline):
    """
    A/B mode deliberately keeps the ungoverned tools, so the names must not collide -
    two agents called Web_Search is ambiguous to the supervisor and to whoever reads
    the trace afterwards.
    """
    planned = plan_agents(baseline, CATALOG, SCHEMA, "add")
    assert _funcs(planned) >= FALLBACK_FUNCTIONS | set(GOVERNED_TOOLS)

    names = [a["name"] for a in planned]
    assert len(names) == len(set(names)), f"colliding agent names: {names}"
    assert any(n.endswith("_Governed") for n in names)


def test_revert_restores_the_milestone_a_baseline(baseline):
    """Rule 3: the previous milestone must stay runnable."""
    replaced = plan_agents(baseline, CATALOG, SCHEMA, "replace")
    reverted = plan_agents(replaced, CATALOG, SCHEMA, "revert")

    assert not _funcs(reverted) & set(GOVERNED_TOOLS)
    # Reverting from a replaced state cannot resurrect tools that were detached, so
    # 03b must be re-run - but nothing else may have been lost along the way.
    assert {a["name"] for a in reverted} >= {
        "Financial_Documents_Assistant", "Ticker_Data_Explorer", "Chart_Generator"
    }


def test_revert_from_add_mode_leaves_the_fallback_intact(baseline):
    """add -> revert is the lossless round trip, and must return exactly the baseline."""
    added = plan_agents(baseline, CATALOG, SCHEMA, "add")
    reverted = plan_agents(added, CATALOG, SCHEMA, "revert")
    assert reverted == baseline


def test_governed_tools_point_at_the_configured_catalog_and_schema(baseline):
    """A tool registered against the wrong schema fails only at query time."""
    planned = plan_agents(baseline, CATALOG, SCHEMA, "replace")
    for agent in planned:
        if agent_function_name(agent) in GOVERNED_TOOLS:
            path = agent["unity_catalog_function"]["uc_path"]
            assert path["catalog"] == CATALOG and path["schema"] == SCHEMA


def test_never_produces_an_empty_agent_list():
    """A supervisor with no agents is worse than no change at all."""
    assert plan_agents([], CATALOG, SCHEMA, "replace")


def test_tool_descriptions_tell_the_model_to_cite():
    """
    Provenance starts at tool selection. If the tool description never mentions
    citing, the supervisor has no instruction-level reason to carry URLs through to
    the answer, and Milestone C's provenance check inherits an unwinnable problem.
    """
    search = GOVERNED_TOOLS["era_you_search"]["description"].lower()
    assert "cite" in search
    assert "news" in search, "the model must learn news comes from this same tool"
