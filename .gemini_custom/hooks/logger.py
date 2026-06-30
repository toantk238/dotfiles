"""Shared logger: writes to hooks.log in the same directory."""
import logging
import os
from pathlib import Path

LOG_LEVEL = os.environ.get("HOOKS_LOG_LEVEL", "INFO").upper()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    # Ensure level is valid
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] [%(filename)s:%(lineno)d] %(levelname)s %(message)s"
    )

    try:
        log_file = Path(__file__).parent / f"{name}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception as e:
        # Fallback to stream handler if file is not writable
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)
        logger.error(f"Failed to set up FileHandler: {e}. Falling back to StreamHandler.")

    return logger
