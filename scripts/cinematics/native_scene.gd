extends Node
signal completed(success: bool)
const Props := preload("res://scripts/world/actors/native_props.gd")
const Facing := preload("res://scripts/world/actors/native_talk_facing.gd")
var host: Node3D
var scene_root: Node3D
var data: Dictionary = {}
var callbacks: Dictionary = {}
var xa_entries: Dictionary = {}
var xa_streams: Dictionary = {}
var directory := ""
var stage := ""
var area := 0
var camera: Camera3D
var camera_collision := false
var shot_suppressed: Array[Node3D] = []
var actors: Dictionary = {}
var records: Dictionary = {}
var segment := 0
var segment_tick := 0
var phase_tick := 0
var total_tick := 0
var command_index := 0
var program_index := 0
var operation_started := false
var operation_tick := 0
var message_busy := false
var message_failed := false
var finishing := false
var running := false
var elapsed := 0.0
var director_state := 0
var head_target := 0
var head_speed := 0
var head_units := 0
var player_clock: NativeAnimation
var saved_motion_active := false
var target_mode := 0
var target_slot := 0
var eye_mode := 0
var focus := Vector3.ZERO
var relative_focus := Vector3.ZERO
var orbit := Vector3.ZERO
var eye := Vector3.ZERO
var focus_velocity := Vector3.ZERO
var orbit_velocity := Vector3.ZERO
var eye_velocity := Vector3.ZERO
var trig: Array = []
var xa: AudioStreamPlayer
var transition_route: Dictionary = {}
var suppressed: Array[Node3D] = []
var suppressed_streams: Array[Dictionary] = []
var owns_root := false
var answer := 0
var skip_locked := false
var skip_requested := false
var scene_flags := 0
var sound_latched := false
var faces: Dictionary = {}
var interpolations: Dictionary = {}
var shake := 0
var shake_decay := 0
var roll := 0
var callback_advanced := false
var area_loading := false
var fade_busy := false
var faded := false
var xa_ready_tick := -1
var xa_answer := -1
var player_faces: Array = []
var player_face_page: Texture2D
var registration_records: Array[String] = []
var player_pose: Node3D
func configure(gameplay: Node3D, level: Node3D, path: String, requested_area: int = -1) -> bool:
	host = gameplay; scene_root = level; directory = path.get_base_dir()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary: return false
	if parsed.has("branch_event_flag"):
		var flags: Dictionary = host.native_context.get("event_flags", {}); var id := int(parsed["branch_event_flag"]); data = parsed.get("branches", {}).get("set" if bool(flags.get(id, flags.get(str(id), false))) else "clear", {})
	else: data = parsed.get("branches", {}).get(str(requested_area), {}) if parsed.has("branches") else parsed
	if data.is_empty(): return false
	stage = str(data["stage"]); area = int(data["area"])
	var callback_path: String = directory.path_join(str(data["callback_contract_file"]))
	if not FileAccess.file_exists(callback_path): return false
	var contract: Variant = JSON.parse_string(FileAccess.get_file_as_string(callback_path))
	if not contract is Dictionary: return false
	callbacks = contract
	registration_records.clear()
	for record in callbacks.get("finish", {}).get("registration_records", []): registration_records.append(str(record).to_lower())
	if callbacks.get("finish", {}).has("registration_record"): registration_records.append(str(callbacks["finish"]["registration_record"]).to_lower())
	var weather: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/weather/manifest.json"))
	if weather is Dictionary: trig = weather.get("trig4096", [])
	if trig.size() != 4096: return false
	for record: Dictionary in data.get("actors", []): records[str(record["source_ram"]).to_lower()] = record
	for entry: Dictionary in data.get("timeline", []):
		if not callbacks.get("segments", {}).has("%d:%d" % [int(entry["phase"]), int(entry["step"])]): return false
	if JSON.stringify(callbacks.get("segments", {})).contains("\"area_change\""): scene_root = Node3D.new(); scene_root.name = "NativeSceneRoot"; host.add_child(scene_root); scene_root.global_transform = level.global_transform; owns_root = true
	camera = Camera3D.new(); camera.name = "NativeSceneCamera"; camera.near = host.player.camera.near; camera.far = host.player.camera.far; camera.fov = rad_to_deg(2.0 * atan(120.0 / 384.0)); scene_root.add_child(camera)
	if bool(data.get("player", {}).get("track_runtime", false)): player_pose = Node3D.new(); scene_root.add_child(player_pose); player_pose.global_position = host.player.global_position; player_pose.global_rotation.y = host.player.player_model.global_rotation.y
	player_clock = preload("res://scripts/world/actors/native_animation.gd").new(); player_clock.automatic = false; add_child(player_clock)
	var clips: Array = []
	for clip: Dictionary in host.player.native_clips.values():
		if str(clip["name"]) != "clip_%03d" % int(clip.get("slot", -1)): continue
		var adapted: Dictionary = clip.duplicate(true)
		for name: StringName in host.player.animation_player.get_animation_list():
			if str(name).get_file() == str(clip["name"]): adapted["name"] = str(name); break
		clips.append(adapted)
	var bank_path := directory.path_join("player_scene.json")
	if FileAccess.file_exists(bank_path):
		var bank: Variant = JSON.parse_string(FileAccess.get_file_as_string(bank_path))
		if not bank is Dictionary: camera.queue_free(); _release_root(); return false
		var library_name := str(bank["library"])
		if not host.player.animation_player.has_animation_library(library_name):
			var packed := load(directory.path_join(str(bank["model"]))) as PackedScene
			if packed == null: camera.queue_free(); _release_root(); return false
			var instance := packed.instantiate(); var players: Array[Node] = instance.find_children("*", "AnimationPlayer", true, false)
			if players.is_empty(): instance.free(); camera.queue_free(); _release_root(); return false
			host.player.animation_player.add_animation_library(library_name, (players[0] as AnimationPlayer).get_animation_library("").duplicate(true)); instance.free()
		for clip: Dictionary in bank["clips"]:
			var adapted: Dictionary = clip.duplicate(true); adapted["name"] = library_name + "/" + str(clip["name"]); clips.append(adapted)
	if not player_clock.configure(host.player.animation_player, clips): camera.queue_free(); _release_root(); return false
	return true
