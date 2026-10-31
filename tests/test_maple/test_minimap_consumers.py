"""
The minimap's consumers on the new reader, fed synthetic frames: the map check,
the position attribute, and the state `ensure_minimap_displayed` waits for.
"""

import random
from collections.abc import Callable
from types import SimpleNamespace

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.screen import Frame
from game_data.sprites import Sprite
from maple.actions import menus
from maple.decision_makers.ensure_still_in_map import CheckStillInMap
from maple.decision_makers.mixins import MinimapAttributesMixin
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState
from tests.test_maple.test_screen_minimap import (
    CANVAS,
    MAP_ID,
    OTHER_CANVAS,
    draw_minimap,
    frame,
    occlude,
    reader,
    screen,
)


class _Data(SimpleNamespace):
    def update_attribute(self, name: str) -> None:
        pass


def _check(shown: Frame, map_id: int | None) -> CheckStillInMap:
    check = object.__new__(CheckStillInMap)
    check.data = _Data(  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
        ign="Tester",
        current_frame=shown,
        minimap_reader=reader(),
        current_minimap=SimpleNamespace(map_id=map_id),
    )
    return check


def _minimap(
    canvas: Sprite | None = None, user_at: tuple[int, int] | None = (30, 30)
) -> Frame:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=canvas, user_at=user_at)
    return frame(pixels)


# --- CheckStillInMap ----------------------------------------------------------


def test_with_a_map_id_the_check_passes_on_the_maps_own_minimap() -> None:
    assert _check(_minimap(CANVAS), MAP_ID)._perform_check()


def test_with_a_map_id_the_check_fails_on_another_maps_minimap() -> None:
    assert not _check(_minimap(OTHER_CANVAS), MAP_ID)._perform_check()


def test_without_a_map_id_the_check_only_asks_that_the_minimap_is_shown() -> None:
    assert _check(_minimap(OTHER_CANVAS), None)._perform_check()
    assert not _check(frame(screen()), None)._perform_check()


def test_a_covered_minimap_fails_the_check() -> None:
    pixels = screen()
    draw_minimap(pixels, 250, 20, canvas=CANVAS)
    occlude(pixels, 250, 20, 6, 72)

    assert not _check(frame(pixels), MAP_ID)._perform_check()
    assert not _check(frame(pixels), None)._perform_check()


# --- The position attribute ---------------------------------------------------


class _Positioned(MinimapAttributesMixin):
    def __init__(self, shown: Frame) -> None:
        self.data = _Data(minimap_reading=reader().read(shown))  # pyright: ignore[reportAttributeAccessIssue] - a stand-in


def test_every_minimap_consumer_declares_the_minimap_reader() -> None:
    assert MINIMAP in MinimapAttributesMixin.screen_readers
    assert MINIMAP in CheckStillInMap.screen_readers


def test_the_position_is_the_markers() -> None:
    assert _Positioned(_minimap(user_at=(12, 34)))._get_minimap_pos() == (12, 34)


@pytest.mark.parametrize(
    ("shown", "says"),
    [
        (frame(screen()), "minimap absent"),
        (_minimap(user_at=None), "marker isn't found"),
    ],
)
def test_no_position_raises_for_the_error_handler(shown: Frame, says: str) -> None:
    with pytest.raises(ValueError, match=says):
        _Positioned(shown)._get_minimap_pos()


# --- The state ensure_minimap_displayed waits for -----------------------------


@pytest.mark.parametrize(
    ("pixels", "state"),
    [
        (lambda: _minimap().pixels, MinimapState.EXPANDED),
        (screen, MinimapState.ABSENT),
        (lambda: np.zeros((300, 400, 3), np.uint8), None),
    ],
)
def test_the_minimap_state_is_read_off_a_fresh_capture(
    mocker: MockerFixture, pixels: Callable[[], np.ndarray], state: MinimapState | None
) -> None:
    grabbed = frame(pixels())
    source = mocker.Mock()
    source.grab.return_value = grabbed
    mocker.patch.object(menus, "frame_source", return_value=source)
    minimap: MinimapReader = reader()

    assert menus.minimap_state(minimap, 1) is state
    source.grab.assert_called_once_with(1)


# --- Keeping the cursor off the minimap ----------------------------------------


# A client area that starts 8 px right and 31 px down from the window's corner,
# as on a framed window, with the window itself somewhere else on the screen.
_WINDOW_RECT = (100, 50, 516, 389)
_CLIENT_ORIGIN = (108, 81)


def test_the_cursor_is_moved_off_the_minimap_where_it_is_on_screen(
    mocker: MockerFixture,
) -> None:
    """
    The box avoided and the point chosen are both in client pixels, and
    `controller.mouse_move` places a client point with `ClientToScreen`: so the
    cursor lands off the minimap on screen, whatever the window's border and
    title bar add. Were either in window pixels, some points would land on the
    minimap's bottom or right strip, which a few hundred draws hit.
    """
    from botting.controller import high_level
    from maple.decision_makers.mixins import _map_mixins

    mocker.patch.object(
        _map_mixins.win32gui, "GetClientRect", return_value=(0, 0, 400, 300)
    )
    mocker.patch.object(high_level.win32gui, "GetWindowRect", return_value=_WINDOW_RECT)
    mocker.patch.object(
        high_level.win32gui,
        "ClientToScreen",
        side_effect=lambda _, p: (p[0] + _CLIENT_ORIGIN[0], p[1] + _CLIENT_ORIGIN[1]),
    )
    reading = reader().read(_minimap())
    assert reading.value is not None
    bounds = reading.value.bounds
    sent: list[tuple[int, int]] = []
    mover = object.__new__(_Positioned)
    mover.data = _Data(  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
        handle=1, ign="Tester", current_entire_minimap_box=bounds
    )
    mover.send = lambda request: sent.append(request.args[1])  # pyright: ignore[reportAttributeAccessIssue]
    random.seed(311)

    for _ in range(300):
        mover._ensure_mouse_not_on_minimap("test")

    on_screen = [high_level.client_to_screen(1, point) for point in sent]
    ox, oy = _CLIENT_ORIGIN
    assert not [
        (x, y)
        for x, y in on_screen
        if bounds.left + ox <= x < bounds.right + ox
        and bounds.top + oy <= y < bounds.bottom + oy
    ]


def test_the_error_handler_moves_the_cursor_before_it_toggles_the_minimap(
    mocker: MockerFixture,
) -> None:
    from maple.decision_makers.mixins import _map_mixins

    order: list[str] = []
    mocker.patch.object(_map_mixins.time, "sleep")
    mocker.patch.object(
        _map_mixins,
        "ensure_minimap_displayed",
        side_effect=lambda *_: order.append("toggle"),
    )
    handler = _Positioned(_minimap(user_at=(12, 34)))
    handler.data.update_attributes = lambda *_: None  # pyright: ignore[reportAttributeAccessIssue]
    handler.data.handle = 1  # pyright: ignore[reportAttributeAccessIssue]
    handler.data.ign = "Tester"  # pyright: ignore[reportAttributeAccessIssue]
    handler.data.minimap_reader = reader()  # pyright: ignore[reportAttributeAccessIssue]
    handler.pipe = mocker.Mock()  # pyright: ignore[reportAttributeAccessIssue]
    handler._proxies = mocker.Mock()  # pyright: ignore[reportAttributeAccessIssue]
    mocker.patch.object(
        handler,
        "_ensure_mouse_not_on_minimap",
        side_effect=lambda _: order.append("mouse"),
    )

    handler._minimap_pos_error_handler()

    assert order == ["mouse", "toggle"]
