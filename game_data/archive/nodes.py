"""
The typed property tree an image parses to.

An image is a tree of named nodes, one class per WZ property type:

| class          | WZ type            | carries                                 |
| -------------- | ------------------ | --------------------------------------- |
| `NullNode`     | null               | nothing                                 |
| `ShortNode`    | short              | `value: int`, 16-bit                    |
| `IntNode`      | int                | `value: int`, 32-bit                    |
| `LongNode`     | long               | `value: int`, 64-bit                    |
| `FloatNode`    | float              | `value: float`, 32-bit precision        |
| `DoubleNode`   | double             | `value: float`                          |
| `StringNode`   | string             | `value: str`                            |
| `PropertyNode` | sub-property       | `children`                              |
| `VectorNode`   | `Shape2D#Vector2D` | `x: int`, `y: int`                      |
| `UolNode`      | `UOL`              | `path: str`, a link to another node     |
| `CanvasNode`   | `Canvas`           | `canvas: CanvasRef`, and `children`     |
| `ConvexNode`   | `Shape2D#Convex2D` | `children`, named `"0"`, `"1"`, ...     |
| `SoundNode`    | `Sound_DX8`        | `sound: SoundRef`                       |
| `RawDataNode`  | `RawData`          | `data: RawDataRef`, and `children`      |

`RawData` isn't in the epic's list of types. The client stores two kinds of
image as raw bytes this way: a colour lookup table and a font.

Every node has a `name` and `children`, which is empty for all but the four
container types and keeps the order the archive stores. `node["a/b/0"]` walks
down by a `/`-separated path, and raises `KeyError` for a missing step.
`node.get(path)` returns `None` instead. Neither follows a `UolNode`:
`ClientData.resolve` does, because a link may leave the image.

Canvases, sounds and raw data are references, not data. `CanvasRef`,
`SoundRef` and `RawDataRef` say where the bytes are in the image's archive,
and nothing here decodes them.

All nodes are frozen dataclasses, so two trees compare equal when they hold the
same names, types and values in the same order.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar


class NodeType(StrEnum):
    """The WZ property type of a node, one per node class."""

    NULL = "null"
    SHORT = "short"
    INT = "int"
    LONG = "long"
    FLOAT = "float"
    DOUBLE = "double"
    STRING = "string"
    PROPERTY = "property"
    VECTOR = "vector"
    UOL = "uol"
    CANVAS = "canvas"
    CONVEX = "convex"
    SOUND = "sound"
    RAW_DATA = "raw_data"


_NO_CHILDREN: Mapping[str, Node] = MappingProxyType({})


class Node:
    """
    Base of every node. Don't instantiate it: use one of the subclasses.

    :ivar name: The node's name, which is also its key in its parent.
    :ivar children: The node's children by name, in archive order.
    :cvar type: The node's WZ property type.
    """

    __slots__ = ()

    type: ClassVar[NodeType]
    name: str
    children: Mapping[str, Node] = _NO_CHILDREN

    def __getitem__(self, path: str) -> Node:
        node: Node = self
        for step in path.split("/"):
            if step:
                node = node.children[step]
        return node

    def get(self, path: str) -> Node | None:
        """The node at `path` below this one, or `None` if there is none."""
        try:
            return self[path]
        except KeyError:
            return None

    def walk(self, prefix: str = "") -> Iterator[tuple[str, Node]]:
        """
        Every node below this one, depth first, with its path from here.

        :param prefix: Prepended to every path, with a `/`.
        """
        for name, child in self.children.items():
            path = f"{prefix}/{name}" if prefix else name
            yield path, child
            yield from child.walk(path)


@dataclass(frozen=True, slots=True, kw_only=True)
class CanvasRef:
    """
    Where a canvas's pixels are, undecoded.

    :ivar offset: The first byte of the pixel data, from the start of the
        archive file. It's the byte after the block's leading flag byte.
    :ivar length: The number of bytes of pixel data, flag byte excluded.
    :ivar format: The pixel format, as stored (1 is BGRA4444, 2 is BGRA8888).
    :ivar scale: The byte stored after the format, a power-of-two scale.
    :ivar width: In pixels.
    :ivar height: In pixels.
    """

    offset: int
    length: int
    format: int
    scale: int
    width: int
    height: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SoundRef:
    """
    Where a sound's audio is, undecoded.

    :ivar offset: The first byte of the audio data, from the start of the
        archive file, after the media-type header.
    :ivar length: The number of bytes of audio data.
    :ivar duration_ms: The sound's length, as stored.
    :ivar header_offset: The first byte of the media-type header, which
        describes the audio format, from the start of the archive file.
    :ivar header_length: The header's length in bytes.
    """

    offset: int
    length: int
    duration_ms: int
    header_offset: int
    header_length: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RawDataRef:
    """
    Where a block of raw bytes is, uninterpreted.

    :ivar offset: The first byte, from the start of the archive file.
    :ivar length: The number of bytes.
    """

    offset: int
    length: int


@dataclass(frozen=True, slots=True, kw_only=True)
class NullNode(Node):
    """A property with a name and no value."""

    type: ClassVar[NodeType] = NodeType.NULL
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ShortNode(Node):
    """A 16-bit signed integer."""

    type: ClassVar[NodeType] = NodeType.SHORT
    name: str
    value: int


@dataclass(frozen=True, slots=True, kw_only=True)
class IntNode(Node):
    """A 32-bit signed integer."""

    type: ClassVar[NodeType] = NodeType.INT
    name: str
    value: int


@dataclass(frozen=True, slots=True, kw_only=True)
class LongNode(Node):
    """A 64-bit signed integer."""

    type: ClassVar[NodeType] = NodeType.LONG
    name: str
    value: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FloatNode(Node):
    """A 32-bit float, widened to a Python `float`."""

    type: ClassVar[NodeType] = NodeType.FLOAT
    name: str
    value: float


@dataclass(frozen=True, slots=True, kw_only=True)
class DoubleNode(Node):
    """A 64-bit float."""

    type: ClassVar[NodeType] = NodeType.DOUBLE
    name: str
    value: float


@dataclass(frozen=True, slots=True, kw_only=True)
class StringNode(Node):
    """A string."""

    type: ClassVar[NodeType] = NodeType.STRING
    name: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PropertyNode(Node):
    """A sub-property: a named group of children. An image's root is one."""

    type: ClassVar[NodeType] = NodeType.PROPERTY
    name: str
    children: Mapping[str, Node]


