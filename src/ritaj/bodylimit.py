"""A real request-body cap, enforced on the bytes rather than on a header.

The first version checked `Content-Length` and stopped there. A client that
sends `Transfer-Encoding: chunked` declares no length at all, so the check was
skipped entirely and the body was buffered in full by whatever read it next —
which is the shape of a trivial memory-exhaustion request against a 2-vCPU host.

This is raw ASGI rather than a `BaseHTTPMiddleware`, because the cap has to sit
on the receive channel: it must count bytes as they arrive and refuse *before*
the application awaits a complete body. `BaseHTTPMiddleware` only hands you the
request after that point.

The whole body is buffered here, which is safe precisely because it is bounded:
the buffer can never exceed `max_bytes` (32 KB by default), and the request is
refused the moment it would.
"""

from __future__ import annotations

import json
import logging

from . import errors

log = logging.getLogger("ritaj.bodylimit")

_METHODS_WITH_BODIES = {"POST", "PUT", "PATCH"}


class BodySizeLimitMiddleware:
    """Refuse a request whose body exceeds `max_bytes`, declared or not."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in _METHODS_WITH_BODIES:
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope.get("headers") or []}
        declared = headers.get(b"content-length")
        # Fast path: an honest oversized request is refused without reading it.
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    return await self._reject(scope, send, f"content-length {int(declared)}")
            except ValueError:
                pass  # malformed header; fall through to counting actual bytes

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # client gave up; nothing to answer
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                # Counted, not declared: this is the path a chunked request takes.
                return await self._reject(scope, send, f"streamed {len(body)}+ bytes")
            if not message.get("more_body", False):
                break

        # Replay the buffered body to the application exactly once.
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)

    async def _reject(self, scope, send, detail: str) -> None:
        error = errors.REQUEST_TOO_LARGE(detail=detail)
        log.warning("rejected oversized body on %s: %s", scope.get("path"), detail)
        payload = json.dumps(error.public()).encode()
        await send({
            "type": "http.response.start",
            "status": error.http_status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                # The browser must be able to read this response, so the CORS
                # middleware has to sit OUTSIDE this one — see api.py's ordering
                # note. Without that, an oversized request surfaces as an opaque
                # CORS failure instead of a 413 the client can explain.
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": payload})
