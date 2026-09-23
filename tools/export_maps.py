import argparse
import hashlib
import json
import struct
import zlib
from collections import defaultdict
from pathlib import Path
from extract_maps import decompress_section, read_u16, read_u32
UNIT = 1.0 / 256.0
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
		if x == 255 or x > end_x or z > end_z: return None
		tiles = {}; ids = set()
		for i in range((end_x - x + 1) * (end_z - z + 1)):
			offset = start + 4 + i * 12; flags, tx, tz = struct.unpack_from("<HBB", b, offset); tiles[(tx, tz)] = b[offset:offset + 12]
			if flags & 0x8000: ids.add(flags & 0x7ff)
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
				coordinates = [((p[0] << shift) * UNIT, -(p[1] << shift) * UNIT, (p[2] << shift) * UNIT) for p in points]; texcoords = struct.unpack_from("<8B", b, uv_base + face * 8); brightness = struct.unpack_from("<4B", b, color_base + face * 4); flag = new[0][3]
				groups[(materials[material], bool(flag & 32), flag & 3)].append((coordinates, [(texcoords[i * 2] + 0.5, texcoords[i * 2 + 1] + 0.5) for i in range(4)], brightness)); previous = points
			if remaining: raise ValueError(f"model {pointer:#x} ends inside a quad strip")
		self.cache[pointer] = groups
		return groups
class Glb:
	def __init__(self, vram):
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
			clut, tpage = page; image = len(self.document["images"]); self.document["images"].append({"bufferView": self.buffer(texture_page(self.vram, clut, tpage)), "mimeType": "image/png"}); texture = len(self.document["textures"]); self.document["textures"].append({"sampler": 0, "source": image}); self.pages[page] = texture
		index = len(self.document["materials"]); self.document["materials"].append({"name": f"clut_{page[0]:04x}_page_{page[1]:04x}", "pbrMetallicRoughness": {"baseColorTexture": {"index": self.pages[page]}, "metallicFactor": 0, "roughnessFactor": 1}, "alphaMode": "MASK", "alphaCutoff": 0.01, "doubleSided": two_sided, "extensions": {"KHR_materials_unlit": {}}, "extras": {"psx_blend": blend}}); self.materials[key] = index
		return index
	def mesh(self, pointer, groups):
		if pointer in self.meshes: return self.meshes[pointer]
		primitives = []
		for key, faces in groups.items():
			positions = []; uvs = []; colors = []
			for coordinates, texcoords, brightness in faces:
				for i in (0, 1, 2, 1, 3, 2): positions.extend(coordinates[i]); uvs.extend(v / 256 for v in texcoords[i]); colors.extend([min(brightness[i] / 128, 1)] * 3 + [1])
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
def export(stage_name, input_dir, output_dir):
	source = (input_dir / f"{stage_name}.BIN").read_bytes(); stage = Stage(source); texture_path = input_dir / f"{stage_name}T.BIN"; vram, texture_count = textures(texture_path); destination = output_dir / stage_name; destination.mkdir(parents=True, exist_ok=True); areas = []
	for index in range(len(stage.grids)):
		area = stage.area(index)
		if area is None or not area[1]: continue
		tiles, ids = area; glb = Glb(vram); quads = 0
		for placement_id in ids:
			state, model_id, flags, height, x, z = stage.placements[placement_id]; a, h, directory = stage.directories[model_id]; variant = flags & 3; variants = ((h >> 24) & 1) + 1
			if variant >= variants: raise ValueError(f"placement {placement_id} selects invalid variant {variant}")
			pointer = read_u16(stage.data, stage.base + (directory & 65535) * 4 + variant * 12); groups = stage.model(pointer); tile = tiles[(x, z)]; oy = 0x400 - tile[6] * 16 - ((height & 0x7f00) >> 4); translation = [((x << 9) - (0x7e00 if h & 0x10000000 else 0x7f00)) * UNIT, -oy * UNIT, ((z << 9) - (0x7e00 if h & 0x20000000 else 0x7f00)) * UNIT]; glb.instance(f"placement_{placement_id:03d}_model_{model_id:03d}", pointer, groups, translation); quads += sum(len(f) for f in groups.values())
		name = f"area_{index:02d}.glb"; bounds = glb.save(destination / name); areas.append({"index": index, "file": name, "placements": len(ids), "models": len(glb.meshes), "quads": quads, "bounds": bounds}); print(f"{stage_name}/{name}: {len(ids)} placements, {quads} quads, {len(glb.pages)} texture pages")
	manifest = {"stage": stage_name, "source_sha256": hashlib.sha256(source).hexdigest(), "textures_sha256": hashlib.sha256(texture_path.read_bytes()).hexdigest(), "texture_sections": texture_count, "areas": areas}; (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest
def main():
	parser = argparse.ArgumentParser(); parser.add_argument("--input-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--output-dir", type=Path, default=Path("assets/levels")); parser.add_argument("--stage", default="ST0F"); args = parser.parse_args(); export(args.stage.upper(), args.input_dir, args.output_dir)
if __name__ == "__main__": main()
