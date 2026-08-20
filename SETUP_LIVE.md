# Going live, at $0

> **DONE — 20 August 2026.** All four human steps were completed and the
> deployment is live. Kept as the record of how it was configured, not as
> outstanding work. The current forward plan is **[FUTURE_PLAN.md](FUTURE_PLAN.md)**.

Everything in this file is free and needs no credit card. It is written to be
followed top to bottom in one sitting; the parts only you can do are marked
**YOU**, and there are four of them.

Facts were re-verified on **20 August 2026** against provider documentation.
Free tiers change — recheck anything that looks off before blaming the code.

---

## 0. What state the project is in

Done, committed, and verified on this branch:

| | |
|---|---|
| Backend tests | 399 passing |
| Extension E2E | 20/20 in real Chromium |
| Extension unit tests | 21 passing |
| Policy gates | corpus, navigation, extension, privacy — all pass |
| Navigation eval | 22 cases, 100% destination precision, 100% intent recall |

The panel is redesigned in Ritaj green/gold, the page finder works with the
backend switched off, and `deploy_space.py` pushes the whole configuration in
one command.

**Two things are not code problems and this file cannot fix them:**

1. **There is no approved corpus.** All 22 previous documents failed the
   Ritaj-only source policy and sit in `data/quarantine/`. Every record in
   `data/sources.yaml` is `approved: false`. Until an authorized acquisition
   path exists, the service starts, reports `not-ready`, and abstains on factual
   questions. That is the design working, not a bug. Read
   `data/quarantine/README.md` before touching it.
2. **No destination is approved**, so the page finder shows its empty state.
   Step 1 below fixes that in about two minutes.

So the honest live state you are about to reach is: **a working navigation
assistant with factual chat disabled.** `PRODUCTION_FREE_LIVE_PLAN.md` §16 says
the same thing, and calls it "still a useful student product and safer than
publishing a chat that guesses."

---

## 1. **YOU** — Confirm the five Ritaj URLs (~2 minutes)

Nothing else in this file needs a browser. This does, because `ritaj.birzeit.edu`
returns **403** to every automated request (Cloudflare managed challenge), and
bypassing that is off limits.

Open each URL in a **normal, signed-out** window and note what happens:

| # | URL | What to record |
|---|---|---|
| 1 | https://ritaj.birzeit.edu/ | loads / 404 / login wall |
| 2 | https://ritaj.birzeit.edu/reg/ | loads / 404 / login wall |
| 3 | https://ritaj.birzeit.edu/academic-calendar | loads / 404 / login wall |
| 4 | https://ritaj.birzeit.edu/hemis/courses | loads / 404 / login wall |
| 5 | https://ritaj.birzeit.edu/bzu-msgs/boards | loads / 404 / login wall |

Record the verdicts in `cowork_ritaj/url-confirmation.md`. A page that 404s must
not be enabled. A page behind a login **can** be enabled — the button just needs
`auth_required: true`, which the panel already shows as "sign-in needed" before
the click.

Then, for each URL that exists, set both fields together in
`data/navigation.yaml` and regenerate the extension's bundled copy:

```bash
# enabled: true  AND  approved_by: "<your name>"   — both, or the row is dropped
python scripts/sync_extension_actions.py
python scripts/check_navigation.py     # expect: 0 awaiting approval
node --test chrome-extension/navigation.test.mjs chrome-extension/links.test.mjs
```

Setting `enabled` without an approver is the failure mode `navigation.problems()`
exists to catch: the row looks approved in the file and silently does nothing.

---

## 2. **YOU** — Cloudflare Workers AI account (~5 minutes)

Free, no card. This is where the model runs. **Nothing is uploaded by you** —
Gemma 4 is already hosted on Cloudflare's side; your deployment carries three
values pointing at it.

1. Sign up at <https://dash.cloudflare.com/sign-up>.
2. Copy your **Account ID** from the dashboard URL:
   `dash.cloudflare.com/<ACCOUNT_ID>`.
3. Create a **scoped** API token at
   <https://dash.cloudflare.com/profile/api-tokens> → *Create Token* →
   *Create Custom Token*:
   - Permission: **Account → Workers AI → Read**
   - Account resources: your account only
   - **Do not use a Global API Key.** It authenticates everything you own; this
     token only needs to run inference.

Free allowance: **10,000 neurons/day**, resetting at 00:00 UTC. At about 50
neurons per answer (~4,000 input / 500 output tokens) that is roughly **200
answers per day** — a closed pilot, not a student body. `LLM_DAILY_NEURON_BUDGET`
below keeps a margin under the ceiling.

---

## 3. **YOU** — Hugging Face token (~2 minutes)

The app already has a Space: `MohAwwad04/ritaj-rag`, public, Docker,
`cpu-basic` ($0/hr). It is currently in `RUNTIME_ERROR` with
*"Launch timed out, workload was not healthy after 30 min"* — the outage the
Phase 1 commit already fixed by binding the port before initializing.

Create a **Write** token at <https://huggingface.co/settings/tokens>.

> **Worth knowing:** Hugging Face now states that *creating* a Docker or Gradio
> Space requires a paid plan. Yours predates that rule and still requests free
> `cpu-basic` hardware. **Repairing the existing Space is the free path;
> creating a new one is not.** Do not delete it.
>
> If the account turns out to be ineligible to restart it, the fallback in
> `PRODUCTION_FREE_LIVE_PLAN.md` §6 is Oracle Always Free A1. Tell me and I will
> wire that instead.

