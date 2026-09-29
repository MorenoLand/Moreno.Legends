extends Node3D
signal transition_finished
const TICK_RATE := 25.0
var player: CharacterBody3D
var target: Node3D
var camera: Camera3D
var saved_camera: Camera3D
var saved_visible := true
var started := false
var transitioning := false
var returning := false
var elapsed := 0.0
var step := 0
var steps := 8
var focus := Vector3.ZERO
var orbit := Vector3.ZERO
var roll := 0.0
var saved_focus := Vector3.ZERO
var saved_orbit := Vector3.ZERO
var saved_roll := 0.0
var from_focus := Vector3.ZERO
var from_orbit := Vector3.ZERO
var from_roll := 0.0
var to_focus := Vector3.ZERO
var to_orbit := Vector3.ZERO
var to_roll := 0.0
func configure(owner_player: CharacterBody3D, actor: Node3D) -> void:
	player = owner_player; target = actor; saved_camera = get_viewport().get_camera_3d(); saved_visible = player.player_model.visible
	focus = player.camera_pivot.global_position; var offset := saved_camera.global_position - focus; var distance := maxf(offset.length(), 0.001)
	orbit = Vector3(atan2(offset.x, -offset.z) * 4096.0 / TAU, asin(clampf(offset.y / distance, -1.0, 1.0)) * 4096.0 / TAU, distance * 256.0)
	saved_focus = focus; saved_orbit = orbit; saved_roll = roll
	camera = Camera3D.new(); camera.name = "NativeTalkCamera"; camera.near = saved_camera.near; camera.far = saved_camera.far; camera.cull_mask = saved_camera.cull_mask; camera.fov = rad_to_deg(2.0 * atan(120.0 / 384.0)); camera.top_level = true; add_child(camera); camera.global_transform = saved_camera.global_transform
	if is_instance_valid(player.lock_on): player.lock_on.clear()
func setup(effect: Dictionary) -> void:
	if int(effect.get("mode", -1)) != 1 or not is_instance_valid(target): return
	var angles: Array = effect["signed12"]; var fields: Dictionary = effect["fields"]; var heading := preload("res://scripts/world/actors/native_talk_facing.gd")._heading(target.global_position, player.global_position)
	var position := target.global_position; position = Vector3(-floorf(-position.x * 256.0), -floorf(-position.y * 256.0), floorf(position.z * 256.0)) / 256.0
	started = true; camera.make_current(); _transition(position + Vector3.UP * float(fields["0xBC"]) / 256.0, Vector3((heading + int(angles[0])) & 4095, int(angles[1]), int(fields["0xBE"])), float(angles[2]), 8)
func _transition(destination_focus: Vector3, destination_orbit: Vector3, destination_roll: float, updates: int) -> void:
	from_focus = focus; from_orbit = orbit; from_roll = roll; to_focus = destination_focus; to_orbit = destination_orbit; to_roll = destination_roll; steps = updates; step = 0; elapsed = 0.0; transitioning = true
func _process(delta: float) -> void:
	if not transitioning: return
	elapsed += delta * TICK_RATE
	while elapsed >= 1.0 and transitioning:
		elapsed -= 1.0; step += 1; var progress := float(step) / float(steps); focus = from_focus.lerp(to_focus, progress)
		orbit = Vector3(from_orbit.x + wrapf(to_orbit.x - from_orbit.x, -2048.0, 2048.0) * progress, from_orbit.y + wrapf(to_orbit.y - from_orbit.y, -2048.0, 2048.0) * progress, lerpf(from_orbit.z, to_orbit.z, progress)); roll = from_roll + wrapf(to_roll - from_roll, -2048.0, 2048.0) * progress
		_place()
		if step >= steps:
			transitioning = false
			if returning and is_instance_valid(saved_camera): saved_camera.make_current()
			transition_finished.emit()
func _place() -> void:
	var yaw := float(roundi(orbit.x)) * TAU / 4096.0; var pitch := float(roundi(orbit.y)) * TAU / 4096.0; var radius := orbit.z / 256.0
	camera.global_position = focus + Vector3(sin(yaw) * cos(pitch), sin(pitch), -cos(yaw) * cos(pitch)) * radius
	if camera.global_position.distance_squared_to(focus) > 0.000001: camera.look_at(focus, Vector3.UP)
	if roll != 0.0: camera.rotate_object_local(Vector3.BACK, -roll * TAU / 4096.0)
func wait_until_ready() -> void:
	if transitioning: await transition_finished
func begin_return(cancelled: bool) -> void:
	returning = true
	player.player_model.visible = saved_visible
	if started: _transition(saved_focus, saved_orbit, saved_roll, 1 if cancelled else 8)
func finish() -> void:
	if is_instance_valid(saved_camera): saved_camera.make_current()
	if is_instance_valid(player): player.player_model.visible = saved_visible
	queue_free()
func _exit_tree() -> void:
	if is_instance_valid(camera) and camera.current and is_instance_valid(saved_camera) and saved_camera.is_inside_tree(): saved_camera.make_current()
	if is_instance_valid(player): player.player_model.visible = saved_visible
