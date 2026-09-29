extends Control
var manifest: Dictionary = {}
var emitters: Array = []
var fields: Array = []
var texture_cache: Dictionary = {}
var bound_context: Dictionary = {}
var texture: Texture2D
var camera: Camera3D
var previous_position := Vector3i.ZERO
var previous_angles := Vector2i.ZERO
var accumulator := 0.0
var rng_state := 0
var bound_stage := ""
var bound_area := -1
var bound_path := ""
func _enter_tree() -> void:
	set_process(not manifest.is_empty() and visible)
func configure(stage: String, area: int, target_camera: Camera3D, native_context: Dictionary = {}, path: String = "res://assets/weather/manifest.json") -> void:
	if stage == bound_stage and area == bound_area and target_camera == camera and path == bound_path and native_context == bound_context and not manifest.is_empty(): return
	set_process(false)
	if path != bound_path: manifest.clear(); texture_cache.clear()
	bound_stage = stage
	bound_area = area
	bound_path = path
	bound_context = native_context.duplicate(true)
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	camera = target_camera
	if manifest.is_empty():
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		var tick_rate: Variant = data.get("tick_rate") if data is Dictionary else null
		if not (tick_rate is int or tick_rate is float) or not is_finite(float(tick_rate)) or float(tick_rate) <= 0.0: hide(); push_error("Invalid native weather tick rate: " + path); return
		manifest = data
		var texture_path := path.get_base_dir().path_join(str(manifest["texture"]))
		if FileAccess.file_exists(texture_path + ".import"): texture = load(texture_path) as Texture2D
		else:
			var image := Image.load_from_file(texture_path)
			if image != null and not image.is_empty(): texture = ImageTexture.create_from_image(image)
		var additive := CanvasItemMaterial.new()
		additive.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		material = additive
	emitters.clear()
	fields.clear()
	accumulator = 0.0
	for record: Dictionary in manifest.get("stages", {}).get(stage, {}).get("areas", {}).get(str(area), []):
		var points: Array = []
		points.resize(int(manifest["particle_count"]))
		var period := int(record["period_ticks"])
		emitters.append({"record": record, "points": points, "draw": [], "phase": 0, "timer": (period + ((_random() & 65535) % period)) & 255})
	previous_position = _camera_position()
	previous_angles = _camera_angles()
	for record: Dictionary in manifest.get("stages", {}).get(stage, {}).get("fields", {}).get(str(area), []):
		if native_context.get("native_save_byte14", 0) != record.get("gate", {}).get("native_save_byte14", 0): continue
		var profile: Dictionary = manifest.get("profiles", {}).get(str(record["profile_id"]), {})
		if profile.get("renderer_kind", "") != "tiled_field": continue
		var field_texture := _field_texture(path.get_base_dir().path_join(str(profile["texture"])))
		if field_texture == null: continue
		fields.append({"record": record, "profile": profile, "texture": field_texture, "scroll": Vector2i(int(record["initial_scroll_raw"][0]), int(record["initial_scroll_raw"][1])), "draw_scroll": Vector2i.ZERO, "mesh": ArrayMesh.new()})
	visible = (not emitters.is_empty() and texture != null) or not fields.is_empty()
	set_process(visible)
	queue_redraw()
func _field_texture(path: String) -> Texture2D:
	if texture_cache.has(path): return texture_cache[path] as Texture2D
	var result: Texture2D
	if FileAccess.file_exists(path + ".import"): result = load(path) as Texture2D
	else:
		var image := Image.load_from_file(path)
		if image != null and not image.is_empty(): result = ImageTexture.create_from_image(image)
	texture_cache[path] = result
	return result
func _random() -> int:
	rng_state = (((rng_state << 1) + (rng_state >> 31) + 1) ^ 0x873CA9E5) & 0xFFFFFFFF
	return rng_state
func _short(value: int) -> int:
	return (value & 32767) - (value & 32768)
func _remainder(value: int, divisor: int) -> int:
	return value - int(float(value) / divisor) * divisor
func _camera_position() -> Vector3i:
	if not is_instance_valid(camera): return previous_position
	var point := camera.global_position
	return Vector3i(_short(floori(-point.x * 256)), _short(floori(-point.y * 256)), _short(floori(point.z * 256)))
