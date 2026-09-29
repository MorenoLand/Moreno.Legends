extends Node
var host: Node
var actor: Node3D
var source: Dictionary = {}
var points: Array = []
var clock: NativeAnimation
var elapsed := 0.0
var waypoint := 0
var native_yaw := 0
var finished := false
var metadata: Dictionary = {}
var dialogue_wait := false
func configure(gameplay: Node, target: Node3D, entry: Dictionary, model: Dictionary) -> void:
	host = gameplay; actor = target; source = entry; metadata = model; native_yaw = int(entry.get("transform_raw", [0, 0, 0, 0])[3]); clock = actor.find_child("NativeAnimationClock", true, false) as NativeAnimation
	var path := "res://assets/levels/ST0F/mine_quest.json"; var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if parsed is Dictionary: points = parsed.get("roll_routes", {}).get(str(entry.get("source_record_ram", "")).to_lower(), {}).get("points_raw", [])
	finished = points.is_empty(); _control(0); _configure_talk(parsed.get("roll_target", {}) if parsed is Dictionary else {})
func _configure_talk(profile: Dictionary) -> void:
	var binding: Dictionary = actor.get_meta("native_interaction", {}); var raw := str(source.get("source_bytes_hex", "")).hex_decode()
	if raw.size() != 20: return
	binding.merge({"stage": "ST0F", "bank_id": "0x8010C000", "message_index": int(raw[11]), "message_call": "0x800BDCF8", "request_call": "0x800F1420", "request_kind": 0x12 if (raw[10] & 128) != 0 else 2, "actor_callback": "0x800F10B8", "target_flags60": 1, "target_descriptor_raw": profile.get("bounds_raw", []), "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": true, "line_of_sight": false}}, true); actor.set_meta("native_interaction", binding); actor.add_to_group("native_interaction_targets")
func _physics_process(delta: float) -> void:
	if finished or not is_instance_valid(actor): return
	if bool(host.dialogue_box.get("active")):
		if not dialogue_wait: dialogue_wait = true; _control(0)
		return
	dialogue_wait = false
	if not host.preparation_finished or not host.playable or host.loading or host.native_scenes.active or not host.player.is_physics_processing() or not actor.is_visible_in_tree(): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and not finished: elapsed -= 1.0; _tick()
func _tick() -> void:
	if waypoint >= points.size(): finished = true; _control(0); return
	var point: Array = points[waypoint]
	if int(point[1]) < 0:
		_control(0); var difference := _turn(int(point[3]), 128)
		if absi(difference) < 56: finished = true
		return
	var local := actor.position; var native_x := roundi(-local.x * 256.0); var native_z := roundi(local.z * 256.0)
	if absi(native_x - int(point[0])) < 32 and absi(native_z - int(point[2])) < 32:
		waypoint += 1
		if waypoint >= points.size(): finished = true; _control(0); return
		point = points[waypoint]
		if int(point[1]) < 0: _control(0); return
	var destination := Vector3(-float(point[0]) / 256.0, local.y, float(point[2]) / 256.0); var yaw := preload("res://scripts/world/actors/native_talk_facing.gd")._heading(local, destination); _turn(yaw, 56); _control(2); var heading := float(native_yaw) * TAU / 4096.0; var movement := Vector3(-sin(heading), 0, cos(heading)) * -608.0 / 4096.0; preload("res://scripts/world/actors/native_actor_motion.gd").move_actor(actor, movement, source["native_hitbox"]["bounds_raw"])
func _turn(yaw: int, maximum: int) -> int:
	var difference := ((yaw - native_yaw + 2048) & 4095) - 2048; native_yaw = (native_yaw + clampi(difference, -maximum, maximum)) & 4095; actor.rotation.y = -float(native_yaw) * TAU / 4096.0; return difference
func _control(code: int) -> void:
	if is_instance_valid(clock): clock.play_control(code)
