"""
Log the ERA supervisor to MLflow, register it to Unity Catalog, and deploy it.

Run from a Databricks notebook or job (it needs workspace auth and writes to UC)::

    python -m era.agent.log_and_deploy --warehouse-id <id> --ka-endpoint <name> \\
        --genie-space-id <id> --deploy

Without --deploy it logs and registers only, which is the safe way to check the
model builds before standing up an endpoint.

WHY A SEPARATE ENDPOINT
-----------------------
This deploys to its own endpoint and never touches `mas-<tile>-endpoint`. Milestone
A's supervisor keeps serving the app throughout, so a failed deployment here costs
nothing that currently works. Repointing the app is a deliberate, separate step.

RESOURCES ARE DECLARED, NOT ASSUMED
-----------------------------------
Every downstream dependency is listed as an MLflow resource so the serving endpoint
is granted access to it automatically. Omitting one produces an agent that deploys
cleanly and then 403s on its first real question - the failure appears at request
time, in production, on whichever tool you forgot.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys

logger = logging.getLogger("era.deploy")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_MODEL_NAME = "era_supervisor"
DEFAULT_ENDPOINT = "era-supervisor"
ENTRYPOINT = str(REPO_ROOT / "era" / "agent" / "serving_entrypoint.py")

# Pinned deliberately. langgraph and databricks-langchain are NOT here: the served
# path runs through run_turn, which is plain Python, and build_graph imports
# langgraph lazily. Shipping them would enlarge the image for code the endpoint
# never executes. Add them only when the checkpointed resume path is served.
PIP_REQUIREMENTS = [
    "mlflow>=3.11",
    "databricks-sdk",
    "openai",
    "pyyaml",
    "httpx",
]


def _default_experiment() -> str:
    """/Users/<caller>/era-supervisor - a per-user path that always exists."""
    from databricks.sdk import WorkspaceClient

    user = WorkspaceClient().current_user.me().user_name
    return f"/Users/{user}/era-supervisor"


def load_config() -> dict:
    ns: dict = {}
    exec((REPO_ROOT / "config.py").read_text(encoding="utf-8"), ns)
    return ns


def build_resources(*, llm_endpoint, ka_endpoint, genie_space_id, warehouse_id, catalog, schema):
    """Declare everything the endpoint must be entitled to reach."""
    from mlflow.models.resources import (
        DatabricksFunction,
        DatabricksGenieSpace,
        DatabricksServingEndpoint,
        DatabricksSQLWarehouse,
        DatabricksTable,
    )

    resources = [DatabricksServingEndpoint(endpoint_name=llm_endpoint)]
    if ka_endpoint:
        resources.append(DatabricksServingEndpoint(endpoint_name=ka_endpoint))
    if genie_space_id:
        resources.append(DatabricksGenieSpace(genie_space_id=genie_space_id))
    if warehouse_id:
        resources.append(DatabricksSQLWarehouse(warehouse_id=warehouse_id))
    for fn in ("era_you_search", "era_you_contents"):
        resources.append(DatabricksFunction(function_name=f"{catalog}.{schema}.{fn}"))
    # The audit table is written by the agent, so it needs to be reachable too.
    resources.append(DatabricksTable(table_name=f"{catalog}.{schema}.egress_audit"))
    return resources


def log_and_register(args) -> tuple[str, int]:
    import mlflow
    from mlflow.types.responses import ResponsesAgentRequest

    cfg = load_config()
    catalog = args.catalog or cfg["catalog"]
    schema = args.schema or cfg["schema"]
    model_name = f"{catalog}.{schema}.{args.model_name}"

    mlflow.set_registry_uri("databricks-uc")

    # An experiment is required and is NOT implicit outside a notebook: a bare
    # local run fails with "Could not find experiment with ID None". Setting it
    # explicitly also gives the agent's traces a stable home, which Milestone D's
    # evaluation and the grafted feedback tests both need.
    experiment = args.experiment or _default_experiment()
    mlflow.set_experiment(experiment)
    logger.info("experiment: %s", experiment)

    resources = build_resources(
        llm_endpoint=args.llm_endpoint,
        ka_endpoint=args.ka_endpoint,
        genie_space_id=args.genie_space_id,
        warehouse_id=args.warehouse_id,
        catalog=catalog,
        schema=schema,
    )

    example = ResponsesAgentRequest(
        input=[{"role": "user", "content": "What supply-chain risks does the latest 10-K disclose?"}]
    ).model_dump()

    with mlflow.start_run(run_name="era-supervisor"):
        info = mlflow.pyfunc.log_model(
            name=args.model_name,
            python_model=ENTRYPOINT,
            # conf/ ships alongside era/ so the gate can load its policy at runtime.
            # Without it the denylist and sensitive-term list would be empty and the
            # gate would approve everything while looking healthy.
            code_paths=[str(REPO_ROOT / "era"), str(REPO_ROOT / "conf")],
            pip_requirements=PIP_REQUIREMENTS,
            resources=resources,
            input_example=example,
            registered_model_name=model_name,
        )

    version = int(info.registered_model_version)
    logger.info("registered %s version %s", model_name, version)
    return model_name, version


def deploy(model_name: str, version: int, args) -> None:
    from databricks import agents

    cfg = load_config()
    catalog = args.catalog or cfg["catalog"]
    schema = args.schema or cfg["schema"]

    env = {
        "ERA_CATALOG": catalog,
        "ERA_SCHEMA": schema,
        "ERA_LLM_ENDPOINT": args.llm_endpoint,
        "ERA_KA_ENDPOINT": args.ka_endpoint or "",
        "ERA_GENIE_SPACE_ID": args.genie_space_id or "",
        "ERA_WAREHOUSE_ID": args.warehouse_id or "",
    }
    if args.you_api_key_env:
        # The Python research tools read YOU_API_KEY from the environment - they do
        # not resolve secret() the way the UC functions do. Passed as a secret
        # reference so the value never appears in this process or in the job log.
        env["YOU_API_KEY"] = args.you_api_key_env

    deployment = agents.deploy(
        model_name=model_name,
        model_version=version,
        endpoint_name=args.endpoint_name,
        scale_to_zero=True,
        environment_vars=env,
        tags={"project": "era", "milestone": "C"},
        description="ERA governed research agent (code-first supervisor).",
    )
    logger.info("deployment requested: %s", getattr(deployment, "endpoint_name", args.endpoint_name))
    print(
        "\nEndpoint is provisioning. It does NOT replace the Milestone A supervisor.\n"
        "Check with: databricks serving-endpoints get " + args.endpoint_name
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--llm-endpoint", default="alexxx-era-sonnet-4-5")
    p.add_argument("--ka-endpoint", default="")
    p.add_argument("--genie-space-id", default="")
    p.add_argument("--warehouse-id", default="")
    p.add_argument("--catalog", default="")
    p.add_argument("--schema", default="")
    p.add_argument("--experiment", default="",
                   help="MLflow experiment path. Defaults to /Users/<you>/era-supervisor.")
    p.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    p.add_argument("--endpoint-name", default=DEFAULT_ENDPOINT)
    p.add_argument("--you-api-key-env", default="",
                   help="Secret reference for YOU_API_KEY, e.g. {{secrets/era_you/api_key}}")
    p.add_argument("--deploy", action="store_true", help="Deploy after registering.")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    model_name, version = log_and_register(args)
    print(f"registered {model_name} v{version}")

    if args.deploy:
        deploy(model_name, version, args)
    else:
        print("not deploying (pass --deploy). Re-run with --deploy once the model looks right.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
