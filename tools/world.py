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
ROOT = Path(__file__).resolve().parents[1]
UNIT = 1.0 / 256.0
COORDINATE_BASIS = {"native_to_godot": [-1, -1, 1], "unit": "1/256 map unit", "root_mirror_required": False, "winding": "reversed for reflected X basis"}
def png(width, height, pixels):
	def chunk(kind, data): return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
	rows = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))
	return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
def textures(path):
	source = path.read_bytes(); vram = bytearray(1024 * 512 * 2); loaded = 0
	for offset in range(0, len(source) - 47, 0x400):
		type_id, size = struct.unpack_from("<2I", source, offset)
		if type_id not in (2, 3): continue
		px, py, colors, palettes, ix, iy, width, height = struct.unpack_from("<8H", source, offset + 12)
		if size != colors * palettes * 2 + width * height * 2 or not 0 < size <= 1024 * 512 * 2: continue
		if px + colors > 1024 or py + palettes > 512 or ix + width > 1024 or iy + height > 512: continue
		if type_id == 3:
			bits = read_u16(source, offset + 36)
			if not bits or bits & 3: continue
			data, _ = decompress_section(source, offset, 36)
		else: data = source[offset + 48:offset + 48 + size]
		if len(data) != size: raise ValueError(f"truncated texture at {offset:#x}")
		cursor = 0
		for y in range(palettes):
			n = colors * 2; destination = ((py + y) * 1024 + px) * 2; vram[destination:destination + n] = data[cursor:cursor + n]; cursor += n
		for y in range(height):
			n = width * 2; destination = ((iy + y) * 1024 + ix) * 2; vram[destination:destination + n] = data[cursor:cursor + n]; cursor += n
		loaded += 1
	if not loaded: raise ValueError("no texture sections decoded")
	return vram, loaded
def texture_page(vram, clut, tpage):
	x = (tpage & 15) * 64; y = ((tpage >> 4) & 1) * 256; depth = (tpage >> 7) & 3; px = (clut & 63) * 16; py = clut >> 6
	if depth > 2: raise ValueError(f"unsupported texture depth {depth}")
	pixels = bytearray()
	for v in range(256):
		for u in range(256):
			if depth < 2:
				shift = 2 if depth == 0 else 1; bits = 4 if depth == 0 else 8; word = read_u16(vram, ((y + v) * 1024 + x + (u >> shift)) * 2); index = (word >> ((u & ((1 << shift) - 1)) * bits)) & ((1 << bits) - 1); color = read_u16(vram, (py * 1024 + px + index) * 2)
			else: color = read_u16(vram, ((y + v) * 1024 + x + u) * 2)
			pixels.extend((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 0 if color == 0 else 255))
	return png(256, 256, pixels)
class Stage:
	def __init__(self, source):
		self.data, _ = decompress_section(source, 0); b = self.data; self.base = read_u32(b, 0) * 4; self.placement_base = read_u32(b, 4) * 4; count = read_u32(b, 8)
		if not 3 <= count <= 256 or not count * 4 <= self.base < self.placement_base <= len(b): raise ValueError("invalid stage section table")
		self.grids = [count * 4] + [read_u32(b, i * 4) * 4 for i in range(3, count)]; self.directories = [struct.unpack_from("<3I", b, self.base + 4 + i * 12) for i in range(read_u32(b, self.base))]
		self.placement_count, self.scripted_count = struct.unpack_from("<2H", b, self.placement_base); self.placements = [struct.unpack_from("<HBBHBB", b, self.placement_base + 4 + i * 8) for i in range(self.placement_count)]; self.cache = {}
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
		materials = [struct.unpack_from("<2H", b, start + 4 + i * 4) for i in range(material_count)]; groups = defaultdict(list)
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
				groups[(materials[material], bool(flag & 32), flag & 3)].append((coordinates, [(texcoords[i * 2] + 0.5, texcoords[i * 2 + 1] + 0.5) for i in range(4)], brightness)); previous = points
			if remaining: raise ValueError(f"model {pointer:#x} ends inside a quad strip")
		self.cache[pointer] = groups
		return groups
def terrain_binding(path, area):
	data = path.read_bytes(); base = read_u32(data, 12); end = min(len(data), 48 + read_u32(data, 4)); opcode = 0x0c000000 | ((0x80026810 >> 2) & 0x3ffffff)
	calls = [offset for offset in range(48, end - 3, 4) if read_u32(data, offset) == opcode]
	if len(calls) != 1: raise ValueError(f"{path.name} has {len(calls)} native terrain setup calls")
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
	if address is None or not 48 <= address - base + 48 <= end - 128: raise ValueError(f"{path.name} terrain UV pointer is unresolved")
	position = address - base + 48
	return {"source_call": hex(base + call - 48), "uv_pointer": hex(address), "uv_words": list(struct.unpack_from("<32I", data, position)), "native_renderer": "SLES0x80027E84 selects terrain when cell&0x4000; UV0x80028534; TPAGE0x80026EB8; CLUT0x80028950"}
