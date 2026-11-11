"""
The Supervisor: the one owner of every DecisionMaker's decision loops in a Bot.

It starts each DecisionMaker's loops once the Bot is assembled, and it is the only
thing that cancels or restarts one. Loops stop and start again because of Pauses:
a DecisionMaker that goes from no Pause to one has its loops cancelled, and one
whose last Pause is released has `on_start()` called and its loops started again.
The DecisionMaker object, and its state, are kept throughout.

Everything here runs in the Engine's event loop. There is no thread, no
`asyncio.to_thread` and no Manager object: a Pause is a value in a list, and the
loops it stops are tasks of the Bot's own TaskGroup.

ADR 0004 records the decisions this module implements.
"""

import asyncio
import contextlib
import importlib
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from botting.telemetry import emit_event
from botting.telemetry_events import DECISION_PAUSED, DECISION_RESUMED, PausePayload

from .errors import StartupRefused

if TYPE_CHECKING:
    from .decision_maker import DecisionMaker

logger = logging.getLogger(__name__)

#: The holder of a Pause the user asked for, through Discord or through
#: `DecisionMaker.pause_for_user`.
USER = "user"


class PauseKind(Enum):
    """How a Pause ends."""

    #: Taken by `DecisionMaker.pause`: ends when its `async with` block exits.
    SCOPED = "scoped"
    #: Held by the user: ends at Discord `RESUME`, and nothing else.
    USER = "user"
    #: Taken by the legacy `_disable_decision_makers`: ends at the matching
    #: `_enable_decision_makers` or at Discord `RESUME`.
    SHIM = "shim"


@dataclass(frozen=True)
class PauseTarget:
    """
    What a Pause pauses: one DecisionMaker class, in one Bot.

    The Bot is part of the address so that a later design can pause a
    DecisionMaker of another bot without changing a call site. Nothing does yet:
    a Supervisor only ever accepts targets in its own Bot.
    """

    bot: str
    cls: type[DecisionMaker]


@dataclass(eq=False)
class Pause:
    """
    One hold on one DecisionMaker. Compared by identity: two holders pausing the
    same target for the same reason still hold two Pauses.
    """

    target: PauseTarget
    #: `repr` of the holding DecisionMaker, or `USER`.
    holder: str
    reason: str
    kind: PauseKind

    def payload(self) -> PausePayload:
        """The `decision.paused` / `decision.resumed` payload for this Pause."""
        return {
            "target": self.target.cls.__name__,
            "holder": self.holder,
            "reason": self.reason,
        }


@dataclass(eq=False)
class _Slot:
    """What the Supervisor knows about one DecisionMaker."""

    dm: DecisionMaker
    pauses: list[Pause] = field(default_factory=list)
    #: Counts the times `pauses` went from empty to not. A loop that ends while
    #: this is unchanged ended by itself rather than by a Pause.
    generation: int = 0
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    #: Set, then replaced, on every change to `pauses`: what `_until` waits on.
    changed: asyncio.Event = field(default_factory=asyncio.Event)


def resolve_pauses(
    classes: Iterable[type[DecisionMaker]],
) -> dict[type[DecisionMaker], frozenset[type[DecisionMaker]]]:
    """
    Resolve each class's `pauses` declaration into the classes it names.

    An entry is a DecisionMaker class, or its dotted path where naming the class
    would create an import cycle. Runs before any DecisionMaker is built.
    :raises StartupRefused: an entry resolves to nothing, or to something that is
        not a DecisionMaker class.
    """
    # Imported here: decision_maker imports this module.
    from .decision_maker import DecisionMaker

    resolved: dict[type[DecisionMaker], frozenset[type[DecisionMaker]]] = {}
    for cls in classes:
        targets: set[type[DecisionMaker]] = set()
        for entry in cls.pauses:
            target = _resolve(entry) if isinstance(entry, str) else entry
            if not (isinstance(target, type) and issubclass(target, DecisionMaker)):
                raise StartupRefused(
                    f"{cls.__name__} declares pauses entry {entry!r}, which is not "
                    "a DecisionMaker class: name the class, or its dotted path "
                    "('package.module.ClassName')."
                )
            targets.add(target)
        resolved[cls] = frozenset(targets)
    return resolved


