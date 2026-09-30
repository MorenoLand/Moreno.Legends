extends Node3D
signal extinguished(fire: Node3D, behaviour: int)
signal sound_requested(id: int, position: Vector3)
signal contact_hit(fire: Node3D, damage: int)
signal ember_requested(fire: Node3D)
signal exploded(fire: Node3D)
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
var explosion := false
var blast: Node3D
var flame_phase := 0
var flame_wave := 0
var debris_count := 0
func configure(source: Dictionary, entry: Dictionary, texture: Texture2D, target: Node3D) -> void:
	mission = source; record = entry; atlas = texture; player = target
	size = int(entry["size"]); strength_max = int(entry["strength_max"]); strength = strength_max; behaviour = int(entry.get("behaviour", 0)); contact_damage = int(entry.get("contact_damage", 8))
	explosion = int(entry.get("variant", 0)) == 1; loop_timer = 0 if explosion else (int(str(entry["bytes_hex"]).substr(4, 2).hex_to_int()) & 15) * 2
	position = Vector3(-float(entry["position_raw"][0]), -float(entry["position_raw"][1]), float(entry["position_raw"][2])) / 256.0
	add_to_group("hose_targets"); add_to_group("lock_targets"); add_to_group("native_pool_actors"); hit_center = position + Vector3.UP * spray_radius
	if explosion: spray_radius = float(source["fire"]["explosion"]["blast"]["burning"]["hitbox"]["radius_raw"]) / 256.0; return
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
	if explosion:
		if blast == null: _explode(); return
		hit_center = global_position + _forward(int(fire["explosion"]["blast"]["burning"]["hitbox"]["forward_raw"]))
	if hit_word & int(fire["hit_mask"]):
		var damage := (hit_word & 0xFFF) * int(fire["damage_scale"])
		if hit_word & 0x2000 and is_instance_valid(player):
			var distance := clampi(roundi(player.global_position.distance_to(global_position) * 256.0), 0x80, 0x100); damage += (((((0x100 - distance) * 13) << 6) >> 7) + 0x3C0) >> 3
		strength -= damage
		if strength <= int(fire["out_threshold"]): strength = 0; dying = 0; remove_from_group("hose_targets"); remove_from_group("lock_targets"); sound_requested.emit(int(fire["sounds"]["extinguished"]), global_position); extinguished.emit(self, behaviour); _hide(); return
	elif strength < strength_max: strength = mini(strength + int(fire["regrow_per_tick"]), strength_max)
	hit_word = 0
	if explosion: _burn(fire); return
	var radius := maxi(0x40, strength >> (5 if size == 0 else 6)); spray_radius = float(radius) / 256.0; hit_center = global_position + Vector3.UP * spray_radius
	if is_instance_valid(player) and player.global_position.distance_to(global_position + Vector3.UP * float(radius) / 256.0) < float(radius) / 256.0 + 0.2: contact_hit.emit(self, contact_damage)
	if behaviour & 4 and strength >= int(fire["embers"]["strength_gate"]) and is_instance_valid(controller) and (controller.ember_block & 1) == 0:
		ember_timer -= 1
		if ember_timer == 0: ember_requested.emit(self)
	loop_timer -= 1
	if loop_timer <= 0: loop_timer = int(fire["sounds"]["loop_period_ticks"]); sound_requested.emit(int(fire["sounds"]["loop"]), global_position)
	var frames: Array = fire["sprite"]["by_size"][size]["frames"]; frame_ticks += 1
	if frame_ticks >= int(frames[frame_index]["ticks"]): frame_ticks = 0; frame_index = (frame_index + 1) % frames.size()
func _hide() -> void:
	if sprite != null: sprite.visible = false
func _base() -> Vector3i: return Vector3i(int(record["position_raw"][0]), int(record["position_raw"][1]), int(record["position_raw"][2]))
func _forward(distance: int) -> Vector3:
	var table: Array = controller.trig[(int(record["yaw_raw"]) + 0x800) & 4095]
	return Vector3(-float((int(table[0]) * distance) >> 12), 0.0, float((int(table[1]) * distance) >> 12)) / 256.0
