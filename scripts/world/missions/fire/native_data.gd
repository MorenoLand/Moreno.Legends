extends Node3D
signal ignited(actor: Node3D)
signal extinguished(actor: Node3D)
signal sound_requested(id: int, position: Vector3)
signal contact_hit(actor: Node3D, damage: int)
const Npc := preload("res://scripts/world/actors/native_npc_behavior.gd")
const Motion := preload("res://scripts/world/actors/native_actor_motion.gd")
var mission: Dictionary = {}
var profile: Dictionary = {}
var controller: Node
var player: Node3D
var model: Node3D
var clock: NativeAnimation
var skeleton: Skeleton3D
var trig: Array = []
var atlas: Texture2D
var flame: MeshInstance3D
var pos := Vector3i.ZERO
var previous := Vector3i.ZERO
var yaw := 0
var pitch := 0
var speed := 0
var vertical := 0
var airborne := false
var state := 0
var sub := 0
var route_sub := 0
var control := -1
var desired := 1
var strength := 0
var hit_word := 0
var flags := 0
var counter := 0
var route := 0
var point := 0
var sound_timer := 0
var flame_frame := 0
var flame_ticks := 0
var elapsed := 0.0
var hit_center := Vector3.ZERO
var spray_radius := 0.125
var talk_registered := false
func configure(source: Dictionary, node: Node3D, owner_node: Node, target: Node3D, table: Array, texture: Texture2D) -> void:
	mission = source; profile = source["kitchen_data"]; model = node; controller = owner_node; player = target; trig = table; atlas = texture
	var raw: Array = profile["actor"]["entry"]["position_raw"]; pos = Vector3i(int(raw[0]), int(raw[1]), int(raw[2])); previous = pos; yaw = int(profile["actor"]["entry"]["yaw_raw"])
	clock = model.get_node_or_null("NativeAnimationClock") as NativeAnimation
	if clock != null: clock.automatic = false
	var skeletons := model.find_children("*", "Skeleton3D", true, false); skeleton = skeletons[0] as Skeleton3D if not skeletons.is_empty() else null
	strength = 0; desired = int(profile["controls"]["panic"]); _play(desired); add_to_group("hose_targets"); add_to_group("native_pool_actors"); model.add_to_group("native_pool_actors")
	flame = MeshInstance3D.new(); flame.mesh = ImmediateMesh.new(); flame.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; flame.top_level = true
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.albedo_texture = atlas; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	flame.material_override = material; add_child(flame); _apply()
func receive_spray(word: int, _origin: Vector3) -> void: hit_word |= word
func receive_ember(word: int) -> void: hit_word |= word
func burning() -> bool: return (flags & 2) != 0
func _physics_process(delta: float) -> void:
	if not is_instance_valid(model): queue_free(); return
	if is_instance_valid(controller) and bool(controller.get("data_rescued")):
		_register_talk_target(); _draw_flame(); return
	elapsed += delta * float(mission.get("native_tick_hz", 25))
	while elapsed >= 1.0: elapsed -= 1.0; _tick()
	_draw_flame()
func _register_talk_target() -> void:
	if talk_registered: return
	var entry: Dictionary = profile["actor"]["entry"]
	model.set_meta("native_stage", str(entry.get("stage", "ST1E"))); model.set_meta("native_area", int(entry.get("area", 2))); model.set_meta("native_actor_source", entry.duplicate(true)); model.set_meta("native_interaction", {"stage": "ST1E", "actor_class": 99, "request_kind": 0, "message_call": "0x80048474", "message_index": int(mission["messages"]["success"][0]), "bank_id": "0x8010C000", "data_menu": true, "service_stage": "ST04", "service_bank_id": "0x8010C000", "service_message_call": "0x800BDCF8", "service_message_index": 180}); model.add_to_group("native_interaction_targets"); talk_registered = true
