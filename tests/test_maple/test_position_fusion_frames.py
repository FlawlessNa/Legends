"""
`PositionFusion` on the real MSCW frame set, as the bot builds it
(`PositionFusion.for_map`, with the bot's `FrameCheck`), against the labelled
`feet` (`tests/frames/README.md`). Frame set v3 repeats v2's frames, so this
reads both. Run with `pytest -m frames`; it needs the game data store.

One `NameTagFinder` reads every frame, map by map in the set's order within
each map, learning our tag where the minimap puts our character, as the bot
would. Each map has its own fusion, so its camera is seeded only by its own
frames. Nothing here is a label: the minimap is read by `MinimapReader`, the
camera by `CameraReader`, the characters by the finder.
"""

import math
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.model.world import WorldMap
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MINIMAP, MinimapReader
from maple.screen.position import (
    WINDOW,
    CameraReader,
    Fusion,
    NameTagFinder,
    PositionFusion,
    PositionSource,
)
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

WITHIN = 2.0
"""Virtual px, on each axis (#392)."""

TAG_HIDDEN = {
    "f040_1366x768.png": "half under a window",
    "f048_800x600.png": "half under a window",
    "henesys_1920x1080_09.png": "its top behind grass drawn in front",
    "henesysL_1920x1080_02.png": "in a portal's glow, which lightens its box",
    "henesysmarket_1920x1080_052.png": "its end behind a leaf",
    "henesysmarket_1920x1080_068.png": "in a portal's glow, which lightens its box",
    "ellinia_1920x1080_032.png": "a rope across its first letters",
}
"""Frames whose feet are labelled but where our tag isn't found: the name tag
finder's own list (`test_screen_characters_frames.NOT_FOUND`). The position
is the minimap's, `coarse`."""

DISAGREE = {
    "henesyscrowd_1920x1080_010.png": (
        "our tag's feet are on the labelled feet, standing on the ground, and "
        "the marker is read 2 canvas rows above the row they put it in"
    ),
}
"""Frames where the reads disagree by more than one canvas pixel, so the
position is `UNSURE` though our character is visible: looked at on a crop."""


@dataclass(frozen=True)
class Fused:
    entry: FrameEntry
    fusion: Fusion


def _by_map(frames: FrameSet) -> dict[int, list[FrameEntry]]:
    """The frames whose map is labelled, by map, in the set's order."""
    out: dict[int, list[FrameEntry]] = {}
    for entry in frames.entries:
        map_id = entry.expect["map_id"]
        if map_id.status is Status.READ:
            out.setdefault(map_id.value, []).append(entry)
    return out


def _read_map(
    frames: FrameSet, map_id: int, entries: list[FrameEntry], finder: NameTagFinder
) -> Iterator[Fused]:
    profile = Profile(job="Swordsman", map_id=map_id)
    sprites = load_reader_sprites([FRAME_CHECK, MINIMAP], profile, STORE, config=CONFIG)
    frame_check = FrameCheck(sprites)
    minimap = MinimapReader(sprites, frame_check, map_id=map_id)
    world_map = WorldMap.load(map_id, root=STORE)
    assert world_map.minimap is not None
    fusion = PositionFusion(
        world_map.minimap,
        lambda: CameraReader(world_map, frame_check=frame_check),
        finder,
    )
    for entry in entries:
        frame = Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)
        yield Fused(entry, fusion.read(frame, minimap.read(frame)))


@pytest.fixture(scope="module")
def fused(frames: FrameSet) -> list[Fused]:
    finder = NameTagFinder()
    out: list[Fused] = []
    for map_id, entries in _by_map(frames).items():
        out.extend(_read_map(frames, map_id, entries, finder))
    return out


def _labelled(f: Fused) -> tuple[int, int] | None:
    feet = f.entry.expect["feet"]
    return (feet.value["x"], feet.value["y"]) if feet.status is Status.READ else None


def _minimap_places(entry: FrameEntry) -> bool:
    """Whether the frame's `minimap` label reads a position: not where it is
    minimised, covered, the marker clipped at the canvas's edge, or at
    2560x1440, where the UI is upscaled."""
    minimap = entry.expect.get("minimap")
    if minimap is None or minimap.status is not Status.READ:
        return False
    return minimap.value.get("self_position") is not None


