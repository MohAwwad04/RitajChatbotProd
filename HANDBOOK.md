# Ritaj Assistant — Handbook

**Everything operational, in one file.** State, architecture, deployment, corpus
handling, release, operations, security, decisions, and what remains.

Companion documents: [`README.md`](README.md) — what this is and how to run it;
[`STATUS.md`](STATUS.md) — what is broken right now and which decision is
waiting. §12 lists what these replaced.

> **As of 21 Aug the model call does not work in production.** The Hugging Face
> container cannot complete a TLS handshake to Cloudflare's API — zero provider
> calls have ever succeeded from it. Everything else in this handbook is live and
> verified. See `STATUS.md` before relying on any answer path.

**Last measured:** 20 August 2026. Every figure below came from running the
command beside it. Where something is unmeasured, it says so.

---

## 1. Current state

Live at **https://mohawwad04-ritaj-rag.hf.space**, on free tiers, at $0.

| Component | Where | State |
|---|---|---|
| Backend | Hugging Face Space, `cpu-basic` | RUNNING, binds its port in 1.2 s |
| LLM | Cloudflare Workers AI, `@cf/google/gemma-4-26b-a4b-it` | Answering |
| Vector DB | Qdrant Cloud free, AWS `us-east-1` | Connected, empty |
| Portal | React, served by FastAPI at `/` | Live |
| Extension | MV3 side panel, v1.2.0 | Built; Store listing not yet updated |
| Navigation | 4 reviewed destinations | Live |

```
pytest -q                      406 passed
node --test (3 suites)          29 passed
node scripts/e2e_extension.mjs  20/20 in real Chromium
5 policy gates                  green
navigation eval                 22 cases, 100% precision, 100% recall
verify_qdrant_remote.py         13/13 against the real cluster
```

**One blocker remains and it is the whole of the remaining work: there is no
approved corpus.** The service starts, reports `NO_CORPUS`, and abstains on
factual questions. That is the design working. See §5.

---

## 2. Architecture

```
student ──► Chrome side panel ──┐
                                ├─► FastAPI ─┬─► retrieval: Qdrant + BM25, RRF-fused
student ──► React portal ───────┘            │              └─► cross-encoder rerank
                                             ├─► guardrails + abstention
                                             ├─► Cloudflare Gemma 4 (answer text only)
                                             └─► navigation: action id → reviewed URL
```

Hybrid retrieval (dense + BM25, RRF-fused) → cross-encoder rerank → metadata
policy + abstention → grounded, cited answer. Arabic normalization and
input/output guardrails throughout.

Conversation memory is **client-owned**: clients send `history` + `session_id`
with each request; the server clamps it, condenses follow-ups for retrieval
(`generate.condense`), and stays stateless.

### Invariants — do not break these

Each has a test and a CI gate.

- **The LLM never produces a URL.** Navigation resolves an action *id* from
  `data/navigation.yaml`; the server maps it to a reviewed destination and the
  extension re-validates independently before `chrome.tabs.create`. The most a
  model can contribute is choosing an id a human already approved.
- **Navigation never depends on corpus, model or quota readiness.**
  `/v2/navigation/{actions,resolve}` are gated on the registry alone, and the
  extension bundles `actions.generated.js` so the page finder works with the
  backend unreachable.
- **Two separate URL policies, never merged.** `navigation.js` = one host, five
  reviewed paths, for steering the browser. `links.js` = official Birzeit hosts,
  for rendering a citation. `links.test.mjs` has two tests that fail first if
  anyone tries to unify them.
- **Only approved records are indexed.** `ingest.build_from_sources` refuses
  anything `approved: false`; the old folder scan raises in production.
- **`/live` never touches a model, the store or the network.** Initialization
  runs on a background thread. Putting work in front of the port bind is what
  caused the original `Launch timed out` outage.
- **Errors leave as stable codes** (`src/ritaj/errors.py`). Provider text and
  tracebacks stay in the protected log.
- **Telemetry is aggregate by default** — no question or answer text.
- **The clients describe only what the backend does.** `check_privacy.py` fails
  the build if UI copy claims record access.

### Readiness is per-capability

`/capabilities` returns `modes`:

