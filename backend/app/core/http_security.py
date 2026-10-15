"""Bound input before JSON parsing, including chunked bodies without Content-Length."""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestLimitsMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        limit = 16384 if scope["path"].startswith("/api/auth/") else self.max_bytes

        async def reject(status: int, detail: str) -> None:
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)

        declared = headers.get("content-length")
        if declared is not None:
            if not declared.isascii() or not declared.isdigit():
                await reject(400, "Invalid request size.")
                return
            # Compare lengths first to avoid converting unbounded attacker-controlled integers.
            normalized = declared.lstrip("0") or "0"
            if len(normalized) > len(str(limit)) or int(normalized) > limit:
                await reject(413, "Request is too large.")
                return
        if headers.get("content-encoding", "identity").lower() != "identity":
            await reject(415, "Compressed requests are not supported.")
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await reject(413, "Request is too large.")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if (
            body
            and headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            await reject(415, "Use application/json for request data.")
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def security_headers(production: bool) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
    }
    if production:
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, production: bool) -> None:
        self.app = app
        self.headers = [
            (key.lower().encode(), value.encode())
            for key, value in security_headers(production).items()
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(self.headers)
            await send(message)

        await self.app(scope, receive, send_with_headers)
