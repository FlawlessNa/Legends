"""
What an attack reaches, and how long a weapon-based cast takes (spec #631 § 4
and 5), from the client's files and the weapon the character holds.

A **reach** is a box around the character's feet, in virtual px, as the client
stores it: facing left, `x` growing to the right and `y` down. Facing right
mirrors it. Conversion to client px is the caller's (ADR 0004, virtual
coordinates).

- **Skill-based:** a level with a box (`lt`, `rb`) reaches that box.
- **Weapon-based:** a skill with no box and no action of its own plays one of
  its weapon family's actions, drawn at random per attack. It reaches what every
  one of them reaches, in brackets 0 and 10 of the weapon's swing set: the
  overlap of their boxes (D12).
- **No reach:** a skill with no box and an action of its own (Magic Claw), a
  weapon-based skill whose weapon's family has no actions here (a bow, a wand, a
  claw), or one whose weapon isn't known.

A skill's `range` is ignored until #633 confirms what it means (spec § 4).

A skill with no action of its own plays the weapon's actions, so its cast time
is the longest of its family's actions, each frame scaled by the weapon's speed
as the client scales it. Boosters are not applied: the bot can't tell whether
one is on (spec § 5). A skill with an action of its own keeps the unscaled cast
time `character_skills` gave it.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from game_data.catalogue.model import Swing, WeaponData

from .maple_skills import MapleSkill

#: The actions a normal attack draws at random, by the weapon's attack family
#: (`info/attack`), which Power Strike and Slash Blast play too. Game knowledge
#: no file of the client's holds: from `docs/research/weapon-reach.md`
#: ("Attack families and their actions"), after a fan client and the MSCW
#: community. The trailing-`F` (Final Attack) poses and `proneStab` are not
#: drawn. The spear set (family 2) is low confidence: the longer list is kept,
#: since it can only shrink the overlap.
FAMILY_ACTIONS: Mapping[int, tuple[str, ...]] = {
    1: ("stabO1", "stabO2", "swingO1", "swingO2", "swingO3"),
    5: ("swingT1", "swingT2", "swingT3", "stabO1", "stabO2"),
    2: ("swingP1", "swingP2", "swingT2", "stabT1", "stabT2"),
}

#: The swing set's brackets a weapon-based reach overlaps. The bracket follows
#: the weapon mastery, which isn't read; brackets 0 to 9 are identical in every
#: set, so 0 and 10 cover every mastery (`docs/research/weapon-reach.md`,
#: "Brackets").
BRACKETS = (0, 10)

#: The bounds of the weapon's speed degree, and the scale of a frame's delay at
#: a degree: `trunc(|delay| x (SPEED_BASE + degree) / SPEED_DIVISOR)`
#: (`docs/research/weapon-reach.md`, "The speed formula").
DEGREE_MIN, DEGREE_MAX = 2, 10
SPEED_BASE, SPEED_DIVISOR = 10, 16


class NoReach(Exception):
    """An attack has no reach: says which, and why."""


class Sides(Enum):
    """Which ways a reach hits from a cast."""

    #: Symmetric about the character: no facing.
    TWO = "two-sided"
    #: The cast faces one way, and hits that way.
    ONE = "one-sided"


@dataclass(frozen=True, slots=True)
class Reach:
    """
    A box around the character's feet, in virtual px, facing left as the
    client stores it: from `(lt_x, lt_y)` to `(rb_x, rb_y)`, `x` to the right,
    `y` down.
    """

    lt_x: int
    lt_y: int
    rb_x: int
    rb_y: int

    @property
    def sides(self) -> Sides:
        """Two-sided when the box is symmetric about the character, one-sided
        otherwise: a box that reaches a little behind is still one-sided."""
        return Sides.TWO if self.lt_x == -self.rb_x else Sides.ONE

    def facing_right(self) -> Reach:
        """The box facing right: mirrored about the character (`x -> -x`)."""
        return Reach(-self.rb_x, self.lt_y, -self.lt_x, self.rb_y)


def skill_reach(skill: MapleSkill) -> Reach | None:
    """The box of the skill's level; None when it has none."""
    if skill.lt is None or skill.rb is None:
        return None
    return Reach(*skill.lt, *skill.rb)


