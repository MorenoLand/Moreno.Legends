extends Control
signal closed
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
var host: Node
var cheats := {"invulnerable": false, "free_flight": false, "no_clip": false}
var location_picker: OptionButton
var room_picker: OptionButton
var location_message: Label
var layout: Dictionary = {}
var font: Font
var surface: Control
var pages: Dictionary = {}
var active_page := "extra"
var option_list: Control
var help_label: Label
var back_row: Control
var gear: Texture2D
var elapsed := 0.0
func configure(owner: Node) -> void:
	host = owner
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	font = load("res://assets/menu/native_font.fnt") as Font
	gear = load("res://assets/menu/" + str(manifest["sprites"]["native_gear_background"]["file"])) as Texture2D
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	var native_theme := Theme.new()
	native_theme.default_font = font
	native_theme.default_font_size = 10
	theme = native_theme
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	_build_options()
	var cheat_page := _page("cheats")
	_scroll_page(cheat_page)
	cheat_page.add_theme_constant_override("separation", 3)
	for key in cheats:
		var label: String = {"invulnerable": "Invulnerable", "free_flight": "Player flight", "no_clip": "No clip"}[key]
		_toggle(cheat_page, label, cheats[key], func(value): _cheat_changed(key, value))
	_toggle(cheat_page, "Location picker", bool(host.settings.get_value("interface", "show_location_picker", true)), _picker_changed)
	_toggle(cheat_page, "Flutter Fly", host.flutter_fly_anytime, func(value): host.flutter_fly_anytime = value)
	_toggle(cheat_page, "Debug achievements", host.debug_achievements, func(value): host.debug_achievements = value)
	_button(cheat_page, "Locations", func(): open_page("locations"); focus_first())
	var controls := Label.new()
	controls.text = "Flight: Space up / C down"
	cheat_page.add_child(controls)
	_button(cheat_page, "Refill health", func():
		if is_instance_valid(host.gameplay): host.gameplay.player.refill_health())
	_button(cheat_page, "Respawn", func():
		if is_instance_valid(host.gameplay): host.gameplay.player.reset_at(host.gameplay.spawn_position))
	var places := _page("locations")
	_label(places, "Main area")
	location_picker = OptionButton.new()
	_style_picker(location_picker)
	places.add_child(location_picker)
	for location: Dictionary in host.locations: location_picker.add_item(str(location["name"]))
	_label(places, "Subarea")
	room_picker = OptionButton.new()
	_style_picker(room_picker)
	places.add_child(room_picker)
	location_picker.item_selected.connect(_location_selected)
	_location_selected(0)
	_button(places, "Load room", _load_room)
	location_message = Label.new()
	location_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	places.add_child(location_message)
	var back := VBoxContainer.new()
	back.position = Vector2(105, 211)
	back.size = Vector2(110, 16)
	surface.add_child(back)
	_button(back, "Back", func(): self.back())
	back_row = back
	resized.connect(_layout)
	_layout()
	open_page("extra")
func _scroll_page(page: VBoxContainer) -> void:
	var wrapper := ScrollContainer.new(); wrapper.position = page.position; wrapper.size = page.size; wrapper.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; wrapper.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER; wrapper.follow_focus = true; surface.add_child(wrapper); page.reparent(wrapper); page.size_flags_horizontal = Control.SIZE_EXPAND_FILL; page.set_meta("scroll_wrapper", wrapper)
	# Native-style scrollbar (same track/thumb as the options list) drawn beside the hidden default one.
	var bar := Control.new(); bar.mouse_filter = Control.MOUSE_FILTER_IGNORE; bar.position = wrapper.position + Vector2(wrapper.size.x + 3.0, 0.0); bar.size = Vector2(5.0, wrapper.size.y); wrapper.add_sibling(bar)
	bar.draw.connect(func() -> void:
		var maximum := maxf(page.size.y - wrapper.size.y, 0.0)
		if not wrapper.visible or maximum <= 0.0: return
		var track := Rect2(1.0, 1.0, 3.0, bar.size.y - 2.0)
		bar.draw_rect(track.grow(1.0), Color(0.16, 0.16, 0.23)); bar.draw_rect(track.grow(1.0), Color(0.76, 0.79, 0.69, 0.7), false, 1.0)
		var thumb := maxf(8.0, track.size.y * wrapper.size.y / page.size.y)
		bar.draw_rect(Rect2(track.position.x, track.position.y + (track.size.y - thumb) * float(wrapper.scroll_vertical) / maximum, track.size.x, thumb), Color(0.76, 0.79, 0.69)))
	wrapper.get_v_scroll_bar().value_changed.connect(func(_value: float) -> void: bar.queue_redraw())
	wrapper.visibility_changed.connect(bar.queue_redraw); page.resized.connect(bar.queue_redraw)
