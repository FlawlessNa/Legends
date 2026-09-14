"""
Loop-level diagnostics, installed once per process.

The Session topology is one MainProcess plus a child process per Engine and one for
the Peripherals, each running its own asyncio event loop. When a task is dropped on
the floor or a callback raises, asyncio hands the failure to that loop's exception
handler, whose default implementation writes to stderr. Child-process stderr is not
captured anywhere, so those reports are lost - the exact class of bug the Session log
artifact is meant to make diagnosable after the fact. Routing them through the
logging module instead puts them in the log, attributed to their process and task.
"""

import asyncio
import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)


def install_loop_diagnostics(*, debug: bool = False) -> None:
    """
    Called from within a running event loop, once per process.
    :param debug: When True, also puts the loop in asyncio debug mode: slow callbacks
     are reported, coroutines are tracked with their creation traceback, and
     never-retrieved task exceptions are surfaced eagerly rather than at collection.
     Costly enough that it stays opt-in.
    :return: None
    """
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_log_loop_exception)
    if debug:
        loop.set_debug(True)
    logger.debug("Loop diagnostics installed (asyncio debug mode: %s).", debug)


def _log_loop_exception(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    """
    asyncio exception handler. Replaces the default stderr report with a log record
    carrying the full traceback plus whatever context asyncio attached to it (the
    offending task, future, handle or protocol).
    :param loop: The event loop reporting the failure.
    :param context: asyncio's context dict. Always has "message"; "exception" and the
     other keys are optional.
    :return: None
    """
    exception = context.get("exception")
    lines = [f"Unretrieved asyncio exception: {context.get('message', 'no message')}"]
    for key, value in sorted(context.items()):
        if key in ("message", "exception"):
            continue
        elif key == "source_traceback":
            # Only present in asyncio debug mode: the stack that created the task.
            # Rendered as a stack rather than a repr'd list of FrameSummary objects.
            lines.append("  source_traceback (where the task was created):")
            lines.extend(
                f"    {line}"
                for line in "".join(traceback.format_list(value)).splitlines()
            )
        else:
            lines.append(f"  {key}: {value!r}")
    logger.error("\n".join(lines), exc_info=exception)
