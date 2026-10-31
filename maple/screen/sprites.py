"""
The readers' sprite set: what each reader compares the screen against, loaded
once from the local `game_data` store when the bot starts.

- `Declaration`: one reader's canvases and vectors, by path (`game_data.sprites`).
  Each is either a fixed tuple of paths, or a function of the `Profile` for the
  sprites that depend on it (the map's `miniMap` canvas). A reader may also name
  skills whose icons it needs (the buffs): each is found in the catalogue by its
  name and the profile's job (`skill_icon_path`), and loaded like a canvas.
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
from typing import Protocol

from game_data.catalogue.catalogue import Catalogue
from game_data.catalogue.model import Ref, SkillData
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
    :ivar buffs: The buffs the bot keeps up, by skill name: the buffs reader
        compares the screen with their icons.
    """

    job: str
    game_map: str
    map_id: int | None = None
    buffs: tuple[str, ...] = ()


type Paths = tuple[str, ...] | Callable[[Profile], Iterable[str]]


@dataclass(frozen=True, slots=True)
class Declaration:
    """
    The sprites one reader needs.

    :ivar reader: The reader's name, used in messages.
    :ivar canvases: Canvas paths, or a function of the profile giving them.
    :ivar vectors: Vector paths, or a function of the profile giving them.
    :ivar skill_icons: Names of skills whose icons the reader needs, or a
        function of the profile giving them. Each is found in the catalogue for
        the profile's job (`skill_icon_path`).
    """

    reader: str
    canvases: Paths = ()
    vectors: Paths = ()
    skill_icons: Paths = ()

    def canvas_paths(self, profile: Profile) -> tuple[str, ...]:
        return _paths(self.canvases, profile)

    def vector_paths(self, profile: Profile) -> tuple[str, ...]:
        return _paths(self.vectors, profile)

    def skill_names(self, profile: Profile) -> tuple[str, ...]:
        return _paths(self.skill_icons, profile)


def _paths(paths: Paths, profile: Profile) -> tuple[str, ...]:
    return paths if isinstance(paths, tuple) else tuple(paths(profile))


FRAME_CHECK = Declaration("frame check", canvases=(GAUGE_LABEL,))

# The profile's `character_class`, case aside -> the client's job id. A job has
# its own skills and those of every job before it, back to the beginner's (0).
JOB_IDS: dict[str, int] = {
    "beginner": 0,
    "swordsman": 100,
    "fighter": 110,
    "page": 120,
    "spearman": 130,
    "magician": 200,
    "wizardfirepoison": 210,
    "magefirepoison": 211,
    "wizardicelightning": 220,
    "mageicelightning": 221,
    "cleric": 230,
    "priest": 231,
    "bishop": 232,
    "archer": 300,
    "hunter": 310,
    "crossbowman": 320,
    "rogue": 400,
    "assassin": 410,
    "hermit": 411,
    "bandit": 420,
}


def job_line(job: str) -> frozenset[int]:
    """
    The ids of `job` and of every job before it: Bishop (232) is
    `{0, 200, 230, 231, 232}`.

    :raises LookupError: `job` isn't in `JOB_IDS`.
    """
    try:
        job_id = JOB_IDS[job.casefold()]
    except KeyError:
        raise LookupError(
            f"no job id for {job!r}; the known jobs are {', '.join(JOB_IDS)}"
        ) from None
    tens = job_id - job_id % 10
    return frozenset({0, job_id - job_id % 100, *range(tens, job_id + 1)})


class SkillSource(Protocol):
    """What `skill_icon_path` asks of a `Catalogue`."""

    def search(self, text: str, kind: str | None = None) -> list[Ref]: ...

    def skill(self, name_or_id: str | int) -> SkillData: ...


def skill_icon_path(catalogue: SkillSource, name: str, job: str) -> str:
    """
    The sprite path of the icon of `job`'s skill called `name`: the catalogue's
    `search`, kept to whole-name matches, case aside, of a job in `job_line`.

    :raises LookupError: The job is unknown, or not exactly one of its skills
        has that name.
    """
    line = job_line(job)
    found = [
        skill
        for ref in catalogue.search(name, "skill")
        if ref.name is not None and ref.name.casefold() == name.casefold()
        for skill in (catalogue.skill(ref.id),)
        if skill.job in line
    ]
    if len(found) != 1:
        which = ", ".join(f"{s.id} (job {s.job})" for s in found) or "none"
        raise LookupError(
            f"{job} needs exactly one skill named {name!r} among jobs "
            f"{sorted(line)}, and has {which}"
        )
    skill = found[0]
    return f"Skill/{skill.job:03d}.img/skill/{skill.id:07d}/icon"


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
    skill_icons: dict[str, Sprite] = field(default_factory=dict[str, Sprite])

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

    def skill_icon(self, name: str) -> Sprite:
        """
        A skill's icon, by the skill's name.

        :raises KeyError: No enabled reader declared it.
        """
        try:
            return self.skill_icons[name]
        except KeyError:
            raise KeyError(
                f"the {name!r} icon isn't in any enabled reader's declaration"
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
        `status` is `missing` or `stale`, a declared path names nothing, or a
        declared skill isn't the job's.
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
    icon_paths = _skill_icon_paths(readers, profile, found.latest, root)
    skill_icons: dict[str, Sprite] = {}
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
        for name, path in icon_paths.items():
            try:
                skill_icons[name] = sprites.canvas(path)
            except SpriteNotFound as error:
                raise StartupRefused(
                    f"the {name!r} skill has no icon in build {found.latest}: {error}"
                ) from error
    return ReaderSprites(found.latest, canvases, vectors, skill_icons)


def _skill_icon_paths(
    readers: Sequence[Declaration], profile: Profile, build: str, root: Path
) -> dict[str, str]:
    """Each declared skill's icon path, from the catalogue, which isn't opened
    when no reader names a skill."""
    wanted = {
        name: declaration.reader
        for declaration in readers
        for name in declaration.skill_names(profile)
    }
    if not wanted:
        return {}
    paths: dict[str, str] = {}
    with Catalogue.open(build, root) as catalogue:
        for name, reader in wanted.items():
            try:
                paths[name] = skill_icon_path(catalogue, name, profile.job)
            except LookupError as error:
                raise StartupRefused(
                    f"the {reader} reader can't find the {name!r} icon: {error}. "
                    "Check the skill's name and the profile's character_class"
                ) from error
    return paths
