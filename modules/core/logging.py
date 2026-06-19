"""Structured logging facade (implements the Logger contract)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


class Logger:
    _SENSITIVE_KEYS = {"token", "secret", "password", "authorization"}

    def _sanitize(self, fields: dict) -> dict:
        sanitized: dict[str, object] = {}
        for key, value in fields.items():
            if any(s in key.lower() for s in self._SENSITIVE_KEYS):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized

    def _emit(self, level: str, event: str, **fields) -> None:
        record = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'level': level,
            'event': event,
            **self._sanitize(fields),
        }
        print(json.dumps(record), file=sys.stderr)

    def info(self, event: str, **fields) -> None:
        self._emit('info', event, **fields)

    def error(self, event: str, **fields) -> None:
        self._emit('error', event, **fields)


log = Logger()
