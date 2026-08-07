"""
Adversarial tests for the egress gate.

The gate is the single control standing between an internal question and a third
party. These tests are written to break it rather than to demonstrate it, because a
gate that has only ever been shown working is a gate nobody has tested.

Where a limitation is real it is asserted as a limitation, not quietly skipped -
a known gap that is written down can be fixed; one that is implied by a passing
suite cannot.
"""

from __future__ import annotations

import pytest

from era.tests.fake_credentials import (
    CREDENTIAL_FIXTURES,
    FAKE_CARD,
    FAKE_DATABRICKS_PAT,
    FAKE_SSN,
)
from era.tools.redaction import (
    InMemoryAuditSink,
    PolicyError,
    Sensitivity,
    audit,
    gate,
    policy_check,
    require,
    scrub,
)


@pytest.fixture
def sink() -> InMemoryAuditSink:
    return InMemoryAuditSink()


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,payload", CREDENTIAL_FIXTURES)
def test_credential_shapes_are_removed(kind, payload):
    result = scrub(f"what is the outlook given {payload} in the config")
    assert payload not in result.text, f"{kind} survived scrubbing"
    assert any(r.kind == kind for r in result.redactions), (
        f"expected a {kind} redaction, got {result.redactions}"
    )


def test_credentials_escalate_sensitivity_regardless_of_caller_claim():
    """
    A caller labelling a query `public` does not make it public.

    This is the important one: sensitivity drives the ZDR refusal, so if a caller
    could under-declare it, the ZDR rule would be advisory.
    """
    result = scrub(f"check {FAKE_DATABRICKS_PAT} against the market")
    assert result.implied_sensitivity is Sensitivity.CONFIDENTIAL


def test_configured_terms_are_removed_case_insensitively():
    result = scrub("how is PROJECT northstar tracking against consensus?")
    assert "northstar" not in result.text.lower()
    assert any(r.kind == "term" for r in result.redactions)


def test_term_matching_respects_word_boundaries():
    """
    'Blue Harbor' must not redact 'Blue Harborough'. Over-redaction mangles real
    queries, which is how people end up disabling the gate.
    """
    result = scrub("Blue Harborough Ltd annual report")
    assert "Blue Harborough" in result.text


# ---------------------------------------------------------------------------
# False positives - the failure mode that gets the gate turned off
# ---------------------------------------------------------------------------

def test_ordinary_domains_are_not_mistaken_for_catalog_names():
    text = "compare coverage on finance.yahoo.com and news.google.com"
    result = scrub(text)
    assert result.text == text, f"mangled a legitimate query: {result.text}"


def test_version_strings_are_not_mistaken_for_catalog_names():
    text = "does this reproduce on 3.11.2 and 1.2.3"
    assert scrub(text).text == text


def test_long_numbers_that_are_not_cards_are_left_alone():
    """13-19 digit numbers are common (order ids, identifiers). Only Luhn-valid ones go."""
    text = "order 1234567890123 shipped and lot 9876543210987654 cleared"
    assert scrub(text).text == text


def test_a_real_card_number_is_removed():
    # Luhn-valid test number.
    result = scrub(f"card {FAKE_CARD} on file")
    assert FAKE_CARD not in result.text
    assert any(r.kind == "card_number" for r in result.redactions)


def test_clean_query_is_untouched_and_reports_clean():
    text = "how did NVIDIA guidance compare to consensus last quarter?"
    result = scrub(text)
    assert result.text == text
    assert result.clean
    assert result.implied_sensitivity is Sensitivity.PUBLIC


def test_scrubbing_is_idempotent():
    """Re-scrubbing must not redact the placeholders it just inserted."""
    once = scrub("mail alex.barreto@entrada.ai now")
    twice = scrub(once.text)
    assert twice.text == once.text
    assert twice.clean


# ---------------------------------------------------------------------------
# Known limitations, asserted so they cannot be forgotten
# ---------------------------------------------------------------------------

