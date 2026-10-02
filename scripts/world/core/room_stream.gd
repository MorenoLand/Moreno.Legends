extends Node3D
signal room_activated(stage: String, area: int)
signal native_context_changed(stage: String, area: int)
signal door_sound(sound_id: int)
signal room_loaded(stage: String)
var rooms: Dictionary = {}
var room_info: Dictionary = {}
var room_bounds: Dictionary = {}
var portal_layout: Array = []
var ladder_transitions: Array = []
var opened_portals: Dictionary = {}
var opened_from: Dictionary = {}
var opened_origin_distance: Dictionary = {}
var portal_leaves: Dictionary = {}
var transition_rate := 1.0
var sliding_scenes: Dictionary = {}
var transition_doors: Dictionary = {}
var portal_depth_views: Dictionary = {}
var portal_backings: Dictionary = {}
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
var native_context: Dictionary = {}
var camera_space_position := Vector3.ZERO
var has_camera_space_position := false
var camera_collision_rooms: Dictionary = {}
var camera_shape_cache: Dictionary = {}
var camera_layers_dirty := true
var open_mesh_cache: Dictionary = {}
var collision_shape_cache: Dictionary = {}
var parked_exterior: Node3D
var exterior_request := 0
var external_routes: Array = []
var parked_exterior_enabled := false
func can_show_parked_exterior() -> bool: return parked_exterior_enabled
static func layout_path_for(stage: String, area: int) -> String:
	var path := "res://assets/locations/room_layout.json" if stage in ["ST04", "ST05", "ST06", "ST07"] else "res://assets/locations/mine_room_layout.json" if stage == "ST0F" else "res://assets/locations/landing_room_layout.json" if stage == "ST08" else "res://assets/locations/ruminoa_room_layout.json" if stage in ["ST19", "ST1A", "ST1B"] else "res://assets/locations/town_room_layout.json"
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if data is Dictionary:
		for room: Dictionary in data.get("rooms", []):
			if str(room["stage"]) == stage and int(room["area"]) == area: return path
	return ""
func _bounded_portal_region(room_key: String, portal: Dictionary, source_side: bool) -> AABB:
	var other: Dictionary = portal["destination"] if source_side else portal["source"]; var other_key := _room_key(str(other["stage"]), int(other["area"])); var bounds: AABB = room_bounds[other_key]; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var position := bounds.position; var end := bounds.end; var width := float(portal["shared_panel_size"][0]) * 0.5; var height := float(portal["shared_panel_size"][1]) * 0.5
	if bool(room_info[room_key].get("exterior", false)):
		var side: Dictionary = portal["source_panel"] if source_side else portal["destination_panel"]; var node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(str(side["node"])); var original: Mesh = source_meshes.get(_mesh_key(room_key, str(side["node"])))
		if is_instance_valid(node) and original != null:
			var exterior_bounds: AABB = node.global_transform * original.get_aabb(); position[axis] = maxf(position[axis], exterior_bounds.position[axis]); end[axis] = minf(end[axis], exterior_bounds.end[axis])
	position[lateral] = float(center[lateral]) - width; end[lateral] = float(center[lateral]) + width; position.y = float(center[1]) - height; end.y = float(center[1]) + height
	return AABB(position, end - position)
func is_exterior_room(stage: String, area: int) -> bool: return bool(room_info.get(_room_key(stage, area), {}).get("exterior", false))
func room_root(stage: String, area: int) -> Node3D: return rooms.get(_room_key(stage, area)) as Node3D
func _subtract_box(box: AABB, hole: AABB) -> Array[AABB]:
	var overlap := box.intersection(hole); var pieces: Array[AABB] = []
	if overlap.size.x <= 0.000001 or overlap.size.y <= 0.000001 or overlap.size.z <= 0.000001: pieces.append(box); return pieces
	var middle := box
	for axis in 3:
		if middle.position[axis] < overlap.position[axis]:
			var part := middle; part.size[axis] = overlap.position[axis] - middle.position[axis]; pieces.append(part); middle.position[axis] = overlap.position[axis]; middle.size[axis] -= part.size[axis]
		if middle.end[axis] > overlap.end[axis]:
			var part := middle; part.position[axis] = overlap.end[axis]; part.size[axis] = middle.end[axis] - overlap.end[axis]; pieces.append(part); middle.size[axis] -= part.size[axis]
	return pieces
func _refresh_native_floor_apertures(room_key: String) -> void:
	var exterior := bool(room_info[room_key].get("exterior", false))
	var holes: Array[AABB] = []; var keys: Array[String] = []
	for portal: Dictionary in portal_layout:
		var key := _portal_key(portal)
		if not opened_portals.has(key): continue
		var source_side := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) == room_key
		if not source_side and _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])) != room_key: continue
		keys.append(key); holes.append(_bounded_portal_region(room_key, portal, source_side))
	for portal: Dictionary in transition_doors.values():
		if _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) != room_key: continue
		var bounds: AABB = room_bounds[room_key]; var position := bounds.position; var end := bounds.end; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var size: Array = portal["shared_panel_size"]
		position[lateral] = float(center[lateral]) - float(size[0]) * 0.5; end[lateral] = float(center[lateral]) + float(size[0]) * 0.5; position.y = float(center[1]) - float(size[1]) * 0.5; end.y = float(center[1]) + float(size[1]) * 0.5
		keys.append(_portal_key(portal)); holes.append(AABB(position, end - position))
	keys.sort(); var signature := ",".join(PackedStringArray(keys))
	for body: StaticBody3D in rooms[room_key].find_children("NativePlacementFloor_*", "StaticBody3D", true, false):
		if str(body.get_meta("native_aperture_signature", "unset")) == signature: continue
		if not body.has_meta("native_aperture_sources"):
			var sources: Array[CollisionShape3D] = []
			for child in body.get_children():
				if child is CollisionShape3D and child.shape is BoxShape3D: sources.append(child)
			body.set_meta("native_aperture_sources", sources)
		for child in body.get_children():
			if child is CollisionShape3D and bool(child.get_meta("native_aperture_piece", false)): child.set_deferred("disabled", true); child.queue_free()
		for source: CollisionShape3D in body.get_meta("native_aperture_sources"):
			if not exterior and not bool(source.get_meta("native_volume", false)): continue
			var box := source.shape as BoxShape3D; var original := source.global_transform * AABB(-box.size * 0.5, box.size); var pieces: Array[AABB] = [original]
			for hole: AABB in holes:
				var clipped: Array[AABB] = []
				for piece: AABB in pieces: clipped.append_array(_subtract_box(piece, hole))
				pieces = clipped
			var changed: bool = pieces.size() != 1 or pieces[0] != original
			source.set_deferred("disabled", changed)
			if not changed: continue
			for piece: AABB in pieces:
				var shape := CollisionShape3D.new(); var geometry := BoxShape3D.new(); geometry.size = piece.size; shape.shape = geometry; shape.position = body.to_local(piece.position + piece.size * 0.5); shape.set_meta("native_aperture_piece", true); body.add_child(shape)
		body.set_meta("native_aperture_signature", signature)
static func _subtract_region(polygon: Array[Vector3], region: AABB) -> Array:
	var kept: Array = []; var inside := polygon
	for axis in 3:
		for sign_value in [-1.0, 1.0]:
			if inside.is_empty(): return kept
			var plane: float = region.position[axis] if sign_value < 0.0 else region.end[axis]; var outside := _clip_floor_triangle(inside, axis, plane, -sign_value, 0.0)
			if outside.size() >= 3: kept.append(outside)
			inside = _clip_floor_triangle(inside, axis, plane, sign_value, 0.0)
	return kept
func clear_parked_exterior() -> void:
	exterior_request += 1
	for room: Node3D in rooms.values(): preload("res://scripts/world/flutter/window_view.gd").set_snowfall(room, false)
	if is_instance_valid(parked_exterior): parked_exterior.queue_free()
	parked_exterior = null
func set_parked_exterior(stage: String, area: int) -> bool:
	if not parked_exterior_enabled: return false
	clear_parked_exterior()
	var request := exterior_request
	var paired: Dictionary = {}
	for route: Dictionary in external_routes:
		if str(route["source_stage"]) == "ST04" and int(route["source_area"]) == 1: paired = route; break
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
	var dock := preload("res://scripts/world/flutter/flutter_dock.gd").exterior_hatch(stage)
	if not dock.is_empty(): exterior_anchor = dock["position"]; exterior_yaw = float(dock["yaw"]) + PI
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
	exterior.set_meta("native_map_face_flags", bool(entry.get("native_map_face_flags_in_alpha", false)))
	var rotation_basis := Basis(Vector3.UP, interior_yaw - exterior_yaw)
	exterior.transform = Transform3D(rotation_basis, interior_anchor - rotation_basis * exterior_anchor)
	exterior.name = "ParkedExterior"
	exterior.process_mode = Node.PROCESS_MODE_DISABLED
	for collider: CollisionObject3D in exterior.find_children("*", "CollisionObject3D", true, false): collider.collision_layer = 0; collider.collision_mask = 0; collider.queue_free()
	add_child(exterior)
	preload("res://scripts/world/rendering/native_material.gd").apply(exterior)
	for mesh: MeshInstance3D in exterior.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		var body := StaticBody3D.new(); body.name = "RoomCollision_1"; body.collision_layer = 32; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.mesh.create_trimesh_shape(); body.add_child(shape); mesh.add_child(body)
	preload("res://scripts/world/core/native_floor.gd").apply(exterior, manifest.get("native_floor_collision", {}), area, native_context)
	for body: StaticBody3D in exterior.find_children("NativePlacementFloor_*", "StaticBody3D", true, false): body.collision_layer = 32
	await _load_room_props(exterior, stage, area, ["player_vehicle"])
	if request != exterior_request:
		exterior.queue_free()
		return false
	for collider: CollisionObject3D in exterior.find_children("*", "CollisionObject3D", true, false): collider.collision_layer = 0 if bool(collider.get_meta("native_floor_replaced", false)) else 32; collider.collision_mask = 0
	for behavior: Node in exterior.find_children("NativeNpcBehavior", "Node", true, false):
		var actor: Node3D = behavior.get("actor"); actor.set_meta("native_motion_collision_mask", 32); behavior.process_mode = Node.PROCESS_MODE_PAUSABLE
	for clock: Node in exterior.find_children("NativeAnimationClock", "Node", true, false): clock.process_mode = Node.PROCESS_MODE_PAUSABLE
	parked_exterior = exterior
	_clip_parked_exterior()
	preload("res://scripts/world/rendering/native_material.gd").depth_cue(exterior, preload("res://scripts/world/rendering/native_material.gd").area_parameters("res://assets/levels/%s/lighting.json" % stage, area))
	var weather: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/weather/manifest.json")); var snow := false
	if weather is Dictionary:
		for record: Dictionary in weather.get("stages", {}).get(stage, {}).get("areas", {}).get(str(area), []): snow = snow or int(record.get("native_variant", -1)) == 1
	exterior.set_meta("window_snowfall", false)
	for room: Node3D in rooms.values(): preload("res://scripts/world/flutter/window_view.gd").set_snowfall(room, false)
	if snow:
		var flakes := CPUParticles3D.new(); flakes.name = "ExteriorSnow"; flakes.process_mode = Node.PROCESS_MODE_PAUSABLE; flakes.amount = 1000; flakes.lifetime = 20.0; flakes.preprocess = 20.0; flakes.local_coords = false; flakes.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX; flakes.emission_box_extents = Vector3(10, 3, 10); flakes.direction = Vector3.DOWN; flakes.spread = 8.0; flakes.initial_velocity_min = 0.35; flakes.initial_velocity_max = 0.55; flakes.gravity = Vector3(0.015, -0.01, 0.015); flakes.position = exterior_anchor + Vector3.UP * 3.0
		var quad := QuadMesh.new(); quad.size = Vector2(0.035, 0.035); var material := ShaderMaterial.new(); material.shader = preload("res://shaders/exterior_snow.gdshader"); material.set_shader_parameter("snow_texture", load("res://assets/weather/snow.png")); quad.material = material; flakes.mesh = quad; exterior.set_meta("snow_material", material); exterior.add_child(flakes); _clip_parked_exterior()
	return true