| Mode | Means | Depends on |
|---|---|---|
| `live` | the process answers | nothing |
| `navigation_ready` | a reviewed destination exists | the registry only |
| `retrieval_ready` | store and embedder work | corpus |
| `generation_ready` | provider configured, circuit closed, budget left | Cloudflare |
| `ready` | full factual chat | the AND of the parts |

---

## 3. Running it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env          # defaults to Ollama + local Qdrant

pytest -q                     # model-free, the CI gate
uvicorn ritaj.api:app --reload --app-dir src
```

Tests run with `STARTUP_INIT=0` and `ENVIRONMENT=development`
(`tests/conftest.py`). Production is fail-closed and refuses to start
misconfigured.

To exercise the full pipeline without waiting for an approved corpus:

```bash
python scripts/build_index.py --dev    # indexes data/quarantine, clearly labelled
```

This is refused when `ENVIRONMENT=production`. The quarantined documents failed
the source policy and **must never reach a production index** — see §5.

### Seeing the extension

```bash
node scripts/screenshot_panel.mjs      # renders the panel at real dock widths
node scripts/e2e_extension.mjs         # 20 checks in real Chromium
```

`chrome://extensions` → Developer mode → **Load unpacked** → `chrome-extension/`.
Clicking the toolbar icon is the one thing no test covers: Playwright cannot
drive Chrome's side panel (microsoft/playwright#26693).

---

## 4. Deployment

### Configuration

Secrets and variables are pushed from the deploying shell, never from a file in
the repo. Keep them in the gitignored `.env.local`.

```bash
set -a; source .env.local; set +a
cd ritaj-student-portal && npm ci && npm run build && cd ..
python scripts/deploy_space.py "what changed"
```

The deploy refuses **before uploading** if a fail-closed setting is missing, and
names it. The container validates the same values at boot, but by then it has
spent twenty minutes building.

| Setting | Where it goes | Note |
|---|---|---|
| `LLM_API_KEY`, `LLM_BASE_URL` | secret | the base URL embeds the Cloudflare account id |
| `QDRANT_API_KEY`, `QDRANT_URL` | secret | the URL embeds the cluster id |
| `ADMIN_USERS`, `SESSION_SECRET` | secret | bcrypt hashes only, never plaintext |
| everything else | variable | publicly viewable on the Space settings page |

An **empty** value clears the setting; an **absent** one leaves it alone. That
distinction matters: `QDRANT_MODE=remote` requires `QDRANT_PATH` to be empty.

### Traps that have actually bitten

- **`QDRANT_PATH` is baked into the image** as an `ENV`. An image `ENV` cannot be
  removed by clearing a platform variable — `scripts/start.sh` unsets it when
  `QDRANT_MODE=remote`.
- **Name collisions.** HF refuses to start a Space where one name exists as both
  a variable and a secret. `deploy_space.py` clears the wrong namespace first.
- **Everything the Dockerfile `COPY`s must be staged.** Derived from the
  Dockerfile itself, so a new `COPY` fails before upload rather than 20 minutes
  later.
- **Do not delete the HF Space.** Hugging Face now requires a paid plan to
  *create* a Docker Space; this one predates that rule and still requests free
  `cpu-basic`.

### Free-tier limits, verified 20 Aug 2026

| Provider | Limit |
|---|---|
| Cloudflare Workers AI | 10,000 neurons/day, no card. ~20 neurons/answer measured, ~44 extrapolated to a 4,000-token prompt → **roughly 200–500 answers/day** |
| HF Space | 2 vCPU, 16 GB RAM, 50 GB **non-persistent** disk. Sleeps after 48 h idle (`gcTimeout: 172800`) |
| Qdrant Cloud | 0.5 vCPU, 1 GB RAM, 4 GB disk. **Suspended after 1 week idle, deleted after 4** |

### Fallback if the Space becomes ineligible

Oracle Always Free A1 (2 OCPU / 12 GB ARM). Put only the app there with remote
LLM and DB; do not self-host the model and the app on one free box without
measuring first. Expose only SSH from operator IPs and HTTPS; never expose
Ollama's port directly.

---

## 5. The corpus — the critical path

### The rule

A record may be indexed only if its canonical source is **exactly
`https://ritaj.birzeit.edu`**, it is public, it was acquired through an
authorized path, and **a named person approved it**. Not a role. Not "team".

