"""
The frame set: real MSCW frames kept in a private repository, and the expected
readings committed beside the tests as `tests/frames/<tag>.json`.

No pixels are committed. The frames themselves are fetched into
`data/frames/<tag>/` by `scripts/fetch_frames.py`.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Status

TESTS_FRAMES = Path(__file__).resolve().parent / "frames"
FRAMES_ROOT = Path(__file__).resolve().parents[1] / "data" / "frames"
CURRENT = TESTS_FRAMES / "CURRENT"


class FrameSetError(ValueError):
    """A committed expected-readings file is malformed."""


class FrameSetMissing(LookupError):
    """The frames of a tag aren't on disk; the message says how to fetch them."""


@dataclass(frozen=True)
class Expected:
    """What one reader should return on one frame."""

    status: Status
    value: Any = None


@dataclass(frozen=True)
class FrameEntry:
    file: str
    client_size: tuple[int, int]
    notes: str
    expect: dict[str, Expected]


@dataclass(frozen=True)
class FrameSet:
    tag: str
    directory: Path
    entries: tuple[FrameEntry, ...]

    def pixels(self, entry: FrameEntry) -> NDArray[np.uint8]:
        """The frame's `H x W x 3` BGR pixels."""
        image = cv2.imread(str(self.directory / entry.file), cv2.IMREAD_COLOR)
        if image is None:
            raise FrameSetMissing(f"{entry.file} can't be read from {self.directory}")
        return image.astype(np.uint8, copy=False)


def current_tag() -> str:
    return CURRENT.read_text(encoding="utf-8").strip()


def committed_files() -> list[Path]:
    return sorted(TESTS_FRAMES.glob("*.json"))


def parse_entries(raw: object, where: str) -> tuple[FrameEntry, ...]:
    """Validate a decoded expected-readings file; raise `FrameSetError` naming `where`."""
    if not isinstance(raw, dict) or not isinstance(raw.get("frames"), list):
        raise FrameSetError(f'{where}: expected an object with a "frames" list')
    entries: list[FrameEntry] = []
    seen: set[str] = set()
    for i, item in enumerate(raw["frames"]):
        label = f"{where}: frames[{i}]"
        if not isinstance(item, dict) or set(item) != {
            "file",
            "client_size",
            "notes",
            "expect",
        }:
            raise FrameSetError(
                f"{label}: keys must be exactly file, client_size, notes, expect"
            )
        file, size, notes, expect = (
            item["file"],
            item["client_size"],
            item["notes"],
            item["expect"],
        )
        if not isinstance(file, str) or not file.endswith(".png"):
            raise FrameSetError(f"{label}: file must be a .png name")
        if file in seen:
            raise FrameSetError(f"{label}: {file} is listed twice")
        seen.add(file)
        if (
            not isinstance(size, list)
            or len(size) != 2
            or not all(type(n) is int and n > 0 for n in size)
        ):
            raise FrameSetError(f"{label}: client_size must be [width, height]")
        if not isinstance(notes, str):
            raise FrameSetError(f"{label}: notes must be a string")
        if not isinstance(expect, dict) or not expect:
            raise FrameSetError(
                f"{label}: expect needs at least one reader (an unfinished stub?)"
            )
        entries.append(
            FrameEntry(file, (size[0], size[1]), notes, _parse_expect(expect, label))
        )
    return tuple(entries)


def _parse_expect(expect: dict[str, Any], label: str) -> dict[str, Expected]:
    parsed: dict[str, Expected] = {}
    for reader, reading in expect.items():
        where = f"{label}: expect[{reader!r}]"
        if not isinstance(reading, dict) or set(reading) != {"status", "value"}:
            raise FrameSetError(f"{where}: must be an object with status and value")
        try:
            status = Status(reading["status"])
        except ValueError:
            valid = ", ".join(s.value for s in Status)
            raise FrameSetError(
                f"{where}: status {reading['status']!r} is not one of {valid}"
            ) from None
        value = reading["value"]
        if status is Status.READ and value is None:
            raise FrameSetError(f"{where}: a read status needs a value")
        if status is not Status.READ and value is not None:
            raise FrameSetError(f"{where}: a {status.value} status carries no value")
        parsed[reader] = Expected(status, value)
    return parsed


def load_expected(path: Path) -> tuple[FrameEntry, ...]:
    with path.open(encoding="utf-8") as fh:
        return parse_entries(json.load(fh), path.name)


def open_frame_set(tag: str, frames_root: Path = FRAMES_ROOT) -> FrameSet:
    """
    The frames of `tag`, with their expected readings.

    :raises FrameSetMissing: when the PNGs (or the committed readings) aren't
        there; the message is the command that fetches them.
    """
    directory = frames_root / tag
    readings = TESTS_FRAMES / f"{tag}.json"
    if not directory.is_dir() or not readings.is_file():
        raise FrameSetMissing(
            f"frame set {tag!r} isn't on disk: run `python scripts/fetch_frames.py {tag}`"
        )
    entries = load_expected(readings)
    missing = [e.file for e in entries if not (directory / e.file).is_file()]
    if missing:
        raise FrameSetMissing(
            f"{directory} lacks {len(missing)} frame(s), first {missing[0]}: "
            f"run `python scripts/fetch_frames.py {tag}`"
        )
    return FrameSet(tag, directory, entries)