func _clip_parked_exterior(visible_rooms: Dictionary = {}) -> void:
	if not is_instance_valid(parked_exterior): return
	var minimum := PackedVector3Array(); var maximum := PackedVector3Array()
	for key in rooms:
		if bool(room_info[key].get("exterior", false)) or (not visible_rooms.has(key) if not visible_rooms.is_empty() else not rooms[key].visible): continue
		var bounds: AABB = room_bounds[key]; minimum.append(bounds.position); maximum.append(bounds.end)
	var count := minimum.size(); minimum.resize(16); maximum.resize(16)
	var snow_material := parked_exterior.get_meta("snow_material") as ShaderMaterial if parked_exterior.has_meta("snow_material") else null
	if snow_material != null: snow_material.set_shader_parameter("interior_clip_count", mini(count, 16)); snow_material.set_shader_parameter("interior_clip_min", minimum); snow_material.set_shader_parameter("interior_clip_max", maximum)
	for mesh: MeshInstance3D in parked_exterior.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null or not preload("res://scripts/world/rendering/native_material.gd").is_model_shader(material.shader): continue
			material.set_shader_parameter("interior_clip_count", mini(count, 16)); material.set_shader_parameter("interior_clip_min", minimum); material.set_shader_parameter("interior_clip_max", maximum)
func _clip_exterior_rooms() -> void:
	var active_interior: bool = room_bounds.has(active_room_key) and not bool(room_info[active_room_key].get("exterior", false)); var minimum := PackedVector3Array(); var maximum := PackedVector3Array()
	if active_interior: var bounds: AABB = room_bounds[active_room_key]; minimum.append(bounds.position - Vector3(0, 0.05, 0)); maximum.append(bounds.end)
	var count := minimum.size(); minimum.resize(16); maximum.resize(16)
	for key in rooms:
		if not bool(room_info[key].get("exterior", false)): continue
		for node: MeshInstance3D in mesh_nodes[key].values():
			for surface in node.mesh.get_surface_count():
				var material := node.get_active_material(surface) as ShaderMaterial
				if material != null: material.set_shader_parameter("interior_clip_count", count); material.set_shader_parameter("interior_clip_min", minimum); material.set_shader_parameter("interior_clip_max", maximum)
func configure(layout_path: String, start_stage: String, start_area: int, player_radius: float = 0.12) -> bool:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(layout_path)) if FileAccess.file_exists(layout_path) else null
	if not data is Dictionary or not data.get("rooms", []) is Array: return false
	body_radius = player_radius; parked_exterior_enabled = bool(data.get("parked_exterior_enabled", false))
	for entry: Dictionary in data["rooms"]:
		var stage := str(entry["stage"]); var area := int(entry["area"]); var key := _room_key(stage, area); room_info[key] = entry; room_offsets[key] = Vector3(float(entry["world_offset"][0]), float(entry["world_offset"][1]), float(entry["world_offset"][2])); var local_bounds: Dictionary = entry["local_bounds"]; var minv: Array = local_bounds["min"]; var maxv: Array = local_bounds["max"]; room_bounds[key] = AABB(Vector3(float(minv[0]), float(minv[1]), float(minv[2])) + room_offsets[key], Vector3(float(maxv[0] - minv[0]), float(maxv[1] - minv[1]), float(maxv[2] - minv[2])))
	portal_layout = data["portals"]; ladder_transitions = data.get("ladder_transitions", []); external_routes = data.get("external_routes", []); active_room_key = _room_key(start_stage, start_area)
	if not await _ensure_room_loaded(start_stage, start_area): return false
	_refresh_room_state()
	return true
func _ensure_room_loaded(stage: String, area: int) -> bool:
	var key := _room_key(stage, area)
	if loading_rooms.has(key):
		while loading_rooms.has(key): await get_tree().process_frame
		return rooms.has(key)
	if rooms.has(key): return true
	if not room_info.has(key): return false
	loading_rooms[key] = true
	if not await AssetStore.ensure_stage(stage):
		loading_rooms.erase(key)
		return false
	if not props_loaded:
		props = preload("res://scripts/world/actors/native_props.gd")._read_manifest("res://assets/stage_props/manifest.json").get("stages", {})
		props_loaded = true
	var entry: Dictionary = room_info[key]; var scene_path := "res://assets/levels/%s/%s" % [stage, str(entry["file"])]; var scene: PackedScene = await _threaded_scene(scene_path)
	if scene == null:
		loading_rooms.erase(key)
		push_error("Cannot preload room " + scene_path)
		return false
	var stage_manifest_path := "res://assets/levels/%s/manifest.json" % stage; var stage_manifest: Variant = await read_json_threaded(stage_manifest_path); var map_face_flags := false; var area_variants: Array = []
	if stage_manifest is Dictionary:
		for area_entry: Dictionary in stage_manifest.get("areas", []):
			if int(area_entry["index"]) == area: map_face_flags = bool(area_entry.get("native_map_face_flags_in_alpha", false)); area_variants = area_entry.get("placement_variants", []); break
	var room := scene.instantiate() as Node3D; preload("res://scripts/world/flutter/room_variants.gd").apply_placements(room, area_variants, native_context); room.name = key.replace(":", "_"); room.position = room_offsets[key]; room.visible = key == active_room_key; room.set_meta("native_map_face_flags", map_face_flags); room.set_meta("native_stream_room_active", key == active_room_key)
	await get_tree().process_frame
	add_child(room); rooms[key] = room; var nodes: Dictionary = {}; mesh_nodes[key] = nodes
	await get_tree().process_frame
	await preload("res://scripts/world/core/native_coplanar_overlays.gd").warm(room)
	preload("res://scripts/world/rendering/native_material.gd").apply(room)
	await get_tree().process_frame
	var slice_start := Time.get_ticks_usec()
	for item in room.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := item as MeshInstance3D
		if mesh_node.mesh == null: continue
		nodes[mesh_node.name] = mesh_node; source_meshes[_mesh_key(key, mesh_node.name)] = mesh_node.mesh; _add_collision(mesh_node, mesh_node.mesh)
		if key != active_room_key:
			for body: StaticBody3D in mesh_node.find_children("*", "StaticBody3D", true, false): body.collision_layer = 0
		if Time.get_ticks_usec() - slice_start > 4000: await get_tree().process_frame; slice_start = Time.get_ticks_usec()
	await get_tree().process_frame
	if stage_manifest is Dictionary: preload("res://scripts/world/core/native_floor.gd").apply(room, stage_manifest.get("native_floor_collision", {}), area, native_context)
	if key != active_room_key:
		for body: StaticBody3D in room.find_children("NativePlacementFloor_*", "StaticBody3D", true, false): body.collision_layer = 0
	await get_tree().process_frame
	await _load_room_props(room, stage, area)
	await get_tree().process_frame
	preload("res://scripts/world/core/area_roof.gd").apply(room, stage, area)
	for generated_roof: MeshInstance3D in room.find_children("*", "MeshInstance3D", true, false):
		if not generated_roof.has_meta("generated_roof_mesh"): continue
		nodes[generated_roof.name] = generated_roof; source_meshes[_mesh_key(key, generated_roof.name)] = generated_roof.mesh
		if key != active_room_key:
			for roof_body: StaticBody3D in generated_roof.find_children("*", "StaticBody3D", true, false): roof_body.collision_layer = 0
	await get_tree().process_frame
	preload("res://scripts/world/flutter/window_view.gd").apply(room, stage, area)
	preload("res://scripts/world/flutter/window_view.gd").set_snowfall(room, is_instance_valid(parked_exterior) and bool(parked_exterior.get_meta("window_snowfall", false)))
	var opened_nodes := {}
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		for side in [[portal["source"], portal["source_panel"]], [portal["destination"], portal["destination_panel"]]]:
			if _room_key(str(side[0]["stage"]), int(side[0]["area"])) == key: opened_nodes[str(side[1]["node"])] = true
	for node_name in opened_nodes: _refresh_open_meshes(key, str(node_name))
	_refresh_room_state()
	await get_tree().physics_frame
	loading_rooms.erase(key)
	_prepare_around_active(); room_loaded.emit(stage)
	return true
func _apply_room_lighting(room: Node3D, stage: String, area: int) -> void:
	var material := preload("res://scripts/world/rendering/native_material.gd"); var parameters: Dictionary = material.area_parameters("res://assets/levels/%s/lighting.json" % stage, area)
	material.depth_cue(room, parameters)
func _load_room_props(room: Node3D, stage: String, area: int, excluded_roles: Array[String] = []) -> void:
	var loader := preload("res://scripts/world/actors/native_props.gd"); var previous_flags: Variant = native_context.get("event_flags", {}); var flags_before: Dictionary = previous_flags.duplicate(true) if previous_flags is Dictionary else {}
	if excluded_roles.is_empty() and _room_key(stage, area) == active_room_key:
		await loader.initialize_into(room, stage, area, native_context)
		preload("res://scripts/world/flutter/room_variants.gd").apply_stage_flags(native_context, loader._read_manifest("res://assets/levels/%s/manifest.json" % stage).get("stage_flag_rules", []))
	else: await loader.load_into(room, stage, area, native_context, excluded_roles)
	var current_flags: Variant = native_context.get("event_flags", {}); var flags_after: Dictionary = current_flags if current_flags is Dictionary else {}
	if flags_before != flags_after and _room_key(stage, area) == active_room_key: native_context_changed.emit(stage, area)
	if is_instance_valid(room): _apply_room_lighting(room, stage, area)
func read_json_threaded(path: String) -> Variant:
	if not FileAccess.file_exists(path): return null
	var holder := {}; var task := WorkerThreadPool.add_task(func() -> void: holder["value"] = JSON.parse_string(FileAccess.get_file_as_string(path)))
	while not WorkerThreadPool.is_task_completed(task): await get_tree().process_frame
	WorkerThreadPool.wait_for_task_completion(task)
	return holder.get("value")
var scene_inflight: Dictionary = {}
func _threaded_scene(path: String) -> PackedScene:
	if scene_inflight.has(path):
		while scene_inflight.has(path): await get_tree().process_frame
		return ResourceLoader.load(path, "PackedScene") as PackedScene
	scene_inflight[path] = true
	var scene := await _threaded_scene_load(path)
	scene_inflight.erase(path)
	return scene
