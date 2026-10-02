extends "res://scripts/world/enemies/native_icefield_enemy.gd"
signal defeated(actor: CharacterBody3D)
var step2 := 0
var side := 0
var gravity := 0
var jump_state := 0
var jump_apex := 0
var wall := false
var timer_a := 0
var timer_b := 0
var bits := 0x70
var inert := false
var hit_yaw := 0
var knock_yaw := 0
var distance_raw := 0
var last_move := {}
var scene_mode := false
var scene_step := 0
var scene_tick := 0
var animation_on := true
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry, metadata, path): return false
	scene_mode = int(entry.get("dispatch_index", 0)) == 1; var armed := scene_mode or int(entry["native_private_raw"][0]) != 0
	top = 1; sub = 0 if armed else 1; control = 1 if armed else 3; control_at_start = control; clock.play_control(control, 0, true)
	var capsule := shape.shape as CapsuleShape3D; capsule.radius = 0.25; capsule.height = 1.0; shape.rotation.x = PI / 2.0; shape.position = Vector3(0.0, 0.25, 0.0)
	var floor_hit := Motion.ray(self, global_position + Vector3.UP * 0.5, global_position - Vector3.UP * 60.0)
	if not floor_hit.is_empty(): global_position.y = (floor_hit["position"] as Vector3).y
	distance_raw = int(_distance()); add_to_group("lock_targets"); return true
func _run() -> void:
	if scene_mode: _scene_run(); return
	if top == 2: _finish(); return
	if health >= 0 and (bits & 0x10) != 0: _damage()
	match sub:
		0: _intro()
		1: _pursue()
		2: _strafe()
		3: _wall_turn()
		4: _knockback()
		6: _leap()
		7: _howl()
		8: _death()
	_post()
	if clock.event_code != 0: _sound(0x16B)
	_register_hits()
	distance_raw = int(_distance())
func _finish() -> void:
	defeated.emit(self); super()
func native_tick(fields: Dictionary) -> void:
	scene_step = int(fields.get("scene_step", 0)); scene_tick = int(fields.get("scene_tick", 0))
	if visible: _tick()
func _animate() -> void:
	if scene_mode and not animation_on and control == control_at_start: return
	super()
func _scene_run() -> void:
	match sub:
		0:
			if scene_step == 3 and scene_tick == 0xA0: control = 0; sub = 1
		1:
			match scene_tick:
				0xBE: control = 4
				0xD1: animation_on = false
				0xE5: animation_on = true
				0x104: sub = 2; step = 0
		2:
			if _scene_jump(): control = 0x20; speed = -0x300; sub = 3
		3:
			_move(native_yaw, 0, speed)
			if clock.event_code != 0: _sound(0x16B)
	if airborne:
		if bool(last_move.get("grounded", false)): airborne = false
	else:
		var ground := Motion.ray(self, global_position + Vector3.UP, global_position - Vector3.UP * 8.0)
		if not ground.is_empty() and (ground["normal"] as Vector3).y > 0.0 and (ground["position"] as Vector3).y >= global_position.y - 16.0 / 256.0: global_position.y = (ground["position"] as Vector3).y
	last_move = {}
func _scene_jump() -> bool:
	match jump_state:
		0: _sound(0x16C); control = 0xF; airborne = true; jump_state = 1; vertical = -0x140; speed = -0x200; gravity = 0x40; _move(native_yaw, vertical, speed)
		1:
			if vertical > 0: control = 0x10; jump_state = 2
			_move(native_yaw, vertical, speed); vertical += gravity
		2:
			if not airborne: _sound(0x170); control = 0x11; jump_state = 3
			else: _move(native_yaw, vertical, speed); vertical += gravity
		3: return _ended()
	return false
