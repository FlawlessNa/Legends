"""
The profile's `map` setting: which map the bot is on, by its game name or id.

The launcher profile passes `settings` to the bot verbatim
(`maple/launchers/profile.py`), so the bot is what reads this. A name goes
through `Catalogue.map()`, which owns the matching rules. `auto` leaves the map
to be identified on screen at start (`maple/bots/map_check.py`).
"""

from __future__ import annotations

from game_data.catalogue import Catalogue, CatalogueError
from maple.launchers.profile import ProfileError

AUTO = "auto"


def is_auto(map_setting: str | int | None) -> bool:
    """Whether the profile's `map` is `auto`, case and spaces aside."""
    return isinstance(map_setting, str) and map_setting.strip().casefold() == AUTO


def refuse_game_map(game_map: object) -> None:
    """
    `game_map` named a hand-made map file under `configs/maps/`. The map files
    are retired (#399): the map comes from the game files, named by `map`, and
    the mobs to look for from `mobs`.

    :raises ProfileError: `game_map` is set.
    """
    if game_map is None:
        return
    raise ProfileError(
        f"`game_map: {game_map}` is retired with the map files (#399). Name the "
        "map by `map`: its game name such as 'Victoria Road: Ellinia', its id, or "
        "`auto`. The map file's `mobs` list moves to the profile's `mobs` "
        "setting, for example `mobs: [Bubbling]`."
    )


def resolve_map_id(map_setting: str | int | None) -> int | None:
    """
    The id of the map the profile names, or `None` when it says `auto`.

    :param map_setting: The profile's `map`: a game map name, a map id, or `auto`.
    :raises ProfileError: `map` is not set, or is unknown or ambiguous.
    """
    if map_setting is None:
        raise ProfileError(
            "The profile's settings need `map`: a game map name such as "
            "'Victoria Road: Ellinia', a map id, or `auto`."
        )
    if is_auto(map_setting):
        return None
    try:
        with Catalogue.latest() as catalogue:
            return catalogue.map(map_setting).id
    except CatalogueError as error:
        raise ProfileError(f"`map` can't be resolved: {error}") from error
    except LookupError as error:
        raise ProfileError(f"`map: {map_setting}`: {error}") from error
