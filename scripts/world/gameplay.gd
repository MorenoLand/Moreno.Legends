@tool
extends Node3D
signal prepared(success: bool)
signal room_changed(stage: String, area: int)
signal stage_transition_requested(route: Dictionary)
@export_file("*.json") var manifest_path := "res://assets/levels/ST04/manifest.json":
	set(value):
		manifest_path = value
		_queue_editor_preview()
@export var initial_area := 0:
	set(value):
		initial_area = value
		_queue_editor_preview()
@onready var area_picker: OptionButton = $HUD/AreaPicker
@onready var player: CharacterBody3D = $Player
@onready var game_hud: Control = $HUD/GameHUD
var areas: Array = []
var level: Node3D
var bounds := AABB()
var spawn_position := Vector3.ZERO
var loading := false
var routes: Array = []
var nearest_door: Dictionary = {}
var transition_overlay: ColorRect
var actor_manifest: Dictionary = {}
var actors: Node3D
var pickups: Node3D
var pickup_data: Dictionary = {}
var pickup_area_key := ""
var enemy_warning := false
var depth_cue_parameters: Dictionary = {}
var audio: Node
var dialogue_box: Control
var event_script: Node
var event_flags: Dictionary = {}
var actor_route: Dictionary = {}
var actor_models: Dictionary = {}
var preparation_finished := false
var playable := false
var stage_events: Dictionary = {}
var explored_stages: Dictionary = {}
var editor_preview_queued := false
var editor_preview_warning := ""
var room_stream: Variant
var streaming_rooms := false
var sky: Node
var previous_player_position := Vector3.ZERO
var has_previous_player_position := false
var room_audio_stage := ""
var room_stage_data: Dictionary = {}
var known_stage_areas: Dictionary = {}
var entry_route: Dictionary = {}
var parked_location: Dictionary = {}
func _enter_tree() -> void:
	if Engine.is_editor_hint():
		set_physics_process(false)
		return
	$Player.combat_allowed = manifest_path.get_base_dir().get_file() not in ["ST04", "ST05", "ST06", "ST07"]
func _ready() -> void:
	level = $Level
	if Engine.is_editor_hint():
		$HUD.visible = false
		set_physics_process(false)
		set_process_unhandled_input(false)
		_queue_editor_preview()
		return
	$HUD.visible = true
	player.set_physics_process(false)
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary or not manifest.has("areas"):
		push_error("Missing extracted level manifest: " + manifest_path)
		preparation_finished = true
		prepared.emit(false)
		return
	areas = manifest["areas"]
	var stage := str(manifest["stage"])
	game_hud.minimap.configure(stage)
	streaming_rooms = stage in ["ST04", "ST05", "ST06", "ST07"]
	if streaming_rooms:
		var layout_path := "res://assets/locations/room_layout.json"
		if not FileAccess.file_exists(layout_path):
			push_error("Missing Flutter room layout: " + layout_path)
			preparation_finished = true
			prepared.emit(false)
			return
		room_stream = preload("res://scripts/world/room_stream.gd").new()
		room_stream.name = "RoomStream"
		level.add_child(room_stream)
		var start_area := int(areas[initial_area]["index"]) if initial_area >= 0 and initial_area < areas.size() else -1
		if start_area < 0: preparation_finished = true; prepared.emit(false); return
		var player_shape := $Player/Collision.shape as CapsuleShape3D
		if not await room_stream.configure(layout_path, stage, start_area, player_shape.radius):
			push_error("Cannot preload Flutter rooms")
			preparation_finished = true
			prepared.emit(false)
			return
		room_stream.room_activated.connect(_stream_room_activated)
	var actor_path := manifest_path.get_base_dir().path_join("npcs.json")
	var actor_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(actor_path)) if FileAccess.file_exists(actor_path) else null
	if actor_data is Dictionary:
		actor_manifest = actor_data
		for model: Dictionary in actor_manifest.get("models", []): actor_models[int(model.get("model_index", model.get("source_model_index", -1)))] = model
	actors = Node3D.new()
	actors.name = "Actors"
	add_child(actors)
	audio = preload("res://scripts/audio/game_audio.gd").new()
	audio.name = "Audio"
	add_child(audio)
	audio.configure(player, "res://assets/audio/ST0F/manifest.json", "music" if stage == "ST0F" else "")
	dialogue_box = Control.new(); dialogue_box.name = "DialogueBox"; dialogue_box.set_script(preload("res://scripts/ui/dialogue_box.gd")); $HUD.add_child(dialogue_box)
	event_script = Node.new(); event_script.name = "EventScript"; event_script.set_script(preload("res://scripts/world/event_script.gd")); add_child(event_script); event_script.configure(dialogue_box)
	if streaming_rooms:
		room_stream.door_sound.connect(audio.play_sound)
	if streaming_rooms or stage == str(parked_location.get("stage", "")):
		sky = preload("res://scripts/world/environment_sky.gd").new()
		add_child(sky)
		sky.configure(player.camera, $WorldEnvironment.environment)
	if streaming_rooms and not parked_location.is_empty():
		if not await room_stream.set_parked_exterior(str(parked_location["stage"]), int(parked_location["area"])): push_warning("Cannot load parked Flutter exterior")
	var door_path := manifest_path.get_base_dir().path_join("doors.json")
	var door_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(door_path)) if FileAccess.file_exists(door_path) else null
	if door_data is Dictionary: routes = door_data.get("area_transitions", [])
	if streaming_rooms: room_stage_data[stage] = {"manifest": manifest, "routes": routes, "actor_manifest": actor_manifest, "actor_models": actor_models.duplicate()}
	transition_overlay = ColorRect.new()
	transition_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	transition_overlay.color = Color(0, 0, 0, 0)
	transition_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	$HUD.add_child(transition_overlay)
	var names: Dictionary = {}
	if FileAccess.file_exists("res://assets/locations/manifest.json"):
		var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/manifest.json"))
		if catalog is Dictionary:
			for location: Dictionary in catalog["locations"]:
				var location_stage := str(location["stage"]); var indices := PackedInt32Array()
				for location_area: Dictionary in location.get("areas", []):
					var index := int(location_area["index"]); indices.append(index)
					if location_stage == stage: names[index] = str(location_area["name"])
				known_stage_areas[location_stage] = indices
	for area: Dictionary in areas:
		var index := int(area["index"])
		area_picker.add_item(str(names.get(index, area.get("name", "Area %02d" % index))))
	area_picker.item_selected.connect(_select_area)
	player.health_changed.connect(game_hud.set_health)
	player.fired.connect(_on_player_fired)
	player.special_sound_requested.connect(audio.play_sound)
	playable = await _select_area(initial_area)
	preparation_finished = true
	prepared.emit(playable)
