"""
A character's skills, built at launch from the client's files (spec #631 § 1).

`character_skills` builds one `MapleSkill` for each skill the IGN's `Skill Keys`
name, from the catalogue (`game_data`), at the level the profile's
`skill_levels` gives, or at the skill's maximum level (D13, until #630 reads
levels in game). A name is looked up only among the skills of the character's
job line (`job_line`), since several jobs share names: `Teleport` is a Wizard's
and a Cleric's.

A skill's cast time is its action's duration, as the catalogue gives it
(`Catalogue.action_duration`), unscaled: the longest when it has several
actions (spec § 5, first bullet). A skill that moves its caster
(`info/casterMove`, a Teleport) plays no action: its cast time is its effect's
duration (`SkillData.effect_duration`), and it has none when it has no effect
(#646). Any other skill with no action of its own is a weapon-based attack,
which plays the weapon's actions: its cast time comes from the weapon
(`maple.model.characters.reach`), and the attack `ATTACKS` serves carries it.
Asking for it here raises `NoCastTime`.
"""

import difflib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from botting.models_abstractions import Skill
from game_data.catalogue.model import Ref, SkillData, SkillLevel

from .jobs import job_line

#: How many close names a refusal suggests for a name the line lacks.
CLOSEST = 5


class SkillsRefused(Exception):
    """The profile's skills can't be built: says which, and why."""


class NoCastTime(RuntimeError):
    """A cast of a skill whose cast time comes from the weapon, asked of the
    skill without it: the attack `ATTACKS` serves carries it."""


@dataclass(frozen=True)
class MapleSkill(Skill):
    """
    A skill of the character's, at one level, as the client's files give it.

    :ivar name: Its name, as the IGN's `Skill Keys` names it.
    :ivar id: The client's ID for it, such as 2301000 for a Cleric's Teleport.
    :ivar level: The level it is used at.
    :ivar max_level: Its maximum level.
    :ivar mob_count: How many mobs that level hits; None when the client says
        nothing.
    :ivar attack_count: How many times that level hits each mob.
    :ivar cooltime: That level's cooldown, in seconds.
    :ivar time: How long that level lasts, in seconds: a buff's duration.
    :ivar lt: The top-left corner of that level's box, from the character's
        feet, facing left, in virtual px; None when it has no box.
    :ivar rb: That box's bottom-right corner.
    :ivar range: That level's `range`.
    :ivar actions: The character actions it plays, its own; none for a
        weapon-based attack.
    :ivar icon: Its icon in the image store.
    :ivar cast_time: How long a cast takes, in seconds; None for a skill that
        plays the weapon's actions, whose cast time comes from the weapon
        (`maple.model.characters.reach.armed`), and for a skill that moves its
        caster with no effect to time it.
    """

    name: str
    id: int
    level: int
    max_level: int
    mob_count: int | None = field(default=None, repr=False)
    attack_count: int | None = field(default=None, repr=False)
    cooltime: int | None = field(default=None, repr=False)
    time: int | None = field(default=None, repr=False)
    lt: tuple[int, int] | None = field(default=None, repr=False)
    rb: tuple[int, int] | None = field(default=None, repr=False)
    range: int | None = field(default=None, repr=False)
    actions: tuple[str, ...] = field(default=(), repr=False)
    icon: str | None = field(default=None, repr=False)
    cast_time: float | None = field(default=None, repr=False)

    @property
    def animation_time(self) -> float:
        """
        Its cast time, in seconds.

        :raises NoCastTime: It comes from the weapon: a weapon-based attack's
            is the one `ATTACKS` carries.
        """
        if self.cast_time is None:
            raise NoCastTime(
                f"{self.name} ({self.id}) plays the weapon's actions, so its cast "
                "time comes from the weapon: cast it as the attack ATTACKS serves"
            )
        return self.cast_time


class SkillCatalogue(Protocol):
    """What building skills asks of a `Catalogue`."""

    def search(self, text: str, kind: str | None = None) -> list[Ref]: ...

    def skill(self, name_or_id: str | int) -> SkillData: ...

    def action_duration(self, action: str) -> int: ...


@dataclass(frozen=True, slots=True)
class CharacterSkills:
    """
    The skills `character_skills` built.

    :ivar skills: Each skill, by its `Skill Keys` name.
    :ivar unsure_levels: The skills whose box, `range`, mobs hit or duration
        differ across their levels, and that the profile gives no level for:
        each is at its maximum level, which may not be the character's.
    """

    skills: dict[str, MapleSkill]
    unsure_levels: tuple[str, ...]


def check_skill_settings(
    job: str, names: Iterable[str], levels: Mapping[str, object] | None
) -> frozenset[int]:
    """
    The settings checks `character_skills` runs before it looks anything up,
    which need no catalogue: so a Bot with no `names` is refused the same way.

    :return: The ids of `job`'s line.
    :raises SkillsRefused: `levels` names a skill `names` doesn't, or `job`
        has no line.
    """
    names = tuple(names)
    unknown = [name for name in levels or {} if name not in names]
    if unknown:
        raise SkillsRefused(
            f"skill_levels names {', '.join(map(repr, unknown))}, which the "
            f"Skill Keys don't: they name {', '.join(map(repr, names)) or 'none'}"
        )
    try:
        return job_line(job)
    except LookupError as error:
        raise SkillsRefused(str(error)) from error


