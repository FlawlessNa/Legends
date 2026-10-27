"""
The typed summary: what changed between two catalogues, by name.

Maps, mobs and skills are compared by ID. One only the new catalogue has is
**added**, and one only the old has is **removed**. Of those both have:

- a **map** is changed when its geometry is: its VR bounds, footholds, ropes,
  portals or spawns. A map's own footholds and ropes are matched by ID,
  portals, spawns and the segments drawn on objects and tiles by what they are,
  since the client gives them no ID (`anonymous`). A
  portal or spawn that is gone while another of the same name (or the same mob
  or NPC) appeared is one that changed.
- a **mob** is changed when a stat is: any value of `MobData` but its name,
  ID and frames.
- a **skill** is changed when a level is added or removed, or a value of a
  level is: `mp_con`, `time`, the area, and every field of `other`.

Names come from the catalogues, which read them from the client's `strings`; a
thing the client names nowhere is told by its ID.
"""

from collections import Counter
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, fields, replace
from typing import Final

from game_data.catalogue import (
    Catalogue,
    Foothold,
    MapData,
    MobData,
    Portal,
    Ref,
    Rope,
    SkillData,
    SkillLevel,
    Spawn,
)
from game_data.extraction import Json

from .diff import Kind

# What `MobData` holds that isn't a stat.
_NOT_STATS: Final = frozenset({"id", "name", "frames"})
# What `SkillLevel` holds that isn't a value of the level on its own.
_NOT_LEVEL_VALUES: Final = frozenset({"skill", "level", "other"})

type Value = Json | bool | tuple[str, ...]


