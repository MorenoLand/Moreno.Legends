extends "res://scripts/world/actors/stage_actor.gd"
signal gone(actor: CharacterBody3D)
var spawner: Node
var rules: Dictionary = {}
var ground_height := 0.0
var offscreen := false
var protected := true
var circle_flag := 0
var leave_counter := 30
func configure_popup(owner: Node, entry: Dictionary, metadata: Dictionary, directory: String, rule_values: Dictionary, floor_height: float) -> void:
	spawner = owner; rules = rule_values; ground_height = floor_height; configure(entry, metadata, directory); native_state = 100; initialized = false; collision_layer = 0; position.y = ground_height - float(rules["rise_depth_raw"]) / 256.0
func can_lift() -> bool: return native_state < 100 and super.can_lift()
func _register_contact() -> void:
	if native_state < 100: super._register_contact()
func _class_five_tick() -> void:
	if native_state >= 100: _popup_tick(); return
	if native_state == 4: _wander_tick()
	else:
		if native_state == 7: spawner.gate_claim()
		super._class_five_tick()
	_leave_check()
func _popup_tick() -> void:
	match native_state:
		100:
			if not initialized: initialized = true; sound_requested.emit(int(rules["rise_sound"]), global_position)
			position.y = minf(position.y + float(rules["rise_step_raw"]) / 256.0, ground_height)
			if control_ended: _set_state(101)
		101:
			_turn(_angle_from(target.global_position), 32); position.y = ground_height; protected = false; circle_flag = _next_random() & 1; leave_counter = int(rules["leave_ticks"]); collision_layer = 8; add_to_group("lock_targets"); _set_state(3)
		102:
			if not initialized: initialized = true; collision_layer = 0; remove_from_group("lock_targets"); remove_from_group("lift_targets"); protected = true; ground_height = _floor_height(); play_control(4); sound_requested.emit(int(rules["leave_sound"]), global_position)
			position.y -= float(rules["leave_step_raw"]) / 256.0
			if position.y < ground_height - float(rules["rise_depth_raw"]) / 256.0: removed = true; gone.emit(self); queue_free()
func _wander_tick() -> void:
	var distance := global_position.distance_to(target.global_position) * 256.0
	if not initialized: initialized = true; play_control(1)
	var desired := _angle_from(target.global_position)
	if distance < 500.0: desired = -desired
	elif distance < 700.0: desired += 1024 if (circle_flag & 1) != 0 else -1024
	native_speed = mini(native_speed + 16, -384) if native_speed < -384 else maxi(native_speed - 16, -384)
	_turn(desired, 32); _move_native(native_speed)
	if cooldown > 0: cooldown -= 1
	if cooldown == 0 and ((0x2c0 >> (_next_random() & 15)) & 1) and distance < float(rules["attack_distance_raw"]) and not offscreen and not spawner.gate_blocked(): spawner.gate_claim(); _set_state(7)
func _leave_check() -> void:
	if offscreen or dying or thrown or native_state == 1 or not is_instance_valid(target): return
	var offset := global_position - target.global_position
	if Vector2(offset.x, offset.z).length() * 256.0 <= float(rules["leave_distance_raw"]): leave_counter = int(rules["leave_ticks"]); return
	leave_counter -= 1
	if leave_counter <= 0: _set_state(102)
func _floor_height() -> float:
	var query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 1.125, global_position - Vector3.UP * 2.0, 1, [get_rid()]); var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return float(hit["position"].y) - (get_parent() as Node3D).global_position.y if not hit.is_empty() else ground_height
