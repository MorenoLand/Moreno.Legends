extends AnimatableBody3D
signal sound_requested(id: int, position: Vector3)
signal stat_delta_requested(delta: int)
signal message_requested(index: int, window: int)
const RandomSource := preload("res://scripts/world/actors/native_npc_behavior.gd")
var actor: Node3D
var player: Node3D
var profile: Dictionary = {}
var context: Dictionary = {}
var elapsed := 0.0
var pending_hit := false
var hit_queued := false
var motion_heading := 0
var visual_heading := 0
var pitch := 0
var roll := 0
var forward_speed := 0
var vertical_speed := 0
var spinning := false
var cooldown := 0
var kick_count := 0
var goal_timer := -1
var goal_second := false
var subtype := 0
var kind := ""
var duck_mode := 1
var duck_phase := 0
var queued_flags := 0
static func spawn_allowed(entry: Dictionary, state: Dictionary) -> bool:
	var source: Dictionary = entry.get("native_kickable", {})
	return not source.has("minimum_save_byte14") or int(state.get("native_save_byte14", 0)) >= int(source["minimum_save_byte14"])
func configure(target: Node3D, entry: Dictionary, state: Dictionary) -> bool:
	actor = target; context = state; profile = entry.get("native_kickable", {}); kind = str(profile.get("kind", "")); subtype = int(entry.get("variant", entry.get("resource_variant", 0))); visual_heading = int(entry.get("yaw_raw", entry.get("transform", {}).get("yaw_raw", 0))) & 4095
	var ancestor: Node = actor
	while ancestor != null and player == null: player = ancestor.get_node_or_null("Player") as Node3D; ancestor = ancestor.get_parent()
	var bounds: Array = profile.get("bounds_raw", [])
	if bounds.size() != 6 or kind not in ["can", "duck"]: return false
	var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
	box.size = maximum - minimum; shape.shape = box; shape.position = (minimum + maximum) * 0.5; add_child(shape); top_level = true; collision_layer = 8; collision_mask = 0; sync_to_physics = false; add_to_group("native_kickable_props"); _sync(); return true
func receive_hit(damage: int, flags: int, _direction: Vector3) -> bool:
	if goal_timer >= 0 or cooldown > 0: return false
	if kind == "duck":
		if duck_mode == 5 or ((flags & 0x80000) == 0 and (flags & 0x10000) == 0) or (damage & 0xFFF) == 0: return false
	elif (flags & 0x80000) == 0: return false
	hit_queued = true; queued_flags = flags; return true
func _physics_process(delta: float) -> void:
	if not is_instance_valid(actor): queue_free(); return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func _native_tick() -> void:
	if kind == "duck": _duck_tick(); return
	if goal_timer >= 0:
		if goal_timer > 0: goal_timer -= 1
		else:
			stat_delta_requested.emit(kick_count << 4); message_requested.emit(101 if goal_second else 100 if subtype == 0 else 102, 4); actor.queue_free(); return
		_sync(); return
	if cooldown > 0: cooldown -= 1; pending_hit = false
	elif pending_hit:
		pending_hit = false; cooldown = 10; forward_speed = 768; vertical_speed = 640 - _look_offset(); spinning = true; kick_count += 1; motion_heading = _player_heading()
		stat_delta_requested.emit(-16); _sound(0x297)
	if spinning or forward_speed != 0 or vertical_speed != 0:
		vertical_speed -= 48; _move_can()
		if spinning: pitch = (pitch + 320) & 4095; visual_heading = (visual_heading + 16) & 4095; roll = (roll + 160) & 4095
		actor.rotation = Vector3(-float(pitch), -float(visual_heading), float(roll)) * TAU / 4096.0
	else: _move_can()
	if _can_goal(): actor.visible = false; collision_layer = 0; goal_timer = 15; _sound(0x299)
	if hit_queued: pending_hit = true; hit_queued = false
	_sync()
func _look_offset() -> int:
	var pivot: Node3D = player.get("camera_pivot") as Node3D if is_instance_valid(player) else null
	return clampi(roundi(-(pivot.rotation.x - deg_to_rad(-12.0)) * 4096.0 / TAU), -0x200, 0x200) if is_instance_valid(pivot) else 0
func _player_heading() -> int:
	if not is_instance_valid(player): return motion_heading
	var model: Node3D = player.get("player_model") as Node3D
	return roundi(-model.rotation.y * 4096.0 / TAU) & 4095 if is_instance_valid(model) else motion_heading
