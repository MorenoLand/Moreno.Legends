extends "res://scripts/world/enemies/native_icefield_enemy.gd"
var state_flags := 0x34
var hurt_mode := 0xFF
var side := 1
var counter := 0
var hops := 0
var turn_step := 0
var gravity := 0
var in_air := false
var wall_bit := false
var wall_flag := false
var last_distance := 0.0
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry, metadata, path): return false
	control = 3; control_at_start = 3; clock.play_control(3, 0, true); visible = false; top = 1; last_distance = _distance(); add_to_group("lock_targets")
	var floor_hit := Motion.ray(self, global_position + Vector3.UP * 0.5, global_position - Vector3.UP * 60.0)
	if not floor_hit.is_empty(): global_position.y = (floor_hit["position"] as Vector3).y
	return true
func _run() -> void:
	match top:
		1: _main()
		2: _finish(); return
	_wrapper()
func _wrapper() -> void:
	last_distance = _distance(); hit_word = 0; hit_damage = 0; collision_layer = 0
	if hurt_mode == 0xFF: return
	_set_volume(256 if hurt_mode == 2 else 48, 100, 100); collision_layer = 8
	if hurt_mode > 2: return
	var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape.shape; query.transform = shape.global_transform; query.collision_mask = target.collision_layer; query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(self, int(attributes[1]), 0xA0000); return
func _animate() -> void:
	if control != control_at_start: clock.play_control(control, 0, true)
	elif (state_flags & 1) != 0: clock.native_tick()
func _main() -> void:
	if (state_flags & 0x10) != 0: _hit_handler()
	match sub:
		0: _dormant()
		1: _hop()
		2: _spit()
		4: _leave()
		5: _retreat()
		6: _knock(false)
		7: _knock(true)
		8: _fall_dead()
		9: _air_dead()
	_ground()
func _go(value: int) -> void: sub = value; step = 0
func _apply(damage: int) -> bool:
	health = mini(health - damage, max_health)
	if health < 0: health = -1; return true
	return false
func _hit_handler() -> void:
	var damage := hit_damage; var typed := (hit_word & 0x1C0000) != 0
	if typed:
		_set_light(248.0)
		if _apply(damage):
			if (state_flags & 2) == 0: sub = 9 if (state_flags & 4) != 0 else 8; step = 0; state_flags |= 2
			return
		if damage >= int(attributes[8]): sub = 7 if (state_flags & 4) != 0 else 6; step = 0; return
		_sound(0x8D)
	if (state_flags & 0x10) != 0 and (hit_word & 0x7000000) != 0 and (hit_word & 0x4000000) != 0:
		if not _apply(damage): sub = 6; step = 0
		elif (state_flags & 4) == 0 and (state_flags & 2) == 0: sub = 8; step = 0; state_flags |= 2
func _move(vertical_raw: int, forward_raw: int) -> void:
	var result := _step(vertical_raw, forward_raw); wall_bit = bool(result.get("blocked", false)) and not bool(result.get("grounded", false))
func _fly() -> void: _move(vertical, speed); vertical += gravity
func _ground() -> void:
	var ground := Motion.ray(self, global_position + Vector3.UP * 0.5, global_position - Vector3.UP * 8.0)
	if ground.is_empty(): in_air = true; return
	var height := global_position.y - (ground["position"] as Vector3).y
	if height <= 16.0 / 256.0: global_position.y = (ground["position"] as Vector3).y; in_air = false
	else: in_air = true
	wall_flag = wall_bit; wall_bit = false
func _dormant() -> void:
	if step == 0:
		if last_distance < 0xC01: step = 1; counter = 0x1E
	elif step == 1:
		counter -= 1
		if counter == 0: visible = true; state_flags |= 0x31; hurt_mode = 0; _sound(0x163); _sound(0xA3); step = 2
	elif step == 2:
		if (clock.record_flags & 128) != 0: sub = 1; step = 0; counter = 0; state_flags &= ~4
func _on_screen() -> bool:
	var camera: Camera3D = target.camera; var size := get_viewport().get_visible_rect().size; var point := global_position
	if camera.is_position_behind(point): return false
	var screen := camera.unproject_position(point)
	return screen.x >= 0.0 and screen.y >= 0.0 and screen.x / size.x * 320.0 < 320.0 and screen.y / size.y * 240.0 < 240.0
