"""
Reading the raw layer's JSON trees (`extraction.raw`), with every surprise an
error that names the image and the node.

A `Tree` is one node of one image's tree: its JSON value, where it is, and the
image's root, so a UOL can be followed. Its getters take a child's name and
check its type: `integer` accepts an int, a short, a long or a string of
digits, `number` a float or a double too, and `text` a string. A child that is missing, or isn't of the
type asked for, raises `CatalogueError`; the `optional_` and `_or` getters
accept a missing one. Nothing is guessed: a catalogue built from a tree it
doesn't understand would be wrong without saying so.

A typed object's own keys, such as a canvas's `image`, `w` and `h`, aren't its
children (`OWN_KEYS`); the raw layer guarantees no child shares their names.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from game_data.extraction import Json

TYPE: Final = "$type"
MAX_LINKS: Final = 16

# The keys of a typed object that are its own, not its children's.
OWN_KEYS: Final = {
    "canvas": frozenset({"image", "w", "h"}),
    "raw_data": frozenset({"length", "sha256"}),
    "sound": frozenset({"duration_ms", "length", "sha256"}),
    "short": frozenset({"value"}),
    "long": frozenset({"value"}),
    "float": frozenset({"value"}),
    "vector": frozenset({"x", "y"}),
    "uol": frozenset({"path"}),
}


class CatalogueError(Exception):
    """The raw layer isn't as the catalogue expects, or the store isn't."""


@dataclass(frozen=True, slots=True)
class Tree:
    """
    One node of an image's raw tree.

    :ivar image: The image's path, such as `Map/Map/Map0/000001000.img`.
    :ivar path: The node's path inside the image; `""` is its root.
    :ivar value: The node's JSON.
    :ivar root: The image's whole tree, which links are followed in.
    """

    image: str
    path: str
    value: Json
    root: Json

    @classmethod
    def of(cls, image: str, root: Json) -> Tree:
        """The root of `image`'s tree."""
        return cls(image, "", root, root)

    def error(self, reason: str) -> CatalogueError:
        """An error naming this node."""
        where = f"image {self.image}, node {self.path}" if self.path else self.image
        return CatalogueError(f"{where}: {reason}")

    @property
    def type(self) -> str:
        """`property` for a sub-property, else the JSON's `$type` or kind."""
        value = self.value
        if isinstance(value, dict):
            tag = value.get(TYPE)
            return tag if isinstance(tag, str) else "property"
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "double"
        if isinstance(value, str):
            return "string"
        return "list"

    def at(self, name: str) -> Tree:
        """The child `name`, which must exist; links aren't followed."""
        found = self.get(name)
        if found is None:
            raise self.error(f"it has no child {name!r}")
        return found

    def get(self, name: str) -> Tree | None:
        """The child `name`, or `None`. Only objects have children."""
        value = self.value
        if not isinstance(value, dict) or name not in value or self._own(name):
            return None
        return Tree(self.image, self._join(name), value[name], self.root)

    def children(self) -> Iterator[tuple[str, Tree]]:
        """Every child, in the client's order: a canvas's or convex's too."""
        value = self.value
        if not isinstance(value, dict):
            return
        for name, child in value.items():
            if not self._own(name):
                yield name, Tree(self.image, self._join(name), child, self.root)

    def expect(self, *types: str) -> Tree:
        """This node, which must be one of `types`."""
        if self.type not in types:
            raise self.error(f"it is a {self.type}, not a {' or '.join(types)}")
        return self

    def resolved(self) -> Tree:
        """This node, or where its UOL leads, inside the same image."""
        node = self
        for _ in range(MAX_LINKS):
            if node.type != "uol":
                return node
            node = node._follow()
        raise self.error(f"following it met more than {MAX_LINKS} links")

    def _follow(self) -> Tree:
        link = self.at_text("path")
        steps = self.path.split("/")[:-1]
        for step in link.split("/"):
            if step in ("", "."):
                continue
            if step == "..":
                if not steps:
                    raise self.error(f"the link {link!r} leaves the image")
                steps.pop()
            else:
                steps.append(step)
        node = Tree.of(self.image, self.root)
        for step in steps:
            found = node.get(step)
            if found is None:
                raise self.error(f"the link {link!r} names nothing")
            node = found.resolved()
        return node

    def integer(self, name: str) -> int:
        """The child `name`: an int, a short or a long."""
        return self.at(name).int_value()

    def integer_or(self, name: str, default: int) -> int:
        """The child `name` as `integer`, or `default` when it's missing."""
        found = self.get(name)
        return default if found is None else found.int_value()

    def optional_integer(self, name: str) -> int | None:
        """The child `name` as `integer`, or `None` when it's missing."""
        found = self.get(name)
        return None if found is None else found.int_value()

    def number(self, name: str) -> float:
        """The child `name`: a float, a double, or an integer type."""
        node = self.at(name).expect("float", "double", "int", "short", "long")
        if node.type in ("int", "short", "long"):
            return float(node.int_value())
        value = node.value
        if isinstance(value, dict):
            value = value.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise node.error("its value isn't a number")
        return float(value)

    def text(self, name: str) -> str:
        """The child `name`, a string."""
        return self.at(name).str_value()

    def optional_text(self, name: str) -> str | None:
        """The child `name` as `text`, or `None` when it's missing."""
        found = self.get(name)
        return None if found is None else found.str_value()

    def str_value(self) -> str:
        """This node's value, a string."""
        value = self.value
        if not isinstance(value, str):
            raise self.error(f"it is a {self.type}, not a string")
        return value

    def at_text(self, name: str) -> str:
        """The JSON key `name` of a typed object, such as a UOL's `path`."""
        value = self.value
        found = value.get(name) if isinstance(value, dict) else None
        if not isinstance(found, str):
            raise self.error(f"its {name!r} isn't a string")
        return found

    def int_value(self) -> int:
        """
        This node's value: an int, a short or a long. A string of digits
        counts too, as the client writes some (a frame's `delay`, a
        background's `no`, a spawn's `id`).
        """
        value = self.value
        if isinstance(value, dict):
            value = value.get("value")
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
            return int(value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self.error(f"it is a {self.type}, not an integer")
        return value

    def vector(self) -> tuple[int, int]:
        """This node's `(x, y)`; it must be a vector."""
        self.expect("vector")
        value = self.value
        assert isinstance(value, dict)
        x, y = value.get("x"), value.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise self.error("its x and y aren't integers")
        return x, y

    def canvas_image(self) -> str | None:
        """A canvas's image in the image store; `None` when it has none."""
        self.expect("canvas")
        value = self.value
        assert isinstance(value, dict)
        image = value.get("image")
        if image is not None and not isinstance(image, str):
            raise self.error("its image isn't a name")
        return image

    def origin(self) -> tuple[int, int]:
        """A canvas's `origin`, `(0, 0)` when it has none."""
        found = self.get("origin")
        return (0, 0) if found is None else found.resolved().vector()

    def _own(self, name: str) -> bool:
        return name == TYPE or name in OWN_KEYS.get(self.type, frozenset())

    def _join(self, name: str) -> str:
        return f"{self.path}/{name}" if self.path else name
