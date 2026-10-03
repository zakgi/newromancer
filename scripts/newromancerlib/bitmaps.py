# SPDX-License-Identifier: MIT
"""Static pictures: room backgrounds (bigpic0158), game graphics (bigpic2) and AI faces (bigAIpic).

Each picture is one Huffman stream at the offset its file's offset table gives. The stream
yields a 64-byte palette, then the picture data. A decode type, which the files do not store,
selects how the data becomes pixels:

    type  run-length  XOR lines  layout
    0     none        yes        planar
    1     rows        yes        planar
    2     columns     yes        planar
    3     columns     no         planar
    4     none        yes        chunky
    5     rows        yes        chunky
    6     columns     yes        chunky
    7     rows        no         chunky
    8     columns     no         chunky

Planar data holds five bitplanes one after the other; bit n of a pixel's color index comes
from plane n. Chunky data holds one byte per pixel, and the color index is that byte's low
five bits in reverse order. A row is width / 8 bytes per plane in planar data and width bytes
in chunky data.

Run-length data is a sequence of records. A byte n in 1..127 repeats the following byte n
times; a byte 0x80 | n with n in 1..127 copies the following n bytes; 0x00 and 0x80 end the
data, as does a full output. Row order fills the output in sequence; column order fills each
plane column by column, each column top to bottom. Bytes past the end of the output are
dropped, and output the records do not reach stays zero.

XOR lines: within each plane, every row from the second down is XORed with the already
decoded row above it.

Palette: 32 big-endian words 0x0RGB, four bits per channel.

Usage:
    picture = Picture.from_stream(stream_bytes, GAME_GRAPHICS[0])
    png_bytes = picture.to_png()
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum
from io import BytesIO

import png

from .containers import FormatError
from .huffman import HuffmanStream

PALETTE_SIZE: int = 64
PALETTE_FORMAT: str = ">32H"
PLANE_COUNT: int = 5
INDEX_BITS: int = 5


class RunLength(Enum):
    NONE = "none"
    ROWS = "rows"
    COLUMNS = "columns"


@dataclass(frozen=True)
class DecodeType:
    run_length: RunLength
    xor_lines: bool
    planar: bool


DECODE_TYPES: tuple[DecodeType, ...] = (
    DecodeType(run_length=RunLength.NONE, xor_lines=True, planar=True),
    DecodeType(run_length=RunLength.ROWS, xor_lines=True, planar=True),
    DecodeType(run_length=RunLength.COLUMNS, xor_lines=True, planar=True),
    DecodeType(run_length=RunLength.COLUMNS, xor_lines=False, planar=True),
    DecodeType(run_length=RunLength.NONE, xor_lines=True, planar=False),
    DecodeType(run_length=RunLength.ROWS, xor_lines=True, planar=False),
    DecodeType(run_length=RunLength.COLUMNS, xor_lines=True, planar=False),
    DecodeType(run_length=RunLength.ROWS, xor_lines=False, planar=False),
    DecodeType(run_length=RunLength.COLUMNS, xor_lines=False, planar=False),
)


@dataclass(frozen=True)
class PictureLayout:
    """Picture size in pixels, decode type, and the number of data bytes taken from the stream."""

    width: int
    height: int
    decode_type: int
    decode_length: int


FULL_DECODE_LENGTH: int = 64000

ROOM_COUNT: int = 58
ROOM_WIDTH: int = 304
ROOM_HEIGHT: int = 112

# Decode type of each room's background, rooms 1 to 58; None for rooms without one.
ROOM_PICTURE_TYPES: tuple[int | None, ...] = (
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 3, 3, 5, 3, 2, 2, 5, 5,
    5, 5, 4, 2, 5, 3, 5, None, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, None, 1, 5, 5, 5, None, 5, 4,
    5, 7, 5, 5, 5, 5, 5, 5,
)  # fmt: skip

# Game graphics, numbered from 1 in file order.
GAME_GRAPHICS: tuple[PictureLayout, ...] = (
    PictureLayout(width=320, height=200, decode_type=2, decode_length=FULL_DECODE_LENGTH),  # 1: splash screen
    PictureLayout(width=288, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 2: walking left/right
    PictureLayout(width=288, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 3: walking up/down
    PictureLayout(width=160, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 4: walking up, head
    PictureLayout(width=160, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 5: walking down, head
    PictureLayout(width=160, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 6: walking right, head
    PictureLayout(width=160, height=130, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 7: walking left, head
    PictureLayout(width=256, height=65, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 8: turning by 45 degrees
    PictureLayout(width=320, height=200, decode_type=5, decode_length=FULL_DECODE_LENGTH),  # 9: dashboard and frame
    PictureLayout(width=64, height=19, decode_type=8, decode_length=1216),  # 10: balloon ends
    PictureLayout(width=320, height=200, decode_type=3, decode_length=FULL_DECODE_LENGTH),  # 11: cyberspace dashboard
    PictureLayout(width=320, height=200, decode_type=7, decode_length=FULL_DECODE_LENGTH),  # 12: database shapes
    PictureLayout(width=320, height=200, decode_type=3, decode_length=FULL_DECODE_LENGTH),  # 13: more shapes
    PictureLayout(width=320, height=200, decode_type=8, decode_length=FULL_DECODE_LENGTH),  # 14: ICE and EEG
    PictureLayout(width=320, height=200, decode_type=7, decode_length=FULL_DECODE_LENGTH),  # 15: unknown use
)

AI_FACE_WIDTH: int = 72
AI_FACE_HEIGHT: int = 80

# Decode type of each AI face, numbered from 1 in file order.
AI_FACE_TYPES: tuple[int, ...] = (5, 7, 5, 7, 5, 5, 7, 7, 7, 5, 7, 7)


def room_layouts() -> tuple[tuple[int, PictureLayout], ...]:
    """(room number, layout) of each background in bigpic0158, in file order."""
    return tuple(
        (
            room,
            PictureLayout(
                width=ROOM_WIDTH,
                height=ROOM_HEIGHT,
                decode_type=decode_type,
                decode_length=FULL_DECODE_LENGTH,
            ),
        )
        for room, decode_type in enumerate(ROOM_PICTURE_TYPES, start=1)
        if decode_type is not None
    )


def ai_face_layouts() -> tuple[PictureLayout, ...]:
    """Layout of each face in bigAIpic, in file order."""
    return tuple(
        PictureLayout(
            width=AI_FACE_WIDTH,
            height=AI_FACE_HEIGHT,
            decode_type=decode_type,
            decode_length=AI_FACE_WIDTH * AI_FACE_HEIGHT,
        )
        for decode_type in AI_FACE_TYPES
    )


@dataclass(frozen=True)
class RunLengthResult:
    data: bytes
    consumed_bytes: int
    record_bytes: int

    @property
    def missing_bytes(self) -> int:
        return max(0, len(self.data) - self.record_bytes)

    @property
    def dropped_bytes(self) -> int:
        return max(0, self.record_bytes - len(self.data))


def decode_run_length(data: bytes, size: int, order: RunLength, row_bytes: int, height: int) -> RunLengthResult:
    """Expand run-length records into `size` bytes of planes `row_bytes` wide and `height` tall."""
    if order is RunLength.NONE:
        raise ValueError("Run-length decoding needs a row or column order")
    plane_size: int = row_bytes * height
    if plane_size <= 0 or size % plane_size:
        raise FormatError(f"Run-length: {size} bytes do not form planes of {row_bytes} x {height}")
    output: bytearray = bytearray(size)
    offset: int = 0
    record_bytes: int = 0
    count: int = -1
    values: bytes
    value: int
    plane: int
    remainder: int
    column: int
    row: int
    while count != 0 and record_bytes < size:
        if offset >= len(data):
            raise FormatError(f"Run-length: data ends at 0x{offset:X} after {record_bytes} of {size} bytes")
        control: int = data[offset]
        offset += 1
        count = control & 0x7F
        if count == 0:
            continue
        if control & 0x80:
            values = data[offset : offset + count]
            offset += count
        else:
            values = data[offset : offset + 1] * count
            offset += 1
        if len(values) < count:
            raise FormatError(f"Run-length: record at 0x{offset - 1:X} runs past the end of the data")
        for value in values:
            if record_bytes < size:
                if order is RunLength.ROWS:
                    output[record_bytes] = value
                else:
                    plane, remainder = divmod(record_bytes, plane_size)
                    column, row = divmod(remainder, height)
                    output[plane * plane_size + row * row_bytes + column] = value
            record_bytes += 1
    return RunLengthResult(data=bytes(output), consumed_bytes=offset, record_bytes=record_bytes)


def xor_adjacent_lines(data: bytes, row_bytes: int, height: int) -> bytes:
    """XOR every row, from the second down, with the already decoded row above it, plane by plane."""
    plane_size: int = row_bytes * height
    if plane_size <= 0 or len(data) % plane_size:
        raise FormatError(f"XOR lines: {len(data)} bytes do not form planes of {row_bytes} x {height}")
    output: bytearray = bytearray(data)
    plane_start: int
    row: int
    start: int
    previous: int
    current: int
    for plane_start in range(0, len(data), plane_size):
        previous = int.from_bytes(output[plane_start : plane_start + row_bytes], "big")
        for row in range(1, height):
            start = plane_start + row * row_bytes
            current = int.from_bytes(output[start : start + row_bytes], "big") ^ previous
            output[start : start + row_bytes] = current.to_bytes(row_bytes, "big")
            previous = current
    return bytes(output)


def planar_to_pixels(data: bytes, row_bytes: int, height: int) -> bytes:
    """Combine five planes, row-major and `row_bytes` wide, into one color index per pixel."""
    plane_size: int = row_bytes * height
    if len(data) != plane_size * PLANE_COUNT:
        raise FormatError(f"Planar: expected {plane_size * PLANE_COUNT} bytes, found {len(data)}")
    pixels: bytearray = bytearray(plane_size * 8)
    plane: int
    offset: int
    bits: int
    bit: int
    for plane in range(PLANE_COUNT):
        for offset in range(plane_size):
            bits = data[plane * plane_size + offset]
            for bit in range(8):
                if bits & (0x80 >> bit):
                    pixels[offset * 8 + bit] |= 1 << plane
    return bytes(pixels)


def reverse_index_bits(value: int) -> int:
    reversed_value: int = 0
    bit: int
    for bit in range(INDEX_BITS):
        reversed_value |= ((value >> bit) & 1) << (INDEX_BITS - 1 - bit)
    return reversed_value


CHUNKY_TO_INDEX: bytes = bytes(reverse_index_bits(value) for value in range(256))


def chunky_to_pixels(data: bytes) -> bytes:
    """Map each chunky byte to its color index: the low five bits in reverse order."""
    return data.translate(CHUNKY_TO_INDEX)


@dataclass(frozen=True)
class Palette:
    colors: tuple[int, ...]

    @staticmethod
    def from_data(data: bytes) -> Palette:
        if len(data) != PALETTE_SIZE:
            raise FormatError(f"Palette: expected {PALETTE_SIZE} bytes, found {len(data)}")
        return Palette(colors=struct.unpack(PALETTE_FORMAT, data))

    @property
    def rgb(self) -> tuple[tuple[int, int, int], ...]:
        """8-bit channels; each 4-bit channel scales by 17 so that 0xF becomes 0xFF."""
        return tuple(((color >> 8 & 0xF) * 17, (color >> 4 & 0xF) * 17, (color & 0xF) * 17) for color in self.colors)


@dataclass(frozen=True)
class Picture:
    width: int
    height: int
    pixels: bytes
    palette: Palette
    run_length: RunLengthResult | None

    @staticmethod
    def from_stream(data: bytes, layout: PictureLayout) -> Picture:
        if not 0 <= layout.decode_type < len(DECODE_TYPES):
            raise FormatError(f"Picture: unknown decode type {layout.decode_type}")
        decode_type: DecodeType = DECODE_TYPES[layout.decode_type]
        if decode_type.planar and layout.width % 8:
            raise FormatError(f"Picture: planar width {layout.width} is not a multiple of 8")
        stream: HuffmanStream = HuffmanStream.from_data(data)
        palette: Palette = Palette.from_data(stream.decode(PALETTE_SIZE))
        body: bytes = stream.decode(layout.decode_length)
        row_bytes: int = layout.width // 8 if decode_type.planar else layout.width
        size: int = row_bytes * layout.height * (PLANE_COUNT if decode_type.planar else 1)
        run_length: RunLengthResult | None = None
        planes: bytes
        if decode_type.run_length is RunLength.NONE:
            if len(body) < size:
                raise FormatError(f"Picture: {len(body)} data bytes, expected {size}")
            planes = body[:size]
        else:
            run_length = decode_run_length(body, size, decode_type.run_length, row_bytes, layout.height)
            planes = run_length.data
        if decode_type.xor_lines:
            planes = xor_adjacent_lines(planes, row_bytes, layout.height)
        pixels: bytes = (
            planar_to_pixels(planes, row_bytes, layout.height) if decode_type.planar else chunky_to_pixels(planes)
        )
        return Picture(
            width=layout.width,
            height=layout.height,
            pixels=pixels,
            palette=palette,
            run_length=run_length,
        )

    def to_png(self) -> bytes:
        """Write an 8-bit indexed PNG carrying all 32 palette entries."""
        writer: png.Writer = png.Writer(
            width=self.width,
            height=self.height,
            bitdepth=8,
            palette=list(self.palette.rgb),
        )
        output: BytesIO
        with BytesIO() as output:
            writer.write_array(output, self.pixels)
            return output.getvalue()
