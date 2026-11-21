"""
Movement Plans in virtual px (#396): a `FootholdGraph` Path turned into a Movement
Plan, compiled with the physics' speeds, and planned from `POSITION` with the
character's current stats (`PathingProvider`, #442).

The maps are the movement lab's Fixture maps (`movement_lab/fixture_maps.py`), on
the client's own physics (`corpus.LAB_PHYSICS`): walk 125 px/s, jump 555 px/s,
gravity 2000 px/s², so a jump that lands at its take-off's height flies
2 × 555 ÷ 2000 = 0.555 s.
"""

import logging
import math
import random
import threading
from collections.abc import Mapping
from dataclasses import replace

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from botting.screen import Reading
from game_data.catalogue import Rope
from maple.actions import movements_v2
from maple.decision_makers.providers import MOVEMENTS, PATH, PathingProvider, actionable
from maple.model.characters import MapleSkill
from maple.model.mechanics import movement_mechanics_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    _MAX_TRAVEL_LENGTH,
    MovementHandler,
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import (
    Direction,
    FootholdGraph,
    FootholdGraphs,
    Move,
    MoveKind,
    Path,
)
from maple.screen.position import (
    PositionSource,
    VirtualPosition,
    feet_of_marker,
    marker_of_feet,
)
from tests.test_maple.movement_lab import corpus
from tests.test_maple.serving import override, pathing

JUMP_KEY = "space"
NOBODY = InputState(frozenset())
PHYSICS = corpus.LAB_PHYSICS


@pytest.fixture(autouse=True)
def jump_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        movement_mechanics_v2, "key_binds", lambda ign: {"jump": JUMP_KEY}
    )


def _entry(name: str) -> corpus.CorpusMap:
    return next(e for e in corpus.FIXTURE_MAPS if e.name == name)


def _handler(name: str) -> MovementHandler:
    return MovementHandler(0, corpus.world_map(_entry(name)), "T")


def _plan(name: str, start: tuple[float, float], goal: tuple[float, float]) -> tuple:
    handler = _handler(name)
    return handler.path_into_movements(handler.compute_path(start, goal, PHYSICS))


def _compile(plan: tuple[_MovementComponent, ...]) -> KeyboardInputWrapper:
    random.seed(0)
    wrapper = compile_movements(
        NOBODY,
        movements=plan,
        handle=0,
        ign="T",
        speed=PHYSICS.walk_speed,
        climb_speed=PHYSICS.climb_speed,
    )
    assert wrapper is not None
    return wrapper


def _kinds(plan: tuple[_MovementComponent, ...]) -> list[MovementTypes]:
    return [c.movement_type for c in plan]


# --- graph moves into components ----------------------------------------------


def test_a_walk_across_a_join_and_a_slope_is_one_walk_cut_into_equal_pieces() -> None:
    """`walk_corridor` is one floor of three footholds, a slope between two flats."""
    plan = _plan("walk_corridor", (0.0, 0.0), (700.0, -20.0))

    walks = plan[:-1]
    assert set(_kinds(walks)) == {MovementTypes.WALK_RIGHT}
    assert sum(c.length for c in walks) == pytest.approx(700.0)
    assert len(walks) == math.ceil(700 / _MAX_TRAVEL_LENGTH)
    assert len({round(c.length, 9) for c in walks}) == 1
    assert walks[0].start == (0.0, 0.0)
    assert walks[-1].end == (700.0, -20.0)
    assert plan[-1].movement_type is MovementTypes.END_OF_MOVEMENT


def test_a_jump_carries_its_flight_from_the_graph() -> None:
    plan = _plan("jump_gap", (180.0, 0.0), (270.0, 0.0))

    (jump,) = [c for c in plan if c.movement_type is MovementTypes.JUMP_RIGHT]
    assert jump.duration == pytest.approx(2 * 555 / 2000)
    assert jump.length == pytest.approx(125 * 2 * 555 / 2000)
    assert jump.grabs_rope is False


def test_a_jump_straight_up_into_a_ropes_bottom_grabs_it() -> None:
    """`rope_grab`'s left rope hangs 40 px above the floor at x 300."""
    plan = _plan("rope_grab", (300.0, 0.0), (300.0, -150.0))

    jump, *climbs, _ = plan
    assert jump.movement_type is MovementTypes.JUMP
    assert jump.grabs_rope is True
    # The rise to 40 px above the take-off, on the way up.
    assert jump.duration == pytest.approx(
        (555 - math.sqrt(555**2 - 2 * 2000 * 40)) / 2000
    )
    assert {c.movement_type for c in climbs} == {MovementTypes.CLIMB_UP}