def test_limitation_obfuscated_identifiers_are_not_caught():
    """
    Deliberately spaced or unicode-substituted identifiers defeat regex detection.
    Structural scrubbing is a safety net for accidents, not a defence against a
    determined insider - that is what the sensitivity/ZDR refusal is for.
    """
    result = scrub("mail alex dot barreto at entrada dot ai")
    assert result.clean, "if this now passes, tighten the limitation note in redaction.py"


# ---------------------------------------------------------------------------
# ZDR policy
# ---------------------------------------------------------------------------

def test_public_queries_are_allowed_to_a_non_zdr_endpoint():
    assert policy_check("research", Sensitivity.PUBLIC).allowed


def test_internal_queries_are_refused_while_account_zdr_is_unconfirmed():
    """
    Shipped default is account_enabled: false, so nothing above `public` may leave -
    including to /v1/search, which You.com covers only once the ACCOUNT has ZDR.
    A per-endpoint flag alone must not be enough to permit it.
    """
    for endpoint in ("search", "contents", "research", "finance_research"):
        decision = policy_check(endpoint, Sensitivity.INTERNAL)
        assert not decision.allowed, f"{endpoint} leaked an internal query"
        assert "ZDR" in decision.reason or "zdr" in decision.reason


def test_confidential_never_reaches_research_endpoints():
    for endpoint in ("research", "finance_research", "contents"):
        assert not policy_check(endpoint, Sensitivity.CONFIDENTIAL).allowed


def test_unknown_endpoint_is_refused():
    """Fail closed: an endpoint nobody declared has no policy, so it gets no traffic."""
    decision = policy_check("v1_something_new", Sensitivity.PUBLIC)
    assert not decision.allowed
    assert "unknown endpoint" in decision.reason


def test_invalid_domain_mode_is_refused():
    assert not policy_check("search", Sensitivity.PUBLIC, domain_mode="everything").allowed


def test_domain_mode_selects_the_matching_list():
    deny = policy_check("search", Sensitivity.PUBLIC, domain_mode="deny")
    allow = policy_check("search", Sensitivity.PUBLIC, domain_mode="allow")
    assert "reddit.com" in deny.domains
    assert "sec.gov" in allow.domains
    assert not set(deny.domains) & set(allow.domains)


# ---------------------------------------------------------------------------
# End-to-end gate behaviour
# ---------------------------------------------------------------------------

def test_gate_escalates_then_refuses_a_query_the_caller_called_public(sink):
    """The two halves composed: scrubbing finds a token, and the refusal follows."""
    decision = gate(
        f"summarise sentiment, ignore {FAKE_DATABRICKS_PAT}",
        endpoint="research",
        sensitivity=Sensitivity.PUBLIC,
        sink=sink,
    )
    assert not decision.allowed
    assert decision.sensitivity is Sensitivity.CONFIDENTIAL


def test_require_raises_instead_of_returning_falsy(sink):
    with pytest.raises(PolicyError):
        require("q", endpoint="research", sensitivity=Sensitivity.CONFIDENTIAL, sink=sink)


def test_refused_calls_are_still_audited(sink):
    """A refusal is exactly the event you most want a record of."""
    gate("q", endpoint="research", sensitivity=Sensitivity.CONFIDENTIAL, sink=sink)
    assert len(sink.records) == 1
    assert sink.records[0].allowed is False


def test_decision_is_falsy_when_refused(sink):
    assert not gate("q", "research", sensitivity=Sensitivity.CONFIDENTIAL, sink=sink)
    assert gate("q", "search", sensitivity=Sensitivity.PUBLIC, sink=sink)


# ---------------------------------------------------------------------------
# The audit trail must not become the leak
# ---------------------------------------------------------------------------

def test_audit_record_contains_no_query_text(sink):
    secret_query = "what is the outlook for Project Northstar and alex.barreto@entrada.ai"
    gate(secret_query, endpoint="search", sink=sink)

    record = sink.records[0]
    blob = " ".join(str(v) for v in record.as_row().values())

    for fragment in ("Northstar", "alex.barreto", "entrada.ai", "outlook"):
        assert fragment not in blob, f"audit row leaked {fragment!r}"


