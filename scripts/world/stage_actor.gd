extends CharacterBody3D
signal died(actor: CharacterBody3D)
signal sound_requested(sound_id: int, point: Vector3)
signal contact_hit(actor: CharacterBody3D, damage: int, flags: int)
signal drop_requested(actor: CharacterBody3D, entries: Array)
static var random_state: int = 0
const TICK_RATE := 25.0
var model: Node3D
var animation_player: AnimationPlayer
var source: Dictionary = {}
var clips: Dictionary = {}
var target: CharacterBody3D
var skeleton: Skeleton3D
var collision: CollisionShape3D
var actor_class: int = 0
var dispatch: int = 0
var health: int = 0
var max_health: int = 0
var contact_damage: int = 0
var charge_damage: int = 0
var attack_damage: int = 0
var attack_effect_state: int = -1
var attack_effect_timer: int = 0
var attack_effect_radius: int = 3
var attack_effect_visual: MeshInstance3D
var attack_effect_tick := 16
var native_state: int = 0
var initialized: bool = false
var mode: int = 0
var hit_count: int = 3
var native_yaw: int = 0
var region_yaw: int = 0
var native_speed: int = 0
var target_yaw: int = 0
var patrol_yaw: int = 0
var patrol_bins: int = 0
var patrol_distance: int = 0
var timer: int = 0
var cooldown: int = 0
var attack_phase: int = 0
var current_control: int = -1
var control_tick: int = 0
var control_frame: int = 0
var control_remaining: int = 0
var control_ended: bool = false
var origin: Vector3
var tick_accumulator: float = 0.0
var dying: bool = false
var removed: bool = false
var native_box := AABB()
var flash_ticks := 0
var native_materials: Array[ShaderMaterial] = []
var pickup_data: Dictionary = {}
var carrier: CharacterBody3D
var carried_state := 0
var thrown := false
var thrown_hits: Dictionary = {}
var thrown_bounces := 0
func configure(entry: Dictionary, metadata: Dictionary, directory: String) -> void:
	source = entry
	var pickup_path := directory.path_join("pickups.json")
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(pickup_path)) if FileAccess.file_exists(pickup_path) else null
	if data is Dictionary: pickup_data = data
	var record := str(entry["source_bytes_hex"]).hex_decode()
	actor_class = record[4]
	dispatch = record[6] & 15
	native_yaw = int(entry["transform"]["yaw_raw"]) & 4095
	region_yaw = native_yaw
	patrol_yaw = native_yaw
	patrol_bins = record[9] - 256 if record[9] > 127 else record[9]
	match actor_class:
		5:
			native_state = [3, 0, 12, 10, 1, 2, 13][dispatch]
			mode = [0, 0, 2, 1, 0, 0, 2][dispatch]
			if dispatch in [0, 1, 3] and patrol_bins != 0: mode = 3
			native_speed = -384 if dispatch in [0, 1, 2] else 0
			if dispatch == 3: patrol_yaw = 0
			native_box = AABB(Vector3(-32, 0, -32) / 256.0, Vector3(64, 160, 64) / 256.0)
		8:
			native_box = AABB(Vector3(-64, 0, -64) / 256.0, Vector3(128, 512, 128) / 256.0)
		7:
			native_box = AABB(Vector3(-250, 0, -250) / 256.0, Vector3(500, 300, 500) / 256.0)
		_:
			set_physics_process(false)
			return
	var attributes: Array = entry["source_attributes"]
	var health_scale := 1 if actor_class == 5 else 4
	max_health = int(attributes[0]) * health_scale
	contact_damage = int(attributes[1]) * health_scale
	charge_damage = int(attributes[2]) if actor_class == 5 else 0
	attack_damage = int(attributes[2]) * 4 if actor_class == 8 else 0
	health = max_health
	var scene := load(directory.path_join(str(entry["model_file"]))) as PackedScene
	if scene == null: return
	model = scene.instantiate() as Node3D
	add_child(model)
	preload("res://scripts/world/native_material.gd").apply(model, 128.0)
	for node in model.find_children("*", "MeshInstance3D", true, false):
		for surface in range((node as MeshInstance3D).mesh.get_surface_count()):
			var material := (node as MeshInstance3D).get_active_material(surface) as ShaderMaterial
			if material != null: native_materials.append(material)
	var coordinates: Array = entry["transform"]["position"]
	position = Vector3(float(coordinates[0]), -float(coordinates[1]), float(coordinates[2]))
	origin = global_position if actor_class == 5 and dispatch == 2 else Vector3.ZERO
	rotation.y = float(native_yaw) * TAU / 4096.0
	var players := model.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty(): animation_player = players[0] as AnimationPlayer
	var skeletons := model.find_children("*", "Skeleton3D", true, false)
	if not skeletons.is_empty(): skeleton = skeletons[0] as Skeleton3D
	for clip: Dictionary in metadata.get("animations", []): clips[int(clip["slot"])] = clip
	play_control(int(entry["startup_control"]["code"]))
	var shape := BoxShape3D.new()
	shape.size = native_box.size
	collision = CollisionShape3D.new()
	collision.shape = shape
	collision.position = native_box.get_center()
	add_child(collision)
	collision_layer = 8
	collision_mask = 3
	if actor_class == 5: add_to_group("lift_targets")
