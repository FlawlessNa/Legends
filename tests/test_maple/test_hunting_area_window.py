"""
`maple.launchers.hunting_area_window`: the window's logic with no window opened,
on the Fixture map of `test_hunting_area`, given a minimap transform whose canvas
pixel is 16 virtual px.
"""

from dataclasses import replace
from pathlib import Path

import pytest

from botting.utilities import Box
from maple.launchers.hunting_area_window import (
    ENTER,
    ESC,
    HuntingAreaPicker,
    LiveReading,
    _lines,
    enlargement,
    placed_beside,
    suggested_rectangle,
)
from maple.model.world import HuntingArea, MinimapTransform, WorldMap
from maple.model.world.hunting_area import load_area, save_area, saved_areas
from tests.test_maple.test_hunting_area import fixture_map

CANVAS = (220, 125)
"""A canvas the size of the Fixture map: 3500 by 2000 virtual px, 16 to a px."""

FACTOR = 16
"""One window px is one virtual px."""


def world() -> WorldMap:
    """The Fixture map with the minimap transform `centre` (500, 1500), `mag` 4."""
    return replace(fixture_map(), minimap=MinimapTransform((500, 1500), 4))


def picker(tmp_path: Path) -> HuntingAreaPicker:
    return HuntingAreaPicker(world(), CANVAS, tmp_path, FACTOR)


def window_of(virtual: tuple[int, int]) -> tuple[int, int]:
    """The window px of a virtual point: `v + centre`, as `FACTOR` is 16."""
    return virtual[0] + 500, virtual[1] + 1500


def draw(window: HuntingAreaPicker, a: tuple[int, int], b: tuple[int, int]) -> None:
    window.drag(window_of(a), window_of(b))


def type_name(window: HuntingAreaPicker, name: str) -> None:
    window.press(ord("s"))
    for letter in name:
        window.press(ord(letter))


def save_many(tmp_path: Path, names: list[str]) -> None:
    for name in names:
        save_area(world(), HuntingArea(0, -100, 400, 50, name), tmp_path)


# --- the suggested rectangle ---------------------------------------------------


def test_the_suggestion_is_500_each_side_250_above_and_100_below_the_feet() -> None:
    assert suggested_rectangle((1000.0, 0.0), world()) == HuntingArea(
        500, -250, 1500, 100
    )


def test_the_suggestion_is_clipped_to_the_maps_bounds() -> None:
    found = suggested_rectangle((-400.0, 450.0), world())

    assert found == HuntingArea(-500, 200, 100, 500)


def test_no_position_suggests_nothing(tmp_path: Path) -> None:
    window = picker(tmp_path)

    window.update(LiveReading())

    assert suggested_rectangle(None, world()) is None
    assert window.rectangle is None


def test_the_first_position_read_suggests_a_rectangle_that_then_stays(
    tmp_path: Path,
) -> None:
    window = picker(tmp_path)

    window.update(LiveReading(character=(1000.0, 0.0)))
    window.update(LiveReading(character=(2000.0, 0.0)))

    assert window.rectangle == HuntingArea(500, -250, 1500, 100)


# --- drawing -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((0, 0), (1000, 100)),
        ((1000, 100), (0, 0)),
        ((0, 100), (1000, 0)),
        ((1000, 0), (0, 100)),
    ],
)
def test_a_drag_is_the_rectangle_between_its_ends_from_any_corner(
    tmp_path: Path, start: tuple[int, int], end: tuple[int, int]
) -> None:
    window = picker(tmp_path)

    draw(window, start, end)

    assert window.rectangle == HuntingArea(0, 0, 1000, 100)
    assert window.rectangle is not None
    assert isinstance(window.rectangle.left, int)


def test_a_drag_that_did_not_move_draws_nothing(tmp_path: Path) -> None:
    window = picker(tmp_path)

    window.drag((10, 10), (10, 10))

    assert window.rectangle is None


def test_a_drag_replaces_the_suggestion(tmp_path: Path) -> None:
    window = picker(tmp_path)
    window.update(LiveReading(character=(1000.0, 0.0)))

    draw(window, (0, -100), (400, 50))

    assert window.rectangle == HuntingArea(0, -100, 400, 50)


# --- saved areas ---------------------------------------------------------------


def test_digits_take_the_saved_areas_in_name_order(tmp_path: Path) -> None:
    save_many(tmp_path, ["zeta", "alpha", "mid"])
    window = picker(tmp_path)

    window.press(ord("1"))
    assert window.rectangle is not None
    assert window.rectangle.name == "alpha"
    window.press(ord("3"))
    assert window.rectangle.name == "zeta"
    assert window.names == ("alpha", "mid", "zeta")


def test_a_tenth_saved_area_is_listed_without_a_number(tmp_path: Path) -> None:
    save_many(tmp_path, [f"a{n}" for n in range(10)])
    window = picker(tmp_path)

    listed = _lines(window)[1:]

    assert len(listed) == 10
    assert listed[8].split() == ["9", "a8"]
    assert listed[9].split() == ["-", "a9"]
    window.press(ord("9"))
    assert window.rectangle is not None
    assert window.rectangle.name == "a8"


