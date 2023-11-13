from dataclasses import dataclass, field
from .maps.base_map import BaseMap


@dataclass
class GameData:
    pass
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

    def update(self, *args, **kwargs) -> None:
        pass