func _threaded_scene_load(path: String) -> PackedScene:
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
	_refresh_room_state()
	var active_room: Node3D = rooms.get(key) as Node3D
	if is_instance_valid(active_room): await _load_room_props(active_room, stage, area); _apply_room_lighting(active_room, stage, area)
	requested_room_key = ""
	_refresh_room_state()
	room_activated.emit(stage, area)
	_evict_unused()
	_prepare_around_active()
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
		var leaf_profile: Dictionary = portal.get("source_native_door", {}) if forward else portal.get("reverse_native_door", {})
		if int(leaf_profile.get("controller_class", 1)) == 3 and not portal_leaves.has(key): await _sliding_door_models(stage, leaf_profile)
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		_refresh_open_meshes(source_key, str(portal["source_panel"]["node"]))
		_refresh_open_meshes(destination_key, str(portal["destination_panel"]["node"]))
		requested_room_key = ""
		_refresh_room_state()
		if not portal_leaves.has(key) and not await _open_leaf(portal, forward): _close_portal(key); return false
		_evict_unused()
		_prepare_around_active()
		return true
	return false
func preload_route(stage: String, area: int, route: Dictionary) -> void:
	var portal := portal_for_route(stage, area, route)
	if portal.is_empty():
		var destination_stage := str(route.get("destination_stage", stage)); var destination_area := int(route["destination_area"]); var destination_key := _room_key(destination_stage, destination_area)
		if not seamless_ladder(stage, area, route).is_empty() and not rooms.has(destination_key) and not loading_rooms.has(destination_key): await _ensure_room_loaded(destination_stage, destination_area)
		return
	var source_side := str(portal["source"]["stage"]) == stage and int(portal["source"]["area"]) == area; var destination: Dictionary = portal["destination"] if source_side else portal["source"]; var key := _room_key(str(destination["stage"]), int(destination["area"]))
	if not rooms.has(key) and not loading_rooms.has(key): await _ensure_room_loaded(str(destination["stage"]), int(destination["area"]))
	var profile: Dictionary = portal.get("source_native_door", {}) if source_side else portal.get("reverse_native_door", {})
	if int(profile.get("controller_class", 1)) == 3: await _sliding_door_models(str(portal["source"]["stage"]) if source_side else str(portal["destination"]["stage"]), profile)
func prepare_transition_door(stage: String, route: Dictionary) -> bool:
	for model: Dictionary in props.get(stage, {}).get("native_doors", []):
		if int(model["variant"]) != int(route["door_slot"]): continue
		var scene: PackedScene = await _threaded_scene("res://assets/stage_props/" + str(model["model_file"]))
		return scene != null
	return false
func open_transition_door(stage: String, area: int, route: Dictionary, rate: float = 1.0) -> bool:
	transition_rate = rate
	if not route.get("source_panel", null) is Dictionary or is_ladder_route(stage, area, route): return false
	var source: Dictionary = route["source_panel"]
	var offset := offset_for(stage, area)
	var center := _as_vector3(source["center"]) + offset
	var bounds: Dictionary = source["bounds"]
	var lateral := 2 if int(source["axis"]) == 0 else 0
	var portal := {"source": {"stage": stage, "area": area}, "destination": {"stage": str(route["destination_stage"]), "area": int(route["destination_area"])}, "source_panel": source, "source_native_door": route.get("native_door", {}), "source_slot": int(route["door_slot"]), "source_contact_raw": route["source_transform_raw"], "source_yaw_raw": int(route["source_transform_raw"][3]), "normal_axis": "x" if int(source["axis"]) == 0 else "z", "world_center": [center.x, center.y, center.z], "shared_panel_size": [float(bounds["max"][lateral]) - float(bounds["min"][lateral]), float(bounds["max"][1]) - float(bounds["min"][1])]}
	var key := _portal_key(portal)
	if transition_doors.has(key): return true
	transition_doors[key] = portal
	_refresh_native_floor_apertures(_room_key(stage, area))
	_refresh_open_meshes(_room_key(stage, area), str(source["node"]))
	_refresh_camera_layers()
	if await _open_leaf(portal, true): _create_doorway_backing(portal, key); return true
	transition_doors.erase(key)
	_refresh_native_floor_apertures(_room_key(stage, area))
	_refresh_open_meshes(_room_key(stage, area), str(source["node"]))
	_refresh_camera_layers()
	return false
func release_transition_door(stage: String, area: int, route: Dictionary) -> void:
	var leaf: Node3D = portal_leaves.get(_portal_key({"source": {"stage": stage, "area": area}, "destination": {"stage": str(route["destination_stage"]), "area": int(route["destination_area"])}}))
	if is_instance_valid(leaf) and leaf.has_meta("swing"): (leaf.get_meta("swing") as Node).release()
func close_transition_door(stage: String, area: int, route: Dictionary) -> void:
	var key := _portal_key({"source": {"stage": stage, "area": area}, "destination": {"stage": str(route["destination_stage"]), "area": int(route["destination_area"])}})
	if not transition_doors.has(key): return
	var portal: Dictionary = transition_doors[key]
	if portal_leaves.has(key):
		var leaf: Node3D = portal_leaves[key]
		portal_leaves.erase(key); leaf.queue_free()
	if portal_depth_views.has(key): portal_depth_views[key].queue_free(); portal_depth_views.erase(key)
	if portal_backings.has(key): portal_backings[key].queue_free(); portal_backings.erase(key)
	transition_doors.erase(key)
	_refresh_native_floor_apertures(_room_key(stage, area))
	_refresh_open_meshes(_room_key(stage, area), str(portal["source_panel"]["node"]))
	_refresh_camera_layers()
func ladder_transition(stage: String, area: int, route: Dictionary) -> Dictionary:
	var destination_stage := str(route.get("destination_stage", stage)); var destination_area := int(route["destination_area"])
	for transition: Dictionary in ladder_transitions:
		var forward := str(transition["source"]["stage"]) == stage and int(transition["source"]["area"]) == area and str(transition["destination"]["stage"]) == destination_stage and int(transition["destination"]["area"]) == destination_area
		var reverse := str(transition["destination"]["stage"]) == stage and int(transition["destination"]["area"]) == area and str(transition["source"]["stage"]) == destination_stage and int(transition["source"]["area"]) == destination_area
		if forward or reverse: return transition
	return {}
func is_ladder_route(stage: String, area: int, route: Dictionary) -> bool: return not ladder_transition(stage, area, route).is_empty()
func seamless_ladder(stage: String, area: int, route: Dictionary) -> Dictionary:
	var transition := ladder_transition(stage, area, route)
	return transition if bool(transition.get("seamless", false)) and has_room(str(route.get("destination_stage", stage)), int(route["destination_area"])) else {}
func close_cleared_portals(player_position: Vector3, camera_position: Vector3, radius: float) -> void:
	camera_space_position = camera_position
	has_camera_space_position = true
	if camera_layers_dirty: _refresh_camera_layers()
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
		if _in_door_sweep(player_position, portal, radius) or _in_door_sweep(camera_position, portal, radius): should_close = false
		if _segment_through_portal(player_position, camera_position, portal, radius): should_close = false
		if should_close: close.append(str(key))
	for key in close: _close_portal(key)
	if render_changed: _refresh_camera_masks()
func _in_door_sweep(point: Vector3, portal: Dictionary, radius: float) -> bool:
	var leaf: Node3D = portal_leaves.get(_portal_key(portal))
	if is_instance_valid(leaf) and leaf.has_meta("sweep_bounds"): return (leaf.get_meta("sweep_bounds") as AABB).grow(radius).has_point(point)
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]); var height := float(portal["shared_panel_size"][1]); var distance := (point[axis] - float(center[axis])) * _outward_sign(portal, true)
	return distance >= -radius and distance <= width + radius and absf(point[lateral] - float(center[lateral])) <= width * 0.5 + radius and absf(point.y - float(center[1])) <= height * 0.5 + radius
func _segment_through_portal(body: Vector3, camera: Vector3, portal: Dictionary, radius: float) -> bool:
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var first := body[axis] - float(center[axis]); var second := camera[axis] - float(center[axis])
	if first * second > 0.0 or absf(first - second) < 0.00001: return false
	var intersection := body.lerp(camera, first / (first - second))
	return absf(intersection[lateral] - float(center[lateral])) <= float(portal["shared_panel_size"][0]) * 0.5 + radius and absf(intersection.y - float(center[1])) <= float(portal["shared_panel_size"][1]) * 0.5 + radius
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
		await _close_leaf(leaf)
		portal_leaves.erase(key); closing_portals.erase(key); leaf.queue_free()
	if portal_depth_views.has(key): portal_depth_views[key].queue_free(); portal_depth_views.erase(key)
	opened_portals.erase(key); opened_from.erase(key); opened_origin_distance.erase(key); portal_camera_sides.erase(key)
	var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
	_refresh_open_meshes(source_key, str(portal["source_panel"]["node"])); _refresh_open_meshes(destination_key, str(portal["destination_panel"]["node"])); _refresh_room_state(); _evict_unused(); _prepare_around_active()
