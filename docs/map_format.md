# Stage geometry extraction

`python tools/world.py maps --stage ST0F` exports the local PAL disc's ST0F areas into `assets/levels/ST0F`. The project starts `scenes/main.tscn`, then loads the shared `scenes/gameplay.tscn` for gameplay. Its area selector loads the generated GLBs. The runtime adds mesh collision and a third-person player; WASD runs, Shift walks, the mouse or Q/E turns the camera, Space jumps, right mouse aims, left mouse fires, R interacts, and O respawns. F and Mouse4 are bound to Special Weapon / Lifter, whose gameplay behavior is still being implemented.

ST0F contains 13 populated area grids, 288 placements and 8,592 exported quads. Geometry, palettes, UVs, vertex brightness and placement positions come from the disc. The current export uses the stored placement state and the first detailed mesh reference. Actor activation boxes, class-five/class-eight movement and combat, and door destinations have been traced; original collision rules and the complete stage scripting system remain unported.

The actor runtime currently implements class-five states 4/7/10/12/14/15 and class-eight states 0–4/255. Class-five states 0/1/2/13, shared spatial avoidance, airborne collision adapters, native death effects and item drops remain unported. Normal source HP is 23 for class five and 60 for class eight. Rendered geometry supplies collision layer one, the player uses layer two, camera proxies use layer four, and actors use layer eight.

## Root structure

The type-0x0D root uses the 0x2000-window LZ codec. Its bitfield length is a little-endian u16 at header +0x10; bitfields start at +0x30 and are read most significant bit first. Tokens select literal u16s or `(token >> 3)` backreferences of `((token & 7) + 2) * 2` bytes; 0xFFFF advances the reference window by 0x2000. The original decoder is at SLES address 0x8001D370.

All decoded root offsets are measured in **32-bit words**. The first two words select the mesh section and placement section. The third is the header word count; the first area starts immediately after that header, and remaining area offsets occupy header words 3 onward. ST0F mesh and placement sections begin at byte offsets 0x84F4 and 0x19958.

Each area starts with four unsigned bytes: inclusive minimum X/Z and maximum X/Z. Each tile has 12 bytes. Its first u16 contains flags and an 11-bit placement index; bit 0x8000 marks an occupied entry. Bytes 2 and 3 hold tile X/Z. Byte 6 supplies the height bias. Area grids select the applicable placement records, preventing different rooms from being superimposed.

## Meshes and placements

The mesh section starts with a u32 directory count and 12-byte directory entries. The final entry word's low 16 bits select a mesh-reference list in word units. Directory bit 0x01000000 indicates a second three-entry reference list. A selected reference's low 16 bits select a model header.

Model headers are four bytes: submesh count, material count, local coordinate shift and an additional flag byte. Material entries are u16 CLUT plus u16 TPAGE. Each submesh descriptor has four u16 fields: vertex offset, quad count, UV offset and brightness offset. Offsets are relative to the mesh section in word units.

Vertex records contain signed 8-bit XYZ and a control byte. A fresh quad reads four records; the **third record's control byte** supplies the number of following strip quads. Each strip continuation retains the preceding last pair and reads two new records. The second newly consumed record's control byte selects a material with its lower six bits. Each quad has eight UV bytes and four brightness bytes. This is traced in SLES 0x8002F3C8 through 0x8003004C.

The placement section begins with two u16 counts, followed by eight-byte placement records and a u32 render-order index per placement. Each record contains a u16 state value, u8 model ID, u8 flags, u16 height and u8 grid X/Z. The selected grid's tile record supplies the height bias. At global shift zero, the original renderer uses:

```
X = (grid_x << 9) - (directory_word1 & 0x10000000 ? 0x7E00 : 0x7F00)
Z = (grid_z << 9) - (directory_word1 & 0x20000000 ? 0x7E00 : 0x7F00)
Y = 0x400 - tile[6] * 16 - ((placement_height & 0x7F00) >> 4)
```

