extends RefCounted
const PLANE_SCALE := 10000.0
const DISTANCE_EPSILON := 0.0001
static var mesh_cache: Dictionary = {}
static var scan_cache: Dictionary = {}
static var cross_cache: Dictionary = {}
static func apply(root: Node3D) -> void:
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if node.mesh != null and mesh_cache.has(node.mesh.get_instance_id()): node.mesh = mesh_cache[node.mesh.get_instance_id()]
	var overlays := collect(root); var nodes := {}
	for entry: Dictionary in overlays:
		var node: MeshInstance3D = entry["node"]
		if not nodes.has(node): nodes[node] = {}
		var surface := int(entry["surface_index"]); var layers: Dictionary = nodes[node].get(surface, {})
		for index in entry["triangle_indices"].size(): layers[int(entry["triangle_indices"][index])] = maxi(int(layers.get(int(entry["triangle_indices"][index]), 0)), int(entry["layers"][index]))
		nodes[node][surface] = layers
	for node: MeshInstance3D in nodes:
		var original: Mesh = node.mesh; var id := original.get_instance_id()
		if mesh_cache.has(id): node.mesh = mesh_cache[id]; continue
		var replacement := ArrayMesh.new(); replacement.resource_name = original.resource_name
		for surface in original.get_surface_count():
			var arrays := _expanded_arrays(original.surface_get_arrays(surface)); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] is PackedColorArray else PackedColorArray()
			if not arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array or arrays[Mesh.ARRAY_NORMAL].is_empty():
				var normals := PackedVector3Array(); normals.resize(vertices.size())
				for triangle in vertices.size() / 3:
					var first := triangle * 3; var normal := (vertices[first + 1] - vertices[first]).cross(vertices[first + 2] - vertices[first]).normalized()
					for corner in 3: normals[first + corner] = normal
				arrays[Mesh.ARRAY_NORMAL] = normals
			if colors.is_empty(): colors.resize(vertices.size()); colors.fill(Color.WHITE)
			for vertex in colors.size(): var color := colors[vertex]; color.a = 1.0; colors[vertex] = color
			var layers: Dictionary = nodes[node].get(surface, {})
			for triangle: int in layers:
				for corner in 3: var vertex := triangle * 3 + corner; var color := colors[vertex]; color.a = float(layers[triangle]) / 255.0; colors[vertex] = color
			arrays[Mesh.ARRAY_COLOR] = colors; replacement.add_surface_from_arrays(original.surface_get_primitive_type(surface), arrays)
			if replacement.get_surface_count() != surface + 1: return
			replacement.surface_set_material(surface, original.surface_get_material(surface)); replacement.surface_set_name(surface, original.surface_get_name(surface))
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
	var expanded_indices := PackedInt32Array(); expanded_indices.resize(indices.size())
	for index in expanded_indices.size(): expanded_indices[index] = index
	result[Mesh.ARRAY_INDEX] = expanded_indices; return result
static func collect(root: Node3D) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var scannable: Array[MeshInstance3D] = []
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		result.append_array(_collect_node(node, root))
		if _scannable(node): scannable.append(node)
	result.append_array(_cross_entries(scannable))
	return result
static func warm(root: Node3D) -> void:
	var tree := root.get_tree(); var jobs: Array[Dictionary] = []; var face_flags := bool(root.get_meta("native_map_face_flags", false))
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if not is_instance_valid(node) or not node.is_inside_tree(): break
		if not _scannable(node): continue
		var partial := _placement(node); var scan_key := "%s|%s|%s|%s" % [node.mesh.resource_path, var_to_str(node.global_transform), face_flags, partial] if node.mesh.resource_path.contains("::") else ""
		if scan_key.is_empty() or scan_cache.has(scan_key): continue
		var job := {"scan_key": scan_key, "holder": {}}; job["task"] = WorkerThreadPool.add_task(_scan_job.bind(_surface_data(node), node.global_transform, face_flags, partial, job["holder"])); jobs.append(job)
		await tree.process_frame
	var cross_nodes: Array[MeshInstance3D] = []
	for node: MeshInstance3D in root.find_children("*", "MeshInstance3D", true, false):
		if is_instance_valid(node) and node.is_inside_tree() and _scannable(node): cross_nodes.append(node)
	var cross_signature := _cross_signature(cross_nodes); var cross_holder := {}; var cross_task := -1
	if not cross_signature.is_empty() and not cross_cache.has(cross_signature):
		var cross_jobs: Array = []; var cross_partners := _cross_partners(cross_nodes); var slice_start := Time.get_ticks_usec()
		for index: int in cross_partners:
			if not is_instance_valid(cross_nodes[index]) or not cross_nodes[index].is_inside_tree(): cross_jobs.clear(); break
			cross_jobs.append(_cross_job_data(cross_nodes, index, cross_partners))
			if Time.get_ticks_usec() - slice_start > 1500: await tree.process_frame; slice_start = Time.get_ticks_usec()
		if cross_jobs.is_empty(): cross_cache[cross_signature] = []
		else: cross_task = WorkerThreadPool.add_task(_cross_job.bind(cross_jobs, cross_holder))
	if cross_task >= 0:
		while not WorkerThreadPool.is_task_completed(cross_task): await tree.process_frame
		WorkerThreadPool.wait_for_task_completion(cross_task); cross_cache[cross_signature] = cross_holder["result"]
	for job in jobs:
		while not WorkerThreadPool.is_task_completed(int(job["task"])): await tree.process_frame
		WorkerThreadPool.wait_for_task_completion(int(job["task"])); scan_cache[job["scan_key"]] = job["holder"]["result"]
