"""
The minimap reader on synthetic frames: a plain background with a nine-piece
frame (with or without its banner) or the minimised title bar, drawn from
made-up sprites the client's sizes, markers, a map canvas (the bot's map's
unless a test says otherwise), and occluders painted over them. No client
pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from game_data.catalogue import Minimap
from game_data.sprites import Sprite
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.minimap import (
    DIFFERENT_SHARE,
    FEET_ROWS,
    FRAME_PARTS,
    MARKER_KINDS,
    MATCHED_SHARE,
    MIN_E,
    MIN_W,
    MINIMAP,
    NE,
    NW,
    SE,
    SW,
    USER,
    WITH_BANNER,
    WITHOUT_BANNER,
    FrameLook,
    MinimapReader,
    MinimapState,
    N,
    W,
    marker_path,
    minimap_canvas_path,
    virtual_feet,
)
from maple.screen.sprites import GAUGE_LABEL, Profile, ReaderSprites

RNG = np.random.default_rng(311)
MAP_ID = 100000000
OTHER_MAP_ID = 100000001


def sprite(path: str, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> Sprite:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, origin)


def marker(path: str, size: int = 12) -> Sprite:
    """A marker with its origin at its centre and a soft, partly transparent
    rim, like `Map/MapHelper.img/minimap/user` (12x12) and `another` (11x11)."""
    s = sprite(path, size, size, origin=(size // 2, size // 2))
    rim = [0, 1, size - 2, size - 1]
    s.rgba[rim, :, 3] = 0
    s.rgba[:, rim, 3] = 0
    return s


def look_sprites(look: FrameLook, band: int) -> dict[str, Sprite]:
    """One look's pieces at the client's sizes: the top band is as tall as
    `nw`, the border as wide. The edges `e` and `s` aren't read, so they get
    made-up paths."""
    return {
        look.nw: sprite(look.nw, 6, band),
        look.n: sprite(look.n, 1, band),
        look.ne: sprite(look.ne, 6, band),
        look.w: sprite(look.w, 6, 1),
        f"{look.nw}:e": sprite(f"{look.nw}:e", 6, 1),
        look.sw: sprite(look.sw, 6, 15),
        f"{look.nw}:s": sprite(f"{look.nw}:s", 1, 15),
        look.se: sprite(look.se, 6, 15),
    }


WITH_BANNER_BAND, WITHOUT_BANNER_BAND = 72, 29
SPRITES = {
    **look_sprites(WITH_BANNER, WITH_BANNER_BAND),
    **look_sprites(WITHOUT_BANNER, WITHOUT_BANNER_BAND),
    MIN_W: sprite(MIN_W, 8, 20),
    "min:c": sprite("min:c", 1, 20),
    MIN_E: sprite(MIN_E, 4, 20),
    USER: marker(USER),
    **{marker_path(kind): marker(marker_path(kind), 11) for kind in MARKER_KINDS},
    # Like the client's: 13x10, with its origin at (0, 0) rather than its centre.
    marker_path("npc"): sprite(marker_path("npc"), 13, 10),
    GAUGE_LABEL: sprite(GAUGE_LABEL, 20, 8),
}
CANVAS = sprite(minimap_canvas_path(MAP_ID), 120, 60)
CANVAS.rgba[::3, ::2, 3] = 0  # a minimap canvas is partly transparent
OTHER_CANVAS = sprite(minimap_canvas_path(OTHER_MAP_ID), 120, 60)

AREA_W, AREA_H = 120, 60
BACKGROUND = 40


def sprites() -> ReaderSprites:
    canvases = {**SPRITES, CANVAS.path: CANVAS, OTHER_CANVAS.path: OTHER_CANVAS}
    return ReaderSprites("build", canvases)


def reader(map_id: int | None = MAP_ID, read_markers: bool = True) -> MinimapReader:
    """A reader for the bot's map, `MAP_ID`, or for a map file without one."""
    s = sprites()
    return MinimapReader(s, FrameCheck(s), map_id=map_id, read_markers=read_markers)


