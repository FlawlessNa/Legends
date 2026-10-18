"""
Which model runs a stage, routed from a table rather than chosen by the agent.

An agent asked to pick its own model picks the strong one every time: it costs
nothing it can see and it is never wrong from where it sits. So the Foreman
asks this module, and the answer is a function of the table, the stage and the
ticket's artifact chain -- nothing else. No network, no clock, no probing of
what the subscription actually has.

Two error classes, deliberately distinct, because the remedies differ:

- an **argument** error means the caller asked wrongly -> `MISUSE`
- a **table** error means the maintainer's file is wrong -> `NEEDS_HUMAN`

Neither ever resolves to a model. A silent fallback to the strong one turns a
typo into a bill, which is the one error class this repo has no test for.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from factory.chain import Chain
from factory.routing import Stage

#: Where the table lives, relative to the repo root. Not inside the package:
#: `pyproject.toml` declares no `package-data`, so a `.toml` under `factory/`
#: is not installed -- and adding one means editing a hard-stop path.
TABLE_PATH: Final = Path("configs") / "factory-models.toml"

#: Weakest to strongest. An override may only move a stage up this list, which
#: is checkable only because the order is declared.
TIER_ORDER: Final[tuple[str, ...]] = ("trivial", "standard", "complex")

#: The tier a stage gets when the table does not name it. Never an error:
#: `standard` cannot silently spend on the strong model, and halting the
#: Foreman over a stage the table forgot is the worse of the two failures.
DEFAULT_TIER: Final = "standard"

#: The stage no agent runs. CI decides the merge (#194), so the answer is a
#: definite "nobody" rather than a refusal to answer.
NO_AGENT: Final = Stage.INTEGRATE


class TableError(Exception):
    """
    The table is wrong, and only the maintainer can settle it.

    Maps to `NEEDS_HUMAN`, not `MISUSE`: nothing about the invocation was
    wrong, and `MISUSE`'s documented remedy -- re-read `factory next` -- is
    useless advice for a malformed config file.
    """


def _strip(value: str) -> str:
    """Whitespace, surrounding quotes, case. The stripping `verdict_of` does."""
    return value.strip().strip("\"'").lower()


def _method_live(chain: Chain | None) -> bool:
    """
    Whether the ticket can only be settled by watching a client.

    `both` counts as well as `live`, matching `chain.needs_qa`. Were it `live`
    alone, a `method: both` ticket would get a weaker model at Review than an
    otherwise identical `live` one, for a distinction that means nothing here.

    False before `spec.md` exists. That is "not yet knowable", not an error:
    the override simply does not fire.
    """
    if chain is None:
        return False
    return _strip(chain.spec.get("method", "")) in {"live", "both"}


#: The closed vocabulary of facts an override may name. A `when` key outside it
#: is a table error, because an override that silently never fires is a policy
#: the maintainer believes is in force and is not.
FACTS: Final[Mapping[str, Callable[[Chain | None], bool]]] = {
    "method_live": _method_live,
}


@dataclass(frozen=True)
class Override:
    """One `[[overrides]]` entry, keeping its file position."""

    when: Mapping[str, bool]
    use: str
    index: int

    def matches(self, chain: Chain | None) -> bool:
        """Every fact must hold: a multi-key `when` is AND."""
        return all(FACTS[key](chain) is value for key, value in self.when.items())


@dataclass(frozen=True)
class Table:
    """A validated model table. An invalid table never becomes one."""

    tiers: Mapping[str, tuple[str, ...]]
    by_stage: Mapping[Stage, str]
    overrides: tuple[Override, ...]
    unavailable: frozenset[str]

    def model_for(self, tier: str) -> str:
        """The first name in the tier's chain that is not unavailable."""
        for name in self.tiers[tier]:
            if name not in self.unavailable:
                return name
        raise TableError(  # pragma: no cover - `load` rejects this first
            f"every model in tier {tier!r} is unavailable"
        )


@dataclass(frozen=True)
class Choice:
    """A resolution, and the rule that produced it."""

    model: str | None
    tier: str | None
    rule: str

    @property
    def record(self) -> str:
        """
        The line the Foreman writes into the chain, so a bad result traces back
        to the model that produced it. #159 decides which file carries it.
        """
        if self.model is None:
            return f"model: null  # {self.rule}"
        return f"model: {self.model}  # tier={self.tier}, rule={self.rule}"


