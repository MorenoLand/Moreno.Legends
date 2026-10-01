extends Node
var host: Node3D
var data: Dictionary = {}
var metadata: Dictionary = {}
var directory := ""
var area := 0
var accumulator := 0.0
var random_state := 0
var trig: Array = []
var state := 0
var sub_state := 0
var step_count := 0
var stage := 0
var base := 0
var live := 0
var killed := false
var delay := 0
var last_tile := Vector2i.ZERO
var center := Vector3i.ZERO
var yaw_player := 0
var yaw_stick := 0
var last_stick := 0
var zone: Dictionary = {}
var nodes: Array = []
var node_position := 0
var list_position := 0
var delay_index := 0
var tracked: Array[Dictionary] = []
var claim_current := false
var claim_pending := false
var disabled := false
var gate_state := 0
var roll_present := false
func configure(gameplay: Node3D, profile: Dictionary, enemy_metadata: Dictionary, area_index: int, enemy_directory: String) -> void:
	host = gameplay; data = profile; metadata = enemy_metadata; area = area_index; directory = enemy_directory; random_state = int(Time.get_ticks_usec()) & 0xFFFFFFFF
	var math: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/visibility_math.json"))
	if math is Dictionary: trig = math["trig4096"]
	var gate: Dictionary = data["roll_gate"]; var flags: Dictionary = host.native_context.get("event_flags", {})
	roll_present = area == int(gate["area"]) and int(host.native_context.get("native_save_byte14", 0)) == int(gate["stage_state"]) and bool(flags.get(int(gate["flags_set"][0]), flags.get(str(gate["flags_set"][0]), false))) and not bool(flags.get(int(gate["flags_clear"][0]), flags.get(str(gate["flags_clear"][0]), false))); disabled = roll_present
func _random() -> int: random_state = (((random_state << 1) & 0xFFFFFFFF) + (random_state >> 31) + 1) ^ 0x873CA9E5; return random_state
func gate_blocked() -> bool: return claim_current
func gate_claim() -> void: claim_pending = true
func _wrap16(value: int) -> int: return ((value + 32768) & 65535) - 32768
func _player_raw() -> Vector3i:
	var point: Vector3 = host._room_local_position()
	return Vector3i(_wrap16(roundi(-point.x * 256.0)), _wrap16(roundi(-point.y * 256.0)), _wrap16(roundi(point.z * 256.0)))
func _tile() -> Vector2i:
	var raw := _player_raw(); return Vector2i(raw.x >> int(data["tile_shift"]), raw.z >> int(data["tile_shift"]))
func _physics_process(delta: float) -> void:
	if trig.is_empty() or not host.preparation_finished or not host.playable or host.loading or not host.player.is_physics_processing() or host.native_scenes.active or bool(host.dialogue_box.get("active")): return
	accumulator += delta
	while accumulator >= 1.0 / 25.0: accumulator -= 1.0 / 25.0; _tick()
func _tick() -> void:
	claim_current = claim_pending; claim_pending = false
	var input := Vector2(Input.get_axis("strafe_left", "strafe_right"), Input.get_axis("move_back", "move_forward")) if host.player.health >= 0 else Vector2.ZERO
	if input.length_squared() > 0.0001: last_stick = roundi(atan2(input.x, input.y) * 4096.0 / TAU) & 4095
	if roll_present: _roll_gate()
	match state:
		0: state = 1
		1: step_count = 0; stage = 0; delay = 0; last_tile = _tile(); state = 2
		2: _watch()
		3:
			match sub_state:
				0: _begin()
				1: _spawn_wave()
				2: delay -= 1; sub_state = 1 if delay == 0 else sub_state
			_review()
		4: _wait()
func _roll_gate() -> void:
	var x := _player_raw().x; var gate: Dictionary = data["roll_gate"]
	if gate_state == 0:
		if x < int(gate["far_minimum"]): gate_state = 1
		elif x >= int(gate["release_minimum"]): disabled = false; gate_state = 1
	elif x < int(gate["band_maximum"]) and x >= int(gate["band_minimum"]): disabled = true; gate_state = 0
