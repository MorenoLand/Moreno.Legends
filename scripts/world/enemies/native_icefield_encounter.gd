extends Node
const Props := preload("res://scripts/world/actors/native_props.gd")
var host: Node
var level: Node3D
var data: Dictionary = {}
var state := 0
var elapsed := 0.0
var boss: CharacterBody3D
var walls: Array[StaticBody3D] = []
var staged: Dictionary = {}
static func attach(parent: Node3D, stage: String, area: int, context: Dictionary) -> void:
	if stage != "ST11" or area != 0 or int(context.get("native_save_byte14", -1)) != 1 or parent.has_node("IcefieldEncounter"): return
	var encounter: Variant = Props._read_manifest("res://assets/levels/ST11/scripted_actors.json").get("native_encounter", null)
	var gameplay: Node = parent
	while gameplay != null and gameplay.get_node_or_null("Player") == null: gameplay = gameplay.get_parent()
	if not encounter is Dictionary or gameplay == null: return
	var node := new(); node.name = "IcefieldEncounter"; parent.add_child(node); node.host = gameplay; node.level = parent; node.data = encounter
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag(id: int, value: bool) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id] = value; flags.erase(str(id)); host.native_context["event_flags"] = flags
func _physics_process(delta: float) -> void:
	if state != 0 or not host.preparation_finished or not host.playable or host.loading or not host.player.is_physics_processing() or host.native_scenes.active or bool(host.dialogue_box.get("active")): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and state == 0:
		elapsed -= 1.0
		var z := roundi(level.to_local(host.player.global_position).z * 256.0)
		if _flag(int(data["trigger"]["flag"])): state = 3
		elif z >= int(data["trigger"]["player_z_raw_minimum"]): _begin()
		else: _stage_burrowers(z)
func _stage_burrowers(z: int) -> void:
	var models := {}
	for candidate: Dictionary in Props._read_manifest("res://assets/levels/ST11/scripted_actors.json").get("models", []): models[int(candidate.get("model_index", -1))] = candidate
	for index in range(data["burrowers"].size()):
		var row: Dictionary = data["burrowers"][index]
		if not staged.has(index) and int(row["player_z_raw_exclusive_minimum"]) < z: staged[index] = true; Props.spawn_entry(level, "ST11", 0, row["entry"], models.get(int(row["entry"]["model_index"]), {}), host.native_context)
func _begin() -> void:
	state = 1; _set_flag(int(data["trigger"]["flag"]), true); host.loading = true; host.area_picker.disabled = true; host.player.velocity = Vector3.ZERO; host.player.set_physics_process(false)
	var scene_brightness: Array = []
	for actor: Dictionary in JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/ST11/scene_2a.json"))["actors"]:
		if str(actor["existing_actor"]).begins_with("icefield_barrier_"): scene_brightness.append(str(actor["entry"]["source_bytes_hex"]).hex_decode()[8])
	var staged_nodes: Array[Node3D] = [_create_boss(host.actors, false)]
	staged_nodes[0].set_meta("native_existing_actor", "icefield_boss"); staged_nodes[0].set_meta("native_scene_deferred", true); staged_nodes[0].visible = false
	for index in range(data["barriers"].size()):
		var marker := Node3D.new(); marker.name = "IcefieldBarrierMarker_%d" % index; host.actors.add_child(marker); marker.global_position = level.to_global(_local(data["barriers"][index]["transform"]["position"])); marker.set_meta("native_existing_actor", "icefield_barrier_%d" % index); marker.set_meta("native_scene_deferred", true); marker.visible = false; staged_nodes.append(marker); _shimmer(marker, scene_brightness[index], data["barriers"][index])
	var success: bool = await host.native_scenes.run_scene(level, "res://assets/levels/ST11/scene_%02x.json" % int(data["trigger"]["scene"]), 0)
	if not is_instance_valid(host) or not host.is_inside_tree(): return
	if not success: host.native_scene_failed.emit(str(host.native_scenes.last_error)); push_error(str(host.native_scenes.last_error))
	for node: Node3D in staged_nodes:
		if is_instance_valid(node): node.queue_free()
	for barrier: Dictionary in data["barriers"]: _wall(barrier)
	boss = _create_boss(level, true)
	host._update_native_player_pose(); host.area_picker.disabled = false; host.player.set_physics_process(true); host.loading = false; state = 2
	var radio: Dictionary = data["radio"]
	if host.event_script.can_play_bound_message("ST11", str(radio["bank"]), int(radio["message"])): host.event_script.play_bound_message("ST11", str(radio["bank"]), int(radio["message"]), "0x800ef5e4", null, int(radio["window"]))