func run() -> bool:
	if host.has_method("set_scene_presentation"): host.set_scene_presentation(true)
	host.player.player_model.visible = true
	_player_face_setup()
	saved_motion_active = host.player.motion_tree.active if host.player.motion_tree != null else false
	if host.player.motion_tree != null: host.player.motion_tree.active = false
	host.player.velocity = Vector3.ZERO; host.player.set_physics_process(false)
	if not await _prepare_voice_assets(): _restore(); return false
	if bool(host.get("streaming_rooms")) and is_instance_valid(host.room_stream):
		for key in host.room_stream.opened_portals.keys():
			var leaf: Node3D = host.room_stream.portal_leaves.get(key)
			if is_instance_valid(leaf) and leaf.has_meta("closed_yaw"): leaf.rotation.y = float(leaf.get_meta("closed_yaw"))
			await host.room_stream._close_portal(str(key))
	var initial: Dictionary = callbacks["initialization"]; head_units = 0
	if not bool(initial.get("player_keep_transform", false)): host.player.global_position = scene_root.to_global(_world(initial["player_position_raw"])); _set_yaw(host.player.player_model, int(initial["player_yaw_raw"]))
	if initial.has("music_cue"): host.audio.play_sound(int(initial["music_cue"]))
	for placement: int in initial.get("suppress_placements", []):
		for node: Node3D in scene_root.find_children("placement_%03d_*" % placement, "Node3D", true, false): node.hide(); suppressed.append(node)
	suppressed_streams = preload("res://scripts/world/rendering/native_material.gd").placement_streams(scene_root, initial.get("placement_streams", []))
	var suppress_props: Array = initial.get("suppress_props", [])
	if not suppress_props.is_empty() and is_instance_valid(host.level):
		for node: Node3D in host.level.find_children("*", "Node3D", true, false):
			for rule: Dictionary in suppress_props:
				if str(node.get_meta("native_spawn_set", "")) == str(rule["spawn_set"]) and str(node.get_meta("native_identity", "")) == str(rule.get("identity", node.get_meta("native_identity", ""))): node.hide(); suppressed.append(node)
	if host.player.upper_modifier != null: host.player.upper_modifier.track_target = false; host.player.upper_modifier.set_source_aim_angles(0, 0)
	var commanded := {}
	for command: Dictionary in data["commands"]:
		if int(command["opcode"]) == 64: commanded[str(command.get("actor_record", {}).get("source_ram", "0x%08x" % int(command["words"][1]))).to_lower()] = true
	for record: Dictionary in records.values():
		if record["model"] == null and not record["entry"].has("native_backdrop") or str(record["source_ram"]).to_lower() in registration_records and not commanded.has(str(record["source_ram"]).to_lower()): continue
		var node: Node3D
		if record.has("existing_actor"):
			for candidate: Node3D in host.actors.find_children("*", "Node3D", true, false):
				if str(candidate.get_meta("native_existing_actor", "")) == str(record["existing_actor"]): node = candidate; break
		elif record["entry"].has("native_backdrop"): node = preload("res://scripts/cinematics/native_stage_backdrop.gd").new(); scene_root.add_child(node); node.configure(self, record["entry"])
		else: node = await Props.spawn_entry(scene_root, stage, area, record["entry"], record["model"], host.native_context)
		if node == null: _restore(); return false
		var clock := node.get_node_or_null("NativeAnimationClock") as NativeAnimation if not record.has("existing_actor") else null
		if clock != null: clock.automatic = false
		var metadata: Dictionary = record["model"] if record["model"] is Dictionary else {}; var direct: bool = record.has("existing_actor") or str(record["source_ram"]) in initial.get("spawn_records", []); node.visible = direct and not node.has_meta("native_scene_deferred"); actors[int(record["slot"])] = {"node": node, "clock": clock, "record": record, "active": direct, "borrowed": record.has("existing_actor"), "head_target": 0, "head_speed": 0, "head_enabled": false, "flag_started": false, "fields": {}, "face_tables": {}, "face_dims": metadata.get("face_dims", [0, 0, 0, 0]), "face_surfaces": _face_surfaces(node, metadata.get("source_surfaces", []))}
	for operation: Dictionary in initial.get("init_ops", []):
		if str(operation["op"]) == "play_xa":
			await _play_xa(int(operation["descriptor"]))
			while is_inside_tree() and is_instance_valid(xa) and xa.get_playback_position() <= 0.0: await get_tree().process_frame
			if message_failed: _restore(); return false
		elif str(operation["op"]) == "fade":
			if bool(operation.get("wait", true)): await _fade(int(operation["type"]))
			else: _fade(int(operation["type"]), false)
		else: _action(operation)
	if callbacks.has("xa") and not initial.has("init_ops"):
		var audio_path := directory.path_join("audio/manifest.json")
		if not FileAccess.file_exists(audio_path): _restore(); return false
		var audio: Variant = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		if not audio is Dictionary or int(audio.get("id", -1)) != int(callbacks["xa"]["descriptor_index"]): _restore(); return false
		if not await AssetStore.ensure_voice(audio): _restore(); return false
		var stream: AudioStream = await host.audio._load_stream(str(audio["file"]))
		if stream == null: _restore(); return false
		xa = AudioStreamPlayer.new(); xa.stream = stream; xa.bus = "SFX" if AudioServer.get_bus_index("SFX") >= 0 else "Master"; add_child(xa); xa.play()
		while is_inside_tree() and xa.get_playback_position() <= 0.0: await get_tree().process_frame
	camera.make_current(); running = true; _commands(); _interpolate(); segment_tick = 1; phase_tick = 1; total_tick = 1; _camera_update()
	var success: bool = await completed
	_restore(); return success
func _process(delta: float) -> void:
	if not running or finishing: return
	if skip_requested: _skip_scene()
	if finishing: return
	elapsed += delta * float(data.get("native_tick_hz", 25))
	while elapsed >= 1.0 and running and not finishing:
		elapsed -= 1.0; native_tick()
