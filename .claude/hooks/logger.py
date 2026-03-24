"""Shared logger: writes to hooks.log in the same directory."""
import logging
from pathlib import Path

LOG_FILE = Path(__file__).parent / "hooks.log"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(name)s] [%(filename)s:%(lineno)d] %(levelname)s %(message)s")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    return logger
