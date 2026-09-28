extends Node3D
signal gauge_changed(charge: int, capacity: int, segment: int, power: int, power_max: int)
const TICK := 1.0 / 30.0
var player: CharacterBody3D
var data: Dictionary = {}
var segments: Array = []
var capacity := 256
var refill := 4
var cost := 1
var tank := 256
var count := 0
var detach := 0
var released := true
var spraying := false
var frame := 0
var elapsed := 0.0
var sound_timer := 0
var aims: Array[Vector2] = []
var points: Array[Vector3] = []
var splashes: Array = []
var droplets: Array = []
var stream_mesh: MeshInstance3D
var splash_mesh: MeshInstance3D
var droplet_mesh: MeshInstance3D
var splash_frames: Array = []
var arm_mesh: MeshInstance3D
var arm_targets: Array = []
var arm_shown := false
var rng := RandomNumberGenerator.new()
func configure(owner: CharacterBody3D) -> bool:
	player = owner
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/weapons/weapon_0f.json")) if FileAccess.file_exists("res://assets/player/weapons/weapon_0f.json") else null
	if not parsed is Dictionary: return false
	data = parsed; segments = data["stream"]["segments"]; splash_frames = data["splash"]["frames"]
	capacity = int(data["tank"]["capacity"]["value"]); refill = int(data["tank"]["refillPerTick"]["value"]); cost = int(data["tank"]["costPerTick"]["value"]); tank = capacity
	var library_name := str(data["library"]); var packed := load("res://assets/player/weapons/" + str(data["model"])) as PackedScene
	if packed == null: return false
	var instance := packed.instantiate(); var players: Array[Node] = instance.find_children("*", "AnimationPlayer", true, false)
	if players.is_empty(): instance.free(); return false
	if not player.animation_player.has_animation_library(library_name): player.animation_player.add_animation_library(library_name, (players[0] as AnimationPlayer).get_animation_library("").duplicate(true))
	_configure_arm(instance); instance.free()
	player.animation_roles["hose"] = library_name + "/clip_096"
	top_level = true
	stream_mesh = _mesh_node(load("res://assets/player/weapons/hose_stream.png") as Texture2D, true)
	splash_mesh = _mesh_node(load("res://assets/player/weapons/hose_splash.png") as Texture2D, true)
	droplet_mesh = _mesh_node(null, true)
	_emit_gauge()
	return true
func _configure_arm(instance: Node) -> void:
	var arm: Dictionary = data["arm"]; var source := instance.find_child(str(arm["node"]), true, false) as MeshInstance3D; var skeletons: Array[Node] = (player.player_model as Node3D).find_children("*", "Skeleton3D", true, false)
	if source == null or skeletons.is_empty(): return
	var skeleton := skeletons[0] as Skeleton3D; var hidden: Array = arm["replaces"]["boneNames"]
	for node in (player.player_model as Node3D).find_children("*", "MeshInstance3D", true, false):
		var target := node as MeshInstance3D
		if target.mesh != null and target.skin != null: arm_targets.append([target, target.mesh, _without_bones(target.mesh, target.skin, skeleton, hidden)])
	arm_mesh = MeshInstance3D.new(); arm_mesh.name = str(arm["node"]); arm_mesh.mesh = source.mesh; arm_mesh.skin = source.skin; arm_mesh.transform = source.transform; arm_mesh.visible = false; skeleton.add_child(arm_mesh); arm_mesh.skeleton = arm_mesh.get_path_to(skeleton)
	for surface in range(arm_mesh.mesh.get_surface_count()):
		var material := ShaderMaterial.new(); material.shader = preload("res://shaders/native_model.gdshader"); material.set_shader_parameter("albedo_texture", (arm_mesh.mesh.surface_get_material(surface) as BaseMaterial3D).albedo_texture); arm_mesh.set_surface_override_material(surface, material)