Local signed-byte vertices are shifted by the model header's coordinate shift and added to these origins. The traced path applies no placement rotation. The exporter converts game units by 1/256 and reverses Y for Godot; quad triangle winding is adjusted accordingly. Placement-origin evidence is at SLES 0x8002F14C through 0x8002F204.

## Terrain

Occupied cell bit `0x8000` gates drawing (`0x80027CB0–0x80027CB8`), then bit `0x4000` selects terrain (`0x80027E84`). Its four native Y values are exactly `-tile[4..7] * 16` (`0x80027D7C–0x80027DFC`), so Godot heights are `tile[4..7] / 16`, with no placement-origin `0x400` subtraction. Terrain (`0x80027E90–0x80027EAC`) and placements (`0x80027FFC–0x80028018`) load the same GTE translation from `0x1F800028`; adding that subtraction lowered the terrain four world units beneath buildings. Native corner order is `(1,3,0,2)` with bit `0x2000`, otherwise `(0,1,2,3)` (`0x800281DC–0x800282B8`).

Placement cells also draw a terrain underlay only when the signed placement height is negative (`0x80027FEC`). The draw uses placement X/Z bytes 6/7, current cell corner heights/colors, and flags `(cell_flags & 0xF000) | placement_height_low_byte | 0xC000` (`0x80028128–0x80028184`); identical contributions are deduplicated. ST08's selected placements have positive height `0x4000`, so they supply their authored floor meshes rather than this underlay.

## Native routes

The shared route extractor resolves current-area indexed pointer loads written to `0x80078FA4`, and standard actor-list tables passed to `SLES0x8003D3F8`, directly from each overlay's MIPS constants and register flow. It preserves explicit native area IDs, 24-byte route records, original arrival coordinates/headings, lock/transition flags, and one-way routes; it retains specialized mine endpoint metadata. Current primary overlays provide 812 transitions: 87 stages fully bound, ST4F partially bound because area 14 has a null route slot, and ST00–ST03/ST1E unresolved. NPC-region door networks are separate from the initial Flutter exterior network; cross-island flight/story travel is not represented by invented door links.

## Ordinary NPC records

ST19, ST1A, ST1B and ST2A bind standard 20-byte class-0 records to the original skinned actor bank. Their constructors (`0x800E808C`, `0x800E7704`, `0x800E7B40`, `0x800E8288`) call `SLES0x8003DFC8` with `actor+6`, selecting resource flags `0x20 | subtype<<16`, and initialize control 0. Byte 6 is a model subtype, not a dialogue index; private bytes 8–11 remain separate. The exported 17 actor records preserve native positions, headings, hitbox pointers and bounds, source record addresses, and complete original animation controls. ST08 and ST09 initial standard/script lists contain no ordinary NPCs; no residents are synthesized there.

## Coplanar faces and exterior fog

SLES `0x8002F96C–0x8002F9F0` uses the first vertex's `0xC0` flag mask to choose the quad's ordering-table depth. Mode `0x80` subtracts sixteen buckets when the maximum-depth bucket is at least sixteen; `0xC0` selects AVSZ4 average depth, rather than an unconditional overlay. Packets are inserted at the ordering-table head at `0x8002FF44–0x8002FF6C`, so earlier source quads win when their depths tie. The coplanar adapter follows that explicit priority and tie order while retaining the camera-facing depth separation needed by Godot's depth buffer.

Silent GPU probes rendered ST05:1, ST06:3/4 and ST07:1 after applying their actual TV/refrigerator placement variants. Repeated bias-enabled frames at the same camera were identical, and cabinet and TV details remained visible in the sampled views. This verifies those views, not every possible camera angle or the PS1's complete ordering-table rasterization.

The map configuration loader sets DQA/DQB, but map mist also changes the texture CLUT independently of per-corner DPCS. ST0D binds table `0x800F04C8` through argument A1 of SLES `0x80026810`; terrain `0x800289D8..0x80028A08` and placements `0x8002FA48..0x8002FA7C` add its low16 palette offset using the maximum native quad SZ shifted by `depth_shift+9`. Terrain flag `0x20` bypasses this palette selection. The source banks start changing at 20 world units and reach the final bank around 46; ST0D exports exact decoded palette atlases and samples the selected bank using all four original quad corners. Environment distance blending remains disabled so it cannot add another fade to the source palettes and native per-corner colours.

