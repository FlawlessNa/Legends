"""
The Stuck detectors and the Reaction Ladder, driven by fed position/Path/clock
streams.

`CONTEXT.md` -> **Movement recovery**. The whole point of the `StuckMonitor` seam
is that this file exists: the monitor is handed a position, a clock reading, a
target, a Path, a Movement Plan and a delivered-Step count, and every symptom's
firing and every rung's advance is decidable offline. Nothing here touches a
client, and nothing here is an Expectation - the thresholds are *supplied* by each
test, because their real values are issue #120's to fit.

Each test disables the detectors it is not about by pushing their windows out of
reach. That is deliberate rather than incidental: five detectors watching one
stream will otherwise race, and a test that passes because a *different* symptom
fired first is worse than no test.
"""

from collections.abc import Mapping, Sequence

import pytest

from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.movement_recovery import (
    Reaction,
    RecoveryThresholds,
    Rung,
    StuckMonitor,
    Symptom,
)
from maple.telemetry_events import (
    RECOVERY_ABANDON,
    RECOVERY_ESCALATE,
    RECOVERY_LADDER_RESET,
    RECOVERY_REFLEX,
    RECOVERY_STUCK_DETECTED,
)

#: Big enough that a detector carrying it never fires within a test's horizon.
NEVER = 1e9

WALK = (_MovementComponent(MovementTypes.WALK_RIGHT, 5),)
PATH = tuple((x, 0) for x in range(10))


def _thresholds(**overrides: float) -> RecoveryThresholds:
    """
    Every detector switched off, so a test switches on only the one it is about.
    """
    base = {
        "stall_window": NEVER,
        "stagnation_window": NEVER,
        "churn_repeats": 10**6,
        "timeout_multiplier": NEVER,
        "timeout_floor": NEVER,
        "starvation_window": NEVER,
    }
    base.update(overrides)
    return RecoveryThresholds(**base)


class _Monitor:
    """
    A `StuckMonitor` plus the clock and the telemetry tape a test reads back.

    `tick`'s keywords mirror `observe`'s one for one rather than going through a
    `**kwargs` bag: a test that misspells `delivered_steps` would otherwise
    silently exercise the default and pass for the wrong reason.
    """

    def __init__(self, thresholds: RecoveryThresholds) -> None:
        self.events: list[tuple[str, Mapping[str, object]]] = []
        self.monitor = StuckMonitor(
            thresholds, emit=lambda e, p: self.events.append((e, p))
        )
        self.now = 0.0
        self.target: tuple[int, int] = (100, 0)
        self.plan: tuple[_MovementComponent, ...] = WALK
        self.delivered_steps = 3

    def tick(
        self,
        position: tuple[int, int] = (0, 0),
        *,
        dt: float = 0.5,
        path: Sequence[tuple[int, int]] = PATH,
        plan: tuple[_MovementComponent, ...] | None = None,
        delivered_steps: int | None = None,
        position_valid: bool = True,
        on_expected_minimap: bool = True,
        alive: bool = True,
    ) -> Reaction | None:
        """One decision cycle, `dt` seconds after the last."""
        self.now += dt
        return self.monitor.observe(
            position,
            self.now,
            target=self.target,
            path=path,
            plan=self.plan if plan is None else plan,
            delivered_steps=(
                self.delivered_steps if delivered_steps is None else delivered_steps
            ),
            position_valid=position_valid,
            on_expected_minimap=on_expected_minimap,
            alive=alive,
        )

    def run(self, cycles: int, **kwargs: object) -> Reaction | None:
        """Cycles until one produces a reaction, or the count runs out."""
        for _ in range(cycles):
            reaction = self.tick(**kwargs)  # pyright: ignore[reportArgumentType]
            if reaction is not None:
                return reaction
        return None

    def fire(self, cycles: int = 10, **kwargs: object) -> Reaction:
        """`run`, for the tests that are asserting a symptom *did* fire."""
        reaction = self.run(cycles, **kwargs)
        assert reaction is not None, f"nothing fired within {cycles} cycles"
        return reaction

    def types(self, *wanted: str) -> list[str]:
        return [e for e, _ in self.events if not wanted or e in wanted]


@pytest.fixture
def stalling() -> _Monitor:
    """A loop delivering Steps and going nowhere: Stall's own shape."""
    return _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0))


# --- the five symptoms ------------------------------------------------------


def test_stall_fires_when_a_delivering_loop_does_not_move(stalling: _Monitor) -> None:
    reaction = stalling.run(6)

    assert reaction is not None
    assert reaction.symptom is Symptom.STALL


