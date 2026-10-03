extends Node
class_name NativeAreaController
var level: Node3D
var player: Node3D
var gameplay: Node
var entry: Dictionary
var document: Dictionary
var elapsed := 0.0
var tick := 0
var finished := false
var flames: Array[Dictionary] = []
var previous_position := Vector3.ZERO
var has_previous := false
func configure(parent: Node3D, owner_game: Node, source: Dictionary, controller: Dictionary) -> void:
	level = parent; gameplay = owner_game; document = source; entry = controller
	var ancestor: Node = parent
	while ancestor != null and player == null: player = ancestor.get_node_or_null("Player") as Node3D; ancestor = ancestor.get_parent()
func _physics_process(delta: float) -> void:
	if finished or not is_instance_valid(level) or not is_instance_valid(player): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and not finished: elapsed -= 1.0; _native_tick(); tick += 1
func _record() -> Vector3: return Vector3(entry["position"][0], entry["position"][1], entry["position"][2])
func _native_tick() -> void:
	match int(entry["class"]):
		19: _music_trigger()
		30: _flame_vents()
		35: _pull_field(); previous_position = player.global_position; has_previous = true
		25: _ice_floor()
func _music_trigger() -> void:
	var local := level.to_local(player.global_position); var record := _record(); var crossed := false
	match int(entry["variant"]):
		0: crossed = local.x <= record.x
		1: crossed = local.x >= record.x
		2: crossed = local.z >= record.z
		3: crossed = local.z <= record.z
	if not crossed: return
	if int(entry["bytes"][0]) != 2 and gameplay.get("audio") != null: gameplay.audio._request_music(int(entry["bytes"][1]))
	finished = true; queue_free()
func _ice_floor() -> void:
	var slab_area: Variant = document["ice_floor"]["slab_only_area"]
	if int(entry["area"]) == (int(slab_area) if slab_area != null else -1):
		var standing := false
		for block: Node in get_tree().get_nodes_in_group("native_ice_blocks"):
			if block.get("solid") == true and block._standing(): standing = true; break
		if not standing: return
	if int(player.call("worn", "shoes")) != int(document["ice_floor"]["cleated_shoes"]): player.set("ice_slip_ticks", 5)
func _sand_puff() -> void:
	var speed := (player.global_position - previous_position).length() * 256.0 if has_previous else 0.0; var count := 0
	if speed >= 9.0: count = (tick & 1) + 1
	elif speed >= 5.0 and (tick & 1) == 1: count = (randi() & 1) + 1
	if count == 0 or not document.has("sand_puff"): return
	var skeleton := player.find_child("Skeleton3D", true, false) as Skeleton3D; var joint: int = count * 3 + 0xB; var point := player.global_position
	if skeleton != null and joint < skeleton.get_bone_count(): point = skeleton.global_transform * skeleton.get_bone_global_pose(joint).origin
	var puff: Dictionary = document["sand_puff"]; var effect := Node3D.new(); effect.set_script(preload("res://scripts/world/combat/native_effect.gd")); level.add_child(effect); effect.global_position = point
	var variants: Array = puff["variants"]; effect.play(variants[randi() % variants.size()], 1.0, puff["pages"])
func _pull_field() -> void:
	if player.get("holder") != null: return
	var offset := _record() - level.to_local(player.global_position); var distance := offset.length() * 256.0; var radius := float(entry["halfwords"][1])
	if distance >= radius: return
	player.set("soft_ground_ticks", 3)
	_sand_puff()
	var flat := Vector3(offset.x, 0.0, offset.z); var step := flat.normalized() * float(entry["halfwords"][0]) * (radius - distance) / radius / 4096.0
	player.global_position += level.global_basis * (flat if flat.length() <= step.length() else step)
func _flame_vents() -> void:
	var vent: Dictionary = document["flame_vent"]
	if (tick & 0x13) == 0x10:
		for point: Array in vent["points_raw"]: flames.append({"position": Vector3(-float(point[0]), -float(point[1]), float(point[2])) / 256.0, "life": 15, "radius": 0x30, "fade": 0x80, "born": -tick, "node": _flame_node()})
	for flame: Dictionary in flames.duplicate():
		var node: MeshInstance3D = flame["node"]
		flame["position"] += Vector3.UP * 0x100 / 4096.0; flame["radius"] = int(flame["radius"]) + 6
		if int(flame["life"]) > 0:
			flame["life"] = int(flame["life"]) - 1
			var center: Vector3 = level.to_global(flame["position"]); var reach := float(flame["radius"]) / 256.0 + 0.3
			if center.distance_to(player.global_position + Vector3.UP * 0.5) < reach and player.has_method("take_hit"): player.take_hit(8, 0, (player.global_position - center).normalized())
		else:
			flame["fade"] = int(flame["fade"]) - 0x10
			if int(flame["fade"]) <= 0: node.queue_free(); flames.erase(flame); continue
		node.position = flame["position"]; node.scale = Vector3.ONE * float(flame["radius"]) / 128.0; var shade := float(flame["fade"] if int(flame["life"]) <= 0 else 0x80) / 128.0; var flame_material := node.material_override as StandardMaterial3D; flame_material.albedo_color = Color(shade, shade, shade, 1.0); flame_material.uv1_offset = Vector3(float((tick + int(flame.get("born", 0))) % 8) / 8.0, 0.0, 0.0)
func _flame_node() -> MeshInstance3D:
	var mesh := MeshInstance3D.new(); var quad := QuadMesh.new(); quad.size = Vector2.ONE; mesh.mesh = quad; var sprite: Dictionary = document["flame_vent"]["sprite"]
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.albedo_texture = load("res://assets/levels/%s/%s" % [str(document["stage"]), str(sprite["file"])]) as Texture2D; material.uv1_scale = Vector3(1.0 / float(sprite["frames"]), 1.0, 1.0)
	mesh.material_override = material; level.add_child(mesh); return mesh