func _without_bones(mesh: Mesh, skin: Skin, skeleton: Skeleton3D, names: Array) -> ArrayMesh:
	var binds := {}; var result := ArrayMesh.new()
	for bind in range(skin.get_bind_count()):
		var bone_name := str(skin.get_bind_name(bind)) if not str(skin.get_bind_name(bind)).is_empty() else skeleton.get_bone_name(skin.get_bind_bone(bind))
		if bone_name in names: binds[bind] = true
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]; var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array(range(vertices.size()))
		var width := bones.size() / maxi(vertices.size(), 1); var removed := PackedByteArray(); removed.resize(vertices.size())
		for vertex in range(vertices.size()):
			for slot in range(width): removed[vertex] = 1 if removed[vertex] == 1 or weights[vertex * width + slot] > 0.0 and binds.has(bones[vertex * width + slot]) else 0
		var kept := PackedInt32Array()
		for corner in range(0, indices.size(), 3):
			if removed[indices[corner]] == 0 and removed[indices[corner + 1]] == 0 and removed[indices[corner + 2]] == 0: kept.append_array([indices[corner], indices[corner + 1], indices[corner + 2]])
		arrays[Mesh.ARRAY_INDEX] = kept; result.add_surface_from_arrays(mesh.surface_get_primitive_type(surface), arrays, [], {}, mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS); result.surface_set_material(surface, mesh.surface_get_material(surface))
	return result
func _sync_arm() -> void:
	var shown: bool = player.active_special() == int(data["weapon"]) and player.combat_allowed
	if arm_mesh == null or shown == arm_shown: return
	arm_shown = shown; arm_mesh.visible = shown
	for target: Array in arm_targets: (target[0] as MeshInstance3D).mesh = target[2] if shown else target[1]
func _mesh_node(texture: Texture2D, additive: bool) -> MeshInstance3D:
	var node := MeshInstance3D.new(); node.mesh = ImmediateMesh.new(); node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	if additive: material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if texture != null: material.albedo_texture = texture
	node.material_override = material; add_child(node); return node
func begin() -> bool:
	if tank < cost or not player.is_on_floor(): return false
	if not player._start_special_action("hose"): return false
	released = false; spraying = false; detach = 0; return true
func action_tick(previous_time: float) -> bool:
	var pose := int(player.special_action_time * 30.0); var timeline: Dictionary = data["timeline"]
	var spawn := int(timeline["spawnPose"]["value"]); var loop_start := int(timeline["loopStartPose"]["value"]); var rewind := int(timeline["loopRewindAtPose"]); var release := int(timeline["releasePose"]["value"])
	if not released and pose >= spawn and not spraying: spraying = true; sound_timer = 0; player.special_sound_requested.emit(int(data["sounds"]["start"]["value"]))
	var holding := (Input.is_action_pressed("special") or Input.is_action_pressed("fire")) and tank >= cost
	if not released and not holding and pose >= spawn: _release(release); return true
	if not released and holding and pose >= rewind: _seek(float(loop_start) / 30.0 + (player.special_action_time - float(rewind) / 30.0)); return true
	return previous_time >= 0.0
func _release(release_pose: int) -> void:
	released = true
	if spraying: player.special_sound_requested.emit(int(data["sounds"]["stop"]["value"]))
	spraying = false
	if player.special_action_time < float(release_pose) / 30.0: _seek(float(release_pose) / 30.0)
func _seek(time: float) -> void:
	player.special_action_time = time; player.motion_tree.set("parameters/MotionSeek/seek_request", time); player.motion_tree.advance(0.0)
func _physics_process(delta: float) -> void:
	if player == null or stream_mesh == null: return
	_sync_arm()
	elapsed += delta
	while elapsed >= TICK: elapsed -= TICK; _tick()
	_draw()
