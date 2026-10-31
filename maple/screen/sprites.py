"""
The readers' sprite set: what each reader compares the screen against, loaded
once from the local `game_data` store when the bot starts.

- `Declaration`: one reader's canvases and vectors, by path (`game_data.sprites`).
  Each is either a fixed tuple of paths, or a function of the `Profile` for the
  sprites that depend on it (the job's buff icons, the map's `miniMap` canvas).
- `enabled_readers(decision_makers)`: the declarations a bot's DecisionMakers
  name in their `screen_readers` class attribute, with the frame check's in
  front whenever any reader is enabled, since every reader calls it first.
- `load_reader_sprites(readers, profile)`: checks `configs/game_data.ini` and
  `game_data` `status`, then loads every declared path once into a
  `ReaderSprites`. Anything missing raises `StartupRefused`, saying what to do.

Nothing reloads during a session: a reader asks the `ReaderSprites` it was
given, which never touches the store again.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from game_data.config import CONFIG, STORE, ClientPathNotSet, client_data_path
from game_data.extraction.status import Freshness, status
from game_data.sprites import Sprite, SpriteNotFound, Sprites

GAUGE_LABEL = "UI/StatusBar.img/canvas:gaugeLabel"
"""The status bar's anchor, which the frame check looks for at 1:1."""


class StartupRefused(Exception):
    """The bot can't start: what its readers need is missing. Says what to do."""


@dataclass(frozen=True, slots=True)
class Profile:
    """
    What profile-dependent sprites depend on.

    :ivar job: The character's job, as the profile's `character_class` names it.
    :ivar game_map: The map the bot runs on, as the profile names it.
    :ivar map_id: The client's id for that map, when the map file has one.
    """

    job: str
    game_map: str
    map_id: int | None = None


type Paths = tuple[str, ...] | Callable[[Profile], Iterable[str]]


@dataclass(frozen=True, slots=True)
class Declaration:
    """
    The sprites one reader needs.

    :ivar reader: The reader's name, used in messages.
    :ivar canvases: Canvas paths, or a function of the profile giving them.
    :ivar vectors: Vector paths, or a function of the profile giving them.
    """

    reader: str
    canvases: Paths = ()
    vectors: Paths = ()

    def canvas_paths(self, profile: Profile) -> tuple[str, ...]:
        return _paths(self.canvases, profile)

    def vector_paths(self, profile: Profile) -> tuple[str, ...]:
        return _paths(self.vectors, profile)


def _paths(paths: Paths, profile: Profile) -> tuple[str, ...]:
    return paths if isinstance(paths, tuple) else tuple(paths(profile))


FRAME_CHECK = Declaration("frame check", canvases=(GAUGE_LABEL,))


@dataclass(frozen=True, slots=True)
class ReaderSprites:
    """
    Every enabled reader's sprites, in memory.

    :ivar build: The extraction they came from, or `None` when no reader is
        enabled and nothing was loaded.
    """

    build: str | None
    canvases: dict[str, Sprite] = field(default_factory=dict[str, Sprite])
    vectors: dict[str, tuple[int, int]] = field(
        default_factory=dict[str, tuple[int, int]]
    )

    def canvas(self, path: str) -> Sprite:
        """
        :raises KeyError: No enabled reader declared it.
        """
        try:
            return self.canvases[path]
        except KeyError:
            raise KeyError(
                f"{path} isn't in any enabled reader's declaration"
            ) from None

    def vector(self, path: str) -> tuple[int, int]:
        """
        :raises KeyError: No enabled reader declared it.
        """
        try:
            return self.vectors[path]
        except KeyError:
            raise KeyError(
                f"{path} isn't in any enabled reader's declaration"
            ) from None


def enabled_readers(decision_makers: Iterable[type]) -> list[Declaration]:
    """
    The declarations named by `decision_makers`' `screen_readers` class
    attributes, each once, with `FRAME_CHECK` first when there is any.
    """
    found: list[Declaration] = []
    for class_ in decision_makers:
        declared: Sequence[Declaration] = getattr(class_, "screen_readers", ())
        found.extend(d for d in declared if d not in found)
    if not found:
        return []
    return [FRAME_CHECK, *(d for d in found if d != FRAME_CHECK)]


def load_reader_sprites(
    readers: Sequence[Declaration],
    profile: Profile,
    root: Path = STORE,
    *,
    config: Path = CONFIG,
) -> ReaderSprites:
    """
    Load every sprite `readers` declare, once.

    With no readers, nothing is checked or loaded.

    :raises StartupRefused: `config` is missing or sets no client, the store's
        `status` is `missing` or `stale`, or a declared path names nothing.
    """
    if not readers:
        return ReaderSprites(None)
    if not config.is_file():
        raise StartupRefused(
            f"{config} is missing, and the screen readers need the game data: "
            "copy configs/game_data.example.ini to it, set [Client] Data to the "
            "client's MSCW\\Data folder, then run `python -m game_data extract`"
        )
    try:
        client = client_data_path(config=config)
    except (ClientPathNotSet, NotADirectoryError) as error:
        raise StartupRefused(f"the game data can't be checked: {error}") from error
    found = status(client, root)
    if found.freshness is Freshness.MISSING or found.latest is None:
        raise StartupRefused(
            f"the game data store {root} has no extraction: run "
            "`python -m game_data extract`"
        )
    if found.freshness is Freshness.STALE:
        raise StartupRefused(
            f"the game data is stale: the client changed since build {found.latest} "
            f"({', '.join(found.changed)}). Run `python -m game_data extract`"
        )
    canvases: dict[str, Sprite] = {}
    vectors: dict[str, tuple[int, int]] = {}
    with Sprites.open(found.latest, root) as sprites:
        for declaration in readers:
            try:
                for path in declaration.canvas_paths(profile):
                    if path not in canvases:
                        canvases[path] = sprites.canvas(path)
                for path in declaration.vector_paths(profile):
                    if path not in vectors:
                        vectors[path] = sprites.vector(path)
            except SpriteNotFound as error:
                raise StartupRefused(
                    f"the {declaration.reader} reader needs a sprite build "
                    f"{found.latest} doesn't have: {error}. If the client was "
                    "patched, run `python -m game_data extract`; if it still "
                    "lacks it, the reader needs updating for this client"
                ) from error
    return ReaderSprites(found.latest, canvases, vectors)
