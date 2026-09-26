@tool
extends Node3D
signal prepared(success: bool)
signal room_changed(stage: String, area: int)
signal stage_transition_requested(route: Dictionary)
signal location_requested(stage: String, area: int)
signal native_scene_failed(reason: String)
var room_transfer_pending := false
@export_file("*.json") var manifest_path := "res://assets/levels/ST04/manifest.json":
	set(value):
		manifest_path = value
		_queue_editor_preview()
@export var initial_area := 0:
	set(value):
		initial_area = value
		_queue_editor_preview()
@onready var area_picker: OptionButton = $HUD/AreaPicker
var stage_picker: OptionButton
@onready var player: CharacterBody3D = $Player
@onready var game_hud: Control = $HUD/GameHUD
var areas: Array = []
var level: Node3D
var bounds := AABB()
var spawn_position := Vector3.ZERO
var loading := false
var routes: Array = []
var automatic_gate_diagnostics: Dictionary = {}
var nearest_door: Dictionary = {}
var nearest_map_interaction: Dictionary = {}
var map_interaction_cache: Dictionary = {}
var scene_trigger_cache: Dictionary = {}
var nearest_npc: Variant
var transition_overlay: Node
var actor_manifest: Dictionary = {}
var actors: Node3D
var pickups: Node3D
var pickup_data: Dictionary = {}
var pickup_area_key := ""
var enemy_warning := false
var depth_cue_parameters: Dictionary = {}
var native_floor_collision: Dictionary = {}
var audio: Node
var dialogue_box: Control
var event_script: Node
var native_scenes: Node
var event_flags: Dictionary = {}
var actor_route: Dictionary = {}
var actor_models: Dictionary = {}
var preparation_finished := false
var playable := false
var play_time_seconds := 0.0
var stage_events: Dictionary = {}
var explored_stages: Dictionary = {}
var editor_preview_queued := false
var editor_preview_warning := ""
var room_stream: Variant
var streaming_rooms := false
var sky: Node
var weather: Control
var zone_notice: Label
var roof_status: Label
var roof_check_elapsed := 0.0
var announced_zone := ""
var previous_player_position := Vector3.ZERO
var has_previous_player_position := false
var room_audio_stage := ""
var room_stage_data: Dictionary = {}
var known_stage_areas: Dictionary = {}
var entry_route: Dictionary = {}
var initial_player_state: Dictionary = {}
var parked_location: Dictionary = {}
var audio_preparing := false
var native_context: Dictionary = {"native_save_byte14": 0, "native_save_byte16": 0, "native_save_word40": 0, "native_save_byte44": 1, "event_flags": {}}
func _enter_tree() -> void:
	if Engine.is_editor_hint():
		set_physics_process(false)
		return
	$Player.combat_allowed = manifest_path.get_base_dir().get_file() not in ["ST04", "ST05", "ST06", "ST07"]
	var source: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	var weapon_policy: Variant = source.get("native_combat_policy", null) if source is Dictionary else null
	$Player.buster_allowed = bool(weapon_policy.get("buster_allowed", true)) if weapon_policy is Dictionary else true
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
	native_floor_collision = manifest.get("native_floor_collision", {})
	var stage := str(manifest["stage"])
	game_hud.minimap.configure(stage)
	var native_area := int(areas[initial_area]["index"]) if initial_area >= 0 and initial_area < areas.size() else -1
	audio = preload("res://scripts/audio/game_audio.gd").new()
	audio.name = "Audio"
	add_child(audio)
	audio.set_preparing(audio_preparing)
	audio.configure(player, "res://assets/audio/ST0F/manifest.json", "music" if stage == "ST0F" else "")
	dialogue_box = Control.new(); dialogue_box.name = "DialogueBox"; dialogue_box.set_script(preload("res://scripts/ui/dialogue_box.gd")); $HUD.add_child(dialogue_box)
	dialogue_box.typing_sound_requested.connect(audio.play_sound)
	event_script = Node.new(); event_script.name = "EventScript"; event_script.set_script(preload("res://scripts/world/event_script.gd")); add_child(event_script); event_script.configure(dialogue_box, "res://assets/dialogue/manifest.json", native_context)
	event_script.native_context_changed.connect(_dialogue_context_changed)
	event_script.native_command_requested.connect(_native_dialogue_command)
	native_scenes = preload("res://scripts/cinematics/native_scene_dispatcher.gd").new(); add_child(native_scenes); native_scenes.configure(self)
	var layout_path := preload("res://scripts/world/room_stream.gd").layout_path_for(stage, native_area)
	streaming_rooms = not layout_path.is_empty()
	if streaming_rooms:
		if not FileAccess.file_exists(layout_path):
			push_error("Missing Flutter room layout: " + layout_path)
			preparation_finished = true
			prepared.emit(false)
			return
		room_stream = preload("res://scripts/world/room_stream.gd").new()
		room_stream.name = "RoomStream"
		room_stream.native_context = native_context
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
		room_stream.native_context_changed.connect(_native_context_changed)
	var actor_path := manifest_path.get_base_dir().path_join("npcs.json")
	var actor_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(actor_path)) if FileAccess.file_exists(actor_path) else null
	if actor_data is Dictionary:
		actor_manifest = actor_data
		for model: Dictionary in actor_manifest.get("models", []): actor_models[int(model.get("model_index", model.get("source_model_index", -1)))] = model
	actors = Node3D.new()
	actors.name = "Actors"
	add_child(actors)
	if streaming_rooms:
		room_stream.door_sound.connect(audio.play_sound)
	sky = preload("res://scripts/world/environment_sky.gd").new()
	add_child(sky)
	sky.configure(player.camera, $WorldEnvironment.environment)
	weather = preload("res://scripts/world/native_weather.gd").new()
	$HUD.add_child(weather)
	$HUD.move_child(weather, 0)
	zone_notice = preload("res://scripts/ui/zone_notice.gd").new()
	$HUD.add_child(zone_notice)
	roof_status = Label.new(); roof_status.name = "RoofStatus"; roof_status.visible = false; roof_status.text = "roof: false"; roof_status.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE); roof_status.offset_top = 16; roof_status.offset_bottom = 44; roof_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; roof_status.mouse_filter = Control.MOUSE_FILTER_IGNORE; roof_status.add_theme_font_size_override("font_size", 20); roof_status.add_theme_color_override("font_shadow_color", Color.BLACK); roof_status.add_theme_constant_override("shadow_offset_x", 1); roof_status.add_theme_constant_override("shadow_offset_y", 1); $HUD.add_child(roof_status)
	if streaming_rooms and room_stream.can_show_parked_exterior() and not parked_location.is_empty():
		if not await room_stream.set_parked_exterior(str(parked_location["stage"]), int(parked_location["area"])): push_warning("Cannot load parked Flutter exterior")
	var door_path := manifest_path.get_base_dir().path_join("doors.json")
	var door_data: Variant = JSON.parse_string(FileAccess.get_file_as_string(door_path)) if FileAccess.file_exists(door_path) else null
	if door_data is Dictionary: routes = door_data.get("area_transitions", [])
	if streaming_rooms: room_stage_data[stage] = {"manifest": manifest, "routes": routes, "actor_manifest": actor_manifest, "actor_models": actor_models.duplicate()}
	transition_overlay = preload("res://scripts/ui/native_fade.gd").new()
	$HUD.add_child(transition_overlay)
	transition_overlay.configure()
	var names: Dictionary = {}
	stage_picker = OptionButton.new(); stage_picker.name = "StagePicker"; stage_picker.anchor_left = 1.0; stage_picker.anchor_right = 1.0
	stage_picker.offset_left = -403.0; stage_picker.offset_right = -173.0; stage_picker.offset_top = 16.0; stage_picker.offset_bottom = 50.0; $HUD.add_child(stage_picker)
	if FileAccess.file_exists("res://assets/locations/manifest.json"):
		var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/manifest.json"))
		if catalog is Dictionary:
			for location: Dictionary in catalog["locations"]:
				var location_stage := str(location["stage"]); var indices := PackedInt32Array()
				if not location.get("areas", []).is_empty():
					stage_picker.add_item(str(location["name"])); stage_picker.set_item_metadata(stage_picker.item_count - 1, {"stage": location_stage, "area": int(location["areas"][0]["index"])})
					if location_stage == stage: stage_picker.select(stage_picker.item_count - 1)
				for location_area: Dictionary in location.get("areas", []):
					var index := int(location_area["index"]); indices.append(index)
					if location_stage == stage: names[index] = str(location_area["name"])
				known_stage_areas[location_stage] = indices
	for area: Dictionary in areas:
		var index := int(area["index"])
		area_picker.add_item(str(names.get(index, area.get("name", "Area %02d" % index))))
	area_picker.item_selected.connect(_select_area)
	stage_picker.item_selected.connect(_pick_stage)
	for picker in [stage_picker, area_picker]:
		picker.fit_to_longest_item = false
		picker.clip_text = true
		picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		picker.get_popup().about_to_popup.connect(_limit_location_popup.bind(picker))
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
	_set_current_area(area)
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
	level.set_meta("native_map_face_flags", bool(areas[area_picker.selected].get("native_map_face_flags_in_alpha", false)))
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
	if is_instance_valid(sky): sky.set_flying(not (bool(depth_cue_parameters.get("enabled", false)) and depth_cue_parameters.get("far_rgb", [0, 0, 0]) == [0, 0, 0]))
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
	preload("res://scripts/world/native_floor.gd").apply(level, native_floor_collision, int(areas[area_picker.selected]["index"]), native_context)
	preload("res://scripts/world/area_roof.gd").apply(level, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]))
	var native_props: Array[Node3D] = await preload("res://scripts/world/native_props.gd").load_into(level, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), native_context)
	for prop: Node3D in native_props:
		if is_instance_valid(prop): preload("res://scripts/world/native_material.gd").depth_cue(prop, depth_cue_parameters)
	actor_route = {}
	_load_actors()
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not entry_route.is_empty():
		if not apply_native_arrival(entry_route): return false
	else:
		if initial_player_state.has("position"):
			var saved_point: Array = initial_player_state["position"]; spawn_position = Vector3(float(saved_point[0]), float(saved_point[1]), float(saved_point[2])); player.reset_at(spawn_position); player.player_model.rotation.y = float(initial_player_state.get("yaw", 0.0)); initial_player_state.clear()
		else:
			if not _find_spawn():
				push_error("Extracted area has no clear walkable spawn")
				return false
			player.reset_at(spawn_position)
	_update_native_player_pose()
	var initialized_props: Array[Node3D] = await preload("res://scripts/world/native_props.gd").initialize_into(level, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), native_context)
	for prop: Node3D in initialized_props:
		if is_instance_valid(prop): preload("res://scripts/world/native_material.gd").depth_cue(prop, depth_cue_parameters)
	_set_current_area(int(areas[area_picker.selected]["index"]))
	_sync_stage_picker()
	if is_instance_valid(audio):
		var audio_stage := manifest_path.get_base_dir().get_file(); var audio_area := int(areas[area_picker.selected]["index"])
		if await audio.set_stage(audio_stage, audio_area, native_context): _drain_native_actor_audio(audio_stage, audio_area)
	_run_native_scene_requests.call_deferred(level, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]))
	player.set_physics_process(not transition)
	game_hud.set_health(player.health, player.max_health)
	return true