func _rand() -> int: return Npc.next_random(controller.host.native_context)
func _tick() -> void:
	previous = pos
	if (flags & 1) == 0:
		if flags & 2:
			var result := _extinguish()
			if result == -1: flags &= ~2; flame_frame = 0; remove_from_group("lock_targets"); extinguished.emit(self)
			elif strength < int(profile["strength_max"]): strength = mini(strength + int(profile["regrow"]), int(profile["strength_max"]))
		elif hit_word & int(profile["hitbox"]["ignite_bit"]): flags |= 2; state = 1; sub = 0
	if controller.remaining == 0 and state == 8: flags |= 1; sub = 0
	match state:
		0: _panic()
		1: _ignite()
		2: _run_out()
		3: _circle()
		4: _return()
		5: _route()
		6: _spin()
		7: _avoid()
		8: _settle()
	hit_word = 0
	if desired != control: _play(desired)
	elif clock != null: clock.native_tick()
	if (flags & 1) == 0 and flags & 2 and is_instance_valid(player) and player.global_position.distance_to(hit_center) < float(profile["hitbox"]["radius_raw"]) / 256.0 + 0.2: contact_hit.emit(self, int(profile["hitbox"]["burning_contact_damage"]))
	_apply()
	if burning():
		var frames: Array = mission["fire"]["effects"]["6"]["subtypes"][0]["frames"]; flame_ticks += 1
		if flame_ticks >= int(frames[flame_frame]["ticks"]): flame_ticks = 0; flame_frame = 0 if str(frames[flame_frame]["next"]) == "loop" or flame_frame + 1 >= frames.size() else flame_frame + 1
func _play(code: int) -> void:
	control = code
	if clock != null: clock.play_control(code, 0, true)
func _apply() -> void:
	model.position = Vector3(-pos.x, -pos.y, pos.z) / 256.0; model.rotation = Vector3(-float(pitch) * TAU / 4096.0, -float(yaw) * TAU / 4096.0, 0.0)
	hit_center = model.global_transform.origin + Vector3.UP * float(-int(profile["hitbox"]["offset_y_raw"])) / 256.0; spray_radius = float(profile["hitbox"]["radius_raw"]) / 256.0
func _extinguish() -> int:
	if not hit_word & int(mission["fire"]["hit_mask"]): return 0
	var damage := (hit_word & 0xFFF) << 5
	if hit_word & 0x2000 and is_instance_valid(player):
		var distance := clampi(roundi(player.global_position.distance_to(model.global_position) * 256.0), 0x80, 0x100); damage += (((((0x100 - distance) * 13) << 6) >> 7) + 0x3C0) >> 3
	if damage == 0: return 0
	if flags & 4: return 1
	strength -= damage
	if strength <= int(mission["fire"]["out_threshold"]): strength = 0; return -1
	return 1
func _atan(dx: int, dz: int) -> int: return roundi(atan2(float(dx), float(dz)) * 2048.0 / PI) & 4095
func _facing_from(target: Vector3i) -> int: return _atan(pos.x - target.x, pos.z - target.z)
func _forward(forward: int, up: int) -> void:
	var sine := int(trig[yaw & 4095][0]); var cosine := int(trig[yaw & 4095][1]); var ps := int(trig[pitch & 4095][0]); var pc := int(trig[pitch & 4095][1])
	var horizontal := (up * ps + forward * pc) >> 12; var vertical_step := (up * pc - forward * ps) >> 12
	pos += Vector3i((sine * horizontal) >> 16, vertical_step >> 4, (cosine * horizontal) >> 16)
func _move_to(target: Vector3i, turn: bool) -> bool:
	if airborne: vertical += int(profile["gravity"])
	var wide := absi(speed); var tall := absi(vertical)
	if pitch != 0: tall = absi(speed); wide = 0x20
	var low := Vector3i(target.x - (wide >> 5), target.y - (tall >> 5), target.z - (wide >> 5)); var arrived := pos.x - low.x >= 0 and pos.x - low.x <= wide >> 3 and pos.z - low.z >= 0 and pos.z - low.z <= wide >> 3
	if pitch != 0: arrived = arrived and pos.y - low.y >= 0 and pos.y - low.y <= tall >> 3
	if arrived: pos = target; return true
	if turn: yaw = _facing_from(target)
	_forward(speed, vertical); return false
