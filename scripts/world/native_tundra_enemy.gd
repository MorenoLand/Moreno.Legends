extends CharacterBody3D
signal died(actor: CharacterBody3D)
signal sound_requested(sound_id: int, point: Vector3)
signal drop_requested(actor: CharacterBody3D, entries: Array)
var source: Dictionary = {}
var target: CharacterBody3D
var host: Node
var model: Node3D
var clock: NativeAnimation
var health := 1
var native_state := 0
var native_yaw := 0
var desired_yaw := 0
var turn_direction := 0
var timer := 0
var elapsed := 0.0
var initialized := false
var native_speed := 0
var native_vertical := 0
var vertical_acceleration := 0
var random_state := 0
var dying := false
var collision: CollisionShape3D
var blocked := false
var pickup_data: Dictionary = {}
var carrier: CharacterBody3D
var thrown := false
var thrown_bounces := 0
var thrown_hits: Dictionary = {}
var removed := false
var hit_center: Vector3:
	get: return collision.global_position if is_instance_valid(collision) else global_position
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, directory: String) -> bool:
	host = gameplay; source = entry; target = host.player; health = int(entry["source_attributes"][0]); native_yaw = int(entry["transform_raw"][3]); desired_yaw = native_yaw
	var pickups: Variant = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join("pickups.json"))) if FileAccess.file_exists(directory.path_join("pickups.json")) else null
	if pickups is Dictionary: pickup_data = pickups
	var packed := load(directory.path_join(str(entry["model_file"]))) as PackedScene
	if packed == null: return false
	model = packed.instantiate() as Node3D
	if model == null: return false
	add_child(model); preload("res://scripts/world/native_material.gd").apply(model, 128.0); var point: Array = entry["transform"]["position"]; position = Vector3(float(point[0]), float(point[1]), float(point[2])); rotation.y = -float(native_yaw) * TAU / 4096.0; clock = preload("res://scripts/world/native_animation.gd").new(); clock.name = "NativeAnimationClock"; add_child(clock); clock.configure(model.find_child("AnimationPlayer", true, false) as AnimationPlayer, metadata.get("animations", [])); clock.automatic = false
	var bounds: Array = entry["native_hitbox"]["bounds_raw"]; var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0; var shape := BoxShape3D.new(); shape.size = maximum - minimum; collision = CollisionShape3D.new(); collision.shape = shape; collision.position = (minimum + maximum) * 0.5; add_child(collision); collision_layer = 8; collision_mask = 3; add_to_group("lift_targets"); _control(0); return true
