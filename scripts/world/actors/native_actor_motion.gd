extends RefCounted
static func settle_on_floor(actor: Node3D) -> void:
	if not is_instance_valid(actor) or not actor.is_inside_tree(): return
	await actor.get_tree().physics_frame
	if not is_instance_valid(actor) or not actor.is_inside_tree(): return
	var ground := ray(actor, actor.global_position + Vector3.UP * 1.125, actor.global_position - Vector3.UP * 2.0)
	if not ground.is_empty() and (ground["normal"] as Vector3).y >= 0.65: actor.global_position.y = (ground["position"] as Vector3).y
static func attach_collision(actor: Node3D, bounds: Array) -> void:
	if bounds.size() != 6: return
	var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
	if maximum.x <= minimum.x or maximum.y <= minimum.y or maximum.z <= minimum.z: return
	var body := AnimatableBody3D.new(); body.name = "NativeActorCollision"; body.collision_layer = 1; body.collision_mask = 0; body.sync_to_physics = false
	var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); box.size = maximum - minimum; shape.shape = box; shape.position = (minimum + maximum) * 0.5; body.add_child(shape); actor.add_child(body)
static func excluded(actor: Node3D) -> Array[RID]:
	var result: Array[RID] = []
	if actor is CollisionObject3D: result.append(actor.get_rid())
	for child: Node in actor.find_children("*", "CollisionObject3D", true, false): result.append((child as CollisionObject3D).get_rid())
	return result
static func ray(actor: Node3D, start: Vector3, finish: Vector3, others: Array[RID] = []) -> Dictionary:
	var omitted := excluded(actor); omitted.append_array(others); var query := PhysicsRayQueryParameters3D.create(start, finish, int(actor.get_meta("native_motion_collision_mask", 1)), omitted); query.collide_with_areas = false
	return actor.get_world_3d().direct_space_state.intersect_ray(query)
static func move_actor(actor: Node3D, motion: Vector3, bounds: Array) -> Dictionary:
	var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
	var sweep_minimum := minimum
	if is_zero_approx(motion.y): sweep_minimum.y += minf(1.0 / 256.0, (maximum.y - minimum.y) * 0.25)
	var box := BoxShape3D.new(); box.size = (maximum - sweep_minimum) * actor.global_basis.get_scale(); var query := PhysicsShapeQueryParameters3D.new(); query.shape = box; query.transform = Transform3D(actor.global_basis.orthonormalized(), actor.global_position + actor.global_basis * (sweep_minimum + maximum) * 0.5); query.motion = motion; query.margin = 0.0; query.collision_mask = int(actor.get_meta("native_motion_collision_mask", 1)); query.exclude = excluded(actor)
	var result: PackedFloat32Array = actor.get_world_3d().direct_space_state.cast_motion(query)
	if result.size() < 2: return {"blocked": true, "floor": false, "grounded": false}
	if result[0] < 1.0:
		if is_zero_approx(motion.y) and Vector2(motion.x, motion.z).length_squared() > 0.0:
			var raised := query.transform; query.motion = Vector3.UP * 0.125; var upward := actor.get_world_3d().direct_space_state.cast_motion(query)
			if upward.size() == 2 and upward[0] >= 1.0:
				query.transform.origin += Vector3.UP * 0.125; query.motion = motion; var forward := actor.get_world_3d().direct_space_state.cast_motion(query)
				if forward.size() == 2 and forward[0] >= 1.0:
					var ground := ray(actor, actor.global_position + motion + Vector3.UP * 0.125, actor.global_position + motion - Vector3.UP * 0.125)
					if not ground.is_empty() and (ground["normal"] as Vector3).y >= 0.65:
						actor.global_position += motion; actor.global_position.y = (ground["position"] as Vector3).y; return {"blocked": false, "floor": true, "grounded": true}
			query.transform = raised; query.motion = motion
		query.transform.origin += motion; var contact: Dictionary = actor.get_world_3d().direct_space_state.get_rest_info(query); var grounded: bool = motion.y < 0.0 and not contact.is_empty() and (contact["normal"] as Vector3).y > 0.0
		if grounded:
			var ground := ray(actor, actor.global_position + motion + Vector3.UP * (maximum.y + 0.125), actor.global_position + motion + Vector3.UP * (minimum.y - 0.125))
			if not ground.is_empty() and (ground["normal"] as Vector3).y > 0.0: var restored: Vector3 = actor.global_position; restored.y = (ground["position"] as Vector3).y; actor.global_position = restored
		return {"blocked": true, "floor": grounded, "grounded": grounded}
	var next_position: Vector3 = actor.global_position + motion; var floor_drop := minf(0.25, (maximum.y - minimum.y) * 0.5) if is_zero_approx(motion.y) else 0.125; var floor_hit := ray(actor, next_position + Vector3.UP * (maximum.y + 0.125), next_position + Vector3.UP * (minimum.y - floor_drop))
	var has_floor: bool = not floor_hit.is_empty() and (floor_hit["normal"] as Vector3).y > 0.0 and (floor_hit["position"] as Vector3).y <= actor.global_position.y + 0.125
	var grounded: bool = has_floor and motion.y < 0.0 and (floor_hit["position"] as Vector3).y >= next_position.y
	if has_floor and (motion.y == 0.0 or grounded): next_position.y = (floor_hit["position"] as Vector3).y
	actor.global_position = next_position
	return {"blocked": false, "floor": has_floor, "grounded": grounded}
