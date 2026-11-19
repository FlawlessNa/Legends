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

The replies switch, `REPLIES_ON`, is the generic Bot's too
(`botting.core.replies`), re-exported here.

**Assembly-built Providers** are built when a DecisionMaker reads one of their
keys:

- `minimap`: the minimap's reading, and the character's virtual position.
- `destination`: where the rotation heads next, and the platform it is on.
  `DESTINATION` is steerable: a DecisionMaker claims it to send the character
  elsewhere (`wander`, or `botting.core.fixed` and `following`).
- `on_screen`: where the character is on screen, as a box on the client.
- `buffs`: the profile's buffs, as their icons show them.
- `status_bar`: the status bar's reading.
- `quick_slots`: the quick slots' reading.
- `chat`: the chat's new lines, and whether its log is shown.

A key's legacy name, when it has one, is the `BotData` attribute unported
DecisionMakers read it by; every other key is read by its own name.
"""

from botting.core import HANDLE, REPLIES_ON

from .buffs import BUFFS_READING, BuffsProvider
from .character import BUFF_NAMES, CHARACTER, CharacterProvider
from .chat import CHAT_LINES, CHAT_SHOWN, ChatProvider
from .client import CHAT_KEYS, FRAME, ClientProvider
from .destination import (
    DESTINATION,
    DESTINATION_PLATFORM,
    DestinationProvider,
    wander,
)
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
from .on_screen import ON_SCREEN_POSITION, OnScreenPositionProvider
from .quick_slots import QUICK_SLOTS_READING, QuickSlotsProvider
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
from .status_bar import STATUS_BAR_READING, StatusBarProvider

__all__ = [
    "BUFFS_READER",
    "BUFFS_READING",
    "BUFF_NAMES",
    "CHARACTER",
    "CHAT_KEYS",
    "CHAT_LINES",
    "CHAT_READER",
    "CHAT_SHOWN",
    "DESTINATION",
    "DESTINATION_PLATFORM",
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
    "ON_SCREEN_POSITION",
    "POSITION",
    "POSITION_FUSION",
    "QUICK_SLOTS_READER",
    "QUICK_SLOTS_READING",
    "READER_SPRITES",
    "REPLIES_ON",
    "STATUS_BAR_READER",
    "STATUS_BAR_READING",
    "WORLD_MAP",
    "BuffsProvider",
    "CharacterProvider",
    "ChatProvider",
    "ClientProvider",
    "DestinationProvider",
    "MapProvider",
    "MinimapProvider",
    "MinimapRecovery",
    "MobsProvider",
    "OnScreenPositionProvider",
    "PositionReader",
    "QuickSlotsProvider",
    "ScreenReadersProvider",
    "StatusBarProvider",
    "wander",
]
