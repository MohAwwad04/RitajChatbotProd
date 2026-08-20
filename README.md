# Ritaj Assistant

An independent, student-built assistant for Birzeit University's **Ritaj** portal.
Ask in Arabic or English, get a grounded and cited answer, or a button to the
right Ritaj page.

**Not an official Birzeit service and not endorsed by the university.**

**Live:** https://mohawwad04-ritaj-rag.hf.space

> **Operational detail lives in [`HANDBOOK.md`](HANDBOOK.md)** — state,
> architecture, deployment, corpus handling, release, operations, security and
> decisions. This file and that one are the only two you need.

---

## What it does, and what it refuses to do

| Does | Refuses |
|---|---|
| Answers from approved public Ritaj pages, with citations | Answering without a source — it abstains instead |
| Opens a reviewed Ritaj page after you click | Reading the page you are on, your cookies or your account |
| Works in Arabic and English, RTL included | Registering, dropping, paying or submitting anything |
| Finds pages even when chat is unavailable | Producing a URL the model invented |

The refusals are the design, not missing features. A plausible answer must not
be able to move a student's browser, and an answer with no approved source is
not an answer.

---

## Current state

The backend is live on free hosting at $0, with Cloudflare Gemma 4 answering and
a Qdrant Cloud vector database connected.

**There is no approved corpus yet**, so factual chat reports `NO_CORPUS` and
abstains. The page finder works. That is the honest state, and
[`HANDBOOK.md` §5](HANDBOOK.md) is the path out of it.

```
pytest -q                       406 passed
node --test (3 suites)           29 passed
node scripts/e2e_extension.mjs   20/20 in real Chromium
5 policy gates                   green
```

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env                 # defaults to Ollama + local Qdrant

pytest -q                            # model-free
uvicorn ritaj.api:app --reload --app-dir src
```

Then open http://127.0.0.1:8000 for the portal, or load
`chrome-extension/` unpacked at `chrome://extensions` for the side panel.

To exercise the whole pipeline before an approved corpus exists:

```bash
python scripts/build_index.py --dev  # dev corpus, refused in production
```

---

## Layout

```
src/ritaj/              FastAPI backend — retrieval, guardrails, generation, navigation
ritaj-student-portal/   React portal, served by FastAPI at /
chrome-extension/       MV3 side panel (storage + sidePanel permissions only)
data/sources.yaml       the corpus review queue — nothing is indexed until approved
data/navigation.yaml    the only destinations this product will ever open
scripts/                gates, evaluations, build, deploy, refresh
docs/OPERATIONS.md      ownership and drills (parsed by check_operations.py)
```

---

## The parts worth knowing before you change anything

- **The LLM never produces a URL.** It can name an action id that a human
  already approved; the server maps it, and the extension validates it again.
- **Only approved records are indexed**, and approval means a named person, a
  checksum and a date.
- **`/live` touches no model, store or network.** Work in front of the port bind
  is what caused the original outage.
- **Navigation never depends on the corpus or the model**, so the page finder
  survives an outage.

Full list, each with its enforcing test, in [`HANDBOOK.md` §2](HANDBOOK.md).

---

## Contributing

Every gate runs in CI and each is runnable locally:

```bash
python scripts/check_corpus_policy.py --release
python scripts/check_navigation.py
python scripts/check_extension.py
python scripts/check_privacy.py
python scripts/check_error_messages.py
```

The full definition of ready is [`HANDBOOK.md` §6](HANDBOOK.md).

---

## Licence and status

An independent student project. It carries no university endorsement, makes no
availability guarantee, and runs on free tiers with no SLA.