func can_lift() -> bool:
	if actor_class != 5 or dying or removed or carrier != null or thrown: return false
	var query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 0.125, global_position + Vector3.DOWN * 0.1875, 1, [get_rid()])
	return not get_world_3d().direct_space_state.intersect_ray(query).is_empty()
func begin_lift(player: CharacterBody3D) -> bool:
	if not can_lift(): return false
	carrier = player
	carried_state = native_state
	collision_layer = 0
	velocity = Vector3.ZERO
	play_control(5)
	return true
func release_lift(direction: Vector3, vertical_raw: int, forward_raw: int) -> void:
	carrier = null
	thrown = true
	thrown_hits.clear()
	thrown_bounces = 0
	collision_layer = 8
	native_yaw = roundi(atan2(direction.x, direction.z) * 4096.0 / TAU) & 4095
	velocity = direction * absf(float(forward_raw)) * TICK_RATE / 4096.0 + Vector3.UP * -float(vertical_raw) * TICK_RATE / 4096.0
	play_control(5)
func _throw_tick() -> void:
	var hit := move_and_collide(velocity / TICK_RATE)
	velocity.y -= 64.0 * TICK_RATE / 4096.0
	_update_collision()
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = collision.shape
	query.transform = collision.global_transform
	query.collision_mask = 8
	query.exclude = [get_rid()]
	for candidate in get_world_3d().direct_space_state.intersect_shape(query):
		var actor: Node = candidate["collider"]
		if actor.has_method("receive_hit") and not thrown_hits.has(actor.get_instance_id()):
			thrown_hits[actor.get_instance_id()] = true
			actor.receive_hit(int(source["source_attributes"][8]), 0x40000, velocity.normalized())
	if hit == null: return
	sound_requested.emit(0xc4, global_position)
	velocity = velocity.bounce(hit.get_normal()) * 0.5
	if hit.get_normal().y > 0.65:
		if thrown_bounces > 0:
			thrown = false
			velocity = Vector3.ZERO
			_set_state(carried_state)
		else: thrown_bounces += 1; play_control(2)
func play_control(slot: int) -> void:
	if slot == current_control or not clips.has(slot): return
	current_control = slot
	control_tick = 0
	control_frame = 0
	control_ended = false
	control_remaining = int(clips[slot]["records"][0]["duration"])
	if animation_player == null: return
	var entry: Dictionary = clips[slot]
	var clip := str(entry["name"])
	if not animation_player.has_animation(clip): return
	var animation := animation_player.get_animation(clip)
	animation.loop_mode = Animation.LOOP_LINEAR if int(entry["records"][-1]["flags"]) != 255 else Animation.LOOP_NONE
	animation_player.play(clip)
	animation_player.speed_scale = 0.0
	animation_player.seek(0.0, true)
