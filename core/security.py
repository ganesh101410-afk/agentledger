"""Small, dependency-free protections: rate limiting, body size cap and security headers."""

from __future__ import annotations

import json
import time
from collections import deque

from .config import get_settings

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    b"content-security-policy": CSP.encode(),
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
    b"cross-origin-opener-policy": b"same-origin",
}


class RateLimiter:
    """Sliding-window limiter keyed by client. In memory, so it is per process."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._max_keys = max_keys

    def check(self, key: str, limit: int, window: float = 60.0, now: float | None = None) -> float | None:
        """Record a hit. Returns None if allowed, else the seconds to wait."""
        if limit <= 0:
            return None
        now = time.monotonic() if now is None else now
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window:
            hits.popleft()
        if len(hits) >= limit:
            return max(0.0, window - (now - hits[0]))
        hits.append(now)
        if len(self._hits) > self._max_keys:
            self._prune(now, window)
        return None

    def _prune(self, now: float, window: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= window]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


def client_ip(headers, peer: str | None, trust_proxy: bool) -> str:
    """The last X-Forwarded-For hop is the one our own proxy appended; earlier hops are client-controlled."""
    if trust_proxy:
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip() or (peer or "unknown")
    return peer or "unknown"


async def _send_json(send, status: int, detail: str, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *(extra or [])]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BodyLimitMiddleware:
    """Reject oversized request bodies, whether or not the client declares a Content-Length."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = get_settings().max_body_bytes
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            return await _send_json(send, 413, "Request body too large.")

        received = 0
        rejected = False

        async def limited_receive():
            # Answer 413 ourselves and report a disconnect, so the app stops reading instead of
            # turning an exception here into a generic 400.
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request" and not rejected:
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    await _send_json(send, 413, "Request body too large.")
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not rejected:  # once we have answered, drop whatever the app tries to send
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not rejected:
                raise


class SecurityHeadersMiddleware:
    """Add hardening headers to every response, and stop browsers caching API responses."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_api = scope["path"].startswith("/api/")
        request_headers = dict(scope["headers"])
        secure = scope.get("scheme") == "https" or (
            get_settings().trust_proxy and request_headers.get(b"x-forwarded-proto", b"").split(b",")[-1].strip() == b"https"
        )

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                headers = list(message.get("headers", []))
                headers += [(k, v) for k, v in SECURITY_HEADERS.items() if k not in existing]
                if is_api and b"cache-control" not in existing:
                    headers.append((b"cache-control", b"no-store"))
                if secure:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
