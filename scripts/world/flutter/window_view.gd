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
# Planar faces of a room's window panes (same vertex/UV test as shaders/window.gdshader), as {plane, lateral, y} in world space with the plane facing away from `inside`; lateral is dot(xz, (-n.z, n.x)).
static func pane_faces(scene: Node3D, stage: String, area: int, offset: Vector3, inside: Vector3) -> Array[Dictionary]:
	var groups := {}
	for entry: Dictionary in ROOMS.get("%s:%d" % [stage, area], []):
		var node := scene.find_child(str(entry["node"]), true, false) as MeshInstance3D
		if node == null or node.mesh == null or node.mesh.get_surface_count() <= int(entry["surface"]): continue
		var local := Transform3D.IDENTITY; var chain: Node = node
		while chain != scene and chain is Node3D: local = (chain as Node3D).transform * local; chain = chain.get_parent()
		local.origin += offset
		var arrays := node.mesh.surface_get_arrays(int(entry["surface"])); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]; var indices: Variant = arrays[Mesh.ARRAY_INDEX]
		var count: int = indices.size() if indices != null and indices.size() > 0 else vertices.size()
		for first in range(0, count, 3):
			var corners: Array[Vector3] = []; var pane := true
			for corner in 3:
				var index: int = indices[first + corner] if indices != null and indices.size() > 0 else first + corner; var point := vertices[index]; var uv := uvs[index]
				pane = pane and point.clamp(entry["min"] - Vector3.ONE * 0.002, entry["max"] + Vector3.ONE * 0.002) == point and uv.clamp(entry["uv_min"] - Vector2.ONE * 0.002, entry["uv_max"] + Vector2.ONE * 0.002) == uv
				corners.append(local * point)
			var normal := (corners[1] - corners[0]).cross(corners[2] - corners[0])
			if not pane or normal.length() < 0.000001 or absf(normal.normalized().y) > 0.01: continue
			normal = Vector3(normal.x, 0.0, normal.z).normalized()
			var centre := (corners[0] + corners[1] + corners[2]) / 3.0
			if normal.dot(centre - inside) < 0.0: normal = -normal
			var key := Vector3(snappedf(normal.x, 0.001), snappedf(normal.z, 0.001), snappedf(normal.dot(centre), 0.001))
			var group: Dictionary = groups.get(key, {"plane": Vector4(normal.x, 0.0, normal.z, -normal.dot(centre)), "lateral": Vector2(INF, -INF), "y": Vector2(INF, -INF)})
			for corner: Vector3 in corners:
				var lateral := corner.x * -normal.z + corner.z * normal.x
				group["lateral"] = Vector2(minf(group["lateral"].x, lateral), maxf(group["lateral"].y, lateral)); group["y"] = Vector2(minf(group["y"].x, corner.y), maxf(group["y"].y, corner.y))
			groups[key] = group
	var faces: Array[Dictionary] = []
	for group: Dictionary in groups.values(): faces.append(group)
	return faces
