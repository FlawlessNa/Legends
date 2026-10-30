"""
The catalogue's occluder sprites, built from the raw layer of a synthetic
client's extraction.

`write_occluders_client` writes a client of only items and effects, every
value invented, laid out as Classic's are:

- `Item/Consume/0200.img`: item `02000000`, whose `info/iconRaw` is a canvas;
  `02000001`, whose `iconRaw` is a UOL to `02000000`'s; `02000002`, whose
  `info` has no `iconRaw`; and `02000003`, with no `info`.
- `Item/Cash/0501.img`: item `05010000`, with an icon.
- `Item/Pet/5000000.img`: a pet, one item to an image, which isn't read.
- `Item/Special/0900.img`: meso `09000000`, of two frames and a third that's
  a UOL to the first; and `09000001`, of one.
- `Effect/BasicEff.img`: the digit sets `NoRed0`, with a `Miss` beside its ten
  digits, and `NoRed1`; and `LevelUp`, which isn't a digit set.
"""

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest

from game_data.catalogue import (
    Catalogue,
    CatalogueError,
    DamageDigit,
    ItemIcon,
    MesoFrame,
    build,
    build_catalogue,
)
from game_data.extraction import extract
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_catalogue import canvas, write_raw


def icon(red: int, *children: w.Property) -> w.Prop:
    return w.Prop("info", [canvas("iconRaw", red, *children), w.Int("price", 5)])


def items() -> list[w.Dir]:
    return [
        w.Dir(
            "Consume",
            [
                w.Img(
                    "0200.img",
                    [
                        w.Prop("02000000", [icon(10, w.Vector("origin", -3, 30))]),
                        w.Prop(
                            "02000001",
                            [
                                w.Prop(
                                    "info",
                                    [w.Uol("iconRaw", "../../02000000/info/iconRaw")],
                                )
                            ],
                        ),
                        w.Prop("02000002", [w.Prop("info", [w.Int("price", 1)])]),
                        w.Prop("02000003", [w.Prop("spec", [w.Int("hp", 50)])]),
                    ],
                )
            ],
        ),
        w.Dir(
            "Cash",
            [w.Img("0501.img", [w.Prop("05010000", [icon(11)])])],
        ),
        w.Dir("Pet", [w.Img("5000000.img", [icon(12)])]),
        w.Dir(
            "Special",
            [
                w.Img(
                    "0900.img",
                    [
                        w.Prop(
                            "09000000",
                            [
                                w.Prop(
                                    "iconRaw",
                                    [
                                        canvas("0", 20, w.Vector("origin", -5, 28)),
                                        canvas("1", 21, w.Vector("origin", -4, 28)),
                                        w.Uol("2", "0"),
                                    ],
                                )
                            ],
                        ),
                        w.Prop("09000001", [w.Prop("iconRaw", [canvas("0", 22)])]),
                    ],
                )
            ],
        ),
    ]


def basic_effects() -> list[w.Property]:
    def digits(name: str, red: int, *extra: w.Property) -> w.Prop:
        return w.Prop(
            name,
            [
                *(
                    canvas(str(d), red + d, w.Vector("origin", 15, 32))
                    for d in range(10)
                ),
                *extra,
            ],
        )

    return [
        digits("NoRed0", 100, canvas("Miss", 99)),
        digits("NoRed1", 120),
        w.Prop("LevelUp", [canvas("0", 140)]),
    ]


def write_occluders_client(data: Path) -> Path:
    """The client described above, in `data`."""
    w.write_tree(data / "Item", items(), ini=False)
    w.write_tree(data / "Effect", [w.Img("BasicEff.img", basic_effects())], ini=False)
    return data


@pytest.fixture
def cat(tmp_path: Path) -> Iterator[Catalogue]:
    root = tmp_path / "store"
    client = write_occluders_client(tmp_path / "Data")
    build_id = extract(client, root, catalogue=build_catalogue).manifest.build
    with Catalogue.open(build_id, root) as catalogue:
        yield catalogue


# --- item icons --------------------------------------------------------------


def test_each_item_with_an_icon_has_one_with_its_category_and_origin(
    cat: Catalogue,
) -> None:
    icons = cat.item_icons()

    assert [(i.item, i.category, i.origin_x, i.origin_y) for i in icons] == [
        (2000000, "Consume", -3, 30),
        (2000001, "Consume", -3, 30),
        (5010000, "Cash", 0, 0),
    ]
    assert None not in {i.image for i in icons}


def test_an_icon_that_is_a_uol_is_the_icon_it_leads_to(cat: Catalogue) -> None:
    first, linked, cash = cat.item_icons()

    assert linked.image == first.image
    assert cash.image != first.image


# --- mesos -------------------------------------------------------------------


def test_each_meso_has_its_frames_and_a_uol_frame_is_the_one_it_leads_to(
    cat: Catalogue,
) -> None:
    frames = cat.meso_frames()

    assert [(f.meso, f.frame, f.origin_x, f.origin_y) for f in frames] == [
        (9000000, 0, -5, 28),
        (9000000, 1, -4, 28),
        (9000000, 2, -5, 28),
        (9000001, 0, 0, 0),
    ]
    assert frames[2].image == frames[0].image
    assert len({f.image for f in frames}) == 3


# --- damage digits -----------------------------------------------------------


def test_each_digit_set_has_its_ten_digits_and_nothing_else(cat: Catalogue) -> None:
    digits = cat.damage_digits()

    assert [(d.digit_set, d.digit) for d in digits] == [
        *(("NoRed0", n) for n in range(10)),
        *(("NoRed1", n) for n in range(10)),
    ]
    assert {(d.origin_x, d.origin_y) for d in digits} == {(15, 32)}
    assert len({d.image for d in digits}) == 20


# --- results and errors ------------------------------------------------------


def test_occluder_lookups_return_frozen_dataclasses(cat: Catalogue) -> None:
    values = (cat.item_icons()[0], cat.meso_frames()[0], cat.damage_digits()[0])

    assert [type(v) for v in values] == [ItemIcon, MesoFrame, DamageDigit]
    for value in values:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, 0)


@pytest.mark.parametrize(
    ("trees", "message"),
    [
        (
            {"Item/Etc/0400.img": {"apple": {}}},
            "image Item/Etc/0400.img, node apple: an item whose name isn't an ID",
        ),
        (
            {"Item/Etc/0400.img": {"04000000": {"info": {"iconRaw": 5}}}},
            (
                "image Item/Etc/0400.img, node 04000000/info/iconRaw: it is a int, "
                "not a canvas"
            ),
        ),
        (
            {"Item/Special/0900.img": {"09000000": {}}},
            "image Item/Special/0900.img, node 09000000: it has no child 'iconRaw'",
        ),
        (
            {"Effect/BasicEff.img": {"NoRed0": {"0": "x"}}},
            "image Effect/BasicEff.img, node NoRed0/0: it is a string, not a canvas",
        ),
    ],
)
def test_an_occluder_image_not_as_expected_names_the_node(
    tmp_path: Path, trees: dict[str, object], message: str
) -> None:
    folder = write_raw(tmp_path / "x", trees)

    with pytest.raises(CatalogueError) as raised:
        build(folder)

    assert str(raised.value) == message
