extends "res://scripts/world/actors/native_npc_behavior.gd"
class_name NativeTownNpc
var step := 0
var phase := 0
var wait_ticks := 0
var spin := 0.0
var pattern := 0
var pattern_steps := 0
var gesture_clip := 0
var record9 := 0
var head: SkeletonModifier3D
var skeleton: Skeleton3D
var look_mode := 0
var look_pitch := 0
var look_yaw := 0
var look_target_pitch := 0
var look_target_yaw := 0
var blocked_normal := Vector3.ZERO
var watch: Node3D
var record_raw := PackedByteArray()
func configure(target: Node3D, source_profile: Dictionary, context: Dictionary = {}) -> void:
	var walking: bool = bool(source_profile.get("walking", false)); var routes: Array = source_profile.get("routes", [])
	var chosen: Array = routes[int(source_profile.get("route", 0))] if walking and int(source_profile.get("route", -1)) >= 0 and int(source_profile.get("route", -1)) < routes.size() else []
	var adjusted := source_profile.duplicate(true); adjusted["nodes_raw"] = chosen; adjusted["source_route_index"] = 0; adjusted["animation_control"] = int(source_profile.get("animation_control", 1)) if walking else 0
	super.configure(target, adjusted, context)
	step = 0; phase = 0; idle_after_talk = false
	if not walking: pattern_steps = 0
	var source: Dictionary = actor.get_meta("native_actor_source", {}); var raw := str(source.get("source_bytes_hex", source.get("source_bytes", ""))); record9 = raw.substr(18, 2).hex_to_int() if raw.length() >= 40 else 0; record_raw = raw.hex_decode() if raw.length() >= 40 else PackedByteArray()
	skeleton = actor.find_child("Skeleton3D", true, false) as Skeleton3D
	if skeleton != null and skeleton.get_bone_count() > 1: head = preload("res://scripts/world/actors/native_head_look.gd").new(); skeleton.add_child(head)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(actor): return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func _native_tick() -> void:
	_state_tick(); _look_tick()
func _state_tick() -> void:
	_watch_tick()
	if talking or talk_return or idle_after_talk:
		look_mode = 2 if (record9 & 0x20) != 0 else 1
		if is_instance_valid(clock): clock.call("native_tick")
		if talk_return and is_instance_valid(clock) and (int(clock.get("record_flags")) & 128) != 0: talk_return = false; idle_after_talk = true; clock.call("play_control", 0, 0)
		if idle_after_talk and (not is_instance_valid(player) or not _player_in_front()): _resume()
		return
	if bool(profile.get("walking", false)):
		_walk_tick()
		if is_instance_valid(player) and _player_ahead(256.0, 512.0): _notice_player()
	else: _gesture_tick()
	if is_instance_valid(clock): clock.call("native_tick")
func _watch_tick() -> void:
	if record_raw.size() < 20 or record_raw[8] == record_raw[10]: return
	if not is_instance_valid(watch):
		watch = null
		for sibling: Node in actor.get_parent().get_children():
			var other := sibling as Node3D; var source: Dictionary = other.get_meta("native_actor_source", {}) if other != null else {}; var raw := str(source.get("source_bytes_hex", source.get("source_bytes", "")))
			if other == null or other == actor or raw.length() < 40 or raw.hex_decode()[4] != 0 or raw.hex_decode()[2] != 0x20 or raw.hex_decode()[8] != record_raw[10]: continue
			watch = other; break
		return
	var toward := watch.global_position - actor.global_position; var arc := _facing_delta(toward)
	if toward.length() * 256.0 < 0x200 and arc >= -0x100 and arc < 0x100: look_mode = 5
func _head_height(node: Node3D) -> float:
	var body := node.find_child("Skeleton3D", true, false) as Skeleton3D
	return (body.global_transform * body.get_bone_global_pose(1)).origin.y if body != null and body.get_bone_count() > 1 else node.global_position.y + 0.9