func native_tick() -> void:
	if message_failed: running = false; completed.emit(false); return
	if area_loading: return
	var profile: Dictionary = _profile()
	for sound: Dictionary in profile.get("sounds", []):
		if int(sound["tick"]) == segment_tick: host.audio.play_at(int(sound["id"]), scene_root.to_global(_world(sound["position_raw"])))
	for action: Dictionary in profile.get("actions", []):
		if action.has("from_tick"):
			if segment_tick >= int(action["from_tick"]) and segment_tick <= int(action["through_tick"]): _action(action)
		elif int(action["tick"]) == segment_tick: _action(action)
	if profile.has("camera_roll"):
		var curve: Dictionary = profile["camera_roll"]; var offset := segment_tick - int(curve["from_tick"])
		roll = int(curve["values_raw"][offset]) if offset >= 0 and offset < curve["values_raw"].size() else int(curve.get("otherwise", 0))
	for motion: Dictionary in profile.get("motion", []):
		if not _motion_active(motion): continue
		if str(motion.get("op", "")) == "player_axis_set": _action(motion)
		else: _motion(host.player, host.player.player_model, motion)
	_program(profile.get("program", []))
	if not running or finishing or area_loading: return
	if callback_advanced: callback_advanced = false
	else:
		_commands(); _interpolate(); segment_tick += 1; phase_tick += 1; total_tick += 1
		var duration := int(data["timeline"][segment]["duration"])
		if duration >= 0 and segment_tick == duration: _advance()
		if not running or finishing: return
	if is_instance_valid(player_pose):
		var reference: float = host.player.global_position.y; _track(player_pose, data["player"]["track"], int(data["timeline"][segment]["step"]))
		if bool(data["player"].get("floor_follow", false)): _floor_follow(player_pose, reference, [-32, 32, -roundi(host.player.body_height * 256.0), 0, -32, 32])
		host.player.global_position = player_pose.global_position; host.player.player_model.global_rotation.y = player_pose.global_rotation.y
	_head_tick(); player_clock.native_tick(); _xa_tick(); _actor_tick(); _face_tick(); _camera_update()
	if camera.has_node("NativeBackdrop"): camera.get_node("NativeBackdrop").native_tick()
func _profile() -> Dictionary:
	var entry: Dictionary = data["timeline"][segment]; return callbacks["segments"]["%d:%d" % [int(entry["phase"]), int(entry["step"])]]
func _program(program: Array) -> void:
	while program_index < program.size():
		var operation: Dictionary = program[program_index]; var op := str(operation["op"])
		if not operation_started:
			operation_started = true; operation_tick = segment_tick
			if operation.has("state"): director_state = int(operation["state"])
			if op in ["message", "message_start"]: _message(int(operation["index"]))
			elif op == "area_change": _area_change(operation)
			elif op == "fade": _fade(int(operation["type"]), bool(operation.get("wait", true)))
			elif op == "jump" or (op == "jump_if" and answer == int(operation["answer"])): program_index = _label(program, str(operation["to"])); operation_started = false; continue
			elif op not in ["message_wait", "minimum_tick", "delay", "turn_wait", "advance", "finish", "label", "jump_if", "wait_flag_clear", "wait_xa_idle", "wait_actor_inactive"]: _action(operation)
		if message_failed: return
		if op == "area_change" and area_loading: return
		if op == "fade" and fade_busy: return
		if op == "wait_flag_clear" and _flag(_flag_id(operation["flag"])): return
		if op == "wait_xa_idle" and is_instance_valid(xa) and xa.playing: return
		if op == "wait_actor_inactive" and actors.has(int(operation["slot"])):
			var actor: Variant = actors[int(operation["slot"])]["node"]
			if is_instance_valid(actor):
				if not actor.has_method("native_scene_active"): message_failed = true; return
				if actor.native_scene_active(): return
		if op in ["message", "message_wait"] and message_busy: return
		if op == "delay" and segment_tick - operation_tick < int(operation["ticks"]): return
		if op == "minimum_tick" and segment_tick < int(operation["tick"]): return
		if op == "turn_wait" and _turn(host.player.player_model, int(operation["heading"]), int(operation["speed"])) != 0: return
		if op == "advance": _advance(callbacks.has("tick_basis")); return
		if op == "finish": _finish_scene(); return
		program_index += 1; operation_started = false
func _message(index: int) -> void:
	message_busy = true
	var success: bool = await host.event_script.play_bound_message(stage, "0x8010C000", index, "0x80048474")
	message_busy = false; message_failed = message_failed or not success
func _mission_banner() -> Control:
	var hud: Node = host.get_node("HUD"); var banner := hud.get_node_or_null("MissionBanner") as Control
	if banner == null: banner = preload("res://scripts/ui/hud/mission_banner.gd").new(); banner.name = "MissionBanner"; hud.add_child(banner); hud.move_child(banner, host.dialogue_box.get_index())
	return banner
func _action(action: Dictionary) -> void:
	match str(action["op"]):
		"player_control": player_clock.play_control(int(action["control"]), int(action.get("start_record", 0)))
		"hp_refill": host.player.refill_health()
		"director_state": director_state = int(action["state"])
		"result_banner": _mission_banner().show_banner(int(action["args_raw"][0]), int(action["args_raw"][1]), int(action["args_raw"][2]))
		"result_banner_hide": _mission_banner().hide_banner()
		"player_special_usable":
			host.player.special_usable = int(action["value"]) != 0
		"head_target": head_target = int(action["target"]); head_speed = int(action["speed"])
		"story_advance": host.native_context["native_save_byte15"] = (int(host.native_context.get("native_save_byte15", host.native_context.get("native_save_byte14", 0))) + 1) & 255
		"event_set":
			var flags: Dictionary = host.native_context.get("event_flags", {}); flags[int(action["id"])] = true; host.native_context["event_flags"] = flags
		"event_clear": _clear_flag(int(action["id"]))
		"close_windows": host.dialogue_box.finish_native_message()
		"despawn":
			var record: Dictionary = records.get(str(action["record"]).to_lower(), {})
			if not record.is_empty(): _remove(int(record["slot"]))
		"actor_spawn": _activate_record(str(action["record"]).to_lower())
		"player_face_init": faces.erase(host.player.player_model.get_instance_id())
		"player_face": _set_face(host.player.player_model, "player_" + str(action["channel"]), str(action["channel"]), int(action["sequence"]))
		"player_face_frame":
			var node: Node3D = host.player.player_model; faces.erase("%d:%s" % [node.get_instance_id(), str(action["channel"])]); node.set_meta("native_face_" + str(action["channel"]), int(action["frame"])); _apply_face(node, str(action["channel"]), int(action["frame"]))
		"player_render_flag": host.player.player_model.visible = bool(action["set"])
		"player_axis_set":
			var value := _expression(action["value_raw"]); var local: Vector3 = scene_root.to_local(host.player.global_position); local[{"x": 0, "y": 1, "z": 2}[str(action["axis"])]] = (-1.0 if str(action["axis"]) != "z" else 1.0) * float(value) / 256.0; host.player.global_position = scene_root.to_global(local)
		"player_yaw_set": _set_yaw(host.player.player_model, int(action["yaw_raw"]))
		"player_yaw_add": _set_yaw(host.player.player_model, (_yaw(host.player.player_model) + int(action["delta_raw"])) & 4095)
		"play_sound": host.audio.play_sound(int(action["id"]))
		"sound_latch": sound_latched = int(action["value"]) != 0
		"pool_clear":
			if (int(action["mask"]) & 0xFFE) != 0:
				for slot: int in actors.keys():
					if bool(actors[slot]["active"]): _remove(slot)
				for node: Node in get_tree().get_nodes_in_group("native_pool_actors"): node.queue_free()
		"actor_state":
			if actors.has(int(action["slot"])): actors[int(action["slot"])]["fields"]["0x0C"] = int(action["field_0x0C"])
		"camera_shake": shake = int(action["magnitude_raw"]); shake_decay = int(action["decay_raw"])
		"skip_lock": skip_locked = bool(action["set"])
		"scene_flag": scene_flags = scene_flags | int(action["mask"]) if bool(action["set"]) else scene_flags & ~int(action["mask"])
		"select_by_flags":
			var ids: Array = action["flags"]
			for index in range(ids.size()):
				if _flag(int(ids[index])): answer = index
		"play_xa": _play_xa(int(action["descriptor_by_answer"][answer]) if action.has("descriptor_by_answer") else int(action["descriptor"]))
		"music_prepare": pass
		"music_play": _play_xa(int(action["id"]))
		"jingle": host.audio.fade_sequences(int(action["args_raw"][0]), int(action["args_raw"][1]), int(action["args_raw"][2]))
		"xa_fade_out": _fade_xa(int(action["speed"]))
		"sky_gradient": camera.set_meta("native_sky_gradient", [int(action.get("horizon_raw", 0)), int(action.get("param_18_raw", 0))])
		"scrolling_backdrop":
			if not camera.has_node("NativeBackdrop"):
				var backdrop := preload("res://scripts/cinematics/native_backdrop.gd").new(); backdrop.name = "NativeBackdrop"; camera.add_child(backdrop); backdrop.configure(load(directory.path_join(str(action["texture"]))))
			camera.get_node("NativeBackdrop").set_state(action)
