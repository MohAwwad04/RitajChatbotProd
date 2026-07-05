"""FastAPI orchestrator — the HTTP boundary for the assistant.

For the base this is a single non-streaming /chat route. Auth, streaming,
rate limiting, and guardrails get layered onto this same endpoint later
(plan sections 8 and 12).

Run:  uvicorn ritaj.api:app --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel

from .generate import answer
from .retrieve import retrieve

app = FastAPI(title="Ritaj Assistant", version="0.1.0")


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    passages = retrieve(req.message)
    text = answer(req.message, passages)
    return {
        "answer": text,
        "sources": [
            {"title": meta.get("title"), "source": meta.get("source")}
            for _, meta in passages
        ],
    }
