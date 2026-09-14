"""
Movement recovery: the Stuck detectors and the Reaction Ladder, with no bot around
them.

Vocabulary: ``CONTEXT.md`` -> **Movement recovery** (Stuck, Delivery Gate, Stall,
Stagnation, Plan Churn, Target Timeout, Starvation, Reaction Ladder). The catalogue
is symptom-keyed: the monitor observes symptoms and reacts to symptoms; causes are
inferred offline from the ``recovery.*`` Telemetry Records it emits.

This is the deep half of the seam issue #119 designed and #128 implements - the
successor to the retired ``FailsafeMixin`` and its raw-equality sentinels. Like
`maple.calibration.driver.TrialDriver`, the monitor is fed everything and owns
nothing live: a position, a clock reading, the target, the freshly recomputed Path,
the Movement Plan, and how many movement Steps were delivered since the last cycle.
It answers with what the loop should do. The DecisionMaker on the other side
(`maple/decision_makers/mixins/_recovery_mixins.py`) holds the plumbing and no
judgement, which is what makes every symptom's firing and every rung's advance
checkable offline.

**The Delivery Gate** is the load-bearing move: no Stuck detector accumulates time
unless movement Steps were actually delivered in the window being judged. Time spent
casting, preempted, or waiting on arbitration counts toward no Stuck threshold - a
character that is not trying to move cannot be stuck. The gate is implemented as a
clock that only advances on cycles the rotation was in control for, so the false
positive the old sentinels had (a character casting in place for 30s) is eliminated
by construction, and so is their inverse hole (a character pinned at a wall while mob
knockback jitters its coordinates never triggered raw position equality). The one
place delivery is the wrong proxy for control is an empty Movement Plan, which
`observe` documents where it opens the gate for it.

Every threshold here is a **named shape with a provisional value**: issue #120's
Trials fit the values against issue #117's jitter/latency figures, per the repo rule
that measured constants are never settled by reasoning.
"""

from __future__ import annotations

import enum
import math
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.telemetry_events import (
    RECOVERY_ABANDON,
    RECOVERY_ESCALATE,
    RECOVERY_LADDER_RESET,
    RECOVERY_REFLEX,
    RECOVERY_STUCK_DETECTED,
    LadderResetPayload,
    ReactionPayload,
    StuckDetectedPayload,
)

#: Movement Plan components that are travel over a platform rather than a gesture
#: at a grid connection. Used by suspect attribution only.
_WALKS = frozenset({MovementTypes.WALK_LEFT, MovementTypes.WALK_RIGHT})


class Symptom(enum.Enum):
    """The five Stuck symptoms. Values are the strings telemetry carries."""

    STALL = "stall"
    STAGNATION = "stagnation"
    PLAN_CHURN = "plan_churn"
    TARGET_TIMEOUT = "target_timeout"
    STARVATION = "starvation"


class Rung(enum.Enum):
    """The Reaction Ladder's rungs. Values are the strings telemetry carries."""

    REFLEX = "reflex"
    ABANDON = "abandon"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RecoveryThresholds:
    """
    Every constant the detectors and the ladder run on, in one place.

    Each is a named shape from issue #119's catalogue; the values are provisional
    and deliberately conservative. #120's Trial campaign fits them against #117's
    measured jitter and detection-latency figures - do not tune them by reasoning.
    """

    #: ``J`` - displacement at or below this is detection jitter, not movement.
    #: The floor is #117's stationary-jitter figure.
    jitter_bound: float = 1.0
    #: ``W_stall`` - gated seconds of within-jitter displacement before Stall fires.
    stall_window: float = 4.0
    #: ``W_stag`` - gated seconds without the remaining-Path-length minimum
    #: decreasing before Stagnation fires.
    stagnation_window: float = 8.0
    #: How far the remaining-Path-length minimum must fall to count as progress.
    #: In Path *nodes*, deliberately not `jitter_bound`: that one is minimap
    #: pixels, and the Stagnation scalar is a node count.
    progress_epsilon: float = 1.0
    #: ``K`` - how many recent cycles the Plan Churn ring buffer holds.
    churn_cycles: int = 12
    #: ``R`` - a (quantized start, Movement Plan) hash seen this many times within
    #: the ring buffer fires Plan Churn, provided Stagnation saw no improvement.
    churn_repeats: int = 4
    #: Cell size, in minimap px, that quantizes a plan's start position for hashing.
    churn_quantum: int = 2
    #: ``m`` - the Target Timeout budget as a multiple of expected traversal time.
    timeout_multiplier: float = 4.0
    #: Expected traversal seconds per Path node - the crude expected-traversal
    #: model ``B = m * seconds_per_node * initial Path length`` runs on.
    seconds_per_node: float = 0.35
    #: The Target Timeout budget never shrinks below this, however short the Path.
    timeout_floor: float = 15.0
    #: ``W_starv`` - seconds of a non-empty Movement Plan with zero delivered
    #: Steps before Starvation is reported. Wall-clock by construction: Starvation
    #: is the Delivery Gate's inverse, so a gated clock could never reach it.
    starvation_window: float = 10.0
    #: ``R1`` - Reflex attempts before the ladder advances to Abandon.
    reflex_attempts: int = 2
    #: ``N`` - Abandons of one target that escalate instead of abandoning again.
    abandons_to_escalate: int = 3


