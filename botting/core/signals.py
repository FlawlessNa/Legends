"""
Signals: announcing that something happened, within one Bot.

A **Signal** (`Signal[T]`) names one kind of announcement and the type of its
payload. A DecisionMaker or a Provider declares the Signals it `announces`; a
DecisionMaker declares the Signals it `awaits`. Announcing wakes every waiter, so
a DecisionMaker waits for what it needs instead of polling for it.

Everything is in-process asyncio, on the Bot's event loop: no Manager object, no
thread. A Signal is not a Telemetry Record and is never sent to Main Process.

ADR 0004 records the decisions this module implements; `docs/agents/decision-makers.md`
is the guide to writing against it.
"""

import asyncio
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, NamedTuple

from .errors import StartupRefused

if TYPE_CHECKING:
    from .data_keys import Provider
    from .decision_maker import DecisionMaker


class SignalNotDeclared(Exception):
    """
    A DecisionMaker or Provider announced a Signal its `announces` does not
    declare, waited for one its `awaits` does not, or asked for the last of one
    in neither.
    """


class Signal[T]:
    """
    The name and payload type of one kind of announcement::

        MOB_KILLED: Signal[int] = Signal("mob_killed")

    Compared by identity, so a Signal is defined once, in the module of whoever
    announces it, and imported by whoever awaits it.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"Signal({self.name!r})"


class Announcement[T](NamedTuple):
    """The latest announcement of a Signal."""

    payload: T
    #: When it was announced, on the Bot's clock (the one `BotData` measures its
    #: thresholds on).
    at: float


class SignalBoard:
    """
    The announcements of one Bot: the latest of each Signal, and who waits for the
    next. Built by `Bot.start`; DecisionMakers and Providers reach it through
    their own `announce`, `wait_for` and `last`.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._latest: dict[Signal[Any], Announcement[Any]] = {}
        self._waiters: dict[Signal[Any], list[asyncio.Future[Any]]] = {}

    def announce[T](self, signal: Signal[T], payload: T, *, by: object) -> None:
        """
        Record `payload` as the latest of `signal` and wake every waiter with it.
        :raises SignalNotDeclared: `signal` is not in `by`'s class's `announces`.
        """
        if signal not in _declared(by, "announces"):
            raise SignalNotDeclared(
                f"{by} announced {signal.name!r}, which {type(by).__name__}."
                "announces does not declare."
            )
        self._latest[signal] = Announcement(payload, self._clock())
        for waiter in self._waiters.pop(signal, []):
            if not waiter.done():
                waiter.set_result(payload)

    async def wait_for[T](self, signal: Signal[T], *, by: object) -> T:
        """
        The payload of the next announcement of `signal` after this call: an
        announcement already made does not count.
        :raises SignalNotDeclared: `signal` is not in `by`'s class's `awaits`.
        """
        if signal not in _declared(by, "awaits"):
            raise SignalNotDeclared(
                f"{by} waited for {signal.name!r}, which {type(by).__name__}."
                "awaits does not declare."
            )
        waiter: asyncio.Future[T] = asyncio.get_running_loop().create_future()
        waiters = self._waiters.setdefault(signal, [])
        waiters.append(waiter)
        try:
            return await waiter
        finally:
            # A cancelled wait must not stay on the board.
            if waiter in waiters:
                waiters.remove(waiter)

    def last[T](self, signal: Signal[T], *, by: object) -> Announcement[T] | None:
        """
        The latest announcement of `signal`, or None when it has not been
        announced yet.
        :raises SignalNotDeclared: `signal` is in neither `announces` nor `awaits`
            of `by`'s class.
        """
        if signal not in (*_declared(by, "announces"), *_declared(by, "awaits")):
            raise SignalNotDeclared(
                f"{by} asked for the last {signal.name!r}, which neither "
                f"{type(by).__name__}.announces nor .awaits declares."
            )
        return self._latest.get(signal)


def _declared(owner: object, declaration: str) -> tuple[Signal[Any], ...]:
    return getattr(type(owner), declaration, ())


def check_signals(
    decision_makers: Iterable[type[DecisionMaker]],
    providers: Iterable[type[Provider]],
) -> None:
    """
    Refuse a Bot where a DecisionMaker awaits a Signal that no DecisionMaker or
    Provider of the Bot announces: it would wait forever. Runs at assembly, from
    the class-level declarations alone.
    :raises StartupRefused: naming the Signal and the DecisionMaker awaiting it.
    """
    decision_makers = list(decision_makers)
    announced = {
        signal for cls in (*decision_makers, *providers) for signal in cls.announces
    }
    for cls in decision_makers:
        for signal in cls.awaits:
            if signal not in announced:
                raise StartupRefused(
                    f"{cls.__name__} awaits {signal.name!r}, which nothing in this "
                    "Bot announces. Add the DecisionMaker or Provider that "
                    "announces it, or stop awaiting it."
                )
