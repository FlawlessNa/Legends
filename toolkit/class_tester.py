import asyncio
import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations import RoyalsData
from royals.models_implementations.minimaps import (
    KerningLine1Area1,
    LudiFreeMarketTemplate,
)
from royals.models_implementations.characters import Magician
from royals.models_implementations.mobs import Bubbling
from royals.bot_implementations.actions.hit_mobs import hit_closest_in_range
from royals.bot_implementations.actions.random_rotation import random_rotation


HANDLE = 0x02300A26


if __name__ == "__main__":
    data = RoyalsData(HANDLE, "FarmFest1")
    data.current_minimap = LudiFreeMarketTemplate()
    data.current_minimap_area_box = data.current_minimap.get_map_area_box(HANDLE)
    data.update("current_minimap_position")
    generator = random_rotation(data)

    while True:
        action = next(generator)
        if action:
            asyncio.run(action())