static func _scan_job(surfaces: Array, world: Transform3D, face_flags: bool, partial: bool, holder: Dictionary) -> void: holder["result"] = _scan(surfaces, world, face_flags, partial)
static func _collect_node(node: MeshInstance3D, root: Node3D, cacheable_only: bool = false) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not _scannable(node): return result
	var partial := _placement(node); var scan_key := "%s|%s|%s|%s" % [node.mesh.resource_path, var_to_str(node.global_transform), bool(root.get_meta("native_map_face_flags", false)), partial] if node.mesh.resource_path.contains("::") else ""
	if cacheable_only and scan_key.is_empty(): return result
	if scan_cache.has(scan_key):
		for cached: Dictionary in scan_cache[scan_key]: var entry := cached.duplicate(true); entry["node"] = node; result.append(entry)
		return result
	var face_flags := bool(root.get_meta("native_map_face_flags", false)); var found := _scan(_surface_data(node), node.global_transform, face_flags, partial)
	if not scan_key.is_empty():
		var stored: Array = []
		for entry: Dictionary in found: stored.append(entry.duplicate(true))
		scan_cache[scan_key] = stored
	for entry: Dictionary in found: entry["node"] = node; result.append(entry)
	return result
static func _cross_signature(nodes: Array[MeshInstance3D]) -> String:
	if nodes.size() < 2: return ""
	var parts: Array[String] = []
	for node: MeshInstance3D in nodes:
		if not node.mesh.resource_path.contains("::"): return ""
		parts.append("%s|%s" % [node.mesh.resource_path, var_to_str(node.global_transform)])
	return str("|".join(parts).hash())
static func _cross_entries(nodes: Array[MeshInstance3D]) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if nodes.size() < 2: return result
	var signature := _cross_signature(nodes); var found: Array = []
	if not signature.is_empty() and cross_cache.has(signature): found = cross_cache[signature]
	else:
		found = _cross_scan(_cross_jobs(nodes))
		if not signature.is_empty(): cross_cache[signature] = found
	for cached: Dictionary in found: var entry := cached.duplicate(true); entry["node"] = nodes[int(entry["node_index"])]; result.append(entry)
	return result
static func _cross_partners(nodes: Array[MeshInstance3D]) -> Dictionary:
	var boxes: Array[AABB] = []; var partners := {}
	for node: MeshInstance3D in nodes: boxes.append(node.global_transform * node.mesh.get_aabb())
	for first in nodes.size():
		for second in range(first + 1, nodes.size()):
			if not boxes[first].grow(0.01).intersects(boxes[second].grow(0.01)): continue
			if not partners.has(first): partners[first] = []
			if not partners.has(second): partners[second] = []
			partners[first].append(boxes[second].grow(0.01)); partners[second].append(boxes[first].grow(0.01))
	return partners
static func _cross_job_data(nodes: Array[MeshInstance3D], index: int, partners: Dictionary) -> Dictionary: return {"node_index": index, "placement": _placement(nodes[index]), "world": nodes[index].global_transform, "surfaces": _surface_data(nodes[index]), "partners": partners[index]}
static func _cross_jobs(nodes: Array[MeshInstance3D]) -> Array:
	var jobs: Array = []; var partners := _cross_partners(nodes)
	for index: int in partners: jobs.append(_cross_job_data(nodes, index, partners))
	return jobs