func _arc(target: Vector3i, horizontal: int) -> int:
	var dx := target.x - pos.x; var dz := target.z - pos.z; var distance := int(sqrt(float(dx * dx + dz * dz)))
	if horizontal == 0 or distance == 0: return -horizontal
	var ticks := int((distance << 16) / (horizontal << 12))
	if ticks == 0: return -horizontal
	var value := int(((pos.y - target.y) << 16) / ticks) + (((int(profile["gravity"]) << 12) * ticks) >> 1); return -(value >> 12)
func _center() -> Vector3i: var raw: Array = profile["center_raw"]; return Vector3i(int(raw[0]), int(raw[1]), int(raw[2]))
func _run_target() -> Vector3i:
	var spec: Dictionary = profile["run_target"]; var index := (int(spec["yaw"]) + 0x800) & 4095; var center := _center()
	return Vector3i(center.x + ((int(trig[index][0]) * int(spec["distance"])) >> 16), 0, center.z + ((int(trig[index][1]) * int(spec["distance"])) >> 16))
func _sound(id: int) -> void: sound_requested.emit(id, model.global_position)
func _scream() -> void:
	if sound_timer != 0: sound_timer -= 1; return
	var r := _rand(); sound_timer = int(profile["sounds"]["scream_interval"][0]) + (r & int(profile["sounds"]["scream_interval"][1])); _sound(int(profile["sounds"]["scream"][(r >> 5) & 1]))
func _panic() -> void:
	if sub == 0:
		desired = int(profile["controls"]["panic"]); speed = int(profile["panic_speed"]); sound_timer = int(profile["sounds"]["panic_interval"][0]) + (_rand() & int(profile["sounds"]["panic_interval"][1])); sub = 1
	_forward(speed, 0)
	var walls := 0; var bounds: Dictionary = profile["bounds_raw"]
	if pos.x < int(bounds["x"][0]): pos.x = int(bounds["x"][0]); walls = 0x200
	elif pos.x > int(bounds["x"][1]): pos.x = int(bounds["x"][1]); walls = 0x100
	if pos.z < int(bounds["z"][0]): pos.z = int(bounds["z"][0]); walls |= 0x800
	elif pos.z > int(bounds["z"][1]): pos.z = int(bounds["z"][1]); walls |= 0x400
	_reflect(walls)
	var r := _rand(); yaw = (yaw - ((r & 0xFF) - 0x80)) & 4095
	if controller.ember_block & 1: return
	if sound_timer != 0: sound_timer -= 1; return
	sound_timer = int(profile["sounds"]["panic_interval"][0]) + ((r >> 8) & int(profile["sounds"]["panic_interval"][1])); _sound(int(profile["sounds"]["panic"][((r >> 11) & 0xC) >> 2]))
func _reflect(walls: int) -> void:
	if walls & 0x300:
		if walls & 0xC00:
			if walls & 0x100: yaw = (0xC00 - yaw if walls & 0x400 else 0x400 - yaw) & 4095
			else: yaw = (0x400 - yaw if walls & 0x400 else 0xC00 - yaw) & 4095
			return
		yaw = (0x1000 - yaw) & 4095
	if walls & 0xC00: yaw = (0x800 - yaw) & 4095
func _ignite() -> void:
	if sub == 0:
		controller.ember_block |= 1; flags |= 4; desired = int(profile["controls"]["ignite"])
		var origin := _raw(player.global_position) if is_instance_valid(player) else pos; yaw = _atan(pos.x - origin.x, pos.z - origin.z)
		strength = int(profile["strength_max"]); flame_frame = 0; flame_ticks = 0; add_to_group("lock_targets"); ignited.emit(self); sound_timer = int(profile["sounds"]["ignite_timer"]); _sound(int(profile["sounds"]["ignite"])); sub = 1
	elif clock != null and clock.held: state = 2; sub = 0