func _tick() -> void:
	frame += 1
	if player.special_action != "hose" and not released: released = true; spraying = false
	var forward: Vector3 = -(player.player_model as Node3D).global_basis.z; var yaw := atan2(forward.x, -forward.z); var pitch := float(player._native_look_pitch()) * TAU / 4096.0 if player.has_method("_native_look_pitch") else 0.0
	aims.push_front(Vector2(yaw, pitch)); aims.resize(mini(aims.size(), segments.size() + 1))
	if spraying:
		tank -= cost; count = mini(count + 1, segments.size()); sound_timer += 1
		if sound_timer >= int(data["sounds"]["loopIntervalTicks"]["value"]): sound_timer = 0; player.special_sound_requested.emit(int(data["sounds"]["loopReplay"]["value"]))
		if tank < cost: _release(int(data["timeline"]["releasePose"]["value"]))
		_spawn_droplets(yaw)
	elif released and count > 0:
		detach += 1
		if detach >= count: count = 0; detach = 0
	if not spraying: tank = mini(capacity, tank + refill)
	_build_points()
	_collide()
	_tick_splashes(); _tick_droplets(); _emit_gauge()
func _build_points() -> void:
	points.clear()
	if count == 0: return
	var skeleton := player.upper_modifier.get_parent() as Skeleton3D if player.upper_modifier != null else null
	var origin: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Bone_%02d" % int(data["stream"]["emitBone"]))).origin if skeleton != null else player.global_position
	var point := origin
	for index in range(count):
		var segment: Dictionary = segments[index]; var aim: Vector2 = aims[mini(int(segment["aimLagTicks"]), aims.size() - 1)]
		var direction := Vector3(sin(aim.x) * cos(aim.y), -sin(aim.y), -cos(aim.x) * cos(aim.y))
		point += direction * float(segment["stepUnits"]) / 256.0; point.y -= float(segment["droopUnits"]) / 256.0; points.append(point)
	points.push_front(origin)
func _collide() -> void:
	if points.size() < 2: return
	var space := get_world_3d().direct_space_state; var origin: Vector3 = points[0]
	for index in range(1, count):
		var target: Vector3 = points[index + 1]; var radius := float(segments[index]["hitRadius"]) / 256.0
		for actor: Node in get_tree().get_nodes_in_group("hose_targets"):
			var node := actor as Node3D
			if node == null or not node.has_method("receive_spray") or (node.get("hit_center") if node.get("hit_center") != null else node.global_position).distance_to(target) > radius + float(node.get("spray_radius") if node.get("spray_radius") != null else 0.25): continue
			node.receive_spray(int(data["stream"]["hit"]["hitWord"]["value"]), player.global_position); _splash(target, index); count = index; points.resize(count + 1); return
		var query := PhysicsRayQueryParameters3D.create(origin, target, 1, [player.get_rid()]); var hit := space.intersect_ray(query)
		if not hit.is_empty(): _splash(hit["position"], index); count = maxi(index - 1, 0); points.resize(count + 1); return
func _splash(position: Vector3, index: int) -> void:
	splashes.append({"position": position, "frame": 0, "ticks": 0, "size": 12.0 + 6.0 * float(index)})
	player.special_sound_requested.emit(int(data["sounds"]["splash"]["value"]))
func _tick_splashes() -> void:
	for splash: Dictionary in splashes.duplicate():
		splash["ticks"] = int(splash["ticks"]) + 1
		if int(splash["ticks"]) < int(splash_frames[int(splash["frame"])]["durationTicks"]): continue
		splash["ticks"] = 0; splash["frame"] = int(splash["frame"]) + 1
		if int(splash["frame"]) >= splash_frames.size(): splashes.erase(splash)
		else: splash["size"] = float(splash["size"]) + float(splash_frames[int(splash["frame"])]["sizeAdd"])
func _spawn_droplets(yaw: float) -> void:
	if points.size() < 1: return
	var profile: Dictionary = data["droplets"]; var velocity: Array = profile["velocityRaw"]["value"]
	for index in int(profile["actors"]["value"]):
		var jitter := float(rng.randi_range(-256, 255)) * TAU / 4096.0; var heading := yaw + jitter
		var forward := -float(velocity[2]) / 16.0 / 256.0; var up := -float(velocity[1]) / 16.0 / 256.0
		droplets.append({"position": points[0], "previous": points[0], "velocity": Vector3(sin(heading) * forward, up, -cos(heading) * forward), "life": int(profile["lifetimeTicks"]["value"])})
