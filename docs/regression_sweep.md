# Regression sweep

Headless real-path sweep: `main_menu._start_session(stage, area, ctx)` per stage/area/story byte14, 300 physics frames (150 idle, then walking forward, then forward/strafe/turn) at time scale 3 with the dummy renderer and audio. 2732 runs over 92 stages / 454 areas; byte14 0-3 on every area, plus 5, 8, 12, 16, 20 on the 40 stages whose scripted actors depend on byte14. 2678 runs raised nothing beyond blind-walk falls.

Flags: NOLOAD session failed to start; HANG load over 90 s; CRASH process died; IDLEFALL player fell out of the world while idle; WALKFALL player left the floor during the blind walk (the path is not map-aware, so this is informational); NOMESH no visible meshes; ERR script/engine error not caused by the dummy renderer; SPIKE worst frame over 150 ms at 3x scale (about 50 ms per 60 Hz step); RUNNERFAULT runner stopped on unresolved code. Engine errors from the dummy renderer (empty mesh storage in `lock_on` ImmediateMesh, `generate_triangle_mesh`, material slots) are ignored as headless artifacts.

## Totals

| Flag | Runs |
|---|---|
| WALKFALL | 563 |
| ERR | 43 |
| SPIKE | 7 |
| IDLEFALL | 4 |

## Fixed

- `native_vram_animation.gd`: the per-tick VRAM copy and CLUT repaint ran per pixel with `set_pixel`; town areas with animated textures (ST1F, ST22, ST23, ST20) cost 70 ms per 25 Hz tick and held every frame over 50 ms. Row-wise copies, a cached 15-bit to RGBA table, per-patch palettes and a single `blit_rect` per patch bring the tick to 13 ms; frame time in ST1F area 0 drops from 45 ms to 17 ms.
- `gameplay._find_spawn`: a free start (area picker, location load) now uses the arrival transform of a route into the area when one lands on floor, then the 11x11 ray grid, then a 47x47 grid, then any route arrival including those from other stages' `doors.json`. This fixes ST2D:5 (the grid picked a point that was not the room floor), ST2E:9, ST2F:4, ST2F:8, ST35:0, ST35:2, ST36:1, ST36:13, ST37:4, ST37:6 and ST37:15.

## Open

- ST4F:14 ("Area 14") is a 2 m stub with one quad and no route into it; it cannot be started without a door and is not a playable room.
- Unsupported native scenes requested by GAME.BIN: ST09 area 0 (scene 0x72), ST3C area 2 (0x5D), ST40 area 1 (0x6A). No `scene_XX.json` is exported for them; this needs the cinematics scene emulation (story flow).
- ST1D area 2 at byte14 20 hit an unresolved MIPS target (0x00000000, ra 0x800E7770) once; a rerun was clean.
- ST01 (world map) has no areas and is not startable through the area path.
- The ST08:0 679 ms first-frame spike and the ST37:4 74 ms spike came from three parallel cold-start processes and do not reproduce alone (about 32 ms).

## Distinct errors

