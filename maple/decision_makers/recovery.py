"""
The thin half of movement recovery: the plumbing a `StuckMonitor` refuses to know
about.

Every judgement - which symptom fired, which rung the Reaction Ladder is on, what
the suspected move is - belongs to `maple.movement_recovery.StuckMonitor`,
which runs offline and is checked offline. What lives here is reading the loop's
state from its holder's keys, measuring the Delivery Gate across the process
boundary, and turning a `Reaction` into an `ActionRequest`. This mirrors the
`TrialDriver`/`TrialRunner` seam, and for the same reason: the half that can be
driven by a fed position stream is the half worth putting the thresholds in.

**Measuring the Delivery Gate across processes.** A DecisionMaker decides in an
Engine; the Input Sequence is compiled and sent in Main Process (ADR 0002), so the
Delivered Prefix is invisible here. `controller.compile_and_send` returns the Step
count, and `ActionRequest.result_callbacks` carries it back onto a manager Queue that
this helper drains once per cycle. A cancelled Action reports nothing, which is the
reading the gate wants: preemption stops the clocks.
"""

import asyncio
import functools
import importlib
import logging
import queue
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from botting import PARENT_LOG, controller
from botting.core import (
    ActionRequest,
    BotData,
    DecisionMaker,
    DiscordRequest,
    Key,
    ProxyFactory,
    action_name,
)
from botting.screen import Reading
from maple.actions import priorities
from maple.actions.movements_v2 import random_jump
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import Point
from maple.movement_recovery import (
    Reaction,
    RecoveryThresholds,
    Rung,
    StuckMonitor,
    Symptom,
)
from maple.screen.position import VirtualPosition, marker_of_feet