def label(id_: int, name: str | None) -> str:
    """A thing told by its name, with its ID; by its ID alone if unnamed."""
    return str(id_) if name is None else f"{name} ({id_})"


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One value that differs: its name, and what it was and became."""

    field: str
    old: Value
    new: Value


@dataclass(frozen=True, slots=True)
class GeometryChange:
    """
    One piece of a map's geometry that differs.

    :ivar part: `vr`, `foothold`, `rope`, `portal` or `spawn`.
    :ivar kind: `added`, `removed` or `changed`.
    :ivar subject: Which one, such as `map foothold 2` or `portal sp`.
    :ivar old: What it was; `None` when added.
    :ivar new: What it became; `None` when removed.
    """

    part: str
    kind: Kind
    subject: str
    old: str | None
    new: str | None


@dataclass(frozen=True, slots=True)
class MapChange:
    """
    A map whose geometry differs.

    :ivar name: `street: map name`; `None` when the client names it nowhere.
    :ivar before: The map in the old catalogue, for drawing.
    :ivar after: The map in the new.
    """

    id: int
    name: str | None
    changes: tuple[GeometryChange, ...]
    before: MapData
    after: MapData


@dataclass(frozen=True, slots=True)
class MobChange:
    """
    A mob whose stats differ.

    :ivar stats: The stats that differ.
    :ivar before: Its sprite in the old extraction: the image of its first
        `stand` frame, or of its first frame. `None` if it has no image.
    :ivar after: Likewise in the new.
    """

    id: int
    name: str | None
    stats: tuple[FieldChange, ...]
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class LevelChange:
    """A level of a skill whose values differ."""

    level: int
    values: tuple[FieldChange, ...]


@dataclass(frozen=True, slots=True)
class SkillChange:
    """
    A skill whose levels differ.

    :ivar levels_added: Levels only the new catalogue has.
    :ivar levels_removed: Levels only the old has.
    :ivar levels: Levels both have whose values differ.
    """

    id: int
    name: str | None
    levels_added: tuple[int, ...]
    levels_removed: tuple[int, ...]
    levels: tuple[LevelChange, ...]


@dataclass(frozen=True, slots=True)
class Summary:
    """Everything that differs, each list by ID."""

    maps_added: tuple[Ref, ...]
    maps_removed: tuple[Ref, ...]
    maps_changed: tuple[MapChange, ...]
    mobs_added: tuple[Ref, ...]
    mobs_removed: tuple[Ref, ...]
    mobs_changed: tuple[MobChange, ...]
    skills_added: tuple[Ref, ...]
    skills_removed: tuple[Ref, ...]
    skills_changed: tuple[SkillChange, ...]


def summarize(old: Catalogue, new: Catalogue) -> Summary:
    """What differs between two catalogues."""
    maps_added, maps_removed, maps_common = _split(old, new, "map")
    mobs_added, mobs_removed, mobs_common = _split(old, new, "mob")
    skills_added, skills_removed, skills_common = _split(old, new, "skill")
    return Summary(
        maps_added=maps_added,
        maps_removed=maps_removed,
        maps_changed=tuple(
            change
            for map_id in maps_common
            if (change := _map_change(old.map(map_id), new.map(map_id)))
        ),
        mobs_added=mobs_added,
        mobs_removed=mobs_removed,
        mobs_changed=tuple(
            change
            for mob_id in mobs_common
            if (change := _mob_change(old.mob(mob_id), new.mob(mob_id)))
        ),
        skills_added=skills_added,
        skills_removed=skills_removed,
        skills_changed=tuple(
            change
            for skill_id in skills_common
            if (change := _skill_change(old.skill(skill_id), new.skill(skill_id)))
        ),
    )


def _split(
    old: Catalogue, new: Catalogue, kind: str
) -> tuple[tuple[Ref, ...], tuple[Ref, ...], list[int]]:
    """What `kind` the new catalogue added, removed, and both have, by ID."""
    before = set(old.ids(kind))
    after = set(new.ids(kind))
    added = tuple(_refs(new, kind, after - before))
    removed = tuple(_refs(old, kind, before - after))
    return added, removed, sorted(before & after)


def _refs(catalogue: Catalogue, kind: str, ids: set[int]) -> list[Ref]:
    if not ids:
        return []
    named = {ref.id: ref.name for ref in catalogue.search("", kind)}
    return [Ref(kind, found, named.get(found)) for found in sorted(ids)]


# --- maps --------------------------------------------------------------------


def _map_change(old: MapData, new: MapData) -> MapChange | None:
    changes: list[GeometryChange] = []
    if old.vr != new.vr or old.vr_derived != new.vr_derived:
        changes.append(GeometryChange("vr", "changed", "VR bounds", _vr(old), _vr(new)))
    for source in ("map", "object", "tile"):
        changes += _segments(
            "foothold",
            [f for f in old.footholds if f.source == source],
            [f for f in new.footholds if f.source == source],
            text=_foothold,
        )
    for source in ("map", "object"):
        changes += _segments(
            "rope",
            [r for r in old.ropes if r.source == source],
            [r for r in new.ropes if r.source == source],
            text=_rope,
        )
    changes += _unkeyed(
        "portal",
        old.portals,
        new.portals,
        key=lambda p: p.name,
        subject=lambda p: f"portal {p.name}",
        text=_portal,
    )
    changes += _unkeyed(
        "spawn",
        old.spawns,
        new.spawns,
        key=lambda s: (s.kind, s.id),
        subject=lambda s: f"{s.kind} {label(s.id, s.name)}",
        text=_spawn,
    )
    if not changes:
        return None
    name = None
    if new.name is not None:
        name = f"{new.street}: {new.name}" if new.street else new.name
    return MapChange(new.id, name, tuple(changes), old, new)


def anonymous[T: (Foothold, Rope)](segment: T) -> T:
    """
    A segment as it can be compared across extractions: a map's own keeps its
    ID, which the client gives it, and one drawn on an object or tile has its
    running number zeroed, since that is only its place in the order the layers
    were read, and shifts when any earlier one is added or removed.
    """
    return segment if segment.source == "map" else replace(segment, id=0)


def _segments[T: (Foothold, Rope)](
    part: str, old: list[T], new: list[T], *, text: Callable[[T], str]
) -> list[GeometryChange]:
    """
    The footholds or ropes of one `source` that are gone, new or different. The
    map's own are matched by ID. The others have no ID of their own, so they
    are compared by value, as portals and spawns are, and one that is moved is
    one removed and one added.
    """
    if not old and not new:
        return []
    source = (old or new)[0].source
    if source == "map":
        return _keyed(
            part,
            old,
            new,
            key=lambda x: x.id,
            subject=lambda x: f"map {part} {x.id}",
            text=text,
        )
    return _unkeyed(
        part,
        [anonymous(x) for x in old],
        [anonymous(x) for x in new],
        key=lambda x: x,
        subject=lambda x: f"{source} {part}",
        text=text,
    )


def _vr(map_data: MapData) -> str:
    vr = map_data.vr
    text = f"left {vr.left}, top {vr.top}, right {vr.right}, bottom {vr.bottom}"
    return f"{text} (from the footholds)" if map_data.vr_derived else text


def _foothold(f: Foothold) -> str:
    text = f"({f.x1}, {f.y1}) to ({f.x2}, {f.y2})"
    if f.prev is not None or f.next is not None:
        text += f", prev {f.prev}, next {f.next}"
    if f.layer is not None or f.group is not None:
        text += f", layer {f.layer}, group {f.group}"
    return text


def _rope(r: Rope) -> str:
    text = f"x {r.x}, y {r.y1} to {r.y2}"
    if r.ladder is not None:
        text += ", ladder" if r.ladder else ", rope"
    if r.usable_from_foothold is not None:
        text += f", usable from foothold {r.usable_from_foothold}"
    if r.page is not None:
        text += f", page {r.page}"
    return text


def _portal(p: Portal) -> str:
    target = "" if p.target_map is None else f" to map {p.target_map}"
    if p.target_portal is not None:
        target += f" portal {p.target_portal}"
    return f"type {p.type} at ({p.x}, {p.y}){target}"


def _spawn(s: Spawn) -> str:
    text = f"at ({s.x}, {s.cy}) on foothold {s.foothold}, range {s.rx0} to {s.rx1}"
    if s.respawn_time is not None:
        text += f", respawn {s.respawn_time}"
    if s.flip:
        text += ", flipped"
    if s.hidden:
        text += ", hidden"
    return text


def _keyed[T](
    part: str,
    old: Sequence[T],
    new: Sequence[T],
    *,
    key: Callable[[T], Hashable],
    subject: Callable[[T], str],
    text: Callable[[T], str],
) -> list[GeometryChange]:
    """The pieces with an ID (`key`) that are gone, new, or different."""
    before = {key(item): item for item in old}
    after = {key(item): item for item in new}
    changes: list[GeometryChange] = []
    for name, item in before.items():
        if name not in after:
            changes.append(
                GeometryChange(part, "removed", subject(item), text(item), None)
            )
        elif after[name] != item:
            changes.append(
                GeometryChange(
                    part, "changed", subject(item), text(item), text(after[name])
                )
            )
    for name, item in after.items():
        if name not in before:
            changes.append(
                GeometryChange(part, "added", subject(item), None, text(item))
            )
    return changes


def _unkeyed[T: Hashable](
    part: str,
    old: Sequence[T],
    new: Sequence[T],
    *,
    key: Callable[[T], Hashable],
    subject: Callable[[T], str],
    text: Callable[[T], str],
) -> list[GeometryChange]:
    """
    The pieces without an ID that are gone, new or, once paired by `key`, a
    different piece of the same kind.
    """
    gone = _left_over(old, new)
    came = _left_over(new, old)
    changes: list[GeometryChange] = []
    for item in gone:
        partner = next((c for c in came if key(c) == key(item)), None)
        if partner is None:
            changes.append(
                GeometryChange(part, "removed", subject(item), text(item), None)
            )
        else:
            came.remove(partner)
            changes.append(
                GeometryChange(
                    part, "changed", subject(item), text(item), text(partner)
                )
            )
    changes += [
        GeometryChange(part, "added", subject(item), None, text(item)) for item in came
    ]
    return changes


def _left_over[T: Hashable](these: Sequence[T], those: Sequence[T]) -> list[T]:
    """What `these` has that `those` hasn't, counting repeats, in order."""
    available = Counter(those)
    left: list[T] = []
    for item in these:
        if available[item] > 0:
            available[item] -= 1
        else:
            left.append(item)
    return left