@dataclass(frozen=True, slots=True, kw_only=True)
class VectorNode(Node):
    """A 2D point."""

    type: ClassVar[NodeType] = NodeType.VECTOR
    name: str
    x: int
    y: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UolNode(Node):
    """
    A link to another node.

    :ivar path: Relative to the link's parent node: `../move/0` names the
        sibling `move/0` of the link's parent. `ClientData.resolve` follows it.
    """

    type: ClassVar[NodeType] = NodeType.UOL
    name: str
    path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CanvasNode(Node):
    """An image, by reference, with its own properties (`origin`, `delay`...)."""

    type: ClassVar[NodeType] = NodeType.CANVAS
    name: str
    canvas: CanvasRef
    children: Mapping[str, Node]


@dataclass(frozen=True, slots=True, kw_only=True)
class ConvexNode(Node):
    """A convex shape: its points as children, usually `VectorNode`s."""

    type: ClassVar[NodeType] = NodeType.CONVEX
    name: str
    children: Mapping[str, Node]


@dataclass(frozen=True, slots=True, kw_only=True)
class SoundNode(Node):
    """A sound, by reference."""

    type: ClassVar[NodeType] = NodeType.SOUND
    name: str
    sound: SoundRef


@dataclass(frozen=True, slots=True, kw_only=True)
class RawDataNode(Node):
    """A block of bytes, by reference, with its own properties if it has any."""

    type: ClassVar[NodeType] = NodeType.RAW_DATA
    name: str
    data: RawDataRef
    children: Mapping[str, Node]
