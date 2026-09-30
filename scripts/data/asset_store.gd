extends Node
const BASE_TEXTURES = ["res://assets/fades/circle.png", "res://assets/fades/bands.png"]
signal progress(group: String, received: int, total: int)
signal state_changed(group: String, state: String)
const SHOW_DELAY := 0.3
const DEFAULT_TITLE := "Downloading game data..."
var last_error := ""
var manifest: Dictionary = {}
var loaded: Dictionary = {}
var busy := false
var current_group := ""
var request: HTTPRequest
var base_url := ""
var audio_dependencies: Dictionary = {}
var state := ""
var group_done := 0
var group_total := 0
var blocking := 0
var blocking_time := 0.0
var blocking_title := DEFAULT_TITLE
var screen: Control
var layer: CanvasLayer
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	request = HTTPRequest.new(); request.timeout = 0.0; request.download_chunk_size = 4194304; add_child(request)
	if OS.has_feature("web"): base_url = str(JavaScriptBridge.eval("new URL('.', window.location.href).href"))
func _process(delta: float) -> void:
	if busy and request != null and state == "Downloading": progress.emit(current_group, group_done + request.get_downloaded_bytes(), group_total)
	if blocking > 0: blocking_time += delta
	var shown := blocking > 0 and blocking_time >= SHOW_DELAY
	if shown and screen == null:
		layer = CanvasLayer.new(); layer.layer = 128; layer.process_mode = Node.PROCESS_MODE_ALWAYS; add_child(layer)
		screen = preload("res://scripts/ui/common/loading_screen.gd").new(); layer.add_child(screen)
		progress.connect(func(_group: String, received: int, total: int) -> void: screen.received = received; screen.total = total)
		state_changed.connect(func(_group: String, value: String) -> void: screen.state = value)
	if screen != null:
		layer.visible = shown
		if shown:
			screen.title = blocking_title
			if state != "Downloading": screen.state = state; screen.received = group_done; screen.total = group_total
func _block(title: String) -> void:
	if blocking == 0: blocking_time = 0.0; blocking_title = title
	blocking += 1
func _unblock() -> void:
	blocking -= 1
func _set_state(value: String) -> void:
	state = value; state_changed.emit(current_group, value)
func _stage_title(stage: String) -> String:
	if FileAccess.file_exists("res://assets/locations/manifest.json"):
		var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/manifest.json"))
		if catalog is Dictionary:
			for location: Dictionary in catalog.get("locations", []):
				if str(location.get("stage", "")) == stage: return "Loading " + str(location["name"]) + "..."
	return DEFAULT_TITLE
func ensure_stage(stage: String) -> bool:
	_block(_stage_title(stage)); var result := await _ensure_stage(stage); _unblock()
	return result
func _ensure_stage(stage: String) -> bool:
	if not await ensure_menu(): return false
	if not await ensure_group("shared"): return false
	if not await ensure_group("audio-ST0F"): return false
	if stage != "ST0F" and not await ensure_group("audio-" + stage): return false
	var audio_path := "res://assets/audio/" + stage + "/manifest.json"
	if not audio_dependencies.has(stage) and FileAccess.file_exists(audio_path):
		var audio: Variant = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		if audio is Dictionary: audio_dependencies[stage] = audio.get("audio_dependencies", [])
	for owner: String in audio_dependencies.get(stage, []):
		if not await ensure_group("audio-" + owner): return false
	if not await ensure_group("dialogue-" + stage, true): return false
	return await ensure_group("stage-" + stage)
func ensure_menu() -> bool:
	_block(DEFAULT_TITLE); var result := await ensure_group("menu-audio"); _unblock()
	return result
func ensure_opening() -> bool:
	_block(DEFAULT_TITLE)
	var result := await ensure_group("shared") and await ensure_group("opening")
	_unblock()
	return result
func ensure_group(group: String, optional := false) -> bool:
	if not OS.has_feature("web") and not FileAccess.file_exists("res://packs/manifest.json"): return true
	while busy: await get_tree().process_frame
	if loaded.has(group): return true
	busy = true; current_group = group; last_error = ""
	var success := await _ensure_group(group, optional)
	if success: loaded[group] = true
	busy = false; state = ""
	return success
func _ensure_group(group: String, optional := false) -> bool:
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
	if not manifest.groups.has(group): return optional or _fail("Missing content group: " + group)
	var entry: Dictionary = manifest.groups[group]; group_done = 0; group_total = int(entry.bytes); _set_state("Verifying")
	await get_tree().process_frame
	var cache := "user://asset_cache"
	if DirAccess.make_dir_recursive_absolute(cache) != OK: return _fail("Cannot create content cache")
	var pack_path := cache.path_join(str(entry.sha256) + ".pck")
	if not _valid_file(pack_path, int(entry.bytes), str(entry.sha256)):
		_set_state("Downloading")
		var output := FileAccess.open(pack_path + ".partial", FileAccess.WRITE)
		if output == null: return _fail("Cannot write content cache")
		for chunk: Dictionary in entry.chunks:
			var chunk_path := cache.path_join(str(chunk.sha256) + ".part")
			if not _valid_file(chunk_path, int(chunk.bytes), str(chunk.sha256)):
				if not OS.has_feature("web"):
					var local_path := "res://" + str(chunk.path)
					if not _valid_file(local_path, int(chunk.bytes), str(chunk.sha256)): output.close(); return _fail("Missing local content: " + group)
					output.store_buffer(FileAccess.get_file_as_bytes(local_path)); group_done += int(chunk.bytes); continue
				request.download_file = chunk_path; request.body_size_limit = int(chunk.bytes)
				if request.request(base_url + str(chunk.path)) != OK: output.close(); request.download_file = ""; return _fail("Cannot request " + group)
				var response: Array = await request.request_completed
				request.download_file = ""
				if int(response[0]) != HTTPRequest.RESULT_SUCCESS or int(response[1]) != 200 or not _valid_file(chunk_path, int(chunk.bytes), str(chunk.sha256)): output.close(); return _fail("Content download failed: " + group)
			output.store_buffer(FileAccess.get_file_as_bytes(chunk_path)); group_done += int(chunk.bytes)
			await get_tree().process_frame
		output.close(); _set_state("Verifying"); await get_tree().process_frame
		if not _valid_file(pack_path + ".partial", int(entry.bytes), str(entry.sha256)): return _fail("Content integrity check failed: " + group)
		if DirAccess.rename_absolute(pack_path + ".partial", pack_path) != OK: return _fail("Cannot finish content cache")
		for chunk: Dictionary in entry.chunks: DirAccess.remove_absolute(cache.path_join(str(chunk.sha256) + ".part"))
	_set_state("Unpacking"); await get_tree().process_frame
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
