extends "res://scripts/world/enemies/native_icefield_enemy.gd"
const Projectile := preload("res://scripts/world/enemies/native_dungeon_projectile.gd")
const Explosion := preload("res://scripts/world/enemies/native_dungeon_explosion.gd")
var skeleton: Skeleton3D
var flag_bits := 0
var timer := 0
var head_yaw := 0
var head_pitch := 0
var cycle := 0
var player_distance := 0
var yaw_offset := 0
var elevation := 0
var head_rotation := Quaternion.IDENTITY
var head_delta := Quaternion.IDENTITY
var volumes: Array[CollisionShape3D] = []
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry, metadata, path): return false
	skeleton = model.find_child("Skeleton3D", true, false) as Skeleton3D
	for index in 2:
		var extra := CollisionShape3D.new(); extra.shape = SphereShape3D.new(); add_child(extra); volumes.append(extra)
	timer = (native_yaw >> 4) + 1; control = 7; control_at_start = 7; start_record = 0; cycle = 0
	var flags: Dictionary = host.native_context.get("event_flags", {})
	if bool(flags.get(0x5B6, flags.get("1462", false))): flag_bits |= 1
	top = 1; sub = 1; clock.play_control(7, 0, true); add_to_group("lock_targets")
	return true
func _joint(index: int, offset_raw := Vector3.ZERO) -> Vector3:
	if skeleton == null or index >= skeleton.get_bone_count(): return global_position
	return skeleton.global_transform * (skeleton.get_bone_global_pose(index) * (Vector3(-offset_raw.x, -offset_raw.y, offset_raw.z) / 256.0))
func _bone_distance() -> int: return roundi(Vector2(_joint(1).x - target.global_position.x, _joint(1).z - target.global_position.z).length() * 256.0)
func _run() -> void:
	if top == 2: _final(); return
	var body := _joint(1); player_distance = _bone_distance()
	var bearing: int = preload("res://scripts/world/actors/native_talk_facing.gd")._heading(target.global_position, body)
	yaw_offset = posmod(bearing - native_yaw + 2048, 4096) - 2048
	var rise := (target.global_position.y + 0.5 - body.y) * 256.0
	elevation = 0x800 - ((0xC00 - posmod(roundi(atan2(float(player_distance), rise) / TAU * 4096.0), 4096)) & 4095)
	match sub:
		0: _dormant_cycle()
		1: _countdown()
		2: _open_fire()
		3: _volley()
		4: _hold()
		5: _close()
		6: _threshold()
		7: _stunned()
		8: _dying()
	_track_head()
	if (flag_bits & 0x10) == 0: _damage()
	hit_word = 0; hit_damage = 0
	if control in [0, 2, 6]: flag_bits &= ~8
	elif sub == 8: flag_bits &= ~8
	else: flag_bits |= 8
	_volumes()
func _tint(red: int, green: int, blue: int) -> void:
	for material in materials: material.set_shader_parameter("light_rgb", Vector3(red, green, blue) * 8.0)
func _ended() -> bool: return (clock.record_flags & 128) != 0
func _start(next_control: int, next_sub: int) -> void: control = next_control; start_record = 0; sub = next_sub
func _attack_opening(mask: int) -> void:
	flag_bits |= 2
	if (_random() & mask) == 0: control = 2; _sound(0x122)
	else: control = 6; _sound(0x123)
	start_record = 0; cycle = 0; sub = 2
func _dormant_cycle() -> void:
	if _ended():
		timer += 1
		if timer == 2: timer = 0xF0; control = 7; sub = 1
		if player_distance <= 0x400 and (flag_bits & 1) != 0: _attack_opening(7)
func _countdown() -> void:
	timer = (timer - 1) & 0xFFFF
	if timer == 0: control = 1; start_record = 0; sub = 0
	elif player_distance <= 0x400 and (flag_bits & 1) != 0: _attack_opening(3)
func _open_fire() -> void:
	if clock.record_index == 14: _sound(0x123)
	if clock.pose >= 14: _shoot(0x10 - timer)
	if _ended(): flag_bits |= 4; timer = 0x10; _sound(0x124); sub = 3
func _volley() -> void:
	if timer >= 0xC: _shoot(0x10 - timer)
	timer = (timer - 1) & 0xFFFF
	if timer == 0:
		if (_random() & 1) != 0: timer = 0x20; control = 0; sub = 4
		else: control = 5; sub = 5
		start_record = 0; cycle = (cycle + 1) & 255
func _hold() -> void:
	if player_distance > 0xA00: flag_bits &= ~6; timer = 0xF0; control = 5; start_record = 0; sub = 1
	else:
		timer = (timer - 1) & 0xFFFF
		if timer == 0: control = 5; start_record = 0; sub = 5
func _close() -> void:
	if _ended():
		if (_random() & 3) == 0: control = 2; _sound(0x122)
		else: control = 6; _sound(0x123)
		start_record = 0; sub = 2
func _threshold() -> void:
	if _ended(): flag_bits = (flag_bits & ~0x10) | 4; timer = 0x20; control = 0; start_record = 0; sub = 4; cycle = (cycle + 1) & 255
func _stunned() -> void:
	timer = (timer - 1) & 0xFFFF
	if timer == 0:
		control = 2; sub = 2; flag_bits = (flag_bits & 0xFEEF) | 4; start_record = 0; cycle = (cycle + 1) & 255; _sound(0x122)
