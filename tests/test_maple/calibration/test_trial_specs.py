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
    Knobs,
    TrialBatch,
    TrialSchedule,
    TrialSpec,
    TrialSpecError,
    available,
    load_schedule,
    render_schedule,
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
    assert schedule.map_name == "GhostShip1"
    assert schedule.batches
    assert "example" in available()


def test_the_example_schedule_round_trips_through_its_renderer() -> None:
    schedule = load_schedule("example")
    reloaded = TrialSchedule.from_json(json.loads(render_schedule(schedule)))
    assert reloaded == schedule


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
