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
var footsteps: AudioStreamPlayer3D
var shots: AudioStreamPlayer3D
var movement: AudioStreamPlayer3D
var ui_effects: AudioStreamPlayer
func configure(player: Node3D, path: String, music_role: String = "music") -> void:
	_ensure_buses()
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not data is Dictionary: return
	manifest = data
	manifest_directory = path.get_base_dir()
	stage = str(manifest.get("stage", "")) if player != null else ""
	music = AudioStreamPlayer.new()
	music.bus = "BGM"
	music.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(music)
	if player == null:
		ui_effects = AudioStreamPlayer.new()
		ui_effects.bus = "SE"
		ui_effects.max_polyphony = 8
		add_child(ui_effects)
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
	var stream := load(path.get_base_dir().path_join(str(entry["file"]))) as AudioStreamWAV
	if stream == null: return
	stream = stream.duplicate() as AudioStreamWAV
	if entry.get("looped", false):
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = int(entry["frames"])
	music.stream = stream
	music_key = key
	music.play()
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
func set_stage(value: String, target_area: int = 0) -> void:
	stage = value.to_upper(); area = target_area
	var role := str(manifest.get("stage_music", {}).get(stage, ""))
	var key := str(manifest.get("roles", {}).get(role, ""))
	var entry: Dictionary = manifest.get("music", {}).get(key, {})
	if music != null and not entry.is_empty() and (music.stream == null or music_key != key): play_music(role, manifest_directory.path_join("manifest.json"))
func set_area(value: int) -> void: area = value
func _reverb_enabled() -> bool:
	var profile: Dictionary = manifest.get("reverb", {}).get("stages", {}).get(stage, {})
	return bool(profile.get("areas", {}).get(str(area), profile.get("area_default", profile.get("enabled", false))))
func _sound_entry(key: String) -> Dictionary:
	var entry: Dictionary = manifest.get("effects", {}).get(key, {})
	return entry.get("reverb", entry) if _reverb_enabled() else entry
func _sound_stream(key: String, entry: Dictionary) -> AudioStream:
	if not entry.has("profile"):
		if not streams.has(key): streams[key] = load(manifest_directory.path_join(str(entry["file"]))) as AudioStream
		return streams[key] as AudioStream
	if not wet_streams.has(key): wet_streams[key] = load(manifest_directory.path_join(str(entry["file"]))) as AudioStream
	return wet_streams[key] as AudioStream
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
	var key := "0x%04X" % sound_id
	if not manifest.get("effects", {}).has(key): return
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
	var key := "0x%04X" % sound_id
	if ui_effects == null or not manifest.get("effects", {}).has(key): return
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
