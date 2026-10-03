extends Node
signal data_save_menu_finished(saved: bool)
var gameplay: Node3D
var debug_overlay: CanvasLayer
var overlay: Control
var pages: Dictionary = {}
var status: Label
var options: Control
var options_return := "main"
var settings := ConfigFile.new()
var title: Control
var audio: Node
var custom: Control
var status_menu: Control
var pause_return := ""
var saves := preload("res://scripts/state/save_store.gd").new()
var save_menu: Control
var save_feedback: Label
var session_loading := false
var data_save_menu_active := false
var opening: Control
var opening_loading := false
var locations: Array = []
var menu_transitioning := false
var achievements := ConfigFile.new()
var achievement_catalog: Dictionary = {}
var achievement_notice: Control
var achievement_menu: Control
var inventory_menu: Control
var map_menu: Control
var equipment_menu: Control
var special_last := 0
var info_return := "pause"
var debug_achievements := false
var flutter_fly_anytime := false
var error_dialogue: Control
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	session_loading = true
	var menu_keys := {"ui_up": KEY_W, "ui_down": KEY_S, "ui_left": KEY_A, "ui_right": KEY_D}
	for action in menu_keys:
		var key := InputEventKey.new()
		key.physical_keycode = menu_keys[action]
		if not InputMap.action_has_event(action, key): InputMap.action_add_event(action, key)
	settings.load("user://settings.cfg")
	achievements.load("user://achievements.cfg")
	var achievement_source: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/achievements/catalog.json")) if FileAccess.file_exists("res://assets/achievements/catalog.json") else null
	if achievement_source is Dictionary:
		for definition: Dictionary in achievement_source.get("achievements", []): achievement_catalog[str(int(definition["id"]))] = definition
	if not InputMap.has_action("status_menu"): InputMap.add_action("status_menu")
	var status_key := InputEventKey.new()
	status_key.physical_keycode = KEY_Z
	if not InputMap.action_has_event("status_menu", status_key): InputMap.action_add_event("status_menu", status_key)
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
	achievement_notice = preload("res://scripts/ui/hud/achievement_notice.gd").new()
	overlay.add_child(achievement_notice)
	var pause_menu := preload("res://scripts/ui/menus/pause_menu.gd").new()
	overlay.add_child(pause_menu)
	pause_menu.configure(); pause_menu.host = self
	pages["pause"] = pause_menu
	options = preload("res://scripts/ui/menus/options_menu.gd").new()
	overlay.add_child(options)
	options.configure(settings)
	options.closed.connect(func(): _show(options_return))
	options.changed.connect(_native_option_changed)
	options.defaults_reset.connect(_native_defaults_reset)
	pages["options"] = options
	save_menu = preload("res://scripts/ui/menus/save_menu.gd").new()
	overlay.add_child(save_menu)
	save_menu.configure(self)
	save_menu.selected.connect(_load_save)
	save_menu.closed.connect(_close_save_menu)
	pages["saves"] = save_menu
	custom = preload("res://scripts/ui/menus/custom_menu.gd").new()
	overlay.add_child(custom)
	custom.configure(self)
	custom.closed.connect(_close_custom)
	pages["custom"] = custom
	status_menu = preload("res://scripts/ui/status/status_menu.gd").new()
	overlay.add_child(status_menu)
	status_menu.configure(self)
	status_menu.options_requested.connect(func(): _options("status"))
	status_menu.closed.connect(_resume)
	pages["status"] = status_menu
	achievement_menu = preload("res://scripts/ui/menus/achievement_menu.gd").new()
	overlay.add_child(achievement_menu)
	achievement_menu.configure(self)
	achievement_menu.closed.connect(func(): audio.play_ui("menu_cancel"); _show("pause"))
	pages["achievements"] = achievement_menu
	inventory_menu = preload("res://scripts/ui/menus/inventory_menu.gd").new(); overlay.add_child(inventory_menu); inventory_menu.configure(self); inventory_menu.closed.connect(_close_info); pages["inventory"] = inventory_menu
	equipment_menu = preload("res://scripts/ui/menus/equipment_menu.gd").new(); overlay.add_child(equipment_menu); equipment_menu.configure(self); equipment_menu.closed.connect(_close_info); pages["equipment"] = equipment_menu
	map_menu = preload("res://scripts/ui/menus/map_menu.gd").new(); overlay.add_child(map_menu); map_menu.configure(self); map_menu.closed.connect(_close_info); pages["map"] = map_menu
	for page_name: String in ["inventory", "equipment", "map"]: pages[page_name].page_requested.connect(_cycle_info)
	title = preload("res://scripts/ui/menus/title_menu.gd").new()
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
	status.offset_top = -64
	status.offset_bottom = -12
	status.offset_left = 24
	status.offset_right = -24
	status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	status.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	status.add_theme_font_size_override("font_size", 24)
	status.add_theme_color_override("font_color", Color.WHITE)
	status.add_theme_color_override("font_outline_color", Color.BLACK)
	status.add_theme_constant_override("outline_size", 4)
	status.add_theme_color_override("font_shadow_color", Color.BLACK)
	status.add_theme_constant_override("shadow_offset_x", 2)
	status.add_theme_constant_override("shadow_offset_y", 2)
	title.add_child(status)
	var pause_page: Control = pages["pause"].get_meta("content")
	_button(pause_page, "Resume", _resume)
	_button(pause_page, "Save Game", _save_game)
	_button(pause_page, "Inventory", func(): _open_info("inventory", "pause"))
	_button(pause_page, "Equipment", func(): _open_info("equipment", "pause"))
	_button(pause_page, "Map", func(): _open_info("map", "pause"))
	_button(pause_page, "Options", func(): _options("pause"))
	_button(pause_page, "Achievements", func(): achievement_menu.refresh(); _show("achievements"))
	_button(pause_page, "Cheats", func(): _open_custom("cheats"))
	_button(pause_page, "Main Menu", _confirm_main_menu)
	_button(pause_page, "Quit to Desktop", func(): _show("quit_confirm"))
	var confirmation := preload("res://scripts/ui/menus/confirmation_menu.gd").new(); overlay.add_child(confirmation); confirmation.configure("Return to Title Screen?"); confirmation.confirmed.connect(func(): audio.play_ui("menu_confirm"); _main_menu()); confirmation.cancelled.connect(func(): audio.play_ui("menu_cancel"); _show("pause")); confirmation.moved.connect(func(): audio.play_ui("menu_move")); pages["title_confirm"] = confirmation
	var quit_confirmation := preload("res://scripts/ui/menus/confirmation_menu.gd").new(); overlay.add_child(quit_confirmation); quit_confirmation.configure("Quit to Desktop?"); quit_confirmation.confirmed.connect(func(): audio.play_ui("menu_confirm"); get_tree().quit()); quit_confirmation.cancelled.connect(func(): audio.play_ui("menu_cancel"); _show("pause")); quit_confirmation.moved.connect(func(): audio.play_ui("menu_move")); pages["quit_confirm"] = quit_confirmation
	save_feedback = Label.new()
	save_feedback.hide()
	save_feedback.add_theme_font_size_override("font_size", 9)
	save_feedback.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	save_feedback.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	pause_page.add_child(save_feedback)
	_apply_native_options()
	get_tree().node_added.connect(_screen_node_added)
	for page: Control in pages.values(): page.hide()
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
	var pause_cursor: bool = pages.has("pause") and parent == pages["pause"].content
	if pause_cursor:
		button.focus_entered.connect(func(): pages["pause"].select_button(button); audio.play_ui("menu_move"))
		button.mouse_entered.connect(button.grab_focus)
		return
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
	if menu_transitioning: return
	menu_transitioning = true
	var context := "gameplay" if is_instance_valid(gameplay) else "title"
	for page: Control in pages.values():
		if page.visible and page != pages[name] and page.has_method("animate_exit"): await page.animate_exit(context)
	overlay.visible = true; _set_pickers(name == "main")
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	for key in pages: pages[key].visible = key == name
	if pages[name].has_method("animate_enter"): await pages[name].animate_enter(context)
	menu_transitioning = false
	if title != null: title.set_process(name == "main")
	if name == "main": title.focus_first()
	if name == "saves": save_menu.focus_first()
	if name == "pause": pages["pause"].call_deferred("focus_first")
	if name == "pause":
		for child in pages["pause"].content.get_children():
			if child is Button and child.text == "Save Game": child.disabled = not is_instance_valid(gameplay)
	if name == "custom": custom.call_deferred("focus_first")
	if name == "status": status_menu.refresh()
	var content: Control = pages[name].get_meta("content", pages[name])
	for child in content.get_children():
		if child is Button:
			child.grab_focus()
			break