func _advance(from_callback: bool = false) -> void:
	callback_advanced = from_callback
	var old_phase := int(data["timeline"][segment]["phase"]); segment += 1
	if segment >= data["timeline"].size(): _finish_scene(); return
	segment_tick = 0; program_index = 0; operation_started = false; director_state = 0
	if int(data["timeline"][segment]["phase"]) != old_phase: phase_tick = 0
func _motion_active(profile: Dictionary) -> bool:
	if profile.has("step") and int(profile["step"]) != int(data["timeline"][segment]["step"]): return false
	if segment_tick < int(profile.get("from_tick", 0)) or segment_tick > int(profile.get("through_tick", 2147483647)): return false
	if profile.has("requires_flag"):
		var flags: Dictionary = host.native_context.get("event_flags", {}); var id := int(profile["requires_flag"])
		if not bool(flags.get(id, flags.get(str(id), false))): return false
	return true
func _motion(node: Node3D, orientation: Node3D, profile: Dictionary) -> void:
	var bearing := Facing._heading(node.global_position, scene_root.to_global(_world(profile["point_raw"]))) if profile.has("point_raw") else int(profile.get("heading", _yaw(orientation)))
	if profile.has("turn_speed"): _turn(orientation, int(profile.get("heading", bearing)), int(profile["turn_speed"]))
	if profile.has("speed_raw"):
		var speed := int(profile["speed_raw"]); node.global_position += Vector3(float(-speed * int(trig[bearing & 4095][0])), 0.0, float(speed * int(trig[bearing & 4095][1]))) / 16777216.0
	if profile.has("velocity_raw"):
		var velocity: Array = profile["velocity_raw"]; var heading := _yaw(orientation); var sine := int(trig[heading][0]); var cosine := int(trig[heading][1]); node.global_position += Vector3(float(-cosine * int(velocity[0]) - sine * int(velocity[2])), -float(int(velocity[1]) * 4096), float(-sine * int(velocity[0]) + cosine * int(velocity[2]))) / 16777216.0
func _turn(node: Node3D, desired: int, maximum: int) -> int:
	var current := _yaw(node); var difference := (desired - current) & 4095
	if difference > 2048: difference -= 4096
	_set_yaw(node, (current + clampi(difference, -maximum, maximum)) & 4095); return difference
func _yaw(node: Node3D) -> int: return roundi(-node.rotation.y * 4096.0 / TAU) & 4095
func _set_yaw(node: Node3D, value: int) -> void: node.rotation.y = -float(value) * TAU / 4096.0
func _world(value: Array) -> Vector3: return Vector3(-float(value[0]), -float(value[1]), float(value[2])) / 256.0
func _actor_tick() -> void:
	var step := int(data["timeline"][segment]["step"])
	for slot: int in actors:
		var actor: Dictionary = actors[slot]
		if not bool(actor["active"]) or not is_instance_valid(actor["node"]): continue
		var node: Node3D = actor["node"]; var profile: Dictionary = callbacks.get("actor_controllers", {}).get(str(slot), {}); var clock: NativeAnimation = actor["clock"]
		if profile.has("external_controller"): continue
		node.position -= actor.get("render_offset", Vector3.ZERO)
		if profile.has("hinge_raw"):
			if not actor.has("rest_yaw"): actor["rest_yaw"] = node.rotation.y
			node.position -= actor.get("hinge_shift", Vector3.ZERO)
		var total_yaw: Dictionary = profile.get("total_yaw_increment", {})
		if not total_yaw.is_empty() and total_tick >= int(total_yaw["from_tick"]) and total_tick <= int(total_yaw["through_tick"]): _set_yaw(node, (_yaw(node) + mini(total_tick >> int(total_yaw["shift"]), int(total_yaw["maximum"])) * int(total_yaw["sign"])) & 4095)
		if profile.has("hinge_raw"):
			var hinge := _world(profile["hinge_raw"]); actor["hinge_shift"] = Basis(Vector3.UP, actor["rest_yaw"]) * hinge - Basis(Vector3.UP, node.rotation.y) * hinge; node.position += actor["hinge_shift"]
		for event: Dictionary in profile.get("events", []):
			if int(event["step"]) != step: continue
			if event.has("tick") and int(event["tick"]) != segment_tick: continue
			if event.has("state") and int(event["state"]) != director_state: continue
			match str(event["op"]):
				"actor_face_init": actor["face_tables"] = {"eyes": str(event["eye_table_ram"]).to_lower() if event["eye_table_ram"] != null else "", "mouth": str(event["mouth_table_ram"]).to_lower() if event["mouth_table_ram"] != null else ""}
				"actor_face": _set_face(node, str(actor["face_tables"].get(str(event["channel"]), "")), str(event["channel"]), int(event["sequence"]))
				"control":
					if clock != null: clock.play_control(int(event["control"]), int(event.get("start_record", 0)))
				"position": node.position = _world(event["position_raw"])
				"actor_head": actor["head_target"] = int(event["target"]); actor["head_speed"] = int(event["speed"]); actor["head_enabled"] = true; node.set_meta("native_head_target", event.duplicate())
		var flag_start: Dictionary = profile.get("event_flag_start", {})
		if not flag_start.is_empty() and int(flag_start["step"]) == step and not bool(actor["flag_started"]):
			var flags: Dictionary = host.native_context.get("event_flags", {}); var id := int(flag_start["id"])
			if bool(flags.get(id, flags.get(str(id), false))):
				actor["flag_started"] = true
				if clock != null: clock.play_control(int(flag_start["control"]))
		for motion: Dictionary in profile.get("motion", []):
			if _motion_active(motion): _motion(node, node, motion)
		if profile.has("track"):
			var reference := node.global_position.y; _track(node, profile["track"]["keyframes"], step)
			if bool(profile["track"].get("floor_follow", false)):
				var floor_bounds: Array = actor["record"]["entry"].get("native_hitbox", {}).get("bounds_raw", []).duplicate()
				if floor_bounds.size() == 6 and profile["track"].has("floor_above_raw"): floor_bounds[2] = -int(profile["track"]["floor_above_raw"])
				_floor_follow(node, reference, floor_bounds)
		if xa_answer >= 0 and xa_ready_tick >= 0:
			for reaction: Dictionary in profile.get("answer_reactions", {}).get("by_answer", {}).get(str(xa_answer), []):
				if int(reaction["after_xa_ready_ticks"]) != total_tick - xa_ready_tick: continue
				if str(reaction["op"]) == "event_clear": _clear_flag(int(reaction["id"]))
				elif str(reaction["op"]) == "actor_face": _set_face(node, str(actor["face_tables"].get(str(reaction["channel"]), "")), str(reaction["channel"]), int(reaction["sequence"]))
		if clock != null: clock.native_tick()
		if node.has_method("native_tick"): actor["fields"]["scene_step"] = step; actor["fields"]["scene_tick"] = segment_tick; node.native_tick(actor["fields"])
		var render_raw: Array = profile.get("render_offset_by_step", {}).get(str(step), [0, 0, 0]); actor["render_offset"] = _world(render_raw); node.position += actor["render_offset"]
