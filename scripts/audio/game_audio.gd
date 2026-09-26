extends Node
var manifest: Dictionary = {}
var streams: Dictionary = {}
var wet_streams: Dictionary = {}
var wet_players: Dictionary = {}
var manifest_directory := ""
var stage := ""
var area := 0
var music: AudioStreamPlayer
var music_key := ""
var music_signature := ""
var footsteps: AudioStreamPlayer3D
var shots: AudioStreamPlayer3D
var movement: AudioStreamPlayer3D
var ui_effects: AudioStreamPlayer
var base_manifest: Dictionary = {}
var audio_catalog: Dictionary = {}
var zone_manifests: Dictionary = {}
var zone_request := 0
var music_request := 0
var music_streams: Dictionary = {}
var requested_music_cue := -1
var requested_music_signature := ""
var native_context: Dictionary = {}
var preparing := false
func set_preparing(value: bool) -> void:
	preparing = value
	if music != null: music.stream_paused = value
func configure(player: Node3D, path: String, music_role: String = "music") -> void:
	_ensure_buses()
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary: return
	manifest = data
	base_manifest = data.duplicate(true)
	audio_catalog = data.get("audio_catalog", {})
	manifest_directory = path.get_base_dir()
	stage = str(manifest.get("stage", "")) if player != null else ""
	music = AudioStreamPlayer.new()
	music.bus = "BGM"
	music.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(music)
	ui_effects = AudioStreamPlayer.new()
	ui_effects.bus = "SE"
	ui_effects.max_polyphony = 8
	add_child(ui_effects)
	if player == null:
		play_music("title_music", path)
		return
	footsteps = AudioStreamPlayer3D.new()
	footsteps.bus = "SE"
	player.add_child(footsteps)
	shots = AudioStreamPlayer3D.new()
	shots.bus = "SE"
	shots.max_polyphony = 8
	player.add_child(shots)
	movement = AudioStreamPlayer3D.new()
	movement.bus = "SE"
	player.add_child(movement)
	player.footstep.connect(_footstep)
	player.fired.connect(_fire)
	player.jumped.connect(func(): _effect(movement, "jump"))
	player.landed.connect(func(): _effect(movement, "land"))
	if not music_role.is_empty(): play_music(music_role, path)
func play_music(role: String, path: String = "res://assets/audio/ST0F/manifest.json") -> void:
	if music == null: return
	var key := str(manifest.get("roles", {}).get(role, ""))
	if not manifest.get("music", {}).has(key): return
	var entry: Dictionary = manifest["music"][key]
	var stream := load(_entry_path(entry, path.get_base_dir())) as AudioStreamWAV
	if stream == null: return
	stream = stream.duplicate() as AudioStreamWAV
	if entry.get("looped", false):
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = int(entry["frames"])
	music.stream = stream
	music_key = key
	music_signature = str(entry.get("bank_sequence_signature", entry.get("file", "")))
	requested_music_cue = key.hex_to_int()
	requested_music_signature = music_signature
	music.play()
	music.stream_paused = preparing
func _entry_path(entry: Dictionary, directory: String = "") -> String:
	var path := str(entry.get("file", ""))
	return path if path.begins_with("res://") or path.begins_with("user://") else (manifest_directory if directory.is_empty() else directory).path_join(path)
func capture_music() -> Dictionary:
	return {"stream": music.stream, "key": music_key, "signature": music_signature, "position": music.get_playback_position(), "playing": music.playing, "paused": music.stream_paused} if music != null and music.stream != null else {}
func adopt_music(state: Dictionary) -> void:
	if music == null or not state.get("stream") is AudioStream: return
	var key := str(state.get("key", ""))
	if requested_music_cue >= 0 and requested_music_cue != 255 and key != "0x%04X" % requested_music_cue: return
	if requested_music_cue >= 0 and requested_music_cue != 255 and not requested_music_signature.is_empty() and requested_music_signature != str(state.get("signature", "")): return
	music.stream = state["stream"]
	music_key = key
	music_signature = str(state.get("signature", ""))
	if bool(state.get("playing", false)): music.play(float(state.get("position", 0.0)))
	music.stream_paused = preparing or bool(state.get("paused", false))
func _load_stream(path: String) -> AudioStream:
	var status := ResourceLoader.load_threaded_get_status(path)
	if status in [ResourceLoader.THREAD_LOAD_INVALID_RESOURCE, ResourceLoader.THREAD_LOAD_FAILED]:
		var error := ResourceLoader.load_threaded_request(path, "AudioStream", true, ResourceLoader.CACHE_MODE_REUSE)
		if error != OK and error != ERR_BUSY: return null
		status = ResourceLoader.load_threaded_get_status(path)
	while status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		await get_tree().process_frame
		status = ResourceLoader.load_threaded_get_status(path)
	return ResourceLoader.load_threaded_get(path) as AudioStream if status == ResourceLoader.THREAD_LOAD_LOADED else null
