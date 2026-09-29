extends "res://scripts/world/stage_actor.gd"
signal defeated(actor: CharacterBody3D)
class Hurtbox extends StaticBody3D:
	var owner_actor: CharacterBody3D
	var weak := false
	func receive_hit(damage: int, flags: int, direction: Vector3 = Vector3.ZERO) -> bool: return owner_actor.receive_native_hit(damage, flags, direction, weak)
var substate := 0
var phase := 0
var native_flags := 0
var awareness_timer := 30
var melee_cooldown := 0
var heading := 0
var turn_step := 0
var neck_phase := -1
var neck_mode := 0
var neck_offset := 0
var death_phase := 0
var death_timer := 0
var body_boxes: Array[StaticBody3D] = []
var limb_boxes: Array[StaticBody3D] = []
var shield_effects_enabled := false
var shield_trails: Array[MeshInstance3D] = []
var event_bits := 0
var hurt_timer := 0
func configure(entry: Dictionary, metadata: Dictionary, directory: String) -> void:
	super.configure(entry, metadata, directory)
	attack_damage = int(entry["source_attributes"][2])
	contact_damage = int(entry["source_attributes"][1])
	native_state = 0
	collision_layer = 0
	for index in range(4):
		var body := Hurtbox.new(); body.owner_actor = self; body.weak = index == 3; body.collision_layer = 8; body.collision_mask = 0
		var shape := CollisionShape3D.new(); var sphere := SphereShape3D.new(); sphere.radius = (180.0 if index == 0 else 80.0) / 256.0; shape.shape = sphere; body.add_child(shape); add_child(body); body_boxes.append(body)
	for index in range(6):
		var body := Hurtbox.new(); body.owner_actor = self; body.collision_layer = 8; body.collision_mask = 0
		var shape := CollisionShape3D.new(); var capsule := CapsuleShape3D.new(); capsule.radius = 72.0 / 256.0; shape.shape = capsule; body.add_child(shape); add_child(body); limb_boxes.append(body)
	set_meta("native_source_record", str(entry.get("source_record_ram", "0x8010180c")))
func _physics_process(delta: float) -> void:
	if target == null or removed or (not dying and not target.is_physics_processing()): return
	tick_accumulator += delta
	while tick_accumulator >= 1.0 / TICK_RATE:
		tick_accumulator -= 1.0 / TICK_RATE
		var freeze_animation := native_state == 5 and substate == 5
		hurt_timer = maxi(hurt_timer - 1, 0)
		melee_cooldown = maxi(melee_cooldown - 1, 0)
		if dying: _boss_death()
		else: _boss_tick()
		if removed: return
		_move_native(native_speed)
		rotation.y = native_yaw * TAU / 4096.0
		model.rotation.y = neck_offset * 16.0 * TAU / 4096.0
		var frame := control_frame; var slot := current_control
		if not freeze_animation: _advance_control()
		event_bits = int(clips[current_control]["records"][control_frame]["event"]) if clips.has(current_control) and (frame != control_frame or slot != current_control) else 0
		if event_bits & 128 and not dying: sound_requested.emit(0xb4, global_position)
		_update_collision()
		_update_body_boxes()
		for trail in shield_trails: trail.native_tick(neck_offset * 16)
		if not dying: _attack_events(); _body_contact()
		_set_hit_light(Vector3(248, 248, 248) if hurt_timer > 0 else Vector3(128, 128, 128))
func _state(state: int, sub: int = 0) -> void:
	native_state = state; substate = sub; phase = 0; initialized = false
func _control(slot: int) -> void:
	native_speed = 0; velocity = Vector3.ZERO; play_control(slot)
func _start_record(slot: int, record: int) -> void:
	_control(slot)
	if not clips.has(slot): return
	var records: Array = clips[slot]["records"]; control_frame = clampi(record, 0, records.size() - 1); control_tick = 0
	for index in range(control_frame): control_tick += int(records[index]["duration"])
	control_remaining = int(records[control_frame]["duration"])
	if animation_player != null: animation_player.seek(control_tick / 30.0, true)
func _move_native(speed: int) -> void:
	var previous := global_position
	super._move_native(speed)
	var displacement := Vector2(global_position.x - previous.x, global_position.z - previous.z).length()
	native_flags = native_flags | 1 if speed != 0 and displacement < absf(speed / 4096.0) * 0.5 else native_flags & ~1
