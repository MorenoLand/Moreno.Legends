extends RefCounted
const PLANE_SCALE := 10000.0
const DISTANCE_EPSILON := 0.0001
static var mesh_cache: Dictionary = {}
static func apply(root: Node3D) -> void:
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if node.mesh != null and mesh_cache.has(node.mesh.get_instance_id()): node.mesh = mesh_cache[node.mesh.get_instance_id()]
	var overlays := collect(root); var nodes := {}
	for entry: Dictionary in overlays:
		var node: MeshInstance3D = entry["node"]
		if not nodes.has(node): nodes[node] = {}
		var surface := int(entry["surface_index"]); var triangles: PackedInt32Array = nodes[node].get(surface, PackedInt32Array()); triangles.append_array(entry["triangle_indices"]); nodes[node][surface] = triangles
	for node: MeshInstance3D in nodes:
		var original: Mesh = node.mesh; var id := original.get_instance_id()
		if mesh_cache.has(id): node.mesh = mesh_cache[id]; continue
		var replacement := ArrayMesh.new(); replacement.resource_name = original.resource_name
		for surface in original.get_surface_count():
			var arrays := _expanded_arrays(original.surface_get_arrays(surface)); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] is PackedColorArray else PackedColorArray()
			if colors.is_empty(): colors.resize(vertices.size()); colors.fill(Color.WHITE)
			for vertex in colors.size(): var color := colors[vertex]; color.a = 1.0; colors[vertex] = color
			for triangle: int in nodes[node].get(surface, PackedInt32Array()):
				for corner in 3: var vertex := triangle * 3 + corner; var color := colors[vertex]; color.a = 0.0; colors[vertex] = color
			arrays[Mesh.ARRAY_COLOR] = colors; replacement.add_surface_from_arrays(original.surface_get_primitive_type(surface), arrays); replacement.surface_set_material(surface, original.surface_get_material(surface))
		replacement.set_meta("coplanar_overlays", true); replacement.set_meta("coplanar_scanned", true); mesh_cache[id] = replacement; node.mesh = replacement
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if node.mesh != null: node.mesh.set_meta("coplanar_scanned", true)
static func _expanded_arrays(arrays: Array) -> Array:
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array()
	if indices.is_empty(): return arrays.duplicate()
	var result := arrays.duplicate(); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	for slot in Mesh.ARRAY_MAX:
		if slot == Mesh.ARRAY_INDEX or arrays[slot] == null or arrays[slot].is_empty(): continue
		var source: Variant = arrays[slot]; var expanded: Variant = source.slice(0, 0); var stride: int = source.size() / vertices.size()
		for index: int in indices:
			for component in stride: expanded.append(source[index * stride + component])
		result[slot] = expanded
	result[Mesh.ARRAY_INDEX] = PackedInt32Array(); return result
