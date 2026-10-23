"""
The factory loop's state for one ticket, kept where no session can trip over it.

It lives at `<git-common-dir>/factory/<n>/state.json`: outside every worktree,
so no worker's diff fills with the loop's bookkeeping and no `git status` shows
it (design.md §4 rule 5). `run.md` is this file rendered for people, once.

**Every writer goes through `update`.** There is deliberately no public direct
write: `factory run`, `feature new`, `spec submit` and `accept` are separate
processes, and a read-change-write that skips the lock loses another process's
update. `update` takes an OS lock for the whole round trip; the OS releases it
if the process dies. `load` takes no lock and relies on the write being an
atomic replace.

**Windows.** `os.replace` raises `PermissionError` while any reader holds the
file open, and a tight reader made 2897 of 3000 bare replaces fail. Reads and
writes both retry it a bounded number of times, then raise `StateError`.
`load` never treats a `PermissionError` as a missing file: that would read a
busy file as "no state yet" and let the next write erase it.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import IO, Any, Final

from factory.chain import common_dir

#: The only schema version this module reads or writes.
VERSION: Final = 1

#: Tries at an operation a concurrent reader or writer can refuse, and the pause
#: between them. 50 x 20 ms held up against a tight reader (0 failures in 200).
RETRIES: Final = 50
RETRY_DELAY: float = 0.02

#: How long `update` waits for another process's lock, and how often it asks.
LOCK_TIMEOUT: float = 10.0
LOCK_POLL: Final = 0.05

_FIELDS: Final = (
    "version",
    "ticket",
    "stage",
    "attempt",
    "cycles",
    "worker",
    "turn_base",
    "submitted",
    "accepted",
    "parked",
    "designer_session",
    "log",
)
_NULLABLE_TEXT: Final = (
    "stage",
    "worker",
    "turn_base",
    "submitted",
    "parked",
    "designer_session",
)
_ACCEPTED_FIELDS: Final = ("spec_blob", "base_sha", "accepted_by", "accepted_at")
_LOG_FIELDS: Final = ("at", "event", "detail")


class StateError(Exception):
    """The state cannot be read or written; the message names the file."""


@dataclass(frozen=True)
class Accepted:
    """The factory loop's own record of an acceptance (design §4.5)."""

    spec_blob: str
    base_sha: str
    accepted_by: str
    accepted_at: str


@dataclass(frozen=True)
class LogEntry:
    """One line of the loop's history."""

    at: str
    event: str
    detail: str = ""


@dataclass(frozen=True)
class TicketState:
    """
    One ticket's loop state. A fresh one is `fresh(ticket)`.

    `cycles` maps each judged stage to the rounds it has used, and is read-only.
    `log` is a tuple that only ever grows. `attempt` is the number of the
    current dispatch of `stage`, 1-based (0 before any dispatch).
    """

    ticket: int
    version: int = VERSION
    stage: str | None = None
    attempt: int = 0
    cycles: Mapping[str, int] = field(default_factory=dict[str, int])
    worker: str | None = None
    turn_base: str | None = None
    submitted: str | None = None
    accepted: Accepted | None = None
    parked: str | None = None
    designer_session: str | None = None
    log: tuple[LogEntry, ...] = ()

    def __post_init__(self) -> None:
        frozen = MappingProxyType(dict(sorted(self.cycles.items())))
        object.__setattr__(self, "cycles", frozen)
        object.__setattr__(self, "log", tuple(self.log))


def fresh(ticket: int) -> TicketState:
    """The state of a ticket the loop has not touched."""
    return TicketState(ticket=ticket)


def with_log(current: TicketState, entry: LogEntry) -> TicketState:
    """`current` with `entry` appended. The only way a log changes."""
    return replace(current, log=(*current.log, entry))


def dispatched(current: TicketState, stage: str) -> TicketState:
    """
    `current` after `stage` is dispatched once more.

    The first dispatch of a stage is attempt 1, the second 2, and a different
    stage starts again at 1.
    """
    name = str(stage)
    if current.stage == name:
        return replace(current, attempt=current.attempt + 1)
    return replace(current, stage=name, attempt=1)


# --- Paths -------------------------------------------------------------------


