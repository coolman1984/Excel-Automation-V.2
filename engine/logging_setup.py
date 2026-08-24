"""Logging.

Logs are for support, not for the user. The application always writes them and
never shows a raw traceback as the primary message.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def configure(log_file: str, verbose: bool = False) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("engine")
    if not _CONFIGURED:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s %(message)s"))
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        # Under pythonw.exe there is no console: sys.stderr is None and a stream
        # handler would fail on every message. The file log is always written.
        if sys.stderr is not None:
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
            quiet = os.environ.get("APP_LOG_QUIET") == "1"
            console.setLevel(logging.CRITICAL if quiet else
                             (logging.DEBUG if verbose else logging.INFO))
            logger.addHandler(console)
        _CONFIGURED = True
    return logger


def logger() -> logging.Logger:
    return logging.getLogger("engine")