func _open_leaf(portal: Dictionary, source_side: bool) -> bool:
	var room: Dictionary = portal["source"] if source_side else portal["destination"]; var stage := str(room["stage"]); var room_key := _room_key(stage, int(room["area"])); var profile: Dictionary = portal.get("source_native_door", {}) if source_side else portal.get("reverse_native_door", {}); var controller := int(profile.get("controller_class", 1)); var variant := int(portal["source_slot"] if source_side else portal["reverse_source_slot"]); variant = variant * 2 if controller == 2 else variant; var model: Dictionary = {}
	for candidate: Dictionary in props.get(stage, {}).get("native_doors", []):
		if int(candidate.get("controller_class", 1)) == controller and int(candidate["variant"]) == variant: model = candidate; break
	if model.is_empty(): push_error("Missing native door resource %s variant %d" % [stage, variant]); return false
	if controller == 3: return await _open_sliding_leaves(portal, source_side, stage, room_key, profile)
	var scene: PackedScene = await _threaded_scene("res://assets/stage_props/" + str(model["model_file"]))
	if scene == null: return false
	var raw: Array = portal["source_contact_raw"] if source_side else portal["reverse_source_contact_raw"]; var yaw := int(raw[3]); var quadrant := ((yaw + (0x200 if controller == 2 else 0)) & 4095) >> 10; var directions := [-1, 0, 1, 0, -1]; var a := int(directions[quadrant]); var b := int(directions[quadrant + 1]); var offsets: Array = profile.get("offset_raw", [80, 64]); var c := int(offsets[0]); var e := int(offsets[1]); var hinge: Vector3 = Vector3(-float(raw[0] + a * c + b * e), -float(raw[1]), float(raw[2] + b * c - a * e)) / 256.0 + room_offsets[room_key]; var closed_yaw := -float((yaw + 0x800) & 4095) * TAU / 4096.0
	var pivot := Node3D.new(); pivot.name = "OpenDoor_" + room_key.replace(":", "_"); add_child(pivot); pivot.global_position = hinge; pivot.rotation.y = closed_yaw; pivot.set_meta("closed_yaw", closed_yaw); var panel := scene.instantiate() as Node3D; pivot.add_child(panel); var scale: Array = model["native_scale_raw"]; panel.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0; preload("res://scripts/world/rendering/native_material.gd").apply(panel, 128.0)
	var transition := transition_doors.has(_portal_key(portal))
	if portal.has("destination_panel") and not _compose_leaf_faces(portal, panel, controller == 2): pivot.queue_free(); return false
	if controller == 2:
		var companion_model: Dictionary = {}
		for candidate: Dictionary in props.get(stage, {}).get("native_doors", []):
			if int(candidate.get("controller_class", 1)) == 2 and int(candidate["variant"]) == variant + 1: companion_model = candidate; break
		if companion_model.is_empty(): pivot.queue_free(); return false
		var companion_scene: PackedScene = await _threaded_scene("res://assets/stage_props/" + str(companion_model["model_file"]))
		if companion_scene == null: pivot.queue_free(); return false
		var companion := companion_scene.instantiate() as Node3D; pivot.add_child(companion); companion.top_level = true; companion.global_position = Vector3(-float(raw[0] - a * c + b * e), -float(raw[1]), float(raw[2] - b * c - a * e)) / 256.0 + room_offsets[room_key]; companion.global_rotation.y = closed_yaw; var companion_scale: Array = companion_model["native_scale_raw"]; companion.scale = Vector3(float(companion_scale[0]), float(companion_scale[1]), float(companion_scale[2])) / 512.0; preload("res://scripts/world/rendering/native_material.gd").apply(companion, 128.0)
		for node: MeshInstance3D in companion.find_children("*", "MeshInstance3D", true, false): if not transition: _add_collision(node, node.mesh, [4])
	for node: MeshInstance3D in panel.find_children("*", "MeshInstance3D", true, false): if not transition: _add_collision(node, node.mesh, [4])
	if transition: portal["leaf_slab"] = _leaf_bounds(pivot).grow(1.0 / 256.0); _refresh_open_meshes(room_key, str(portal["source_panel"]["node"]))
	_create_doorway_depth(portal, panel)
	var open_yaw := closed_yaw - 0x3C0 * TAU / 4096.0
	pivot.set_meta("sweep_bounds", _door_sweep_bounds(pivot, panel, closed_yaw, closed_yaw - (0x6C0 if transition else 0x3C0) * TAU / 4096.0))
	portal_leaves[_portal_key(portal)] = pivot; door_sound.emit(0xB8)
	if transition:
		var swing := preload("res://scripts/world/core/native_door_swing.gd").new(); pivot.add_child(swing); swing.configure(closed_yaw, transition_rate, 9); swing.sound_requested.connect(door_sound.emit); pivot.set_meta("swing", swing)
	else: create_tween().tween_property(pivot, "rotation:y", open_yaw, 0.25)
	return true
func _compose_leaf_faces(portal: Dictionary, leaf: Node3D, split: bool = false) -> bool:
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var minimum := INF; var maximum := -INF; var side_minimum := INF; var side_maximum := -INF; var native_nodes := leaf.find_children("*", "MeshInstance3D", true, false)
	for node: MeshInstance3D in native_nodes:
		var bounds := node.mesh.get_aabb()
		for corner in 8:
			var point := node.to_global(bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)); minimum = minf(minimum, point[axis]); maximum = maxf(maximum, point[axis]); side_minimum = minf(side_minimum, point[lateral]); side_maximum = maxf(side_maximum, point[lateral])
	if maximum - minimum <= 0.00001: return false
	var composed := ArrayMesh.new()
	for source_side in [true, false]:
		var room: Dictionary = portal["source"] if source_side else portal["destination"]; var side: Dictionary = portal["source_panel"] if source_side else portal["destination_panel"]; var key := _room_key(str(room["stage"]), int(room["area"])); var node: MeshInstance3D = mesh_nodes[key][str(side["node"])]; var original: Mesh = source_meshes[_mesh_key(key, str(side["node"]))]; var wanted := {}; var added := false
		for quad: Dictionary in side["quads"]:
			if split:
				var total := 0.0; var count := 0
				for triangle: Array in quad["triangles_local"]:
					for corner: Array in triangle: total += node.to_global(Vector3(float(corner[0]), float(corner[1]), float(corner[2])))[lateral]; count += 1
				if total / float(count) < side_minimum - 0.01 or total / float(count) > side_maximum + 0.01: continue
			var surface := int(quad.get("primitive_index", side["primitive_index"])); var signatures: Dictionary = wanted.get(surface, {})
			for triangle: Array in quad["triangles_local"]: signatures[_triangle_key(triangle[0], triangle[1], triangle[2])] = true
			wanted[surface] = signatures
		for surface: int in wanted:
			if surface < 0 or surface >= original.get_surface_count(): push_error("Native door panel refers to a missing source surface"); return false
			var arrays := original.surface_get_arrays(surface)
			if arrays.size() != Mesh.ARRAY_MAX or not arrays[Mesh.ARRAY_VERTEX] is PackedVector3Array: push_error("Native door source surface has invalid vertex arrays"); return false
			var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]; var colors: PackedColorArray = arrays[Mesh.ARRAY_COLOR]; var vertices := PackedVector3Array(); var texture_uvs := PackedVector2Array(); var vertex_colors := PackedColorArray(); var count := indices.size() if not indices.is_empty() else points.size()
			for triangle in range(0, count, 3):
				var ids := [indices[triangle] if not indices.is_empty() else triangle, indices[triangle + 1] if not indices.is_empty() else triangle + 1, indices[triangle + 2] if not indices.is_empty() else triangle + 2]
				if not wanted[surface].has(_triangle_key(points[ids[0]], points[ids[1]], points[ids[2]])): continue
				for id: int in ids:
					var point := node.to_global(points[id]); point[axis] = minimum if _outward_sign(portal, source_side) > 0.0 else maximum; vertices.append(leaf.to_local(point)); texture_uvs.append(uvs[id]); vertex_colors.append(colors[id])
			if vertices.is_empty(): continue
			var output: Array = []; output.resize(Mesh.ARRAY_MAX); output[Mesh.ARRAY_VERTEX] = vertices; output[Mesh.ARRAY_TEX_UV] = texture_uvs; output[Mesh.ARRAY_COLOR] = vertex_colors; composed.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, output)
			var material := node.get_active_material(surface).duplicate() as ShaderMaterial
			if material == null: return false
			material.set_shader_parameter("double_sided", false); material.set_shader_parameter("room_clip_count", 0); material.set_shader_parameter("portal_clip_enabled", false); material.set_shader_parameter("portal_floor_clip_count", 0); composed.surface_set_material(composed.get_surface_count() - 1, material); added = true
		if not added: return false
	for node: MeshInstance3D in native_nodes:
		var removed := {}
		for surface in node.mesh.get_surface_count():
			var arrays: Array = node.mesh.surface_get_arrays(surface); var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var count := indices.size() if not indices.is_empty() else points.size(); var faces: Array = []
			for triangle in range(0, count, 3):
				var ids := [indices[triangle] if not indices.is_empty() else triangle, indices[triangle + 1] if not indices.is_empty() else triangle + 1, indices[triangle + 2] if not indices.is_empty() else triangle + 2]; var front := true; var back := true
				for id: int in ids: front = front and absf(node.to_global(points[id])[axis] - minimum) < 0.00001; back = back and absf(node.to_global(points[id])[axis] - maximum) < 0.00001
				if front or back: faces.append([points[ids[0]], points[ids[1]], points[ids[2]]])
			removed[surface] = faces
		node.mesh = _mesh_without_faces(node.mesh, removed)
		for surface in node.mesh.get_surface_count():
			var material := node.get_active_material(surface) as ShaderMaterial
			if material == null: continue
			material = material.duplicate() as ShaderMaterial; material.set_shader_parameter("double_sided", true); node.set_surface_override_material(surface, material)
	var view := MeshInstance3D.new(); view.name = "PairedDoorFaces"; view.mesh = composed; leaf.add_child(view)
	return true
func _open_sliding_leaves(portal: Dictionary, source_side: bool, stage: String, room_key: String, profile: Dictionary) -> bool:
	var raw: Array = portal["source_contact_raw"] if source_side else portal["reverse_source_contact_raw"]; var yaw := int(raw[3]); var quadrant := (yaw & 4095) >> 10; var directions := [-1, 0, 1, 0, -1]; var a := int(directions[quadrant]); var b := int(directions[quadrant + 1]); var c := int(profile["offset_raw"][0]); var e := int(profile["offset_raw"][1]); var speed := int((absi(c) - 8) / 10); var ticks := int(profile["opening_ticks"]); var movement_q := ((yaw + 0x200) & 4095) >> 10; var closed_yaw := -float((yaw + 0x800) & 4095) * TAU / 4096.0
	var loaded := await _sliding_door_models(stage, profile)
	if loaded.is_empty(): return false
	var group := Node3D.new(); group.name = "OpenDoor_" + room_key.replace(":", "_"); add_child(group); var closed: Array[Vector3] = []; var shifts: Array[Vector3] = []; var index := 0
	for entry: Array in loaded:
		var model: Dictionary = entry[0]; var scene: PackedScene = entry[1]
		var signed_c := c if index == 0 else -c; var signed_speed := speed if index == 0 else -speed; var pivot := Node3D.new(); group.add_child(pivot); pivot.global_position = Vector3(-float(raw[0] + signed_c * a + e * b), -float(raw[1]), float(raw[2] + signed_c * b - e * a)) / 256.0 + room_offsets[room_key]; pivot.rotation.y = closed_yaw
		var panel := scene.instantiate() as Node3D; pivot.add_child(panel); var scale: Array = model["native_scale_raw"]; panel.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0; preload("res://scripts/world/rendering/native_material.gd").apply(panel, 128.0)
		if portal.has("destination_panel") and not _compose_leaf_faces(portal, panel, true): group.queue_free(); return false
		for node: MeshInstance3D in panel.find_children("*", "MeshInstance3D", true, false): _add_collision(node, node.mesh)
		closed.append(pivot.position); shifts.append(Vector3(-signed_speed * int(directions[movement_q]), 0, signed_speed * int(directions[movement_q + 1])) / 256.0 * ticks); index += 1
	_create_doorway_depth(portal, group)
	var sweep := AABB(group.get_child(0).global_position, Vector3.ZERO)
	for leaf_index in group.get_child_count():
		for node: MeshInstance3D in group.get_child(leaf_index).find_children("*", "MeshInstance3D", true, false):
			var bounds := node.mesh.get_aabb()
			for corner in 8:
				var point := node.to_global(bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)); sweep = sweep.expand(point).expand(point + shifts[leaf_index])
	group.set_meta("sweep_bounds", sweep); group.set_meta("sliding", true); group.set_meta("closed_positions", closed); group.set_meta("sounds", profile["sounds"]); group.set_meta("closing_ticks", int(profile["closing_ticks"])); group.set_meta("tick_rate", float(profile["tick_rate"]))
	portal_leaves[_portal_key(portal)] = group; door_sound.emit(int(profile["sounds"][0])); var duration := float(ticks) / float(profile["tick_rate"]); var tween := create_tween().set_parallel(true)
	for leaf_index in group.get_child_count(): tween.tween_property(group.get_child(leaf_index), "position", closed[leaf_index] + shifts[leaf_index], duration)
	if int(profile["sounds"][1]) >= 0: tween.tween_callback(door_sound.emit.bind(int(profile["sounds"][1]))).set_delay(duration)
	return true
