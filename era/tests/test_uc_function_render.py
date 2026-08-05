"""
Guards on the Milestone B governed-egress layer (ERA addition, not grafted).

Everything here runs offline. That is deliberate: the properties being checked are
policy properties, and a policy control that can only be verified by calling a paid
third-party API in a live workspace is a control nobody actually verifies.

The one test that does need a workspace is marked `integration` and skips cleanly.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONF_DIR = REPO_ROOT / "conf"
SQL_PATH = REPO_ROOT / "era" / "connections" / "you_uc_functions.sql"
RENDERER = REPO_ROOT / "era" / "connections" / "render_uc_functions.py"


def _flatten(path: pathlib.Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        item
        for key, value in doc.items()
        if key != "version" and isinstance(value, list)
        for item in value
        if isinstance(item, str)
    ]


@pytest.fixture(scope="module")
def sql() -> str:
    assert SQL_PATH.exists(), f"{SQL_PATH} missing - run render_uc_functions.py"
    return SQL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------

def test_committed_sql_is_not_stale():
    """
    The deployed policy must equal the reviewable policy.

    If this fails someone edited conf/ without regenerating, or edited the
    generated SQL by hand. Either way the file people review and the rule Unity
    Catalog enforces have diverged, which is the whole failure mode this layer
    exists to prevent.
    """
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"generated SQL is out of sync with conf/\n{result.stdout}{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Policy coherence
# ---------------------------------------------------------------------------

def test_no_domain_appears_on_both_lists():
    """A domain that is both trusted and blocked has no defined behaviour."""
    allow = set(_flatten(CONF_DIR / "domain_allowlist.yaml"))
    deny = set(_flatten(CONF_DIR / "domain_denylist.yaml"))
    assert not allow & deny, f"domains on both lists: {sorted(allow & deny)}"


def test_every_denylisted_domain_reaches_the_sql(sql):
    """A domain in the YAML that never made it into the function is not enforced."""
    missing = [d for d in _flatten(CONF_DIR / "domain_denylist.yaml") if d not in sql]
    assert not missing, f"denylisted but absent from the deployed function: {missing}"


def test_domain_params_are_structurally_mutually_exclusive(sql):
    """
    The You.com Search API rejects include_domains and exclude_domains together.

    The function must make that impossible by construction rather than by asking
    the caller nicely - the caller here is an LLM choosing tool arguments.
    """
    inc = re.search(r"'include_domains',\s*CASE WHEN (.+?) THEN", sql, re.S)
    exc = re.search(r"'exclude_domains',\s*CASE WHEN (.+?) THEN", sql, re.S)
    assert inc and exc, "could not find both domain params in the rendered SQL"

    inc_cond = " ".join(inc.group(1).split())
    exc_cond = " ".join(exc.group(1).split())

    # The two guards must be exact negations of one another.
    assert inc_cond.endswith("IS NOT NULL"), inc_cond
    assert exc_cond.endswith("IS NULL"), exc_cond
    assert inc_cond[: -len("IS NOT NULL")].strip() == exc_cond[: -len("IS NULL")].strip(), (
        "include/exclude guards test different expressions, so some input could "
        f"satisfy both:\n  include: {inc_cond}\n  exclude: {exc_cond}"
    )


def test_non_200_is_surfaced_not_swallowed(sql):
    """
    Every tool must report transport failure explicitly.

    An empty result on error is worse than an error: it reads to the model as
    "the web had nothing to say", which is an invitation to answer from memory
    and present it as retrieved fact.
    """
    assert sql.count("era_error") >= 2, "each function needs an error envelope"
    assert "status_code = 200" in sql


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def test_api_key_is_only_ever_a_secret_reference():
    """No credential material in git - the key is always a secret() lookup."""
    tracked = list((REPO_ROOT / "era" / "connections").rglob("*")) + list(CONF_DIR.rglob("*"))
    for path in tracked:
        if not path.is_file() or path.suffix not in {".py", ".sql", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"X-API-Key'\s*,\s*([^)]+)\)", text):
            assert "secret(" in match.group(1), (
                f"{path.relative_to(REPO_ROOT)} passes X-API-Key without secret(): {match.group(1)!r}"
            )
        # A You.com key is a long opaque token; catch anything key-shaped assigned inline.
        for match in re.finditer(r"(?i)(api[_-]?key|bearer_token)\s*[:=]\s*['\"]([A-Za-z0-9_\-]{24,})['\"]", text):
            pytest.fail(f"possible hardcoded credential in {path.relative_to(REPO_ROOT)}: {match.group(1)}")


# ---------------------------------------------------------------------------
# Coexistence with the Milestone A fallback
# ---------------------------------------------------------------------------

def test_governed_functions_do_not_clobber_the_03b_fallback(sql):
    """
    03b already registers you_web_search / you_content_extract / you_research
    against the free-tier MCP endpoint. Those remain the Milestone A fallback, so
    the governed functions must not reuse their names.
    """
    created = set(re.findall(r"CREATE OR REPLACE FUNCTION\s+[\w.]+\.(\w+)\s*\(", sql))
    assert created, "no functions found in the rendered SQL"

    collisions = created & {"you_web_search", "you_content_extract", "you_research"}
    assert not collisions, f"would overwrite the Milestone A fallback functions: {collisions}"
    assert all(name.startswith("era_") for name in created), (
        f"all governed functions must carry the era_ prefix, got: {sorted(created)}"
    )


def test_fast_and_slow_endpoints_use_the_right_connection(sql):
    """
    Search and Contents live on ydc-index.io; Research lives on api.you.com. A UC
    connection pins one host, so using the wrong one is a guaranteed 404 that will
    only show up at runtime.
    """
    assert "conn    => 'you_search_http'" in sql
    assert "you_research_http" not in sql, (
        "the slow-tier connection must not appear in the fast-tier SQL - Research "
        "is long-running and belongs in a Python tool, not a SQL UDF"
    )


def test_routing_policy_matches_the_verified_api_surface():
    """
    Pin the non-obvious facts about You.com so a future edit cannot quietly
    contradict them. Each was verified against the live API reference.
    """
    policy = yaml.safe_load((CONF_DIR / "routing_policy.yaml").read_text(encoding="utf-8"))
    ep = policy["endpoints"]

    assert ep["search"]["host"] == "https://ydc-index.io"
    assert ep["contents"]["host"] == "https://ydc-index.io"
    assert ep["research"]["host"] == "https://api.you.com"
    assert ep["finance_research"]["host"] == "https://api.you.com"

    # ZDR covers /v1/search and nothing else.
    assert ep["search"]["zdr_covered"] is True
    assert not any(ep[name]["zdr_covered"] for name in ("contents", "research", "finance_research"))

    # Research can go async; Finance Research documents no background flag.
    assert ep["research"]["supports_background"] is True
    assert ep["finance_research"]["supports_background"] is False

    # frontier effort is background-only.
    assert "frontier" in policy["research_effort"]["requires_background"]


# ---------------------------------------------------------------------------
# Live call (opt-in)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_live_search_returns_results(serving_env):  # noqa: ARG001 - fixture gates on env
    """
    Smoke test against the real connection. Requires ERA_WAREHOUSE_ID plus a
    provisioned you_search_http connection and secret.
    """
    import json
    import os

    warehouse_id = os.environ.get("ERA_WAREHOUSE_ID")
    if not warehouse_id:
        pytest.skip("set ERA_WAREHOUSE_ID to run the live You.com smoke test")

    from databricks.sdk import WorkspaceClient

    from era.connections.render_uc_functions import load_config

    catalog, schema = load_config()
    w = WorkspaceClient()
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"SELECT {catalog}.{schema}.era_you_search('NVIDIA earnings', 'week', 3, NULL)",
        wait_timeout="50s",
    )
    assert resp.status and resp.status.state and resp.status.state.value == "SUCCEEDED", resp.status

    payload = json.loads(resp.result.data_array[0][0])
    assert "era_error" not in payload, payload["era_error"]
    assert "results" in payload, f"unexpected shape: {list(payload)[:5]}"
