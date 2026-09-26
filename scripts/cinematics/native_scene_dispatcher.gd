extends Node
const Runtime := preload("res://scripts/cinematics/native_scene.gd")
var host: Node3D
var active := false
var transition_requested := false
var last_error := ""
func configure(gameplay: Node3D) -> void: host = gameplay
func run_pending(parent: Node3D, stage: String, area: int) -> bool:
	last_error = ""; transition_requested = false
	var pending: Array = preload("res://scripts/world/native_props.gd").pending_scene_requests(parent)
	for request: Dictionary in pending:
		if str(request.get("status", "")) in ["complete_native_scene", "running_native_scene"]: continue
		var function := str(request.get("source_function", "")).to_lower(); var id := int(request.get("argument", -1)); var path := "res://assets/levels/%s/scene_%02x.json" % [stage, id]
		if not function.ends_with("800c0b0c") or id < 0 or not FileAccess.file_exists(path):
			request["status"] = "unbound_native_scene"; last_error = "Unsupported native scene %s:%02X requested by %s" % [stage, id, str(request.get("source_function", ""))]; parent.set_meta("native_pending_scene_requests", pending); return false
		var runtime: Node = Runtime.new(); add_child(runtime)
		if not runtime.configure(host, parent, path, area): request["status"] = "unbound_native_scene"; last_error = "Incomplete native scene assets: %s:%02X" % [stage, id]; runtime.queue_free(); return false
		request["status"] = "running_native_scene"; active = true; parent.set_meta("native_pending_scene_requests", pending)
		var success: bool = await runtime.run(); var transition: Dictionary = runtime.transition_route.duplicate(true); runtime.queue_free(); active = false
		if not is_instance_valid(parent): return false
		request["status"] = "complete_native_scene" if success else "failed_native_scene"; parent.set_meta("native_pending_scene_requests", pending)
		if not success: last_error = "Native scene execution failed: %s:%02X" % [stage, id]; return false
		if not transition.is_empty(): transition_requested = true; host.stage_transition_requested.emit(transition); return true
		if str(request.get("spawn_set", "")).is_empty(): continue
		for node: Node3D in parent.find_children("*", "Node3D", true, false):
			if str(node.get_meta("native_spawn_set", "")) != str(request.get("spawn_set", "")): continue
			var status: Dictionary = node.get_meta("native_action_status", {}); var action_key := str(request["key"]).get_slice(":", str(request["key"]).get_slice_count(":") - 1); status[action_key] = "done"; node.set_meta("native_action_status", status)
	return true
