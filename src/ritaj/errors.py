"""Public error codes — what a client is allowed to be told.

Before this, a provider failure was streamed to the browser as
`{"type":"error","message": str(exc)}`, which could carry the upstream URL (with
the Cloudflare account id in the path), an httpx traceback string, or a provider
error body. Students see the code; operators see the detail in the protected log,
correlated by request id.

Each code carries a bilingual, fact-free student-facing message. Fact-free is
deliberate: an error message is emitted exactly when the system is not working
properly, so it must not assert anything (a deadline, a fee, an office hour) that
could be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PublicError(Exception):
    """An error safe to show a student, plus the private detail for the log."""

    code: str
    http_status: int
    en: str
    ar: str
    detail: str = ""          # never sent to the client
    retry_after: int | None = None  # seconds, when the client should try again

    def public(self, locale: str = "en") -> dict:
        body = {"code": self.code, "message": self.ar if locale == "ar" else self.en}
        if self.retry_after is not None:
            body["retry_after"] = self.retry_after
        return body

    def __str__(self) -> str:  # log/repr side only
        return f"{self.code}: {self.detail or self.en}"


def _err(code: str, status: int, en: str, ar: str):
    def make(detail: str = "", retry_after: int | None = None) -> PublicError:
        return PublicError(code=code, http_status=status, en=en, ar=ar,
                           detail=detail, retry_after=retry_after)

    return make


INITIALIZING = _err(
    "INITIALIZING", 503,
    "The assistant is still starting up. Please try again in a moment.",
    "المساعد ما زال قيد التشغيل. يرجى المحاولة بعد لحظات.",
)

NOT_READY = _err(
    "NOT_READY", 503,
    "The assistant is temporarily unavailable. Please try again shortly.",
    "المساعد غير متاح مؤقتاً. يرجى المحاولة بعد قليل.",
)

LLM_UNAVAILABLE = _err(
    "LLM_UNAVAILABLE", 503,
    "The answering service is unavailable right now. Please try again shortly.",
    "خدمة الإجابة غير متاحة حالياً. يرجى المحاولة بعد قليل.",
)

LLM_TIMEOUT = _err(
    "LLM_TIMEOUT", 504,
    "That took too long to answer. Please try again, or ask a shorter question.",
    "استغرقت الإجابة وقتاً طويلاً. حاول مرة أخرى أو اطرح سؤالاً أقصر.",
)

LLM_BUDGET_EXHAUSTED = _err(
    "LLM_BUDGET_EXHAUSTED", 429,
    "The assistant has reached today's usage limit. Please try again tomorrow, "
    "or use the linked Ritaj page directly.",
    "بلغ المساعد حد الاستخدام اليومي. يرجى المحاولة غداً أو استخدام صفحة ريتاج مباشرة.",
)

RATE_LIMITED = _err(
    "RATE_LIMITED", 429,
    "You're sending messages faster than the assistant can handle. "
    "Please wait a moment and try again.",
    "ترسل رسائل أسرع مما يستطيع المساعد معالجته. انتظر لحظة ثم حاول مجدداً.",
)

BUSY = _err(
    "BUSY", 503,
    "The assistant is handling too many questions right now. Please try again shortly.",
    "المساعد مشغول بعدد كبير من الأسئلة الآن. يرجى المحاولة بعد قليل.",
)

REQUEST_TOO_LARGE = _err(
    "REQUEST_TOO_LARGE", 413,
    "That message is too long. Please shorten it and try again.",
    "الرسالة طويلة جداً. يرجى اختصارها وإعادة المحاولة.",
)

INTERNAL = _err(
    "INTERNAL", 500,
    "Something went wrong on our side. Please try again.",
    "حدث خطأ لدينا. يرجى المحاولة مرة أخرى.",
)
