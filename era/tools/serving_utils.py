# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/model_serving_utils.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Serving endpoint client and feedback logging.

Trace/feedback correlation contract:
- Each request gets a unique client_request_id (generated here). The client never
  "tags the latest trace" with this id (that would be racy under concurrency).
- Feedback is tied to a trace either by:
  (1) trace_id: when the caller has the server-provided trace_id (e.g. from response
      metadata), pass it to log_user_feedback(..., trace_id=...) for deterministic attachment.
  (2) client_request_id: when the serving endpoint tags the trace it creates with this id
      (e.g. from request header X-Client-Request-ID), log_user_feedback(client_request_id=...)
      looks up the trace by tag. Requires the endpoint to set the tag; otherwise feedback
      will not find a trace.

Concurrency contract (CHANGED FROM ORIGINAL):
The upstream version stored current_client_request_id / current_trace_id as plain
instance attributes and documented itself as NOT thread-safe - safe only because
Streamlit reruns the script per interaction. In ERA this class backs a serving
endpoint that handles concurrent requests, so per-request state now lives in
contextvars instead of on the instance.

WHY contextvars and not threading.local: a ResponsesAgent endpoint may serve
requests as asyncio tasks on a single thread. threading.local would let those
tasks clobber each other's request ids; ContextVar isolates both OS threads and
asyncio tasks, because each Task copies the context at creation.

current_client_request_id / current_trace_id remain readable as attributes (they
are now properties over the ContextVars) so existing callers and tests are
unaffected.

Caveat: predict_stream is a generator and runs in whichever context consumes it.
Create and consume the stream in the same thread/task - handing the generator to
a different one will read a different context.
"""

import contextvars
import logging
import os
import uuid
from typing import Generator, Optional

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.entities.assessment import AssessmentSource, AssessmentSourceType
from mlflow.pyfunc import ResponsesAgent
from mlflow.tracking import MlflowClient
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

logger = logging.getLogger(__name__)

# Per-request state. Module-level by design: ContextVars must be created at module
# scope (creating them per-instance leaks context slots), and the values are scoped
# to a single in-flight request anyway, not to an agent instance.
_client_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "era_client_request_id", default=None
)
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "era_trace_id", default=None
)


class SimpleResponsesAgent(ResponsesAgent):
    """
    Production-ready Responses Agent for querying Databricks serving endpoints.

    Supports both streaming and non-streaming modes with MLflow tracing.
    Uses client_request_id for reliable feedback tracking across traces.
    """

    def __init__(self, model: str):
        """
        Initialize the ResponsesAgent.

        Args:
            model: The name of the Databricks serving endpoint to query

        Raises:
            RuntimeError: If WorkspaceClient cannot be initialized (bad credentials, no workspace context)
        """
        try:
            self.client = WorkspaceClient().serving_endpoints.get_open_ai_client()
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize WorkspaceClient. Check DATABRICKS_HOST and credentials: {e}"
            ) from e
        self.model = model

    # ------------------------------------------------------------------
    # Per-request state, exposed as properties for backward compatibility.
    # Reads and writes go to the ContextVars, so concurrent requests cannot
    # observe each other's ids.
    # ------------------------------------------------------------------
    @property
    def current_client_request_id(self) -> Optional[str]:
        return _client_request_id_var.get()

    @current_client_request_id.setter
    def current_client_request_id(self, value: Optional[str]) -> None:
        _client_request_id_var.set(value)

    @property
    def current_trace_id(self) -> Optional[str]:
        return _trace_id_var.get()

    @current_trace_id.setter
    def current_trace_id(self, value: Optional[str]) -> None:
        _trace_id_var.set(value)

    def _extract_trace_id(self, event) -> Optional[str]:
        """Extract server-provided trace_id from a stream event or response object."""
        tid = getattr(event, "trace_id", None) or getattr(getattr(event, "response_metadata", None), "trace_id", None)
        if tid and isinstance(tid, str):
            return tid
        return None

    def predict_stream(self, request: ResponsesAgentRequest) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Query the endpoint with streaming enabled.

        Args:
            request: ResponsesAgentRequest containing the conversation input

        Yields:
            ResponsesAgentStreamEvent objects as tokens arrive

        Note: No manual tracing - relies on serving endpoint's automatic tracing.
        Client request ID is generated and passed in the request so the server can tag
        the trace; we do not tag from the client (racy under concurrency).
        """
        client_request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.current_client_request_id = client_request_id
        self.current_trace_id = None
        logger.info(f"Generated client request ID: {client_request_id}")

        try:
            event_count = 0
            kwargs = {
                "input": request.input,
                "stream": True,
                "model": self.model,
                "extra_headers": {"X-Client-Request-ID": client_request_id},
            }
            for event in self.client.responses.create(**kwargs):
                event_count += 1
                # Capture server-provided trace_id from event if present (deterministic feedback).
                tid = self._extract_trace_id(event)
                if tid:
                    self.current_trace_id = tid

                # Filter out problematic function_call_output events to avoid Pydantic warnings.
                # Tool output is still accessible via response.output_item.done events in app.py.
                if hasattr(event, "item") and hasattr(event.item, "type"):
                    if event.item.type == "function_call_output":
                        logger.debug(
                            "Skipping function_call_output event: %s",
                            getattr(event.item, "output", ""),
                        )
                        continue

                yield event

            logger.info(f"Completed streaming {event_count} events for client_request_id: {client_request_id}")

        except Exception as e:
            logger.error(f"Error in predict_stream: {e}")
            raise

    def get_last_client_request_id(self) -> Optional[str]:
        """Get the client request ID from the last predict_stream call."""
        return self.current_client_request_id

    def get_last_trace_id(self) -> Optional[str]:
        """Get the server-provided trace ID from the last predict_stream call, if any."""
        return self.current_trace_id

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """
        Query the endpoint without streaming (synchronous response).
        """
        client_request_id = f"req-{uuid.uuid4().hex[:8]}"
        self.current_client_request_id = client_request_id
        self.current_trace_id = None
        response = self.client.responses.create(
            input=request.input,
            stream=False,
            model=self.model,
            extra_headers={"X-Client-Request-ID": client_request_id},
        )
        # Capture trace_id from non-streaming response
        tid = self._extract_trace_id(response)
        if tid:
            self.current_trace_id = tid
        return response


