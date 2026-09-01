"""
Low-level module that handles sending inputs to the focused window through SendInput().
"""

import asyncio
import ctypes
import logging
from collections.abc import Callable, Generator, Sequence
from ctypes import wintypes
from dataclasses import dataclass, field, replace
from typing import Any, Literal, cast

import win32con
from win32api import HIBYTE, GetAsyncKeyState, GetKeyState
from win32com.client import Dispatch
from win32gui import GetForegroundWindow, SetForegroundWindow

from .held_keys_ledger import HeldKeysLedger, InputState, require_main_process
from .inputs_helpers import (
    _EXPORTED_FUNCTIONS,
    EXTENDED_KEYS,
    MAPVK_VK_TO_VSC_EX,
    OVERHEAD,
    _get_virtual_key,
    _keyboard_layout_handle,
    random_delay,
)
from .shared_resources import SharedResources

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

logger = logging.getLogger(__name__)

KeyboardEvent = Literal["keydown", "keyup"]
MouseEvent = Literal["mousedown", "mouseup"]
ClickEvent = Literal["click"]
EVENTS = KeyboardEvent | MouseEvent | ClickEvent
InputValue = str | tuple[int, int] | None
InputEntry = InputValue | Sequence[InputValue]
EventValue = EVENTS | None
EventEntry = EventValue | Sequence[EventValue]
SendInputStructure = tuple[wintypes.UINT, Any, wintypes.INT]
OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}