def terrain_groups(tiles, binding, placements):
	groups = defaultdict(list)
	seen = set()
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
		if page not in self.pages:
			clut, tpage = page
			if page not in self.texture_cache: self.texture_cache[page] = texture_page(self.vram, clut, tpage)
			image = len(self.document["images"]); self.document["images"].append({"bufferView": self.buffer(self.texture_cache[page]), "mimeType": "image/png"}); texture = len(self.document["textures"]); self.document["textures"].append({"sampler": 0, "source": image}); self.pages[page] = texture
		index = len(self.document["materials"]); self.document["materials"].append({"name": f"clut_{page[0]:04x}_page_{page[1]:04x}", "pbrMetallicRoughness": {"baseColorTexture": {"index": self.pages[page]}, "metallicFactor": 0, "roughnessFactor": 1}, "alphaMode": "MASK", "alphaCutoff": 0.01, "doubleSided": two_sided, "extensions": {"KHR_materials_unlit": {}}, "extras": {"psx_blend": blend}}); self.materials[key] = index
		return index
	def mesh(self, pointer, groups):
		if pointer in self.meshes: return self.meshes[pointer]
		primitives = []
		for key, faces in groups.items():
			positions = []; uvs = []; colors = []
			for coordinates, texcoords, brightness in faces:
				for i in (0, 2, 1, 1, 2, 3): positions.extend(coordinates[i]); uvs.extend(v / 256 for v in texcoords[i]); colors.extend([brightness[i] / 255] * 3 + [1])
			primitives.append({"attributes": {"POSITION": self.accessor(positions, 3, True), "TEXCOORD_0": self.accessor(uvs, 2), "COLOR_0": self.accessor(colors, 4)}, "material": self.material(key), "mode": 4})
		index = len(self.document["meshes"]); self.document["meshes"].append({"name": f"map_mesh_{pointer:04x}", "primitives": primitives}); self.meshes[pointer] = index
		return index
	def instance(self, name, pointer, groups, translation):
		mesh = self.mesh(pointer, groups); index = len(self.document["nodes"]); self.document["nodes"].append({"name": name, "mesh": mesh, "translation": translation}); self.document["scenes"][0]["nodes"].append(index)
		for faces in groups.values():
			for points, _, _ in faces: self.bounds.extend(tuple(p[k] + translation[k] for k in range(3)) for p in points)
	def save(self, path):
		self.binary.extend(b"\0" * (-len(self.binary) % 4)); self.document["buffers"][0]["byteLength"] = len(self.binary); text = json.dumps(self.document, separators=(",", ":")).encode(); text += b" " * (-len(text) % 4); size = 12 + 8 + len(text) + 8 + len(self.binary); path.write_bytes(struct.pack("<3I", 0x46546c67, 2, size) + struct.pack("<2I", len(text), 0x4e4f534a) + text + struct.pack("<2I", len(self.binary), 0x004e4942) + self.binary)
		return {"min": [min(p[k] for p in self.bounds) for k in range(3)], "max": [max(p[k] for p in self.bounds) for k in range(3)]}
