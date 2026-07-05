"""Strip inline source citations ([n]) from the student-facing answer text.

The system prompt tells the model to cite sources inline as [1], [2] — and those
markers must survive the whole pipeline: grounding.py verifies them and links.py
maps each to a page URL. So we remove them only at the very end, for display.

Two entry points:
  strip()        — full text. Used for the non-streaming /chat response and for
                   the repair/fallback text.
  strip_stream() — a stateful filter over the token stream. It holds back a
                   trailing run of [n] markers (which may still be growing — e.g.
                   "[1]" before ", [2]" has streamed in, or "[1" before its "]")
                   until it resolves, so a citation split across tokens is never
                   half-shown.

This mirrors the client-side stripCitations (ritaj-student-portal/src/api/chat.ts).
Doing it server-side too means a stale/cached client — or any raw API consumer —
gets clean text regardless.
"""

import re
from collections.abc import Iterable, Iterator

# A run of one or more [n] markers joined by spaces / commas (English , or Arabic ،).
_RUN = re.compile(r"\s*\[\d+\](?:\s*[،,]\s*\[\d+\])*")

# A trailing region that might still be growing into a citation run: a sequence
# of [n] markers joined by separators (so the whole "[1], [2], [3]" run is held
# as a unit — never cut between a separator and the next marker, which would leak
# the comma), a dangling separator, and an optional still-open "[12".
_TRAIL = re.compile(r"(?:\s*[،,]?\s*\[\d+\])*(?:\s*[،,])?\s*(?:\[\d*)?$")


def strip(text: str) -> str:
    """Remove citation markers/runs from a complete piece of text and tidy up."""
    text = _RUN.sub("", text)
    text = re.sub(r"\s*\[\d*$", "", text)          # a trailing, never-closed marker
    text = re.sub(r"[ \t]+([.!?؟،,])", r"\1", text)  # space a removed marker left
    text = re.sub(r"[ \t]{2,}", " ", text)         # collapse doubled spaces
    return text


def strip_stream(deltas: Iterable[str]) -> Iterator[str]:
    """Yield citation-free deltas from a raw token stream.

    Emits everything up to a trailing region that could still become a citation
    run, holding that tail until the next token (or end of stream) resolves it.
    """
    buf = ""
    for delta in deltas:
        buf += delta
        m = _TRAIL.search(buf)
        cut = m.start() if m else len(buf)
        emit, buf = buf[:cut], buf[cut:]
        if emit:
            yield strip(emit)
    if buf:
        yield strip(buf)
