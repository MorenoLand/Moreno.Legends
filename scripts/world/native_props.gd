extends RefCounted
class_name NativeProps

static var _manifest_cache: Dictionary = {}
static var _npc_source_cache: Dictionary = {}
static func load_into(parent: Node3D, stage: String, area: int, native_context: Dictionary = {}, excluded_roles: Array[String] = [], active: bool = false) -> Array[Node3D]:
	var created: Array[Node3D] = []
	if not is_instance_valid(parent) or not await AssetStore.ensure_stage(stage): return created
	if not is_instance_valid(parent): return created
	var props_manifest := _read_manifest("res://assets/stage_props/manifest.json")
	var source: Dictionary = props_manifest.get("stages", {}).get(stage, {}); var npc_manifest := _read_manifest("res://assets/levels/%s/npcs.json" % stage); var npc_models := _models_by_index(npc_manifest.get("models", []))
	var model_by_index := _models_by_index(source.get("models", [])); var npc_sources := _npc_source_offsets(stage); var base_key := "native_props_base_%s_%d" % [stage, area]
	if not bool(parent.get_meta(base_key, false)):
		for entry: Dictionary in source.get("instances", []):
			var source_offset := int(entry.get("source_file_offset_value", -1)); var source_raw := str(entry.get("source_bytes", ""))
			if int(entry.get("area", -1)) != area or npc_sources.has(_source_key(area, source_offset, source_raw)): continue
			var node := await _load_actor(parent, "res://assets/stage_props/" + str(entry.get("model_file", "")), entry, model_by_index.get(int(entry.get("model_index", -1)), {}), native_context)
			if node != null: _attach_native_source(node, stage, area, entry); created.append(node)
			if not is_instance_valid(parent): return created
		parent.set_meta(base_key, true)
	var static_key := "native_static_actor_props_%s_%d" % [stage, area]
	if not bool(parent.get_meta(static_key, false)):
		for entry: Dictionary in npc_manifest.get("static_actor_instances", []):
			var listed_areas: Variant = entry.get("global_area_indices", null); var entry_areas: Array = listed_areas if listed_areas is Array else [entry.get("area_index", entry.get("area", -1))]
			if area not in entry_areas: continue
			var actor_path := "res://assets/levels/%s/%s" % [stage, str(entry.get("model_file", ""))]; var node := await _load_actor(parent, actor_path, entry, npc_models.get(int(entry.get("model_index", entry.get("source_model_index", -1))), {}), native_context)
			if node != null: _attach_native_source(node, stage, area, entry); node.name = "NativeStaticActor_%s_%d" % [stage, int(entry.get("file_offset", -1))]; created.append(node)
			if not is_instance_valid(parent): return created
		parent.set_meta(static_key, true)
	var scripted := _read_manifest("res://assets/levels/%s/scripted_actors.json" % stage); var script_context := _scene_local_state_context(parent, stage, scripted, native_context, active); var scripted_models := _models_by_index(scripted.get("models", [])); var enabled_sets: Array[String] = []; var enabled_set_ids := {}; var spawn_sets_by_id := {}
	for spawn_set: Dictionary in scripted.get("spawn_sets", []):
		spawn_sets_by_id[str(spawn_set.get("id", ""))] = spawn_set
	while true:
		var found_enabled := false
		for spawn_set_id: String in spawn_sets_by_id:
			if enabled_set_ids.has(spawn_set_id) or not _spawn_set_enabled(spawn_sets_by_id[spawn_set_id], script_context, area, enabled_set_ids): continue
			enabled_set_ids[spawn_set_id] = true; enabled_sets.append(spawn_set_id); found_enabled = true
		if not found_enabled: break
	var registry_key := "native_scripted_actor_registry_%s_%d" % [stage, area]; var registry: Dictionary = parent.get_meta(registry_key, {}); var action_sets := {}; var deferred_pose := false
	for entry: Dictionary in scripted.get("instances", []):
		var spawn_set_id := str(entry.get("spawn_set", "")); var spawn_set: Dictionary = spawn_sets_by_id.get(spawn_set_id, {}); var spawn_source: Dictionary = spawn_set.get("source", {}); var direct: bool = spawn_source.has("controller")
		if not active and (direct or entry.has("native_pose_resolver")): continue
		if active and entry.has("native_pose_resolver") and not script_context.has(str(entry["native_pose_resolver"]["player_pose_key"])):
			deferred_pose = deferred_pose or enabled_sets.has(spawn_set_id)
			continue
		var record_id := int(entry.get("record_id", -1)); var record_key := "controller:" + str(entry["source_record_ram"]) if direct else str(record_id); var source_bytes := str(entry.get("source_bytes_hex", entry.get("source_bytes", ""))); var prior: Variant = registry.get(record_key, null)
		var role := str(entry.get("role", ""))
		if excluded_roles.has(role):
			if is_instance_valid(prior) and str(prior.get_meta("native_role", "")) == role: prior.queue_free(); registry.erase(record_key)
			continue
		if not enabled_sets.has(str(entry.get("spawn_set", ""))): continue
		if is_instance_valid(prior) and str(prior.get_meta("native_source_bytes", "")) == source_bytes:
			if active: _attach_spawn_actions(prior, spawn_set_id, spawn_source, action_sets)
			continue
		if is_instance_valid(prior): prior.queue_free()
		var node := await _load_actor(parent, "res://assets/levels/%s/%s" % [stage, str(entry.get("model_file", ""))], entry, scripted_models.get(int(entry.get("model_index", -1)), {}), script_context)
		if node != null:
			_attach_native_source(node, stage, area, entry); node.set_meta("native_record_id", record_id); node.set_meta("native_source_bytes", source_bytes); node.set_meta("native_identity", str(entry.get("identity", ""))); node.set_meta("native_role", role); created.append(node); registry[record_key] = node
			if active: _attach_spawn_actions(node, spawn_set_id, spawn_source, action_sets)
		if not is_instance_valid(parent): return created
	parent.set_meta(registry_key, registry)
	if active: parent.set_meta("native_deferred_pose", deferred_pose)
	return created