All 22 previous documents failed this and live in `data/quarantine/`. Three were
partly fabricated and cited anyway. **Copying them into `data/snapshots/` does
not launder their provenance** — read `data/quarantine/README.md` first.

### Acquisition cannot be automated

`ritaj.birzeit.edu` answers **403 to every automated request** — verified across
`/`, `/academic-calendar` and `/robots.txt`, with and without a browser
User-Agent. Defeating that Cloudflare challenge is out of scope, and it would
falsify this project's central claim.

So a human saves the page. Everything either side is automated.

### Intake — from a saved page to a published corpus

```bash
# 1. save the page from a signed-out browser into:
#    data/snapshots/<corpus-version>/<source-id>.<ext>

python scripts/build_index.py --rehash        # 2. get its sha256

# 3. fill content_path, fetched_at, sha256 in data/sources.yaml (approved stays false)
# 4. read it: no personal data, no placeholder text, dates correct, honest refresh window
# 5. approved: true + approved_by: "<name>"   — one record per commit

python scripts/check_corpus_policy.py --release   # 6. must exit 0, non-vacuously
python scripts/build_index.py --publish           # 7. versioned artifact + CURRENT
```

Arabic and English are approved **separately, by their own owners**. One person
signing off text they cannot read is not an approval.

### Keeping it current

```bash
python scripts/refresh_sources.py --report              # what is overdue, and by how long
python scripts/refresh_sources.py --update <id> <file>  # record a re-saved page
```

`--update` answers the question that matters more than "is it time to look
again": **did the content actually move?**

- **Unchanged** → `fetched_at` bumped, approval untouched, staleness cleared.
  Nobody re-reviews text they already reviewed.
- **Changed** → approval withdrawn, the record leaves the index until a human
  reads the diff. Re-indexing changed text under an old sign-off is exactly what
  the `sha256` field exists to prevent. For a calendar corpus, a confidently
  cited deadline from last year is the highest-harm failure this product has.

Run `--report` on a schedule; it exits 1 when something is overdue.

### Data-quality work still outstanding

- [ ] **Content-level deduplication.** The policy rejects duplicate ids and
      duplicate canonical URLs. Nothing compares the content itself, so two
      snapshots of one page — or an AR/EN pair that is actually the same text —
      would both index and both be citable.
- [ ] **`scan_pii` has never processed a real document.** Run it against a
      deliberately dirty sample and confirm it fires *before* the first approval.
      The privacy policy already promises it works.
- [ ] **Re-run `eval_chunk_size.py` on real content.** It has only ever seen the
      quarantined dev corpus — hand-assembled markdown, not Ritaj HTML. Chunk
      boundaries that work on prose fail on tables, and the calendar is a table.
- [ ] **Exercise the staleness badge end to end** once a record has a
      `fetched_at`. It has never fired.
- [ ] **Drop `course-browser`** — `/hemis/courses` was confirmed not to load.
- [ ] **Decide `public-directory` deliberately** — most likely to contain
      personal data. Refusing it is a valid outcome.

### Quality thresholds, none of which has a number yet

| Metric | Threshold | Now |
|---|---|---|
| Answerable cases | ≥ 100 | **0** |
| Calendar cases | ≥ 25 | **0** |
| Navigation cases | ≥ 20 | 22 ✓ |
| Retrieval recall@10 | ≥ 95% | unmeasured |
| Supported-answer accuracy | ≥ 90% | unmeasured |
| Citation precision | ≥ 95% | unmeasured |
| Unsupported factual claims | < 2% | unmeasured |
| Correct refusal | ≥ 95% | unmeasured |
| Navigation destination precision | 100% | 100% ✓ |

Separate Arabic and English tables are required. The accuracy of this product is
**unknown**, which is a different and more honest claim than "untested".

---

## 6. Release checklist

Run from a clean checkout of the release tag. Items with no command are human
judgements and say so.

### A. Gates

