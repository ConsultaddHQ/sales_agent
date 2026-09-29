"""Observability shared by both services: structured logs, correlation IDs,
Sentry, and a periodic CPU/RAM sampler.

Correlation model: ElevenLabs' `conversation_id` is the single key that ties a
shopper's call together across the widget, webhook tools (search /
product-details), Supabase tables, Sentry events and Grafana traces. Each HTTP
request also gets a `request_id` so one webhook call can be found in the logs.

Everything here is opt-in via env vars and degrades to a no-op when a
dependency (sentry-sdk, psutil) or its config (SENTRY_DSN) is missing, so local
dev keeps working without accounts.

Env vars:
  LOG_LEVEL                  INFO (default) | DEBUG | WARNING ...
  LOG_FORMAT                 json (default — what Grafana Loki parses) | text
  SENTRY_DSN                 enables Sentry when set
  SENTRY_ENVIRONMENT         default "production"
  SENTRY_TRACES_SAMPLE_RATE  default 1.0 (pilot traffic is tiny; lower later)
  RELEASE                    release tag for Sentry (e.g. git SHA); optional
  SYSTEM_STATS_INTERVAL_SECONDS  default 60; 0 disables the CPU/RAM sampler
"""

import asyncio
import contextvars
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

# One mutable dict per request. Middleware creates it; endpoints fill in
# conversation_id once they've parsed the body. A dict (not two ContextVars)
# because endpoint code may run in a copied context (anyio task groups), and
# mutations to a shared object stay visible to the middleware's access log.
_request_ctx: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "request_ctx", default=None
)

_SERVICE_NAME = "unknown"
_sentry_enabled = False


# ── Logging ────────────────────────────────────────────────────────────────

class _ContextFilter(logging.Filter):
    """Stamps every record with service + the current request's correlation IDs."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _request_ctx.get() or {}
        record.service = _SERVICE_NAME
        record.request_id = ctx.get("request_id")
        record.conversation_id = ctx.get("conversation_id")
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": getattr(record, "service", _SERVICE_NAME),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "conversation_id"):
            val = getattr(record, key, None)
            if val:
                out[key] = val
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            out.update(fields)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s - %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = []
        cid = getattr(record, "conversation_id", None)
        if cid:
            extras.append(f"cid={cid}")
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            extras.extend(f"{k}={v}" for k, v in fields.items())
        return f"{base} | {' '.join(extras)}" if extras else base


def setup_logging(service: str) -> logging.Logger:
    """Configure the root logger once per process. Returns the service logger."""
    global _SERVICE_NAME
    _SERVICE_NAME = service

    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    fmt = os.getenv("LOG_FORMAT", "json").lower()
    handler.setFormatter(_JsonFormatter() if fmt == "json" else _TextFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    # uvicorn's own access log duplicates our access line; keep its errors only.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx logs every request line at INFO (Supabase calls) — noise on the hot path.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(service)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """One structured line: `event` is a stable dotted name (e.g. "search.completed")
    that dashboards and alerts key on; `fields` become top-level JSON keys."""
    logger.log(level, event, extra={"fields": {"event": event, **fields}})


# ── Correlation ────────────────────────────────────────────────────────────

def bind_conversation(conversation_id: Optional[str]) -> None:
    """Attach the ElevenLabs conversation_id to the current request's logs + Sentry scope."""
    if not conversation_id:
        return
    ctx = _request_ctx.get()
    if ctx is not None:
        ctx["conversation_id"] = conversation_id
    if _sentry_enabled:
        import sentry_sdk
        sentry_sdk.set_tag("conversation_id", conversation_id)


def current_request_id() -> Optional[str]:
    ctx = _request_ctx.get()
    return ctx.get("request_id") if ctx else None


def _client_ip(scope: Dict[str, Any]) -> str:
    for name, value in scope.get("headers") or []:
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "?"


class CorrelationMiddleware:
    """Pure-ASGI middleware (no BaseHTTPMiddleware body buffering):
    - assigns request_id (reuses an inbound X-Request-Id, e.g. from the proxy)
    - picks up X-Conversation-Id if the caller sent one
    - echoes X-Request-Id on the response
    - writes one `http.request` access line with status + duration
    """

    def __init__(self, app, quiet_paths: tuple = ("/health",)):
        self.app = app
        self.quiet_paths = quiet_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        ctx: Dict[str, Any] = {
            "request_id": headers.get("x-request-id") or uuid.uuid4().hex[:16],
            "conversation_id": headers.get("x-conversation-id") or None,
        }
        token = _request_ctx.set(ctx)
        if ctx["conversation_id"]:
            bind_conversation(ctx["conversation_id"])

        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", ctx["request_id"].encode("latin-1"))
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            status = status_holder["status"]
            level = logging.WARNING if status >= 500 else logging.INFO
            if path in self.quiet_paths and status < 400:
                level = logging.DEBUG
            log_event(
                logging.getLogger(_SERVICE_NAME), "http.request", level,
                method=scope.get("method"), path=path, status=status,
                duration_ms=int((time.perf_counter() - started) * 1000),
                client_ip=_client_ip(scope),
            )
            _request_ctx.reset(token)


# ── Sentry ─────────────────────────────────────────────────────────────────

def init_sentry(service: str) -> bool:
    """Initialise Sentry if SENTRY_DSN is set and sentry-sdk is installed.
    FastAPI/Starlette integrations auto-enable, so unhandled exceptions and
    request performance traces are captured with no further code."""
    global _sentry_enabled
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger(service).warning("SENTRY_DSN set but sentry-sdk not installed — skipping")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("RELEASE") or None,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0")),
        send_default_pii=False,
        server_name=service,
    )
    sentry_sdk.set_tag("service", service)
    _sentry_enabled = True
    logging.getLogger(service).info("Sentry initialised")
    return True


def capture_exception(exc: BaseException, **tags: Any) -> None:
    """Report a handled exception (one we recovered from) to Sentry, if enabled."""
    if not _sentry_enabled:
        return
    import sentry_sdk
    with sentry_sdk.new_scope() as scope:
        for k, v in tags.items():
            scope.set_tag(k, v)
        sentry_sdk.capture_exception(exc)


# ── System stats (answers "is the 2 GB Lightsail box the bottleneck?") ──────

async def run_system_stats_logger(logger: logging.Logger) -> None:
    """Log CPU / RAM / swap / load every SYSTEM_STATS_INTERVAL_SECONDS.
    Graph `system.stats` in Grafana next to search p95 to see whether slow
    searches line up with CPU saturation or swapping."""
    interval = float(os.getenv("SYSTEM_STATS_INTERVAL_SECONDS", "60"))
    if interval <= 0:
        return
    try:
        import psutil
    except ImportError:
        logger.warning("psutil not installed — system.stats sampler disabled")
        return

    proc = psutil.Process()
    psutil.cpu_percent(None)
    proc.cpu_percent(None)
    while True:
        await asyncio.sleep(interval)
        try:
            vm = psutil.virtual_memory()
            sw = psutil.swap_memory()
            log_event(
                logger, "system.stats",
                cpu_pct=psutil.cpu_percent(None),
                proc_cpu_pct=proc.cpu_percent(None),
                proc_rss_mb=int(proc.memory_info().rss / 1_048_576),
                mem_available_mb=int(vm.available / 1_048_576),
                mem_used_pct=vm.percent,
                swap_used_mb=int(sw.used / 1_048_576),
                load1=round(os.getloadavg()[0], 2),
            )
        except Exception as e:  # never let telemetry kill the loop
            logger.debug(f"system.stats sample failed: {e}")
