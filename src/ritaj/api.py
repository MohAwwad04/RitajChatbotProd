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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (
    about, adminauth, answer_checks, bootstrap, chatlog, citations, config, corpus,
    errors, evaluation, generate, grounding, guardrails, ingest, links, llm, readiness,
    runtime_config, source_policy, viz,
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

# The chat endpoints are called cross-origin by the Chrome extension (origin
# chrome-extension://<id>) and by the deployed web portal. No cookies or
# credentials are used, but the endpoint spends metered LLM quota, so production
# takes an explicit allowlist (config.allowed_origins) rather than a wildcard
# that lets any site on the internet bill this account. Development still
# resolves to "*" so unpacked extensions — whose origin changes on each reload —
# keep working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


class ChatRequest(BaseModel):
    message: str
    # Conversation memory: the client sends its prior turns with every request
    # (the server stays stateless — nothing is cached per chat server-side).
    history: list[ChatTurn] = Field(default_factory=list)
    # Optional client metadata, logged so the admin console can group a
    # conversation's turns and see who/where a question came from.
    session_id: str | None = None
    user: str | None = None
    client: str | None = None


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
def ready():
    """Readiness: can this instance actually answer a question right now?

    503 while initializing or failed, so a load balancer withholds traffic
    without the process being restarted. The body names the state and the
    startup timings, which is what makes a slow boot diagnosable after the fact.
    """
    snap = readiness.snapshot()
    body = {
        "status": "ready" if readiness.is_ready() else "not-ready",
        **snap,
        "corpus": corpus.summary(),
        "llm": {"model": settings.llm_model, "circuit": llm.circuit_state()},
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
    """The stored chunks projected to 3D via PCA."""
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
    """Recent chat interactions (what users asked + what the bot answered)."""
    return {"entries": chatlog.recent(limit)}


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


@app.post("/chat")
def chat(req: ChatRequest):
    _require_ready()
    _log = dict(user=req.user, session=req.session_id, client=req.client)
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
        return {
            "answer": scope["response"],
            "repaired": False,
            "blocked": scope["category"],
            "sources": [],
            "grounding": {"verdict": "blocked"},
            "links": [],
        }
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
    draft = answer(req.message, clean, history)
    # Ground-check the text the student actually sees, not the pre-repair draft.
    final, report, repaired = generate.finalize(draft, clean, req.message)
    chatlog.record(req.message, final, verdict=report.get("verdict"),
                   repaired=repaired, injection=injection["detected"], **_log)
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
    }


@app.post("/chat/stream")
def chat_stream_route(req: ChatRequest):
    """Stream the answer as Server-Sent Events.

    The scope guardrail runs first: a blocked request emits a single `blocked`
    event and stops. Otherwise retrieval runs (so citations are known up front),
    we send the sources as the opening event (plus an `injection` event if a
    retrieved chunk looks adversarial), then stream the answer token-by-token.
    Once the full answer is in hand we run the grounding guardrail and send its
    verdict, then a final done event.
    """
    _require_ready()
    scope = guardrails.check_scope(req.message)
    _log = dict(user=req.user, session=req.session_id, client=req.client)

    def events():
        # "Who made this?" — fixed credit answer + team photos, then stop.
        if about.match(req.message):
            ans = about.response(req.message)
            chatlog.record(req.message, ans, verdict="about", **_log)
            yield f"data: {json.dumps({'type': 'about', 'answer': ans, 'images': about.IMAGES})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        # Blocked input: send the decline as the answer and stop — no retrieval.
        if not scope["allowed"]:
            chatlog.record(req.message, scope["response"], blocked=scope["category"], **_log)
            yield f"data: {json.dumps({'type': 'blocked', 'category': scope['category'], 'answer': scope['response']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
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
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
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
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