func _sliding_door_models(stage: String, profile: Dictionary) -> Array:
	var loaded: Array = []
	for variant: int in profile["variants"]:
		var model: Dictionary = {}
		for candidate: Dictionary in props.get(stage, {}).get("native_doors", []):
			if int(candidate.get("controller_class", 1)) == 3 and int(candidate["variant"]) == variant: model = candidate; break
		var scene: PackedScene = (sliding_scenes.get(str(model.get("model_file", ""))) if sliding_scenes.has(str(model.get("model_file", ""))) else await _threaded_scene("res://assets/stage_props/" + str(model["model_file"]))) if not model.is_empty() else null
		if scene == null: push_error("Missing native door resource %s variant %d" % [stage, variant]); return []
		sliding_scenes[str(model["model_file"])] = scene; loaded.append([model, scene])
	return loaded
func _close_leaf(leaf: Node3D) -> void:
	if not leaf.has_meta("sliding"):
		await create_tween().tween_property(leaf, "rotation:y", float(leaf.get_meta("closed_yaw")), 0.25).finished
		door_sound.emit(0xB9)
		return
	var closed: Array = leaf.get_meta("closed_positions"); var sounds: Array = leaf.get_meta("sounds"); var tween := create_tween().set_parallel(true)
	door_sound.emit(int(sounds[2]))
	for index in leaf.get_child_count(): tween.tween_property(leaf.get_child(index), "position", closed[index], float(leaf.get_meta("closing_ticks")) / float(leaf.get_meta("tick_rate")))
	await tween.finished
func _leaf_bounds(leaf: Node3D) -> AABB:
	var result := AABB(leaf.global_position, Vector3.ZERO)
	for node: MeshInstance3D in leaf.find_children("*", "MeshInstance3D", true, false):
		var bounds := node.mesh.get_aabb()
		for corner in 8: result = result.expand(node.to_global(bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)))
	return result
func _slab_faces(node: MeshInstance3D, source: Mesh, slab: AABB) -> Dictionary:
	var result := {}
	for surface in source.get_surface_count():
		var arrays: Array = source.surface_get_arrays(surface); var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var count := indices.size() if not indices.is_empty() else points.size(); var faces: Array = []
		for triangle in range(0, count, 3):
			var ids := [indices[triangle] if not indices.is_empty() else triangle, indices[triangle + 1] if not indices.is_empty() else triangle + 1, indices[triangle + 2] if not indices.is_empty() else triangle + 2]; var inside := true
			for id: int in ids: inside = inside and slab.has_point(node.to_global(points[id]))
			if inside: faces.append([points[ids[0]], points[ids[1]], points[ids[2]]])
		if not faces.is_empty(): result[surface] = faces
	return result
func _door_sweep_bounds(pivot: Node3D, panel: Node3D, closed_yaw: float, open_yaw: float) -> AABB:
	var points := PackedVector3Array()
	var parent := pivot.get_parent() as Node3D
	for node: MeshInstance3D in panel.find_children("*", "MeshInstance3D", true, false):
		var bounds := node.mesh.get_aabb()
		for corner in 8:
			var point := pivot.to_local(node.to_global(bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)))
			for step in 33: points.append(pivot.global_position + parent.global_basis * (Basis(Vector3.UP, lerpf(closed_yaw, open_yaw, float(step) / 32.0)) * point))
	if points.is_empty(): return AABB(pivot.global_position, Vector3.ZERO)
	var result := AABB(points[0], Vector3.ZERO)
	for point in points: result = result.expand(point)
	return result
func _create_doorway_depth(portal: Dictionary, leaf: Node3D) -> void:
	var key := _portal_key(portal)
	if portal_depth_views.has(key): return
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2
	var lateral := 2 if axis == 0 else 0
	var center: Array = portal["world_center"]
	var width := float(portal["shared_panel_size"][0]) * 0.5
	var height := float(portal["shared_panel_size"][1]) * 0.5
	var minimum := float(center[axis])
	var maximum := minimum
	for side: String in ["source", "destination"]:
		if not portal.has("source_panel" if side == "source" else "destination_panel"): continue
		var room: Dictionary = portal[side]
		var room_key := _room_key(str(room["stage"]), int(room["area"]))
		var panel: Dictionary = portal["source_panel" if side == "source" else "destination_panel"]
		var plane := float(panel["center"][axis]) + float(room_offsets[room_key][axis])
		minimum = minf(minimum, plane); maximum = maxf(maximum, plane)
	for node: MeshInstance3D in leaf.find_children("*", "MeshInstance3D", true, false):
		var bounds := node.mesh.get_aabb()
		for corner in 8:
			var point := bounds.position + Vector3(bounds.size.x if corner & 1 else 0.0, bounds.size.y if corner & 2 else 0.0, bounds.size.z if corner & 4 else 0.0)
			var world := node.to_global(point)
			minimum = minf(minimum, world[axis]); maximum = maxf(maximum, world[axis])
	if maximum - minimum <= 0.00001: return
	var room: Dictionary = portal["source"]
	var room_key := _room_key(str(room["stage"]), int(room["area"]))
	var node: MeshInstance3D = mesh_nodes[room_key][str(portal["source_panel"]["node"])]
	var mesh := ArrayMesh.new()
	var seen := {}
	var inverse := global_transform.affine_inverse()
	for surface in node.mesh.get_surface_count():
		var original: Array = node.mesh.surface_get_arrays(surface)
		var points: PackedVector3Array = original[Mesh.ARRAY_VERTEX]
		var indices: PackedInt32Array = original[Mesh.ARRAY_INDEX] if original[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array()
		var uvs: PackedVector2Array = original[Mesh.ARRAY_TEX_UV]
		var colors: PackedColorArray = original[Mesh.ARRAY_COLOR]
		var vertices := PackedVector3Array(); var texture_uvs := PackedVector2Array(); var vertex_colors := PackedColorArray()
		var count := indices.size() if not indices.is_empty() else points.size()
		for triangle in range(0, count, 3):
			for edge in 3:
				var ia := indices[triangle + edge] if not indices.is_empty() else triangle + edge
				var ib := indices[triangle + (edge + 1) % 3] if not indices.is_empty() else triangle + (edge + 1) % 3
				var a := node.to_global(points[ia]); var b := node.to_global(points[ib])
				if absf(a[axis] - float(center[axis])) > 1.0 / 256.0 or absf(b[axis] - float(center[axis])) > 1.0 / 256.0: continue
				var vertical := absf(a[lateral] - b[lateral]) < 0.00001 and absf(absf(a[lateral] - float(center[lateral])) - width) < 1.0 / 256.0 and minf(a.y, b.y) >= float(center[1]) - height - 0.00001 and maxf(a.y, b.y) <= float(center[1]) + height + 0.00001
				var ceiling := absf(a.y - float(center[1]) - height) < 0.00001 and absf(b.y - a.y) < 0.00001 and minf(a[lateral], b[lateral]) >= float(center[lateral]) - width - 0.00001 and maxf(a[lateral], b[lateral]) <= float(center[lateral]) + width + 0.00001
				if not vertical and not ceiling: continue
				var edge_key := _triangle_key(a, b, (a + b) * 0.5)
				if seen.has(edge_key): continue
				seen[edge_key] = true
				var far_a := a; var far_b := b; a[axis] = minimum; b[axis] = minimum; far_a[axis] = maximum; far_b[axis] = maximum
				for corner in [0, 1, 2, 1, 3, 2]:
					vertices.append(inverse * [a, b, far_a, far_b][corner]); texture_uvs.append(uvs[ia if corner % 2 == 0 else ib]); vertex_colors.append(colors[ia if corner % 2 == 0 else ib])
		if vertices.is_empty(): continue
		var arrays: Array = []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_TEX_UV] = texture_uvs; arrays[Mesh.ARRAY_COLOR] = vertex_colors
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material := node.get_active_material(surface).duplicate() as ShaderMaterial
		material.set_shader_parameter("double_sided", true); material.set_shader_parameter("room_clip_count", 0); material.set_shader_parameter("portal_clip_enabled", false); material.set_shader_parameter("portal_floor_clip_count", 0)
		mesh.surface_set_material(mesh.get_surface_count() - 1, material)
	if mesh.get_surface_count() == 0: return
	var depth := MeshInstance3D.new(); depth.name = "DoorwayDepth"; depth.mesh = mesh; depth.set_meta("pc_doorway_depth", maximum - minimum); add_child(depth); portal_depth_views[key] = depth
func _create_doorway_backing(portal: Dictionary, key: String) -> void:
	if portal.has("destination_panel") or rooms.has(_room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))) or portal_backings.has(key) or not portal_leaves.has(key): return
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var sign := _outward_sign(portal, true); var center: Array = portal["world_center"]; var sweep: AABB = portal_leaves[key].get_meta("sweep_bounds"); var far := (sweep.end[axis] if sign > 0.0 else sweep.position[axis]) - float(center[axis])
	var quad := QuadMesh.new(); quad.size = Vector2(float(portal["shared_panel_size"][0]) + 0.2, float(portal["shared_panel_size"][1]) + 0.2); var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.albedo_color = Color.BLACK; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.disable_fog = true; quad.material = material
	var backing := MeshInstance3D.new(); backing.name = "DoorwayBacking"; backing.mesh = quad; backing.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; add_child(backing); backing.global_position = Vector3(float(center[0]), float(center[1]), float(center[2])) + (Vector3.RIGHT if axis == 0 else Vector3.BACK) * (far + 0.05 * sign); backing.rotation.y = PI * 0.5 if axis == 0 else 0.0; portal_backings[key] = backing
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
		# Count the pass only once the body centre crosses a body radius beyond the doorway plane; sliding along the wall jitters around the plane itself.
		if before > body_radius or after <= body_radius: continue
		var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]); var height := float(portal["shared_panel_size"][1]); var lateral_clearance := maxf(0.0, width * 0.5 - body_radius); var bottom := float(center[1]) - height * 0.5
		var crossing := previous.lerp(current, clampf((body_radius - before) / (after - before), 0.0, 1.0))
		if absf(crossing[lateral] - float(center[lateral])) > lateral_clearance or crossing.y < bottom - 0.05 or crossing.y + body_height > bottom + height + 0.05: continue
		if absf(current[lateral] - float(center[lateral])) > lateral_clearance or current.y < bottom - 0.05 or current.y + body_height > bottom + height + 0.05: continue
		var target: Dictionary = portal["destination"] if source_side else portal["source"]
		var target_key := _room_key(str(target["stage"]), int(target["area"]))
		if not rooms.has(target_key) or loading_rooms.has(target_key): continue
		return {"stage": str(target["stage"]), "area": int(target["area"]), "portal": portal}
	return {}
func doorway_camera_yaw(point: Vector3, yaw: float, motion: Vector3) -> float:
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		if active_room_key != source_key and active_room_key != destination_key: continue
		var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var center: Array = portal["world_center"]; var height := float(portal["shared_panel_size"][1]) * 0.5
		if absf(motion[axis]) < 0.05 or absf(motion[axis]) <= absf(motion[lateral]): continue
		if absf(point[axis] - float(center[axis])) > body_radius + 0.25 or absf(point[lateral] - float(center[lateral])) > float(portal["shared_panel_size"][0]) * 0.5 + body_radius or point.y < float(center[1]) - height - 0.05 or point.y > float(center[1]) + height: continue
		var normal_yaw := PI * 0.5 if axis == 0 else 0.0; var difference := wrapf(yaw - normal_yaw, -PI, PI)
		if absf(difference) > PI * 0.5: normal_yaw += PI; difference = wrapf(yaw - normal_yaw, -PI, PI)
		return normal_yaw + clampf(difference, -PI / 6.0, PI / 6.0)
	return yaw
