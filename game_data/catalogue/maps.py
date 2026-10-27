"""
One map's raw tree, and the asset images it draws from, as catalogue rows.

A map's image, `Map/Map/Map<n>/<id>.img`, holds:

- `info`: the VR bounds (`VRLeft`, `VRTop`, `VRRight`, `VRBottom`), the
  flags, `bgm` and `returnMap`. A map without VR bounds gets the extents of its
  own footholds, flagged `vr_derived`.
- `miniMap`: the minimap transform, when the map has one.
- `foothold/<layer>/<group>/<id>`, `ladderRope/<id>`, `portal/<n>` and
  `life/<n>`: footholds, ropes, portals and spawns, one row each.
- `0` ... `7`, the map's layers: each `tile/<n>` and `obj/<n>` is a
  `map_layers` row, and its frames are `layer_frames` rows. A tile is
  `Map/Tile/<tS>.img/<u>/<no>`, `tS` from the layer's `info`. An object is
  `Map/Obj/<oS>.img/<l0>/<l1>/<l2>`, whose numbered children are its frames.
  The footholds and ropes drawn on them are `geometry`'s.
- `back/<n>`: the backgrounds, `Map/Back/<bS>.img/back/<no>`, or
  `.../ani/<no>` for an animated one (`ani` 1). A background with no `bS` is a
  colour with no image: no asset and no frames.

Positions are stored as the map gives them: the renderer applies `origin`.
A value missing from a tree the client always fills is an error; flags the
client leaves out when they're 0 (`town`, `f`, `hide`...) are read as 0.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final

from . import geometry
from .geometry import Climb, Segment
from .trees import Tree

MAP_IMAGE: Final = re.compile(r"Map/Map/Map\d/(?P<id>\d{9})\.img")
NO_MAP: Final = 999999999
LAYERS: Final = range(8)

type Row = tuple[int | float | str | None, ...]

_NO_BACKGROUND: Final[tuple[int | None, ...]] = (None,) * 7


@dataclass(slots=True)
class Rows:
    """The rows read so far, by table, in the order they're inserted."""

    maps: list[Row] = field(default_factory=list[Row])
    footholds: list[Row] = field(default_factory=list[Row])
    ropes: list[Row] = field(default_factory=list[Row])
    portals: list[Row] = field(default_factory=list[Row])
    spawns: list[Row] = field(default_factory=list[Row])
    map_layers: list[Row] = field(default_factory=list[Row])
    layer_frames: list[Row] = field(default_factory=list[Row])


class Assets:
    """
    The asset images maps draw from, each read from the raw layer once.

    :param read: An image's root by its path, or `None` when there is none.
    """

    def __init__(self, read: Callable[[str], Tree | None]) -> None:
        self._read = read
        self._trees: dict[str, Tree | None] = {}

    def node(self, image: str, steps: list[str], user: Tree) -> Tree:
        """
        The node at `steps` in `image`, links followed.

        :param user: The node that names it, which an error names.
        """
        if image not in self._trees:
            self._trees[image] = self._read(image)
        node = self._trees[image]
        if node is None:
            raise user.error(f"it names {image}, which the raw layer doesn't have")
        for step in steps:
            found = node.resolved().get(step)
            if found is None:
                raise user.error(
                    f"it names {image}/{'/'.join(steps)}, which doesn't exist"
                )
            node = found
        return node.resolved()


