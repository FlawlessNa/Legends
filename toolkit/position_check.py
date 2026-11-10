"""
Position check (#393, epic #302 Part 2, item 11 and decision C1): how the
position readers behave, live beside the client or replayed over a folder of
frames, so they can be calibrated and trusted.

**It sends no keys, ever.** It copies the client's pixels (`botting.screen`'s
Desktop Duplication, as the bot does) and draws in its own OpenCV window. The
only keys it reads are the ones pressed in that window. It imports nothing that
sends input.

    python -m toolkit.position_check live --map "Victoria Road: Ellinia"
    python -m toolkit.position_check live --map auto --still
    python -m toolkit.position_check replay data/frames/v3 --labels tests/frames/v3.json

**The production readers, nothing else.** For each map it builds what the bot
builds (`MapleBot._set_world_map`, `MapMixin`): the `FrameCheck`, the
`MinimapReader` given the map's id, and `PositionFusion` with the map's
`CameraReader` (given the same `FrameCheck`) and a `NameTagFinder`, or a
`YoloCharacterFinder` with `--weights`. The camera reader and the finder are
passed to fusion through taps that keep what each returned to it. A camera or
characters read that fusion didn't ask for is `skipped`: fusion stops at the
minimap when the minimap gives no position, and at the camera when it is
`UNSURE`. One finder serves the whole run, as one serves the bot: our name tag
is learned once.

**What it records.** One CSV row per frame (`FIELDS`): every read's status and
value (the minimap's position, the camera, the characters found, the fused
position), the play-area read and how far it is from the minimap's, and the
frame's age when the fused reading is made (`age_ms`, from `captured_at` to the
end of the read). The **play-area read** is the fused position when it is
`fused`. Otherwise it is the character found nearest the minimap's position:
among those the finder marks ours once it can tell ours apart, else among all of
them. So a character too far from the minimap, or two in the window, still
shows how far the reads are apart.

**At the end** it prints, and writes beside the CSV, per map:

- how often each read isn't `READ`, by status, out of the frames it was asked
  on;
- how often the position is `fused`, `coarse` (the minimap's fallback) and
  `UNSURE`, and the longest run of `UNSURE` positions;
- how often our tag was found outside the window (`Fusion.own_elsewhere`);
- the frame's age at the fused read;
- with the character standing still (`--still`, or `s` in the window), each
  read's spread in virtual px: minimap, play area, fused.

Frames that aren't the client's (`Frame.ok` false: the client not in front, as
when this window has the focus) are written to the CSV but left out of the
rates: the bot keeps the client in front.

**Live** reads a frame every `--interval` seconds (0.1, the bot's refresh of
`current_frame` and `minimap_reading`) and skips frames that repeat the last
copy. With `--minimap-lag`, the minimap is read on the frame grabbed that long
before the one fusion reads. In the bot, the minimap reading and the frame are
two attributes each refreshed on its own 0.1 s threshold, so they can come from
different grabs. A walk read with `--minimap-lag 0.1` against one read without
it shows what that costs. `--map auto` identifies the map as the bot does
(`MapIdentifier`, with the minimap's banner shown or not), and again after
`REIDENTIFY_AFTER` frames in a row with no minimap position, which follows the
character through a portal. Keys in the window: `q` quits, space pauses, `s`
marks the character standing still or not, `f` saves the last frame read while
the client was in front, `c` clears the trails.

**Saved frames** go to `<out>/frames/`, laid out as `toolkit/capture_frames.py`
lays them out (#308): the PNG, and a stub entry in `frames.json` for a person to
complete. This tool fills the stub's `expect.map_id` with the map it read on,
and a `notes` line with what it read. Only frames that `FrameCheck.frame_usable`
passes are saved. The PNGs can show other players' names: they go only to the
private `legends-frames` repository, never into git.

**Replay** reads a folder of PNGs. The map of each frame comes from `--map`, or
from a manifest's `expect.map_id` (`--labels`; by default the folder's
`frames.json`). It reads them map by map, in the manifest's order within each
map, as the frame tests do. A frame with no map is written with every read
`skipped`. A replayed frame is captured when it is loaded, so its times
(`age_ms`, `captured_at`, and the seconds a run of `UNSURE` spans) are only the
readers' own.

**During a Session.** It can run beside one, but it doesn't share the Session's
capture. It runs in its own process, with its own Desktop Duplication and its
own readers. It reads neither the Session's frames nor its telemetry, so what it
reads can differ from the bot's by a grab, and its reads take CPU from the bot's
process. It hasn't been run beside a Session yet. If DXGI refuses a second
duplication, the frames come back not `ok`, with the reason, and never as a
reading.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading, Status
from game_data.archive import Pixels
from game_data.catalogue import Catalogue
from game_data.config import CONFIG, STORE
from maple.model.world import MinimapTransform, WorldMap
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapView
from maple.screen.position import (
    Camera,
    CameraReader,
    CharacterFinder,
    CharacterSighting,
    Fusion,
    NameTagFinder,
    PositionFusion,
    PositionSource,
    YoloCharacterFinder,
)
from maple.screen.position.fusion import CameraSource
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from toolkit.capture_frames import MANIFEST, save_frame

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO / "data" / "position_check"

BOT_REFRESH: Final = 0.1
"""Seconds: how often the bot refreshes `current_frame` and `minimap_reading`
(`MapleBot`, `MapMixin.MINIMAP_POS_REFRESH_RATE`), and live mode's default
interval."""

REIDENTIFY_AFTER: Final = 20
"""Frames in a row with no minimap position after which `--map auto` checks
which map the minimap shows again."""

HISTORY: Final = 64
"""Frames kept for `--minimap-lag`."""

SKIPPED: Final = "skipped"
"""The status of a read fusion didn't ask for, or of every read on a frame with
no map."""

READS: Final[tuple[str, ...]] = ("minimap", "camera", "characters", "position")
"""The reads whose statuses are counted, in the order they are reported."""

FIELDS: Final[tuple[str, ...]] = (
    "frame", "map_id", "client_width", "client_height", "frame_ok",
    "frame_reason", "still", "captured_at", "age_ms", "minimap_age_ms",
    "minimap_status", "minimap_detail", "minimap_state", "marker_x", "marker_y",
    "minimap_x", "minimap_y",
    "camera_status", "camera_detail", "camera_x", "camera_y", "camera_share",
    "camera_sharpness", "play_area_width", "play_area_height",
    "characters_status", "characters_detail", "characters_found",
    "characters_own", "sightings",
    "play_x", "play_y", "play_dx", "play_dy",
    "position_status", "position_source", "position_x", "position_y",
    "position_detail", "near", "by_tag", "own_elsewhere",
)  # fmt: skip
"""The CSV's columns. Positions are virtual px. `minimap_*` is the minimap's
position: `minimap_status` is the minimap's own status when it isn't read, else
its marker's; `marker_*` is the marker's canvas pixel, `minimap_x`/`y` the
feet's virtual position fusion takes from it. `sightings` lists each character
found as `x:y` in virtual px, with `:own` when the finder marks it ours.
`play_dx`/`dy` are the play-area read minus the minimap's position. Times are
seconds (`captured_at`, from the run's start) and milliseconds (`*_ms`)."""

# ----------------------------------------------------------------- the readers


class MinimapSource(Protocol):
    """The part of `MinimapReader` used here."""

    def read(self, frame: Frame) -> Reading[MinimapView]: ...


class CameraTap:
    """
    Fusion's camera reader, made on its first read as fusion makes it, keeping
    what it last returned.
    """

    def __init__(self, make: Callable[[], CameraSource]) -> None:
        self._make = make
        self._reader: CameraSource | None = None
        self.last: Reading[Camera] | None = None

    def read(self, frame: Frame, seed: Camera | None = None) -> Reading[Camera]:
        if self._reader is None:
            self._reader = self._make()
        self.last = self._reader.read(frame, seed)
        return self.last


class FinderTap:
    """A `CharacterFinder` that keeps what `find` last returned."""

    def __init__(self, finder: CharacterFinder) -> None:
        self.finder = finder
        self.last: Reading[list[CharacterSighting]] | None = None

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        self.last = self.finder.find(frame)
        return self.last

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        return self.finder.learn_own(frame, near)


@dataclass(frozen=True)
class FrameRead:
    """
    One frame, and what each read said on it.

    :ivar minimap: `None` on a frame with no map.
    :ivar minimap_at: `captured_at` of the frame the minimap was read on.
    :ivar camera: `None` when fusion didn't ask for it.
    :ivar characters: `None` when fusion didn't ask for them.
    :ivar fusion: `None` on a frame with no map.
    :ivar read_at: `time.monotonic()` when the fused reading was made.
    """

    name: str
    map_id: int | None
    frame: Frame
    minimap: Reading[MinimapView] | None
    minimap_at: float
    camera: Reading[Camera] | None
    characters: Reading[list[CharacterSighting]] | None
    fusion: Fusion | None
    read_at: float
    still: bool = False


class MapReaders:
    """One map's readers, wired as the bot wires them."""

    def __init__(
        self,
        map_id: int,
        minimap: MinimapSource,
        transform: MinimapTransform,
        camera: Callable[[], CameraSource],
        finder: FinderTap,
        *,
        frame_check: FrameCheck | None = None,
        world_map: WorldMap | None = None,
    ) -> None:
        """
        :param camera: Makes the map's camera reader, on the first camera read.
        :param finder: The run's finder, shared by every map.
        """
        self.map_id = map_id
        self.minimap = minimap
        self.camera = CameraTap(camera)
        self.finder = finder
        self.fusion = PositionFusion(transform, lambda: self.camera, finder)
        self.frame_check = frame_check
        self.world_map = world_map
        self.render: Pixels | None = None
        """The static render the camera reader matches against, once made."""

    @classmethod
    def load(
        cls,
        map_id: int,
        finder: FinderTap,
        *,
        store: Path = STORE,
        config: Path = CONFIG,
    ) -> MapReaders:
        """
        The bot's readers for `map_id`, from the game data store.

        :raises StartupRefused: As `load_reader_sprites` does.
        :raises LookupError: The store's catalogue has no map `map_id`.
        :raises ValueError: The map has no minimap.
        """
        profile = Profile(job="", game_map="", map_id=map_id)
        sprites = load_reader_sprites(
            [FRAME_CHECK, MINIMAP], profile, store, config=config
        )
        frame_check = FrameCheck(sprites)
        world_map = WorldMap.load(map_id, root=store)
        if world_map.minimap is None:
            raise ValueError(f"map {map_id} has no minimap")

        def camera() -> CameraSource:
            assert world_map.static_render is not None
            readers.render = world_map.static_render.pixels()
            return CameraReader(
                world_map, frame_check=frame_check, render=readers.render
            )

        readers = cls(
            map_id,
            MinimapReader(sprites, frame_check, map_id=map_id),
            world_map.minimap,
            camera,
            finder,
            frame_check=frame_check,
            world_map=world_map,
        )
        return readers

    def read(
        self,
        frame: Frame,
        minimap_frame: Frame | None = None,
        *,
        name: str = "",
        still: bool = False,
    ) -> FrameRead:
        """
        The position on `frame`, with the minimap read on `minimap_frame`
        (`frame` when not given).
        """
        on = frame if minimap_frame is None else minimap_frame
        minimap = self.minimap.read(on)
        self.camera.last = None
        self.finder.last = None
        fusion = self.fusion.read(frame, minimap)
        return FrameRead(
            name,
            self.map_id,
            frame,
            minimap,
            on.captured_at,
            self.camera.last,
            self.finder.last,
            fusion,
            time.monotonic(),
            still,
        )


def no_map(frame: Frame, name: str, still: bool = False) -> FrameRead:
    """A frame read with no map: every read `skipped`."""
    at = time.monotonic()
    return FrameRead(
        name, None, frame, None, frame.captured_at, None, None, None, at, still
    )


def make_finder(weights: Path | None) -> FinderTap:
    """The run's finder: YOLO's on `weights`, else the name tags'."""
    if weights is None:
        return FinderTap(NameTagFinder())
    return FinderTap(YoloCharacterFinder.from_weights(weights))


def resolve_map(text: str, store: Path = STORE) -> int:
    """
    The id of the map `text` names, as a profile's `map` names it.

    :raises LookupError: As `Catalogue.map` does.
    """
    with Catalogue.latest(store) as catalogue:
        return catalogue.map(int(text) if text.isdigit() else text).id


def is_auto(text: str) -> bool:
    return text.strip().casefold() == "auto"


# ------------------------------------------------------------------- one row


def _minimap_position(
    reading: Reading[MinimapView] | None,
) -> tuple[str, str, Reading[tuple[int, int]] | None]:
    """The minimap's position status and detail, and its marker reading."""
    if reading is None:
        return SKIPPED, "no map", None
    if reading.value is None:
        return reading.status.value, reading.detail, None
    marker = reading.value.self_position
    return marker.status.value, marker.detail, marker


def play_area_read(read: FrameRead) -> tuple[float, float] | None:
    """
    The play area's position: the fused position when it is `fused`; else the
    character found nearest the minimap's, among those marked ours once the
    finder can tell ours apart.
    """
    fusion = read.fusion
    if fusion is None:
        return None
    value = fusion.position.value
    if value is not None and value.source is PositionSource.FUSED:
        return value.x, value.y
    if fusion.minimap is None or not fusion.sightings:
        return None
    found = read.characters.value if read.characters is not None else None
    owns = [s.own for s in found] if found else [False] * len(fusion.sightings)
    places = [
        p
        for p, own in zip(fusion.sightings, owns, strict=True)
        if own or not fusion.by_tag
    ]
    if not places:
        return None
    mx, my = fusion.minimap
    return min(places, key=lambda p: max(abs(p[0] - mx), abs(p[1] - my)))


def _num(value: float | None, digits: int = 1) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def row(read: FrameRead, start: float = 0.0) -> dict[str, str]:
    """
    The CSV row of `read` (`FIELDS`).

    :param start: `time.monotonic()` at the run's start, which `captured_at`
        is measured from.
    """
    frame, fusion = read.frame, read.fusion
    status, detail, marker = _minimap_position(read.minimap)
    view = None if read.minimap is None else read.minimap.value
    camera = read.camera.value if read.camera is not None else None
    found = read.characters.value if read.characters is not None else None
    position = None if fusion is None else fusion.position
    value = None if position is None else position.value
    play = play_area_read(read)
    minimap = None if fusion is None else fusion.minimap
    sightings = (
        ""
        if fusion is None
        else ";".join(
            f"{x:.1f}:{y:.1f}" + (":own" if found and found[i].own else "")
            for i, (x, y) in enumerate(fusion.sightings)
        )
    )

    def status_of(reading: Reading[Any] | None) -> tuple[str, str]:
        if reading is None:
            return SKIPPED, "no map" if fusion is None else "not asked"
        return reading.status.value, reading.detail

    camera_status, camera_detail = status_of(read.camera)
    characters_status, characters_detail = status_of(read.characters)
    if position is None:
        position_status, position_detail = SKIPPED, "no map"
    else:
        position_status, position_detail = position.status.value, position.detail
    return {
        "frame": read.name,
        "map_id": "" if read.map_id is None else str(read.map_id),
        "client_width": str(frame.client_size[0]),
        "client_height": str(frame.client_size[1]),
        "frame_ok": str(int(frame.ok)),
        "frame_reason": frame.reason,
        "still": str(int(read.still)),
        "captured_at": _num(frame.captured_at - start, 3),
        "age_ms": _num((read.read_at - frame.captured_at) * 1000),
        "minimap_age_ms": _num((read.read_at - read.minimap_at) * 1000),
        "minimap_status": status,
        "minimap_detail": detail,
        "minimap_state": "" if view is None else view.state.value,
        "marker_x": ""
        if marker is None or marker.value is None
        else str(marker.value[0]),
        "marker_y": ""
        if marker is None or marker.value is None
        else str(marker.value[1]),
        "minimap_x": "" if minimap is None else str(minimap[0]),
        "minimap_y": "" if minimap is None else str(minimap[1]),
        "camera_status": camera_status,
        "camera_detail": camera_detail,
        "camera_x": "" if camera is None else str(camera.x),
        "camera_y": "" if camera is None else str(camera.y),
        "camera_share": "" if camera is None else _num(camera.share, 3),
        "camera_sharpness": "" if camera is None else _num(camera.sharpness, 3),
        "play_area_width": "" if camera is None else str(camera.play_area[0]),
        "play_area_height": "" if camera is None else str(camera.play_area[1]),
        "characters_status": characters_status,
        "characters_detail": characters_detail,
        "characters_found": "" if found is None else str(len(found)),
        "characters_own": "" if found is None else str(sum(s.own for s in found)),
        "sightings": sightings,
        "play_x": _num(None if play is None else play[0]),
        "play_y": _num(None if play is None else play[1]),
        "play_dx": ""
        if play is None or minimap is None
        else _num(play[0] - minimap[0]),
        "play_dy": ""
        if play is None or minimap is None
        else _num(play[1] - minimap[1]),
        "position_status": position_status,
        "position_source": "" if value is None else value.source.value,
        "position_x": _num(None if value is None else value.x),
        "position_y": _num(None if value is None else value.y),
        "position_detail": position_detail,
        "near": "" if fusion is None else str(fusion.near),
        "by_tag": "" if fusion is None else str(int(fusion.by_tag)),
        "own_elsewhere": "" if fusion is None else str(int(fusion.own_elsewhere)),
    }


# ----------------------------------------------------------------- the rates

_READ = Status.READ.value


@dataclass
class MapRates:
    """
    One map's rates, from its CSV rows.

    :ivar frames: Its rows.
    :ivar counted: Its rows whose frame is the client's (`frame_ok`), which
        every other count is out of.
    :ivar asked: By read, the counted rows it was asked on (not `skipped`).
    :ivar not_read: By read, the statuses other than `read` it gave, counted.
    :ivar sources: The position's source when read, counted.
    :ivar longest_unsure: The longest run of counted rows in a row whose
        position isn't read, and how many seconds it spans.
    :ivar own_elsewhere: Counted rows where our tag was found outside the
        window.
    :ivar ages: The frame's age at the fused read, ms, of every counted row.
    """

    map_id: str
    frames: int = 0
    counted: int = 0
    asked: dict[str, int] = field(default_factory=lambda: dict.fromkeys(READS, 0))
    not_read: dict[str, collections.Counter[str]] = field(
        default_factory=lambda: {r: collections.Counter() for r in READS}
    )
    sources: collections.Counter[str] = field(default_factory=collections.Counter)
    longest_unsure: tuple[int, float] = (0, 0.0)
    own_elsewhere: int = 0
    ages: list[float] = field(default_factory=list)


def map_rates(rows: Iterable[Mapping[str, str]]) -> dict[str, MapRates]:
    """Each map's rates, by `map_id` as the rows give it, in order of first
    appearance; frames with no map are under `""`."""
    rates: dict[str, MapRates] = {}
    runs: dict[str, tuple[int, float | None]] = {}
    for r in rows:
        key = r["map_id"]
        rate = rates.setdefault(key, MapRates(key))
        rate.frames += 1
        if r["frame_ok"] != "1":
            continue
        rate.counted += 1
        for read in READS:
            status = r[f"{read}_status"]
            if status == SKIPPED:
                continue
            rate.asked[read] += 1
            if status != _READ:
                rate.not_read[read][status] += 1
        if r["position_source"]:
            rate.sources[r["position_source"]] += 1
        rate.own_elsewhere += r["own_elsewhere"] == "1"
        if r["age_ms"]:
            rate.ages.append(float(r["age_ms"]))
        length, began = runs.get(key, (0, None))
        at = float(r["captured_at"] or 0.0)
        if r["position_status"] not in (_READ, SKIPPED):
            began = at if length == 0 else began
            length += 1
            span = at - (began or at)
            if length > rate.longest_unsure[0]:
                rate.longest_unsure = (length, span)
        else:
            length, began = 0, None
        runs[key] = (length, began)
    return rates


@dataclass(frozen=True)
class Spread:
    """How much one read moved, in virtual px, with the character still."""

    samples: int
    std: tuple[float, float]
    range: tuple[float, float]


def spreads(rows: Iterable[Mapping[str, str]]) -> dict[str, dict[str, Spread]]:
    """
    By map, each read's spread on the counted rows marked `still`: `minimap`
    (its feet position), `play area` (the play-area read) and `fused` (the
    position as read, `fused` or `coarse`). A read with no sample is left out.
    """
    points: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for r in rows:
        if r["still"] != "1" or r["frame_ok"] != "1":
            continue
        by_read = points.setdefault(r["map_id"], {})
        for name, x, y in (
            ("minimap", "minimap_x", "minimap_y"),
            ("play area", "play_x", "play_y"),
            ("fused", "position_x", "position_y"),
        ):
            if r[x] and r[y]:
                by_read.setdefault(name, []).append((float(r[x]), float(r[y])))
    out: dict[str, dict[str, Spread]] = {}
    for map_id, by_read in points.items():
        out[map_id] = {}
        for name, pts in by_read.items():
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out[map_id][name] = Spread(
                len(pts),
                (statistics.pstdev(xs), statistics.pstdev(ys)),
                (max(xs) - min(xs), max(ys) - min(ys)),
            )
    return out


def _share(n: int, of: int) -> str:
    return f"{n}/{of} ({n / of:.0%})" if of else f"{n}/0"


def summary(
    rows: Sequence[Mapping[str, str]], names: Mapping[str, str] | None = None
) -> str:
    """The end-of-run report: each map's rates, and spreads when still."""
    if not rows:
        return "no frames read"
    names = names or {}
    out: list[str] = []
    still = spreads(rows)
    for key, rate in map_rates(rows).items():
        if key == "":
            out.append(f"no map: {rate.frames} frames, not read")
            continue
        label = f"map {key}" + (f" {names[key]}" if key in names else "")
        out.append(
            f"{label}: {rate.frames} frames, {rate.frames - rate.counted} not the "
            "client's (left out)"
        )
        for read in READS:
            missed = rate.not_read[read]
            n = sum(missed.values())
            why = ", ".join(f"{s} {c}" for s, c in missed.most_common())
            out.append(
                f"  {read:<10} not read {_share(n, rate.asked[read])}"
                + (f" ({why})" if why else "")
            )
        asked = rate.asked["position"]
        out.append(
            f"  position   fused {_share(rate.sources[PositionSource.FUSED.value], asked)}, "
            f"coarse {_share(rate.sources[PositionSource.COARSE.value], asked)}; "
            f"longest run not read: {rate.longest_unsure[0]} frames "
            f"({rate.longest_unsure[1]:.2f} s)"
        )
        out.append(f"  our tag outside the window: {rate.own_elsewhere} frames")
        if rate.ages:
            ages = np.array(rate.ages)
            out.append(
                f"  frame age at the fused read, ms: median {np.median(ages):.0f}, "
                f"p90 {np.percentile(ages, 90):.0f}, max {ages.max():.0f}"
            )
        for name, s in still.get(key, {}).items():
            out.append(
                f"  still, {name:<9} {s.samples} frames: std x {s.std[0]:.1f} "
                f"y {s.std[1]:.1f}; range x {s.range[0]:.1f} y {s.range[1]:.1f} "
                "virtual px"
            )
    return "\n".join(out)


# ------------------------------------------------------------------ the output


class Output:
    """The run's CSV, its summary, and the frames saved."""

    def __init__(self, folder: Path, start: float) -> None:
        self.folder = folder
        self.start = start
        folder.mkdir(parents=True, exist_ok=True)
        self.csv_path = folder / "readings.csv"
        self._file = self.csv_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, FIELDS)
        self._writer.writeheader()
        self.rows: list[dict[str, str]] = []
        self.names: dict[str, str] = {}

    def write(self, read: FrameRead) -> dict[str, str]:
        r = row(read, self.start)
        self._writer.writerow(r)
        self._file.flush()
        self.rows.append(r)
        return r

    def close(self) -> str:
        """Close the CSV; write and return the summary."""
        self._file.close()
        text = summary(self.rows, self.names)
        (self.folder / "summary.txt").write_text(text + "\n", encoding="utf-8")
        return text