func _head_tick() -> void:
	var difference := ((_yaw(host.player.player_model) + head_units - head_target + 2048) & 4095) - 2048
	if difference < -int(head_speed / 2): head_units = mini(768, head_units + head_speed)
	elif difference > int(head_speed / 2): head_units = maxi(-768, head_units - head_speed)
	if host.player.upper_modifier != null: host.player.upper_modifier.set_source_aim_angles(0, head_units)
func _commands() -> void:
	while command_index < data["commands"].size():
		var command: Dictionary = data["commands"][command_index]; var words: Array = command["words"]; var opcode := int(command["opcode"]); var header := int(words[0]); var timeline: Dictionary = data["timeline"][segment]
		if opcode == 0 and total_tick < (header & 0xFFFFFF): return
		if opcode == 1 and (int(timeline["phase"]) != ((header >> 16) & 255) or phase_tick != (header & 65535)): return
		if opcode == 2 and (int(timeline["step"]) != ((header >> 16) & 255) or segment_tick != (header & 65535)): return
		command_index += 1
		match opcode:
			0, 1, 2: pass
			3: eye_mode = 0
			4: eye_mode = 1
			5: target_mode = 0
			6: target_mode = 1
			7: target_mode = 2
			16: target_mode = 0; focus = _fixed(words)
			17, 18: target_mode = 1 if opcode == 17 else 2; target_slot = (header >> 16) & 255; relative_focus = _fixed(words)
			19: orbit = _fixed(words)
			20: eye = _fixed(words)
			21: focus_velocity = _fixed(words); interpolations.erase("focus")
			22: orbit_velocity = _fixed(words); interpolations.erase("view")
			23: eye_velocity = _fixed(words); interpolations.erase("view")
			32, 33, 34: camera.set_meta("native_depth_cue_mode", opcode - 32)
			64:
				var record: Dictionary = records.get(str(command.get("actor_record", {}).get("source_ram", "")).to_lower(), {})
				if record.is_empty(): record = records.get("0x%08x" % int(words[1]), {})
				if record.is_empty(): message_failed = true; return
				_activate_record(str(record["source_ram"]).to_lower())
			65:
				var record: Dictionary = records.get("0x%08x" % int(words[1]), {})
				if not record.is_empty(): _remove(int(record["slot"]))
			66:
				host.player.global_position = scene_root.to_global(_world([_fixed(words).x, _fixed(words).y, _fixed(words).z])); _set_yaw(host.player.player_model, int(words[4]) & 4095)
			24, 25, 26:
				var channel := "focus" if opcode == 24 else "view"; var origin: Vector3 = (focus if target_mode == 0 else relative_focus) if opcode == 24 else orbit if opcode == 25 else eye
				interpolations[channel] = {"from": origin, "to": _fixed(words), "ticks": maxi(header & 65535, 1), "ease": (header >> 16) & 7, "elapsed": 0}
				if opcode == 24: focus_velocity = Vector3.ZERO
				elif opcode == 25: orbit_velocity = Vector3.ZERO
				else: eye_velocity = Vector3.ZERO
			255: return
			_: message_failed = true; return
