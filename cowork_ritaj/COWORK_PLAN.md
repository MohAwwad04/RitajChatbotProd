# Ritaj Assistant — Cowork execution plan to production

> **DONE — its tasks are recorded in [PROGRESS.md](PROGRESS.md).** The current
> forward plan is **[../FUTURE_PLAN.md](../FUTURE_PLAN.md)**. `INTAKE.md` in
> this folder remains authoritative — the corpus path is unchanged.

**Written:** 2026-08-10 · **Baseline commit:** `3b2a6e3` on `roadmap/2026-release` (draft PR #2 → `release`)
**Audience:** Claude Cowork agents working in `~/Desktop/ritaj-rag-chatbot`, plus the human owner for the steps no agent can do.

This plan takes the project from "engineering complete, nothing deployed" to
"students are using it". Every command below was run or read on 2026-08-10;
nothing here is invented. Appendix A records exactly what was verified.

---

## 0. Prime directives — read before touching anything

These are not style preferences. Each one exists because breaking it would ship
something harmful or make a green gate meaningless.

1. **Never fabricate, infer, scrape or "reconstruct" corpus content.** The
   production rule is that a record's canonical source is *exactly*
   `https://ritaj.birzeit.edu`, with an owner, a snapshot, a sha256 and a named
   approver. All 22 previous documents failed that and live in
   `data/quarantine/`. If a task appears blocked on missing content, it **is**
   blocked — report it, do not fill the gap. Read `data/quarantine/README.md`
   first, always.
2. **Never bypass the Cloudflare managed challenge** on `ritaj.birzeit.edu`.
   Direct automated fetches return 403 by design. Acquisition happens through an
   authorized path (§3), or it does not happen.
3. **Never weaken a threshold, waive a gate, or add `continue-on-error` to make
   something pass.** If `eval_release.py --gate` fails, the release is not
   ready. That is the gate working.
4. **Never write evaluation cases against the quarantined corpus.** A suite that
   passes on material that must never ship is worse than an empty category,
   because it reads as evidence.
5. **Never enable a navigation action without a named approver.** All five are
   `enabled: false`. Setting `enabled: true` and filling `approved_by` is one
   atomic, human-authorized act.
6. **Never commit, paste, echo or log a secret.** `scripts/secret_inventory.py`
   reports presence and fingerprints only. `ritaj_rag_admins.rtf` is gitignored
   plaintext and is treated as already compromised.
7. **Preserve the five architecture invariants** in `CLAUDE.md` §"Architecture
   invariants". Each has a test and a CI gate. If a change requires breaking
   one, stop and escalate instead.
8. **Report honestly.** Separate measured from assumed. If you could not verify
   something, say so in your handoff rather than describing it as done.

### Anti-patterns that have a real chance of happening here

| Tempting action | Why it is forbidden |
|---|---|
| Adding a few Markdown files to `data/raw/` so the index is non-empty | A stray file dropped there once went straight to production; `check_corpus_policy.py` check 2 exists because of it |
| Copying quarantine docs into `data/snapshots/` | Off-domain and SAMPLE content becomes "approved" with a laundered path |
| Lowering `required_counts.answerable` from 100 | The number is the release contract, not a config knob |
| Setting `approved: true` with `approved_by: "team"` | An approver is a named person or ticket, not a collective noun |
| Screenshotting the portal and calling it the side panel | Misrepresenting the product to the Chrome Web Store is a policy violation |
| Re-running `sbom.py` right before packaging | Dirties the tree; see T1.1 for the actual fix |

---

## 1. How to work this plan in Cowork

**Task IDs** are `T<stream>.<n>`. Each card states: who can do it (`AGENT` /
`HUMAN` / `AGENT+HUMAN`), what must be true first, the steps, and a **runnable**
acceptance check. A task is done when its acceptance command exits 0 — or, for
human-judgement items, when the named evidence exists in the repo.

**Parallelism.** Stream 1 and Stream 2's preparation work can start immediately
and simultaneously. Streams 3–5 have hard external dependencies. Suggested agent
allocation:

```
Agent A  →  Stream 1 (repo hygiene)              starts now, no dependencies
Agent B  →  Stream 2 prep (T2.1–T2.3)            starts now, hands off to human
Agent C  →  Stream 6 (ops docs + drills prep)    starts now
   ...then, once external inputs land...
Agent D  →  Stream 3 (evaluation)                needs approved corpus
Agent E  →  Stream 4 (provider + deploy)         needs Cloudflare + HF tokens
Agent F  →  Stream 5 (navigation + store)        needs approver + store account
```

**Working agreement.** One task per branch off `roadmap/2026-release`; keep the
tree clean (see T1.1 — an untracked file is enough to make packaging refuse).
Run `pytest -q` before every handoff. Do not merge PR #2 until Stream 7.

**Handoff format.** Each finished task appends to `cowork_ritaj/PROGRESS.md`:
task ID, what changed, the acceptance command and its exit code, and anything
you could **not** verify.

---

## 2. Stream 1 — Repo hygiene (no external dependencies, start today)

Roughly 1–2 engineering days of agent work. All of it is unblocked right now.

### T1.1 — Fix the stale SBOM and the checklist ordering trap · `AGENT`

**Problem (found 2026-08-10, not previously recorded).** The committed
`release/sbom.json` was generated 2026-08-05T14:27:45Z, but
`requirements.lock.txt` was updated ~20 minutes later by the security bump. The
committed SBOM says `pypdf 6.13.3` / `setuptools 81.0.0`; the lock ships
`6.14.2` / `83.0.0`. **The shipped bill of materials misstates the image.** No
gate catches this: CI regenerates the file and uploads it as an artifact, so it
never compares against the committed copy.

Second, `docs/RELEASE_CHECKLIST.md` §A runs `sbom.py` (which rewrites the file)
four lines before `package_extension.py --verify` (which refuses a dirty tree).
Following the checklist in order fails.

**Steps**

1. `python scripts/sbom.py` and commit the regenerated `release/sbom.json`.
2. Add `--check-current` to `scripts/sbom.py`: regenerate in memory, compare to
   the committed file ignoring `metadata.timestamp`, exit 1 on drift.
3. Wire it into `.github/workflows/ci.yml` in the `security` job, blocking.
4. Reorder `docs/RELEASE_CHECKLIST.md` §A so SBOM generation precedes packaging,
   and note that generation dirties the tree.

**Acceptance**
```bash
python scripts/sbom.py --check-current && git diff --quiet release/sbom.json
python scripts/package_extension.py --verify      # exit 0 on a clean tree
```

### T1.2 — Make the ownership register enforceable · `AGENT`

`docs/OPERATIONS.md` §1 has nine blank rows and §4 has four blank drill rows. A
blank duty is a duty nobody performs, and prose cannot enforce itself.

**Steps**

1. Write `scripts/check_operations.py`: parse OPERATIONS §1 and §4; exit 1 if
   any Primary/Backup cell is empty or any drill lacks a date and recovery time.
2. Add it to CI as **advisory** now (it will fail until Stream 6), and list it in
   `docs/RELEASE_CHECKLIST.md` §E as blocking at release.
3. Add a one-line note in §1 that the register is machine-checked.

**Acceptance** — `python scripts/check_operations.py` exits 1 today with a
message naming every blank row, and exits 0 once Stream 6 fills them.

### T1.3 — Retire the stale deployment doc · `AGENT`

`DEPLOYMENT.md` still names Groq as the provider and the popup as the UI. Both
were removed. `CLAUDE.md` already calls it "partly stale", which is not enough —
an operator reading it during an incident is reading fiction.

**Steps** — Either fold the still-true parts into `docs/DEPLOY_GEMMA4.md` and
delete `DEPLOYMENT.md`, or prepend a hard "SUPERSEDED — do not follow" banner and
strip the Groq/popup sections. Prefer deletion; the git history keeps it.
Then grep the repo for remaining `groq`/`popup` references outside history and
`data/quarantine/`.

**Acceptance**
```bash
grep -rin 'groq\|popup' --include='*.md' --include='*.py' --include='*.js' . \
  | grep -v '\.git/\|quarantine/\|node_modules/\|CHANGELOG' | grep -v 'no stale popup'
# expect: no hits, or only intentional historical notes
python scripts/check_privacy.py
```

### T1.4 — Prepare admin credential rotation · `AGENT+HUMAN`

`ritaj_rag_admins.rtf` holds weak, username-derived plaintext passwords. Treat
them as disclosed.

**Steps**

1. `AGENT`: document the exact rotation sequence in `docs/OPERATIONS.md` §3.5.
   `python -m ritaj.adminauth hash <username>` exists and prompts for the
   password **interactively** — it must be run by a human in a real terminal
   (that is the point: the password never enters argv, shell history, or an
   agent transcript). `python scripts/set_admins.py --count N` writes the pairs.
2. `HUMAN`: generate new passwords with a password manager (never an agent, never
   a chat), produce bcrypt hashes, set `ADMIN_USERS` on the host, delete the
   `.rtf`, and confirm the fingerprint changed.

**Acceptance** — `python scripts/secret_inventory.py` shows `ADMIN_USERS`
present with a fingerprint differing from the pre-rotation one, and
`ritaj_rag_admins.rtf` no longer exists on disk.

### T1.5 — Protect the `release` branch · `HUMAN` (agent prepares)

`GET /repos/MohAwwad04/NLP_Project/branches/release/protection` returns 404 —
the branch is unprotected, so the whole "reviewed release commit" model is
currently advisory.

**Agent prepares this exact command for the repo admin to run:**
```bash
gh api -X PUT repos/MohAwwad04/NLP_Project/branches/release/protection \
  -H "Accept: application/vnd.github+json" \
  -F "required_status_checks[strict]=true" \
  -F "required_status_checks[contexts][]=Backend tests" \
  -F "required_status_checks[contexts][]=Corpus, navigation, privacy and extension policy" \
  -F "required_status_checks[contexts][]=Secrets and dependencies" \
  -F "required_status_checks[contexts][]=Portal build and extension tests" \
  -F "required_status_checks[contexts][]=Load and resilience" \
  -F "required_pull_request_reviews[required_approving_review_count]=1" \
  -F "enforce_admins=true" -F "restrictions=null"
```
**Acceptance** — the same endpoint returns 200 with those contexts.

### T1.6 — Refresh the status blocks · `AGENT` (do this last in Stream 1)

`README.md`, `CLAUDE.md`, `READY_TO_RELEASE_EXECUTION_PLAN.md` §2.2 and several
`data/*.yaml` headers are stamped "4 Aug / 5 Aug 2026" and describe conditions
that have since changed: portal lint now passes, the base image is digest-pinned,
the navigation eval category is populated (22 cases), the branch is pushed with
PR #2 open, the container job has now actually built, and the suite is 355 tests
rather than 312.

**Acceptance** — every dated status claim in those files matches Appendix A, and
`pytest -q` still reports the count the docs assert.

---

## 3. Stream 2 — Acquire an authorized Ritaj corpus (the critical path)

**Nothing downstream of this can be finished without it.** The repo's own
estimate is 3–10 working days plus review; realistically it is dominated by how
fast a Birzeit department responds, which no amount of engineering shortens.
Start T2.1 today.

Current state: 7 candidate records in `data/sources.yaml`, **all
`approved: false`**, none with a snapshot. `check_corpus_policy.py` passes
*vacuously* — it reports "none published", i.e. it is validating an empty set.

### T2.1 — Draft the acquisition request · `AGENT` → `HUMAN` sends

**Steps** — Draft, in **Arabic and English**, a request to the Birzeit Computer
Center and to the Registration Office. It must state: who the student team is,
that this is an independent unofficial project, exactly which pages are wanted
(the 7 candidates in `data/sources.yaml`), that only public pages are in scope,
that no student data is requested, which of the three authorized paths
(§`data/quarantine/README.md`) would suit them, and what "approval" means
concretely (a named person confirming the content is correct and public).

Save as `cowork_ritaj/outreach/acquisition-request-{ar,en}.md`. Include a
one-page appendix showing what the assistant does and its refusal behaviour —
approvers respond better to a demo than a description.

**Acceptance** — both drafts exist and name all 7 candidate URLs; human confirms
they were sent and logs the date and recipient in `cowork_ritaj/PROGRESS.md`.

### T2.2 — Confirm the candidate URLs exist and are public · `HUMAN`

An entry in `data/sources.yaml` is a *question* ("is this the right page?"), not
an assertion. Automated confirmation is impossible — 403 by design, and
bypassing that is forbidden.

**Steps** — A human opens each of the 7 candidates in a normal browser session,
records: does it exist, is it reachable **without** signing in, is it the right
page, and what is its true canonical URL. Log results in
`cowork_ritaj/url-confirmation.md`. Any URL that requires login is out of scope
for the public corpus — mark it and remove the candidate.

**Acceptance** — every candidate in `data/sources.yaml` has a line in the
confirmation log with a verdict and a date.

### T2.3 — Build the snapshot intake path · `AGENT`

Prepare the machinery so that the moment approved content arrives, it can be
ingested without improvisation.

**Steps**

1. Write `cowork_ritaj/INTAKE.md`: given a saved page or an export, where the
   file goes (`data/snapshots/<corpus-version>/`), how to compute the hash
   (`python scripts/build_index.py --rehash`), which `sources.yaml` fields to
   fill, and the content review checklist (no PII, no private-page content, an
   effective date, a refresh window).
2. Verify the whole path end-to-end using the **dev** corpus only:
   `python scripts/build_index.py --dev` — never `--publish`.
3. Confirm `check_corpus_policy.py` rejects a deliberately bad record: add one
   off-domain record locally, confirm exit 1, then revert it.

**Acceptance** — the negative test is demonstrated (exit 1 on an off-domain
record, exit 0 after revert), and `git status --porcelain` is empty afterwards.

### T2.4 — Promote approved records · `AGENT+HUMAN`

**Preconditions:** T2.2 and T2.3 done, real snapshots delivered, named approvers
identified.

**Steps** — For each delivered page: place the snapshot, set `content_path`,
`fetched_at`, `sha256`, `effective_date`, then have the owning office confirm
the content and only then set `approved: true` with `approved_by` naming that
person or ticket. Arabic and English are approved separately by their own owners.

**Acceptance**
```bash
python scripts/check_corpus_policy.py --strict   # exit 0, non-vacuously
grep -c 'approved: true' data/sources.yaml       # matches the number approved
```

### T2.5 — Publish the first corpus artifact · `AGENT`

```bash
python scripts/build_index.py --publish     # writes data/corpus/<version>/ + CURRENT
python scripts/check_corpus_policy.py       # must now report a non-zero chunk count
python scripts/ensure_index.py              # artifact restores and answers
```

**Acceptance** — `check_corpus_policy.py` names a published artifact with a
non-zero chunk count, and reports no `www.birzeit.edu`, other-domain, private or
`SAMPLE` material.

### T2.6 — Prove freshness and rollback · `AGENT`

**Steps** — Publish a second artifact version, point `data/corpus/CURRENT` at the
previous one, restart, confirm answers change, then roll forward. Separately, ask
a question whose source is past its refresh window and confirm the answer says
the source may be out of date.

**Acceptance** — both behaviours observed and recorded with timings in
`docs/OPERATIONS.md` §4 (corpus rollback drill row).

---

## 4. Stream 3 — Complete the release evaluation

**Blocked on:** T2.5. This is the gate that currently fails: `answerable 0/100`,
`calendar 0/25`.

### T3.1 — Author 100 bilingual `answerable` cases · `AGENT+HUMAN`

**Steps** — Derive every case from the **approved** corpus only. Roughly balanced
Arabic/English. Each case names the question, the expected source id(s), and the
fact that must appear. Cover the questions the quarantined corpus was trying to
answer (its README lists the topics) — but write the cases from approved text.
A human content owner spot-checks a sample for factual correctness; an agent
cannot be the sole judge of whether a Birzeit fact is right.

**Acceptance** — `answerable` has ≥100 entries and each `source_id` resolves to
an `approved: true` record.

### T3.2 — Author 25 `calendar` cases · `AGENT+HUMAN`

Date questions are the highest-harm category — a wrong deadline is worse than a
refusal. Include: questions whose answer depends on the current date, sources
past their refresh window (expect a staleness caveat), and at least three where
the correct behaviour is to abstain.

**Acceptance** — `calendar` has ≥25 entries; `python scripts/eval_release.py --gate`
exits **0** for the first time.

### T3.3 — Score against a live model · `AGENT`

**Preconditions:** T4.1 (a real provider) and a running Qdrant.

```bash
docker run -p 6333:6333 qdrant/qdrant          # eval scripts need the store
python scripts/eval_golden.py                  # loads models; not model-free
python scripts/eval_redteam.py
```
Both scripts load embedding + reranker weights and require the vector store —
they are slow and cannot run in the model-free CI job.

**Acceptance** — every threshold in `data/eval/release_set.yaml` is met:
recall@10 ≥95%, supported-answer accuracy ≥90%, citation precision ≥95%,
unsupported claims <2%, correct refusal ≥95%, navigation precision **100%**.
Store the report under `cowork_ritaj/eval-reports/<date>/`.

### T3.4 — Make the completeness gate blocking · `AGENT`

Remove `continue-on-error: true` from the "Release-set completeness (advisory)"
step in `.github/workflows/ci.yml`, and rename it. Do this **only after** T3.2
passes — never to make a red gate disappear.

**Acceptance** — CI green with the step blocking.

---

## 5. Stream 4 — Provider, staging, and repairing production

**Blocked on:** Cloudflare and Hugging Face credentials.

### T4.1 — Provision Cloudflare Workers AI · `HUMAN`

Per `docs/DEPLOY_GEMMA4.md` §1.1: create a **scoped** token (Workers AI only,
not a global key), note the account id, and set three variables on the host:

```dotenv
LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
LLM_MODEL=@cf/google/gemma-4-26b-a4b-it
LLM_API_KEY=<scoped token>
```

Also **re-confirm the model id and the free allowance against Cloudflare's
current catalogue before relying on them** — ADR-001's figures
(`@cf/google/gemma-4-26b-a4b-it`, 10,000 neurons/day ≈ 200 answers/day) were read
on 2026-08-04 and have not been re-verified since.

**Acceptance** — `python scripts/secret_inventory.py` shows `LLM_API_KEY`
present, and the provider contract tests pass against the real endpoint
(`pytest tests/test_provider_contract.py`, per `docs/DEPLOY_GEMMA4.md` §1.3).

### T4.2 — Deploy staging and prove cold start · `AGENT+HUMAN`

```bash
HF_TOKEN=hf_xxx python scripts/deploy_space.py --space staging
```
(`STAGING_SPACE_ID` defaults to `MohAwwad04/ritaj-rag-staging`.)

**Acceptance** — three consecutive cold starts succeed inside the host timeout;
`/ready` reports `timings_ms.listening` in seconds, not minutes; `/live` 200 and
`/ready` 200.

### T4.3 — Measure real latency and calibrate the client identity · `AGENT`

The current load numbers (p50 69 ms / p95 81 ms, 300-request soak, +0.2 MB heap)
are **application** numbers against a stub provider. They are not a capacity
claim about the product.

**Steps** — Measure first-token and full-answer latency on staging against
Cloudflare. Separately, set `TRUSTED_PROXY_COUNT` correctly for the HF Space and
confirm `/ready` reports `client_addressing.ok: true` — if it is false, the
network rate limit is either global (every student in one bucket) or
client-choosable (no limit at all).

**Acceptance** — real latency figures recorded in `cowork_ritaj/PROGRESS.md`, and
`client_addressing.ok` is true on staging.

### T4.4 — Repair production · `AGENT+HUMAN`

`https://mohawwad04-ritaj-rag.hf.space` returns **HTTP 503, "your space is in
error"** and runs an older commit. It cannot be repaired without an HF write
token. Deploy only after Stream 7 tags a release — do not push an untagged tree
in front of students.

---

## 6. Stream 5 — Navigation approval, extension, and the store

### T5.1 — Approve navigation destinations · `HUMAN` decides, `AGENT` applies

All five actions in `data/navigation.yaml` are `enabled: false` with an empty
`approved_by`. Until a Ritaj service owner confirms each destination is correct
and public, the flagship navigation feature resolves nothing.

Set `enabled: true` and `approved_by: <named person or ticket>` **together**, one
action at a time, each in its own commit.

**Acceptance** — `python scripts/check_navigation.py` reports zero actions
awaiting approval, all 18 hostile URLs still rejected, and
`node --test chrome-extension/navigation.test.mjs` passes.

### T5.2 — Recapture the store screenshots · `HUMAN` (agent prepares)

The three images in `chrome-extension/store/assets/` show the deleted 384×560
popup. `SUBMISSION.md` correctly says submitting them would misrepresent the
product — that is a policy problem, not a cosmetic one.

**This cannot be automated.** Chrome's side panel cannot be opened
programmatically and Playwright cannot drive one. Do **not** substitute a
screenshot of `sidepanel.html` rendered as an ordinary tab, or a composite — it
would be the same misrepresentation in a new form.

`AGENT` prepares `cowork_ritaj/screenshot-checklist.md` specifying the three
required 1280×800 captures: (1) English answer with a source row, (2) Arabic
answer, (3) an answer offering an **Open …** navigation button. `HUMAN` loads the
unpacked extension, clicks the toolbar icon, and captures the real panel.

**Acceptance** — three new 1280×800 PNGs, and the warning block in
`SUBMISSION.md` §0 removed because it no longer applies.

### T5.3 — Store account, extension id, CORS · `HUMAN`

Register the developer account ($5), create the item, obtain the extension id,
then add `chrome-extension://<id>` to the production CORS allowlist. Production
refuses a wildcard CORS list, so the id is a hard prerequisite for launch.

### T5.4 — Package and E2E from the tag · `AGENT`

**Preconditions:** T5.1–T5.3, and a release tag from Stream 7.

```bash
python scripts/package_extension.py --verify                 # deterministic, clean tree only
python scripts/release_manifest.py --require-clean -o release/manifest.json
node scripts/e2e_extension.mjs /tmp/unzipped-package         # the PACKAGE, not the source dir
```

**Manual, unautomatable checks** (from `docs/RELEASE_CHECKLIST.md` §A): clicking
the toolbar icon opens the **side panel** (not a popup, not the portal), and the
conversation survives navigating the active tab between pages.

---

## 7. Stream 6 — Operational readiness

### T6.1 — Fill the ownership register · `HUMAN`

Nine duties in `docs/OPERATIONS.md` §1, each needing a **primary and a backup** —
one person is a single point of failure, and pilots run during term time when
people have exams. The support inbox `ritaj.assistant.project@gmail.com` is
published in the privacy policy and the store listing, so an unmonitored inbox is
a broken promise.

**Acceptance** — `python scripts/check_operations.py` (T1.2) exits 0.

### T6.2 — Rehearse the four drills · `AGENT+HUMAN`

Corpus rollback, backend rollback, navigation kill switch, secret rotation.
Record the date and recovery time for each in `docs/OPERATIONS.md` §4. A rollback
that has never been performed is a plan, not a capability.

### T6.3 — Establish the watch · `HUMAN`

Someone must actually look at `/admin/usage` daily during the pilot: budget
neurons, provider calls per question, circuit state, active generations, corpus
version, `client_addressing.ok`. Agree in advance what triggers a pause.

---

## 8. Stream 7 — Cut the release candidate

**Preconditions:** every acceptance check in Streams 1–6 green.

1. Merge PR #2 into `release` (branch protection from T1.5 now requires review).
2. Run the full `docs/RELEASE_CHECKLIST.md` §A block from a clean checkout, plus
   `pip-audit -r requirements.lock.txt` with **no unresolved finding** (it is
   advisory in CI by design; it is blocking here).
3. `git tag -a vX.Y.Z` on the reviewed `release` commit — an artifact is only a
   release if `git tag --points-at HEAD` is non-empty. There is **no tag today**.
4. `python scripts/release_manifest.py --require-clean -o release/manifest.json`
   — commit SHA, corpus version, provider/model, extension version.
5. Deploy staging from the tag, run the full suite against it, then promote the
   **same artifact** to production. No rebuild between staging and production.
6. Smoke: `/live` 200, `/ready` 200 with the expected corpus version, one Arabic
   and one English question answered correctly.

---

## 9. Stream 8 — Staged rollout

Per `docs/RELEASE_CHECKLIST.md` §F. Do not compress these.

| Stage | Audience | Exit criteria |
|---|---|---|
| Internal alpha | maintainers only | uptime stable, sources correct |
| Closed pilot | 10–25 students, both languages, store visibility **Unlisted** | one week clean; navigation confirmation always on; opt-in feedback only |
| Limited rollout | wider, still monitored | error codes, quota, latency, refusal rate, navigation use, thumbs all within agreed bounds |
| General availability | public | Streams 1–7 green and held |

**Capacity reality check before GA.** ADR-001 puts the free Cloudflare tier at
~200 RAG answers/day. That is a closed-pilot budget, not a student body. Before
limited rollout, decide explicitly: raise the budget with someone paying, move to
the Oracle self-host, or cap the audience. Do **not** raise
`LLM_DAILY_NEURON_BUDGET` above the free allowance unless someone has agreed to
pay.

**Never use raw conversation text as a product metric.** The aggregate log
already gives counts, latencies, error codes, source ids and grounding verdicts,
which is what these decisions need.

---

## 10. Consolidated human-input list

Nothing in the repository can substitute for these. Everything else waits on
them, so chase them in this order:

| # | Input | Unblocks | Who to ask |
|---|---|---|---|
| 1 | Authorized Ritaj page export or approval to snapshot | Streams 2, 3, and therefore everything | Birzeit Computer Center / Registration Office |
| 2 | Named Arabic and English content approvers | T2.4 corpus publication | Owning Birzeit units |
| 3 | Navigation destination approver | T5.1 | Ritaj service owner |
| 4 | Cloudflare account + scoped Workers AI token | T4.1, all live evaluation | Project infrastructure owner |
| 5 | Hugging Face write token | T4.2, T4.4 (the 503) | Deployment owner |
| 6 | Chrome Web Store account ($5) + extension id | T5.3, production CORS | Extension owner |
| 7 | Named support/incident owners (9 duties × 2) | T6.1 | Project team |
| 8 | GitHub admin to protect `release` | T1.5 | Repository administrator |
| 9 | New operator passwords | T1.4 | Maintainer, via a password manager |

---

## Appendix A — Verified baseline (measured 2026-08-10, commit `3b2a6e3`)

Re-run before trusting; these are point-in-time measurements.

| Check | Result |
|---|---|
| `pytest -q` | 355 passed, 9.7 s |
| CI on `3b2a6e3` (dispatch run 31018965224) | all 6 jobs green, **including the container build** |
| `check_corpus_policy.py` | exit 0 — but **vacuous**: "artifact: none published" |
| `check_navigation.py` | exit 0 — 18/18 hostile URLs rejected; **5 actions awaiting approval** |
| `check_extension.py` / `check_privacy.py` | exit 0 |
| `eval_release.py` | exit 0 — 22 navigation cases, 100% destination precision, 100% intent recall |
| `eval_release.py --gate` | **exit 1** — `answerable 0/100`, `calendar 0/25`; navigation 22/20, unanswerable 15/15, personal_data 12/10, adversarial 8/5/12 |
| `sbom.py --check-pinned`, `lock_deps.py --check` | exit 0 |
| `loadtest.py` | exit 0 — soak 300 req, p50 69 ms / p95 81 ms, heap +0.2 MB; budget exhaustion refuses cleanly; circuit opens on provider failure. **Stub provider — application numbers only** |
| `secret_inventory.py` (full) | exit 1 — `LLM_API_KEY`, `ADMIN_USERS`, `SESSION_SECRET` missing. Expected locally; CI uses `--scan-only` (exit 0) |
| `package_extension.py --verify` | exit 0 on a clean tree; refuses if anything is uncommitted — **including untracked files** |
| Live Space `https://mohawwad04-ritaj-rag.hf.space` | **HTTP 503**, "your space is in error" |
| `data/sources.yaml` | 7 candidates, **all `approved: false`**, no snapshots |
| `data/navigation.yaml` | 5 actions, **all `enabled: false`**, `approved_by: ""` |
| `git tag` | **none** |
| `release/manifest.json` | **does not exist** |
| Branch protection on `release` | **not configured** (404) |
| `release/sbom.json` vs `requirements.lock.txt` | **stale** — see T1.1 |

**Fixed since the 2026-08-05 plan baseline:** portal lint runs, base image
digest-pinned, navigation eval category populated (0 → 22), branch pushed with
PR #2 open, container job actually builds, suite 312 → 355 tests.

## Appendix B — Environment bootstrap

```bash
cd ~/Desktop/ritaj-rag-chatbot
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env                        # then edit
ollama pull gemma4:e4b                      # dev LLM (gemma4:e2b on lighter machines)
docker run -p 6333:6333 qdrant/qdrant       # dev vector store

python scripts/build_index.py --dev         # DEV index from quarantine — never --publish
uvicorn ritaj.api:app --reload --app-dir src
```

Tests run with `STARTUP_INIT=0`, `ENVIRONMENT=development` (`tests/conftest.py`).
`config.check_production_config()` is fail-closed — production will not start
misconfigured, and that is deliberate.

---

*This file is untracked. Commit it, or `package_extension.py` and a production
`deploy_space.py` will refuse the tree — both call `git status --porcelain`,
which counts untracked files as dirty.*