class Check(Protocol):
    def frame_usable(self, frame: Frame) -> Reading[None] | None: ...


def save(read: FrameRead, folder: Path, check: Check, start: float = 0.0) -> str | None:
    """
    Save `read`'s frame as `toolkit/capture_frames.py` saves one, with the map
    in its stub's `expect` and what was read in its `notes`. The file name, or
    `None` when `check` refuses the frame.
    """
    file = save_frame(read.frame, folder, check)
    if file is None:
        return None
    manifest = folder / MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    r = row(read, start)
    for entry in data["frames"]:
        if entry["file"] == file:
            entry["notes"] = (
                f"position check: position {r['position_status']} "
                f"{r['position_source']} ({r['position_x']}, {r['position_y']}); "
                f"minimap ({r['minimap_x']}, {r['minimap_y']}); "
                f"camera ({r['camera_x']}, {r['camera_y']})"
            )
            if read.map_id is not None:
                entry["expect"]["map_id"] = {"status": _READ, "value": read.map_id}
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return file


# ------------------------------------------------------------------- replay


def manifest_maps(path: Path) -> list[tuple[str, int | None]]:
    """Each frame of a manifest (`frames.json`, `tests/frames/<tag>.json`),
    with its `expect.map_id` when read."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, int | None]] = []
    for entry in data["frames"]:
        expected = entry.get("expect", {}).get("map_id")
        read = expected is not None and expected.get("status") == _READ
        out.append((entry["file"], int(expected["value"]) if read else None))
    return out


def replay_order(
    folder: Path,
    labels: Path | None,
    map_id: int | None,
    pattern: str = "*.png",
) -> list[tuple[int | None, list[str]]]:
    """
    The frames to replay, by map, in the order they are read: each map's in
    the manifest's order (the folder's sorted otherwise), maps in order of
    first appearance, and the frames with no map last.
    """
    if labels is None and (folder / MANIFEST).is_file():
        labels = folder / MANIFEST
    if labels is not None:
        listed = [(f, map_id or m) for f, m in manifest_maps(labels)]
        present = {p.name for p in folder.glob(pattern)}
        listed = [(f, m) for f, m in listed if f in present]
    else:
        listed = [(p.name, map_id) for p in sorted(folder.glob(pattern))]
    groups: dict[int | None, list[str]] = {}
    for file, m in listed:
        groups.setdefault(m, []).append(file)
    order = [(m, files) for m, files in groups.items() if m is not None]
    if None in groups:
        order.append((None, groups[None]))
    return order


def load_frame(path: Path) -> Frame:
    """A saved frame, as if just captured: `ok` and `fresh`."""
    pixels = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if pixels is None:
        raise OSError(f"can't read {path}")
    height, width = pixels.shape[:2]
    return Frame(pixels, (width, height), time.monotonic(), True, True)


def replay(
    folder: Path,
    finder: FinderTap,
    *,
    labels: Path | None = None,
    map_id: int | None = None,
    pattern: str = "*.png",
    still: bool = False,
    store: Path = STORE,
    config: Path = CONFIG,
) -> Iterator[tuple[FrameRead, MapReaders | None]]:
    """Every frame of `folder` read, map by map (`replay_order`), with the
    readers that read it; one map's readers are let go before the next's."""
    for group_map, files in replay_order(folder, labels, map_id, pattern):
        readers = (
            None
            if group_map is None
            else MapReaders.load(group_map, finder, store=store, config=config)
        )
        for file in files:
            frame = load_frame(folder / file)
            if readers is None:
                yield no_map(frame, file, still), None
            else:
                yield readers.read(frame, name=file, still=still), readers
        del readers


# --------------------------------------------------------------------- live


def lagged(history: Sequence[Frame], lag: float) -> Frame:
    """The newest frame of `history` captured at least `lag` s before its
    last; the oldest when none is that old."""
    last = history[-1]
    if lag <= 0:
        return last
    for frame in reversed(history):
        if frame.captured_at <= last.captured_at - lag:
            return frame
    return history[0]


class Identifier:
    """`--map auto`: the bot's `MapIdentifier`, built once."""

    def __init__(self, store: Path, config: Path) -> None:
        from maple.screen.map_identification import MapCanvases, MapIdentifier
        from maple.screen.minimap_title import MinimapTitleReader

        sprites = load_reader_sprites(
            [FRAME_CHECK, MINIMAP], Profile(job="", game_map=""), store, config=config
        )
        self.frame_check = FrameCheck(sprites)
        minimap = MinimapReader(sprites, self.frame_check)
        self.canvases = MapCanvases.load(store)
        title = MinimapTitleReader(sprites, minimap, self.canvases.titles)
        self._identifier = MapIdentifier(minimap, title, self.canvases)

    def identify(self, frame: Frame) -> Reading[int]:
        return self._identifier.identify(frame)


