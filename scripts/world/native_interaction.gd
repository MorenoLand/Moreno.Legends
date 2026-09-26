extends RefCounted
const FRIENDLY_TALK_REQUESTS := {"ST19": "0x800E82BC", "ST1A": "0x800E7934", "ST1B": "0x800E7D70", "ST2A": "0x800E84B8"}
static func attach(node: Node3D, record: Dictionary) -> bool:
	var binding: Variant = record.get("native_interaction", null)
	if not binding is Dictionary or binding.is_empty(): return false
	node.set_meta("native_interaction", binding.duplicate(true)); node.set_meta("native_actor_source", record.duplicate(true)); node.add_to_group("native_interaction_targets")
	return true
static func binding(node: Node3D) -> Dictionary:
	return node.get_meta("native_interaction", {}) if is_instance_valid(node) else {}
static func has_target_profile(node: Node3D) -> bool:
	var source := binding(node); var descriptor: Array = source.get("target_descriptor_raw", []); var criteria: Dictionary = source.get("target_criteria", {})
	return descriptor.size() == 6 and source.has("target_flags60") and criteria.has("range_extra_raw") and criteria.has("yaw_half_cone_raw") and criteria.has("line_of_sight") and not bool(criteria["line_of_sight"])
static func target_score(player: Node3D, target: Node3D) -> float:
	if not is_instance_valid(player) or not is_instance_valid(target) or not has_target_profile(target): return INF
	var source := binding(target); var descriptor: Array = source["target_descriptor_raw"]; var criteria: Dictionary = source["target_criteria"]; var flags := int(source["target_flags60"]); var model := player.get("player_model") as Node3D
	if (flags & 1) == 0 or model == null: return INF
	var origin := Vector3i(floori(-player.global_position.x * 256.0), floori(-player.global_position.y * 256.0), floori(player.global_position.z * 256.0)); var center := Vector3i(floori(-target.global_position.x * 256.0) + int(descriptor[0]), floori(-target.global_position.y * 256.0) + int(descriptor[1]), floori(target.global_position.z * 256.0) + int(descriptor[2])); var offset := center - origin
	if offset.y <= int(descriptor[4]) or offset.y >= int(descriptor[5]): return INF
	var distance := floori(sqrt(float(offset.length_squared())))
	if distance >= int(criteria["range_extra_raw"]) + int(descriptor[3]): return INF
	var bearing := preload("res://scripts/world/native_talk_facing.gd")._heading(Vector3.ZERO, Vector3(-float(offset.x), -float(offset.y), float(offset.z)) / 256.0); var heading := roundi(-model.global_rotation.y * 4096.0 / TAU) & 4095; var delta := (heading - bearing) & 4095; var angle := mini(delta, 4096 - delta)
	if angle >= int(criteria["yaw_half_cone_raw"]): return INF
	if flags & 0x80:
		var target_heading := roundi(-target.global_rotation.y * 4096.0 / TAU) & 4095; var target_delta := (target_heading - bearing + 0x800) & 4095
		if mini(target_delta, 4096 - target_delta) > 0x200: return INF
	return float(distance + (angle >> 2))
static func player_faces_target(player: Node3D, target: Node3D) -> bool:
	if not is_instance_valid(player) or not is_instance_valid(target): return false
	var model := player.get("player_model") as Node3D
	if model == null: return false
	var heading := roundi(-model.global_rotation.y * 4096.0 / TAU) & 4095; var bearing := preload("res://scripts/world/native_talk_facing.gd")._heading(player.global_position, target.global_position); var difference := (heading - bearing) & 4095
	return mini(difference, 4096 - difference) < 512
static func begin_facing(node: Node3D, player: Node3D) -> Node:
	if not is_instance_valid(node) or not is_instance_valid(player): return null
	var source := binding(node)
	if source.is_empty():
		var entry: Variant = node.get("source") if node is StaticBody3D else null
		if not entry is Dictionary or not FRIENDLY_TALK_REQUESTS.has(str(entry.get("stage", ""))) or int(entry.get("actor_class", -1)) != 0: return null
		var private: Array = entry.get("native_private_raw", [])
		if private.size() != 4 or int(private[3]) == 255: return null
		source = {"request_kind": (int(private[1]) >> 2) & 0x10, "request_call": FRIENDLY_TALK_REQUESTS[str(entry["stage"])]}
	if not source.has("request_kind") or (int(source["request_kind"]) & 0x10) != 0: return null
	var facing := preload("res://scripts/world/native_talk_facing.gd").new(); facing.name = "NativeTalkFacing"; node.add_child(facing); facing.configure(node, player); return facing
static func end_facing(facing: Node) -> void:
	if is_instance_valid(facing): await facing.return_to_saved_heading()
static func resolve_pose(record: Dictionary, native_context: Dictionary) -> Dictionary:
	var resolver: Dictionary = record.get("native_pose_resolver", {})
	if resolver.is_empty(): return record.get("transform", {})
	var player: Variant = native_context.get(str(resolver["player_pose_key"]), null)
	if not player is Array or player.size() < 3: push_error("Missing original player pose for native NPC position resolver"); return {}
	var selected: Dictionary = resolver["default"]
	for candidate: Dictionary in resolver["cases"]:
		if int(player[0]) == int(candidate["player_xz"][0]) and int(player[2]) == int(candidate["player_xz"][1]): selected = candidate; break
	var raw: Array = record["transform_raw"]
	return {"position": [-float(selected["actor_xz"][0]) / 256.0, -float(raw[1]) / 256.0, float(selected["actor_xz"][1]) / 256.0], "yaw_raw": int(selected["yaw_raw"]), "yaw_turns": -float(selected["yaw_raw"]) / 4096.0, "floor_height": bool(record["transform"].get("floor_height", false)), "native_resolver_result": int(selected["result"])}
static func can_play(node: Node3D, event_script: Node) -> bool:
	var source := binding(node)
	if source.is_empty() or not is_instance_valid(event_script): return false
	if source.has("bank_id"): return event_script.can_play_bound_message(str(source["stage"]), str(source["bank_id"]), int(source["message_index"]))
	return event_script.can_play_native_call(str(source["stage"]), str(source["message_call"]), int(source["message_index"]))
static func play(node: Node3D, event_script: Node) -> bool:
	if not can_play(node, event_script): return false
	var source := binding(node)
	if source.has("bank_id"): return await event_script.play_bound_message(str(source["stage"]), str(source["bank_id"]), int(source["message_index"]), str(source["message_call"]), node)
	return await event_script.play_native_call(str(source["stage"]), str(source["message_call"]), int(source["message_index"]), node)