static func _attach_spawn_actions(node: Node3D, id: String, source: Dictionary, owners: Dictionary) -> void:
	var actions: Array = source.get("native_side_effects", []).duplicate(true); actions.append_array(source.get("native_local_state_mutations", []))
	if actions.is_empty() or owners.has(id): return
	if str(node.get_meta("native_spawn_set", "")) != id: node.remove_meta("native_action_status")
	node.set_meta("native_spawn_set", id); node.set_meta("native_actions", actions); owners[id] = true
static func initialize_into(parent: Node3D, stage: String, area: int, native_context: Dictionary = {}, excluded_roles: Array[String] = []) -> Array[Node3D]:
	var created: Array[Node3D] = []; var tree := Engine.get_main_loop() as SceneTree; var flags_changed := false; var state_changed := false
	while true:
		var loaded: Array[Node3D] = await load_into(parent, stage, area, native_context, excluded_roles, true); created.append_array(loaded)
		if not is_instance_valid(parent): return created
		if bool(parent.get_meta("native_deferred_pose", false)):
			parent.set_meta("native_initialization_result", {"flags_changed": flags_changed, "state_changed": state_changed, "deferred_native_pose": true, "pending_scene_requests": pending_scene_requests(parent)})
			return created
		var result := process_spawn_actions(parent, stage, area, native_context, _native_action_nodes(parent, stage, area))
		flags_changed = flags_changed or bool(result.get("flags_changed", false)); state_changed = state_changed or bool(result.get("state_changed", false))
		if not bool(result.get("flags_changed", false)) and not bool(result.get("state_changed", false)): break
		await tree.physics_frame
	if is_instance_valid(parent): parent.set_meta("native_initialization_result", {"flags_changed": flags_changed, "state_changed": state_changed, "pending_scene_requests": pending_scene_requests(parent)})
	return created
static func initialization_result(parent: Node3D) -> Dictionary: return parent.get_meta("native_initialization_result", {}) if is_instance_valid(parent) else {}
static func pending_scene_requests(parent: Node3D) -> Array: return parent.get_meta("native_pending_scene_requests", []) if is_instance_valid(parent) else []
static func _native_action_nodes(parent: Node3D, stage: String, area: int) -> Array[Node3D]:
	var result: Array[Node3D] = []
	for node: Node3D in parent.find_children("*", "Node3D", true, false):
		if node.has_meta("native_actions") and str(node.get_meta("native_stage", "")) == stage and int(node.get_meta("native_area", -1)) == area: result.append(node)
	return result
