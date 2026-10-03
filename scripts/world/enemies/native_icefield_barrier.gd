extends Node3D
const Effect := preload("res://scripts/world/enemies/native_icefield_effect.gd")
var profile: Dictionary = {}
var origin_raw := Vector3i.ZERO
var mesh_node: MeshInstance3D
var accumulator := 0.0
func configure(level: Node3D, record: Array, brightness: int, source: Dictionary = {}, texture_path: String = "res://assets/levels/ST11/icefield_barrier.png") -> void:
	profile = source if not source.is_empty() else Effect.data()["barrier"]; top_level = true; global_transform = level.global_transform
	var mask := int(profile["cell_mask_raw"]); origin_raw = Vector3i(((int(record[0]) & mask) + 32768 & 65535) - 32768, int(record[1]) + int(profile["y_offset_raw"]), ((int(record[2]) & mask) + int(profile["z_offset_raw"]) + 32768 & 65535) - 32768)
	mesh_node = MeshInstance3D.new(); mesh_node.mesh = ArrayMesh.new(); mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; add_child(mesh_node)
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.albedo_texture = load(texture_path) as Texture2D; material.albedo_color = Color(float(brightness) / 128.0, float(brightness) / 128.0, float(brightness) / 128.0); mesh_node.material_override = material
	_rebuild()
func _physics_process(delta: float) -> void:
	accumulator += delta * 25.0
	while accumulator >= 1.0: accumulator -= 1.0; if _in_view(): _rebuild()
func _in_view() -> bool:
	var camera := get_viewport().get_camera_3d()
	if camera == null: return true
	for offset in [-700, -200, 320, 800, 1300]:
		if camera.is_position_in_frustum(to_global(_point(origin_raw + Vector3i(offset, -266, 0)))): return true
	return false
func _point(value: Vector3i) -> Vector3: return Vector3(-float(value.x), -float(value.y), float(value.z)) / 256.0
func _rebuild() -> void:
	var vertices := PackedVector3Array(); var uvs := PackedVector2Array(); var indices := PackedInt32Array(); var mask := int(profile["random_mask"]); var thickness := int(profile["thickness_raw"])
	var corners: Array = profile["texture_uv_raw"]; var coordinates: Array[Vector2] = []
	for index in range(4): coordinates.append(Vector2(float(int(corners[index * 2]) - 128) / 31.0, float(int(corners[index * 2 + 1]) - 128) / 31.0))
	for column in range(int(profile["columns"])):
		var offset := int(profile["column_start_raw"][column]); var lateral := int(profile["column_step_raw"][column])
		for row in range(int(profile["rows"])):
			var row_y := origin_raw.y - row * int(profile["row_step_raw"]); var previous_top := Vector3i.ZERO; var previous_corner := Vector3i.ZERO
			for segment in range(int(profile["segments"])):
				var first := Effect.random() & mask; var quad: Array[Vector3i]
				if segment == 0:
					var second := Effect.random() & mask; var x := origin_raw.x + offset; var y := row_y - thickness
					quad = [Vector3i(x + lateral, y + first, origin_raw.z), Vector3i(x, y + second, origin_raw.z), Vector3i(x + lateral, y + first + thickness, origin_raw.z), Vector3i(x, y + second + thickness, origin_raw.z)]
				else:
					var x := origin_raw.x + lateral * (segment + 1) + offset
					quad = [Vector3i(x, row_y + first, origin_raw.z), previous_top, Vector3i(x, row_y + first - thickness, origin_raw.z), previous_corner]
				previous_top = quad[0]; previous_corner = quad[2]; var base := vertices.size()
				for index in range(4): vertices.append(_point(quad[index])); uvs.append(coordinates[index])
				indices.append_array([base, base + 1, base + 2, base + 1, base + 3, base + 2])
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_TEX_UV] = uvs; arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := mesh_node.mesh as ArrayMesh; mesh.clear_surfaces(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
