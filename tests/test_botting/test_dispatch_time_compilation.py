"""
Tests for dispatch-time movement compilation (ADR 0002).

DecisionMakers no longer ship compiled Input Sequences: they ship the plan, and Main
Process compiles it when the Action is actually dispatched, against the Held-Keys
Ledger, from inside the focus-lock critical section. These tests pin that ordering -
compiling before the lock would re-open the compile->dispatch race one layer down -
and the picklability that lets a plan cross the pipe at all.

Nothing here sends real input: `_send_input` and `release_keys` are patched out and
the handles are arbitrary integers.
"""

import asyncio
import functools
import importlib
import pickle
from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from botting.controller.inputs.focused_inputs import (
    KeyboardInputWrapper,
    compile_and_send,
)
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger, InputState
from botting.controller.inputs.shared_resources import SharedResources
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 4321
IGN = "TestChar"

# `botting.controller.inputs` re-exports `focused_inputs` as a name, shadowing the
# submodule of the same name, so the module object has to be fetched explicitly.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)


@pytest.fixture(autouse=True)
def reset_ledger() -> Iterator[None]:
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


def _sequence(*keys: str, delay: float = 0.0) -> KeyboardInputWrapper:
    """A trivial Input Sequence holding `keys` down, compiled against nothing held."""
    return KeyboardInputWrapper(
        HANDLE,
        list(keys),
        ["keydown"] * len(keys),
        [delay] * len(keys),
        initial_state=InputState(),
    )


class _DispatchScenario:
    """
    Drives one `compile_and_send` call, recording what the compiler was handed and in
    what order things happened, optionally cancelling once N Steps are delivered.
    """

    def __init__(
        self,
        compiler_result: KeyboardInputWrapper | None,
        cancel_after: int | None = None,
    ) -> None:
        self._result = compiler_result
        self.cancel_after = cancel_after
        self.seen_state: InputState | None = None
        self.locked_during_compile = None
        self.trace: list[str] = []
        self.released: list[str] = []
        self.delivered = 0
        self.sent_count = None
        self.lock_released = None

    def _compile(self, initial_state: InputState | None) -> KeyboardInputWrapper | None:
        self.seen_state = initial_state
        self.locked_during_compile = SharedResources.focus_lock.locked()
        self.trace.append("compile")
        return self._result

    def run(self, mocker: MockerFixture) -> _DispatchScenario:
        asyncio.run(self._run(mocker))
        return self

    async def _run(self, mocker: MockerFixture) -> None:
        reached = asyncio.Event()

        async def _fake_activate(hwnd: int) -> bool:
            self.trace.append("activate")
            await SharedResources.focus_lock.acquire()
            return True

        def _fake_send(structure: tuple) -> None:
            self.delivered += 1
            self.trace.append("send")
            if self.delivered == self.cancel_after:
                reached.set()

        def _fake_release(keys: list[str], hwnd: int) -> None:
            self.released.extend(keys)

        # A lock created inside this test's own event loop: the class-level one is
        # shared process-wide and would carry state between tests. `mocker` undoes
        # every patch below when the test ends.
        mocker.patch.object(SharedResources, "focus_lock", asyncio.Lock())
        mocker.patch.object(
            focused_inputs_module, "activate", side_effect=_fake_activate
        )
        mocker.patch.object(
            focused_inputs_module, "_send_input", side_effect=_fake_send
        )
        mocker.patch.object(
            focused_inputs_module, "release_keys", side_effect=_fake_release
        )

        task = asyncio.create_task(compile_and_send(HANDLE, self._compile))
        if self.cancel_after is None:
            self.sent_count = await task
        else:
            await reached.wait()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.lock_released = not SharedResources.focus_lock.locked()


# --- dispatch-time compilation ------------------------------------------------


def test_compiler_reads_the_ledger_entry_for_its_own_handle(
    mocker: MockerFixture,
) -> None:
    """
    The whole point of moving the compile: the held state it sees is this
    client's, at dispatch - not a system-wide `GetAsyncKeyState` sampled in some
    DecisionMaker's process at decide time.
    """
    HeldKeysLedger.record_step(HANDLE, ["right", "a"], ["keydown", "keydown"])

    scenario = _DispatchScenario(_sequence("up")).run(mocker)

    # Only movement keys: that is what the seam's held set describes. The typematic
    # owner is deliberately not narrowed - `a` was the last keydown, so `a` owns.
    seen = scenario.seen_state
    assert seen is not None
    assert seen.held_keys == frozenset({"right"})
    assert isinstance(seen.held_keys, frozenset)
    assert seen.typematic_owner == "a"


