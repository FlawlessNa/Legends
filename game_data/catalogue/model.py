"""
What the catalogue's lookups return: frozen dataclasses, in virtual
coordinates, with nothing of SQL or of the client's tree in them.

`docs/agents/game-data.md` says what each table's columns mean; these carry the
same values under the same names.
"""

from dataclasses import dataclass, field

from game_data.extraction import Json


@dataclass(frozen=True, slots=True)
class Ref:
    """
    Something `search` found.

    :ivar kind: `map`, `mob` or `skill`.
    :ivar id: Its ID.
    :ivar name: Its fullest name, which a lookup accepts: for a map,
        `street: map name`. `None` when the client names it nowhere.
    """

    kind: str
    id: int
    name: str | None


@dataclass(frozen=True, slots=True)
class MapRef:
    """
    A map some mob spawns on.

    :ivar name: `street: map name`; `None` when the client names it nowhere.
    :ivar spawns: How many times the mob is placed on it.
    """

    id: int
    name: str | None
    spawns: int


@dataclass(frozen=True, slots=True)
class Bounds:
    """A map's VR bounds: the box the camera stays in."""

    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class Minimap:
    """
    How a map's minimap relates to its virtual coordinates, as `miniMap`
    gives it.

    :ivar center_x: Added to a virtual x to measure it from the minimap's left.
    :ivar center_y: Likewise for y, from its top.
    :ivar mag: The minimap is scaled down by `2**mag`.
    :ivar width: The minimap's extent, in virtual pixels.
    :ivar height: Likewise.
    """

    center_x: int
    center_y: int
    mag: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class Foothold:
    """
    One foothold segment.

    :ivar source: `map`, or `object` or `tile` for one drawn on a layer item.
    :ivar layer: `None` unless the map's own.
    :ivar group: Likewise.
    :ivar id: The map's foothold ID; a running number for the others.
    :ivar prev: `None` unless the map's own; 0 for none.
    :ivar next: Likewise.
    """

    source: str
    layer: int | None
    group: int | None
    id: int
    x1: int
    y1: int
    x2: int
    y2: int
    prev: int | None
    next: int | None


@dataclass(frozen=True, slots=True)
class Rope:
    """
    A rope or ladder: the vertical line at `x` from `y1` to `y2`.

    :ivar source: `map` or `object`.
    :ivar ladder: `None` unless the map's own; likewise the last two.
    :ivar usable_from_foothold: Whether it can be climbed off at its top.
    :ivar page: The depth the character is drawn at while on it.
    """

    source: str
    id: int
    x: int
    y1: int
    y2: int
    ladder: bool | None
    usable_from_foothold: bool | None
    page: int | None


@dataclass(frozen=True, slots=True)
class Portal:
    """
    :ivar target_map: `None` when it leads to no other map.
    :ivar target_portal: `None` when it names none.
    """

    name: str
    type: int
    x: int
    y: int
    target_map: int | None
    target_portal: str | None


@dataclass(frozen=True, slots=True)
class Spawn:
    """
    A mob or NPC placed on the map.

    :ivar kind: `mob` or `npc`.
    :ivar id: The mob's or NPC's ID.
    :ivar name: Its name, from the client's strings; `None` if it has none.
    :ivar cy: The y of the foothold it stands on.
    :ivar rx0: The left of the range it moves in.
    :ivar rx1: The right.
    :ivar respawn_time: `None` when the map doesn't set one.
    """

    kind: str
    id: int
    name: str | None
    x: int
    cy: int
    foothold: int
    rx0: int
    rx1: int
    respawn_time: int | None
    flip: bool
    hidden: bool


@dataclass(frozen=True, slots=True)
class Background:
    """A background's parallax and tiling, as the map gives them."""

    type: int
    rx: int
    ry: int
    cx: int
    cy: int
    a: int
    front: bool


@dataclass(frozen=True, slots=True)
class LayerFrame:
    """
    One frame of a layer item.

    :ivar image: Its image in the image store; `None` when its pixels
        couldn't be found.
    :ivar delay: In milliseconds; `None` when the frame doesn't set one.
    """

    frame: int
    image: str | None
    origin_x: int
    origin_y: int
    delay: int | None


@dataclass(frozen=True, slots=True)
class MapLayer:
    """
    A tile, object or background, at its raw position: drawing it at `(x, y)`
    puts the frame's origin there.

    :ivar kind: `tile`, `object` or `back`.
    :ivar layer: 0 to 7; `None` for a background.
    :ivar z: The order within its layer: an object's `z`, a tile's canvas `z`,
        a background's number.
    :ivar zm: The map's `zM` for a tile or object; `None` for a background.
    :ivar asset: The node it's drawn from, such as
        `Map/Tile/tile_x.img/bsc/0`; `None` for a background with no image.
    :ivar background: `None` unless a background.
    """

    kind: str
    layer: int | None
    z: int
    zm: int | None
    x: int
    y: int
    flip: bool
    asset: str | None
    frames: tuple[LayerFrame, ...]
    background: Background | None


