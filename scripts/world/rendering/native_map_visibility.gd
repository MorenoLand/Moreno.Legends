extends Node
static var trig: Array = []
var source: Node3D
var parameters: Dictionary
var surfaces: Array[Dictionary] = []
var texture: ImageTexture
var previous: Array = []
var last_pixels := PackedByteArray()
var last_world := Transform3D()
var last_materials: Array = []
var last_visible: Array = []
static var palette_meshes: Dictionary = {}
func configure(map_root: Node3D, profile: Dictionary) -> void:
	process_mode = Node.PROCESS_MODE_PAUSABLE
	source = map_root; parameters = profile
	if trig.is_empty(): trig = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/visibility_math.json"))["trig4096"]
	var pixels := PackedByteArray(); pixels.resize(128 * 128); texture = ImageTexture.create_from_image(Image.create_from_data(128, 128, false, Image.FORMAT_L8, pixels))
	for mesh: MeshInstance3D in source.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or (mesh.name != "terrain" and not str(mesh.name).begins_with("placement_")): continue
		var placement := int(str(mesh.name).get_slice("_", 1)) if mesh.name != "terrain" else -1
		var palette: Dictionary = parameters.get("palette_fog", {})
		if palette.get("enabled", false):
			var disabled: Array = []
			for cell: Array in palette.get("terrain_disabled_cells", []): disabled.append(Vector2i(int(cell[0]), int(cell[1])))
			mesh.mesh = _quad_mesh(mesh.mesh, placement < 0, disabled)
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null: continue
			if palette.get("enabled", false) and palette["atlases"].has(material.resource_name):
				var atlas_path: String = str(palette["directory"]).path_join(str(palette["atlases"][material.resource_name])); var table := PackedInt32Array(); var variants := PackedInt32Array(palette["variants"])
				for offset: int in palette["offsets"]: table.append(variants.find(offset))
				material.set_shader_parameter("native_palette_enabled", true); material.set_shader_parameter("native_palette_atlas", load(atlas_path)); material.set_shader_parameter("native_palette_layers", palette["variants"].size()); material.set_shader_parameter("native_palette_offsets", table); material.set_shader_parameter("native_palette_bucket_shift", int(palette["bucket_shift"])); material.set_shader_parameter("native_depth_cue_shift", int(parameters["depth_shift"]))
			material.set_shader_parameter("native_map_cells", texture); material.set_shader_parameter("native_map_world_to_local", source.global_transform.affine_inverse()); material.set_shader_parameter("native_map_terrain", placement < 0); surfaces.append({"mesh": mesh, "surface": surface, "placement": placement, "cells": _placement_cells(placement)}); last_materials.append(material); last_visible.append(-1)
	_process(0.0)
