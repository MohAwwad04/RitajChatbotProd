# Where this project stands — 21 August 2026

A living status document. [`README.md`](README.md) says what this is;
[`HANDBOOK.md`](HANDBOOK.md) says how it works. **This file says what is broken
right now, what was ruled out, and which decision is waiting.**

Every claim carries the command or log line it came from.

---

## The one-paragraph version

Everything is deployed and working **except the model call**. The backend is
live, the vector database holds 92 chunks and is readable, the extension talks
to the deployment, navigation works, the admin console works. Asking a question
fails, because **the Hugging Face container cannot open a TLS connection to
Cloudflare's API**. That is a network-path problem between two third parties,
not a defect in this code, and it is not fixable from inside the application.
A decision about where the model runs is required before anything else matters.

---

## 1. What is live and working

```
https://mohawwad04-ritaj-rag.hf.space
```

| Surface | State | Evidence |
|---|---|---|
| `/live` | `{"status":"live","state":"ready"}` | port bound in 1.2 s |
| `/capabilities` `modes` | `live`, `navigation_ready`, `retrieval_ready`, `generation_ready`, `ready` — **all true** | live probe |
| Vector database | Qdrant Cloud, AWS `us-east-1`, **92 chunks readable** | `retrieval_ready: true` |
| Navigation | 4 reviewed destinations, AR + EN | `/v2/navigation/resolve` returns them |
| Portal | React SPA at `/` | HTTP 200 |
| `/privacy` | public URL for the Store listing | HTTP 200 |
| Admin console | login works as `ritaj-admin` | session token issued |
| Extension → live backend | **6/6 checks** | `node scripts/e2e_live.mjs` |

Test suite: **406 backend**, **29 extension**, **20/20** Chromium E2E, **13/13**
against the real Qdrant cluster, five policy gates green.

---

## 2. The blocker

### Symptom

```
$ curl -X POST .../v2/chat -d '{"message":"test"}'
HTTP 503 in 53.5s
{"code":"LLM_UNAVAILABLE"}
```

### Cause, from the container's own log

```
LLM call failed (attempt 1/2): ConnectTimeout('_ssl.c:999: The handshake operation timed out')
LLM call failed (attempt 2/2): ConnectTimeout('_ssl.c:999: The handshake operation timed out')
POST /v2/chat -> LLM_TIMEOUT: ConnectTimeout(...)
```

The container cannot complete a **TLS handshake** to `api.cloudflare.com`. Both
attempts fail identically.

### The decisive measurement

```
/admin/usage  ->  neurons_used: 0.0 / 9000
                  provider_calls: 0
```

**Zero provider calls, ever.** That counter has been live through every attempt
since the first deploy. The Space has never once completed a request to
Cloudflare — this is not intermittent, not a quota problem, and not slowness.

---

## 3. What was ruled out, and how

Listed because each of these was a plausible explanation that turned out to be
wrong, and re-testing them costs time.

| Hypothesis | Ruled out by |
|---|---|
| The model is slow | Raising connect 5 s → 20 s changed nothing. The failure is at *handshake*, before any generation. |
| The API key is wrong | The same key answers from a laptop: `/user/tokens/verify` returns active, and a real completion returns 1.85 neurons of usage. |
| The account or model id is wrong | A full RAG answer was generated locally through the same code path — 846 chars EN, 743 chars AR, 6 sources each. |
| The corpus or retrieval is broken | `retrieval_ready: true`, 92 chunks readable through the alias. |
| Outbound network is blocked wholesale | The **same container reaches Qdrant Cloud on port 6333**. That is how retrieval works at all. |
| CORS | The HF proxy is permissive and echoes every origin — see HANDBOOK §8. The extension reaches the backend fine, 6/6. |
| Our timeout configuration | Now a setting (`LLM_CONNECT_TIMEOUT_SECONDS`, default 20 s) rather than a hard-coded 5 s. Correct fix, wrong cause. |

**Conclusion:** `api.cloudflare.com` specifically refuses to complete a TLS
handshake from Hugging Face Spaces' egress addresses. Neither side of that is
under this project's control.

---

## 4. The three ways out

### Option A — Hugging Face Inference Providers

Verified working with the existing token, from this machine:

```
router.huggingface.co/v1     132 models visible
google/gemma-4-26B-A4B-it    the SAME model Cloudflare serves
a real completion            works, and returns NO reasoning_content
                             (0 chars, vs ~70% of output on Cloudflare)
```

OpenAI-compatible, so **zero code changes** — three config values. It is also
HF → HF, so reachability is near-certain.

**The catch is capacity.** Free HF accounts receive **$0.10 per month** of
Inference credit.

