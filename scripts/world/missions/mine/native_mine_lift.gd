extends Node
var host: Node
var actor: Node3D
var data: Dictionary = {}
var ride: Dictionary = {}
var lift: Dictionary = {}
var route: Dictionary = {}
var busy := false
var riding := false
var covered := false
var pending := false
static var profile: Dictionary = {}
static func _load() -> bool:
	if profile.is_empty():
		var path := "res://assets/levels/ST0F/mine_lifts.json"; var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		if parsed is Dictionary: profile = parsed
	return not profile.is_empty()
static func lift_for_route(stage: String, route: Dictionary) -> Dictionary:
	if stage != "ST0F" or not route.has("source_area") or not _load(): return {}
	var raw: Array = route.get("source_transform_raw", [])
	if raw.size() < 3: return {}
	for candidate: Dictionary in profile["lifts"]:
		var position: Array = candidate["position_raw"]
		if int(candidate["area"]) == int(route["source_area"]) and int(position[0]) == int(raw[0]) and int(position[1]) == int(raw[1]) and int(position[2]) == int(raw[2]): return candidate
	return {}
static func mark(stage: String, route: Dictionary) -> Dictionary:
	var candidate := lift_for_route(stage, route)
	if candidate.is_empty(): return route
	var result := route.duplicate(true); result["native_lift"] = {"pad_ram": str(candidate["source_ram"]).to_lower(), "fade_code": int(profile["ride"]["fade_code"]), "entry_fade_code": int(profile["ride"]["entry_fade_code"])}; return result
static func attach_all(gameplay: Node, root: Node3D) -> void:
	if not _load(): return
	for node: Node3D in root.find_children("*", "Node3D", true, false):
		var source: Dictionary = node.get_meta("native_actor_source", {})
		if str(node.get_meta("native_stage", "")) != "ST0F" or int(source.get("class", -1)) != 0x19 or node.has_meta("native_item_controller"): continue
		var lift := new(); lift.name = "NativeMineLift"; node.add_child(lift)
		if not lift.configure(gameplay, node, source, profile): lift.queue_free()
static func arrival_point(gameplay: Node, root: Node3D, route: Dictionary, area: int) -> Vector3:
	if not route.get("native_lift", null) is Dictionary or not route.get("destination_transform_raw", null) is Array: return Vector3.INF
	attach_all(gameplay, root); var raw: Array = route["destination_transform_raw"]
	for node: Node in gameplay.get_tree().get_nodes_in_group("native_mine_lifts"):
		var controller: Node = node.get_meta("native_item_controller", null)
		if not is_instance_valid(controller) or not root.is_ancestor_of(node) or int(node.get_meta("native_area", -1)) != area: continue
		var position: Array = controller.lift["position_raw"]
		if int(controller.lift["area"]) == area and int(position[0]) == int(raw[0]) and int(position[1]) == int(raw[1]) and int(position[2]) == int(raw[2]): return node.global_position + Vector3.UP * (-float(controller.data["hitbox_raw"][2]) / 256.0 + 0.05)
	return Vector3.INF
func configure(gameplay: Node, target: Node3D, entry: Dictionary, profile: Dictionary) -> bool:
	host = gameplay; actor = target; data = profile["pad"]; ride = profile["ride"]; var address := str(entry.get("source_ram", "")).to_lower()
	for candidate: Dictionary in profile["lifts"]:
		if str(candidate["source_ram"]).to_lower() == address: lift = candidate
	if lift.is_empty(): return false
	for item: Dictionary in host.routes:
		if route.is_empty() and lift_for_route("ST0F", item) == lift: route = item
	if route.is_empty(): return false
	var yaw := int(lift["yaw_raw"]); var descriptors: Dictionary = data["target_descriptors_by_yaw"]; var selected := str(yaw) if yaw in [0, 0x400, 0x800] else "3072"
	actor.set_meta("native_interaction", {"stage": "ST0F", "actor_class": 0x19, "actor_callback": "0x800F2E4C", "bank_id": data["bank_id"], "message_index": int(lift["message_index"]), "message_call": data["message_call"], "request_kind": 0, "target_flags60": int(data["target_flags60"]), "target_descriptor_raw": descriptors[selected], "target_descriptor_source": data["target_descriptor_source"], "target_criteria": data["target_criteria"]})
	actor.set_meta("native_item_controller", self); actor.set_meta("native_interaction_label", "Use"); actor.add_to_group("native_interaction_targets"); actor.add_to_group("native_mine_lifts")
	if actor.get_node_or_null("NativeLiftPlatform") == null:
		var bounds: Array = data["hitbox_raw"]; var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
		var body := AnimatableBody3D.new(); body.name = "NativeLiftPlatform"; body.collision_layer = 1; body.collision_mask = 0; body.sync_to_physics = false; body.scale = Vector3.ONE / actor.scale
		var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); box.size = maximum - minimum; shape.shape = box; shape.position = (minimum + maximum) * 0.5; body.add_child(shape); actor.add_child(body)
	return true
