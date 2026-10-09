"""Tests for Apps resource merging used after a bundle-only chatbot deploy."""

from __future__ import annotations

import importlib.util
import pathlib

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "resources"
    / "grant_app_mas_permissions.py"
)
_spec = importlib.util.spec_from_file_location("grant_app_mas_permissions", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
merge_app_resources = _mod.merge_app_resources


def test_merge_keeps_lakebase_and_replaces_serving_bindings():
    existing = [
        {
            "name": "serving-endpoint",
            "serving_endpoint": {"name": "stale-mas", "permission": "CAN_QUERY"},
        },
        {
            "name": "sub-agent-1",
            "serving_endpoint": {"name": "stale-ka", "permission": "CAN_QUERY"},
        },
        {
            "name": "database",
            "database": {
                "database_name": "databricks_postgres",
                "instance_name": "agent-bricks-lakebase-workshop",
                "permission": "CAN_CONNECT_AND_CREATE",
            },
        },
        {
            "name": "sql-warehouse",
            "sql_warehouse": {"name": "shared", "permission": "CAN_USE"},
        },
    ]
    merged = merge_app_resources(existing, "mas-live", ["ka-live", "ka-other"])
    names = [r["name"] for r in merged]
    assert names[0] == "serving-endpoint"
    assert merged[0]["serving_endpoint"]["name"] == "mas-live"
    assert names[1] == "sub-agent-1"
    assert merged[1]["serving_endpoint"]["name"] == "ka-live"
    assert names[2] == "sub-agent-2"
    assert "database" in names
    assert "sql-warehouse" in names
    assert "stale-mas" not in str(merged)
    assert "stale-ka" not in str(merged)


def test_merge_attaches_functions_genie_warehouse_and_you_connection():
    existing = [
        {
            "name": "database",
            "database": {"database_name": "databricks_postgres"},
        },
    ]
    merged = merge_app_resources(
        existing,
        "mas-live",
        [],
        uc_functions=["alexxx.era_research.you_web_search"],
        genie_spaces=[{"id": "space-1", "name": "Financial_Data_Explorer"}],
        warehouse_id="abc123",
        connection_name="you-mcp",
    )
    by_name = {r["name"]: r for r in merged}
    assert by_name["uc-fn-1"]["function"]["permission"] == "CAN_EXECUTE"
    assert by_name["genie-space"]["genie_space"]["space_id"] == "space-1"
    assert by_name["sql-warehouse"]["sql_warehouse"]["id"] == "abc123"
    assert by_name["you-mcp"]["connection"]["name"] == "you-mcp"
    assert "database" in by_name
