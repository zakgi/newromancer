# SPDX-License-Identifier: MIT
"""Instrument and sound-effect samples (*.SAM): headerless signed 8-bit mono PCM.

The samples are written as 8-bit WAV files at NOMINAL_RATE_HZ: note C at period 428 on the
NTSC audio clock (3,579,545 Hz / 428), the rate at which an instrument plays its recorded
pitch. PAL machines play the same period at 8,287 Hz. WAV stores 8-bit samples unsigned, so
each byte has its top bit flipped; the conversion loses nothing.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from io import BytesIO

from .containers import FormatError

NOMINAL_RATE_HZ: int = 8363
SIGN_FLIP: bytes = bytes(value ^ 0x80 for value in range(256))


@dataclass(frozen=True)
class Sample:
    data: bytes

    @staticmethod
    def from_data(data: bytes) -> Sample:
        if not data:
            raise FormatError("Sample: no data")
        return Sample(data=data)

    def to_wav(self, rate_hz: int = NOMINAL_RATE_HZ) -> bytes:
        output: BytesIO
        writer: wave.Wave_write
        with BytesIO() as output:
            with wave.open(output, "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(1)
                writer.setframerate(rate_hz)
                writer.writeframes(self.data.translate(SIGN_FLIP))
            return output.getvalue()
