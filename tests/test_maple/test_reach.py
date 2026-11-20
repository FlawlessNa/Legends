"""
What an attack reaches, and how long a weapon-based cast takes (#637, spec #631
§ 4 and 5), as pure functions of the skill, the weapon and the catalogue.

On fixture data: `swordOL`'s boxes in brackets 0 and 10, the body's action
delays, and the skills' levels are the MSCW client's, copied from the research
behind `docs/research/weapon-reach.md` (extraction `3c238cfcb903ce34`) and the
catalogue of build `756a6f605a752cec`.
"""

from dataclasses import replace

import pytest

from game_data.catalogue.model import Swing, WeaponData
from maple.model.characters.maple_skills import MapleSkill
from maple.model.characters.reach import (
    FAMILY_ACTIONS,
    NoReach,
    Reach,
    Sides,
    armed,
    attack_speed_degree,
    overlap,
    scaled_duration,
    skill_reach,
    weapon_cast_time,
    weapon_reach,
)

#: A one-handed sword: `swordOL`, speed 4, family 1 (`Catalogue.weapon(1302000)`).
SWORD = WeaponData(1302000, "Sword", "swordOL", 4, 1)
#: A bow: family 3, whose swings aren't known.
BOW = WeaponData(1452002, "War Bow", "swordTS", 6, 3)

_BRACKET_0 = {
    "swingO1": (-88, -62, -18, -6),
    "swingO2": (-73, -50, 5, 17),
    "swingO3": (-102, -50, -22, -10),
    "stabO1": (-84, -30, -20, -15),
    "stabO2": (-83, -30, -12, -16),
    # Not drawn by a normal attack: they would move the overlap's far edge.
    "swingOF": (-123, -48, 13, -1),
    "stabOF": (-110, -32, -40, -11),
    "proneStab": (-74, -11, -15, 1),
}
_BRACKET_10 = {
    **_BRACKET_0,
    "swingO1": (-90, -72, -18, -6),
    "swingO2": (-73, -50, 5, 23),
    "stabOF": (-113, -32, -40, -11),
}
SWORD_OL = {0: _BRACKET_0, 10: _BRACKET_10}

#: `Character/00002000.img`'s delays, in ms.
DELAYS = {
    **{swing: [300, 150, 350] for swing in ("swingO1", "swingO2", "swingO3")},
    **{stab: [350, 450] for stab in ("stabO1", "stabO2")},
    "swingOF": [200, 100, 100, 300],
}


class Swings:
    """`Catalogue.swings` and `Catalogue.action_delays` over the fixture."""

    def __init__(
        self,
        sets: dict[str, dict[int, dict[str, tuple[int, int, int, int]]]],
        delays: dict[str, list[int]],
    ) -> None:
        self.sets = sets
        self.delays = delays

    def swings(self, afterimage: str, bracket: int) -> tuple[Swing, ...]:
        found = self.sets.get(afterimage, {}).get(bracket)
        if found is None:
            raise LookupError(f"swing set {afterimage!r} has no bracket {bracket}")
        return tuple(
            Swing(afterimage, bracket, action, *box) for action, box in found.items()
        )

    def action_delays(self, action: str) -> list[int]:
        if action not in self.delays:
            raise LookupError(f"the character has no action {action!r}")
        return self.delays[action]


CATALOGUE = Swings({"swordOL": SWORD_OL}, DELAYS)


def _skill(
    name: str,
    id_: int,
    actions: tuple[str, ...] = (),
    box: tuple[int, int, int, int] | None = None,
    cast_time: float | None = None,
) -> MapleSkill:
    return MapleSkill(
        name,
        id=id_,
        level=1,
        max_level=20,
        lt=None if box is None else box[:2],
        rb=None if box is None else box[2:],
        actions=actions,
        cast_time=cast_time,
    )


#: No box, no action: plays the weapon's actions. Its `range` is ignored.
POWER_STRIKE = _skill("Power Strike", 1001001)
SLASH_BLAST = MapleSkill(
    "Slash Blast", id=1001002, level=1, max_level=20, range=130, mob_count=6
)
#: Heal at level 1: a box symmetric about the character.
HEAL = _skill("Heal", 2301001, ("alert2",), (-250, -90, 250, 90), cast_time=0.6)
SAVAGE_BLOW = _skill("Savage Blow", 4201003, ("savage",), (-95, -62, -18, -6), 1.2)
#: Its own actions, and no box.
MAGIC_CLAW = _skill("Magic Claw", 2001003, ("swingO1", "swingO2", "swingO3"), None, 0.8)


# --- the spec's cases ---------------------------------------------------------------


def test_power_strike_with_a_one_handed_sword_reaches_the_overlap_of_its_swings() -> (
    None
):
    found = armed(POWER_STRIKE, SWORD, CATALOGUE)

    assert found.reach == Reach(-73, -30, -22, -16)
    assert found.reach.sides is Sides.ONE


def test_power_strike_at_speed_4_takes_699_ms() -> None:
    found = armed(POWER_STRIKE, SWORD, CATALOGUE)

    assert found.skill.animation_time == 0.699
    assert found.skill == replace(POWER_STRIKE, cast_time=0.699)


def test_heal_at_level_1_is_two_sided() -> None:
    found = armed(HEAL, None, None)

    assert found.reach == Reach(-250, -90, 250, 90)
    assert found.reach.sides is Sides.TWO