def map_name(world_map: WorldMap | None) -> str:
    if world_map is None:
        return ""
    return ": ".join(p for p in (world_map.street, world_map.name) if p)


# ------------------------------------------------------------------- window

MM_COLOUR = (255, 200, 0)  # BGR: light blue
PLAY_COLOUR = (0, 220, 0)
FUSED_COLOUR = (255, 0, 255)
OTHER_COLOUR = (0, 200, 255)
GREY = (170, 170, 170)
WHITE = (255, 255, 255)
RED = (60, 60, 255)
PANEL = 480


def _bgr(rgba: Pixels, background: int = 30) -> NDArray[np.uint8]:
    """RGBA over a dark background, as BGR."""
    alpha = rgba[..., 3:4].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32) * alpha + background * (1 - alpha)
    return np.ascontiguousarray(rgb[..., ::-1]).astype(np.uint8)


class Viewer:
    """The side window: the map with each read's trail, the frame, a 1:1 zoom
    with the footholds, and each read's status."""

    TITLE = "position check (sends no keys)"

    def __init__(self, height: int = 700, trail: int = 300) -> None:
        self.height = height
        self.trail = trail
        self.trails: dict[str, collections.deque[tuple[float, float]]] = {}
        self.paused = False
        self._readers: MapReaders | None = None
        self._base: NDArray[np.uint8] | None = None
        self._scale = 1.0
        self.clear()

    def clear(self) -> None:
        self.trails = {
            k: collections.deque(maxlen=self.trail) for k in ("mm", "play", "fused")
        }

    def _map_view(self, readers: MapReaders) -> NDArray[np.uint8]:
        if readers is not self._readers:
            self._readers, self._base = readers, None
            self.clear()
        if self._base is None:
            world_map = readers.world_map
            assert world_map is not None
            b = world_map.bounds
            width, height = b.right - b.left, b.bottom - b.top
            self._scale = min(self.height / height, 900 / width, 1.0)
            if readers.render is not None:
                small = cv2.resize(
                    readers.render, None, fx=self._scale, fy=self._scale,
                    interpolation=cv2.INTER_AREA,
                )  # fmt: skip
                self._base = _bgr(small)
            else:  # drawn on the first camera read
                size = (
                    max(1, int(height * self._scale)),
                    max(1, int(width * self._scale)),
                )
                return np.full((*size, 3), 30, np.uint8)
        return self._base.copy()

    def _to_view(self, p: tuple[float, float]) -> tuple[int, int]:
        assert self._readers is not None
        assert self._readers.world_map is not None
        b = self._readers.world_map.bounds
        return int((p[0] - b.left) * self._scale), int((p[1] - b.top) * self._scale)

    def show(self, read: FrameRead, readers: MapReaders | None, fps: float) -> int:
        """Draw `read`; the key pressed in the window, if any."""
        cv2.imshow(self.TITLE, self.compose(read, readers, fps))
        return cv2.waitKey(1) & 0xFF

    def compose(
        self, read: FrameRead, readers: MapReaders | None, fps: float
    ) -> NDArray[np.uint8]:
        r = row(read)
        points = {
            "mm": _point(r, "minimap_x", "minimap_y"),
            "play": _point(r, "play_x", "play_y"),
            "fused": _point(r, "position_x", "position_y"),
        }
        parts = [self._thumb(read)]
        if readers is not None and readers.world_map is not None:
            left = self._map_view(readers)
            for k, p in points.items():
                if p is not None:
                    self.trails[k].append(p)
            self._draw_map(left, read, points)
            parts.append(self._zoom(readers, read, points))
        else:
            left = np.full((self.height, 600, 3), 30, np.uint8)
        parts.append(self._text(read, r, readers, fps))
        right = _vstack(parts, PANEL)
        h = max(left.shape[0], right.shape[0])
        out = np.zeros((h, left.shape[1] + PANEL + 4, 3), np.uint8)
        out[: left.shape[0], : left.shape[1]] = left
        out[: right.shape[0], left.shape[1] + 4 :] = right
        return out

    def _draw_map(
        self,
        img: NDArray[np.uint8],
        read: FrameRead,
        points: Mapping[str, tuple[float, float] | None],
    ) -> None:
        camera = read.camera.value if read.camera is not None else None
        if camera is not None:
            a = self._to_view((camera.x, camera.y))
            b = self._to_view(
                (camera.x + camera.play_area[0], camera.y + camera.play_area[1])
            )
            cv2.rectangle(img, a, b, GREY, 1)
        colours = {"mm": MM_COLOUR, "play": PLAY_COLOUR, "fused": FUSED_COLOUR}
        for k, trail in self.trails.items():
            pts = np.array([self._to_view(p) for p in trail], np.int32)
            if len(pts) > 1:
                cv2.polylines(img, [pts], False, colours[k], 1, cv2.LINE_AA)
        _markers(img, read, points, self._to_view, 6)

    def _zoom(
        self,
        readers: MapReaders,
        read: FrameRead,
        points: Mapping[str, tuple[float, float] | None],
    ) -> NDArray[np.uint8]:
        """The map at 1:1 around the position, with the footholds in white."""
        zw, zh = PANEL, 260
        img = np.full((zh, zw, 3), 30, np.uint8)
        centre = points["fused"] or points["play"] or points["mm"]
        world_map = readers.world_map
        if centre is None or world_map is None:
            return img
        b = world_map.bounds
        x0, y0 = int(centre[0]) - zw // 2, int(centre[1]) - zh // 2
        render = readers.render
        if render is not None:
            rx0, ry0 = x0 - b.left, y0 - b.top
            sx0, sy0 = max(0, rx0), max(0, ry0)
            sx1, sy1 = min(render.shape[1], rx0 + zw), min(render.shape[0], ry0 + zh)
            if sx1 > sx0 and sy1 > sy0:
                img[sy0 - ry0 : sy1 - ry0, sx0 - rx0 : sx1 - rx0] = _bgr(
                    render[sy0:sy1, sx0:sx1]
                )
        for platform in world_map.platforms:
            for f in platform.footholds:
                cv2.line(img, (f.x1 - x0, f.y1 - y0), (f.x2 - x0, f.y2 - y0), WHITE, 1)

        def to(p: tuple[float, float]) -> tuple[int, int]:
            return int(p[0] - x0), int(p[1] - y0)

        _markers(img, read, points, to, 7)
        _put(img, "1:1, white: footholds", (4, zh - 6), GREY)
        return img

    def _thumb(self, read: FrameRead) -> NDArray[np.uint8]:
        pixels = read.frame.pixels
        if pixels.size == 0:
            return np.zeros((10, PANEL, 3), np.uint8)
        k = PANEL / pixels.shape[1]
        img = cv2.resize(pixels, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)

        def at(x: float, y: float) -> tuple[int, int]:
            return int(x * k), int(y * k)

        view = None if read.minimap is None else read.minimap.value
        if view is not None and view.map_area is not None:
            a = view.map_area
            cv2.rectangle(img, at(a.left, a.top), at(a.right, a.bottom), MM_COLOUR, 1)
        found = read.characters.value if read.characters is not None else None
        for s in found or []:
            colour = PLAY_COLOUR if s.own else OTHER_COLOUR
            if s.box is not None:
                cv2.rectangle(img, at(*s.box[:2]), at(*s.box[2:]), colour, 1)
            cv2.drawMarker(img, at(*s.feet), colour, cv2.MARKER_CROSS, 8, 1)
        return img

    def _text(
        self,
        read: FrameRead,
        r: Mapping[str, str],
        readers: MapReaders | None,
        fps: float,
    ) -> NDArray[np.uint8]:
        def colour(status: str, ok: tuple[int, int, int]) -> tuple[int, int, int]:
            return ok if status == _READ else (GREY if status == SKIPPED else RED)

        flags = ("  STILL" if read.still else "") + ("  paused" if self.paused else "")
        name = "" if readers is None else map_name(readers.world_map)
        minimap = (
            f"MINIMAP  {r['minimap_status']} ({r['minimap_x']}, {r['minimap_y']}) "
            f"canvas ({r['marker_x']}, {r['marker_y']})"
        )
        camera = (
            f"CAMERA   {r['camera_status']} ({r['camera_x']}, {r['camera_y']}) "
            f"share {r['camera_share']} sharp {r['camera_sharpness']}"
        )
        characters = (
            f"CHARS    {r['characters_status']} found {r['characters_found']}, "
            f"ours {r['characters_own']}, near {r['near']}, by tag {r['by_tag']}"
        )
        play = (
            f"PLAY     ({r['play_x']}, {r['play_y']})  minimap to play: "
            f"dx {r['play_dx']} dy {r['play_dy']}"
        )
        position = (
            f"POSITION {r['position_status']} {r['position_source']} "
            f"({r['position_x']}, {r['position_y']})"
        )
        lines = [
            (f"{read.name}  {fps:.1f} fps{flags}", WHITE),
            (f"map {r['map_id'] or '-'} {name}", WHITE),
            (minimap, colour(r["minimap_status"], MM_COLOUR)),
            (f"  {r['minimap_detail']}", GREY),
            (camera, colour(r["camera_status"], GREY)),
            (f"  {r['camera_detail']}", GREY),
            (characters, colour(r["characters_status"], OTHER_COLOUR)),
            (play, PLAY_COLOUR),
            (position, colour(r["position_status"], FUSED_COLOUR)),
            (f"  {r['position_detail']}", GREY),
            (f"age {r['age_ms']} ms (minimap's frame {r['minimap_age_ms']} ms)", GREY),
        ]
        if r["own_elsewhere"] == "1":
            lines.append(("OUR TAG FOUND OUTSIDE THE WINDOW", RED))
        if not read.frame.ok:
            lines.append((f"not the client's: {read.frame.reason}"[:80], RED))
        lines.append(("q quit, space pause, s still, f save frame, c clear", GREY))
        img = np.zeros((18 * len(lines) + 8, PANEL, 3), np.uint8)
        for i, (text, c) in enumerate(lines):
            _put(img, text[:84], (4, 16 + 18 * i), c)
        return img


