"""
Groups A, B, C, D and E of the offline invariant catalogue
(`docs/planning/movement-invariant-catalogue.md`), run over the **whole** movement-lab
Corpus rather than over a hand-built plan.

`corpus.plans(entry)` stops at the Movement Plan - compiling it into an Input Sequence
is this ticket's (issue #104), so every check below calls `compile_movements` itself.
Each check is a set/interval operation over Steps already produced, or over the
`Hold`s `KeyboardInputWrapper.holds` derives from them, so sweeping every record and
every cancel point stays cheap: no real delay is ever awaited here, `compile_movements`
never sends anything.

**A red function here is a finding, not a bug in the lab** - the catalogue already
records A2 and D1 as *fails*, tied to issue #113. The lab is what turns "the case a
hand-built plan happened to exercise" into "however often this actually happens across
nine maps and ~2,100 sampled routes."

Groups C (Continuation) and D (Preemption) do not drive real `asyncio` cancellation:
both invariants reduce to set operations over Holds and `forced_key_releases` once the
mechanism they describe is fixed, and that mechanism (`focused_inputs`'s `finally`
block; see `botting/controller/inputs/focused_inputs.py`) is already exercised for real
by `tests/test_botting/test_preemption_direction_release.py`. Re-deriving its formula
here, against real corpus-scale compiled sequences instead of hand-built ones, is what
stays inside the suite's time budget while still sweeping every cancel point of every
sampled route exhaustively, per the catalogue's own "each check is a set operation over
the already-derived Holds" reasoning for D1.
"""

from __future__ import annotations

import itertools
import math
import warnings
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import cache, lru_cache

import pytest

from botting.controller.inputs.focused_inputs import (
    NO_COMPONENT,
    KeyboardInputWrapper,
)
from botting.controller.inputs.held_keys_ledger import InputState
from botting.controller.inputs.inputs_helpers import DELAY, OVERHEAD
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    compile_movements,
)
from tests.test_maple.movement_lab import corpus

DIRECTIONS = frozenset({"left", "right", "up", "down"})
OPPOSITES = {"left": "right", "right": "left", "up": "down", "down": "up"}
NOBODY = InputState(frozenset())

# The components B1 calls atomic: an in-game gesture a cut splits rather than shortens.
ATOMIC = frozenset(
    {
        MovementTypes.JUMP,
        MovementTypes.JUMP_LEFT,
        MovementTypes.JUMP_RIGHT,
        MovementTypes.JUMP_DOWN,
        MovementTypes.ENTER_PORTAL,
        MovementTypes.TELEPORT_LEFT,
        MovementTypes.TELEPORT_RIGHT,
        MovementTypes.TELEPORT_UP,
        MovementTypes.TELEPORT_DOWN,
    }
)

# Matches `Rotation`'s and `TrialRunner`'s production default
# (`maple/decision_makers/rotation.py`'s `movements_duration`,
# `maple/decision_makers/trial_runner.py::DEFAULT_ACTION_DURATION`) - the Action
# duration cap essentially every live movement compiles against.
ACTION_DURATION = 1.0

# `random_delay` yields `uniform(0.95, 1.05) * DELAY` - the most a single Step's delay
# can cost, which is what B2 and B5 bound the fill's overshoot by.
MAX_DELAY = 1.05 * DELAY


