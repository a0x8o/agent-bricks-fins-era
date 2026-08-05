# --------------------------------------------------------------------------
# GRAFTED FILE - MODIFIED FROM ORIGINAL
# Source repo   : alexxx-db/agent-bricks-fins-legal
# Source path   : app/streamlit-chatbot-app/test_env.py
# Source commit : cf640d0 (2026-03-23)
# Grafted into  : agent-bricks-fins-era on 2026-08-03
# Modifications : provenance header added; see this repo's git history for
#                 all subsequent changes.
# License       : Databricks DB license - see LICENSE.md and NOTICE.md at the
#                 root of this repository. Provided AS-IS.
# --------------------------------------------------------------------------
"""
Shared test environment: required env vars and skip helper.
Used by script-style tests and by conftest fixtures.
"""

import os

import pytest

# Use explicit profile for tests when not set (avoids assuming a specific workspace)
if "DATABRICKS_CONFIG_PROFILE" not in os.environ:
    os.environ["DATABRICKS_CONFIG_PROFILE"] = "DEFAULT"

SERVING_ENDPOINT = os.environ.get("SERVING_ENDPOINT")
MLFLOW_EXPERIMENT_ID = os.environ.get("MLFLOW_EXPERIMENT_ID")

SKIP_REASON = (
    "Set SERVING_ENDPOINT and MLFLOW_EXPERIMENT_ID to run these tests. See app/streamlit-chatbot-app/README.md."
)


def skip_if_missing_env() -> None:
    """Skip the current module if required env vars are not set (for script-style tests)."""
    if not SERVING_ENDPOINT or not MLFLOW_EXPERIMENT_ID:
        pytest.skip(SKIP_REASON, allow_module_level=True)
