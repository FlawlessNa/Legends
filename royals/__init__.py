from .core import Bot
from .core import SessionManager

import logging
import os
import time

from .utilities import custom_logging
from paths import ROOT


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="%(levelname)s -- PROCESS %(processName)s -- MODULE %(name)s -- %(asctime)s:::%(message)s",
    datefmt="%Y.%m.%d. %H:%M:%S",
)  # TODO - If you ever switch to 3.12, then add TASK %(taskName)s to the formatter

if not os.path.exists(os.path.join(ROOT, "logs")):
    os.mkdir(os.path.join(ROOT, "logs"))
file_handler = custom_logging.MultiProcessRotatingFileHandler(
    os.path.join(ROOT, "logs", f'Session {time.strftime("%Y%m%d")}.log'),
    maxBytes=10 * (2**20),  # 10 MB
    backupCount=100,
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

console_handler = custom_logging.MultiProcessStreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)
