"""
`ATTACKS` and `FACING` (#637, spec #631 § 6, validation, and § 8): the profile's
attacks, in order, each with its skill, reach, sides and `min_mobs`, served by
`AttacksProvider`.

No client: the skills are real `MapleSkill`s served as their Bot-level Provider
serves them (`serving.serve`), the swings and delays are `test_reach`'s fixture,
and the equipment window's setup is a stand-in that serves the weapon.
"""

import pytest

from botting.core import StartupRefused
from game_data.catalogue.model import WeaponData
from maple.decision_makers.providers import (
    ATTACKS,
    FACING,
    WEAPON,
    Attack,
    AttacksProvider,
    EquipmentMenuProvider,
    Facing,
)
from maple.decision_makers.providers import attacks as attacks_module
from maple.model.characters.reach import Reach, Sides
from tests.test_maple.serving import Served, serve
from tests.test_maple.test_reach import (
    BOW,
    CATALOGUE,
    HEAL,
    MAGIC_CLAW,
    POWER_STRIKE,
    SAVAGE_BLOW,
    SLASH_BLAST,
    SWORD,
)

SKILLS = {s.name: s for s in (POWER_STRIKE, SLASH_BLAST, HEAL, SAVAGE_BLOW, MAGIC_CLAW)}

SWORDSMAN = [
    {"skill": "Slash Blast", "min_mobs": 3},
    {"skill": "Power Strike", "min_mobs": 1},
]


class Equipment:
    """`EquipmentMenuProvider.setup()`, standing in for the window: serves
    `weapon`, or refuses as a weapon that can't be read does."""

    def __init__(self, weapon: WeaponData | None) -> None:
        self.weapon = weapon
        self.reads = 0

    def setup(self, provider: EquipmentMenuProvider) -> None:
        self.reads += 1
        if self.weapon is None:
            raise StartupRefused("the weapon can't be read: no icon matched")
        weapon = self.weapon
        provider.register(WEAPON, lambda: weapon, initial_value=weapon)


@pytest.fixture
def equipment(monkeypatch: pytest.MonkeyPatch) -> Equipment:
    found = Equipment(SWORD)
    monkeypatch.setattr(
        EquipmentMenuProvider, "setup", lambda provider: found.setup(provider)
    )
    return found


def served(monkeypatch: pytest.MonkeyPatch, **settings: object) -> Served:
    """A Bot whose profile `settings` are given, with `AttacksProvider` built
    and set up, as assembly builds it, on the fixture catalogue."""
    result = serve(monkeypatch, skills=SKILLS)
    result.providers.settings.update({"catalogue": CATALOGUE, **settings})
    result.providers.build([AttacksProvider])
    return result


def attacks(monkeypatch: pytest.MonkeyPatch, **settings: object) -> tuple[Attack, ...]:
    found = served(monkeypatch, **settings).data.read(ATTACKS)
    assert found is not None
    return found


def refusal(monkeypatch: pytest.MonkeyPatch, **settings: object) -> str:
    """Why the start is refused, checked to be one line."""
    with pytest.raises(StartupRefused) as refused:
        served(monkeypatch, **settings)
    message = str(refused.value)
    assert "\n" not in message
    return message


# --- what it serves ----------------------------------------------------------------


