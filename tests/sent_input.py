"""
What the controller sends to a game client, recorded where it leaves the process.

`install` patches only the operating system's side of the send path:

- `_send_input` (`SendInput`) and `_post_message` (`PostMessage`), which record the
  structures they are handed, decoded back to keys, instead of sending them;
- `activate`, so no window is brought to the foreground;
- `_physically_held`, so `release_all`'s reconciliation sweep reads no physical
  keyboard;
- `asyncio.sleep`, which advances a virtual clock instead of waiting.

Everything above them (`press`, `write`, `release_all`, `focused_inputs`, the
Held-Keys Ledger) runs as it does live, so a recorded Step is one the game would
have received, at the time it would have received it.
"""

import asyncio
import importlib
import string
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, Literal

import pytest
import win32con

from botting.controller.inputs.inputs_helpers import (
    KEYBOARD_MAPPING,
    _get_virtual_key,
    _keyboard_layout_handle,
)

# `botting.controller.inputs` re-exports `focused_inputs` as a name, shadowing the
# submodule of the same name, so the module objects are fetched explicitly.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)
non_focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.non_focused_inputs"
)

Event = Literal["keydown", "keyup", "char"]


@dataclass(frozen=True)
class Sent:
    """
    One key event that reached the client.

    :ivar key: The key's name (`"enter"`, `"1"`, `"h"`), or the character itself
        when it was typed as a character (a Unicode `SendInput`, or `WM_CHAR`).
    :ivar event: `keydown`, `keyup`, or `char` for a `WM_CHAR` message.
    :ivar at: When it was sent, in seconds on the virtual clock.
    :ivar typed: Whether it was typed as a character rather than pressed as a key.
    """

    key: str
    event: Event
    at: float
    typed: bool = False


@dataclass
class SentInput:
    """
    Everything sent, in order, and every wait in between.

    :ivar steps: The key events, in the order they were sent.
    :ivar sleeps: Every `asyncio.sleep` asked for, in order.
    :ivar now: The virtual clock, in seconds.
    """

    steps: list[Sent] = field(default_factory=list[Sent])
    sleeps: list[float] = field(default_factory=list[float])
    now: float = 0.0
    _names: dict[int, str] = field(default_factory=dict[int, str])

    def keys(self) -> list[tuple[str, Event]]:
        """The steps without their times: `(key, event)` in order."""
        return [(step.key, step.event) for step in self.steps]

    def gap_before(self, index: int) -> float:
        """The time between step `index` and the one before it."""
        return self.steps[index].at - self.steps[index - 1].at

    def run(self, coroutine: Awaitable[Any]) -> None:
        """Run `coroutine` to completion on a fresh event loop."""

        async def _main() -> None:
            await coroutine

        asyncio.run(_main())

    def name(self, vk: int) -> str:
        """The name of virtual key `vk`."""
        return self._names.get(vk, f"vk_{vk:#04x}")

    def record(self, key: str, event: Event, typed: bool) -> None:
        """Note one key event, sent now."""
        self.steps.append(Sent(key, event, self.now, typed))


def _key_names(handle: int) -> dict[int, str]:
    """Virtual-key code to key name, on the keyboard layout `handle` sends with."""
    layout = _keyboard_layout_handle(handle)
    names: dict[int, str] = {}
    for name in KEYBOARD_MAPPING:
        names.setdefault(KEYBOARD_MAPPING[name], name)
    # Digits and letters first: `!` shares `1`'s virtual key, and `1` is the name.
    for char in string.digits + string.ascii_lowercase + string.punctuation:
        vk = _get_virtual_key(char, False, layout)
        if vk not in (0, 0xFF):
            names.setdefault(vk, char)
    return names


def install(monkeypatch: pytest.MonkeyPatch, handle: int) -> SentInput:
    """
    Record what is sent to `handle` instead of sending it.

    :param monkeypatch: The test's, which undoes every patch when it ends.
    :param handle: The window the test sends to. Any integer: no window is needed.
    :return: The record, filled as the test sends.
    """
    sent = SentInput(_names=_key_names(handle))
    real_sleep = asyncio.sleep

    async def _sleep(delay: float, result: object = None) -> object:
        sent.sleeps.append(delay)
        sent.now += delay
        return await real_sleep(0, result)

    def _send_input(structure: Any) -> None:  # noqa: ANN401
        count = int(structure[0].value)
        array = structure[1].contents
        for index in range(count):
            entry = array[index]
            assert entry.type == 1, "only keyboard input is decoded"
            ki = entry.structure.ki
            up = bool(ki.dwFlags & focused_inputs_module.KEYEVENTF_KEYUP)
            event: Event = "keyup" if up else "keydown"
            if ki.dwFlags & focused_inputs_module.KEYEVENTF_UNICODE:
                sent.record(chr(ki.wScan), event, typed=True)
            else:
                sent.record(sent.name(ki.wVk), event, typed=False)

    def _post_message(message: Any) -> None:  # noqa: ANN401
        kind = int(message[1].value)
        param = int(message[2].value)
        if kind == win32con.WM_CHAR:
            sent.record(chr(param), "char", typed=True)
        elif kind in (win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN):
            sent.record(sent.name(param), "keydown", typed=False)
        elif kind in (win32con.WM_KEYUP, win32con.WM_SYSKEYUP):
            sent.record(sent.name(param), "keyup", typed=False)
        else:
            raise AssertionError(f"unexpected message {kind:#x}")

    async def _activate(hwnd: int) -> bool:
        return False

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    monkeypatch.setattr(focused_inputs_module, "_send_input", _send_input)
    monkeypatch.setattr(focused_inputs_module, "activate", _activate)
    monkeypatch.setattr(focused_inputs_module, "_physically_held", lambda hwnd: set())
    monkeypatch.setattr(non_focused_inputs_module, "_post_message", _post_message)
    return sent


__all__ = ["Event", "Sent", "SentInput", "install"]
