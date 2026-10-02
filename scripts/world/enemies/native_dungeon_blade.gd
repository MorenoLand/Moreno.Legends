extends "res://scripts/world/enemies/native_icefield_enemy.gd"
var skeleton: Skeleton3D
var velocity_limit := 0x40
var acceleration := 2
var spin := 0
var pause := 0
var rearm := 0
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry, metadata, path): return false
	skeleton = model.find_child("Skeleton3D", true, false) as Skeleton3D
	velocity_limit = 0x40 if int(entry.get("variant", 0)) == 0 else -0x40; acceleration = 2 if velocity_limit > 0 else -2; top = 1; sub = 0
	control = 0; control_at_start = 0; clock.play_control(0, 0, true)
	return true
func _joint(index: int, offset_raw := Vector3.ZERO) -> Vector3:
	if skeleton == null or index >= skeleton.get_bone_count(): return global_position
	return skeleton.global_transform * (skeleton.get_bone_global_pose(index) * (Vector3(-offset_raw.x, -offset_raw.y, offset_raw.z) / 256.0))
func _run() -> void:
	var touched := _contact()
	match sub:
		0:
			spin = velocity_limit if absi(velocity_limit) < absi(spin) else spin + acceleration
			if touched: sub = 1
			var bearing: int = preload("res://scripts/world/actors/native_talk_facing.gd")._heading(target.global_position, global_position)
			var difference := posmod(bearing - (native_yaw + 0x400) + 2048, 4096) - 2048
			if rearm == 0 and absi(difference) < 0x100: _sound(0x145); rearm = 0xF
			if rearm != 0: rearm -= 1
		1:
			if absi(spin) < absi(acceleration): spin = 0; pause = 0x5A; sub = 2
			else: spin -= acceleration
		2:
			pause -= 1
			if pause == 0: sub = 0
	_face(native_yaw + spin)
func _contact() -> bool:
	var touched := false
	var base := _joint(1)
	var segments: Array = [[_joint(0, Vector3(0, 0x40, 0)), _joint(1, Vector3(0, 0x40, 0)), 48.0, 1, 0xA00000], [_joint(1, Vector3(0, 0x100, 0)), _joint(1, Vector3(0, 0x2BC, 0)), 128.0, int(attributes[1]), 0xA80000]]
	for segment: Array in segments:
		var sphere := SphereShape3D.new(); sphere.radius = float(segment[2]) / 256.0
		for step_index in 5:
			var query := PhysicsShapeQueryParameters3D.new(); query.shape = sphere; query.transform = Transform3D(Basis.IDENTITY, (segment[0] as Vector3).lerp(segment[1] as Vector3, float(step_index) / 4.0)); query.collision_mask = target.collision_layer
			for hit in get_world_3d().direct_space_state.intersect_shape(query):
				if hit["collider"] == target:
					touched = true
					if not bool(target.no_clip): contact_hit.emit(self, int(segment[3]), int(segment[4]))
					break
			if touched: break
		if touched: break
	return touched and base != Vector3.INF
