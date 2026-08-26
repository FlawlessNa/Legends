"""
This package defines the basis for a "color" (aka image detection) botting framework.
It contains the necessary tool to establish one or multiple botting processes,
and provides abstractions into how a bot should be structured and implemented.
"""

import faulthandler
import logging.handlers
import multiprocessing
import os
import pytesseract
import time

from paths import ROOT, TESSERACT
from ._debug_names import install as _install_debug_names
from .logging_config import PARENT_LOG
from .telemetry import emit_event, not_telemetry

pytesseract.pytesseract.tesseract_cmd = TESSERACT

# Set the root logger for the entire project.
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

current_process = multiprocessing.current_process()

# Always-on, in every process. A hard crash (segfault, C-level abort in a native
# dependency) never reaches the logging module, so the only trace it can leave is the
# interpreter-level traceback faulthandler dumps to stderr.
try:
    faulthandler.enable()
except (AttributeError, RuntimeError, ValueError):
    # sys.stderr is None or has no file descriptor - the case under pythonw and some
    # IDE runners. Nothing to dump to, so carry on without the crash tracebacks.
    pass

# Opt-in, debugger-only. Must happen before any thread or event loop exists.
_install_debug_names()

if current_process.name == "MainProcess":
    # If this is the main process, then we want to set up the logging handlers.

    class CustomFormatter(logging.Formatter):
        """
        Custom formatter for logging. Ensures most log messages are vertically aligned.
        """

        def format(self, record):
            for attr, value in record.__dict__.items():
                if attr == "name":
                    record.__dict__[attr] = record.__dict__[attr].ljust(50)
                    record.__dict__[attr] = record.__dict__[attr].removeprefix(
                        "botting."
                    )
                    record.__dict__[attr] = record.__dict__[attr].removeprefix("core.")
                    record.__dict__[attr] = record.__dict__[attr].removeprefix(
                        "maple."
                    )
                elif attr == "processName":
                    record.__dict__[attr] = record.__dict__[attr].ljust(30)
                elif attr == "levelname":
                    record.__dict__[attr] = record.__dict__[attr].ljust(10)
                elif attr == "taskName":
                    # None whenever the record was emitted outside an asyncio task.
                    record.__dict__[attr] = str(value or "-").ljust(30)
            return super().format(record)

    formatter = CustomFormatter(
        fmt=(
            "{levelname} -- PROCESS {processName} -- TASK {taskName} -- "
            "MODULE {name} -- {asctime}:::{message}"
        ),
        style="{",
        # datefmt="%Y.%m.%d. %H:%M:%S:%f",
    )

    if not os.path.exists(os.path.join(ROOT, "logs")):
        os.mkdir(os.path.join(ROOT, "logs"))

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(ROOT, "logs", f'Session {time.strftime("%Y%m%d")}.log'),
        maxBytes=10 * (2**20),  # 10 MB
        backupCount=100,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Telemetry Records ride this same hierarchy on their way to the JSONL sink.
    # They carry an empty message, so a text handler without this filter prints
    # a blank line per emitted event.
    file_handler.addFilter(not_telemetry)
    console_handler.addFilter(not_telemetry)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
