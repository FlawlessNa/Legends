"""
The map the Bot plays on, as `MapleBot.child_init` checked it at start: its ID,
its `WorldMap` from the game data, the game's physics constants, and the reader
of the character's position on it.
"""

from collections.abc import Mapping
from typing import Any

from botting.core import Key, Provider
from maple.model.world import WorldMap
from maple.screen.position import PositionFusion


class MapProvider(Provider):
    """
    Serves the Bot's map: its ID, its `WorldMap`, the game's `Physics.img`
    values, and the `PositionFusion` that reads the character's position on it.

    Bot-level: the Bot checks the map on the minimap at start, and refuses to
    start on another one, before it builds this Provider. `setup()` does no
    I/O.
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        map_id: int,
        world_map: WorldMap | None = None,
        game_physics: Mapping[str, float] | None = None,
        position_fusion: PositionFusion | None = None,
        **settings: object,
    ) -> None:
        """
        :param map_id: The map checked, or identified, at start.
        :param world_map: Its `WorldMap`, or None when no reader is enabled.
        :param game_physics: The game data's `Physics.img` values, with it.
        :param position_fusion: The position's reader, or None when the map has
            no minimap.
        """
        super().__init__(*args, **settings)
        self.map_id = map_id
        self.world_map = world_map
        self.game_physics = game_physics
        self.position_fusion = position_fusion

    def setup(self) -> None:
        self.register(MAP_ID, lambda: self.map_id)
        self.register(WORLD_MAP, lambda: self.world_map)
        self.register(GAME_PHYSICS, lambda: self.game_physics)
        self.register(POSITION_FUSION, lambda: self.position_fusion)


#: The map the Bot plays on, as the game data numbers it.
MAP_ID: Key[int] = Key("map_id", MapProvider)
#: The map's `WorldMap`: its footholds, ropes, portals and minimap transform.
WORLD_MAP: Key[WorldMap | None] = Key("world_map", MapProvider)
#: The game data's `Physics.img` values, which Movement Plans derive from.
GAME_PHYSICS: Key[Mapping[str, float] | None] = Key("game_physics", MapProvider)
#: The reader of the character's virtual position on the map, from the minimap
#: and the play area. None when the map has no minimap.
POSITION_FUSION: Key[PositionFusion | None] = Key("position_fusion", MapProvider)