def test_a_fall_off_a_ropes_bottom_is_a_climb_down_lasting_the_fall() -> None:
    """`rope_grab`'s right rope is walled in: below its middle, it is left by falling."""
    plan = _plan("rope_grab", (500.0, -98.0), (428.0, 0.0))

    climb, fall, walk, _ = plan
    assert (climb.movement_type, climb.length, climb.duration) == (
        MovementTypes.CLIMB_DOWN,
        58.0,
        None,
    )
    assert fall.movement_type is MovementTypes.CLIMB_DOWN
    assert fall.length == 40.0
    assert fall.duration == pytest.approx(PHYSICS.fall_time(40.0))
    assert walk.movement_type is MovementTypes.WALK_LEFT


def test_a_fall_off_a_platforms_end_is_walked_for_its_drift() -> None:
    """Off the end of a platform, the direction is held through the fall."""
    world = corpus.world_map(_entry("jump_ledge"))
    shelf, floor = world.platforms[1], world.platforms[0]
    fall = Move(
        MoveKind.FALL, Direction.RIGHT, (400.0, -50.0), (427.0, 0.0), shelf, floor, 0.2
    )
    walk = Move(
        MoveKind.WALK,
        Direction.RIGHT,
        (380.0, -50.0),
        (400.0, -50.0),
        shelf,
        shelf,
        0.1,
    )

    plan = _handler("jump_ledge").path_into_movements(Path((walk, fall)))

    assert plan[:-1] == (
        _MovementComponent(
            MovementTypes.WALK_RIGHT, 47.0, start=(380.0, -50.0), end=(427.0, 0.0)
        ),
    )


def test_consecutive_teleports_the_same_way_are_one_component_of_that_many_casts() -> (
    None
):
    world = corpus.world_map(_entry("teleport_shaft"))
    low, middle, high = world.platforms[0], world.platforms[1], world.platforms[2]
    up = [
        Move(
            MoveKind.TELEPORT, Direction.UP, (50.0, 0.0), (50.0, -110.0), low, middle, 1
        ),
        Move(
            MoveKind.TELEPORT,
            Direction.UP,
            (50.0, -110.0),
            (50.0, -220.0),
            middle,
            high,
            1,
        ),
    ]

    (teleport, _) = _handler("teleport_shaft").path_into_movements(Path(tuple(up)))

    assert teleport.movement_type is MovementTypes.TELEPORT_UP
    assert (teleport.casts, teleport.length) == (2, 220.0)
    assert (teleport.start, teleport.end) == ((50.0, 0.0), (50.0, -220.0))


# --- compiling ------------------------------------------------------------------


def test_a_walk_lasts_its_length_at_the_walk_speed() -> None:
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 62.5),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    ((t_down, t_up),) = _compile(plan).holds["right"]

    assert t_up - t_down >= 62.5 / 125


def test_a_climb_lasts_its_length_at_the_climb_speed() -> None:
    plan = (
        _MovementComponent(MovementTypes.CLIMB_UP, 50.0),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )
    random.seed(0)
    wrapper = compile_movements(
        NOBODY, movements=plan, handle=0, ign="T", speed=1e9, climb_speed=100.0
    )
    assert wrapper is not None

    ((t_down, t_up),) = wrapper.holds["up"]
    assert t_up - t_down >= 0.5