def reader_with(canvas: Sprite) -> MinimapReader:
    """A reader whose map's canvas, `MAP_ID`'s, is `canvas`."""
    s = sprites()
    s.canvases[canvas.path] = canvas
    return MinimapReader(s, FrameCheck(s), map_id=MAP_ID, read_markers=True)


def paste(pixels: np.ndarray, s: Sprite, x: int, y: int) -> None:
    """Draw `s`'s opaque pixels with its top-left at `(x, y)`, clipped."""
    h, w = s.rgba.shape[:2]
    for dy in range(h):
        for dx in range(w):
            px, py = x + dx, y + dy
            inside = 0 <= px < pixels.shape[1] and 0 <= py < pixels.shape[0]
            if inside and s.rgba[dy, dx, 3] == 255:
                pixels[py, px] = s.rgba[dy, dx, 2::-1]


def screen(w: int = 400, h: int = 300) -> np.ndarray:
    pixels = np.full((h, w, 3), BACKGROUND, dtype=np.uint8)
    paste(pixels, SPRITES[GAUGE_LABEL], 10, h - 12)
    return pixels


def draw_minimap(
    pixels: np.ndarray,
    x: int,
    y: int,
    canvas: Sprite | None = CANVAS,
    user_at: tuple[int, int] | None = None,
    banner: bool = True,
    canvas_at: tuple[int, int] = (0, 0),
    markers: dict[str, list[tuple[int, int]]] | None = None,
) -> Box:
    """
    The frame with `nw` at `(x, y)` around an `AREA_W`x`AREA_H` map area,
    `canvas` in it with its top-left at `canvas_at` (clipped to the area, as the
    client scrolls it), `markers` by kind with their centre on each position,
    and the player marker's origin at `user_at`. Positions are pixels of the
    map area, which are the canvas's while `canvas_at` is `(0, 0)`. Returns the
    map area.
    """
    look = WITH_BANNER if banner else WITHOUT_BANNER
    band = WITH_BANNER_BAND if banner else WITHOUT_BANNER_BAND
    left, top = x + 6, y + band
    right, bottom = left + AREA_W, top + AREA_H
    paste(pixels, SPRITES[look.nw], x, y)
    for cx in range(left, right):
        paste(pixels, SPRITES[look.n], cx, y)
        paste(pixels, SPRITES[f"{look.nw}:s"], cx, bottom)
    paste(pixels, SPRITES[look.ne], right, y)
    for cy in range(top, bottom):
        paste(pixels, SPRITES[look.w], x, cy)
        paste(pixels, SPRITES[f"{look.nw}:e"], right, cy)
    paste(pixels, SPRITES[look.sw], x, bottom)
    paste(pixels, SPRITES[look.se], right, bottom)
    pixels[top:bottom, left:right] = 0
    if canvas is not None:
        paste(pixels[top:bottom, left:right], canvas, *canvas_at)
    for kind, positions in (markers or {}).items():
        drawn = SPRITES[marker_path(kind)]
        h, w = drawn.rgba.shape[:2]
        for mx, my in positions:
            paste(pixels, drawn, left + mx - w // 2, top + my - h // 2)
    if user_at is not None:
        ux, uy = user_at
        paste(pixels, SPRITES[USER], left + ux - 6, top + uy - 6)
    return Box(left=left, right=right, top=top, bottom=bottom)


def draw_minimised(pixels: np.ndarray, x: int, y: int, width: int = 150) -> Box:
    """The minimised title bar, `width` wide, with `w` at `(x, y)`. Returns its
    bounds."""
    paste(pixels, SPRITES[MIN_W], x, y)
    for cx in range(x + 8, x + width - 4):
        paste(pixels, SPRITES["min:c"], cx, y)
    paste(pixels, SPRITES[MIN_E], x + width - 4, y)
    return Box(left=x, right=x + width, top=y, bottom=y + 20)


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 7.0, True, ok, reason)


