from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from botting.models import BaseMap


@dataclass
class GameData(ABC):
    """
    Base class to represent in-game data. This class is meant to be inherited by a class that will be used to store data about the game client.
    Here, sample data attributes are provided, but the inheriting class can add/remove more attributes as needed.
    """
    handle: int = field(repr=False)
    ign: str = field()

    current_map: BaseMap = field(repr=False, default=None)
    current_pos: tuple[float, float] = field(repr=False, default=None)
    current_hp_potions: int = field(repr=False, default=None)
    current_mp_potions: int = field(repr=False, default=None)
    current_pet_food: int = field(repr=False, default=None)
    current_mount_food: int = field(repr=False, default=None)
    current_mesos: int = field(repr=False, default=None)
    current_storage_space: int = field(repr=False, default=None)
    current_inventory_equip_space: int = field(repr=False, default=None)
    current_inventory_use_space: int = field(repr=False, default=None)
    current_inventory_etc_space: int = field(repr=False, default=None)
    current_lvl: int = field(repr=False, default=None)

    @abstractmethod
    def update(self, *args, **kwargs) -> None:
        """
        This method will be called whenever an in-game action is completed/cancelled. It is meant to update the data attributes of the class.
        It should update the relevant attributes based on the action that was completed/cancelled.
        Examples:
            If the character performed movements, then the current position (and perhaps current map) should be updated.
            If the character used a potion, then the current potion count should be updated.
            etc.
        """
        pass
