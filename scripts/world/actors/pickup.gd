extends CharacterBody3D
signal collected(group: int, value: int, sound_id: int)
const TICK_RATE := 25.0
var target: CharacterBody3D
var source: Dictionary = {}
var data: Dictionary = {}
var visual: MeshInstance3D
var mesh: ArrayMesh
var vertices := PackedVector3Array()
var faces: Array = []
var age := 0.0
var accumulator := 0.0
var taken := false
var settled := false
func configure(entry: Dictionary, metadata: Dictionary, player: CharacterBody3D) -> void:
	source = entry; data = metadata; target = player; position = entry["position"]; velocity = entry["velocity"]
	var group := int(entry["group"]); var type := int(entry["type"]); var size := 6 + ((type * 5) >> 1)
	var points: Array = data["money_vertices_raw" if group == 0 else "energy_vertices_raw" if group == 1 else "health_vertices_raw"]
	for point: Array in points: vertices.append(Vector3(-float(point[0]), -float(point[1]), float(point[2])) * float(size) / (16.0 * 256.0))
	if group == 0: faces = data["money_triangles"]
	elif group == 1:
		for side in range(4): faces.append([0, 1 + side, 1 + ((side + 1) & 3)]); faces.append([5, 1 + ((side + 1) & 3), 1 + side])
	else:
		for quad in [[0,1,2,3],[2,3,4,5],[4,5,6,7],[6,7,0,1],[0,2,6,4],[1,3,7,5]]: faces.append([quad[0],quad[2],quad[1]]); faces.append([quad[1],quad[2],quad[3]])
	visual = MeshInstance3D.new(); add_child(visual)
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.vertex_color_use_as_albedo = true; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA if group == 0 else BaseMaterial3D.TRANSPARENCY_DISABLED; visual.material_override = material
	var shape := CollisionShape3D.new(); var sphere := SphereShape3D.new(); sphere.radius = 0.025; shape.shape = sphere; add_child(shape); collision_layer = 0; collision_mask = 1
	_rebuild_mesh()
func _physics_process(delta: float) -> void:
	if taken or target == null: return
	age += delta; accumulator += delta
	if age >= float(data["lifetime_ticks"]) / TICK_RATE: queue_free(); return
	if age >= float(data["lifetime_ticks"] - 64) / TICK_RATE: visual.visible = (int(age * TICK_RATE) & 1) == 0
	while accumulator >= 1.0 / TICK_RATE:
		accumulator -= 1.0 / TICK_RATE
		var distance := global_position.distance_to(target.global_position)
		if distance < float(data["pickup_radius_raw"]) / 256.0:
			taken = true; set_physics_process(false); collected.emit(int(source["group"]), int(source["value"]), int(data["sound_ids"][int(source["group"])])); queue_free(); return
		if settled and distance < float(data["magnet_radius_raw"]) / 256.0:
			var direction := target.global_position - global_position; direction.y = 0.0; var heading := direction.normalized() * float(data["magnet_speed_raw"]) * TICK_RATE / 4096.0; velocity.x = heading.x; velocity.z = heading.z
		elif settled: velocity.x = 0.0; velocity.z = 0.0
		if not settled or not is_zero_approx(velocity.y): velocity.y -= float(data["gravity_raw"]) * TICK_RATE * TICK_RATE / 4096.0 / TICK_RATE
		var hit := move_and_collide(velocity / TICK_RATE)
		if hit != null:
			if absf(velocity.y) <= 64.0 * TICK_RATE / 4096.0 and Vector2(velocity.x, velocity.z).length() <= 16.0 * TICK_RATE / 4096.0:
				velocity = Vector3.ZERO; settled = true
			else: velocity = Vector3(velocity.x * 0.5, -velocity.y * 0.5, velocity.z * 0.5)
		visual.rotation.y += TAU * float(128 - ((6 + ((int(source["type"]) * 5) >> 1)) << 4)) / 4096.0
		_rebuild_mesh()
func _rebuild_mesh() -> void:
	# Money: SLES 0x8003A8EC-0x8003ACC8 draws gouraud GP0 0x32/0x3A faces with DR_MODE 0xE1000200 (semi-transparency B/2+F/2), four per-vertex colours cycling between the 0x8006B060 pair, depth ordered by AVSZ.
	var money := int(source["group"]) == 0; var pair: Array = data["colors"][int(source["type"]) if money else 7 if int(source["group"]) == 1 else 8]
	var colors := PackedColorArray(); var output := PackedVector3Array(); var order: Array = range(faces.size()); var phases: Array = data["money_triangle_phases"] if money else []
	if money:
		var camera := get_viewport().get_camera_3d(); var depths := {}
		for face in order:
			var center := Vector3.ZERO
			for index in faces[face]: center += vertices[int(index)]
			depths[face] = camera.global_position.distance_squared_to(visual.global_transform * (center / 3.0)) if camera != null else 0.0
		order.sort_custom(func(left: int, right: int) -> bool: return depths[left] > depths[right])
	for face in order:
		for corner in range(3):
			var phase: int = ((int(age * TICK_RATE) + int(phases[face][corner])) if money else (int(age * TICK_RATE) + (face / 4) * 16)) & 31; var blend := float(phase) / 16.0 if phase < 16 else float(32 - phase) / 16.0
			var color := Color8(int(lerpf(float(pair[0]),float(pair[4]),blend)),int(lerpf(float(pair[1]),float(pair[5]),blend)),int(lerpf(float(pair[2]),float(pair[6]),blend)), 128 if money else 255)
			output.append(vertices[int(faces[face][corner])]); colors.append(color)
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = output; arrays[Mesh.ARRAY_COLOR] = colors; mesh = ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); visual.mesh = mesh