func _duck_tick() -> void:
	if cooldown > 0: cooldown -= 1
	if pending_hit:
		pending_hit = false; motion_heading = _player_heading(); duck_phase = 0
		if queued_flags & 0x80000: duck_mode = 5; forward_speed = 0x600; vertical_speed = 0x300; _sound(0x29B)
		else: duck_mode = 4; forward_speed = maxi(absi(forward_speed), 0x2A0); vertical_speed = 0x100; cooldown = 7
		pitch = 0; roll = 0; actor.rotation = Vector3.ZERO; _sync(); return
	if duck_mode in [4, 5]:
		var landed := _move_duck()
		if duck_phase == 0:
			vertical_speed -= 0x40
			if landed: vertical_speed = 0; duck_phase = 1
		else:
			forward_speed -= 0x40
			if forward_speed <= 0: forward_speed = 0; vertical_speed = 0; duck_mode = 1; duck_phase = 0
		actor.rotation = Vector3.ZERO
	if hit_queued: pending_hit = true; hit_queued = false
	_sync()
func _move_duck() -> bool:
	var yaw := float(motion_heading) * TAU / 4096.0; var previous := actor.global_position; var next := previous + Vector3(sin(yaw) * forward_speed, vertical_speed, -cos(yaw) * forward_speed) / 4096.0; var wall := _ray(previous + Vector3.UP * 0.125, next + Vector3.UP * 0.125)
	if not wall.is_empty() and absf((wall["normal"] as Vector3).y) < 0.5:
		var normal: Vector3 = wall["normal"]; var direction := Vector3(sin(yaw), 0.0, -cos(yaw)).bounce(normal); motion_heading = roundi(atan2(direction.x, -direction.z) * 4096.0 / TAU) & 4095; next.x = previous.x; next.z = previous.z
	var floor := _ray(Vector3(next.x, maxf(previous.y, next.y) + 0.25, next.z), next - Vector3.UP * 0.25); var landed := false
	if not floor.is_empty() and (floor["normal"] as Vector3).y > 0.0 and vertical_speed <= 0 and next.y <= float(floor["position"].y): next.y = float(floor["position"].y); landed = true
	actor.global_position = next; return landed
func _sound(id: int) -> void: sound_requested.emit(id, actor.global_position)
func _sync() -> void: global_transform = Transform3D(Basis.IDENTITY, actor.global_position)
func _ray(first: Vector3, second: Vector3) -> Dictionary:
	var excluded: Array[RID] = [get_rid()]
	if player is CollisionObject3D: excluded.append(player.get_rid())
	var query := PhysicsRayQueryParameters3D.create(first, second, 1, excluded); query.hit_back_faces = true
	return get_world_3d().direct_space_state.intersect_ray(query)
func _move_can() -> void:
	var yaw := float(motion_heading) * TAU / 4096.0; var movement := Vector3(sin(yaw) * forward_speed, vertical_speed, -cos(yaw) * forward_speed) / 4096.0; var previous := actor.global_position; var next := previous + movement; var extent := 16.0 / 256.0; var sweep := Vector3(movement.x, 0.0, movement.z); var wall := _ray(previous + Vector3.UP * (8.0 / 256.0), next + Vector3.UP * (8.0 / 256.0) + (sweep.normalized() * extent if sweep.length_squared() > 0.0 else Vector3.ZERO))
	if not wall.is_empty() and absf((wall["normal"] as Vector3).y) < 0.5:
		var normal: Vector3 = wall["normal"]; var contact: Vector3 = wall["position"]
		if absf(normal.x) >= absf(normal.z): next.x = contact.x + signf(normal.x) * extent; motion_heading = (0x1000 - motion_heading) & 4095
		else: next.z = contact.z + signf(normal.z) * extent; motion_heading = (0x800 - motion_heading) & 4095
		_sound(0x29A)
	elif not wall.is_empty() and (wall["normal"] as Vector3).y <= -0.5 and vertical_speed > 0: next.y = previous.y; vertical_speed = -vertical_speed; _sound(0x29A)
	var floor := _ray(Vector3(next.x, maxf(previous.y, next.y) + 0.25, next.z), next - Vector3.UP * 0.25)
	if not floor.is_empty() and (floor["normal"] as Vector3).y > 0.0:
		var resting_y := float(floor["position"].y) + 8.0 / 256.0
		if vertical_speed <= 0 and next.y <= resting_y:
			next.y = resting_y
			if spinning or vertical_speed != 0 or forward_speed != 0:
				vertical_speed = -((vertical_speed * (7 + (RandomSource.next_random(context) & 3))) >> 4); forward_speed = (forward_speed * (7 + (RandomSource.next_random(context) & 3))) >> 4
				if absi(vertical_speed) <= 32:
					vertical_speed = 0; forward_speed = 0
					if spinning: spinning = false; pitch = (pitch + 512) & 0xC00; roll = (roll + 512) & 0xC00; _sound(0x299)
				else: _sound(0x298)
	actor.global_position = next
func _can_goal() -> bool:
	var source := Vector3i(roundi(-actor.global_position.x * 256.0), roundi(-actor.global_position.y * 256.0), roundi(actor.global_position.z * 256.0))
	if source.y < -128 or source.y > -96: return false
	if source.x >= -2096 and source.x <= -2000 and source.z >= -4048 and source.z <= -4008: goal_second = false; return true
	if source.x >= 4144 and source.x <= 4184 and source.z >= 208 and source.z <= 304: goal_second = true; return true
	return false
