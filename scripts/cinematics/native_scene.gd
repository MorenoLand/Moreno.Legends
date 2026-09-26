extends Node
signal completed(success: bool)
const Props := preload("res://scripts/world/native_props.gd")
const Facing := preload("res://scripts/world/native_talk_facing.gd")
var host: Node3D
var scene_root: Node3D
var data: Dictionary = {}
var callbacks: Dictionary = {}
var directory := ""
var stage := ""
var area := 0
var camera: Camera3D
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
var trig: Array = []
var xa: AudioStreamPlayer
var transition_route: Dictionary = {}
var suppressed: Array[Node3D] = []
func configure(gameplay: Node3D, level: Node3D, path: String, requested_area: int = -1) -> bool:
	host = gameplay; scene_root = level; directory = path.get_base_dir()
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary: return false
	data = parsed.get("branches", {}).get(str(requested_area), {}) if parsed.has("branches") else parsed
	if data.is_empty(): return false
	stage = str(data["stage"]); area = int(data["area"])
	var callback_path: String = directory.path_join(str(data["callback_contract_file"]))
	if not FileAccess.file_exists(callback_path): return false
	var contract: Variant = JSON.parse_string(FileAccess.get_file_as_string(callback_path))
	if not contract is Dictionary: return false
	callbacks = contract
	var weather: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/weather/manifest.json"))
	if weather is Dictionary: trig = weather.get("trig4096", [])
	if trig.size() != 4096: return false
	for record: Dictionary in data.get("actors", []): records[str(record["source_ram"]).to_lower()] = record
	for entry: Dictionary in data.get("timeline", []):
		if not callbacks.get("segments", {}).has("%d:%d" % [int(entry["phase"]), int(entry["step"])]): return false
	camera = Camera3D.new(); camera.name = "NativeSceneCamera"; camera.near = host.player.camera.near; camera.far = host.player.camera.far; camera.fov = rad_to_deg(2.0 * atan(120.0 / 384.0)); scene_root.add_child(camera)
	player_clock = preload("res://scripts/world/native_animation.gd").new(); player_clock.automatic = false; add_child(player_clock)
	var clips: Array = []
	for clip: Dictionary in host.player.native_clips.values():
		if str(clip["name"]) != "clip_%03d" % int(clip.get("slot", -1)): continue
		var adapted: Dictionary = clip.duplicate(true)
		for name: StringName in host.player.animation_player.get_animation_list():
			if str(name).get_file() == str(clip["name"]): adapted["name"] = str(name); break
		clips.append(adapted)
	if not player_clock.configure(host.player.animation_player, clips): camera.queue_free(); return false
	return true
func run() -> bool:
	saved_motion_active = host.player.motion_tree.active if host.player.motion_tree != null else false
	if host.player.motion_tree != null: host.player.motion_tree.active = false
	host.player.velocity = Vector3.ZERO; host.player.set_physics_process(false)
	var initial: Dictionary = callbacks["initialization"]; host.player.global_position = scene_root.to_global(_world(initial["player_position_raw"])); _set_yaw(host.player.player_model, int(initial["player_yaw_raw"])); head_units = 0
	if initial.has("music_cue"): host.audio.play_sound(int(initial["music_cue"]))
	for placement: int in initial.get("suppress_placements", []):
		for node: Node3D in scene_root.find_children("placement_%03d_*" % placement, "Node3D", true, false): node.hide(); suppressed.append(node)
	if host.player.upper_modifier != null: host.player.upper_modifier.track_target = false; host.player.upper_modifier.set_source_aim_angles(0, 0)
	for record: Dictionary in records.values():
		if str(record["source_ram"]).to_lower() == str(callbacks["finish"].get("registration_record", "")): continue
		var node: Node3D = await Props.spawn_entry(scene_root, stage, area, record["entry"], record["model"], host.native_context)
		if node == null: _restore(); return false
		var clock := node.get_node_or_null("NativeAnimationClock") as NativeAnimation
		if clock != null: clock.automatic = false
		var direct: bool = str(record["source_ram"]) in initial.get("spawn_records", []); node.visible = direct; actors[int(record["slot"])] = {"node": node, "clock": clock, "record": record, "active": direct, "head_target": 0, "head_speed": 0, "head_enabled": false, "flag_started": false}
	if callbacks.has("xa"):
		var audio_path := directory.path_join("audio/manifest.json")
		if not FileAccess.file_exists(audio_path): _restore(); return false
		var audio: Variant = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		if not audio is Dictionary or int(audio.get("id", -1)) != int(callbacks["xa"]["descriptor_index"]): _restore(); return false
		var stream: AudioStream = await host.audio._load_stream(str(audio["file"]))
		if stream == null: _restore(); return false
		xa = AudioStreamPlayer.new(); xa.stream = stream; xa.bus = "SFX" if AudioServer.get_bus_index("SFX") >= 0 else "Master"; add_child(xa); xa.play()
		while is_inside_tree() and xa.get_playback_position() <= 0.0: await get_tree().process_frame
	camera.make_current(); running = true; _commands(); segment_tick = 1; phase_tick = 1; total_tick = 1; _camera_update()
	var success: bool = await completed
	_restore(); return success
