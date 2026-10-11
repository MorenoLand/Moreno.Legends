extends CanvasLayer
## Draws the GPU packets of the original effect renderer: records that hold screen coordinates go over the 3D view, mapped from the 320 x 240 frame through the projection distance and the port camera's field of view; records with a world position (dropped items, shots, sparks) become depth tested quads of the 3D view, their packets placed back along the original camera's rays at the depth of each vertex's own projection so that they keep their place in the world as the port camera moves. Textures come from the stage's video memory image.

const VRAM_WIDTH := 1024
## Canvas per blend: mix (opaque, and the 0.5 B + 0.5 F rate carried by the vertex alpha), add (B + F, and B + 0.25 F by the vertex alpha) and subtract (B - F).
const BLEND := [CanvasItemMaterial.BLEND_MODE_MIX, CanvasItemMaterial.BLEND_MODE_ADD, CanvasItemMaterial.BLEND_MODE_SUB]
const RATE := [0.5, 1.0, 1.0, 0.25]
const CANVAS := [0, 1, 2, 1]
## Texture pixels by their semi-transparency bit: textured semi-transparent polygons blend only the pixels that carry bit 15 and draw the others opaque.
const ALL := 0
const SOLID := 1
const BLENDED := 2

var vram := PackedByteArray()
var textures: Dictionary = {}
var canvases: Array[Control] = []
var batches: Array = [[], [], []]
var world := Node3D.new()
var instances: Array[MeshInstance3D] = []
var materials: Dictionary = {}


func configure(path: String) -> void:
	layer = 0
	vram = FileAccess.get_file_as_bytes(path)
	for mode in 3:
		var canvas := Control.new()
		canvas.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
		canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		var material := CanvasItemMaterial.new()
		material.blend_mode = BLEND[mode]
		canvas.material = material
		canvas.draw.connect(_draw_mode.bind(canvas, mode))
		add_child(canvas)
		canvases.append(canvas)


## Triangle batches per canvas, consecutive packets of one texture sharing a batch; safe off the main thread. packets: the frame's GPU packets; projection: the GTE projection distance; fov: the port camera's vertical field of view in degrees; size: the viewport size.
func build(frame_packets: Array, projection: int, fov: float, size: Vector2) -> Array:
	var factor := size.y / (2.0 * float(maxi(projection, 1)) * tan(deg_to_rad(fov) * 0.5))
	var center := size * 0.5
	var result: Array = [[], [], []]
	for packet: Dictionary in frame_packets:
		var textured: bool = packet["textured"]
		var translucent: bool = packet["translucent"]
		var abr: int = int(packet["abr"]) if translucent else 0
		var vertices: Array[Vector2] = packet["vertices"]
		var packet_colors: Array[Color] = packet["colors"]
		var points := PackedVector2Array()
		for index in vertices.size():
			points.append(center + (vertices[index] - Vector2(160, 120)) * factor)
		var packet_uvs: Array[Vector2] = packet["uvs"]
		var passes: Array = [[CANVAS[abr], ALL, 1.0]]
		if translucent and textured:
			passes = [[0, SOLID, 1.0], [CANVAS[abr], BLENDED, RATE[abr]]]
		for step: Array in passes:
			var colors := PackedColorArray()
			for index in vertices.size():
				var color := packet_colors[index]
				colors.append(Color(minf(color.r * 2.0, 1.0), minf(color.g * 2.0, 1.0), minf(color.b * 2.0, 1.0), step[2]) if textured else Color(color.r, color.g, color.b, RATE[abr] if translucent else 1.0))
			var key := -1
			var texture: Texture2D = null
			if textured:
				key = int(packet["tpage"]) | (int(packet["clut"]) << 16) | (int(step[1]) << 28)
				texture = _texture(int(packet["tpage"]), int(packet["clut"]), int(step[1]))
			var list: Array = result[step[0]]
			if list.is_empty() or list[-1]["key"] != key:
				list.append({"key": key, "texture": texture, "points": PackedVector2Array(), "colors": PackedColorArray(), "uvs": PackedVector2Array(), "indices": PackedInt32Array()})
			var batch: Dictionary = list[-1]
			for triangle: Array in [[0, 1, 2], [1, 2, 3]] if points.size() == 4 else [[0, 1, 2]]:
				if absf((points[triangle[1]] - points[triangle[0]]).cross(points[triangle[2]] - points[triangle[0]])) < 1.0:
					continue
				var base: int = batch["points"].size()
				for corner: int in triangle:
					batch["points"].append(points[corner])
					batch["colors"].append(colors[corner])
					if textured:
						batch["uvs"].append(packet_uvs[corner] / 256.0)
				batch["indices"].append_array(PackedInt32Array([base, base + 1, base + 2]))
	return result


