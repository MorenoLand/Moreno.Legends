extends "res://scripts/world/enemies/native_icefield_enemy.gd"
var wake := 0
var rumble := 0
var growl := 0
var heading := 0
var counter := 0
var distant := 0
var timeout := 0
var wobble := 0
var mode := 0
var sx := 512
var sy := 0
var sz := 512
var result := {}
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry, metadata, path): return false
	var floor_hit := Motion.ray(self, global_position + Vector3.UP * 0.5, global_position - Vector3.UP * 60.0)
	if not floor_hit.is_empty(): global_position.y = (floor_hit["position"] as Vector3).y
	heading = native_yaw; flags = 2; top = 1; control = 1; control_at_start = 1; clock.play_control(1, _bios_rand() & 0x1F, true); add_to_group("lock_targets")
	if int(str(entry["source_bytes_hex"]).hex_decode()[6]) == 2: sub = 7; flags |= 0x10
	_set_scale(sx, sy, sz); return true
func _run() -> void:
	match top:
		1: _outer()
		2: _awaken()
		3: _hunt()
		4: _finish(); return
	collision_layer = 0 if (flags & 2) != 0 else collision_layer
func _outer() -> void:
	if wake == 0 and (flags & 2) == 0:
		var hit := _damage_check()
		if hit != 0 or (hit_word & 0x10000) != 0: control = 3; sub = 4; step = 0; wake = 1
	match sub:
		0: _rise()
		1: _wander()
		2: _slow()
		3: _fall(false)
		4: _burst()
		5: _sink()
		6: _fade()
		7: _dormant()
	if wake == 0 and sub != 4:
		rumble = (rumble - 1) & 255
		if rumble == 0: rumble = 0x37; _sound(0x167)
	_finish_tick()
func _finish_tick() -> void:
	if (flags & 2) == 0: _register(mode)
func _awaken() -> void:
	sx = 0x156; sy = 0x156; sz = 0x156; _set_scale(sx, sy, sz); control = 2; control_at_start = 2; clock.play_control(2, _bios_rand() & 0xF, true); stagger_count = 0; mode = 1; counter = 0; hit_word = 0; hit_damage = 0; top = 3; sub = 0; step = 0; start_record = 0
func _hunt() -> void:
	if timeout != 0x258: timeout += 1
	if (flags & 2) == 0:
		var hit := _damage_check()
		if hit == -1: sub = 5; step = 0; control = 4; speed = 0; flags = 0; counter = 0; mode += 1
		elif (flags & 0x28) == 8: sub = 4; step = 0; control = 3
	match sub:
		0: _grow()
		1: _chase()
		2: _recoil()
		3: _fall(true)
		4: _stagger()
		5: _defeat()
		6: _sink()
		7: _roam()
	if sub != 5:
		growl = (growl - 1) & 255
		if growl == 0: growl = (_random() & 0x3F) + 106; _sound(0x16A)
	_finish_tick()
func _after(value: int) -> void: sub = value; step = 0
func _burrow() -> void: sub = 6; step = 0; control = 2; flags = 2
func _land() -> void: sub = 3; step = 0; control = 0; flags |= 0x20
func _probe() -> int:
	var ground := Motion.ray(self, global_position + Vector3.UP * 0.125, global_position - Vector3.UP * 0.25)
	var has := not ground.is_empty() and (ground["normal"] as Vector3).y > 0.0
	if airborne:
		if has and (ground["position"] as Vector3).y >= global_position.y - 0.01: airborne = false
		return 0
	if not has: airborne = true; return 1
	return 0
func _wobble_move() -> int:
	wobble = (wobble + 1) & 0x7F; var offset := (wobble & 0x1F) << 4
	if (wobble & 0x20) != 0: offset = 0x200 - offset
	if (wobble & 0x40) != 0: offset = -offset
	_face(heading + offset); return _resolve(_step(0, speed))
func _rise() -> void:
	var emitting := step < 3
	if step == 0: _sound(0xA3); step = 1
	if step == 1:
		sy += 16
		if sy >= 544: step = 2
	elif step == 2:
		sy -= 8
		if sy < 513: sy = 512; step = 3; counter = 0
	elif step == 3:
		counter += 1
		if counter == 0x1E: step = 4
	elif step == 4:
		sub = 1; step = 0; start_record = _bios_rand() & 0x1F; speed = -0x48; control = 0; flags = 0; rumble = 0x37
	_set_scale(sx, sy, sz)
	if emitting: _dust("burrower")
func _wander() -> void:
	var reply := _wobble_move()
	if clock.record_counter == 0xF or clock.record_counter == 0x25: _sound(0x166)
	if reply == 2: sub = 6; step = 0; flags = 2
	if reply == 1: sub = 3; step = 0; flags |= 0x20; return
	if _distance() >= 3072.0:
		distant += 1
		if distant >= 121: sub = 5; step = 0; flags = 2
	else: distant = 0
