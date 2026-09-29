@tool
extends RefCounted
const ROOMS := {"ST04:0": [{"node": "placement_000_model_001", "surface": 6, "min": Vector3(-1.875, 0.5, -0.875), "max": Vector3(1.875, 1.125, 0.375), "uv_min": Vector2(192.5, 192.5) / 256.0, "uv_max": Vector2(255.5, 255.5) / 256.0}]}
static func apply(room: Node3D, stage: String, area: int) -> void:
	for entry: Dictionary in ROOMS.get("%s:%d" % [stage, area], []):
		var node := room.find_child(str(entry["node"]), true, false) as MeshInstance3D
		if node == null or node.mesh == null or node.mesh.get_surface_count() <= int(entry["surface"]): continue
		var source := node.get_active_material(int(entry["surface"])) as ShaderMaterial
		if source == null: continue
		var material := ShaderMaterial.new()
		material.shader = preload("res://shaders/window.gdshader")
		material.set_shader_parameter("snowfall_enabled", bool(room.get_meta("window_snowfall", false)))
		for parameter in ["albedo_texture", "color_scale", "double_sided"]: material.set_shader_parameter(parameter, source.get_shader_parameter(parameter))
		material.set_shader_parameter("pane_min", entry["min"]); material.set_shader_parameter("pane_max", entry["max"])
		material.set_shader_parameter("pane_uv_min", entry["uv_min"]); material.set_shader_parameter("pane_uv_max", entry["uv_max"])
		material.set_shader_parameter("snow_texture", load("res://assets/weather/snow.png"))
		material.set_shader_parameter("reflection_texture", load("res://assets/opening/effects/ST02/atmosphere_1_primary.png"))
		node.set_surface_override_material(int(entry["surface"]), material)
static func set_snowfall(room: Node3D, enabled: bool) -> void:
	room.set_meta("window_snowfall", enabled)
	for node: MeshInstance3D in room.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null: continue
		for surface in node.mesh.get_surface_count():
			var material := node.get_active_material(surface) as ShaderMaterial
			if material != null and material.shader == preload("res://shaders/window.gdshader"): material.set_shader_parameter("snowfall_enabled", enabled)
