"""
What the client draws over mobs, as `item_icons`, `meso_frames` and
`damage_digits` rows.

- **Item icons.** An item image, `Item/<category>/<prefix>.img` such as
  `Item/Consume/0200.img`, holds one child per item, named by its ID
  (`02000000`). Its `info/iconRaw` is the icon a drop shows: a canvas, or a UOL
  to one in the same image. An item with no `info`, or no `iconRaw`, has no
  row. The pets' images, `Item/Pet/<id>.img`, are one item each and aren't
  read.
- **Mesos.** `Item/Special/0900.img` holds one child per meso sprite, named by
  its ID (`09000000`), whose `iconRaw/<n>` are the frames of its spin.
- **Damage digits.** `Effect/BasicEff.img` holds the digit sets the client
  draws numbers with, `No<colour><n>` such as `NoRed0`, each with a canvas per
  digit, `0` to `9`. A set's other children, such as `Miss` or `effect`,
  aren't digits.

An image the client doesn't have leaves its table empty.
"""

import re
from collections.abc import Iterable
from typing import Final

from .maps import Row
from .trees import Tree

ITEM_IMAGE: Final = re.compile(r"Item/(?P<category>[A-Za-z]+)/(?P<prefix>\d{4})\.img")
MESO_IMAGE: Final = "Item/Special/0900.img"
DIGITS_IMAGE: Final = "Effect/BasicEff.img"
DIGIT_SET: Final = re.compile(r"No[A-Za-z]+\d+")


def read_item_icons(trees: Iterable[tuple[str, Tree]]) -> list[Row]:
    """
    Every item's icon, by image and then the image's order.

    :param trees: Each item image's category and root.
    """
    rows: list[Row] = []
    for category, tree in trees:
        for key, item in tree.expect("property").children():
            if not key.isdigit():
                raise item.error("an item whose name isn't an ID")
            info = item.expect("property").get("info")
            icon = None if info is None else info.expect("property").get("iconRaw")
            if icon is None:
                continue
            canvas = icon.resolved().expect("canvas")
            rows.append((int(key), category, canvas.canvas_image(), *canvas.origin()))
    return rows


def read_meso_frames(tree: Tree) -> list[Row]:
    """`Item/Special/0900.img`'s meso sprites, one row per frame."""
    rows: list[Row] = []
    for key, meso in tree.expect("property").children():
        if not key.isdigit():
            raise meso.error("a meso whose name isn't an ID")
        icon = meso.expect("property").at("iconRaw").expect("property")
        for frame, child in icon.children():
            if not frame.isdigit():
                continue
            canvas = child.resolved().expect("canvas")
            rows.append((int(key), int(frame), canvas.canvas_image(), *canvas.origin()))
    return rows


def read_damage_digits(tree: Tree) -> list[Row]:
    """`Effect/BasicEff.img`'s digit sets, one row per digit."""
    rows: list[Row] = []
    for name, digits in tree.expect("property").children():
        if not DIGIT_SET.fullmatch(name):
            continue
        for key, child in digits.expect("property").children():
            if len(key) != 1 or not key.isdigit():
                continue
            canvas = child.resolved().expect("canvas")
            rows.append((name, int(key), canvas.canvas_image(), *canvas.origin()))
    return rows
