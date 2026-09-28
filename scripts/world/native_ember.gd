extends Node3D
signal contact_hit(ember: Node3D, damage: int)
var mission: Dictionary = {}
var trig: Array = []
var atlas: Texture2D
var player: Node3D
var data: Node3D
var pos := Vector3i.ZERO
var heading := 0
var vertical := 0
var landed := false
var size := 48
var life := 0
var frame_index := 0
var frame_ticks := 0
var hit_word := 0
var elapsed := 0.0
var sprite: MeshInstance3D
var hit_center := Vector3.ZERO
var spray_radius := 0.09375
func configure(source: Dictionary, start: Vector3i, yaw: int, speed: int, table: Array, texture: Texture2D, target_player: Node3D, target_data: Node3D) -> void:
	mission = source; pos = start; heading = yaw; vertical = speed; trig = table; atlas = texture; player = target_player; data = target_data
	var profile: Dictionary = mission["kitchen_data"]; size = int(profile["ember_size_raw"]); spray_radius = float(profile["ember_hitbox"]["radius_raw"]) / 256.0
	frame_ticks = int(_frames()[0]["ticks"]); add_to_group("hose_targets"); add_to_group("native_pool_actors")
	sprite = MeshInstance3D.new(); sprite.mesh = ImmediateMesh.new(); sprite.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; sprite.top_level = true
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.albedo_texture = atlas; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	sprite.material_override = material; add_child(sprite); _apply()
func receive_spray(word: int, _origin: Vector3) -> void: hit_word |= word
func _frames() -> Array: return mission["fire"]["effects"]["5"]["subtypes"][0]["frames"]
func _physics_process(delta: float) -> void:
	elapsed += delta * float(mission.get("native_tick_hz", 25))
	while elapsed >= 1.0 and is_inside_tree() and not is_queued_for_deletion(): elapsed -= 1.0; _tick()
	_draw()
func _tick() -> void:
	if not landed:
		vertical += int(mission["fire"]["embers"]["flight"]["gravity_per_tick"]); var index := (heading + 0x800) & 4095; var step := int(mission["fire"]["embers"]["flight"]["horizontal_speed_raw"])
		var from := _local(pos); pos += Vector3i(((int(trig[index][0]) * step) >> 12) >> 4, vertical >> 4, ((int(trig[index][1]) * step) >> 12) >> 4)
		var parent := get_parent() as Node3D; var query := PhysicsRayQueryParameters3D.create(parent.to_global(from), parent.to_global(_local(pos)), 1); var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty():
			var point: Vector3 = parent.to_local(hit["position"]); var floor_raw := roundi(-point.y * 256.0)
			if pos.y - floor_raw >= 0 and pos.y - floor_raw < 0x20: pos.y = floor_raw
			landed = true
	else:
		size -= 1
		if size < int(mission["kitchen_data"]["ember_land_shrink_until"]): queue_free(); return
	var frames := _frames(); var frame: Dictionary = frames[frame_index]; size += int(frame["size_delta_per_tick"]); frame_ticks -= 1
	if frame_ticks <= 0:
		if str(frame["next"]) == "die": queue_free(); return
		frame_index = 0 if str(frame["next"]) == "loop" else frame_index + 1; frame_ticks = int(frames[frame_index]["ticks"])
	if hit_word & int(mission["fire"]["embers"]["flight"]["water_mask"]): queue_free(); return
	life += 1
	if life >= int(mission["fire"]["embers"]["flight"]["lifetime_ticks"]): queue_free(); return
	_apply(); hit_word = 0
	var radius := spray_radius
	if is_instance_valid(data) and data.get("hit_center") is Vector3 and hit_center.distance_to(data.hit_center) < radius + float(data.spray_radius): data.receive_ember(int(mission["kitchen_data"]["ember_hitbox"]["word"]))
	if is_instance_valid(player) and player.global_position.distance_to(hit_center) < radius + 0.2: contact_hit.emit(self, int(mission["kitchen_data"]["ember_hitbox"]["word"]) & 0xFF)
func _local(raw: Vector3i) -> Vector3: return Vector3(-raw.x, -raw.y, raw.z) / 256.0
func _apply() -> void: position = _local(pos); hit_center = global_position
func _draw() -> void:
	var mesh := sprite.mesh as ImmediateMesh; mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d(); var frame: Dictionary = _frames()[frame_index]
	if camera == null or atlas == null or frame.get("atlas_id") == null: return
	var uv: Array = mission["fire"]["atlas_frames"][int(frame["atlas_id"])]["uv"]; var half := float(size) / 512.0; var right := camera.global_basis.x * half; var up := camera.global_basis.y * half; var texture_size := atlas.get_size(); var center := global_position
	var rect := Rect2(float(uv[0]) / texture_size.x, float(uv[1]) / texture_size.y, float(uv[2]) / texture_size.x, float(uv[3]) / texture_size.y)
	var corners := [center - right + up, center + right + up, center - right - up, center + right - up]; var uvs := [rect.position, Vector2(rect.end.x, rect.position.y), Vector2(rect.position.x, rect.end.y), rect.end]
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in [0, 1, 2, 2, 1, 3]: mesh.surface_set_uv(uvs[index]); mesh.surface_add_vertex(corners[index])
	mesh.surface_end()