static func collect(root: Node3D) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if node.mesh == null or bool(node.mesh.get_meta("coplanar_scanned", false)) or node.mesh.get_blend_shape_count() > 0: continue
		var skinned := false
		for surface in node.mesh.get_surface_count():
			var material := node.get_active_material(surface) as ShaderMaterial
			skinned = skinned or (node.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_BONES) != 0 or (material != null and material.shader != null and material.shader.resource_path != "res://shaders/native_model.gdshader")
		if skinned: continue
		var planes := {}
		for surface in range(node.mesh.get_surface_count()):
			if node.mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: continue
			var arrays: Array = node.mesh.surface_get_arrays(surface); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var triangle_count := indices.size() / 3 if not indices.is_empty() else vertices.size() / 3
			for triangle in range(triangle_count):
				var i0 := int(indices[triangle * 3]) if not indices.is_empty() else triangle * 3; var i1 := int(indices[triangle * 3 + 1]) if not indices.is_empty() else triangle * 3 + 1; var i2 := int(indices[triangle * 3 + 2]) if not indices.is_empty() else triangle * 3 + 2
				var points := [node.global_transform * vertices[i0], node.global_transform * vertices[i1], node.global_transform * vertices[i2]]; var normal: Vector3 = (points[1] - points[0]).cross(points[2] - points[0]); var doubled_area: float = normal.length()
				if doubled_area <= 0.000001: continue
				normal /= doubled_area
				if absf(normal.y) >= 0.5: continue
				var canonical := _canonical_normal(normal); var plane := canonical.dot(points[0]); var key := "%d:%d:%d:%d" % [roundi(canonical.x * PLANE_SCALE), roundi(canonical.y * PLANE_SCALE), roundi(canonical.z * PLANE_SCALE), roundi(plane * PLANE_SCALE)]
				if not planes.has(key): planes[key] = []
				planes[key].append({"surface": surface, "triangle": triangle, "points": points, "normal": normal, "area": doubled_area * 0.5, "axis": _dominant_axis(canonical)})
		for key: String in planes:
			var group: Array = planes[key]; var by_surface := {}
			for overlay: Dictionary in group:
				var parent: Dictionary = {}; var parent_area := INF
				for candidate: Dictionary in group:
					if not _comes_after(overlay, candidate) or float(candidate["area"]) <= float(overlay["area"]): continue
					if not _inside_triangle(overlay["points"], candidate["points"], int(overlay["axis"])): continue
					if float(candidate["area"]) < parent_area: parent = candidate; parent_area = float(candidate["area"])
				if parent.is_empty(): continue
				var surface_index := int(overlay["surface"])
				if not by_surface.has(surface_index): by_surface[surface_index] = {"node": node, "surface_index": surface_index, "triangle_indices": PackedInt32Array(), "render_normals": PackedVector3Array(), "parent_surfaces": PackedInt32Array(), "parent_triangles": PackedInt32Array()}
				var entry: Dictionary = by_surface[surface_index]; entry["triangle_indices"].append(int(overlay["triangle"])); entry["render_normals"].append(parent["normal"]); entry["parent_surfaces"].append(int(parent["surface"])); entry["parent_triangles"].append(int(parent["triangle"]))
			for surface_index: int in by_surface: result.append(by_surface[surface_index])
	return result
static func _canonical_normal(normal: Vector3) -> Vector3:
	var value := normal
	if value.x < -0.000001 or (absf(value.x) <= 0.000001 and value.y < -0.000001) or (absf(value.x) <= 0.000001 and absf(value.y) <= 0.000001 and value.z < 0.0): value = -value
	return value
static func _dominant_axis(normal: Vector3) -> int:
	var axis := 0
	if absf(normal.y) > absf(normal.x): axis = 1
	if absf(normal.z) > absf(normal[axis]): axis = 2
	return axis
static func _comes_after(a: Dictionary, b: Dictionary) -> bool:
	return int(a["surface"]) > int(b["surface"]) or (int(a["surface"]) == int(b["surface"]) and int(a["triangle"]) > int(b["triangle"]))
static func _project(point: Vector3, axis: int) -> Vector2:
	return Vector2(point.y, point.z) if axis == 0 else Vector2(point.x, point.z) if axis == 1 else Vector2(point.x, point.y)
static func _inside_triangle(points: Array, triangle: Array, axis: int) -> bool:
	var a := _project(triangle[0], axis); var b := _project(triangle[1], axis); var c := _project(triangle[2], axis); var denominator := (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
	if absf(denominator) <= 0.0000001: return false
	for point: Vector3 in points:
		var p := _project(point, axis); var u := ((b.y - c.y) * (p.x - c.x) + (c.x - b.x) * (p.y - c.y)) / denominator; var v := ((c.y - a.y) * (p.x - c.x) + (a.x - c.x) * (p.y - c.y)) / denominator
		if minf(minf(u, v), 1.0 - u - v) < -DISTANCE_EPSILON: return false
	return true
static func _same_triangle(a: Array, b: Array) -> bool:
	for point: Vector3 in a:
		var found := false
		for other: Vector3 in b:
			if point.distance_squared_to(other) <= DISTANCE_EPSILON * DISTANCE_EPSILON: found = true; break
		if not found: return false
	return true
