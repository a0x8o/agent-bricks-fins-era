"""
Run the ERA evaluation and enforce the release gate.

    python -m era.eval.run_eval --offline-fixtures era/eval/fixtures.json
    python -m era.eval.run_eval --endpoint <serving-endpoint>
    python -m era.eval.run_eval --endpoint <endpoint> --no-judges   # deterministic only

Exit code 0 means the gate passed. Anything else means do not promote this agent.
That is the whole contract with the deploy job: it does not parse the output, it
checks the exit code.

WHY THE GATE IS EVALUATED HERE AND NOT LEFT TO A DASHBOARD
----------------------------------------------------------
A threshold nobody enforces is a chart. The point of `conf/release_gate.yaml` is that
a regression in provenance separation stops a deploy rather than appearing in a
weekly review after the regression has shipped.

The gate deliberately splits blocking (deterministic) from advisory (judge) metrics -
see the reasoning in the config. A judge having an off day must not hold up a deploy;
a fabricated citation must.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

from era.eval import datasets
from era.eval.datasets import Bucket

logger = logging.getLogger("era.eval")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "conf" / "release_gate.yaml"


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    evaluated: int = 0

    def report(self) -> str:
        lines = [f"{'PASS' if self.passed else 'FAIL'}  ({self.evaluated} questions evaluated)"]
        for name, value in sorted(self.metrics.items()):
            lines.append(f"  {name:<28} {value:.3f}")
        for failure in self.failures:
            lines.append(f"  BLOCKING  {failure}")
        for warning in self.warnings:
            lines.append(f"  advisory  {warning}")
        return "\n".join(lines)


def load_gate(path: pathlib.Path = GATE_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _metric_value(metrics: dict[str, Any], name: str) -> float | None:
    """
    Find a metric regardless of the suffix MLflow attaches to aggregations.

    MLflow reports aggregated scorer metrics as e.g. `provenance_separation/mean`.
    Matching loosely here keeps the gate config readable - the alternative is
    thresholds named after an implementation detail of the aggregation.
    """
    if name in metrics:
        return _as_float(metrics[name])
    for key, value in metrics.items():
        base = key.split("/")[0]
        if base == name:
            return _as_float(value)
    return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_gate(
    metrics: dict[str, Any],
    *,
    evaluated: int,
    buckets_seen: set[str],
    gate: dict | None = None,
) -> GateResult:
    """
    Apply the gate to a metrics dict. Pure, so it is testable without running an eval.
    """
    gate = gate or load_gate()
    result = GateResult(passed=True, evaluated=evaluated)

    # Coverage first. A harness that silently evaluated nothing would otherwise score
    # a clean 1.0 on every metric and report a pass.
    minimum = int(gate.get("min_questions_evaluated", 0))
    if evaluated < minimum:
        result.passed = False
        result.failures.append(
            f"only {evaluated} question(s) evaluated, gate requires at least {minimum}"
        )

    required = set(gate.get("required_buckets") or ())
    missing = sorted(required - buckets_seen)
    if missing:
        result.passed = False
        result.failures.append(f"no results for required bucket(s): {', '.join(missing)}")

    for name, threshold in (gate.get("blocking") or {}).items():
        value = _metric_value(metrics, name)
        if value is None:
            result.passed = False
            result.failures.append(f"{name} is missing from the run (expected >= {threshold})")
            continue
        result.metrics[name] = value
        if value < float(threshold):
            result.passed = False
            result.failures.append(f"{name} {value:.3f} < {threshold}")

    for name, threshold in (gate.get("advisory") or {}).items():
        value = _metric_value(metrics, name)
        if value is None:
            result.warnings.append(f"{name} not reported (judges may be disabled)")
            continue
        result.metrics[name] = value
        if value < float(threshold):
            result.warnings.append(f"{name} {value:.3f} < {threshold}")

    return result


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def score_offline(records: list[dict], answers: dict[str, Any]) -> dict[str, float]:
    """
    Score pre-computed answers with the deterministic scorers only.

    This exists so the gate logic and the scorers can be exercised without a
    workspace, a judge model, or a live agent - which is what makes it possible to
    test that the gate actually fails when it should. `answers` maps question_id to
    either an answer string or {"answer": ..., "evidence": {...}}.
    """
    from era.eval import scorers as era_scorers

    scorer_fns = era_scorers.deterministic_scorers()
    totals: dict[str, list[float]] = {s.name: [] for s in scorer_fns}

    for record in records:
        question_id = record["tags"]["question_id"]
        if question_id not in answers:
            continue
        outputs = answers[question_id]
        expectations = record["expectations"]

        for scorer_fn in scorer_fns:
            feedback = _call_scorer(scorer_fn, outputs, expectations)
            value = _as_float(getattr(feedback, "value", feedback))
            if value is not None:
                totals[scorer_fn.name].append(value)

    return {
        name: (sum(values) / len(values)) if values else 0.0
        for name, values in totals.items()
    }


def _call_scorer(scorer_fn, outputs, expectations):
    """Call a scorer with only the arguments it declares."""
    try:
        return scorer_fn(outputs=outputs, expectations=expectations)
    except TypeError:
        return scorer_fn(outputs=outputs)


def build_predict_fn(endpoint: str) -> Callable[..., dict]:
    """
    Call the DEPLOYED agent endpoint.

    An earlier version constructed EraSupervisor(model=endpoint) and ran the pipeline
    locally, which evaluated the code on this machine rather than the thing actually
    serving traffic - and would have failed anyway, because an agent endpoint speaks
    the Responses API while that path calls chat completions.

    Evidence comes back in custom_outputs. Without it the deterministic scorers have
    nothing to resolve citations against, and citation_validity would score every
    answer 1.0 including fabricated ones - the harness would report success precisely
    where it is meant to fail.
    """
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient().serving_endpoints.get_open_ai_client()

    def predict_fn(question: str) -> dict:
        response = client.responses.create(
            model=endpoint, input=[{"role": "user", "content": question}]
        )
        payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)

        text = ""
        for item in payload.get("output") or []:
            if isinstance(item, dict) and item.get("type") == "message":
                for chunk in item.get("content") or []:
                    if isinstance(chunk, dict) and chunk.get("text"):
                        text += chunk["text"]

        custom = payload.get("custom_outputs") or {}
        return {
            "answer": text,
            "evidence": custom.get("evidence") or {},
            "notices": custom.get("notices") or [],
        }

    return predict_fn


def run(
    *,
    endpoint: str | None = None,
    include_judges: bool = True,
    judge_model: str | None = None,
    questions=None,
) -> tuple[dict[str, Any], int, set[str]]:
    """Drive mlflow.genai.evaluate against the deployed agent."""
    import mlflow.genai

    from era.eval import scorers as era_scorers

    questions = questions or datasets.ALL
    records = datasets.to_records(questions)
    buckets = {q.bucket.value for q in questions}

    result = mlflow.genai.evaluate(
        data=records,
        scorers=era_scorers.all_scorers(include_judges=include_judges, judge_model=judge_model),
        predict_fn=build_predict_fn(endpoint) if endpoint else None,
    )
    metrics = dict(getattr(result, "metrics", {}) or {})
    return metrics, len(records), buckets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--endpoint", help="Serving endpoint of the deployed agent.")
    p.add_argument("--offline-fixtures", help="JSON file mapping question_id -> answer, for a run with no workspace.")
    p.add_argument("--no-judges", action="store_true", help="Deterministic scorers only.")
    p.add_argument("--judge-model", help="Endpoint for the LLM judges.")
    p.add_argument("--bucket", action="append", choices=[b.value for b in Bucket], help="Restrict to bucket(s).")
    p.add_argument("--gate", default=str(GATE_PATH))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    questions = datasets.ALL
    if args.bucket:
        wanted = {Bucket(b) for b in args.bucket}
        questions = tuple(q for q in datasets.ALL if q.bucket in wanted)

    if args.offline_fixtures:
        answers = json.loads(pathlib.Path(args.offline_fixtures).read_text(encoding="utf-8"))
        records = datasets.to_records(questions)
        metrics = score_offline(records, answers)
        evaluated = sum(1 for r in records if r["tags"]["question_id"] in answers)
        buckets = {
            r["expectations"]["bucket"] for r in records if r["tags"]["question_id"] in answers
        }
    elif args.endpoint:
        metrics, evaluated, buckets = run(
            endpoint=args.endpoint,
            include_judges=not args.no_judges,
            judge_model=args.judge_model,
            questions=questions,
        )
    else:
        p.error("pass --endpoint to evaluate a deployed agent, or --offline-fixtures to score saved answers")
        return 2

    gate = load_gate(pathlib.Path(args.gate))
    result = evaluate_gate(metrics, evaluated=evaluated, buckets_seen=buckets, gate=gate)

    print(result.report())
    if not result.passed:
        print("\nRelease gate FAILED - do not promote this agent.", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
