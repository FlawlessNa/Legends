"""
The minimap's consumers on the new reader, fed synthetic frames: the map check,
the position attribute, and the state `ensure_minimap_displayed` waits for.
"""

import random
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core import BotData
from botting.screen import Frame, Reading, Status
from game_data.sprites import Sprite
from maple.actions import menus
from maple.decision_makers.ensure_still_in_map import CheckStillInMap
from maple.decision_makers.mixins import MinimapAttributesMixin
from maple.screen.minimap import MINIMAP, MinimapReader, MinimapState, MinimapView
from maple.screen.position import Fusion, PositionSource, VirtualPosition
from maple.telemetry_events import POSITION_READ
from tests.test_maple.test_screen_minimap import (
    CANVAS,
    MAP_ID,
    OTHER_CANVAS,
    draw_minimap,
    draw_minimised,
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
    canvas: Sprite | None = CANVAS, user_at: tuple[int, int] | None = (30, 30)
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


def _minimised() -> Frame:
    pixels = screen()
    draw_minimised(pixels, 30, 10)
    return frame(pixels)


@pytest.mark.parametrize("map_id", [MAP_ID, None])
def test_a_minimised_minimap_fails_the_check(map_id: int | None) -> None:
    assert not _check(_minimised(), map_id)._perform_check()


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


def test_without_a_map_id_the_position_raises_for_the_error_handler() -> None:
    positioned = object.__new__(_Positioned)
    positioned.data = _Data(minimap_reading=reader(map_id=None).read(_minimap()))  # pyright: ignore[reportAttributeAccessIssue] - a stand-in

    with pytest.raises(ValueError, match="position unsure: no map_id"):
        positioned._get_minimap_pos()


@pytest.mark.parametrize(
    ("shown", "displayed"),
    [
        (_minimap(), True),
        (_minimised(), False),
        (frame(screen()), False),
    ],
)
def test_the_minimap_counts_as_displayed_only_when_expanded(
    shown: Frame, displayed: bool
) -> None:
    """The Stuck detector's guard (`_on_expected_minimap`) reads this: a
    minimised minimap shows no map."""
    assert _Positioned(shown)._minimap_displayed() is displayed


def test_a_covered_minimap_keeps_the_last_answers_and_absent_says_not_shown() -> None:
    """No policy for a covered minimap yet: whether it is shown, and where,
    keep their last values (`HeldReading`). Not on screen is an answer."""
    shown = _minimap()
    covered = _minimap()
    occlude(covered.pixels, 250, 20, 6, 72)
    positioned = _Positioned(shown)
    bounds = positioned._entire_minimap_box()
    assert positioned._minimap_displayed() is True
    assert bounds is not None

    positioned.data.minimap_reading = reader().read(covered)  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    assert positioned.data.minimap_reading.status is Status.COVERED
    assert positioned._minimap_displayed() is True
    assert positioned._entire_minimap_box() == bounds

    positioned.data.minimap_reading = reader().read(frame(screen()))  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    assert positioned.data.minimap_reading.status is Status.ABSENT
    assert positioned._minimap_displayed() is False
    assert positioned._entire_minimap_box() == bounds


def test_the_position_is_the_markers() -> None:
    assert _Positioned(_minimap(user_at=(12, 34)))._get_minimap_pos() == (12, 34)


@pytest.mark.parametrize(
    ("shown", "says"),
    [
        (frame(screen()), "minimap absent"),
        (_minimap(user_at=None), "marker isn't found"),
        (_minimised(), "minimised"),
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
        (lambda: _minimised().pixels, MinimapState.MINIMISED),
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


def _without_banner() -> Frame:
    pixels = screen()
    draw_minimap(pixels, 250, 20, banner=False)
    return frame(pixels)


@pytest.mark.parametrize(
    ("shown", "banner"),
    [
        (_minimap, True),
        (_without_banner, False),
        (_minimised, False),
        (lambda: frame(screen()), False),
    ],
)
def test_the_banner_is_asked_of_a_fresh_capture(
    mocker: MockerFixture, shown: Callable[[], Frame], banner: bool
) -> None:
    source = mocker.Mock()
    source.grab.return_value = shown()
    mocker.patch.object(menus, "frame_source", return_value=source)

    assert menus.minimap_banner_shown(reader(), 1) is banner


@pytest.mark.parametrize("banner", [True, False])
def test_ensure_minimap_displayed_waits_for_the_banner_only_when_asked(
    mocker: MockerFixture, banner: bool
) -> None:
    """On the look without the banner, the toggle is pressed again only when
    the banner is asked for."""
    source = mocker.Mock()
    source.grab.return_value = _without_banner()
    mocker.patch.object(menus, "frame_source", return_value=source)
    action = mocker.patch.object(menus, "ActionWithValidation")

    menus.ensure_minimap_displayed(
        "test", 1, "Tester", mocker.Mock(), reader(), mocker.Mock(), 1.0, banner=banner
    )

    validator = action.call_args.args[1]
    assert validator() is not banner


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


# --- The virtual position attribute (#392) -------------------------------------


class _Fusion:
    """Answers `position`, and counts its reads."""

    def __init__(self, position: Reading[VirtualPosition]) -> None:
        self.position = position
        self.reads = 0

    def read(self, frame: Frame, minimap: Reading[MinimapView]) -> Fusion:
        self.reads += 1
        return Fusion(self.position, (600, 336), near=1)


def _located(fusion: _Fusion | None) -> tuple[_Positioned, list[tuple[str, Any]]]:
    shown = _minimap()
    located = _Positioned(shown)
    located.data.current_frame = shown  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    located.data.position_fusion = fusion  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    emitted: list[tuple[str, Any]] = []
    located.emit = lambda event, payload: emitted.append((event, payload))  # pyright: ignore[reportAttributeAccessIssue]
    return located, emitted


def test_the_position_is_fusions_and_each_read_is_recorded() -> None:
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    located, emitted = _located(_Fusion(fused))

    assert located._get_position() == fused
    assert emitted == [
        (
            POSITION_READ,
            {
                "status": "read",
                "source": "fused",
                "x": 605.5,
                "y": 340.0,
                "minimap_x": 600,
                "minimap_y": 336,
                "camera_x": None,
                "camera_y": None,
                "found": 0,
                "near": 1,
                "by_tag": False,
                "own_elsewhere": False,
                "detail": "",
            },
        )
    ]


def test_an_unsure_position_is_recorded_then_raises_for_the_error_handler() -> None:
    located, emitted = _located(_Fusion(Reading.unsure(3.0, "the reads disagree")))

    with pytest.raises(ValueError, match="position unsure: the reads disagree"):
        located._get_position()
    assert [(e, p["status"], p["source"]) for e, p in emitted] == [
        (POSITION_READ, "unsure", None)
    ]


def test_without_a_fusion_the_position_raises_for_the_error_handler() -> None:
    located, emitted = _located(None)

    with pytest.raises(ValueError, match="no position fusion"):
        located._get_position()
    assert emitted == []


def test_the_position_attribute_has_the_minimaps_error_handler_and_waits_to_be_read(
    mocker: MockerFixture,
) -> None:
    """Creating it reads nothing, so it sends nothing: the first consumer to
    ask reads it, and an unsure read goes to the handler
    `current_minimap_position` has."""
    from maple.decision_makers.mixins import _map_mixins

    mocker.patch.object(_map_mixins, "ensure_minimap_displayed")
    fused = Reading.read(VirtualPosition(605.5, 340.0, PositionSource.FUSED), 3.0)
    fusion = _Fusion(fused)
    data = BotData("Tester")
    shown = _minimap()
    data.set_static("handle", 1)
    data.set_static("current_frame", shown)
    data.set_static("minimap_reader", reader())
    data.set_static("position_fusion", fusion)
    located = object.__new__(_Positioned)
    located.data = data
    located.pipe = mocker.Mock()  # pyright: ignore[reportAttributeAccessIssue]
    located._proxies = mocker.Mock()  # pyright: ignore[reportAttributeAccessIssue]
    located.emit = mocker.Mock()  # pyright: ignore[reportAttributeAccessIssue]

    located._create_minimap_attributes()

    managed = data._managed  # pyright: ignore[reportPrivateUsage] - the attribute's configuration
    assert fusion.reads == 0
    assert (
        managed["current_position"].error_handler
        == managed["current_minimap_position"].error_handler
        == located._minimap_pos_error_handler
    )
    assert data.current_position == fused
    assert fusion.reads == 1
