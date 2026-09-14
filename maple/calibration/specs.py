"""
Trial specs: the checked-in, reproducible definition of a calibration experiment.

A **Trial** is one closed-loop movement run (`CONTEXT.md` -> Movement calibration).
This module holds the half of it that is *checked in*: where a Trial starts, where
it is aiming, how close counts as arrived, and how long it may take. The other half
- what actually happened - is a Trial record, and those are per-machine artifacts
(`maple/calibration/records.py`).

The nesting is Schedule -> Batch -> Trial, and it exists for one reason: **Knobs**
are a per-batch override. A sweep is therefore several batches over the same trial
list, and lives in one file a reviewer can read top to bottom, rather than in
several files whose only difference is a number.

Parsing is strict. An unknown key, an unknown Knob, or a non-positive tolerance is a
`TrialSpecError` and not a silently-ignored line: a typo that quietly disables the
Knob being swept produces a batch that measures the default twice and looks like a
result.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from paths import ROOT

#: Where checked-in schedules live. Beside the map JSON, because a schedule names a
#: map and is the same kind of thing: shared project data, not per-user config.
TRIALS_DIR: Final = Path(ROOT) / "configs" / "trials"

#: Every Knob's field name, in declaration order. The one list a new Knob is added to.
KNOB_NAMES: Final[tuple[str, ...]] = (
    "decision_interval",
    "action_duration",
    "precision_threshold",
    "edge_departure_threshold",
)


class TrialSpecError(ValueError):
    """A schedule file is missing, malformed, or asks for something that isn't."""


# --- Knobs ------------------------------------------------------------------------


@dataclass(frozen=True)
class Knobs:
    """
    The controller parameters a batch may override, `None` meaning "leave the
    production default alone".

    Four today, named by what they control rather than by the symbol that holds
    them, so a rename in the movement layer does not invalidate a checked-in
    schedule:

    * ``decision_interval`` - how often the calibration bot's DecisionMaker decides,
      i.e. `DecisionMaker._throttle`.
    * ``action_duration`` - the Action duration cap a Movement Plan is compiled
      against, i.e. `data.action_duration`.
    * ``precision_threshold`` - the platform width (minimap pixels) at or below which
      a jump or teleport gets the landing direction-stop, i.e. `MovementHandler`'s
      ``narrow_platform_threshold``.
    * ``edge_departure_threshold`` - the distance (minimap pixels) from a platform's
      end, in the travel direction, within which a jump or teleport gets the
      pre-departure stop, i.e. `MovementHandler`'s ``edge_departure_threshold``.

    Extending this is one field here plus one line in `KNOB_NAMES`; every consumer
    reads Knobs through this object, so nothing else has to learn the new name.
    """

    decision_interval: float | None = None
    action_duration: float | None = None
    precision_threshold: float | None = None
    edge_departure_threshold: float | None = None

    def overrides(self) -> dict[str, float]:
        """Only the Knobs this batch actually sets - the rest keep their defaults."""
        return {
            name: value
            for name in KNOB_NAMES
            if (value := getattr(self, name)) is not None
        }

    def to_json(self) -> dict[str, Any]:
        return dict(self.overrides())

    @classmethod
    def from_json(cls, payload: object, where: str) -> Knobs:
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise TrialSpecError(f"{where}.knobs must be a mapping.")
        unknown = set(payload) - set(KNOB_NAMES)
        if unknown:
            raise TrialSpecError(
                f"{where}.knobs has unknown Knob(s): {', '.join(sorted(unknown))}. "
                f"Known Knobs: {', '.join(KNOB_NAMES)}."
            )
        knobs = cls()
        for name, value in payload.items():
            knobs = replace(knobs, **{name: _positive(value, f"{where}.knobs.{name}")})
        return knobs


# --- The schedule -----------------------------------------------------------------


