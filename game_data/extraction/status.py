"""
`status`: does the installed client match the latest extraction?

- `missing`: the store has no extraction.
- `fresh`: the installed archives are the latest extraction's Build.
- `stale`: they aren't. `python -m game_data extract` brings it up to date.

It is cheap enough to call at every bot startup: it `stat`s the archives and
compares each one's size and modification time with the latest manifest. An
archive is read only when its size matches and its time doesn't, to tell a
file copied or touched from one changed. An unchanged client is answered
without reading a byte of any archive.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from game_data.config import STORE

from .build import ArchiveFile, HashedArchive, archive_files, file_sha256
from .store import Store


class Freshness(StrEnum):
    MISSING = "missing"
    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class Status:
    """
    :ivar freshness: The answer.
    :ivar latest: The latest extraction's build id, or `None` when `missing`.
    :ivar changed: When `stale`, the archives that differ from it: added,
        removed or changed, by path. Empty otherwise.
    """

    freshness: Freshness
    latest: str | None
    changed: tuple[str, ...] = ()


def status(client: Path, root: Path = STORE) -> Status:
    """The installed client at `client` against the store at `root`."""
    latest = Store(root).latest()
    if latest is None:
        return Status(Freshness.MISSING, None)
    recorded = {archive.path: archive for archive in latest.archives}
    installed = {archive.path: archive for archive in archive_files(client)}
    changed = sorted(recorded.keys() ^ installed.keys())
    for path in sorted(recorded.keys() & installed.keys()):
        if _differs(client, recorded[path], installed[path]):
            changed.append(path)
    if changed:
        return Status(Freshness.STALE, latest.build, tuple(sorted(changed)))
    return Status(Freshness.FRESH, latest.build)


def _differs(client: Path, was: HashedArchive, now: ArchiveFile) -> bool:
    """Whether an archive changed, reading it only if its time alone did."""
    if was.size != now.size:
        return True
    if was.mtime_ns == now.mtime_ns:
        return False
    return file_sha256(client / now.path) != was.sha256