func _run_native_scene_requests(parent: Node3D, stage: String, area: int) -> void:
	if preload("res://scripts/world/native_props.gd").pending_scene_requests(parent).is_empty(): return
	while is_inside_tree() and is_instance_valid(parent) and (not preparation_finished or not is_visible_in_tree() or loading or not player.is_physics_processing()): await get_tree().process_frame
	if not is_inside_tree() or not is_instance_valid(parent) or native_scenes.active or stage != manifest_path.get_base_dir().get_file() or areas.is_empty() or area != int(areas[area_picker.selected]["index"]): return
	if parent != (room_stream.room_root(stage, area) if streaming_rooms else level): return
	loading = true; area_picker.disabled = true; player.set_physics_process(false)
	var success: bool = await native_scenes.run_pending(parent, stage, area)
	if not is_inside_tree() or not is_instance_valid(parent): return
	if not success:
		var reason := str(native_scenes.last_error); push_error(reason); native_scene_failed.emit(reason); loading = false; area_picker.disabled = false; player.set_physics_process(true); return
	if native_scenes.transition_requested: return
	_update_native_player_pose(); loading = false; area_picker.disabled = false; player.set_physics_process(true)
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
	return {"stage": stage, "area": int(areas[area_picker.selected]["index"]), "location_name": get_location_names()["main"], "player": {"position": [point.x, point.y, point.z], "yaw": player.player_model.rotation.y, "camera_rotation": [camera_rotation.x, camera_rotation.y, camera_rotation.z], "health": player.health, "max_health": player.max_health, "zenny": player.zenny, "inventory": player.inventory.duplicate(true), "equipment": player.equipment.duplicate(true), "equipped_special": player.equipped_special}, "play_time_seconds": play_time_seconds, "defeated_actors": defeated, "minimap": cells, "stage_events": events, "explored_stages": explored, "parked_location": parked_location.duplicate(true), "native_context": native_context.duplicate(true)}
