"""
Building an extraction's `catalogue.sqlite` from its `raw.sqlite`, and nothing
else: the client is never read, so a catalogue can be rebuilt wherever the
store is.

It reads:

- `String/Map.img`, `String/Mob.img`, `String/Npc.img` and
  `String/Skill.img` into `strings`. `Map.img` groups maps by region,
  `<region>/<id>/mapName`, `streetName` and `mapDesc`; the others are
  `<id>/name`, and a skill's `<id>/desc` too. A `Skill.img` entry with a
  `bookName` names a job's skill book, not a skill, and is left out.
- every map image, `Map/Map/Map<n>/<id>.img`, and the assets it draws from
  (`maps`).
- `Map/Physics.img` into `physics`, one row per value.
- every mob image, `Mob/<id>.img`, into `mobs` and `mob_frames` (`mobs`).
- every job's skill image, `Skill/<job>.img`, into `skills` and
  `skill_levels`, and `Character/00002000.img` into `actions` (`skills`).
- every item image, `Item/<category>/<prefix>.img`, into `item_icons`;
  `Item/Special/0900.img` into `meso_frames`; and `Effect/BasicEff.img` into
  `damage_digits` (`occluders`).

An image the client doesn't have, such as `String/Map.img` in a client of only
mobs, leaves its tables empty. One that is there but isn't as expected is an
error naming the image and the node, and builds nothing.

The catalogue is written beside the raw layer under a temporary name, and
renamed over the old one when it's complete.
"""

import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from game_data.extraction import ImageStore

from .maps import MAP_IMAGE, Assets, MapReader, Row
from .mobs import MOB_IMAGE, read_mobs
from .occluders import (
    DIGITS_IMAGE,
    ITEM_IMAGE,
    MESO_IMAGE,
    read_damage_digits,
    read_item_icons,
    read_meso_frames,
)
from .schema import CATALOGUE, INDEXES, SCHEMA_VERSION, TABLES
from .skills import ACTIONS_IMAGE, SKILL_IMAGE, read_actions, read_skills
from .trees import CatalogueError, Tree

RAW = "raw.sqlite"
STRING_KINDS = {
    "mob": "String/Mob.img",
    "npc": "String/Npc.img",
    "skill": "String/Skill.img",
}


def build_catalogue(extraction: Path, images: ImageStore) -> int:
    """
    The catalogue hook `extract` calls: builds the catalogue in the
    extraction's folder, and returns its schema version.
    """
    del images
    build(extraction)
    return SCHEMA_VERSION


