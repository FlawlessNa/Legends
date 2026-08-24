"""
Tests for invariant D2 - "after a Preemption, no direction key remains down".

The release lives in the `focused_inputs` send loop rather than in a task
done-callback, so these drive the loop directly and assert on the volley it emits.
Nothing here sends real input: `_send_input` and `release_keys` are patched out, and
the handles are arbitrary integers.
"""

import asyncio
import importlib

import pytest

from botting.controller.inputs.focused_inputs import focused_inputs
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger

HANDLE = 1234

# `botting.controller.inputs` re-exports `focused_inputs` as a name, shadowing the
# submodule of the same name, so the module object has to be fetched explicitly.
focused_inputs_module = importlib.import_module(
    "botting.controller.inputs.focused_inputs"
)


@pytest.fixture(autouse=True)
def reset_ledger():
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


class _SendLoopScenario:
    """
    Runs one Input Sequence through `focused_inputs`, optionally cancelling it once a
    given number of Steps have been delivered.
    """

    def __init__(
        self,
        keys: list,
        events: list,
        delays: list[float],
        forced_key_releases: list[str] = None,
        cancel_after: int = None,
    ) -> None:
        self.keys = keys
        self.events = events
        self.delays = delays
        self.forced_key_releases = forced_key_releases
        self.cancel_after = cancel_after
        self.released: list[str] = []
        self.delivered = 0

    def run(self, mocker) -> "_SendLoopScenario":
        asyncio.run(self._run(mocker))
        return self

    async def _run(self, mocker) -> None:
        reached = asyncio.Event()

        def _fake_send(structure):
            self.delivered += 1
            if self.delivered == self.cancel_after:
                reached.set()

        def _fake_release(keys, hwnd):
            self.released.extend(keys)

        # `mocker` undoes every patch below when the test ends.
        mocker.patch.object(
            focused_inputs_module, "_send_input", side_effect=_fake_send
        )
        mocker.patch.object(
            focused_inputs_module, "activate", new=mocker.AsyncMock(return_value=False)
        )
        mocker.patch.object(
            focused_inputs_module, "release_keys", side_effect=_fake_release
        )

        task = asyncio.create_task(
            focused_inputs(
                HANDLE,
                [mocker.Mock()] * len(self.keys),
                self.delays,
                forced_key_releases=self.forced_key_releases,
                keys=self.keys,
                events=self.events,
            )
        )
        if self.cancel_after is None:
            await task
            return
        await reached.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_cancellation_releases_a_direction_never_declared_for_forced_release(mocker):
    """
    The defect this fixes: a movement Action that declares no forced release for
    its direction key used to leave it down forever once preempted.
    """
    scenario = _SendLoopScenario(
        keys=["right", "jump", "jump"],
        events=["keydown", "keydown", "keyup"],
        delays=[0, 10, 10],
        forced_key_releases=["jump"],
        cancel_after=2,
    ).run(mocker)

    assert sorted(scenario.released) == ["jump", "right"]
    # `release_keys` is patched, so the ledger still shows the Delivered Prefix -
    # two Steps out, the third never sent.
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"right", "jump"})


def test_normal_completion_carries_the_direction_over(mocker):
    """
    A Continuation deliberately keeps walking across the route-cycle boundary, so
    the same key must survive a sequence that ran to its end (C3).
    """
    scenario = _SendLoopScenario(
        keys=["right", "jump", "jump"],
        events=["keydown", "keydown", "keyup"],
        delays=[0, 0, 0],
        forced_key_releases=["jump"],
    ).run(mocker)

    assert scenario.delivered == 3
    assert scenario.released == []
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"right"})


def test_cancellation_releases_a_direction_inherited_from_a_prior_sequence(mocker):
    """
    Preemption can land before this sequence delivers a Step of its own. The key
    left down is then the one the previous Continuation carried over, and D2 still
    has to hold - so the release reads the ledger rather than this sequence.
    """
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")

    scenario = _SendLoopScenario(
        keys=["jump", "jump"],
        events=["keydown", "keyup"],
        delays=[10, 10],
        forced_key_releases=["jump"],
        cancel_after=1,
    ).run(mocker)

    assert sorted(scenario.released) == ["jump", "left"]


def test_every_direction_key_is_released_not_just_left_and_right(mocker):
    """`up` and `down` are direction keys too - a held `up` keeps climbing."""
    scenario = _SendLoopScenario(
        keys=["up", "down", "left", "right"],
        events=["keydown"] * 4,
        delays=[0, 0, 0, 10],
        forced_key_releases=None,
        cancel_after=4,
    ).run(mocker)

    assert sorted(scenario.released) == ["down", "left", "right", "up"]


def test_nothing_is_sent_when_the_ledger_holds_no_direction(mocker):
    scenario = _SendLoopScenario(
        keys=["jump", "jump"],
        events=["keydown", "keyup"],
        delays=[0, 10],
        forced_key_releases=None,
        cancel_after=2,
    ).run(mocker)

    assert scenario.released == []
