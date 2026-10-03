extends AnimatableBody3D
class_name NativeIceBlock
const NativeMaterial := preload("res://scripts/world/rendering/native_material.gd")
const BIT_SOLID := 2
var prop: Node3D
var gameplay: Node
var player: Node3D
var profile: Dictionary = {}
var model_files: Dictionary = {}
var model_scales: Dictionary = {}
var variant := 0
var stage := ""
var phase := 0
var sub_phase := 0
var timer := 0
var hit_pending := false
var solid := true
var elapsed := 0.0
var key := 0
var blend := 0
var visuals: Dictionary = {}
var shape: CollisionShape3D
var minimum := Vector3.ZERO
var maximum := Vector3.ZERO
var debris: Array[Dictionary] = []
func configure(owner_game: Node, target: Node3D, stage_name: String, stage_profile: Dictionary, models: Array, entry: Dictionary) -> bool:
	gameplay = owner_game; prop = target; stage = stage_name; profile = stage_profile; variant = int(entry["native_ice_block"]["variant"]); key = int(entry["native_ice_block"]["key"])
	for model: Dictionary in models:
		for model_key in profile.get("models", {}):
			if int(profile["models"][model_key]) == int(model.get("model_index", -1)): model_files[int(model_key)] = "res://assets/stage_props/" + str(model.get("model_file", "")); model_scales[int(model_key)] = model.get("native_scale_raw", [512, 512, 512])
	var bounds: Array = profile["bounds_raw"]["slab"]
	minimum = Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0; maximum = Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
	shape = CollisionShape3D.new(); var box := BoxShape3D.new(); box.size = maximum - minimum; shape.shape = box; shape.position = (minimum + maximum) * 0.5; add_child(shape)
	top_level = true; collision_layer = 9; collision_mask = 0; sync_to_physics = false; global_position = prop.global_position; rotation.y = prop.global_rotation.y; add_to_group("native_ice_blocks")
	visuals[key] = _own_meshes()
	var ancestor: Node = prop
	while ancestor != null and player == null: player = ancestor.get_node_or_null("Player") as Node3D; ancestor = ancestor.get_parent()
	if variant != 0 and variant != 3: _translucent(1)
	if variant == 3: phase = 2; solid = false
	_apply()
	set_physics_process(true)
	return true
func _translucent(mode: int) -> void:
	blend = mode
	for visual_key: int in visuals:
		for item: Node in visuals[visual_key]: NativeMaterial.translucent(item as Node3D, mode)
func _own_meshes() -> Array[Node]:
	var result: Array[Node] = []
	if prop is MeshInstance3D: result.append(prop)
	for child: Node in prop.find_children("*", "MeshInstance3D", true, false):
		if not is_ancestor_of(child) and child != self: result.append(child)
	return result
func _physics_process(delta: float) -> void:
	if not is_instance_valid(prop): queue_free(); return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func receive_hit(damage: int, flags: int, _direction: Vector3 = Vector3.ZERO) -> bool:
	if (damage & 0xFFF) == 0 or (flags & 0x440000) == 0: return false
	hit_pending = true; return true
func _native_tick() -> void:
	_tick_debris()
	var hit := hit_pending; hit_pending = false
	match phase:
		0: solid = true; timer = 0x64; phase = 1
		1: _armed(hit)
		2: _hidden()
		3: _fade()
	_apply()
func _armed(hit: bool) -> void:
	if hit:
		if variant == 2: _shatter_large(); prop.queue_free(); return
		_break(); return
	match variant:
		0: _stand_timer()
		3: _trigger()
func _stand_timer() -> void:
	if _standing():
		var counter := (timer - 2) & 0xFFFF; timer = counter; counter &= 0xFFFE
		if counter == 0x32: _sound(int(profile["sounds"]["crack"])); _set_model(int(profile["crack_key"]))
		elif counter == 0: _break()
	else:
		var counter := timer; timer = (timer + 1) & 0xFFFF
		if counter >= 0x64: timer = 0x64
		elif counter == 0x32: _set_model(int(profile["intact_key"]))
func _trigger() -> void:
	if sub_phase == 0: timer = 0x10; sub_phase = 1; _sound(int(profile["sounds"]["trigger"])); _translucent(1); return
	timer = (timer - 1) & 0xFFFF
	if timer == 0: phase = 2; sub_phase = 0; solid = false
func _break() -> void:
	solid = false; phase = 2; sub_phase = 0; timer = int(profile["respawn_ticks"][variant])
	if variant == 0: _shatter_pieces()
	else: _shatter_shards(false)
func _hidden() -> void:
	timer = (timer - 1) & 0xFFFF
	if timer != 0: return
	_sound(int(profile["sounds"]["reappear"])); _set_model(0 if stage == "ST58" else int(profile["variant_keys"][variant])); timer = 2; solid = true; phase = 3; _translucent(1)
func _fade() -> void:
	timer += 1
	if timer == 0x10:
		phase = 0; sub_phase = 0
		if variant == 0 or variant == 3: _translucent(0)
