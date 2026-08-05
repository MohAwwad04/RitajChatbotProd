# Ritaj Assistant: ready-to-release execution plan

**Prepared:** 5 August 2026  
**Applies to:** `roadmap/2026-release` at `859773e` and later  
**Target release:** Chrome side-panel assistant backed by a Ritaj-only RAG service and Gemma 4  
**Primary production topology:** Hugging Face Space for the application, Cloudflare Workers AI for Gemma 4  
**Status:** not ready to release; implementation is advanced, but data, deployment, approval, and release gates remain incomplete

This document begins from the repository state verified on 5 August 2026. It is
an execution plan, not a description of an ideal future system. Every phase has
an outcome, a reason, concrete work, dependencies, verification, and an exit
gate. A release is allowed only when all blocking gates in this document and
`docs/RELEASE_CHECKLIST.md` are green.

---

## 1. Release objective

Ship a dependable Chrome extension for students using Ritaj that behaves as
follows:

1. The user clicks the extension icon.
2. Chrome opens a persistent side-panel chat.
3. The user asks a question in Arabic or English about Ritaj.
4. The backend answers only from approved material whose canonical source is
   exactly `https://ritaj.birzeit.edu`.
5. The answer cites the relevant Ritaj source and communicates uncertainty,
   staleness, or missing information honestly.
6. When navigation is useful, the backend proposes a reviewed action identifier.
7. The extension shows a clear confirmation button, validates the destination
   again, and opens or focuses the approved Ritaj page.

The release must not read a logged-in page, inspect the DOM, capture cookies or
credentials, access private student data, submit a form, register a course, pay
a fee, or change anything in Ritaj.

### 1.1 Non-negotiable data boundary

The production knowledge base may use only content with a canonical origin of:

```text
https://ritaj.birzeit.edu
```

The following are prohibited from the production corpus:

- `www.birzeit.edu` or any other host;
- search-engine snippets or cached copies;
- guessed or invented instructions;
- sample material;
- private or authenticated student records;
- content copied from a user's open browser page;
- content without an accountable owner, snapshot, hash, and approval record.

If a needed Ritaj page is protected by login or cannot be acquired safely, the
correct action is to request an authorized public export from the responsible
Birzeit unit. Bypassing access controls is not an ingestion strategy.

---

## 2. Verified baseline

### 2.1 What is already implemented

- A FastAPI RAG backend with dense and BM25 retrieval, fusion, multilingual
  reranking, streamed generation, citations, grounding checks, conversation
  history, and an admin surface.
- Startup now binds Uvicorn before expensive initialization. `/live`, `/ready`,
  and the legacy `/health` route exist.
- Exact-host Ritaj source policy, corpus manifests, approval fields, hashes,
  effective dates, and production fail-closed behavior exist.
- The old corpus is quarantined and excluded from production indexing.
- Retrieval filtering, duplicate control, relevance thresholds, abstention,
  source freshness, and language/date handling exist.
- Public API controls include request identifiers, bounded generation
  concurrency, daily provider budget, circuit breaking, safe error objects,
  production CORS validation, admin authentication, redaction, and aggregate
  operational logging.
- The extension is Manifest V3 version `1.1.0`, uses a Chrome side panel, stores
  bounded local history, streams answers, and supports stop, retry, clear,
  sources, and navigation actions.
- Navigation is deterministic: the model cannot invent a URL, and both backend
  and extension validate the destination.
- Privacy and store documents disclose the provider, retention, local storage,
  navigation behavior, and independent-project status.
- Cloudflare Workers AI configuration, provider contract tests, and a Gemma 4
  deployment runbook exist.
- CI contains backend, policy, security, frontend, extension, and container jobs.

### 2.2 Verified checks on 5 August 2026

| Check | Result | Release meaning |
|---|---:|---|
| Backend test suite | 312 passed | Strong local implementation baseline |
| Extension navigation tests | 9 passed | URL validator rejects the covered attacks |
| Portal TypeScript + production build | Passed | Portal compiles and bundles |
| Source, navigation, extension, privacy, secret, and model-free checks | Passed | Policy code is present and internally consistent |
| Release-set completeness | Failed | Correct blocker: no answerable/calendar/navigation evaluation corpus |
| Portal lint | Failed | ESLint 9 has no flat configuration |
| Reproducibility check | Warning | Docker base image is tag-pinned, not digest-pinned |
| Live Hugging Face service | HTTP 503 | Production is down and runs an older commit |

