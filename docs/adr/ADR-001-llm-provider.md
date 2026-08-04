# ADR-001 — LLM provider for the release pilot

**Status:** accepted
**Date:** 2026-08-04
**Supersedes:** the implicit "Groq `llama-3.3-70b-versatile`" choice recorded in
`DEPLOYMENT.md` and `CLAUDE.md`.

## Context

The release requires Gemma 4 and a responsive, always-available endpoint. The
backend (`src/ritaj/llm.py`) speaks the OpenAI Chat Completions protocol, so any
OpenAI-compatible host is a configuration change rather than a rewrite.

Options considered (limits checked against provider documentation on
2026-08-04, recorded in `RELEASE_ROADMAP_2026.md` §3):

| Option | Own weights? | Practical ceiling |
|---|---|---|
| Cloudflare Workers AI `@cf/google/gemma-4-26b-a4b-it` | no | 10,000 neurons/day free ≈ 200 RAG answers/day |
| Oracle Always Free A1 (2 OCPU / 12 GB) + Ollama `gemma4:e2b` | yes | CPU-speed generation, low concurrency, idle-reclamation risk |
| HF ZeroGPU | yes | 5 GPU-minutes/day; needs a Gradio-shaped rewrite |
| HF CPU Space hosting Gemma beside E5-large + BGE-M3 | yes | will not fit 16 GB / 2 vCPU safely |
| Render / Railway / Koyeb free tiers | no | too small for this backend |

## Decision

Use **Cloudflare Workers AI `@cf/google/gemma-4-26b-a4b-it`** for the release
pilot. Keep the Oracle self-host as the independence/fallback path, evaluated in
the split topology (HF Space runs the RAG app, Oracle runs only Gemma).

Configuration lives entirely in environment variables:

```dotenv
LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
LLM_MODEL=@cf/google/gemma-4-26b-a4b-it
LLM_API_KEY=<CLOUDFLARE_API_TOKEN>   # server-side secret only
```

## Consequences

- Fastest migration: no client rewrite, and the provider is swappable again later.
- The free allocation is a hard ceiling. The service must degrade politely rather
  than fail opaquely, so a daily budget guard (`src/ritaj/budget.py`) trips
  *below* the provider limit and returns `LLM_BUDGET_EXHAUSTED`.
- Answers leave the university's infrastructure and are processed by Cloudflare.
  The privacy policy must name Cloudflare (not Groq) as the model host —
  see Phase 8.
- Dependence on a third party remains; ADR revisit is triggered by (a) quota
  proving insufficient in the pilot, (b) a policy requirement to keep data
  on-premises, or (c) Oracle benchmarks meeting an agreed relaxed SLO.

## Not decided here

Whether to promote the Oracle self-host to production. That needs the Phase 7
benchmark numbers (first-token latency, tokens/sec, peak RSS, two-request
concurrency) which cannot be produced without an Oracle account.