func _facing(limit: int) -> bool: return absi(_yaw_difference(_angle_from(target.global_position))) <= limit
func _target_condition(limit: int) -> int:
	if not _facing(limit): return 1
	var distance := global_position.distance_to(target.global_position) * 256.0
	if distance >= 5000: return 2
	var ray := PhysicsRayQueryParameters3D.create(_bone(1), target.global_position + Vector3.UP * 0.5, 1, [get_rid()]); var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	return (128 if distance < 600 else 0) | (3 if not hit.is_empty() else 0)
func _awareness(limit: int, mode: int) -> void:
	var condition := _target_condition(limit)
	if mode == 2 and condition & 128 and melee_cooldown == 0: native_flags &= ~32; _state(5); return
	if mode == 2 and health <= 64: return
	var blocked := condition & (79 if mode == 2 else 15)
	awareness_timer = maxi(awareness_timer - 1, 0) if (blocked != 0 if mode == 2 else blocked == 0) else 60 if mode == 2 else 30
	if awareness_timer == 0:
		if mode == 0: _state(3)
		elif mode == 1: _state(1)
		elif mode == 2: _state(2, 1)
func _boss_tick() -> void:
	if neck_mode == 0: neck_offset = 0
	elif neck_mode == 2: neck_offset = clampi(_yaw_difference(_angle_from(target.global_position)) >> 4, -32, 32)
	if neck_phase >= 0:
		var goals := [32, -32, 32, -32, 32, -32, 0]; neck_offset = move_toward(neck_offset, goals[neck_phase], 8)
		if neck_offset == goals[neck_phase]: neck_phase += 1
		if neck_phase == 7: neck_phase = -1; neck_mode = 0
	match native_state:
		0:
			if not initialized: initialized = true; _control(2); native_speed = -128; timer = 3; native_flags &= 124
			if control_ended: timer -= 1
			if timer <= 0 or native_flags & 1: _state(2)
			_awareness(512, 0)
		1:
			if phase == 0:
				_control(3); native_speed = -384; neck_mode = 2; awareness_timer = 60 if native_flags & 4 else awareness_timer; native_flags = (native_flags | 2) & ~5; timer = [3, 4, 3, 5, 3, 5, 3, 4][_next_random() & 7]; phase = 1
			if phase == 1:
				_turn(_angle_from(target.global_position), 32)
				if control_ended: timer -= 1
				if timer <= 0: phase = 2; timer = [1, 2, 1, 2, 2, 1, 3, 1][_next_random() & 7]
			elif phase == 2:
				if control_ended: timer -= 1
				if timer <= 0: phase = 0
			_awareness(768, 2)
			if native_flags & 1: _state(4)
		2:
			_turn_state()
		3:
			if not initialized: initialized = true; _control(11 if substate == 0 else 12); native_flags |= 6 if substate == 0 else 2; _effects(true)
			if control_ended:
				if substate == 0: _state(1)
				else: _effects(false); _state(0)
		4:
			if not initialized:
				initialized = true; native_flags |= 2
				var condition := _target_condition(768); var mask := 648 if target.global_position.distance_to(global_position) * 256.0 >= 1000 or (condition & 15) < 2 else 64887
				if ((condition & 15) == 0 or (mask >> (_next_random() & 15)) & 1) and melee_cooldown == 0: native_flags |= 32; _state(5); return
				_control(3); native_speed = -384; turn_step = 32 if (_next_random() & 1) else -32; awareness_timer += 15
			native_yaw = (native_yaw + turn_step) & 4095
			if not _wall_ahead(native_yaw, 128): _state(1)
			_awareness(768, 2)
		5:
			_melee_state()
		6:
			_stagger_state()