func _select_area(index: int, transition: bool = false) -> bool:
	if streaming_rooms: return await _select_stream_room(index, transition)
	if loading and not transition: return false
	loading = true
	area_picker.disabled = true
	area_picker.select(index)
	player.set_physics_process(false)
	var scene := ResourceLoader.load(manifest_path.get_base_dir().path_join(str(areas[index]["file"])), "PackedScene", ResourceLoader.CACHE_MODE_REPLACE_DEEP) as PackedScene
	if scene == null:
		push_error("Cannot load extracted area")
		loading = false
		area_picker.disabled = false
		player.set_physics_process(true)
		return false
	for projectile in get_tree().get_nodes_in_group("projectiles"):
		if is_ancestor_of(projectile): projectile.queue_free()
	remove_child(level)
	level.queue_free()
	level = scene.instantiate() as Node3D
	level.name = "Level"
	add_child(level)
	var success := await _prepare_area(transition)
	playable = success
	if not transition:
		area_picker.disabled = false
		loading = false
	return success
func _select_stream_room(index: int, transition: bool = false) -> bool:
	if loading and not transition: return false
	if index < 0 or index >= areas.size(): return false
	loading = true
	area_picker.disabled = true
	area_picker.select(index)
	player.set_physics_process(false)
	var stage := manifest_path.get_base_dir().get_file()
	var area := int(areas[index]["index"])
	if not await room_stream.select_room(stage, area):
		loading = false
		area_picker.disabled = false
		player.set_physics_process(true)
		return false
	bounds = room_stream.bounds_for(stage, area)
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not entry_route.is_empty():
		if not apply_native_arrival(entry_route): loading = false; area_picker.disabled = false; return false
	else:
		if not _find_spawn():
			push_error("Flutter room has no clear walkable spawn")
			loading = false
			area_picker.disabled = false
			player.set_physics_process(true)
			return false
		player.reset_at(spawn_position)
	game_hud.set_area(area)
	player.set_physics_process(not transition)
	game_hud.set_health(player.health, player.max_health)
	previous_player_position = player.global_position
	has_previous_player_position = true
	if not transition:
		area_picker.disabled = false
		loading = false
		_update_actor_route()
	return true
func _prepare_area(transition: bool = false) -> bool:
	preload("res://scripts/world/native_material.gd").apply(level)
	depth_cue_parameters = {}
	var lighting_path := manifest_path.get_base_dir().path_join("lighting.json")
	if FileAccess.file_exists(lighting_path):
		var lighting: Variant = JSON.parse_string(FileAccess.get_file_as_string(lighting_path))
		if lighting is Dictionary:
			for parameters: Dictionary in lighting.get("native_color_pipeline", {}).get("depth_cue", {}).get("area_parameters", []):
				if int(parameters["area"]) == int(areas[area_picker.selected]["index"]): depth_cue_parameters = parameters; break
	preload("res://scripts/world/native_material.gd").depth_cue(level, depth_cue_parameters)
	preload("res://scripts/world/native_material.gd").depth_cue(player.player_model, depth_cue_parameters)
	var first := true
	for node in level.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null: continue
		var box: AABB = mesh_node.global_transform * mesh_node.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
		var body := StaticBody3D.new()
		body.collision_layer = 1
		body.collision_mask = 0
		var shape := CollisionShape3D.new()
		shape.shape = mesh_node.mesh.create_trimesh_shape()
		body.add_child(shape)
		mesh_node.add_child(body)
		var camera_body := StaticBody3D.new()
		camera_body.collision_layer = 4
		camera_body.collision_mask = 0
		var camera_shape := CollisionShape3D.new()
		var camera_mesh := shape.shape.duplicate() as ConcavePolygonShape3D
		camera_mesh.backface_collision = true
		camera_shape.shape = camera_mesh
		camera_body.add_child(camera_shape)
		mesh_node.add_child(camera_body)
	actor_route = {}
	_load_actors()
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not entry_route.is_empty():
		if not apply_native_arrival(entry_route): return false
	else:
		if not _find_spawn():
			push_error("Extracted area has no clear walkable spawn")
			return false
		player.reset_at(spawn_position)
	game_hud.set_area(int(areas[area_picker.selected]["index"]))
	player.set_physics_process(not transition)
	game_hud.set_health(player.health, player.max_health)
	return true
func save_state(allow_loading: bool = false) -> Dictionary:
	if (loading and not allow_loading) or not playable: return {}
	var defeated: Array = []
	for id in event_flags:
		if event_flags[id]: defeated.append(int(id))
	var cells: Array = []
	for cell: Vector3i in game_hud.minimap.explored: cells.append([cell.x, cell.y, cell.z])
	var point := _room_local_position()
	var camera_rotation: Vector3 = player.camera_pivot.rotation
	var stage := manifest_path.get_base_dir().get_file()
	var events := {}
	for saved_stage in stage_events:
		var ids: Array = []
		for id in stage_events[saved_stage]:
			if stage_events[saved_stage][id]: ids.append(int(id))
		events[saved_stage] = ids
	events[stage] = defeated
	var explored := explored_stages.duplicate(true); explored[stage] = cells
	return {"stage": stage, "area": int(areas[area_picker.selected]["index"]), "player": {"position": [point.x, point.y, point.z], "yaw": player.player_model.rotation.y, "camera_rotation": [camera_rotation.x, camera_rotation.y, camera_rotation.z], "health": player.health, "max_health": player.max_health, "zenny": player.zenny}, "defeated_actors": defeated, "minimap": cells, "stage_events": events, "explored_stages": explored, "parked_location": parked_location.duplicate(true)}