func _build_options() -> void:
	option_list = preload("res://scripts/ui/menus/options_list.gd").new()
	option_list.position = Vector2(38, 59)
	option_list.size = Vector2(244, 104)
	surface.add_child(option_list)
	option_list.configure(font)
	option_list.sound.connect(func(sound_name: String): host.audio.play_ui(sound_name))
	pages["extra"] = option_list
	help_label = Label.new()
	help_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	help_label.add_theme_font_override("font", font)
	help_label.add_theme_font_size_override("font_size", 10)
	help_label.position = Vector2(44, 178)
	help_label.size = Vector2(232, 24)
	help_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	help_label.clip_text = true
	surface.add_child(help_label)
	option_list.help_changed.connect(func(text: String): help_label.text = text)
	var rows: Array = [{"kind": "heading", "label": "Game"}]
	for entry: Array in [["controller", "Controller", ["A", "B", "C"], "Select the controller layout."], ["view", "Camera direction", ["Reverse", "Normal"], "Select the camera direction."], ["buster_lock_on", "Buster lock-on", ["Manual", "Auto"], "Select how the Buster locks on."], ["special_lock_on", "Special weapon lock-on", ["Manual", "Auto"], "Select how special weapons lock on."], ["vibration", "Vibration", ["On", "Off"], "Turn vibration on or off."], ["sound", "Sound", ["Stereo", "Monaural"], "Select the sound output."]]:
		var key := str(entry[0])
		rows.append({"kind": "choice", "label": entry[1], "choices": entry[2], "help": entry[3], "silent": true, "get": func(): return int(host.options.values[key]), "set": func(value): host.options._set_value(key, value)})
	rows.append({"kind": "heading", "label": "Sound"})
	for entry: Array in [["bgm_volume", "BGM volume", "Adjust the music volume."], ["se_volume", "Sound effects volume", "Adjust the sound effects volume."]]:
		var key := str(entry[0])
		rows.append({"kind": "range", "label": entry[1], "min": 0, "max": 127, "step": 4, "help": entry[2], "silent": true, "get": func(): return int(host.options.values[key]), "set": func(value): host.options._set_value(key, value)})
	rows.append({"kind": "heading", "label": "Display"})
	for entry: Array in [["screen_x", "Screen position X", -12, 12, "Shift the screen horizontally."], ["screen_y", "Screen position Y", 0, 12, "Shift the screen vertically."]]:
		var key := str(entry[0])
		rows.append({"kind": "range", "label": entry[1], "min": entry[2], "max": entry[3], "step": 1, "help": entry[4], "silent": true, "get": func(): return int(host.options.values[key]), "set": func(value): host.options._set_value(key, value)})
	rows.append({"kind": "range", "label": "Camera FOV", "min": 45, "max": 100, "step": 1, "help": "Adjust the field of view.", "get": func(): return int(host.settings.get_value("camera", "fov", 65)), "set": func(value): _fov_changed(float(value))})
	rows.append({"kind": "choice", "label": "Fullscreen", "choices": ["Off", "On"], "help": "Switch between windowed and fullscreen.", "get": func(): return int(DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN), "set": func(value): DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if value == 1 else DisplayServer.WINDOW_MODE_WINDOWED)})
	rows.append({"kind": "heading", "label": "Controls"})
	rows.append({"kind": "range", "label": "Mouse sensitivity", "min": 0.0005, "max": 0.01, "step": 0.0005, "float": true, "scale": 10000.0, "format": "%d", "help": "Adjust the mouse look speed.", "get": func(): return float(host.settings.get_value("controls", "mouse_sensitivity", 0.003)), "set": func(value): host._sensitivity_changed(float(value))})
	rows.append({"kind": "heading", "label": "Online"})
	rows.append({"kind": "choice", "label": "Discord status", "choices": ["On", "Off"], "help": "Show what you are playing on Discord.", "get": func(): return 0 if DiscordPresence.enabled else 1, "set": func(value): _discord_changed(value == 0)})
	rows.append({"kind": "heading", "label": ""})
	rows.append({"kind": "action", "label": "Restore defaults", "help": "Restore all settings to their defaults.", "do": func(): host.options.selected_row = 7; host.options._activate_row(); sync_game_options()})
	rows.append({"kind": "action", "label": "Back", "cancel": true, "help": "Return to the previous menu.", "do": func(): self.back()})
	option_list.set_rows(rows)