def _resolve(path: str) -> object:
    """The object a dotted path names, or None when it names nothing."""
    module_name, _, name = path.rpartition(".")
    if not module_name:
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    return getattr(module, name, None)


class Supervisor:
    """
    Runs every DecisionMaker's loops for one Bot, and holds the Bot's Pauses.

    Built by `Bot.start` once its DecisionMakers are, and attached to each of
    them: a DecisionMaker reaches it through `pause`, `pause_for_user` and the
    legacy shim, never directly.
    """

    def __init__(
        self,
        bot: str,
        decision_makers: Sequence[DecisionMaker],
        declared_pauses: Mapping[type[DecisionMaker], frozenset[type[DecisionMaker]]],
    ) -> None:
        """
        :param bot: The Bot's ign: the only Bot this Supervisor's Pauses address.
        :param decision_makers: The Bot's DecisionMakers, built.
        :param declared_pauses: Each class's resolved `pauses`, from
            `resolve_pauses`.
        """
        self.bot = bot
        self._slots = [_Slot(dm) for dm in decision_makers]
        self._declared = dict(declared_pauses)
        self._tg: asyncio.TaskGroup | None = None
        for dm in decision_makers:
            dm._supervisor = self  # pyright: ignore[reportPrivateUsage] - its owner

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.bot})"

    # --- running --------------------------------------------------------------

    async def run(self) -> None:
        """
        Run every DecisionMaker's loops until cancelled, or until one raises.

        The loops are tasks of one TaskGroup, so a loop that raises ends the Bot
        as it always has, and the Bot's `ExceptionGroup` holds that exception.
        """
        async with asyncio.TaskGroup() as tg:
            self._tg = tg
            for slot in self._slots:
                tg.create_task(self._supervise(slot), name=f"{slot.dm} - Supervisor")

    async def _supervise(self, slot: _Slot) -> None:
        """
        Start one DecisionMaker's loops whenever it holds no Pause, and wait for
        them to end; for ever.

        A restart waits for every loop of the previous run to have ended, so two
        runs of one DecisionMaker never overlap, and `on_stop` always comes
        between them.
        """
        dm = slot.dm
        assert self._tg is not None, "run() creates the TaskGroup first"
        while True:
            await self._until(slot, lambda: not slot.pauses)
            generation = slot.generation
            dm.on_start()
            slot.tasks = [
                self._tg.create_task(
                    dm._decision_loop(loop.name, loop.decide),  # pyright: ignore[reportPrivateUsage] - the Supervisor is what runs it
                    name=loop.name,
                )
                for loop in dm.loops()
            ]
            try:
                if slot.tasks:
                    await asyncio.wait(slot.tasks)
            finally:
                await self._stop(slot.tasks)
                slot.tasks = []
                dm.on_stop()
            # Loops that ended by themselves rather than by a Pause stay ended
            # until the next Pause is taken and released, as a dead decision
            # task always has. Waiting here is what stops them restarting in a
            # hot loop.
            await self._until(slot, lambda then=generation: slot.generation != then)

    @staticmethod
    async def _stop(tasks: Sequence[asyncio.Task[None]]) -> None:
        """
        Cancel `tasks` and wait until every one has finished unwinding, so that
        `on_stop` only ever runs once the loops have stopped.

        Only reached with loops still running when `_supervise` itself is
        leaving on an exception (the Bot is cancelled, or another loop raised),
        which re-raises once this returns. A further cancellation while waiting
        is therefore absorbed rather than allowed to skip `on_stop`.

        A loop already being cancelled (by the TaskGroup, as the Bot ends) is
        not cancelled again: a second cancellation would land inside its own
        clean-up, at its first `await`, and cut it short.
        """
        for task in tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        while not all(task.done() for task in tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait(tasks)

    @staticmethod
    async def _until(slot: _Slot, predicate: Callable[[], bool]) -> None:
        while not predicate():
            await slot.changed.wait()

    @staticmethod
    def _changed(slot: _Slot) -> None:
        slot.changed.set()
        slot.changed = asyncio.Event()

    # --- holding and releasing ------------------------------------------------

    def declared(self, cls: type[DecisionMaker]) -> frozenset[type[DecisionMaker]]:
        """The classes `cls` declares it may pause, resolved."""
        return self._declared.get(cls, frozenset())

    def classes(self) -> list[type[DecisionMaker]]:
        """The class of every DecisionMaker this Bot runs, in the Bot's order."""
        return [type(slot.dm) for slot in self._slots]

    def target(self, cls: type[DecisionMaker]) -> PauseTarget:
        """The address of `cls` in this Bot."""
        return PauseTarget(self.bot, cls)

    def hold(self, pause: Pause) -> bool:
        """
        Take `pause`. A DecisionMaker going from no Pause to one has its loops
        cancelled, at once: none of them decides again before the Pause is
        released.
        :return: Whether anything was paused. A Pause on a class this Bot does
            not run is a no-op; one on a class pauses that exact class only,
            never a subclass.
        """
        slots = self._slots_of(pause.target)
        for slot in slots:
            slot.pauses.append(pause)
            if len(slot.pauses) == 1:
                slot.generation += 1
                for task in slot.tasks:
                    task.cancel()
            self._changed(slot)
        return bool(slots)

    def release(self, pause: Pause) -> bool:
        """
        Release `pause`. A DecisionMaker left with no Pause has `on_start()`
        called and its loops started again. Releasing twice does nothing.
        :return: Whether `pause` was held.
        """
        released = False
        for slot in self._slots_of(pause.target):
            if pause in slot.pauses:
                slot.pauses.remove(pause)
                released = True
                self._changed(slot)
        return released

    def held(self, cls: type[DecisionMaker]) -> list[Pause]:
        """Every Pause held on `cls` in this Bot, oldest first."""
        return [
            pause for slot in self._slots_of(self.target(cls)) for pause in slot.pauses
        ]

    def _slots_of(self, target: PauseTarget) -> list[_Slot]:
        if target.bot != self.bot:
            raise ValueError(
                f"{self} cannot pause {target.cls.__name__} of {target.bot}: "
                "a Pause addresses its own Bot only."
            )
        return [slot for slot in self._slots if type(slot.dm) is target.cls]

    # --- the user ---------------------------------------------------------------

    def pause_for_user(self, reason: str) -> list[Pause]:
        """
        Discord `PAUSE`: a Pause held by the user on every DecisionMaker. The
        movement-key release that goes with it is `Bot.pause`'s to send.
        :return: The Pauses taken, one per DecisionMaker class.
        """
        taken: list[Pause] = []
        for cls in dict.fromkeys(self.classes()):
            pause = Pause(self.target(cls), USER, reason, PauseKind.USER)
            if self.hold(pause):
                emit_event(None, DECISION_PAUSED, pause.payload(), logger_name=__name__)
                taken.append(pause)
        return taken

    def resume_for_user(self) -> list[Pause]:
        """
        Discord `RESUME`: release every user-held Pause, and every legacy shim
        Pause, as `RESUME` has always restarted every DecisionMaker. Scoped
        Pauses stay held: their blocks are still running.
        :return: The Pauses released.
        """
        released: list[Pause] = []
        for slot in self._slots:
            for pause in list(slot.pauses):
                if pause.kind is PauseKind.SCOPED:
                    continue
                if self.release(pause):
                    released.append(pause)
                    if pause.kind is PauseKind.USER:
                        emit_event(
                            None,
                            DECISION_RESUMED,
                            pause.payload(),
                            logger_name=__name__,
                        )
        return released
