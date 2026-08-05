"""
Tests for claim tagging and citation validation.

The cases that matter here are the dishonest ones. An answer that cites correctly is
easy; the module earns its place by catching answers that *look* well-sourced -
fabricated URLs, citations pointing at nothing, inference dressed up as verified
fact - because those are strictly more dangerous than an obviously unsourced answer.
"""

from __future__ import annotations

import pytest

from era.agent.provenance import (
    Evidence,
    Tag,
    ViolationKind,
    check,
    parse_answer,
)

GOOD_ANSWER = """\
NVIDIA reported data centre revenue of $47.5B last quarter [IV:alexxx.era_research.ticker_data].
Analysts covering the print described the guidance as conservative [EC:1].
Taken together, the setup implies continued share gains into next year [INF].

## Sources
[1] Nvidia beats on datacentre demand - https://reuters.com/tech/nvidia-q3 (retrieved 2026-08-04T09:15:00Z)
"""


@pytest.fixture
def evidence() -> Evidence:
    ev = Evidence()
    ev.add_internal("alexxx.era_research.ticker_data")
    ev.add_external("https://reuters.com/tech/nvidia-q3")
    return ev


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parses_each_tag_kind():
    parsed = parse_answer(GOOD_ANSWER)
    tags = [c.tag for c in parsed.claims]
    assert Tag.INTERNAL_VERIFIED in tags
    assert Tag.EXTERNAL_CITED in tags
    assert Tag.INFERRED in tags


def test_parses_sources_with_timestamp():
    parsed = parse_answer(GOOD_ANSWER)
    assert len(parsed.sources) == 1
    source = parsed.sources[0]
    assert source.index == 1
    assert source.url == "https://reuters.com/tech/nvidia-q3"
    assert source.retrieved_at == "2026-08-04T09:15:00Z"


def test_tags_are_stripped_from_the_claim_text():
    """The tag is metadata; it must not end up rendered in the prose."""
    parsed = parse_answer(GOOD_ANSWER)
    assert all("[IV:" not in c.text and "[EC:" not in c.text for c in parsed.claims)


def test_headings_and_questions_are_not_treated_as_claims():
    parsed = parse_answer("## Summary\nWhat does this mean for margins?\n")
    assert parsed.claims == ()


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------

def test_a_well_formed_answer_passes(evidence):
    report = check(GOOD_ANSWER, evidence)
    assert report.ok, report.violations
    assert report.citation_coverage == 1.0
    assert report.counts["internal-verified"] == 1
    assert report.counts["external-cited"] == 1
    assert report.counts["inferred"] == 1


# ---------------------------------------------------------------------------
# Dishonest answers
# ---------------------------------------------------------------------------

def test_fabricated_url_is_caught(evidence):
    """
    The central case. The answer is well-formed, the citation is numbered, the
    Sources block is present - and the URL is somewhere no tool ever went.
    """
    answer = GOOD_ANSWER.replace(
        "https://reuters.com/tech/nvidia-q3", "https://bloomberg.com/invented-article"
    )
    report = check(answer, evidence)
    assert not report.ok
    assert any(v.kind is ViolationKind.FABRICATED_SOURCE for v in report.violations)


def test_citation_pointing_at_a_missing_source_is_caught(evidence):
    answer = GOOD_ANSWER.replace("[EC:1]", "[EC:7]")
    report = check(answer, evidence)
    assert not report.ok
    assert any(v.kind is ViolationKind.DANGLING_CITATION for v in report.violations)


def test_invented_internal_lineage_is_caught(evidence):
    """Claiming a table the query never touched is fabrication with a lakehouse accent."""
    answer = GOOD_ANSWER.replace(
        "[IV:alexxx.era_research.ticker_data]", "[IV:alexxx.era_research.secret_forecasts]"
    )
    report = check(answer, evidence)
    assert not report.ok
    assert any(v.kind is ViolationKind.UNKNOWN_LINEAGE for v in report.violations)


def test_untagged_claim_fails_the_answer(evidence):
    """Rule 4: unlabelled blended output is a failing answer, not a warning."""
    answer = GOOD_ANSWER.replace(" [INF]", "")
    report = check(answer, evidence)
    assert not report.ok
    assert any(v.kind is ViolationKind.UNTAGGED_CLAIM for v in report.violations)
    assert report.citation_coverage < 1.0


def test_entirely_untagged_answer_scores_zero_coverage(evidence):
    answer = "NVIDIA had a very strong quarter and the outlook remains constructive."
    report = check(answer, evidence)
    assert not report.ok
    assert report.citation_coverage == 0.0


def test_malformed_sources_entry_is_reported(evidence):
    answer = GOOD_ANSWER.replace(
        "[1] Nvidia beats on datacentre demand - https://reuters.com/tech/nvidia-q3 (retrieved 2026-08-04T09:15:00Z)",
        "Reuters said some things",
    )
    report = check(answer, evidence)
    assert not report.ok
    assert any(v.kind is ViolationKind.MALFORMED_SOURCE for v in report.violations)


