# Single-container deploy (Hugging Face Spaces / any Docker host).
# FastAPI orchestrator + embedder + reranker + embedded Qdrant + student portal.
# CPU-only. The LLM is a hosted OpenAI-compatible API (set via env).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Model cache baked into the image (below) so cold starts don't re-download
    # the ~2GB embedder + reranker. Kept under /app so it survives in the layer.
    HF_HOME=/app/.cache/hf

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first so pip doesn't pull the ~2GB CUDA build transitively.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Editable install so `ritaj` keeps importing from /app/src (api.py resolves the
# portal path relative to the source tree).
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

# Pre-download (bake) the embedder + reranker into the image.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('intfloat/multilingual-e5-large'); \
CrossEncoder('BAAI/bge-reranker-v2-m3')"

COPY data ./data
COPY scripts ./scripts
COPY ritaj-student-portal/dist ./ritaj-student-portal/dist

# HF Spaces runs as a non-root user (UID 1000): make caches/app readable+writable.
RUN chmod +x scripts/start.sh && chmod -R 777 /app/.cache

# HF Spaces serves on 7860; start.sh binds uvicorn to $PORT (default 7860).
EXPOSE 7860
CMD ["scripts/start.sh"]
