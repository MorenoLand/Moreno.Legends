extends Control
signal selected(action: String)
signal moved
signal opened
signal press_started
signal engine_scene_requested(stage: String)
var manifest: Dictionary = {}
var logo: TextureRect
var cursor: TextureRect
var buttons: Array[TextureButton] = []
var background: TextureRect
var selection := 0
var phase := "logo_in"
var fade := 0
var logo_hold := 180
var idle_counter := 512
var native_ticks := 0.0
var prompt: TextureRect
var copyright: TextureRect
var clear: ColorRect
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if not data is Dictionary: return
	manifest = data
	logo_hold = int(manifest["startup_logo_phase"]["hold_counter_initial"])
	clear = ColorRect.new()
	clear.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	clear.color = Color.BLACK
	clear.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(clear)
	background = TextureRect.new()
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_SCALE
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if manifest.get("native_background", {}).has("file"): background.texture = load("res://assets/menu/" + str(manifest["native_background"]["file"])) as Texture2D
	add_child(background)
	logo = TextureRect.new()
	logo.texture = _texture("title_logo")
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(logo)
	prompt = TextureRect.new()
	prompt.texture = _texture("title_press_start")
	prompt.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	prompt.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(prompt)
	copyright = TextureRect.new()
	copyright.texture = _texture("title_copyright")
	copyright.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	copyright.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(copyright)
	for action: String in manifest["title_reference_layout"]["entry_order"]:
		var button := TextureButton.new()
		button.set_meta("action", action)
		button.texture_normal = _button_texture(action, false)
		button.ignore_texture_size = true
		button.stretch_mode = TextureButton.STRETCH_SCALE
		button.pressed.connect(func(): selected.emit(action))
		button.focus_entered.connect(func(): _point(button))
		button.mouse_entered.connect(func(): button.grab_focus())
		add_child(button)
		buttons.append(button)
	for index in range(buttons.size()):
		buttons[index].focus_neighbor_top = buttons[index].get_path_to(buttons[posmod(index - 1, buttons.size())])
		buttons[index].focus_neighbor_left = buttons[index].focus_neighbor_top
		buttons[index].focus_neighbor_bottom = buttons[index].get_path_to(buttons[(index + 1) % buttons.size()])
		buttons[index].focus_neighbor_right = buttons[index].focus_neighbor_bottom
	cursor = TextureRect.new()
	cursor.texture = _texture("title_cursor")
	cursor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	cursor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(cursor)
	resized.connect(_layout)
	_apply_phase()
	_layout()
func _texture(key: String) -> Texture2D:
	var entry: Dictionary = manifest["sprites"].get(key, {})
	return load("res://assets/menu/" + str(entry["file"])) as Texture2D if entry.has("file") else null
func _button_texture(action: String, selected_state: bool) -> Texture2D:
	if action == "tutorial": return _texture("title_tutorial_tutorial_selected" if selected_state else "title_tutorial_tutorial")
	for entry: Dictionary in manifest["title_entries"]:
		if str(entry["role"]) == action: return _texture(str(entry["selected_sprite" if selected_state else "normal_sprite"]))
	return null
func _layout() -> void:
	if logo == null: return
	var layout: Dictionary = manifest["title_reference_layout"]
	var factor := size.y / float(layout["viewport"][1])
	var offset := Vector2((size.x - float(layout["viewport"][0]) * factor) * 0.5, 0)
	_place(logo, manifest["startup_logo_phase"].get("rect", [48, 192, 544, 96]) if phase.begins_with("logo") else layout["logo_rect"], offset, factor)
	_place(prompt, manifest["press_start_phase"]["prompt_rect"], offset, factor)
	_place(copyright, manifest["press_start_phase"]["copyright_rect"], offset, factor)
	for index in range(buttons.size()): _place(buttons[index], layout["button_rects"][index], offset, factor)
	if cursor != null:
		_place(cursor, layout["cursor_rect"], offset, factor)
		for button in buttons:
			if button.has_focus(): _point(button)
