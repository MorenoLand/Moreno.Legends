# Stage geometry extraction

`python tools/export_maps.py --stage ST0F` exports the local PAL disc's ST0F areas into `assets/levels/ST0F`. The project starts `scenes/extracted_level.tscn`; its area selector loads the generated GLBs. The runtime now adds mesh collision and a third-person player; WASD walks, the mouse or Q/E turns the camera, Space jumps, right mouse aims, left mouse fires, and F respawns.

ST0F contains 13 populated area grids, 288 placements and 8,592 exported quads. Geometry, palettes, UVs, vertex brightness and placement positions come from the disc. The current export uses the stored placement state and the first detailed mesh reference; NPC logic, original collision rules, scripted state changes and PSX blend equations are not decoded.

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

## Textures and audio

The stage's `STxxT.BIN` contains executable overlay data and type-2/type-3 texture sections. Texture palettes use XY at +0x0C, color/palette counts at +0x10, image XY at +0x14 and word width/height at +0x18. Compressed sections use the u16 bitfield length at +0x24. Palettes and pixels are restored into PSX VRAM coordinates, then each model's CLUT/TPAGE is decoded into an embedded PNG. The [DashGL texture documentation](https://docs.dashgl.com/format/psx/megaman-legends-2/textures) describes the codec and VRAM texture layouts.

Type-0x05 stage sections contain SPU audio banks. Their payloads satisfy the 16-byte PSX ADPCM block header rules and are excluded from geometry decoding.
