extends Node3D
signal contact_hit(actor: CharacterBody3D, damage: int, flags: int)
const Motion := preload("res://scripts/world/actors/native_actor_motion.gd")
const Effect := preload("res://scripts/world/enemies/native_icefield_effect.gd")
var owner_enemy: CharacterBody3D
var target: CharacterBody3D
var charging := true
var charge := 0x14
var size := 0
var life := 0x3C
var direction := Vector3.ZERO
var elapsed := 0.0
var damage := 0
var passes: Array[MeshInstance3D] = []
var source: Dictionary = {}
func configure(enemy: CharacterBody3D, aim: Vector3) -> void:
	owner_enemy = enemy; target = enemy.target; damage = int(enemy.attributes[2]); top_level = true; global_position = _mouth(); direction = (aim - global_position).normalized()
	source = Effect.data(); charge = int(source.get("spit", {}).get("charge_ticks", charge)); life = int(source.get("spit", {}).get("life_ticks", life))
	for index in range(3):
		var visual := MeshInstance3D.new(); visual.mesh = ArrayMesh.new(); var material := ShaderMaterial.new(); material.shader = preload("res://shaders/native_impact.gdshader"); visual.material_override = material; visual.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; add_child(visual); passes.append(visual)
	_resize()
func _mouth() -> Vector3:
	var heading := float(owner_enemy.native_yaw) * TAU / 4096.0
	return owner_enemy.global_position + Vector3(sin(heading) * 96.0, 128.0, -cos(heading) * 96.0) / 256.0
func _resize() -> void:
	if source.is_empty(): return
	var inner := [0, size - (size >> 2), size]; var outer := [size - (size >> 1), size - (size >> 1), size - (size >> 2)]
	for pass_index in range(3):
		var vertices := PackedVector3Array(); var colors := PackedColorArray(); var indices := PackedInt32Array(); var rgb: Array = source["spit"]["colors_rgb"][pass_index]; var color := Color(float(rgb[0]) / 255.0, float(rgb[1]) / 255.0, float(rgb[2]) / 255.0)
		for segment in range(int(source["spit"]["segments"])):
			var first := vertices.size(); var angle := int(source["spit"]["start_index"]) + segment * int(source["spit"]["angle_step"])
			for point in [[angle, inner[pass_index]], [angle, outer[pass_index]], [angle + 2, inner[pass_index]], [angle + 2, outer[pass_index]]]:
				var trig: Array = source["trig64"][int(point[0]) & 63]; vertices.append(Vector3(float((int(trig[1]) * int(point[1])) >> 12), -float((int(trig[0]) * int(point[1])) >> 12), 0) / 256.0); colors.append(color)
			indices.append_array(PackedInt32Array([first, first + 1, first + 2, first + 1, first + 2, first + 3]))
		var arrays: Array = []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = vertices; arrays[Mesh.ARRAY_COLOR] = colors; arrays[Mesh.ARRAY_INDEX] = indices; var mesh := passes[pass_index].mesh as ArrayMesh; mesh.clear_surfaces(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); var radius := float(size) / 256.0; passes[pass_index].custom_aabb = AABB(Vector3.ONE * -radius, Vector3.ONE * radius * 2); (passes[pass_index].material_override as ShaderMaterial).set_shader_parameter("sorting_bias", float(maxi(int(inner[pass_index]), int(outer[pass_index]))) / 512.0)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(owner_enemy) or not is_instance_valid(target) or bool(owner_enemy.host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and is_inside_tree(): elapsed -= 1.0; _tick()
func _tick() -> void:
	if charging:
		global_position = _mouth(); _resize(); size += int(source["spit"]["charge_size_step_raw"])
		if owner_enemy.sub != 2: queue_free(); return
		charge -= 1
		if charge == 0: charging = false; size = int(source["spit"]["flight_size_raw"])
		return
	var next := global_position + direction * 0.5
	var wall := Motion.ray(owner_enemy, global_position, next)
	if not wall.is_empty(): queue_free(); return
	global_position = next; _resize(); life -= 1
	if life == 0: queue_free(); return
	var query := PhysicsShapeQueryParameters3D.new(); var sphere := SphereShape3D.new(); sphere.radius = 0x40 / 256.0; query.shape = sphere; query.transform = global_transform; query.collision_mask = target.collision_layer
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		if hit["collider"] == target: contact_hit.emit(owner_enemy, damage, 0x180000); queue_free(); return