func _new_game() -> void:
	await _start_session({}, "ST39", 0, {"native_save_byte14": 0, "native_save_byte16": 1, "native_save_word40": 0, "native_save_byte44": 1, "native_save_byte45": 1, "event_flags": {}})
func _show_error(message: String) -> void:
	status.hide()
	if not is_instance_valid(error_dialogue):
		error_dialogue = preload("res://scripts/ui/dialogue/dialogue_box.gd").new(); error_dialogue.process_mode = Node.PROCESS_MODE_ALWAYS; overlay.add_child(error_dialogue); error_dialogue.z_index = 200; error_dialogue.mouse_filter = Control.MOUSE_FILTER_STOP; error_dialogue.typing_sound_requested.connect(audio.play_sound); error_dialogue.menu_sound_requested.connect(audio.play_ui)
	if error_dialogue.active: return
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null: focus.release_focus()
	await error_dialogue.present_message("MENU", {"index": -1, "text": message})
	if is_instance_valid(focus) and focus.is_visible_in_tree(): focus.grab_focus()
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
func _start_session(state: Dictionary, stage: String = "ST04", area: int = 0, context: Dictionary = {}, load_feedback: bool = false, parked_override: Dictionary = {}, carried: Dictionary = {}) -> void:
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
		return
	var stage_path := "res://assets/levels/" + stage + "/manifest.json"
	if not FileAccess.file_exists(stage_path) or not ResourceLoader.exists("res://assets/player/megaman.glb"):
		if pages["saves"].visible: save_menu.set_message("Prepare your disc assets before loading.")
		else:
			status.text = "Prepare your disc assets with tools/assets.py before starting."
			status.show()
		session_loading = false
		return
	var stage_manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(stage_path))
	var area_index := -1
	if stage_manifest is Dictionary:
		var entries: Array = stage_manifest.get("areas", [])
		for index in range(entries.size()):
			if int(entries[index]["index"]) == area: area_index = index; break
	var runner_area := -1
	if area_index < 0 and not stage_manifest.get("areas", []).is_empty() and preload("res://scripts/world/actors/native_props.gd").runner_owned(stage): runner_area = area; area_index = 0
	if area_index < 0:
		if pages["saves"].visible: save_menu.set_message("This area's native ID is not available.")
		elif custom.visible: custom.set_location_message("This area's native ID is not available.")
		session_loading = false
		return
	var weapon_policy: Variant = stage_manifest.get("native_combat_policy", null)
	var buster_allowed := bool(weapon_policy.get("buster_allowed", true)) if weapon_policy is Dictionary else true
	var player_path := "res://assets/player/megaman_civilian.glb" if stage in ["ST04", "ST05", "ST06", "ST07"] else ("res://assets/player/megaman.glb" if buster_allowed else "res://assets/player/megaman_normal.glb")
	var gameplay_script := ResourceLoader.load("res://scripts/world/core/gameplay.gd", "GDScript") as GDScript
	if gameplay_script == null or not gameplay_script.can_instantiate() and (gameplay_script.reload() != OK or not gameplay_script.can_instantiate()):
		session_loading = false; await _show_error("The gameplay script could not be loaded."); return
	var scene: PackedScene = await _threaded_scene("res://scenes/gameplay.tscn")
	var player_scene: PackedScene = await _threaded_scene(player_path) if scene != null else null
	if scene == null or player_scene == null:
		session_loading = false
		await _show_error("The game could not be opened.")
		return
	await get_tree().process_frame
	var previous := gameplay
	var previous_paused := get_tree().paused
	if is_instance_valid(previous): previous.process_mode = Node.PROCESS_MODE_DISABLED
	get_tree().paused = false
	var candidate := scene.instantiate() as Node3D
	if candidate == null or candidate.get_script() == null or not (candidate.get_script() as GDScript).can_instantiate():
		if candidate != null: candidate.queue_free()
		if is_instance_valid(previous): previous.process_mode = Node.PROCESS_MODE_PAUSABLE
		get_tree().paused = previous_paused; session_loading = false
		await _show_error("The gameplay script could not be loaded.")
		push_error("Failed to compile res://scripts/world/core/gameplay.gd or one of its dependencies")
		return
	candidate.manifest_path = stage_path
	candidate.initial_area = area_index
	if runner_area >= 0: candidate.set_meta("runner_start_area", runner_area)
	candidate.entry_route = state.get("entry_route", {}).duplicate(true)
	var entry_fade_code := int(candidate.entry_route.get("native_entry_fade", 0x02))
	candidate.parked_location = state.get("parked_location", parked_override).duplicate(true)
	candidate.native_context = state.get("native_context", context if not context.is_empty() else {"native_save_byte14": 0, "native_save_byte16": 0, "native_save_word40": 0, "native_save_byte44": 1, "native_save_byte45": 1, "event_flags": {}}).duplicate(true)
	preload("res://scripts/world/core/native_region.gd").enter_stage(candidate.native_context, stage)
	candidate.initial_player_state = state.get("player", {}).duplicate(true) if candidate.entry_route.is_empty() else {}
	candidate.audio_preparing = true
	candidate.process_mode = Node.PROCESS_MODE_PAUSABLE
	candidate.hide()
	candidate.get_node("HUD").hide()
	add_child(candidate)
	if candidate.audio != null and candidate.audio.music != null: candidate.audio.music.stream_paused = true
	var success: bool = candidate.playable if candidate.preparation_finished else await candidate.prepared
	if success and not state.is_empty(): success = await candidate.restore_state(state)
	if success and not carried.is_empty(): candidate.apply_carry(carried)
	if success: candidate.entry_route = {}; candidate.initial_player_state = {}
	var docked_hull: Node3D = await preload("res://scripts/world/flutter/flutter_dock.gd").ensure(candidate) if success else null
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
		return
	if load_feedback: audio.play_sound(0xEF); await save_menu.finish_load()
	if is_instance_valid(previous) and previous.audio != null and candidate.audio != null: candidate.audio.adopt_music(previous.audio.capture_music())
	if entry_fade_code != 0xFF: candidate.transition_overlay.hold(entry_fade_code in [0x09, 0x0A, 0x0B, 0x0C])
	if is_instance_valid(previous):
		remove_child(previous)
		previous.queue_free()
	gameplay = candidate
	gameplay.stage_transition_requested.connect(_stage_transition)
	gameplay.location_requested.connect(_load_location)
	gameplay.achievement_earned.connect(_unlock_achievement)
	gameplay.game_over_requested.connect(_game_over)
	var achievement_blockers: Array[Control] = [pages["pause"], options, save_menu, custom, status_menu, achievement_menu, inventory_menu, equipment_menu, map_menu, gameplay.dialogue_box, gameplay.transition_overlay]; achievement_notice.configure(achievement_blockers)
	gameplay.set_meta("native_landing_active", bool(state.get("entry_route", {}).get("flutter_landing", false)))
	gameplay.show()
	gameplay.get_node("HUD").show()
	gameplay.player.mouse_sensitivity = float(settings.get_value("controls", "mouse_sensitivity", 0.003))
	_apply_native_options()
	custom.apply_player()
	gameplay.set_location_picker_visible(bool(settings.get_value("interface", "show_location_picker", true)))
	gameplay.set_minimap_visible(bool(settings.get_value("interface", "show_minimap", true)))
	gameplay.player.set_physics_process(false)
	if gameplay.audio != null: gameplay.audio.set_preparing(false)
	if is_instance_valid(opening): opening._finish(true)
	await _resume(not OS.has_feature("web"))
	if bool(state.get("entry_route", {}).get("flutter_landing", false)):
		if is_instance_valid(docked_hull) and not await preload("res://scripts/world/flutter/flutter_dock.gd").land(gameplay, docked_hull): push_error("Flutter landing sequence failed: " + gameplay.native_scenes.last_error)
		gameplay.set_meta("native_landing_active", false)
	await gameplay.transition_overlay.request(entry_fade_code)
	gameplay.player.set_physics_process(true); session_loading = false
