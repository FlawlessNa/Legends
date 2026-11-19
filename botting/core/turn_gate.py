"""
The Turn Gate (`CONTEXT.md`): a DecisionMaker takes its turn on the client by
entering it, and the Action it sends leaves it, from Main Process (ADR 0004).
"""

import asyncio
from collections.abc import Callable
from typing import Protocol


class _Lock(Protocol):
    """A Manager Lock, as its proxy is called: or any lock that acts the same."""

    def acquire(self, blocking: bool = True) -> bool: ...

    def release(self) -> None: ...


class TurnGate:
    """
    One decision at a time on the client, for one DecisionMaker: it enters
    before it sends an Action, and the Action's callback, run in Main Process
    once the Action is done, lets the next decision in.

    Over a Manager Lock, because the release runs in Main Process: the gate
    itself never travels, only `releaser`, the lock's own `release`.

    - `try_enter()` takes the gate when it is free, and never waits.
    - `await enter()` waits for it, yielding to the event loop while it waits.
    - `releaser` goes in the Action's `callbacks`, and leaves the gate.
    - `reset()` frees it whatever holds it, for `on_start()`: a run cancelled
      while holding it would otherwise leave it held.
    """

    def __init__(self, lock: _Lock) -> None:
        """
        :param lock: The Manager Lock underneath: `ProxyFactory.instance(owner,
            "Lock")`, made in its DecisionMaker's `setup()`.
        """
        self._lock = lock

    def try_enter(self) -> bool:
        """Take the gate when it is free; whether it was taken. Never waits."""
        return self._lock.acquire(blocking=False)

    async def enter(self) -> None:
        """Wait for the gate and take it, without blocking the event loop."""
        await asyncio.to_thread(self._lock.acquire)

    async def leave(self) -> None:
        """Leave the gate from the Engine, for a decision that sent nothing."""
        await asyncio.to_thread(self._lock.release)

    def leave_now(self) -> None:
        """
        Leave the gate from the Engine without yielding, for a decision that
        sent nothing and must not give the event loop away before it ends
        (`Rotation`'s, which always released its lock so). The proxy call
        blocks the loop for its round trip.
        """
        self._lock.release()

    @property
    def releaser(self) -> Callable[[], None]:
        """What leaves the gate from Main Process: the lock's `release`, for an
        Action's `callbacks`."""
        return self._lock.release

    def reset(self) -> None:
        """Free the gate, held or not."""
        self._lock.acquire(blocking=False)
        self._lock.release()
