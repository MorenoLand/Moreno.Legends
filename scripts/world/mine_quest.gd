extends Node
var host: Node3D
var catalogs: Dictionary = {}
var actor_records: Dictionary = {}
var stage := ""
var area := -1
var parent: Node3D
var busy := false
var elapsed := 0.0
var state := 0
var boss: CharacterBody3D
var ordinary: Dictionary = {}
func configure(gameplay: Node3D) -> void:
	host = gameplay
	for name in ["ST0D", "ST0F"]:
		var path := "res://assets/levels/%s/mine_quest.json" % name; var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		if parsed is Dictionary: catalogs[name] = parsed
	var path := "res://assets/levels/ST0F/mine_actors.json"; var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if parsed is Dictionary:
		for record: Dictionary in parsed.get("actors", []): actor_records[str(record["source_ram"]).to_lower()] = record
func _physics_process(delta: float) -> void:
	if not host.preparation_finished or not host.playable or host.loading or busy or not host.player.is_physics_processing() or host.native_scenes.active or bool(host.dialogue_box.get("active")): return
	var current := str(host.manifest_path.get_base_dir().get_file()); var index := int(host.areas[host.area_picker.selected]["index"]); var root: Node3D = host.room_stream.room_root(current, index) if host.streaming_rooms else host.level
	if current != stage or index != area or root != parent:
		stage = current; area = index; parent = root; state = 0; elapsed = 0.0; ordinary.clear(); boss = null
		if catalogs.has(stage): _enter()
		return
	if not catalogs.has(stage): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and not busy:
		elapsed -= 1.0
		if stage == "ST0F" and int(host.native_context.get("native_save_byte14", 0)) == 0: _tick_mine()
		elif stage == "ST0D" and area == 0 and not parent.has_meta("native_mine_entrance_open") and (int(host.native_context.get("native_save_byte14", 0)) != 0 or _flag(0x5E1) or _flag(0x5E2)): _refresh_entrance()
func _refresh_entrance() -> void:
	busy = true; await _open_entrance(); busy = false
func _enter() -> void:
	busy = true
	if stage == "ST0D":
		if area == 0: await _open_entrance()
		await _spawn_exterior()
		await _attach_items()
	elif int(host.native_context.get("native_save_byte14", 0)) == 0:
		var data: Dictionary = catalogs[stage]
		if area == int(data["entry_actions"]["area"]):
			if not _flag(int(data["quest_flags"]["entrance_initialized"])):
				for flag in data["entry_actions"]["first_visit_set"]: _set_flag(int(flag), true)
				for record: String in data["entry_actions"]["first_visit_records"]: await _spawn_ordinary(record)
			for flag in data["entry_actions"]["every_entry_clear"]: _set_flag(int(flag), false)
			state = 1
		elif area == int(data["intro"]["area"]):
			var record := "0x8010083c" if _flag(0x580) else "0x80100828" if _flag(0x689) else "0x80100814"
			await _spawn_ordinary(record)
			if not _flag(0x580): _set_flag(0x689, true)
			state = 3 if _flag(0x580) else 2
		elif area == int(data["boss"]["area"]) and _flag(0x582) and not _flag(0x583): await _ensure_boss()
		elif area == int(data["item_gate"]["area"]): _item_wave()
	if stage == "ST0F": await _attach_items()
	busy = false
func _tick_mine() -> void:
	var data: Dictionary = catalogs[stage]
	if area == int(data["intro"]["area"]) and state == 2 and int(-host._room_local_position().x * 256.0) >= int(data["intro"]["native_x_minimum"]):
		state = 3; _set_flag(int(data["intro"]["flag"]), true); _scene(int(data["intro"]["scene"]))
	elif area == int(data["pre_boss"]["area"]) and state == 0:
		state = 1
		if _flag(0x583) and not _flag(0x584): _clear_cutscene_flags(); _set_flag(0x584, true); _scene(int(data["return"]["scene"]))
		elif not _flag(0x583) and not _flag(0x581): _clear_cutscene_flags(); _set_flag(0x581, true); _scene(int(data["pre_boss"]["scene"]))
		elif not _flag(0x583): _spawn_preboss()
	elif area == int(data["boss"]["area"]) and state == 0:
		if _flag(0x583): state = 2
		elif not _flag(0x582): state = 1; _clear_cutscene_flags(); _set_flag(0x582, true); _set_flag(0x710, true); _scene(int(data["boss"]["scene_start"]))
		else: state = 1; _set_flag(0x710, true)
	elif area == int(data["item_gate"]["area"]): _item_wave()
func _item_wave() -> void:
	var gate: Dictionary = catalogs["ST0F"]["item_gate"]; var index := int(gate["set_mode"] if _flag(int(gate["event_flag"])) else gate["clear_mode"])
	if int(host.actor_route.get("script_area_index", -1)) != index: host.actor_route = {"script_area_index": index, "yaw_offset_gate": false}; host._load_actors()
