"""
Tests for the You.com tool wrappers.

No network, no API key, no five-minute waits: transport and SQL execution are both
injected. What is actually being tested is the contract with You.com's documented
behaviour - the asymmetries that are easy to get wrong and expensive to discover in
production.
"""

from __future__ import annotations

import json

import pytest

from era.tests.fake_credentials import FAKE_DATABRICKS_PAT
from era.tools import you_fast, you_research
from era.tools.redaction import InMemoryAuditSink, PolicyError, Sensitivity
from era.tools.you_research import Effort, ResearchError, TaskStatus

CATALOG, SCHEMA = "alexxx", "era_research"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv(you_research.SECRET_ENV, "test-key-not-real")


@pytest.fixture
def sink() -> InMemoryAuditSink:
    return InMemoryAuditSink()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeSql:
    """Records the statement and parameters, returns a canned payload."""

    def __init__(self, payload):
        self.payload = payload
        self.statements: list[str] = []
        self.params: list[list[dict]] = []

    def scalar(self, statement: str, params: list[dict]) -> str:
        self.statements.append(statement)
        self.params.append(params)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class FakeTransport:
    def __init__(self, post=None, get=None):
        self._post = post or (200, {})
        self._get = get or (200, {})
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def post(self, url, json, headers, timeout):
        self.posts.append((url, json))
        return self._post

    def get(self, url, headers, timeout):
        self.gets.append(url)
        return self._get


SEARCH_PAYLOAD = {
    "results": {
        "web": [{
            "url": "https://reuters.com/a", "title": "A", "description": "d",
            "page_age": "2026-08-01T00:00:00Z",
        }],
        "news": [{"url": "https://ft.com/b", "title": "B", "description": "n"}],
    },
    "metadata": {"search_uuid": "x", "latency": 0.4},
}


# ---------------------------------------------------------------------------
# Fast tier
# ---------------------------------------------------------------------------

def test_search_returns_web_and_news_from_one_call(sink):
    sql = FakeSql(SEARCH_PAYLOAD)
    resp = you_fast.search("nvidia earnings", catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink)

    assert len(resp.results) == 2
    assert resp.urls == {"https://reuters.com/a", "https://ft.com/b"}
    assert len(resp.news) == 1, "news must come back from the same search call"


def test_search_stamps_retrieval_time_on_every_result(sink):
    """
    The provenance format requires retrieved_at on every external citation, and
    You.com does not return one - so we stamp it. page_age is the article's own
    date and is not a substitute.
    """
    resp = you_fast.search("q", catalog=CATALOG, schema=SCHEMA, executor=FakeSql(SEARCH_PAYLOAD), sink=sink)
    assert all(r.retrieved_at.endswith("Z") for r in resp.results)


def test_search_passes_the_scrubbed_query_not_the_original(sink):
    """The whole point of the gate: what leaves is not what came in."""
    sql = FakeSql(SEARCH_PAYLOAD)
    you_fast.search(
        "outlook for alex.barreto@entrada.ai holdings",
        catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink,
    )
    sent = next(p["value"] for p in sql.params[0] if p["name"] == "q")
    assert "alex.barreto@entrada.ai" not in sent
    assert "REDACTED" in sent


def test_search_uses_parameter_binding_not_string_interpolation(sink):
    """A query is user-controlled text heading for a SQL statement. Bind it."""
    sql = FakeSql(SEARCH_PAYLOAD)
    nasty = "'); DROP TABLE users; --"
    you_fast.search(nasty, catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink)

    assert nasty not in sql.statements[0], "query text was interpolated into SQL"
    assert ":q" in sql.statements[0]


def test_supplying_include_domains_switches_the_call_to_allow_mode(sink):
    sql = FakeSql(SEARCH_PAYLOAD)
    resp = you_fast.search(
        "q", catalog=CATALOG, schema=SCHEMA, executor=sql,
        include_domains="sec.gov", sink=sink,
    )
    assert resp.domain_mode == "allow"


def test_error_envelope_from_the_uc_function_is_raised_not_swallowed(sink):
    """An empty result on failure reads as 'the web had nothing to say'."""
    sql = FakeSql({"era_error": "You.com search returned HTTP 429", "body": "slow down"})
    with pytest.raises(you_fast.ToolError, match="429"):
        you_fast.search("q", catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink)


def test_non_json_response_is_raised_not_swallowed(sink):
    with pytest.raises(you_fast.ToolError, match="non-JSON"):
        you_fast.search("q", catalog=CATALOG, schema=SCHEMA, executor=FakeSql("<html>502</html>"), sink=sink)


