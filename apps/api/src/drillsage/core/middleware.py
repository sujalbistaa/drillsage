"""Pure-ASGI middleware: correlation ids, access logging, and Prometheus metrics.

Pure ASGI (not `BaseHTTPMiddleware`) so streaming responses such as SSE alert feeds pass
through without buffering.
"""

import re
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from drillsage.core.logging import bind_request_id, get_logger

REQUEST_ID_HEADER = "x-request-id"
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.encode("latin-1")
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = get_logger("drillsage.access")

HTTP_REQUESTS = Counter(
    "drillsage_http_requests_total",
    "HTTP requests by route template, method and status class",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "drillsage_http_request_duration_seconds",
    "HTTP request latency by route template",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

_UNMATCHED_ROUTE = "<unmatched>"
_QUIET_PATHS = frozenset({"/healthz", "/metrics"})


def _incoming_request_id(scope: Scope) -> str:
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for name, value in headers:
        if name == _REQUEST_ID_HEADER_BYTES:
            candidate = value.decode("latin-1")
            if _VALID_REQUEST_ID.match(candidate):
                return candidate
    return uuid.uuid4().hex


def _route_template(scope: Scope) -> str:
    """Use the matched route template (e.g. /wells/{id}) to keep metric cardinality bounded."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else _UNMATCHED_ROUTE


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        bind_request_id(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            method = scope["method"]
            route = _route_template(scope)
            HTTP_REQUESTS.labels(method, route, f"{status_code // 100}xx").inc()
            HTTP_LATENCY.labels(method, route).observe(elapsed)
            if scope["path"] not in _QUIET_PATHS:
                log.info(
                    "http_request",
                    method=method,
                    path=scope["path"],
                    route=route,
                    status=status_code,
                    duration_ms=round(elapsed * 1000, 2),
                )