### 2.3 Current hard blockers

1. There is no approved Ritaj corpus and no published `data/corpus/CURRENT`.
2. All seven source candidates are unapproved.
3. The answerable, calendar, and navigation evaluation sets are empty.
4. All five navigation actions are disabled and have no approver.
5. The new branch is local, has no upstream, and has not been reviewed or
   merged into `release`.
6. There is no release tag or `release/manifest.json`.
7. The live Hugging Face Space is in `RUNTIME_ERROR` and contains the old data.
8. Cloudflare, Hugging Face, and Chrome Web Store production access have not
   been supplied to this repository workflow.
9. Store screenshots show the removed popup.
10. Human content, privacy, support, and incident-response ownership is not
    recorded.

---

## 3. Target architecture

```text
Chrome toolbar click
        |
        v
Chrome side panel
  - chat UI
  - local bounded history
  - destination revalidation
        |
        | HTTPS, extension origin allowed by production CORS
        v
Hugging Face Space / FastAPI
  - /live and /ready
  - admission controls
  - Ritaj-only hybrid retrieval
  - grounded response validation
  - deterministic action resolver
        |
        | server-side token only
        v
Cloudflare Workers AI
  - Gemma 4 generation

Approved Ritaj snapshots -> versioned corpus artifact -> retrieval service
Reviewed action registry -> action_id -> extension confirmation -> Ritaj page
```

The extension never receives the Cloudflare token. The language model never
selects an arbitrary URL. The application host can be replaced later without
changing these security boundaries.

---

## 4. Work order and dependencies

The critical path is:

```text
Repository gate fixes
        +
Authorized Ritaj acquisition
        |
        v
Published corpus and approved navigation registry
        |
        v
Complete bilingual release evaluation
        |
        v
Staging deployment with real Gemma provider
        |
        v
Browser E2E, load, security, and rollback tests
        |
        v
Reviewed tag and immutable release artifacts
        |
        v
Internal alpha -> closed pilot -> limited rollout -> general availability
```

Repository repairs and data acquisition should run in parallel. Evaluation
cannot be finalized before the approved corpus exists. Production CORS cannot
be finalized before the Chrome Web Store assigns the extension identifier.

---

## 5. Phase A: repair the engineering release gates

**Outcome:** the repository truthfully describes its behavior and every local
software gate is executable before external data or credentials are introduced.

### A1. Fix frontend lint

Work:

- Add an ESLint 9 flat configuration under `ritaj-student-portal`.
- Configure TypeScript, React hooks, React refresh, browser globals, and ignores
  for `dist` and generated assets.
- Fix actual lint violations; do not disable rules broadly just to make CI green.
- Add `npm run lint` to the frontend CI job before `npm run build`.

Reason: `npm run lint` exists but currently cannot start, while CI and release
documentation imply that linting is a gate.

Verification:

```bash
cd ritaj-student-portal
npm ci
npm run lint
npm run build
```

Exit gate: both commands exit zero in a clean checkout and in CI.

### A2. Correct anonymous rate limiting

Work:

- Replace the single `hash(IP + session_id)` bucket with independent controls:
  a privacy-preserving per-network/IP bucket and a per-session bucket.
- Do not trust `X-Forwarded-For` from arbitrary clients. Accept forwarded client
  information only from a documented trusted-proxy chain provided by the host.
- Add tests showing that changing `session_id` does not reset the network limit.
- Add tests for missing, malformed, and reused session identifiers.
- Confirm one campus NAT does not make normal use impossible; configure separate
  limits rather than weakening the identity model.
- Document that in-process limits are valid only for the single-worker/single-
  replica deployment. Require shared state before horizontal scaling.

Reason: the current combined bucket can be bypassed by minting a new session ID,
and the apparent client IP behind a hosting proxy may not be the originating IP.

Exit gate: adversarial tests prove session rotation cannot obtain an unlimited
number of provider calls.

### A3. Sanitize readiness failures

Work:

- Keep initialization exception details and tracebacks in protected logs.
- Return only stable public fields from `/ready`, such as `state`, `code`, safe
  timings, corpus version, and retry guidance.
- Never return provider URLs, account identifiers, filesystem paths, secret
  names, raw exception text, or source content.
- Add tests using exceptions that contain fake paths and tokens and prove the
  public response does not contain them.

Reason: exception messages are not guaranteed to be safe even when stack traces
are excluded.

