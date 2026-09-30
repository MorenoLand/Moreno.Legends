extends Node3D
signal contact_hit(damage: int)
var mission: Dictionary = {}
var spec: Dictionary = {}
var trig: Array = []
var atlas: Texture2D
var player: Node3D
var rand: Callable
var flames: Array[Dictionary] = []
var debris: Array[Dictionary] = []
var flash := -1
var elapsed := 0.0
var closing := false
var flame_mesh: MeshInstance3D
var debris_mesh: MeshInstance3D
var flash_rect: ColorRect
func configure(source: Dictionary, table: Array, texture: Texture2D, target: Node3D, random: Callable) -> void:
	mission = source; spec = source["fire"]["explosion"]["blast"]; trig = table; atlas = texture; player = target; rand = random; add_to_group("native_pool_actors")
	flame_mesh = _sprites(BaseMaterial3D.BLEND_MODE_ADD, false); debris_mesh = _sprites(BaseMaterial3D.BLEND_MODE_MIX, true)
	var layer := CanvasLayer.new(); layer.layer = 0; add_child(layer); flash_rect = ColorRect.new(); flash_rect.set_anchors_preset(Control.PRESET_FULL_RECT); flash_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE; flash_rect.visible = false
	var blend := CanvasItemMaterial.new(); blend.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD; flash_rect.material = blend; layer.add_child(flash_rect)
func _sprites(blend_mode: int, cutout: bool) -> MeshInstance3D:
	var node := MeshInstance3D.new(); node.mesh = ImmediateMesh.new(); node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; node.top_level = true
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.blend_mode = blend_mode; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR if cutout else BaseMaterial3D.TRANSPARENCY_ALPHA; material.alpha_scissor_threshold = 0.5; material.vertex_color_use_as_albedo = true; material.albedo_texture = atlas; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.cull_mode = BaseMaterial3D.CULL_DISABLED
	if not cutout: material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	node.material_override = material; add_child(node)
	return node
func start_flash() -> void:
	flash = int(spec["flash"]["initial"]); _show_flash()
func spawn_flame(base: Vector3i, yaw_byte: int, speed: int, damage: int) -> void:
	var sub: Dictionary = mission["fire"]["effects"]["2"]["subtypes"][0]
	flames.append({"pos": base, "yaw": (yaw_byte << 4) & 4095, "speed": speed, "vel": int(spec["flame"]["init_velocity"]), "size": int(sub["initial_size_raw"]), "rot": 0, "frame": 0, "ticks": int(sub["frames"][0]["ticks"]), "damage": damage})
func spawn_debris(base: Vector3i, yaw_byte: int, speed: int, subtype: int) -> void:
	var sub: Dictionary = mission["fire"]["effects"]["4"]["subtypes"][subtype]; var launch: Array = spec["debris"]["init_velocity"]
	debris.append({"pos": base, "yaw": (yaw_byte << 4) & 4095, "speed": speed, "vel": -(int(launch[0]) + (int(rand.call()) & int(launch[1]))), "size": int(sub["initial_size_raw"]), "rot": 0, "frame": 0, "ticks": int(sub["frames"][0]["ticks"]), "age": 0, "sub": subtype})
func finish() -> void: closing = true
func _physics_process(delta: float) -> void:
	elapsed += delta * float(mission.get("native_tick_hz", 25))
	while elapsed >= 1.0 and is_inside_tree(): elapsed -= 1.0; _tick()
	_draw(flame_mesh, flames, "2", false); _draw(debris_mesh, debris, "4", true)
	if closing and flames.is_empty() and debris.is_empty() and flash < 0: queue_free()
func _tick() -> void:
	if flash >= 0:
		if flash < int(spec["flash"]["end_below"]): flash = -1; flash_rect.visible = false
		else: flash -= int(spec["flash"]["decay"]); _show_flash()
	var index := 0
	while index < flames.size():
		if _flame(flames[index]): index += 1
		else: flames.remove_at(index)
	index = 0
	while index < debris.size():
		if _debris(debris[index]): index += 1
		else: debris.remove_at(index)
func _show_flash() -> void:
	flash_rect.color = Color8(flash, flash, flash); flash_rect.visible = flash > 0