| | Free capacity |
|---|---|
| Cloudflare | 10,000 neurons/**day** → ~6,000–15,000 answers/month |
| HF free | $0.10/**month** → **~200 answers/month** |
| HF PRO, $9/mo | $2.00/month → ~4,000 answers/month |

At ~$0.00049 per RAG answer (4,000 in / 300 out at the provider's published
rate), free HF is about **seven answers a day**. A demo budget, not a pilot.

### Option B — Move the app to Oracle Always Free

Keeps Cloudflare's capacity, still $0. **Investigated on 21 Aug and it is a
bigger job than it appears.**

| Question | Finding |
|---|---|
| Base image on ARM64? | ✅ multi-arch; `linux/arm64/v8` is in the pinned digest |
| Does an ARM torch wheel exist? | ✅ plain `torch==2.13.0` on the PyTorch CPU index |
| **Does the current lock install on ARM?** | ❌ **no** |
| **Can it be fixed with the current tooling?** | ❌ **not cleanly** |

The obstruction is specific. On x86 the CPU index serves `torch==2.13.0+cpu`; on
ARM the same index serves `torch==2.13.0` — **different versions from one
source**. `uv`'s universal resolver picks one version per source. Three marker
configurations were tried:

```
sys_platform == 'linux'                    -> resolves +cpu for ARM. Does not exist.
linux and x86_64                           -> ARM falls to PyPI and pulls ~2 GB of
                                              nvidia CUDA libraries, which DO publish
                                              aarch64 builds. On a CPU-only box.
both arches -> pytorch-cpu index            -> resolves +cpu for both again.
```

`uv export` has no `--python-platform`, so the usual escape hatch — one lock file
per architecture — is not directly available either.

Reaching Oracle therefore requires **one** of:

- two independently generated lock files with a Dockerfile that selects on
  `TARGETARCH` — giving up the single-lock reproducibility guarantee;
- accepting ~2 GB of CUDA libraries on a machine with no GPU;
- dropping `--require-hashes` on ARM, i.e. the tamper-evidence property.

On top of two gates outside anyone's control: **Oracle Always Free A1 capacity is
frequently unavailable** (`Out of host capacity` is the most-reported problem
with that tier), and **Oracle requires a credit card** for identity verification.

### Option C — Investigate the Cloudflare block

Cannot be done from outside either network. May not be fixable at all: if
Cloudflare's edge is refusing datacenter ranges, no configuration on this side
changes it.

---

## 5. The recommendation, and why

**Run Option A as a test before committing to Option B.**

Not as a destination — as *information*. It costs one deploy and answers the
question that decides everything else:

- **If HF works from the Space**, the block is Cloudflare-specific. The cheapest
  real fix becomes **HF PRO at $9/month** — 4,000 answers/month, no migration, no
  ARM dependency surgery, no CUDA, no capacity lottery. And there is a live,
  answering chatbot the same afternoon.
- **If HF also fails**, HF egress is broken generally, Option B is genuinely
  necessary, and the ARM work is done knowing it is required rather than hoped.

Either result makes the Oracle decision better-informed. Doing Option B first
risks a weekend of dependency work for a free tier that may not provision.

**Awaiting a decision on this.**

---

## 6. Everything else outstanding

Unchanged by the above; see [`HANDBOOK.md`](HANDBOOK.md) §10 for the ordered list.

- **The corpus is unverified.** Currently serving the quarantined material by
  explicit operator decision, recorded in the manifest. Both clients show a
  persistent banner in Arabic and English. One real Ritaj page removes it —
  `https://ritaj.birzeit.edu/academic-calendar` through HANDBOOK §5.
- **Three credentials need rotating** — Cloudflare, Hugging Face and Qdrant, all
  pasted into a chat transcript. The Qdrant key decodes to `"access":"m"`, full
  manage rights.
- **Store screenshots are dated 6 July** and predate the redesign entirely.
- **13 unassigned duties and undrilled rollbacks** — `check_operations.py` exits 1.
- **`release` branch is unprotected.**
- **No accuracy number exists** for this product: `answerable 0/100`,
  `calendar 0/25`.

---

## 7. Not verified by anyone

- Whether Hugging Face Spaces can reach *any* external HTTPS host on 443, or
  whether Cloudflare is a special case. **Option A's deploy answers this.**
- Three consecutive cold starts.
- Latency as a distribution. Two samples — 9.7 s and 12.2 s for a complete
  answer against a p95 ≤ 12 s target — cannot establish a p95.
- `scan_pii` against real Ritaj markup.
- Whether Oracle A1 capacity is available in the relevant region.
- Whether a re-locked ARM dependency set actually builds and runs.

---

## 8. What changed on 20–21 August

For anyone returning to this after a gap.

- Deployed from scratch: the Space had been dead since 6 July with
  `Launch timed out, workload was not healthy after 30 min`.
- Connected Qdrant Cloud and verified the publish/alias/rollback path 13/13
  against the real cluster.
- Approved four navigation destinations; `/hemis/courses` was confirmed not to
  load and stays disabled.
- Published the unverified corpus with a banner, by explicit decision.
- Fixed, among others: a traversal check that never fired, Arabic punctuation
  breaking intent matching, `tabs.query` needing a permission the extension does
  not request, a deploy that had never staged `requirements.lock.txt`, a
  vacuously-passing corpus gate, `/admin/points` returning 500 on every fresh
  deployment, and a readiness check that was blind to the Qdrant alias.
- Consolidated sixteen planning documents into `README.md` + `HANDBOOK.md`.