func _camera_angles() -> Vector2i:
	if not is_instance_valid(camera): return previous_angles
	return Vector2i(floori(camera.global_rotation.x * 4096 / TAU) & 4095, floori((PI - camera.global_rotation.y) * 4096 / TAU) & 4095)
func _trig(angle: int, cosine: bool = false) -> int:
	return int(manifest["trig4096"][angle & 4095][1 if cosine else 0])
func _process(delta: float) -> void:
	if manifest.is_empty(): set_process(false); return
	accumulator += delta
	var interval := 1.0 / float(manifest["tick_rate"])
	if accumulator < interval: return
	accumulator = fmod(accumulator, interval)
	_tick()
	queue_redraw()
func _tick() -> void:
	var position := _camera_position()
	var angles := _camera_angles()
	var displacement := previous_position - position
	var yaw_sine := _trig(angles.y)
	var yaw_cosine := _trig(angles.y, true)
	var pitch_sine := _trig(angles.x)
	var pitch_cosine := _trig(angles.x, true)
	var yaw_change := _trig(previous_angles.y - angles.y)
	var pitch_change := _trig(previous_angles.x - angles.x)
	for emitter: Dictionary in emitters:
		var record: Dictionary = emitter["record"]
		var wind: Array = record["wind_raw"]
		var dx := _short(displacement.x + int(wind[0]))
		var dy := _short(displacement.y + int(wind[1]))
		var dz := _short(displacement.z + int(wind[2]))
		var sideways := (dx * yaw_cosine - dz * yaw_sine) >> 13
		var forward := _short((dx * yaw_sine + dz * yaw_cosine) >> 12)
		var vertical := (dy * pitch_cosine + forward * pitch_sine) >> 12
		var depth_change := _short((forward * pitch_cosine - dy * pitch_sine * 2) >> 12)
		var jitter := _short(_random())
		var points: Array = emitter["points"]
		emitter["draw"] = []
		for index in range(points.size() - 1, -1, -1):
			if points[index] == null: continue
			var point: Vector3i = points[index]
			var yaw_drift := (point.z * yaw_change) >> 13
			var edge_drift := -absi((point.z * yaw_change) >> 13)
			var horizontal := _short(sideways - ((point.x * _short(depth_change)) >> 10) - 1 + _remainder(jitter >> index, 3))
			var vertical_rotation := _short(vertical + (((180 - point.y) * _short(depth_change)) >> 10))
			var x := _short(point.x + yaw_drift + ((horizontal * (2048 - point.z)) >> 11))
			var y := _short(point.y + ((edge_drift * pitch_sine - point.z * pitch_change) >> 12) + ((vertical_rotation * (2048 - point.z)) >> 11))
			var z := _short(point.z + depth_change)
			var wrapped := _wrap(Vector3i(x, y, z), depth_change)
			emitter["draw"].append(wrapped)
			points[index] = Vector3i(((wrapped.x + 180) & 511) - 180, wrapped.y & 511, wrapped.z & 1023)
		_fill(emitter)
	for field: Dictionary in fields: _tick_field(field, angles)
	previous_position = position
	previous_angles = angles
