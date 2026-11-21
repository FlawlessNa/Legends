"""
`game_data.scenes.players`: characters drawn and composed from a synthetic
client.

`write_players_client` writes a client whose parts are blocks of one colour
each, so where a colour lands says where its part was anchored. In the feet's
coordinates (the body's origin at `(0, 0)`):

- the body, 4x4, gives `navel` at `(0, -2)` and `neck` at `(0, -4)`;
- the arm hangs from the `navel` and gives `hand` at `(4, -1)`, which the
  weapon hangs from: anchors found through another part;
- the head hangs from the `neck` and gives `brow` at `(0, -8)`, which the
  face, the hair, the cap and the face accessory hang from;
- the coat's `mail` covers the body's middle and the arm's left column:
  `mailChest` is in front of `body` in `Base/zmap.img`, and behind `arm`,
  though the arm is read before it;
- the cap's `vslot` is `CpH1`, and the hair's `hairOverHead` is `H1` in
  `Base/smap.img`, so the cap hides it. The hood's `vslot` also covers the
  head's `Hd`, so it hides the head, whose `brow` the face still hangs from;
- the hair's `hairShade` has one canvas per skin, `0` and `1`; every skin's
  body and head are skin `0`'s.

The body has every pose of `PLAYER_ACTIONS`, one frame each linking to
`stand1/0`, but `walk1`, which has two, and `ladder` and `rope`, whose frame
is the body alone with the face hidden (`face` 0). Every piece but the face
and the face accessory has every pose, frame `0` only, linking to its
`stand1/0`, with these gaps:

- the weapons and the shield have no `ladder` or `rope` (`UNSEEN`);
- the overall (`Longcoat`, `islot` `MaPn`) has no `alert`;
- the face accessory has only a `default`;
- the odd cap's part has a `z` that `Base/zmap.img` lacks;
- the cash weapon holds its frames under types `30` (`hand` at `(-2, 0)`,
  like the regular weapon) and `40` (`hand` at `(-3, 0)`), and `49`, a type
  no player wields; the broken cash weapon only under `49`;
- weapon `1392000` is of type 39, which no player wields.

`Character/Cap/_Canvas/` holds a cap, which isn't a piece.

`UI/NameTag.img` has one style, `3`: red west, green centre and blue east
pieces, black text.
"""

import logging
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from game_data.catalogue import Catalogue, CatalogueError, build_catalogue
from game_data.extraction import extract
from game_data.scenes.players import (
    MOVES,
    PLAYER_ACTIONS,
    SLOTS,
    TAG_BACKGROUND,
    TAG_GAP,
    TAG_HEIGHT,
    WEAPON_TYPES,
    Look,
    MissingFrame,
    Outfit,
    Part,
    PartError,
    Player,
    Wardrobe,
    anchor,
    coverage,
    image_of,
    slot_of,
)
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_render import Rgba, origin, solid

BODY: Rgba = (200, 0, 0, 255)
ARM: Rgba = (0, 200, 0, 255)
WEAPON: Rgba = (200, 200, 0, 255)
HEAD: Rgba = (0, 0, 200, 255)
FACE: Rgba = (255, 255, 255, 255)
HAIR: Rgba = (10, 10, 10, 255)
OVER_HEAD: Rgba = (20, 20, 20, 255)
SHADE_0: Rgba = (30, 30, 30, 255)
SHADE_1: Rgba = (40, 40, 40, 255)
CAP: Rgba = (200, 0, 200, 255)
MAIL: Rgba = (0, 200, 200, 255)
CASH_30: Rgba = (250, 150, 0, 255)
CASH_40: Rgba = (150, 250, 0, 255)
FACE_ACC: Rgba = (100, 0, 100, 255)
OVERALL: Rgba = (0, 100, 100, 255)
SHIELD: Rgba = (100, 100, 0, 255)
OTHER: Rgba = (90, 90, 90, 255)
WEST: Rgba = (255, 0, 0, 255)
CENTRE: Rgba = (0, 255, 0, 255)
EAST: Rgba = (0, 0, 255, 255)

ZMAP = [
    "shield",
    "weapon",
    "accessoryFace",
    "hairOverHead",
    "cap",
    "hair",
    "face",
    "hairShade",
    "head",
    "arm",
    "glove",
    "mailChest",
    "pants",
    "shoes",
    "body",
    "cape",
]
SMAP = {"hairOverHead": "H1", "hair": "H2", "cap": "CpH1", "head": "Hd"}

