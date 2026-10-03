# Picture formats

Room backgrounds, game graphics, AI faces and room animation frames are
Huffman-coded pictures stored in four files on the game disk.
[huffman.py](../scripts/newromancerlib/huffman.py),
[bitmaps.py](../scripts/newromancerlib/bitmaps.py) and
[animations.py](../scripts/newromancerlib/animations.py) decode them.

## Sources

Every statement below refers to these files of the original disk
(SHA-256 `12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9`):

| File | Size | SHA-256 | Pictures |
| --- | --- | --- | --- |
| `bigpic0158` | 313,625 | `0e09d360df1ceaa9e40466486adab44377b17b8998301d09e19e0a00c68ba227` | 55 room backgrounds |
| `bigpic2` | 94,993 | `d4a16e96dabf60654729e50c93a2d08538b364ec4570f5776c791b0d42cfe04f` | 15 game graphics |
| `bigAIpic` | 11,973 | `c5c9325f778d507cd15be9aeb508c0f59b049f0161f3e9a7b593d6b9fd01cf0d` | 12 AI faces |
| `bigRnnd` | 75,468 | `d96a1235c18278987d11c3a8684d7db5f6aa501b7cbf08d420d73aa208ba8a34` | 350 animation frames in 25 rooms |
| `NEURO` | 142,820 | `4bb072dd925e2380881e09d5bcbb03d4608a6d583e5e5eb8192c6b6433b882d0` | the executable |

`NEURO` is an AmigaDOS executable of 25 hunks. Addresses in it are given as
hunk number plus offset into the hunk.

## Offset table

Each file opens with big-endian 32-bit file offsets, one per picture, ended by
a zero entry. The first offset equals the end of the table and the offsets
ascend (**Observed**). A picture's stream runs from its offset to the next
offset, or to the end of the file for the last picture.

## Huffman streams

| Offset | Size | Contents |
| --- | --- | --- |
| 0x00 | 4 | Decoded-byte budget, big-endian |
| 0x04 | 4 | Coded length in bits plus 7, big-endian; never read by the game |
| 0x08 | | Code tree, then the coded bytes |

The bits form one stream of 16-bit big-endian words, most significant bit
first. The tree is stored in pre-order: bit 1 is a leaf followed by its 8-bit
value, most significant bit first; bit 0 is an inner node followed by the
subtree taken on a 0 bit, one bit the reader skips, and the subtree taken on a
1 bit. Decoding walks from the root, one bit per inner node, and emits the
value of the leaf it reaches. Several decode requests can follow one another
on a stream; together they emit at most the budget.

**Observed** in the game: the tree reader at hunk 11 + 0x650, the bit reader
at hunk 11 + 0x77C and the decoder at hunk 11 + 0x7C6. The decoder holds its
bit position between requests and lowers the budget by the bytes emitted. It
reads the file through a 512-byte buffer and refills it at the end of each
buffer, past the end of the file included. The second header word is skipped.

**Observed** in the 82 streams of the three files:

- Each budget is used up by the palette and picture requests listed below.
- At every one of the 10,250 inner nodes the skipped bit is 0.
- Each stream ends 0 to 7 bits before the next stream starts; no decode reads
  past it.
- The second header word equals the number of coded bits, tree included,
  plus 7.

## Picture decoding

The picture loader starts at hunk 11 + 0x000. Its argument is a picture
number: the low 24 bits select the picture, the top 8 bits the decode type. A
descriptor supplies the width, height and decode length. The loader opens the
file, reads the picture's offset from the table, reads the tree, decodes 64
palette bytes and then up to the decode length of data bytes, and finally
transforms the data according to the decode type (**Observed**):

| Type | Run-length | XOR lines | Layout |
| --- | --- | --- | --- |
| 0 | none | yes | planar |
| 1 | rows | yes | planar |
| 2 | columns | yes | planar |
| 3 | columns | no | planar |
| 4 | none | yes | chunky |
| 5 | rows | yes | chunky |
| 6 | columns | yes | chunky |
| 7 | rows | no | chunky |
| 8 | columns | no | chunky |

Types above 8 decode like type 8. Types 0 and 6 occur in none of the three
files.

### Planar and chunky layouts

Planar data holds five bitplanes, one after the other. Each plane holds
`height` rows of `width / 8` bytes, and the descriptor gives the width in
bytes. Bit n of a pixel's color index comes from plane n. The loader copies
the planes to the screen bitmap as they are (hunk 11 + 0x364).

Chunky data holds one byte per pixel, and the descriptor gives the width in
pixels. The conversion to planes (hunk 11 + 0x3AC) moves byte bit 0 to plane 4,
bit 1 to plane 3 and so on up to bit 4, which goes to plane 0; bits 5 to 7 are
ignored. The color index is therefore the byte's low five bits in reverse
order. No chunky byte in the three files sets bits 5 to 7 (**Observed**).