func _game_over() -> void:
	if not is_instance_valid(gameplay): return
	var previous := gameplay
	remove_child(previous); previous.queue_free(); gameplay = null
	get_tree().paused = true
	for page in pages.values(): page.hide()
	overlay.show()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var screen := preload("res://scripts/ui/screens/game_over.gd").new()
	screen.audio = audio
	overlay.add_child(screen)
	await screen.finished
	screen.queue_free()
	_main_menu()
func _load_location(stage: String, area: int) -> void:
	var carried: Dictionary = gameplay.carry_state() if is_instance_valid(gameplay) else {}
	var context: Dictionary = gameplay.native_context.duplicate(true) if is_instance_valid(gameplay) else {}
	var parked: Dictionary = gameplay.parked_location.duplicate(true) if is_instance_valid(gameplay) else {}
	await _start_session({}, stage, area, context, false, parked, carried)
func _stage_transition(route: Dictionary) -> void:
	if session_loading or not is_instance_valid(gameplay): return
	var previous := gameplay
	var state: Dictionary = previous.save_state(true)
	if state.is_empty(): previous.cancel_stage_transition(); return
	var stage := str(route["destination_stage"]); var area := int(route["destination_area"])
	var source_stage := str(state["stage"]); var source_area := int(state["area"])
	if route.get("parked_location", null) is Dictionary: state["parked_location"] = route["parked_location"].duplicate(true)
	elif source_stage in ["ST04", "ST05", "ST06", "ST07"] and stage not in ["ST04", "ST05", "ST06", "ST07"]:
		if str(state.get("parked_location", {}).get("stage", "")) != stage or int(state.get("parked_location", {}).get("area", -1)) != area: state["parked_location"] = {"stage": stage, "area": area}
	elif stage in ["ST04", "ST05", "ST06", "ST07"] and source_stage not in ["ST04", "ST05", "ST06", "ST07"] and (state.get("parked_location", {}).is_empty() or not preload("res://scripts/world/flutter/flutter_dock.gd").descriptor(source_stage).is_empty()):
		if str(state.get("parked_location", {}).get("stage", "")) != source_stage or int(state.get("parked_location", {}).get("area", -1)) != source_area: state["parked_location"] = {"stage": source_stage, "area": source_area}
	state["stage"] = stage; state["area"] = area
	state["defeated_actors"] = state.get("stage_events", {}).get(stage, []).duplicate()
	state["minimap"] = state.get("explored_stages", {}).get(stage, []).duplicate(true)
	state["entry_route"] = route.duplicate(true)
	await _start_session(state)
	if is_instance_valid(previous) and gameplay == previous: await previous.transition_overlay.request(int(route.get("native_entry_fade", 0xFF))); previous.cancel_stage_transition()
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
	if save_menu.confirming_load or save_menu.loading_display: return
	if save_menu.completion_active: save_menu.acknowledge_completion(); return
	if save_menu.save_mode:
		if not is_instance_valid(gameplay): return
		if FileAccess.file_exists(saves.directory.path_join(id + ".json")) and not await save_menu.confirm_load(true): audio.play_ui("menu_cancel"); return
		audio.play_ui("menu_confirm"); save_menu.show_loading(); session_loading = true
		await RenderingServer.frame_post_draw
		var saved_id: String = saves.write(gameplay.save_state(data_save_menu_active), id)
		session_loading = false
		if saved_id.is_empty():
			save_menu.set_message(saves.error)
			return
		save_menu.refresh(saves.entries(), true)
		audio.play_sound(0xEF)
		await save_menu.show_completion()
		if data_save_menu_active: data_save_menu_finished.emit(true); return
		_show("pause")
		return
	var data: Dictionary = saves.read(id)
	if data.is_empty():
		save_menu.set_message(saves.error)
		return
	if not await save_menu.confirm_load(): audio.play_ui("menu_cancel"); return
	audio.play_ui("menu_confirm"); save_menu.show_loading()
	await _start_session(data["state"], "ST04", 0, {}, true)
