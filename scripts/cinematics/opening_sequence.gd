extends Control
signal prepared(success: bool)
signal finished(skipped: bool)
var manifest: Dictionary = {}
var directory := ""
var viewport: SubViewport
var world: Node3D
var camera: Camera3D
var effects: Node
var audio: AudioStreamPlayer
var audio_entries: Dictionary = {}
var xa_volume := 127
var xa_fade := 0
var veil: ColorRect
var scenes: Dictionary = {}
var actors: Dictionary = {}
var bank := "ST02"
var area := 0
var phase := 0
var step := 0
var segment := 0
var segment_tick := 0
var phase_tick := 0
var total_tick := 0
var command_index := 0
var accumulator := 0.0
var running := false
var target_mode := 0
var target_slot := 0
var eye_mode := 0
var focus := Vector3.ZERO
var relative_focus := Vector3.ZERO
var orbit := Vector3.ZERO
var eye := Vector3.ZERO
var focus_velocity := Vector3.ZERO
var orbit_velocity := Vector3.ZERO
var eye_velocity := Vector3.ZERO
var focus_curve: Dictionary = {}
var orbit_curve: Dictionary = {}
var eye_curve: Dictionary = {}
var fade := 255
var fade_speed := 0
var transition := 0
var trig: Array = []
func configure(path: String = "res://assets/opening/manifest.json") -> bool:
	if not FileAccess.file_exists(path): prepared.emit(false); return false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary or parsed.get("commands", []).is_empty(): prepared.emit(false); return false
	manifest = parsed; directory = path.get_base_dir(); mouse_filter = Control.MOUSE_FILTER_STOP; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); process_mode = Node.PROCESS_MODE_ALWAYS
	var display := SubViewportContainer.new(); display.stretch = true; display.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); add_child(display)
	viewport = SubViewport.new(); viewport.size = Vector2i(1280, 720); viewport.own_world_3d = true; viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS; display.add_child(viewport)
	world = Node3D.new(); viewport.add_child(world)
	camera = Camera3D.new(); camera.near = 0.1875; camera.far = 2048.0; camera.fov = rad_to_deg(2.0 * atan(120.0 / 384.0)); camera.current = true; world.add_child(camera); camera.set_meta("screen_offset", Vector2(160, 120)); camera.set_meta("projection_h", 384.0)
	var environment := WorldEnvironment.new(); environment.environment = Environment.new(); environment.environment.background_mode = Environment.BG_CANVAS; environment.environment.background_canvas_max_layer = -1; environment.environment.background_color = Color.BLACK; world.add_child(environment)
	effects = preload("res://scripts/cinematics/opening_effects.gd").new(); world.add_child(effects)
	if effects.configure(camera, manifest): trig = effects.data.get("trig4096", [])
	audio = AudioStreamPlayer.new(); audio.bus = "BGM" if AudioServer.get_bus_index("BGM") >= 0 else "Master"; add_child(audio)
	var audio_path: String = directory.path_join("audio/manifest.json")
	if FileAccess.file_exists(audio_path):
		var audio_manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(audio_path))
		if audio_manifest is Dictionary:
			for entry: Dictionary in audio_manifest.get("entries", []): audio_entries[str(int(entry["id"]))] = entry
	veil = ColorRect.new(); veil.color = Color.BLACK; veil.mouse_filter = Control.MOUSE_FILTER_IGNORE; veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); add_child(veil)
	resized.connect(_resize); _resize(); _prepare.call_deferred(); return true