func _request_music(cue: int) -> void:
	if cue == 255: requested_music_cue = cue; return
	requested_music_cue = cue
	requested_music_signature = ""
	music_request += 1
	var request := music_request
	if cue < 0: return
	var key := "0x%04X" % cue
	var entry: Dictionary = audio_catalog.get("music_variants", {}).get(stage, {}).get(key, audio_catalog.get("music", {}).get(key, manifest.get("music", {}).get(key, {})))
	if entry.is_empty(): return
	requested_music_signature = str(entry.get("bank_sequence_signature", entry.get("file", "")))
	if music != null and music.stream != null and music_key == key and music_signature == requested_music_signature: return
	var owner := str(entry.get("owner_stage", stage))
	if not await AssetStore.ensure_group("audio-" + owner) or request != music_request: return
	var path := _entry_path(entry)
	if not music_streams.has(path):
		var stream: AudioStream = await _load_stream(path)
		if stream == null or request != music_request: return
		music_streams[path] = stream
	if request != music_request or music == null: return
	var stream := (music_streams[path] as AudioStream).duplicate() as AudioStreamWAV
	if stream == null: return
	if bool(entry.get("looped", false)): stream.loop_mode = AudioStreamWAV.LOOP_FORWARD; stream.loop_begin = 0; stream.loop_end = int(entry["frames"])
	music.stream = stream
	music_key = key
	music_signature = requested_music_signature
	music.play()
	music.stream_paused = preparing
func _cue_key(sound_id: int) -> String:
	var key := "0x%04X" % sound_id
	return "0x%04X" % int(audio_catalog.get("cue_types", {}).get(key, {}).get("alias", sound_id))
func _cue_music(sound_id: int) -> bool:
	return str(audio_catalog.get("cue_types", {}).get("0x%04X" % sound_id, {}).get("kind", "")) == "music"
func _prepare_effect(key: String) -> bool:
	var entry: Dictionary = manifest.get("effects", {}).get(key, {})
	if entry.is_empty(): return false
	if not entry.has("owner_stage"): return true
	if not await AssetStore.ensure_group("audio-" + str(entry["owner_stage"])): return false
	if entry.has("reverb") and not await AssetStore.ensure_group("audio-" + str(entry["reverb"].get("owner_stage", entry["owner_stage"]))): return false
	var path := _entry_path(entry)
	if not streams.has(path):
		var stream: AudioStream = await _load_stream(path)
		if stream == null: return false
		streams[path] = stream
	return true
func _effect(node: AudioStreamPlayer3D, role: String) -> void:
	var key := str(manifest.get("roles", {}).get(role, ""))
	if not manifest.get("effects", {}).has(key): return
	var entry: Dictionary = _sound_entry(key)
	var target := node
	if entry.has("profile"):
		var player_key := "%d:%s" % [node.get_instance_id(), key]
		if not wet_players.has(player_key):
			var wet_player := AudioStreamPlayer3D.new(); wet_player.bus = node.bus; wet_player.unit_size = node.unit_size; wet_player.max_distance = node.max_distance; wet_player.attenuation_model = node.attenuation_model; wet_player.panning_strength = node.panning_strength; node.add_child(wet_player); wet_players[player_key] = wet_player
		target = wet_players[player_key] as AudioStreamPlayer3D
		var interval := (8.0 if node == footsteps else 5.0 if node == shots else 1.0) / 30.0
		target.max_polyphony = maxi(1, int(ceil(float(entry.get("duration_seconds", 0)) / interval)) + 1)
	var stream: AudioStream = _sound_stream(key, entry)
	if target.stream != stream: target.stream = stream
	target.volume_db = float(entry.get("volume_db", 0)); target.play()
func set_stage(value: String, target_area: int = 0, context: Dictionary = {}) -> bool:
	var changed_stage := stage != value.to_upper()
	stage = value.to_upper(); area = target_area
	if not context.is_empty(): native_context = context.duplicate(true)
	zone_request += 1
	if changed_stage: music_request += 1; requested_music_cue = -1
	var request := zone_request
	var entry: Dictionary = audio_catalog.get("zones", {}).get(stage, {})
	if entry.is_empty(): return false
	if not await AssetStore.ensure_group("audio-" + stage) or request != zone_request: return false
	if not zone_manifests.has(stage):
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(str(entry["manifest"])))
		if not data is Dictionary: return false
		zone_manifests[stage] = data
	if request != zone_request: return false
	var zone: Dictionary = zone_manifests[stage]
	for owner: String in zone.get("audio_dependencies", []):
		if not await AssetStore.ensure_group("audio-" + owner) or request != zone_request: return false
	var effects: Dictionary = manifest.get("effects", {}).duplicate(true)
	for key in effects.keys():
		if int(effects[key].get("physical_bank", 0)) in zone.get("loaded_effect_slots", []): effects.erase(key)
	for key in zone.get("effects", {}): effects[key] = zone["effects"][key]
	manifest["effects"] = effects
	set_area(area)
	return true
