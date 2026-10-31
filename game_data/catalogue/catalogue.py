"""
`Catalogue`: one extraction's catalogue, opened for lookups.

    cat = Catalogue.latest()               # or Catalogue.open(build_id)
    cat.map("Henesys")      -> MapData     # or cat.map(map_id)
    cat.map_layers("Henesys") -> tuple[MapLayer, ...]
    cat.mob("Snail")        -> MobData
    cat.skill("Magic Claw").level(20) -> SkillLevel
    cat.action_duration("swingO1")    -> int, in milliseconds
    cat.skill_duration("Magic Claw")  -> int, in milliseconds
    cat.maps_spawning("Snail")        -> list[MapRef]
    cat.search("henes")     -> list[Ref]
    cat.ids("mob")          -> list[int]
    cat.physics()           -> dict[str, float]
    cat.item_icons()        -> tuple[ItemIcon, ...]
    cat.meso_frames()       -> tuple[MesoFrame, ...]
    cat.damage_digits()     -> tuple[DamageDigit, ...]

**Names first, IDs accepted.** A lookup takes a name or an ID: an `int`, or a
string of digits. A name matches whole and case-insensitively, and a map's
also matches as `street: map name`, since many maps share a name. A name that
matches several raises `LookupError` listing each with its ID, and one that
matches nothing raises `LookupError` listing the closest names
(`difflib.get_close_matches`). Nothing is picked silently. Maps, mobs and
skills are each looked up among their own kind.

**Opening rebuilds an outdated catalogue.** When the manifest's catalogue
schema version isn't `SCHEMA_VERSION`, or the extraction has no catalogue, it
is rebuilt from the raw layer before it's opened, and the manifest updated.
The client isn't needed for that.

A catalogue holds its file open until `close`; use it as a context manager.
"""

import difflib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from game_data.config import STORE
from game_data.extraction import ExtractionError, Json, Manifest, Store

from .build import build as build_from_raw
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

CLOSEST: Final = 5

# What a lookup can name, and the table each kind is in.
KINDS: Final = {"map": "maps", "mob": "mobs", "skill": "skills"}

type _Value = int | float | str | None


