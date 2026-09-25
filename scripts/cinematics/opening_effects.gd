extends Node
class DrawSurface extends Node2D:
	var renderer: Node
	var flash := false
	func _draw() -> void:
		if flash: renderer._draw_lightning(self)
		else: renderer._draw_atmosphere(self)
var camera: Camera3D
var data: Dictionary = {}
var bank := "ST02"
var actors: Array[Dictionary] = []
var background: DrawSurface
var flashes: DrawSurface
var texture_cache: Dictionary = {}
func configure(view_camera: Camera3D, manifest: Dictionary) -> bool:
	camera = view_camera
	var path: String = str(manifest.get("effects", "res://assets/opening/effects/manifest.json"))
	if not FileAccess.file_exists(path): return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary: return false
	data = parsed
	for kind: String in data.get("supported_variants", {}):
		var variants: Array = data["supported_variants"][kind]
		for index: int in range(variants.size()): variants[index] = int(variants[index])
	var back_layer := CanvasLayer.new(); back_layer.layer = -1; add_child(back_layer)
	background = DrawSurface.new(); background.renderer = self; background.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; back_layer.add_child(background)
	var flash_layer := CanvasLayer.new(); flash_layer.layer = 1; add_child(flash_layer)
	flashes = DrawSurface.new(); flashes.renderer = self; flashes.flash = true; flash_layer.add_child(flashes)
	var additive := CanvasItemMaterial.new(); additive.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD; flashes.material = additive
	return true
func set_bank(value: String) -> void:
	if not data.get("texture_banks", {}).has(value): return
	bank = value
	for actor: Dictionary in actors:
		if int(actor["class"]) == 18 and int(actor["variant"]) in [0, 1, 2]: _cloud_materials(actor)
func spawn(variant: int, params: Dictionary) -> void:
	var kind: int = int(params.get("class", 18)); var slot: int = int(params.get("slot", -1))
	if slot >= 0: remove(slot)
	if not variant in data.get("supported_variants", {}).get("class%d" % kind, []): return
	var actor: Dictionary = {"class": kind, "variant": variant, "slot": slot, "parameter": int(params.get("parameter", 0)), "source": Vector3(float(params.get("x", 0)), float(params.get("y", 0)), float(params.get("z", 0))), "age": 0, "phases": [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 0], "meshes": []}
	actors.append(actor)
	if kind == 14: actor["age"] = -1
	if kind == 18 and variant in [0, 1, 2]:
		var profile: Dictionary = data["clouds"]["variant%d" % variant]
		for index: int in range(profile["height"].size()):
			var instance := MeshInstance3D.new(); instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; camera.get_parent().add_child(instance); actor["meshes"].append(instance)
		_cloud_materials(actor)
		if variant == 0:
			var companion: Dictionary = params.duplicate(); companion["slot"] = -1; spawn(1, companion)
	if kind == 18 and variant == 6:
		var instance := MeshInstance3D.new(); instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; var mesh := ImmediateMesh.new(); var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.albedo_color = Color(192.0 / 255.0, 240.0 / 255.0, 192.0 / 255.0, 0.5)
		mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, material)
		for index: int in [0, 1, 2, 2, 1, 3]:
			var vertex: Array = data["variant6_vertices"][index]; mesh.surface_add_vertex(_world(Vector3(float(vertex[0]), float(vertex[1]), float(vertex[2]))))
		mesh.surface_end(); instance.mesh = mesh; camera.get_parent().add_child(instance); actor["meshes"].append(instance)
func remove(slot: int) -> void:
	for index: int in range(actors.size() - 1, -1, -1):
		if int(actors[index]["slot"]) == slot: _remove_actor(index)
func _remove_actor(index: int) -> void:
	for instance: MeshInstance3D in actors[index]["meshes"]: instance.queue_free()
	actors.remove_at(index)
func native_tick() -> void:
	if data.is_empty() or not is_instance_valid(camera): return
	var yaw_delta: int = int(camera.get_meta("native_yaw_previous", 0)) - int(camera.get_meta("native_yaw_current", 0))
	for index: int in range(actors.size() - 1, -1, -1):
		var actor: Dictionary = actors[index]; var variant: int = int(actor["variant"]); var phases: Array = actor["phases"]
		if int(actor["class"]) == 14:
			actor["age"] = int(actor["age"]) + 1
			if int(actor["age"]) > 7: _remove_actor(index)
			continue
		if variant in [0, 1, 2]:
			for ring: int in range(actor["meshes"].size()): phases[ring] = _s16(int(phases[ring]) - (8 if variant == 1 else 6) - ring) % 4096
			_draw_cloud_meshes(actor)
		elif variant in [3, 5]:
			phases[1] = _s16(int(phases[1]) + yaw_delta * 8 + 1)
			if int(phases[1]) >= 4096: phases[1] = 0
			if variant == 3:
				phases[2] = _s16(int(phases[2]) + 1 - yaw_delta * 2)
				if int(phases[2]) >= 1024: phases[2] = 0
		elif variant == 4:
			for phase: int in [0, 1, 2]:
				var limit: int = 512 if phase == 2 else 1024
				var before: int = _s16(int(phases[phase])); phases[phase] = _s16(before + 1) if before < limit else 0
	background.queue_redraw(); flashes.queue_redraw()
