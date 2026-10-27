"""
The raw diff: what changed between two extractions' raw layers, by image path.

An image is **added** or **removed** when only one raw layer has its path, and
**changed** when both have it and the `sha256` of its stored tree differs. That
hash covers everything the tree holds, a canvas's image name included, so a
canvas whose pixels changed is a changed image. Unchanged images are never
read. A changed image with no node differences kept its nodes and reordered
them.

A changed image gets its node-level differences: the path of each node that
differs, and its old and new value. A node that exists on one side only is
reported once, at the root of what was added or removed. A canvas is compared
as the node it is, so a changed canvas shows as a changed `image` name (its
hash) under the canvas's path.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from game_data.extraction import Json

TYPE = "$type"

type Kind = Literal["added", "removed", "changed"]


@dataclass(frozen=True, slots=True)
class NodeChange:
    """
    One node that differs inside a changed image.

    :ivar path: The node's path inside the image, such as `info/level`; empty
        for the image's root.
    :ivar kind: `added` (`old` is then `None`), `removed` (`new` is then
        `None`) or `changed`.
    :ivar old: The node's tree before, as the raw layer stores it.
    :ivar new: The node's tree after.
    """

    path: str
    kind: Kind
    old: Json
    new: Json


@dataclass(frozen=True, slots=True)
class ImageChange:
    """A changed image, and how its tree differs."""

    path: str
    nodes: tuple[NodeChange, ...]


@dataclass(frozen=True, slots=True)
class RawDiff:
    """
    Every image that differs, each list by path.

    :ivar added: Images only the new raw layer has.
    :ivar removed: Images only the old one has.
    :ivar changed: Images both have, whose trees differ.
    """

    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[ImageChange, ...]


def diff_raw(old: Path, new: Path) -> RawDiff:
    """
    Compares two `raw.sqlite` files.

    :param old: The older extraction's raw layer.
    :param new: The newer one's.
    """
    with closing(sqlite3.connect(f"{old.resolve().as_uri()}?mode=ro", uri=True)) as db:
        db.execute("ATTACH DATABASE ? AS newer", (f"{new.resolve().as_uri()}?mode=ro",))
        added = [
            path
            for (path,) in db.execute(
                "SELECT path FROM newer.images "
                "WHERE path NOT IN (SELECT path FROM main.images) ORDER BY path"
            )
        ]
        removed = [
            path
            for (path,) in db.execute(
                "SELECT path FROM main.images "
                "WHERE path NOT IN (SELECT path FROM newer.images) ORDER BY path"
            )
        ]
        changed = [
            ImageChange(
                path,
                tuple(diff_trees(_tree(before), _tree(after))),
            )
            for path, before, after in db.execute(
                "SELECT o.path, o.tree, n.tree FROM main.images o "
                "JOIN newer.images n ON n.path = o.path "
                "WHERE o.sha256 != n.sha256 ORDER BY o.path"
            ).fetchall()
        ]
    return RawDiff(tuple(added), tuple(removed), tuple(changed))


def _tree(text: str) -> Json:
    tree: Json = json.loads(text)
    return tree


def diff_trees(old: Json, new: Json, path: str = "") -> Iterator[NodeChange]:
    """
    The nodes that differ between two trees, in the order the trees hold them.

    Two sub-properties, or two nodes of one `$type`, are compared child by
    child. Anything else that isn't equal is one change. `5` and `5.0` differ,
    since the raw layer keeps an int apart from a double.
    """
    if _same(old, new):
        return
    if (
        isinstance(old, dict)
        and isinstance(new, dict)
        and old.get(TYPE) == new.get(TYPE)
    ):
        for name, child in old.items():
            below = f"{path}/{name}" if path else name
            if name not in new:
                yield NodeChange(below, "removed", child, None)
            else:
                yield from diff_trees(child, new[name], below)
        for name, child in new.items():
            if name not in old:
                yield NodeChange(
                    f"{path}/{name}" if path else name, "added", None, child
                )
        return
    yield NodeChange(path, "changed", old, new)


def _same(old: Json, new: Json) -> bool:
    """Equal in value and in kind, whatever they hold."""
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(
            _same(child, new[name]) for name, child in old.items()
        )
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(
            _same(a, b) for a, b in zip(old, new, strict=True)
        )
    return type(old) is type(new) and old == new