func _notice_player() -> void:
	idle_after_talk = true; look_mode = 2 if (record9 & 0x20) != 0 else 1
	if is_instance_valid(clock): clock.call("play_control", 0, 0)
func _player_ahead(range_raw: float, arc_raw: float) -> bool:
	var toward := player.global_position - actor.global_position
	return toward.length() * 256.0 < range_raw and absf(wrapf(atan2(toward.x, toward.z) + PI - actor.rotation.y, -PI, PI)) < arc_raw * TAU / 4096.0
func _facing_delta(toward: Vector3) -> int: return roundi(-wrapf(atan2(toward.x, toward.z) + PI - actor.rotation.y, -PI, PI) * 4096.0 / TAU)
func _yaw_toward(toward: Vector3) -> int: return clampi(_facing_delta(toward), -0x300, 0x300) >> 4
func _pitch_toward(target_y: float) -> int:
	var reach := roundi((target_y - ((skeleton.global_transform * skeleton.get_bone_global_pose(1)).origin.y if skeleton != null else actor.global_position.y + 0.9)) * 256.0)
	return -12 if reach > 0x40 else 12 if reach < -0x40 else 0
func _node_delta(offset_x := 0.0) -> Vector3:
	var node: Dictionary = nodes_raw[current_node]; return Vector3(-float(node["x"]) / 256.0 - actor.position.x, 0.0, float(node["z" if offset_x == 0.0 else "x"]) / 256.0 - actor.position.z)
func _reroll_look() -> void:
	if (record9 & 0x80) != 0: return
	match record9 & 7:
		0, 4: look_mode = 1
		1, 5: look_mode = [4, 1, 4, 1, 4, 4, 4, 1][next_random(native_context) & 7]
		2, 6: look_mode = [1, 2, 3, 2, 1, 2, 3, 2][next_random(native_context) & 7]
func _look_tick() -> void:
	if head == null or not is_instance_valid(player): return
	match look_mode:
		1: look_target_pitch = 0; look_target_yaw = 0
		2: look_target_yaw = _yaw_toward(player.global_position - actor.global_position); look_target_pitch = _pitch_toward(player.global_position.y + 0.9)
		3, 4:
			look_target_pitch = 0 if look_mode == 3 else _pitch_toward(actor.global_position.y); look_target_yaw = 0
			if not nodes_raw.is_empty():
				var arc := _facing_delta(_node_delta(1.0))
				if arc >= -0x100 and arc < 0x100: look_target_yaw = _yaw_toward(_node_delta())
		5, 6:
			if is_instance_valid(watch): look_target_yaw = _yaw_toward(watch.global_position - actor.global_position); look_target_pitch = _pitch_toward(_head_height(watch) if look_mode == 5 else actor.global_position.y)
		7: look_target_pitch = -12; look_target_yaw = 0
		8: look_target_pitch = 12; look_target_yaw = 0
	look_yaw += clampi(look_target_yaw - look_yaw, -6, 6); look_pitch += clampi(look_target_pitch - look_pitch, -2, 2); head.yaw_units = look_yaw * 16; head.pitch_units = look_pitch * 16
func _player_in_front() -> bool:
	var toward := player.global_position - actor.global_position; var yaw := atan2(toward.x, toward.z) + PI
	return Vector2(toward.x, toward.z).length() <= 384.0 / 256.0 and absf(wrapf(yaw - actor.rotation.y, -PI, PI)) <= 640.0 * TAU / 4096.0
func _resume() -> void:
	idle_after_talk = false; step = 0; phase = 0
	if is_instance_valid(clock): clock.call("play_control", int(profile.get("animation_control", 1)) if bool(profile.get("walking", false)) else 0, 0)
