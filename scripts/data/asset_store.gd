extends Node
signal progress(group: String, received: int, total: int)
var last_error := ""
var manifest: Dictionary = {}
var loaded: Dictionary = {}
var busy := false
var current_group := ""
var request: HTTPRequest
var base_url := ""
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	request = HTTPRequest.new(); request.timeout = 0.0; add_child(request)
	if OS.has_feature("web"): base_url = str(JavaScriptBridge.eval("new URL('.', window.location.href).href"))
func _process(_delta: float) -> void:
	if busy and request != null: progress.emit(current_group, request.get_downloaded_bytes(), request.get_body_size())
func ensure_stage(stage: String) -> bool:
	if not await ensure_menu(): return false
	if not await ensure_group("shared"): return false
	if not await ensure_group("audio-ST0F"): return false
	if stage != "ST0F" and not await ensure_group("audio-" + stage): return false
	var audio_path := "res://assets/audio/" + stage + "/manifest.json"
	if FileAccess.file_exists(audio_path):
		var audio: Variant = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		if audio is Dictionary:
			for owner: String in audio.get("audio_dependencies", []):
				if not await ensure_group("audio-" + owner): return false
	return await ensure_group("stage-" + stage)
func ensure_menu() -> bool:
	return await ensure_group("menu-audio")
func ensure_opening() -> bool:
	if not await ensure_group("shared"): return false
	return await ensure_group("opening")
func ensure_group(group: String) -> bool:
	if not OS.has_feature("web") and not FileAccess.file_exists("res://packs/manifest.json"): return true
	while busy: await get_tree().process_frame
	if loaded.has(group): return true
	busy = true; current_group = group; last_error = ""
	var success := await _ensure_group(group)
	if success: loaded[group] = true
	busy = false
	return success
func _ensure_group(group: String) -> bool:
	if manifest.is_empty():
		var value: Variant
		if FileAccess.file_exists("res://packs/manifest.json"): value = JSON.parse_string(FileAccess.get_file_as_string("res://packs/manifest.json"))
		else:
			if request.request(base_url + "packs/manifest.json") != OK: return _fail("Cannot request content manifest")
			var response: Array = await request.request_completed
			if int(response[0]) != HTTPRequest.RESULT_SUCCESS or int(response[1]) != 200: return _fail("Cannot download content manifest")
			value = JSON.parse_string((response[3] as PackedByteArray).get_string_from_utf8())
		if not value is Dictionary or not value.get("groups") is Dictionary: return _fail("Invalid content manifest")
		manifest = value
	if not manifest.groups.has(group): return _fail("Missing content group: " + group)
	var entry: Dictionary = manifest.groups[group]
	var cache := "user://asset_cache"
	if DirAccess.make_dir_recursive_absolute(cache) != OK: return _fail("Cannot create content cache")
	var pack_path := cache.path_join(str(entry.sha256) + ".pck")
	if not _valid_file(pack_path, int(entry.bytes), str(entry.sha256)):
		var output := FileAccess.open(pack_path + ".partial", FileAccess.WRITE)
		if output == null: return _fail("Cannot write content cache")
		for chunk: Dictionary in entry.chunks:
			var chunk_path := cache.path_join(str(chunk.sha256) + ".part")
			if not _valid_file(chunk_path, int(chunk.bytes), str(chunk.sha256)):
				if not OS.has_feature("web"):
					var local_path := "res://" + str(chunk.path)
					if not _valid_file(local_path, int(chunk.bytes), str(chunk.sha256)): output.close(); return _fail("Missing local content: " + group)
					output.store_buffer(FileAccess.get_file_as_bytes(local_path)); continue
				request.download_file = chunk_path; request.body_size_limit = int(chunk.bytes)
				if request.request(base_url + str(chunk.path)) != OK: output.close(); request.download_file = ""; return _fail("Cannot request " + group)
				var response: Array = await request.request_completed
				request.download_file = ""
				if int(response[0]) != HTTPRequest.RESULT_SUCCESS or int(response[1]) != 200 or not _valid_file(chunk_path, int(chunk.bytes), str(chunk.sha256)): output.close(); return _fail("Content download failed: " + group)
			output.store_buffer(FileAccess.get_file_as_bytes(chunk_path))
			await get_tree().process_frame
		output.close()
		if not _valid_file(pack_path + ".partial", int(entry.bytes), str(entry.sha256)): return _fail("Content integrity check failed: " + group)
		if DirAccess.rename_absolute(pack_path + ".partial", pack_path) != OK: return _fail("Cannot finish content cache")
		for chunk: Dictionary in entry.chunks: DirAccess.remove_absolute(cache.path_join(str(chunk.sha256) + ".part"))
	if not ProjectSettings.load_resource_pack(pack_path, false): return _fail("Cannot mount content group: " + group)
	return true
func _valid_file(path: String, bytes: int, digest: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return false
	var valid := file.get_length() == bytes; file.close()
	return valid and FileAccess.get_sha256(path) == digest
func _fail(message: String) -> bool:
	last_error = message; push_error(message)
	return false