func _watch() -> void:
	if disabled: return
	var tile := _tile()
	if tile == last_tile: return
	step_count += 1
	var thresholds: Array = data["step_thresholds"]
	if stage < thresholds.size() and step_count == int(thresholds[stage]): stage += 1
	var words: Array = data["chance_words"]; var word := int(words[base + stage]) if base + stage < words.size() else 0
	if ((word << (_random() & 31)) & 0x80000000) != 0:
		var raw := _player_raw(); center = raw; yaw_stick = last_stick; yaw_player = (roundi(-host.player.camera_pivot.rotation.y * 4096.0 / TAU) + yaw_stick) & 4095; state = 3; sub_state = 0
	last_tile = tile
func _rotate(point: Vector3i, angle: int) -> Vector3i:
	var pair: Array = trig[angle & 4095]; var sine := int(pair[0]); var cosine := int(pair[1])
	return Vector3i((cosine * point.x + sine * point.z) >> 12, point.y, (-sine * point.x + cosine * point.z) >> 12)
func _pick() -> Vector3i:
	var zones: Array = data["zones"]; var selector: Array = data["zone_selector"]; zone = zones[int(selector[_random() & 31])]; list_position = 0
	var rule: Array = data["node_selectors"][int(zone["flags"]) >> 4]; var set_index := int(rule[0]) + (_random() & 0xFFFF) % int(rule[1])
	var quadrant := (((yaw_stick + 0x200) >> 7) & 0x18) >> 3; var choice: Dictionary = data["node_sets"][set_index][quadrant]; nodes = choice["nodes"]; node_position = 0; delay_index = int(choice["delay_index"])
	return _rotate(Vector3i(0, 0, -int(zone["spawn_radius"])), yaw_player - yaw_stick)
func _begin() -> void:
	sub_state = 1; var offset := _pick()
	if not _tile_clear(center.x + offset.x, center.z + offset.z):
		var turn := 0x400 if _wrap16(yaw_stick) <= 0x800 else -0x400
		yaw_stick = (yaw_stick + turn) & 0xFFFF; offset = _pick()
		if not _tile_clear(center.x + offset.x, center.z + offset.z): yaw_stick = (yaw_stick + turn) & 0xFFFF; offset = _pick()
	center = Vector3i(_wrap16(offset.x + center.x), _wrap16(offset.y + center.y), _wrap16(offset.z + center.z)); live = 0; killed = false
	_spawn_wave()
func _spawn_wave() -> void:
	var indices: Array = zone["indices"]; var templates: Array = data["templates"]
	while true:
		var node: Dictionary = nodes[node_position]; var offset := _rotate(Vector3i(int(node["x"]), int(node["y"]), int(node["z"])), yaw_player - yaw_stick)
		var point := Vector3i(_wrap16(offset.x + center.x), center.y, _wrap16(offset.z + center.z)); var yaw := (yaw_player - yaw_stick + int(node["flag"]) + 0x800) & 0xFFF
		if _tile_clear(point.x, point.z) and tracked.size() < 64: _create(str(templates[int(indices[list_position])]), point, yaw)
		if (int(node["flag"]) & 0x8000) != 0: break
		list_position += 1
		if list_position >= indices.size() or int(indices[list_position]) < 0: break
		node_position += 1
		if (int(zone["flags"]) & 1) == 0:
			var delays: Array = data["delay_words"]; var count := (int(delays[delay_index]) >> (_random() & 0x1E)) & 3
			if count != 0: delay = count; sub_state = 2; return
	if live != 0: state = 4
	else: state = 1
