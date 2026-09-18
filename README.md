# Meridian National Customer Service Concierge — Azure AI Foundry

A personal-banking customer service agent. It runs on a LangGraph `StateGraph`
and answers questions from a synthetic knowledge base plus mocked customer-data
tools. All inference runs on **Azure AI Foundry**. The agent calls Foundry
directly. There is no gateway in the request path.

Three model calls use Foundry:

- The agent chat model (`src/concierge/graph.py`).
- The retrieval embeddings (`src/concierge/retrieval.py`).
- The offline eval judge (`evals/evaluators.py`).

All three read one endpoint and one auth setting from `.env`. See
[Setup](#setup).

## What's in here

```
src/concierge/
  azure_foundry.py   Builds the Foundry chat + embeddings clients (endpoint + auth)
  graph.py           StateGraph -> agent (LLM) <-> ToolNode
  app.py             FastAPI custom routes (mounts the React UI at /concierge/)
  state.py           MessagesState + retrieval_calls counter
  context.py         Pulls the system prompt (AGENTS.md) from LangSmith Context Hub at runtime
  context_hub.py     Seeds the hub AGENTS.md + show-only SKILL.md repos
  governance.py      Shared names: Application tag, review queue, feedback rule
  prompts.py         System prompt seed pushed to the hub + offline fallback
  tools.py           search_banking_docs + 4 mocked banking tools
  retrieval.py       In-memory vector store over kb/*.md
  mock_data.py       Fake customers, transactions, branches
  kb/                ~20 synthetic banking FAQ markdown docs
frontend/
  src/               React + assistant-ui chat client (Vite + Tailwind v4)
scripts/
  load_generation.py     Runs mixed conversations against the agent
  setup_context_hub.py   Seeds the hub with AGENTS.md + demo skills
  setup_workspace.py     Review queue + Application grouping + thumbs-down routing rule
  setup_online_evals.py  Online LLM-judge run rules on the tracing project
  teardown_context_hub.py  Delete context hub artifacts
evals/
  evaluators.py            LLM judges (hallucination, trajectory) + pii_leak_rate regex check
  run_experiment.py        aevaluate(...) runner; pick golden / pii / hallucinations
  dataset_snapshot.py      Export / restore datasets to/from committed JSON
  dataset_golden.json      Committed snapshot of banking-concierge-golden
  dataset_hallucinations.json  Committed snapshot of banking-concierge-hallucinations
  dataset_pii.json         Committed snapshot of banking-concierge-pii
langgraph.json       Deployment manifest (graphs + http.app) for LangSmith Cloud
rubric.md            Annotation-queue rubric for human review of flagged traces
```

## Prerequisites

- Python 3.13 and [`uv`](https://docs.astral.sh/uv/).
- An Azure AI Foundry project with two deployments: a chat model and an
  embeddings model.
- A LangSmith account for tracing, datasets, and deployment.

## Setup

Install dependencies and create your `.env`:

```bash
uv sync
cp .env.example .env
```

Set these Azure AI Foundry variables in `.env`:

| Var | Purpose |
|---|---|
| `AZURE_AI_PROJECT_ENDPOINT` | Your Foundry project endpoint (from the Foundry portal, project Overview) |
| `AZURE_AI_API_KEY` | Your Foundry API key. Leave empty to use Microsoft Entra ID instead |
| `CONCIERGE_MODEL` | Chat model **deployment name** (default `gpt-4o-mini`) |
| `CONCIERGE_EMBEDDING_MODEL` | Embedding model **deployment name** (default `text-embedding-3-small`) |
| `EVAL_JUDGE_MODEL` | Judge deployment name for offline evals (default `gpt-4o`) |

Set these LangSmith variables in `.env`:

| Var | Purpose |
|---|---|
| `LANGSMITH_API_KEY` | Tracing, datasets, experiments, deployment |
| `LANGSMITH_TRACING` | `"true"` to send traces |
| `LANGSMITH_PROJECT` | Tracing project name |
| `LANGSMITH_WORKSPACE_ID` | Workspace the Context Hub repo is seeded into |

### Authentication

The agent supports two auth methods. Pick one:

- **API key:** set `AZURE_AI_API_KEY`. This is the fastest way to start.
- **Microsoft Entra ID:** leave `AZURE_AI_API_KEY` empty. The clients then use
  `DefaultAzureCredential`. Run `az login`, or assign a managed identity, and
  grant it the **Azure AI Developer** role on the Foundry project.

### Seed Context Hub (one-time)

The agent pulls its system prompt from LangSmith Context Hub. Seed the hub
before the first run:

```bash
uv run python -m scripts.setup_context_hub
```

This creates the `banking-concierge-agent` repo (with `AGENTS.md`) and a few
show-only skill repos. Until you run it, `get_prompt()` falls back to the seed
in `prompts.py`, so the agent still works.

To reset the hub for a clean prompt history:

```bash
uv run python -m scripts.teardown_context_hub --yes
uv run python -m scripts.setup_context_hub
```

## Run locally

```bash
# one-time: build the chat UI (only needed for /concierge/, not for Studio)
npm --prefix frontend install
npm --prefix frontend run build

# start the agent server + custom routes
uv run langgraph dev
```

`langgraph dev` serves two UIs:

- **`http://localhost:2024/concierge/`** — the custom React chat UI (the main
  UI), served by `src/concierge/app.py` from `frontend/dist/`. Build it first,
  or the page returns a 503 with a "run npm build" hint.
- **`http://localhost:2024/app/`** — LangGraph Studio, the built-in debugger.
  It works with no frontend build.

`http://localhost:2024/` redirects to `/concierge/`.

To iterate on the frontend without a rebuild, run the Vite dev server in a
second terminal:

```bash
npm --prefix frontend run dev   # hot-reloading UI on http://localhost:5173
```

Open `http://localhost:5173`. Keep `uv run langgraph dev` running on `:2024` —
Vite proxies the agent endpoints to it.

## Generate load

```bash
# in-process against the local compiled graph
uv run python scripts/load_generation.py --mode local --n 150

# against a deployed LangSmith assistant
uv run python scripts/load_generation.py --mode remote --n 150 \
    --url $LANGGRAPH_DEPLOYMENT_URL
```

Each run is tagged with `loadgen` and `category:<intent>` so you can filter the
traces by category in LangSmith.

## Create the evaluation datasets

The datasets restore from committed JSON snapshots, so setup is deterministic:

```bash
uv run python evals/dataset_snapshot.py restore golden --reset
uv run python evals/dataset_snapshot.py restore hallucinations --reset
uv run python evals/dataset_snapshot.py restore pii --reset
```

## Run the offline experiment

```bash
uv run python evals/run_experiment.py golden          # golden suite
uv run python evals/run_experiment.py hallucinations  # hallucination dataset
uv run python evals/run_experiment.py pii             # PII-leak dataset
```

`run_experiment.py` takes the dataset as a positional argument. Each choice
selects its dataset name, evaluators, and experiment prefix. The judge runs on
Azure AI Foundry using `EVAL_JUDGE_MODEL`.

## Score live traces (online evals)

Offline experiments grade a fixed dataset. Online evals grade production traces
as they arrive.

```bash
uv run python -m scripts.setup_online_evals                   # score every trace
uv run python -m scripts.setup_online_evals --sampling-rate 0.2
```

The script creates one LangSmith run rule per evaluator. Re-running it deletes
and recreates the rules, so it is safe to repeat. Rules score only traces that
arrive after you create them.

This judge runs server-side in LangSmith, not in this app. It resolves its model
from a **workspace Provider Secret**, not from `.env`. Configure that secret for
your Azure provider under **Settings → Workspace → Secrets**, and set
`EVAL_JUDGE_MODEL` to the deployment name.

## Group the workspace and route feedback for review

```bash
uv run python -m scripts.setup_workspace
```

Run it after the first trace exists and the datasets are restored. It does three
things, and re-running it is safe:

1. Creates the **`Meridian National: Negative Feedback Review`** annotation
   queue.
2. Tags every resource with the reserved **`Application`** tag value
   `banking-concierge`, so the project, datasets, queue, and Context Hub repos
   group under one application.
3. Creates the **`Negative Feedback`** run rule: any run scored
   `user_feedback = 0` is routed into the review queue.

> Tagging needs Plus/Enterprise. Creating the `Application` tag *value* needs
> workspace-admin.

## Repeatable evals via GitHub Actions

`.github/workflows/evals-on-pr.yml` runs `run_experiment.py` on every pull
request. A strategy matrix fires one parallel job per dataset and posts a PR
comment per dataset linking to that experiment.

Required GitHub configuration:

- Secrets: `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_API_KEY`, `LANGSMITH_API_KEY`,
  `LANGSMITH_WORKSPACE_ID`.
- Variables (optional): `LANGSMITH_PROJECT`, `CONCIERGE_MODEL`,
  `CONCIERGE_EMBEDDING_MODEL`, `EVAL_JUDGE_MODEL`.

## Deploy to LangSmith Cloud

```bash
# Build the frontend first — its dist/ is what the deployment serves
npm --prefix frontend install
npm --prefix frontend run build

uv tool install langgraph-cli
uv run langgraph deploy
```

The manifest (`langgraph.json`) registers one assistant `agent`
(`src/concierge/graph.py:graph`) and one custom HTTP app
(`src/concierge/app.py:app`) that mounts the React UI at `/concierge/`.

Set the Azure AI Foundry and LangSmith environment variables on the deployment
so the agent can reach Foundry at runtime.

LangSmith Cloud protects the default `/threads`, `/runs`, and `/assistants`
endpoints with the workspace API key. The React client passes the key two ways:

- **URL parameter:** open
  `https://<deployment>.us.langgraph.app/concierge/?api_key=lsv2_pt_...` once.
  The frontend saves the key and strips it from the URL.
- **Manual:** `localStorage.setItem("concierge:apiKey", "lsv2_pt_...")` from the
  browser console.
