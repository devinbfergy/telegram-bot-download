from __future__ import annotations
import json
import logging
import sys
from datetime import datetime
from app.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload = {
            "ts": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_DEF_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

_configured = False


def setup_logging(level: str | None = None, json_mode: bool | None = None) -> None:
    global _configured
    if _configured:  # idempotent
        return
    level = level or settings.LOG_LEVEL
    json_mode = settings.LOG_JSON if json_mode is None else json_mode
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    if json_mode:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_DEF_FORMAT))
    root.handlers.clear()
    root.addHandler(handler)
    _configured = True


get_logger = logging.getLogger