func _slow() -> void:
	if _distance() >= 206.0: sub = 1; step = 0; control = 0
	if _probe() == 1: _land()
func _fall(hunting: bool) -> void:
	vertical = mini(vertical + 0x30, 0x2000); _resolve(_step(vertical, speed))
	if airborne: return
	if hunting: sub = 1; step = 0; vertical = 0; flags &= ~0x20
	elif control == 3: vertical = 0; sub = 4; step = 0
	else: vertical = 0; sub = 1; step = 0; flags &= ~0x20
func _burst() -> void:
	if step == 0: flags = 2; step = 1
	elif step == 1:
		if (clock.record_flags & 128) != 0: control = 4; step = 2; counter = 0
	elif step == 2:
		counter += 1
		if counter == 0x28: _sound(0x168); rumble = (_random() & 0x1F) + 60; top = 2; sub = 0; step = 0; start_record = 0
	_dust("burrower_burst")
func _sink() -> void:
	if step == 0: _sound(0xA4); step = 1
	sy -= 16; _set_scale(sx, sy, sz)
	if sy <= 0: sy = 0; top = 4
	_dust("burrower")
func _fade() -> void:
	_wobble_move()
	if step == 0: _translucent(); counter = 0x10; flags |= 0x10; step = 1
	else:
		counter -= 1
		if counter == 0: visible = false; remove_from_group("lock_targets"); top = 4
	_set_light(float(maxi(counter, 0) * 8))
func _dormant() -> void:
	visible = false
	if _distance() < 1025.0: visible = true; sub = 0
func _grow() -> void:
	sx += 10; sy = sx; sz = sx; counter += 1; _set_scale(sx, sy, sz)
	if counter == 0x11: sx = 0x200; sy = 0x200; sz = 0x200; sub = 1; step = 0; start_record = _bios_rand() & 0x1F; control = 0; speed = -0x100; flags = 0; counter = 0; distant = 0; _set_scale(sx, sy, sz)
	_dust("burrower")
func _chase_heading(distance: float) -> void:
	if (flags & 0x40) != 0:
		if distance >= 640.0: flags &= ~0x40
		return
	if counter != 0: counter -= 1; return
	var roll := _bios_rand()
	if (roll & 0x3F) != 0: heading = _bearing()
	else: heading = (heading + (400 if (roll & 0x40) != 0 else -400)) & 0xFFFF; counter = ((roll >> 7) & 7) + 16
func _chase() -> void:
	var distance := _distance()
	if step == 0: _chase_heading(distance)
	if ((clock.record_counter - 2) & 7) == 0: _sound(0x169)
	_turn(heading, 0x40); var reply := _resolve(_step(0, speed))
	if reply == 1: _land()
	elif reply == 2:
		if counter == 0: heading = _reflect(native_yaw); counter = (_bios_rand() & 0xF) + 16
	else:
		if (hit_word & 0x10000) != 0: sub = 2; step = 0; control = 1; speed = 0x80; _face(_bearing())
		if distance >= 3072.0:
			distant += 1
			if distant >= 121: _burrow()
		else: distant = 0
	if distance < 64.0: flags |= 0x40
	if timeout == 0x258: _burrow()
func _recoil() -> void:
	var reply := _resolve(_step(0, speed))
	if (clock.record_flags & 128) != 0: sub = 7; step = 0; control = 0; speed = -0x100; counter = 0; heading = native_yaw
	if reply == 1: _land()
func _stagger() -> void:
	if (clock.record_flags & 128) != 0: control = 0; sub = 1; step = 0
	if _probe() == 1: _land()
func _defeat() -> void:
	if airborne: vertical = mini(vertical + 0x30, 0x2000); _resolve(_step(vertical, speed)); return
	flags &= ~0x20; vertical = 0
	if step == 0: _death_effect("burrower"); counter = 0; step = 1
	else:
		counter += 1
		if counter == 0x20: counter = 0; top = 4; drop_requested.emit(self, _drops())
		elif counter == 0xF: flags |= 2
func _roam() -> void:
	_turn(heading, 0x40); var reply := _resolve(_step(0, speed)); var distance := _distance(); var near := distance < 640.0
	if reply == 1: _land()
	elif reply == 2:
		if native_yaw == heading: heading = (native_yaw - 512 if (_bios_rand() & 1) != 0 else native_yaw + 512) & 4095
	else:
		if (hit_word & 0x10000) != 0: sub = 2; step = 0; control = 1; speed = 0x80
		if distance >= 3072.0:
			distant += 1
			if distant >= 121: _burrow(); near = distance < 640.0
		else: distant = 0
	if near:
		counter += 1
		if counter < 91: return
	if (_bios_rand() & 3) != 0: control = 0; sub = 1; step = 0; counter = 0
	else: _burrow()