def state_path(repo_root: Path, ticket: int) -> Path:
    """Where `ticket`'s state lives, or `StateError` outside a repository."""
    common = common_dir(repo_root)
    if common is None:
        raise StateError(f"{repo_root} is not inside a git repository.")
    return common / "factory" / str(ticket) / "state.json"


# --- Serialisation -----------------------------------------------------------


def _to_data(current: TicketState) -> dict[str, Any]:
    """The JSON object for `current`. A read-only mapping is copied to a dict."""
    accepted = current.accepted
    return {
        "version": current.version,
        "ticket": current.ticket,
        "stage": current.stage,
        "attempt": current.attempt,
        "cycles": dict(sorted(current.cycles.items())),
        "worker": current.worker,
        "turn_base": current.turn_base,
        "submitted": current.submitted,
        "accepted": None
        if accepted is None
        else {name: getattr(accepted, name) for name in _ACCEPTED_FIELDS},
        "parked": current.parked,
        "designer_session": current.designer_session,
        "log": [{name: getattr(e, name) for name in _LOG_FIELDS} for e in current.log],
    }


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _record(
    value: object, names: tuple[str, ...], where: str, path: Path
) -> dict[str, str]:
    """A mapping of exactly `names`, each a string; `where` names it in errors."""
    if not isinstance(value, dict):
        raise StateError(f"{path}: field {where}: must be an object.")
    found: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
    for key in found:
        if key not in names:
            raise StateError(f"{path}: field {where}: unknown key {key!r}.")
    out: dict[str, str] = {}
    for name in names:
        if name not in found:
            raise StateError(f"{path}: field {where}: missing key {name!r}.")
        if not isinstance(found[name], str):
            raise StateError(f"{path}: field {where}: {name!r} must be a string.")
        out[name] = found[name]
    return out


def _parse(data: object, path: Path, ticket: int) -> TicketState:
    """Validate `data` field by field; every refusal names `path` and the field."""
    if not isinstance(data, dict):
        raise StateError(f"{path}: the top level must be a JSON object.")
    raw: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    for name in raw:
        if name not in _FIELDS:
            raise StateError(f"{path}: unknown field {name!r}.")
    for name in _FIELDS:
        if name not in raw:
            raise StateError(f"{path}: missing field {name!r}.")

    if not _is_int(raw["version"]) or raw["version"] != VERSION:
        raise StateError(
            f"{path}: field 'version' is {raw['version']!r}; only {VERSION} is read."
        )
    if not _is_int(raw["ticket"]) or raw["ticket"] != ticket:
        raise StateError(
            f"{path}: field 'ticket' is {raw['ticket']!r}; this file is ticket {ticket}."
        )
    if not _is_int(raw["attempt"]) or raw["attempt"] < 0:
        raise StateError(f"{path}: field 'attempt' must be a non-negative integer.")
    for name in _NULLABLE_TEXT:
        if raw[name] is not None and not isinstance(raw[name], str):
            raise StateError(f"{path}: field {name!r} must be a string or null.")

    cycles = raw["cycles"]
    if not isinstance(cycles, dict):
        raise StateError(f"{path}: field 'cycles' must be an object.")
    counted: dict[str, int] = {}
    for stage, rounds in cycles.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(stage, str) or not _is_int(rounds) or rounds < 0:
            raise StateError(
                f"{path}: field 'cycles' maps each stage to a non-negative integer."
            )
        counted[stage] = rounds

    accepted: Accepted | None = None
    if raw["accepted"] is not None:
        accepted = Accepted(
            **_record(raw["accepted"], _ACCEPTED_FIELDS, "'accepted'", path)
        )

    entries = raw["log"]
    if not isinstance(entries, list):
        raise StateError(f"{path}: field 'log' must be a list.")
    log = tuple(
        LogEntry(**_record(item, _LOG_FIELDS, f"'log'[{index}]", path))
        for index, item in enumerate(entries)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    )
    return TicketState(
        ticket=ticket,
        version=VERSION,
        stage=raw["stage"],
        attempt=raw["attempt"],
        cycles=counted,
        worker=raw["worker"],
        turn_base=raw["turn_base"],
        submitted=raw["submitted"],
        accepted=accepted,
        parked=raw["parked"],
        designer_session=raw["designer_session"],
        log=log,
    )


# --- Reading and writing -----------------------------------------------------