func open_data_save_menu() -> bool:
	if session_loading or not is_instance_valid(gameplay): return false
	data_save_menu_active = true; save_menu.refresh(saves.entries(), true)
	if not saves.error.is_empty(): save_menu.set_message(saves.error)
	await _show("saves")
	var saved: bool = await data_save_menu_finished
	data_save_menu_active = false
	if is_instance_valid(gameplay): await _resume()
	return saved
func _close_save_menu(play_sound := true) -> void:
	if session_loading: return
	if save_menu.confirming_load: save_menu.load_confirmed.emit(false); return
	if save_menu.completion_active: save_menu.acknowledge_completion(); return
	if play_sound: audio.play_ui("menu_cancel")
	if data_save_menu_active: data_save_menu_finished.emit(false)
	else: _show("pause" if save_menu.save_mode else "main")
func _pause() -> void:
	pause_return = ""
	if is_instance_valid(gameplay): gameplay.sync_items()
	save_feedback.text = ""
	save_feedback.hide()
	get_tree().paused = true
	_show("pause")
func _resume(capture_mouse: bool = true) -> void:
	if menu_transitioning: return
	if not is_instance_valid(gameplay):
		if pause_return == "opening" and is_instance_valid(opening):
			_show("opening")
			opening.audio.stream_paused = false
			opening.set_process(true)
		else: _show("main")
		pause_return = ""
		return
	pause_return = ""
	menu_transitioning = true
	for page: Control in pages.values():
		if page.visible and page.has_method("animate_exit"): await page.animate_exit("gameplay")
	audio.music.stop()
	gameplay.audio.music.stream_paused = false
	overlay.hide(); _set_pickers(true)
	for page in pages.values(): page.hide()
	title.set_process(false)
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if capture_mouse else Input.MOUSE_MODE_VISIBLE
	menu_transitioning = false