func _ended() -> bool: return (clock.record_flags & 128) != 0
func _enter(value: int) -> void: sub = value; step = 0; step2 = 0
func receive_hit(damage: int, hit_flags: int, direction: Vector3 = Vector3.ZERO) -> bool:
	if not super(damage, hit_flags, direction): return false
	hit_yaw = roundi(atan2(direction.x, -direction.z) * 4096.0 / TAU) & 4095 if direction.length_squared() > 0.0001 else (_bearing() + 2048) & 4095
	return true
func _hurt(damage: int) -> bool:
	health -= damage
	if health < 0: health = -1; return true
	health = mini(health, max_health); return false
func _damage() -> void:
	var word := hit_word; var damage := hit_damage & 0xFFF
	if (word & 0x1C0000) != 0:
		_set_light(248.0)
		if _hurt(damage):
			if (bits & 2) == 0: sub = 8; step = 0; bits |= 2; return
		elif damage >= int(attributes[8]): _sound(0x8E); knock_yaw = hit_yaw; sub = 4; step = 0; return
		else: _sound(0x8D)
	if (bits & 0x10) != 0 and (word & 0x7000000) != 0 and (word & 0x400000) != 0:
		if _hurt(damage):
			if (bits & 6) == 0: sub = 8; step = 0; bits |= 2
		else: sub = 4; step = 0
func _move(yaw: int, vertical_raw: int, forward_raw: int) -> void:
	var heading := float(yaw) * TAU / 4096.0
	var result := Motion.move_actor(self, Vector3(-sin(heading) * float(forward_raw), -float(vertical_raw), cos(heading) * float(forward_raw)) / 4096.0, bounds)
	last_move = {"blocked": bool(last_move.get("blocked", false)) or bool(result.get("blocked", false)), "grounded": bool(last_move.get("grounded", false)) or bool(result.get("grounded", false))}
func _post() -> void:
	wall = bool(last_move.get("blocked", false)) and not bool(last_move.get("grounded", false))
	if airborne:
		if bool(last_move.get("grounded", false)): airborne = false
	else:
		var ground := Motion.ray(self, global_position + Vector3.UP, global_position - Vector3.UP * 8.0)
		if not ground.is_empty() and (ground["normal"] as Vector3).y > 0.0: global_position.y = (ground["position"] as Vector3).y
	last_move = {}
func _register_hits() -> void:
	hit_word = 0; hit_damage = 0; collision_layer = 8
	if inert: return
	var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape.shape; query.transform = shape.global_transform; query.collision_mask = target.collision_layer; query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(self, int(attributes[1]), 0xA0000); return
func _on_screen() -> bool:
	var camera := get_viewport().get_camera_3d()
	if camera == null: return true
	return not camera.is_position_behind(global_position) and get_viewport().get_visible_rect().has_point(camera.unproject_position(global_position))
func _angle_difference(from: int, to: int) -> int: return ((to - from + 2048) & 4095) - 2048
func _aim(speed_value: int, gravity_value: int, limit: int) -> int:
	var numerator := mini(int(_distance()), limit) << 16; var denominator := speed_value << 12
	if denominator == 0 or numerator == 0: return -speed_value
	var ticks := numerator / denominator
	if ticks == 0: return -speed_value
	var delta := int((global_position.y - target.global_position.y) * -256.0 * 65536.0)
	return -((delta / ticks + (((gravity_value << 12) * ticks) >> 1)) >> 12)
func _jump(alternate: bool) -> bool:
	match jump_state:
		0:
			control = 0xF if alternate else 0xC; _sound(0x16C); airborne = true; jump_state = 1; jump_apex = 0; bits &= 0xBF; _move(native_yaw, vertical, speed)
		1:
			if jump_apex == 0 and vertical > 0: control = 0x10 if alternate else 0xD; jump_apex = 1
			if not airborne: control = 0xE; _sound(0x170); bits |= 0x40; jump_state = 2
			else: _move(native_yaw, vertical, speed); vertical += gravity
		2: return _ended()
	return false
func _intro() -> void:
	match step:
		0:
			if distance_raw < 0x1001: control = 0; step = 1
		1:
			if _ended(): control = 4; step = 2
		2:
			if _ended(): _enter(1); control = 3
