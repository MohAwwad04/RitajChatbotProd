# Ritaj AI Assistant — Project Base

> ENCS5342 Course Project — NLP_Project

A walking-skeleton RAG chatbot: **document → ChromaDB → Gemma 4 → cited answer**,
exposed over one FastAPI route. See `PLAN.md` for the full design and
`PLAN_EXPLAINED.md` for the plain-language reasoning.

## Stack

- **LLM:** Gemma 4 (open-weight), served via **Ollama** in dev and **vLLM** in
  prod — both reached through one OpenAI-compatible client. Switch by editing
  `.env` only.
- **Vector DB:** ChromaDB (self-hosted, on-prem).
- **Embeddings:** `intfloat/multilingual-e5-large` (Arabic + English).
- **API:** FastAPI.

## Setup

1. **Install dependencies**
   ```bash
   uv venv && source .venv/bin/activate   # or: python3 -m venv .venv && source .venv/bin/activate
   uv pip install -e ".[dev]"             # or: pip install -e ".[dev]"
   ```

2. **Start the LLM (Ollama)**
   ```bash
   # install from https://ollama.com, then:
   ollama pull gemma4:e4b      # use gemma4:e2b on lighter machines
   ```
   (Verify the exact model tag on ollama.com.)

3. **Configure**
   ```bash
   cp .env.example .env        # defaults already point at local Ollama
   ```

## Run

```bash
# 1. Build the index from data/raw/ (first run downloads the embedder, ~2 GB)
python scripts/build_index.py

# 2. Start the API
uvicorn ritaj.api:app --reload --app-dir src

# 3. Ask a question
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message": "How do I drop a course in Ritaj?"}' | python -m json.tool
```

## Test

```bash
pytest
```

## What's next (in order)

~~Hybrid search (BM25 sidecar + RRF)~~ ✅ → ~~reranker~~ ✅ → ~~Arabic
normalization~~ ✅ → structure-aware chunking → streaming + auth on the API →
the React widget → tool calling for personalized data. See `PLAN.md` sections
7–9.

Retrieval is a **funnel** — `retrieve()` runs dense (Chroma) and sparse (BM25,
`bm25.py`) in parallel, fuses them with Reciprocal Rank Fusion for recall, then
a cross-encoder reranker (`rerank.py`, `BAAI/bge-reranker-v2-m3`) reorders the
candidates by true relevance and keeps the top `TOP_K`. The BM25 index is built
lazily from the chunks already in Chroma, so rebuild the index and restart the
API to pick up new content. The reranker downloads ~600 MB on first use.

Arabic text is normalized (`arabic.py`) before both embedding and BM25
tokenization — unifying alef/ya/ta-marbuta forms, stripping diacritics, tatweel
and the definite article, and mapping Arabic-Indic digits — so مقرر and المقرر
match. English passes through unchanged. **Note:** the current `data/raw/`
corpus is English-only, so BM25 can't keyword-match Arabic queries yet (dense
search handles them cross-lingually); the normalization pays off once real
Arabic documents are indexed.

## Note on data

The project runs **fully locally** — no live Ritaj/Birzeit connection. The
knowledge base is just the files in `data/raw/`; the chatbot answers only from
what's indexed there. Each file declares its provenance in a header:

- **REAL** — public facts collected from `birzeit.edu` (academic calendar,
  tuition, admission, English placement). Each cites its source URL and the
  academic year it reflects. Verify against the official site before a pilot;
  the university revises these.
- **MIXED / SAMPLE** — clearly-labeled illustrative content filling gaps the
  public site doesn't expose (e.g. step-by-step portal/IT instructions, the full
  letter-grade table). Replace with official documents (the Computer Center
  partnership in plan Phase 0) before any pilot.

Note: the Ritaj portal itself (`ritaj.birzeit.edu`) requires login, so its
private content is intentionally **not** scraped — only public pages were used.