| Areas | Message |
|---|---|
| ST35:2, ST36:13, ST37:15, ST4F:14 | ERROR: Flutter room has no clear walkable spawn / [0] _select_stream_room (res://scripts/world/core/gameplay.gd:292) |
| ST09:0 | ERROR: Unsupported native scene ST09:72 requested by GAME.BIN 0x800c0b0c / [0] _run_native_scene_requests (res://scripts/world/core/gameplay.gd:393) |
| ST3C:2 | ERROR: Unsupported native scene ST3C:5D requested by GAME.BIN 0x800c0b0c / [0] _run_native_scene_requests (res://scripts/world/core/gameplay.gd:393) |
| ST40:1 | ERROR: Unsupported native scene ST40:6A requested by GAME.BIN 0x800c0b0c / [0] _run_native_scene_requests (res://scripts/world/core/gameplay.gd:393) |

## Per stage

| Stage | Name | Areas | Runs | byte14 | Findings |
|---|---|---|---|---|---|
| ST00 | Debug area | 2 | 8 | 0,1,2,3 | WALKFALL: a1 (4 runs) |
| ST02 | Sulphur-Bottom opening | 2 | 8 | 0,1,2,3 | WALKFALL: a1,2 (8 runs) |
| ST03 | Flutter opening | 4 | 16 | 0,1,2,3 | WALKFALL: a2,3 (8 runs) |
| ST04 | Flutter | 3 | 12 | 0,1,2,3 | OK |
| ST05 | Flutter | 3 | 12 | 0,1,2,3 | OK |
| ST06 | Flutter | 6 | 24 | 0,1,2,3 | OK |
| ST07 | Flutter | 3 | 27 | 0,1,2,3,5,8,12,16,20 | OK |
| ST08 | Yosyonke City | 2 | 18 | 0,1,2,3,5,8,12,16,20 | SPIKE: a0 (1 runs); WALKFALL: a1 (9 runs) |
| ST09 | Yosyonke City | 1 | 9 | 0,1,2,3,5,8,12,16,20 | ERR: a0 (1 runs) |
| ST0A | Yosyonke City | 5 | 45 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a0,1,3,4 (30 runs) |
| ST0B | Yosyonke City | 2 | 18 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a1 (9 runs) |
| ST0C | Yosyonke City | 3 | 27 | 0,1,2,3,5,8,12,16,20 | OK |
| ST0D | Calinca Tundra | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST0E | Calinca Tundra | 3 | 12 | 0,1,2,3 | WALKFALL: a1 (4 runs) |
| ST0F | Abandoned Mine | 13 | 52 | 0,1,2,3 | WALKFALL: a5,6,9,10 (16 runs) |
| ST10 | Forbidden Island | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST11 | Forbidden Island | 1 | 9 | 0,1,2,3,5,8,12,16,20 | OK |
| ST12 | Manda Ruins | 7 | 28 | 0,1,2,3 | WALKFALL: a1,3,4,6 (16 runs) |
| ST13 | Manda Ruins | 11 | 44 | 0,1,2,3 | WALKFALL: a0,1,7,8,9,10 (24 runs) |
| ST14 | Manda Ruins | 5 | 45 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a0,1,2 (27 runs) |
| ST15 | Nino Island | 1 | 4 | 0,1,2,3 | OK |
| ST16 | Nino Island | 1 | 4 | 0,1,2,3 | OK |
| ST17 | King Glydon | 3 | 27 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a1,2 (18 runs) |
| ST18 | Nino Island | 6 | 54 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a3,4,5 (27 runs) |
| ST19 | Nino Island | 4 | 16 | 0,1,2,3 | WALKFALL: a1,2,3 (12 runs) |
| ST1A | Ruminoa City | 2 | 8 | 0,1,2,3 | WALKFALL: a0 (4 runs) |
| ST1B | Ruminoa City | 5 | 45 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a0 (9 runs) |
| ST1C | Forbidden Island / Sulphur-Bottom scenes | 6 | 24 | 0,1,2,3 | WALKFALL: a2,5 (8 runs) |
| ST1D | Forbidden Island | 3 | 27 | 0,1,2,3,5,8,12,16,20 | SPIKE: a1 (1 runs) |
| ST1E | Flutter fire | 3 | 12 | 0,1,2,3 | WALKFALL: a1 (4 runs) |
| ST1F | Glyde's Base | 2 | 18 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a1 (9 runs) |
| ST20 | Kito Village | 2 | 18 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a1 (9 runs) |
| ST21 | Calbania Plains | 1 | 4 | 0,1,2,3 | OK |
| ST22 | Calbania Plains | 1 | 7 | 0,1,2,3,5,12,20 | OK |
| ST23 | Calbania Plains | 1 | 9 | 0,1,2,3,5,8,12,16,20 | OK |
| ST24 | Pokte Plains | 3 | 27 | 0,1,2,3,5,8,12,16,20 | OK |
| ST25 | Pokte Village | 7 | 63 | 0,1,2,3,5,8,12,16,20 | SPIKE: a1,2,3,4 (5 runs); WALKFALL: a5 (9 runs) |
| ST26 | Saul Kada Ruins | 7 | 28 | 0,1,2,3 | WALKFALL: a0,1,2,3,5,6 (24 runs) |
| ST27 | Saul Kada Ruins | 9 | 36 | 0,1,2,3 | WALKFALL: a2,5 (8 runs) |
| ST28 | Saul Kada Ruins | 6 | 24 | 0,1,2,3 | WALKFALL: a1,2,4,5 (16 runs) |
| ST29 | Kimotoma City | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST2A | Kimotoma City | 5 | 20 | 0,1,2,3 | WALKFALL: a4 (4 runs) |
| ST2B | Kimotoma City | 4 | 36 | 0,1,2,3,5,8,12,16,20 | OK |
| ST2C | Kimotoma City | 1 | 9 | 0,1,2,3,5,8,12,16,20 | OK |
| ST2D | Calinca Ruins | 10 | 40 | 0,1,2,3 | IDLEFALL: a5 (4 runs); WALKFALL: a7,9 (8 runs) |
| ST2E | Calinca Ruins | 12 | 51 | 0,1,2,3,5,12,20 | WALKFALL: a3,8,9 (15 runs) |
| ST2F | Calinca Ruins | 9 | 81 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a2,3 (18 runs) |
| ST30 | Glyde's Base | 5 | 20 | 0,1,2,3 | WALKFALL: a3,4 (8 runs) |
| ST31 | Glyde's Base | 2 | 8 | 0,1,2,3 | OK |
| ST32 | Pokte Mayor's Home | 1 | 9 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a0 (9 runs) |
| ST33 | Saul Kada Ruins | 1 | 4 | 0,1,2,3 | OK |
| ST34 | Saul Kada Ruins | 6 | 24 | 0,1,2,3 | WALKFALL: a0,2,4,5 (16 runs) |
| ST35 | Nino Ruins | 6 | 54 | 0,1,2,3,5,8,12,16,20 | ERR: a2 (9 runs); WALKFALL: a1,2 (17 runs) |
| ST36 | Nino Ruins | 14 | 62 | 0,1,2,3,5,12,20 | ERR: a13 (7 runs); WALKFALL: a1,3,6,12,13 (26 runs) |
| ST37 | Nino Ruins | 16 | 73 | 0,1,2,3,5,12,20 | ERR: a15 (7 runs); WALKFALL: a4,6,11,15 (25 runs) |
| ST38 | Nino Ruins | 13 | 117 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a9 (9 runs) |
| ST39 | Flutter new-game scene | 2 | 8 | 0,1,2,3 | WALKFALL: a0 (3 runs) |
| ST3A | Sulphur-Bottom / Forbidden Island scenes | 4 | 16 | 0,1,2,3 | WALKFALL: a0,1,2 (11 runs) |
| ST3B | Kimotoma City | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST3C | Kimotoma City | 5 | 45 | 0,1,2,3,5,8,12,16,20 | ERR: a2 (1 runs) |
| ST3D | Sulphur-Bottom | 4 | 36 | 0,1,2,3,5,8,12,16,20 | OK |
| ST3E | Sulphur-Bottom | 7 | 63 | 0,1,2,3,5,8,12,16,20 | OK |
| ST3F | Sulphur-Bottom | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST40 | Elysium | 14 | 126 | 0,1,2,3,5,8,12,16,20 | ERR: a1 (9 runs) |
| ST41 | Defense Area | 15 | 60 | 0,1,2,3 | OK |
| ST42 | Defense Area | 16 | 64 | 0,1,2,3 | OK |
| ST43 | Mother Zone | 5 | 20 | 0,1,2,3 | OK |
| ST44 | Mother Zone | 5 | 20 | 0,1,2,3 | OK |
| ST45 | Mother Zone | 6 | 24 | 0,1,2,3 | OK |
| ST46 | Nino Island / Flutter scenes | 3 | 12 | 0,1,2,3 | WALKFALL: a1 (4 runs) |
| ST47 | Yosyonke City | 3 | 27 | 0,1,2,3,5,8,12,16,20 | OK |
| ST48 | Saul Kada Desert | 2 | 18 | 0,1,2,3,5,8,12,16,20 | OK |
| ST49 | Flutter / Dropship scenes | 4 | 16 | 0,1,2,3 | WALKFALL: a1,2 (8 runs) |
| ST4A | Tutorial | 7 | 63 | 0,1,2,3,5,8,12,16,20 | OK |
| ST4B | Sulphur-Bottom | 6 | 24 | 0,1,2,3 | WALKFALL: a3,4 (8 runs) |
| ST4C | Mother Zone | 5 | 45 | 0,1,2,3,5,8,12,16,20 | OK |
| ST4D | Guild Ruins | 9 | 36 | 0,1,2,3 | OK |
| ST4E | Pokte Caverns | 10 | 40 | 0,1,2,3 | OK |
| ST4F | Kito Caverns | 15 | 135 | 0,1,2,3,5,8,12,16,20 | ERR: a14 (9 runs); WALKFALL: a10,14 (16 runs) |
| ST50 | Kimotoma Caverns | 11 | 99 | 0,1,2,3,5,8,12,16,20 | WALKFALL: a3,4 (18 runs) |
| ST51 | Pokte Caverns | 3 | 27 | 0,1,2,3,5,8,12,16,20 | OK |
| ST52 | Sera / Master scenes | 5 | 20 | 0,1,2,3 | WALKFALL: a0,2 (8 runs) |
| ST53 | Calinca Tundra scenes | 3 | 12 | 0,1,2,3 | WALKFALL: a1,2 (8 runs) |
| ST54 | Rocket launch ending | 3 | 12 | 0,1,2,3 | OK |
| ST55 | License Test Ruins | 7 | 28 | 0,1,2,3 | OK |
| ST56 | Master's Room | 1 | 4 | 0,1,2,3 | OK |
| ST57 | Game credits | 1 | 4 | 0,1,2,3 | WALKFALL: a0 (4 runs) |
| ST58 | Mother Zone | 5 | 45 | 0,1,2,3,5,8,12,16,20 | OK |
| ST59 | Manda Circuit | 1 | 4 | 0,1,2,3 | WALKFALL: a0 (4 runs) |
| ST5A | Calinca Circuit | 1 | 4 | 0,1,2,3 | WALKFALL: a0 (4 runs) |
| ST5B | Saul Kada Circuit | 1 | 4 | 0,1,2,3 | OK |
| ST5C | Mother Zone | 1 | 4 | 0,1,2,3 | OK |