static func _cross_job(jobs: Array, holder: Dictionary) -> void: holder["result"] = _cross_scan(jobs)
static func _cross_scan(jobs: Array) -> Array[Dictionary]:
	var groups := {}; var result: Array[Dictionary] = []
	for job: Dictionary in jobs:
		var world: Transform3D = job["world"]
		for item: Dictionary in job["surfaces"]:
			var arrays: Array = item["arrays"]; var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR] if arrays[Mesh.ARRAY_COLOR] is PackedColorArray else PackedColorArray(); var triangle_count := indices.size() / 3 if not indices.is_empty() else vertices.size() / 3
			for triangle in triangle_count:
				var i0 := int(indices[triangle * 3]) if not indices.is_empty() else triangle * 3; var i1 := int(indices[triangle * 3 + 1]) if not indices.is_empty() else triangle * 3 + 1; var i2 := int(indices[triangle * 3 + 2]) if not indices.is_empty() else triangle * 3 + 2
				var points := [world * vertices[i0], world * vertices[i1], world * vertices[i2]]; var low: Vector3 = points[0].min(points[1]).min(points[2]); var near := false
				for partner: AABB in job["partners"]:
					if partner.intersects(AABB(low, (points[0].max(points[1]).max(points[2])) - low)): near = true; break
				if not near: continue
				var normal: Vector3 = (points[1] - points[0]).cross(points[2] - points[0]); var doubled_area: float = normal.length()
				if doubled_area <= 0.000001: continue
				var canonical := _canonical_normal(normal / doubled_area); var key := Vector4i(roundi(canonical.x * PLANE_SCALE), roundi(canonical.y * PLANE_SCALE), roundi(canonical.z * PLANE_SCALE), roundi(canonical.dot(points[0]) * PLANE_SCALE)); var axis := _dominant_axis(canonical); var polygon := PackedVector2Array()
				for point: Vector3 in points: polygon.append(_project(point, axis))
				var existing := 0
				if not colors.is_empty() and colors[i0].a < 0.5: existing = maxi(1, roundi(colors[i0].a * 255.0))
				if not groups.has(key): groups[key] = []
				groups[key].append({"node": int(job["node_index"]), "placement": bool(job["placement"]), "surface": int(item["surface"]), "triangle": triangle, "polygon": polygon, "bounds": _polygon_bounds(polygon), "layer": existing})
	var by_surface := {}
	for key: Vector4i in groups:
		var group: Array = groups[key]
		if group.size() < 2: continue
		group.sort_custom(_cross_before); var prior_faces: Array = []
		for face: Dictionary in group:
			var support := -1; var polygon: PackedVector2Array = face["polygon"]; var original_area := _polygon_area(polygon); var epsilon := DISTANCE_EPSILON * DISTANCE_EPSILON * maxf(1.0, original_area)
			for prior: Dictionary in prior_faces:
				if int(prior["node"]) == int(face["node"]) or not (face["bounds"] as Rect2).intersects(prior["bounds"], true): continue
				var outside_area := 0.0
				for piece: PackedVector2Array in _subtract_triangle(polygon, prior["polygon"]): outside_area += _polygon_area(piece)
				if original_area - outside_area > epsilon: support = maxi(support, int(prior["layer"]))
			prior_faces.append(face)
			if support < 0 or not bool(face["placement"]) or mini(support + 1, 127) <= int(face["layer"]): continue
			face["layer"] = mini(support + 1, 127); var slot := "%d:%d" % [face["node"], face["surface"]]
			if not by_surface.has(slot): by_surface[slot] = {"node_index": int(face["node"]), "surface_index": int(face["surface"]), "triangle_indices": PackedInt32Array(), "layers": PackedInt32Array()}
			by_surface[slot]["triangle_indices"].append(int(face["triangle"])); by_surface[slot]["layers"].append(int(face["layer"]))
	for slot: String in by_surface: result.append(by_surface[slot])
	return result
static func _cross_before(first: Dictionary, second: Dictionary) -> bool:
	if int(first["node"]) != int(second["node"]): return int(first["node"]) < int(second["node"])
	return _comes_after(second, first)