func _dying() -> void:
	_tint(24, 12, 12)
	if (timer & 7) == 0: Explosion.spawn(self, _joint(1, Vector3(0, 0, -0x400)) + Vector3(-float((_random() & 0x7F) - 0x40), -float(((_random() & 0x7F0) >> 4) - 0x40), float(((_random() & 0x7F00) >> 8) - 0x40)) / 256.0, 0x40, 0)
	timer = (timer - 1) & 0xFFFF
	if timer == 0: top = 2
func _shoot(_variant: int) -> void:
	var first := _random(); var second := _random(); var pitch := head_pitch & 4095
	var lift := ((first & 0x1FF) - 0x100) + ((7 * roundi(sin(float(pitch) * TAU / 4096.0) * 4096.0)) >> 5)
	if cycle == 0: lift += 0x200
	elif player_distance > 0x200: lift -= 0x80
	Projectile.spawn(self, _joint(1, Vector3(0, 0, -0x80)), (native_yaw + head_yaw + ((second & 0x7F80) >> 6) - 0x100) & 4095, lift, -((7 * roundi(cos(float(pitch) * TAU / 4096.0) * 4096.0) * 128) >> 12))
func _track_head() -> void:
	if (flag_bits & 4) != 0:
		var difference := yaw_offset - head_yaw
		if difference > 0x40: head_yaw = head_yaw + 0x40 if head_yaw < 0x280 else 0x280
		elif difference >= -0x40:
			if ((head_yaw + 0x27F) & 0xFFFF) < 0x4FF: head_yaw = yaw_offset
		else: head_yaw = -0x280 if head_yaw < -0x27F else head_yaw - 0x40
		head_pitch = elevation
	else:
		head_yaw = head_yaw - 0x40 if head_yaw > 0x40 else head_yaw + 0x40 if head_yaw < -0x40 else 0
		head_pitch = head_pitch - 0x40 if head_pitch > 0x40 else head_pitch + 0x40 if head_pitch < -0x40 else 0
func _apply_head() -> void:
	if skeleton == null or skeleton.get_bone_count() < 3: return
	head_delta = Quaternion(Vector3.UP, -float(head_yaw) * TAU / 4096.0) * Quaternion(Vector3.RIGHT, -float(head_pitch >> 1) * TAU / 4096.0)
	head_rotation = skeleton.get_bone_pose_rotation(2) * head_delta; skeleton.set_bone_pose_rotation(2, head_rotation)
func _animate() -> void:
	if skeleton != null and skeleton.get_bone_count() > 2 and head_delta != Quaternion.IDENTITY and skeleton.get_bone_pose_rotation(2).is_equal_approx(head_rotation): skeleton.set_bone_pose_rotation(2, head_rotation * head_delta.inverse())
	head_delta = Quaternion.IDENTITY
	super()
	_apply_head()
func _damage() -> void:
	var damage := 0
	if (flag_bits & 0x100) == 0:
		if (hit_word & 0xC0000) != 0 and (flag_bits & 8) == 0: damage += hit_damage; _set_light(248.0)
	elif (hit_word & 0x40000) != 0: timer = 0x96
	if (hit_word & 0x40000) != 0: damage += hit_damage * 2; _set_light(248.0)
	if damage == 0: return
	flag_bits &= ~0x100; health = mini(health - damage, max_health)
	if health < 0:
		health = -1; flag_bits |= 0x10
		if (flag_bits & 2) != 0: sub = 8; control = 4; start_record = 0; timer = 0x3C
		else: top = 2
	elif (flag_bits & 2) != 0:
		flag_bits |= 0x10; var reacted := false
		for step_bits in [[0x20, 1], [0x40, 2], [0x80, 3]]:
			if (flag_bits & int(step_bits[0])) == 0 and health < (max_health >> int(step_bits[1])): sub = 6; control = 3; start_record = 0; flag_bits |= int(step_bits[0]); reacted = true
		if not reacted: sub = 7; control = 5; start_record = 0; timer = 0x96; flag_bits = (flag_bits | 0x100) & 0xFFEB
func _volumes() -> void:
	var centers: Array[Vector3] = [_joint(1), _joint(2, Vector3(0, -0x100, -0x480)), _joint(3, Vector3(0, 0x100, -0x480))]
	_set_volume(56, 0, 0); shape.global_position = centers[0]
	for index in 2: (volumes[index].shape as SphereShape3D).radius = 56.0 / 256.0; volumes[index].global_position = centers[index + 1]
	collision_layer = 8 if (flag_bits & 1) != 0 else 0
	var damage_flags := 0x20000 if control in [0, 2, 6] else 0x10000 if sub == 8 else 0x200000
	var arm_flags := 0xA00000 if (flag_bits & 8) != 0 else 0x810000 if sub == 8 else 0x820000
	if (flag_bits & 1) == 0: return
	for index in 3:
		var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape.shape if index == 0 else volumes[index - 1].shape; query.transform = Transform3D(Basis.IDENTITY, centers[index]); query.collision_mask = target.collision_layer; query.exclude = [get_rid()]
		for hit in get_world_3d().direct_space_state.intersect_shape(query):
			if hit["collider"] == target: contact_hit.emit(self, int(attributes[1]), damage_flags if index == 0 else arm_flags); return
func _final() -> void:
	Explosion.spawn(self, _joint(1, Vector3(0, 0, -0x400)), 0x100, 0x20)
	drop_requested.emit(self, _drops()); _finish()