`native_map_visibility.gd` ports the mode 0/1 near-square and yaw-dependent scan bands from SLES `0x800270CC`, `0x8002770C`, `0x80027A24`, `0x80029E4C`, `0x8002A48C` and `0x8002A7A4`. Its 1,404 window fixtures match original Unicorn execution over positions, pitches and yaws, including negative coordinates and cardinal directions. Terrain uses cell masks and placements use the source marker cells; shared pool actors retain their separate renderer path. Cell centres are `(cell*512)-32512`; the test plane and per-area ordering-depth threshold come from the original draw routine at `0x80027D40�0x80027E84`. Wider custom camera lenses admit the additional side regions exposed by their projection while preserving the original central window and per-area depth limit. The Godot view transform feeds this test, rather than emulating the integer GTE matrix and flags, and combined terrain masks approximate native whole-quad submission at boundaries.

ST0D areas 0/1 bind background bands through ST0DT `0x800E7200` to GAME `0x800BEF64`: table `0x800F0004` selects `0x800EFE80`, whose bands are solid RGB `(176,176,184)`. The extractor validates the call and bands and the runtime expands its native framebuffer RGB5 to display colour `(181,181,189)` instead of flight clouds behind the draw cutoff. Mode 2/3 draw traversal, other stages' native background bands remain outside this visibility port.

## Flutter fire placement and effects

ST1ET `0x800EABE4` calls GAME `0x800C010C(tile, 1)` for the explosion at tile `(64,63)`, selecting placement 5's second model reference. The two references share all 14 collision records and 237 quads; one door-glass quad changes UV rows 128–175 to 176–223. Runtime swaps must rebuild material bindings because the references order their materials differently. The fire controller remembers this placement change across room reloads, preserving the shattered glass.

Fire persistence is separate: `0x800E76E8–0x800E773C` clears the Living Room's active count, explosion trigger, ember block and idle counter, spawns thirteen normal fires, then sets the active count to thirteen. A Unicorn reentry probe reproduced that reset. GAME `0x800C02D0` resets the area script and flags; it does not reset the placement variant. The original backward mission doors are locked, although the PC room selector can force a revisit.

Both fire death handlers (`0x800EA3CC`, `0x800EB014`) emit three class-`0x12`, variant-one, subtype-two steam sprites on ticks 1, 3 and 5. They use the exported five-subtype animation table: subtype two starts at size 96, rises two raw units per update, and has eight six-update frames. Random spawn offsets, size growth, rotation and colours come from the original records. After the third puff, shared class `0x14` (`GAME0x800D73A0`, SLES dispatch `0x8006B3E4`) grows a sixteen-sample untextured subtractive smoke ribbon, holds it until the fire's 464-update wait ends, then drains it. Its player eye/mouth frame-four writes and frame-zero cleanup use the existing face UV layout. Godot projection, depth testing and a local native update counter adapt the original GTE projection, ordering table and global wave phase.

Silent GPU probes exercised the explosion, intact-to-shattered glass rendering, three steam sprites, smoke growth/drain, face-frame changes and room reentry with the broken glass retained and thirteen normal fires restored.

## Textures and audio

