"""FastAPI orchestrator — the HTTP boundary for the assistant.

Routes group into three surfaces:
  • Student portal  — GET / serves the React SPA; POST /chat[/stream] answer it.
  • Admin dashboard — GET /admin is the operator console (3D + process view and a
    calibration tab); /admin/* powers it (viz data, evals, config, training).
  • /health.

Run:  uvicorn ritaj.api:app --reload --app-dir src
"""

import json
import logging
import secrets as _secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import (
    about, adminauth, answer_checks, bodylimit, bootstrap, budget, chatlog, citations, config,
    corpus, errors, evaluation, generate, grounding, guardrails, ingest, links, llm,
    navigation, ratelimit, readiness, redact, runtime_config, source_policy,
    vectorstore, viz,
)
from .config import settings
from .generate import answer, answer_stream, repair
from .retrieve import retrieve, trace

log = logging.getLogger("ritaj.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bind the port first; initialize behind it.

    Uvicorn starts accepting connections as soon as this yields, so /live answers
    within milliseconds of the process starting. Loading the embedder, opening
    the corpus and warming retrieval all happen on a background thread, and chat
    reports INITIALIZING until they finish. The previous arrangement — a full
    index build ahead of `exec uvicorn` — meant nothing listened on the port for
    minutes, which is what Hugging Face eventually killed as unhealthy.
    """
    problems = config.check_production_config()
    if problems:
        # Fail closed. A misconfigured production deployment must not start and
        # look healthy; that is how an open /admin or a wildcard CORS ships.
        for problem in problems:
            log.critical("production configuration error: %s", problem)
        raise RuntimeError(
            "refusing to start in production with: " + "; ".join(problems)
        )
    readiness.mark("listening")
    if settings.startup_init:
        readiness.start_background_init(bootstrap.initialize)
    yield


app = FastAPI(title="Ritaj Assistant", version="0.1.0", lifespan=lifespan)

# --- Middleware ordering ------------------------------------------------------
# Starlette builds the stack so that the LAST middleware added is the OUTERMOST.
# The order below is therefore, from outside in:
#
#     CORS  ->  request context  ->  body size limit  ->  application
#
# CORS must be outermost so that *every* response carries the headers — including
# the 413 from the body limiter and the 429 from rate limiting. With CORS inside,
# a browser reports those as an opaque CORS failure and the client can neither
# display the reason nor honour Retry-After.
#
# The body limiter is innermost of the three because it is the only one that
# needs to sit on the receive channel, and nothing outside it reads the body.

app.add_middleware(bodylimit.BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and log the outcome without the content.

    The id is the join key between what a student can quote ("it said
    LLM_UNAVAILABLE, request 3f2a…") and the protected log line that holds the
    provider's actual error. It is echoed in the response header and in the SSE
    `done` event.

    Body size is enforced one layer in (bodylimit.py), on the bytes themselves —
    a `Content-Length` check here would be skipped entirely by a chunked request.
    """
    request_id = _secrets.token_hex(8)
    request.state.request_id = request_id

    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if request.url.path.endswith("/chat") or request.url.path.endswith("/chat/stream"):
        log.info(
            "chat request_id=%s status=%s ms=%.0f client_ip=%s",
            request_id, response.status_code, (time.monotonic() - started) * 1000,
            redact.ip(ratelimit.client_ip(request)),
        )
    return response


# The chat endpoints are called cross-origin by the Chrome extension (origin
# chrome-extension://<id>) and by the deployed web portal. No cookies or
# credentials are used, but the endpoint spends metered LLM quota, so production
# takes an explicit allowlist (config.allowed_origins) rather than a wildcard
# that lets any site on the internet bill this account. Development still
# resolves to "*" so unpacked extensions — whose origin changes on each reload —
# keep working.
#
# Added last, so it wraps everything above.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


def _supplied_token(request: Request) -> str:
    """Pull the admin credential from `X-Admin-Token` or `Authorization: Bearer`."""
    supplied = request.headers.get("x-admin-token", "")
    auth = request.headers.get("authorization", "")
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:]
    return supplied


def require_admin(request: Request) -> None:
    """Gate for every /admin/* API route.

    Three modes, in priority order:
      1. ADMIN_USERS set → per-user login: the caller must present a valid
         session token (from POST /admin/login) as `X-Admin-Token` or Bearer.
      2. else ADMIN_TOKEN set → legacy single shared token.
      3. else open — local development only.
    """
    if adminauth.load_users():
        if adminauth.verify_session(_supplied_token(request)):
            return
        raise HTTPException(status_code=401, detail="admin login required")

    token = settings.admin_token
    if not token:
        return
    if not _secrets.compare_digest(_supplied_token(request), token):
        raise HTTPException(status_code=401, detail="admin token required")


