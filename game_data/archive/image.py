"""
Parses one image's bytes into its property tree.

An image is the unit the archive's directory points at, such as
`000001000.img`. Its bytes are an extended object, always a `Property`, whose
property list holds the tree.

- **String blocks** are a tag, then either the string itself (`0x00`, `0x73`)
  or an `int32` offset from the start of the image to where the string is
  (`0x01`, `0x1B`).
- **A property** is a string-block name, a type byte, then its value: null
  (0), short (2, 11), int (3, 19, compressed), long (20, compressed), float
  (4: `0x80` then the float, or `0x00` for zero), double (5), string (8), or
  an extended object (9: a `uint32` length, then the object).
- **An extended object** is a string-block type name, then its body:
  `Property`, `Canvas`, `Shape2D#Vector2D`, `Shape2D#Convex2D`, `UOL`,
  `Sound_DX8` or `RawData`.

The parse is strict. An unknown tag, type or name, a read past the end, or an
extended object that doesn't end exactly at its stated length raises
`CorruptArchive` naming the archive, the image and the node path. Nothing is
skipped and no partial tree is returned.
"""

from collections.abc import Buffer
from pathlib import Path

from .errors import CorruptArchive
from .nodes import (
    CanvasNode,
    CanvasRef,
    ConvexNode,
    DoubleNode,
    FloatNode,
    IntNode,
    LongNode,
    Node,
    NullNode,
    PropertyNode,
    RawDataNode,
    RawDataRef,
    ShortNode,
    SoundNode,
    SoundRef,
    StringNode,
    UolNode,
    VectorNode,
)
from .reader import BadFormat, ByteReader

_INLINE = frozenset({0x00, 0x73})
_OFFSET = frozenset({0x01, 0x1B})

# The fixed part of a Sound_DX8 header, before the byte that gives the length of
# the wave format after it: a tag byte, then the major type, subtype and format
# type GUIDs of a DirectShow media type, with two bytes between them.
_SOUND_HEADER = 51


def parse_image(
    data: Buffer,
    *,
    archive: Path | str,
    image: str,
    base: int = 0,
) -> PropertyNode:
    """
    The property tree of one image.

    :param data: The image's bytes, from its first byte to its last. String
        offsets inside the image count from `data[0]`.
    :param archive: The file the image comes from, for errors.
    :param image: The image's name, such as `000001000.img`, for errors.
    :param base: The offset of `data[0]` in the archive file. Canvas and sound
        references add it, so their offsets count from the start of the file.
    :raises CorruptArchive: The bytes don't follow the format.
    """
    parser = _ImageParser(data, base)
    try:
        root = parser.root()
    except BadFormat as error:
        raise CorruptArchive(archive, image, parser.where(), str(error)) from error
    return root


