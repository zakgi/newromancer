# SPDX-License-Identifier: MIT
"""Songs (KURT1, KURT2): a sequence of 16-bit big-endian note events.

    first byte   bit 7     octave flag
                 bits 6-5  channel
                 bits 4-0  duration code, an index into DURATION_TABLE
    second byte  bit 7     set when another event follows in the same step
                 bits 6-0  note and octave: octave * 12 + note; 0x7F is a rest, no note starts

The sample an event plays follows from its channel: channel 0, or any event with the octave
flag set, plays sample 4; channel 1 plays sample octave + 7 (drums), and sample 8, which has
no file, plays sample 4 instead; channel 2 plays sample 5; channel 3 plays sample 6.
SAMPLE_FILES names the sample files. Drums play once; the other instruments loop until the
event's duration ends.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .containers import FormatError

EVENT_FORMAT: str = ">H"
EVENT_SIZE: int = struct.calcsize(EVENT_FORMAT)
NOTES_PER_OCTAVE: int = 12
REST: int = 0x7F

DURATION_TABLE: tuple[int, ...] = (
    0, 0, 0, 2, 0, 3, 4, 0, 6, 8, 0, 12, 16, 0, 24, 32,
    0, 48, 64, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
)  # fmt: skip

NOTE_NAMES: tuple[str, ...] = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")

# Sample number to file name.
SAMPLE_FILES: dict[int, str] = {
    4: "FLUTE.SAM",
    5: "BASS.SAM",
    6: "SYNTH.SAM",
    7: "BASSDRUM.SAM",
    9: "SNARE.SAM",
    10: "CLAP.SAM",
}

MELODY_SAMPLE: int = 4
DRUM_SAMPLE_BASE: int = 7
MISSING_DRUM_SAMPLE: int = 8
CHANNEL_SAMPLES: dict[int, int] = {2: 5, 3: 6}


@dataclass(frozen=True)
class NoteEvent:
    octave_flag: bool
    channel: int
    duration_code: int
    continues: bool
    note_octave: int

    @staticmethod
    def from_word(word: int) -> NoteEvent:
        return NoteEvent(
            octave_flag=bool(word & 0x8000),
            channel=(word >> 13) & 0x3,
            duration_code=(word >> 8) & 0x1F,
            continues=bool(word & 0x80),
            note_octave=word & 0x7F,
        )

    @property
    def octave(self) -> int:
        return self.note_octave // NOTES_PER_OCTAVE

    @property
    def note(self) -> int:
        return self.note_octave % NOTES_PER_OCTAVE

    @property
    def is_rest(self) -> bool:
        return self.note_octave == REST

    @property
    def duration(self) -> int:
        return DURATION_TABLE[self.duration_code]

    @property
    def sample(self) -> int:
        sample: int
        if self.octave_flag or self.channel == 0:
            sample = MELODY_SAMPLE
        elif self.channel == 1:
            sample = self.octave + DRUM_SAMPLE_BASE
            if sample == MISSING_DRUM_SAMPLE:
                sample = MELODY_SAMPLE
        else:
            sample = CHANNEL_SAMPLES[self.channel]
        return sample

    def describe(self) -> str:
        pitch: str = "rest" if self.is_rest else f"{NOTE_NAMES[self.note]}-{self.octave}"
        sample_file: str = SAMPLE_FILES.get(self.sample, "none")
        return (
            f"{pitch:<5} sample {self.sample:2} ({sample_file}) duration {self.duration:2}"
            f" channel {self.channel}{' continues' if self.continues else ''}"
        )


@dataclass(frozen=True)
class Song:
    events: tuple[NoteEvent, ...]

    @staticmethod
    def from_data(data: bytes) -> Song:
        if len(data) % EVENT_SIZE:
            raise FormatError(f"Song: {len(data)} bytes do not form 16-bit events")
        return Song(events=tuple(NoteEvent.from_word(word) for (word,) in struct.iter_unpack(EVENT_FORMAT, data)))
