extends Node3D
signal room_activated(stage: String, area: int)
signal door_sound(sound_id: int)
var rooms: Dictionary = {}
var room_info: Dictionary = {}
var room_bounds: Dictionary = {}
var portal_layout: Array = []
var ladder_transitions: Array = []
var opened_portals: Dictionary = {}
var opened_from: Dictionary = {}
var opened_origin_distance: Dictionary = {}
var portal_leaves: Dictionary = {}
var closing_portals: Dictionary = {}
var portal_camera_sides: Dictionary = {}
var mesh_nodes: Dictionary = {}
var source_meshes: Dictionary = {}
var room_offsets: Dictionary = {}
var loading_rooms: Dictionary = {}
var floor_supports: Dictionary = {}
var active_room_key := ""
var previous_room_key := ""
var requested_room_key := ""
var visible_neighbor_keys: Dictionary = {}
var body_radius := 0.12
var props: Dictionary = {}
var props_loaded := false
var parked_exterior: Node3D
var exterior_request := 0
var external_routes: Array = []
func clear_parked_exterior() -> void:
	exterior_request += 1
	if is_instance_valid(parked_exterior): parked_exterior.queue_free()
	parked_exterior = null
func set_parked_exterior(stage: String, area: int) -> bool:
	clear_parked_exterior()
	var request := exterior_request
	var paired: Dictionary = {}
	for route: Dictionary in external_routes:
		if str(route["destination_stage"]) == stage and int(route["destination_area"]) == area: paired = route; break
	if paired.is_empty(): return false
	if not await AssetStore.ensure_stage(stage) or request != exterior_request: return false
	var doors_path := "res://assets/levels/%s/doors.json" % stage
	var doors: Variant = JSON.parse_string(FileAccess.get_file_as_string(doors_path)) if FileAccess.file_exists(doors_path) else null
	if not doors is Dictionary: return false
	var reciprocal: Dictionary = {}
	for route: Dictionary in doors.get("area_transitions", []):
		if int(route["source_area"]) == area and str(route["destination_stage"]) == str(paired["source_stage"]) and int(route["destination_area"]) == int(paired["source_area"]): reciprocal = route; break
	if reciprocal.is_empty(): return false
	var inside: Array = paired["source_transform_raw"]; var outside: Array = reciprocal["source_transform_raw"]
	if int(inside[1]) == -1 or int(outside[1]) == -1: return false
	var interior_anchor := Vector3(-float(inside[0]), -float(inside[1]), float(inside[2])) / 256.0 + offset_for(str(paired["source_stage"]), int(paired["source_area"]))
	var exterior_anchor := Vector3(-float(outside[0]), -float(outside[1]), float(outside[2])) / 256.0
	var interior_yaw := -float(inside[3]) * TAU / 4096.0
	var exterior_yaw := -float(outside[3]) * TAU / 4096.0 + PI
	var manifest_path := "res://assets/levels/%s/manifest.json" % stage
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) if FileAccess.file_exists(manifest_path) else null
	if not manifest is Dictionary: return false
	var entry: Dictionary = {}
	for candidate: Dictionary in manifest.get("areas", []):
		if int(candidate["index"]) == area: entry = candidate; break
	if entry.is_empty(): return false
	var scene: PackedScene = await _threaded_scene("res://assets/levels/%s/%s" % [stage, str(entry["file"])])
	if scene == null or request != exterior_request: return false
	var exterior := scene.instantiate() as Node3D
	if exterior == null: return false
	var rotation_basis := Basis(Vector3.UP, interior_yaw - exterior_yaw)
	exterior.transform = Transform3D(rotation_basis, interior_anchor - rotation_basis * exterior_anchor)
	exterior.name = "ParkedExterior"
	exterior.process_mode = Node.PROCESS_MODE_DISABLED
	for collider: CollisionObject3D in exterior.find_children("*", "CollisionObject3D", true, false): collider.collision_layer = 0; collider.collision_mask = 0; collider.queue_free()
	add_child(exterior)
	preload("res://scripts/world/native_material.gd").apply(exterior)
	await _load_room_props(exterior, stage, area)
	if request != exterior_request:
		exterior.queue_free()
		return false
	for collider: CollisionObject3D in exterior.find_children("*", "CollisionObject3D", true, false): collider.collision_layer = 0; collider.collision_mask = 0; collider.queue_free()
	parked_exterior = exterior
	return true
