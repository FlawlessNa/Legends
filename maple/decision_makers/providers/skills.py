"""
The character's skills, from the client's files (spec #631 § 1).

`SkillsProvider` builds them once, at start, for the skills the IGN's
`Skill Keys` name (`maple.model.characters.maple_skills.character_skills`), each
at the level the profile's `skill_levels` gives, or at its maximum level. A
skill the job's line lacks, or a bad level, refuses the start. One warning names
the skills left at their maximum level whose box, `range`, mobs hit or duration
depend on it.
"""

import logging
from collections.abc import Mapping
from typing import Any

from botting import PARENT_LOG
from botting.core import Key, Provider, StartupRefused
from botting.models_abstractions.base_skill import skill_keys
from game_data.catalogue import Catalogue, CatalogueError
from maple.model.characters.maple_skills import (
    MapleSkill,
    SkillCatalogue,
    SkillsRefused,
    character_skills,
    check_skill_settings,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class SkillsProvider(Provider):
    """
    Serves `SKILLS`: the character's skills, by their `Skill Keys` names.

    Bot-level: `MapleBot.child_init` builds it beside `CharacterProvider`, with
    the profile's job. `setup()` reads the IGN's `Skill Keys` and builds the
    skills from `catalogue`, the latest extraction's when none is given.
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        job: str,
        catalogue: SkillCatalogue | None = None,
        skill_levels: Mapping[str, object] | None = None,
        **settings: object,
    ) -> None:
        """
        :param job: The profile's `character_class`.
        :param catalogue: Where the skills are looked up; the latest
            extraction's catalogue when None.
        :param skill_levels: The profile's `skill_levels`: a level by skill name.
        """
        super().__init__(*args, **settings)
        self.job = job
        self.catalogue = catalogue
        self.skill_levels = skill_levels

    def setup(self) -> None:
        """
        :raises StartupRefused: The skills can't be built (`character_skills`),
            `skill_levels` isn't a mapping, or the game data has no catalogue.
        """
        skills = self._skills()
        self.register(SKILLS, lambda: skills, initial_value=skills)

    def _skills(self) -> dict[str, MapleSkill]:
        try:
            names = tuple(skill_keys(self.data.ign))
        except AssertionError, KeyError:
            # As `startup_chat_keys` reads a missing section: a Bot that casts
            # nothing (a calibration sitting) needs none.
            logger.warning(
                "No Skill Keys for %r in the keybindings: it has no skills.",
                self.data.ign,
            )
            names = ()
        if self.skill_levels is not None and not isinstance(self.skill_levels, Mapping):
            raise StartupRefused(
                f"skill_levels must map skill names to levels, got "
                f"{self.skill_levels!r}"
            )
        try:
            check_skill_settings(self.job, names, self.skill_levels)
        except SkillsRefused as error:
            raise StartupRefused(f"{self.data.ign}'s skills: {error}") from error
        if not names:
            return {}
        if self.catalogue is not None:
            return self._build(self.catalogue, names)
        try:
            with Catalogue.latest() as catalogue:
                return self._build(catalogue, names)
        except CatalogueError as error:
            raise StartupRefused(
                f"{self.data.ign}'s skills come from the game data: {error}"
            ) from error

    def _build(
        self, catalogue: SkillCatalogue, names: tuple[str, ...]
    ) -> dict[str, MapleSkill]:
        try:
            built = character_skills(catalogue, self.job, names, self.skill_levels)
        except SkillsRefused as error:
            raise StartupRefused(f"{self.data.ign}'s skills: {error}") from error
        if built.unsure_levels:
            logger.warning(
                "%s: %s depend on their level and are assumed at their maximum: "
                "give each its level in the profile's skill_levels, or their "
                "reach, mobs hit or duration may not be the character's.",
                self.data.ign,
                ", ".join(built.unsure_levels),
            )
        return built.skills


#: The character's skills, by their `Skill Keys` names.
SKILLS: Key[Mapping[str, MapleSkill]] = Key("skills", SkillsProvider)