def test_it_serves_the_profiles_attacks_in_order(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    found = attacks(monkeypatch, attacks=SWORDSMAN)

    assert [(a.skill.name, a.reach, a.sides, a.min_mobs) for a in found] == [
        ("Slash Blast", Reach(-73, -30, -22, -16), Sides.ONE, 3),
        ("Power Strike", Reach(-73, -30, -22, -16), Sides.ONE, 1),
    ]


def test_a_weapon_based_skills_cast_time_is_the_weapons(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    """`cast_skill` holds the key for the attack's `animation_time`."""
    found = attacks(monkeypatch, attacks=SWORDSMAN)

    assert [a.skill.animation_time for a in found] == [0.699, 0.699]


def test_skill_based_attacks_carry_their_box_and_sides(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    found = attacks(
        monkeypatch,
        attacks=[
            {"skill": "Heal", "min_mobs": 2},
            {"skill": "Savage Blow", "min_mobs": 1},
        ],
    )

    assert [(a.reach, a.sides, a.skill) for a in found] == [
        (Reach(-250, -90, 250, 90), Sides.TWO, HEAL),
        (Reach(-95, -62, -18, -6), Sides.ONE, SAVAGE_BLOW),
    ]


def test_attacks_is_none_when_the_profile_has_none(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    result = served(monkeypatch)

    assert result.data.read(ATTACKS) is None
    assert EquipmentMenuProvider not in result.providers


def test_facing_is_closest_by_default(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    assert served(monkeypatch, attacks=SWORDSMAN).data.read(FACING) is Facing.CLOSEST


def test_facing_most_is_served(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    result = served(monkeypatch, attacks=SWORDSMAN, facing="most")

    assert result.data.read(FACING) is Facing.MOST


# --- the weapon, read only when needed ---------------------------------------------


def test_the_weapon_is_read_when_an_attack_plays_the_weapons_actions(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    result = served(monkeypatch, attacks=SWORDSMAN)

    assert EquipmentMenuProvider in result.providers
    assert equipment.reads == 1


def test_the_weapon_is_not_read_when_no_attack_plays_the_weapons_actions(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    """A Bandit's Savage Blow carries its own box and action: the equipment
    window is never opened, and no catalogue is."""
    monkeypatch.setattr(
        attacks_module.Catalogue, "latest", lambda: pytest.fail("opened")
    )
    result = serve(monkeypatch, skills=SKILLS)
    result.providers.settings.update(attacks=[{"skill": "Savage Blow", "min_mobs": 1}])
    result.providers.build([AttacksProvider])

    assert EquipmentMenuProvider not in result.providers
    assert equipment.reads == 0


def test_a_weapon_that_cant_be_read_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    equipment.weapon = None

    assert "no icon matched" in refusal(monkeypatch, attacks=SWORDSMAN)


def test_a_weapon_based_attack_with_a_bow_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    equipment.weapon = BOW

    assert "attack Slash Blast (1001002) plays the weapon's actions" in refusal(
        monkeypatch, attacks=SWORDSMAN
    )


# --- validation --------------------------------------------------------------------


def test_an_attack_with_no_reach_refuses_the_start_naming_it(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    message = refusal(monkeypatch, attacks=[{"skill": "Magic Claw", "min_mobs": 1}])

    assert "Magic Claw (2001003) has no box" in message


def test_an_attack_the_character_lacks_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    message = refusal(monkeypatch, attacks=[{"skill": "Rush", "min_mobs": 1}])

    assert "attack 'Rush' isn't one of the character's skills" in message


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ([], "attacks is []: it is a list of attacks"),
        ({"skill": "Power Strike"}, "it is a list of attacks"),
        ("Power Strike", "it is a list of attacks"),
        ([{"skill": "Power Strike"}], "attack 1 is"),
        ([{"skill": "Power Strike", "min_mobs": 1, "range": 3}], "and nothing else"),
        (["Power Strike"], "attack 1 is 'Power Strike'"),
        ([{"skill": 3, "min_mobs": 1}], "attack 1's skill is 3"),
        ([{"skill": "Power Strike", "min_mobs": 0}], "min_mobs is 0"),
        ([{"skill": "Power Strike", "min_mobs": "2"}], "min_mobs is '2'"),
        ([{"skill": "Power Strike", "min_mobs": True}], "min_mobs is True"),
        ([{"skill": "Power Strike", "min_mobs": 1.5}], "min_mobs is 1.5"),
    ],
    ids=[
        "empty",
        "a-mapping",
        "a-name",
        "no-min-mobs",
        "an-unknown-key",
        "an-entry-not-a-mapping",
        "a-skill-not-a-name",
        "zero",
        "a-string",
        "a-bool",
        "a-float",
    ],
)
def test_a_bad_attack_list_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch,
    equipment: Equipment,
    setting: object,
    expected: str,
) -> None:
    assert expected in refusal(monkeypatch, attacks=setting)


def test_a_bad_facing_refuses_the_start(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    message = refusal(monkeypatch, attacks=SWORDSMAN, facing="nearest")

    assert "facing is 'nearest': it is closest or most" in message


def test_an_attack_with_no_reach_refuses_before_the_weapon_is_read(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    """Reading the weapon presses the equipment key: a list refused anyway
    sends nothing."""
    refusal(
        monkeypatch,
        attacks=[
            {"skill": "Power Strike", "min_mobs": 1},
            {"skill": "Magic Claw", "min_mobs": 1},
        ],
    )

    assert equipment.reads == 0


def test_game_data_with_no_catalogue_refuses_before_the_weapon_is_read(
    monkeypatch: pytest.MonkeyPatch, equipment: Equipment
) -> None:
    def no_extraction() -> object:
        raise attacks_module.CatalogueError("the store has no extraction")

    monkeypatch.setattr(attacks_module.Catalogue, "latest", no_extraction)

    message = refusal(monkeypatch, attacks=SWORDSMAN, catalogue=None)

    assert "the weapon's swings come from the game data" in message
    assert equipment.reads == 0
