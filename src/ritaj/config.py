"""Central configuration, loaded from environment / .env.

Every tunable lives here so the rest of the code never reads os.environ
directly. Switching from local Ollama to the GPU vLLM server is a .env change.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    """Read a boolean env var. Anything but 1/true/yes/on is false."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class Settings:
    # Which deployment this is. "production" turns on the fail-closed checks:
    # admin auth must be configured, CORS must be an explicit allowlist, and the
    # slow in-process index build is refused. Getting this wrong should make the
    # service refuse to start, not quietly run a development configuration in
    # front of students.
    environment: str = os.getenv("ENVIRONMENT", "development").strip().lower()

    # LLM (any OpenAI-compatible endpoint: Ollama for dev, Cloudflare Workers AI
    # for the pilot — see docs/adr/ADR-001-llm-provider.md)
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

    # Operator console — per-user login (preferred). "username:bcrypt_hash"
    # pairs, comma/newline-separated (hashes ONLY, never plaintext). Generate
    # with `python -m ritaj.adminauth hash <username>`. When set, every /admin/*
    # route requires a session token obtained from POST /admin/login, and this
    # takes precedence over the legacy ADMIN_TOKEN below.
    admin_users: str = os.getenv("ADMIN_USERS", "")
    # HMAC key that signs admin session tokens. Set a long random value in prod
    # (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) so
    # sessions survive restarts; if empty, a random per-process key is used and
    # everyone is logged out on restart.
    session_secret: str = os.getenv("SESSION_SECRET", "")
    session_ttl_hours: int = int(os.getenv("SESSION_TTL_HOURS", "12"))

    # Legacy single shared token (fallback used only when ADMIN_USERS is empty).
    # When set, every /admin/* API route requires it (X-Admin-Token or
    # Authorization: Bearer). Empty = open, for local dev only.
    admin_token: str = os.getenv("ADMIN_TOKEN", "")

    # Where runtime writers persist. On HF Spaces the app dir is read-only for
    # the runtime user, so start.sh points these at /tmp/… there.
    chat_log_path: str = os.getenv("CHAT_LOG_PATH", "chat_log.jsonl")
    calibration_path: str = os.getenv("CALIBRATION_PATH", "calibration.json")

    # Conversation memory bounds (per request; the server enforces these on the
    # client-sent history so a hostile client can't blow up the prompt).
    history_max_turns: int = int(os.getenv("HISTORY_MAX_TURNS", "8"))
    history_max_chars: int = int(os.getenv("HISTORY_MAX_CHARS", "1500"))

    # ---- Startup (Phase 1) --------------------------------------------------
    # Whether the service may embed the corpus in-process at boot. Production
    # serves a prebuilt corpus artifact (scripts/build_index.py --publish);
    # building inside the launch window is what caused the Hugging Face
    # `Launch timed out` failure, so it is off by default outside development.
    allow_index_build_on_boot: bool = _flag(
        "ALLOW_INDEX_BUILD_ON_BOOT", os.getenv("ENVIRONMENT", "development") != "production"
    )
    # Whether creating the app kicks off background initialization. Always true
    # in a real deployment; tests and CLI tools that only exercise HTTP routing
    # set STARTUP_INIT=0 so importing the app doesn't load a 2 GB embedder.
    startup_init: bool = _flag("STARTUP_INIT", True)

    # ---- Public-service controls (Phase 4) ----------------------------------
    # Explicit CORS allowlist. The published extension origin
    # (chrome-extension://<id>) and the deployed web origin belong here; "*" is
    # refused in production because the chat endpoint costs real LLM quota.
    cors_origins: list[str] = _csv("CORS_ORIGINS")
    # Convenience: the Chrome Web Store extension id, expanded into an origin.
    extension_id: str = os.getenv("EXTENSION_ID", "").strip()

    # Request size limits — the prompt is built from these, so they cap cost.
    max_message_chars: int = int(os.getenv("MAX_MESSAGE_CHARS", "2000"))
    max_body_bytes: int = int(os.getenv("MAX_BODY_BYTES", "32768"))

    # Anonymous rate limits, per network bucket and per local session.
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    rate_limit_per_hour: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "60"))
    rate_limit_per_day: int = int(os.getenv("RATE_LIMIT_PER_DAY", "150"))
    # Global cap on simultaneous generations — a 2-core CPU host with one model
    # copy cannot usefully run more, and unbounded concurrency is how a free
    # quota disappears in a minute.
    max_concurrent_generations: int = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))
    queue_timeout_seconds: float = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "10"))

    # Daily application budget for LLM answers. Kept below the provider's hard
    # free allowance so the service returns a controlled message instead of the
    # provider's error. 0 disables the guard.
    llm_daily_budget: int = int(os.getenv("LLM_DAILY_BUDGET", "180"))

    # ---- Telemetry + retention (Phase 4/8) ----------------------------------
    # "aggregate" (default): counts, verdicts, latencies — no question/answer
    # text. "full": raw conversations, permitted only with an explicit opt-in
    # and a stated retention period.
    chat_log_mode: str = os.getenv("CHAT_LOG_MODE", "aggregate").strip().lower()
    chat_log_retention_days: int = int(os.getenv("CHAT_LOG_RETENTION_DAYS", "30"))


settings = Settings()


def production() -> bool:
    return settings.environment == "production"


def allowed_origins() -> list[str]:
    """Resolved CORS allowlist for this environment.

    Development keeps the permissive wildcard so local portals and unpacked
    extensions (whose ids change on every reload) just work. Production requires
    an explicit list — `check_production_config()` refuses to start without one.
    """
    origins = list(settings.cors_origins)
    if settings.extension_id:
        origins.append(f"chrome-extension://{settings.extension_id}")
    if not production() and not origins:
        return ["*"]
    return sorted(set(origins))


def check_production_config() -> list[str]:
    """Configuration errors that must prevent a production start. [] = fine.

    Fail-closed: every one of these silently degrades a public deployment into
    an unsafe one, and each has already been observed in this project's own
    history (open CORS, an unauthenticated /admin, a Space with no LLM secret).
    """
    if not production():
        return []
    problems: list[str] = []
    if not (settings.admin_users or settings.admin_token):
        problems.append(
            "no admin authentication configured (set ADMIN_USERS with bcrypt hashes)"
        )
    if settings.admin_users and not settings.session_secret:
        problems.append(
            "SESSION_SECRET is empty — admin sessions would not survive a restart"
        )
    if not allowed_origins():
        problems.append("CORS_ORIGINS / EXTENSION_ID are empty (no origin may call the API)")
    if "*" in allowed_origins():
        problems.append("CORS_ORIGINS contains '*' — not permitted in production")
    if not settings.llm_api_key or settings.llm_api_key == "ollama":
        problems.append("LLM_API_KEY is unset or still the Ollama placeholder")
    if settings.chat_log_mode not in {"aggregate", "full"}:
        problems.append(f"CHAT_LOG_MODE must be 'aggregate' or 'full', got {settings.chat_log_mode!r}")
    return problems