def character_skills(
    catalogue: SkillCatalogue,
    job: str,
    names: Iterable[str],
    levels: Mapping[str, object] | None = None,
) -> CharacterSkills:
    """
    The skills of `job` that `names` names, each at its level in `levels`, or
    at its maximum.

    :param job: The profile's `character_class`.
    :param names: The IGN's `Skill Keys` names.
    :param levels: The profile's `skill_levels`: a level by skill name.
    :raises SkillsRefused: `job` has no line; a name isn't a skill of the line,
        or names several; `levels` names a skill `names` doesn't, or gives a
        level outside 1 to the skill's maximum; or a skill's action has no
        duration in the catalogue.
    """
    names = tuple(names)
    levels = dict(levels or {})
    line = check_skill_settings(job, names, levels)
    skills: dict[str, MapleSkill] = {}
    unsure: list[str] = []
    for name in names:
        data = find_skill(catalogue, name, job, line)
        if name in levels:
            level = _level(name, levels[name], data)
        else:
            level = data.max_level
            if depends_on_level(data):
                unsure.append(name)
        try:
            at_level = data.level(level)
        except LookupError as error:
            raise SkillsRefused(f"{name} ({data.id}): {error}") from error
        skills[name] = _skill(catalogue, name, data, at_level)
    return CharacterSkills(skills, tuple(unsure))


def find_skill(
    catalogue: SkillCatalogue, name: str, job: str, line: frozenset[int]
) -> SkillData:
    """
    The skill called `name`, case aside, of a job in `line`.

    :raises SkillsRefused: No skill of the line has that name, naming the
        line's closest; or several do, naming each.
    """
    found = [
        skill
        for ref in catalogue.search(name, "skill")
        if ref.name is not None and ref.name.casefold() == name.casefold()
        for skill in (catalogue.skill(ref.id),)
        if skill.job in line
    ]
    if len(found) == 1:
        return found[0]
    if found:
        listed = ", ".join(f"{s.id} (job {s.job})" for s in found)
        raise SkillsRefused(
            f"{len(found)} skills of {job}'s line are named {name!r}: {listed}"
        )
    closest = _closest(catalogue, name, line)
    hint = f"; the closest are: {', '.join(closest)}" if closest else ""
    raise SkillsRefused(
        f"{job}'s line (jobs {', '.join(map(str, sorted(line)))}) has no skill "
        f"named {name!r}{hint}. The Skill Keys name skills as the client does: "
        f"`python -m game_data search <name> --kind skill`"
    )


def depends_on_level(skill: SkillData) -> bool:
    """Whether the skill's box, `range`, mobs hit or duration differ across its
    levels."""
    return (
        len(
            {
                (lv.lt_x, lv.lt_y, lv.rb_x, lv.rb_y, lv.range, lv.mob_count, lv.time)
                for lv in skill.levels
            }
        )
        > 1
    )


def _level(name: str, given: object, skill: SkillData) -> int:
    """`given`, the profile's level for `name`, once checked against `skill`."""
    if (
        isinstance(given, bool)
        or not isinstance(given, int)
        or not 1 <= given <= skill.max_level
    ):
        raise SkillsRefused(
            f"skill_levels gives {name} level {given!r}: it goes from 1 to "
            f"{skill.max_level}"
        )
    return given


def _skill(
    catalogue: SkillCatalogue, name: str, data: SkillData, level: SkillLevel
) -> MapleSkill:
    return MapleSkill(
        name=name,
        id=data.id,
        level=level.level,
        max_level=data.max_level,
        mob_count=level.mob_count,
        attack_count=level.attack_count,
        cooltime=level.cooltime,
        time=level.time,
        lt=_corner(level.lt_x, level.lt_y),
        rb=_corner(level.rb_x, level.rb_y),
        range=level.range,
        actions=data.actions,
        icon=data.icon,
        cast_time=_cast_time(catalogue, name, data),
    )


def _cast_time(catalogue: SkillCatalogue, name: str, data: SkillData) -> float | None:
    """
    The longest of the skill's own actions, in seconds, unscaled. With none:
    its effect's duration for a skill that moves its caster, or None when it
    has no effect; and None for any other skill (a weapon-based attack).
    """
    durations: list[int] = []
    for action in data.actions:
        try:
            durations.append(catalogue.action_duration(action))
        except LookupError as error:
            raise SkillsRefused(
                f"{name} ({data.id}) plays {action!r}, whose duration the game "
                f"data doesn't give: {error}"
            ) from error
    if durations:
        return max(durations) / 1000
    if data.caster_move and data.effect_duration is not None:
        return data.effect_duration / 1000
    return None


def _corner(x: int | None, y: int | None) -> tuple[int, int] | None:
    return None if x is None or y is None else (x, y)


def _closest(catalogue: SkillCatalogue, name: str, line: frozenset[int]) -> list[str]:
    """The names of the line's skills closest to `name`. Every skill is read,
    so this is for a refusal only."""
    names: dict[str, str] = {}
    for ref in catalogue.search("", "skill"):
        if ref.name is not None and catalogue.skill(ref.id).job in line:
            names.setdefault(ref.name.casefold(), ref.name)
    found = difflib.get_close_matches(name.casefold(), list(names), n=CLOSEST)
    return [names[key] for key in found]