---

## 4. Generate admin credentials (interactive, on your machine)

Passwords must never be generated by an agent, pasted into a chat, or passed as
a command-line argument. `set_admins.py` prompts, so the password never enters
`argv` or your shell history.

```bash
python scripts/set_admins.py --count 1     # prints username:bcrypt_hash pairs
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SESSION_SECRET
```

Store both in a password manager. Then delete `ritaj_rag_admins.rtf` from every
machine that has it — it holds weak, username-derived plaintext passwords and
those accounts should be treated as already disclosed.

---

## 5. Deploy

Put the values in your shell — **not in a file in the repo**. `deploy_space.py`
reads them from the environment and pushes them to the Space as secrets and
variables, so no credential is ever staged with the upload.

```bash
cd ~/Desktop/ritaj-rag-chatbot
source .venv/bin/activate

# --- credentials (secrets on the Space; never printed, never committed) ---
export HF_TOKEN='hf_...'
export LLM_API_KEY='<cloudflare scoped token>'
export ADMIN_USERS='<username>:<bcrypt hash from step 4>'
export SESSION_SECRET='<the token from step 4>'

# --- deployment settings (variables on the Space; public, and fine to be) ---
export LLM_BASE_URL='https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1'
export LLM_MODEL='@cf/google/gemma-4-26b-a4b-it'
export LLM_DAILY_NEURON_BUDGET=9000
export MAX_CONCURRENT_GENERATIONS=2
export ENVIRONMENT=production
export STARTUP_INIT=1
export ALLOW_INDEX_BUILD_ON_BOOT=0
export CHAT_LOG_MODE=aggregate
export CHAT_LOG_RETENTION_DAYS=30
export QDRANT_MODE=embedded
export QDRANT_PATH=/tmp/qdrant
export CORS_ORIGINS='https://mohawwad04-ritaj-rag.hf.space'
export TRUSTED_PROXY_COUNT=1

# --- build the portal, then deploy ---
cd ritaj-student-portal && npm ci && npm run build && cd ..
python scripts/deploy_space.py "first live deploy"
```

The deploy refuses immediately — before uploading anything — if a fail-closed
setting is missing, and lists which. That is deliberate: the container validates
the same values at boot, but by then it has spent twenty minutes building.

Watch the build at <https://huggingface.co/spaces/MohAwwad04/ritaj-rag>.

### Verify it is actually live

```bash
SPACE=https://mohawwad04-ritaj-rag.hf.space
curl -s $SPACE/live                      # {"status":"live",...}  — fast, no dependencies
curl -s $SPACE/ready | python3 -m json.tool
curl -s $SPACE/capabilities | python3 -m json.tool   # look at "modes"
curl -s -o /dev/null -w '%{http_code}\n' $SPACE/privacy   # 200, needed for the Store
curl -s -X POST $SPACE/v2/navigation/resolve \
  -H 'Content-Type: application/json' \
  -d '{"message":"open the academic calendar"}'
```

Expect `modes.navigation_ready: true` once step 1 is done, and
`modes.retrieval_ready: false` until a corpus exists. **`ready: false` is the
correct answer right now** — the service is telling you the truth.

---

## 6. Point the extension at the live backend and load it

`chrome-extension/config.js` already points at
`https://mohawwad04-ritaj-rag.hf.space`, matching `manifest.json`
`host_permissions`. If the URL ever changes, change **both** and bump the
version.

To see it in your own Chrome right now:

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select `~/Desktop/ritaj-rag-chatbot/chrome-extension`
3. Click the toolbar icon — the side panel opens.

That last click is the one thing no test covers: Playwright cannot drive
Chrome's side panel (microsoft/playwright#26693), so `scripts/e2e_extension.mjs`
verifies everything behind it and stops there.

To see the panel without installing anything:

```bash
node scripts/screenshot_panel.mjs      # writes release/screenshots/
```

---

## 7. What is still not done, honestly

| Item | Why it is blocked | Who unblocks it |
|---|---|---|
| Factual chat | No approved corpus. `eval_release.py --gate` exits 1 on `answerable 0/100` — the gate working | An authorized Ritaj export or written approval to snapshot |
| Chrome Web Store update | Screenshots still show the removed popup; the listing claims fees/grades the product cannot do | You, after step 1 and a live backend |
| Qdrant Cloud | Code is ready (`QDRANT_MODE=remote`, versioned collections, atomic alias switch) and tested against local-mode Qdrant. Not needed until a corpus exists | Nobody yet — embedded is correct for one container |
| Upstash Redis | Rate limits and the daily budget reset on restart. Acceptable for one process/one replica; document it, or provision Upstash | You, before the pilot widens |
| Operator ownership | `scripts/check_operations.py` exits 1 — nine duties have no primary or backup | You, naming people |
| Branch protection | `release` is unprotected (404 on the protection endpoint) | Repository admin — command in `cowork_ritaj/human-actions.md` §H1 |

**Not verified by anyone yet:** that Qdrant Cloud behaves like local-mode Qdrant
under TLS and auth; that the Space rebuilds successfully on the current free
allowance; that Cloudflare's real latency meets the p50 ≤ 3s first-token target.
Each needs the live thing to exist first.
