"""
The model table: every validation, the default, and the one override.

These tests exist because the failure this table prevents is silent. A wrong
answer here is not a crash, it is a session started on the wrong model -- or,
in the case the review caught, on a model that does not exist -- with an exit
code of 0 and a confident reason attached.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from factory.chain import Chain, read_chain
from factory.models import (
    DEFAULT_TIER,
    TABLE_PATH,
    TIER_ORDER,
    TableError,
    load,
    resolve,
)
from factory.routing import Stage

TICKET = 7

MINIMAL = """
unavailable = []
[tiers]
trivial  = ["haiku"]
standard = ["sonnet"]
complex  = ["fable", "opus"]
[by_stage]
design = "complex"
qa = "standard"
"""


def _table(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "models.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _chain(tmp_path: Path, method: str) -> Chain:
    """A chain whose `spec.md` records a verification method."""
    root = tmp_path / ".factory" / str(TICKET)
    root.mkdir(parents=True, exist_ok=True)
    (root / "spec.md").write_text(
        f"---\nticket: {TICKET}\nmethod: {method}\n---\n", encoding="utf-8"
    )
    return read_chain(tmp_path, TICKET)


# --- The shipped table -------------------------------------------------------
#
# Not a fixture's table: the real one. A table that only a fixture exercises is
# a table nobody has checked.


def _shipped() -> Path:
    return Path(__file__).resolve().parents[2] / TABLE_PATH


def test_the_shipped_table_loads() -> None:
    """If this fails, `factory model` is broken for every ticket."""
    assert load(_shipped()).by_stage


def test_the_shipped_table_resolves_every_stage_to_something() -> None:
    table = load(_shipped())
    for stage in Stage:
        choice = resolve(table, stage)
        assert choice.rule, f"{stage} resolved with no reason given"
        if stage is not Stage.INTEGRATE:
            assert choice.model, f"{stage} resolved to no model"


def test_the_shipped_table_routes_judgement_to_the_strong_tier() -> None:
    """The policy's whole point: Design and Review are not where to be cheap."""
    table = load(_shipped())
    assert table.by_stage[Stage.DESIGN] == "complex"
    assert table.by_stage[Stage.REVIEW] == "complex"


def test_the_shipped_table_routes_nothing_to_trivial() -> None:
    """`trivial` is reserved, not a budget. A stage on it is a ticket, not an edit."""
    table = load(_shipped())
    assert "trivial" not in table.by_stage.values()


def test_the_shipped_table_declares_fable_unavailable_so_complex_is_opus() -> None:
    """
    The documented state of the subscription, and the one line meant to change.

    This test is what makes enabling Fable visible: delete the `unavailable`
    entry and this goes red, which is the reminder to update it deliberately.
    """
    table = load(_shipped())
    assert "fable" in table.unavailable
    assert table.model_for("complex") == "opus"
    assert resolve(table, Stage.DESIGN).model == "opus"


def test_every_shipped_stage_key_is_a_real_stage() -> None:
    """The table cannot drift from the vocabulary `factory next` uses."""
    raw = tomllib.loads(_shipped().read_text(encoding="utf-8"))
    for key in raw["by_stage"]:
        assert key in {str(member) for member in Stage}


# --- Tiers and availability --------------------------------------------------


def test_an_unavailable_first_entry_is_skipped(tmp_path: Path) -> None:
    table = load(_table(tmp_path, MINIMAL.replace("[]", '["fable"]')))
    assert table.model_for("complex") == "opus"


def test_an_available_first_entry_wins(tmp_path: Path) -> None:
    """Deleting the `unavailable` entry is the whole of enabling Fable."""
    table = load(_table(tmp_path, MINIMAL))
    assert table.model_for("complex") == "fable"


def test_a_name_in_unavailable_that_is_in_no_tier_is_a_table_error(
    tmp_path: Path,
) -> None:
    """
    The review's finding: one transposition, and `complex` resolves to a model
    nobody has, at exit 0, with a confident reason.
    """
    with pytest.raises(TableError, match="appear in no tier"):
        load(_table(tmp_path, MINIMAL.replace("[]", '["fabel"]')))


def test_a_wholly_unavailable_tier_is_a_table_error(tmp_path: Path) -> None:
    with pytest.raises(TableError, match="declared unavailable"):
        load(_table(tmp_path, MINIMAL.replace("[]", '["fable", "opus"]')))


def test_an_empty_tier_is_a_table_error(tmp_path: Path) -> None:
    with pytest.raises(TableError, match="non-empty list"):
        load(_table(tmp_path, MINIMAL.replace('trivial  = ["haiku"]', "trivial = []")))


def test_an_unknown_tier_name_is_a_table_error(tmp_path: Path) -> None:
    """A fourth tier has no place in the order, so "only escalate" loses meaning."""
    with pytest.raises(TableError, match="not one of"):
        load(_table(tmp_path, MINIMAL.replace("[tiers]", '[tiers]\ncheap = ["x"]')))