func _explode() -> void:
	var fire: Dictionary = mission["fire"]; var spec: Dictionary = fire["explosion"]["blast"]; var init: Dictionary = spec["init"]; var base := _base(); var yaw_byte := int(record["yaw_raw"]) >> int(init["yaw_byte_shift"])
	blast = preload("res://scripts/world/missions/fire/native_blast.gd").new(); blast.name = "Blast"; get_parent().add_child(blast); blast.configure(mission, controller.trig, atlas, player, controller._rand); blast.contact_hit.connect(func(damage: int) -> void: contact_hit.emit(self, damage)); blast.start_flash()
	for index in int(init["debris_count"]):
		var r: int = controller._rand(); var wobble: Array = init["debris_yaw_wobble"]; var speed: Array = init["debris_speed"]
		blast.spawn_debris(Vector3i(base.x, base.y + int(init["debris_y_raise"]) - (r & int(init["debris_y_mask"])), base.z), yaw_byte + int(wobble[0]) - ((r >> int(wobble[2])) & int(wobble[1])), int(speed[0]) + ((r >> int(speed[2])) & int(speed[1])), index % int(init["debris_subtypes"]))
	sound_requested.emit(int(init["sound"]), global_position); exploded.emit(self)
func _burn(fire: Dictionary) -> void:
	var spec: Dictionary = fire["explosion"]["blast"]["burning"]; var base := _base(); var yaw_byte := int(record["yaw_raw"]) >> int(fire["explosion"]["blast"]["init"]["yaw_byte_shift"]); flame_phase += 1; flame_wave += 1
	if flame_phase == int(spec["flame_period_ticks"]):
		flame_phase = 0; var jitter: Dictionary = spec["flame_jitter"]; var shifts: Array = jitter["shifts"]; var r: int = controller._rand(); var wave: Dictionary = spec["wobble"]; var phase := flame_wave & int(wave["mask"])
		var wobble := int(wave["center"]) - phase if flame_wave & int(wave["phase_bit"]) != 0 else phase - int(wave["center"])
		blast.spawn_flame(Vector3i(base.x + int(jitter["offset"]) - ((r >> int(shifts[0])) & int(jitter["mask"])), base.y + int(jitter["offset"]) - ((r >> int(shifts[1])) & int(jitter["mask"])), base.z + int(jitter["offset"]) - ((r >> int(shifts[2])) & int(jitter["mask"]))), yaw_byte + wobble, strength >> int(spec["flame_size_shift"]), contact_damage)
	if debris_count < int(spec["debris_ticks"]):
		debris_count += 1; var init: Dictionary = fire["explosion"]["blast"]["init"]; var subtype: int = controller._rand() % int(spec["debris_subtypes"]); var r: int = controller._rand(); var wobble: Array = init["debris_yaw_wobble"]; var speed: Array = init["debris_speed"]
		blast.spawn_debris(Vector3i(base.x, base.y + int(init["debris_y_raise"]) - (r & int(init["debris_y_mask"])), base.z), yaw_byte + int(wobble[0]) - ((r >> int(wobble[2])) & int(wobble[1])), int(speed[0]) + ((r >> int(speed[2])) & int(speed[1])), subtype)
	if loop_timer == 0: loop_timer = int(fire["sounds"]["explosion_fire_loop_period_ticks"]) - 1; sound_requested.emit(int(fire["sounds"]["explosion_fire_loop"]), global_position)
	else: loop_timer -= 1
	if is_instance_valid(player) and player.global_position.distance_to(hit_center) < spray_radius + 0.2: contact_hit.emit(self, contact_damage)
func _exit_tree() -> void:
	if is_instance_valid(blast): blast.finish()
func _draw() -> void:
	if sprite == null: return
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
