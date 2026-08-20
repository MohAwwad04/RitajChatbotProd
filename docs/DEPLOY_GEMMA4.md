# Deploying Gemma 4

Roadmap Phase 7. Two paths: the **Cloudflare Workers AI pilot** (recommended,
ADR-001) and the **Oracle self-host** (the independence/fallback path). Both are
configuration against the same OpenAI-compatible client, so switching is three
environment variables and a redeploy.

Nothing here can be executed from this repository: it needs a Cloudflare account
and token, an Oracle account, and a Hugging Face write token. See §4.

---

## 1. Cloudflare Workers AI (pilot)

### 1.1 Create a scoped token

Scope it to **Workers AI inference only** — not account-wide. A token that can
only run inference cannot create workers, read logs, or change billing if it
leaks. Note the account id; it appears in the base URL path.

### 1.2 Configure the host

Set as **Space secrets**, never in the repo, and never in the extension package:

```dotenv
LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
LLM_MODEL=@cf/google/gemma-4-26b-a4b-it
LLM_API_KEY=<token>
LLM_DAILY_NEURON_BUDGET=9000
ENVIRONMENT=production
CORS_ORIGINS=https://mohawwad04-ritaj-rag.hf.space
EXTENSION_ID=<known after the first store submission>
ADMIN_USERS=<username:bcrypt-hash pairs>
SESSION_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(48))">
```

The service refuses to start in production without admin auth, a real LLM key
and a non-wildcard CORS list (`config.check_production_config`). That is
deliberate: each of those has silently shipped before.

### 1.3 Verify before deploying

```bash
python -m pytest tests/test_provider_contract.py -q   # wire shapes, failure modes
python scripts/secret_inventory.py                    # names + fingerprints only
```

Then a single live call, once the token exists, to confirm the account is
enabled for the model:

```bash
curl -sS "$LLM_BASE_URL/chat/completions" \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"@cf/google/gemma-4-26b-a4b-it","messages":[{"role":"user","content":"Reply with OK"}],"max_tokens":5}'
```

### 1.4 Budget

Cloudflare's free allocation is **10,000 neurons/day**. It publishes Gemma 4 26B
A4B at **$0.10 per million input tokens** and **$0.30 per million output tokens**
(verified against the model documentation on 2026-08-05), and bills neurons at
**$0.011 per 1,000**. So:

```text
input    $0.10/M  ÷  $0.011/1000  =   9,091 neurons per million input tokens
output   $0.30/M  ÷  $0.011/1000  =  27,273 neurons per million output tokens
```

A representative RAG request (4,000 input + 500 output) is about **50 neurons**,
making the daily allowance roughly **200 answers**.

`LLM_DAILY_NEURON_BUDGET=9000` trips below the provider's limit, so students get
a sentence they can act on rather than an opaque error mid-stream.

The budget is metered from the provider's own `usage` block at every call
(`llm.py`), not counted per answer. That distinction matters: `generate.condense()`
makes a second call to rewrite each follow-up, which per-answer accounting missed
entirely, and a short question costs a fraction of a long one carrying six turns
of context. `/admin/usage` reports neurons used, provider calls made, and the
rates in effect.

**Reconcile against the Cloudflare dashboard during the pilot.** Cloudflare does
not publish a neurons-per-token figure for this model directly — the rates above
are derived from its dollar prices — and there have been community reports of
billing discrepancies on this model. Treat the budget as a guard rail, not an
exact meter; `NEURONS_PER_M_INPUT` / `NEURONS_PER_M_OUTPUT` exist so the
conversion can be corrected without a code change.

Other verified facts, same date: the model id is `@cf/google/gemma-4-26b-a4b-it`,
the context window is 256,000 tokens, streaming is supported via `stream: true`,
and the OpenAI-compatible `/v1/chat/completions` endpoint is available — which is
what makes this a configuration change rather than a client rewrite.

### 1.5 Deploy

```bash
git tag -a v1.1.0 -m "side panel + navigation + Ritaj-only corpus"
python scripts/build_index.py --publish          # needs approved sources (§4.3)
python scripts/release_manifest.py --require-clean -o release/manifest.json
python scripts/deploy_space.py --space staging   # staging first, always
# ... run the smoke, golden, red-team and navigation suites against staging ...
python scripts/deploy_space.py                   # promote the same artifacts
```

Production refuses a dirty tree with no override. Watch `/ready` after the
build: it reports the state, the startup timings and the corpus version.

---

## 2. Oracle Always Free self-host (fallback)

Oracle's Always Free A1 allocation is 2 OCPU and 12 GB RAM **across the
account**. `gemma4:e2b` under Ollama is about 7.2 GB on disk.

### 2.1 Topology

Use the **split topology** first: the Hugging Face Space keeps running the RAG
app (embedder, reranker, index, API) and Oracle runs only Gemma. Putting the
E5-large embedder, the BGE-M3 reranker, Qdrant *and* Gemma in one 12 GB box will
swap or get OOM-killed. Do not promise otherwise without measurement.

