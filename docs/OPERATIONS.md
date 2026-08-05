# Operations — owners, monitoring, and incident runbook

Roadmap Phase F4. Two things live here: **who is responsible for what**, and
**what to do when something breaks**. Both must be filled in and rehearsed
before the closed pilot, because an incident is the worst time to discover that
nobody knows who can rotate a token.

---

## 1. Ownership register

**Every row below is unfilled.** The repository cannot invent an owner, and a
duty with no name is a duty nobody performs. Assign a primary and a backup —
one person is a single point of failure, and pilots run during term time when
people have exams.

| Duty | Primary | Backup | Access needed |
|---|---|---|---|
| Service uptime, Hugging Face deployment | | | HF write token, Space settings |
| Cloudflare quota, token rotation | | | Cloudflare account, Workers AI scope |
| Corpus corrections and refresh | | | Repo write, content-owner contact |
| Navigation kill switch | | | Repo write, deploy |
| Privacy and deletion requests | | | Support inbox, log access |
| Security incidents | | | All of the above, plus repo admin |
| Chrome Web Store listing and support inbox | | | Store developer account |
| Content approval — Arabic | | | Named Birzeit unit |
| Content approval — English | | | Named Birzeit unit |

**Support address:** `ritaj.assistant.project@gmail.com` — must be monitored by a
named person before the listing goes live. It is published in the privacy policy
and the store listing, so an unmonitored inbox is a broken promise, not a minor
gap.

---

## 2. What to watch

`/admin/usage` (authenticated) is the single operational view:

| Signal | Healthy | Act when |
|---|---|---|
| `budget.neurons_used` | rising steadily through the day | >70% before midday — expansion is outpacing the free tier |
| `budget.provider_calls` | ~1–2 per student question | ≫2 per question means condensation is firing constantly |
| `llm.circuit.open` | `false` | `true` for more than a few minutes |
| `concurrency.active_generations` | below the cap | pinned at the cap with `BUSY` in the logs |
| `corpus.version` | the version you deployed | anything else — a stale artifact is being served |
| `/ready` `client_addressing.ok` | `true` | `false` — rate limiting is not identifying clients correctly |

From the aggregate log (`/admin/log`): abstention rate, refusal rate, repaired
rate, injection flags, p50/p95 latency, error codes. All of these are
privacy-preserving counts; raw conversation text is not stored and must not
become a product metric.

---

## 3. Incident runbook

Each entry: how you notice, what to do first, and how to confirm recovery.
**Containment before diagnosis** — students are using it while you investigate.

### 3.1 Service outage (`/live` failing or 5xx at the edge)

1. Check the Space build/runtime logs.
2. `/live` failing but the process up → restart the Space.
3. `/live` fine, `/ready` failing → read `code` on `/ready`
   (`CORPUS_UNAVAILABLE`, `STORE_UNAVAILABLE`, `MODEL_LOAD_FAILED`,
   `LLM_MISCONFIGURED`, `STORAGE_UNWRITABLE`). The message is deliberately not
   there — it is in the protected logs.
4. Not resolved in 15 minutes → redeploy the previous release tag.

**Recovered when:** `/live` 200, `/ready` 200 with the expected corpus version,
and one Arabic and one English question answer correctly.

### 3.2 Quota exhaustion

Students see `LLM_BUDGET_EXHAUSTED`. The service is *working as designed* — it
refused rather than overspending.

1. `/admin/usage` → is the spend real traffic or one caller?
2. One caller → check whether `client_addressing.ok` is false; if so the network
   limit is not identifying clients and `TRUSTED_PROXY_COUNT` is wrong for this
   host.
3. Real growth → either lower `MAX_CONCURRENT_GENERATIONS` and the per-network
   limits to spread the day's allowance, or pause the rollout. **Do not** raise
   `LLM_DAILY_NEURON_BUDGET` above the provider's free allowance unless someone
   has agreed to pay.
4. Reconcile against the Cloudflare dashboard — the neuron conversion is derived
   from published prices, not reported by the API.

**Recovered when:** spend per hour is inside the daily allowance.

### 3.3 An unsafe or wrong answer

1. Get the request id from the student (it is in the `done` event and the
   `X-Request-ID` header).
2. Find the aggregate log entry: which sources, what grounding verdict.
3. Wrong because a **source is wrong or stale** → fix the source, republish the
   corpus, or roll `data/corpus/CURRENT` back.
4. Wrong although **the source is right** → a generation or grounding defect.
   Capture it as an evaluation case *before* changing anything.
5. Harmful content → take the corpus offline by pointing `CURRENT` at the
   previous artifact and redeploying; the service abstains rather than answering
   from something unreviewed.

**Recovered when:** the question is in the release evaluation set and passes.

### 3.4 A wrong or unsafe navigation destination

Highest severity: this changes browser state.

1. Set `enabled: false` on the action in `data/navigation.yaml` and redeploy.
   **No Chrome Web Store review is needed** — that is why the switch is
   server-side.
2. Confirm the action no longer resolves: `python scripts/check_navigation.py`
   and one live request.
3. Only then investigate whether it was a bad registry entry or a resolver bug.
4. Add the case to `data/eval/release_set.yaml` under `navigation` with
   `expect: none` or the correct action id.

**Recovered when:** the destination cannot be produced, and the eval set covers
it.

### 3.5 Exposed secret

Assume disclosure from the moment of suspicion; do not wait for proof.

1. **Revoke first, investigate second.** Cloudflare token → delete it in the
   dashboard. HF token → revoke in settings. Admin passwords → rotate.
2. Issue a replacement, update the host secret, confirm the fingerprint changed:
   `python scripts/secret_inventory.py`.
3. Determine the exposure path: committed (`--scan-only` over history), packaged
   (the ZIP scan), logged, or pasted.
4. If it was committed, rotating is sufficient — rewriting history is not, since
   the value may already have been cloned.
5. Check the provider's usage/audit log for activity you cannot account for.

**Recovered when:** the old credential is revoked, the new one works, and the
fingerprint in the inventory differs from the compromised one.

### 3.6 Extension regression

1. Server-side first: can it be fixed without a store update? Registry flags,
   corpus rollback and API behaviour all can.
2. If not, resubmit the previous package — **store review takes hours to days**,
   so assume the bad version is live meanwhile.
3. If the regression is dangerous rather than merely broken, disable the feature
   server-side so the published extension has nothing to do wrong.

**Recovered when:** the published version behaves correctly, verified with
`node scripts/e2e_extension.mjs` against the packaged ZIP.

### 3.7 Suspected private data in the corpus

1. Point `data/corpus/CURRENT` at the previous artifact, redeploy.
2. `python scripts/check_corpus_policy.py` on the suspect artifact.
3. Delete the artifact and its snapshot; record what it contained and who was
   notified.
4. Do not re-publish until the source policy check passes and the content owner
   re-approves.

---

## 4. Rehearsal

Rehearse before the pilot, not during it. Record the date and the recovery time:

| Drill | Rehearsed | Recovery time |
|---|---|---|
| Corpus rollback (repoint `CURRENT`, redeploy, confirm answers change) | | |
| Backend rollback (redeploy previous tag) | | |
| Navigation kill switch (`enabled: false`, confirm it stops resolving) | | |
| Secret rotation (rotate a staging token end to end) | | |

A rollback that has never been performed is a plan, not a capability.
