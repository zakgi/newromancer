# SPDX-License-Identifier: MIT
"""Colored command-line logging: timestamp, severity, and module/function/line."""

from __future__ import annotations

import logging
import os
import sys
from typing import TextIO

from colorama import Back, Fore, Style, just_fix_windows_console

LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: Fore.BLUE,
    logging.INFO: Fore.GREEN,
    logging.WARNING: Fore.YELLOW,
    logging.ERROR: Fore.RED,
    logging.CRITICAL: Fore.BLACK + Back.RED,
}


class LogColorFormatter(logging.Formatter):
    """Timestamp, colored severity, and highlighted module/function/line."""

    def __init__(self, use_color: bool = True) -> None:
        super().__init__()
        self.use_color: bool = use_color

    def format(self, record: logging.LogRecord) -> str:
        level_name: str = "FATAL" if record.levelno == logging.CRITICAL else record.levelname
        level_label: str = f"{level_name:<7}"
        origin: str = "%(module)s"
        if record.funcName != "__init__":
            origin += "::%(funcName)s"
        if self.use_color:
            level_color: str = LEVEL_COLORS.get(record.levelno, "")
            level_label = f"{Style.RESET_ALL}{level_color}{level_label}{Style.RESET_ALL}"
            origin = f"{Style.BRIGHT}{origin}{Style.RESET_ALL}"
        layout: str = f"%(asctime)s: [ {level_label} ] {origin}:%(lineno)d %(message)s"
        formatter: logging.Formatter = logging.Formatter(layout)
        return formatter.format(record)


def setup_logging(level: str = "INFO", stream: TextIO | None = None) -> logging.Logger:
    """Configure CLI logging once; redirected output and NO_COLOR use plain text."""
    just_fix_windows_console()
    output: TextIO = sys.stderr if stream is None else stream
    handler: logging.StreamHandler[TextIO] = logging.StreamHandler(output)
    handler.setFormatter(LogColorFormatter(use_color=output.isatty() and not os.environ.get("NO_COLOR")))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    return logging.getLogger()
