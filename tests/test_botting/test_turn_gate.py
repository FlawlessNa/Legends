"""
The Turn Gate (ADR 0004), over a fake of the Manager Lock it wraps: a
thread's lock, which a Manager Lock's proxy acts like. Main Process's callback
is `releaser`, called from another thread, as the Task Manager calls it.
"""

import asyncio
import threading

from botting.core import TurnGate


class _Lock:
    """Stands in for a Manager Lock: a thread's lock, and who called it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self, blocking: bool = True) -> bool:
        return self._lock.acquire(blocking)

    def release(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()


def test_try_enter_takes_a_free_gate_and_fails_while_it_is_held() -> None:
    lock = _Lock()
    gate = TurnGate(lock)

    assert gate.try_enter() is True
    assert gate.try_enter() is False
    assert lock.locked()


def test_enter_waits_for_the_gate_without_blocking_the_event_loop() -> None:
    lock = _Lock()
    gate = TurnGate(lock)
    assert gate.try_enter()

    async def scenario() -> None:
        entering = asyncio.create_task(gate.enter())
        ticks = 0
        for _ in range(20):
            await asyncio.sleep(0.005)
            ticks += 1
        assert ticks == 20, "the loop ran while enter() waited"
        assert not entering.done()

        # Main Process's callback, on its own thread.
        threading.Thread(target=gate.releaser).start()
        await asyncio.wait_for(entering, timeout=5)

    asyncio.run(scenario())
    assert lock.locked(), "enter() took the gate once it was free"


def test_releaser_frees_the_gate_and_is_the_locks_own_release() -> None:
    lock = _Lock()
    gate = TurnGate(lock)
    assert gate.try_enter()

    gate.releaser()

    assert not lock.locked()
    assert gate.try_enter() is True
    # What travels to Main Process in an Action's callbacks: the lock's own
    # method, so the release runs on the Manager's lock, not on a copy.
    assert gate.releaser == lock.release


def test_leave_frees_the_gate_from_the_engine() -> None:
    lock = _Lock()
    gate = TurnGate(lock)
    assert gate.try_enter()

    asyncio.run(gate.leave())

    assert not lock.locked()


def test_reset_frees_a_held_gate_and_leaves_a_free_one_free() -> None:
    lock = _Lock()
    gate = TurnGate(lock)

    gate.reset()
    assert not lock.locked()

    assert gate.try_enter()
    gate.reset()
    assert not lock.locked()
