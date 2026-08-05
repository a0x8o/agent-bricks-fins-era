"""
Tests for the async research worker.

No sleeping, no network, no Lakebase: the clock, the sleep and the transport are all
injected. The properties that matter are that the worker terminates, that it never
strands a thread, and that the state it writes is the exact shape the supervisor
resumes from.
"""

from __future__ import annotations

import pytest

from era.agent import research_worker as worker
from era.agent import supervisor as sup
from era.tools.you_research import Citation, ResearchResult, TaskStatus


class FakeTransport:
    """Returns a scripted sequence of poll responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.gets = 0

    def get(self, url, headers, timeout):
        self.gets += 1
        return self.responses.pop(0) if self.responses else (200, {"status": "running"})

    def post(self, url, json, headers, timeout):  # pragma: no cover - unused
        raise AssertionError("worker should not POST")


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    from era.tools import you_research

    monkeypatch.setenv(you_research.SECRET_ENV, "test-key")


COMPLETED = (200, {
    "status": "completed",
    "result": {"output": {
        "content": "Deep findings [1].",
        "sources": [{"url": "https://ft.com/deep", "title": "Deep"}],
    }},
})
RUNNING = (200, {"status": "running"})


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

def test_waits_until_the_task_settles():
    clock = FakeClock()
    transport = FakeTransport([RUNNING, RUNNING, COMPLETED])

    task = worker.wait_for_task("t-1", transport=transport, sleep=clock.sleep, now=clock.now)

    assert task.status is TaskStatus.COMPLETED
    assert transport.gets == 3


def test_polling_backs_off_rather_than_hammering():
    """
    A p50 of 300s does not answer sooner because you asked more often; a tight loop
    just burns rate limit against the endpoint you are waiting on.
    """
    clock = FakeClock()
    transport = FakeTransport([RUNNING, RUNNING, RUNNING, COMPLETED])
    worker.wait_for_task("t-1", transport=transport, sleep=clock.sleep, now=clock.now)

    # Three sleeps at 15, 22.5, 33.75 with 1.5x backoff.
    assert clock.t == pytest.approx(15 + 22.5 + 33.75)


def test_backoff_is_capped():
    clock = FakeClock()
    transport = FakeTransport([RUNNING] * 40 + [COMPLETED])
    worker.wait_for_task("t-1", transport=transport, sleep=clock.sleep, now=clock.now, timeout=10**9)

    # No single wait may exceed the cap, so total stays proportional to attempts.
    assert clock.t <= worker.MAX_INTERVAL * 41


def test_timeout_returns_a_failed_task_rather_than_raising():
    """
    Raising here would strand the thread waiting on a result that will never arrive.
    A settled-but-failed task lets the next turn say so.
    """
    clock = FakeClock()
    transport = FakeTransport([RUNNING] * 100)

    task = worker.wait_for_task(
        "t-1", transport=transport, sleep=clock.sleep, now=clock.now, timeout=60.0
    )
    assert task.status is TaskStatus.FAILED
    assert "gave up" in task.error


def test_a_failed_task_settles_immediately():
    clock = FakeClock()
    transport = FakeTransport([(200, {"status": "failed", "error": "upstream 500"})])

    task = worker.wait_for_task("t-1", transport=transport, sleep=clock.sleep, now=clock.now)
    assert task.status is TaskStatus.FAILED
    assert task.error == "upstream 500"
    assert clock.t == 0.0, "a settled task must not sleep at all"


# ---------------------------------------------------------------------------
# State handoff - the contract with the supervisor
# ---------------------------------------------------------------------------

def test_result_state_is_the_shape_the_supervisor_resumes_from():
    """
    A field-name mismatch here would surface as research that silently never
    arrives, which is close to undebuggable from the user's side. So assert the
    handoff end to end rather than the shape in isolation.
    """
    result = ResearchResult(
        answer_md="Findings [1].",
        citations=(Citation(n=1, url="https://ft.com/deep", title="Deep", retrieved_at="2026-08-04T09:00:00Z"),),
        effort="deep",
        endpoint="research",
    )
    state_update = worker.result_to_state(result)

    state = sup.new_state("q")
    state.update(state_update)

    # The supervisor must route to synthesis and see the citation as usable evidence.
    assert sup.route_by_stage(state) == sup.STAGE_SYNTHESIZE
    assert "https://ft.com/deep" in sup.build_evidence(state).external_urls


def test_research_citations_validate_as_provenance_evidence():
    from era.agent.provenance import check

    result = ResearchResult(
        answer_md="x",
        citations=(Citation(n=1, url="https://ft.com/deep", title="Deep", retrieved_at="2026-08-04T09:00:00Z"),),
        effort="deep",
        endpoint="research",
    )
    state = sup.new_state("q")
    state.update(worker.result_to_state(result))

    answer = (
        "External analysis reached the same conclusion [EC:1].\n\n"
        "## Sources\n"
        "[1] Deep - https://ft.com/deep (retrieved 2026-08-04T09:00:00Z)\n"
    )
    assert check(answer, sup.build_evidence(state)).ok


def test_result_to_state_returns_a_complete_state_update():
    """
    It must clear research_task_id as well as set research_result. Leaving the task
    id in place would make act_node believe research is still in flight forever.
    """
    result = ResearchResult(answer_md="x", citations=(), effort="deep", endpoint="research")
    update = worker.result_to_state(result)

    assert update["research_task_id"] is None
    assert update["research_result"]["citations"] == []
    assert set(update) == {"research_task_id", "research_result"}


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

class FakeGraph:
    def __init__(self):
        self.updates: list[tuple[dict, dict]] = []

    async def aupdate_state(self, config, update):
        self.updates.append((config, update))


def test_resume_writes_into_the_existing_thread():
    """
    aupdate_state, not invoke: the result must land in the checkpoint the endpoint
    will resume from, not start a fresh run.
    """
    import asyncio

    graph = FakeGraph()
    asyncio.run(worker.resume_thread("thread-9", {"research_result": {"answer_md": "x"}}, graph=graph))

    config, update = graph.updates[0]
    assert config["configurable"]["thread_id"] == "thread-9"
    assert update["research_result"]["answer_md"] == "x"


def test_cli_requires_a_lakebase_instance():
    assert worker.main(["--thread-id", "t", "--task-id", "x", "--lakebase-instance", ""]) == 1


def test_cli_requires_something_to_do():
    assert worker.main(["--thread-id", "t", "--lakebase-instance", "inst"]) == 1
