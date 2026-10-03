# Asset extraction tools

The repository ships no game data. `tools/assets.py` rebuilds every runtime asset from your own copy of the PAL disc (SLES-03556); everything it writes is ignored by Git.

## Requirements

| Need | Used for | Notes |
| --- | --- | --- |
| Python 3.13 or newer | all tools | developed on 3.14, checked on 3.13; the standard library plus `pip` is enough |
| `unicorn` 2.1.4 | emulating the original MIPS code (scenes, menus, HUD, door/cutscene scripts) | installed automatically into `build/pydeps` on first run (needs `pip` and network) |
| `capstone` 5.0.9 | the `special_modes` export only | installed automatically into `build/pydeps` on first use |
| FFmpeg on `PATH` | decoding PS1 ADPCM samples, encoding every extracted sound to Ogg Vorbis (`libvorbis`), transcoding STR movies (`libtheora`, `libvorbis`) | `ffmpeg` must be runnable from the shell that starts the tool |
| FluidSynth | rendering the original scores (encoded to Ogg Vorbis afterwards) | Windows: the v2.6.1 release is downloaded from GitHub into `build/audio` on first use. Linux/macOS: install the FluidSynth shared library (`libfluidsynth`) with your package manager |
| Redot 26.2 | opening the project and running the game | [Redot releases](https://github.com/Redot-Engine/redot-engine/releases) |

Disk: about 4 GB of generated assets in `assets/`, about 100 MB of extracted disc files in `build/disc-assets`, plus working caches elsewhere in `build/`.

## The disc image

Dump your own copy of the European (PAL) release of Mega Man Legends 2, serial SLES-03556, as a BIN/CUE pair. Track 1 must be `MODE2/2352`; the CUE file and the BIN it names must sit in the same folder. The tools never modify the image and nothing from it is committed.

## Extract everything

```
python tools/assets.py "path/to/Mega Man Legends 2.cue"
```

This one command

1. copies the game ISO files into `build/disc-assets` (a file already there is verified against the disc and reused),
2. exports every group listed below into `assets/`,
3. writes `build/asset_coverage.json` (source file hashes, what was exported, what failed).

The full run exports location names and every stage's geometry first, then mine door metadata and normalized routes, followed by props, model archives, interface data, audio and voices, and finally the scenes and layouts that consume them. Existing output is not needed for this dependency order.

The root `ZNULL.DAT` padding entry is skipped: it contains no game assets and can reference headerless zero sectors beyond the track. Disc-file copies, raw movie sectors and opening-audio manifests follow the same output policy as the other exports; FFmpeg returns decoded samples and transcoded movies through stdout so `write_output` controls their files too.

The exit status is nonzero if any export failed; the report names the failing task. After it finishes, open the project in Redot (see below).

Already extracted? `python tools/assets.py` (no CUE) reuses `build/disc-assets`. The `media` group needs the raw disc sectors, so without a CUE that group is reported as `requires_disc` and the exit status is 1; add `--only` for the other groups to avoid that, for example `python tools/assets.py --only world --only models --only textures --only ui --only audio --only cinematics`.

`python tools/assets.py --help` prints every option and the group list.

## Editor import settings

Extraction writes Redot 26.2 `.import` presets for PNG, GLB and bitmap-font assets through `write_output`. Opening the project in the editor uses these presets directly. PNGs use lossless compression, no mipmaps and disabled automatic 3D recompression; alpha-border repair remains enabled for the snow/reflection textures that use linear filtering. GLBs retain skeletons and animation settings while disabling generated LODs, shadow meshes, light baking and vertex compression. Embedded images remain lossless `ImageTexture` resources instead of generating another external PNG import.

UIDs hash the case-preserving `res://` path with SHA-256, mask its first eight little-endian bytes to 63 bits, and use Redot's `abcdefghijklmnopqrstuvwxy012345678` base-34 alphabet. Generated scripts/shaders receive `.uid` files; generated text scenes/resources receive embedded UIDs. Existing sidecars are kept by default; `--overwrite` or a matching `--overwrite-only` pattern updates controlled settings while preserving editor cache paths and dependency sections. Asset and sidecar patterns are independent.

`assets/audio/`, `assets/library/`, `assets/extracted/`, `assets/converted/` and the bulk game folders `assets/levels/`, `assets/stage_props/`, `assets/opening/`, `assets/flutter/` and `assets/minimap/` receive `.gdignore` files, so the editor never imports them. Audio loaders read the Ogg Vorbis files directly (`AudioStreamOggVorbis.load_from_file`; a manifest path with the other extension still resolves to whichever of `.ogg`/`.wav` exists). GLB and PNG files in the bulk game folders get no `.import` sidecar (`write_output` skips them); `scripts/data/runtime_loader.gd`, registered as a `ResourceFormatLoader` by the `AssetStore` autoload, serves every `load()`, `ResourceLoader.exists()` and threaded request for them: a GLB goes through `GLTFDocument` into a `PackedScene` (lossless embedded images, animations normalised to the editor importer's track set and key optimisation, meshes keeping a `<glb>::<id>` resource path) and a PNG becomes an `ImageTexture` with alpha-edge repair, both cached by the resource loader. A file that has a sidecar still uses the editor import. Per file, the node tree, transforms, metadata, meshes, surface materials, textures, skeletons and animation tracks match the editor import for all 1,165 GLBs. Web packs include the raw bytes. JSON manifests remain readable through `FileAccess`. The small UI, HUD, player and effect assets (`assets/menu`, `hud`, `player`, `fades`, `effects`, `weather`, `achievements`) remain editor-imported resources.

The `cinematics` group's opening-effects export also writes each texture bank's `overlay.png` and the original step 9/10 screen vertices into `assets/opening/effects/manifest.json`. These outputs use the same import presets and overwrite policy as the other opening textures.

Assets that were extracted before these presets existed, or imported by the editor with default settings, are retrofitted without the disc: `python tools/assets.py --import-sidecars` writes missing `.import` presets for the editor-imported folders and the `.gdignore` markers (library, audio, `extracted`, `converted` and the bulk game folders above) and exits; `--prune-sidecars` with it deletes the now useless `.import` files of GLB/PNG assets under the bulk game folders (the cache entries in `.godot/imported` can then be deleted); it needs neither the CUE nor the Python dependencies. Existing sidecars follow the normal overwrite policy, so `--import-sidecars --overwrite-only "assets/**/*.import"` patches the controlled settings of editor-written ones (their cache paths stay; the editor reimports only those). `assets/achievements` is tracked and untouched. PNGs next to a GLB named `<glb>_<n>.png` were extracted by older default GLB import settings; they are no longer produced and can be deleted to avoid importing them.

With the bulk game folders ignored a cleared `.godot` imports in about 12 s (660 cached files) instead of about 73 s (3,372 files) for the same tree with sidecars; the game itself parses the GLBs when they are first needed. Earlier measurements on the same machine with a cleared `.godot`: default import of a fresh extraction 255 s, with the presets 90 s (GLB scenes about 55 s of that); an already imported tree with stale editor sidecars and extracted PNGs went from 281 s to 210 s.

## Subsets

`--only GROUP` (repeatable) limits the run to the named groups; `--stage STxx` (repeatable, `ST00`-`STFF`) limits stage-bound work to those stages.

| Group | Contents |
| --- | --- |
| `world` | stage geometry, collision, routes, props, NPCs and scripted actors, lighting, depth cue, weather, minimaps (HUD bitmap/tile maps and the Flutter deck map), room layouts, shops, location names, roofs, Roll's development tables, plus every stage-bound scene and mission: fire mission (ST1E), flight (ST3A), landing and Joseph's workshop (ST08), dropship (ST49), Flutter (ST04, ST01 travel, ST10 craft), Yosyonke (ST09), Joseph's room (ST47), mine quest, scenes and effects (ST0D, ST0F), church (ST0B) |
| `models` | player and its variants, player outfit meshes (helmet/shoes sets), special weapon 0F, special weapons 05 (Hyper Shell), 06 (Homing Missile) and 0E (Spread Buster), effects captured by running the original code and the SLES record renderer in Unicorn with an emulated GTE, player effects, special-mode table, weapon stat tables, mine and Icefield enemy effects, every actor model archive on the disc |
| `textures` | texture upload library |
| `ui` | HUD, projectiles, title menu, fonts (including the title font), status menu, dialogue text banks, mission banner, game over, screen fades |
| `audio` | sound effects, music, zone and stage audio, game-over music, scene audio |
| `cinematics` | opening scene and effects, ST39 Game Start scene, player scene clips |
| `media` | raw XA voices and music, opening/intro audio, STR movies (needs the CUE) |

`assets/levels/ST01/flutter_travel.json` (task `flutter_travel`) also carries `arrival_rules` (the ST01T destination callbacks run on the original code by `cinematics.flutter_arrival_rules`: per list position and scenario list, whether choosing the destination advances the story byte, rewrites the stage request or sets flags) and, per dock, `landing_scene` (the scene the island starts with its Flutter hull, found by `world.flutter_landing_scene`). Regenerate it alone with `python tools/assets.py --only world --stage ST01 --overwrite-only assets/levels/ST01/flutter_travel.json`.

Examples:

```
python tools/assets.py --only ui                       # menus, HUD, fonts, dialogue
python tools/assets.py --stage ST10                    # everything stage-bound that touches ST10
python tools/assets.py --only world --stage ST0F       # the mine only
python tools/assets.py --only audio --only media "disc.cue"
```

A full run orders its tasks by dependency (verified from a clone holding only the PAL disc image: 180 tasks, no failures, a second run rewrites nothing, and the editor imports the result in about 75 s). With `--stage` or `--only`, tasks that consume other exports (room layouts need every stage's `doors.json`; Flutter travel needs the ST10, ST24 and ST01 models; landing, Yosyonke, Joseph and mine-quest scenes need `doors.json` and the ST08 audio) read earlier output, so run the dependency first or run without `--stage`.

XA voices retain each native descriptor ID, archive, range, channel and source hash while identical archive/range/channel keys reference one Ogg Vorbis file. The SLES archive table at `0x800695F4` contains 24 slots, ending at the common descriptor table `0x80069624`; stage enumeration stops when the next record has no matching native XA audio sectors. Each stage's two descriptor tables (`id & 0x8000` selects the `0x80078DD4` table, otherwise `0x80078DD8`) are located by the `sw` of the table pointer to `0x8DD4`/`0x8DD8` in the stage overlay, with the pointer built by `lui`/`addiu` into whichever register that `sw` stores. Overlapping descriptors decode with separate predictor histories. New voices use `assets/audio/voices/xa_<key>.ogg`; verified existing files can remain at their current paths. Entries carry `file_sha256` (the written `.ogg`) and `pcm_sha256` (the decoded native PCM it was encoded from). Each entry declares its `voice-<key>` asset group so stage and opening loaders mount the corresponding PCK before playback.

Dialogue opcode `0x1A` follows SLES `0x8004D11C`: request playback through `0x8001B9A4`, then wait for `0x8001AF94` readiness before advancing the command or accepting page input. SPU effects, reverb and scores reuse verified canonical resources before exporting; default reruns preserve existing Ogg files and manifests. Duplicate pruning removes only outputs created during the run or explicitly selected for overwrite, and follows the same policy.

Dialogue opcodes `0x12` (open a bank message in another window, SLES `0x8004CD68`), `0x41` (three-way redirect on byte `0x8009C82D`, SLES `0x8004E950`), `0x2E` (signed pen advance) and `0x3D` (item name from the message context) are decoded; Roll's bridge menu (ST04 messages 71, 72 and 75) needs them, so a tree extracted earlier refreshes with `--only ui --overwrite-only "assets/dialogue/ST04.json"`. `assets/development` holds the ST04T development scene's 74-message bank, the 26 recipe records and the per-weapon improvement costs and caps (`world.py`, `export_development`).

## Audio encoding

Every sound the tools write to `assets/` (effects, reverb renders, FluidSynth scores, XA voices, opening and scene audio, the `assets/library/audio` bank samples) is encoded with FFmpeg `libvorbis` at `-q:a 5` from the exact 16-bit PCM the exporter produced, keeping the native channel count and sample rate (44100 Hz effects and scores, 37800/18900 Hz XA). The encoder runs with bit-exact flags and no metadata, so identical PCM gives identical bytes and duplicate pruning still works. Manifests keep `pcm_sha256` of the lossless source PCM, `file_sha256` of the `.ogg` where the entry has one, and the original `frames`/`sample_rate`; the Ogg granule position is the exact frame count. Intermediate WAVs (SoundFont samples) stay in `build/audio` only.

Scores loop over their whole render: music entries carry `looped`, `loop_begin_frame` (0) and `loop_end_frame` (equal to `frames`, the end of the file, so nothing is trimmed). `scripts/audio/game_audio.gd` applies them with `AudioStreamOggVorbis.loop` and `loop_offset = loop_begin_frame / sample_rate`. SPU loop flags inside single tones (`loop_start_frame`) are only provenance: effects are rendered as finite sounds and were never looped at runtime. Short effects start immediately (Vorbis has no encoder delay in the stream) and nothing needs sample-exact WAV timing, so no sound is kept as WAV.

`python tools/assets.py --convert-audio` retrofits a tree extracted before this change, without the disc: each `.wav` under `assets/` is encoded to a `.ogg` beside it (existing `.ogg` files follow the overwrite policy and are kept, then verified), the stream header must match the WAV exactly (channels, rate, frames) and an FFmpeg decode must match its length (within one Vorbis block) and RMS, the manifests are rewritten in place (same JSON layout and line endings; `.wav` paths become `.ogg`, `wav_sha256` becomes `file_sha256`, `pcm_sha256` and the music loop fields are added) and only then are the verified `.wav` files deleted. A file that fails verification keeps its `.wav` and manifest path and the command exits non-zero. Reruns are safe and resume where they stopped.

## Overwrite policy

By default the tools never replace a file that already exists: a new file is written, an existing one is left alone and counted. The run ends with `Kept N existing files; ...`; add `--verbose` to list each kept path.

| Flag | Effect |
| --- | --- |
| `--overwrite` | replace every existing output file |
| `--overwrite-only PATTERN` | replace only existing files matching the glob (repeatable) |
| `--verbose` | print each kept file |

`PATTERN` is relative to the repository root and uses forward slashes. `*` matches within one path segment, `**` crosses folders, and a pattern that names a folder covers everything inside it.

```
python tools/assets.py --only ui --overwrite-only "assets/dialogue/*"
python tools/assets.py --stage ST10 --overwrite-only "assets/levels/ST10/**"
python tools/assets.py --overwrite-only "assets/levels/*/doors.json" --overwrite-only "assets/audio/**"
python tools/assets.py "disc.cue" --overwrite
```

Rules:

- Flags only decide about files that existed before the run. A file the run itself created or already rewrote can be patched again later in the same run, which several exporters rely on.
- `build/` is a disposable cache (normalised archives, map sections, decoded audio, FluidSynth, pip packages, the coverage report) and is always rewritten, except for the extracted disc files in `build/disc-assets`. Those follow the same rules: an existing file identical to the disc is reused; a different one stops the run unless `--overwrite` (or a matching `--overwrite-only`) allows replacing it.
- `tools/location_names.json` is an output too (the area names `tools/world.py` reads) and is kept unless overwritten like any other file.
- `python tools/world.py room-layout [--overwrite]` regenerates the Flutter room layout. Ladder pairs between Flutter decks (ST04 area 1 / ST06 area 0 / ST07 area 0) stack their rooms: the lower room's ceiling hatch (its `area_roofs.json` black-out height) meets the bottom of the upper room's ladder pit, with both ladder foot points (each route's source transform) on one vertical line. Each `ladder_transitions` entry records `seamless`, `delta`, `upper`/`lower`, `hatch_height` and `pit_depth`; the runtime streams the destination room and climbs through without a fade. Ladders without a hatch height or pit (the mine ladders) keep `seamless: false` and fade.
- Town groups use the same exporter through `assets.py`, one task per entry of `world.TOWN_LAYOUTS` (`<name>_room_layout.json`; each entry maps a stage to its joined areas, `None` for all): `town` (Yosyonke: ST09 with ST0A, ST0C, ST47 area 0), `ruminoa` (ST19 area 1, ST1A, ST1B areas 0-3), `pokte` (ST25 areas 0-4), `pokte_mayor` (ST24 areas 1-2 and the mayor's home ST32), `kito` (ST20), `kimotoma` (ST29, ST2A, ST2B, ST2C, ST3B, ST3C), `sulphur` (ST3D, ST3E areas 0-5, ST3F) and `glyde` (outdoor ST1F with ST30 areas 0-2 and ST31 area 0; its sliding doors join the layout like hinged ones), plus the ruin and cavern groups `manda` (ST12-ST14), `saul_kada` (ST26, ST27, ST28, ST33, ST34), `calinca_ruins` (ST2D-ST2F), `nino_ruins` (ST35-ST38), `defense` (ST41, ST42), `mother_zone` (ST43-ST45, ST4C, ST58), `guild_ruins` (ST4D), `pokte_caverns` (ST4E, ST51), `kito_caverns` (ST4F), `kimotoma_caverns` (ST50) and `license_test` (ST55). Mine lift pads (`mine_lifts.json` positions), style-None routes and routes without a reciprocal door stay external; style-None routes are zone triggers or story-state duplicates (ST3D area 0 and ST3E area 0 are the same room) with no door panel to align on, so they play as fades. Elysium (ST40) has only such routes and gets no layout; the tutorial ST4A is scripted lesson by lesson and stays unstreamed. `TOWN_EXTERIORS` marks the outdoor rooms. Non-hinged routes stay external and fade; a door pair is matched to its reciprocal by arrival point, and a door whose placement would contradict the rooms already placed (it closes a loop) is exported to `external_routes` with `reason: "closes a loop"` and plays as a fade door inside the stream (`room_stream.is_fade_route`). Refresh the layouts in about a second with `python tools/assets.py --task "*_room_layout" --overwrite-only "assets/locations/*_room_layout.json"` (`--task NAME` takes a glob of task names, repeatable, skips the per-stage geometry and model passes and reads earlier output).
- Existing Godot `.import` files are kept by default.

## Where the output goes

| Path | Contents |
| --- | --- |
| `build/disc-assets/` | the ISO file tree (`COMMON`, `DAT`, `SLES_035.56`, ...) |
| `build/asset_coverage.json` | per-file hashes and per-task results |
| `assets/levels/STxx/` | geometry, collision, doors, NPCs, scene and callback JSON, per-stage models and audio |
| `assets/library/` | every model archive, texture upload, sound bank/sequence, voice archive and player on the disc (marked `.gdignore`) |
| `assets/audio/`, `assets/opening/`, `assets/video/` | sound effects and music, opening scene data, movies |
| `assets/hud/`, `assets/menu/`, `assets/dialogue/`, `assets/fades/`, `assets/effects/` | interface art, fonts, text banks, fades |
| `assets/player/`, `assets/stage_props/`, `assets/minimap/`, `assets/locations/`, `assets/weather/`, `assets/shops/`, `assets/development/` | player, props, minimaps, room layouts, weather, shop catalogues, development messages and tables |

## Open it in Redot

Open the folder with Redot 26.2 once extraction has finished. The first open imports the generated assets and takes a while. Run `scenes/main.tscn`. Folders full of bulk exports (`assets/library`, `assets/levels`, `assets/stage_props`, `assets/opening`, `assets/flutter`, `assets/minimap`) carry a `.gdignore` so the editor does not import them; the game loads them at runtime.

If you open the project before extracting, extract and reopen (or use Project > Reload Current Project).

## Web export

`python tools/export_web.py --engine "path/to/redot-editor" [--output bin/web] [--chunk-mib 4]` packs the generated assets into chunked `.pck` files and runs the editor's Web export. It needs the Web export templates installed in that editor and the assets extracted. `python tools/asset_server.py` is a local upload endpoint for the mesh viewer in `build/mml2-mesh-viewer`; it always replaces the uploaded file.

## Actor coverage audit

`world.export_actor_coverage` (run by `python tools/assets.py --only world`, skipped with `--stage`) scans every stage overlay's standard 20-byte actor list and writes `docs/actor_coverage.md` and `docs/actor_coverage.json`: per stage and record class (`type/class/variant`) how many original records exist, how many are exported (static props, NPCs, scripted actors, pickups, doors, weather), which capabilities the exports carry (talk, movement, enemy, follower, kickable, lock-on), callback addresses and whether the stage has a scripted-actor export. Both files are regenerated only with `--overwrite` or `--overwrite-only "docs/actor_coverage.*"`.

Regular dungeon enemies are listed in `world.DUNGEON_ENEMIES` (stage, class) -> GDScript port; `export_props` then adds `source_attributes`, `native_enemy.script` and the transform to those stage-prop instances and `export_dungeon_effects` writes `assets/levels/<stage>/effect_burst.png` and `effect_projectile.png`. The model resource key per class is read from its constructor (`actor_resource_keys`), which resolves classes whose key is not `actor+6` (ST41/42 class 97 uses `actor+7`). ST41/42 class 97 is the grabber trap (`native_dungeon_grabber.gd`); it has no attribute table, so its entry carries `source_attributes: []` and no `export_dungeon_effects` run. Refresh with `python tools/assets.py --only world --stage ST41 --stage ST42 --overwrite-only "assets/stage_props/manifest.json"` (the task swallows exporter errors, check the manifest role `dungeon_enemy`).

Dungeon chests (type 0x20, class 21) share one callback across 20+ overlays; `world.chest_profile` finds it by its prologue, reads the stage's chest table, and `export_props` adds `native_chest` (collected flag, message, reward word) plus the interaction descriptor to those instances in `assets/stage_props/manifest.json`. `NativeProps` attaches the same chest controller the mine uses.

## Town NPC movement, terminals and proximity messages

`models.bind_town_movement` runs at the end of `export_interior_scripted_actors` and `export_friendly_npcs`. It locates the stage's class-0 NPC machine from `INTERIOR_SCRIPT_BINDINGS`/`NPC_STAGE_BINDINGS` (`callback` -> state table -> substate table -> walk step table) and checks that the walk/idle/talk handlers (substates 0-3, from the first substate to the last) hash to `TOWN_NPC_CODE_HASH` after masking overlay addresses; every stage with a class-0 callback carries the identical code except ST18 (different hash, skipped) and ST2B (no walk table). It then reads the stage's route table (the pointer the overlay init stores in GAME global 0x80078D30; 8-byte nodes `links[4] int8, x int16, z int16`), the walk/run velocity and turn rows (`actor+0x3C/0x4A` setup, table indexed by record byte 6), the 16 idle timers and the 4 gesture patterns, and writes them as `native_town_npc` in `scripted_actors.json` (or `npcs.json`) plus a `native_movement` of kind `town_npc` on each class-0 instance: record byte 8 is the route index (instances with an index outside the stage's routes are left static), byte 9 bit 7 marks a stationary NPC, bit 4 lets it pause at nodes, bits 0-2 are the mode (0-3 walk, 4-7 run, stationary mode 1 plays the gesture patterns). `scripts/world/actors/native_town_npc.gd` runs the walk step table at 25 Hz: step 0/1 turn toward and walk to the node (arrival window 128 raw), a random draw of `0x550000AA << (rng & 31)` pauses 25% of the arrivals at nodes with bit 4 (step 4, timer from the idle table, then the NPC waits while the player is within 384 raw and 640 yaw units in front), step 2 picks the next node with the shared `((state<<1)+(state>>31)+1)^0x873CA9E5` generator, step 3 spins in place of a blocked step until the move is free. Head tracking (the look bytes at `actor+0x14C+4..7`) is not ported. Refresh with `python tools/assets.py --only world --stage ST09 --overwrite-only "assets/levels/ST09/scripted_actors.json"`.

`world.NATIVE_SCRIPTED_INTERACTIONS` gained ST29 (class 1), ST32 (classes 88, 95, 130) and ST4A (class 0); ST32 and ST4A register their NPCs one record at a time through GAME 0x800C08BC, which `INTERIOR_SCRIPT_BINDINGS[...]["registration_function"]` lets the Unicorn path enumerator observe. `world.bind_proximity_messages` exports the one-shot proximity messages of ST2B and ST3B (`native_proximity_message`, `native_proximity_message.gd`). `world.actor_controller_callbacks` adds the 0xE0 controller callbacks (and the E0/27 spawn routines) to the audit.

`world.export_gravity_gates` (task `gravity_gates`, ST41 and ST42) checks the E0/37 callback by code hash and writes `assets/levels/<stage>/gravity_gates.json` (record position, line angle, radius, the cleared/set event flags and the sound read from the code). `world.export_props` resolves type-0x60 resource variants through `prop_resource_variant` (the constructor's key table, indexed by the record variant, or key 0) and, for class 31 state 0 (`ice_block_profile`, hash-checked), adds `native_ice_block` to the instances and a stage-level profile (key tables, hitboxes, timers, sounds, piece models) to the props manifest; the ice pieces' models are exported with the stage props. `world.export_area_controllers` (task `area_controllers`, ST14, ST28, ST2D/2E/2F, ST48, ST5B) hash-checks the E0/19, E0/30, E0/25 and E0/35 callbacks and writes `area_controllers.json` (records with position and argument bytes, the flame vent points for ST28, the ice-floor rule for ST2D/2E/2F). `world.export_vram_animations` (task `vram_animations`, ST00/1F/20/22/23/48/4C/5B) runs the E0/5 and E0/26 callbacks in Unicorn (needs `unicorn`), records the VRAM copy packets per tick and writes `vram_animations.json` and `vram_area_NN.bin` per area. `world.export_quiz` (task `quiz`, ST32) writes `assets/levels/ST32/quiz.json`: the 212 embedded questions decoded through `ui.native_text_messages`, the question rows per quiz kind, the answer table, the prompt window map and the teacher prize flags.

`world.export_dungeon_lifts` (task `dungeon_lifts`, after the mine scenes and the stage props) writes `assets/levels/<stage>/mine_lifts.json`, the schema of ST0F's file, for every dungeon whose overlay holds the ST0F lift code: the pad callback and the setup, run, finish and ride scene callbacks hash-identically (`LIFT_CODE`, after masking overlay addresses) in ST12, ST13, ST14, ST26, ST2D, ST2E, ST2F, ST35-ST38, ST3C, ST40-ST45, ST4C-ST4F, ST50, ST51, ST56 and ST58. The pad hitbox and the four yaw target descriptors are read from the stage's pad constants (equal to ST0F's), the ride profile is ST0F's, and each type-0x60 class 25 record becomes a lift (record byte 8 question message, byte 9 direction, byte 10 lock flag offset, byte 11 locked message) paired with the route of the same area and contact position. It reads `assets/levels/ST0F/mine_lifts.json` and `assets/stage_props/manifest.json`. `native_mine_lift.gd` loads the profile per stage and `native_props.gd` attaches it to the class 25 props outside ST0F.

## Original-code runner

`models` also recompiles the original MIPS code into GDScript: `python tools/models.py runner [--stage STxx]... [--overwrite|--overwrite-only GLOB] [--output DIR] [--trace]` writes `assets/runner` (git-ignored): `engine.gd` (SLES and GAME functions reachable from the stage overlays, shared by every stage), `STxx.gd` (the overlay functions), the overlay image, the decompressed root and model archive at the loader's banks, `ram.bin` (SLES and GAME at their load addresses), `PL00P000.sN.bin` and `PL00Rxx.sN.bin` (the sections of the player and special-weapon files at their load addresses) with one translated unit per weapon module, `STxx.vram.bin` (video memory image after the common player, overlay and root texture uploads, sampled by the effect packets) and `manifest.json`. `tools/assets.py` runs it with the `models` group for the stages in `models.RUNNER_STAGES` (the boss gauge stages and ST1C, the post-boss scene stage); the model archive section of each stage is the first type-0x0C section after the root. Stages with an `attach` rule in `RUNNER_STAGES` are run beside the port by `scripts/runner/runner_host.gd` (currently ST1D, story byte 1, areas 1 and 2, ST1C, which plays scene 0x13 and hands over to ST3E, ST24 and ST25 (Manda scenes 0x14, 0x1B, 0x1C and the Jagd Krabbe fight), ST3E (Sulphur-Bottom scenes) and ST46 (Nino approach scene 0x31), besides the dungeon stages). The hand-written services live in `scripts/runner/hle.gd` and `hle_bios.gd`; every `h_XXXXXXXX` method replaces the original function at that address when the units are generated, so the export has to be repeated after adding one. The attach rule may carry `min_story` (`models.RUNNER_MIN_STORY`; ST39 from story byte 1) so a stage's earlier story keeps the port's scene contract.

Two developer tools drive the units in a throw-away project under `build/` (they never start the game's autoloads); both need `--engine` (the Redot editor executable, always launched headless with the dummy audio driver):

- `python tools/models.py runner-pilot --engine EXE [--stage ST1D]` plays Forbidden Island scene 0x28, the class-52 boss fight with scripted hits and scene 0x29 through `scripts/runner/runner_probe.gd` and prints events, frame times, messages, transitions, unresolved targets and the final stage request.
- `python tools/models.py runner-verify --engine EXE [--stage ST1D] [--cases N] [--seed N]` runs every translated function whose call tree has no indirect calls on random registers and RAM in Unicorn and in the engine through `scripts/runner/runner_verify.gd` and compares registers, RAM and scratchpad digests; it also replays a boss-fight effect render (RAM, scratchpad, GTE registers) in NativeMachine and requires the ordering-table packets and every GTE operation to match; it also compares the GTE (RTPS, RTPT, MVMVA, NCLIP, OP, SQR, AVSZ3/4, GPF, GPL) with the Python GTE (MAC0, IR0 and the screen coordinates within the reciprocal table's rounding). Exit status 1 on any difference.

## Module map

| Module | Owns |
| --- | --- |
| `tools/assets.py` | the CLI and the order of every export |
| `tools/disc.py` | CUE/ISO reading, XA sector access, section decompression, movies, the output policy (`write_output`) and dependency bootstrap |
| `tools/world.py` | maps, terrain, lighting, minimaps, collision, routes, props, shops, Roll's development tables, location names, roofs, Flutter travel, mine quest |
| `tools/models.py` | models, skeletons, animations, actors, NPCs, doors, special weapons, player and mine effects, the original-code runner (recompiler, pilot and verification commands) |
| `tools/ui.py` | HUD, menus, fonts, dialogue, banners, game over, fades |
| `tools/audio.py` | sound banks, effects, music, XA voices |
| `tools/cinematics.py` | native cutscene exporters: opening, Game Start, fire mission, flight, landing, Flutter, Yosyonke, Joseph's room/workshop, mine scenes, church, player scene clips |
| `tools/export_web.py`, `tools/asset_server.py` | packaging and serving, not extraction |

## Troubleshooting

- `Extraction has unresolved errors; inspect the coverage report.` Open `build/asset_coverage.json` and look for `"status": "unsupported"`; the `error` field is the exception text.
- `FFmpeg is required ...` FFmpeg is not on `PATH` in the shell that runs the tool.
- `The native FluidSynth shared library is required ...` (Linux/macOS) install FluidSynth so `libfluidsynth` is found by the loader. On Windows delete `build/audio/fluidsynth` and rerun to repeat the download.
- `cached file differs from the selected disc` `build/disc-assets` came from another disc image. Rerun with `--overwrite`, or delete the folder.
- `pip` errors when installing `unicorn` or `capstone`: install them yourself with `pip install --target build/pydeps unicorn==2.1.4 capstone==5.0.9`.
- A refreshed export still shows old data: the file was kept. Use `--overwrite-only` with a path pattern, or `--overwrite`.
- Only `Full media extraction requires the original CUE.` failed: you ran without a CUE; pass the CUE or restrict `--only`.

The ST11 `scripted_actors.json` also carries `native_encounter` (Icefield mini-boss record `0x800F3278`, class 59, its model `ST11_model_09.glb`, scene trigger, arrival, music cue, radio message, barrier collision boxes and defeat actions), produced by `models.bind_icefield_encounter`; `icefield_effects.json` gains `death.boss`. Regenerate with `python tools/assets.py --only world --stage ST11 --overwrite-only "assets/levels/ST11/scripted_actors.json"`.
`models.export_arena_barriers` (run by `assets.py` for ST1D) writes `assets/levels/ST1D/arena_barrier.json` and `arena_barrier.png`: the two class 0x28 barrier records of ST1D (`0x800FC388`, `0x800FD048`), the collision variant-1 boxes of their tiles (GAME `0x800C010C`) and the shimmer profile shared with ST11 (draw constants checked equal). Regenerate with `python tools/assets.py --only world --stage ST1D --overwrite-only "assets/levels/ST1D/arena_barrier*"`.

The ST10 ice domes (class 29, area 1, story byte14 1; resource variant 0 is the translucent dome, variants 1-4 the curled figures) combine three exports: `models.SCRIPT_FLOOR_SNAP` stores `native_floor_snap.floor_raw`, the floor query result including the variant-1 collision that the dome record selects with `GAME 0x800C010C` (`models.script_snap_floor` reads it from `world.export_floor_shapes`), so the runtime places the actor at `floor_raw + 0x90` without a physics ray; `models.SCRIPT_TRANSLUCENCY` stores `native_translucency` (`SLES 0x8003F28C` semi-transparency, mode 0) that `native_material.translucent` applies; `world.AREA_COLLISION_VARIANTS[("ST10", 1)]` adds the four dome collision variants to `manifest.json` and their examine contacts (message 0 of the ST10 bank) to `doors.json`. Regenerate with `python tools/assets.py --only world --only models --stage ST10 --overwrite-only "assets/levels/ST10/scripted_actors.json" --overwrite-only "assets/levels/ST10/manifest.json" --overwrite-only "assets/levels/ST10/doors.json"`.

`cinematics.export_icefield_scene` (world group, ST11) emulates ST11 scene 0x2A with the same Unicorn harness as the other scenes and writes `scene_2a.json`, `scene_2a_callbacks.json`, `player_scene.json` and `player_scene_ST11.glb`.

`ui` also exports the item icon sheet (`assets/menu/item_icons.png`, with `status.json` `item_icons`; part of the `menu` task) and the slot machine reel symbols (`assets/menu/slot_symbols.png`, task `slot_symbols`, read from the exported `assets/levels/ST1A/area_00.glb`); regenerate with `--overwrite-only 'assets/menu/*'`.
