# Native player controls

The local player export reads `COMMON/PL00P000.BIN` for combat and `PL00P010.BIN` for the civilian model. The models use fifteen joints, with the original sixteenth source joint unused by these meshes. Packed positions and rotations follow SLES `0x8003F96C`/`0x8003FAD8`, including signed shifts and integer interpolation. Controls zero, one and two provide idle, run and walk.

## Buster

GAME `0x800CDCC0` selects controls 112/113 for weapon ID two. Control 113 applies during movement states two, seven and eight. Control 65 and cue `0x95` belong to weapon ID one's kick, not ranged firing. The Buster actor is GAME `0x800D03D0`; its emission uses cue `0x9A`, or `0xF4` underwater.

SLES `0x80040624` caches bone-seven translation at player `+0x4C8/+0x4CA/+0x4CC`. GAME `0x800D069C`–`0x800D06E4` reads this cache for projectile origin. The Godot attachment uses Bone_07's local origin. Upper-body mode two uses the root, head and bones five through seven; the base animation retains leg and inactive-arm world pose.

GAME `0x800CEFD0` binds the upper control at source record one, then sets spawn flag `0x20`. `0x800CE6F0` consumes that flag and allocates one class-one projectile. Markers four, nine and thirteen advance attack substates; they are not three projectile emissions. `0x800CF0E8` compares the sequential control pose against weapon-controller byte one plus the rapid stat delay. The normal base Buster uses pose four plus delay seven, giving an eleven-tick repeat interval on the port's 30-Hz animation timeline. The original PAL wall-clock conversion remains unverified.

The normal new-game initializer `0x800C35B0` clears Buster stats at `0x800C3688`–`0x800C36A8`, yielding attack level zero, damage eight, three maximum shots, fourteen native lifetime ticks, and rapid delay seven. `0x800B09D0` backs up existing stats before the temporary level-two preset; `0x800B0A8C` restores them. Levels zero and one use red `(255,32,32)`, two and three green `(32,192,32)`, four and five yellow `(160,160,32)`, and six and seven blue. GAME `0x800D0A04` draws the original 32×32 sprite at UV `(0,32)`, CLUT `0x7C92`, with normal and additive layers and a sixteen-segment glow. Native spin is `(frame<<7)&0xFFF`.

## Health and reactions

New-game health and maximum health are eighty; the life gauge scales with maximum health instead of showing the enlarged upgrade capacity at startup. The normal starting armor setting two scales contact damage as `max(1,(damage*3)>>2)`. Weak reactions use controls 32/33; strong reactions use 34/38, landing 35/39 and recovery 37/41. Knockback physics and the complete death flow remain unported.

## Jumping

GAME `0x800C68BC` starts stationary control 16 before launch, then uses 17 for rising, 18 for falling and 19 for landing. Moving jumps use controls 20, 21 and 22. Their `0xFF` terminal control flags hold the final pose until the corresponding physics state changes; landing waits for its control to finish before returning to idle or locomotion.

The normal native launch velocity is −800, held-jump gravity adds 48 per update, and releasing jump brakes the ascent by 576. Native vertical displacement is `−velocity/4096` per update. The current 30-update gameplay adapter measures approximately 1.727 map units for a held jump, matching the native discrete ascent sum of 1.7265625 within the collision margin. Moving launch speed is 512 and airborne target speed is 640, with acceleration 16 per update. Underwater gravity remains unported.

## Civilian equipment

SLES `0x80078ADC` safe descriptor row `[0,1,2,4,6]` selects native normal-hand groups `0x26F0` on bones 2–4 and `0x1DD0` on bones 5–7. The exporter uses these actual P010 vertices and its bare head; it does not mirror the combat glove or hide part of the Buster mesh. ST04–ST07 select this model before animation setup and reject firing requests.
