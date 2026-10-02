extends Node
var host: Node3D
var data: Dictionary = {}
var atlas: Texture2D
var area := -1
var level: Node3D
var fires: Array[Node3D] = []
var timers: Dictionary = {}
var remaining := 0
var extinguished_total := 0
var elapsed := 0.0
var idle := 0
var finished := false
var data_rescued := false
var started := false
var kitchen_greeted := false
var busy := false
var radio_pending := 0
var ember_block := 0
var kitchen_data: Node3D
var trig: Array = []
var broken_placements: Dictionary = {}
var effects: Node3D
func configure(gameplay: Node3D) -> bool:
	host = gameplay
	var path := "res://assets/levels/ST1E/fire_mission.json"
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if not parsed is Dictionary: return false
	data = parsed; atlas = load("res://assets/levels/ST1E/" + str(data["fire"]["sprite"]["atlas"])) as Texture2D
	var weather: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/weather/manifest.json")); trig = weather.get("trig4096", []) if weather is Dictionary else []
	return atlas != null and trig.size() == 4096
func enter_area(parent: Node3D, index: int) -> void:
	for fire in fires:
		if is_instance_valid(fire): fire.queue_free()
	fires.clear(); level = parent; area = index; idle = 0; ember_block = 0
	for node_name: String in broken_placements.get(index, []): preload("res://scripts/world/flutter/room_variants.gd").apply_runtime(parent, node_name)
	if is_instance_valid(kitchen_data): kitchen_data.queue_free()
	var profile: Dictionary = data["areas"].get(str(index), {})
	if profile.is_empty() or finished: return
	for flag in profile["entry_flags"]: _set_flag(int(flag), true)
	remaining = int(profile["fire_count_initial"])
	for entry: Dictionary in profile["fires"]: _spawn(entry)
	if index == 0 and not started: started = true; _sequence(profile.get("start_sequence", []))
	if index == 2: ember_block = 1; _spawn_data(parent)
	if index == 2 and not kitchen_greeted: kitchen_greeted = true; await _sequence([{"op": "conversation", "message": int(data["messages"]["kitchen"]), "window": 1}])
	if index == 2 and area == 2: ember_block = 0
func _spawn_data(parent: Node3D) -> void:
	var actor: Dictionary = data["kitchen_data"]["actor"]; var node: Node3D = await preload("res://scripts/world/actors/native_props.gd").spawn_entry(parent, "ST1E", 2, actor["entry"], actor["model"], host.native_context)
	if node == null: push_error("ST1E kitchen Data model failed to load"); return
	if not is_instance_valid(parent) or parent != level or area != 2 or finished: node.queue_free(); return
	kitchen_data = preload("res://scripts/world/missions/fire/native_data.gd").new(); kitchen_data.name = "KitchenData"; parent.add_child(kitchen_data); kitchen_data.configure(data, node, self, host.player, trig, atlas)
	kitchen_data.ignited.connect(func(_actor: Node3D) -> void: remaining += 1); kitchen_data.extinguished.connect(func(_actor: Node3D) -> void: remaining -= 1; _check_clear())
	kitchen_data.sound_requested.connect(host.audio.play_at); kitchen_data.contact_hit.connect(_contact)
