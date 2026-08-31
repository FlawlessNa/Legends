"""
One place for all logging configuration.

Two independent dials:
  * **capture** - what reaches the log files. Always everything (``DEBUG``).
  * **display** - what reaches your console. :data:`CONSOLE_THRESHOLDS`, layered
    with the ``BOTTING_CONSOLE`` environment variable.

A record's level is its *severity*, never its visibility. That separation is
what let the old ``LOG_LEVEL`` module constants be deleted outright rather than
transcribed: a call site now states how severe its event is, and the console
map alone decides who sees it.

Also holds the per-Session directory the text logs and the JSONL telemetry sink
share, created before the first handler is built.
"""

from __future__ import annotations

import logging
import os
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


#: The four Log Buckets, and the order their handlers are built in.
BUCKET_NAMES: Final = ("movement", "inputs", "decisions", "other")

#: Logger-name prefix -> Log Bucket. Longest prefix wins, so a submodule can
#: escape its parent's bucket - which three ``decision_makers`` submodules do.
#:
#: Records are routed here, on the handler, rather than by giving each bucket
#: its own logger: ``Engine`` and ``PeripheralsProcess`` run in child processes,
#: so nearly every interesting record travels QueueHandler -> QueueListener ->
#: handlers directly and never touches the logger hierarchy in this process.
BUCKETS: Final[dict[str, str]] = {
    PARENT_LOG: "other",
    "botting.controller": "inputs",
    "botting.core": "decisions",
    "botting.maple.bots": "decisions",
    "botting.maple.decision_makers": "decisions",
    "botting.maple.model.mechanics": "movement",
    "botting.maple.decision_makers.rotation": "movement",
    "botting.maple.decision_makers.mixins._map_mixins": "movement",
    "botting.maple.decision_makers.mixins._rotation_mixins": "movement",
    # Movement compilation, sitting under `maple.actions` rather than
    # `model.mechanics`. Its siblings there (menus, writing, skills) are not
    # movement, hence the module-level prefix rather than the package one.
    "botting.maple.actions.movements_v2": "movement",
}

#: Display dial: logger-name prefix -> the level the console shows from.
#: Longest prefix wins; ``None`` mutes that prefix outright. Seeded *empty* on
#: purpose - an empty map plus the INFO default reproduces today's console
#: exactly, which is what makes the dictConfig switch-over reviewable.
#:
#: It stays empty after the per-call-site severity re-derivation, too. Once every
#: level is honest, the INFO default lands each record where it belongs on its
#: own: plumbing traces sit at DEBUG and stay off the console, faults sit at
#: WARNING and reach it, and the decision narrative left the text log entirely to
#: become Telemetry Records. An entry here would be needed only where an honest
#: level and the right console are in tension, and no call site is. Turning a
#: subsystem up for one run is what ``BOTTING_CONSOLE`` is for.
CONSOLE_DEFAULT: Final = logging.INFO
CONSOLE_THRESHOLDS: Final[dict[str, int | None]] = {}

_FMT: Final = (
    "{levelname} -- PROCESS {processName} -- TASK {taskName} -- "
    "MODULE {name} -- {asctime}:::{message}"
)


def _longest_prefix(name: str, table: dict, default):
    """
    Look ``name`` up in a prefix table, letting the most specific entry win.

    A prefix matches on a dotted-name boundary only, so ``botting.core`` does
    not claim ``botting.core_utils``.
    """
    best, best_len = default, -1
    for prefix, value in table.items():
        if (name == prefix or name.startswith(f"{prefix}.")) and len(prefix) > best_len:
            best, best_len = value, len(prefix)
    return best


def bucket_for(name: str) -> str:
    """
    :param name: A logger name, as it appears on the record.
    :return: The Log Bucket that name's records belong to.
    """
    return _longest_prefix(name, BUCKETS, "other")


def _env_overrides() -> dict[str, int | None]:
    """
    Parse ``BOTTING_CONSOLE`` into console threshold entries.

    Syntax is comma-separated ``<target>=<level>``, where ``<target>`` is either
    a Log Bucket name or a logger-name prefix, and ``<level>`` is a level name
    or ``OFF``/``NONE``/``MUTE`` to silence it::

        BOTTING_CONSOLE=movement=DEBUG,botting.core.engine=OFF

    Console-only by construction: these entries never reach a file handler, so
    turning the console up or down can never cost file fidelity.

    :return: Entries to layer over :data:`CONSOLE_THRESHOLDS`.
    """
    raw = os.environ.get("BOTTING_CONSOLE", "").strip()
    if not raw:
        return {}
    out: dict[str, int | None] = {}
    for clause in filter(None, (c.strip() for c in raw.split(","))):
        key, _, value = clause.partition("=")
        key, value = key.strip(), value.strip().upper()
        if value in {"OFF", "NONE", "MUTE"}:
            level = None
        else:
            level = logging.getLevelName(value)
            if isinstance(level, str):
                raise ValueError(f"BOTTING_CONSOLE: unknown level {value!r}")
        # A bucket name expands to every prefix routed into that bucket.
        targets = (
            [p for p, b in BUCKETS.items() if b == key]
            if key in BUCKET_NAMES
            else [key]
        )
        for target in targets:
            out[target] = level
    return out