def test_gate_refusal_prevents_the_warehouse_call_entirely(sink):
    """A refused call must not reach the warehouse, never mind You.com."""
    sql = FakeSql(SEARCH_PAYLOAD)
    with pytest.raises(PolicyError):
        you_fast.search(
            "q", catalog=CATALOG, schema=SCHEMA, executor=sql,
            sensitivity=Sensitivity.CONFIDENTIAL, sink=sink,
        )
    assert sql.statements == [], "statement was executed despite the refusal"


def test_contents_audits_the_urls_because_they_are_the_payload(sink):
    sql = FakeSql([{"url": "https://reuters.com/a", "title": "A", "markdown": "# A"}])
    out = you_fast.contents(
        ["https://reuters.com/a"], catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink
    )
    assert out[0].markdown == "# A"
    assert sink.records and sink.records[0].endpoint == "contents"


def test_contents_with_no_urls_makes_no_call(sink):
    sql = FakeSql([])
    assert you_fast.contents([], catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink) == ()
    assert sql.statements == []


# ---------------------------------------------------------------------------
# Slow tier - Research
# ---------------------------------------------------------------------------

def test_submit_always_requests_background_mode(sink):
    """
    Holding a chat turn open for a p50 of 300s is not a behaviour worth having, so
    background is unconditional rather than a caller decision.
    """
    transport = FakeTransport(post=(200, {"task_id": "t-1", "status": "queued"}))
    task = you_research.submit_research("q", transport=transport, sink=sink)

    _, body = transport.posts[0]
    assert body["background"] is True
    assert task.task_id == "t-1"
    assert task.status is TaskStatus.QUEUED
    assert not task.settled


def test_submit_sends_the_scrubbed_query(sink):
    """
    Contact details are neutralised by removal, so the call proceeds with the
    identifier stripped. This is the scrub-and-send path; scrub-and-refuse is next.
    """
    transport = FakeTransport(post=(200, {"task_id": "t-1", "status": "queued"}))
    you_research.submit_research(
        "what is the market view on holdings managed by alex.barreto@entrada.ai",
        sensitivity=Sensitivity.PUBLIC, transport=transport, sink=sink,
    )
    _, body = transport.posts[0]
    assert "alex.barreto@entrada.ai" not in body["input"]
    assert "REDACTED" in body["input"]


def test_configured_codename_is_refused_rather_than_hollowed_out(sink):
    """
    Redacting a codename leaves "how is [REDACTED:term] viewed" - a query that
    discloses that someone is researching the codename while being useless as a
    search. Refusing is the honest outcome.
    """
    transport = FakeTransport(post=(200, {"task_id": "t-1", "status": "queued"}))
    with pytest.raises(PolicyError):
        you_research.submit_research(
            "how is Project Northstar viewed externally", transport=transport, sink=sink
        )
    assert transport.posts == []


def test_credential_in_a_research_query_is_refused_before_egress(sink):
    """Research is not ZDR-covered; a query carrying a token must never leave."""
    transport = FakeTransport(post=(200, {"task_id": "t-1", "status": "queued"}))
    with pytest.raises(PolicyError):
        you_research.submit_research(
            f"review {FAKE_DATABRICKS_PAT} exposure",
            transport=transport, sink=sink,
        )
    assert transport.posts == [], "request was sent despite the refusal"


def test_oversized_input_is_rejected_before_the_gate(sink):
    with pytest.raises(ResearchError, match="40000|40_000|character limit"):
        you_research.submit_research("x" * 40_001, sink=sink)


def test_poll_returns_unsettled_while_running(sink):
    transport = FakeTransport(get=(200, {"status": "running", "result": None}))
    task = you_research.poll_research("t-1", transport=transport)
    assert task.status is TaskStatus.RUNNING
    assert not task.settled
    assert task.result is None


def test_poll_normalises_a_completed_result_with_citations():
    transport = FakeTransport(get=(200, {
        "status": "completed",
        "result": {
            "output": {
                "content": "Findings [1].",
                "content_type": "text",
                "sources": [
                    {"url": "https://reuters.com/x", "title": "X", "snippets": ["s"]},
                    {"url": "https://ft.com/y", "title": "Y"},
                ],
            },
            "warnings": ["partial coverage"],
        },
    }))
    task = you_research.poll_research("t-1", transport=transport)

    assert task.settled and task.status is TaskStatus.COMPLETED
    result = task.result
    assert result.answer_md == "Findings [1]."
    assert [c.n for c in result.citations] == [1, 2]
    assert result.urls == {"https://reuters.com/x", "https://ft.com/y"}
    assert all(c.retrieved_at.endswith("Z") for c in result.citations)
    assert result.warnings == ("partial coverage",)