func _rand() -> int: return preload("res://scripts/world/actors/native_npc_behavior.gd").next_random(host.native_context)
func _ember(fire: Node3D) -> void:
	var spec: Dictionary = data["kitchen_data"]; var r := _rand(); fire.ember_timer = int(spec["ember_interval"][0]) + (r & int(spec["ember_interval"][1]))
	var origin: Array = data["fire"]["embers"]["target_raw"]; var jitter: Dictionary = spec["ember_target_jitter"]; r = _rand()
	var target := Vector3i(int(origin[0]) - ((r & int(jitter["x"][0])) + int(jitter["x"][1])), int(origin[1]), int(origin[2]) - (((r >> 8) & int(jitter["z"][0])) + int(jitter["z"][1])))
	var source: Array = fire.record["position_raw"]; var base := Vector3i(int(source[0]), int(source[1]), int(source[2])); var launch: Dictionary = spec["ember_launch"]
	var yaw := roundi(atan2(float(base.x - target.x), float(base.z - target.z)) * 2048.0 / PI) & 4095; var index := (yaw + 0x800) & 4095
	var start := Vector3i(base.x + ((int(trig[index][0]) * int(launch["distance"])) >> 16), base.y + int(launch["y"][0]) - (_rand() & int(launch["y"][1])), base.z + ((int(trig[index][1]) * int(launch["distance"])) >> 16))
	var dx := target.x - start.x; var dz := target.z - start.z; var distance := int(sqrt(float(dx * dx + dz * dz))); var ticks := int((distance << 16) / (int(launch["arc_speed"]) << 12)); var vertical := -int(launch["arc_speed"])
	if distance != 0 and ticks != 0: vertical = -((int(((start.y - target.y) << 16) / ticks) + (((int(launch["arc_gravity"]) << 12) * ticks) >> 1)) >> 12)
	var ember: Node3D = preload("res://scripts/world/missions/fire/native_ember.gd").new(); ember.name = "Ember"; level.add_child(ember); ember.configure(data, start, yaw, vertical, trig, atlas, host.player, kitchen_data if is_instance_valid(kitchen_data) else null); ember.contact_hit.connect(_contact)
func _spawn(entry: Dictionary) -> void:
	var fire: Node3D = preload("res://scripts/world/missions/fire/native_fire.gd").new(); fire.name = "Fire_%02d" % int(entry["index"]); level.add_child(fire); fire.configure(data, entry, atlas, host.player)
	fire.extinguished.connect(_fire_out); fire.sound_requested.connect(host.audio.play_at); fire.contact_hit.connect(_contact); fire.ember_requested.connect(_ember); fire.exploded.connect(_explode); fires.append(fire)
	fire.controller = self; fire.ember_timer = int(data["kitchen_data"]["ember_init_timer"][0]) + (_rand() & int(data["kitchen_data"]["ember_init_timer"][1]))
func _explode(fire: Node3D) -> void:
	var shake: Dictionary = data["fire"]["explosion"]["blast"]["init"]["shake"]; host.player.camera_shake(int(shake["mode"]), int(shake["magnitude"]), int(shake["decay"]))
	var change: Dictionary = fire.record.get("map_change", {})
	if not change.is_empty():
		var nodes: Array = broken_placements.get(area, []); var node_name := str(change["node"])
		if not nodes.has(node_name): nodes.append(node_name); broken_placements[area] = nodes
		preload("res://scripts/world/flutter/room_variants.gd").apply_runtime(level, node_name)
func _effects() -> Node3D:
	if not is_instance_valid(effects) or effects.get_parent() != level:
		effects = preload("res://scripts/world/missions/fire/native_blast.gd").new(); effects.name = "FireSteam"; level.add_child(effects); effects.configure(data, trig, atlas, host.player, _rand)
	return effects
func _steam(position_raw: Vector3i, subtype: int) -> void: _effects().spawn_steam(position_raw, subtype)
func _smoke(position_raw: Vector3i) -> Dictionary: return _effects().spawn_smoke(position_raw)
func _contact(fire: Node3D, damage: int) -> void:
	if host.player.no_clip or not host.player.hurt_phase.is_empty(): return
	host.player.take_hit(damage, 0, host.player.global_position - fire.global_position)
func _fire_out(_fire: Node3D, behaviour: int) -> void:
	remaining -= 1; extinguished_total += 1; idle = 0
	var profile: Dictionary = data["areas"][str(area)]
	if behaviour & 2:
		for entry: Dictionary in profile.get("triggered_fires", []): _spawn(entry); remaining += 1
	_check_clear()
func _check_clear() -> void:
	var profile: Dictionary = data["areas"][str(area)]
	if remaining > 0 or finished: return
	for operation: Dictionary in profile["on_clear"]:
		match str(operation["kind"]):
			"flag_set": _set_flag(int(operation["value"]), true)
			"flag_clear": _set_flag(int(operation["value"]), false)
			"scene_start": _finish(true)
func _physics_process(delta: float) -> void:
	if finished or area < 0 or not started or host.loading or busy or host.native_scenes.active or bool(host.dialogue_box.get("active")) and radio_pending == 0: return
	elapsed += delta * float(data.get("native_tick_hz", 25))
	while elapsed >= 1.0 and not finished and not busy: elapsed -= 1.0; _tick()
