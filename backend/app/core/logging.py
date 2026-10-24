"""Request-scoped logging and safe error translation.

Two rules this module exists to enforce:

* A client never sees a Python traceback or an internal path. It gets a short
  message and a request id.
* The server log always carries that same request id, so a user reporting
  "error, id 3f2a..." can be traced without guessing.
"""

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

# Substrings that must never reach a log line or an API response.
_REDACT_KEYS = {
    "password",
    "password_hash",
    "secret",
    "token",
    "credential",
    "code_hash",
    "credential_hash",
    "device_secret",
    "authorization",
}


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)


def get_request_id() -> Optional[str]:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_pam_configured", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    handler.addFilter(RequestIdFilter())
    handler._pam_configured = True

    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Uvicorn installs its own handlers; route them through ours so every line
    # carries the request id.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def redact(data: dict) -> dict:
    """Drop sensitive values before anything is written to audit or logs."""
    clean = {}
    for key, value in (data or {}).items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in _REDACT_KEYS):
            clean[key] = "[redacted]"
        elif isinstance(value, dict):
            clean[key] = redact(value)
        else:
            clean[key] = value
    return clean