class Catalogue:
    """
    One extraction's catalogue. Open one with `latest` or `open`.

    :ivar build: The extraction's build id.
    :ivar store: The store it's in, whose image store holds its images.
    """

    def __init__(self, build: str, database: sqlite3.Connection, store: Store) -> None:
        self.build = build
        self.store = store
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
        return cls(build, database, Store(root))

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
        map_id = self._id("map", name_or_id)
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
        map_id = self._id("map", name_or_id)
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

    def mob(self, name_or_id: str | int) -> MobData:
        """
        A mob, by name or ID, with every frame of every action. A mob that
        shares another's sprites has that mob's frames.

        :raises LookupError: Nothing has that ID; or the name matches several
            mobs, or none.
        """
        mob_id = self._id("mob", name_or_id)
        row = self._one("SELECT * FROM mobs WHERE id = ?", mob_id)
        _, name, link, level, max_hp, max_mp, speed, fly_speed, exp = row[:9]
        pa, ma, pd, md, acc, eva, pushed = row[9:16]
        body_attack, boss, undead, first_attack, elem_attr = row[16:]
        frames: list[MobFrame] = []
        for frame_row in self._all(
            "SELECT * FROM mob_frames WHERE mob = ? ORDER BY rowid", mob_id
        ):
            _, action, frame, image, origin_x, origin_y = frame_row[:6]
            frames.append(
                MobFrame(
                    _str(action),
                    _int(frame),
                    _text(image),
                    _int(origin_x),
                    _int(origin_y),
                    *(_optional_int(value) for value in frame_row[6:]),
                )
            )
        return MobData(
            id=mob_id,
            name=_text(name),
            link=_optional_int(link),
            level=_int(level),
            max_hp=_int(max_hp),
            max_mp=_int(max_mp),
            speed=_optional_int(speed),
            fly_speed=_optional_int(fly_speed),
            exp=_optional_int(exp),
            pa_damage=_int(pa),
            ma_damage=_int(ma),
            pd_damage=_int(pd),
            md_damage=_int(md),
            acc=_int(acc),
            eva=_int(eva),
            pushed=_int(pushed),
            body_attack=bool(body_attack),
            boss=bool(boss),
            undead=bool(undead),
            first_attack=bool(first_attack),
            elem_attr=_text(elem_attr),
            frames=tuple(frames),
        )

    def skill(self, name_or_id: str | int) -> SkillData:
        """
        A skill, by name or ID, with every level; `skill(...).level(n)` is
        one of them.

        :raises LookupError: Nothing has that ID; or the name matches several
            skills, or none.
        """
        skill_id = self._id("skill", name_or_id)
        row = self._one("SELECT * FROM skills WHERE id = ?", skill_id)
        _, job, name, description, type_, max_level, actions_json, icon = row
        actions = _json_strings(actions_json)
        levels: list[SkillLevel] = []
        for level_row in self._all(
            "SELECT * FROM skill_levels WHERE skill = ? ORDER BY level", skill_id
        ):
            mp_con, time, lt_x, lt_y, rb_x, rb_y = level_row[2:8]
            mob_count, attack_count, range_, cooltime = level_row[8:12]
            levels.append(
                SkillLevel(
                    skill=skill_id,
                    level=_int(level_row[1]),
                    actions=actions,
                    mp_con=_optional_int(mp_con),
                    time=_optional_int(time),
                    lt_x=_optional_int(lt_x),
                    lt_y=_optional_int(lt_y),
                    rb_x=_optional_int(rb_x),
                    rb_y=_optional_int(rb_y),
                    mob_count=_optional_int(mob_count),
                    attack_count=_optional_int(attack_count),
                    range=_optional_int(range_),
                    cooltime=_optional_int(cooltime),
                    other=_json_object(level_row[12]),
                )
            )
        return SkillData(
            id=skill_id,
            job=_int(job),
            name=_text(name),
            description=_text(description),
            type=_optional_int(type_),
            max_level=_int(max_level),
            actions=actions,
            icon=_text(icon),
            levels=tuple(levels),
        )

    def action_duration(self, action: str) -> int:
        """
        How long a character action takes, in milliseconds: its frames'
        delays added up, each by its magnitude.

        :raises LookupError: The character has no such action, or none of its
            frames says how long it lasts.
        """
        found = self._all(
            "SELECT duration FROM actions WHERE action = ? LIMIT 1", action
        )
        if not found:
            names = [_str(name) for (name,) in self._all("SELECT action FROM actions")]
            closest = difflib.get_close_matches(action, sorted(set(names)), n=CLOSEST)
            hint = f"; the closest are: {', '.join(closest)}" if closest else ""
            raise LookupError(f"the character has no action {action!r}{hint}")
        duration = found[0][0]
        if duration is None:
            raise LookupError(f"none of the action {action!r}'s frames has a delay")
        return _int(duration)

    def skill_duration(self, name_or_id: str | int) -> int:
        """
        How long a skill's first action takes, in milliseconds.

        :raises LookupError: As `skill` does; the skill plays no action; or as
            `action_duration` does.
        """
        skill = self.skill(name_or_id)
        if not skill.actions:
            raise LookupError(f"{skill.name or skill.id} plays no action")
        return self.action_duration(skill.actions[0])

    def maps_spawning(self, mob: str | int) -> list[MapRef]:
        """
        Every map a mob, by name or ID, is placed on, by ID.

        :raises LookupError: As `mob` does.
        """
        mob_id = self._id("mob", mob)
        return [
            MapRef(_int(map_id), _full_name(_text(name), _text(street)), _int(count))
            for map_id, name, street, count in self._all(
                "SELECT maps.id, maps.name, maps.street, count(*) FROM spawns "
                "JOIN maps ON maps.id = spawns.map "
                "WHERE spawns.kind = 'mob' AND spawns.id = ? "
                "GROUP BY maps.id ORDER BY maps.id",
                mob_id,
            )
        ]

    def search(self, text: str, kind: str | None = None) -> list[Ref]:
        """
        Every map, mob and skill whose name contains `text`, case aside, and
        whatever has it as its ID: maps, then mobs, then skills, each by ID.
        A map's name is its `street: map name`.

        :param kind: Only maps, mobs or skills: `map`, `mob` or `skill`.
        """
        wanted = text.strip().casefold()
        found: list[Ref] = []
        for each in KINDS if kind is None else (kind,):
            for found_id, full, _ in self._named(each):
                if (full is not None and wanted in full.casefold()) or (
                    wanted.isdigit() and int(wanted) == found_id
                ):
                    found.append(Ref(each, found_id, full))
        return found

    def ids(self, kind: str) -> list[int]:
        """
        The ID of every map, mob or skill (`kind`: `map`, `mob` or `skill`),
        ascending.

        :raises LookupError: `kind` is none of those.
        """
        if kind not in KINDS:
            raise LookupError(f"no kind {kind!r}; the kinds are {', '.join(KINDS)}")
        return [
            _int(found_id)
            for (found_id,) in self._all(f"SELECT id FROM {KINDS[kind]} ORDER BY id")
        ]

    def physics(self) -> dict[str, float]:
        """`Map/Physics.img`'s values, by key."""
        return {
            _str(key): float(_int_or_float(value))
            for key, value in self._all("SELECT key, value FROM physics ORDER BY key")
        }

    def item_icons(self) -> tuple[ItemIcon, ...]:
        """Every item's icon, by item ID."""
        return tuple(
            ItemIcon(_int(item), _str(category), _text(image), _int(x), _int(y))
            for item, category, image, x, y in self._all(
                "SELECT * FROM item_icons ORDER BY item"
            )
        )

    def meso_frames(self) -> tuple[MesoFrame, ...]:
        """Every frame of every meso sprite, by sprite and then frame."""
        return tuple(
            MesoFrame(_int(meso), _int(frame), _text(image), _int(x), _int(y))
            for meso, frame, image, x, y in self._all(
                "SELECT * FROM meso_frames ORDER BY meso, frame"
            )
        )

    def damage_digits(self) -> tuple[DamageDigit, ...]:
        """Every digit of every damage digit set, by set and then digit."""
        return tuple(
            DamageDigit(_str(digit_set), _int(digit), _text(image), _int(x), _int(y))
            for digit_set, digit, image, x, y in self._all(
                "SELECT * FROM damage_digits ORDER BY digit_set, digit"
            )
        )

    def _id(self, kind: str, name_or_id: str | int) -> int:
        """The ID of the map, mob or skill (`kind`) a name or an ID names."""
        if isinstance(name_or_id, int) or name_or_id.strip().isdigit():
            found_id = int(name_or_id)
            if not self._all(f"SELECT 1 FROM {KINDS[kind]} WHERE id = ?", found_id):
                raise LookupError(f"no {kind} has the ID {found_id}")
            return found_id
        wanted = name_or_id.strip().casefold()
        named = self._named(kind)
        matches = [
            (found_id, full)
            for found_id, full, accepted in named
            if wanted in (name.casefold() for name in accepted)
        ]
        if len(matches) == 1:
            return matches[0][0]
        if matches:
            listed = ", ".join(f"{full} ({found_id})" for found_id, full in matches)
            by = "`street: map name` or by ID" if kind == "map" else "ID"
            raise LookupError(
                f"{name_or_id!r} names {len(matches)} {kind}s: {listed}. "
                f"Ask for one by {by}"
            )
        candidates: dict[str, str] = {}
        for _, _, accepted in named:
            for candidate in accepted:
                candidates.setdefault(candidate.casefold(), candidate)
        closest = difflib.get_close_matches(wanted, list(candidates), n=CLOSEST)
        if not closest:
            raise LookupError(f"no {kind} is named {name_or_id!r}")
        listed = ", ".join(candidates[key] for key in closest)
        raise LookupError(
            f"no {kind} is named {name_or_id!r}; the closest are: {listed}"
        )

    def _named(self, kind: str) -> list[tuple[int, str | None, tuple[str, ...]]]:
        """
        Every map, mob or skill (`kind`), by ID: its ID, its fullest name, and
        the names a lookup accepts for it.
        """
        if kind != "map":
            return [
                (_int(found_id), _text(name), () if name is None else (_str(name),))
                for found_id, name in self._all(
                    f"SELECT id, name FROM {KINDS[kind]} ORDER BY id"
                )
            ]
        found: list[tuple[int, str | None, tuple[str, ...]]] = []
        for map_id, name, street in self._all(
            "SELECT id, name, street FROM maps ORDER BY id"
        ):
            full = _full_name(_text(name), _text(street))
            accepted = () if full is None else (_str(name), full)
            found.append((_int(map_id), full, accepted))
        return found

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


def _json_strings(value: _Value) -> tuple[str, ...]:
    found: Json = json.loads(_str(value))
    if not isinstance(found, list) or not all(isinstance(x, str) for x in found):
        raise CatalogueError(f"the catalogue holds {value!r} where a list of text goes")
    return tuple(x for x in found if isinstance(x, str))


def _json_object(value: _Value) -> dict[str, Json]:
    found: Json = json.loads(_str(value))
    if not isinstance(found, dict):
        raise CatalogueError(f"the catalogue holds {value!r} where a JSON object goes")
    return found
