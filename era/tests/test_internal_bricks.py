"""
Tests for the internal evidence tools.

The property under test is lineage. An internal answer without lineage is not
verifiable, and the system must degrade honestly rather than tag it `[IV]` anyway -
so the tests care as much about the no-lineage path as the happy one.
"""

from __future__ import annotations

import pytest

from era.tools.internal_bricks import (
    InternalToolError,
    ask_documents,
    extract_tables,
    query_data,
)

SPACE = "space-1"


# ---------------------------------------------------------------------------
# SQL lineage extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sql,expected",
    [
        ("SELECT * FROM alexxx.era_research.ticker_data", ("alexxx.era_research.ticker_data",)),
        ("select a from `alexxx`.`era_research`.`ticker_data` t", ("alexxx.era_research.ticker_data",)),
        (
            "SELECT * FROM main.fin.a JOIN main.fin.b ON a.id = b.id",
            ("main.fin.a", "main.fin.b"),
        ),
        ("SELECT * FROM main.fin.a JOIN main.fin.a x ON 1=1", ("main.fin.a",)),  # deduped
    ],
)
def test_extracts_qualified_tables(sql, expected):
    assert extract_tables(sql) == expected


def test_unqualified_table_names_are_not_reported_as_lineage():
    """
    A bare name cannot be resolved to a catalog and schema without guessing, and a
    guessed lineage would let a claim cite a table that was never read.
    """
    assert extract_tables("SELECT * FROM ticker_data") == ()


def test_subqueries_do_not_produce_keyword_lineage():
    assert extract_tables("SELECT * FROM (SELECT 1) x") == ()


def test_empty_sql_yields_no_lineage():
    assert extract_tables("") == ()


# ---------------------------------------------------------------------------
# Knowledge Assistant
# ---------------------------------------------------------------------------


class FakeServing:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[tuple[str, list[dict]]] = []

    def query(self, endpoint, messages):
        self.calls.append((endpoint, messages))
        return self.payload


def test_ka_answer_and_document_lineage_are_returned():
    client = FakeServing({
        "choices": [{"message": {"content": "The filing cites supply constraints."}}],
        "citations": [{"doc_uri": "/Volumes/x/10K-NVDA-2025.pdf"}],
    })
    result = ask_documents("why?", endpoint="ka-endpoint", client=client)

    assert "supply constraints" in result.answer
    assert result.lineage == ("/Volumes/x/10K-NVDA-2025.pdf",)
    assert result.has_lineage
    assert result.source == "knowledge_assistant"


def test_ka_without_citations_reports_no_lineage():
    """
    The honest-degradation case. An answer with no citation cannot support an
    internal-verified claim, and has_lineage is how the caller learns that.
    """
    client = FakeServing({"choices": [{"message": {"content": "Probably supply."}}]})
    result = ask_documents("why?", endpoint="ka", client=client)

    assert result.answer
    assert result.lineage == ()
    assert not result.has_lineage


def test_ka_lineage_is_found_regardless_of_nesting_depth():
    client = FakeServing({
        "choices": [{"message": {"content": "x"}}],
        "metadata": {"retrieval": {"chunks": [{"document_id": "doc-42"}]}},
    })
    assert ask_documents("q", endpoint="ka", client=client).lineage == ("doc-42",)


def test_ka_with_no_content_raises_rather_than_returning_empty():
    with pytest.raises(InternalToolError):
        ask_documents("q", endpoint="ka", client=FakeServing({"choices": []}))


# ---------------------------------------------------------------------------
# Genie
# ---------------------------------------------------------------------------


class FakeGenie:
    def __init__(self, statuses, sql="SELECT close FROM alexxx.era_research.ticker_data"):
        self.statuses = list(statuses)
        self.sql = sql
        self.polls = 0

    def _message(self, status):
        msg = {"id": "m1", "status": status}
        if status == "COMPLETED":
            msg["attachments"] = [{
                "attachment_id": "a1",
                "query": {"query": self.sql, "description": "Closing prices."},
            }]
        return msg

    def start(self, space_id, content):
        return {"conversation_id": "c1", "message": self._message(self.statuses.pop(0))}

    def get_message(self, space_id, conversation_id, message_id):
        self.polls += 1
        return self._message(self.statuses.pop(0))

    def get_result(self, space_id, conversation_id, message_id, attachment_id):
        return {"statement_response": {
            "manifest": {"schema": {"columns": [{"name": "close"}]}},
            "result": {"data_array": [["145.2"]]},
        }}


def test_genie_returns_sql_rows_and_table_lineage():
    genie = FakeGenie(["EXECUTING_QUERY", "COMPLETED"])
    result = query_data("closing prices?", space_id=SPACE, client=genie, sleep=lambda _: None)

    assert result.source == "genie"
    assert result.lineage == ("alexxx.era_research.ticker_data",)
    assert result.columns == ("close",)
    assert result.rows == (("145.2",),)
    assert "Closing prices" in result.answer
    assert result.has_lineage


def test_genie_polls_until_the_message_settles():
    genie = FakeGenie(["EXECUTING_QUERY", "EXECUTING_QUERY", "COMPLETED"])
    query_data("q", space_id=SPACE, client=genie, sleep=lambda _: None)
    assert genie.polls == 2


def test_genie_failure_raises_rather_than_returning_an_empty_answer():
    genie = FakeGenie(["EXECUTING_QUERY", "FAILED"])
    with pytest.raises(InternalToolError, match="FAILED"):
        query_data("q", space_id=SPACE, client=genie, sleep=lambda _: None)


def test_genie_timeout_is_bounded():
    """A hung Genie query must not hold the turn open indefinitely."""

    class Hanging(FakeGenie):
        def get_message(self, *a, **k):
            return {"id": "m1", "status": "EXECUTING_QUERY"}

    genie = Hanging(["EXECUTING_QUERY"])
    with pytest.raises(InternalToolError, match="did not settle"):
        query_data("q", space_id=SPACE, client=genie, timeout=0.01, sleep=lambda _: None)


def test_genie_without_ids_raises():
    class NoIds:
        def start(self, *a, **k):
            return {}

    with pytest.raises(InternalToolError, match="no ids"):
        query_data("q", space_id=SPACE, client=NoIds(), sleep=lambda _: None)


# ---------------------------------------------------------------------------
# Lineage feeds provenance
# ---------------------------------------------------------------------------

def test_internal_lineage_satisfies_provenance_validation():
    """
    End-to-end coupling: a claim tagged with the lineage Genie reported must
    validate. If these two modules disagree about the identifier format, every
    internal claim fails validation for reasons the model cannot fix.
    """
    from era.agent.provenance import Evidence, check

    genie = FakeGenie(["COMPLETED"])
    result = query_data("q", space_id=SPACE, client=genie, sleep=lambda _: None)

    evidence = Evidence()
    for lineage in result.lineage:
        evidence.add_internal(lineage)

    answer = f"Closing price was $145.20 [IV:{result.lineage[0]}]."
    assert check(answer, evidence).ok
