from abc import ABC
from dataclasses import dataclass
from typing import Any

from .base_mob import BaseMob


@dataclass
class BaseMap(ABC):
    """
    This class is an example of how a map can be defined.
    A map may contain the following:
    - A set of mobs that can be found within it.
    - A set of coordinates that define the on-screen area used for detection.
    - A Minimap associated with that Map
    - Connections to other minimaps
    This is merely an example. Map implementations may vary.
    """

    mobs: tuple[BaseMob, ...]
    minimap: Any