def test_a_missing_standard_tier_is_a_table_error(tmp_path: Path) -> None:
    """It is what an unnamed stage falls back to, so it cannot be absent."""
    with pytest.raises(TableError, match="must define"):
        load(_table(tmp_path, MINIMAL.replace('standard = ["sonnet"]', "")))


# --- Stages ------------------------------------------------------------------


def test_a_stage_absent_from_the_table_gets_the_default(tmp_path: Path) -> None:
    """
    Restored on the review's argument: `standard` can never silently spend on
    the strong model, so halting the Foreman over a forgotten stage is worse.
    """
    choice = resolve(load(_table(tmp_path, MINIMAL)), Stage.DOCUMENT)
    assert choice.tier == DEFAULT_TIER
    assert choice.model == "sonnet"
    assert "does not name" in choice.rule


def test_a_table_key_that_is_not_a_stage_is_a_table_error(tmp_path: Path) -> None:
    """`spec-review` is the real case: a role inside Design, not a stage."""
    with pytest.raises(TableError, match="is not a stage"):
        load(_table(tmp_path, MINIMAL + '\nspec-review = "complex"\n'))


def test_a_stage_naming_an_undefined_tier_is_a_table_error(tmp_path: Path) -> None:
    with pytest.raises(TableError, match="undefined tier"):
        load(_table(tmp_path, MINIMAL.replace('qa = "standard"', 'qa = "cheap"')))


def test_integrate_answers_no_model_rather_than_refusing(tmp_path: Path) -> None:
    """
    A definite "nobody runs this" is an answer. Refusing forced the Foreman to
    special-case `integrate` before calling -- to know what it was asking about.
    """
    choice = resolve(load(_table(tmp_path, MINIMAL)), Stage.INTEGRATE)
    assert choice.model is None
    assert choice.tier is None
    assert "no agent" in choice.rule
    assert choice.record == f"model: null  # {choice.rule}"


# --- Overrides ---------------------------------------------------------------
#
# The review rebuilt this part. The first draft shipped three overrides whose
# facts could not be evaluated at any stage, so every call on every ticket
# would have errored.

LIVE_OVERRIDE = """
unavailable = []
[tiers]
trivial  = ["haiku"]
standard = ["sonnet"]
complex  = ["fable", "opus"]
[by_stage]
qa = "standard"
review = "standard"
[[overrides]]
when = { method_live = true }
use  = "complex"
"""


def test_an_override_beats_the_stage_table(tmp_path: Path) -> None:
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    choice = resolve(table, Stage.QA, _chain(tmp_path, "live"))
    assert choice.tier == "complex"
    assert "override 0" in choice.rule


def test_an_override_whose_fact_is_false_does_not_fire(tmp_path: Path) -> None:
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    choice = resolve(table, Stage.QA, _chain(tmp_path, "suite"))
    assert choice.tier == "standard"
    assert "stage table" in choice.rule


@pytest.mark.parametrize("method", ["live", "both"])
def test_method_live_covers_both(tmp_path: Path, method: str) -> None:
    """
    Otherwise the same ticket gets two models for a distinction that means
    nothing here. `chain.needs_qa` already treats them alike.
    """
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    assert resolve(table, Stage.REVIEW, _chain(tmp_path, method)).tier == "complex"


def test_a_quoted_method_still_matches(tmp_path: Path) -> None:
    """
    `front_matter` does not strip quotes. Without the same stripping
    `verdict_of` does, `method: "live"` would silently never fire -- a policy
    the maintainer believes is in force and is not.
    """
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    assert resolve(table, Stage.QA, _chain(tmp_path, '"LIVE"')).tier == "complex"


def test_no_chain_means_no_override_fires(tmp_path: Path) -> None:
    """`--stage` with no ticket: every fact is "not yet knowable", not false."""
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    assert resolve(table, Stage.QA, None).tier == "standard"


def test_a_ticket_before_its_spec_exists_does_not_fire_an_override(
    tmp_path: Path,
) -> None:
    """
    The case that broke the first draft: at `plan` and `design` there is no
    `spec.md`, so `method_live` is unknowable. It must not be an error.
    """
    (tmp_path / ".factory" / str(TICKET)).mkdir(parents=True)
    chain = read_chain(tmp_path, TICKET)
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    assert resolve(table, Stage.QA, chain).tier == "standard"


def test_the_first_matching_override_wins(tmp_path: Path) -> None:
    """
    File order, not specificity, so a reader can predict the answer from the
    file. The second override here would reach the same tier by another rule;
    the `rule` field proves which one was consulted.
    """
    two = (
        LIVE_OVERRIDE
        + '\n[[overrides]]\nwhen = { method_live = true }\nuse = "complex"\n'
    )
    choice = resolve(load(_table(tmp_path, two)), Stage.QA, _chain(tmp_path, "live"))
    assert "override 0" in choice.rule


