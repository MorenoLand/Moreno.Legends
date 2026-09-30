extends CharacterBody3D
signal collected(group: int, value: int, sound_id: int)
const TICK_RATE := 25.0
var target: CharacterBody3D
var source: Dictionary = {}
var data: Dictionary = {}
var visual: MeshInstance3D
var halo: MeshInstance3D
var mesh: ArrayMesh
var raw_vertices := PackedVector3Array()
var vertices := PackedVector3Array()
var faces: Array = []
var face_phases: Array = []
var age := 0.0
var accumulator := 0.0
var taken := false
var settled := false
var airborne := true
var bob_phase := 0
var spin := 0
var size := 0
var collect_stage := 0
var collect_timer := 0
func configure(entry: Dictionary, metadata: Dictionary, player: CharacterBody3D) -> void:
	source = entry; data = metadata; target = player; position = entry["position"]; velocity = entry["velocity"]; spin = int(entry.get("yaw_raw", 0))
	var group := int(entry["group"]); var type := int(entry["type"]); size = 6 + ((type * 5) >> 1)
	var points: Array = data["money_vertices_raw" if group == 0 else "energy_vertices_raw" if group == 1 else "health_vertices_raw"]
	for point: Array in points: raw_vertices.append(Vector3(-float(point[0]), -float(point[1]), float(point[2])) / (16.0 * 256.0))
	_scale_vertices()
	if group == 0: faces = data["money_triangles"]; face_phases = data["money_triangle_phases"]
	elif group == 1:
		for side in range(4):
			var base := 16 * ((side - 1) & 3); var ring := 1 + ((side + 1) & 3)
			faces.append([0, 1 + side, ring]); face_phases.append([(base + 8) & 31, (base + 16) & 31, (base + 24) & 31]); faces.append([1 + side, ring, 5]); face_phases.append([base & 31, (base + 8) & 31, (base + 16) & 31])
	else:
		for ring in range(2):
			for quad in [[0, 1, 2, 3, 0, 1, 2, 3], [2, 3, 4, 5, 3, 0, 1, 2], [4, 5, 6, 7, 2, 3, 0, 1]]:
				var v: Array = []; var p: Array = []
				for corner in range(4): v.append(int(quad[corner]) + 8 * ring); p.append((16 * ring + 8 * int(quad[4 + corner])) & 31)
				faces.append([v[0], v[1], v[2]]); face_phases.append([p[0], p[1], p[2]]); faces.append([v[1], v[2], v[3]]); face_phases.append([p[1], p[2], p[3]])
	visual = MeshInstance3D.new(); add_child(visual)
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.vertex_color_use_as_albedo = true; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; visual.material_override = material
	if group != 0:
		halo = MeshInstance3D.new(); halo.top_level = true; add_child(halo)
		var glow := StandardMaterial3D.new(); glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; glow.cull_mode = BaseMaterial3D.CULL_DISABLED; glow.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; glow.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; glow.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; glow.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; glow.albedo_texture = load(str(data["sprites"]["texture"])) as Texture2D; halo.material_override = glow
	var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); var hitbox: Array = data["hitbox_raw"]; box.size = Vector3(float(hitbox[1] - hitbox[0]), float(hitbox[3] - hitbox[2]), float(hitbox[5] - hitbox[4])) / 256.0; shape.shape = box; add_child(shape); collision_layer = 0; collision_mask = 1
	_rebuild_mesh()
func _scale_vertices() -> void:
	vertices = PackedVector3Array()
	for point in raw_vertices: vertices.append(point * float(size))
func _process(_delta: float) -> void:
	var camera := get_viewport().get_camera_3d()
	if halo != null and camera != null: halo.global_transform = Transform3D(camera.global_basis, visual.global_position)
func _physics_process(delta: float) -> void:
	if target == null: return
	age += delta; accumulator += delta
	if collect_stage == 0:
		if age >= float(data["lifetime_ticks"]) / TICK_RATE: queue_free(); return
		if age >= float(data["lifetime_ticks"] - 64) / TICK_RATE:
			visual.visible = (int(age * TICK_RATE) & 1) == 0
			if halo != null: halo.visible = visual.visible
	while accumulator >= 1.0 / TICK_RATE:
		accumulator -= 1.0 / TICK_RATE
		if collect_stage > 0:
			global_position = target.global_position + Vector3.UP * (176.0 / 256.0)
			if collect_stage == 1:
				collected.emit(int(source["group"]), int(source["value"]), int(data["sound_ids"][int(source["group"])])); size = (size * 3) >> 2; _scale_vertices(); collect_timer = 8; collect_stage = 2
			else:
				collect_timer -= 1
				if collect_timer == 0: queue_free(); return
				visual.position.y += 8.0 / 256.0; spin = (spin + 0x100) & 0xFFFF
		else:
			var distance := global_position.distance_to(target.global_position)
			if distance < float(data["pickup_radius_raw"]) / 256.0:
				collect_stage = 1; taken = true; visual.visible = true
				if halo != null: halo.visible = true
			else: _tick_motion(distance)
		visual.rotation.y = TAU * float(spin & 4095) / 4096.0
		_rebuild_mesh()