@dataclass(frozen=True)
class _StubTeleportSkill(MapleSkill):
    """
    A `Skill` whose key bind does not go through the gitignored keybindings config -
    same shape as `tests/test_botting/test_telecast.py`'s `_StubSkill`.

    `corpus.handler()` carries no Teleport skill - `path_into_movements` never needs
    one, only `compile_movements` does - so compiling a plan that contains a
    `TELEPORT_*` component (only `teleport_shaft` and `GhostShip1` sample any) needs
    one supplied here instead.
    """

    key: str = field(default="insert", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


_TELEPORT_SKILL = _StubTeleportSkill("Teleport", "Movement", animation_time=0.15)


def compile_record(
    record: corpus.PlanRecord,
    grid: MinimapGrid,
    *,
    initial_state: InputState | None = NOBODY,
    total_duration: float | None = None,
) -> KeyboardInputWrapper | None:
    """
    A record's Movement Plan compiled into an Input Sequence - the step `corpus.py`
    deliberately stops short of. `None` for an unreachable pair's empty plan, exactly
    as `compile_movements` itself would return for an empty `movements`.
    """
    if not record.movements:
        return None
    return compile_movements(
        initial_state,
        movements=record.movements,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=grid.speed,
        teleport=_TELEPORT_SKILL,
        total_duration=total_duration,
    )


def _reachable_records(
    plans: Iterable[corpus.PlanRecord],
) -> Iterator[corpus.PlanRecord]:
    return (record for record in plans if record.path)


def _reachable(
    plans: Iterable[corpus.PlanRecord],
) -> Iterator[tuple[int, corpus.PlanRecord]]:
    return ((i, record) for i, record in enumerate(plans) if record.path)


@cache
def _compiled(
    corpus_map: corpus.CorpusMap, index: int, total_duration: float | None = None
) -> KeyboardInputWrapper | None:
    """
    `compile_record` memoized on the record's position in its map's frozen sample.

    Every Invariant test below compiles the same ~2,100 records independently; without
    this, each one gets recompiled once per test function (fifteen-odd times over,
    for the full, `NOBODY`-initial compile every group but C wants). `corpus.plans`
    itself is `@cache`d and its order stable, so `(corpus_map, index)` names one record
    as reliably as the pair itself would.
    """
    record = corpus.plans(corpus_map)[index]
    return compile_record(
        record, corpus.grid(corpus_map), total_duration=total_duration
    )


def _batches(wrapper: KeyboardInputWrapper) -> list[list[tuple[str, str]]]:
    """Each Step as a list of `(key, event)` pairs - single-key Steps included."""
    batches = []
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list):
            batches.append(list(zip(keys, events)))
        else:
            batches.append([(keys, events)])
    return batches


class _Walk:
    """
    One traversal of a compiled Input Sequence's Steps, computing every quantity
    Groups A and D need from `down(i-1)` and `own(i-1)`: A6, A7, D1 and D2 all read the
    state *entering* a Step, so one pass fills every violation list at once instead of
    re-deriving `down`/`own` per invariant.
    """

    def __init__(self, wrapper: KeyboardInputWrapper) -> None:
        self.wrapper = wrapper
        self.phantom_releases: list[tuple[int, str]] = []
        self.illegal_repeats: list[tuple[int, str]] = []
        self.d1_violations: list[tuple[int, str]] = []
        # down(k-1) for every cancel point k in [0, n] - index k.
        self.cancel_points: list[frozenset[str]] = []

        down: set[str] = set(
            wrapper.initial_state.held_keys if wrapper.initial_state else ()
        )
        owner = wrapper.initial_state.typematic_owner if wrapper.initial_state else None
        forced = set(wrapper.forced_key_releases)

        for i, batch in enumerate(_batches(wrapper)):
            self.cancel_points.append(frozenset(down))
            bad = {k for k in down if k not in forced and k not in DIRECTIONS}
            if bad:
                self.d1_violations.append((i, min(bad)))
            for key, event in batch:
                if event == "keydown":
                    if key in down and owner != key:
                        self.illegal_repeats.append((i, key))
                    down.add(key)
                    owner = key
                elif event == "keyup":
                    if key not in down:
                        self.phantom_releases.append((i, key))
                    down.discard(key)
                    if owner == key:
                        owner = None
        self.cancel_points.append(frozenset(down))
        bad = {k for k in down if k not in forced and k not in DIRECTIONS}
        if bad:
            self.d1_violations.append((len(wrapper.keys), min(bad)))


def _post_cancel_held(down: frozenset[str], forced: Iterable[str]) -> frozenset[str]:
    """
    What `focused_inputs`'s cancellation path leaves down, computed directly from a
    `down(k-1)` snapshot rather than by driving a real cancelled task: the `finally`
    block (`botting/controller/inputs/focused_inputs.py`) releases every forced key
    still held, and on the cancellation path only, every direction key still held.
    """
    return down - set(forced) - (down & DIRECTIONS)


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# --- A - Input Sequence, structural -------------------------------------------------