def test_audit_hashes_distinguish_queries_but_do_not_reveal_them(sink):
    gate("question one", endpoint="search", sink=sink)
    gate("question two", endpoint="search", sink=sink)

    a, b = sink.records
    assert a.query_sha256 != b.query_sha256
    assert len(a.query_sha256) == 64
    assert "question" not in a.query_sha256


def test_audit_records_what_was_redacted_without_the_values(sink):
    gate("mail alex.barreto@entrada.ai about Project Northstar", endpoint="search", sink=sink)
    counts = sink.records[0].redaction_counts
    assert counts.get("email") == 1
    assert counts.get("term") == 1
    assert all(isinstance(v, int) for v in counts.values())


def test_scrubbed_hash_differs_from_original_when_something_was_removed(sink):
    """Proves the call that went out was not the call that came in."""
    gate("contact alex.barreto@entrada.ai", endpoint="search", sink=sink)
    record = sink.records[0]
    assert record.query_sha256 != record.scrubbed_sha256


def test_identical_queries_hash_identically_for_correlation(sink):
    gate("same question", endpoint="search", sink=sink)
    gate("same question", endpoint="search", sink=sink)
    assert sink.records[0].query_sha256 == sink.records[1].query_sha256


def test_audit_record_has_no_field_that_could_hold_raw_text():
    """
    Structural guarantee rather than a behavioural one: if no field can hold the
    query, no future edit can accidentally start storing it.
    """
    from era.tools.redaction import AuditRecord

    allowed = {
        "ts", "endpoint", "allowed", "reason", "query_sha256", "scrubbed_sha256",
        "redaction_counts", "sensitivity", "domain_mode", "zdr_covered",
        "principal", "cost_usd", "latency_ms", "request_id",
    }
    assert set(AuditRecord.__dataclass_fields__) == allowed, (
        "AuditRecord gained or lost a field - confirm the new shape cannot carry "
        "query or response text before updating this test"
    )


# ---------------------------------------------------------------------------
# Escalation policy: redaction that neutralises vs redaction that signals
# ---------------------------------------------------------------------------

def test_contact_details_are_removed_without_escalating(sink):
    """
    Stripping an email genuinely neutralises it, and the remaining question is
    ordinary. Escalating here would refuse the call *after* successfully cleaning
    it - which makes redaction pointless and teaches people to route around the gate.
    """
    result = scrub("outlook for holdings managed by alex.barreto@entrada.ai")
    assert "alex.barreto" not in result.text
    assert result.implied_sensitivity is Sensitivity.PUBLIC

    decision = gate("outlook for alex.barreto@entrada.ai holdings", endpoint="search", sink=sink)
    assert decision.allowed, "a scrubbed contact detail must not block an ordinary query"


def test_credentials_escalate_and_therefore_refuse(sink):
    """The opposite case: presence signals the subject is sensitive, not just the token."""
    decision = gate(
        f"audit {FAKE_DATABRICKS_PAT} usage", endpoint="search", sink=sink
    )
    assert not decision.allowed
    assert decision.sensitivity is Sensitivity.CONFIDENTIAL


def test_configured_terms_escalate_because_asking_is_the_disclosure(sink):
    decision = gate("how is Project Northstar tracking", endpoint="search", sink=sink)
    assert not decision.allowed


def test_regulated_identifiers_escalate(sink):
    for payload in (FAKE_SSN, FAKE_CARD):
        assert not gate(f"reconcile {payload} against the ledger", endpoint="search", sink=sink).allowed


def test_internal_topology_is_stripped_without_refusing(sink):
    """A schema name is worth removing, but its removal leaves a usable question."""
    decision = gate("compare figures in main.finance.revenue to consensus", endpoint="search", sink=sink)
    assert decision.allowed
    assert "main.finance.revenue" not in decision.scrubbed_query


# ---------------------------------------------------------------------------
# Audit sinks
# ---------------------------------------------------------------------------

class _FakeStatementExecution:
    def __init__(self):
        self.calls = []

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return None


class _FakeWorkspace:
    def __init__(self):
        self.statement_execution = _FakeStatementExecution()