func _run_out() -> void:
	var target := _run_target()
	if sub == 0:
		flags &= ~4; desired = int(profile["controls"]["burning"]); speed = int(profile["burning_speed"]); yaw = _facing_from(target); sub = 1
	if sub == 1 and _move_to(target, true): state = 3; sub = 0
	if not burning(): state = 4; sub = 0
	_scream()
func _circle() -> void:
	if sub == 0: counter = 0; sub = 1
	_forward(speed, 0); var center := _center(); yaw = (_facing_from(center) + int(profile["circle_yaw_offset"])) & 4095
	var dx := pos.x - center.x; var dz := pos.z - center.z; var distance := int(sqrt(float(dx * dx + dz * dz)))
	if distance > int(profile["circle_radius"]):
		var length := sqrt(float(dx * dx + dz * dz)); pos.x = center.x + int(float(dx) / length * float(int(profile["circle_radius"]))); pos.z = center.z + int(float(dz) / length * float(int(profile["circle_radius"])))
	counter += 1
	if counter >= int(profile["circle_ticks"]): state = 5; sub = 0
	if not burning(): state = 4; sub = 0
	_scream()
func _return() -> void:
	var center := _center()
	if sub == 0:
		speed = int(profile["burning_speed"]); pitch = 0; desired = int(profile["controls"]["panic"])
		if pos.y != center.y: vertical = _arc(center, -speed); airborne = true
		else: vertical = 0; airborne = false
		sub = 1
	elif _move_to(center, true): pos = center; airborne = false; vertical = 0; controller.ember_block &= ~1; state = 0; sub = 0
func _point() -> Array: return profile["routes_raw"][route][point]
func _route() -> void:
	if sub == 0: route = _rand() & 3; point = 0; counter = _rand() & 3; sub = 1
	if sub == 1:
		var spot := _point(); var target := Vector3i(int(spot[0]), int(spot[1]), int(spot[2]))
		match (int(spot[3]) >> 12) & 3:
			0:
				if route_sub == 0: yaw = _facing_from(target); pitch = 0; speed = int(profile["burning_speed"]); route_sub = 1
				elif _move_to(target, true): route_sub = 0; sub = 2
			1:
				if route_sub == 0: pitch = 0; yaw = _facing_from(target); vertical = _arc(target, -speed); airborne = true; route_sub = 1
				elif _move_to(target, true): vertical = 0; speed = int(profile["burning_speed"]); airborne = false; route_sub = 0; sub = 2
				if pos.y >= 0: pos.y = 0
			2:
				if route_sub == 0:
					if target.y < pos.y: yaw = 0x400; pitch = (-0x400) & 4095
					else: yaw = (-0x400) & 4095; pitch = 0x400
					route_sub = 1
				elif _move_to(target, false): route_sub = 0; sub = 2
	elif sub == 2:
		if not burning(): state = 4; sub = 0; _scream(); return
		var spot := _point()
		if int(spot[3]) & 0x8000:
			point = int(spot[3]) & 0xF
			if counter != 0: counter -= 1
			else: pitch = 0; state = 6; sub = 0; _scream(); return
		else: point += 1
		sub = 1
	_scream()
func _spin() -> void:
	var center := _center()
	if sub == 0:
		counter = int(profile["spin_ticks"]); speed = int(profile["burning_speed"])
		if pos.y != center.y: vertical = _arc(center, 0x190); airborne = true
		else: vertical = 0; airborne = false
		desired = int(profile["controls"]["burning"]); sub = 1
	if sub == 1:
		if _move_to(center, true): pos = center; vertical = 0; airborne = false; sub = 2
	elif sub == 2:
		yaw = (yaw + int(profile["spin_speed"])) & 4095; counter -= 1
		if counter == 0: state = 7; sub = 0
	if not burning() and not airborne: state = 4; sub = 0
	_scream()
