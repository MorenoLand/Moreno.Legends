# New-game progression

Traced from the PAL disc (SLES-03556). Addresses are SLES, GAME (`COMMON/GAME.BIN`, load 0x800AD000) or stage overlays (`DAT/STxxT.BIN`, load 0x800E7000).

## Engine mechanisms

- Game-state block 0x8009C7E8: stage +0x10, area +0x11, scenario +0x14/+0x15, start mode +0x0D, difficulty +0x16, load-from-save +0x0C.
- SLES 0x8001392C(type, arg) only starts a screen transition (jump table 0x80010094): 0x02 subtractive reveal, 0x12 cover to black, 0x22 type-2 wipe, 0x26 circle wipe.
- Stage changes use the request block 0x80078D08: +0 type, +4 stage, +5 area, +0x10/+0x12/+0x14 position, +0x16 facing, +0x18 arrival fade, +0x19 exit fade (0xFF none). Type 2 changes stage (GAME 0x800B0420, writes at 0x800B04B8). Type -1 changes area within the stage (GAME 0x800AEC4C, write at 0x800AED6C). Both copy +0x15 to +0x14 and clear flags 0x580-0x65F (0x800C037C).
- Event flags: bitfield at 0x80098538; set 0x800C0558, clear 0x800C0584, test 0x800C05B4.
- Scenes: GAME 0x800C0B0C(id) starts scene `id` through handler table GAME 0x800DC490. Handlers call 0x800C0C5C(camera_stream, timeline). Timeline entries are 8 bytes: phase, step, s16 trigger frame (-1 = callback advances), callback address; 0xFF ends. 0x800C0D70 runs the timeline.

## Game Start

1. DEMO 0x800AD774-0x800AD7B0: stage 0x39, area 0, +0x0C/+0x0D/+0x12-+0x15 = 0, +0x16 = 1; transition 0x26.
2. GAME state 0 (0x800AE7B0): 0x800AE328 game-block defaults, 0x800C0284 clears all flags, 0x800D97B4 difficulty tables, 0x800C35B0 player initialiser (only caller 0x800AE824; struct 0x8008C0A0; HP/items from +0x16 and +0x0D).
3. GAME state 1 (0x800AE848) loads stage +0x10 (0x800BA600).

## Chain