class _ImageParser:
    def __init__(self, data: Buffer, base: int) -> None:
        self._reader = ByteReader(data)
        self._base = base
        self._path: list[str] = []
        self._strings: dict[int, str] = {}

    def where(self) -> str:
        return "/".join(self._path)

    def root(self) -> PropertyNode:
        node = self._extended("")
        if not isinstance(node, PropertyNode):
            raise BadFormat(f"the image's root is a {node.type}, not a property")
        if self._reader.pos != len(self._reader):
            raise BadFormat(
                f"the tree ends at offset {self._reader.pos}, "
                f"but the image is {len(self._reader)} bytes"
            )
        return node

    def _string_block(self) -> str:
        reader = self._reader
        tag = reader.u8()
        if tag in _INLINE:
            return reader.wz_string()
        if tag in _OFFSET:
            offset = reader.i32()
            cached = self._strings.get(offset)
            if cached is not None:
                return cached
            resume = reader.pos
            reader.seek(offset)
            value = reader.wz_string()
            reader.seek(resume)
            self._strings[offset] = value
            return value
        raise BadFormat(f"unknown string block tag {tag:#04x}")

    def _property_list(self) -> dict[str, Node]:
        count = self._reader.compressed_int()
        if count < 0:
            raise BadFormat(f"a property list has {count} entries")
        children: dict[str, Node] = {}
        for _ in range(count):
            name = self._string_block()
            self._path.append(name)
            if name in children:
                raise BadFormat("the name appears twice in its parent")
            children[name] = self._property(name)
            self._path.pop()
        return children

    def _property(self, name: str) -> Node:
        reader = self._reader
        kind = reader.u8()
        match kind:
            case 0:
                return NullNode(name=name)
            case 2 | 11:
                return ShortNode(name=name, value=reader.s16())
            case 3 | 19:
                return IntNode(name=name, value=reader.compressed_int())
            case 20:
                return LongNode(name=name, value=reader.compressed_long())
            case 4:
                flag = reader.u8()
                if flag == 0x80:
                    return FloatNode(name=name, value=reader.f32())
                if flag == 0:
                    return FloatNode(name=name, value=0.0)
                raise BadFormat(f"unknown float tag {flag:#04x}")
            case 5:
                return DoubleNode(name=name, value=reader.f64())
            case 8:
                return StringNode(name=name, value=self._string_block())
            case 9:
                size = reader.u32()
                end = reader.pos + size
                node = self._extended(name)
                if reader.pos != end:
                    raise BadFormat(
                        f"the {node.type} ends at offset {reader.pos}, "
                        f"but its length says {end}"
                    )
                return node
            case _:
                raise BadFormat(f"unknown property type {kind}")

    def _extended(self, name: str) -> Node:
        reader = self._reader
        kind = self._string_block()
        match kind:
            case "Property":
                reader.u16()
                return PropertyNode(name=name, children=self._property_list())
            case "Canvas":
                return self._canvas(name)
            case "Shape2D#Vector2D":
                x = reader.compressed_int()
                return VectorNode(name=name, x=x, y=reader.compressed_int())
            case "Shape2D#Convex2D":
                count = reader.compressed_int()
                if count < 0:
                    raise BadFormat(f"a convex shape has {count} points")
                points: dict[str, Node] = {}
                for index in range(count):
                    self._path.append(str(index))
                    points[str(index)] = self._extended(str(index))
                    self._path.pop()
                return ConvexNode(name=name, children=points)
            case "UOL":
                reader.u8()
                return UolNode(name=name, path=self._string_block())
            case "Sound_DX8":
                return self._sound(name)
            case "RawData":
                return self._raw_data(name)
            case _:
                raise BadFormat(f"unknown extended object type {kind!r}")

    def _optional_properties(self, kind: str) -> dict[str, Node]:
        """The property list a canvas or raw data may carry, behind a flag."""
        reader = self._reader
        flag = reader.u8()
        if flag == 0:
            return {}
        if flag != 1:
            raise BadFormat(f"unknown {kind} property flag {flag}")
        reader.u16()
        return self._property_list()

    def _canvas(self, name: str) -> CanvasNode:
        reader = self._reader
        reader.u8()
        children = self._optional_properties("canvas")
        width = reader.compressed_int()
        height = reader.compressed_int()
        pixel_format = reader.compressed_int()
        scale = reader.u8()
        reader.i32()
        length = reader.i32()
        if width < 0 or height < 0 or length < 1:
            raise BadFormat(
                f"a canvas is {width}x{height} with {length} bytes of pixel data"
            )
        reader.u8()
        offset = reader.pos
        reader.seek(offset + length - 1)
        return CanvasNode(
            name=name,
            canvas=CanvasRef(
                offset=self._base + offset,
                length=length - 1,
                format=pixel_format,
                scale=scale,
                width=width,
                height=height,
            ),
            children=children,
        )

    def _sound(self, name: str) -> SoundNode:
        reader = self._reader
        reader.u8()
        length = reader.compressed_int()
        duration = reader.compressed_int()
        header_offset = reader.pos
        reader.seek(header_offset + _SOUND_HEADER)
        header_length = _SOUND_HEADER + 1 + reader.u8()
        offset = header_offset + header_length
        if length < 0:
            raise BadFormat(f"a sound has {length} bytes of audio")
        reader.seek(offset + length)
        return SoundNode(
            name=name,
            sound=SoundRef(
                offset=self._base + offset,
                length=length,
                duration_ms=duration,
                header_offset=self._base + header_offset,
                header_length=header_length,
            ),
        )

    def _raw_data(self, name: str) -> RawDataNode:
        reader = self._reader
        tag = reader.u8()
        if tag != 1:
            raise BadFormat(f"unknown raw data tag {tag}")
        children = self._optional_properties("raw data")
        length = reader.compressed_int()
        if length < 0:
            raise BadFormat(f"raw data has {length} bytes")
        offset = reader.pos
        reader.seek(offset + length)
        return RawDataNode(
            name=name,
            data=RawDataRef(offset=self._base + offset, length=length),
            children=children,
        )
