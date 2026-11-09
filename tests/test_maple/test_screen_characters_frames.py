"""
`NameTagFinder` on the real MSCW frame set: one finder reads every frame in
order, learning our tag where the minimap puts our character, as
`PositionFusion` will have it do. Where the tag is visible it finds our feet
within 2 virtual px of the labelled `feet`, never places ours on another
character, and lists the other characters in the crowded frames. Run with
`pytest -m frames`.

Where the minimap puts our character comes from the frame's labelled `minimap`
and `camera` readings, which the minimap reader's own frame tests hold it to.
"""

import math
from dataclasses import dataclass

import pytest

from botting.screen import Frame, Reading, Status
from game_data.catalogue import Catalogue
from game_data.catalogue.model import Minimap
from game_data.config import STORE
from maple.screen.minimap import virtual_feet
from maple.screen.position import CharacterSighting, NameTagFinder
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

PLAY_AREA = {
    (1920, 1080): (1366, 768),
    (1920, 1200): (1228, 768),
    (2560, 1440): (1366, 768),
}
"""The play area's size where the client upscales it, as `tests/frames/README.md`
measured it on these frames; smaller clients draw it 1:1. Only to turn the
labels' virtual px into client px."""

WITHIN = 2.0
"""Virtual px, on each axis (#391)."""

NOT_FOUND = {
    "f040_1366x768.png": "half under a window",
    "f048_800x600.png": "half under a window",
    "henesys_1920x1080_09.png": "its top behind grass drawn in front",
    "henesysL_1920x1080_02.png": "in a portal's glow, which lightens its box",
    "henesysmarket_1920x1080_052.png": "its end behind a leaf",
    "henesysmarket_1920x1080_068.png": "in a portal's glow, which lightens its box",
    "ellinia_1920x1080_032.png": "a rope across its first letters",
}
"""Frames whose labelled feet our learned tag isn't found at, and why: each was
looked at on a crop. The first three are in the README's lists too."""


@dataclass(frozen=True)
class Seen:
    entry: FrameEntry
    learned: bool
    reading: Reading[list[CharacterSighting]]


def scale_of(entry: FrameEntry) -> tuple[float, float]:
    """Client px per virtual px, on each axis."""
    width, height = entry.client_size
    view = PLAY_AREA.get(entry.client_size, entry.client_size)
    return width / view[0], height / view[1]


def to_virtual(entry: FrameEntry, feet: tuple[float, float]) -> tuple[float, float]:
    sx, sy = scale_of(entry)
    camera = entry.expect["camera"].value
    return camera["x"] + feet[0] / sx, camera["y"] + feet[1] / sy


def minimap_feet(
    entry: FrameEntry, minimaps: dict[int, Minimap]
) -> tuple[float, float] | None:
    """Where the minimap puts our feet on screen, client px: the middle of the
    canvas pixel its marker is read at; None where it isn't read."""
    camera, minimap = entry.expect.get("camera"), entry.expect.get("minimap")
    if camera is None or camera.status is not Status.READ:
        return None
    if minimap is None or minimap.status is not Status.READ:
        return None
    canvas = minimap.value.get("self_position")
    if canvas is None:
        return None
    transform = minimaps[entry.expect["map_id"].value]
    half = 2**transform.mag / 2
    x, y = virtual_feet((canvas[0], canvas[1]), transform)
    sx, sy = scale_of(entry)
    return (x + half - camera.value["x"]) * sx, (y + half - camera.value["y"]) * sy


@pytest.fixture(scope="module")
def seen(frames: FrameSet) -> list[Seen]:
    """Every frame read in order by one finder, which learns as it goes."""
    map_ids = {
        entry.expect["map_id"].value
        for entry in frames.entries
        if entry.expect["map_id"].status is Status.READ
    }
    with Catalogue.latest(STORE) as catalogue:
        maps = {i: catalogue.map(i).minimap for i in map_ids}
    minimaps = {i: m for i, m in maps.items() if m is not None}
    assert minimaps.keys() == maps.keys()
    finder = NameTagFinder()
    out: list[Seen] = []
    for entry in frames.entries:
        frame = Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)
        near = minimap_feet(entry, minimaps)
        if near is not None:
            finder.learn_own(frame, near)
        out.append(Seen(entry, finder.learned(entry.client_size), finder.find(frame)))
    return out


def own(reading: Reading[list[CharacterSighting]]) -> list[CharacterSighting]:
    assert reading.status is Status.READ
    assert reading.value is not None
    return [s for s in reading.value if s.own]


def feet_read(seen: list[Seen]) -> list[Seen]:
    return [s for s in seen if s.entry.expect["feet"].status is Status.READ]


def test_our_feet_are_found_within_2_px_where_our_tag_is_visible(
    seen: list[Seen],
) -> None:
    wrong: list[str] = []
    missed: list[str] = []
    found = 0
    for s in feet_read(seen):
        ours = own(s.reading)
        expected = s.entry.expect["feet"].value
        if len(ours) > 1:
            wrong.append(f"{s.entry.file}: {len(ours)} sightings marked ours")
        elif ours:
            x, y = to_virtual(s.entry, ours[0].feet)
            if abs(x - expected["x"]) > WITHIN or abs(y - expected["y"]) > WITHIN:
                wrong.append(f"{s.entry.file}: ({x:.1f}, {y:.1f}) for {expected}")
            found += 1
        elif s.learned and s.entry.file not in NOT_FOUND:
            missed.append(f"{s.entry.file}: {s.reading.detail}")
    assert not wrong, "\n".join(wrong)
    assert not missed, "\n".join(missed)
    not_learned = [s.entry.file for s in feet_read(seen) if not s.learned]
    # Our tag is learned on the set's third frame with a minimap reading.
    assert not_learned == ["f001_1366x768.png", "f003_1366x768.png"]
    # Every other frame with feet: ours found, or one of the known misses.
    assert found == len(feet_read(seen)) - len(not_learned) - len(NOT_FOUND)


def test_every_size_in_the_set_is_found_on(seen: list[Seen]) -> None:
    """2560x1440 too, where the minimap can't be read to learn from: what was
    learned at the nearest scale, resized, finds it there."""
    sizes = {s.entry.client_size for s in feet_read(seen) if own(s.reading)}
    assert sizes == {s.entry.client_size for s in feet_read(seen)}


def test_ours_is_never_placed_on_a_frame_whose_feet_cant_be_read(
    seen: list[Seen],
) -> None:
    placed = [
        s.entry.file
        for s in seen
        if s.entry.expect["feet"].status is Status.COVERED
        and s.reading.status is Status.READ
        and own(s.reading)
    ]
    assert placed == []


def test_other_characters_are_listed_in_the_crowd(seen: list[Seen]) -> None:
    crowd = [s for s in feet_read(seen) if s.entry.file.startswith("henesyscrowd_")]
    assert crowd
    for s in crowd:
        assert s.reading.value is not None
        ours = own(s.reading)
        others = [o for o in s.reading.value if not o.own]
        assert len(others) >= 5, s.entry.file
        if ours:
            # Another character's tag is never ours read twice.
            assert all(math.dist(o.feet, ours[0].feet) > 8 for o in others), (
                s.entry.file
            )
