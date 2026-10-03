# Text formats

Room texts, miscellaneous texts and database texts are stored as 5-bit packed
strings in three files on the game disk.
[text.py](../scripts/newromancerlib/text.py) decodes them.

## Sources

Every statement below refers to these files of the original disk
(SHA-256 `12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9`);
addresses in the executable are given as hunk number plus offset, as in
[picture-formats.md](picture-formats.md#sources).

| File | Size | SHA-256 | Entries |
| --- | --- | --- | --- |
| `bigRnnt` | 48,764 | `ed071be9c366b39d3ea7799533f31acbbe0ced58a099c1830456598cc10bdb3d` | 58 rooms |
| `bigText` | 17,893 | `50cfd2a8dd07acd22dbb2df6df187499261ce7120460ea825377db7fd745cebf` | 21 text groups |
| `bigdb` | 97,026 | `53edc19338b76886c000120374811a8fb82ebd7a0dd332c9036475006cd2dd3c` | 38 databases |

## Entries

Each file opens with the offset table described in
[picture-formats.md](picture-formats.md#offset-table). An entry runs to the
next offset, or to the end of the file. An entry that consists of the two
bytes 0x4E71 is empty. Every other entry starts with a big-endian 32-bit size
that equals the entry's length (**Observed**).

## Text tables

A text table is a 60-byte alphabet followed by big-endian 16-bit offsets,
relative to the start of the offset list; the first offset divided by two is
the number of offsets. Offset n starts string n. Each table holds one offset
more than it has strings: the last one points at the final byte of the entry
and marks the end of the last string (**Observed**). What that final byte
holds is **Unknown**.

A string is a sequence of 5-bit codes, packed least significant bit first:

| Code | Meaning |
| --- | --- |
| 0x00 to 0x1D | alphabet byte at this index |
| 0x1E | the next character is capitalized: its alphabet byte minus 0x20 |
| 0x1F | the next code indexes the second half of the alphabet: code + 30 |

A NUL character ends the string; the alphabet itself supplies it. The game's
decoder (hunk 10 + 0x10F0) takes the address of an alphabet and a string
number, reads the string's offset from the list and expands the codes into a
buffer until the NUL (**Observed**).

## Room texts: `bigRnnt`

One entry per room, room 1 first. The entries of rooms 5, 13, 14, 15, 16, 18,
21, 28, 30, 31, 33, 37, 38, 39, 43, 48, 49, 54 and 55 are empty
(**Observed**).

| Offset | Size | Contents |
| --- | --- | --- |
| 0x00 | 4 | entry size |
| 0x04 | 4 | offset of the text table |
| 0x08 | 3 x 4 | action slots: offset of a 32-bit value holding the action's offset, or 0 |
| 0x14 | 6 x 2 | offsets, each relative to its own position, or 0 |
| 0x20 | 5 x 4 | **Unknown** |
| 0x34 | 1 | 1 when the room has a PAX booth |
| 0x35 | 1 | 2 when the room has a cyberspace jack |
| 0x36 | 2 | zero in every room |

The game tests byte 0x34 for 1 (hunk 5 + 0x1CDC) and byte 0x35 for 2
(hunk 5 + 0x13A2); the files hold no other nonzero values there
(**Observed**). Rooms 1, 7, 8, 41 and 46 have a PAX booth; rooms 7, 8, 22,
35, 47, 51, 53, 56, 57 and 58 have a jack.

On entering a room the game decodes string 0 of its table on the first visit
and string 1 on later visits, keeping one visited flag per room
(hunk 10 + 0xC8E, **Observed**). The other strings serve the room's
dialogue.

The action slots, the offsets at 0x14 and the area from 0x38 up to the text
table belong to the room scripts. The text table never starts before 0x46
(**Observed**), but the area from 0x38 has no fixed layout: in room 6 the
first action slot points at 0x38 itself. The extractor reads this area as the
earlier tools did: six relative offsets at 0x38, and lists of NUL-terminated
words, ended by an empty word, through the offsets at 0x3C (known words) and
0x42 (known locations). A list counts only when all its words are printable
ASCII and it ends inside the entry. Known words appear in rooms 8, 11, 12, 20,
23, 26, 27, 32, 44 and 52, known locations only in room 26 (**Inferred**).

## Miscellaneous texts: `bigText`

Each entry is the 32-bit size followed by a text table at offset 4, unless its
first 16-bit word is not zero; then it holds other data (**Observed**).

| Entries | Contents |
| --- | --- |
| 0 | AI lines during combat |
| 1 | bank screens |
| 2 | messages |
| 3 | bulletin board |
| 4 | first-time user information |
| 5, 6, 8, 9, 10, 15, 16 | 256-byte data blocks of names, 9-digit numbers and binary bytes; layout **Unknown** |
| 7, 14 | empty |
| 11 | news in brief |
| 12 | Night City News |
| 13 | PAX |
| 17, 18, 19 | ROM constructs: Dixie Flatline, Toshiro Mifune, Rombo |
| 20 | ending |

## Databases: `bigdb`

Entries 0 to 36 hold databases; entry 37 is empty. Byte 0x04 numbers them 0
to 37 without 28 (**Observed**).

| Offset | Size | Contents |
| --- | --- | --- |
| 0x00 | 4 | entry size |
| 0x04 | 1 | database number |
| 0x05 | 1 | number of levels, 1 to 3 |
| 0x06 | 2 x 2 | **Unknown** |
| 0x0A | 2 | offset of the text table, relative to 0x0A |
| 0x0C | 2 | **Unknown** |
| 0x0E | 2 | offset of the passwords, relative to 0x0E |
| 0x10 | 2 | offset of the data after the passwords, relative to 0x10 |
| 0x12 | 2 | **Unknown** |

The passwords are NUL-terminated strings between the two offsets. Thirty-one
databases hold one password fewer than their levels, six hold one per level
(**Observed**). The data after the passwords belongs to the database scripts.

## Validation

All 1,609 strings of the 61 text tables decode, and each ends with its NUL
before the next string's offset. Unverified: the use of the room header words
at 0x20, the database header words at 0x06, 0x0C and 0x12, and the layout of
the data blocks in `bigText`.
