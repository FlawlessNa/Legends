"""
What a cast reaches (#571, spec section 6): the one place the rotation asks what
makes a good spot. The later "mob hunting" topic changes this Provider, or what
it provides, and the rotation follows.

`CAST_REACH` is how far the training skill reaches from the character's feet, in
client px as the skill declares it, and how many mobs make a cast worth it. Its
halves are the ones `MobsHitting` masks the frame with; the character's own
width, which that mask adds, and the chat's top, which it stops at, are not part
of it. `MobsHitting` keeps its own mask.

It stays in client px: the scale to virtual px is the frame's size over the
Camera's play area, which only a read gives (`CastReach.in_virtual`).
"""

import logging
from dataclasses import dataclass
from typing import Any

from botting import PARENT_LOG
from botting.core import Key, Provider, StartupRefused
from maple.model.characters.maple_skills import MapleSkill

from .skills import SKILLS

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


@dataclass(frozen=True, slots=True)
class CastReach:
    """
    How far a cast of the training skill reaches from the character's feet, in
    client px, and how many mobs in reach make it worth casting.

    :ivar left: How far it reaches to the left.
    :ivar right: How far it reaches to the right.
    :ivar up: How far it reaches above the feet.
    :ivar down: How far it reaches below them.
    :ivar min_mobs: The profile's `mob_count_threshold`.
    """

    left: int
    right: int
    up: int
    down: int
    min_mobs: int

    def in_virtual(
        self, client_size: tuple[int, int], play_area: tuple[int, int]
    ) -> tuple[float, float, float, float]:
        """
        `left, right, up, down` in virtual px, scaled as `Camera.to_virtual`
        scales a point: a client px is `play_area / client_size` virtual px.

        :param client_size: The width and height of the frame the mobs were
            found on.
        :param play_area: The Camera's `play_area`, read on that frame.
        """
        sx = client_size[0] / play_area[0]
        sy = client_size[1] / play_area[1]
        return self.left / sx, self.right / sx, self.up / sy, self.down / sy


def cast_reach(skill: MapleSkill, min_mobs: int) -> CastReach | None:
    """
    The skill's reach: half its `horizontal_screen_range` each side; half its
    `vertical_up_screen_range` and `vertical_down_screen_range`, or half its
    `vertical_screen_range` when one is not set, above and below. Halved as
    `MobsHitting` halves them (whole px). `None` when the skill declares no
    horizontal or no vertical range.
    """
    horizontal = skill.horizontal_screen_range
    up = skill.vertical_up_screen_range or skill.vertical_screen_range
    down = skill.vertical_down_screen_range or skill.vertical_screen_range
    if horizontal is None or up is None or down is None:
        return None
    return CastReach(
        left=horizontal // 2,
        right=horizontal // 2,
        up=up // 2,
        down=down // 2,
        min_mobs=min_mobs,
    )


class CastReachProvider(Provider):
    """
    Serves `CAST_REACH`, made once in `setup()` from the profile's
    `mob_count_threshold` and its `training_skill`, in `SKILLS`, as
    `MobsHitting` takes it. No I/O.

    `None` for a profile with no `mob_count_threshold` (`CalibrationBot`), and,
    logged, for a profile with no `training_skill` or a skill that declares no
    range. A skill built from the client's files declares none: its reach comes
    with #637.
    """

    needs = (SKILLS,)

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        mob_count_threshold: int | None = None,
        training_skill: str | None = None,
        **settings: object,
    ) -> None:
        """
        :param mob_count_threshold: How many mobs in reach make a cast worth it.
        :param training_skill: The skill cast at mobs, by its `Skill Keys` name.
        """
        super().__init__(*args, **settings)
        self.mob_count_threshold = mob_count_threshold
        self.training_skill = training_skill

    def setup(self) -> None:
        reach = self._reach()
        # Registered with its value: nothing is read again.
        self.register(CAST_REACH, lambda: reach, initial_value=reach)

    def _reach(self) -> CastReach | None:
        if self.mob_count_threshold is None:
            return None
        if self.training_skill is None:
            logger.warning(
                "%s: the profile names no training_skill, so no cast reach is known.",
                self,
            )
            return None
        skill = self.read(SKILLS).get(self.training_skill)
        if skill is None:
            raise StartupRefused(
                f"{self}: training_skill {self.training_skill!r} isn't one of the "
                "character's skills: name it in the Skill Keys"
            )
        reach = cast_reach(skill, self.mob_count_threshold)
        if reach is None:
            logger.warning(
                "%s: %s declares no screen range, so no cast reach is known.",
                self,
                skill.name,
            )
        return reach


#: How far a cast reaches, in client px, and how many mobs make it worth it;
#: None with no `mob_count_threshold`.
CAST_REACH: Key[CastReach | None] = Key("cast_reach", CastReachProvider)