func get_location_names() -> Dictionary:
	var stage := manifest_path.get_base_dir().get_file()
	var main_name := stage
	if stage_picker != null:
		for index in range(stage_picker.item_count):
			if str(stage_picker.get_item_metadata(index)["stage"]) == stage: main_name = stage_picker.get_item_text(index); break
	return {"main": main_name, "area": area_picker.get_item_text(area_picker.selected) if area_picker.selected >= 0 else ""}
func set_minimap_visible(value: bool) -> void:
	game_hud.minimap.set_display_enabled(value)
func _update_native_player_pose() -> void:
	var point := _room_local_position()
	native_context["native_player_pose_raw"] = [roundi(-point.x * 256.0), roundi(-point.y * 256.0), roundi(point.z * 256.0), roundi(-player.player_model.rotation.y * 4096.0 / TAU) & 4095]
func _set_current_area(area: int) -> void:
	_update_native_player_pose()
	if is_instance_valid(sky): sky.set_fog(sky.flying and (not streaming_rooms or room_stream.is_exterior_room(manifest_path.get_base_dir().get_file(), area)))
	game_hud.set_area(area)
	if is_instance_valid(weather): weather.configure(manifest_path.get_base_dir().get_file(), area, player.camera, native_context)
func _limit_location_popup(picker: OptionButton) -> void:
	picker.get_popup().max_size = Vector2i(roundi(picker.size.x * picker.get_global_transform_with_canvas().get_scale().x), roundi(get_viewport().get_visible_rect().size.y * 0.5))
	for index in range(picker.item_count): picker.get_popup().set_item_tooltip(index, picker.get_item_text(index))
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
	player.inventory = saved.get("inventory", player.inventory).duplicate(true)
	player.equipment = saved.get("equipment", player.equipment).duplicate(true)
	player.equipped_special = int(saved.get("equipped_special", 0))
	play_time_seconds = float(state.get("play_time_seconds", 0.0))
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
func set_location_picker_visible(value: bool) -> void:
	area_picker.visible = value
	if stage_picker != null: stage_picker.visible = value
func _pick_stage(index: int) -> void:
	if loading or index < 0 or index >= stage_picker.item_count: return
	var location: Dictionary = stage_picker.get_item_metadata(index)
	if str(location["stage"]) != manifest_path.get_base_dir().get_file(): location_requested.emit(str(location["stage"]), int(location["area"]))
func _sync_stage_picker() -> void:
	if stage_picker == null: return
	for index in range(stage_picker.item_count):
		if str(stage_picker.get_item_metadata(index)["stage"]) == manifest_path.get_base_dir().get_file(): stage_picker.select(index); return
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
	for entry: Dictionary in actor_manifest.get("npc_instances", []):
		if int(entry.get("actor_class", -1)) == 0:
			if int(areas[area_picker.selected]["index"]) not in entry.get("global_area_indices", [entry.get("area_index", -1)]): continue
			var npc := preload("res://scripts/world/friendly_actor.gd").new()
			npc.name = "NPC_%06X" % int(entry["file_offset"])
			actors.add_child(npc)
			if not npc.configure(entry, actor_models.get(int(entry["model_index"]), {}), manifest_path.get_base_dir()): npc.queue_free(); continue
			preload("res://scripts/world/native_material.gd").depth_cue(npc.model, depth_cue_parameters if (int(entry["flags"]) & 0x20) == 0 else {})
			continue
		if actor_route.is_empty() or int(entry["script_area_index"]) != int(actor_route["script_area_index"]) or event_flags.get(int(entry["instance_id"]), false): continue
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
func _dialogue_context_changed(stage: String, context: Dictionary) -> void:
	native_context = context
	if streaming_rooms: room_stream.native_context = native_context
	if not areas.is_empty(): _native_context_changed(stage, int(areas[area_picker.selected]["index"]))
func bind_native_kickable_prop(receiver: Node) -> void:
	var actor := receiver.get("actor") as Node3D; var stage := str(actor.get_meta("native_stage", "")); receiver.sound_requested.connect(audio.play_at); receiver.stat_delta_requested.connect(event_script.apply_native_stat_delta.bind(stage)); receiver.message_requested.connect(_native_prop_message.bind(stage))
func _drain_native_actor_audio(stage: String, area: int) -> void:
	if not is_instance_valid(audio) or stage != manifest_path.get_base_dir().get_file() or areas.is_empty() or area != int(areas[area_picker.selected]["index"]): return
	var parent: Node3D = room_stream.room_root(stage, area) if streaming_rooms else level
	if is_instance_valid(parent): preload("res://scripts/world/native_props.gd").drain_audio_requests(parent, audio, stage, area)