func _tick() -> void:
	var profile: Dictionary = data["areas"].get(str(area), {})
	if profile.is_empty(): return
	var tick := int(timers.get(area, 0)) + 1; timers[area] = tick
	if tick >= int(profile["timer_limit"]) or host.player.health <= 0: _finish(false); return
	for warning: Dictionary in profile["warnings"]:
		if int(warning["tick"]) == tick: idle = 0; _radio(int(warning["message"])); return
	var flags: Dictionary = host.native_context.get("event_flags", {})
	if bool(flags.get(0x681, flags.get(str(0x681), false))) or is_instance_valid(host.player.hose) and host.player.hose.spraying: idle = 0
	elif idle >= int(profile["hint"]["idle_ticks"]): idle = 0; _radio(int(profile["hint"]["message"])); return
	else: idle += 1
func _radio(message: int) -> void:
	radio_pending += 1; _set_flag(0x681, true)
	while is_inside_tree() and bool(host.dialogue_box.get("active")): await get_tree().process_frame
	if not is_inside_tree(): return
	await host.event_script.play_bound_message("ST1E", "0x8010C000", message, "0x800E7B20", null, 4)
	if not is_instance_valid(host) or not host.is_inside_tree(): return
	radio_pending -= 1
	if radio_pending == 0: _set_flag(0x681, false)
func _sequence(operations: Array) -> void:
	busy = true
	for operation: Dictionary in operations:
		while is_inside_tree() and (host.loading or bool(host.dialogue_box.get("active"))): await get_tree().process_frame
		if str(operation["op"]) == "overlay_show": _banner().show_banner(int(operation["args_raw"][0]), int(operation["args_raw"][1]), int(operation["args_raw"][2]))
		elif str(operation["op"]) == "overlay_hide": _banner().hide_banner()
		if str(operation["op"]) != "conversation": continue
		host.player.set_physics_process(false)
		await host.event_script.play_bound_message("ST1E", "0x8010C000", int(operation["message"]), "0x80048474", null, int(operation.get("window", 1)))
		if not finished: host.player.set_physics_process(true)
	busy = false
func _finish(success: bool) -> void:
	if finished: return
	finished = true
	var completion: Dictionary = data["completion"]
	if success:
		_set_flag(int(completion["flag"]), true)
		# RetroAchievements 83148 "Dammit Data!": every fire (Data included) out before the sprinklers, i.e. any successful clear (the sprinklers come with the timer failure).
		host.achievement_earned.emit("83148")
		if int(timers.get(0, 0)) + int(timers.get(1, 0)) + int(timers.get(2, 0)) < int(completion["fast_limit"]):
			_set_flag(int(completion["fast_flag"]), true)
	elif extinguished_total >= int(completion["failure_fast_count"]): _set_flag(int(completion["fast_flag"]), true)
	while is_inside_tree() and (host.loading or bool(host.dialogue_box.get("active"))): await get_tree().process_frame
	host.loading = true; host.player.set_physics_process(false)
	var ok: bool = await host.native_scenes.run_scene(level, "res://assets/levels/ST1E/scene_0d_%s.json" % ("success" if success else "failure"), area, true)
	if not is_instance_valid(host) or not host.is_inside_tree(): return
	if not ok: push_error(str(host.native_scenes.last_error))
	else: data_rescued = success
	if host.native_scenes.transition_requested: return
	host.player.camera_pivot.rotation = Vector3(deg_to_rad(-12.0), host.player.player_model.rotation.y, 0.0); host.player.camera.make_current(); host.player.refresh_room_camera(); host.area_picker.disabled = false; host.loading = false; host.player.set_physics_process(true)
func _set_flag(id: int, value: bool) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id] = value; flags.erase(str(id)); host.native_context["event_flags"] = flags
func _banner() -> Control:
	var hud: Node = host.get_node("HUD"); var banner := hud.get_node_or_null("MissionBanner") as Control
	if banner == null: banner = preload("res://scripts/ui/hud/mission_banner.gd").new(); banner.name = "MissionBanner"; hud.add_child(banner); hud.move_child(banner, host.dialogue_box.get_index())
	return banner
