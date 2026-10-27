"""
Reads the client's archives into typed property trees.

This layer turns bytes into trees and knows nothing about the game: it has no
idea what a map or a mob is. The public API:

- `ClientData(data)`: the whole `MSCW\\Data` folder as one namespace.
  `directory`, `image`, `node` and `resolve` take paths such as
  `Map/Map/Map0/000001000.img/info/bgm`, and `resolve` follows links (`client`).
- `Directory` and `Image`: what the namespace holds. A directory lists its
  `directories` and `images`. An image knows its `archive` and its `entry`,
  and `parse()` returns its tree.
- `WzArchive`: one `.wz` file, its version detected from the header, and its
  directory (`wz`). `WzDirectory` and `ImageEntry` are that directory.
- `MsPack`: one `.ms` pack, v2 (ChaCha20), with its entry table (`ms`).
  `PackEntry` is one entry. `ChaCha20` is the cipher (`chacha20`).
- `parse_image`: one image's bytes to its tree (`image`).
- The nodes of the tree, one class per WZ property type, all subclasses of
  `Node` (`nodes`). `CanvasRef`, `SoundRef` and `RawDataRef` say where
  pixels, audio and raw bytes are without decoding them.
- The errors (`errors`): `ArchiveError`, the base, names the archive, the image
  and the node path. `CorruptArchive` is malformed or truncated input,
  `UnsupportedFormat` a known format this reader doesn't implement, and
  `NodeNotFound` a path that names nothing. Nothing returns a partial tree.
"""

from .chacha20 import ChaCha20
from .client import ClientData, Directory, Image
from .errors import ArchiveError, CorruptArchive, NodeNotFound, UnsupportedFormat
from .image import parse_image
from .ms import MsPack, PackEntry
from .nodes import (
    CanvasNode,
    CanvasRef,
    ConvexNode,
    DoubleNode,
    FloatNode,
    IntNode,
    LongNode,
    Node,
    NodeType,
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
from .wz import ImageEntry, WzArchive, WzDirectory

__all__ = [
    "ArchiveError",
    "CanvasNode",
    "CanvasRef",
    "ChaCha20",
    "ClientData",
    "ConvexNode",
    "CorruptArchive",
    "Directory",
    "DoubleNode",
    "FloatNode",
    "Image",
    "ImageEntry",
    "IntNode",
    "LongNode",
    "MsPack",
    "Node",
    "NodeNotFound",
    "NodeType",
    "NullNode",
    "PackEntry",
    "PropertyNode",
    "RawDataNode",
    "RawDataRef",
    "ShortNode",
    "SoundNode",
    "SoundRef",
    "StringNode",
    "UnsupportedFormat",
    "UolNode",
    "VectorNode",
    "WzArchive",
    "WzDirectory",
    "parse_image",
]
