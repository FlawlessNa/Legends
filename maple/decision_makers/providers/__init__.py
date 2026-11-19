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
- `profile`: the profile's speed and jump stats, and its Calibration constants.

The replies switch, `REPLIES_ON`, is the generic Bot's too
(`botting.core.replies`), re-exported here.

**Assembly-built Providers** are built when a DecisionMaker reads one of their
keys:

- `minimap`: the minimap's reading, and the character's virtual position.
- `destination`: where the rotation heads next, and the platform it is on,
  from the destination source the profile's `rotation` names (`sources/`).
  `DESTINATION` is steerable: a DecisionMaker claims it to send the character
  elsewhere (`wander`, or `botting.core.fixed` and `following`).
- `pathing`: the Path to `DESTINATION`, its Movement Plan, and what the plan is
  compiled with at dispatch.
- `on_screen`: where the character is on screen, as a box on the client.
- `buffs`: the profile's buffs, as their icons show them.
- `menus`: the ability menu, with the speed and jump it shows, and the
  inventory menu.
- `status_bar`: the status bar's reading.
- `quick_slots`: the quick slots' reading.
- `chat`: the chat's new lines, and whether its log is shown.
- `other_players`: the other players' minimap markers, in virtual px.
- `hunting_area`: the Hunting Area the `hunting_area` rotation hunts, its
  stretches a Path reaches, and whether another player has settled in it;
  each None with another rotation.
- `cast_reach`: how far a cast of the training skill reaches, and how many
  mobs make it worth it.
"""

from botting.core import HANDLE, REPLIES_ON

from .buffs import BUFFS_READING, BuffsProvider
from .cast_reach import CAST_REACH, CastReach, CastReachProvider
from .character import BUFF_NAMES, CHARACTER, CharacterProvider
from .chat import CHAT_LINES, CHAT_SHOWN, ChatProvider
from .client import CHAT_KEYS, FRAME, ClientProvider
from .destination import (
    DESTINATION,
    DESTINATION_PLATFORM,
    DestinationProvider,
    wander,
)
from .hunting_area import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    HUNTING_AREA,
    AreaPresence,
    HuntingAreaProvider,
    PresenceCounter,
)
from .map import GAME_PHYSICS, MAP_ID, POSITION_FUSION, WORLD_MAP, MapProvider
from .menus import (
    ABILITY_MENU,
    ABILITY_MENU_DISPLAYED,
    AVAILABLE_AP,
    CURRENT_MESOS,
    INVENTORY_MENU,
    INVENTORY_MENU_ACTIVE_TAB,
    INVENTORY_MENU_DISPLAYED,
    INVENTORY_MENU_EXTENDED,
    INVENTORY_SPACE_LEFT,
    JUMP_MULTIPLIER,
    SPEED_MULTIPLIER,
    AbilityMenuProvider,
    InventoryMenuProvider,
)
from .minimap import (
    MINIMAP_BOX,
    MINIMAP_READING,
    MINIMAP_SHOWN,
    POSITION,
    MinimapProvider,
    MinimapRecovery,
    PositionReader,
    position_or_unsure,
)
from .mobs import MOBS, MobsProvider
from .on_screen import ON_SCREEN_POSITION, OnScreenPositionProvider
from .other_players import OTHER_PLAYERS, OtherPlayers, OtherPlayersProvider
from .pathing import (
    ACTION_DURATION,
    ALWAYS_RELEASE_KEYS,
    MOVEMENT_HANDLER,
    MOVEMENTS,
    PATH,
    MovementPlan,
    PathingProvider,
    actionable,
    pathing,
)
from .profile import (
    CALIBRATION,
    PROFILE_JUMP_MULTIPLIER,
    PROFILE_SPEED_MULTIPLIER,
    ProfileProvider,
)
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
    "ABILITY_MENU",
    "ABILITY_MENU_DISPLAYED",
    "ACTION_DURATION",
    "ALWAYS_RELEASE_KEYS",
    "AREA_PRESENCE",
    "AREA_STRETCHES",
    "AVAILABLE_AP",
    "BUFFS_READER",
    "BUFFS_READING",
    "BUFF_NAMES",
    "CALIBRATION",
    "CAST_REACH",
    "CHARACTER",
    "CHAT_KEYS",
    "CHAT_LINES",
    "CHAT_READER",
    "CHAT_SHOWN",
    "CURRENT_MESOS",
    "DESTINATION",
    "DESTINATION_PLATFORM",
    "FRAME",
    "FRAME_CHECK",
    "GAME_PHYSICS",
    "HANDLE",
    "HUNTING_AREA",
    "INVENTORY_MENU",
    "INVENTORY_MENU_ACTIVE_TAB",
    "INVENTORY_MENU_DISPLAYED",
    "INVENTORY_MENU_EXTENDED",
    "INVENTORY_SPACE_LEFT",
    "JUMP_MULTIPLIER",
    "MAP_ID",
    "MINIMAP_BOX",
    "MINIMAP_READER",
    "MINIMAP_READING",
    "MINIMAP_SHOWN",
    "MOBS",
    "MOVEMENTS",
    "MOVEMENT_HANDLER",
    "ON_SCREEN_POSITION",
    "OTHER_PLAYERS",
    "PATH",
    "POSITION",
    "POSITION_FUSION",
    "PROFILE_JUMP_MULTIPLIER",
    "PROFILE_SPEED_MULTIPLIER",
    "QUICK_SLOTS_READER",
    "QUICK_SLOTS_READING",
    "READER_SPRITES",
    "REPLIES_ON",
    "SPEED_MULTIPLIER",
    "STATUS_BAR_READER",
    "STATUS_BAR_READING",
    "WORLD_MAP",
    "AbilityMenuProvider",
    "AreaPresence",
    "BuffsProvider",
    "CastReach",
    "CastReachProvider",
    "CharacterProvider",
    "ChatProvider",
    "ClientProvider",
    "DestinationProvider",
    "HuntingAreaProvider",
    "InventoryMenuProvider",
    "MapProvider",
    "MinimapProvider",
    "MinimapRecovery",
    "MobsProvider",
    "MovementPlan",
    "OnScreenPositionProvider",
    "OtherPlayers",
    "OtherPlayersProvider",
    "PathingProvider",
    "PositionReader",
    "PresenceCounter",
    "ProfileProvider",
    "QuickSlotsProvider",
    "ScreenReadersProvider",
    "StatusBarProvider",
    "actionable",
    "pathing",
    "position_or_unsure",
    "wander",
]
