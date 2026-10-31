"""
`game_data.scenes.players`: a character composed from a synthetic client.

`write_players_client` writes a client whose parts are blocks of one colour
each, so where a colour lands says where its part was anchored. In the feet's
coordinates (the body's origin at `(0, 0)`):

- the body, 4x4, gives `navel` at `(0, -2)` and `neck` at `(0, -4)`;
- the arm hangs from the `navel` and gives `hand` at `(4, -1)`, which the
  weapon hangs from: anchors found through another part;
- the head hangs from the `neck` and gives `brow` at `(0, -8)`, which the
  face, the hair and the cap hang from;
- the coat's `mail` covers the body's middle and the arm's left column:
  `mailChest` is in front of `body` in `Base/zmap.img`, and behind `arm`,
  though the arm is read before it;
- the cap's `vslot` is `CpH1`, and the hair's `hairOverHead` is `H1` in
  `Base/smap.img`, so the cap hides it;
- the hair's `hairShade` has one canvas per skin, `0` and `1`; skin `1`'s
  body and head are skin `0`'s.

`UI/NameTag.img` has one style, `3`: red west, green centre and blue east
pieces, black text.
"""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from game_data.catalogue import Catalogue, CatalogueError, build_catalogue
from game_data.extraction import extract
from game_data.scenes.players import (
    PIECES,
    SLOTS,
    TAG_BACKGROUND,
    TAG_GAP,
    TAG_HEIGHT,
    Outfit,
    Part,
    Player,
    Wardrobe,
    anchor,
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
WEST: Rgba = (255, 0, 0, 255)
CENTRE: Rgba = (0, 255, 0, 255)
EAST: Rgba = (0, 0, 255, 255)

ZMAP = [
    "weapon",
    "hairOverHead",
    "cap",
    "hair",
    "face",
    "hairShade",
    "head",
    "arm",
    "mailChest",
    "body",
]
SMAP = {"hairOverHead": "H1", "hair": "H2", "cap": "CpH1"}

FACE_ID, HAIR_ID, CAP_ID, COAT_ID, WEAPON_ID = 20000, 30000, 1002000, 1040000, 1302000
DRESSED = Outfit(skin=0, face=FACE_ID, hair=HAIR_ID, coat=COAT_ID, weapon=WEAPON_ID)


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


def body() -> list[w.Property]:
    return [
        stand(
            part("body", (4, 4), BODY, (2, 4), "body", navel=(0, -2), neck=(0, -4)),
            part("arm", (2, 2), ARM, (1, 1), "arm", navel=(-3, 0), hand=(1, 1)),
            w.Short("face", 1),
            w.Int("delay", 500),
        ),
        w.Prop(
            "walk1",
            [
                w.Prop("0", [w.Uol("body", "../../stand1/0/body")]),
                w.Prop("1", [w.Uol("body", "../../stand1/0/body")]),
            ],
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


def info(vslot: str) -> w.Prop:
    return w.Prop("info", [w.String("vslot", vslot)])


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
        stand(
            w.Uol("hair", "../../default/hair"),
            w.Uol("hairOverHead", "../../default/hairOverHead"),
            w.Uol("hairShade", "../../default/hairShade"),
        ),
    ]


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
    cap = [
        info("CpH1"),
        w.Prop("default", [part("default", (1, 1), CAP, (0, 0), "cap", brow=(-2, 2))]),
        stand(w.Uol("default", "../../default/default")),
    ]
    coat = [
        info("Ma"),
        stand(part("mail", (4, 2), MAIL, (1, 1), "mailChest", navel=(0, 0))),
    ]
    weapon = [
        info("Wp"),
        stand(part("weapon", (1, 1), WEAPON, (0, 0), "weapon", hand=(-2, 0))),
    ]
    w.write_tree(
        data / "Character",
        [
            w.Img("00002000.img", body()),
            w.Img("00012000.img", head()),
            w.Img("00002001.img", body()),
            w.Img("00012001.img", head()),
            w.Dir("Face", [w.Img(f"{FACE_ID:08d}.img", face)]),
            w.Dir("Hair", [w.Img(f"{HAIR_ID:08d}.img", hair())]),
            w.Dir("Cap", [w.Img(f"{CAP_ID:08d}.img", cap)]),
            w.Dir("Coat", [w.Img(f"{COAT_ID:08d}.img", coat)]),
            w.Dir("Weapon", [w.Img(f"{WEAPON_ID:08d}.img", weapon)]),
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


def test_a_part_sharing_no_anchor_raises_naming_it() -> None:
    body = Part("body", 1, "b", (0, 0), "body", {"navel": (0, -2)})
    stray = Part("cape", 7, "c", (0, 0), "cape", {"tail": (0, 0)})
    with pytest.raises(CatalogueError, match="7/cape"):
        anchor([body, stray])


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
    with pytest.raises(LookupError, match="no action 'jump'"):
        wardrobe.compose(Outfit(), "jump", 0)
    with pytest.raises(LookupError, match="no frame stand1/5"):
        wardrobe.compose(Outfit(), "stand1", 5)


def test_a_piece_without_the_frame_is_left_out(wardrobe: Wardrobe) -> None:
    player = wardrobe.compose(DRESSED, "walk1", 1)
    assert not where(player, WEAPON)
    assert where(player, BODY)


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


def test_every_slot_has_five_pieces_or_more() -> None:
    assert set(SLOTS) <= set(PIECES)
    assert all(len(set(ids)) >= 5 for ids in PIECES.values())


def test_a_drawn_outfit_depends_only_on_the_seed() -> None:
    def drawn(seed: int) -> list[Outfit]:
        rng = np.random.default_rng(seed)
        return [Outfit.drawn(rng) for _ in range(20)]

    assert drawn(1) == drawn(1)
    assert drawn(1) != drawn(2)
    for outfit in drawn(1):
        for slot, ids in PIECES.items():
            assert getattr(outfit, slot) in (*ids, None)
