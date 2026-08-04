"""FastAPI orchestrator — the HTTP boundary for the assistant.

Routes group into three surfaces:
  • Student portal  — GET / serves the React SPA; POST /chat[/stream] answer it.
  • Admin dashboard — GET /admin is the operator console (3D + process view and a
    calibration tab); /admin/* powers it (viz data, evals, config, training).
  • /health.

Run:  uvicorn ritaj.api:app --reload --app-dir src
"""

import json
import secrets as _secrets
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import about, adminauth, chatlog, citations, evaluation, generate, grounding, guardrails, ingest, links, runtime_config, viz
from .config import settings
from .generate import answer, answer_stream, repair
from .retrieve import retrieve, trace

app = FastAPI(title="Ritaj Assistant", version="0.1.0")

# The chat endpoints are called cross-origin by the Chrome extension (origin
# chrome-extension://<id>) and potentially by other front-ends on custom
# domains. No cookies/credentials are used, so a wildcard is safe here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health")
def health():
    return {"status": "ok"}


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
    return [
        {"title": meta.get("title"), "source": meta.get("source")}
        for _, meta in passages
    ]


@app.post("/chat")
def chat(req: ChatRequest):
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
    # Untrusted-source defense: flag AND redact instruction-override spans so the
    # model never sees them; generate + ground against the sanitized text.
    clean, injection = guardrails.sanitize(passages)
    draft = answer(req.message, clean, history)
    report = grounding.check(draft, clean)
    final, repaired = repair(draft, report)
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

            for shown in citations.strip_stream(raw_deltas()):
                yield f"data: {json.dumps({'type': 'token', 'text': shown})}\n\n"
            draft = "".join(parts)
            report = grounding.check(draft, clean)
            yield f"data: {json.dumps({'type': 'grounding', 'grounding': report})}\n\n"
            # The draft was already streamed; if the guardrail rejects it, tell
            # the client to swap in the safe (citation-free) fallback.
            final, repaired = repair(draft, report)
            if repaired:
                yield f"data: {json.dumps({'type': 'repair', 'answer': citations.strip(final)})}\n\n"
            # Page links last (after the answer settles) so they're keyed on the
            # citations actually present in the final text, mirroring grounding.
            yield f"data: {json.dumps({'type': 'links', 'links': links.links_for(passages, final)})}\n\n"
            chatlog.record(req.message, final, verdict=report.get("verdict"),
                           repaired=repaired, injection=injection["detected"], **_log)
        except Exception as exc:
            # Emit a clean error event rather than aborting the socket (which the
            # browser would surface as an opaque "Failed to fetch").
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
