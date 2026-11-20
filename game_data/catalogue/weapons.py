"""
Weapons, their swings and their icons, as `weapons`, `swings` and
`weapon_icons` rows.

- **Weapons.** `Character/Weapon/<id>.img`, such as `01302000.img`, holds a
  weapon's art, and its `info` the fields the catalogue keeps: `afterImage`,
  the swing set it plays (`swordOL`; none for most cash items), `attackSpeed`
  and `attack`, its attack family (1 a one-handed weapon or a dagger, 2 a spear
  or polearm, 3 a bow, 4 a crossbow, 5 a two-handed weapon, 6 a wand or
  staff, 7 a claw, 8 bare hands). An image with no `info` isn't a weapon. Its
  name is in `String/Eqp.img`, `ClassicWorld/Weapon/<id>/name`.
- **Swings.** `Character/Afterimage/<set>.img/<bracket>/<action>` holds the
  frames of an action's swing, and its `lt` and `rb`: the hit box, facing left,
  as the client stores it. A bracket is a number, 0 to 10 (bare hands go to
  16). The `charge` child of a bracket is another set of actions, and is
  skipped, as are the children of an image that aren't numbered brackets, such
  as `charge` and `Afterimage/hit.img`'s effects. An action with no `lt` and
  `rb` has no row.
- **Weapon icons.** A weapon's `info/icon`, the icon the equipment window
  shows, with its origin. A weapon without one has no row.

Every value is as the client gives it.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

from .maps import Row
from .trees import Tree

WEAPON_IMAGE: Final = re.compile(r"Character/Weapon/(?P<id>\d+)\.img")
AFTERIMAGE: Final = re.compile(r"Character/Afterimage/(?P<name>[A-Za-z0-9]+)\.img")
EQP_IMAGE: Final = "String/Eqp.img"
CHARGE: Final = "charge"


@dataclass(slots=True)
class WeaponRows:
    """The rows read so far, by table."""

    weapons: list[Row] = field(default_factory=list[Row])
    weapon_icons: list[Row] = field(default_factory=list[Row])


def read_weapon_names(tree: Tree) -> dict[int, str | None]:
    """`String/Eqp.img`'s weapons, `<world>/Weapon/<id>/name`, by ID."""
    names: dict[int, str | None] = {}
    for _, world in tree.expect("property").children():
        category = world.expect("property").get("Weapon")
        if category is None:
            continue
        for key, entry in category.expect("property").children():
            if not key.isdigit():
                raise entry.error("a weapon whose name isn't an ID")
            if int(key) in names:
                raise entry.error(f"weapon {int(key)} is named twice")
            names[int(key)] = entry.expect("property").optional_text("name")
    return names


def read_weapons(
    trees: Mapping[int, Tree], names: Mapping[int, str | None]
) -> WeaponRows:
    """
    Every weapon and its icon, by ID.

    :param trees: Each weapon's image, by the weapon's ID.
    :param names: Each weapon's name, from `String/Eqp.img`.
    """
    rows = WeaponRows()
    for weapon, tree in sorted(trees.items()):
        info = tree.expect("property").get("info")
        if info is None:
            continue
        info.expect("property")
        rows.weapons.append(
            (
                weapon,
                names.get(weapon),
                info.optional_text("afterImage"),
                info.optional_integer("attackSpeed"),
                info.optional_integer("attack"),
            )
        )
        icon = info.get("icon")
        if icon is not None:
            canvas = icon.resolved().expect("canvas")
            rows.weapon_icons.append((weapon, canvas.canvas_image(), *canvas.origin()))
    return rows


def read_swings(trees: Iterable[tuple[str, Tree]]) -> list[Row]:
    """
    Every swing's hit box, by set, bracket and then the image's order.

    :param trees: Each swing set's name and image.
    """
    rows: list[Row] = []
    for name, tree in sorted(trees, key=lambda found: found[0]):
        for bracket, actions in tree.expect("property").children():
            if not bracket.isdigit():
                continue
            for action, swing in actions.expect("property").children():
                if action == CHARGE:
                    continue
                swing.expect("property")
                lt = swing.get("lt")
                rb = swing.get("rb")
                if lt is None or rb is None:
                    continue
                rows.append((name, int(bracket), action, *lt.vector(), *rb.vector()))
    return rows