_ADMIN = [Depends(require_admin)]


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/admin/login", include_in_schema=False)
def admin_login(req: LoginRequest, request: Request):
    """Exchange username + password for a signed session token.

    Not gated by `require_admin` (it is how you obtain the credential). Only
    active when ADMIN_USERS is configured; rate-limited per (IP, username).
    """
    if not adminauth.load_users():
        raise HTTPException(status_code=404, detail="login disabled (no accounts configured)")
    ip = request.client.host if request.client else "?"
    key = f"{ip}:{req.username}"
    if adminauth.rate_limited(key):
        raise HTTPException(status_code=429, detail="too many attempts — wait a few minutes")
    if not adminauth.authenticate(req.username.strip(), req.password):
        adminauth.record_fail(key)
        raise HTTPException(status_code=401, detail="invalid username or password")
    adminauth.clear_fails(key)
    token, exp = adminauth.issue_session(req.username.strip())
    return {"token": token, "username": req.username.strip(), "expires_at": exp}


@app.get("/admin/me", include_in_schema=False, dependencies=_ADMIN)
def admin_me(request: Request):
    """Who am I — used by the console to confirm a session is still valid."""
    return {"username": adminauth.verify_session(_supplied_token(request)) or ""}

_STATIC = Path(__file__).parent / "static"
# The student-facing React SPA (built with `npm run build`). Its assets are
# absolute (/assets/...), so we mount that directory at the root and serve the
# SPA index at GET / (and /chat as a friendly alias).
_PORTAL = Path(__file__).resolve().parents[2] / "ritaj-student-portal" / "dist"

if (_PORTAL / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_PORTAL / "assets"), name="assets")

# Backend-owned static files (e.g. the team photos for the about-the-makers reply).
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def _bound_content(cls, value: str) -> str:
        if len(value) > settings.max_message_chars:
            raise ValueError(
                f"history turn exceeds {settings.max_message_chars} characters"
            )
        return value


class ChatRequest(BaseModel):
    """The /chat and /v2/chat request body.

    Length bounds are validated here, not in the handler, so an oversized
    request is rejected before any of it is used to build a prompt — the prompt
    is what costs money on a metered provider.

    The bound is read from `settings.max_message_chars` at validation time
    rather than baked into `Field(max_length=...)` at import. There used to be
    three different answers to "how long may a message be?" — `MAX_MESSAGE_CHARS`
    said 2000 and was never read, the schema said 8000, and the extension had no
    limit at all. One setting, consulted everywhere, is the only version of this
    that stays true.
    """

    message: str = Field(min_length=1)
    # Conversation memory: the client sends its prior turns with every request
    # (the server stays stateless — nothing is cached per chat server-side).
    history: list[ChatTurn] = Field(default_factory=list, max_length=50)

    @field_validator("message")
    @classmethod
    def _bound_message(cls, value: str) -> str:
        if len(value) > settings.max_message_chars:
            raise ValueError(f"message exceeds {settings.max_message_chars} characters")
        return value
    # Optional client metadata, logged so the admin console can group a
    # conversation's turns and see which client a question came from.
    session_id: str | None = Field(default=None, max_length=100)
    client: str | None = Field(default=None, max_length=40)
    # v2 additions. `locale` picks the language of fixed responses when the
    # message itself is ambiguous. `current_ritaj_path` is accepted for forward
    # compatibility and deliberately unused: the first release sends no browsing
    # context at all, which is what lets the store listing say so (Phase 8).
    locale: Literal["ar", "en"] | None = None
    current_ritaj_path: str | None = Field(default=None, max_length=200)
    # Deprecated: a self-reported display name. The portal no longer collects
    # one (Phase 8) and it is only ever stored in the opt-in "full" log mode.
    # Kept so an older published client's request still validates instead of
    # 422-ing. Not marked deprecated=True on the field itself: pydantic emits a
    # DeprecationWarning on every read, which would fire on every request.
    user: str | None = Field(default=None, max_length=100)


def _bounded_history(req: ChatRequest) -> list[dict]:
    """Clamp client-sent history to sane bounds (turn count + chars per turn)."""
    turns = [
        {"role": t.role, "content": t.content.strip()[: settings.history_max_chars]}
        for t in req.history
        if t.content and t.content.strip()
    ]
    return turns[-settings.history_max_turns:]