The stage's `STxxT.BIN` contains executable overlay data and type-2/type-3 texture sections. Texture palettes use XY at +0x0C, color/palette counts at +0x10, image XY at +0x14 and word width/height at +0x18. Compressed sections use the u16 bitfield length at +0x24. Palettes and pixels are restored into PSX VRAM coordinates, then each model's CLUT/TPAGE is decoded into an embedded PNG. The [DashGL texture documentation](https://docs.dashgl.com/format/psx/megaman-legends-2/textures) describes the codec and VRAM texture layouts.

Type-0x05 stage sections contain SPU audio banks. Their payloads satisfy the 16-byte PSX ADPCM block header rules and are excluded from geometry decoding.

Pooled PBD actors use a separate origin rejection path at SLES `0x800245F0-0x800246AC` and `0x800255E0-0x8002569C`: RTPS `SZ>>2` must be at least 16 and no greater than scratch `0x1F800010`, selected from config offsets 8/10/12 by depth shift. Projected origin bounds are X `[-352,672]` and Y `[-136,888]`. Actor byte 0 bit `0x40` bypasses these checks only below the depth limit; bit `0x20` disables vertex colour cueing independently. `native_actor_visibility.gd` applies this render-only rejection to model roots while keeping simulation and interaction active; ST0D limit 3072 corresponds to 48 world units. Godot view/projection replaces the integer GTE transform; nonzero depth-shift camera modes remain approximate. Source reviewed; no runtime rendering test was run for this change.

The opened mine entrance remains static ST0D placement 67, model 15 variant 1 (`ST0DT800EEA3C..EEB14 -> GAME800C010C`), rather than a pooled actor. Its replacement scene root inherits map classification before material setup, so the original placement marker cells and the five existing palette-fog atlases govern visibility; the GLB root origin is not used for actor rejection. The mesh translation remains `[-52,6.625,-9]`. Source/asset metadata reviewed; runtime rendering unverified.

Kind `0x1B` placement boxes are solid horizontal-collision walls: GAME `0x800B36E8` runs every box with kind below `0x100` whose mask intersects the actor class through shape `0x800B3C8C`, and handler `0x800B3D34` returns flags `0x41` when the previous XZ position lies inside the box and `0x43` otherwise (kind zero returns `0x43`). Their meshes carry no collision (Flutter hangar launch-bay railing: a `0xFFFF` rim box up to 128 high plus a `0xFFF3` player/friendly box 704 high over the pit, with the floor slab kind zero beneath), so `native_floor.gd` adds every kind `0x1B` box with mask bit zero to the layer-64 `NativeWallCells` body beside the cell walls; the placement keeps its mesh floor.

## Flutter deck map
ST04T-ST07T draw the Flutter's map (`0x800EF16C`) from `COMMON/SUBMAP.BIN` page 7 (three hull strips plus a bow piece, tpage `0x88`, CLUT `0x7FC0`). `tools/world.py export_flutter_map` writes `assets/minimap/Flutter/decks.png` and `manifest.json`: the three deck sprite lists (`0x800F4408`), the 18-entry room table (`0x800F4414`: marker x, y, deck, rule function) and the three marker rule functions `0x800EF5A4`/`0x800EF5F4`/`0x800EF6A8`. A room's entry is its stage base (ST04 0, ST05 3, ST06 6, ST07 12) plus its area index; the player arrow sits at the entry position, or at the rule-function position chosen from the player's cell `((integer position + 0x8000) >> 9)`.

Semi-transparent faces: SLES `0x8002FA14..0x8002FA44` takes the first vertex's flag bits `0x03`; zero draws opaque, otherwise the packet gains the semi-transparent command bit and the TPAGE ABR becomes `status-1` (1 = 50% mix, 2 = additive, 3 = subtractive). `Glb.material` keeps one material per CLUT/TPAGE/blend and writes it to the glTF material `extras.psx_blend`. Blended pages export STP texels (palette word bit `0x8000`) with alpha 128 and other non-zero texels with alpha 255; `native_material.gd` builds `native_model` variants with `blend_mix`/`blend_add`/`blend_sub` and no depth write: texel alpha below 0.25 is discarded, mix draws STP texels at 50% and non-STP texels opaque, add/subtract draw every kept texel at full weight. Gouraud black at a vertex then adds or subtracts nothing (ST1B Junk Shop lamp cone and light slab, status 2). Affected stages: ST00 ST03 ST04 ST07 ST0A ST0D ST0F ST10 ST14 ST1B ST20 ST25 ST28 ST29 ST2C ST2F ST35 ST39 ST3A ST3E ST3F ST40 ST43-ST46 ST49 ST4B ST4C ST4D-ST52 ST58 ST5C.
