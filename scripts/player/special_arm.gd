extends RefCounted
var player: CharacterBody3D
var mesh: MeshInstance3D
var targets: Array = []
var shown := false
var hidden: Array = []
var skeleton: Skeleton3D
func configure(owner: CharacterBody3D, instance: Node, arm: Dictionary) -> void:
	player = owner; var source := instance.find_child(str(arm["node"]), true, false) as MeshInstance3D; var skeletons: Array[Node] = (player.player_model as Node3D).find_children("*", "Skeleton3D", true, false)
	if source == null or skeletons.is_empty(): return
	skeleton = skeletons[0] as Skeleton3D; hidden = arm["replaces"]["boneNames"]
	mesh = MeshInstance3D.new(); mesh.name = str(arm["node"]); mesh.mesh = source.mesh; mesh.skin = source.skin; mesh.transform = source.transform; mesh.visible = false; skeleton.add_child(mesh); mesh.skeleton = mesh.get_path_to(skeleton)
	for surface in range(mesh.mesh.get_surface_count()):
		var material := ShaderMaterial.new(); material.shader = preload("res://shaders/native_model.gdshader"); material.set_shader_parameter("albedo_texture", (mesh.mesh.surface_get_material(surface) as BaseMaterial3D).albedo_texture); mesh.set_surface_override_material(surface, material)
	refresh()
func refresh() -> void:
	if skeleton == null: return
	targets.clear()
	for node in (player.player_model as Node3D).find_children("*", "MeshInstance3D", true, false):
		var target := node as MeshInstance3D
		if target.name == &"MegaManMesh" and target.mesh != null and target.skin != null: targets.append([target, target.mesh, _without_bones(target.mesh, target.skin, skeleton, hidden)])
	var was := shown; shown = false; show(was)
func _without_bones(mesh: Mesh, skin: Skin, skeleton: Skeleton3D, names: Array) -> ArrayMesh:
	var binds := {}; var result := ArrayMesh.new()
	for bind in range(skin.get_bind_count()):
		var bone_name := str(skin.get_bind_name(bind)) if not str(skin.get_bind_name(bind)).is_empty() else skeleton.get_bone_name(skin.get_bind_bone(bind))
		if bone_name in names: binds[bind] = true
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface); var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]; var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]; var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]; var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array(range(vertices.size()))
		var width := bones.size() / maxi(vertices.size(), 1); var removed := PackedByteArray(); removed.resize(vertices.size())
		for vertex in range(vertices.size()):
			for slot in range(width): removed[vertex] = 1 if removed[vertex] == 1 or weights[vertex * width + slot] > 0.0 and binds.has(bones[vertex * width + slot]) else 0
		var kept := PackedInt32Array()
		for corner in range(0, indices.size(), 3):
			if removed[indices[corner]] == 0 and removed[indices[corner + 1]] == 0 and removed[indices[corner + 2]] == 0: kept.append_array([indices[corner], indices[corner + 1], indices[corner + 2]])
		arrays[Mesh.ARRAY_INDEX] = kept; result.add_surface_from_arrays(mesh.surface_get_primitive_type(surface), arrays, [], {}, mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS); result.surface_set_material(surface, mesh.surface_get_material(surface))
	return result
func show(value: bool) -> void:
	if mesh == null or value == shown: return
	shown = value; mesh.visible = value
	for target: Array in targets: (target[0] as MeshInstance3D).mesh = target[2] if value else target[1]