@dataclass(frozen=True, slots=True)
class MapData:
    """
    One map: its bounds, flags and geometry.

    :ivar name: `None` when the client's strings don't name it; so is
        `street`.
    :ivar vr_derived: Whether the map lacks VR bounds, so `vr` is the extent
        of its footholds.
    :ivar minimap: `None` when the map has no minimap.
    :ivar return_map: `None` when the map names none.
    """

    id: int
    name: str | None
    street: str | None
    vr: Bounds
    vr_derived: bool
    minimap: Minimap | None
    town: bool
    swim: bool
    fly: bool
    field_limit: int
    bgm: str | None
    return_map: int | None
    footholds: tuple[Foothold, ...]
    ropes: tuple[Rope, ...]
    portals: tuple[Portal, ...]
    spawns: tuple[Spawn, ...]


@dataclass(frozen=True, slots=True)
class MobFrame:
    """
    One frame of a mob's action, relative to the mob's position: the origin
    is the pixel drawn there.

    :ivar image: Its image in the image store; `None` when its pixels
        couldn't be found.
    :ivar lt_x: The body hitbox's top left, `lt`; `None` when the frame has
        none, as are the other hitbox and head values.
    :ivar rb_x: The body hitbox's bottom right, `rb`.
    :ivar head_x: Where the head is, `head`.
    :ivar delay: In milliseconds; `None` when the frame doesn't set one.
    """

    action: str
    frame: int
    image: str | None
    origin_x: int
    origin_y: int
    lt_x: int | None
    lt_y: int | None
    rb_x: int | None
    rb_y: int | None
    head_x: int | None
    head_y: int | None
    delay: int | None


@dataclass(frozen=True, slots=True)
class MobData:
    """
    One mob: its stats and every frame of every action.

    :ivar name: `None` when the client's strings don't name it.
    :ivar link: The mob whose sprites it shares, whose frames `frames` are;
        `None` when it has its own.
    :ivar speed: `None` when the client doesn't say; so are `fly_speed` and
        `exp`.
    :ivar pa_damage: `PADamage`, its physical attack: what touching it does
        when `body_attack`.
    :ivar elem_attr: Its elements, as the client writes them (`elemAttr`);
        `None` when it has none.
    """

    id: int
    name: str | None
    link: int | None
    level: int
    max_hp: int
    max_mp: int
    speed: int | None
    fly_speed: int | None
    exp: int | None
    pa_damage: int
    ma_damage: int
    pd_damage: int
    md_damage: int
    acc: int
    eva: int
    pushed: int
    body_attack: bool
    boss: bool
    undead: bool
    first_attack: bool
    elem_attr: str | None
    frames: tuple[MobFrame, ...]


@dataclass(frozen=True, slots=True)
class SkillLevel:
    """
    One level of a skill. The fields the skill sets at every level (its
    `common`) are here at each.

    :ivar skill: The skill's ID.
    :ivar actions: The character actions the skill plays.
    :ivar mp_con: `mpCon`, its MP cost; `None` when the level doesn't say, as
        for every value but `other`.
    :ivar time: How long it lasts, in seconds.
    :ivar lt_x: The area it reaches is `lt` to `rb`, relative to the
        character.
    :ivar mob_count: How many mobs it hits, `mobCount`.
    :ivar attack_count: How many times it hits each, `attackCount`.
    :ivar range: `range`.
    :ivar cooltime: Its cooldown, in seconds.
    :ivar other: Every other field, by its name in the client, such as `mad`
        or `x`.
    """

    skill: int
    level: int
    actions: tuple[str, ...]
    mp_con: int | None
    time: int | None
    lt_x: int | None
    lt_y: int | None
    rb_x: int | None
    rb_y: int | None
    mob_count: int | None
    attack_count: int | None
    range: int | None
    cooltime: int | None
    other: dict[str, Json] = field(hash=False)


@dataclass(frozen=True, slots=True)
class SkillData:
    """
    One skill, with every level.

    :ivar job: The job whose skill it is, such as 200 for a magician's.
    :ivar name: `None` when the client's strings don't name it; so is
        `description`.
    :ivar type: Its `info/type`; `None` when it has none.
    :ivar actions: The character actions it plays, in order.
    :ivar icon: Its icon in the image store; `None` when it has none.
    """

    id: int
    job: int
    name: str | None
    description: str | None
    type: int | None
    max_level: int
    actions: tuple[str, ...]
    icon: str | None
    levels: tuple[SkillLevel, ...]

    def level(self, level: int) -> SkillLevel:
        """
        One of its levels.

        :raises LookupError: It has no such level.
        """
        for found in self.levels:
            if found.level == level:
                return found
        raise LookupError(
            f"{self.name or self.id} has no level {level}; it has 1 to {self.max_level}"
            if self.max_level
            else f"{self.name or self.id} has no levels"
        )