Exit gate: `/ready` remains operationally useful without exposing injected
exception text.

### A4. Align request limits

Work:

- Choose one supported maximum question length and make Pydantic validation,
  `MAX_MESSAGE_CHARS`, extension validation, documentation, and tests agree.
- Enforce a real streamed-body cap or reject unsupported chunked oversized
  requests; checking `Content-Length` alone is insufficient.
- Keep bounded history turn count and per-turn length checks.

Exit gate: ordinary, oversized content-length, and oversized chunked requests
all have deterministic tests and safe public errors.

### A5. Make builds reproducible

Work:

- Replace `FROM python:3.11-slim` with the reviewed image digest.
- Install production Python dependencies from a locked, hashed resolution.
- Keep development-only packages out of the runtime image.
- Generate the release SBOM from the final container image rather than an
  arbitrary developer environment.
- Record model artifact identifiers and hashes in the release manifest.
- Decide when the large container build runs. It must be blocking for a release
  candidate even if it remains too expensive for every ordinary pull request.

Verification:

```bash
python scripts/sbom.py --check-pinned
docker build -t ritaj-assistant:release-check .
```

Exit gate: no mutable base-image warning, and two builds from the same tag use
the same locked inputs.

### A6. Update documentation to match the product

Work:

- Rewrite the root README so it no longer describes Groq, old `data/raw`
  content, unrestricted Birzeit sources, or vLLM as the selected pilot path.
- Rewrite `chrome-extension/README.md` to describe the side panel, not a popup.
- Clearly mark the older broad `PLAN.md` as historical or superseded where it
  conflicts with the Ritaj-only release boundary.
- Make CI comments, commit messages, release documentation, and actual triggers
  agree about which checks run on pull requests and release candidates.
- Link this plan, the roadmap, release checklist, threat model, and provider
  runbook from the root README.

Exit gate: a new maintainer can follow the README without being directed toward
the old corpus, old provider, or removed UI.

### Phase A verification

```bash
pytest -q
node --test chrome-extension/navigation.test.mjs
python scripts/check_extension.py
python scripts/check_privacy.py
python scripts/secret_inventory.py --scan-only
python scripts/sbom.py --check-pinned
cd ritaj-student-portal && npm run lint && npm run build
```

**Phase A done when:** all commands pass, documentation is consistent, and the
fixes are reviewed on a remote pull request.

---

## 6. Phase B: acquire and publish an authorized Ritaj-only corpus

**Outcome:** the service has a non-empty, versioned, approved knowledge base
that satisfies the user's single-source requirement.

### B1. Assign human ownership

For each topic, identify a person or accountable Birzeit unit that can approve
the content and its refresh interval. At minimum:

| Topic | Suggested accountable unit | Required coverage |
|---|---|---|
| Registration instructions | Registration office | add/drop, enrollment, common errors |
| Academic calendar | Academic/registration owner | term dates and deadlines |
| Course browser | Academic systems owner | course search and public catalog usage |
| Ritaj message boards | Ritaj/Computer Center owner | board navigation and public behavior |
| Account and portal help | Computer Center | login recovery and approved support route |

The repository cannot invent approvers. Record a name, unit, ticket, or approval
reference in `approved_by`.

### B2. Confirm the candidate URLs

Review every record in `data/sources.yaml`:

- confirm the URL exists and uses HTTPS;
- confirm the exact host is `ritaj.birzeit.edu`;
- confirm it is public and does not expose student-specific content;
- resolve the duplicate canonical registration URL;
- confirm the unverified English calendar path;
- assign content language, content type, owner, refresh interval, and effective
  dates;
- remove guessed candidates rather than approving them speculatively.

### B3. Acquire immutable source snapshots

Preferred acquisition order:

1. Authorized export supplied by the owning Birzeit unit.
2. Public Ritaj response fetched with permission and normal access rules.
3. Maintainer-reviewed manual export when automated fetch is unsuitable.

Each snapshot must include:

- canonical Ritaj URL;
- title and language;
- capture timestamp;
- content owner and approver;
- source last-modified value when available;
- SHA-256 content hash;
- effective-from/effective-to dates when relevant;
- refresh deadline;
- normalized content path;
- acquisition method and approval reference.

Do not store login pages, session tokens, cookies, student identifiers, grades,
balances, schedules, or personalized HTML.

### B4. Normalize and review content