@app.exception_handler(errors.PublicError)
async def _public_error_handler(request: Request, exc: errors.PublicError):
    """Return the stable code; keep the provider's words in the protected log.

    Raw exception text used to reach the browser, which could leak the upstream
    endpoint (the Cloudflare account id sits in its path) or a provider error
    body echoing the prompt.
    """
    log.warning("%s %s -> %s", request.method, request.url.path, exc)
    locale = request.headers.get("accept-language", "en")[:2].lower()
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return JSONResponse(exc.public(locale), status_code=exc.http_status, headers=headers)


def _admit(request: Request, req: ChatRequest) -> str:
    """Everything that must hold before a question costs anything. Returns the id.

    Order is deliberate — each check is cheaper than the next, and each refuses
    with a code the client can act on:
      readiness  → the service can answer at all
      rate limit → this caller has had its share (429 + Retry-After)
      budget     → today's provider allowance is spent (429, resets at UTC midnight)
    The concurrency cap is taken later, around generation itself, so a request
    that will be refused doesn't occupy a slot while being refused.
    """
    _require_ready()
    # Resolved through the configured trusted-proxy chain, not taken raw from
    # X-Forwarded-For — see ratelimit.client_ip.
    ratelimit.check(ratelimit.client_ip(request), req.session_id)
    budget.check()
    return getattr(request.state, "request_id", "")


def _require_ready() -> None:
    """Refuse chat until initialization finished — with a code, not a dead port.

    A client that receives `503 {"code":"INITIALIZING"}` knows to retry shortly.
    That is the whole reason readiness is modelled explicitly: during a cold
    start the service is *temporarily* unable to answer, which is different from
    being broken, and different again from not listening at all.
    """
    if readiness.is_ready() or not settings.startup_init:
        return
    state = readiness.state()
    if state in ("starting", "initializing"):
        raise errors.INITIALIZING(detail=f"state={state}", retry_after=10)
    # An absent corpus is not an outage and will not clear on its own, so it
    # gets its own code rather than being flattened into "try again shortly".
    # The category is already public on /ready; reusing it here just means the
    # chat surface stops contradicting the readiness surface.
    if readiness.failure_code() == "CORPUS_UNAVAILABLE":
        raise errors.NO_CORPUS(detail="no approved corpus published")
    raise errors.NOT_READY(detail=f"state={state}", retry_after=30)


