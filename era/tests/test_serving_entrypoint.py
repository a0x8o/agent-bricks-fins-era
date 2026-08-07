"""
Tests for the serving entrypoint.

This module is the only place the offline pipeline meets real deployment wiring, so
the things worth testing are the wiring failures: a question that cannot be found in
the request, a partially-configured deployment, and - most importantly - an audit
sink left on its in-memory default, which would make the gate look like it works
while recording nothing.
"""

from __future__ import annotations

import pytest
from mlflow.types.responses import ResponsesAgentRequest

from era.agent import serving_entrypoint as ep


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (ep.ENV_CATALOG, ep.ENV_SCHEMA, ep.ENV_LLM, ep.ENV_KA,
                 ep.ENV_GENIE, ep.ENV_WAREHOUSE, "YOU_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _agent(answer="The filings note supply concentration [INF]."):
    agent = ep.EraResponsesAgent()
    agent._supervisor._llm = lambda system, user: (
        "internal_documents" if "planning step" in system else answer
    )
    return agent


def _text(response) -> str:
    d = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    return d["output"][0]["content"][0]["text"]


def _custom(response) -> dict:
    d = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    return d.get("custom_outputs") or {}


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

def test_reads_a_plain_string_message():
    req = ResponsesAgentRequest(input=[{"role": "user", "content": "hello there friend"}])
    assert ep._last_user_message(req) == "hello there friend"


def test_reads_structured_content_parts():
    req = ResponsesAgentRequest(input=[
        {"role": "user", "content": [{"type": "input_text", "text": "what are the risks"}]}
    ])
    assert "what are the risks" in ep._last_user_message(req)


def test_takes_the_most_recent_user_turn_not_the_first():
    """A multi-turn conversation must answer the current question, not the opener."""
    req = ResponsesAgentRequest(input=[
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "an answer"},
        {"role": "user", "content": "second question"},
    ])
    assert ep._last_user_message(req) == "second question"


def test_no_user_message_is_handled_rather_than_crashing():
    req = ResponsesAgentRequest(input=[{"role": "assistant", "content": "orphaned"}])
    assert ep._last_user_message(req) == ""

    response = _agent().predict(req)
    assert "did not receive a question" in _text(response)


# ---------------------------------------------------------------------------
# Deployment wiring
# ---------------------------------------------------------------------------

def test_tools_are_gated_on_their_own_configuration(monkeypatch):
    """A partial deployment should lose tools, not fail at request time."""
    assert all(v is None for v in vars(ep.build_tools()).values())

    monkeypatch.setenv(ep.ENV_KA, "ka-endpoint")
    monkeypatch.setenv(ep.ENV_GENIE, "space-1")
    tools = ep.build_tools()
    assert tools.ask_documents is not None
    assert tools.query_data is not None
    assert tools.search is None, "search needs a warehouse and must stay off without one"


def test_missing_audit_config_is_loud_not_silent(caplog):
    """
    The in-memory default would make every egress decision vanish while the gate
    still appeared to enforce policy. That must never pass quietly.
    """
    with caplog.at_level("ERROR", logger="era.serving"):
        ep._install_audit_sink()
    assert any("will NOT be persisted" in r.message for r in caplog.records)


def test_audit_sink_is_installed_when_configured(monkeypatch):
    from era.tools.redaction import SqlWarehouseAuditSink, get_audit_sink, set_audit_sink, InMemoryAuditSink

    original = get_audit_sink()
    try:
        monkeypatch.setenv(ep.ENV_WAREHOUSE, "wh-1")
        monkeypatch.setenv(ep.ENV_CATALOG, "alexxx")
        monkeypatch.setenv(ep.ENV_SCHEMA, "era_research")
        ep._install_audit_sink()
        assert isinstance(get_audit_sink(), SqlWarehouseAuditSink)
    finally:
        set_audit_sink(original if original else InMemoryAuditSink())


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------

def test_provenance_verdict_is_returned_to_the_caller():
    """
    The app needs to know whether the answer passed validation - otherwise the
    provenance work is invisible to everyone downstream.
    """
    custom = _custom(_agent().predict(
        ResponsesAgentRequest(input=[{"role": "user", "content": "what are the supply risks"}])
    ))
    assert custom["provenance_ok"] is True
    assert custom["citation_coverage"] == 1.0
    assert custom["provenance_violations"] == []


def test_a_failing_answer_reports_its_violations():
    """An untagged claim must surface as a violation, not be quietly returned."""
    custom = _custom(_agent(answer="NVIDIA depends heavily on a single foundry.").predict(
        ResponsesAgentRequest(input=[{"role": "user", "content": "what are the supply risks"}])
    ))
    assert custom["provenance_ok"] is False
    assert custom["provenance_violations"]


def test_custom_inputs_can_carry_sensitivity_and_a_resumed_research_result():
    req = ResponsesAgentRequest(
        input=[{"role": "user", "content": "what did the deep research find"}],
        custom_inputs={
            "sensitivity": "public",
            "research_result": {"answer_md": "findings", "citations": []},
        },
    )
    assert _text(_agent().predict(req))
