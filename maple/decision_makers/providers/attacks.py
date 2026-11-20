"""
The profile's attacks (spec #631 § 6, validation, and § 8, the Provider):
`ATTACKS`, the ordered list `MobsHitting` and the rotation sources go down, and
`FACING`, which way a one-sided attack turns.

```yaml
attacks:
  - skill: Slash Blast
    min_mobs: 3
  - skill: Power Strike
    min_mobs: 1
facing: closest        # or: most. Default: closest
```

Each attack carries its skill, its reach in virtual px with its sides
(`maple.model.characters.reach`), and its `min_mobs`. A skill that plays the
weapon's actions takes its reach, when it has no box, and its cast time from the
weapon the character holds: only then is `WEAPON` read, so only then is the
equipment window opened at start.
"""

import logging
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from enum import Enum
from typing import Any

from botting import PARENT_LOG
from botting.core import Key, Provider, StartupRefused
from game_data.catalogue import Catalogue, CatalogueError
from game_data.catalogue.model import WeaponData
from maple.model.characters.maple_skills import MapleSkill
from maple.model.characters.reach import (
    Armed,
    NoReach,
    Reach,
    Sides,
    WeaponCatalogue,
    armed,
    plays_weapon_actions,
)

from .menus import WEAPON, EquipmentMenuProvider
from .skills import SKILLS

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: The keys an entry of `attacks` has.
ENTRY_KEYS = frozenset({"skill", "min_mobs"})


class Facing(Enum):
    """Which way a one-sided attack faces, when both ways qualify."""

    #: The side of the counted mob nearest the feet.
    CLOSEST = "closest"
    #: The side with more counted mobs; `CLOSEST`'s on a tie.
    MOST = "most"


@dataclass(frozen=True, slots=True)
class Attack:
    """
    One attack of the profile's `attacks`.

    :ivar skill: The skill cast, whose `animation_time` is its cast time.
    :ivar reach: What a cast reaches, facing left, in virtual px.
    :ivar min_mobs: How many mobs in reach make it fire.
    :ivar swings: The weapon's swing boxes, facing left, when `reach` is their
        overlap; None for a reach of the skill's own.
    """

    skill: MapleSkill
    reach: Reach
    min_mobs: int
    swings: tuple[Reach, ...] | None = None

    @property
    def sides(self) -> Sides:
        """Which ways a cast hits: a one-sided attack faces a side."""
        return self.reach.sides


