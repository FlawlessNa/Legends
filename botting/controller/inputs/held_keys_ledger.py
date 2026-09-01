"""
The Held-Keys Ledger: the authoritative per-handle record of the keys the bot has
pressed and not yet released.

Ownership
---------
Main Process owns the ledger, because Main Process is the sole sender of input
(`SendInput` only ever reaches the foreground window, and only Main Process
arbitrates which client is foreground). Child (Engine) processes therefore see an
empty ledger; the guard below turns "all keyboard input goes through Main Process"
from a convention into a crash. Standalone tooling - the minimap editor - is its
own Main Process, so it owns a ledger of its own and is unaffected.

Truth
-----
The ledger is written at Step granularity by the `focused_inputs` send loop, right
after each Step reaches the game, so it stays exact when cancellation truncates a
Delivered Prefix mid-flight. It is reconciled against the physical keyboard
(`GetAsyncKeyState`) at exactly two points - a session-start sweep and the sweep
inside `release_all` at every focus switch. Everywhere else it is read, not
queried.

At most one handle's entry is ever non-empty - the current foreground - because
`activate()` releases every key before switching focus. `_check_single_holder`
logs a defect if that invariant is ever broken.

Typematic ownership
-------------------
Beside the held set, the ledger carries which key currently owns typematic - the one
Windows repeats while it stays down. A keydown claims ownership, a later keydown takes
it, and any keyup ends repetition outright rather than handing it back to a key still
held. `record_step` already witnesses every delivered Step, in order, at the moment it
reaches the game, so it is the only place that can observe this.

Ownership is *not* recoverable from `GetAsyncKeyState`, which reports down/up and knows
nothing about repetition. Neither reconciliation point can restore it, so "nobody owns"
is the representable default rather than a separately modelled "unknown". The errors are
not symmetric: emitting repeats with no owner is the defect **A7 Typematic Legality**
names, while emitting no repeats is always physically producible.
"""

import logging
import multiprocessing
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

logger = logging.getLogger(__name__)

MAIN_PROCESS_NAME = "MainProcess"

# Movement keys are always reconciliation candidates, even before this process has
# sent any of them: they are the ones a previous Session may have left latched.
_ALWAYS_SWEPT = frozenset({"left", "right", "up", "down"})


@dataclass(frozen=True)
class InputState:
    """
    The keyboard state an Input Sequence is compiled against: what is down, and which
    key may legally repeat while it stays down.

    One value object rather than two parallel parameters, because the two halves answer
    one question and a caller reading only the first is exactly the defect issue #97
    was. `held_keys` of `{right}` is equally consistent with "right was just pressed and
    owns typematic" and "right is a Continuation carry whose ownership a teleport took
    and dropped", so the held set alone cannot say which keydowns are legal repeats.

    `owner_elapsed` is data, not a clock: the ledger stamps the owning keydown and
    whoever reads the ledger computes the elapsed time at dispatch. A sequence that
    presses `right` in its final 100ms hands the next one an owner whose typematic delay
    is already 100ms spent. Passing it as data keeps compilation a pure function over
    plain data, so it still pickles into an ActionRequest and the offline lab compiles
    identically (issue #30).

    "Nobody owns" is `typematic_owner is None`, and `owner_elapsed` is 0.0 and
    meaningless there.
    """

    held_keys: frozenset[str] = frozenset()
    typematic_owner: str | None = None
    owner_elapsed: float = 0.0


def in_main_process() -> bool:
    """
    :return: Whether the calling process is the one that owns the Held-Keys Ledger.
    """
    return multiprocessing.current_process().name == MAIN_PROCESS_NAME


def require_main_process(func_name: str) -> None:
    """
    Guard for the input-sending functions. Keyboard input reaches only the foreground
    window, which Main Process alone arbitrates, so sending from anywhere else is a
    defect rather than a degraded mode.
    :param func_name: Name of the guarded function, for the error message.
    :return: None
    :raises RuntimeError: When called outside Main Process.
    """
    if not in_main_process():
        raise RuntimeError(
            f"{func_name}() was called from process "
            f"{multiprocessing.current_process().name!r}. All keyboard and mouse "
            f"input must be sent from Main Process - send an ActionRequest instead."
        )


