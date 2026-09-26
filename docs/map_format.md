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

## Textures and audio

The stage's `STxxT.BIN` contains executable overlay data and type-2/type-3 texture sections. Texture palettes use XY at +0x0C, color/palette counts at +0x10, image XY at +0x14 and word width/height at +0x18. Compressed sections use the u16 bitfield length at +0x24. Palettes and pixels are restored into PSX VRAM coordinates, then each model's CLUT/TPAGE is decoded into an embedded PNG. The [DashGL texture documentation](https://docs.dashgl.com/format/psx/megaman-legends-2/textures) describes the codec and VRAM texture layouts.

Type-0x05 stage sections contain SPU audio banks. Their payloads satisfy the 16-byte PSX ADPCM block header rules and are excluded from geometry decoding.
