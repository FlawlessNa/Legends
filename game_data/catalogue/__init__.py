"""
The catalogue: an extraction's typed tables, and the lookups that read them.

It is built only from the extraction's raw layer, never from the client, so it
can be rebuilt wherever the store is. The public API:

- `Catalogue`: one extraction's `catalogue.sqlite`, opened with
  `Catalogue.latest(root)` or `Catalogue.open(build, root)`. `map` and
  `map_layers` look a map up by name or ID, `mob` a mob, and `skill` a skill
  with its levels; `action_duration` and `skill_duration` say how long a
  character action and a skill's first action take; `maps_spawning` lists
  the maps a mob is on; `search` lists what matches some text; `physics`
  gives `Map/Physics.img`; and `item_icons`, `meso_frames` and
  `damage_digits` give the sprites drawn over mobs (`catalogue`). Each
  returns frozen dataclasses (`model`).
- `build_catalogue`: the catalogue hook `extract` calls (`build`).
- `SCHEMA_VERSION` and the tables (`schema`). `docs/agents/game-data.md`
  documents every column, for anyone querying the file directly.
- `CatalogueError`: the raw layer, or the store, isn't as expected. It names
  the image and node (`trees`).

How maps are read is `maps`, and the footholds and ropes drawn on objects and
tiles, ported from the v83 module, are `geometry`. Mobs are read in `mobs`,
skills and the character's actions in `skills`, and item icons, mesos and
damage digits in `occluders`.
"""

from .build import build, build_catalogue
from .catalogue import Catalogue
from .model import (
    Background,
    Bounds,
    DamageDigit,
    Foothold,
    ItemIcon,
    LayerFrame,
    MapData,
    MapLayer,
    MapRef,
    MesoFrame,
    Minimap,
    MobData,
    MobFrame,
    Portal,
    Ref,
    Rope,
    SkillData,
    SkillLevel,
    Spawn,
)
from .schema import CATALOGUE, SCHEMA_VERSION
from .trees import CatalogueError

__all__ = [
    "CATALOGUE",
    "SCHEMA_VERSION",
    "Background",
    "Bounds",
    "Catalogue",
    "CatalogueError",
    "DamageDigit",
    "Foothold",
    "ItemIcon",
    "LayerFrame",
    "MapData",
    "MapLayer",
    "MapRef",
    "MesoFrame",
    "Minimap",
    "MobData",
    "MobFrame",
    "Portal",
    "Ref",
    "Rope",
    "SkillData",
    "SkillLevel",
    "Spawn",
    "build",
    "build_catalogue",
]
