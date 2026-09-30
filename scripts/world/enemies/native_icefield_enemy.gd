extends CharacterBody3D
signal sound_requested(sound_id: int, point: Vector3)
signal drop_requested(actor: CharacterBody3D, entries: Array)
signal contact_hit(actor: CharacterBody3D, damage: int, flags: int)
const Motion := preload("res://scripts/world/actors/native_actor_motion.gd")
static var bios_seed := 1
var source: Dictionary = {}
var host: Node
var target: CharacterBody3D
var model: Node3D
var clock: NativeAnimation
var materials: Array[ShaderMaterial] = []
var bounds: Array = []
var attributes: Array = []
var pickup_data: Dictionary = {}
var health := 0
var max_health := 0
var top := 0
var sub := 0
var step := 0
var start_record := 0
var control := 0
var control_at_start := 0
var native_yaw := 0
var speed := 0
var vertical := 0
var airborne := false
var flags := 0
var hit_word := 0
var hit_damage := 0
var stagger_count := 0
var elapsed := 0.0
var random_state := 0
var removed := false
var scale_raw := Vector3(512, 512, 512)
var base_scale := Vector3.ONE
var shape: CollisionShape3D
var shape_height := 0.0
var shape_radius := 0.0
var hit_center: Vector3:
	get: return shape.global_position if is_instance_valid(shape) else global_position
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	host = gameplay; source = entry; target = host.player; attributes = entry["source_attributes"]; bounds = entry["native_hitbox"]["bounds_raw"]; max_health = int(attributes[0]); health = max_health; native_yaw = int(entry["transform"]["yaw_raw"]) & 4095
	var pickups: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/%s/pickups.json" % str(entry["stage"]))) if FileAccess.file_exists("res://assets/levels/%s/pickups.json" % str(entry["stage"])) else null
	if pickups is Dictionary: pickup_data = pickups
	var packed := load(path) as PackedScene
	if packed == null: return false
	model = packed.instantiate() as Node3D
	if model == null: return false
	var raw: Array = metadata.get("native_scale_raw", [512, 512, 512]); scale_raw = Vector3(float(raw[0]), float(raw[1]), float(raw[2])); base_scale = scale_raw / 512.0
	add_child(model); preload("res://scripts/world/rendering/native_material.gd").apply(model, 128.0)
	for node in model.find_children("*", "MeshInstance3D", true, false):
		for surface in range((node as MeshInstance3D).mesh.get_surface_count()):
			var material := (node as MeshInstance3D).get_active_material(surface) as ShaderMaterial
			if material != null: materials.append(material)
	var point: Array = entry["transform"]["position"]; position = Vector3(float(point[0]), float(point[1]), float(point[2])); rotation.y = -float(native_yaw) * TAU / 4096.0
	clock = preload("res://scripts/world/actors/native_animation.gd").new(); clock.name = "NativeAnimationClock"; add_child(clock); clock.configure(model.find_child("AnimationPlayer", true, false) as AnimationPlayer, metadata.get("animations", [])); clock.automatic = false
	shape = CollisionShape3D.new(); shape.shape = CapsuleShape3D.new(); add_child(shape); collision_layer = 0; collision_mask = 0; random_state = int(Time.get_ticks_usec()) & 0xFFFFFFFF
	return true