def _block(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise TableError(f"the table needs a [{key}] block, got {value!r}")
    return value


def _tiers_of(raw: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    tiers: dict[str, tuple[str, ...]] = {}
    for name, chain in _block(raw, "tiers").items():
        if name not in TIER_ORDER:
            raise TableError(f"tier {name!r} is not one of {list(TIER_ORDER)}")
        if not isinstance(chain, list) or not chain:
            raise TableError(f"tier {name!r} must be a non-empty list of models")
        tiers[name] = tuple(str(item) for item in chain)
    if DEFAULT_TIER not in tiers:
        raise TableError(
            f"[tiers] must define {DEFAULT_TIER!r}: it is what a stage the "
            f"table does not name resolves to."
        )
    return tiers


def _stages_of(raw: dict[str, Any], tiers: Mapping[str, object]) -> dict[Stage, str]:
    stages: dict[Stage, str] = {}
    for key, tier in _block(raw, "by_stage").items():
        try:
            stage = Stage(key)
        except ValueError as unknown:
            raise TableError(
                f"{key!r} is not a stage. The stages are "
                f"{[str(member) for member in Stage]}."
            ) from unknown
        if tier not in tiers:
            raise TableError(f"stage {key!r} names undefined tier {tier!r}")
        stages[stage] = str(tier)
    return stages


def _overrides_of(raw: dict[str, Any], tiers: Mapping[str, object]) -> list[Override]:
    overrides: list[Override] = []
    for index, entry in enumerate(raw.get("overrides", [])):
        when, use = entry.get("when"), entry.get("use")
        if not isinstance(when, dict) or not when:
            raise TableError(f"override {index} needs a non-empty `when`, got {when!r}")
        if use not in tiers:
            raise TableError(f"override {index} names undefined tier {use!r}")
        for key, value in when.items():
            if key not in FACTS:
                raise TableError(
                    f"override {index} names unknown fact {key!r}. "
                    f"The facts are {sorted(FACTS)}."
                )
            if not isinstance(value, bool):
                raise TableError(
                    f"override {index} compares fact {key!r} to {value!r}. "
                    f"The facts are predicates: write true or false, or the "
                    f"comparison can never hold and the override is dead."
                )
        overrides.append(Override(when=dict(when), use=str(use), index=index))
    return overrides


def _check_availability(
    tiers: Mapping[str, tuple[str, ...]], unavailable: frozenset[str]
) -> None:
    """
    The two ways the one line a maintainer edits can be wrong.

    A name in `unavailable` that is in no tier is almost always a typo, and the
    consequence is the one this module exists to prevent: `complex` resolving
    to a model nobody has, at exit 0, with a confident reason.
    """
    every_model = {name for chain in tiers.values() for name in chain}
    stray = sorted(unavailable - every_model)
    if stray:
        raise TableError(
            f"unavailable names {stray}, which appear in no tier. A typo here "
            f"would leave a tier resolving to a model that does not exist."
        )
    for tier, chain in tiers.items():
        if all(name in unavailable for name in chain):
            raise TableError(f"every model in tier {tier!r} is declared unavailable")


def _check_escalation(overrides: list[Override], by_stage: Mapping[Stage, str]) -> None:
    """
    An override must be able to escalate *something*.

    Resolution never demotes, so a demoting override would not run a weak model
    -- it would silently never fire, which is the other failure this table is
    meant not to have: a policy the maintainer believes is in force and is not.
    An override is therefore dead unless its tier is above the weakest tier any
    stage holds, and dead config is a table error.
    """
    floor = min(
        (TIER_ORDER.index(tier) for tier in by_stage.values()),
        default=TIER_ORDER.index(DEFAULT_TIER),
    )
    for override in overrides:
        if TIER_ORDER.index(override.use) <= floor:
            raise TableError(
                f"override {override.index} uses tier {override.use!r}, which "
                f"is not above {TIER_ORDER[floor]!r} -- the weakest tier any "
                f"stage holds -- so it can never escalate anything. An "
                f"override may only escalate; routing down is a decision, not "
                f"a config."
            )


def load(path: Path) -> Table:
    """
    Read and fully validate the table, or raise `TableError`.

    Validation covers the **whole** file, not the part a given call touches: a
    transposed name in `unavailable` is an error on the first call, not on the
    one that happens to need that tier.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as missing:
        raise TableError(f"no model table at {path}: {missing}") from missing
    except tomllib.TOMLDecodeError as broken:
        raise TableError(f"{path} is not valid TOML: {broken}") from broken

    tiers = _tiers_of(raw)
    by_stage = _stages_of(raw, tiers)
    overrides = _overrides_of(raw, tiers)
    unavailable = frozenset(str(name) for name in raw.get("unavailable", []))

    _check_availability(tiers, unavailable)
    _check_escalation(overrides, by_stage)

    return Table(
        tiers=tiers,
        by_stage=by_stage,
        overrides=tuple(overrides),
        unavailable=unavailable,
    )


def resolve(table: Table, stage: Stage, chain: Chain | None = None) -> Choice:
    """
    The model for one stage of one ticket, and the rule that chose it.

    `chain` is optional because `--stage` can be asked with no ticket. `None`
    means every fact is "not yet knowable", so no override fires -- the correct
    answer rather than a degraded one.
    """
    if stage is NO_AGENT:
        return Choice(
            model=None,
            tier=None,
            rule="no agent runs integrate: CI decides the merge (#194)",
        )

    tier = table.by_stage.get(stage)
    rule = f"stage table: {stage}"
    if tier is None:
        tier = DEFAULT_TIER
        rule = f"default: the table does not name {stage}"

    for override in table.overrides:
        if not override.matches(chain):
            continue
        #: First match wins, whether or not it raises the tier. A stage already
        #: at or above it keeps what it had: resolution never demotes.
        if TIER_ORDER.index(override.use) > TIER_ORDER.index(tier):
            tier = override.use
            rule = f"override {override.index}: {dict(override.when)}"
        break

    return Choice(model=table.model_for(tier), tier=tier, rule=rule)
