extends Node
var gameplay: Node3D
var overlay: Control
var pages: Dictionary = {}
var status: Label
var options: Control
var options_return := "main"
var settings := ConfigFile.new()
var title: Control
var audio: Node
var custom: PanelContainer
var custom_return := ""
var saves := preload("res://scripts/state/save_store.gd").new()
var save_menu: Control
var save_feedback: Label
var session_loading := false
var opening: Control
var opening_loading := false
var locations: Array = []
var pending_custom_menu := false
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	session_loading = true
	var menu_keys := {"ui_up": KEY_W, "ui_down": KEY_S, "ui_left": KEY_A, "ui_right": KEY_D}
	for action in menu_keys:
		var key := InputEventKey.new()
		key.physical_keycode = menu_keys[action]
		if not InputMap.action_has_event(action, key): InputMap.action_add_event(action, key)
	settings.load("user://settings.cfg")
	if FileAccess.file_exists("res://assets/locations/manifest.json"):
		var catalog: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/manifest.json"))
		if catalog is Dictionary: locations = catalog["locations"]
	AudioServer.set_bus_volume_db(0, 0.0)
	AudioServer.set_bus_mute(0, false)
	audio = preload("res://scripts/audio/game_audio.gd").new()
	audio.name = "MenuAudio"
	add_child(audio)
	var canvas := CanvasLayer.new()
	canvas.layer = 100
	add_child(canvas)
	overlay = Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	canvas.add_child(overlay)
	var theme := Theme.new()
	theme.default_font = load("res://assets/menu/native_font.fnt") as Font
	theme.default_font_size = 24
	overlay.theme = theme
	var background := ColorRect.new()
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.color = Color.TRANSPARENT
	overlay.add_child(background)
	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(center)
	var pause_menu := preload("res://scripts/ui/pause_menu.gd").new()
	overlay.add_child(pause_menu)
	pause_menu.configure()
	pages["pause"] = pause_menu
	options = preload("res://scripts/ui/options_menu.gd").new()
	overlay.add_child(options)
	options.configure(settings)
	options.closed.connect(func(): _show(options_return))
	options.changed.connect(_native_option_changed)
	options.defaults_reset.connect(_native_defaults_reset)
	pages["options"] = options
	save_menu = preload("res://scripts/ui/save_menu.gd").new()
	overlay.add_child(save_menu)
	save_menu.configure(self)
	save_menu.selected.connect(_load_save)
	save_menu.closed.connect(func():
		if session_loading: return
		audio.play_ui("menu_cancel")
		_show("pause" if save_menu.save_mode else "main"))
	pages["saves"] = save_menu
	custom = preload("res://scripts/ui/custom_menu.gd").new()
	var custom_theme := Theme.new()
	custom_theme.default_font = ThemeDB.fallback_font
	custom_theme.default_font_size = 18
	custom.theme = custom_theme
	center.add_child(custom)
	custom.configure(self)
	custom.closed.connect(_close_custom)
	pages["custom"] = custom
	title = preload("res://scripts/ui/title_menu.gd").new()
	overlay.add_child(title)
	pages["main"] = title
	title.selected.connect(_title_selected)
	title.moved.connect(func(): audio.play_ui("menu_move"))
	title.opened.connect(func(): audio.play_sound(0x81))
	title.press_started.connect(func(): audio.play_music("title_music"))
	title.engine_scene_requested.connect(_play_opening)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.visible = false
	status.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	status.offset_top = -32
	status.offset_left = 24
	status.offset_right = -24
	status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_child(status)
	var pause_page: Control = pages["pause"].get_meta("content")
	_button(pause_page, "Resume", _resume)
	_button(pause_page, "Save Game", _save_game)
	_button(pause_page, "Options", func(): _options("pause"))
	_button(pause_page, "Main Menu", _main_menu)
	save_feedback = Label.new()
	save_feedback.add_theme_font_size_override("font_size", 9)
	save_feedback.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	save_feedback.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	pause_page.add_child(save_feedback)
	_apply_native_options()
	get_tree().node_added.connect(_screen_node_added)
	_show("main")
	title.set_process(false)
	status.text = "Loading menu audio..."; status.show()
	if not await AssetStore.ensure_menu():
		status.text = AssetStore.last_error
		return
	audio.configure(null, "res://assets/audio/ST0F/manifest.json")
	audio.music.stop()
	status.hide()
	session_loading = false
	_show("main")
	if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
