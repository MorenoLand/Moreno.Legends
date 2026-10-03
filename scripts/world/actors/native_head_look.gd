extends SkeletonModifier3D
var bone := 1
var pitch_units := 0
var yaw_units := 0
func _process_modification() -> void:
	var skeleton := get_skeleton()
	if skeleton == null or bone >= skeleton.get_bone_count() or (pitch_units == 0 and yaw_units == 0): return
	var angles := Basis(skeleton.get_bone_pose_rotation(bone)).get_euler(EULER_ORDER_XYZ)
	angles.x -= TAU * float(pitch_units) / 4096.0; angles.y -= TAU * float(yaw_units) / 4096.0
	skeleton.set_bone_pose_rotation(bone, Basis.from_euler(angles, EULER_ORDER_XYZ).get_rotation_quaternion())