from .providers import (
    DESTINATION,
    FRAME,
    HANDLE,
    MINIMAP_SHOWN,
    MOVEMENTS,
    PATH,
    POSITION,
    WORLD_MAP,
    DestinationProvider,
    actionable,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: The DecisionMakers an Escalate stops until a human resumes: the set
#: `CheckStillInMap` stops when it confirms the character is out of its map,
#: the established "stop the bot and wait for a human" idiom, and the telecast.
#: Dotted paths: each of these modules imports the rotation, which holds this.
ESCALATION_TARGETS = (
    "maple.decision_makers.rotation.Rotation",
    "maple.decision_makers.ensure_still_in_map.CheckStillInMap",
    "maple.decision_makers.ensure_mob_still_spawn.CheckMobsStillSpawn",
    "maple.decision_makers.mobs_hitting.MobsHitting",
    "maple.decision_makers.telecast_mobs_hitting.TelecastMobsHitting",
)


def escalation_classes() -> tuple[type[DecisionMaker], ...]:
    """
    The classes `ESCALATION_TARGETS` names, in its order. Imported when asked:
    once a Bot is assembled, which resolved its holder's `pauses`, every one of
    their modules is.
    """
    classes: list[type[DecisionMaker]] = []
    for path in ESCALATION_TARGETS:
        module, _, name = path.rpartition(".")
        classes.append(getattr(importlib.import_module(module), name))
    return tuple(classes)


class _Holder(Protocol):
    """The DecisionMaker a `MovementRecovery` recovers: `Rotation`."""

    data: BotData

    def read[T](self, key: Key[T]) -> T: ...

    def send(
        self, request: ActionRequest, correlation_id: str | None = None
    ) -> None: ...

    def emit(
        self,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None: ...

    def pause_for_user(self, *classes: type[DecisionMaker], reason: str) -> None: ...


class MovementRecovery:
    """
    Wires a `StuckMonitor` to a rotation loop: the helper its holder calls once
    per cycle (`check`), whose Delivery Gate its holder's Movement Actions feed
    (`delivered`).

    Successor to `FailsafeMixin`, whose six raw-equality sentinels this replaces.
    The inputs are deliberately DecisionMaker-neutral - a position stream, a
    target, a Path, a Movement Plan and a delivered-Step count - so a second loop
    can be wired to it without the monitor learning anything about DecisionMakers.
    Only `Rotation` holds one.

    It reads through its holder, whose `reads` must declare every key in
    `reads`, and sends, emits and pauses through it: its Actions are its
    holder's, and an Escalate pauses what its holder's `pauses` declares.
    """

    #: The keys it reads, which its holder declares.
    reads = (
        HANDLE,
        FRAME,
        WORLD_MAP,
        POSITION,
        DESTINATION,
        PATH,
        MOVEMENTS,
        MINIMAP_SHOWN,
    )

    #: How long after the loop starts the detectors begin judging. A Session's
    #: first seconds are spent finding the character and the minimap, and a Stall
    #: measured through that is measuring the setup, not the rotation.
    RECOVERY_GRACE_PERIOD = 10.0

    #: How stale a position reading may be before the detectors stop judging it.
    STALE_POSITION_AFTER = 1.0

    def __init__(
        self,
        holder: _Holder,
        *,
        physics: Callable[[], VRPhysics],
        thresholds: RecoveryThresholds | None = None,
    ) -> None:
        """
        :param holder: The DecisionMaker it recovers.
        :param physics: The character's physics now: the Reflex's jump lasts the
            flight of its current jump.
        :param thresholds: The named shapes the detectors run on. None takes the
            provisional defaults, which issue #120's Trials are what actually fit.
        """
        self._holder = holder
        self._physics = physics
        self._thresholds = thresholds
        self._monitor: StuckMonitor
        self._recovery_starts_at = 0.0
        self._escalation_targets: tuple[type[DecisionMaker], ...] = ()
        self._escalated = False
        self._delivery: queue.Queue[Any]

    def setup(
        self,
        proxies: ProxyFactory,
        escalation_targets: Sequence[type[DecisionMaker]],
    ) -> None:
        """
        Make the monitor and the delivery queue, and start the grace period:
        its holder's `setup()`, since asking Main Process for a Queue is I/O.
        :param proxies: Its holder's `ProxyFactory`.
        :param escalation_targets: What an Escalate pauses until a human resumes.
        """
        # Telemetry keeps the target's canvas px beside its virtual px (R-D2).
        world_map = self._holder.read(WORLD_MAP)
        transform = None if world_map is None else world_map.minimap
        self._monitor = StuckMonitor(
            self._thresholds,
            emit=self._holder.emit,
            to_canvas=(
                None
                if transform is None
                else functools.partial(marker_of_feet, transform)
            ),
        )
        self._recovery_starts_at = time.perf_counter() + self.RECOVERY_GRACE_PERIOD
        self._escalation_targets = tuple(escalation_targets)
        self._escalated = False
        # Main Process puts one Delivered Prefix length here per completed movement
        # Action; this process drains it each cycle. A Queue rather than a shared
        # counter because both halves of it - Main Process's put and the Engine's
        # drain - are then single atomic proxy calls.
        self._delivery = proxies.instance(f"{self._holder} - delivery", "Queue")

    @property
    def delivered(self) -> Callable[[object], None]:
        """What reports a Movement Action's Delivered Prefix from Main Process:
        the delivery queue's own `put_nowait`, for its `result_callbacks`."""
        return self._delivery.put_nowait

    def restart_grace_period(self) -> None:
        """
        Push the detectors' start back, as at setup.

        Called whenever the decision loop (re)starts: a DecisionMaker that was
        paused and resumed is in the same position a fresh Session is - the
        character may be anywhere, and the first cycles are spent finding it.
        """
        self._recovery_starts_at = time.perf_counter() + self.RECOVERY_GRACE_PERIOD

    # --- the cycle ----------------------------------------------------------------

    def check(self, now: float) -> None:
        """
        Hand the monitor one decision cycle, and act on what comes back.

        Called every cycle, before the gate is tried: a cycle that cannot enter
        it still happened, and the Delivery Gate is what makes those cycles cost
        nothing rather than needing to be skipped.
        :param now: A monotonic reading, in seconds.
        """
        delivered = self._drain_delivery()
        if now < self._recovery_starts_at:
            return

        read = self._holder.read
        # Virtual px throughout (#398): the position fusion read, the target on
        # the map's platforms, and the graph Path's remaining time.
        reading = self._position()
        position = None if reading.value is None else (reading.value.x, reading.value.y)
        path = read(PATH)
        target = read(DESTINATION)
        # The *actionable* plan, which is what both the Delivery Gate and
        # Starvation ask about. A plan holding nothing but the END_OF_MOVEMENT
        # sentinel compiles to no Input Sequence and is never dispatched, so
        # handing it over as non-empty would report a loop that is planning
        # when it is not.
        movements = read(MOVEMENTS)
        reaction = self._monitor.observe(
            position,
            now,
            target=target,
            remaining=None if path is None else path.duration,
            plan=movements if actionable(movements) else (),
            delivered_steps=delivered,
            position_valid=self._position_is_valid(),
            on_expected_minimap=self._on_expected_minimap(),
            alive=self._is_alive(),
        )
        if reaction is not None:
            self._react_to(reaction)

    def _position(self) -> Reading[VirtualPosition]:
        """
        `POSITION`, read when it is stale; `UNSURE`, without a read, on a map no
        position is read on (the map not known, or with no minimap), where a
        read could only fail into the minimap's error handler.
        """
        world_map = self._holder.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            return Reading.unsure(0.0, "no position is read on this map")
        return self._holder.read(POSITION)

    def _drain_delivery(self) -> int:
        """
        :return: Movement Steps delivered since the previous cycle, summed over
            however many Actions completed in between.
        """
        delivered = 0
        while True:
            try:
                delivered += int(self._delivery.get_nowait())
            except queue.Empty:
                return delivered
            except EOFError, OSError:
                # The manager is going away, which is the Session ending. Worth a
                # line, but not worth taking the Engine down from inside the thing
                # whose whole job is noticing trouble.
                logger.debug("%s could not read the delivery queue.", self._ign)
                return delivered

    # --- look-alike guards ----------------------------------------------------------

    def _position_is_valid(self) -> bool:
        """
        Whether the position the detectors are about to judge was actually read
        recently. Reacting to a detection outage is the minimap's error
        handler's; this only stops the Stuck clocks from charging the outage to
        the rotation, which is how a blind bot used to look exactly like a stuck
        one. An `UNSURE` read is handed over as no position, which freezes them
        too.
        """
        age = self._holder.data.get_time_since_last_valid_update(POSITION.name)
        return age <= self.STALE_POSITION_AFTER

    def _on_expected_minimap(self) -> bool:
        """
        Whether the minimap the position was read off is on screen at all.

        The cached value, deliberately: `MINIMAP_SHOWN` has no threshold, so
        reading it costs no screenshot, and it is refreshed by the minimap's
        error handler, which is precisely when it goes False. The other half of
        this guard - being in the *right* map - is `CheckStillInMap`'s, which
        pauses the rotation outright when it confirms otherwise, so no clock
        runs through it either.
        """
        return bool(self._holder.read(MINIMAP_SHOWN))

    def _is_alive(self) -> bool:
        """
        Whether the character is alive. Death detection is issue #127's; until it
        lands there is nothing to ask, and the guard exists from day one so that
        wiring it later is one method body rather than a new parameter threaded
        through every detector.
        """
        return True

    # --- reactions -------------------------------------------------------------------

    def _react_to(self, reaction: Reaction) -> None:
        if reaction.rung is Rung.REFLEX:
            self._holder.send(self._reflex_request(reaction))
        elif reaction.rung is Rung.ABANDON:
            dropped = reaction.target
            replacement = self._abandon_destination()
            if replacement is None:
                # Claimed: its holder decides where the character goes, so
                # nothing was abandoned and there is nothing to alert about.
                logger.warning(
                    "%s kept target %s after %s: the destination is claimed.",
                    self._ign,
                    dropped,
                    reaction.symptom.value,
                )
                return
            logger.warning(
                "%s abandoned target %s for %s after %s.",
                self._ign,
                dropped,
                replacement,
                reaction.symptom.value,
            )
            self._holder.send(
                self._alert_request(self._abandon_message(reaction, replacement))
            )
        elif reaction.rung is Rung.ESCALATE:
            self._escalate(reaction)
        elif reaction.symptom is Symptom.UNSURE_POSITION:
            self._report_unsure_position()
        else:
            # Starvation: reported, never reacted to in-game. Nothing about the map
            # is wrong, so a Reflex would be noise and an Abandon would be a lie.
            logger.error(
                "%s produced movements but delivered no input. %s",
                self._ign,
                "Something upstream is starving the rotation.",
            )
            self._holder.send(
                self._alert_request(
                    f"{self._ign}: movements are being produced but no input is "
                    f"reaching the client."
                )
            )

    def _abandon_destination(self) -> Point | None:
        """
        Abandon, through `DESTINATION`'s Provider: a new destination, or None
        while a Claim holds it, when the Provider does nothing.
        """
        providers = self._holder.data.providers
        assert providers is not None, "the Bot attaches its Providers to its data"
        return providers.get(DestinationProvider).abandon()

    def _report_unsure_position(self) -> None:
        """
        The Unsure position: an alert, and nothing in-game. Moving a character the
        bot can't place would be a guess (C-NOGUESS), so the rotation keeps
        holding and a human looks.
        """
        reading = self._position()
        window = self._monitor.thresholds.unsure_window
        detail = reading.detail or "no detail"
        logger.error(
            "%s could not place itself for %.0f s: %s", self._ign, window, detail
        )
        self._holder.send(
            self._alert_request(
                f"{self._ign} has not been able to place itself for "
                f"{window:.0f} s ({detail}), so the rotation is holding. Another "
                f"player standing on it is the usual cause."
            )
        )

    def _reflex_request(self, reaction: Reaction) -> ActionRequest:
        """
        The first rung: release whatever is held, pause, jump somewhere random.

        Priority and cancellation are `FailsafeMixin`'s, unchanged - this preempts
        the rotation Action it is trying to unstick, and blocks lower priorities
        while it runs so the loop cannot immediately re-dispatch into the same wall.
        """
        return ActionRequest(
            f"{self._holder} - Reflex",
            self._wait_and_random_jump,
            ign=self._ign,
            priority=priorities.FAILSAFE,
            requeue_if_not_scheduled=True,
            block_lower_priority=True,
            cancels_itself=True,
            cancel_tasks=[self._holder_actions()],
            args=(
                self._holder.read(HANDLE),
                controller.key_binds(self._ign)["jump"],
                self._physics().jump_duration,
            ),
        )

    def _alert_request(self, message: str) -> ActionRequest:
        """
        A Discord alert and nothing else. Every Abandon alerts, every time: early
        spam is signal, and rate-limiting waits until real session data justifies
        it (#119).
        """
        return ActionRequest(
            f"{self._holder} - Recovery alert",
            self._noop,
            ign=self._ign,
            priority=priorities.FAILSAFE,
            requeue_if_not_scheduled=False,
            cancels_itself=True,
            discord_request=DiscordRequest(message, self._holder.read(FRAME).pixels),
        )

    def _escalate(self, reaction: Reaction) -> None:
        """
        The last rung: stop deciding, drop the keys, and wait for a human.

        Idempotent, so that a caller reaching here again before the Pause has
        cancelled this loop ships no second alert.

        The stop is a user-held Pause on the escalation targets
        (`pause_for_user`), its holder's own class among them: only the Discord
        `RESUME` command releases it.
        """
        if self._escalated:
            return
        self._escalated = True
        names = ", ".join(cls.__name__ for cls in self._escalation_targets)
        logger.critical(
            "%s escalating after %s; suspending %s.",
            self._ign,
            reaction.symptom.value,
            names,
        )
        self._holder.send(
            ActionRequest(
                f"{self._holder} - Escalate",
                self._release_movement_keys,
                ign=self._ign,
                priority=priorities.FAILSAFE,
                requeue_if_not_scheduled=True,
                cancels_itself=True,
                cancel_tasks=[self._holder_actions()],
                discord_request=DiscordRequest(
                    self._escalate_message(reaction), self._holder.read(FRAME).pixels
                ),
                args=(self._holder.read(HANDLE),),
            )
        )
        self._holder.pause_for_user(
            *self._escalation_targets,
            reason=f"movement recovery escalated after {reaction.symptom.value}",
        )

    def _holder_actions(self) -> str:
        """What its holder's own Actions are named: what a rung preempts."""
        return action_name(type(self._holder), self._ign)

    @property
    def _ign(self) -> str:
        return self._holder.data.ign

    # --- messages ----------------------------------------------------------------------

    def _abandon_message(self, reaction: Reaction, replacement: Point) -> str:
        return (
            f"{self._ign} gave up on {_px(reaction.target)} after "
            f"{reaction.symptom.value} and is heading for {_px(replacement)} "
            f"instead. {self._suspect_clause(reaction)}"
        )

    def _escalate_message(self, reaction: Reaction) -> str:
        target = _px(reaction.target)
        if reaction.abandon_count:
            cause = f"has now abandoned {target} {reaction.abandon_count} times"
        else:
            cause = f"could not recover from {reaction.symptom.value} at {target}"
        return (
            f"{self._ign} {cause} and is paused with its keys released. "
            f"{self._suspect_clause(reaction)} Send RESUME when it is unstuck."
        )

    @staticmethod
    def _suspect_clause(reaction: Reaction) -> str:
        suspect = reaction.suspected_connection
        if suspect is None:
            return ""
        return (
            f"Suspected connection: {suspect.movement_type} "
            f"{suspect.start} -> {suspect.end}."
        )

    # --- Main Process procedures ---------------------------------------------------------

    @staticmethod
    async def _wait_and_random_jump(handle: int, jump_key: str, flight: float) -> None:
        """
        The Reflex itself, run in Main Process.

        The release is `release_directions`, not a blind keyup volley: it reads the
        Held-Keys Ledger, so it sends nothing for a key that is not actually down
        and cannot emit a phantom release (**A6**). A latched direction is the
        commonest cause of a Stall, so this alone often unsticks the character; the
        jump covers the rest.
        """
        controller.release_directions(handle)
        await asyncio.sleep(3.0)
        await random_jump(handle, jump_key, flight).send()

    @staticmethod
    async def _release_movement_keys(handle: int) -> None:
        controller.release_keys(["left", "up", "down", "right"], handle)

    @staticmethod
    async def _noop() -> None:
        """An Action whose whole purpose is the Discord alert riding on it."""


def _px(point: Point) -> str:
    """A virtual position, rounded to the px, for a human to read."""
    return f"({round(point[0])}, {round(point[1])}) virtual px"