func _tick_field(field: Dictionary, angles: Vector2i) -> void:
	var profile: Dictionary = field["profile"]
	var descriptor: Array = profile["descriptor"]
	var parameter := int(profile["parameter"])
	var scroll: Vector2i = field["scroll"]
	scroll.x = _short(scroll.x + (-int(descriptor[2]) if parameter & 1 else int(descriptor[2])))
	scroll.y = _short(scroll.y + (-int(descriptor[3]) if parameter & 2 else int(descriptor[3])))
	field["scroll"] = scroll
	var screen := Vector2i((scroll.x >> 4) + _short(angles.y), (scroll.y >> 4) + _short(angles.x))
	field["draw_scroll"] = screen
	var vertices := PackedVector3Array()
	var colors := PackedColorArray()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var count := int(profile["tile_pixels"])
	for row in range(int(profile["rows"])):
		for column in range(int(profile["columns"])):
			var x := column * count - (screen.x & 31)
			var y := row * count - (screen.y & 31)
			var source_x := screen.x + column * count
			var source_y := screen.y + row * count
			var u := ((~source_x if parameter & 1 else source_x) & 96)
			var v := ((96 - (source_y & 96)) if parameter & 2 else (source_y & 96))
			var first := vertices.size()
			for offset: Vector2i in [Vector2i.ZERO, Vector2i(count, 0), Vector2i(0, count), Vector2i(count, count)]:
				vertices.append(Vector3(x + offset.x, y + offset.y, 0))
				var brightness := float(((int(descriptor[0]) + ((_trig(source_x + source_y + offset.x + offset.y) * int(descriptor[1])) >> 12)) & 255)) / 128.0
				colors.append(Color(brightness, brightness, brightness))
				uvs.append(Vector2(u + (31 - offset.x * 31 / count if parameter & 1 else offset.x * 31 / count), v + (31 - offset.y * 31 / count if parameter & 2 else offset.y * 31 / count)) / 128.0)
			indices.append_array(PackedInt32Array([first, first + 1, first + 2, first + 1, first + 2, first + 3]))
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh: ArrayMesh = field["mesh"]
	mesh.clear_surfaces()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
func _fill(emitter: Dictionary) -> void:
	var points: Array = emitter["points"]
	var period := int(emitter["record"]["period_ticks"])
	if int(emitter["phase"]) == 0 and bool(emitter["record"]["prewarm"]):
		for index in range(points.size() - 1, -1, -1): points[index] = Vector3i((_random() & 65535) % 360 - 180, (_random() & 65535) % 280, (_random() & 65535) % 824 + 200)
		emitter["phase"] = 2
	elif int(emitter["phase"]) in [0, 1]:
		emitter["phase"] = 1
		emitter["timer"] = (int(emitter["timer"]) - 1) & 255
		if int(emitter["timer"]) != 255: return
		for index in range(points.size() - 1, -1, -1):
			if points[index] == null: points[index] = Vector3i((_random() & 65535) % 360 - 180, 0, (_random() & 65535) % 824 + 200); break
		emitter["timer"] = (period + ((_random() & 65535) % period)) & 255
		if not points.has(null): emitter["phase"] = 2
func _wrap(point: Vector3i, depth_change: int) -> Vector3i:
	if (point.z & 65535) > 1024:
		var selector := 1 if depth_change <= 0 else _random()
		if selector & 1: return Vector3i((_random() & 65535) % 360 - 180, (_random() & 65535) % 280, point.z & 1023)
		if selector & 16: point.x = (_random() & 65535) % 360 - 180; point.y = 10 if selector & 64 else 270
		else: point.x = -170 if selector & 64 else 170; point.y = (_random() & 65535) % 280
		point.z = _random() & 1023
		return point
	if (point.y & 65535) > 280: return Vector3i((_random() & 65535) % 360 - 180, (_random() & 65535) % 280, (point.z + 1536) & 1023)
	if ((point.x + 180) & 65535) > 360:
		var selector := _random()
		if selector & 7: point.y = _remainder(_short(selector) >> 3, 280); point.x = _remainder(point.x + 540, 360) - 180
		else: point.y = 10; point.x = _remainder(_short(selector) >> 3, 360) - 180; point.z = _random() & 1023
	return point
func _draw() -> void:
	if size.y <= 0: return
	var scale_y := size.y / 240.0
	var scale_x := size.x / 320.0
	for field: Dictionary in fields: draw_mesh(field["mesh"], field["texture"], Transform2D(Vector2(scale_x, 0), Vector2(0, scale_y), Vector2.ZERO))
	if texture == null: return
	for emitter: Dictionary in emitters:
		for point: Vector3i in emitter["draw"]:
			if point.z < 100: continue
			var width := (1 + ((1024 - point.z) >> 8)) * scale_y
			var brightness := float((64 + (point.z >> 3)) & 255) / 128.0
			draw_texture_rect(texture, Rect2(Vector2((point.x + 160) * scale_x, (point.y - 20) * scale_y), Vector2.ONE * width), false, Color(brightness, brightness, brightness))
