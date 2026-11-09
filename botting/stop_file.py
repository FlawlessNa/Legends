"""
The stop file: how something outside the bot asks a Session to stop.

A file named ``STOP`` in the Session directory is the request, and its text is
the reason. ``python -m botting.session stop`` writes it (``request_stop``),
and ``SessionManager`` runs ``watch_stop_file`` as one of its Main Process
tasks, which looks for it once a second.

The request ends the Session the way a finished Task Manager does: ``None`` on
its queue, so ``SessionManager.launch`` returns normally and ``__exit__`` runs
as usual, releasing every key. It is not a ``KeyboardInterrupt``, which would
make the exit look like an error, and there is no socket or signal: the file is
the whole channel, and it leaves the reason on disk.

Both ends live here, outside ``botting.core``, so the reader imports them
without loading the engine.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Final

from botting.telemetry import emit_event
from botting.telemetry_events import (
    SESSION_STOP_REQUESTED,
    SessionStopRequestedPayload,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

logger = logging.getLogger(__name__)

#: The file's name in the Session directory.
STOP_FILENAME: Final = "STOP"
#: Seconds between two looks for the file.
POLL_INTERVAL: Final = 1.0
#: The reason recorded when the file is empty.
NO_REASON: Final = "no reason given"


def request_stop(session_dir: Path, reason: str) -> Path:
    """
    Write the stop file. It is written whole under another name, then renamed,
    so the Session never reads half a reason.

    :param session_dir: The Session directory, ``logs/<ts>/``.
    :param reason: Why the Session should stop; recorded as given.
    :return: The stop file's path.
    """
    path = session_dir / STOP_FILENAME
    partial = session_dir / f"{STOP_FILENAME}.partial"
    partial.write_text(reason, encoding="utf-8")
    os.replace(partial, path)
    return path


async def watch_stop_file(
    session_dir: Path,
    queue: asyncio.Queue[Any],
    on_request: Callable[[str], object],
    *,
    interval: float = POLL_INTERVAL,
) -> None:
    """
    Look for the stop file every ``interval`` seconds. Once it appears: log a
    WARNING with the reason, emit ``session.stop_requested``, hand the reason to
    ``on_request``, and put ``None`` on ``queue``. Never raises.

    It then waits to be cancelled rather than returning. ``launch`` waits for
    the first of its tasks to finish, and the one that should is the Task
    Manager, after the request in hand and on reading ``None``; returning here
    would have ``launch`` cancel it mid-request instead.

    A cancelled watch emits nothing, whatever is on disk: ``__exit__`` cancels
    it before writing ``session.ended``, which must stay the last record.

    :param session_dir: The Session directory to watch.
    :param queue: The Task Manager's queue.
    :param on_request: Called with the reason, before ``None`` is queued. The
        Session stores it there for ``session.ended``.
    :param interval: Seconds between looks.
    """
    path = session_dir / STOP_FILENAME
    while (reason := _read_reason(path)) is None:
        await asyncio.sleep(interval)

    logger.warning("Stop requested through %s: %s", path, reason)
    payload: SessionStopRequestedPayload = {"reason": reason}
    emit_event(None, SESSION_STOP_REQUESTED, payload, logger_name=logger.name)
    on_request(reason)
    queue.put_nowait(None)
    await asyncio.Event().wait()


def _read_reason(path: Path) -> str | None:
    """
    The stop file's reason, ``NO_REASON`` when it is empty, or ``None`` when
    there is no file to read yet. A file that can't be read now is looked at
    again next time, never raised.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.debug("Stop file %s not readable yet: %s", path, exc)
        return None
    return raw.decode("utf-8", errors="replace").strip() or NO_REASON
