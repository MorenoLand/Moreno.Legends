extends RefCounted
static var catalog: Dictionary = {}
static func descriptor(stage: String) -> Dictionary:
	if catalog.is_empty() and FileAccess.file_exists("res://assets/levels/ST01/flutter_travel.json"): catalog = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/ST01/flutter_travel.json"))
	return catalog.get("docks", {}).get(stage, {})
static func exterior_hatch(stage: String) -> Dictionary:
	var data := descriptor(stage); var source := descriptor("ST08")
	if data.is_empty() or source.is_empty(): return {}
	var hull: Array = source["position_raw"]; var door: Array = source["boarding_raw"]; var target: Array = data["position_raw"]; var relative := Vector3(-float(door[0] - hull[0]), -float(door[1] - hull[1]), float(door[2] - hull[2])) / 256.0; var yaw := -float(data["yaw_raw"]) * TAU / 4096.0
	var position := Vector3(-float(target[0]), -float(target[1]), float(target[2])) / 256.0 + Basis(Vector3.UP, yaw) * relative; var boarding: Array = data["boarding_raw"]
	if int(boarding[1]) <= int(target[1]): position.y = -float(boarding[1]) / 256.0
	return {"position": position, "yaw": yaw - float(door[3]) * TAU / 4096.0}
static func ensure(host: Node3D) -> Node3D:
	var stage := str(host.manifest_path.get_base_dir().get_file()); var area := int(host.areas[host.area_picker.selected]["index"])
	if str(host.parked_location.get("stage", "")) != stage or int(host.parked_location.get("area", -1)) != area: return null
	for node: Node3D in host.get_tree().get_nodes_in_group("parked_flutter_hulls"):
		if host.is_ancestor_of(node) and node.visible: return node
	if not await AssetStore.ensure_stage("ST01"): return null
	var data := descriptor(stage)
	if data.is_empty() or int(data["area"]) != area: return null
	var story := int(host.native_context.get("native_save_byte14", 0)); var craft: Dictionary = data.get("arrival_craft", {}); var craft_parent: Node3D = host.room_stream.room_root(stage, area) if host.streaming_rooms else host.level
	if story < int(data.get("minimum_save_byte14", 0)):
		if not craft.is_empty() and craft["save_byte14"].any(func(value: Variant) -> bool: return int(value) == story) and craft_parent.get_node_or_null("ArrivalCraft") == null: _place_craft(host, craft_parent, craft)
		return null
	var scene := load(str(data["model_file"])) as PackedScene
	if scene == null: push_error("Cannot load docked Flutter hull for " + stage); return null
	var parent: Node3D = host.room_stream.room_root(stage, area) if host.streaming_rooms else host.level; var hull := scene.instantiate() as Node3D; parent.add_child(hull); hull.name = "DockedFlutter"; var point: Array = data["position_raw"]; hull.position = Vector3(-float(point[0]), -float(point[1]), float(point[2])) / 256.0; hull.rotation.y = -float(data["yaw_raw"]) * TAU / 4096.0; hull.add_to_group("parked_flutter_hulls"); hull.set_meta("native_role", "player_vehicle"); preload("res://scripts/world/rendering/native_material.gd").apply(hull); preload("res://scripts/world/rendering/native_material.gd").depth_cue(hull, host.depth_cue_parameters)
	var meshes: Array[Node] = hull.find_children("*", "MeshInstance3D", true, false)
	if hull is MeshInstance3D: meshes.push_front(hull)
	for mesh: MeshInstance3D in meshes:
		if mesh.mesh == null: continue
		for layer in [1, 4]:
			var body := StaticBody3D.new(); body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.mesh.create_trimesh_shape(); body.add_child(shape); mesh.add_child(body)
	return hull
static func _place_craft(host: Node3D, parent: Node3D, craft: Dictionary) -> void:
	var scene := load(str(craft["model_file"])) as PackedScene
	if scene == null: push_error("Cannot load the arrival craft"); return
	var node := scene.instantiate() as Node3D; parent.add_child(node); node.name = "ArrivalCraft"; var point: Array = craft["position_raw"]; node.position = Vector3(-float(point[0]), -float(point[1]), float(point[2])) / 256.0; node.rotation.y = -float(craft["yaw_raw"]) * TAU / 4096.0
	preload("res://scripts/world/rendering/native_material.gd").apply(node); preload("res://scripts/world/rendering/native_material.gd").depth_cue(node, host.depth_cue_parameters)
	for mesh: MeshInstance3D in node.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		for layer in [1, 4]:
			var body := StaticBody3D.new(); body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.mesh.create_trimesh_shape(); body.add_child(shape); mesh.add_child(body)
static func land(host: Node3D, hull: Node3D) -> bool:
	if not is_instance_valid(hull): return false
	var stage := str(host.manifest_path.get_base_dir().get_file()); var data := descriptor(stage); var source := descriptor("ST08"); var point: Array = source["position_raw"]; var origin := Vector3(-float(point[0]), -float(point[1]), float(point[2])) / 256.0; var basis := Basis(Vector3.UP, hull.global_rotation.y); var rig := Node3D.new(); host.add_child(rig); rig.name = "FlutterLanding"; rig.global_transform = Transform3D(basis, hull.global_position - basis * origin); hull.hide()
	var success: bool = await host.native_scenes.run_scene(rig, "res://assets/levels/ST01/landing.json", int(data["area"]), false, {"0x800f2670": str(data["model_file"])})
	if is_instance_valid(hull): hull.show()
	rig.queue_free(); return success