func sync_game_options() -> void:
	if option_list != null: option_list.queue_redraw()
func _page(key: String) -> VBoxContainer:
	var page := VBoxContainer.new()
	page.position = Vector2(43, 64)
	page.size = Vector2(234, 130)
	page.add_theme_constant_override("separation", 6)
	surface.add_child(page)
	pages[key] = page
	return page
func open_page(key: String) -> void:
	if not pages.has(key): return
	active_page = key
	if key == "extra": sync_game_options()
	for page in pages:
		pages[page].visible = page == key
		if pages[page].has_meta("scroll_wrapper"): pages[page].get_meta("scroll_wrapper").visible = page == key
	if key == "locations" and is_instance_valid(host.gameplay):
		var stage := str(host.gameplay.manifest_path.get_base_dir().get_file())
		for index in range(host.locations.size()):
			if str(host.locations[index]["stage"]) == stage: location_picker.select(index); _location_selected(index); break
		var area: int = int(host.gameplay.areas[host.gameplay.area_picker.selected]["index"])
		for index in range(room_picker.item_count):
			if room_picker.get_item_id(index) == area: room_picker.select(index); break
	help_label.visible = key == "extra"
	back_row.visible = key != "extra"
	queue_redraw()
func back() -> void:
	if active_page == "locations": open_page("cheats"); focus_first()
	else: closed.emit()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide()
	await FRAME.exit(self, layout, context)
func focus_first() -> void:
	if not is_visible_in_tree(): return
	if active_page == "extra": option_list.grab_focus(); return
	for child in pages[active_page].get_children():
		if child is BaseButton or child is Slider: child.grab_focus(); return
func _label(parent: Control, text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 10)
	parent.add_child(label)
	return label
func _style_picker(picker: OptionButton) -> void:
	picker.custom_minimum_size.y = 18
	picker.fit_to_longest_item = false
	picker.clip_text = true
	picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_CHAR
	picker.add_theme_font_size_override("font_size", 10)
	for state in ["normal", "hover", "pressed", "focus"]: picker.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	var popup := picker.get_popup()
	popup.about_to_popup.connect(_limit_picker_popup.bind(picker))
	popup.add_theme_font_override("font", font)
	popup.add_theme_font_size_override("font_size", 10)
	popup.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color(0.16, 0.16, 0.23)
	panel.border_color = Color(0.76, 0.79, 0.69)
	panel.set_border_width_all(1)
	popup.add_theme_stylebox_override("panel", panel)
