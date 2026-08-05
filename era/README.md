# ERA — Enterprise Research Agent

A governed research agent over Databricks: internal evidence from the existing
Knowledge Assistant and Genie space, external evidence from You.com, and every
material claim tagged `internal-verified` / `external-cited` / `inferred`.

This package is additive. Everything in `setup_instructor/`, `chatbot-app/`,
`resources/` and `data/` still works exactly as before — each milestone leaves the
previous one runnable.

## Layering

The You.com integration is staged rather than swapped wholesale. Each layer is
independently demoable, and later layers reuse the earlier ones.

| Layer | Integration | Orchestrator | Buys you | Costs you |
|---|---|---|---|---|
| **A** | `03b` free-tier MCP functions + `05` MCP server | Agent Bricks MAS | Blended answers in hours; validates workspace/KA/Genie/MAS/app | No gate, no provenance, no parameter control |
| **B** | `era_you_*` UC functions over `http_request` | Agent Bricks MAS | Credential in UC, parameter control, domain policy pushed to the provider | No redaction, no per-call audit (a SQL UDF cannot write Delta) |
| **C** | Hybrid: fast via UC functions, slow via Python tools with async resume | Code-first `ResponsesAgent` + LangGraph | Full governance, provenance separation, long-running research off the turn | Real code |

Layer A stays in the repo permanently as the fallback. `05_create_mcp_server_OPTIONAL.ipynb`
is not deleted.

## Milestone B runbook

Prerequisite: Milestone A complete, i.e. the supervisor named by `config.sa_name`
exists and answers a blended question.

```bash
# 1. Store the You.com key. Nothing in this repo ever contains it.
databricks secrets create-scope era_you
databricks secrets put-secret era_you api_key

# 2. Create the two UC HTTP connections, then prove the key actually works.
#    CREATE CONNECTION succeeds without ever contacting You.com, so --verify
#    is the only thing that tells you the credential is good.
python era/connections/setup_you_http_connection.py --warehouse-id <id> --verify

# 3. Create the governed UC functions (run the SQL in a notebook or DBSQL editor).
#    Regenerate first if you changed anything in conf/.
python era/connections/render_uc_functions.py
#    then execute era/connections/you_uc_functions.sql

# 4. Swap the supervisor's web tools over. Inspect before applying.
python era/connections/register_mas_tools.py --dry-run
python era/connections/register_mas_tools.py
```

To go back to the Layer A behaviour: `register_mas_tools.py --mode revert`, then
re-run `03b` to reattach the free-tier tools.

## Milestone C: the code-first agent

Built and tested offline; not yet deployed (that needs Milestone A verified).

```
question
  -> plan       which tools, and why. An empty plan falls back to internal sources,
                never to answering from memory.
  -> act        run them. Every failure degrades: a policy refusal, a Genie timeout
                or a KA without citations all leave the turn able to answer from
                whatever else succeeded, with a notice the user actually sees.
  -> synthesize write the answer, then validate its provenance before anyone sees it
  -> critique   repair a draft that failed validation. Bounded to one pass.
```

| Module | Does |
|---|---|
| `tools/redaction.py` | scrub → policy_check → audit. The single egress gate. |
| `agent/provenance.py` | resolves every `[IV:]`/`[EC:]` tag back to evidence a tool really returned |
| `agent/prompts.py` | planner / synthesis / critique prompts carrying the tag contract |
| `tools/internal_bricks.py` | KA + Genie as tools, returning document and table lineage |
| `tools/you_fast.py` | search + contents via the Milestone B UC functions |
| `tools/you_research.py` | `/v1/research` submit+poll, `/v1/finance_research` blocking |
| `agent/supervisor.py` | the graph, as plain functions plus a lazy LangGraph wiring |
| `agent/research_worker.py` | polls a background task and resumes the checkpointed thread |

### Provenance

Every material claim carries one tag: `[IV:<lineage>]`, `[EC:<n>]`, or `[INF]`, with a
`## Sources` block resolving each citation. Validation is not cosmetic — a citation
pointing at a URL no tool returned is a **failed answer**, as is an untagged claim.