func _fixed(words: Array) -> Vector3: return Vector3(_s32(int(words[1])), _s32(int(words[2])), _s32(int(words[3]))) / 65536.0
func _s32(value: int) -> int: return (value & 2147483647) - (value & 2147483648)
func _camera_update() -> void:
	_restore_shot_visibility()
	var shot := _profile()
	if shot.has("visible_actor_slots"):
		for slot: int in actors:
			var node: Variant = actors[slot]["node"]
			if is_instance_valid(node) and node.visible and not shot["visible_actor_slots"].has(float(slot)): shot_suppressed.append(node); node.hide()
	if not bool(shot.get("player_visible", true)) and host.player.player_model.visible: shot_suppressed.append(host.player.player_model); host.player.player_model.hide()
	var target := focus
	var render_offset: Array = _profile().get("camera_offset_raw", [0, 0, 0])
	if target_mode == 1 and actors.has(target_slot):
		var tracked: Variant = actors[target_slot]["node"]; if is_instance_valid(tracked): actors[target_slot]["last_global"] = tracked.global_position
		var actor_position: Vector3 = scene_root.to_local(actors[target_slot].get("last_global", Vector3.ZERO)) - actors[target_slot].get("render_offset", Vector3.ZERO); target = Vector3(-actor_position.x, -actor_position.y, actor_position.z) * 256.0 + relative_focus
	elif target_mode == 2: var local: Vector3 = scene_root.to_local(host.player.global_position); target = Vector3(-local.x, -local.y, local.z) * 256.0 + relative_focus
	target.y -= float(shake >> 8); shake = maxi(shake - shake_decay, 0)
	if eye_mode != 0:
		camera.position = _world([eye.x, eye.y, eye.z]); var point := _world([target.x, target.y, target.z])
		if point.distance_squared_to(camera.position) > 0.000001: camera.look_at(scene_root.to_global(point), Vector3.UP)
		if roll != 0: camera.rotate_object_local(Vector3.BACK, -float(roll) * TAU / 4096.0)
		camera.position += _world(render_offset); _constrain_camera(target + Vector3(render_offset[0], render_offset[1], render_offset[2]))
		return
	var yaw := float(orbit.x) * TAU / 4096.0; var pitch := float(orbit.y) * TAU / 4096.0; var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * orbit.z; var rotation := Basis(Vector3.RIGHT, pitch) * Basis(Vector3.UP, -yaw)
	var rows: Array[Vector3] = [Vector3(rotation.x.x, rotation.y.x, rotation.z.x), Vector3(rotation.x.y, rotation.y.y, rotation.z.y), Vector3(rotation.x.z, rotation.y.z, rotation.z.z)]
	camera.basis = Basis(Vector3(-rows[0].x, rows[1].x, rows[2].x), Vector3(-rows[0].y, rows[1].y, rows[2].y), Vector3(rows[0].z, -rows[1].z, -rows[2].z)).inverse(); camera.position = _world([target.x - offset.x, target.y - offset.y, target.z - offset.z])
	if roll != 0: camera.rotate_object_local(Vector3.BACK, -float(roll) * TAU / 4096.0)
	camera.position += _world(render_offset); _constrain_camera(target + Vector3(render_offset[0], render_offset[1], render_offset[2]))
func _constrain_camera(target: Vector3) -> void:
	if not camera_collision: return
	var focus_position := scene_root.to_global(_world([target.x, target.y, target.z])); var offset := camera.global_position - focus_position
	if offset.length_squared() <= 0.000001: return
	var query := PhysicsRayQueryParameters3D.create(focus_position, camera.global_position, 4); query.hit_back_faces = true; query.exclude = [host.player.get_rid()]
	var hit: Dictionary = camera.get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty(): camera.global_position = focus_position + offset.normalized() * maxf(focus_position.distance_to(hit["position"]) - maxf(camera.near * 2.0, 0.1), 0.0)
func _remove(slot: int) -> void:
	if not actors.has(slot): return
	var node: Variant = actors[slot]["node"]
	if is_instance_valid(node) and not bool(actors[slot].get("borrowed", false)): node.queue_free()
	actors.erase(slot)
func _activate_record(address: String) -> void:
	var record: Dictionary = records.get(address, {})
	if record.is_empty(): message_failed = true; return
	if not actors.has(int(record["slot"])):
		if not record["entry"].has("native_backdrop"): return
		var node := preload("res://scripts/cinematics/native_stage_backdrop.gd").new(); scene_root.add_child(node); node.configure(self, record["entry"]); actors[int(record["slot"])] = {"node": node, "clock": null, "record": record, "active": false, "head_target": 0, "head_speed": 0, "head_enabled": false, "flag_started": false, "fields": {}, "face_tables": {}, "face_dims": [0, 0, 0, 0], "face_surfaces": []}
	var slot := int(record["slot"]); actors[slot]["active"] = true; actors[slot]["node"].visible = true; var clock: NativeAnimation = actors[slot]["clock"]
	if clock != null: clock.play_control(int(callbacks.get("actor_controllers", {}).get(str(slot), {}).get("startup_control", 0)))
func _finish_scene() -> void:
	if finishing: return
	finishing = true
	var finish: Dictionary = callbacks["finish"]
	for operation: Dictionary in finish.get("ops", []):
		match str(operation["op"]):
			"play_sound_if_latched":
				if sound_latched: host.audio.play_sound(int(operation["id"]))
			"wait_xa_idle":
				while is_inside_tree() and is_instance_valid(xa) and xa.playing: await get_tree().process_frame
			"fade":
				if bool(operation.get("wait", true)): await _fade(int(operation["type"]))
				else: _fade(int(operation["type"]), false)
			_: _action(operation)
	if finish.has("fade_exit") and not faded: await host.transition_overlay.request(int(finish["fade_exit"]))
	for slot: int in actors.keys():
		var actor: Dictionary = actors[slot]; var node: Variant = actor["node"]
		if str(actor["record"]["source_ram"]).to_lower() in finish.get("retain_actor_records", []) and is_instance_valid(node):
			if node.get_parent() != host.level: node.reparent(host.level, true)
			actors.erase(slot)
		else: _remove(slot)
	for address: String in registration_records:
		var record: Dictionary = records.get(address, {})
		if record.is_empty(): running = false; completed.emit(false); return
		if record["model"] == null: continue
		var vendor: Node3D = await Props.spawn_entry(scene_root, stage, area, record["entry"], record["model"], host.native_context)
		if vendor == null: running = false; completed.emit(false); return
		vendor.set_meta("native_scene_registration", true)
		preload("res://scripts/world/rendering/native_material.gd").depth_cue(vendor, host.depth_cue_parameters)
	if finish.has("player_position_raw"): host.player.global_position = scene_root.to_global(_world(finish["player_position_raw"]))
	if finish.has("player_yaw_raw"): _set_yaw(host.player.player_model, int(finish["player_yaw_raw"]))
	host.player.camera.make_current(); camera.current = false
	if finish.has("fade_entry"): await host.transition_overlay.request(int(finish["fade_entry"]))
	transition_route = finish.get("transition", {}).duplicate(true)
	if transition_route.has("destination_transform_raw"):
		var raw: Array = transition_route["destination_transform_raw"]; transition_route["destination_transform"] = {"position": [float(raw[0]) / 256.0, float(raw[1]) / 256.0, float(raw[2]) / 256.0], "yaw_raw": int(raw[3]), "floor_height": int(raw[1]) == -1}
	running = false; completed.emit(true)
