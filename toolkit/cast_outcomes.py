"""
Cast-outcome report for tuning a reach: which casts hit, which missed, which mobs were skipped (#640, epic #631).

Offline. It reads a recorded Session, sends nothing and reads nothing from the
game. It prints numbers only: no frame is shown or written, and no name is read
or printed.

    python -m toolkit.cast_outcomes logs/<session dir>
    python -m toolkit.cast_outcomes logs/<session dir> --cast-time 0.8 --video D:/rec.avi

**What it reads.** ``telemetry.jsonl``'s ``combat.mobs_hit`` and
``combat.partial_reach``, and the video ``recording.started`` names (``--video``
overrides it), mapped to the Session's clock by ``recording.checkpoint``
(``botting.session.frames``). Both events carry each mob's box from the feet in
client px, the feet in client px and the client area's top left in screen px
(``FeetAnchor``, #640), which put a box on a frame of the video (the whole
screen, 1:1 with client px). A Session recorded before #640 has none of it,
and is refused.

**Hit or miss.** For each ``combat.mobs_hit``, the video frames from the event
to ``--cast-time`` seconds after it are searched, over each counted mob's box,
for a damage number: any digit of the catalogue's ``damage_digits`` sets that
deal damage to a mob (``DAMAGE_SETS``: ``NoRed`` and ``NoCri``; the other
colours, such as the damage the character takes, don't count), matched by
template. The search region is the box, ``MARGIN_X`` px wider each side and
reaching ``RISE`` px above it (a number rises above the head,
``game_data.scenes.occluders``); both grow with ``--scale``, as the numbers
do. A mob with a number is **hit**. A cast with no
mob hit is a **miss**.

**Skipped mobs.** Each ``combat.partial_reach`` is listed, with its attack and
the offsets of the mobs in a swing and out of the reach.

Every threshold here is an Expectation, read off no client: ``--cast-time``,
``--tolerance`` (how far a digit may differ from its sprite, 0 exact to 1) and
``--scale`` (how much the client upscales its play area; 1 for a client at the
play area's size). The first real recording is what tunes them.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.session.frames import FrameError, frame_index_at
from botting.session.reading import (
    Record,
    Session,
    SessionError,
    load_session,
    telemetry_path,
)
from botting.telemetry_events import RECORDING_CHECKPOINT, RECORDING_STARTED
from game_data.scenes.occluders import DAMAGE_SETS

COMBAT_MOBS_HIT: Final = "combat.mobs_hit"
COMBAT_PARTIAL_REACH: Final = "combat.partial_reach"

#: Seconds after a `combat.mobs_hit` whose frames are searched. An Expectation.
CAST_TIME: Final = 1.0
#: Screen px added to each side of a mob's box when searching it.
MARGIN_X: Final = 20
#: Screen px above a mob's box searched: `DAMAGE_RISE` and a digit's height.
RISE: Final = 90
#: A digit matches when its normalised squared difference is at most this.
TOLERANCE: Final = 0.05
#: A digit sprite is taken for a number when it has at least this many opaque
#: pixels, so that a stray speck is not.
MIN_OPAQUE: Final = 20

_ANCHOR: Final = ("feet_x", "feet_y", "client_left", "client_top")

Box = tuple[int, int, int, int]
Frame = NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class Template:
    """One digit sprite: its BGR pixels, and its alpha as a 0/255 mask."""

    pixels: Frame
    mask: Frame


@dataclass(frozen=True, slots=True)
class Cast:
    """A `combat.mobs_hit` judged: how many of its counted mobs had a number."""

    t: float
    attack: str
    mobs: int
    hit: int

    @property
    def missed(self) -> bool:
        return self.hit == 0


@dataclass(frozen=True, slots=True)
class Skipped:
    """A `combat.partial_reach`."""

    t: float
    attack: str
    offsets: tuple[Box, ...]


class ReportError(Exception):
    """The Session can't be reported on; the message is meant to be printed."""