The reason for validating rather than trusting the tags: a model asked to cite will
cite, and under pressure will invent a plausible citation or tag its own inference as
verified. Both produce output that looks *more* trustworthy than an honest untagged
answer. Internal claims are held to the same standard — a KA that returns no citations
yields no lineage, and the answer must say `[INF]` rather than claim verification it
does not have.

### Two things the gate does that are easy to get wrong

**Redaction and refusal are different tools.** Stripping an email neutralises it and
the remaining question is ordinary, so the call proceeds. A credential or a configured
codename escalates instead: their presence says the *subject* is sensitive, and the
scrubbed remainder (`"how is [REDACTED:term] viewed"`) would be a useless query that
still discloses someone is asking. Escalating on everything would refuse calls right
after successfully cleaning them, which teaches people to route around the gate.

**The audit trail never contains the query.** It stores SHA-256 hashes plus redaction
counts by kind — enough to prove what happened, correlate a complaint, and spot a
spike; not enough to reconstruct the question. Otherwise the audit table recreates the
exposure the gate exists to prevent, in a table that is widely readable and long-lived.

### Long-running research

`/v1/research` is submitted with `background: true` and never awaited inside a turn.
The task id goes into the LangGraph checkpoint; `era/agent/research_worker.py` polls
with capped backoff and writes the result back via `graph.aupdate_state`; the next
turn resumes at synthesis. The worker is a separate process on purpose — a serving
replica can be recycled at any time, and a thread waiting out a 12000-second tail
would take the pending research with it.

```bash
python -m era.agent.research_worker --thread-id <id> --task-id <task> \
    --lakebase-instance <instance>
# Finance Research has no task API, so the worker holds the blocking call:
python -m era.agent.research_worker --thread-id <id> --finance-query "..." \
    --lakebase-instance <instance>
```

## Milestone D: evaluation and the release gate

```bash
# Score saved answers with no workspace, no judges, no cost:
python -m era.eval.run_eval --offline-fixtures era/eval/fixtures.example.json

# Evaluate the deployed agent:
python -m era.eval.run_eval --endpoint <serving-endpoint>
python -m era.eval.run_eval --endpoint <endpoint> --no-judges
python -m era.eval.run_eval --endpoint <endpoint> --bucket governance
```

**Exit code 0 means the gate passed.** That is the entire contract with the deploy
job — it checks the code, it does not parse the output.

### Golden questions

Four buckets in `era/eval/datasets.py`, organised by what a question *requires*,
because that determines how a wrong answer goes wrong:

| Bucket | Failure it catches |
|---|---|
| `internal_only` | reaching for the web, or citing news for something the filing states |
| `external_only` | answering from training data and presenting it as retrieved |
| `blended` | mixing internal and external without saying which is which |
| `governance` | **addition beyond the three specified** — questions that must be *refused* |

The governance bucket is separated so you can drop it, but a gate that never tests
refusal only proves the agent works when nothing is at stake.

### Blocking vs advisory thresholds

`conf/release_gate.yaml` splits them, and the split is the important design decision.

**Blocking** metrics are governance properties with a right answer, scored
deterministically by `era.agent.provenance` — no judge model. A gate whose verdict
moves when nobody changed the agent is a gate people learn to re-run until it passes,
which is worse than no gate because it still produces a green tick.

**Advisory** metrics come from MLflow's LLM judges (`Correctness`, `RelevanceToQuery`,
`Safety`, plus a `Guidelines` judge on the provenance contract). Real signal, genuinely
non-deterministic. A judge having an off day must not hold up a deploy — and equally
must never be the only thing standing between a fabricated citation and production.

The gate also fails a run that evaluated too few questions or skipped a required
bucket. Otherwise a broken harness scores 1.0 across an empty set and reports green,
which is the most dangerous false pass available.

### The `[OPS]` tag — an addition the gate forced

Writing the harness surfaced a real flaw in Milestone C. `"That request was blocked by
policy"` is a statement about the *system*, not a claim about the world. With only
`[IV]`/`[EC]`/`[INF]` it was unrepresentable — not internal, not external, and calling
it inference would misstate where it came from. Left untagged it counted as an
unlabelled material claim, so **an agent that correctly refused a sensitive question
scored worse on provenance than one that answered it**, and the gate blocked the
deploy for doing the right thing.