def occlude(pixels: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    pixels[y : y + h, x : x + w] = 200


# --- READ --------------------------------------------------------------------


def test_an_expanded_minimap_reads_its_area_bounds_and_position() -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20, user_at=(37, 41))

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.state is MinimapState.EXPANDED
    assert reading.value.map_area == area
    assert reading.value.map_area == Box(left=256, right=376, top=92, bottom=152)
    assert reading.value.bounds == Box(left=250, right=382, top=20, bottom=167)
    assert reading.value.self_position.value == (37, 41)
    assert reading.value.markers == {}
    assert reading.value.banner == Box(left=250, right=382, top=20, bottom=92)
    assert reading.frame_time == 7.0


def test_an_expanded_minimap_without_its_banner_reads_expanded() -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20, user_at=(37, 41), banner=False)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.state is MinimapState.EXPANDED
    assert reading.value.map_area == area
    assert area == Box(left=256, right=376, top=49, bottom=109)
    assert reading.value.bounds == Box(left=250, right=382, top=20, bottom=124)
    assert reading.value.self_position.value == (37, 41)
    assert reading.value.banner is None


def test_a_minimised_minimap_reads_its_title_bar_and_no_area() -> None:
    pixels = screen()
    bounds = draw_minimised(pixels, 30, 10)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.state is MinimapState.MINIMISED
    assert reading.value.bounds == bounds
    assert reading.value.map_area is None
    assert reading.value.self_position.status is Status.UNSURE
    assert reading.value.markers == {}
    assert reading.value.banner is None


def test_a_reader_not_asked_for_markers_reads_none() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=(60, 30), markers={"another": [(20, 15)]})

    reading = reader(read_markers=False).read(frame(pixels))

    assert reading.value is not None
    assert reading.value.markers is None
    assert reading.value.self_position.value == (60, 30)


def test_the_other_markers_are_read_by_kind() -> None:
    pixels = screen()
    draw_minimap(
        pixels,
        250,
        20,
        user_at=(60, 30),
        markers={"another": [(20, 15), (90, 40)], "npc": [(40, 50)]},
    )

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.markers == {
        "another": ((20, 15), (90, 40)),
        "npc": ((40, 50),),
    }
    assert reading.value.self_position.value == (60, 30)


# The marker's opaque core reaches 4 pixels left of and above its origin, and 3
# right of and below it; so these put it against each edge of the map area.
@pytest.mark.parametrize("at", [(4, 4), (AREA_W - 4, AREA_H - 4), (4, AREA_H - 4)])
def test_the_position_is_read_with_the_marker_against_the_areas_edges(
    at: tuple[int, int],
) -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=at)

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position.value == at


def test_a_minimap_without_the_players_marker_reads_its_position_covered() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.self_position.status is Status.COVERED
    assert reading.value.self_position.value is None


# --- The character's marker, partly hidden (#502) -----------------------------


def draw_user_clipped(pixels: np.ndarray, area: Box, at: tuple[int, int]) -> None:
    """The player's marker with its origin at `at` in the map area, clipped to
    it, as the client draws it: the frame around the area stays."""
    inside = pixels[area.top : area.bottom, area.left : area.right]
    paste(inside, SPRITES[USER], at[0] - 6, at[1] - 6)


