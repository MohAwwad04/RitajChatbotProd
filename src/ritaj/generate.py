"""Generation: retrieved chunks + question -> grounded, cited answer.

The system prompt is the core hallucination defense (plan section 8): answer
only from the provided sources, cite them, reply in the user's language, and
admit when the answer isn't in the sources.
"""

from .llm import chat

SYSTEM_PROMPT = """You are the Ritaj Assistant, the official Birzeit University student helper.

Rules:
- Answer ONLY using the numbered sources provided. Do not use outside knowledge.
- If the sources do not contain the answer, say you don't know and point the
  student to the relevant office (e.g. Registration or the IT helpdesk).
- Always cite the sources you used, inline, as [1], [2], etc.
- Reply in the user's language (Arabic or English), matching their tone.
- Be concise; use numbered steps for procedures.
- Never invent policies, dates, fees, or contacts."""


def build_user_prompt(question: str, passages: list[tuple[str, dict]]) -> str:
    blocks = []
    for i, (doc, meta) in enumerate(passages, start=1):
        title = meta.get("title", "source")
        source = meta.get("source", "")
        blocks.append(f"[{i}] {title} — {source}\n{doc}")
    sources = "\n\n".join(blocks) if blocks else "(no sources found)"
    return f"Sources:\n{sources}\n\nQuestion: {question}"


def answer(question: str, passages: list[tuple[str, dict]]) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, passages)},
    ]
    return chat(messages)
