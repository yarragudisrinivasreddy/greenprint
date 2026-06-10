"""Structured JSON logging for GreenPrint.

Cloud Run ingests stdout; emitting one JSON object per line lets Cloud
Logging index severity and module without custom parsers. Each module
requests its own logger so log origin is always attributable.
"""
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root handler exactly once."""
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)


def get_logger(module_name: str) -> logging.Logger:
    """Return the per-module logger used across GreenPrint services."""
    return logging.getLogger(module_name)
