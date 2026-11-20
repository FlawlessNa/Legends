"""
A character's skills come from the client's files (#635, spec #631 § 1 and 7):
`SKILLS`, built at start for the names the IGN's `Skill Keys` give, in the
character's job line, at the level `skill_levels` gives or at their maximum.

On a fixture catalogue: Power Strike, Slash Blast and Iron Body carry the MSCW
client's values (build `3c238cfcb903ce34`), Teleport its four IDs; Holy Rays, a
Priest's skill, is invented, since the client has no third job.
"""

import logging
from collections.abc import Callable
from typing import Any, Self

import pytest

from botting.core import BotData, Providers, StartupRefused
from game_data.catalogue import Ref, SkillData, SkillLevel
from maple.bots import CalibrationBot, TrainingBot
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.decision_makers.providers import SKILLS, SkillsProvider
from maple.decision_makers.providers import skills as skills_module
from maple.decision_makers.rebuffs import solo_buffs
from maple.launchers.profile import ProfileError
from maple.model.characters import (
    JOB_IDS,
    MAPPING,
    Bandit,
    Fighter,
    MapleSkill,
    character_class,
)
from maple.model.characters.maple_skills import NoCastTime
from tests.test_maple.serving import serve

#: `alert2`, the pose most buffs play, in ms.
ALERT2 = 600

#: A level's value: the same at every level, or a function of the level.
type ByLevel = int | Callable[[int], int]


def _levels(skill: int, count: int, **by_level: ByLevel) -> tuple[SkillLevel, ...]:
    def value(name: str, level: int) -> int | None:
        found = by_level.get(name)
        return found(level) if callable(found) else found

    return tuple(
        SkillLevel(
            skill=skill,
            level=level,
            actions=(),
            mp_con=None,
            time=value("time", level),
            lt_x=value("lt_x", level),
            lt_y=value("lt_y", level),
            rb_x=value("rb_x", level),
            rb_y=value("rb_y", level),
            mob_count=value("mob_count", level),
            attack_count=value("attack_count", level),
            range=value("range", level),
            cooltime=None,
            other={},
        )
        for level in range(1, count + 1)
    )


def _skill(
    id_: int,
    job: int,
    name: str,
    levels: int,
    actions: tuple[str, ...] = (),
    **by_level: ByLevel,
) -> SkillData:
    return SkillData(
        id=id_,
        job=job,
        name=name,
        description=None,
        type=None,
        max_level=levels,
        actions=actions,
        icon=f"icon-{id_}",
        levels=_levels(id_, levels, **by_level),
    )


SKILL_DATA = [
    _skill(1001001, 100, "Power Strike", 20, mob_count=1, attack_count=1),
    _skill(
        1001002,
        100,
        "Slash Blast",
        20,
        mob_count=6,
        attack_count=1,
        range=lambda level: 130 if level <= 10 else 150,
    ),
    _skill(
        1001000,
        100,
        "Iron Body",
        20,
        ("alert2",),
        time=lambda level: 600 if level == 20 else 300 + 15 * (level - 1),
    ),
    _skill(1101004, 110, "Rage", 30, ("alert2",), time=300),
    _skill(2101001, 210, "Teleport", 20, range=150),
    _skill(2201001, 220, "Teleport", 20, range=150),
    _skill(2301000, 230, "Teleport", 20, range=150),
    _skill(8001002, 800, "Teleport", 1),
    _skill(2311000, 231, "Holy Rays", 30, ("alert2",), mob_count=6),
    _skill(4201001, 420, "Haste", 20, ("alert2",), time=300),
]


class _Catalogue:
    """The calls skills are built with, over `SKILL_DATA`, as `Catalogue`
    answers them."""

    def __init__(self, skills: list[SkillData]) -> None:
        self.skills = {skill.id: skill for skill in skills}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None: ...

    def search(self, text: str, kind: str | None = None) -> list[Ref]:
        assert kind == "skill"
        return [
            Ref("skill", skill.id, skill.name)
            for skill in self.skills.values()
            if skill.name is not None and text.casefold() in skill.name.casefold()
        ]

    def skill(self, name_or_id: str | int) -> SkillData:
        return self.skills[int(name_or_id)]

    def action_duration(self, action: str) -> int:
        if action != "alert2":
            raise LookupError(f"the character has no action {action!r}")
        return ALERT2