func _turn_state() -> void:
	match substate:
		0:
			if phase == 0: heading = _choose_heading(1024 if native_flags & 1 else 512); turn_step = 24; _control(1); native_flags &= 125; neck_mode = 1; neck_phase = 0; neck_offset = 0; phase = 1
			if phase == 1 and neck_phase < 0: phase = 2; play_control(2)
			if phase == 2: _turn(heading, turn_step); if absi(_yaw_difference(heading)) <= turn_step: _state(0)
			_awareness(768, 0)
		1:
			if phase == 0 and control_ended: heading = _choose_heading(512); turn_step = 16; _control(0); awareness_timer = 30; native_flags |= 2; phase = 1; play_control(20)
			elif phase == 1 and control_ended: _state(3, 1) if health > 64 else _state(1)
			_turn(heading, turn_step)
			_awareness(768, 1)
		2:
			if phase == 0: _control(1); native_flags |= 128; neck_mode = 1; neck_phase = 0; neck_offset = 0; phase = 1
			if not _facing(768) or neck_phase < 0: _state(3)
func _melee_state() -> void:
	if substate == 0:
		if phase == 0:
			phase = 1
			if native_flags & 32: native_flags &= ~32; substate = 1
			else: _control(0); timer = 30
		if substate == 0: timer -= 1; if timer <= 0: substate = 1
	if substate == 1:
		var difference := _yaw_difference(_angle_from(target.global_position)); substate = 2 if absi(difference) < 256 else 3 if difference > 0 else 4; phase = 0; native_flags |= 2
	if substate in [2, 3, 4]:
		if phase == 0: phase = 1; _control({2: 6, 3: 7, 4: 17}[substate]); attack_effect_timer = 0
		if control_ended: _finish_melee()
	elif substate == 5:
		if phase == 0: phase = 1; timer = 4
		timer -= 1
		if timer <= 0: substate = 6
	elif substate == 6 and control_ended: _finish_melee()
func _finish_melee() -> void:
	native_flags |= 4; melee_cooldown = [30, 30, 30, 30, 60, 30, 60, 30, 60, 30, 60, 30, 30, 30, 30, 30][_next_random() & 15]; _state(1)
func _stagger_state() -> void:
	match phase:
		0: native_flags |= 64; _control(10 if native_flags & 2 else 9); neck_mode = 0; neck_phase = -1; phase = 1; _effects(false)
		1:
			native_speed = -96 if event_bits else 0
			if control_ended: phase = 2; native_flags &= ~64
		2: play_control(3); native_flags |= 6; heading = _angle_from(target.global_position); turn_step = 64; phase = 3
		3:
			_turn(heading, turn_step)
			if absi(_yaw_difference(heading)) <= turn_step or _facing(768): _state(1)
func _wall_ahead(yaw: int, radius_raw: int) -> bool:
	var angle := yaw * TAU / 4096.0; var start := global_position + Vector3.UP * 0.4; var end := start - Vector3(sin(angle), 0, cos(angle)) * radius_raw / 256.0
	return not get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(start, end, 1, [get_rid()])).is_empty()
func _choose_heading(spread: int) -> int:
	var mask := 7
	for offset in range(3):
		if _wall_ahead((native_yaw + (offset - 1) * spread) & 4095, 375): mask &= ~(1 << (2 - offset))
	if mask == 0: return (native_yaw + 2048) & 4095
	var choices := [1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 1, -1, -1, -1, -1, -1, 1, -1, 1, 0, -1, 0, -1, 1, 0, -1, 0]
	return (native_yaw + int(choices[(mask - 1) * 4 + (_next_random() & 3)]) * spread) & 4095
func _bone(index: int) -> Vector3:
	return skeleton.global_transform * skeleton.get_bone_global_pose(index).origin if skeleton != null and index < skeleton.get_bone_count() else global_position
func _update_body_boxes() -> void:
	var points := [_bone(0), _bone(12), _bone(15), _bone(0) + global_basis * Vector3(0, -0.5, 100.0 / 256.0)]
	for index in range(body_boxes.size()): body_boxes[index].global_position = points[index]
	for index in range(limb_boxes.size()):
		var first: int = [2, 3, 4, 6, 7, 8][index]; var start := _bone(first); var end := _bone(first + 1); var axis := end - start
		limb_boxes[index].global_position = (start + end) * 0.5
		if axis.length_squared() > 0.000001: limb_boxes[index].global_basis = Basis(Quaternion(Vector3.UP, axis.normalized()))
		(limb_boxes[index].get_child(0).shape as CapsuleShape3D).height = axis.length() + 144.0 / 256.0
