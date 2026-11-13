"""
The minimap reader on the real MSCW frame set: every expected `minimap`
reading, at every client size in the set; the position, in pixels on the map's
canvas, within 1 pixel for a reader given the map's `map_id` and `UNSURE` for
one without; and the expected-map check against every map the set shows. Run
with `pytest -m frames`.
"""

import cv2
import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.catalogue import Catalogue
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState
from maple.screen.sprites import (
    FRAME_CHECK,
    GAUGE_LABEL,
    Profile,
    ReaderSprites,
    load_reader_sprites,
)
from tests import frame_set
from tests.frame_set import FRAMES_ROOT, FrameEntry, FrameSet, load_expected

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

MAPS = (
    "Dungeon: Damp Forest",
    "Victoria Road: Ellinia",
    "Victoria Road: Henesys",
    "Victoria Road: Henesys Market",
)
"""The maps the set shows, as their `map` is written in it."""


@pytest.fixture(scope="module")
def map_ids() -> dict[str, int]:
    with Catalogue.latest(STORE) as catalogue:
        return {name: catalogue.map(name).id for name in MAPS}


def reader_sprites(map_id: int | None = None) -> ReaderSprites:
    profile = Profile(job="Swordsman", map_id=map_id)
    return load_reader_sprites([FRAME_CHECK, MINIMAP], profile, STORE, config=CONFIG)


def reader_for(map_id: int | None = None) -> MinimapReader:
    sprites = reader_sprites(map_id)
    return MinimapReader(sprites, FrameCheck(sprites), map_id=map_id, read_markers=True)


def frame_of(frames: FrameSet, entry: FrameEntry) -> Frame:
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def expanded(frames: FrameSet, shown: str | None = None) -> list[FrameEntry]:
    """The frames whose minimap is expanded, showing `shown` if given."""
    return [
        entry
        for entry in frames.entries
        if (expected := entry.expect.get("minimap"))
        and expected.value
        and expected.value["state"] == MinimapState.EXPANDED.value
        and shown in (None, expected.value["map"])
    ]


def test_every_expected_minimap_reading(frames: FrameSet) -> None:
    """One reader without a map_id reads the whole set in order, across every
    client resize and between the minimap's looks; it reads no position."""
    reader = reader_for()
    wrong: list[str] = []
    checked = 0
    for entry in frames.entries:
        expected = entry.expect.get("minimap")
        if expected is None:
            continue
        checked += 1
        reading = reader.read(frame_of(frames, entry))
        got = reading.value
        problem = ""
        if reading.status is not expected.status:
            problem = f"status {reading.status.name}"
        elif expected.value is not None and got is not None:
            if got.state.value != expected.value["state"]:
                problem = f"state {got.state.value}"
            elif got.self_position.status is not Status.UNSURE:
                problem = f"position {got.self_position} without a map_id"
        if problem:
            wrong.append(f"{entry.file}: {problem} {reading.detail}")
    assert checked
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("shown", MAPS)
def test_the_position_is_read_on_the_maps_canvas(
    frames: FrameSet, map_ids: dict[str, int], shown: str
) -> None:
    """With the map's map_id, every expanded frame of it reads the character's
    position within 1 pixel of where the oracle puts it on the canvas, and
    none where the oracle has none. A marker clipped at the canvas's edge is
    placed (#502): Henesys's right end."""
    reader = reader_for(map_ids[shown])
    wrong: list[str] = []
    for entry in expanded(frames, shown):
        want = entry.expect["minimap"].value["self_position"]
        view = reader.read(frame_of(frames, entry)).value
        at = view.self_position.value if view is not None else None
        if want is None:
            if at is not None:
                wrong.append(
                    f"{entry.file}: {view and view.self_position}, expected none"
                )
        elif at is None or max(abs(at[0] - want[0]), abs(at[1] - want[1])) > 1:
            detail = view.self_position if view is not None else "no view"
            wrong.append(f"{entry.file}: {detail}, expected {want}")
    assert expanded(frames, shown)
    assert not wrong, "\n".join(wrong)


