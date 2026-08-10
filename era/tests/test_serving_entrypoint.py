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


# ---------------------------------------------------------------------------
# Streaming contract
#
# The app talks to the endpoint through the Vercel AI SDK, which always asks for a
# stream. A ResponsesAgent that only implements `predict` therefore fails every
# request with NotImplementedError from the serving container - these tests exist so
# that regression is caught here rather than in the deployed app.
# ---------------------------------------------------------------------------

def _events(agent, question="what are the supply risks"):
    req = ResponsesAgentRequest(input=[{"role": "user", "content": question}])
    return [
        e.model_dump(exclude_none=True) if hasattr(e, "model_dump") else dict(e)
        for e in agent.predict_stream(req)
    ]


def test_streaming_emits_the_answer_and_a_completed_item():
    events = _events(_agent())
    assert [e["type"] for e in events] == [
        "response.output_text.delta",
        "response.output_item.done",
    ]

    delta, done = events
    assert "supply concentration" in delta["delta"]
    assert done["item"]["content"][0]["text"] == delta["delta"]
    # The app's provider reads deltas and completed items as one item when the ids
    # match, and as two separate answers when they do not.
    assert delta["item_id"] == done["item"]["id"]


def test_streamed_item_carries_the_fields_the_app_parses():
    """
    The client validates each chunk; a chunk that fails validation is dropped, so a
    missing `output_index` or `annotations` shows up as an empty reply rather than an
    error. Both are easy to lose and neither is exercised by `predict`.
    """
    done = _events(_agent())[-1]
    assert done["output_index"] == 0
    item = done["item"]
    assert item["type"] == "message" and item["role"] == "assistant"
    assert item["content"][0]["annotations"] == []


def test_streaming_reports_provenance_the_same_way_predict_does():
    """The verdict must not be lost just because the caller asked for a stream."""
    done = _events(_agent())[-1]
    assert done["custom_outputs"]["provenance_ok"] is True
    assert done["custom_outputs"]["citation_coverage"] == 1.0


def test_streaming_handles_a_request_with_no_question():
    req = ResponsesAgentRequest(input=[{"role": "assistant", "content": "orphaned"}])
    events = [e.model_dump(exclude_none=True) for e in _agent().predict_stream(req)]
    assert "did not receive a question" in events[-1]["item"]["content"][0]["text"]


def test_the_mlflow_reducer_sees_exactly_one_answer():
    """
    Deltas plus a completed item is the shape MLflow's trace reducer expects; if the
    answer were emitted only as deltas the trace would record an empty output, and if
    it were emitted as two items every consumer would show it twice.
    """
    from mlflow.pyfunc import ResponsesAgent

    reduced = ResponsesAgent.responses_agent_output_reducer(_events(_agent()))
    assert len(reduced["output"]) == 1
    assert "supply concentration" in reduced["output"][0]["content"][0]["text"]