@dataclass(frozen=True)
class TrialSpec:
    """
    One Trial: get to ``start``, then go to ``target`` and see how that goes.

    The run is two phases, and only the second is measured. A Trial whose character
    began somewhere else measures the wrong thing, so the framework walks to
    ``start`` first (the positioning phase, budgeted by ``setup_budget``) and only
    then starts the clock on ``time_budget``. Both phases share ``tolerance``: what
    counts as "at the target" is what counts as "at the start".
    """

    name: str
    start: tuple[int, int]
    target: tuple[int, int]
    tolerance: float
    time_budget: float
    setup_budget: float | None = None

    @property
    def positioning_budget(self) -> float:
        """How long the walk to ``start`` may take; the measured budget by default."""
        return self.time_budget if self.setup_budget is None else self.setup_budget

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "start": list(self.start),
            "target": list(self.target),
            "tolerance": self.tolerance,
            "time_budget": self.time_budget,
        }
        if self.setup_budget is not None:
            payload["setup_budget"] = self.setup_budget
        return payload

    @classmethod
    def from_json(cls, payload: object, where: str) -> TrialSpec:
        if not isinstance(payload, dict):
            raise TrialSpecError(f"{where} must be a mapping.")
        _reject_unknown(payload, _TRIAL_KEYS, where)
        for required in ("name", "start", "target", "tolerance", "time_budget"):
            if required not in payload:
                raise TrialSpecError(f"{where} is missing required key '{required}'.")
        return cls(
            name=str(payload["name"]),
            start=_point(payload["start"], f"{where}.start"),
            target=_point(payload["target"], f"{where}.target"),
            tolerance=_positive(payload["tolerance"], f"{where}.tolerance"),
            time_budget=_positive(payload["time_budget"], f"{where}.time_budget"),
            setup_budget=(
                _positive(payload["setup_budget"], f"{where}.setup_budget")
                if payload.get("setup_budget") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class TrialBatch:
    """A run of Trials sharing one set of Knob overrides. The unit a sweep varies."""

    name: str
    trials: tuple[TrialSpec, ...]
    knobs: Knobs = Knobs()

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        knobs = self.knobs.to_json()
        if knobs:
            payload["knobs"] = knobs
        payload["trials"] = [trial.to_json() for trial in self.trials]
        return payload

    @classmethod
    def from_json(cls, payload: object, where: str) -> TrialBatch:
        if not isinstance(payload, dict):
            raise TrialSpecError(f"{where} must be a mapping.")
        _reject_unknown(payload, _BATCH_KEYS, where)
        if not payload.get("name"):
            raise TrialSpecError(f"{where} is missing required key 'name'.")
        raw_trials = payload.get("trials")
        if not isinstance(raw_trials, list) or not raw_trials:
            raise TrialSpecError(f"{where}.trials must be a non-empty list.")
        trials = tuple(
            TrialSpec.from_json(entry, f"{where}.trials[{i}]")
            for i, entry in enumerate(raw_trials)
        )
        _reject_duplicates(
            [trial.name for trial in trials], f"{where}.trials", "trial name"
        )
        return cls(
            name=str(payload["name"]),
            trials=trials,
            knobs=Knobs.from_json(payload.get("knobs"), where),
        )


@dataclass(frozen=True)
class TrialSchedule:
    """
    A whole checked-in experiment: which map, and the batches to walk in order.

    One map per schedule. A Trial's coordinates are minimap coordinates and mean
    nothing off their own map, so a schedule spanning two maps would be two
    experiments sharing a filename.
    """

    name: str
    map_name: str
    batches: tuple[TrialBatch, ...]
    description: str = ""

    @property
    def trials(self) -> tuple[tuple[TrialBatch, TrialSpec], ...]:
        """Every Trial in walking order, each paired with the batch it belongs to."""
        return tuple((batch, trial) for batch in self.batches for trial in batch.trials)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "map": self.map_name}
        if self.description:
            payload["description"] = self.description
        payload["batches"] = [batch.to_json() for batch in self.batches]
        return payload

    @classmethod
    def from_json(cls, payload: object, where: str = "schedule") -> TrialSchedule:
        if not isinstance(payload, dict):
            raise TrialSpecError(f"{where} must be a top-level mapping.")
        _reject_unknown(payload, _SCHEDULE_KEYS, where)
        for required in ("name", "map"):
            if not payload.get(required):
                raise TrialSpecError(f"{where} is missing required key '{required}'.")
        raw_batches = payload.get("batches")
        if not isinstance(raw_batches, list) or not raw_batches:
            raise TrialSpecError(f"{where}.batches must be a non-empty list.")
        batches = tuple(
            TrialBatch.from_json(entry, f"{where}.batches[{i}]")
            for i, entry in enumerate(raw_batches)
        )
        _reject_duplicates(
            [batch.name for batch in batches], f"{where}.batches", "batch name"
        )
        return cls(
            name=str(payload["name"]),
            map_name=str(payload["map"]),
            batches=batches,
            description=str(payload.get("description", "")),
        )


# --- Loading ----------------------------------------------------------------------


def available(directory: Path | None = None) -> list[str]:
    """Every schedule on disk, by name."""
    root = TRIALS_DIR if directory is None else directory
    if not root.is_dir():
        return []
    return sorted(path.stem for path in root.glob("*.json"))


def load_schedule(name: str, directory: Path | None = None) -> TrialSchedule:
    """
    Read and validate ``configs/trials/<name>.json`` (or a path to one).

    Accepts a bare name or a filesystem path, so a one-off schedule kept outside the
    repo runs through the same loader as a checked-in one.
    """
    root = TRIALS_DIR if directory is None else directory
    path = Path(name)
    if not path.suffix:
        path = root / f"{name}.json"
    if not path.exists():
        known = available(root)
        hint = (
            f"Available schedules: {', '.join(known)}"
            if known
            else f"No schedules exist yet -- add one under {root}."
        )
        raise TrialSpecError(f"No trial schedule at {path}.\n{hint}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrialSpecError(f"{path} is not valid JSON:\n{exc}") from exc
    return TrialSchedule.from_json(payload, os.path.basename(str(path)))


def render_schedule(schedule: TrialSchedule) -> str:
    """
    The file's exact text: what a generator writes, and what a round-trip check
    compares against.
    """
    return json.dumps(schedule.to_json(), indent=2) + "\n"


# --- Parsing helpers --------------------------------------------------------------

_TRIAL_KEYS: Final = frozenset(
    {"name", "start", "target", "tolerance", "time_budget", "setup_budget"}
)
_BATCH_KEYS: Final = frozenset({"name", "knobs", "trials"})
_SCHEDULE_KEYS: Final = frozenset({"name", "map", "description", "batches"})


def _reject_unknown(payload: dict[str, Any], known: frozenset[str], where: str) -> None:
    unknown = set(payload) - known
    if unknown:
        raise TrialSpecError(
            f"{where} has unexpected key(s): {', '.join(sorted(unknown))}."
        )


def _reject_duplicates(names: list[str], where: str, what: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise TrialSpecError(f"{where} repeats the {what} '{name}'.")
        seen.add(name)


def _point(value: object, where: str) -> tuple[int, int]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        raise TrialSpecError(f"{where} must be a pair of integers, e.g. [12, 34].")
    return int(value[0]), int(value[1])


def _positive(value: object, where: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TrialSpecError(f"{where} must be a number.")
    if value <= 0:
        raise TrialSpecError(f"{where} must be positive.")
    return float(value)
