"""Structured JSON logging to stdout (collected by the hosting platform)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(payload, default=str)


def configure() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("doctracker")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