func _play_opening(_stage: String) -> void:
	if session_loading or opening_loading or is_instance_valid(opening): return
	opening_loading = true
	title.set_process(false)
	status.text = "Loading opening..."; status.show()
	if not await AssetStore.ensure_opening():
		opening_loading = false
		status.text = AssetStore.last_error
		title.show_press_start()
		_show("main")
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	status.hide()
	opening = preload("res://scripts/cinematics/opening_sequence.gd").new()
	overlay.add_child(opening)
	for page in pages.values(): page.hide()
	pages["opening"] = opening
	title.set_process(false)
	audio.music.stop()
	opening.finished.connect(_opening_finished)
	opening.prepared.connect(func(success: bool):
		if not success:
			status.text = "Opening assets could not be loaded."
			status.show()
			_opening_finished(false))
	if not opening.configure(): _opening_finished(false)
	opening_loading = false
	if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
func _opening_finished(_skipped: bool) -> void:
	if not is_instance_valid(opening): return
	if is_instance_valid(opening):
		overlay.remove_child(opening)
		opening.queue_free()
	opening = null
	pages.erase("opening")
	title.show_press_start()
	_show("main")
func _button(parent: Control, text: String, action: Callable) -> void:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 14
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.add_theme_font_size_override("font_size", 10)
	button.add_theme_color_override("font_color", Color(0.72, 0.68, 0.52))
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_focus_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color.WHITE)
	var style := StyleBoxEmpty.new()
	style.set_content_margin(SIDE_LEFT, 14)
	style.set_content_margin(SIDE_RIGHT, 4)
	for state in ["normal", "hover", "pressed", "disabled"]: button.add_theme_stylebox_override(state, style)
	button.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	button.pressed.connect(func():
		audio.play_ui("menu_confirm")
		action.call())
	parent.add_child(button)
	var cursor := TextureRect.new()
	cursor.texture = load("res://assets/menu/title_cursor.png") as Texture2D
	cursor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	cursor.size = Vector2(7, 7)
	cursor.position = Vector2(2, (button.size.y - cursor.size.y) * 0.5)
	button.resized.connect(func(): cursor.position.y = (button.size.y - cursor.size.y) * 0.5)
	cursor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cursor.hide()
	button.add_child(cursor)
	button.focus_entered.connect(cursor.show)
	button.focus_entered.connect(func(): audio.play_ui("menu_move"))
	button.focus_exited.connect(cursor.hide)
	button.mouse_entered.connect(button.grab_focus)
func _show(name: String) -> void:
	overlay.visible = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	for key in pages: pages[key].visible = key == name
	if title != null: title.set_process(name == "main")
	if name == "main": title.focus_first()
	if name == "saves": save_menu.focus_first()
	var content: Control = pages[name].get_meta("content", pages[name])
	for child in content.get_children():
		if child is Button:
			child.grab_focus()
			break
func _new_game() -> void:
	await _start_session({})
func _threaded_scene(path: String) -> PackedScene:
	var status := ResourceLoader.load_threaded_get_status(path)
	if status in [ResourceLoader.THREAD_LOAD_INVALID_RESOURCE, ResourceLoader.THREAD_LOAD_FAILED]:
		var request_error := ResourceLoader.load_threaded_request(path, "PackedScene", true, ResourceLoader.CACHE_MODE_REUSE)
		if request_error != OK and request_error != ERR_BUSY: return null
		status = ResourceLoader.load_threaded_get_status(path)
	while status == ResourceLoader.THREAD_LOAD_IN_PROGRESS:
		await get_tree().process_frame
		status = ResourceLoader.load_threaded_get_status(path)
	return ResourceLoader.load_threaded_get(path) as PackedScene if status == ResourceLoader.THREAD_LOAD_LOADED else null
