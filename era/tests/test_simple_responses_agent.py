# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_simple_responses_agent.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Unit tests for SimpleResponsesAgent (no live endpoint).
Tests client_request_id generation, trace_id capture, predict/predict_stream,
and error handling with mocked WorkspaceClient.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_workspace_client():
    """Patch WorkspaceClient so SimpleResponsesAgent can be instantiated without credentials."""
    with patch("era.tools.serving_utils.WorkspaceClient") as mock_ws:
        mock_client = MagicMock()
        mock_ws.return_value.serving_endpoints.get_open_ai_client.return_value = mock_client
        yield mock_client


@pytest.fixture
def agent(mock_workspace_client):
    from era.tools.serving_utils import SimpleResponsesAgent

    return SimpleResponsesAgent(model="test-endpoint")


class TestInit:
    def test_init_sets_model(self, agent):
        assert agent.model == "test-endpoint"

    def test_init_state_is_none(self, agent):
        assert agent.current_client_request_id is None
        assert agent.current_trace_id is None

    def test_init_failure_raises_runtime_error(self):
        with patch("era.tools.serving_utils.WorkspaceClient", side_effect=Exception("bad creds")):
            from era.tools.serving_utils import SimpleResponsesAgent

            with pytest.raises(RuntimeError, match="Failed to initialize WorkspaceClient"):
                SimpleResponsesAgent(model="test-endpoint")


class TestPredictStream:
    def test_generates_client_request_id(self, agent, mock_workspace_client):
        mock_workspace_client.responses.create.return_value = iter([])
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        list(agent.predict_stream(request))

        crid = agent.get_last_client_request_id()
        assert crid is not None
        assert crid.startswith("req-")
        assert len(crid) == 12  # "req-" + 8 hex chars

    def test_passes_client_request_id_header(self, agent, mock_workspace_client):
        mock_workspace_client.responses.create.return_value = iter([])
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        list(agent.predict_stream(request))

        call_kwargs = mock_workspace_client.responses.create.call_args[1]
        assert "extra_headers" in call_kwargs
        header_val = call_kwargs["extra_headers"]["X-Client-Request-ID"]
        assert header_val == agent.get_last_client_request_id()

    def test_captures_trace_id_from_event(self, agent, mock_workspace_client):
        event = MagicMock()
        event.type = "response.output_text.delta"
        event.trace_id = "trace-abc-123"
        event.delta = "hello"
        event.item = MagicMock()
        event.item.type = "message"

        mock_workspace_client.responses.create.return_value = iter([event])
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        list(agent.predict_stream(request))
        assert agent.get_last_trace_id() == "trace-abc-123"

    def test_filters_function_call_output_events(self, agent, mock_workspace_client):
        normal_event = MagicMock()
        normal_event.type = "response.output_text.delta"
        normal_event.trace_id = None
        normal_event.response_metadata = None
        normal_event.item = MagicMock()
        normal_event.item.type = "message"

        filtered_event = MagicMock()
        filtered_event.type = "response.output_item.done"
        filtered_event.trace_id = None
        filtered_event.response_metadata = None
        filtered_event.item = MagicMock()
        filtered_event.item.type = "function_call_output"
        filtered_event.item.output = "some output"

        mock_workspace_client.responses.create.return_value = iter([normal_event, filtered_event])
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        events = list(agent.predict_stream(request))
        assert len(events) == 1  # filtered_event should be skipped

    def test_raises_on_endpoint_error(self, agent, mock_workspace_client):
        mock_workspace_client.responses.create.side_effect = Exception("endpoint down")
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        with pytest.raises(Exception, match="endpoint down"):
            list(agent.predict_stream(request))

    def test_empty_stream_returns_no_events(self, agent, mock_workspace_client):
        mock_workspace_client.responses.create.return_value = iter([])
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        events = list(agent.predict_stream(request))
        assert events == []
        assert agent.get_last_client_request_id() is not None
        assert agent.get_last_trace_id() is None


class TestPredict:
    def test_generates_client_request_id(self, agent, mock_workspace_client):
        mock_response = MagicMock()
        mock_response.trace_id = None
        mock_response.response_metadata = None
        mock_workspace_client.responses.create.return_value = mock_response
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        agent.predict(request)

        crid = agent.get_last_client_request_id()
        assert crid is not None
        assert crid.startswith("req-")

    def test_captures_trace_id_from_response(self, agent, mock_workspace_client):
        mock_response = MagicMock()
        mock_response.trace_id = "trace-sync-456"
        mock_response.response_metadata = None
        mock_workspace_client.responses.create.return_value = mock_response
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        agent.predict(request)
        assert agent.get_last_trace_id() == "trace-sync-456"

    def test_passes_stream_false(self, agent, mock_workspace_client):
        mock_response = MagicMock()
        mock_response.trace_id = None
        mock_response.response_metadata = None
        mock_workspace_client.responses.create.return_value = mock_response
        from mlflow.types.responses import ResponsesAgentRequest

        request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])

        agent.predict(request)

        call_kwargs = mock_workspace_client.responses.create.call_args[1]
        assert call_kwargs["stream"] is False


class TestLogUserFeedback:
    def test_invalid_experiment_id_returns_false(self):
        with patch.dict(os.environ, {"MLFLOW_EXPERIMENT_ID": "YOUR_EXPERIMENT_ID"}, clear=False):
            from era.tools.serving_utils import log_user_feedback

            result = log_user_feedback("req-abc", thumbs_up=True, trace_id=None)
            assert result is False

    def test_empty_experiment_id_returns_false(self):
        with patch.dict(os.environ, {"MLFLOW_EXPERIMENT_ID": ""}, clear=False):
            from era.tools.serving_utils import log_user_feedback

            result = log_user_feedback("req-abc", thumbs_up=True, trace_id=None)
            assert result is False


class TestGetAgent:
    def test_returns_agent_instance(self, mock_workspace_client):
        from era.tools.serving_utils import get_agent

        agent = get_agent("my-endpoint")
        assert agent.model == "my-endpoint"