FACE_ID, HAIR_ID, CAP_ID, COAT_ID, WEAPON_ID = 20000, 30000, 1002000, 1040000, 1302000
HOOD_ID, ODD_CAP_ID, FACE_ACC_ID, OVERALL_ID = 1002001, 1002002, 1010000, 1050000
PANTS_ID, SHOES_ID, GLOVE_ID = 1060000, 1070000, 1080000
SHIELD_ID, CAPE_ID = 1092000, 1102000
CASH_ID, BROKEN_CASH_ID, BARE_HANDS_ID = 1702000, 1702001, 1392000
DRESSED = Outfit(skin=0, face=FACE_ID, hair=HAIR_ID, coat=COAT_ID, weapon=WEAPON_ID)
CLIMBING = frozenset({"ladder", "rope"})


def part(
    name: str,
    size: tuple[int, int],
    colour: Rgba,
    at: tuple[int, int],
    z: str,
    **anchors: tuple[int, int],
) -> w.Canvas:
    """A block of `colour`, origin `at`, its `map` the anchors given."""
    return solid(
        name,
        *size,
        colour,
        origin(*at),
        w.Prop("map", [w.Vector(key, x, y) for key, (x, y) in anchors.items()]),
        w.String("z", z),
    )


def stand(*children: w.Property) -> w.Prop:
    return w.Prop("stand1", [w.Prop("0", list(children))])


def posed(
    *children: w.Canvas | w.Uol, without: frozenset[str] = frozenset()
) -> list[w.Property]:
    """
    `stand1/0` holding `children`, and frame `0` of every other pose of
    `PLAYER_ACTIONS` but those `without`, linking to them.
    """
    found: list[w.Property] = [stand(*children)]
    for action in PLAYER_ACTIONS:
        if action == "stand1" or action in without:
            continue
        links = [w.Uol(c.name, f"../../stand1/0/{c.name}") for c in children]
        found.append(w.Prop(action, [w.Prop("0", list(links))]))
    return found


def body() -> list[w.Property]:
    def torso() -> w.Canvas:
        return part("body", (4, 4), BODY, (2, 4), "body", navel=(0, -2), neck=(0, -4))

    climbing = [w.Prop("0", [torso(), w.Short("face", 0)])]
    return [
        stand(
            torso(),
            part("arm", (2, 2), ARM, (1, 1), "arm", navel=(-3, 0), hand=(1, 1)),
            w.Short("face", 1),
            w.Int("delay", 500),
        ),
        w.Prop(
            "walk1",
            [
                w.Prop(
                    str(n),
                    [
                        w.Uol("body", "../../stand1/0/body"),
                        w.Uol("arm", "../../stand1/0/arm"),
                    ],
                )
                for n in range(2)
            ],
        ),
        *(
            w.Prop(action, climbing)
            if action in CLIMBING
            else w.Prop(action, [w.Uol("0", "../stand1/0")])
            for action in PLAYER_ACTIONS
            if action not in ("stand1", "walk1")
        ),
    ]


def head() -> list[w.Property]:
    return [
        w.Prop(
            "front",
            [part("head", (6, 6), HEAD, (3, 3), "head", neck=(0, 3), brow=(0, -1))],
        ),
        stand(w.Uol("head", "../../front/head")),
    ]


def info(vslot: str, *, cash: bool = False) -> w.Prop:
    return w.Prop(
        "info",
        [w.String("islot", vslot), w.String("vslot", vslot), w.Int("cash", int(cash))],
    )


def hair() -> list[w.Property]:
    def shade(name: str, colour: Rgba) -> w.Canvas:
        return part(name, (1, 1), colour, (0, 0), "hairShade", brow=(2, 2))

    return [
        info("H1H2"),
        w.Prop(
            "default",
            [
                part("hair", (1, 1), HAIR, (0, 0), "hair", brow=(0, 2)),
                part(
                    "hairOverHead",
                    (1, 1),
                    OVER_HEAD,
                    (0, 0),
                    "hairOverHead",
                    brow=(1, 2),
                ),
                w.Prop("hairShade", [shade("0", SHADE_0), shade("1", SHADE_1)]),
            ],
        ),
        *posed(
            w.Uol("hair", "../../default/hair"),
            w.Uol("hairOverHead", "../../default/hairOverHead"),
            w.Uol("hairShade", "../../default/hairShade"),
        ),
    ]