def build(extraction: Path) -> None:
    """
    Builds `catalogue.sqlite` in an extraction's folder, from its raw layer.

    :raises CatalogueError: The raw layer isn't as expected.
    """
    raw_path = extraction / RAW
    if not raw_path.is_file():
        raise CatalogueError(f"{extraction} has no {RAW} to build a catalogue from")
    target = extraction / CATALOGUE
    temporary = extraction / f"{CATALOGUE}.{os.getpid()}.tmp"
    temporary.unlink(missing_ok=True)
    try:
        with (
            closing(
                sqlite3.connect(f"{raw_path.resolve().as_uri()}?mode=ro", uri=True)
            ) as raw,
            closing(sqlite3.connect(temporary)) as catalogue,
        ):
            _write(_Raw(raw), catalogue)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class _Raw:
    """The raw layer's trees, by image path."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def tree(self, path: str) -> Tree | None:
        row = self._connection.execute(
            "SELECT tree FROM images WHERE path = ?", (path,)
        ).fetchone()
        return None if row is None else Tree.of(path, json.loads(row[0]))

    def maps(self) -> list[tuple[int, str]]:
        """Every map image's ID and path, by ID."""
        return self._numbered("Map/Map/Map[0-9]/*.img", MAP_IMAGE)

    def item_trees(self) -> list[tuple[str, Tree]]:
        """Each item image's category and tree, by path."""
        rows = self._connection.execute(
            "SELECT path FROM images WHERE path GLOB 'Item/*/*.img' ORDER BY path"
        ).fetchall()
        found: list[tuple[str, Tree]] = []
        for (path,) in rows:
            match = ITEM_IMAGE.fullmatch(path)
            if match:
                tree = self.tree(path)
                assert tree is not None
                found.append((match["category"], tree))
        return found

    def numbered_trees(self, glob: str, pattern: re.Pattern[str]) -> dict[int, Tree]:
        """
        The trees of the images whose path `pattern` matches whole, by the
        number its first group captures. `glob` narrows the query.
        """
        found: dict[int, Tree] = {}
        for number, path in self._numbered(glob, pattern):
            if number in found:
                raise CatalogueError(
                    f"{path} and {found[number].image} are both number {number}"
                )
            tree = self.tree(path)
            assert tree is not None
            found[number] = tree
        return found

    def _numbered(self, glob: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
        rows = self._connection.execute(
            "SELECT path FROM images WHERE path GLOB ?", (glob,)
        ).fetchall()
        found: list[tuple[int, str]] = []
        for (path,) in rows:
            match = pattern.fullmatch(path)
            if match:
                found.append((int(match[1]), path))
        return sorted(found)


def _write(raw: _Raw, catalogue: sqlite3.Connection) -> None:
    catalogue.execute("PRAGMA journal_mode = OFF")
    catalogue.execute("PRAGMA synchronous = OFF")
    for table in TABLES:
        catalogue.execute(table)
    strings = _strings(raw)
    _insert(catalogue, "strings", strings.rows)
    reader = MapReader(Assets(raw.tree), strings.maps)
    seen: dict[int, str] = {}
    for map_id, path in raw.maps():
        if map_id in seen:
            raise CatalogueError(f"{path} and {seen[map_id]} are both map {map_id}")
        seen[map_id] = path
        tree = raw.tree(path)
        assert tree is not None
        reader.read(map_id, tree.expect("property"))
    rows = reader.rows
    for table in (
        "maps",
        "footholds",
        "ropes",
        "portals",
        "spawns",
        "map_layers",
        "layer_frames",
    ):
        _insert(catalogue, table, getattr(rows, table))
    _insert(catalogue, "physics", _physics(raw))
    mobs = read_mobs(raw.numbered_trees("Mob/*.img", MOB_IMAGE), strings.mobs)
    _insert(catalogue, "mobs", mobs.mobs)
    _insert(catalogue, "mob_frames", mobs.mob_frames)
    skills = read_skills(raw.numbered_trees("Skill/*.img", SKILL_IMAGE), strings.skills)
    _insert(catalogue, "skills", skills.skills)
    _insert(catalogue, "skill_levels", skills.skill_levels)
    actions = raw.tree(ACTIONS_IMAGE)
    if actions is not None:
        _insert(catalogue, "actions", read_actions(actions))
    _insert(catalogue, "item_icons", read_item_icons(raw.item_trees()))
    mesos = raw.tree(MESO_IMAGE)
    if mesos is not None:
        _insert(catalogue, "meso_frames", read_meso_frames(mesos))
    digits = raw.tree(DIGITS_IMAGE)
    if digits is not None:
        _insert(catalogue, "damage_digits", read_damage_digits(digits))
    for index in INDEXES:
        catalogue.execute(index)
    catalogue.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    catalogue.commit()


def _insert(catalogue: sqlite3.Connection, table: str, rows: list[Row]) -> None:
    if not rows:
        return
    marks = ", ".join("?" * len(rows[0]))
    try:
        catalogue.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    except sqlite3.IntegrityError as error:
        raise CatalogueError(f"two rows of {table} share a key: {error}") from error


@dataclass(slots=True)
class _Strings:
    """
    The `strings` rows, and the names they give, by ID.

    :ivar maps: Each map's name and street.
    :ivar mobs: Each mob's name.
    :ivar skills: Each skill's name and description.
    """

    rows: list[Row] = field(default_factory=list[Row])
    maps: dict[int, tuple[str | None, str | None]] = field(
        default_factory=dict[int, tuple[str | None, str | None]]
    )
    mobs: dict[int, str | None] = field(default_factory=dict[int, str | None])
    skills: dict[int, tuple[str | None, str | None]] = field(
        default_factory=dict[int, tuple[str | None, str | None]]
    )


def _strings(raw: _Raw) -> _Strings:
    found = _Strings()
    maps = raw.tree("String/Map.img")
    if maps is not None:
        for _, region in maps.expect("property").children():
            for key, entry in region.expect("property").children():
                map_id = _string_id(entry, key)
                if map_id in found.maps:
                    raise entry.error(f"map {map_id} is named twice")
                entry.expect("property")
                name = entry.optional_text("mapName")
                found.maps[map_id] = (name, entry.optional_text("streetName"))
                found.rows.append(("map", map_id, name, entry.optional_text("mapDesc")))
    for kind, path in STRING_KINDS.items():
        tree = raw.tree(path)
        if tree is None:
            continue
        for key, entry in tree.expect("property").children():
            entry.expect("property")
            if kind == "skill" and entry.get("bookName") is not None:
                continue
            string_id = _string_id(entry, key)
            name = entry.optional_text("name")
            description = entry.optional_text("desc") if kind == "skill" else None
            found.rows.append((kind, string_id, name, description))
            if kind == "mob":
                found.mobs[string_id] = name
            elif kind == "skill":
                found.skills[string_id] = (name, description)
    return found


def _string_id(entry: Tree, key: str) -> int:
    if not key.isdigit():
        raise entry.error("an entry whose name isn't an ID")
    return int(key)


def _physics(raw: _Raw) -> list[Row]:
    found = raw.tree("Map/Physics.img")
    if found is None:
        return []
    root = found.expect("property")
    rows: list[Row] = []
    for key, _ in root.children():
        rows.append((key, root.number(key)))
    return rows
