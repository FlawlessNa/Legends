"""
Trial specs: that a schedule round-trips, and that a malformed one is rejected loudly.

The rejection half carries the weight. A schedule is the *definition* of an
experiment, and the failure mode that matters is silent: a mistyped Knob that leaves
the default in place produces a batch which measures the baseline a second time and
reports it as a swept result. Every check below that asserts a `TrialSpecError` is
guarding against a number in a report that nobody can tell is wrong.
"""

import json
from pathlib import Path

import pytest

from maple.calibration.specs import (
    KNOB_NAMES,
    TRIALS_DIR,
    Knobs,
    Measure,
    TrialBatch,
    TrialSchedule,
    TrialSpec,
    TrialSpecError,
    available,
    load_schedule,
    render_schedule,
    schedule_map_id,
)

MINIMAL: dict = {
    "name": "minimal",
    "map": "GhostShip1",
    "batches": [
        {
            "name": "baseline",
            "trials": [
                {
                    "name": "a-to-b",
                    "start": [15, 42],
                    "target": [109, 42],
                    "tolerance": 2.0,
                    "time_budget": 20.0,
                }
            ],
        }
    ],
}


def _with_trial(**overrides: object) -> dict:
    """A copy of MINIMAL whose single trial has the given keys replaced."""
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["trials"][0].update(overrides)
    return payload


# --- The checked-in schedule ------------------------------------------------------


def test_the_example_schedule_on_disk_loads() -> None:
    """
    `configs/trials/example.json` is the template every campaign is copied from, so
    it has to survive its own loader.
    """
    schedule = load_schedule("example")
    assert schedule.map == "Victoria Road: Ellinia"
    assert schedule.batches
    assert "example" in available()


