# Native player controls

The local player export reads `COMMON/PL00P000.BIN` for combat and `PL00P010.BIN` for the civilian model. The models use fifteen joints, with the original sixteenth source joint unused by these meshes. Packed positions and rotations follow SLES `0x8003F96C`/`0x8003FAD8`, including signed shifts and integer interpolation. Controls zero, one and two provide idle, run and walk.

## Buster

GAME `0x800CDCC0` selects controls 112/113 for weapon ID two. Control 113 applies during movement states two, seven and eight. Control 65 and cue `0x95` belong to weapon ID one's kick, not ranged firing. The Buster actor is GAME `0x800D03D0`; its emission uses cue `0x9A`, or `0xF4` underwater.

SLES `0x80040624` caches bone-seven translation at player `+0x4C8/+0x4CA/+0x4CC`. GAME `0x800D069C`–`0x800D06E4` reads this cache for projectile origin. The Godot attachment uses Bone_07's local origin. Upper-body mode two uses the root, head and bones five through seven; the base animation retains leg and inactive-arm world pose.

GAME `0x800CEFD0` binds the upper control at source record one, then sets spawn flag `0x20`. `0x800CE6F0` consumes that flag and allocates one class-one projectile. Markers four, nine and thirteen advance attack substates; they are not three projectile emissions. `0x800CF0E8` compares the sequential control pose against weapon-controller byte one plus the rapid stat delay. The normal base Buster uses pose four plus delay seven, giving an eleven-tick repeat interval on the port's 30-Hz animation timeline. The original PAL wall-clock conversion remains unverified.

The normal new-game initializer `0x800C35B0` clears Buster stats at `0x800C3688`–`0x800C36A8`, yielding attack level zero, damage eight, three maximum shots, fourteen native lifetime ticks, and rapid delay seven. `0x800B09D0` backs up existing stats before the temporary level-two preset; `0x800B0A8C` restores them. Levels zero and one use red `(255,32,32)`, two and three green `(32,192,32)`, four and five yellow `(160,160,32)`, and six and seven blue. GAME `0x800D0A04` draws the original 32×32 sprite at UV `(0,32)`, CLUT `0x7C92`, with normal and additive layers and a sixteen-segment glow. Native spin is `(frame<<7)&0xFFF`.

## Health and reactions

New-game health and maximum health are eighty; the life gauge scales with maximum health instead of showing the enlarged upgrade capacity at startup. The normal starting armor setting two scales contact damage as `max(1,(damage*3)>>2)`. Weak reactions use controls 32/33; strong reactions use 34/38, landing 35/39 and recovery 37/41. Knockback physics remain unported.

## Death

SLES `0x80044070(actor, delta)` applies damage only while the game block `0x8009C7E8+1` is 2 and flag `0x6F4` is clear. From HP above zero, an overshoot clamps HP to 0 and returns 1; a hit at HP 0 or below (`0x80044020`) stores −1 and returns −1. Any nonzero return selects the strong reaction in `0x800CB678` (state 0xF, `0x800C8C44`), so HP 0 is alive and the next hit kills. Substate 3 recovers with controls 37/41 only when HP ≥ 0; at HP −1 it holds the landing control 35/39, slides to rest and `0x800C8E10` sets player `+8` = 2. `0x800CC724` then writes game block +0 = 8, +1 = 0. Map interaction `0x800C4364` runs only at HP ≥ 0. The ST1E timer routine `0x800E7B88` fails the mission at HP exactly 0 before a killing hit can land.

Mode 8 (`0x800B00D0`): `0x80048944(1)`; transition `0x14` (`0x12` when flag `0x246` is set) with `0x80020984(0x3F, 0xB6, 0)` fading music channels by 182 per update from 0x3FFF; after the fade `0x80020C90` and engine phase 5 reload `COMMON/DEMO.BIN` (state 6, `0x800ADE7C`). With flag `0x246` set the fade completes into `0x800B0B18` instead, restoring mode 3 in ST0B (flag `0x248` clear) or ST1B. The ST0B/ST1B handlers heal the player and clear `0x246`. No zenny or item changes were found, and there is no retry or continue prompt.

DEMO state 6 loads file 4 (`COMMON/G_OVER00.BIN`: GAME/OVER textures at VRAM words (640,256) and (768,256), CLUT row 496, sequence section `0x9000`, bank `0x9800`), clears the transition, starts music 0xC, raises a tint from 0 to 0x80 in steps of 2, then holds `(3−0x1F800005)<<8` updates. Start, Cross or Triangle (`0x5008`) skips it. Transition `0x20` then returns to DEMO state 0, the title. The background is the Gouraud quad colour `(0, 0, tint·14>>7)`; four 8-bit sprites at (72, 208) in 640×480 space carry the text. `G_OVER01.BIN` and `G_OVER02.BIN` hold Japanese-text artwork; no loader for file IDs 5 or 6 was found.

## Jumping

GAME `0x800C68BC` starts stationary control 16 before launch, then uses 17 for rising, 18 for falling and 19 for landing. Moving jumps use controls 20, 21 and 22. Their `0xFF` terminal control flags hold the final pose until the corresponding physics state changes; landing waits for its control to finish before returning to idle or locomotion.

The normal native launch velocity is −800, held-jump gravity adds 48 per update, and releasing jump brakes the ascent by 576. Native vertical displacement is `−velocity/4096` per update. The current 30-update gameplay adapter measures approximately 1.727 map units for a held jump, matching the native discrete ascent sum of 1.7265625 within the collision margin. Moving launch speed is 512 and airborne target speed is 640, with acceleration 16 per update. Underwater gravity remains unported.

## Civilian equipment

SLES `0x80078ADC` safe descriptor row `[0,1,2,4,6]` selects native normal-hand groups `0x26F0` on bones 2–4 and `0x1DD0` on bones 5–7. The exporter uses these actual P010 vertices and its bare head; it does not mirror the combat glove or hide part of the Buster mesh. ST04–ST07 select this model before animation setup and reject firing requests.