static func process_spawn_actions(parent: Node3D, stage: String, area: int, native_context: Dictionary, spawned: Array[Node3D]) -> Dictionary:
	var flags_changed := false; var state_changed := false; var pending: Array = parent.get_meta("native_pending_scene_requests", [])
	for node: Node3D in spawned:
		if not is_instance_valid(node) or not node.has_meta("native_actions"): continue
		var spawn_set_id := str(node.get_meta("native_spawn_set", "")); var actions: Array = node.get_meta("native_actions", []); var status: Dictionary = node.get_meta("native_action_status", {})
		for index in range(actions.size()):
			var action_key := str(index); var action_state := str(status.get(action_key, "")); var action: Dictionary = actions[index]
			if action_state == "done" or action_state == "pending": continue
			match str(action.get("kind", "")):
				"set_event_flag":
					var flags: Variant = native_context.get("event_flags", {}); if not (flags is Dictionary): flags = {}
					var id := int(action.get("id", -1)); var current := bool(flags.get(id, flags.get(str(id), false))); var guard := int(action.get("when_event_flag_clear", -1)); var guard_set := bool(flags.get(guard, flags.get(str(guard), false))) if guard >= 0 else false
					if guard_set: status[action_key] = "done"
					else:
						if id >= 0 and not current: flags[id] = true; flags_changed = true
						native_context["event_flags"] = flags; status[action_key] = "done"
				"increment_stage_script_state_byte":
					var changed := _apply_local_state_mutation(parent, stage, native_context, action); state_changed = state_changed or changed; status[action_key] = "done"
				"call":
					var request_key := "%s:%d:%s:%d" % [stage, area, spawn_set_id, index]; var exists := false
					for request: Dictionary in pending:
						if str(request.get("key", "")) == request_key: exists = true; break
					if not exists: pending.append({"key": request_key, "stage": stage, "area": area, "spawn_set": spawn_set_id, "source_function": str(action.get("function", "")), "argument": int(action.get("argument", -1)), "status": "pending_native_scene"})
					status[action_key] = "pending"
				_:
					status[action_key] = "pending"
		node.set_meta("native_action_status", status)
	parent.set_meta("native_pending_scene_requests", pending)
	return {"flags_changed": flags_changed, "state_changed": state_changed, "pending_scene_requests": pending.duplicate(true)}
static func _scene_local_state_context(parent: Node3D, stage: String, manifest: Dictionary, native_context: Dictionary, active: bool) -> Dictionary:
	var reset: Dictionary = manifest.get("source", {}).get("local_context_reset", {}); var state_map: Dictionary = {}; var owner_key := "native_script_state_owner"; var owner_id := "%s:%s" % [stage, str(reset.get("owner_ram", ""))]
	if not reset.is_empty():
		var owner: Variant = parent.get_meta(owner_key, {})
		if not (owner is Dictionary) or str(owner.get("owner_id", "")) != owner_id:
			var local_states: Dictionary = {}; var local_bytes: Dictionary = {}; var initialized_offsets: Array = reset.get("initialized_offsets", []); var initial_value := int(reset.get("initial_value", 0)); var owner_ram := str(reset.get("owner_ram", ""))
			for offset in initialized_offsets: local_bytes[str(int(offset))] = initial_value
			local_states[owner_ram] = local_bytes
			owner = {"owner_id": owner_id, "stage": stage, "source": reset, "states": local_states}
			if active: parent.set_meta(owner_key, owner)
		var owner_states: Variant = owner.get("states", {}); state_map = owner_states.duplicate(true) if owner_states is Dictionary else {}
	var provided: Variant = native_context.get("stage_script_state_bytes", null)
	if provided is Dictionary:
		for key in provided:
			var value: Variant = provided[key]
			if value is Dictionary:
				var fields: Dictionary = state_map.get(str(key), {}); fields.merge(value, true); state_map[str(key)] = fields
			else: state_map[str(key)] = value
	var resolved := native_context.duplicate(true); resolved["stage_script_state_bytes"] = state_map; return resolved
static func _script_state_byte(context: Dictionary, function_key: String, slot: int, owner_key: String, offset: int, fallback: int) -> int:
	var state_map: Variant = context.get("stage_script_state_bytes", {}); if not state_map is Dictionary: return fallback
	for key in [function_key + ":" + str(slot), function_key, owner_key]:
		var fields: Variant = state_map.get(key, null)
		if fields is Dictionary:
			if fields.has(offset): return int(fields[offset])
			if fields.has(str(offset)): return int(fields[str(offset)])
	return fallback
