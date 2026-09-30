extends Node3D
signal contact_hit(actor: CharacterBody3D, damage: int, flags: int)
const Motion := preload("res://scripts/world/actors/native_actor_motion.gd")
var owner_enemy: CharacterBody3D
var target: CharacterBody3D
var charging := true
var charge := 0x14
var size := 0
var life := 0x3C
var direction := Vector3.ZERO
var elapsed := 0.0
var damage := 0
var visual: MeshInstance3D
func configure(enemy: CharacterBody3D, aim: Vector3) -> void:
	owner_enemy = enemy; target = enemy.target; damage = int(enemy.attributes[2]); top_level = true; global_position = _mouth(); direction = (aim - global_position).normalized()
	visual = MeshInstance3D.new(); visual.mesh = SphereMesh.new(); var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.albedo_color = Color(0.55, 0.85, 1.0, 0.9); material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; visual.material_override = material; add_child(visual); _resize()
func _mouth() -> Vector3:
	var heading := float(owner_enemy.native_yaw) * TAU / 4096.0
	return owner_enemy.global_position + Vector3(sin(heading) * 96.0, 128.0, -cos(heading) * 96.0) / 256.0
func _resize() -> void: var radius := float(size) / 256.0; (visual.mesh as SphereMesh).radius = maxf(radius, 0.01); (visual.mesh as SphereMesh).height = maxf(radius * 2.0, 0.02)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(owner_enemy) or not is_instance_valid(target) or bool(owner_enemy.host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and is_inside_tree(): elapsed -= 1.0; _tick()
func _tick() -> void:
	if charging:
		global_position = _mouth(); size += 6; _resize()
		if owner_enemy.sub != 2: queue_free(); return
		charge -= 1
		if charge == 0: charging = false; size = 0x40; _resize()
		return
	var next := global_position + direction * 0.5
	var wall := Motion.ray(owner_enemy, global_position, next)
	if not wall.is_empty(): queue_free(); return
	global_position = next; life -= 1
	if life == 0: queue_free(); return
	var query := PhysicsShapeQueryParameters3D.new(); var sphere := SphereShape3D.new(); sphere.radius = 0x40 / 256.0; query.shape = sphere; query.transform = global_transform; query.collision_mask = target.collision_layer
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(owner_enemy, damage, 0x180000); queue_free(); return