func _walk_tick() -> void:
	if nodes_raw.is_empty(): return
	match step:
		0: step = 1; phase = 0; _reroll_look(); _walk_forward()
		1: _walk_forward()
		2: _select_next_node(nodes_raw[current_node]); _advance(); step = 0; phase = 0
		3: _walk_blocked()
		4: _walk_wait()
func _advance() -> Dictionary:
	var velocity_raw := absi(int(profile.get("velocity_raw", -64))); var motion := Vector3(-sin(actor.rotation.y), 0.0, -cos(actor.rotation.y)) * float(velocity_raw) / 4096.0; var parent := actor.get_parent() as Node3D
	if parent != null: motion = parent.global_basis * motion
	return Motion.move_actor(actor, motion, profile.get("collision_bounds_raw", []))
func _walk_forward() -> void:
	if phase == 0:
		if is_instance_valid(clock): clock.call("play_control", int(profile.get("animation_control", 1)), 0)
		phase = 1
	var node: Dictionary = nodes_raw[current_node]; var native_x := -actor.position.x * 256.0; var native_z := actor.position.z * 256.0
	var direction := Vector3(-(float(node["x"]) - native_x), 0.0, float(node["z"]) - native_z)
	if direction.length_squared() > 0.0:
		var turn := float(profile.get("turn_step_raw", 24)) * TAU / 4096.0; actor.rotation.y += clampf(wrapf(atan2(direction.x, direction.z) + PI - actor.rotation.y, -PI, PI), -turn, turn)
	var result := _advance(); var after_x := -actor.position.x * 256.0; var after_z := actor.position.z * 256.0; var arrived := absf(float(node["x"]) - after_x) < 128.0 and absf(float(node["z"]) - after_z) < 128.0; var blocked := bool(result["blocked"])
	if arrived:
		var roll := next_random(native_context) & 31; step = 2; phase = 0
		if ((0x550000AA << roll) & 0x80000000) != 0 and bool(profile.get("idle_at_nodes", false)): _select_next_node(node); step = 4
	elif blocked: step = 3; phase = 0; blocked_normal = result.get("normal", Vector3.ZERO)
func _walk_blocked() -> void:
	if phase == 0:
		var away := Vector3(signf(blocked_normal.x) if absf(blocked_normal.x) >= 0.5 else 0.0, 0.0, signf(blocked_normal.z) if absf(blocked_normal.z) >= 0.5 else 0.0); phase = 1; spin = -1.0 if _facing_delta(away) >= 0 else 1.0
	var result := _advance(); actor.rotation.y += spin * float(profile.get("turn_step_raw", 24)) * 2.0 * TAU / 4096.0
	if not bool(result["blocked"]): step = 1; phase = 0
func _walk_wait() -> void:
	if phase == 0:
		if is_instance_valid(clock): clock.call("play_control", 0, 0)
		var timers: Array = profile.get("idle_timer_ticks", [180]); wait_ticks = int(timers[next_random(native_context) & 15 if timers.size() >= 16 else 0]); phase = 1
	wait_ticks -= 1
	if wait_ticks <= 0: idle_after_talk = true; step = 0; phase = 0
func _gesture_tick() -> void:
	var patterns: Array = profile.get("gesture_patterns", [])
	if patterns.is_empty() or not is_instance_valid(clock): return
	match step:
		0: look_mode = [5, 8, 5, 7, 5, 7, 6, 8][next_random(native_context) & 7]; next_random(native_context); pattern = int(patterns[next_random(native_context) & 3]); pattern_steps = 16; step = 1
		1: gesture_clip = 3 if (pattern & 0x8000) != 0 else 0; clock.call("play_control", gesture_clip, 0, true); step = 2
		2:
			if (int(clock.get("record_flags")) & 128) == 0: return
			if gesture_clip == 3: gesture_clip = 5; clock.call("play_control", 5, 0, true); return
			pattern = (pattern << 1) & 0xFFFF; pattern_steps -= 1; step = 0 if pattern_steps <= 0 else 1
