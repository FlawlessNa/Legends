"""
Key Times (#538): a ``key.down``/``key.up`` Telemetry Record per key transition,
written from where keys are sent, and nothing about what is sent changed.

Nothing here sends real input: `_send_input` is replaced by a fake that copies the
bytes each call would have handed `SendInput`, and the handles are arbitrary
integers. **C-KEYS** is the point of the first test: the same Movement Plan,
compiled from the same seed, reaches `SendInput` byte for byte the same, with the
same delays, whether key times are recorded or not.
"""

import asyncio
import ctypes
import functools
import importlib
import json
import logging
import random
from collections.abc import Iterator
from typing import Any

import pytest
from pytest_mock import MockerFixture

from botting.controller.inputs import key_times
from botting.controller.inputs.focused_inputs import (
    Input,
    KeyboardInputWrapper,
    compile_and_send,
    release_all,
)
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger, InputState
from botting.controller.inputs.shared_resources import SharedResources
from botting.telemetry import TELEMETRY_ATTR
from botting.telemetry_events import KEY_DOWN, KEY_UP
from maple.model.mechanics import movement_mechanics_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 4321
IGN = "TestChar"
JUMP_KEY = "space"

focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)

#: A walk into a jump, then a walk: direction keys held over typematic repeats, a
#: jump key pressed while the walk's key is down, and a terminal release.
PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 20),
    _MovementComponent(MovementTypes.JUMP_RIGHT, 2, duration=0.08),
    _MovementComponent(MovementTypes.WALK_RIGHT, 3),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
)


@pytest.fixture(autouse=True)
def clean_state(mocker: MockerFixture) -> Iterator[None]:
    """Empty ledger and buffer, and the jump key without the personal config."""
    mocker.patch.object(
        movement_mechanics_v2, "key_binds", return_value={"jump": JUMP_KEY}
    )
    HeldKeysLedger.reset()
    key_times.flush()
    yield
    HeldKeysLedger.reset()
    key_times.flush()


class _Sink(logging.Handler):
    """Collects the Telemetry Records that reach the `botting` logger tree."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        line = getattr(record, TELEMETRY_ATTR, None)
        if line is not None:
            self.records.append(json.loads(line))

    def keys(self) -> list[tuple[str, str, str]]:
        """(event type, key, cause) of every key record, in order."""
        return [
            (r["event_type"], r["payload"]["key"], r["payload"]["cause"])
            for r in self.records
            if r["event_type"] in (KEY_DOWN, KEY_UP)
        ]


@pytest.fixture
def sink() -> Iterator[_Sink]:
    handler = _Sink()
    logger = logging.getLogger(key_times.logger.name)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


class _Wire:
    """A fake `SendInput`: the bytes of every array it was handed, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes]] = []

    def send(self, structure: tuple[Any, Any, Any]) -> None:
        count = int(structure[0].value)
        size = int(structure[2].value)
        raw = ctypes.string_at(structure[1], count * ctypes.sizeof(Input))
        assert size == ctypes.sizeof(Input)
        self.calls.append((count, raw))


def _patch_focus(mocker: MockerFixture, wire: _Wire) -> None:
    async def _fake_activate(hwnd: int) -> bool:
        await SharedResources.focus_lock.acquire()
        return True

    mocker.patch.object(SharedResources, "focus_lock", asyncio.Lock())
    mocker.patch.object(focused_inputs_module, "activate", side_effect=_fake_activate)
    mocker.patch.object(focused_inputs_module, "_send_input", side_effect=wire.send)


def _send_plan(
    mocker: MockerFixture, seed: int
) -> tuple[list[tuple[int, bytes]], KeyboardInputWrapper]:
    """Compile `PLAN` at dispatch from `seed` and send it to a fake `SendInput`."""
    wire = _Wire()
    compiled: list[KeyboardInputWrapper] = []
    compiler = functools.partial(
        compile_movements,
        movements=PLAN,
        handle=HANDLE,
        ign=IGN,
        speed=100.0,
        total_duration=0.45,
        teleport=None,
        always_release=True,
    )

    def _compile(state: InputState | None) -> KeyboardInputWrapper | None:
        structure = compiler(state)
        assert structure is not None
        compiled.append(structure)
        return structure

    async def _run() -> None:
        _patch_focus(mocker, wire)
        await compile_and_send(HANDLE, _compile)

    random.seed(seed)
    HeldKeysLedger.reset()
    asyncio.run(_run())
    return wire.calls, compiled[0]