def test_a_multi_key_when_is_and(tmp_path: Path) -> None:
    """Both facts must hold. Only one exists today, so this pins the semantics."""
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    assert table.overrides[0].when == {"method_live": True}
    assert not table.overrides[0].matches(_chain(tmp_path, "suite"))


def test_an_override_that_could_only_demote_is_a_table_error(tmp_path: Path) -> None:
    """
    The review's finding. Resolution never demotes, so such an override would
    not run a weak model -- it would silently never fire, which is worse.
    """
    with pytest.raises(TableError, match="can never escalate"):
        load(
            _table(
                tmp_path, LIVE_OVERRIDE.replace('use  = "complex"', 'use = "trivial"')
            )
        )


def test_an_override_naming_an_unknown_fact_is_a_table_error(tmp_path: Path) -> None:
    """
    `touches_hard_stop` is the real case: it needs the radius, which is the
    output of stage 3, so it cannot ship until #143 lands.
    """
    with pytest.raises(TableError, match="unknown fact"):
        load(
            _table(
                tmp_path,
                LIVE_OVERRIDE.replace("method_live = true", "touches_hard_stop = true"),
            )
        )


def test_an_override_comparing_a_fact_to_a_non_boolean_is_a_table_error(
    tmp_path: Path,
) -> None:
    """Otherwise the comparison can never hold and the override is dead config."""
    with pytest.raises(TableError, match="predicates"):
        load(
            _table(
                tmp_path,
                LIVE_OVERRIDE.replace("method_live = true", 'method_live = "yes"'),
            )
        )


def test_an_empty_when_is_a_table_error(tmp_path: Path) -> None:
    """It would match every stage, which is the stage table with extra steps."""
    with pytest.raises(TableError, match="non-empty"):
        load(_table(tmp_path, LIVE_OVERRIDE.replace("{ method_live = true }", "{}")))


def test_an_override_naming_an_undefined_tier_is_a_table_error(tmp_path: Path) -> None:
    with pytest.raises(TableError, match="undefined tier"):
        load(
            _table(tmp_path, LIVE_OVERRIDE.replace('use  = "complex"', 'use = "huge"'))
        )


# --- The table as a whole ----------------------------------------------------


def test_a_missing_table_is_a_table_error(tmp_path: Path) -> None:
    """Not MISUSE: the caller did not write this file."""
    with pytest.raises(TableError, match="no model table"):
        load(tmp_path / "absent.toml")


def test_unparseable_toml_is_a_table_error(tmp_path: Path) -> None:
    with pytest.raises(TableError, match="not valid TOML"):
        load(_table(tmp_path, "unavailable = [\n"))


@pytest.mark.parametrize("block", ["tiers", "by_stage"])
def test_a_missing_block_is_a_table_error(tmp_path: Path, block: str) -> None:
    with pytest.raises(TableError, match=rf"\[{block}\] block"):
        load(_table(tmp_path, MINIMAL.replace(f"[{block}]", "[ignored]")))


def test_validation_covers_the_whole_table_not_the_part_asked_about(
    tmp_path: Path,
) -> None:
    """
    A transposed name must be an error on the first call, not on the one that
    happens to need that tier. `trivial` is routed to by nothing, and a typo
    in it still fails to load.
    """
    broken = MINIMAL.replace('trivial  = ["haiku"]', 'trivial = ["haiku"]').replace(
        "unavailable = []", 'unavailable = ["haiko"]'
    )
    with pytest.raises(TableError, match="appear in no tier"):
        load(_table(tmp_path, broken))


def test_the_tier_order_is_weakest_first() -> None:
    """`_check_escalation` and the resolve-time guard both read this order."""
    assert TIER_ORDER == ("trivial", "standard", "complex")
    assert DEFAULT_TIER in TIER_ORDER


def test_the_same_inputs_always_give_the_same_answer(tmp_path: Path) -> None:
    """No network, no clock: the Foreman's choice is reproducible from the file."""
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    chain = _chain(tmp_path, "live")
    assert resolve(table, Stage.QA, chain) == resolve(table, Stage.QA, chain)


def test_the_record_names_the_model_the_tier_and_the_rule(tmp_path: Path) -> None:
    """So a bad result traces back to the model that produced it."""
    choice = resolve(load(_table(tmp_path, LIVE_OVERRIDE)), Stage.QA, None)
    assert choice.record == "model: sonnet  # tier=standard, rule=stage table: qa"


def test_a_choice_always_explains_itself(tmp_path: Path) -> None:
    """An answer with no reason cannot be argued with, which is the point."""
    table = load(_table(tmp_path, LIVE_OVERRIDE))
    for stage in Stage:
        assert resolve(table, stage, _chain(tmp_path, "live")).rule