func configure(layout_path: String, start_stage: String, start_area: int, player_radius: float = 0.12) -> bool:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(layout_path)) if FileAccess.file_exists(layout_path) else null
	if not data is Dictionary or not data.get("rooms", []) is Array: return false
	body_radius = player_radius
	for entry: Dictionary in data["rooms"]:
		var stage := str(entry["stage"]); var area := int(entry["area"]); var key := _room_key(stage, area); room_info[key] = entry; room_offsets[key] = Vector3(float(entry["world_offset"][0]), float(entry["world_offset"][1]), float(entry["world_offset"][2])); var local_bounds: Dictionary = entry["local_bounds"]; var minv: Array = local_bounds["min"]; var maxv: Array = local_bounds["max"]; room_bounds[key] = AABB(Vector3(float(minv[0]), float(minv[1]), float(minv[2])) + room_offsets[key], Vector3(float(maxv[0] - minv[0]), float(maxv[1] - minv[1]), float(maxv[2] - minv[2])))
	portal_layout = data["portals"]; ladder_transitions = data.get("ladder_transitions", []); external_routes = data.get("external_routes", []); active_room_key = _room_key(start_stage, start_area)
	if not await _ensure_room_loaded(start_stage, start_area): return false
	_refresh_room_state()
	return true
func _ensure_room_loaded(stage: String, area: int) -> bool:
	var key := _room_key(stage, area)
	if rooms.has(key): return true
	if not room_info.has(key): return false
	if loading_rooms.has(key):
		while loading_rooms.has(key): await get_tree().process_frame
		return rooms.has(key)
	loading_rooms[key] = true
	if not await AssetStore.ensure_stage(stage):
		loading_rooms.erase(key)
		return false
	if not props_loaded:
		var props_path := "res://assets/stage_props/manifest.json"
		if FileAccess.file_exists(props_path):
			var props_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(props_path))
			if props_data is Dictionary: props = props_data.get("stages", {})
		props_loaded = true
	var entry: Dictionary = room_info[key]; var scene_path := "res://assets/levels/%s/%s" % [stage, str(entry["file"])]; var scene: PackedScene = await _threaded_scene(scene_path)
	if scene == null:
		loading_rooms.erase(key)
		push_error("Cannot preload room " + scene_path)
		return false
	var room := scene.instantiate() as Node3D; room.name = key.replace(":", "_"); room.position = room_offsets[key]; add_child(room); preload("res://scripts/world/native_material.gd").apply(room); rooms[key] = room; var nodes: Dictionary = {}; mesh_nodes[key] = nodes
	for item in room.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := item as MeshInstance3D
		if mesh_node.mesh == null: continue
		nodes[mesh_node.name] = mesh_node; source_meshes[_mesh_key(key, mesh_node.name)] = mesh_node.mesh; _add_collision(mesh_node, mesh_node.mesh)
	await _load_room_props(room, stage, area)
	preload("res://scripts/world/window_view.gd").apply(room, stage, area)
	loading_rooms.erase(key)
	var opened_nodes := {}
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		for side in [[portal["source"], portal["source_panel"]], [portal["destination"], portal["destination_panel"]]]:
			if _room_key(str(side[0]["stage"]), int(side[0]["area"])) == key: opened_nodes[str(side[1]["node"])] = true
	for node_name in opened_nodes: _refresh_open_meshes(key, str(node_name))
	_refresh_room_state()
	return true
func _load_room_props(room: Node3D, stage: String, area: int) -> void:
	var source: Dictionary = props.get(stage, {})
	for entry: Dictionary in source.get("instances", []):
		if int(entry["area"]) != area: continue
		var packed: PackedScene = await _threaded_scene("res://assets/stage_props/" + str(entry["model_file"]))
		if packed == null: continue
		var prop := packed.instantiate() as Node3D
		room.add_child(prop)
		var position: Array = entry["position"]
		prop.position = Vector3(float(position[0]), float(position[1]), float(position[2]))
		prop.rotation.y = float(entry["yaw_turns"]) * TAU
		for model: Dictionary in source.get("models", []):
			if int(model["model_index"]) != int(entry["model_index"]): continue
			var scale: Array = model.get("native_scale_raw", [512, 512, 512])
			prop.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0
			var animation := prop.find_child("AnimationPlayer", true, false) as AnimationPlayer
			if animation != null:
				for clip: Dictionary in model.get("animations", []):
					if int(clip["slot"]) == int(entry["control"]): animation.play(str(clip["name"])); animation.advance(0)
		preload("res://scripts/world/native_material.gd").apply(prop, 128.0)
