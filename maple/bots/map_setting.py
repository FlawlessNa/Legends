"""
The profile's `map` setting: which map the bot is on, by its game name or id.

The launcher profile passes `settings` to the bot verbatim
(`maple/launchers/profile.py`), so the bot is what reads this. A name goes
through `Catalogue.map()`, which owns the matching rules.
"""

from __future__ import annotations

from game_data.catalogue import Catalogue, CatalogueError
from maple.launchers.profile import ProfileError
from maple.model.mechanics.minimap_creation.minimap_edits_model import (
    MinimapEditsManager,
)

AUTO = "auto"
AUTO_REFUSAL = "map: auto needs map identification (#387), which has not landed yet"


def resolve_map_id(map_setting: str | int | None, game_map: str | None) -> int | None:
    """
    The id of the map the profile names, or `None` when it names it only by a
    map file (`game_map`, kept until the map files are retired).

    :param map_setting: The profile's `map`: a game map name, a map id, or `auto`.
    :param game_map: The profile's `game_map`: a JSON map file's name.
    :raises ProfileError: Neither is set; `map` is set without `game_map` (the
        old map loading still needs a map file, until #399); `map` is `auto`,
        unknown or ambiguous; or the map file's own `map_id` is another map
        than `map`.
    """
    if map_setting is None:
        if not game_map:
            raise ProfileError(
                "The profile's settings need `map`: a game map name such as "
                "'Victoria Road: Ellinia', or a map id."
            )
        return None
    if isinstance(map_setting, str) and map_setting.strip().casefold() == AUTO:
        raise ProfileError(AUTO_REFUSAL)
    if not game_map:
        raise ProfileError(
            f"`map: {map_setting}` needs `game_map` too: the map file in "
            "configs/maps/ is still needed until the map files are retired (#399)."
        )
    try:
        with Catalogue.latest() as catalogue:
            map_id = catalogue.map(map_setting).id
    except CatalogueError as error:
        raise ProfileError(f"`map` can't be resolved: {error}") from error
    except LookupError as error:
        raise ProfileError(f"`map: {map_setting}`: {error}") from error
    map_file = MinimapEditsManager.from_json(game_map)
    if map_file is not None and map_file.map_id not in (None, map_id):
        raise ProfileError(
            f"`map: {map_setting}` is map {map_id}, but the map file "
            f"{game_map!r} says it is map {map_file.map_id}."
        )
    return map_id
