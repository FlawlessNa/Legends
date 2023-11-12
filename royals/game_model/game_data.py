from dataclasses import dataclass, field
from .maps.base_map import BaseMap


@dataclass
class GameData:
    pass
    # handle: int = field(repr=False)
    # ign: str = field()
    #
    # current_map: BaseMap
    # current_hp_potions: int = field(repr=False)
    # current_mp_potions: int = field(repr=False)
    # current_pet_food: int = field(repr=False)
    # current_mount_food: int = field(repr=False)
    # current_mesos: int = field(repr=False)
    # current_storage_space: int = field(repr=False)
    # current_inventory_equip_space: int = field(repr=False)
    # current_inventory_use_space: int = field(repr=False)
    # current_inventory_etc_space: int = field(repr=False)
    # current_lvl: int = field(repr=False)
