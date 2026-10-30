"""
Players: one character composed from `Character.wz`, with a name tag under it.

A feasibility composer (#289): it isn't drawn in scenes yet. It reads the raw
layer's trees (`raw.sqlite`) and the image store, never the client, because
the catalogue has no tables for characters.

**The pieces.** A body (`Character/0000200n.img`) and its head
(`Character/0001200n.img`), `n` the skin, then a face, a hair, and one piece
per slot of `SLOTS`, each drawn from `PIECES`. A piece's frame is its
`<action>/<frame>` node: every canvas under it is a part. The head gives only
its `head`; the face its `default/face`, when the body's frame shows a face. A
part held once per skin (a hair's `hairShade`) is the skin's.

**Anchoring.** The body's part `body` has its origin at `(0, 0)`, the feet.
Every part's `map` holds anchor points (`navel`, `neck`, `hand`, `brow`...)
relative to its origin. A part is placed so that the first of its anchors
already known coincides with it, and then adds the others it holds. Parts are
placed until none is left: `neck` comes from the body, `brow` from the head,
`hand` from the arm.

**Draw order** is `Base/zmap.img`, whose first entry is the front: each part
is drawn at its canvas's `z`.

**Hiding.** A part is not drawn when every slot code of its `z` in
`Base/smap.img` (two letters each, such as `H1`) is in another piece's
`info/vslot`: a skullcap (`CpH1H5`) hides the hair's `hairOverHead` (`H1`).

**The name tag** is drawn under the feet. `UI/NameTag.img` holds only the
decorative styles (numbered from 3), each a west, centre and east piece and a
text colour. The plain tag, the one most players have, isn't in the files: it
is drawn here as a dark translucent box with white text. The game's font,
`UI/Font/NotoSansKRMedium.img`, is stored by the extraction as a hash only, so
the text is in a stand-in: Pillow's bundled default font (`TAG_FONT_SIZE`).
"""

import json
import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Self

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from game_data.archive import Pixels
from game_data.catalogue import Catalogue
from game_data.catalogue.trees import CatalogueError, Tree
from game_data.extraction import RAW
from game_data.render import Images

PLAYER_ACTIONS: Final = ("stand1", "walk1")
"""The actions a player is composed in, checked against the extract."""

SKINS: Final = (0, 1, 2, 3, 4)
"""The skins: body `Character/0000200n.img`, head `Character/0001200n.img`."""

SLOTS: Final = ("cap", "coat", "pants", "shoes", "weapon")

PIECES: Final[dict[str, tuple[int, ...]]] = {
    "face": (20000, 20001, 20002, 20003, 20004),
    "hair": (30000, 30010, 30020, 30030, 30040),
    "cap": (1002000, 1002003, 1002007, 1002009, 1002011),
    "coat": (1040002, 1040004, 1040006, 1040008, 1040010),
    "pants": (1060002, 1060004, 1060006, 1060008, 1060010),
    "shoes": (1072001, 1072004, 1072007, 1072009, 1072011),
    "weapon": (1302000, 1302002, 1302004, 1302007, 1302016),
}
"""
The pieces a player is drawn from, by slot: none cash, all of level 30 or
less, each with `stand1` and `walk1`. The weapons are one-handed, which stand
and walk in `stand1` and `walk1`.
"""

FOLDERS: Final = {
    "face": "Face",
    "hair": "Hair",
    "cap": "Cap",
    "coat": "Coat",
    "pants": "Pants",
    "shoes": "Shoes",
    "weapon": "Weapon",
}

BARE_HEAD: Final = 0.2
"""The chance a drawn outfit has no cap, so its hair shows whole."""

TAG_GAP: Final = 2
"""Pixels between the feet and the tag's top. Not measured on the client."""

TAG_HEIGHT: Final = 15
TAG_PADDING: Final = 3
"""The plain tag's height, and its margin either side of the text."""

TAG_BACKGROUND: Final = (0, 0, 0, 160)
"""The plain tag's box, RGBA. Not measured on the client."""

TAG_FONT_SIZE: Final = 12

_HEAD: Final = "head"
_ROOT: Final = "body"

_log = logging.getLogger(__name__)

type Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Outfit:
    """
    What a player wears. Each piece is an item ID from `PIECES`, or `None`.
    """

    skin: int = 0
    face: int | None = None
    hair: int | None = None
    cap: int | None = None
    coat: int | None = None
    pants: int | None = None
    shoes: int | None = None
    weapon: int | None = None

    @classmethod
    def drawn(cls, rng: np.random.Generator) -> Outfit:
        """One drawn uniformly from `SKINS` and `PIECES`, bare-headed by chance."""
        skin = SKINS[int(rng.integers(len(SKINS)))]
        pieces: dict[str, int | None] = {
            slot: ids[int(rng.integers(len(ids)))] for slot, ids in PIECES.items()
        }
        if rng.random() < BARE_HEAD:
            pieces["cap"] = None
        return cls(skin, **pieces)

    def pieces(self) -> Iterator[tuple[str, int]]:
        """Each piece worn, `(image path, item ID)`, body and head first."""
        yield f"Character/{2000 + self.skin:08d}.img", 2000 + self.skin
        yield f"Character/{12000 + self.skin:08d}.img", 12000 + self.skin
        for slot, folder in FOLDERS.items():
            item = getattr(self, slot)
            if item is not None:
                yield f"Character/{folder}/{item:08d}.img", item


@dataclass(frozen=True, slots=True)
class Player:
    """
    One composed player.

    :ivar pixels: `(height, width, 4)` RGBA: the character and its tag.
    :ivar origin: Where its feet are in `pixels`, `(x, y)`.
    :ivar box: The bounds of the character's opaque pixels, tag excluded,
        `(x1, y1, x2, y2)` in `pixels`, `x2` and `y2` one past the last.
    :ivar tag: The tag's bounds likewise, `None` without one.
    """

    pixels: Pixels
    origin: tuple[int, int]
    box: Box
    tag: Box | None