func set_area(value: int) -> void:
	area = value
	var entry: Dictionary = audio_catalog.get("zones", {}).get(stage, {})
	var variant := int(native_context.get("native_save_byte14", 0))
	var flags: Dictionary = native_context.get("event_flags", {})
	for rule: Dictionary in entry.get("music_rules", []):
		var span: Array = rule["native_save_byte14"]
		if int(rule["area"]) != area or variant < int(span[0]) or variant > int(span[1]): continue
		var matches := true
		for flag in rule.get("flags", {}):
			if bool(flags.get(int(flag), flags.get(str(flag), false))) != bool(rule["flags"][flag]): matches = false; break
		if matches: _request_music(int(rule["cue"])); return
func _reverb_enabled() -> bool:
	var profile: Dictionary = manifest.get("reverb", {}).get("stages", {}).get(stage, {})
	return bool(profile.get("areas", {}).get(str(area), profile.get("area_default", profile.get("enabled", false))))
func _sound_entry(key: String) -> Dictionary:
	var entry: Dictionary = manifest.get("effects", {}).get(key, {})
	return entry.get("reverb", entry) if _reverb_enabled() else entry
func _sound_stream(key: String, entry: Dictionary) -> AudioStream:
	if not entry.has("profile"):
		var path := _entry_path(entry)
		if not streams.has(path): streams[path] = load(path) as AudioStream
		return streams[path] as AudioStream
	var path := _entry_path(entry)
	if not wet_streams.has(path): wet_streams[path] = load(path) as AudioStream
	return wet_streams[path] as AudioStream
func play_ui(role: String) -> void:
	var key := str(manifest.get("roles", {}).get(role, ""))
	if ui_effects == null or not manifest.get("effects", {}).has(key): return
	ui_effects.stream = _sound_stream(key, manifest["effects"][key])
	ui_effects.volume_db = float(manifest["effects"][key].get("volume_db", 0))
	ui_effects.play()
func _footstep(sound_id: int = 0x91) -> void:
	_effect(footsteps, "footstep_alternate" if sound_id == 0x90 else "footstep")
func _fire(_projectile: Node3D) -> void:
	_effect(shots, "buster")
func play_at(sound_id: int, point: Vector3) -> void:
	var key := _cue_key(sound_id)
	if _cue_music(sound_id): _request_music(sound_id); return
	if not await _prepare_effect(key): return
	var emitter := AudioStreamPlayer3D.new()
	emitter.bus = "SE"
	get_parent().add_child(emitter)
	emitter.global_position = point
	var entry: Dictionary = _sound_entry(key)
	emitter.stream = _sound_stream(key, entry)
	emitter.volume_db = float(entry.get("volume_db", 0))
	emitter.finished.connect(emitter.queue_free)
	emitter.play()
func play_sound(sound_id: int) -> void:
	var key := _cue_key(sound_id)
	if _cue_music(sound_id): _request_music(sound_id); return
	if ui_effects == null or not await _prepare_effect(key): return
	ui_effects.stream = _sound_stream(key, manifest["effects"][key])
	ui_effects.volume_db = float(manifest["effects"][key].get("volume_db", 0))
	ui_effects.play()
func _ensure_buses() -> void:
	for name in ["BGM", "SE"]:
		if AudioServer.get_bus_index(name) >= 0: continue
		AudioServer.add_bus()
		var index := AudioServer.bus_count - 1
		AudioServer.set_bus_name(index, name)
		AudioServer.set_bus_send(index, "Master")
func apply_options(bgm: int, se: int, sound: int) -> void:
	_ensure_buses()
	for entry in [["BGM", bgm], ["SE", se]]:
		var index := AudioServer.get_bus_index(str(entry[0]))
		AudioServer.set_bus_volume_db(index, linear_to_db(maxf(float(entry[1]) / 127.0, 0.0001)))
		AudioServer.set_bus_mute(index, int(entry[1]) == 0)
	var stereo: AudioEffectStereoEnhance
	for index in range(AudioServer.get_bus_effect_count(0)):
		var effect := AudioServer.get_bus_effect(0, index)
		if effect is AudioEffectStereoEnhance:
			stereo = effect
			break
	if stereo == null:
		stereo = AudioEffectStereoEnhance.new()
		AudioServer.add_bus_effect(0, stereo)
	stereo.pan_pullout = 0.0 if sound == 1 else 1.0
