extends MeshInstance3D
var random_source: Callable
func configure(random_callback: Callable) -> void:
	random_source = random_callback; mesh = ImmediateMesh.new()
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material_override = material
func _random() -> int: return int(random_source.call())
func _point(basis: Basis, point: Vector3) -> Vector3:
	var rotated := basis * point
	return Vector3(-rotated.x, -rotated.y, rotated.z) / 256.0
func _diamond(basis: Basis, width: int, distance: int) -> Array[Vector3]:
	return [_point(basis, Vector3(-width, 0, distance)), _point(basis, Vector3(0, -width, distance)), _point(basis, Vector3(width, 0, distance)), _point(basis, Vector3(0, width, distance))]
func _vertex(geometry: ImmediateMesh, point: Vector3, color: Color) -> void: geometry.surface_set_color(color); geometry.surface_add_vertex(point)
func _quad(geometry: ImmediateMesh, points: Array, colors: Array) -> void:
	for index in [0, 1, 2, 0, 2, 3]: _vertex(geometry, points[index], colors[index])
func redraw(state: int, radius: int, remaining: int, tick: int) -> void:
	var geometry := mesh as ImmediateMesh; geometry.clear_surfaces()
	if state < 0: return
	geometry.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	if state in [1, 2]:
		var native_radius := radius << 4; var step := native_radius / 7
		for bundle in range(3):
			var sector := (tick + bundle) & 7
			var angle := Vector3((1024 if sector < 4 else 3072) - (_random() & 1023), (sector & 3) * 1024 + 768 - (_random() & 511), 128 - (_random() & 255))
			var basis := Basis.from_euler(angle * TAU / 4096.0)
			var previous := _diamond(basis, 2, 32)
			for segment in range(6):
				var shift := segment >> 1
				var jitter := Vector3((128 - (_random() & 255)) >> shift, (64 - (_random() & 127)) >> shift, (32 - (_random() & 63)) >> shift)
				basis = Basis.from_euler((angle + jitter) * TAU / 4096.0)
				var distance := native_radius if segment == 5 else int(step) * (segment + 1) + 40 - (_random() & 15)
				var current := _diamond(basis, 5 + segment + (_random() & 7), distance)
				var color_a := Color(maxi(192 - segment * 8, 0) / 255.0, maxi(128 - segment * 8, 0) / 255.0, maxi(96 - segment * 8, 0) / 255.0)
				var color_b := Color(maxi(184 - segment * 8, 0) / 255.0, maxi(120 - segment * 8, 0) / 255.0, maxi(88 - segment * 8, 0) / 255.0)
				for side in range(4): _quad(geometry, [previous[side], previous[(side + 1) & 3], current[(side + 1) & 3], current[side]], [color_a, color_a, color_b, color_b])
				previous = current
	else:
		var camera := get_viewport().get_camera_3d()
		if camera != null:
			var radius_world := float((radius + 2) << 4) / 256.0; var roll := float((_random() << 1) & 4095) * TAU / 4096.0
			var color := Color((96.0 + sin(tick * TAU / 64.0) * 64.0) / 510.0, (96.0 + cos(tick * TAU / 128.0) * 64.0) / 510.0, (96.0 + sin(tick * TAU / 256.0) * 64.0) / 510.0)
			color *= float(8 - remaining if state == 0 else remaining) / 8.0; color.a = 1
			var right := global_basis.inverse() * camera.global_basis.x; var up := global_basis.inverse() * camera.global_basis.y
			for sector in range(16):
				var first := roll + sector * TAU / 16.0; var second := first + TAU / 16.0
				_vertex(geometry, (right * cos(first) + up * sin(first)) * radius_world, Color.BLACK); _vertex(geometry, Vector3.ZERO, color); _vertex(geometry, (right * cos(second) + up * sin(second)) * radius_world, Color.BLACK)
	geometry.surface_end()