CATALOGUE = _Catalogue(SKILL_DATA)


def skills(
    monkeypatch: pytest.MonkeyPatch,
    job: str,
    names: list[str],
    **settings: object,
) -> dict[str, MapleSkill]:
    """`SKILLS` for a `job` whose `Skill Keys` name `names`, with the profile
    `settings`, built as `MapleBot.child_init` builds its Provider."""
    keys = {name: "f" for name in names}
    monkeypatch.setattr(skills_module, "skill_keys", lambda ign: keys)
    data = BotData("Hero")
    providers = Providers(data, None, None, settings)  # pyright: ignore[reportArgumentType] - nothing is sent
    providers.add(SkillsProvider, job=job, catalogue=CATALOGUE)
    return dict(data.read(SKILLS))


SWORDSMAN = ["Power Strike", "Slash Blast", "Iron Body"]


def test_a_swordsman_gets_the_skills_its_skill_keys_name_at_their_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = skills(monkeypatch, "Swordsman", SWORDSMAN)

    assert list(found) == SWORDSMAN
    assert [(s.id, s.level, s.max_level) for s in found.values()] == [
        (1001001, 20, 20),
        (1001002, 20, 20),
        (1001000, 20, 20),
    ]
    assert found["Slash Blast"].range == 150
    assert (found["Iron Body"].time, found["Iron Body"].actions) == (600, ("alert2",))
    assert found["Iron Body"].icon == "icon-1001000"


def test_skill_levels_sets_a_skills_level(monkeypatch: pytest.MonkeyPatch) -> None:
    found = skills(monkeypatch, "Swordsman", SWORDSMAN, skill_levels={"Slash Blast": 8})

    assert (found["Slash Blast"].level, found["Slash Blast"].range) == (8, 130)
    assert found["Iron Body"].level == 20


def test_one_warning_names_the_skills_whose_level_matters_and_is_not_given(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=skills_module.logger.name):
        skills(monkeypatch, "Swordsman", SWORDSMAN, skill_levels={"Slash Blast": 8})

    (warning,) = [r.getMessage() for r in caplog.records]
    assert "Iron Body" in warning
    assert "Power Strike" not in warning
    assert "Slash Blast" not in warning


def test_a_misspelt_name_refuses_the_start_naming_the_closest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        StartupRefused, match=r"'Power Strik'.*closest are: Power Strike"
    ):
        skills(monkeypatch, "Swordsman", ["Power Strik"])


def test_a_skill_of_another_line_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(StartupRefused, match="has no skill named 'Haste'"):
        skills(monkeypatch, "Swordsman", ["Haste"])


def test_a_clerics_teleport_is_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    assert skills(monkeypatch, "Cleric", ["Teleport"])["Teleport"].id == 2301000


def test_a_bishop_finds_a_priest_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    found = skills(monkeypatch, "Bishop", ["Holy Rays", "Teleport"])

    assert (found["Holy Rays"].id, found["Teleport"].id) == (2311000, 2301000)


@pytest.mark.parametrize(
    ("levels", "refusal"),
    [
        ({"Rage": 3}, "skill_levels names 'Rage', which the Skill Keys don't"),
        ({"Slash Blast": 0}, "level 0: it goes from 1 to 20"),
        ({"Slash Blast": 21}, "level 21: it goes from 1 to 20"),
        ({"Slash Blast": "8"}, "level '8': it goes from 1 to 20"),
    ],
    ids=["not-keyed", "below-1", "above-maximum", "not-a-number"],
)
def test_a_bad_skill_level_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, levels: dict[str, object], refusal: str
) -> None:
    with pytest.raises(StartupRefused, match=refusal):
        skills(monkeypatch, "Swordsman", SWORDSMAN, skill_levels=levels)


def test_a_skills_cast_time_is_its_actions_duration_unscaled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert skills(monkeypatch, "Swordsman", SWORDSMAN)["Iron Body"].animation_time == (
        ALERT2 / 1000
    )


