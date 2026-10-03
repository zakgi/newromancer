# SPDX-License-Identifier: MIT
"""Read-only access to the game disk image (ADF) through amitools.

The game's files sit in an AmigaDOS OFS volume named NEUROMANCER (Observed). The whole image
is read once into memory; decoders receive file contents as bytes and never touch the image.

The original disk is 901,120 bytes with SHA-256
12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9. Other images, such as
patched game disks, are accepted with a warning.

Usage:
    disk = GameDisk.from_path(Path("assets/Neuromancer.adf"))
    data = disk.read("bigpic0158")
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath

from amitools.fs.ADFSDir import ADFSDir
from amitools.fs.ADFSNode import ADFSNode
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.blkdev.BlockDevice import BlockDevice
from amitools.fs.FSError import FSError

from .containers import FormatError

LOGGER: logging.Logger = logging.getLogger(__name__)

ORIGINAL_DISK_SHA256: str = "12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9"


@dataclass(frozen=True)
class SourceRecord:
    path: str
    size: int
    sha256: str


@dataclass
class GameDisk:
    image_name: str
    image_sha256: str
    volume_name: str
    files: dict[str, bytes] = field(default_factory=dict)
    records: dict[str, SourceRecord] = field(default_factory=dict)

    @staticmethod
    def from_path(path: Path) -> GameDisk:
        return GameDisk.from_data(path.read_bytes(), path.name)

    @staticmethod
    def from_data(image: bytes, image_name: str) -> GameDisk:
        """Read every file of an ADF image held in memory; keys are upper-case volume paths."""
        image_sha256: str = hashlib.sha256(image).hexdigest()
        disk: GameDisk
        blkdev: BlockDevice | None = None
        volume: ADFSVolume | None = None
        try:
            blkdev = BlkDevFactory().open(image_name, read_only=True, fobj=BytesIO(image))
            volume = ADFSVolume(blkdev)
            volume.open()
            disk = GameDisk(
                image_name=image_name,
                image_sha256=image_sha256,
                volume_name=volume.get_volume_name().get_unicode(),
            )
            disk.add_directory(volume.get_root_dir(), PurePosixPath())
        except (FSError, OSError, ValueError) as error:
            raise FormatError(f"{image_name}: not a readable AmigaDOS disk image ({error})") from error
        finally:
            if volume is not None:
                volume.close()
            if blkdev is not None:
                blkdev.close()
        if not disk.is_original:
            LOGGER.warning("%s is not the original disk (SHA-256 %s)", image_name, image_sha256)
        LOGGER.debug("Read %d files from volume %s on %s", len(disk.files), disk.volume_name, image_name)
        return disk

    @property
    def is_original(self) -> bool:
        return self.image_sha256 == ORIGINAL_DISK_SHA256

    def add_directory(self, directory: ADFSDir, prefix: PurePosixPath) -> None:
        node: ADFSNode
        path: PurePosixPath
        key: str
        data: bytes
        for node in directory.get_entries():
            path = prefix / node.get_file_name().get_unicode_name()
            if node.is_dir():
                self.add_directory(node, path)
            else:
                key = path.as_posix().upper()
                if key in self.files:
                    raise FormatError(f"{self.image_name}: ambiguous file name {path}")
                data = node.get_file_data()
                self.files[key] = data
                self.records[key] = SourceRecord(
                    path=path.as_posix(),
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )

    def read(self, name: str) -> bytes:
        key: str = name.upper()
        if key not in self.files:
            raise FormatError(f"{self.image_name}: missing file {name}")
        return self.files[key]
