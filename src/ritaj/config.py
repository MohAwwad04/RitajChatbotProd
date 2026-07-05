"""Central configuration, loaded from environment / .env.

Every tunable lives here so the rest of the code never reads os.environ
directly. Switching from local Ollama to the GPU vLLM server is a .env change.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM (any OpenAI-compatible endpoint: Ollama for dev, vLLM in prod)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")
    llm_model: str = os.getenv("LLM_MODEL", "gemma4:e4b")

    # Embeddings (multilingual; must handle Arabic well)
    embed_model: str = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")

    # Reranker (cross-encoder; multilingual). Refines the fused candidate list.
    rerank_model: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

    # Vector store (Qdrant). A remote http URL talks to a Qdrant server (Docker in
    # dev). Set QDRANT_PATH instead to run Qdrant embedded on local disk — no
    # separate service needed, which is what the single-container HF Spaces deploy
    # uses (the index is rebuilt from data/raw on boot).
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_path: str = os.getenv("QDRANT_PATH", "")
    collection: str = os.getenv("COLLECTION", "ritaj")

    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "6"))

    # Operator console. When set, every /admin/* API route requires this token
    # (X-Admin-Token or Authorization: Bearer). Empty = open, for local dev only;
    # ALWAYS set it on a public deployment.
    admin_token: str = os.getenv("ADMIN_TOKEN", "")

    # Where runtime writers persist. On HF Spaces the app dir is read-only for
    # the runtime user, so start.sh points these at /tmp/… there.
    chat_log_path: str = os.getenv("CHAT_LOG_PATH", "chat_log.jsonl")
    calibration_path: str = os.getenv("CALIBRATION_PATH", "calibration.json")

    # Conversation memory bounds (per request; the server enforces these on the
    # client-sent history so a hostile client can't blow up the prompt).
    history_max_turns: int = int(os.getenv("HISTORY_MAX_TURNS", "8"))
    history_max_chars: int = int(os.getenv("HISTORY_MAX_CHARS", "1500"))


settings = Settings()
