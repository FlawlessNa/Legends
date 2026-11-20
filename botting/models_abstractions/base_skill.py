from abc import ABC, abstractmethod
from functools import lru_cache

from botting.utilities import config_reader


class Skill(ABC):
    """
    What the cast path asks of a skill: its name, the key it is bound to, and
    how long a cast of it takes.

    :ivar name: The skill's name, as the IGN's `Skill Keys` names it.
    """

    name: str

    @property
    @abstractmethod
    def animation_time(self) -> float:
        """How long a cast takes, in seconds: the key is held that long."""

    @lru_cache  # noqa: B019 - skills are few and live as long as the Bot
    def key_bind(self, ign: str) -> str:
        """The key `ign`'s `Skill Keys` bind this skill to."""
        return skill_keys(ign)[self.name]


def skill_keys(ign: str) -> dict[str, str]:
    """`ign`'s `Skill Keys`: each skill's name, and the key it is bound to."""
    return eval(str(config_reader("keybindings", ign, "Skill Keys")))
