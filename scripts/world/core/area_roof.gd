extends RefCounted
static var manifests: Dictionary = {}
static func apply(root: Node3D, stage: String, area: int) -> bool:
	if root.has_meta("area_roof_configured"): return bool(root.get_meta("area_roof_generated", false))
	var path := "res://assets/levels/%s/area_roofs.json" % stage
	if not manifests.has(stage):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		manifests[stage] = data if data is Dictionary else {}
	for record: Dictionary in manifests[stage].get("areas", []):
		if int(record.get("area", -1)) != area: continue
		root.set_meta("area_roof_configured", true); root.set_meta("native_fixed_pitch", bool(record.get("fixed_pitch", false)))
		var roof: Dictionary = record.get("roof", {}); var points: Array = roof.get("vertices", [])
		_apply_blackouts(root, roof)
		if points.is_empty(): return false
		var source := root.find_child(str(roof.get("material_node", "")), true, false) as MeshInstance3D
		if source == null or source.mesh == null: return false
		var surface := int(roof.get("material_surface", -1))
		if surface < 0 or surface >= source.mesh.get_surface_count(): return false
		var material := source.get_active_material(surface)
		if material == null: return false
		var vertices := PackedVector3Array(); var uv := PackedVector2Array(); var colors := PackedColorArray(); var normals := PackedVector3Array(); var coordinates: Array = roof.get("uv", []); var tint: Array = roof.get("color", [0.5, 0.5, 0.5, 1])
		if points.size() != coordinates.size() or points.size() % 3 != 0: return false
		for index in points.size():
			var point: Array = points[index]; var coordinate: Array = coordinates[index]; vertices.append(Vector3(float(point[0]), float(point[1]), float(point[2]))); uv.append(Vector2(float(coordinate[0]), float(coordinate[1]))); colors.append(Color(float(tint[0]), float(tint[1]), float(tint[2]), float(tint[3]))); normals.append(Vector3.DOWN)
		var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_TEX_UV] = uv; arrays[Mesh.ARRAY_COLOR] = colors; arrays[Mesh.ARRAY_NORMAL] = normals
		var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); var ceiling := MeshInstance3D.new(); ceiling.name = "GeneratedAreaRoof"; ceiling.mesh = mesh; ceiling.material_override = material.duplicate()
		if ceiling.material_override is ShaderMaterial:
			var shader_material := ceiling.material_override as ShaderMaterial; shader_material.set_shader_parameter("double_sided", true)
			if str(roof.get("material_source", "")) == "existing_wall": shader_material.set_shader_parameter("roof_texture_region", _quiet_texture_region(shader_material, roof))
		elif ceiling.material_override is BaseMaterial3D: (ceiling.material_override as BaseMaterial3D).cull_mode = BaseMaterial3D.CULL_DISABLED
		root.add_child(ceiling); var shape := CollisionShape3D.new(); shape.shape = mesh.create_trimesh_shape()
		ceiling.set_meta("generated_roof_mesh", true)
		if shape.shape is ConcavePolygonShape3D: (shape.shape as ConcavePolygonShape3D).backface_collision = true
		var body := StaticBody3D.new(); body.name = "RoomCollision_4"; body.collision_layer = 4; body.collision_mask = 0; body.add_child(shape); ceiling.add_child(body)
		var player_body := StaticBody3D.new(); player_body.name = "GeneratedRoofPlayerCollision"; player_body.collision_layer = 16; player_body.collision_mask = 0; var player_shape := CollisionShape3D.new(); player_shape.shape = shape.shape.duplicate(); player_body.add_child(player_shape); ceiling.add_child(player_body)
		_apply_wall_infills(root, roof)
		root.set_meta("area_roof_generated", true); return true
	return false