class MouseInputStruct(ctypes.Structure):
    """Contains information about a simulated mouse event."""

    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KeyBdInputStruct(ctypes.Structure):
    """Contains information about a simulated keyboard event."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInputStruct(ctypes.Structure):
    """
    Contains information about a simulated message generated
    by an input device other than a keyboard or mouse.
    Not Implemented.
    """

    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class CombinedInput(ctypes.Union):
    """Contains information about a simulated event of any kind."""

    _fields_ = [
        ("ki", KeyBdInputStruct),
        ("mi", MouseInputStruct),
        ("hi", HardwareInputStruct),
    ]


class Input(ctypes.Structure):
    """
    Used by SendInput to store information for synthesizing input events
    such as keystrokes, mouse movement, and mouse clicks.
    """

    _fields_ = [("type", wintypes.DWORD), ("structure", CombinedInput)]


InputArray = Input * 1


MOUSE = wintypes.DWORD(0)
KEYBOARD = wintypes.DWORD(1)
HARDWARE = wintypes.DWORD(2)


@dataclass
class KeyboardInputWrapper:
    """
    Dataclass that stores the input structure and the delay to wait before sending
    the next input.
    """

    handle: int
    keys: list[str | list[str]] = field(default_factory=list["str | list[str]"])
    events: list[EVENTS | list[EVENTS]] = field(
        default_factory=list["EVENTS | list[EVENTS]"]
    )
    delays: list[float] = field(default_factory=list[float])
    forced_key_releases: list[str] = field(default_factory=list[str])
    initial_state: InputState | None = None

    def __post_init__(self) -> None:
        """
        Before the instance is finalized, look into top-level held keys (directed to the
        relevant window).
        If opposites keys to the ones desired are held, release them.

        `initial_state` overrides the Held-Keys Ledger read below, so
        offline/deterministic compilation can supply the start state instead. Compiling
        outside Main Process must supply it: no other process owns a ledger.

        It is one value object rather than a held set beside a typematic owner, because
        a call site reading one half and forgetting the other is exactly issue #97 -
        `H0` and `T0` are one question, asked once. The resolved state is stored back
        onto the field, so it is an `InputState` for the rest of the instance's life,
        `keys_held` has an `H0` to accumulate from and `typematic_owner` a `T0`. It also
        stops `truncate` re-reading the ledger for the copy.

        `desired_keys` stays sequence-local - what these Steps want held, which is not
        the same question as what is already down.
        """
        if self.initial_state is None:
            self.initial_state = get_input_state(self.handle)
        self._clear_opposites(
            held_keys=set(self.initial_state.held_keys),
            desired_keys=self.get_held_movement_keys(self.keys, self.events),
        )

    def _clear_opposites(
        self, held_keys: set[str], desired_keys: set[str], idx: int | None = None
    ) -> None:
        """
        Utility function that compares the desired keys to be held versus those already
        held. If the opposites are held, a release event is inserted.

        Only keys `held_keys` reports as down are released. This used to also release
        the opposite of any desired `left`/`right` unconditionally, as a blunt guard
        against a stale direction latching the character - a guard that only existed
        because compile-time held-keys state was untrustworthy. The Held-Keys Ledger
        makes it authoritative, so the guard goes and **A6 No Phantom Release** holds:
        no keyup targets a key that is not down.
        """
        to_release: list[str] = []
        for key in filter(lambda k: k in ("left", "right", "up", "down"), desired_keys):
            if OPPOSITES[key] in held_keys:
                to_release.append(OPPOSITES[key])

        if to_release:
            releases: list[EVENTS] = ["keyup"] * len(to_release)
            self.insert(idx or 0, to_release, releases, next(random_delay))

    def __str__(self) -> str:
        result: list[str] = []
        current_key = None
        current_event = None
        total_delay = 0.0
        for key, event, delay in zip(self.keys, self.events, self.delays):
            if key != current_key or event != current_event:
                if current_key is not None:
                    result.append(
                        f"{current_key} {current_event} for {total_delay:.3f}s"
                    )
                current_key = key
                current_event = event
                total_delay = delay
            else:
                total_delay += delay + OVERHEAD
        if current_key is not None:
            result.append(f"{current_key} {current_event} for {total_delay:.3f}s")
        return "\n".join(
            result
            + [
                f"Total Duration: {self.duration:.3f}s",
                f"Forced Key Releases: {self.forced_key_releases}",
            ],
        )

    @property
    def c_input(self) -> list[SendInputStructure]:
        inputs = cast(Sequence[InputEntry], self.keys)
        events = cast(Sequence[EventEntry], self.events)
        return input_constructor(self.handle, inputs, events)

    @property
    def duration(self) -> float:
        return sum(self.delays) + OVERHEAD * len(self.delays)

    def append(
        self, keys: str | list[str], events: EVENTS | list[EVENTS], delay: float
    ) -> None:
        """
        Before appending new keys, retrospectively look at prior held keys and insert
        release events on opposites, if any.

        The release goes at the end - immediately ahead of the Step about to be
        appended. It used to go at `-1`, which lands *before* the last existing Step:
        when that Step was the keydown of the very key being released, the sequence
        read `keyup, keydown, <opposite> keydown`, leaving both directions down (A3)
        off a keyup for a key that was not yet pressed (A6).
        """
        self._clear_opposites(
            held_keys=self.keys_held,
            desired_keys=self.get_held_movement_keys([keys], [events]),
            idx=len(self.keys),
        )
        self.keys.append(keys)
        self.events.append(events)
        self.delays.append(delay)

    def insert(
        self,
        index: int,
        keys: str | list[str],
        events: EVENTS | list[EVENTS],
        delay: float,
    ) -> None:
        self.keys.insert(index, keys)
        self.events.insert(index, events)
        self.delays.insert(index, delay)

    def fill(
        self,
        key: str,
        event: EVENTS,
        delay_generator: Generator[float],
        limit: float,
    ) -> None:
        """
        Fills the structure with the given key and event until the duration reaches the
        limit.
        :param key:
        :param event:
        :param delay_generator:
        :param limit:
        :return:
        """
        while self.duration < limit:
            self.append(key, event, next(delay_generator))

    @property
    def keys_held(self) -> set[str]:
        """
        The keys down at the end of this sequence: `down(n-1)` in the invariant
        catalogue's terms.

        Accumulates from `initial_state.held_keys` - the catalogue's `down(-1) = H0` -
        so a key the Held-Keys Ledger reported at the sequence's start is reported here
        until a Step releases it. Walking from an empty set instead meant every
        builder after the first in a Movement Plan lost the inherited state
        (issue #97): `_resolve_held_keys` returns this property whenever a structure
        already exists.
        :return:
        """
        return self.get_held_movement_keys(
            self.keys,
            self.events,
            initial=self.initial_state.held_keys if self.initial_state else None,
        )

    @property
    def typematic_owner(self) -> str | None:
        """
        The key entitled to repeat at the end of this sequence: `own(n-1)` in the
        invariant catalogue's terms, and the `T0` the next sequence inherits.

        Seeded from `initial_state.typematic_owner` for the same reason `keys_held` is
        seeded from `H0`: a builder chaining onto an existing structure asks this of the
        structure rather than of the ledger, so a walk from `None` would lose the carry
        at the second builder in a Movement Plan - issue #97's defect, in the other half
        of the start state.
        :return: The owning key, or None when nobody owns.
        """
        return self.get_typematic_owner(
            self.keys,
            self.events,
            initial=self.initial_state.typematic_owner if self.initial_state else None,
        )

    @staticmethod
    def get_held_movement_keys(
        keys: list[str | list[str]],
        events: list[EVENTS | list[EVENTS]],
        initial: frozenset[str] | set[str] | None = None,
    ) -> set[str]:
        """
        Walks the Steps, tracking which keys a KEYDOWN left down and no KEYUP closed.

        :param initial: The keys already down before the first Step - the sequence's
            `H0`. Omitted, the walk starts from nothing, which is the right question
            for "what do these Steps want held" and the wrong one for "what is down".
        """
        keys_down: set[str] = set(initial) if initial else set()
        for key, event in zip(keys, events):
            if isinstance(key, list) and isinstance(event, list):
                for k, e in zip(key, event):
                    if e == "keydown":
                        keys_down.add(k)
                    elif e == "keyup":
                        keys_down.discard(k)
            elif isinstance(key, str) and isinstance(event, str):
                if event == "keydown":
                    keys_down.add(key)
                elif event == "keyup":
                    keys_down.discard(key)
            else:
                raise TypeError(f"Invalid key {key} or event {event}")
        return keys_down

    @staticmethod
    def get_typematic_owner(
        keys: list[str | list[str]],
        events: list[EVENTS | list[EVENTS]],
        initial: str | None = None,
    ) -> str | None:
        """
        Walks the Steps, tracking which key owns typematic, by the rule Spy++ settled on
        a live client: a keydown claims ownership, a later keydown takes it, and any
        keyup ends repetition outright rather than handing it back to a key still held.

        Within a simultaneous batch the walk keeps Step order, so the last keydown owns
        and a keyup anywhere in the batch drops ownership - the same order the game
        sees, since `SendInput` delivers the batch as a single array.

        :param initial: The key owning before the first Step - the sequence's `T0`.
            Omitted, the walk starts from nobody owning.
        :return: The key owning after the last Step, or None when nobody owns.
        """
        owner = initial
        for key, event in zip(keys, events):
            if isinstance(key, list) and isinstance(event, list):
                pairs = list(zip(key, event))
            elif isinstance(key, str) and isinstance(event, str):
                pairs = [(key, event)]
            else:
                raise TypeError(f"Invalid key {key} or event {event}")
            for k, e in pairs:
                if e == "keydown":
                    owner = k
                elif e == "keyup":
                    owner = None
        return owner

    async def send(self) -> int:
        return await focused_inputs(
            self.handle,
            self.c_input,
            self.delays,
            self.forced_key_releases,
            keys=self.keys,
            events=self.events,
        )

    def truncate(self, limit: float) -> KeyboardInputWrapper:
        result = KeyboardInputWrapper(
            self.handle,
            forced_key_releases=self.forced_key_releases,
            initial_state=self.initial_state,
        )
        generator = zip(self.keys, self.events, self.delays)
        while result.duration < limit:
            try:
                key, event, delay = next(generator)
                result.append(key, event, delay)
            except StopIteration:
                break
        return result


async def activate(hwnd: int) -> bool:
    """
    Activates the window associated with the handle.
    Any key press or mouse click will be sent to the active window.
    :return: None
    """
    acquired = False
    if GetForegroundWindow() != hwnd:
        acquired = await SharedResources.focus_lock.acquire()
        logger.debug("Activating window %s", hwnd)
        # Before activating, make sure to release any keys that are currently pressed.
        release_all(GetForegroundWindow())
        Dispatch("WScript.Shell").SendKeys("%")
        SetForegroundWindow(hwnd)

    elif not acquired and not SharedResources.focus_lock.locked():
        acquired = await SharedResources.focus_lock.acquire()
    return acquired


def release_all(hwnd: int | None = None) -> None:
    """
    Releases every key the Held-Keys Ledger holds for the window, then clears its
    entry. This is one of the two reconciliation points against physical key state -
    the other being the session-start sweep - so it also releases any key found down
    that the ledger did not know about (a human keystroke, or a leftover from a
    previous Session).
    :param hwnd: Handle to the window to release the keys from. Defaults to foreground.
    :return: None
    """
    require_main_process("release_all")
    if hwnd is None:
        hwnd = GetForegroundWindow()
    keys_to_release = set(HeldKeysLedger.keys_held(hwnd))
    stragglers = _physically_held(hwnd) - keys_to_release
    if stragglers:
        logger.warning(
            "Keys %s were physically down on window %s without being in the Held-Keys "
            "Ledger. Releasing them as well.",
            sorted(stragglers),
            hwnd,
        )
        keys_to_release |= stragglers
    if keys_to_release:
        logger.debug("Releasing keys %s from window %s", sorted(keys_to_release), hwnd)
    release_keys(sorted(keys_to_release), hwnd)
    HeldKeysLedger.clear(hwnd)


def _physically_held(hwnd: int) -> set[str]:
    """
    The reconciliation sweep itself: one `GetAsyncKeyState` per candidate key. Note the
    query is system-wide, so it describes the physical keyboard rather than this
    window - which is exactly what a reconciliation needs, and why it is only ever
    used while `hwnd` is the foreground window.
    :param hwnd: Handle to the window whose keyboard layout resolves the key names.
    :return: The candidate keys currently down.
    """
    layout = _keyboard_layout_handle(hwnd)
    return {
        key
        for key in HeldKeysLedger.sweep_candidates()
        if HIBYTE(GetAsyncKeyState(_get_virtual_key(key, False, layout))) != 0
    }


def release_directions(hwnd: int | None = None) -> None:
    """
    Releases every direction key the Held-Keys Ledger holds for the window. Unlike
    `release_all` this is not a reconciliation point: it reads the ledger and sends
    nothing for keys the ledger does not hold.

    Note this sends outside the focus lock, so it only reaches `hwnd` while `hwnd` is
    the foreground window. Cancelling a movement Action does not need it - the send
    loop releases directions from inside its own critical section (see
    `focused_inputs`).
    :param hwnd: Handle to the window to release from. Defaults to foreground.
    :return: None
    """
    require_main_process("release_directions")
    if hwnd is None:
        hwnd = GetForegroundWindow()
    held = HeldKeysLedger.keys_held(hwnd)
    _release_keys = [key for key in OPPOSITES if key in held]
    if _release_keys:
        logger.debug("Releasing keys %s from window %s", _release_keys, hwnd)
        release_keys(_release_keys, hwnd)


def input_constructor(
    hwnd: int,
    inputs: Sequence[InputEntry],
    events: Sequence[EventEntry],
    as_unicode: bool = False,
    mouse_data: int | None = None,
) -> list[SendInputStructure]:
    """
    Constructs the input structures for the given inputs and events.
    These must be of the same length. When an item in inputs is a list, the
    corresponding item in events must also be a list. Those are considered as a single
    input array for the purpose of SendInput, so they are sent simultaneously.
    :param hwnd: Handle to the window that will receive the inputs.
    :param inputs: keystrokes (str), mouse coordinates (tuple), None, or a list of those
    :param events: "keydown", "keyup", "click", "mousedown", "mouseup",
        or a list of those
    :param as_unicode: TODO
    :param mouse_data: TODO
    :return: Series of input structures to be sent to the active window with SendInput.
    """
    structures: list[SendInputStructure] = []
    for lst_inputs, lst_events in zip(inputs, events):
        if isinstance(lst_inputs, str):  # Keyboard input
            assert isinstance(lst_events, str)
            assert lst_events in {"keydown", "keyup"}
            HeldKeysLedger.note_sent(lst_inputs)
            input_array_class = Input * 1
            input_array = input_array_class(
                _single_input_constructor(
                    hwnd,
                    lst_inputs,
                    cast(KeyboardEvent, lst_events),
                    as_unicode,
                )
            )
            structures.append(
                (
                    wintypes.UINT(1),
                    ctypes.POINTER(input_array_class)(input_array),
                    wintypes.INT(ctypes.sizeof(Input)),
                )
            )
        elif isinstance(lst_inputs, tuple) and lst_events is None:  # Mouse move input
            x, y = cast(tuple[int, int], lst_inputs)
            input_array_class = Input * 1
            input_array = input_array_class(
                _single_input_mouse_constructor(x, y, None, mouse_data)
            )
            structures.append(
                (
                    wintypes.UINT(1),
                    ctypes.POINTER(input_array_class)(input_array),
                    wintypes.INT(ctypes.sizeof(Input)),
                )
            )
        elif lst_inputs is None:  # Click events
            assert lst_events in {None, "mousedown", "mouseup", "click"}
            input_array_class = Input * 1
            input_array = input_array_class(
                _single_input_mouse_constructor(
                    None,
                    None,
                    cast(MouseEvent | ClickEvent | None, lst_events),
                    mouse_data,
                )
            )
            structures.append(
                (
                    wintypes.UINT(1),
                    ctypes.POINTER(input_array_class)(input_array),
                    wintypes.INT(ctypes.sizeof(Input)),
                )
            )

        elif isinstance(lst_inputs, list) and isinstance(lst_events, list):
            assert len(lst_inputs) == len(lst_events)
            built_inputs: list[Input] = []
            for i, e in zip(lst_inputs, lst_events):
                if isinstance(i, str):
                    assert isinstance(e, str)
                    assert e in {"keydown", "keyup"}
                    built_inputs.append(
                        _single_input_constructor(
                            hwnd, i, cast(KeyboardEvent, e), as_unicode
                        )
                    )
                    HeldKeysLedger.note_sent(i)
                elif isinstance(i, tuple):
                    assert e is None
                    x, y = i
                    built_inputs.append(
                        _single_input_mouse_constructor(x, y, None, mouse_data)
                    )
                elif i is None:
                    assert e in {None, "mousedown", "mouseup", "click"}
                    built_inputs.append(
                        _single_input_mouse_constructor(
                            None,
                            None,
                            cast(MouseEvent | ClickEvent | None, e),
                            mouse_data,
                        )
                    )
                else:
                    raise TypeError(f"Unsupported input item: {i!r}")

            num_inputs = len(built_inputs)
            array_class = Input * num_inputs
            array_pointer = ctypes.POINTER(array_class)
            input_array = array_class()
            for index, value in enumerate(built_inputs):
                input_array[index] = value
            structures.append(
                (
                    wintypes.UINT(num_inputs),
                    array_pointer(input_array),
                    wintypes.INT(ctypes.sizeof(input_array[0])),
                )
            )

    return structures


async def focused_inputs(
    hwnd: int,
    inputs: list[SendInputStructure] | None = None,
    delays: list[float] | None = None,
    forced_key_releases: list[str] | None = None,
    keys: list[str | list[str]] | None = None,
    events: list[EVENTS | list[EVENTS]] | None = None,
    compiler: Callable[[InputState | None], KeyboardInputWrapper | None] | None = None,
) -> int:
    """
    Sends the inputs to the active window.
    A small delay is added between each input.
    :param hwnd: handle to the window to send the inputs to.
    :param inputs: input structures to send. Omitted when `compiler` is provided.
    :param delays: delays between each input. Omitted when `compiler` is provided.
    :param forced_key_releases: If provided, these are sure to be released at the end,
    even if the task is cancelled.
    :param keys: The keys each input structure carries, index-aligned with `inputs`.
    :param events: The events each input structure carries, index-aligned with `inputs`.
    :param compiler: Dispatch-time compilation. When provided, the Input Sequence is
    built here - after focus is acquired, from the Held-Keys Ledger - instead of being
    handed in pre-compiled. It is called with the whole `InputState`: held keys and
    typematic owner together. See `compile_and_send`.
    :return: Nbr of inputs successfully sent.

    Note:
        `keys` and `events` are what the Held-Keys Ledger is written from - the input
        structures themselves are opaque C buffers. A Step is recorded only once
        `_send_input` has returned, so the ledger describes the Delivered Prefix
        rather than the Input Sequence when cancellation truncates the loop.
        Callers sending no keyboard input (mouse moves, clicks) leave them None.

        `compiler` exists because held keys shape the *structure* of an Input
        Sequence, so the state it compiles against must be the state at dispatch, in
        this window. Compiling here rather than in the caller keeps the read and the
        first Step inside one focus-lock critical section, and keeps the compile
        window under the same cancellation handling as the send loop.

        Cancellation additionally releases every direction key the ledger holds for
        the window - invariant D2, "after a Preemption, no direction key remains
        down". This is the one release that `forced_key_releases` cannot express:
        that list fires on normal completion too, whereas a Continuation carries its
        direction key across the route-cycle boundary on purpose. Being here rather
        than in a task done-callback keeps the release inside the focus-lock critical
        section, so it reaches this client rather than whichever one the preempting
        Action has meanwhile brought to the foreground.
    """
    require_main_process("focused_inputs")
    res = 0
    acquired = False
    cancelled = False
    try:
        acquired = await activate(hwnd)

        if compiler is not None:
            structure = compiler(get_input_state(hwnd))
            if structure is None:
                return res
            inputs = structure.c_input
            delays = structure.delays
            keys = structure.keys
            events = structure.events
            forced_key_releases = structure.forced_key_releases

        # Either a `compiler` produced them just above, or the caller handed them in.
        assert inputs is not None, "focused_inputs needs inputs or a compiler"
        assert delays is not None, "focused_inputs needs delays or a compiler"

        for i in range(len(inputs)):
            _send_input(inputs[i])
            res += 1
            if keys is not None and events is not None:
                HeldKeysLedger.record_step(hwnd, keys[i], events[i])
            await asyncio.sleep(delays[i])
        return res

    except asyncio.CancelledError:
        cancelled = True
        raise

    except Exception:
        raise

    finally:
        held = HeldKeysLedger.keys_held(hwnd)
        keys_to_release = {k for k in forced_key_releases or () if k in held}
        if cancelled:
            keys_to_release.update(k for k in OPPOSITES if k in held)
        if keys_to_release:
            release_keys(sorted(keys_to_release), hwnd)
        if acquired:
            SharedResources.focus_lock.release()


async def compile_and_send(
    hwnd: int,
    compiler: Callable[[InputState | None], KeyboardInputWrapper | None],
) -> int:
    """
    The live path's entry point: an ActionRequest procedure that carries the plan
    rather than a compiled Input Sequence, and compiles it at dispatch.

    Acquire focus -> read the Held-Keys Ledger for `hwnd` -> compile through the
    `initial_state` seam -> stream the Steps, all inside one critical section.
    A DecisionMaker deciding in its own process cannot do the read: only Main Process
    owns a ledger, and by dispatch its snapshot would be stale anyway (see ADR 0002).
    :param hwnd: Handle to the client window the sequence targets.
    :param compiler: Called with the `InputState` the ledger reports for `hwnd` - the
    movement keys held, the typematic owner, and how long it has owned; returns the
    Input Sequence to send, or None when there is nothing to send.
    :return: Nbr of inputs successfully sent.
    """
    return await focused_inputs(hwnd, compiler=compiler)


def get_held_movement_keys(hwnd: int) -> list[str]:
    """
    Returns a list of the currently held movement keys, read from the Held-Keys Ledger.
    Only Main Process owns a ledger, so a call from an Engine process reports none held
    (and warns once) - live compilation must be fed ledger state at dispatch instead.
    :param hwnd: Handle to the client window.
    :return: The movement keys currently down for that client.
    """
    held = HeldKeysLedger.keys_held(hwnd)
    return [key for key in OPPOSITES if key in held]


def get_input_state(hwnd: int) -> InputState:
    """
    The compiler seam's start state, read from the Held-Keys Ledger: the movement keys
    held for this client, the key that owns typematic, and how long it has owned.

    `held_keys` is narrowed to movement keys, which is what the seam has always
    described - held state shapes a movement's structure and no other key's does. The
    owner is deliberately *not* narrowed: a teleport or skill key can own typematic, and
    collapsing that into "nobody owns" would wrongly forbid `teleport`'s own skill-key
    fill, which is legal precisely because its first Step is a genuine press.

    Only Main Process owns a ledger, so a call from an Engine process reports nothing
    held and nobody owning (and warns once) - live compilation must be fed this at
    dispatch instead.
    :param hwnd: Handle to the client window.
    :return: The state to compile that client's next Input Sequence against.
    """
    state = HeldKeysLedger.input_state(hwnd)
    return replace(
        state, held_keys=frozenset(key for key in OPPOSITES if key in state.held_keys)
    )


def _send_input(structure: SendInputStructure) -> None:
    """
    Sends the input structure to the active window.
    :param structure: A single input structure.
    :return:
    """
    failure_count = 0
    count = int(structure[0].value)
    array_class = Input * count
    pointer = ctypes.POINTER(array_class)
    send_input: Any = _EXPORTED_FUNCTIONS["SendInput"]
    send_input.argtypes = [wintypes.UINT, pointer, wintypes.INT]
    while send_input(*structure) != count:
        logger.error("Failed to send input %s", structure)
        failure_count += 1
        if failure_count > 10:
            logger.critical("Unable to send structure %s to active window", structure)
            raise RuntimeError(f"Unable to send structure {structure} to active window")


def _single_input_constructor(
    hwnd: int,
    key: str,
    event: KeyboardEvent,
    as_unicode: bool = False,
) -> Input:
    """
    Constructs a single input structure for the given key and event.
    :param hwnd:
    :param key:
    :param event:
    :param as_unicode:
    :return:
    """
    assert isinstance(key, str)
    assert isinstance(event, str)
    assert event in ["keyup", "keydown"], f"Event type {event} is not supported"
    flags = KEYEVENTF_EXTENDEDKEY if key in EXTENDED_KEYS else 0
    vk_key = _get_virtual_key(key, False, _keyboard_layout_handle(hwnd))
    if as_unicode:
        assert len(key) == 1, (
            f"Key {key} must be a single character when as_unicode=True"
        )
        scan_code = _get_virtual_key(key, True, _keyboard_layout_handle(hwnd))
        vk_key = 0
        flags |= KEYEVENTF_UNICODE
    else:
        scan_code = _EXPORTED_FUNCTIONS["MapVirtualKeyExW"](
            vk_key,
            MAPVK_VK_TO_VSC_EX,
            _keyboard_layout_handle(hwnd),
        )
    flags = flags | KEYEVENTF_KEYUP if event == "keyup" else flags

    keybd_input = KeyBdInputStruct(
        wintypes.WORD(vk_key),
        wintypes.WORD(scan_code),
        wintypes.DWORD(flags),
        wintypes.DWORD(0),
        None,
    )
    input_struct = Input(type=KEYBOARD, structure=CombinedInput(ki=keybd_input))
    return input_struct


def _single_input_mouse_constructor(
    x: int | None,
    y: int | None,
    event: MouseEvent | ClickEvent | None,
    mouse_data: int | None,
) -> Input:
    """
    :param x: Absolute X target mouse cursor position.
    :param y: Absolute Y target mouse cursor position.
    :param event: Whether the event is a click, down or up, or nothing.
    :param mouse_data: Set to 0 unless mouse scroll is used.
    :return:
    """
    if mouse_data is None:
        mouse_data = 0
    flags = 0
    if x is not None and y is not None:
        flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE
    else:
        x = 0
        y = 0

    if event is not None:
        if event == "mousedown":
            flags |= MOUSEEVENTF_LEFTDOWN
        elif event == "mouseup":
            flags |= MOUSEEVENTF_LEFTUP
        else:
            raise ValueError(f"Event {event} is not supported.")

    assert flags != 0, "Either x, y or event must be provided."
    mouse_input = MouseInputStruct(
        wintypes.LONG(x),
        wintypes.LONG(y),
        wintypes.DWORD(mouse_data),
        wintypes.DWORD(flags),
        wintypes.DWORD(0),
        None,
    )
    input_struct = Input(type=MOUSE, structure=CombinedInput(mi=mouse_input))
    return input_struct


def _remove_num_lock() -> None:
    """
    Removes the num lock if it is on.
    :return:
    """
    if GetKeyState(win32con.VK_NUMLOCK) != 0:
        logger.info("NumLock is on. Turning it off.")
        array_class = Input * 2
        array_pointer = ctypes.POINTER(array_class)
        _input = [
            _single_input_constructor(GetForegroundWindow(), "num_lock", "keydown"),
            _single_input_constructor(GetForegroundWindow(), "num_lock", "keyup"),
        ]

        input_array = array_class()
        for index, value in enumerate(_input):
            input_array[index] = value
        _send_input(
            (
                wintypes.UINT(2),
                array_pointer(input_array),
                wintypes.INT(ctypes.sizeof(input_array[0])),
            )
        )


_remove_num_lock()


def release_keys(keys: list[str], handle: int | None = None) -> None:
    """
    Releases the given keys.
    :param keys: Keys to release.
    :param handle: Handle to the window to release the keys.
    :return: Input structure to release the given keys.
    """
    require_main_process("release_keys")
    if handle is None:
        handle = GetForegroundWindow()
    if keys:
        events: list[Literal["keyup"]] = ["keyup"] * len(keys)
        inputs = input_constructor(
            handle,
            [keys],
            [events],
        )
        if inputs:
            _send_input(inputs[0])
            HeldKeysLedger.record_step(handle, list(keys), events)