func restore_state(state: Dictionary) -> bool:
	stage_events.clear()
	for stage in state.get("stage_events", {}):
		var flags := {}
		for id in state["stage_events"][stage]: flags[int(id)] = true
		stage_events[stage] = flags
	explored_stages = state.get("explored_stages", {}).duplicate(true)
	var selected := -1
	for index in range(areas.size()):
		if int(areas[index]["index"]) == int(state["area"]): selected = index
	if selected < 0: return false
	player.set_physics_process(false)
	event_flags.clear()
	for id: Variant in state["defeated_actors"]: event_flags[int(id)] = true
	if selected != area_picker.selected and not await _select_area(selected, true): return false
	var saved: Dictionary = state["player"]
	if entry_route.is_empty():
		var point: Array = saved["position"]
		var restored_position := Vector3(float(point[0]), float(point[1]), float(point[2]))
		if streaming_rooms: restored_position += room_stream.offset_for(manifest_path.get_base_dir().get_file(), int(state["area"]))
		player.reset_at(restored_position)
		player.player_model.rotation.y = float(saved["yaw"])
		var rotation: Array = saved["camera_rotation"]
		player.camera_pivot.rotation = Vector3(float(rotation[0]), float(rotation[1]), 0.0)
	player.max_health = int(saved["max_health"])
	player.health = int(saved["health"])
	player.zenny = int(saved.get("zenny", 0))
	if not entry_route.is_empty() and not apply_native_arrival(entry_route): return false
	game_hud.minimap.explored.clear()
	for cell: Array in state["minimap"]: game_hud.minimap.explored[Vector3i(int(cell[0]), int(cell[1]), int(cell[2]))] = true
	spawn_position = player.global_position
	actor_route = {}
	_load_actors()
	loading = false
	area_picker.disabled = false
	_update_actor_route()
	game_hud.set_player(player.global_position, player.player_model.rotation.y)
	game_hud.set_health(player.health, player.max_health, true)
	player.health_changed.emit(player.health, player.max_health)
	return true
func _load_actors() -> void:
	var area_key := "%s:%d" % [manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"])]
	if pickup_area_key != area_key:
		pickup_area_key = area_key; pickup_data.clear()
		if is_instance_valid(pickups):
			for pickup in pickups.get_children(): pickups.remove_child(pickup); pickup.queue_free()
	if streaming_rooms and is_instance_valid(actors): actors.position = room_stream.offset_for(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]))
	for actor in actors.get_children():
		actors.remove_child(actor)
		actor.queue_free()
	if actor_route.is_empty(): return
	for entry: Dictionary in actor_manifest.get("npc_instances", []):
		if int(entry["script_area_index"]) != int(actor_route["script_area_index"]) or event_flags.get(int(entry["instance_id"]), false): continue
		var actor := preload("res://scripts/world/stage_actor.gd").new()
		actor.name = "Actor_%03d" % int(entry["instance_id"])
		actors.add_child(actor)
		actor.configure(entry, actor_models.get(int(entry["model_index"]), {}), manifest_path.get_base_dir())
		preload("res://scripts/world/native_material.gd").depth_cue(actor.model, depth_cue_parameters if (int(entry["flags"]) & 0x20) == 0 else {})
		actor.target = player
		actor.contact_hit.connect(_actor_contact)
		actor.sound_requested.connect(audio.play_at)
		actor.died.connect(_actor_died)
		actor.drop_requested.connect(_spawn_actor_drops)
		actor.add_to_group("lock_targets")
		if actor_route.get("yaw_offset_gate", false) and int(entry["flags2"]) & 128: actor.rotation.y += PI
func _actor_contact(actor: CharacterBody3D, damage: int, flags: int) -> void:
	if not player.no_clip: player.take_hit(maxi(1, (damage * 3) >> 2), flags, player.global_position - actor.global_position)
func _actor_died(actor: CharacterBody3D) -> void:
	event_flags[int(actor.source["instance_id"])] = true
func _spawn_actor_drops(_actor: CharacterBody3D, entries: Array) -> void:
	if pickup_data.is_empty():
		var path := manifest_path.get_base_dir().path_join(str(actor_manifest["pickups"]))
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not data is Dictionary: push_error("Invalid native pickup metadata: " + path); return
		pickup_data = data
	if not is_instance_valid(pickups): pickups = Node3D.new(); pickups.name = "Pickups"; add_child(pickups)
	for entry: Dictionary in entries:
		var pickup := preload("res://scripts/world/pickup.gd").new()
		pickups.add_child(pickup); pickup.configure(entry, pickup_data, player); pickup.global_position = entry["position"]
		pickup.collected.connect(_pickup_collected)
func _pickup_collected(group: int, value: int, sound_id: int) -> void:
	if group == 0: player.zenny = clampi(player.zenny + value, 0, 9999999)
	elif group == 1: game_hud.special_charge = mini(game_hud.special_capacity, game_hud.special_charge + value); game_hud.queue_redraw()
	elif group == 2: player.health = mini(player.max_health, player.health + value); player.health_changed.emit(player.health, player.max_health)
	audio.play_sound(sound_id)