```bash
pytest -q
node --test chrome-extension/navigation.test.mjs \
            chrome-extension/links.test.mjs \
            chrome-extension/transport.test.mjs
python scripts/check_corpus_policy.py --release   # refuses to pass on an empty set
python scripts/check_navigation.py                # 18 hostile URLs rejected
python scripts/check_extension.py                 # minimal permissions, allowlist parity
python scripts/check_privacy.py                   # disclosures match the code
python scripts/check_error_messages.py            # every error code has wording, both clients, both languages
python scripts/check_operations.py                # every duty and drill has an owner and a date
python scripts/eval_release.py                    # refusals, injection, URL precision
python scripts/eval_release.py --gate             # release-set completeness
python scripts/lock_deps.py --check

# SBOM BEFORE packaging, in this order: sbom.py rewrites release/sbom.json and
# therefore dirties the tree, and package_extension.py --verify refuses a dirty
# tree. Commit the regenerated file before continuing.
python scripts/sbom.py --check-current
python scripts/sbom.py
python scripts/sbom.py --check-pinned

python scripts/secret_inventory.py
python scripts/loadtest.py
python scripts/package_extension.py --verify      # deterministic ZIP, clean tree only
node scripts/e2e_extension.mjs
pip-audit -r requirements.lock.txt
cd ritaj-student-portal && npm run lint && npm run build
```

**By hand** — Chrome's side panel cannot be driven programmatically:

- [ ] Load unpacked, click the toolbar icon, confirm the **side panel** opens.
- [ ] Navigate between pages; confirm the panel stays open and the conversation
      survives.

### B. Service

- [ ] `/live` 200 and `/ready` 200 in production.
- [ ] **Three consecutive cold starts** inside the host timeout.
      `/ready` reports `timings_ms.listening` — seconds, not minutes.
- [ ] Base image pinned by digest; dependencies installed `--require-hashes`.
- [ ] Load and resilience numbers recorded (`loadtest.py --json`). Those are
      application numbers against a stub; **real latency must be measured
      against Cloudflare** before any capacity claim.
- [ ] `/admin/usage` shows budget, concurrency and circuit state, and someone is
      watching it.
- [ ] **Rollback rehearsed, not just documented.**

### C. Data

- [ ] `check_corpus_policy.py --release` exits 0 — the `--release` form is what
      makes this line mean anything.
- [ ] Every approved record has a checksum, a fetch date and a named approver.
- [ ] Release-set thresholds in §5 met, with separate AR/EN tables.
- [ ] Content owner has signed off on sampled answers.

### D. Extension

- [ ] Permissions are exactly `storage` and `sidePanel`, plus one backend host.
- [ ] **Screenshots recaptured.** The current ones are dated 6 July and predate
      the redesign — they show the old red UI, no page finder, no status pill.
- [ ] Verified against the **live** backend. The E2E suite blackholes the host by
      design, so this is unproven.
- [ ] ZIP SHA-256 recorded in `release/manifest.json`.

### E. Privacy and operations

- [ ] Public `/privacy` URL loads from production.
- [ ] Listing, manifest, code and policy name the same backend, provider and
      data behaviour.
- [ ] `check_operations.py` exits 0.
- [ ] Independent / non-endorsed status visible in Arabic and English.

### F. Rollout

1. **Maintainer alpha** — navigation only, chat abstaining. *This is today.*
2. **Closed pilot, 10–20 students** — after a corpus and a measured evaluation.
3. **Limited Store rollout, one week** — review errors, quota, latency, freshness
   and corrections daily.
4. **General availability** — only when every gate is green and free-tier risk is
   accepted by a named owner.

Plan the rollout around **200–500 answers/day**, not around demand.

---

## 7. Operations

### Ownership

`docs/OPERATIONS.md` §1 and §4 are **parsed by `check_operations.py`** — keep
that file where it is and in its current shape.

```bash
python scripts/check_operations.py    # exits 1: 13 unassigned duties/undrilled drills
```

Nine duties need a named **primary and backup**; four rollback drills need a
recorded date and recovery time. "The team" is rejected deliberately: when
everybody is responsible, nobody is paged.

### Branch model

`roadmap/2026-release` → PR → `release` → tag → deploy. `main` is a stale single
commit and is not the integration branch. **`release` is not yet
branch-protected** — the command is in `cowork_ritaj/human-actions.md` §H1.

### Rollback matrix

