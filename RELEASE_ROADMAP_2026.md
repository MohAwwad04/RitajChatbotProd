# Ritaj Assistant: implementation and release roadmap

**Prepared:** 4 August 2026  
**Scope:** Chrome extension, RAG service, Gemma 4 hosting, Ritaj-only knowledge,
safe page navigation, deployment, testing, and release operations.  
**Status:** implementation plan; no production deployment is authorized by this
document.

## 1. Executive decision

The recommended first production architecture is:

1. Keep the existing Hugging Face Space as the application host after fixing
   its startup failure.
2. Replace Groq/Llama with Cloudflare Workers AI's hosted
   `@cf/google/gemma-4-26b-a4b-it` for the release pilot.
3. Convert the Chrome popup into a persistent Chrome side panel that opens when
   the toolbar icon is pressed.
4. Add **navigation assistance only**: the backend proposes a reviewed,
   allowlisted `https://ritaj.birzeit.edu/...` destination and the extension
   opens it after a user click. It must not register courses, submit forms,
   change student data, pay fees, or handle credentials.
5. Replace the production knowledge collection with pages whose canonical
   source is exactly `ritaj.birzeit.edu`. Do not index `www.birzeit.edu`, search
   result snippets, invented instructions, or the current `SAMPLE` sections.

This is the fastest credible path to a responsive release. Cloudflare already
serves Gemma 4 through an OpenAI-compatible endpoint, so the current LLM client
needs configuration changes rather than a rewrite. Its free allocation is
limited, so an Oracle self-hosted option remains the independence/fallback path.

There is no honest free, always-on GPU server with unlimited production usage.
The free choices trade off quotas, speed, availability, or all three.

## 2. Verified current state

### 2.1 What works locally

- The backend is a real FastAPI RAG service with dense and BM25 retrieval, RRF,
  multilingual reranking, streamed generation, citations, grounding checks,
  prompt-injection filtering, conversation replay, and an admin console.
- The Manifest V3 extension is already a thin chat client. Clicking its icon
  opens `popup.html`, streams `/chat/stream`, stores the conversation locally,
  and displays deterministic page links.
- The React portal builds successfully.
- The full local test suite passed on 4 August 2026: **133 tests passed** with
  one non-failing deprecation warning.
- `npm run build` completed successfully.

### 2.2 Immediate release blockers

1. **Production is down.** The public health route returned HTTP 503. Hugging
   Face reported `RUNTIME_ERROR` with: `Launch timed out, workload was not
   healthy after 30 min`.
2. **Startup blocks before the web server listens.** `scripts/start.sh` runs
   `ensure_index.py` before Uvicorn. Model/index initialization can therefore
   consume the entire Hugging Face launch window.
3. **The production corpus violates the requested source policy.** Several
   files cite `www.birzeit.edu`, `koha.birzeit.edu`, or no canonical URL; many
   sections are explicitly labeled `SAMPLE`. These cannot remain in the
   production index under the new Ritaj-only rule.
4. **The link map also contains off-domain URLs.** `data/links.yaml` must be
   generated from approved Ritaj source records instead of manually mixing
   domains and guessed/fallback links.
5. **Privacy statements and behavior disagree.** The policy says no names are
   collected, while the web portal asks for a name and sends it to the backend.
   It also names Groq, which will be false after the model migration.
6. **Product identity is inconsistent.** The store listing says this is an
   independent student project, while the generation system prompt calls it
   the "official" helper. It must say "independent" until Birzeit formally
   approves it.
7. **The public API has no anonymous rate limit.** A free LLM quota or a
   two-core CPU host can be exhausted by one client.
8. **CORS is unrestricted.** `allow_origins=["*"]` lets any site consume the
   public chat service. Production should allow the published extension origin
   and the deployed web origin, with a separate development setting.
9. **Raw backend exceptions are streamed to users.** Production errors should
   have a public error code while full details stay in protected logs.
10. **Deployment uploads the working tree.** The repository currently contains
    uncommitted work. A release must come from a reviewed commit/tag, not an
    arbitrary dirty tree.

## 3. Hosting research and decision

All limits below were checked against official provider documentation on
4 August 2026.

