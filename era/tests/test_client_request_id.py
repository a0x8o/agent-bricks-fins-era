# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_client_request_id.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Test the updated era.tools.serving_utils with client_request_id approach.
This validates that:
1. Client request IDs are generated and tagged to traces
2. Traces can be found by client_request_id
3. Feedback can be logged successfully

Requires env: SERVING_ENDPOINT, MLFLOW_EXPERIMENT_ID (optional: DATABRICKS_CONFIG_PROFILE).
"""

import logging
import time
import traceback

import mlflow
from mlflow.tracking import MlflowClient
from mlflow.types.responses import ResponsesAgentRequest

from era.tools.serving_utils import get_agent, log_user_feedback
from test_env import MLFLOW_EXPERIMENT_ID, SERVING_ENDPOINT, skip_if_missing_env

skip_if_missing_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXPERIMENT_ID = MLFLOW_EXPERIMENT_ID

# Configure MLflow to use Databricks tracking server
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(experiment_id=EXPERIMENT_ID)

print(f"MLflow Tracking URI: {mlflow.get_tracking_uri()}")
print(f"MLflow Experiment ID: {EXPERIMENT_ID}")

print(f"Testing client_request_id approach with endpoint: {SERVING_ENDPOINT}\n")
print("=" * 80)

# Test 1: Generate a request and capture client_request_id
print("\n[TEST 1] Query endpoint and capture client_request_id")
print("-" * 80)

agent = get_agent(SERVING_ENDPOINT)
test_request = ResponsesAgentRequest(input=[{"role": "user", "content": "What is 7+8?"}])

try:
    full_response = ""
    for event in agent.predict_stream(test_request):
        if hasattr(event, "delta") and event.delta:
            full_response += event.delta

    client_request_id = agent.get_last_client_request_id()
    print(f"✓ Client request ID: {client_request_id}")
    print(f"Response preview: {full_response[:100]}...")

    if not client_request_id:
        print("✗ FAILED: No client_request_id captured!")
        exit(1)

except Exception as e:
    print(f"✗ FAILED: {e}")
    exit(1)

# Test 2: Search for trace by client_request_id
print("\n[TEST 2] Search for trace by client_request_id")
print("-" * 80)


def find_trace_by_client_request_id(client, experiment_id, client_request_id, max_attempts=5, delay_sec=2):
    """Retry trace search until found or max_attempts; returns (matching_trace, recent_traces)."""
    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(delay_sec)
        recent_traces = client.search_traces(
            experiment_ids=[experiment_id], max_results=50, order_by=["timestamp DESC"]
        )
        for trace in recent_traces:
            if hasattr(trace.info, "client_request_id") and trace.info.client_request_id == client_request_id:
                return trace, recent_traces
            if hasattr(trace.info, "tags") and trace.info.tags.get("client_request_id") == client_request_id:
                return trace, recent_traces
    return None, recent_traces


try:
    client = MlflowClient()
    print("Waiting for trace to be indexed (retrying up to 5 times)...")
    matching_trace, recent_traces = find_trace_by_client_request_id(client, EXPERIMENT_ID, client_request_id)

    if matching_trace:
        print("✓ Found trace!")
        print(f"  Trace ID: {matching_trace.info.trace_id}")
        print(f"  Client request ID from trace: {matching_trace.info.client_request_id}")
    else:
        print(f"✗ FAILED: No trace found for client_request_id: {client_request_id}")
        print("\nDebugging - searching for recent traces:")
        for i, t in enumerate(recent_traces[:5]):
            print(f"\n  Trace {i + 1}:")
            print(f"    Trace ID: {t.info.trace_id}")
            print(f"    Client request ID: {getattr(t.info, 'client_request_id', 'N/A')}")
        exit(1)

except Exception as e:
    print(f"✗ FAILED: Error searching for trace: {e}")
    traceback.print_exc()
    exit(1)

# Test 3: Log feedback using client_request_id
print("\n[TEST 3] Log feedback using client_request_id")
print("-" * 80)

try:
    success = log_user_feedback(
        client_request_id=client_request_id,
        thumbs_up=True,
        comment="Test feedback from test script",
        user_id="test_user@example.com",
    )

    if success:
        print("✓ Feedback logged successfully!")

        # Verify feedback was attached - search again for the trace (with retry)
        matching_trace, _ = find_trace_by_client_request_id(client, EXPERIMENT_ID, client_request_id)
        if matching_trace and hasattr(matching_trace.data, "assessments") and matching_trace.data.assessments:
            print(f"  Assessments found: {len(matching_trace.data.assessments)}")
            for assessment in matching_trace.data.assessments:
                print(f"    - {assessment.name}: {assessment.value}")
        else:
            print("  Note: Assessments may take a moment to appear in search results")
    else:
        print("✗ FAILED: Feedback logging returned False")
        exit(1)

except Exception as e:
    print(f"✗ FAILED: Error logging feedback: {e}")
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 80)
print("SUCCESS! All tests passed.")
print("=" * 80)
print("\nKey findings:")
print(f"1. Client request ID generated: {client_request_id}")
print("2. Trace found by client_request_id: ✓")
print("3. Feedback logged successfully: ✓")
print("\nThis approach should resolve the dual-trace issue!")
print("Next: Update app.py to use get_last_client_request_id() instead of get_last_trace_id()")