func _physics_process(delta: float) -> void:
	if target == null or removed or not target.is_physics_processing(): return
	tick_accumulator += delta
	while tick_accumulator >= 1.0 / TICK_RATE:
		tick_accumulator -= 1.0 / TICK_RATE
		if is_instance_valid(carrier):
			global_position = carrier.lift_anchor(native_box.size.y)
			rotation.y = carrier.player_model.rotation.y
			_advance_control()
			_update_collision()
			continue
		if thrown:
			_throw_tick()
			_advance_control()
			continue
		if dying: _death_tick()
		elif actor_class == 5: _class_five_tick()
		else: _class_eight_tick()
		if removed: return
		_update_hit_light()
		rotation.y = float(native_yaw) * TAU / 4096.0
		_advance_control()
		_update_collision()
		if actor_class == 8: _tick_attack_effect()
		if not dying: _register_contact()
func _next_random() -> int:
	random_state = ((((random_state << 1) & 0xffffffff) + (random_state >> 31) + 1) ^ 0x873ca9e5) & 0xffffffff
	return random_state
func _angle_from(point: Vector3) -> int:
	var difference := global_position - point
	return roundi(atan2(difference.x, difference.z) * 4096.0 / TAU) & 4095
func _yaw_difference(yaw: int) -> int:
	var difference := (yaw - native_yaw) & 4095
	return difference - 4096 if difference > 2048 else difference
func _turn(yaw: int, step: int) -> void:
	var difference := _yaw_difference(yaw)
	native_yaw = (native_yaw + clampi(difference, -absi(step), absi(step)) * (1 if step >= 0 else -1)) & 4095
func _move_native(speed: int) -> void:
	var yaw := float(native_yaw) * TAU / 4096.0
	var motion := Vector3(sin(yaw), 0, cos(yaw)) * float(speed) / 4096.0
	var hit := move_and_collide(motion)
	if hit != null:
		var normal := hit.get_normal()
		if actor_class == 5 and native_state == 10:
			patrol_yaw = (patrol_yaw + 2048) & 4095
			native_speed = 0
			patrol_bins = (int(str(source["source_bytes_hex"]).hex_decode()[9]) * 2)
		elif actor_class == 5 and native_state in [4, 12]:
			if absf(normal.x) > absf(normal.z): native_yaw = (-native_yaw) & 4095
			else: native_yaw = (2048 - native_yaw) & 4095
	var floor_query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 0.125, global_position + Vector3.DOWN * 0.1875, 1, [get_rid()])
	var floor_hit := get_world_3d().direct_space_state.intersect_ray(floor_query)
	if not floor_hit.is_empty(): global_position.y = float(floor_hit["position"].y)
func _set_state(state: int) -> void:
	native_state = state
	initialized = false
	attack_phase = 0
