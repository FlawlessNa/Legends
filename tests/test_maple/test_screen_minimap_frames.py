"""
The minimap reader on the real MSCW frame set: every expected `minimap`
reading, at every client size in the set, with the position within 1 pixel,
and the expected-map check against both maps the set shows. Run with
`pytest -m frames`.
"""

import pytest

from botting.screen import Frame, Status
from game_data.catalogue import Catalogue
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState
from maple.screen.sprites import (
    FRAME_CHECK,
    Profile,
    ReaderSprites,
    load_reader_sprites,
)
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]

MAPS = ("Dungeon: Damp Forest", "Victoria Road: Ellinia")
"""The maps the set shows, as their `map` is written in it."""


@pytest.fixture(scope="module")
def map_ids() -> dict[str, int]:
    with Catalogue.latest(STORE) as catalogue:
        return {name: catalogue.map(name).id for name in MAPS}


def sprites_for(map_id: int | None = None) -> ReaderSprites:
    profile = Profile(job="Swordsman", game_map="x", map_id=map_id)
    return load_reader_sprites([FRAME_CHECK, MINIMAP], profile, STORE, config=CONFIG)


def frame_of(frames: FrameSet, entry: FrameEntry) -> Frame:
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def expanded(frames: FrameSet) -> list[FrameEntry]:
    return [
        entry
        for entry in frames.entries
        if (expected := entry.expect.get("minimap"))
        and expected.value
        and expected.value["state"] == MinimapState.EXPANDED.value
    ]


def test_every_expected_minimap_reading(frames: FrameSet) -> None:
    """One reader reads the whole set in order, across every client resize and
    between the minimap's looks."""
    sprites = sprites_for()
    reader = MinimapReader(sprites, FrameCheck(sprites))
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
            elif "self_position" in expected.value:
                want = expected.value["self_position"]
                at = got.self_position
                if at is None or max(abs(at[0] - want[0]), abs(at[1] - want[1])) > 1:
                    problem = f"position {at}, expected {want}"
        if problem:
            wrong.append(f"{entry.file}: {problem} {reading.detail}")
    assert checked
    assert not wrong, "\n".join(wrong)


def test_every_state_and_size_is_in_the_set(frames: FrameSet) -> None:
    read = [
        entry
        for entry in frames.entries
        if (expected := entry.expect.get("minimap")) and expected.value
    ]
    sizes = {entry.client_size for entry in expanded(frames)}
    states = {entry.expect["minimap"].value["state"] for entry in read}
    assert {(800, 600), (1024, 768), (1280, 720), (1366, 768), (1920, 1080)} <= sizes
    assert {"expanded", "minimised"} <= states
    assert {entry.expect["minimap"].value["map"] for entry in expanded(frames)} == set(
        MAPS
    )


@pytest.mark.parametrize("expected_map", MAPS)
def test_the_expected_map_is_told_from_the_other(
    frames: FrameSet, map_ids: dict[str, int], expected_map: str
) -> None:
    """On every expanded frame, the bot's map reads `True` where the minimap
    shows it and `False` where it shows the other map."""
    sprites = sprites_for(map_ids[expected_map])
    reader = MinimapReader(sprites, FrameCheck(sprites))
    wrong: list[str] = []
    for entry in expanded(frames):
        shown = entry.expect["minimap"].value["map"]
        reading = reader.is_expected_map(frame_of(frames, entry), map_ids[expected_map])
        if reading.status is not Status.READ or reading.value != (
            shown == expected_map
        ):
            wrong.append(f"{entry.file} shows {shown}: {reading}")
    assert not wrong, "\n".join(wrong)


def test_the_npcs_seen_in_ellinia_are_read_as_npc_markers(frames: FrameSet) -> None:
    """With the view scrolled to the same place, Ellinia's frames show the same
    four NPC markers wholly inside the map area, and the storage keeper's."""
    sprites = sprites_for()
    reader = MinimapReader(sprites, FrameCheck(sprites))
    found: set[tuple[tuple[str, int], ...]] = set()
    for entry in expanded(frames):
        if entry.expect["minimap"].value["map"] != "Victoria Road: Ellinia":
            continue
        view = reader.read(frame_of(frames, entry)).value
        assert view is not None
        found.add(
            tuple((kind, len(view.markers.get(kind, ()))) for kind in ("npc", "trunk"))
        )
    assert found == {(("npc", 4), ("trunk", 1))}