func _native_prop_message(index: int, window: int, stage: String) -> void:
	while is_inside_tree() and (loading or bool(dialogue_box.get("active"))): await get_tree().process_frame
	if not is_inside_tree() or manifest_path.get_base_dir().get_file() != stage: return
	native_context["native_wallet"] = player.zenny
	await event_script.play_bound_message(stage, "0x8010C000", index, "0x80048474", null, window)
func _native_dialogue_command(_stage: String, _index: int, _opcode: int, _arguments: Array, source: Dictionary, _actor: Node3D) -> void:
	if str(source.get("effect", "")) == "native_sound_cue": audio.play_sound(int(source["sound_id"]))
	var mutation: Dictionary = source.get("native_context_mutation", {})
	if mutation.has("native_wallet"): player.zenny = int(mutation["native_wallet"])
func _update_nearest_map_interaction() -> void:
	nearest_map_interaction = {}
	if loading or areas.is_empty() or player.health <= 0 or not player.special_action.is_empty() or not player.hurt_phase.is_empty() or not player.interaction_role.is_empty(): return
	var stage := manifest_path.get_base_dir().get_file(); var area := int(areas[area_picker.selected]["index"])
	if not map_interaction_cache.has(stage):
		var path := "res://assets/levels/%s/doors.json" % stage; var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null; map_interaction_cache[stage] = value.get("map_interactions", []) if value is Dictionary else []
	for interaction: Dictionary in map_interaction_cache[stage]:
		if int(interaction["source_area"]) != area: continue
		if preload("res://scripts/world/native_transition.gd").manual_contact(interaction, _room_local_position(), player.player_model.rotation.y): nearest_map_interaction = interaction; return
func _use_map_interaction(interaction: Dictionary) -> void:
	if loading: return
	var stage := manifest_path.get_base_dir().get_file(); loading = true; area_picker.disabled = true; player.velocity = Vector3.ZERO; player.set_physics_process(false)
	var success: bool = await event_script.play_bound_message(stage, str(interaction["source_bank_pointer"]), int(interaction["runtime_index"]), str(interaction["source_function"]), null, int(interaction.get("window", 0)))
	if not is_inside_tree(): return
	if not success: push_error("Native map interaction did not execute in %s:%d" % [stage, int(interaction["runtime_index"])])
	loading = false; area_picker.disabled = false; player.set_physics_process(true)
func _native_context_changed(stage: String, area: int) -> void:
	if stage == manifest_path.get_base_dir().get_file() and not areas.is_empty() and area == int(areas[area_picker.selected]["index"]) and is_instance_valid(audio):
		if await audio.set_stage(stage, area, native_context): _drain_native_actor_audio(stage, area)
	if stage != manifest_path.get_base_dir().get_file() or areas.is_empty(): return
	if area != int(areas[area_picker.selected]["index"]): return
	var scene_parent: Node3D = room_stream.room_root(stage, area) if streaming_rooms else level
	if not is_instance_valid(scene_parent): return
	if not scene_trigger_cache.has(stage):
		var path := "res://assets/levels/%s/scene_triggers.json" % stage; var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null; scene_trigger_cache[stage] = value.get("triggers", []) if value is Dictionary else []
	for trigger: Dictionary in scene_trigger_cache[stage]:
		var flags: Dictionary = native_context.get("event_flags", {}); var id := int(trigger["event_flag"])
		if not bool(flags.get(id, flags.get(str(id), false))): continue
		flags[id] = false; flags[str(id)] = false; native_context["event_flags"] = flags
		var pending: Array = preload("res://scripts/world/native_props.gd").pending_scene_requests(scene_parent); pending.append({"key": "%s:%d:event%d:%d" % [stage, area, id, Time.get_ticks_usec()], "stage": stage, "area": area, "source_function": str(trigger["source_function"]), "argument": int(trigger["scene_id"]), "status": "pending_native_scene"}); scene_parent.set_meta("native_pending_scene_requests", pending); _run_native_scene_requests.call_deferred(scene_parent, stage, area)
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
	_set_current_area(area)
	if is_instance_valid(audio):
		_sync_stage_picker()
		if room_audio_stage != stage:
			if await audio.set_stage(stage, area, native_context): room_audio_stage = stage; _drain_native_actor_audio(stage, area)
		else: audio.set_area(area); _drain_native_actor_audio(stage, area)
	if not loading:
		spawn_position = player.global_position
		_update_actor_route()
		game_hud.set_player(_room_local_position(), player.player_model.rotation.y)
	var scene_parent: Node3D = room_stream.room_root(stage, area)
	if is_instance_valid(scene_parent): _run_native_scene_requests.call_deferred(scene_parent, stage, area)
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
	if Engine.is_editor_hint() or not preparation_finished or not playable: return
	if event.is_action_pressed("respawn") and not loading: player.reset_at(spawn_position)
	elif event.is_action_pressed("interact") and not loading:
		_update_nearest_map_interaction(); _update_nearest_npc(); _update_nearest_door()
		if is_instance_valid(player.carried_actor):
			if player.use_special(): get_viewport().set_input_as_handled()
		elif not nearest_map_interaction.is_empty(): get_viewport().set_input_as_handled(); _use_map_interaction(nearest_map_interaction)
		elif is_instance_valid(nearest_npc): get_viewport().set_input_as_handled(); _talk_to_npc(nearest_npc)
		elif not nearest_door.is_empty(): get_viewport().set_input_as_handled(); _use_door(nearest_door)
		elif Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and player.use_special(): get_viewport().set_input_as_handled()