func _update_actor_route() -> void:
	if loading or areas.is_empty(): return
	var index := int(areas[area_picker.selected]["index"])
	var local_player := _room_local_position()
	var point := Vector2i(floori(-local_player.x / 2.0), floori(local_player.z / 2.0))
	for group: Dictionary in actor_manifest.get("source", {}).get("global_area_script_routes", []):
		if int(group["global_area_index"]) != index: continue
		for entry: Dictionary in group["entries"]:
			if int(entry["flags"]) & 1: continue
			var condition: Dictionary = entry["condition"]
			var minimum: Array = condition["minimum_bins"]
			var span: Array = condition["span_bins"]
			var offset := point - Vector2i(int(minimum[0]), int(minimum[1]))
			if offset.x < 0 or offset.y < 0 or offset.x >= int(span[0]) or offset.y >= int(span[1]): continue
			if actor_route.get("script_area_index", -1) != entry["script_area_index"] or actor_route.get("yaw_offset_gate", false) != entry["yaw_offset_gate"]:
				actor_route = entry
				_load_actors()
			return
func _stream_room_activated(stage: String, area: int) -> void:
	if not streaming_rooms: return
	var old_stage := manifest_path.get_base_dir().get_file()
	if old_stage != stage:
		stage_events[old_stage] = event_flags.duplicate()
		event_flags = stage_events.get(stage, {}).duplicate()
	var stage_data: Dictionary = room_stage_data.get(stage, {})
	if stage_data.is_empty(): return
	manifest_path = "res://assets/levels/%s/manifest.json" % stage
	var manifest: Dictionary = stage_data["manifest"]
	areas = manifest.get("areas", [])
	routes = stage_data["routes"]
	actor_manifest = stage_data["actor_manifest"]
	actor_models = stage_data["actor_models"].duplicate()
	area_picker.clear()
	var selected := -1
	for index in range(areas.size()):
		var area_index := int(areas[index]["index"])
		area_picker.add_item(str(areas[index].get("name", "Area %02d" % area_index)))
		if area_index == area: selected = index
	if selected < 0: return
	area_picker.select(selected)
	bounds = room_stream.bounds_for(stage, area)
	actors.position = room_stream.offset_for(stage, area)
	actor_route = {}
	game_hud.minimap.configure(stage)
	game_hud.set_area(area)
	if is_instance_valid(audio):
		if room_audio_stage != stage:
			audio.set_stage(stage, area)
			room_audio_stage = stage
		else: audio.set_area(area)
	if not loading:
		spawn_position = player.global_position
		_update_actor_route()
		game_hud.set_player(_room_local_position(), player.player_model.rotation.y)
	room_changed.emit(stage, area)
func _room_local_position() -> Vector3:
	return player.global_position - room_stream.offset_for(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"])) if streaming_rooms and not areas.is_empty() else player.global_position
func _find_spawn() -> bool:
	var world := get_world_3d().direct_space_state
	var capsule: Shape3D = $Player/Collision.shape
	var closest := INF
	var lowest := INF
	var found := false
	for x in range(1, 12):
		for z in range(1, 12):
			var point := Vector3(bounds.position.x + bounds.size.x * x / 12.0, bounds.end.y + 1.0, bounds.position.z + bounds.size.z * z / 12.0)
			var ray := PhysicsRayQueryParameters3D.create(point, Vector3(point.x, bounds.position.y - 1.0, point.z), 1)
			var hit := world.intersect_ray(ray)
			if hit.is_empty() or hit["normal"].y < 0.65: continue
			var foot: Vector3 = hit["position"] + Vector3.UP * 0.05
			var query := PhysicsShapeQueryParameters3D.new()
			query.shape = capsule
			query.transform = Transform3D(Basis.IDENTITY, foot + Vector3.UP * ($Player/Collision.shape as CapsuleShape3D).height * 0.5)
			query.collision_mask = 1
			query.margin = 0.01
			if not world.intersect_shape(query, 1).is_empty(): continue
			var score := foot.distance_squared_to(bounds.get_center())
			if (foot.y < lowest - 0.01 or (absf(foot.y - lowest) <= 0.01 and score < closest)) if not player.combat_allowed else score < closest:
				closest = score
				lowest = foot.y
				spawn_position = foot
				found = true
	return found
func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint(): return
	if event.is_action_pressed("respawn") and not loading: player.reset_at(spawn_position)
	elif event.is_action_pressed("interact") and not nearest_door.is_empty() and not loading: _use_door(nearest_door)
func _physics_process(_delta: float) -> void:
	if Engine.is_editor_hint(): return
	if streaming_rooms:
		var current := player.global_position
		if has_previous_player_position:
			var collision_shape: Shape3D = $Player/Collision.shape
			var body_height := (collision_shape as CapsuleShape3D).height if collision_shape is CapsuleShape3D else 0.8
			var body_radius := (collision_shape as CapsuleShape3D).radius if collision_shape is CapsuleShape3D else 0.2
			var crossing: Dictionary = room_stream.crossed_room(previous_player_position, current, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), body_height, body_radius)
			if not crossing.is_empty():
				var next_stage := str(crossing["stage"])
				if await _ensure_room_stage_data(next_stage): await room_stream.select_room(next_stage, int(crossing["area"]))
		room_stream.close_cleared_portals(player.global_position, player.camera.global_position, ($Player/Collision.shape as CapsuleShape3D).radius)
		previous_player_position = player.global_position
		has_previous_player_position = true
	game_hud.set_aiming(player.aiming)
	game_hud.set_player(_room_local_position(), player.player_model.rotation.y)
	_update_nearest_door()
	_update_door_prompt()
	_update_actor_route()
	if not loading and player.global_position.y < bounds.position.y - 12.0: player.reset_at(spawn_position)
	_update_enemy_warning()
func _update_enemy_warning() -> void:
	if not is_instance_valid(actors): return
	var warning := false
	var viewport_rect := Rect2(Vector2.ZERO, get_viewport().get_visible_rect().size)
	for actor in actors.get_children():
		if not actor is CharacterBody3D or (actor.collision_layer & 8) == 0: continue
		var point: Vector3 = actor.collision.global_position
		var offset := Vector2(point.x - player.global_position.x, point.z - player.global_position.z) * 256.0
		if offset.length_squared() > 0x9c3fff: continue
		if player.camera.is_position_behind(point) or not viewport_rect.has_point(player.camera.unproject_position(point)): warning = true; break
	if warning and not enemy_warning: audio.play_sound(0x88)
	enemy_warning = warning; game_hud.set_threat_alert(warning)
