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
| Next | ST08:0 | NPC callback 0x800EE95C: 0x5C1 set and 0x5E1 clear -> Roll 0x800F5298 (message 0x28 -> 0x29 choice -> 0x2A clears 0x711); ST08:1 handler 0x800E7738 with 0x5C2 set -> 0x5C3, 0x5E1, scene 0x4F | |
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
