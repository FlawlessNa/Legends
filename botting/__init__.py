"""
This package defines the basis for a "color" (aka image detection) botting framework.
It contains the necessary tool to establish one or multiple botting processes,
and provides abstractions into how a bot should be structured and implemented.
"""

# isort: off
# First, before anything reads a window rectangle or a screen metric.
from . import _dpi_awareness  # noqa: F401
# isort: on

import faulthandler
import logging.config
import multiprocessing

import pytesseract

from paths import TESSERACT

from ._debug_names import install as _install_debug_names
from .logging_config import PARENT_LOG, levels_config
from .telemetry import emit_event, not_telemetry

pytesseract.pytesseract.tesseract_cmd = TESSERACT

# The capture dial, in every process: `botting` captures at DEBUG and stops
# propagating to the root logger. Handlers are deliberately absent here - a
# child process ships its records to Main Process over the logging queue, and
# Main Process builds its own once `SessionManager` has a Session directory to
# write into.
logging.config.dictConfig(levels_config())
logger = logging.getLogger(PARENT_LOG)

current_process = multiprocessing.current_process()

# Always-on, in every process. A hard crash (segfault, C-level abort in a native
# dependency) never reaches the logging module, so the only trace it can leave is the
# interpreter-level traceback faulthandler dumps to stderr.
try:
    faulthandler.enable()
except AttributeError, RuntimeError, ValueError:
    # sys.stderr is None or has no file descriptor - the case under pythonw and some
    # IDE runners. Nothing to dump to, so carry on without the crash tracebacks.
    pass

# Opt-in, debugger-only. Must happen before any thread or event loop exists.
_install_debug_names()

__all__ = ["PARENT_LOG", "emit_event", "levels_config", "not_telemetry"]
