"""
Players: one character composed from `Character.wz`, with a name tag under it.

Not drawn in scenes yet. It reads the raw layer's trees (`raw.sqlite`) and the
image store, never the client, because the catalogue has no tables for
characters.

**The pieces.** A body (`Character/0000200n.img`) and its head
(`Character/0001200n.img`), `n` the skin, then a face, a hair, and one piece
per slot of `SLOTS`. Each slot's pieces are every image of its folder
(`Wardrobe.pieces`), cash or not: `Character/Cap/01002000.img` is cap
1002000. The slot is the item ID's prefix (`id // 10000`), so `Accessory`
splits into face accessories (101), eye accessories (102) and earrings (103),
and an overall (`Longcoat`, 105) fills the coat's slot.

**A piece's frame** is its `<action>/<frame>` node: every canvas under it is a
part. A cash weapon (170) holds its frames under a weapon type
(`30/stand1/0`), the type of the weapon it is worn over (`Outfit.weapon_type`).
The head gives only its `head`. A piece holding the action but not that frame
shows nothing in it: most gloves have no `swingO1/0`, where the hand is behind
the body. A piece lacking the action, or holding it through a link that names
nothing, is a `MissingFrame`, so a player is never drawn with a part missing,
with two exceptions. The face and the accessories (`FACE_PIECES`) follow the
face: without the action, their `default`, and nothing when the body's frame
hides the face (`face` 0, a climber's back). On a ladder or rope the weapon
and the shield may lack the action (`UNSEEN`). A part held once per skin (a
hair's `hairShade`) is the skin's.

**The weapon type** (`id // 10000 % 100`, `WEAPON_TYPES`) picks the stance,
`stand1`/`walk1` or `stand2`/`walk2` (a two-handed sword stands in `stand2`
and walks in `walk1`), and the attacks: the poses of `Outfit.poses`. A
shield is worn with a one-handed weapon only (types under 40).

**Drawing.** `Wardrobe.outfit(rng)` draws each slot uniformly among its
pieces, an optional slot (`EMPTY`) left empty by chance, pants only under a
coat whose `islot` leaves the legs (`Pn`) free. `Wardrobe.draw(rng)` then draws
a pose and a frame; when a piece lacks the pose or can't be placed, the outfit
and pose are redrawn, and the miss is counted by item (`Wardrobe.misses`) and
logged. The same `rng` gives the same character.

**Anchoring.** The body's part `body` has its origin at `(0, 0)`, the feet.
Every part's `map` holds anchor points (`navel`, `neck`, `hand`, `brow`...)
relative to its origin. A part is placed so that the first of its anchors
already known coincides with it, and then adds the others it holds. Parts are
placed until none is left: `neck` comes from the body, `brow` from the head,
`hand` from the arm. The body's parts that hold a `handMove` (its `lHand`, in
`alert`) stand their origin on the feet as `body` does, and a part hidden as
below still gives its anchors.

**Draw order** is `Base/zmap.img`, whose first entry is the front: each part
is drawn at its canvas's `z`.

**Hiding.** A part is not drawn when every slot code of its `z` in
`Base/smap.img` (two letters each, such as `H1`) is in another piece's
`info/vslot`: a skullcap (`CpH1H5`) hides the hair's `hairOverHead` (`H1`).

**The box** bounds the character's opaque pixels only, never its name tag.

**The name tag** is drawn under the feet. `UI/NameTag.img` holds only the
decorative styles (numbered from 3), each a west, centre and east piece and a
text colour. The plain tag, the one most players have, isn't in the files: it
is drawn here as a dark translucent box with white text. The game's font,
`UI/Font/NotoSansKRMedium.img`, is stored by the extraction as a hash only, so
the text is in a stand-in: Pillow's bundled default font (`TAG_FONT_SIZE`).

`coverage` composes random outfits in every pose and frame, and groups what
fails by item.
"""

import json
import logging
import sqlite3
from collections import Counter, OrderedDict
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


@dataclass(frozen=True, slots=True)
class WeaponType:
    """
    How a weapon type stands, walks and attacks.

    :ivar name: What it is, such as `one-handed sword`.
    :ivar stand: Its standing action, `stand1` or `stand2`.
    :ivar walk: Its walking action, `walk1` or `walk2`.
    :ivar attacks: The attacks a player hunting with it shows.
    """

    name: str
    stand: str
    walk: str
    attacks: tuple[str, ...]