func _on_player_fired(_projectile: Node3D) -> void:
	game_hud.pulse_buster()
func _update_door_prompt() -> void:
	if loading or nearest_door.is_empty(): game_hud.set_interaction(Vector2.ZERO, ""); return
	var point: Vector3
	if streaming_rooms:
		var portal: Dictionary = room_stream.portal_for_route(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), nearest_door)
		if portal.is_empty():
			if not nearest_door.get("source_panel", null) is Dictionary: game_hud.set_interaction(Vector2.ZERO, ""); return
			var center: Array = nearest_door["source_panel"]["center"]; point = Vector3(float(center[0]), float(center[1]) + 0.2, float(center[2])) + room_stream.offset_for(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]))
		else:
			if room_stream.opened_portals.has(room_stream._portal_key(portal)): game_hud.set_interaction(Vector2.ZERO, ""); return
			var center: Array = portal["world_center"]; point = Vector3(float(center[0]), float(center[1]) + 0.2, float(center[2]))
	else:
		var raw: Array = nearest_door["source_transform_raw"]; point = Vector3(-float(raw[0]) / 256.0, player.global_position.y + player.body_height, float(raw[2]) / 256.0)
	if player.camera.is_position_behind(point): game_hud.set_interaction(Vector2.ZERO, ""); return
	var key := ""
	for event in InputMap.action_get_events("interact"):
		if event is InputEventKey: key = OS.get_keycode_string(event.physical_keycode if event.physical_keycode != 0 else event.keycode); break
	game_hud.set_interaction(player.camera.unproject_position(point), "Open", key)
func _update_nearest_door() -> void:
	nearest_door = {}
	if loading or areas.is_empty(): return
	var index := int(areas[area_picker.selected]["index"])
	var distance := INF
	for route: Dictionary in routes:
		if int(route["source_area"]) != index: continue
		if event_flags.get(0x710, false) or event_flags.get(int(route.get("lock_event", -1)), false): continue
		var destination_stage := str(route.get("destination_stage", manifest_path.get_base_dir().get_file())); var destination_area := int(route["destination_area"]); var destination_known := false
		if streaming_rooms and room_stream.has_room(destination_stage, destination_area): destination_known = true
		elif destination_stage == manifest_path.get_base_dir().get_file():
			for area: Dictionary in areas:
				if int(area["index"]) == destination_area: destination_known = true; break
		else: destination_known = known_stage_areas.has(destination_stage) and known_stage_areas[destination_stage].has(destination_area)
		if not destination_known: continue
		if streaming_rooms:
			var portal: Dictionary = room_stream.portal_for_route(manifest_path.get_base_dir().get_file(), index, route)
			if portal.is_empty():
				if room_stream.has_room(destination_stage, destination_area) and not room_stream.is_ladder_route(manifest_path.get_base_dir().get_file(), index, route): continue
				var raw: Array = route["source_transform_raw"]; var source_y := 0.0 if int(raw[1]) == -1 else -float(raw[1]) / 256.0; var source: Vector3 = Vector3(-float(raw[0]) / 256.0, source_y, float(raw[2]) / 256.0) + room_stream.offset_for(manifest_path.get_base_dir().get_file(), index); var contact: Vector3 = player.global_position + Vector3.UP * player.body_height * 0.65; var target: Vector3 = source + Vector3.UP * player.body_height * 0.65
				if route.get("source_panel", null) is Dictionary:
					var center: Array = route["source_panel"]["center"]; target = Vector3(float(center[0]), float(center[1]), float(center[2])) + room_stream.offset_for(manifest_path.get_base_dir().get_file(), index)
				if contact.distance_to(target) > 0.5: continue
				var expected_yaw := -float(raw[3]) * TAU / 4096.0
				if absf(wrapf(player.player_model.rotation.y - expected_yaw, -PI, PI)) > TAU * 512.0 / 4096.0 or not _clear_route_source_los(route, manifest_path.get_base_dir().get_file(), index, contact, target): continue
				var ladder_distance: float = contact.distance_squared_to(target)
				if ladder_distance < distance: distance = ladder_distance; nearest_door = route
				continue
			var center: Array = portal["world_center"]; var contact: Vector3 = player.global_position + Vector3.UP * player.body_height * 0.65; var panel_center := Vector3(float(center[0]), float(center[1]), float(center[2]))
			if contact.distance_to(panel_center) > 0.5: continue
			var size: Array = portal["shared_panel_size"]; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var radius := ($Player/Collision.shape as CapsuleShape3D).radius
			if absf(player.global_position[lateral] - float(center[lateral])) > float(size[0]) * 0.5 + radius or absf(contact.y - float(center[1])) > (float(size[1]) + player.body_height) * 0.5: continue
			var expected_yaw := -float(route["source_transform_raw"][3]) * TAU / 4096.0
			if absf(wrapf(player.player_model.rotation.y - expected_yaw, -PI, PI)) > TAU * 512.0 / 4096.0 or not _clear_stream_door_los(portal, manifest_path.get_base_dir().get_file(), index, contact, panel_center): continue
			var stream_distance: float = contact.distance_squared_to(panel_center)
			if stream_distance < distance: distance = stream_distance; nearest_door = route
			continue
		var source: Vector3
		var coordinates: Array
		coordinates = route["source_transform"]["position"]
		source = Vector3(-float(coordinates[0]), -float(coordinates[1]), float(coordinates[2]))
		var contact: Vector3 = player.global_position + Vector3.UP * player.body_height * 0.65; var target: Vector3 = source + Vector3.UP * player.body_height * 0.65
		if contact.distance_to(target) > 0.5: continue
		var expected_yaw := -float(route["source_transform"]["yaw_raw"]) * TAU / 4096.0
		if absf(wrapf(player.player_model.rotation.y - expected_yaw, -PI, PI)) > TAU * 512.0 / 4096.0 or not _clear_door_los(contact, target): continue
		var static_distance: float = contact.distance_squared_to(target)
		if static_distance < distance:
			distance = static_distance
			nearest_door = route

