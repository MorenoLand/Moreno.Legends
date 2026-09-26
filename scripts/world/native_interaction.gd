extends RefCounted
static func attach(node: Node3D, record: Dictionary) -> bool:
	var binding: Variant = record.get("native_interaction", null)
	if not binding is Dictionary or binding.is_empty(): return false
	node.set_meta("native_interaction", binding.duplicate(true)); node.set_meta("native_actor_source", record.duplicate(true)); node.add_to_group("native_interaction_targets")
	return true
static func binding(node: Node3D) -> Dictionary:
	return node.get_meta("native_interaction", {}) if is_instance_valid(node) else {}
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