def _point(r: Mapping[str, str], x: str, y: str) -> tuple[float, float] | None:
    return (float(r[x]), float(r[y])) if r[x] and r[y] else None


def _markers(
    img: NDArray[np.uint8],
    read: FrameRead,
    points: Mapping[str, tuple[float, float] | None],
    to: Callable[[tuple[float, float]], tuple[int, int]],
    radius: int,
) -> None:
    for s in read.fusion.sightings if read.fusion is not None else ():
        cv2.circle(img, to(s), 3, OTHER_COLOUR, -1)
    if (p := points["mm"]) is not None:
        cv2.circle(img, to(p), radius, MM_COLOUR, 2)
    if (p := points["play"]) is not None:
        cv2.drawMarker(img, to(p), PLAY_COLOUR, cv2.MARKER_CROSS, 2 * radius + 4, 2)
    if (p := points["fused"]) is not None:
        x, y = to(p)
        cv2.rectangle(
            img, (x - radius, y - radius), (x + radius, y + radius), FUSED_COLOUR, 2
        )


def _put(
    img: NDArray[np.uint8], text: str, at: tuple[int, int], colour: tuple[int, int, int]
) -> None:
    cv2.putText(img, text, at, cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)


def _vstack(parts: list[NDArray[np.uint8]], width: int) -> NDArray[np.uint8]:
    out = np.zeros((sum(p.shape[0] + 4 for p in parts), width, 3), np.uint8)
    y = 0
    for p in parts:
        out[y : y + p.shape[0], : min(width, p.shape[1])] = p[:, :width]
        y += p.shape[0] + 4
    return out


