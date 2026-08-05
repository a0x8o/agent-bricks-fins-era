# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_trace_capture.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Test script to explore different ways of capturing trace IDs from serving endpoint calls.
Run this to understand which approach correctly captures the endpoint's trace ID.
"""

import logging

import mlflow
from mlflow.types.responses import ResponsesAgentRequest

from era.tools.serving_utils import get_agent
from test_env import SERVING_ENDPOINT, skip_if_missing_env

skip_if_missing_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print(f"Testing with endpoint: {SERVING_ENDPOINT}\n")
print("=" * 80)

# Test message
test_request = ResponsesAgentRequest(input=[{"role": "user", "content": "Hello, what is 2+2?"}])

# Test 1: Current approach with manual span
print("\n[TEST 1] Current approach: Manual span wrapper")
print("-" * 80)
agent = get_agent(SERVING_ENDPOINT)
trace_ids_collected = []

try:
    full_response = ""
    for event in agent.predict_stream(test_request):
        if hasattr(event, "delta") and event.delta:
            full_response += event.delta

    manual_span_trace_id = agent.get_last_trace_id()
    print(f"✓ Manual span trace ID: {manual_span_trace_id}")
    trace_ids_collected.append(("Manual Span", manual_span_trace_id))

    # Try getting active span after streaming
    try:
        active_span = mlflow.get_current_active_span()
        if active_span:
            active_trace_id = active_span.trace_id
            print(f"✓ Active span trace ID (after stream): {active_trace_id}")
            trace_ids_collected.append(("Active Span After", active_trace_id))
        else:
            print("✗ No active span found after streaming")
    except Exception as e:
        print(f"✗ Error getting active span: {e}")

    print(f"Response preview: {full_response[:100]}...")

except Exception as e:
    print(f"✗ Test 1 failed: {e}")

# Test 2: Check if response object has trace metadata
print("\n[TEST 2] Inspecting response object metadata")
print("-" * 80)
try:
    agent2 = get_agent(SERVING_ENDPOINT)
    response_events = []

    for event in agent2.client.responses.create(input=test_request.input, stream=True, model=SERVING_ENDPOINT):
        response_events.append(event)

        # Check first event for metadata
        if len(response_events) == 1:
            print(f"Event type: {type(event)}")
            print(f"Event attributes: {dir(event)}")

            # Check for common trace-related attributes
            for attr in ["trace_id", "request_id", "id", "metadata", "headers"]:
                if hasattr(event, attr):
                    val = getattr(event, attr)
                    print(f"  - {attr}: {val}")

    print(f"✓ Processed {len(response_events)} events")

except Exception as e:
    print(f"✗ Test 2 failed: {e}")

# Test 3: Non-streaming to compare
print("\n[TEST 3] Non-streaming response (for comparison)")
print("-" * 80)
try:
    agent3 = get_agent(SERVING_ENDPOINT)
    response = agent3.predict(test_request)

    print(f"Response type: {type(response)}")
    print(f"Response attributes: {dir(response)}")

    # Check for trace-related attributes
    for attr in ["trace_id", "request_id", "id", "metadata"]:
        if hasattr(response, attr):
            val = getattr(response, attr)
            print(f"  - {attr}: {val}")
            if "trace" in attr.lower() or "id" in attr.lower():
                trace_ids_collected.append((f"Non-streaming {attr}", val))

except Exception as e:
    print(f"✗ Test 3 failed: {e}")

# Summary
print("\n" + "=" * 80)
print("TRACE ID SUMMARY")
print("=" * 80)
if trace_ids_collected:
    for source, trace_id in trace_ids_collected:
        print(f"{source:30} -> {trace_id}")

    # Check if all trace IDs are the same
    unique_traces = set([tid for _, tid in trace_ids_collected if tid])
    if len(unique_traces) == 1:
        print("\n✓ All trace IDs match - good!")
    else:
        print(f"\n⚠ WARNING: Found {len(unique_traces)} different trace IDs!")
        print("This likely explains why you're seeing multiple traces in Databricks.")
else:
    print("✗ No trace IDs collected")

print("\nNext steps:")
print("1. Check the Databricks MLflow UI for these trace IDs")
print("2. Note which trace ID(s) appear under service principal vs user")
print("3. Use the correct trace ID approach in the app")
