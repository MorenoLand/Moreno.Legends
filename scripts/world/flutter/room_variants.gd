extends RefCounted
static func _flag(context: Dictionary, id: int) -> bool:
	var flags: Variant = context.get("event_flags", {})
	return flags is Dictionary and bool(flags.get(id, flags.get(str(id), false)))
static func apply_placements(room: Node3D, entries: Array, context: Dictionary) -> void:
	for entry: Dictionary in entries:
		var base := room.find_child(str(entry["base_node"]), true, false) as MeshInstance3D; var alternate := room.find_child(str(entry["variant_node"]), true, false) as MeshInstance3D
		if base == null or alternate == null: continue
		if entry.has("runtime"): base.set_meta("runtime_variant_mesh", alternate.mesh)
		elif int(entry["variant_when_set"] if _flag(context, int(entry["event_flag"])) else entry["variant_when_clear"]) == int(entry["variant"]): base.mesh = alternate.mesh
		alternate.get_parent().remove_child(alternate); alternate.free()
static func apply_runtime(room: Node3D, node_name: String) -> void:
	var base := room.find_child(node_name, true, false) as MeshInstance3D
	if base == null or not base.has_meta("runtime_variant_mesh"): return
	base.mesh = base.get_meta("runtime_variant_mesh") as Mesh; base.remove_meta("runtime_variant_mesh")
	for body: Node in base.get_children():
		if body is not StaticBody3D: continue
		for item: Node in body.get_children():
			if item is not CollisionShape3D: continue
			var shape := base.mesh.create_trimesh_shape(); (item as CollisionShape3D).shape = shape
			if (body as StaticBody3D).collision_layer == 4: shape.backface_collision = true
static func apply_stage_flags(context: Dictionary, rules: Array) -> void:
	if rules.is_empty(): return
	var flags: Variant = context.get("event_flags", {})
	if not flags is Dictionary: flags = {}
	for rule: Dictionary in rules:
		var active := _flag(context, int(rule["when_event_flag"]))
		for id: Variant in rule["flags"]:
			flags.erase(int(id)); flags.erase(str(int(id)))
			if active: flags[int(id)] = true
	context["event_flags"] = flags