func _threaded_scene(path: String) -> PackedScene:
	var status := ResourceLoader.load_threaded_get_status(path)
	if status == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
		var request_error := ResourceLoader.load_threaded_request(path, "PackedScene", true, ResourceLoader.CACHE_MODE_REUSE)
		if request_error != OK and request_error != ERR_BUSY: return null
		status = ResourceLoader.load_threaded_get_status(path)
	while status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		await get_tree().process_frame
		status = ResourceLoader.load_threaded_get_status(path)
	return ResourceLoader.load_threaded_get(path) as PackedScene if status == ResourceLoader.THREAD_LOAD_LOADED else null
func offset_for(stage: String, area: int) -> Vector3: return room_offsets.get(_room_key(stage, area), Vector3.ZERO)
func bounds_for(stage: String, area: int) -> AABB: return room_bounds.get(_room_key(stage, area), AABB())
func has_room(stage: String, area: int) -> bool: return room_info.has(_room_key(stage, area))
func has_stage(stage: String) -> bool:
	for key in room_info:
		if str(key).begins_with(stage + ":"): return true
	return false
func select_room(stage: String, area: int) -> bool:
	if not await _ensure_room_loaded(stage, area): return false
	var key := _room_key(stage, area)
	if active_room_key != key: previous_room_key = active_room_key
	active_room_key = key
	requested_room_key = ""
	_refresh_room_state()
	room_activated.emit(stage, area)
	_evict_unused()
	return true
func open_route(stage: String, area: int, route: Dictionary, player_position: Vector3 = Vector3.ZERO, camera_position: Vector3 = Vector3.ZERO) -> bool:
	var destination_stage := str(route.get("destination_stage", stage)); var destination_area := int(route["destination_area"])
	for portal: Dictionary in portal_layout:
		var forward := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area and str(portal["destination"]["stage"]) == destination_stage and int(portal["destination"]["area"]) == destination_area
		var reverse := str(portal["destination"]["stage"]) == stage and int(portal["destination"]["area"]) == area and str(portal["source"]["stage"]) == destination_stage and int(portal["source"]["area"]) == destination_area
		if not forward and not reverse: continue
		var key := _portal_key(portal)
		while closing_portals.has(key): await get_tree().process_frame
		requested_room_key = _room_key(destination_stage, destination_area)
		if not await _ensure_room_loaded(destination_stage, destination_area): requested_room_key = ""; return false
		opened_portals[key] = true
		opened_from[key] = _room_key(stage, area); var source_side := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var sign := _outward_sign(portal, source_side); var plane := float(portal["world_center"][axis]); opened_origin_distance[key] = (player_position[axis] - plane) * sign
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		_refresh_open_meshes(source_key, str(portal["source_panel"]["node"]))
		_refresh_open_meshes(destination_key, str(portal["destination_panel"]["node"]))
		requested_room_key = ""
		_refresh_room_state()
		if not portal_leaves.has(key) and not await _open_leaf(portal, forward): _close_portal(key); return false
		_evict_unused()
		return true
	return false
func is_ladder_route(stage: String, area: int, route: Dictionary) -> bool:
	var destination_stage := str(route.get("destination_stage", stage)); var destination_area := int(route["destination_area"])
	for transition: Dictionary in ladder_transitions:
		var forward := str(transition["source"]["stage"]) == stage and int(transition["source"]["area"]) == area and str(transition["destination"]["stage"]) == destination_stage and int(transition["destination"]["area"]) == destination_area
		var reverse := str(transition["destination"]["stage"]) == stage and int(transition["destination"]["area"]) == area and str(transition["source"]["stage"]) == destination_stage and int(transition["source"]["area"]) == destination_area
		if forward or reverse: return true
	return false
