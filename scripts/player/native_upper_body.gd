extends SkeletonModifier3D
var tree: AnimationTree
var animations: AnimationPlayer
var motion: AnimationNodeAnimation
var root_track := -1
var hip_track := -1
var clip_name := ""
var source_root_yaw := 0.0
var source_head_yaw := 0.0
var clip_contexts: Dictionary = {}
var aim_target := Vector3.ZERO
var track_target := false
var muzzle_offset := Vector3.ZERO
func _active_arm_mode() -> int:
	var blend_tree := tree.tree_root as AnimationNodeBlendTree
	if blend_tree == null or not blend_tree.has_node("Arm"): return 0
	var arm := blend_tree.get_node("Arm") as AnimationNodeAnimation
	if arm == null: return 0
	if float(tree.get("parameters/UpperBody/blend_amount")) <= 0.0: return 0
	var context := str(clip_contexts.get(arm.animation, ""))
	if context == "upperBodyMode1" or context.ends_with("mode1 bones2..4"): return 1
	if context == "upperBodyMode2": return 2
	return 0
func set_source_aim_angles(root_yaw_units: int, head_yaw_units: int) -> void:
	source_root_yaw = -TAU * float(root_yaw_units & 0xfff) / 4096.0
	source_head_yaw = -TAU * float(head_yaw_units & 0xfff) / 4096.0
func _process_modification() -> void:
	if tree == null or animations == null or motion == null: return
	var skeleton := get_skeleton()
	var clip := animations.get_animation(motion.animation)
	if clip == null: return
	if clip_name != motion.animation:
		clip_name = motion.animation
		root_track = -1
		hip_track = -1
		for track in range(clip.get_track_count()):
			var path := clip.track_get_path(track)
			if path.get_subname_count() == 0 or clip.track_get_type(track) != Animation.TYPE_ROTATION_3D: continue
			if str(path.get_subname(0)) == "Bone_00": root_track = track
			elif str(path.get_subname(0)) == "Bone_08": hip_track = track
	if root_track < 0 or hip_track < 0: return
	var time := float(tree.get("parameters/Motion/current_position"))
	var base_root := clip.rotation_track_interpolate(root_track, time)
	var hip := clip.rotation_track_interpolate(hip_track, time)
	var root_index := skeleton.find_bone("Bone_00")
	var hip_index := skeleton.find_bone("Bone_08")
	if not is_zero_approx(source_root_yaw): skeleton.set_bone_pose_rotation(root_index, Quaternion(Vector3.UP, source_root_yaw) * skeleton.get_bone_pose_rotation(root_index))
	var correction := skeleton.get_bone_pose_rotation(root_index).inverse() * base_root
	skeleton.set_bone_pose_rotation(hip_index, correction * hip)
	skeleton.set_bone_pose_position(hip_index, correction * skeleton.get_bone_rest(hip_index).origin)
	var arm_mode := _active_arm_mode()
	if not is_zero_approx(source_head_yaw):
		var head_index := skeleton.find_bone("Bone_01")
		if head_index >= 0:
			var head_angles := Basis(skeleton.get_bone_pose_rotation(head_index)).get_euler(EULER_ORDER_XYZ)
			head_angles.y += source_head_yaw
			skeleton.set_bone_pose_rotation(head_index, Basis.from_euler(head_angles, EULER_ORDER_XYZ).get_rotation_quaternion())
	if arm_mode != 0:
		var active_arm := skeleton.find_bone("Bone_02" if arm_mode == 1 else "Bone_05")
		var arm_angles := Basis(skeleton.get_bone_pose_rotation(active_arm)).get_euler(EULER_ORDER_XYZ)
		arm_angles.z -= source_head_yaw
		skeleton.set_bone_pose_rotation(active_arm, Basis.from_euler(arm_angles, EULER_ORDER_XYZ).get_rotation_quaternion())
		if track_target:
			var barrel := skeleton.find_bone("Bone_03" if arm_mode == 1 else "Bone_06")
			var outlet := skeleton.find_bone("Bone_04" if arm_mode == 1 else "Bone_07")
			var target := skeleton.global_transform.affine_inverse() * aim_target
			var shoulder := skeleton.get_bone_global_pose(active_arm).origin
			var shoulder_heading := target - shoulder
			var shoulder_flat := Vector3(shoulder_heading.x, 0.0, shoulder_heading.z)
			if shoulder_heading.y < -shoulder_flat.length() * 0.5 and shoulder_flat.length_squared() > 0.000001:
				var shoulder_parent := skeleton.get_bone_global_pose(skeleton.get_bone_parent(active_arm)).basis
				var outward := Vector3.UP.cross(shoulder_flat.normalized()) * (-1.0 if arm_mode == 1 else 1.0)
				var elbow := (skeleton.get_bone_global_pose(barrel).origin - shoulder).normalized()
				var spread := elbow.dot(outward)
				if spread < 0.85:
					var bend := (elbow - outward * spread).normalized()
					var goal := (outward * 0.85 + bend * sqrt(1.0 - 0.85 * 0.85)).normalized()
					var shoulder_basis := shoulder_parent.inverse() * Basis(Quaternion(elbow, goal)) * shoulder_parent
					skeleton.set_bone_pose_rotation(active_arm, (shoulder_basis * Basis(skeleton.get_bone_pose_rotation(active_arm))).get_rotation_quaternion())
			var parent_basis := skeleton.get_bone_global_pose(skeleton.get_bone_parent(barrel)).basis
			var joint := skeleton.get_bone_global_pose(barrel).origin
			var origin := skeleton.get_bone_global_pose(outlet) * muzzle_offset - joint
			var heading := target - joint
			var direction := -skeleton.get_bone_global_pose(barrel).basis.y.normalized()
			var flat := Vector3(heading.x, 0.0, heading.z)
			if flat.length_squared() > 0.000001:
				var source_pitch := atan2(direction.y, Vector2(direction.x, direction.z).length())
				var pitch := clampf(atan2(heading.y, flat.length()), source_pitch - PI / 4.0, source_pitch + PI / 4.0)
				heading = (flat.normalized() * cos(pitch) + Vector3.UP * sin(pitch)) * heading.length()
			var projection := origin.dot(direction)
			var distance := maxf(sqrt(maxf(projection * projection + heading.length_squared() - origin.length_squared(), 0.0)) - projection, 0.0)
			var correction_basis := parent_basis.inverse() * Basis(Quaternion((origin + direction * distance).normalized(), heading.normalized())) * parent_basis
			skeleton.set_bone_pose_rotation(barrel, (correction_basis * Basis(skeleton.get_bone_pose_rotation(barrel))).get_rotation_quaternion())
