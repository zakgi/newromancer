# SPDX-License-Identifier: MIT
"""The offset table that opens every big* resource file, and the shared decoding error.

Layout (Observed in bigpic0158, bigpic2, bigAIpic, bigRnnd, bigRnnt, bigText, bigdb and
bigIceData of the original disk):

    0x00: uint32 big-endian file offset of asset 0
    0x04: uint32 big-endian file offset of asset 1
    ...
    n*4:  uint32 zero, ending the table

Every offset lies between the end of the table and the end of the file. In the original
files the first offset equals the end of the table and the offsets ascend; neither property
is required here.
"""

from __future__ import annotations

import struct

OFFSET_FORMAT: str = ">I"
OFFSET_SIZE: int = struct.calcsize(OFFSET_FORMAT)


class FormatError(Exception):
    """Malformed or unsupported resource data."""


def read_offset_table(data: bytes, offset: int = 0) -> tuple[int, ...]:
    """Read big-endian 32-bit offsets from `offset` up to the terminating zero entry."""
    if not 0 <= offset <= len(data):
        raise FormatError(f"Offset table: start 0x{offset:X} lies outside {len(data)} bytes")
    offsets: list[int] = []
    position: int = offset
    value: int = -1
    while value != 0:
        if position + OFFSET_SIZE > len(data):
            raise FormatError(f"Offset table: no terminating zero before 0x{position:X}")
        (value,) = struct.unpack_from(OFFSET_FORMAT, data, position)
        position += OFFSET_SIZE
        if value != 0:
            offsets.append(value)
    table_end: int = position
    index: int
    entry: int
    for index, entry in enumerate(offsets):
        if not table_end <= entry < len(data):
            raise FormatError(
                f"Offset table: entry {index} at 0x{offset + index * OFFSET_SIZE:X} points to 0x{entry:X},"
                f" outside 0x{table_end:X}..0x{len(data):X}"
            )
    return tuple(offsets)
