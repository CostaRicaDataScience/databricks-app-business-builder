"""Structured logger with sensitive field redaction."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


class Logger:
    sensitive_keys = {"token", "secret", "password", "authorization"}

    def _sanitize(self, fields: dict[str, object]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in fields.items():
            if any(k in key.lower() for k in self.sensitive_keys):
                out[key] = "***REDACTED***"
            else:
                out[key] = value
        return out

    def emit(self, level: str, event: str, **fields: object) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **self._sanitize(fields),
        }
        print(json.dumps(record), file=sys.stderr)

    def info(self, event: str, **fields: object) -> None:
        self.emit("info", event, **fields)

    def error(self, event: str, **fields: object) -> None:
        self.emit("error", event, **fields)


log = Logger()