@dataclass(frozen=True)
class SuspectedConnection:
    """
    The grid connection a Stuck incident is attributed to: the first gesture ahead
    in the Movement Plan, located on the Path. Attribution telemetry for #120's
    defect filing - never acted on live (per-session graph exclusion was rejected
    by #119).
    """

    start: tuple[int, int]
    end: tuple[int, int]
    movement_type: str


@dataclass(frozen=True)
class Reaction:
    """
    What the loop should do about the symptom that just fired.

    ``rung`` is None for a report-only symptom (Starvation): alert and record,
    change nothing in-game. The wiring formats the human-facing alert; everything
    it needs to say is here.
    """

    symptom: Symptom
    rung: Rung | None
    target: tuple[int, int]
    suspected_connection: SuspectedConnection | None = None
    #: Which Reflex attempt this is (1-based) when ``rung`` is REFLEX.
    reflex_attempt: int = 0
    #: How many times this target has been Abandoned, this one included.
    abandon_count: int = 0


@dataclass
class _TargetState:
    """Everything that resets when the ladder resets: one target's incident state."""

    target: tuple[int, int]
    #: The gated clock: advances only on cycles the rotation was in control for.
    gated: float = 0.0
    #: Stall anchor: where the character was, and the gated instant it was last
    #: seen outside jitter range of that spot.
    stall_pos: tuple[int, int] | None = None
    stall_at: float = 0.0
    #: Stagnation: the best (minimum) remaining-Path-length seen, and the gated
    #: instant it last improved.
    best_scalar: float | None = None
    improved_at: float = 0.0
    #: Plan Churn ring buffer of (hash, gated instant) pairs.
    churn: deque[tuple[int, float]] = field(default_factory=deque)
    #: Target Timeout: budget and the gated instant it started counting from.
    budget: float = 0.0
    timeout_from: float = 0.0
    #: Ladder position.
    reflex_count: int = 0
    abandoned: bool = False


