"""
Tests for the Held-Keys Ledger and the Main-Process-only input guard.

Nothing here sends real input: `_send_input` is patched out, and the handles are
arbitrary integers (handle 0 resolves to the current thread's keyboard layout, which
is all `input_constructor` needs).
"""

import asyncio
import importlib
import multiprocessing
import threading

import pytest

from botting.controller import get_held_movement_keys
from botting.controller.inputs.focused_inputs import focused_inputs, release_all
from botting.controller.inputs.held_keys_ledger import (
    HeldKeysLedger,
    in_main_process,
    require_main_process,
)

HANDLE = 1234
OTHER_HANDLE = 5678

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


def _guard_in_child(queue: multiprocessing.Queue) -> None:
    """Spawned target: reports whether the guard fires outside Main Process."""
    try:
        require_main_process("focused_inputs")
    except RuntimeError as e:
        queue.put(("raised", str(e)))
    else:
        queue.put(("passed", multiprocessing.current_process().name))


def _guard_in_thread(results: list) -> None:
    """Thread target: the minimap editor's shape - a worker thread of Main Process."""
    try:
        require_main_process("focused_inputs")
    except RuntimeError as e:
        results.append(("raised", str(e)))
    else:
        results.append(("passed", None))


# --- the ledger itself --------------------------------------------------------


def test_keydown_and_keyup_fold_into_one_entry():
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")
    HeldKeysLedger.record_step(HANDLE, "jump", "keydown")
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"left", "jump"})

    HeldKeysLedger.record_step(HANDLE, "left", "keyup")
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"jump"})


def test_simultaneous_keys_in_one_step():
    HeldKeysLedger.record_step(HANDLE, ["left", "up"], ["keydown", "keydown"])
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"left", "up"})

    HeldKeysLedger.record_step(HANDLE, ["left", "up"], ["keyup", "keyup"])
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset()


def test_entries_are_per_handle():
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")
    assert HeldKeysLedger.keys_held(OTHER_HANDLE) == frozenset()


def test_mouse_steps_leave_the_ledger_untouched():
    HeldKeysLedger.record_step(HANDLE, (10, 20), None)
    HeldKeysLedger.record_step(HANDLE, None, "mousedown")
    assert HeldKeysLedger.snapshot() == {}


def test_released_entry_is_dropped_rather_than_left_empty():
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")
    HeldKeysLedger.record_step(HANDLE, "left", "keyup")
    assert HeldKeysLedger.snapshot() == {}


def test_get_held_movement_keys_reads_the_ledger():
    HeldKeysLedger.record_step(HANDLE, ["left", "jump"], ["keydown", "keydown"])
    assert get_held_movement_keys(HANDLE) == ["left"]
    assert get_held_movement_keys(OTHER_HANDLE) == []


def test_sweep_candidates_cover_movement_keys_and_everything_sent():
    HeldKeysLedger.note_sent("space")
    candidates = HeldKeysLedger.sweep_candidates()
    assert {"left", "right", "up", "down", "space"} <= candidates


def test_release_all_clears_the_entry(mocker):
    HeldKeysLedger.record_step(HANDLE, ["left", "jump"], ["keydown", "keydown"])
    release = mocker.patch.object(focused_inputs_module, "release_keys")
    mocker.patch.object(focused_inputs_module, "_physically_held", return_value=set())
    release_all(HANDLE)
    assert sorted(release.call_args.args[0]) == ["jump", "left"]
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset()


def test_release_all_also_releases_keys_the_ledger_missed(mocker):
    release = mocker.patch.object(focused_inputs_module, "release_keys")
    mocker.patch.object(
        focused_inputs_module, "_physically_held", return_value={"ctrl"}
    )
    release_all(HANDLE)
    assert release.call_args.args[0] == ["ctrl"]


# --- the ledger under cancellation --------------------------------------------
# The ledger must describe the Delivered Prefix, not the Input Sequence: a cancelled
# send loop leaves down exactly the keys whose Step made it out.


def test_truncated_send_loop_records_only_delivered_steps(mocker):
    keys = ["left", "right", "up", "down"]
    events = ["keydown"] * 4
    # Step 3 is still waiting out step 2's delay when the task is cancelled.
    delays = [0, 0, 10, 10]

    async def _scenario():
        third_step_sent = asyncio.Event()
        sent = []

        def _fake_send(structure):
            sent.append(structure)
            if len(sent) == 3:
                third_step_sent.set()

        # `mocker` undoes every patch below when the test ends.
        mocker.patch.object(
            focused_inputs_module, "_send_input", side_effect=_fake_send
        )
        mocker.patch.object(
            focused_inputs_module, "activate", new=mocker.AsyncMock(return_value=False)
        )
        release = mocker.patch.object(focused_inputs_module, "release_keys")

        task = asyncio.create_task(
            focused_inputs(
                HANDLE,
                [mocker.Mock()] * 4,
                delays,
                forced_key_releases=keys,
                keys=keys,
                events=events,
            )
        )
        await third_step_sent.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(sent) == 3
        return release

    release = asyncio.run(_scenario())
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"left", "right", "up"})
    # The forced-release block reads the ledger, so it never releases "down".
    assert sorted(release.call_args.args[0]) == ["left", "right", "up"]


# --- the Main-Process-only guard ----------------------------------------------


def test_passes_in_main_process():
    assert in_main_process()
    require_main_process("focused_inputs")  # Must not raise.


def test_passes_from_a_worker_thread_of_main_process():
    results: list = []
    thread = threading.Thread(target=_guard_in_thread, args=(results,))
    thread.start()
    thread.join()
    assert results == [("passed", None)]


def test_raises_in_a_child_process():
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_guard_in_child, args=(queue,))
    process.start()
    process.join(timeout=30)
    outcome, detail = queue.get(timeout=5)
    assert outcome == "raised"
    assert "Main Process" in detail
