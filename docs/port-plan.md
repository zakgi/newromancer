# Port plan

The C++ port reuses the existing implementation of the game, restructured
under [coding-style.md](coding-style.md): the game logic moves into the
engine, everything that touches the host moves out of it, and the engine
gains a target build for the RP2350. This document records the agreed
architecture and the order of work; update it as steps land or decisions
change.

## Layout

| Directory | Contents |
| --- | --- |
| `src/core/` | The engine: components and actions, game state, script interpreters, the screen and its palette, asset structures (views only), audio voices, ring and song player. No exceptions, no RTTI, no dynamic allocation. |
| `src/host/` | SFML window, presenter, input and audio output; reading the disk image; the asset manager. |
| `src/host/format/` | Decoders for the original files, returning `std::expected`. |
| `src/target/`, `src/boards/` | RP2350 support and board definitions. |
| `test/` | GoogleTest. Tests that need the disk image read it from `NEWROMANCER_ADF` and skip when it is absent. |
| `cmake/` | Source lists, the RP2350 toolchain and flags. |

## Subsystems

**Assets.** The host reads the disk image once, decodes every resource once
into fixed host storage, and fills the engine's asset structures: room
backgrounds and animation frames, game graphics, AI faces, text tables,
songs and samples, all as views. Components receive these structures by
reference and never query the asset manager. On the target the same
structures are read-only data in flash, packed on the host. A missing asset
is an empty view and draws nothing.

**Rendering.** The engine draws into a 320 x 200 screen of 8-bit pens with a
32-color palette: clipped blits that copy, mask or XOR, rectangle fills, text
in a bitmap Topaz font, and the mouse pointer. Highlights invert pens, and
cyberspace animates by rotating palette entries; there are no shaders. Only
the host presenter turns pens into RGBA.

**Audio.** The main loop renders audio frames into a single-producer,
single-consumer ring. Voices resample the 8-bit samples; the song player
advances once per 50 Hz field. On the host an SFML stream drains the ring; on
the target I2S DMA will.

**Game.** Each screen or mode is a component (real world, PAX, database,
cyberspace and so on), and timed sequences are actions on an action stack.
There are no threads: input events and the game clock advance in the main
loop. The room and database script interpreters move into the engine.
Two defects of the existing interpreter are fixed on the way: opcode 15
updates a copy of the game state instead of the state itself, and opcode 18
sets its index to 1 instead of 0.

**Font.** A Topaz bitmap font from the amigafonts raw set, fetched at build
time.

## Steps

Each step is a separate, reviewable change.

1. Host build skeleton: CMake, presets, an empty engine library, a window,
   GoogleTest.
2. Decoders for the original files, tested against the digests the Python
   tests pin.
3. Screen, palette, image views, font and the host presenter.
4. Disk image reader and asset manager filling the asset structures.
5. Audio: voices, ring, song player, host output.
6. Game code, area by area, starting with the real world: rooms, walking,
   room text.
7. RP2350 board and target support, and the asset image packer.