def draw_marker(pixels: np.ndarray, area: Box, kind: str, at: tuple[int, int]) -> None:
    """A `kind` marker with its centre at `at` in the map area, clipped to it."""
    drawn = SPRITES[marker_path(kind)]
    h, w = drawn.rgba.shape[:2]
    inside = pixels[area.top : area.bottom, area.left : area.right]
    paste(inside, drawn, at[0] - w // 2, at[1] - h // 2)


# The marker's 8x8 opaque core spans 4 pixels left of and above its origin to 3
# right of and below it; each of these leaves 2 or 3 of its 8 columns or rows
# outside the map area.
@pytest.mark.parametrize(
    ("edge", "at"),
    [
        ("left", (1, 30)),
        ("right", (AREA_W - 2, 30)),
        ("top", (60, 1)),
        ("bottom", (60, AREA_H - 2)),
    ],
)
def test_a_marker_clipped_by_the_areas_edge_is_placed_by_its_origin(
    edge: str, at: tuple[int, int]
) -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_user_clipped(pixels, area, at)

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    position = reading.value.self_position
    assert position.status is Status.READ, f"{edge}: {position}"
    assert position.value == at
    assert "drawn" in position.detail


def test_a_marker_touching_a_portal_is_read_whole() -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_marker(pixels, area, "portal", (40, 30))
    draw_user_clipped(pixels, area, (32, 30))

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position == Reading.read((32, 30), 7.0)
    assert reading.value.markers == {"portal": ((40, 30),)}


def test_a_marker_partly_under_a_portal_is_placed() -> None:
    """The portal, drawn over it, hides 3 of its 8 columns on 7 of its rows."""
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_user_clipped(pixels, area, (30, 30))
    draw_marker(pixels, area, "portal", (34, 30))

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    position = reading.value.self_position
    assert position.status is Status.READ
    assert position.value == (30, 30)
    assert position.detail == "the character's marker 67% drawn"


def test_a_marker_clipped_at_the_edge_next_to_a_portal_is_placed() -> None:
    """As on the first live run (#502): at the map's left end, cut by the
    edge, with a portal one marker to its right."""
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_marker(pixels, area, "portal", (8, 40))
    draw_user_clipped(pixels, area, (2, 40))

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position.value == (2, 40)


def test_a_marker_mostly_hidden_reads_covered() -> None:
    """Less than `MARKER_DRAWN_SHARE` drawn: 6 of its 8 columns under a window."""
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_user_clipped(pixels, area, (30, 30))
    occlude(pixels, area.left + 26, area.top + 20, 6, 20)

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position.status is Status.COVERED
    assert "isn't found" in reading.value.self_position.detail


def test_a_portal_alone_is_not_taken_for_the_marker() -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20)
    draw_marker(pixels, area, "portal", (2, 40))
    draw_marker(pixels, area, "another", (60, 30))

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position.status is Status.COVERED


# --- Positions are pixels on the map's canvas ---------------------------------


def test_without_a_map_id_no_position_is_read() -> None:
    """The canvas can't be located without the map's canvas, so neither the
    position nor the markers are guessed from the map area."""
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=(37, 41), markers={"another": [(20, 15)]})

    reading = reader(map_id=None).read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.state is MinimapState.EXPANDED
    assert reading.value.self_position.status is Status.UNSURE
    assert reading.value.self_position.value is None
    assert "map_id" in reading.value.self_position.detail
    assert reading.value.markers == {}


def test_positions_are_on_the_canvas_as_it_scrolls() -> None:
    """A canvas taller than the map area scrolls with the character: the same
    place on the map area is a different place on the canvas."""
    tall = sprite(minimap_canvas_path(MAP_ID), 80, 150)
    tall.rgba[::3, ::2, 3] = 0
    minimap = reader_with(tall)
    readings = []
    for scroll in (-37, -80, -37):
        pixels = screen()
        draw_minimap(
            pixels,
            250,
            20,
            canvas=tall,
            canvas_at=(20, scroll),
            user_at=(40, 30),
            markers={"another": [(60, 20)]},
        )
        reading = minimap.read(frame(pixels))
        assert reading.value is not None
        readings.append(reading.value)

    assert [view.self_position.value for view in readings] == [
        (20, 67),
        (20, 110),
        (20, 67),
    ]
    assert readings[0].markers == {"another": ((40, 57),)}


def test_another_maps_canvas_reads_the_position_unsure() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=OTHER_CANVAS, user_at=(37, 41))

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position.status is Status.UNSURE
    assert "not found" in reading.value.self_position.detail


# --- ABSENT, COVERED, UNSURE --------------------------------------------------


def test_no_minimap_reads_absent_with_no_value() -> None:
    reading = reader().read(frame(screen()))

    assert reading.status is Status.ABSENT
    assert reading.value is None