def test_audit_ddl_columns_track_the_record_shape():
    """
    The DDL, both sinks and every query share one column list. If AuditRecord gains
    a field without the DDL following, writes fail at runtime in production only.
    """
    from era.tools.redaction import AUDIT_COLUMNS, AuditRecord

    assert [name for name, _ in AUDIT_COLUMNS] == list(AuditRecord.__dataclass_fields__)


def test_warehouse_sink_writes_a_parameterised_insert_with_no_query_text(sink):
    from era.tools.redaction import SqlWarehouseAuditSink

    w = _FakeWorkspace()
    warehouse_sink = SqlWarehouseAuditSink("alexxx", "era_research", "wh-1", workspace_client=w)

    gate("outlook for Project Northstar and alex.barreto@entrada.ai",
         endpoint="search", sink=warehouse_sink)

    assert len(w.statement_execution.calls) == 1
    call = w.statement_execution.calls[0]

    # The statement is all placeholders - no interpolated values at all.
    assert "INSERT INTO alexxx.era_research.egress_audit" in call["statement"]
    for fragment in ("Northstar", "alex.barreto", "entrada.ai", "outlook"):
        assert fragment not in call["statement"]
        assert all(fragment not in str(p.value) for p in call["parameters"])


def test_warehouse_sink_survives_the_all_null_common_case():
    """
    A clean call has no redactions, no cost, no latency and no request id. That is
    the COMMON path, and it is the one schema inference cannot type - hence explicit
    types on every null parameter.
    """
    from era.tools.redaction import AuditRecord, SqlWarehouseAuditSink

    w = _FakeWorkspace()
    SqlWarehouseAuditSink("c", "s", "wh-1", workspace_client=w).write(
        AuditRecord(
            ts="2026-08-05T00:00:00Z", endpoint="search", allowed=True, reason="ok",
            query_sha256="a" * 64, scrubbed_sha256="a" * 64, redaction_counts={},
            sensitivity="public", domain_mode="deny", zdr_covered=False,
            principal="sp", cost_usd=None, latency_ms=None, request_id=None,
        )
    )
    params = {p.name: p for p in w.statement_execution.calls[0]["parameters"]}
    for nullable in ("cost_usd", "latency_ms", "request_id"):
        assert params[nullable].value is None
        assert params[nullable].type, f"{nullable} needs an explicit type when null"


def test_warehouse_sink_keeps_redaction_counts_a_typed_map():
    """JSON on the wire, MAP in the table - the transport must not degrade the column."""
    from era.tools.redaction import SqlWarehouseAuditSink

    w = _FakeWorkspace()
    s = SqlWarehouseAuditSink("c", "s", "wh-1", workspace_client=w)
    gate("mail alex.barreto@entrada.ai", endpoint="search", sink=s)

    call = w.statement_execution.calls[0]
    assert "from_json(:redaction_counts, 'MAP<STRING, INT>')" in call["statement"]
    counts = next(p for p in call["parameters"] if p.name == "redaction_counts")
    assert '"email": 1' in counts.value or '"email":1' in counts.value


def test_warehouse_sink_passes_sdk_parameter_objects_not_dicts():
    """
    execute_statement calls .as_dict() on every parameter, so dicts raise
    "'dict' object has no attribute 'as_dict'". That failure surfaced as the audit
    write blowing up before any egress decision could be recorded, which in turn
    made the governance questions score as unrefused - the gate had never been
    reached. Pin the type so it cannot regress to dicts.
    """
    from databricks.sdk.service.sql import StatementParameterListItem
    from era.tools.redaction import SqlWarehouseAuditSink

    w = _FakeWorkspace()
    gate("a clean question about market conditions", endpoint="search",
         sink=SqlWarehouseAuditSink("c", "s", "wh-1", workspace_client=w))

    params = w.statement_execution.calls[0]["parameters"]
    assert params, "no parameters were bound"
    for p in params:
        assert isinstance(p, StatementParameterListItem), f"got {type(p).__name__}, expected SDK object"
        assert hasattr(p, "as_dict"), "the SDK requires objects exposing as_dict()"