func _move(particle: Dictionary, gravity: int) -> void:
	var table: int = (int(particle["yaw"]) + 0x800) & 4095; var pos: Vector3i = particle["pos"]; var speed := int(particle["speed"]); particle["vel"] = int(particle["vel"]) + gravity
	particle["pos"] = pos + Vector3i((int(trig[table][0]) * speed) >> 12, int(particle["vel"]) >> 4, (int(trig[table][1]) * speed) >> 12)
func _animate(particle: Dictionary, frames: Array) -> bool:
	var frame: Dictionary = frames[int(particle["frame"])]; particle["size"] = int(particle["size"]) + int(frame["size_delta_per_tick"]); particle["rot"] = (int(particle["rot"]) + int(frame["rotation_delta_per_tick"])) & 255; particle["ticks"] = int(particle["ticks"]) - 1
	if int(particle["ticks"]) > 0: return true
	if str(frame["next"]) == "die": return false
	particle["frame"] = 0 if str(frame["next"]) == "loop" else int(particle["frame"]) + 1; particle["ticks"] = int(frames[int(particle["frame"])]["ticks"])
	return true
func _flame(particle: Dictionary) -> bool:
	_move(particle, int(spec["flame"]["gravity"]))
	var alive := _animate(particle, mission["fire"]["effects"]["2"]["subtypes"][0]["frames"])
	var radius := float((int(particle["size"]) >> int(spec["flame"]["hitbox"]["size_shift"])) * 4) / 256.0
	if is_instance_valid(player) and player.global_position.distance_to(_global(particle["pos"])) < radius + 0.2: contact_hit.emit(int(particle["damage"]))
	return alive
func _debris(particle: Dictionary) -> bool:
	var previous: Vector3i = particle["pos"]; _move(particle, int(spec["debris"]["gravity"]))
	var alive := _animate(particle, mission["fire"]["effects"]["4"]["subtypes"][int(particle["sub"])]["frames"]); particle["age"] = int(particle["age"]) + 1
	if int(particle["age"]) > int(spec["debris"]["floor_probe_after"]):
		var query := PhysicsRayQueryParameters3D.create(_global(previous), _global(particle["pos"]), 1)
		if not get_world_3d().direct_space_state.intersect_ray(query).is_empty(): return false
	return alive and int(particle["age"]) < int(spec["debris"]["max_age"])
func _global(raw: Vector3i) -> Vector3: return to_global(Vector3(-raw.x, -raw.y, raw.z) / 256.0)
func _draw(node: MeshInstance3D, list: Array[Dictionary], effect: String, by_subtype: bool) -> void:
	var mesh := node.mesh as ImmediateMesh; mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if list.is_empty() or camera == null or atlas == null: return
	var texture_size := atlas.get_size(); var subtypes: Array = mission["fire"]["effects"][effect]["subtypes"]
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for particle: Dictionary in list:
		var frame: Dictionary = subtypes[int(particle["sub"]) if by_subtype else 0]["frames"][int(particle["frame"])]
		if frame.get("atlas_id") == null: continue
		var uv: Array = mission["fire"]["atlas_frames"][int(frame["atlas_id"])]["uv"]; var rect := Rect2(float(uv[0]) / texture_size.x, float(uv[1]) / texture_size.y, float(uv[2]) / texture_size.x, float(uv[3]) / texture_size.y)
		var angle := float(int(particle["rot"]) * 16) * TAU / 4096.0; var half := float(particle["size"]) / 512.0; var right := (camera.global_basis.x * cos(angle) + camera.global_basis.y * sin(angle)) * half; var up := (camera.global_basis.y * cos(angle) - camera.global_basis.x * sin(angle)) * half
		var center := _global(particle["pos"]); var rgb: Array = frame["rgb"]; var tint := Color(float(rgb[0]) / 128.0, float(rgb[1]) / 128.0, float(rgb[2]) / 128.0)
		var corners := [center - right + up, center + right + up, center - right - up, center + right - up]; var uvs := [rect.position, Vector2(rect.end.x, rect.position.y), Vector2(rect.position.x, rect.end.y), rect.end]
		for corner in [0, 1, 2, 2, 1, 3]: mesh.surface_set_color(tint); mesh.surface_set_uv(uvs[corner]); mesh.surface_add_vertex(corners[corner])
	mesh.surface_end()