func _confirm_main_menu() -> void:
	if is_instance_valid(gameplay): _show("title_confirm")
	else: _main_menu()
func _main_menu() -> void:
	if is_instance_valid(opening): opening._finish(true)
	if is_instance_valid(gameplay):
		var previous := gameplay
		remove_child(previous); previous.queue_free(); gameplay = null
	get_tree().paused = true
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
	options_return = "pause" if return_page == "status" else return_page
	custom.open_page("extra"); _show("custom")
func _input(event: InputEvent) -> void:
	if is_instance_valid(error_dialogue) and error_dialogue.active: return
	if menu_transitioning: get_viewport().set_input_as_handled(); return
	if event.is_action_pressed("swap_special") and is_instance_valid(gameplay) and (pages["pause"].visible or pages["equipment"].visible): swap_special(); get_viewport().set_input_as_handled(); return
	if event.is_action_pressed("status_menu"):
		if not session_loading and not opening_loading and is_instance_valid(gameplay) and not is_instance_valid(opening):
			if pages["pause"].visible: _resume()
			else: _pause(); audio.play_ui("menu_confirm")
		get_viewport().set_input_as_handled()
		return
	for action in ["inventory_menu", "map_menu"]:
		if event.is_action_pressed(action): _info_hotkey(action.trim_suffix("_menu")); get_viewport().set_input_as_handled(); return
	if not event.is_action_pressed("debug_overlay"): return
	if not is_instance_valid(debug_overlay): debug_overlay = preload("res://scripts/ui/hud/debug_overlay.gd").new(); debug_overlay.name = "DebugOverlay"; add_child(debug_overlay); debug_overlay.configure(self)
	debug_overlay.toggle()
	get_viewport().set_input_as_handled()