def cap(vslot: str, z: str = "cap") -> list[w.Property]:
    return [
        info(vslot),
        w.Prop("default", [part("default", (1, 1), CAP, (0, 0), z, brow=(-2, 2))]),
        *posed(w.Uol("default", "../../default/default")),
    ]


def weapon(colour: Rgba, hand: tuple[int, int]) -> list[w.Property]:
    """A weapon's poses: one block hanging from the hand, none climbing."""
    return posed(
        part("weapon", (1, 1), colour, (0, 0), "weapon", hand=hand), without=CLIMBING
    )


def worn(slot: str, z: str, colour: Rgba = OTHER) -> list[w.Property]:
    """A piece of one block 3 pixels left of the navel, in every pose."""
    return [info(slot), *posed(part(z, (1, 1), colour, (0, 0), z, navel=(3, 0)))]


def name_tag() -> list[w.Property]:
    return [
        w.Prop(
            "3",
            [
                solid("w", 2, 3, WEST, origin(2, 1)),
                solid("c", 1, 3, CENTRE, origin(0, 1)),
                solid("e", 2, 3, EAST, origin(0, 1)),
                w.Int("clr", -16777216),
            ],
        )
    ]


def write_players_client(data: Path) -> Path:
    """The client described above, in `data`."""
    w.write_tree(
        data / "Base",
        [
            w.Img("zmap.img", [w.Null(name) for name in ZMAP]),
            w.Img(
                "smap.img",
                [
                    w.String(name, SMAP[name]) if name in SMAP else w.Null(name)
                    for name in ZMAP
                ],
            ),
        ],
        ini=False,
    )
    face = [
        w.Prop("default", [part("face", (2, 1), FACE, (1, 0), "face", brow=(0, -1))])
    ]
    face_accessory = [
        info("Af"),
        w.Prop(
            "default",
            [part("default", (1, 1), FACE_ACC, (0, 0), "accessoryFace", brow=(3, 0))],
        ),
    ]
    coat = [
        info("Ma"),
        *posed(part("mail", (4, 2), MAIL, (1, 1), "mailChest", navel=(0, 0))),
    ]
    overall = [
        info("MaPn"),
        *posed(
            part("mail", (4, 2), OVERALL, (1, 1), "mailChest", navel=(0, 0)),
            without=frozenset({"alert"}),
        ),
    ]
    shield = [
        info("Si"),
        *posed(
            part("shield", (1, 1), SHIELD, (0, 0), "shield", navel=(3, 0)),
            without=CLIMBING,
        ),
    ]
    cash = [
        info("Wp", cash=True),
        w.Prop("30", weapon(CASH_30, (-2, 0))),
        w.Prop("40", weapon(CASH_40, (-3, 0))),
        w.Prop("49", weapon(OTHER, (-2, 0))),
    ]
    broken_cash = [info("Wp", cash=True), w.Prop("49", weapon(OTHER, (-2, 0)))]
    bodies = [
        w.Img(f"{prefix + skin:08d}.img", build())
        for skin in range(5)
        for prefix, build in ((2000, body), (12000, head))
    ]
    weapons = [
        w.Img(f"{WEAPON_ID:08d}.img", [info("Wp"), *weapon(WEAPON, (-2, 0))]),
        w.Img(f"{CASH_ID:08d}.img", cash),
        w.Img(f"{BROKEN_CASH_ID:08d}.img", broken_cash),
        w.Img(f"{BARE_HANDS_ID:08d}.img", [info("Wp"), *weapon(OTHER, (-2, 0))]),
    ]
    w.write_tree(
        data / "Character",
        [
            *bodies,
            w.Dir("Face", [w.Img(f"{FACE_ID:08d}.img", face)]),
            w.Dir("Hair", [w.Img(f"{HAIR_ID:08d}.img", hair())]),
            w.Dir(
                "Cap",
                [
                    w.Img(f"{CAP_ID:08d}.img", cap("CpH1")),
                    w.Img(f"{HOOD_ID:08d}.img", cap("CpH1Hd")),
                    w.Img(f"{ODD_CAP_ID:08d}.img", cap("Cp", "capBelowHead")),
                    w.Dir("_Canvas", [w.Img("01002003.img", cap("Cp"))]),
                ],
            ),
            w.Dir("Accessory", [w.Img(f"{FACE_ACC_ID:08d}.img", face_accessory)]),
            w.Dir("Coat", [w.Img(f"{COAT_ID:08d}.img", coat)]),
            w.Dir("Longcoat", [w.Img(f"{OVERALL_ID:08d}.img", overall)]),
            w.Dir("Pants", [w.Img(f"{PANTS_ID:08d}.img", worn("Pn", "pants"))]),
            w.Dir("Shoes", [w.Img(f"{SHOES_ID:08d}.img", worn("So", "shoes"))]),
            w.Dir("Glove", [w.Img(f"{GLOVE_ID:08d}.img", worn("Gv", "glove"))]),
            w.Dir("Cape", [w.Img(f"{CAPE_ID:08d}.img", worn("Sr", "cape"))]),
            w.Dir("Shield", [w.Img(f"{SHIELD_ID:08d}.img", shield)]),
            w.Dir("Weapon", weapons),
        ],
        ini=False,
    )
    w.write_tree(data / "UI", [w.Img("NameTag.img", name_tag())], ini=False)
    return data


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("players")
    root = base / "store"
    extract(write_players_client(base / "Data"), root, catalogue=build_catalogue)
    return root