func _avoid() -> void:
	var origin := _raw(player.global_position) if is_instance_valid(player) else pos
	match sub:
		0:
			vertical = 0; _sound(int(profile["sounds"]["jump"][_rand() & 0xF])); sub = 1
		1:
			yaw = _atan(pos.x - origin.x, pos.z - origin.z); _forward(speed, 0)
			var dx := pos.x - origin.x; var dz := pos.z - origin.z
			if int(sqrt(float(dx * dx + dz * dz))) < int(profile["avoid_distance"]): vertical = int(profile["avoid_jump"]); airborne = true; sub = 2
			_floor()
		2:
			if hit_word & 0x10000: yaw = (yaw + 0x800) & 4095; sub = 3
			else:
				vertical += int(profile["gravity"]); _forward(speed, vertical); var result := _floor()
				if not airborne: vertical = 0; sub = 4
				elif result == 2: sub = 3
		3:
			vertical += int(profile["gravity"]); _forward(speed, vertical); _floor()
			if not airborne: vertical = 0; sub = 4
		4:
			if _move_to(_run_target(), true): state = 3; sub = 0
			else:
				_floor()
				if airborne: sub = 3
	if not burning() and not airborne: state = 4; sub = 0
	_scream()
func _settle() -> void:
	var center := _center()
	if sub == 0: speed = int(profile["panic_speed"]); desired = int(profile["controls"]["panic"]); sub = 1
	if sub == 1:
		if _move_to(center, not airborne): pos = center; vertical = 0; airborne = false; sub = 2
	elif sub == 2: desired = 0; speed = 0; sub = 3
func _raw(point_global: Vector3) -> Vector3i:
	var local: Vector3 = (get_parent() as Node3D).to_local(point_global); return Vector3i(roundi(-local.x * 256.0), roundi(-local.y * 256.0), roundi(local.z * 256.0))
func _floor() -> int:
	var parent := get_parent() as Node3D; var here := Vector3(-pos.x, -pos.y, pos.z) / 256.0; var top := parent.to_global(here + Vector3.UP * 0.5); var hit := Motion.ray(model, top, parent.to_global(here + Vector3.DOWN * 4.0))
	if hit.is_empty(): pos = previous; return 2
	var floor_raw := roundi(-parent.to_local(hit["position"]).y * 256.0)
	if not airborne:
		if absi(floor_raw - pos.y) <= 0x20: pos.y = floor_raw; return 0
		if floor_raw > pos.y: airborne = true; return 1
		pos = previous; return 2
	if vertical >= 0 and pos.y >= floor_raw: pos.y = floor_raw; airborne = false; return 0
	if floor_raw < previous.y - 0x20: pos = Vector3i(previous.x, pos.y, previous.z); return 2
	return 1
func _draw_flame() -> void:
	var mesh := flame.mesh as ImmediateMesh; mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if not burning() or camera == null or atlas == null: return
	var frames: Array = mission["fire"]["effects"]["6"]["subtypes"][0]["frames"]; var frame: Dictionary = frames[flame_frame]
	if frame.get("atlas_id") == null: return
	var source: Dictionary = mission["fire"]["atlas_frames"][int(frame["atlas_id"])]; var uv: Array = source["uv"]
	var center := hit_center
	if skeleton != null and skeleton.get_bone_count() > int(profile["flame"]["bone"]): center = skeleton.to_global(skeleton.get_bone_global_pose(int(profile["flame"]["bone"])).origin) + Vector3.UP * float(-int(profile["flame"]["bone_offset_y_raw"])) / 256.0
	var half := float(strength >> int(profile["flame"]["size_shift"])) / 512.0; var right := camera.global_basis.x * half; var up := camera.global_basis.y * half; var size := atlas.get_size()
	var rect := Rect2(float(uv[0]) / size.x, float(uv[1]) / size.y, float(uv[2]) / size.x, float(uv[3]) / size.y)
	var corners := [center - right + up, center + right + up, center - right - up, center + right - up]; var uvs := [rect.position, Vector2(rect.end.x, rect.position.y), Vector2(rect.position.x, rect.end.y), rect.end]
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in [0, 1, 2, 2, 1, 3]: mesh.surface_set_uv(uvs[index]); mesh.surface_add_vertex(corners[index])
	mesh.surface_end()