class AttacksProvider(Provider):
    """
    Serves `ATTACKS` and `FACING`, made once in `setup()` from the profile's
    `attacks` and `facing` and the character's `SKILLS`.

    `WEAPON` is read outside `needs`, only when an attack plays the weapon's
    actions: `EquipmentMenuProvider` is built then (`Providers.ensure`), and a
    character whose attacks all play their own actions never opens the
    equipment window. The swings and action delays come from `catalogue`, the
    latest extraction's when none is given.
    """

    needs = (SKILLS,)

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        attacks: object = None,
        facing: object = None,
        catalogue: WeaponCatalogue | None = None,
        **settings: object,
    ) -> None:
        """
        :param attacks: The profile's `attacks`: a list of `skill` and
            `min_mobs`.
        :param facing: The profile's `facing`: `closest`, the default, or
            `most`.
        :param catalogue: Where the weapon's swings and action delays are
            looked up; the latest extraction's catalogue when None.
        """
        super().__init__(*args, **settings)
        self.attacks = attacks
        self.facing = facing
        self.catalogue = catalogue

    def setup(self) -> None:
        """
        :raises StartupRefused: `facing` or `attacks` is malformed; an attack
            isn't one of the character's skills, or has no reach; or the weapon
            can't be read, or the game data has no catalogue.
        """
        facing = self._facing()
        attacks = self._attacks()
        self.register(ATTACKS, lambda: attacks, initial_value=attacks)
        self.register(FACING, lambda: facing, initial_value=facing)

    def _facing(self) -> Facing:
        if self.facing is None:
            return Facing.CLOSEST
        try:
            return Facing(self.facing)
        except ValueError:
            raise StartupRefused(
                f"{self}: facing is {self.facing!r}: it is "
                f"{' or '.join(f.value for f in Facing)}"
            ) from None

    def _attacks(self) -> tuple[Attack, ...] | None:
        if self.attacks is None:
            return None
        entries = self._entries()
        skills = self.read(SKILLS)
        chosen: list[tuple[MapleSkill, int]] = []
        for name, min_mobs in entries:
            skill = skills.get(name)
            if skill is None:
                raise StartupRefused(
                    f"{self}: attack {name!r} isn't one of the character's skills: "
                    f"name it in the Skill Keys, which name "
                    f"{', '.join(map(repr, skills)) or 'none'}"
                )
            chosen.append((skill, min_mobs))
        # Every check that needs no weapon goes first: reading it sends keys.
        found = {
            skill.name: self._armed(skill, None, None)
            for skill, _ in chosen
            if not plays_weapon_actions(skill)
        }
        weapon_based = [skill for skill, _ in chosen if plays_weapon_actions(skill)]
        if weapon_based:
            with self._catalogue() as catalogue:
                weapon = self._weapon()
                for skill in weapon_based:
                    found[skill.name] = self._armed(skill, weapon, catalogue)
        attacks = tuple(
            Attack(
                found[skill.name].skill,
                found[skill.name].reach,
                min_mobs,
                found[skill.name].swings,
            )
            for skill, min_mobs in chosen
        )
        for attack in attacks:
            logger.info(
                "%s: %s reaches %s, %s, in %.3f s, at %d or more mobs.",
                self,
                attack.skill.name,
                attack.reach,
                attack.sides.value,
                attack.skill.animation_time,
                attack.min_mobs,
            )
        return attacks

    def _entries(self) -> list[tuple[str, int]]:
        """The `attacks` setting's skill names and `min_mobs`, in order."""
        example = "such as `attacks: [{skill: Power Strike, min_mobs: 1}]`"
        if not isinstance(self.attacks, list) or not self.attacks:
            raise StartupRefused(
                f"{self}: attacks is {self.attacks!r}: it is a list of attacks, "
                f"each a skill and its min_mobs, {example}"
            )
        entries: list[tuple[str, int]] = []
        for position, entry in enumerate(self.attacks, start=1):
            if not isinstance(entry, Mapping) or set(entry) != ENTRY_KEYS:
                raise StartupRefused(
                    f"{self}: attack {position} is {entry!r}: each attack has a "
                    f"skill and a min_mobs, and nothing else, {example}"
                )
            name: object = entry["skill"]
            min_mobs: object = entry["min_mobs"]
            if not isinstance(name, str):
                raise StartupRefused(
                    f"{self}: attack {position}'s skill is {name!r}: it is a "
                    "skill's name, as the Skill Keys give it"
                )
            if (
                isinstance(min_mobs, bool)
                or not isinstance(min_mobs, int)
                or min_mobs < 1
            ):
                raise StartupRefused(
                    f"{self}: {name}'s min_mobs is {min_mobs!r}: it is a whole "
                    "number, 1 or more"
                )
            entries.append((name, min_mobs))
        return entries

    def _weapon(self) -> WeaponData:
        """
        `WEAPON`, read outside `needs`: its Provider is built now, the first
        time an attack plays the weapon's actions.

        :raises StartupRefused: As `EquipmentMenuProvider.setup()` does.
        """
        providers = self.data.providers
        assert providers is not None, "assembly attaches the Providers first"
        providers.ensure(EquipmentMenuProvider)
        return self.data.read(WEAPON)

    def _catalogue(self) -> AbstractContextManager[WeaponCatalogue]:
        """The catalogue the weapon's swings and delays are looked up in:
        `catalogue`, or the latest extraction's."""
        if self.catalogue is not None:
            return nullcontext(self.catalogue)
        try:
            return Catalogue.latest()
        except CatalogueError as error:
            raise StartupRefused(
                f"{self}: the weapon's swings come from the game data: {error}"
            ) from error

    def _armed(
        self,
        skill: MapleSkill,
        weapon: WeaponData | None,
        catalogue: WeaponCatalogue | None,
    ) -> Armed:
        try:
            return armed(skill, weapon, catalogue)
        except NoReach as error:
            raise StartupRefused(f"{self}: attack {error}") from error


#: The profile's attacks, in order; None when it has no `attacks`
#: (`CalibrationBot`).
ATTACKS: Key[tuple[Attack, ...] | None] = Key("attacks", AttacksProvider)
#: Which way a one-sided attack faces, when both ways qualify.
FACING: Key[Facing] = Key("facing", AttacksProvider)
