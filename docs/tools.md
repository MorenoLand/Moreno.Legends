# Asset extraction tools

The repository ships no game data. `tools/assets.py` rebuilds every runtime asset from your own copy of the PAL disc (SLES-03556); everything it writes is ignored by Git.

## Requirements

| Need | Used for | Notes |
| --- | --- | --- |
| Python 3.13 or newer | all tools | developed on 3.14, checked on 3.13; the standard library plus `pip` is enough |
| `unicorn` 2.1.4 | emulating the original MIPS code (scenes, menus, HUD, door/cutscene scripts) | installed automatically into `build/pydeps` on first run (needs `pip` and network) |
| `capstone` 5.0.9 | the `special_modes` export only | installed automatically into `build/pydeps` on first use |
| FFmpeg on `PATH` | decoding PS1 ADPCM samples, transcoding STR movies (`libtheora`, `libvorbis`) | `ffmpeg` must be runnable from the shell that starts the tool |
| FluidSynth | rendering the original scores to WAV | Windows: the v2.6.1 release is downloaded from GitHub into `build/audio` on first use. Linux/macOS: install the FluidSynth shared library (`libfluidsynth`) with your package manager |
| Redot 26.2 | opening the project and running the game | [Redot releases](https://github.com/Redot-Engine/redot-engine/releases) |

Disk: about 4 GB of generated assets in `assets/`, about 100 MB of extracted disc files in `build/disc-assets`, plus working caches elsewhere in `build/`.

## The disc image

Dump your own copy of the European (PAL) release of Mega Man Legends 2, serial SLES-03556, as a BIN/CUE pair. Track 1 must be `MODE2/2352`; the CUE file and the BIN it names must sit in the same folder. The tools never modify the image and nothing from it is committed.

## Extract everything

```
python tools/assets.py "path/to/Mega Man Legends 2.cue"
```

This one command

1. copies every ISO file into `build/disc-assets` (a file already there is verified against the disc and reused),
2. exports every group listed below into `assets/`,
3. writes `build/asset_coverage.json` (source file hashes, what was exported, what failed).

The exit status is nonzero if any export failed; the report names the failing task. After it finishes, open the project in Redot (see below).

Already extracted? `python tools/assets.py` (no CUE) reuses `build/disc-assets`. The `media` group needs the raw disc sectors, so without a CUE that group is reported as `requires_disc` and the exit status is 1; add `--only` for the other groups to avoid that, for example `python tools/assets.py --only world --only models --only textures --only ui --only audio --only cinematics`.

`python tools/assets.py --help` prints every option and the group list.

## Subsets

`--only GROUP` (repeatable) limits the run to the named groups; `--stage STxx` (repeatable, `ST00`-`STFF`) limits stage-bound work to those stages.

| Group | Contents |
| --- | --- |
| `world` | stage geometry, collision, routes, props, NPCs and scripted actors, lighting, depth cue, weather, minimaps, room layouts, shops, location names, roofs, plus every stage-bound scene and mission: fire mission (ST1E), flight (ST3A), landing and Joseph's workshop (ST08), dropship (ST49), Flutter (ST04, ST01 travel, ST10 craft), Yosyonke (ST09), Joseph's room (ST47), mine quest, scenes and effects (ST0D, ST0F), church (ST0B) |
| `models` | player and its variants, special weapon 0F, player effects, special-mode table, mine effects, every actor model archive on the disc |
| `textures` | texture upload library |
| `ui` | HUD, projectiles, title menu, fonts (including the title font), status menu, dialogue text banks, mission banner, game over, screen fades |
| `audio` | sound effects, music, zone and stage audio, game-over music, scene audio |
| `cinematics` | opening scene and effects, ST39 Game Start scene, player scene clips |
| `media` | raw XA voices and music, opening/intro audio, STR movies (needs the CUE) |

Examples:

```
python tools/assets.py --only ui                       # menus, HUD, fonts, dialogue
python tools/assets.py --stage ST10                    # everything stage-bound that touches ST10
python tools/assets.py --only world --stage ST0F       # the mine only
python tools/assets.py --only audio --only media "disc.cue"
```

Some tasks depend on others (room layouts need every stage's `doors.json`; Flutter travel needs the ST10 and ST01 models). Run the dependency first or run without `--stage`.

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
- Godot `.import` files are never touched, except that regenerated sound-effect WAVs get `compress/mode=0` written into an existing sidecar.

## Where the output goes

| Path | Contents |
| --- | --- |
| `build/disc-assets/` | the ISO file tree (`COMMON`, `DAT`, `SLES_035.56`, ...) |
| `build/asset_coverage.json` | per-file hashes and per-task results |
| `assets/levels/STxx/` | geometry, collision, doors, NPCs, scene and callback JSON, per-stage models and audio |
| `assets/library/` | every model archive, texture upload, sound bank/sequence, voice archive and player on the disc (marked `.gdignore`) |
| `assets/audio/`, `assets/opening/`, `assets/video/` | sound effects and music, opening scene data, movies |
| `assets/hud/`, `assets/menu/`, `assets/dialogue/`, `assets/fades/`, `assets/effects/` | interface art, fonts, text banks, fades |
| `assets/player/`, `assets/stage_props/`, `assets/minimap/`, `assets/locations/`, `assets/weather/`, `assets/shops/` | player, props, minimaps, room layouts, weather, shop catalogues |

## Open it in Redot

Open the folder with Redot 26.2 once extraction has finished. The first open imports the generated assets and takes a while. Run `scenes/main.tscn`. Folders full of bulk exports (`assets/library`, per-stage `models`) carry a `.gdignore` so the editor does not import them.

If you open the project before extracting, extract and reopen (or use Project > Reload Current Project).

## Web export

`python tools/export_web.py --engine "path/to/redot-editor" [--output bin/web] [--chunk-mib 4]` packs the generated assets into chunked `.pck` files and runs the editor's Web export. It needs the Web export templates installed in that editor and the assets extracted. `python tools/asset_server.py` is a local upload endpoint for the mesh viewer in `build/mml2-mesh-viewer`; it always replaces the uploaded file.

## Module map

| Module | Owns |
| --- | --- |
| `tools/assets.py` | the CLI and the order of every export |
| `tools/disc.py` | CUE/ISO reading, XA sector access, section decompression, movies, the output policy (`write_output`) and dependency bootstrap |
| `tools/world.py` | maps, terrain, lighting, minimaps, collision, routes, props, shops, location names, roofs, Flutter travel, mine quest |
| `tools/models.py` | models, skeletons, animations, actors, NPCs, doors, special weapons, player and mine effects |
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
