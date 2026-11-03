"""
The probe's input commands, with the input layer mocked: every command runs its
guards in order, releases every key whatever happens, and a refusal sends nothing.
"""

import json
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from botting.controller.inputs import HeldKeysLedger, SharedResources
from botting.utilities import CLIENT_HORIZONTAL_MARGIN_PX, CLIENT_VERTICAL_MARGIN_PX
from maple import probe

HANDLE = 4242


@pytest.fixture(autouse=True)
def _empty_ledger() -> Iterator[None]:
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


@pytest.fixture
def io(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """
    Mocks the window and every input function the probe calls. They are children of
    one mock, so `io.mock_calls` is the order they ran in.
    """
    monkeypatch.setattr(probe, "get_open_clients", lambda: [HANDLE])
    monkeypatch.setattr(probe, "maple_ign_finder", lambda handle: "Alice")
    monkeypatch.setattr(
        probe, "key_binds", lambda ign: {"Inventory Menu": "i", "Sneaky": "left"}
    )
    monkeypatch.setattr(probe, "_client_size", lambda handle: (1024, 768))

    io = MagicMock()
    io.activate = AsyncMock(return_value=False)
    io.reset = MagicMock()
    io.release_all = MagicMock()
    io.release_directions = MagicMock()
    io.press = AsyncMock()
    io.write = AsyncMock()
    io.mouse_move_and_click = AsyncMock()
    io.send = AsyncMock()
    io.move = MagicMock(return_value=MagicMock(send=io.send))
    for name in (
        "activate",
        "release_all",
        "release_directions",
        "press",
        "write",
        "mouse_move_and_click",
        "move",
    ):
        monkeypatch.setattr(probe, name, getattr(io, name))
    monkeypatch.setattr(probe.HeldKeysLedger, "reset", io.reset)
    return io


# One case per input command: its argv, the mock its gesture goes through, and the
# calls the gesture makes.
TARGET = (100 + CLIENT_HORIZONTAL_MARGIN_PX, 50 + CLIENT_VERTICAL_MARGIN_PX)
COMMANDS = {
    "press": (["press", "i"], "press", [call.press(HANDLE, "i")]),
    "hold": (
        ["hold", "right", "--ms", "500"],
        "send",
        [
            call.move(HANDLE, "right", duration=0.5),
            call.send(),
            call.release_directions(HANDLE),
        ],
    ),
    "write": (["write", "hello"], "write", [call.write(HANDLE, "hello")]),
    "click": (
        ["click", "100", "50"],
        "mouse_move_and_click",
        [call.mouse_move_and_click(HANDLE, TARGET)],
    ),
}
GUARD_BEFORE = [call.activate(HANDLE), call.reset(), call.release_all(HANDLE)]
GUARD_AFTER = [call.release_all(HANDLE)]


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def _assert_nothing_sent(io: MagicMock) -> None:
    assert io.mock_calls == []


# --- the order ---------------------------------------------------------------


@pytest.mark.parametrize("command", COMMANDS)
def test_each_command_runs_the_guards_in_order(
    io: MagicMock, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    argv, _, gesture = COMMANDS[command]

    assert probe.main(argv) == 0

    assert io.mock_calls == GUARD_BEFORE + gesture + GUARD_AFTER
    out = _out(capsys)
    assert out["ok"] is True
    assert out["held_after"] == []


@pytest.mark.parametrize("command", COMMANDS)
def test_an_exception_in_the_gesture_still_releases_every_key(
    io: MagicMock, command: str
) -> None:
    argv, failing, _ = COMMANDS[command]
    getattr(io, failing).side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        probe.main(argv)

    assert io.mock_calls[: len(GUARD_BEFORE)] == GUARD_BEFORE
    assert io.mock_calls[-1] == call.release_all(HANDLE)


@pytest.mark.parametrize("command", COMMANDS)
def test_ctrl_c_in_the_gesture_still_releases_every_key(
    io: MagicMock, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    argv, failing, _ = COMMANDS[command]
    getattr(io, failing).side_effect = KeyboardInterrupt

    assert probe.main(argv) == probe.EXIT_INTERRUPTED

    assert io.mock_calls[: len(GUARD_BEFORE)] == GUARD_BEFORE
    assert io.mock_calls[-1] == call.release_all(HANDLE)
    assert capsys.readouterr().out == ""


def test_a_failed_activate_still_releases_every_key(io: MagicMock) -> None:
    io.activate.side_effect = RuntimeError("no focus")

    with pytest.raises(RuntimeError, match="no focus"):
        probe.main(["press", "i"])

    assert io.mock_calls == [call.activate(HANDLE), call.release_all(HANDLE)]


def test_the_focus_lock_activate_took_is_handed_back_before_the_gesture(
    io: MagicMock,
) -> None:
    async def take_the_lock(handle: int) -> bool:
        return await SharedResources.focus_lock.acquire()

    io.activate.side_effect = take_the_lock
    io.press.side_effect = lambda *a: assert_unlocked()

    def assert_unlocked() -> None:
        assert not SharedResources.focus_lock.locked()

    assert probe.main(["press", "i"]) == 0

    io.press.assert_awaited_once()
    assert not SharedResources.focus_lock.locked()


# --- what each gesture sends -------------------------------------------------


def test_press_resolves_a_binding_name_case_insensitively(
    io: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert probe.main(["press", "INVENTORY menu"]) == 0

    io.press.assert_awaited_once_with(HANDLE, "i")
    assert _out(capsys) == {"ok": True, "pressed": "i", "times": 1, "held_after": []}


def test_press_accepts_a_plain_key_name(io: MagicMock) -> None:
    assert probe.main(["press", "Escape"]) == 0

    io.press.assert_awaited_once_with(HANDLE, "escape")


def test_press_times_presses_that_many_complete_times(io: MagicMock) -> None:
    assert probe.main(["press", "i", "--times", "10"]) == 0

    assert io.press.await_args_list == [call(HANDLE, "i")] * 10


def test_press_with_ign_reads_that_ign_s_bindings(
    io: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "get_client_handle", lambda ign, finder: HANDLE)
    seen: list[str] = []
    monkeypatch.setattr(
        probe, "key_binds", lambda ign: seen.append(ign) or {"loot": "z"}
    )

    assert probe.main(["press", "loot", "--ign", "Bob"]) == 0

    assert seen == ["Bob"]
    io.press.assert_awaited_once_with(HANDLE, "z")


def test_press_without_bindings_for_the_ign_still_takes_a_key_name(
    io: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_section(ign: str) -> dict[str, str]:
        raise AssertionError("No keybindings section")

    monkeypatch.setattr(probe, "key_binds", no_section)

    assert probe.main(["press", "enter"]) == 0

    io.press.assert_awaited_once_with(HANDLE, "enter")


# --- refusals send nothing ---------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["press", "no such key"],
        ["press", "left"],
        ["press", "RIGHT"],
        ["press", "sneaky"],  # a binding that names a direction
        ["click", "1024", "0"],
        ["click", "0", "768"],
    ],
)
def test_a_refused_input_exits_non_zero_and_sends_nothing(
    io: MagicMock, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    assert probe.main(argv) == probe.EXIT_REFUSED

    _assert_nothing_sent(io)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err


def test_press_refuses_a_direction_and_points_to_hold(
    io: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    probe.main(["press", "up"])

    assert "hold up" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["press", "i", "--times", "11"],
        ["press", "i", "--times", "0"],
        ["hold", "right", "--ms", "10001"],
        ["hold", "right", "--ms", "0"],
        ["hold", "right"],
        ["hold", "jump", "--ms", "100"],
        ["click", "-1", "5"],
        ["click", "a", "5"],
    ],
)
def test_out_of_range_arguments_are_usage_errors_that_send_nothing(
    io: MagicMock, argv: list[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(argv)

    assert raised.value.code == 2
    _assert_nothing_sent(io)


def test_the_caps_themselves_are_allowed(io: MagicMock) -> None:
    assert probe.main(["hold", "left", "--ms", "10000"]) == 0

    io.move.assert_called_once_with(HANDLE, "left", duration=10.0)
