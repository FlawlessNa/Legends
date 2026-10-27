"""
Mob images, `Mob/<id>.img`, as `mobs` and `mob_frames` rows.

A mob's image holds:

- `info`: its stats. `level`, `maxHP`, `maxMP`, `PADamage`, `MADamage`,
  `PDDamage`, `MDDamage`, `acc`, `eva` and `pushed` are always there; `speed`,
  `flySpeed`, `exp` and `elemAttr` only when they apply, so they're NULL
  otherwise. The flags (`bodyAttack`, `boss`, `undead`, `firstAttack`) are 0
  when left out.
- one child per action (`stand`, `move`, `hit1`, `attack1`...), whose numbered
  children are its frames: canvases, or UOLs to canvases in the same image.
  An action's other children, such as `zigzag` or an attack's `info`, aren't
  frames.

A mob with `info/link` shares another mob's sprites: its image has `info`
only, and its frames are the linked mob's, written again under its own ID so
`mob_frames` answers for it directly. The link is recorded in `mobs.link`.
Classic numbers its mobs `0000001`..., and keeps them in the `.ms` packs; the
raw layer has them under `Mob/` all the same.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from .maps import Row
from .trees import MAX_LINKS, Tree

MOB_IMAGE: Final = re.compile(r"Mob/(?P<id>\d{7})\.img")

_STATS: Final = (
    "level",
    "maxHP",
    "maxMP",
    "speed",
    "flySpeed",
    "exp",
    "PADamage",
    "MADamage",
    "PDDamage",
    "MDDamage",
    "acc",
    "eva",
    "pushed",
)
_OPTIONAL: Final = frozenset({"speed", "flySpeed", "exp"})
_FLAGS: Final = ("bodyAttack", "boss", "undead", "firstAttack")


@dataclass(slots=True)
class MobRows:
    """The rows read so far, by table."""

    mobs: list[Row] = field(default_factory=list[Row])
    mob_frames: list[Row] = field(default_factory=list[Row])


def read_mobs(trees: Mapping[int, Tree], names: Mapping[int, str | None]) -> MobRows:
    """
    Every mob's rows, by ID.

    :param trees: Each mob image's root, by the mob's ID.
    :param names: Each mob's name, from `String/Mob.img`.
    """
    links: dict[int, int] = {}
    frames: dict[int, list[Row]] = {}
    rows = MobRows()
    for mob_id, tree in sorted(trees.items()):
        tree.expect("property")
        info = tree.at("info").expect("property")
        link = info.optional_text("link")
        if link is not None:
            if not link.isdigit():
                raise info.at("link").error("a link that isn't a mob's ID")
            links[mob_id] = int(link)
        frames[mob_id] = _frames(mob_id, tree)
        if link is not None and frames[mob_id]:
            raise tree.error("it links to another mob's sprites, and has its own")
        rows.mobs.append(_mob(mob_id, info, names.get(mob_id), links.get(mob_id)))
    for mob_id in sorted(trees):
        source = _linked(mob_id, links, trees)
        rows.mob_frames += [(mob_id, *row[1:]) for row in frames[source]]
    return rows


def _mob(mob_id: int, info: Tree, name: str | None, link: int | None) -> Row:
    stats = [
        info.optional_integer(key) if key in _OPTIONAL else info.integer(key)
        for key in _STATS
    ]
    flags = [info.integer_or(key, 0) for key in _FLAGS]
    return (mob_id, name, link, *stats, *flags, info.optional_text("elemAttr"))


def _frames(mob_id: int, tree: Tree) -> list[Row]:
    rows: list[Row] = []
    for action, node in tree.children():
        if action == "info":
            continue
        node.expect("property")
        for key, child in node.children():
            if not key.isdigit():
                continue
            frame = child.resolved().expect("canvas")
            rows.append(
                (
                    mob_id,
                    action,
                    int(key),
                    frame.canvas_image(),
                    *frame.origin(),
                    *_optional_vector(frame, "lt"),
                    *_optional_vector(frame, "rb"),
                    *_optional_vector(frame, "head"),
                    frame.optional_integer("delay"),
                )
            )
    return rows


def _optional_vector(node: Tree, name: str) -> tuple[int | None, int | None]:
    found = node.get(name)
    return (None, None) if found is None else found.resolved().vector()


def _linked(mob_id: int, links: Mapping[int, int], trees: Mapping[int, Tree]) -> int:
    """The mob whose frames `mob_id` has: itself, or where its links lead."""
    found = mob_id
    for _ in range(MAX_LINKS):
        if found not in links:
            return found
        target = links[found]
        if target not in trees:
            raise (
                trees[found]
                .at("info")
                .at("link")
                .error(f"it links to mob {target}, which the raw layer doesn't have")
            )
        found = target
    raise trees[mob_id].error(f"following its links met more than {MAX_LINKS}")
