"""
Concurrency regression tests for SimpleResponsesAgent (ERA addition, not grafted).

The upstream class stored per-request state (client_request_id, trace_id) on the
instance and documented itself as NOT thread-safe. That was fine under Streamlit,
which reruns the script per interaction. In ERA the same class backs a serving
endpoint handling concurrent requests, so the state moved to ContextVars.

These tests fail against the upstream implementation and pass against the ERA one.
They are the reason the change exists - without them the fix is unverified.

Two independent hazards are covered:
  1. OS threads          -> would break threading.local-free instance attributes
  2. asyncio tasks       -> would break threading.local as well, since concurrent
                            tasks share one thread. ContextVar handles both.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from mlflow.types.responses import ResponsesAgentRequest

N_WORKERS = 8


@pytest.fixture
def agent():
    """SimpleResponsesAgent whose endpoint call is slow enough to force interleaving."""
    with patch("era.tools.serving_utils.WorkspaceClient") as mock_ws:
        mock_client = MagicMock()
        mock_ws.return_value.serving_endpoints.get_open_ai_client.return_value = mock_client

        # Echo the caller's own request id back as the trace id, and sleep so that
        # every worker is inside predict() at the same time. Without the sleep the
        # calls could serialise and the test would pass even on a broken impl.
        def _slow_create(**kwargs):
            threading.Event().wait(0.05)
            resp = MagicMock()
            resp.trace_id = "trace-for-" + kwargs["extra_headers"]["X-Client-Request-ID"]
            return resp

        mock_client.responses.create.side_effect = _slow_create

        from era.tools.serving_utils import SimpleResponsesAgent

        yield SimpleResponsesAgent(model="test-endpoint")


def _one_request(agent):
    """Issue one request and report what this caller observes afterwards."""
    request = ResponsesAgentRequest(input=[{"role": "user", "content": "hi"}])
    response = agent.predict(request)
    return {
        "sent": response.trace_id.removeprefix("trace-for-"),
        "observed_crid": agent.get_last_client_request_id(),
        "observed_trace": agent.get_last_trace_id(),
    }


def _assert_isolated(results):
    """Every caller must observe the id it actually sent, and all ids must differ."""
    for r in results:
        assert r["observed_crid"] == r["sent"], (
            f"cross-request leak: caller sent {r['sent']} but observed "
            f"{r['observed_crid']} - per-request state is shared"
        )
        assert r["observed_trace"] == f"trace-for-{r['sent']}"

    crids = [r["observed_crid"] for r in results]
    assert len(set(crids)) == len(crids), f"client_request_ids were not unique: {crids}"


def test_threads_do_not_share_request_state(agent):
    """Concurrent OS threads must not observe each other's client_request_id."""
    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        results = list(pool.map(lambda _: _one_request(agent), range(N_WORKERS)))

    assert len(results) == N_WORKERS
    _assert_isolated(results)


def test_asyncio_tasks_do_not_share_request_state(agent):
    """
    Concurrent asyncio tasks must not observe each other's client_request_id.

    This is the case threading.local would NOT catch: these tasks all run on the
    same OS thread. Each asyncio Task copies the context at creation, so the
    ContextVar writes stay task-local.
    """

    async def run():
        # to_thread would defeat the point (separate threads), so call directly:
        # predict() is sync, but each task still gets its own context copy.
        async def one():
            return _one_request(agent)

        return await asyncio.gather(*(one() for _ in range(N_WORKERS)))

    results = asyncio.run(run())

    assert len(results) == N_WORKERS
    _assert_isolated(results)


def test_state_starts_none_in_a_fresh_context(agent):
    """A caller that has not issued a request sees no leaked state."""
    assert agent.get_last_client_request_id() is None
    assert agent.get_last_trace_id() is None
