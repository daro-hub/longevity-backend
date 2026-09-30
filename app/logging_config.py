"""Structured-ish logging setup. Neither of the original two files
(main.py, index_docs.py) imported the stdlib logging module at all — every
failure went to console.error on the frontend or a bare `print` here, with
nothing captured server-side. This is the minimum viable fix: real log
records with a request id, so a production error can actually be traced.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. re-imported in tests)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
            defaults={"request_id": "-"},
        )
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