_SWING_ONE: Final = ("swingO1", "swingO2", "swingO3", "stabO1", "stabO2")
_SWING_TWO: Final = ("swingT1", "swingT2", "swingT3", "stabO1", "stabO2")
_POLE: Final = ("swingP1", "swingP2", "swingT2", "stabT1", "stabT2")
_MAGIC: Final = ("swingO1", "swingO2", "swingO3", "stabO1", "shoot1")

WEAPON_TYPES: Final[dict[int, WeaponType]] = {
    30: WeaponType("one-handed sword", "stand1", "walk1", _SWING_ONE),
    31: WeaponType("one-handed axe", "stand1", "walk1", _SWING_ONE),
    32: WeaponType("one-handed blunt weapon", "stand1", "walk1", _SWING_ONE),
    33: WeaponType("dagger", "stand1", "walk1", _SWING_ONE),
    37: WeaponType("wand", "stand1", "walk1", _MAGIC),
    38: WeaponType("staff", "stand1", "walk1", _MAGIC),
    40: WeaponType("two-handed sword", "stand2", "walk1", _SWING_TWO),
    41: WeaponType("two-handed axe", "stand2", "walk2", _SWING_TWO),
    42: WeaponType("two-handed blunt weapon", "stand2", "walk2", _SWING_TWO),
    43: WeaponType("spear", "stand2", "walk2", _POLE),
    44: WeaponType("polearm", "stand2", "walk2", _POLE),
    45: WeaponType("bow", "stand1", "walk1", ("shoot1",)),
    46: WeaponType("crossbow", "stand2", "walk2", ("shoot2",)),
    47: WeaponType("claw", "stand1", "walk1", _SWING_ONE),
}
"""
The weapon types a player can wield, by `id // 10000 % 100`. The stances are
the regular weapons' `info/stand` and `info/walk`. The attacks are the ones
each type's regular weapons all have frames of, among those its class uses;
which of them players show most isn't measured. Type 39 (one hidden weapon,
bare hands) and the types no regular weapon has (48, 49) are left out.
"""

ONE_HANDED: Final = 40
"""Weapon types under this are one-handed, the only ones worn with a shield."""

MOVES: Final = ("alert", "jump", "ladder", "rope", "prone")
"""The poses every player shows, whatever it wields."""

PLAYER_ACTIONS: Final = tuple(
    dict.fromkeys(
        [
            *(kind.stand for kind in WEAPON_TYPES.values()),
            *(kind.walk for kind in WEAPON_TYPES.values()),
            *MOVES,
            *(attack for kind in WEAPON_TYPES.values() for attack in kind.attacks),
        ]
    )
)
"""Every pose a player is composed in: the hunting set."""

SKINS: Final = (0, 1, 2, 3, 4)
"""The skins: body `Character/0000200n.img`, head `Character/0001200n.img`."""

SLOTS: Final = (
    "cap",
    "face_accessory",
    "eye_accessory",
    "earrings",
    "coat",
    "pants",
    "shoes",
    "glove",
    "cape",
    "shield",
    "weapon",
)
"""The equip slots, regular and cash alike. No rings and no pet equips."""

FACE_PIECES: Final = frozenset({"face", "face_accessory", "eye_accessory", "earrings"})
"""The pieces that follow the face: see the module."""

UNSEEN: Final[dict[str, frozenset[str]]] = {
    "ladder": frozenset({"weapon", "shield"}),
    "rope": frozenset({"weapon", "shield"}),
}
"""
The slots a pose may not show: a piece of them without the frame is left out,
not missing. A climber shows its back, and almost no weapon has a ladder or
rope frame.
"""

EMPTY: Final[dict[str, float]] = {
    "cap": 0.2,
    "face_accessory": 0.7,
    "eye_accessory": 0.6,
    "earrings": 0.6,
    "glove": 0.4,
    "cape": 0.5,
    "shield": 0.5,
}
"""
The chance each optional slot is left empty, a shield's only with a one-handed
weapon. First guesses, not measured on players.
"""

