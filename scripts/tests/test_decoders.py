"""Synthetic boundary cases for the decoders; no game data needed."""

from __future__ import annotations

import io
import struct
import unittest
import wave

from newromancerlib.animations import AnimationFrame, BlitMode, RoomAnimations, compose
from newromancerlib.bitmaps import (
    Palette,
    Picture,
    PictureLayout,
    RunLength,
    RunLengthResult,
    chunky_to_pixels,
    decode_run_length,
    planar_to_pixels,
    xor_adjacent_lines,
)
from newromancerlib.containers import FormatError, read_offset_table
from newromancerlib.huffman import HuffmanStream
from newromancerlib.samples import NOMINAL_RATE_HZ, Sample
from newromancerlib.songs import NoteEvent, Song
from newromancerlib.text import TextTable, decode_string, read_word_list


def pack_bits(bits: str) -> bytes:
    """Most-significant-bit-first bytes, padded with zero bits to a whole 16-bit word."""
    padded: str = bits + "0" * (-len(bits) % 16)
    return int(padded, 2).to_bytes(len(padded) // 8, "big") if padded else b""


def tree_bits(prefix: int = 0, depth: int = 0) -> str:
    """A complete depth-8 code tree whose code for each byte is the byte itself."""
    bits: str
    if depth == 8:
        bits = "1" + f"{prefix:08b}"
    else:
        bits = "0" + tree_bits(prefix * 2, depth + 1) + "0" + tree_bits(prefix * 2 + 1, depth + 1)
    return bits


FULL_TREE: str = tree_bits()


def encode_stream(data: bytes, budget: int | None = None) -> bytes:
    bits: str = FULL_TREE + "".join(f"{value:08b}" for value in data)
    return struct.pack(">II", len(data) if budget is None else budget, len(bits) + 7) + pack_bits(bits)


def pack_codes(codes: list[int]) -> bytes:
    """5-bit codes packed least significant bit first, as in the text files."""
    value: int = 0
    code: int
    for index, code in enumerate(codes):
        value |= code << (5 * index)
    return value.to_bytes((5 * len(codes) + 7) // 8, "little")


def palette_bytes(colors: list[int]) -> bytes:
    return struct.pack(">32H", *(colors + [0] * (32 - len(colors))))


ALPHABET: bytes = (b"\0abcdefghijklmnopqrstuvwxyz .\n" + b"0123456789!?").ljust(60, b"#")


class ContainerTests(unittest.TestCase):
    def test_reads_offsets_up_to_the_zero_entry(self) -> None:
        data: bytes = struct.pack(">III", 12, 14, 0) + b"abcd"
        self.assertEqual(read_offset_table(data), (12, 14))

    def test_rejects_missing_terminator(self) -> None:
        with self.assertRaisesRegex(FormatError, "no terminating zero"):
            read_offset_table(struct.pack(">I", 8))

    def test_rejects_offsets_outside_the_data(self) -> None:
        with self.assertRaisesRegex(FormatError, "outside"):
            read_offset_table(struct.pack(">II", 4, 0) + b"xx")
        with self.assertRaisesRegex(FormatError, "outside"):
            read_offset_table(struct.pack(">II", 10, 0) + b"xx")


class HuffmanTests(unittest.TestCase):
    def test_successive_decodes_continue_the_stream(self) -> None:
        data: bytes = bytes(range(256))
        stream: HuffmanStream = HuffmanStream.from_data(encode_stream(data))
        self.assertEqual(stream.decode(10), data[:10])
        self.assertEqual(stream.decode(1000), data[10:])
        self.assertEqual(stream.decode(5), b"")

    def test_budget_limits_the_output(self) -> None:
        stream: HuffmanStream = HuffmanStream.from_data(encode_stream(b"abc", budget=2))
        self.assertEqual(stream.decode(10), b"ab")

    def test_single_leaf_tree_needs_no_bits(self) -> None:
        stream: HuffmanStream = HuffmanStream.from_data(struct.pack(">II", 3, 0) + pack_bits("1" + "01000001"))
        self.assertEqual(stream.decode(3), b"AAA")

    def test_rejects_streams_that_run_out(self) -> None:
        stream: HuffmanStream = HuffmanStream.from_data(encode_stream(b"abcdef")[:-4])
        with self.assertRaisesRegex(FormatError, "bit stream ends"):
            stream.decode(6)
        with self.assertRaisesRegex(FormatError, "stream header"):
            HuffmanStream.from_data(bytes(7))

    def test_rejects_overly_deep_trees(self) -> None:
        with self.assertRaisesRegex(FormatError, "deeper"):
            HuffmanStream.from_data(struct.pack(">II", 1, 0) + pack_bits("0" * 300))


class RunLengthTests(unittest.TestCase):
    def test_rows_repeat_and_copy(self) -> None:
        result: RunLengthResult = decode_run_length(bytes([3, 7, 0x82, 1, 2, 0]), 5, RunLength.ROWS, 5, 1)
        self.assertEqual(result.data, bytes([7, 7, 7, 1, 2]))
        self.assertEqual(result.consumed_bytes, 5)
        self.assertEqual((result.missing_bytes, result.dropped_bytes), (0, 0))

    def test_both_end_markers_leave_zeros(self) -> None:
        marker: int
        for marker in (0x00, 0x80):
            result: RunLengthResult = decode_run_length(bytes([2, 9, marker]), 4, RunLength.ROWS, 4, 1)
            self.assertEqual(result.data, bytes([9, 9, 0, 0]))
            self.assertEqual(result.missing_bytes, 2)

    def test_excess_bytes_are_dropped(self) -> None:
        result: RunLengthResult = decode_run_length(bytes([5, 4]), 3, RunLength.ROWS, 3, 1)
        self.assertEqual(result.data, bytes([4, 4, 4]))
        self.assertEqual(result.dropped_bytes, 2)

    def test_columns_fill_top_to_bottom(self) -> None:
        result: RunLengthResult = decode_run_length(bytes([0x84, 1, 2, 3, 4]), 4, RunLength.COLUMNS, 2, 2)
        self.assertEqual(result.data, bytes([1, 3, 2, 4]))

    def test_rejects_truncated_records(self) -> None:
        with self.assertRaisesRegex(FormatError, "past the end"):
            decode_run_length(bytes([0x83, 1]), 4, RunLength.ROWS, 4, 1)
        with self.assertRaisesRegex(FormatError, "data ends"):
            decode_run_length(bytes([2, 1]), 4, RunLength.ROWS, 4, 1)
        with self.assertRaises(ValueError):
            decode_run_length(bytes([2, 1]), 4, RunLength.NONE, 4, 1)


class PixelTests(unittest.TestCase):
    def test_xor_lines_accumulate_down_each_plane(self) -> None:
        self.assertEqual(xor_adjacent_lines(bytes([1, 2, 3, 4, 5, 6]), 2, 3), bytes([1, 2, 2, 6, 7, 0]))

    def test_plane_n_supplies_bit_n(self) -> None:
        planes: bytes = bytes([0x80, 0x80, 0x01, 0x01, 0x01])
        self.assertEqual(planar_to_pixels(planes, 1, 1), bytes([3, 0, 0, 0, 0, 0, 0, 28]))

    def test_chunky_bytes_reverse_their_low_five_bits(self) -> None:
        self.assertEqual(chunky_to_pixels(bytes([0x01, 0x10, 0x17, 0xE1])), bytes([0x10, 0x01, 0x1D, 0x10]))

    def test_palette_scales_four_bit_channels(self) -> None:
        palette: Palette = Palette.from_data(palette_bytes([0x0F00, 0x00F0, 0x000F, 0x0123]))
        self.assertEqual(palette.rgb[:4], ((255, 0, 0), (0, 255, 0), (0, 0, 255), (17, 34, 51)))
        with self.assertRaises(FormatError):
            Palette.from_data(bytes(63))

    def test_chunky_run_length_picture(self) -> None:
        stream: bytes = encode_stream(palette_bytes([0x0FFF]) + bytes([0x82, 0x01, 0x10]))
        picture: Picture = Picture.from_stream(
            stream, PictureLayout(width=2, height=1, decode_type=7, decode_length=100)
        )
        self.assertEqual(picture.pixels, bytes([0x10, 0x01]))
        self.assertTrue(picture.to_png().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_planar_picture_with_xor_lines(self) -> None:
        planes: bytes = bytes([0xFF, 0x00]) + bytes(8)
        stream: bytes = encode_stream(palette_bytes([]) + planes)
        picture: Picture = Picture.from_stream(
            stream, PictureLayout(width=8, height=2, decode_type=0, decode_length=10)
        )
        self.assertEqual(picture.pixels, bytes([1]) * 16)
        self.assertIsNone(picture.run_length)

    def test_rejects_unknown_types_and_short_data(self) -> None:
        stream: bytes = encode_stream(palette_bytes([]) + bytes(4))
        with self.assertRaisesRegex(FormatError, "decode type"):
            Picture.from_stream(stream, PictureLayout(width=8, height=1, decode_type=9, decode_length=4))
        with self.assertRaisesRegex(FormatError, "data bytes"):
            Picture.from_stream(stream, PictureLayout(width=8, height=1, decode_type=0, decode_length=4))


class AnimationTests(unittest.TestCase):
    def frame_entry(self, x: int) -> bytes:
        planes: bytes = bytes([0x80, 0x00]) + bytes(8)
        return struct.pack(">II", 8, 0) + encode_stream(bytes([1, 2, x, 9]) + planes)

    def background(self) -> Picture:
        return Picture(
            width=16,
            height=4,
            pixels=bytes([3]) * 64,
            palette=Palette.from_data(palette_bytes([])),
            run_length=None,
        )

    def test_empty_entry_has_no_frames(self) -> None:
        self.assertEqual(RoomAnimations.from_entry(b"\x4e\x71", 3).frames, ())

    def test_frame_header_and_position(self) -> None:
        animations: RoomAnimations = RoomAnimations.from_entry(self.frame_entry(6), 1)
        self.assertEqual(len(animations.frames), 1)
        frame: AnimationFrame = animations.frames[0]
        self.assertEqual((frame.width, frame.height, frame.left, frame.top), (8, 2, 4, 1))
        self.assertEqual(frame.pixels[0], 1)
        self.assertEqual(frame.pixels[8], 1)

    def test_copy_and_xor(self) -> None:
        frame: AnimationFrame = RoomAnimations.from_entry(self.frame_entry(6), 1).frames[0]
        copied: Picture = compose(self.background(), frame, BlitMode.COPY)
        xored: Picture = compose(self.background(), frame, BlitMode.XOR)
        self.assertEqual((copied.pixels[16 + 4], copied.pixels[16 + 5]), (1, 0))
        self.assertEqual((xored.pixels[16 + 4], xored.pixels[16 + 5]), (2, 3))
        self.assertEqual(copied.pixels[:16], bytes([3]) * 16)

    def test_frames_are_clipped_to_the_background(self) -> None:
        frame: AnimationFrame = RoomAnimations.from_entry(self.frame_entry(10), 1).frames[0]
        copied: Picture = compose(self.background(), frame, BlitMode.COPY)
        self.assertEqual(len(copied.pixels), 64)
        self.assertEqual(copied.pixels[16 + 12], 1)
        self.assertEqual(copied.pixels[32:48], bytes([3]) * 12 + bytes([1, 0, 0, 0]))


class TextTests(unittest.TestCase):
    def test_capital_and_second_half_codes(self) -> None:
        self.assertEqual(decode_string(ALPHABET, pack_codes([0x1E, 1, 2, 0x1F, 0, 0])), "Ab0")

    def test_rejects_strings_without_nul(self) -> None:
        with self.assertRaisesRegex(FormatError, "NUL"):
            decode_string(ALPHABET, bytes([0x21]))

    def test_table_offsets_delimit_strings(self) -> None:
        first: bytes = pack_codes([1, 2, 0])
        second: bytes = pack_codes([3, 0])
        offsets: bytes = struct.pack(">3H", 6, 6 + len(first), 6 + len(first) + len(second))
        table: TextTable = TextTable.from_data(ALPHABET + offsets + first + second + b"\0", 0)
        self.assertEqual(table.strings, ("ab", "c"))

    def test_word_lists(self) -> None:
        self.assertEqual(read_word_list(struct.pack(">H", 2) + b"ONE\0TWO\0 \0\0", 0), ("ONE", "TWO"))
        self.assertEqual(read_word_list(struct.pack(">H", 2) + b"O\x01E\0\0", 0), ())
        self.assertEqual(read_word_list(struct.pack(">H", 2) + b"ONE\0TWO", 0), ())
        self.assertEqual(read_word_list(struct.pack(">H", 0), 0), ())


class SongTests(unittest.TestCase):
    def test_event_fields(self) -> None:
        event: NoteEvent = NoteEvent.from_word(0b1_01_01001_1_0011001)
        self.assertEqual(
            (event.octave_flag, event.channel, event.duration, event.continues, event.octave, event.note),
            (True, 1, 8, True, 2, 1),
        )
        self.assertEqual(event.sample, 4)

    def test_samples_by_channel(self) -> None:
        self.assertEqual(NoteEvent.from_word(0x2000).sample, 7)
        self.assertEqual(NoteEvent.from_word(0x2000 | 12).sample, 4)
        self.assertEqual(NoteEvent.from_word(0x2000 | 24).sample, 9)
        self.assertEqual(NoteEvent.from_word(0x4000).sample, 5)
        self.assertEqual(NoteEvent.from_word(0x6000).sample, 6)
        self.assertTrue(NoteEvent.from_word(0x7F).is_rest)

    def test_rejects_odd_lengths(self) -> None:
        self.assertEqual(len(Song.from_data(bytes(4)).events), 2)
        with self.assertRaises(FormatError):
            Song.from_data(bytes(3))


class SampleTests(unittest.TestCase):
    def test_wav_round_trip(self) -> None:
        reader: wave.Wave_read
        with wave.open(io.BytesIO(Sample.from_data(bytes([0x00, 0x7F, 0x80, 0xFF])).to_wav())) as reader:
            self.assertEqual(reader.getframerate(), NOMINAL_RATE_HZ)
            self.assertEqual(reader.getsampwidth(), 1)
            self.assertEqual(reader.readframes(4), bytes([0x80, 0xFF, 0x00, 0x7F]))
        with self.assertRaises(FormatError):
            Sample.from_data(b"")


if __name__ == "__main__":
    unittest.main()
