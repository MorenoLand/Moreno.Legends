@tool
extends RefCounted
static var lighting_cache: Dictionary = {}
static var stream_cache: Dictionary = {}
static func area_parameters(path: String, area: int) -> Dictionary:
	if not lighting_cache.has(path):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		lighting_cache[path] = data if data is Dictionary else {}
	for parameters: Dictionary in lighting_cache[path].get("native_color_pipeline", {}).get("depth_cue", {}).get("area_parameters", []):
		if int(parameters.get("area", -1)) == area: return parameters
	return {}
static func apply(root: Node3D, color_scale: float = 255.0) -> void:
	_stream_defaults(root)
	preload("res://scripts/world/core/native_coplanar_overlays.gd").apply(root)
	var nodes: Array[Node] = root.find_children("*", "MeshInstance3D", true, false)
	if root is MeshInstance3D: nodes.push_front(root)
	for node in nodes:
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		for surface in range(mesh.mesh.get_surface_count()):
			var active := mesh.get_active_material(surface) as ShaderMaterial
			if active != null:
				if active.shader == preload("res://shaders/native_model.gdshader"): active.set_shader_parameter("coplanar_overlay_flags", bool(mesh.mesh.get_meta("coplanar_overlays", active.get_shader_parameter("coplanar_overlay_flags"))))
				if mesh.has_meta("native_stream_visibility"): active.set_shader_parameter("hidden_face_range", mesh.get_meta("native_stream_visibility"))
				continue
			var source := mesh.get_active_material(surface) as BaseMaterial3D
			if source == null: continue
			var material := ShaderMaterial.new()
			material.resource_name = source.resource_name
			material.shader = preload("res://shaders/native_model.gdshader")
			material.set_shader_parameter("albedo_texture", source.albedo_texture)
			material.set_shader_parameter("color_scale", color_scale)
			material.set_shader_parameter("double_sided", source.cull_mode == BaseMaterial3D.CULL_DISABLED)
			material.set_shader_parameter("part_visible", not source.resource_name.ends_with("_default_hidden"))
			if mesh.has_meta("native_stream_visibility"): material.set_shader_parameter("hidden_face_range", mesh.get_meta("native_stream_visibility"))
			material.set_shader_parameter("coplanar_overlay_flags", bool(mesh.mesh.get_meta("coplanar_overlays", false)))
			mesh.set_surface_override_material(surface, material)
static func _stream_defaults(root: Node3D) -> void:
	for mesh: MeshInstance3D in root.find_children("placement_*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.has_meta("native_stream_visibility") or str(mesh.name).ends_with("_variant_1"): continue
		var path := mesh.mesh.resource_path.get_slice("::", 0); var manifest := path.get_base_dir().path_join("manifest.json")
		if not stream_cache.has(manifest):
			var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest)) if FileAccess.file_exists(manifest) else null; stream_cache[manifest] = parsed.get("areas", []) if parsed is Dictionary else []
		for area: Dictionary in stream_cache[manifest]:
			if str(area["file"]) != path.get_file(): continue
			for rule: Dictionary in area.get("placement_streams", []):
				if not str(mesh.name).begins_with("placement_%03d_" % int(rule["placement"])): continue
				var range: Array = rule["default_hidden_range"]; mesh.set_meta("native_stream_visibility", Vector2(float(range[0]), float(range[1])))
static func placement_streams(root: Node3D, rules: Array) -> Array[Dictionary]:
	var saved: Array[Dictionary] = []
	for rule: Dictionary in rules:
		for mesh: MeshInstance3D in root.find_children("placement_%03d_*" % int(rule["placement"]), "MeshInstance3D", true, false):
			var range: Array = rule["hidden_range"]
			for surface in mesh.mesh.get_surface_count():
				var material := mesh.get_active_material(surface) as ShaderMaterial
				if material == null: continue
				var copy := material.duplicate() as ShaderMaterial; mesh.set_surface_override_material(surface, copy); saved.append({"node": mesh, "surface": surface, "material": material}); copy.set_shader_parameter("hidden_face_range", Vector2(float(range[0]), float(range[1])))
	return saved
static func depth_cue(root: Node3D, parameters: Dictionary, actor_flags: int = 0) -> void:
	if not is_instance_valid(root): return
	if root.has_meta("native_actor_source"):
		var entry: Dictionary = root.get_meta("native_actor_source"); var raw := str(entry.get("source_bytes_hex", entry.get("source_bytes", ""))).hex_decode(); actor_flags = int(entry.get("flags", raw[0] if not raw.is_empty() else actor_flags))
	var rgb: Array = parameters.get("far_rgb", [0, 0, 0]); var cue_enabled := bool(parameters.get("enabled", false)) and (actor_flags & 0x20) == 0; var signature := [cue_enabled, int(parameters.get("depth_shift", 0)), float(rgb[0]), float(rgb[1]), float(rgb[2])].hash()
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null or int(material.get_meta("depth_cue_signature", 0)) == signature: continue
			material.set_meta("depth_cue_signature", signature)
			material.set_shader_parameter("native_depth_cue_enabled", cue_enabled)
			material.set_shader_parameter("native_depth_cue_shift", int(parameters.get("depth_shift", 0)))
			material.set_shader_parameter("native_far_color", Vector3(float(rgb[0]), float(rgb[1]), float(rgb[2])))
	if root.has_meta("native_map_face_flags") and bool(parameters.get("visibility", {}).get("window", {}).get("enabled", false)) and not root.has_node("NativeMapVisibility"):
		var visibility := preload("res://scripts/world/rendering/native_map_visibility.gd").new(); visibility.name = "NativeMapVisibility"; root.add_child(visibility); visibility.configure(root, parameters)
	if not root.has_meta("native_map_face_flags"):
		var visibility := root.get_node_or_null("NativeActorVisibility")
		if visibility == null: visibility = preload("res://scripts/world/rendering/native_actor_visibility.gd").new(); visibility.name = "NativeActorVisibility"; root.add_child(visibility)
		visibility.configure(root, parameters, actor_flags)