func _process(delta: float) -> void:
	if not running or finishing: return
	elapsed += delta * float(data.get("native_tick_hz", 25))
	while elapsed >= 1.0 and running and not finishing:
		elapsed -= 1.0; native_tick()
func native_tick() -> void:
	if message_failed: running = false; completed.emit(false); return
	var profile: Dictionary = _profile()
	for sound: Dictionary in profile.get("sounds", []):
		if int(sound["tick"]) == segment_tick: host.audio.play_at(int(sound["id"]), scene_root.to_global(_world(sound["position_raw"])))
	for action: Dictionary in profile.get("actions", []):
		if int(action["tick"]) == segment_tick: _action(action)
	for motion: Dictionary in profile.get("motion", []):
		if _motion_active(motion): _motion(host.player, host.player.player_model, motion)
	_program(profile.get("program", []))
	if not running or finishing: return
	_commands(); _head_tick(); player_clock.native_tick(); segment_tick += 1; phase_tick += 1; total_tick += 1
	var duration := int(data["timeline"][segment]["duration"])
	if duration >= 0 and segment_tick == duration: _advance()
	if not running or finishing: return
	_actor_tick(); _camera_update()
func _profile() -> Dictionary:
	var entry: Dictionary = data["timeline"][segment]; return callbacks["segments"]["%d:%d" % [int(entry["phase"]), int(entry["step"])]]
func _program(program: Array) -> void:
	while program_index < program.size():
		var operation: Dictionary = program[program_index]; var op := str(operation["op"])
		if not operation_started:
			operation_started = true; operation_tick = segment_tick
			if operation.has("state"): director_state = int(operation["state"])
			if op in ["message", "message_start"]: _message(int(operation["index"]))
			elif op not in ["message_wait", "minimum_tick", "delay", "turn_wait", "advance", "finish"]: _action(operation)
		if message_failed: return
		if op in ["message", "message_wait"] and message_busy: return
		if op == "delay" and segment_tick - operation_tick < int(operation["ticks"]): return
		if op == "minimum_tick" and segment_tick < int(operation["tick"]): return
		if op == "turn_wait" and _turn(host.player.player_model, int(operation["heading"]), int(operation["speed"])) != 0: return
		if op == "advance": _advance(); return
		if op == "finish": _finish_scene(); return
		program_index += 1; operation_started = false
func _message(index: int) -> void:
	message_busy = true
	var success: bool = await host.event_script.play_bound_message(stage, "0x8010C000", index, "0x80048474")
	message_busy = false; message_failed = message_failed or not success
func _action(action: Dictionary) -> void:
	match str(action["op"]):
		"player_control": player_clock.play_control(int(action["control"]), int(action.get("start_record", 0)))
		"head_target": head_target = int(action["target"]); head_speed = int(action["speed"])
		"event_set":
			var flags: Dictionary = host.native_context.get("event_flags", {}); flags[int(action["id"])] = true; host.native_context["event_flags"] = flags
		"despawn":
			var record: Dictionary = records.get(str(action["record"]).to_lower(), {})
			if not record.is_empty(): _remove(int(record["slot"]))