def test_listed_but_uncited_source_is_flagged_without_failing(evidence):
    """
    Padding the Sources block inflates apparent rigour. Worth surfacing, but it does
    not make the claims wrong, so it must not fail an otherwise sound answer.
    """
    evidence.add_external("https://ft.com/unused")
    answer = GOOD_ANSWER.replace(
        "## Sources",
        "## Sources\n[2] Unused - https://ft.com/unused (retrieved 2026-08-04T09:15:00Z)",
    )
    report = check(answer, evidence)
    assert any(v.kind is ViolationKind.UNUSED_SOURCE for v in report.violations)
    assert report.ok, "an uncited extra source must not fail the answer"


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_url_normalisation_tolerates_trailing_slash_and_fragment(evidence):
    answer = GOOD_ANSWER.replace(
        "https://reuters.com/tech/nvidia-q3", "https://reuters.com/tech/nvidia-q3/#results"
    )
    assert check(answer, evidence).ok, "trailing slash or fragment must not read as a different source"


def test_multiple_tags_on_one_line_are_all_resolved(evidence):
    """A sentence blending internal and external evidence must resolve both."""
    answer = (
        "Revenue rose 22% [IV:alexxx.era_research.ticker_data] which analysts attributed "
        "to datacentre demand [EC:1].\n\n"
        "## Sources\n"
        "[1] Nvidia beats - https://reuters.com/tech/nvidia-q3 (retrieved 2026-08-04T09:15:00Z)\n"
    )
    report = check(answer, evidence)
    assert report.ok, report.violations
    assert report.counts["internal-verified"] == 1
    assert report.counts["external-cited"] == 1


def test_empty_answer_does_not_crash_or_falsely_pass():
    report = check("", Evidence())
    assert report.citation_coverage == 1.0  # nothing claimed, nothing unsupported
    assert report.counts["untagged"] == 0


def test_draft_mode_tolerates_untagged_but_still_catches_fabrication(evidence):
    """
    The critique node wants a report on a draft without failing it for missing tags -
    but a fabricated citation must fail even in draft, because that is not something
    a later pass will fix.
    """
    untagged = GOOD_ANSWER.replace(" [INF]", "")
    assert check(untagged, evidence, require_full_coverage=False).ok

    fabricated = GOOD_ANSWER.replace(
        "https://reuters.com/tech/nvidia-q3", "https://example.com/made-up"
    )
    assert not check(fabricated, evidence, require_full_coverage=False).ok


# ---------------------------------------------------------------------------
# Prompt / parser coupling
# ---------------------------------------------------------------------------

def test_the_prompts_worked_example_actually_validates():
    """
    The synthesis prompt teaches a format by example. If the parser cannot validate
    that very example, the agent fails every answer for a reason the model was never
    told - the worst kind of bug, because the model's output looks correct.
    """
    from era.agent.prompts import EXAMPLE_ANSWER

    ev = Evidence()
    ev.add_internal("main.finance.ticker_data")
    ev.add_external("https://reuters.com/tech/nvidia-q3")

    report = check(EXAMPLE_ANSWER, ev)
    assert report.ok, f"the prompt's own example fails validation: {report.violations}"
    assert report.citation_coverage == 1.0
    assert report.counts["internal-verified"] == 1
    assert report.counts["external-cited"] == 1
    assert report.counts["inferred"] == 1


def test_every_tag_kind_is_documented_in_the_contract():
    """A tag the parser accepts but the prompt never mentions will never be produced."""
    from era.agent.prompts import PROVENANCE_CONTRACT

    for token in ("[IV:", "[EC:", "[INF]"):
        assert token in PROVENANCE_CONTRACT, f"{token} is unreachable - not in the prompt"
    assert "## Sources" in PROVENANCE_CONTRACT


def test_synthesis_prompt_embeds_the_contract_and_the_example():
    from era.agent.prompts import EXAMPLE_ANSWER, PROVENANCE_CONTRACT, SYNTHESIS_PROMPT

    assert PROVENANCE_CONTRACT in SYNTHESIS_PROMPT
    assert EXAMPLE_ANSWER in SYNTHESIS_PROMPT


# ---------------------------------------------------------------------------
# Operational statements
# ---------------------------------------------------------------------------

def test_operational_statements_are_valid_without_evidence():
    """
    "That request was blocked by policy" is a statement about the system, not a claim
    about the world. It needs no source and must not count as unlabelled.
    """
    answer = "That request was blocked by policy, so I did not search externally [OPS]."
    report = check(answer, Evidence())

    assert report.ok
    assert report.citation_coverage == 1.0
    assert report.counts["operational"] == 1
    assert report.counts["untagged"] == 0


def test_a_correct_refusal_scores_as_well_as_a_normal_answer(evidence):
    """
    The regression that motivated the tag: without [OPS] an agent that correctly
    refused scored WORSE on provenance than one that answered, so the release gate
    blocked deploys for doing the right thing.
    """
    refusal = (
        "That request was blocked by policy before any external search was made [OPS].\n"
        "I cannot answer it from outside sources [OPS].\n"
    )
    assert check(refusal, Evidence()).citation_coverage == 1.0
    assert check(GOOD_ANSWER, evidence).citation_coverage == 1.0


def test_ops_is_documented_in_the_prompt_contract():
    from era.agent.prompts import PROVENANCE_CONTRACT

    assert "[OPS]" in PROVENANCE_CONTRACT
    assert "not a way to avoid sourcing" in PROVENANCE_CONTRACT.lower() or "nothing else" in PROVENANCE_CONTRACT
