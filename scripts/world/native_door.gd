extends Node3D
signal sound_requested(sound_id: int)
var profile: Dictionary = {}
var leaves: Array[Node3D] = []
var velocities: Array[Vector3] = []
var original_nodes: Array[MeshInstance3D] = []
var original_meshes: Dictionary = {}
var opened_meshes: Dictionary = {}
var original_shapes: Dictionary = {}
var ready_to_open := false
func configure(level: Node3D, stage: String, route: Dictionary) -> bool:
	profile = route.get("native_door", {})
	if profile.get("style", "") != "sliding_pair" or not is_inside_tree(): return false
	var file := FileAccess.open("res://assets/stage_props/manifest.json", FileAccess.READ)
	if file == null: return false
	var manifest: Dictionary = JSON.parse_string(file.get_as_text()); var resources: Array = manifest.get("stages", {}).get(stage, {}).get("native_doors", []); var scenes: Array[PackedScene] = []; var models: Array[Dictionary] = []
	for variant: int in profile["variants"]:
		var model: Dictionary = {}
		for candidate: Dictionary in resources:
			if int(candidate.get("controller_class", 1)) == 3 and int(candidate["variant"]) == variant: model = candidate; break
		if model.is_empty(): push_error("Missing native sliding door resource %s/%d" % [stage, variant]); return false
		var scene := load("res://assets/stage_props/" + str(model["model_file"])) as PackedScene
		if scene == null: return false
		scenes.append(scene); models.append(model)
	var source_panel: Dictionary = profile.get("source_panel", {})
	if source_panel.is_empty(): return false
	for node: MeshInstance3D in level.find_children("*", "MeshInstance3D", true, false):
		if str(node.name) != str(source_panel["node"]): continue
		var removed := {}
		for quad: Dictionary in source_panel["quads"]:
			var surface := int(quad.get("primitive_index", source_panel["primitive_index"])); var triangles: Array = removed.get(surface, []); triangles.append_array(quad["triangles_local"]); removed[surface] = triangles
		original_nodes.append(node); original_meshes[node] = node.mesh; opened_meshes[node] = preload("res://scripts/world/room_stream.gd")._mesh_without_faces(node.mesh, removed)
	if original_nodes.is_empty(): push_error("Missing native sliding door panel " + str(source_panel["node"])); return false
	var raw: Array = route["source_transform_raw"]; var yaw := int(raw[3]); var q := (yaw & 4095) >> 10; var directions := [-1, 0, 1, 0, -1]; var a := int(directions[q]); var b := int(directions[q + 1]); var c := int(profile["offset_raw"][0]); var e := int(profile["offset_raw"][1]); var speed := int((absi(c) - 8) / 10); var movement_q := ((yaw + 0x200) & 4095) >> 10
	for index in 2:
		var signed_c := c if index == 0 else -c; var pivot := Node3D.new(); add_child(pivot); pivot.global_position = level.to_global(Vector3(-float(raw[0] + signed_c * a + e * b), -float(raw[1]), float(raw[2] + signed_c * b - e * a)) / 256.0); pivot.rotation.y = level.rotation.y - float((yaw + 0x800) & 4095) * TAU / 4096.0
		var panel := scenes[index].instantiate() as Node3D; pivot.add_child(panel); var scale: Array = models[index]["native_scale_raw"]; panel.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0; preload("res://scripts/world/native_material.gd").apply(panel, 128.0)
		for mesh: MeshInstance3D in panel.find_children("*", "MeshInstance3D", true, false):
			var geometry := mesh.mesh.create_trimesh_shape()
			if geometry == null: continue
			for layer in [1, 4]:
				var body := StaticBody3D.new(); body.collision_layer = 0; body.set_meta("native_layer", layer); body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = geometry.duplicate() if layer == 4 else geometry
				if layer == 4: (shape.shape as ConcavePolygonShape3D).backface_collision = true
				body.add_child(shape); mesh.add_child(body)
		pivot.hide(); leaves.append(pivot); var signed_speed := speed if index == 0 else -speed; velocities.append(level.global_basis * Vector3(-signed_speed * int(directions[movement_q]), 0, signed_speed * int(directions[movement_q + 1])) / 256.0)
	ready_to_open = true; return true
func open() -> void:
	if not ready_to_open: return
	for leaf: Node3D in leaves:
		leaf.show()
		for body: StaticBody3D in leaf.find_children("*", "StaticBody3D", true, false): body.collision_layer = int(body.get_meta("native_layer"))
	for node: MeshInstance3D in original_nodes:
		node.mesh = opened_meshes[node]
		for body: StaticBody3D in node.find_children("*", "StaticBody3D", true, false):
			for shape: CollisionShape3D in body.find_children("*", "CollisionShape3D", true, false):
				original_shapes[shape] = shape.shape; shape.shape = node.mesh.create_trimesh_shape()
				if body.collision_layer == 4 and shape.shape is ConcavePolygonShape3D: (shape.shape as ConcavePolygonShape3D).backface_collision = true
	sound_requested.emit(int(profile["sounds"][0])); await _move(1.0, int(profile["opening_ticks"]))
func hold() -> void:
	if not ready_to_open: return
	sound_requested.emit(int(profile["sounds"][1])); await get_tree().create_timer(float(profile["hold_ticks"]) / float(profile["tick_rate"])).timeout
func close() -> void:
	if not ready_to_open: return
	sound_requested.emit(int(profile["sounds"][2])); await _move(-1.0, int(profile["closing_ticks"]))
func _move(direction: float, ticks: int) -> void:
	var tween := create_tween().set_parallel(true)
	for index in leaves.size(): tween.tween_property(leaves[index], "global_position", leaves[index].global_position + velocities[index] * direction * ticks, float(ticks) / float(profile["tick_rate"]))
	await tween.finished
func dispose() -> void:
	for node: MeshInstance3D in original_nodes:
		if is_instance_valid(node): node.mesh = original_meshes[node]
	for shape: CollisionShape3D in original_shapes:
		if is_instance_valid(shape): shape.shape = original_shapes[shape]
	ready_to_open = false; queue_free()