func _scene(id: int) -> void:
	busy = true; host.loading = true; host.area_picker.disabled = true; host.player.velocity = Vector3.ZERO; host.player.set_physics_process(false)
	var success: bool = await host.native_scenes.run_scene(parent, "res://assets/levels/ST0F/scene_%02x.json" % id, area)
	if not is_instance_valid(host) or not host.is_inside_tree(): return
	if not success: host.native_scene_failed.emit(str(host.native_scenes.last_error)); push_error(str(host.native_scenes.last_error))
	elif id == 0x52: await _ensure_boss()
	elif id == 0x51: await _spawn_preboss()
	if host.native_scenes.transition_requested: return
	host._update_native_player_pose(); host.area_picker.disabled = false; host.loading = false; host.player.set_physics_process(true); busy = false
func _spawn_ordinary(address: String) -> Node3D:
	var key := address.to_lower(); var previous: Node3D = ordinary.get(key)
	if is_instance_valid(previous): return previous
	for node: Node3D in parent.find_children("*", "Node3D", true, false):
		if str(node.get_meta("native_actor_source", {}).get("source_record_ram", "")).to_lower() == key: ordinary[key] = node; return node
	if key == "0x80100864":
		for entry: Dictionary in catalogs["ST0F"]["records"]:
			if str(entry["source_record_ram"]).to_lower() != key: continue
			var effect: Node3D = preload("res://scripts/world/native_mine_flame.gd").new(); parent.add_child(effect); effect.configure(entry); effect.add_to_group("native_pool_actors"); ordinary[key] = effect; return effect
	var record: Dictionary = actor_records.get(key, {})
	if record.is_empty(): return null
	var node: Node3D = await preload("res://scripts/world/native_props.gd").spawn_entry(parent, stage, area, record["entry"], record["model"], host.native_context)
	if node != null:
		ordinary[key] = node; node.add_to_group("native_pool_actors"); preload("res://scripts/world/native_material.gd").depth_cue(node, host.depth_cue_parameters)
		var behavior: Node
		if int(record["entry"].get("actor_class", -1)) == 0x60: behavior = preload("res://scripts/world/native_mine_roll.gd").new(); behavior.name = "NativeMineRoll"
		elif int(record["entry"].get("actor_class", -1)) == 0x6F: behavior = preload("res://scripts/world/native_mine_refractor.gd").new(); behavior.name = "NativeMineRefractor"
		if behavior != null: node.add_child(behavior); behavior.configure(host, node, record["entry"], record["model"])
	return node
func _spawn_preboss() -> void:
	var was_busy := busy
	busy = true
	for address in ["0x80100850", "0x80100864", "0x80100878"]: await _spawn_ordinary(address)
	busy = was_busy
func _ensure_boss() -> void:
	if is_instance_valid(boss): return
	var address := str(catalogs["ST0F"]["boss"]["actor_record_ram"]).to_lower(); var record: Dictionary = actor_records.get(address, {})
	if record.is_empty(): push_error("Missing native mine boss actor contract"); return
	var existing: Node3D
	for node: Node3D in parent.find_children("*", "Node3D", true, false):
		if str(node.get_meta("native_actor_source", {}).get("source_record_ram", "")).to_lower() == address: existing = node; break
	var controller := load("res://scripts/world/native_mine_boss.gd") as GDScript
	if controller == null: push_error("Missing native mine boss controller"); return
	boss = controller.new(); host.actors.add_child(boss); boss.configure(record["entry"], record["model"], "res://assets/levels/ST0F"); boss.target = host.player; boss.contact_hit.connect(host._actor_contact); boss.sound_requested.connect(host.audio.play_at); boss.defeated.connect(_boss_died); boss.add_to_group("lock_targets"); boss.add_to_group("native_pool_actors")
	if is_instance_valid(existing): boss.global_transform = existing.global_transform; existing.get_parent().remove_child(existing); existing.queue_free()
	preload("res://scripts/world/native_material.gd").depth_cue(boss.model, host.depth_cue_parameters)
func _boss_died(_actor: CharacterBody3D) -> void:
	if stage != "ST0F" or area != int(catalogs["ST0F"]["boss"]["area"]) or state == 2: return
	state = 2; _set_flag(0x583, true); _set_flag(0x710, false); _scene(int(catalogs["ST0F"]["boss"]["scene_defeat"]))
