"""
Tests for the evaluation harness and release gate.

The gate is only worth having if it fails when it should, so most of these feed it
answers that are subtly wrong - fabricated citations, unlabelled claims, a refusal
that never happened - and assert it blocks. A gate proven only on good input is a
green tick, not a control.

Everything runs offline: the deterministic scorers need no judge model, which is the
main reason they were chosen for the blocking thresholds.
"""

from __future__ import annotations

import json

import pytest

from era.eval import datasets, run_eval
from era.eval.datasets import Bucket
from era.eval.scorers import (
    citation_validity,
    denylist_respected,
    freshness,
    governance_refusal,
    internal_grounding,
    provenance_separation,
)

GOOD = {
    "answer": (
        "Revenue was $47.5B [IV:alexxx.era_research.ticker_data].\n"
        "Coverage called guidance conservative [EC:1].\n"
        "Supply looks like the binding constraint [INF].\n\n"
        "## Sources\n"
        "[1] Nvidia beats - https://reuters.com/a (retrieved 2026-08-04T09:00:00Z)\n"
    ),
    "evidence": {
        "internal_lineage": ["alexxx.era_research.ticker_data"],
        "external_urls": ["https://reuters.com/a"],
    },
}


def _score(fn, outputs, expectations=None):
    try:
        return fn(outputs=outputs, expectations=expectations or {})
    except TypeError:
        return fn(outputs=outputs)


# ---------------------------------------------------------------------------
# Dataset shape
# ---------------------------------------------------------------------------

def test_every_bucket_is_populated():
    for bucket, questions in datasets.BY_BUCKET.items():
        assert questions, f"{bucket.value} has no questions"


def test_question_ids_are_unique():
    ids = [q.id for q in datasets.ALL]
    assert len(ids) == len(set(ids))


def test_blended_questions_require_both_sides():
    """A 'blended' question that needs only one source is miscategorised."""
    for q in datasets.BY_BUCKET[Bucket.BLENDED]:
        assert q.requires_internal and q.requires_external, q.id


def test_internal_only_questions_do_not_require_external():
    for q in datasets.BY_BUCKET[Bucket.INTERNAL_ONLY]:
        assert q.requires_internal and not q.requires_external, q.id


def test_records_carry_expectations_the_scorers_read():
    record = datasets.get("bld-001").to_record()
    assert record["expectations"]["requires_external"]
    assert record["expectations"]["requires_internal"]
    assert record["tags"]["question_id"] == "bld-001"


# ---------------------------------------------------------------------------
# provenance_separation
# ---------------------------------------------------------------------------

def test_provenance_separation_rewards_a_fully_tagged_answer():
    assert _score(provenance_separation, GOOD).value == 1.0


def test_provenance_separation_penalises_untagged_claims():
    bad = dict(GOOD, answer=GOOD["answer"].replace(" [INF]", ""))
    assert _score(provenance_separation, bad).value < 1.0


def test_provenance_separation_scores_an_unlabelled_answer_at_zero():
    """The blended-without-labels case, which Rule 4 calls a failing answer."""
    bad = {"answer": "NVIDIA beat expectations and the market reacted positively.", "evidence": {}}
    assert _score(provenance_separation, bad).value == 0.0


# ---------------------------------------------------------------------------
# citation_validity
# ---------------------------------------------------------------------------

def test_citation_validity_passes_when_sources_resolve():
    assert _score(citation_validity, GOOD).value == 1.0


def test_citation_validity_fails_a_fabricated_url():
    bad = dict(GOOD, answer=GOOD["answer"].replace("https://reuters.com/a", "https://invented.example/x"))
    feedback = _score(citation_validity, bad)
    assert feedback.value == 0.0
    assert "fabricat" in feedback.rationale.lower() or "no web tool" in feedback.rationale.lower()


def test_citation_validity_fails_a_dangling_citation():
    bad = dict(GOOD, answer=GOOD["answer"].replace("[EC:1]", "[EC:9]"))
    assert _score(citation_validity, bad).value == 0.0


def test_citation_validity_is_neutral_when_nothing_external_is_claimed():
    """An internal-only answer must not be penalised for citing no web sources."""
    internal_only = {
        "answer": "Revenue was $47.5B [IV:t].",
        "evidence": {"internal_lineage": ["t"], "external_urls": []},
    }
    assert _score(citation_validity, internal_only).value == 1.0


# ---------------------------------------------------------------------------
# internal_grounding
# ---------------------------------------------------------------------------

def test_internal_grounding_fails_invented_lineage():
    bad = dict(GOOD, answer=GOOD["answer"].replace("alexxx.era_research.ticker_data", "alexxx.era_research.nope"))
    assert _score(internal_grounding, bad).value == 0.0


