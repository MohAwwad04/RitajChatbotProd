"""LLM client — one thin wrapper over the OpenAI-compatible chat API.

Both Ollama (dev) and vLLM (prod) speak this exact protocol, so this code is
identical for both; only LLM_BASE_URL / LLM_MODEL change in .env.
"""

import json
from collections.abc import Iterator

import httpx

from . import runtime_config
from .config import settings


def _payload(messages: list[dict], temperature: float, max_tokens: int, stream: bool) -> dict:
    # llm_model is tunable from /admin; blank falls back to the .env default.
    return {
        "model": runtime_config.get("llm_model") or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def chat(messages: list[dict], temperature: float | None = None,
         max_tokens: int | None = None) -> str:
    """Send a chat completion request and return the assistant's text.

    temperature / max_tokens default to the live runtime values (tunable from
    /admin); low temperature suits a grounded, citation-bound assistant.
    """
    if temperature is None:
        temperature = runtime_config.get("temperature")
    if max_tokens is None:
        max_tokens = runtime_config.get("max_tokens")
    resp = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=_payload(messages, temperature, max_tokens, stream=False),
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_stream(
    messages: list[dict], temperature: float | None = None,
    max_tokens: int | None = None
) -> Iterator[str]:
    """Stream a chat completion, yielding text deltas as the model produces them.

    Both Ollama and vLLM emit the OpenAI Server-Sent-Events format: lines of
    `data: {json}`, each carrying an incremental `choices[0].delta.content`,
    terminated by `data: [DONE]`. We yield only the text pieces.
    """
    if temperature is None:
        temperature = runtime_config.get("temperature")
    if max_tokens is None:
        max_tokens = runtime_config.get("max_tokens")
    with httpx.stream(
        "POST",
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json=_payload(messages, temperature, max_tokens, stream=True),
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                yield delta
