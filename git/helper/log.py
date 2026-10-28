"""Logging for gittool.

Console: coloured, level from ``LOG_LEVEL`` (default INFO), written to stderr.
File:    everything at DEBUG, rotated, at ``GITTOOL_LOG_FILE`` or
         ``$XDG_STATE_HOME/gittool/gittool.log`` (default ``~/.local/state``).
         Set ``GITTOOL_LOG_FILE=`` (empty) to disable the file log.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(levelname)8s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)8s | %(filename)s:%(lineno)d | %(message)s"


class ColourFormatter(logging.Formatter):
    """Adapted from https://stackoverflow.com/a/56944256/3638629"""

    COLOURS = {
        logging.DEBUG: "\x1b[38;21m",
        logging.INFO: "\x1b[38;5;39m",
        logging.WARNING: "\x1b[38;5;226m",
        logging.ERROR: "\x1b[38;5;196m",
        logging.CRITICAL: "\x1b[31;1m",
    }
    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelno, "")
        return f"{colour}{super().format(record)}{self.RESET}"


def _console_level() -> int:
    name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return logging.getLevelNamesMapping().get(name, logging.INFO)


def _log_file() -> Path | None:
    override = os.environ.get("GITTOOL_LOG_FILE")
    if override is not None:
        return Path(override) if override else None
    state_home = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(state_home) / "gittool" / "gittool.log"


def _build_logger() -> logging.Logger:
    log = logging.getLogger("gittool")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    if log.handlers:  # already configured (e.g. module re-imported in tests)
        return log

    console = logging.StreamHandler()
    console.setLevel(_console_level())
    console.setFormatter(ColourFormatter(FORMAT))
    log.addHandler(console)

    path = _log_file()
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
            log.addHandler(file_handler)
        except OSError as exc:  # unwritable state dir: keep going with console only
            log.debug("file logging disabled: %s", exc)
    return log


logger = _build_logger()