def test_stall_tolerates_jitter_but_not_real_movement() -> None:
    """
    The bound is what the retired raw-equality sentinels lacked. A character
    pinned at a wall while mob knockback jitters its coordinates never tripped
    them, precisely because the coordinates kept *changing* - so the positions
    fed here have to wobble, cycle to cycle, the way a real reading does. A
    detector comparing successive readings for equality sees six moves and never
    fires; one measuring displacement from where the character actually was sees
    none.
    """
    wobble = [(0, 0), (1, 0), (0, 1), (1, 1), (1, 0), (0, 1), (1, 1), (0, 0)]

    jittering = _Monitor(_thresholds(stall_window=1.0, jitter_bound=2.0))
    assert any(jittering.tick(spot) for spot in wobble)

    walking = _Monitor(_thresholds(stall_window=1.0, jitter_bound=2.0))
    assert not any(walking.tick((step * 5, 0)) for step in range(1, 9))


def test_stagnation_fires_when_the_remaining_path_stops_shrinking() -> None:
    """
    Measured on the recomputed Path, never on distance-to-target - so walking
    *away* from the target to reach a ladder is not Stagnation.
    """
    detouring = _Monitor(_thresholds(stagnation_window=1.0, progress_epsilon=1.0))

    # The character moves steadily away from the target, and the Path shortens
    # anyway: that is a legitimate detour, and nothing fires.
    for step in range(1, 7):
        away = (-step * 10, 0)
        assert detouring.tick(away, path=PATH[step:]) is None

    stuck = _Monitor(_thresholds(stagnation_window=1.0, progress_epsilon=1.0))
    reaction = stuck.run(6, position=(0, 0))
    assert reaction is not None
    assert reaction.symptom is Symptom.STAGNATION


def test_plan_churn_fires_on_a_plan_re_derived_from_one_place() -> None:
    churning = _Monitor(_thresholds(churn_repeats=3, churn_cycles=8, churn_quantum=2))

    reaction = churning.run(6)

    assert reaction is not None
    assert reaction.symptom is Symptom.PLAN_CHURN


def test_plan_churn_ignores_a_plan_re_derived_while_the_path_shrinks() -> None:
    """
    The conjunct. Re-deriving the same plan is normal - the loop does it every
    cycle - and only becomes churn once the remaining Path stops shrinking too.
    """
    progressing = _Monitor(
        _thresholds(churn_repeats=3, churn_cycles=8, progress_epsilon=1.0)
    )

    reactions = [
        progressing.tick((0, 0), path=PATH[: len(PATH) - step]) for step in range(6)
    ]

    assert not any(reactions)


def test_plan_churn_is_behind_the_gate_like_every_other_detector() -> None:
    """
    Re-deriving one plan from one spot while nothing is being sent is the loop
    waiting its turn behind a cast, not the loop churning. Churn's own conjunct
    cannot catch this - the remaining Path is not shrinking either, because the
    character is not moving - so the ring buffer has to be gated too.
    """
    waiting = _Monitor(_thresholds(churn_repeats=3, churn_cycles=8))

    reactions = [waiting.tick(delivered_steps=0) for _ in range(10)]

    assert not any(reactions)


def test_target_timeout_fires_however_the_character_is_moving() -> None:
    """The backstop: it holds when a bad grid connection makes the Path lie."""
    timing_out = _Monitor(
        _thresholds(timeout_multiplier=1.0, seconds_per_node=0.1, timeout_floor=1.0)
    )

    # Moving the whole time, and the Path shrinking: every finer detector is blind.
    reaction = None
    for step in range(1, 8):
        reaction = timing_out.tick((step * 10, 0), path=PATH[: max(1, 9 - step)])
        if reaction is not None:
            break

    assert reaction is not None
    assert reaction.symptom is Symptom.TARGET_TIMEOUT


def test_starvation_reports_a_plan_that_never_reaches_the_client() -> None:
    starving = _Monitor(_thresholds(starvation_window=1.0))

    reaction = starving.run(6, delivered_steps=0)

    assert reaction is not None
    assert reaction.symptom is Symptom.STARVATION


def test_starvation_changes_nothing_in_game_and_reports_once() -> None:
    """
    Telemetry and an alert only: nothing about the map is wrong, so there is no
    rung to climb - and re-reporting every cycle would only spam the channel.
    """
    starving = _Monitor(_thresholds(starvation_window=1.0))

    reactions = [starving.tick(delivered_steps=0) for _ in range(10)]
    reported = [r for r in reactions if r is not None]

    assert len(reported) == 1
    assert reported[0].rung is None


# --- the Delivery Gate ------------------------------------------------------


def test_the_gate_stops_the_clocks_while_nothing_is_delivered() -> None:
    """
    The load-bearing move. A character casting in place for the whole window
    tripped the retired sentinels; here the clock never advances, so the
    false positive is gone by construction rather than tuned around.
    """
    casting = _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0))

    reactions = [casting.tick(delivered_steps=0) for _ in range(20)]

    assert not any(reactions)