def test_failed_task_is_settled_and_carries_the_error():
    transport = FakeTransport(get=(200, {"status": "failed", "error": "upstream timeout"}))
    task = you_research.poll_research("t-1", transport=transport)
    assert task.settled
    assert task.error == "upstream timeout"
    assert task.result is None


def test_sources_without_a_url_are_dropped():
    """A citation with no URL cannot be resolved by provenance, so it must not exist."""
    transport = FakeTransport(get=(200, {
        "status": "completed",
        "result": {"output": {"content": "x", "sources": [{"title": "no url"}, {"url": "https://a.com"}]}},
    }))
    task = you_research.poll_research("t-1", transport=transport)
    assert [c.url for c in task.result.citations] == ["https://a.com"]


def test_http_error_on_submit_is_raised(sink):
    transport = FakeTransport(post=(422, {"detail": "frontier requires background"}))
    with pytest.raises(ResearchError, match="422"):
        you_research.submit_research("q", transport=transport, sink=sink)


def test_submit_without_a_task_id_is_an_error(sink):
    transport = FakeTransport(post=(200, {"status": "queued"}))
    with pytest.raises(ResearchError, match="no task_id"):
        you_research.submit_research("q", transport=transport, sink=sink)


# ---------------------------------------------------------------------------
# Slow tier - Finance Research asymmetry
# ---------------------------------------------------------------------------

def test_finance_research_rejects_efforts_the_endpoint_does_not_accept(sink):
    """Finance Research documents deep and exhaustive only."""
    for bad in (Effort.LITE, Effort.STANDARD, Effort.FRONTIER):
        with pytest.raises(ResearchError, match="deep"):
            you_research.finance_research("q", effort=bad, sink=sink)


def test_finance_research_never_sends_a_background_flag(sink):
    """
    The endpoint documents no background flag. Sending one anyway would be guessing
    at an undocumented API, and the whole async design here exists because it is absent.
    """
    transport = FakeTransport(post=(200, {"output": {"content": "x", "sources": []}}))
    you_research.finance_research("q", effort=Effort.DEEP, transport=transport, sink=sink)

    _, body = transport.posts[0]
    assert "background" not in body
    assert set(body) == {"input", "research_effort"}


def test_only_research_supports_background_per_the_policy_file():
    """Pins the asymmetry that drives the worker design."""
    import yaml
    from era.tools.redaction import CONF_DIR

    endpoints = yaml.safe_load((CONF_DIR / "routing_policy.yaml").read_text())["endpoints"]
    assert endpoints["research"]["supports_background"] is True
    assert endpoints["finance_research"]["supports_background"] is False


def test_missing_api_key_fails_loudly(monkeypatch, sink):
    monkeypatch.delenv(you_research.SECRET_ENV, raising=False)
    transport = FakeTransport(post=(200, {"task_id": "t", "status": "queued"}))
    with pytest.raises(ResearchError, match=you_research.SECRET_ENV):
        you_research.submit_research("q", transport=transport, sink=sink)


# ---------------------------------------------------------------------------
# Billing state must be legible, not just a status code
# ---------------------------------------------------------------------------

def test_402_on_research_names_the_cause_not_just_the_status(sink):
    """
    402 is the one failure that looks like a broken key but isn't. If the error
    says only "HTTP 402" the next person debugs the connection, the secret and the
    header before finding the billing page.
    """
    transport = FakeTransport(post=(402, {"error": "payment_required"}))
    with pytest.raises(ResearchError) as exc:
        you_research.submit_research("q", transport=transport, sink=sink)

    message = str(exc.value).lower()
    assert "402" in message
    assert "balance" in message or "credit" in message
    assert "you.com/platform" in message


def test_402_from_the_uc_function_names_the_cause(sink):
    sql = FakeSql({"era_error": "You.com search returned HTTP 402", "body": "payment_required"})
    with pytest.raises(you_fast.ToolError) as exc:
        you_fast.search("q", catalog=CATALOG, schema=SCHEMA, executor=sql, sink=sink)

    message = str(exc.value).lower()
    assert "402" in message
    assert "balance" in message or "credit" in message


def test_401_is_still_reported_as_a_credential_problem(sink):
    """The distinction only helps if 401 does NOT get the billing wording."""
    transport = FakeTransport(post=(401, {"error": "unauthorized"}))
    with pytest.raises(ResearchError) as exc:
        you_research.submit_research("q", transport=transport, sink=sink)
    assert "balance" not in str(exc.value).lower()