def test_compile_happens_inside_the_focus_lock_critical_section(
    mocker: MockerFixture,
) -> None:
    """
    Load-bearing: compiling before the lock is taken re-opens the same
    compile->dispatch race the ledger was built to close (ADR 0002).
    """
    scenario = _DispatchScenario(_sequence("right")).run(mocker)

    assert scenario.locked_during_compile
    assert scenario.trace[:2] == ["activate", "compile"]
    assert scenario.trace[2] == "send"
    assert scenario.lock_released


def test_compiled_steps_are_streamed_and_recorded_in_the_ledger(
    mocker: MockerFixture,
) -> None:
    """
    The dispatch path feeds the same send loop, so the ledger still describes what
    was delivered.
    """
    scenario = _DispatchScenario(_sequence("right")).run(mocker)

    # One Step: the `right` keydown itself. Nothing is held, so construction inserts
    # no opposite release - A6 forbids the phantom `left` keyup this used to carry
    # (issue #28).
    assert scenario.delivered == 1
    assert scenario.sent_count == 1
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"right"})


def test_a_plan_that_compiles_to_nothing_sends_nothing(mocker: MockerFixture) -> None:
    """
    `compile_movements` returns None for a plan with no Steps in it. The old live
    path could only discover that by compiling in the Engine process first.
    """
    scenario = _DispatchScenario(None).run(mocker)

    assert scenario.delivered == 0
    assert scenario.sent_count == 0
    assert scenario.trace == ["activate", "compile"]
    assert scenario.lock_released


def test_cancellation_of_a_dispatch_compiled_send_still_releases_directions(
    mocker: MockerFixture,
) -> None:
    """
    Moving the compile inside `focused_inputs` puts it under the same cancellation
    handling as the send loop, so D2 keeps holding on the new path.
    """
    scenario = _DispatchScenario(
        _sequence("right", "up", delay=10.0), cancel_after=2
    ).run(mocker)

    assert "right" in scenario.released
    assert scenario.lock_released


# --- the compile function itself ----------------------------------------------
# Now module-level and keyed only on plain data.

PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 5),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
)


def _compile(always_release: bool = False) -> KeyboardInputWrapper:
    """Every case here compiles to something; a `None` would be the test's own bug."""
    wrapper = compile_movements(
        InputState(),
        movements=PLAN,
        handle=HANDLE,
        ign=IGN,
        speed=1.0,
        total_duration=0.3,
        always_release=always_release,
    )
    assert wrapper is not None
    return wrapper


def test_a_truncated_sequence_carries_its_direction_key_by_default() -> None:
    """
    The Continuation case: the next route cycle picks the walk back up, so the key
    is deliberately left down.
    """
    structure = _compile()

    assert structure.keys_held == {"right"}
    assert "right" not in structure.forced_key_releases


def test_always_release_declares_every_key_still_held() -> None:
    """
    `always_release` is the flag form of what `_always_release_keys_on_actions`
    used to do by post-processing a compiled Action in the Engine process. The
    inventory trip needs it: nothing follows to release the key.
    """
    structure = _compile(always_release=True)

    assert "right" in structure.forced_key_releases


def test_the_compile_inputs_survive_a_pickle_round_trip() -> None:
    """
    The plan travels to Main Process inside an ActionRequest, over a
    `multiprocessing.Pipe`. A `MovementHandler` could not make that trip - its
    per-instance `lru_cache` wrappers are unpicklable - which is why the compile
    is a module-level function over plain data.
    """
    compiler = functools.partial(
        compile_movements,
        movements=PLAN,
        handle=HANDLE,
        ign=IGN,
        speed=1.0,
        total_duration=0.3,
        teleport=None,
        always_release=True,
    )

    revived = pickle.loads(pickle.dumps(compiler))

    from_revived = revived(InputState())
    from_original = compiler(InputState())
    assert from_revived is not None
    assert from_original is not None
    assert from_revived.keys == from_original.keys
