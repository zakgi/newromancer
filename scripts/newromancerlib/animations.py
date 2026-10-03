# SPDX-License-Identifier: MIT
"""Room animation frames (bigRnnd).

The file's offset table has one entry per room, rooms 1 to 58 in order. The entry of a room
without animations is the two bytes 0x4E71. Any other entry is a zero-terminated table of
big-endian 32-bit frame offsets, relative to the start of the entry, followed by the frames.

A frame is one Huffman stream. Its first four decoded bytes are the width in bytes, the
height, x and y; five bitplanes of width x height bytes with XORed lines follow, laid out
like planar pictures (see bitmaps.py). The frame's top-left corner lies at (2 * x - 8, y - 8)
in the room's background, and the frame uses the background's palette.

A frame is either copied over the background or XORed onto it; the file does not record
which.

Usage:
    animations = RoomAnimations.from_entry(entry_bytes, room)
    picture = compose(background, animations.frames[0], BlitMode.XOR)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import pairwise

from .bitmaps import PLANE_COUNT, Picture, planar_to_pixels, xor_adjacent_lines
from .containers import FormatError, read_offset_table
from .huffman import HuffmanStream

EMPTY_ENTRY: bytes = b"\x4e\x71"
FRAME_HEADER_SIZE: int = 4
X_UNIT: int = 2
BACKGROUND_LEFT: int = 8
BACKGROUND_TOP: int = 8


class BlitMode(Enum):
    COPY = "copy"
    XOR = "xor"


@dataclass(frozen=True)
class AnimationFrame:
    width: int
    height: int
    x: int
    y: int
    pixels: bytes

    @staticmethod
    def from_stream(data: bytes) -> AnimationFrame:
        stream: HuffmanStream = HuffmanStream.from_data(data)
        header: bytes = stream.decode(FRAME_HEADER_SIZE)
        if len(header) < FRAME_HEADER_SIZE:
            raise FormatError(f"Animation frame: budget too small for the {FRAME_HEADER_SIZE}-byte header")
        row_bytes: int
        height: int
        x: int
        y: int
        row_bytes, height, x, y = header
        if row_bytes == 0 or height == 0:
            raise FormatError(f"Animation frame: empty size {row_bytes} x {height}")
        size: int = row_bytes * height * PLANE_COUNT
        planes: bytes = stream.decode(size)
        if len(planes) < size:
            raise FormatError(f"Animation frame: {len(planes)} data bytes, expected {size}")
        return AnimationFrame(
            width=row_bytes * 8,
            height=height,
            x=x,
            y=y,
            pixels=planar_to_pixels(xor_adjacent_lines(planes, row_bytes, height), row_bytes, height),
        )

    @property
    def left(self) -> int:
        """Column of the frame's left edge in the room background."""
        return X_UNIT * self.x - BACKGROUND_LEFT

    @property
    def top(self) -> int:
        """Row of the frame's top edge in the room background."""
        return self.y - BACKGROUND_TOP


@dataclass(frozen=True)
class RoomAnimations:
    room: int
    frames: tuple[AnimationFrame, ...]

    @staticmethod
    def from_entry(entry: bytes, room: int) -> RoomAnimations:
        frames: tuple[AnimationFrame, ...] = ()
        if entry != EMPTY_ENTRY:
            offsets: tuple[int, ...] = read_offset_table(entry) + (len(entry),)
            frames = tuple(AnimationFrame.from_stream(entry[start:end]) for start, end in pairwise(offsets))
        return RoomAnimations(room=room, frames=frames)


def compose(background: Picture, frame: AnimationFrame, mode: BlitMode) -> Picture:
    """Draw `frame` onto `background` by copy or XOR; parts outside the background are clipped."""
    pixels: bytearray = bytearray(background.pixels)
    first_row: int = max(0, -frame.top)
    last_row: int = min(frame.height, background.height - frame.top)
    first_column: int = max(0, -frame.left)
    last_column: int = min(frame.width, background.width - frame.left)
    row: int
    source: bytes
    start: int
    for row in range(first_row, last_row):
        source = frame.pixels[row * frame.width + first_column : row * frame.width + last_column]
        start = (frame.top + row) * background.width + frame.left + first_column
        if mode is BlitMode.XOR:
            source = bytes(value ^ target for value, target in zip(source, pixels[start : start + len(source)]))
        pixels[start : start + len(source)] = source
    return Picture(
        width=background.width,
        height=background.height,
        pixels=bytes(pixels),
        palette=background.palette,
        run_length=None,
    )