func close_cleared_portals(player_position: Vector3, camera_position: Vector3, radius: float) -> void:
	var close: Array[String] = []
	var render_changed := false
	for key in opened_portals:
		var portal: Dictionary = {}
		for candidate: Dictionary in portal_layout:
			if _portal_key(candidate) == str(key): portal = candidate; break
		if portal.is_empty(): continue
		var camera_axis := 0 if str(portal["normal_axis"]) == "x" else 2; var view_distance := (camera_position[camera_axis] - float(portal["world_center"][camera_axis])) * _outward_sign(portal, true); var camera_source: bool = portal_camera_sides.get(key, str(opened_from.get(key, "")) == _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])))
		if absf(view_distance) > 0.02:
			var source_side := view_distance < 0.0
			if source_side != camera_source or not portal_camera_sides.has(key): portal_camera_sides[key] = source_side; render_changed = true
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])); var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var plane := float(portal["world_center"][axis]); var open_side := str(opened_from.get(key, "")); var active_source := active_room_key == source_key; var active_destination := active_room_key == destination_key; var should_close := false
		if active_source or active_destination:
			var source_side := active_source; var outward := _outward_sign(portal, source_side); var body_distance := (player_position[axis] - plane) * outward; var camera_distance := (camera_position[axis] - plane) * outward
			if active_room_key == open_side: should_close = body_distance < float(opened_origin_distance.get(key, -INF)) - radius * 1.5 and camera_distance < 0.0
			else: should_close = body_distance < -(radius + 0.03) and camera_distance < -(radius + 0.03)
		else:
			var body_side_a := absf((player_position[axis] - plane) * _outward_sign(portal, true)); var body_side_b := absf((player_position[axis] - plane) * _outward_sign(portal, false)); var camera_side_a := absf((camera_position[axis] - plane) * _outward_sign(portal, true)); var camera_side_b := absf((camera_position[axis] - plane) * _outward_sign(portal, false)); should_close = minf(body_side_a, body_side_b) > radius * 1.5 and minf(camera_side_a, camera_side_b) > radius * 1.5
		var lateral := 2 if axis == 0 else 0; var lateral_clear := absf(player_position[lateral] - float(portal["world_center"][lateral])) > float(portal["shared_panel_size"][0]) * 0.5 + radius
		if lateral_clear and not _in_door_sweep(player_position, portal, radius) and not _in_door_sweep(camera_position, portal, radius): should_close = true
		if should_close: close.append(str(key))
	for key in close: _close_portal(key)
	if render_changed: _refresh_camera_masks()
func _in_door_sweep(point: Vector3, portal: Dictionary, radius: float) -> bool:
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]); var height := float(portal["shared_panel_size"][1]); var distance := (point[axis] - float(center[axis])) * _outward_sign(portal, true)
	return distance >= -radius and distance <= width + radius and absf(point[lateral] - float(center[lateral])) <= width * 0.5 + radius and absf(point.y - float(center[1])) <= height * 0.5 + radius
func _refresh_camera_masks() -> void:
	for room_key in mesh_nodes:
		var limits := PackedFloat32Array()
		for portal: Dictionary in portal_layout:
			var key := _portal_key(portal)
			if not opened_portals.has(key): continue
			var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
			if room_key != source_key and room_key != destination_key: continue
			var camera_source: bool = portal_camera_sides.get(key, str(opened_from.get(key, "")) == source_key); limits.append(-0.0001 if camera_source == (room_key == source_key) else 0.0001)
		limits.resize(16)
		for node: MeshInstance3D in mesh_nodes[room_key].values():
			for surface in node.mesh.get_surface_count():
				var material := node.get_active_material(surface) as ShaderMaterial
				if material != null: material.set_shader_parameter("room_clip_limits", limits)
func _close_portal(key: String) -> void:
	var portal := _portal_by_key(key)
	if portal.is_empty() or closing_portals.has(key): return
	if portal_leaves.has(key):
		closing_portals[key] = true
		var leaf: Node3D = portal_leaves[key]
		await create_tween().tween_property(leaf, "rotation:y", float(leaf.get_meta("closed_yaw")), 0.25).finished
		door_sound.emit(0xB9)
		portal_leaves.erase(key); closing_portals.erase(key); leaf.queue_free()
	opened_portals.erase(key); opened_from.erase(key); opened_origin_distance.erase(key); portal_camera_sides.erase(key)
	var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
	_refresh_open_meshes(source_key, str(portal["source_panel"]["node"])); _refresh_open_meshes(destination_key, str(portal["destination_panel"]["node"])); _refresh_room_state(); _evict_unused()
func _open_leaf(portal: Dictionary, source_side: bool) -> bool:
	var room: Dictionary = portal["source"]; var stage := str(room["stage"]); var room_key := _room_key(stage, int(room["area"])); var variant := int(portal["source_slot"]); var model: Dictionary = {}
	for candidate: Dictionary in props.get(stage, {}).get("native_doors", []):
		if int(candidate["variant"]) == variant: model = candidate; break
	if model.is_empty(): push_error("Missing native door resource %s variant %d" % [stage, variant]); return false
	var scene: PackedScene = await _threaded_scene("res://assets/stage_props/" + str(model["model_file"]))
	if scene == null: return false
	var raw: Array = portal["source_contact_raw"]; var yaw := int(raw[3]); var quadrant := (yaw & 4095) >> 10; var directions := [-1, 0, 1, 0, -1]; var a := int(directions[quadrant]); var b := int(directions[quadrant + 1]); var hinge: Vector3 = Vector3(-float(raw[0] + a * 80 + b * 64), -float(raw[1]), float(raw[2] + b * 80 - a * 64)) / 256.0 + room_offsets[room_key]; var closed_yaw := -float((yaw + 0x800) & 4095) * TAU / 4096.0
	var pivot := Node3D.new(); pivot.name = "OpenDoor_" + room_key.replace(":", "_"); add_child(pivot); pivot.global_position = hinge; pivot.rotation.y = closed_yaw; pivot.set_meta("closed_yaw", closed_yaw); var panel := scene.instantiate() as Node3D; pivot.add_child(panel); var scale: Array = model["native_scale_raw"]; panel.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0; preload("res://scripts/world/native_material.gd").apply(panel, 128.0)
	for node: MeshInstance3D in panel.find_children("*", "MeshInstance3D", true, false): _add_collision(node, node.mesh)
	portal_leaves[_portal_key(portal)] = pivot; door_sound.emit(0xB8); create_tween().tween_property(pivot, "rotation:y", closed_yaw - 0x3C0 * TAU / 4096.0, 0.25)
	return true