def _ledger_only(
    hwnd: int,
    keys: object,
    events: object,
    cause: str,
    origin: int | None = None,
    correlation_id: str | None = None,
) -> None:
    """The send path as it was before #538: the ledger, and nothing else."""
    HeldKeysLedger.record_step(hwnd, keys, events)  # type: ignore[arg-type]


# --- C-KEYS: nothing sent changes ----------------------------------------------


def test_recording_key_times_changes_no_byte_and_no_delay(
    mocker: MockerFixture, sink: _Sink
) -> None:
    with_times, sequence_with = _send_plan(mocker, seed=538)
    assert sink.keys(), "the scenario must record key times to prove anything"

    mocker.patch.object(
        focused_inputs_module, "_record_delivered", side_effect=_ledger_only
    )
    without, sequence_without = _send_plan(mocker, seed=538)

    assert with_times == without
    assert sequence_with.keys == sequence_without.keys
    assert sequence_with.events == sequence_without.events
    assert sequence_with.delays == sequence_without.delays
    assert sequence_with.origins == sequence_without.origins


# --- what is recorded ------------------------------------------------------------


def test_one_record_per_transition_and_none_per_repeat(
    mocker: MockerFixture, sink: _Sink
) -> None:
    wire = _Wire()

    def _sequence(state: InputState | None) -> KeyboardInputWrapper:
        # A typematic fill on `space` (three keydowns, one press), a batch, and a
        # delay-only Step.
        return KeyboardInputWrapper(
            HANDLE,
            ["space", "space", "space", ["right", "space"], [], ["right"]],
            ["keydown", "keydown", "keydown", ["keydown", "keyup"], [], ["keyup"]],
            [0.0] * 6,
            initial_state=InputState(),
        )

    async def _run() -> None:
        _patch_focus(mocker, wire)
        await compile_and_send(HANDLE, _sequence)

    asyncio.run(_run())
    assert len(wire.calls) == 6
    assert sink.keys() == [
        (KEY_DOWN, "space", "step"),
        (KEY_DOWN, "right", "step"),
        (KEY_UP, "space", "step"),
        (KEY_UP, "right", "step"),
    ]


def test_a_compiled_plan_records_its_presses_and_releases(
    mocker: MockerFixture, sink: _Sink
) -> None:
    _send_plan(mocker, seed=1)
    recorded = sink.keys()
    assert recorded[0] == (KEY_DOWN, "right", "step")
    assert (KEY_DOWN, JUMP_KEY, "step") in recorded
    assert (KEY_UP, JUMP_KEY, "step") in recorded
    # Every key that went down came up: the terminal release included.
    assert {r[1] for r in recorded if r[0] == KEY_DOWN} <= {
        r[1] for r in recorded if r[0] == KEY_UP
    }


def test_a_record_carries_the_frames_clock_the_wall_clock_and_provenance(
    mocker: MockerFixture, sink: _Sink
) -> None:
    mocker.patch.object(key_times, "stamp", return_value=(1234.5, 1.7e9))
    _send_plan(mocker, seed=2)
    payloads = [
        r["payload"] for r in sink.records if r["event_type"] in (KEY_DOWN, KEY_UP)
    ]
    first = payloads[0]
    assert first["t"] == 1234.5
    assert first["wall"] == 1.7e9
    assert first["handle"] == HANDLE
    jump = next(p for p in payloads if p["key"] == JUMP_KEY)
    assert jump["origin"] == 1  # the JUMP_RIGHT component
    ups = [p for p in payloads if "held" in p]
    assert ups
    assert all(p["held"] for p in ups)