func _gameplay_free() -> bool:
	return is_instance_valid(gameplay) and not is_instance_valid(opening) and gameplay.playable and not gameplay.loading and not gameplay.native_scenes.active and not (is_instance_valid(gameplay.dialogue_box) and gameplay.dialogue_box.active) and gameplay.transition_overlay.is_idle()
func special_partner() -> String:
	if not is_instance_valid(gameplay): return ""
	var player: Node = gameplay.player; var owned: Dictionary = player.inventory["special_weapons"]
	if int(player.equipped_special) != 0: return "0"
	var ids: Array = owned.keys().filter(func(id): return id != "0" and int(owned[id]) > 0)
	return str(special_last) if ids.has(str(special_last)) else str(ids[0]) if not ids.is_empty() else ""
func swap_special() -> bool:
	var target := special_partner()
	if target.is_empty(): audio.play_ui("menu_cancel"); return false
	if int(gameplay.player.equipped_special) != 0: special_last = int(gameplay.player.equipped_special)
	gameplay.player.equipped_special = int(target); audio.play_ui("menu_confirm")
	for page_name: String in ["pause", "equipment"]: pages[page_name].queue_redraw()
	return true
func _cycle_info(direction: int) -> void:
	var order := ["inventory", "equipment", "map"]; var from := order.find(order.filter(func(key): return pages[key].visible)[0])
	audio.play_ui("menu_move"); _open_info(order[posmod(from + direction, order.size())], info_return)