func _tick_droplets() -> void:
	var gravity := float(data["droplets"]["gravityRaw"]["value"]) / 16.0 / 256.0
	for droplet: Dictionary in droplets.duplicate():
		droplet["previous"] = droplet["position"]; droplet["velocity"] = (droplet["velocity"] as Vector3) - Vector3(0.0, gravity, 0.0); droplet["position"] = (droplet["position"] as Vector3) + (droplet["velocity"] as Vector3); droplet["life"] = int(droplet["life"]) - 1
		if int(droplet["life"]) <= 0: droplets.erase(droplet)
func _emit_gauge() -> void:
	gauge_changed.emit(tank, capacity, 16, int(data["tank"]["reserve"]["value"]), int(data["tank"]["reserve"]["value"]))
func _draw() -> void:
	var camera := get_viewport().get_camera_3d()
	if camera == null: return
	global_transform = Transform3D.IDENTITY
	var right := camera.global_basis.x; var up := camera.global_basis.y
	var stream := stream_mesh.mesh as ImmediateMesh; stream.clear_surfaces()
	var render: Dictionary = data["stream"]["render"]; var base: Array = render["rgb"]["value"]; var step: Array = render["rgbStepPerSegment"]["value"]; var drawn := false
	for index in range(detach, count):
		if index + 1 >= points.size(): break
		var size := float(segments[index]["billboardSize"]) / 256.0
		if size <= 0.0: continue
		if not drawn: stream.surface_begin(Mesh.PRIMITIVE_TRIANGLES); drawn = true
		var color := Color(maxf(float(base[0]) - float(step[0]) * index, 0.0) / 128.0, maxf(float(base[1]) - float(step[1]) * index, 0.0) / 128.0, maxf(float(base[2]) - float(step[2]) * index, 0.0) / 128.0)
		var u := float((frame + index) & 3) * 0.25
		_quad(stream, points[index + 1], right * size * 0.5, up * size * 0.5, Rect2(u, 0.0, 0.25, 1.0), color)
	if drawn: stream.surface_end()
	var splash_draw := splash_mesh.mesh as ImmediateMesh; splash_draw.clear_surfaces()
	if not splashes.is_empty():
		splash_draw.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
		for splash: Dictionary in splashes:
			var definition: Dictionary = splash_frames[int(splash["frame"])]; var uv: Array = definition["uv"]; var rgb: Array = definition["rgb"]; var size := float(splash["size"]) / 256.0
			_quad(splash_draw, splash["position"], right * size * 0.5, up * size * 0.5, Rect2(float(uv[0]) / 192.0, 0.0, float(uv[2]) / 192.0, 1.0), Color(float(rgb[0]) / 128.0, float(rgb[1]) / 128.0, float(rgb[2]) / 128.0))
		splash_draw.surface_end()
	var lines := droplet_mesh.mesh as ImmediateMesh; lines.clear_surfaces()
	if not droplets.is_empty():
		lines.surface_begin(Mesh.PRIMITIVE_LINES)
		for droplet: Dictionary in droplets:
			lines.surface_set_color(Color(float(base[0]) * 2.0 / 128.0, float(base[1]) * 2.0 / 128.0, float(base[2]) * 2.0 / 128.0)); lines.surface_add_vertex(droplet["previous"]); lines.surface_add_vertex(droplet["position"])
		lines.surface_end()
func _quad(mesh: ImmediateMesh, center: Vector3, right: Vector3, up: Vector3, uv: Rect2, color: Color) -> void:
	var corners := [center - right + up, center + right + up, center - right - up, center + right - up]; var uvs := [uv.position, Vector2(uv.end.x, uv.position.y), Vector2(uv.position.x, uv.end.y), uv.end]
	for index in [0, 1, 2, 2, 1, 3]: mesh.surface_set_color(color); mesh.surface_set_uv(uvs[index]); mesh.surface_add_vertex(corners[index])
