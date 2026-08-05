"""
Point the Multi-Agent Supervisor at the governed You.com tools (Milestone B).

The MAS consumes these exactly the way it already consumes ``generate_vega_lite_spec``
- as Unity Catalog function agents - so no new integration mechanism is involved.
This script only edits the supervisor's agent list.

WHY REPLACE RATHER THAN ADD (default mode)
------------------------------------------
``setup_instructor/03b_create_youdotcom_uc_functions.ipynb`` registers
``you_web_search`` / ``you_content_extract`` / ``you_research`` against the free-tier
MCP endpoint - no API key, no Unity Catalog connection, hardcoded host. Leaving those
attached alongside the governed ones gives the supervisor two tools that do the same
job, one of which bypasses every control in ``conf/``. The model will sometimes pick
the ungoverned one, and the egress you were trying to govern happens anyway.

So by default the fallback tools are detached from the supervisor. They are NOT
deleted from Unity Catalog - 03b still owns them, they remain callable, and
``--mode revert`` puts them back. That keeps the Milestone A baseline demoable, which
is the point of keeping it at all.

Usage::

    python era/connections/register_mas_tools.py --dry-run
    python era/connections/register_mas_tools.py
    python era/connections/register_mas_tools.py --mode add       # run both, for A/B
    python era/connections/register_mas_tools.py --mode revert    # back to 03b only
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from databricks.sdk import WorkspaceClient  # noqa: E402

from resources.brick_setup_functions import AgentBricksManager  # noqa: E402

logger = logging.getLogger("era.mas")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# The ungoverned Milestone A tools, by UC function name.
FALLBACK_FUNCTIONS = {"you_web_search", "you_content_extract", "you_research"}

# The governed replacements. Descriptions matter more than usual here: they are the
# only thing the supervisor reads when deciding which tool to reach for, so they
# state both what the tool does and when NOT to use it.
GOVERNED_TOOLS = {
    "era_you_search": {
        "name": "Web_Search",
        "description": (
            "Search the web and news for current information via a governed You.com "
            "connection. Returns raw JSON with results.web[] and results.news[] - news "
            "comes back from this same tool, there is no separate news tool. Use for "
            "events, market reaction, and anything more recent than your training data. "
            "Pass a freshness window when recency matters. Every result carries a URL "
            "that MUST be cited when you use it."
        ),
    },
    "era_you_contents": {
        "name": "Web_Content_Extractor",
        "description": (
            "Fetch the full text of specific URLs as markdown. Use after Web_Search when "
            "a snippet is not enough to support a claim you intend to make. Do not guess "
            "at page contents you have not fetched."
        ),
    },
}


def load_config() -> dict:
    ns: dict = {}
    exec((REPO_ROOT / "config.py").read_text(encoding="utf-8"), ns)
    return ns


def uc_function_agent(catalog: str, schema: str, func: str, name: str, description: str) -> dict:
    """Build a MAS agent entry for a UC function, matching 04's existing shape."""
    return {
        "name": name,
        "description": description,
        "agent_type": "function",
        "unity_catalog_function": {
            "uc_path": {"catalog": catalog, "schema": schema, "name": func}
        },
    }


def agent_function_name(agent: dict) -> str | None:
    """Return the UC function name an agent points at, if it is a function agent."""
    if agent.get("agent_type") != "function":
        return None
    return (agent.get("unity_catalog_function") or {}).get("uc_path", {}).get("name")


def plan_agents(current: list[dict], catalog: str, schema: str, mode: str) -> list[dict]:
    """Compute the new agent list. Pure function so it is testable without a workspace."""
    if mode == "revert":
        # Drop the governed tools; leave everything else (including 03b's) untouched.
        return [a for a in current if agent_function_name(a) not in GOVERNED_TOOLS]

    kept = [
        a
        for a in current
        if agent_function_name(a) not in GOVERNED_TOOLS
        and (mode == "add" or agent_function_name(a) not in FALLBACK_FUNCTIONS)
    ]
    governed = [
        uc_function_agent(catalog, schema, func, spec["name"], spec["description"])
        for func, spec in GOVERNED_TOOLS.items()
    ]
    if mode == "add":
        # Both sets attached: disambiguate the names so the supervisor can tell them
        # apart, otherwise two agents called Web_Search collide.
        for agent in governed:
            agent["name"] = f"{agent['name']}_Governed"
    return kept + governed


def describe(label: str, agents: list[dict]) -> None:
    print(f"\n{label} ({len(agents)} agents)")
    for a in agents:
        fn = agent_function_name(a)
        suffix = f"  -> {fn}" if fn else f"  [{a.get('agent_type')}]"
        print(f"  - {a.get('name')}{suffix}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["replace", "add", "revert"], default="replace")
    p.add_argument("--dry-run", action="store_true", help="Show the change without applying it.")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    cfg = load_config()
    catalog, schema, sa_name = cfg["catalog"], cfg["schema"], cfg["sa_name"]

    w = WorkspaceClient()
    mgr = AgentBricksManager(w)

    resp = w.api_client.do(
        "GET", f"/api/2.0/tiles?filter=name_contains%3D{sa_name}%26%26tile_type%3DMAS"
    )
    tiles = [t for t in resp.get("tiles", []) if t.get("name") == sa_name]
    if not tiles:
        logger.error(
            "Supervisor '%s' not found. Run setup_instructor/04_instructor_setup_sa "
            "first (Milestone A).", sa_name,
        )
        return 1
    tile_id = tiles[0]["tile_id"]

    mas = mgr.mas_get(tile_id)
    current = (mas or {}).get("multi_agent_supervisor", {}).get("agents", []) or []

    # Refuse to run if the governed functions do not exist yet - otherwise the MAS
    # ends up referencing a function that is not there and every web query fails.
    if args.mode != "revert":
        missing = [
            f"{catalog}.{schema}.{fn}"
            for fn in GOVERNED_TOOLS
            if not _function_exists(w, catalog, schema, fn)
        ]
        if missing:
            logger.error(
                "governed UC functions not found: %s\nRun era/connections/you_uc_functions.sql first.",
                ", ".join(missing),
            )
            return 1

    planned = plan_agents(current, catalog, schema, args.mode)

    describe("BEFORE", current)
    describe(f"AFTER  (mode={args.mode})", planned)

    if args.dry_run:
        print("\ndry run - nothing applied")
        return 0

    if not planned:
        logger.error("refusing to leave the supervisor with zero agents")
        return 1

    mgr.mas_update(tile_id, agents=planned)
    logger.info("supervisor '%s' updated", sa_name)
    print(
        "\nNote: the supervisor endpoint may take a few minutes to redeploy. "
        "The app service principal needs EXECUTE on the new functions and "
        "USE CONNECTION on you_search_http."
    )
    return 0


def _function_exists(w: WorkspaceClient, catalog: str, schema: str, name: str) -> bool:
    try:
        w.functions.get(f"{catalog}.{schema}.{name}")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