# ---------------------------------------------------------------------- main


class _Session:
    """What a run keeps between frames: its output, window and keys."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.start = time.monotonic()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.output = Output(args.out or OUT_ROOT / stamp, self.start)
        self.viewer = None if args.headless else Viewer(args.view_height, args.trail)
        self.still: bool = args.still
        self.last_usable: tuple[FrameRead, Check] | None = None
        self._last_at = time.perf_counter()
        self._fps = 0.0

    def record(self, read: FrameRead, readers: MapReaders | None) -> None:
        r = self.output.write(read)
        if readers is not None and readers.world_map is not None:
            self.output.names[str(readers.map_id)] = map_name(readers.world_map)
        if read.frame.ok and readers is not None and readers.frame_check is not None:
            self.last_usable = (read, readers.frame_check)
        now = time.perf_counter()
        rate = 1 / max(now - self._last_at, 1e-6)
        self._fps = 0.8 * self._fps + 0.2 * rate if self._fps else rate
        self._last_at = now
        if self.viewer is None:
            print(
                f"{read.name:36s} {r['map_id']:>10s} mm {r['minimap_status']:>7s} "
                f"cam {r['camera_status']:>7s} chars {r['characters_status']:>7s} "
                f"pos {r['position_status']:>7s} {r['position_source']:>6s} "
                f"({r['position_x']}, {r['position_y']}) dx {r['play_dx']} dy {r['play_dy']}"
            )

    def keys(self, read: FrameRead, readers: MapReaders | None, wait: float) -> bool:
        """Show `read` and handle the window's keys for `wait` s at least;
        False to quit."""
        if self.viewer is None:
            if wait > 0:
                time.sleep(wait)
            return True
        viewer = self.viewer
        key = viewer.show(read, readers, self._fps)
        until = time.perf_counter() + wait
        while True:
            if key in (ord("q"), 27):
                return False
            if key == ord(" "):
                viewer.paused = not viewer.paused
            elif key == ord("s"):
                self.still = not self.still
                print(f"standing still: {'yes' if self.still else 'no'}")
            elif key == ord("c"):
                viewer.clear()
            elif key == ord("f"):
                self.save()
            if key != 255:
                cv2.imshow(viewer.TITLE, viewer.compose(read, readers, self._fps))
            if not viewer.paused and time.perf_counter() >= until:
                return True
            key = cv2.waitKey(20) & 0xFF

    def save(self) -> None:
        if self.last_usable is None:
            print("no frame read with the client in front yet: nothing saved")
            return
        read, check = self.last_usable
        file = save(read, self.output.folder / "frames", check, self.start)
        if file is None:
            refused = check.frame_usable(read.frame)
            print(f"not saved: {refused.detail if refused else 'not usable'}")
        else:
            print(f"saved {self.output.folder / 'frames' / file}")

    def close(self) -> None:
        if self.viewer is not None:
            cv2.destroyAllWindows()
        print(self.output.close())
        print(f"readings: {self.output.csv_path}")


def run_replay(args: argparse.Namespace) -> int:
    finder = make_finder(args.weights)
    map_id = None if args.map is None else resolve_map(args.map, args.store)
    session = _Session(args)
    try:
        for read, readers in replay(
            args.folder,
            finder,
            labels=args.labels,
            map_id=map_id,
            pattern=args.glob,
            still=args.still,
            store=args.store,
        ):
            read = _with_still(read, session.still)
            session.record(read, readers)
            if not session.keys(read, readers, args.delay / 1000):
                break
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


def _with_still(read: FrameRead, still: bool) -> FrameRead:
    if read.still == still:
        return read
    return FrameRead(
        read.name, read.map_id, read.frame, read.minimap, read.minimap_at,
        read.camera, read.characters, read.fusion, read.read_at, still,
    )  # fmt: skip


def run_live(args: argparse.Namespace) -> int:
    from botting.screen import frame_source
    from maple.screen.client import find_client

    handle = find_client()
    source = frame_source()
    finder = make_finder(args.weights)
    auto = is_auto(args.map)
    identifier = Identifier(args.store, CONFIG) if auto else None
    map_id = None if auto else resolve_map(args.map, args.store)
    readers: MapReaders | None = None
    history: collections.deque[Frame] = collections.deque(maxlen=HISTORY)
    session = _Session(args)
    misses, n, due = 0, 0, 0.0
    try:
        while True:
            pause = due - time.monotonic()
            if pause > 0:
                time.sleep(min(pause, 0.01))
                continue
            frame = source.grab(handle)
            if not frame.fresh:  # the last copy again, or none at all
                time.sleep(0.005)
                continue
            due = time.monotonic() + args.interval
            history.append(frame)
            n += 1
            name = f"live {n}"
            if (
                identifier is not None
                and frame.ok
                and (map_id is None or misses >= REIDENTIFY_AFTER)
            ):
                misses = 0
                found = identifier.identify(frame)
                if found.value is not None and found.value != map_id:
                    map_id, readers = found.value, None
                    print(
                        f"map: {identifier.canvases[map_id].title} ({map_id}): {found.detail}"
                    )
                elif map_id is None:
                    print(
                        f"map not identified yet: {found.status.value} {found.detail}"
                    )
            if map_id is None:
                read = no_map(frame, name, session.still)
            else:
                if readers is None:
                    readers = MapReaders.load(map_id, finder, store=args.store)
                minimap_frame = lagged(history, args.minimap_lag)
                read = readers.read(
                    frame, minimap_frame, name=name, still=session.still
                )
                marker = _minimap_position(read.minimap)[0]
                misses = misses + 1 if frame.ok and marker != _READ else 0
            session.record(read, readers)
            if not session.keys(read, readers, 0):
                break
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m toolkit.position_check",
        description="How the position readers behave, live or on saved frames. "
        "Sends no keys.",
    )
    sub = p.add_subparsers(dest="mode", required=True)
    live = sub.add_parser("live", help="beside the running client")
    live.add_argument("--map", required=True, help='a game map name or id, or "auto"')
    live.add_argument(
        "--interval", type=float, default=BOT_REFRESH,
        help=f"seconds between reads (default {BOT_REFRESH}, the bot's refresh)",
    )  # fmt: skip
    live.add_argument(
        "--minimap-lag", type=float, default=0.0,
        help="read the minimap on the frame grabbed this many seconds before "
        "the one fusion reads (the bot's worst case is 0.1)",
    )  # fmt: skip
    rep = sub.add_parser("replay", help="over a folder of saved frames")
    rep.add_argument("folder", type=Path)
    rep.add_argument(
        "--labels", type=Path,
        help="a manifest naming each frame's map (default: the folder's frames.json)",
    )  # fmt: skip
    rep.add_argument("--map", help="every frame's map, a game map name or id")
    rep.add_argument("--glob", default="*.png")
    rep.add_argument(
        "--delay", type=float, default=1.0, help="ms per frame in the window"
    )
    for each in (live, rep):
        each.add_argument(
            "--still", action="store_true", help="the character stands still"
        )
        each.add_argument(
            "--weights", type=Path, help="YOLO weights: its finder, not the name tags'"
        )
        each.add_argument(
            "--out", type=Path, help=f"output folder (default {OUT_ROOT}/<time>)"
        )
        each.add_argument(
            "--store", type=Path, default=STORE, help="the game data store"
        )
        each.add_argument(
            "--headless", action="store_true", help="no window: a line per frame"
        )
        each.add_argument("--trail", type=int, default=300)
        each.add_argument("--view-height", type=int, default=700)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return run_live(args) if args.mode == "live" else run_replay(args)


if __name__ == "__main__":
    sys.exit(main())