class StuckMonitor:
    """
    Watches one rotation loop for the five Stuck symptoms and walks the Reaction
    Ladder.

    One call per decision cycle::

        reaction = monitor.observe(
            position, now, target=..., path=..., plan=..., delivered_steps=...
        )

    Nothing here reads a clock or a client. ``now`` is passed in -
    ``time.perf_counter()`` on the live path, whatever the test says offline - and
    only differences are used. Telemetry goes through the injected ``emit``, so a
    Trial analyzer and the live bot read one signal set.

    One Reaction Ladder per target: any symptom advances the single ladder, and
    issuing a reaction resets every detector window, so cascading symptoms of one
    incident advance it once rather than once each. Real progress (the remaining
    Path length improving beyond the jitter bound) resets the ladder entirely, as
    does a natural target change. The per-target Abandon tally deliberately
    survives both resets: ``N`` Abandons of one target is the config-failure
    signature Escalate exists to surface, however much progress happened in
    between.
    """

    def __init__(
        self,
        thresholds: RecoveryThresholds | None = None,
        *,
        emit: Callable[[str, dict], None] | None = None,
    ) -> None:
        """
        :param thresholds: The named shapes the detectors run on. Defaults to the
            provisional values #120 will fit.
        :param emit: Receives every ``recovery.*`` Telemetry Record as
            ``(event_type, payload)``. None drops them, which only a test wants.
        """
        self.thresholds = thresholds or RecoveryThresholds()
        self._emit_fn = emit
        self._last_now: float | None = None
        self._state: _TargetState | None = None
        #: Session-lifetime Abandon tally per target - see the class docstring.
        self._abandons: dict[tuple[int, int], int] = {}
        #: Set when an Abandon was issued and the target change it causes is
        #: therefore not a *natural* one.
        self._abandon_pending = False
        #: Starvation runs on wall clock, outside any target's gated state.
        self._starved = 0.0
        self._starvation_reported = False

    # --- the cycle ------------------------------------------------------------

    def observe(
        self,
        position: tuple[int, int],
        now: float,
        *,
        target: tuple[int, int],
        path: Sequence[tuple[int, int]],
        plan: Sequence[_MovementComponent],
        delivered_steps: int,
        position_valid: bool = True,
        on_expected_minimap: bool = True,
        alive: bool = True,
    ) -> Reaction | None:
        """
        Hand over one decision cycle.

        :param position: The detected minimap position this cycle decided from.
        :param now: A monotonic reading, in seconds. Only differences are used.
        :param target: Where the rotation is currently heading.
        :param path: The freshly recomputed Path, as ``(x, y)`` nodes. Its length
            is the Stagnation scalar - never distance-to-target, so a legitimate
            detour cannot fire Stagnation by construction.
        :param plan: The Movement Plan this cycle derived from that Path.
        :param delivered_steps: Movement Steps delivered to the game since the
            previous ``observe`` call - the Delivery Gate's input, read off the
            Held-Keys Ledger's send loop by the wiring.
        :param position_valid: Look-alike guard: False freezes every clock.
        :param on_expected_minimap: Look-alike guard: False freezes every clock.
        :param alive: Look-alike guard: False freezes every clock (#127 owns
            actually detecting death; the seam exists from day one).
        :return: What to do about it, or None when nothing fired.
        """
        dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now

        state = self._state
        if state is None or target != state.target:
            self._retarget(target, path)
            state = self._state
            assert state is not None
            dt = 0.0  # A fresh incident starts its clocks at zero.

        if not (position_valid and on_expected_minimap and alive):
            return None

        # --- Starvation: the gate's inverse, so it clocks wall time ------------
        starvation = self._observe_starvation(dt, plan, delivered_steps, target)

        # --- The Delivery Gate ---------------------------------------------------
        # Issue #119 words the gate as "movement Steps were delivered in the window",
        # and delivery is the proxy for what it is actually after: *the rotation was
        # in control of the character*. Time another DecisionMaker owned - casting,
        # preemption, lock waits - must not be charged to this loop.
        #
        # An empty Movement Plan is where that proxy inverts. A loop that can plan
        # nothing delivers nothing, so a gate reading delivery alone freezes every
        # clock exactly when the character is most thoroughly stuck: no Path to the
        # target, which is the case the retired `no_path` sentinel existed for. That
        # is not preemption, it is the rotation failing on its own time, so the gate
        # opens. (Starvation covers the opposite pairing - a plan produced and
        # nothing sent - so the two partition the space rather than overlapping.)
        if delivered_steps > 0 or not plan:
            state.gated += dt
        gated = state.gated

        # --- Feed the detectors --------------------------------------------------
        scalar = float(len(path))
        if state.stall_pos is None or (
            math.dist(position, state.stall_pos) > self.thresholds.jitter_bound
        ):
            state.stall_pos = position
            state.stall_at = gated

        if state.best_scalar is None:
            state.best_scalar = scalar
            state.improved_at = gated
        elif scalar <= state.best_scalar - self.thresholds.progress_epsilon:
            state.best_scalar = scalar
            state.improved_at = gated
            self._reset_ladder(state, reason="progress")

        # The ring buffer is fed only on delivering cycles, for the same reason the
        # clocks are: a plan re-derived while nothing is being sent is the loop
        # waiting its turn, not the loop churning.
        if plan and delivered_steps > 0:
            cell = (
                position[0] // self.thresholds.churn_quantum,
                position[1] // self.thresholds.churn_quantum,
            )
            state.churn.append((hash((cell, tuple(plan))), gated))
            while len(state.churn) > self.thresholds.churn_cycles:
                state.churn.popleft()

        if starvation is not None:
            return starvation

        symptom = self._judge(state, gated)
        if symptom is None:
            return None

        self._reset_detectors(state, position, scalar)
        return self._advance_ladder(state, symptom, path, plan)

    # --- detectors --------------------------------------------------------------

    def _judge(self, state: _TargetState, gated: float) -> Symptom | None:
        """The four gated detectors, in the order the catalogue lists them."""
        t = self.thresholds
        if gated - state.stall_at >= t.stall_window > 0:
            self._stuck(Symptom.STALL, state, gated - state.stall_at, t.stall_window)
            return Symptom.STALL

        if gated - state.improved_at >= t.stagnation_window > 0:
            self._stuck(
                Symptom.STAGNATION,
                state,
                gated - state.improved_at,
                t.stagnation_window,
            )
            return Symptom.STAGNATION

        churned = self._churned(state)
        if churned is not None:
            self._stuck(
                Symptom.PLAN_CHURN, state, float(churned), float(t.churn_repeats)
            )
            return Symptom.PLAN_CHURN

        if gated - state.timeout_from >= state.budget:
            self._stuck(
                Symptom.TARGET_TIMEOUT, state, gated - state.timeout_from, state.budget
            )
            return Symptom.TARGET_TIMEOUT
        return None

    def _churned(self, state: _TargetState) -> int | None:
        """
        Plan Churn's conjunct: a hash repeated >= R times within the buffer, AND no
        Stagnation improvement since that hash was first seen. Oscillation shows up
        as alternating hashes each reaching R; benign re-derivations keep improving
        the scalar and never satisfy the second half.
        """
        counts: dict[int, int] = {}
        first_seen: dict[int, float] = {}
        for digest, at in state.churn:
            counts[digest] = counts.get(digest, 0) + 1
            first_seen.setdefault(digest, at)
        for digest, count in counts.items():
            if count >= self.thresholds.churn_repeats and (
                state.improved_at <= first_seen[digest]
            ):
                return count
        return None

    def _observe_starvation(
        self,
        dt: float,
        plan: Sequence[_MovementComponent],
        delivered_steps: int,
        target: tuple[int, int],
    ) -> Reaction | None:
        if delivered_steps > 0 or not plan:
            self._starved = 0.0
            self._starvation_reported = False
            return None
        self._starved += dt
        if self._starved < self.thresholds.starvation_window:
            return None
        if self._starvation_reported:
            return None
        # Reported once per episode: the alert is the point, and nothing in-game
        # reacts, so re-firing every cycle would only spam the channel.
        self._starvation_reported = True
        assert self._state is not None
        self._stuck(
            Symptom.STARVATION,
            self._state,
            self._starved,
            self.thresholds.starvation_window,
        )
        return Reaction(Symptom.STARVATION, None, target)

    # --- the Reaction Ladder ------------------------------------------------------

    def _advance_ladder(
        self,
        state: _TargetState,
        symptom: Symptom,
        path: Sequence[tuple[int, int]],
        plan: Sequence[_MovementComponent],
    ) -> Reaction:
        target = state.target
        suspected = _suspect(path, plan)

        if not state.abandoned and state.reflex_count < self.thresholds.reflex_attempts:
            state.reflex_count += 1
            reaction = Reaction(
                symptom,
                Rung.REFLEX,
                target,
                suspected_connection=suspected,
                reflex_attempt=state.reflex_count,
            )
            self._react(RECOVERY_REFLEX, reaction)
            return reaction

        tally = self._abandons.get(target, 0) + 1
        if state.abandoned or tally >= self.thresholds.abandons_to_escalate:
            # Either the Abandon this ladder already issued failed to change the
            # target, or this target has been Abandoned N times across the session:
            # both are the human's problem now.
            reaction = Reaction(
                symptom,
                Rung.ESCALATE,
                target,
                suspected_connection=suspected,
                abandon_count=self._abandons.get(target, 0),
            )
            self._react(RECOVERY_ESCALATE, reaction)
            return reaction

        self._abandons[target] = tally
        state.abandoned = True
        self._abandon_pending = True
        reaction = Reaction(
            symptom,
            Rung.ABANDON,
            target,
            suspected_connection=suspected,
            abandon_count=tally,
        )
        self._react(RECOVERY_ABANDON, reaction)
        return reaction

    # --- resets -----------------------------------------------------------------

    def _retarget(
        self, target: tuple[int, int], path: Sequence[tuple[int, int]]
    ) -> None:
        """
        A new incident: the target changed, naturally (arrival, smart rotation) or
        because an Abandon dropped the old one. Either way every detector and the
        ladder position start over; only the Abandon tally survives.
        """
        if self._state is not None and not self._abandon_pending:
            self._reset_ladder(self._state, reason="target_change")
        self._abandon_pending = False
        t = self.thresholds
        state = _TargetState(target)
        state.budget = max(
            t.timeout_multiplier * t.seconds_per_node * len(path), t.timeout_floor
        )
        self._state = state

    def _reset_detectors(
        self, state: _TargetState, position: tuple[int, int], scalar: float
    ) -> None:
        """
        After a reaction is issued, every window re-accumulates from scratch - this
        is what makes cascading symptoms of one incident advance the ladder once,
        and what gives each rung time to act before the next is judged.
        """
        gated = state.gated
        state.stall_pos = position
        state.stall_at = gated
        state.improved_at = gated
        state.churn.clear()
        state.timeout_from = gated
        state.budget = max(
            self.thresholds.timeout_multiplier
            * self.thresholds.seconds_per_node
            * scalar,
            self.thresholds.timeout_floor,
        )

    def _reset_ladder(self, state: _TargetState, *, reason: str) -> None:
        if state.reflex_count == 0 and not state.abandoned:
            return  # Nothing engaged; a reset record would be noise.
        payload: LadderResetPayload = {
            "reason": reason,
            "target_x": int(state.target[0]),
            "target_y": int(state.target[1]),
        }
        self._emit(RECOVERY_LADDER_RESET, dict(payload))
        state.reflex_count = 0
        state.abandoned = False

    # --- telemetry ----------------------------------------------------------------

    def _stuck(
        self, symptom: Symptom, state: _TargetState, measure: float, threshold: float
    ) -> None:
        payload: StuckDetectedPayload = {
            "symptom": symptom.value,
            "target_x": int(state.target[0]),
            "target_y": int(state.target[1]),
            "measure": float(measure),
            "threshold": float(threshold),
        }
        self._emit(RECOVERY_STUCK_DETECTED, dict(payload))

    def _react(self, event_type: str, reaction: Reaction) -> None:
        suspected = reaction.suspected_connection
        payload: ReactionPayload = {
            "symptom": reaction.symptom.value,
            "target_x": int(reaction.target[0]),
            "target_y": int(reaction.target[1]),
            "reflex_attempt": int(reaction.reflex_attempt),
            "abandon_count": int(reaction.abandon_count),
            "suspected_movement": (
                suspected.movement_type if suspected is not None else None
            ),
            "suspected_start_x": (
                int(suspected.start[0]) if suspected is not None else None
            ),
            "suspected_start_y": (
                int(suspected.start[1]) if suspected is not None else None
            ),
            "suspected_end_x": int(suspected.end[0]) if suspected is not None else None,
            "suspected_end_y": int(suspected.end[1]) if suspected is not None else None,
        }
        self._emit(event_type, dict(payload))

    def _emit(self, event_type: str, payload: dict) -> None:
        if self._emit_fn is not None:
            self._emit_fn(event_type, payload)


def _suspect(
    path: Sequence[tuple[int, int]], plan: Sequence[_MovementComponent]
) -> SuspectedConnection | None:
    """
    The grid connection to blame: the first non-walk gesture ahead in the plan,
    located on the Path by the walk lengths before it. A plan that is nothing but
    walking blames its first component - a wall mid-platform is still a place.
    """
    components = [
        c for c in plan if c.movement_type is not MovementTypes.END_OF_MOVEMENT
    ]
    if not components or not path:
        return None
    offset = 0
    suspect = components[0]
    for component in components:
        if component.movement_type not in _WALKS:
            suspect = component
            break
        offset += component.length
    else:
        offset = 0
    start = path[min(offset, len(path) - 1)]
    end = path[min(offset + suspect.length, len(path) - 1)]
    return SuspectedConnection(
        (int(start[0]), int(start[1])),
        (int(end[0]), int(end[1])),
        suspect.movement_type.name,
    )
