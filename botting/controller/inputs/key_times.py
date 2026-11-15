"""
Key times: when each key went down and up at a client, kept as Telemetry Records.

The Held-Keys Ledger (ADR 0002) knows which keys are down now and keeps no
history. This module keeps the history: one ``key.down`` or ``key.up`` record
per key transition, with the moment the ``SendInput`` that carried it returned
(#538). It records; it decides nothing, and it changes no key, no delay and no
order of what is sent.

**What counts as a transition.** A keydown for a key the ledger did not hold
is a ``key.down``. A keydown for a key already down is a typematic repeat and
is not recorded: a walk repeats its key every ~33 ms, and recording repeats
would multiply the volume by about 30 for nothing a report reads. Every keyup
sent is a ``key.up``, with ``held`` saying whether the ledger had the key
down: a keyup for a key it did not hold is a straggler that ``release_all``
found down on the physical keyboard, or a phantom release, either worth seeing.

**Two times, one moment.** ``t`` is ``time.monotonic()``, the clock frames are
captured on (`botting.screen`, ``Frame.captured_at``, a Reading's
``frame_time``), so a key time lines up with a position read with no offset.
``wall`` is ``time.time()`` at the same moment, for lining up with the
envelope timestamps of other records. The envelope's own timestamp is when
the record was written, which is later (below).

**Off the send path.** The send loop stamps the times and appends to a deque;
nothing on it formats, encodes or writes. The records are written by
`flush`, scheduled with ``loop.call_soon`` so it runs while the send loop
sleeps out its Step's delay, never awaited by it. With no running loop (a
release at Session start or end) the flush runs at once. `SessionManager`
flushes before ``session.ended`` so a record still buffered is not lost.
A record that cannot be built or written is logged, never dropped silently,
and never raises into the send loop: telemetry may not raise inside what it
observes (ADR 0001).

**Correlation ID.** A key belongs to the Action whose task sent it.
`AsyncTaskManager` binds each task it creates to its request's Correlation ID
(`bind`), and `record` looks up the running task. Procedures still take no
``correlation_id`` parameter (ADR 0001). A key sent outside any scheduled task
(the Session-start sweep, the release at the Session's end) carries ``None``;
a ``release_all`` on a focus switch carries the incoming Action's id, since
that Action's task sends it.

Main Process only, like everything that sends input; the module itself sends
nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time
import weakref
from collections import deque
from collections.abc import Sequence
from typing import Any, cast

from botting.telemetry import emit_event
from botting.telemetry_events import (
    KEY_DOWN,
    KEY_UP,
    KeyCause,
    KeyPayload,
    KeyUpPayload,
)

logger = logging.getLogger(__name__)

#: Records built on the send path and not yet written: (Correlation ID, Event
#: Type, payload). A deque, so appending on the send path and draining in
#: `flush` need no lock between them.
_pending: deque[tuple[str | None, str, KeyPayload | KeyUpPayload]] = deque()

#: Each scheduled task's Correlation ID. Weak, so a finished task leaves no entry.
_bound: weakref.WeakKeyDictionary[asyncio.Task[Any], str | None] = (
    weakref.WeakKeyDictionary()
)


def bind(task: asyncio.Task[Any], correlation_id: str | None) -> None:
    """
    Name the Correlation ID every key `task` sends is recorded with. Called by
    `AsyncTaskManager` on the line after it creates the task, before it runs.
    :param task: The task running an `ActionRequest`'s procedure.
    :param correlation_id: The request's Correlation ID, possibly ``None``.
    """
    _bound[task] = correlation_id


def stamp() -> tuple[float, float]:
    """
    :return: ``(time.monotonic(), time.time())`` now: the two clocks a key time
        is given in. Taken by the caller right after ``SendInput`` returns.
    """
    return time.monotonic(), time.time()


def record(
    handle: int,
    keys: object,
    events: object,
    held_before: frozenset[str],
    cause: KeyCause,
    sent_at: tuple[float, float],
    origin: int | None = None,
) -> None:
    """
    Buffer one record per key transition in a delivered Step. Never raises.

    :param handle: The client window the Step was sent to.
    :param keys: The key, or keys sent at once, of the Step. A mouse Step's
        coordinates and a delay-only Step's empty list record nothing.
    :param events: The matching event or events.
    :param held_before: The keys the Held-Keys Ledger held for `handle` before
        the Step was recorded to it.
    :param cause: ``step`` for a Step of an Input Sequence, ``release`` for a
        release outside one (`release_keys`, which `release_all` and the send
        loop's forced and cancel releases go through).
    :param sent_at: `stamp`, taken when ``SendInput`` returned.
    :param origin: The Movement Plan component that produced the Step (its
        Provenance), ``None`` when the Step has none to give.
    """
    try:
        pairs = _pairs(keys, events)
        if not pairs:
            return
        correlation_id = _current_correlation_id()
        mono, wall = sent_at
        held = set(held_before)
        for key, event in pairs:
            if event == "keydown":
                if key in held:
                    continue  # a typematic repeat, not a transition
                held.add(key)
                down: KeyPayload = {
                    "key": key,
                    "handle": int(handle),
                    "t": round(mono, 6),
                    "wall": round(wall, 6),
                    "cause": cause,
                    "origin": origin,
                }
                _pending.append((correlation_id, KEY_DOWN, down))
            elif event == "keyup":
                up: KeyUpPayload = {
                    "key": key,
                    "handle": int(handle),
                    "t": round(mono, 6),
                    "wall": round(wall, 6),
                    "cause": cause,
                    "origin": origin,
                    "held": key in held,
                }
                held.discard(key)
                _pending.append((correlation_id, KEY_UP, up))
        _schedule_flush()
    except Exception:
        logger.exception("Could not record the key times of %r %r.", keys, events)


def flush() -> None:
    """
    Write every buffered record. Never raises; a record that fails is logged.
    Safe to call at any time and from any number of places: it drains what is
    there and returns.
    """
    while _pending:
        try:
            correlation_id, event_type, payload = _pending.popleft()
        except IndexError:  # drained by another caller in between
            return
        try:
            emit_event(correlation_id, event_type, payload, logger_name=logger.name)
        except Exception:
            logger.exception("Could not write a key time: %s %r", event_type, payload)


def pending() -> int:
    """:return: How many records are buffered and not yet written (for tests)."""
    return len(_pending)


def _schedule_flush() -> None:
    """Write the buffer after the send loop yields, or now with no running loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        flush()
        return
    loop.call_soon(flush)


def _current_correlation_id() -> str | None:
    try:
        task = asyncio.current_task()
    except RuntimeError:  # no running loop
        return None
    return None if task is None else _bound.get(task)


def _pairs(keys: object, events: object) -> list[tuple[str, str]]:
    """The Step's (key, event) pairs, keyboard ones only."""
    if isinstance(keys, str) and isinstance(events, str):
        return [(keys, events)]
    if isinstance(keys, (list, tuple)) and isinstance(events, (list, tuple)):
        pairs: list[tuple[str, str]] = []
        steps = cast("Sequence[object]", keys)
        kinds = cast("Sequence[object]", events)
        for key, event in zip(steps, kinds):
            if isinstance(key, str) and isinstance(event, str):
                pairs.append((key, event))
        return pairs
    return []