func _portal_by_key(key: String) -> Dictionary:
	for portal: Dictionary in portal_layout:
		if _portal_key(portal) == key: return portal
	return {}
func portal_for_route(stage: String, area: int, route: Dictionary) -> Dictionary:
	var destination_stage := str(route["destination_stage"]); var destination_area := int(route["destination_area"])
	for portal: Dictionary in portal_layout:
		var forward := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area and str(portal["destination"]["stage"]) == destination_stage and int(portal["destination"]["area"]) == destination_area
		var reverse := str(portal["destination"]["stage"]) == stage and int(portal["destination"]["area"]) == area and str(portal["source"]["stage"]) == destination_stage and int(portal["source"]["area"]) == destination_area
		if forward or reverse: return portal
	return {}
func is_panel_collider(portal: Dictionary, stage: String, area: int, collider: Object) -> bool:
	var source_side := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area; var panel: Dictionary = portal["source_panel"] if source_side else portal["destination_panel"]; var node: MeshInstance3D = mesh_nodes.get(_room_key(stage, area), {}).get(str(panel["node"]))
	return is_instance_valid(node) and node.get_node_or_null("RoomCollision_1") == collider
func crossed_room(previous: Vector3, current: Vector3, stage: String, area: int, body_height: float, body_radius: float) -> Dictionary:
	for portal: Dictionary in portal_layout:
		var source_side := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area; var destination_side := str(portal["destination"]["stage"]) == stage and int(portal["destination"]["area"]) == area
		if not source_side and not destination_side: continue
		if not opened_portals.has(_portal_key(portal)): continue
		var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var sign := _outward_sign(portal, source_side); var plane := float(portal["world_center"][axis]); var before := (previous[axis] - plane) * sign; var after := (current[axis] - plane) * sign
		if before > -body_radius or after <= -body_radius: continue
		var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]); var height := float(portal["shared_panel_size"][1]); var lateral_clearance := maxf(0.0, width * 0.5 - body_radius); var bottom := float(center[1]) - height * 0.5
		if absf(current[lateral] - float(center[lateral])) > lateral_clearance or current.y < bottom - 0.05 or current.y + body_height > bottom + height + 0.05: continue
		var target: Dictionary = portal["destination"] if source_side else portal["source"]
		return {"stage": str(target["stage"]), "area": int(target["area"]), "portal": portal}
	return {}
func _outward_sign(portal: Dictionary, source_side: bool) -> float:
	var side: Dictionary = portal["source_panel"] if source_side else portal["destination_panel"]; var raw: Array = portal["source_contact_raw"] if source_side else portal["reverse_source_contact_raw"]; var yaw := int(portal["source_yaw_raw"] if source_side else portal["reverse_source_yaw_raw"]); var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var yaw_radians := -float(yaw) * TAU / 4096.0; var contact := -float(raw[axis]) / 256.0 if axis == 0 else float(raw[axis]) / 256.0; var face := float(side["center"][axis]); var contact_sign := signf(face - contact)
	var player_forward := Vector3(-sin(yaw_radians), 0.0, -cos(yaw_radians)); var player_forward_sign := signf(player_forward[axis])
	return player_forward_sign if player_forward_sign != 0.0 else contact_sign