func _physics_process(_delta: float) -> void:
	if Engine.is_editor_hint() or not preparation_finished or not playable: return
	if room_transfer_pending: return
	if playable and not loading and is_instance_valid(roof_status) and roof_status.visible:
		roof_check_elapsed += _delta
		if roof_check_elapsed >= 0.1:
			roof_check_elapsed = 0.0
			var roof_origin: Vector3 = player.global_position + Vector3.UP * (player.body_height + 0.01)
			var roof_target := Vector3(roof_origin.x, maxf(roof_origin.y + 0.01, bounds.end.y + 1.0), roof_origin.z)
			var roof_query := PhysicsRayQueryParameters3D.create(roof_origin, roof_target, 5); roof_query.exclude = [player.get_rid()]; roof_query.hit_back_faces = true
			roof_status.text = "roof: " + str(not get_world_3d().direct_space_state.intersect_ray(roof_query).is_empty())
	if playable and not loading: play_time_seconds += _delta
	if playable and not loading and is_instance_valid(zone_notice):
		var zone_key := "%s:%d" % [manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"])]
		if zone_key != announced_zone:
			announced_zone = zone_key
			var names := get_location_names()
			zone_notice.announce(str(names["main"]), str(names["area"]))
	if streaming_rooms:
		var current := player.global_position
		if has_previous_player_position and not loading:
			var collision_shape: Shape3D = $Player/Collision.shape
			var body_height := (collision_shape as CapsuleShape3D).height if collision_shape is CapsuleShape3D else 0.8
			var body_radius := (collision_shape as CapsuleShape3D).radius if collision_shape is CapsuleShape3D else 0.2
			var crossing: Dictionary = room_stream.crossed_room(previous_player_position, current, manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), body_height, body_radius)
			if not crossing.is_empty():
				var previous_stage := manifest_path.get_base_dir().get_file(); var previous_area := int(areas[area_picker.selected]["index"]); var previous_spawn := spawn_position
				room_transfer_pending = true; loading = true; player.set_physics_process(false); area_picker.disabled = true
				var next_stage := str(crossing["stage"])
				var switched := false
				if await _ensure_room_stage_data(next_stage): switched = await room_stream.select_room(next_stage, int(crossing["area"]))
				await get_tree().physics_frame
				if switched and not _find_spawn():
					await room_stream.select_room(previous_stage, previous_area); player.reset_at(previous_spawn); spawn_position = previous_spawn; switched = false
				if switched: player.refresh_room_camera()
				else: player.reset_at(previous_spawn); spawn_position = previous_spawn
				await get_tree().physics_frame
				loading = false; area_picker.disabled = false; room_transfer_pending = false; player.set_physics_process(true)
		var camera_position: Vector3 = player.camera_world_position if player.camera_world_valid else player.camera.global_position
		room_stream.close_cleared_portals(player.global_position, camera_position, ($Player/Collision.shape as CapsuleShape3D).radius)
		previous_player_position = player.global_position
		has_previous_player_position = true
	game_hud.set_aiming(player.aiming)
	var lift_target: CharacterBody3D = player.get_lift_target()
	game_hud.set_lifter_state(is_instance_valid(player.carried_actor), player.special_action == "lift_grab", is_instance_valid(lift_target), false, Input.is_action_pressed("interact") or Input.is_action_pressed("special"))
	game_hud.set_player(_room_local_position(), player.player_model.rotation.y)
	_update_automatic_route()
	_update_nearest_door()
	_update_nearest_npc()
	_update_door_prompt()
	_update_actor_route()
	if not loading and player.global_position.y < bounds.position.y - 12.0:
		if OS.is_debug_build(): push_warning("Player fell outside level collision in %s:%d at %s; restoring %s" % [manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), player.global_position, spawn_position])
		player.reset_at(spawn_position)
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
	_projectile.impact_sound_requested.connect(audio.play_at)
func _update_door_prompt() -> void:
	if not loading and is_instance_valid(nearest_npc):
		var point: Vector3 = nearest_npc.global_position + Vector3.UP * 0.625
		if not player.camera.is_position_behind(point):
			var key := ""
			for event: InputEvent in InputMap.action_get_events("interact"):
				if event is InputEventKey: key = OS.get_keycode_string(event.physical_keycode if event.physical_keycode != 0 else event.keycode); break
			game_hud.set_interaction(player.camera.unproject_position(point), "Talk", key)
			return
	if loading or nearest_door.is_empty(): game_hud.set_interaction(Vector2.ZERO, ""); return
	if streaming_rooms: room_stream.preload_route(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), nearest_door)
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
	var locked := _door_locked(nearest_door); game_hud.set_interaction(player.camera.unproject_position(point), "Locked" if locked else "Open", "" if locked else key)
func _update_nearest_npc() -> void:
	nearest_npc = null
	if loading or event_script == null: return
	native_context["native_wallet"] = player.zenny
	var stage := manifest_path.get_base_dir().get_file()
	var distance := INF; var fallback_range: float = player.body_height * player.body_height * 4.0
	var candidates: Array = actors.get_children(); candidates.append_array(get_tree().get_nodes_in_group("native_interaction_targets"))
	for npc: Node3D in candidates:
		if not is_ancestor_of(npc) or not npc.is_visible_in_tree(): continue
		if npc.is_in_group("native_interaction_targets"):
			if str(npc.get_meta("native_stage", "")) != stage or int(npc.get_meta("native_area", -1)) != int(areas[area_picker.selected]["index"]) or not preload("res://scripts/world/native_interaction.gd").can_play(npc, event_script): continue
		else:
			if not npc.is_in_group("world_npcs"): continue
			var source: Dictionary = npc.source; var private: Array = source.get("native_private_raw", [])
			if private.size() != 4 or not event_script.can_play_native_call(stage, "0x800BDCF8", int(private[3])): continue
		if preload("res://scripts/world/native_interaction.gd").has_target_profile(npc):
			var score := preload("res://scripts/world/native_interaction.gd").target_score(player, npc)
			if score < distance: distance = score; nearest_npc = npc
			continue
		if not preload("res://scripts/world/native_interaction.gd").player_faces_target(player, npc): continue
		var candidate: float = player.global_position.distance_squared_to(npc.global_position)
		if candidate >= fallback_range: continue
		var query := PhysicsRayQueryParameters3D.create(player.global_position + Vector3.UP * player.body_height * 0.65, npc.global_position + Vector3.UP * 0.40625, 1)
		var excluded: Array[RID] = [player.get_rid()]
		if npc is CollisionObject3D: excluded.append(npc.get_rid())
		for body: CollisionObject3D in npc.find_children("*", "CollisionObject3D", true, false): excluded.append(body.get_rid())
		query.exclude = excluded
		if not get_world_3d().direct_space_state.intersect_ray(query).is_empty(): continue
		var score := sqrt(candidate) * 256.0
		if score < distance: distance = score; nearest_npc = npc