- Preserve headings, tables, ordered instructions, dates, course codes, and
  Arabic directionality.
- Remove navigation chrome, repeated footers, session-specific values, and
  scripts.
- Do not translate an official source and present the translation as official.
  If bilingual content is needed, acquire or separately approve both versions.
- Present a human-readable diff or preview to the content owner before approval.
- Set `approved: true` only after the snapshot and metadata are complete.

### B5. Build the immutable corpus artifact

```bash
python scripts/check_corpus_policy.py
python scripts/build_index.py --publish
python scripts/check_corpus_policy.py
```

The published artifact must contain a manifest, hashes, chunk counts, model
identifiers, source references, build time, and a version identifier. Update
`data/corpus/CURRENT` only after verification. Retain the prior artifact for
rollback.

### B6. Test freshness and rollback

- Use a deliberately expired test source and verify the answer identifies it as
  stale or abstains according to policy.
- Change `CURRENT` to the previous version in staging, restart, and prove that
  the reported version and retrieval results change.
- Roll forward to the candidate artifact and repeat the health checks.

**Phase B done when:** `check_corpus_policy.py` reports a non-zero published
artifact, every production chunk traces to an approved exact-host Ritaj source,
and bilingual content owners sign off.

---

## 7. Phase C: complete the release evaluation

**Outcome:** the system's answer quality and refusal behavior are measured
against the corpus that will actually ship.

### C1. Populate the required sets

Create at least:

- 100 answerable questions;
- 25 academic-calendar questions;
- 20 navigation requests;
- 15 unanswerable/out-of-scope questions;
- 10 or more private/personal-data requests;
- Arabic, English, and realistically mixed-language cases;
- adversarial prompt-injection and malicious URL cases.

Every answerable case must point to approved source identifiers and expected
facts. Do not write expected answers from memory or from another website.

### C2. Cover high-risk cases

Include:

- conflicting old and current dates;
- expired academic-calendar content;
- similar Arabic terminology and spelling variants;
- course codes and exact strings;
- questions whose answer is absent from the corpus;
- requests for grades, balances, schedules, passwords, and student records;
- instructions hidden inside retrieved source text;
- lookalike hosts, encoded paths, protocol-relative URLs, fragments, and unsafe
  query parameters;
- ambiguous navigation intent that must ask a follow-up rather than guess.

### C3. Establish release thresholds

At minimum, measure:

- factual correctness;
- citation/source correctness;
- groundedness;
- appropriate abstention;
- language correctness;
- stale-source behavior;
- navigation action precision;
- malicious destination rejection;
- first-token and full-response latency.

Threshold changes require a reviewed reason. Never lower a threshold merely to
approve a known regression.

### C4. Run the gates

```bash
python scripts/eval_release.py
python scripts/eval_release.py --gate
pytest -q
```

Remove `continue-on-error` from release-set completeness once the data exists.
The model-free safety suite remains blocking on every pull request. The real
provider evaluation runs on staging before a release because it spends quota.

**Phase C done when:** completeness and quality gates pass on the exact corpus,
model configuration, and prompt intended for production, with recorded results.

---

## 8. Phase D: provision Gemma and deploy staging

**Outcome:** the complete application answers through the real provider on a
non-production URL with production-like configuration.

### D1. Provision external access

Required inputs:

- Cloudflare account ID;
- scoped Workers AI token with only the required inference permission;
- Hugging Face token with write access to a staging Space;
- a separate Hugging Face production Space/token scope where practical;
- final allowed web origins;
- candidate Chrome extension ID;
- production admin users and newly generated password hashes;
- a high-entropy session secret.

Secrets must be configured in the host secret manager, never committed, added
to the extension, printed in logs, or written into release artifacts.

### D2. Revalidate the provider contract

Before deployment, verify that the selected Gemma 4 model identifier, API
compatibility, free allowance, rate limits, input/output limits, streaming
format, and data handling still match `docs/DEPLOY_GEMMA4.md`. Provider terms
and catalogs can change; the checked-in plan is not proof of current service.

### D3. Configure staging

Use the runbook values, including:

```dotenv
ENVIRONMENT=production
LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
LLM_MODEL=@cf/google/gemma-4-26b-a4b-it
LLM_API_KEY=<HOST_SECRET>
LLM_DAILY_REQUEST_BUDGET=180
ALLOW_INDEX_BUILD_ON_BOOT=0
STARTUP_INIT=1
```

