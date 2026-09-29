extends Node
signal restored
const ANGLES: Array = preload("res://scripts/world/actors/native_follower.gd").ANGLES
var actor: Node3D
var saved_heading := 0
var target_heading := 0
var returning := false
var elapsed := 0.0
func configure(target: Node3D, player: Node3D) -> void:
	actor = target; saved_heading = roundi(-actor.rotation.y * 4096.0 / TAU) & 4095; target_heading = _heading(actor.global_position, player.global_position)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(actor): restored.emit(); queue_free(); return
	elapsed += delta * 25.0
	while elapsed >= 1.0:
		elapsed -= 1.0
		if _turn(saved_heading if returning else target_heading) and returning: set_physics_process(false); restored.emit(); return
func return_to_saved_heading() -> void:
	returning = true
	if not is_instance_valid(actor) or (roundi(-actor.rotation.y * 4096.0 / TAU) & 4095) == saved_heading: queue_free(); return
	await restored
	queue_free()
func _turn(desired: int) -> bool:
	var current := roundi(-actor.rotation.y * 4096.0 / TAU) & 4095; var difference := (desired - current) & 4095
	if difference > 2048: difference -= 4096
	var heading := desired if absi(difference) <= 128 else (current + (128 if difference > 0 else -128)) & 4095
	actor.rotation.y = -float(heading) * TAU / 4096.0
	return heading == desired
static func _heading(first: Vector3, second: Vector3) -> int:
	var x := int((second.x - first.x) * 16777216.0); var z := int((first.z - second.z) * 16777216.0); var negative_x := x < 0; var negative_z := z < 0; x = absi(x); z = absi(z)
	if x == 0 and z == 0: return 0
	var angle: int
	if x < z:
		var ratio: int = int(float(x) / float(z >> 10)) if (x & 0x7FE00000) != 0 else int(float(x << 10) / float(z)); angle = int(ANGLES[ratio])
	else:
		var ratio: int = int(float(z) / float(x >> 10)) if (z & 0x7FE00000) != 0 else int(float(z << 10) / float(x)); angle = 1024 - int(ANGLES[ratio])
	if negative_z: angle = 2048 - angle
	if negative_x: angle = -angle
	return angle & 4095