func _talk_to_npc(npc: Node3D) -> void:
	if loading or not is_instance_valid(npc): return
	_update_native_player_pose()
	native_context["native_wallet"] = player.zenny
	loading = true; area_picker.disabled = true; game_hud.set_interaction(Vector2.ZERO, "")
	player.velocity = Vector3.ZERO; player.set_physics_process(false); player._play_animation("idle")
	var behavior: Node = npc.get_node_or_null("NativeFollower")
	if behavior == null: behavior = npc.get_node_or_null("NativeNpcBehavior")
	if behavior != null and behavior.has_method("begin_talk"): behavior.begin_talk()
	var facing: Node = preload("res://scripts/world/native_interaction.gd").begin_facing(npc, player)
	if npc.is_in_group("native_interaction_targets"): await preload("res://scripts/world/native_interaction.gd").play(npc, event_script)
	else:
		var source: Dictionary = npc.get("source")
		await event_script.play_native_call(manifest_path.get_base_dir().get_file(), "0x800BDCF8", int(source["native_private_raw"][3]), npc)
	if not is_inside_tree(): return
	await preload("res://scripts/world/native_interaction.gd").end_facing(facing)
	if not is_inside_tree(): return
	if is_instance_valid(behavior) and behavior.has_method("end_talk"): behavior.end_talk()
	loading = false; area_picker.disabled = false; player.set_physics_process(true)
func _update_nearest_door() -> void:
	nearest_door = {}
	if loading or areas.is_empty(): return
	var index := int(areas[area_picker.selected]["index"])
	var distance := INF
	for route: Dictionary in routes:
		if int(route["source_area"]) != index: continue
		if preload("res://scripts/world/native_transition.gd").is_automatic(route): continue
		var destination_stage := str(route.get("destination_stage", manifest_path.get_base_dir().get_file())); var destination_area := int(route["destination_area"]); var destination_known := false
		if streaming_rooms and room_stream.has_room(destination_stage, destination_area): destination_known = true
		elif destination_stage == manifest_path.get_base_dir().get_file():
			for area: Dictionary in areas:
				if int(area["index"]) == destination_area: destination_known = true; break
		else: destination_known = known_stage_areas.has(destination_stage) and known_stage_areas[destination_stage].has(destination_area)
		if not destination_known or preload("res://scripts/world/native_transition.gd").is_automatic(route): continue
		if not streaming_rooms and not route.get("native_contacts", []).is_empty():
			if not preload("res://scripts/world/native_transition.gd").manual_contact(route, _room_local_position(), player.player_model.rotation.y): continue
			var raw: Array = route["source_transform_raw"]; var source := Vector3(-float(raw[0]), -float(raw[1]), float(raw[2])) / 256.0; var contact_distance := player.global_position.distance_squared_to(source)
			if contact_distance < distance: distance = contact_distance; nearest_door = route
			continue
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
			if route.get("native_contacts", []).is_empty() and contact.distance_to(panel_center) > 0.5: continue
			var source_contact: bool = not route.get("native_contacts", []).is_empty()
			if source_contact and not preload("res://scripts/world/native_transition.gd").manual_contact(route, _room_local_position(), player.player_model.rotation.y): continue
			var size: Array = portal["shared_panel_size"]; var axis := 0 if str(portal["normal_axis"]) == "x" else 2; var lateral := 2 if axis == 0 else 0; var radius := ($Player/Collision.shape as CapsuleShape3D).radius
			if absf(player.global_position[lateral] - float(center[lateral])) > float(size[0]) * 0.5 + radius or absf(contact.y - float(center[1])) > (float(size[1]) + player.body_height) * 0.5: continue
			var expected_yaw := -float(route["source_transform_raw"][3]) * TAU / 4096.0
			if absf(wrapf(player.player_model.rotation.y - expected_yaw, -PI, PI)) > TAU * 512.0 / 4096.0 or (not source_contact and not _clear_stream_door_los(portal, manifest_path.get_base_dir().get_file(), index, contact, panel_center)): continue
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

func _door_locked(route: Dictionary) -> bool: return _native_event_set(0x710) or _native_event_set(int(route.get("lock_event", -1)))
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
func _update_automatic_route() -> void:
	if not playable or loading or areas.is_empty() or player.free_flight or player.no_clip: return
	var area := int(areas[area_picker.selected]["index"]); var current: Array = []
	for route: Dictionary in routes:
		if int(route["source_area"]) == area and route.get("native_automatic_walk", null) is Dictionary: current.append(route)
	var route: Dictionary = preload("res://scripts/world/native_transition.gd").automatic_route(current, _room_local_position())
	if route.is_empty(): return
	if _native_event_set(0x730) or _native_event_set(int(route.get("transition_event", -1))):
		var key := "%s:%d:%d" % [manifest_path.get_base_dir().get_file(), area, int(route["record_index"])]
		if not automatic_gate_diagnostics.has(key): push_warning("Native gateway %s requires the alternate event730 script state, which is not implemented" % key); automatic_gate_diagnostics[key] = true
		return
	var stage := str(route["destination_stage"]); var destination := int(route["destination_area"])
	if not known_stage_areas.has(stage) or not known_stage_areas[stage].has(destination): return
	_use_door(route, true)
func _native_event_set(id: int) -> bool:
	var flags: Dictionary = native_context.get("event_flags", {})
	return bool(flags.get(id, flags.get(str(id), false)))