Also configure exact CORS origins, admin users, session secret, corpus artifact,
log retention, request limits, concurrency, timeouts, and circuit-breaker
settings. Production-mode validation must fail closed when a required value is
missing.

### D4. Deploy staging from a reviewed commit

```bash
python scripts/secret_inventory.py
python scripts/deploy_space.py --space staging
```

Do not deploy a dirty working tree. Record the commit SHA and corpus version.

### D5. Prove startup behavior

For three consecutive cold starts:

1. `/live` returns 200 within the host's health window.
2. `/ready` initially reports a safe initializing state.
3. `/ready` later returns 200 with the correct corpus version.
4. Initialization does not build the corpus from raw data.
5. No second model copy is created by multiple workers.
6. A failed initialization leaves `/live` responsive and `/ready` safely
   diagnostic.

### D6. Prove the real provider path

- Test Arabic, English, mixed language, refusal, stale source, and navigation.
- Confirm streaming events are parsed correctly.
- Confirm citations are derived from retrieved records, not model-generated URLs.
- Trigger a provider timeout and provider error; verify circuit breaking, retries,
  safe user errors, and request IDs.
- Exhaust a staging budget and verify the service stops spending predictably.
- Inspect `/admin/usage` using authenticated admin access.

**Phase D done when:** staging survives repeated cold starts and the complete
RAG-to-Gemma path passes the release evaluation without leaking secrets.

---

## 9. Phase E: finish navigation automation and the Chrome extension

**Outcome:** toolbar click opens a stable chat, and every navigation action is
safe, useful, reviewed, and tested in a real Chrome session.

### E1. Approve the action registry

For each entry in `data/navigation.yaml`:

- confirm exact scheme, host, path, allowed query parameters, and fragment rules;
- verify Arabic and English labels;
- confirm the page's behavior while logged out and logged in;
- fill `approved_by` and approval reference;
- enable the action only after review;
- retain a server-side kill switch through `enabled: false`.

Do not add generic “open this URL” behavior. New destinations require a new
reviewed action record and tests.

### E2. Preserve the automation boundary

The implemented flow must remain:

```text
user request
  -> backend selects a registered action_id
  -> backend resolves and validates the registered destination
  -> extension displays a confirmation button
  -> user explicitly clicks
  -> extension validates again
  -> service worker opens or focuses the Ritaj page
```

There must be no content scripts, `tabs` permission, `activeTab`, `scripting`,
webRequest interception, DOM reading, keystroke capture, form submission, or
credential access in this release.

### E3. Run browser E2E scenarios

Test the unpacked release candidate in Chrome:

- icon click opens the side panel and not a popup or full portal;
- the panel remains usable while the active tab navigates;
- Arabic RTL and English layouts are readable at supported panel widths;
- stream stop, retry, clear history, reconnect, and backend error states work;
- local history remains capped and clears completely;
- citations open only expected HTTPS destinations;
- navigation requires confirmation every time;
- malicious or modified action payloads are rejected by the extension;
- a disabled action cannot be used from old chat history;
- unauthenticated Ritaj redirects are handled by Ritaj, not inspected by the
  extension;
- no request is sent to any host other than the configured backend and the
  user-confirmed Ritaj destination.

### E4. Prepare store assets and listing

- Recapture three 1280x800 screenshots showing the side panel: English, Arabic,
  and a confirmed navigation suggestion.
- Replace all images showing the old popup.
- Confirm the support email is controlled and monitored.
- Make the privacy policy publicly reachable independently of a broken chat
  initialization where possible.
- Ensure listing copy says “independent student project,” not “official.”
- Start with Store visibility set to **Unlisted**.
- Complete the privacy and permission declarations using the checked-in copy.

### E5. Produce a reproducible extension package

Add or document a deterministic packaging command that:

- includes only the extension runtime and required assets;
- excludes tests, secrets, local configuration, and store drafts;
- reads the version from `manifest.json`;
- emits a SHA-256 checksum;
- refuses a dirty tree for release mode.

Record the package name and checksum in `release/manifest.json`.

**Phase E done when:** real Chrome E2E passes, every enabled destination has a
human approver, store assets show the side panel, and the exact reviewed ZIP is
ready for an Unlisted submission.

---

## 10. Phase F: security, privacy, performance, and operations

**Outcome:** maintainers can operate the pilot safely, detect failure, control
cost, and roll back without waiting for a new extension review.