def test_every_state_size_and_map_is_in_the_set(frames: FrameSet) -> None:
    read = [
        entry
        for entry in frames.entries
        if (expected := entry.expect.get("minimap")) and expected.value
    ]
    sizes = {entry.client_size for entry in expanded(frames)}
    states = {entry.expect["minimap"].value["state"] for entry in read}
    maps = {entry.expect["minimap"].value["map"] for entry in expanded(frames)}
    assert {(800, 600), (1024, 768), (1280, 720), (1366, 768), (1920, 1080)} <= sizes
    assert {"expanded", "minimised"} <= states
    assert maps == set(MAPS)


@pytest.mark.parametrize("expected_map", MAPS)
def test_the_expected_map_is_told_from_the_other(
    frames: FrameSet, map_ids: dict[str, int], expected_map: str
) -> None:
    """On every expanded frame, the bot's map reads `True` where the minimap
    shows it and `False` where it shows another map."""
    reader = reader_for(map_ids[expected_map])
    wrong: list[str] = []
    for entry in expanded(frames):
        shown = entry.expect["minimap"].value["map"]
        reading = reader.is_expected_map(frame_of(frames, entry), map_ids[expected_map])
        if reading.status is not Status.READ or reading.value != (
            shown == expected_map
        ):
            wrong.append(f"{entry.file} shows {shown}: {reading}")
    assert not wrong, "\n".join(wrong)


def test_the_npcs_seen_in_ellinia_are_read_as_npc_markers(
    frames: FrameSet, map_ids: dict[str, int]
) -> None:
    """With the view scrolled to the same place, Ellinia's frames show the same
    four NPC markers wholly inside the map area, and the storage keeper's.
    Those are frame set `v2`'s Ellinia frames, all at one spot; `v3`'s climb
    scrolls the view, so they show other markers."""
    ellinia = "Victoria Road: Ellinia"
    reader = reader_for(map_ids[ellinia])
    at_one_spot = {
        entry.file for entry in load_expected(frame_set.TESTS_FRAMES / "v2.json")
    }
    found: set[tuple[tuple[str, int], ...]] = set()
    for entry in expanded(frames, ellinia):
        if entry.file not in at_one_spot:
            continue
        view = reader.read(frame_of(frames, entry)).value
        assert view is not None
        assert view.markers is not None
        markers = view.markers
        found.add(
            tuple((kind, len(markers.get(kind, ()))) for kind in ("npc", "trunk"))
        )
    assert found == {(("npc", 4), ("trunk", 1))}


LEFT_EDGE = FRAMES_ROOT.parent / "live_run1" / "minimap_marker_at_left_edge.png"
"""The minimap, cropped from the first live run's frame (#502): our character at
Ellinia's left end, its marker cut by the canvas's edge and touching a portal.
A client pixel, so never committed: the maintainer keeps it in
`.scratch/live_run1/`, and this test reads it from `data/live_run1/`."""


def test_the_marker_clipped_at_ellinias_left_end_is_placed(
    map_ids: dict[str, int],
) -> None:
    """Read live as `COVERED`, which stopped the bot. The crop is pasted into a
    blank client with the status bar's anchor, which the frame check asks for."""
    if not LEFT_EDGE.is_file():
        pytest.skip(f"copy minimap_marker_at_left_edge.png to {LEFT_EDGE}")
    ellinia = map_ids["Victoria Road: Ellinia"]
    sprites = reader_sprites(ellinia)
    reader = MinimapReader(sprites, FrameCheck(sprites), map_id=ellinia)
    crop = cv2.imread(str(LEFT_EDGE), cv2.IMREAD_COLOR)
    assert crop is not None, f"{LEFT_EDGE} isn't an image"
    pixels = np.zeros((600, 800, 3), np.uint8)
    pixels[: crop.shape[0], : crop.shape[1]] = crop
    label = sprites.canvas(GAUGE_LABEL).rgba
    opaque = label[:, :, 3] == 255
    h, w = opaque.shape
    pixels[560 : 560 + h, 10 : 10 + w][opaque] = label[:, :, 2::-1][opaque]

    reading = reader.read(Frame(pixels, (800, 600), 0.0, True, True))

    assert reading.value is not None
    position = reading.value.self_position
    assert position.status is Status.READ, position
    # Where the whole marker's origin is: 1 of its 8 columns is cut off.
    assert position.value == (3, 297)
    assert position.detail == "the character's marker 92% drawn"