def test_savage_blow_is_one_sided_and_mirrors_facing_right() -> None:
    found = armed(SAVAGE_BLOW, None, None)

    assert found.reach.sides is Sides.ONE
    assert found.reach.facing_right() == Reach(18, -62, 95, -6)


def test_magic_claw_has_no_reach() -> None:
    with pytest.raises(NoReach, match=r"Magic Claw \(2001003\) has no box"):
        armed(MAGIC_CLAW, SWORD, CATALOGUE)


# --- skill-based -------------------------------------------------------------------


def test_a_skill_with_its_own_action_keeps_its_unscaled_cast_time() -> None:
    """Savage Blow's cast time is its action's, as `character_skills` gave
    it: the weapon's speed doesn't scale it."""
    assert armed(SAVAGE_BLOW, SWORD, CATALOGUE).skill is SAVAGE_BLOW


def test_a_skill_with_no_box_has_no_skill_reach() -> None:
    assert skill_reach(POWER_STRIKE) is None
    assert skill_reach(SAVAGE_BLOW) == Reach(-95, -62, -18, -6)


def test_a_box_that_reaches_a_little_behind_is_still_one_sided() -> None:
    """`swingO2` reaches 5 px behind: the game still faces it."""
    assert Reach(-73, -50, 5, 17).sides is Sides.ONE


def test_a_two_sided_reach_mirrors_onto_itself() -> None:
    assert Reach(-250, -90, 250, 90).facing_right() == Reach(-250, -90, 250, 90)


# --- weapon-based ------------------------------------------------------------------


def test_range_is_ignored() -> None:
    """Slash Blast's `range` (130) doesn't widen its reach until #633."""
    assert armed(SLASH_BLAST, SWORD, CATALOGUE).reach == Reach(-73, -30, -22, -16)


def test_the_final_attack_poses_and_the_prone_stab_are_not_drawn() -> None:
    """With `stabOF`, the far edge would be -40: it isn't in the family."""
    assert "stabOF" not in FAMILY_ACTIONS[1]
    assert weapon_reach(SWORD, CATALOGUE.swings).rb_x == -22


def test_bracket_10_counts_too() -> None:
    """A swing that shrinks in bracket 10 shrinks the overlap."""
    shrunk = {**_BRACKET_10, "stabO1": (-60, -30, -20, -15)}
    catalogue = Swings({"swordOL": {0: _BRACKET_0, 10: shrunk}}, DELAYS)

    assert weapon_reach(SWORD, catalogue.swings).lt_x == -60


def test_a_weapon_family_with_no_known_swings_has_no_reach() -> None:
    with pytest.raises(NoReach, match=r"Power Strike .*War Bow .*family 3"):
        armed(POWER_STRIKE, BOW, CATALOGUE)


def test_a_weapon_based_attack_with_no_weapon_has_no_reach() -> None:
    with pytest.raises(NoReach, match="the weapon isn't known"):
        armed(POWER_STRIKE, None, None)


def test_a_swing_set_missing_one_of_the_familys_actions_has_no_reach() -> None:
    """Fewer boxes would widen the overlap: the bot would swing at air."""
    partial = {k: v for k, v in _BRACKET_0.items() if k != "stabO2"}
    catalogue = Swings({"swordOL": {0: partial, 10: _BRACKET_10}}, DELAYS)

    with pytest.raises(NoReach, match="no box for stabO2 in bracket 0"):
        weapon_reach(SWORD, catalogue.swings)


def test_a_swing_set_missing_a_bracket_has_no_reach() -> None:
    catalogue = Swings({"swordOL": {0: _BRACKET_0}}, DELAYS)

    with pytest.raises(NoReach, match="no bracket 10"):
        weapon_reach(SWORD, catalogue.swings)


def test_boxes_that_share_no_pixel_overlap_nowhere() -> None:
    assert overlap([Reach(-10, -10, -5, -5), Reach(5, 5, 10, 10)]) is None
    assert overlap([Reach(-10, -10, 0, 0), Reach(0, 0, 10, 10)]) == Reach(0, 0, 0, 0)


# --- weapon-based cast time --------------------------------------------------------


def test_each_frame_is_scaled_and_truncated_on_its_own() -> None:
    """At degree 4: 300 -> 262, 150 -> 131 (131.25), 350 -> 306 (306.25)."""
    assert scaled_duration([300, 150, 350], 4) == 699
    assert scaled_duration([300, 150, 350], 6) == 800


def test_a_negative_delay_counts_by_its_magnitude() -> None:
    assert scaled_duration([-500, 500], 6) == 1000


@pytest.mark.parametrize(
    ("attack_speed", "degree"), [(0, 2), (2, 2), (4, 4), (10, 10), (15, 10)]
)
def test_the_speed_degree_is_the_weapons_speed_clamped(
    attack_speed: int, degree: int
) -> None:
    assert attack_speed_degree(attack_speed) == degree


def test_the_cast_time_is_the_longest_of_the_familys_actions() -> None:
    """`stabO2` made longer than the swings (699 ms): 437 + 437 at degree 4."""
    delays = {**DELAYS, "stabO2": [500, 500]}

    assert weapon_cast_time(SWORD, delays.__getitem__) == 874


def test_a_weapon_with_no_attack_speed_has_no_cast_time() -> None:
    unknown = WeaponData(1302000, "Sword", "swordOL", None, 1)

    with pytest.raises(NoReach, match="no attack speed"):
        weapon_cast_time(unknown, CATALOGUE.action_delays)