static func _apply_wall_infills(root: Node3D, roof: Dictionary) -> void:
	var number := 0
	for infill: Dictionary in roof.get("wall_infills", []):
		var source := root.find_child(str(infill.get("material_node", "")), true, false) as MeshInstance3D; var surface := int(infill.get("material_surface", -1)); var points: Array = infill.get("vertices", []); var coordinates: Array = infill.get("uv", []); var tints: Array = infill.get("colors", [])
		if source == null or source.mesh == null or surface < 0 or surface >= source.mesh.get_surface_count() or points.size() != coordinates.size() or points.size() != tints.size(): continue
		var material := source.get_active_material(surface)
		if material == null: continue
		var vertices := PackedVector3Array(); var uv := PackedVector2Array(); var colors := PackedColorArray()
		for index in points.size():
			var point: Array = points[index]; var coordinate: Array = coordinates[index]; var tint: Array = tints[index]; vertices.append(Vector3(float(point[0]), float(point[1]), float(point[2]))); uv.append(Vector2(float(coordinate[0]), float(coordinate[1]))); colors.append(Color(float(tint[0]), float(tint[1]), float(tint[2]), float(tint[3])))
		var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_TEX_UV] = uv; arrays[Mesh.ARRAY_COLOR] = colors; var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); var wall := MeshInstance3D.new(); wall.name = "GeneratedRoofWall_%d" % number; number += 1; wall.mesh = mesh; wall.material_override = material.duplicate(); wall.set_meta("generated_roof_mesh", true)
		if wall.material_override is ShaderMaterial: (wall.material_override as ShaderMaterial).set_shader_parameter("double_sided", true)
		elif wall.material_override is BaseMaterial3D: (wall.material_override as BaseMaterial3D).cull_mode = BaseMaterial3D.CULL_DISABLED
		root.add_child(wall); var geometry := mesh.create_trimesh_shape(); geometry.backface_collision = true
		for layer in [4, 16]:
			var body := StaticBody3D.new(); body.name = "RoomCollision_4" if layer == 4 else "GeneratedRoofPlayerCollision"; body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = geometry.duplicate(); body.add_child(shape); wall.add_child(body)
static func _apply_blackouts(root: Node3D, roof: Dictionary) -> void:
	var vertices := PackedVector3Array()
	for loop: Array in roof.get("blackouts", []):
		var polygon := PackedVector2Array()
		for point: Array in loop: polygon.append(Vector2(float(point[0]), float(point[2])))
		var triangles := Geometry2D.triangulate_polygon(polygon)
		for index in triangles:
			var point: Array = loop[index]; vertices.append(Vector3(float(point[0]), float(point[1]), float(point[2])))
	if vertices.is_empty(): return
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.albedo_color = Color.BLACK; var cover := MeshInstance3D.new(); cover.name = "LadderHatchBlackout"; cover.mesh = mesh; cover.material_override = material; root.add_child(cover)
static func _quiet_texture_region(material: ShaderMaterial, roof: Dictionary) -> Vector4:
	var texture := material.get_shader_parameter("albedo_texture") as Texture2D
	if texture == null: return Vector4.ZERO
	var image := texture.get_image()
	if image == null or image.is_empty(): return Vector4.ZERO
	if image.is_compressed() and image.decompress() != OK: return Vector4.ZERO
	var low: Array = roof.get("sample_uv_min", []); var high: Array = roof.get("sample_uv_max", [])
	if low.size() != 2 or high.size() != 2: return Vector4.ZERO
	var width := image.get_width(); var height := image.get_height(); var left := clampi(floori(float(low[0]) * width), 0, width - 1); var top := clampi(floori(float(low[1]) * height), 0, height - 1); var right := clampi(ceili(float(high[0]) * width), left + 1, width); var bottom := clampi(ceili(float(high[1]) * height), top + 1, height); var patch := mini(8, mini(right - left, bottom - top)); var best := INF; var selected := Vector2i(-1, -1)
	for y in range(top, bottom - patch + 1, 2):
		for x in range(left, right - patch + 1, 2):
			var total := Vector3.ZERO; var squares := 0.0; var opaque := true
			for py in range(y, y + patch):
				for px in range(x, x + patch):
					var color := image.get_pixel(px, py); var rgb := Vector3(color.r, color.g, color.b); opaque = opaque and color.a >= 0.99; total += rgb; squares += rgb.length_squared()
			if not opaque: continue
			var mean := total / float(patch * patch); var brightness := mean.dot(Vector3(0.2126, 0.7152, 0.0722)); var score := squares / float(patch * patch) - mean.length_squared() + 0.03 * pow(1.0 - brightness, 2)
			if score < best: best = score; selected = Vector2i(x, y)
	if selected.x < 0: return Vector4.ZERO
	return Vector4((selected.x + 0.5) / float(width), (selected.y + 0.5) / float(height), maxf(patch - 1.0, 0.01) / width, maxf(patch - 1.0, 0.01) / height)
