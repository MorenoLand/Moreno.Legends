# Native audio data

`tools/audio.py` reads the extracted PAL `SLES_035.56`, `COMMON/INIT.BIN`, `COMMON/TITLE.BIN`, `DAT/ST0F.BIN`, `DAT/ST0F00.BIN` and `DAT/ST0F01.BIN` from `build/disc-assets`. Its `export_audio(cue=None)` API returns the generated manifest; the CLI accepts `--cue`. Run `python tools/audio.py audio` after disc extraction. FFmpeg must be on PATH. The exporter downloads the official FluidSynth 2.6.1 Windows runtime into `build/audio` when absent; Linux/macOS use the installed native FluidSynth shared library.

## Sound banks

Type-5 headers store physical slot at `+0x0C`, logical ID at `+0x0E`, SPU offset at `+0x10`, metadata length at `+0x14`, waveform length at `+0x18` and program count at `+0x1C`. Metadata starts at header `+0x30`; waveform bytes start at the next `0x800` sector after metadata. Programs have eight-byte headers followed by exactly sixteen twenty-byte tone records per program. The native loader is SLES `0x800186C4` / `0x80019798` / `0x800198BC`.

INIT's bank is at file `0x9800`, with metadata at `0x9830` and waveform bytes at `0xA000`. Native SPU upload and tone relocation add the same physical bank base (`0x1010` for slot zero); sample offsets retain eight-byte address granularity. Samples use sixteen-byte PS1 ADPCM blocks, twenty-eight decoded samples per block and native loop/end flags.

SLES `0x8001F000` selects eight-byte sound descriptors. Direct sound `0x95` is descriptor `0000015217000000` at RAM `0x80069A24`: physical slot zero, program one, tone five, voice twenty-three. Native `0x8001EB4C` uses tone byte `+0x0A` plus descriptor note delta as the requested note. `0x8001F044` subtracts tone center byte `+8` and calls `0x8001F2A0`, interpolating tone fine byte `+9`. The sample clock is `44100 * pitch / 4096`.

Original driver execution for `0x95` produced requested note 65, tone center 89 and SPU pitch 1024 (11025 Hz). The source waveform is file `0x18260`, 1056 encoded bytes and 1848 decoded frames. Constructor/uploader execution confirmed SPU base `0x1010`, original tone bytes and waveform upload beginning at file `0xA000`; no sample-offset correction is applied. Capture provenance is generated at `build/audio/buster-native-pitch.json` and `build/audio/buster-native-upload.json`.

Effects use the reference SPU integer ADPCM predictor/history/clamp, four-tap Gaussian table and ADSR divider/rate stepping at 44100 Hz. Native pitch advances the source counter; it does not become a Godot interpolation rate. Cue `0x95` produces a 44100-Hz WAV with 7392 frames and the same 0.167619-second duration. This cue belongs to the kick/melee actor, not the Buster. Dry effects retain bank/program/tone gain in manifest `volume_db`; wet variants bake that gain before processing the native reverb registers. The exporter preserves existing effect import settings except for setting `compress/mode=0`, keeping the rendered PCM instead of QOA. The actual Buster uses cue `0x9A`.

## Actor sound events

| Event | Sound ID | Native call |
| --- | --- | --- |
| Footstep | `0x91` | GAME `0x800CC8C8`, animation event bit `0x80` |
| Jump | `0x92` | GAME `0x800C787C` |
| Land | `0x93` | GAME `0x800C81E8` |
| Kick/melee actor-zero emission | `0x95` | GAME `0x800D0298` |
| Buster actor-one emission | `0x9A` | GAME `0x800D07CC`–`0x800D07E8` |
| Menu navigation | `0x80` | DEMO `0x800AD904` |
| Menu confirmation | `0x81` | DEMO `0x800AD750` |
| Menu cancellation | `0x82` | DEMO `0x800AD710` |

Run control one has footstep records three and eleven; walk control two has records six and twenty-two. Both action dispatchers `0x800CE5D4` and `0x800CE6F0` allocate actor subtype zero for action ID one, the kick. SLES actor dispatch table `0x8006B3A0[0]` selects GAME `0x800D0194`; state zero selects `0x800D01F4`, which plays `0x95` at the cached player root coordinates `+0x490/+0x492/+0x494`. Weapon ID two selects the Buster actor `0x800D03D0`, sound `0x9A`, and cached bone-seven muzzle at `+0x4C8/+0x4CA/+0x4CC`. Underwater flags select cue `0xF4` instead.