| Incident | Action | Recovery |
|---|---|---|
| Bad destination | `enabled: false`, redeploy | minutes; the extension's bundled copy still validates |
| Bad corpus | repoint the Qdrant alias to the previous collection | seconds — the previous collection is kept |
| Bad backend | deploy the previous tagged image | one build |
| LLM incident or quota | disable generation; navigation stays up | immediate |
| Suspected secret leak | **revoke first**, rotate, invalidate sessions, then investigate | immediate |
| Extension bug | pause Store rollout, resubmit the prior package | Store review time |

### Credentials

**Three credentials were pasted into a chat transcript on 20 Aug and all need
rotating.** Notes are at the top of the gitignored `.env.local`. The Qdrant key
decodes to `"access":"m"` — full manage rights, able to delete every collection —
so roll that one first.

Passwords must never be generated by an agent, pasted into a chat, or passed as
a command-line argument. `scripts/set_admins.py` prompts for exactly that reason.

Housekeeping still owed: delete `dev_unapproved_never_served` from the
production cluster, and `rm OPERATOR-PASSWORD.txt ritaj_rag_admins.rtf` after
moving the password into a manager.

### Restart-proof limits

Rate limits and the daily neuron budget live in process memory; a Space restart
reopens both. Acceptable for a closed alpha. Before a wide pilot, either move
them to Upstash Redis or document the reset explicitly.

`TRUSTED_PROXY_COUNT` must be set per host or the network limit becomes global;
`/ready` reports `client_addressing.ok`.

---

## 8. Security

| # | Threat | Control |
|---|---|---|
| 1 | Indirect prompt injection via corpus content | Injection scanning and redaction on retrieved passages; grounded-answer checking and repair |
| 2 | Malicious or wrong navigation destination | Reviewed registry; the LLM emits an id, never a URL; server and extension validate independently |
| 3 | Quota exhaustion / denial of wallet | Two rate-limit buckets (network + session), daily neuron budget, concurrency cap, circuit breaker |
| 4 | Log leakage / accumulating personal data | Aggregate-by-default telemetry; PII masking; stated retention |
| 5 | Admin takeover | bcrypt per-user auth, signed sessions, brute-force limiting, `/admin/*` closed in production |
| 6 | Supply chain | Hashed dependency lock, digest-pinned base image, SBOM checked against the tree, reproducible extension ZIP |
| 7 | Extension update compromise | Deterministic packaging from a clean tag, recorded SHA-256, no remote code |
| 8 | Corpus poisoning through ingestion | Source policy, checksums, named approval, quarantine |
| 9 | Backend impersonation | The extension re-validates every URL it receives; it trusts neither model output nor arbitrary backend URLs |

### CORS is not a control on this host

Measured 20 Aug 2026. The application's CORS allowlist is correct — run against
the same production configuration locally, it blocks `https://evil.example.com`
and blocks an unknown `chrome-extension://` origin, allowing only the configured
origin.

**The Hugging Face proxy overrides that in front of the app.** Live, every
origin is echoed back in `access-control-allow-origin`, including
`evil.example.com`. The proxy also answers OPTIONS preflights itself: a route
the application does not serve returns `200` to a preflight and `404` to a GET,
which is how the behaviour was traced to the platform rather than to us.

Consequences, and neither is optional:

- **Do not treat CORS as a quota control on this host.** Anything that must
  actually be enforced has to be enforced server-side. The two rate-limit
  buckets, the daily neuron budget and the concurrency cap are the real
  controls; CORS is defence in depth that this platform removes.
- `check_production_config()` still refuses a wildcard `CORS_ORIGINS`, and that
  stays worthwhile — it is correct on any host that does not rewrite the header,
  including the Oracle fallback.

**Residual, accepted:** free tiers carry no SLA; the admin bearer token is held
in local storage (documented XSS exposure); a compromised approver could
introduce a bad source; CORS is unenforceable on the current host, as above.

---

## 9. Decisions

**ADR-001 — LLM provider.** Cloudflare Workers AI, `@cf/google/gemma-4-26b-a4b-it`.
Free 10,000 neurons/day with no card; OpenAI-compatible, which the client already
speaks; no weights to host. Consequence: ~200–500 answers/day, and a provider
dependency. Revisit if the free allowance changes or latency proves unacceptable.