func _prepare() -> void:
	for source: Dictionary in manifest.get("actor_banks", []):
		for model: Dictionary in source.get("models", []):
			var path: String = directory.path_join(str(model["export"]["model_file"])); var resource: Resource = load(path)
			if not resource is PackedScene: prepared.emit(false); return
			scenes[path] = resource
	var level_path: String = directory.path_join(str(manifest["levels"])); var levels: Variant = JSON.parse_string(FileAccess.get_file_as_string(level_path))
	if not levels is Dictionary: prepared.emit(false); return
	for level: Dictionary in levels.get("areas", []):
		var path: String = level_path.get_base_dir().path_join(str(level["file"])); var resource: Resource = load(path)
		if not resource is PackedScene: prepared.emit(false); return
		scenes["area%d" % int(level["index"])] = resource
	running = true; _segment_enter(); _commands(); _camera_update(); prepared.emit(true)
func _resize() -> void:
	if not is_instance_valid(viewport): return
	if is_instance_valid(effects) and is_instance_valid(effects.background): effects.background.scale = size / Vector2(320, 240); effects.flashes.scale = effects.background.scale
func _unhandled_input(event: InputEvent) -> void:
	if running and (event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_cancel")):
		get_viewport().set_input_as_handled(); _finish(true)
func _process(delta: float) -> void:
	if not running: return
	accumulator += delta * 25.0
	while accumulator >= 1.0 and running: accumulator -= 1.0; native_tick()
func native_tick() -> void:
	if not running: return
	_callback()
	if not running: return
	_commands(); _curves(); _actors_tick(); _camera_update(); effects.native_tick()
	if xa_fade != 0: xa_volume = clampi(xa_volume + xa_fade, 0, 127); audio.volume_db = linear_to_db(maxf(float(xa_volume) / 127.0, 0.0001))
	if fade_speed != 0: fade = clampi(fade + fade_speed, 0, 255); veil.color.a = float(fade) / 255.0
	total_tick += 1; phase_tick += 1; segment_tick += 1
	var duration: int = int(manifest["timeline"][segment]["duration"])
	if duration >= 0 and segment_tick == duration: _advance()
func _advance() -> void:
	segment += 1
	if segment >= manifest["timeline"].size(): _finish(false); return
	var next_phase: int = int(manifest["timeline"][segment]["phase"])
	if phase != next_phase: phase = next_phase; phase_tick = 0
	step = int(manifest["timeline"][segment]["step"]); segment_tick = 0; transition = 0; _segment_enter()
func _segment_enter() -> void:
	var key: String = "%d:%d" % [phase, step]
	if key == "0:0": _request_fade(16); _play_xa(key)
	elif key == "0:1" or key == "2:7": _request_fade(2)
	elif key == "1:13" or key == "2:6" or key == "2:11": transition = 0
	for record: Dictionary in manifest.get("callbacks", {}).get(key, {}).get("spawn", []): _spawn(record)
	var source: Dictionary = manifest.get("callbacks", {}).get(key, {})
	if source.has("bank"): _set_bank(str(source["bank"]))
	if source.has("area"): _set_area(int(source["area"]))
func _callback() -> void:
	var key: String = "%d:%d" % [phase, step]
	if key == "0:0": _advance()
	elif key == "0:2" and segment_tick == 350: _set_area(1); _advance()
	elif key == "1:13":
		if transition == 0 and segment_tick == 100: transition = 1; _request_fade(18); xa_fade = -8
		elif transition == 1 and fade >= 255 and xa_volume == 0:
			for slot: int in actors.keys(): _remove(slot)
			for effect: Dictionary in effects.actors.duplicate(): effects.remove(int(effect["slot"]))
			_set_bank("ST0201"); _set_area(2); _play_xa(key); _request_fade(2); _advance()
	elif key == "2:6":
		if segment_tick == 40: xa_fade = -8; transition = 1
		elif transition == 1 and xa_volume == 0: _set_bank("ST0202"); _play_xa(key); _advance()
	elif key == "2:7" and segment_tick == 0:
		for record: Dictionary in manifest.get("callback_records", {}).get("0x800f1a38", []): _spawn(record)
	elif key == "2:11":
		if transition == 0: xa_fade = -8; transition = 1
		elif xa_volume == 0: _set_bank("ST0203"); _play_xa(key); _advance()
	elif key == "2:14" and segment_tick == 300: _request_fade(18)
	elif key == "2:14" and segment_tick > 300 and fade >= 255: _advance()
	for action: Dictionary in manifest.get("callbacks", {}).get(key, {}).get("actions", []):
		if int(action["tick"]) != segment_tick: continue
		if action.has("effect"):
			var effect: Dictionary = action["effect"]; effects.spawn(int(effect["variant"]), effect)
		var slot: int = int(action.get("slot", -1))
		if action.has("control"): _control(slot, int(action["control"]))
		if action.has("position") and actors.has(slot): actors[slot]["node"].position = _world(_vector(action["position"]))
		if action.has("yaw") and actors.has(slot): actors[slot]["node"].rotation.y = -float(action["yaw"]) * TAU / 4096.0
		if actors.has(slot): actors[slot]["fields"].merge(action.get("fields", {}), true)
	for clear: Dictionary in manifest.get("callbacks", {}).get(key, {}).get("pool_clears", []):
		if int(clear["tick"]) != segment_tick: continue
		for slot: int in actors.keys():
			if str(actors[slot]["record"].get("pool", "")) == str(clear["pool"]): _remove(slot)
func _request_fade(code: int) -> void:
	var speeds: Array[int] = [255, 64, 16, 8, 4]; var speed: int = speeds[code & 7]
	fade = 255 if code < 16 else 0; fade_speed = -speed if code < 16 else speed; veil.color.a = float(fade) / 255.0
func _play_xa(key: String) -> void:
	xa_volume = 127; xa_fade = 0; audio.volume_db = 0.0
	for entry: Dictionary in manifest.get("xa", {}).get("entries", []):
		if str(entry["phase"]) != key or not audio_entries.has(str(int(entry["id"]))): continue
		var source: Dictionary = audio_entries[str(int(entry["id"]))]; var path: String = str(source["file"]); path = path if path.begins_with("res://") else directory.path_join("audio").path_join(path)
		if not ResourceLoader.exists(path): return
		audio.stream = load(path) as AudioStream; audio.play(); return
func _commands() -> void:
	while command_index < manifest["commands"].size():
		var command: Dictionary = manifest["commands"][command_index]; var words: Array = command["words"]; var opcode: int = int(command["opcode"]); var header: int = int(words[0])
		if opcode == 0 and total_tick < (header & 0xffffff): return
		if opcode == 1 and (phase != ((header >> 16) & 255) or phase_tick != (header & 65535)): return
		if opcode == 2 and (step != ((header >> 16) & 255) or segment_tick != (header & 65535)): return
		command_index += 1
		match opcode:
			3: eye_mode = 0
			4: eye_mode = 1
			5: target_mode = 0
			6: target_mode = 1
			7: target_mode = 2
			16: target_mode = 0; focus = _fixed(words); focus_curve.clear()
			17, 18: target_mode = 1 if opcode == 17 else 2; target_slot = (header >> 16) & 255; relative_focus = _fixed(words); focus_curve.clear()
			19: orbit = _fixed(words); orbit_curve.clear()
			20: eye = _fixed(words); eye_curve.clear()
			21: focus_velocity = _fixed(words); focus_curve.clear()
			22: orbit_velocity = _fixed(words); orbit_curve.clear()
			23: eye_velocity = _fixed(words); eye_curve.clear()
			24: focus_curve = {"start": focus if target_mode == 0 else relative_focus, "end": _fixed(words), "tick": 0, "duration": header & 65535, "curve": (header >> 16) & 7}; focus_velocity = Vector3.ZERO
			25: orbit_curve = {"start": orbit, "end": _fixed(words), "tick": 0, "duration": header & 65535, "curve": (header >> 16) & 7}; orbit_velocity = Vector3.ZERO
			26: eye_curve = {"start": eye, "end": _fixed(words), "tick": 0, "duration": header & 65535, "curve": (header >> 16) & 7}; eye_velocity = Vector3.ZERO
			32, 33, 34: camera.set_meta("native_fade_mode", opcode - 32)
			64: _spawn(command["actor_record"])
			65: _remove(_record(command["actor_record"])[1])
			255: return
func _fixed(words: Array) -> Vector3: return Vector3(_s32(int(words[1])), _s32(int(words[2])), _s32(int(words[3]))) / 65536.0
func _vector(value: Array) -> Vector3: return Vector3(float(value[0]), float(value[1]), float(value[2]))
func _s32(value: int) -> int: return (value & 2147483647) - (value & 2147483648)
func _world(value: Vector3) -> Vector3: return Vector3(-value.x, -value.y, value.z) / 256.0
func _curves() -> void:
	if focus_curve.is_empty():
		if target_mode == 0: focus += focus_velocity
		else: relative_focus += focus_velocity
	else:
		if target_mode == 0: focus = _curve(focus_curve)
		else: relative_focus = _curve(focus_curve)
	if orbit_curve.is_empty(): orbit += orbit_velocity
	else: orbit = _curve(orbit_curve)
	if eye_curve.is_empty(): eye += eye_velocity
	else: eye = _curve(eye_curve)
func _curve(value: Dictionary) -> Vector3:
	var tick: int = int(value["tick"]); var duration: int = maxi(1, int(value["duration"])); var start: Vector3 = value["start"]; var end: Vector3 = value["end"]; var result: Vector3
	if tick >= duration - 1: result = end; value.clear(); return result
	if int(value["curve"]) == 1 and not trig.is_empty():
		var cosine: int = int(trig[(int(tick * 2048 / duration)) & 4095][1])
		for axis: int in range(3):
			var first: int = int(start[axis] * 65536.0) >> 1; var second: int = int(end[axis] * 65536.0) >> 1; var scale: int = int(float(first - second) / 4096.0); result[axis] = float(first + second + scale * cosine) / 65536.0
	else: result = start.lerp(end, float(tick) / float(duration))
	value["tick"] = tick + 1; return result
func _record(source: Dictionary) -> PackedByteArray: return str(source["bytes"]).hex_decode()
func _spawn(source: Dictionary) -> void:
	var record: PackedByteArray = _record(source); var slot: int = int(source.get("slot", record[1])); var kind: int = int(record[4]); var variant: int = int(record[6]); _remove(slot)
	if kind in [14, 18]: effects.spawn(variant, {"class": kind, "slot": slot, "parameter": record.decode_u32(8), "x": record.decode_s16(12), "y": record.decode_s16(14), "z": record.decode_s16(16)}); return
	var flags: int = (variant << 16) | (kind << 8) | (int(record[2]) & 0x60)
	for source_bank: Dictionary in manifest["actor_banks"]:
		if str(source_bank["archive"]).get_file().get_basename() != bank: continue
		for model: Dictionary in source_bank["models"]:
			if int(model["flags"]) != flags: continue
			var model_path: String = directory.path_join(str(model["export"]["model_file"])); var node: Node3D = (scenes[model_path] as PackedScene).instantiate(); node.name = "Actor_%02d" % slot; world.add_child(node); node.position = _world(Vector3(record.decode_s16(12), record.decode_s16(14), record.decode_s16(16))); node.rotation.y = -float(record.decode_u16(18)) * TAU / 4096.0; preload("res://scripts/world/native_material.gd").apply(node, 128.0)
			actors[slot] = {"node": node, "record": source, "model": model, "clock": 0, "control": -1, "class": kind, "yaw": record.decode_u16(18), "forward": 0, "fields": {"0x0C": record.decode_u32(8)}}
			_face_surfaces(actors[slot])
			if kind == 20 and variant == 1: node.rotation.x = -float(record.decode_u16(10) & 4095) * TAU / 4096.0
			if kind == 39: node.scale = Vector3.ONE * 4.0
			if (int(record[2]) & 0x60) == 0x20 and kind in [22, 26, 29, 30, 33, 35, 37, 40, 60]: _ground_actor(node)
			_control(slot, 0); return
func _ground_actor(node: Node3D) -> void:
	var source: Dictionary = manifest.get("native_floor_shapes", {}).get(str(area), {})
	if source.is_empty(): return
	var position := Vector3i(int(-node.position.x * 256.0), int(-node.position.y * 256.0), int(node.position.z * 256.0)); var best := 32767
	var tile: Array = source.get("grid", {}).get("%d:%d" % [(position.x >> 9) + 64, (position.z >> 9) + 64], [])
	if not tile.is_empty() and ((int(tile[0]) | (int(tile[1]) << 8)) & 0x4800) != 0x0800: best = _tile_floor(tile, position.x, position.z)
	for box: Dictionary in source.get("boxes", []):
		if int(box["kind"]) != 0 or int(box["mask"]) == 0: continue
		if position.x <= int(box["x"][0]) - 8 or position.x >= int(box["x"][1]) + 8 or position.z <= int(box["z"][0]) - 8 or position.z >= int(box["z"][1]) + 8: continue
		if int(box["y"][0]) < best and mini(position.y, best) < int(box["y"][1]): best = int(box["y"][0])
	if best != 32767: node.position.y = -float(best) / 256.0
func _tile_floor(tile: Array, x: int, z: int) -> int:
	var first: int = int(tile[4]) << 4; var second: int = int(tile[5]) << 4; var third: int = int(tile[6]) << 4; var fourth: int = int(tile[7]) << 4; var u: int = x & 511; var v: int = 511 - (z & 511); var alternate: bool = ((int(tile[0]) | (int(tile[1]) << 8)) & 0x2000) != 0
	if (u >= v if alternate else 511 - u >= v): return int(float((first - second) * u) / 512.0) + int(float((second - fourth if alternate else first - third) * v) / 512.0) - first
	return int(float((third - fourth) * u) / 512.0) + int(float((first - third if alternate else second - fourth) * v) / 512.0) - first if alternate else int(float((third - fourth) * u) / 512.0) + int(float((second - fourth) * v) / 512.0) - second - third + fourth
func _control(slot: int, index: int, restart: bool = false) -> void:
	if not actors.has(slot): return
	var actor: Dictionary = actors[slot]; var animation: AnimationPlayer = actor["node"].find_child("AnimationPlayer", true, false) as AnimationPlayer
	if animation == null: return
	if int(actor["control"]) == index and not restart: return
	var clip := ""
	for source: Dictionary in actor["model"]["export"].get("animations", []):
		if int(source["slot"]) == index: clip = str(source["name"]); break
	if clip.is_empty() or not animation.has_animation(clip): return
	animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL; animation.play(clip); animation.advance(0); actor["control"] = index; actor["clock"] = 0
func _remove(slot: int) -> void:
	effects.remove(slot)
	if actors.has(slot): actors[slot]["node"].queue_free(); actors.erase(slot)
func _set_bank(value: String) -> void:
	bank = value; effects.set_bank(value)
func _set_area(index: int) -> void:
	var previous: Node = world.get_node_or_null("StageMap")
	if is_instance_valid(previous): world.remove_child(previous); previous.queue_free()
	area = index
	if not scenes.has("area%d" % index): return
	var node: Node3D = (scenes["area%d" % index] as PackedScene).instantiate(); node.name = "StageMap"
	world.add_child(node); preload("res://scripts/world/native_material.gd").apply(node)
func _actors_tick() -> void:
	for slot: int in actors:
		var actor: Dictionary = actors[slot]; var animation: AnimationPlayer = actor["node"].find_child("AnimationPlayer", true, false) as AnimationPlayer
		_actor_controls(slot, actor)
		_actor_faces(actor)
		_actor_motion(actor)
		if int(actor["class"]) == 39: _ship_tick(actor)
		if animation != null and animation.is_playing(): animation.advance(1.0 / 30.0)
		actor["clock"] = int(actor["clock"]) + 1
	for frame: Dictionary in manifest.get("actor_frames", {}).get(str(total_tick), []):
		var slot: int = int(frame["slot"])
		if not actors.has(slot): continue
		if frame.has("position"): actors[slot]["node"].position = _world(_vector(frame["position"]))
		if frame.has("yaw"): actors[slot]["node"].rotation.y = -float(frame["yaw"]) * TAU / 4096.0
		if frame.has("control") and int(actors[slot]["control"]) != int(frame["control"]): _control(slot, int(frame["control"]))
func _actor_controls(slot: int, actor: Dictionary) -> void:
	var kind: String = str(int(actor["class"])); var mode: String = str(int(actor["fields"].get("0x0C", 0)) & 255)
	for event: Dictionary in manifest.get("actor_controls", {}).get(kind, {}).get(mode, {}).get(str(step), []):
		if int(event["tick"]) != segment_tick: continue
		_control(slot, int(event["control"]), bool(event.get("restart", false)))
func _actor_motion(actor: Dictionary) -> void:
	var mode := str(int(actor["fields"].get("0x0C", 0)) & 255)
	var modes: Dictionary = manifest.get("actor_motion", {}).get(str(int(actor["class"])), {})
	if not modes.has(mode): return
	for event: Dictionary in modes[mode].get(str(step), []):
		if int(event["tick"]) != segment_tick: continue
		actor["forward"] = int(event["forward"]); actor["yaw"] = (int(actor["yaw"]) + int(event.get("yaw_delta", 0))) & 4095
	var node: Node3D = actor["node"]; var yaw := int(actor["yaw"]); var forward := -int(actor["forward"])
	node.rotation.y = -float(yaw) * TAU / 4096.0
	if forward != 0 and not trig.is_empty(): node.position += _world(Vector3(float(int(trig[yaw][0]) * forward) / 65536.0, 0.0, float(int(trig[yaw][1]) * forward) / 65536.0)); _ground_actor(node)
func _face_surfaces(actor: Dictionary) -> void:
	var surfaces: Array = []
	var definitions: Array = actor["model"]["export"].get("source_surfaces", [])
	var meshes: Array[Node] = actor["node"].find_children("*", "MeshInstance3D", true, false)
	if definitions.is_empty() or meshes.is_empty(): actor["face_surfaces"] = surfaces; return
	var mesh := meshes[0] as MeshInstance3D
	for source: Dictionary in definitions:
		var surface := int(source["surface"])
		if surface >= mesh.mesh.get_surface_count(): continue
		var material := mesh.get_active_material(surface) as ShaderMaterial
		if material == null: continue
		material.set_shader_parameter("part_visible", not bool(source.get("default_hidden", false)))
		surfaces.append({"part": int(source["source_part"]), "stream": int(source["uv_stream"]), "material": material})
	actor["face_surfaces"] = surfaces
func _actor_faces(actor: Dictionary) -> void:
	var mode := str(int(actor["fields"].get("0x0C", 0)) & 255)
	for event: Dictionary in manifest.get("actor_faces", {}).get(str(int(actor["class"])), {}).get(mode, {}).get(str(step), []):
		if int(event["tick"]) != segment_tick: continue
		var hidden := PackedInt32Array(event.get("hidden_parts", []))
		for surface: Dictionary in actor.get("face_surfaces", []):
			var material := surface["material"] as ShaderMaterial
			var stream := int(surface["stream"])
			if stream in [1, 2]: material.set_shader_parameter("uv_word", int(event["uv_words"][stream - 1]))
			material.set_shader_parameter("part_visible", not int(surface["part"]) in hidden)
func _ship_tick(actor: Dictionary) -> void:
	var node: Node3D = actor["node"]; var yaw: int = int(actor["yaw"])
	if step == 0 and segment_tick == 0: actor["forward"] = 0
	if step == 1 and segment_tick == 0: actor["forward"] = 64
	if step == 2 and segment_tick == 0: node.position.x = 0.0; node.position.z = 1830.0 / 256.0; yaw = 0; actor["forward"] = 64
	var source_z: int = int(node.position.z * 256.0)
	if step in [0, 1] and ((source_z > 400 and ((total_tick * 2) & 1) == 0) or (source_z < -400 and ((total_tick * 2) & 3) == 0)): yaw = (yaw + 1) & 4095
	actor["yaw"] = yaw; node.rotation.y = -float(yaw) * TAU / 4096.0
	var velocity: int = -int(actor["forward"])
	if velocity != 0 and not trig.is_empty(): node.position += _world(Vector3(float(int(trig[yaw][0]) * velocity) / 65536.0, 0.0, float(int(trig[yaw][1]) * velocity) / 65536.0))
func _camera_update() -> void:
	var target: Vector3 = focus
	if target_mode != 0:
		target = relative_focus
		if actors.has(target_slot): target += Vector3(-actors[target_slot]["node"].position.x, -actors[target_slot]["node"].position.y, actors[target_slot]["node"].position.z) * 256.0
	var camera_frames: Array = manifest.get("camera_frames", [])
	if total_tick < camera_frames.size():
		var frame: Dictionary = camera_frames[total_tick]
		if frame.has("control"):
			_native_view(frame["control"]); return
		camera.position = _world(_vector(frame["eye"])); target = _vector(frame["target"])
	elif eye_mode != 0:
		camera.position = _world(eye)
		var world_target: Vector3 = _world(target)
		if camera.position.distance_squared_to(world_target) > 0.000001: camera.look_at(world_target, Vector3.UP)
	else:
		var pitch: float = orbit.x * TAU / 4096.0; var yaw: float = orbit.y * TAU / 4096.0; var offset := Vector3(sin(pitch) * cos(yaw), sin(yaw), cos(pitch) * cos(yaw)) * orbit.z; var rotation: Basis = Basis(Vector3.RIGHT, yaw) * Basis(Vector3.UP, -pitch); var rows: Array[Vector3] = [Vector3(rotation.x.x, rotation.y.x, rotation.z.x), Vector3(rotation.x.y, rotation.y.y, rotation.z.y), Vector3(rotation.x.z, rotation.y.z, rotation.z.z)]; camera.basis = _view_basis(rows).inverse(); camera.position = _world(target - offset)
	camera.set_meta("native_yaw_previous", camera.get_meta("native_yaw_current", 0)); camera.set_meta("native_yaw_current", -int(orbit.y) & 4095)
func _native_view(control: Array) -> void:
	var packed := PackedByteArray(); packed.resize(20)
	for index: int in range(5): packed.encode_u32(index * 4, int(control[index]))
	var rows: Array[Vector3] = []
	for row: int in range(3): rows.append(Vector3(packed.decode_s16(row * 6), packed.decode_s16(row * 6 + 2), packed.decode_s16(row * 6 + 4)) / 4096.0)
	var inverse: Basis = _view_basis(rows).inverse(); var translation := Vector3(_s32(int(control[5])), -_s32(int(control[6])), -_s32(int(control[7]))) / 256.0
	camera.transform = Transform3D(inverse, -(inverse * translation)); camera.set_meta("native_yaw_previous", camera.get_meta("native_yaw_current", 0)); camera.set_meta("native_yaw_current", -int(orbit.y) & 4095)
func _view_basis(rows: Array[Vector3]) -> Basis: return Basis(Vector3(-rows[0].x, rows[1].x, rows[2].x), Vector3(-rows[0].y, rows[1].y, rows[2].y), Vector3(rows[0].z, -rows[1].z, -rows[2].z))
func _finish(skipped: bool) -> void:
	running = false; audio.stop(); finished.emit(skipped)