func _open_entrance() -> void:
	var entrance: Dictionary = catalogs["ST0D"]["entrance"]
	if int(host.native_context.get("native_save_byte14", 0)) == 0 and not _flag(0x5E1) and not _flag(0x5E2): return
	for route: Dictionary in host.routes:
		if int(route["source_area"]) == 0 and str(route["destination_stage"]) == "ST0F": route["native_contacts"] = entrance["native_contacts"].duplicate(true); route["native_automatic_walk"] = entrance["native_automatic_walk"].duplicate(true)
	if parent.has_meta("native_mine_entrance_open"): return
	var scene := load("res://assets/levels/ST0D/" + str(entrance["model_file"])) as PackedScene
	if scene == null: push_error("Missing native mine entrance variant"); return
	for mesh: MeshInstance3D in parent.find_children("placement_%03d_model_*" % int(entrance["placement"]), "MeshInstance3D", true, false):
		mesh.hide()
		for body: CollisionObject3D in mesh.find_children("*", "CollisionObject3D", true, false): body.collision_layer = 0; body.set_meta("native_floor_replaced", true)
	for body: StaticBody3D in parent.find_children("NativePlacementFloor_%03d*" % int(entrance["placement"]), "StaticBody3D", true, false): body.collision_layer = 0; body.queue_free()
	var node := scene.instantiate() as Node3D; parent.add_child(node); preload("res://scripts/world/native_material.gd").apply(node); preload("res://scripts/world/native_material.gd").depth_cue(node, host.depth_cue_parameters)
	for mesh: MeshInstance3D in node.find_children("*", "MeshInstance3D", true, false):
		for layer in [1, 4]:
			var body := StaticBody3D.new(); body.collision_layer = layer; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh.mesh.create_trimesh_shape()
			if layer == 4: (shape.shape as ConcavePolygonShape3D).backface_collision = true
			body.add_child(shape); mesh.add_child(body)
	preload("res://scripts/world/native_floor.gd").apply(node, {"0": {"boxes": entrance["collision_boxes"]}}, 0, host.native_context)
	parent.set_meta("native_mine_entrance_open", true)
func _spawn_exterior() -> void:
	var controller := load("res://scripts/world/native_tundra_enemy.gd") as GDScript
	if controller == null: return
	host.actor_manifest["pickups"] = "pickups.json"
	for entry: Dictionary in catalogs["ST0D"].get("exterior_enemies", []):
		if int(entry["area_index"]) != area or int(entry["actor_class"]) != 0x7E: continue
		for node: Node3D in parent.find_children("*", "Node3D", true, false):
			var source: Dictionary = node.get_meta("native_actor_source", {})
			if str(source.get("source_bytes_hex", source.get("source_bytes", ""))) == str(entry["source_bytes_hex"]): node.get_parent().remove_child(node); node.queue_free()
		var model: Dictionary = {}
		for candidate: Dictionary in catalogs["ST0D"]["models"]:
			if int(candidate["model_index"]) == int(entry["model_index"]): model = candidate; break
		var enemy: CharacterBody3D = controller.new(); host.actors.add_child(enemy)
		if not enemy.configure(host, entry, model, "res://assets/levels/ST0D"): enemy.queue_free(); continue
		enemy.sound_requested.connect(host.audio.play_at); enemy.drop_requested.connect(host._spawn_actor_drops); enemy.add_to_group("lock_targets")
		preload("res://scripts/world/native_material.gd").depth_cue(enemy.model, host.depth_cue_parameters)
func _attach_items() -> void:
	var controller := load("res://scripts/world/native_mine_item.gd") as GDScript
	if controller == null: return
	for descriptor: Dictionary in catalogs[stage].get("items", []):
		var entry: Dictionary = descriptor["entry"]
		if int(entry["area_index"]) != area: continue
		var model: Dictionary = {}
		for candidate: Dictionary in catalogs[stage]["item_models"]:
			if int(candidate["model_index"]) == int(entry["model_index"]): model = candidate; break
		for node: Node3D in parent.find_children("*", "Node3D", true, false):
			var source: Dictionary = node.get_meta("native_actor_source", {})
			if str(source.get("source_bytes_hex", source.get("source_bytes", ""))) == str(entry["source_bytes_hex"]): node.get_parent().remove_child(node); node.queue_free()
		var actor: Node3D = await preload("res://scripts/world/native_props.gd").spawn_entry(parent, stage, area, entry, model, host.native_context)
		if actor == null: push_error("Native mine chest model failed to load"); continue
		if int(entry.get("transform_raw", [0, 0, 0])[1]) == -1: await preload("res://scripts/world/native_actor_motion.gd").settle_on_floor(actor)
		preload("res://scripts/world/native_material.gd").depth_cue(actor, host.depth_cue_parameters)
		var item: Node = controller.new(); actor.add_child(item); item.configure(host, actor, entry, descriptor)
func _clear_cutscene_flags() -> void:
	_set_flag(0x700, false); _set_flag(0x701, false)
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag(id: int, value: bool) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id] = value; flags.erase(str(id)); host.native_context["event_flags"] = flags