func _tick_motion(distance: float) -> void:
	if settled and distance < float(data["magnet_radius_raw"]) / 256.0:
		var direction := target.global_position - global_position; direction.y = 0.0; var heading := direction.normalized() * float(data["magnet_speed_raw"]) * TICK_RATE / 4096.0; velocity.x = heading.x; velocity.z = heading.z
	elif settled: velocity.x = 0.0; velocity.z = 0.0
	if airborne: velocity.y -= float(data["gravity_raw"]) * TICK_RATE * TICK_RATE / 4096.0 / TICK_RATE
	var hit := move_and_collide(velocity / TICK_RATE)
	if hit != null:
		if absf(velocity.y) <= 64.0 * TICK_RATE / 4096.0 and (settled or Vector2(velocity.x, velocity.z).length() <= 16.0 * TICK_RATE / 4096.0):
			velocity = Vector3(velocity.x, 0.0, velocity.z) if settled else Vector3.ZERO; settled = true; airborne = false
		else: velocity = Vector3(velocity.x * 0.5, -velocity.y * 0.5, velocity.z * 0.5); airborne = true
	if settled and not airborne:
		var hitbox: Array = data["hitbox_raw"]; var rest := -float(hitbox[2]) / 256.0; var floor_y := -INF; var space := get_world_3d().direct_space_state
		for offset in [Vector2.ZERO, Vector2(-1, -1), Vector2(1, -1), Vector2(-1, 1), Vector2(1, 1)]:
			var origin := global_position + Vector3(offset.x * float(hitbox[1]), 0.0, offset.y * float(hitbox[5])) / 256.0; var query := PhysicsRayQueryParameters3D.create(origin + Vector3.UP * (rest * 2.0), origin + Vector3.DOWN * (rest + 0.1875), 1, [get_rid()]); var floor_hit := space.intersect_ray(query)
			if not floor_hit.is_empty() and (floor_hit["normal"] as Vector3).y > 0.0: floor_y = maxf(floor_y, float((floor_hit["position"] as Vector3).y))
		if is_inf(floor_y): airborne = true
		else: global_position.y = floor_y + rest
	if settled: spin = (spin + 0x80 - (size << 4)) & 0xFFFF
	bob_phase = 0 if airborne else (bob_phase + 1) & 63
	visual.position.y = 0.0 if airborne else -float((int(data["bob_samples_raw"][bob_phase]) >> 8) - 8) / 256.0
func _rebuild_mesh() -> void:
	# SLES 0x8003A2DC: gouraud GP0 0x32/0x3A faces with DR_MODE 0xE1000200 (semi-transparency B/2+F/2), four per-vertex colours cycling between the 0x8006B060 pair (index = type for money, 7 energy, 8 health), depth ordered by AVSZ; energy/health first emit a 0x2E glow sprite (0x8003A82C / 0x8003ACD8).
	var group := int(source["group"]); var pair: Array = data["colors"][int(source["type"]) if group == 0 else 7 if group == 1 else 8]
	var colors := PackedColorArray(); var output := PackedVector3Array(); var order: Array = range(faces.size()); var camera := get_viewport().get_camera_3d(); var depths := {}
	for face in order:
		var center := Vector3.ZERO
		for index in faces[face]: center += vertices[int(index)]
		depths[face] = camera.global_position.distance_squared_to(visual.global_transform * (center / 3.0)) if camera != null else 0.0
	order.sort_custom(func(left: int, right: int) -> bool: return depths[left] > depths[right])
	for face in order:
		for corner in range(3):
			var phase: int = (int(age * TICK_RATE) + int(face_phases[face][corner])) & 31; var blend := float(phase) / 16.0 if phase < 16 else float(32 - phase) / 16.0
			colors.append(Color8(int(lerpf(float(pair[0]),float(pair[4]),blend)),int(lerpf(float(pair[1]),float(pair[5]),blend)),int(lerpf(float(pair[2]),float(pair[6]),blend)), 128)); output.append(vertices[int(faces[face][corner])])
	var arrays := []; arrays.resize(Mesh.ARRAY_MAX); arrays[Mesh.ARRAY_VERTEX] = output; arrays[Mesh.ARRAY_COLOR] = colors; mesh = ArrayMesh.new(); mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays); visual.mesh = mesh
	if halo == null: return
	var sprite: Dictionary = data["sprites"]["energy" if group == 1 else "health"]; var half := float(size >> int(sprite["size_shift"])) / 256.0; var step := ((((spin & 0xFFFF) >> 1) & 0xFFF) + int(data["sprites"]["angle_base_raw"])) & 0xFFF; var angle := TAU * float(step >> 6) / 64.0
	var offset := Vector2(cos(angle), sin(angle)) * half; var turned := Vector2(-offset.y, offset.x); var left := float(sprite["atlas_x"]) / 64.0
	var corners := PackedVector3Array([Vector3(-offset.x, offset.y, 0.0), Vector3(turned.x, -turned.y, 0.0), Vector3(-turned.x, turned.y, 0.0), Vector3(offset.x, -offset.y, 0.0)]); var uvs := PackedVector2Array([Vector2(left, 0.0), Vector2(left + 0.5, 0.0), Vector2(left, 1.0), Vector2(left + 0.5, 1.0)])
	var halo_arrays := []; halo_arrays.resize(Mesh.ARRAY_MAX); halo_arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([corners[0], corners[1], corners[2], corners[1], corners[2], corners[3]]); halo_arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([uvs[0], uvs[1], uvs[2], uvs[1], uvs[2], uvs[3]])
	var halo_mesh := ArrayMesh.new(); halo_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, halo_arrays); halo.mesh = halo_mesh
