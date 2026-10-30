# Ported from wzlib-rs, `src/crypto/chacha20.rs`, which `src/wz/ms_file.rs`
# uses (https://github.com/apredovic419/wzlib-rs, commit 0463e2e). MIT License,
# Copyright (c) 2026 wzlib-rs contributors: the permission notice is in that
# repository's LICENSE file, and applies to this file's ported parts.
"""
ChaCha20 (RFC 8439), in pure Python, as `.ms` packs use it.

`ChaCha20(key, nonce, counter)` produces the keystream from block `counter`,
and `process` XORs it into data. Two details follow wzlib-rs rather than the
RFC:

- **The counter carries.** When the 32-bit block counter wraps, it carries into
  the first nonce word. The RFC leaves a wrap undefined, and no RFC vector
  reaches one.
- **`reset_counter`** rewinds to the counter the cipher started at, which the
  pack's entry table needs (`ms._EntryTable`).
"""

import struct

KEY_SIZE = 32
NONCE_SIZE = 12
BLOCK_SIZE = 64

_MASK = 0xFFFFFFFF
# "expand 32-byte k", as four little-endian words.
_CONSTANTS = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)
_WORDS = struct.Struct("<16I")


def chacha20_block(state: list[int]) -> bytes:
    """
    One 64-byte keystream block for a 16-word state (RFC 8439 §2.3).

    The rounds are unrolled into locals: a list-indexed quarter round is
    several times slower in CPython.
    """
    x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12, x13, x14, x15 = state
    for _ in range(10):
        # Columns.
        x0 = (x0 + x4) & _MASK
        x12 ^= x0
        x12 = ((x12 << 16) | (x12 >> 16)) & _MASK
        x8 = (x8 + x12) & _MASK
        x4 ^= x8
        x4 = ((x4 << 12) | (x4 >> 20)) & _MASK
        x0 = (x0 + x4) & _MASK
        x12 ^= x0
        x12 = ((x12 << 8) | (x12 >> 24)) & _MASK
        x8 = (x8 + x12) & _MASK
        x4 ^= x8
        x4 = ((x4 << 7) | (x4 >> 25)) & _MASK

        x1 = (x1 + x5) & _MASK
        x13 ^= x1
        x13 = ((x13 << 16) | (x13 >> 16)) & _MASK
        x9 = (x9 + x13) & _MASK
        x5 ^= x9
        x5 = ((x5 << 12) | (x5 >> 20)) & _MASK
        x1 = (x1 + x5) & _MASK
        x13 ^= x1
        x13 = ((x13 << 8) | (x13 >> 24)) & _MASK
        x9 = (x9 + x13) & _MASK
        x5 ^= x9
        x5 = ((x5 << 7) | (x5 >> 25)) & _MASK

        x2 = (x2 + x6) & _MASK
        x14 ^= x2
        x14 = ((x14 << 16) | (x14 >> 16)) & _MASK
        x10 = (x10 + x14) & _MASK
        x6 ^= x10
        x6 = ((x6 << 12) | (x6 >> 20)) & _MASK
        x2 = (x2 + x6) & _MASK
        x14 ^= x2
        x14 = ((x14 << 8) | (x14 >> 24)) & _MASK
        x10 = (x10 + x14) & _MASK
        x6 ^= x10
        x6 = ((x6 << 7) | (x6 >> 25)) & _MASK

        x3 = (x3 + x7) & _MASK
        x15 ^= x3
        x15 = ((x15 << 16) | (x15 >> 16)) & _MASK
        x11 = (x11 + x15) & _MASK
        x7 ^= x11
        x7 = ((x7 << 12) | (x7 >> 20)) & _MASK
        x3 = (x3 + x7) & _MASK
        x15 ^= x3
        x15 = ((x15 << 8) | (x15 >> 24)) & _MASK
        x11 = (x11 + x15) & _MASK
        x7 ^= x11
        x7 = ((x7 << 7) | (x7 >> 25)) & _MASK

        # Diagonals.
        x0 = (x0 + x5) & _MASK
        x15 ^= x0
        x15 = ((x15 << 16) | (x15 >> 16)) & _MASK
        x10 = (x10 + x15) & _MASK
        x5 ^= x10
        x5 = ((x5 << 12) | (x5 >> 20)) & _MASK
        x0 = (x0 + x5) & _MASK
        x15 ^= x0
        x15 = ((x15 << 8) | (x15 >> 24)) & _MASK
        x10 = (x10 + x15) & _MASK
        x5 ^= x10
        x5 = ((x5 << 7) | (x5 >> 25)) & _MASK

        x1 = (x1 + x6) & _MASK
        x12 ^= x1
        x12 = ((x12 << 16) | (x12 >> 16)) & _MASK
        x11 = (x11 + x12) & _MASK
        x6 ^= x11
        x6 = ((x6 << 12) | (x6 >> 20)) & _MASK
        x1 = (x1 + x6) & _MASK
        x12 ^= x1
        x12 = ((x12 << 8) | (x12 >> 24)) & _MASK
        x11 = (x11 + x12) & _MASK
        x6 ^= x11
        x6 = ((x6 << 7) | (x6 >> 25)) & _MASK

        x2 = (x2 + x7) & _MASK
        x13 ^= x2
        x13 = ((x13 << 16) | (x13 >> 16)) & _MASK
        x8 = (x8 + x13) & _MASK
        x7 ^= x8
        x7 = ((x7 << 12) | (x7 >> 20)) & _MASK
        x2 = (x2 + x7) & _MASK
        x13 ^= x2
        x13 = ((x13 << 8) | (x13 >> 24)) & _MASK
        x8 = (x8 + x13) & _MASK
        x7 ^= x8
        x7 = ((x7 << 7) | (x7 >> 25)) & _MASK

        x3 = (x3 + x4) & _MASK
        x14 ^= x3
        x14 = ((x14 << 16) | (x14 >> 16)) & _MASK
        x9 = (x9 + x14) & _MASK
        x4 ^= x9
        x4 = ((x4 << 12) | (x4 >> 20)) & _MASK
        x3 = (x3 + x4) & _MASK
        x14 ^= x3
        x14 = ((x14 << 8) | (x14 >> 24)) & _MASK
        x9 = (x9 + x14) & _MASK
        x4 ^= x9
        x4 = ((x4 << 7) | (x4 >> 25)) & _MASK
    mixed = (x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12, x13, x14, x15)
    return _WORDS.pack(*((a + b) & _MASK for a, b in zip(mixed, state, strict=True)))


