"""
The Corpus itself: that it covers every movement type, that its frozen samples say
what the code actually does, and that regenerating them changes nothing.

This module checks the *corpus*, not the compiler. The Invariants and the Goldens run
over these same Movement Plans and belong to issue #104; what has to hold first is
that the plans exist, that they reach every row of the coverage matrix, and that the
checked-in `(start, end, reachable)` triples are still true.
"""

import pytest

from maple.model.mechanics.minimap_creation.minimap_grid import ConnectionTypes
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from tests.test_maple.movement_lab import corpus

CORPUS_IDS = [entry.name for entry in corpus.CORPUS]
FIXTURE_IDS = [entry.name for entry in corpus.FIXTURE_MAPS]


@pytest.fixture(params=corpus.CORPUS, ids=CORPUS_IDS)
def entry(request: pytest.FixtureRequest) -> corpus.CorpusMap:
    return request.param


@pytest.fixture(params=corpus.FIXTURE_MAPS, ids=FIXTURE_IDS)
def fixture_entry(request: pytest.FixtureRequest) -> corpus.CorpusMap:
    return request.param


# --- The coverage matrix ----------------------------------------------------------


def test_the_coverage_matrix_has_thirteen_rows() -> None:
    """
    `path_into_movements` can emit 13 of the 16 `MovementTypes`. Pinned so that adding
    a movement type without a Corpus entry that reaches it fails here, naming the gap,
    rather than quietly leaving a row unchecked.
    """
    assert len(corpus.REACHABLE_MOVEMENT_TYPES) == 13
    assert corpus.UNREACHABLE_BY_CONSTRUCTION | corpus.REACHABLE_MOVEMENT_TYPES == (
        set(MovementTypes) - {MovementTypes.END_OF_MOVEMENT}
    )


def test_the_fixture_maps_alone_cover_every_reachable_movement_type() -> None:
    """
    The reason the Corpus is two-tiered. Coverage rests on maps built to force each
    movement type, never on whether a real map happens to contain a jump-down.
    """
    covered: frozenset[MovementTypes] = frozenset().union(
        *(corpus.movement_types_in(entry) for entry in corpus.FIXTURE_MAPS)
    )

    assert covered - {MovementTypes.END_OF_MOVEMENT} == corpus.REACHABLE_MOVEMENT_TYPES


def test_each_fixture_map_forces_the_movement_types_it_was_built_for(
    fixture_entry: corpus.CorpusMap,
) -> None:
    """
    Per-map, so a fixture that stops forcing its own type is named by the failure
    instead of hiding behind another map that happens to cover it too.
    """
    produced = corpus.movement_types_in(fixture_entry)

    assert corpus.FIXTURE_GUARANTEES[fixture_entry.name] <= produced


def test_every_fixture_map_is_in_the_guarantee_table() -> None:
    assert set(corpus.FIXTURE_GUARANTEES) == {e.name for e in corpus.FIXTURE_MAPS}


def test_the_narrow_perch_fixture_produces_jumps_onto_a_narrow_platform() -> None:
    """
    `narrow` is a flag on a component, not a movement type, so it has no row in the
    matrix - but it changes what the jump builders emit, so the Corpus has to reach it.
    """
    entry = next(e for e in corpus.FIXTURE_MAPS if e.name == "narrow_perch")

    narrow = [
        component
        for record in corpus.plans(entry)
        for component in record.movements
        if component.narrow
    ]

    assert narrow, "narrow_perch produced no jump onto a narrow platform"


# --- Unreachable by construction --------------------------------------------------


def test_no_connection_type_maps_to_an_unimplemented_movement() -> None:
    """
    Why the three are unreachable rather than uncovered: `path_into_movements` names a
    movement by `MovementTypes[connection_type.name]`, and no `ConnectionTypes` member
    carries one of these names - they are commented out as `NotImplemented` there.
    """
    named_by_a_connection = {
        MovementTypes[connection.name]
        for connection in ConnectionTypes
        if connection.name in MovementTypes.__members__
    }

    assert not named_by_a_connection & corpus.UNREACHABLE_BY_CONSTRUCTION


def test_the_corpus_emits_no_unimplemented_movement(entry: corpus.CorpusMap) -> None:
    assert not corpus.movement_types_in(entry) & corpus.UNREACHABLE_BY_CONSTRUCTION


@pytest.mark.parametrize(
    "move_type", sorted(corpus.UNREACHABLE_BY_CONSTRUCTION), ids=lambda m: m.name
)
def test_an_unimplemented_movement_raises_rather_than_compiling(
    move_type: MovementTypes, held_movement_keys: object
) -> None:
    """
    The other half of "unreachable by construction": were a grid ever to produce one,
    compilation raises rather than emitting something plausible and wrong.
    """
    plan = (
        _MovementComponent(move_type, 1),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
    )

    with pytest.raises(NotImplementedError, match=move_type.name):
        compile_movements(
            None,
            movements=plan,
            handle=corpus.LAB_HANDLE,
            ign=corpus.LAB_IGN,
            speed=1.0,
        )


# --- The frozen sample ------------------------------------------------------------


def test_every_corpus_map_has_a_frozen_sample(entry: corpus.CorpusMap) -> None:
    sample = corpus.load_sample(entry)

    assert entry.pairs_path.exists()
    assert len(sample) == entry.sample_size


def test_no_pairs_file_is_orphaned() -> None:
    """A sample left behind by a map that has since left the Corpus is dead data."""
    on_disk = {path.stem for path in corpus.PAIRS_ROOT.glob("*.json")}

    assert on_disk == {entry.name for entry in corpus.CORPUS}


def test_the_frozen_pairs_are_reproducible_from_the_seed(
    entry: corpus.CorpusMap,
) -> None:
    """
    Half of "rerunning the generator reproduces the file": which pairs were drawn, and
    in what order, is a pure function of the seed and the map's walkable nodes.
    """
    drawn = corpus.draw_pairs(entry)
    recorded = tuple((pair.start, pair.end) for pair in corpus.load_sample(entry))

    assert drawn == recorded


def test_the_frozen_reachability_still_matches_the_grid(
    entry: corpus.CorpusMap,
) -> None:
    """
    The other half, and the one with teeth: reachability is recorded as data, so a
    pair that stops being reachable - or starts being - fails here instead of being
    silently skipped by a check that queried the grid itself.
    """
    disagreed = [
        (record.pair.start, record.pair.end, record.pair.reachable, bool(record.path))
        for record in corpus.plans(entry)
        if bool(record.path) != record.pair.reachable
    ]

    assert not disagreed, (
        f"{len(disagreed)} pair(s) in {entry.pairs_path.name} no longer agree with the "
        f"grid; regenerate with `python toolkit/generate_movement_lab_pairs.py "
        f"{entry.name}` once the change is known to be deliberate. First: {disagreed[0]}"
    )


def test_the_sample_file_is_exactly_what_the_generator_renders(
    entry: corpus.CorpusMap,
) -> None:
    """
    The last third: the serialization. Together with the two checks above, a rerun of
    the generator reproduces the checked-in file.
    """
    rendered = corpus.render_sample(entry, corpus.load_sample(entry))

    assert rendered == entry.pairs_path.read_text(encoding="utf-8")


def test_the_corpus_samples_both_reachable_and_unreachable_pairs() -> None:
    """
    Recording reachability as data is only worth anything if the Corpus contains both
    answers. `portal_pair`'s portal is one-directional for exactly this reason.
    """
    reachable = {
        pair.reachable for entry in corpus.CORPUS for pair in corpus.load_sample(entry)
    }

    assert reachable == {True, False}