func _restore() -> void:
	_restore_shot_visibility()
	if host.player.motion_tree != null: host.player.motion_tree.active = saved_motion_active
	if host.player.upper_modifier != null: host.player.upper_modifier.set_source_aim_angles(0, 0)
	host.player.camera.make_current(); host.player.player_model.visible = true
	for surface: Dictionary in player_faces: (surface["material"] as ShaderMaterial).set_shader_parameter("uv_word", 0); (surface["material"] as ShaderMaterial).set_shader_parameter("albedo_texture", surface["texture"])
	if host.has_method("set_scene_presentation"): host.set_scene_presentation(false)
	for slot: int in actors.keys(): _remove(slot)
	if is_instance_valid(camera): camera.queue_free()
	if is_instance_valid(player_pose): player_pose.queue_free()
	_release_root()
	for node: Node3D in suppressed:
		if is_instance_valid(node): node.show()
	for entry: Dictionary in suppressed_streams:
		if is_instance_valid(entry["node"]): (entry["node"] as MeshInstance3D).set_surface_override_material(int(entry["surface"]), entry["material"])
	suppressed_streams.clear()
func _restore_shot_visibility() -> void:
	for node: Node3D in shot_suppressed:
		if is_instance_valid(node): node.show()
	shot_suppressed.clear()
func _release_root() -> void:
	if owns_root and is_instance_valid(scene_root): scene_root.queue_free()
	owns_root = false
func _area_change(operation: Dictionary) -> void:
	area_loading = true
	var success: bool = await host.native_scene_area(int(operation["area"]), operation["position_raw"], int(operation["facing_raw"]))
	area = int(operation["area"]); area_loading = false; message_failed = message_failed or not success
	if success: camera.make_current()
func _fade(code: int, wait := true) -> void:
	fade_busy = wait; faded = true
	await host.transition_overlay.request(code)
	if wait: fade_busy = false
func _label(program: Array, name: String) -> int:
	for index in range(program.size()):
		if str(program[index]["op"]) == "label" and str(program[index]["name"]) == name: return index
	message_failed = true; return program.size()
func _expression(value: Variant) -> int:
	if not value is String: return int(value)
	var total := 0; var sign := 1
	for token: String in str(value).replace("+", " + ").replace("-", " - ").split(" ", false):
		if token in ["+", "-"]: sign = 1 if token == "+" else -1; continue
		total += sign * (segment_tick if token == "tick" else answer if token == "answer" else token.hex_to_int() if token.begins_with("0x") else int(token))
	return total
func _flag_id(value: Variant) -> int: return _expression(value)
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _clear_flag(id: int) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id] = false; flags.erase(str(id)); host.native_context["event_flags"] = flags
func _prepare_voice_assets() -> bool:
	var descriptors: Dictionary = {}; var prepared: Dictionary = {}; var pending: Array = [callbacks]
	if callbacks.has("xa"): descriptors[int(callbacks["xa"]["descriptor_index"])] = true
	while not pending.is_empty():
		var value: Variant = pending.pop_back()
		if value is Array: pending.append_array(value)
		elif value is Dictionary:
			if str(value.get("op", "")) == "play_xa":
				if value.has("descriptor"): descriptors[int(value["descriptor"])] = true
				for id in value.get("descriptor_by_answer", []): descriptors[int(id)] = true
			elif str(value.get("op", "")) in ["music_prepare", "music_play"]: descriptors[int(value["id"])] = true; prepared[int(value["id"])] = true
			for child: Variant in value.values():
				if child is Dictionary or child is Array: pending.append(child)
	if descriptors.is_empty(): return true
	for path: String in ["res://assets/audio/common_voices/manifest.json", directory.path_join("audio/manifest.json")]:
		if not FileAccess.file_exists(path): continue
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not manifest is Dictionary: return false
		for entry: Dictionary in manifest.get("entries", []): xa_entries[int(entry["id"])] = entry
		if manifest.has("id") and manifest.has("file"): xa_entries[int(manifest["id"])] = manifest
	for id in descriptors:
		if not xa_entries.has(id) or not await AssetStore.ensure_voice(xa_entries[id]): return false
		if prepared.has(id):
			var stream: AudioStream = await host.audio._load_stream(str(xa_entries[id]["file"]))
			if stream == null: return false
			xa_streams[id] = stream
	return true
func _play_xa(id: int) -> void:
	var entry: Dictionary = xa_entries.get(id, {})
	if entry.is_empty(): message_failed = true; return
	if not await AssetStore.ensure_voice(entry) or not is_inside_tree(): message_failed = true; return
	var stream: AudioStream = xa_streams[id] if xa_streams.has(id) else await host.audio._load_stream(str(entry["file"]))
	if stream == null: message_failed = true; return
	if not is_instance_valid(xa): xa = AudioStreamPlayer.new(); xa.bus = "SFX" if AudioServer.get_bus_index("SFX") >= 0 else "Master"; add_child(xa)
	xa.stream = stream; xa.volume_db = 0.0; xa.play(); xa_ready_tick = -1; xa_answer = answer if id != int(callbacks.get("xa", {}).get("descriptor_index", -1)) else -1
func _fade_xa(speed: int) -> void:
	if not is_instance_valid(xa) or not xa.playing or speed <= 0: return
	var tween := create_tween(); tween.tween_property(xa, "volume_db", -60.0, 127.0 / float(speed) / float(data.get("native_tick_hz", 25))); tween.tween_callback(xa.stop)
func _xa_tick() -> void:
	if is_instance_valid(xa) and xa.playing and xa_ready_tick < 0 and xa.get_playback_position() > 0.0: xa_ready_tick = total_tick
func _interpolate() -> void:
	if not interpolations.has("focus"):
		if target_mode == 0: focus += focus_velocity
		else: relative_focus += focus_velocity
	if not interpolations.has("view"):
		if eye_mode == 0: orbit += orbit_velocity
		else: eye += eye_velocity
	for channel: String in interpolations.keys():
		var state: Dictionary = interpolations[channel]; var value: Vector3 = state["from"]; var tick := int(state["elapsed"]); var ticks := int(state["ticks"])
		if tick == ticks - 1: value = state["to"]
		elif tick > 0:
			for axis in range(3):
				var start := roundi(float(state["from"][axis]) * 65536.0); var end := roundi(float(state["to"][axis]) * 65536.0); var raw := 0
				match int(state["ease"]):
					1: raw = end if start == end else int(float((start >> 1) - (end >> 1)) / 4096.0) * int(trig[((tick << 11) / ticks) & 4095][1]) + (start >> 1) + (end >> 1)
					2: var ratio := ((tick - ticks) << 8) / ticks; raw = end if start == end else ((start - end) >> 8) * ((ratio * ratio) >> 8) + end
					3: var ratio := (tick << 8) / ticks; raw = start if start == end else ((end - start) >> 8) * ((ratio * ratio) >> 8) + start
					_: raw = int(float((ticks - tick) * (start >> 16) + tick * (end >> 16)) / float(ticks)) * 65536 + int(float((ticks - tick) * (start & 65535) + tick * (end & 65535)) / float(ticks))
				value[axis] = float(raw) / 65536.0
		if channel == "focus":
			if target_mode == 0: focus = value
			else: relative_focus = value
		elif eye_mode == 0: orbit = value
		else: eye = value
		state["elapsed"] = tick + 1
		if tick == ticks - 1: interpolations.erase(channel)
