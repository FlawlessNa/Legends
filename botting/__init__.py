"""
This package defines the basis for a "color" (aka image detection) botting framework.
It contains the necessary tool to establish one or multiple botting processes,
and provides abstractions into how a bot should be structured and implemented.
"""

import logging.handlers
import multiprocessing
import os
import pytesseract
import time

# from .core import SessionManager, Executor, EngineData
from paths import ROOT, TESSERACT


PARENT_LOG = __name__
pytesseract.pytesseract.tesseract_cmd = TESSERACT

# Set the root logger for the entire project.
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

current_process = multiprocessing.current_process()

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
                    record.__dict__[attr] = record.__dict__[attr].removeprefix(
                        "core."
                    )
                    record.__dict__[attr] = record.__dict__[attr].removeprefix(
                        "royals."
                    )
                elif attr == "processName":
                    record.__dict__[attr] = record.__dict__[attr].ljust(30)
                elif attr == "levelname":
                    record.__dict__[attr] = record.__dict__[attr].ljust(10)
            return super().format(record)

    formatter = CustomFormatter(
        fmt="{levelname} -- PROCESS {processName} -- MODULE {name} -- {asctime}:::{message}",
        style="{",
        datefmt="%Y.%m.%d. %H:%M:%S",
    )  # TODO - If you ever switch to 3.12, then add TASK %(taskName)s to the formatter

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
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