def get_agent(endpoint_name: str) -> SimpleResponsesAgent:
    """
    Factory function to create a ResponsesAgent instance.

    Args:
        endpoint_name: Name of the Databricks serving endpoint

    Returns:
        SimpleResponsesAgent instance configured for the endpoint
    """
    return SimpleResponsesAgent(model=endpoint_name)


def _log_feedback_to_trace(
    trace_id: str,
    thumbs_up: bool,
    comment: str,
    user_id: str,
) -> None:
    """Attach user feedback assessment to a specific trace."""
    mlflow.log_feedback(
        trace_id=trace_id,
        name="user_feedback",
        value=thumbs_up,
        rationale=comment or ("Positive feedback" if thumbs_up else "Negative feedback"),
        source=AssessmentSource(
            source_type=AssessmentSourceType.HUMAN,
            source_id=user_id,
        ),
    )


def log_user_feedback(
    client_request_id: str,
    thumbs_up: bool,
    comment: str = "",
    user_id: str = "unknown",
    experiment_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> bool:
    """
    Log user feedback for a specific trace.

    Prefer passing trace_id when the server provided it (deterministic). Otherwise
    the trace is looked up by client_request_id tag (requires the serving endpoint
    to have tagged the trace, e.g. from X-Client-Request-ID header).

    Args:
        client_request_id: Client request ID (used for lookup when trace_id is None).
        thumbs_up: True for positive, False for negative.
        comment: Optional comment.
        user_id: User identifier.
        experiment_id: MLflow experiment ID (defaults to MLFLOW_EXPERIMENT_ID env).
        trace_id: If set, feedback is attached to this trace directly (no search).

    Returns:
        True if feedback was logged successfully, False otherwise.
    """
    try:
        logger.info(
            "Attempting to log feedback: client_request_id=%s thumbs_up=%s user_id=%s trace_id=%s",
            client_request_id,
            thumbs_up,
            user_id,
            trace_id,
        )

        if trace_id:
            # Deterministic: attach to this trace only (no search, safe under concurrency).
            _log_feedback_to_trace(trace_id, thumbs_up, comment, user_id)
            logger.info("Successfully logged feedback for trace_id=%s", trace_id)
            return True

        # Fallback: find trace by client_request_id tag (set by server when it receives X-Client-Request-ID).
        if experiment_id is None:
            experiment_id = os.environ.get("MLFLOW_EXPERIMENT_ID")
        if not experiment_id or experiment_id.strip() in ("", "YOUR_EXPERIMENT_ID", "0"):
            logger.error(
                "MLFLOW_EXPERIMENT_ID is not set or invalid ('%s'). Cannot search for traces.",
                experiment_id,
            )
            return False

        client = MlflowClient()
        # Search with pagination to handle older traces
        matching_trace = None
        page_token = None
        max_pages = 5  # Search up to 250 traces (50 per page)

        for _ in range(max_pages):
            search_kwargs = {
                "experiment_ids": [experiment_id],
                "max_results": 50,
                "order_by": ["timestamp DESC"],
            }
            if page_token:
                search_kwargs["page_token"] = page_token

            recent_traces = client.search_traces(**search_kwargs)

            for trace in recent_traces:
                if getattr(trace.info, "client_request_id", None) == client_request_id:
                    matching_trace = trace
                    break
                if getattr(trace.info, "tags", None) and trace.info.tags.get("client_request_id") == client_request_id:
                    matching_trace = trace
                    break

            if matching_trace:
                break

            # Check for next page
            page_token = getattr(recent_traces, "token", None)
            if not page_token:
                break

        if not matching_trace:
            logger.error(
                "No trace found for client_request_id=%s in experiment=%s "
                "(endpoint may not tag traces with X-Client-Request-ID)",
                client_request_id,
                experiment_id,
            )
            return False

        tid = matching_trace.info.trace_id
        _log_feedback_to_trace(tid, thumbs_up, comment, user_id)
        logger.info("Successfully logged feedback for trace_id=%s (client_request_id=%s)", tid, client_request_id)
        return True

    except Exception as e:
        logger.error("Failed to log feedback for client_request_id=%s: %s", client_request_id, e, exc_info=True)
        return False
