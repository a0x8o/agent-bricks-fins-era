# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_no_manual_span.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Test script to try capturing trace ID WITHOUT manual span wrapper.
This tests if the serving endpoint's native tracing is sufficient.
"""

import logging

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.types.responses import ResponsesAgentRequest

from test_env import SERVING_ENDPOINT, skip_if_missing_env

skip_if_missing_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print(f"Testing WITHOUT manual span wrapper on endpoint: {SERVING_ENDPOINT}\n")
print("=" * 80)

# Test message
test_request = ResponsesAgentRequest(input=[{"role": "user", "content": "What is 3+3?"}])

client = WorkspaceClient().serving_endpoints.get_open_ai_client()

# Approach 1: Try to get active span during iteration
print("\n[APPROACH 1] Check for active span DURING streaming")
print("-" * 80)
try:
    full_response = ""
    trace_id_during_stream = None

    for i, event in enumerate(client.responses.create(input=test_request.input, stream=True, model=SERVING_ENDPOINT)):
        if hasattr(event, "delta") and event.delta:
            full_response += event.delta

        # Try to capture active span on first event
        if i == 0:
            try:
                active_span = mlflow.get_current_active_span()
                if active_span:
                    trace_id_during_stream = active_span.trace_id
                    print(f"✓ Found active span during stream: {trace_id_during_stream}")
                else:
                    print("✗ No active span found during streaming")
            except Exception as e:
                print(f"✗ Error checking active span: {e}")

    print(f"Response: {full_response[:100]}...")
    print(f"Trace ID captured: {trace_id_during_stream}")

except Exception as e:
    print(f"✗ Approach 1 failed: {e}")

# Approach 2: Use @mlflow.trace decorator
print("\n[APPROACH 2] Using @mlflow.trace decorator")
print("-" * 80)


@mlflow.trace
def query_with_trace_decorator(client, request, model):
    """Query with automatic MLflow tracing via decorator."""
    full_response = ""
    for event in client.responses.create(input=request.input, stream=True, model=model):
        if hasattr(event, "delta") and event.delta:
            full_response += event.delta
    return full_response


try:
    response = query_with_trace_decorator(client, test_request, SERVING_ENDPOINT)

    # Try to get trace ID after decorated function
    try:
        active_span = mlflow.get_current_active_span()
        if active_span:
            trace_id_from_decorator = active_span.trace_id
            print(f"✓ Trace ID from decorator: {trace_id_from_decorator}")
        else:
            print("✗ No active span after decorator")
    except Exception as e:
        print(f"✗ Error: {e}")

    print(f"Response: {response[:100]}...")

except Exception as e:
    print(f"✗ Approach 2 failed: {e}")

# Approach 3: Context manager approach
print("\n[APPROACH 3] Using mlflow.start_span but checking for parent trace")
print("-" * 80)
try:
    # Check if there's already an active trace before we start
    try:
        parent_span = mlflow.get_current_active_span()
        if parent_span:
            print(f"⚠ Parent span already exists: {parent_span.trace_id}")
    except Exception as e:
        print(f"✓ No parent span (clean state): {e}")

    full_response = ""
    with mlflow.start_span(name="test_span") as span:
        our_trace_id = span.trace_id
        print(f"Our span trace ID: {our_trace_id}")

        for event in client.responses.create(input=test_request.input, stream=True, model=SERVING_ENDPOINT):
            if hasattr(event, "delta") and event.delta:
                full_response += event.delta

        # Check if serving endpoint created a different trace
        try:
            active = mlflow.get_current_active_span()
            if active and active.trace_id != our_trace_id:
                print(f"⚠ Different active span detected: {active.trace_id}")
            else:
                print(f"✓ Consistent trace ID: {our_trace_id}")
        except Exception:
            pass

    print(f"Response: {full_response[:100]}...")

except Exception as e:
    print(f"✗ Approach 3 failed: {e}")

print("\n" + "=" * 80)
print("RECOMMENDATIONS:")
print("=" * 80)
print("1. If APPROACH 1 found a trace ID, the endpoint auto-traces without manual spans")
print("2. If APPROACH 2 worked, use @mlflow.trace decorator on predict_stream")
print("3. If multiple different trace IDs appeared, that explains the dual-trace issue")
print("4. Check Databricks MLflow UI to see which trace ID corresponds to which user")