func _place(node: Control, coordinates: Array, offset: Vector2, factor: float) -> void:
	node.position = offset + Vector2(float(coordinates[0]), float(coordinates[1])) * factor
	node.size = Vector2(float(coordinates[2]), float(coordinates[3])) * factor
func _point(button: TextureButton) -> void:
	var index := buttons.find(button)
	if index != selection:
		selection = index
		moved.emit()
	for entry in buttons:
		var action := str(entry.get_meta("action"))
		entry.texture_normal = _button_texture(action, entry == button)
	if cursor != null: cursor.position.y = button.position.y + (button.size.y - cursor.size.y) * 0.5
func focus_first() -> void:
	if phase == "menu" and not buttons.is_empty(): buttons[selection].grab_focus()
func _physics_process(delta: float) -> void:
	if not visible or manifest.is_empty(): return
	native_ticks += delta
	while native_ticks >= 1.0 / 30.0:
		native_ticks -= 1.0 / 30.0
		match phase:
			"logo_in":
				fade = mini(fade + int(manifest["startup_logo_phase"]["fade_step"]), int(manifest["startup_logo_phase"]["fade_max"]))
				if fade == int(manifest["startup_logo_phase"]["fade_max"]): phase = "logo_hold"
			"logo_hold":
				logo_hold -= 1
				if logo_hold < 0: _finish_logo()
			"press_in":
				fade = mini(fade + int(manifest["press_start_phase"]["fade_step"]), int(manifest["press_start_phase"]["fade_max"]))
				if fade == int(manifest["press_start_phase"]["fade_max"]): phase = "press"
			"press":
				idle_counter -= 1
				if idle_counter < 0:
					idle_counter = int(manifest["press_start_phase"]["idle_updates"])
			"menu":
				if cursor != null:
					var factor := size.y / 480.0
					cursor.position.x = (size.x - 640.0 * factor) * 0.5 + (172.0 + sin(float(idle_counter << 8) * TAU / 4096.0) * 4.0) * factor
					idle_counter += 1
		_apply_phase()
func show_press_start() -> void:
	phase = "press_in"
	fade = 0
	idle_counter = int(manifest["press_start_phase"]["idle_updates"])
	_apply_phase()
	_layout()
	press_started.emit()
func _finish_logo() -> void:
	phase = "opening"
	engine_scene_requested.emit("ST02")
func _open_menu() -> void:
	phase = "menu"
	fade = 128
	idle_counter = 0
	_apply_phase()
	_layout()
	focus_first()
	opened.emit()
func _apply_phase() -> void:
	var startup := phase.begins_with("logo")
	clear.color = Color(float(fade) / 128.0, float(fade) / 128.0, float(fade) / 128.0) if startup else Color.BLACK
	background.visible = not startup
	logo.texture = _texture("startup_capcom" if startup else "title_logo")
	logo.modulate = Color(float(fade) / 128.0, float(fade) / 128.0, float(fade) / 128.0)
	background.modulate = logo.modulate
	prompt.visible = phase == "press_in" or (phase == "press" and (idle_counter & 32) != 0)
	prompt.modulate = logo.modulate
	copyright.visible = phase in ["press_in", "press"]
	copyright.modulate = logo.modulate
	for button in buttons:
		button.visible = phase == "menu"
		button.focus_mode = Control.FOCUS_ALL if phase == "menu" else Control.FOCUS_NONE
	if cursor != null: cursor.visible = phase == "menu"
func _gui_input(event: InputEvent) -> void:
	if not visible: return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if phase == "logo_hold": _finish_logo()
		elif phase in ["press", "press_in"]: _open_menu()
		else: return
		accept_event()
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	var start: bool = event is InputEventJoypadButton and event.pressed and event.button_index == JOY_BUTTON_START
	if not start and not event.is_action_pressed("ui_accept"): return
	if phase == "logo_hold": _finish_logo()
	elif phase in ["press", "press_in"]: _open_menu()
	else: return
	get_viewport().set_input_as_handled()