@pytest.mark.parametrize("name", ["example", "physics"])
def test_a_checked_in_schedule_is_exactly_its_rendered_text(name: str) -> None:
    """
    The file on disk is what the renderer writes, so a schedule regenerated from
    its objects diffs only where it changed.
    """
    schedule = load_schedule(name)
    reloaded = TrialSchedule.from_json(json.loads(render_schedule(schedule)))
    assert reloaded == schedule
    text = (TRIALS_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert text == render_schedule(schedule)  # read_text folds CRLF


def test_the_example_s_precision_knob_is_in_virtual_px() -> None:
    """The old 8 minimap px, at 16 virtual px each (#397)."""
    knobs = {b.name: b.knobs for b in load_schedule("example").batches}
    assert knobs["short-actions"].precision_threshold == 128


def test_the_physics_schedule_measures_every_physics_value() -> None:
    """
    #397: walk, climb, jump arc, a jump off a rope, drops and teleports, each
    tagged for the analyzer, on Ellinia by its game name. Every batch but the
    teleport one plans without teleport, so a teleporting class still walks.
    """
    schedule = load_schedule("physics")
    assert schedule.map == "Victoria Road: Ellinia"
    measured = {trial.measures for _, trial in schedule.trials}
    assert measured == set(Measure)
    for batch, trial in schedule.trials:
        assert batch.teleport == (trial.measures is Measure.TELEPORT)


def test_a_missing_schedule_names_the_ones_that_exist(tmp_path: Path) -> None:
    (tmp_path / "here.json").write_text(json.dumps(MINIMAL), encoding="utf-8")
    with pytest.raises(TrialSpecError, match="here"):
        load_schedule("not-here", directory=tmp_path)


def test_a_schedule_can_be_loaded_by_path(tmp_path: Path) -> None:
    """A one-off schedule kept outside the repo goes through the same loader."""
    path = tmp_path / "adhoc.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    assert load_schedule(str(path)).name == "minimal"


def test_a_schedule_that_is_not_json_says_so(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(TrialSpecError, match="not valid JSON"):
        load_schedule(str(path))


# --- Shape ------------------------------------------------------------------------


def test_trials_are_walked_batch_by_batch_in_file_order() -> None:
    schedule = TrialSchedule.from_json(
        {
            "name": "sweep",
            "map": "GhostShip1",
            "batches": [
                {
                    "name": "first",
                    "trials": [
                        _trial("one"),
                        _trial("two"),
                    ],
                },
                {"name": "second", "trials": [_trial("three")]},
            ],
        }
    )
    walked = [(batch.name, trial.name) for batch, trial in schedule.trials]
    assert walked == [("first", "one"), ("first", "two"), ("second", "three")]


def test_setup_budget_defaults_to_the_measured_budget() -> None:
    spec = TrialSpec("t", (0, 0), (1, 1), 2.0, 20.0)
    assert spec.positioning_budget == 20.0
    assert (
        TrialSpec("t", (0, 0), (1, 1), 2.0, 20.0, setup_budget=5.0).positioning_budget
        == 5.0
    )


# --- Knobs ------------------------------------------------------------------------


def test_a_batch_with_no_knobs_overrides_nothing() -> None:
    batch = TrialBatch.from_json(MINIMAL["batches"][0], "batch")
    assert batch.knobs == Knobs()
    assert batch.knobs.overrides() == {}


@pytest.mark.parametrize("knob", KNOB_NAMES)
def test_every_knob_can_be_set_on_its_own(knob: str) -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["knobs"] = {knob: 3}
    schedule = TrialSchedule.from_json(payload)
    assert schedule.batches[0].knobs.overrides() == {knob: 3.0}


def test_an_unknown_knob_is_rejected_rather_than_ignored() -> None:
    """
    The silent-typo case, and the reason parsing is strict at all: a swept batch
    that quietly swept nothing looks exactly like a batch whose Knob had no effect.
    """
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["knobs"] = {"decision_intervall": 0.25}
    with pytest.raises(TrialSpecError, match="unknown Knob"):
        TrialSchedule.from_json(payload)


@pytest.mark.parametrize("value", [0, -1, "fast", True])
def test_a_knob_must_be_a_positive_number(value: object) -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["knobs"] = {"decision_interval": value}
    with pytest.raises(TrialSpecError):
        TrialSchedule.from_json(payload)


def test_knobs_round_trip_through_json() -> None:
    knobs = Knobs(decision_interval=0.25, precision_threshold=8)
    assert Knobs.from_json(knobs.to_json(), "where") == knobs


# --- Rejections -------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["name", "start", "target", "tolerance", "time_budget"]
)
def test_a_trial_missing_a_required_key_is_rejected(missing: str) -> None:
    payload = json.loads(json.dumps(MINIMAL))
    del payload["batches"][0]["trials"][0][missing]
    with pytest.raises(TrialSpecError, match=missing):
        TrialSchedule.from_json(payload)


@pytest.mark.parametrize("point", [[1], [1, 2, 3], ["a", "b"], [1.5, 2.5], "12,34"])
def test_a_coordinate_must_be_a_pair_of_integers(point: object) -> None:
    with pytest.raises(TrialSpecError, match="pair of integers"):
        TrialSchedule.from_json(_with_trial(start=point))


@pytest.mark.parametrize("field", ["tolerance", "time_budget", "setup_budget"])
def test_a_budget_or_tolerance_must_be_positive(field: str) -> None:
    with pytest.raises(TrialSpecError, match=field):
        TrialSchedule.from_json(_with_trial(**{field: 0}))


def test_an_unexpected_key_is_rejected_at_every_level() -> None:
    with pytest.raises(TrialSpecError, match="epsilon"):
        TrialSchedule.from_json(_with_trial(epsilon=2.0))

    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["repetitions"] = 3
    with pytest.raises(TrialSpecError, match="repetitions"):
        TrialSchedule.from_json(payload)

    payload = json.loads(json.dumps(MINIMAL))
    payload["notes"] = "hello"
    with pytest.raises(TrialSpecError, match="notes"):
        TrialSchedule.from_json(payload)


def test_a_repeated_trial_name_is_rejected_within_a_batch() -> None:
    """
    Names are how a record is grouped for analysis. Two Trials sharing one inside a
    batch would average two different experiments together.
    """
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["trials"].append(_trial("a-to-b"))
    with pytest.raises(TrialSpecError, match="repeats the trial name"):
        TrialSchedule.from_json(payload)


def test_a_repeated_batch_name_is_rejected() -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"].append(json.loads(json.dumps(MINIMAL["batches"][0])))
    with pytest.raises(TrialSpecError, match="repeats the batch name"):
        TrialSchedule.from_json(payload)


def test_an_empty_schedule_is_rejected() -> None:
    with pytest.raises(TrialSpecError, match="non-empty"):
        TrialSchedule.from_json({"name": "n", "map": "m", "batches": []})
    with pytest.raises(TrialSpecError, match="non-empty"):
        TrialSchedule.from_json(
            {"name": "n", "map": "m", "batches": [{"name": "b", "trials": []}]}
        )


def _trial(name: str) -> dict:
    return {
        "name": name,
        "start": [15, 42],
        "target": [109, 42],
        "tolerance": 2.0,
        "time_budget": 20.0,
    }


# --- The map, by game name or id (#397) ------------------------------------------


@pytest.mark.parametrize("value", ["Victoria Road: Ellinia", 10002000])
def test_the_map_is_a_game_name_or_an_id(value: object) -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["map"] = value
    schedule = TrialSchedule.from_json(payload)
    assert schedule.map == value
    assert TrialSchedule.from_json(schedule.to_json()) == schedule


@pytest.mark.parametrize("value", ["", "  ", True, -1, 1.5, None, ["a"]])
def test_a_map_that_is_neither_is_rejected(value: object) -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["map"] = value
    with pytest.raises(TrialSpecError, match="game name"):
        TrialSchedule.from_json(payload)


def test_a_schedule_without_a_map_is_rejected() -> None:
    payload = json.loads(json.dumps(MINIMAL))
    del payload["map"]
    with pytest.raises(TrialSpecError, match="'map'"):
        TrialSchedule.from_json(payload)


class _Catalogue:
    def map(self, name_or_id: object) -> object:
        if name_or_id == "Mushroom Town":
            raise LookupError("'Mushroom Town' matches several maps: 200, 201")
        return type("MapData", (), {"id": 10002000})()


def test_the_catalogue_resolves_the_schedule_s_map() -> None:
    schedule = TrialSchedule.from_json({**MINIMAL, "map": "Victoria Road: Ellinia"})
    assert schedule_map_id(schedule, _Catalogue()) == 10002000  # type: ignore[arg-type]


def test_an_ambiguous_map_name_is_a_spec_error_listing_the_ids() -> None:
    schedule = TrialSchedule.from_json({**MINIMAL, "map": "Mushroom Town"})
    with pytest.raises(TrialSpecError, match="200, 201"):
        schedule_map_id(schedule, _Catalogue())  # type: ignore[arg-type]


# --- What a Trial measures, and batches without teleport -------------------------


def test_a_trial_may_say_what_it_measures() -> None:
    schedule = TrialSchedule.from_json(_with_trial(measures="rope_jump"))
    assert schedule.trials[0][1].measures is Measure.ROPE_JUMP
    assert TrialSchedule.from_json(schedule.to_json()) == schedule


def test_an_unknown_measure_is_rejected() -> None:
    with pytest.raises(TrialSpecError, match="walk, climb"):
        TrialSchedule.from_json(_with_trial(measures="swim"))


def test_a_batch_plans_with_teleport_unless_it_says_not() -> None:
    assert TrialSchedule.from_json(MINIMAL).batches[0].teleport is True
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["teleport"] = False
    schedule = TrialSchedule.from_json(payload)
    assert schedule.batches[0].teleport is False
    assert TrialSchedule.from_json(schedule.to_json()) == schedule


def test_a_batch_s_teleport_must_be_true_or_false() -> None:
    payload = json.loads(json.dumps(MINIMAL))
    payload["batches"][0]["teleport"] = "no"
    with pytest.raises(TrialSpecError, match="true or false"):
        TrialSchedule.from_json(payload)


# --- No Trial code reads the map files (#397) -------------------------------------


def test_no_trial_code_reads_the_map_files() -> None:
    """
    #302 acceptance criterion 11: the Trial framework names maps by game name and
    judges in virtual px, so it keeps working once `configs/maps` is retired (#399).
    Checked on the code itself: no import of the map-file modules, no read of the
    map-file attributes, and no path into `configs/maps`.
    """
    import ast

    from paths import ROOT

    root = Path(ROOT)
    files = [
        *sorted((root / "maple" / "calibration").glob("*.py")),
        root / "maple" / "decision_makers" / "trial_runner.py",
        root / "maple" / "bots" / "calibration.py",
    ]
    banned_modules = ("minimap_creation", "maple_map", "minimap_edits_model")
    banned_attributes = {
        "current_map",
        "current_minimap",
        "current_minimap_position",
        "current_grid",
        "game_map",
        "MapleMinimap",
        "MinimapEditsManager",
        "MinimapGrid",
        "MinimapPhysics",
    }
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, documented)
            and node.body
            and isinstance(node.body[0], ast.Expr)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom | ast.Import):
                names = [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                names += [alias.name for alias in node.names]
                assert not any(b in n for n in names for b in banned_modules), path
                assert not banned_attributes & set(names), path
            if isinstance(node, ast.Attribute):
                assert node.attr not in banned_attributes, (path, node.attr)
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                assert "configs/maps" not in node.value.replace("\\", "/"), path
