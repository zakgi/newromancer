#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract Neuromancer resources from the game disk image using Python 3.10+.

Usage:
    python3 scripts/extract.py all -o work/extracted
    python3 scripts/extract.py files assets/Neuromancer.adf -o work/files
    python3 scripts/extract.py pictures -o work/pictures
    python3 scripts/extract.py animations -o work/animations
    python3 scripts/extract.py text -o work/text
    python3 scripts/extract.py songs -o work/songs
    python3 scripts/extract.py samples -o work/samples

The disk image defaults to assets/Neuromancer.adf. The output directory must be new; it is
created only after every requested resource has decoded. Each run writes manifest.json with
the image digest, the files read and every output's digest. Formats: docs/picture-formats.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path, PurePosixPath

from newromancerlib.animations import AnimationFrame, BlitMode, RoomAnimations, compose
from newromancerlib.bitmaps import (
    GAME_GRAPHICS,
    Picture,
    PictureLayout,
    ai_face_layouts,
    room_layouts,
)
from newromancerlib.containers import FormatError, read_offset_table
from newromancerlib.disk import GameDisk
from newromancerlib.logging import setup_logging
from newromancerlib.samples import Sample
from newromancerlib.songs import Song
from newromancerlib.text import DatabaseText, MiscText, RoomText, TextTable

LOGGER: logging.Logger = logging.getLogger(__name__)

DEFAULT_ADF: Path = Path("assets/Neuromancer.adf")
COMMANDS: tuple[str, ...] = ("files", "pictures", "animations", "text", "songs", "samples")
SONG_FILES: tuple[str, ...] = ("KURT1", "KURT2")
SAMPLE_SUFFIX: str = ".SAM"
MANIFEST_NAME: str = "manifest.json"


@dataclass
class Options(argparse.Namespace):
    command: str = ""
    adf: Path = DEFAULT_ADF
    output: Path = Path()
    logging_level: str = "INFO"


def parse_args(argv: list[str] | None = None) -> Options:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=("all", *COMMANDS))
    parser.add_argument("adf", type=Path, nargs="?", default=DEFAULT_ADF, help=f"disk image (default: {DEFAULT_ADF})")
    parser.add_argument("-o", "--output", type=Path, required=True, help="new output directory")
    parser.add_argument(
        "-l",
        "--logging-level",
        type=str.upper,
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "FATAL"),
        default="INFO",
        help="minimum logging level (default: INFO)",
    )
    options: Options = Options()
    parser.parse_args(argv, namespace=options)
    return options


@dataclass(frozen=True)
class OutputRecord:
    path: str
    size: int
    sha256: str