func _set_face(node: Node3D, table: String, channel: String, sequence: int) -> void:
	var source: Dictionary = data.get("face_tables", {}).get(table, {}); var sequences: Array = source.get("sequences", [])
	if sequence < 0 or sequence >= sequences.size(): return
	faces["%d:%s" % [node.get_instance_id(), channel]] = {"node": node, "channel": channel, "entries": sequences[sequence]["entries"], "index": 0, "ticks": 0, "held": false}
func _face_tick() -> void:
	for key: String in faces.keys():
		var state: Dictionary = faces[key]
		if not is_instance_valid(state["node"]): faces.erase(key); continue
		var node: Node3D = state["node"]
		if bool(state["held"]): continue
		var entries: Array = state["entries"]; var entry: Dictionary = entries[int(state["index"])]
		node.set_meta("native_face_" + str(state["channel"]), int(entry["frame"])); _apply_face(node, str(state["channel"]), int(entry["frame"])); state["ticks"] = int(state["ticks"]) + 1
		if int(state["ticks"]) < int(entry["ticks"]): continue
		state["ticks"] = 0
		match int(entry["op"]):
			1: state["held"] = true
			2: state["index"] = 0
			4: state["index"] = clampi(int(state["index"]) + int(entry["arg"]), 0, entries.size() - 1)
			_: state["index"] = mini(int(state["index"]) + 1, entries.size() - 1)
func _track(node: Node3D, keyframes: Array, step: int) -> void:
	var previous: Dictionary = {}; var following: Dictionary = {}
	for frame: Dictionary in keyframes:
		if int(frame["step"]) < step or (int(frame["step"]) == step and int(frame["tick"]) <= segment_tick): previous = frame
		elif following.is_empty(): following = frame
	if previous.is_empty(): return
	var position: Array = previous["position_raw"]; var yaw := int(previous["yaw_raw"])
	if not following.is_empty() and int(following["step"]) == step and int(previous["step"]) == step and int(following["tick"]) > int(previous["tick"]):
		var t := float(segment_tick - int(previous["tick"])) / float(int(following["tick"]) - int(previous["tick"])); var target: Array = following["position_raw"]
		position = [lerpf(float(position[0]), float(target[0]), t), lerpf(float(position[1]), float(target[1]), t), lerpf(float(position[2]), float(target[2]), t)]
		yaw = (yaw + roundi(float(((int(following["yaw_raw"]) - yaw + 2048) & 4095) - 2048) * t)) & 4095
	node.position = _world(position); _set_yaw(node, yaw)
func _floor_follow(node: Node3D, reference: float, bounds: Array) -> void:
	if bounds.size() != 6: return
	var origin := Vector3(node.global_position.x, reference, node.global_position.z); var hit: Dictionary = preload("res://scripts/world/actors/native_actor_motion.gd").ray(node, origin + Vector3.UP * (-float(bounds[2]) / 256.0 + 0.125), Vector3(origin.x, minf(host.bounds.position.y, origin.y) - 0.125, origin.z))
	if not hit.is_empty() and (hit["normal"] as Vector3).y > 0.0: node.global_position.y = (hit["position"] as Vector3).y
func _unhandled_input(event: InputEvent) -> void:
	if not running or finishing or not event.is_action_pressed("ui_cancel"): return
	get_viewport().set_input_as_handled()
	if not skip_locked: skip_requested = true; _skip_scene()
func _skip_scene() -> void:
	var skip: Dictionary = callbacks.get("finish", {}).get("skip_path", {})
	if skip.is_empty() or scene_flags & 4 or area_loading or fade_busy or bool(host.dialogue_box.get("active")): return
	faded = true; finishing = true; await host.transition_overlay.request(int(skip["fade"])); finishing = false; _finish_scene()
func _face_surfaces(node: Node3D, definitions: Array) -> Array:
	var result: Array = []; var meshes: Array[Node] = node.find_children("*", "MeshInstance3D", true, false)
	if meshes.is_empty(): return result
	var mesh := meshes[0] as MeshInstance3D
	for source: Dictionary in definitions:
		if not int(source["uv_stream"]) in [1, 2] or int(source["surface"]) >= mesh.mesh.get_surface_count(): continue
		var material := mesh.get_active_material(int(source["surface"])) as ShaderMaterial
		if material != null: result.append({"stream": int(source["uv_stream"]), "material": material})
	return result
func _player_face_setup() -> void:
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/manifest.json")); var page_path := directory.path_join("player_face_page1.png")
	player_face_page = load(page_path) as Texture2D if ResourceLoader.exists(page_path) else null
	var meshes: Array[Node] = host.player.player_model.find_children("*", "MeshInstance3D", true, false)
	if not manifest is Dictionary or meshes.is_empty(): return
	var mesh := meshes[0] as MeshInstance3D
	for source: Dictionary in manifest.get("faceSurfaces", []):
		var material := mesh.get_surface_override_material(int(source["surface"])) as ShaderMaterial if int(source["surface"]) < mesh.mesh.get_surface_count() else null
		if material != null: player_faces.append({"stream": int(source["uv_stream"]), "material": material, "texture": material.get_shader_parameter("albedo_texture")})
func _apply_face(node: Node3D, channel: String, frame: int) -> void:
	if node == host.player.player_model:
		var cell := frame % 20; var page := frame / 20
		for surface: Dictionary in player_faces:
			if int(surface["stream"]) != (1 if channel == "eyes" else 2): continue
			var material: ShaderMaterial = surface["material"]; material.set_shader_parameter("uv_word", (cell % 4) * 64 | ((cell / 4) * 51) << 8); material.set_shader_parameter("albedo_texture", player_face_page if page == 1 and player_face_page != null else surface["texture"])
		return
	for actor: Dictionary in actors.values():
		if actor["node"] != node: continue
		var stream := 1 if channel == "eyes" else 2; var dims: Array = actor["face_dims"]; var width := int(dims[0 if stream == 1 else 2]); var height := int(dims[1 if stream == 1 else 3])
		if width <= 0 or height <= 0: return
		var columns := 256 / width; var cell := frame % (columns * (256 / height))
		for surface: Dictionary in actor["face_surfaces"]:
			if int(surface["stream"]) == stream: (surface["material"] as ShaderMaterial).set_shader_parameter("uv_word", (cell % columns) * width | ((cell / columns) * height) << 8)
		return