class ChaCha20:
    """
    The ChaCha20 keystream for one key and nonce, from a starting block.

    :param key: 32 bytes.
    :param nonce: 12 bytes.
    :param counter: The first block's number.
    :raises ValueError: The key or nonce is the wrong size.
    """

    __slots__ = ("_initial", "_state")

    def __init__(self, key: bytes, nonce: bytes, counter: int = 0) -> None:
        if len(key) != KEY_SIZE:
            raise ValueError(f"a ChaCha20 key is {KEY_SIZE} bytes, not {len(key)}")
        if len(nonce) != NONCE_SIZE:
            raise ValueError(
                f"a ChaCha20 nonce is {NONCE_SIZE} bytes, not {len(nonce)}"
            )
        self._state = [
            *_CONSTANTS,
            *struct.unpack("<8I", key),
            counter & _MASK,
            *struct.unpack("<3I", nonce),
        ]
        self._initial = counter & _MASK

    @property
    def counter(self) -> int:
        """The next block's number."""
        return self._state[12]

    def reset_counter(self) -> None:
        """Rewinds to the block the cipher started at."""
        self._state[12] = self._initial

    def keystream(self, size: int) -> bytes:
        """The next `size` bytes of keystream, which use whole blocks."""
        blocks: list[bytes] = []
        state = self._state
        for _ in range(-(-size // BLOCK_SIZE)):
            blocks.append(chacha20_block(state))
            state[12] = (state[12] + 1) & _MASK
            if state[12] == 0:
                state[13] = (state[13] + 1) & _MASK
        return b"".join(blocks)[:size]

    def process(self, data: bytes) -> bytes:
        """
        `data` XORed with the next keystream. A partial last block uses up its
        whole block, as the RFC's does.
        """
        size = len(data)
        if size == 0:
            return b""
        stream = int.from_bytes(self.keystream(size), "little")
        return (int.from_bytes(data, "little") ^ stream).to_bytes(size, "little")