func _clear_door_los(origin: Vector3, target: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(origin, target, 1); query.exclude = [player.get_rid()]; var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return hit.is_empty() or (hit["position"] as Vector3).distance_to(target) <= 0.2
func _clear_route_source_los(route: Dictionary, stage: String, area: int, origin: Vector3, target: Vector3) -> bool:
	if not route.get("source_panel", null) is Dictionary: return _clear_door_los(origin, target)
	var query := PhysicsRayQueryParameters3D.create(origin, target, 1); query.exclude = [player.get_rid()]; var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty(): return true
	var node: MeshInstance3D = room_stream.mesh_nodes.get("%s:%d" % [stage, area], {}).get(str(route["source_panel"]["node"]))
	return is_instance_valid(node) and node.get_node_or_null("RoomCollision_1") == hit["collider"] and (hit["position"] as Vector3).distance_to(target) <= 0.2
func _ensure_room_stage_data(stage: String) -> bool:
	if room_stage_data.has(stage): return true
	if room_stream == null or not room_stream.has_stage(stage) or not await AssetStore.ensure_stage(stage): return false
	var stage_path := "res://assets/levels/%s/manifest.json" % stage
	if not FileAccess.file_exists(stage_path): return false
	var stage_manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(stage_path))
	if not stage_manifest is Dictionary or not stage_manifest.has("areas"): return false
	var route_path := "res://assets/levels/%s/doors.json" % stage; var route_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(route_path)) if FileAccess.file_exists(route_path) else null; var actor_path := "res://assets/levels/%s/npcs.json" % stage; var actor_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(actor_path)) if FileAccess.file_exists(actor_path) else null; var models := {}
	if actor_data is Dictionary:
		for model: Dictionary in actor_data.get("models", []): models[int(model.get("model_index", model.get("source_model_index", -1)))] = model
	room_stage_data[stage] = {"manifest": stage_manifest, "routes": route_data.get("area_transitions", []) if route_data is Dictionary else [], "actor_manifest": actor_data if actor_data is Dictionary else {}, "actor_models": models}
	return true
func _clear_stream_door_los(portal: Dictionary, stage: String, area: int, origin: Vector3, target: Vector3) -> bool:
	var query := PhysicsRayQueryParameters3D.create(origin, target, 1); query.exclude = [player.get_rid()]; var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty(): return true
	return room_stream.is_panel_collider(portal, stage, area, hit["collider"]) and (hit["position"] as Vector3).distance_to(target) <= 0.2
func _use_door(route: Dictionary) -> void:
	if loading: return
	var ladder: bool = streaming_rooms and room_stream.is_ladder_route(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), route)
	if streaming_rooms:
		var current_stage := manifest_path.get_base_dir().get_file(); var current_area := int(areas[area_picker.selected]["index"]); var portal: Dictionary = room_stream.portal_for_route(current_stage, current_area, route)
		if not portal.is_empty():
			if room_stream.opened_portals.has(room_stream._portal_key(portal)): return
			loading = true; nearest_door = {}; area_picker.disabled = true
			var destination_stage := str(route.get("destination_stage", current_stage)); var destination_area := int(route["destination_area"])
			if await room_stream._ensure_room_loaded(destination_stage, destination_area):
				player.player_model.rotation.y = -float(route["source_transform_raw"][3]) * TAU / 4096.0
				var interaction: Dictionary = player.begin_interaction("door_open")
				if not interaction.is_empty(): await get_tree().create_timer(float(interaction["open_at"]), false).timeout
				await room_stream.open_route(current_stage, current_area, route, player.global_position, player.camera.global_position)
				if not player.interaction_role.is_empty(): await player.interaction_finished
			area_picker.disabled = false; loading = false
			return
		var destination_stage := str(route.get("destination_stage", current_stage)); var destination_area := int(route["destination_area"])
		if room_stream.has_room(destination_stage, destination_area) and not room_stream.is_ladder_route(current_stage, current_area, route): return
	if loading: return
	var source_stage := manifest_path.get_base_dir().get_file(); var source_area := area_picker.selected; var source_position := player.global_position; var source_yaw: float = player.player_model.rotation.y; var source_camera_rotation: Vector3 = player.camera_pivot.rotation; var source_spawn := spawn_position; var arrived := false
	loading = true
	nearest_door = {}
	area_picker.disabled = true
	player.set_physics_process(false)
	player.player_model.rotation.y = -float(route["source_transform_raw"][3]) * TAU / 4096.0
	if ladder:
		var raw: Array = route["source_transform_raw"]
		player.global_position = Vector3(-float(raw[0]), -float(raw[1]) + 6.0, float(raw[2])) / 256.0 + room_stream.offset_for(source_stage, int(areas[source_area]["index"]))
	var interaction: Dictionary = player.begin_interaction("ladder_down" if int(route["door_mode"]) == 3 else "ladder_up") if ladder else player.begin_interaction("door_open")
	if not interaction.is_empty():
		if not ladder:
			await get_tree().create_timer(float(interaction["open_at"]), false).timeout
			audio.play_sound(0xB8)
		if not player.interaction_role.is_empty(): await player.interaction_finished
		if not ladder: audio.play_sound(0xB9)
	await create_tween().tween_property(transition_overlay, "color:a", 1.0, 0.12).finished
	var destination_stage := str(route.get("destination_stage", manifest_path.get_base_dir().get_file()))
	if streaming_rooms != (destination_stage in ["ST04", "ST05", "ST06", "ST07"]):
		var request := route.duplicate(true); request["source_stage"] = source_stage
		stage_transition_requested.emit(request)
		return
	if destination_stage != manifest_path.get_base_dir().get_file() and streaming_rooms and not await _ensure_room_stage_data(destination_stage):
		await create_tween().tween_property(transition_overlay, "color:a", 0.0, 0.12).finished
		area_picker.disabled = false
		loading = false
		player.set_physics_process(true)
		return
	if destination_stage != manifest_path.get_base_dir().get_file() and not await _change_stage(destination_stage):
		await create_tween().tween_property(transition_overlay, "color:a", 0.0, 0.12).finished
		area_picker.disabled = false
		loading = false
		player.set_physics_process(true)
		return
	var destination := int(route["destination_area"])
	var selected := -1
	for index in range(areas.size()):
		if int(areas[index]["index"]) == destination: selected = index
	if selected >= 0:
		if await _select_area(selected, true):
			var destination_offset: Vector3 = room_stream.offset_for(destination_stage, destination) if streaming_rooms else Vector3.ZERO; var point := _door_arrival(route["destination_transform"], destination_offset)
			if point.is_finite():
				player.reset_at(point)
				var yaw := -float(int(route["destination_transform"]["yaw_raw"])) * TAU / 4096.0
				player.player_model.rotation.y = yaw
				player.camera_pivot.rotation.y = yaw
				spawn_position = point
				previous_player_position = point
				has_previous_player_position = true
				arrived = true
	else: push_error("Missing destination area for native door route")
	if not arrived:
		if manifest_path.get_base_dir().get_file() != source_stage: await _change_stage(source_stage)
		await _select_area(source_area, true)
		player.reset_at(source_position)
		player.player_model.rotation.y = source_yaw
		player.camera_pivot.rotation = source_camera_rotation
		spawn_position = source_spawn
		previous_player_position = source_position
		has_previous_player_position = true
	await create_tween().tween_property(transition_overlay, "color:a", 0.0, 0.12).finished
	area_picker.disabled = false
	loading = false
	player.set_physics_process(true)
