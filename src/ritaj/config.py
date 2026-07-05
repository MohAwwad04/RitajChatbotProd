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

    # Vector store
    chroma_path: str = os.getenv("CHROMA_PATH", "./chroma_db")
    collection: str = os.getenv("COLLECTION", "ritaj")

    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "6"))


settings = Settings()
