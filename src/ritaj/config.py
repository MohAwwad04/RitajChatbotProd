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

    # Model revisions, pinned. A bare repo name resolves to whatever is on the
    # hub at build time, so two builds of the same commit can bake different
    # weights — and different weights mean different retrieval, which invalidates
    # the evaluation the release was signed off on. These are the revisions the
    # current results were produced with.
    embed_revision: str = os.getenv(
        "EMBED_REVISION", "3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3"
    )
    rerank_revision: str = os.getenv(
        "RERANK_REVISION", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )

    # Vector store (Qdrant).
    #
    # QDRANT_MODE makes the choice explicit instead of inferring it from which
    # variable happens to be set. The old rule was "QDRANT_PATH wins if
    # non-empty", which meant a deployment carrying both a cloud URL and a
    # leftover path silently ran embedded against an empty local directory and
    # reported itself healthy — the failure looks exactly like an empty corpus.
    #
    #   embedded  Qdrant on local disk at QDRANT_PATH. No separate service. What
    #             the single-container Spaces deploy uses.
    #   remote    A Qdrant server at QDRANT_URL, with QDRANT_API_KEY over TLS
    #             for Qdrant Cloud.
    #   auto      Legacy inference, kept so an existing deployment does not break
    #             on upgrade: path if set, else url.
    qdrant_mode: str = os.getenv("QDRANT_MODE", "auto").strip().lower()
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_path: str = os.getenv("QDRANT_PATH", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")
    qdrant_timeout_seconds: float = float(os.getenv("QDRANT_TIMEOUT_SECONDS", "10"))
    collection: str = os.getenv("COLLECTION", "ritaj")
    # The name clients read. Indexing writes `ritaj_<corpus-version>` and points
    # this alias at it only after the new collection validates, so a rebuild
    # never leaves the live name pointing at a half-filled collection — and the
    # previous one survives for an instant rollback.
    qdrant_alias: str = os.getenv("QDRANT_COLLECTION_ALIAS", "")

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

    # Per-SESSION limits. The session id is client-supplied, so these bound one
    # conversation rather than one attacker — a hostile client can mint a new id.
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    rate_limit_per_hour: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "60"))
    rate_limit_per_day: int = int(os.getenv("RATE_LIMIT_PER_DAY", "150"))

    # Per-NETWORK limits. A client cannot change its address, so this is the
    # limit that actually holds. Set higher than the session limits because a
    # campus NAT puts many honest students behind one address — the answer to
    # shared egress is a separate, larger allowance, not a weaker identity model.
    network_rate_limit_per_minute: int = int(os.getenv("NETWORK_RATE_LIMIT_PER_MINUTE", "30"))
    network_rate_limit_per_hour: int = int(os.getenv("NETWORK_RATE_LIMIT_PER_HOUR", "200"))
    network_rate_limit_per_day: int = int(os.getenv("NETWORK_RATE_LIMIT_PER_DAY", "400"))

    # How many proxies sit in front of this deployment. 0 = ignore
    # X-Forwarded-For entirely (safe against spoofing; behind a proxy it makes
    # the network limit effectively global). On Hugging Face Spaces this is
    # normally 1 — confirm against the host before setting it, because too high
    # a value lets a client choose its own rate-limit bucket.
    trusted_proxy_count: int = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
    # Global cap on simultaneous generations — a 2-core CPU host with one model
    # copy cannot usefully run more, and unbounded concurrency is how a free
    # quota disappears in a minute.
    max_concurrent_generations: int = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "2"))
    queue_timeout_seconds: float = float(os.getenv("QUEUE_TIMEOUT_SECONDS", "10"))

    # Daily application budget, in the unit the provider actually meters.
    # Cloudflare's free Workers AI allowance is 10,000 neurons/day; 9,000 leaves
    # headroom so the service returns a controlled message instead of the
    # provider's error mid-stream. 0 disables the guard (development).
    #
    # Counting neurons rather than answers is deliberate — see budget.py. A
    # request-count budget mis-prices a short question and a six-turn
    # conversation identically, and the previous one silently missed the second
    # provider call that every follow-up makes.
    llm_daily_neuron_budget: int = int(os.getenv("LLM_DAILY_NEURON_BUDGET", "9000"))
    # Optional coarse safety net on raw provider calls, independent of size.
    # 0 = off; the neuron budget is the real limit.
    llm_daily_call_cap: int = int(os.getenv("LLM_DAILY_CALL_CAP", "0"))

    # Neuron cost per million tokens, derived from Cloudflare's published prices
    # for @cf/google/gemma-4-26b-a4b-it ($0.10/M input, $0.30/M output) at the
    # Workers Paid rate of $0.011 per 1,000 neurons. Configurable because a
    # provider price change would otherwise silently invalidate the budget.
    neurons_per_m_input: int = int(os.getenv("NEURONS_PER_M_INPUT", "9091"))
    neurons_per_m_output: int = int(os.getenv("NEURONS_PER_M_OUTPUT", "27273"))

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
    problems.extend(qdrant_problems())
    return problems


def qdrant_mode() -> str:
    """The resolved store mode: 'embedded' or 'remote'.

    `auto` reproduces the historical rule so an existing deployment keeps
    working; anything explicit is honoured exactly, which is the point.
    """
    declared = settings.qdrant_mode
    if declared in {"embedded", "remote"}:
        return declared
    return "embedded" if settings.qdrant_path else "remote"


def qdrant_problems() -> list[str]:
    """Store configuration that is ambiguous or unsafe. [] = fine.

    Separated from check_production_config so the indexing job — which runs
    outside the server and must not start against the wrong cluster — can call
    it too.
    """
    problems: list[str] = []
    mode = qdrant_mode()

    if settings.qdrant_mode not in {"embedded", "remote", "auto"}:
        problems.append(
            f"QDRANT_MODE must be 'embedded', 'remote' or 'auto', got {settings.qdrant_mode!r}"
        )

    if mode == "embedded":
        if not settings.qdrant_path:
            problems.append("QDRANT_MODE=embedded but QDRANT_PATH is empty")
        if settings.qdrant_api_key:
            # A key present in embedded mode means someone believes they are
            # talking to Qdrant Cloud and are not. Refusing is the only way that
            # belief gets corrected before the corpus appears to vanish.
            problems.append(
                "QDRANT_API_KEY is set but the store is embedded — the key would "
                "be ignored and the cloud collection never read"
            )
    else:
        if not settings.qdrant_url:
            problems.append("QDRANT_MODE=remote but QDRANT_URL is empty")
        elif production():
            if not settings.qdrant_url.startswith("https://"):
                problems.append(
                    f"QDRANT_URL must be https in production, got {_scheme_of(settings.qdrant_url)!r}"
                )
            if not settings.qdrant_api_key:
                problems.append("QDRANT_MODE=remote in production but QDRANT_API_KEY is empty")
        if settings.qdrant_path and settings.qdrant_mode == "remote":
            problems.append(
                "QDRANT_MODE=remote but QDRANT_PATH is also set — unset it, or the "
                "next person to read this config cannot tell which store is live"
            )
    return problems


def _scheme_of(url: str) -> str:
    """The scheme of `url`, for an error message that never echoes the host.

    A Qdrant Cloud URL identifies the cluster, and error strings reach logs and
    sometimes clients. Only the scheme is ever quoted back.
    """
    return url.split("://", 1)[0] if "://" in url else "(none)"