func _change_stage(stage: String) -> bool:
	if not await AssetStore.ensure_stage(stage): return false
	var path := "res://assets/levels/%s/manifest.json" % stage
	if not FileAccess.file_exists(path): return false
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not manifest is Dictionary or not manifest.has("areas"): return false
	stage_events[manifest_path.get_base_dir().get_file()] = event_flags.duplicate()
	event_flags = stage_events.get(stage, {}).duplicate()
	manifest_path = path
	areas = manifest["areas"]
	area_picker.clear()
	for area: Dictionary in areas: area_picker.add_item(str(area.get("name", "Area %02d" % int(area["index"]))))
	var door_path := path.get_base_dir().path_join("doors.json")
	var door_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(door_path)) if FileAccess.file_exists(door_path) else null
	routes = door_data.get("area_transitions", []) if door_data is Dictionary else []
	var actor_path := path.get_base_dir().path_join("npcs.json")
	var actor_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(actor_path)) if FileAccess.file_exists(actor_path) else null
	actor_manifest = actor_data if actor_data is Dictionary else {}
	actor_models.clear()
	for model: Dictionary in actor_manifest.get("models", []): actor_models[int(model.get("model_index", model.get("source_model_index", -1)))] = model
	game_hud.minimap.configure(stage)
	return true
func apply_native_arrival(route: Dictionary) -> bool:
	if areas.is_empty() or area_picker.selected < 0 or area_picker.selected >= areas.size(): return false
	var stage := manifest_path.get_base_dir().get_file(); var area := int(areas[area_picker.selected]["index"])
	if str(route.get("destination_stage", stage)) != stage or int(route.get("destination_area", -1)) != area or not route.get("destination_transform", null) is Dictionary: return false
	var offset: Vector3 = room_stream.offset_for(stage, area) if streaming_rooms else Vector3.ZERO; var point := _door_arrival(route["destination_transform"], offset)
	if not point.is_finite(): return false
	var yaw := -float(int(route["destination_transform"]["yaw_raw"])) * TAU / 4096.0
	player.reset_at(point); player.player_model.rotation.y = yaw; player.camera_pivot.rotation.y = yaw; spawn_position = point; previous_player_position = point; has_previous_player_position = true
	return true
func cancel_stage_transition() -> void:
	loading = false; area_picker.disabled = false; nearest_door = {}; player.set_physics_process(true)
	if is_instance_valid(transition_overlay): transition_overlay.color.a = 0.0