func _class_five_tick() -> void:
	var distance := global_position.distance_to(target.global_position) * 256.0
	match native_state:
		1:
			if not initialized:
				initialized = true
				attack_phase = 0
				velocity = Vector3.DOWN * 64.0 / 4096.0
				play_control(2)
			var hit := move_and_collide(velocity)
			velocity.y -= 64.0 / 4096.0
			if hit != null and hit.get_normal().y > 0.65:
				sound_requested.emit(0xc4, global_position)
				if attack_phase == 0:
					attack_phase = 1
					native_yaw = ((_next_random() & 255) << 4) & 4095
					var yaw := float(native_yaw) * TAU / 4096.0
					velocity = Vector3(sin(yaw) * -128.0 / 4096.0, -velocity.y * 0.5, cos(yaw) * -128.0 / 4096.0)
				else:
					velocity = Vector3.ZERO
					_set_state([4, 10, 12, 4, 13][mode])
		3:
			native_speed = -384
			play_control(1)
			_set_state(4)
		4:
			if not initialized:
				initialized = true
				play_control(1)
			var desired := _angle_from(target.global_position)
			if distance < 500.0: desired = -desired
			elif distance < 700.0: desired += 1024 if (_next_random() & 1) else -1024
			native_speed = mini(native_speed + 16, -384) if native_speed < -384 else maxi(native_speed - 16, -384)
			_turn(desired, 32)
			_move_native(native_speed)
			if cooldown > 0: cooldown -= 1
			if cooldown == 0 and ((0x2c0 >> (_next_random() & 15)) & 1) and distance < 700.0: _set_state(7)
		7:
			if not initialized:
				initialized = true
				timer = 90
				cooldown = [60, 90, 60, 120, 60, 120, 60, 90, 60, 90, 60, 120, 60, 120, 60, 90][_next_random() & 15]
				play_control(0)
			if attack_phase == 0:
				native_yaw = _angle_from(target.global_position)
				var scale_raw := 512 + ((timer & 1) << 5)
				model.scale = Vector3(float(scale_raw) / 512.0, float(512 - ((timer & 1) << 5)) / 512.0, float(scale_raw) / 512.0)
				timer -= 1
				if timer == 0:
					attack_phase = 1
					model.scale = Vector3.ONE
			elif attack_phase == 1:
				attack_phase = 2
				timer = 15
				native_yaw = _angle_from(target.global_position)
				native_speed = -768
				play_control(3)
				sound_requested.emit(0xa6, global_position)
			if attack_phase == 2:
				_move_native(native_speed)
				timer -= 1
				if timer == 0: _set_state(3)
		10:
			if not initialized:
				initialized = true
				play_control(1)
			if native_yaw != patrol_yaw:
				native_speed = mini(native_speed + 16, 0)
				if native_speed == 0: _turn(patrol_yaw, 64)
			else: native_speed = maxi(native_speed - 16, -576)
			var previous := global_position
			_move_native(native_speed)
			if floori(previous.x * 2) != floori(global_position.x * 2) or floori(previous.z * 2) != floori(global_position.z * 2):
				patrol_bins -= 1
				if patrol_bins < 0:
					patrol_yaw = (patrol_yaw + 2048) & 4095
					patrol_bins = int(str(source["source_bytes_hex"]).hex_decode()[9]) * 2
		12:
			if not initialized:
				initialized = true
				play_control(1)
			native_speed = maxi(native_speed - 16, -384)
			_turn(_angle_from(origin), [0, 32, 0, 32, 96, 32, 64, 32, 32, 48, 32, 48, 32, 0, 32, 0][_next_random() & 15])
			_move_native(native_speed)
			if distance < 700.0:
				mode = 0
				_set_state(4)
		14:
			if not initialized:
				initialized = true
				model.scale = Vector3.ONE
				native_speed = 0
				play_control(0)
				sound_requested.emit(0x8d, global_position)
			elif control_ended: _set_state([4, 10, 12, 4, 13][mode])
		15:
			if not initialized:
				initialized = true
				timer = 6
				hit_count = 3
				play_control(2)
				sound_requested.emit(0x8d, global_position)
			_move_native(-672)
			timer -= 1
			if timer == 0: _set_state([4, 10, 12, 4, 13][mode])
func _inside_eight_region(bounds: Vector4, offset_raw: int = 0) -> bool:
	var yaw := float(region_yaw) * TAU / 4096.0
	var difference := (global_position - target.global_position) * 256.0 + Vector3(sin(yaw), 0, cos(yaw)) * float(offset_raw)
	var local := Vector2(difference.x * cos(yaw) - difference.z * sin(yaw), difference.x * sin(yaw) + difference.z * cos(yaw))
	return bounds.x < local.x and local.x < bounds.z and bounds.y < local.y and local.y < bounds.w
func _class_eight_tick() -> void:
	var attack_region := Vector4(-768, -768, 768, 768)
	var corridor := Vector4(-256, 0, 256, 3072)
	match native_state:
		0, 2:
			if not initialized:
				initialized = true
				timer = _next_random() & 255
				play_control(1)
			if native_state == 2:
				var desired := _angle_from(target.global_position)
				if absi(_yaw_difference(desired)) > 32:
					_turn(desired, 32)
					play_control(4)
				else:
					native_yaw = desired
					play_control(1)
				target_yaw = desired
			timer = (timer + 1) & 65535
			if _inside_eight_region(attack_region): _set_state(3)
			elif native_state == 0 and _inside_eight_region(corridor, patrol_distance): _set_state(1)
			elif global_position.distance_to(target.global_position) * 256.0 < 1536.0 and (timer & 31) == 0: _set_state(4)
		1:
			if not initialized:
				initialized = true
				play_control(0)
			_move_native(-192)
			patrol_distance += 12
			if _inside_eight_region(attack_region): _set_state(3)
			elif not _inside_eight_region(corridor, patrol_distance): _set_state(0)
			elif patrol_distance >= 2560: _set_state(2)
		3:
			if not initialized:
				initialized = true
				play_control(3)
			if not _inside_eight_region(attack_region): _set_state(2 if patrol_distance >= 2560 else 0)
		4:
			if not initialized:
				initialized = true
				timer = 128
				play_control(2)
			timer -= 1
			if timer == 0 or _inside_eight_region(attack_region) or global_position.distance_to(target.global_position) * 256.0 >= 1536.0: _set_state(2 if patrol_distance >= 2560 else 0)
		255:
			if not initialized:
				initialized = true
				play_control(7)
			elif control_ended: _set_state(2 if patrol_distance >= 2560 else 0)
