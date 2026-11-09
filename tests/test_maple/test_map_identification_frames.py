"""
Map identification on the real MSCW frame set: the banner's title read with
the harvested glyphs on every frame that shows it, and the map identified
against every map's canvas in the store on every expanded frame, `UNSURE` on
minimised ones. Run with `pytest -m "frames and client_files"`, after
`python -m toolkit.harvest_glyphs`.
"""

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.map_identification import MapCanvases, MapIdentifier
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState
from maple.screen.minimap_title import MINIMAP_TITLE_READER, MinimapTitleReader
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]


@pytest.fixture(scope="module")
def canvases() -> MapCanvases:
    return MapCanvases.load(STORE)


def _readers(canvases: MapCanvases) -> tuple[MinimapReader, MinimapTitleReader]:
    profile = Profile(job="Swordsman", game_map="x")
    sprites = load_reader_sprites(
        [FRAME_CHECK, MINIMAP, MINIMAP_TITLE_READER], profile, STORE, config=CONFIG
    )
    minimap = MinimapReader(sprites, FrameCheck(sprites))
    return minimap, MinimapTitleReader(sprites, minimap, canvases.titles)


def _frame(frames: FrameSet, entry: FrameEntry) -> Frame:
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def _expected(entry: FrameEntry) -> tuple[str, str] | None:
    """The minimap's expected state and map, when it is read."""
    expected = entry.expect.get("minimap")
    if expected is None or not expected.value:
        return None
    return expected.value["state"], expected.value.get("map")


def test_the_title_is_read_on_every_frame_that_shows_the_banner(
    frames: FrameSet, canvases: MapCanvases
) -> None:
    minimap, title = _readers(canvases)
    wrong: list[str] = []
    read = 0
    for entry in frames.entries:
        frame = _frame(frames, entry)
        view = minimap.read(frame).value
        if view is None or view.banner is None:
            continue
        read += 1
        expected = _expected(entry)
        reading = title.read_view(frame, view)
        if expected is None or reading.value != expected[1]:
            wrong.append(f"{entry.file}: {reading}, expected {expected}")
    assert read
    assert not wrong, "\n".join(wrong)


def test_every_expanded_frame_is_identified_and_minimised_ones_are_unsure(
    frames: FrameSet, canvases: MapCanvases
) -> None:
    """With and without the banner: frame set v2's maps each have a canvas of
    their own, so the canvas alone decides where no title is read."""
    minimap, title = _readers(canvases)
    identifier = MapIdentifier(minimap, title, canvases)
    by_title = {m.title: m.map_id for m in canvases}
    wrong: list[str] = []
    states: set[str] = set()
    for entry in frames.entries:
        expected = _expected(entry)
        reading = identifier.identify(_frame(frames, entry))
        if expected is None:
            if reading.status is Status.READ:
                wrong.append(f"{entry.file}: {reading} where no minimap is read")
            continue
        state, shown = expected
        states.add(state)
        if state == MinimapState.EXPANDED.value:
            if reading.value != by_title[shown]:
                wrong.append(f"{entry.file} shows {shown}: {reading}")
        elif reading.status is not Status.UNSURE:
            wrong.append(f"{entry.file} is {state}: {reading}")
    assert states == {"expanded", "minimised"}
    assert not wrong, "\n".join(wrong)


def test_the_set_has_a_frame_without_the_banner(
    frames: FrameSet, canvases: MapCanvases
) -> None:
    """So the canvas-only path is exercised on a real frame."""
    minimap, _ = _readers(canvases)
    without = [
        entry.file
        for entry in frames.entries
        if (view := minimap.read(_frame(frames, entry)).value) is not None
        and view.state is MinimapState.EXPANDED
        and view.banner is None
    ]
    assert without