# --- mobs --------------------------------------------------------------------


def _mob_change(old: MobData, new: MobData) -> MobChange | None:
    stats: list[FieldChange] = []
    for field in fields(MobData):
        if field.name in _NOT_STATS:
            continue
        before: Value = getattr(old, field.name)
        after: Value = getattr(new, field.name)
        if before != after:
            stats.append(FieldChange(field.name, before, after))
    if not stats:
        return None
    return MobChange(new.id, new.name, tuple(stats), sprite(old), sprite(new))


def sprite(mob: MobData) -> str | None:
    """A mob's first `stand` frame's image, or else its first frame's."""
    drawn = [frame for frame in mob.frames if frame.image is not None]
    chosen = [frame for frame in drawn if frame.action == "stand"] or drawn
    if not chosen:
        return None
    return min(chosen, key=lambda frame: frame.frame).image


# --- skills ------------------------------------------------------------------


def _skill_change(old: SkillData, new: SkillData) -> SkillChange | None:
    before = {level.level: level for level in old.levels}
    after = {level.level: level for level in new.levels}
    changed = tuple(
        LevelChange(number, values)
        for number in sorted(before.keys() & after.keys())
        if (values := _level_values(before[number], after[number]))
    )
    added = tuple(sorted(after.keys() - before.keys()))
    removed = tuple(sorted(before.keys() - after.keys()))
    if not (changed or added or removed):
        return None
    return SkillChange(new.id, new.name, added, removed, changed)


def _level_values(old: SkillLevel, new: SkillLevel) -> tuple[FieldChange, ...]:
    values: list[FieldChange] = []
    for field in fields(SkillLevel):
        if field.name in _NOT_LEVEL_VALUES:
            continue
        before: Value = getattr(old, field.name)
        after: Value = getattr(new, field.name)
        if before != after:
            values.append(FieldChange(field.name, before, after))
    for name in sorted(old.other.keys() | new.other.keys()):
        if old.other.get(name) != new.other.get(name) or (name in old.other) != (
            name in new.other
        ):
            values.append(
                FieldChange(f"other.{name}", old.other.get(name), new.other.get(name))
            )
    return tuple(values)