func _hop() -> void:
	match step:
		0:
			if last_distance < 0x400:
				if not _on_screen() or (_random() & 3) == 0: _go(5)
				else: _go(2)
			elif last_distance < 0xC01:
				speed = -0x178; var difference := (((_bearing() - native_yaw + 2048) & 4095) - 2048) + (0x100 if side > 0 else -0x100); turn_step = difference >> 1; _face(native_yaw + turn_step); step = 1; start_record = 0
			else: _go(4)
		1:
			control = 1; _face(native_yaw + turn_step); _sound(0x163); gravity = 0x80; vertical = -0x3C0; counter = 3; state_flags |= 4; side = ~side; step = 2; start_record = 0
		2:
			counter -= 1
			if counter == 0: _fly(); step = 3
		3:
			if not in_air: step = 0; state_flags &= ~4
			else:
				if start_record == 0 and vertical > 0: control = 2; step = 4
				_fly()
		4:
			if not in_air: step = 5; control = 0xD; speed = -0x100; state_flags &= ~4
			else: _fly()
		5:
			if (clock.record_flags & 128) != 0: step = 0
			else: _move(0, speed)
func _spit() -> void:
	if step < 2: _face(_bearing())
	match step:
		0:
			_fire(); counter = 0x14; control = 4; _sound(0x164); step = 1
		1:
			counter -= 1
			if counter == 0: control = 5; step = 2; counter = 1
		2:
			counter -= 1
			if counter == 0: _sound(0x165); step = 3
		3:
			if (clock.record_flags & 128) != 0: control = 6; step = 4
		4:
			if (clock.record_flags & 128) != 0: step = 5; control = 0; counter = 0x14
		5:
			counter -= 1
			if counter == 0: sub = 1; step = 0; counter = 0
func _fire() -> void:
	var projectile := preload("res://scripts/world/enemies/native_icefield_spit.gd").new(); get_parent().add_child(projectile)
	projectile.configure(self, target.global_position + Vector3.UP * 90.0 / 256.0); projectile.contact_hit.connect(func(actor, damage, hit_flags): contact_hit.emit(actor, damage, hit_flags))
func _leave() -> void:
	if step == 0: state_flags &= ~0x30; control = 0xC; step = 1; hurt_mode = 3; counter = 0x1E
	elif step == 1:
		counter -= 1
		if counter == 0: visible = false; sub = 0; step = 0; control = 3; hurt_mode = 0xFF; counter = 0; state_flags &= ~1; _sound(0xA4)
func _retreat() -> void:
	if wall_flag: state_flags |= 0x80
	match step:
		0:
			hops = (hops + 1) & 255
			if hops < 3:
				_face(_bearing() + 2048); speed = -0x178; control = 1; _sound(0x163); gravity = 0x80; vertical = -0x3C0; counter = 3; step = 1; start_record = 0; state_flags |= 4
			else: step = 5; hops = 0
		1:
			counter -= 1
			if counter == 0: _fly(); step = 2
		2:
			if not in_air: step = 0; state_flags &= ~4
			else:
				if start_record == 0 and vertical > 0: control = 2; step = 3
				_fly()
		3:
			if not in_air: step = 4; control = 0xD; speed = -0x100; state_flags &= ~4
			else: _fly()
		4:
			if (clock.record_flags & 128) != 0:
				if (state_flags & 0x80) == 0: step = 0
				else: state_flags &= 0x7F; step = 5
			else: _move(0, speed)
		5:
			turn_step = ((((_bearing() - native_yaw + 2048) & 4095) - 2048)) >> 4; counter = 0x10; control = 0xE; step = 6
		6:
			counter -= 1
			if counter == 0: sub = 1; step = 0
			else: _face(native_yaw + turn_step)
func _knock(airborne_hit: bool) -> void:
	if step == 0:
		control = 6 if airborne_hit else 5; _sound(0x8E); vertical = -0x1E0; speed = 0x100; gravity = 0x40; state_flags &= ~0x30; _set_light(248.0); hurt_mode = 3; step = 1
		return
	if airborne_hit:
		_fly()
		if not in_air: sub = 4; step = 0; start_record = 0; state_flags = (state_flags | 0x30) & ~4
		return
	if step == 1:
		_fly()
		if (clock.record_flags & 128) != 0: step = 2
	elif step == 2:
		_fly()
		if not in_air: control = 6; step = 3
	elif step == 3:
		if (clock.record_flags & 128) != 0: sub = 4; step = 0; start_record = 0; state_flags = (state_flags | 0x30) & ~0x40
func _fall_dead() -> void:
	if step == 0: control = 7; hurt_mode = 3; step = 1
	elif step == 1:
		if (clock.record_flags & 128) != 0: control = 8; step = 2; counter = 0x1E
	elif step == 2:
		counter -= 1
		if counter == 0xF: hurt_mode = 0xFF
		elif counter <= 0: drop_requested.emit(self, _drops()); top = 2
func _air_dead() -> void:
	if step == 0: visible = false; drop_requested.emit(self, _drops()); counter = 0xF; step = 1; hurt_mode = 3
	elif step == 1:
		counter -= 1
		if counter == 0: top = 2
