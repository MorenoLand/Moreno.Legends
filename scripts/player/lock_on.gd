extends Node3D
# Native lock-on: search SLES 0x80043570, tracking GAME 0x800C853C, reticle SLES 0x8003BC6C.
const SCREEN_RANGE := 0x3400 / 256.0
const NEAR_RANGE := 0xC80 / 256.0
const PITCH_STEP := 0x40
const PITCH_LIMIT := 0x200
const YAW_STEP := 0x80
const RESELECT_TICKS := 12
const FLY_TICKS := 8
const LOCK_SOUND := 0x87
const TICK_RATE := 25.0
var player: CharacterBody3D
var target: Node3D
var last_target: Node3D
var pitch := 0
var tick := 0
var released_tick := -100
var acquired_tick := -1
var elapsed := 0.0
var mesh: MeshInstance3D
func configure(owner_player: CharacterBody3D) -> void:
	player = owner_player; top_level = true
	mesh = MeshInstance3D.new(); mesh.mesh = ImmediateMesh.new(); mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; mesh.top_level = true
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.no_depth_test = true; material.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh.material_override = material; add_child(mesh)
func locked() -> bool: return is_instance_valid(target)
func update(delta: float, held: bool) -> void:
	elapsed += delta * TICK_RATE
	while elapsed >= 1.0: elapsed -= 1.0; _tick(held)
	_draw_reticle()
func clear() -> void:
	if is_instance_valid(target): last_target = target; released_tick = tick
	target = null; acquired_tick = -1; player.locked_target = null
	if is_instance_valid(mesh): (mesh.mesh as ImmediateMesh).clear_surfaces()
func lock_point(node: Node3D) -> Vector3:
	# Native lock point = centre of the hit volume the actor registered (SLES 0x80042704); stage actors build their collision box from it.
	var center: Variant = node.get("hit_center")
	if center is Vector3: return center
	var box: Variant = node.get("collision")
	if box is CollisionShape3D and is_instance_valid(box) and box.is_inside_tree(): return (box as CollisionShape3D).global_position
	return node.global_position + Vector3.UP
func _tick(held: bool) -> void:
	tick += 1
	if not held: clear(); return
	if is_instance_valid(target) and not target.is_in_group("lock_targets"): target = null
	if not is_instance_valid(target):
		target = _search(); acquired_tick = tick if target != null else -1
	player.locked_target = target
	if target == null: pitch = clampi(0, pitch - PITCH_STEP, pitch + PITCH_STEP); return
	if tick - acquired_tick == FLY_TICKS + 1: player.special_sound_requested.emit(LOCK_SOUND)
	var offset := lock_point(target) - (player.global_position + Vector3.UP * 0x80 / 256.0)
	var goal := clampi(roundi(atan2(-offset.y, Vector2(offset.x, offset.z).length()) * 4096.0 / TAU), -PITCH_LIMIT, PITCH_LIMIT)
	pitch = clampi(goal, pitch - PITCH_STEP, pitch + PITCH_STEP)
	var model := player.player_model as Node3D; var step := float(YAW_STEP) * TAU / 4096.0
	model.rotation.y += clampf(wrapf(atan2(-offset.x, -offset.z) - model.rotation.y, -PI, PI), -step, step)
func _search() -> Node3D:
	var camera := player.camera as Camera3D; var size := get_viewport().get_visible_rect().size
	var skip: Node3D = last_target if tick - released_tick <= RESELECT_TICKS and is_instance_valid(last_target) else null
	var best_screen: Node3D = null; var screen_distance := SCREEN_RANGE; var best_near: Node3D = null; var near_distance := NEAR_RANGE
	for candidate in get_tree().get_nodes_in_group("lock_targets"):
		var node := candidate as Node3D
		if node == null or node == skip or not node.is_visible_in_tree(): continue
		var point := lock_point(node); var distance := Vector2(point.x - player.global_position.x, point.z - player.global_position.z).length()
		var on_screen := not camera.is_position_behind(point) and camera.unproject_position(point).x >= 0.0 and camera.unproject_position(point).x < size.x
		if on_screen and distance < screen_distance: screen_distance = distance; best_screen = node
		if distance < near_distance: near_distance = distance; best_near = node
	return best_screen if best_screen != null else best_near
func _draw_reticle() -> void:
	var immediate := mesh.mesh as ImmediateMesh; immediate.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if not is_instance_valid(target) or camera == null: return
	var special: bool = player.active_special() != 0
	var outer := float(0x90 if special else 0x80) / 256.0; var inner := float(0x70 if special else 0x60) / 256.0
	var color := Color8(0, 0xE0, 0xE0)
	if special: color = Color8(0xE0, 0xE0, 0) if _in_range() else Color8(0xE0, 0, 0)
	var age := float(tick - acquired_tick) + elapsed; var center := lock_point(target)
	if age < FLY_TICKS: center = camera.global_position.lerp(center, age / FLY_TICKS); color.a = 0.25
	var right := camera.global_basis.x; var up := camera.global_basis.y; var spread := (outer - inner) * 0.6
	immediate.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for quarter in 4:
		var angle := quarter * PI * 0.5; var radial := right * cos(angle) + up * sin(angle); var side := right * -sin(angle) + up * cos(angle)
		var tip := center + radial * inner; var left := center + radial * outer + side * spread; var right_corner := center + radial * outer - side * spread
		for point in [tip, left, right_corner]: immediate.surface_set_color(color); immediate.surface_add_vertex(point)
	if special: _draw_arcs(immediate, center, right, up, color.a)
	immediate.surface_end()
func _draw_arcs(immediate: ImmediateMesh, center: Vector3, right: Vector3, up: Vector3, fade: float) -> void:
	# Special-weapon ring, SLES 0x8003BC6C records 0x8006B330 drawn by 0x80039100 type 0xF0: 4 arcs x 8 steps of 1/64 turn, radius 0xA0..0xB0 (centre 0xA8 bright), spin 2/64 turn per tick, additive.
	var radii := PackedFloat32Array([0xA0, 0xA8, 0xB0]); var shades := PackedFloat32Array([0x20, 0x80, 0x20]); var spin := 2 * (tick & 0x1F)
	for arc in 4:
		for step in 8:
			var first := float(4 + arc * 16 + step + spin) * TAU / 64.0; var last := first + TAU / 64.0
			for band in 2:
				var inner_color := Color(shades[band] / 255.0 * fade, shades[band] / 255.0 * fade, shades[band] / 255.0 * fade); var outer_color := Color(shades[band + 1] / 255.0 * fade, shades[band + 1] / 255.0 * fade, shades[band + 1] / 255.0 * fade)
				var v0 := center + (right * cos(first) - up * sin(first)) * radii[band] / 256.0; var v1 := center + (right * cos(last) - up * sin(last)) * radii[band] / 256.0
				var v2 := center + (right * cos(first) - up * sin(first)) * radii[band + 1] / 256.0; var v3 := center + (right * cos(last) - up * sin(last)) * radii[band + 1] / 256.0
				for corner in [[v0, inner_color], [v1, inner_color], [v2, outer_color], [v1, inner_color], [v3, outer_color], [v2, outer_color]]: immediate.surface_set_color(corner[1]); immediate.surface_add_vertex(corner[0])
func _in_range() -> bool:
	var hose: Node = player.get("hose")
	var reach := 968.0 / 256.0 if player.active_special() == 15 and is_instance_valid(hose) else 0x80 * 2 / 256.0 + 0.25
	return player.global_position.distance_to(lock_point(target)) <= reach