func _refresh_open_meshes(room_key: String, node_name: String) -> void:
	var key := _mesh_key(room_key, node_name); var mesh_node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(node_name)
	if not is_instance_valid(mesh_node): return
	var original: Mesh = source_meshes.get(key, mesh_node.mesh); var faces_by_surface := {}
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		for side in [[portal["source"], portal["source_panel"]], [portal["destination"], portal["destination_panel"]]]:
			if _room_key(str(side[0]["stage"]), int(side[0]["area"])) != room_key or str(side[1]["node"]) != node_name: continue
			for quad: Dictionary in side[1]["quads"]:
				var surface := int(quad.get("primitive_index", side[1]["primitive_index"])); var triangles: Array = faces_by_surface.get(surface, []); triangles.append_array(quad["triangles_local"]); faces_by_surface[surface] = triangles
	mesh_node.mesh = _mesh_without_faces(original, faces_by_surface)
	_refresh_collision(mesh_node, mesh_node.mesh)
	var entry: Dictionary = room_info[room_key]
	preload("res://scripts/world/window_view.gd").apply(rooms[room_key], str(entry["stage"]), int(entry["area"]))
func _mesh_without_faces(source: Mesh, faces_by_surface: Dictionary) -> Mesh:
	if not source is ArrayMesh: return source
	var result := ArrayMesh.new()
	for surface in source.get_surface_count():
		var arrays: Array = source.surface_get_arrays(surface); var triangles: Array = faces_by_surface.get(surface, []); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		if not triangles.is_empty() and not vertices.is_empty():
			var wanted := {}
			for tri: Array in triangles: wanted[_triangle_key(tri[0], tri[1], tri[2])] = true
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			if indices.is_empty(): arrays = _remove_unindexed(arrays, vertices, wanted)
			else:
				var kept := PackedInt32Array()
				for i in range(0, indices.size(), 3):
					var signature := _triangle_key(vertices[indices[i]], vertices[indices[i + 1]], vertices[indices[i + 2]])
					if wanted.has(signature): continue
					kept.append(indices[i]); kept.append(indices[i + 1]); kept.append(indices[i + 2])
				if kept.is_empty(): kept = PackedInt32Array([0, 0, 0])
				arrays[Mesh.ARRAY_INDEX] = kept
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays)
		var new_surface := result.get_surface_count() - 1; var material := source.surface_get_material(surface)
		if material != null: result.surface_set_material(new_surface, material)
		result.surface_set_name(new_surface, source.surface_get_name(surface))
	return result
func _remove_unindexed(arrays: Array, vertices: PackedVector3Array, wanted: Dictionary) -> Array:
	var kept := PackedInt32Array()
	for i in range(0, vertices.size(), 3):
		if wanted.has(_triangle_key(vertices[i], vertices[i + 1], vertices[i + 2])): continue
		kept.append(i); kept.append(i + 1); kept.append(i + 2)
	if kept.is_empty():
		arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
		for slot in range(1, Mesh.ARRAY_MAX): arrays[slot] = _degenerate_attribute(arrays[slot], vertices.size())
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 0, 0])
		return arrays
	for slot in range(Mesh.ARRAY_MAX):
		if slot == Mesh.ARRAY_INDEX or arrays[slot] == null: continue
		arrays[slot] = _filter_attribute(arrays[slot], kept, vertices.size())
	return arrays
func _filter_attribute(values: Variant, vertices: PackedInt32Array, vertex_count: int) -> Variant:
	if values is PackedVector2Array:
		var vector2_result := PackedVector2Array(); for index in vertices: vector2_result.append(values[index]); return vector2_result
	if values is PackedVector3Array:
		var vector3_result := PackedVector3Array(); for index in vertices: vector3_result.append(values[index]); return vector3_result
	if values is PackedVector4Array:
		var vector4_result := PackedVector4Array(); for index in vertices: vector4_result.append(values[index]); return vector4_result
	if values is PackedColorArray:
		var color_result := PackedColorArray(); for index in vertices: color_result.append(values[index]); return color_result
	if values is PackedFloat32Array or values is PackedFloat64Array or values is PackedInt32Array or values is PackedInt64Array or values is PackedByteArray:
		var stride := int(values.size() / vertex_count); var packed_result: Variant = values.duplicate(); packed_result.clear()
		for index in vertices:
			for component in stride: packed_result.append(values[index * stride + component])
		return packed_result
	return values
func _degenerate_attribute(values: Variant, old_vertex_count: int) -> Variant:
	if values is PackedVector2Array: return PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
	if values is PackedVector3Array: return PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP])
	if values is PackedVector4Array: return PackedVector4Array([Vector4.ZERO, Vector4.ZERO, Vector4.ZERO])
	if values is PackedColorArray: return PackedColorArray([Color.WHITE, Color.WHITE, Color.WHITE])
	if values is PackedFloat32Array or values is PackedFloat64Array or values is PackedInt32Array or values is PackedInt64Array or values is PackedByteArray:
		var stride := int(values.size() / old_vertex_count) if old_vertex_count > 0 else 1; var packed_result: Variant = values.duplicate(); packed_result.clear()
		for component in stride * 3: packed_result.append(0)
		return packed_result
	return values
