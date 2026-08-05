# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_no_manual_tracing.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Test the updated approach without manual tracing in predict_stream.
Verify that only ONE trace is created (by the serving endpoint).

Requires env: SERVING_ENDPOINT, MLFLOW_EXPERIMENT_ID (optional: DATABRICKS_CONFIG_PROFILE).
"""

import logging
import time
import traceback

import mlflow
from mlflow.tracking import MlflowClient
from mlflow.types.responses import ResponsesAgentRequest

from era.tools.serving_utils import get_agent
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
print(f"Serving Endpoint: {SERVING_ENDPOINT}\n")

print(f"Testing NO manual tracing approach with endpoint: {SERVING_ENDPOINT}\n")
print("=" * 80)

# Get initial trace count
client = MlflowClient()
initial_traces = client.search_traces(experiment_ids=[EXPERIMENT_ID], max_results=10, order_by=["timestamp DESC"])
initial_count = len(initial_traces)
print(f"Initial trace count: {initial_count}")

# Make a query
print("\n[TEST] Query endpoint without manual tracing")
print("-" * 80)

agent = get_agent(SERVING_ENDPOINT)
test_request = ResponsesAgentRequest(input=[{"role": "user", "content": "What is 9+10?"}])

try:
    full_response = ""
    for event in agent.predict_stream(test_request):
        if hasattr(event, "delta") and event.delta:
            full_response += event.delta

    client_request_id = agent.get_last_client_request_id()
    print(f"✓ Client request ID: {client_request_id}")
    print(f"Response preview: {full_response[:100]}...")

    # Retry until trace appears (indexing can be delayed)
    initial_trace_ids = {t.info.trace_id for t in initial_traces}
    new_trace_list = []
    for _ in range(5):
        time.sleep(2)
        recent = client.search_traces(experiment_ids=[EXPERIMENT_ID], max_results=10, order_by=["timestamp DESC"])
        new_trace_list = [t for t in recent if t.info.trace_id not in initial_trace_ids]
        if new_trace_list:
            break
    new_count = len(new_trace_list)

    print("\n📊 Trace Analysis:")
    print(f"  Traces before query: {initial_count}")
    print(f"  New traces created: {new_count}")

    if new_count == 1:
        print("\n✓ SUCCESS! Only ONE trace was created (no duplicate)")
        print("  This means we eliminated the manual client-side trace!")
    elif new_count == 0:
        print("\n⚠ WARNING: No new trace was created")
        print("  The serving endpoint might not be auto-tracing")
    else:
        print(f"\n✗ PROBLEM: {new_count} traces were created")
        print("  We're still getting duplicate traces")

        # Show the traces
        print("\n  Recent traces:")
        for i, trace in enumerate(new_trace_list):
            print(f"    {i + 1}. {trace.info.trace_id}")
            print(f"       Name: {trace.info.tags.get('mlflow.traceName', 'N/A')}")
            if hasattr(trace.info, "client_request_id"):
                print(f"       Client Request ID: {trace.info.client_request_id}")

except Exception as e:
    print(f"✗ FAILED: {e}")
    traceback.print_exc()

print("\n" + "=" * 80)
