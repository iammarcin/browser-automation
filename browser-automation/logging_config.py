"""Centralized logging configuration for browser-automation container.

Matches the logging format used in storage-backend for consistency.
Logs to both stdout and persistent file in /storage/logs/.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

_ORIGINAL_LOG_RECORD_FACTORY = logging.getLogRecordFactory()
_LOG_RECORD_FACTORY_CONFIGURED = False
_LOGGING_CONFIGURED = False

# Path prefix to trim from log messages
_PATH_TRIM_PREFIX = "/app/"


def _install_log_record_factory() -> None:
    """Install a log record factory that exposes trimmed paths."""
    global _LOG_RECORD_FACTORY_CONFIGURED
    if _LOG_RECORD_FACTORY_CONFIGURED:
        return

    def factory(*args, **kwargs):
        record = _ORIGINAL_LOG_RECORD_FACTORY(*args, **kwargs)
        pathname = getattr(record, "pathname", "") or ""

        # Trim /app/ prefix from paths
        if pathname.startswith(_PATH_TRIM_PREFIX):
            record.shortpathname = pathname[len(_PATH_TRIM_PREFIX):]
        else:
            record.shortpathname = pathname

        return record

    logging.setLogRecordFactory(factory)
    _LOG_RECORD_FACTORY_CONFIGURED = True


def setup_logging() -> None:
    """Configure logging to match backend format with dual output.

    Logs to:
    1. stdout (for docker logs) - console handler
    2. /storage/logs/browser-automation.log - rotating file handler

    Format: YYYY-MM-DD HH:MM:SS LEVEL [path:line] - message
    Example: 2025-11-26 07:41:42 INFO [browser_api.py:76] - Starting task...
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    # Install custom log record factory first
    _install_log_record_factory()

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(shortpathname)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler (persistent with rotation)
    log_dir = Path("/storage/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "browser-automation.log"

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _LOGGING_CONFIGURED = True

    # Log initialization confirmation
    logger = logging.getLogger(__name__)
    logger.info("Browser automation logging initialized (stdout + file: %s)", log_file)


__all__ = ["setup_logging"]