### F1. Security verification

- Run the committed-secret scanner against tracked files and the extension ZIP.
- Run a current dependency vulnerability audit and review every high/critical
  finding; do not rely only on an advisory CI result.
- Scan the final container image and generate its SBOM.
- Verify admin authentication fails closed in production.
- Rotate the weak operator credentials called out in the release checklist.
- Confirm Cloudflare and Hugging Face tokens use minimum scope and have owners,
  rotation dates, and revocation instructions.
- Test CORS from the allowed extension/web origins and from a rejected origin.
- Test injection, SSRF-like URLs, lookalike domains, encoded paths, oversized
  bodies, rate-limit bypass attempts, and malformed streaming requests.

### F2. Privacy verification

- Confirm the portal and extension do not ask for or transmit a student's name.
- Confirm default logs contain only aggregate operational fields: request ID,
  status/error code, latency, provider usage, source identifiers, grounding
  result, and action identifier.
- Confirm no raw question, answer, page content, IP address, student ID, cookie,
  or credential enters default logs.
- Verify the 30-day retention process actually deletes eligible records.
- Document data correction and deletion contacts and name responsible people.
- Keep any feedback collection optional and separate from raw conversation
  storage.

### F3. Load and resilience verification

Test at least:

- normal sequential chat;
- supported concurrent generation count;
- queue timeout and `BUSY` response;
- per-session and per-network rate limits;
- daily provider budget exhaustion;
- provider 429, 500, timeout, broken stream, and malformed stream;
- corpus unavailable or corrupt;
- one cold start while clients poll readiness;
- a sustained pilot-sized soak without unbounded memory growth.

Record p50/p95 first-token latency, full-answer latency, error rate, provider
usage per answer, memory, and active-generation count. Capacity claims must come
from this test, not from the provider's theoretical maximum.

### F4. Operational ownership

Name owners and backups for:

- service uptime and Hugging Face deployment;
- Cloudflare quota and token rotation;
- corpus corrections and refresh;
- navigation kill switch;
- privacy/deletion requests;
- security incidents;
- Chrome Web Store listing and support inbox.

Create a short incident runbook for service outage, quota exhaustion, unsafe
answer, wrong destination, exposed secret, and extension regression.

**Phase F done when:** security findings are resolved or formally accepted,
load targets are measured, retention is verified, credentials are rotated, and
every operational duty has a named owner and backup.

---

## 11. Phase G: create the release candidate

**Outcome:** one immutable set of artifacts has passed staging and can be
promoted without rebuilding.

### G1. Merge through review

1. Push `roadmap/2026-release` to the GitHub origin.
2. Open a pull request with the roadmap, this execution plan, validation output,
   known limitations, and content approvals.
3. Require passing CI and human review.
4. Merge into `release` only after the approved corpus and release gates exist.
5. Configure branch protection for `main` and `release`.

### G2. Build and record immutable artifacts

From a clean `release` checkout:

```bash
pytest -q
node --test chrome-extension/navigation.test.mjs
python scripts/check_corpus_policy.py
python scripts/check_navigation.py
python scripts/check_extension.py
python scripts/check_privacy.py
python scripts/eval_release.py
python scripts/eval_release.py --gate
python scripts/secret_inventory.py
python scripts/sbom.py --check-pinned
cd ritaj-student-portal && npm run lint && npm run build
```

Then:

1. Tag the reviewed release commit as `vX.Y.Z`.
2. Build the immutable corpus artifact.
3. Build the container from the tag.
4. Build the extension ZIP from the same tag.
5. Generate `release/manifest.json` with commit, tag, corpus version and hash,
   container identity, provider/model, extension version and ZIP checksum, SBOM,
   and evaluation result identifier.
6. Deploy those artifacts to staging again and run final smoke tests.
7. Obtain final content and release sign-off.

No source, configuration, prompt, corpus, dependency, or package may change
between final staging and production promotion. A change creates a new release
candidate.

### G3. Rehearse rollback

- Backend: redeploy the previous known-good tag.
- Corpus: repoint `CURRENT` to the previous artifact and redeploy.
- Navigation: disable the affected action server-side and redeploy.
- Provider: stop generation safely when the provider or budget is unavailable.
- Extension: retain the previous package, recognizing that Store rollback may
  require review.

Record the rehearsal result and recovery time.

