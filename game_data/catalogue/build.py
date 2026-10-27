"""
Building an extraction's `catalogue.sqlite` from its `raw.sqlite`, and nothing
else: the client is never read, so a catalogue can be rebuilt wherever the
store is.

It reads:

- `String/Map.img`, `String/Mob.img` and `String/Npc.img` into `strings`.
  `Map.img` groups maps by region, `<region>/<id>/mapName`, `streetName` and
  `mapDesc`; the others are `<id>/name`.
- every map image, `Map/Map/Map<n>/<id>.img`, and the assets it draws from
  (`maps`).
- `Map/Physics.img` into `physics`, one row per value.

An image the client doesn't have, such as `String/Map.img` in a client of only
mobs, leaves its tables empty. One that is there but isn't as expected is an
error naming the image and the node, and builds nothing.

The catalogue is written beside the raw layer under a temporary name, and
renamed over the old one when it's complete.
"""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from game_data.extraction import ImageStore

from .maps import MAP_IMAGE, Assets, MapReader, Row
from .schema import CATALOGUE, INDEXES, SCHEMA_VERSION, TABLES
from .trees import CatalogueError, Tree

RAW = "raw.sqlite"
STRING_KINDS = {"mob": "String/Mob.img", "npc": "String/Npc.img"}


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
        rows = self._connection.execute(
            "SELECT path FROM images WHERE path GLOB 'Map/Map/Map[0-9]/*.img'"
        ).fetchall()
        found: list[tuple[int, str]] = []
        for (path,) in rows:
            match = MAP_IMAGE.fullmatch(path)
            if match:
                found.append((int(match["id"]), path))
        return sorted(found)


def _write(raw: _Raw, catalogue: sqlite3.Connection) -> None:
    catalogue.execute("PRAGMA journal_mode = OFF")
    catalogue.execute("PRAGMA synchronous = OFF")
    for table in TABLES:
        catalogue.execute(table)
    strings, names = _strings(raw)
    _insert(catalogue, "strings", strings)
    reader = MapReader(Assets(raw.tree), names)
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


def _strings(raw: _Raw) -> tuple[list[Row], dict[int, tuple[str | None, str | None]]]:
    """The `strings` rows, and each map's name and street."""
    rows: list[Row] = []
    names: dict[int, tuple[str | None, str | None]] = {}
    maps = raw.tree("String/Map.img")
    if maps is not None:
        for _, region in maps.expect("property").children():
            for key, entry in region.expect("property").children():
                map_id = _string_id(entry, key)
                if map_id in names:
                    raise entry.error(f"map {map_id} is named twice")
                entry.expect("property")
                name = entry.optional_text("mapName")
                names[map_id] = (name, entry.optional_text("streetName"))
                rows.append(("map", map_id, name, entry.optional_text("mapDesc")))
    for kind, path in STRING_KINDS.items():
        found = raw.tree(path)
        if found is None:
            continue
        for key, entry in found.expect("property").children():
            entry.expect("property")
            rows.append(
                (kind, _string_id(entry, key), entry.optional_text("name"), None)
            )
    return rows, names


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
