"""
`Catalogue`: one extraction's catalogue, opened for lookups.

    cat = Catalogue.latest()               # or Catalogue.open(build_id)
    cat.map("Henesys")      -> MapData     # or cat.map(map_id)
    cat.map_layers("Henesys") -> tuple[MapLayer, ...]
    cat.search("henes")     -> list[Ref]
    cat.physics()           -> dict[str, float]

**Names first, IDs accepted.** A lookup takes a name or an ID: an `int`, or a
string of digits. A name matches whole and case-insensitively, and a map's
also matches as `street: map name`, since many maps share a name. A name that
matches several raises `LookupError` listing each with its ID, and one that
matches nothing raises `LookupError` listing the closest names
(`difflib.get_close_matches`). Nothing is picked silently.

**Opening rebuilds an outdated catalogue.** When the manifest's catalogue
schema version isn't `SCHEMA_VERSION`, or the extraction has no catalogue, it
is rebuilt from the raw layer before it's opened, and the manifest updated.
The client isn't needed for that.

A catalogue holds its file open until `close`; use it as a context manager.
"""

import difflib
import sqlite3
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from game_data.config import STORE
from game_data.extraction import ExtractionError, Manifest, Store

from .build import build as build_from_raw
from .model import (
    Background,
    Bounds,
    Foothold,
    LayerFrame,
    MapData,
    MapLayer,
    Minimap,
    Portal,
    Ref,
    Rope,
    Spawn,
)
from .schema import CATALOGUE, SCHEMA_VERSION
from .trees import CatalogueError

CLOSEST: Final = 5

type _Value = int | float | str | None