func _hit_volume(point: Vector3, radius_raw: int, damage: int, flags: int) -> bool:
	var shape := SphereShape3D.new(); shape.radius = radius_raw / 256.0
	var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape; query.transform = Transform3D(Basis.IDENTITY, point); query.collision_mask = target.collision_layer; query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(self, damage, flags); return true
	return false
func _body_contact() -> void:
	_hit_volume(_bone(0), 180, contact_damage, 0x20000)
	for index in [5, 9]: _hit_volume(_bone(index), 72, attack_damage if native_flags & 8 else contact_damage, 0x180000 if native_flags & 8 else 0x20000)
	native_flags &= ~8
func _attack_events() -> void:
	if native_state != 5 or substate not in [2, 3, 4] or event_bits == 0: return
	var point := (_bone(5) + _bone(9)) * 0.5 + global_basis * Vector3(0, 0, -100.0 / 256.0) if substate == 2 else _bone(5) + Vector3.DOWN * 150.0 / 256.0 if substate == 3 else _bone(9)
	if event_bits & 1: _hit_volume(point, 256 if substate == 2 else 180, attack_damage, 0x980000)
	if event_bits & 2: sound_requested.emit(0xb6 if substate == 2 else 0xb5, global_position)
	var recovery := 0
	if event_bits & 4 and _hand_wall(point, 200 if substate == 2 else 128): recovery = {2: 14, 3: 15, 4: 19}[substate]
	if substate == 4:
		if event_bits & 1: native_flags |= 8; if attack_effect_timer == 0: sound_requested.emit(0xb7, global_position); attack_effect_timer = 1
		if event_bits & 16: _hit_volume(_bone(5), 180, attack_damage, 0x980000)
		if event_bits & 32: _hit_volume(_bone(5), 128, attack_damage, 0x980000)
		if event_bits & 32 and _hand_wall(_bone(5), 128): recovery = 19
	if recovery != 0:
		var start := 65 - control_frame if recovery == 15 else 36 - control_frame if recovery == 19 else 0
		substate = 5; phase = 0; _start_record(recovery, start)
func _hand_wall(point: Vector3, radius_raw: int) -> bool:
	for direction in [Vector3.LEFT, Vector3.RIGHT, Vector3.FORWARD, Vector3.BACK]:
		var query := PhysicsRayQueryParameters3D.create(point, point + direction * radius_raw / 256.0, 1, [get_rid()]); var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty() and absf(hit["normal"].y) < 0.5: return true
	return false
func _effects(value: bool) -> void:
	shield_effects_enabled = value
	if value and shield_trails.is_empty():
		for offset in [Vector3(-24, -56, -66), Vector3(24, -56, -66), Vector3(-24, -34, -68), Vector3(24, -34, -68)]:
			var trail := preload("res://scripts/world/native_mine_trail.gd").new(); add_child(trail); trail.configure(self, offset); shield_trails.append(trail)
	elif not value:
		for trail in shield_trails: trail.queue_free()
		shield_trails.clear()
func receive_hit(damage: int, flags: int, direction: Vector3 = Vector3.ZERO) -> bool: return receive_native_hit(damage, flags, direction, false)
func receive_native_hit(damage: int, flags: int, direction: Vector3, weak: bool) -> bool:
	if dying or removed or damage <= 0 or hurt_timer > 0 or not (flags & 0xc0000): return false
	var effective := damage if weak and absi(_yaw_difference(roundi(atan2(-direction.x, -direction.z) * 4096.0 / TAU))) < 1024 else 1
	health -= effective
	sound_requested.emit(0x8e if effective > 1 else 0x8d, global_position)
	if flags & 0x400000: hurt_timer = 20
	if health < 0:
		dying = true; death_phase = 0; collision_layer = 0
		for body in body_boxes + limb_boxes: body.collision_layer = 0
		defeated.emit(self)
	elif effective > 1: _state(6)
	elif not (native_flags & 130): _state(2, 2)
	return true
func _boss_death() -> void:
	match death_phase:
		0: _control(13); neck_offset = 0; neck_mode = 0; neck_phase = -1; _effects(false); death_phase = 1
		1:
			if event_bits: sound_requested.emit(0x162, global_position)
			if control_ended: death_phase = 2; death_timer = 42
		2:
			death_timer -= 1
			if death_timer <= 0:
				removed = true; drop_requested.emit(self, _drop_entries()); died.emit(self); queue_free()
