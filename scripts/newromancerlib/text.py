# SPDX-License-Identifier: MIT
"""Compressed text: room texts (bigRnnt), miscellaneous texts (bigText) and databases (bigdb).

Each file's offset table has one entry per room, text group or database. An entry that is
just the two bytes 0x4E71 is empty.

Text table: a 60-byte alphabet, then big-endian 16-bit offsets relative to the start of the
offset list. The first offset divided by two is the number of offsets; each offset starts a
string, and the last one marks the end of the last string.

String: 5-bit codes, packed least significant bit first. Code 0x1E capitalizes the next
character (its alphabet byte minus 0x20), code 0x1F selects the second half of the alphabet
for the next code (code + 30), any other code is an index into the alphabet. A NUL character
ends the string.

bigRnnt entry, rooms 1 to 58 (offsets relative to the entry):

    0x00  uint32  entry size
    0x04  uint32  offset of the text table
    0x08  uint32  x3  action slots: offset of a uint32 holding the action's offset, or 0
    0x14  uint16  x6  dialogue pointers, each relative to its own position, or 0
    0x34  uint8   nonzero when the room has a PAX booth
    0x35  uint8   nonzero when the room has a cyberspace jack

From 0x38 up to the text table the layout varies by room. The extractor reads it as fixed
fields: six secondary dialogue pointers at 0x38, each relative to its own position, and the
relative offsets of known words at 0x3C and known locations at 0x42, each a list of
NUL-terminated words ended by an empty one. A word list counts only if all its words are
printable ASCII and it ends inside the entry.

Text string 0 is shown on the first visit to the room, string 1 on later visits.

bigText entry: a uint32 entry size, then the text table at offset 4. An entry whose first
16-bit word is not zero holds other data instead of text.

bigdb entry (offsets relative to the entry):

    0x00  uint32  entry size
    0x04  uint8   database index
    0x05  uint8   number of levels
    0x0A  uint16  offset of the text table, relative to 0x0A
    0x0E  uint16  offset of the passwords, relative to 0x0E
    0x10  uint16  offset of the data that follows the passwords, relative to 0x10

The passwords are NUL-terminated strings between those two offsets.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from itertools import pairwise

from .containers import FormatError

EMPTY_ENTRY: bytes = b"\x4e\x71"
ALPHABET_SIZE: int = 60
CODE_BITS: int = 5
CODE_MASK: int = 0x1F
CAPITAL_CODE: int = 0x1E
ALTERNATE_CODE: int = 0x1F
ALTERNATE_SHIFT: int = 30
CAPITAL_OFFSET: int = 0x20
TEXT_ENCODING: str = "latin-1"

ROOM_TEXT_TABLE_OFFSET: int = 0x04
ROOM_ACTIONS: int = 0x08
ROOM_ACTION_COUNT: int = 3
ROOM_DIALOGUE_POINTERS: int = 0x14
ROOM_SECONDARY_DIALOGUE_POINTERS: int = 0x38
ROOM_POINTER_COUNT: int = 6
ROOM_PAX_FLAG: int = 0x34
ROOM_JACK_FLAG: int = 0x35
ROOM_KNOWN_WORDS: int = 0x3C
ROOM_KNOWN_LOCATIONS: int = 0x42
ROOM_HEADER_SIZE: int = 0x46

MISC_TEXT_TABLE_OFFSET: int = 0x04

DATABASE_HEADER_FORMAT: str = ">IBBHHHHHHH"
DATABASE_HEADER_SIZE: int = struct.calcsize(DATABASE_HEADER_FORMAT)
DATABASE_TEXT_TABLE_BASE: int = 0x0A
DATABASE_PASSWORDS_BASE: int = 0x0E
DATABASE_PASSWORDS_END_BASE: int = 0x10


def decode_string(alphabet: bytes, data: bytes) -> str:
    """Decode one string from the start of `data`, up to its NUL character."""
    output: bytearray = bytearray()
    bits: int = 0
    bit_count: int = 0
    position: int = 0
    capital: bool = False
    alternate: bool = False
    done: bool = False
    code: int
    character: int
    while not done:
        if bit_count < CODE_BITS:
            if position >= len(data):
                raise FormatError(f"Text: no terminating NUL within {len(data)} bytes")
            bits |= data[position] << bit_count
            position += 1
            bit_count += 8
        else:
            code = bits & CODE_MASK
            bits >>= CODE_BITS
            bit_count -= CODE_BITS
            if code == CAPITAL_CODE:
                capital = True
            elif code == ALTERNATE_CODE:
                alternate = True
            else:
                character = alphabet[code + ALTERNATE_SHIFT if alternate else code]
                if capital:
                    character = (character - CAPITAL_OFFSET) & 0xFF
                capital = False
                alternate = False
                done = character == 0
                if not done:
                    output.append(character)
    return output.decode(TEXT_ENCODING)


@dataclass(frozen=True)
class TextTable:
    alphabet: bytes
    strings: tuple[str, ...]

    @staticmethod
    def from_data(entry: bytes, alphabet_offset: int) -> TextTable:
        table_start: int = alphabet_offset + ALPHABET_SIZE
        if not (0 <= alphabet_offset and table_start + 2 <= len(entry)):
            raise FormatError(f"Text table: alphabet at 0x{alphabet_offset:X} lies outside {len(entry)} bytes")
        table_size: int
        (table_size,) = struct.unpack_from(">H", entry, table_start)
        if table_size < 2 or table_size % 2 or table_start + table_size > len(entry):
            raise FormatError(f"Text table: invalid offset list size {table_size} at 0x{table_start:X}")
        starts: tuple[int, ...] = tuple(
            table_start + offset for offset in struct.unpack_from(f">{table_size // 2}H", entry, table_start)
        )
        start: int
        for start in starts:
            if not table_start + table_size <= start <= len(entry):
                raise FormatError(f"Text table: string offset 0x{start:X} lies outside the entry")
        alphabet: bytes = entry[alphabet_offset:table_start]
        return TextTable(
            alphabet=alphabet,
            strings=tuple(decode_string(alphabet, entry[start:end]) for start, end in pairwise(starts)),
        )


def read_uint16(entry: bytes, offset: int) -> int:
    if offset + 2 > len(entry):
        raise FormatError(f"Entry: 16-bit field at 0x{offset:X} lies outside {len(entry)} bytes")
    value: int
    (value,) = struct.unpack_from(">H", entry, offset)
    return value


def read_uint32(entry: bytes, offset: int) -> int:
    if offset + 4 > len(entry):
        raise FormatError(f"Entry: 32-bit field at 0x{offset:X} lies outside {len(entry)} bytes")
    value: int
    (value,) = struct.unpack_from(">I", entry, offset)
    return value


def read_word_list(entry: bytes, position: int) -> tuple[str, ...]:
    """Words at the offset stored at `position`; empty unless the list is printable and ends in the entry."""
    relative: int = read_uint16(entry, position)
    words: list[str] = []
    valid: bool = relative != 0
    start: int = position + relative
    end: int
    word: bytes
    while valid and start < len(entry) and entry[start] != 0:
        end = entry.find(b"\0", start)
        word = entry[start:end] if end >= 0 else b""
        valid = end >= 0 and all(0x20 <= value < 0x7F for value in word)
        if valid and word != b" ":
            words.append(word.decode("ascii"))
        start = end + 1
    return tuple(words) if valid and start < len(entry) else ()


@dataclass(frozen=True)
class RoomText:
    room: int
    table: TextTable
    actions: tuple[int | None, ...]
    dialogue_pointers: tuple[int | None, ...]
    secondary_dialogue_pointers: tuple[int | None, ...]
    has_pax: bool
    has_cyberspace_jack: bool
    known_words: tuple[str, ...]
    known_locations: tuple[str, ...]

    @staticmethod
    def from_entry(entry: bytes, room: int) -> RoomText | None:
        room_text: RoomText | None = None
        if entry != EMPTY_ENTRY:
            if len(entry) < ROOM_HEADER_SIZE:
                raise FormatError(f"Room {room}: {len(entry)} bytes cannot hold the {ROOM_HEADER_SIZE}-byte header")
            room_text = RoomText(
                room=room,
                table=TextTable.from_data(entry, read_uint32(entry, ROOM_TEXT_TABLE_OFFSET)),
                actions=tuple(
                    RoomText.read_action(entry, read_uint32(entry, ROOM_ACTIONS + 4 * slot))
                    for slot in range(ROOM_ACTION_COUNT)
                ),
                dialogue_pointers=RoomText.read_pointers(entry, ROOM_DIALOGUE_POINTERS),
                secondary_dialogue_pointers=RoomText.read_pointers(entry, ROOM_SECONDARY_DIALOGUE_POINTERS),
                has_pax=entry[ROOM_PAX_FLAG] != 0,
                has_cyberspace_jack=entry[ROOM_JACK_FLAG] != 0,
                known_words=read_word_list(entry, ROOM_KNOWN_WORDS),
                known_locations=read_word_list(entry, ROOM_KNOWN_LOCATIONS),
            )
        return room_text

    @staticmethod
    def read_action(entry: bytes, slot_offset: int) -> int | None:
        """Entry offset of the action whose offset is stored at `slot_offset`; None for an empty slot."""
        action: int | None = None
        if slot_offset != 0:
            action = read_uint32(entry, slot_offset)
            if action >= len(entry):
                raise FormatError(f"Room text: action at 0x{action:X} lies outside {len(entry)} bytes")
        return action

    @staticmethod
    def read_pointers(entry: bytes, position: int) -> tuple[int | None, ...]:
        pointers: list[int | None] = []
        index: int
        value: int
        for index in range(ROOM_POINTER_COUNT):
            value = read_uint16(entry, position + 2 * index)
            pointers.append(position + 2 * index + value if value != 0 else None)
        return tuple(pointers)


@dataclass(frozen=True)
class MiscText:
    """A bigText entry: a text table, or a block of other data when `table` is None."""

    table: TextTable | None
    block: bytes

    @staticmethod
    def from_entry(entry: bytes) -> MiscText | None:
        misc_text: MiscText | None = None
        if entry != EMPTY_ENTRY:
            if read_uint16(entry, 0) != 0:
                misc_text = MiscText(table=None, block=entry)
            else:
                misc_text = MiscText(table=TextTable.from_data(entry, MISC_TEXT_TABLE_OFFSET), block=b"")
        return misc_text


@dataclass(frozen=True)
class DatabaseText:
    index: int
    levels: int
    passwords: tuple[str, ...]
    table: TextTable

    @staticmethod
    def from_entry(entry: bytes) -> DatabaseText | None:
        database_text: DatabaseText | None = None
        if entry != EMPTY_ENTRY:
            if len(entry) < DATABASE_HEADER_SIZE:
                raise FormatError(f"Database text: {len(entry)} bytes cannot hold the header")
            index: int
            levels: int
            text_table: int
            passwords: int
            passwords_end: int
            _, index, levels, _, _, text_table, _, passwords, passwords_end, _ = struct.unpack_from(
                DATABASE_HEADER_FORMAT, entry
            )
            start: int = DATABASE_PASSWORDS_BASE + passwords
            end: int = DATABASE_PASSWORDS_END_BASE + passwords_end
            if not start <= end <= len(entry):
                raise FormatError(f"Database text: passwords 0x{start:X}..0x{end:X} lie outside the entry")
            database_text = DatabaseText(
                index=index,
                levels=levels,
                passwords=tuple(
                    password.decode(TEXT_ENCODING) for password in entry[start:end].split(b"\0") if password
                ),
                table=TextTable.from_data(entry, DATABASE_TEXT_TABLE_BASE + text_table),
            )
        return database_text
