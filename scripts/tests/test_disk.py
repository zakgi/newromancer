"""Checks against the original disk image named by NEWROMANCER_ADF; skipped when it is unset."""

from __future__ import annotations

import hashlib
import os
import struct
import unittest
from itertools import pairwise
from pathlib import Path
from typing import ClassVar

from newromancerlib.animations import RoomAnimations
from newromancerlib.bitmaps import (
    GAME_GRAPHICS,
    Picture,
    PictureLayout,
    ai_face_layouts,
    room_layouts,
)
from newromancerlib.containers import read_offset_table
from newromancerlib.disk import GameDisk
from newromancerlib.songs import Song
from newromancerlib.text import DatabaseText, MiscText, RoomText, TextTable

ADF_VARIABLE: str = "NEWROMANCER_ADF"

SOURCE_SHA256: dict[str, str] = {
    "bigpic0158": "0e09d360df1ceaa9e40466486adab44377b17b8998301d09e19e0a00c68ba227",
    "bigpic2": "d4a16e96dabf60654729e50c93a2d08538b364ec4570f5776c791b0d42cfe04f",
    "bigAIpic": "c5c9325f778d507cd15be9aeb508c0f59b049f0161f3e9a7b593d6b9fd01cf0d",
    "bigRnnd": "d96a1235c18278987d11c3a8684d7db5f6aa501b7cbf08d420d73aa208ba8a34",
    "bigRnnt": "ed071be9c366b39d3ea7799533f31acbbe0ced58a099c1830456598cc10bdb3d",
    "bigText": "50cfd2a8dd07acd22dbb2df6df187499261ce7120460ea825377db7fd745cebf",
    "bigdb": "53edc19338b76886c000120374811a8fb82ebd7a0dd332c9036475006cd2dd3c",
    "KURT1": "e79d9e3cabb9f70f7a05d1989ed6b72d0f92a5a0e35e383cc146052568d9f943",
    "KURT2": "518f0bb4b31107d4cd226feafcf51ecd2d1d5d8967bab777f86a60a3e09bab87",
}

# Digests of the decoded output, so that a change to a decoder cannot alter it unnoticed.
PICTURES_SHA256: str = "7ee36d7134f90db8be5344167ac5ca14d699aedf9dd5f25cefea4f8b28c2c92c"
FRAMES_SHA256: str = "499af6ade7d82b00d59d60ba0aa620519e1bf20748ca1f55daac14a5b6de1499"
STRINGS_SHA256: str = "de59cbb0bb45b9ff5088d8382838a96e5ad1a9604c1b2a01ea5d57d009697ebf"


@unittest.skipUnless(os.environ.get(ADF_VARIABLE), f"set {ADF_VARIABLE} to the original disk image")
class DiskTests(unittest.TestCase):
    disk: ClassVar[GameDisk]

    @classmethod
    def setUpClass(cls) -> None:
        cls.disk = GameDisk.from_path(Path(os.environ[ADF_VARIABLE]))

    def entries(self, name: str) -> tuple[bytes, ...]:
        data: bytes = bytes(self.disk.read(name))
        bounds: tuple[int, ...] = (*read_offset_table(data), len(data))
        return tuple(data[start:end] for start, end in pairwise(bounds))

    def test_original_image_and_sources(self) -> None:
        self.assertTrue(self.disk.is_original)
        name: str
        digest: str
        for name, digest in SOURCE_SHA256.items():
            self.assertEqual(self.disk.records[name.upper()].sha256, digest, name)

    def test_pictures(self) -> None:
        layouts: tuple[PictureLayout, ...] = (
            *(layout for _, layout in room_layouts()),
            *GAME_GRAPHICS,
            *ai_face_layouts(),
        )
        streams: tuple[bytes, ...] = (*self.entries("bigpic0158"), *self.entries("bigpic2"), *self.entries("bigAIpic"))
        self.assertEqual(len(streams), 82)
        self.assertEqual(len(layouts), 82)
        digest: hashlib._Hash = hashlib.sha256()
        stream: bytes
        layout: PictureLayout
        picture: Picture
        for stream, layout in zip(streams, layouts):
            picture = Picture.from_stream(stream, layout)
            digest.update(struct.pack(">HH", picture.width, picture.height))
            digest.update(picture.pixels)
            digest.update(struct.pack(">32H", *picture.palette.colors))
        self.assertEqual(digest.hexdigest(), PICTURES_SHA256)

    def test_animation_frames(self) -> None:
        digest: hashlib._Hash = hashlib.sha256()
        frame_count: int = 0
        room: int
        entry: bytes
        for room, entry in enumerate(self.entries("bigRnnd"), start=1):
            for frame in RoomAnimations.from_entry(entry, room).frames:
                digest.update(struct.pack(">HHBB", frame.width, frame.height, frame.x, frame.y))
                digest.update(frame.pixels)
                frame_count += 1
        self.assertEqual(frame_count, 350)
        self.assertEqual(digest.hexdigest(), FRAMES_SHA256)

    def test_text(self) -> None:
        tables: list[TextTable] = []
        room: int
        entry: bytes
        for room, entry in enumerate(self.entries("bigRnnt"), start=1):
            room_text: RoomText | None = RoomText.from_entry(entry, room)
            if room_text is not None:
                tables.append(room_text.table)
        for entry in self.entries("bigText"):
            misc_text: MiscText | None = MiscText.from_entry(entry)
            if misc_text is not None and misc_text.table is not None:
                tables.append(misc_text.table)
        for entry in self.entries("bigdb"):
            database_text: DatabaseText | None = DatabaseText.from_entry(entry)
            if database_text is not None:
                tables.append(database_text.table)
        strings: list[str] = [string for table in tables for string in table.strings]
        self.assertEqual(len(strings), 1609)
        self.assertEqual(
            hashlib.sha256(b"".join(string.encode() + b"\0" for string in strings)).hexdigest(), STRINGS_SHA256
        )

    def test_songs(self) -> None:
        self.assertEqual(len(Song.from_data(bytes(self.disk.read("KURT1"))).events), 803)
        self.assertEqual(len(Song.from_data(bytes(self.disk.read("KURT2"))).events), 433)


if __name__ == "__main__":
    unittest.main()
