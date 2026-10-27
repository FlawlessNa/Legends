"""
An image's property tree as JSON, losslessly: the raw layer's `tree` column.

Every node keeps its name, its type, its value and its children's order. The
common types are plain JSON, and the rest are objects tagged with `$type`:

| node           | JSON                                                        |
| -------------- | ----------------------------------------------------------- |
| sub-property   | an object of its children, by name, in archive order        |
| int            | a number without a fraction: `5`                            |
| double         | a number with one: `5.0`                                    |
| string         | a string                                                    |
| null           | `null`                                                      |
| short          | `{"$type": "short", "value": 5}`                            |
| long           | `{"$type": "long", "value": 5}`                             |
| float          | `{"$type": "float", "value": 0.5}`                          |
| vector         | `{"$type": "vector", "x": 1, "y": 2}`                       |
| UOL            | `{"$type": "uol", "path": "../0"}`, the link as stored      |
| canvas         | `{"$type": "canvas", "image": <hash>, "w": 2, "h": 2, ...}` |
| convex         | `{"$type": "convex", "0": ..., "1": ...}`                   |
| sound          | `{"$type": "sound", "duration_ms", "length", "sha256"}`     |
| raw data       | `{"$type": "raw_data", "length", "sha256", ...}`            |

- **A canvas** is its image in the image store (`image`, a name such as the
  client's `_hash`), the image's width and height (`w`, `h`), then its
  properties (`origin`, `delay`, `_outlink`...) as children. The image is the
  canvas's pixels wherever they are: a placeholder's `w` and `h` are those of
  the canvas its link leads to. `image` is `null` when a link names nothing
  (`BrokenLink`); `w` and `h` are then the placeholder's own.
- **A sound** is a reference only: its length in bytes, its duration, and the
  SHA-256 of its audio, so a changed sound is seen. It is never decoded.
- **Raw data** (a colour lookup table, a font) is likewise its length and
  SHA-256, and its children.

A JSON object is a sub-property exactly when it has no `$type`. So that
nothing is read back as something else, a child can't be named `$type`, nor
after a typed object's own keys (`image`, `w` and `h` in a canvas). The client
has no such child; `encode_tree` raises `UnstorableNode` if one appears.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from game_data.archive import (
    CanvasNode,
    ConvexNode,
    DoubleNode,
    FloatNode,
    IntNode,
    LongNode,
    Node,
    NullNode,
    PropertyNode,
    RawDataNode,
    ShortNode,
    SoundNode,
    StringNode,
    UolNode,
    VectorNode,
)

type Json = None | int | float | str | list[Json] | dict[str, Json]

TYPE = "$type"


@dataclass(frozen=True, slots=True)
class CanvasImage:
    """
    A canvas's entry in the image store.

    :ivar name: The image's name, or `None` when its pixels can't be found.
    :ivar width: In pixels.
    :ivar height: In pixels.
    """

    name: str | None
    width: int
    height: int


class UnstorableNode(Exception):
    """
    A node the JSON can't hold without ambiguity.

    :param node: Its path inside the image.
    """

    def __init__(self, node: str, reason: str) -> None:
        self.node = node
        super().__init__(f"node {node}: {reason}")


def encode_tree(
    tree: PropertyNode,
    *,
    canvas: Callable[[str, CanvasNode], CanvasImage],
    payload_sha256: Callable[[int, int], str],
) -> dict[str, Json]:
    """
    An image's tree as JSON.

    :param canvas: Gives a canvas's image, from its path inside the image.
    :param payload_sha256: Gives the SHA-256 of a sound's or raw data's bytes,
        from the `offset` and `length` of its reference.
    :raises UnstorableNode: A child's name is reserved (see above).
    """
    encoder = _Encoder(canvas, payload_sha256)
    return encoder.children(tree, "", ())


def dumps(tree: dict[str, Json]) -> str:
    """The JSON text stored for a tree: compact, and the same for equal trees."""
    return json.dumps(tree, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class _Encoder:
    def __init__(
        self,
        canvas: Callable[[str, CanvasNode], CanvasImage],
        payload_sha256: Callable[[int, int], str],
    ) -> None:
        self._canvas = canvas
        self._payload_sha256 = payload_sha256

    def children(
        self, node: Node, path: str, reserved: tuple[str, ...]
    ) -> dict[str, Json]:
        out: dict[str, Json] = {}
        for name, child in node.children.items():
            child_path = f"{path}/{name}" if path else name
            if name == TYPE or name in reserved:
                raise UnstorableNode(
                    child_path, f"the name {name!r} is reserved in the raw layer"
                )
            out[name] = self.node(child, child_path)
        return out

    def node(self, node: Node, path: str) -> Json:
        match node:
            case PropertyNode():
                return self.children(node, path, ())
            case IntNode():
                return node.value
            case DoubleNode():
                return float(node.value)
            case StringNode():
                return node.value
            case NullNode():
                return None
            case ShortNode():
                return {TYPE: "short", "value": node.value}
            case LongNode():
                return {TYPE: "long", "value": node.value}
            case FloatNode():
                return {TYPE: "float", "value": node.value}
            case VectorNode():
                return {TYPE: "vector", "x": node.x, "y": node.y}
            case UolNode():
                return {TYPE: "uol", "path": node.path}
            case CanvasNode():
                image = self._canvas(path, node)
                head: dict[str, Json] = {
                    TYPE: "canvas",
                    "image": image.name,
                    "w": image.width,
                    "h": image.height,
                }
                return head | self.children(node, path, ("image", "w", "h"))
            case ConvexNode():
                return {TYPE: "convex"} | self.children(node, path, ())
            case SoundNode():
                sound = node.sound
                return {
                    TYPE: "sound",
                    "duration_ms": sound.duration_ms,
                    "length": sound.length,
                    "sha256": self._payload_sha256(sound.offset, sound.length),
                }
            case RawDataNode():
                data = node.data
                head = {
                    TYPE: "raw_data",
                    "length": data.length,
                    "sha256": self._payload_sha256(data.offset, data.length),
                }
                return head | self.children(node, path, ("length", "sha256"))
            case _:
                raise UnstorableNode(path, f"unknown node type {node.type}")