def test_the_gate_charges_only_the_cycles_that_delivered() -> None:
    """
    Not merely "delivery resets the clock" - the gated cycles accumulate across
    the undelivered ones in between, so a loop that manages one Action in three
    still reaches the threshold, three times slower.
    """
    intermittent = _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0))

    for _ in range(4):
        assert intermittent.tick(delivered_steps=0) is None
    reactions = [intermittent.tick(delivered_steps=2) for _ in range(3)]

    assert any(reactions)


def test_an_unplannable_loop_is_judged_even_though_it_delivers_nothing() -> None:
    """
    Where delivery is the wrong proxy for control. A loop that can plan nothing
    sends nothing, so a gate reading delivery alone would freeze every clock
    exactly when the character is most thoroughly stuck - the case the retired
    `no_path` sentinel existed for. Starvation covers the opposite pairing, so
    the two partition rather than overlap.
    """
    pathless = _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0))

    reaction = pathless.run(6, plan=(), path=(), delivered_steps=0)

    assert reaction is not None
    assert reaction.symptom is Symptom.STALL


# --- look-alike guards ------------------------------------------------------


@pytest.mark.parametrize("guard", ["position_valid", "on_expected_minimap", "alive"])
def test_each_guard_freezes_every_clock(guard: str, stalling: _Monitor) -> None:
    """
    A bot that cannot see is not a bot that is stuck. Each guard is first-class
    (#119) even where the signal behind it is still owned elsewhere.
    """
    reactions = [
        stalling.tick(**{guard: False})  # pyright: ignore[reportArgumentType]
        for _ in range(20)
    ]

    assert not any(reactions)


def test_a_guard_that_clears_does_not_forfeit_the_time_it_froze(
    stalling: _Monitor,
) -> None:
    blind = [stalling.tick(position_valid=False) for _ in range(10)]
    assert not any(blind)

    assert stalling.run(6) is not None


# --- the Reaction Ladder ----------------------------------------------------


@pytest.fixture
def climbing() -> _Monitor:
    """A Stall that keeps firing, so the ladder has to keep answering."""
    return _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0, reflex_attempts=2))


def _rungs(monitor: _Monitor, firings: int) -> list[Rung | None]:
    rungs = []
    for _ in range(firings):
        rungs.append(monitor.fire().rung)
    return rungs


def test_the_ladder_climbs_reflex_then_abandon_then_escalate(
    climbing: _Monitor,
) -> None:
    assert _rungs(climbing, 4) == [
        Rung.REFLEX,
        Rung.REFLEX,
        Rung.ABANDON,
        Rung.ESCALATE,
    ]


def test_one_incident_advances_the_ladder_once_per_firing(climbing: _Monitor) -> None:
    """
    Every window re-accumulates after a reaction is issued, which is what gives
    each rung time to act before the next is judged - and what stops cascading
    symptoms of one incident from climbing the whole ladder in a single cycle.
    """
    first = climbing.run(10)
    assert first is not None
    assert first.rung is Rung.REFLEX

    # The very next cycle cannot fire again: the Stall window restarted.
    assert climbing.tick() is None


def _reset_reasons(monitor: _Monitor) -> list[str]:
    return [str(p["reason"]) for e, p in monitor.events if e == RECOVERY_LADDER_RESET]


def test_real_progress_resets_the_ladder(climbing: _Monitor) -> None:
    assert _rungs(climbing, 2) == [Rung.REFLEX, Rung.REFLEX]

    # The Path shortens: the character is genuinely on its way again.
    climbing.tick((50, 0), path=PATH[:4])

    assert climbing.fire().rung is Rung.REFLEX
    assert _reset_reasons(climbing) == ["progress"]


def test_a_natural_target_change_resets_the_ladder(climbing: _Monitor) -> None:
    """
    The rung goes back to Reflex by construction - a new target is a new
    incident, with its own state. What is worth pinning beyond that is the
    *record*: an analyzer reading a ladder that reached Abandon and then went
    quiet needs to know whether the loop recovered or simply wandered off.
    """
    assert _rungs(climbing, 2) == [Rung.REFLEX, Rung.REFLEX]

    climbing.target = (200, 0)

    assert climbing.fire().rung is Rung.REFLEX
    assert _reset_reasons(climbing) == ["target_change"]


def test_an_abandon_is_not_recorded_as_a_natural_target_change(
    climbing: _Monitor,
) -> None:
    """
    Abandon changes the target itself, so the retarget that follows is the
    ladder's own doing. Recording it as a natural change would tell an analyzer
    the loop recovered when what actually happened is that it gave up.
    """
    assert _rungs(climbing, 3) == [Rung.REFLEX, Rung.REFLEX, Rung.ABANDON]

    climbing.target = (200, 0)
    climbing.tick()

    assert "target_change" not in _reset_reasons(climbing)


