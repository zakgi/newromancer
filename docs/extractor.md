# Python resource extractor

[scripts/extract.py](../scripts/extract.py) reads the game's resources straight
from the original disk image and writes them as PNG, WAV and text files. The
decoders live in [scripts/newromancerlib](../scripts/newromancerlib); the
formats are described in [picture-formats.md](picture-formats.md). It requires
Python 3.10 or newer, amitools to read the disk image, Colorama for terminal
logging and PyPNG for PNG encoding.

## Installation

The root `pyproject.toml` declares the package, its dependencies, the
`newromancer-extract` command, and Black's 120-column formatting. With uv:

```sh
uv sync --extra dev
uv run newromancer-extract --help
```

Alternatively, activate a Python 3.10+ virtual environment and install with
`python -m pip install -e ".[dev]"`. Omit the `dev` extra when Black and Ruff
are not needed. Direct invocation as `python3 scripts/extract.py` works within
that environment too.

## The disk image

The repository ships no game data. Place the original disk image at
`assets/Neuromancer.adf` (the directory is ignored by git) or pass its path as
the second argument. The original image is 901,120 bytes with SHA-256
`12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9`. Other images,
such as patched game disks, are read with a warning; the disk image is never
modified.

## Commands

Run from the project root:

```sh
uv run newromancer-extract all -o work/extracted
uv run newromancer-extract pictures path/to/Neuromancer.adf -o work/pictures
```

| Command | Output |
| --- | --- |
| `files` | every file on the disk, unchanged, in its directory |
| `pictures` | `rooms/roomNN.png` (by room number), `graphics/graphicsNN.png`, `faces/faceNN.png` |
| `animations` | `roomNN/frameMM_copy.png` and `roomNN/frameMM_xor.png` for every animation frame |
| `text` | `rooms.txt`, `misc.txt` with `miscNN.bin` for its non-text blocks, `databases.txt` |
| `songs` | `KURT1.txt` and `KURT2.txt`, one line per note event |
| `samples` | one 8-bit WAV per `.SAM` sample, at 8,363 Hz |
| `all` | all of the above, each in a subdirectory named after its command |

The output directory must not exist yet. It is created only after everything
requested has decoded, so a format error leaves nothing behind. An I/O error
while writing can leave a partial directory; use a new one for the next run.
`-l`/`--logging-level` selects the minimum logging level (default `INFO`).

Every run writes `manifest.json`: the disk image's name, digest and volume
name, each disk file read (path, size, SHA-256), and each output (path, size,
SHA-256).

Write outputs under `work/`, which git ignores. They are derived from the
game's data and must not be committed.

### Pictures and animations

PNG files are 8-bit indexed images carrying the picture's 32-color palette, so
pixel values are the game's color indices. Each 4-bit palette channel is
scaled by 17.

Each animation frame is drawn onto its room's untouched background in both of
the ways the game draws frames: `copy` replaces the background under the
frame, `xor` combines the two. Most frames are XOR frames, for which the
`copy` version shows the raw difference; the file does not record which way
the game draws a frame.

### Text

`rooms.txt` lists, for every room with text, its flags (PAX booth, cyberspace
jack), action offsets, dialogue pointers, known words and known locations,
then its strings; string 0 is shown on the first visit, string 1 afterwards.
`databases.txt` gives each database's index, level count and passwords before
its strings. Offsets are relative to the start of the room or database entry.

## Tests

```sh
python -m unittest discover -s scripts -p 'test_*.py'
```

`scripts/tests/test_decoders.py` covers the decoders with synthetic data.
`scripts/tests/test_disk.py` checks the original disk image: the digests of
the source files, the number of pictures, frames, strings and note events,
and digests of all decoded pixels and strings. It runs only when
`NEWROMANCER_ADF` names the image:

```sh
NEWROMANCER_ADF=assets/Neuromancer.adf python -m unittest discover -s scripts -p 'test_*.py'
```