def template(rgba: NDArray[np.uint8], scale: float = 1.0) -> Template:
    """A sprite's RGBA pixels as a `Template`, scaled by `scale`."""
    if scale != 1.0:
        rgba = cv2.resize(rgba, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    mask = np.where(rgba[..., 3] > 127, 255, 0).astype(np.uint8)
    return Template(bgr, mask)


def has_number(
    frame: Frame, region: Box, templates: Sequence[Template], tolerance: float
) -> bool:
    """
    Whether any template's digit is in `region` of `frame` (screen px, clipped
    to the frame): a normalised squared difference of at most `tolerance`
    over the sprite's opaque pixels.
    """
    height, width = frame.shape[:2]
    left, top = max(region[0], 0), max(region[1], 0)
    right, bottom = min(region[2], width), min(region[3], height)
    crop = frame[top:bottom, left:right]
    for found in templates:
        th, tw = found.pixels.shape[:2]
        if crop.shape[0] < th or crop.shape[1] < tw:
            continue
        score = cv2.matchTemplate(
            crop, found.pixels, cv2.TM_SQDIFF_NORMED, mask=found.mask
        )
        score = score[np.isfinite(score)]
        if score.size and float(score.min()) <= tolerance:
            return True
    return False


def mob_regions(payload: Mapping[str, Any], scale: float = 1.0) -> list[Box]:
    """
    Where to search for each counted mob's number, in screen px. `scale` is
    how much the client upscales its play area: it grows the margins.
    """
    margin, rise = round(MARGIN_X * scale), round(RISE * scale)
    ox = round(payload["feet_x"]) + payload["client_left"]
    oy = round(payload["feet_y"]) + payload["client_top"]
    regions: list[Box] = []
    for mob in payload["mobs"]:
        regions.append(
            (
                ox + mob["left"] - margin,
                oy + mob["top"] - rise,
                ox + mob["right"] + margin,
                oy + mob["bottom"],
            )
        )
    return regions


def judge(
    record: Record,
    frames: Sequence[Frame],
    templates: Sequence[Template],
    tolerance: float,
    scale: float = 1.0,
) -> Cast:
    """A `combat.mobs_hit` judged over the `frames` of its cast time."""
    regions = mob_regions(record.payload, scale)
    hit = sum(
        any(has_number(frame, region, templates, tolerance) for frame in frames)
        for region in regions
    )
    return Cast(record.t, str(record.payload["attack"]), len(regions), hit)


def skipped(record: Record) -> Skipped:
    """A `combat.partial_reach`."""
    return Skipped(
        record.t,
        str(record.payload["attack"]),
        tuple(
            (m["left"], m["top"], m["right"], m["bottom"])
            for m in record.payload["mobs"]
        ),
    )


def check_anchored(records: Sequence[Record]) -> None:
    """
    :raises ReportError: when an event lacks the fields that place its boxes.
    """
    for record in records:
        missing = [key for key in _ANCHOR if key not in record.payload]
        if missing:
            raise ReportError(
                f"{record.event_type} at line {record.line} has no "
                f"{', '.join(missing)}: this Session was recorded before #640 added "
                "where the feet and the client are on the screen, so its mob boxes "
                "can't be placed on the video. Record a new Session."
            )


def frame_ranges(
    session: Session, hits: Sequence[Record], cast_time: float
) -> list[range]:
    """The video frame indices of each hit's cast time."""
    checkpoints = [
        (r.t, index)
        for r in session.records
        if r.event_type == RECORDING_CHECKPOINT
        and isinstance(index := r.payload.get("frame_index"), int)
    ]
    ranges: list[range] = []
    for record in hits:
        first = frame_index_at(checkpoints, record.t)
        last = frame_index_at(checkpoints, record.t + cast_time)
        ranges.append(range(first, last + 1))
    return ranges


def read_frames(video: Path, indices: Sequence[range]) -> Iterator[list[Frame]]:
    """
    The frames of each range, in order. Frames past the video's end are left out.
    :raises ReportError: when the video can't be read.
    """
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise ReportError(f"{video} cannot be read as a video")
        for wanted in indices:
            frames: list[Frame] = []
            capture.set(cv2.CAP_PROP_POS_FRAMES, wanted.start)
            for _ in wanted:
                ok, image = capture.read()
                if not ok:
                    break
                frames.append(image)
            yield frames
    finally:
        capture.release()


def video_path(session: Session, override: Path | None) -> Path:
    """
    :raises ReportError: with no recording, or no video file.
    """
    if override is not None:
        return override
    started = session.first(RECORDING_STARTED)
    if started is None or not isinstance(started.payload.get("path"), str):
        raise ReportError("no recording: there is no recording.started record")
    path = Path(started.payload["path"])
    if not path.is_file():
        raise ReportError(f"the video {path} no longer exists")
    return path


def catalogue_templates(scale: float, root: Path | None = None) -> list[Template]:
    """
    The digit sprites of `DAMAGE_SETS` in the latest catalogue of the store at
    `root` (the default store when None), as templates scaled by `scale`.
    :raises ReportError: when there are none.
    """
    from game_data.catalogue import Catalogue
    from game_data.render import Images

    with Catalogue.latest(*([] if root is None else [root])) as cat:
        images = Images(cat.store.images)
        found = [
            template(images.get(digit.image), scale)
            for digit in cat.damage_digits()
            if digit.image is not None
            and digit.digit_set.rstrip("0123456789") in DAMAGE_SETS
        ]
    found = [t for t in found if int(np.count_nonzero(t.mask)) >= MIN_OPAQUE]
    if not found:
        raise ReportError("the catalogue has no damage digit sprites")
    return found


def report(
    session: Session,
    video: Path,
    templates: Sequence[Template],
    *,
    cast_time: float = CAST_TIME,
    tolerance: float = TOLERANCE,
    scale: float = 1.0,
) -> tuple[list[Cast], list[Skipped]]:
    """
    Every `combat.mobs_hit` judged, and every `combat.partial_reach`.
    :raises ReportError: when the Session can't be reported on.
    """
    hits = [r for r in session.records if r.event_type == COMBAT_MOBS_HIT]
    partials = [r for r in session.records if r.event_type == COMBAT_PARTIAL_REACH]
    check_anchored([*hits, *partials])
    casts: list[Cast] = []
    if hits:
        try:
            ranges = frame_ranges(session, hits, cast_time)
        except FrameError as exc:
            raise ReportError(str(exc)) from None
        for record, frames in zip(hits, read_frames(video, ranges), strict=True):
            casts.append(judge(record, frames, templates, tolerance, scale))
    return casts, [skipped(r) for r in partials]


def lines(casts: Sequence[Cast], partials: Sequence[Skipped]) -> list[str]:
    """The table and the totals, numbers and attack names only."""
    out = [f"{'t (s)':>9}  {'attack':<24} {'mobs':>4} {'hit':>4}  outcome"]
    for cast in casts:
        out.append(
            f"{cast.t:9.2f}  {cast.attack:<24} {cast.mobs:>4} {cast.hit:>4}  "
            f"{'MISS' if cast.missed else 'hit'}"
        )
    out.append("")
    out.append("per attack: casts, casts that hit, misses, mobs counted, mobs hit")
    by_attack: dict[str, list[Cast]] = defaultdict(list)
    for cast in casts:
        by_attack[cast.attack].append(cast)
    for attack, group in sorted(by_attack.items()):
        misses = sum(c.missed for c in group)
        out.append(
            f"  {attack:<24} {len(group):>4} {len(group) - misses:>4} {misses:>4} "
            f"{sum(c.mobs for c in group):>5} {sum(c.hit for c in group):>5}"
        )
    total_misses = sum(c.missed for c in casts)
    out.append(
        f"total: {len(casts)} casts, {len(casts) - total_misses} hit, "
        f"{total_misses} missed; {sum(c.mobs for c in casts)} mobs counted, "
        f"{sum(c.hit for c in casts)} with a damage number"
    )
    out.append("")
    out.append(f"partial reach: {len(partials)} events")
    for p in partials:
        shown = "; ".join(f"l{x1} t{y1} r{x2} b{y2}" for x1, y1, x2, y2 in p.offsets)
        out.append(f"  {p.t:9.2f}  {p.attack:<24} {len(p.offsets)} mobs: {shown}")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m toolkit.cast_outcomes", description=__doc__.split("\n")[0]
    )
    parser.add_argument(
        "session", type=Path, help="a Session directory or its telemetry.jsonl"
    )
    parser.add_argument(
        "--video", type=Path, help="the video, when not the one recorded"
    )
    parser.add_argument("--cast-time", type=float, default=CAST_TIME)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument("--scale", type=float, default=1.0)
    arguments = parser.parse_args(argv)
    try:
        session = load_session(telemetry_path(arguments.session))
        video = video_path(session, arguments.video)
        casts, partials = report(
            session,
            video,
            catalogue_templates(arguments.scale),
            cast_time=arguments.cast_time,
            tolerance=arguments.tolerance,
            scale=arguments.scale,
        )
    except (SessionError, ReportError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("\n".join(lines(casts, partials)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