@dataclass
class Extraction:
    disk: GameDisk
    outputs: dict[PurePosixPath, bytes] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)
    backgrounds: dict[int, Picture] = field(default_factory=dict)

    def read(self, name: str) -> bytes:
        data: bytes = bytes(self.disk.read(name))
        self.sources.add(name.upper())
        return data

    def entries(self, name: str) -> tuple[bytes, ...]:
        """The slices of a big* file that its offset table delimits."""
        data: bytes = self.read(name)
        bounds: tuple[int, ...] = (*read_offset_table(data), len(data))
        return tuple(data[start:end] for start, end in pairwise(bounds))

    def add(self, path: PurePosixPath, data: bytes) -> None:
        if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise FormatError(f"Unsafe output path: {path}")
        if path in self.outputs:
            raise FormatError(f"Duplicate output path: {path}")
        self.outputs[path] = data

    def run(self, command: str) -> None:
        name: str
        if command == "all":
            for name in COMMANDS:
                self.run_command(name, PurePosixPath(name))
        else:
            self.run_command(command, PurePosixPath())

    def run_command(self, command: str, prefix: PurePosixPath) -> None:
        match command:
            case "files":
                self.add_files(prefix)
            case "pictures":
                self.add_pictures(prefix)
            case "animations":
                self.add_animations(prefix)
            case "text":
                self.add_text(prefix)
            case "songs":
                self.add_songs(prefix)
            case "samples":
                self.add_samples(prefix)
            case _:
                raise ValueError(f"Unknown command {command}")

    def add_files(self, prefix: PurePosixPath) -> None:
        key: str
        for key in sorted(self.disk.records):
            self.add(prefix / self.disk.records[key].path, self.read(key))
        LOGGER.info("Files: %d", len(self.disk.records))

    def decode_pictures(self, name: str, layouts: tuple[PictureLayout, ...]) -> tuple[Picture, ...]:
        streams: tuple[bytes, ...] = self.entries(name)
        if len(streams) != len(layouts):
            raise FormatError(f"{name}: {len(streams)} pictures, expected {len(layouts)}")
        return tuple(Picture.from_stream(stream, layout) for stream, layout in zip(streams, layouts))

    def room_backgrounds(self) -> dict[int, Picture]:
        if not self.backgrounds:
            rooms: tuple[tuple[int, PictureLayout], ...] = room_layouts()
            pictures: tuple[Picture, ...] = self.decode_pictures("bigpic0158", tuple(layout for _, layout in rooms))
            self.backgrounds = {room: picture for (room, _), picture in zip(rooms, pictures)}
        return self.backgrounds

    def add_pictures(self, prefix: PurePosixPath) -> None:
        room: int
        picture: Picture
        number: int
        for room, picture in self.room_backgrounds().items():
            self.add(prefix / "rooms" / f"room{room:02}.png", picture.to_png())
        for number, picture in enumerate(self.decode_pictures("bigpic2", GAME_GRAPHICS), start=1):
            self.add(prefix / "graphics" / f"graphics{number:02}.png", picture.to_png())
        faces: tuple[PictureLayout, ...] = ai_face_layouts()
        for number, picture in enumerate(self.decode_pictures("bigAIpic", faces), start=1):
            self.add(prefix / "faces" / f"face{number:02}.png", picture.to_png())
        LOGGER.info("Pictures: %d rooms, %d graphics, %d faces", len(self.backgrounds), len(GAME_GRAPHICS), len(faces))

    def add_animations(self, prefix: PurePosixPath) -> None:
        backgrounds: dict[int, Picture] = self.room_backgrounds()
        frame_count: int = 0
        room: int
        entry: bytes
        animations: RoomAnimations
        number: int
        frame: AnimationFrame
        mode: BlitMode
        for room, entry in enumerate(self.entries("bigRnnd"), start=1):
            animations = RoomAnimations.from_entry(entry, room)
            if animations.frames and room not in backgrounds:
                raise FormatError(f"bigRnnd: room {room} has frames but no background")
            for number, frame in enumerate(animations.frames, start=1):
                for mode in BlitMode:
                    self.add(
                        prefix / f"room{room:02}" / f"frame{number:02}_{mode.value}.png",
                        compose(backgrounds[room], frame, mode).to_png(),
                    )
            frame_count += len(animations.frames)
        LOGGER.info("Animations: %d frames", frame_count)

    def add_text(self, prefix: PurePosixPath) -> None:
        lines: list[str] = []
        string_count: int = 0
        index: int
        entry: bytes
        room_text: RoomText | None
        for index, entry in enumerate(self.entries("bigRnnt"), start=1):
            room_text = RoomText.from_entry(entry, index)
            if room_text is None:
                lines.append(f"=== Room {index:02}: empty ===\n")
            else:
                lines.extend(describe_room(room_text))
                string_count += len(room_text.table.strings)
        self.add(prefix / "rooms.txt", "\n".join(lines).encode())
        lines = []
        misc_text: MiscText | None
        for index, entry in enumerate(self.entries("bigText")):
            misc_text = MiscText.from_entry(entry)
            if misc_text is None:
                lines.append(f"=== Entry {index:02}: empty ===\n")
            elif misc_text.table is None:
                lines.append(f"=== Entry {index:02}: data block, see misc{index:02}.bin ===\n")
                self.add(prefix / f"misc{index:02}.bin", misc_text.block)
            else:
                lines.append(f"=== Entry {index:02} ===\n")
                lines.extend(describe_strings(misc_text.table))
                string_count += len(misc_text.table.strings)
        self.add(prefix / "misc.txt", "\n".join(lines).encode())
        lines = []
        database_text: DatabaseText | None
        for index, entry in enumerate(self.entries("bigdb")):
            database_text = DatabaseText.from_entry(entry)
            if database_text is None:
                lines.append(f"=== Entry {index:02}: empty ===\n")
            else:
                lines.append(
                    f"=== Entry {index:02}: database {database_text.index}, {database_text.levels} levels,"
                    f" passwords: {', '.join(database_text.passwords) or 'none'} ===\n"
                )
                lines.extend(describe_strings(database_text.table))
                string_count += len(database_text.table.strings)
        self.add(prefix / "databases.txt", "\n".join(lines).encode())
        LOGGER.info("Text: %d strings", string_count)

    def add_songs(self, prefix: PurePosixPath) -> None:
        name: str
        song: Song
        for name in SONG_FILES:
            song = Song.from_data(self.read(name))
            self.add(
                prefix / f"{name}.txt",
                "".join(f"{index:4}: {event.describe()}\n" for index, event in enumerate(song.events)).encode(),
            )
        LOGGER.info("Songs: %d", len(SONG_FILES))

    def add_samples(self, prefix: PurePosixPath) -> None:
        sample_count: int = 0
        key: str
        path: PurePosixPath
        for key in sorted(self.disk.records):
            path = PurePosixPath(self.disk.records[key].path)
            if path.suffix.upper() == SAMPLE_SUFFIX:
                self.add(prefix / f"{path.stem}.wav", Sample.from_data(self.read(key)).to_wav())
                sample_count += 1
        LOGGER.info("Samples: %d", sample_count)

    def manifest(self) -> bytes:
        outputs: list[OutputRecord] = [
            OutputRecord(path=path.as_posix(), size=len(data), sha256=hashlib.sha256(data).hexdigest())
            for path, data in sorted(self.outputs.items())
        ]
        document: dict[str, object] = {
            "image": {
                "name": self.disk.image_name,
                "sha256": self.disk.image_sha256,
                "original": self.disk.is_original,
                "volume": self.disk.volume_name,
            },
            "sources": [asdict(self.disk.records[key]) for key in sorted(self.sources)],
            "outputs": [asdict(record) for record in outputs],
        }
        return (json.dumps(document, indent=2) + "\n").encode()

    def write(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=False)
        path: PurePosixPath
        data: bytes
        target: Path
        for path, data in self.outputs.items():
            target = root.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (root / MANIFEST_NAME).write_bytes(self.manifest())