func can_interact() -> bool:
	if busy or riding or not is_instance_valid(actor) or route.is_empty(): return false
	var facing: Dictionary = data["facing"]; var heading := roundi(-host.player.player_model.global_rotation.y * 4096.0 / TAU) & 4095
	return absi(((heading + int(facing["player_yaw_bias"])) & 4095) - ((int(lift["yaw_raw"]) + int(facing["actor_yaw_bias"])) & 4095)) < int(facing["half_range"])
func interact() -> bool:
	if not can_interact(): return false
	busy = true; var index := int(lift["locked_message_index"]) if _flag(int(data["lock_flag_base"]) + int(lift["lock_flag_offset"])) else int(lift["message_index"])
	var shown: bool = await host.event_script.play_bound_message("ST0F", str(data["bank_id"]), index, str(data["message_call"]), actor, 0)
	pending = true; busy = false; return shown
func _physics_process(_delta: float) -> void:
	if not pending or busy or riding or not is_instance_valid(actor) or host.loading or bool(host.dialogue_box.get("active")): return
	pending = false
	if not _flag(int(data["answer_flag"])): return
	_set_flag(int(data["answer_flag"]), false)
	if not _flag(int(data["lock_flag_base"]) + int(lift["lock_flag_offset"])): host._use_door(route)
func ride_scene() -> void:
	riding = true; var player: CharacterBody3D = host.player; var first: Dictionary = ride["first_frame"]; var origin := actor.global_position; var direction := -1.0 if int(lift["direction"]) != 0 else 1.0
	player.velocity = Vector3.ZERO; player.player_model.rotation.y = -float((int(lift["yaw_raw"]) + int(first["yaw_offset_raw"])) & 4095) * TAU / 4096.0; player._play_animation("idle"); player.global_position = Vector3(origin.x, origin.y - float(first["player_height_raw"]) / 256.0, origin.z)
	var frame := 0; var speed := 0; var elapsed := 0.0; var rate := float(ride["tick_hz"]); var period := int(ride["motor_sound_period_by_tick_mode"]["default"])
	covered = false
	while not covered and is_instance_valid(actor):
		await get_tree().physics_frame; elapsed += get_physics_process_delta_time() * rate
		while elapsed >= 1.0 and not covered:
			elapsed -= 1.0; frame += 1
			if frame == int(ride["fade_frame"]): _cover()
			speed = mini(speed + int(ride["acceleration_raw"]), int(ride["maximum_speed_raw"]))
			var step := Vector3(0.0, direction * float(speed) / 256.0, 0.0); player.global_position += step; actor.global_position += step
			if frame - 1 < int(ride["motor_sound_frames"]) and (frame - 1) % period == 0: host.audio.play_at(int(ride["motor_sound"]), actor.global_position)
	if is_instance_valid(actor): actor.global_position = origin
	riding = false
func _cover() -> void:
	await host.transition_overlay.request(int(ride["fade_code"])); covered = true
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag(id: int, value: bool) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id if flags.has(id) or not flags.has(str(id)) else str(id)] = value; host.native_context["event_flags"] = flags