| Option | Free resources | Can upload own Gemma weights? | Suitability |
|---|---|---:|---|
| Cloudflare Workers AI | 10,000 neurons/day; Gemma 4 26B A4B is available and has an OpenAI-compatible API | No; provider-hosted model | **Recommended pilot LLM.** Fastest migration and best user experience within the daily quota. |
| Oracle Cloud Always Free A1 | 2 OCPU and 12 GB RAM total, 200 GB block storage | Yes | **Recommended self-host experiment.** Run quantized Gemma 4 E2B with Ollama or llama.cpp; expect CPU latency and low concurrency. |
| Existing HF CPU Space | 2 vCPU, 16 GB RAM, non-persistent disk; free hardware sleeps | Technically, but not reliably beside the current embedder/reranker | Keep for the app after fixing startup. Do not place the current RAG stack and Gemma in the same 16 GB/2-core container. |
| HF ZeroGPU | Shared 48 GB or 96 GB GPU; free account usage is 5 minutes/day | Yes, through supported Gradio/ZeroGPU workflow | Not suitable for an always-available extension; current Docker/FastAPI design would also require a Gradio-specific rewrite. |
| Colab/Kaggle notebooks | Temporary GPU sessions | Yes | Development/evaluation only, not a dependable public server. |
| Typical Render/Railway/Koyeb free services | Small RAM or trial credits | Not at the required size | Rejected for self-hosted Gemma and the current model-heavy backend. |

Official references:

