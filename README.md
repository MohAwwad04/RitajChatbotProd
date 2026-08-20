# Ritaj Assistant

> ENCS5342 Course Project — NLP_Project

An **independent, student-built** assistant for Birzeit University's Ritaj
portal. It is not an official Birzeit service and is not endorsed by the
university.

Ask a question in Arabic or English; get a short answer built only from approved
Ritaj pages, with the page it came from and when that page was captured. When
navigation helps, the answer offers a button that opens a reviewed
`ritaj.birzeit.edu` page — after you click it.

**Clients:** a Chrome **side panel** extension (`chrome-extension/`), a React
student portal served at `/`, and a login-gated operator console at `/admin`.

---

## Current status — read this first

**Not ready to release.** The implementation is advanced; the data, deployment
and approval gates are not.

| | |
|---|---|
| **There is no production corpus** | All 22 previous documents failed the Ritaj-only source policy and are quarantined. `data/sources.yaml` is a review queue — every record is `approved: false`. The service starts, reports `not-ready`, and abstains from every question until an authorized Ritaj export exists. |
| **Nothing is deployed** | The public Space returns 503 and runs an older commit. Repairing it needs a Hugging Face write token. |
| **No provider credentials** | Production refuses to start without a real `LLM_API_KEY`, admin auth, and a non-wildcard CORS list. |

Do **not** "fix" the empty corpus by adding content. Read
[`data/quarantine/README.md`](data/quarantine/README.md) first — the rule is
that a production record's canonical source must be exactly
`https://ritaj.birzeit.edu`, with an owner, a snapshot, a hash and a named
approver.

Because there is no corpus, **the portal's home view reports zero approved
topics and zero navigation destinations, and the assistant abstains from every
question.** That is the product working as designed, not a broken build — the
home view is rendered from `GET /capabilities`, so it can only ever show what
has actually been approved.

Full picture: [`cowork_ritaj/COWORK_PLAN.md`](cowork_ritaj/COWORK_PLAN.md) (the
current work order),
[`READY_TO_RELEASE_EXECUTION_PLAN.md`](READY_TO_RELEASE_EXECUTION_PLAN.md) and
[`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md).

---

## Documentation

| Document | What it is for |
|---|---|
| [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) | What "ready" means, with a runnable command per item |
| [`READY_TO_RELEASE_EXECUTION_PLAN.md`](READY_TO_RELEASE_EXECUTION_PLAN.md) | The phase-by-phase plan to get there |
| [`RELEASE_ROADMAP_2026.md`](RELEASE_ROADMAP_2026.md) | The architecture and policy decisions being implemented |
| [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md) | Branch model, CI gates, rollback matrix |
| [`docs/DEPLOY_GEMMA4.md`](docs/DEPLOY_GEMMA4.md) | Cloudflare Workers AI pilot + Oracle self-host runbook |
| [`docs/SECURITY_THREAT_MODEL.md`](docs/SECURITY_THREAT_MODEL.md) | Threats, controls, and residual risk |
| [`docs/adr/`](docs/adr/) | ADR-001 provider choice · ADR-002 navigation-only automation |
| `PLAN.md`, `PLAN_EXPLAINED.md`, `process.md` | **Historical.** The original design, written before the Ritaj-only data boundary. Superseded wherever they conflict with it. |

## Stack

- **LLM:** Gemma 4 through any OpenAI-compatible endpoint. Ollama in
  development; **Cloudflare Workers AI** (`@cf/google/gemma-4-26b-a4b-it`) is the
  selected pilot host — see [ADR-001](docs/adr/ADR-001-llm-provider.md). Switching
  is three environment variables.
- **Retrieval:** dense (`intfloat/multilingual-e5-large`) + BM25, RRF-fused,
  then a `BAAI/bge-reranker-v2-m3` cross-encoder, then metadata policy and a
  calibrated abstention floor. Model revisions are pinned.
- **Vector store:** Qdrant — embedded on disk in the container, a server in dev.
- **API:** FastAPI. `/live`, `/ready`, `/capabilities`, `/chat`,
  `/v2/chat[/stream]`, `/admin/*`.

**Conversation memory** is client-owned: each client replays its prior turns
(`history`) plus a `session_id`; the server clamps them, condenses follow-ups
into a standalone retrieval query, and stays stateless.

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env          # then edit: LLM endpoint, admin auth, limits
ollama pull gemma4:e4b        # development LLM (gemma4:e2b on lighter machines)
docker run -p 6333:6333 qdrant/qdrant
```

Build a **development** index from the quarantined corpus — clearly marked
unapproved, and refused in production:

```bash
python scripts/build_index.py --dev
uvicorn ritaj.api:app --reload --app-dir src
```

Building the *production* index requires approved sources and will tell you so:

```bash
python scripts/build_index.py --publish
```

## Checks

Everything below runs in CI on every pull request:

```bash
pytest -q                                   # backend unit + integration
node --test chrome-extension/navigation.test.mjs
python scripts/check_corpus_policy.py       # every chunk traces to an approved Ritaj URL
python scripts/check_navigation.py          # destinations reviewed; URL attacks rejected
python scripts/check_extension.py           # minimal permissions; allowlist + limit parity
python scripts/check_privacy.py             # disclosures match the code
python scripts/eval_release.py              # scope refusals, injection, URL rejection
python scripts/secret_inventory.py          # secrets present; nothing committed
python scripts/sbom.py --check-pinned       # deployables reproducible
python scripts/lock_deps.py --check         # dependency lock is current
cd ritaj-student-portal && npm run lint && npm run build
```

## Architecture invariants

Changes must preserve these. Each has a test and a CI gate.

- **The LLM never produces a URL.** Navigation resolves an action *id* from a
  reviewed registry; the server maps it to a destination and the extension
  re-validates independently before opening a tab ([ADR-002](docs/adr/ADR-002-navigation-only-automation.md)).
- **Only approved records are indexed.** The old folder scan survives solely as
  a development path and raises in production.
- **`/live` never touches a model, the store or the network.** Initialization
  runs on a background thread — putting work in front of the port bind is what
  caused the outage this release recovers from.
- **Errors leave as stable codes.** Provider text, filesystem paths and
  tracebacks stay in the protected log, including on `/ready`.
- **Telemetry is aggregate by default** — no question or answer text.
- **The extension reads no page data**, and holds no permission that would let
  it.

## Security

Never commit or paste API keys. `scripts/secret_inventory.py` scans for them.
`ritaj_rag_admins.rtf` (plaintext operator passwords) is gitignored and **those
accounts still need rotating** before any deployment.