func _pursue() -> void:
	_face(_bearing()); speed = -0x400; _move(native_yaw, 0, speed)
	if not _ended(): return
	if wall: _enter(3)
	elif distance_raw < 0xC01: _enter(2)
	elif distance_raw >= 0x1000: _enter(7)
func _strafe() -> void:
	var turn := -0x20 if side != 0 else 0x20
	match step2:
		0:
			if _angle_difference(native_yaw, _bearing()) > 0: side = 0; _face(native_yaw - 0x400)
			else: side = 1; _face(native_yaw + 0x400)
			vertical = -0x280; speed = -0x400; gravity = 0x100; step2 = 1; jump_state = 0
		1:
			if _jump(false): control = 9 if side != 0 else 6; speed = -0x400; step2 = 2
		2:
			_move(native_yaw, 0, speed); _face(native_yaw + turn)
			if _ended(): control = 7 if side != 0 else 10; timer_a = 0x78; timer_b = 0x12C; step2 = 3
		3:
			_move(native_yaw, 0, speed); _face(native_yaw + turn)
			if _on_screen():
				if distance_raw < 0x801: _enter(6); timer_a = 0; timer_b = 0
				else:
					timer_b -= 1
					if timer_b == 0: _enter(7); timer_a = 0
			else:
				timer_a -= 1
				if timer_a == 0: step2 = 4
		4:
			_move(native_yaw, 0, speed); _face(native_yaw + (-8 if side != 0 else 8))
			if _on_screen(): timer_a = 0x78; timer_b = 0x12C; step2 = 3
func _wall_turn() -> void:
	if step == 0: timer_a = 0x10; step = 1
	_face(native_yaw + 0x40); timer_a -= 1
	if timer_a == 0: _enter(1)
func _knockback() -> void:
	match step:
		0: _sound(0x16F); control = 0x13; bits &= 0x8F; step = 1; timer_a = 2
		1:
			timer_a -= 1
			if timer_a == 0: vertical = -0x1E0; speed = 0x100; gravity = 0x40; _face(knock_yaw + 0x800); airborne = true; step = 2; _move(native_yaw, vertical, speed)
		2:
			_move(native_yaw, vertical, speed); vertical += gravity
			if not airborne: _sound(0x16D); control = 0x14; step = 3
		3:
			if _ended(): control = 0x15; step = 4
		4:
			if _ended(): bits |= 0x70; _enter(1); control = 3
func _leap() -> void:
	match step:
		0: _face(_bearing() - 0x120); vertical = -0xA0; speed = -0x400; gravity = 0x100; step = 1; jump_state = 0; _jump(false)
		1:
			if _jump(false): _face(_bearing() + 0x120); vertical = -0xA0; speed = -0x400; gravity = 0x100; step = 2; jump_state = 0
		2:
			if _jump(false):
				_sound(0x16E); _face(_bearing()); speed = -0x800; gravity = 0x100; var aimed := _aim(0x800, 0x100, 0x400); vertical = aimed if (aimed & 0xFFFF) > 0xF9FF else -0x100; step = 3; jump_state = 0
		3:
			if _jump(true): control = 0x20; step = 4; speed = -0x400; timer_a = 0x1E; jump_state = 0
		4:
			_move(native_yaw, 0, speed); timer_a -= 1
			if timer_a == 0: _enter(2)
func _howl() -> void:
	match step:
		0: control = 0x17; speed = 4; step = 1
		1:
			_move(0, 0, speed)
			if _ended(): control = 0x18; step = 2
		2:
			if distance_raw < 0x1000: control = 0x19; step = 3
		3:
			if _ended(): _enter(1); control = 3
func _death() -> void:
	if step == 0:
		_death_effect("boss"); drop_requested.emit(self, _drops()); inert = true; remove_from_group("lock_targets"); timer_a = 0xF; step = 1
	else:
		timer_a -= 1
		if timer_a == 0: top = 2; sub = 0; step = 0