### Run-length records

A record starts with a control byte:

| Control byte | Meaning |
| --- | --- |
| 0x00 | end of data |
| 0x01 to 0x7F | repeat the following byte that many times |
| 0x80 | end of data |
| 0x81 to 0xFF | copy the following `control & 0x7F` bytes |

Decoding also stops after the record that fills the output. The size of the
output is `width x height x planes` bytes, with the width in bytes as above
and one plane for chunky data. In row order the records fill the output in
sequence (hunk 11 + 0x43A). In column order they fill each plane column by
column, each column from top to bottom (hunk 11 + 0x4E4, stepping at
hunk 11 + 0x5B2).

The game expands the records into a scratch buffer and then copies the
picture's bytes from it (**Observed**). A final record may write past the
picture; those bytes never reach it. Bytes that no record reaches keep
whatever the scratch buffer held before. The port drops the excess bytes and
leaves unreached bytes at zero. Three pictures are affected (**Observed**):

| Picture | Effect |
| --- | --- |
| room 16 | the last record ends 60 bytes past the picture |
| game graphics 10 | the last record ends 13 bytes past the picture |
| game graphics 11 | a 0x00 control byte ends the data one byte short; the last byte of plane 5 is not reached |

### XOR lines

Within each plane, every row from the second down is XORed with the row above
it after that row's own XOR (hunk 11 + 0x61A). Rows therefore hold the
difference to the row above.

### Palette

The 64 palette bytes are 32 big-endian words `0x0RGB`, four bits per channel.
The top four bits are zero in all 82 palettes (**Observed**). The extractor
scales each channel by 17 for 8-bit output, so 0xF becomes 0xFF.

## Picture tables

None of the three files stores sizes or decode types; they come from the
executable.

### Room backgrounds: `bigpic0158`

The room background loader (hunk 10 + 0xDE8) reads the decode type of the room
from a 58-byte table at hunk 10 + 0x1B72, room 1 first. For types below 4 it
sets the width to 38 bytes, otherwise to 304 pixels. The descriptor at
hunk 11 + 0x91E supplies the height, 112, and the decode length, 64,000. Every
background is 304 x 112 pixels (**Observed**).

| Rooms | Decode types |
| --- | --- |
| 1-10 | 5 5 5 5 5 5 5 5 5 5 |
| 11-20 | 5 5 3 3 5 3 2 2 5 5 |
| 21-30 | 5 5 4 2 5 3 5 0xFF 5 5 |
| 31-40 | 5 5 5 5 5 5 5 5 5 5 |
| 41-50 | 5 5 0xFF 1 5 5 5 0xFF 5 4 |
| 51-58 | 5 7 5 5 5 5 5 5 |

The picture loader turns room number n into a picture index: n - 1 for rooms
below 28, n - 2 for rooms 28 to 43, n - 3 for rooms 44 to 48 and n - 4 from
room 49 (hunk 11 + 0x00E, **Observed**). The 55 pictures are thus the
backgrounds of the 55 rooms whose type is not 0xFF, in room order. Rooms 28,
43 and 48 map onto the picture of rooms 27, 44 and 49, but their type 0xFF
would decode it as type 8 instead of that picture's type 5, 1 and 5
(**Inferred**: these rooms never show a background). Whether the game enters
them is **Unknown**.

### Game graphics: `bigpic2`

Each call site sets the picture number, decode type and size; the descriptor
at hunk 11 + 0x946 is shared by all of them except number 10, which uses the
descriptor at hunk 11 + 0x96E (**Observed**).

| Number | Size | Type | Decode length | Contents | Set at |
| --- | --- | --- | --- | --- | --- |
| 1 | 320 x 200 | 2 | 64,000 | splash screen | hunk 14 + 0x70C |
| 2 | 288 x 130 | 8 | 64,000 | player walking left and right | hunk 10 + 0x32A |
| 3 | 288 x 130 | 8 | 64,000 | player walking up and down | hunk 10 + 0x32A |
| 4 | 160 x 130 | 8 | 64,000 | player walking up, turning head | hunk 10 + 0x334 |
| 5 | 160 x 130 | 8 | 64,000 | player walking down, turning head | hunk 10 + 0x334 |
| 6 | 160 x 130 | 8 | 64,000 | player walking right, turning head | hunk 10 + 0x334 |
| 7 | 160 x 130 | 8 | 64,000 | player walking left, turning head | hunk 10 + 0x334 |
| 8 | 256 x 65 | 8 | 64,000 | player turning by 45 degrees | hunk 10 + 0x1C6 |
| 9 | 320 x 200 | 5 | 64,000 | dashboard and scene frame | hunk 10 + 0xBA |
| 10 | 64 x 19 | 8 | 1,216 | thought and dialogue balloon ends | hunk 14 + 0x8CA |
| 11 | 320 x 200 | 3 | 64,000 | cyberspace dashboard | hunk 16 + 0x874 |
| 12 | 320 x 200 | 7 | 64,000 | database horizon tiles and shapes | hunk 16 + 0x82C |
| 13 | 320 x 200 | 3 | 64,000 | more database shapes | hunk 16 + 0x7E4 |
| 14 | 320 x 200 | 8 | 64,000 | ICE, ArmorAll and EEG graphics | hunk 16 + 0x808 |
| 15 | 320 x 200 | 7 | 64,000 | **Unknown** use | hunk 16 + 0x850 |