TRIES: Final = 1000
"""How many outfits and poses `Wardrobe.draw` tries before giving up."""

PREFIXES: Final[dict[int, tuple[str, str]]] = {
    100: ("cap", "Cap"),
    101: ("face_accessory", "Accessory"),
    102: ("eye_accessory", "Accessory"),
    103: ("earrings", "Accessory"),
    104: ("coat", "Coat"),
    105: ("coat", "Longcoat"),
    106: ("pants", "Pants"),
    107: ("shoes", "Shoes"),
    108: ("glove", "Glove"),
    109: ("shield", "Shield"),
    110: ("cape", "Cape"),
    170: ("weapon", "Weapon"),
    **{100 + kind: ("weapon", "Weapon") for kind in WEAPON_TYPES},
}
"""Each equip's slot and folder, by `id // 10000`."""

CASH_WEAPON: Final = 170
"""The prefix of cash weapons, whose frames are held per weapon type."""

LEGS: Final = "Pn"
"""The `islot` code of the legs: a coat holding it is an overall."""

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
_HAND: Final = "handMove"
_TREES: Final = 512
"""How many images' trees a wardrobe keeps parsed."""

_log = logging.getLogger(__name__)

type Box = tuple[int, int, int, int]


class MissingFrame(LookupError):
    """
    Pieces of an outfit lack the frame of its pose.

    :ivar items: Their item IDs.
    """

    def __init__(self, items: tuple[int, ...], action: str, frame: int) -> None:
        names = ", ".join(str(item) for item in items)
        super().__init__(f"no frame {action}/{frame} in {names}")
        self.items = items


class _Missing(Exception):
    """A piece lacks a frame."""


class PartError(CatalogueError):
    """
    Parts can't be anchored or layered.

    :ivar items: The item IDs of the pieces they're from.
    :ivar reason: What's wrong, without the items, to group failures by.
    """

    def __init__(self, items: tuple[int, ...], reason: str, detail: str) -> None:
        super().__init__(detail)
        self.items = items
        self.reason = reason


