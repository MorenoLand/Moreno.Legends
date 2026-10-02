from __future__ import annotations
import argparse
import hashlib
import json
import struct
import zlib
from collections import defaultdict
from pathlib import Path
from collections import Counter
import re
import disc
import math
ROOT = Path(__file__).resolve().parents[1]
UNIT = 1.0 / 256.0
COORDINATE_BASIS = {"native_to_godot": [-1, -1, 1], "unit": "1/256 map unit", "root_mirror_required": False, "winding": "reversed for reflected X basis"}
AREA_TEXTURE_BANKS = {("ST3A", 3): [{"file": "ST3A01.BIN", "file_id": 252, "source": "ST3AT overlay callback 0x800F2FEC via SLES0x8001B2D8"}, {"file": "ST3A02.BIN", "file_id": 253, "source": "ST3AT overlay callback 0x800F40A8 via SLES0x8001B2D8"}]}
AREA_PLACEMENT_VARIANTS = {("ST06", 3): [{"tile": [63, 64], "event_flag": 0xD6, "item": "television", "overlay_words": {0x800E7410: 0x0C03016D, 0x800E7414: 0x240400D6, 0x800E7420: 0x24020040, 0x800E7448: 0x2503003F, 0x800E7468: 0x8C440000, 0x800E746C: 0x0C030043, 0x800E7470: 0x24050001}, "source": "ST06T living room handler 0x800E73A4 (table 0x800E8FF0[3]): flag 0xD6 clear -> GAME 0x800C010C(tile (63,64), 1) at 0x800E746C"}], ("ST06", 4): [{"tile": [64, 64], "event_flag": 0xD4, "item": "refrigerator", "overlay_words": {0x800E7534: 0x0C03016D, 0x800E7538: 0x240400D4, 0x800E7540: 0x24020040, 0x800E7568: 0x24C30040, 0x800E7588: 0x8C440000, 0x800E758C: 0x0C030043, 0x800E7590: 0x24050001}, "source": "ST06T kitchen handler 0x800E7510 (table 0x800E8FF0[4]): flag 0xD4 clear -> GAME 0x800C010C(tile (64,64), 1) at 0x800E758C"}], ("ST1E", 1): [{"tile": [64, 63], "item": "door", "runtime": "fire mission explosion", "overlay_words": {0x800EABE0: 0x8C640000, 0x800EABE4: 0x0C030043, 0x800EABE8: 0x24050001, 0x800EABF0: 0x24056000, 0x800EABF4: 0x0C005AC7, 0x800EABF8: 0x24060800, 0x800EABFC: 0x2404008B}, "source": "ST1ET variant 1 fire init 0x800EAA18: tile ((x>>9)+0x40, (z>>9)+0x40) of the fire -> GAME 0x800C010C(tile, 1) at 0x800EABE4; then SLES 0x80016B1C(1, 0x6000, 0x800) camera shake and sound 0x8B"}]}
STAGE_FLAG_RULES = {"ST06": [{"when_event_flag": 0xD1, "flags": [0x717, 0x719], "overlay_words": {0x800E72A4: 0x0C03016D, 0x800E72A8: 0x240400D1, 0x800E72B4: 0x0C030156, 0x800E72B8: 0x24040717, 0x800E72BC: 0x0C030156, 0x800E72C0: 0x24040719, 0x800E72CC: 0x0C030161, 0x800E72D0: 0x24040717, 0x800E72D4: 0x0C030161, 0x800E72D8: 0x24040719}, "source": "ST06T stage frame 0x800E729C (GAME table 0x800DC66C[6]): flag 0xD1 set -> set 0x717/0x719 (0x800C0558), clear -> clear them (0x800C0584); the Deck 2 living room and storage doors lock on them"}]}
AREA_COLLISION_VARIANTS = {("ST10", 1): [{"tile": [63, 65], "variant": 1, "predicate": {"all": [{"kind": "native_save_byte_equals", "key": "native_save_byte14", "default": 0, "value": 1}]}, "overlay_words": {0x800F2A1C: 0x02002021, 0x800F2A20: 0x24050001, 0x800F2A24: 0x0C00FCA3, 0x800F2A44: 0x00021643, 0x800F2A48: 0x2463FFC0, 0x800F2A64: 0x00031E43, 0x800F2A68: 0x2442FFC0, 0x800F2A90: 0x8C440000, 0x800F2A94: 0x0C030043, 0x800F2A98: 0x24050001}, "source": "ST10T0x800F2910 class 29 resource variant 0 (state byte14 1 registration 0x800E7874) selects tile (63,65) collision variant 1 via GAME0x800C010C at 0x800F2A94 and enables semi-transparency through SLES0x8003F28C at 0x800F2A24"}, {"tile": [62, 68], "variant": 1, "predicate": {"all": [{"kind": "native_save_byte_equals", "key": "native_save_byte14", "default": 0, "value": 1}]}, "overlay_words": {0x800F2A1C: 0x02002021, 0x800F2A20: 0x24050001, 0x800F2A24: 0x0C00FCA3, 0x800F2A44: 0x00021643, 0x800F2A48: 0x2463FFC0, 0x800F2A64: 0x00031E43, 0x800F2A68: 0x2442FFC0, 0x800F2A90: 0x8C440000, 0x800F2A94: 0x0C030043, 0x800F2A98: 0x24050001}, "source": "ST10T0x800F2910 class 29 resource variant 0 (state byte14 1 registration 0x800E7874) selects tile (62,68) collision variant 1 via GAME0x800C010C at 0x800F2A94 and enables semi-transparency through SLES0x8003F28C at 0x800F2A24"}, {"tile": [67, 68], "variant": 1, "predicate": {"all": [{"kind": "native_save_byte_equals", "key": "native_save_byte14", "default": 0, "value": 1}]}, "overlay_words": {0x800F2A1C: 0x02002021, 0x800F2A20: 0x24050001, 0x800F2A24: 0x0C00FCA3, 0x800F2A44: 0x00021643, 0x800F2A48: 0x2463FFC0, 0x800F2A64: 0x00031E43, 0x800F2A68: 0x2442FFC0, 0x800F2A90: 0x8C440000, 0x800F2A94: 0x0C030043, 0x800F2A98: 0x24050001}, "source": "ST10T0x800F2910 class 29 resource variant 0 (state byte14 1 registration 0x800E7874) selects tile (67,68) collision variant 1 via GAME0x800C010C at 0x800F2A94 and enables semi-transparency through SLES0x8003F28C at 0x800F2A24"}, {"tile": [69, 65], "variant": 1, "predicate": {"all": [{"kind": "native_save_byte_equals", "key": "native_save_byte14", "default": 0, "value": 1}]}, "overlay_words": {0x800F2A1C: 0x02002021, 0x800F2A20: 0x24050001, 0x800F2A24: 0x0C00FCA3, 0x800F2A44: 0x00021643, 0x800F2A48: 0x2463FFC0, 0x800F2A64: 0x00031E43, 0x800F2A68: 0x2442FFC0, 0x800F2A90: 0x8C440000, 0x800F2A94: 0x0C030043, 0x800F2A98: 0x24050001}, "source": "ST10T0x800F2910 class 29 resource variant 0 (state byte14 1 registration 0x800E7874) selects tile (69,65) collision variant 1 via GAME0x800C010C at 0x800F2A94 and enables semi-transparency through SLES0x8003F28C at 0x800F2A24"}], ("ST08", 1): [{"tile": [63, 64], "variant": 1, "predicate": {"all": [{"kind": "native_save_byte_equals", "key": "native_save_byte14", "default": 0, "value": 0, "negate": True}]}, "overlay_words": {0x800E75B4: 0x14620019, 0x800E75BC: 0x90820014, 0x800E75C4: 0x10400015, 0x800E75C8: 0x24020040, 0x800E75F0: 0x24E3003F, 0x800E7614: 0x0C030043, 0x800E7618: 0x24050001}, "source": "ST08T800E75B0..7618: area1 and saveByte14 nonzero select tile63,64 collision variant1 via GAME800C010C; geometry remains unchanged"}]}
def check_overlay_words(overlay, words, label):
	for address, expected in words.items():
		actual = struct.unpack_from("<I", overlay, 48 + address - 0x800E7000)[0]
		if actual != expected: raise ValueError(f"{label}: overlay word at {address:#x} is {actual:#010x}, expected {expected:#010x}")
def png(width, height, pixels):
	def chunk(kind, data): return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
	rows = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
	return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
def textures(path):
	vram, banks = texture_vram([path]); return vram, sum(bank["upload_count"] for bank in banks)
def texture_vram(paths):
	vram = bytearray(1024 * 512 * 2); banks = []
	for path in paths:
		source = path.read_bytes(); uploads = texture_uploads(source, vram, path.name)
		if not uploads: raise ValueError(f"no texture sections decoded in {path.name}")
		banks.append({"file": path.name, "sha256": digest(source), "upload_count": len(uploads)})
	return vram, banks
def texture_page(vram, clut, tpage, pixels_only=False, stp=False):
	x = (tpage & 15) * 64; y = ((tpage >> 4) & 1) * 256; depth = (tpage >> 7) & 3; px = (clut & 63) * 16; py = clut >> 6
	if depth > 2: raise ValueError(f"unsupported texture depth {depth}")
	pixels = bytearray()
	for v in range(256):
		for u in range(256):
			if depth < 2:
				shift = 2 if depth == 0 else 1; bits = 4 if depth == 0 else 8; word = read_u16(vram, ((y + v) * 1024 + x + (u >> shift)) * 2); index = (word >> ((u & ((1 << shift) - 1)) * bits)) & ((1 << bits) - 1); color = read_u16(vram, (py * 1024 + px + index) * 2)
			else: color = read_u16(vram, ((y + v) * 1024 + x + u) * 2)
			pixels.extend((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 0 if color == 0 else 128 if stp and color & 0x8000 else 255))
	return pixels if pixels_only else png(256, 256, pixels)
class Stage:
	def __init__(self, source):
		self.data, _ = decompress_section(source, 0); b = self.data; self.base = read_u32(b, 0) * 4; self.placement_base = read_u32(b, 4) * 4; count = read_u32(b, 8)
		if not 3 <= count <= 256 or not count * 4 <= self.base < self.placement_base <= len(b): raise ValueError("invalid stage section table")
		self.grids = [count * 4] + [read_u32(b, i * 4) * 4 for i in range(3, count)]; self.directories = [struct.unpack_from("<3I", b, self.base + 4 + i * 12) for i in range(read_u32(b, self.base))]
		self.placement_count, self.scripted_count = struct.unpack_from("<2H", b, self.placement_base); self.placements = [struct.unpack_from("<HBBHBB", b, self.placement_base + 4 + i * 8) for i in range(self.placement_count)]; self.cache = {}; self.face_metadata = {}
	def area(self, index):
		b = self.data; start = self.grids[index]; x, z, end_x, end_z = b[start:start + 4]
		if max(x, z, end_x, end_z) >= 128 or x > end_x or z > end_z: return None
		tiles = {}; ids = set()
		for i in range((end_x - x + 1) * (end_z - z + 1)):
			offset = start + 4 + i * 12; flags, tx, tz = struct.unpack_from("<HBB", b, offset); tiles[(tx, tz)] = b[offset:offset + 12]
			if flags & 0xc000 == 0x8000: ids.add(flags & 0x7ff)
		if any(i >= self.placement_count for i in ids): raise ValueError(f"area {index} has invalid placement index")
		return tiles, sorted(ids)
	def model(self, pointer):
		if pointer in self.cache: return self.cache[pointer]
		b = self.data; start = self.base + pointer * 4; sub_count, material_count, shift, extra = struct.unpack_from("<4B", b, start)
		if not sub_count or not material_count or shift > 12 or extra: raise ValueError(f"unsupported map model header {pointer:#x}")
		materials = [struct.unpack_from("<2H", b, start + 4 + i * 4) for i in range(material_count)]; groups = defaultdict(list); metadata = defaultdict(list); order = 0
		for s in range(sub_count):
			vertex, count, uv, color = struct.unpack_from("<4H", b, start + 4 + material_count * 4 + s * 8); cursor = self.base + vertex * 4; uv_base = self.base + uv * 4; color_base = self.base + color * 4; remaining = 0; previous = None
			for face in range(count):
				if remaining:
					new = [struct.unpack_from("<3bB", b, cursor + k * 4) for k in range(2)]; points = previous[2:] + new; cursor += 8; remaining -= 1
				else:
					new = [struct.unpack_from("<3bB", b, cursor + k * 4) for k in range(4)]; points = new; remaining = new[2][3]; cursor += 16
				material = new[1][3] & 63
				if material >= material_count: raise ValueError(f"model {pointer:#x} face {face} selects missing material {material}")
				coordinates = [(-(p[0] << shift) * UNIT, -(p[1] << shift) * UNIT, (p[2] << shift) * UNIT) for p in points]; texcoords = struct.unpack_from("<8B", b, uv_base + face * 8); brightness = struct.unpack_from("<4B", b, color_base + face * 4); flag = new[0][3]
				key = (materials[material], bool(flag & 32), flag & 3); groups[key].append((coordinates, [(texcoords[i * 2] + 0.5, texcoords[i * 2 + 1] + 0.5) for i in range(4)], brightness)); metadata[key].append({"flags": flag, "order": order, "stream": s, "face": face}); order += 1; previous = points
			if remaining: raise ValueError(f"model {pointer:#x} ends inside a quad strip")
		self.cache[pointer] = groups; self.face_metadata[pointer] = metadata
		return groups
def terrain_binding(path, area):
	return map_config_info(path.read_bytes(), area, path.name)
def map_config_info(data, area, source_name="overlay"):
	base = read_u32(data, 12); end = min(len(data), 48 + read_u32(data, 4)); opcode = 0x0c000000 | ((0x80026810 >> 2) & 0x3ffffff)
	calls = [offset for offset in range(48, end - 3, 4) if read_u32(data, offset) == opcode]
	if len(calls) != 1: raise ValueError(f"{source_name} has {len(calls)} native terrain setup calls")
	call = calls[0]; registers = [None] * 32; registers[0] = 0
	for offset in range(max(48, call - 160), call + 8, 4):
		word = read_u32(data, offset); op = word >> 26; rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31; immediate = (word & 32767) - (word & 32768); value = None; target = None
		if op == 15: target = rt; value = (word & 65535) << 16
		elif op in (8, 9, 13):
			target = rt
			if registers[rs] is not None: value = registers[rs] | (word & 65535) if op == 13 else (registers[rs] + immediate) & 0xffffffff
		elif op == 0 and word & 63 in (0, 33, 35, 37):
			target = rd; function = word & 63
			if function == 0 and registers[rt] is not None: value = (registers[rt] << ((word >> 6) & 31)) & 0xffffffff
			elif registers[rs] is not None and registers[rt] is not None: value = (registers[rs] + registers[rt] if function == 33 else registers[rs] - registers[rt] if function == 35 else registers[rs] | registers[rt]) & 0xffffffff
		elif op in (35, 36, 37):
			target = rt
			if registers[rs] is not None:
				address = (registers[rs] + immediate) & 0xffffffff; position = address - base + 48
				if address == 0x8009c7f9 and op == 36: value = area
				elif 48 <= position and position + (4 if op == 35 else 2 if op == 37 else 1) <= end: value = struct.unpack_from({35: "<I", 36: "<B", 37: "<H"}[op], data, position)[0]
		if target is not None and target != 0: registers[target] = value
	address = registers[4]
	if address is None or not 48 <= address - base + 48 <= end - 128: raise ValueError(f"{source_name} terrain UV pointer is unresolved")
	position = address - base + 48
	config = registers[6]
	if config is None or not 48 <= config - base + 48 <= end - 36: raise ValueError(f"{source_name} map configuration pointer is unresolved")
	palette = registers[5]
	return {"source_call": hex(base + call - 48), "uv_pointer": hex(address), "uv_words": list(struct.unpack_from("<32I", data, position)), "palette_pointer": hex(palette) if palette is not None else None, "palette_offsets": list(struct.unpack_from("<32I", data, palette - base + 48)) if palette is not None and 48 <= palette - base + 48 <= end - 128 else [], "config_pointer": hex(config), "config_bytes_hex": data[config - base + 48:config - base + 84].hex(), "native_renderer": "SLES0x80027E84 selects terrain when cell&0x4000; UV0x80028534; TPAGE0x80026EB8; CLUT0x80028950"}
def terrain_groups(tiles, binding, placements):
	groups = defaultdict(list)
	seen = set()
	binding["palette_disabled_cells"] = []
	executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); rotation_base = 0x800 + 0x8006af14 - 0x80010000
	for (x, z), tile in tiles.items():
		flags = read_u16(tile, 0)
		if flags == 0xffff or not flags & 0x8000: continue
		if not flags & 0x4000:
			if not flags & 0x8000: continue
			_, _, _, height, x, z = placements[flags & 0x7ff]
			if not height & 0x8000: continue
			flags = (flags & 0xf000) | (height & 0xff) | 0xc000
		key = (x, z, flags, bytes(tile[4:12]))
		if key in seen: continue
		seen.add(key)
		if flags & 0x20: binding["palette_disabled_cells"].append([x, z])
		word = binding["uv_words"][flags & 31]; u0, v0, u1, v1 = struct.unpack("<4B", struct.pack("<I", word)); v1 = (v1 + 31) & 255; uv = [(u0 + .5, v0 + .5), (u1 + .5, v0 + .5), (u0 + .5, v1 + .5), (u1 + .5, v1 + .5)]
		rotation = ((flags >> 8) & 3); order = list(executable[rotation_base + rotation * 4:rotation_base + rotation * 4 + 4]); uv = [uv[index] for index in order]
		x0 = ((x << 9) - 0x8000) * UNIT; z0 = ((z << 9) - 0x8000) * UNIT; heights = [tile[index] * 16 * UNIT for index in range(4, 8)]
		corners = [(-x0, heights[0], z0 + 2), (-x0 - 2, heights[1], z0 + 2), (-x0, heights[2], z0), (-x0 - 2, heights[3], z0)]; order = (1, 3, 0, 2) if flags & 0x2000 else (0, 1, 2, 3); clut = ((496 + bool(flags & 128)) << 6) | ((flags >> 3) & 8)
		groups[((clut, 0x1e), bool(flags & 0x800), 0)].append(([corners[index] for index in order], [uv[index] for index in order], [tile[8 + index] for index in order]))
	return groups
