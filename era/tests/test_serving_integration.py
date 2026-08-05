# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_serving_integration.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Pytest integration tests for the serving endpoint.
Use the serving_env fixture from conftest.py; tests are skipped if env is not set.
Run only when SERVING_ENDPOINT and MLFLOW_EXPERIMENT_ID are set; in CI use: pytest -m "not integration".
"""

import pytest
from mlflow.types.responses import ResponsesAgentRequest

from era.tools.serving_utils import get_agent


@pytest.mark.integration
def test_agent_stream_yields_events(serving_env):
    """Query the endpoint and assert we get at least one streamed event."""
    endpoint_name, _ = serving_env
    agent = get_agent(endpoint_name)
    request = ResponsesAgentRequest(input=[{"role": "user", "content": "Reply with the number 42 only."}])
    events = list(agent.predict_stream(request))
    assert len(events) >= 1, "Expected at least one event from predict_stream"


@pytest.mark.integration
def test_client_request_id_after_stream(serving_env):
    """After streaming, get_last_client_request_id() returns a non-empty string."""
    endpoint_name, _ = serving_env
    agent = get_agent(endpoint_name)
    request = ResponsesAgentRequest(input=[{"role": "user", "content": "Say hello."}])
    for _ in agent.predict_stream(request):
        pass
    client_request_id = agent.get_last_client_request_id()
    assert client_request_id is not None, "Expected a client_request_id"
    assert isinstance(client_request_id, str) and len(client_request_id) > 0
