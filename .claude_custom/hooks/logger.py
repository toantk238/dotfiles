"""Shared logger: writes to hooks.log in the same directory."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import os
from pathlib import Path
from typing import Generator

LOG_LEVEL = os.environ.get("HOOKS_LOG_LEVEL", "INFO").upper()

# The model currently answering, tagged onto every log line while set.
_current_model: ContextVar[str] = ContextVar("current_model", default="")


@contextmanager
def model_context(model: str) -> Generator[None, None, None]:
    """Tag every log line written inside this block with `[model]`."""
    token = _current_model.set(model)
    try:
        yield
    finally:
        _current_model.reset(token)


class _ModelTagFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        model = _current_model.get()
        record.model_tag = f" [{model}]" if model else ""
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    # Ensure level is valid
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] [%(filename)s:%(lineno)d] %(levelname)s%(model_tag)s %(message)s"
    )

    try:
        log_file = Path(__file__).parent / f"{name}.log"
        handler: logging.Handler = logging.FileHandler(log_file, encoding="utf-8")
        error = None
    except Exception as e:
        # Fallback to stream handler if file is not writable
        handler = logging.StreamHandler()
        error = e
    handler.setFormatter(fmt)
    handler.addFilter(_ModelTagFilter())
    logger.addHandler(handler)
    if error:
        logger.error(f"Failed to set up FileHandler: {error}. Falling back to StreamHandler.")

    return logger