def plays_weapon_actions(skill: MapleSkill) -> bool:
    """Whether a cast of the skill plays the weapon's actions: it has none of
    its own. Its cast time then comes from the weapon (`weapon_cast_time`)."""
    return not skill.actions


def overlap(boxes: Iterable[Reach]) -> Reach | None:
    """What every box covers; None when they share no pixel, or there are
    none."""
    boxes = tuple(boxes)
    if not boxes:
        return None
    found = Reach(
        max(b.lt_x for b in boxes),
        max(b.lt_y for b in boxes),
        min(b.rb_x for b in boxes),
        min(b.rb_y for b in boxes),
    )
    if found.lt_x > found.rb_x or found.lt_y > found.rb_y:
        return None
    return found


def family_actions(weapon: WeaponData) -> tuple[str, ...]:
    """
    The actions a weapon-based attack with `weapon` draws from.

    :raises NoReach: The weapon's family has none here: a bow, crossbow,
        wand, staff, claw, or bare hands.
    """
    actions = FAMILY_ACTIONS.get(weapon.attack) if weapon.attack is not None else None
    if actions is None:
        raise NoReach(
            f"{_weapon(weapon)} is of attack family {weapon.attack}, whose swings "
            f"aren't known: only families {', '.join(map(str, FAMILY_ACTIONS))} "
            "(one-handed, two-handed, spear and polearm) are"
        )
    return actions


def weapon_swings(
    weapon: WeaponData, swings: Callable[[str, int], Sequence[Swing]]
) -> tuple[Reach, ...]:
    """
    The boxes of the weapon family's actions, in each of `BRACKETS` of the
    weapon's swing set: every box a weapon-based cast may play.

    :param swings: A swing set's swings in a bracket, as `Catalogue.swings`
        gives them.
    :raises NoReach: The family has no actions here (`family_actions`); the
        weapon has no swing set; or the set lacks a bracket or one of the
        family's actions.
    """
    actions = family_actions(weapon)
    if weapon.afterimage is None:
        raise NoReach(f"{_weapon(weapon)} has no swing set")
    boxes: list[Reach] = []
    for bracket in BRACKETS:
        try:
            found = {s.action: s for s in swings(weapon.afterimage, bracket)}
        except LookupError as error:
            raise NoReach(f"{_weapon(weapon)}'s swings: {error}") from error
        missing = [action for action in actions if action not in found]
        if missing:
            raise NoReach(
                f"{_weapon(weapon)}'s swing set {weapon.afterimage!r} has no box "
                f"for {', '.join(missing)} in bracket {bracket}"
            )
        boxes += [
            Reach(s.lt_x, s.lt_y, s.rb_x, s.rb_y)
            for s in (found[action] for action in actions)
        ]
    return tuple(boxes)


def weapon_reach(
    weapon: WeaponData, swings: Callable[[str, int], Sequence[Swing]]
) -> Reach:
    """
    The overlap of the boxes of the weapon family's actions, in each of
    `BRACKETS` of the weapon's swing set (`weapon_swings`).

    :param swings: A swing set's swings in a bracket, as `Catalogue.swings`
        gives them.
    :raises NoReach: As `weapon_swings` does; or the boxes share no pixel.
    """
    return _swings_overlap(weapon, weapon_swings(weapon, swings))


def _swings_overlap(weapon: WeaponData, boxes: Iterable[Reach]) -> Reach:
    """
    The overlap of `boxes`, the weapon's swings (`weapon_swings`).

    :raises NoReach: They share no pixel.
    """
    reach = overlap(boxes)
    if reach is None:
        raise NoReach(
            f"{_weapon(weapon)}'s swings {', '.join(family_actions(weapon))} share "
            "no pixel"
        )
    return reach


