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
AREA_TEXTURE_BANKS = {("ST3A", 3): [{"file": "ST3A01.BIN", "file_id": 252, "source": "ST3AT overlay callback 0x800F2FEC via SLES0x8001B2D8"}, {"file": "ST3A02.BIN", "file_id": 253, "source": "ST3AT overlay callback 0x800F40A8 via SLES0x8001B2D8"}]}
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
	return {"source_call": hex(base + call - 48), "uv_pointer": hex(address), "uv_words": list(struct.unpack_from("<32I", data, position)), "config_pointer": hex(config), "config_bytes_hex": data[config - base + 48:config - base + 84].hex(), "native_renderer": "SLES0x80027E84 selects terrain when cell&0x4000; UV0x80028534; TPAGE0x80026EB8; CLUT0x80028950"}
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
		self.binary.extend(b"\0" * (-len(self.binary) % 4)); self.document["buffers"][0]["byteLength"] = len(self.binary); text = json.dumps(self.document, separators=(",", ":")).encode(); text += b" " * (-len(text) % 4); size = 12 + 8 + len(text) + 8 + len(self.binary); write_if_changed(path, struct.pack("<3I", 0x46546c67, 2, size) + struct.pack("<2I", len(text), 0x4e4f534a) + text + struct.pack("<2I", len(self.binary), 0x004e4942) + self.binary)
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
	manifest = {"stage": stage_name, "coordinate_basis": COORDINATE_BASIS, "source_sha256": hashlib.sha256(source).hexdigest(), "textures_sha256": hashlib.sha256(texture_path.read_bytes()).hexdigest(), "texture_sections": texture_count, "areas": areas}; write_if_changed(destination / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
	trig_offset = 0x80073E4C - exe_load; math_data = {"source": "SLES80073E4C; map windows270CC..276E4 and2984C; rays yaw+-0x100, division constants384/4096 and cell centers512", "trig4096": [list(struct.unpack_from("<2h", exe_code, trig_offset + index * 4)) for index in range(4096)]}; output_dir.mkdir(parents=True, exist_ok=True); write_if_changed(output_dir / "visibility_math.json", json.dumps(math_data, separators=(",", ":")) + "\n")
	for stage in sorted(set(stages or [path.stem for path in dat_dir.glob("ST??.BIN")])):
		root_path = dat_dir / (stage + ".BIN"); overlay_path = dat_dir / (stage + "T.BIN")
		if not root_path.is_file() or not overlay_path.is_file(): continue
		stage_data = Stage(root_path.read_bytes())
		try: cue = map_depth_cue_info(overlay_path.read_bytes(), exe_code, exe_load, len(stage_data.grids))
		except ValueError as error: result["unresolved"][stage] = str(error); continue
		for area in cue["area_parameters"]:
			geometry = stage_data.area(area["area"]); tiles = geometry[0] if geometry is not None else {}; cells = {}
			grid = stage_data.grids[area["area"]]; area["visibility"]["window"] = {"enabled": geometry is not None and area["mode"] in (0, 1), "grid_bounds": list(stage_data.data[grid:grid + 4]), "math_manifest": "res://assets/levels/visibility_math.json", "source": "SLES270CC..276E4 near square plus yaw-dependent2770C/27A24 scan bands; mode1 equivalent2984C", "half_ray_angle_raw": 256}
			for (x, z), tile in sorted(tiles.items()):
				flags = read_u16(tile, 0)
				if flags == 0xFFFF or not flags & 0x8000 or flags & 0x4000: continue
				cells.setdefault(str(flags & 0x7FF), []).append([(x << 9) - 0x7F00, (z << 9) - 0x7F00])
			area["visibility"]["placement_cells"] = cells; area["visibility"]["cell_center_source"] = "SLES27C08..27C24:cellX/Z*512-0x7F00"; area["visibility"]["test_plane_source"] = "SLES27B10..27B54:cameraNativeY+(sin(-cameraPitch)*(tileRange+1)>>4)"; area["visibility"]["placement_gate_source"] = "SLES26E08..26E28 clears visibility flags;27E38 dispatch marks referenced placements from visible cells;2F0F4..2F100 draws only marked records"; area["visibility"]["runtime_adapters"] = ["Godot camera transforms feed the native per-cell depth test; the native integer GTE transform is not emulated.", "Combined terrain geometry reconstructs512-unit cell centers from its local x/z fragment coordinates.", "Mode0/1 near-square and yaw-dependent far scan bands use the original integer LUT and division rules; mode2/3 traversal and model directionalLOD selection remain separate."]
		path = output_dir / stage / "lighting.json"; lighting = json.loads(path.read_text()) if path.is_file() else {"sources": {"stage_overlay": {"file": "build/disc-assets/DAT/" + overlay_path.name, "sha256": hashlib.sha256(overlay_path.read_bytes()).hexdigest()}}, "native_color_pipeline": {}}
		lighting.setdefault("native_color_pipeline", {})["depth_cue"] = cue; path.parent.mkdir(parents=True, exist_ok=True); write_if_changed(path, json.dumps(lighting, indent=2) + "\n"); result["stages"][stage] = len(cue["area_parameters"])
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
	OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True); write_if_changed(OUTPUT_PATH, json.dumps(lighting, indent=2) + "\n", encoding="utf-8"); print(f"Wrote {OUTPUT_PATH}: {len(areas)} areas, ST0FT CTC2 registers {overlay['ctc2_control_registers_written']}")

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
	output_dir.mkdir(parents=True, exist_ok=True); atlas_path = output_dir / "tiles.png"; write_if_changed(atlas_path, atlas)
	manifest = {"stage": "ST0F", "atlas": "tiles.png", "atlas_size": [256, 256], "atlas_clut": ATLAS_CLUT, "atlas_tpage": ATLAS_TPAGE, "atlas_alpha": "zero palette word transparent; STP bit alpha 128; other nonzero palette words opaque", "atlas_sha256": sha256(atlas), "source": {"root_file": "build/maps/ST0F_map.bin", "root_type": 13, "root_sha256": sha256(root), "root_grid_table_index": ROOT_GRID_POINTER, "root_grid_base": ROOT_GRID_BASE, "root_grid_end": previous_end, "layout_file": "build/disc-assets/DAT/ST0FT.BIN", "layout_sha256": sha256(stage_texture), "area_pointer_offset": AREA_POINTER_OFFSET, "area_layout_offset": AREA_LAYOUT_OFFSET, "texture_sections": texture_count, "arrow_code_file": "build/disc-assets/COMMON/GAME.BIN", "arrow_code_address": "0x800BB5B0", "arrow_call_site": "ST0FT 0x800FCD1C"}, "draw": {"gpu_opcode": "0x7E", "texture_blend_mode": "average", "tile_pixels": 16, "tile_uv_pixels": {"u": "(tile_id & 0x0f) * 16", "v": "tile_id & 0xf0"}, "skip_tile_ids": [255, 92, 93, 94, 95], "visited_rgb": [128, 128, 128], "unvisited_small_area_rgb": [48, 48, 48], "unvisited_area_threshold": 5, "small_area_rule": "areas with index below threshold draw undiscovered tiles dark; larger areas omit undiscovered tiles", "native_clip": {"x": 12, "y": 24, "width": 72, "height": 72}, "map_center_pixels": [0, 0], "tile_origin_pixels": {"x": "-8 * area.width + 16 * column", "y": "8 * area.height - 16 - 16 * row"}, "player_position_source_offsets": {"x": "player+0x12 (signed16)", "z": "player+0x1A (signed16)"}, "player_scroll_pixels": {"x": "signed16(player_x) >> 6", "y": "-(signed16(player_z) >> 6)"}, "tile_draw_base_pixels": {"x": "anchor_x + 36 - scroll_x", "y": "framebuffer_y + 60 - scroll_y", "anchor_x": 12, "framebuffer_y": 0}, "player_marker_pixels": {"x": "(signed16(player_x) >> 6) - center_x", "y": "center_z - (signed16(player_z) >> 6)"}, "player_arrow": {"callback_call_site": "ST0FT 0x800FCD1C", "draw_address": "COMMON/GAME.BIN 0x800BB5B0", "gpu_opcodes": ["0x30", "0x4C"], "heading_delta": "signed16(player+0xF2) - signed16(player+0x2A)", "heading_field_meanings": "unknown", "draw_style": "Gouraud triangle plus closed polyline", "angle_zero_triangle": [[0, 6], [-3, -5], [3, -5]], "cardinal_tip_by_angle": {"0": [0, 6], "1024": [6, 0], "2048": [0, -6], "3072": [-6, 0]}}, "area_extra_fields_used_by_minimap_callback": False}, "areas": areas}
	manifest_path = output_dir / "manifest.json"; write_if_changed(manifest_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
				boxes.append({"x": [values[0] + offset_x, values[1] + offset_x], "z": [values[2] + offset_z, values[3] + offset_z], "y": [values[4] + offset_y, values[5] + offset_y], "kind": values[6], "mask": values[7], "placement": placement, "source_offset": hex(offset), "contact_raw": [int((values[0] + values[1]) / 2) + offset_x, int((values[4] + values[5]) / 2) + offset_y, int((values[2] + values[3]) / 2) + offset_z]})
		result[str(area)] = {"grid": {"%d:%d" % coordinates: list(data) for coordinates, data in tiles.items()}, "boxes": boxes, "source": "SLES0x80038D20 placement collision directory; GAME0x800B13FC floor selector; GAME0x800B5658 shape0 footprint"}
	return result

def floor_collision_manifest(path):
	return {area: {"boxes": source["boxes"], "source": source["source"], "slope_source": "GAME0x800B1C48;kind10:+Z,11:-Z,12:+X,13:-X;B1EA8 integer interpolation;B2868 upper surface"} for area, source in export_floor_shapes(path).items()}

def bind_route_contacts(routes, floors):
	for route in routes:
		matches = [box for box in floors.get(str(route["source_area"]), {}).get("boxes", []) if box["kind"] >= 0x100 and box["contact_raw"] == route["source_transform_raw"][:3]]
		route["native_contacts"] = [{**box, "type": box["kind"] >> 8, "automatic": box["kind"] == 0xF00, "probe_forward_raw": -64 if box["mask"] & 0x8000 else 0, "source_consumer": "GAME0x800B8588;type15:0x800B8134->0x800B8460"} for box in matches]
	return routes

NATIVE_SCRIPTED_INTERACTIONS = {"ST04": {(1, 0): (0x800E8190, 0x800E84C4, 2, False), (96, 0): (0x800E9DB0, 0x800EA15C, 0, False)}, "ST08": {(0, 0): (0x800E78CC, 0x800E7D4C, 0, False), (0, 1): (0x800E93EC, 0x800E9A1C, 0, True), (0, 2): (0x800EBFFC, 0x800EC58C, 0, True), (1, 0): (0x800EA4F4, 0x800EA828, 2, False)}, "ST09": {(0, 0): (0x800E81EC, 0x800E866C, 0, False)}}
def bind_scripted_interactions(stage, records, overlay):
	base = read_u32(overlay, 12)
	for record in records:
		raw = bytes.fromhex(record["source_bytes_hex"]); profile = NATIVE_SCRIPTED_INTERACTIONS.get(stage, {}).get((raw[4], raw[5])) if len(raw) == 20 and raw[2] == 0x20 else None
		if profile is None: continue
		actor_callback, request, kind, signed = profile; offset = 48 + request - base
		if not 48 <= offset <= len(overlay) - 8 or read_u32(overlay, offset) != 0x0C02F8B8: raise ValueError(f"{stage} scripted interaction source call differs at {request:#x}")
		if not any(read_u32(overlay, at) >> 26 == (0x20 if signed else 0x24) and read_u32(overlay, at) & 65535 == 0x0F for at in range(offset - 20, offset, 4)): raise ValueError(f"{stage} scripted interaction index load differs at {request:#x}")
		record["native_private_raw"] = list(raw[8:12]); record["native_interaction"] = {"stage": stage, "actor_class": raw[4], "actor_state": raw[5], "actor_callback": hex(actor_callback), "request_call": hex(request), "request_api": "0x800BE2E0", "request_kind": kind | ((raw[9] >> 2) & 0x10) if not signed else kind, "message_call": "0x800BDCF8", "message_index": raw[11] - 256 if signed and raw[11] & 128 else raw[11], "index_source": ("signed" if signed else "unsigned") + " actor+0x0F copied from record byte0x0B", "window": 0, "selected_actor_gate": "GAME0x800D0154 requires player+1D0 low24bits equal actor and bit24 set", "bank_id": "0x8010C000", "source_record_ram": record["source_record_ram"]}
	return records

REFERENCE = "https://dwn009.fandom.com/wiki/Mega_Man_Legends_2/Locations"
STAGE_NAMES = {"ST00": "Debug area", "ST01": "World map", "ST02": "Sulphur-Bottom opening", "ST03": "Flutter opening", **dict.fromkeys(["ST04", "ST05", "ST06", "ST07"], "Flutter"), **dict.fromkeys(["ST08", "ST09", "ST0A", "ST0B", "ST0C", "ST47"], "Yosyonke City"), **dict.fromkeys(["ST0D", "ST0E"], "Calinca Tundra"), "ST0F": "Abandoned Mine", **dict.fromkeys(["ST10", "ST11", "ST1D"], "Forbidden Island"), **dict.fromkeys(["ST12", "ST13", "ST14"], "Manda Ruins"), **dict.fromkeys(["ST15", "ST16", "ST18", "ST19"], "Nino Island"), "ST17": "King Glydon", **dict.fromkeys(["ST1A", "ST1B"], "Ruminoa City"), "ST1C": "Forbidden Island / Sulphur-Bottom scenes", "ST1E": "Flutter fire", **dict.fromkeys(["ST1F", "ST30", "ST31"], "Glyde's Base"), "ST20": "Kito Village", **dict.fromkeys(["ST21", "ST22", "ST23"], "Calbania Plains"), "ST24": "Pokte Plains", "ST25": "Pokte Village", **dict.fromkeys(["ST26", "ST27", "ST28", "ST33", "ST34"], "Saul Kada Ruins"), **dict.fromkeys(["ST29", "ST2A", "ST2B", "ST2C", "ST3B", "ST3C"], "Kimotoma City"), **dict.fromkeys(["ST2D", "ST2E", "ST2F"], "Calinca Ruins"), "ST32": "Pokte Mayor's Home", **dict.fromkeys(["ST35", "ST36", "ST37", "ST38"], "Nino Ruins"), "ST39": "Flutter new-game scene", "ST3A": "Sulphur-Bottom / Forbidden Island scenes", **dict.fromkeys(["ST3D", "ST3E", "ST3F", "ST4B"], "Sulphur-Bottom"), "ST40": "Elysium", **dict.fromkeys(["ST41", "ST42"], "Defense Area"), **dict.fromkeys(["ST43", "ST44", "ST45", "ST4C", "ST58", "ST5C"], "Mother Zone"), "ST46": "Nino Island / Flutter scenes", "ST48": "Saul Kada Desert", "ST49": "Flutter / Dropship scenes", "ST4A": "Tutorial", "ST4D": "Guild Ruins", **dict.fromkeys(["ST4E", "ST51"], "Pokte Caverns"), "ST4F": "Kito Caverns", "ST50": "Kimotoma Caverns", "ST52": "Sera / Master scenes", "ST53": "Calinca Tundra scenes", "ST54": "Rocket launch ending", "ST55": "License Test Ruins", "ST56": "Master's Room", "ST57": "Game credits", "ST59": "Manda Circuit", "ST5A": "Calinca Circuit", "ST5B": "Saul Kada Circuit"}
LOCATIONS = (("ST04", 0, "Flutter Bridge"), ("ST04", 1, "Flutter Deck 1"), ("ST04", 2, "Flutter Lab"), ("ST05", 0, "Flutter MegaMan's Room"), ("ST05", 1, "Flutter Roll's Room"), ("ST05", 2, "Flutter Barrell's Room"), ("ST06", 0, "Flutter Deck 2"), ("ST06", 1, "Flutter Toilet"), ("ST06", 2, "Flutter Storage"), ("ST06", 3, "Flutter Living Room"), ("ST06", 4, "Flutter Kitchen"), ("ST06", 5, "Flutter Bathroom"), ("ST07", 0, "Flutter Deck 3"), ("ST07", 1, "Flutter Hangar"), ("ST07", 2, "Flutter Engine Room"))
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
			data, section = decompress_section(source, offset, 36); palette_data = data[:palette_size]; image_data = data[palette_size:expected]; section_end = offset + 0x30 + section["compressed_size"]; layout = "decompressed"
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
				name = "upload_%05X.bin" % offset; write_if_changed(directory / name, payload); entry.update(status="exported", file=name, sha256=hashlib.sha256(payload).hexdigest(), packing="Native palette words followed by packed VRAM image words")
				if colors and palettes:
					pixels = bytearray()
					for index in range(colors * palettes):
						word = read_u16(palette_data, index * 2); pixels.extend(((word & 31) * 255 // 31, ((word >> 5) & 31) * 255 // 31, ((word >> 10) & 31) * 255 // 31, 0 if word == 0 else 128 if word & 0x8000 else 255))
					name = "palette_%05X.png" % offset; write_if_changed(directory / name, png(colors, palettes, pixels)); entry["palette_file"] = name
			except (ValueError, IndexError, struct.error) as error: entry.update(status="unsupported", error=str(error))
			entries.append(entry)
		if entries: write_if_changed(directory / "manifest.json", json.dumps({"textures": entries}, indent=2), encoding="utf-8"); result.extend(entries)
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
			tiles, placement_ids = area; area_banks = AREA_TEXTURE_BANKS.get((stage_name, area_index), []); area_paths = [texture_path, *[input_dir / bank["file"] for bank in area_banks]]; area_vram, loaded_banks = texture_vram(area_paths) if area_banks else (vram, [{"file": texture_path.name, "sha256": digest(texture_bytes), "upload_count": texture_count}]); glb = Glb(area_vram, {}); quads = 0
			ground_binding = terrain_binding(texture_path, area_index) if any(read_u16(tile, 0) != 0xffff and read_u16(tile, 0) & 0x8000 and (read_u16(tile, 0) & 0x4000 or stage.placements[read_u16(tile, 0) & 0x7ff][3] & 0x8000) for tile in tiles.values()) else None
			ground = terrain_groups(tiles, ground_binding, stage.placements) if ground_binding else {}
			if ground: glb.instance("terrain", -1, ground, [0, 0, 0]); quads += sum(len(faces) for faces in ground.values())
			if not placement_ids and not ground: continue
			for placement_id in placement_ids:
				_, model_id, flags, height, x, z = stage.placements[placement_id]; _, header, directory = stage.directories[model_id]; variant = flags & 3; variant_count = ((header >> 24) & 1) + 1
				if variant >= variant_count: raise ValueError(f"{stage_name} area {area_index:02d} placement {placement_id} selects invalid variant {variant}")
				pointer = read_u16(stage.data, stage.base + (directory & 0xffff) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [-((x << 9) - (0x7e00 if header & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if header & 0x20000000 else 0x7f00)) * UNIT]; glb.instance(f"placement_{placement_id:03d}_model_{model_id:03d}", pointer, groups, translation); quads += sum(len(faces) for faces in groups.values())
			file_name = f"area_{area_index:02d}.glb"; bounds = glb.save(stage_dir / file_name); area_manifest = {"index": area_index, "name": display_name.removeprefix(family + " ") if display_name and family else display_name or "Area %02d" % area_index, "file": file_name, "placements": len(placement_ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds, "native_map_code": {"stage": int(stage_name[2:], 16), "area": area_index}, "terrain_source": ground_binding}
			if area_banks: area_manifest["texture_state"] = {"source_order": [{"file": f"DAT/{texture_path.name}", "file_id": 254, "sha256": digest(texture_bytes), "source": "GAME0x800BA600 default ST3A root/T loader"}, *[{"file": f"DAT/{bank['file']}", "file_id": bank["file_id"], "sha256": item["sha256"], "source": bank["source"]} for bank, item in zip(area_banks, loaded_banks[1:])]], "applied_in_vram_order": True}
			areas.append(area_manifest); print(f"{stage_name}_{area_index:02d}: {len(placement_ids)} placements, {quads} quads")
		stage_manifest = {"stage": stage_name, "name": STAGE_NAMES.get(stage_name, stage_name), "source_reference": {"description": "native stage/substage values XX/YY and room labels", "url": REFERENCE} if stage_name in STAGE_BINDINGS else None, "coordinate_unit": "1/256 map unit", "coordinate_basis": COORDINATE_BASIS, "source": {"root_file": f"DAT/{stage_name}.BIN", "textures_file": f"DAT/{stage_name}T.BIN", "root_sha256": digest(root_bytes), "textures_sha256": digest(texture_bytes), "texture_sections": texture_count}, "areas": areas, "native_floor_collision": floor_collision_manifest(root_path), "native_combat_policy": native_combat_policy(texture_bytes)}; write_if_changed(stage_dir / "manifest.json", json.dumps(stage_manifest, indent=2) + "\n", encoding="utf-8"); catalog.append({"stage": stage_name, "name": stage_manifest["name"], "manifest": "res://" + (stage_dir / "manifest.json").resolve().relative_to(ROOT).as_posix(), "area_names": [area["name"] for area in areas]})
	catalog_path = output_dir.parent / "locations" / "manifest.json"; catalog_path.parent.mkdir(parents=True, exist_ok=True); existing = json.loads(catalog_path.read_text()).get("locations", []) if catalog_path.exists() else []; entries = {item["stage"]: item for item in existing}; entries.update({item["stage"]: item for item in catalog})
	for entry in entries.values():
		manifest = json.loads((ROOT / entry["manifest"].removeprefix("res://")).read_text()); entry["areas"] = [{"index": int(area["index"]), "name": str(area.get("name", "Area %02d" % area["index"]))} for area in manifest["areas"]]; entry.pop("area_names", None)
	catalog_manifest = {"locations": [entries[key] for key in sorted(entries)], "source_reference": REFERENCE}; write_if_changed(catalog_path, json.dumps(catalog_manifest, indent=2) + "\n", encoding="utf-8"); return catalog_manifest

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
		bind_route_contacts(routes, floor_collision_manifest(dat_dir / (stage + ".BIN")))
		walk = native_automatic_walk(data)
		for route in routes:
			if any(contact["automatic"] for contact in route["native_contacts"]): route["native_automatic_walk"] = walk
			if stage == "ST0F" and any(contact["type"] == 8 for contact in route["native_contacts"]):
				mode = route["door_mode"] >> 4; offsets = ((128, 0), (160, 0), (256, 0))
				if mode < len(offsets): route["native_door"] = {"style": "sliding_pair", "controller_class": 3, "variants": [route["door_slot"] * 2, route["door_slot"] * 2 + 1], "offset_raw": list(offsets[mode]), "opening_ticks": 10, "hold_ticks": 10, "closing_ticks": 9, "tick_rate": 25, "sounds": [0xBA, 0xBD, 0xBB], "player_gesture": False, "unsupported_event": 0x701, "source_placement": next(contact["placement"] for contact in route["native_contacts"] if contact["type"] == 8), "constructor": "ST0FT0x800FB198", "timeline": "ST0FT0x8010138C", "motion": "GAME0x800D20EC"}
				if "native_door" in route:
					_, faces = room_faces(output_dir, stage, route["source_area"]); raw = route["source_transform_raw"]; center = [-raw[0] / 256, -raw[1] / 256, raw[2] / 256]; axis = 2 if ((raw[3] & 4095) >> 10) % 2 == 0 else 0; prefix = f"placement_{route['native_door']['source_placement']:03d}_"; route["native_door"]["source_panel"] = select_panel([face for face in faces if face["node"].startswith(prefix)], center, axis)
		manifest = {**previous, "stage": stage, "binding_status": "partial" if binding and unresolved_areas else "bound" if binding else "unbound", "source": {**previous.get("source", {}), "file": f"DAT/{stage}T.BIN", "sha256": digest(data), "area_route_pointer_ram": hex(binding["routes"]) if binding else None, "active_pointer_ram": "0x80078FA4", "native_table_writers": discovered["routes"], "native_actor_tables": discovered["actors"], "unresolved_areas": unresolved_areas, "unresolved": None if binding else "No unique source area-table assignment to 0x80078FA4", "record_stride": 24, "consumer": "GAME0x800B7B38-0x800B7E74", "lock_consumer": "GAME0x800B89B4", "transition_consumer": "GAME0x800B8A2C", "native_contact": "xyz matches collision contact0x800E0BCC; heading difference within[-0x200,0x200)", "runtime_interaction": "PC interaction requires a nearby door face and native heading; destinationY=-1 resolves room collision floor"}, "area_transitions": routes}; manifests[stage] = manifest; result[stage] = routes
	for stage, routes in result.items():
		for route in routes:
			other = result.get(route["destination_stage"])
			reciprocal = next((candidate for candidate in other or [] if candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"]), None); route["reciprocal_native_route"] = reciprocal is not None
			if stage in STAGES and route["destination_stage"] not in STAGES and reciprocal is not None:
				reverse = next(candidate for candidate in other if candidate["source_area"] == route["destination_area"] and candidate["destination_stage"] == stage and candidate["destination_area"] == route["source_area"]); center, axis = route_center(route, reverse, True); _, faces = room_faces(output_dir, stage, route["source_area"]); route["source_panel"] = select_panel(faces, center, axis)
	for stage, manifest in manifests.items(): write_if_changed(output_dir / stage / "doors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
def actor_archive_for_records(stage, source, records, work, dat_dir, fallback_offset=None):
	required = [record for record in records if record["raw"][2] in (0x20, 0x60, 0x61) and not (record["raw"][2] == 0x60 and record["raw"][4] == 2 and record["raw"][5] == 0)]
	candidates = []; offsets = list(range(0x400, len(source) - 0x30, 0x400))
	if fallback_offset is not None: offsets.insert(0, fallback_offset)
	for offset in dict.fromkeys(offsets):
		if offset + 12 > len(source) or read_u32(source, offset) != 0x0C: continue
		try:
			payload, section = decompress_section(source, offset); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); normalized = work / f"{stage}_models_{offset:05X}.bin"; write_if_changed(normalized, header + payload); archive, payload = actor_archive(normalized)
		except (ValueError, IndexError, KeyError, struct.error, OSError): continue
		match_count = 0
		for record in required:
			raw = record["raw"]; flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == flags]
			if len(matches) == 1: match_count += 1
		door_count = sum(1 for model in archive["models"] if model["flags"] & 0xFFFF in (0x161, 0x361))
		if required and match_count == 0: continue
		if not required and not door_count and fallback_offset != offset: continue
		candidates.append((match_count, door_count, offset, archive, payload, section, stage + ".BIN"))
	extra_archive_path = dat_dir / (stage + "00.BIN")
	if extra_archive_path.is_file() and read_u32(extra_archive_path.read_bytes(), 0) == 10:
		try:
			archive, payload = actor_archive(extra_archive_path); match_count = 0
			for record in required:
				raw = record["raw"]; flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == flags]
				if len(matches) == 1: match_count += 1
			door_count = sum(1 for model in archive["models"] if model["flags"] & 0xFFFF in (0x161, 0x361))
			if required and match_count: candidates.append((match_count, door_count, None, archive, payload, None, extra_archive_path.name))
		except (ValueError, IndexError, KeyError, struct.error, OSError): pass
	if not candidates: return None
	candidates.sort(key=lambda value: (-value[0], -value[1], 0 if value[2] == fallback_offset else 1 if value[2] is not None else 2, value[2] or 0)); best = candidates[0]
	if len(candidates) > 1 and (candidates[1][0], candidates[1][1]) == (best[0], best[1]) and fallback_offset not in (best[2], candidates[1][2]): return None
	return {"archive": best[3], "payload": best[4], "section": best[5], "offset": best[2], "archive_file": best[6]}
def export_props(dat_dir, output_dir, stages):
	output_dir.mkdir(parents=True, exist_ok=True); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); target = output_dir / "manifest.json"; manifest = json.loads(target.read_text()) if target.exists() else {"stages": {}}
	for stage in stages:
		manual = STAGE_BINDINGS.get(stage, {}); overlay_path = dat_dir / (stage + "T.BIN"); root_path = dat_dir / (stage + ".BIN"); instances = []; models = {}; native_doors = []; unresolved = []; weather_records = []; section = None; uploads = []; source = root_path.read_bytes()
		if not overlay_path.is_file(): manifest["stages"][stage] = {"binding_status": "unbound", "source": {"archive": root_path.name, "overlay": overlay_path.name}, "models": [], "native_doors": [], "instances": []}; continue
		overlay = overlay_path.read_bytes(); area_count = len(Stage(source).grids); table_area_count = area_count; detections = native_actor_lists(overlay, table_area_count); detected = detections[0] if detections else None
		if detected: actor_pointer_table = detected["address"]; actor_caller = hex(detected["call_pc"]); raw_records = detected["records"]
		else: actor_pointer_table = None; actor_caller = None; raw_records = []
		weather_records = [{"area": item["area"], "source_file_offset": hex(item["offset"]), "source_bytes": item["raw"].hex(), "native_type": "procedural_weather"} for item in raw_records if item["raw"][2] == 0x60 and item["raw"][4] == 2 and item["raw"][5] == 0]; mesh_records = [item for item in raw_records if item["raw"][2] in (0x20, 0x60, 0x61) and not (item["raw"][2] == 0x60 and item["raw"][4] == 2 and item["raw"][5] == 0)]; archive_info = actor_archive_for_records(stage, source, raw_records, work, dat_dir, manual.get("actor_section")) if actor_pointer_table is not None else None; archive_source = archive_info["archive_file"] if archive_info else root_path.name
		if actor_pointer_table is not None and archive_info is None and mesh_records: unresolved.extend({"area": item["area"], "source_file_offset": hex(item["offset"]), "source_bytes": item["raw"].hex(), "reason": "no uniquely matching type-0x0C PBD archive"} for item in mesh_records)
		if archive_info:
			archive = archive_info["archive"]; payload = archive_info["payload"]; section = archive_info["section"]; vram = bytearray(1024 * 512 * 2)
			for bank in SHARED_TEXTURES:
				bank_path = dat_dir.parent / bank
				if bank_path.is_file(): uploads.extend(texture_uploads(bank_path.read_bytes(), vram, bank))
			uploads.extend(texture_uploads(overlay, vram, "DAT/" + overlay_path.name)); uploads.extend(texture_uploads(source, vram, f"DAT/{stage}.BIN")); texture_header = bytearray(48); struct.pack_into("<3I", texture_header, 0, 2, len(vram), 1); struct.pack_into("<8H", texture_header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / (stage + "_vram.bin"); write_if_changed(texture_path, texture_header + vram)
			for item in raw_records:
				area = item["area"]; record = item["record"]; pointer = item["pointer"]; offset = item["offset"]; raw = item["raw"]
				if raw[2] == 0x60 and raw[4] == 2 and raw[5] == 0: continue
				if raw[2] not in (0x20, 0x60, 0x61): continue
				resource_flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
				if len(matches) != 1: unresolved.append({"area": area, "source_file_offset": hex(offset), "source_bytes": raw.hex(), "resource_flags": hex(resource_flags), "reason": "no unique PBD model match"}); continue
				model = matches[0]; index = model["index"]
				if index not in models:
					path = output_dir / stage / f"model_{index:02d}.glb"; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_actor_model(payload, index, texture_path, path, archive_source) if model["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, path, archive_source); metadata["source_surfaces"] = record_source(path, archive_source, index, payload); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata
				x, y, z, yaw = struct.unpack_from("<3hH", raw, 12); instances.append({"area": area, "source_ram": hex(pointer + record * 20), "source_file_offset": hex(offset), "source_file_offset_value": offset, "source_bytes": raw.hex(), "class": raw[4], "variant": raw[6], "model_index": index, "model_file": models[index]["model_file"], "position_raw": [x, y, z], "position": [-x / 256, -y / 256, z / 256], "yaw_raw": yaw, "yaw_turns": -yaw / 4096, "control": raw[8], "frame": raw[9], "role": manual.get("roles", {}).get(raw[4], "source_prop"), "native_control_source": "Native record bytes8/9; original PBD control table", "controller_candidate": manual.get("controllers", {}).get(raw[4])})
			for model in archive["models"]:
				if model["flags"] & 0xFFFF not in (0x161, 0x361): continue
				index = model["index"]
				if index not in models:
					path = output_dir / stage / f"model_{index:02d}.glb"; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_static_actor(payload, index, texture_path, path, archive_source); metadata["model_file"] = path.relative_to(output_dir).as_posix(); metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); models[index] = metadata
				native_doors.append({"variant": (model["flags"] >> 16) & 255, "controller_class": (model["flags"] >> 8) & 255, "model_index": index, "model_file": models[index]["model_file"], "native_scale_raw": models[index]["native_scale_raw"], "source_flags": hex(model["flags"]), "resource_loader": "SLES0x8003DFC8", "constructor": "GAME0x800D1F1C" if model["flags"] & 0xFFFF == 0x361 else "GAME0x800D1768"})
		for index, metadata in models.items(): metadata["model_index"] = index
		status = "bound" if actor_pointer_table is not None and (archive_info is not None or not mesh_records) else "partial" if actor_pointer_table is not None else "unbound"; manifest["stages"][stage] = {"binding_status": status, "source": {"archive": stage + ".BIN", "actor_archive": archive_info["archive_file"] if archive_info else None, "overlay": stage + "T.BIN", "sha256": digest(source), "decoded_section": section, "actor_pointer_table": hex(actor_pointer_table) if actor_pointer_table else None, "actor_list_area_count": len(detected["pointers"]) if detected else table_area_count if actor_pointer_table is not None else None, "caller": actor_caller, "consumer": "SLES0x8003D3F8; 20-byte object records", "actor_archive_section": archive_info["offset"] if archive_info else None, "texture_uploads": uploads, "coordinate_basis": "(-nativeX,-nativeY,+nativeZ)/256; room stream offset is separate"}, "models": list(models.values()), "native_doors": native_doors, "instances": instances, "procedural_records": weather_records, "unresolved_instances": unresolved}
	manifest["exterior"] = {"asset_source": "Original ST02 atmosphere assets", "effects_manifest": "res://assets/opening/effects/manifest.json", "native_effect_class": 18, "native_effect_variant": 3, "bank": "ST02", "parameter": 0x01000001, "source_renderer": "ST02T0x800EC0A4", "stage_native_selection": "Unbound; original atmosphere reuse is selected by the runtime"}; manifest["map_blending"] = {"source": "SLES0x8002FA14-0x8002FA44", "packed_status": "first vertex flag&3", "semi_enabled": "status!=0", "tpage": "baseTPAGE|((status-1)<<5) when semi enabled"}; write_if_changed(target, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
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
		texture_name = stage.lower() + "_field.png"; write_if_changed(output_dir / texture_name, png(128, 128, pixels)); image_uploads = []
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
	write_if_changed(output_dir / "snow.png", png(32, 32, pixels)); stages = {}; unresolved = []
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
	manifest = {"schema": 1, "profiles": field_profiles, "tick_rate": 25, "viewport": [320, 240], "particle_count": 32, "texture": "snow.png", "texture_source": {"archive": "COMMON/GAME.BIN", "tpage": "0x2F", "clut": "0x7C50", "uv": [32, 32, 32, 32], "blend": "Native GP0 opcode2E with additive TPAGE mode1; nonzero sprite texels are exported opaque for additive compositing"}, "source": {"record_parser": "SLES8003D3F8 20-byte type60/61 records", "callback_binding": "SLES8003CC58..3CC84 indexes source stage table80078DE0 with actor+4/+5", "reference": "ST08T800ED6BC/EDCA4/EDD4C/EDB80", "timing": "PAL GAME800AE948 ->SLES8001136C(a0=0),divider2 at50fields; GAME800B0244 ->8003CBD0 once per update", "particle_word": "x+180:bits0..8; y:bits9..17; depth:bits18..27", "screen_ranges": {"x": [-180, 180], "y": [0, 280], "depth": [0, 1024]}, "initial_depth": [200, 1023], "draw_minimum_depth": 100, "sprite_size": "1+((1024-depth)>>8)", "sprite_color": "64+(depth>>3)", "rng": "((state<<1)+(state>>31)+1)^873CA9E5 modulo2^32", "trig_table": "SLES80073E4C", "camera_source": {"current_eye": "8007D010+2C/30/34", "previous_eye": "8007D010+3C/40/44", "eye_writer": "SLES80015DB0..80015E24", "displacement": "previous-current, added to source wind", "current_angles": "8007D010+7C/7E", "previous_angles": "8007D010+84/86", "angle_delta": "previous-current; current-angle sin/cos basis", "canonical_camera_adapter": "nativeEye=(-GodotX,-GodotY,+GodotZ)*256; nativePitch=GodotPitch; nativeYaw=PI-GodotYaw", "radial_terms": "ST08T800EDF68/800EDFA4 use signed16 depth velocity S2, not angular sine", "horizontal_rotation": "ST08T800EDF94 uses depth*yawDeltaSine>>13"}}, "trig4096": trig, "stages": stages, "unresolved": unresolved, "renderer_adapters": ["Native 320x240 screen positions scale to the current viewport; flake size preserves the native vertical pixel scale.", "PC camera positions and Euler angles feed the native integer compensation formulas.", "The independent weather RNG stream does not reproduce native interleaving with other actors.", "Canvas additive flakes do not reproduce native ordering-table occlusion against 3D geometry."]}; write_if_changed(output_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n"); return manifest
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
	output_path.parent.mkdir(parents=True, exist_ok=True); write_if_changed(output_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"Flutter room layout: {len(rooms)} rooms, {len(portals)} paired portals, {len(external)} external routes -> {output_path}"); return manifest

def room_layout_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--assets-dir", type=Path, default=ROOT / "assets/levels"); parser.add_argument("--output", type=Path, default=ROOT / "assets/locations/room_layout.json"); args = parser.parse_args(); export_room_layout(args.assets_dir, args.output)
from disc import decompress_section, write_if_changed
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
