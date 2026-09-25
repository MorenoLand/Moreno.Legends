@tool
extends RefCounted
static func apply(root: Node3D, color_scale: float = 255.0) -> void:
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		for surface in range(mesh.mesh.get_surface_count()):
			var source := mesh.get_active_material(surface) as BaseMaterial3D
			if source == null: continue
			var material := ShaderMaterial.new()
			material.shader = preload("res://shaders/native_model.gdshader")
			material.set_shader_parameter("albedo_texture", source.albedo_texture)
			material.set_shader_parameter("color_scale", color_scale)
			material.set_shader_parameter("double_sided", source.cull_mode == BaseMaterial3D.CULL_DISABLED)
			mesh.set_surface_override_material(surface, material)
static func depth_cue(root: Node3D, parameters: Dictionary) -> void:
	if not is_instance_valid(root): return
	var rgb: Array = parameters.get("far_rgb", [0, 0, 0])
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null: continue
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null: continue
			material.set_shader_parameter("native_depth_cue_enabled", bool(parameters.get("enabled", false)))
			material.set_shader_parameter("native_depth_cue_shift", int(parameters.get("depth_shift", 0)))
			material.set_shader_parameter("native_far_color", Vector3(float(rgb[0]), float(rgb[1]), float(rgb[2])))