func _standing() -> bool:
	if not is_instance_valid(player) or not player.has_method("is_on_floor") or not player.is_on_floor(): return false
	var local := to_local(player.global_position)
	return local.x >= minimum.x and local.x <= maximum.x and local.z >= minimum.z and local.z <= maximum.z and local.y >= maximum.y - 0.05 and local.y <= maximum.y + 0.2
func _apply() -> void:
	shape.disabled = not solid
	for visual_key: int in visuals:
		for item: Node in visuals[visual_key]: (item as Node3D).visible = solid and visual_key == key
func _set_model(next_key: int) -> void:
	if next_key == key: return
	if not visuals.has(next_key) and model_files.has(next_key):
		var scene := load(model_files[next_key]) as PackedScene
		if scene != null:
			var instance := scene.instantiate() as Node3D; prop.get_parent().add_child(instance); instance.transform = prop.transform; prop.tree_exiting.connect(instance.queue_free); visuals[next_key] = [instance]; NativeMaterial.apply(instance, 128.0)
			if blend > 0: NativeMaterial.translucent(instance, blend)
	if visuals.has(next_key): key = next_key
func _sound(sound_id: int) -> void:
	if gameplay != null and gameplay.get("audio") != null: gameplay.audio.play_at(sound_id, global_position)
func _floor_height() -> float:
	var query := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 0.5, global_position - Vector3.UP * 32.0, 1, [get_rid()]); var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return float((hit["position"] as Vector3).y) if not hit.is_empty() else global_position.y - 32.0
func _spawn(piece_key: int, point: Vector3, kind: int, velocity_raw: Vector3, floor_y: float) -> void:
	if not model_files.has(piece_key): return
	var scene := load(model_files[piece_key]) as PackedScene
	if scene == null: return
	var piece := scene.instantiate() as Node3D; prop.get_parent().add_child(piece); var scale_raw: Array = model_scales.get(piece_key, [512, 512, 512]); piece.scale = Vector3(float(scale_raw[0]), float(scale_raw[1]), float(scale_raw[2])) / 512.0
	piece.global_position = point; piece.rotation = Vector3(randf_range(-0.2, 0.2), prop.rotation.y + randf_range(-0.2, 0.2), randf_range(-0.2, 0.2)); NativeMaterial.apply(piece, 128.0)
	debris.append({"node": piece, "kind": kind, "velocity": velocity_raw, "floor": floor_y, "phase": 0, "timer": 0})
func _shatter_pieces() -> void:
	_sound(int(profile["sounds"]["break_cracked"])); var floor_y := _floor_height(); var offsets: Array = profile["piece_offsets"]
	for index in 3:
		var offset := Basis(Vector3.UP, rotation.y) * Vector3(-float(offsets[index * 2]), 0.0, float(offsets[index * 2 + 1])) / 4096.0
		_spawn(int(profile["piece_keys"][2 + index]), global_position + offset - Vector3.UP * 0.117, 1, Vector3.ZERO, floor_y)
func _shatter_shards(large: bool) -> void:
	_sound(int(profile["sounds"]["break_large" if large else "break_ice"])); var floor_y := _floor_height() if not large else global_position.y
	if large:
		for column in 4:
			for row in 4:
				var offset := Basis(Vector3.UP, rotation.y) * Vector3(-float((-0xe0 + 0x40 * column) * 16), float(-0x400 - 0x800 * row), 0.0) / 4096.0
				_spawn(int(profile["piece_keys"][5]), global_position + Vector3(offset.x, -offset.y, offset.z), 2, Vector3(float((randi() & 7) - 4) * 16.0, -float((randi() & 7) - 4) * 16.0, float((randi() & 7) - 4) * 16.0), floor_y)
		return
	for index in 16:
		var angle := float(randi() & 0xFFF) * TAU / 4096.0; var radius := float((randi() & 0xFF) + 0x10) * 16.0 / 4096.0
		_spawn(int(profile["piece_keys"][5]), global_position + Vector3(sin(angle), 0.0, cos(angle)) * radius, 3, Vector3(float((randi() & 7) - 4) * 16.0, 0.0, float((randi() & 7) - 4) * 16.0), floor_y)
func _shatter_large() -> void: _shatter_shards(true)
func _tick_debris() -> void:
	for piece: Dictionary in debris.duplicate():
		var node: Node3D = piece["node"]
		if not is_instance_valid(node): debris.erase(piece); continue
		var velocity: Vector3 = piece["velocity"]; var kind: int = piece["kind"]
		if kind == 3 or int(piece["phase"]) > 0 or (kind == 2 and node.global_position.y <= float(piece["floor"]) + 0.125):
			if int(piece["phase"]) == 0: piece["phase"] = 1; piece["timer"] = 12; velocity.y = -velocity.y * 0.5
			velocity.y += 0x30; node.visible = not node.visible; piece["timer"] = int(piece["timer"]) - 1
			if int(piece["timer"]) == 0: node.queue_free(); debris.erase(piece); continue
		else:
			velocity.y += 0x30
			if node.global_position.y <= float(piece["floor"]) + 0.125:
				if kind == 1: node.queue_free(); debris.erase(piece); continue
		piece["velocity"] = velocity
		node.global_position += Basis(Vector3.UP, prop.rotation.y) * Vector3(-velocity.x, -velocity.y, velocity.z) / 4096.0