func _process(_delta: float) -> void:
	if not is_instance_valid(source) or not source.is_visible_in_tree(): return
	var camera := get_viewport().get_camera_3d()
	if camera == null: return
	var local := source.to_local(camera.global_position); var forward := source.global_basis.inverse() * -camera.global_basis.z
	var position := Vector3i(roundi(-local.x * 256), roundi(-local.y * 256), roundi(local.z * 256)); var yaw := roundi(atan2(-forward.x, forward.z) * 4096.0 / TAU) & 4095; var pitch := roundi(asin(clampf(forward.y, -1, 1)) * 4096.0 / TAU) & 4095
	var projection := camera.get_camera_projection(); var lens_scale := maxf(1.0, 256.0 / (106.0 * absf(projection.x.x)))
	var current := [position, yaw, pitch, camera.global_transform, source.global_transform, lens_scale]
	if current == previous: return
	previous = current
	var visibility: Dictionary = parameters["visibility"]; var bounds: Array = visibility["window"]["grid_bounds"]; var pixels := window_cells(position, pitch, yaw, bounds); var near := near_square(position, pitch, bounds)
	var to_view := camera.global_transform.affine_inverse() * source.global_transform; var base_y := -(position.y + (int(trig[(-pitch) & 4095][0]) * (int(visibility["tile_range"]) + 1) >> 4)) / 256.0; var depth_limit := int(visibility["map_cell_ot_depth_limit"]); var has_near := near.size.x > 0 and near.size.y > 0
	for z in range(int(bounds[1]), int(bounds[3]) + 1):
		for x in range(int(bounds[0]), int(bounds[2]) + 1):
			var index := z * 128 + x
			if pixels[index] == 0 and lens_scale <= 1.0: continue
			var view := to_view * Vector3(-(x * 512 - 32512) / 256.0, base_y, (z * 512 - 32512) / 256.0); var depth := floori(-view.z * 256) >> 2; var width := ((maxi(depth, 0) * 106) >> 6) + (600 if has_near and near.has_point(Vector2i(x, z)) else 400)
			var lateral := absf(view.x * 256)
			if pixels[index] == 0 and depth >= 0 and lateral > width and lateral <= width * lens_scale: pixels[index] = 255
			if depth >= depth_limit or lateral > width * lens_scale: pixels[index] = 0
	var world := source.global_transform; var world_changed: bool = world != last_world; var cells_changed: bool = pixels != last_pixels
	if cells_changed: last_pixels = pixels; texture.update(Image.create_from_data(128, 128, false, Image.FORMAT_L8, pixels))
	if world_changed: last_world = world
	for index in surfaces.size():
		var entry: Dictionary = surfaces[index]; var mesh := entry["mesh"] as MeshInstance3D
		if not is_instance_valid(mesh): continue
		var material := mesh.get_active_material(int(entry["surface"])) as ShaderMaterial
		if material == null: continue
		var fresh: bool = material != last_materials[index]
		if fresh: last_materials[index] = material; last_visible[index] = -1; material.set_shader_parameter("native_map_cells", texture); material.set_shader_parameter("native_map_terrain", int(entry["placement"]) < 0)
		if fresh or world_changed: material.set_shader_parameter("native_map_world_to_local", world.affine_inverse())
		if not (fresh or cells_changed): continue
		var visible := int(entry["placement"]) < 0
		if not visible:
			for cell: int in entry["cells"]:
				if pixels[cell] != 0: visible = true; break
		if int(visible) != last_visible[index]: last_visible[index] = int(visible); material.set_shader_parameter("native_map_placement_visible", visible)
func _placement_cells(placement: int) -> PackedInt32Array:
	var cells := PackedInt32Array()
	for point: Array in parameters["visibility"]["placement_cells"].get(str(placement), []):
		var x := (int(point[0]) + 32512) >> 9; var z := (int(point[1]) + 32512) >> 9
		if x >= 0 and x < 128 and z >= 0 and z < 128 and not cells.has(z * 128 + x): cells.append(z * 128 + x)
	return cells
static func _quad_mesh(original: Mesh, terrain: bool, disabled: Array) -> Mesh:
	var key := [original.get_instance_id(), terrain, disabled]
	if palette_meshes.has(key): return palette_meshes[key]
	var replacement := ArrayMesh.new(); replacement.resource_name = original.resource_name
	for surface in original.get_surface_count():
		var arrays: Array = preload("res://scripts/world/core/native_coplanar_overlays.gd")._expanded_arrays(original.surface_get_arrays(surface)); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var channels: Array[PackedFloat32Array] = [PackedFloat32Array(), PackedFloat32Array(), PackedFloat32Array(), PackedFloat32Array()]
		if vertices.size() % 6 != 0: push_error("Native map quad triangle stream is incomplete"); return original
		for start in range(0, vertices.size(), 6):
			var center := (vertices[start] + vertices[start + 1] + vertices[start + 2] + vertices[start + 5]) * 0.25; var cell := Vector2i(floori((-center.x * 256 + 32768) / 512), floori((center.z * 256 + 32768) / 512)); var enabled := 0.0 if terrain and disabled.has(cell) else 1.0
			for vertex in 6:
				for channel in 4: var point := vertices[start + [0, 1, 2, 5][channel]]; channels[channel].append_array(PackedFloat32Array([point.x, point.y, point.z, enabled]))
		for channel in 4: arrays[Mesh.ARRAY_CUSTOM0 + channel] = channels[channel]
		arrays[Mesh.ARRAY_INDEX] = null
		var flags := 0
		for shift in [Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT, Mesh.ARRAY_FORMAT_CUSTOM1_SHIFT, Mesh.ARRAY_FORMAT_CUSTOM2_SHIFT, Mesh.ARRAY_FORMAT_CUSTOM3_SHIFT]: flags |= Mesh.ARRAY_CUSTOM_RGBA_FLOAT << shift
		replacement.add_surface_from_arrays(original.surface_get_primitive_type(surface), arrays, [], {}, flags)
		if replacement.get_surface_count() != surface + 1: push_error("Native palette quad attributes could not be created"); return original
		replacement.surface_set_material(surface, original.surface_get_material(surface)); replacement.surface_set_name(surface, original.surface_get_name(surface))
	for name: StringName in original.get_meta_list(): replacement.set_meta(name, original.get_meta(name))
	palette_meshes[key] = replacement; return replacement