def slot_of(item: int) -> str:
    """
    The slot an item ID fills: `body`, `head`, `face`, `hair`, or one of
    `SLOTS`.

    :raises ValueError: It fills none, as a ring doesn't.
    """
    if item < 10000:
        return "body"
    if item < 20000:
        return "head"
    if 20000 <= item < 30000:
        return "face"
    if 30000 <= item < 50000:
        return "hair"
    found = PREFIXES.get(item // 10000)
    if found is None:
        raise ValueError(f"item {item} fills no slot a player is drawn with")
    return found[0]


def image_of(item: int) -> str:
    """The image of an item ID, such as `Character/Cap/01002000.img`."""
    slot = slot_of(item)
    if slot in ("body", "head"):
        return f"Character/{item:08d}.img"
    folder = slot.capitalize() if slot in ("face", "hair") else None
    if folder is None:
        folder = PREFIXES[item // 10000][1]
    return f"Character/{folder}/{item:08d}.img"


def is_cash_weapon(item: int) -> bool:
    return item // 10000 == CASH_WEAPON


@dataclass(frozen=True, slots=True)
class Outfit:
    """
    What a player wears. Each piece is an item ID, or `None`.

    :ivar weapon_type: The weapon type whose stance and frames the weapon
        takes, a key of `WEAPON_TYPES`. A regular weapon's is its own
        (`id // 10000 % 100`) when `None`; a cash weapon needs one.
    """

    skin: int = 0
    face: int | None = None
    hair: int | None = None
    cap: int | None = None
    face_accessory: int | None = None
    eye_accessory: int | None = None
    earrings: int | None = None
    coat: int | None = None
    pants: int | None = None
    shoes: int | None = None
    glove: int | None = None
    cape: int | None = None
    shield: int | None = None
    weapon: int | None = None
    weapon_type: int | None = None

    @property
    def wields(self) -> WeaponType | None:
        """
        Its weapon's type, `None` bare-handed.

        :raises LookupError: A cash weapon without a `weapon_type`, or a type
            `WEAPON_TYPES` lacks.
        """
        if self.weapon is None:
            return None
        kind = self.weapon_type
        if kind is None:
            if is_cash_weapon(self.weapon):
                raise LookupError(f"cash weapon {self.weapon} needs a weapon_type")
            kind = self.weapon // 10000 % 100
        found = WEAPON_TYPES.get(kind)
        if found is None:
            raise LookupError(f"weapon {self.weapon}: no weapon type {kind}")
        return found

    def poses(self) -> tuple[str, ...]:
        """
        The poses it's drawn in: its weapon type's stance, `MOVES`, and its
        attacks. Bare-handed, `stand1` and `walk1` and `MOVES`.

        :raises LookupError: As `wields` does.
        """
        kind = self.wields
        if kind is None:
            return ("stand1", "walk1", *MOVES)
        return (kind.stand, kind.walk, *MOVES, *kind.attacks)

    def pieces(self) -> Iterator[tuple[str, int]]:
        """Each piece worn, `(image path, item ID)`, body and head first."""
        yield f"Character/{2000 + self.skin:08d}.img", 2000 + self.skin
        yield f"Character/{12000 + self.skin:08d}.img", 12000 + self.skin
        for slot in ("face", "hair", *SLOTS):
            item = getattr(self, slot)
            if item is not None:
                yield image_of(item), item


@dataclass(frozen=True, slots=True)
class Look:
    """
    One drawn player: what it wears, and the pose it shows.

    :ivar flip: Faces right.
    """

    outfit: Outfit
    action: str
    frame: int
    flip: bool


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
class Coverage:
    """
    What `coverage` found.

    :ivar tried: Frames composed: outfits x poses x frames.
    :ivar composed: Those that composed.
    :ivar failures: By item ID, how many frames failed for each reason.
    """

    tried: int
    composed: int
    failures: dict[int, Counter[str]]

    @property
    def share(self) -> float:
        """The share of frames that composed."""
        return self.composed / self.tried if self.tried else 0.0


@dataclass(frozen=True, slots=True)
class _Layer:
    """Pixels to lay, their top left at `(left, top)` from the feet."""

    pixels: Pixels
    left: int
    top: int


class Wardrobe:
    """
    Draws and composes players from one extraction's raw layer and image
    store. It holds the raw layer open until closed, so use it in a `with`.
    """

    def __init__(self, cat: Catalogue) -> None:
        raw = cat.store.extraction(cat.build) / RAW
        self._db = sqlite3.connect(f"{raw.resolve().as_uri()}?mode=ro", uri=True)
        self._trees: OrderedDict[str, Tree | None] = OrderedDict()
        self._pieces: dict[str, tuple[int, ...]] | None = None
        self._order: dict[str, int] | None = None
        self._codes: dict[str, frozenset[str]] | None = None
        self.images = Images(cat.store.images)
        self.misses: Counter[int] = Counter()
        """By item ID, how many draws it made `draw` redraw."""

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

    # --- drawing ----------------------------------------------------------------

    def pieces(self, slot: str) -> tuple[int, ...]:
        """
        Every piece of a slot (`face`, `hair` or one of `SLOTS`) in the
        extract, by item ID, ascending. The weapons are those of
        `WEAPON_TYPES`, and every cash weapon.
        """
        if self._pieces is None:
            found: dict[str, list[int]] = {}
            rows = self._db.execute(
                "SELECT path FROM images WHERE path LIKE 'Character/%/%.img'"
            )
            for (path,) in rows:
                parts = path.split("/")
                stem = parts[-1].removesuffix(".img")
                if len(parts) != 3 or len(stem) != 8 or not stem.isdigit():
                    continue
                item = int(stem)
                try:
                    if image_of(item) != path:
                        continue
                except ValueError:
                    continue
                found.setdefault(slot_of(item), []).append(item)
            self._pieces = {key: tuple(sorted(ids)) for key, ids in found.items()}
        return self._pieces.get(slot, ())

    def weapon_types(self, weapon: int) -> tuple[int, ...]:
        """
        The weapon types a weapon can be worn as: a regular weapon's own, a
        cash weapon's every key of `WEAPON_TYPES` it holds frames under.
        """
        if not is_cash_weapon(weapon):
            kind = weapon // 10000 % 100
            return (kind,) if kind in WEAPON_TYPES else ()
        keys = (name for name, _ in self.tree(image_of(weapon)).children())
        return tuple(
            sorted(int(k) for k in keys if k.isdigit() and int(k) in WEAPON_TYPES)
        )

    def outfit(self, rng: np.random.Generator) -> Outfit:
        """
        One outfit, each slot drawn uniformly among its `pieces`, as the
        module says. A cash weapon held under no weapon type is redrawn, and
        counted in `misses`.

        :raises LookupError: The extract has no piece of a slot every outfit
            fills, or no weapon that can be worn.
        """
        skin = SKINS[int(rng.integers(len(SKINS)))]
        face = self._pick(rng, "face")
        hair = self._pick(rng, "hair")
        weapon, kinds = self._pick(rng, "weapon"), ()
        for _ in range(TRIES):
            kinds = self.weapon_types(weapon)
            if kinds:
                break
            self._miss(weapon, "has no frames under a weapon type")
            weapon = self._pick(rng, "weapon")
        if not kinds:
            raise LookupError(f"no weapon of {TRIES} drawn can be worn")
        weapon_type = kinds[int(rng.integers(len(kinds)))]
        coat = self._pick(rng, "coat")
        pants = None if self._covers_legs(coat) else self._pick(rng, "pants")
        shoes = self._pick(rng, "shoes")
        optional = {
            slot: self._maybe(rng, slot)
            for slot in ("cap", "face_accessory", "eye_accessory", "earrings")
        }
        glove = self._maybe(rng, "glove")
        cape = self._maybe(rng, "cape")
        shield = self._maybe(rng, "shield") if weapon_type < ONE_HANDED else None
        return Outfit(
            skin=skin,
            face=face,
            hair=hair,
            coat=coat,
            pants=pants,
            shoes=shoes,
            glove=glove,
            cape=cape,
            shield=shield,
            weapon=weapon,
            weapon_type=weapon_type,
            **optional,
        )

    def draw(self, rng: np.random.Generator) -> Look:
        """
        One player: an `outfit`, then one of its `Outfit.poses`, a frame and a
        facing, each uniformly. When a piece lacks the pose (a `MissingFrame`)
        or can't be placed (a `PartError`), the outfit and pose are redrawn,
        and the miss is counted by item in `misses` and logged. What it
        returns composes.

        :raises LookupError: As `outfit` does, or `TRIES` draws all missed.
        """
        for _ in range(TRIES):
            outfit = self.outfit(rng)
            poses = outfit.poses()
            action = poses[int(rng.integers(len(poses)))]
            frame = int(rng.integers(self.frames(outfit, action)))
            flip = bool(rng.random() < 0.5)
            try:
                self._placed(outfit, action, frame)
            except (MissingFrame, PartError) as error:
                why = (
                    f"has no {action}"
                    if isinstance(error, MissingFrame)
                    else f"in {action}/{frame}: {error.reason}"
                )
                for item in error.items:
                    self._miss(item, why)
                continue
            return Look(outfit, action, frame, flip)
        raise LookupError(f"{TRIES} drawn players all lacked a frame")

    # --- composing --------------------------------------------------------------

    def frames(self, outfit: Outfit, action: str) -> int:
        """
        How many frames the outfit's body has in `action`.

        :raises LookupError: The extract has no such body, or it no such action.
        """
        body, _ = next(outfit.pieces())
        return len(list(self._body_action(body, action).children()))

    def parts(self, outfit: Outfit, action: str, frame: int) -> list[Part]:
        """
        The parts of the outfit's frame, before hiding and anchoring.

        :raises MissingFrame: Pieces lack the frame, as the module says.
        :raises LookupError: The extract lacks one of the outfit's pieces, or
            its body lacks the frame.
        """
        parts, missing = self._parts(outfit, action, frame)
        if missing:
            raise MissingFrame(missing, action, frame)
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
        :raises MissingFrame: As `parts` does.
        :raises LookupError: As `parts` does, or the extract has no such tag
            style.
        :raises PartError: A part can't be anchored, or has a `z` that
            `Base/zmap.img` lacks.
        """
        placed = self._placed(outfit, action, frame)
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

    def _placed(
        self, outfit: Outfit, action: str, frame: int
    ) -> list[tuple[Part, tuple[int, int]]]:
        """
        The parts shown, where their origins go from the feet, back to front.

        :raises MissingFrame: As `parts` does.
        :raises PartError: As `compose` does.
        """
        order = self._zmap()
        parts = self.parts(outfit, action, frame)
        shown = {id(p) for p in _shown(parts, self._vslots(outfit), self._smap())}
        placed = [found for found in anchor(parts) if id(found[0]) in shown]
        for part, _ in placed:
            if part.z not in order:
                raise PartError(
                    (part.item,),
                    f"z {part.z!r} isn't in Base/zmap.img",
                    f"item {part.item}'s part {part.name}: z {part.z!r} isn't in "
                    "Base/zmap.img",
                )
        placed.sort(key=lambda found: -order[found[0].z])
        return placed

    def _parts(
        self, outfit: Outfit, action: str, frame: int
    ) -> tuple[list[Part], tuple[int, ...]]:
        """The parts of the pieces that have the frame, and those that lack it."""
        pieces = list(outfit.pieces())
        (body_path, body_id), (head_path, head_id) = pieces[:2]
        body_frame = self._body_action(body_path, action).get(str(frame))
        if body_frame is None:
            raise LookupError(f"{body_path} has no frame {action}/{frame}")
        body_frame = body_frame.resolved()
        parts = _canvases(body_frame, body_id, outfit.skin)
        head = self.tree(head_path)
        head_frame = _child(head, action, str(frame)) or _child(head, "front")
        if head_frame is not None:
            parts += [
                p
                for p in _canvases(head_frame, head_id, outfit.skin)
                if p.name == _HEAD
            ]
        flag = body_frame.get("face")
        shows_face = flag is None or flag.resolved().int_value() != 0
        missing: list[int] = []
        for path, item in pieces[2:]:
            try:
                found = self._piece_frame(outfit, path, item, action, frame, shows_face)
                if found is not None:
                    parts += _canvases(found, item, outfit.skin)
            except _Missing:
                missing.append(item)
            except CatalogueError as error:
                _log.info("%s: %s; missing", path, error)
                missing.append(item)
        return parts, tuple(missing)

    def _piece_frame(
        self,
        outfit: Outfit,
        path: str,
        item: int,
        action: str,
        frame: int,
        shows_face: bool,
    ) -> Tree | None:
        """
        A piece's frame node, or `None` when the frame doesn't show it.

        :raises _Missing: It lacks the action.
        :raises CatalogueError: A link on the way names nothing.
        """
        slot = slot_of(item)
        root: Tree | None = self.tree(path)
        if is_cash_weapon(item):
            root = _child(root, str(outfit.weapon_type))
        frames = None if root is None else _child(root, action)
        if frames is not None:
            return _child(frames, str(frame))
        if root is not None and slot in FACE_PIECES:
            return _child(root, "default") if shows_face else None
        if slot in UNSEEN.get(action, frozenset()):
            return None
        raise _Missing

    def _pick(self, rng: np.random.Generator, slot: str) -> int:
        ids = self.pieces(slot)
        if not ids:
            raise LookupError(f"the extract has no {slot}")
        return ids[int(rng.integers(len(ids)))]

    def _maybe(self, rng: np.random.Generator, slot: str) -> int | None:
        """A piece of an optional slot, or `None` with `EMPTY`'s chance."""
        if rng.random() < EMPTY[slot] or not self.pieces(slot):
            return None
        return self._pick(rng, slot)

    def _covers_legs(self, coat: int) -> bool:
        info = self.tree(image_of(coat)).get("info")
        islot = None if info is None else info.optional_text("islot")
        return bool(islot) and LEGS in _codes(islot or "")

    def _miss(self, item: int, why: str) -> None:
        self.misses[item] += 1
        _log.info("%s %s; redrawn", image_of(item), why)

    def _body_action(self, path: str, action: str) -> Tree:
        found = _child(self.tree(path), action)
        if found is None:
            raise LookupError(f"{path} has no action {action!r}")
        return found

    def tree(self, path: str) -> Tree:
        """
        An image's raw tree, such as `Character/Cap/01002000.img`.

        :raises LookupError: The extract has no such image.
        """
        if path in self._trees:
            self._trees.move_to_end(path)
        else:
            row = self._db.execute(
                "SELECT tree FROM images WHERE path = ?", (path,)
            ).fetchone()
            self._trees[path] = (
                None if row is None else Tree.of(path, json.loads(row[0]))
            )
            if len(self._trees) > _TREES:
                self._trees.popitem(last=False)
        found = self._trees[path]
        if found is None:
            raise LookupError(f"the extract has no {path}")
        return found

    def _zmap(self) -> dict[str, int]:
        """Each layer's place, the front first."""
        if self._order is None:
            layers = self.tree("Base/zmap.img").expect("property").children()
            self._order = {name: index for index, (name, _) in enumerate(layers)}
        return self._order

    def _smap(self) -> dict[str, frozenset[str]]:
        """Each layer's slot codes."""
        if self._codes is None:
            found: dict[str, frozenset[str]] = {}
            smap = self.tree("Base/smap.img").expect("property")
            for name, node in smap.children():
                found[name] = (
                    frozenset() if node.value is None else _codes(node.str_value())
                )
            self._codes = found
        return self._codes

    def _vslots(self, outfit: Outfit) -> dict[int, frozenset[str]]:
        """Each piece's `info/vslot` codes, for those that have one."""
        found: dict[int, frozenset[str]] = {}
        for path, item in outfit.pieces():
            info = self.tree(path).get("info")
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
        found = _child(self.tree("UI/NameTag.img"), str(style))
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


def coverage(wardrobe: Wardrobe, rng: np.random.Generator, outfits: int) -> Coverage:
    """
    Composes `outfits` outfits drawn by `wardrobe.outfit`, each in every one
    of its poses and every frame, and groups the failures by item: a
    `MissingFrame` as `no frame <action>`, a `PartError` by its reason.
    """
    tried = composed = 0
    failures: dict[int, Counter[str]] = {}
    for _ in range(outfits):
        outfit = wardrobe.outfit(rng)
        for action in outfit.poses():
            for frame in range(wardrobe.frames(outfit, action)):
                tried += 1
                try:
                    wardrobe.compose(outfit, action, frame)
                except MissingFrame as error:
                    for item in error.items:
                        failures.setdefault(item, Counter())[f"no frame {action}"] += 1
                except PartError as error:
                    for item in error.items:
                        failures.setdefault(item, Counter())[error.reason] += 1
                else:
                    composed += 1
    return Coverage(tried, composed, failures)


def summary(found: Coverage) -> str:
    """`coverage`'s result as text: the share, then each failing item."""
    lines = [
        f"{found.composed} of {found.tried} frames composed ({found.share:.1%})",
    ]
    ranked = sorted(found.failures.items(), key=lambda kv: -sum(kv[1].values()))
    for item, reasons in ranked:
        why = "; ".join(f"{reason} x{n}" for reason, n in reasons.most_common())
        lines.append(f"  {item} ({slot_of(item)}): {why}")
    return "\n".join(lines)


def anchor(parts: list[Part]) -> list[tuple[Part, tuple[int, int]]]:
    """
    Where each part's origin goes, from the feet: the body's `body` at
    `(0, 0)`, and the body's parts that hold a `handMove` (its `lHand`) too,
    then each part at the first of its anchors already known.

    :returns: The parts placed, in the order given.
    :raises PartError: There is no `body` part, or a part has no anchor that
        any placed part holds.
    """
    bodies = [part for part in parts if part.name == _ROOT]
    if not bodies:
        reason = "the frame has no body part to anchor the others to"
        raise PartError((), reason, reason)
    roots = [bodies[0]] + [
        part
        for part in parts
        if part.item == bodies[0].item
        and _HAND in part.anchors
        and part is not bodies[0]
    ]
    known: dict[str, tuple[int, int]] = {}
    at: dict[int, tuple[int, int]] = {}
    for root in roots:
        at[id(root)] = (0, 0)
        for name, point in root.anchors.items():
            known.setdefault(name, point)
    pending = [part for part in parts if id(part) not in at]
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
            raise PartError(
                tuple(dict.fromkeys(p.item for p in left)),
                "can't anchor "
                + ", ".join(f"{p.name} {sorted(p.anchors)}" for p in left),
                f"these parts share no anchor with the rest: {names}",
            )
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