## Depth tested batches for the records with a world position (run by RunnerSession.render_world), in the level's local coordinates: each packet vertex is carried back along its camera ray at the depth the original's projection gave that vertex (the frame's depths by screen position; a vertex the projection did not produce, such as the far corners of a billboard, takes the mean of its packet, then the record's own depth), then through the camera matrix to the game's world. Safe off the main thread.
func build_world(data: Dictionary) -> Array:
	var camera: Dictionary = data["camera"]
	var rows: Array = camera["rows"]
	var translation: Vector3 = camera["translation"]
	var projection := float(maxi(int(camera["projection"]), 1))
	var centre: Vector2 = camera["centre"]
	var depths: Dictionary = data["depths"]
	var result := []
	for entry: Dictionary in data["world"]:
		var fallback := -1.0
		if entry.has("position"):
			fallback = (rows[2] as Vector3).dot(entry["position"]) + translation.z
		for packet: Dictionary in entry["packets"]:
			var textured: bool = packet["textured"]
			var translucent: bool = packet["translucent"]
			var abr: int = int(packet["abr"]) if translucent else 0
			var vertices: Array[Vector2] = packet["vertices"]
			var packet_colors: Array[Color] = packet["colors"]
			var packet_uvs: Array[Vector2] = packet["uvs"]
			var vertex_depths := PackedFloat32Array()
			var known := 0.0
			var count := 0
			for vertex in vertices:
				var depth: float = depths.get((int(vertex.x) & 0xFFFF) | ((int(vertex.y) & 0xFFFF) << 16), -1)
				vertex_depths.append(depth)
				if depth >= 1.0:
					known += depth
					count += 1
			var mean := known / count if count > 0 else fallback
			if mean < 1.0:
				continue
			var points := PackedVector3Array()
			for index in vertices.size():
				var depth := vertex_depths[index] if vertex_depths[index] >= 1.0 else mean
				var view := Vector3((vertices[index].x - centre.x) * depth / projection, (vertices[index].y - centre.y) * depth / projection, depth) - translation
				var raw: Vector3 = (rows[0] as Vector3) * view.x + (rows[1] as Vector3) * view.y + (rows[2] as Vector3) * view.z
				points.append(Vector3(-raw.x, -raw.y, raw.z) / 256.0)
			var passes: Array = [[CANVAS[abr], ALL, 1.0]]
			if translucent and textured:
				passes = [[0, SOLID, 1.0], [CANVAS[abr], BLENDED, RATE[abr]]]
			for step: Array in passes:
				var blend: int = step[0] + 1 if step[0] > 0 else int(step[2] < 1.0 or translucent and not textured)
				var key := -1
				var texture: Texture2D = null
				if textured:
					key = int(packet["tpage"]) | (int(packet["clut"]) << 16) | (int(step[1]) << 28)
					texture = _texture(int(packet["tpage"]), int(packet["clut"]), int(step[1]))
				if result.is_empty() or result[-1]["key"] != key or result[-1]["blend"] != blend:
					result.append({"key": key, "blend": blend, "texture": texture, "positions": PackedVector3Array(), "colors": PackedColorArray(), "uvs": PackedVector2Array(), "indices": PackedInt32Array()})
				var batch: Dictionary = result[-1]
				for triangle: Array in [[0, 1, 2], [1, 2, 3]] if points.size() == 4 else [[0, 1, 2]]:
					if absf((vertices[triangle[1]] - vertices[triangle[0]]).cross(vertices[triangle[2]] - vertices[triangle[0]])) < 1.0:
						continue
					var base: int = batch["positions"].size()
					for corner: int in triangle:
						batch["positions"].append(points[corner])
						var color := packet_colors[corner]
						batch["colors"].append(Color(minf(color.r * 2.0, 1.0), minf(color.g * 2.0, 1.0), minf(color.b * 2.0, 1.0), step[2]) if textured else Color(color.r, color.g, color.b, RATE[abr] if translucent else 1.0))
						if textured:
							batch["uvs"].append(packet_uvs[corner] / 256.0)
					batch["indices"].append_array(PackedInt32Array([base, base + 1, base + 2]))
	return result