func _physics_process(delta: float) -> void:
	if not is_instance_valid(host) or not is_instance_valid(target) or not target.is_physics_processing() or bool(host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and not removed: elapsed -= 1.0; _tick()
func _tick() -> void:
	control_at_start = control; _set_light(128.0); _run()
	if stagger_count < 0: stagger_count += 1
	if not removed and top != 4: _animate()
func _run() -> void: pass
func _animate() -> void:
	if control == control_at_start: clock.native_tick()
	else: clock.play_control(control, start_record, true); start_record = 0
func _set_light(value: float) -> void:
	for material in materials: material.set_shader_parameter("light_rgb", Vector3(value, value, value))
func _set_scale(x: int, y: int, z: int) -> void: model.scale = Vector3(float(x), float(y), float(z)) / 512.0 * base_scale
func _set_volume(radius_raw: int, low_raw: int, high_raw: int) -> void:
	shape_radius = float(radius_raw) / 256.0; shape_height = float(high_raw - low_raw) / 256.0 + shape_radius * 2.0; (shape.shape as CapsuleShape3D).radius = shape_radius; (shape.shape as CapsuleShape3D).height = shape_height; shape.position = Vector3(0, float(low_raw + high_raw) * 0.5 / 256.0, 0)
func _register(mode: int) -> void:
	hit_word = 0; hit_damage = 0
	if mode == 0: _set_volume(60, 48, 192)
	else: _set_volume(96, 64, 228)
	collision_layer = 8
	if mode > 1: return
	var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape.shape; query.transform = shape.global_transform; query.collision_mask = target.collision_layer; query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(self, int(attributes[1 + mode]), 0x20000 if mode == 0 else 0xA0000); return
func _unregister() -> void: collision_layer = 0
func receive_hit(damage: int, hit_flags: int, _direction: Vector3 = Vector3.ZERO) -> bool:
	if collision_layer == 0: return false
	hit_word |= hit_flags & 0xFFFFF000; hit_damage = mini(hit_damage + damage, 0xFFF); return true
func _damage_check() -> int:
	flags &= ~8; var damage := hit_damage if (hit_word & 0x1D0000) != 0 else 0
	if damage == 0: return 0
	_set_light(248.0); sound_requested.emit(0x8D, global_position); hit_damage = 0
	health = mini(health - damage, max_health)
	if health < 0: health = -1; return -1
	if stagger_count >= 0:
		stagger_count += 1
		if damage >= 32 or stagger_count >= 8: stagger_count = -16; flags |= 8
	return 1
func _step(vertical_raw: int, forward_raw: int) -> Dictionary:
	var heading := float(native_yaw) * TAU / 4096.0; var motion := Vector3(-sin(heading) * float(forward_raw), -float(vertical_raw), cos(heading) * float(forward_raw)) / 4096.0
	return Motion.move_actor(self, motion, bounds)
func _resolve(result: Dictionary) -> int:
	if airborne:
		if bool(result.get("grounded", false)): airborne = false; return 0
		return 2 if bool(result.get("blocked", false)) else 0
	if bool(result.get("blocked", false)): return 2
	if not bool(result.get("floor", false)): airborne = true; return 1
	return 0
func _reflect(yaw: int) -> int:
	var heading := float(native_yaw) * TAU / 4096.0; var forward := Vector3(-sin(heading), 0, cos(heading)) * (-1.0 if speed < 0 else 1.0)
	var hit := Motion.ray(self, global_position + Vector3.UP * 0.5, global_position + Vector3.UP * 0.5 + forward * 2.0)
	if hit.is_empty(): return (yaw + 2048) & 4095
	var normal: Vector3 = hit["normal"]
	return (-yaw) & 4095 if absf(normal.x) > absf(normal.z) else (2048 - yaw) & 4095
func _distance() -> float: return Vector2(global_position.x - target.global_position.x, global_position.z - target.global_position.z).length() * 256.0
func _bearing() -> int: return preload("res://scripts/world/actors/native_talk_facing.gd")._heading(global_position, target.global_position)
func _turn(yaw: int, maximum: int) -> void: var difference := (yaw - native_yaw + 2048) & 4095; native_yaw = (native_yaw + clampi(difference - 2048, -maximum, maximum)) & 4095; rotation.y = -float(native_yaw) * TAU / 4096.0
func _face(yaw: int) -> void: native_yaw = yaw & 4095; rotation.y = -float(native_yaw) * TAU / 4096.0
func _random() -> int: random_state = (((random_state << 1) + (random_state >> 31) + 1) ^ 0x873CA9E5) & 0xFFFFFFFF; return random_state
func _bios_rand() -> int: bios_seed = (bios_seed * 0x41C64E6D + 0x3039) & 0xFFFFFFFF; return (bios_seed >> 16) & 0x7FFF
func _sound(id: int) -> void: sound_requested.emit(id, global_position)
func _drops() -> Array:
	if pickup_data.is_empty(): return []
	var profile := int(attributes[5])
	if profile >= pickup_data["profiles"].size(): return []
	var row: Array = pickup_data["profiles"][profile]; var entries: Array = []
	for group in range(3):
		for type in range(7):
			for item in range(int(row[group * 8 + type])):
				if group > 0 and (_random() & 255) > int(row[group * 8 + 7]): continue
				entries.append({"group": group, "type": type, "value": int(pickup_data["values"][group][type]), "position": global_position})
	for entry: Dictionary in entries:
		var type := int(entry["type"]); var yaw := _random() & 4095; var upward := -512 - ((type + (_random() & 15) - 8) << 5); var forward := 256 - ((type + (_random() & 15) - 8) << 5); var angle := float(yaw) * TAU / 4096.0; entry["yaw_raw"] = yaw; entry["velocity"] = Vector3(sin(angle) * forward, -upward, -cos(angle) * forward) * 25.0 / 4096.0
	return entries
func _finish() -> void: removed = true; remove_from_group("lock_targets"); queue_free()
