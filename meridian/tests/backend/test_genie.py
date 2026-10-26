"""Genie client state machine + read-only SQL guard."""

import pytest

from app.services.genie_client import extract_answer, tables_used
from app.services.sql_exec import _SELECT_GUARD


def test_extract_answer_text_sql_suggestions():
    msg = {
        "status": "COMPLETED",
        "attachments": [
            {"attachment_id": "a1", "query": {"query": "SELECT 1", "description": "d"}},
            {"text": {"content": "answer text"}},
            {"suggested_questions": ["follow up?"]},
        ],
    }
    out = extract_answer(msg)
    assert out["text"] == "answer text"
    assert out["sql"] == "SELECT 1"
    assert out["attachment_id"] == "a1"
    assert out["suggested"] == ["follow up?"]


def test_extract_clarifying_question():
    msg = {"status": "COMPLETED", "attachments": [{"text": {"content": "Which symbol?"}}]}
    out = extract_answer(msg)
    assert out["text"] == "Which symbol?" and out["sql"] is None


def test_tables_used_finds_fqns():
    sql = "SELECT * FROM fins.meridian.v_returns r JOIN `fins`.`meridian`.dim_security d USING (symbol)"
    tables = tables_used(sql)
    assert "fins.meridian.v_returns" in tables


def test_select_guard():
    assert _SELECT_GUARD.match("SELECT 1")
    assert _SELECT_GUARD.match("  WITH x AS (SELECT 1) SELECT * FROM x")
    assert not _SELECT_GUARD.match("DELETE FROM t")
    assert not _SELECT_GUARD.match("INSERT INTO t SELECT 1")
    assert not _SELECT_GUARD.match("DROP TABLE t")


@pytest.mark.parametrize("bad", ["DELETE FROM t", "SELECT 1; DROP TABLE t", "UPDATE t SET x=1"])
def test_run_readonly_rejects_non_select(bad):
    from app.auth import Identity
    from app.services.sql_exec import run_readonly_sql
    with pytest.raises(ValueError):
        run_readonly_sql(bad, Identity(mode="mock", user="t", token=None))