def _retry[T](operation: Callable[[], T], path: Path, what: str) -> T:
    """Run `operation`, retrying a `PermissionError` a bounded number of times."""
    for attempt in range(RETRIES):
        try:
            return operation()
        except PermissionError:
            if attempt + 1 < RETRIES:
                time.sleep(RETRY_DELAY)
    raise StateError(
        f"{path}: could not {what}: another process kept it busy for "
        f"{RETRIES} tries {RETRY_DELAY * 1000:.0f} ms apart."
    )


def _read(path: Path, ticket: int) -> TicketState:
    """The state in `path`, the fresh one if there is no such file."""
    try:
        text = _retry(lambda: path.read_text(encoding="utf-8"), path, "read")
    except FileNotFoundError:
        return fresh(ticket)
    except OSError as broken:
        raise StateError(f"{path}: could not read: {broken}") from broken
    try:
        data = json.loads(text)
    except ValueError as broken:
        raise StateError(f"{path}: malformed JSON: {broken}") from broken
    return _parse(data, path, ticket)


def _save(path: Path, new: TicketState) -> None:
    """
    Replace `path` with `new`, atomically. Private: callers use `update`.

    The new text goes to a temporary file in the same directory, is flushed and
    fsynced, and only then replaces `path`. A process killed before the replace
    leaves the previous state in `path`; the temporary file is never read.
    """
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    text = json.dumps(_to_data(new), indent=2, sort_keys=True) + "\n"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _retry(lambda: os.replace(temporary, path), path, "replace")
    except Exception:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def load(repo_root: Path, ticket: int) -> TicketState:
    """
    `ticket`'s state: the file's, or a fresh one when there is no file.

    Takes no lock. A malformed file is `StateError`, never a fresh state.
    """
    return _read(state_path(repo_root, ticket), ticket)


# --- The lock ----------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def locked(directory: Path) -> Iterator[None]:
    """
    Hold an exclusive OS lock on `directory/state.lock`, or `StateError`.

    The wait is bounded by `LOCK_TIMEOUT`. The OS drops the lock if the process
    dies, so a crash never leaves the ticket locked.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "state.lock"
    deadline = time.monotonic() + LOCK_TIMEOUT
    with open(path, "a+b") as handle:
        while True:
            try:
                _try_lock(handle)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise StateError(
                        f"{path}: another process held the lock for {LOCK_TIMEOUT} s."
                    ) from None
                time.sleep(LOCK_POLL)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                _unlock(handle)


def update(
    repo_root: Path, ticket: int, change: Callable[[TicketState], TicketState]
) -> TicketState:
    """
    Load `ticket`'s state, apply `change`, save it, and return the result.

    The one way to write. The lock is held from the read to the replace, so two
    processes updating at once lose neither update. `change` must return a
    valid state for the same ticket whose log extends the old one; otherwise
    nothing is written and `StateError` says which field.
    """
    path = state_path(repo_root, ticket)
    with locked(path.parent):
        old = _read(path, ticket)
        new = change(old)
        _parse(_to_data(new), path, ticket)
        if new.log[: len(old.log)] != old.log:
            raise StateError(f"{path}: field 'log' may only be appended to.")
        _save(path, new)
    return new


# --- run.md ------------------------------------------------------------------


def _cell(text: str) -> str:
    """A table cell: no newline, and no bare pipe."""
    return " ".join(text.split()).replace("|", "\\|")


def render_run_md(current: TicketState) -> str:
    """
    `current` as `run.md`: front matter, then the log as a table.

    Pure and ordered, so equal states give identical text. `cycles` is a nested
    block, which `chain.front_matter` reads back as `cycles.<stage>`.
    """
    lines = [
        "---",
        f"ticket: {current.ticket}",
        f"stage: {current.stage if current.stage is not None else 'null'}",
        f"attempt: {current.attempt}",
    ]
    if current.cycles:
        lines.append("cycles:")
        lines.extend(
            f"  {stage}: {rounds}" for stage, rounds in sorted(current.cycles.items())
        )
    else:
        lines.append("cycles: {}")
    lines += [
        "---",
        "",
        f"# Run log for ticket {current.ticket}",
        "",
        "| at | event | detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {_cell(e.at)} | {_cell(e.event)} | {_cell(e.detail)} |" for e in current.log
    )
    return "\n".join(lines) + "\n"