def test_casting_a_skill_with_no_action_of_its_own_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A weapon-based attack's cast time comes with #637: until then, nothing
    is sent with no wait."""
    power_strike = skills(monkeypatch, "Swordsman", SWORDSMAN)["Power Strike"]

    with pytest.raises(NoCastTime, match=r"Power Strike .*\(#637\)"):
        _ = power_strike.animation_time


def test_no_skill_keys_build_no_skills_and_open_no_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_section(ign: str) -> dict[str, str]:
        raise KeyError(ign)

    monkeypatch.setattr(skills_module, "skill_keys", no_section)
    monkeypatch.setattr(
        skills_module.Catalogue, "latest", lambda: pytest.fail("opened")
    )
    data = BotData("Hero")
    Providers(data, None, None, {}).add(SkillsProvider, job="Swordsman")  # pyright: ignore[reportArgumentType] - nothing is sent

    assert data.read(SKILLS) == {}


# --- the jobs ------------------------------------------------------------------


def test_every_job_has_a_class() -> None:
    assert {name.casefold() for name in MAPPING} == set(JOB_IDS)


def test_a_class_is_named_case_aside() -> None:
    assert character_class("wizardfirepoison") == (
        "WizardFirePoison",
        MAPPING["WizardFirePoison"],
    )


@pytest.mark.parametrize(
    ("job", "class_", "stat"), [("Fighter", Fighter, "STR"), ("bandit", Bandit, "LUK")]
)
def test_fighter_and_bandit_build_a_bot(job: str, class_: type, stat: str) -> None:
    bot = CalibrationBot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        map="auto",
        character_class=job,
        trial_schedule="physics",
    )

    assert bot.character_class is class_
    assert bot.character_class.main_stat == stat


def test_an_unknown_class_refuses_the_start() -> None:
    with pytest.raises(ProfileError, match="no job is named 'Pirate'"):
        CalibrationBot("Someone", {}, map="auto", character_class="Pirate")  # pyright: ignore[reportArgumentType]


# --- buffs ---------------------------------------------------------------------


@pytest.mark.parametrize("setting", ["included_buffs", "excluded_buffs"])
def test_each_retired_buff_setting_refuses_the_start_naming_buffs(setting: str) -> None:
    retired: dict[str, Any] = {setting: ["Haste"]}
    with pytest.raises(
        ProfileError, match=rf"`{setting}: \['Haste'\]` is retired.*`buffs`"
    ):
        TrainingBot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            character_class="Bandit",
            **retired,
        )


def test_buffs_must_be_a_list_of_names() -> None:
    with pytest.raises(ProfileError, match="must be a list of skill names"):
        TrainingBot("Someone", {}, map="auto", character_class="Bandit", buffs="Haste")  # pyright: ignore[reportArgumentType]


def test_the_profiles_buffs_last_their_levels_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = skills(monkeypatch, "Swordsman", SWORDSMAN, skill_levels={"Iron Body": 5})

    (iron_body,) = solo_buffs(found, ["Iron Body"])

    assert iron_body.time == 360


@pytest.mark.parametrize(
    ("buff", "refusal"),
    [
        ("Rage", "'Rage', which isn't one of the character's skills"),
        ("Power Strike", "'Power Strike', whose level 20 lasts no time"),
    ],
)
def test_a_buff_that_is_not_a_lasting_skill_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, buff: str, refusal: str
) -> None:
    found = skills(monkeypatch, "Swordsman", SWORDSMAN)

    with pytest.raises(StartupRefused, match=refusal):
        solo_buffs(found, [buff])


# --- MobsHitting, until a skill's reach replaces its screen ranges (#638) ------


@pytest.mark.parametrize(
    ("training_skill", "refusal"),
    [
        (None, "casts the profile's training_skill: name one"),
        ("Rage", "'Rage' isn't one of the character's skills"),
        ("Power Strike", "Power Strike declares no screen range"),
    ],
    ids=["none", "not-keyed", "from-the-client"],
)
def test_mobs_hitting_refuses_a_training_skill_it_cannot_count_mobs_for(
    monkeypatch: pytest.MonkeyPatch, training_skill: str | None, refusal: str
) -> None:
    found = skills(monkeypatch, "Swordsman", SWORDSMAN)
    served = serve(monkeypatch, skills=found, chat=object())
    hitting = MobsHitting(
        {},  # pyright: ignore[reportArgumentType] - no Manager needed
        served.data,
        None,  # pyright: ignore[reportArgumentType] - nothing is sent
        mob_count_threshold=1,
        training_skill=training_skill,
    )

    with pytest.raises(StartupRefused, match=refusal):
        hitting.setup()
