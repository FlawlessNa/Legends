"""
The thin half of movement recovery: the plumbing a `StuckMonitor` refuses to know
about.

Every judgement - which symptom fired, which rung the Reaction Ladder is on, what
the suspected grid connection is - belongs to `maple.movement_recovery.StuckMonitor`,
which runs offline and is checked offline. What lives here is reading the loop's
state out of `BotData`, measuring the Delivery Gate across the process boundary, and
turning a `Reaction` into an `ActionRequest`. This mirrors the
`TrialDriver`/`TrialRunner` seam, and for the same reason: the half that can be
driven by a fed position stream is the half worth putting the thresholds in.

**Measuring the Delivery Gate across processes.** A DecisionMaker decides in an
Engine; the Input Sequence is compiled and sent in Main Process (ADR 0002), so the
Delivered Prefix is invisible here. `controller.compile_and_send` returns the Step
count, and `ActionRequest.result_callbacks` carries it back onto a manager Queue that
this mixin drains once per cycle. A cancelled Action reports nothing, which is the
reading the gate wants: preemption stops the clocks.
"""

import asyncio
import logging
import queue
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DiscordRequest, ProxyFactory
from maple.actions import priorities
from maple.actions.movements_v2 import random_jump
from maple.movement_recovery import (
    Reaction,
    RecoveryThresholds,
    Rung,
    StuckMonitor,
    Symptom,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: The DecisionMakers an Escalate suspends. Matches the set `CheckStillInMap`
#: disables when it confirms the character is out of its map - the established
#: "stop the bot and wait for a human" idiom available to a DecisionMaker.
DEFAULT_ESCALATION_TARGETS = (
    "Rotation",
    "CheckStillInMap",
    "CheckMobsStillSpawn",
    "MobsHitting",
    "TelecastMobsHitting",
    "PartyRebuff",
)


class _Node(Protocol):
    """The two fields this mixin needs off a Path node."""

    x: int
    y: int


class MovementRecoveryMixin:
    """
    Wires a `StuckMonitor` to a rotation loop.

    Successor to `FailsafeMixin`, whose six raw-equality sentinels this replaces.
    The inputs are deliberately DecisionMaker-neutral - a position stream, a
    target, a Path, a Movement Plan and a delivered-Step count - so a second loop
    can be wired to it without the monitor learning anything about DecisionMakers.
    Only `Rotation` is wired in this effort.
    """

    data: BotData
    send: Callable[[ActionRequest], None]
    emit: Callable[[str, Mapping[str, object]], None]
    _proxies: ProxyFactory
    _disable_decision_makers: Callable[..., None]
    _abandon_current_target: Callable[[], tuple[int, int]]
    _has_movements: Callable[[], bool]

    #: How long after the loop starts the detectors begin judging. A Session's
    #: first seconds are spent finding the character and the minimap, and a Stall
    #: measured through that is measuring the setup, not the rotation.
    RECOVERY_GRACE_PERIOD = 10.0

    #: How stale a position reading may be before the detectors stop judging it.
    STALE_POSITION_AFTER = 1.0

    _monitor: StuckMonitor
    _recovery_starts_at: float

    def _create_recovery_attributes(
        self,
        thresholds: RecoveryThresholds | None = None,
        *,
        escalation_targets: Sequence[str] = DEFAULT_ESCALATION_TARGETS,
    ) -> None:
        """
        :param thresholds: The named shapes the detectors run on. None takes the
            provisional defaults, which issue #120's Trials are what actually fit.
        :param escalation_targets: The DecisionMakers an Escalate suspends.
        """
        self._monitor = StuckMonitor(thresholds, emit=self.emit)
        self._recovery_starts_at = time.perf_counter() + self.RECOVERY_GRACE_PERIOD
        self._escalation_targets = tuple(escalation_targets)
        self._escalated = False
        # Main Process puts one Delivered Prefix length here per completed movement
        # Action; this process drains it each cycle. A Queue rather than a shared
        # counter because both halves of it - Main Process's put and the Engine's
        # drain - are then single atomic proxy calls.
        self._delivery = self._proxies.instance(f"{self} - delivery", "Queue")
        self.data.set_feature("has_recovery_attributes")

    def _restart_recovery_grace_period(self) -> None:
        """
        Push the detectors' start back, as at construction.

        Called whenever the decision task (re)starts: a DecisionMaker that was
        suspended and resumed is in the same position a fresh Session is - the
        character may be anywhere, and the first cycles are spent finding it.
        """
        self._recovery_starts_at = time.perf_counter() + self.RECOVERY_GRACE_PERIOD

    # --- the cycle ----------------------------------------------------------------

    def _recovery_check(self, now: float) -> None:
        """
        Hand the monitor one decision cycle, and act on what comes back.

        Called every cycle, before the lock is contended for: a cycle that cannot
        acquire the lock still happened, and the Delivery Gate is what makes those
        cycles cost nothing rather than needing to be skipped.
        :param now: A monotonic reading, in seconds.
        """
        delivered = self._drain_delivery()
        if now < self._recovery_starts_at:
            return

        reaction = self._monitor.observe(
            self.data.current_minimap_position,
            now,
            target=self.data.next_target,
            path=_as_points(self.data.path),
            # The *actionable* plan, which is what both the Delivery Gate and
            # Starvation ask about. A plan holding nothing but the END_OF_MOVEMENT
            # sentinel compiles to no Input Sequence and is never dispatched, so
            # handing it over as non-empty would report a loop that is planning
            # when it is not.
            plan=self.data.movements if self._has_movements() else (),
            delivered_steps=delivered,
            position_valid=self._position_is_valid(),
            on_expected_minimap=self._on_expected_minimap(),
            alive=self._is_alive(),
        )
        if reaction is not None:
            self._react_to(reaction)

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
                logger.debug("%s could not read the delivery queue.", self.data.ign)
                return delivered

    # --- look-alike guards ----------------------------------------------------------

    def _position_is_valid(self) -> bool:
        """
        Whether the position the detectors are about to judge was actually detected
        recently. Reacting to a detection outage is `_minimap_pos_error_handler`'s;
        this only stops the Stuck clocks from charging the outage to the rotation,
        which is how a blind bot used to look exactly like a stuck one.
        """
        age = self.data.get_time_since_last_valid_update("current_minimap_position")
        return age <= self.STALE_POSITION_AFTER

    def _on_expected_minimap(self) -> bool:
        """
        Whether the minimap the position was read off is on screen at all.

        The cached value, deliberately: refreshing it costs a client screenshot,
        and the attribute is refreshed by the error handler, which is precisely
        when it goes False. The other half of this guard - being in the *right*
        map - is `CheckStillInMap`'s, which disables this DecisionMaker outright
        when it confirms otherwise, so no clock runs through it either.
        """
        return bool(self.data.minimap_currently_displayed)

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
            self.send(self._reflex_request(reaction))
        elif reaction.rung is Rung.ABANDON:
            dropped = reaction.target
            replacement = self._abandon_current_target()
            logger.warning(
                "%s abandoned target %s for %s after %s.",
                self.data.ign,
                dropped,
                replacement,
                reaction.symptom.value,
            )
            self.send(self._alert_request(self._abandon_message(reaction, replacement)))
        elif reaction.rung is Rung.ESCALATE:
            self._escalate(reaction)
        else:
            # Starvation: reported, never reacted to in-game. Nothing about the map
            # is wrong, so a Reflex would be noise and an Abandon would be a lie.
            logger.error(
                "%s produced movements but delivered no input. %s",
                self.data.ign,
                "Something upstream is starving the rotation.",
            )
            self.send(
                self._alert_request(
                    f"{self.data.ign}: movements are being produced but no input is "
                    f"reaching the client."
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
            f"{self} - Reflex",
            self._wait_and_random_jump,
            ign=self.data.ign,
            priority=priorities.FAILSAFE,
            requeue_if_not_scheduled=True,
            block_lower_priority=True,
            cancels_itself=True,
            cancel_tasks=[f"{self}"],
            args=(self.data.handle, controller.key_binds(self.data.ign)["jump"]),
        )

    def _alert_request(self, message: str) -> ActionRequest:
        """
        A Discord alert and nothing else. Every Abandon alerts, every time: early
        spam is signal, and rate-limiting waits until real session data justifies
        it (#119).
        """
        return ActionRequest(
            f"{self} - Recovery alert",
            self._noop,
            ign=self.data.ign,
            priority=priorities.FAILSAFE,
            requeue_if_not_scheduled=False,
            cancels_itself=True,
            discord_request=DiscordRequest(message, self.data.current_client_img),
        )

    def _escalate(self, reaction: Reaction) -> None:
        """
        The last rung: stop deciding, drop the keys, and wait for a human.

        Idempotent, because the disable takes effect when the disabler thread
        cancels this task and one or more further cycles may reach here first.

        The suspension is `_disable_decision_makers`, which is the only pause a
        DecisionMaker can reach from inside an Engine - `Bot.pause()` is driven
        from Main Process by the Discord PAUSE command. Resume is the Discord
        RESUME command, which calls `Bot.resume()`; that it recreates tasks for
        DecisionMakers which were never suspended is a pre-existing wart and issue
        #121's to settle, not this one's.
        """
        if self._escalated:
            return
        self._escalated = True
        logger.critical(
            "%s escalating after %s; suspending %s.",
            self.data.ign,
            reaction.symptom.value,
            ", ".join(self._escalation_targets),
        )
        self.send(
            ActionRequest(
                f"{self} - Escalate",
                self._release_movement_keys,
                ign=self.data.ign,
                priority=priorities.FAILSAFE,
                requeue_if_not_scheduled=True,
                cancels_itself=True,
                cancel_tasks=[f"{self}"],
                discord_request=DiscordRequest(
                    self._escalate_message(reaction), self.data.current_client_img
                ),
                args=(self.data.handle,),
            )
        )
        self._disable_decision_makers(*self._escalation_targets)

    # --- messages ----------------------------------------------------------------------

    def _abandon_message(self, reaction: Reaction, replacement: tuple[int, int]) -> str:
        return (
            f"{self.data.ign} gave up on {reaction.target} after "
            f"{reaction.symptom.value} and is heading for {replacement} instead. "
            f"{self._suspect_clause(reaction)}"
        )

    def _escalate_message(self, reaction: Reaction) -> str:
        if reaction.abandon_count:
            cause = (
                f"has now abandoned {reaction.target} {reaction.abandon_count} times"
            )
        else:
            cause = (
                f"could not recover from {reaction.symptom.value} at {reaction.target}"
            )
        return (
            f"{self.data.ign} {cause} and is paused with its keys released. "
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
    async def _wait_and_random_jump(handle: int, jump_key: str) -> None:
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
        await random_jump(handle, jump_key).send()

    @staticmethod
    async def _release_movement_keys(handle: int) -> None:
        controller.release_keys(["left", "up", "down", "right"], handle)

    @staticmethod
    async def _noop() -> None:
        """An Action whose whole purpose is the Discord alert riding on it."""


def _as_points(path: Sequence[_Node] | None) -> tuple[tuple[int, int], ...]:
    """
    The Path as plain coordinates. The monitor measures the remaining Path's
    *length* and locates the suspected connection on it; neither needs a
    `MinimapNode`, and taking one would put the pathfinder's types in front of
    every offline check.
    """
    if not path:
        return ()
    return tuple((int(node.x), int(node.y)) for node in path)


#: Re-exported so a caller configuring the mixin does not also have to import from
#: `maple.movement_recovery`.
__all__ = [
    "DEFAULT_ESCALATION_TARGETS",
    "MovementRecoveryMixin",
    "RecoveryThresholds",
    "Rung",
    "Symptom",
]
