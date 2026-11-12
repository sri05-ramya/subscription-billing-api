"""Structured JSON logging with a request ID on every line."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Holds the current request's tracking number (set by the middleware in Step 13.2)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Standard fields Python puts on every log record; we skip these when adding extras
_STANDARD_FIELDS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        # Anything passed with extra={...} becomes its own field
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Our middleware logs every request, so turn off uvicorn's duplicate access log
    logging.getLogger("uvicorn.access").disabled = True