static func _apply_local_state_mutation(parent: Node3D, stage: String, context: Dictionary, mutation: Dictionary) -> bool:
	var reset: Dictionary = _read_manifest("res://assets/levels/%s/scripted_actors.json" % stage).get("source", {}).get("local_context_reset", {}); var owner: Variant = parent.get_meta("native_script_state_owner", {}); var owner_key := str(mutation.get("owner_ram", reset.get("owner_ram", ""))); var owner_id := "%s:%s" % [stage, owner_key]
	if reset.is_empty() or not (owner is Dictionary) or str(owner.get("owner_id", "")) != owner_id: return false
	var function_key := str(mutation.get("source_function", "")); var slot := int(mutation.get("script_slot", 0)); var offset := int(mutation.get("offset", 0)); var offset_key := str(offset); var states: Dictionary = owner.get("states", {}); var local_fields: Dictionary = states.get(owner_key, {}); var current := _script_state_byte(context, function_key, slot, owner_key, offset, int(local_fields.get(offset_key, 0)))
	var previous := int(local_fields.get(offset_key, current)); var value := current + int(mutation.get("amount", 1)); local_fields[offset_key] = value; states[owner_key] = local_fields; owner["states"] = states; parent.set_meta("native_script_state_owner", owner); return previous != value
static func _spawn_set_enabled(spawn_set: Dictionary, native_context: Dictionary, area: int, enabled_sets: Dictionary = {}) -> bool:
	var parent_set := str(spawn_set.get("parent_spawn_set", "")); if not parent_set.is_empty() and not enabled_sets.has(parent_set): return false
	var predicate: Dictionary = spawn_set.get("predicate", {}); var conditions: Array = predicate.get("all", [])
	for condition: Dictionary in conditions:
		match str(condition.get("kind", "")):
			"stage_state_byte_equals":
				if not native_context.has("native_save_byte14") or int(native_context["native_save_byte14"]) != int(condition.get("value", -1)): return false
			"stage_area_byte_equals":
				if area != int(condition.get("value", -1)): return false
			"stage_script_state_byte_equals":
				var function_key := str(condition.get("source_function", "")); var owner_key := str(condition.get("owner_ram", "")); var state_byte := _script_state_byte(native_context, function_key, int(condition.get("script_slot", 0)), owner_key, int(condition.get("offset", 0)), -1)
				if state_byte != int(condition.get("value", -1)): return false
			"native_event_flag":
				var flags: Variant = native_context.get("event_flags", null); var id := int(condition.get("id", -1))
				if not (flags is Dictionary): return false
				var is_set := false
				if flags.has(id): is_set = bool(flags[id])
				elif flags.has(str(id)): is_set = bool(flags[str(id)])
				if is_set != bool(condition.get("set", false)): return false
			_:
				return false
	return not conditions.is_empty() or not parent_set.is_empty()
static func _read_manifest(path: String) -> Dictionary:
	if _manifest_cache.has(path): return _manifest_cache[path]
	if not FileAccess.file_exists(path): return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)); var data: Dictionary = parsed if parsed is Dictionary else {}; _manifest_cache[path] = data; return data
static func _models_by_index(models: Array) -> Dictionary:
	var result := {}
	for model: Dictionary in models: result[int(model.get("model_index", model.get("source_model_index", model.get("index", -1))))] = model
	return result
static func _attach_native_source(node: Node3D, stage: String, area: int, entry: Dictionary) -> void:
	node.set_meta("native_stage", stage); node.set_meta("native_area", area); preload("res://scripts/world/native_interaction.gd").attach(node, entry)
static func _npc_source_offsets(stage: String) -> Dictionary:
	if _npc_source_cache.has(stage): return _npc_source_cache[stage]
	var result := {}; var data := _read_manifest("res://assets/levels/%s/npcs.json" % stage)
	for category in ["npc_instances", "instances", "scripted_actor_instances", "static_actor_instances"]:
		for entry: Dictionary in data.get(category, []):
			var listed_areas: Variant = entry.get("global_area_indices", null); var areas: Array = listed_areas if listed_areas is Array else [entry.get("area_index", entry.get("area", -1))]; var offset := int(entry.get("file_offset", entry.get("source_file_offset_value", -1))); var raw := str(entry.get("source_bytes_hex", entry.get("source_bytes", "")))
			if offset < 0 or raw.is_empty(): continue
			for area_value in areas:
				var area := int(area_value)
				if area >= 0: result[_source_key(area, offset, raw)] = true
	_npc_source_cache[stage] = result; return result