**ADR-002 — Navigation-only automation.** The extension may open reviewed pages
and nothing else. It does not read the page, cookies, account, grades, schedule,
balance or forms. Consequence: it can never "do things for you", and that is the
point — a plausible answer must not be able to move a student's browser. Revisit
only with a written authorization and a different threat model.

**Gemma 4 is a reasoning model.** It emits `reasoning_content` before `content`,
and those tokens bill as output — measured at ~70% of output on a RAG-shaped
call. Every documented way to cap it (`reasoning_effort: low`/`none`,
`reasoning.effort`, `thinking.type: disabled`) was tested against the live
provider and **silently ignored**. `max_tokens` is therefore 2,048 with a floor
of 512. Earlier advice to reduce it to 350–500 is **withdrawn**: that budget
returns empty answers.

---

## 10. What remains, in order

1. **Content deduplication** (§5). Cheap, and it makes later measurements
   trustworthy.
2. **One approved document** (§5). *Nothing else starts without it.* It converts
   the entire quality section from theory into measurements.
3. **Send the outreach drafts** — `cowork_ritaj/outreach/`. The only route to
   automated acquisition, and nothing else shortens it.
4. **Measure quality** (§5 thresholds) and real latency.
5. **Assign owners and rehearse rollbacks** (§7). Independent of everything
   above; blocked only on people.
6. **Rotate three credentials** (§7).
7. **Recapture Store screenshots and verify against the live backend** (§6 D).

---

## 11. Not verified by anyone

Stated so it is not mistaken for tested:

- ~~The extension against the live backend.~~ **Verified 20 Aug** —
  `node scripts/e2e_live.mjs`, 6/6: it reaches the deployment, renders the four
  server-supplied destinations, shows the real chat state, receives the genuine
  `503 NO_CORPUS` refusal rather than a network error, and contacts no other
  host. Clicking the toolbar icon remains a manual check.
- Three consecutive cold starts.
- Any behaviour with a real corpus — none exists.
- Latency as a distribution. Two samples (9.7 s, 12.2 s complete answer against
  a p95 ≤ 12 s target) cannot establish a p95.
- `scan_pii` against real Ritaj markup.
- Whether the free HF account can rebuild the Space indefinitely.

---

## 12. What this replaced

Fifteen planning documents, ~5,000 lines, several contradicting each other. That
drift is how `DEPLOYMENT.md` came to describe a provider and a UI that no longer
existed, and it had begun again: as of this morning `CLAUDE.md` still said
"nothing is deployed".

Folded in and deleted: `FUTURE_PLAN.md`, `SETUP_LIVE.md`,
`PRODUCTION_FREE_LIVE_PLAN.md`, `READY_TO_RELEASE_EXECUTION_PLAN.md`,
`RELEASE_ROADMAP_2026.md`, `SELF_HOSTED_LLM_PLAN.md`, `DEPENDENCIES.md`,
`docs/RELEASE_CHECKLIST.md`, `docs/RELEASE_PROCESS.md`, `docs/DEPLOY_GEMMA4.md`,
`docs/SECURITY_THREAT_MODEL.md`, `docs/adr/*`, `cowork_ritaj/COWORK_PLAN.md`,
`cowork_ritaj/INTAKE.md`, `cowork_ritaj/PROGRESS.md`. All recoverable from git
history.

**Deliberately kept**, because code reads them at fixed paths or they are
correspondence rather than documentation:

| Path | Why |
|---|---|
| `docs/OPERATIONS.md` | parsed by `check_operations.py` |
| `chrome-extension/store/privacy-policy.md` | parsed by `check_privacy.py`; served as `/privacy` |
| `chrome-extension/store/SUBMISSION.md` | parsed by `check_privacy.py` |
| `data/quarantine/README.md`, `data/raw/README.md` | content-policy markers referenced by the build |
| `data/quarantine/*.md` | dev corpus and evaluation fixtures |
| `cowork_ritaj/outreach/*` | letters to send, not documentation |
| `cowork_ritaj/human-actions.md`, `url-confirmation.md`, `screenshot-checklist.md` | worksheets with a human's working in them |
| `chrome-extension/README.md` | reviewer-facing, ships with the package |
| `CLAUDE.md` | agent orientation, gitignored |