func _shimmer(parent: Node3D, brightness: int, barrier: Dictionary) -> void:
	var visual := preload("res://scripts/world/enemies/native_icefield_barrier.gd").new(); parent.add_child(visual); visual.configure(level, barrier["transform_raw"], brightness)
func _local(position: Array) -> Vector3: return Vector3(float(position[0]), float(position[1]), float(position[2]))
func _wall(barrier: Dictionary) -> void:
	var body := StaticBody3D.new(); body.name = "IcefieldBarrier_%d" % int(barrier["record_id"]); body.collision_layer = 1; body.collision_mask = 0; level.add_child(body)
	for box: Dictionary in barrier["boxes"]:
		var x: Array = box["x"]; var y: Array = box["y"]; var z: Array = box["z"]; var shape := CollisionShape3D.new(); var volume := BoxShape3D.new()
		volume.size = Vector3(float(x[1]) - float(x[0]), float(y[1]) - float(y[0]), float(z[1]) - float(z[0])) / 256.0; shape.shape = volume
		shape.position = Vector3(-(float(x[0]) + float(x[1])) * 0.5, -(float(y[0]) + float(y[1])) * 0.5, (float(z[0]) + float(z[1])) * 0.5) / 256.0; body.add_child(shape)
	_shimmer(body, str(barrier["source_bytes_hex"]).hex_decode()[8], barrier); walls.append(body)
func _create_boss(parent: Node3D, fight: bool) -> CharacterBody3D:
	var entry: Dictionary = data["boss"]["entry" if fight else "scene_entry"]; var model: Dictionary = {}
	for candidate: Dictionary in Props._read_manifest("res://assets/levels/ST11/scripted_actors.json").get("models", []):
		if int(candidate.get("model_index", -1)) == int(data["boss"]["model_index"]): model = candidate
	var enemy: CharacterBody3D = preload("res://scripts/world/enemies/native_icefield_boss.gd").new(); parent.add_child(enemy)
	if not enemy.configure(host, entry, model, "res://assets/levels/ST11/" + str(entry["model_file"])): enemy.queue_free(); push_error("Missing native Icefield boss resource"); return null
	var point := level.to_global(_local(entry["transform"]["position"])); enemy.global_position = Vector3(point.x, enemy.global_position.y, point.z)
	preload("res://scripts/world/rendering/native_material.gd").depth_cue(enemy.model, host.depth_cue_parameters)
	if not fight: return enemy
	host.actor_manifest["pickups"] = "pickups.json"
	enemy.sound_requested.connect(host.audio.play_at); enemy.drop_requested.connect(host._spawn_actor_drops); enemy.contact_hit.connect(host._actor_contact); enemy.defeated.connect(_defeated)
	host.game_hud.bind_boss(enemy, 1, Color8(254, 0, 0))
	return enemy
func _defeated(_actor: CharacterBody3D) -> void:
	if state != 2: return
	state = 3; var defeat: Dictionary = data["defeat"]; _set_flag(int(defeat["flag"]), true)
	var fade: Dictionary = defeat["fade"]; host.audio.fade_sequences(int(fade["mask"]), int(fade["speed"]), int(fade["delay"]))
	for wall: StaticBody3D in walls: wall.queue_free()
	walls.clear()
	var models := {}
	for candidate: Dictionary in Props._read_manifest("res://assets/levels/ST11/scripted_actors.json").get("models", []): models[int(candidate.get("model_index", -1))] = candidate
	for entry: Dictionary in defeat["spawn"]: Props.spawn_entry(level, "ST11", 0, entry, models.get(int(entry["model_index"]), {}), host.native_context)