### 2.2 Build

1. Always Free A1 instance, full 2 OCPU / 12 GB, Ubuntu ARM64, in the account's
   home region.
2. Boot volume large enough for OS + model + container images + logs.
3. Install Ollama ARM64 (or build llama.cpp) and pull the exact quantized
   `gemma4:e2b` package. Record the digest — "gemma4:e2b" is a moving tag.
4. **Bind the model server to loopback only.**
5. Caddy or Nginx in front: HTTPS, a long bearer token, request size limits,
   concurrency 1, timeouts, and access logs **without prompt bodies**.
6. Firewall: SSH from a restricted source, HTTPS 443. Port 11434 is never
   exposed.
7. Context window at the measured RAG requirement — start at 8K, not 128K. A
   long KV cache costs memory that this box does not have.
8. Disable model unloading if memory permits; otherwise document the cold-load
   time, because it becomes the first student's latency.

### 2.3 Benchmark before believing it

Record, for both Arabic and English:

| Metric | Why |
|---|---|
| first-token latency (p50, p95) | the SLO students feel |
| tokens/second | whether a full answer completes in time |
| peak RSS + swap growth | whether it survives a day |
| two simultaneous requests | whether one student blocks another |
| answer quality vs. the pilot | whether independence costs accuracy |

Then point staging at Oracle and run the full evaluation set. Only after that is
it a decision rather than a preference.

### 2.4 Operational risks — not footnotes

- Oracle reclaims idle Always Free instances when CPU, network and A1 memory
  utilization stay below its thresholds for seven days.
- Free A1 capacity is regularly unavailable in a given region.
- There is no second instance to fail over to.

Back up configuration and the corpus artifact, and keep the Cloudflare path
configured so a switch is an environment change.

### 2.5 Single-server experiment

Only after the split topology works. Replace E5-large and the BGE-M3 reranker
with a measured light retrieval profile, ship the prebuilt index, one process,
capped concurrency. Require a 24-hour memory soak with no swap growth and no OOM
before considering it for release.

---

## 3. Rollback

| Symptom | Action |
|---|---|
| Provider erroring or throttling | circuit breaker opens automatically; students get `LLM_UNAVAILABLE` |
| Quota exhausted early | lower `LLM_DAILY_NEURON_BUDGET`; students get `LLM_BUDGET_EXHAUSTED` |
| Bad answers from a new corpus | point `data/corpus/CURRENT` at the previous version, redeploy |
| Wrong navigation destination | `enabled: false` in `data/navigation.yaml`, redeploy |
| Bad backend build | redeploy the previous tag |

No server-side rollback depends on a Chrome Web Store review.

---

## 4. What this repository cannot supply

1. **Cloudflare account id + scoped Workers AI token** — without it the pilot
   endpoint is unconfigured and production refuses to start.
2. **Hugging Face write token + access to the Space** — without it nothing can
   be deployed or the current 503 repaired.
3. **An approved Ritaj corpus** — `build_index.py --publish` exits with "no
   approved sources" until Birzeit authorization or an approved export exists
   (`data/quarantine/README.md`). Deploying without it gives a service that
   starts, reports `not-ready`, and abstains from every question.
4. **The Chrome Web Store extension id** — needed for the production CORS
   allowlist, and only known after the first submission.
5. **An Oracle account and region** — for the self-host benchmarks in §2.3.

---

## 5. Hugging Face Space specifics

Folded in from `DEPLOYMENT.md`, which this document supersedes. These are the
host facts that survived the provider change and the popup→side-panel
conversion; everything else in that file described a build that no longer
exists.

- **A fine-grained HF token 403s on Space creation.** `scripts/deploy_space.py`
  needs a **Write** token.
- **The Space runtime user is non-root (UID 1000).** Writable paths must live
  under `/tmp` — hence `QDRANT_PATH=/tmp/qdrant` — and any baked cache directory
  needs its permissions opened at build time.
- **Embedded Qdrant survives the two-process startup because it is on disk.**
  `ensure_index.py` runs as a separate process and writes `/tmp/qdrant`; uvicorn
  then reads it. A `:memory:` client would not cross the process boundary, and
  the service would come up with an empty store and answer nothing.
- **The Space serves the privacy policy itself** at `/privacy`
  (`src/ritaj/static/privacy.html`), which is the URL the store listing and the
  extension both point at. A gist copy will drift; the served page cannot,
  because `scripts/check_privacy.py` reads it.
- **`/live` binds before initialization.** Anything moved in front of the port
  bind reproduces the outage that made the platform kill the container as
  unhealthy — see `CLAUDE.md` §"Architecture invariants".

Admin accounts, secret rotation and the incident runbook live in
[`OPERATIONS.md`](OPERATIONS.md) §3, not here.