def export_maps(stage_name, input_dir, output_dir):
	source = (input_dir / f"{stage_name}.BIN").read_bytes(); stage = Stage(source); texture_path = input_dir / f"{stage_name}T.BIN"; vram, texture_count = textures(texture_path); destination = output_dir / stage_name; destination.mkdir(parents=True, exist_ok=True); areas = []
	texture_cache = {}
	for index in range(len(stage.grids)):
		area = stage.area(index)
		if area is None: continue
		tiles, ids = area; glb = Glb(vram, texture_cache); quads = 0
		ground = terrain_groups(tiles, terrain_binding(texture_path, index), stage.placements) if any(read_u16(tile, 0) != 0xffff and read_u16(tile, 0) & 0x8000 and (read_u16(tile, 0) & 0x4000 or stage.placements[read_u16(tile, 0) & 0x7ff][3] & 0x8000) for tile in tiles.values()) else {}
		if ground: glb.instance("terrain", -1, ground, [0, 0, 0]); quads += sum(len(faces) for faces in ground.values())
		if not ids and not ground: continue
		for placement_id in ids:
			state, model_id, flags, height, x, z = stage.placements[placement_id]; a, h, directory = stage.directories[model_id]; variant = flags & 3; variants = ((h >> 24) & 1) + 1
			if variant >= variants: raise ValueError(f"placement {placement_id} selects invalid variant {variant}")
			pointer = read_u16(stage.data, stage.base + (directory & 65535) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [-((x << 9) - (0x7e00 if h & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if h & 0x20000000 else 0x7f00)) * UNIT]; glb.instance(f"placement_{placement_id:03d}_model_{model_id:03d}", pointer, groups, translation); quads += sum(len(f) for f in groups.values())
		name = f"area_{index:02d}.glb"; bounds = glb.save(destination / name); areas.append({"index": index, "file": name, "placements": len(ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds}); print(f"{stage_name}/{name}: {len(ids)} placements, {quads} quads, {len(glb.pages)} texture pages")
	manifest = {"stage": stage_name, "coordinate_basis": COORDINATE_BASIS, "source_sha256": hashlib.sha256(source).hexdigest(), "textures_sha256": hashlib.sha256(texture_path.read_bytes()).hexdigest(), "texture_sections": texture_count, "areas": areas}; (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest
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

def map_depth_cue_info(overlay_data, exe_code, exe_load, area_count):
	base = struct.unpack_from("<I", overlay_data, 0xC)[0]; table = 0x801005E0; signatures = {0x800E72E8: 0x3C068010, 0x800E72F4: 0x24C605E0, 0x800E7304: 0x0C009A04}
	if any(struct.unpack_from("<I", overlay_data, pc - base + 0x30)[0] != word for pc, word in signatures.items()): raise ValueError("ST0F map configuration binding differs from the native source")
	if instruction_at(exe_code, exe_load, 0x8002B750) != 0x4A780010 or instruction_at(exe_code, exe_load, 0x800264FC) != 0x4A780010: raise ValueError("Native depth-cue instructions differ from the source trace")
	callbacks = [instruction_at(exe_code, exe_load, 0x80078B7C + index * 4) for index in range(8)]; parameters = []
	for area in range(area_count):
		address = table + area * 36; offset = address - base + 0x30; raw = overlay_data[offset:offset + 36]
		if len(raw) != 36: raise ValueError("Truncated native map configuration")
		mode = raw[7] & 3; fog_near = struct.unpack_from("<H", raw, 4)[0]
		parameters.append({"area": area, "source_ram": hex(address), "source_file_offset": hex(offset), "raw_hex": raw.hex(), "enabled": bool(mode & 1), "mode": mode, "flags": raw[7], "far_rgb": list(raw[:3]), "depth_shift": raw[3], "native_units_per_world": 256, "ir0_scale": 4096, "sz_max": 65535, "map_callback": hex(callbacks[mode]), "placement_callback": hex(callbacks[mode + 4]), "noise_range": struct.unpack_from("<H", raw, 0x18)[0], "noise_offset_step": [value - 256 if value & 128 else value for value in raw[0x1A:0x1C]], "rational_setup": {"fog_near_raw": fog_near, "reference_h": 384, "dqa": int(-fog_near * 320 / 384), "dqb": 0x01400000, "used_for_map_corners": False}})
	return {"area_selector": "0x8009C7E8+0x11", "config_loader": "ST0FT0x800E72C0..0x800E7308 -> SLES0x80026810", "record_table": hex(table), "record_stride": 36, "map_dispatch": "SLES0x80026EA0..0x80026EC4 indexes 0x80078B7C by config.flags&3", "placement_dispatch": "SLES0x8002707C..0x800270B4 indexes 0x80078B8C by config.flags&3", "far_color_loader": "SLES0x8005F6F4 writes configRGB<<4 to GTE control21/22/23", "map_corner_source": "SLES0x8002B728..0x8002B754 and0x8002C210..0x8002C23C write vertexSZ>>depth_shift into IR0 before DPCS", "pbd_corner_source": "SLES0x800260C4..0x80026100 and0x800264D4..0x80026510 depth-cue the already tinted activeRGB buffer", "pbd_enable_guard": "config.flags&1 !=0 and actor.byte0&0x20 ==0; SLES0x80024BA4..0x80024BF4 and0x80025B00..0x80025B44", "formula": {"sz": "clamp(floor(camera_view_depth*256),0,65535)", "ir0": "unsigned16(SZ>>depth_shift)", "rgb": "clamp((activeRGB*(4096-ir0)+farRGB*ir0)>>12,0,255)", "interpolation": "Per-corner RGB is depth-cued before texture modulation and Gouraud interpolation; DQA/DQB do not supply IR0 in this path", "black_far_color": "For farRGB=0, effective depth-cue factor saturates at1 when IR0>=4096"}, "area_parameters": parameters}
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
	OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True); OUTPUT_PATH.write_text(json.dumps(lighting, indent=2) + "\n", encoding="utf-8"); print(f"Wrote {OUTPUT_PATH}: {len(areas)} areas, ST0FT CTC2 registers {overlay['ctc2_control_registers_written']}")

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
	output_dir.mkdir(parents=True, exist_ok=True); atlas_path = output_dir / "tiles.png"; atlas_path.write_bytes(atlas)
	manifest = {"stage": "ST0F", "atlas": "tiles.png", "atlas_size": [256, 256], "atlas_clut": ATLAS_CLUT, "atlas_tpage": ATLAS_TPAGE, "atlas_alpha": "zero palette word transparent; STP bit alpha 128; other nonzero palette words opaque", "atlas_sha256": sha256(atlas), "source": {"root_file": "build/maps/ST0F_map.bin", "root_type": 13, "root_sha256": sha256(root), "root_grid_table_index": ROOT_GRID_POINTER, "root_grid_base": ROOT_GRID_BASE, "root_grid_end": previous_end, "layout_file": "build/disc-assets/DAT/ST0FT.BIN", "layout_sha256": sha256(stage_texture), "area_pointer_offset": AREA_POINTER_OFFSET, "area_layout_offset": AREA_LAYOUT_OFFSET, "texture_sections": texture_count, "arrow_code_file": "build/disc-assets/COMMON/GAME.BIN", "arrow_code_address": "0x800BB5B0", "arrow_call_site": "ST0FT 0x800FCD1C"}, "draw": {"gpu_opcode": "0x7E", "texture_blend_mode": "average", "tile_pixels": 16, "tile_uv_pixels": {"u": "(tile_id & 0x0f) * 16", "v": "tile_id & 0xf0"}, "skip_tile_ids": [255, 92, 93, 94, 95], "visited_rgb": [128, 128, 128], "unvisited_small_area_rgb": [48, 48, 48], "unvisited_area_threshold": 5, "small_area_rule": "areas with index below threshold draw undiscovered tiles dark; larger areas omit undiscovered tiles", "native_clip": {"x": 12, "y": 24, "width": 72, "height": 72}, "map_center_pixels": [0, 0], "tile_origin_pixels": {"x": "-8 * area.width + 16 * column", "y": "8 * area.height - 16 - 16 * row"}, "player_position_source_offsets": {"x": "player+0x12 (signed16)", "z": "player+0x1A (signed16)"}, "player_scroll_pixels": {"x": "signed16(player_x) >> 6", "y": "-(signed16(player_z) >> 6)"}, "tile_draw_base_pixels": {"x": "anchor_x + 36 - scroll_x", "y": "framebuffer_y + 60 - scroll_y", "anchor_x": 12, "framebuffer_y": 0}, "player_marker_pixels": {"x": "(signed16(player_x) >> 6) - center_x", "y": "center_z - (signed16(player_z) >> 6)"}, "player_arrow": {"callback_call_site": "ST0FT 0x800FCD1C", "draw_address": "COMMON/GAME.BIN 0x800BB5B0", "gpu_opcodes": ["0x30", "0x4C"], "heading_delta": "signed16(player+0xF2) - signed16(player+0x2A)", "heading_field_meanings": "unknown", "draw_style": "Gouraud triangle plus closed polyline", "angle_zero_triangle": [[0, 6], [-3, -5], [3, -5]], "cardinal_tip_by_angle": {"0": [0, 6], "1024": [6, 0], "2048": [0, -6], "3072": [-6, 0]}}, "area_extra_fields_used_by_minimap_callback": False}, "areas": areas}
	manifest_path = output_dir / "manifest.json"; manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	print(f"ST0F minimap: {len(areas)} areas, {sum(area['width'] * area['height'] for area in areas)} cells, {texture_count} texture sections -> {output_dir}")
	return manifest

def minimap_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--maps-dir", type=Path, default=Path("build/maps")); parser.add_argument("--output-dir", type=Path, default=Path("assets/minimap/ST0F")); args = parser.parse_args(); export_minimap(args.dat_dir, args.maps_dir, args.output_dir)

def export_floor_shapes(path):
	stage = Stage(Path(path).read_bytes()); result = {}
	for area in range(len(stage.grids)):
		parsed = stage.area(area)
		if parsed is None: continue
		tiles, placements = parsed; boxes = []
		for placement in placements:
			_, model, flags, height, x, z = stage.placements[placement]; _, header, directory = stage.directories[model]; variant = stage.base + (directory & 65535) * 4 + (flags & 3) * 12; pointer = struct.unpack_from("<H", stage.data, variant + 2)[0] * 4 + stage.base; count = stage.data[variant + 6]; offset_x = (x << 9) - (0x7E00 if header & 0x10000000 else 0x7F00); offset_z = (z << 9) - (0x7E00 if header & 0x20000000 else 0x7F00); offset_y = 0x400 - tiles[(x, z)][6] * 16 - ((height & 0x7F00) >> 4)
			for index in range(count):
				offset = pointer + index * 16; values = struct.unpack_from("<6h2H", stage.data, offset)
				boxes.append({"x": [values[0] + offset_x, values[1] + offset_x], "z": [values[2] + offset_z, values[3] + offset_z], "y": [values[4] + offset_y, values[5] + offset_y], "kind": values[6], "mask": values[7], "placement": placement, "source_offset": hex(offset)})
		result[str(area)] = {"grid": {"%d:%d" % coordinates: list(data) for coordinates, data in tiles.items()}, "boxes": boxes, "source": "SLES0x80038D20 placement collision directory; GAME0x800B13FC floor selector; GAME0x800B5658 shape0 footprint"}
	return result

REFERENCE = "https://dwn009.fandom.com/wiki/Mega_Man_Legends_2/Locations"
LOCATIONS = (("ST04", 0, "Flutter Bridge"), ("ST04", 1, "Flutter Deck 1"), ("ST04", 2, "Flutter Lab"), ("ST05", 0, "Flutter MegaMan's Room"), ("ST05", 1, "Flutter Roll's Room"), ("ST05", 2, "Flutter Barrell's Room"), ("ST06", 0, "Flutter Deck 2"), ("ST06", 1, "Flutter Toilet"), ("ST06", 2, "Flutter Storage"), ("ST06", 3, "Flutter Living Room"), ("ST06", 4, "Flutter Kitchen"), ("ST06", 5, "Flutter Bathroom"), ("ST07", 0, "Flutter Deck 3"), ("ST07", 1, "Flutter Hangar"), ("ST07", 2, "Flutter Engine Room"))
STAGE_BINDINGS = {"ST04": {"name": "Flutter", "area_count": 3, "routes": 0x800EFB94, "actors": 0x800EFA48, "actor_caller": "0x800E7570", "actor_section": 0x6800, "roles": {71: "bridge_steering_wheel"}, "controllers": {71: "ST04T0x800E9C98 reads actor+C/D and continues3F768; callback-to-class47 binding still unresolved"}}, "ST05": {"name": "Flutter", "area_count": 3, "routes": 0x800E9B04, "actors": 0x800E9A30, "actor_caller": "0x800E71E4", "actor_section": 0x6800}, "ST06": {"name": "Flutter", "area_count": 6, "routes": 0x800E8D10, "actors": 0x800E8B04, "actor_caller": "0x800E71B4", "actor_section": 0x6800}, "ST07": {"name": "Flutter", "area_count": 3, "routes": 0x800E88CC, "actors": 0x800E87B0, "actor_caller": "0x800E71B4", "actor_section": 0x6800}}
STAGE_BINDINGS["ST08"] = {"area_count": 2, "routes": 0x800F200C, "actors": 0x800F1F20, "actor_caller": "0x800E74BC", "actor_section": 0x8800}
BASE = 0x800E7000
SHARED_TEXTURES = ("COMMON/PL00T.BIN",)

def digest(data): return hashlib.sha256(data).hexdigest()
def texture_uploads(source, vram, name):
	uploads = []
	for offset in range(0, len(source) - 47, 0x400):
		kind, size = struct.unpack_from("<2I", source, offset)
		if kind not in (2, 3): continue
		px, py, colors, palettes, x, y, width, height = struct.unpack_from("<8H", source, offset + 12); expected = colors * palettes * 2 + width * height * 2
		if not expected or size not in (expected, expected + 0x7D0) or px + colors > 1024 or py + palettes > 512 or x + width > 1024 or y + height > 512: continue
		if kind == 3:
			bits = read_u16(source, offset + 36)
			if not bits or bits & 3: continue
			data, _ = decompress_section(source, offset, 36)
		else: start = offset + (0x800 if size == expected + 0x7D0 else 0x30); data = source[start:start + expected]
		if len(data) != expected: raise ValueError(f"{name} texture upload at{offset:#x} is truncated")
		cursor = 0
		for row in range(palettes):
			start = ((py + row) * 1024 + px) * 2; count = colors * 2; vram[start:start + count] = data[cursor:cursor + count]; cursor += count
		for row in range(height):
			start = ((y + row) * 1024 + x) * 2; count = width * 2; vram[start:start + count] = data[cursor:cursor + count]; cursor += count
		uploads.append({"file": name, "section_offset": hex(offset), "section_type": kind, "palette_rect": [px, py, colors, palettes], "image_rect": [x, y, width, height]})
	return uploads

def export_texture_library(source_dir, output_dir):
	source_dir = Path(source_dir); output_dir = Path(output_dir); result = []
	for path in sorted(source_dir.rglob("*.BIN")):
		data = path.read_bytes(); entries = []
		for offset in range(0, len(data) - 47, 0x400):
			kind, size = struct.unpack_from("<2I", data, offset)
			if kind not in (2, 3): continue
			px, py, colors, palettes, x, y, width, height = struct.unpack_from("<8H", data, offset + 12); expected = colors * palettes * 2 + width * height * 2
			if not expected or size not in (expected, expected + 0x7d0) or px + colors > 1024 or py + palettes > 512 or x + width > 1024 or y + height > 512: continue
			directory = output_dir / path.parent.name.lower() / path.stem; directory.mkdir(parents=True, exist_ok=True); entry = {"source": path.relative_to(source_dir).as_posix(), "offset": offset, "type": kind, "palette_rect": [px, py, colors, palettes], "image_rect": [x, y, width, height]}
			try:
				if kind == 3: payload, _ = decompress_section(data, offset, 36)
				else: start = offset + (0x800 if size == expected + 0x7d0 else 48); payload = data[start:start + expected]
				if len(payload) != expected: raise ValueError("Truncated texture upload")
				name = "upload_%05X.bin" % offset; (directory / name).write_bytes(payload); entry.update(status="exported", file=name, sha256=hashlib.sha256(payload).hexdigest(), packing="Native palette words followed by packed VRAM image words")
				if colors and palettes:
					pixels = bytearray()
					for index in range(colors * palettes):
						word = read_u16(payload, index * 2); pixels.extend(((word & 31) * 255 // 31, ((word >> 5) & 31) * 255 // 31, ((word >> 10) & 31) * 255 // 31, 0 if word == 0 else 128 if word & 0x8000 else 255))
					name = "palette_%05X.png" % offset; (directory / name).write_bytes(png(colors, palettes, pixels)); entry["palette_file"] = name
			except (ValueError, IndexError, struct.error) as error: entry.update(status="unsupported", error=str(error))
			entries.append(entry)
		if entries: (directory / "manifest.json").write_text(json.dumps({"textures": entries}, indent=2), encoding="utf-8"); result.extend(entries)
	return result
def export_geometry(input_dir, output_dir, stages):
	output_dir.mkdir(parents=True, exist_ok=True); catalog = []
	for stage_name in stages:
		root_path = input_dir / f"{stage_name}.BIN"; texture_path = input_dir / f"{stage_name}T.BIN"; root_bytes = root_path.read_bytes(); texture_bytes = texture_path.read_bytes(); stage = Stage(root_bytes); vram, texture_count = textures(texture_path); stage_dir = output_dir / stage_name; stage_dir.mkdir(parents=True, exist_ok=True); areas = []
		texture_cache = {}
		for area_index in range(len(stage.grids)):
			display_name = next((item[2] for item in LOCATIONS if item[0] == stage_name and item[1] == area_index), None); family = STAGE_BINDINGS.get(stage_name, {}).get("name")
			if area_index >= len(stage.grids): raise ValueError(f"{stage_name} has no native area {area_index:02d}")
			area = stage.area(area_index)
			if area is None: continue
			tiles, placement_ids = area; glb = Glb(vram, texture_cache); quads = 0
			ground_binding = terrain_binding(texture_path, area_index) if any(read_u16(tile, 0) != 0xffff and read_u16(tile, 0) & 0x8000 and (read_u16(tile, 0) & 0x4000 or stage.placements[read_u16(tile, 0) & 0x7ff][3] & 0x8000) for tile in tiles.values()) else None
			ground = terrain_groups(tiles, ground_binding, stage.placements) if ground_binding else {}
			if ground: glb.instance("terrain", -1, ground, [0, 0, 0]); quads += sum(len(faces) for faces in ground.values())
			if not placement_ids and not ground: continue
			for placement_id in placement_ids:
				_, model_id, flags, height, x, z = stage.placements[placement_id]; _, header, directory = stage.directories[model_id]; variant = flags & 3; variant_count = ((header >> 24) & 1) + 1
				if variant >= variant_count: raise ValueError(f"{stage_name} area {area_index:02d} placement {placement_id} selects invalid variant {variant}")
				pointer = read_u16(stage.data, stage.base + (directory & 0xffff) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [-((x << 9) - (0x7e00 if header & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if header & 0x20000000 else 0x7f00)) * UNIT]; glb.instance(f"placement_{placement_id:03d}_model_{model_id:03d}", pointer, groups, translation); quads += sum(len(faces) for faces in groups.values())
			file_name = f"area_{area_index:02d}.glb"; bounds = glb.save(stage_dir / file_name); areas.append({"index": area_index, "name": display_name.removeprefix(family + " ") if display_name and family else display_name or "Area %02d" % area_index, "file": file_name, "placements": len(placement_ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds, "native_map_code": {"stage": int(stage_name[2:], 16), "area": area_index}, "terrain_source": ground_binding}); print(f"{stage_name}_{area_index:02d}: {len(placement_ids)} placements, {quads} quads")
		stage_manifest = {"stage": stage_name, "name": STAGE_BINDINGS.get(stage_name, {}).get("name") or stage_name, "source_reference": {"description": "native stage/substage values XX/YY and room labels", "url": REFERENCE} if stage_name in STAGE_BINDINGS else None, "coordinate_unit": "1/256 map unit", "coordinate_basis": COORDINATE_BASIS, "source": {"root_file": f"DAT/{stage_name}.BIN", "textures_file": f"DAT/{stage_name}T.BIN", "root_sha256": digest(root_bytes), "textures_sha256": digest(texture_bytes), "texture_sections": texture_count}, "areas": areas}; (stage_dir / "manifest.json").write_text(json.dumps(stage_manifest, indent=2) + "\n", encoding="utf-8"); catalog.append({"stage": stage_name, "name": stage_manifest["name"], "manifest": "res://" + (stage_dir / "manifest.json").resolve().relative_to(ROOT).as_posix(), "area_names": [area["name"] for area in areas]})
	catalog_path = output_dir.parent / "locations" / "manifest.json"; catalog_path.parent.mkdir(parents=True, exist_ok=True); existing = json.loads(catalog_path.read_text()).get("locations", []) if catalog_path.exists() else []; entries = {item["stage"]: item for item in existing}; entries.update({item["stage"]: item for item in catalog})
	for entry in entries.values():
		manifest = json.loads((ROOT / entry["manifest"].removeprefix("res://")).read_text()); entry["areas"] = [{"index": int(area["index"]), "name": str(area.get("name", "Area %02d" % area["index"]))} for area in manifest["areas"]]; entry.pop("area_names", None)
	catalog_manifest = {"locations": [entries[key] for key in sorted(entries)], "source_reference": REFERENCE}; catalog_path.write_text(json.dumps(catalog_manifest, indent=2) + "\n", encoding="utf-8"); return catalog_manifest

def export_routes(dat_dir, output_dir, stages):
	result = {}; manifests = {}
	for stage in stages:
		binding = STAGE_BINDINGS.get(stage); routes = []; data = (dat_dir / (stage + "T.BIN")).read_bytes()
		if binding:
			for area in range(binding["area_count"]):
				pointer = struct.unpack_from("<I", data, 0x30 + binding["routes"] - BASE + area * 4)[0]; offset = 0x30 + pointer - BASE; index = 0
				while data[offset] != 255:
					raw = data[offset:offset + 24]
					if len(raw) != 24: raise ValueError(f"{stage} area {area} has a truncated native route")
					sx, sy, sz, yaw, dx, dy, dz, arrival_yaw = struct.unpack_from("<hhhHhhhH", raw, 8); routes.append({"source_area": area, "destination_stage": f"ST{raw[6]:02X}", "destination_area": raw[7], "door_id": raw[0], "door_slot": raw[1], "door_mode": raw[2], "record_index": index, "file_offset": offset, "source_transform_raw": [sx, sy, sz, yaw], "source_transform": {"position": [sx / 256, sy / 256, sz / 256], "yaw_raw": yaw}, "destination_transform_raw": [dx, dy, dz, arrival_yaw], "destination_transform": {"position": [dx / 256, dy / 256, dz / 256], "yaw_raw": arrival_yaw, "floor_height": dy == -1}, "lock_event": 0x710 + (raw[0] & 31), "transition_event": 0x730 + (raw[0] & 31), "blocked_message": struct.unpack_from("<h", raw, 4)[0], "bytes_hex": raw.hex()}); offset += 24; index += 1
					if index > 64: raise ValueError(f"{stage} area {area} route list has no terminator")
		manifest = {"stage": stage, "binding_status": "bound" if binding else "unbound", "source": {"file": f"DAT/{stage}T.BIN", "sha256": digest(data), "area_route_pointer_ram": hex(binding["routes"]) if binding else None, "active_pointer_ram": "0x80078FA4", "record_stride": 24, "consumer": "GAME0x800B7B38-0x800B7E74", "lock_consumer": "GAME0x800B89B4", "transition_consumer": "GAME0x800B8A2C", "native_contact": "xyz matches collision contact0x800E0BCC; heading difference within[-0x200,0x200)", "runtime_interaction": "PC interaction requires a nearby door face and native heading; destinationY=-1 resolves room collision floor"}, "area_transitions": routes}; manifests[stage] = manifest; result[stage] = routes
	for stage, routes in result.items():
		for route in routes:
			other = result.get(route["destination_stage"])
			if other is not None and not any(candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"] for candidate in other): raise ValueError(f"{stage} door{route['door_id']} has no reciprocal native destination")
			if stage in STAGES and route["destination_stage"] not in STAGES and other is not None:
				reverse = next(candidate for candidate in other if candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"]); center, axis = route_center(route, reverse, True); _, faces = room_faces(output_dir, stage, route["source_area"]); route["source_panel"] = select_panel(faces, center, axis)
	for stage, manifest in manifests.items(): (output_dir / stage / "doors.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return result
def export_props(dat_dir, output_dir, stages):
	output_dir.mkdir(parents=True, exist_ok=True); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); target = output_dir / "manifest.json"; manifest = json.loads(target.read_text()) if target.exists() else {"stages": {}}
	for stage in stages:
		binding = STAGE_BINDINGS.get(stage); overlay_path = dat_dir / (stage + "T.BIN"); overlay = overlay_path.read_bytes(); source = (dat_dir / (stage + ".BIN")).read_bytes(); instances = []; models = {}; native_doors = []; section = None; uploads = []
		if binding:
			payload, section = decompress_section(source, binding["actor_section"]); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); normalized = work / (stage + "_models.bin"); normalized.write_bytes(header + payload); archive, payload = actor_archive(normalized); vram = bytearray(1024 * 512 * 2)
			for bank in SHARED_TEXTURES: uploads.extend(texture_uploads((dat_dir.parent / bank).read_bytes(), vram, bank))
			uploads.extend(texture_uploads(overlay, vram, "DAT/" + overlay_path.name)); uploads.extend(texture_uploads(source, vram, f"DAT/{stage}.BIN")); header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / (stage + "_vram.bin"); texture_path.write_bytes(header + vram)
			for area, pointer in enumerate(struct.unpack_from("<" + "I" * binding["area_count"], overlay, 0x30 + binding["actors"] - BASE)):
				for record in range(128):
					offset = 0x30 + pointer - BASE + record * 20; raw = overlay[offset:offset + 20]
					if len(raw) != 20: raise ValueError(f"{stage} native actor list is truncated")
					if raw[0] == 255: break
					if raw[2] not in (0x20, 0x60, 0x61): continue
					matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == raw[2] | raw[4] << 8 | raw[6] << 16]
					if len(matches) != 1: raise ValueError(f"{stage} source actor has no unique native PBD model")
					model = matches[0]; index = model["index"]
					if index not in models:
						path = output_dir / stage / f"model_{index:02d}.glb"; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_actor_model(payload, index, texture_path, path) if model["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, path, stage + ".BIN"); metadata["source_surfaces"] = record_source(path, stage + ".BIN", index, payload); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata
					x, y, z, yaw = struct.unpack_from("<3hH", raw, 12); instances.append({"area": area, "source_ram": hex(pointer + record * 20), "source_file_offset": hex(offset), "source_bytes": raw.hex(), "class": raw[4], "variant": raw[6], "model_index": index, "model_file": models[index]["model_file"], "position_raw": [x, y, z], "position": [-x / 256, -y / 256, z / 256], "yaw_raw": yaw, "yaw_turns": -yaw / 4096, "control": raw[8], "frame": raw[9], "role": binding.get("roles", {}).get(raw[4], "source_prop"), "native_control_source": "Native record bytes8/9; original PBD control table", "controller_candidate": binding.get("controllers", {}).get(raw[4])})
				else: raise ValueError(f"{stage} actor list has no native terminator")
			for model in archive["models"]:
				if model["flags"] & 0xFFFF != 0x161: continue
				index = model["index"]; path = output_dir / stage / f"model_{index:02d}.glb"; metadata = export_static_actor(payload, index, texture_path, path, stage + ".BIN"); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata; native_doors.append({"variant": (model["flags"] >> 16) & 255, "model_index": index, "model_file": metadata["model_file"], "native_scale_raw": metadata["native_scale_raw"], "source_flags": hex(model["flags"]), "resource_loader": "SLES0x8003DFC8", "constructor": "GAME0x800D1768"})
		for index, metadata in models.items(): metadata["model_index"] = index
		manifest["stages"][stage] = {"binding_status": "bound" if binding else "unbound", "source": {"archive": stage + ".BIN", "overlay": stage + "T.BIN", "sha256": digest(source), "decoded_section": section, "actor_pointer_table": hex(binding["actors"]) if binding else None, "caller": binding["actor_caller"] if binding else None, "consumer": "SLES0x8003D3F8", "texture_uploads": uploads, "coordinate_basis": "(-nativeX,-nativeY,+nativeZ)/256; room stream offset is separate"}, "models": list(models.values()), "native_doors": native_doors, "instances": instances}
	manifest["exterior"] = {"asset_source": "Original ST02 atmosphere assets", "effects_manifest": "res://assets/opening/effects/manifest.json", "native_effect_class": 18, "native_effect_variant": 3, "bank": "ST02", "parameter": 0x01000001, "source_renderer": "ST02T0x800EC0A4", "stage_native_selection": "Unbound; original atmosphere reuse is selected by the runtime"}; manifest["map_blending"] = {"source": "SLES0x8002FA14-0x8002FA44", "packed_status": "first vertex flag&3", "semi_enabled": "status!=0", "tpage": "baseTPAGE|((status-1)<<5) when semi enabled"}; temporary = target.with_suffix(".json.tmp"); temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); temporary.replace(target); return manifest
def export_stage(dat_dir=None, output_dir=None, stages=None):
	dat_dir = Path(dat_dir) if dat_dir else ROOT / "build/disc-assets/DAT"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/levels"; stages = sorted(set(stages or STAGE_BINDINGS))
	if any(len(stage) != 4 or not stage.startswith("ST") or any(character not in "0123456789ABCDEF" for character in stage[2:]) for stage in stages): raise ValueError("Stage names must be original STxx hexadecimal identifiers")
	catalog = export_geometry(dat_dir, output_dir, stages); export_routes(dat_dir, output_dir, stages); props = export_props(dat_dir, output_dir.parent / "stage_props", stages); catalog["props_manifest"] = "res://" + (output_dir.parent / "stage_props/manifest.json").resolve().relative_to(ROOT).as_posix(); catalog["bindings"] = {stage: props["stages"][stage]["binding_status"] for stage in stages}; return catalog
def stage_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--stage", action="append"); parser.add_argument("--dat-dir", type=Path); parser.add_argument("--output-dir", type=Path); args = parser.parse_args(); result = export_stage(args.dat_dir, args.output_dir, args.stage); print(json.dumps({"stage_bindings": result["bindings"], "props_manifest": result["props_manifest"]}))

STAGES = ("ST04", "ST05", "ST06", "ST07")
UNIT_BASIS = [-1, -1, 1]
LADDER_PAIRS = {frozenset((("ST04", 1), ("ST06", 0))), frozenset((("ST06", 0), ("ST07", 0)))}

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
		if not min(side) - 0.15 <= center[lateral] <= max(side) + 0.15 or max(vertical) < 0.3 or min(vertical) > 1.1: continue
		key = (face["node"], face["mesh_index"], face["primitive_index"], face["material_index"], round(plane, 3)); groups.setdefault(key, []).append(face)
	candidates = []
	for (node, mesh_index, primitive_index, material_index, plane), quads in groups.items():
		points = [point for face in quads for point in face["quad"]]; mins = [min(point[i] for point in points) for i in range(3)]; maxs = [max(point[i] for point in points) for i in range(3)]; width = maxs[lateral] - mins[lateral]; height = maxs[1] - mins[1]; side_center = (mins[lateral] + maxs[lateral]) * 0.5; score = abs(plane - center[axis]) + abs(side_center - center[lateral]) + abs(mins[1]) + abs(maxs[1] - 1.0) + 0.05 * abs(width - 0.625)
		candidates.append((score, node, mesh_index, primitive_index, material_index, plane, mins, maxs, quads))
	if not candidates: raise ValueError(f"no static panel face near route portal {center}")
	candidates.sort(key=lambda item: item[0]); best = candidates[0]; _, node, mesh_index, primitive_index, material_index, plane, mins, maxs, quads = best; selected_quads = list(quads); selected_signatures = {tuple(sorted(tuple(round(value * 65536) for value in point) for point in face["quad"])) for face in selected_quads}
	for face in faces:
		if face["node"] != node or face["mesh_index"] != mesh_index: continue
		points = face["quad"]; normal = [point[axis] for point in points]; side = [point[lateral] for point in points]; vertical = [point[1] for point in points]
		signature = tuple(sorted(tuple(round(value * 65536) for value in point) for point in points))
		if signature in selected_signatures or max(normal) - min(normal) > 0.002 or abs(sum(normal) / 4 - plane) > 0.002: continue
		if min(side) < mins[lateral] - 0.02 or max(side) > maxs[lateral] + 0.02: continue
		inside_panel = min(vertical) >= min(0.0, mins[1]) - 0.002 and max(vertical) <= max(1.0, maxs[1]) + 0.002
		bottom_strip = min(vertical) >= -0.01 and max(vertical) <= mins[1] + 0.002 and max(vertical) - min(vertical) <= 0.25
		if not inside_panel and not bottom_strip: continue
		selected_quads.append(face); selected_signatures.add(signature)
	selected_points = [point for face in selected_quads for point in face["quad"]]; bound_mins = [min(point[i] for point in selected_points) for i in range(3)]; bound_maxs = [max(point[i] for point in selected_points) for i in range(3)]; bounds = {"min": bound_mins, "max": bound_maxs}; face_center = [(bound_mins[i] + bound_maxs[i]) * 0.5 for i in range(3)]; match = re.fullmatch(r"placement_(\d+)_model_(\d+)", node)
	if not match: raise ValueError(f"unexpected map placement node {node}")
	return {"center": face_center, "axis": axis, "bounds": bounds, "placement_id": int(match.group(1)), "model_id": int(match.group(2)), "node": node, "mesh_index": mesh_index, "primitive_index": primitive_index, "material_index": material_index, "quads": [{"quad_index": face["quad_index"], "primitive_index": face["primitive_index"], "first_vertex": face["quad_index"] * 6, "first_triangle": face["quad_index"] * 2, "triangle_count": 2, "triangles_local": face["triangles_local"]} for face in selected_quads], "score": best[0]}

def export_room_layout(assets_dir, output_path):
	room_catalog = {}; route_data = {}; route_hashes = {}; external = []
	for stage in STAGES:
		manifest_path = assets_dir / stage / "manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8")); stage_areas = {area["index"]: area for area in manifest["areas"]}; route_path = assets_dir / stage / "doors.json"; route_file = json.loads(route_path.read_text(encoding="utf-8")); route_data[stage] = route_file["area_transitions"]; route_hashes[stage] = hashlib.sha256(route_path.read_bytes()).hexdigest()
		for index, area in stage_areas.items(): room_catalog[(stage, index)] = {"manifest": f"assets/levels/{stage}/manifest.json", "file": area["file"], "bounds": area["bounds"]}
	all_routes = [(stage, route) for stage, routes in route_data.items() for route in routes]; edges = []; ladder_transitions = []; paired = set()
	for stage, route in all_routes:
		a = (stage, route["source_area"]); b = (route["destination_stage"], route["destination_area"])
		if b[0] not in STAGES:
			external.append({"source_stage": stage, "source_area": a[1], "destination_stage": b[0], "destination_area": b[1], "door_id": route["door_id"], "source_transform_raw": route["source_transform_raw"], "destination_transform_raw": route["destination_transform_raw"], "file_offset": route["file_offset"]}); continue
		if (a, b) in paired or (b, a) in paired: continue
		reverses = [other for other in route_data[b[0]] if other["source_area"] == b[1] and other["destination_stage"] == a[0] and other["destination_area"] == a[1]]
		if len(reverses) != 1: raise ValueError(f"{a} to {b} has {len(reverses)} reciprocal routes")
		reverse = reverses[0]; paired.update(((a, b), (b, a)))
		if frozenset((a, b)) in LADDER_PAIRS:
			ladder_transitions.append({"source": {"stage": a[0], "area": a[1]}, "destination": {"stage": b[0], "area": b[1]}, "door_id": route["door_id"], "door_mode": route["door_mode"], "reverse_door_mode": reverse["door_mode"], "source_route_file_offset": route["file_offset"], "reverse_route_file_offset": reverse["file_offset"], "source_transform_raw": route["source_transform_raw"], "destination_transform_raw": route["destination_transform_raw"]}); continue
		center_a, axis_a = route_center(route, reverse, True); center_b, axis_b = route_center(route, reverse, False)
		if axis_a != axis_b: raise ValueError(f"{a} to {b} uses different local portal axes")
		path_a, faces_a = room_faces(assets_dir, *a); path_b, faces_b = room_faces(assets_dir, *b); face_a = select_panel(faces_a, center_a, axis_a); face_b = select_panel(faces_b, center_b, axis_b)
		if face_a["axis"] != face_b["axis"]: raise ValueError(f"{a} to {b} panel normal axes disagree")
		translation = tuple(face_a["center"][i] - face_b["center"][i] for i in range(3)); edges.append({"a": a, "b": b, "route": route, "reverse": reverse, "panel_a": face_a, "panel_b": face_b, "delta": translation, "glb_a": path_a, "glb_b": path_b})
	adjacency = {}
	for edge in edges:
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
	rooms = [{"stage": stage, "area": area, "manifest": data["manifest"], "file": data["file"], "world_offset": offsets[(stage, area)], "rotation_y": 0.0, "local_bounds": data["bounds"], "routes_remain_area_local": True} for (stage, area), data in sorted(room_catalog.items())]
	portals = []
	for edge in edges:
		a, b, pa, pb = edge["a"], edge["b"], edge["panel_a"], edge["panel_b"]; wa = [pa["center"][i] + offsets[a][i] for i in range(3)]; wb = [pb["center"][i] + offsets[b][i] for i in range(3)]; axis = pa["axis"]; lateral = 2 if axis == 0 else 0; size = [min(pa["bounds"]["max"][lateral] - pa["bounds"]["min"][lateral], pb["bounds"]["max"][lateral] - pb["bounds"]["min"][lateral]), min(pa["bounds"]["max"][1] - pa["bounds"]["min"][1], pb["bounds"]["max"][1] - pb["bounds"]["min"][1])]; center = [(wa[i] + wb[i]) * 0.5 for i in range(3)]; portal = {"source": {"stage": a[0], "area": a[1]}, "destination": {"stage": b[0], "area": b[1]}, "door_id": edge["route"]["door_id"], "door_mode": edge["route"]["door_mode"], "source_route_file_offset": edge["route"]["file_offset"], "reverse_route_file_offset": edge["reverse"]["file_offset"], "source_contact_raw": edge["route"]["source_transform_raw"], "source_slot": edge["route"]["door_slot"], "reverse_source_slot": edge["reverse"]["door_slot"], "source_yaw_raw": edge["route"]["source_transform_raw"][3], "reverse_source_contact_raw": edge["reverse"]["source_transform_raw"], "reverse_source_yaw_raw": edge["reverse"]["source_transform_raw"][3], "destination_contact_raw": edge["route"]["destination_transform_raw"], "source_panel": pa, "destination_panel": pb, "world_center": center, "normal_axis": "x" if axis == 0 else "z", "panel_center_error": max(abs(wa[i] - wb[i]) for i in range(3)), "shared_panel_size": size, "static_map_face": True}; portals.append(portal)
	components_json = [[{"stage": stage, "area": area} for stage, area in component] for component in components]; anchor = components[0][0] if components else ("", 0); ladder_transitions.sort(key=lambda item: (item["source"]["stage"], item["source"]["area"], item["destination"]["stage"], item["destination"]["area"]))
	manifest = {"coordinate_basis": {"native_to_godot": UNIT_BASIS, "unit": "1/256 map unit", "rotation": "identity for every room"}, "placement_source": "reciprocal native Flutter door routes matched to static door-face quads in area GLBs; vertical ladder routes remain transitions", "anchor": {"stage": anchor[0], "area": anchor[1], "world_offset": [0, 0, 0]}, "graph": {"room_count": len(rooms), "reciprocal_edge_count": len(edges), "connected": len(components) == 1, "component_count": len(components), "is_tree": len(components) == 1 and len(edges) == len(rooms) - 1, "is_forest": len(edges) == len(rooms) - len(components), "components": components_json, "cycle_residuals": residuals}, "rooms": rooms, "portals": portals, "ladder_transitions": ladder_transitions, "external_routes": external, "route_data_remains_local": True, "source_sha256": {stage: {"manifest": hashlib.sha256((assets_dir / stage / "manifest.json").read_bytes()).hexdigest(), "doors": route_hashes[stage]} for stage in STAGES}}
	output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"Flutter room layout: {len(rooms)} rooms, {len(portals)} paired portals, {len(external)} external routes -> {output_path}"); return manifest

def room_layout_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--assets-dir", type=Path, default=ROOT / "assets/levels"); parser.add_argument("--output", type=Path, default=ROOT / "assets/locations/room_layout.json"); args = parser.parse_args(); export_room_layout(args.assets_dir, args.output)
from disc import decompress_section
from disc import read_u16
from disc import read_u32
from ui import decode_page
from models import actor_archive
from models import export_actor_model
from models import export_static_actor
from cinematics import record_source
if __name__ == '__main__':
	import sys
	commands = {'maps': 'maps_cli', 'lighting': 'lighting_cli', 'minimap': 'minimap_cli', 'stage': 'stage_cli', 'room-layout': 'room_layout_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