func receive_hit(damage: int, source_flags: int, incoming_direction: Vector3 = Vector3.ZERO) -> bool:
	if dying or removed or damage <= 0: return false
	if actor_class == 5:
		if native_state in [14, 15] and initialized: return false
		if source_flags & 0x1c0000:
			hit_count -= 1
			_set_state(14)
			if incoming_direction.length_squared() > 0.0: target_yaw = roundi(atan2(-incoming_direction.x, -incoming_direction.z) * 4096.0 / TAU) & 4095
		elif not (source_flags & 0x7000000): return false
	elif actor_class == 8 and not (source_flags & 0x40000): return false
	health = mini(health - damage, max_health)
	flash_ticks = 1
	_set_hit_light(Vector3(248, 248, 248))
	if health < 0:
		health = -1
		dying = true
		initialized = false
		model.scale = Vector3.ONE
		play_control(2 if actor_class == 5 else 7)
		collision_layer = 0
		if actor_class == 5: native_yaw = target_yaw
	elif actor_class == 5 and hit_count <= 0:
		native_yaw = target_yaw
		_set_state(15)
	elif actor_class == 8:
		sound_requested.emit(0x8e if health < (max_health >> 1) else 0x8d, global_position)
		if health < (max_health >> 1): _set_state(255)
	return true
func _set_hit_light(color: Vector3) -> void:
	for material in native_materials: material.set_shader_parameter("light_rgb", color)
func _update_hit_light() -> void:
	_set_hit_light(Vector3(248, 248, 248) if flash_ticks > 0 else Vector3(160, 128, 128) if dying and actor_class == 5 and (timer & 1) else Vector3(248, 248, 248) if dying and actor_class == 5 else Vector3(248, 128, 128) if dying else Vector3(128, 128, 128))
	flash_ticks = maxi(flash_ticks - 1, 0)
func _death_tick() -> void:
	if not initialized:
		initialized = true
		if actor_class == 5:
			var query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 0.125, global_position + Vector3.DOWN * 0.1875, 1, [get_rid()])
			timer = 20 if not get_world_3d().direct_space_state.intersect_ray(query).is_empty() else 8
		else: timer = 16
		var death_effect := preload("res://scripts/world/native_mine_death.gd").new(); get_parent().add_child(death_effect)
		var point := global_position + Vector3.UP * 96.0 / 256.0 if actor_class == 5 else skeleton.global_transform * skeleton.get_bone_global_pose(0).origin if skeleton != null else global_position
		death_effect.configure(point, 48 if actor_class == 5 else 128, timer, Callable(self, "_next_random")); death_effect.sound_requested.connect(func(sound_id: int, position: Vector3): sound_requested.emit(sound_id, position))
	timer -= 1
	if timer <= 0:
		removed = true
		drop_requested.emit(self, _drop_entries())
		died.emit(self)
		queue_free()