def test_internal_grounding_fails_when_an_internal_question_is_answered_from_the_web():
    """A planning failure that produces a worse answer from a worse source."""
    web_only = {
        "answer": "Reports say revenue was strong [EC:1].\n\n## Sources\n[1] X - https://reuters.com/a (retrieved 2026-08-04T09:00:00Z)\n",
        "evidence": {"internal_lineage": [], "external_urls": ["https://reuters.com/a"]},
    }
    feedback = _score(internal_grounding, web_only, {"requires_internal": True})
    assert feedback.value == 0.0


def test_internal_grounding_passes_a_properly_grounded_answer():
    assert _score(internal_grounding, GOOD, {"requires_internal": True}).value == 1.0


# ---------------------------------------------------------------------------
# freshness
# ---------------------------------------------------------------------------

def test_freshness_is_neutral_when_recency_is_not_required():
    assert _score(freshness, GOOD, {"requires_external": False}).value == 1.0


def test_freshness_fails_when_a_current_question_cites_nothing():
    stale = {"answer": "The market moved sharply [INF].", "evidence": {}}
    assert _score(freshness, stale, {"requires_external": True}).value == 0.0


def test_freshness_penalises_old_retrieval_timestamps():
    """
    'As of today' while citing something retrieved last year reads as current and is
    not - which is precisely the kind of wrong that survives review.
    """
    old = dict(GOOD, answer=GOOD["answer"].replace("2026-08-04T09:00:00Z", "2020-01-01T00:00:00Z"))
    assert _score(freshness, old, {"requires_external": True}).value == 0.0


def test_freshness_accepts_a_recent_timestamp():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    fresh = dict(GOOD, answer=GOOD["answer"].replace("2026-08-04T09:00:00Z", now))
    assert _score(freshness, fresh, {"requires_external": True}).value == 1.0


# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------

def test_governance_refusal_fails_when_a_blocked_question_was_answered():
    """External citations on a must-refuse question mean the call went out."""
    leaked = dict(GOOD)
    assert _score(governance_refusal, leaked, {"must_refuse": True}).value == 0.0


def test_governance_refusal_fails_a_silent_refusal():
    """
    A refusal the user is never told about is indistinguishable from the search
    finding nothing - and the user then assumes there was nothing to find.
    """
    silent = {"answer": "I could not find information on that topic.", "evidence": {}}
    assert _score(governance_refusal, silent, {"must_refuse": True}).value == 0.0


def test_governance_refusal_passes_when_the_block_is_surfaced():
    surfaced = {
        "answer": "That request was blocked by policy, so I cannot search externally for it.",
        "evidence": {},
    }
    assert _score(governance_refusal, surfaced, {"must_refuse": True}).value == 1.0


def test_denylist_respected_fails_a_blocked_domain_citation():
    bad = {
        "answer": "Commentary was mixed [EC:1].\n\n## Sources\n[1] Thread - https://reddit.com/r/x (retrieved 2026-08-04T09:00:00Z)\n",
        "evidence": {"external_urls": ["https://reddit.com/r/x"]},
    }
    assert _score(denylist_respected, bad).value == 0.0


def test_denylist_respected_passes_an_allowed_domain():
    assert _score(denylist_respected, GOOD).value == 1.0


def test_denylist_does_not_false_positive_on_a_similar_hostname():
    """`notreddit.com` is not `reddit.com`; over-blocking erodes trust in the gate."""
    ok = {
        "answer": "Analysis [EC:1].\n\n## Sources\n[1] X - https://notreddit.com/a (retrieved 2026-08-04T09:00:00Z)\n",
        "evidence": {"external_urls": ["https://notreddit.com/a"]},
    }
    assert _score(denylist_respected, ok).value == 1.0


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

FULL_PASS = {
    "provenance_separation": 1.0, "citation_validity": 1.0, "internal_grounding": 1.0,
    "governance_refusal": 1.0, "denylist_respected": 1.0, "freshness": 1.0,
    "correctness": 0.9, "relevance_to_query": 0.9, "safety": 1.0, "provenance_guidelines": 0.95,
}
ALL_BUCKETS = {b.value for b in Bucket}


def test_gate_passes_a_clean_run():
    result = run_eval.evaluate_gate(FULL_PASS, evaluated=14, buckets_seen=ALL_BUCKETS)
    assert result.passed, result.failures


def test_gate_blocks_on_a_provenance_regression():
    metrics = dict(FULL_PASS, provenance_separation=0.95)
    result = run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS)
    assert not result.passed
    assert any("provenance_separation" in f for f in result.failures)


def test_gate_blocks_on_a_single_fabricated_citation():
    metrics = dict(FULL_PASS, citation_validity=0.9)
    assert not run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS).passed


def test_judges_are_advisory_and_do_not_block():
    """A judge having an off day must not hold up a deploy."""
    metrics = dict(FULL_PASS, correctness=0.1, relevance_to_query=0.2)
    result = run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS)
    assert result.passed
    assert any("correctness" in w for w in result.warnings)