func _set_pickers(shown: bool) -> void:
	if not is_instance_valid(gameplay) or not gameplay.scene_ui_state.is_empty(): return
	if shown: gameplay.set_location_picker_visible(bool(settings.get_value("interface", "show_location_picker", true)))
	else: gameplay.set_location_picker_visible(false)
func _open_info(page: String, source: String) -> void:
	info_return = source; pages[page].refresh(); _show(page)
func _close_info() -> void:
	audio.play_ui("menu_cancel")
	if info_return == "pause": _show("pause")
	else: _resume()
func _info_hotkey(page: String) -> void:
	if session_loading or opening_loading or not is_instance_valid(gameplay): return
	var shown: Array = pages.keys().filter(func(key): return pages[key].visible)
	if shown.has(page): _close_info(); return
	if shown.is_empty():
		if get_tree().paused or not _gameplay_free(): return
		info_return = ""; pause_return = ""; save_feedback.hide()
	elif shown == ["pause"]: info_return = "pause"
	elif not (shown.size() == 1 and shown[0] in ["inventory", "equipment", "map"]): return
	audio.play_ui("menu_confirm"); get_tree().paused = true; _open_info(page, info_return)
func _open_custom(page: String) -> void:
	if page == "extra": _options("pause"); return
	custom.open_page(page)
	_show("custom")
func _unhandled_input(event: InputEvent) -> void:
	if is_instance_valid(error_dialogue) and error_dialogue.active: return
	if menu_transitioning: get_viewport().set_input_as_handled(); return
	if session_loading or opening_loading: return
	if is_instance_valid(opening) and not (pages["pause"].visible or custom.visible or pages["options"].visible): return
	if not event.is_action_pressed("ui_cancel"): return
	audio.play_ui("menu_cancel")
	if pages["title_confirm"].visible or pages["quit_confirm"].visible: _show("pause")
	elif custom.visible: _close_custom()
	elif status_menu.visible: status_menu.back()
	elif inventory_menu.visible or equipment_menu.visible or map_menu.visible: _close_info()
	elif pages["saves"].visible: _close_save_menu(false)
	elif pages["options"].visible: _show(options_return)
	elif pages["pause"].visible: _resume()
	elif is_instance_valid(gameplay) and not pages["main"].visible:
		if get_tree().paused: _resume()
		else: _pause()
	get_viewport().set_input_as_handled()
func _close_custom() -> void:
	if custom.active_page == "locations": custom.open_page("cheats"); custom.focus_first()
	elif custom.active_page == "extra": _show(options_return)
	else: _show("pause")
func _sensitivity_changed(value: float) -> void:
	if is_instance_valid(gameplay): gameplay.player.mouse_sensitivity = value
	settings.set_value("controls", "mouse_sensitivity", value)
	settings.save("user://settings.cfg")
func _native_option_changed(_key: String, _value: int) -> void:
	audio.play_ui("menu_move")
	_apply_native_options()
	if is_instance_valid(custom): custom.sync_game_options()
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
func achievement_badge(id: String) -> String:
	return "res://assets/achievements/" + str(achievement_catalog[id]["icon_file" if achievements.has_section_key("unlocked", id) else "locked_icon_file"]) if achievement_catalog.has(id) else ""
func debug_set_achievement(id: String, unlocked: bool) -> void:
	if not debug_achievements or not achievement_catalog.has(id): return
	if unlocked: _unlock_achievement(id, true)
	else: achievements.erase_section_key("unlocked", id); achievements.save("user://achievements.cfg")
	achievement_menu.call_deferred("refresh")
func _unlock_achievement(id: String, debug_preview: bool = false) -> void:
	if not achievement_catalog.has(id) or achievements.has_section_key("unlocked", id): return
	achievements.set_value("unlocked", id, int(Time.get_unix_time_from_system())); achievements.save("user://achievements.cfg")
	var definition: Dictionary = achievement_catalog[id]; achievement_notice.enqueue({"id": id, "title": definition["title"], "description": definition["description"], "icon": achievement_badge(id), "debug_preview": debug_preview})
