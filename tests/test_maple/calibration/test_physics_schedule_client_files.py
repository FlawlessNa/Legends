"""
`configs/trials/physics.json` against Ellinia's own foothold graph.

A physics Trial measures one move, but it only names a start and a target: the
planner chooses the Path. So each Trial is checked here to be planned through the
move it measures, on the graph the bot plans on (with teleport only where its batch
allows it), and each Trial's start to be reachable from where the one before it
ends, so the sitting runs as one tour. What the client does with those Paths is
the live sitting's to say.

Needs the game data store: `client_files`.
"""

import pytest

from maple.calibration.specs import Measure, TrialBatch, TrialSpec, load_schedule
from maple.model.navigation import FootholdGraph, MoveKind, Path
from maple.model.world import Platform, WorldMap
from tests.test_maple.movement_lab.corpus import LAB_PHYSICS

pytestmark = pytest.mark.client_files

SCHEDULE = load_schedule("physics")


@pytest.fixture(scope="module")
def graphs() -> dict[bool, FootholdGraph]:
    world_map = WorldMap.load(SCHEDULE.map)
    return {
        teleport: FootholdGraph.build(world_map, LAB_PHYSICS, teleport=teleport)
        for teleport in (False, True)
    }


def _measures(path: Path, measure: Measure) -> bool:
    """Whether ``path`` makes the move ``measure`` reads."""
    kinds = {
        Measure.WALK: lambda m: m.kind is MoveKind.WALK,
        Measure.CLIMB: lambda m: m.kind is MoveKind.CLIMB,
        Measure.JUMP: lambda m: (
            m.kind is MoveKind.JUMP
            and isinstance(m.start_on, Platform)
            and isinstance(m.end_on, Platform)
        ),
        Measure.ROPE_JUMP: lambda m: (
            m.kind is MoveKind.JUMP and not isinstance(m.start_on, Platform)
        ),
        Measure.TELEPORT: lambda m: m.kind is MoveKind.TELEPORT,
        Measure.DROP: lambda m: m.kind is MoveKind.DROP,
    }
    return any(kinds[measure](move) for move in path.moves)


@pytest.mark.parametrize(
    ("batch", "trial"),
    SCHEDULE.trials,
    ids=[f"{b.name}/{t.name}" for b, t in SCHEDULE.trials],
)
def test_each_trial_is_planned_through_the_move_it_measures(
    graphs: dict[bool, FootholdGraph], batch: TrialBatch, trial: TrialSpec
) -> None:
    assert trial.measures is not None
    path = graphs[batch.teleport].path(trial.start, trial.target)
    assert path is not None, f"{trial.name}: no Path"
    assert _measures(path, trial.measures), [m.kind.value for m in path.moves]


def test_the_schedule_runs_as_one_tour(graphs: dict[bool, FootholdGraph]) -> None:
    """Each Trial's start is reachable from where the one before it ends."""
    previous = None
    for batch, trial in SCHEDULE.trials:
        if previous is not None:
            assert graphs[batch.teleport].path(previous, trial.start) is not None, (
                trial.name
            )
        previous = trial.target