static func _scan(surfaces: Array, world: Transform3D, face_flags: bool, partial: bool = false) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	var planes := {}
	for item: Dictionary in surfaces:
		var surface := int(item["surface"]); var arrays: Array = item["arrays"]; var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var triangle_count := indices.size() / 3 if not indices.is_empty() else vertices.size() / 3; var source_faces: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2] if arrays[Mesh.ARRAY_TEX_UV2] is PackedVector2Array else PackedVector2Array(); var source_encoded: bool = face_flags and source_faces.size() == vertices.size()
		for triangle in range(triangle_count):
			var i0 := int(indices[triangle * 3]) if not indices.is_empty() else triangle * 3; var i1 := int(indices[triangle * 3 + 1]) if not indices.is_empty() else triangle * 3 + 1; var i2 := int(indices[triangle * 3 + 2]) if not indices.is_empty() else triangle * 3 + 2
			var points := [world * vertices[i0], world * vertices[i1], world * vertices[i2]]; var normal: Vector3 = (points[1] - points[0]).cross(points[2] - points[0]); var doubled_area: float = normal.length()
			if doubled_area <= 0.000001: continue
			normal /= doubled_area
			var canonical := _canonical_normal(normal); var plane := canonical.dot(points[0]); var key := "%d:%d:%d:%d" % [roundi(canonical.x * PLANE_SCALE), roundi(canonical.y * PLANE_SCALE), roundi(canonical.z * PLANE_SCALE), roundi(plane * PLANE_SCALE)]
			if not planes.has(key): planes[key] = []
			var axis := _dominant_axis(canonical); var polygon := PackedVector2Array()
			for point: Vector3 in points: polygon.append(_project(point, axis))
			planes[key].append({"surface": surface, "triangle": triangle, "points": points, "normal": normal, "area": doubled_area * 0.5, "axis": axis, "polygon": polygon, "bounds": _polygon_bounds(polygon), "source_flags": roundi(source_faces[i0].y) if source_encoded else -1, "source_order": roundi(source_faces[i0].x) if source_encoded else -1, "layer": 0})
	for key: String in planes:
		var group: Array = planes[key]; group.sort_custom(_face_before); var parents: Array = []; var by_surface := {}
		for overlay: Dictionary in group:
			var parent: Dictionary = {}; var supporting_layer := 0; var polygon: PackedVector2Array = overlay["polygon"]; var original_area := _polygon_area(polygon); var remaining: Array[PackedVector2Array] = [polygon]; var epsilon := DISTANCE_EPSILON * DISTANCE_EPSILON * maxf(1.0, original_area)
			for candidate: Dictionary in parents:
				if not (overlay["bounds"] as Rect2).intersects(candidate["bounds"]): continue
				var outside := _subtract_triangle(polygon, candidate["polygon"]); var outside_area := 0.0
				for piece: PackedVector2Array in outside: outside_area += _polygon_area(piece)
				if original_area - outside_area <= epsilon: continue
				if parent.is_empty() or int(candidate["layer"]) > supporting_layer: parent = candidate
				supporting_layer = maxi(supporting_layer, int(candidate["layer"])); var next_remaining: Array[PackedVector2Array] = []
				for piece: PackedVector2Array in remaining: next_remaining.append_array(_subtract_triangle(piece, candidate["polygon"]))
				remaining = next_remaining
			var uncovered_area := 0.0
			for piece: PackedVector2Array in remaining: uncovered_area += _polygon_area(piece)
			var marked: bool = not parent.is_empty() and (partial or uncovered_area <= epsilon or _source_decorator(overlay)); overlay["layer"] = mini(supporting_layer + 1, 127) if marked else 0; parents.append(overlay)
			if not marked: continue
			var surface_index := int(overlay["surface"])
			if not by_surface.has(surface_index): by_surface[surface_index] = {"surface_index": surface_index, "triangle_indices": PackedInt32Array(), "layers": PackedInt32Array(), "render_normals": PackedVector3Array(), "parent_surfaces": PackedInt32Array(), "parent_triangles": PackedInt32Array()}
			var entry: Dictionary = by_surface[surface_index]; entry["triangle_indices"].append(int(overlay["triangle"])); entry["layers"].append(int(overlay["layer"])); entry["render_normals"].append(parent["normal"]); entry["parent_surfaces"].append(int(parent["surface"])); entry["parent_triangles"].append(int(parent["triangle"]))
		for surface_index: int in by_surface: result.append(by_surface[surface_index])
	return result
static func _placement(node: MeshInstance3D) -> bool: return str(node.name).begins_with("placement_")
static func _scannable(node: MeshInstance3D) -> bool:
	if node.mesh == null or bool(node.mesh.get_meta("coplanar_scanned", false)) or node.mesh.get_blend_shape_count() > 0: return false
	var skinned := false
	for surface in node.mesh.get_surface_count():
		var material := node.get_active_material(surface) as ShaderMaterial
		skinned = skinned or (node.mesh.surface_get_format(surface) & Mesh.ARRAY_FORMAT_BONES) != 0 or (material != null and material.shader != null and material.shader.resource_path != "res://shaders/native_model.gdshader")
	return not skinned
static func _surface_data(node: MeshInstance3D) -> Array:
	var surfaces: Array = []
	for surface in node.mesh.get_surface_count():
		if node.mesh.surface_get_primitive_type(surface) == Mesh.PRIMITIVE_TRIANGLES: surfaces.append({"surface": surface, "arrays": node.mesh.surface_get_arrays(surface)})
	return surfaces