def describe_strings(table: TextTable) -> list[str]:
    return [f"--- String {index} ---\n{string}\n" for index, string in enumerate(table.strings)]


def describe_room(room_text: RoomText) -> list[str]:
    actions: str = ", ".join("-" if action is None else f"0x{action:X}" for action in room_text.actions)
    lines: list[str] = [
        f"=== Room {room_text.room:02} ===",
        f"PAX booth: {'yes' if room_text.has_pax else 'no'}",
        f"Cyberspace jack: {'yes' if room_text.has_cyberspace_jack else 'no'}",
        f"Actions: {actions}",
        f"Dialogue pointers: {describe_pointers(room_text.dialogue_pointers)}",
        f"Secondary dialogue pointers: {describe_pointers(room_text.secondary_dialogue_pointers)}",
        f"Known words: {', '.join(room_text.known_words) or 'none'}",
        f"Known locations: {', '.join(room_text.known_locations) or 'none'}\n",
    ]
    lines.extend(describe_strings(room_text.table))
    return lines


def describe_pointers(pointers: tuple[int | None, ...]) -> str:
    return ", ".join("-" if pointer is None else f"0x{pointer:X}" for pointer in pointers)


def main(argv: list[str] | None = None) -> int:
    options: Options = parse_args(argv)
    logger: logging.Logger = setup_logging(options.logging_level)
    status: int = 1
    try:
        extraction: Extraction = Extraction(disk=GameDisk.from_path(options.adf))
        extraction.run(options.command)
        extraction.write(options.output)
        logger.info("Wrote %d files to %s", len(extraction.outputs) + 1, options.output)
        status = 0
    except (OSError, FormatError) as error:
        logger.error("%s", error)
    return status


if __name__ == "__main__":
    sys.exit(main())