func _start_session(state: Dictionary, stage: String = "ST04", area: int = 0) -> void:
	if session_loading or opening_loading: return
	session_loading = true
	if not state.is_empty():
		stage = str(state["stage"])
		area = int(state["area"])
	if not await AssetStore.ensure_stage(stage):
		session_loading = false
		if pages["saves"].visible: save_menu.set_message(AssetStore.last_error)
		elif custom.visible: custom.set_location_message(AssetStore.last_error)
		else: status.text = AssetStore.last_error; status.show()
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	var stage_path := "res://assets/levels/" + stage + "/manifest.json"
	if not FileAccess.file_exists(stage_path) or not ResourceLoader.exists("res://assets/player/megaman.glb"):
		if pages["saves"].visible: save_menu.set_message("Prepare your disc assets before loading.")
		else:
			status.text = "Prepare your disc assets with tools/assets.py before starting."
			status.show()
		session_loading = false
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	var stage_manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(stage_path))
	var area_index := -1
	if stage_manifest is Dictionary:
		var entries: Array = stage_manifest.get("areas", [])
		for index in range(entries.size()):
			if int(entries[index]["index"]) == area: area_index = index; break
	if area_index < 0:
		if pages["saves"].visible: save_menu.set_message("This area's native ID is not available.")
		elif custom.visible: custom.set_location_message("This area's native ID is not available.")
		session_loading = false
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	var scene: PackedScene = await _threaded_scene("res://scenes/gameplay.tscn")
	var player_path := "res://assets/player/megaman_civilian.glb" if stage in ["ST04", "ST05", "ST06", "ST07"] else "res://assets/player/megaman.glb"
	var player_scene: PackedScene = await _threaded_scene(player_path) if scene != null else null
	if scene == null or player_scene == null:
		if pages["saves"].visible: save_menu.set_message("The game could not be opened.")
		session_loading = false
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	await get_tree().process_frame
	var previous := gameplay
	var previous_paused := get_tree().paused
	if is_instance_valid(previous): previous.process_mode = Node.PROCESS_MODE_DISABLED
	get_tree().paused = false
	var candidate := scene.instantiate() as Node3D
	candidate.manifest_path = stage_path
	candidate.initial_area = area_index
	candidate.entry_route = state.get("entry_route", {}).duplicate(true)
	candidate.parked_location = state.get("parked_location", {}).duplicate(true)
	candidate.process_mode = Node.PROCESS_MODE_PAUSABLE
	candidate.hide()
	candidate.get_node("HUD").hide()
	add_child(candidate)
	if candidate.audio != null and candidate.audio.music != null: candidate.audio.music.stream_paused = true
	var success: bool = candidate.playable if candidate.preparation_finished else await candidate.prepared
	if success and not state.is_empty(): success = await candidate.restore_state(state)
	if not success:
		remove_child(candidate)
		candidate.queue_free()
		if is_instance_valid(previous):
			previous.process_mode = Node.PROCESS_MODE_PAUSABLE
			previous.player.camera.current = true
		get_tree().paused = previous_paused
		session_loading = false
		if pages["saves"].visible: save_menu.set_message("This save's area could not be loaded.")
		elif custom.visible: custom.set_location_message("The room could not be loaded.")
		else:
			status.text = "The starting area could not be loaded."
			status.show()
		if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
		return
	if is_instance_valid(previous):
		remove_child(previous)
		previous.queue_free()
	gameplay = candidate
	gameplay.stage_transition_requested.connect(_stage_transition)
	gameplay.show()
	gameplay.get_node("HUD").show()
	gameplay.player.mouse_sensitivity = float(settings.get_value("controls", "mouse_sensitivity", 0.003))
	_apply_native_options()
	custom.apply_player()
	gameplay.player.set_physics_process(true)
	session_loading = false
	if is_instance_valid(opening): opening._finish(true)
	_resume(not OS.has_feature("web"))
	if pending_custom_menu: pending_custom_menu = false; _toggle_custom_menu()
func _load_location(stage: String, area: int) -> void:
	await _start_session({}, stage, area)