func _door_arrival(transform: Dictionary, world_offset: Vector3 = Vector3.ZERO) -> Vector3:
	var coordinates: Array = transform["position"]
	var point := Vector3(-float(coordinates[0]), -float(coordinates[1]) + 0.05, float(coordinates[2])) + world_offset
	if transform.get("floor_height", false):
		var ray := PhysicsRayQueryParameters3D.create(Vector3(point.x, spawn_position.y + 1.0, point.z), Vector3(point.x, bounds.position.y - 1.0, point.z), 1)
		var hit := get_world_3d().direct_space_state.intersect_ray(ray)
		if hit.is_empty(): return Vector3.INF
		point.y = float(hit["position"].y) + 0.05
	var capsule := $Player/Collision.shape as CapsuleShape3D; var collision := $Player/Collision as CollisionShape3D; var yaw := -float(int(transform.get("yaw_raw", 0))) * TAU / 4096.0; var forward := Vector3(-sin(yaw), 0.0, -cos(yaw)); var step := maxf(capsule.radius * 0.25, 0.01); var query := PhysicsShapeQueryParameters3D.new(); query.shape = capsule; query.collision_mask = 1; query.exclude = [player.get_rid()]; query.margin = 0.01
	var native_floor_ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * capsule.radius, point - Vector3.UP * capsule.height, 1); native_floor_ray.exclude = [player.get_rid()]; var native_floor := get_world_3d().direct_space_state.intersect_ray(native_floor_ray)
	if not native_floor.is_empty() and (native_floor["normal"] as Vector3).y >= 0.65:
		var native_point := Vector3(point.x, float(native_floor["position"].y) + 0.05, point.z); query.transform = Transform3D(player.global_basis, native_point) * collision.transform
		if get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty(): return native_point
	var ray_from := point + Vector3.UP * capsule.height * 0.5 - forward * capsule.height; var ray_to := point + Vector3.UP * capsule.height * 0.5 + forward * capsule.height; var clearance := 0.0; var found_surface := false
	for hit_index in 16:
		var panel_ray := PhysicsRayQueryParameters3D.create(ray_from, ray_to, 1); panel_ray.exclude = [player.get_rid()]; panel_ray.hit_back_faces = true; var panel_hit := get_world_3d().direct_space_state.intersect_ray(panel_ray)
		if panel_hit.is_empty(): break
		var hit_position: Vector3 = panel_hit["position"]; var hit_distance := (hit_position - point).dot(forward)
		if hit_distance > -capsule.radius - 0.02 and hit_distance <= capsule.height: clearance = maxf(clearance, hit_distance + capsule.radius + 0.02); found_surface = true
		ray_from = hit_position + forward * 0.01
	if not found_surface:
		var lateral := 2 if absf(forward.x) > 0.5 else 0; var probe_y := point.y + capsule.height * 0.5
		var arrival_mesh_nodes: Array = []
		if streaming_rooms:
			var room_key := "%s:%d" % [manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"])]
			for mesh_node: MeshInstance3D in room_stream.mesh_nodes.get(room_key, {}).values(): arrival_mesh_nodes.append(mesh_node)
		else: arrival_mesh_nodes = level.find_children("*", "MeshInstance3D", true, false)
		for item in arrival_mesh_nodes:
			var mesh_node := item as MeshInstance3D
			if mesh_node.mesh == null: continue
			for surface in mesh_node.mesh.get_surface_count():
				if mesh_node.mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES: continue
				var arrays: Array = mesh_node.mesh.surface_get_arrays(surface); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]; var count := indices.size() if not indices.is_empty() else vertices.size()
				for triangle in range(0, count, 3):
					var ia := indices[triangle] if not indices.is_empty() else triangle; var ib := indices[triangle + 1] if not indices.is_empty() else triangle + 1; var ic := indices[triangle + 2] if not indices.is_empty() else triangle + 2; var a := mesh_node.to_global(vertices[ia]); var b := mesh_node.to_global(vertices[ib]); var c := mesh_node.to_global(vertices[ic]); var normal := (b - a).cross(c - a).normalized()
					if absf(normal.dot(forward)) < 0.8: continue
					var min_y := minf(a.y, minf(b.y, c.y)); var max_y := maxf(a.y, maxf(b.y, c.y)); var min_lateral := minf(a[lateral], minf(b[lateral], c[lateral])); var max_lateral := maxf(a[lateral], maxf(b[lateral], c[lateral]))
					if probe_y < min_y - 0.05 or probe_y > max_y + 0.05 or point[lateral] + capsule.radius < min_lateral or point[lateral] - capsule.radius > max_lateral: continue
					var plane_distance := ((a + b + c) / 3.0 - point).dot(forward)
					if plane_distance > -capsule.radius - 0.02 and plane_distance <= capsule.height: clearance = maxf(clearance, plane_distance + capsule.radius + 0.02); found_surface = true
	if clearance > 0.0: point += forward * clearance
	for sample in range(ceili(2.0 / step) + 1):
		var candidate := point + forward * (float(sample) * step); var floor_ray := PhysicsRayQueryParameters3D.create(candidate + Vector3.UP * capsule.radius, candidate - Vector3.UP * capsule.height, 1); floor_ray.exclude = [player.get_rid()]; var floor_hit := get_world_3d().direct_space_state.intersect_ray(floor_ray)
		if floor_hit.is_empty() or (floor_hit["normal"] as Vector3).y < 0.65: continue
		candidate.y = (floor_hit["position"] as Vector3).y + 0.05
		query.transform = Transform3D(player.global_basis, candidate) * collision.transform
		if get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty(): return candidate
	push_error("Native door arrival has no clear capsule position")
	return Vector3.INF
func _queue_editor_preview() -> void:
	if not Engine.is_editor_hint() or not is_inside_tree() or editor_preview_queued: return
	editor_preview_queued = true
	_refresh_editor_preview.call_deferred()
func _refresh_editor_preview() -> void:
	editor_preview_queued = false
	if not Engine.is_editor_hint() or not is_inside_tree(): return
	var container := get_node_or_null("Level") as Node3D
	if container == null: return
	var previous := container.get_node_or_null("NativeAreaPreview")
	if previous != null and previous.owner == null:
		container.remove_child(previous)
		previous.queue_free()
	editor_preview_warning = ""
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) if FileAccess.file_exists(manifest_path) else null
	if not manifest is Dictionary or not manifest.get("areas", []) is Array:
		editor_preview_warning = "Import the disc assets and select a level manifest."
	else:
		var entries: Array = manifest.get("areas", [])
		if initial_area < 0 or initial_area >= entries.size():
			editor_preview_warning = "Initial Area is outside this level's exported rooms."
		else:
			var path := manifest_path.get_base_dir().path_join(str(entries[initial_area]["file"]))
			var packed := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_REPLACE_DEEP) as PackedScene if ResourceLoader.exists(path) else null
			if packed == null:
				editor_preview_warning = "The selected room has not been imported."
			else:
				var preview := packed.instantiate() as Node3D
				preview.name = "NativeAreaPreview"
				container.add_child(preview)
				preload("res://scripts/world/native_material.gd").apply(preview)
	update_configuration_warnings()
func _get_configuration_warnings() -> PackedStringArray:
	return PackedStringArray([editor_preview_warning]) if not editor_preview_warning.is_empty() else PackedStringArray()
