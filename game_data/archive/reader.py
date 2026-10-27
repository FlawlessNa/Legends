"""
Bounds-checked little-endian reads, and the WZ encodings built on them.

`ByteReader` raises `OutOfBounds` instead of returning short data, so a
truncated file can't parse to a partial tree. `OutOfBounds` and `BadFormat`
carry no location: the parser that catches them knows the archive, image and
node, and re-raises them as `CorruptArchive`.
"""

import struct
from collections.abc import Buffer

_S8 = struct.Struct("<b")
_U16 = struct.Struct("<H")
_S16 = struct.Struct("<h")
_I32 = struct.Struct("<i")
_U32 = struct.Struct("<I")
_I64 = struct.Struct("<q")
_U64 = struct.Struct("<Q")
_F32 = struct.Struct("<f")
_F64 = struct.Struct("<d")


class BadFormat(Exception):
    """The bytes are there, but they don't follow the format."""


class OutOfBounds(BadFormat):
    """A read ran past the end of the data."""


class ByteReader:
    """
    Reads from a buffer at a cursor, `pos`, which every read advances.

    :param data: Any buffer: `bytes`, or an `mmap` of a whole archive.
    :param pos: Where the cursor starts.
    """

    __slots__ = ("_view", "pos")

    def __init__(self, data: Buffer, pos: int = 0) -> None:
        self._view = memoryview(data)
        self.pos = pos

    def release(self) -> None:
        """Lets go of the buffer, which an `mmap` needs before it can close."""
        self._view.release()

    def __len__(self) -> int:
        return len(self._view)

    def _take(self, size: int) -> int:
        start = self.pos
        if start < 0 or start + size > len(self._view):
            raise OutOfBounds(
                f"needs {size} bytes at offset {start}, "
                f"but the data is {len(self._view)} bytes"
            )
        self.pos = start + size
        return start

    def seek(self, pos: int) -> None:
        """Moves the cursor, which must stay within the data."""
        if not 0 <= pos <= len(self._view):
            raise OutOfBounds(
                f"offset {pos} is outside the data's {len(self._view)} bytes"
            )
        self.pos = pos

    def u8(self) -> int:
        return self._view[self._take(1)]

    def s8(self) -> int:
        return _S8.unpack_from(self._view, self._take(1))[0]

    def u16(self) -> int:
        return _U16.unpack_from(self._view, self._take(2))[0]

    def s16(self) -> int:
        return _S16.unpack_from(self._view, self._take(2))[0]

    def i32(self) -> int:
        return _I32.unpack_from(self._view, self._take(4))[0]

    def u32(self) -> int:
        return _U32.unpack_from(self._view, self._take(4))[0]

    def i64(self) -> int:
        return _I64.unpack_from(self._view, self._take(8))[0]

    def u64(self) -> int:
        return _U64.unpack_from(self._view, self._take(8))[0]

    def f32(self) -> float:
        return _F32.unpack_from(self._view, self._take(4))[0]

    def f64(self) -> float:
        return _F64.unpack_from(self._view, self._take(8))[0]

    def raw(self, size: int) -> bytes:
        start = self._take(size)
        return bytes(self._view[start : start + size])

    def compressed_int(self) -> int:
        """A signed byte, or, when the byte is -128, the `int32` after it."""
        value = self.s8()
        return self.i32() if value == -128 else value

    def compressed_long(self) -> int:
        """A signed byte, or, when the byte is -128, the `int64` after it."""
        value = self.s8()
        return self.i64() if value == -128 else value

    def wz_string(self) -> str:
        """
        A length-prefixed, XOR-masked string.

        The length is a signed byte. Positive is that many UTF-16 code units,
        each masked by `0xAAAA`, incremented per unit. Negative is that many
        bytes, each masked by `0xAA`, incremented per byte. 127 and -128 mean
        the true length follows as an `int32`. Classic's string key is zero, so
        the mask is the whole decryption.
        """
        length = self.s8()
        if length == 0:
            return ""
        if length > 0:
            if length == 127:
                length = self.i32()
            if length <= 0:
                raise BadFormat(f"a UTF-16 string has length {length}")
            start = self._take(2 * length)
            return _unmask(self._view[start : start + 2 * length], 2).decode(
                "utf-16-le", "surrogatepass"
            )
        length = self.i32() if length == -128 else -length
        if length <= 0:
            raise BadFormat(f"a byte string has length {length}")
        start = self._take(length)
        return _unmask(self._view[start : start + length], 1).decode("latin-1")


def _mask(width: int, count: int) -> bytes:
    """`count` masks of `width` bytes: `0xAA` or `0xAAAA`, then each one plus 1."""
    start, limit = (0xAA, 0x100) if width == 1 else (0xAAAA, 0x10000)
    return b"".join(
        ((start + i) % limit).to_bytes(width, "little") for i in range(count)
    )


# Long enough for any string the client stores. A longer one builds its own.
_MASKS = {1: _mask(1, 8192), 2: _mask(2, 4096)}


def _unmask(data: memoryview, width: int) -> bytes:
    """XORs `data` with the incrementing mask for `width`-byte units."""
    size = len(data)
    mask = _MASKS[width]
    if size > len(mask):
        mask = _mask(width, size // width)
    value = int.from_bytes(data, "little") ^ int.from_bytes(mask[:size], "little")
    return value.to_bytes(size, "little")