def test_a_straggler_release_is_recorded_as_not_held(
    mocker: MockerFixture, sink: _Sink
) -> None:
    wire = _Wire()
    mocker.patch.object(focused_inputs_module, "_send_input", side_effect=wire.send)
    mocker.patch.object(
        focused_inputs_module, "_physically_held", return_value={"ctrl"}
    )
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")
    release_all(HANDLE)
    by_key = {r["payload"]["key"]: r for r in sink.records if r["event_type"] == KEY_UP}
    assert by_key["left"]["payload"]["held"] is True
    assert by_key["ctrl"]["payload"]["held"] is False
    assert by_key["ctrl"]["payload"]["cause"] == "release"
    # Outside any scheduled task: no Action sent it.
    assert by_key["ctrl"]["correlation_id"] is None


def test_records_carry_the_correlation_id_baked_into_the_compiler(
    mocker: MockerFixture, sink: _Sink
) -> None:
    """ADR 0001's way: the id rides in the partial `_decide()` builds, the compiled
    sequence carries it, and every record of that sequence (its Steps and its
    forced release) has it. A release outside any sequence has none."""
    wire = _Wire()
    compiler = functools.partial(
        compile_movements,
        # A long walk cut at 0.1 s: `right` is still down, so `always_release`
        # releases it at the end of the send, outside the Steps.
        movements=(
            _MovementComponent(MovementTypes.WALK_RIGHT, 300),
            _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
        ),
        handle=HANDLE,
        ign=IGN,
        speed=100.0,
        total_duration=0.1,
        teleport=None,
        always_release=True,
        correlation_id="cid-538",
    )

    async def _run() -> None:
        _patch_focus(mocker, wire)
        await compile_and_send(HANDLE, compiler)

    random.seed(3)
    asyncio.run(_run())
    in_sequence = [r for r in sink.records if r["event_type"] in (KEY_DOWN, KEY_UP)]
    assert {r["payload"]["cause"] for r in in_sequence} == {"step", "release"}
    assert {r["correlation_id"] for r in in_sequence} == {"cid-538"}

    sink.records.clear()
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")
    focused_inputs_module.release_keys(["left"], HANDLE)
    (outside,) = sink.records
    assert outside["correlation_id"] is None


def test_a_compiler_stamps_the_id_its_partial_carries_and_no_step_changes() -> None:
    def _compile(correlation_id: str | None) -> KeyboardInputWrapper:
        random.seed(4)
        structure = compile_movements(
            InputState(),
            movements=PLAN,
            handle=HANDLE,
            ign=IGN,
            speed=100.0,
            total_duration=0.45,
            teleport=None,
            correlation_id=correlation_id,
        )
        assert structure is not None
        return structure

    stamped, bare = _compile("cid-538"), _compile(None)
    assert stamped.correlation_id == "cid-538"
    assert bare.correlation_id is None
    assert (stamped.keys, stamped.events, stamped.delays, stamped.origins) == (
        bare.keys,
        bare.events,
        bare.delays,
        bare.origins,
    )
    assert stamped.truncate(0.1).correlation_id == "cid-538"


# --- off the send path -------------------------------------------------------------


def test_records_are_buffered_and_written_once_the_sender_yields(
    mocker: MockerFixture,
) -> None:
    written = mocker.patch.object(key_times, "emit_event")

    async def _run() -> tuple[int, int, int]:
        key_times.record(
            HANDLE,
            ["left", "space"],
            ["keydown", "keydown"],
            frozenset(),
            "step",
            key_times.stamp(),
        )
        on_the_send_path = written.call_count
        buffered = key_times.pending()
        await asyncio.sleep(0)
        return on_the_send_path, buffered, written.call_count

    on_the_send_path, buffered, after = asyncio.run(_run())
    assert on_the_send_path == 0
    assert buffered == 2
    assert after == 2


def test_a_record_that_cannot_be_written_never_raises_into_the_sender(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    mocker.patch.object(key_times, "emit_event", side_effect=OSError("disk gone"))
    # No running loop: written at once, and the failure is logged, not raised.
    key_times.record(HANDLE, "left", "keyup", frozenset({"left"}), "release", (0, 0))
    assert key_times.pending() == 0
    assert "Could not write a key time" in caplog.text