@pytest.mark.parametrize(
    ("covered", "box"),
    [
        (NW, (250, 20, 6, 72)),
        (NE, (376, 20, 6, 72)),
        (SW, (250, 152, 6, 15)),
        (SE, (376, 152, 6, 15)),
        (W, (250, 92, 6, 1)),
    ],
)
def test_a_covered_frame_piece_reads_covered_naming_it(
    covered: str, box: tuple[int, int, int, int]
) -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=(30, 30))
    occlude(pixels, *box)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert covered in reading.detail


def test_a_minimised_minimap_whose_right_end_is_covered_reads_covered() -> None:
    pixels = screen()
    bounds = draw_minimised(pixels, 30, 10)
    occlude(pixels, bounds.right - 4, bounds.top, 4, 20)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.COVERED
    assert MIN_E in reading.detail


def test_an_unusable_frame_reads_unsure() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=(30, 30))

    reading = reader().read(frame(pixels, ok=False, reason="window moved"))

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert "window moved" in reading.detail


def test_a_frame_without_the_status_bar_at_1_1_reads_unsure() -> None:
    pixels = np.full((300, 400, 3), BACKGROUND, dtype=np.uint8)
    draw_minimap(pixels, 250, 20, user_at=(30, 30))

    reading = reader().read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


# --- Remembering where it was -------------------------------------------------


def test_the_minimap_is_searched_for_once_while_it_stays_put() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=(30, 30))
    minimap = reader()

    for _ in range(3):
        assert minimap.read(frame(pixels)).status is Status.READ

    assert minimap.searches == 1


@pytest.mark.parametrize("look", ["without banner", "minimised"])
def test_the_look_found_last_is_tried_first(look: str) -> None:
    pixels = screen()
    if look == "minimised":
        draw_minimised(pixels, 30, 10)
    else:
        draw_minimap(pixels, 250, 20, banner=False)
    minimap = reader()
    minimap.read(frame(pixels))
    searched = minimap.searches

    for _ in range(3):
        assert minimap.read(frame(pixels)).status is Status.READ

    assert minimap.searches == searched


def test_a_new_client_size_searches_again_and_finds_it_moved() -> None:
    minimap = reader()
    small = screen(400, 300)
    draw_minimap(small, 250, 20, user_at=(30, 30))
    large = screen(640, 480)
    area = draw_minimap(large, 500, 10, user_at=(31, 32))

    assert minimap.read(frame(small)).status is Status.READ
    reading = minimap.read(frame(large))

    assert minimap.searches == 2
    assert reading.value is not None
    assert reading.value.map_area == area
    assert reading.value.self_position.value == (31, 32)


# --- The expected map ---------------------------------------------------------


def test_the_maps_own_canvas_reads_as_the_expected_map() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=CANVAS, user_at=(60, 30))

    reading = reader().is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.READ
    assert reading.value is True


def test_another_maps_canvas_reads_as_not_the_expected_map() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=OTHER_CANVAS, user_at=(60, 30))

    reading = reader().is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.READ
    assert reading.value is False


# The client draws a canvas narrower than the map area centred, and scrolls one
# taller than it with the character (frame set v2).
@pytest.mark.parametrize(
    ("size", "at"),
    [
        ((80, 150), (20, 0)),
        ((80, 150), (20, AREA_H - 150)),
        ((80, 150), (20, -37)),
        ((AREA_W, 150), (0, -50)),
        ((AREA_W + 30, 150), (-12, -50)),
    ],
)
def test_a_canvas_drawn_as_a_window_reads_as_the_expected_map(
    size: tuple[int, int], at: tuple[int, int]
) -> None:
    tall = sprite(minimap_canvas_path(MAP_ID), *size)
    tall.rgba[::3, ::2, 3] = 0
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=tall, canvas_at=at, user_at=(60, 30))

    reading = reader_with(tall).is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.READ
    assert reading.value is True


