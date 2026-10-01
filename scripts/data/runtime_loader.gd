extends ResourceFormatLoader
const EXTENSIONS := ["glb", "png"]
func _get_recognized_extensions() -> PackedStringArray: return PackedStringArray(EXTENSIONS)
func _handles_type(type: StringName) -> bool: return type in [&"PackedScene", &"Texture2D", &"Texture", &"ImageTexture"]
func _recognize_path(path: String, type: StringName) -> bool: return path.get_extension().to_lower() in EXTENSIONS and (type == &"" or _handles_type(type) and (type == &"PackedScene") == (path.get_extension().to_lower() == "glb")) and not FileAccess.file_exists(path + ".import") and FileAccess.file_exists(path)
func _get_resource_type(path: String) -> String: return "PackedScene" if path.get_extension().to_lower() == "glb" and _recognize_path(path, &"") else ("ImageTexture" if _recognize_path(path, &"") else "")
func _exists(path: String) -> bool: return FileAccess.file_exists(path)
func _load(path: String, _original_path: String, _use_sub_threads: bool, _cache_mode: int) -> Variant:
	if path.get_extension().to_lower() == "png":
		var image := Image.new()
		if image.load_png_from_buffer(FileAccess.get_file_as_bytes(path)) != OK: return ERR_FILE_CORRUPT
		image.fix_alpha_edges(); return ImageTexture.create_from_image(image)
	var state := GLTFState.new(); state.handle_binary_image = GLTFState.HANDLE_BINARY_EMBED_AS_UNCOMPRESSED
	var document := GLTFDocument.new()
	if document.append_from_file(path, state) != OK: return ERR_FILE_CORRUPT
	var root := document.generate_scene(state, 30.0, false, false)
	if root == null: return ERR_FILE_CORRUPT
	_own(root, root, path)
	for player: AnimationPlayer in root.find_children("*", "AnimationPlayer", true, false): _normalize(player, root)
	var packed := PackedScene.new(); var error := packed.pack(root); root.free()
	return packed if error == OK else error
func _own(node: Node, root: Node, path: String) -> void:
	var mesh := (node as MeshInstance3D).mesh if node is MeshInstance3D else null
	if mesh != null and mesh.resource_path.is_empty(): mesh.resource_path = path + "::" + str(mesh.get_instance_id())
	for child in node.get_children(): child.owner = root; _own(child, root, path)
func _rest(root: Node, path: NodePath, type: int) -> Variant:
	var node := root.get_node_or_null(NodePath(path.get_concatenated_names()))
	if node == null: return null
	var transform: Transform3D
	if path.get_subname_count() > 0 and node is Skeleton3D:
		var bone := (node as Skeleton3D).find_bone(path.get_concatenated_subnames())
		if bone < 0: return null
		transform = (node as Skeleton3D).get_bone_rest(bone)
	elif node is Node3D: transform = (node as Node3D).transform
	else: return null
	return transform.origin if type == Animation.TYPE_POSITION_3D else (transform.basis.get_rotation_quaternion() if type == Animation.TYPE_ROTATION_3D else transform.basis.get_scale())
func _same(a: Variant, b: Variant) -> bool: return a.is_equal_approx(b)
func _normalize(player: AnimationPlayer, root: Node) -> void:
	var base := player.get_node(player.root_node); var used := {}; var rests := {}; var names := player.get_animation_list()
	for name in names:
		var animation := player.get_animation(name)
		for track in animation.get_track_count():
			var type := animation.track_get_type(track)
			if type < Animation.TYPE_POSITION_3D or type > Animation.TYPE_SCALE_3D: continue
			var key := str(animation.track_get_path(track)) + "|" + str(type); var rest: Variant = _rest(base, animation.track_get_path(track), type)
			if rest == null: continue
			rests[key] = rest
			if used.has(key): continue
			for index in animation.track_get_key_count(track):
				if not _same(animation.track_get_key_value(track, index), rest): used[key] = true; break
	for name in names:
		var animation := player.get_animation(name); var present := {}
		for track in range(animation.get_track_count() - 1, -1, -1):
			var type := animation.track_get_type(track)
			if type < Animation.TYPE_POSITION_3D or type > Animation.TYPE_SCALE_3D: continue
			var key := str(animation.track_get_path(track)) + "|" + str(type)
			if used.has(key): present[key] = true
			elif rests.has(key): animation.remove_track(track)
		for key: String in used:
			if present.has(key): continue
			var parts := key.rsplit("|", true, 1); var type := int(parts[1]); var track := animation.add_track(type); animation.track_set_path(track, NodePath(parts[0]))
			if type == Animation.TYPE_POSITION_3D: animation.position_track_insert_key(track, 0.0, rests[key])
			elif type == Animation.TYPE_ROTATION_3D: animation.rotation_track_insert_key(track, 0.0, rests[key])
			else: animation.scale_track_insert_key(track, 0.0, rests[key])
		animation.optimize()
