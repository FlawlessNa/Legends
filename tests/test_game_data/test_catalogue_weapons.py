"""
The catalogue's weapons, swings and weapon icons, built from the raw layer of
a synthetic client's extraction, every value invented:

- `Character/Weapon/01302000.img`: a one-handed sword with `afterImage`
  `swordOL`, `attackSpeed` 4, `attack` 1 and an icon; `01302001.img`, with
  none of those but an `attack`, and no name in the strings; and
  `01702000.img`, a cash item with no `info`.
- `Character/Afterimage/swordOL.img`: brackets 0 and 10 of `swingO1` and
  `stabO1`, with a `charge` child of actions, a bracket of that name, and an
  action with no box; and `blank.img`, with no bracket.
- `String/Eqp.img`: names the sword, and a cap.
- `Character/00002000.img`: `swingO1` of three delays, and `alert3`, whose
  delays are negative.
"""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest

from game_data.catalogue import (
    Catalogue,
    Swing,
    WeaponData,
    build_catalogue,
)
from game_data.extraction import extract
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_catalogue import canvas

SWORD = 1302000
PLAIN = 1302001


def box(name: str, lt: tuple[int, int], rb: tuple[int, int]) -> w.Prop:
    return w.Prop(
        name,
        [
            w.Prop("0", [canvas("0", 70)]),
            w.Vector("lt", *lt),
            w.Vector("rb", *rb),
        ],
    )


def afterimages() -> list[w.Img]:
    def bracket(number: int, swing_lt: tuple[int, int]) -> w.Prop:
        return w.Prop(
            str(number),
            [
                box("swingO1", swing_lt, (-18, -6)),
                box("stabO1", (-84, -30), (-20, -15)),
                w.Prop("proneStab", [w.Prop("0", [canvas("0", 71)])]),
                w.Prop("charge", [box("swingO1", (-1, -1), (1, 1))]),
            ],
        )

    return [
        w.Img(
            "swordOL.img",
            [
                bracket(0, (-88, -62)),
                bracket(10, (-90, -72)),
                w.Prop("charge", [box("swingO1", (-2, -2), (2, 2))]),
            ],
        ),
        w.Img("blank.img", [w.Prop("axe", [w.Prop("0", [canvas("0", 72)])])]),
    ]


def weapons() -> list[w.Img]:
    return [
        w.Img(
            "01302000.img",
            [
                w.Prop(
                    "info",
                    [
                        canvas("icon", 80, w.Vector("origin", 0, 30)),
                        w.Short("attack", 1),
                        w.String("afterImage", "swordOL"),
                        w.Int("attackSpeed", 4),
                    ],
                ),
                w.Prop("walk1", [w.Prop("0", [canvas("weapon", 81)])]),
            ],
        ),
        w.Img("01302001.img", [w.Prop("info", [w.Short("attack", 1)])]),
        w.Img("01702000.img", [w.Prop("stand1", [w.Prop("0", [canvas("a", 82)])])]),
    ]


def body() -> list[w.Img]:
    def frame(name: str, delay: int) -> w.Prop:
        return w.Prop(name, [w.Int("delay", delay)])

    return [
        w.Img(
            "00002000.img",
            [
                w.Prop("info", [w.String("islot", "Bd")]),
                w.Prop("swingO1", [frame("0", 300), frame("1", 150), frame("2", 350)]),
                w.Prop("alert3", [frame("0", -500), frame("1", -500), frame("2", 500)]),
            ],
        )
    ]


def strings() -> list[w.Img]:
    return [
        w.Img(
            "Eqp.img",
            [
                w.Prop(
                    "ClassicWorld",
                    [
                        w.Prop(
                            "Cap", [w.Prop("1002000", [w.String("name", "Red Cap")])]
                        ),
                        w.Prop(
                            "Weapon",
                            [w.Prop("1302000", [w.String("name", "Sword")])],
                        ),
                    ],
                )
            ],
        )
    ]


def write_weapons_client(data: Path) -> Path:
    w.write_tree(
        data / "Character",
        [
            *body(),
            w.Dir("Weapon", weapons()),
            w.Dir("Afterimage", afterimages()),
        ],
        ini=False,
    )
    w.write_tree(data / "String", strings(), ini=False)
    return data


@pytest.fixture
def cat(tmp_path: Path) -> Iterator[Catalogue]:
    root = tmp_path / "store"
    client = write_weapons_client(tmp_path / "Data")
    build_id = extract(client, root, catalogue=build_catalogue).manifest.build
    with Catalogue.open(build_id, root) as catalogue:
        yield catalogue


def test_a_weapon_holds_its_info_and_its_name_from_the_strings(
    cat: Catalogue,
) -> None:
    assert cat.weapon(SWORD) == WeaponData(SWORD, "Sword", "swordOL", 4, 1)
    assert cat.weapon("sword") == cat.weapon(str(SWORD))


def test_a_weapon_without_afterimage_or_name_has_none_of_them(cat: Catalogue) -> None:
    assert cat.weapon(PLAIN) == WeaponData(PLAIN, None, None, None, 1)


def test_an_image_without_info_is_no_weapon(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="no weapon has the ID 1702000"):
        cat.weapon(1702000)
    with pytest.raises(LookupError, match="no weapon is named 'swrod'; the closest"):
        cat.weapon("swrod")


def test_a_bracket_holds_its_swings_with_the_charge_child_skipped(
    cat: Catalogue,
) -> None:
    assert cat.swings("swordOL", 0) == (
        Swing("swordOL", 0, "swingO1", -88, -62, -18, -6),
        Swing("swordOL", 0, "stabO1", -84, -30, -20, -15),
    )
    assert cat.swings("swordOL", 10)[0] == Swing(
        "swordOL", 10, "swingO1", -90, -72, -18, -6
    )


def test_an_unknown_swing_set_or_bracket_is_a_lookup_error(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match=r"has no bracket 3; it has \[0, 10\]"):
        cat.swings("swordOL", 3)
    with pytest.raises(LookupError, match="no swing set is named 'swordO'"):
        cat.swings("swordO", 0)
    with pytest.raises(LookupError, match="no swing set is named 'blank'"):
        cat.swings("blank", 0)


def test_a_weapon_with_an_icon_has_one_with_its_origin(cat: Catalogue) -> None:
    icons = cat.weapon_icons()
    assert [(i.weapon, i.origin_x, i.origin_y) for i in icons] == [(SWORD, 0, 30)]
    assert icons[0].image is not None


def test_an_actions_delays_come_in_order_with_their_sign(cat: Catalogue) -> None:
    assert cat.action_delays("swingO1") == [300, 150, 350]
    assert cat.action_delays("alert3") == [-500, -500, 500]
    with pytest.raises(LookupError, match="no action 'swingO9'"):
        cat.action_delays("swingO9")


def test_the_results_are_frozen(cat: Catalogue) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        cat.weapon(SWORD).name = "x"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cat.weapon_icons()[0].image = None  # type: ignore[misc]