- [Gemma 4 model sizes and memory requirements](https://ai.google.dev/gemma/docs/core)
- [Ollama Gemma 4 packages](https://ollama.com/library/gemma4)
- [Cloudflare Gemma 4 26B A4B](https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/)
- [Cloudflare Workers AI pricing/free allocation](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Cloudflare OpenAI-compatible endpoint](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [Hugging Face Spaces resources and lifecycle](https://huggingface.co/docs/hub/spaces-overview)
- [Hugging Face ZeroGPU quotas and compatibility](https://huggingface.co/docs/hub/main/en/spaces-zerogpu)

### 3.1 Why Cloudflare is the release recommendation

The current `src/ritaj/llm.py` already sends OpenAI Chat Completions requests.
The migration values are:

```dotenv
LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
LLM_MODEL=@cf/google/gemma-4-26b-a4b-it
LLM_API_KEY=<CLOUDFLARE_API_TOKEN>
```

No secret belongs in source control or the extension. The API token remains a
server-side secret.

Cloudflare's current price table assigns Gemma 4 approximately 9,091 neurons
per million input tokens and 27,273 per million output tokens. A representative
RAG request with 4,000 input tokens and 500 output tokens consumes roughly 50
neurons. The 10,000-neuron free allowance would therefore cover roughly 200
such answers/day. Shorter prompts can support more; follow-up condensation,
long history, and longer answers support fewer. Treat this as a pilot capacity
estimate, not a guarantee.

### 3.2 The self-hosted alternative

Oracle's free A1 allocation is currently 2 OCPU/12 GB across the account. The
Ollama `gemma4:e2b` package is about 7.2 GB on disk. It can be tested there with
a constrained context, one inference slot, and a reverse proxy, but CPU
generation will be much slower than Workers AI.

Oracle also states that idle free instances may be reclaimed when CPU, network,
and A1 memory utilization remain below its thresholds over seven days. Free
capacity can be unavailable in a chosen region. These are operational risks,
not footnotes.

Use one of these topologies:

- **Split topology:** existing HF Space runs the RAG app; Oracle runs only
  Gemma. This preserves memory for each component.
- **Single Oracle topology:** use Gemma E2B plus a deliberately lighter RAG
  runtime: precomputed document vectors, a small multilingual query embedder,
  no heavyweight cross-encoder, a single web worker, and a bounded 8K context.
  Benchmark memory and p95 latency before choosing it.

Do not promise that the current E5-large + BGE-M3 reranker + Qdrant + Gemma stack
will fit safely in 12 GB without measurement. It is likely to swap or be killed.

## 4. Target product behavior

### 4.1 User experience

1. The student visits Ritaj and clicks the Ritaj Assistant toolbar icon.
2. Chrome opens a persistent side panel containing only the chat experience.
3. The student asks in Arabic or English.
4. The assistant returns a concise, grounded answer, the source page title and
   date, and—when helpful—a clear button such as **Open Course Registration**.
5. The student presses the button. The extension opens or focuses the reviewed
   Ritaj destination. The chat stays visible in the side panel.
6. If the destination requires login, Ritaj handles the session. The extension
   does not read or transmit the password, cookies, student ID, balance, grades,
   or page DOM.

### 4.2 Product boundaries

The first release may:

- answer from approved public Ritaj material;
- explain where a page is and how to use it;
- open an allowlisted Ritaj page;
- retain conversation locally;
- show source freshness and uncertainty;
- ask the user to confirm navigation.

The first release must not:

- scrape or index private authenticated content;
- answer personal questions such as "what is my GPA?";
- read the user's Ritaj page, cookies, local storage, or form values;
- fill, click, submit, register, drop, pay, or alter records;
- open a URL generated directly by the model;
- navigate to any host other than exactly `ritaj.birzeit.edu`;
- claim to be an official university product without authorization.

## 5. Target architecture

```text
Chrome action click
    |
    v
Ritaj Assistant side panel (MV3)
    |  POST /v2/chat/stream over HTTPS
    v
FastAPI application host
    |-- request validation, anonymous rate limit, safe logging
    |-- Ritaj-only hybrid retrieval
    |-- source and freshness checks
    |-- deterministic navigation-intent resolver
    |-- grounded answer validation
    |
    +--> Cloudflare Workers AI / Gemma 4 (recommended pilot)
    |        or Oracle-hosted Gemma 4 E2B (self-host option)
    |
    +--> versioned Ritaj public index
             documents carry canonical source URL, date, language and hash

Response events
    sources -> answer tokens -> grounding -> navigation suggestion -> done
    |
    v
User clicks "Open ..." -> extension validates allowlist -> chrome.tabs API
```

Answer generation and navigation resolution are separate. A plausible LLM
answer can never grant itself browser authority.

## 6. Work plan

### Phase 0 — protect the current work and establish release control

**Goal:** make every later change reviewable and reversible.

Tasks:

1. Preserve the current dirty tree on its own branch/commit after a human
   reviews the uncommitted admin, privacy, and deployment changes.
2. Create `develop`, `staging`, and protected `release` flows, or use equivalent
   pull-request gates.
3. Add a release manifest recording commit SHA, corpus version, model/provider,
   extension version, and deployment time.
4. Change `scripts/deploy_space.py` to refuse a dirty tree by default. Allow a
   deliberate override only for non-production preview Spaces.
5. Inventory secrets without printing them. Rotate any token that has ever been
   pasted, logged, committed, or put in an extension package.
6. Record two architecture decisions:
   - ADR-001: Workers AI for pilot vs Oracle self-host.
   - ADR-002: navigation-only automation for version 1.

Exit gate:

- A tagged commit can reproduce an artifact, and rollback points to a known
  prior tag and corpus version.

Reasoning: the current deployment script stages the working directory directly.
That is useful during development but unsafe for a public release.

### Phase 1 — restore and stabilize the live application

**Goal:** remove the present 503 before adding features.

Tasks:

1. Split health into:
   - `/live`: process is listening; never waits for models or the index.
   - `/ready`: corpus loaded, retrieval works, and LLM configuration is valid.
2. Start Uvicorn immediately. Do not run a long, blocking index build before
   binding the HTTP port.
3. Build the production index in CI/deployment and ship a versioned seed
   artifact. On boot, copy/open that artifact from writable storage.
4. If background initialization remains necessary, expose its state and return
   a bounded `503 {"code":"INITIALIZING"}` from chat until ready.
5. Set `QDRANT_PATH=/tmp/qdrant` in the deployment definition, not only as an
   undocumented dashboard variable.
6. Set Hugging Face model loading to offline at runtime after weights are baked
   into the image, preventing startup HEAD requests and retry delays.
7. Add outbound timeouts, one retry with jitter for transient LLM failures, and
   a circuit breaker. Never retry a streamed request after tokens are emitted.
8. Limit concurrency to match the host. A two-core CPU service should not load
   multiple model copies through multiple workers.
9. Capture protected startup logs and measure time for process listen, index
   ready, first retrieval, and first token.
10. Deploy to a staging Space first; test `/live`, `/ready`, one Arabic query,
    one English query, one blocked personal query, and one navigation intent.

Exit gate:

- The staging service starts within two minutes, stays ready across three
  restarts, and passes an automated 30-minute soak test.

Reasoning: a healthy API must be able to report that it is initializing. Making
the entire web process wait for model/index work causes hosting platforms to
kill an otherwise recoverable deployment.

### Phase 2 — rebuild the database from Ritaj only

**Goal:** create a defensible source-of-truth corpus.

#### 2.1 Source policy

Every production record must satisfy all of these conditions:

- canonical URL uses `https`;
- `hostname == "ritaj.birzeit.edu"` exactly;
- it is public information approved for this assistant;
- source content was fetched/exported directly from Ritaj, not copied from a
  third-party site or search result;
- the record stores retrieval time, content hash, language, page title,
  effective date when applicable, and approval status;
- the source can be opened by a reviewer;
- the text contains no personal student data or credentials.

The current production index must exclude all current off-domain and `SAMPLE`
material. Keep it in a quarantine folder only if it is useful as development
test data, and ensure production build code cannot see that folder.

#### 2.2 Ritaj pages discovered during research

Publicly indexed Ritaj areas include:

- `/register/` public directory;
- `/reg/instructions` registration instructions;
- `/academic-calendar` and the newer public academic-calendar route;
- `/hemis/courses` course browser;
- `/bzu-msgs/boards` public boards;
- academic guides, regulations, FAQs, ITC, payment instructions, contacts and
  other public links exposed by the Ritaj directory.

These are discovery candidates, not automatic approval. Each exact URL must be
reviewed and entered into the source manifest.

#### 2.3 Acquisition constraint

Direct automated requests to the Ritaj root and `robots.txt` returned a
Cloudflare managed challenge (HTTP 403) during this audit. Do not bypass that
protection.

Use one of these authorized acquisition paths, in priority order:

1. Birzeit Computer Center supplies an export/API or allowlists the ingestion
   job's identity and rate.
2. A content owner exports approved public pages/PDFs to a signed snapshot.
3. A reviewer uses an authenticated browser to save a public page deliberately,
   then records the canonical Ritaj URL and approval. This is a manual snapshot,
   not a general authenticated crawler.

Search-engine cache/snippet text is not an acceptable production source. If
none of the authorized acquisition paths is available, reduce the launch scope
to the small set of verifiable public documents; do not fill gaps with guesses.

#### 2.4 Source manifest

Add `data/sources.yaml` with a schema like:

```yaml
- id: registration-instructions-ar
  canonical_url: https://ritaj.birzeit.edu/reg/instructions
  title: تعليمات التسجيل
  language: ar
  visibility: public
  content_kind: html
  owner: registration-office
  refresh: weekly
  approved: true
  approved_by: <role-or-ticket>
  fetched_at: 2026-08-04T00:00:00Z
  effective_from: null
  effective_to: null
  sha256: <content-hash>
  navigation:
    id: course-registration
    label_ar: فتح تسجيل المساقات
    label_en: Open course registration
    destination: https://ritaj.birzeit.edu/reg/
    auth_required: true
```

The build must fail if the host is wrong, required metadata is missing, the hash
does not match, or an unapproved record enters the production set.

#### 2.5 Ingestion pipeline

1. Fetch/import into `data/snapshots/<corpus-version>/`.
2. Preserve raw HTML/PDF plus response metadata for audit.
3. Remove navigation chrome, scripts, repeated footers, and hidden elements.
4. Preserve headings, lists, tables, dates, language and canonical URL.
5. Split Arabic and English variants without machine-inventing missing text.
6. Chunk by document structure, then token budget; attach the full metadata to
   every chunk.
7. Detect personal identifiers, passwords, account numbers and prompt-injection
   text. Quarantine flagged records for human review.
8. Create embeddings and BM25 data offline.
9. Run retrieval evaluation before promoting the corpus.
10. Publish an immutable corpus artifact and manifest.

#### 2.6 Freshness

- Calendar/deadlines: check daily during registration/exam periods, otherwise
  weekly.
- Course browser/registration instructions: weekly and before each term.
- Boards/announcements: daily only if approved for ingestion.
- Regulations/guides: monthly plus change notification from the content owner.
- A changed hash creates a review task; it does not silently replace production
  facts.
- Expired dates remain searchable only when the query names the old year; the
  default answer prefers the currently effective record.

Exit gate:

- 100% of indexed chunks trace to an approved `ritaj.birzeit.edu` URL, and the
  build emits zero off-domain or unapproved records.

Reasoning: citations are only trustworthy when provenance is enforced by code,
not by comments in hand-written Markdown.

### Phase 3 — retrieval and answer-quality improvements

**Goal:** make the Ritaj-only corpus accurate in both Arabic and English.

Tasks:

1. Keep hybrid dense + BM25 retrieval, but benchmark model size against startup
   and host memory. Evaluate a smaller multilingual embedder if needed.
2. Generate BM25 tokens from the actual Arabic source pages, eliminating the
   current English-only sparse-search limitation.
3. Add metadata filters for language, academic year, effective date, document
   type and public visibility.
4. Retrieve a wider candidate set, deduplicate adjacent chunks from the same
   section, then rerank only the remaining candidates.
5. Put canonical URL and source date into the model-visible citation header.
6. Require an abstention if no source clears the calibrated relevance threshold.
7. Ensure grounding verification runs on the exact text the user ultimately
   sees, including repaired answers.
8. Add citation coverage, stale-source and contradictory-date checks.
9. Change the system identity to an independent Ritaj assistant until official
   approval is documented.
10. Add a fixed bilingual response for personal-data questions that explains
    that the release cannot inspect a student's account.

Evaluation set:

- at least 100 bilingual questions;
- at least 25 current-calendar/deadline questions;
- at least 20 navigation intents;
- at least 15 unanswerable/out-of-scope questions;
- at least 10 personal-data requests;
- Arabic dialect, spelling variations and mixed Arabic/English course codes;
- adversarial instructions inside both queries and source documents.

Release thresholds:

- retrieval recall@10 >= 95%;
- supported-answer accuracy >= 90%;
- citation precision >= 95%;
- unsupported factual claim rate < 2%;
- correct refusal >= 95%;
- navigation destination precision = 100% on the release set.

Navigation precision is intentionally stricter because a wrong answer is bad,
but sending a student to an unrelated or unsafe page changes browser state.

### Phase 4 — harden the API contract

**Goal:** make the backend safe for a public extension and a free quota.

#### 4.1 Versioned request

```json
{
  "message": "Open course registration",
  "history": [],
  "session_id": "random-local-uuid",
  "client": "chrome-extension",
  "locale": "en",
  "current_ritaj_path": "/register/"
}
```

`current_ritaj_path` is optional. If used, send only the path after an explicit
in-product disclosure; do not send page text, query parameters, cookies, title,
student identity, or form state. It is unnecessary for the first release and
can be omitted to keep permissions minimal.

#### 4.2 Versioned response events

```json
{"type":"sources","sources":[{"title":"...","url":"https://ritaj.birzeit.edu/...","as_of":"2026-08-04"}]}
{"type":"token","text":"..."}
{"type":"navigation","action":{"id":"course-registration","label":"Open course registration","url":"https://ritaj.birzeit.edu/reg/","auth_required":true,"requires_confirmation":true}}
{"type":"done","request_id":"..."}
```

Clients must ignore unknown event types for forward compatibility.

#### 4.3 Public-service controls

- Enforce message, history, turn and total-body limits.
- Rate-limit anonymous chat by privacy-preserving network bucket plus local
  session, with lower burst and daily limits aligned to model quota.
- Set a global concurrent-generation cap and queue timeout.
- Return `429` with a retry hint when capacity is exhausted.
- Allow only the deployed web origin and published extension ID in production
  CORS; configure development origins separately.
- Protect all admin routes in every public environment. Refuse startup if no
  production admin configuration is set.
- Store no raw password, cookie, authorization header, or Ritaj DOM content.
- Redact likely student IDs, emails, phone numbers and secrets before logs.
- Default to aggregate metrics; retain raw conversations only with a clear
  opt-in and a defined deletion period.
- Replace public exception text with stable codes such as `LLM_UNAVAILABLE`.
- Add request IDs, structured logs and provider usage accounting.

Exit gate:

- Abuse, quota, CORS, error-redaction and admin-auth integration tests pass.

### Phase 5 — replace the popup with a focused side-panel chat

**Goal:** clicking the extension icon opens only a persistent chat beside Ritaj.

Chrome's Side Panel API is designed for this: it can open on an action click and
remain present while the student navigates. See the official
[Side Panel API documentation](https://developer.chrome.com/docs/extensions/reference/api/sidePanel).

Tasks:

1. Rename/reuse the popup UI as `sidepanel.html`, `sidepanel.css`, and
   `sidepanel.js`.
2. Remove `action.default_popup` from `manifest.json`.
3. Add:

   ```json
   {
     "permissions": ["storage", "sidePanel"],
     "side_panel": {"default_path": "sidepanel.html"},
     "background": {"service_worker": "service-worker.js"}
   }
   ```

4. In the service worker, set
   `chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true})`.
5. Make the layout responsive to panel width rather than hard-coding
   `384px x 560px`.
6. Remove the "open full portal" button so icon click presents a single-purpose
   chat. Keep language, new chat, retry and clear-history controls.
7. Preserve the conversation in `chrome.storage.local`, but cap stored turns
   and bytes. Add a visible **Clear history** action.
8. Use an `AbortController` so the user can stop a response and so abandoned
   streams do not consume quota.
9. Render source title, Ritaj hostname, effective date, and navigation buttons
   separately from answer text.
10. Add keyboard operation, focus states, screen-reader status messages,
    sufficient contrast, Arabic RTL tests, and reduced-motion behavior.
11. Show initialization, offline, quota-exhausted and provider-unavailable states
    with useful retry timing.

Minimal permissions are preferable. Chrome states that creating or navigating
a tab normally does not require the broad `tabs` permission. Do not request
`tabs`, `scripting`, or persistent Ritaj host access unless a later approved
feature truly needs page data. See the official
[Tabs API permission guidance](https://developer.chrome.com/docs/extensions/reference/api/tabs).

Exit gate:

- Toolbar click opens the side panel; chat survives navigation; no popup or
  unrelated portal UI appears; Arabic and English flows pass accessibility and
  extension E2E tests.

### Phase 6 — add safe page-navigation automation

**Goal:** help the student reach the requested Ritaj page without giving the LLM
arbitrary browser control.

#### 6.1 Navigation registry

Create `data/navigation.yaml`, reviewed and generated from the approved source
manifest. Each action contains:

- stable action ID;
- Arabic/English labels and intent phrases;
- exact canonical destination;
- whether login is required;
- safe query parameters, if any;
- minimum intent confidence;
- source/owner/approval metadata;
- optional relevant document IDs.

At load time, reject every destination unless:

```text
scheme == https
hostname == ritaj.birzeit.edu
no embedded credentials
no fragment/script URL
path matches the registered action
query keys are a registered subset
```

#### 6.2 Resolver

Use deterministic resolution in this order:

1. Explicit exact intent/alias match in Arabic or English.
2. Retrieval metadata points to one reviewed action and passes a high threshold.
3. Optional Gemma tool/function call returns an **action ID only**, never a URL;
   the server resolves that ID through the registry.
4. Otherwise return normal source links with no navigation action.

#### 6.3 Execution policy

| Request type | Behavior |
|---|---|
| "Open course registration" | Show/open the registered page after confirmation. |
| "Where can I register?" | Answer briefly and show an **Open** button. |
| "How do I register?" | Give grounded instructions; show the button but do not navigate automatically. |
| "Register COMP233 for me" | Refuse the transaction; offer to open registration. |
| "Pay my fees" | Refuse payment automation; offer the official payment-instructions destination if approved. |
| Ambiguous request | Ask a clarification or show at most two reviewed choices. |
| Personal record request | Explain that personal data is unavailable; optionally open the appropriate Ritaj landing page. |

Default `requires_confirmation` to true. A later opt-in setting may let explicit
"open/go to" commands navigate immediately, but the student must enable it and
must be able to turn it off.

#### 6.4 Extension validation

The extension independently parses and checks every URL before calling
`chrome.tabs.create()` or `chrome.tabs.update()`. Backend validation alone is
not enough. If validation fails, render no clickable action and record only a
non-sensitive local diagnostic.

#### 6.5 What is deliberately postponed

Form filling, DOM reading, clicks, submission and personalized tools require
additional Chrome permissions and university authorization. They also implicate
Chrome Web Store browsing-data rules and Ritaj account security. Treat them as a
separate future product with explicit consent, transaction previews, audit
logs, idempotency, step-up confirmation and official APIs—not as an extension
of navigation.

Exit gate:

- All release navigation cases resolve to the correct registered action; fuzz
  tests cannot produce an off-domain, `javascript:`, credential-bearing, or
  unregistered destination.

### Phase 7 — deploy Gemma 4 and the application

#### 7.1 Recommended pilot deployment

1. Create a scoped Cloudflare API token for Workers AI inference only.
2. Configure the Cloudflare account ID and token as host secrets.
3. Set the three LLM environment variables shown in section 3.1.
4. Run provider contract tests for normal and streamed responses.
5. Enforce a daily application budget below the provider's hard free limit so
   the service can return a controlled quota message.
6. Deploy the fixed application image to a staging Space.
7. Promote the exact image/corpus to the existing public Space.
8. Preserve the public backend URL for the first extension update, avoiding an
   unnecessary host-permission change.

#### 7.2 Oracle self-host runbook

1. Create an Always Free A1 instance with the full 2 OCPU/12 GB allocation and
   Ubuntu ARM64 in the account's home region.
2. Use an Always-Free-eligible boot volume with enough room for OS, model,
   container images and logs.
3. Install Ollama ARM64 or build llama.cpp; pull the exact quantized
   `gemma4:e2b` package.
4. Bind the model server to loopback only.
5. Put Caddy or Nginx in front with HTTPS, a long bearer token, request size
   limits, concurrency 1, timeouts and access logs without prompt bodies.
6. Open only SSH through a restricted source and HTTPS 443. Never expose Ollama
   port 11434 directly.
7. Set context to the measured RAG requirement, initially 8K, not the maximum
   128K; long KV caches cost memory.
8. Disable model unloading if memory permits; otherwise document cold-load time.
9. Benchmark Arabic/English quality, first-token latency, tokens/second, peak
   RSS, swap use, and two simultaneous requests.
10. Point the staging app to Oracle and run the full evaluation set before
    deciding whether independence is worth the slower experience.
11. Back up configuration and corpus, monitor free-tier limits, and plan for
    Oracle capacity/idle-reclamation risk.

#### 7.3 Single-server Oracle experiment

Only attempt this after the split topology works. Replace E5-large and the
BGE-M3 reranker with a measured light retrieval profile, package the index, use
one process, and cap concurrency. Pass a 24-hour memory soak without swap growth
or OOM before considering release.

Exit gate:

- Recommended deployment meets p50 first-token <= 3 s and p95 full-answer <=
  12 s under pilot load. If self-hosted CPU cannot meet an agreed relaxed SLO,
  keep it as a fallback/dev environment.

### Phase 8 — privacy, security and Chrome Web Store update

**Goal:** make disclosures match actual behavior.

Tasks:

1. Remove the portal name gate or make it explicitly optional and do not send
   the name to the server. The simpler release choice is removal.
2. Rewrite the privacy policy to name the actual model host, message/history
   transfer, local storage, server logs, retention, deletion path and navigation
   behavior.
3. Add the Chrome Limited Use statement and describe why any browsing context
   is needed. If no current-path context is sent, say so clearly.
4. State that navigation opens reviewed Ritaj pages and does not read or submit
   their content.
5. Update the store single-purpose description, permission justifications,
   screenshots and bilingual listing for the side panel.
6. Do not make unsupported claims such as "privacy complete", "nothing is
   collected", "official", or guaranteed automatic verification.
7. Replace personal maintainer email exposure with a project support address if
   available.
8. Add terms/disclaimer: information may change; the linked Ritaj page is
   authoritative; no personalized academic/financial decision is provided.
9. Perform threat modeling for prompt injection, malicious corpus content,
   URL injection, quota abuse, log leakage, admin takeover, supply-chain risk
   and extension update compromise.
10. Generate a software bill of materials, run dependency and container scans,
    and pin deployable versions/hashes.

Chrome policy requires minimal permissions, accurate user-data disclosure and
limited use of browsing activity. See the official
[Chrome Web Store program policies](https://developer.chrome.com/docs/webstore/program-policies/policies).

Exit gate:

- A reviewer can trace every behavior involving messages, storage, providers
  and navigation to a matching privacy-policy and store disclosure.

### Phase 9 — test and release engineering

#### 9.1 Automated tests

Backend unit tests:

- source-manifest hostname/hash/approval validation;
- effective-date selection;
- navigation registry and URL parser;
- Arabic/English intent resolution;
- rate limit, body limit and error redaction;
- CORS and admin fail-closed behavior;
- streaming event order and disconnect cleanup;
- PII redaction and retention enforcement.

Integration tests:

- real packaged index with no network;
- mock Workers AI and mock Ollama providers;
- provider timeout, 429, 500 and malformed stream;
- source changes and corpus rollback;
- cold start and readiness transitions.

Extension E2E tests in Chromium:

- action click opens the side panel;
- Arabic and English streamed chats;
- history persists and clears;
- cancel/retry and offline states;
- confirmed navigation opens the exact approved Ritaj URL;
- malicious backend URL is rejected;
- keyboard and screen-reader semantics;
- no credentials/page DOM/network history are accessed.

Quality/security tests:

- bilingual golden set and human review;
- prompt injection in user and source text;
- URL homoglyphs, subdomain tricks, redirects and encoded schemes;
- long messages/history, concurrent abuse and quota exhaustion;
- dependency audit, secret scan, container scan and CSP review.

#### 9.2 CI/CD gates

Pull request:

1. Python lint/type checks and 133+ unit tests.
2. TypeScript build, lint and extension tests.
3. Manifest validation and prohibited-permission check.
4. Corpus policy and source-link checks.
5. Secret scan, dependency audit and container build.

Release candidate:

1. Build immutable app image, corpus artifact and extension zip.
2. Generate checksums/SBOM and sign or attest artifacts.
3. Deploy staging and run smoke, golden, red-team and navigation tests.
4. Run load/soak test within provider quota.
5. Human content-owner sign-off and bilingual UX review.
6. Promote the same artifacts; no rebuild between staging and production.

Rollback:

- retain at least the last two app images, corpus versions and extension zips;
- server rollback must not depend on a Chrome Store review;
- keep the previous API version until the newly published extension adoption is
  high enough;
- disable navigation actions server-side through a signed/controlled registry
  flag if an incorrect destination is discovered.

### Phase 10 — staged rollout

1. **Internal alpha:** maintainers only; verify uptime and source correctness.
2. **Closed university pilot:** 10–25 students in both languages; navigation
   confirmation always on; collect opt-in feedback.
3. **Limited store rollout:** monitor errors, quota, latency, refusals,
   navigation use and thumbs feedback for one week.
4. **General availability:** only after all release gates below pass.

Do not use raw conversation text as a product metric by default. Prefer counts,
latency, error codes, retrieval/source IDs, grounding verdicts and opt-in
feedback.

## 7. File-level implementation map

| Area | Planned change |
|---|---|
| `chrome-extension/manifest.json` | Side panel + service worker; remove default popup; keep minimal permissions; bump major/minor version. |
| `chrome-extension/popup.*` | Rename/refactor into responsive `sidepanel.*`; render sources/actions; cancel and clear controls. |
| `chrome-extension/service-worker.js` | New: open side panel on action click and execute validated navigation. |
| `chrome-extension/navigation.js` | New: independent exact-host/scheme/path validation. |
| `chrome-extension/store/*` | New screenshots, permission text, privacy and listing copy. |
| `src/ritaj/api.py` | `/v2` contract, `/live`, `/ready`, rate limits, safe errors, CORS allowlist and navigation SSE event. |
| `src/ritaj/navigation.py` | New deterministic resolver and action registry. |
| `src/ritaj/source_policy.py` | New manifest validation, hostname rules and freshness logic. |
| `src/ritaj/ingest.py` | Consume approved snapshots/manifest only; preserve URL/date/language metadata. |
| `src/ritaj/retrieve.py` | Metadata/date/language filtering, deduplication and calibrated abstention. |
| `src/ritaj/generate.py` | Independent identity, source freshness in prompt, action ID tool schema if later enabled. |
| `src/ritaj/config.py` | Provider, origin, rate-limit, readiness, retention and corpus-version settings. |
| `src/ritaj/chatlog.py` | Aggregate-by-default telemetry, PII redaction, retention/deletion. |
| `data/sources.yaml` | New authoritative Ritaj-only source manifest. |
| `data/navigation.yaml` | New reviewed action registry generated/validated from sources. |
| `data/raw/` | Replace in production with approved Ritaj snapshots; quarantine off-domain/sample material. |
| `data/links.yaml` | Generate from canonical approved source records or remove as a separate hand-maintained map. |
| `scripts/start.sh` | Bind web server immediately; background or prebuilt initialization. |
| `scripts/build_index.py` | Emit immutable, versioned artifact with manifest/checksum. |
| `scripts/deploy_space.py` | Require clean tagged commit, configure/check required variables, deploy staging first. |
| `Dockerfile` | Copy prebuilt corpus/index, offline runtime model loading, health check, pinned dependencies. |
| `.github/workflows/ci.yml` | Frontend/extension, corpus-policy, security and container gates. |
| `tests/` | Source, navigation, API abuse, extension E2E, provider contract and readiness tests. |

## 8. Definition of ready to release

The project is release-ready only when every item is true:

### Service

- Production `/live` and `/ready` are healthy.
- Three consecutive cold starts succeed inside the host timeout.
- No unresolved critical/high dependency or container vulnerability.
- Provider quota, latency, error rate and concurrency are monitored.
- Rollback was rehearsed successfully.

### Data and answers

- Every indexed chunk has an approved `ritaj.birzeit.edu` canonical URL.
- No `www.birzeit.edu`, other domain, private student content, or `SAMPLE`
  material is present in the production artifact.
- Source freshness/effective-date metadata is visible and tested.
- Golden, refusal, grounding and navigation thresholds pass.
- Arabic and English content owners approve the pilot corpus.

### Extension

- Clicking the icon opens only the side-panel chat.
- Chat remains available while navigating.
- Every navigation action is allowlisted, confirmed and independently
  revalidated in the extension.
- No form submission or private-page reading occurs.
- Permissions are minimal and match the store disclosure.
- Extension zip is generated from the release tag and its checksum recorded.

### Privacy and operations

- Privacy policy matches the actual provider, logs, retention and navigation.
- The product is labeled independent unless official approval exists.
- Admin access is fail-closed and secrets are server-side only.
- Support, incident response, content correction and data-deletion procedures
  have named owners.

## 9. External inputs required before completion

These are genuine authorization/dependency boundaries, not coding tasks:

1. A Cloudflare account ID and scoped Workers AI token, or an Oracle account and
   approved region/instance choice.
2. A Hugging Face write token and access to current Space logs/settings to repair
   and redeploy the public service.
3. Birzeit authorization or an approved export for the Ritaj-only corpus. The
   site's Cloudflare challenge must not be bypassed.
4. The Chrome Web Store developer account and final extension ID. The ID is used
   in the production CORS allowlist.
5. Human approval for the bilingual content, privacy wording, navigation
   registry and independent/official branding.

Without item 3, a release can cover only the small public Ritaj content that can
be directly verified and approved. Without deployment/store credentials, the
software can be built and packaged but not published on the user's behalf.

## 10. Recommended execution order from now

1. Preserve and review the dirty working tree.
2. Repair startup and restore a healthy staging/public backend.
3. Select Workers AI for the pilot and run the Gemma 4 provider contract test.
4. Obtain the Ritaj content/export authorization.
5. Build the source manifest and Ritaj-only corpus; remove noncompliant data from
   the production artifact.
6. Add deterministic navigation registry/API actions.
7. Convert the extension to the side panel and implement independent URL checks.
8. Harden public API, telemetry, privacy and rate limits.
9. Complete automated, golden, red-team, accessibility, load and soak tests.
10. Run internal and closed pilots, then submit the release-tagged extension.

This order puts availability and source integrity ahead of interface polish.
There is little value in publishing a polished extension that points to a 503
backend or answers from sources that violate the product's own data rule.