func _physics_process(delta: float) -> void:
	if not is_instance_valid(host) or not is_instance_valid(target) or not target.is_physics_processing() or not is_visible_in_tree() or bool(host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _tick()
func _tick() -> void:
	if removed: return
	clock.native_tick()
	if dying: removed = true; drop_requested.emit(self, _drops()); died.emit(self); queue_free(); return
	if is_instance_valid(carrier): global_position = carrier.lift_anchor((collision.shape as BoxShape3D).size.y); rotation.y = carrier.player_model.rotation.y; return
	if thrown: _throw_tick(); return
	match native_state:
		0:
			if not initialized: initialized = true; native_speed = 0; _control(0)
			elif (clock.record_flags & 128) != 0: _wander_choice()
		1:
			_turn(desired_yaw, 32); _move(native_speed)
			if blocked:
				if turn_direction == 0: turn_direction = 32 if (_random() & 1) != 0 else -32
				desired_yaw = (desired_yaw + turn_direction) & 4095
			elif (clock.record_flags & 128) != 0 and (_random() & 1) != 0: _state(0)
		2:
			if not initialized: initialized = true; native_speed = -480; _control(9)
			_turn(desired_yaw, 64); _move(native_speed)
			if blocked: desired_yaw = native_yaw
			if timer > 0: timer -= 1
			else:
				var close := global_position.distance_to(target.global_position) * 256.0 < 512.0; timer = 64 if close else 16; desired_yaw = (desired_yaw + (1024 if close else 512) * (1 if (_random() & 1) != 0 else -1)) & 4095
			if global_position.distance_to(target.global_position) * 256.0 > 4096.0 and (clock.record_flags & 128) != 0: _state(0)
		3:
			if not initialized: initialized = true; vertical_acceleration = 64; _control(7)
			if _air_move(): _state(2)
		4:
			if not initialized: initialized = true; native_speed = 512; vertical_acceleration = 64; _control(2)
			if _air_move(): native_speed >>= 1; native_vertical = -native_vertical >> 1; timer += 1; _control(3 if timer == 1 else 4); native_state = 5
		5:
			if _air_move(): timer += 1; native_speed >>= 1; native_vertical = -native_vertical >> 1
			if timer >= 3 and native_vertical <= 64: _state(2)
	if native_state in [0, 1]:
		var angle := _bearing(target.global_position); var difference := (native_yaw - angle + 2048) & 4095; difference -= 2048; var cone := 1536 if clock.current_control == 1 else 1024
		if absi(difference) < cone and global_position.distance_to(target.global_position) * 256.0 < 1024.0: desired_yaw = (native_yaw + (1024 if difference < 0 else -1024)) & 4095; _state(2)
func _wander_choice() -> void:
	if (_random() & 3) == 0: _control(1); return
	if (_random() & 15) == 0: _control(0); return
	desired_yaw = (native_yaw + (_random() & 1023) - 512) & 4095; var fast := (_random() & 1) != 0; native_speed = -256 if fast else -64; _control(9 if fast else 8); _state(1)
func receive_hit(damage: int, flags: int, incoming_direction: Vector3 = Vector3.ZERO) -> bool:
	if dying: return false
	if (flags & 0x40000) != 0 or (flags & 0xFFF) != 0: health -= damage
	if health < 0: dying = true; collision_layer = 0; return true
	native_yaw = (_bearing(global_position + incoming_direction) + 2048) & 4095; desired_yaw = native_yaw; native_vertical = -clampi(damage, 32, 48) * 16; sound_requested.emit(0x8D, global_position); _state(4); return true
func can_lift() -> bool: return not dying and health >= 0 and not is_instance_valid(carrier) and not thrown and native_state in [0, 1, 2]
func begin_lift(player: CharacterBody3D) -> bool:
	if not can_lift(): return false
	carrier = player; collision_layer = 0; velocity = Vector3.ZERO; _control(6); return true
func release_lift(direction: Vector3, vertical_raw: int, forward_raw: int) -> void:
	carrier = null; thrown = true; thrown_bounces = 0; thrown_hits.clear(); collision_layer = 8; native_yaw = roundi(atan2(direction.x, direction.z) * 4096.0 / TAU) & 4095; velocity = direction * absf(float(forward_raw)) * 25.0 / 4096.0 + Vector3.UP * -float(vertical_raw) * 25.0 / 4096.0
func _throw_tick() -> void:
	var hit := move_and_collide(velocity / 25.0); velocity.y -= 64.0 * 25.0 / 4096.0; var query := PhysicsShapeQueryParameters3D.new(); query.shape = collision.shape; query.transform = collision.global_transform; query.collision_mask = 8; query.exclude = [get_rid()]
	for candidate: Dictionary in get_world_3d().direct_space_state.intersect_shape(query):
		var other: Node = candidate["collider"]
		if other.has_method("receive_hit") and not thrown_hits.has(other.get_instance_id()): thrown_hits[other.get_instance_id()] = true; other.receive_hit(int(source["source_attributes"][8]), 0x40000, velocity.normalized())
	if hit == null: return
	velocity = velocity.bounce(hit.get_normal()) * 0.5
	if hit.get_normal().y > 0.65:
		thrown_bounces += 1
		if thrown_bounces >= 3: thrown = false; velocity = Vector3.ZERO; _state(2)
		else: _control(2)
func _state(value: int) -> void: native_state = value; initialized = false; timer = 0; turn_direction = 0
func _control(value: int) -> void: clock.play_control(value, 0, true)
func _random() -> int: random_state = (((random_state << 1) + (random_state >> 31) + 1) ^ 0x873CA9E5) & 0xFFFFFFFF; return random_state
func _bearing(point: Vector3) -> int: return preload("res://scripts/world/native_talk_facing.gd")._heading(global_position, point)
func _turn(yaw: int, maximum: int) -> void: var difference := (yaw - native_yaw + 2048) & 4095; native_yaw = (native_yaw + clampi(difference - 2048, -maximum, maximum)) & 4095; rotation.y = -float(native_yaw) * TAU / 4096.0
func _move(speed: int) -> void:
	var heading := float(native_yaw) * TAU / 4096.0; var motion := Vector3(-sin(heading), 0, cos(heading)) * float(speed) / 4096.0; var result: Dictionary = preload("res://scripts/world/native_actor_motion.gd").move_actor(self, motion, source["native_hitbox"]["bounds_raw"]); blocked = bool(result.get("blocked", false))
func _air_move() -> bool:
	var heading := float(native_yaw) * TAU / 4096.0; var motion := Vector3(-sin(heading) * float(native_speed), -float(native_vertical), cos(heading) * float(native_speed)) / 4096.0; var result: Dictionary = preload("res://scripts/world/native_actor_motion.gd").move_actor(self, motion, source["native_hitbox"]["bounds_raw"]); native_vertical += vertical_acceleration; return bool(result.get("grounded", false)) and native_vertical >= 0
func _drops() -> Array:
	if pickup_data.is_empty(): return []
	var profile := int(source["source_attributes"][5])
	if profile >= pickup_data["profiles"].size(): return []
	var row: Array = pickup_data["profiles"][profile]; var entries: Array = []
	for group in range(3):
		for type in range(7):
			for item in range(int(row[group * 8 + type])):
				if group > 0 and (_random() & 255) > int(row[group * 8 + 7]): continue
				var yaw := _random() & 4095; var vertical := -512 - ((type + (_random() & 15) - 8) << 5); var forward := 256 - ((type + (_random() & 15) - 8) << 5); var angle := float(yaw) * TAU / 4096.0; entries.append({"group": group, "type": type, "value": int(pickup_data["values"][group][type]), "position": global_position, "yaw_raw": yaw, "velocity": Vector3(sin(angle) * forward, -vertical, -cos(angle) * forward) * 25.0 / 4096.0})
	return entries