def test_a_canvas_larger_than_the_area_reads_as_another_map_over_another() -> None:
    big = sprite(minimap_canvas_path(MAP_ID), AREA_W + 20, AREA_H + 40)
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=OTHER_CANVAS)

    reading = reader_with(big).is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.READ
    assert reading.value is False


def test_a_partly_overdrawn_canvas_is_unsure() -> None:
    pixels = screen()
    area = draw_minimap(pixels, 250, 20, canvas=CANVAS)
    # Overdraw a share of the canvas between the two thresholds.
    share = (MATCHED_SHARE + DIFFERENT_SHARE) / 2
    occlude(pixels, area.left, area.top, int(AREA_W * (1 - share)), AREA_H)

    reading = reader().is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.UNSURE
    assert reading.value is None


def test_the_expected_map_check_is_unsure_on_a_minimised_minimap() -> None:
    pixels = screen()
    draw_minimised(pixels, 30, 10)

    reading = reader().is_expected_map(frame(pixels), MAP_ID)

    assert reading.status is Status.UNSURE
    assert "minimised" in reading.detail


def test_the_expected_map_check_reports_a_missing_minimap_as_its_status() -> None:
    reading = reader().is_expected_map(frame(screen()), MAP_ID)

    assert reading.status is Status.ABSENT
    assert reading.value is None


# --- The declaration ----------------------------------------------------------


def test_a_maps_canvas_path_follows_the_clients_folders() -> None:
    assert minimap_canvas_path(100000000) == "Map/Map/Map1/100000000.img/miniMap/canvas"
    assert minimap_canvas_path(1000) == "Map/Map/Map0/000001000.img/miniMap/canvas"


def test_the_declaration_names_the_maps_canvas_only_when_the_map_id_is_known() -> None:
    without = MINIMAP.canvas_paths(Profile(job="Cleric"))
    with_id = MINIMAP.canvas_paths(Profile(job="Cleric", map_id=MAP_ID))

    markers = {marker_path(kind) for kind in MARKER_KINDS}
    assert set(without) == {*FRAME_PARTS, USER, *markers}
    assert {NW, N, NE, W, SW, SE, MIN_W, MIN_E} <= set(FRAME_PARTS)
    assert set(with_id) == {*without, minimap_canvas_path(MAP_ID)}


# --- From canvas pixels to virtual coordinates --------------------------------


def _transform(center_x: int, center_y: int, mag: int) -> Minimap:
    return Minimap(center_x=center_x, center_y=center_y, mag=mag, width=0, height=0)


def test_a_canvas_pixel_converts_to_the_feet_six_rows_below_it() -> None:
    transform = _transform(center_x=1_000, center_y=2_000, mag=4)

    assert FEET_ROWS == 6
    assert virtual_feet((10, 20), transform) == (10 * 16 - 1_000, 26 * 16 - 2_000)


def test_the_conversion_scales_by_two_to_the_maps_mag() -> None:
    transform = _transform(center_x=300, center_y=-40, mag=3)

    assert virtual_feet((10, 20), transform) == (10 * 8 - 300, 26 * 8 + 40)
    assert virtual_feet((0, 0), _transform(0, 0, mag=5)) == (0, 6 * 32)


@pytest.mark.parametrize("mag", [3, 4, 5])
@pytest.mark.parametrize("feet", [(0, 0), (-713, 219), (1_234, -88), (15, 31)])
def test_the_feet_lie_in_the_canvas_pixel_the_marker_implies(
    feet: tuple[int, int], mag: int
) -> None:
    # Where the marker is drawn for these feet, as frame set v2 shows it.
    transform = _transform(center_x=845, center_y=1_310, mag=mag)
    scale = 2**mag
    marker = (
        (feet[0] + transform.center_x) // scale,
        (feet[1] + transform.center_y) // scale - FEET_ROWS,
    )

    x, y = virtual_feet(marker, transform)

    assert 0 <= feet[0] - x < scale
    assert 0 <= feet[1] - y < scale