class MapReader:
    """
    Reads maps into `rows`, numbering their layer items across all maps.

    :param names: Each map's name and street, from `String/Map.img`.
    """

    def __init__(
        self, assets: Assets, names: Mapping[int, tuple[str | None, str | None]]
    ) -> None:
        self._assets = assets
        self._names = names
        self.rows = Rows()
        self._item = 0

    def read(self, map_id: int, tree: Tree) -> None:
        """Reads one map's tree."""
        segments = self._footholds(map_id, tree)
        self._ropes(map_id, tree)
        self._portals(map_id, tree)
        self._spawns(map_id, tree)
        object_segments, tile_segments, climbs = self._layers(map_id, tree)
        self._backgrounds(map_id, tree)
        for source, found in (("object", object_segments), ("tile", tile_segments)):
            self.rows.footholds += [
                (map_id, source, None, None, n, s.x1, s.y1, s.x2, s.y2, None, None)
                for n, s in enumerate(found)
            ]
        self.rows.ropes += [
            (map_id, "object", n, c.x, c.y1, c.y2, None, None, None)
            for n, c in enumerate(climbs)
        ]
        self.rows.maps.append(self._map(map_id, tree, segments))

    def _map(self, map_id: int, tree: Tree, segments: list[Segment]) -> Row:
        info = tree.at("info").expect("property")
        bounds = _vr_bounds(info)
        derived = bounds is None
        if bounds is None:
            if not segments:
                raise info.error("it has no VR bounds, and no footholds to derive them")
            xs = [x for s in segments for x in (s.x1, s.x2)]
            ys = [y for s in segments for y in (s.y1, s.y2)]
            bounds = (min(xs), min(ys), max(xs), max(ys))
        minimap: tuple[int | None, ...] = (None,) * 5
        found = tree.get("miniMap")
        if found is not None:
            mini = found.expect("property")
            minimap = tuple(
                mini.integer(key)
                for key in ("centerX", "centerY", "mag", "width", "height")
            )
        name, street = self._names.get(map_id, (None, None))
        return_map = info.optional_integer("returnMap")
        return (
            map_id,
            name,
            street,
            *bounds,
            int(derived),
            *minimap,
            info.integer_or("town", 0),
            info.integer_or("swim", 0),
            info.integer_or("fly", 0),
            info.integer_or("fieldLimit", 0),
            info.optional_text("bgm"),
            None if return_map == NO_MAP else return_map,
        )

    def _footholds(self, map_id: int, tree: Tree) -> list[Segment]:
        segments: list[Segment] = []
        for layer, groups in _numbered(tree.get("foothold")):
            for group, footholds in _numbered(groups):
                for number, foothold in _numbered(footholds):
                    x1, y1, x2, y2, prev, next_ = (
                        foothold.integer(key)
                        for key in ("x1", "y1", "x2", "y2", "prev", "next")
                    )
                    segments.append(Segment(x1, y1, x2, y2))
                    self.rows.footholds.append(
                        (map_id, "map", layer, group, number, x1, y1, x2, y2)
                        + (prev, next_)
                    )
        return segments

    def _ropes(self, map_id: int, tree: Tree) -> None:
        for number, rope in _numbered(tree.get("ladderRope")):
            self.rows.ropes.append(
                (map_id, "map", number)
                + tuple(
                    rope.integer(key) for key in ("x", "y1", "y2", "l", "uf", "page")
                )
            )

    def _portals(self, map_id: int, tree: Tree) -> None:
        for _, portal in _numbered(tree.get("portal")):
            target_map = portal.integer("tm")
            target_portal = portal.text("tn")
            self.rows.portals.append(
                (
                    map_id,
                    portal.text("pn"),
                    portal.integer("pt"),
                    portal.integer("x"),
                    portal.integer("y"),
                    None if target_map == NO_MAP else target_map,
                    target_portal or None,
                )
            )

    def _spawns(self, map_id: int, tree: Tree) -> None:
        for _, life in _numbered(tree.get("life")):
            kind = {"m": "mob", "n": "npc"}.get(life.text("type"))
            if kind is None:
                raise life.at("type").error("a life type that isn't m or n")
            self.rows.spawns.append(
                (
                    map_id,
                    kind,
                    life.integer("id"),
                    life.integer("x"),
                    life.integer("cy"),
                    life.integer("fh"),
                    life.integer("rx0"),
                    life.integer("rx1"),
                    life.optional_integer("mobTime"),
                    life.integer_or("f", 0),
                    life.integer_or("hide", 0),
                )
            )

    def _layers(
        self, map_id: int, tree: Tree
    ) -> tuple[list[Segment], list[Segment], list[Climb]]:
        objects: list[Segment] = []
        tiles: list[Segment] = []
        climbs: list[Climb] = []
        for layer in LAYERS:
            found = tree.get(str(layer))
            if found is None:
                continue
            section = found.expect("property")
            for _, obj in _numbered(section.get("obj")):
                x, y, flip = obj.integer("x"), obj.integer("y"), obj.integer_or("f", 0)
                path = [obj.text(key) for key in ("l0", "l1", "l2")]
                image = f"Map/Obj/{obj.text('oS')}.img"
                node = self._assets.node(image, path, obj)
                frames = _frames(node)
                holders = [frames[0][1]] + ([node] if node.type == "property" else [])
                objects += geometry.footholds(holders, x, y, bool(flip))
                climbs += geometry.climbs(holders, x, y, bool(flip))
                self._item_rows(
                    map_id,
                    "object",
                    layer,
                    (obj.integer("z"), obj.integer("zM"), x, y, flip),
                    f"{image}/{'/'.join(path)}",
                    frames,
                )
            tile_set = section.at("info").expect("property").optional_text("tS")
            for _, tile in _numbered(section.get("tile")):
                if tile_set is None:
                    raise tile.error("its layer's info has no tS")
                x, y = tile.integer("x"), tile.integer("y")
                path = [tile.text("u"), str(tile.integer("no"))]
                image = f"Map/Tile/{tile_set}.img"
                canvas = self._assets.node(image, path, tile).expect("canvas")
                tiles += geometry.footholds([canvas], x, y, False)
                self._item_rows(
                    map_id,
                    "tile",
                    layer,
                    (canvas.integer_or("z", 0), tile.integer("zM"), x, y, 0),
                    f"{image}/{'/'.join(path)}",
                    [("0", canvas)],
                )
        return objects, tiles, climbs

    def _backgrounds(self, map_id: int, tree: Tree) -> None:
        for number, back in _numbered(tree.get("back")):
            kind = back.integer("ani")
            section = {0: "back", 1: "ani"}.get(kind)
            if section is None:
                raise back.at("ani").error(f"a background of kind {kind}")
            name = back.text("bS")
            frames: list[tuple[str, Tree]] = []
            asset = None
            if name:
                path = [section, str(back.integer("no"))]
                image = f"Map/Back/{name}.img"
                node = self._assets.node(image, path, back)
                frames = _frames(node) if kind else [("0", node.expect("canvas"))]
                asset = f"{image}/{'/'.join(path)}"
            place = (number, None, back.integer("x"), back.integer("y"))
            self._item_rows(
                map_id,
                "back",
                None,
                (*place, back.integer_or("f", 0)),
                asset,
                frames,
                tuple(
                    back.integer(key)
                    for key in ("type", "rx", "ry", "cx", "cy", "a", "front")
                ),
            )

    def _item_rows(
        self,
        map_id: int,
        kind: str,
        layer: int | None,
        place: tuple[int | None, ...],
        asset: str | None,
        frames: list[tuple[str, Tree]],
        background: tuple[int | None, ...] = _NO_BACKGROUND,
    ) -> None:
        item = self._item
        self._item += 1
        for number, canvas in frames:
            self.rows.layer_frames.append(
                (
                    item,
                    int(number),
                    canvas.canvas_image(),
                    *canvas.origin(),
                    canvas.optional_integer("delay"),
                )
            )
        origin = frames[0][1].origin() if frames else (None, None)
        z, zm, x, y, flip = place
        self.rows.map_layers.append(
            (item, map_id, kind, layer, z, zm, x, y, flip, *origin, len(frames), asset)
            + background
        )


