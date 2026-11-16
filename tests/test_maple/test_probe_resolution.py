"""
The probe's `resolution` command: its refusals send nothing, its result is
checked on a fresh frame, and its inputs go through the guarded gestures. The
menu steps themselves are `test_menus.py`'s.
"""

import json
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, call

import numpy as np
import pytest

from botting.controller.inputs import HeldKeysLedger
from botting.screen import Frame
from botting.utilities import Box
from maple import menus, probe

HANDLE = 4242


@pytest.fixture(autouse=True)
def _empty_ledger() -> Iterator[None]:
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


def _rect(left: int, top: int, right: int, bottom: int) -> Box:
    return Box(left=left, top=top, right=right, bottom=bottom)


def _frame(size: tuple[int, int]) -> Frame:
    return Frame(np.zeros((size[1], size[0], 3), np.uint8), size, 1.0, True, True)


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mocks the window, the sprites, the menu steps and the capture."""
    mocks = MagicMock()
    mocks.resolve_input_handle.return_value = HANDLE
    mocks.set_resolution.return_value = (1920, 1080)
    mocks.grab.return_value = _frame((800, 600))
    monkeypatch.setattr(probe, "resolve_input_handle", mocks.resolve_input_handle)
    monkeypatch.setattr(probe, "menu_sprites", mocks.menu_sprites)
    monkeypatch.setattr(probe, "_screen_size", lambda: (2560, 1440))
    monkeypatch.setattr(probe.menus, "set_resolution", mocks.set_resolution)
    monkeypatch.setattr(probe.ProbeClient, "front", mocks.front)
    monkeypatch.setattr(probe.ProbeClient, "fit", mocks.fit)
    monkeypatch.setattr(probe, "grab", mocks.grab)
    monkeypatch.setattr(probe, "_client_rect", lambda _: _rect(10, 20, 810, 620))
    monkeypatch.setattr(probe, "where", lambda _: "WHERE THE CLIENT IS.")
    return mocks


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = probe.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_list_prints_the_windowed_sizes(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(["resolution", "--list"], capsys)

    assert code == 0
    assert json.loads(out)["sizes"] == [
        "800x600",
        "1024x768",
        "1280x720",
        "1366x768",
        "1920x1080",
        "1920x1200",
        "2560x1440",
    ]


def test_it_sets_the_size_and_prints_before_and_after(
    cli: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(["resolution", "800x600"], capsys)

    assert code == 0
    assert json.loads(out) == {
        "ok": True,
        "before": [1920, 1080],
        "after": [800, 600],
        "origin": [10, 20],
    }
    assert cli.set_resolution.call_args.args[2] == (800, 600)
    # The client is brought to the front, and onto the primary monitor, before the
    # first step reads the screen.
    names = [name for name, _, _ in cli.mock_calls]
    assert names.index("front") < names.index("fit") < names.index("set_resolution")


@pytest.mark.parametrize(
    "size",
    [
        "640x480",  # not in the list
        "1920x1080 (Full Screen)",  # full-screen entries are refused
        "1920x1080fs",
        "big",
    ],
)
def test_a_size_it_cannot_set_is_refused_before_any_input(
    cli: MagicMock, capsys: pytest.CaptureFixture[str], size: str
) -> None:
    code, out, err = _run(["resolution", size], capsys)

    assert code == probe.EXIT_REFUSED
    assert out == ""
    assert "Nothing was sent" in err
    cli.resolve_input_handle.assert_not_called()
    cli.set_resolution.assert_not_called()


def test_a_size_bigger_than_the_screen_is_refused(
    cli: MagicMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(probe, "_screen_size", lambda: (1920, 1080))

    code, _, err = _run(["resolution", "1920x1200"], capsys)

    assert code == probe.EXIT_REFUSED
    assert "doesn't fit" in err
    cli.resolve_input_handle.assert_not_called()


def test_a_client_at_another_size_after_confirm_exits_non_zero(
    cli: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.grab.return_value = _frame((1024, 768))

    code, out, err = _run(["resolution", "800x600"], capsys)

    assert code == probe.EXIT_ERROR
    assert out == ""
    assert "1024x768 after Confirm, not 800x600" in err


def test_a_failed_step_is_named(
    cli: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.set_resolution.side_effect = menus.MenuError(
        "open the resolution list", "expected the list"
    )

    code, _, err = _run(["resolution", "800x600"], capsys)

    assert code == probe.EXIT_ERROR
    assert "'open the resolution list' failed: expected the list" in err
    assert err.rstrip().endswith("WHERE THE CLIENT IS.")


def test_a_frame_that_is_not_ok_after_confirm_says_where_the_client_is(
    cli: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.grab.side_effect = probe.ProbeError(probe.EXIT_FRAME_NOT_OK, "Not ok.")

    code, _, err = _run(["resolution", "800x600"], capsys)

    assert code == probe.EXIT_FRAME_NOT_OK
    assert err.strip() == "Not ok. WHERE THE CLIENT IS."


SCREEN = (2560, 1440)
WORK_AREA = _rect(0, 0, 2560, 1392)  # a 48 px taskbar along the bottom


@pytest.mark.parametrize(
    ("rect", "origin"),
    [
        # Already entirely on the screen, if under the taskbar: left alone.
        (_rect(0, 0, 2560, 1440), None),
        (_rect(300, 300, 1100, 900), None),
        # 13 px past the bottom, as #412 saw at 1920x1200: up into the work area.
        (_rect(320, 253, 2240, 1453), (320, 192)),
        # Off the top-left: the least move that brings it on.
        (_rect(-8, -31, 1912, 1049), (0, 0)),
        # Off the right only: moved left, its top kept.
        (_rect(1000, 100, 2920, 1180), (640, 100)),
        # Taller than the work area: inside the screen instead.
        (_rect(0, 40, 1920, 1460), (0, 20)),
        # Bigger than the screen: it can't be.
        (_rect(0, 0, 3000, 1440), None),
    ],
)
def test_the_client_is_moved_onto_the_primary_monitor_as_little_as_possible(
    rect: Box, origin: tuple[int, int] | None
) -> None:
    assert probe.fitted_origin(rect, SCREEN, WORK_AREA) == origin


def test_where_names_the_size_the_position_and_whether_it_is_on_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(probe, "_screen_size", lambda: SCREEN)
    monkeypatch.setattr(probe, "_client_rect", lambda _: _rect(0, 253, 1920, 1453))

    assert probe.where(HANDLE) == (
        "The client is 1920x1200, its client area at (0, 253), not entirely on "
        "the 2560x1440 primary monitor."
    )


@pytest.fixture
def io(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The input functions under the guards, as children of one mock, in order."""
    io = MagicMock()
    io.activate = AsyncMock(return_value=False)
    io.press = AsyncMock()
    io.mouse_move_and_click = AsyncMock()
    for name in ("activate", "release_all", "press", "mouse_move_and_click"):
        monkeypatch.setattr(probe, name, getattr(io, name))
    monkeypatch.setattr(probe.HeldKeysLedger, "reset", io.reset)
    return io


GUARD = [call.activate(HANDLE), call.reset(), call.release_all(HANDLE)]


def test_each_key_is_a_guarded_gesture(io: MagicMock) -> None:
    probe.ProbeClient(HANDLE).press("escape")

    assert io.mock_calls == [
        *GUARD,
        call.press(HANDLE, "escape"),
        call.release_all(HANDLE),
    ]


def test_each_click_is_a_guarded_gesture(io: MagicMock) -> None:
    probe.ProbeClient(HANDLE).click(10, 20)

    assert io.mock_calls == [
        *GUARD,
        call.mouse_move_and_click(HANDLE, (10, 20)),
        call.release_all(HANDLE),
    ]


def test_front_sends_no_key(io: MagicMock) -> None:
    probe.ProbeClient(HANDLE).front()

    assert io.mock_calls == [*GUARD, call.release_all(HANDLE)]


def test_a_failing_click_still_releases_every_key(io: MagicMock) -> None:
    io.mouse_move_and_click.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        probe.ProbeClient(HANDLE).click(10, 20)

    assert io.mock_calls[-1] == call.release_all(HANDLE)