class Glb:
	def __init__(self, vram, texture_cache=None):
		self.texture_cache = {} if texture_cache is None else texture_cache
		self.vram = vram; self.binary = bytearray(); self.document = {"asset": {"version": "2.0", "generator": "MML2 map extractor"}, "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "textures": [], "images": [], "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 10497, "wrapT": 10497}], "buffers": [{}], "bufferViews": [], "accessors": [], "extensionsUsed": ["KHR_materials_unlit"]}; self.materials = {}; self.pages = {}; self.meshes = {}; self.bounds = []
	def buffer(self, data, target=None):
		self.binary.extend(b"\0" * (-len(self.binary) % 4)); index = len(self.document["bufferViews"]); view = {"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(data)}
		if target: view["target"] = target
		self.document["bufferViews"].append(view); self.binary.extend(data)
		return index
	def accessor(self, values, dimension, position=False):
		index = len(self.document["accessors"]); accessor = {"bufferView": self.buffer(struct.pack("<" + str(len(values)) + "f", *values), 34962), "componentType": 5126, "count": len(values) // dimension, "type": {2: "VEC2", 3: "VEC3", 4: "VEC4"}[dimension]}
		if position: accessor.update(min=[min(values[k::dimension]) for k in range(dimension)], max=[max(values[k::dimension]) for k in range(dimension)])
		self.document["accessors"].append(accessor)
		return index
	def material(self, key):
		if key in self.materials: return self.materials[key]
		page, two_sided, blend = key
		source = (page, bool(blend))
		if source not in self.pages:
			clut, tpage = page
			if source not in self.texture_cache: self.texture_cache[source] = texture_page(self.vram, clut, tpage, stp=bool(blend))
			image = len(self.document["images"]); self.document["images"].append({"bufferView": self.buffer(self.texture_cache[source]), "mimeType": "image/png"}); texture = len(self.document["textures"]); self.document["textures"].append({"sampler": 0, "source": image}); self.pages[source] = texture
		index = len(self.document["materials"]); self.document["materials"].append({"name": f"clut_{page[0]:04x}_page_{page[1]:04x}", "pbrMetallicRoughness": {"baseColorTexture": {"index": self.pages[source]}, "metallicFactor": 0, "roughnessFactor": 1}, "alphaMode": "MASK", "alphaCutoff": 0.01, "doubleSided": two_sided, "extensions": {"KHR_materials_unlit": {}}, "extras": {"psx_blend": blend}}); self.materials[key] = index
		return index
	def mesh(self, pointer, groups, face_metadata=None):
		if pointer in self.meshes: return self.meshes[pointer]
		primitives = []
		for key, faces in groups.items():
			positions = []; uvs = []; colors = []; native_faces = []
			for face, (coordinates, texcoords, brightness) in enumerate(faces):
				metadata = face_metadata[key][face] if face_metadata else None
				for i in (0, 2, 1, 1, 2, 3):
					positions.extend(coordinates[i]); uvs.extend(v / 256 for v in texcoords[i]); colors.extend([brightness[i] / 255] * 3 + [metadata["flags"] / 255 if metadata else 1])
					if metadata: native_faces.extend((metadata["order"], metadata["flags"]))
			attributes = {"POSITION": self.accessor(positions, 3, True), "TEXCOORD_0": self.accessor(uvs, 2), "COLOR_0": self.accessor(colors, 4)}
			if face_metadata: attributes["TEXCOORD_1"] = self.accessor(native_faces, 2)
			primitives.append({"attributes": attributes, "material": self.material(key), "mode": 4})
		index = len(self.document["meshes"]); self.document["meshes"].append({"name": f"map_mesh_{pointer:04x}", "primitives": primitives}); self.meshes[pointer] = index
		return index
	def instance(self, name, pointer, groups, translation, face_metadata=None):
		mesh = self.mesh(pointer, groups, face_metadata); index = len(self.document["nodes"]); self.document["nodes"].append({"name": name, "mesh": mesh, "translation": translation}); self.document["scenes"][0]["nodes"].append(index)
		for faces in groups.values():
			for points, _, _ in faces: self.bounds.extend(tuple(p[k] + translation[k] for k in range(3)) for p in points)
	def save(self, path):
		self.binary.extend(b"\0" * (-len(self.binary) % 4)); self.document["buffers"][0]["byteLength"] = len(self.binary); text = json.dumps(self.document, separators=(",", ":")).encode(); text += b" " * (-len(text) % 4); size = 12 + 8 + len(text) + 8 + len(self.binary); write_output(path, struct.pack("<3I", 0x46546c67, 2, size) + struct.pack("<2I", len(text), 0x4e4f534a) + text + struct.pack("<2I", len(self.binary), 0x004e4942) + self.binary)
		return {"min": [min(p[k] for p in self.bounds) for k in range(3)], "max": [max(p[k] for p in self.bounds) for k in range(3)]}
def export_maps(stage_name, input_dir, output_dir):
	source = (input_dir / f"{stage_name}.BIN").read_bytes(); stage = Stage(source); texture_path = input_dir / f"{stage_name}T.BIN"; vram, texture_count = textures(texture_path); destination = output_dir / stage_name; destination.mkdir(parents=True, exist_ok=True); areas = []
	texture_cache = {}
	for index in range(len(stage.grids)):
		area = stage.area(index)
		if area is None: continue
		tiles, ids = area; glb = Glb(vram, texture_cache); quads = 0; placement_streams = []
		ground = terrain_groups(tiles, terrain_binding(texture_path, index), stage.placements) if any(read_u16(tile, 0) != 0xffff and read_u16(tile, 0) & 0x8000 and (read_u16(tile, 0) & 0x4000 or stage.placements[read_u16(tile, 0) & 0x7ff][3] & 0x8000) for tile in tiles.values()) else {}
		if ground: glb.instance("terrain", -1, ground, [0, 0, 0]); quads += sum(len(faces) for faces in ground.values())
		if not ids and not ground: continue
		for placement_id in ids:
			state, model_id, flags, height, x, z = stage.placements[placement_id]; a, h, directory = stage.directories[model_id]; variant = flags & 3; variants = ((h >> 24) & 1) + 1
			if variant >= variants: raise ValueError(f"placement {placement_id} selects invalid variant {variant}")
			pointer = read_u16(stage.data, stage.base + (directory & 65535) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [-((x << 9) - (0x7e00 if h & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if h & 0x20000000 else 0x7f00)) * UNIT]; glb.instance(f"placement_{placement_id:03d}_model_{model_id:03d}", pointer, groups, translation, stage.face_metadata[pointer]); quads += sum(len(f) for f in groups.values())
			streams = placement_stream_visibility(stage, placement_id)
			if streams: placement_streams.append(streams)
		name = f"area_{index:02d}.glb"; bounds = glb.save(destination / name); areas.append({"index": index, "file": name, "placements": len(ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds, "native_map_face_flags_in_alpha": True, "placement_streams": placement_streams}); print(f"{stage_name}/{name}: {len(ids)} placements, {quads} quads, {len(glb.pages)} texture pages")
	manifest = {"stage": stage_name, "coordinate_basis": COORDINATE_BASIS, "source_sha256": hashlib.sha256(source).hexdigest(), "textures_sha256": hashlib.sha256(texture_path.read_bytes()).hexdigest(), "texture_sections": texture_count, "areas": areas}; write_output(destination / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest
def placement_stream_visibility(stage, placement_id):
	_, model_id, flags, _, _, _ = stage.placements[placement_id]; _, _, directory = stage.directories[model_id]; descriptor = read_u32(stage.data, stage.base + (directory & 65535) * 4 + (flags & 3) * 12 + 4)
	if not descriptor & 0x10000000: return None
	first = 4 if descriptor & 0x01000000 else 0; pointer = read_u16(stage.data, stage.base + (directory & 65535) * 4 + (flags & 3) * 12); base = stage.base + pointer * 4; count, materials = stage.data[base:base + 2]; ranges = []; order = 0
	for stream in range(count):
		faces = read_u16(stage.data, base + 4 + materials * 4 + stream * 8 + 2); ranges.append([order, order + faces]); order += faces
	closed = ranges[first + 1] if first + 1 < len(ranges) else [-1, -1]; opened = ranges[first] if first < len(ranges) else [-1, -1]
	return {"placement": placement_id, "closed_hidden_range": closed, "open_hidden_range": opened, "default_hidden_range": opened if flags & 4 else closed, "source": "SLES0x80038EF4 sets placement flags bit4; full-LOD renderer0x8002F274..2F2F0 builds stream skip mask1/2 (shift4 when descriptor&0x01000000); 0x80030008..30024 shifts once per8-byte stream descriptor"}
def maps_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--input-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--output-dir", type=Path, default=Path("assets/levels")); parser.add_argument("--stage", default="ST0F"); args = parser.parse_args(); export_maps(args.stage.upper(), args.input_dir, args.output_dir)

STAGE_PATH = ROOT / "build/disc-assets/DAT/ST0F.BIN"
OVERLAY_PATH = ROOT / "build/disc-assets/DAT/ST0FT.BIN"
PLAYER_PATH = ROOT / "build/disc-assets/COMMON/PL00P000.BIN"
EXE_PATH = ROOT / "build/disc-assets/SLES_035.56"
GAME_PATH = ROOT / "build/disc-assets/COMMON/GAME.BIN"
OUTPUT_PATH = ROOT / "assets/levels/ST0F/lighting.json"
PLAYER_PARTS = (("Body", 0x80, 6), ("Head", 0xB60, 3), ("Feet", 0x1800, 2), ("Buster", 0x2220, 3), ("LeftArm", 0x26F0, 3))
MAP_DRAW_RANGE = (0x8002F3C8, 0x8003004C)
PBD_TINT_WORDS = {0x80023954: 0x8E0302A8, 0x80023958: 0x8E0202AC, 0x8002398C: 0x8E0402A8, 0x80023AA4: 0x8E0202A8, 0x80023AB0: 0xAE0202AC}

def read_executable(path):
	data = path.read_bytes()
	if data[:8] != b"PS-X EXE": raise ValueError("SLES input is not a PS-X EXE")
	load_address, code_size = struct.unpack_from("<2I", data, 0x18)
	code = data[0x800:0x800 + code_size]
	if len(code) != code_size: raise ValueError("truncated SLES executable code")
	return data, load_address, code

def instruction_at(code, load_address, pc):
	offset = pc - load_address
	if offset < 0 or offset + 4 > len(code): raise ValueError(f"SLES address outside loaded code: {pc:#x}")
	return struct.unpack_from("<I", code, offset)[0]

def ctc2_registers(code, base, start=None, end=None):
	start = 0 if start is None else max(0, start - base); end = len(code) if end is None else min(end - base + 4, len(code)); result = Counter()
	for offset in range(start, end - 3, 4):
		word = struct.unpack_from("<I", code, offset)[0]
		if word >> 26 == 0x12 and ((word >> 21) & 31) == 6: result[(word >> 11) & 31] += 1
	return result

def memory_offsets(code, base, wanted):
	loads = []
	stores = []
	for offset in range(0, len(code) - 3, 4):
		word = struct.unpack_from("<I", code, offset)[0]; op = word >> 26; immediate = word & 0xffff; pc = base + offset
		if op in (32, 33, 35, 36, 37) and immediate in wanted: loads.append({"pc": f"0x{pc:08X}", "word": f"0x{word:08X}", "offset": f"0x{immediate:04X}"})
		if op in (40, 41, 43) and immediate in wanted: stores.append({"pc": f"0x{pc:08X}", "word": f"0x{word:08X}", "offset": f"0x{immediate:04X}"})
	return loads, stores

def overlay_info(path):
	data = path.read_bytes(); section_type, full_size, section_count, load_address = struct.unpack_from("<4I", data, 0)
	if section_type != 1 or full_size <= 0 or 0x30 + full_size > len(data): raise ValueError("invalid ST0FT executable section")
	code = data[0x30:0x30 + full_size]; control_regs = ctc2_registers(code, load_address)
	loads, stores = memory_offsets(code, load_address, {0x02A8, 0x02AC})
	return {"file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest(), "section_type": f"0x{section_type:02X}", "full_size": full_size, "section_count": section_count, "load_address": f"0x{load_address:08X}", "ctc2_control_registers_written": sorted(control_regs), "ctc2_write_counts": {str(k): v for k, v in sorted(control_regs.items())}, "direct_entity_tint_field_loads": loads, "direct_entity_tint_field_stores": stores}

def stage_colors(path):
	source = path.read_bytes(); stage = Stage(source); output = []
	for area_index in range(len(stage.grids)):
		area = stage.area(area_index)
		if area is None: continue
		tiles, placement_ids = area; pointers = set()
		for placement_id in placement_ids:
			_, model_id, flags, _, _, _ = stage.placements[placement_id]; _, header, directory = stage.directories[model_id]; variant = flags & 3; variant_count = ((header >> 24) & 1) + 1
			if variant >= variant_count: raise ValueError(f"area {area_index} placement {placement_id} selects invalid model variant")
			pointers.add(struct.unpack_from("<H", stage.data, stage.base + (directory & 0xffff) * 4 + variant * 12)[0])
		values = Counter()
		for pointer in pointers:
			for faces in stage.model(pointer).values():
				for _, _, corners in faces: values.update(corners)
		if values:
			count = sum(values.values()); output.append({"area": area_index, "placements": len(placement_ids), "unique_models": len(pointers), "corner_brightness_bytes": count, "range": [min(values), max(values)], "mean": round(sum(value * number for value, number in values.items()) / count, 4), "histogram": {str(value): values[value] for value in sorted(values)}})
	return source, output

def player_color_info(path):
	data = path.read_bytes(); full_size = struct.unpack_from("<I", data, 4)[0]; payload = data[0x30:0x30 + full_size]; active = []; reference = []; strip_count = 0
	for _, base, count in PLAYER_PARTS:
		for strip_index in range(count):
			offset = base + strip_index * 0x18; _, _, vertex_count, _, _, _, _, active_offset, reference_offset = struct.unpack_from("<4B5I", payload, offset)
			if not vertex_count or active_offset + vertex_count * 4 > len(payload) or reference_offset + vertex_count * 4 > len(payload): raise ValueError(f"invalid player PBD color strip at {offset:#x}")
			active.extend(payload[active_offset + i * 4 + c] for i in range(vertex_count) for c in range(3)); reference.extend(payload[reference_offset + i * 4 + c] for i in range(vertex_count) for c in range(3)); strip_count += 1
	return {"file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest(), "color_strips": strip_count, "active_reference_equal": active == reference, "active_rgb_bytes": {"count": len(active), "range": [min(active), max(active)], "neutral_value": 128, "histogram": {str(value): active.count(value) for value in sorted(set(active))}}, "reference_rgb_bytes_equal_active": active == reference}

def native_actor_area_count(data, maximum):
	base = read_u32(data, 12); end = min(len(data), 48 + read_u32(data, 4)); counts = []
	for table in native_area_tables(data)["actors"]:
		count = 0
		for area in range(maximum):
			offset = 48 + table["pointer_ram"] - base + area * 4
			if not 48 <= offset <= end - 4: break
			pointer = read_u32(data, offset); offset = 48 + pointer - base
			if not 48 <= offset < end: break
			valid = False
			for index in range(128):
				position = offset + index * 20
				if position >= end: break
				if data[position] == 255: valid = True; break
				if position + 20 > end or data[position + 2] not in (0, 0x20, 0x60, 0x61, 0xA0, 0xA1, 0xE0): break
			if not valid: break
			count += 1
		counts.append({"table_ram": hex(table["pointer_ram"]), "count": count, "source_call": table["source_call"]})
	if not counts or len({item["count"] for item in counts}) != 1 or counts[0]["count"] == 0: raise ValueError("Native actor-area table extent is unresolved")
	return counts[0]["count"], counts
def map_depth_cue_info(overlay_data, exe_code, exe_load, area_count):
	base = struct.unpack_from("<I", overlay_data, 0xC)[0]; native_count, actor_tables = native_actor_area_count(overlay_data, area_count); unresolved_areas = list(range(native_count, area_count)); bindings = [map_config_info(overlay_data, area) for area in range(native_count)]; table = int(bindings[0]["config_pointer"], 16) if bindings else None
	if instruction_at(exe_code, exe_load, 0x8002B750) != 0x4A780010 or instruction_at(exe_code, exe_load, 0x800264FC) != 0x4A780010: raise ValueError("Native depth-cue instructions differ from the source trace")
	callbacks = [instruction_at(exe_code, exe_load, 0x80078B7C + index * 4) for index in range(8)]; parameters = []
	for area in range(native_count):
		address = int(bindings[area]["config_pointer"], 16); offset = address - base + 0x30; raw = bytes.fromhex(bindings[area]["config_bytes_hex"])
		if len(raw) != 36: raise ValueError("Truncated native map configuration")
		if raw[3] > 2: raise ValueError(f"Area{area} does not select one of the three native depth-shift configuration columns")
		mode = raw[7] & 3; fog_near = struct.unpack_from("<H", raw, 4)[0]
		parameters.append({"area": area, "source_ram": hex(address), "source_file_offset": hex(offset), "raw_hex": raw.hex(), "enabled": bool(mode & 1), "mode": mode, "flags": raw[7], "far_rgb": list(raw[:3]), "depth_shift": raw[3], "native_units_per_world": 256, "ir0_scale": 4096, "sz_max": 65535, "map_callback": hex(callbacks[mode]), "placement_callback": hex(callbacks[mode + 4]), "visibility": {"tile_range": raw[6], "map_cell_depth_limit_table": list(struct.unpack_from("<3H", raw, 8)), "map_cell_ot_depth_limit": struct.unpack_from("<H", raw, 8 + raw[3] * 2)[0], "map_cell_transformed_depth_limit": struct.unpack_from("<H", raw, 8 + raw[3] * 2)[0] * 4, "placement_depth_limit_table": list(struct.unpack_from("<3H", raw, 0x10)), "scratch_0e": struct.unpack_from("<H", raw, 0x0E)[0], "scratch_9c": struct.unpack_from("<H", raw, 0x1C)[0], "scratch_9e": struct.unpack_from("<H", raw, 0x1E)[0], "scratch_a0": struct.unpack_from("<H", raw, 0x20)[0], "scratch_a2_before_depth_shift": struct.unpack_from("<H", raw, 0x22)[0], "source": "SLES26934..26994 selects config8/0A/0C by depth_shift into scratch10;27E2C..27E38 rejects transformed cellDepth>>2>=scratch10; tile range config6->scratch9A"}, "noise_range": struct.unpack_from("<H", raw, 0x18)[0], "noise_offset_step": [value - 256 if value & 128 else value for value in raw[0x1A:0x1C]], "rational_setup": {"fog_near_raw": fog_near, "reference_h": 384, "dqa": int(-fog_near * 320 / 384), "dqb": 0x01400000, "used_for_map_corners": False}})
	return {"area_selector": "0x8009C7E8+0x11", "area_actor_tables": actor_tables, "unresolved_geometry_grid_indices": unresolved_areas, "area_count_scope": "Native area-object pointer table extent is validated independently; additional geometry grids are not assumed to be native area indices", "config_loader": {"callee": "SLES0x80026810", "source_calls": sorted({binding["source_call"] for binding in bindings})}, "record_table": hex(table) if table is not None else None, "record_stride": 36, "map_dispatch": "SLES0x80026EA0..0x80026EC4 indexes 0x80078B7C by config.flags&3", "placement_dispatch": "SLES0x8002707C..0x800270B4 indexes 0x80078B8C by config.flags&3", "far_color_loader": "SLES0x8005F6F4 writes configRGB<<4 to GTE control21/22/23", "map_corner_source": "SLES0x8002B728..0x8002B754 and0x8002C210..0x8002C23C write vertexSZ>>depth_shift into IR0 before DPCS", "pbd_corner_source": "SLES0x800260C4..0x80026100 and0x800264D4..0x80026510 depth-cue the already tinted activeRGB buffer", "pbd_enable_guard": "config.flags&1 !=0 and actor.byte0&0x20 ==0; SLES0x80024BA4..0x80024BF4 and0x80025B00..0x80025B44", "formula": {"sz": "clamp(floor(camera_view_depth*256*(1<<depth_shift)),0,65535)", "ir0": "unsigned16(SZ>>depth_shift)", "rgb": "clamp((activeRGB*(4096-ir0)+farRGB*ir0)>>12,0,255)", "interpolation": "Per-corner RGB is depth-cued before texture modulation and Gouraud interpolation; DQA/DQB do not supply IR0 in this path", "black_far_color": "For farRGB=0, effective depth-cue factor saturates at1 when IR0>=4096"}, "area_parameters": parameters}
def export_depth_cue(dat_dir=None, output_dir=None, stages=None):
	dat_dir = Path(dat_dir) if dat_dir else ROOT / "build/disc-assets/DAT"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/levels"; _, exe_load, exe_code = read_executable(dat_dir.parent / "SLES_035.56"); result = {"stages": {}, "unresolved": {}}
	trig_offset = 0x80073E4C - exe_load; math_data = {"source": "SLES80073E4C; map windows270CC..276E4 and2984C; rays yaw+-0x100, division constants384/4096 and cell centers512", "trig4096": [list(struct.unpack_from("<2h", exe_code, trig_offset + index * 4)) for index in range(4096)]}; output_dir.mkdir(parents=True, exist_ok=True); write_output(output_dir / "visibility_math.json", json.dumps(math_data, separators=(",", ":")) + "\n")
	for stage in sorted(set(stages or [path.stem for path in dat_dir.glob("ST??.BIN")])):
		root_path = dat_dir / (stage + ".BIN"); overlay_path = dat_dir / (stage + "T.BIN")
		if not root_path.is_file() or not overlay_path.is_file(): continue
		stage_data = Stage(root_path.read_bytes())
		try: cue = map_depth_cue_info(overlay_path.read_bytes(), exe_code, exe_load, len(stage_data.grids))
		except ValueError as error: result["unresolved"][stage] = str(error); continue
		if stage == "ST0D":
			background_overlay = overlay_path.read_bytes(); check_overlay_words(background_overlay, {0x800E71EC: 0x92220011, 0x800E71F0: 0x24630004, 0x800E71FC: 0x8C440000, 0x800E7200: 0x0C02FBD9}, "ST0D native background binding")
			vram, _ = textures(overlay_path)
			palette_atlases = set()
			for profile in cue["area_parameters"]:
				pointer = read_u32(background_overlay, 48 + 0x800F0004 - 0x800E7000 + int(profile["area"]) * 4); colors = list(struct.unpack_from("<48I", background_overlay, 48 + pointer - 0x800E7000))
				if len(set(colors)) != 1 or colors[0] & 0xFF000000: raise ValueError("ST0D native background is no longer a solid Gouraud strip")
				profile["background"] = {"mode": "solid", "rgb": list(struct.pack("<I", colors[0])[:3]), "source_call": "ST0DT800E7200->GAME800BEF64", "source_table": "0x800F0004", "source_bands": hex(pointer), "draw_source": "GAME800BEFB8..800BF164, 32-pixel Gouraud bands"}
				binding = map_config_info(background_overlay, int(profile["area"])); offsets = [value & 65535 for value in binding["palette_offsets"]]
				if len(offsets) != 32 or offsets != [0] * 10 + [1] * 3 + [2] * 3 + [3] * 2 + [4] * 2 + [5] * 2 + [6] + [7] * 9: raise ValueError("ST0D native depth palette table changed")
				variants = sorted(set(offsets)); geometry = stage_data.area(int(profile["area"])); tiles, placements = geometry; groups = terrain_groups(tiles, binding, stage_data.placements); materials = set(groups)
				for placement in placements:
					_, model, flags, _, _, _ = stage_data.placements[placement]; _, _, directory = stage_data.directories[model]; variant = flags & 3; model_pointer = read_u16(stage_data.data, stage_data.base + (directory & 65535) * 4 + variant * 12); materials.update(stage_data.model(model_pointer))
				atlases = {}
				for (clut, tpage), _, _ in sorted(materials):
					name = f"clut_{clut:04x}_page_{tpage:04x}"; target = output_dir / stage / "palette_fog" / (name + ".png")
					if name not in palette_atlases and disc.may_write(target):
						pixels = b"".join(texture_page(vram, clut + offset, tpage, True) for offset in variants); write_output(target, png(256, 256 * len(variants), pixels))
					palette_atlases.add(name); atlases[name] = "palette_fog/" + target.name
				profile["palette_fog"] = {"enabled": True, "directory": f"res://assets/levels/{stage}", "source_table": binding["palette_pointer"], "offsets": offsets, "variants": variants, "atlases": atlases, "terrain_disabled_cells": binding["palette_disabled_cells"], "bucket_shift": int(profile["depth_shift"]) + 9, "source": "SLES289D8..28A08 terrain flag20 clear; 2FA48..2FA7C placements; max quad SZ>>2 shifted by scratchB5+7 indexes scratchA8 u32 table and adds low16 to CLUT"}
		for area in cue["area_parameters"]:
			geometry = stage_data.area(area["area"]); tiles = geometry[0] if geometry is not None else {}; cells = {}
			grid = stage_data.grids[area["area"]]; area["visibility"]["window"] = {"enabled": geometry is not None and area["mode"] in (0, 1), "grid_bounds": list(stage_data.data[grid:grid + 4]), "math_manifest": "res://assets/levels/visibility_math.json", "source": "SLES270CC..276E4 near square plus yaw-dependent2770C/27A24 scan bands; mode1 equivalent29E4C/2A48C/2A7A4", "half_ray_angle_raw": 256}
			for (x, z), tile in sorted(tiles.items()):
				flags = read_u16(tile, 0)
				if flags == 0xFFFF or not flags & 0x8000 or flags & 0x4000: continue
				cells.setdefault(str(flags & 0x7FF), []).append([(x << 9) - 0x7F00, (z << 9) - 0x7F00])
			area["visibility"]["placement_cells"] = cells; area["visibility"]["cell_center_source"] = "SLES27C08..27C24:cellX/Z*512-0x7F00"; area["visibility"]["test_plane_source"] = "SLES27B10..27B54:cameraNativeY+(sin(-cameraPitch)*(tileRange+1)>>4)"; area["visibility"]["placement_gate_source"] = "SLES26E08..26E28 clears visibility flags;27E38 dispatch marks referenced placements from visible cells;2F0F4..2F100 draws only marked records"; area["visibility"]["runtime_adapters"] = ["Godot camera transforms feed the native per-cell depth test; the native integer GTE transform is not emulated.", "Combined terrain geometry reconstructs512-unit cell centers from its local x/z fragment coordinates.", "Mode0/1 near-square and yaw-dependent far scan bands use the original integer LUT and division rules; mode2/3 traversal and model directionalLOD selection remain separate."]
		path = output_dir / stage / "lighting.json"; lighting = json.loads(path.read_text()) if path.is_file() else {"sources": {"stage_overlay": {"file": "build/disc-assets/DAT/" + overlay_path.name, "sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest()}}, "native_color_pipeline": {}}
		lighting.setdefault("native_color_pipeline", {})["depth_cue"] = cue; path.parent.mkdir(parents=True, exist_ok=True); write_output(path, json.dumps(lighting, indent=2) + "\n"); result["stages"][stage] = len(cue["area_parameters"])
	return result
def lighting_cli():
	stage_path = STAGE_PATH; overlay_path = OVERLAY_PATH; player_path = PLAYER_PATH; exe_path = EXE_PATH
	stage_source, areas = stage_colors(stage_path); overlay = overlay_info(overlay_path); player = player_color_info(player_path); exe_data, exe_load, exe_code = read_executable(exe_path)
	if exe_load != 0x80010000: raise ValueError(f"unexpected SLES load address {exe_load:#x}")
	map_ctc2 = ctc2_registers(exe_code, exe_load, MAP_DRAW_RANGE[0], MAP_DRAW_RANGE[1])
	tint_signatures = {f"0x{pc:08X}": f"0x{instruction_at(exe_code, exe_load, pc):08X}" for pc in PBD_TINT_WORDS}
	if any(int(value, 16) != PBD_TINT_WORDS[int(address, 16)] for address, value in tint_signatures.items()): raise ValueError("SLES PBD tint instructions differ from verified native trace")
	map_loads, map_stores = memory_offsets(exe_code[MAP_DRAW_RANGE[0] - exe_load:MAP_DRAW_RANGE[1] - exe_load + 4], MAP_DRAW_RANGE[0], {0x02A8, 0x02AC})
	lighting = {"sources": {"stage": {"file": str(stage_path.relative_to(ROOT)), "sha256": hashlib.sha256(stage_source).hexdigest(), "section": {"type": "0x0D", "decoded_size": len(Stage(stage_source).data), "areas": areas}}, "stage_overlay": overlay, "main_executable": {"file": str(exe_path.relative_to(ROOT)), "sha256": hashlib.sha256(exe_data).hexdigest(), "load_address": f"0x{exe_load:08X}"}, "player_pbd": player}, "native_color_pipeline": {"map_renderer": {"address_range": [f"0x{x:08X}" for x in MAP_DRAW_RANGE], "gte_control_registers_written": sorted(map_ctc2), "direct_entity_tint_field_loads": map_loads, "direct_entity_tint_field_stores": map_stores, "surface_color_source": "ST0F type-0x0D model submesh color pointer; four bytes per face, one byte per corner", "neutral_byte": 128, "modulation_factor": "corner_byte/128", "light_sources_or_room_rgb_records": "none confirmed in the decoded grid/placement/model layout"}, "entity_pbd_tint": {"function": "0x80023438", "target_rgb_offset": "0x2A8", "cached_rgb_offset": "0x2AC", "formula": "activeRGB=clamp(referenceRGB+targetRGB-128,0,255)", "neutral_rgb": [128, 128, 128], "setter_or_room_source": "not identified in ST0F/ST0FT"}, "stage_overlay_gte": {"ctc2_control_registers_written": overlay["ctc2_control_registers_written"], "color_matrix_control_registers": [8, 9, 10, 11, 12], "color_matrix_registers_written": sorted(set(overlay["ctc2_control_registers_written"]).intersection((8, 9, 10, 11, 12)))}, "player_pbd": {"modulation_factor": "active_byte/128", "active_reference_buffers_equal_in_disc": player["active_reference_equal"], "tint_words": tint_signatures}}, "room_lighting": {"decoded_point_lights": [], "separate_room_rgb_table": None, "evidence_scope": "ST0F grid, placement, and model color tables; ST0FT executable GTE control writes; SLES map draw CTC2 writes", "note": "No source-confirmed point-light list or per-room RGB table was found in these structures; per-face map color bytes and entity PBD tint remain distinct source inputs."}}
	game = GAME_PATH.read_bytes(); game_base = struct.unpack_from("<I", game, 0xc)[0]; signatures = {0x800AE394: 0xA6A00040, 0x800C4AF4: 0xAE0202A8, 0x800CE408: 0x8450C828, 0x800CE484: 0xAE2202A8}
	if any(struct.unpack_from("<I", game, pc - game_base + 0x30)[0] != word for pc, word in signatures.items()): raise ValueError("GAME player tint instructions differ from the native source trace")
	lighting["sources"]["game_overlay"] = {"file": str(GAME_PATH.relative_to(ROOT)), "sha256": hashlib.sha256(game).hexdigest(), "load_address": hex(game_base)}
	lighting["native_color_pipeline"]["entity_pbd_tint"]["setter_or_room_source"] = "GAME player initializer 0x800C4AF4 and update 0x800CE408..0x800CE484; no room tint source confirmed"
	lighting["native_color_pipeline"]["player_state_tint"] = {"scope": "player only; persistent gameplay state, not confirmed room lighting", "initializer": "GAME 0x800C4AF4 writes RGB128", "guard": "GAME 0x800CE3F8..0x800CE400 skips tint when player+0xB8 low byte is nonzero", "state_address": "0x8009C828", "state_structure": "0x8009C7E8+0x40 signed16", "state_initializer": "GAME 0x800AE394 writes zero", "state_setter": "SLES 0x80043EC0 adds signed delta and clamps to [-32767,32767]", "script_command": "SLES 0x8004E7DC reads big-endian signed16 from script+2/+3 and invokes setter at 0x8004E808", "rgb_formula": "s>16384:192; s>=8192:(s+8192)>>7; s>=-8192:128; s>=-16384:(s+24576)>>7; otherwise64", "source_update": "GAME 0x800CE408..0x800CE484", "target": "player+0x2A8, equal red/green/blue", "new_state_rgb": [128, 128, 128], "instruction_signatures": {hex(pc): hex(word) for pc, word in signatures.items()}}
	depth_cue = map_depth_cue_info(overlay_path.read_bytes(), exe_code, exe_load, len(areas)); lighting["native_color_pipeline"]["depth_cue"] = depth_cue; lighting["native_color_pipeline"]["map_renderer"]["active_room_callbacks"] = sorted({record["map_callback"] for record in depth_cue["area_parameters"]}); lighting["native_color_pipeline"]["map_renderer"]["address_range_scope"] = "Existing range describes the non-depth-cued placement renderer; active room callbacks are selected from native per-area configurations"
	lighting["native_color_pipeline"]["dynamic_corner_modulation"] = {"table_ram": "0x80085120", "table_size": 256, "initializer": "SLES0x800267EC calls0x80015A5C to zero all256bytes", "initial_table": [0] * 256, "initial_offset": [0, 0], "range_loader": "SLES0x800269AC writes config+0x18 to scratch0x1F8000B6", "offset_update": "SLES0x80026DC0..0x80026E04 adds signed config+0x1A/+0x1B to scratch0x1F8000B8/+0xBA each map draw", "coordinate_source": "Signed native world vertex coordinates before GTE transform", "formula": "i=((x+offsetX)>>4)+(y>>3); j=(z+offsetZ)>>4; sample=signed8(table[(signed8(table[i&255])+signed8(table[j&255]))&255])>>1; corner=(baseCorner+trunc(sample*(range-(SZ>>2))/range))&255", "apply_gate": "Face ordering depth<range; original per-cornerSZ and integer division are used", "runtime_table_writer": "Unbound; initialization and draw consumers are source-confirmed", "stage_initial_state": "All13ST0F area records select range1 and offsetStep0; the initialized zero table contributes no modulation"}
	actor_overlay = overlay_path.read_bytes(); player_records = []
	for area in range(len(areas)):
		pointer = struct.unpack_from("<I", actor_overlay, 0x18B70 + area * 4)[0]; start = 0x30 + pointer - 0x800E7000
		for record in range(128):
			offset = start + record * 20; raw = actor_overlay[offset:offset + 20]
			if len(raw) != 20: raise ValueError("Truncated native player actor record list")
			if raw[0] == 255: break
			if raw[2] == 0: player_records.append({"area": area, "source_file_offset": hex(offset), "source_bytes_hex": raw.hex(), "record_flags": raw[0], "initial_render_flags": raw[0] | 8, "depth_cue_exempt": bool((raw[0] | 8) & 0x20)})
	depth_cue["initial_actor_flags"] = {"no_depth_cue_mask": 0x20, "player_constructor": "SLES0x8003D488..0x8003D498 sets player.byte0=record.flags|8", "player_records": player_records, "npc_constructor": "GAME0x800DA49C..0x800DA4A4 copies scripted instance record.flags to actor.byte0; SLES0x8003D504..0x8003D50C copies static instance flags", "runtime_binding": "Use actor-instance flags; the PBD resource flags identify the model bank and do not supply this render exemption", "scope": "Initial source flags; later actor flag changes must preserve the native0x20 exemption"}
	lighting["room_lighting"]["native_depth_cue"] = "Native area flags select depth-cued map and PBD callbacks; ST0F uses black far color and depth_shift0, reaching black at16worldunits"
	OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True); write_output(OUTPUT_PATH, json.dumps(lighting, indent=2) + "\n", encoding="utf-8"); print(f"Wrote {OUTPUT_PATH}: {len(areas)} areas, ST0FT CTC2 registers {overlay['ctc2_control_registers_written']}")

ROOT_GRID_POINTER = 13
ROOT_GRID_BASE = 0x82C4
AREA_POINTER_OFFSET = 0x1A550
AREA_LAYOUT_OFFSET = 0x1A56C
AREA_COUNT = 13
ATLAS_CLUT = 0x7FC0
ATLAS_TPAGE = 0x1D

def sha256(data): return hashlib.sha256(data).hexdigest()

def export_minimap(dat_dir, maps_dir, output_dir):
	stage_path = dat_dir / "ST0F.BIN"; stage_texture_path = dat_dir / "ST0FT.BIN"; root_path = maps_dir / "ST0F_map.bin"
	stage = stage_path.read_bytes(); stage_texture = stage_texture_path.read_bytes(); root = root_path.read_bytes()
	if struct.unpack_from("<I", stage)[0] != 0x0D or struct.unpack_from("<I", stage, 4)[0] != len(root): raise ValueError("ST0F type-0x0D source does not match the extracted root")
	if len(root) != 0x1A6DC or struct.unpack_from("<I", root, 8 + ROOT_GRID_POINTER * 4)[0] * 4 != ROOT_GRID_BASE: raise ValueError("unexpected ST0F root grid table")
	if struct.unpack_from("<4I", stage_texture)[:3] != (1, 0x1AA88, 0x36) or struct.unpack_from("<I", stage_texture, 12)[0] != 0x800E7000: raise ValueError("unexpected ST0FT source header")
	pointers = struct.unpack_from("<14H", stage_texture, AREA_POINTER_OFFSET)
	if pointers[AREA_COUNT] != 0 or not all(pointers[:AREA_COUNT]): raise ValueError("unexpected ST0FT area pointer table")
	areas = []; previous_end = ROOT_GRID_BASE
	for index, pointer in enumerate(pointers[:AREA_COUNT]):
		layout = struct.unpack_from("<4Bhh", stage_texture, AREA_LAYOUT_OFFSET + index * 8)
		origin_x, origin_z, width, height, extra_x, extra_z = layout
		root_offset = ROOT_GRID_BASE + (pointer - pointers[0]) * 8
		if pointer < pointers[0] or root_offset < previous_end or width == 0 or height == 0: raise ValueError(f"invalid area table entry {index}")
		if origin_x + width + 1 != 64 or origin_z + height + 1 != 64: raise ValueError(f"area {index} does not match the stage minimap grid bounds")
		cells = root[root_offset:root_offset + width * height]
		if len(cells) != width * height: raise ValueError(f"area {index} grid span is invalid")
		areas.append({"index": index, "pointer": pointer, "root_offset": root_offset, "origin_x": origin_x, "origin_z": origin_z, "width": width, "height": height, "extra_x": extra_x, "extra_z": extra_z, "tiles": [list(cells[row * width:(row + 1) * width]) for row in range(height)]})
		previous_end = root_offset + len(cells)
	if previous_end != 0x84F4: raise ValueError("ST0F minimap grid span does not end at the mesh directory")
	vram, texture_count = textures(stage_texture_path); atlas_pixels = decode_page(vram, ATLAS_TPAGE, ATLAS_CLUT); atlas = png(256, 256, atlas_pixels)
	output_dir.mkdir(parents=True, exist_ok=True); atlas_path = output_dir / "tiles.png"; write_output(atlas_path, atlas)
	manifest = {"stage": "ST0F", "atlas": "tiles.png", "atlas_size": [256, 256], "atlas_clut": ATLAS_CLUT, "atlas_tpage": ATLAS_TPAGE, "atlas_alpha": "zero palette word transparent; STP bit alpha 128; other nonzero palette words opaque", "atlas_sha256": sha256(atlas), "source": {"root_file": "build/maps/ST0F_map.bin", "root_type": 13, "root_sha256": sha256(root), "root_grid_table_index": ROOT_GRID_POINTER, "root_grid_base": ROOT_GRID_BASE, "root_grid_end": previous_end, "layout_file": "build/disc-assets/DAT/ST0FT.BIN", "layout_sha256": sha256(stage_texture), "area_pointer_offset": AREA_POINTER_OFFSET, "area_layout_offset": AREA_LAYOUT_OFFSET, "texture_sections": texture_count, "arrow_code_file": "build/disc-assets/COMMON/GAME.BIN", "arrow_code_address": "0x800BB5B0", "arrow_call_site": "ST0FT 0x800FCD1C"}, "draw": {"gpu_opcode": "0x7E", "texture_blend_mode": "average", "tile_pixels": 16, "tile_uv_pixels": {"u": "(tile_id & 0x0f) * 16", "v": "tile_id & 0xf0"}, "skip_tile_ids": [255, 92, 93, 94, 95], "visited_rgb": [128, 128, 128], "unvisited_small_area_rgb": [48, 48, 48], "unvisited_area_threshold": 5, "small_area_rule": "areas with index below threshold draw undiscovered tiles dark; larger areas omit undiscovered tiles", "native_clip": {"x": 12, "y": 24, "width": 72, "height": 72}, "map_center_pixels": [0, 0], "tile_origin_pixels": {"x": "-8 * area.width + 16 * column", "y": "8 * area.height - 16 - 16 * row"}, "player_position_source_offsets": {"x": "player+0x12 (signed16)", "z": "player+0x1A (signed16)"}, "player_scroll_pixels": {"x": "signed16(player_x) >> 6", "y": "-(signed16(player_z) >> 6)"}, "tile_draw_base_pixels": {"x": "anchor_x + 36 - scroll_x", "y": "framebuffer_y + 60 - scroll_y", "anchor_x": 12, "framebuffer_y": 0}, "player_marker_pixels": {"x": "(signed16(player_x) >> 6) - center_x", "y": "center_z - (signed16(player_z) >> 6)"}, "player_arrow": {"callback_call_site": "ST0FT 0x800FCD1C", "draw_address": "COMMON/GAME.BIN 0x800BB5B0", "gpu_opcodes": ["0x30", "0x4C"], "heading_delta": "signed16(player+0xF2) - signed16(player+0x2A)", "heading_field_meanings": "unknown", "draw_style": "Gouraud triangle plus closed polyline", "angle_zero_triangle": [[0, 6], [-3, -5], [3, -5]], "cardinal_tip_by_angle": {"0": [0, 6], "1024": [6, 0], "2048": [0, -6], "3072": [-6, 0]}}, "area_extra_fields_used_by_minimap_callback": False}, "areas": areas}
	manifest_path = output_dir / "manifest.json"; write_output(manifest_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	print(f"ST0F minimap: {len(areas)} areas, {sum(area['width'] * area['height'] for area in areas)} cells, {texture_count} texture sections -> {output_dir}")
	return manifest

# Stage init (SLES stage handler) stores the HUD map callback at 0x80078EA8: 0 in ST08T/ST0BT/ST20T; ST2AT/ST2BT area setup installs it only for area < 2 (ST09T/ST29T/ST30T/ST31T/ST3BT/ST3CT: every area).
BITMAP_MINIMAP_HUD_AREAS = {"ST08": (), "ST0B": (), "ST20": (), "ST2A": (0, 1), "ST2B": (0, 1)}
def export_bitmap_minimaps(dat_dir, output_dir, stages=None):
	bindings = {"ST08": 0, "ST09": 1, "ST0B": 2, "ST20": 8, "ST30": 3, "ST31": 6, "ST29": 9, "ST2A": 11, "ST2B": 13, "ST3B": 15, "ST3C": 17}; result = {}; source_path = Path(dat_dir) / "ST09T.BIN"; source_data = source_path.read_bytes(); source_base = read_u32(source_data, 12)
	for stage, first_index in bindings.items():
		if stages and stage not in stages: continue
		overlay_path = Path(dat_dir) / (stage + "T.BIN"); manifest_path = ROOT / "assets/levels" / stage / "manifest.json"
		if not overlay_path.is_file() or not manifest_path.is_file(): continue
		manifest = json.loads(manifest_path.read_text()); root = (ROOT / "build/maps" / (stage + "_map.bin")).read_bytes(); areas = []; vram, _ = textures(overlay_path); target = Path(output_dir) / stage; target.mkdir(parents=True, exist_ok=True)
		for source in manifest["areas"]:
			index = int(source["index"]); map_index = first_index + (index if stage not in ("ST08", "ST09", "ST0B", "ST20") else 0)
			if map_index >= 22: raise ValueError(f"{stage}:{index} exceeds original HUD minimap table")
			clut, tpage = struct.unpack_from("<2H", source_data, 48 + 0x800F2FA4 - source_base + map_index * 4); offset = list(struct.unpack_from("<4h", source_data, 48 + 0x800F2EF4 - source_base + map_index * 8)); atlas = "bitmap_%02d.png" % map_index; write_output(target / atlas, texture_page(vram, clut, tpage)); min_x, min_z, max_x, max_z = root[struct.unpack_from("<I", root, 8 + index * 4)[0] * 4:][:4]; center = [(((min_x + max_x) >> 1) - 64) * 8, (((min_z + max_z) >> 1) - 64) * 8]; areas.append({"index": index, "hud": index in BITMAP_MINIMAP_HUD_AREAS.get(stage, (index,)), "width": 256, "height": 256, "native_center": center, "bitmap_origin": [center[0] - offset[2] - ((max_x - min_x + 1) >> 1), center[1] - offset[3] + ((max_z - min_z + 1) >> 1)], "source_bounds": [min_x, min_z, max_x, max_z], "source_offset": offset, "atlas": atlas, "native_map_index": map_index, "tpage": hex(tpage), "clut": hex(clut)})
		write_output(target / "manifest.json", json.dumps({"stage": stage, "mode": "bitmap", "atlas": areas[0]["atlas"], "source": {"overlay": overlay_path.name, "dispatch_source": "ST09T800F1434/800E70B4", "hud_source": "HUD callback word 0x80078EA8 (GAME0x800BB3A4 calls it each frame): ST08T/ST0BT/ST20T store 0; ST2AT/ST2BT area setup stores it for area<2 only", "offset_table": "0x800F2EF4", "texture_table": "0x800F2FA4", "native_units_per_pixel": 64}, "areas": areas}, indent=2) + "\n", encoding="utf-8"); result[stage] = len(areas)
	return result
FLUTTER_MAP_STAGES = {"ST04": 0, "ST05": 3, "ST06": 6, "ST07": 12}
# ST04T-ST07T draw the Flutter deck plans (renderer 0x800EF16C, sprite lists via 0x800EF73C) from SUBMAP page 7; the marker rules are the three table functions 0x800EF5A4/5F4/6A8 (verified by running them in Unicorn).
FLUTTER_MAP_RULES = [{"source": "0x800EF5A4", "y_by_z_cell": {"63": 12, "64": -12}, "default_y": -44}, {"source": "0x800EF5F4", "y_by_z_cell": {"63": -8, "64": -24}, "x_by_x_cell": {"62": -24, "63": -8, "64": 8}, "default_x": 24, "default_y": -40}, {"source": "0x800EF6A8", "y_by_z_cell": {"63": -24}, "x_by_x_cell": {"62": -24, "63": -8, "64": 8}, "default_x": 24, "default_y": -40}]
def export_flutter_map(dat_dir, output_dir):
	signature = struct.pack("<hhBBBB", 0, 48, 0, 3, 255, 0) + struct.pack("<hhBBBB", 24, 0, 0, 3, 0, 0); reference = None
	for stage in FLUTTER_MAP_STAGES:
		overlay = (Path(dat_dir) / (stage + "T.BIN")).read_bytes(); table = overlay.find(signature)
		if table < 12 or overlay.find(signature, table + 1) >= 0: raise ValueError(f"{stage}T Flutter map room table not found")
		base = read_u32(overlay, 12); entries = [dict(zip(("x", "y", "deck", "extra", "rule", "variant"), struct.unpack_from("<hhBBBB", overlay, table + 8 * index))) for index in range(18)]; decks = []
		for pointer in struct.unpack_from("<3I", overlay, table - 12):
			cursor = 0x30 + pointer - base; sprites = []
			while struct.unpack_from("<h", overlay, cursor)[0] != 0x7FFF:
				x, y, uv, size = struct.unpack_from("<hhHH", overlay, cursor); sprites.append({"x": x, "y": y, "u": uv & 255, "v": uv >> 8, "width": size & 255, "height": size >> 8}); cursor += 8
			decks.append(sprites)
		if reference is None: reference = (entries, decks)
		elif reference != (entries, decks): raise ValueError(f"{stage}T Flutter map tables differ from ST04T")
	submap = (Path(dat_dir).parent / "COMMON/SUBMAP.BIN").read_bytes(); vram = bytearray(1024 * 512 * 2); texture_uploads(submap[0x77800:0x77800 + 0x11000], vram, "SUBMAP.BIN"); output = Path(output_dir)
	write_output(output / "decks.png", texture_page(vram, 511 * 64, 8 | (1 << 7)))
	write_output(output / "manifest.json", json.dumps({"schema": 1, "atlas": "decks.png", "source": {"overlays": [stage + "T.BIN" for stage in FLUTTER_MAP_STAGES], "renderer": "0x800EF16C", "sprite_renderer": "0x800EF73C", "room_table": "0x800F4414 (ST04T)", "deck_lists": "0x800F4408 (ST04T)", "texture": "COMMON/SUBMAP.BIN section 0x77800, tpage 0x88, CLUT 0x7FC0", "entry_index": "stage base + area index (ST04 0, ST05 3, ST06 6, ST07 12); deck list = deck + variant", "marker": "entry x,y in deck coordinates, replaced by the rule function when rule != 255; z/x cells = ((player integer position + 0x8000) >> 9)"}, "stages": FLUTTER_MAP_STAGES, "entries": reference[0], "decks": reference[1], "rules": FLUTTER_MAP_RULES}, indent=1) + "\n", encoding="utf-8")
	return {"decks": len(reference[1]), "rooms": 18}
def minimap_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--maps-dir", type=Path, default=Path("build/maps")); parser.add_argument("--output-dir", type=Path, default=Path("assets/minimap/ST0F")); args = parser.parse_args(); export_minimap(args.dat_dir, args.maps_dir, args.output_dir)

def export_floor_shapes(path, variants=None):
	stage = Stage(Path(path).read_bytes()); result = {}
	for area in range(len(stage.grids)):
		parsed = stage.area(area)
		if parsed is None: continue
		tiles, placements = parsed; boxes = []
		for placement in placements:
			_, model, flags, height, x, z = stage.placements[placement]; _, header, directory = stage.directories[model]; variant = stage.base + (directory & 65535) * 4 + (variants.get(placement, flags & 3) if variants else flags & 3) * 12; pointer = struct.unpack_from("<H", stage.data, variant + 2)[0] * 4 + stage.base; count = stage.data[variant + 6]; offset_x = (x << 9) - (0x7E00 if header & 0x10000000 else 0x7F00); offset_z = (z << 9) - (0x7E00 if header & 0x20000000 else 0x7F00); offset_y = 0x400 - tiles[(x, z)][6] * 16 - ((height & 0x7F00) >> 4)
			for index in range(count):
				offset = pointer + index * 16; values = struct.unpack_from("<6h2H", stage.data, offset)
				boxes.append({"x": [values[0] + offset_x, values[1] + offset_x], "z": [values[2] + offset_z, values[3] + offset_z], "y": [values[4] + offset_y, values[5] + offset_y], "kind": values[6], "mask": values[7], "placement": placement, "source_offset": hex(offset), "contact_raw": [int((values[0] + values[1]) / 2) + offset_x, int((values[4] + values[5]) / 2) + offset_y, int((values[2] + values[3]) / 2) + offset_z]})
		walls = {key for key, data in tiles.items() if read_u16(data, 0) & 0x4800 != 0x800 and read_u16(data, 0) & 0x400}; edge = {key for key in walls if any((key[0] + dx, key[1] + dz) not in walls for dx in (-1, 0, 1) for dz in (-1, 0, 1))}; wall_rects = []
		for key in sorted(edge, key=lambda cell: (cell[1], cell[0])):
			if key not in edge: continue
			x, z = key; width = 1
			while (x + width, z) in edge: width += 1
			height = 1
			while all((x + i, z + height) in edge for i in range(width)): height += 1
			for i in range(width):
				for j in range(height): edge.discard((x + i, z + j))
			wall_rects.append([(x << 9) - 0x8000, ((x + width) << 9) - 0x8000, (z << 9) - 0x8000, ((z + height) << 9) - 0x8000])
		result[str(area)] = {"grid": {"%d:%d" % coordinates: list(data) for coordinates, data in tiles.items()}, "boxes": boxes, "walls": wall_rects, "wall_source": "GAME0x800B36E8/0x800B13FC: cell flags&0x4800!=0x800 and flags&0x400 block actor classes with mask&3 (player=1,friendly=2; enemy 4 and 8 pass) via shape0 box y+-0x4000; class mask GAME0x800B786C", "source": "SLES0x80038D20 placement collision directory; GAME0x800B13FC floor selector; GAME0x800B5658 shape0 footprint"}
	return result

def floor_collision_manifest(path):
	path = Path(path); result = {area: {"boxes": source["boxes"], "walls": source["walls"], "wall_source": source["wall_source"], "source": source["source"], "slope_source": "GAME0x800B1C48;kind10:+Z,11:-Z,12:+X,13:-X;B1EA8 integer interpolation;B2868 upper surface"} for area, source in export_floor_shapes(path).items()}
	for (stage_name, area), rules in AREA_COLLISION_VARIANTS.items():
		if stage_name != path.stem.upper(): continue
		stage = Stage(path.read_bytes()); tiles, _ = stage.area(area); overlay = path.with_name(stage_name + "T.BIN").read_bytes()
		for rule in rules:
			check_overlay_words(overlay, rule["overlay_words"], stage_name + " collision variant"); placement = read_u16(tiles[tuple(rule["tile"])], 0) & 0x7FF; alternate = export_floor_shapes(path, {placement: rule["variant"]})[str(area)]["boxes"]
			result[str(area)].setdefault("placement_variants", []).append({"placement": placement, "variant": rule["variant"], "predicate": rule["predicate"], "boxes": [record for record in alternate if record["placement"] == placement], "source": rule["source"]})
	return result

def bind_route_contacts(routes, floors):
	for route in routes:
		matches = [box for box in floors.get(str(route["source_area"]), {}).get("boxes", []) if box["kind"] >= 0x100 and box["contact_raw"] == route["source_transform_raw"][:3]]
		route["native_contacts"] = []
		for box in matches:
			contact = {**box, "type": box["kind"] >> 8, "automatic": box["kind"] == 0xF00, "probe_forward_raw": -64 if box["mask"] & 0x8000 else 0, "source_consumer": "GAME0x800B8588;type15:0x800B8134->0x800B8460"}
			if contact["type"] == 2: contact["native_probe"] = {"source": "GAME0x800B8588..0x800B8750; SLES0x8005FE44/0x8005F4D4", "player_position_fields": ["+0x12 X", "+0x16 Y", "+0x1A Z"], "position_scale": "signed16 native units at 1/256 map unit", "sweep_local_raw": [0, 0, -64], "sweep_yaw_source": "player+0x2A through SLES0x8005FE44", "vertical_test": "player+0x16 remains unchanged across the forward sweep; no vertical capsule half-height expansion in this probe"}
			route["native_contacts"].append(contact)
	return routes

NATIVE_SCRIPTED_INTERACTIONS = {"ST04": {(1, 0): (0x800E8190, 0x800E84C4, 2, False), (96, 0): (0x800E9DB0, 0x800EA15C, 0, False)}, "ST08": {(0, 0): (0x800E78CC, 0x800E7D4C, 0, False), (0, 1): (0x800E93EC, 0x800E9A1C, 0, True), (0, 2): (0x800EBFFC, 0x800EC58C, 0, True), (1, 0): (0x800EA4F4, 0x800EA828, 2, False)}, "ST09": {(0, 0): (0x800E81EC, 0x800E866C, 0, False)}, "ST0A": {(0, 0): (0x800E8920, 0x800E8DA0, 0, False)}, "ST0C": {(0, 0): (0x800E752C, 0x800E79AC, 0, False)}, "ST47": {(0, 0): (0x800E8600, 0x800E8A80, 0, False)}}
NATIVE_SCRIPTED_INTERACTIONS.update({"ST0B": {(0, 0): (0x800E8174, 0x800E85F4, 0, False)}, "ST0D": {(0, 0): (0x800E74A4, 0x800E7924, 0, False)}, "ST17": {(0, 0): (0x800E9D00, 0x800EA180, 0, False)}, "ST18": {(0, 0): (0x800E84C4, 0x800E8764, 0, False)}, "ST1B": {(0, 0): (0x800E78F0, 0x800E7D70, 0, False)}, "ST1F": {(0, 0): (0x800E80D4, 0x800E8554, 0, False)}, "ST20": {(0, 0): (0x800E8494, 0x800E8914, 0, False)}, "ST24": {(0, 0): (0x800E7944, 0x800E7DBC, 0, False)}, "ST25": {(0, 0): (0x800E7FFC, 0x800E847C, 0, False)}, "ST29": {(0, 0): (0x800E7CB4, 0x800E8134, 0, False)}, "ST3B": {(0, 0): (0x800E8E24, 0x800E92A4, 0, False)}, "ST3C": {(0, 0): (0x800E8A2C, 0x800E8EAC, 0, False)}, "ST3D": {(0, 0): (0x800E77C0, 0x800E7C40, 0, False)}, "ST3E": {(0, 0): (0x800E799C, 0x800E7E1C, 0, False)}, "ST3F": {(0, 0): (0x800E77FC, 0x800E7C7C, 0, False)}})
NATIVE_INTERACTION_TARGETS = {"ST08": {(0, 0): (0x800F2928, 0x800F2934), (0, 1): (0x800F2C50, 0x800F2C50), (1, 0): (0x800F32A4, 0x800F32A4)}, "ST09": {(0, 0): (0x800F2750, 0x800F275C)}, "ST0A": {(0, 0): (0x800EFA8C, 0x800EFA98)}, "ST0C": {(0, 0): (0x800EAED8, 0x800EAEE4)}, "ST47": {(0, 0): (0x800ED074, 0x800ED080)}}
NATIVE_INTERACTION_TARGETS.update({"ST0B": {(0, 0): (0x800EF45C, 0x800EF468)}, "ST0D": {(0, 0): (0x800F084C, 0x800F0858)}, "ST17": {(0, 0): (0x80106F48, 0x80106F54)}, "ST18": {(0, 0): (0x801075E4, 0x801075E4)}, "ST1B": {(0, 0): (0x800F0280, 0x800F028C)}, "ST1F": {(0, 0): (0x801012C8, 0x801012D4)}, "ST20": {(0, 0): (0x800F2088, 0x800F2094)}, "ST24": {(0, 0): (0x800F2454, 0x800F2460)}, "ST25": {(0, 0): (0x800F9F44, 0x800F9F50)}, "ST29": {(0, 0): (0x800F70A8, 0x800F70B4)}, "ST3B": {(0, 0): (0x800FE524, 0x800FE530)}, "ST3C": {(0, 0): (0x800FEA74, 0x800FEA80)}, "ST3D": {(0, 0): (0x800EB0B8, 0x800EB0C4)}, "ST3E": {(0, 0): (0x800ED614, 0x800ED620)}, "ST3F": {(0, 0): (0x800EF948, 0x800EF954)}})
NATIVE_SCRIPTED_INTERACTIONS.update({"ST2C": {(0, 0): (0x800E7454, 0x800E78D4, 0, False)}})
NATIVE_INTERACTION_TARGETS.update({"ST2C": {(0, 0): (0x800EA884, 0x800EA890)}})
NATIVE_SCRIPTED_INTERACTIONS["ST09"][(0, 1)] = (0x800E9D0C, 0x800EA33C, 0, True)
NATIVE_SCRIPTED_INTERACTIONS["ST0B"][(1, 0)] = (0x800E9C94, 0x800E9FC8, 2, False)
NATIVE_INTERACTION_TARGETS["ST0B"][(1, 0)] = (0x800EFD9C, 0x800EFD9C)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST10", {})[(1, 0)] = (0x800E7A4C, 0x800E7D80, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST10", {})[(1, 0)] = (0x800F8348, 0x800F8348)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST17", {})[(1, 0)] = (0x800E7C24, 0x800E7F58, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST17", {})[(1, 0)] = (0x80106E80, 0x80106E80)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST1D", {})[(1, 0)] = (0x800E7B00, 0x800E7E34, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST1D", {})[(1, 0)] = (0x800FCB4C, 0x800FCB4C)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST1F", {})[(1, 0)] = (0x800E9BF4, 0x800E9F28, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST1F", {})[(1, 0)] = (0x80101C08, 0x80101C08)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST24", {})[(1, 0)] = (0x800E945C, 0x800E9790, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST24", {})[(1, 0)] = (0x800F2D94, 0x800F2D94)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST3C", {})[(1, 0)] = (0x800EA54C, 0x800EA880, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST3C", {})[(1, 0)] = (0x800FF3B4, 0x800FF3B4)
NATIVE_SCRIPTED_INTERACTIONS.setdefault("ST3F", {})[(1, 0)] = (0x800E931C, 0x800E9650, 2, False)
NATIVE_INTERACTION_TARGETS.setdefault("ST3F", {})[(1, 0)] = (0x800F0288, 0x800F0288)
NATIVE_SCRIPTED_INTERACTIONS["ST40"] = {(0, 0): (0x800E84E4, 0x800E8964, 0, False), (1, 0): (0x800EA004, 0x800EA338, 2, False)}
NATIVE_INTERACTION_TARGETS["ST40"] = {(0, 0): (0x800FD564, 0x800FD570), (1, 0): (0x800FDEA4, 0x800FDEA4)}
for _stage, _callback, _target in (("ST14", 0x800E7D84, 0x80106720), ("ST23", 0x800E7708, 0x800F05F8), ("ST35", 0x800E7994, 0x800FA274), ("ST48", 0x800E7844, 0x800F9AAC), ("ST2F", 0x800E8064, 0x8010360C), ("ST4C", 0x800E77E8, 0x800FB364)): NATIVE_SCRIPTED_INTERACTIONS[_stage] = {(1, 0): (_callback, _callback + 0x334, 2, False)}; NATIVE_INTERACTION_TARGETS[_stage] = {(1, 0): (_target, _target)}
NATIVE_SCRIPTED_INTERACTIONS["ST24"][(11, 0)] = (0x800EB2BC, 0x800EB318, 0, False); NATIVE_INTERACTION_TARGETS["ST24"][(11, 0)] = (0x800F4CD0, 0x800F4CDC)
NATIVE_SCRIPTED_INTERACTIONS["ST3B"][(11, 1)] = (0x800ECAE8, 0x800ECB44, 0, False); NATIVE_INTERACTION_TARGETS["ST3B"][(11, 1)] = (0x800FE8E8, 0x800FE8F4)
for _stage, _callback, _target in (("ST4F", 0x800F2AF4, 0x800FEC78), ("ST50", 0x800EFE68, 0x800FF2DC), ("ST51", 0x800EA190, 0x800EEE80)): NATIVE_SCRIPTED_INTERACTIONS[_stage] = {(111, 0): (_callback, _callback + 0x304, 0x12, False)}; NATIVE_INTERACTION_TARGETS[_stage] = {(111, 0): (_target, _target)}
def bind_scripted_interactions(stage, records, overlay, source_key="source_bytes_hex", address_key="source_record_ram"):
	base = read_u32(overlay, 12)
	for record in records:
		raw = bytes.fromhex(record[source_key]); profile = NATIVE_SCRIPTED_INTERACTIONS.get(stage, {}).get((raw[4], raw[5])) if len(raw) == 20 and raw[2] == 0x20 else None
		if profile is None: continue
		targets = NATIVE_INTERACTION_TARGETS.get(stage, {}).get((raw[4], raw[5]))
		if targets and targets[0] != targets[1] and raw[11] == 255: record.pop("native_interaction", None); continue
		actor_callback, request, kind, signed = profile; offset = 48 + request - base
		if not 48 <= offset <= len(overlay) - 8 or read_u32(overlay, offset) != 0x0C02F8B8: raise ValueError(f"{stage} scripted interaction source call differs at {request:#x}")
		if not any(read_u32(overlay, at) >> 26 == (0x20 if signed else 0x24) and read_u32(overlay, at) & 65535 == 0x0F for at in range(offset - 20, offset, 4)): raise ValueError(f"{stage} scripted interaction index load differs at {request:#x}")
		record["native_private_raw"] = list(raw[8:12]); record["native_interaction"] = {"stage": stage, "actor_class": raw[4], "actor_state": raw[5], "actor_callback": hex(actor_callback), "request_call": hex(request), "request_api": "0x800BE2E0", "request_kind": kind | ((raw[9] >> 2) & 0x10) if not signed else kind, "message_call": "0x800BDCF8", "message_index": raw[11] - 256 if signed and raw[11] & 128 else raw[11], "index_source": ("signed" if signed else "unsigned") + " actor+0x0F copied from record byte0x0B", "window": 0, "selected_actor_gate": "GAME0x800D0154 requires player+1D0 low24bits equal actor and bit24 set", "bank_id": "0x8010C000", "source_record_ram": record[address_key]}
		if targets:
			pointer = targets[bool(raw[9] & 8)]; descriptor = list(struct.unpack_from("<6h", overlay, 48 + pointer - base)); record["native_interaction"].update(target_descriptor_raw=descriptor, target_descriptor_source=hex(pointer), target_flags60=1, target_selector_source="GAME0x800CC2F0/0x800CC5B4", target_criteria={"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False})
	return records

STAGE_NAMES = {"ST00": "Debug area", "ST01": "World map", "ST02": "Sulphur-Bottom opening", "ST03": "Flutter opening", **dict.fromkeys(["ST04", "ST05", "ST06", "ST07"], "Flutter"), **dict.fromkeys(["ST08", "ST09", "ST0A", "ST0B", "ST0C", "ST47"], "Yosyonke City"), **dict.fromkeys(["ST0D", "ST0E"], "Calinca Tundra"), "ST0F": "Abandoned Mine", **dict.fromkeys(["ST10", "ST11", "ST1D"], "Forbidden Island"), **dict.fromkeys(["ST12", "ST13", "ST14"], "Manda Ruins"), **dict.fromkeys(["ST15", "ST16", "ST18", "ST19"], "Nino Island"), "ST17": "King Glydon", **dict.fromkeys(["ST1A", "ST1B"], "Ruminoa City"), "ST1C": "Forbidden Island / Sulphur-Bottom scenes", "ST1E": "Flutter fire", **dict.fromkeys(["ST1F", "ST30", "ST31"], "Glyde's Base"), "ST20": "Kito Village", **dict.fromkeys(["ST21", "ST22", "ST23"], "Calbania Plains"), "ST24": "Pokte Plains", "ST25": "Pokte Village", **dict.fromkeys(["ST26", "ST27", "ST28", "ST33", "ST34"], "Saul Kada Ruins"), **dict.fromkeys(["ST29", "ST2A", "ST2B", "ST2C", "ST3B", "ST3C"], "Kimotoma City"), **dict.fromkeys(["ST2D", "ST2E", "ST2F"], "Calinca Ruins"), "ST32": "Pokte Mayor's Home", **dict.fromkeys(["ST35", "ST36", "ST37", "ST38"], "Nino Ruins"), "ST39": "Flutter new-game scene", "ST3A": "Sulphur-Bottom / Forbidden Island scenes", **dict.fromkeys(["ST3D", "ST3E", "ST3F", "ST4B"], "Sulphur-Bottom"), "ST40": "Elysium", **dict.fromkeys(["ST41", "ST42"], "Defense Area"), **dict.fromkeys(["ST43", "ST44", "ST45", "ST4C", "ST58", "ST5C"], "Mother Zone"), "ST46": "Nino Island / Flutter scenes", "ST48": "Saul Kada Desert", "ST49": "Flutter / Dropship scenes", "ST4A": "Tutorial", "ST4D": "Guild Ruins", **dict.fromkeys(["ST4E", "ST51"], "Pokte Caverns"), "ST4F": "Kito Caverns", "ST50": "Kimotoma Caverns", "ST52": "Sera / Master scenes", "ST53": "Calinca Tundra scenes", "ST54": "Rocket launch ending", "ST55": "License Test Ruins", "ST56": "Master's Room", "ST57": "Game credits", "ST59": "Manda Circuit", "ST5A": "Calinca Circuit", "ST5B": "Saul Kada Circuit"}
LOCATIONS = (("ST04", 0, "Flutter Bridge"), ("ST04", 1, "Flutter Deck 1"), ("ST04", 2, "Flutter Lab"), ("ST05", 0, "Flutter MegaMan's Room"), ("ST05", 1, "Flutter Roll's Room"), ("ST05", 2, "Flutter Barrell's Room"), ("ST06", 0, "Flutter Deck 2"), ("ST06", 1, "Flutter Toilet"), ("ST06", 2, "Flutter Storage"), ("ST06", 3, "Flutter Living Room"), ("ST06", 4, "Flutter Kitchen"), ("ST06", 5, "Flutter Bathroom"), ("ST07", 0, "Flutter Deck 3"), ("ST07", 1, "Flutter Hangar"), ("ST07", 2, "Flutter Engine Room"))
def location_name(stage, area):
	names = json.loads((Path(__file__).with_name("location_names.json")).read_text(encoding="utf-8"))["areas"] if (Path(__file__).with_name("location_names.json")).is_file() else {}
	name = names.get(stage, {}).get(str(area))
	if not name: return None
	common = 0; words = name.split(); stage_words = STAGE_NAMES.get(stage, "").split()
	while common < min(len(words), len(stage_words)) and words[common] == stage_words[common]: common += 1
	remainder = " ".join(words[common:]).removeprefix("- ")
	return remainder if common and remainder and not remainder.isdigit() else name
STAGE_BINDINGS = {"ST04": {"name": "Flutter", "area_count": 3, "routes": 0x800EFB94, "actors": 0x800EFA48, "actor_caller": "0x800E7570", "actor_section": 0x6800, "roles": {71: "bridge_steering_wheel"}, "controllers": {71: "ST04T0x800E9C98 reads actor+C/D and continues3F768; callback-to-class47 binding still unresolved"}}, "ST05": {"name": "Flutter", "area_count": 3, "routes": 0x800E9B04, "actors": 0x800E9A30, "actor_caller": "0x800E71E4", "actor_section": 0x6800}, "ST06": {"name": "Flutter", "area_count": 6, "routes": 0x800E8D10, "actors": 0x800E8B04, "actor_caller": "0x800E71B4", "actor_section": 0x6800}, "ST07": {"name": "Flutter", "area_count": 3, "routes": 0x800E88CC, "actors": 0x800E87B0, "actor_caller": "0x800E71B4", "actor_section": 0x6800}}
STAGE_BINDINGS["ST08"] = {"area_count": 2, "routes": 0x800F200C, "actors": 0x800F1F20, "actor_caller": "0x800E74BC", "actor_section": 0x8800}
BASE = 0x800E7000
SHARED_TEXTURES = ("COMMON/PL00T.BIN",)

def digest(data): return hashlib.sha256(data).hexdigest()
def native_constants(words):
	registers = {0: 0}; call_delay = -1
	for word in words:
		if call_delay == 0:
			for register in [1, *range(2, 16), 24, 25, 31]: registers.pop(register, None)
			call_delay = -1
		op = word >> 26; rs = word >> 21 & 31; rt = word >> 16 & 31; rd = word >> 11 & 31; immediate = word & 65535; signed = immediate - 65536 if immediate & 32768 else immediate; value = None; destination = None; left = registers.get(rs); right = registers.get(rt)
		if op == 15: destination = rt; value = immediate << 16
		elif op in (9, 13): destination = rt; value = ((left + signed) & 0xFFFFFFFF if op == 9 else left | immediate) if left is not None else None
		elif op == 0 and word & 63 in (0x21, 0x25): destination = rd; value = ((left + right) & 0xFFFFFFFF if word & 63 == 0x21 else left | right) if left is not None and right is not None else None
		elif op == 0 and word & 63 == 0: destination = rd; value = right << (word >> 6 & 31) & 0xFFFFFFFF if right is not None else None
		elif op in (*range(8, 15), *range(0x20, 0x28)): destination = rt
		if destination is not None and destination != 0: registers[destination] = value
		if op == 3 or op == 0 and word & 63 == 9: call_delay = 1
		elif call_delay == 1: call_delay = 0
	return registers
def native_combat_policy(data):
	base = read_u32(data, 12); size = min(read_u32(data, 4), len(data) - 48); words = struct.unpack_from(f"<{size // 4}I", data, 48); policies = []
	for index, word in enumerate(words[:-1]):
		if word != 0x0C033D2A or words[index + 1] >> 26 != 0x2B or words[index + 1] & 65535 != 0x8FA4: continue
		mode = native_constants(words[max(0, index - 12):index + 2]).get(4)
		if mode not in (0, 1, 2): continue
		policies.append({"weapon_mode": mode, "buster_allowed": mode != 0, "primary": 0 if mode == 0 else "equipped" if mode == 1 else 15, "secondary": 1 if mode in (0, 2) else "equipped", "source_call": hex(base + index * 4), "source_api": "GAME0x800CF4A8 writes player19E/18C/18D; SLES0x80023438 selects arm descriptors", "scope": "Weapon mode; ordinary normal-hand actions are not disabled by this field"})
	return policies[0] if len(policies) == 1 else None
def native_automatic_walk(data):
	base = read_u32(data, 12); size = min(read_u32(data, 4), len(data) - 48); words = struct.unpack_from(f"<{size // 4}I", data, 48); tables = set()
	for index, word in enumerate(words):
		if word >> 26 != 0x2B or word & 65535 != 0x8E7C: continue
		registers = native_constants(words[max(0, index - 8):index + 1]); address = registers.get(word >> 16 & 31)
		if registers.get(word >> 21 & 31) == 0x80080000 and address is not None: tables.add(address)
	if len(tables) != 1: return None
	table = next(iter(tables)); offset = 48 + table - base + 13 * 4
	if not 48 <= offset <= len(data) - 4: return None
	callback = read_u32(data, offset); index = (callback - base) // 4
	if not 0 <= index < len(words) - 7: return None
	states = native_constants(words[index:index + 7]).get(3); offset = 48 + states - base if states is not None else -1
	if not 48 <= offset <= len(data) - 4: return None
	constructor = read_u32(data, offset); start = (constructor - base) // 4
	if not 0 <= start < len(words): return None
	for index in range(start, min(start + 240, len(words) - 1)):
		if words[index] != 0x0C030317: continue
		timeline = native_constants(words[max(start, index - 8):index + 2]).get(5); offset = 48 + timeline - base if timeline is not None else -1
		if not 48 <= offset <= len(data) - 16: continue
		flag, parameter, ticks, movement = struct.unpack_from("<BBHI", data, offset)
		if flag != 0 or parameter != 0 or data[offset + 8] != 255: continue
		move_index = (movement - base) // 4
		if not 0 <= move_index < len(words) - 10: continue
		for call in range(move_index, move_index + 10):
			if words[call] != 0x0C033421: continue
			arguments = native_constants(words[move_index:call + 2])
			if arguments.get(5) != 0 or arguments.get(6) != 0 or arguments.get(7) is None: continue
			step = arguments[7]; step = step - 0x100000000 if step & 0x80000000 else step
			return {"ticks": ticks, "local_step_raw": [0, 0, step], "native_fraction_bits": 4, "world_step": step / 4096.0, "control": 1, "tick_rate": 25, "source_table": hex(table), "source_callback": hex(callback), "source_constructor": hex(constructor), "source_timeline": hex(timeline), "source_movement": hex(movement), "source_translation": "GAME0x800CD084->SLES0x800417AC/41A54: rotate localStep<<12 and add to actor16.16; collision and floor each tick", "source_clock": "SLES03556 PAL gameplay divider2:50/2 ticks per second"}
	return None
def native_area_tables(data):
	base = read_u32(data, 12); size = min(read_u32(data, 4), len(data) - 48); words = struct.unpack_from(f"<{size // 4}I", data, 48); result = {"routes": [], "actors": []}
	for index, word in enumerate(words):
		if not (word >> 26 == 0x2B and word & 65535 == 0x8FA4 or word == 0x0C00F4FE): continue
		registers = {0: 0, 28: 0x8007890C}; pending_call = False
		for at in range(max(0, index - 160), index + 1):
			instruction = words[at]; op = instruction >> 26; rs = instruction >> 21 & 31; rt = instruction >> 16 & 31; rd = instruction >> 11 & 31; immediate = instruction & 65535; signed = immediate - 65536 if immediate & 0x8000 else immediate; value = None; destination = rd if op == 0 and instruction & 63 not in (8, 9) else rt if op in (*range(8, 16), *range(0x20, 0x28)) else None; left = registers.get(rs); right = registers.get(rt)
			if op == 15: destination = rt; value = immediate << 16
			elif op in (9, 13): destination = rt; value = ((left + signed) & 0xFFFFFFFF if op == 9 else left | immediate) if isinstance(left, int) else None
			elif op == 0 and instruction & 63 in (0x21, 0x25):
				destination = rd
				if isinstance(left, int) and isinstance(right, int): value = (left + right if instruction & 63 == 0x21 else left | right) & 0xFFFFFFFF
				elif left == 0: value = right
				elif right == 0: value = left
				elif instruction & 63 == 0x21 and isinstance(left, tuple) and left[0] == "area_offset" and isinstance(right, int): value = ("area_address", right, left[1])
				elif instruction & 63 == 0x21 and isinstance(right, tuple) and right[0] == "area_offset" and isinstance(left, int): value = ("area_address", left, right[1])
			elif op == 0 and instruction & 63 == 0:
				destination = rd; shift = instruction >> 6 & 31; value = (right << shift) & 0xFFFFFFFF if isinstance(right, int) else ("area_offset", 1 << shift) if right == ("area",) else None
			elif op in (0x23, 0x24):
				destination = rt
				if op == 0x24 and isinstance(left, int) and (left + signed) & 0xFFFFFFFF == 0x8009C7F9: value = ("area",)
				elif op == 0x23 and isinstance(left, tuple) and left[0] == "area_address" and left[2] == 4 and signed == 0: value = ("area_table", left[1])
				elif isinstance(left, int) and 0 <= left + signed - base <= size - (4 if op == 0x23 else 1): value = read_u32(data, 48 + left + signed - base) if op == 0x23 else data[48 + left + signed - base]
			if destination is not None and destination != 0: registers[destination] = value
			if at == index:
				selected = registers.get(4) if word == 0x0C00F4FE else registers.get(rt)
				if isinstance(selected, tuple) and selected[0] == "area_table" and (word == 0x0C00F4FE or isinstance(left, int) and (left + signed) & 0xFFFFFFFF == 0x80078FA4): result["actors" if word == 0x0C00F4FE else "routes"].append({"pointer_ram": selected[1], "source_call": hex(base + at * 4)})
			if pending_call:
				for register in [1, *range(2, 16), 24, 25, 31]: registers.pop(register, None)
			pending_call = op == 3 or op == 0 and instruction & 63 == 9
	return result
def texture_upload_records(source, name):
	uploads = []; offset = 0
	while offset <= len(source) - 48:
		kind, size = struct.unpack_from("<2I", source, offset)
		if kind not in (2, 3):
			if kind in (1, 0xA) and size and offset + 0x30 + size <= len(source): offset = max(offset + 0x400, ((offset + 0x30 + size + 0x3FF) // 0x400) * 0x400); continue
			offset += 0x400; continue
		px, py, colors, palettes, x, y, width, raw_height = struct.unpack_from("<8H", source, offset + 12); palette_size = colors * palettes * 2; image_size = width * raw_height * 2; sector_count = read_u32(source, offset + 8); image_rect_y = y; height = raw_height; palette_start = offset + 0x30; image_start = palette_start + palette_size; layout = "contiguous"
		if kind == 2 and sector_count > 1 and offset + 0x30 + size == offset + sector_count * 0x800 and palette_size and width and raw_height and width * raw_height * 2 == (sector_count - 1) * 0x800 and palette_size <= 0x800 - 0x30:
			image_size = (sector_count - 1) * 0x800; palette_start = offset + 0x30; image_start = offset + 0x800; layout = "clut_first_sector_image_following_sectors"
		expected = palette_size + image_size; section_end = offset + 0x30 + size
		if not expected or not 0 < expected <= 1024 * 512 * 2 or px + colors > 1024 or py + palettes > 512 or x + width > 1024 or image_rect_y + height > 512: offset += 0x400; continue
		if kind == 3:
			bits = read_u16(source, offset + 36)
			if not bits or bits & 3: offset += 0x400; continue
			data, section = decompress_section(source, offset, 36); palette_data = data[:palette_size]; image_data = data[palette_size:expected]; section_end = offset + section["compressed_size"]; layout = "decompressed"
		elif layout == "contiguous":
			if size not in (expected, expected + 0x7D0): offset += 0x400; continue
			data_start = offset + (0x800 if size == expected + 0x7D0 else 0x30); data = source[data_start:data_start + expected]; palette_data = data[:palette_size]; image_data = data[palette_size:expected]; palette_start = data_start; image_start = data_start + palette_size; layout = "sector_padded" if data_start == offset + 0x800 else layout
		else:
			if size != palette_size + (0x800 - 0x30 - palette_size) + image_size or palette_start + palette_size > offset + 0x800 or image_start + image_size > section_end: offset += 0x400; continue
			palette_data = source[palette_start:palette_start + palette_size]; image_data = source[image_start:image_start + image_size]
		if len(palette_data) != palette_size or len(image_data) != image_size: raise ValueError(f"{name} texture upload at {offset:#x} is truncated")
		uploads.append({"file": name, "section_offset": offset, "section_type": kind, "palette_rect": [px, py, colors, palettes], "image_rect": [x, image_rect_y, width, height], "palette_data": palette_data, "image_data": image_data, "palette_source_offset": palette_start, "image_source_offset": image_start, "source_layout": layout})
		offset = max(offset + 0x400, ((section_end + 0x3FF) // 0x400) * 0x400)
	return uploads
def texture_uploads(source, vram, name):
	uploads = texture_upload_records(source, name)
	for upload in uploads:
		px, py, colors, palettes = upload["palette_rect"]; x, y, width, height = upload["image_rect"]; palette_data = upload["palette_data"]; image_data = upload["image_data"]
		for row in range(palettes):
			start = ((py + row) * 1024 + px) * 2; count = colors * 2; source_start = row * count; vram[start:start + count] = palette_data[source_start:source_start + count]
		for row in range(height):
			start = ((y + row) * 1024 + x) * 2; count = width * 2; source_start = row * count; vram[start:start + count] = image_data[source_start:source_start + count]
		upload["palette_rect"] = list(upload["palette_rect"]); upload["image_rect"] = list(upload["image_rect"]); upload["palette_source_offset"] = hex(upload["palette_source_offset"]); upload["image_source_offset"] = hex(upload["image_source_offset"]); upload.pop("palette_data"); upload.pop("image_data")
	return uploads

def export_texture_library(source_dir, output_dir):
	source_dir = Path(source_dir); output_dir = Path(output_dir); result = []
	for path in sorted(source_dir.rglob("*.BIN")):
		data = path.read_bytes(); entries = []; uploads = texture_upload_records(data, path.name)
		for upload in uploads:
			offset = int(upload["section_offset"]); kind = int(upload["section_type"]); px, py, colors, palettes = upload["palette_rect"]; x, y, width, height = upload["image_rect"]; palette_data = upload["palette_data"]; image_data = upload["image_data"]; payload = palette_data + image_data
			directory = output_dir / path.parent.name.lower() / path.stem; directory.mkdir(parents=True, exist_ok=True); entry = {"source": path.relative_to(source_dir).as_posix(), "offset": offset, "type": kind, "palette_rect": [px, py, colors, palettes], "image_rect": [x, y, width, height], "source_layout": upload["source_layout"], "palette_source_offset": hex(upload["palette_source_offset"]), "image_source_offset": hex(upload["image_source_offset"])}
			try:
				name = "upload_%05X.bin" % offset; write_output(directory / name, payload); entry.update(status="exported", file=name, sha256=hashlib.sha256(payload).hexdigest(), packing="Native palette words followed by packed VRAM image words")
				if colors and palettes:
					pixels = bytearray()
					for index in range(colors * palettes):
						word = read_u16(palette_data, index * 2); pixels.extend(((word & 31) * 255 // 31, ((word >> 5) & 31) * 255 // 31, ((word >> 10) & 31) * 255 // 31, 0 if word == 0 else 128 if word & 0x8000 else 255))
					name = "palette_%05X.png" % offset; write_output(directory / name, png(colors, palettes, pixels)); entry["palette_file"] = name
			except (ValueError, IndexError, struct.error) as error: entry.update(status="unsupported", error=str(error))
			entries.append(entry)
		if entries: write_output(directory / "manifest.json", json.dumps({"textures": entries}, indent=2), encoding="utf-8"); result.extend(entries)
	return result
def export_geometry(input_dir, output_dir, stages):
	output_dir.mkdir(parents=True, exist_ok=True); catalog = []
	for stage_name in stages:
		root_path = input_dir / f"{stage_name}.BIN"; texture_path = input_dir / f"{stage_name}T.BIN"; root_bytes = root_path.read_bytes(); texture_bytes = texture_path.read_bytes(); stage = Stage(root_bytes); vram, texture_count = textures(texture_path); stage_dir = output_dir / stage_name; stage_dir.mkdir(parents=True, exist_ok=True); areas = []
		texture_cache = {}
		for area_index in range(len(stage.grids)):
			display_name = next((item[2] for item in LOCATIONS if item[0] == stage_name and item[1] == area_index), None) or location_name(stage_name, area_index); family = STAGE_BINDINGS.get(stage_name, {}).get("name")
			if area_index >= len(stage.grids): raise ValueError(f"{stage_name} has no native area {area_index:02d}")
			area = stage.area(area_index)
			if area is None: continue
			tiles, placement_ids = area; area_banks = AREA_TEXTURE_BANKS.get((stage_name, area_index), []); area_paths = [texture_path, *[input_dir / bank["file"] for bank in area_banks]]; area_vram, loaded_banks = texture_vram(area_paths) if area_banks else (vram, [{"file": texture_path.name, "sha256": digest(texture_bytes), "upload_count": texture_count}]); glb = Glb(area_vram, {}); quads = 0
			ground_binding = terrain_binding(texture_path, area_index) if any(read_u16(tile, 0) != 0xffff and read_u16(tile, 0) & 0x8000 and (read_u16(tile, 0) & 0x4000 or stage.placements[read_u16(tile, 0) & 0x7ff][3] & 0x8000) for tile in tiles.values()) else None
			ground = terrain_groups(tiles, ground_binding, stage.placements) if ground_binding else {}
			if ground: glb.instance("terrain", -1, ground, [0, 0, 0]); quads += sum(len(faces) for faces in ground.values())
			if not placement_ids and not ground: continue
			variant_rules = []; variant_manifest = []; placement_streams = []
			for rule in AREA_PLACEMENT_VARIANTS.get((stage_name, area_index), []):
				tile_flags = read_u16(tiles[tuple(rule["tile"])], 0)
				if tile_flags & 0xc000 != 0x8000: raise ValueError(f"{stage_name} area {area_index:02d} tile {rule['tile']} holds no placement")
				check_overlay_words(texture_bytes, rule["overlay_words"], f"{stage_name} area {area_index:02d} {rule['item']} variant rule"); variant_rules.append(dict(rule, placement=tile_flags & 0x7ff))
			for placement_id in placement_ids:
				_, model_id, flags, height, x, z = stage.placements[placement_id]; _, header, directory = stage.directories[model_id]; variant = flags & 3; variant_count = ((header >> 24) & 1) + 1
				if variant >= variant_count: raise ValueError(f"{stage_name} area {area_index:02d} placement {placement_id} selects invalid variant {variant}")
				pointer = read_u16(stage.data, stage.base + (directory & 0xffff) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [-((x << 9) - (0x7e00 if header & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if header & 0x20000000 else 0x7f00)) * UNIT]; node_name = f"placement_{placement_id:03d}_model_{model_id:03d}"; glb.instance(node_name, pointer, groups, translation, stage.face_metadata[pointer]); quads += sum(len(faces) for faces in groups.values())
				streams = placement_stream_visibility(stage, placement_id)
				if streams: placement_streams.append(streams)
				variant_rule = next((rule for rule in variant_rules if rule["placement"] == placement_id), None)
				if variant_rule is not None:
					if variant_count != 2 or variant != 0: raise ValueError(f"{stage_name} area {area_index:02d} placement {placement_id} is not a two-variant placement")
					variant_pointer = read_u16(stage.data, stage.base + (directory & 0xffff) * 4 + 12); variant_groups = stage.model(variant_pointer); glb.instance(node_name + "_variant_1", variant_pointer, variant_groups, translation, stage.face_metadata[variant_pointer])
					variant_manifest.append({"placement": placement_id, "model": model_id, "item": variant_rule["item"], "base_node": node_name, "base_variant": 0, "variant_node": node_name + "_variant_1", "variant": 1, **({"event_flag": variant_rule["event_flag"], "variant_when_set": 0, "variant_when_clear": 1} if "event_flag" in variant_rule else {"runtime": variant_rule["runtime"]}), "tile": variant_rule["tile"], "source": variant_rule["source"]})
			file_name = f"area_{area_index:02d}.glb"; bounds = glb.save(stage_dir / file_name); area_manifest = {"index": area_index, "name": display_name.removeprefix(family + " ").removeprefix("- ") if display_name and family else display_name or "Area %02d" % area_index, "file": file_name, "placements": len(placement_ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds, "native_map_code": {"stage": int(stage_name[2:], 16), "area": area_index}, "terrain_source": ground_binding, "native_map_face_flags_in_alpha": True, "placement_streams": placement_streams}
			if variant_manifest: area_manifest["placement_variants"] = variant_manifest
			if area_banks: area_manifest["texture_state"] = {"source_order": [{"file": f"DAT/{texture_path.name}", "file_id": 254, "sha256": digest(texture_bytes), "source": "GAME0x800BA600 default ST3A root/T loader"}, *[{"file": f"DAT/{bank['file']}", "file_id": bank["file_id"], "sha256": item["sha256"], "source": bank["source"]} for bank, item in zip(area_banks, loaded_banks[1:])]], "applied_in_vram_order": True}
			areas.append(area_manifest); print(f"{stage_name}_{area_index:02d}: {len(placement_ids)} placements, {quads} quads")
		stage_manifest = {"stage": stage_name, "name": STAGE_NAMES.get(stage_name, stage_name), "source_reference": {"description": "native stage/substage values XX/YY and room labels"} if stage_name in STAGE_BINDINGS else None, "coordinate_unit": "1/256 map unit", "coordinate_basis": COORDINATE_BASIS, "source": {"root_file": f"DAT/{stage_name}.BIN", "textures_file": f"DAT/{stage_name}T.BIN", "root_sha256": digest(root_bytes), "textures_sha256": digest(texture_bytes), "texture_sections": texture_count}, "areas": areas, "native_floor_collision": floor_collision_manifest(root_path), "native_combat_policy": native_combat_policy(texture_bytes)}
		for rule in STAGE_FLAG_RULES.get(stage_name, []): check_overlay_words(texture_bytes, rule["overlay_words"], f"{stage_name} stage flag rule")
		if stage_name in STAGE_FLAG_RULES: stage_manifest["stage_flag_rules"] = [{key: value for key, value in rule.items() if key != "overlay_words"} for rule in STAGE_FLAG_RULES[stage_name]]
		write_output(stage_dir / "manifest.json", json.dumps(stage_manifest, indent=2) + "\n", encoding="utf-8"); catalog.append({"stage": stage_name, "name": stage_manifest["name"], "manifest": "res://" + (stage_dir / "manifest.json").resolve().relative_to(ROOT).as_posix(), "area_names": [area["name"] for area in areas]})
	catalog_path = output_dir.parent / "locations" / "manifest.json"; catalog_path.parent.mkdir(parents=True, exist_ok=True); existing = json.loads(catalog_path.read_text()).get("locations", []) if catalog_path.exists() else []; entries = {item["stage"]: item for item in existing}; entries.update({item["stage"]: item for item in catalog})
	for entry in entries.values():
		manifest = json.loads((ROOT / entry["manifest"].removeprefix("res://")).read_text()); entry["areas"] = [{"index": int(area["index"]), "name": str(area.get("name", "Area %02d" % area["index"]))} for area in manifest["areas"]]; entry.pop("area_names", None)
	catalog_manifest = {"locations": [entries[key] for key in sorted(entries)]}; write_output(catalog_path, json.dumps(catalog_manifest, indent=2) + "\n", encoding="utf-8"); return catalog_manifest

def native_hinged_door_bindings(data):
	words = struct.unpack_from("<" + "I" * ((len(data) - 48) // 4), data, 48); result = {}
	for index, word in enumerate(words):
		if word == 0xA0740004 and index + 4 < len(words) and words[index + 1] == 0x92220003 and words[index + 2] >> 16 == 0x3C04 and tuple(words[index + 3:index + 5]) == (0xAC60000C, 0xA0620006): result[1] = {"source": hex(BASE + index * 4), "offsets": [[80, 64]]}
		if word == 0xA0440004 and 0x24040003 in words[max(0, index - 12):index] and tuple(words[index + 1:index + 5]) == (0x92220003, 0x8E03002C, 0x00021040, 0xA0620006) and index + 60 < len(words):
			pairs = [(39, 40, 0x3C02, 0x2442), (52, 55, 0x3C04, 0x2484), (57, 60, 0x3C05, 0x24A5)]; pointers = []
			for upper_at, lower_at, upper_code, lower_code in pairs:
				upper, lower = words[index + upper_at], words[index + lower_at]
				if upper >> 16 != upper_code or lower >> 16 != lower_code: break
				pointers.append(((upper & 65535) << 16) + struct.unpack("<h", struct.pack("<H", lower & 65535))[0])
			if len(pointers) == 3:
				offset, script, timeline = [48 + pointer - BASE for pointer in pointers]
				if 0 <= offset <= len(data) - 12 and 0 <= script <= len(data) - 4 and 0 <= timeline <= len(data) - 32 and read_u32(data, script) == 0xFFFFFFFF and [read_u32(data, timeline + tick * 8) for tick in range(4)] == [0x000A0000, 0x000A0100, 0x00090200, 255]: result[3] = {"source": hex(BASE + index * 4), "offset_source": hex(pointers[0]), "offsets": [list(struct.unpack_from("<2h", data, offset + row * 4)) for row in range(3)], "timeline": hex(pointers[2]), "player_script": hex(pointers[1])}
		if word == 0xA0440004 and 0x24040003 in words[max(0, index - 20):index] and tuple(words[index + 1:index + 5]) == (0x92220003, 0x8E03002C, 0x00021040, 0xA0620006) and index + 6 < len(words):
			upper, lower = words[index + 5:index + 7]
			if upper >> 16 == 0x3C02 and lower >> 16 == 0x2442:
				pointer = ((upper & 65535) << 16) + struct.unpack("<h", struct.pack("<H", lower & 65535))[0]; offset = 48 + pointer - BASE; registers = {}; script_pointer = None; timeline_pointer = None
				for instruction in words[index:min(index + 100, len(words))]:
					opcode = instruction >> 26; rs = (instruction >> 21) & 31; rt = (instruction >> 16) & 31; immediate = struct.unpack("<h", struct.pack("<H", instruction & 65535))[0]
					if instruction == 0x0C030317: script_pointer = registers.get(4); timeline_pointer = registers.get(5); break
					if opcode == 15: registers[rt] = (instruction & 65535) << 16
					elif opcode == 9 and rs in registers: registers[rt] = (registers[rs] + immediate) & 0xFFFFFFFF
					elif opcode in [9, 32, 33, 34, 35, 36, 37, 38]: registers.pop(rt, None)
				if script_pointer is not None and timeline_pointer is not None:
					script = 48 + script_pointer - BASE; timeline = 48 + timeline_pointer - BASE
					if 0 <= offset <= len(data) - 8 and 0 <= script <= len(data) - 4 and 0 <= timeline <= len(data) - 32 and read_u32(data, script) == 0xFFFFFFFF and [read_u32(data, timeline + tick * 8) for tick in range(4)] == [0x000A0000, 0x000A0100, 0x00090200, 255]: result[3] = {"source": hex(BASE + index * 4), "offset_source": hex(pointer), "offsets": [list(struct.unpack_from("<2h", data, offset + row * 4)) for row in range(2)], "timeline": hex(timeline_pointer), "player_script": hex(script_pointer)}
		if word != 0xA0440004 or 0x24040002 not in words[max(0, index - 12):index] or index + 11 >= len(words) or tuple(words[index + 1:index + 5]) != (0x92220003, 0x8E03002C, 0x00021040, 0xA0620006): continue
		upper, lower = words[index + 5:index + 7]
		if upper >> 16 != 0x3C02 or lower >> 16 != 0x2442: continue
		pointer = ((upper & 65535) << 16) + struct.unpack("<h", struct.pack("<H", lower & 65535))[0]; offset = 48 + pointer - BASE
		if 0 <= offset <= len(data) - 8: result[2] = {"source": hex(BASE + index * 4), "offset_source": hex(pointer), "offsets": [list(struct.unpack_from("<2h", data, offset + row * 4)) for row in range(2)]}
	return result

def export_routes(dat_dir, output_dir, stages):
	result = {}; manifests = {}
	for stage in stages:
		routes = []; unresolved_areas = {}; data = (dat_dir / (stage + "T.BIN")).read_bytes(); discovered = native_area_tables(data); candidates = {item["pointer_ram"] for item in discovered["routes"]}; native_areas = [int(entry["index"]) for entry in json.loads((output_dir / stage / "manifest.json").read_text())["areas"]]; binding = {"routes": next(iter(candidates)), "areas": native_areas} if len(candidates) == 1 else None
		if binding:
			for area in binding["areas"]:
				pointer = struct.unpack_from("<I", data, 0x30 + binding["routes"] - BASE + area * 4)[0]; offset = 0x30 + pointer - BASE; index = 0
				if pointer == 0 or not 0 <= offset <= len(data) - 24:
					unresolved_areas[str(area)] = {"pointer_ram": hex(pointer), "reason": "Native indexed slot has no in-overlay route list"}
					continue
				while True:
					if not 0 <= offset <= len(data) - 24: raise ValueError(f"{stage} area {area} has invalid native route pointer {pointer:#x}")
					if data[offset] == 255: break
					raw = data[offset:offset + 24]
					if len(raw) != 24: raise ValueError(f"{stage} area {area} has a truncated native route")
					sx, sy, sz, yaw, dx, dy, dz, arrival_yaw = struct.unpack_from("<hhhHhhhH", raw, 8); routes.append({"source_area": area, "destination_stage": f"ST{raw[6]:02X}", "destination_area": raw[7], "door_id": raw[0], "door_slot": raw[1], "door_mode": raw[2], "record_index": index, "file_offset": offset, "source_transform_raw": [sx, sy, sz, yaw], "source_transform": {"position": [sx / 256, sy / 256, sz / 256], "yaw_raw": yaw}, "destination_transform_raw": [dx, dy, dz, arrival_yaw], "destination_transform": {"position": [dx / 256, dy / 256, dz / 256], "yaw_raw": arrival_yaw, "floor_height": dy == -1}, "lock_event": 0x710 + (raw[0] & 31), "transition_event": 0x730 + (raw[0] & 31), "blocked_message": struct.unpack_from("<h", raw, 4)[0], "bytes_hex": raw.hex()}); offset += 24; index += 1
					if index > 64: raise ValueError(f"{stage} area {area} route list has no terminator")
		path = output_dir / stage / "doors.json"; previous = json.loads(path.read_text()) if path.exists() else {}
		for route in routes:
			old = next((candidate for candidate in previous.get("area_transitions", []) if candidate.get("source_area") == route["source_area"] and candidate.get("bytes_hex") == route["bytes_hex"]), {})
			for key, value in old.items(): route.setdefault(key, value)
		floor_manifest = floor_collision_manifest(dat_dir / (stage + ".BIN")); bind_route_contacts(routes, floor_manifest)
		map_interactions = [{"source_area": int(area), "native_contacts": [{**contact, "type": 16, "automatic": False, "probe_forward_raw": -64 if contact["mask"] & 0x8000 else 0}], "runtime_index": contact["mask"] & 255, "message_kind": 0, "window": 0, "source_function": "GAME0x800B81CC/0x800BE330", "source_bank_pointer": "0x8010C000", "action_required": True} for area, collision in floor_manifest.items() for contact in collision.get("boxes", []) if contact["kind"] == 0x1000 and contact["mask"] & 0x4000]
		for area, collision in floor_manifest.items():
			for variant in collision.get("placement_variants", []):
				for interaction in map_interactions:
					if interaction["source_area"] != int(area) or interaction["native_contacts"][0]["placement"] != variant["placement"]: continue
					if any(record["kind"] == 0x1000 and record["mask"] & 255 == interaction["runtime_index"] for record in variant["boxes"]): continue
					interaction["availability"] = {"all": [{**condition, "negate": not condition.get("negate", False)} for condition in variant["predicate"]["all"]], "source": variant["source"]}
			for variant in collision.get("placement_variants", []):
				base = [box for box in collision["boxes"] if box["placement"] == variant["placement"]]
				for contact in variant["boxes"]:
					if contact["kind"] != 0x1000 or not contact["mask"] & 0x4000 or contact in base: continue
					map_interactions.append({"source_area": int(area), "native_contacts": [{**contact, "type": 16, "automatic": False, "probe_forward_raw": -64 if contact["mask"] & 0x8000 else 0}], "runtime_index": contact["mask"] & 255, "message_kind": 0, "window": 0, "source_function": "GAME0x800B81CC/0x800BE330", "source_bank_pointer": "0x8010C000", "action_required": True, "availability": {"all": variant["predicate"]["all"], "source": variant["source"]}})
		walk = native_automatic_walk(data); hinge_bindings = native_hinged_door_bindings(data)
		for route in routes:
			if any(contact["automatic"] for contact in route["native_contacts"]): route["native_automatic_walk"] = walk
			for door_class in [1, 2]:
				contact = next((contact for contact in route["native_contacts"] if contact["type"] == door_class + 1), None); hinge_binding = hinge_bindings.get(door_class); mode = route["door_mode"] >> 4
				if contact is None or hinge_binding is None or mode >= len(hinge_binding["offsets"]): continue
				route["native_door"] = {"style": "hinged" if door_class == 1 else "hinged_with_fixed_companion", "controller_class": door_class, "variants": [route["door_slot"]] if door_class == 1 else [route["door_slot"] * 2, route["door_slot"] * 2 + 1], "offset_raw": hinge_binding["offsets"][mode], "opening_ticks": 9, "hold_ticks": 0, "closing_ticks": 17, "tick_rate": 25, "sounds": [0xB8, -1, 0xB9], "player_gesture": True, "source_placement": contact["placement"], "constructor": "GAME0x800D17A4" if door_class == 1 else "GAME0x800D1B10", "source_initializer": hinge_binding["source"], "motion": "GAME0x800D1950" if door_class == 1 else "GAME0x800D1CC0"}
				_, faces = room_faces(output_dir, stage, route["source_area"]); raw = route["source_transform_raw"]; center = [-raw[0] / 256, -raw[1] / 256, raw[2] / 256]; axis = 2 if ((raw[3] & 4095) >> 10) % 2 == 0 else 0; prefix = f"placement_{contact['placement']:03d}_"
				try: route["native_door"]["source_panel"] = select_panel([face for face in faces if face["node"].startswith(prefix)], center, axis)
				except ValueError as error: route["native_door"]["unresolved_panel"] = str(error)
			if 3 in hinge_bindings and any(contact["type"] == 8 for contact in route["native_contacts"]):
				mode = route["door_mode"] >> 4; offsets = hinge_bindings[3]["offsets"]
				if mode < len(offsets): route["native_door"] = {"style": "sliding_pair", "controller_class": 3, "variants": [route["door_slot"] * 2, route["door_slot"] * 2 + 1], "offset_raw": list(offsets[mode]), "opening_ticks": 10, "hold_ticks": 10, "closing_ticks": 9, "tick_rate": 25, "sounds": [0xBA, 0xBD, 0xBB], "player_gesture": False, "unsupported_event": 0x701, "source_placement": next(contact["placement"] for contact in route["native_contacts"] if contact["type"] == 8), "constructor": "GAME0x800D1F1C", "source_initializer": hinge_bindings[3]["source"], "timeline": hinge_bindings[3]["timeline"], "motion": "GAME0x800D20EC"}
				if "native_door" in route:
					_, faces = room_faces(output_dir, stage, route["source_area"]); raw = route["source_transform_raw"]; center = [-raw[0] / 256, -raw[1] / 256, raw[2] / 256]; axis = 2 if ((raw[3] & 4095) >> 10) % 2 == 0 else 0; prefix = f"placement_{route['native_door']['source_placement']:03d}_"
					try: route["native_door"]["source_panel"] = select_panel([face for face in faces if face["node"].startswith(prefix)], center, axis)
					except ValueError as error:
						marker_faces = [face for face in faces if face["node"].startswith(prefix)]
						if len(marker_faces) == 1 and max(point[1] for point in marker_faces[0]["quad"]) < center[1] and max(point[1] for point in marker_faces[0]["quad"]) - min(point[1] for point in marker_faces[0]["quad"]) < 0.00001 and all(0.0 < max(point[axis] for point in marker_faces[0]["quad"]) - min(point[axis] for point in marker_faces[0]["quad"]) <= 32 * UNIT for axis in [0, 2]):
							face = marker_faces[0]; route["native_door"]["source_panel"] = {"node": face["node"], "primitive_index": face["primitive_index"], "quads": [{"quad_index": face["quad_index"], "primitive_index": face["primitive_index"], "triangles_local": face["triangles_local"]}]}; route["native_door"]["source_panel_role"] = "native_placement_visibility_marker"; route["native_door"].pop("unresolved_panel", None)
						else: route["native_door"]["unresolved_panel"] = str(error)
		manifest = {**previous, "stage": stage, "binding_status": "partial" if binding and unresolved_areas else "bound" if binding else "unbound", "source": {**previous.get("source", {}), "file": f"DAT/{stage}T.BIN", "sha256": digest(data), "area_route_pointer_ram": hex(binding["routes"]) if binding else None, "active_pointer_ram": "0x80078FA4", "native_table_writers": discovered["routes"], "native_actor_tables": discovered["actors"], "unresolved_areas": unresolved_areas, "unresolved": None if binding else "No unique source area-table assignment to 0x80078FA4", "record_stride": 24, "consumer": "GAME0x800B7B38-0x800B7E74", "lock_consumer": "GAME0x800B89B4", "transition_consumer": "GAME0x800B8A2C", "native_contact": "xyz matches collision contact0x800E0BCC; heading difference within[-0x200,0x200)", "runtime_interaction": "PC interaction requires a nearby door face and native heading; destinationY=-1 resolves room collision floor"}, "area_transitions": routes, "map_interactions": map_interactions}; manifests[stage] = manifest; result[stage] = routes
	for stage, routes in result.items():
		for route in routes:
			other = result.get(route["destination_stage"])
			reciprocal = next((candidate for candidate in other or [] if candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"]), None); route["reciprocal_native_route"] = reciprocal is not None
			if stage in STAGES and route["destination_stage"] not in STAGES and reciprocal is not None:
				reverse = next(candidate for candidate in other if candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"]); center, axis = route_center(route, reverse, True); _, faces = room_faces(output_dir, stage, route["source_area"]); route["source_panel"] = select_panel(faces, center, axis)
	for stage, manifest in manifests.items(): write_output(output_dir / stage / "doors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return result
def native_actor_lists(overlay, area_count):
	base = read_u32(overlay, 12) or BASE; found = {}; target = 0x8003D3F8
	for call_off in range(0x30 + 12, len(overlay), 4):
		word = read_u32(overlay, call_off)
		if word >> 26 != 3: continue
		pc = base + call_off - 0x30
		if ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2) != target: continue
		load = read_u32(overlay, call_off - 4); add = read_u32(overlay, call_off - 8); shift = read_u32(overlay, call_off - 12)
		if load >> 26 != 0x23 or ((load >> 16) & 31) != 4 or (load & 0xFFFF) != 0: continue
		index_reg = (load >> 21) & 31; add_rs = (add >> 21) & 31; add_rt = (add >> 16) & 31; add_rd = (add >> 11) & 31
		if add >> 26 != 0 or (add & 63) != 0x21 or add_rd != index_reg or add_rs != index_reg: continue
		if shift >> 26 != 0 or (shift & 63) != 0 or ((shift >> 11) & 31) != index_reg or ((shift >> 16) & 31) != index_reg or ((shift >> 6) & 31) != 2: continue
		table_reg = add_rt; candidate = None
		for low_off in range(call_off - 16, max(0x30, call_off - 0x40) - 4, -4):
			low = read_u32(overlay, low_off)
			if low >> 26 != 9 or ((low >> 21) & 31) != table_reg or ((low >> 16) & 31) != table_reg: continue
			for high_off in range(low_off - 4, max(0x30, low_off - 0x20) - 4, -4):
				high = read_u32(overlay, high_off)
				if high >> 26 != 0x0F or ((high >> 16) & 31) != table_reg: continue
				address = ((((high & 0xFFFF) << 16) + ((low & 0xFFFF) - (0x10000 if low & 0x8000 else 0))) & 0xFFFFFFFF); file_off = 0x30 + address - base
				if file_off < 0x30 or file_off + area_count * 4 > len(overlay): continue
				pointers = []; lists = []; valid = True
				for area in range(max(1, area_count)):
					if file_off + (area + 1) * 4 > len(overlay): break
					pointer = read_u32(overlay, file_off + area * 4); at = 0x30 + pointer - base
					if at < 0x30 or at + 20 > len(overlay): break
					records = []; terminated = False
					for record in range(256):
						offset = at + record * 20; raw = overlay[offset:offset + 20]
						if len(raw) != 20: valid = False; break
						if raw[0] == 0xFF: terminated = True; break
						records.append({"area": area, "record": record, "pointer": pointer, "offset": offset, "raw": raw})
					if not valid or not terminated: break
					pointers.append(pointer); lists.extend(records)
				if valid and pointers:
					entry = {"address": address, "call_pc": pc, "pointers": pointers, "records": lists}; found.setdefault(address, entry); candidate = entry; break
			if candidate: break
	return sorted(found.values(), key=lambda item: item["call_pc"])
def actor_archive_for_records(stage, source, records, work, dat_dir, fallback_offset=None, required_door_flags=None):
	required = [record for record in records if record["raw"][2] in (0x20, 0x60, 0x61) and not (record["raw"][2] == 0x60 and record["raw"][4] == 2 and record["raw"][5] == 0)]
	required_door_flags = set(required_door_flags or []); candidates = []; offsets = list(range(0x400, len(source) - 0x30, 0x400))
	if fallback_offset is not None: offsets.insert(0, fallback_offset)
	for offset in dict.fromkeys(offsets):
		if offset + 12 > len(source) or read_u32(source, offset) != 0x0C: continue
		try:
			payload, section = decompress_section(source, offset); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); normalized = work / f"{stage}_models_{offset:05X}.bin"; write_output(normalized, header + payload); archive, payload = actor_archive(normalized)
		except (ValueError, IndexError, KeyError, struct.error, OSError): continue
		match_count = 0
		for record in required:
			raw = record["raw"]; flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == flags]
			if len(matches) == 1: match_count += 1
		door_count = sum(1 for model in archive["models"] if model["flags"] & 0xFFFF in (0x161, 0x261, 0x361))
		if required_door_flags and any(sum(model["flags"] & 0xFFFFFF == flags for model in archive["models"]) != 1 for flags in required_door_flags): continue
		if required and match_count == 0 and not required_door_flags: continue
		if not required and not door_count and fallback_offset != offset: continue
		candidates.append((match_count, door_count, offset, archive, payload, section, stage + ".BIN"))
	extra_archive_path = dat_dir / (stage + "00.BIN")
	if extra_archive_path.is_file() and read_u32(extra_archive_path.read_bytes(), 0) == 10:
		try:
			archive, payload = actor_archive(extra_archive_path); match_count = 0
			for record in required:
				raw = record["raw"]; flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == flags]
				if len(matches) == 1: match_count += 1
			door_count = sum(1 for model in archive["models"] if model["flags"] & 0xFFFF in (0x161, 0x261, 0x361))
			if (required and match_count or required_door_flags) and all(sum(model["flags"] & 0xFFFFFF == flags for model in archive["models"]) == 1 for flags in required_door_flags): candidates.append((match_count, door_count, None, archive, payload, None, extra_archive_path.name))
		except (ValueError, IndexError, KeyError, struct.error, OSError): pass
	if not candidates: return None
	candidates.sort(key=lambda value: (-value[0], -value[1], 0 if value[2] == fallback_offset else 1 if value[2] is not None else 2, value[2] or 0)); best = candidates[0]
	if len(candidates) > 1 and (candidates[1][0], candidates[1][1]) == (best[0], best[1]) and fallback_offset not in (best[2], candidates[1][2]): return None
	return {"archive": best[3], "payload": best[4], "section": best[5], "offset": best[2], "archive_file": best[6]}
CHEST_PROLOGUE = (0x27BDFFD0, 0xAFB00020, 0x00808021, 0x3C048009, 0x2484C0B0, 0x26050010)
def chest_profile(stage, overlay, mine=False):
	if stage in ("ST0D", "ST0F") and not mine: return None
	base = read_u32(overlay, 12) or BASE; words = struct.unpack_from("<%dI" % ((len(overlay) - 0x30) // 4), overlay, 0x30); offset = lambda address: 0x30 + address - base
	for index in range(len(words) - 12):
		if words[index:index + 6] != CHEST_PROLOGUE: continue
		callback = base + index * 4; low = words[index + 10] & 0xFFFF; table = (((words[index + 6] & 0xFFFF) << 16) + low - (0x10000 if low & 0x8000 else 0)) & 0xFFFFFFFF
		if read_u32(overlay, offset(table + 0x20)) != callback: continue
		return {"callback": callback, "table": table, "descriptors": read_u32(overlay, offset(table)), "body": list(struct.unpack_from("<6h", overlay, offset(table + 4))), "target": list(struct.unpack_from("<6h", overlay, offset(table + 0x10))), "overlay": overlay, "base": base}
	return None
def chest_entry(stage, chest, raw):
	flag, message, reward = struct.unpack_from("<HHI", chest["overlay"], 0x30 + chest["descriptors"] + raw[6] * 8 - chest["base"])
	return {"stage": stage, "actor_class": 21, "native_hitbox": {"bounds_raw": chest["body"]}, "startup_control": {"code": 0}, "native_interaction": {"stage": stage, "message_index": message, "message_call": "0x800BE330", "request_kind": 0, "target_descriptor_raw": chest["target"], "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 384, "strict_bounds": True, "line_of_sight": False}, "bank_id": "0x8010C000"}, "native_chest": {"collected_flag": flag, "message_index": message, "reward_word": reward, "message_call": "0x800BE330", "descriptor_ram": hex(chest["descriptors"] + raw[6] * 8), "source_callback": hex(chest["callback"])}}
def kickable_profile(stage, raw):
	if stage != "ST09" or raw[2] != 0x60 or raw[4] not in (0x4A, 0x4B): return None
	can = raw[4] == 0x4A
	result = {"kind": "can" if can else "duck", "bounds_raw": [-16, 16, -8, 8, -16, 16] if can else [-32, 32, -160, 0, -32, 32], "resource_variant": 0, "native_tick_hz": 25, "velocity_world_divisor": 4096, "source": {"callback": "0x800edb9c" if can else "0x800ee3a4", "constructor": "0x800edc04" if can else "0x800ee574", "resource_loader": "SLES0x8003DFA4", "body_bounds": "0x800f2c7c" if can else "0x800f2c94", "target_bounds": "0x800f2c88" if can else "0x800f2ca0", "hit_handler": "0x800ee24c" if can else "0x800eee98"}, "sound_ids": [0x297, 0x298, 0x299, 0x29A] if can else [0x29B], "kick_flags": 0x80000}
	if can and raw[6] == 1: result["minimum_save_byte14"] = 2
	return result
def export_scene_door_records(stage, overlay, metadata, dat_dir):
	bindings = {"ST0B": {"scene": 0x27, "areas": {0: [0x800EF314, 0x800EF328], 1: [0x800EF33C, 0x800EF350]}}}; binding = bindings.get(stage)
	if binding is None: return
	groups = []
	for area, pointers in binding["areas"].items():
		actors = []
		for slot, pointer in enumerate(pointers):
			raw = overlay[48 + pointer - BASE:48 + pointer - BASE + 20]; resource = next(model for model in metadata["native_doors"] if model["controller_class"] == 2 and model["variant"] == raw[6]); model = next(model for model in metadata["models"] if model["model_index"] == resource["model_index"]); x, y, z, yaw = struct.unpack_from("<3hH", raw, 12)
			entry = {"stage": stage, "area": area, "source_record_ram": hex(pointer), "source_bytes_hex": raw.hex(), "actor_class": raw[4], "actor_state": raw[5], "resource_variant": raw[6], "position": [-x / 256, -y / 256, z / 256], "yaw_turns": -yaw / 4096, "control": raw[8], "frame": raw[9], "model_index": resource["model_index"], "model_file": "assets/stage_props/" + resource["model_file"]}; actors.append({"source_ram": hex(pointer), "slot": slot, "entry": entry, "model": {**model, "model_file": "assets/stage_props/" + model["model_file"]}})
		groups.append({"area": area, "actors": actors})
	write_output(ROOT / "assets/levels" / stage / f"scene_{binding['scene']:02x}_doors.json", json.dumps({"stage": stage, "scene": binding["scene"], "groups": groups}, indent=2) + "\n", encoding="utf-8")
	cinematics.scenes_export_church(dat_dir, ROOT / "assets/levels" / stage)

def export_props(dat_dir, output_dir, stages):
	output_dir.mkdir(parents=True, exist_ok=True); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); target = output_dir / "manifest.json"; manifest = json.loads(target.read_text()) if target.exists() else {"stages": {}}
	for stage in stages:
		manual = STAGE_BINDINGS.get(stage, {}); overlay_path = dat_dir / (stage + "T.BIN"); root_path = dat_dir / (stage + ".BIN"); instances = []; models = {}; native_doors = []; unresolved = []; weather_records = []; section = None; uploads = []; source = root_path.read_bytes()
		if not overlay_path.is_file(): manifest["stages"][stage] = {"binding_status": "unbound", "source": {"archive": root_path.name, "overlay": overlay_path.name}, "models": [], "native_doors": [], "instances": []}; continue
		overlay = overlay_path.read_bytes(); area_count = len(Stage(source).grids); table_area_count = area_count; detections = native_actor_lists(overlay, table_area_count); detected = detections[0] if detections else None
		if detected: actor_pointer_table = detected["address"]; actor_caller = hex(detected["call_pc"]); raw_records = detected["records"]
		else: actor_pointer_table = None; actor_caller = None; raw_records = []
		weather_records = [{"area": item["area"], "source_file_offset": hex(item["offset"]), "source_bytes": item["raw"].hex(), "native_type": "procedural_weather"} for item in raw_records if item["raw"][2] == 0x60 and item["raw"][4] == 2 and item["raw"][5] == 0]; mesh_records = [item for item in raw_records if item["raw"][2] in (0x20, 0x60, 0x61) and not (item["raw"][2] == 0x60 and item["raw"][4] == 2 and item["raw"][5] == 0)]; door_path = ROOT / "assets/levels" / stage / "doors.json"; door_data = json.loads(door_path.read_text(encoding="utf-8")) if door_path.is_file() else {}; required_door_flags = {0x61 | (int(route["native_door"]["controller_class"]) << 8) | (int(variant) << 16) for route in door_data.get("area_transitions", []) if route.get("native_door") for variant in route["native_door"].get("variants", [])}; archive_info = actor_archive_for_records(stage, source, raw_records, work, dat_dir, manual.get("actor_section"), required_door_flags) if actor_pointer_table is not None or required_door_flags else None; archive_source = archive_info["archive_file"] if archive_info else root_path.name
		if actor_pointer_table is not None and archive_info is None and mesh_records: unresolved.extend({"area": item["area"], "source_file_offset": hex(item["offset"]), "source_bytes": item["raw"].hex(), "reason": "no uniquely matching type-0x0C PBD archive"} for item in mesh_records)
		if archive_info:
			archive = archive_info["archive"]; payload = archive_info["payload"]; section = archive_info["section"]; vram = bytearray(1024 * 512 * 2)
			for bank in SHARED_TEXTURES:
				bank_path = dat_dir.parent / bank
				if bank_path.is_file(): uploads.extend(texture_uploads(bank_path.read_bytes(), vram, bank))
			uploads.extend(texture_uploads(overlay, vram, "DAT/" + overlay_path.name)); uploads.extend(texture_uploads(source, vram, f"DAT/{stage}.BIN")); texture_header = bytearray(48); struct.pack_into("<3I", texture_header, 0, 2, len(vram), 1); struct.pack_into("<8H", texture_header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / (stage + "_vram.bin"); write_output(texture_path, texture_header + vram)
			chest = chest_profile(stage, overlay); resource_keys = actor_resource_keys(stage, overlay); class_callbacks = actor_class_callbacks(stage, overlay)
			for item in raw_records:
				area = item["area"]; record = item["record"]; pointer = item["pointer"]; offset = item["offset"]; raw = item["raw"]
				if raw[2] == 0x60 and raw[4] == 2 and raw[5] == 0: continue
				if raw[2] not in (0x20, 0x60, 0x61): continue
				kickable = kickable_profile(stage, raw); resource_variant = kickable["resource_variant"] if kickable else 0 if chest and raw[2] == 0x20 and raw[4] == 21 else raw[6]; resource_flags = raw[2] | (raw[4] << 8) | (resource_variant << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
				if len(matches) != 1 and raw[2] in (0x20, 0x60) and raw[4] in resource_keys:
					alternate = raw[resource_keys[raw[4]]] if resource_keys[raw[4]] is not None else 0; alternate_flags = raw[2] | (raw[4] << 8) | (alternate << 16); alternate_matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == alternate_flags]
					if len(alternate_matches) == 1: resource_variant, resource_flags, matches = alternate, alternate_flags, alternate_matches
				if len(matches) != 1: unresolved.append({"area": area, "source_file_offset": hex(offset), "source_bytes": raw.hex(), "resource_flags": hex(resource_flags), "reason": "no unique PBD model match"}); continue
				model = matches[0]; index = model["index"]
				if index not in models:
					path = output_dir / stage / f"model_{index:02d}.glb"; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_actor_model(payload, index, texture_path, path, archive_source) if model["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, path, archive_source); metadata["source_surfaces"] = record_source(path, archive_source, index, payload); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata
				x, y, z, yaw = struct.unpack_from("<3hH", raw, 12); instances.append({"area": area, "source_ram": hex(pointer + record * 20), "source_file_offset": hex(offset), "source_file_offset_value": offset, "source_bytes": raw.hex(), "class": raw[4], "variant": raw[6], "model_index": index, "model_file": models[index]["model_file"], "position_raw": [x, y, z], "position": [-x / 256, -y / 256, z / 256], "yaw_raw": yaw, "yaw_turns": -yaw / 4096, "control": raw[8], "frame": raw[9], "role": manual.get("roles", {}).get(raw[4], "source_prop"), "native_control_source": "Native record bytes8/9; original PBD control table", "controller_candidate": manual.get("controllers", {}).get(raw[4])})
				if stage == "ST09" and raw[2] == 0x60 and raw[4] == 1 and raw[5] == 0 and raw[6] in [2, 3, 4]: instances[-1]["pc_source_mesh_collision"] = {"layers": [1, 4], "source_constructor": "ST09T0x800EBA8C/0x800EBB30", "native_role": "render_only_statue_part", "adapter": "Solid collision from the original statue triangles"}
				if raw[2] == 0x20 and (stage, raw[4]) in DUNGEON_ENEMIES: instances[-1].update(dungeon_enemy_entry(stage, raw[4], instances[-1], class_callbacks, output_dir)); instances[-1]["role"] = "dungeon_enemy"
				if chest and raw[2] == 0x20 and raw[4] == 21: instances[-1].update(chest_entry(stage, chest, raw)); instances[-1]["role"] = "dungeon_chest"; instances[-1]["source_bytes_hex"] = raw.hex()
				if kickable: instances[-1]["native_kickable"] = kickable; instances[-1]["native_animation_startup"] = {"control": 0, "start_record": 0}; instances[-1]["role"] = "source_kickable_" + kickable["kind"]
			for model in archive["models"]:
				if model["flags"] & 0xFFFF not in (0x161, 0x261, 0x361): continue
				index = model["index"]
				if index not in models:
					path = output_dir / stage / f"model_{index:02d}.glb"; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_static_actor(payload, index, texture_path, path, archive_source); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata
				native_doors.append({"variant": (model["flags"] >> 16) & 255, "controller_class": (model["flags"] >> 8) & 255, "model_index": index, "model_file": models[index]["model_file"], "native_scale_raw": models[index]["native_scale_raw"], "source_flags": hex(model["flags"]), "resource_loader": "SLES0x8003DFC8", "constructor": "GAME0x800D1F1C" if model["flags"] & 0xFFFF == 0x361 else "GAME0x800D1B10" if model["flags"] & 0xFFFF == 0x261 else "GAME0x800D17A4"})
		if any(key[0] == stage for key in DUNGEON_ENEMIES) and archive_info: export_dungeon_effects(stage, vram)
		bind_scripted_interactions(stage, instances, overlay, source_key="source_bytes", address_key="source_ram")
		for index, metadata in models.items(): metadata["model_index"] = index
		status = "bound" if actor_pointer_table is not None and (archive_info is not None or not mesh_records) else "partial" if actor_pointer_table is not None else "unbound"; manifest["stages"][stage] = {"binding_status": status, "source": {"archive": stage + ".BIN", "actor_archive": archive_info["archive_file"] if archive_info else None, "overlay": stage + "T.BIN", "sha256": digest(source), "decoded_section": section, "actor_pointer_table": hex(actor_pointer_table) if actor_pointer_table else None, "actor_list_area_count": len(detected["pointers"]) if detected else table_area_count if actor_pointer_table is not None else None, "caller": actor_caller, "consumer": "SLES0x8003D3F8; 20-byte object records", "actor_archive_section": archive_info["offset"] if archive_info else None, "texture_uploads": uploads, "coordinate_basis": "(-nativeX,-nativeY,+nativeZ)/256; room stream offset is separate"}, "models": list(models.values()), "native_doors": native_doors, "instances": instances, "procedural_records": weather_records, "unresolved_instances": unresolved}
		if stage == "ST0B": export_scene_door_records(stage, overlay, manifest["stages"][stage], dat_dir)
	manifest["exterior"] = {"asset_source": "Original ST02 atmosphere assets", "effects_manifest": "res://assets/opening/effects/manifest.json", "native_effect_class": 18, "native_effect_variant": 3, "bank": "ST02", "parameter": 0x01000001, "source_renderer": "ST02T0x800EC0A4", "stage_native_selection": "Unbound; original atmosphere reuse is selected by the runtime"}; manifest["map_blending"] = {"source": "SLES0x8002FA14-0x8002FA44", "packed_status": "first vertex flag&3", "semi_enabled": "status!=0", "tpage": "baseTPAGE|((status-1)<<5) when semi enabled"}; write_output(target, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
def export_weather_fields(dat_dir, output_dir):
	bindings = {"ST10": {"record": 0x800F7A90, "renderer": 0x800F36F8, "dispatch_table": 0x800F7A28, "areas": [0, 1], "callers": [0x800E7788, 0x800E7890]}, "ST11": {"record": 0x800F2EC0, "renderer": 0x800ED70C, "dispatch_table": 0x800F2D68, "areas": [0], "callers": [0x800E7748]}, "ST1D": {"record": 0x800FC3B0, "renderer": 0x800F8E8C, "dispatch_table": 0x800FC210, "areas": [0, 1], "callers": [0x800E7818, 0x800E79A8]}}; game_path = dat_dir.parent / "COMMON/GAME.BIN"; shared, _ = textures(game_path); result = {}; profiles = {}
	for stage, binding in bindings.items():
		path = dat_dir / (stage + "T.BIN"); data = path.read_bytes(); base = read_u32(data, 12); renderer = binding["renderer"]; source = data[48 + renderer - base:48 + renderer - base + 0x44C]
		if len(source) != 0x44C or read_u32(source, 0x368) >> 26 != 15 or read_u32(source, 0x368) & 65535 != 0x7C92: raise ValueError(f"{stage} weather field does not match its native renderer")
		descriptor_table = ((read_u32(source, 0x3C) & 65535) << 16) + struct.unpack_from("<h", source, 0x40)[0]; raw = data[48 + binding["record"] - base:48 + binding["record"] - base + 20]
		if raw[2] != 0xA0 or raw[3] & 8 == 0 or raw[4] != 9: raise ValueError(f"{stage} weather field record is not a custom small class9 actor")
		parameter = raw[6]; descriptor_ram = descriptor_table + ((parameter >> 1) & 56); descriptor = list(struct.unpack_from("<4h", data, 48 + descriptor_ram - base)); local, _ = textures(path); pixels = bytearray()
		for row in range(128):
			for column in range(128):
				word = read_u16(local, (((row + 128) * 1024 + 896 + (column >> 2)) * 2)); color = read_u16(shared, (498 * 1024 + 288 + ((word >> ((column & 3) * 4)) & 15)) * 2); pixels.extend((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 255 if color else 0))
		texture_name = stage.lower() + "_field.png"; write_output(output_dir / texture_name, png(128, 128, pixels)); image_uploads = []
		for offset in range(0, len(data) - 47, 0x400):
			if read_u32(data, offset) in (2, 3) and struct.unpack_from("<4H", data, offset + 20) == (896, 128, 64, 128): image_uploads.append(hex(offset))
		profile_id = stage + "_tiled_snow"; profiles[profile_id] = {"renderer_kind": "tiled_field", "texture": texture_name, "texture_source": {"image_archive": "DAT/" + path.name, "image_sections": image_uploads, "palette_archive": "COMMON/GAME.BIN", "palette_section": "0x39800", "tpage": "0x2E", "clut": "0x7C92", "uv": [0, 128, 128, 128]}, "descriptor": descriptor, "parameter": parameter, "columns": 11, "rows": 9, "tile_pixels": 32, "source": {"renderer": hex(renderer), "descriptor_table": hex(descriptor_table), "descriptor": hex(descriptor_ram), "record": hex(binding["record"]), "record_bytes": raw.hex(), "script_dispatch_table": hex(binding["dispatch_table"]), "spawn_calls": [hex(value) for value in binding["callers"]], "consumer": "GAME800C0818 ->800C05E0 ->SLES8003E8F8; custom small-particle table80078DCC class9", "draw": "GP0 Gouraud quad3E, additive TPAGE2E; 11 columns by9 rows, 32 native pixels; native camera oldYaw/oldPitch offset", "spawn_guard": "0x680 is a registration guard for ST10/ST11; setting it prevents duplicate allocation and does not hide the existing field"}}
		row = read_u32(data, 48 + binding["dispatch_table"] - base + 4); gate = {"native_save_byte14": 1}; initial = list(struct.unpack_from("<3h", raw, 12))
		result[stage] = {str(area): [{"profile_id": profile_id, "gate": gate, "initial_scroll_raw": [initial[0], initial[2]], "ordering_table_slot": read_u16(raw, 8), "dispatch_row": hex(row), "area_callback": hex(read_u32(data, 48 + row - base + area * 4))}] for area in binding["areas"]}
	return profiles, result
def export_weather(dat_dir=None, output_dir=None):
	dat_dir = Path(dat_dir) if dat_dir else ROOT / "build/disc-assets/DAT"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/weather"; output_dir.mkdir(parents=True, exist_ok=True); reference = (dat_dir / "ST08T.BIN").read_bytes(); executable = (dat_dir.parent / "SLES_035.56").read_bytes(); reference_base = read_u32(reference, 12)
	def payload(data, address, size):
		offset = 48 + address - read_u32(data, 12)
		return data[offset:offset + size] if 48 <= offset and offset + size <= min(len(data), 48 + read_u32(data, 4)) else b""
	ctor_signature = hashlib.sha256(payload(reference, 0x800EDCA4, 0xA8)).digest(); sprite_signature = hashlib.sha256(payload(reference, 0x800EDB80, 0x124)).digest()
	def callback_tables(data):
		base = read_u32(data, 12); size = min(read_u32(data, 4), len(data) - 48); words = struct.unpack_from("<%dI" % (size // 4), data, 48); found = set()
		for index, word in enumerate(words):
			if word >> 26 != 43 or word & 65535 != 0x8DE0: continue
			registers = {0: 0, 28: 0x8007890C}
			for instruction in words[max(0, index - 12):index + 1]:
				op = instruction >> 26; rs = instruction >> 21 & 31; rt = instruction >> 16 & 31; imm = instruction & 65535; signed = imm - 65536 if imm & 32768 else imm
				if op == 15: registers[rt] = imm << 16
				elif op in (9, 13) and rs in registers: registers[rt] = ((registers[rs] + signed) if op == 9 else registers[rs] | imm) & 0xFFFFFFFF
				elif op == 43 and rs in registers and rt in registers and (registers[rs] + signed) & 0xFFFFFFFF == 0x80078DE0 and base <= registers[rt] < base + size: found.add(registers[rt])
		return found
	def weather_profile(data, dispatcher):
		code = payload(data, dispatcher, 52)
		if len(code) != 52: return None
		words = struct.unpack("<13I", code)
		if words[3] != 0x90820008 or words[5] != 0x00021080 or words[6] != 0x00431021 or words[9] != 0x0040F809: return None
		table = ((words[1] & 65535) << 16) + ((words[4] & 32767) - (words[4] & 32768)); record = payload(data, table, 24)
		if len(record) != 24: return None
		ctor, update, initial, spawn, no_op, expire = struct.unpack("<6I", record)
		if hashlib.sha256(payload(data, ctor, 0xA8)).digest() != ctor_signature or initial <= update or initial - update > 0x800: return None
		body = payload(data, update, initial - update); renderer = None
		for offset in range(0, len(body) - 3, 4):
			word = read_u32(body, offset)
			if word >> 26 == 3:
				target = 0x80000000 | (word & 0x3FFFFFF) << 2
				if hashlib.sha256(payload(data, target, 0x124)).digest() == sprite_signature: renderer = target
		return {"dispatcher": hex(dispatcher), "state_table": hex(table), "constructor": hex(ctor), "update": hex(update), "initial_fill": hex(initial), "spawn": hex(spawn), "expire": hex(expire), "renderer": hex(renderer)} if renderer else None
	vram, _ = textures(dat_dir.parent / "COMMON/GAME.BIN"); pixels = bytearray()
	for row in range(32):
		for column in range(32):
			u = column + 32; word = read_u16(vram, ((row + 32) * 1024 + 960 + (u >> 2)) * 2); index = (word >> ((u & 3) * 4)) & 15; color = read_u16(vram, (497 * 1024 + 256 + index) * 2); pixels.extend((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 255 if color else 0))
	write_output(output_dir / "snow.png", png(32, 32, pixels)); stages = {}; unresolved = []
	for root_path in sorted(dat_dir.glob("ST??.BIN")):
		stage = root_path.stem; overlay_path = dat_dir / (stage + "T.BIN")
		if not overlay_path.is_file(): continue
		data = overlay_path.read_bytes(); base = read_u32(data, 12); area_count = len(Stage(root_path.read_bytes()).grids); tables = {item["pointer_ram"]: item for item in native_area_tables(data)["actors"]}; profiles = {}; emitters = {}
		for table in callback_tables(data):
			for actor_class in range(32):
				entry = payload(data, table + actor_class * 4, 4)
				if len(entry) != 4: continue
				row = read_u32(entry, 0)
				if not row: continue
				entry = payload(data, row, 4)
				if len(entry) != 4: continue
				profile = weather_profile(data, read_u32(entry, 0))
				if profile: profiles[actor_class] = {**profile, "callback_table": hex(table), "callback_row": hex(row)}
		for table, binding in tables.items():
			for area in range(area_count):
				entry = payload(data, table + area * 4, 4)
				if len(entry) != 4: continue
				pointer = read_u32(entry, 0)
				for index in range(128):
					raw = payload(data, pointer + index * 20, 20)
					if len(raw) != 20 or raw[0] == 255: break
					if raw[2] not in (0x60, 0x61) or raw[4] not in profiles or raw[5] != 0 or not raw[0] & 1: continue
					item = {"source_ram": hex(pointer + index * 20), "source_bytes": raw.hex(), "actor_class": raw[4], "native_variant": raw[6], "wind_raw": list(struct.unpack("<3b", raw[8:11])), "period_ticks": raw[11] or 30, "prewarm": bool(raw[6]), "profile": profiles[raw[4]]}
					emitters.setdefault(str(area), {})[item["source_ram"]] = item
		if len(tables) > 1 and emitters: unresolved.append({"stage": stage, "reason": "Multiple native area-object tables require source conditional selection"}); emitters = {}
		stages[stage] = {"areas": {key: list(value.values()) for key, value in emitters.items()}, "source": {"overlay": "DAT/" + overlay_path.name, "sha256": hashlib.sha256(data).hexdigest(), "area_actor_tables": [{**item, "pointer_ram": hex(pointer)} for pointer, item in tables.items()]}}
	field_profiles, field_stages = export_weather_fields(dat_dir, output_dir)
	for stage, areas in field_stages.items(): stages[stage]["fields"] = areas
	if "ST0D" in stages: stages["ST0D"]["weather_audit"] = {"ambient_binding": "unbound", "area_dispatch": "ST0DT800E72E4 selects table800F05B8 by native save byte14 then area", "traced_state_values": list(range(21)), "scripted_registration_records": ["800F0620", "800F0634", "800F0648", "800F065C"], "registration_type": "All four records are type20 PBD actors; all area1 callbacks are no-ops", "custom_particle_tables": {"large": "800EFE40:only class0 row points to0", "small": "800EFE48:zero"}, "excluded_particle_spawns": [{"caller": "800E93EC", "pool": "small custom", "class": 16}, {"caller": "800EAAB4", "pool": "small shared", "class": 0}, {"caller": "800EAEBC", "pool": "large shared", "class": 8}, {"caller": "800EB214", "pool": "small custom", "class": 1}, {"caller": "800EE08C", "pool": "small shared", "class": 0, "source_gate": "Class7E movement state; actor position with64-unit particle size, alternate native ticks"}], "source_limit": "No ambient snowfall binding found in the traced initializer, static area lists, area dispatcher, or direct particle allocations; no replacement field is selected from terrain appearance"}
	trig = [list(struct.unpack_from("<2h", executable, 0x800 + 0x80073E4C - 0x80010000 + phase * 4)) for phase in range(4096)]
	manifest = {"schema": 1, "profiles": field_profiles, "tick_rate": 25, "viewport": [320, 240], "particle_count": 32, "texture": "snow.png", "texture_source": {"archive": "COMMON/GAME.BIN", "tpage": "0x2F", "clut": "0x7C50", "uv": [32, 32, 32, 32], "blend": "Native GP0 opcode2E with additive TPAGE mode1; nonzero sprite texels are exported opaque for additive compositing"}, "source": {"record_parser": "SLES8003D3F8 20-byte type60/61 records", "callback_binding": "SLES8003CC58..3CC84 indexes source stage table80078DE0 with actor+4/+5", "reference": "ST08T800ED6BC/EDCA4/EDD4C/EDB80", "timing": "PAL GAME800AE948 ->SLES8001136C(a0=0),divider2 at50fields; GAME800B0244 ->8003CBD0 once per update", "particle_word": "x+180:bits0..8; y:bits9..17; depth:bits18..27", "screen_ranges": {"x": [-180, 180], "y": [0, 280], "depth": [0, 1024]}, "initial_depth": [200, 1023], "draw_minimum_depth": 100, "sprite_size": "1+((1024-depth)>>8)", "sprite_color": "64+(depth>>3)", "rng": "((state<<1)+(state>>31)+1)^873CA9E5 modulo2^32", "trig_table": "SLES80073E4C", "camera_source": {"current_eye": "8007D010+2C/30/34", "previous_eye": "8007D010+3C/40/44", "eye_writer": "SLES80015DB0..80015E24", "displacement": "previous-current, added to source wind", "current_angles": "8007D010+7C/7E", "previous_angles": "8007D010+84/86", "angle_delta": "previous-current; current-angle sin/cos basis", "canonical_camera_adapter": "nativeEye=(-GodotX,-GodotY,+GodotZ)*256; nativePitch=GodotPitch; nativeYaw=PI-GodotYaw", "radial_terms": "ST08T800EDF68/800EDFA4 use signed16 depth velocity S2, not angular sine", "horizontal_rotation": "ST08T800EDF94 uses depth*yawDeltaSine>>13"}}, "trig4096": trig, "stages": stages, "unresolved": unresolved, "renderer_adapters": ["Native 320x240 screen positions scale to the current viewport; flake size preserves the native vertical pixel scale.", "PC camera positions and Euler angles feed the native integer compensation formulas.", "The independent weather RNG stream does not reproduce native interleaving with other actors.", "Canvas additive flakes do not reproduce native ordering-table occlusion against 3D geometry."]}; write_output(output_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n"); return manifest
def export_stage(dat_dir=None, output_dir=None, stages=None):
	dat_dir = Path(dat_dir) if dat_dir else ROOT / "build/disc-assets/DAT"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/levels"; stages = sorted(set(stages or STAGE_BINDINGS))
	if any(len(stage) != 4 or not stage.startswith("ST") or any(character not in "0123456789ABCDEF" for character in stage[2:]) for stage in stages): raise ValueError("Stage names must be original STxx hexadecimal identifiers")
	catalog = export_geometry(dat_dir, output_dir, stages); export_routes(dat_dir, output_dir, stages); props = export_props(dat_dir, output_dir.parent / "stage_props", stages); catalog["props_manifest"] = "res://" + (output_dir.parent / "stage_props/manifest.json").resolve().relative_to(ROOT).as_posix(); catalog["bindings"] = {stage: props["stages"][stage]["binding_status"] for stage in stages}; return catalog
def stage_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--stage", action="append"); parser.add_argument("--dat-dir", type=Path); parser.add_argument("--output-dir", type=Path); parser.add_argument("--props-only", action="store_true"); args = parser.parse_args()
	if args.props_only:
		props = export_props(args.dat_dir, args.output_dir.parent / "stage_props", args.stage); result = {"bindings": {stage: props["stages"][stage]["binding_status"] for stage in args.stage}, "props_manifest": "res://" + (args.output_dir.parent / "stage_props/manifest.json").resolve().relative_to(ROOT).as_posix()}
	else: result = export_stage(args.dat_dir, args.output_dir, args.stage)
	print(json.dumps({"stage_bindings": result["bindings"], "props_manifest": result["props_manifest"]}))

STAGES = ("ST04", "ST05", "ST06", "ST07")
UNIT_BASIS = [-1, -1, 1]
LADDER_PAIRS = {frozenset((("ST04", 1), ("ST06", 0))), frozenset((("ST06", 0), ("ST07", 0))), frozenset((("ST0F", 1), ("ST0F", 5))), frozenset((("ST0F", 9), ("ST0F", 10)))}

def read_glb(path):
	data = path.read_bytes()
	if struct.unpack_from("<I", data)[0] != 0x46546c67: raise ValueError(f"{path} is not a GLB")
	json_size, json_type = struct.unpack_from("<II", data, 12)
	if json_type != 0x4e4f534a: raise ValueError(f"{path} has no JSON chunk")
	document = json.loads(data[20:20 + json_size])
	binary_offset = 20 + json_size
	binary_size, binary_type = struct.unpack_from("<II", data, binary_offset)
	if binary_type != 0x004e4942: raise ValueError(f"{path} has no BIN chunk")
	return document, data[binary_offset + 8:binary_offset + 8 + binary_size]

def native_png_pixels(data):
	width, height = struct.unpack_from(">II", data, 16); offset = 8; chunks = []
	while offset < len(data):
		size = struct.unpack_from(">I", data, offset)[0]
		if data[offset + 4:offset + 8] == b"IDAT": chunks.append(data[offset + 8:offset + 8 + size])
		offset += size + 12
	rows = zlib.decompress(b"".join(chunks)); stride = width * 4 + 1
	if len(rows) != height * stride or any(rows[y * stride] != 0 for y in range(height)): raise ValueError("Native exporter PNG must contain unfiltered RGBA rows")
	return width, height, b"".join(rows[y * stride + 1:(y + 1) * stride] for y in range(height))
def glb_used_texels(document, binary, primitive, width, height):
	accessor = document["accessors"][primitive["attributes"]["TEXCOORD_0"]]; view = document["bufferViews"][accessor["bufferView"]]; offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0); uvs = [struct.unpack_from("<2f", binary, offset + index * view.get("byteStride", 8)) for index in range(accessor["count"])]
	if "indices" in primitive:
		accessor = document["accessors"][primitive["indices"]]; view = document["bufferViews"][accessor["bufferView"]]; offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0); code = "H" if accessor["componentType"] == 5123 else "I"; size = struct.calcsize(code); indices = struct.unpack_from("<" + code * accessor["count"], binary, offset)
	else: indices = range(len(uvs))
	pixels = set()
	for start in range(0, len(indices), 3):
		points = [(uvs[indices[start + corner]][0] * width, uvs[indices[start + corner]][1] * height) for corner in range(3)]; area = (points[1][0] - points[0][0]) * (points[2][1] - points[0][1]) - (points[1][1] - points[0][1]) * (points[2][0] - points[0][0])
		for x, y in points: pixels.add(min(height - 1, max(0, int(y))) * width + min(width - 1, max(0, int(x))))
		if abs(area) < 0.000001: continue
		for y in range(max(0, int(min(point[1] for point in points))), min(height - 1, int(max(point[1] for point in points))) + 1):
			for x in range(max(0, int(min(point[0] for point in points))), min(width - 1, int(max(point[0] for point in points))) + 1):
				values = [(points[(corner + 1) % 3][0] - points[corner][0]) * (y + 0.5 - points[corner][1]) - (points[(corner + 1) % 3][1] - points[corner][1]) * (x + 0.5 - points[corner][0]) for corner in range(3)]
				if all(value >= -0.00001 for value in values) or all(value <= 0.00001 for value in values): pixels.add(y * width + x)
	return pixels
def audit_door_textures(dat_dir, repair=False):
	props_path = ROOT / "assets/stage_props/manifest.json"; props = json.loads(props_path.read_text(encoding="utf-8")); report = {"stages_checked": 0, "resources_checked": 0, "affected_resources": [], "fully_transparent_materials": [], "repaired_resources": []}; work = ROOT / "build/stages"
	for stage, metadata in props["stages"].items():
		resources = metadata.get("native_doors", [])
		if not resources: continue
		report["stages_checked"] += 1; vram = bytearray(1024 * 512 * 2); uploads = []
		for bank in SHARED_TEXTURES:
			path = dat_dir.parent / bank
			if path.is_file(): uploads.extend(texture_uploads(path.read_bytes(), vram, bank))
		for name in [stage + "T.BIN", stage + ".BIN"]: uploads.extend(texture_uploads((dat_dir / name).read_bytes(), vram, "DAT/" + name))
		pages = {}; affected = []
		for resource in resources:
			path = ROOT / "assets/stage_props" / resource["model_file"]; document, binary = read_glb(path); tpage = document["extras"]["texture_tpage"]; clut = document["extras"]["texture_clut"]; key = (tpage, clut)
			if key not in pages: pages[key] = decode_page(vram, tpage, clut)
			expected = pages[key]; changed = False; report["resources_checked"] += 1
			for mesh in document["meshes"]:
				for material_index, primitive in enumerate(mesh["primitives"]):
					material = document["materials"][primitive["material"]]; image = document["images"][document["textures"][material["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]; view = document["bufferViews"][image["bufferView"]]; width, height, current = native_png_pixels(binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]])
					if width != 256 or height != 256: raise ValueError("Native door texture is not a 256-pixel source page")
					if current == expected: continue
					used = glb_used_texels(document, binary, primitive, width, height); differing = sum(current[index * 4:index * 4 + 4] != expected[index * 4:index * 4 + 4] for index in used)
					if not differing: continue
					changed = True; old_opaque = sum(current[index * 4 + 3] >= 128 for index in used); new_opaque = sum(expected[index * 4 + 3] >= 128 for index in used); row = {"stage": stage, "model_index": resource["model_index"], "material": material_index, "tpage": hex(tpage), "clut": hex(clut), "used_texels": len(used), "changed_used_texels": differing, "old_opaque_texels": old_opaque, "native_opaque_texels": new_opaque}; report["affected_resources"].append(row)
					if old_opaque == 0 and new_opaque > 0: report["fully_transparent_materials"].append(row)
			if changed: affected.append(resource)
		if repair and affected:
			header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / (stage + "_vram.bin"); write_output(texture_path, header + vram); source = (dat_dir / (stage + ".BIN")).read_bytes(); doors_path = ROOT / "assets/levels" / stage / "doors.json"; door_data = json.loads(doors_path.read_text(encoding="utf-8")); flags = {0x61 | (int(route["native_door"]["controller_class"]) << 8) | (int(variant) << 16) for route in door_data["area_transitions"] if route.get("native_door") for variant in route["native_door"]["variants"]}; archive = actor_archive_for_records(stage, source, [], work, dat_dir, metadata["source"].get("actor_archive_section"), flags)
			if archive is None: raise ValueError(stage + " native door archive is not uniquely bound")
			for resource in affected:
				path = ROOT / "assets/stage_props" / resource["model_file"]; export_static_actor(archive["payload"], resource["model_index"], texture_path, path, archive["archive_file"]); report["repaired_resources"].append({"stage": stage, "model_index": resource["model_index"], "file": resource["model_file"]})
			metadata["source"]["texture_uploads"] = uploads
	if repair: write_output(props_path, json.dumps(props, indent=2) + "\n", encoding="utf-8")
	write_output(ROOT / "build/maps/door_texture_audit.json", json.dumps(report, indent=2) + "\n", encoding="utf-8"); return report
def door_textures_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=ROOT / "build/disc-assets/DAT"); parser.add_argument("--repair", action="store_true"); args = parser.parse_args(); report = audit_door_textures(args.dat_dir, args.repair); print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in report.items()}))

def room_faces(assets_dir, stage, area):
	path = assets_dir / stage / f"area_{area:02d}.glb"; document, binary = read_glb(path); faces = []
	for node_index, node in enumerate(document["nodes"]):
		if "mesh" not in node: continue
		translation = node.get("translation", [0, 0, 0]); rotation = node.get("rotation", [0, 0, 0, 1]); scale = node.get("scale", [1, 1, 1])
		if rotation != [0, 0, 0, 1] or scale != [1, 1, 1]: raise ValueError(f"{path} has a transformed map node {node['name']}")
		for primitive_index, primitive in enumerate(document["meshes"][node["mesh"]]["primitives"]):
			accessor = document["accessors"][primitive["attributes"]["POSITION"]]; view = document["bufferViews"][accessor["bufferView"]]; start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
			if accessor["componentType"] != 5126 or accessor["type"] != "VEC3" or accessor["count"] % 6: raise ValueError(f"{path} has a non-quad position surface")
			positions = [struct.unpack_from("<3f", binary, start + index * 12) for index in range(accessor["count"])]
			for quad_index in range(0, accessor["count"] // 6):
				index = quad_index * 6; triangles = [[positions[index + i] for i in (0, 1, 2)], [positions[index + i] for i in (3, 4, 5)]]; quad_local = [positions[index + i] for i in (0, 2, 1, 5)]; quad = [tuple(point[axis] + translation[axis] for axis in range(3)) for point in quad_local]
				faces.append({"node": node["name"], "node_index": node_index, "mesh_index": node["mesh"], "primitive_index": primitive_index, "material_index": primitive.get("material", -1), "quad_index": quad_index, "quad": quad, "triangles_local": triangles})
	return path, faces

def native_point(raw): return (-raw[0] / 256.0, 0.0 if raw[1] == -1 else -raw[1] / 256.0, raw[2] / 256.0)

def route_center(route, reverse, source_side):
	source = native_point(route["source_transform_raw"] if source_side else reverse["source_transform_raw"]); arrival = native_point(reverse["destination_transform_raw"] if source_side else route["destination_transform_raw"]); center = tuple((source[axis] + arrival[axis]) * 0.5 for axis in range(3)); axis = 0 if abs(source[0] - arrival[0]) > abs(source[2] - arrival[2]) else 2
	if abs(source[axis] - arrival[axis]) < 1e-6: raise ValueError("route endpoints do not identify a portal axis")
	return center, axis

def select_panel(faces, center, axis):
	lateral = 2 if axis == 0 else 0; groups = {}
	for face in faces:
		points = face["quad"]; normal = [point[axis] for point in points]; side = [point[lateral] for point in points]; vertical = [point[1] for point in points]
		if max(normal) - min(normal) > 0.002: continue
		width = max(side) - min(side); height = max(vertical) - min(vertical); plane = sum(normal) / 4; side_center = sum(side) / 4
		if abs(plane - center[axis]) > 0.65 or not 0.2 <= width <= 2.0 or not 0.3 <= height <= 1.75: continue
		if not min(side) - 0.15 <= center[lateral] <= max(side) + 0.15 or max(vertical) < center[1] + 0.3 or min(vertical) > center[1] + 1.1: continue
		key = (face["node"], face["mesh_index"], face["primitive_index"], face["material_index"], round(plane, 3)); groups.setdefault(key, []).append(face)
	candidates = []
	for (node, mesh_index, primitive_index, material_index, plane), quads in groups.items():
		points = [point for face in quads for point in face["quad"]]; mins = [min(point[i] for point in points) for i in range(3)]; maxs = [max(point[i] for point in points) for i in range(3)]; width = maxs[lateral] - mins[lateral]; height = maxs[1] - mins[1]; side_center = (mins[lateral] + maxs[lateral]) * 0.5; score = abs(plane - center[axis]) + abs(side_center - center[lateral]) + abs(mins[1] - center[1]) + abs(maxs[1] - center[1] - 1.0) + 0.05 * abs(width - 0.625)
		candidates.append((score, node, mesh_index, primitive_index, material_index, plane, mins, maxs, quads))
	if not candidates: raise ValueError(f"no static panel face near route portal {center}")
	candidates.sort(key=lambda item: item[0]); best = candidates[0]; _, node, mesh_index, primitive_index, material_index, plane, mins, maxs, quads = best; selected_quads = list(quads); selected_signatures = {tuple(sorted(tuple(round(value * 65536) for value in point) for point in face["quad"])) for face in selected_quads}
	for face in faces:
		if face["node"] != node or face["mesh_index"] != mesh_index: continue
		points = face["quad"]; normal = [point[axis] for point in points]; side = [point[lateral] for point in points]; vertical = [point[1] for point in points]
		signature = tuple(sorted(tuple(round(value * 65536) for value in point) for point in points))
		if signature in selected_signatures or max(normal) - min(normal) > 0.002 or abs(sum(normal) / 4 - plane) > 0.002: continue
		if min(side) < mins[lateral] - 0.02 or max(side) > maxs[lateral] + 0.02: continue
		inside_panel = min(vertical) >= min(center[1], mins[1]) - 0.002 and max(vertical) <= max(center[1] + 1.0, maxs[1]) + 0.002
		bottom_strip = min(vertical) >= center[1] - 0.01 and max(vertical) <= mins[1] + 0.002 and max(vertical) - min(vertical) <= 0.25
		if not inside_panel and not bottom_strip: continue
		selected_quads.append(face); selected_signatures.add(signature)
	selected_points = [point for face in selected_quads for point in face["quad"]]; bound_mins = [min(point[i] for point in selected_points) for i in range(3)]; bound_maxs = [max(point[i] for point in selected_points) for i in range(3)]; bounds = {"min": bound_mins, "max": bound_maxs}; face_center = [(bound_mins[i] + bound_maxs[i]) * 0.5 for i in range(3)]; match = re.fullmatch(r"placement_(\d+)_model_(\d+)", node)
	if not match: raise ValueError(f"unexpected map placement node {node}")
	return {"center": face_center, "axis": axis, "bounds": bounds, "placement_id": int(match.group(1)), "model_id": int(match.group(2)), "node": node, "mesh_index": mesh_index, "primitive_index": primitive_index, "material_index": material_index, "quads": [{"quad_index": face["quad_index"], "primitive_index": face["primitive_index"], "first_vertex": face["quad_index"] * 6, "first_triangle": face["quad_index"] * 2, "triangle_count": 2, "triangles_local": face["triangles_local"]} for face in selected_quads], "score": best[0]}

FLUTTER_LADDER_STAGES = {"ST04", "ST05", "ST06", "ST07"}
TOWN_STAGES = {"ST09", "ST19"}
TOWN_AREAS = {"ST47": {0}, "ST19": {1}, "ST1B": {0, 1, 2, 3}}
TOWN_EXTERIORS = {("ST09", 0), ("ST19", 1)}

def ladder_link(assets_dir, room_catalog, route, reverse, a, b):
	"""Stack the two rooms of a ladder pair: the lower room's ceiling hatch (its black-out loop height) meets the bottom of the upper room's ladder pit, with the two ladder foot points (each route's source transform) on one vertical line."""
	down = (int(route["door_mode"]) & 15) not in (0, 2); upper, lower = (a, b) if down else (b, a)
	roofs = assets_dir / lower[0] / "area_roofs.json"
	if not roofs.is_file(): return None
	heights = [point[1] for entry in json.loads(roofs.read_text(encoding="utf-8"))["areas"] if entry["area"] == lower[1] for loop in entry["roof"].get("blackouts", []) for point in loop]
	pit = room_catalog[upper]["bounds"]["min"][1]
	if not heights or pit >= 0: return None
	hatch = math.floor(max(heights) * 256) / 256; source = native_point(route["source_transform_raw"]); arrival = native_point(reverse["source_transform_raw"]); rise = hatch - pit
	return {"delta": [source[0] - arrival[0], -rise if down else rise, source[2] - arrival[2]], "upper": {"stage": upper[0], "area": upper[1]}, "lower": {"stage": lower[0], "area": lower[1]}, "hatch_height": hatch, "pit_depth": pit}

def export_room_layout(assets_dir, output_path, stages=STAGES):
	STAGES = stages; town = bool(TOWN_STAGES & set(stages))
	room_catalog = {}; route_data = {}; route_hashes = {}; external = []
	for stage in STAGES:
		manifest_path = assets_dir / stage / "manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8")); stage_areas = {area["index"]: area for area in manifest["areas"]}; route_path = assets_dir / stage / "doors.json"; route_file = json.loads(route_path.read_text(encoding="utf-8")); route_data[stage] = route_file["area_transitions"]; route_hashes[stage] = hashlib.sha256(route_path.read_bytes()).hexdigest()
		for index, area in stage_areas.items():
			if town and index not in TOWN_AREAS.get(stage, {index}): continue
			room_catalog[(stage, index)] = {"manifest": f"assets/levels/{stage}/manifest.json", "file": area["file"], "bounds": area["bounds"]}
	all_routes = [(stage, route) for stage, routes in route_data.items() for route in routes]; edges = []; ladder_transitions = []; ladder_edges = []; paired = set()
	for stage, route in all_routes:
		a = (stage, route["source_area"]); b = (route["destination_stage"], route["destination_area"])
		if a not in room_catalog: continue
		if b not in room_catalog or (town and not route.get("native_door", {}).get("style", "").startswith("hinged")):
			external.append({"source_stage": stage, "source_area": a[1], "destination_stage": b[0], "destination_area": b[1], "door_id": route["door_id"], "source_transform_raw": route["source_transform_raw"], "destination_transform_raw": route["destination_transform_raw"], "file_offset": route["file_offset"]}); continue
		if (a, b) in paired or (b, a) in paired: continue
		reverses = [other for other in route_data[b[0]] if other["source_area"] == b[1] and other["destination_stage"] == a[0] and other["destination_area"] == a[1]]
		if len(reverses) != 1: raise ValueError(f"{a} to {b} has {len(reverses)} reciprocal routes")
		reverse = reverses[0]; paired.update(((a, b), (b, a)))
		if frozenset((a, b)) in LADDER_PAIRS:
			link = ladder_link(assets_dir, room_catalog, route, reverse, a, b) if a[0] in FLUTTER_LADDER_STAGES and b[0] in FLUTTER_LADDER_STAGES else None
			ladder_transitions.append({"source": {"stage": a[0], "area": a[1]}, "destination": {"stage": b[0], "area": b[1]}, "door_id": route["door_id"], "door_mode": route["door_mode"], "reverse_door_mode": reverse["door_mode"], "source_route_file_offset": route["file_offset"], "reverse_route_file_offset": reverse["file_offset"], "source_transform_raw": route["source_transform_raw"], "destination_transform_raw": route["destination_transform_raw"], "seamless": link is not None, **(link or {})})
			if link: ladder_edges.append({"a": a, "b": b, "delta": tuple(link["delta"])})
			continue
		native_a = route.get("native_door", {}).get("source_panel"); native_b = reverse.get("native_door", {}).get("source_panel")
		if not (native_a and native_b): center_a, axis_a = route_center(route, reverse, True); center_b, axis_b = route_center(route, reverse, False)
		if not (native_a and native_b) and axis_a != axis_b: raise ValueError(f"{a} to {b} uses different local portal axes")
		path_a = assets_dir / a[0] / f"area_{a[1]:02d}.glb"; path_b = assets_dir / b[0] / f"area_{b[1]:02d}.glb"; face_a = native_a or select_panel(room_faces(assets_dir, *a)[1], center_a, axis_a); face_b = native_b or select_panel(room_faces(assets_dir, *b)[1], center_b, axis_b)
		if face_a["axis"] != face_b["axis"]: raise ValueError(f"{a} to {b} panel normal axes disagree")
		translation = tuple((-route["source_transform_raw"][1] + reverse["source_transform_raw"][1]) / 256 if town and i == 1 else face_a["center"][i] - face_b["center"][i] for i in range(3)); edges.append({"a": a, "b": b, "route": route, "reverse": reverse, "panel_a": face_a, "panel_b": face_b, "delta": translation, "glb_a": path_a, "glb_b": path_b})
	adjacency = {}
	for edge in edges + ladder_edges:
		adjacency.setdefault(edge["a"], []).append((edge["b"], edge["delta"])); adjacency.setdefault(edge["b"], []).append((edge["a"], tuple(-value for value in edge["delta"])))
	offsets = {}; components = []; residuals = []
	for anchor in sorted(room_catalog):
		if anchor in offsets: continue
		offsets[anchor] = (0.0, 0.0, 0.0); stack = [anchor]; component = []
		while stack:
			node = stack.pop(); component.append(node)
			for other, delta in adjacency.get(node, []):
				proposal = tuple(offsets[node][axis] + delta[axis] for axis in range(3))
				if other not in offsets: offsets[other] = proposal; stack.append(other)
				elif max(abs(offsets[other][axis] - proposal[axis]) for axis in range(3)) > 1e-5: residuals.append({"from": list(node), "to": list(other), "residual": [offsets[other][axis] - proposal[axis] for axis in range(3)]})
		components.append(sorted(component))
	if len(offsets) != len(room_catalog) or residuals: raise ValueError(f"room layout does not close: reached {len(offsets)}/{len(room_catalog)} rooms with {len(residuals)} residuals")
	rooms = [{"stage": stage, "area": area, "manifest": data["manifest"], "file": data["file"], "world_offset": offsets[(stage, area)], "rotation_y": 0.0, "local_bounds": data["bounds"], "routes_remain_area_local": True, "exterior": (town and (stage, area) in TOWN_EXTERIORS) or (stage, area) == ("ST08", 0)} for (stage, area), data in sorted(room_catalog.items())]
	portals = []
	for edge in edges:
		a, b, pa, pb = edge["a"], edge["b"], edge["panel_a"], edge["panel_b"]; wa = [pa["center"][i] + offsets[a][i] for i in range(3)]; wb = [pb["center"][i] + offsets[b][i] for i in range(3)]; axis = pa["axis"]; lateral = 2 if axis == 0 else 0; size = [min(pa["bounds"]["max"][lateral] - pa["bounds"]["min"][lateral], pb["bounds"]["max"][lateral] - pb["bounds"]["min"][lateral]), min(pa["bounds"]["max"][1] - pa["bounds"]["min"][1], pb["bounds"]["max"][1] - pb["bounds"]["min"][1])]; center = [(wa[i] + wb[i]) * 0.5 for i in range(3)]; portal = {"source": {"stage": a[0], "area": a[1]}, "destination": {"stage": b[0], "area": b[1]}, "door_id": edge["route"]["door_id"], "door_mode": edge["route"]["door_mode"], "source_route_file_offset": edge["route"]["file_offset"], "reverse_route_file_offset": edge["reverse"]["file_offset"], "source_contact_raw": edge["route"]["source_transform_raw"], "source_slot": edge["route"]["door_slot"], "reverse_source_slot": edge["reverse"]["door_slot"], "source_yaw_raw": edge["route"]["source_transform_raw"][3], "reverse_source_contact_raw": edge["reverse"]["source_transform_raw"], "reverse_source_yaw_raw": edge["reverse"]["source_transform_raw"][3], "destination_contact_raw": edge["route"]["destination_transform_raw"], "source_panel": pa, "destination_panel": pb, "world_center": center, "normal_axis": "x" if axis == 0 else "z", "panel_center_error": max(abs(wa[i] - wb[i]) for i in range(3)), "shared_panel_size": size, "static_map_face": True, "source_native_door": edge["route"].get("native_door", {}), "reverse_native_door": edge["reverse"].get("native_door", {})};
		if town:
			bottom = max(pa["bounds"]["min"][1] + offsets[a][1], pb["bounds"]["min"][1] + offsets[b][1]); top = min(pa["bounds"]["max"][1] + offsets[a][1], pb["bounds"]["max"][1] + offsets[b][1]); portal["world_center"][1] = (bottom + top) * 0.5; portal["shared_panel_size"][1] = top - bottom
		portals.append(portal)
	components_json = [[{"stage": stage, "area": area} for stage, area in component] for component in components]; anchor = components[0][0] if components else ("", 0); ladder_transitions.sort(key=lambda item: (item["source"]["stage"], item["source"]["area"], item["destination"]["stage"], item["destination"]["area"]))
	manifest = {"coordinate_basis": {"native_to_godot": UNIT_BASIS, "unit": "1/256 map unit", "rotation": "identity for every room"}, "parked_exterior_enabled": "ST04" in STAGES, "placement_source": "reciprocal native Flutter door routes matched to static door-face quads in area GLBs; ladder pairs stack their rooms at the ladder foot points", "anchor": {"stage": anchor[0], "area": anchor[1], "world_offset": [0, 0, 0]}, "graph": {"room_count": len(rooms), "reciprocal_edge_count": len(edges), "connected": len(components) == 1, "component_count": len(components), "is_tree": len(components) == 1 and len(edges) == len(rooms) - 1, "is_forest": len(edges) == len(rooms) - len(components), "components": components_json, "cycle_residuals": residuals}, "rooms": rooms, "portals": portals, "ladder_transitions": ladder_transitions, "external_routes": external, "route_data_remains_local": True, "source_sha256": {stage: {"manifest": hashlib.sha256((assets_dir / stage / "manifest.json").read_bytes()).hexdigest(), "doors": route_hashes[stage]} for stage in STAGES}}
	output_path.parent.mkdir(parents=True, exist_ok=True); write_output(output_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"Flutter room layout: {len(rooms)} rooms, {len(portals)} paired portals, {len(external)} external routes -> {output_path}"); return manifest

def export_stage_regions(output_path):
	game = GAME_PATH.read_bytes(); base = struct.unpack_from("<I", game, 0xc)[0]; table = 0x800DBDA0; count = 0x5D
	return write_output(output_path, json.dumps({"source": {"file": str(GAME_PATH.relative_to(ROOT)), "sha256": hashlib.sha256(game).hexdigest(), "table_ram": hex(table), "consumer": "GAME 0x800BA374 stores table[stage] to game+0x12 unless 0xFF, then 0x800BA420 counts region changes", "counter_function": "0x800BA420", "counter_bytes": "game+0x7C..0x83 (non-zero, below 0xFF, incremented once per region change at stage >= 8)", "last_region_byte": "game+0x84"}, "regions": list(game[48 + table - base:48 + table - base + count])}, indent=2) + "\n", encoding="utf-8")
def room_layout_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--assets-dir", type=Path, default=ROOT / "assets/levels"); parser.add_argument("--output", type=Path, default=ROOT / "assets/locations/room_layout.json"); parser.add_argument("--overwrite", action="store_true"); args = parser.parse_args(); disc.configure_overwrite(args.overwrite); export_room_layout(args.assets_dir, args.output)
SHOP_ROOT = Path(__file__).resolve().parent.parent
SHOP_OUTPUT = SHOP_ROOT / "assets/shops"
"""Shop scene data (junk shops, general stores): the shop module and its data are identical in every shop stage overlay; the overlay message bank, stock tables and item catalog are exported to assets/shops."""
SHOP_BASE = 0x800E7000
SHOP_SLES_BASE = 0x80010000
SHOP_STAGES = ["ST0A", "ST1A", "ST1B", "ST25", "ST29", "ST3B", "ST3F"]
# offsets from the scene init function (the function holding the 0x6FE test): (lui, addiu) instruction pairs and the register they load
SHOP_ANCHORS = {"bank": (0x314, 0x328, 5, 5), "set_rows": (0x308, 0x30C, 3, 3), "stock_b": (0x21E4, 0x21E8, 2, 21), "stock_a": (0x21EC, 0x21F0, 2, 20), "categories": (0x1EC0, 0x1EC4, 2, 2), "scene_table": (-0x38, -0x2C, 3, 3), "unsellable": (0x1EE8, 0x1EEC, 4, 3)}
SHOP_LENGTHS = {0x05: 4, 0x06: 8, 0x08: 4, 0x0A: 3, 0x0C: 2, 0x1A: 6, 0x22: 3, 0x09: 3, 0x0E: 3, 0x0F: 3, 0x10: 3, 0x11: 3, 0x15: 13, 0x16: 6, 0x18: 2, 0x19: 4, 0x1D: 2, 0x21: 3, 0x24: 2, 0x26: 4, 0x27: 4, 0x28: 6, 0x29: 3, 0x2A: 7, 0x2B: 2, 0x2C: 3, 0x30: 3, 0x31: 2, 0x33: 3, 0x37: 7, 0x38: 3, 0x39: 3, 0x3E: 4, 0x3F: 5, 0x0B: 2, 0x20: 4, 0x3C: 14, 0x40: 4, 0x42: 9, 0x47: 6}
SHOP_ITEM_FIRST = 0x380
SHOP_ITEM_LAST = 0x485
SHOP_PRICE_TABLE = 0x80070FC8 - 0x700
SHOP_SPECIAL_PRICES = {"bionic": (0x800711C8, 5), "extra": (0x800711D4, 15), "medicine": (0x800711F4, 15)}
SHOP_DESCRIPTION_BANK = 0x8006DDAC
def shop_word(blob, address, base): return struct.unpack_from("<I", blob, 0x30 + address - base)[0]
def shop_immediate(blob, address, expected_op, expected_rt, expected_rs=None):
	value = shop_word(blob, address, SHOP_BASE); op = value >> 26
	if op != expected_op or ((value >> 16) & 31) != expected_rt or expected_rs is not None and ((value >> 21) & 31) != expected_rs: raise ValueError(f"shop anchor {address:#x}: unexpected instruction {value:08x}")
	return value & 0xFFFF
def shop_address_of(blob, init, anchor, load=False):
	hi_offset, lo_offset, hi_reg, lo_reg = SHOP_ANCHORS[anchor]; hi = shop_immediate(blob, init + hi_offset, 0x0F, hi_reg); lo = shop_immediate(blob, init + lo_offset, 0x21 if load else 9, lo_reg, hi_reg)
	return ((hi << 16) + (lo - 0x10000 if lo & 0x8000 else lo)) & 0xFFFFFFFF
def shop_locate_init(blob):
	hits = [SHOP_BASE + offset - 0x30 for offset in range(0x30, len(blob) - 3, 4) if struct.unpack_from("<I", blob, offset)[0] == 0x240406FE]
	if len(hits) != 2: raise ValueError("shop overlay does not hold exactly two flag 0x6FE accesses")
	init = hits[0] - 0x58
	if shop_word(blob, init, SHOP_BASE) != 0x27BDFFE0 or shop_word(blob, hits[1] - 0xC, SHOP_BASE) >> 26 != 3: raise ValueError("shop scene init function not found")
	return init
def shop_decode_program(data, start, limit, commands):
	"""Glyph runs of one message program (bytes outside commands, up to 0xFF); commands come from the native trace."""
	spans = sorted((int(command["file_offset"]), int(command["file_offset"]) + int(command["native_length"])) for command in commands); runs = []; cursor = start + 2; raw = bytearray(); raw_start = cursor
	def flush():
		if raw:
			runs.append({"file_offset": raw_start, "relative_offset": raw_start - start, "raw_hex": bytes(raw).hex(), "text": __import__("ui").decode_native_text(bytes(raw), False)}); raw.clear()
	span_index = 0
	while cursor < limit:
		while span_index < len(spans) and spans[span_index][1] <= cursor: span_index += 1
		if span_index < len(spans) and spans[span_index][0] == cursor: flush(); cursor = spans[span_index][1]; raw_start = cursor; continue
		value = data[cursor]
		if value == 0xFF: break
		if not raw: raw_start = cursor
		raw.append(value); cursor += 1
	flush(); return runs
def shop_choice_rows(commands, runs):
	"""Rows of every choice command (same structure as ui.native_program_trace, but built from this module's runs)."""
	for command in commands:
		if command["opcode"] not in ("0x10", "0x39"): continue
		markers = [item for item in commands if item["opcode"] == "0x0F" and item["file_offset"] < command["file_offset"]][-command["choice_count"]:]; rows = []
		for index, marker in enumerate(markers):
			stop = markers[index + 1]["file_offset"] if index + 1 < len(markers) else command["file_offset"]; row_runs = [run for run in runs if marker["file_offset"] < run["file_offset"] < stop]; row_index = marker["arguments"][0]; coordinates = command["cursor_coordinates"][row_index] if row_index < len(command["cursor_coordinates"]) else []
			rows.append({"index": row_index, "marker_file_offset": marker["file_offset"], "text": "".join(run["text"] for run in row_runs).strip(), "text_runs": row_runs, "native_coordinates": coordinates})
		command["choice_rows"] = rows
SHOP_COMMAND_KEYS = ("opcode", "file_offset", "arguments", "native_length", "effect", "dynamic_text", "message_index", "target_index", "choice_rows")
def shop_slim(entry, origin):
	"""Keeps only the fields the runtime message resolver reads."""
	commands = []
	for command in entry["native_commands"]:
		kept = {key: command[key] for key in SHOP_COMMAND_KEYS if key in command}; kept["file_offset"] -= origin
		if "choice_rows" in kept: kept["choice_rows"] = [{"index": row["index"], "text": row["text"], "native_coordinates": row["native_coordinates"], "text_runs": [{"file_offset": run["file_offset"] - origin, "text": run["text"]} for run in row["text_runs"]]} for row in kept["choice_rows"]]
		commands.append(kept)
	return {"index": entry["index"], "text": entry["text"], "display_ready": True, "text_blocks": [{"file_offset": run["file_offset"] - origin, "text": run["text"]} for run in entry["text_blocks"]], "native_commands": commands, "display_resolution": entry["display_resolution"]}
def shop_message_entries(data, payload_offset, size, count, base):
	entries = []
	for message in __import__("ui").native_text_messages(data, payload_offset, size, count):
		commands = message["native_commands"]; runs = shop_decode_program(data, message["file_offset"], payload_offset + size, commands)
		for command in commands:
			if command.get("effect") == "item_name_text" and command.get("inserted_text"): runs.append({"file_offset": command["file_offset"], "relative_offset": command["file_offset"] - message["file_offset"], "raw_hex": "", "text": command["inserted_text"], "dynamic": "item_name_text", "native_length": command["native_length"]})
		runs.sort(key=lambda run: run["file_offset"]); text = "".join(run["text"] for run in runs)
		entry = {"index": message["index"], "index_hex": message["index_hex"], "relative_offset": message["relative_offset"], "file_offset": message["file_offset"], "text": text, "display_ready": True, "text_blocks": runs, "native_commands": commands, "display_resolution": {"status": "native_primary_program", "requires_runtime_resolution": any(command.get("effect") in ("native_state_redirect", "runtime_number_format") for command in commands), "root_message_index": message["index"], "bank_pointer": "message_context+0x28"}}
		shop_choice_rows(commands, runs)
		entries.append(shop_slim(entry, payload_offset))
	return entries
def shop_item_text(sles, offset_base, index, header=0):
	"""Plain item name / description text with the native colour markers (FB 0A n / FB 0B) and glyph escapes the port font draws."""
	table = offset_base; cursor = table + struct.unpack_from("<H", sles, table + index * 2)[0] + header; text = []; raw = bytearray()
	def flush():
		if raw: text.append(__import__("ui").decode_native_text(bytes(raw), False)); raw.clear()
	while cursor < len(sles) and sles[cursor] != 0xFF:
		value = sles[cursor]
		if value == 0xFB:
			opcode = sles[cursor + 1]
			if opcode == 0x1F: break
			flush()
			if opcode == 0x0A: color = sles[cursor + 2] & 0x7F; text.append(chr(0xE0F0 + (color if color < 8 else 0)))
			elif opcode == 0x0B: text.append(chr(0xE0FF))
			cursor += SHOP_LENGTHS.get(opcode, 2); continue
		raw.append(value); cursor += 1
	flush(); return "".join(text).replace("\u27e663\u27e7", ":").replace("\u27e664\u27e7", "\ue064").replace("\u27e665\u27e7", "\ue065").strip()
def shop_catalog(sles):
	names = {}; descriptions = {}; prices = {}
	name_table = 0x800 + 0x8006CFB8 - SHOP_SLES_BASE; description_table = 0x800 + SHOP_DESCRIPTION_BANK - SHOP_SLES_BASE; name_count = struct.unpack_from("<H", sles, name_table)[0] // 2; description_count = struct.unpack_from("<H", sles, description_table)[0] // 2
	for code in range(SHOP_ITEM_FIRST, SHOP_ITEM_LAST + 1):
		index = code - SHOP_ITEM_FIRST
		if index < name_count: names[str(code)] = shop_item_text(sles, name_table, index)
		if index < description_count: descriptions[str(code)] = shop_item_text(sles, description_table, index, 2)
		price = struct.unpack_from("<h", sles, 0x800 + SHOP_PRICE_TABLE + 2 * code - SHOP_SLES_BASE)[0]; prices[str(code)] = price
	specials = {key: [struct.unpack_from("<h", sles, 0x800 + address - SHOP_SLES_BASE + 2 * index)[0] for index in range(count)] for key, (address, count) in SHOP_SPECIAL_PRICES.items()}
	return {"schema": 1, "names": names, "descriptions": descriptions, "base_prices": prices, "price_rule": "SLES0x80051534: negative base = 500 * |value|; buying scales by byte 0x8009C82C (0: 4/5, 1: 1, 2: 6/5); selling pays (price + 3) >> 2", "special_prices": specials, "price_table": f"0x{0x80070FC8 - 0x700:08X} + 2 * code", "name_table": "SLES0x8006CFB8", "description_bank": "SLES0x8006DDAC"}
def shop_pointer_lists(blob, base_address, count, limit_low, limit_high):
	lists = []
	for index in range(count):
		pointer = shop_word(blob, base_address + 4 * index, SHOP_BASE)
		if pointer == 0: lists.append([]); continue
		if not limit_low <= pointer < limit_high: raise ValueError(f"stock list pointer {pointer:#x} outside the data section")
		cursor = pointer; ids = []
		while True:
			value = struct.unpack_from("<B", blob, 0x30 + cursor - SHOP_BASE)[0]
			if value == 0xFF: break
			ids.append(value); cursor += 1
		lists.append(ids)
	return lists
def shop_export_stage(source, stage):
	blob = (source / "DAT" / f"{stage}T.BIN").read_bytes(); init = shop_locate_init(blob); bank = shop_address_of(blob, init, "bank"); rows_address = shop_address_of(blob, init, "set_rows"); stock_a = shop_address_of(blob, init, "stock_a"); stock_b = shop_address_of(blob, init, "stock_b"); scene_table = shop_address_of(blob, init, "scene_table"); categories = shop_address_of(blob, init, "categories")
	payload_offset = 0x30 + bank - SHOP_BASE; first = struct.unpack_from("<H", blob, payload_offset)[0]; count = first // 2; size = rows_address - bank
	if not size - 8 <= struct.unpack_from("<H", blob, payload_offset + 2 * (count - 1))[0] <= size: raise ValueError(f"{stage}: the message bank does not end at the set table")
	entries = shop_message_entries(blob, payload_offset, size, count - 1, bank); rows = [list(blob[0x30 + rows_address - SHOP_BASE + 16 * row:0x30 + rows_address - SHOP_BASE + 16 * row + 16]) for row in range(2)]
	list_count = (scene_table - stock_b) // 4
	if stock_b - stock_a < 4 * list_count or not 0 < list_count < 64: raise ValueError(f"{stage}: unexpected stock array layout")
	low = stock_a - 0x200; lists_a = shop_pointer_lists(blob, stock_a, list_count, low, stock_b); lists_b = shop_pointer_lists(blob, stock_b, list_count, low, stock_b)
	ranges = [list(struct.unpack_from("<2H", blob, 0x30 + categories - SHOP_BASE + 4 * index)) for index in range(2)]
	unsellable = []; cursor = shop_address_of(blob, init, "unsellable", load=True)
	while True:
		value = struct.unpack_from("<h", blob, 0x30 + cursor - SHOP_BASE)[0]
		if value == -1: break
		unsellable.append(value); cursor += 2
	source_info = {"file": f"DAT/{stage}T.BIN", "overlay_base": f"0x{SHOP_BASE:08X}", "scene_init": f"0x{init:08X}", "runtime_message_base": f"0x{bank:08X}", "set_rows": f"0x{rows_address:08X}", "stock_a": f"0x{stock_a:08X}", "stock_b": f"0x{stock_b:08X}", "category_ranges": f"0x{categories:08X}", "message_count": len(entries)}
	return {"source": source_info, "messages": entries, "shop": {"stage": stage, "set_rows": rows, "stock_a": lists_a, "stock_b": lists_b, "category_ranges": ranges, "unsellable": unsellable}}
def export_shops(source_dir=None, output_dir=None):
	"""The shop module and its data are identical in every shop stage overlay, so one shared bank is exported and checked against each stage."""
	source = Path(source_dir) if source_dir else SHOP_ROOT / "build/disc-assets"; output = Path(output_dir) if output_dir else SHOP_OUTPUT; output.mkdir(parents=True, exist_ok=True); reference = None; banks = {}
	for stage in SHOP_STAGES:
		data = shop_export_stage(source, stage); comparable = json.dumps({"messages": data["messages"], "shop": {key: value for key, value in data["shop"].items() if key != "stage"}}, sort_keys=True)
		if reference is None: reference = (stage, comparable, data)
		elif comparable != reference[1]: raise ValueError(f"{stage} shop data differs from {reference[0]}")
		banks[stage] = {"file": "shop.json", "runtime_message_base": data["source"]["runtime_message_base"], "messages": data["source"]["message_count"]}
	data = dict(reference[2]); data["shop"] = {key: value for key, value in data["shop"].items() if key != "stage"}; data["source"] = {"runtime_message_base": data["source"]["runtime_message_base"], "origin": f"DAT/{reference[0]}T.BIN", "stages": SHOP_STAGES, **{key: data["source"][key] for key in ("scene_init", "set_rows", "stock_a", "stock_b", "category_ranges", "message_count")}}
	write_output(output / "shop.json", json.dumps({"source": data["source"], "message_calls": [], "messages": data["messages"], "shop": data["shop"]}, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
	write_output(output / "items.json", json.dumps(shop_catalog((source / "SLES_035.56").read_bytes()), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
	write_output(output / "manifest.json", json.dumps({"schema": 2, "banks": banks, "items": "items.json"}, indent=1) + "\n", encoding="utf-8"); return {"stages": list(banks)}
DEVELOPMENT_OUTPUT = SHOP_ROOT / "assets/development"
"""Roll's development scene (scene 0x30 of ST04T, started by dialogue flag 0x6FD): the overlay message bank, the item recipe table and the special weapon improvement tables."""
DEVELOPMENT_STAGE = "ST04"
DEVELOPMENT_BANK = 0x800F25C4
DEVELOPMENT_COST_POINTERS = 0x800F4040
DEVELOPMENT_RECIPES = 0x800F4088
DEVELOPMENT_MAX_LEVELS = 0x800DC8E8
DEVELOPMENT_GAME_BASE = 0x800AD000
DEVELOPMENT_WEAPONS = range(3, 0x12)
def development_u16(blob, address, count): return list(struct.unpack_from(f"<{count}H", blob, 0x30 + address - SHOP_BASE))
def export_development(source_dir=None, output_dir=None):
	"""The recipe records are 12 bytes (result, first item, second item or 0xFFFF, kind, first hint, second hint) up to the 0xFFFF result; costs are three levels of five u32 per weapon (attack, energy, range, rapid, special) and the caps are 5 bytes per weapon at GAME 0x800DC8E8."""
	source = Path(source_dir) if source_dir else SHOP_ROOT / "build/disc-assets"; output = Path(output_dir) if output_dir else DEVELOPMENT_OUTPUT; output.mkdir(parents=True, exist_ok=True); blob = (source / "DAT" / f"{DEVELOPMENT_STAGE}T.BIN").read_bytes(); game = (source / "COMMON/GAME.BIN").read_bytes()
	payload_offset = 0x30 + DEVELOPMENT_BANK - SHOP_BASE; table = development_u16(blob, DEVELOPMENT_BANK, 75)
	if table[0] != 150 or any(a > b for a, b in zip(table, table[1:])): raise ValueError("ST04T development message bank index table not found")
	entries = shop_message_entries(blob, payload_offset, table[74], 74, DEVELOPMENT_BANK); recipes = []; address = DEVELOPMENT_RECIPES
	while True:
		result, first, second, kind, first_hint, second_hint = development_u16(blob, address, 6)
		if result == 0xFFFF: break
		recipes.append({"result": result, "first": first, "second": -1 if second == 0xFFFF else second, "kind": kind, "first_hint": first_hint, "second_hint": second_hint}); address += 12
	if not 20 < len(recipes) < 40: raise ValueError("ST04T development recipe table not found")
	weapons = {}
	for weapon in DEVELOPMENT_WEAPONS:
		pointer = shop_word(blob, DEVELOPMENT_COST_POINTERS + 4 * weapon, SHOP_BASE); caps = list(game[0x30 + DEVELOPMENT_MAX_LEVELS - DEVELOPMENT_GAME_BASE + 8 * weapon:][:5])
		if not DEVELOPMENT_BANK < pointer < DEVELOPMENT_COST_POINTERS: raise ValueError(f"weapon {weapon:#x} cost table pointer {pointer:#x} outside the data section")
		weapons[str(weapon)] = {"caps": caps, "costs": [list(struct.unpack_from("<5I", blob, 0x30 + pointer - SHOP_BASE + 20 * level)) for level in range(3)]}
	data = {"recipes": recipes, "weapons": weapons, "item_range": [0x408, 0x437], "weapon_range": [0x383, 0x393], "cancel": 0x485, "maximum_cost": 0x98967F, "cost_percent_by_byte45": [-10, 0, 10]}
	source_info = {"origin": f"DAT/{DEVELOPMENT_STAGE}T.BIN", "overlay_base": f"0x{SHOP_BASE:08X}", "runtime_message_base": f"0x{DEVELOPMENT_BANK:08X}", "message_count": len(entries), "scene": "GAME table 0x800DC490[0x30] -> hook 0x80078DC0 = 0x800EE228 (states 0x800EE264/0x800EE454/0x800EE4B0); started by flag 0x6FD (ST04T 0x800E79B4, message 0x4E)", "menu_states": "table 0x800F41CC (0x800EAACC main, 0x800EBAB0 development, 0x800EADD4 change weapon, 0x800EB1FC improve)", "recipes": f"0x{DEVELOPMENT_RECIPES:08X}", "weapon_costs": f"0x{DEVELOPMENT_COST_POINTERS:08X}", "weapon_caps": f"GAME0x{DEVELOPMENT_MAX_LEVELS:08X}", "cost_rule": "ST04T 0x800EDBA4: cost[weapon][level][stat]; byte 0x8009C82D 0: cost - cost / 10, 1: unchanged, 2: cost + cost / 10; at most 9,999,999"}
	write_output(output / "development.json", json.dumps({"source": source_info, "message_calls": [], "messages": entries, "development": data}, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
	write_output(output / "manifest.json", json.dumps({"schema": 2, "banks": {DEVELOPMENT_STAGE: {"file": "development.json", "runtime_message_base": f"0x{DEVELOPMENT_BANK:08X}", "messages": len(entries)}}}, indent=1) + "\n", encoding="utf-8"); return {"messages": len(entries), "recipes": len(recipes), "weapons": len(weapons)}

from disc import decompress_section, write_output
from disc import read_u16
from disc import read_u32
from ui import decode_page
from models import actor_archive
from models import export_actor_model
from models import export_static_actor
from cinematics import record_source

# ---- area_roofs ----
def camera_table(data):
	call = data.find(struct.pack("<I", 0x0C000000 | ((0x80016270 >> 2) & 0x03FFFFFF)), 48)
	if call < 40: raise ValueError("Native area camera initializer not found")
	upper = None
	for offset in range(call - 40, call, 4):
		word = struct.unpack_from("<I", data, offset)[0]
		if word >> 16 == 0x3C04: upper = (word & 65535) << 16
		if word >> 16 == 0x2484 and upper is not None: return upper + struct.unpack("<h", struct.pack("<H", word & 65535))[0]
	raise ValueError("Native area camera table address unresolved")
def geometry(path, native_map_face_flags=False):
	data = path.read_bytes(); size = struct.unpack_from("<I", data, 12)[0]; document = json.loads(data[20:20 + size]); binary = data[28 + size:]
	def accessor(index):
		record = document["accessors"][index]; view = document["bufferViews"][record["bufferView"]]; width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[record["type"]]; fmt = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[record["componentType"]]; stride = view.get("byteStride", struct.calcsize(fmt) * width); offset = view.get("byteOffset", 0) + record.get("byteOffset", 0)
		return [struct.unpack_from("<" + fmt * width, binary, offset + item * stride) for item in range(record["count"])]
	parents = {child: index for index, node in enumerate(document["nodes"]) for child in node.get("children", [])}
	def point(index, value):
		node = document["nodes"][index]
		if "matrix" in node:
			matrix = node["matrix"]; value = [sum(matrix[column * 4 + row] * value[column] for column in range(3)) + matrix[12 + row] for row in range(3)]
		else:
			value = [value[axis] * node.get("scale", [1, 1, 1])[axis] for axis in range(3)]; x, y, z, w = node.get("rotation", [0, 0, 0, 1]); tx = 2 * (y * value[2] - z * value[1]); ty = 2 * (z * value[0] - x * value[2]); tz = 2 * (x * value[1] - y * value[0]); value = [value[0] + w * tx + y * tz - z * ty, value[1] + w * ty + z * tx - x * tz, value[2] + w * tz + x * ty - y * tx]; value = [value[axis] + node.get("translation", [0, 0, 0])[axis] for axis in range(3)]
		return point(parents[index], value) if index in parents else value
	triangles = []
	for index, node in enumerate(document["nodes"]):
		if "mesh" not in node: continue
		for surface, primitive in enumerate(document["meshes"][node["mesh"]]["primitives"]):
			if primitive.get("mode", 4) != 4: continue
			attributes = primitive["attributes"]; positions = [point(index, value) for value in accessor(attributes["POSITION"])]; uv = accessor(attributes["TEXCOORD_0"]) if "TEXCOORD_0" in attributes else [(0, 0)] * len(positions); colors = accessor(attributes["COLOR_0"]) if "COLOR_0" in attributes else [(0.5, 0.5, 0.5, 1)] * len(positions); indices = [value[0] for value in accessor(primitive["indices"])] if "indices" in primitive else list(range(len(positions)))
			if native_map_face_flags and "TEXCOORD_1" in attributes: colors = [(*value[:3], 1.0) for value in colors]
			for start in range(0, len(indices), 3):
				ids = indices[start:start + 3]
				if len(ids) != 3: continue
				vertices = [positions[item] for item in ids]; u = [vertices[1][axis] - vertices[0][axis] for axis in range(3)]; v = [vertices[2][axis] - vertices[0][axis] for axis in range(3)]; normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; length = math.sqrt(sum(value * value for value in normal))
				if length < 1e-10: continue
				triangles.append({"vertices": vertices, "uv": [uv[item] for item in ids], "colors": [colors[item] for item in ids], "normal_y": normal[1] / length, "area": length / 2, "node": node["name"], "surface": surface})
	return triangles
def signed_edge(a, b, p): return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
def split(polygon, a, b, sign):
	inside = []; outside = []
	for index, p in enumerate(polygon):
		q = polygon[(index + 1) % len(polygon)]; dp = signed_edge(a, b, p) * sign; dq = signed_edge(a, b, q) * sign
		if dp >= -1e-8: inside.append(p)
		if dp <= 1e-8: outside.append(p)
		if (dp > 1e-8 and dq < -1e-8) or (dp < -1e-8 and dq > 1e-8):
			factor = dp / (dp - dq); cut = [p[axis] + (q[axis] - p[axis]) * factor for axis in range(2)]; inside.append(cut); outside.append(cut)
	return inside, outside
def subtract(polygon, triangle):
	if any(max(p[axis] for p in polygon) < min(p[axis] for p in triangle) or min(p[axis] for p in polygon) > max(p[axis] for p in triangle) for axis in range(2)): return [polygon]
	sign = 1 if signed_edge(triangle[0], triangle[1], triangle[2]) > 0 else -1; remaining = polygon; pieces = []
	for index in range(3):
		remaining, outside = split(remaining, triangle[index], triangle[(index + 1) % 3], sign)
		if len(outside) >= 3: pieces.append(outside)
		if len(remaining) < 3: break
	return pieces
def roof_geometry(triangles):
	floors = [triangle for triangle in triangles if triangle["normal_y"] > 0.999]
	if not floors: return {"reason": "no_horizontal_floor", "vertices": []}
	floor_y = min(min(vertex[1] for vertex in triangle["vertices"]) for triangle in floors); walls = [triangle for triangle in triangles if abs(triangle["normal_y"]) < 0.25]; roof_y = max(vertex[1] for triangle in (walls or triangles) for vertex in triangle["vertices"]); floors = sorted((triangle for triangle in floors if max(vertex[1] for vertex in triangle["vertices"]) <= roof_y + 0.01), key=lambda triangle: triangle["vertices"][0][1])
	floor_area = sum(triangle["area"] for triangle in floors if abs(triangle["vertices"][0][1] - floor_y) < 0.01); ceiling_planes = Counter()
	for triangle in triangles:
		if triangle["normal_y"] < -0.999 and min(vertex[1] for vertex in triangle["vertices"]) > floor_y + 0.75: ceiling_planes[round(triangle["vertices"][0][1], 6)] += triangle["area"]
	if ceiling_planes and floor_area > 0:
		ceiling_y, ceiling_area = ceiling_planes.most_common(1)[0]
		if ceiling_area / floor_area >= 0.8: return {"reason": "existing_ceiling", "height": ceiling_y, "native_ceiling_coverage": ceiling_area / floor_area, "vertices": []}
	if roof_y - floor_y < 0.75: return {"reason": "insufficient_room_height", "vertices": []}
	ceilings = [triangle for triangle in triangles if triangle["normal_y"] < -0.999 and min(vertex[1] for vertex in triangle["vertices"]) >= roof_y - 0.01]; samples = ceilings or walls
	if not samples: return {"reason": "no_material_sample", "vertices": []}
	material_area = Counter()
	for triangle in samples: material_area[(triangle["node"], triangle["surface"])] += triangle["area"]
	material = material_area.most_common(1)[0][0]; sample = max((triangle for triangle in samples if (triangle["node"], triangle["surface"]) == material), key=lambda triangle: triangle["area"]); uv_min = [min(value[axis] for value in sample["uv"]) for axis in range(2)]; uv_max = [max(value[axis] for value in sample["uv"]) for axis in range(2)]; color = [sum(value[axis] for value in sample["colors"]) / 3 for axis in range(3)] + [1]; cuts = [[[vertex[0], vertex[2]] for vertex in triangle["vertices"]] for triangle in ceilings]; vertices = []; uvs = []
	for floor in floors:
		pieces = [[[vertex[0], vertex[2]] for vertex in floor["vertices"]]]
		for cut in cuts:
			pieces = [part for polygon in pieces for part in subtract(polygon, cut)]
			if not pieces: break
		for polygon in pieces:
			low = [min(point[axis] for point in polygon) for axis in range(2)]; high = [max(point[axis] for point in polygon) for axis in range(2)]
			for index in range(1, len(polygon) - 1):
				triangle = [polygon[0], polygon[index], polygon[index + 1]]
				if abs(signed_edge(*triangle)) < 1e-7: continue
				cuts.append(triangle)
				for point in triangle:
					vertices.append([round(point[0], 6), round(roof_y, 6), round(point[1], 6)]); uvs.append([uv_min[axis] + (point[axis] - low[axis]) / max(high[axis] - low[axis], 1e-8) * (uv_max[axis] - uv_min[axis]) for axis in range(2)])
	return {"reason": "missing_ceiling" if vertices else "existing_ceiling", "height": roof_y, "material_node": material[0], "material_surface": material[1], "material_source": "existing_ceiling" if ceilings else "existing_wall", "sample_uv_min": uv_min, "sample_uv_max": uv_max, "color": color, "vertices": vertices, "uv": uvs}
def ceiling_holes(triangles, height):
	edges = Counter()
	for triangle in triangles:
		if triangle["normal_y"] > -0.999 or abs(triangle["vertices"][0][1] - height) >= 0.01: continue
		points = [tuple(round(value, 6) for value in (vertex[0], vertex[2])) for vertex in triangle["vertices"]]
		for index in range(3): edges[tuple(sorted((points[index], points[(index + 1) % 3])))] += 1
	graph = {}
	for (a, b), count in edges.items():
		if count % 2: graph.setdefault(a, []).append(b); graph.setdefault(b, []).append(a)
	if any(len(neighbors) != 2 for neighbors in graph.values()): raise ValueError("Ceiling opening boundary is not a closed loop")
	loops = []; seen = set()
	for start in graph:
		if start in seen: continue
		loop = []; previous = None; point = start
		while point not in seen:
			seen.add(point); loop.append(point); neighbors = graph[point]; next_point = neighbors[0] if neighbors[0] != previous else neighbors[1]; previous, point = point, next_point
		loops.append(loop)
	if len(loops) < 2: return []
	area = lambda loop: abs(sum(point[0] * loop[(index + 1) % len(loop)][1] - loop[(index + 1) % len(loop)][0] * point[1] for index, point in enumerate(loop)))
	outer = max(loops, key=area); holes = []
	for loop in loops:
		if loop == outer: continue
		x, z = loop[0]; inside = False
		for index, a in enumerate(outer):
			b = outer[(index + 1) % len(outer)]
			if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]: inside = not inside
		if inside: holes.append([[point[0], height + 0.002, point[1]] for point in loop])
	return holes
def close_raised_roof(triangles, roof):
	if not roof.get("vertices"): return
	floor_y = min(vertex[1] for triangle in triangles for vertex in triangle["vertices"]); height = float(roof["height"]); wall_tops = Counter(); walls = []
	for triangle in triangles:
		if abs(triangle["normal_y"]) > 0.01: continue
		top = max(vertex[1] for vertex in triangle["vertices"])
		if top < (floor_y + height) * 0.5: continue
		wall_tops[round(top, 6)] += triangle["area"]; walls.append(triangle)
	if not wall_tops: return
	wall_y = wall_tops.most_common(1)[0][0]
	if height - wall_y < 0.01: return
	edges = {}; graph = {}
	for triangle in walls:
		if abs(max(vertex[1] for vertex in triangle["vertices"]) - wall_y) > 1e-6: continue
		indices = [index for index, vertex in enumerate(triangle["vertices"]) if abs(vertex[1] - wall_y) < 1e-6]
		if len(indices) != 2: continue
		a, b = [tuple(round(vertex[axis], 6) for axis in (0, 2)) for vertex in (triangle["vertices"][index] for index in indices)]; key = tuple(sorted((a, b)))
		if a == b or key in edges: continue
		edges[key] = (triangle, indices); graph.setdefault(a, []).append(b); graph.setdefault(b, []).append(a)
	loops = []; seen = set()
	for start in graph:
		if start in seen: continue
		component = []; pending = [start]
		while pending:
			point = pending.pop()
			if point in seen: continue
			seen.add(point); component.append(point); pending.extend(graph[point])
		if any(len(graph[point]) != 2 for point in component): continue
		loop = []; previous = None; point = start
		while point not in loop:
			loop.append(point); neighbors = graph[point]; next_point = neighbors[0] if neighbors[0] != previous else neighbors[1]; previous, point = point, next_point
		if point == start: loops.append(loop)
	if not loops: return
	signed_area = lambda loop: sum(point[0] * loop[(index + 1) % len(loop)][1] - loop[(index + 1) % len(loop)][0] * point[1] for index, point in enumerate(loop))
	outline = max(loops, key=lambda loop: abs(signed_area(loop))); polygon = list(outline)
	while len(polygon) > 3:
		flat = next((index for index in range(len(polygon)) if abs(signed_edge(polygon[index - 1], polygon[index], polygon[(index + 1) % len(polygon)])) < 1e-8), None)
		if flat is None: break
		polygon.pop(flat)
	sign = 1 if signed_area(polygon) > 0 else -1; remaining = list(polygon); faces = []
	while len(remaining) > 3:
		ear = None
		for index in range(len(remaining)):
			a, b, c = remaining[index - 1], remaining[index], remaining[(index + 1) % len(remaining)]
			if signed_edge(a, b, c) * sign <= 1e-8: continue
			if any(all(signed_edge(p, q, point) * sign >= -1e-8 for p, q in ((a, b), (b, c), (c, a))) for point in remaining if point not in (a, b, c)): continue
			ear = index; faces.append([a, b, c]); break
		if ear is None: return
		remaining.pop(ear)
	faces.append(remaining)
	for start in range(0, len(roof["vertices"]), 3):
		uncovered = [[[point[0], point[2]] for point in roof["vertices"][start:start + 3]]]
		for face in faces:
			uncovered = [piece for part in uncovered for piece in subtract(part, face)]
			if not uncovered: break
		uncovered_area = sum(abs(sum(point[0] * part[(index + 1) % len(part)][1] - part[(index + 1) % len(part)][0] * point[1] for index, point in enumerate(part))) / 2 for part in uncovered)
		if uncovered_area > 1e-7:
			roof["rejected_wall_contour"] = "Closed wall component does not cover the existing floor-derived roof"
			perimeter_roof_height(triangles, roof)
			return
	height += 0.01; low = [min(point[axis] for point in polygon) for axis in range(2)]; high = [max(point[axis] for point in polygon) for axis in range(2)]; uv_low = roof["sample_uv_min"]; uv_high = roof["sample_uv_max"]; roof["vertices"] = [[point[0], height, point[1]] for face in faces for point in face]; roof["uv"] = [[uv_low[axis] + (point[axis] - low[axis]) / max(high[axis] - low[axis], 1e-8) * (uv_high[axis] - uv_low[axis]) for axis in range(2)] for face in faces for point in face]; roof["height"] = height; groups = {}; wall_bias = 0.002
	for index, a in enumerate(outline):
		b = outline[(index + 1) % len(outline)]; triangle, indices = edges[tuple(sorted((a, b)))]; ia, ib = indices; va, vb = triangle["vertices"][ia], triangle["vertices"][ib]; ic = next(item for item in range(3) if item not in indices); lower = triangle["vertices"][ic]; match = ia if math.hypot(lower[0] - va[0], lower[2] - va[2]) < math.hypot(lower[0] - vb[0], lower[2] - vb[2]) else ib; fraction = min(1.0, (height - wall_y) / max(wall_y - lower[1], 1e-8)); delta = [(triangle["uv"][ic][axis] - triangle["uv"][match][axis]) * fraction for axis in range(2)]; ua, ub = triangle["uv"][ia], triangle["uv"][ib]; da, db = [[uv[axis] + delta[axis] for axis in range(2)] for uv in (ua, ub)]; ta, tb = [va[0], height, va[2]], [vb[0], height, vb[2]]; key = (triangle["node"], triangle["surface"])
		if key not in groups: groups[key] = {"material_node": key[0], "material_surface": key[1], "vertices": [], "uv": [], "colors": []}
		length = math.hypot(b[0] - a[0], b[1] - a[1]); offset = [-(b[1] - a[1]) * sign * wall_bias / length, 0, (b[0] - a[0]) * sign * wall_bias / length]; va = [va[axis] + offset[axis] for axis in range(3)]; vb = [vb[axis] + offset[axis] for axis in range(3)]; ta = [ta[axis] + offset[axis] for axis in range(3)]; tb = [tb[axis] + offset[axis] for axis in range(3)]; va[1] -= wall_bias; vb[1] -= wall_bias
		group = groups[key]; group["vertices"].extend([va, vb, tb, va, tb, ta]); group["uv"].extend([da, db, ub, da, ub, ua]); group["colors"].extend([triangle["colors"][item] for item in (ia, ib, ib, ia, ib, ia)])
	roof["wall_infills"] = list(groups.values()); roof["wall_top_height"] = wall_y; roof["wall_inward_bias"] = wall_bias
def perimeter_roof_height(triangles, roof):
	floor = [[[point[0], point[2]] for point in roof["vertices"][start:start + 3]] for start in range(0, len(roof["vertices"]), 3)]; tops = []
	def inside(point): return any(all(signed_edge(a, b, point) >= -1e-8 for a, b in zip(face, face[1:] + face[:1])) or all(signed_edge(a, b, point) <= 1e-8 for a, b in zip(face, face[1:] + face[:1])) for face in floor)
	for triangle in triangles:
		if abs(triangle["normal_y"]) > 0.01: continue
		top = max(point[1] for point in triangle["vertices"]); points = [point for point in triangle["vertices"] if abs(point[1] - top) < 1e-6]
		if len(points) != 2: continue
		a, b = points; dx, dz = b[0] - a[0], b[2] - a[2]; length = math.hypot(dx, dz)
		if length < 1e-8: continue
		middle = [(a[0] + b[0]) / 2, (a[2] + b[2]) / 2]; left = inside([middle[0] - dz * 0.002 / length, middle[1] + dx * 0.002 / length]); right = inside([middle[0] + dz * 0.002 / length, middle[1] - dx * 0.002 / length])
		if left != right: tops.append(top)
	if not tops: return
	height = max(tops)
	if height >= float(roof["height"]): return
	roof["height"] = height; roof["wall_top_height"] = height
	for point in roof["vertices"]: point[1] = height
def export_area_roofs(dat_dir=None, output_dir=None, stages=None):
	dat_dir = Path(dat_dir or ROOT / "build/disc-assets/DAT"); output_dir = Path(output_dir or ROOT / "assets/levels"); summary = Counter()
	for path in sorted(dat_dir.glob("ST??T.BIN")):
		stage = path.stem[:-1]; lighting_path = output_dir / stage / "lighting.json"
		if stages is not None and stage not in stages: continue
		if not lighting_path.is_file(): continue
		data = path.read_bytes(); base = struct.unpack_from("<I", data, 12)[0]; table = camera_table(data); lighting = json.loads(lighting_path.read_text()); records = []; map_manifest_path = output_dir / stage / "manifest.json"; map_manifest = json.loads(map_manifest_path.read_text()) if map_manifest_path.is_file() else {}; area_flags = {int(area["index"]): bool(area.get("native_map_face_flags_in_alpha", False)) for area in map_manifest.get("areas", [])}
		for area in lighting["native_color_pipeline"]["depth_cue"]["area_parameters"]:
			index = int(area["area"]); offset = 48 + table - base + index * 12
			if offset < 48 or offset + 12 > 48 + struct.unpack_from("<I", data, 4)[0]: raise ValueError(stage + " camera record outside native section")
			values = struct.unpack_from("<BB5h", data, offset); record = {"area": index, "native_camera_record": list(values), "fixed_pitch": values[1] == 2, "source_offset": hex(offset), "roof": {"reason": "camera_allows_pitch", "vertices": []}}; mesh_path = output_dir / stage / ("area_%02d.glb" % index)
			if record["fixed_pitch"] and mesh_path.is_file():
				triangles = geometry(mesh_path, area_flags.get(index, False)); record["roof"] = roof_geometry(triangles); close_raised_roof(triangles, record["roof"])
			if stage in ("ST04", "ST06", "ST07") and index == 0 and mesh_path.is_file():
				triangles = geometry(mesh_path, area_flags.get(index, False)); ceiling = roof_geometry(triangles)
				if ceiling["reason"] == "existing_ceiling": record["roof"]["blackouts"] = ceiling_holes(triangles, ceiling["height"])
			summary[record["roof"]["reason"]] += 1; records.append(record)
		manifest = {"stage": stage, "source": {"archive": "DAT/" + path.name, "camera_table": hex(table), "record_stride": 12, "loader": "SLES80016270", "fixed_pitch_branch": "SLES800163EC..80016404; mode2 ignores look offset", "classification": "Fixed pitch is a roof candidate hint, not an indoor flag; generated geometry is a Godot adaptation"}, "areas": records}; write_output(output_dir / stage / "area_roofs.json", json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
	return dict(summary)

# ---- location_text ----
SLES = ROOT / "build/disc-assets/SLES_035.56"
RECORD_TABLE = 0x611A0
STRING_BASE = 0x60B05
HEADER = bytes([0xFB, 0x1F, 0xFF])
def decode(raw):
	out = []
	for value in raw:
		if value == 0x4C: out.append(" ")
		elif value in (0x0C, 0x5D): out.append("'")
		elif value == 0x61: out.append("-")
		elif value <= 9: out.append(str(value))
		elif 20 <= value <= 45: out.append(chr(65 + value - 20))
		elif 46 <= value <= 71: out.append(chr(97 + value - 46))
		else: out.append("?")
	return "".join(out)
def read_strings(data):
	entries = []; position = STRING_BASE
	while position < 0x6119A:
		end = data.find(HEADER, position + 3)
		entries.append(decode(data[position + 3:end]) if end >= 0 else ""); position = end if end >= 0 else 0x6119A
	return entries
def export_location_names(hints_path=None, output=None):
	data = SLES.read_bytes(); strings = read_strings(data)
	hints = json.loads(Path(hints_path).read_text(encoding="utf-8"))["areas"] if hints_path else {}
	records = []; cursor = RECORD_TABLE
	while data[cursor] <= 0x5C and (not records or data[cursor] >= records[-1][0]): records.append(tuple(data[cursor:cursor + 4])); cursor += 4
	groups = defaultdict(list)
	for stage, area, sub, main in records:
		label = strings[33 + sub].strip() if sub else ""
		if label and "?" not in label: groups[(stage, label)].append(area)
	areas = {}
	for stage, area, sub, main in records:
		label = strings[33 + sub].strip() if sub else ""
		key = "ST%02X" % stage
		if not label or "?" in label:
			hint = hints.get(key, {}).get(str(area))
			if hint: areas.setdefault(key, {})[str(area)] = hint
			continue
		members = groups[(stage, label)]
		if len(members) > 1:
			hint = hints.get(key, {}).get(str(area), ""); skip = set(label.split()) | {"Floor"} | set(strings[(main & 0x7F) + 1].split()) | {"City", "Ruins", "Island"}
			words = [w for w in hint.replace("(", " ").replace(")", " ").split() if w not in skip and not (len(w) == 2 and w[0] == "B" and w[1].isdigit())]
			number = members.index(area) + 1; label = label + " - " + " ".join(words) if words else (label if number == 1 and not label.startswith("Floor") else label + " - Zone %d" % number)
		areas.setdefault(key, {})[str(area)] = label
	result = {"source": "SLES_035.56 location strings 0x60B05 and (stage, area, sub-name, main-name) records at 0x611A0. Repeated labels are numbered.", "areas": areas}
	path = Path(output or ROOT / "tools/location_names.json"); write_output(path, json.dumps(result, indent=1) + "\n", encoding="utf-8")
	return result

# ---- flutter_travel ----
def st10_arrival_craft():
	"""ST10T area 0 script table 0x800F7A28[byte14]: byte14 1 runs 0x800E7740 (no Flutter hull; registers the 0x2C arrival craft at 0x800F7A7C), byte14 >= 2 runs 0x800E78C4 (registers the 0x30 Flutter hull at 0x800F7BD0); neither requests a scene."""
	overlay = (ROOT / "build/disc-assets/DAT/ST10T.BIN").read_bytes(); base = struct.unpack_from("<I", overlay, 12)[0]; word = lambda address: struct.unpack_from("<I", overlay, 48 + address - base)[0]; jal = lambda target: 0x0C000000 | (target >> 2 & 0x3FFFFFF)
	area0 = [word(word(0x800F7A28 + story * 4)) for story in range(19)]; craft_stories = [story for story, callback in enumerate(area0) if callback == 0x800E7740]; hull_stories = [story for story, callback in enumerate(area0) if callback == 0x800E78C4]
	if craft_stories != [1] or hull_stories != list(range(2, 19)) or area0[0] != 0x800C0B04: raise ValueError("ST10 area 0 script table differs")
	if (word(0x800E7764) & 0xFFFF, word(0x800E776C), word(0x800E7770)) != (0x7A7C, jal(0x800C0818), 0x24050001): raise ValueError("ST10 craft registration differs")
	if (word(0x800E78E4) & 0xFFFF, word(0x800E78E8), word(0x800E78EC)) != (0x7BD0, jal(0x800C0818), 0x24050002): raise ValueError("ST10 hull registration differs")
	raw = overlay[48 + 0x800F7A7C - base:68 + 0x800F7A7C - base]; resource = raw[2] | (raw[4] << 8) | (raw[6] << 16)
	if len(raw) != 20 or resource != 0x2C20: raise ValueError("ST10 arrival craft record differs")
	matches = [ROOT / model["file"] for path in (ROOT / "assets/levels/ST10/models").glob("ST10_*/manifest.json") for model in json.loads(path.read_text())["models"] if model.get("flags") == resource]
	if len(matches) != 1: raise ValueError("ST10 arrival craft model is not uniquely exported")
	model_file = ROOT / "assets/levels/ST10/arrival_craft.glb"; write_output(model_file, matches[0].read_bytes()); pose = list(struct.unpack_from("<4h", raw, 12))
	return {"minimum_save_byte14": hull_stories[0], "arrival_craft": {"record": "0x800f7a7c", "save_byte14": craft_stories, "position_raw": pose[:3], "yaw_raw": pose[3], "model_file": "res://" + model_file.relative_to(ROOT).as_posix()}}
def st01_destination_redirects():
	"""ST01T destination callback table 0x800E94FC[slot] (slot 1 = Forbidden Island, 0x800E8788): while flag 0x5C0 is clear it sets the flag and rewrites the request to stage 0x49 area 2 at (0, -1, 0) facing 0 (0x800E87B0..0x800E87E8)."""
	overlay = (ROOT / "build/disc-assets/DAT/ST01T.BIN").read_bytes(); base = struct.unpack_from("<I", overlay, 12)[0]; word = lambda address: struct.unpack_from("<I", overlay, 48 + address - base)[0]
	if word(0x800E94FC + 4) != 0x800E8788 or [word(address) & 0xFFFF for address in (0x800E87B4, 0x800E87C4, 0x800E87C8, 0x800E87D0)] != [0x5C0, 0x5C0, 0x49, 2] or [word(address) for address in (0x800E87D8, 0x800E87DC, 0x800E87E0, 0x800E87E4, 0x800E87E8)] != [0x2402FFFF, 0xA6000004, 0xA6020006, 0xA6000008, 0xA600000A]: raise ValueError("ST01 Forbidden Island destination callback differs")
	return {"ST10": {"event_flag": 0x5C0, "stage": "ST49", "area": 2, "position_raw": [0, -1, 0], "facing_raw": 0}}
def export_flutter_travel():
	data = (ROOT / "build/disc-assets/DAT/ST01T.BIN").read_bytes(); base = struct.unpack_from("<I", data, 12)[0]; offset = lambda address: 48 + address - base; records = {}
	for index in range(10):
		address = 0x800E92E4 + index * 16; stage, area, x, z, yaw, px, py, pz, heading = struct.unpack_from("<BB7h", data, offset(address)); records[hex(address)] = {"stage": "ST%02X" % stage, "area": area, "map_position": [x, z], "map_yaw_raw": yaw, "position_raw": [px, py, pz], "yaw_raw": heading}
	scenarios = {}
	for scenario in range(19):
		pointer = struct.unpack_from("<I", data, offset(0x800E94A4 + scenario * 4))[0]; destinations = []
		for index in range(10):
			address = struct.unpack_from("<I", data, offset(pointer + index * 4))[0]
			if not address: break
			destinations.append(dict(records[hex(address)], name=["Calinca", "Forbidden Island", "Sulphur Island", "Manda Island", "Nino Island", "Calbania Island", "Saul Kada"][index]))
		scenarios[str(scenario)] = destinations
	docks = {}; hull_records = {"ST08": (0x800F2670, 0), "ST10": (0x800F7BD0, 0), "ST3F": (0x800EF84C, 0), "ST24": (0x800F224C, 0), "ST17": (0x800FEDCC, 0), "ST23": (0x800EB59C, 0), "ST48": (0x800F8F9C, 0), "ST1F": (0x80101100, 0), "ST3C": (0x800FE658, 3)}
	from models import INTERIOR_SCRIPT_BINDINGS
	for stage, (address, area) in hull_records.items():
		overlay = (ROOT / "build/disc-assets/DAT" / (stage + "T.BIN")).read_bytes(); overlay_base = struct.unpack_from("<I", overlay, 12)[0]; raw = overlay[48 + address - overlay_base:68 + address - overlay_base]
		if len(raw) != 20 or raw[2] | (raw[4] << 8) | (raw[6] << 16) != 0x3020: raise ValueError(stage + " native Flutter hull record differs")
		owner = Path(INTERIOR_SCRIPT_BINDINGS.get(stage, {}).get("actor_archive_file", stage + ".BIN")).stem; scripted = ROOT / "assets/levels" / stage / "scripted_actors.json"; matches = sorted({ROOT / "assets/levels" / stage / instance["model_file"] for instance in json.loads(scripted.read_text())["instances"] if instance["source_record_ram"] == hex(address)}) if scripted.is_file() else []
		for path in [] if matches else (ROOT / "assets/levels" / stage / "models").glob(owner + "_*/manifest.json"):
			for model in json.loads(path.read_text())["models"]:
				if model.get("flags") == 0x3020: matches.append(ROOT / model["file"])
		if len(matches) != 1: raise ValueError(stage + " native Flutter hull model is not uniquely exported")
		model_file = ROOT / "assets/levels" / stage / "flutter_hull.glb"; write_output(model_file, matches[0].read_bytes()); pose = list(struct.unpack_from("<4h", raw, 12)); doors = json.loads((ROOT / "assets/levels" / stage / "doors.json").read_text()); boarding = next(route for route in doors["area_transitions"] if int(route["source_area"]) == area and route["destination_stage"] == "ST04" and int(route["destination_area"]) == 1); docks[stage] = {"area": area, "record": hex(address), "position_raw": pose[:3], "yaw_raw": pose[3], "boarding_raw": boarding["source_transform_raw"], "model_file": "res://" + model_file.relative_to(ROOT).as_posix()}
	docks["ST10"].update(st10_arrival_craft())
	landing = json.loads((ROOT / "assets/levels/ST08/scene_55.json").read_text()); contract = json.loads((ROOT / "assets/levels/ST08/scene_55_callbacks.json").read_text()); landing["callback_contract_file"] = "landing_callbacks.json"; landing["actors"][0]["entry"]["model_file"] = docks["ST08"]["model_file"]; contract["initialization"] = {"player_keep_transform": True, "spawn_records": ["0x800f2670"], "init_ops": [{"op": "player_render_flag", "set": False}]}; contract["finish"] = {"ops": [{"op": "player_render_flag", "set": True}]}; contract.pop("xa", None); write_output(ROOT / "assets/levels/ST01/landing.json", json.dumps(landing, indent=2) + "\n", encoding="utf-8"); write_output(ROOT / "assets/levels/ST01/landing_callbacks.json", json.dumps(contract, indent=2) + "\n", encoding="utf-8")
	vram, _ = texture_vram([ROOT / "build/disc-assets/COMMON/INIT.BIN", ROOT / "build/disc-assets/COMMON/GAME.BIN", ROOT / "build/disc-assets/DAT/ST01T.BIN"]); pixels = bytearray(512 * 512 * 4)
	write_output(ROOT / "assets/levels/ST01/location_pins.png", png(96, 80, b"".join(ui.hud_crop(ui.decode_page(vram, 0x1E, clut, True), 0, 0, 96, 24) + ui.hud_crop(ui.decode_page(vram, 0x1E, clut), 0, 24, 96, 16) for clut in (0x7FC0, 0x7FC1))))
	for quadrant, (tpage, clut) in enumerate(zip([0x95, 0x97, 0x99, 0x9B], [0x7C00, 0x7C40, 0x7C80, 0x7CC0])):
		for y in range(256):
			for x in range(256):
				word = disc.read_u16(vram, (((y + ((tpage >> 4) & 1) * 256) * 1024) + (tpage & 15) * 64 + x // 2) * 2); palette_index = (word >> ((x & 1) * 8)) & 255; palette = disc.read_u16(vram, ((clut >> 6) * 1024 + (clut & 63) * 16 + palette_index) * 2); target = ((y + (quadrant // 2) * 256) * 512 + x + (quadrant & 1) * 256) * 4; pixels[target:target + 4] = bytes(ui.color(palette, True))
	output = ROOT / "assets/levels/ST01"; write_output(output / "flutter.glb", (output / "models/ST01_00800/model_000.glb").read_bytes()); write_output(output / "world_map.png", png(512, 512, pixels)); write_output(output / "flutter_travel.json", json.dumps({"source": "ST01 800E92E4 destination records;800E94A4 scenario lists;800E8D50 map;800E7378 aircraft;800E8AAC pins;800E7B88 targets", "list_override": {"7": [6, 0x582, 7]}, "targets": {"0": [255], "1": [1], "2": [3], "3": [3], "4": [3, 0x3D0, 2], "5": [4], "6": [255], "7": [4, 0x582, 5], "8": [5], "9": [4], "10": [4, 0x3D1, 2], "11": [6], "12": [6], "13": [6, 0x3D2, 2], "14": [0], "15": [0], "16": [0, 0x3D3, 2], "17": [5], "18": [5]}, "launch_ticks": 20, "landing_ticks": 20, "tick_rate": 25, "scenarios": scenarios, "docks": docks, "redirects": st01_destination_redirects()}, indent=2) + "\n", encoding="utf-8")

# ---- tundra_follower ----
def add_tundra_follower(manifest, dat_dir, output_dir):
	import models
	dat_dir = Path(dat_dir); output_dir = Path(output_dir); overlay = (dat_dir / "ST0DT.BIN").read_bytes(); root = (dat_dir / "ST0D.BIN").read_bytes(); offset = lambda address: 48 + address - 0x800E7000; pointer = 0x800F0FD8; raw = overlay[offset(pointer):offset(pointer) + 20]
	if raw.hex() != "03002002600000000000000000d5cafbd0ee0000": raise ValueError("ST0D native Roll record changed")
	if struct.unpack_from("<I", overlay, offset(0x800EFC34))[0] != 0x800EB9BC: raise ValueError("ST0D Roll callback changed")
	work = models.ROOT / "build/stages"; archive = actor_archive_for_records("ST0D", root, [{"raw": raw}], work, dat_dir, 0xB000)
	if archive is None: raise ValueError("ST0D Roll model archive missing")
	match = [entry for entry in archive["archive"]["models"] if entry["flags"] & 0xFFFFFF == 0x6020]
	if len(match) != 1 or match[0]["index"] != 9: raise ValueError("ST0D Roll model identity changed")
	model_file = "actors/ST0D_model_09.glb"; (output_dir / "actors").mkdir(parents=True, exist_ok=True); model = models.export_actor_model(archive["payload"], 9, dat_dir / "ST0DT.BIN", output_dir / model_file, archive["archive_file"])
	model.update(model_index=9, model_file=model_file, native_resource_flags=0x6020, native_scale_raw=list(struct.unpack_from("<3h", archive["payload"], match[0]["mesh_offset"] + 0x30)), identity="Roll", role="roll_companion")
	set_id = "native_tundra_roll_follower"; predicates = [{"kind": "stage_state_byte_equals", "value": 0}, {"kind": "stage_area_byte_equals", "value": 0}, {"kind": "native_event_flag", "id": 0x5E1, "set": True}, {"kind": "native_event_flag", "id": 0x5E2, "set": False}]
	spawn = {"id": set_id, "area_index": 0, "predicate": {"all": predicates}, "source": {"file": "ST0DT.BIN", "call_pc": "0x800eeb24", "callback": "0x800eea1c", "consumer": "ST0DT800EEE54 -> SLES8003E5B0; GAME800DA49C/800DA4E8", "native_side_effects": [], "native_local_state_mutations": []}, "record_offsets": [offset(pointer)], "non_mesh_records": []}
	x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); cases = [{"player_xz": [13824, -4864], "actor_xz": [13680, -4864], "yaw_raw": 3072, "result": 1, "when_event_flag_clear": 0x5D0, "arrival_message_index": 22}, {"player_xz": [12288, -2304], "actor_xz": [12160, -2304], "yaw_raw": 3072, "result": 2}]
	instance = {"stage": "ST0D", "spawn_set": set_id, "area_index": 0, "source_pc": "0x800eeb24", "record_ordinal": 0, "file_offset": offset(pointer), "source_record_ram": hex(pointer), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "resource_variant": raw[6], "resource_key": raw[7], "control": raw[8], "frame": raw[9], "native_private_raw": list(raw[8:12]), "source_bytes_hex": raw.hex(), "model_index": 9, "model_file": model_file, "identity": "Roll", "role": "roll_companion", "native_follower_profile": "tundra", "native_resource_flags": 0x6020, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256, -y / 256, z / 256], "yaw_raw": yaw, "yaw_turns": -yaw / 4096, "floor_height": True}, "native_pose_resolver": {"source": "ST0DT800EEB30..800EEC9C", "player_pose_key": "native_player_pose_raw", "cases": cases, "default": {"actor_xz": [x, z], "yaw_raw": yaw}}, "native_animation_startup": {"control": 0, "start_record": 0, "source_constructor": "0x800EBD78", "source_update": "0x800EB9BC"}, "native_hitbox": {"bounds_raw": list(struct.unpack_from("<6h", overlay, offset(0x800F0EFC))), "source_pointer_ram": "0x800f0efc", "source_field": "actor+0x58", "source_constructor": "0x800ebd78", "source_consumer": "GAME800B13B4/800B3564", "anchor": "actor+0x10"}, "native_interaction": {"stage": "ST0D", "actor_class": 96, "actor_state": 0, "actor_callback": "0x800eb9bc", "request_call": "0x800ec138", "request_api": "0x800BE2E0", "request_kind": 0, "message_call": "0x800BDCF8", "message_index": raw[11], "index_source": "unsigned actor+0x0F, dynamically selected by the native companion controller", "window": 0, "bank_id": "0x8010C000", "source_record_ram": hex(pointer), "target_descriptor_raw": list(struct.unpack_from("<6h", overlay, offset(0x800F0F08))), "target_descriptor_source": "0x800f0f08", "target_flags60": 3, "target_selector_source": "GAME800CC2F0/800CC5B4", "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False}}, "native_following": {"idle_control": 0, "walk_control": 1, "run_control": 2, "walk_stop_control": 5, "run_stop_control": 6, "idle_start_distance_raw": 512, "walk_stop_distance_raw": 256, "walk_run_distance_raw": 1024, "run_stop_distance_raw": 512, "walk_speed_raw": 128, "run_speed_raw": 384, "walk_turn_raw": 64, "run_turn_raw": 96, "run_turn_while_player_moving_raw": 48, "source": "ST0DT800EC1E4/800EC288/800EC4A4", "unported": ["Combat, damage and scripted reaction states"]}}
	manifest["spawn_sets"] = [entry for entry in manifest.get("spawn_sets", []) if entry["id"] != set_id] + [spawn]; manifest["instances"] = [entry for entry in manifest.get("instances", []) if entry.get("spawn_set") != set_id] + [instance]; manifest["models"] = [entry for entry in manifest.get("models", []) if entry.get("model_index") != 9] + [model]
	manifest["source"]["native_tundra_follower"] = {"record": hex(pointer), "overlay_sha256": sha256(overlay), "model_flags": "0x6020", "callback": "0x800EB9BC", "constructor": "0x800EBD78", "spawn_predicate": "area0, scenario0, flag5E1 set, flag5E2 clear"}
	write_output(output_dir / "scripted_actors.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); return manifest

# ---- tundra_spawner ----
def add_tundra_spawners(profile, overlay, game, dat_dir, output_dir, archive):
	import models
	offset = lambda address: 48 + address - 0x800E7000; game_offset = lambda address: address - 0x800AD000 + 0x30; word = lambda data, position: struct.unpack_from("<I", data, position)[0]
	if [word(game, game_offset(0x800DD978 + index * 4)) for index in range(5)] != [0x800DA778, 0x800DA7A0, 0x800DA7E4, 0x800DA91C, 0x800DB130] or [word(game, game_offset(0x800DD98C + index * 4)) for index in range(3)] != [0x800DAB94, 0x800DACF4, 0x800DB108]: raise ValueError("ST0D pop-up spawner callbacks changed")
	if word(overlay, offset(0x800E70E0)) != 0x3C02800F or word(overlay, offset(0x800E70E4)) != 0x24420200 or word(overlay, offset(0x800E7078)) != 0x24040012: raise ValueError("ST0D pop-up spawner registration changed")
	tables = [word(overlay, offset(0x800F0200 + index * 4)) for index in range(5)]
	if tables != [0x800F00B4, 0x800F00D8, 0x800F00FC, 0x800F01BC, 0x800F01FC]: raise ValueError("ST0D pop-up spawner tables changed")
	templates = [overlay[offset(tables[0] + index * 12):offset(tables[0] + index * 12) + 12] for index in range((min(word(overlay, offset(tables[1] + index * 12)) for index in range((tables[2] - tables[1]) // 12)) - tables[0]) // 12)]
	if [template.hex() for template in templates] != ["030020020500000001000000", "030020020500000000000000"]: raise ValueError("ST0D pop-up templates changed")
	def index_list(pointer):
		values = []
		while overlay[offset(pointer) + len(values)] < 128: values.append(overlay[offset(pointer) + len(values)])
		return values
	def node_list(pointer):
		nodes = []
		while True:
			x, y, z, flag = struct.unpack_from("<hhhH", overlay, offset(pointer) + len(nodes) * 8); nodes.append({"x": x, "y": y, "z": z, "flag": flag})
			if flag & 0x8000: return nodes
	zones = []
	for index in range((tables[2] - tables[1]) // 12):
		pointer, flags, spawn_radius, despawn_radius, cooldown = struct.unpack_from("<IHHHH", overlay, offset(tables[1] + index * 12)); zones.append({"index_list_ram": hex(pointer), "indices": index_list(pointer), "flags": flags, "spawn_radius": spawn_radius, "despawn_radius": despawn_radius, "despawn_ticks": cooldown})
	selectors = [list(overlay[offset(tables[4] + index * 2):offset(tables[4] + index * 2) + 2]) for index in range((0x800F0200 - tables[4]) // 2)]; node_sets = []
	for index in range((tables[4] - tables[3]) // 32):
		quadrants = []
		for quadrant in range(4):
			pointer, delay_index, music = struct.unpack_from("<IBB", overlay, offset(tables[3] + index * 32 + quadrant * 8)); quadrants.append({"nodes_ram": hex(pointer), "delay_index": delay_index, "music": music, "nodes": node_list(pointer)})
		node_sets.append(quadrants)
	immediate = lambda address: struct.unpack_from("<h", overlay, offset(address))[0]; gate = {"area": 0, "stage_state": 0, "flags_set": [0x5E1], "flags_clear": [0x5E2], "far_minimum": immediate(0x800EED5C), "release_minimum": immediate(0x800EED64), "band_maximum": immediate(0x800EED94), "band_minimum": immediate(0x800EED9C), "source": "ST0DT800EECD0..800EEDBC toggles GAME800469E0 bit 0x200 from player x; disabled at 800EECAC when the Roll record 800EEB24 is constructed"}
	if [word(overlay, offset(address)) >> 26 for address in (0x800EED5C, 0x800EED64, 0x800EED94, 0x800EED9C)] != [10, 10, 10, 10] or (gate["far_minimum"], gate["release_minimum"], gate["band_maximum"], gate["band_minimum"]) != (-0x1200, -0x7FF, -0x800, -0x11FF): raise ValueError("ST0D pop-up Roll gate changed")
	terrain = Stage((dat_dir / "ST0D.BIN").read_bytes()); grids = {}
	for area in (0, 1):
		tiles, _ = terrain.area(area); keys = list(tiles); x0 = min(key[0] for key in keys); x1 = max(key[0] for key in keys); z0 = min(key[1] for key in keys); z1 = max(key[1] for key in keys)
		grids[str(area)] = {"x_minimum": x0, "z_minimum": z0, "width": x1 - x0 + 1, "rows": ["".join("1" if (x, z) in tiles and (value := struct.unpack_from("<H", tiles[(x, z)], 0)[0]) & 0x8000 and value & 0x4000 and not value & 0x400 else "0" for x in range(x0, x1 + 1)) for z in range(z0, z1 + 1)]}
	raw = templates[0] + bytes(8); resource = overlay[offset(0x800F0BE8 + raw[7])]; flags = 0x20 | raw[4] << 8 | resource << 16; matches = [entry for entry in archive["archive"]["models"] if entry["flags"] & 0xFFFFFF == flags]
	if len(matches) != 1: raise ValueError("ST0D pop-up enemy model selector is unresolved")
	index = matches[0]["index"]; model_file = f"actors/ST0D_model_{index:02d}.glb"; model = models.export_actor_model(archive["payload"], index, dat_dir / "ST0DT.BIN", output_dir / "ST0D" / model_file, archive["archive_file"]); model.update(model_index=index, model_file=model_file, native_resource_flags=matches[0]["flags"])
	profile["models"] = [entry for entry in profile["models"] if entry["model_index"] != index] + [model]; combat = models.source_combat_attributes(game, raw[4], raw[7]); bounds = list(struct.unpack_from("<6h", overlay, offset(0x800F0B68)))
	profile["popup_spawner"] = {"source": {"controller_registration": "ST0DT800E7074..800E7110 -> GAME800D97EC(mask 0x12): kind1 controller 800DA644", "controller_states": "GAME800DD978: 800DA778,800DA7A0,800DA7E4,800DA91C,800DB130", "spawn_states": "GAME800DD98C: 800DAB94,800DACF4,800DB108", "despawn_check": "GAME800DB1D0/800DB59C", "tile_check": "GAME800DB85C/800DB924", "tables_ram": hex(0x800F0200), "enemy_callback": "ST0DT800E8FC4", "enemy_constructor": "ST0DT800E9228", "enemy_rise": "ST0DT800E94B8", "enemy_leave": "ST0DT800EB03C"},
		"roll_gate": gate, "tile_shift": 9, "step_thresholds": list(game[game_offset(0x800DD998):game_offset(0x800DD998) + 8]), "chance_words": [word(game, game_offset(0x800DD9A0 + index * 4)) for index in range(16)], "delay_words": [word(game, game_offset(0x800DD9C0 + index * 4)) for index in range(8)], "base_maximum": 6,
		"zone_selector": list(overlay[offset(tables[2]):offset(tables[2]) + 32]), "zones": zones, "node_selectors": selectors, "node_sets": node_sets, "templates": [template.hex() for template in templates], "tile_grids": grids,
		"enemy": {"stage": "ST0D", "actor_class": raw[4], "dispatch_index": raw[6], "actor_resource_key": raw[7], "model_index": index, "model_file": model_file, "source_bytes_hex": raw.hex(), "combat": combat, "source_attributes": combat["normal"]["attributes"], "native_hitbox": {"bounds_raw": bounds}, "startup_control": {"code": 0}, "transform": {"position": [0.0, 0.0, 0.0], "yaw_raw": 0}, "instance_id": -1, "script_area_index": 0, "flags": 0, "flags2": 0},
		"rules": {"rise_depth_raw": 180, "rise_step_raw": 12, "rise_dust_interval": 3, "rise_sound": 0xA3, "leave_sound": 0xA4, "leave_step_raw": 16, "leave_distance_raw": 0x600, "leave_ticks": 30, "attack_gate_slot": overlay[offset(0x800F0BF4 + (raw[6] & 15))], "attack_gate_table": hex(0x800F0214), "attack_distance_raw": 0x2BC, "offscreen_x_limit": 0x140, "offscreen_y_limit": 0xF0, "onscreen_despawn_distance_squared": 0x0A900000}}

# ---- mine_quest ----
def add_items(stage, profile, overlay, dat_dir, output_dir):
	import models
	offset = lambda pointer: 48 + pointer - 0x800E7000; pointer = struct.unpack_from("<I", overlay, offset(0x800F0ED4 if stage == "ST0D" else 0x80100E30))[0]; items = []
	if stage == "ST0D":
		sources = [record for record in profile["exterior_enemies"] if record["actor_class"] == 21]; profile["exterior_enemies"] = [record for record in profile["exterior_enemies"] if record["actor_class"] != 21]
		profile["item_models"] = [model for model in profile["models"] if any(model["model_index"] == record["model_index"] for record in sources)]
	else:
		npcs = json.loads((output_dir / stage / "npcs.json").read_text(encoding="utf-8")); sources = []; archive, payload = models.actor_archive(dat_dir / "ST0F00.BIN"); match = next(model for model in archive["models"] if model["flags"] & 65535 == 0x1520); model = models.export_actor_model(payload, match["index"], dat_dir / "ST0FT.BIN", output_dir / stage / "actors/mine_chest.glb", "ST0F00.BIN"); model.update(model_index=match["index"], model_file="actors/mine_chest.glb"); profile["item_models"] = [model]
		for record in npcs["static_actor_instances"]:
			raw = bytes.fromhex(record["source_bytes_hex"])
			if raw[4] == 21: sources.append(dict(record, stage=stage, actor_class=21, dispatch_index=raw[6], model_file="actors/mine_chest.glb", model_index=match["index"]))
	for record in sources:
		raw = bytes.fromhex(record["source_bytes_hex"]); flag, message, reward = struct.unpack_from("<HHI", overlay, offset(pointer + raw[6] * 8)); body = 0x800F0ED8 if stage == "ST0D" else 0x80100E34; target = 0x800F0EE4 if stage == "ST0D" else 0x80100E40; record["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, offset(body)))}; record["native_interaction"] = {"stage": stage, "message_index": message, "message_call": "0x800BE330", "request_kind": 0, "target_descriptor_raw": list(struct.unpack_from("<6h", overlay, offset(target))), "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 384, "strict_bounds": True}}; record["startup_control"] = {"code": 0}; items.append({"entry": record, "collected_flag": flag, "message_index": message, "reward_word": reward, "descriptor_ram": hex(pointer + raw[6] * 8), "source_callback": "0x800EB760" if stage == "ST0D" else "0x800EEEEC"})
	profile["items"] = items
	for item in items:
		item["entry"]["native_interaction"]["bank_id"] = "0x8010C000"; item["entry"]["native_interaction"]["target_criteria"]["line_of_sight"] = False
	if stage == "ST0D":
		models.export_pickup_data((dat_dir.parent / "COMMON/GAME.BIN").read_bytes(), output_dir / stage)
		for record in profile["exterior_enemies"]:
			record["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, offset(0x800F0F50)))}; record["native_target_bounds"] = list(struct.unpack_from("<6h", overlay, offset(0x800F0F5C))); record["behavior_dispatch"].update(constructor="0x800ED698", state_callbacks=["0x800ED86C", "0x800ED8DC", "0x800EDC58", "0x800EDE3C", "0x800EDECC"], hit_callback="0x800EE51C", death_callback="0x800EE45C"); record["native_health_scale"] = 1
def export_mine_quest(dat_dir, output_dir):
	import models
	dat_dir = Path(dat_dir); output_dir = Path(output_dir); game = (dat_dir.parent / "COMMON/GAME.BIN").read_bytes(); result = {}
	for stage in ("ST0D", "ST0F"):
		overlay = (dat_dir / f"{stage}T.BIN").read_bytes(); offset = lambda pointer: 48 + pointer - 0x800E7000; instances = []; model_list = []
		if stage == "ST0D":
			definitions = [(0, 0x800F0020, 0x800ED490), (0, 0x800F0034, 0x800ED490), (1, 0x800F0084, None)]; records = [{"raw": overlay[offset(pointer):offset(pointer) + 20]} for _, pointer, _ in definitions]; archive = actor_archive_for_records(stage, (dat_dir / f"{stage}.BIN").read_bytes(), records, models.ROOT / "build/stages", dat_dir, 0xB000); exported = {}
			for area, pointer, callback in definitions:
				raw = overlay[offset(pointer):offset(pointer) + 20]; actor_class = raw[4]; matches = [entry for entry in archive["archive"]["models"] if entry["flags"] & 0xFFFF == (actor_class << 8 | 0x20)]
				if len(matches) != 1: raise ValueError(f"{stage} class{actor_class:02X} model selector is unresolved")
				index = matches[0]["index"]; model_file = f"actors/{stage}_model_{index:02d}.glb"
				if index not in exported:
					model = models.export_actor_model(archive["payload"], index, dat_dir / f"{stage}T.BIN", output_dir / stage / model_file, archive["archive_file"]); model.update(model_index=index, model_file=model_file, native_resource_flags=matches[0]["flags"]); exported[index] = model; model_list.append(model)
				x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); combat = models.source_combat_attributes(game, actor_class, raw[7]); instances.append({"stage": stage, "area_index": area, "source_record_ram": hex(pointer), "source_bytes_hex": raw.hex(), "actor_class": actor_class, "dispatch_index": raw[6], "actor_resource_key": raw[7], "model_index": index, "model_file": model_file, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256, -y / 256, z / 256], "yaw_turns": -yaw / 4096}, "combat": combat, "source_attributes": combat["normal"]["attributes"], "behavior_dispatch": {"actor_class": actor_class, "class_callback": hex(callback) if callback else None}, "source": {"loader": "SLES8003D3F8", "area_table": "ST0DT800F00AC", "spawn_gate": "static area list; no quest flag predicate"}})
			profile = {"stage": stage, "tick_rate": 25, "entrance": {"source_transform_raw": [13056, -1632, -2304, 3072], "destination_stage": "ST0F", "destination_area": 0, "destination_transform_raw": [-2304, -1, 512, 3072], "route_pointer_ram": "0x800F0308", "native_lock_event": 0x710, "source": "ST0DT route table800F0370; GAME800B89B4 lock consumer", "source_contact_unresolved": True}, "exterior_enemies": instances, "models": model_list}
		else:
			row = struct.unpack_from("<I", overlay, offset(0x801008F4))[0]; handlers = list(struct.unpack_from("<13I", overlay, offset(row))); scene_ids = [0x50, 0x51, 0x52, 0x53, 0x54]; actor_records = []
			for pointer in (0x801007EC, 0x80100800, 0x80100814, 0x80100828, 0x8010083C, 0x80100850, 0x80100864, 0x80100878):
				raw = overlay[offset(pointer):offset(pointer) + 20]; actor_records.append({"source_record_ram": hex(pointer), "source_bytes_hex": raw.hex(), "actor_class": raw[4], "record_type": raw[2], "transform_raw": list(struct.unpack_from("<hhhH", raw, 12))})
			profile = {"stage": stage, "tick_rate": 25, "scenario0_area_callbacks": [hex(pointer) for pointer in handlers], "scene_ids": scene_ids, "records": actor_records, "quest_flags": {"intro": 0x580, "pre_boss": 0x581, "battle_started": 0x582, "boss_defeated": 0x583, "return_scene": 0x584, "entrance_initialized": 0x585}, "intro": {"area": 1, "native_x_minimum": 3072, "flag": 0x580, "scene": 0x50, "source": "ST0FT800E76F4..7714"}, "pre_boss": {"area": 11, "scene": 0x51, "flag": 0x581, "source": "ST0FT800E7738..7808"}, "boss": {"area": 12, "scene_start": 0x52, "scene_defeat": 0x53, "actor_pointer_ram": "0x8009C900", "actor_pointer_writer": "ST0FT800FE880..FE888 copies scene-owner+2C", "actor_record_ram": "0x80100850", "actor_class": 0x6F, "class_callback": "0x800F1E2C", "death_test": "signed16(actor+70)<0", "source": "ST0FT800E780C..78E4"}, "return": {"area": 11, "requires_set": 0x583, "requires_clear": 0x584, "flag_set": 0x584, "scene": 0x54, "source": "ST0FT800E7768..77AC"}, "entry_actions": {"area": 0, "first_visit_set": [0x783, 0x585], "first_visit_records": ["0x801007EC", "0x80100800"], "every_entry_clear": [0x5D0, *range(0x710, 0x730)], "source": "ST0FT800E7574..7600"}}
		if stage == "ST0D":
			terrain = Stage((dat_dir / "ST0D.BIN").read_bytes()); tiles, _ = terrain.area(0); _, model_id, _, height, x, z = terrain.placements[67]; _, header, directory = terrain.directories[model_id]; variant = terrain.base + (directory & 65535) * 4 + 12; pointer = struct.unpack_from("<H", terrain.data, variant)[0]; groups = terrain.model(pointer); ox = (x << 9) - (0x7E00 if header & 0x10000000 else 0x7F00); oz = (z << 9) - (0x7E00 if header & 0x20000000 else 0x7F00); oy = 0x400 - tiles[(x, z)][6] * 16 - ((height & 0x7F00) >> 4); vram, _ = textures(dat_dir / "ST0DT.BIN"); glb = Glb(vram); glb.instance("placement_067_model_015", pointer, groups, [-ox / 256, -oy / 256, oz / 256], terrain.face_metadata[pointer]); glb.save(output_dir / stage / "mine_entrance_open.glb"); collision_pointer = struct.unpack_from("<H", terrain.data, variant + 2)[0] * 4 + terrain.base; boxes = []
			for index in range(terrain.data[variant + 6]):
				address = collision_pointer + index * 16; values = struct.unpack_from("<6h2H", terrain.data, address); boxes.append({"x": [values[0] + ox, values[1] + ox], "z": [values[2] + oz, values[3] + oz], "y": [values[4] + oy, values[5] + oy], "kind": values[6], "mask": values[7], "placement": 67, "source_offset": hex(address), "contact_raw": [(values[0] + values[1]) // 2 + ox, (values[4] + values[5]) // 2 + oy, (values[2] + values[3]) // 2 + oz]})
			contact = next(box for box in boxes if box["kind"] >> 8 == 15); contact.update(type=15, automatic=True, probe_forward_raw=0, source_consumer="GAME800B8588;type15:800B8134->800B8460"); doors = json.loads((output_dir / stage / "doors.json").read_text(encoding="utf-8")); walk = next(route["native_automatic_walk"] for route in doors["area_transitions"] if route.get("native_automatic_walk")); profile["entrance"].update(availability={"any": [{"kind": "stage_state_byte_not_equals", "value": 0}, {"kind": "native_event_flag", "id": 0x5E1, "set": True}, {"kind": "native_event_flag", "id": 0x5E2, "set": True}]}, placement=67, model_variant=1, model_file="mine_entrance_open.glb", collision_boxes=boxes, native_contacts=[contact], native_automatic_walk=walk, source_contact_unresolved=False, source_variant="ST0DT800EEA3C..EEB14 GAME800C010C sets variant1 for placement cell89,59")
		else:
			pointer = 0x8010180C; raw = overlay[offset(pointer):offset(pointer) + 20]; profile["records"].append({"source_record_ram": hex(pointer), "source_bytes_hex": raw.hex(), "actor_class": raw[4], "record_type": raw[2], "transform_raw": list(struct.unpack_from("<hhhH", raw, 12))}); callback_row = struct.unpack_from("<I", overlay, offset(0x800FF4E0 + 7 * 4))[0]; callback = struct.unpack_from("<I", overlay, offset(callback_row))[0]; profile["boss"].update(actor_class=7, actor_record_ram=hex(pointer), record_type=0x20, class_callback=hex(callback), registration_command_ram="0x80101890", registration_slot=0); profile["item_gate"] = {"area": 8, "event_flag": 0x2B3, "helper": "SLES800464B4", "set_mode": 8, "clear_mode": 7, "source": "ST0FT800E7498..752C"}; profile["intro"]["native_states"] = [{"state": 0, "actions": [{"clear_pointer": "0x8009C904"}, {"next_state": 1}]}, {"state": 1, "context_must_be_inactive": True, "flag580_set_record": "0x8010083C", "flag580_set_next_state": 2, "flag580_clear_flag689_clear_record": "0x80100814", "flag580_clear_flag689_clear_set": 0x689, "flag580_clear_flag689_set_record": "0x80100828", "source": "ST0FT800E7660..76F0"}, {"state": 2, "native_x_minimum": 3072, "set_flag": 0x580, "scene": 0x50, "next_state": 3}]
		if stage == "ST0F":
			profile["intro"]["native_states"][1].update(flag580_set_next_state=3, flag580_clear_next_state=2); profile["roll_routes"] = {}
			for record, table, count in [(0x801007EC, 0x80100F0C, 6), (0x80100814, 0x80100F3C, 5)]: profile["roll_routes"][hex(record)] = {"points_raw": [list(struct.unpack_from("<4h", overlay, offset(table) + index * 8)) for index in range(count)], "table_ram": hex(table), "callback": "0x800F1538/0x800F1684", "speed_raw": 608, "turn_raw": 56, "terminal_turn_raw": 128, "arrival_box_half_extent_raw": 32}
			profile["roll_target"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, offset(0x80100F00))), "source": "ST0FT80100F00;constructorF128C", "flags60": 1}
			profile["refractor"] = {"actor_record_ram": "0x80100850", "actor_class": 0x6F, "callback": "0x800F1A8C", "constructor": "0x800F1BC8", "interaction_callback": "0x800F1CEC", "request_call": "0x800F1D90", "request_kind": 0x12, "message_index": 30, "target_bounds_raw": list(struct.unpack_from("<6h", overlay, offset(0x80100F90))), "body_bounds_raw": list(struct.unpack_from("<6h", overlay, offset(0x80100F84))), "yaw_step_raw": 16, "scale_raw": 1024, "boss_defeated_redirect": {"flag": 0x583, "message": 34, "tail_message": 35, "clear_flag": 0x710}, "native_bob": {"callback": "0x800F1B2C..1B6C", "table_ram": "0x800965D8", "table_count": 64, "sample_shift": 8, "sample_bias": -8, "samples_bound": False}, "source": "ST0FT PBDcallbacktable800FF4E0[class6F]->800FF4DC->800F1A8C;message30redirects583to34then35clears710"}
			executable = (dat_dir.parent / "SLES_035.56").read_bytes(); profile["refractor"]["native_bob"].update(samples_bound=True, samples_raw=[struct.unpack_from("<h", executable, 0x800 + 0x80073E4E - 0x80010000 + phase * 64 * 4)[0] for phase in range(64)], initializer="SLES800112B8..11314 copiescosinefrom80073E4E every64phases into800965D8")
			raw = overlay[offset(0x80100800):offset(0x80100800) + 20]; profile["procedural_actors"] = [{"stage": "ST0F", "area_index": 0, "source_record_ram": "0x80100800", "record_type": raw[2], "actor_class": raw[4], "source_bytes_hex": raw.hex(), "callback": "0x800FAA44", "dispatch": raw[6], "message_index": struct.unpack_from("<h", raw, 8)[0], "window": 4, "bank_id": "0x8010C000", "message_call": "0x800FB124", "maximum_scenario": struct.unpack_from("<b", raw, 10)[0], "skip_when_flag_set": struct.unpack_from("<h", raw, 18)[0], "message_source": "ST0FT800FB0FC..FB148 configureswindow4andcalls80048474 withsignedactor+0C;recordsource80100800", "source_dispatch": "SLES8003D010 scriptpool->ST0FT800FF784[0x1B]=800FAA44;subtype0table80101344[0]=800FAB48->800FB0FC"}]
		if stage == "ST0D": add_tundra_spawners(profile, overlay, game, dat_dir, output_dir, archive)
		add_items(stage, profile, overlay, dat_dir, output_dir); profile["source"] = {"overlay_sha256": sha256(overlay), "original_overlay": f"DAT/{stage}T.BIN"}; target = output_dir / stage / "mine_quest.json"; write_output(target, json.dumps(profile, indent=2) + "\n", encoding="utf-8"); result[stage] = profile
	return result

ACTOR_RECORD_KINDS = {0x00: "area_header", 0x20: "actor", 0x40: "type40", 0x60: "prop", 0x61: "prop", 0xA0: "object_a0", 0xA1: "door", 0xE0: "controller_e0"}
ACTOR_EXPORT_FILES = {"npcs.json": "npc", "scripted_actors.json": "scripted", "pickups.json": "pickup", "mine_actors.json": "mine"}
ACTOR_CAPABILITIES = {"native_interaction": "talk", "native_movement": "movement", "native_enemy": "enemy", "native_follower_profile": "follower", "native_kickable": "kickable", "native_lock_on": "lock_on", "native_pose_resolver": "pose_resolver"}
ACTOR_CLASS_ROLES = {"20/0": "talk NPC (shared class-0 template)", "20/1": "Data terminal (shared class-1 template)", "20/21": "treasure chest (shared callback)", "20/111": "Refractor", "20/48": "Flutter vehicle", "20/23": "Forbidden Island enemy", "20/41": "Forbidden Island burrower", "20/59": "Forbidden Island boss"}
def actor_export_index(levels_dir, props_dir, stage):
	index = {}
	def visit(node, source):
		if isinstance(node, dict):
			raw = next((node[key] for key in ("source_bytes_hex", "source_bytes", "bytes_hex") if isinstance(node.get(key), str) and len(node[key]) == 40), None)
			if raw is not None:
				entry = index.setdefault(raw, {"sources": set(), "capabilities": set(), "callbacks": set(), "spawn_gated": False}); entry["sources"].add(source); entry["capabilities"].update(label for key, label in ACTOR_CAPABILITIES.items() if key in node)
				interaction = node.get("native_interaction") if isinstance(node.get("native_interaction"), dict) else {}; dispatch = node.get("behavior_dispatch") if isinstance(node.get("behavior_dispatch"), dict) else {}
				entry["callbacks"].update(str(value) for value in (interaction.get("actor_callback"), dispatch.get("class_callback")) if value); entry["spawn_gated"] = entry["spawn_gated"] or "spawn_set" in node
			for value in node.values(): visit(value, source)
		elif isinstance(node, list):
			for value in node: visit(value, source)
	for name, source in ACTOR_EXPORT_FILES.items():
		path = levels_dir / stage / name
		if path.is_file(): visit(json.loads(path.read_text(encoding="utf-8")), source)
	manifest = json.loads((props_dir / "manifest.json").read_text(encoding="utf-8")).get("stages", {}).get(stage, {}) if (props_dir / "manifest.json").is_file() else {}
	visit(manifest.get("instances", []), "static_prop")
	return index, manifest
def actor_class_callbacks(stage, overlay):
	chest = chest_profile(stage, overlay, True)
	if chest is None: return {}
	base = chest["base"]; count = (len(overlay) - 0x30) // 4; words = struct.unpack_from("<%dI" % count, overlay, 0x30); inside = lambda value: base <= value < base + count * 4 and value % 4 == 0; cell = chest["callback"] - 0x204
	cells = [base + index * 4 for index, word in enumerate(words) if word == cell]; slots = [base + index * 4 for index, word in enumerate(words) if word in cells]
	if len(slots) != 1: return {}
	table = slots[0] - 21 * 4; result = {}
	for actor_class in range(128):
		entry = table + actor_class * 4
		if not inside(entry): break
		pointer = words[(entry - base) // 4]
		if pointer and inside(pointer) and inside(words[(pointer - base) // 4]): result[actor_class] = hex(words[(pointer - base) // 4])
	return result
def actor_resource_keys(stage, overlay):
	callbacks = actor_class_callbacks(stage, overlay); base = read_u32(overlay, 12) or BASE; count = (len(overlay) - 0x30) // 4; words = struct.unpack_from("<%dI" % count, overlay, 0x30); word = lambda address: words[(address - base) // 4] if base <= address < base + count * 4 and address % 4 == 0 else None; keys = {}
	def constructor(callback):
		for at in range(callback, callback + 0x100, 4):
			high = word(at)
			if high is None or high >> 26 != 0x0F: continue
			for later in range(at + 4, at + 24, 4):
				low = word(later)
				if low is not None and low >> 26 == 9 and (low >> 21) & 31 == (high >> 16) & 31 and (low >> 16) & 31 == (high >> 16) & 31:
					table = (((high & 0xFFFF) << 16) + (low & 0xFFFF) - (0x10000 if low & 0x8000 else 0)) & 0xFFFFFFFF; entry = word(table)
					if entry is not None and word(entry) is not None and word(entry) >> 16 == 0x27BD: return entry
		return None
	for actor_class, callback in callbacks.items():
		entry = constructor(int(callback, 16))
		if entry is None: continue
		for at in range(entry, entry + 0x100, 4):
			call = word(at)
			if call in (0x0C00F7E9, 0x0C00F7F2):
				offset = None
				for near in range(at - 8, at + 12, 4):
					value = word(near)
					if value is not None and value >> 26 == 9 and (value >> 16) & 31 == 5 and (value >> 21) & 31 in (16, 17, 18): offset = value & 0xFFFF
				keys[actor_class] = offset if call == 0x0C00F7F2 else None; break
	return keys
DUNGEON_ENEMIES = {("ST13", 38): "res://scripts/world/enemies/native_dungeon_turret.gd", ("ST13", 32): "res://scripts/world/enemies/native_dungeon_blade.gd"}
def export_dungeon_effects(stage, vram):
	game_vram, _ = ui.textures(ROOT / "build/disc-assets/COMMON/GAME.BIN"); output = ROOT / "assets/levels" / stage
	write_output(output / "effect_burst.png", ui.png(192, 96, ui.hud_crop(ui.decode_page(game_vram, 0x2E, 0x7C10), 0, 0, 192, 96)))
	pixels = bytearray()
	for v in range(24):
		for u in range(24):
			index = (read_u16(vram, ((0x80 + v) * 1024 + 896 + (u >> 2)) * 2) >> ((u & 3) * 4)) & 15; level = index * 17; pixels += bytes((level, level, level, 255 if index else 0))
	write_output(output / "effect_projectile.png", png(24, 24, bytes(pixels)))
def dungeon_enemy_entry(stage, actor_class, instance, callbacks, output_dir):
	import models
	game = (ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes(); combat = models.source_combat_attributes(game, actor_class, 0); models.export_pickup_data(game, ROOT / "assets/levels" / stage)
	return {"stage": stage, "actor_class": actor_class, "resource_key": 0, "source_attributes": combat["normal"]["attributes"], "combat": combat, "native_enemy": {"callback": callbacks.get(actor_class), "script": DUNGEON_ENEMIES[(stage, actor_class)]}, "native_hitbox": {"bounds_raw": [0, 0, 0, 0, 0, 0]}, "transform": {"position": instance["position"], "yaw_raw": instance["yaw_raw"], "yaw_turns": instance["yaw_turns"]}}
def actor_talk_sites(stage, overlay):
	base = read_u32(overlay, 12) or BASE; count = (len(overlay) - 0x30) // 4; words = struct.unpack_from("<%dI" % count, overlay, 0x30); bound = {profile[1] for profile in NATIVE_SCRIPTED_INTERACTIONS.get(stage, {}).values()}; sites = []
	for index, word in enumerate(words):
		if word != 0x0C02F8B8: continue
		if not any((words[at] >> 26) in (0x20, 0x24) and (words[at] & 0xFFFF) == 0xF and ((words[at] >> 16) & 31) == 7 for at in range(max(0, index - 10), index)): continue
		function = next((base + at * 4 for at in range(index, max(0, index - 4096), -1) if (words[at] >> 16) == 0x27BD and words[at] & 0x8000), None); sites.append({"request_call": hex(base + index * 4), "function": hex(function) if function else None, "bound": base + index * 4 in bound})
	return sites
def actor_scripted_summary(path):
	if not path.is_file(): return None
	data = json.loads(path.read_text(encoding="utf-8")); instances = data.get("instances", []); capabilities = Counter(label for entry in instances for key, label in ACTOR_CAPABILITIES.items() if key in entry)
	return {"instances": len(instances), "spawn_sets": len(data.get("spawn_sets", [])), "unported_script_paths": len(data.get("unported_native_script_paths", [])), "classes": dict(sorted(Counter(str(entry.get("actor_class", entry.get("record_class", "?"))) for entry in instances).items())), "capabilities": dict(capabilities)}
def export_actor_coverage(dat_dir=None, levels_dir=None, props_dir=None, docs_dir=None):
	import models
	dat_dir = dat_dir or ROOT / "build/disc-assets/DAT"; levels_dir = levels_dir or ROOT / "assets/levels"; props_dir = props_dir or ROOT / "assets/stage_props"; docs_dir = docs_dir or ROOT / "docs"; summary = {}; class_totals = defaultdict(lambda: {"records": 0, "exported": 0, "stages": set()})
	for overlay_path in sorted(dat_dir.glob("ST??T.BIN")):
		stage = overlay_path.name[:4]; source = (dat_dir / (stage + ".BIN")).read_bytes(); overlay = overlay_path.read_bytes()
		try: area_count = len(Stage(source).grids); detected = native_actor_lists(overlay, area_count)
		except (ValueError, IndexError, KeyError, struct.error): summary[stage] = {"name": STAGE_NAMES.get(stage, ""), "status": "no_actor_list"}; continue
		if not detected: summary[stage] = {"name": STAGE_NAMES.get(stage, ""), "areas": area_count, "status": "no_actor_list"}; continue
		index, manifest = actor_export_index(levels_dir, props_dir, stage); talk_sites = actor_talk_sites(stage, overlay); class_callbacks = actor_class_callbacks(stage, overlay); classes = {}; kinds = Counter(); exported = missing = 0; unresolved = {item["source_bytes"] for item in manifest.get("unresolved_instances", []) if "source_bytes" in item}
		for record in detected[0]["records"]:
			raw = record["raw"]; kind = ACTOR_RECORD_KINDS.get(raw[2], "type%02X" % raw[2]); kinds[kind] += 1
			if kind == "area_header": continue
			key = "%02X/%d/v%d" % (raw[2], raw[4], raw[6]) if kind in ("actor", "prop") else "%02X/%d" % (raw[2], raw[4]); item = classes.setdefault(key, {"kind": kind, "records": 0, "exported": 0, "sources": set(), "capabilities": set(), "callbacks": set(), "spawn_gated": False, "areas": set(), "class_callback": class_callbacks.get(raw[4]) if kind in ("actor", "prop") else None})
			item["records"] += 1; item["areas"].add(record["area"]); found = index.get(raw.hex())
			if kind == "door" or (raw[2] == 0x60 and raw[4] == 2 and raw[5] == 0): item["exported"] += 1; item["sources"].add("doors.json" if kind == "door" else "weather"); exported += 1
			elif found: item["exported"] += 1; item["sources"].update(found["sources"]); item["capabilities"].update(found["capabilities"]); item["callbacks"].update(found["callbacks"]); item["spawn_gated"] = item["spawn_gated"] or found["spawn_gated"]; exported += 1
			else: missing += 1; item["unresolved_model"] = item.get("unresolved_model", False) or raw.hex() in unresolved
		for key, item in classes.items():
			total = class_totals[key]; total["records"] += item["records"]; total["exported"] += item["exported"]; total["stages"].add(stage)
		binding = {name: hex(table[name]) for table in (models.INTERIOR_SCRIPT_BINDINGS.get(stage, {}), models.NPC_STAGE_BINDINGS.get(stage, {})) for name in ("callback", "constructor", "hitbox", "dispatcher") if table.get(name)}
		has_actors = any(item["kind"] in ("actor", "prop", "controller_e0", "object_a0", "type40") for item in classes.values())
		export_files = sorted(name for name in ACTOR_EXPORT_FILES if (levels_dir / stage / name).is_file()); scripted = actor_scripted_summary(levels_dir / stage / "scripted_actors.json")
		category = "gameplay" if any(item["kind"] == "actor" for item in classes.values()) or export_files else "props_only" if has_actors else "room_only"
		summary[stage] = {"name": STAGE_NAMES.get(stage, ""), "areas": area_count, "status": "listed", "category": category, "records": dict(kinds), "exported_records": exported, "unexported_records": missing, "export_files": export_files, "scripted": scripted, "talk_sites": talk_sites, "bindings": binding, "classes": {key: {**item, "sources": sorted(item["sources"]), "capabilities": sorted(item["capabilities"]), "callbacks": sorted(item["callbacks"]), "areas": sorted(item["areas"])} for key, item in sorted(classes.items())}}
	gaps = {stage: entry for stage, entry in summary.items() if entry.get("unexported_records")}
	class_rows = {key: {"records": value["records"], "exported": value["exported"], "stages": sorted(value["stages"])} for key, value in sorted(class_totals.items(), key=lambda pair: pair[1]["records"] - pair[1]["exported"], reverse=True)}
	result = {"source": "native_actor_lists (SLES 0x8003D3F8 caller scan of each STxxT overlay); exports matched on the 20-byte record", "stages": summary, "class_totals": class_rows}
	write_output(docs_dir / "actor_coverage.json", json.dumps(result, indent=1) + "\n", encoding="utf-8")
	lines = ["# Actor coverage", "", "Generated by `export_actor_coverage` in `tools/world.py` (`python tools/assets.py --only world --overwrite-only \"docs/actor_coverage.*\"`). Records come from each overlay's standard 20-byte actor list; a record counts as exported when its bytes appear in `npcs.json`, `scripted_actors.json`, `pickups.json`, `mine_actors.json` or the static prop manifest, or as a door or procedural weather record. `docs/actor_coverage.json` holds the per-class detail (sources, capabilities such as talk/movement/enemy, callback addresses).", "", "Record kinds: `actor` = type 0x20 mesh actors (NPCs, enemies); `prop` = 0x60/0x61; `door` = 0xA1; `controller_e0` = 0xE0; `object_a0` = 0xA0. Category `room_only` = nothing but area headers and doors; `props_only` = props and controllers without type 0x20 actors.", "", "| Stage | Name | Areas | Category | Exported | Not exported | Scripted actors | Talk sites bound/found | Export files | Bindings |", "| --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |"]
	for stage, entry in summary.items(): lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (stage, entry["name"], entry.get("areas", ""), entry.get("category", entry["status"]), entry.get("exported_records", ""), entry.get("unexported_records", ""), ("%d (talk %d, move %d, unported paths %d)" % (entry["scripted"]["instances"], entry["scripted"]["capabilities"].get("talk", 0), entry["scripted"]["capabilities"].get("movement", 0), entry["scripted"]["unported_script_paths"])) if entry.get("scripted") else "-", ("%d/%d" % (sum(site["bound"] for site in entry["talk_sites"]), len(entry["talk_sites"]))) if entry.get("talk_sites") else "-", ", ".join(entry.get("export_files", [])) or "-", ", ".join("%s %s" % pair for pair in entry.get("bindings", {}).items()) or "-"))
	lines += ["", "## Record classes by unexported count", "", "| Record (type/class/variant) | Role | Records | Exported | Stages |", "| --- | --- | ---: | ---: | --- |"]
	for key, row in list(class_rows.items())[:40]:
		if row["records"] != row["exported"]: lines.append("| %s | %s | %d | %d | %s |" % (key, ACTOR_CLASS_ROLES.get("/".join(key.split("/")[:2]), "-"), row["records"], row["exported"], ", ".join(row["stages"])))
	lines += ["", "## Unexported records per stage", "", "| Stage | Record | Class callback | Count | Areas | Capabilities in exports |", "| --- | --- | --- | ---: | --- | --- |"]
	for stage, entry in gaps.items():
		for key, item in entry["classes"].items():
			if item["records"] > item["exported"]: lines.append("| %s | %s%s | %s | %d | %s | %s |" % (stage, key, " (model unresolved)" if item.get("unresolved_model") else "", item.get("class_callback") or "-", item["records"] - item["exported"], ",".join(map(str, item["areas"])), ",".join(item["capabilities"]) or "-"))
	lines += ["", "## Notes", "", "- Type 0x20 actors and 0x60 props share the class callback table the overlay init installs (the table slot for class 21 points at the cell holding the class update function; `class_callback` in the tables above). The update function dispatches `actor+8` through a state table whose entry 0 is the constructor.", "- The constructor selects the model with SLES 0x8003DFC8 using a key byte (`actor+6` for class 0, `actor+7` for class 97) or SLES 0x8003DFA4 (key 0, e.g. chests); `actor_resource_keys` reads that from the constructor.", "- Types 0xE0, 0xA0 and 0x40 are 32-byte pool records (SLES 0x8003E9D8, 0x8003EB7C) without a class callback; GAME 0x800DA1F8 and 0x800DB4A4 only stream-despawn them with per-stage bitmaps. What each E0 class encodes is still untraced.", "- Class 25 type-0x60 props at route contact positions are the lift pads (ST0F is ported; other dungeons use the same pad/route pairing).", "", "## Easter eggs and secrets found so far", "", "- ST09 kickable can (class 0x4A, hit handler 0x800EE24C) and duck (class 0x4B, hit handler 0x800EEE98): kicking them is ported; message ST09:100 pays 200 zenny and earns the matching achievement.", "- ST2B/ST3B class-8 type-0x60 props: proximity message triggers (`lb a3,0xF(actor)` index, flag from the record) with request calls at ST2B 0x800ED5C0 and ST3B 0x800F2ECC; not ported."]
	write_output(docs_dir / "actor_coverage.md", "\n".join(lines) + "\n", encoding="utf-8")
	return {"stages": len(summary), "stages_with_gaps": len(gaps), "unexported_records": sum(entry.get("unexported_records", 0) for entry in summary.values())}

import cinematics
import ui

if __name__ == '__main__':
	import sys
	commands = {'maps': 'maps_cli', 'lighting': 'lighting_cli', 'minimap': 'minimap_cli', 'stage': 'stage_cli', 'room-layout': 'room_layout_cli', 'door-textures': 'door_textures_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
