"""
A plain file logger at ~/.vaultfather/vaultfather.log. Nothing fancy —
the point is that when something goes wrong in the background upload
thread, there's a real trace to look at afterward instead of a job
that's just silently stuck with no explanation.
"""

import logging
from pathlib import Path

LOG_PATH = Path.home() / ".vaultfather" / "vaultfather.log"


def get_logger() -> logging.Logger:
    logger = logging.getLogger("vaultfather")
    if logger.handlers:
        return logger  # already configured

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
