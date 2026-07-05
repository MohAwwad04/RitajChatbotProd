# Dependencies — What's Installed & Why

This documents every package installed into the project's virtual environment
(`.venv`), grouped by **direct** dependencies (the ones we deliberately chose,
declared in `pyproject.toml`) and **transitive** dependencies (pulled in
automatically because the direct ones need them).

Environment: Python 3.13 · macOS (Apple Silicon) · installed via `pip install -e ".[dev]"`

---

## 1. Direct dependencies (we chose these)

These are the building blocks of the RAG pipeline. Each maps to a stage in `PLAN.md`.

| Package | Version | What it is | Why we use it (goal in this project) |
|---------|---------|-----------|--------------------------------------|
| **chromadb** | 1.5.9 | Open-source vector database | Stores document chunks as embeddings and finds the most relevant ones for a question. The "memory" / retrieval store (PLAN §5). Self-hosted so data stays on-prem. |
| **sentence-transformers** | 5.5.1 | Library for text embedding models | Runs the multilingual embedder (`multilingual-e5-large`) that turns Arabic/English text into meaning-vectors for search (PLAN §5, §10). |
| **fastapi** | 0.137.1 | Modern Python web framework | Exposes the assistant over HTTP — the `/chat` orchestrator endpoint the frontend/widget calls (PLAN §4). |
| **uvicorn** | 0.49.0 | ASGI web server | Actually runs the FastAPI app (`uvicorn ritaj.api:app`). The process that serves requests. |
| **pypdf** | 6.13.2 | PDF text extraction | Reads text out of PDF documents (handbooks, calendars) during ingestion (PLAN §6.1). |
| **python-dotenv** | 1.2.2 | Loads `.env` files | Reads config (LLM URL, model name, paths) from `.env` so settings aren't hard-coded — the dev↔prod switch lives here. |
| **httpx** | 0.28.1 | HTTP client | Calls the LLM's OpenAI-compatible API (Ollama in dev, vLLM in prod) from `llm.py`. |
| **pydantic** | 2.13.4 | Data validation | Validates/parses incoming request bodies in the API (e.g. the `{"message": ...}` schema). |
| **pytest** *(dev)* | 9.1.0 | Testing framework | Runs the smoke tests; seed of the golden-set eval harness (PLAN §13). |

---

## 2. Transitive dependencies (pulled in automatically)

Grouped by which direct dependency brought them in and what role they play.

### ML / embeddings backend (via `sentence-transformers`)
| Package | Role |
|---------|------|
| **torch** (2.12.0) | Deep-learning engine that runs the embedding model. The heavyweight of the install. |
| **transformers** (5.12.1) | Hugging Face model library; loads the e5 model architecture. |
| **tokenizers** (0.22.2) | Fast text tokenization for the embedder. |
| **huggingface-hub** (1.19.0), **hf-xet** (1.5.1) | Download model weights from Hugging Face on first run. |
| **safetensors** (0.8.0) | Safe, fast format for loading model weights. |
| **scikit-learn** (1.9.0), **scipy** (1.17.1), **numpy** (2.4.6) | Numerical / vector math underneath embeddings and similarity. |
| **sympy** (1.14.0), **mpmath** (1.3.0), **networkx** (3.6.1), **filelock**, **fsspec**, **joblib**, **threadpoolctl**, **regex** | Math, graph, file, and caching utilities torch/transformers depend on. |

### Vector DB internals (via `chromadb`)
| Package | Role |
|---------|------|
| **onnxruntime** (1.27.0) | Runs Chroma's built-in models efficiently. |
| **grpcio** (1.81.1), **protobuf** (6.33.6), **googleapis-common-protos** | Internal communication / data serialization for Chroma. |
| **opentelemetry-*** (api, sdk, exporters) | Tracing/telemetry hooks — aligns with the observability goal (PLAN §15). |
| **kubernetes** (36.0.2) | Client Chroma uses for clustered/server deployments. |
| **pypika** (0.51.1) | Builds SQL queries for Chroma's metadata store. |
| **mmh3**, **pybase64**, **bcrypt**, **overrides**, **durationpy**, **tenacity** | Hashing, encoding, auth, and retry helpers. |

### Web stack (via `fastapi` / `uvicorn`)
| Package | Role |
|---------|------|
| **starlette** (1.3.1) | The ASGI toolkit FastAPI is built on (routing, requests). |
| **pydantic-core** (2.46.4), **pydantic-settings**, **annotated-types**, **typing-inspection** | Engine and helpers behind pydantic validation. |
| **anyio** (4.14.0), **h11**, **httpcore**, **httptools**, **uvloop**, **websockets**, **watchfiles** | Async I/O, HTTP/WebSocket protocol handling, and `--reload` file watching for the server. |
| **certifi**, **idna**, **urllib3**, **charset-normalizer**, **requests**, **requests-oauthlib**, **oauthlib**, **websocket-client** | HTTP/TLS plumbing used across networking libs. |

### Shared utilities
| Package | Role |
|---------|------|
| **rich**, **typer**, **click**, **shellingham**, **pygments**, **markdown-it-py**, **mdurl** | Pretty terminal output and CLI handling used by several tools. |
| **tqdm** (4.68.2) | Progress bars during model downloads / embedding. |
| **pyyaml**, **jsonschema**, **jsonschema-specifications**, **referencing**, **rpds-py**, **orjson** | Config parsing and fast JSON/schema handling. |
| **jinja2**, **MarkupSafe** | Templating (transitive). |
| **packaging**, **setuptools**, **build**, **pyproject-hooks**, **importlib-resources**, **iniconfig**, **pluggy**, **typing-extensions**, **six**, **python-dateutil**, **attrs**, **annotated-doc**, **flatbuffers**, **multidict**, **yarl**, **frozenlist**, **aiosignal**, **aiohttp**, **aiohappyeyeballs**, **propcache**, **narwhals** | Build tooling, plugin systems, and low-level async/data helpers required by the above. |

---

## 3. Not yet installed (next step — outside Python)

These are part of the stack but installed separately, not via pip:

| Component | What it is | Goal | How to install |
|-----------|-----------|------|----------------|
| **Ollama** | Local LLM server (macOS app) | Serves the Gemma 4 model behind an OpenAI-compatible API for local dev | `brew install ollama` or [ollama.com/download](https://ollama.com/download) |
| **Gemma 4 (E4B)** | Google's open-weight LLM | The "writer" that composes grounded, cited answers (PLAN §8) | `ollama pull gemma4:e4b` (verify exact tag) |
| **e5 embedding weights** | `intfloat/multilingual-e5-large` (~2 GB) | Downloaded automatically on the first `build_index.py` run by sentence-transformers | (automatic) |

> **Production note:** in prod the LLM is served by **vLLM** on a GPU host (not
> Ollama), running the larger `gemma-4-26B-A4B-it` / `31B` models. Same API, so
> no code changes — see `PLAN.md` §5 and §15.
