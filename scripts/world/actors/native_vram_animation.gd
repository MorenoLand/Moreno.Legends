extends Node
class_name NativeVramAnimation
const NativeMaterial := preload("res://scripts/world/rendering/native_material.gd")
var level: Node3D
var vram := PackedByteArray()
var animation: Dictionary
var tick := 0
var elapsed := 0.0
var pages: Dictionary = {}
var discovered := false
func configure(parent: Node3D, entry: Dictionary, vram_bytes: PackedByteArray) -> void:
	level = parent; animation = entry; vram = vram_bytes.duplicate()
func _physics_process(delta: float) -> void:
	if not is_instance_valid(level): return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func _discover() -> void:
	discovered = true
	for node: Node in level.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		if mesh == null: continue
		for surface in mesh.get_surface_count():
			var material := (node as MeshInstance3D).get_active_material(surface) as ShaderMaterial
			if material == null or not material.resource_name.begins_with("clut_"): continue
			var parts := material.resource_name.split("_"); var key := material.resource_name
			if parts.size() < 4: continue
			if not pages.has(key):
				var source := material.get_shader_parameter("albedo_texture") as Texture2D
				if source == null or source.get_image() == null: continue
				var image := source.get_image().duplicate() as Image
				if image.is_compressed(): image.decompress()
				image.convert(Image.FORMAT_RGBA8)
				pages[key] = {"clut": parts[1].hex_to_int(), "tpage": parts[3].hex_to_int(), "image": image, "texture": ImageTexture.create_from_image(image), "materials": [], "stp": not NativeMaterial.model_shader(0) == material.shader}
			pages[key]["materials"].append(material); material.set_shader_parameter("albedo_texture", pages[key]["texture"])
func _native_tick() -> void:
	if not discovered: _discover()
	var prefix: Array = animation["prefix"]; var period: Array = animation["period"]; var copies: Array = prefix[tick] if tick < prefix.size() else period[(tick - prefix.size()) % period.size()]
	tick += 1
	if copies.is_empty(): return
	var touched := {}
	for copy: Array in copies:
		var width := int(copy[2]); var height := int(copy[3]); var source := PackedByteArray(); var contiguous := (int(copy[0]) & 1023) + width <= 1024 and (int(copy[4]) & 1023) + width <= 1024
		if contiguous:
			for row in height: var at := (((int(copy[1]) + row) & 511) * 1024 + (int(copy[0]) & 1023)) * 2; source.append_array(vram.slice(at, at + width * 2))
			for row in height:
				var to := (((int(copy[5]) + row) & 511) * 1024 + (int(copy[4]) & 1023)) * 2; var from := row * width * 2; var length := width * 2; var offset := 0
				while offset + 8 <= length: vram.encode_u64(to + offset, source.decode_u64(from + offset)); offset += 8
				while offset < length: vram[to + offset] = source[from + offset]; offset += 1
		else:
			for row in height:
				for column in width: var at := (((int(copy[1]) + row) & 511) * 1024 + ((int(copy[0]) + column) & 1023)) * 2; source.append(vram[at]); source.append(vram[at + 1])
			for row in height:
				for column in width: var to := (((int(copy[5]) + row) & 511) * 1024 + ((int(copy[4]) + column) & 1023)) * 2; var from := (row * width + column) * 2; vram[to] = source[from]; vram[to + 1] = source[from + 1]
		for key: String in pages: if _patch(pages[key], int(copy[4]), int(copy[5]), int(copy[2]), int(copy[3])): touched[key] = true
	for key: String in touched: pages[key]["texture"].update(pages[key]["image"])
func _word(x: int, y: int) -> int: var at := ((y & 511) * 1024 + (x & 1023)) * 2; return vram[at] | (vram[at + 1] << 8)
func _patch(page: Dictionary, dx: int, dy: int, width: int, height: int) -> bool:
	var tpage: int = page["tpage"]; var depth := (tpage >> 7) & 3
	if depth > 2: return false
	var origin_x := (tpage & 15) * 64; var origin_y := ((tpage >> 4) & 1) * 256; var per_word := 4 if depth == 0 else 2 if depth == 1 else 1; var bits := 4 if depth == 0 else 8 if depth == 1 else 16
	var first_x := maxi(dx & 1023, origin_x); var last_x := mini((dx & 1023) + width, origin_x + 256 / per_word); var first_y := maxi(dy & 511, origin_y); var last_y := mini((dy & 511) + height, origin_y + 256)
	if first_x >= last_x or first_y >= last_y: return false
	var clut: int = page["clut"]; var clut_x := (clut & 63) * 16; var clut_y := clut >> 6; var image: Image = page["image"]; var lut := _lut(page["stp"])
	var region_width := (last_x - first_x) * per_word; var region_height := last_y - first_y; var bytes := PackedByteArray(); bytes.resize(region_width * region_height * 4)
	var palette := PackedInt32Array()
	if depth < 2:
		palette.resize(1 << bits)
		for index in palette.size(): palette[index] = lut[_word(clut_x + index, clut_y)]
	var mask := (1 << bits) - 1
	for y in range(first_y, last_y):
		var out := (y - first_y) * region_width * 4; var at := ((y & 511) * 1024 + first_x) * 2
		for x in range(first_x, last_x):
			var word: int = vram[at] | (vram[at + 1] << 8); at += 2
			if depth == 2: bytes.encode_u32(out, lut[word]); out += 4; continue
			for k in per_word: bytes.encode_u32(out, palette[(word >> (k * bits)) & mask]); out += 4
	image.blit_rect(Image.create_from_data(region_width, region_height, false, Image.FORMAT_RGBA8, bytes), Rect2i(0, 0, region_width, region_height), Vector2i((first_x - origin_x) * per_word, first_y - origin_y))
	return true
static var luts: Dictionary = {}
static func _lut(stp: bool) -> PackedInt32Array:
	if luts.has(stp): return luts[stp]
	var table := PackedInt32Array(); table.resize(65536)
	for color in range(1, 65536): table[color] = ((color & 31) * 255 + 15) / 31 | ((((color >> 5) & 31) * 255 + 15) / 31) << 8 | ((((color >> 10) & 31) * 255 + 15) / 31) << 16 | (128 if stp and (color & 0x8000) != 0 else 255) << 24
	luts[stp] = table
	return table