func _outward_sign(portal: Dictionary, source_side: bool) -> float:
	var side: Dictionary = portal["source_panel"] if source_side else portal["destination_panel"]; var raw: Array = portal["source_contact_raw"] if source_side else portal["reverse_source_contact_raw"]; var yaw := int(portal["source_yaw_raw"] if source_side else portal["reverse_source_yaw_raw"]); var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var yaw_radians := -float(yaw) * TAU / 4096.0; var contact := -float(raw[axis]) / 256.0 if axis == 0 else float(raw[axis]) / 256.0; var face := float(side["center"][axis]); var contact_sign := signf(face - contact)
	var player_forward := Vector3(-sin(yaw_radians), 0.0, -cos(yaw_radians)); var player_forward_sign := signf(player_forward[axis])
	return player_forward_sign if player_forward_sign != 0.0 else contact_sign
func _open_mesh_for(room_key: String, node_name: String, extra_key: String = "") -> Mesh:
	var key := _mesh_key(room_key, node_name); var mesh_node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(node_name)
	var original: Mesh = source_meshes.get(key, mesh_node.mesh); var faces_by_surface := {}; var open_keys: Array[String] = []
	var candidates: Array = portal_layout.duplicate(); candidates.append_array(transition_doors.values())
	for portal: Dictionary in candidates:
		var portal_key := _portal_key(portal)
		if not opened_portals.has(portal_key) and not transition_doors.has(portal_key) and portal_key != extra_key: continue
		var sides: Array = [[portal["source"], portal["source_panel"]]]
		if portal.has("destination_panel"): sides.append([portal["destination"], portal["destination_panel"]])
		for side in sides:
			if _room_key(str(side[0]["stage"]), int(side[0]["area"])) != room_key or str(side[1]["node"]) != node_name: continue
			open_keys.append(portal_key)
			for quad: Dictionary in side[1]["quads"]:
				var surface := int(quad.get("primitive_index", side[1]["primitive_index"])); var triangles: Array = faces_by_surface.get(surface, []); triangles.append_array(quad["triangles_local"]); faces_by_surface[surface] = triangles
			if portal.has("leaf_slab"):
				open_keys[open_keys.size() - 1] += "+slab"
				var slab_faces := _slab_faces(mesh_node, original, portal["leaf_slab"])
				for surface: int in slab_faces:
					var triangles: Array = faces_by_surface.get(surface, []); triangles.append_array(slab_faces[surface]); faces_by_surface[surface] = triangles
	open_keys.sort(); var cache_key := key + "|" + ",".join(PackedStringArray(open_keys)) + "|" + str(original.get_instance_id())
	if not open_mesh_cache.has(cache_key): open_mesh_cache[cache_key] = _mesh_without_faces(original, faces_by_surface)
	return open_mesh_cache[cache_key]
func _refresh_open_meshes(room_key: String, node_name: String) -> void:
	var mesh_node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(node_name)
	if not is_instance_valid(mesh_node): return
	mesh_node.mesh = _open_mesh_for(room_key, node_name)
	_refresh_collision(room_key, mesh_node, mesh_node.mesh)
	camera_layers_dirty = true
	var entry: Dictionary = room_info[room_key]
	preload("res://scripts/world/flutter/window_view.gd").apply(rooms[room_key], str(entry["stage"]), int(entry["area"]))
static func _mesh_without_faces(source: Mesh, faces_by_surface: Dictionary) -> Mesh:
	if not source is ArrayMesh: return source
	var result := ArrayMesh.new()
	for surface in source.get_surface_count():
		var arrays: Array = source.surface_get_arrays(surface); var triangles: Array = faces_by_surface.get(surface, []); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		if not triangles.is_empty() and not vertices.is_empty():
			var wanted := {}
			for tri: Array in triangles: wanted[_triangle_key(tri[0], tri[1], tri[2])] = true
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array()
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
static func _remove_unindexed(arrays: Array, vertices: PackedVector3Array, wanted: Dictionary) -> Array:
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
static func _filter_attribute(values: Variant, vertices: PackedInt32Array, vertex_count: int) -> Variant:
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
static func _degenerate_attribute(values: Variant, old_vertex_count: int) -> Variant:
	if values is PackedVector2Array: return PackedVector2Array([Vector2.ZERO, Vector2.ZERO, Vector2.ZERO])
	if values is PackedVector3Array: return PackedVector3Array([Vector3.UP, Vector3.UP, Vector3.UP])
	if values is PackedVector4Array: return PackedVector4Array([Vector4.ZERO, Vector4.ZERO, Vector4.ZERO])
	if values is PackedColorArray: return PackedColorArray([Color.WHITE, Color.WHITE, Color.WHITE])
	if values is PackedFloat32Array or values is PackedFloat64Array or values is PackedInt32Array or values is PackedInt64Array or values is PackedByteArray:
		var stride := int(values.size() / old_vertex_count) if old_vertex_count > 0 else 1; var packed_result: Variant = values.duplicate(); packed_result.clear()
		for component in stride * 3: packed_result.append(0)
		return packed_result
	return values
static func _triangle_key(a: Variant, b: Variant, c: Variant) -> String:
	var points := [_as_vector3(a), _as_vector3(b), _as_vector3(c)]; var keys: Array[String] = []
	for point: Vector3 in points: keys.append("%d,%d,%d" % [roundi(point.x * 65536.0), roundi(point.y * 65536.0), roundi(point.z * 65536.0)])
	keys.sort(); return "%s|%s|%s" % [keys[0], keys[1], keys[2]]
static func _as_vector3(value: Variant) -> Vector3: return value if value is Vector3 else Vector3(float(value[0]), float(value[1]), float(value[2]))
func _add_collision(mesh_node: MeshInstance3D, mesh: Mesh, layers: Array[int] = [1, 4]) -> void:
	var geometry := mesh.create_trimesh_shape()
	if geometry == null: return
	for layer: int in layers:
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
	_clip_parked_exterior(visible)
	_clip_exterior_rooms()
	for support in floor_supports.values():
		if is_instance_valid(support): support.collision_layer = 0; support.collision_mask = 0; support.queue_free()
	floor_supports.clear()
	for room_key in rooms:
		rooms[room_key].visible = visible.has(room_key)
		rooms[room_key].set_meta("native_stream_room_active", room_key == active_room_key)
		for collider: CollisionObject3D in rooms[room_key].find_children("*", "CollisionObject3D", true, false):
			if collider.has_meta("native_stream_actor_layer"): collider.collision_layer = int(collider.get_meta("native_stream_actor_layer")) if room_key == active_room_key else 0
		var clip_plane := Vector4.ZERO
		var clip_enabled := false
		var room_planes := PackedVector4Array(); var room_limits := PackedFloat32Array(); var room_clip_bounds := PackedVector4Array(); var room_clip_depths := PackedVector2Array(); var room_clip_bounded: Array[bool] = []; var room_clip_view_gate: Array[bool] = []; var room_clip_view_cut: Array[bool] = []
		for portal: Dictionary in portal_layout:
			var portal_key := _portal_key(portal)
			if not opened_portals.has(portal_key): continue
			var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
			if room_key != source_key and room_key != destination_key: continue
			var source_side: bool = room_key == source_key; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var inward := -_outward_sign(portal, source_side); var plane := Vector4.ZERO; plane[axis] = inward; plane.w = -float(portal["world_center"][axis]) * inward; room_planes.append(plane)
			var camera_source: bool = portal_camera_sides.get(portal_key, str(opened_from.get(portal_key, "")) == source_key); room_limits.append(-0.0001 if camera_source == source_side else 0.0001)
			var bounded := bool(room_info[room_key].get("exterior", false)); room_clip_bounded.append(bounded); room_clip_view_gate.append(room_key != active_room_key and (source_key == active_room_key or destination_key == active_room_key)); room_clip_view_cut.append(bounded && room_key == active_room_key)
			if bounded or room_clip_view_gate.back():
				var region := _bounded_portal_region(str(room_key), portal, source_side); var lateral := 2 if axis == 0 else 0; var lateral_sign := plane.x if axis == 0 else -plane.z; var first := region.position[lateral] * lateral_sign; var last := region.end[lateral] * lateral_sign; room_clip_bounds.append(Vector4(minf(first, last), maxf(first, last), region.position.y, region.end.y)); first = region.position[axis] * inward + plane.w; last = region.end[axis] * inward + plane.w; room_clip_depths.append(Vector2(minf(first, last), maxf(first, last)))
			else: room_clip_bounds.append(Vector4.ZERO); room_clip_depths.append(Vector2.ZERO)
		var room_count := room_planes.size(); room_planes.resize(16); room_limits.resize(16); room_clip_bounds.resize(16); room_clip_depths.resize(16); room_clip_bounded.resize(16); room_clip_view_gate.resize(16); room_clip_view_cut.resize(16)
		var floor_planes := PackedVector4Array(); var floor_bounds := PackedVector4Array(); var floor_depths := PackedVector2Array(); var floor_bounded: Array[bool] = []
		if room_key == active_room_key:
			for portal: Dictionary in portal_layout:
				if not opened_portals.has(_portal_key(portal)): continue
				var source_side: bool = _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) == room_key; var destination_side: bool = _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])) == room_key
				if not source_side and not destination_side: continue
				var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var inward := -_outward_sign(portal, source_side); var plane := Vector4.ZERO; var center: Array = portal["world_center"]; var width := float(portal["shared_panel_size"][0]) * 0.5; var bottom := float(center[1]) - float(portal["shared_panel_size"][1]) * 0.5
				plane[axis] = inward; plane.w = -float(center[axis]) * inward; floor_planes.append(plane); floor_bounds.append(Vector4(float(center[lateral]) - width, float(center[lateral]) + width, bottom - 0.025, bottom + 0.025))
				var bounded := bool(room_info[room_key].get("exterior", false)); floor_bounded.append(bounded)
				if bounded:
					var region := _bounded_portal_region(str(room_key), portal, source_side); var first := region.position[axis] * inward + plane.w; var last := region.end[axis] * inward + plane.w; floor_depths.append(Vector2(minf(first, last), maxf(first, last)))
				else: floor_depths.append(Vector2.ZERO)
		var floor_count := floor_planes.size(); floor_planes.resize(16); floor_bounds.resize(16); floor_depths.resize(16); floor_bounded.resize(16)
		if room_key != active_room_key and visible.has(room_key):
			for portal: Dictionary in portal_layout:
				if not opened_portals.has(_portal_key(portal)): continue
				var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
				if not ((source_key == active_room_key and destination_key == room_key) or (destination_key == active_room_key and source_key == room_key)): continue
				var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var inward := -_outward_sign(portal, source_key == room_key); clip_plane[axis] = inward; clip_plane.w = -float(portal["world_center"][axis]) * inward; clip_enabled = true; break
		var shape_state := _room_clip_state(str(room_key), true) if room_key == active_room_key else {}
		var applied_signature := [room_count, room_planes, room_clip_bounds, room_clip_depths, room_clip_bounded, room_clip_view_gate, room_clip_view_cut, floor_count, floor_planes, floor_bounds, floor_depths, floor_bounded].hash()
		for node: MeshInstance3D in mesh_nodes[room_key].values():
			for surface in node.mesh.get_surface_count():
				var material := node.get_active_material(surface) as ShaderMaterial
				if material != null and int(material.get_meta("room_state_signature", 0)) == applied_signature: material.set_shader_parameter("room_clip_limits", room_limits)
				elif material != null:
					material.set_meta("room_state_signature", applied_signature)
					material.set_shader_parameter("portal_clip_enabled", false); material.set_shader_parameter("room_clip_count", room_count); material.set_shader_parameter("room_clip_planes", room_planes); material.set_shader_parameter("room_clip_limits", room_limits); material.set_shader_parameter("room_clip_bounds", room_clip_bounds); material.set_shader_parameter("room_clip_depths", room_clip_depths); material.set_shader_parameter("room_clip_bounded", room_clip_bounded); material.set_shader_parameter("room_clip_view_gate", room_clip_view_gate); material.set_shader_parameter("room_clip_view_cut", room_clip_view_cut); material.set_shader_parameter("portal_floor_clip_count", floor_count); material.set_shader_parameter("portal_floor_clip_planes", floor_planes); material.set_shader_parameter("portal_floor_clip_bounds", floor_bounds); material.set_shader_parameter("portal_floor_clip_depths", floor_depths); material.set_shader_parameter("portal_floor_clip_bounded", floor_bounded)
			for body in node.get_children():
				if not body is StaticBody3D: continue
				if body.name == "RoomCollision_1":
					if room_key == active_room_key:
						var geometry := _player_room_shape(str(room_key), node, shape_state)
						for shape: CollisionShape3D in body.find_children("*", "CollisionShape3D", true, false): shape.shape = geometry
					body.collision_layer = 1 if room_key == active_room_key and not bool(body.get_meta("native_floor_replaced", false)) else 0
				if body.name == "GeneratedRoofPlayerCollision": body.collision_layer = 16 if room_key == active_room_key else 0
		_refresh_native_floor_apertures(str(room_key))
		for body: StaticBody3D in rooms[room_key].find_children("NativePlacementFloor_*", "StaticBody3D", true, false): body.collision_layer = 1 if room_key == active_room_key else 0
	for portal: Dictionary in portal_layout:
		if not opened_portals.has(_portal_key(portal)): continue
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		if source_key == active_room_key and rooms.has(destination_key): _add_floor_support(destination_key, portal, false)
		elif destination_key == active_room_key and rooms.has(source_key): _add_floor_support(source_key, portal, true)
	_refresh_camera_layers()
