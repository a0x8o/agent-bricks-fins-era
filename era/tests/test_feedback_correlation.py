# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_feedback_correlation.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Unit tests for trace/feedback correlation (no live endpoint).
Verify that feedback uses trace_id when provided and does not rely on "latest trace".
"""

import os
from unittest.mock import MagicMock, patch

from era.tools.serving_utils import log_user_feedback


def test_log_user_feedback_with_trace_id_calls_mlflow_directly():
    """When trace_id is provided, log_feedback is called with it and no trace search is performed."""
    with patch("era.tools.serving_utils.mlflow.log_feedback") as mock_feedback:
        with patch("era.tools.serving_utils.MlflowClient") as mock_client_cls:
            result = log_user_feedback(
                "req-abc123",
                thumbs_up=True,
                user_id="test@example.com",
                trace_id="trace-xyz-789",
            )
            mock_feedback.assert_called_once()
            call_kw = mock_feedback.call_args[1]
            assert call_kw["trace_id"] == "trace-xyz-789"
            mock_client_cls.assert_not_called()
            assert result is True


def test_log_user_feedback_without_trace_id_searches_by_client_request_id():
    """When trace_id is None, search_traces is used to find by client_request_id tag."""
    mock_trace = MagicMock()
    mock_trace.info.trace_id = "found-trace-123"
    mock_trace.info.client_request_id = None
    mock_trace.info.tags = {"client_request_id": "req-abc123"}

    with patch("era.tools.serving_utils.mlflow.log_feedback") as mock_feedback:
        with patch("era.tools.serving_utils.MlflowClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.search_traces.return_value = [mock_trace]
            mock_client_cls.return_value = mock_client

            with patch.dict(os.environ, {"MLFLOW_EXPERIMENT_ID": "1"}, clear=False):
                result = log_user_feedback(
                    "req-abc123",
                    thumbs_up=False,
                    user_id="test@example.com",
                    trace_id=None,
                )
            mock_client.search_traces.assert_called_once()
            mock_feedback.assert_called_once()
            assert mock_feedback.call_args[1]["trace_id"] == "found-trace-123"
            assert result is True


def test_log_user_feedback_no_trace_id_and_no_match_returns_false():
    """When trace_id is None and no trace has the client_request_id tag, returns False."""
    with patch("era.tools.serving_utils.mlflow.log_feedback"):
        with patch("era.tools.serving_utils.MlflowClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.search_traces.return_value = []
            mock_client_cls.return_value = mock_client
            with patch.dict(os.environ, {"MLFLOW_EXPERIMENT_ID": "1"}, clear=False):
                result = log_user_feedback(
                    "req-nonexistent",
                    thumbs_up=True,
                    trace_id=None,
                )
            assert result is False
