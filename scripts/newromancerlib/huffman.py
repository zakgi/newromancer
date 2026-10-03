# SPDX-License-Identifier: MIT
"""Huffman-coded streams.

Stream layout:

    0x00: uint32 big-endian decoded-byte budget. Successive `decode` calls on one stream
          yield at most this many bytes in total.
    0x04: uint32 big-endian, unused by the decoder.
    0x08: the code tree, then the coded bytes, as one bit stream of 16-bit big-endian
          words, most significant bit first.

Tree: pre-order. Bit 1 is a leaf followed by its 8-bit value, most significant bit first.
Bit 0 is an inner node followed by the subtree taken on a 0 bit, one ignored bit, and the
subtree taken on a 1 bit.

Decoding walks from the root, one bit per inner node, and yields the value of the leaf it
reaches. A stream whose bits run out before its budget is rejected.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .containers import FormatError

HEADER_FORMAT: str = ">II"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)
VALUE_BITS: int = 8
MAX_TREE_DEPTH: int = 255


@dataclass
class BitReader:
    """Most-significant-bit-first reader; `position` counts bits from the start of `data`."""

    data: bytes
    position: int = 0

    def read(self, width: int) -> int:
        if self.position + width > len(self.data) * 8:
            raise FormatError(f"Huffman: bit stream ends at bit offset {self.position}")
        value: int = 0
        for _ in range(width):
            value = (value << 1) | ((self.data[self.position // 8] >> (7 - self.position % 8)) & 1)
            self.position += 1
        return value


@dataclass
class HuffmanNode:
    value: int = 0
    zero: HuffmanNode | None = None
    one: HuffmanNode | None = None

    @staticmethod
    def from_bits(reader: BitReader, depth: int = 0) -> HuffmanNode:
        if depth > MAX_TREE_DEPTH:
            raise FormatError(f"Huffman: tree deeper than {MAX_TREE_DEPTH} at bit offset {reader.position}")
        node: HuffmanNode
        if reader.read(1):
            node = HuffmanNode(value=reader.read(VALUE_BITS))
        else:
            zero: HuffmanNode = HuffmanNode.from_bits(reader, depth + 1)
            reader.read(1)
            one: HuffmanNode = HuffmanNode.from_bits(reader, depth + 1)
            node = HuffmanNode(zero=zero, one=one)
        return node

    @property
    def is_leaf(self) -> bool:
        return self.zero is None


@dataclass
class HuffmanStream:
    """A coded stream with its tree read; `decode` continues where the previous call stopped."""

    budget: int
    reader: BitReader
    root: HuffmanNode

    @staticmethod
    def from_data(data: bytes) -> HuffmanStream:
        if len(data) < HEADER_SIZE:
            raise FormatError(f"Huffman: {len(data)} bytes cannot hold the {HEADER_SIZE}-byte stream header")
        budget: int
        budget, _ = struct.unpack_from(HEADER_FORMAT, data)
        reader: BitReader = BitReader(data=data, position=HEADER_SIZE * 8)
        root: HuffmanNode = HuffmanNode.from_bits(reader)
        return HuffmanStream(budget=budget, reader=reader, root=root)

    def decode(self, count: int) -> bytes:
        """Decode up to `count` bytes, fewer when the stream's budget runs out first."""
        length: int = min(count, self.budget)
        output: bytearray = bytearray()
        node: HuffmanNode
        while len(output) < length:
            node = self.root
            while not node.is_leaf:
                node = node.one if self.reader.read(1) else node.zero
            output.append(node.value)
        self.budget -= length
        return bytes(output)
