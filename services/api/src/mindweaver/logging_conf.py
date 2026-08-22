"""Structured JSON logging with secret redaction.

Any secret registered via :func:`register_secret` (in practice the
configured ``SECURITY__SECRET_KEY``) is replaced by ``***`` in every log
line, so credentials never reach the output.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

REDACTED = "***"

_secrets: list[str] = []


def register_secret(secret: str) -> None:
    if secret and secret not in _secrets:
        _secrets.append(secret)


def clear_secrets() -> None:
    _secrets.clear()


def redact(text: str) -> str:
    if not text or not _secrets:
        return text
    for secret in _secrets:
        text = text.replace(secret, REDACTED)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = redact(str(request_id))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", *, secret: str | None = None) -> None:
    register_secret(secret or "")
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