func _advance() -> void:
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
		var total_yaw: Dictionary = profile.get("total_yaw_increment", {})
		if not total_yaw.is_empty() and total_tick >= int(total_yaw["from_tick"]) and total_tick <= int(total_yaw["through_tick"]): _set_yaw(node, (_yaw(node) + mini(total_tick >> int(total_yaw["shift"]), int(total_yaw["maximum"])) * int(total_yaw["sign"])) & 4095)
		for event: Dictionary in profile.get("events", []):
			if int(event["step"]) != step: continue
			if event.has("tick") and int(event["tick"]) != segment_tick: continue
			if event.has("state") and int(event["state"]) != director_state: continue
			match str(event["op"]):
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
		if clock != null: clock.native_tick()
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
			21, 22:
				if _fixed(words) != Vector3.ZERO: message_failed = true; return
			32, 33, 34: camera.set_meta("native_depth_cue_mode", opcode - 32)
			64:
				var record: Dictionary = records.get(str(command.get("actor_record", {}).get("source_ram", "")).to_lower(), {})
				if record.is_empty(): record = records.get("0x%08x" % int(words[1]), {})
				if record.is_empty(): message_failed = true; return
				var slot := int(record["slot"])
				if not actors.has(slot): message_failed = true; return
				actors[slot]["active"] = true; actors[slot]["node"].visible = true
				var clock: NativeAnimation = actors[slot]["clock"]
				if clock != null: clock.play_control(int(callbacks.get("actor_controllers", {}).get(str(slot), {}).get("startup_control", 0)))
			65:
				var record: Dictionary = records.get("0x%08x" % int(words[1]), {})
				if not record.is_empty(): _remove(int(record["slot"]))
			255: return
			_: message_failed = true; return
func _fixed(words: Array) -> Vector3: return Vector3(_s32(int(words[1])), _s32(int(words[2])), _s32(int(words[3]))) / 65536.0
func _s32(value: int) -> int: return (value & 2147483647) - (value & 2147483648)
func _camera_update() -> void:
	var target := focus
	if target_mode == 1 and actors.has(target_slot): target = Vector3(-actors[target_slot]["node"].position.x, -actors[target_slot]["node"].position.y, actors[target_slot]["node"].position.z) * 256.0 + relative_focus
	elif target_mode == 2: var local: Vector3 = scene_root.to_local(host.player.global_position); target = Vector3(-local.x, -local.y, local.z) * 256.0 + relative_focus
	if eye_mode != 0:
		camera.position = _world([eye.x, eye.y, eye.z]); var point := _world([target.x, target.y, target.z])
		if point.distance_squared_to(camera.position) > 0.000001: camera.look_at(scene_root.to_global(point), Vector3.UP)
		return
	var yaw := float(orbit.x) * TAU / 4096.0; var pitch := float(orbit.y) * TAU / 4096.0; var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * orbit.z; var rotation := Basis(Vector3.RIGHT, pitch) * Basis(Vector3.UP, -yaw)
	var rows: Array[Vector3] = [Vector3(rotation.x.x, rotation.y.x, rotation.z.x), Vector3(rotation.x.y, rotation.y.y, rotation.z.y), Vector3(rotation.x.z, rotation.y.z, rotation.z.z)]
	camera.basis = Basis(Vector3(-rows[0].x, rows[1].x, rows[2].x), Vector3(-rows[0].y, rows[1].y, rows[2].y), Vector3(rows[0].z, -rows[1].z, -rows[2].z)).inverse(); camera.position = _world([target.x - offset.x, target.y - offset.y, target.z - offset.z])
func _remove(slot: int) -> void:
	if not actors.has(slot): return
	var node: Node3D = actors[slot]["node"]
	if is_instance_valid(node): node.queue_free()
	actors.erase(slot)
func _finish_scene() -> void:
	if finishing: return
	finishing = true
	var finish: Dictionary = callbacks["finish"]
	if finish.has("fade_exit"): await host.transition_overlay.request(int(finish["fade_exit"]))
	for slot: int in actors.keys(): _remove(slot)
	if finish.has("registration_record"):
		var record: Dictionary = records.get(str(finish["registration_record"]).to_lower(), {})
		if record.is_empty(): running = false; completed.emit(false); return
		var vendor: Node3D = await Props.spawn_entry(scene_root, stage, area, record["entry"], record["model"], host.native_context)
		if vendor == null: running = false; completed.emit(false); return
		preload("res://scripts/world/native_material.gd").depth_cue(vendor, host.depth_cue_parameters)
	if finish.has("player_yaw_raw"): _set_yaw(host.player.player_model, int(finish["player_yaw_raw"]))
	host.player.camera.make_current(); camera.current = false
	if finish.has("fade_entry"): await host.transition_overlay.request(int(finish["fade_entry"]))
	transition_route = finish.get("transition", {}).duplicate(true)
	running = false; completed.emit(true)
func _restore() -> void:
	if host.player.motion_tree != null: host.player.motion_tree.active = saved_motion_active
	if host.player.upper_modifier != null: host.player.upper_modifier.set_source_aim_angles(0, 0)
	host.player.camera.make_current()
	for slot: int in actors.keys(): _remove(slot)
	if is_instance_valid(camera): camera.queue_free()
	for node: Node3D in suppressed:
		if is_instance_valid(node): node.show()