class HeldKeysLedger:
    """
    Per-handle record of the keys sent and not yet released. See module docstring.
    All state is class-level: there is one ledger per process, and only the Main
    Process one is authoritative.
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _held: ClassVar[dict[int, set[str]]] = {}
    # Per handle, the key that owns typematic and the `time.monotonic()` stamp of the
    # keydown that claimed it. Absent means nobody owns.
    _owner: ClassVar[dict[int, tuple[str, float]]] = {}
    _sent_at_least_once: ClassVar[set[str]] = set()
    _warned_foreign_read = False

    @classmethod
    def keys_held(cls, handle: int) -> frozenset[str]:
        """
        :param handle: Handle to the client window.
        :return: The keys currently held down for that client.
        """
        cls._warn_if_foreign_read()
        with cls._lock:
            return frozenset(cls._held.get(handle, ()))

    @classmethod
    def record_step(
        cls,
        handle: int,
        keys: str | Sequence[object] | None,
        events: str | Sequence[object] | None,
    ) -> None:
        """
        Applies one delivered Step to the ledger. Mouse Steps (non-string keys) and
        events other than keydown/keyup leave it untouched.

        Typematic ownership moves with the same walk, in Step order: a keydown claims
        it, so the last keydown of a simultaneous batch owns, and any keyup drops it
        outright. The stamp is the moment this Step reached the game, taken once - the
        whole batch is delivered by a single `SendInput`.
        :param handle: Handle to the client window the Step was sent to.
        :param keys: The key or keys sent simultaneously at that Step. A mouse Step
            carries coordinates rather than key names, hence the widest element type.
        :param events: The matching event or events.
        :return: None
        """
        pairs: list[tuple[object, object]]
        if isinstance(keys, str) and isinstance(events, str):
            pairs = [(keys, events)]
        elif isinstance(keys, (list, tuple)) and isinstance(events, (list, tuple)):
            pairs = list(zip(keys, events))
        else:
            return

        now = time.monotonic()
        with cls._lock:
            entry = cls._held.setdefault(handle, set())
            for key, event in pairs:
                if not isinstance(key, str):
                    continue
                cls._sent_at_least_once.add(key)
                if event == "keydown":
                    entry.add(key)
                    cls._owner[handle] = (key, now)
                elif event == "keyup":
                    entry.discard(key)
                    cls._owner.pop(handle, None)
            if not entry:
                cls._held.pop(handle, None)
        cls._check_single_holder(handle)

    @classmethod
    def input_state(cls, handle: int) -> InputState:
        """
        The full start state for a compile: every key held for that client, the key that
        owns typematic, and how long it has owned.

        `owner_elapsed` is computed here, at the moment of the read, which is what keeps
        the clock out of compilation - see `InputState`.
        :param handle: Handle to the client window.
        :return: The keyboard state to compile that client's next sequence against.
        """
        cls._warn_if_foreign_read()
        with cls._lock:
            held = frozenset(cls._held.get(handle, ()))
            owner = cls._owner.get(handle)
        if owner is None:
            return InputState(held_keys=held)
        key, stamp = owner
        return InputState(
            held_keys=held,
            typematic_owner=key,
            owner_elapsed=max(0.0, time.monotonic() - stamp),
        )

    @classmethod
    def note_sent(cls, key: object) -> None:
        """
        Widens the reconciliation candidate set. Called for every key handed to
        `input_constructor`, including those built for a sequence that is never sent.
        :param key: The key that was compiled into an input structure. Mouse
            coordinates reach this too, and are ignored.
        :return: None
        """
        if isinstance(key, str):
            with cls._lock:
                cls._sent_at_least_once.add(key)

    @classmethod
    def sweep_candidates(cls) -> frozenset[str]:
        """
        :return: The keys a reconciliation sweep should query `GetAsyncKeyState` for -
        every key this process has ever compiled, plus the movement keys.
        """
        with cls._lock:
            return frozenset(cls._sent_at_least_once | _ALWAYS_SWEPT)

    @classmethod
    def clear(cls, handle: int) -> None:
        """
        Drops a client's entry, asserting that nothing of its is held any more. Called
        by `release_all` once the releases have been sent. Nothing held means nothing
        owns typematic, so the owner goes with it.
        :param handle: Handle to the client window.
        :return: None
        """
        with cls._lock:
            cls._held.pop(handle, None)
            cls._owner.pop(handle, None)

    @classmethod
    def reset(cls) -> None:
        """
        Empties the whole ledger, candidate set included. Only the session-start sweep
        should need this: nothing has been sent yet, so the movement keys are the only
        thing worth reconciling.
        :return: None
        """
        with cls._lock:
            cls._held.clear()
            cls._owner.clear()
            cls._sent_at_least_once.clear()

    @classmethod
    def snapshot(cls) -> dict[int, frozenset[str]]:
        """
        :return: A copy of every non-empty entry, for logging and tests.
        """
        with cls._lock:
            return {handle: frozenset(keys) for handle, keys in cls._held.items()}

    @classmethod
    def _check_single_holder(cls, handle: int) -> None:
        """
        Logs a defect when more than one client holds keys, which the focus-switch
        release makes impossible.
        """
        with cls._lock:
            others = {h: set(k) for h, k in cls._held.items() if h != handle and k}
        if others:
            logger.error(
                "Held-Keys Ledger invariant broken: %s is not the only client holding "
                "keys. Others: %s",
                handle,
                others,
            )

    @classmethod
    def _warn_if_foreign_read(cls) -> None:
        """
        A read outside Main Process always answers "nothing held", which is a plausible
        but unverified answer. Say so once per process rather than on every read.
        """
        if not cls._warned_foreign_read and not in_main_process():
            cls._warned_foreign_read = True
            logger.warning(
                "Held-Keys Ledger read from process %r, which owns no ledger. It will "
                "report no keys held.",
                multiprocessing.current_process().name,
            )