func _s16(value: int) -> int: return (value & 32767) - (value & 32768)
func _world(value: Vector3) -> Vector3: return Vector3(-value.x, -value.y, value.z) / 256.0
func _view(value: Vector3) -> Vector3:
	var local: Vector3 = camera.to_local(_world(value)); return Vector3(local.x, -local.y, -local.z) * 256.0
func _project(value: Vector3) -> Vector2:
	var offset: Vector2 = camera.get_meta("screen_offset", Vector2(160, 120)); var h: float = float(camera.get_meta("projection_h", 120.0 / tan(deg_to_rad(camera.fov) * 0.5)))
	return Vector2(floor(offset.x + value.x * h / value.z), floor(offset.y + value.y * h / value.z))
func _texture(path: String) -> Texture2D:
	if not texture_cache.has(path): texture_cache[path] = load(path)
	return texture_cache[path] as Texture2D
func _atlas(actor: Dictionary, index: int, alternate: bool = false) -> Texture2D:
	var entry: Dictionary = data["texture_banks"][bank]["textures"][index]; return _texture(str(entry["alternate" if alternate else "primary"]["texture"]))
func _cloud_materials(actor: Dictionary) -> void:
	var profile: Dictionary = data["clouds"]["variant%d" % int(actor["variant"])]; var alternate: int = 8 if int(actor["variant"]) == 2 and (int(actor["parameter"]) & 255) == 0 else 0
	for index: int in range(actor["meshes"].size()):
		var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.albedo_texture = _texture(str(data["texture_banks"][bank]["cloud_palettes"][str(alternate + (int(profile["clut_offset"][index]) >> 4))])); actor["meshes"][index].material_override = material
func _draw_cloud_meshes(actor: Dictionary) -> void:
	var variant: int = int(actor["variant"]); var profile: Dictionary = data["clouds"]["variant%d" % variant]; var source: Vector3 = actor["source"]; var yaw: int = int(camera.get_meta("native_yaw_current", 0)); var trig: Array = data["trig4096"]; var small: Array = data["trig64"]
	for ring: int in range(actor["meshes"].size()):
		var mesh := ImmediateMesh.new(); var begun := false
		var width: int = int(profile["half_size"][ring]); var a: int = (width * int(small[24][1])) >> 12; var b: int = (width * int(small[24][0])) >> 12
		for item: int in range(8 if variant == 1 else 32):
			var angle: int = (int(actor["phases"][ring]) + item * 128) % 4096; var reference: int = 3072 - yaw if variant != 2 else 4096 - angle; var distance: int = ((angle - reference + 2048) & 4095) - 2048 if variant != 2 else (((yaw + 1024) - reference + 2048) & 4095) - 2048
			if abs(distance) >= (1225 if variant != 2 else 674): continue
			var radius: int = int(profile["radius"][ring]) + ((int(profile["radius_jitter"][item]) >> 3) - 32 if variant == 1 else 0)
			var center := Vector3(_s16(int(source.x) + ((radius * int(trig[angle & 4095][1])) >> 12)), _s16(int(source.y) + int(profile["height"][ring]) + ((int(small[(ring + item * 2) & 63][0]) >> 8) if variant != 2 else 0)), _s16(int(source.z) + ((radius * int(trig[angle & 4095][0])) >> 12)))
			if _view(center).z < 48.0: continue
			if not begun: mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES); begun = true
			var offsets: Array[Vector2] = [Vector2(-a, -b), Vector2(-b, a), Vector2(b, -a), Vector2(a, b)]; var u: int = int(profile["uv_x"][item & 7]); var uv: Array[Vector2] = [Vector2(u, 128), Vector2(u + 63, 128), Vector2(u, 191), Vector2(u + 63, 191)]
			for corner: int in [0, 1, 2, 2, 1, 3]: mesh.surface_set_uv(uv[corner] / 256.0); mesh.surface_add_vertex(_world(center) + camera.global_basis * Vector3(offsets[corner].x, -offsets[corner].y, 0.0) / 256.0)
		if begun: mesh.surface_end()
		actor["meshes"][ring].mesh = mesh
