# Self-Hosted LLM Plan — run your own Gemma, no APIs, no call limits

> Goal (your words): keep the RAG chatbot **live**, but replace the hosted Groq
> API with **your own Gemma** (`gemma4:e2b`, the one already working locally),
> hosted on a **free** server, **independent**, with **no call/rate limits**.
>
> This document is the full plan: which free host to use and why, the exact way
> the app talks to the model, every step to stand the model server up, and the
> minimal code/config changes. Written to sit next to `DEPLOYMENT.md` (which
> covers the current Groq setup).
>
> **Status:** proposal / runbook. Nothing here is applied yet.

---

## 0. The one honest constraint you must accept

There is **no free host that gives you a GPU with no usage limit.** Every "free
GPU" (HF ZeroGPU, Colab, Kaggle) is metered by minutes/day or times out — that
*is* a call limit, just wearing a different hat (verified July 2026: HF ZeroGPU
free = **3.5 min GPU/day**; Colab/Kaggle = session timeouts). So "free + no
limits + your own model" forces exactly one thing:

> **Run Gemma on a free CPU server.** No GPU. Unlimited requests, but each
> answer is **slow** (~5–15 tokens/sec → a typical answer takes ~5–30 s instead
> of Groq's <1 s).

This is the same wall `DEPLOYMENT.md` hit ("No free host can self-run the 7.2 GB
model; no GPUs on free tiers") — the difference now is we *accept slow CPU* in
exchange for independence, and we pick a host with enough **RAM** (≥12 GB) to
actually hold the model, which the old Railway trial (1 GB) could not.

Your `gemma4:e2b` is 7.2 GB on disk → needs ~8–10 GB RAM live. That rules out
tiny free tiers and points at exactly one class of host: a **free always-on VM
with ≥12 GB RAM**, or the **existing 16 GB Hugging Face CPU Space**.

If a fast, snappy chatbot matters more than "no API", the honest answer is to
stay on Groq (or Google's Gemini API, which serves *real* Gemma and is also
OpenAI-compatible and free-tier). This plan assumes independence wins.

---

## 1. How the app talks to the LLM today (the seam we reuse)

The whole reason this is mostly a *config* job and not a *rewrite*: the app was
built around **one OpenAI-compatible seam**. All generation goes through
`src/ritaj/llm.py`, which POSTs to `{LLM_BASE_URL}/chat/completions`:

```python
# src/ritaj/llm.py  (today)
resp = httpx.post(
    f"{settings.llm_base_url}/chat/completions",
    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
    json=_payload(messages, temperature, max_tokens, stream=False),
    timeout=120,
)
```

`Ollama`, `vLLM`, `Groq`, and `Gemini` **all speak this identical protocol.**
Switching provider = changing three environment variables:

| Env var | Today (Groq) | After (your Gemma via Ollama) |
|---|---|---|
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | `https://<your-llm-host>/v1` |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | `gemma4:e2b` |
| `LLM_API_KEY` | *(Groq key, secret)* | *(a token **you** invent, secret)* |

**Ollama exposes exactly this endpoint** at `http://<host>:11434/v1/chat/completions`
— OpenAI-compatible, including SSE streaming (`chat_stream` in `llm.py` already
parses `data: {json}` / `[DONE]`). That is the entire "communication type": the
live HF Space keeps doing all retrieval/rerank/grounding locally and makes **one
outbound HTTPS call** to your Gemma box for the text-generation step, precisely
where it calls Groq today.

**Nothing about the Chrome extension or the student portal changes** — they talk
to the HF Space (`https://mohawwad04-ritaj-rag.hf.space`), not to the LLM. The
swap is invisible to every client.

---

## 2. Which free host — comparison & recommendation

| Option | RAM / CPU | Always-on? | Truly no limits? | Cost | Verdict |
|---|---|---|---|---|---|
| **Oracle Cloud "Always Free" A1 (ARM)** | 12 GB / 2 OCPU (was 24/4 before Oracle's July-2026 cut; existing boxes keep 24/4) | ✅ yes | ✅ yes | $0 forever | **✅ RECOMMENDED — dedicated, persistent, unlimited** |
| **HF CPU Space (Ollama in the same container)** | shares 16 GB / 2 vCPU with embedder+reranker | ⚠️ sleeps after 48 h idle | ✅ yes | $0 | ✅ Good fallback — zero new accounts, one host |
| **HF CPU Space (2nd Space, LLM only)** | 16 GB / 2 vCPU | ⚠️ sleeps 48 h idle | ✅ yes | $0 | ✅ OK — clean split, but 2 sleepy Spaces |
| HF ZeroGPU (free) | H200 GPU | on-demand | ❌ **3.5 min GPU/day** | $0 | ❌ hard daily limit — fails your requirement |
| Google Colab / Kaggle | T4/P100 GPU | ❌ 9–12 h max, idle-kills | ❌ session caps | $0 | ❌ not a server; dies constantly |
| Fly.io / Render / Koyeb free | 256–512 MB | spins down | — | $0 | ❌ far too little RAM for 7.2 GB |
| Railway (the old attempt) | 1 GB trial | — | — | trial | ❌ already proven impossible (see `DEPLOYMENT.md`) |

### Recommendation

**Primary: Oracle Cloud "Always Free" ARM VM (Ampere A1).** It is the only
genuinely *free, persistent, dedicated, unlimited* box big enough for Gemma. A
2 OCPU / 12 GB A1 runs a quantized 2–4B model at ~5–8 tok/s — usable. Caveats:
requires a credit card for identity check (not charged on Always-Free shapes),
A1 capacity in popular regions can be hard to grab (retry / pick a quieter home
region), and Oracle *can* reclaim idle Always-Free VMs — keep it busy (a cron
ping) and take snapshots.

**Fallback (fastest to ship, no new account): run Ollama inside the existing HF
Space container** — you already own it and it has 16 GB. Downside: it sleeps
after 48 h idle and the CPU is shared with the embedder/reranker. Covered in
[§7](#7-alternative-run-gemma-inside-the-existing-hf-space-no-new-host).

The rest of this doc details the **Oracle path** as the main build, then the HF
in-container path as the alternative. Both end at the same place: an
OpenAI-compatible Gemma endpoint the live Space points at.

---

## 3. Target architecture

```
  student browser / Chrome extension
        │ https
        ▼
  HF Space — one Docker container (16 GB)            [UNCHANGED HOST]
    uvicorn :7860 (ritaj.api:app)
      ├─ React portal, /admin, /health
      ├─ embed + BM25 + RRF + rerank  (all local)
      ├─ embedded Qdrant (/tmp/qdrant)
      └─ grounded prompt ──────────────┐
                                        │ ONE outbound https call
                                        │ POST {LLM_BASE_URL}/chat/completions
                                        │ Authorization: Bearer <your token>
                                        ▼
  Oracle Always-Free VM (ARM, 12 GB)                 [NEW — your LLM host]
    Caddy :443  (HTTPS + bearer-token gate)  ──►  Ollama :11434
                                                     └─ gemma4:e2b  (your model)
```

The only new box is the Oracle VM. Retrieval "brain", data, guardrails, and all
clients stay exactly where they are. This also means **your knowledge base never
leaves the HF Space** — only the final prompt+sources go to your own Gemma box,
which you control end-to-end (that's the "independent" you wanted).

---

## 4. The communication contract (what flows on the wire)

This is the "communication type and way to communicate with the LLM" spec.

- **Transport:** HTTPS, request/response JSON; streaming is Server-Sent Events.
- **Protocol:** OpenAI Chat Completions (`POST /v1/chat/completions`).
- **Auth:** `Authorization: Bearer <LLM_API_KEY>` — a token *you* choose; Ollama
  ignores it, so **Caddy in front enforces it** (§6.4). Without this, a public
  Ollama port is an open LLM anyone can abuse.

**Non-streaming request** (what `llm.chat()` sends — used for `condense()` and
non-stream answers):

```http
POST https://<your-llm-host>/v1/chat/completions
Authorization: Bearer <your token>
Content-Type: application/json

{
  "model": "gemma4:e2b",
  "messages": [
    {"role": "system",    "content": "You are the Ritaj Assistant …"},
    {"role": "user",      "content": "Sources:\n[1] …\n\nQuestion: …"}
  ],
  "temperature": 0.2,
  "max_tokens": 1024,
  "stream": false
}
```

**Response** (the app reads `choices[0].message.content`):

```json
{ "choices": [ { "message": { "role": "assistant", "content": "…answer…" } } ] }
```

**Streaming** (`llm.chat_stream()`, `stream: true`): identical URL, response is
`text/event-stream` — lines of `data: {json}` each carrying
`choices[0].delta.content`, terminated by `data: [DONE]`. `llm.py` already parses
this. **Ollama emits this exact format**, so streaming into the portal and the
extension keeps working unchanged.

No code understands "Ollama" specifically — it only knows this contract. That's
why the provider swap is config, not rewrite.

---

## 5. Part A — provision the Oracle Always-Free VM

1. Create an Oracle Cloud account → **Menu ▸ Compute ▸ Instances ▸ Create**.
2. **Image & shape:** Canonical **Ubuntu 22.04**; shape **Ampere / VM.Standard.A1.Flex**;
   set **2 OCPU / 12 GB** (or 4 / 24 if offered — all "Always Free" eligible).
   If you get *"out of capacity"*, retry, or pick a different Availability
   Domain / a quieter home region.
3. **Networking:** add your SSH public key; note the **public IP**.
4. **Open the port:** VCN ▸ the subnet's **Security List** ▸ add an **Ingress
   rule**: source `0.0.0.0/0`, TCP, dest port **443** (for Caddy HTTPS). Do
   **not** open 11434 publicly — Ollama stays bound to localhost.
5. SSH in: `ssh ubuntu@<public-ip>`.
6. Also open the OS firewall for 443 (Oracle Ubuntu images ship iptables closed):
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### 5.1 Install Ollama and pull *your* model

```bash
curl -fsSL https://ollama.com/install.sh | sh          # installs + starts a systemd service
ollama --version                                        # sanity check

ollama pull gemma4:e2b                                   # ~7.2 GB, one-time download
ollama run gemma4:e2b "Say hello in one word."           # smoke test the model
```

`gemma4:e2b` is the same tag you run locally, so behaviour matches your machine.

### 5.2 Configure Ollama for RAG + always-warm (important)

Two server-side settings prevent the two classic self-host bugs — a truncated
context (RAG stuffs ~6 sources in) and slow "reload the model every request":

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
# Bigger context so retrieved sources + history aren't cut off (default is 4096).
Environment="OLLAMA_CONTEXT_LENGTH=8192"
# Keep the model resident in RAM so there's no per-request cold-load (-1 = forever).
Environment="OLLAMA_KEEP_ALIVE=-1"
# Serve loopback only; Caddy (next) is the public, authenticated front door.
Environment="OLLAMA_HOST=127.0.0.1:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

> Setting context server-side keeps `llm.py` model-agnostic — no Ollama-specific
> fields in the request payload.

---

## 6. Part B — put HTTPS + auth in front (Caddy)

The HF Space calls out over HTTPS to a name with a valid cert, and only requests
carrying your secret token get through to Ollama.

### 6.1 A free hostname (Caddy needs a domain for auto-HTTPS)

Use a free **DuckDNS** subdomain (or any domain you own). At duckdns.org, create
e.g. `ritaj-llm.duckdns.org` and point it at the VM's public IP.

### 6.2 Install Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

### 6.3 Pick and store your token

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # copy this — it becomes LLM_API_KEY
```

### 6.4 Caddyfile — HTTPS + bearer-token gate + proxy to Ollama

```caddy
# /etc/caddy/Caddyfile   — replace the host and the token
ritaj-llm.duckdns.org {
    @unauthorized not header Authorization "Bearer PASTE_YOUR_TOKEN_HERE"
    respond @unauthorized "Unauthorized" 401

    reverse_proxy 127.0.0.1:11434 {
        # long timeouts: CPU generation of a full answer can take minutes
        transport http {
            read_timeout  600s
            write_timeout 600s
        }
    }
}
```

```bash
sudo systemctl restart caddy      # obtains a Let's Encrypt cert automatically
```

**Verify from your Mac** (this is exactly what the Space will do):

```bash
HOST=https://ritaj-llm.duckdns.org
TOKEN=PASTE_YOUR_TOKEN_HERE
curl -s $HOST/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"gemma4:e2b","messages":[{"role":"user","content":"one word hi"}],"stream":false}' \
  | python3 -m json.tool
# expect choices[0].message.content ; and WITHOUT the header → 401
```

### 6.5 Keep the VM from being reclaimed / model warm

Oracle can reclaim idle Always-Free VMs. A tiny keep-alive cron both keeps the
box "used" and the model hot:

```bash
( crontab -l 2>/dev/null; echo '*/15 * * * * curl -s http://127.0.0.1:11434/api/tags >/dev/null' ) | crontab -
```

---

## 7. Part C — point the live HF Space at your Gemma

No redeploy needed — just change env vars on the Space and restart. Using the
same `huggingface_hub` ops as `DEPLOYMENT.md` (needs an HF **Write** token):

```python
from huggingface_hub import add_space_variable, add_space_secret, restart_space
rid = "MohAwwad04/ritaj-rag"; HF = "hf_xxx"          # your Write token

add_space_variable(rid, "LLM_BASE_URL", "https://ritaj-llm.duckdns.org/v1", token=HF)
add_space_variable(rid, "LLM_MODEL",    "gemma4:e2b",                        token=HF)
add_space_secret  (rid, "LLM_API_KEY",  "PASTE_YOUR_TOKEN_HERE",             token=HF)  # the token from §6.3
restart_space(rid, token=HF)
```

**Smoke-test the whole live pipeline end-to-end:**

```bash
B=https://mohawwad04-ritaj-rag.hf.space
curl -s "$B/health"
curl -s -X POST "$B/chat" -H "Content-Type: application/json" \
  -d '{"message":"How much is one credit hour?"}'      # now answered by YOUR Gemma
```

Expect a grounded, cited answer (citing `tuition_and_fees.md`), just slower than
Groq. If it 500s, check the Space run logs (`.../api/spaces/MohAwwad04/ritaj-rag/logs/run`)
and your VM's `journalctl -u caddy -u ollama`.

**Rollback is instant** — set `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` back to the
Groq values and `restart_space`. Keep the Groq values noted so you can flip back
if the VM misbehaves.

---

## 8. Code changes (minimal — one required, a few recommended)

The app already speaks the protocol, so this is nearly config-only. But two
things about CPU serving need real edits.

### 8.1 REQUIRED — raise the client timeout (`src/ritaj/llm.py`)

CPU generation of up to `max_tokens=1024` at ~6 tok/s can exceed **120 s** and
the current hard-coded `timeout=120` will raise mid-answer. Make it configurable
and default it higher.

**`src/ritaj/config.py`** — add one setting:

```python
    llm_model: str = os.getenv("LLM_MODEL", "gemma4:e2b")
    # Read timeout (seconds) for LLM calls. CPU self-hosting is slow, so default
    # generously; a fast hosted API never gets near it.
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "300"))
```

**`src/ritaj/llm.py`** — use it in both calls (replace `timeout=120`):

```python
# in chat():
        timeout=settings.llm_timeout,
# in chat_stream():
        timeout=settings.llm_timeout,
```

Then set `LLM_TIMEOUT=300` (or higher) as a Space variable.

### 8.2 RECOMMENDED — trim answer length for CPU (no code change)

Answer latency is ~linear in tokens generated. From `/admin ▸ Calibration` (or
env), drop **Max answer tokens** from 1024 to ~**512**, and keep temperature low
(0.2). Purely runtime — halves worst-case wait.

### 8.3 RECOMMENDED — skip the extra "condense" call on CPU

When a request carries history, `generate.condense()` makes a **second** LLM call
to rewrite the follow-up before retrieval — that *doubles* CPU latency on
multi-turn chats. Gate it behind a flag so you can turn it off on the slow host.

**`src/ritaj/config.py`:**
```python
    condense_followups: bool = os.getenv("CONDENSE_FOLLOWUPS", "true").lower() != "false"
```

**`src/ritaj/generate.py`** — early-return in `condense()`:
```python
def condense(question: str, history: list[dict]) -> str:
    from .config import settings
    if not history or not settings.condense_followups:
        return question
    ...
```
Set `CONDENSE_FOLLOWUPS=false` on the Space if multi-turn feels too slow. (You
lose some follow-up resolution quality; single-turn questions are unaffected.)

### 8.4 Update `.env.example` (dev parity)

The dev defaults already point at local Ollama (`gemma4:e4b`) — align the tag to
what you actually run and note the new knobs:

```dotenv
LLM_MODEL=gemma4:e2b          # the model you self-host
LLM_TIMEOUT=300               # CPU serving is slow; give it room
# CONDENSE_FOLLOWUPS=false    # optional: skip the extra rewrite call on slow hosts
```

> These are the **only** code touches. `llm.py`, `generate.py`, `config.py` — no
> new provider adapter, no client rewrite, because of the OpenAI seam.

---

## 9. Alternative — run Gemma *inside* the existing HF Space (no new host)

If you'd rather not manage a VM, host the model in the Space container you
already own. One host, one deploy, no Oracle account. Trade-offs: shares 16 GB
and the CPU with the embedder+reranker, and the Space **sleeps after 48 h idle**
(first request after sleep is very slow while the model reloads).

Sketch (edit `Dockerfile` + `scripts/start.sh`, then redeploy per `DEPLOYMENT.md`):

1. **Install Ollama in the image** — add to `Dockerfile`:
   ```dockerfile
   RUN curl -fsSL https://ollama.com/install.sh | sh
   ENV OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_KEEP_ALIVE=-1 OLLAMA_HOST=127.0.0.1:11434
   ```
2. **Start Ollama + pull the model on boot** — prepend to `scripts/start.sh`
   (before uvicorn), pulling to writable `/tmp` since `/app` is read-only:
   ```bash
   export OLLAMA_MODELS=/tmp/ollama
   ollama serve & 
   until curl -sf http://127.0.0.1:11434/api/tags >/dev/null; do sleep 1; done
   ollama pull gemma4:e2b || echo "WARNING: model pull failed"
   ```
   > First cold boot downloads 7.2 GB into ephemeral `/tmp` — slow, and repeats
   > on every rebuild. Better: **bake** it in the Dockerfile like the embedder is,
   > so it ships in the image layer.
3. **Point the app at the in-container model** — set Space vars:
   `LLM_BASE_URL=http://127.0.0.1:11434/v1`, `LLM_MODEL=gemma4:e2b`,
   `LLM_API_KEY=local` (loopback, so no Caddy/token needed).

This is the quickest way to "no APIs" but the sleepy shared CPU makes it best for
a demo; the Oracle VM is better for a persistent, always-warm service.

---

## 10. Verification checklist

- [ ] `ollama run gemma4:e2b "hi"` works on the VM.
- [ ] `curl … /v1/chat/completions` with the token returns `choices[…].content`;
      **without** the token returns **401** (auth actually enforced).
- [ ] Cert valid: `https://ritaj-llm.duckdns.org` loads without a TLS warning.
- [ ] `LLM_BASE_URL/MODEL/API_KEY/TIMEOUT` set on the Space; Space restarted.
- [ ] `POST $B/chat` returns a grounded, cited answer (verdict `grounded`).
- [ ] Streaming works in the portal and the extension (tokens appear live).
- [ ] Multi-turn follow-up ("and in Arabic?") still resolves (or `CONDENSE_FOLLOWUPS=false` if too slow).
- [ ] Keep-alive cron installed; a snapshot of the VM taken.

## 11. Performance, cost, risks

- **Cost:** $0. Oracle Always-Free A1 + DuckDNS + Caddy + Ollama are all free.
- **Speed:** expect **~5–8 tok/s** on 2 ARM OCPUs → short answers in a few
  seconds, long ones tens of seconds. Mitigate with `max_tokens≈512`,
  `CONDENSE_FOLLOWUPS=false`, and keeping the model warm (§5.2).
- **No call limits:** correct — it's your CPU; the only ceiling is throughput
  (requests queue rather than get rejected).
- **Risks:**
  - *Oracle reclaims idle Always-Free VMs* → keep-alive cron + snapshots (§6.5).
  - *Oracle A1 capacity* at signup → retry / change region.
  - *Space cold start* (48 h idle) unchanged from today — first request wakes it.
  - *Open LLM abuse* → the Caddy bearer gate is **not optional**; never expose
    11434 to `0.0.0.0`.
  - *Secrets:* the token is a Space **secret** + the Caddyfile only. Never commit
    it (same rule as the Groq key in `DEPLOYMENT.md`).

## 12. TL;DR

1. Free host = **Oracle Cloud Always-Free ARM VM** (≥12 GB) — only free box big
   enough, persistent, unlimited. (Fallback: Ollama inside the current HF Space.)
2. Install **Ollama**, `ollama pull gemma4:e2b`, set `OLLAMA_CONTEXT_LENGTH=8192`
   + `OLLAMA_KEEP_ALIVE=-1`.
3. Front it with **Caddy** (auto-HTTPS via a DuckDNS name) that checks a
   **Bearer token** and proxies to Ollama.
4. On the live Space, set `LLM_BASE_URL=https://…/v1`, `LLM_MODEL=gemma4:e2b`,
   `LLM_API_KEY=<token>`, `LLM_TIMEOUT=300`, and **restart**.
5. Code changes: only a **configurable timeout** in `llm.py`/`config.py` is
   required; a condense on/off flag and a smaller `max_tokens` are recommended
   for CPU. Extension and portal need **zero** changes.
6. Communication stays **OpenAI Chat Completions over HTTPS** (streaming = SSE) —
   the exact seam the app already uses. Rollback = flip the env back to Groq.

---

*Sources for the 2026 free-tier facts:*
[Oracle Free Tier for LLMs (2026)](https://blog.easecloud.io/ai-cloud/launch-oracle-cloud-llms-in/) ·
[Oracle halves Always-Free A1 (InfoQ, Jul 2026)](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/) ·
[Ollama + Open WebUI on OCI free ARM](https://medium.com/@viplav.fauzdar/running-multiple-open-source-llms-on-ocis-free-arm-tier-with-ollama-open-webui-f3193df00dc9) ·
[HF ZeroGPU free quota = 3.5 min/day](https://discuss.huggingface.co/t/free-account-zerogpu-quota-issue/175180) ·
[HF pricing 2026](https://www.metacto.com/blogs/the-true-cost-of-hugging-face-a-guide-to-pricing-and-integration)