func _use_door(route: Dictionary, automatic: bool = false) -> void:
	automatic = automatic or preload("res://scripts/world/native_transition.gd").is_automatic(route)
	if loading: return
	if _door_locked(route): audio.play_ui("menu_cancel"); return
	var elevator := preload("res://scripts/world/native_transition.gd").is_elevator(route)
	var ladder: bool = streaming_rooms and room_stream.is_ladder_route(manifest_path.get_base_dir().get_file(), int(areas[area_picker.selected]["index"]), route)
	if streaming_rooms and not automatic:
		var current_stage := manifest_path.get_base_dir().get_file(); var current_area := int(areas[area_picker.selected]["index"]); var portal: Dictionary = room_stream.portal_for_route(current_stage, current_area, route)
		if not portal.is_empty():
			if room_stream.opened_portals.has(room_stream._portal_key(portal)): return
			loading = true; nearest_door = {}; area_picker.disabled = true
			var destination_stage := str(route.get("destination_stage", current_stage)); var destination_area := int(route["destination_area"])
			if await room_stream._ensure_room_loaded(destination_stage, destination_area):
				player.player_model.rotation.y = -float(route["source_transform_raw"][3]) * TAU / 4096.0
				var interaction: Dictionary = {} if elevator else player.begin_interaction("door_open", true)
				if not interaction.is_empty(): await get_tree().create_timer(float(interaction["open_at"]), false).timeout
				await room_stream.open_route(current_stage, current_area, route, player.global_position, player.camera.global_position)
				if not player.interaction_role.is_empty(): await player.interaction_finished
			area_picker.disabled = false; loading = false
			return
		var destination_stage := str(route.get("destination_stage", current_stage)); var destination_area := int(route["destination_area"])
		if room_stream.has_room(destination_stage, destination_area) and not room_stream.is_ladder_route(current_stage, current_area, route): return
	if loading: return
	var source_stage := manifest_path.get_base_dir().get_file(); var source_area := area_picker.selected; var source_position := player.global_position; var source_yaw: float = player.player_model.rotation.y; var source_camera_rotation: Vector3 = player.camera_pivot.rotation; var source_spawn := spawn_position; var arrived := false
	var fade_route := route.duplicate(true); fade_route["source_stage"] = source_stage; var fade_profile: Dictionary = preload("res://scripts/world/native_transition.gd").fade_profile(fade_route)
	loading = true
	nearest_door = {}
	area_picker.disabled = true
	player.set_physics_process(false)
	var destination_stage := str(route.get("destination_stage", source_stage)); var policy_changed := false
	if destination_stage != source_stage:
		if not await AssetStore.ensure_stage(destination_stage): cancel_stage_transition(); return
		var path := "res://assets/levels/%s/manifest.json" % destination_stage; var metadata: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		if not metadata is Dictionary: cancel_stage_transition(); return
		var policy: Variant = metadata.get("native_combat_policy", null)
		policy_changed = policy is Dictionary and bool(policy.get("buster_allowed", true)) != player.buster_allowed
	player.player_model.rotation.y = -float(route["source_transform_raw"][3]) * TAU / 4096.0
	if automatic:
		var raw: Array = route["source_transform_raw"]; var quadrant := (int(raw[3]) & 4095) >> 10; var directions := [-1, 0, 1, 0, -1]; var point := Vector3(-float(raw[0] + int(directions[quadrant + 1]) * 16), -float(raw[1]), float(raw[2] - int(directions[quadrant]) * 16)) / 256.0
		if streaming_rooms: point += room_stream.offset_for(source_stage, int(areas[source_area]["index"]))
		var floor_query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * player.body_height, Vector3(point.x, bounds.position.y - player.body_height, point.z), 1); floor_query.exclude = [player.get_rid()]; var floor_hit := get_world_3d().direct_space_state.intersect_ray(floor_query)
		if floor_hit.is_empty() or (floor_hit["normal"] as Vector3).y < 0.65: cancel_stage_transition(); return
		point.y = float(floor_hit["position"].y) + 0.05; player.global_position = point
		if not player.begin_scripted_walk(route["native_automatic_walk"], player.player_model.rotation.y): player.global_position = source_position; cancel_stage_transition(); return
		player.set_physics_process(true)
		var completed: bool = await player.scripted_walk_finished
		if not completed: cancel_stage_transition(); return
		player.set_physics_process(false)
	if ladder:
		var raw: Array = route["source_transform_raw"]
		player.global_position = Vector3(-float(raw[0]), -float(raw[1]) + 6.0, float(raw[2])) / 256.0 + room_stream.offset_for(source_stage, int(areas[source_area]["index"]))
	var door_profile: Dictionary = route.get("native_door", {})
	var flutter_exit: bool = streaming_rooms and not ladder and not automatic and not room_stream.has_room(destination_stage, int(route["destination_area"]))
	var native_transition: bool = not automatic and not ladder and not elevator and streaming_rooms and route.get("source_panel", null) is Dictionary and str(door_profile.get("style", "")) != "sliding_pair"
	if native_transition and not await room_stream.prepare_transition_door(source_stage, route):
		cancel_stage_transition()
		return
	var physical_door: Node3D = null
	if not streaming_rooms and not automatic and not ladder and str(door_profile.get("style", "")) in ["hinged", "hinged_with_fixed_companion"]:
		physical_door = preload("res://scripts/world/native_door.gd").new(); add_child(physical_door); physical_door.sound_requested.connect(audio.play_sound)
		if not physical_door.configure(level, source_stage, route): physical_door.dispose(); cancel_stage_transition(); return
	var interaction: Dictionary = {}
	var animated_transition := false
	if not automatic and not ladder and str(door_profile.get("style", "")) == "sliding_pair":
		var flags: Dictionary = native_context.get("event_flags", {}); var alternate := int(door_profile.get("unsupported_event", -1))
		if alternate >= 0 and bool(flags.get(alternate, flags.get(str(alternate), false))): push_error("Native sliding door alternate timeline is not bound"); cancel_stage_transition(); return
		var sliding := preload("res://scripts/world/native_door.gd").new(); add_child(sliding); sliding.sound_requested.connect(audio.play_sound)
		if not sliding.configure(level, source_stage, route): sliding.dispose(); cancel_stage_transition(); return
		await sliding.open(); await sliding.hold(); await sliding.close(); sliding.dispose(); animated_transition = true
	elif not automatic and not elevator: interaction = player.begin_interaction("ladder_down" if int(route["door_mode"]) == 3 else "ladder_up") if ladder else player.begin_interaction("door_open", not flutter_exit)
	if native_transition and interaction.is_empty():
		cancel_stage_transition()
		return
	if not interaction.is_empty():
		if not ladder:
			await get_tree().create_timer(float(interaction["open_at"]), false).timeout
			if native_transition:
				animated_transition = await room_stream.open_transition_door(source_stage, int(areas[source_area]["index"]), route)
				if not animated_transition:
					if not player.interaction_role.is_empty(): await player.interaction_finished
					cancel_stage_transition()
					return
			elif physical_door != null:
				await physical_door.open(); animated_transition = true
			else: audio.play_sound(0xB8)
			if physical_door != null:
				await get_tree().create_timer(maxf(float(interaction["close_at"]) - player.interaction_elapsed, 0.0), false).timeout
				await physical_door.close(); physical_door.dispose()
			elif animated_transition and not flutter_exit:
				await get_tree().create_timer(maxf(float(interaction["close_at"]) - player.interaction_elapsed, 0.0), false).timeout
				await room_stream.close_transition_door(source_stage, int(areas[source_area]["index"]), route)
		if not player.interaction_role.is_empty(): await player.interaction_finished
		if not ladder and not animated_transition: audio.play_sound(0xB9)
	if flutter_exit:
		if not player.begin_scripted_walk({"control": 2, "ticks": 8, "tick_rate": 25, "local_step_raw": [0, 0, -256]}, player.player_model.rotation.y): cancel_stage_transition(); return
		player.set_physics_process(true); await player.scripted_walk_finished; player.set_physics_process(false)
	await transition_overlay.request(int(fade_profile.get("exit", 0xFF)))
	if flutter_exit and animated_transition: await room_stream.close_transition_door(source_stage, int(areas[source_area]["index"]), route)
	if policy_changed or streaming_rooms != (not preload("res://scripts/world/room_stream.gd").layout_path_for(destination_stage, int(route["destination_area"])).is_empty()):
		var request := fade_route.duplicate(true); request["native_entry_fade"] = int(fade_profile.get("entry", 0xFF))
		stage_transition_requested.emit(request)
		return
	if destination_stage != manifest_path.get_base_dir().get_file() and streaming_rooms and not await _ensure_room_stage_data(destination_stage):
		await transition_overlay.request(int(fade_profile.get("entry", 0xFF)))
		area_picker.disabled = false
		loading = false
		player.set_physics_process(true)
		return
	if destination_stage != manifest_path.get_base_dir().get_file() and not await _change_stage(destination_stage):
		await transition_overlay.request(int(fade_profile.get("entry", 0xFF)))
		area_picker.disabled = false
		loading = false
		player.set_physics_process(true)
		return
	var destination := int(route["destination_area"])
	var selected := -1
	for index in range(areas.size()):
		if int(areas[index]["index"]) == destination: selected = index
	if selected >= 0:
		entry_route = route.duplicate(true)
		var selected_ok := await _select_area(selected, true)
		entry_route = {}
		arrived = selected_ok
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
	await transition_overlay.request(int(fade_profile.get("entry", 0xFF)))
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
	native_floor_collision = manifest.get("native_floor_collision", {})
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
	player.cancel_scripted_walk()
	loading = false; area_picker.disabled = false; nearest_door = {}; player.set_physics_process(true)
	if is_instance_valid(transition_overlay): transition_overlay.clear()