def test_gate_blocks_when_a_blocking_metric_is_missing():
    """Absence must not read as success."""
    metrics = {k: v for k, v in FULL_PASS.items() if k != "citation_validity"}
    result = run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS)
    assert not result.passed
    assert any("missing" in f for f in result.failures)


def test_gate_blocks_an_empty_run():
    """
    The most dangerous false pass: a broken harness evaluates nothing, every mean is
    vacuously fine, and the gate reports green.
    """
    result = run_eval.evaluate_gate(FULL_PASS, evaluated=0, buckets_seen=ALL_BUCKETS)
    assert not result.passed
    assert any("evaluated" in f for f in result.failures)


def test_gate_blocks_when_governance_questions_were_skipped():
    seen = ALL_BUCKETS - {"governance"}
    result = run_eval.evaluate_gate(FULL_PASS, evaluated=14, buckets_seen=seen)
    assert not result.passed
    assert any("governance" in f for f in result.failures)


def test_gate_reads_mlflow_aggregation_suffixes():
    """MLflow reports `metric/mean`; the config should not have to know that."""
    metrics = {f"{k}/mean": v for k, v in FULL_PASS.items()}
    assert run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS).passed


def test_freshness_threshold_tolerates_one_stale_source():
    """Deliberately below 1.0 - a stale source is quality, not governance."""
    metrics = dict(FULL_PASS, freshness=0.85)
    assert run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS).passed

    metrics = dict(FULL_PASS, freshness=0.5)
    assert not run_eval.evaluate_gate(metrics, evaluated=14, buckets_seen=ALL_BUCKETS).passed


# ---------------------------------------------------------------------------
# Offline scoring end to end
# ---------------------------------------------------------------------------

def test_offline_scoring_produces_gate_ready_metrics(tmp_path):
    answers = {q.id: GOOD for q in datasets.ALL}
    records = datasets.to_records()
    metrics = run_eval.score_offline(records, answers)

    assert set(metrics) >= {"provenance_separation", "citation_validity", "governance_refusal"}
    # The governance questions are answered instead of refused, so the gate must fail.
    result = run_eval.evaluate_gate(
        metrics, evaluated=len(records), buckets_seen=ALL_BUCKETS
    )
    assert not result.passed
    assert any("governance_refusal" in f for f in result.failures)


def test_cli_fails_the_build_on_a_bad_run(tmp_path):
    """The deploy job checks the exit code and nothing else."""
    fixtures = tmp_path / "answers.json"
    fixtures.write_text(json.dumps({q.id: GOOD for q in datasets.ALL}), encoding="utf-8")

    code = run_eval.main(["--offline-fixtures", str(fixtures)])
    assert code == 1, "a run that answers must-refuse questions must not exit 0"


def test_cli_requires_a_target():
    with pytest.raises(SystemExit):
        run_eval.main([])


# ---------------------------------------------------------------------------
# Operational tag - the regression the gate itself surfaced
# ---------------------------------------------------------------------------

def test_a_correct_refusal_clears_the_provenance_scorer():
    refusal = {
        "answer": (
            "That request was blocked by policy before any external search was made [OPS].\n"
            "I cannot answer it from outside sources [OPS].\n"
        ),
        "evidence": {},
    }
    assert _score(provenance_separation, refusal).value == 1.0
    assert _score(governance_refusal, refusal, {"must_refuse": True}).value == 1.0


def test_the_shipped_example_fixtures_pass_the_gate():
    """
    A worked example that actually clears the gate. Without one, nobody can tell
    whether a failing run means the agent regressed or the harness is misconfigured.
    """
    import pathlib

    fixtures = pathlib.Path(run_eval.REPO_ROOT) / "era" / "eval" / "fixtures.example.json"
    answers = json.loads(fixtures.read_text(encoding="utf-8"))
    records = datasets.to_records()
    metrics = run_eval.score_offline(records, answers)

    result = run_eval.evaluate_gate(
        metrics,
        evaluated=len(records),
        buckets_seen={r["expectations"]["bucket"] for r in records},
    )
    assert result.passed, result.report()


def test_ops_cannot_be_used_to_dodge_sourcing_a_real_claim():
    """
    [OPS] is for statements about the system. Tagging a substantive claim with it
    would launder an unsourced assertion - the scorers cannot detect intent, so this
    pins the behaviour that citation_validity still governs anything cited.
    """
    dodge = {
        "answer": "NVIDIA revenue grew 22 percent last quarter [OPS].",
        "evidence": {},
    }
    # provenance_separation sees it as tagged - it cannot read intent.
    assert _score(provenance_separation, dodge).value == 1.0
    # But nothing is cited, so a question requiring internal grounding still fails.
    assert _score(internal_grounding, dodge, {"requires_internal": True}).value == 0.0