func _tile_clear(x: int, z: int) -> bool:
	var grid: Dictionary = data["tile_grids"][str(area)]; var shifted_x := (x + 0x8000) & 0xFFFF; var shifted_z := (z + 0x8000) & 0xFFFF; var tile_x := (shifted_x >> 9) & 255; var tile_z := (shifted_z >> 9) & 255
	var low_x := tile_x - 1 if (shifted_x & 256) == 0 else tile_x; var low_z := tile_z - 1 if (shifted_z & 256) == 0 else tile_z; var rows: Array = grid["rows"]
	for row in range(low_z, low_z + 2):
		for column in range(low_x, low_x + 2):
			var index_z: int = row - int(grid["z_minimum"]); var index_x: int = column - int(grid["x_minimum"])
			if index_z < 0 or index_z >= rows.size() or index_x < 0 or index_x >= int(grid["width"]) or str(rows[index_z])[index_x] != "1": return false
	return true
func _create(template: String, point: Vector3i, yaw: int) -> void:
	var entry: Dictionary = (data["enemy"] as Dictionary).duplicate(true); var local := Vector3(-float(point.x) / 256.0, 0.0, float(point.z) / 256.0)
	var origin: Vector3 = Vector3(local.x, host._room_local_position().y + 6.0, local.z) + (host.actors.global_position as Vector3)
	var query := PhysicsRayQueryParameters3D.create(origin, origin - Vector3.UP * 20.0, 1); var hit := host.get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty(): return
	var ground: float = float(hit["position"].y) - float(host.actors.global_position.y); entry["source_bytes_hex"] = template + "0000000000000000"; entry["transform"] = {"position": [local.x, 0.0, local.z], "yaw_raw": (-yaw) & 4095}
	var enemy: CharacterBody3D = preload("res://scripts/world/enemies/native_tundra_popup.gd").new(); host.actors.add_child(enemy); enemy.configure_popup(self, entry, metadata, directory, data["rules"], ground)
	enemy.target = host.player; enemy.contact_hit.connect(host._actor_contact); enemy.sound_requested.connect(host.audio.play_at); enemy.drop_requested.connect(host._spawn_actor_drops); enemy.died.connect(_defeated)
	preload("res://scripts/world/rendering/native_material.gd").depth_cue(enemy.model, host.depth_cue_parameters, template.hex_decode()[0])
	tracked.append({"actor": enemy, "counter": int(zone["despawn_ticks"])}); live += 1
func _defeated(_actor: CharacterBody3D) -> void: killed = true
func _review() -> void:
	live = 0
	for entry in tracked.duplicate():
		var enemy = entry["actor"]
		if not is_instance_valid(enemy) or bool(enemy.removed): tracked.erase(entry); continue
		live += 1
		if _expired(entry, enemy): enemy.removed = true; enemy.queue_free(); tracked.erase(entry); live -= 1
func _expired(entry: Dictionary, enemy: CharacterBody3D) -> bool:
	var camera: Camera3D = host.player.camera; var size := host.get_viewport().get_visible_rect().size; var point := enemy.global_position
	var screen := camera.unproject_position(point); var visible := not camera.is_position_behind(point) and screen.x / size.x * 320.0 < float(data["rules"]["offscreen_x_limit"]) and screen.y / size.y * 240.0 < float(data["rules"]["offscreen_y_limit"]) and screen.x >= 0.0 and screen.y >= 0.0
	enemy.offscreen = not visible
	if bool(enemy.protected) or bool(enemy.dying): entry["counter"] = int(zone["despawn_ticks"]); return false
	var player_raw := _player_raw(); var raw := Vector3(-point.x, 0.0, point.z) * 256.0 - Vector3(player_raw.x, 0.0, player_raw.z) + Vector3(host.actors.global_position.x, 0.0, -host.actors.global_position.z) * 256.0
	var distance := raw.x * raw.x + raw.z * raw.z; var limit := float(int(zone["despawn_radius"]) * int(zone["despawn_radius"])) if not visible else float(data["rules"]["onscreen_despawn_distance_squared"])
	if distance > limit: entry["counter"] = int(entry["counter"]) - 1; return int(entry["counter"]) <= 0
	entry["counter"] = int(zone["despawn_ticks"]); return false
func _wait() -> void:
	center = _player_raw(); _review()
	if live == 0:
		state = 1; base = mini(base + 1, int(data["base_maximum"])) if not killed else maxi(base - 1, 0)
