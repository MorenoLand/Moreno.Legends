extends MeshInstance3D
var history: Array[Vector3] = []
var native_offset := Vector3.ZERO
var owner_actor: Node3D
func configure(actor: Node3D, offset: Vector3) -> void:
	owner_actor = actor; native_offset = offset; top_level = true; global_transform = Transform3D.IDENTITY; mesh = ImmediateMesh.new()
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.no_depth_test = false; material_override = material
func native_tick(neck_yaw: int) -> void:
	var yaw: float = (int(owner_actor.native_yaw) + neck_yaw) * TAU / 4096.0
	var offset := Basis(Vector3.UP, yaw) * Vector3(-native_offset.x, -native_offset.y, native_offset.z) / 16.0
	history.push_front(owner_actor.global_position + offset)
	if history.size() > 26: history.pop_back()
	var geometry := mesh as ImmediateMesh; geometry.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if history.size() < 2 or camera == null: return
	geometry.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in range(history.size() - 1):
		var width_a := 24.0 if index == 0 else 3.0 * (16 - ((history.size() - index) >> 1)); var width_b := 3.0 * (16 - ((history.size() - index - 1) >> 1))
		var right := camera.global_basis.x; var up := camera.global_basis.y
		var corners_a := [history[index] + (-right - up) * width_a / 256.0, history[index] + (right - up) * width_a / 256.0, history[index] + (right + up) * width_a / 256.0, history[index] + (-right + up) * width_a / 256.0]
		var corners_b := [history[index + 1] + (-right - up) * width_b / 256.0, history[index + 1] + (right - up) * width_b / 256.0, history[index + 1] + (right + up) * width_b / 256.0, history[index + 1] + (-right + up) * width_b / 256.0]
		var shade_a := maxf(52.0 - index * 2, 0) / 255.0; var shade_b := maxf(54.0 - index * 2, 0) / 255.0
		for side in range(4):
			var next := (side + 1) & 3
			for vertex in [0, 1, 2, 0, 2, 3]:
				var point: Vector3 = [corners_a[side], corners_a[next], corners_b[next], corners_b[side]][vertex]
				geometry.surface_set_color(Color(shade_a, shade_a, shade_a, 1) if vertex < 2 else Color(shade_b, shade_b, shade_b, 1)); geometry.surface_add_vertex(point)
	geometry.surface_end()