func _limit_picker_popup(picker: OptionButton) -> void:
	picker.get_popup().max_size = Vector2i(roundi(picker.size.x * picker.get_global_transform_with_canvas().get_scale().x), roundi(size.y * 0.5))
	for index in range(picker.item_count): picker.get_popup().set_item_tooltip(index, picker.get_item_text(index))
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor := size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	if not is_instance_valid(host.gameplay):
		var phase: int = (int(elapsed * 30.0) >> 1) & 63
		draw_texture_rect(gear, Rect2(Vector2(-offset.x / factor, 0) + Vector2(phase - 80, phase - 80), Vector2(size.x / factor, 240) + Vector2(160, 160)), true)
	FRAME.draw(self, layout, "header", Rect2(34, 25, 252, 23))
	if active_page == "extra": FRAME.draw(self, layout, "selector", Rect2(34, 54, 252, 114)); FRAME.draw(self, layout, "prompt", Rect2(34, 174, 252, 32))
	else: FRAME.draw(self, layout, "selector", Rect2(34, 57, 252, 145))
	if FRAME.content_visible(self): draw_string(font, Vector2(44, 31 + font.get_ascent(12)), "Options" if active_page == "extra" else active_page.capitalize(), HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
func _location_selected(index: int) -> void:
	room_picker.clear()
	if index < 0 or index >= host.locations.size(): return
	for area: Dictionary in host.locations[index]["areas"]: room_picker.add_item(str(area["name"]), int(area["index"]))
func _load_room() -> void:
	set_location_message("")
	if location_picker.selected < 0 or room_picker.selected < 0: return
	var stage := str(host.locations[location_picker.selected]["stage"])
	host._load_location(stage, room_picker.get_selected_id())
func set_location_message(text: String) -> void:
	if location_message != null: location_message.text = text
func _toggle(parent: Control, caption: String, value: bool, action: Callable) -> void:
	var button := Button.new()
	button.toggle_mode = true
	button.text = caption + ": " + ("ON" if value else "OFF")
	button.button_pressed = value
	button.toggled.connect(action)
	button.toggled.connect(func(current): button.text = caption + ": " + ("ON" if current else "OFF"))
	parent.add_child(button)
	_style_button(button)
func _button(parent: Control, caption: String, action: Callable) -> void:
	var button := Button.new()
	button.text = caption
	button.set_meta("cancel_action", caption == "Back")
	button.pressed.connect(action)
	parent.add_child(button)
	_style_button(button)
func _style_button(button: Button) -> void:
	button.custom_minimum_size.y = 14
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.add_theme_font_size_override("font_size", 10)
	button.add_theme_color_override("font_color", Color(0.72, 0.68, 0.52))
	button.add_theme_color_override("font_focus_color", Color.WHITE)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	for state in ["normal", "hover", "pressed", "focus"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	button.mouse_entered.connect(button.grab_focus)
	button.focus_entered.connect(func(): host.audio.play_ui("menu_move"))
	button.pressed.connect(func(): host.audio.play_ui("menu_cancel" if button.get_meta("cancel_action", false) else "menu_confirm"))
func _picker_changed(value: bool) -> void:
	host.settings.set_value("interface", "show_location_picker", value)
	host.settings.save("user://settings.cfg")
	if is_instance_valid(host.gameplay): host.gameplay.set_location_picker_visible(value)
func _cheat_changed(key: String, value: bool) -> void:
	cheats[key] = value
	apply_player()
func _discord_changed(value: bool) -> void:
	host.settings.set_value("interface", "discord_status", value)
	host.settings.save("user://settings.cfg")
	DiscordPresence.set_enabled(value)
func _fov_changed(value: float) -> void:
	host.settings.set_value("camera", "fov", value)
	host.settings.save("user://settings.cfg")
	if is_instance_valid(host.gameplay): host.gameplay.player.camera.fov = value
func apply_player() -> void:
	if not is_instance_valid(host.gameplay): return
	for key in cheats: host.gameplay.player.set(key, cheats[key])
	host.gameplay.player.camera.fov = float(host.settings.get_value("camera", "fov", 65))
func _process(delta: float) -> void:
	elapsed += delta
	if visible and not is_instance_valid(host.gameplay): queue_redraw()