func _stage_transition(route: Dictionary) -> void:
	if session_loading or not is_instance_valid(gameplay): return
	var previous := gameplay
	var state: Dictionary = previous.save_state(true)
	if state.is_empty(): previous.cancel_stage_transition(); return
	var stage := str(route["destination_stage"]); var area := int(route["destination_area"])
	var source_stage := str(state["stage"]); var source_area := int(state["area"])
	if source_stage in ["ST04", "ST05", "ST06", "ST07"] and stage not in ["ST04", "ST05", "ST06", "ST07"]: state["parked_location"] = {"stage": stage, "area": area}
	elif stage in ["ST04", "ST05", "ST06", "ST07"] and source_stage not in ["ST04", "ST05", "ST06", "ST07"]: state["parked_location"] = {"stage": source_stage, "area": source_area}
	state["stage"] = stage; state["area"] = area
	state["defeated_actors"] = state.get("stage_events", {}).get(stage, []).duplicate()
	state["minimap"] = state.get("explored_stages", {}).get(stage, []).duplicate(true)
	state["entry_route"] = route.duplicate(true)
	await _start_session(state)
	if is_instance_valid(previous) and gameplay == previous: previous.cancel_stage_transition()
func _save_game() -> void:
	if session_loading or not is_instance_valid(gameplay): return
	save_menu.refresh(saves.entries(), true)
	if not saves.error.is_empty(): save_menu.set_message(saves.error)
	_show("saves")
func _show_saves() -> void:
	save_menu.refresh(saves.entries())
	if not saves.error.is_empty(): save_menu.set_message(saves.error)
	_show("saves")
func _load_save(id: String) -> void:
	if session_loading: return
	if save_menu.save_mode:
		if not is_instance_valid(gameplay): return
		var saved_id: String = saves.write(gameplay.save_state(), id)
		if saved_id.is_empty():
			save_menu.set_message(saves.error)
			return
		audio.play_ui("menu_confirm")
		save_feedback.text = "Game saved." if id.is_empty() else "Save overwritten."
		_show("pause")
		return
	var data: Dictionary = saves.read(id)
	if data.is_empty():
		save_menu.set_message(saves.error)
		return
	audio.play_ui("menu_confirm")
	save_menu.set_message("Loading...")
	await _start_session(data["state"])
func _pause() -> void:
	save_feedback.text = ""
	get_tree().paused = true
	_show("pause")
func _resume(capture_mouse: bool = true) -> void:
	audio.music.stop()
	gameplay.audio.music.stream_paused = false
	overlay.hide()
	for page in pages.values(): page.hide()
	title.set_process(false)
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if capture_mouse else Input.MOUSE_MODE_VISIBLE
func _main_menu() -> void:
	get_tree().paused = true
	gameplay.audio.music.stream_paused = true
	title.show_press_start()
	_show("main")
func _title_selected(action: String) -> void:
	if session_loading or opening_loading: return
	audio.play_ui("menu_confirm")
	match action:
		"game_start": _new_game()
		"continue": _show_saves()
		"tutorial":
			_start_session({}, "ST4A", 0)
		"options": _options("main")
func _options(return_page: String) -> void:
	options_return = return_page
	_show("options")
func _input(event: InputEvent) -> void:
	if not event.is_action_pressed("custom_menu"): return
	if session_loading or opening_loading: pending_custom_menu = not pending_custom_menu
	else: _toggle_custom_menu()
	get_viewport().set_input_as_handled()
func _toggle_custom_menu() -> void:
	if custom.visible: _close_custom(); return
	custom_return = ""
	for key in pages:
		if overlay.visible and pages[key].visible: custom_return = key
	if is_instance_valid(opening):
		opening.set_process(false)
		opening.audio.stream_paused = true
	get_tree().paused = is_instance_valid(gameplay)
	_show("custom")
func _unhandled_input(event: InputEvent) -> void:
	if session_loading or opening_loading or is_instance_valid(opening): return
	if not event.is_action_pressed("ui_cancel"): return
	audio.play_ui("menu_cancel")
	if custom.visible: _close_custom()
	elif pages["saves"].visible: _show("pause" if save_menu.save_mode else "main")
	elif pages["options"].visible: _show(options_return)
	elif is_instance_valid(gameplay) and not pages["main"].visible:
		if get_tree().paused: _resume()
		else: _pause()
	get_viewport().set_input_as_handled()
