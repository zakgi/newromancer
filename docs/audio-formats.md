# Audio formats

The two songs and the instrument and sound-effect samples are plain files on
the game disk. [songs.py](../scripts/newromancerlib/songs.py) and
[samples.py](../scripts/newromancerlib/samples.py) decode them.

## Sources

Every statement below refers to these files of the original disk
(SHA-256 `12e8ed5f8bf4345527258767ce9f06deddc6ee32ecbf7eafb124cf78196e1df9`);
addresses in the executable are given as hunk number plus offset, as in
[picture-formats.md](picture-formats.md#sources).

| File | Size | SHA-256 |
| --- | --- | --- |
| `KURT1` | 1,606 | `e79d9e3cabb9f70f7a05d1989ed6b72d0f92a5a0e35e383cc146052568d9f943` |
| `KURT2` | 866 | `518f0bb4b31107d4cd226feafcf51ecd2d1d5d8967bab777f86a60a3e09bab87` |
| `FLUTE.SAM` | 1,198 | `c90b34bee7a7f76018795a1b3c7729204fd8a2ffb0934eddcd793919067800d1` |
| `BASS.SAM` | 382 | `65bb53ae0ef54772bc1fe4e7b7b4907403ec0defbe45148081fbb56230469887` |
| `SYNTH.SAM` | 1,206 | `2759bd20cd5eb4cff2c855acc8270b45611fe95516bb768de8f7d6d079079a47` |
| `BASSDRUM.SAM` | 1,098 | `fa67091b6023fd292f130c7f943d766d0378eb5207e1b9d1884bd7a98de92c60` |
| `SNARE.SAM` | 1,042 | `6f1419393e4306b3dea0c8614fb4315066ceb0dc8b4d1e8d16c3426422dfc277` |
| `CLAP.SAM` | 626 | `76b72b3515d9a630c5e27a1b88c31d153ec10e79c6da649b8bbc33af804200fd` |
| `SndExplo.SAM` | 3,994 | `d6c8198fd1742b2c4c1accbbc3aefb6cfabf76917a408d15be31fae8a0d2bd59` |
| `SndOkay.SAM` | 1,680 | `8713c704c6930040184f46d594e461178b01622d9bcc9b6e70ada097d23a3362` |
| `SndShot1.SAM` | 6,690 | `51f0c79f651f71807ceae54f4937c6eb5a200ea79155293330e8c2e9c113f128` |
| `SndShot2.SAM` | 4,398 | `88ea0fcb2a273b4f078f10a658b28bfb87b56ae9284925f895017b55245e5d8d` |

## Songs

A song is a sequence of 16-bit big-endian note events with no header.
`KURT1` holds 803 events, `KURT2` 433.

| Byte | Bits | Contents |
| --- | --- | --- |
| first | 7 | instrument flag |
| first | 6-5 | channel |
| first | 4-0 | duration code |
| second | 7 | set when another event follows in the same step |
| second | 6-0 | octave x 12 + note; 0x7F is a rest |

**Observed** in the song player (hunk 2 + 0x50C):

- The player reads events until one with bit 7 of its second byte clear, then
  waits for the shortest duration among them before reading again. A song
  restarts from its first event when it reaches its end and looping is on.
- The duration is the entry of a 19-word table at hunk 2 + 0xF1E, times a
  scale factor that is 1. The table holds 0, 0, 0, 2, 0, 3, 4, 0, 6, 8, 0, 12,
  16, 0, 24, 32, 0, 48, 64; codes 19 to 31 would read past it and occur in
  neither song. The songs use codes 6, 9, 11, 12, 14, 15, 17 and 18.
- A rest starts no note.
- The note selects a period from the 12-entry table at hunk 2 + 0xF4C:
  428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226, the equal-tempered
  scale from C.
- The instrument flag and the channel select the sample, period and volume
  through a jump table at hunk 2 + 0xE22:

  | Flag, channel | Sample | Period | Volume |
  | --- | --- | --- | --- |
  | flag set, any channel; or channel 0 | 4, `FLUTE.SAM` | shifted left by 2 - octave | 53 |
  | channel 1 | 7 + octave: `BASSDRUM.SAM`, 8, `SNARE.SAM`, `CLAP.SAM` | as in the table | 63 |
  | channel 2 | 5, `BASS.SAM` | halved for octaves above 0 | 63 |
  | channel 3 | 6, `SYNTH.SAM` | shifted left by 2 - octave | 53 |

- Drums (channel 1) play their sample once; the other instruments loop it
  until the note's duration ends.
- The channel is the preferred one of the four Amiga audio channels; the
  player takes the next channel whose note has ended when it is busy.
- When four or fewer duration units remain, a channel's volume halves on each
  step until it falls below 3, then the channel stops.

Sample 8 has no file. The drum channel selects it at octave 1, three times in
`KURT1` and four times in `KURT2`, and those notes play the flute, sample 4.

The player runs from the vertical-blank interrupt, once per video field, so a
duration unit lasts 1/50 s on a PAL machine.

## Samples

A sample is headerless signed 8-bit mono PCM (**Observed**). `FLUTE.SAM`,
`BASS.SAM`, `SYNTH.SAM`, `BASSDRUM.SAM`, `SNARE.SAM` and `CLAP.SAM` are the
song instruments; the song loader (hunk 2 + 0x8C8) loads them as sample
numbers 4 to 7, 9 and 10 (**Observed**). The four `Snd` files are sound
effects, loaded separately (hunk 2 + 0x898).

The game plays a sample at the rate the period sets: the Amiga's audio clock
divided by the period. An instrument plays its recorded pitch at period 428,
the note C without shifting: 8,363 Hz on the NTSC clock of 3,579,545 Hz, the
usual reference rate for Amiga samples, and 8,287 Hz on the PAL clock of
3,546,895 Hz. The extractor writes WAV files at 8,363 Hz.

## Validation

All events of both songs decode; their fields agree with the earlier song
listing. All ten samples convert to 8-bit WAV and back byte for byte.
