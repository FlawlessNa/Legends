from dataclasses import dataclass, field

from botting.models_abstractions import Skill


@dataclass(frozen=True)
class MapleSkill(Skill):
    """
    A MapleStory skill. A buff's icon, which confirms that a cast took effect,
    comes from the client's files, through `maple.screen.buffs`.
    """

    vertical_up_screen_range: int | None = field(default=None, repr=False)
    vertical_down_screen_range: int | None = field(default=None, repr=False)


@dataclass(frozen=True)
class MapleBuff(MapleSkill):
    """A buff the character casts on itself."""

    type: str = field(init=False, default="Buff")


@dataclass(frozen=True)
class MaplePartyBuff(MapleSkill):
    """A buff cast on the party, the character included."""

    type: str = field(init=False, default="Party Buff")