**Phase G done when:** the tag, manifest, checksums, SBOM, evaluation report,
approvals, rollback record, and exact deployable artifacts all refer to the same
reviewed release candidate.

---

## 12. Phase H: staged rollout

### H1. Internal alpha

Audience: maintainers and named Birzeit reviewers only.

Verify:

- uptime and cold start behavior;
- source correctness in both languages;
- safe abstention;
- action destinations and confirmation;
- quota dashboard, logs, support route, and rollback access.

Exit gate: no open critical defect, wrong source, private-data incident, or
unsafe destination.

### H2. Closed Unlisted pilot

Audience: approximately 10–25 consenting students covering Arabic and English.

Monitor only privacy-preserving aggregates:

- availability and error code counts;
- p50/p95 latency;
- quota usage and average output size;
- grounding/abstention rate;
- source identifiers used;
- action proposal and confirmation counts;
- optional thumbs feedback.

Do not use raw conversations as a default product metric.

Exit gate: stable operation for the agreed pilot period, no unresolved critical
content/privacy/security issue, and measured capacity supports expansion.

### H3. Limited rollout

- Expand gradually rather than publishing to everyone at once.
- Keep navigation confirmation enabled.
- Review error, cost, latency, grounding, refusal, and support data daily.
- Freeze new corpus sources and navigation actions during the observation week
  except for emergency corrections.

Exit gate: at least one stable observation week and explicit go/no-go approval
from technical, content, and privacy owners.

### H4. General availability

General availability is permitted only when every blocking item in this plan
and `docs/RELEASE_CHECKLIST.md` is green. Continue to label the product as an
independent project unless Birzeit grants written authorization to describe it
otherwise.

---

## 13. Release readiness matrix

| Gate | Required green condition | Evidence |
|---|---|---|
| Repository | Clean reviewed release tag | Git tag and protected-branch PR |
| Backend | Tests, lint, image build, startup checks pass | CI and cold-start record |
| Corpus | Non-zero artifact; exact-host Ritaj sources only | Corpus manifest and policy output |
| Content | Arabic and English owners approve | `approved_by` plus approval reference |
| Quality | Complete release set passes | Stored evaluation report |
| Provider | Real Gemma streaming and failure tests pass | Staging provider test record |
| Security | No unresolved critical secret/image/dependency issue | Audit and SBOM review |
| Privacy | Disclosure matches runtime; retention works | Policy check and deletion test |
| Navigation | Each enabled action reviewed and E2E tested | Registry approval and browser record |
| Extension | Side-panel E2E, new assets, signed package | ZIP checksum and Store draft |
| Operations | Monitoring, incident owners, and rollback rehearsed | Runbook and rehearsal record |
| Production | `/live` and `/ready` healthy on promoted artifacts | Post-deploy smoke report |

Any red row blocks release. “Mostly complete” is not a release state.

---

## 14. External input tracker

| Input | Owner | Current status | Blocks |
|---|---|---|---|
| Authorized Ritaj snapshots/export | Birzeit content/Computer Center owner | Missing | Corpus, evaluation, release |
| Arabic and English content approval | Named content owners | Missing | Corpus publication |
| Navigation destination approval | Ritaj service owner | Missing | Automation enablement |
| Cloudflare account and scoped token | Infrastructure owner | Missing | Real Gemma staging |
| Hugging Face write access | Deployment owner | Missing | Staging/production repair |
| Chrome Web Store developer access and ID | Extension owner | Missing | CORS and Store release |
| Support and incident-response owners | Project team | Missing | Pilot operation |
| Privacy wording approval | Privacy/project owner | Missing | Store submission |
| GitHub branch protection | Repository administrator | Not configured | Controlled release process |

These items require people or systems outside the repository. Code should not
pretend to satisfy them.

---

## 15. Risk register