def _source(f: Fused) -> PositionSource | None:
    value = f.fusion.position.value
    return None if value is None else value.source


def test_our_feet_are_fused_within_2_px_wherever_they_can_be(
    fused: list[Fused],
) -> None:
    """Every frame whose feet are labelled is fused to them, or is a frame the
    minimap gives no position on (`UNSURE`), one of `TAG_HIDDEN` (`coarse`)
    or one of `DISAGREE` (`UNSURE`)."""
    wrong: list[str] = []
    fused_count = 0
    for f in fused:
        feet = _labelled(f)
        if feet is None:
            continue
        name, position = f.entry.file, f.fusion.position
        if not _minimap_places(f.entry) or name in DISAGREE:
            expected: PositionSource | None = None
        elif name in TAG_HIDDEN:
            expected = PositionSource.COARSE
        else:
            expected = PositionSource.FUSED
        if _source(f) is not expected:
            wrong.append(f"{name}: {position.status.name} {position.detail}")
            continue
        if expected is PositionSource.FUSED:
            fused_count += 1
            assert position.value is not None
            off = (position.value.x - feet[0], position.value.y - feet[1])
            if max(abs(off[0]), abs(off[1])) > WITHIN:
                wrong.append(f"{name}: off by ({off[0]:.1f}, {off[1]:.1f})")
    assert not wrong, "\n".join(wrong)
    assert fused_count >= 230


def test_nothing_is_fused_where_our_tag_cant_be_read(fused: list[Fused]) -> None:
    """Our tag under a window, a chat balloon or an object: on frame set v3
    the name tag finder reads a sword, a pet's tag and a balloon there, inside
    the window, and none of them is taken for ours."""
    placed = [
        f"{f.entry.file}: {f.fusion.position.detail}"
        for f in fused
        if _labelled(f) is None and _source(f) is PositionSource.FUSED
    ]
    assert placed == []


def test_in_the_crowd_our_tag_chooses_among_several_by_the_minimaps(
    fused: list[Fused],
) -> None:
    """Never another player's character: every crowded frame fused is on our
    feet (above), and on several of them more than one character stood
    within the window."""
    crowd = [f for f in fused if f.entry.file.startswith("henesyscrowd_")]
    assert crowd
    several = [f for f in crowd if f.fusion.near >= 2]
    assert len(several) >= 5
    for f in several:
        assert f.fusion.by_tag, f.entry.file
        assert _source(f) is PositionSource.FUSED, f.entry.file


def test_the_minimaps_position_is_within_32_px_of_the_labelled_feet(
    fused: list[Fused],
) -> None:
    far: list[str] = []
    checked = 0
    for f in fused:
        feet, minimap = _labelled(f), f.fusion.minimap
        if feet is None or minimap is None:
            continue
        checked += 1
        off = (minimap[0] - feet[0], minimap[1] - feet[1])
        if max(abs(off[0]), abs(off[1])) > WINDOW:
            far.append(f"{f.entry.file}: {off}")
    assert not far, "\n".join(far)
    assert checked >= 240


def test_a_fused_position_agrees_with_the_minimap_within_one_canvas_pixel(
    fused: list[Fused],
) -> None:
    """The minimap's position is the middle of a 16 px canvas pixel."""
    for f in fused:
        value, minimap = f.fusion.position.value, f.fusion.minimap
        if value is None or value.source is not PositionSource.FUSED:
            continue
        assert minimap is not None
        cells = (
            math.floor((value.x - minimap[0] + 8) / 16),
            math.floor((value.y - minimap[1] + 8) / 16),
        )
        assert max(abs(cells[0]), abs(cells[1])) <= 1, f.entry.file


def test_a_frame_the_minimap_gives_no_position_on_is_unsure(
    fused: list[Fused],
) -> None:
    for f in fused:
        if not _minimap_places(f.entry):
            assert f.fusion.position.status is Status.UNSURE, f.entry.file
