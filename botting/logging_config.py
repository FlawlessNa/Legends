"""
One place for all logging configuration.

Currently holds the Session-directory half. The dictConfig levels/handlers half
(Log Buckets, Console Thresholds, the aligned formatter) was designed alongside
it and lands with the mechanical ``LOG_LEVEL`` sweep; this module is where it
goes. What is here is what the JSONL telemetry sink needs to exist: a directory
scoped to one Session, created before the first handler is built.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Final

from paths import ROOT

#: Root of the logger hierarchy for the whole project. Every logger in
#: ``botting/`` names itself after ``__name__``; every logger in ``maple/``
#: prefixes ``__name__`` with this.
PARENT_LOG: Final = "botting"

LOGS_ROOT: Final[Path] = Path(ROOT) / "logs"

#: How many Session directories survive. Old ones go at the *start* of a
#: Session, not the end - see ``prune_old_sessions``.
KEEP_SESSIONS: Final = 20


def prune_old_sessions(keep: int = KEEP_SESSIONS) -> None:
    """
    Drop all but the most recent Session directories.

    Called at Session start rather than at exit, so a Session that died without
    tidying up still gets cleaned up - by the next one.

    Only directories are considered: the legacy ``Session YYYYMMDD.log`` files
    sit at the logs root as plain files, so pruning leaves them alone.

    :param keep: How many Session directories to end up with, counting the one
        the caller is about to create.
    """
    if not LOGS_ROOT.is_dir():
        return
    # Timestamped names sort chronologically as strings, so name order is age
    # order - no stat() call needed, and no dependence on mtimes that a backup
    # or a sync tool may have rewritten.
    dirs = sorted((p for p in LOGS_ROOT.iterdir() if p.is_dir()), key=lambda p: p.name)
    # keep - 1, because this runs before the caller's own directory exists and
    # that directory is one of the `keep`.
    for stale in dirs[: max(0, len(dirs) - keep + 1)]:
        shutil.rmtree(stale, ignore_errors=True)


def new_session_dir() -> Path:
    """
    Create and return the directory holding one Session's logs and telemetry.

    :return: ``logs/<YYYY-MM-DD_HH-MM-SS>/``, freshly created.
    """
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    prune_old_sessions()
    session_dir = LOGS_ROOT / time.strftime("%Y-%m-%d_%H-%M-%S")
    session_dir.mkdir(exist_ok=True)
    return session_dir