# --- Student portal ---------------------------------------------------------
@app.get("/", include_in_schema=False)
@app.get("/chat", include_in_schema=False)
def portal_page():
    """Serve the Ritaj student portal SPA (the student-facing UI)."""
    return FileResponse(_PORTAL / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    return FileResponse(_PORTAL / "favicon.svg")


@app.get("/privacy", include_in_schema=False)
def privacy_page():
    """Privacy policy for the chatbot clients (the Chrome Web Store requires a
    public URL for it; the extension listing points here)."""
    return FileResponse(_STATIC / "privacy.html")


@app.get("/live")
def live():
    """Liveness: the process is up and serving. Never touches models or the store.

    This is the probe a host should restart on. It must not consult the vector
    store, load a model, or make a network call — a slow dependency would
    otherwise be indistinguishable from a dead process, and the platform would
    kill a container that was merely still warming up.
    """
    return {"status": "live", "state": readiness.state()}


@app.get("/ready")
def ready(request: Request):
    """Readiness: can this instance actually answer a question right now?

    503 while initializing or failed, so a load balancer withholds traffic
    without the process being restarted. The body names the state and the
    startup timings, which is what makes a slow boot diagnosable after the fact.

    Everything here is a *public* surface — an unauthenticated probe on the open
    internet. `readiness.snapshot()` is therefore sanitized: it carries a stable
    failure code and category, never the exception text, which can contain
    filesystem paths, provider URLs with the account id, or a secret name.
    """
    snap = readiness.snapshot()
    body = {
        "status": "ready" if readiness.is_ready() else "not-ready",
        **snap,
        "corpus": corpus.summary(),
        "llm": {"model": settings.llm_model, "circuit": llm.circuit_state()},
        # Whether the address used for rate limiting is plausibly the real
        # client. Silent and expensive in both directions — see ratelimit.py.
        "client_addressing": ratelimit.client_ip_diagnostics(request),
    }
    if readiness.is_ready():
        return body
    return JSONResponse(body, status_code=503)


@app.get("/health")
def health():
    """Backwards-compatible alias.

    The published extension and the portal both probe /health; it stays until
    those clients have rolled over. It reports *readiness*, which is what the
    old single route effectively promised.
    """
    if readiness.is_ready():
        return {"status": "ok", "state": "ready"}
    return JSONResponse({"status": "unavailable", "state": readiness.state()},
                        status_code=503)


@app.get("/capabilities")
def capabilities():
    """What this deployment can actually do, derived from the registries.

    The student portal's home view renders this. It exists because the portal
    previously described capabilities it did not have — a dashboard of invented
    courses, grades and a balance, over a backend whose scope guardrail declines
    every personal-record question by design (`guardrails._RESPONSE_PERSONAL`).
    A hard-coded list would drift back the same way, so nothing here is written
    twice: topics come from `data/sources.yaml`, destinations from
    `data/navigation.yaml`, and counts from the built corpus manifest.

    Public and unauthenticated, so it carries the same discipline as /ready:

      * only `approved: true` records are named. A review-queue entry is a
        question ("is this the right page?"), not a capability, and listing one
        would tell a student the assistant knows something it does not;
      * only `enabled: true` navigation actions are named, so flipping the kill
        switch withdraws a destination from the UI in the same redeploy that
        withdraws it from the answer path;
      * no filesystem path, no snapshot content, no owner email, no counts that
        reveal anything but size.
    """
    report = source_policy.load_and_validate(check_content=False)
    approved = [s for s in report.sources if s.approved]
    actions = [a for a in navigation.load_registry().values() if a.enabled]
    return {
        "corpus": corpus.summary(),
        "ready": readiness.is_ready(),
        "topics": [
            {
                "id": s.id,
                "title": s.title,
                "language": s.language,
                "url": s.canonical_url,
                "refresh": s.refresh,
                "stale": s.is_stale(),
            }
            for s in approved
        ],
        # Size of the review queue, without naming its members.
        "pending_topics": len(report.sources) - len(approved),
        "navigation": [
            {
                "id": a.id,
                "label_ar": a.label_ar,
                "label_en": a.label_en,
                "url": a.destination,
                "auth_required": a.auth_required,
            }
            for a in actions
        ],
        "pending_navigation": navigation.declared_count() - len(actions),
        # Per-feature readiness. A single `ready` boolean forced every client to
        # treat the whole product as one thing, so an absent corpus took the
        # page-finder down with it even though finding a page needs neither a
        # corpus nor a model. Clients degrade feature by feature off this block.
        "modes": _capability_modes(),
        # Stated positively so the portal renders the limits from the same
        # source of truth the guardrail enforces, rather than from UI copy.
        "limits": {
            "personal_records": False,   # grades, GPA, schedule, balance
            "sign_in_on_your_behalf": False,
            "public_ritaj_pages": True,
            "navigation_needs_confirmation": True,
        },
    }


def _capability_modes() -> dict:
    """Readiness split into the capabilities a client can use independently.

    `ready` (full factual chat) is the AND of the parts, so it keeps its old
    meaning for older clients. The parts are what let a new client keep working
    when only some of the system is up:

      live             the process answers. No dependency is consulted.
      navigation_ready an approved destination exists. Registry only — no vector
                       store, no embedder, no provider, so this stays true
                       through a corpus rebuild, a model outage and an exhausted
                       quota. It is the capability that survives.
      retrieval_ready  initialization finished, so the store and embedder work.
      generation_ready the provider is configured and neither the circuit
                       breaker nor the daily budget is refusing calls.
    """
    navigation_ready = any(a.enabled for a in navigation.load_registry().values())
    retrieval_ready = readiness.is_ready()
    # A missing key is the honest "not configured" case: production refuses to
    # start without one, but development and a mis-set Space would both reach
    # here, and a client should be told generation is unavailable rather than
    # discovering it one 500 at a time.
    generation_ready = bool(settings.llm_api_key) and llm.circuit_state() != "open"
    if generation_ready:
        try:
            budget.check()
        except errors.PublicError:
            generation_ready = False
    return {
        "live": True,
        "navigation_ready": navigation_ready,
        "retrieval_ready": retrieval_ready,
        "generation_ready": generation_ready,
        "ready": retrieval_ready and generation_ready,
    }


# --- Navigation (independent of corpus, model and quota) --------------------
#
# These two routes are the reason the extension stays useful during an outage.
# They deliberately do NOT call _require_ready(): a reviewed destination is a
# fact about data/navigation.yaml, which is loaded at import and needs no vector
# store, no embedder and no provider. Gating them on full readiness is what made
# the flagship page-finder die whenever the corpus or the model was unavailable
# — which is most of the time, by design, until an approved corpus exists.
#
# Rate limiting still applies (they are public and unauthenticated); the daily
# neuron budget does not, because nothing here reaches a metered provider.
class NavigationResolveRequest(BaseModel):
    """A question to match against the reviewed intent phrases."""

    message: str = Field(min_length=1)
    locale: Literal["ar", "en"] | None = None
    session_id: str | None = Field(default=None, max_length=100)

    @field_validator("message")
    @classmethod
    def _bound_message(cls, value: str) -> str:
        if len(value) > settings.max_message_chars:
            raise ValueError(f"message exceeds {settings.max_message_chars} characters")
        return value


@app.get("/v2/navigation/actions")
def navigation_actions(request: Request):
    """Every enabled destination, for a client to render and to cache offline.

    The extension bundles its own copy of this list so the page-finder works
    with the backend entirely unreachable. This route is the fresher answer when
    the network is available — flipping `enabled: false` here withdraws a bad
    destination in one redeploy, without waiting on a Chrome Web Store review.
    That is the incident rollback for a bad URL, so it must not be gated on
    anything that can itself be broken.
    """
    ratelimit.check(ratelimit.client_ip(request), None)
    actions = [a for a in navigation.load_registry().values() if a.enabled]
    return {
        # A client compares this to its bundled copy and prefers the newer.
        "version": navigation.registry_version(),
        "actions": [
            {
                "id": a.id,
                "label_ar": a.label_ar,
                "label_en": a.label_en,
                "url": a.destination,
                "auth_required": a.auth_required,
                "requires_confirmation": a.requires_confirmation,
                "intents_ar": a.intents_ar,
                "intents_en": a.intents_en,
                "min_confidence": a.min_confidence,
            }
            for a in actions
        ],
        "pending": navigation.declared_count() - len(actions),
    }


@app.post("/v2/navigation/resolve")
def navigation_resolve(req: NavigationResolveRequest, request: Request):
    """Match a question to one reviewed action, or to nothing.

    Nothing is the common and correct answer. The resolver is pure phrase
    containment over reviewed strings (navigation._intent_match), so the model
    is not involved and cannot be: the most this route can return is an id a
    human already approved, which is the ADR-002 rule stated as an endpoint.
    """
    ratelimit.check(ratelimit.client_ip(request), req.session_id)
    action = navigation.resolve(req.message, None, req.locale or "en")
    return {"action": action, "version": navigation.registry_version()}


# --- Admin dashboard --------------------------------------------------------
@app.get("/admin", include_in_schema=False)
def admin_page():
    """The operator console: 3D + process view and the calibration tab."""
    return FileResponse(_STATIC / "admin.html")


@app.get("/viz", include_in_schema=False)
def viz_redirect():
    """The dashboard moved to /admin; keep the old path working."""
    return RedirectResponse("/admin")


@app.get("/admin/points", dependencies=_ADMIN)
def admin_points():
    """The stored chunks projected to 3D via PCA.

    Returns an empty projection rather than 500 when no collection exists. A
    fresh deployment has no corpus by design, and that is precisely when an
    operator opens this page — a stack trace there says "broken" when the true
    answer is "nothing has been indexed yet".
    """
    if not vectorstore.collection_ready():
        return {"points": [], "explained_variance": [0.0, 0.0, 0.0],
                "corpus": "none-indexed"}
    return viz.points()


@app.get("/admin/chunks", dependencies=_ADMIN)
def admin_chunks():
    """How each raw document is split into chunks (current strategy)."""
    return viz.chunking()


@app.get("/admin/eval/golden", dependencies=_ADMIN)
def admin_eval_golden(judge: bool = False):
    """Run the full-pipeline golden-set eval (slow: one LLM call per case)."""
    return evaluation.run_golden(judge=judge)


@app.get("/admin/eval/chunking", dependencies=_ADMIN)
def admin_eval_chunking():
    """Run the chunk-size sweep + window-vs-structure comparison (slow)."""
    return evaluation.run_chunking_eval()


@app.get("/admin/eval/redteam", dependencies=_ADMIN)
def admin_eval_redteam():
    """Run the adversarial red-team suite through the live pipeline (slow)."""
    return evaluation.run_redteam()


@app.get("/admin/eval/threshold", dependencies=_ADMIN)
def admin_eval_threshold():
    """Sweep the grounding support-threshold over the golden set (slow)."""
    return evaluation.tune_threshold()


@app.post("/admin/query", dependencies=_ADMIN)
def admin_query(req: ChatRequest):
    """Embed a query and place it in the same 3D space as the chunks."""
    return viz.project_query(req.message)


@app.post("/admin/trace", dependencies=_ADMIN)
def admin_trace(req: ChatRequest):
    """Every retrieval-funnel stage (dense, BM25, fusion, rerank) for a query."""
    return trace(req.message)


@app.get("/admin/log", dependencies=_ADMIN)
def admin_log(limit: int = 200):
    """Recent interactions.

    In the default aggregate mode these carry verdicts, timings and source ids
    but no question or answer text — see chatlog.py. `summary` is the view an
    operator usually wants, and the one that stays meaningful in either mode.
    """
    return {"entries": chatlog.recent(limit), "summary": chatlog.summary()}


@app.get("/admin/usage", dependencies=_ADMIN)
def admin_usage():
    """Provider budget, concurrency and rate-limit posture."""
    return {
        "budget": budget.snapshot(),
        "concurrency": ratelimit.snapshot(),
        "llm": {"model": settings.llm_model, "circuit": llm.circuit_state()},
        "corpus": corpus.summary(),
    }


@app.post("/admin/log/purge", dependencies=_ADMIN)
def admin_log_purge():
    """Apply the retention period now, deleting entries past it."""
    return {"status": "ok", "removed": chatlog.purge_expired()}


@app.post("/admin/log/clear", dependencies=_ADMIN)
def admin_log_clear():
    """Wipe the chat interaction log."""
    chatlog.clear()
    return {"status": "ok", "entries": []}


# --- Admin: calibration + training ------------------------------------------
def _chunk_count() -> int | None:
    """Indexed-chunk count, or None if the vector store is unreachable."""
    try:
        from . import vectorstore
        return vectorstore.count()
    except Exception:
        return None


def _config_payload() -> dict:
    return {
        "spec": runtime_config.SPEC,
        "values": runtime_config.all_values(),
        "defaults": runtime_config.DEFAULTS,
        # Deployment settings (restart-only) shown read-only for context.
        "deployment": {
            "embed_model": settings.embed_model,
            "rerank_model": settings.rerank_model,
            "qdrant_url": settings.qdrant_url,
            "collection": settings.collection,
            "llm_base_url": settings.llm_base_url,
            "env_llm_model": settings.llm_model,
        },
        "chunks_indexed": _chunk_count(),
    }


@app.get("/admin/config", dependencies=_ADMIN)
def admin_get_config():
    """Calibration spec + live values (and read-only deployment settings)."""
    return _config_payload()


@app.post("/admin/config", dependencies=_ADMIN)
def admin_set_config(values: dict = Body(...)):
    """Update + persist calibration values; returns the full payload."""
    runtime_config.update(values)
    return _config_payload()


@app.post("/admin/config/reset", dependencies=_ADMIN)
def admin_reset_config():
    """Restore all calibration values to their defaults."""
    runtime_config.reset()
    return _config_payload()


@app.post("/admin/train", dependencies=_ADMIN)
def admin_train():
    """Rebuild the vector index from data/raw with the current chunk settings."""
    count = ingest.build_index()
    return {"status": "ok", "chunks_indexed": count,
            "strategy": runtime_config.get("chunk_strategy"),
            "chunk_target": runtime_config.get("chunk_target"),
            "chunk_overlap": runtime_config.get("chunk_overlap")}


def _sources(passages) -> list[dict]:
    """What the client shows under an answer: page, capture date, freshness.

    The canonical URL and `as_of` come from the source manifest, so a citation
    the student can click is the same page the model was shown — see
    generate._source_header, which builds the model-visible header from the same
    metadata.
    """
    out = []
    for _, meta in passages:
        entry = {
            "title": meta.get("title"),
            "source": meta.get("source"),
            "url": meta.get("url") or None,
            "as_of": (meta.get("as_of") or "")[:10] or None,
            "language": meta.get("language") or None,
        }
        if meta.get("stale") or source_policy.meta_is_stale(meta):
            entry["stale"] = True
        if meta.get("effective_to"):
            entry["effective_to"] = meta["effective_to"][:10]
        out.append(entry)
    return out


def _navigation_for(req: ChatRequest, passages=None) -> dict | None:
    """Resolve a reviewed navigation action, revalidating before it goes out.

    The resolver already returns registry entries only, so the second
    `validate_destination` call is redundant by construction — which is the
    point. It is the cheap invariant that catches a future edit making the
    resolver's output less trustworthy, on the one code path where being wrong
    changes the student's browser rather than just their information.
    """
    locale = req.locale or ("ar" if generate.localized("en", "ar", req.message) == "ar" else "en")
    try:
        action = navigation.resolve(req.message, passages, locale)
    except Exception:  # noqa: BLE001 — navigation must never break answering
        log.exception("navigation resolution failed")
        return None
    if not action:
        return None
    if navigation.validate_destination(action["url"]) is None:
        log.error("resolver produced an invalid destination for action %s", action.get("id"))
        return None
    return action


def _abstain(question: str, log: dict) -> dict:
    """No retrieved source cleared the relevance floor — say so, spend no tokens.

    Reaching the LLM with an empty source list invites it to answer from
    parametric memory, which is the one thing a grounded assistant must not do.
    """
    text = generate.localized(generate.NO_SOURCES, generate.NO_SOURCES_AR, question)
    chatlog.record(question, text, verdict="abstained", **log)
    return {
        "answer": text,
        "repaired": False,
        "abstained": True,
        "sources": [],
        "grounding": {"verdict": "abstained"},
        "links": [],
    }


@app.post("/v2/chat")
@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    request_id = _admit(request, req)
    _log = dict(user=req.user, session=req.session_id, client=req.client,
                request_id=request_id)
    # "Who made this?" — a fixed credit answer with team photos, no retrieval/LLM.
    if about.match(req.message):
        ans = about.response(req.message)
        chatlog.record(req.message, ans, verdict="about", **_log)
        return {
            "answer": ans, "repaired": False, "sources": [],
            "grounding": {"verdict": "about"}, "links": [], "images": about.IMAGES,
        }
    # Input guardrail: decline out-of-scope / personal-without-auth / harmful
    # before spending a retrieval + LLM call on them.
    scope = guardrails.check_scope(req.message)
    if not scope["allowed"]:
        chatlog.record(req.message, scope["response"], blocked=scope["category"], **_log)
        body = {
            "answer": scope["response"],
            "repaired": False,
            "blocked": scope["category"],
            "sources": [],
            "grounding": {"verdict": "blocked"},
            "links": [],
        }
        # A refused transaction still deserves the page the student can do it on
        # themselves — refusing and offering are not in tension.
        action = _navigation_for(req)
        if action:
            body["navigation"] = action
        return body
    # Conversation memory: retrieval sees a standalone rewrite of follow-ups;
    # generation sees the actual prior turns.
    history = _bounded_history(req)
    query = generate.condense(req.message, history)
    passages = retrieve(query)
    if not passages:
        return _abstain(req.message, _log)
    # Untrusted-source defense: flag AND redact instruction-override spans so the
    # model never sees them; generate + ground against the sanitized text.
    clean, injection = guardrails.sanitize(passages)
    started = time.monotonic()
    with ratelimit.generation_slot():
        draft = answer(req.message, clean, history)
    # Ground-check the text the student actually sees, not the pre-repair draft.
    final, report, repaired = generate.finalize(draft, clean, req.message)
    chatlog.record(req.message, final, verdict=report.get("verdict"),
                   repaired=repaired, injection=injection["detected"],
                   sources=[m.get("source") for _, m in passages],
                   latency_ms=(time.monotonic() - started) * 1000, **_log)
    # Build the page links from the cited (raw) text first, then strip the [n]
    # markers from what the student actually sees.
    page_links = links.links_for(passages, final)
    return {
        "answer": citations.strip(final),
        "repaired": repaired,
        "sources": _sources(passages),
        "grounding": report,
        # Citation coverage, stale sources, contradictory effective windows —
        # things every sentence can pass individually while the answer as a
        # whole still misleads.
        "checks": answer_checks.run(final, passages, report),
        "injection": injection,
        # Deterministic page links for the cited docs (citation-aware; built from
        # data/links.yaml, never emitted by the model).
        "links": page_links,
        # Reviewed navigation action, or absent. Never a model-produced URL.
        **({"navigation": nav} if (nav := _navigation_for(req, passages)) else {}),
    }


@app.post("/v2/chat/stream")
@app.post("/chat/stream")
def chat_stream_route(req: ChatRequest, request: Request):
    """Stream the answer as Server-Sent Events.

    The scope guardrail runs first: a blocked request emits a single `blocked`
    event and stops. Otherwise retrieval runs (so citations are known up front),
    we send the sources as the opening event (plus an `injection` event if a
    retrieved chunk looks adversarial), then stream the answer token-by-token.
    Once the full answer is in hand we run the grounding guardrail and send its
    verdict, then a final done event carrying the request id.

    Event order is part of the contract: sources → [injection] → token* →
    grounding → [repair] → links → [navigation] → done. Clients must ignore
    event types they do not recognise, so a later release can add one without
    breaking a published extension.

    Admission (readiness, rate limit, budget) happens here, before the response
    starts. Once the stream is open the only way to report a refusal is an
    `error` event the client may already have rendered tokens ahead of.
    """
    request_id = _admit(request, req)
    scope = guardrails.check_scope(req.message)
    _log = dict(user=req.user, session=req.session_id, client=req.client,
                request_id=request_id)
    done = json.dumps({"type": "done", "request_id": request_id})

    # Take a generation slot BEFORE the response starts.
    #
    # This route had no concurrency cap at all — it was applied only to /chat,
    # which almost nothing calls, while the extension uses this one. A load test
    # against a stub provider found it: eight simultaneous requests against a cap
    # of two were all served.
    #
    # Acquired here rather than inside the generator so that BUSY is a clean 503
    # the client can retry, instead of an error event arriving after the sources
    # have already been rendered. Released in the generator's `finally`, which
    # runs on normal completion and on client disconnect alike.
    slot = ratelimit.generation_slot()
    slot.acquire()

    def events():
        try:
            yield from _stream_events()
        finally:
            # Runs on normal completion, on an exception, and on client
            # disconnect (Starlette closes the generator, raising GeneratorExit).
            # A slot leaked here would permanently shrink capacity.
            slot.release()

    def _stream_events():
        # "Who made this?" — fixed credit answer + team photos, then stop.
        if about.match(req.message):
            ans = about.response(req.message)
            chatlog.record(req.message, ans, verdict="about", **_log)
            yield f"data: {json.dumps({'type': 'about', 'answer': ans, 'images': about.IMAGES})}\n\n"
            yield f"data: {done}\n\n"
            return
        # Blocked input: send the decline as the answer and stop — no retrieval.
        if not scope["allowed"]:
            chatlog.record(req.message, scope["response"], blocked=scope["category"], **_log)
            yield f"data: {json.dumps({'type': 'blocked', 'category': scope['category'], 'answer': scope['response']})}\n\n"
            # A refused transaction still gets the page to do it on.
            blocked_action = _navigation_for(req)
            if blocked_action:
                yield f"data: {json.dumps({'type': 'navigation', 'action': blocked_action})}\n\n"
            yield f"data: {done}\n\n"
            return

        # Conversation memory: retrieval sees a standalone rewrite of follow-ups;
        # generation sees the actual prior turns.
        history = _bounded_history(req)
        query = generate.condense(req.message, history)
        passages = retrieve(query)
        if not passages:
            # Nothing cleared the abstention floor. Emit the decline as the
            # answer and stop — no LLM call, so an unanswerable question costs
            # no quota.
            result = _abstain(req.message, _log)
            yield f"data: {json.dumps({'type': 'blocked', 'category': 'no_sources', 'answer': result['answer']})}\n\n"
            yield f"data: {done}\n\n"
            return
        yield f"data: {json.dumps({'type': 'sources', 'sources': _sources(passages)})}\n\n"
        # Flag AND redact instruction-override spans before they reach the model.
        clean, injection = guardrails.sanitize(passages)
        if injection["detected"]:
            yield f"data: {json.dumps({'type': 'injection', 'injection': injection})}\n\n"
        try:
            # Keep the RAW deltas (with [n] citations) for grounding + links, but
            # stream the citation-free text to the client via strip_stream.
            parts = []

            def raw_deltas():
                for delta in answer_stream(req.message, clean, history):
                    parts.append(delta)
                    yield delta

            first = True
            for shown in citations.strip_stream(raw_deltas()):
                if first:
                    readiness.mark("first_token")
                    first = False
                yield f"data: {json.dumps({'type': 'token', 'text': shown})}\n\n"
            draft = "".join(parts)
            # finalize() re-checks the repaired text, so the verdict sent to the
            # client describes what the client will display.
            final, report, repaired = generate.finalize(draft, clean, req.message)
            checks = answer_checks.run(final, passages, report)
            yield f"data: {json.dumps({'type': 'grounding', 'grounding': report, 'checks': checks})}\n\n"
            # The draft was already streamed; if the guardrail rejected it, tell
            # the client to swap in the safe (citation-free) text.
            if repaired:
                yield f"data: {json.dumps({'type': 'repair', 'answer': citations.strip(final)})}\n\n"
            # Page links last (after the answer settles) so they're keyed on the
            # citations actually present in the final text, mirroring grounding.
            yield f"data: {json.dumps({'type': 'links', 'links': links.links_for(passages, final)})}\n\n"
            # Navigation last of the content events: it is an offer to change
            # browser state, so it should follow the answer that justifies it.
            action = _navigation_for(req, passages)
            if action:
                yield f"data: {json.dumps({'type': 'navigation', 'action': action})}\n\n"
            chatlog.record(req.message, final, verdict=report.get("verdict"),
                           repaired=repaired, injection=injection["detected"], **_log)
        except errors.PublicError as exc:
            # A clean error event rather than aborting the socket (which the
            # browser surfaces as an opaque "Failed to fetch"). The student gets
            # the stable code; the provider's actual message stays in the log.
            log.warning("chat stream failed: %s", exc)
            yield f"data: {json.dumps({'type': 'error', **exc.public()})}\n\n"
        except Exception as exc:  # noqa: BLE001 — last line before the socket
            log.exception("unexpected chat stream failure")
            internal = errors.INTERNAL(detail=f"{type(exc).__name__}: {exc}")
            yield f"data: {json.dumps({'type': 'error', **internal.public()})}\n\n"
        yield f"data: {done}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