def test_abandoning_the_same_target_enough_times_escalates() -> None:
    """
    The config-failure signature: the per-target tally survives both resets, so
    N Abandons of one target escalate however much progress happened between
    them.
    """
    repeating = _Monitor(
        _thresholds(
            stall_window=1.0,
            jitter_bound=1.0,
            reflex_attempts=0,
            abandons_to_escalate=3,
        )
    )
    rungs = []
    for round_ in range(3):
        # A fresh incident each time: the rotation wandered off and came back.
        repeating.target = (999, round_)
        repeating.run(10)
        repeating.target = (100, 0)
        rungs.append(repeating.fire().rung)

    assert rungs == [Rung.ABANDON, Rung.ABANDON, Rung.ESCALATE]


def test_an_abandon_that_did_not_change_the_target_escalates(
    climbing: _Monitor,
) -> None:
    """
    Abandon's contract is that the loop stops heading there. A ladder that is
    asked again while still aimed at the target it abandoned has nothing left
    to try.
    """
    assert _rungs(climbing, 3) == [Rung.REFLEX, Rung.REFLEX, Rung.ABANDON]

    assert climbing.fire().rung is Rung.ESCALATE


# --- attribution ------------------------------------------------------------


def test_the_suspected_connection_is_the_first_gesture_ahead(
    stalling: _Monitor,
) -> None:
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 3),
        _MovementComponent(MovementTypes.JUMP, 1),
        _MovementComponent(MovementTypes.WALK_RIGHT, 2),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
    )

    reaction = stalling.fire(6, plan=plan)

    suspect = reaction.suspected_connection
    assert suspect is not None
    assert suspect.movement_type == "JUMP"
    assert (suspect.start, suspect.end) == (PATH[3], PATH[4])


def test_a_plan_that_is_only_walking_blames_where_it_started(
    stalling: _Monitor,
) -> None:
    """A wall mid-platform is still a place worth naming."""
    reaction = stalling.fire(6, plan=WALK)

    suspect = reaction.suspected_connection
    assert suspect is not None
    assert suspect.movement_type == "WALK_RIGHT"
    assert suspect.start == PATH[0]


def test_attribution_survives_a_path_shorter_than_the_plan_claims(
    stalling: _Monitor,
) -> None:
    """Indexing off the end would raise inside the thing that is recovering."""
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 50),
        _MovementComponent(MovementTypes.JUMP, 50),
    )

    reaction = stalling.fire(6, plan=plan, path=PATH[:2])

    assert reaction.suspected_connection is not None


# --- telemetry --------------------------------------------------------------


def test_every_firing_records_the_symptom_it_was(stalling: _Monitor) -> None:
    stalling.run(6)

    detections = [p for e, p in stalling.events if e == RECOVERY_STUCK_DETECTED]
    assert len(detections) == 1
    assert detections[0]["symptom"] == "stall"
    measure, threshold = detections[0]["measure"], detections[0]["threshold"]
    assert isinstance(measure, float)
    assert isinstance(threshold, float)
    assert measure >= threshold


def test_every_rung_records_itself(climbing: _Monitor) -> None:
    _rungs(climbing, 4)

    assert climbing.types(RECOVERY_REFLEX, RECOVERY_ABANDON, RECOVERY_ESCALATE) == [
        RECOVERY_REFLEX,
        RECOVERY_REFLEX,
        RECOVERY_ABANDON,
        RECOVERY_ESCALATE,
    ]


def test_payloads_carry_json_primitives_only(stalling: _Monitor) -> None:
    """
    An analyzer is written against these, and a `MovementTypes` or a tuple
    reaching the transport is a record nobody can read back.
    """
    stalling.run(6)

    for _, payload in stalling.events:
        for key, value in payload.items():
            assert value is None or type(value) in (int, float, str), (
                f"{key} is a {type(value).__name__}"
            )


def test_the_abandon_record_names_the_suspected_connection(climbing: _Monitor) -> None:
    _rungs(climbing, 3)

    abandon = next(p for e, p in climbing.events if e == RECOVERY_ABANDON)
    assert abandon["suspected_movement"] == "WALK_RIGHT"
    assert abandon["abandon_count"] == 1


def test_a_ladder_that_never_engaged_records_no_reset() -> None:
    """A reset record per cycle would drown the ones that mean something."""
    healthy = _Monitor(_thresholds(stall_window=1.0, jitter_bound=1.0))

    for step in range(1, 8):
        healthy.tick((step * 10, 0), path=PATH[: max(1, 9 - step)])

    assert healthy.types() == []