| Risk | Likelihood/impact | Mitigation | Release trigger |
|---|---|---|---|
| No authorized corpus | High/high | Obtain approved export first; keep fail-closed | Zero approved chunks blocks release |
| Provider free quota too small | Medium/high | Daily budget, short prompts, pilot cap, usage dashboard | Pause expansion before paid use |
| HF cold-start regression | Medium/high | Bind first, prebuilt corpus, offline model assets, three-start gate | Any failed cold start blocks promotion |
| Wrong or stale date | Medium/high | Effective dates, freshness policy, calendar eval, owner review | Wrong deadline stops rollout |
| Model invents an action URL | Low/high | Action IDs only; backend and extension validation | Any arbitrary URL is critical |
| Lookalike/encoded URL bypass | Low/high | Exact scheme/host/path/query validation and hostile tests | Any bypass is critical |
| Rate-limit bypass drains quota | Medium/high | Separate session/network buckets and provider budget | Adversarial bypass blocks staging |
| Secret reaches client/log/repo | Low/critical | Host secret manager, scans, redaction, rotation | Rotate and investigate immediately |
| Private Ritaj data is ingested | Low/critical | Public-only policy, manual review, no DOM permissions | Remove artifact and stop service |
| Store review delays rollback | Medium/medium | Server-side kill switches and backward-compatible API | Keep previous API/package supported |
| Documentation misleads operators | Medium/medium | Update README and validate runbook in clean checkout | Documentation review required |

---

## 16. Recommended execution batches

Effort estimates are working ranges, not calendar commitments. External
approval and Store/provider availability can dominate elapsed time.

### Batch 1: repository hardening — approximately 2–4 engineering days

- ESLint configuration and CI lint.
- Rate-limit identity correction and tests.
- Readiness sanitization and tests.
- Request-size alignment.
- Docker/lock/SBOM reproducibility.
- README and CI documentation corrections.

### Batch 2: corpus and approvals — approximately 3–10 working days plus review

- Assign owners.
- Validate Ritaj candidates.
- Acquire and normalize approved snapshots.
- Publish first corpus artifact.
- Rehearse freshness and rollback.

### Batch 3: evaluation — approximately 3–5 engineering/content days

- Write bilingual golden and adversarial cases.
- Run retrieval and answer review.
- Correct corpus/prompt/retrieval defects.
- Make completeness blocking.

### Batch 4: staging and extension completion — approximately 3–5 days

- Provision Cloudflare/Hugging Face/Store inputs.
- Deploy and cold-start test staging.
- Approve navigation actions.
- Execute real Chrome E2E.
- Recapture Store assets and build the package.

### Batch 5: release and pilot — approximately 1–2 days plus pilot observation

- Security, privacy, load, and rollback checks.
- Tag and generate the immutable manifest.
- Promote the same artifacts.
- Internal alpha, closed pilot, and observation period.

---

## 17. Immediate next actions

Do these next, in order where dependencies require it:

1. Push the current roadmap branch and open a review PR; do not merge or deploy
   it as a production release yet.
2. Fix ESLint and make portal lint an actual CI gate.
3. Correct rate limiting, readiness output, and request-size enforcement.
4. Pin the runtime image/dependencies and generate the SBOM from the container.
5. Update the root and extension READMEs.
6. Obtain named owners and authorized Ritaj snapshots/exports.
7. Complete `data/sources.yaml`, resolve the duplicate URL, and publish the first
   non-empty corpus artifact.
8. Populate and pass the answerable, calendar, and navigation evaluation sets.
9. Obtain scoped Cloudflare and Hugging Face staging credentials and deploy the
   reviewed candidate.
10. Approve actions, run Chrome E2E, replace popup screenshots, and submit an
    Unlisted pilot only after all blocking gates pass.

The critical business dependency is item 6. The critical engineering work is
items 2–5. Both should begin immediately.

---

## 18. Definition of ready to release

The project is ready to release only when all of the following are true:

- The production commit is reviewed, tagged, clean, and protected.
- All blocking CI checks pass, including lint, release-set completeness,
  container build, policy checks, and tests.
- The final container and extension package are reproducible and checksummed.
- The corpus is non-empty, versioned, approved, and derived only from exact-host
  Ritaj sources.
- No sample, external-domain, authenticated, or personalized content is indexed.
- Arabic and English answer quality passes the release thresholds.
- All enabled navigation destinations are approved and confirmation remains on.
- The extension reads no page data and has no permission capable of form
  automation or credential access.
- The real Gemma provider works under measured budget, latency, and failure
  behavior.
- `/live` and `/ready` survive three cold starts on staging and production.
- Privacy disclosures match the deployed code and retention is verified.
- Secrets are server-side, scoped, scanned, and rotated where required.
- Store screenshots and copy describe the side panel and independent status.
- Monitoring, support, incident response, content correction, and rollback have
  named owners.
- The exact artifacts tested in staging are promoted to production without a
  rebuild.
- Internal alpha and closed pilot exit gates are satisfied.

Until every statement above is true, the accurate status is **release
candidate in progress**, not ready to release.