static func near_square(position: Vector3i, pitch: int, bounds: Array) -> Rect2i:
	var radius := absi(int(int(trig[pitch][0]) / 384)); var x := int((position.x + 256) / 512) + 64; var z := int((position.z + 256) / 512) + 64
	var minimum := Vector2i(maxi(x - radius - 3, bounds[0]), maxi(z - radius - 3, bounds[1])); var maximum := Vector2i(mini(x + radius + 3, bounds[2]), mini(z + radius + 3, bounds[3])); return Rect2i(minimum, maximum - minimum + Vector2i.ONE)
static func window_cells(position: Vector3i, pitch: int, yaw: int, bounds: Array) -> PackedByteArray:
	var pixels := PackedByteArray(); pixels.resize(128 * 128); var near := near_square(position, pitch, bounds)
	for z in range(near.position.y, near.end.y):
		for x in range(near.position.x, near.end.x): pixels[z * 128 + x] = 255
	var sin_yaw := clampi(int(trig[yaw][0]), -4095, 4095); var cos_yaw := clampi(int(trig[yaw][1]), -4095, 4095); var cos_pitch := absi(int(trig[pitch][1])); var center := Vector2i(int((position.x + int(sin_yaw * cos_pitch * 2 / 4096)) / 512) + 64, int((position.z + int(cos_yaw * cos_pitch * 2 / 4096)) / 512) + 64); var radius := cos_pitch >> 8
	var minimum := Vector2i(maxi(center.x - radius, bounds[0]), maxi(center.y - radius, bounds[1])); var maximum := Vector2i(mini(center.x + radius, bounds[2]), mini(center.y + radius, bounds[3])); var z_rows := ((yaw - 512) & 1024) != 0; var negative := ((yaw - 512) & 2048) != 0
	var slopes := PackedInt32Array()
	for angle in [(yaw - 256) & 4095, (yaw + 256) & 4095]:
		var numerator := int(trig[angle][0 if z_rows else 1]) + 1; var denominator := -(int(trig[angle][1 if z_rows else 0]) + 1); var value := int(numerator * 4096 / denominator) & 65535; slopes.append(value - 65536 if value >= 32768 else value)
	var low := slopes[0] if negative else slopes[1]; var high := slopes[1] if negative else slopes[0]
	var row_min := minimum.y if z_rows else minimum.x; var row_max := maximum.y if z_rows else maximum.x; var other_min := minimum.x if z_rows else minimum.y; var other_max := maximum.x if z_rows else maximum.y; var axis := position.z if z_rows else position.x; var other := position.x if z_rows else position.z
	var delta := int((axis + 256) / 512) - row_min + ((62 if negative else 65) if z_rows else (65 if negative else 62)); var base := int((other + 256) / 512)
	for row in range(row_min, row_max + 1):
		var start := base + int(delta * low / 4096) + 61; var finish := base + int(delta * high / 4096) + 66
		if start < other_min or start > other_max: start = other_min
		if finish < other_min or finish > other_max: finish = other_max
		for column in range(start, finish + 1):
			var x := column if z_rows else row; var z := row if z_rows else column; pixels[z * 128 + x] = 255
		delta -= 1
	return pixels