@pytest.mark.parametrize("flight", [0.2, 0.555, 1.1])
def test_a_jump_holds_its_direction_for_its_flight_from_the_take_off(
    flight: float, overhead: float
) -> None:
    """
    The jump key's press is the take-off; the direction stays held until the flight
    is over. No fixed number of seconds: the flight is the component's own.

    The send loop spends one `OVERHEAD` on top of every Step's delay, and two Steps
    sit between the take-off and the direction's release (the jump key's own press
    and its release). The jump spends both out of its flight, so the hold is the
    flight whatever `OVERHEAD` is (#589). It held the flight plus two `OVERHEAD`s
    before, which #473 wrote down as the expectation: every key after a jump then
    went down that late. `OVERHEAD` is measured once at import and reads ~1 ms on a
    quiet machine but 10 ms or more when other processes are running, so the test
    runs at several values of it (root `conftest.overhead`), not at the machine's.
    """
    plan = (
        _MovementComponent(MovementTypes.JUMP_RIGHT, 70.0, duration=flight),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = _compile(plan)

    ((take_off, _),) = wrapper.holds[JUMP_KEY]
    ((_, landed),) = wrapper.holds["right"]
    assert landed - take_off == pytest.approx(flight, abs=1e-9)


def test_a_jump_with_no_flight_refuses_to_compile() -> None:
    plan = (
        _MovementComponent(MovementTypes.JUMP_RIGHT, 70.0),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    with pytest.raises(ValueError, match="JUMP_RIGHT has no duration"):
        _compile(plan)


def test_the_jump_builders_hold_no_fixed_time() -> None:
    """The 0.75 s hold is gone: a shorter flight is a shorter Input Sequence."""
    short = movements_v2.single_jump(
        0, "right", JUMP_KEY, initial_state=NOBODY, duration=0.3
    )
    long = movements_v2.single_jump(
        0, "right", JUMP_KEY, initial_state=NOBODY, duration=0.9
    )

    assert long.duration - short.duration == pytest.approx(0.6, abs=0.01)


def test_a_jump_straight_up_into_a_rope_has_its_own_shape() -> None:
    """
    #111: `jump_on_rope` takes left or right only. A jump straight up into a rope
    releases what else is held, presses the jump key and `up` together, holds them
    for the flight, releases the jump key, and keeps `up` held into the climb.
    """
    plan = (
        _MovementComponent(MovementTypes.JUMP, 0.0, duration=0.085, grabs_rope=True),
        _MovementComponent(MovementTypes.CLIMB_UP, 50.0),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )
    random.seed(0)
    wrapper = compile_movements(
        InputState(frozenset({"left"})),
        movements=plan,
        handle=0,
        ign="T",
        speed=125.0,
    )
    assert wrapper is not None

    steps = list(zip(wrapper.keys, wrapper.events, wrapper.delays, strict=True))
    assert steps[0][:2] == ("left", "keyup")
    assert steps[1] == ([JUMP_KEY, "up"], ["keydown", "keydown"], 0.085)
    assert steps[2][:2] == (JUMP_KEY, "keyup")
    (up,) = wrapper.holds["up"]
    assert up[1] - up[0] >= 0.085 + 50 / 125


def test_jump_up_on_rope_presses_up_once_when_it_is_already_held() -> None:
    wrapper = movements_v2.jump_up_on_rope(
        0, JUMP_KEY, initial_state=InputState(frozenset({"up"})), duration=0.1
    )

    assert wrapper.keys[0] == JUMP_KEY
    assert "up" in wrapper.keys_held


def test_a_drop_onto_a_rope_refuses_to_compile() -> None:
    """The graph has no drop onto a rope (#111's other half)."""
    plan = (
        _MovementComponent(MovementTypes.JUMP_DOWN, 0.0, duration=0.3, grabs_rope=True),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    with pytest.raises(ValueError, match="a drop lands on a platform only"):
        _compile(plan)


# --- planning with the character's current stats --------------------------------


def _planner(
    name: str,
    position: tuple[float, float],
    target: tuple[float, float],
    *,
    status_read: bool = True,
    wait: bool = True,
    source: PositionSource = PositionSource.FUSED,
) -> PathingProvider:
    provider = _pathing(name, position, target, status_read=status_read, source=source)
    data = provider.data
    if wait:
        # The graph builds in a worker thread from setup on (#430), and planning
        # holds until it is there: waited for here, so the tests below plan.
        data.movement_handler.graph(provider.physics())
    override(data, PATH, threshold=1e-9)
    override(data, MOVEMENTS, threshold=1e-9)
    return provider


def _pathing(
    name: str,
    position: tuple[float, float],
    target: tuple[float, float],
    *,
    status_read: bool = True,
    skills: Mapping[str, object] | None = None,
    source: PositionSource = PositionSource.FUSED,
    disable_teleport: bool = False,
) -> PathingProvider:
    """
    The rotation's pathing, set up on what it plans from: the map, the physics,
    a position, a target; and the profile's `disable_teleport`.
    """
    reading = (
        Reading.read(VirtualPosition(*position, source), 0.0)
        if status_read
        else Reading.unsure(0.0, "two characters in the window")
    )
    return pathing(
        corpus.world_map(_entry(name)),
        lambda: reading,
        lambda: target,
        skills=skills,
        game_physics=corpus.LAB_PHYSICS_VALUES,
        position_threshold=1e-9,
        disable_teleport=disable_teleport,
    )


def test_the_target_is_planned_to_as_it_is_in_virtual_px() -> None:
    """The rotation's targets are virtual since #398: no conversion on the way."""
    planner = _planner("jump_gap", (100.0, 0.0), (600.0, 0.0))

    path = planner.data.path
    assert path is not None
    assert path.moves[0].start == (100.0, 0.0)
    assert path.moves[-1].end == (600.0, 0.0)


def test_an_unsure_position_plans_nothing_and_sends_nothing() -> None:
    planner = _planner("jump_gap", (100.0, 0.0), (600.0, 0.0), status_read=False)

    assert planner.data.path is None
    assert planner.data.movements == ()
    assert actionable(planner.data.movements) is False


def test_a_coarse_read_plans_no_walk_inside_its_own_canvas_pixel() -> None:
    # #516: a coarse read is the middle of a 16 px canvas pixel, so a walk of
    # 8 px or less may already be where the read cannot tell it from: the live
    # record walked 7 and 9 px either side of a ladder for minutes.
    coarse = _planner(
        "ladder_climb", (304.0, -496.0), (300.0, -500.0), source=PositionSource.COARSE
    )
    fused = _planner("ladder_climb", (304.0, -500.0), (300.0, -500.0))

    assert coarse.data.path == Path(())
    assert actionable(coarse.data.movements) is False
    assert _kinds(fused.data.movements) == [
        MovementTypes.WALK_LEFT,
        MovementTypes.END_OF_MOVEMENT,
    ]


def test_a_coarse_read_still_walks_further_than_its_pixel_and_onto_a_rope() -> None:
    walk = _planner(
        "ladder_climb", (288.0, -496.0), (300.0, -500.0), source=PositionSource.COARSE
    )
    # The same 4 px off the ladder, heading down it: a climb is no walk.
    down = _planner(
        "ladder_climb", (304.0, -496.0), (300.0, -300.0), source=PositionSource.COARSE
    )

    assert _kinds(walk.data.movements) == [
        MovementTypes.WALK_RIGHT,
        MovementTypes.END_OF_MOVEMENT,
    ]
    assert _kinds(down.data.movements)[:2] == [
        MovementTypes.WALK_LEFT,
        MovementTypes.CLIMB_DOWN,
    ]


def test_a_map_with_no_minimap_plans_nothing() -> None:
    world = corpus.world_map(_entry("jump_gap"))
    unread = Reading[VirtualPosition].unsure(0.0, "no position is read on this map")

    data = pathing(replace(world, minimap=None), lambda: unread).data

    assert data.movement_handler is None
    assert data.path is None
    assert data.movements == ()


def test_a_change_of_jump_stat_between_two_paths_changes_the_ranges_and_the_flight() -> (
    None
):
    """
    The stats are read at the start of a Session and can change inside it. Planned
    after the change, the next Path is on a graph built for the new jump: its jump
    ranges differ, and so does the flight its jump carries and is compiled with.
    """
    planner = _planner("jump_gap", (100.0, 0.0), (300.0, 0.0))
    handler: MovementHandler = planner.data.movement_handler

    def jump() -> _MovementComponent:
        planner.data.update_attribute("movements")
        (component,) = [
            c
            for c in planner.data.movements
            if c.movement_type is MovementTypes.JUMP_RIGHT
        ]
        return component

    before_physics = planner.physics()
    before = jump()
    planner.data.jump_multiplier = 1.2  # a buff, say: a new reading replaces it
    after_physics = planner.physics()
    handler.graph(after_physics)  # built off the loop (#430): waited for here
    after = jump()

    assert after_physics.jump_speed == pytest.approx(1.2 * before_physics.jump_speed)
    assert before.duration == pytest.approx(2 * 555 / 2000)
    assert after.duration == pytest.approx(2 * 1.2 * 555 / 2000)

    def ranges(physics: VRPhysics) -> set[tuple[float, float]]:
        return {
            (m.low, m.high)
            for m in handler.graph(physics).moves
            if m.kind is MoveKind.JUMP and m.direction is Direction.RIGHT
        }

    assert ranges(before_physics) != ranges(after_physics)

    def hold(component: _MovementComponent) -> float:
        plan = (component, _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0))
        ((take_off, _),) = _compile(plan).holds[JUMP_KEY]
        ((_, landed),) = _compile(plan).holds["right"]
        return landed - take_off

    assert hold(after) - hold(before) == pytest.approx(2 * 0.2 * 555 / 2000, abs=0.005)


def _hold_build_half_way(
    monkeypatch: pytest.MonkeyPatch, physics: VRPhysics | None = None
) -> tuple[threading.Event, threading.Event]:
    """
    Holds the build of the graph of `physics` (of any, for `None`) half-way:
    its moves are traced and its nodes and edges not yet made. Returns the event
    set when a build gets there, and the one that lets it go on.
    """
    reached, release = threading.Event(), threading.Event()
    build_graph = FootholdGraph._build_graph

    def held(graph: FootholdGraph) -> None:
        if physics is None or graph._physics == physics:
            reached.set()
            assert release.wait(5), "the test never let the build go on"
        build_graph(graph)

    monkeypatch.setattr(FootholdGraph, "_build_graph", held)
    return reached, release


def test_while_the_new_stats_graph_builds_nothing_is_planned_then_the_next_path_is_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The jump stat changes while the graph is in use. The new graph builds in the
    worker, and until it is whole no Path is planned: neither on the old stats'
    graph, whose arc is another's, nor on the half-built one. The next Path after
    it is built is planned on it, with its flight.
    """
    planner = _planner("jump_gap", (100.0, 0.0), (300.0, 0.0))
    handler: MovementHandler = planner.data.movement_handler

    def plan() -> tuple[_MovementComponent, ...]:
        planner.data.update_attribute("movements")
        return planner.data.movements

    def flight(movements: tuple[_MovementComponent, ...]) -> float | None:
        (jump,) = [c for c in movements if c.movement_type is MovementTypes.JUMP_RIGHT]
        return jump.duration

    assert flight(plan()) == pytest.approx(2 * 555 / 2000)
    planner.data.jump_multiplier = 1.2
    buffed = planner.physics()
    reached, release = _hold_build_half_way(monkeypatch, buffed)
    try:
        assert plan() == ()  # the change is seen: its graph starts, planning holds
        assert reached.wait(5)  # the new graph is half-built in the worker
        assert planner.data.path is None
        assert plan() == ()
        assert handler.ready_graph(buffed) is None
    finally:
        release.set()

    handler.graph(buffed)  # waits for the worker's build to finish
    assert flight(plan()) == pytest.approx(2 * 1.2 * 555 / 2000)
    assert planner.data.path is not None


def test_the_graph_starts_building_at_setup_before_any_path_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsure position asks for no graph, so only the setup can have started it."""
    reached, release = _hold_build_half_way(monkeypatch)
    try:
        planner = _planner(
            "jump_gap", (100.0, 0.0), (0, 0), status_read=False, wait=False
        )
        assert reached.wait(5)
        assert planner.data.movement_handler.graphs.is_building()
    finally:
        release.set()


def test_a_configured_handler_starts_its_graph_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A Trial batch planned without teleport, on a teleporting character: its
    graph starts building when the batch's Knobs are put in place, before any
    Path is asked, as the first batch's always did.
    """
    provider = _pathing(
        "jump_gap",
        (100.0, 0.0),
        (0, 0),
        status_read=False,
        skills={"Teleport": _Teleport()},
    )
    provider.data.movement_handler.graph(provider.physics())
    reached, release = _hold_build_half_way(monkeypatch)
    try:
        provider.configure(duration=1.0, teleport=False)
        assert reached.wait(5)
        handler: MovementHandler = provider.data.movement_handler
        assert handler.teleport is None
        assert handler.graphs.teleport is False
        assert handler.graphs.is_building()
    finally:
        release.set()


def test_a_remade_handler_plans_on_the_graphs_already_built() -> None:
    """A Trial batch remakes the handler; another DecisionMaker makes its own."""
    planner = _planner("jump_gap", (100.0, 0.0), (300.0, 0.0))
    first: MovementHandler = planner.data.movement_handler

    planner.data.update_attribute("movement_handler")
    second: MovementHandler = planner.data.movement_handler

    assert second is not first
    assert second.graphs is first.graphs
    assert second.ready_graph(planner.physics()) is first.graph(planner.physics())


def test_trial_batches_that_switch_teleport_build_each_settings_graph_once() -> None:
    """
    A Trial alternates batches planned with and without teleport (`TrialRunner`
    configures the Provider so). Each setting keeps its own graphs, so switching
    back needs no build.
    """
    planner = _planner("jump_gap", (100.0, 0.0), (300.0, 0.0))
    world = planner.data.world_map

    walking = planner._graphs_for(world, teleport=False)
    teleporting = planner._graphs_for(world, teleport=True)

    assert walking.teleport is False
    assert teleporting.teleport is True
    assert planner._graphs_for(world, teleport=False) is walking
    assert planner._graphs_for(world, teleport=True) is teleporting
    assert (
        planner._graphs_for(replace(world), teleport=False) is not walking
    )  # a new map


class _Teleport:
    name = "Teleport"
    id = 2301000
    cast_time = 0.6


@pytest.mark.parametrize(
    "disable_teleport", [False, True], ids=["teleport", "teleport-disabled"]
)
def test_a_rotation_plans_with_the_characters_teleport_unless_disabled(
    disable_teleport: bool,
) -> None:
    """
    The profile's `disable_teleport` configures the rotation's pathing, which
    then plans and compiles with no teleport skill. The character's skills are
    left as they are: no other Bot loses its Teleport (#49).
    """
    teleport = _Teleport()
    skills = {"Teleport": teleport}

    provider = _pathing(
        "jump_gap",
        (100.0, 0.0),
        (0, 0),
        status_read=False,
        skills=skills,
        disable_teleport=disable_teleport,
    )

    handler: MovementHandler = provider.data.movement_handler
    assert handler.teleport is (None if disable_teleport else teleport)
    assert handler.graphs.teleport is not disable_teleport
    assert provider.compiler(None).keywords["teleport"] is (
        None if disable_teleport else teleport
    )
    assert skills == {"Teleport": teleport}


def test_a_teleport_with_no_cast_time_is_planned_as_no_teleport(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    No Teleport of the client's has an action of its own, and the Cleric's has
    no effect to time it either (#646), so it has no cast time, and a plan that
    cast it couldn't be compiled: Paths walk, and the setup says so once.
    """
    teleport = MapleSkill("Teleport", id=2301000, level=20, max_level=20)

    with caplog.at_level(logging.WARNING):
        provider = _pathing(
            "jump_gap",
            (100.0, 0.0),
            (0, 0),
            status_read=False,
            skills={"Teleport": teleport},
        )
        provider.data.movement_handler.graph(provider.physics())

    handler: MovementHandler = provider.data.movement_handler
    assert handler.teleport is None
    assert handler.graphs.teleport is False
    assert provider.compiler(None).keywords["teleport"] is None
    warnings = [
        r.getMessage() for r in caplog.records if "plans no teleport" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert "Teleport (2301000) has no cast time" in warnings[0]


def test_a_handler_refuses_another_maps_graphs() -> None:
    graphs = FootholdGraphs(corpus.world_map(_entry("rope_grab")), teleport=False)

    with pytest.raises(ValueError, match="another map's"):
        MovementHandler(0, corpus.world_map(_entry("jump_gap")), "T", graphs=graphs)


def test_the_compile_speeds_follow_the_current_speed_stat() -> None:
    planner = _planner("jump_gap", (100.0, 0.0), (300.0, 0.0))
    planner.data.speed_multiplier = 1.4

    compiler = planner.compiler(None)

    assert compiler.keywords["speed"] == pytest.approx(1.4 * 125)
    assert compiler.keywords["climb_speed"] == pytest.approx(1.4 * 125)


def test_the_graph_is_built_once_per_physics() -> None:
    handler = _handler("jump_gap")

    assert handler.graph(PHYSICS) is handler.graph(PHYSICS)
    assert handler.graph(replace(PHYSICS, jump_speed=600.0)) is not handler.graph(
        PHYSICS
    )


# --- the minimap transform ----------------------------------------------------------


def test_feet_and_marker_convert_both_ways() -> None:
    transform = corpus.world_map(_entry("jump_gap")).minimap
    assert transform is not None

    for marker in ((0, 0), (63, 56), (80, 40)):
        assert marker_of_feet(transform, feet_of_marker(transform, marker)) == marker


def test_a_rope_is_what_a_grab_ends_on() -> None:
    """`grabs_rope` is read off the move's landing surface."""
    plan = _plan("rope_grab", (356.0, 0.0), (300.0, -82.0))
    world = corpus.world_map(_entry("rope_grab"))

    (jump,) = [c for c in plan if c.grabs_rope]
    assert jump.movement_type is MovementTypes.JUMP_LEFT
    assert jump.end is not None
    assert any(isinstance(rope, Rope) and rope.x == jump.end[0] for rope in world.ropes)


# --- a sideways jump off a rope, a climb key still down (#561) -----------------


def test_a_sideways_jump_off_a_rope_is_planned_as_leaving_it() -> None:
    """`leaves_rope` is read off the move's take-off surface, as `grabs_rope` is off
    its landing."""
    plan = _plan("rope_grab", (300.0, -150.0), (150.0, 0.0))

    (jump,) = [c for c in plan if c.movement_type is MovementTypes.JUMP_LEFT]
    assert jump.leaves_rope is True
    assert jump.grabs_rope is False
    (floor_jump,) = [
        c
        for c in _plan("jump_gap", (180.0, 0.0), (270.0, 0.0))
        if c.movement_type is MovementTypes.JUMP_RIGHT
    ]
    assert floor_jump.leaves_rope is False


def _off_rope(
    held: frozenset[str], *, leaves_rope: bool = True
) -> KeyboardInputWrapper:
    plan = (
        _MovementComponent(
            MovementTypes.JUMP_LEFT, 80.0, duration=0.6, leaves_rope=leaves_rope
        ),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )
    random.seed(0)
    wrapper = compile_movements(
        InputState(held),
        movements=plan,
        handle=0,
        ign="T",
        speed=PHYSICS.walk_speed,
        climb_speed=PHYSICS.climb_speed,
    )
    assert wrapper is not None
    return wrapper


@pytest.mark.parametrize(
    "held",
    [
        frozenset({"down", "left"}),
        frozenset({"down", "right"}),
        frozenset({"down"}),
        frozenset({"up", "left"}),
    ],
)
def test_a_climb_key_comes_up_before_a_sideways_jump_off_a_rope(
    held: frozenset[str],
) -> None:
    """
    #561: on the descent, 56 of 64 jumps off a rope keyed with `down` still down
    (a climb cut at the Action cap) never left it, and 7 of the 8 others left it at
    its bottom, not by the jump. The climb key comes up first, and the jump key waits
    the gap `jump_on_rope` leaves after its own releases.
    """
    wrapper = _off_rope(held)

    ((take_off, _),) = wrapper.holds[JUMP_KEY]
    (climb,) = held & {"up", "down"}
    ((_, released),) = wrapper.holds[climb]
    assert released < take_off
    # `random_delay * 5`: 5 × 0.95 × DELAY at the least.
    assert take_off - released >= 5 * 0.95 * 0.03
    assert wrapper.holds["left"][-1][0] <= take_off


def test_a_sideways_jump_off_a_platform_keeps_its_climb_key_and_its_timing() -> None:
    """Off a platform (straight off a climb up, `up` still down), the jump key goes
    down first, as before: a release there would only delay a take-off the
    character is walking into."""
    wrapper = _off_rope(frozenset({"up", "left"}), leaves_rope=False)

    assert wrapper.keys[0] == JUMP_KEY
    assert wrapper.events[0] == "keydown"


def test_a_climb_down_into_a_sideways_jump_off_the_rope_releases_down_first() -> None:
    """The same jump inside a plan, straight after a climb down the rope."""
    plan = (
        _MovementComponent(MovementTypes.CLIMB_DOWN, 30.0),
        _MovementComponent(
            MovementTypes.JUMP_LEFT, 80.0, duration=0.6, leaves_rope=True
        ),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = _compile(plan)

    ((take_off, _),) = wrapper.holds[JUMP_KEY]
    ((_, released),) = wrapper.holds["down"]
    assert released < take_off
