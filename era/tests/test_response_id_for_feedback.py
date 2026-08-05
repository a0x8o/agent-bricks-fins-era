# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_response_id_for_feedback.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Test if we can use the response.id field for feedback instead of manual trace ID.
This tests whether the serving endpoint's response ID is what we should use.
"""

import logging

from databricks.sdk import WorkspaceClient
from mlflow.types.responses import ResponsesAgentRequest

from test_env import SERVING_ENDPOINT, skip_if_missing_env

skip_if_missing_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print(f"Testing response ID approach with endpoint: {SERVING_ENDPOINT}\n")
print("=" * 80)

# Test message
test_request = ResponsesAgentRequest(input=[{"role": "user", "content": "What is 5+5?"}])

client = WorkspaceClient().serving_endpoints.get_open_ai_client()

print("\n[TEST] Query endpoint and capture response ID")
print("-" * 80)

# Make a simple call without any manual tracing
full_response = ""
response_id = None
event_ids = []

for event in client.responses.create(input=test_request.input, stream=True, model=SERVING_ENDPOINT):
    if hasattr(event, "delta") and event.delta:
        full_response += event.delta

    # Capture IDs from events
    if hasattr(event, "id"):
        event_ids.append(event.id)

    # First event should have the response ID
    if response_id is None and hasattr(event, "item_id"):
        response_id = event.item_id
        print(f"✓ Found item_id from event: {response_id}")

print(f"\nResponse preview: {full_response[:100]}...")
print(f"\nUnique event IDs collected: {set(event_ids)}")

# Try non-streaming to see if it's clearer
print("\n[TEST] Non-streaming response to compare")
print("-" * 80)

response = client.responses.create(input=test_request.input, stream=False, model=SERVING_ENDPOINT)

print(f"Response ID: {response.id}")
print(f"Response has _request_id: {hasattr(response, '_request_id')}")
if hasattr(response, "_request_id"):
    print(f"  _request_id value: {response._request_id}")

# Check all id-like attributes
print("\nAll ID-related attributes:")
for attr in dir(response):
    if "id" in attr.lower() and not attr.startswith("_"):
        val = getattr(response, attr, None)
        if val and isinstance(val, str):
            print(f"  {attr}: {val}")

print("\n" + "=" * 80)
print("HYPOTHESIS TEST")
print("=" * 80)
print("\nThe response.id field is likely the serving endpoint's request/trace ID.")
print("Try using THIS ID when calling mlflow.log_feedback() instead of your manual trace ID.")
print("\nNext step: Test logging feedback with this response.id")
print(f"  Response ID to use: {response.id}")