def _vr_bounds(info: Tree) -> tuple[int, int, int, int] | None:
    keys = ("VRLeft", "VRTop", "VRRight", "VRBottom")
    present = [info.get(key) is not None for key in keys]
    if not any(present):
        return None
    if not all(present):
        raise info.error("it has some of the VR bounds but not all four")
    left, top, right, bottom = (info.integer(key) for key in keys)
    return left, top, right, bottom


def _numbered(node: Tree | None) -> list[tuple[int, Tree]]:
    """A sub-property's children, each named by a number, in the client's order."""
    if node is None:
        return []
    found: list[tuple[int, Tree]] = []
    for name, child in node.expect("property").children():
        if not name.isdigit():
            raise child.error("a child that isn't numbered")
        found.append((int(name), child.resolved().expect("property")))
    return found


def _frames(node: Tree) -> list[tuple[str, Tree]]:
    """
    An animated asset's frames, in order: its numbered children, each a
    canvas. A canvas on its own is one frame.
    """
    if node.type == "canvas":
        return [("0", node)]
    node.expect("property")
    frames = sorted(
        (
            (int(name), child.resolved().expect("canvas"))
            for name, child in node.children()
            if name.isdigit()
        ),
        key=lambda frame: frame[0],
    )
    if not frames:
        raise node.error("it has no frames")
    return [(str(number), canvas) for number, canvas in frames]