func _door_arrival(transform: Dictionary, world_offset: Vector3 = Vector3.ZERO) -> Vector3:
	var coordinates: Array = transform["position"]
	var point := Vector3(-float(coordinates[0]), -float(coordinates[1]) + 0.05, float(coordinates[2])) + world_offset
	if transform.get("floor_height", false):
		var ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * player.body_height, Vector3(point.x, bounds.position.y - 1.0, point.z), 1); ray.exclude = [player.get_rid()]
		var hit := get_world_3d().direct_space_state.intersect_ray(ray)
		if hit.is_empty(): return Vector3.INF
		point.y = float(hit["position"].y) + 0.05
	var capsule := $Player/Collision.shape as CapsuleShape3D; var collision := $Player/Collision as CollisionShape3D; var yaw := -float(int(transform.get("yaw_raw", 0))) * TAU / 4096.0; var forward := Vector3(-sin(yaw), 0.0, -cos(yaw)); var step := maxf(capsule.radius * 0.25, 0.01); var query := PhysicsShapeQueryParameters3D.new(); query.shape = capsule; query.collision_mask = player.collision_mask | 1; query.exclude = [player.get_rid()]; query.margin = 0.01
	var anchor_ray := PhysicsRayQueryParameters3D.create(point + Vector3.UP * capsule.radius, point - Vector3.UP * capsule.height, 1); anchor_ray.exclude = [player.get_rid()]; var anchor_floor := get_world_3d().direct_space_state.intersect_ray(anchor_ray)
	if not anchor_floor.is_empty() and (anchor_floor["normal"] as Vector3).y >= 0.65:
		var anchor := point; anchor.y = (anchor_floor["position"] as Vector3).y + 0.05; query.transform = Transform3D(player.global_basis, anchor) * collision.transform
		if get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty(): return anchor
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
				var arrays: Array = mesh_node.mesh.surface_get_arrays(surface); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array else PackedInt32Array(); var count := indices.size() if not indices.is_empty() else vertices.size()
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
				preview.set_meta("native_map_face_flags", bool(entries[initial_area].get("native_map_face_flags_in_alpha", false)))
				container.add_child(preview)
				preload("res://scripts/world/native_material.gd").apply(preview)
	update_configuration_warnings()
func _get_configuration_warnings() -> PackedStringArray:
	return PackedStringArray([editor_preview_warning]) if not editor_preview_warning.is_empty() else PackedStringArray()
