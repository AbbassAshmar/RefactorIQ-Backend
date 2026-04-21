from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from app.config import settings


def configure_logging() -> None:
    base_dir = Path(__file__).resolve().parents[2]
    log_dir = base_dir / settings.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    effective_level = (
        settings.LOG_LEVEL.upper()
        if settings.LOG_LEVEL
        else ("INFO" if settings.ENVIRONMENT == "production" else "DEBUG")
    )

    log_file = log_dir / settings.LOG_FILE_NAME
    error_log_file = log_dir / "error.log"

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": effective_level,
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "level": effective_level,
                    "filename": str(log_file),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
                "error_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "formatter": "default",
                    "level": "ERROR",
                    "filename": str(error_log_file),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": effective_level,
                "handlers": ["console", "file", "error_file"],
            },
            "loggers": {
                "uvicorn": {"handlers": ["console", "file", "error_file"], "level": effective_level, "propagate": False},
                "uvicorn.error": {"handlers": ["console", "file", "error_file"], "level": effective_level, "propagate": False},
                "uvicorn.access": {"handlers": ["console", "file"], "level": effective_level, "propagate": False},
            },
        }
    )