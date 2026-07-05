"""LLM client — one thin wrapper over the OpenAI-compatible chat API.

Both Ollama (dev) and vLLM (prod) speak this exact protocol, so this code is
identical for both; only LLM_BASE_URL / LLM_MODEL change in .env.
"""

import httpx

from .config import settings


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    """Send a chat completion request and return the assistant's text.

    Low temperature by default: for a grounded, citation-bound assistant we
    want faithful answers, not creative ones.
    """
    resp = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