func _triangle_key(a: Variant, b: Variant, c: Variant) -> String:
	var points := [_as_vector3(a), _as_vector3(b), _as_vector3(c)]; var keys: Array[String] = []
	for point: Vector3 in points: keys.append("%d,%d,%d" % [roundi(point.x * 65536.0), roundi(point.y * 65536.0), roundi(point.z * 65536.0)])
	keys.sort(); return "%s|%s|%s" % [keys[0], keys[1], keys[2]]
func _as_vector3(value: Variant) -> Vector3: return value if value is Vector3 else Vector3(float(value[0]), float(value[1]), float(value[2]))
func _add_collision(mesh_node: MeshInstance3D, mesh: Mesh) -> void:
	var geometry := mesh.create_trimesh_shape()
	if geometry == null: return
	for layer in [1, 4]:
		var body := StaticBody3D.new(); body.name = "RoomCollision_%d" % layer; body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = geometry.duplicate() if layer == 4 else geometry
		if layer == 4 and shape.shape is ConcavePolygonShape3D: (shape.shape as ConcavePolygonShape3D).backface_collision = true
		body.add_child(shape); mesh_node.add_child(body)
func _refresh_room_state() -> void:
	var visible := {}
	visible_neighbor_keys.clear()
	if not active_room_key.is_empty(): visible[active_room_key] = true
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		if source_key == active_room_key: visible[destination_key] = true; visible_neighbor_keys[destination_key] = true
		elif destination_key == active_room_key: visible[source_key] = true; visible_neighbor_keys[source_key] = true
	for support in floor_supports.values():
		if is_instance_valid(support): support.collision_layer = 0; support.collision_mask = 0; support.queue_free()
	floor_supports.clear()
	for room_key in rooms:
		rooms[room_key].visible = visible.has(room_key)
		var clip_plane := Vector4.ZERO
		var clip_enabled := false
		var room_planes := PackedVector4Array(); var room_limits := PackedFloat32Array()
		for portal: Dictionary in portal_layout:
			var portal_key := _portal_key(portal)
			if not opened_portals.has(portal_key): continue
			var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
			if room_key != source_key and room_key != destination_key: continue
			var source_side: bool = room_key == source_key; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var inward := -_outward_sign(portal, source_side); var plane := Vector4.ZERO; plane[axis] = inward; plane.w = -float(portal["world_center"][axis]) * inward; room_planes.append(plane)
			var camera_source: bool = portal_camera_sides.get(portal_key, str(opened_from.get(portal_key, "")) == source_key); room_limits.append(-0.0001 if camera_source == source_side else 0.0001)
		var room_count := room_planes.size(); room_planes.resize(16); room_limits.resize(16)
		var floor_planes := PackedVector4Array(); var floor_bounds := PackedVector4Array()
		if room_key == active_room_key:
			for portal: Dictionary in portal_layout:
				if not opened_portals.has(_portal_key(portal)): continue
				var source_side: bool = _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) == room_key; var destination_side: bool = _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])) == room_key
				if not source_side and not destination_side: continue
				var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var inward := -_outward_sign(portal, source_side); var plane := Vector4.ZERO; var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]) * 0.5; var bottom := float(center[1]) - float(portal["shared_panel_size"][1]) * 0.5
				plane[axis] = inward; plane.w = -float(center[axis]) * inward; floor_planes.append(plane); floor_bounds.append(Vector4(float(center[lateral]) - width, float(center[lateral]) + width, bottom - 0.025, bottom + 0.025))
		var floor_count := floor_planes.size(); floor_planes.resize(16); floor_bounds.resize(16)
		if room_key != active_room_key and visible.has(room_key):
			for portal: Dictionary in portal_layout:
				if not opened_portals.has(_portal_key(portal)): continue
				var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
				if not ((source_key == active_room_key and destination_key == room_key) or (destination_key == active_room_key and source_key == room_key)): continue
				var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var inward := -_outward_sign(portal, source_key == room_key); clip_plane[axis] = inward; clip_plane.w = -float(portal["world_center"][axis]) * inward; clip_enabled = true; break
		for node: MeshInstance3D in mesh_nodes[room_key].values():
			for surface in node.mesh.get_surface_count():
				var material := node.get_active_material(surface) as ShaderMaterial
				if material != null:
					material.set_shader_parameter("portal_clip_enabled", false); material.set_shader_parameter("room_clip_count", room_count); material.set_shader_parameter("room_clip_planes", room_planes); material.set_shader_parameter("room_clip_limits", room_limits); material.set_shader_parameter("portal_floor_clip_count", floor_count); material.set_shader_parameter("portal_floor_clip_planes", floor_planes); material.set_shader_parameter("portal_floor_clip_bounds", floor_bounds)
			for body in node.get_children():
				if not body is StaticBody3D: continue
				body.collision_layer = (1 if body.name == "RoomCollision_1" else 4) if room_key == active_room_key else 0
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		if source_key == active_room_key and rooms.has(destination_key): _add_floor_support(destination_key, portal, false)
		elif destination_key == active_room_key and rooms.has(source_key): _add_floor_support(source_key, portal, true)