func _drop_entries() -> Array:
	if pickup_data.is_empty(): return []
	var profile := int(source["source_attributes"][5])
	if profile >= pickup_data["profiles"].size(): return []
	var row: Array = pickup_data["profiles"][profile]
	var entries: Array = []
	for group in range(3):
		for type in range(7):
			for item in range(int(row[group * 8 + type])):
				if group > 0 and (_next_random() & 255) > int(row[group * 8 + 7]): continue
				entries.append({"group": group, "type": type, "value": int(pickup_data["values"][group][type]), "position": global_position})
	for entry: Dictionary in entries:
		entry["yaw_raw"] = _next_random() & 4095
		var vertical := -512 - ((int(entry["type"]) + (_next_random() & 15) - 8) << 5)
		var forward := 256 - ((int(entry["type"]) + (_next_random() & 15) - 8) << 5)
		var yaw := float(entry["yaw_raw"]) * TAU / 4096.0
		entry["velocity"] = Vector3(sin(yaw) * forward, -vertical, -cos(yaw) * forward) * TICK_RATE / 4096.0
	return entries
func _advance_control() -> void:
	if not clips.has(current_control): return
	control_ended = false
	var clip: Dictionary = clips[current_control]
	var records: Array = clip["records"]
	control_remaining -= 1
	if control_remaining <= 0:
		var flags := int(records[control_frame]["flags"])
		if flags & 128:
			control_ended = true
			if flags != 255:
				control_frame = flags & 127
				control_tick = 0
				for index in range(control_frame): control_tick += int(records[index]["duration"])
		else: control_frame += 1
		control_frame = mini(control_frame, records.size() - 1)
		control_remaining = int(records[control_frame]["duration"])
		var event := int(records[control_frame]["event"])
		if actor_class == 5 and (event & 128): sound_requested.emit(0xa5, global_position)
		elif actor_class == 8 and current_control == 0 and int(records[control_frame]["pose"]) in [15, 31]: sound_requested.emit(0xd3, global_position)
	control_tick += 1
	if animation_player != null: animation_player.seek(float(control_tick) / 30.0, true)
func _update_collision() -> void:
	if collision == null: return
	var center := native_box.get_center()
	if skeleton != null and skeleton.get_bone_count() > 0: center += global_transform.affine_inverse() * (skeleton.global_transform * skeleton.get_bone_global_pose(0).origin)
	collision.position = center
func _register_contact() -> void:
	if collision == null: return
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = collision.shape
	query.transform = collision.global_transform
	query.collision_mask = target.collision_layer
	query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target:
			contact_hit.emit(self, charge_damage if actor_class == 5 and native_state == 7 and attack_phase == 2 else contact_damage, 0x180000 if actor_class == 5 and native_state == 7 and attack_phase == 2 else 0x20000)
			return
func _tick_attack_effect() -> void:
	if attack_effect_visual == null:
		attack_effect_visual = preload("res://scripts/world/native_mine_energy.gd").new(); add_child(attack_effect_visual); attack_effect_visual.configure(Callable(self, "_next_random"))
	var bound := native_state == 3 and not dying
	if attack_effect_state == -1:
		if not bound: attack_effect_visual.redraw(-1, 0, 0, 0); return
		attack_effect_state = 0
		attack_effect_timer = 8
		attack_effect_radius = 3
		attack_effect_tick = 16
		sound_requested.emit(0xd4, global_position)
	attack_effect_visual.global_position = collision.global_position - global_basis * native_box.get_center()
	attack_effect_visual.global_basis = Basis.IDENTITY
	attack_effect_visual.redraw(attack_effect_state, attack_effect_radius, attack_effect_timer, attack_effect_tick)
	attack_effect_tick = (attack_effect_tick + 1) & 255
	if attack_effect_state in [1, 2]:
		var shape := SphereShape3D.new()
		shape.radius = float(attack_effect_radius) / 16.0
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape
		query.transform = Transform3D(Basis.IDENTITY, collision.global_position - global_basis * native_box.get_center())
		query.collision_mask = target.collision_layer
		query.exclude = [get_rid()]
		for hit in get_world_3d().direct_space_state.intersect_shape(query):
			if hit["collider"] == target:
				contact_hit.emit(self, attack_damage, 0x100000)
				break
	if attack_effect_state == 2:
		if not bound:
			attack_effect_state = 3
			attack_effect_timer = 8
	else:
		if attack_effect_state == 1: attack_effect_radius += 2
		attack_effect_timer -= 1
		if attack_effect_timer <= 0:
			attack_effect_state += 1
			attack_effect_timer = 7 if attack_effect_state == 1 else 8
			if attack_effect_state == 4: attack_effect_state = -1