func _draw_atmosphere(surface: Node2D) -> void:
	for actor: Dictionary in actors:
		if int(actor["class"]) != 18: continue
		var variant: int = int(actor["variant"])
		if not variant in [3, 4, 5]: continue
		var parameter: int = int(actor["parameter"]); var atlas: Texture2D = _atlas(actor, (parameter >> 24) & 255, (parameter & 255) == 0 and variant != 4); var phases: Array = actor["phases"]; var rows: Array = data["screen_atmosphere"]["variant%d_rows" % variant]; var y_base: int = 80 if variant == 4 else 0; var bg_atlas: Texture2D = _atlas(actor, (parameter >> 16) & 255) if variant == 4 else atlas
		for row: int in range(rows.size()):
			var y: int = y_base + row * 16
			for column: int in range(20): surface.draw_texture_rect_region(bg_atlas, Rect2(column * 16, y, 16, 16), Rect2(int(rows[rows.size() - 1 - row]), 0 if variant == 4 else 224, 16, 16))
		if variant in [3, 5]:
			var shifted: int = int(phases[1]) >> 4; var fine: int = shifted & 31; var coarse: int = shifted >> 5
			for column: int in range(11): surface.draw_texture_rect_region(atlas, Rect2(column * 32 + fine - 32, 160 if variant == 5 else 80, 32, 80 if variant == 5 else 160), Rect2(((column - coarse) * 32) & 224, 0, 32, 80 if variant == 5 else 160))
			if variant == 3:
				shifted = int(phases[2]) >> 2; fine = shifted & 31; coarse = shifted >> 5
				for column: int in range(11): surface.draw_texture_rect_region(atlas, Rect2(column * 32 - fine, 176, 32, 64), Rect2(((column + coarse) * 32) & 224, 160, 32, 64))
		else:
			var shifted: int = int(phases[0]) >> 2; var fine: int = shifted & 31; var coarse: int = shifted >> 5
			for y: int in range(160, 240, 16):
				for column: int in range(11): surface.draw_texture_rect_region(atlas, Rect2(column * 32 - fine, y, 32, 16), Rect2(((column + coarse) * 32) & 96, y - 144, 32, 16))
			shifted = int(phases[1]) >> 2; fine = shifted & 31; coarse = shifted >> 5
			for y: int in range(16, 96, 16):
				for column: int in range(11): surface.draw_texture_rect_region(atlas, Rect2(column * 32 + fine - 32, y, 32, 16), Rect2(((column - coarse) * 32) & 224, y + 32, 32, 16))
			shifted = int(phases[2]) >> 1; fine = shifted & 31; coarse = shifted >> 5
			for y: int in range(0, 96, 16):
				for column: int in range(11): surface.draw_texture_rect_region(atlas, Rect2(column * 32 - fine, y, 32, 16), Rect2(((column + coarse) * 32) & 224, y + 160, 32, 16))
func _draw_lightning(surface: Node2D) -> void:
	var trig: Array = data["trig64"]
	for actor: Dictionary in actors:
		if int(actor["class"]) != 14 or int(actor["age"]) < 1: continue
		var center: Vector3 = _view(actor["source"]) if int(actor["variant"]) == 2 else Vector3(0, 0, 192)
		if center.z <= 0.0: continue
		var radius: int = int(center.z * 5.0 / 6.0) & 65535; var brightness: int = int(data["lightning"]["colors"][int(actor["age"]) - 1][0]); var color := Color(float(brightness) / 255.0, float(brightness) / 255.0, float(brightness) / 255.0)
		for segment: int in range(16):
			var first: int = segment * 4; var second: int = ((segment + 1) * 4) & 63; var start := Vector3(center.x + ((radius * int(trig[first][1])) >> 12), center.y + ((radius * int(trig[first][0])) >> 12), center.z); var end := Vector3(center.x + ((radius * int(trig[second][1])) >> 12), center.y + ((radius * int(trig[second][0])) >> 12), center.z)
			surface.draw_polygon(PackedVector2Array([_project(start), _project(center), _project(end)]), PackedColorArray([Color(0, 0, 0), color, Color(0, 0, 0)]))
func _exit_tree() -> void:
	for actor: Dictionary in actors:
		for instance: MeshInstance3D in actor["meshes"]:
			if is_instance_valid(instance): instance.queue_free()