class Catalogue:
    """
    One extraction's catalogue. Open one with `latest` or `open`.

    :ivar build: The extraction's build id.
    """

    def __init__(self, build: str, database: sqlite3.Connection) -> None:
        self.build = build
        self._db = database

    @classmethod
    def latest(cls, root: Path = STORE) -> Catalogue:
        """
        The latest extraction's catalogue.

        :raises CatalogueError: The store has no extraction.
        """
        manifest = Store(root).latest()
        if manifest is None:
            raise CatalogueError(
                f"{root} has no extraction; run `python -m game_data extract`"
            )
        return cls.open(manifest.build, root)

    @classmethod
    def open(cls, build: str, root: Path = STORE) -> Catalogue:
        """
        The catalogue of the extraction of `build`, rebuilt first if outdated.

        :raises CatalogueError: The store has no such extraction, or its raw
            layer isn't as expected.
        """
        folder = Store(root).extraction(build)
        try:
            manifest = Manifest.read(folder)
        except ExtractionError as error:
            raise CatalogueError(f"{root} has no extraction {build}") from error
        file = folder / CATALOGUE
        if manifest.catalogue_schema_version != SCHEMA_VERSION or not file.is_file():
            build_from_raw(folder)
            replace(manifest, catalogue_schema_version=SCHEMA_VERSION).write(folder)
        database = sqlite3.connect(f"{file.resolve().as_uri()}?mode=ro", uri=True)
        return cls(build, database)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()

    def map(self, name_or_id: str | int) -> MapData:
        """
        A map, by name or ID.

        :raises LookupError: Nothing has that ID; or the name matches several
            maps, or none.
        """
        map_id = self._map_id(name_or_id)
        row = self._one("SELECT * FROM maps WHERE id = ?", map_id)
        (_, name, street, left, top, right, bottom, derived) = row[:8]
        center_x, center_y, mag, width, height = row[8:13]
        town, swim, fly, field_limit, bgm, return_map = row[13:]
        minimap = None
        if mag is not None:
            minimap = Minimap(
                _int(center_x), _int(center_y), _int(mag), _int(width), _int(height)
            )
        return MapData(
            id=map_id,
            name=_text(name),
            street=_text(street),
            vr=Bounds(_int(left), _int(top), _int(right), _int(bottom)),
            vr_derived=bool(derived),
            minimap=minimap,
            town=bool(town),
            swim=bool(swim),
            fly=bool(fly),
            field_limit=_int(field_limit),
            bgm=_text(bgm),
            return_map=_optional_int(return_map),
            footholds=tuple(
                Foothold(
                    _str(source),
                    _optional_int(layer),
                    _optional_int(group),
                    _int(id_),
                    _int(x1),
                    _int(y1),
                    _int(x2),
                    _int(y2),
                    _optional_int(prev),
                    _optional_int(next_),
                )
                for (
                    _,
                    source,
                    layer,
                    group,
                    id_,
                    x1,
                    y1,
                    x2,
                    y2,
                    prev,
                    next_,
                ) in self._all(
                    "SELECT * FROM footholds WHERE map = ? ORDER BY rowid", map_id
                )
            ),
            ropes=tuple(
                Rope(
                    _str(source),
                    _int(id_),
                    _int(x),
                    _int(y1),
                    _int(y2),
                    _optional_bool(ladder),
                    _optional_bool(uf),
                    _optional_int(page),
                )
                for (_, source, id_, x, y1, y2, ladder, uf, page) in self._all(
                    "SELECT * FROM ropes WHERE map = ? ORDER BY rowid", map_id
                )
            ),
            portals=tuple(
                Portal(
                    _str(name),
                    _int(type_),
                    _int(x),
                    _int(y),
                    _optional_int(target_map),
                    _text(target_portal),
                )
                for (_, name, type_, x, y, target_map, target_portal) in self._all(
                    "SELECT * FROM portals WHERE map = ? ORDER BY rowid", map_id
                )
            ),
            spawns=tuple(
                Spawn(
                    _str(kind),
                    _int(id_),
                    _text(spawn_name),
                    _int(x),
                    _int(cy),
                    _int(foothold),
                    _int(rx0),
                    _int(rx1),
                    _optional_int(respawn),
                    bool(flip),
                    bool(hidden),
                )
                for (
                    kind,
                    id_,
                    spawn_name,
                    x,
                    cy,
                    foothold,
                    rx0,
                    rx1,
                    respawn,
                    flip,
                    hidden,
                ) in self._all(
                    "SELECT spawns.kind, spawns.id, strings.name, x, cy, foothold, "
                    "rx0, rx1, respawn_time, flip, hidden FROM spawns "
                    "LEFT JOIN strings ON strings.kind = spawns.kind "
                    "AND strings.id = spawns.id "
                    "WHERE map = ? ORDER BY spawns.rowid",
                    map_id,
                )
            ),
        )

    def map_layers(self, name_or_id: str | int) -> tuple[MapLayer, ...]:
        """
        A map's tiles, objects and backgrounds, each with its frames, in the
        map's order.

        :raises LookupError: As `map` does.
        """
        map_id = self._map_id(name_or_id)
        frames: dict[int, list[LayerFrame]] = {}
        for item, frame, image, origin_x, origin_y, delay in self._all(
            "SELECT layer_frames.* FROM layer_frames JOIN map_layers USING (item) "
            "WHERE map = ? ORDER BY item, frame",
            map_id,
        ):
            frames.setdefault(_int(item), []).append(
                LayerFrame(
                    _int(frame),
                    _text(image),
                    _int(origin_x),
                    _int(origin_y),
                    _optional_int(delay),
                )
            )
        layers: list[MapLayer] = []
        for row in self._all(
            "SELECT * FROM map_layers WHERE map = ? ORDER BY item", map_id
        ):
            item, _, kind, layer, z, zm, x, y, flip = row[:9]
            asset = row[12]
            type_, rx, ry, cx, cy, a, front = row[13:]
            background = None
            if kind == "back":
                background = Background(
                    _int(type_),
                    _int(rx),
                    _int(ry),
                    _int(cx),
                    _int(cy),
                    _int(a),
                    bool(front),
                )
            layers.append(
                MapLayer(
                    kind=_str(kind),
                    layer=_optional_int(layer),
                    z=_int(z),
                    zm=_optional_int(zm),
                    x=_int(x),
                    y=_int(y),
                    flip=bool(flip),
                    asset=_text(asset),
                    frames=tuple(frames.get(_int(item), [])),
                    background=background,
                )
            )
        return tuple(layers)

    def search(self, text: str) -> list[Ref]:
        """
        Every map whose name, or `street: map name`, contains `text`, case
        aside; and the map whose ID it is, if it's one. By ID.
        """
        wanted = text.strip().casefold()
        found: list[Ref] = []
        for map_id, name, street in self._names():
            full = _full_name(name, street)
            if (full is not None and wanted in full.casefold()) or (
                wanted.isdigit() and int(wanted) == map_id
            ):
                found.append(Ref("map", map_id, full))
        return found

    def physics(self) -> dict[str, float]:
        """`Map/Physics.img`'s values, by key."""
        return {
            _str(key): float(_int_or_float(value))
            for key, value in self._all("SELECT key, value FROM physics ORDER BY key")
        }

    def _map_id(self, name_or_id: str | int) -> int:
        if isinstance(name_or_id, int) or name_or_id.strip().isdigit():
            map_id = int(name_or_id)
            if not self._all("SELECT 1 FROM maps WHERE id = ?", map_id):
                raise LookupError(f"no map has the ID {map_id}")
            return map_id
        wanted = name_or_id.strip().casefold()
        names = self._names()
        matches = [
            (map_id, _full_name(name, street))
            for map_id, name, street in names
            if name is not None
            and wanted in (name.casefold(), (_full_name(name, street) or "").casefold())
        ]
        if len(matches) == 1:
            return matches[0][0]
        if matches:
            listed = ", ".join(f"{full} ({map_id})" for map_id, full in matches)
            raise LookupError(
                f"{name_or_id!r} names {len(matches)} maps: {listed}. "
                "Ask for one by `street: map name` or by ID"
            )
        candidates: dict[str, str] = {}
        for _, name, street in names:
            for candidate in (name, _full_name(name, street)):
                if candidate is not None:
                    candidates.setdefault(candidate.casefold(), candidate)
        closest = difflib.get_close_matches(wanted, list(candidates), n=CLOSEST)
        if not closest:
            raise LookupError(f"no map is named {name_or_id!r}")
        listed = ", ".join(candidates[key] for key in closest)
        raise LookupError(f"no map is named {name_or_id!r}; the closest are: {listed}")

    def _names(self) -> list[tuple[int, str | None, str | None]]:
        return [
            (_int(map_id), _text(name), _text(street))
            for map_id, name, street in self._all(
                "SELECT id, name, street FROM maps ORDER BY id"
            )
        ]

    def _one(self, sql: str, *parameters: _Value) -> Sequence[_Value]:
        row: Sequence[_Value] | None = self._db.execute(sql, parameters).fetchone()
        if row is None:
            raise LookupError(f"nothing matches {parameters}")
        return row

    def _all(self, sql: str, *parameters: _Value) -> list[Sequence[_Value]]:
        return self._db.execute(sql, parameters).fetchall()


def _full_name(name: str | None, street: str | None) -> str | None:
    if name is None:
        return None
    return f"{street}: {name}" if street else name


def _int(value: _Value) -> int:
    if not isinstance(value, int):
        raise CatalogueError(f"the catalogue holds {value!r} where an integer goes")
    return value


def _optional_int(value: _Value) -> int | None:
    return None if value is None else _int(value)


def _optional_bool(value: _Value) -> bool | None:
    return None if value is None else bool(value)


def _int_or_float(value: _Value) -> int | float:
    if not isinstance(value, (int, float)):
        raise CatalogueError(f"the catalogue holds {value!r} where a number goes")
    return value


def _str(value: _Value) -> str:
    if not isinstance(value, str):
        raise CatalogueError(f"the catalogue holds {value!r} where text goes")
    return value


def _text(value: _Value) -> str | None:
    return None if value is None else _str(value)