func _add_floor_support(room_key: String, portal: Dictionary, neighbor_is_source: bool) -> void:
	var vertices := PackedVector3Array(); var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var center: Array = portal["world_center"]; var plane := float(center[axis]); var outward := _outward_sign(portal, neighbor_is_source); var inverse := global_transform.affine_inverse()
	for mesh_node: MeshInstance3D in mesh_nodes[room_key].values():
		if mesh_node.mesh == null: continue
		for surface in mesh_node.mesh.get_surface_count():
			if mesh_node.mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: continue
			var arrays: Array = mesh_node.mesh.surface_get_arrays(surface); var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]; var count := indices.size() if not indices.is_empty() else points.size()
			for triangle in range(0, count, 3):
				var ia := indices[triangle] if not indices.is_empty() else triangle; var ib := indices[triangle + 1] if not indices.is_empty() else triangle + 1; var ic := indices[triangle + 2] if not indices.is_empty() else triangle + 2; var a := mesh_node.to_global(points[ia]); var b := mesh_node.to_global(points[ib]); var c := mesh_node.to_global(points[ic])
				if (b - a).cross(c - a).normalized().y > -0.65: continue
				var polygon := _clip_floor_triangle([a, b, c], axis, plane, outward, body_radius)
				for index in range(1, polygon.size() - 1): vertices.append(inverse * polygon[0]); vertices.append(inverse * polygon[index]); vertices.append(inverse * polygon[index + 1])
	if vertices.is_empty(): return
	var arrays: Array = []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	for layer in [1, 4]:
		var body := StaticBody3D.new(); body.name = "RoomFloorSupport_%s_%d" % [room_key.replace(":", "_"), layer]; body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.create_trimesh_shape()
		if layer == 4: (shape.shape as ConcavePolygonShape3D).backface_collision = true
		body.add_child(shape); add_child(body); floor_supports[_mesh_key(room_key, _portal_key(portal)) + ":" + str(layer)] = body
func _clip_floor_triangle(triangle: Array[Vector3], axis: int, plane: float, outward: float, margin: float) -> Array[Vector3]:
	var result: Array[Vector3] = []; var previous: Vector3 = triangle.back(); var previous_distance := (previous[axis] - plane) * outward - margin
	for current: Vector3 in triangle:
		var current_distance := (current[axis] - plane) * outward - margin; var previous_inside := previous_distance <= 0.0; var current_inside := current_distance <= 0.0
		if previous_inside != current_inside: result.append(previous.lerp(current, previous_distance / (previous_distance - current_distance)))
		if current_inside: result.append(current)
		previous = current; previous_distance = current_distance
	return result
func _evict_unused() -> void:
	var keep := {}
	for key in [active_room_key, previous_room_key, requested_room_key]:
		if not str(key).is_empty(): keep[str(key)] = true
	for key in visible_neighbor_keys: keep[str(key)] = true
	for key in rooms.keys():
		if keep.has(str(key)): continue
		var room: Node = rooms[key]; rooms.erase(key); mesh_nodes.erase(key); var prefix := str(key) + ":"
		for mesh_key in source_meshes.keys(): if str(mesh_key).begins_with(prefix): source_meshes.erase(mesh_key)
		room.queue_free()
func _refresh_collision(mesh_node: MeshInstance3D, mesh: Mesh) -> void:
	for child in mesh_node.get_children():
		if child is not StaticBody3D: continue
		for item in child.get_children():
			if item is not CollisionShape3D: continue
			item.shape = mesh.create_trimesh_shape()
			if child.collision_layer == 4 and item.shape is ConcavePolygonShape3D: (item.shape as ConcavePolygonShape3D).backface_collision = true
func _room_key(stage: String, area: int) -> String: return "%s:%d" % [stage, area]
func _mesh_key(room_key: String, node_name: String) -> String: return room_key + ":" + node_name
func _portal_key(portal: Dictionary) -> String:
	var a := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var b := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])); return a + "|" + b if a < b else b + "|" + a
