"""
Map identification on synthetic frames: the minimap and title of
`test_screen_minimap` and `test_screen_minimap_title`, over a few made-up maps
whose canvases are made-up sprites. No client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.locator import FrameCheck
from maple.screen.map_identification import MapCanvas, MapCanvases, MapIdentifier
from maple.screen.minimap import MinimapReader, minimap_canvas_path
from maple.screen.minimap_title import MinimapTitleReader
from tests.test_maple.test_screen_minimap import (
    CANVAS,
    OTHER_CANVAS,
    draw_minimap,
    draw_minimised,
    frame,
    occlude,
    screen,
)
from tests.test_maple.test_screen_minimap_title import (
    FRAME_AT,
    TITLE,
    draw_title,
    title_sprites,
)

HERE, ELSEWHERE, TWIN, ALIKE = 101, 102, 103, 104
THIRD = Sprite(
    minimap_canvas_path(105),
    np.random.default_rng(387).integers(0, 256, (60, 120, 4), dtype=np.uint8),
    (0, 0),
)
THIRD.rgba[:, :, 3] = 255


def canvas(map_id: int, like: Sprite) -> Sprite:
    """`like`'s pixels, under `map_id`'s canvas path."""
    return Sprite(minimap_canvas_path(map_id), like.rgba, like.origin)


def maps(*entries: tuple[int, str, Sprite]) -> MapCanvases:
    return MapCanvases(MapCanvas.of(i, t, canvas(i, c)) for i, t, c in entries)


DEFAULT = maps(
    (HERE, TITLE, CANVAS),
    (ELSEWHERE, "Cc: Ab", OTHER_CANVAS),
)


def identifier(canvases: MapCanvases = DEFAULT) -> MapIdentifier:
    s = title_sprites()
    minimap = MinimapReader(s, FrameCheck(s))
    title = MinimapTitleReader(s, minimap, canvases.titles)
    return MapIdentifier(minimap, title, canvases)


def shown(
    drawn: Sprite | None = CANVAS, banner: bool = True, title: bool = True
) -> Frame:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT, canvas=drawn, banner=banner)
    if banner and title:
        draw_title(pixels)
    return frame(pixels)


def test_the_title_picks_the_map_and_its_canvas_confirms_it() -> None:
    reading = identifier().identify(shown())

    assert reading.status is Status.READ
    assert reading.value == HERE


def test_a_title_whose_canvas_isnt_drawn_is_unsure() -> None:
    """The title says one map, the minimap shows another: they disagree."""
    reading = identifier().identify(shown(OTHER_CANVAS))

    assert reading.status is Status.UNSURE
    assert "no map called that" in reading.detail


def test_of_maps_sharing_a_title_the_one_whose_canvas_is_drawn_is_read() -> None:
    canvases = maps((HERE, TITLE, CANVAS), (TWIN, TITLE, OTHER_CANVAS))

    assert identifier(canvases).identify(shown(OTHER_CANVAS)).value == TWIN
    assert identifier(canvases).identify(shown(CANVAS)).value == HERE


def test_maps_sharing_their_title_and_canvas_are_unsure() -> None:
    canvases = maps((HERE, TITLE, CANVAS), (ALIKE, TITLE, CANVAS))

    reading = identifier(canvases).identify(shown())

    assert reading.status is Status.UNSURE
    assert str(HERE) in reading.detail
    assert str(ALIKE) in reading.detail


def test_without_the_banner_a_canvas_only_one_map_has_decides() -> None:
    canvases = maps(
        (HERE, TITLE, CANVAS), (ELSEWHERE, "Cc: Ab", OTHER_CANVAS), (105, "x", THIRD)
    )

    reading = identifier(canvases).identify(shown(OTHER_CANVAS, banner=False))

    assert reading.status is Status.READ
    assert reading.value == ELSEWHERE


def test_without_a_readable_title_the_canvas_alone_decides_too() -> None:
    """The banner is shown, but its title isn't drawn in known glyphs."""
    reading = identifier().identify(shown(CANVAS, title=False))

    assert reading.value == HERE


def test_without_the_banner_a_canvas_several_maps_share_is_unsure() -> None:
    canvases = maps((HERE, TITLE, CANVAS), (ALIKE, "Cc: Ab", CANVAS))

    reading = identifier(canvases).identify(shown(CANVAS, banner=False))

    assert reading.status is Status.UNSURE
    assert "share" in reading.detail


def test_without_the_banner_no_canvas_drawn_is_unsure() -> None:
    reading = identifier().identify(shown(THIRD, banner=False))

    assert reading.status is Status.UNSURE
    assert "no map's minimap is drawn" in reading.detail


def test_a_minimised_minimap_is_unsure() -> None:
    pixels = screen()
    draw_minimised(pixels, *FRAME_AT)

    reading = identifier().identify(frame(pixels))

    assert reading.status is Status.UNSURE
    assert "minimised" in reading.detail


@pytest.mark.parametrize("status", [Status.ABSENT, Status.COVERED])
def test_a_minimap_not_read_is_its_own_status(status: Status) -> None:
    pixels = screen()
    if status is Status.COVERED:
        draw_minimap(pixels, *FRAME_AT)
        occlude(pixels, FRAME_AT[0] + 110, FRAME_AT[1], 40, 30)

    assert identifier().identify(frame(pixels)).status is status


def test_maps_sharing_a_canvas_are_known_by_its_pixels() -> None:
    canvases = maps((HERE, TITLE, CANVAS), (ALIKE, "Cc: Ab", CANVAS), (105, "x", THIRD))

    assert set(canvases.sharing(HERE)) == {HERE, ALIKE}
    assert canvases.sharing(105) == (105,)
    assert canvases.titles == {TITLE, "Cc: Ab", "x"}
    assert [m.map_id for m in canvases.titled(TITLE)] == [HERE]