func _refresh_camera_layers() -> void:
	camera_layers_dirty = false
	camera_collision_rooms.clear()
	for room_key in rooms:
		var keep: bool = room_key == active_room_key or rooms[room_key].visible
		if keep: camera_collision_rooms[room_key] = true
		var state := _room_clip_state(str(room_key), room_key == active_room_key) if keep else {}
		for node: MeshInstance3D in mesh_nodes[room_key].values():
			var body := node.get_node_or_null("RoomCollision_4") as StaticBody3D
			if body == null: continue
			if keep:
				var geometry := _camera_room_shape(str(room_key), node, state)
				for child in body.get_children():
					if child is CollisionShape3D and child.shape != geometry: child.shape = geometry
			if body.collision_layer != (4 if keep else 0): body.collision_layer = 4 if keep else 0
func _camera_inside_room(room_key: String) -> bool:
	if not has_camera_space_position or not room_bounds[room_key].grow(body_radius).has_point(camera_space_position): return false
	if bool(room_info[room_key].get("exterior", false)): return true
	for portal: Dictionary in portal_layout:
		var source_side := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) == room_key
		if not source_side and _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])) != room_key: continue
		var axis := 0 if str(portal["normal_axis"]) == "x" else 2
		if (camera_space_position[axis] - float(portal["world_center"][axis])) * _outward_sign(portal, source_side) > body_radius: return false
	return true
func _room_clip_state(room_key: String, active: bool, extra_key: String = "") -> Dictionary:
	var clip_keys: Array[String] = []
	var clips: Array[Dictionary] = []
	for portal: Dictionary in portal_layout:
		var portal_key := _portal_key(portal)
		if not opened_portals.has(portal_key) and portal_key != extra_key: continue
		var source_side := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])) == room_key
		if not source_side and _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])) != room_key: continue
		clip_keys.append(portal_key)
		clips.append({"axis": 0 if str(portal["normal_axis"]) == "x" else 2, "plane": portal["world_center"][0 if str(portal["normal_axis"]) == "x" else 2], "outward": _outward_sign(portal, source_side)})
		if bool(room_info[room_key].get("exterior", false)) and active: clips.back()["region"] = _bounded_portal_region(room_key, portal, source_side)
	clip_keys.sort()
	return {"signature": ",".join(PackedStringArray(clip_keys)) + (":active" if active else ":view"), "clips": clips}
func _shape_variants(room_key: String, node_name: String, mesh: Mesh, signature: String) -> Dictionary:
	var cache_key := _mesh_key(room_key, node_name) + "|" + str(mesh.get_instance_id()) + "|" + signature
	if not camera_shape_cache.has(cache_key): camera_shape_cache[cache_key] = {}
	return camera_shape_cache[cache_key]
func _finish_variant(variants: Dictionary) -> void:
	if not variants.has("task"): return
	WorkerThreadPool.wait_for_task_completion(int(variants["task"]))
	var vertices: PackedVector3Array = variants["holder"].get("vertices", PackedVector3Array()); var geometry: ConcavePolygonShape3D
	if not vertices.is_empty(): geometry = ConcavePolygonShape3D.new(); geometry.set_faces(vertices)
	if geometry != null: geometry.backface_collision = true
	variants.erase("task"); variants.erase("holder"); variants["shape"] = geometry
func _camera_room_shape(room_key: String, node: MeshInstance3D, state: Dictionary = {}) -> ConcavePolygonShape3D:
	if state.is_empty(): state = _room_clip_state(room_key, room_key == active_room_key)
	var variants := _shape_variants(room_key, str(node.name), node.mesh, str(state["signature"]))
	_finish_variant(variants)
	if variants.has("shape"): return variants["shape"]
	var clips: Array = state["clips"]
	var geometry: ConcavePolygonShape3D
	if clips.is_empty(): geometry = node.mesh.create_trimesh_shape() as ConcavePolygonShape3D
	else:
		var vertices := _clip_room_faces(node.mesh.get_faces(), node.global_transform, clips)
		if not vertices.is_empty(): geometry = ConcavePolygonShape3D.new(); geometry.set_faces(vertices)
	if geometry != null: geometry.backface_collision = true
	variants["shape"] = geometry
	return geometry
static func _clip_room_faces(faces: PackedVector3Array, transform: Transform3D, clips: Array) -> PackedVector3Array:
	var vertices := PackedVector3Array()
	var inverse := transform.affine_inverse()
	for index in range(0, faces.size(), 3):
		var polygon: Array[Vector3] = [transform * faces[index], transform * faces[index + 1], transform * faces[index + 2]]
		var polygons: Array = [polygon]
		for clip: Dictionary in clips:
			var clipped: Array = []
			for current: Array[Vector3] in polygons:
				var safe := _clip_floor_triangle(current, int(clip["axis"]), float(clip["plane"]), float(clip["outward"]), 0.0)
				if safe.size() >= 3: clipped.append(safe)
				if clip.has("region"):
					var crossing := _clip_floor_triangle(current, int(clip["axis"]), float(clip["plane"]), -float(clip["outward"]), -0.00001)
					if crossing.size() >= 3: clipped.append_array(_subtract_region(crossing, clip["region"]))
			polygons = clipped
		for current: Array[Vector3] in polygons:
			for vertex in range(1, current.size() - 1): vertices.append(inverse * current[0]); vertices.append(inverse * current[vertex]); vertices.append(inverse * current[vertex + 1])
	return vertices
func _player_room_shape(room_key: String, node: MeshInstance3D, state: Dictionary = {}) -> ConcavePolygonShape3D:
	if state.is_empty(): state = _room_clip_state(room_key, room_key == active_room_key)
	var geometry := _camera_room_shape(room_key, node, state)
	if geometry == null: return null
	var variants := _shape_variants(room_key, str(node.name), node.mesh, str(state["signature"]))
	if not variants.has("player"):
		var shape := geometry.duplicate() as ConcavePolygonShape3D; shape.backface_collision = false; variants["player"] = shape
	return variants["player"]
func _add_floor_support(room_key: String, portal: Dictionary, neighbor_is_source: bool) -> void:
	var vertices := PackedVector3Array(); var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var center: Array = portal["world_center"]; var plane := float(center[axis]); var outward := _outward_sign(portal, neighbor_is_source)
	for mesh_node: MeshInstance3D in mesh_nodes[room_key].values():
		if mesh_node.mesh == null: continue
		vertices.append_array(_floor_support_node(room_key, mesh_node, mesh_node.mesh, axis, plane, outward))
	if vertices.is_empty(): return
	var arrays: Array = []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; var mesh := ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	for layer in [1, 4]:
		var body := StaticBody3D.new(); body.name = "RoomFloorSupport_%s_%d" % [room_key.replace(":", "_"), layer]; body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.create_trimesh_shape()
		if layer == 4: (shape.shape as ConcavePolygonShape3D).backface_collision = true
		body.add_child(shape); add_child(body); floor_supports[_mesh_key(room_key, _portal_key(portal)) + ":" + str(layer)] = body
func _floor_support_node(room_key: String, mesh_node: MeshInstance3D, mesh: Mesh, axis: int, plane: float, outward: float) -> PackedVector3Array:
	var cache_key := _mesh_key(room_key, str(mesh_node.name)) + "|" + str(mesh.get_instance_id()) + "|%d|%s|%s|%s" % [axis, plane, outward, body_radius]
	if floor_support_cache.has(cache_key): return floor_support_cache[cache_key]
	var vertices := PackedVector3Array(); var inverse := global_transform.affine_inverse()
	for surface in mesh.get_surface_count():
		if mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: continue
		var arrays: Array = mesh.surface_get_arrays(surface); var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var count := indices.size() if not indices.is_empty() else points.size()
		for triangle in range(0, count, 3):
			var ia := indices[triangle] if not indices.is_empty() else triangle; var ib := indices[triangle + 1] if not indices.is_empty() else triangle + 1; var ic := indices[triangle + 2] if not indices.is_empty() else triangle + 2; var a := mesh_node.to_global(points[ia]); var b := mesh_node.to_global(points[ib]); var c := mesh_node.to_global(points[ic])
			if (b - a).cross(c - a).normalized().y > -0.65: continue
			var polygon := _clip_floor_triangle([a, b, c], axis, plane, outward, body_radius)
			for index in range(1, polygon.size() - 1): vertices.append(inverse * polygon[0]); vertices.append(inverse * polygon[index]); vertices.append(inverse * polygon[index + 1])
	floor_support_cache[cache_key] = vertices
	return vertices
