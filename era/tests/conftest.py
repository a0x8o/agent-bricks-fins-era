# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/conftest.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Pytest configuration: central env check and fixtures for serving-endpoint tests.
"""

import os

import pytest


# Markers: "integration" = requires live SERVING_ENDPOINT + MLFLOW_EXPERIMENT_ID (skip in CI)
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests that require a live Databricks serving endpoint (skip when env not set)",
    )


# Apply default profile when not set (use DEFAULT; set env for your workspace)
if "DATABRICKS_CONFIG_PROFILE" not in os.environ:
    os.environ["DATABRICKS_CONFIG_PROFILE"] = "DEFAULT"

SERVING_ENDPOINT = os.environ.get("SERVING_ENDPOINT")
MLFLOW_EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID")


@pytest.fixture(scope="session")
def serving_env():
    """
    (endpoint_name, experiment_id). Skips the test if SERVING_ENDPOINT or
    MLFLOW_EXPERIMENT_ID are not set.
    """
    if not SERVING_ENDPOINT or not MLFLOW_EXPERIMENT_ID:
        pytest.skip(
            "Set SERVING_ENDPOINT and MLFLOW_EXPERIMENT_ID to run these tests. See era/tests/README.md."
        )
    return SERVING_ENDPOINT, MLFLOW_EXPERIMENT_ID


@pytest.fixture(autouse=True)
def _reset_request_context():
    """
    Reset SimpleResponsesAgent's per-request ContextVars between tests.

    WHY (ERA addition): per-request state moved from instance attributes to
    module-level ContextVars so the agent can back a concurrent serving endpoint.
    ContextVars persist for the life of the context, and pytest runs every test in
    the same context - so without this reset a test that asserts "state starts as
    None" would pass or fail depending on which tests ran before it. Resetting here
    keeps the suite order-independent instead of accidentally-ordered.
    """
    from era.tools.serving_utils import _client_request_id_var, _trace_id_var

    t1 = _client_request_id_var.set(None)
    t2 = _trace_id_var.set(None)
    try:
        yield
    finally:
        _client_request_id_var.reset(t1)
        _trace_id_var.reset(t2)