func _close_custom() -> void:
	if custom_return == "opening" and is_instance_valid(opening):
		_show("opening")
		opening.audio.stream_paused = false
		opening.set_process(true)
	elif custom_return.is_empty() and is_instance_valid(gameplay): _resume()
	elif custom_return.is_empty(): _show("main")
	else: _show(custom_return)
func _sensitivity_changed(value: float) -> void:
	if is_instance_valid(gameplay): gameplay.player.mouse_sensitivity = value
	settings.set_value("controls", "mouse_sensitivity", value)
	settings.save("user://settings.cfg")
func _native_option_changed(_key: String, _value: int) -> void:
	audio.play_ui("menu_move")
	_apply_native_options()
func _native_defaults_reset() -> void:
	AudioServer.set_bus_volume_db(0, 0.0)
	AudioServer.set_bus_mute(0, false)
func _apply_native_options() -> void:
	audio.apply_options(int(options.values["bgm_volume"]), int(options.values["se_volume"]), int(options.values["sound"]))
	_apply_controller_scheme()
	if is_instance_valid(gameplay):
		gameplay.player.controller_layout = int(options.values["controller"])
		gameplay.player.inverse_mouse_y = int(options.values["view"]) == 0
		gameplay.player.buster_auto_lock = int(options.values["buster_lock_on"]) == 1
		gameplay.player.special_auto_lock = int(options.values["special_lock_on"]) == 1
		gameplay.player.vibration_enabled = int(options.values["vibration"]) == 0
	_apply_screen_offset(get_tree().root)
func _apply_controller_scheme() -> void:
	var profile: Dictionary = options.layout["roles"]["controller_schemes"][["A", "B", "C"][int(options.values["controller"])]]
	var fields := {"move_forward": "0x11c", "move_back": "0x11e", "turn_left": "0x120", "turn_right": "0x122", "strafe_left": "0x124", "strafe_right": "0x126", "jump": "0x12c", "fire": "0x12e", "special": "0x130", "interact": "0x132", "aim": "0x136"}
	var masks := {1: JOY_BUTTON_BACK, 2: JOY_BUTTON_LEFT_STICK, 4: JOY_BUTTON_RIGHT_STICK, 8: JOY_BUTTON_START, 16: JOY_BUTTON_DPAD_UP, 32: JOY_BUTTON_DPAD_RIGHT, 64: JOY_BUTTON_DPAD_DOWN, 128: JOY_BUTTON_DPAD_LEFT, 256: JOY_AXIS_TRIGGER_LEFT, 512: JOY_AXIS_TRIGGER_RIGHT, 1024: JOY_BUTTON_LEFT_SHOULDER, 2048: JOY_BUTTON_RIGHT_SHOULDER, 4096: JOY_BUTTON_Y, 8192: JOY_BUTTON_B, 16384: JOY_BUTTON_A, 32768: JOY_BUTTON_X}
	for action in fields:
		for event in InputMap.action_get_events(action):
			if event is InputEventJoypadButton or event is InputEventJoypadMotion: InputMap.action_erase_event(action, event)
		var mask := int(str(profile["player_field_masks"][fields[action]]).hex_to_int())
		if mask not in masks: continue
		if mask in [256, 512]:
			var event := InputEventJoypadMotion.new()
			event.axis = masks[mask]
			event.axis_value = 1.0
			InputMap.action_add_event(action, event)
		else:
			var event := InputEventJoypadButton.new()
			event.button_index = masks[mask]
			InputMap.action_add_event(action, event)
func _screen_node_added(node: Node) -> void:
	if node is CanvasLayer: _apply_screen_offset(node)
func _apply_screen_offset(node: Node) -> void:
	if node is CanvasLayer: node.offset = Vector2(float(options.values.get("screen_x", 0)), float(options.values.get("screen_y", 0))) * get_viewport().get_visible_rect().size.y / 240.0
	for child in node.get_children(): _apply_screen_offset(child)