A control that punishes correct behaviour gets weakened until it stops objecting. So
operational statements now carry `[OPS]`: they assert nothing about the subject, need
no evidence, and are always structurally valid. This widens the three-label contract
in the spec — drop it if you would rather keep the taxonomy at three, but the refusal
path needs some answer to this.

### Still to do for Milestone C

- Repoint `chatbot-app/` at the code-first endpoint (it already speaks the
  ResponsesAgent streaming contract) and keep Lakebase history.
- Log/register the agent to Unity Catalog and extend `databricks.yml` with the new
  resources. Databricks' current guidance is DABs rather than a separate deploy call,
  and era already has a bundle, so that is the path.
- Both need a verified Milestone A first.

## Egress policy

`conf/` is the source of truth. `era/connections/you_uc_functions.sql` is **generated**
from it — do not edit the SQL by hand, and `era/tests/test_uc_function_render.py`
fails the build if the two drift apart. A governance control that is documented in one
place and enforced in another is not a control.

- `domain_allowlist.yaml` — trusted sources, sent as `include_domains` in allow-mode.
- `domain_denylist.yaml` — never-acceptable sources, sent as `exclude_domains` in deny-mode.
- `routing_policy.yaml` — endpoint inventory, ZDR posture, effort and freshness defaults.

The two domain lists are **mutually exclusive per request** — the You.com Search API
rejects a call carrying both. The generated SQL enforces that structurally, so it is
not possible to call the function in a way that sends both.

## Things about You.com that will bite you

All verified against the live API reference on 2026-08-03. Re-verify before changing
any of them.

- **The base URL is split.** `ydc-index.io` serves `/v1/search` and `/v1/contents`;
  `api.you.com` serves `/v1/research`, `/v1/research/{task_id}` and
  `/v1/finance_research`. One connection cannot cover both — hence two.
- **REST auth is `X-API-Key`, MCP auth is a bearer token.** They are not
  interchangeable. A UC connection can only inject `Authorization: Bearer`, so the
  functions pass `X-API-Key` explicitly via `secret()`.
- **There is no news endpoint.** News arrives as `results.news[]` inside the ordinary
  search response.
- **Zero Data Retention is not a parameter.** It is an account-level enterprise term,
  applied server-side, and it currently covers `/v1/search` only. Research, Finance
  Research and Contents are **not** covered — see `zero_data_retention` in
  `routing_policy.yaml`, which is set to `account_enabled: false` until You.com
  confirms otherwise in writing.
- **`research_effort: frontier` requires `background: true`** — a synchronous frontier
  request returns 422. Research p50 is ~300s and can reach 12000s, which is why it
  belongs in a Python tool with checkpoint-and-resume rather than a SQL function.
- **Finance Research has no `background` flag**, so it cannot use You.com's task API.
  It needs an ERA-side worker driving the resume instead.

## Tests

```bash
python -m pytest era/tests/ -q                    # everything that runs offline
python -m pytest era/tests/ -m integration        # needs a live workspace
```

Integration tests skip cleanly unless `SERVING_ENDPOINT`, `MLFLOW_EXPERIMENT_ID` and
`ERA_WAREHOUSE_ID` are set.

The offline suite is not a formality — it holds the properties that are expensive to
check any other way: that the deployed egress policy equals the reviewed one, that no
ungoverned web tool can remain attached to the supervisor, that no credential is
inlined, and that per-request state cannot leak between concurrent callers.

## Layout

```
era/
├── agent/           # Milestone C: supervisor, prompts, provenance
│   ├── instructions/            # grafted KA/MAS instruction docs
│   └── _ref_banking_*.py        # reference skeletons (async resume, state machine)
├── connections/     # Milestone B: UC connections, generated UC functions, MAS wiring
├── ingest/          # grafted controlled Vector Search ingest (doc_id lineage)
├── eval/            # Milestone D: datasets, scorers, release gate
├── tests/
└── tools/           # serving contract, You.com tools, redaction gate
conf/                # egress policy — source of truth for the generated SQL
```

Files prefixed `_ref_` are read-only references copied from the banking accelerator,
kept for their async checkpoint/resume pattern. They are not wired into anything yet.

## Provenance and licensing

Grafted files carry a header naming their source repo, path and commit. The upstream
licence requires modified files to say they were modified; the header is how that
obligation is met. See `LICENSE.md` and `NOTICE.md` at the repo root.