## Shows the batches of build_world under the level's transform; the mesh instances are reused from frame to frame.
func show_world(built: Array, level: Transform3D) -> void:
	world.global_transform = level
	for index in built.size():
		if index == instances.size():
			var added := MeshInstance3D.new()
			added.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			world.add_child(added)
			instances.append(added)
		var batch: Dictionary = built[index]
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = batch["positions"]
		arrays[Mesh.ARRAY_COLOR] = batch["colors"]
		if batch["texture"] != null:
			arrays[Mesh.ARRAY_TEX_UV] = batch["uvs"]
		arrays[Mesh.ARRAY_INDEX] = batch["indices"]
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		instances[index].mesh = mesh
		instances[index].material_override = _material(batch)
		instances[index].visible = true
	for index in range(built.size(), instances.size()):
		instances[index].visible = false


## Opaque (alpha tested texels, writes depth), the 0.5 mix, add and subtract blends (read depth only).
func _material(batch: Dictionary) -> StandardMaterial3D:
	var texture: Texture2D = batch["texture"]
	var blend: int = batch["blend"]
	var key := int(batch["key"]) * 8 + blend
	if materials.has(key):
		return materials[key]
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.vertex_color_is_srgb = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.disable_fog = true
	material.albedo_texture = texture
	if blend == 0:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR if texture != null else BaseMaterial3D.TRANSPARENCY_DISABLED
	else:
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		material.blend_mode = [BaseMaterial3D.BLEND_MODE_MIX, BaseMaterial3D.BLEND_MODE_MIX, BaseMaterial3D.BLEND_MODE_ADD, BaseMaterial3D.BLEND_MODE_SUB][blend]
	materials[key] = material
	return material


func show_batches(built: Array) -> void:
	batches = built
	for canvas in canvases:
		canvas.queue_redraw()


func _draw_mode(canvas: Control, mode: int) -> void:
	for batch: Dictionary in batches[mode]:
		var texture: Texture2D = batch["texture"]
		RenderingServer.canvas_item_add_triangle_array(canvas.get_canvas_item(), batch["indices"], batch["points"], batch["colors"], batch["uvs"], PackedInt32Array(), PackedFloat32Array(), texture.get_rid() if texture != null else RID())


func _texture(tpage: int, clut: int, kind: int) -> Texture2D:
	var key := tpage | (clut << 16) | (kind << 28)
	if textures.has(key):
		return textures[key]
	var base_x := (tpage & 15) * 64
	var base_y := ((tpage >> 4) & 1) * 256
	var depth := (tpage >> 7) & 3
	var palette_x := (clut & 63) * 16
	var palette_y := clut >> 6
	var data := PackedByteArray()
	data.resize(256 * 256 * 4)
	for v in 256:
		var row := ((base_y + v) * VRAM_WIDTH + base_x) * 2
		for u in 256:
			var word := 0
			if depth == 0:
				var index := (vram.decode_u16(row + (u >> 2) * 2) >> ((u & 3) * 4)) & 15
				word = vram.decode_u16(((palette_y * VRAM_WIDTH) + palette_x + index) * 2)
			elif depth == 1:
				var index := (vram.decode_u16(row + (u >> 1) * 2) >> ((u & 1) * 8)) & 255
				word = vram.decode_u16(((palette_y * VRAM_WIDTH) + palette_x + index) * 2)
			else:
				word = vram.decode_u16(row + u * 2) if base_x + u < VRAM_WIDTH else 0
			var offset := (v * 256 + u) * 4
			if word != 0 and (kind == ALL or kind == BLENDED == (word & 0x8000 != 0)):
				data[offset] = (word & 31) << 3
				data[offset + 1] = ((word >> 5) & 31) << 3
				data[offset + 2] = ((word >> 10) & 31) << 3
				data[offset + 3] = 255
	var texture := ImageTexture.create_from_image(Image.create_from_data(256, 256, false, Image.FORMAT_RGBA8, data))
	textures[key] = texture
	return texture