def test_a1_shape(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        if not (len(wrapper.keys) == len(wrapper.events) == len(wrapper.delays)):
            violations.append((record.pair.start, record.pair.end, "length mismatch"))
            continue
        for keys, events in zip(wrapper.keys, wrapper.events):
            both_str = isinstance(keys, str) and isinstance(events, str)
            both_list = (
                isinstance(keys, list)
                and isinstance(events, list)
                and len(keys) == len(events)
            )
            if not (both_str or both_list):
                violations.append((record.pair.start, record.pair.end, (keys, events)))
    assert not violations, (
        f"A1 Shape: {len(violations)} violation(s), first {violations[0]}"
    )


def test_a2_terminal_release(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """Only checkable on a sequence that was **not** truncated - the full compile."""
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        leftover = wrapper.keys_held - set(wrapper.forced_key_releases)
        if leftover:
            violations.append((record.pair.start, record.pair.end, sorted(leftover)))
    assert not violations, (
        f"A2 Terminal Release: {len(violations)} violation(s) - known, issue #113. "
        f"First: {violations[0] if violations else None}"
    )


def test_a3_no_opposing_overlap(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        holds = wrapper.holds
        for left, right in (("left", "right"), ("up", "down")):
            for a in holds.get(left, ()):
                for b in holds.get(right, ()):
                    if _overlaps(a, b):
                        violations.append(
                            (record.pair.start, record.pair.end, left, right, a, b)
                        )
    assert not violations, f"A3 No Opposing Overlap: first {violations[0]}"


def test_a4_skill_key_closure(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        for key, intervals in wrapper.holds.items():
            if key in DIRECTIONS:
                continue
            for t_down, t_up in intervals:
                if not t_up < wrapper.duration:
                    violations.append((record.pair.start, record.pair.end, key, t_up))
    assert not violations, f"A4 Skill Key Closure: first {violations[0]}"


def test_a5_delays(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        bad = [d for d in wrapper.delays if not (math.isfinite(d) and d >= 0)]
        if bad:
            violations.append((record.pair.start, record.pair.end, bad[0]))
    assert not violations, f"A5 Delays: first {violations[0]}"


def test_a6_no_phantom_release(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        walk = _Walk(wrapper)
        if walk.phantom_releases:
            violations.append(
                (record.pair.start, record.pair.end, walk.phantom_releases[0])
            )
    assert not violations, f"A6 No Phantom Release: first {violations[0]}"


def test_a7_typematic_legality(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        walk = _Walk(wrapper)
        if walk.illegal_repeats:
            violations.append(
                (record.pair.start, record.pair.end, walk.illegal_repeats[0])
            )
    assert not violations, f"A7 Typematic Legality: first {violations[0]}"


# --- B - Movement Plan / Input Sequence consistency ---------------------------------


def test_b1_truncation_integrity(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """
    Whether the cut, taken at production's own `ACTION_DURATION`, ever lands inside an
    atomic (`JUMP*`/`TELEPORT*`/`ENTER_PORTAL`) component rather than on a boundary -
    checkable at all only because Provenance (`wrapper.origins`, issue #102) survives
    `truncate`.
    """
    violations = []
    for i, record in _reachable(corpus_plans):
        full = _compiled(corpus_map, i)
        cut = _compiled(corpus_map, i, ACTION_DURATION)
        if full is None or cut is None:
            continue
        before = Counter(o for o in full.origins if o != NO_COMPONENT)
        after = Counter(o for o in cut.origins if o != NO_COMPONENT)
        for origin, kept in after.items():
            if (
                kept < before[origin]
                and record.movements[origin].movement_type in ATOMIC
            ):
                violations.append(
                    (
                        record.pair.start,
                        record.pair.end,
                        record.movements[origin].movement_type.name,
                    )
                )
                break
    assert not violations, (
        f"B1 Truncation Integrity: {len(violations)}/{sum(1 for _ in _reachable_records(corpus_plans))} "
        f"route(s) cut mid-gesture at ACTION_DURATION={ACTION_DURATION}s - known, "
        f"the fix waits on knowing where cuts land (issue #102). First: {violations[0] if violations else None}"
    )


def test_b2_fill_bound(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """
    Literally as the catalogue states it: the elapsed cost of every Step Provenance
    attributes to this walk component, against `L / grid.speed`.

    The catalogue's own note under B2 already flags the reason this does not hold
    everywhere: "release Steps inserted ahead of a component consume budget without
    extending the direction's Hold... if that gap turns out to matter, it becomes its
    own entry." A walk next to a `CLIMB_UP`/`CLIMB_DOWN`/`ENTER_PORTAL` transition, or
    one that has to clear an opposite direction on entry, is exactly that gap: `move`'s
    pre-press release Steps and secondary-direction press are real Steps this
    component's Provenance owns, and only `fill`'s own silent branch ever discounts
    for them - the ordinary press-and-repeat path does not. This run turns that
    "if" into a measured "how often".
    """
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        spent: dict[int, float] = {}
        for origin, delay in zip(wrapper.origins, wrapper.delays):
            spent[origin] = spent.get(origin, 0.0) + delay + OVERHEAD
        for origin, component in enumerate(record.movements):
            if component.movement_type not in (
                MovementTypes.WALK_LEFT,
                MovementTypes.WALK_RIGHT,
            ):
                continue
            budget = component.length / corpus_grid.speed
            elapsed = spent.get(origin, 0.0)
            # `budget` and `elapsed` sum the same per-Step delays in a different order
            # (one division here, an accumulation of individually-jittered delays in
            # `fill`), so floating-point addition's non-associativity alone can put
            # `elapsed` a few ULPs under `budget` with no Step actually missing.
            if not (budget - 1e-9 <= elapsed < budget + MAX_DELAY + OVERHEAD):
                violations.append(
                    (record.pair.start, record.pair.end, origin, budget, elapsed)
                )
    assert not violations, (
        f"B2 Fill Bound: {len(violations)} walk component(s) whose Provenance-owned "
        f"Steps fall outside [L/speed, L/speed + max_delay + OVERHEAD) - the gap the "
        f"catalogue's own B2 note anticipated. First: {violations[0] if violations else None}"
    )


def test_b3_distance_fidelity_needs_a_live_client() -> None:
    pytest.skip(
        "B3 Distance Fidelity is an Expectation gated on calibration - #13/#14."
    )


def test_b4_component_non_empty(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """
    An Expectation: reported, not gating (catalogue). Every component up to the cut
    should produce a Step unless its direction was already held at its own start.
    """
    silent = 0
    checked = 0
    for i, record in _reachable(corpus_plans):
        cut = _compiled(corpus_map, i, ACTION_DURATION)
        if cut is None:
            continue
        produced = {o for o in cut.origins if o != NO_COMPONENT}
        for origin, component in enumerate(record.movements[:-1]):
            if origin not in {o for o in cut.origins}:
                continue  # never reached by the cut
            checked += 1
            if origin not in produced:
                silent += 1
    if silent:
        warnings.warn(
            f"B4 Component Non-empty (Expectation, not gating): {silent}/{checked} "
            f"reached component(s) in {corpus_map.name} produced no Step.",
            stacklevel=1,
        )


def test_b5_cast_window() -> None:
    """
    No fixture map in the Corpus samples a `cast_skill` component - only rotation's
    skill-casting DecisionMakers build one, and the movement lab's plans come solely
    from `path_into_movements`. B5 stays covered at the unit level
    (`tests/test_botting/test_cast_window.py`); nothing in the Corpus exercises it.
    """
    pytest.skip("No cast_skill component reaches the movement lab's Corpus.")


def test_b6_repeat_cadence_needs_a_live_client() -> None:
    pytest.skip(
        "B6 Repeat Cadence is an Expectation against the client's measured typematic "
        "timing, not decidable from a compiled sequence alone."
    )


# --- C - Continuation pair -----------------------------------------------------------


def _post_completion_state(wrapper: KeyboardInputWrapper) -> InputState:
    """
    The Held-Keys Ledger state a Continuation hands to the next compile: every forced
    key still held is released in `focused_inputs`'s `finally` block on normal
    completion too, and any release - forced or not - drops typematic ownership
    outright (`get_typematic_owner`'s rule). `wrapper.holds` gives the still-open
    interval an owner's ownership carries from, which is what `owner_elapsed` is.
    """
    released = wrapper.keys_held & set(wrapper.forced_key_releases)
    held = wrapper.keys_held - released
    owner = wrapper.typematic_owner
    owner_elapsed = 0.0
    if owner in released:
        owner = None
    elif owner is not None:
        t_down = wrapper.holds[owner][-1][0]
        owner_elapsed = wrapper.duration - t_down
    return InputState(frozenset(held), owner, owner_elapsed)


def _continuation_pairs(
    plans: Iterable[corpus.PlanRecord],
) -> Iterator[tuple[int, int, corpus.PlanRecord, corpus.PlanRecord]]:
    """
    Consecutive reachable records in the frozen sample, treated as back-to-back
    rotation Actions `N` and `N+1` - the corpus does not promise `N`'s end is `N+1`'s
    start, but every Continuation invariant is about what the compiler and the ledger
    carry across the boundary, not about whether the route made spatial sense.

    Both raw indices (not positions among the reachable-only subset) are what
    `_continuation_compile` needs to cache on, alongside `_compiled`'s own.
    """
    reachable = list(_reachable(plans))
    return (
        (i, j, record, next_record)
        for (i, record), (j, next_record) in itertools.pairwise(reachable)
    )


@cache
def _continuation_compile(
    corpus_map: corpus.CorpusMap, n_index: int, n_plus_1_index: int
) -> tuple[InputState, KeyboardInputWrapper | None] | None:
    """
    `N+1` compiled against the `InputState` `N`'s completion hands it - shared by C1,
    C2 and C3 rather than recompiled once per test, since the only input that varies
    between them is what each one goes on to check about the result.

    `N` compiles at `ACTION_DURATION`, not the untruncated full sequence: rotation
    passes `total_duration` on every Action, so "N reached its end" means its own
    budget, not a natural stop - truncation is the case that actually carries a
    direction across the boundary (the catalogue's C3 note: "it happens on
    truncation, where the end-of-sequence release does not run at all"). An
    untruncated `N` runs its own terminal release first, which empties `keys_held`
    of everything not forced and would make every Continuation pair here trivial.
    """
    full = _compiled(corpus_map, n_index, ACTION_DURATION)
    if full is None:
        return None
    h0 = _post_completion_state(full)
    n_plus_1 = corpus.plans(corpus_map)[n_plus_1_index]
    compiled = compile_record(n_plus_1, corpus.grid(corpus_map), initial_state=h0)
    return h0, compiled


def test_c1_inherited_state_agreement(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, j, n, n_plus_1 in _continuation_pairs(corpus_plans):
        result = _continuation_compile(corpus_map, i, j)
        if result is None:
            continue
        expected, compiled = result
        if compiled is None:
            continue
        if compiled.initial_state != expected:
            violations.append((n.pair, n_plus_1.pair))
    assert not violations, f"C1 Inherited State Agreement: first {violations[0]}"


def test_c2_boundary_opposing_release(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, j, n, n_plus_1 in _continuation_pairs(corpus_plans):
        result = _continuation_compile(corpus_map, i, j)
        if result is None:
            continue
        h0, compiled = result
        if compiled is None:
            continue
        for direction in DIRECTIONS & h0.held_keys:
            opposite = OPPOSITES[direction]
            steps = list(zip(compiled.keys, compiled.events))
            pressed_at = next(
                (
                    i
                    for i, (k, e) in enumerate(steps)
                    if (k == opposite and e == "keydown")
                    or (isinstance(k, list) and opposite in k and "keydown" in e)
                ),
                None,
            )
            if pressed_at is None:
                continue
            released_before = any(
                (k == direction and e == "keyup")
                or (isinstance(k, list) and direction in k and "keyup" in e)
                for k, e in steps[: pressed_at + 1]
            )
            if not released_before:
                violations.append((n.pair, n_plus_1.pair, direction))
    assert not violations, f"C2 Boundary Opposing Release: first {violations[0]}"


def test_c3_no_inherited_stuck_key(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, j, n, n_plus_1 in _continuation_pairs(corpus_plans):
        result = _continuation_compile(corpus_map, i, j)
        if result is None:
            continue
        h0, compiled = result
        if compiled is None:
            continue
        first_component_directions = {
            d
            for d in DIRECTIONS
            if n_plus_1.movements
            and n_plus_1.movements[0].movement_type.name.split("_")[-1].lower() == d
        }
        for key in h0.held_keys:
            if key in first_component_directions:
                continue
            releases_it = any(
                (k == key and e == "keyup")
                or (isinstance(k, list) and key in k and "keyup" in e)
                for k, e in zip(compiled.keys, compiled.events)
            )
            if not releases_it:
                violations.append((n.pair, n_plus_1.pair, key))
    assert not violations, f"C3 No Inherited Stuck Key: first {violations[0]}"


# --- D - Preemption pair --------------------------------------------------------------


def test_d1_cancel_safety(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """
    Swept exhaustively over every cancel point `k` in `[0, n]` of every reachable
    sample's full compile, per the catalogue's own "exhaustive is cheap" reasoning.
    """
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        walk = _Walk(wrapper)
        if walk.d1_violations:
            violations.append(
                (record.pair.start, record.pair.end, walk.d1_violations[0])
            )
    assert not violations, (
        f"D1 Cancel Safety: {len(violations)} route(s) with a non-directional key "
        f"undeclared for forced release at some cancel point - known, issue #113. "
        f"First: {violations[0] if violations else None}"
    )


def test_d2_preemption_direction_release(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    violations = []
    for i, record in _reachable(corpus_plans):
        wrapper = _compiled(corpus_map, i)
        if wrapper is None:
            continue
        walk = _Walk(wrapper)
        for down in walk.cancel_points:
            remaining = _post_cancel_held(down, wrapper.forced_key_releases)
            if remaining & DIRECTIONS:
                violations.append((record.pair.start, record.pair.end, remaining))
                break
    assert not violations, f"D2 Preemption Direction Release: first {violations[0]}"


# --- E - Movement Plan structure -------------------------------------------------------


def test_e1_path_terminus(
    corpus_map: corpus.CorpusMap, corpus_plans: tuple[corpus.PlanRecord, ...]
) -> None:
    """
    The reachable half - non-empty Path - is already pinned by
    `test_corpus.test_the_frozen_reachability_still_matches_the_grid`. This is the
    terminus half: for a reachable pair, the Path's last node is the requested end.
    """
    violations = []
    for record in _reachable_records(corpus_plans):
        last = (record.path[-1].x, record.path[-1].y)
        if last != record.pair.end:
            violations.append((record.pair.start, record.pair.end, last))
    assert not violations, f"E1 Path Terminus: first {violations[0]}"


def test_e2_adjacency_legality(
    corpus_map: corpus.CorpusMap,
    corpus_plans: tuple[corpus.PlanRecord, ...],
    corpus_grid: MinimapGrid,
) -> None:
    """
    Every consecutive node pair in a Path is a grid neighbour or a declared
    connection - `path_into_movements` would otherwise have raised `NotImplementedError`
    while `corpus.plans` built the sample, so this re-derives the same test the
    compiler's own control flow already passed, directly against the grid.
    """
    violations = []
    for record in _reachable_records(corpus_plans):
        for a, b in zip(record.path, record.path[1:]):
            if b not in corpus_grid.adjacent_nodes(a) and b not in a.connections:
                violations.append((record.pair.start, record.pair.end, a, b))
    assert not violations, f"E2 Adjacency Legality: first {violations[0]}"


def test_e3_walk_squeeze_bound(
    corpus_map: corpus.CorpusMap, corpus_plans: tuple[corpus.PlanRecord, ...]
) -> None:
    violations = [
        (record.pair.start, record.pair.end, component)
        for record in _reachable_records(corpus_plans)
        for component in record.movements
        if component.movement_type
        in (MovementTypes.WALK_LEFT, MovementTypes.WALK_RIGHT)
        and component.length > MovementHandler._MAX_WALK_SIZE
    ]
    assert not violations, f"E3 Walk Squeeze Bound: first {violations[0]}"


def test_e4_plan_non_empty(
    corpus_map: corpus.CorpusMap, corpus_plans: tuple[corpus.PlanRecord, ...]
) -> None:
    violations = [
        (record.pair.start, record.pair.end)
        for record in _reachable_records(corpus_plans)
        if len(record.path) >= 2 and len(record.movements) < 2
    ]
    assert not violations, f"E4 Plan Non-empty: first {violations[0]}"


def test_e5_sentinel_terminus(
    corpus_map: corpus.CorpusMap, corpus_plans: tuple[corpus.PlanRecord, ...]
) -> None:
    violations = []
    for record in _reachable_records(corpus_plans):
        sentinels = [
            i
            for i, c in enumerate(record.movements)
            if c.movement_type is MovementTypes.END_OF_MOVEMENT
        ]
        if sentinels != [len(record.movements) - 1]:
            violations.append((record.pair.start, record.pair.end, sentinels))
    assert not violations, f"E5 Sentinel Terminus: first {violations[0]}"