@pytest.fixture
def wardrobe(root: Path) -> Iterator[Wardrobe]:
    with Catalogue.latest(root) as cat, Wardrobe(cat) as found:
        yield found


def where(player: Player, colour: Rgba) -> set[tuple[int, int]]:
    """The pixels of exactly `colour`, from the feet."""
    ox, oy = player.origin
    found = np.argwhere((player.pixels == np.array(colour, dtype=np.uint8)).all(-1))
    return {(int(x) - ox, int(y) - oy) for y, x in found}


def block(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    """The pixels from `(x0, y0)` to `(x1, y1)`, both included."""
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


# --- anchoring ---------------------------------------------------------------


def test_the_body_stands_its_origin_on_the_feet(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(Outfit(), "stand1", 0)
    assert where(player, BODY) == block(-2, -4, 1, -1)


def test_the_head_hangs_from_the_bodys_neck(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(Outfit(), "stand1", 0)
    assert where(player, HEAD) == block(-3, -10, 2, -5)


def test_the_weapon_hangs_from_the_hand_the_arm_gives(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0)
    assert where(player, ARM) == block(2, -3, 3, -2)
    assert where(player, WEAPON) == {(6, -1)}


def test_face_hair_and_cap_hang_from_the_heads_brow(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0)
    assert where(player, FACE) == {(-1, -7), (0, -7)}
    assert where(player, HAIR) == {(0, -10)}
    assert where(player, OVER_HEAD) == {(-1, -10)}
    capped = wardrobe.compose(replace(DRESSED, cap=CAP_ID), "stand1", 0)
    assert where(capped, CAP) == {(2, -10)}


def test_a_part_held_per_skin_is_the_skins(wardrobe: Wardrobe) -> None:
    light = wardrobe.compose(DRESSED, "stand1", 0)
    tanned = wardrobe.compose(replace(DRESSED, skin=1), "stand1", 0)
    assert where(light, SHADE_0) == {(-2, -10)}
    assert where(tanned, SHADE_1) == {(-2, -10)}
    assert not where(tanned, SHADE_0)


def test_anchors_are_found_whatever_the_parts_order() -> None:
    body = Part("body", 1, "b", (0, 0), "body", {"navel": (0, -2)})
    arm = Part("arm", 1, "a", (0, 0), "arm", {"navel": (-3, 0), "hand": (1, 1)})
    weapon = Part("weapon", 2, "w", (0, 0), "weapon", {"hand": (-2, 0)})
    placed = {p.name: at for p, at in anchor([weapon, arm, body])}
    assert placed == {"body": (0, 0), "arm": (3, -2), "weapon": (6, -1)}


def test_the_bodys_hand_held_by_hand_move_stands_on_the_feet() -> None:
    body = Part("body", 1, "b", (0, 0), "body", {"navel": (0, -2)})
    hand = Part("lHand", 1, "h", (0, 0), "hand", {"handMove": (-3, -5)})
    glove = Part("lGlove", 2, "g", (0, 0), "glove", {"handMove": (1, 1)})
    placed = {p.name: at for p, at in anchor([glove, hand, body])}
    assert placed == {"body": (0, 0), "lHand": (0, 0), "lGlove": (-4, -6)}


def test_a_part_sharing_no_anchor_raises_naming_it() -> None:
    body = Part("body", 1, "b", (0, 0), "body", {"navel": (0, -2)})
    stray = Part("cape", 7, "c", (0, 0), "cape", {"tail": (0, 0)})
    with pytest.raises(PartError, match="7/cape") as error:
        anchor([body, stray])
    assert error.value.items == (7,)
    assert isinstance(error.value, CatalogueError)


def test_a_frame_without_a_body_raises() -> None:
    with pytest.raises(CatalogueError, match="no body part"):
        anchor([Part("arm", 1, "a", (0, 0), "arm", {"navel": (0, 0)})])


# --- layers, hiding, flipping --------------------------------------------------


def test_parts_are_drawn_back_to_front_by_zmap(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0)
    assert where(player, MAIL) == block(-1, -3, 1, -2)
    assert where(player, BODY) == block(-2, -4, 1, -1) - block(-1, -3, 1, -2)
    assert where(player, ARM) == block(2, -3, 3, -2)


def test_a_cap_hides_the_hair_its_vslot_covers(wardrobe: Wardrobe) -> None:
    capped = wardrobe.compose(replace(DRESSED, cap=CAP_ID), "stand1", 0)
    assert not where(capped, OVER_HEAD)
    assert where(capped, HAIR) == {(0, -10)}


def test_a_hidden_part_still_gives_its_anchors(wardrobe: Wardrobe) -> None:
    hooded = wardrobe.compose(replace(DRESSED, cap=HOOD_ID), "stand1", 0)
    assert not where(hooded, HEAD)
    assert where(hooded, FACE) == {(-1, -7), (0, -7)}
    assert where(hooded, CAP) == {(2, -10)}


def test_a_z_the_zmap_lacks_raises_naming_the_item(wardrobe: Wardrobe) -> None:
    with pytest.raises(PartError, match="capBelowHead") as error:
        wardrobe.compose(replace(DRESSED, cap=ODD_CAP_ID), "stand1", 0)
    assert error.value.items == (ODD_CAP_ID,)


def test_flipping_mirrors_the_character_about_its_feet(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0, flip=True)
    assert where(player, WEAPON) == {(-7, -1)}
    assert where(player, ARM) == block(-4, -3, -3, -2)
    assert where(player, MAIL) == block(-2, -3, 0, -2)


def test_the_box_bounds_the_character_without_its_tag(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0, name="Abc")
    ox, oy = player.origin
    assert player.box == (ox - 3, oy - 10, ox + 7, oy)


def test_frames_counts_the_bodys_frames(wardrobe: Wardrobe) -> None:
    assert wardrobe.frames(Outfit(), "stand1") == 1
    assert wardrobe.frames(Outfit(), "walk1") == 2


def test_missing_pieces_and_frames_raise_lookup_error(wardrobe: Wardrobe) -> None:
    with pytest.raises(LookupError, match="Character/Shoes/01072001.img"):
        wardrobe.compose(Outfit(shoes=1072001), "stand1", 0)
    with pytest.raises(LookupError, match="no action 'fly'"):
        wardrobe.compose(Outfit(), "fly", 0)
    with pytest.raises(LookupError, match="no frame stand1/5"):
        wardrobe.compose(Outfit(), "stand1", 5)


def test_a_piece_with_the_pose_but_not_the_frame_shows_nothing_in_it(
    wardrobe: Wardrobe,
) -> None:
    player = wardrobe.compose(DRESSED, "walk1", 1)
    assert not where(player, WEAPON)
    assert where(player, BODY)


def test_a_piece_lacking_the_pose_raises_missing_frame(wardrobe: Wardrobe) -> None:
    with pytest.raises(MissingFrame, match=str(OVERALL_ID)) as error:
        wardrobe.compose(replace(DRESSED, coat=OVERALL_ID), "alert", 0)
    assert error.value.items == (OVERALL_ID,)
    assert isinstance(error.value, LookupError)


def test_a_climber_shows_neither_weapon_shield_nor_face(wardrobe: Wardrobe) -> None:
    outfit = replace(DRESSED, face_accessory=FACE_ACC_ID, shield=SHIELD_ID)
    for action in CLIMBING:
        player = wardrobe.compose(outfit, action, 0)
        assert where(player, HAIR)
        for hidden in (WEAPON, SHIELD, FACE, FACE_ACC, ARM):
            assert not where(player, hidden)


def test_a_face_accessory_wears_its_default_in_any_pose(wardrobe: Wardrobe) -> None:
    outfit = replace(DRESSED, face_accessory=FACE_ACC_ID)
    for action in ("stand1", "alert", "swingO1"):
        assert where(wardrobe.compose(outfit, action, 0), FACE_ACC) == {(-3, -8)}


def test_a_cash_weapon_takes_its_frames_from_its_weapon_type(
    wardrobe: Wardrobe,
) -> None:
    as_sword = replace(DRESSED, weapon=CASH_ID, weapon_type=30)
    as_two_handed = replace(DRESSED, weapon=CASH_ID, weapon_type=40)
    sword = wardrobe.compose(as_sword, "stand1", 0)
    two_handed = wardrobe.compose(as_two_handed, "stand2", 0)
    assert where(sword, CASH_30) == {(6, -1)}
    assert not where(sword, CASH_40)
    assert where(two_handed, CASH_40) == {(7, -1)}
    assert not where(two_handed, CASH_30)


# --- name tags --------------------------------------------------------------


def test_the_plain_tag_is_a_box_centred_under_the_feet(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0, name="Abc")
    assert player.tag is not None
    x1, y1, x2, y2 = player.tag
    ox, oy = player.origin
    assert y1 == oy + TAG_GAP
    assert y2 - y1 == TAG_HEIGHT
    assert abs((x1 + x2) / 2 - ox) <= 1
    assert tuple(player.pixels[y1, x1]) == TAG_BACKGROUND
    text = player.pixels[y1:y2, x1:x2]
    assert (text[..., :3] == 255).all(-1).any()


def test_a_styled_tag_lays_its_pieces_around_the_text(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "stand1", 0, name="Abc", tag=3)
    assert player.tag is not None
    x1, y1, x2, _ = player.tag
    assert y1 == player.origin[1] + TAG_GAP
    row = [tuple(int(v) for v in pixel) for pixel in player.pixels[y1, x1:x2]]
    width = len(row) - 4
    assert width > 0
    assert row == [WEST] * 2 + [CENTRE] * width + [EAST] * 2
    assert (player.pixels[..., :3] == 0).all(-1).any()


def test_an_unknown_tag_style_raises(wardrobe: Wardrobe) -> None:
    with pytest.raises(LookupError, match="no style 99"):
        wardrobe.compose(DRESSED, "stand1", 0, name="Abc", tag=99)


# --- outfits ----------------------------------------------------------------


def test_each_slot_holds_its_folders_items_by_prefix(wardrobe: Wardrobe) -> None:
    assert wardrobe.pieces("face") == (FACE_ID,)
    assert wardrobe.pieces("hair") == (HAIR_ID,)
    assert wardrobe.pieces("cap") == (CAP_ID, HOOD_ID, ODD_CAP_ID)
    assert wardrobe.pieces("face_accessory") == (FACE_ACC_ID,)
    assert wardrobe.pieces("eye_accessory") == ()
    assert wardrobe.pieces("coat") == (COAT_ID, OVERALL_ID)
    assert wardrobe.pieces("shield") == (SHIELD_ID,)
    assert wardrobe.pieces("weapon") == (WEAPON_ID, CASH_ID, BROKEN_CASH_ID)
    for slot in ("face", "hair", *SLOTS):
        for item in wardrobe.pieces(slot):
            assert slot_of(item) == slot


def test_a_cash_weapon_is_worn_as_the_types_it_has_frames_of(
    wardrobe: Wardrobe,
) -> None:
    assert wardrobe.weapon_types(WEAPON_ID) == (30,)
    assert wardrobe.weapon_types(CASH_ID) == (30, 40)
    assert wardrobe.weapon_types(BROKEN_CASH_ID) == ()


def test_the_weapon_type_picks_the_stance_and_the_attacks() -> None:
    assert Outfit(weapon=1302000).poses()[:2] == ("stand1", "walk1")
    assert Outfit(weapon=1402000).poses()[:2] == ("stand2", "walk1")
    assert Outfit(weapon=1412000).poses()[:2] == ("stand2", "walk2")
    spear = Outfit(weapon=CASH_ID, weapon_type=43).poses()
    assert spear == ("stand2", "walk2", *MOVES, *WEAPON_TYPES[43].attacks)
    assert Outfit().poses() == ("stand1", "walk1", *MOVES)
    for kind in WEAPON_TYPES:
        poses = Outfit(weapon=CASH_ID, weapon_type=kind).poses()
        assert set(poses) <= set(PLAYER_ACTIONS)
    with pytest.raises(LookupError, match="weapon_type"):
        Outfit(weapon=CASH_ID).poses()


def drawn(wardrobe: Wardrobe, seed: int, n: int = 200) -> list[Outfit]:
    rng = np.random.default_rng(seed)
    return [wardrobe.outfit(rng) for _ in range(n)]


def test_a_drawn_outfit_depends_only_on_the_seed(wardrobe: Wardrobe) -> None:
    assert drawn(wardrobe, 1, 30) == drawn(wardrobe, 1, 30)
    assert drawn(wardrobe, 1, 30) != drawn(wardrobe, 2, 30)


def test_an_outfit_fills_each_slot_from_its_pieces(wardrobe: Wardrobe) -> None:
    outfits = drawn(wardrobe, 3)
    for outfit in outfits:
        for slot in ("face", "hair", *SLOTS):
            item = getattr(outfit, slot)
            assert item is None or item in wardrobe.pieces(slot)
        for slot in ("face", "hair", "coat", "shoes"):
            assert getattr(outfit, slot) is not None
        assert outfit.weapon is not None
        assert outfit.weapon_type in wardrobe.weapon_types(outfit.weapon)
    for slot in ("cap", "face_accessory", "glove", "cape", "shield"):
        assert {getattr(o, slot) is None for o in outfits} == {True, False}


def test_an_overall_goes_without_pants(wardrobe: Wardrobe) -> None:
    outfits = drawn(wardrobe, 4)
    assert {o.coat for o in outfits} == {COAT_ID, OVERALL_ID}
    for outfit in outfits:
        assert (outfit.pants is None) == (outfit.coat == OVERALL_ID)


def test_a_shield_is_worn_with_a_one_handed_weapon_only(wardrobe: Wardrobe) -> None:
    outfits = drawn(wardrobe, 5)
    assert {o.weapon_type for o in outfits} == {30, 40}
    assert any(o.shield for o in outfits)
    assert all(o.shield is None for o in outfits if o.weapon_type == 40)


# --- drawing players ----------------------------------------------------------


def looks(wardrobe: Wardrobe, seed: int, n: int = 150) -> list[Look]:
    rng = np.random.default_rng(seed)
    return [wardrobe.draw(rng) for _ in range(n)]


def test_a_drawn_player_depends_only_on_the_seed(wardrobe: Wardrobe) -> None:
    assert looks(wardrobe, 1, 30) == looks(wardrobe, 1, 30)
    assert looks(wardrobe, 1, 30) != looks(wardrobe, 2, 30)


def test_a_drawn_player_composes_in_one_of_its_poses(wardrobe: Wardrobe) -> None:
    found = looks(wardrobe, 6)
    for look in found:
        assert look.action in look.outfit.poses()
        assert 0 <= look.frame < wardrobe.frames(look.outfit, look.action)
        wardrobe.compose(look.outfit, look.action, look.frame, flip=look.flip)
    assert {look.action for look in found} >= {"stand1", "stand2", "ladder"}
    assert {look.flip for look in found} == {True, False}


def test_what_lacks_the_pose_is_redrawn_and_counted_by_item(
    wardrobe: Wardrobe, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="game_data.scenes.players"):
        found = looks(wardrobe, 7)
    assert not any(
        look.outfit.coat == OVERALL_ID and look.action == "alert" for look in found
    )
    for look in found:
        if look.outfit.cap == ODD_CAP_ID:
            assert (look.action, look.frame) == ("walk1", 1)
    assert set(wardrobe.misses) == {OVERALL_ID, ODD_CAP_ID, BROKEN_CASH_ID}
    assert image_of(OVERALL_ID) in caplog.text


# --- coverage -----------------------------------------------------------------


def test_coverage_groups_what_fails_by_item(wardrobe: Wardrobe) -> None:
    found = coverage(wardrobe, np.random.default_rng(8), 40)
    assert 0 < found.composed < found.tried
    assert found.share == found.composed / found.tried
    assert set(found.failures) == {OVERALL_ID, ODD_CAP_ID}
    assert set(found.failures[OVERALL_ID]) == {"no frame alert"}
    reasons = set(found.failures[ODD_CAP_ID])
    assert reasons == {"z 'capBelowHead' isn't in Base/zmap.img"}
