"""
`game_data.scenes.players` on the local store's extraction of the client.

Marked `client_files`, so the default run deselects them: they read the store
that `configs/game_data.ini` points at, extracted from the client. Run them
with `pytest -m client_files`.
"""

from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pytest

from game_data.catalogue import Catalogue
from game_data.config import STORE
from game_data.scenes.players import (
    SLOTS,
    WEAPON_TYPES,
    Outfit,
    Wardrobe,
    coverage,
    image_of,
)

pytestmark = pytest.mark.client_files

BASE = Outfit(
    skin=0,
    face=20000,
    hair=30000,
    cap=1002000,
    coat=1040002,
    pants=1060002,
    shoes=1072001,
    weapon=1302000,
)
"""Beginner's clothes and a one-handed sword, all regular items."""

CASH_SWORD = 1702008
"""A cash weapon held under type 30 only, with ladder and rope frames."""

WORN = {
    "glove": 1082000,
    "cape": 1102000,
    "shield": 1092000,
    "face_accessory": 1017000,
    "eye_accessory": 1027000,
    "earrings": 1032000,
}
"""One piece of each optional slot, cash and regular, that has every pose."""

OVERALL = 1050000


@pytest.fixture(scope="module")
def wardrobe() -> Iterator[Wardrobe]:
    with Catalogue.latest(STORE) as cat, Wardrobe(cat) as found:
        yield found


def every_frame(wardrobe: Wardrobe, outfit: Outfit) -> Iterator[tuple[str, int]]:
    for action in outfit.poses():
        for frame in range(wardrobe.frames(outfit, action)):
            yield action, frame


def test_each_weapon_types_regular_weapons_stand_walk_and_attack_as_it_says(
    wardrobe: Wardrobe,
) -> None:
    for kind, wields in WEAPON_TYPES.items():
        weapons = [
            item for item in wardrobe.pieces("weapon") if item // 10000 == 100 + kind
        ]
        assert weapons, f"no regular weapon of type {kind}"
        for item in weapons:
            tree = wardrobe.tree(image_of(item))
            info = tree.at("info")
            stand = f"stand{info.integer('stand')}"
            walk = f"walk{info.integer('walk')}"
            assert (stand, walk) == (wields.stand, wields.walk), item
            for action in (wields.stand, wields.walk, *wields.attacks):
                assert tree.get(action) is not None, (item, action)


def test_every_slot_has_pieces_cash_ones_among_them(wardrobe: Wardrobe) -> None:
    for slot in ("face", "hair", *SLOTS):
        assert wardrobe.pieces(slot), slot
    weapons = wardrobe.pieces("weapon")
    assert sum(item // 10000 == 170 for item in weapons) > 300
    assert len(wardrobe.pieces("cap")) > 900


def test_regular_items_compose_in_every_pose_and_frame(wardrobe: Wardrobe) -> None:
    for action, frame in every_frame(wardrobe, BASE):
        player = wardrobe.compose(BASE, action, frame, name="Legends")
        x1, y1, x2, y2 = player.box
        assert 20 <= x2 - x1 <= 120, (action, frame, player.box)
        assert 20 <= y2 - y1 <= 120, (action, frame, player.box)
        assert player.tag is not None


def test_a_cash_weapon_composes_from_its_weapon_types_frames(
    wardrobe: Wardrobe,
) -> None:
    assert wardrobe.weapon_types(CASH_SWORD) == (30,)
    outfit = replace(BASE, weapon=CASH_SWORD, weapon_type=30)
    tree = wardrobe.tree(image_of(CASH_SWORD))
    for action, frame in every_frame(wardrobe, outfit):
        wardrobe.compose(outfit, action, frame)
        held = tree.get("30")
        assert held is not None
        node = held.get(action)
        if node is None or node.get(str(frame)) is None:
            continue
        images = {
            p.image
            for p in wardrobe.parts(outfit, action, frame)
            if p.item == CASH_SWORD
        }
        assert images, (action, frame)


def test_every_optional_slot_and_an_overall_compose(wardrobe: Wardrobe) -> None:
    dressed = replace(BASE, **WORN)
    overall = replace(BASE, coat=OVERALL, pants=None)
    two_handed = replace(overall, weapon=1402000)
    for outfit in (dressed, overall, two_handed):
        for action, frame in every_frame(wardrobe, outfit):
            wardrobe.compose(outfit, action, frame)


def test_most_random_frames_compose_and_every_drawn_player_does(
    wardrobe: Wardrobe,
) -> None:
    found = coverage(wardrobe, np.random.default_rng(0), 40)
    assert found.share > 0.8
    rng = np.random.default_rng(1)
    for _ in range(40):
        look = wardrobe.draw(rng)
        wardrobe.compose(look.outfit, look.action, look.frame, flip=look.flip)