def attack_speed_degree(attack_speed: int) -> int:
    """The weapon's speed degree, without boosters: its `attackSpeed`,
    clamped."""
    return max(DEGREE_MIN, min(DEGREE_MAX, attack_speed))


def scaled_duration(delays: Iterable[int], degree: int) -> int:
    """An action's duration in ms at a speed degree: each frame's delay
    magnitude scaled and truncated on its own, then added up."""
    return sum(abs(delay) * (SPEED_BASE + degree) // SPEED_DIVISOR for delay in delays)


def weapon_cast_time(
    weapon: WeaponData, action_delays: Callable[[str], Sequence[int]]
) -> int:
    """
    How long a cast that plays the weapon's actions takes, in ms: the longest
    of its family's actions at the weapon's speed, so that a cast never cuts
    the next one short.

    :param action_delays: An action's frame delays, as
        `Catalogue.action_delays` gives them.
    :raises NoReach: The family has no actions here (`family_actions`), the
        weapon has no `attackSpeed`, or an action has no delays.
    """
    actions = family_actions(weapon)
    if weapon.attack_speed is None:
        raise NoReach(f"{_weapon(weapon)} has no attack speed")
    degree = attack_speed_degree(weapon.attack_speed)
    durations: list[int] = []
    for action in actions:
        try:
            delays = action_delays(action)
        except LookupError as error:
            raise NoReach(f"{_weapon(weapon)}'s actions: {error}") from error
        if not delays:
            raise NoReach(f"the action {action!r} has no frame delays")
        durations.append(scaled_duration(delays, degree))
    return max(durations)


class WeaponCatalogue(Protocol):
    """What an attack's reach and cast time ask of a `Catalogue`."""

    def swings(self, afterimage: str, bracket: int) -> tuple[Swing, ...]: ...

    def action_delays(self, action: str) -> list[int]: ...


@dataclass(frozen=True, slots=True)
class Armed:
    """
    An attack's skill, ready to cast, and what it reaches.

    :ivar skill: The skill, with its cast time: the weapon's, when it plays the
        weapon's actions.
    :ivar reach: What a cast reaches, facing left.
    :ivar swings: The boxes of the weapon's swings, facing left, when `reach`
        is their overlap: a mob in one of them and out of `reach` may be hit,
        and isn't counted (`combat.partial_reach`). None otherwise.
    """

    skill: MapleSkill
    reach: Reach
    swings: tuple[Reach, ...] | None = None


def armed(
    skill: MapleSkill, weapon: WeaponData | None, catalogue: WeaponCatalogue | None
) -> Armed:
    """
    The skill's reach, and the skill with its cast time.

    :param weapon: The weapon the character holds; None when it isn't read,
        which only a skill with an action of its own may do without.
    :param catalogue: The swings and action delays; None as `weapon`.
    :raises NoReach: The skill has no box and an action of its own; it plays
        the weapon's actions and the weapon isn't known; or as `weapon_reach`
        and `weapon_cast_time` raise.
    """
    reach = skill_reach(skill)
    if not plays_weapon_actions(skill):
        if reach is None:
            raise NoReach(
                f"{skill.name} ({skill.id}) has no box, and plays its own "
                f"{', '.join(skill.actions)}: its reach isn't known"
            )
        return Armed(skill, reach)
    if weapon is None or catalogue is None:
        raise NoReach(
            f"{skill.name} ({skill.id}) plays the weapon's actions, and the weapon "
            "isn't known"
        )
    swings: tuple[Reach, ...] | None = None
    try:
        if reach is None:
            swings = weapon_swings(weapon, catalogue.swings)
            reach = _swings_overlap(weapon, swings)
        cast_time = weapon_cast_time(weapon, catalogue.action_delays)
    except NoReach as error:
        raise NoReach(
            f"{skill.name} ({skill.id}) plays the weapon's actions: {error}"
        ) from error
    return Armed(replace(skill, cast_time=cast_time / 1000), reach, swings)


def _weapon(weapon: WeaponData) -> str:
    return f"{weapon.name or 'the weapon'} ({weapon.id})"
