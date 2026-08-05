"""
The worker that closes the async research loop.

This is the piece that makes "research does not block a turn" true rather than
aspirational. It runs OUT OF BAND from the serving endpoint - as a Databricks job, a
loop in a sidecar, or by hand during a demo:

    turn 1    supervisor.act submits research, stores task_id in the checkpoint,
              answers from internal evidence and tells the user research is running
    worker    polls You.com until the task settles, then writes the result into the
              same checkpointed thread via graph.aupdate_state
    turn 2    route_by_stage sees research_result and re-enters at synthesis

Adapted from the banking accelerator's `send_background_check.py`, which drives
exactly this shape for a human-in-the-loop approval. The mechanism is identical; only
the thing being waited on differs.

WHY A SEPARATE PROCESS RATHER THAN A BACKGROUND THREAD IN THE ENDPOINT
---------------------------------------------------------------------
A serving endpoint replica can be recycled at any time. A thread waiting out a
12000-second tail would take the pending research with it, and the user would wait
forever for a result nobody is still watching. The checkpoint is durable; the replica
is not. Putting the wait in a process whose only job is waiting means a restart
resumes rather than loses.

FINANCE RESEARCH IS DIFFERENT
-----------------------------
/v1/research hands back a task_id to poll. /v1/finance_research documents no
`background` flag at all, so there is nothing to poll - the worker has to hold the
blocking call itself and write the result when it returns. `run_finance_task` does
that, and it is the reason this worker exists as a general driver rather than a
poll loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Callable

from era.tools.you_research import (
    Effort,
    ResearchResult,
    ResearchTask,
    TaskStatus,
    finance_research,
    poll_research,
    record_completion,
)

logger = logging.getLogger("era.worker")

# You.com research p50 is ~300s with a long tail. Poll gently: a tighter interval
# buys nothing and just burns rate limit against an endpoint that is not going to
# answer sooner.
INITIAL_INTERVAL = 15.0
MAX_INTERVAL = 120.0
BACKOFF = 1.5
DEFAULT_TIMEOUT = 3600.0


def result_to_state(result: ResearchResult) -> dict[str, Any]:
    """
    Build the COMPLETE supervisor state update for a finished research task.

    Returns the full update - `{"research_result": {...}, "research_task_id": None}` -
    rather than just the inner payload, so every caller can `state.update(...)` it
    directly and none has to remember which key to nest it under.

    WHY that matters: an earlier version returned only the inner dict, and the first
    caller written against it (a test) splatted the fields at the top level. The
    supervisor then found no research_result, resumed as though nothing had come
    back, and reported no error anywhere. Research that silently never arrives is
    close to undebuggable from the user's side, so the shape that invites the mistake
    is gone.

    This is also the single place the worker and the supervisor agree on field names.
    """
    return {
        "research_task_id": None,
        "research_result": {
            "answer_md": result.answer_md,
            "effort": result.effort,
            "endpoint": result.endpoint,
            "warnings": list(result.warnings),
            "citations": [
                {
                    "n": c.n,
                    "url": c.url,
                    "title": c.title,
                    "retrieved_at": c.retrieved_at,
                }
                for c in result.citations
            ],
        },
    }


def wait_for_task(
    task_id: str,
    *,
    effort: str = Effort.STANDARD.value,
    timeout: float = DEFAULT_TIMEOUT,
    transport=None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> ResearchTask:
    """
    Poll until the task settles or the deadline passes.

    Returns the settled task rather than raising on failure: a failed research task
    is information the next turn should convey to the user, not an exception that
    strands the thread waiting for a result that will never come.
    """
    deadline = now() + timeout
    interval = INITIAL_INTERVAL

    while True:
        task = poll_research(task_id, effort=effort, transport=transport)
        if task.settled:
            return task

        if now() >= deadline:
            task.status = TaskStatus.FAILED
            task.error = f"worker gave up after {timeout:.0f}s (task still {task.status.value})"
            return task

        sleep(min(interval, MAX_INTERVAL))
        interval *= BACKOFF


async def resume_thread(
    thread_id: str,
    state_update: dict[str, Any],
    *,
    graph,
    config: dict | None = None,
) -> None:
    """
    Inject the result into the checkpointed thread.

    `aupdate_state` writes into the existing checkpoint rather than starting a new
    run, which is what lets the next turn resume mid-graph with the research present.
    """
    cfg = config or {"configurable": {"thread_id": thread_id}}
    await graph.aupdate_state(cfg, state_update)
    logger.info("thread %s updated with research result", thread_id)


async def _open_graph(instance_name: str, schema: str, llm, tools):
    """
    Build the graph against the same Lakebase checkpointer the endpoint uses.

    It must be the same store - a worker writing to a different checkpointer would
    report success while the endpoint never sees the result.
    """
    from databricks_langchain.checkpoint import AsyncCheckpointSaver

    from era.agent.supervisor import build_graph

    checkpointer = AsyncCheckpointSaver(instance_name=instance_name, schema=schema)
    return checkpointer, build_graph(llm=llm, tools=tools, checkpointer=checkpointer)


async def drive_background_research(
    thread_id: str,
    task_id: str,
    *,
    instance_name: str,
    schema: str,
    llm,
    tools,
    original_query: str = "",
    effort: str = Effort.STANDARD.value,
    timeout: float = DEFAULT_TIMEOUT,
) -> ResearchTask:
    """Poll /v1/research to completion, then resume the thread. The main entry point."""
    started = time.monotonic()
    task = wait_for_task(task_id, effort=effort, timeout=timeout)
    latency_ms = int((time.monotonic() - started) * 1000)

    record_completion(task, original_query, latency_ms=latency_ms)

    if task.status is TaskStatus.COMPLETED and task.result:
        update: dict[str, Any] = result_to_state(task.result)
    else:
        update = {"research_task_id": None}
        # Tell the next turn plainly. Silence here reads to the user as the research
        # still running, forever.
        update["notices"] = [
            f"Background research did not complete ({task.error or task.status.value})."
        ]

    checkpointer, graph = await _open_graph(instance_name, schema, llm, tools)
    async with checkpointer:
        await checkpointer.setup()
        await resume_thread(thread_id, update, graph=graph)
    return task


async def run_finance_task(
    thread_id: str,
    query: str,
    *,
    instance_name: str,
    schema: str,
    llm,
    tools,
    effort: Effort = Effort.DEEP,
) -> None:
    """
    Finance Research has no task API, so the worker holds the blocking call itself
    and resumes the thread when it returns.
    """
    try:
        result = finance_research(query, effort=effort)
        update = result_to_state(result)
    except Exception as exc:
        logger.warning("finance research failed: %s", exc)
        update = {"research_task_id": None, "notices": [f"Finance research failed: {exc}"]}

    checkpointer, graph = await _open_graph(instance_name, schema, llm, tools)
    async with checkpointer:
        await checkpointer.setup()
        await resume_thread(thread_id, update, graph=graph)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--thread-id", required=True)
    p.add_argument("--task-id", help="Research task id to poll. Omit with --finance-query.")
    p.add_argument("--finance-query", help="Run a blocking Finance Research call instead.")
    p.add_argument("--effort", default=Effort.STANDARD.value)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p.add_argument("--lakebase-instance", default=os.environ.get("LAKEBASE_INSTANCE_NAME", ""))
    p.add_argument("--checkpoint-schema", default=os.environ.get("CHECKPOINT_SCHEMA", "era_checkpoints"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.lakebase_instance:
        print("ERROR: --lakebase-instance or LAKEBASE_INSTANCE_NAME is required", file=sys.stderr)
        return 1
    if not args.task_id and not args.finance_query:
        print("ERROR: pass --task-id or --finance-query", file=sys.stderr)
        return 1

    from era.agent.supervisor import EraSupervisor, ToolBundle

    agent = EraSupervisor()
    tools = ToolBundle()

    if args.finance_query:
        asyncio.run(run_finance_task(
            args.thread_id, args.finance_query,
            instance_name=args.lakebase_instance, schema=args.checkpoint_schema,
            llm=agent._llm, tools=tools,
        ))
        return 0

    task = asyncio.run(drive_background_research(
        args.thread_id, args.task_id,
        instance_name=args.lakebase_instance, schema=args.checkpoint_schema,
        llm=agent._llm, tools=tools, effort=args.effort, timeout=args.timeout,
    ))
    print(f"task {task.task_id} finished with status {task.status.value}")
    return 0 if task.status is TaskStatus.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