static func _source_decorator(face: Dictionary) -> bool: return int(face["source_flags"]) >= 0 and (int(face["source_flags"]) & 0xC0) == 0x80
static func _face_before(first: Dictionary, second: Dictionary) -> bool:
	var first_decorator := _source_decorator(first); var second_decorator := _source_decorator(second)
	if first_decorator != second_decorator: return not first_decorator
	if int(first["source_order"]) >= 0 and int(second["source_order"]) >= 0 and int(first["source_order"]) != int(second["source_order"]): return int(first["source_order"]) > int(second["source_order"])
	return _comes_after(second, first)
static func _polygon_bounds(polygon: PackedVector2Array) -> Rect2:
	var bounds := Rect2(polygon[0], Vector2.ZERO)
	for point: Vector2 in polygon: bounds = bounds.expand(point)
	return bounds
static func _polygon_area(polygon: PackedVector2Array) -> float:
	var area := 0.0
	for index in polygon.size(): area += polygon[index].cross(polygon[(index + 1) % polygon.size()])
	return absf(area) * 0.5
static func _half_plane(polygon: PackedVector2Array, first: Vector2, second: Vector2, orientation: float, inside: bool) -> PackedVector2Array:
	var result := PackedVector2Array()
	for index in polygon.size():
		var point := polygon[index]; var next := polygon[(index + 1) % polygon.size()]; var distance := orientation * (second - first).cross(point - first); var next_distance := orientation * (second - first).cross(next - first); var kept: bool = distance >= 0.0 if inside else distance <= 0.0; var next_kept: bool = next_distance >= 0.0 if inside else next_distance <= 0.0
		if kept: result.append(point)
		if kept != next_kept: result.append(point.lerp(next, distance / (distance - next_distance)))
	return result
static func _subtract_triangle(polygon: PackedVector2Array, triangle: PackedVector2Array) -> Array[PackedVector2Array]:
	var result: Array[PackedVector2Array] = []; var remaining := polygon; var orientation := signf((triangle[1] - triangle[0]).cross(triangle[2] - triangle[0]))
	for edge in 3:
		var first := triangle[edge]; var second := triangle[(edge + 1) % 3]; var outside := _half_plane(remaining, first, second, orientation, false)
		if _polygon_area(outside) > 0.000000000001: result.append(outside)
		remaining = _half_plane(remaining, first, second, orientation, true)
		if remaining.size() < 3: break
	return result
static func _parent_faces(group: Array) -> Array:
	var result := group.duplicate(); var edges := {}
	for face: Dictionary in group:
		var points: Array = face["points"]
		for corner in 3:
			var first: Vector3 = points[corner]; var second: Vector3 = points[(corner + 1) % 3]; var first_key := "%d:%d:%d" % [roundi(first.x * PLANE_SCALE), roundi(first.y * PLANE_SCALE), roundi(first.z * PLANE_SCALE)]; var second_key := "%d:%d:%d" % [roundi(second.x * PLANE_SCALE), roundi(second.y * PLANE_SCALE), roundi(second.z * PLANE_SCALE)]; var key := first_key + ":" + second_key if first_key < second_key else second_key + ":" + first_key
			for prior: Dictionary in edges.get(key, []):
				var projected := PackedVector2Array()
				for point: Vector3 in points: projected.append(_project(point, int(face["axis"])))
				for point: Vector3 in prior["points"]: projected.append(_project(point, int(face["axis"])))
				var polygon := Geometry2D.convex_hull(projected); var area := 0.0
				for vertex in polygon.size(): area += polygon[vertex].cross(polygon[(vertex + 1) % polygon.size()])
				area = absf(area) * 0.5
				var combined_area := float(face["area"]) + float(prior["area"]); var normal: Vector3 = face["normal"]
				if absf(area - combined_area * absf(normal[int(face["axis"])])) > DISTANCE_EPSILON * maxf(1.0, area): continue
				var parent: Dictionary = (face if _comes_after(face, prior) else prior).duplicate(); parent["polygon"] = polygon; parent["area"] = combined_area; result.append(parent)
			if not edges.has(key): edges[key] = []
			edges[key].append(face)
	return result
static func _inside_face(points: Array, face: Dictionary, axis: int) -> bool:
	if not face.has("polygon"): return _inside_triangle(points, face["points"], axis)
	for point: Vector3 in points:
		if not Geometry2D.is_point_in_polygon(_project(point, axis), face["polygon"]): return false
	return true
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