The class-eight dungeon attack uses cue `0xD4`. Its descriptor at SLES `0x80069C1C` is `0001045230280000`, selecting physical bank one, program four, tone five. That bank is stored in `DAT/ST0F.BIN` at section `0x1C800`; exporting only INIT's bank zero omits this sound.

## Footsteps and stage acoustics

GAME `0x800CC850`–`0x800CC8CC` selects cue `0x90` for animation event `0x40` and cue `0x91` for event `0x80`. Both descriptors use INIT physical bank zero, program one: tone zero has SPU pitch 1323; tone one has pitch 1486. They reference the same ADPCM waveform at INIT file `0x16200`. Across the extracted DAT archives, INIT is the only type-five bank assigned physical slot zero. Terrain flag `player+0xBE` adds the native splash/dust actor through `0x800CCAE8` without replacing the footstep sound ID.

Location changes the original reverb enable flag. SLES `0x8001D7C4` forwards its second argument into `0x8001D834`, storing sound flags at `0x8007CFC2`. SLES `0x8001ED94`–`0x8001EDD4` enables reverb only when the selected tone's byte `+5` is nonzero and sound flag bit zero is set. ST0FT initialization at `0x800E728C` passes one; ST04T/ST05T/ST06T/ST07T pass zero. ST40T `0x800E7588`–`0x800E75AC` additionally enables it in area one and disables it in other areas. `tools/audio.py` extracts these numeric stage rules from the native calls.

The original SPU initializes reverb profile one at SLES `0x8001D6A4`. `0x8001FF68` resolves its descriptor at `0x800696BC`: mode `0x103` selects Studio Medium preset three and clears the work area; left/right output depths are `0x4080`. The 32 native register values come from `0x80071914 + 3*68 + 4`; the work area starts at `0xF6F8*8`. Wet exports use the reference integer 22050-Hz reflection, comb and all-pass processing from `psxrecomp/runtime/src/spu.c`, retaining their stereo tails. Runtime selection uses `GameAudio.set_stage(stage, area)` and `set_area(area)`; it does not infer an acoustic profile from a room name or choose invented surface recordings.

The reference SPU uses a two-frame input average and linear output reconstruction instead of a verified hardware boundary filter. Each exported effect starts with an empty work area, so simultaneous sounds do not share hardware clipping/history. Tails are trimmed only after output remains below eight signed16 PCM units for a complete native work-area period. These limits are recorded in the generated manifest; the exports do not establish complete SPU DSP parity.

## ST0F scores

| Music ID | Archive | Sequence section | Bank section | Logical bank / sequence |
| --- | --- | --- | --- | --- |
| `0x19` | `ST0F00.BIN` | `0x13800` | `0x16800` | 53 / 21 |
| `0x30` | `ST0F01.BIN` | `0x11000` | `0x14000` | 71 / 39 |
| `0x00` | `TITLE.BIN` | `0x23000` | `0x23800` | 32 / 0 |

DEMO `0x800AD690` calls SLES `0x80020210` with title music ID zero. Its descriptor at `0x800696E4` is `3120000200000000`. TITLE's type-nine compressed sequence uses the same native word-LZ format as other compressed sections; it decodes to 3160 bytes, PPQN 48 and initial tempo 400000 microseconds per quarter note. The rendered source score has 425 note-on events and a 29.008322-second loop.

The score uses a custom event stream: status, event payload, then the following variable-length delay. `FF 51` takes exactly three big-endian tempo bytes and then a delay; it has no SMF length byte. `FF 2F 00` ends the stream without another delay. SLES `0x80021EDC` handles these commands, `0x80022054` reads one to four delay bytes, and `0x80020E38` reads initial tempo and PPQN. The tick period is `max(2400000, tempo_microseconds * 1000 // PPQN)` nanoseconds.

The exporter renders those events with the original instrument waveforms, tone zones, pitches, pans and volumes in a generated SoundFont. It generates no substitute instruments. FluidSynth rendering does not establish parity with PS1 Gaussian interpolation, exact ADSR or reverb; the manifest explicitly marks SPU DSP parity unverified. ST0FT initialization calls `0x8001D7C4` with selector `0x19`; a native room-by-room `0x19` versus `0x30` selection rule has not been established.