static func _source_key(area: int, offset: int, raw: String) -> String: return "%d:%d:%s" % [area, offset, raw]
static func _load_actor(parent: Node3D, path: String, entry: Dictionary, model: Dictionary, native_context: Dictionary = {}) -> Node3D:
	if not is_instance_valid(parent) or path.ends_with("/") or not path.ends_with(".glb"): return null
	var transform: Dictionary = entry.get("transform", {})
	if entry.has("native_pose_resolver"):
		transform = preload("res://scripts/world/native_interaction.gd").resolve_pose(entry, native_context)
		if transform.is_empty(): return null
	var packed := await _threaded_scene(path)
	if packed == null or not is_instance_valid(parent): return null
	var node := packed.instantiate() as Node3D
	if node == null: return null
	parent.add_child(node)
	var position: Array = transform.get("position", entry.get("position", [0.0, 0.0, 0.0])); node.position = Vector3(float(position[0]), float(position[1]), float(position[2])); node.rotation.y = float(transform.get("yaw_turns", entry.get("yaw_turns", 0.0))) * TAU
	var scale: Array = model.get("native_scale_raw", [512, 512, 512]); node.scale = Vector3(float(scale[0]), float(scale[1]), float(scale[2])) / 512.0
	var hitbox: Dictionary = entry.get("native_hitbox", {}); preload("res://scripts/world/native_actor_motion.gd").attach_collision(node, hitbox.get("bounds_raw", []))
	var animation := node.find_child("AnimationPlayer", true, false) as AnimationPlayer
	if animation != null:
		var startup: Dictionary = entry.get("native_animation_startup", model.get("native_animation_startup", {})); var control := int(startup.get("control", entry.get("control", 0))); var frame := int(startup.get("start_record", entry.get("frame", 0)))
		var animation_clock := preload("res://scripts/world/native_animation.gd").new(); animation_clock.name = "NativeAnimationClock"; node.add_child(animation_clock)
		if animation_clock.configure(animation, model.get("animations", [])): animation_clock.play_control(control, frame)
	var movement_profile: Dictionary = entry.get("native_movement", {})
	if not movement_profile.is_empty():
		var behavior := preload("res://scripts/world/native_npc_behavior.gd").new(); behavior.name = "NativeNpcBehavior"; node.add_child(behavior); behavior.configure(node, movement_profile, native_context)
	var interaction: Dictionary = entry.get("native_interaction", {})
	if str(entry.get("stage", "")) == "ST08" and int(entry.get("actor_class", -1)) == 0 and int(entry.get("model_index", -1)) == 2 and str(entry.get("source_record_ram", "")) == "0x800f5284" and int(interaction.get("actor_state", -1)) == 1 and str(interaction.get("actor_callback", "")).to_lower() == "0x800e93ec":
		var follower := preload("res://scripts/world/native_follower.gd").new(); follower.name = "NativeFollower"; node.add_child(follower)
		if not follower.configure(node, entry, native_context): follower.queue_free()
	preload("res://scripts/world/native_material.gd").apply(node, 128.0)
	if entry.has("native_broadphase"):
		var meshes: Array[MeshInstance3D] = []
		if node is MeshInstance3D: meshes.append(node as MeshInstance3D)
		else:
			for child: Node in node.find_children("*", "MeshInstance3D", true, false):
				if child is MeshInstance3D: meshes.append(child as MeshInstance3D)
		for mesh_node: MeshInstance3D in meshes:
			if mesh_node.mesh == null: continue
			var mesh_shape: Shape3D = mesh_node.mesh.create_trimesh_shape()
			if mesh_shape == null: continue
			if mesh_shape is ConcavePolygonShape3D: (mesh_shape as ConcavePolygonShape3D).backface_collision = true
			var body := StaticBody3D.new(); body.name = "NativeMeshCollision"; body.collision_layer = 1; body.collision_mask = 0; var shape := CollisionShape3D.new(); shape.shape = mesh_shape; body.add_child(shape); mesh_node.add_child(body)
	return node
static func _threaded_scene(path: String) -> PackedScene:
	var status := ResourceLoader.load_threaded_get_status(path)
	if status == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
		var request_error := ResourceLoader.load_threaded_request(path, "PackedScene", true, ResourceLoader.CACHE_MODE_REUSE)
		if request_error != OK and request_error != ERR_BUSY: return null
		status = ResourceLoader.load_threaded_get_status(path)
	var tree := Engine.get_main_loop() as SceneTree
	while status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		await tree.process_frame
		status = ResourceLoader.load_threaded_get_status(path)
	return ResourceLoader.load_threaded_get(path) as PackedScene if status == ResourceLoader.THREAD_LOAD_LOADED else null
