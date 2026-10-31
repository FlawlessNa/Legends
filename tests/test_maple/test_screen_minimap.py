"""
The minimap reader on synthetic frames: a plain background with a nine-piece
frame the test draws from made-up sprites the client's sizes, a marker, a map
canvas, and occluders painted over them. No client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from botting.utilities import Box
from game_data.sprites import Sprite
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.minimap import (
    DIFFERENT_SHARE,
    MATCHED_SHARE,
    MINIMAP,
    NE,
    NW,
    SE,
    SW,
    USER,
    MinimapReader,
    MinimapState,
    N,
    W,
    minimap_canvas_path,
)
from maple.screen.sprites import GAUGE_LABEL, Profile, ReaderSprites

RNG = np.random.default_rng(311)
MAP_ID = 100000000
OTHER_MAP_ID = 100000001


def sprite(path: str, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> Sprite:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, origin)


def marker(path: str) -> Sprite:
    """A 12x12 marker with its origin at its centre and a soft, partly
    transparent rim, like `Map/MapHelper.img/minimap/user`."""
    s = sprite(path, 12, 12, origin=(6, 6))
    s.rgba[[0, 1, 10, 11], :, 3] = 0
    s.rgba[:, [0, 1, 10, 11], 3] = 0
    return s


# The client's sizes: the top band is as tall as `nw`, the border as wide.
SPRITES = {
    NW: sprite(NW, 6, 72),
    N: sprite(N, 1, 72),
    NE: sprite(NE, 6, 72),
    W: sprite(W, 6, 1),
    "e": sprite("e", 6, 1),
    SW: sprite(SW, 6, 15),
    "s": sprite("s", 1, 15),
    SE: sprite(SE, 6, 15),
    USER: marker(USER),
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


def reader() -> MinimapReader:
    s = sprites()
    return MinimapReader(s, FrameCheck(s))


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
    canvas: Sprite | None = None,
    user_at: tuple[int, int] | None = None,
) -> Box:
    """The frame with `nw` at `(x, y)` around an `AREA_W`x`AREA_H` map area,
    `canvas` in it, and the player marker's origin at `user_at` (minimap pixels).
    Returns the map area."""
    left, top = x + 6, y + 72
    right, bottom = left + AREA_W, top + AREA_H
    paste(pixels, SPRITES[NW], x, y)
    for cx in range(left, right):
        paste(pixels, SPRITES[N], cx, y)
        paste(pixels, SPRITES["s"], cx, bottom)
    paste(pixels, SPRITES[NE], right, y)
    for cy in range(top, bottom):
        paste(pixels, SPRITES[W], x, cy)
        paste(pixels, SPRITES["e"], right, cy)
    paste(pixels, SPRITES[SW], x, bottom)
    paste(pixels, SPRITES[SE], right, bottom)
    pixels[top:bottom, left:right] = 0
    if canvas is not None:
        paste(pixels, canvas, left, top)
    if user_at is not None:
        ux, uy = user_at
        paste(pixels, SPRITES[USER], left + ux - 6, top + uy - 6)
    return Box(left=left, right=right, top=top, bottom=bottom)


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
    assert reading.value.self_position == (37, 41)
    assert reading.value.markers is None
    assert reading.frame_time == 7.0


# The marker's opaque core reaches 4 pixels left of and above its origin, and 3
# right of and below it; so these put it against each edge of the map area.
# Whether the client draws it over the frame when the character is closer still
# needs frames to tell.
@pytest.mark.parametrize("at", [(4, 4), (AREA_W - 4, AREA_H - 4), (4, AREA_H - 4)])
def test_the_position_is_read_with_the_marker_against_the_areas_edges(
    at: tuple[int, int],
) -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, user_at=at)

    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert reading.value.self_position == at


def test_a_minimap_without_the_players_marker_reads_with_no_position() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.self_position is None


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

    assert minimap.locator.searches == 1


def test_a_new_client_size_searches_again_and_finds_it_moved() -> None:
    minimap = reader()
    small = screen(400, 300)
    draw_minimap(small, 250, 20, user_at=(30, 30))
    large = screen(640, 480)
    area = draw_minimap(large, 500, 10, user_at=(31, 32))

    assert minimap.read(frame(small)).status is Status.READ
    reading = minimap.read(frame(large))

    assert minimap.locator.searches == 2
    assert reading.value is not None
    assert reading.value.map_area == area
    assert reading.value.self_position == (31, 32)


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


def test_a_canvas_larger_than_the_map_area_is_not_the_expected_map() -> None:
    big = sprite(minimap_canvas_path(MAP_ID), AREA_W + 1, AREA_H)
    s = sprites()
    s.canvases[big.path] = big
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=CANVAS)

    reading = MinimapReader(s, FrameCheck(s)).is_expected_map(frame(pixels), MAP_ID)

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


def test_the_expected_map_check_reports_a_missing_minimap_as_its_status() -> None:
    reading = reader().is_expected_map(frame(screen()), MAP_ID)

    assert reading.status is Status.ABSENT
    assert reading.value is None


# --- The declaration ----------------------------------------------------------


def test_a_maps_canvas_path_follows_the_clients_folders() -> None:
    assert minimap_canvas_path(100000000) == "Map/Map/Map1/100000000.img/miniMap/canvas"
    assert minimap_canvas_path(1000) == "Map/Map/Map0/000001000.img/miniMap/canvas"


def test_the_declaration_names_the_maps_canvas_only_when_the_map_id_is_known() -> None:
    without = MINIMAP.canvas_paths(Profile(job="Cleric", game_map="Somewhere"))
    with_id = MINIMAP.canvas_paths(
        Profile(job="Cleric", game_map="Somewhere", map_id=MAP_ID)
    )

    assert set(without) == {NW, N, NE, W, SW, SE, USER}
    assert set(with_id) == {*without, minimap_canvas_path(MAP_ID)}
