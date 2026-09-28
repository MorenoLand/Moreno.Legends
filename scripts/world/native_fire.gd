extends Node3D
signal extinguished(fire: Node3D, behaviour: int)
signal sound_requested(id: int, position: Vector3)
signal contact_hit(fire: Node3D, damage: int)
signal ember_requested(fire: Node3D)
var mission: Dictionary = {}
var record: Dictionary = {}
var size := 0
var strength := 0
var strength_max := 0
var behaviour := 0
var contact_damage := 8
var hit_word := 0
var hit_origin := Vector3.ZERO
var dying := -1
var frame_index := 0
var frame_ticks := 0
var loop_timer := 0
var elapsed := 0.0
var spray_radius := 0.25
var hit_center := Vector3.ZERO
var player: Node3D
var sprite: MeshInstance3D
var atlas: Texture2D
var controller: Node
var ember_timer := 0
func configure(source: Dictionary, entry: Dictionary, texture: Texture2D, target: Node3D) -> void:
	mission = source; record = entry; atlas = texture; player = target
	size = int(entry["size"]); strength_max = int(entry["strength_max"]); strength = strength_max; behaviour = int(entry.get("behaviour", 0)); contact_damage = int(entry.get("contact_damage", 8))
	loop_timer = (int(str(entry["bytes_hex"]).substr(4, 2).hex_to_int()) & 15) * 2
	position = Vector3(-float(entry["position_raw"][0]), -float(entry["position_raw"][1]), float(entry["position_raw"][2])) / 256.0
	add_to_group("hose_targets"); add_to_group("lock_targets"); add_to_group("native_pool_actors"); hit_center = position + Vector3.UP * spray_radius
	sprite = MeshInstance3D.new(); sprite.mesh = ImmediateMesh.new(); sprite.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.albedo_texture = atlas; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	sprite.material_override = material; sprite.top_level = true; add_child(sprite)
func receive_spray(word: int, origin: Vector3) -> void:
	hit_word |= word; hit_origin = origin
func _physics_process(delta: float) -> void:
	elapsed += delta * float(mission.get("native_tick_hz", 25))
	while elapsed >= 1.0: elapsed -= 1.0; _tick()
	_draw()
func _tick() -> void:
	if dying >= 0:
		dying += 1
		if dying >= 0x1D0: queue_free()
		return
	var fire: Dictionary = mission["fire"]
	if hit_word & int(fire["hit_mask"]):
		var damage := (hit_word & 0xFFF) * int(fire["damage_scale"])
		if hit_word & 0x2000 and is_instance_valid(player):
			var distance := clampi(roundi(player.global_position.distance_to(global_position) * 256.0), 0x80, 0x100); damage += (((((0x100 - distance) * 13) << 6) >> 7) + 0x3C0) >> 3
		strength -= damage
		if strength <= int(fire["out_threshold"]): strength = 0; dying = 0; remove_from_group("hose_targets"); remove_from_group("lock_targets"); sound_requested.emit(int(fire["sounds"]["extinguished"]), global_position); extinguished.emit(self, behaviour); sprite.visible = false; return
	elif strength < strength_max: strength = mini(strength + int(fire["regrow_per_tick"]), strength_max)
	hit_word = 0
	var radius := maxi(0x40, strength >> (5 if size == 0 else 6)); spray_radius = float(radius) / 256.0; hit_center = global_position + Vector3.UP * spray_radius
	if is_instance_valid(player) and player.global_position.distance_to(global_position + Vector3.UP * float(radius) / 256.0) < float(radius) / 256.0 + 0.2: contact_hit.emit(self, contact_damage)
	if behaviour & 4 and strength >= int(fire["embers"]["strength_gate"]) and is_instance_valid(controller) and (controller.ember_block & 1) == 0:
		ember_timer -= 1
		if ember_timer == 0: ember_requested.emit(self)
	loop_timer -= 1
	if loop_timer <= 0: loop_timer = int(fire["sounds"]["loop_period_ticks"]); sound_requested.emit(int(fire["sounds"]["loop"]), global_position)
	var frames: Array = fire["sprite"]["by_size"][size]["frames"]; frame_ticks += 1
	if frame_ticks >= int(frames[frame_index]["ticks"]): frame_ticks = 0; frame_index = (frame_index + 1) % frames.size()
func _draw() -> void:
	var mesh := sprite.mesh as ImmediateMesh; mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if dying >= 0 or camera == null or atlas == null: return
	var fire: Dictionary = mission["fire"]; var frame: Dictionary = fire["sprite"]["by_size"][size]["frames"][frame_index]; var source: Dictionary = fire["atlas_frames"][int(frame["atlas_id"])]; var uv: Array = source["uv"]
	var half := float((strength >> 4) - (strength >> 6)) / 512.0; var center := global_position + Vector3.UP * float(strength >> 5) / 256.0
	var right := camera.global_basis.x * half; var up := camera.global_basis.y * half; var atlas_size := atlas.get_size()
	var rect := Rect2(float(uv[0]) / atlas_size.x, float(uv[1]) / atlas_size.y, float(uv[2]) / atlas_size.x, float(uv[3]) / atlas_size.y)
	var corners := [center - right + up, center + right + up, center - right - up, center + right - up]; var uvs := [rect.position, Vector2(rect.end.x, rect.position.y), Vector2(rect.position.x, rect.end.y), rect.end]
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in [0, 1, 2, 2, 1, 3]: mesh.surface_set_uv(uvs[index]); mesh.surface_add_vertex(corners[index])
	mesh.surface_end()