| Step | Stage/area | Trigger | State |
| --- | --- | --- | --- |
| Intro cutscene | ST39:0 | 0x800E72D8 starts scene 5 once (latch 0x80095E08) when +0x14 = 0; camera 0x800F1BAC, timeline 0x800F1F14 | none |
| Cockpit cuts | ST39:1 / ST39:0 | timeline callbacks: step 0 frame 0x235 -> area 1 (0x800EBBC8); step 4 frame 0x25D -> area 0 (0x800EC118); step 5 frame 0x78 -> area 1 at (0x40, 0, -0xA0) (0x800EC1E0) | none |
| Hand-off | ST39 -> ST1E:0 | step 9 tick 250: transition 0x12, then request stage 0x1E area 0 at (0x300, -1, 0x300), facing 0x400, arrival fade 2 (0x800EBAE8); skipping uses transition 0x22 (0x800EB9C4) | +0x14 stays 0 |
| Fire mission | ST1E:0-2 | area handlers 0x800EF1F0 set 0x711-0x715 (Kitchen 0x681) and spawn fires (0x800C0818); timers at 0x8009C900 (+0xA 0x708, +0xC 0xE10, +0xE 0x1518); a room clears when its fire count (+4) is 0 | Kitchen clear sets 0x129 and starts scene 0xD (0x800E7A54); any timeout starts scene 0xD without 0x129 |
| Fire result | ST1E scene 0xD | sets 0x703; with 0x129 and total time < 0xD49 also sets 0x12A; success timeline 0x800F0D34, failure 0x800F0D4C | transition 0x22, request ST3A:0 (0x800EDB4C), HP refilled, 0x703 cleared |
| Flight scene | ST3A:0-3 | scene 6 when area byte 0x8009C7F9 == 0 and latch 0x8009BE08 == 0 (0x800E7574; area init 0x800E7544 clears the latch), timeline 0x800F6894 cuts between areas 0, 1 and 3 | request ST08:0 at (-0x580, -0x400, 0x10), facing 0xC00 (0x800F2C48) |
| Yosyonke, first visit | ST08:0 -> ST09:0 | ST08 door 0 (automatic contact) to ST09:0 at (0, -1, -0x1E00); ST08 door 1 (Joseph's Lab) stays locked by 0x711 (area handler 0x800E769C sets it while 0x5E1 is clear; locked message ST08 0x00 redirects to 0x01 while 0x5C1 is clear). ST09 area init 0x800E73C8 clears 0x710/0x711; area handler 0x800E7480 (byte14 0) sets 0x711 (door to ST0A:4 locked), spawns nothing and starts no scene while 0x5C1 is clear | player free |
| Junk shop | ST0A:0 | area handler 0x800E7578: 0x5C1 clear -> scene 0x4D (handler 0x800E7A1C, messages 0xC8..0xD7, step 1 sets 0x680), flag 0x5C1, state 2; otherwise spawns the vendor 0x800EF554 and plays 0x16 (SLES0x800201B0) | finish registers vendor 0x800EF878; no stage request |
| Back in Yosyonke | ST09:0 | handler 0x800E7480 with 0x5C1 set: townsfolk 0x800F2354 x2, then 0x5C2 clear -> scene 0x4E (handler 0x800E7884: walker 0x800F2574, player head turns, 150 ticks), flag 0x5C2, 0x711 | player free |
| Roll at the pad | ST08:0 | NPC callback 0x800EE95C: 0x5C1 set and 0x5E1 clear -> Roll 0x800F5298 (idle control 0 after the constructor tick); talk message 0x28 (sets 0x681, 0x682) -> redirect 0x29 (opcode 0x10 two-row choice, no cancel; 0x11 redirects row 0 -> 0x2A, row 1 -> 0x2B) -> 0x2A clears 0x711 (door 1 unlocks) | no scripted walk or stage request; the player opens door 1 |
| Joseph's Lab | ST08:1 | handler 0x800E7738 with 0x5C2 set and 0x5C3 clear: sets 0x5C3 and 0x5E1, scene 0x4F (handler 0x800EFE40; Roll 0x800F53FC and the girl 0x800F5410 are class 0 state 3 actors, messages 0x32, 0x33, 0x34, 0x35, 0x39) | finish respawns Roll 0x800F5424 and the girl 0x800F5438, player free |
| After the lab | ST08:0 | 0x5E1 set: 0x800EE95C spawns Roll 0x800F5284 (follower 0x800E93EC, pose resolver 0x800EEABC; messages 0x11 / 0x10 gated by 0x5D0) | next story target unverified (message 0x34: Joe "went to the ruins") |
| Landing | ST08:0 | handler 0x800E769C: byte14 0 and flag 0x5E4 clear -> spawn hull 0x800F2670, set 0x5E4, scene 0x55 (handler 0x800F0718); later visits spawn group 0x800F2670 x5 | XA 0x62, fade 0x12, sets 0x780, request ST04:0 facing 0, arrival fade 2 |
| Flutter talk | ST04:0 | handler 0x800E7B10: flag 0x5F0 clear -> set 0x5F0, 0xD0-0xD2, scene 0x4C (ST04T 0x800E7CA0); otherwise 0x800E7828 revisit spawns | messages 0xC9, 0xCA, 0xCB->0xCC (set 0x5E3), fade 0x12, request ST08:0 at (0x40,0,0) facing 0x800, arrival fade 3 |
| Free play | ST08:0 | player control; door 1 (Joseph's Lab, scene 0x4F needs 0x5C2) locked by 0x711; door 0 to ST09 / ST0D / ST04:1 | next story step: ST09 junk shop |

## ST1E fire mission

- Door lists come from the per-area table 0x800EEEA8 (copied to 0x80078FA4 at 0x800E73E8-0x800E7404). GAME 0x800B89B4 locks a door while flag 0x710 or 0x710+id is set and shows the record's message.

| Area | Door | Lock flag | Message | Destination |
| --- | --- | --- | --- | --- |
| 0 Deck 2 | id1 | 0x711 | 0x0A | Living Room |
| 0 Deck 2 | four id5 | 0x715 | 0x0B | none |
| 1 Living Room | id2 | 0x712 | 0x0B | Deck 2 |
| 1 Living Room | id3 | 0x713 | 0x0A | Kitchen |
| 2 Kitchen | id4 | 0x714 | 0x0A | Living Room |

- Only the forward doors unlock: 0x800E766C clears 0x711 and 0x800E7878 clears 0x713 when the room's fires are out. Door use runs scene 0 (flag 0x700, handler 0x800ED1EC, timeline 0x800F0BB8).
- Fires are class 0x36 (variant 0 handler 0x800E9DE4, states 0x800EF468: init 0x800E9E68, burning 0x800E9FD8, dying 0x800EA3CC; variant 1 0x800EA994 is spawned when Living Room fire 12 is extinguished). Spawn tables 0x800EF1FC/0x800EF24C/0x800EF350/0x800EF364: Deck 4, Living Room 13+1, Kitchen 5. Strength 0x800/0x1000/0x1C00 by size (0x800EF474). A hit needs hit-word & 0x42000; damage (word & 0xFFF) * 32 plus a close-range bonus with bit 0x2000; extinguished at <= 0x200, otherwise regrows 0x10 per tick. Sounds: crackle 0x152, extinguished 0x153. Frames 0x800EF494.
- Kitchen fires throw embers at Data (spawn 168,0,144); a burning Data (state 0x800E8258) counts as a fire.
- The extinguisher is special weapon 0x0F with flag 0x38F, equipped by the new-game initialiser GAME 0x800C37B0; its module is most likely COMMON/PL00R0F.BIN (unverified).
- Timers are not displayed. Limits: Deck 0x708, Living Room 0xE10, Kitchen 0x1518 ticks. Warnings: message 0x28 at 0x546 (Deck) and 0xA8C (other rooms); Kitchen also 0x29 at 0xFD2. Hint 0x2A after 900 ticks without spraying. 0x800E7B88 fails the mission on timeout or HP 0.
- Mission start: message 0x00 (Yes/No), then 0x01 or 0x02 (extinguisher tutorial), then the objective card 0x32. Kitchen entry: 0x03.
- Scene 0xD (handler 0x800ED7B8): success camera 0x800F0C5C, timeline 0x800F0D34 (messages 0x14, 0x1F); failure camera 0x800F0CC4, timeline 0x800F0D4C (messages 0x22, 0x1E, 0x1F, sprinkler sound 0x10D). Failure also sets 0x12A when 18 or more fires were extinguished. No item or zenny changes.

Scene 0x68 (camera 0x800F225C, timeline 0x800F229C) is a later ST39:1 revisit gated on +0x14 = 0x11 (0x800E7324); it sets 0x580 and leads to ST1F:0.

## Unverified

- DEMO to GAME state hand-off.
- ST1E area 0 -> 1 -> 2 transitions (likely doors).
- Whether the ST3A request is the final timeline step.
- Flags set by dialogue opcodes 0x26/0x27 inside these scenes.

## Flutter repairs and furnishings

- Flag 0xD1 (set by the first-visit scene 0x4C) is the damaged state: the ST06 stage frame `0x800E729C` (GAME table `0x800DC66C[6]`) sets 0x717/0x719 while it is set, which locks the Deck 2 doors to the Living Room and Storage (blocked message ST06:1). Clearing 0xD1 unlocks them.
- Roll's menu (ST04 messages 0x52-0x54 via Talk to Roll): Repairs -> message 0x28/0x29 (cost 2,000/4,000/6,000/8,000 by flags 0x129/0x12A from the fire mission). Yes runs op 0x42 (SLES `0x8004EA14`: wallet below price -> message 0x2B), sets 0xDF, spends zenny (op 0x37) and adds 3000 to save+0x42 (op 0x40, SLES `0x8004E8F8`). ST04T `0x800E7828` then sets save byte 0x7C to 1 and flag 0x134. Op 0x47 (SLES `0x8004ECC4`) compares byte 0x7C against 2/3/4/5; message 0x7C clears 0xD1. GAME `0x800BA420` increments non-zero bytes 0x7C-0x83 whenever a stage >= 8 in a different region (table `0x800DBDA0`, saved as byte 0x12/0x84) is entered.
- Furniture is a placement variant chosen on room entry: ST06T Living Room handler `0x800E73A4` calls GAME `0x800C010C(tile (63,64), 1)` while flag 0xD6 (TV bought, 25,000 zenny) is clear, so the television is absent until bought; Kitchen handler `0x800E7510` does the same for the refrigerator while 0xD4 (5,000 zenny) is clear. 0xD5 (newspaper) spawns an extra actor in the Living Room (unported).

## Abandoned Mine refractor

- Scene 0x54 (ST0FT `0x800FED6C`, finish `0x800FEF20`) registers the refractor `0x8010194C`, Joe `0x80101960` and Roll `0x80101974` (the scene's own copies `0x80101924`/`0x80101938` are removed), sets 0x710 and calls GAME `0x800C0360` at `0x800FF024`: the pending story byte `0x8009C7FD` += 1. GAME `0x800B04B4..0x800B04E0` (and `0x800AED5C..0x800AED80`) commit it to `0x8009C7FC` on the next area request and clear flags 0x580..0x65F (`0x800C037C` -> memclear `0x80015A5C`).
- The refractor actor (class 0x6F, `0x800F1A8C`; talk `0x800F1CEC`, request `0x800BE2E0` kind 0x12) only plays message 30. With 0x583 set it redirects (`FB28`) to 34 ("You got: A refractor!") -> `FB0E` -> 35 ("All right, then, let's go, MegaMan!"), which clears 0x710 and ends with `FB3C` (SLES `0x8004E528`): request block `0x80078D08` type 2, ST47 area 2 at (0,0,0), exit fade 0x22 (`0x8001392C`), arrival fade 2. No item or flag is stored; the refractor is gone because byte14 becomes 1 and the mine handlers (byte14 0 rows) stop spawning it.
- ST47 (Joseph's Room) area 2 row byte14 1 (`0x800E74F4`): flag 0x5B0 clear -> set, GAME `0x800C0B0C(0x12)` (handler `0x800E77B4`, camera `0x800ECD94`, timeline `0x800ECE2C`, states `0x800ECE84`), spawns Joe in bed `0x800ECB38`. Scene: Roll `0x800ECD80`, messages 100, 103, 105, 114, 115, 50-tick hold, fade 0x12, reveal fade 1, music 0x16.
- No original prompt text was found for interactions: target selection (GAME `0x800CC2F0`, `0x800CFAC0`) only latches the actor in player+0x1D0 and enters player state 0x10; no draw call references it. The port's panel is a convenience: "Talk" for NPCs, "Examine" for the refractor, "Open" for chests.

## Forbidden Island capsule

- ST49 scene 0x18 (`0x800E72B0`) selects its camera and timeline at initialization using flag 0x5C1. Clear: camera `0x800EC850`, timeline `0x800ECB20`, seven callback steps, arrival ST10:0 at `(2048,-881,-13312)`, yaw 0x800. Set: camera `0x800ECA44`, timeline `0x800ECB60`, four callback steps, arrival ST04:0 at `(264,-1,320)`, yaw 0. Both requests use mode 2 and arrival fade 2. The per-frame trigger `0x800E7270` tests 0x5C0 or 0x5C1 without an area condition.
- ST07 area 1 (Flutter hangar) parks the capsule: ST07T stage-frame table `0x800E8B28[area]`, area 1 frame `0x800E72FC`, spawns record `0x800E8B10` (class 0x6D, resource `0x6D20`, raw `(0,152,176)` yaw 0x400) once through `0x800E7364` whenever save byte14 is nonzero. No event flag gates it and its update is a no-op, so it stays in every story state. `tools/models.py stage-actors --stage ST07` exports it as per-state scripted actors (constructor `0x800E74E4`, control 2).
- Records `0x800EC788`, `0x800EC79C` and `0x800EC7B0` are procedural pool-0x60 class-0x12 renderers, rather than missing mesh resources. Variants 3 (`0x800EA188`) and 5 (`0x800EAD08`) draw sprite strips; variant 2 (`0x800E9B34`) draws four rotating rings of 32 billboards using heights `0x800ECD2C`, radii `0x800ECD38`, sizes `0x800ECD44`, UV table `0x800ECD50` and palettes selected by `0x800ECC20`. Record `0x800EC7C4` belongs to pool 0xA0 class 9 (`0x800EB2B0`): an additive 11-by-9 grid of textured quads, using page 0x2E, CLUT 0x7C92 and sine-modulated vertex brightness. Its profile at `0x800ECDA0` supplies base 48, amplitude 16 and phase velocities `(320,-240)`.
- Native emulation verifies the departure and return requests over 1302 and 865 updates respectively. A silent Redot GPU probe checks both runtime branch selections, retained records, procedural geometry, textures and the waveform's first native GPU packet positions, UVs and vertex colours. The complete travel and cinematic flow still requires a separate runtime check.

## Sequence mechanics audit

- Camera commands `0x15`/`0x16`/`0x17` install focus/orbit/eye velocity; `0x18`/`0x19`/`0x1A` interpolate those channels. GAME `0x800C1CE4` submits the starting value at elapsed zero and the endpoint on the last update, using the original integer easing tables. Callback `event_clear` operations now clear their native flags.
- ST02T `0x800F00E0` draws additive four-update flashes at step 9 ticks 0 and 125; `0x800F01A4` alternates the two texture regions at step 10 ticks 13–42. Their signed screen vertices come directly from `0x800F298C`/`0x800F2996`, with page 37 and CLUT `0x3DC0`; the large offscreen corners are authored GPU coordinates. Step 14 restores fourteen props at tick 129 from `0x800F2584`. The 128-update VRAM wipe and ten map-cell actor removals still need a port.
- ST49 strip scrolling at `0x800EAEBC–0x800EAEF8` subtracts previous/current camera yaw directly before signed 16-bit phase wrapping. Ring billboards still use the renderer frustum rather than the native centre rejection helper `0x800E8DA0`.
- SLES `0x8001B9D0` resolves XA `0xFF01` to common descriptor `0x8006962C`; this is actual audio, rather than a music hold command. SLES `0x80020984` selects SPU sequence slots and sets their volume fade step/delay, consumed by `0x8001E374`. The main loop calls audio at `0x800110C8`, after the VBlank-divider wait at `0x80010F48`; GAME `0x800AE948` selects divider two through SLES `0x8001136C`/`0x800114A4`, giving 25 updates per second on PAL.
- Scene skips latch Start only while context bit `0x20` permits it (`0x800C10D8`); the pending request survives temporary blockers until bit 4 clears (`0x800C1128`). Scene actions now execute their flag changes, window closure, common XA preparation/playback and sequence-volume fades. The audio adapter currently represents one active music sequence, rather than all six native SPU sequence slots.
- ST1E radio warnings use window 4 (`0x800EBFA8`), preserve player control and continue the room timer (`0x800E7B88`); flag `0x681` suppresses further idle hints while the message is active. The idle hint runs after 901 updates (`0x800E7A8C`). Fire-result transition to ST3A (`0x800EDB4C`) keeps camera and physics ownership with the transition.
- The first-visit mine radio record `0x80100800` now instantiates the existing procedural controller and plays message `0x37` through window 4 (`ST0FT0x800FB0FC–0x800FB148`). Fire-result health refill follows `ST1ET0x800EDB74–0x800EDB84`.
- Mine scene `0x52` retains the intro boss record for gameplay (`ST0FT0x800FE888`). Scene `0x53` borrows that live boss without replacing its transform or animation, waits for native actor removal (`0x800FED28–0x800FED50`), and leaves cleanup with the mission controller. The death animation and 42-update hold complete before the director advances.
- These additions were traced from the original code and reviewed in source; runtime and visual verification remain pending.
