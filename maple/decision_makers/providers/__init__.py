"""
MapleStory's Data Keys and the Providers that serve them, one module per
Provider (ADR 0004; `docs/agents/decision-makers.md`).

**Bot-level Providers** serve what `MapleBot.child_init` finds and checks at
start, and the Bot builds them there (`Providers.add`), before any
DecisionMaker:

- `client`: what the client shows (`FRAME`) and its chat keys. The window's
  handle, `HANDLE`, is the generic Bot's (`botting.core.window`), re-exported
  here.
- `screen_readers`: the screen readers, and the sprites they are built on.
- `map`: the map's ID, its `WorldMap`, the game's physics, the position reader.
- `mobs`: the map's mobs, as detection looks for them.
- `character`: the character, and the buffs the profile casts.

**Assembly-built Providers** are built when a DecisionMaker reads one of their
keys:

- `minimap`: the minimap's reading, and the character's virtual position.

A key's legacy name, when it has one, is the `BotData` attribute unported
DecisionMakers read it by; every other key is read by its own name.
"""

from botting.core import HANDLE

from .character import BUFF_NAMES, CHARACTER, CharacterProvider
from .client import CHAT_KEYS, FRAME, ClientProvider
from .map import GAME_PHYSICS, MAP_ID, POSITION_FUSION, WORLD_MAP, MapProvider
from .minimap import (
    MINIMAP_BOX,
    MINIMAP_READING,
    MINIMAP_SHOWN,
    POSITION,
    MinimapProvider,
    MinimapRecovery,
    PositionReader,
)
from .mobs import MOBS, MobsProvider
from .screen_readers import (
    BUFFS_READER,
    CHAT_READER,
    FRAME_CHECK,
    MINIMAP_READER,
    QUICK_SLOTS_READER,
    READER_SPRITES,
    STATUS_BAR_READER,
    ScreenReadersProvider,
)

__all__ = [
    "BUFFS_READER",
    "BUFF_NAMES",
    "CHARACTER",
    "CHAT_KEYS",
    "CHAT_READER",
    "FRAME",
    "FRAME_CHECK",
    "GAME_PHYSICS",
    "HANDLE",
    "MAP_ID",
    "MINIMAP_BOX",
    "MINIMAP_READER",
    "MINIMAP_READING",
    "MINIMAP_SHOWN",
    "MOBS",
    "POSITION",
    "POSITION_FUSION",
    "QUICK_SLOTS_READER",
    "READER_SPRITES",
    "STATUS_BAR_READER",
    "WORLD_MAP",
    "CharacterProvider",
    "ClientProvider",
    "MapProvider",
    "MinimapProvider",
    "MinimapRecovery",
    "MobsProvider",
    "PositionReader",
    "ScreenReadersProvider",
]