Numbers 2 to 7 go through two small loaders that set the width, 288 or 160,
and the height, 130; their callers pass the picture number.

### AI faces: `bigAIpic`

The face loader reads the decode type from a 12-byte table at
hunk 16 + 0x1F90, indexed by byte 11 of the current database's record
(hunk 16 + 0x1F34); the descriptor at hunk 11 + 0x8F6 supplies the size,
72 x 80, and the decode length, 5,760 (**Observed**). That byte numbers the
face of the database's AI (**Inferred**).

| Faces | Decode types |
| --- | --- |
| 1-12 | 5 7 5 7 5 5 7 7 7 5 7 7 |

## Animation frames: `bigRnnd`

The offset table of `bigRnnd` has 58 entries, one per room, room 1 first; the
room number minus one selects the entry directly. A room without animations
has the two bytes 0x4E71 as its entry. Any other entry is a zero-terminated
table of big-endian 32-bit frame offsets, relative to the start of the entry,
followed by the frames; a frame runs to the next frame offset or to the end of
the entry (**Observed**). Frames are numbered from 1 in table order.

The game does not inspect the entry to tell the two kinds apart. The room
animation loader (hunk 6 + 0x7EE) consults a 58-byte table at
hunk 6 + 0x8F2, one byte per room, and loads frames only for rooms whose byte
is not zero (**Observed**). The table is nonzero for exactly the 25 rooms whose
entry holds frames, and every one of those rooms has a background
(**Observed**).

### Frame streams

Each frame is one Huffman stream. The frame loader (hunk 11 + 0x1B8) decodes
four bytes, then the planes, and keeps each frame as a separate five-plane
bitmap (**Observed**):

| Decoded offset | Size | Contents |
| --- | --- | --- |
| 0 | 1 | width in bytes |
| 1 | 1 | height |
| 2 | 1 | x, in units of two pixels |
| 3 | 1 | y |
| 4 | width x height x 5 | five bitplanes, lines XORed as in planar pictures |

The frame uses the palette of its room's background.

### Placement and blit mode

The frame blit (hunk 6 + 0x792) draws the whole frame at screen position
(2 * x, y), and the room background sits at (8, 8) on the screen
(descriptor at hunk 11 + 0x91E). Relative to the background, a frame
therefore starts at (2 * x - 8, y - 8) (**Observed**).

The blit takes its minterm from the caller: 0x60 XORs the frame onto the
screen, 0xC0 copies it over the screen (**Observed**). XOR frames hold the
difference to what is on screen, so drawing one twice restores the previous
image. The callers choose as follows (**Observed**):

- The per-frame animation step (hunk 6 + 0x72A) draws with XOR. It copies
  instead for frames 8 to 11 while one game-state byte is set
  (hunk 6 + 0x74C) and for frames 19 to 22 while another is set
  (hunk 6 + 0x774).
- On entering one of the seven rooms 12, 26, 34, 45, 50, 52 and 53, listed at
  hunk 6 + 0x6CC, a routine at hunk 6 + 0x5F4 looks the room up in a table of
  10-byte room records at hunk 19 + 0x6F6. If the record's first byte equals
  the room number, bit 7 clear, it copies the room's last frame
  (hunk 6 + 0x660). Room 26 also depends on two further state bytes.
- The same routine then copies frame 22 of room 12 and frame 6 of room 41
  while their state bytes are set (hunk 6 + 0x672).

The copied frames are the changes to a room's background that its script
triggers, such as opened doors; the room scripts set these state bytes.

## Validation

All 82 pictures and all 350 animation frames decode with the extractor. The
run-length edge cases above are the only irregularities; every frame's
budget equals its four header bytes plus its planes, and every frame lies
inside its room's background. Unverified: what the game's scratch buffer
holds at the unreached byte of game graphics 11, and the use of game
graphics 15.