class BucketFilter(logging.Filter):
    """Admits only the records belonging to one Log Bucket."""

    def __init__(self, bucket: str) -> None:
        super().__init__()
        self.bucket = bucket

    def filter(self, record: logging.LogRecord) -> bool:
        return bucket_for(record.name) == self.bucket


class ConsoleFilter(logging.Filter):
    """
    The display dial. Never affects what the files capture.

    Thresholds are resolved once, at construction: the env var is read at
    Session start and the map underneath it is a module constant.
    """

    def __init__(self) -> None:
        super().__init__()
        self.thresholds = {**CONSOLE_THRESHOLDS, **_env_overrides()}

    def filter(self, record: logging.LogRecord) -> bool:
        threshold = _longest_prefix(record.name, self.thresholds, CONSOLE_DEFAULT)
        return threshold is not None and record.levelno >= threshold


class CustomFormatter(logging.Formatter):
    """
    Vertically aligns records so a log file reads as columns.

    Formats a *copy*. The ``QueueListener`` hands the same record object to
    every handler in turn, and ``handle()`` runs ``filter()`` before ``emit()``,
    so mutating ``record.name`` here would strip ``botting.`` from the name the
    next handler's :class:`BucketFilter` matches on - and every handler after
    the first would drop the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        record = logging.makeLogRecord(record.__dict__)
        # Strip before padding: the other order pads to 50 and *then* removes
        # the prefix, so the same record prints at different widths depending on
        # how deep its logger name is.
        name = (
            record.name.removeprefix("botting.")
            .removeprefix("core.")
            .removeprefix("maple.")
        )
        record.name = name.ljust(50)
        record.processName = str(record.processName).ljust(30)
        record.levelname = record.levelname.ljust(10)
        # None whenever the record was emitted outside an asyncio task.
        record.taskName = str(getattr(record, "taskName", None) or "-").ljust(30)
        return super().format(record)


def levels_config() -> dict:
    """
    The capture dial, applied at import in *every* process.

    Declares no handlers: a child process ships its records to Main Process
    through the ``QueueHandler`` that ``ChildProcess`` installs, and Main
    Process gets its handlers from :func:`full_config`, once the Session
    directory exists.

    :return: A ``logging.config.dictConfig`` mapping.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {PARENT_LOG: {"level": "DEBUG", "propagate": False}},
    }


def full_config(session_dir: Path) -> dict:
    """
    The full Main Process configuration: one file per Log Bucket, a combined
    ``session.log``, and the console.

    Every file handler captures at ``DEBUG`` and is unfiltered by level - the
    console is the only sink the display dial touches.

    :param session_dir: This Session's directory, from :func:`new_session_dir`.
    :return: A ``logging.config.dictConfig`` mapping.
    """
    # Deferred: `telemetry` imports PARENT_LOG from this module, so a top-level
    # import here would close the cycle. By the time a Session builds handlers,
    # both modules are long since imported.
    from .telemetry import not_telemetry

    handlers: dict[str, dict] = {
        f"file_{bucket}": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(session_dir / f"{bucket}.log"),
            "maxBytes": 10 * 2**20,
            "backupCount": 10,
            "encoding": "utf-8",
            "level": "DEBUG",
            "formatter": "aligned",
            "filters": [f"bucket_{bucket}", "not_telemetry"],
        }
        for bucket in BUCKET_NAMES
    }
    # The one sink showing cross-subsystem interleaving, which is the thing that
    # cannot be reconstructed from the split files.
    handlers["file_session"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(session_dir / "session.log"),
        "maxBytes": 10 * 2**20,
        "backupCount": 10,
        "encoding": "utf-8",
        "level": "DEBUG",
        "formatter": "aligned",
        "filters": ["not_telemetry"],
    }
    handlers["console"] = {
        "class": "logging.StreamHandler",
        # DEBUG so `respect_handler_level` on the QueueListener never pre-empts
        # ConsoleFilter, which owns the threshold.
        "level": "DEBUG",
        "formatter": "aligned",
        "filters": ["console", "not_telemetry"],
    }
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"aligned": {"()": CustomFormatter, "fmt": _FMT, "style": "{"}},
        "filters": {
            **{f"bucket_{b}": {"()": BucketFilter, "bucket": b} for b in BUCKET_NAMES},
            "console": {"()": ConsoleFilter},
            # A plain callable is a valid filter object, so the factory just
            # hands it over. Every text handler needs it: a Telemetry Record
            # carries an empty message and would otherwise contribute one blank
            # line per emitted event.
            "not_telemetry": {"()": lambda: not_telemetry},
        },
        "handlers": handlers,
        "loggers": {
            PARENT_LOG: {
                "level": "DEBUG",
                "handlers": list(handlers),
                "propagate": False,
            }
        },
    }