@dataclass(frozen=True, slots=True)
class Part:
    """
    One canvas of a piece's frame.

    :ivar name: Its node's name, such as `arm` or `hairOverHead`.
    :ivar item: The item ID of the piece it's from.
    :ivar image: Its image in the image store.
    :ivar origin: Its `origin`.
    :ivar z: Its `z`, a layer of `Base/zmap.img`.
    :ivar anchors: Its `map`: anchor points relative to its origin.
    """

    name: str
    item: int
    image: str
    origin: tuple[int, int]
    z: str
    anchors: dict[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _Layer:
    """Pixels to lay, their top left at `(left, top)` from the feet."""

    pixels: Pixels
    left: int
    top: int


class Wardrobe:
    """
    Composes players from one extraction's raw layer and image store. It holds
    the raw layer open until closed, so use it in a `with`.
    """

    def __init__(self, cat: Catalogue) -> None:
        raw = cat.store.extraction(cat.build) / RAW
        self._db = sqlite3.connect(f"{raw.resolve().as_uri()}?mode=ro", uri=True)
        self._trees: dict[str, Tree | None] = {}
        self.images = Images(cat.store.images)

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

    def frames(self, outfit: Outfit, action: str) -> int:
        """
        How many frames the outfit's body has in `action`.

        :raises LookupError: The extract has no such body, or it no such action.
        """
        body, _ = next(outfit.pieces())
        return len(list(self._body_action(body, action).children()))

    def parts(self, outfit: Outfit, action: str, frame: int) -> list[Part]:
        """
        The parts of the outfit's frame, before hiding and anchoring. A piece
        without that frame is left out, with a warning.

        :raises LookupError: The extract lacks one of the outfit's pieces, or
            its body lacks the frame.
        """
        pieces = list(outfit.pieces())
        (body_path, body_id), (head_path, head_id) = pieces[:2]
        body_frame = self._body_action(body_path, action).get(str(frame))
        if body_frame is None:
            raise LookupError(f"{body_path} has no frame {action}/{frame}")
        body_frame = body_frame.resolved()
        parts = list(_canvases(body_frame, body_id, outfit.skin))
        head = self._tree(head_path)
        head_frame = _child(head, action, str(frame)) or _child(head, "front")
        if head_frame is not None:
            parts += [
                p
                for p in _canvases(head_frame, head_id, outfit.skin)
                if p.name == _HEAD
            ]
        shows_face = body_frame.get("face")
        for path, item in pieces[2:]:
            tree = self._tree(path)
            if item == outfit.face:
                if shows_face is None or shows_face.int_value() != 0:
                    found = _child(tree, "default")
                    parts += (
                        [] if found is None else _canvases(found, item, outfit.skin)
                    )
                continue
            found = _child(tree, action, str(frame))
            if found is None:
                _log.warning("%s has no frame %s/%s; left out", path, action, frame)
                continue
            parts += _canvases(found, item, outfit.skin)
        return parts

    def compose(
        self,
        outfit: Outfit,
        action: str,
        frame: int,
        *,
        name: str | None = None,
        tag: int | None = None,
        flip: bool = False,
    ) -> Player:
        """
        One player: the outfit's frame, anchored, layered and hidden as the
        module says, with `name` in a tag under it.

        :param tag: `None` for the plain tag, or a style of `UI/NameTag.img`.
        :param flip: Face right: the character is mirrored about its feet, and
            the tag isn't.
        :raises LookupError: As `parts` does, or the extract has no such tag
            style.
        :raises CatalogueError: A part can't be anchored, or has a `z` that
            `Base/zmap.img` lacks.
        """
        order = self._zmap()
        shown = _shown(
            self.parts(outfit, action, frame), self._vslots(outfit), self._smap()
        )
        placed = anchor(shown)
        for part, _ in placed:
            if part.z not in order:
                raise CatalogueError(
                    f"item {part.item}'s part {part.name}: z {part.z!r} isn't in "
                    "Base/zmap.img"
                )
        placed.sort(key=lambda found: -order[found[0].z])
        layers: list[_Layer] = []
        for part, (x, y) in placed:
            pixels = self.images.get(part.image)
            left, top = x - part.origin[0], y - part.origin[1]
            if flip:
                pixels = pixels[:, ::-1]
                left = -(left + pixels.shape[1])
            layers.append(_Layer(pixels, left, top))
        tag_layers = [] if name is None else self._tag(name, tag)
        return _flatten(layers, tag_layers)

    def _body_action(self, path: str, action: str) -> Tree:
        found = _child(self._tree(path), action)
        if found is None:
            raise LookupError(f"{path} has no action {action!r}")
        return found

    def _tree(self, path: str) -> Tree:
        if path not in self._trees:
            row = self._db.execute(
                "SELECT tree FROM images WHERE path = ?", (path,)
            ).fetchone()
            self._trees[path] = (
                None if row is None else Tree.of(path, json.loads(row[0]))
            )
        found = self._trees[path]
        if found is None:
            raise LookupError(f"the extract has no {path}")
        return found

    def _zmap(self) -> dict[str, int]:
        """Each layer's place, the front first."""
        layers = self._tree("Base/zmap.img").expect("property").children()
        return {name: index for index, (name, _) in enumerate(layers)}

    def _smap(self) -> dict[str, frozenset[str]]:
        """Each layer's slot codes."""
        found: dict[str, frozenset[str]] = {}
        for name, node in self._tree("Base/smap.img").expect("property").children():
            found[name] = (
                frozenset() if node.value is None else _codes(node.str_value())
            )
        return found

    def _vslots(self, outfit: Outfit) -> dict[int, frozenset[str]]:
        """Each piece's `info/vslot` codes, for those that have one."""
        found: dict[int, frozenset[str]] = {}
        for path, item in outfit.pieces():
            info = self._tree(path).get("info")
            vslot = None if info is None else info.optional_text("vslot")
            if vslot:
                found[item] = _codes(vslot)
        return found

    def _tag(self, name: str, style: int | None) -> list[_Layer]:
        font = ImageFont.load_default(size=TAG_FONT_SIZE)
        if not isinstance(font, ImageFont.FreeTypeFont):
            raise TypeError("drawing name tags needs Pillow built with FreeType")
        if style is None:
            return _plain_tag(name, font)
        found = _child(self._tree("UI/NameTag.img"), str(style))
        if found is None:
            raise LookupError(f"UI/NameTag.img has no style {style}")
        return self._styled_tag(name, font, found)

    def _styled_tag(
        self, name: str, font: ImageFont.FreeTypeFont, style: Tree
    ) -> list[_Layer]:
        """
        A style's west piece ending at the text's left, its centre piece
        tiled under the text, its east piece from the text's right, each at
        its origin; the text in the style's `clr`, ARGB.
        """
        text = _text(name, font, _argb(style.integer("clr")))
        width = text.shape[1]
        layers: list[_Layer] = []
        pieces = {key: style.at(key).resolved() for key in ("w", "c", "e")}
        for key, node in pieces.items():
            image = node.canvas_image()
            if image is None:
                raise CatalogueError(f"UI/NameTag.img {style.path}/{key} has no image")
            pixels = self.images.get(image)
            ox, oy = node.origin()
            if key == "w":
                layers.append(_Layer(pixels, -ox, -oy))
            elif key == "e":
                layers.append(_Layer(pixels, width - ox, -oy))
            else:
                step = pixels.shape[1]
                for x in range(0, width, step):
                    tile = pixels[:, : min(step, width - x)]
                    layers.append(_Layer(tile, x - ox, -oy))
        layers.append(_Layer(text, 0, 0))
        return _centred(layers)


def anchor(parts: list[Part]) -> list[tuple[Part, tuple[int, int]]]:
    """
    Where each part's origin goes, from the feet: the body's `body` at
    `(0, 0)`, then each part at the first of its anchors already known.

    :returns: The parts placed, in the order given.
    :raises CatalogueError: There is no `body` part, or a part has no anchor
        that any placed part holds.
    """
    roots = [part for part in parts if part.name == _ROOT]
    if not roots:
        raise CatalogueError("the frame has no body part to anchor the others to")
    known = dict(roots[0].anchors)
    at: dict[int, tuple[int, int]] = {id(roots[0]): (0, 0)}
    pending = [part for part in parts if part is not roots[0]]
    while pending:
        left: list[Part] = []
        for part in pending:
            shared = next((name for name in part.anchors if name in known), None)
            if shared is None:
                left.append(part)
                continue
            kx, ky = known[shared]
            px, py = part.anchors[shared]
            x, y = kx - px, ky - py
            at[id(part)] = (x, y)
            for name, (ax, ay) in part.anchors.items():
                known.setdefault(name, (x + ax, y + ay))
        if len(left) == len(pending):
            names = ", ".join(f"{p.item}/{p.name} {sorted(p.anchors)}" for p in left)
            raise CatalogueError(f"these parts share no anchor with the rest: {names}")
        pending = left
    return [(part, at[id(part)]) for part in parts]


def _shown(
    parts: list[Part],
    vslots: dict[int, frozenset[str]],
    smap: dict[str, frozenset[str]],
) -> list[Part]:
    """The parts no other piece's `vslot` hides."""
    shown: list[Part] = []
    for part in parts:
        codes = smap.get(part.z, frozenset())
        hidden = bool(codes) and any(
            codes <= vslot for item, vslot in vslots.items() if item != part.item
        )
        if not hidden:
            shown.append(part)
    return shown


def _codes(text: str) -> frozenset[str]:
    return frozenset(text[i : i + 2] for i in range(0, len(text) - 1, 2))


def _child(tree: Tree, *names: str) -> Tree | None:
    node: Tree | None = tree
    for name in names:
        node = node.get(name) if node is not None else None
        node = node.resolved() if node is not None else None
    return node


def _canvases(frame: Tree, item: int, skin: int) -> list[Part]:
    """
    Every canvas under a frame, links followed, as parts. A property of
    numbered canvases, as a hair's `hairShade` is, gives the one of the skin,
    or its `0` when it has none.
    """
    parts: list[Part] = []
    for name, node in frame.children():
        node = node.resolved()
        if node.type == "property":
            found = node.get(str(skin)) or node.get("0")
            if found is None:
                continue
            node = found.resolved()
        if node.type != "canvas":
            continue
        image = node.canvas_image()
        if image is None:
            _log.warning("%s %s has no image; left out", node.image, node.path)
            continue
        z = node.get("z")
        anchors = node.get("map")
        parts.append(
            Part(
                name,
                item,
                image,
                node.origin(),
                "" if z is None else str(z.resolved().value),
                {}
                if anchors is None
                else {k: v.resolved().vector() for k, v in anchors.children()},
            )
        )
    return parts


def _text(name: str, font: ImageFont.FreeTypeFont, colour: tuple[int, ...]) -> Pixels:
    """`name` in `font`, `colour` RGBA, on transparent pixels."""
    ascent, descent = font.getmetrics()
    left, _, right, _ = (round(v) for v in font.getbbox(name))
    mask = Image.new("L", (max(right - left, 1), ascent + descent))
    ImageDraw.Draw(mask).text((-left, 0), name, font=font, fill=255)
    alpha = np.asarray(mask, dtype=np.float32) / 255 * colour[3]
    pixels = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    pixels[..., :3] = colour[:3]
    pixels[..., 3] = np.rint(alpha).astype(np.uint8)
    return pixels


def _plain_tag(name: str, font: ImageFont.FreeTypeFont) -> list[_Layer]:
    text = _text(name, font, (255, 255, 255, 255))
    height, width = text.shape[:2]
    box = np.zeros((TAG_HEIGHT, width + 2 * TAG_PADDING, 4), dtype=np.uint8)
    box[...] = TAG_BACKGROUND
    return _centred(
        [
            _Layer(box, 0, 0),
            _Layer(text, TAG_PADDING, (TAG_HEIGHT - height) // 2),
        ]
    )


def _centred(layers: list[_Layer]) -> list[_Layer]:
    """The layers moved so their top is `TAG_GAP` under the feet, centred."""
    left = min(layer.left for layer in layers)
    right = max(layer.left + layer.pixels.shape[1] for layer in layers)
    top = min(layer.top for layer in layers)
    dx = -(left + right) // 2
    dy = TAG_GAP - top
    return [_Layer(layer.pixels, layer.left + dx, layer.top + dy) for layer in layers]


def _argb(value: int) -> tuple[int, int, int, int]:
    """A signed 32-bit ARGB colour, as the client writes `clr`, to RGBA."""
    value &= 0xFFFFFFFF
    return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, value >> 24


def _flatten(character: list[_Layer], tag: list[_Layer]) -> Player:
    layers = character + tag
    left = min(layer.left for layer in layers)
    top = min(layer.top for layer in layers)
    right = max(layer.left + layer.pixels.shape[1] for layer in layers)
    bottom = max(layer.top + layer.pixels.shape[0] for layer in layers)
    pixels = np.zeros((bottom - top, right - left, 4), dtype=np.uint8)
    for layer in character:
        _over(pixels, layer.pixels, layer.left - left, layer.top - top)
    box = _opaque(pixels)
    for layer in tag:
        _over(pixels, layer.pixels, layer.left - left, layer.top - top)
    tag_box = None
    if tag:
        tag_left = min(layer.left for layer in tag) - left
        tag_top = min(layer.top for layer in tag) - top
        tag_right = max(layer.left + layer.pixels.shape[1] for layer in tag) - left
        tag_bottom = max(layer.top + layer.pixels.shape[0] for layer in tag) - top
        tag_box = (tag_left, tag_top, tag_right, tag_bottom)
    if box is None:
        raise CatalogueError("the player has no opaque pixel")
    return Player(pixels, (-left, -top), box, tag_box)


def _opaque(pixels: Pixels) -> Box | None:
    mask = pixels[..., 3] > 0
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if not rows.size:
        return None
    return int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1


def _over(target: Pixels, pixels: Pixels, left: int, top: int) -> None:
    """Lays RGBA `pixels` over RGBA `target`, top left at `(left, top)`."""
    height, width = pixels.shape[:2]
    source = pixels.astype(np.float32)
    region = target[top : top + height, left : left + width]
    below = region.astype(np.float32)
    alpha = source[..., 3:] / 255
    under = below[..., 3:] / 255 * (1 - alpha)
    out = alpha + under
    colour = source[..., :3] * alpha + below[..., :3] * under
    colour = np.divide(colour, out, out=np.zeros_like(colour), where=out > 0)
    region[..., :3] = np.rint(colour).astype(np.uint8)
    region[..., 3:] = np.rint(out * 255).astype(np.uint8)