def test_a_digit_with_no_saved_area_says_so(tmp_path: Path) -> None:
    window = picker(tmp_path)

    window.press(ord("2"))

    assert window.rectangle is None
    assert "no saved area 2" in window.message


# --- naming --------------------------------------------------------------------


def test_s_a_name_and_enter_save_the_rectangle(tmp_path: Path) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))

    type_name(window, "corner_2")
    window.press(ENTER)

    assert load_area(world().id, "corner_2", tmp_path) == HuntingArea(
        0, -100, 400, 50, "corner_2"
    )
    assert window.typing is None
    assert not window.finished
    assert window.names == ("corner_2",)


def test_while_a_name_is_typed_digits_go_to_the_name(tmp_path: Path) -> None:
    save_many(tmp_path, ["alpha"])
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))

    type_name(window, "a1")

    assert window.typing == "a1"
    assert window.rectangle is not None
    assert window.rectangle.name is None


def test_escape_while_a_name_is_typed_drops_the_name_and_keeps_the_window(
    tmp_path: Path,
) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))
    type_name(window, "abc")

    window.press(ESC)

    assert window.typing is None
    assert not window.finished
    assert saved_areas(world().id, tmp_path) == {}


@pytest.mark.parametrize("name", ["", "has space", "x" * 25, "dash-ed"])
def test_a_name_outside_the_rule_is_refused_with_a_message(
    tmp_path: Path, name: str
) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))
    type_name(window, name)

    window.press(ENTER)

    assert "1 to 24 characters" in window.message
    assert window.typing == name
    assert saved_areas(world().id, tmp_path) == {}


def test_s_with_no_rectangle_starts_no_name(tmp_path: Path) -> None:
    window = picker(tmp_path)

    window.press(ord("s"))

    assert window.typing is None
    assert window.message


# --- Enter and Esc -------------------------------------------------------------


def test_enter_on_a_rectangle_that_holds_a_stretch_returns_it(tmp_path: Path) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))

    window.press(ENTER)

    assert window.finished
    assert window.result == HuntingArea(0, -100, 400, 50)


def test_enter_on_a_rectangle_with_no_stretch_does_nothing_and_says_why(
    tmp_path: Path,
) -> None:
    window = picker(tmp_path)
    draw(window, (0, 200), (400, 400))

    window.press(ENTER)

    assert not window.finished
    assert window.result is None
    assert "no Platform" in window.message


def test_enter_with_no_rectangle_does_nothing(tmp_path: Path) -> None:
    window = picker(tmp_path)

    window.press(ENTER)

    assert not window.finished
    assert window.message


def test_escape_outside_a_name_gives_up(tmp_path: Path) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))

    window.press(ESC)

    assert window.finished
    assert window.result is None


# --- what the minimap shows ----------------------------------------------------

SHOWN = Box(left=0, top=-500, right=600, bottom=300)


def test_a_rectangle_larger_than_what_the_minimap_shows_says_so(
    tmp_path: Path,
) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (1000, 50))

    window.update(LiveReading(shown=SHOWN))

    assert "larger than what the minimap shows" in window.message


def test_a_rectangle_inside_what_the_minimap_shows_says_nothing(
    tmp_path: Path,
) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (400, 50))

    window.update(LiveReading(shown=SHOWN))

    assert window.message == ""


def test_with_no_part_shown_it_says_nothing(tmp_path: Path) -> None:
    window = picker(tmp_path)
    draw(window, (0, -100), (3000, 50))

    window.update(LiveReading(shown=None))

    assert window.message == ""


# --- size and place ------------------------------------------------------------


@pytest.mark.parametrize(
    ("canvas", "factor"),
    [((220, 125), 5), ((92, 158), 5), ((400, 100), 3), ((2000, 900), 1)],
)
def test_the_canvas_is_enlarged_by_the_largest_whole_factor_within_1200_by_800(
    canvas: tuple[int, int], factor: int
) -> None:
    assert enlargement(canvas) == factor


def test_the_window_goes_right_of_the_client_then_left_then_the_corner() -> None:
    work = Box(left=0, top=0, right=1920, bottom=1040)
    screen = (1920, 1080)
    size = (600, 400)

    right_of = placed_beside(
        Box(left=0, top=100, right=800, bottom=700), size, screen, work
    )
    left_of = placed_beside(
        Box(left=1000, top=100, right=1900, bottom=700), size, screen, work
    )
    neither = placed_beside(
        Box(left=100, top=100, right=1900, bottom=700), size, screen, work
    )
    no_client = placed_beside(None, size, screen, work)

    assert right_of == (808, 100)
    assert left_of == (392, 100)
    assert neither == (0, 0)
    assert no_client == (0, 0)