static func _clip_floor_triangle(triangle: Array[Vector3], axis: int, plane: float, outward: float, margin: float) -> Array[Vector3]:
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
	for key in camera_collision_rooms: keep[str(key)] = true
	for key in nearby_keys: keep[str(key)] = true
	for key in loading_rooms: keep[str(key)] = true
	for key in rooms.keys():
		if keep.has(str(key)): continue
		var room: Node = rooms[key]; rooms.erase(key); mesh_nodes.erase(key); var prefix := str(key) + ":"
		for mesh_key in source_meshes.keys(): if str(mesh_key).begins_with(prefix): source_meshes.erase(mesh_key)
		for mesh_key in camera_shape_cache.keys(): if str(mesh_key).begins_with(prefix): camera_shape_cache.erase(mesh_key)
		for mesh_key in open_mesh_cache.keys(): if str(mesh_key).begins_with(prefix): open_mesh_cache.erase(mesh_key)
		for mesh_key in collision_shape_cache.keys(): if str(mesh_key).begins_with(prefix): collision_shape_cache.erase(mesh_key)
		for mesh_key in floor_support_cache.keys(): if str(mesh_key).begins_with(prefix): floor_support_cache.erase(mesh_key)
		for portal_key in prepared_portals.keys(): if str(portal_key).contains(str(key)): prepared_portals.erase(portal_key)
		camera_layers_dirty = true
		_free_room_sliced(room)
func _collision_shape(room_key: String, node_name: String, mesh: Mesh, back: bool) -> Shape3D:
	var shape_key := _mesh_key(room_key, node_name) + "|" + str(mesh.get_instance_id()) + ("|back" if back else "|plain")
	if not collision_shape_cache.has(shape_key):
		var shape := mesh.create_trimesh_shape()
		if back and shape is ConcavePolygonShape3D: (shape as ConcavePolygonShape3D).backface_collision = true
		collision_shape_cache[shape_key] = shape
	return collision_shape_cache[shape_key]
func _free_room_sliced(room: Node) -> void:
	room.process_mode = Node.PROCESS_MODE_DISABLED
	var nodes := room.find_children("*", "", true, false); nodes.reverse()
	for index in nodes.size():
		if is_instance_valid(nodes[index]): nodes[index].queue_free()
		if index % 12 == 11: await get_tree().process_frame
		if not is_instance_valid(room): return
	room.queue_free()
func _refresh_collision(room_key: String, mesh_node: MeshInstance3D, mesh: Mesh) -> void:
	camera_layers_dirty = true
	for child in mesh_node.get_children():
		if child is not StaticBody3D: continue
		for item in child.get_children():
			if item is not CollisionShape3D: continue
			item.shape = _collision_shape(room_key, str(mesh_node.name), mesh, child.name == "RoomCollision_4")
const PREP_BUDGET_USEC := 2500
const PREFETCH_RADIUS := 8.0
var prep_steps: Array[Callable] = []
var prep_pending: Array[Dictionary] = []
var prepared_portals: Dictionary = {}
var prefetch_portals: Array[Dictionary] = []
var prefetch_for := ""
var nearby_keys: Dictionary = {}
var floor_support_cache: Dictionary = {}
func _process(_delta: float) -> void:
	if prep_steps.is_empty() and prep_pending.is_empty(): return
	var start := Time.get_ticks_usec()
	for index in range(prep_pending.size() - 1, -1, -1):
		var variants: Dictionary = prep_pending[index]["variants"]
		if not variants.has("task"): prep_pending.remove_at(index); continue
		if not WorkerThreadPool.is_task_completed(int(variants["task"])): continue
		var wants_player: bool = prep_pending[index]["player"]; prep_pending.remove_at(index); _finish_variant(variants)
		if wants_player and variants["shape"] != null and not variants.has("player"):
			var player_shape := (variants["shape"] as ConcavePolygonShape3D).duplicate() as ConcavePolygonShape3D; player_shape.backface_collision = false; variants["player"] = player_shape
		if Time.get_ticks_usec() - start > PREP_BUDGET_USEC: return
	while not prep_steps.is_empty():
		prep_steps.pop_front().call()
		if Time.get_ticks_usec() - start > PREP_BUDGET_USEC: break
func _prepare_around_active() -> void:
	if active_room_key.is_empty() or not rooms.has(active_room_key): return
	var keys := opened_portals.keys(); keys.sort(); var stamp := ",".join(PackedStringArray(keys)) + "|" + active_room_key
	for portal: Dictionary in portal_layout:
		var key := _portal_key(portal)
		if opened_portals.has(key) or not portal.has("source_panel") or not portal.has("destination_panel") or prepared_portals.get(key, "") == stamp: continue
		var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
		if source_key != active_room_key and destination_key != active_room_key: continue
		if not rooms.has(source_key) or not rooms.has(destination_key) or loading_rooms.has(source_key) or loading_rooms.has(destination_key): continue
		prepared_portals[key] = stamp
		var other := destination_key if source_key == active_room_key else source_key
		prep_steps.append(_prep_mesh.bind(source_key, str(portal["source_panel"]["node"]), key)); prep_steps.append(_prep_mesh.bind(destination_key, str(portal["destination_panel"]["node"]), key))
		for side in [[source_key, true], [destination_key, false]]: prep_steps.append(_prep_floor.bind(str(side[0]), key, bool(side[1]), str(portal["source_panel"]["node"]) if str(side[0]) == source_key else str(portal["destination_panel"]["node"])))
		for variant in [[active_room_key, true], [other, false], [other, true], [active_room_key, false]]: prep_steps.append(_prep_room.bind(str(variant[0]), bool(variant[1]), key, str(portal["source_panel"]["node"]) if str(variant[0]) == source_key else str(portal["destination_panel"]["node"])))
func _prep_mesh(room_key: String, node_name: String, extra_key: String) -> void:
	if not rooms.has(room_key) or not mesh_nodes.get(room_key, {}).has(node_name): return
	var mesh := _open_mesh_for(room_key, node_name, extra_key)
	prep_steps.append(_prep_collision.bind(room_key, node_name, mesh, false)); prep_steps.append(_prep_collision.bind(room_key, node_name, mesh, true))
func _prep_floor(room_key: String, portal_key: String, neighbor_is_source: bool, panel_node: String) -> void:
	var portal := _portal_by_key(portal_key)
	if not rooms.has(room_key) or portal.is_empty() or opened_portals.has(portal_key): return
	var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var plane := float((portal["world_center"] as Array)[axis]); var outward := _outward_sign(portal, neighbor_is_source)
	for node_name in mesh_nodes[room_key]: prep_steps.append(_prep_floor_node.bind(room_key, str(node_name), portal_key, axis, plane, outward, panel_node))
func _prep_floor_node(room_key: String, node_name: String, portal_key: String, axis: int, plane: float, outward: float, panel_node: String) -> void:
	var node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(node_name)
	if not is_instance_valid(node) or node.mesh == null or opened_portals.has(portal_key): return
	_floor_support_node(room_key, node, _open_mesh_for(room_key, node_name, portal_key) if node_name == panel_node else node.mesh, axis, plane, outward)
func _prep_collision(room_key: String, node_name: String, mesh: Mesh, back: bool) -> void:
	if rooms.has(room_key) and is_instance_valid(mesh): _collision_shape(room_key, node_name, mesh, back)
func _prep_room(room_key: String, active: bool, extra_key: String, panel_node: String) -> void:
	if not rooms.has(room_key) or opened_portals.has(extra_key): return
	var state := _room_clip_state(room_key, active, extra_key)
	for node_name in mesh_nodes[room_key]: prep_steps.append(_prep_node.bind(room_key, str(node_name), active, state, extra_key, panel_node))
func _prep_node(room_key: String, node_name: String, active: bool, state: Dictionary, extra_key: String, panel_node: String) -> void:
	var node: MeshInstance3D = mesh_nodes.get(room_key, {}).get(node_name)
	if not is_instance_valid(node) or node.mesh == null or opened_portals.has(extra_key): return
	var mesh: Mesh = _open_mesh_for(room_key, node_name, extra_key) if node_name == panel_node else node.mesh
	var variants := _shape_variants(room_key, node_name, mesh, str(state["signature"]))
	if variants.has("shape") or variants.has("task"): return
	var holder := {}; variants["holder"] = holder; variants["task"] = WorkerThreadPool.add_task(_clip_job.bind(mesh.get_faces(), node.global_transform, state["clips"], holder)); prep_pending.append({"variants": variants, "player": active})
static func _clip_job(faces: PackedVector3Array, transform: Transform3D, clips: Array, holder: Dictionary) -> void: holder["vertices"] = _clip_room_faces(faces, transform, clips)
func prefetch_near(position: Vector3) -> void:
	if prefetch_for != active_room_key:
		prefetch_for = active_room_key; prefetch_portals.clear(); nearby_keys.clear()
		for portal: Dictionary in portal_layout:
			var source_key := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var destination_key := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"]))
			if source_key != active_room_key and destination_key != active_room_key: continue
			var center: Array = portal["world_center"]; var other: Dictionary = portal["destination"] if source_key == active_room_key else portal["source"]
			prefetch_portals.append({"stage": str(other["stage"]), "area": int(other["area"]), "key": destination_key if source_key == active_room_key else source_key, "center": Vector3(float(center[0]), float(center[1]), float(center[2]))})
		for transition: Dictionary in ladder_transitions:
			var source_key := _room_key(str(transition["source"]["stage"]), int(transition["source"]["area"])); var destination_key := _room_key(str(transition["destination"]["stage"]), int(transition["destination"]["area"]))
			if not bool(transition.get("seamless", false)) or (source_key != active_room_key and destination_key != active_room_key): continue
			var from_source := source_key == active_room_key; var foot: Array = transition["source_transform_raw"] if from_source else transition["destination_transform_raw"]; var other: Dictionary = transition["destination"] if from_source else transition["source"]
			prefetch_portals.append({"stage": str(other["stage"]), "area": int(other["area"]), "key": destination_key if from_source else source_key, "center": Vector3(-float(foot[0]), 0.0 if int(foot[1]) == -1 else -float(foot[1]), float(foot[2])) / 256.0 + offset_for(str(transition["source"]["stage"]) if from_source else str(transition["destination"]["stage"]), int(transition["source"]["area"]) if from_source else int(transition["destination"]["area"]))})
	nearby_keys.clear()
	for entry: Dictionary in prefetch_portals:
		var distance := (entry["center"] as Vector3).distance_squared_to(position)
		if distance > PREFETCH_RADIUS * PREFETCH_RADIUS * 1.5625: continue
		nearby_keys[entry["key"]] = true
		if distance <= PREFETCH_RADIUS * PREFETCH_RADIUS and loading_rooms.is_empty() and not rooms.has(entry["key"]): _ensure_room_loaded(str(entry["stage"]), int(entry["area"]))
func _room_key(stage: String, area: int) -> String: return "%s:%d" % [stage, area]
func _mesh_key(room_key: String, node_name: String) -> String: return room_key + ":" + node_name
func _portal_key(portal: Dictionary) -> String:
	var a := _room_key(str(portal["source"]["stage"]), int(portal["source"]["area"])); var b := _room_key(str(portal["destination"]["stage"]), int(portal["destination"]["area"])); return a + "|" + b if a < b else b + "|" + a
