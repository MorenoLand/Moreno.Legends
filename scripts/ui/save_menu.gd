extends Control
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
signal selected(save_id: String)
signal closed
var host: Node
var manifest: Dictionary = {}
var layout: Dictionary = {}
var background: Texture2D
var font: Font
var surface: Control
var scroll: ScrollContainer
var rows: VBoxContainer
var empty: Label
var cancel: Button
var message: Label
var entries: Array = []
var buttons: Array[Button] = []
var selected_index: int = 0
var save_mode := false
var elapsed: float = 0.0
var selector_rect := Rect2(41, 112, 239, 94)
func configure(owner: Node) -> void:
	host = owner
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	manifest = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	background = load("res://assets/menu/" + str(manifest["sprites"]["native_gear_background"]["file"])) as Texture2D
	font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	scroll = ScrollContainer.new()
	scroll.position = Vector2(48, 117)
	scroll.size = Vector2(228, 61)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.follow_focus = true
	surface.add_child(scroll)
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 3)
	scroll.add_child(rows)
	empty = _label("No saved games", font, 12)
	empty.position = Vector2(48, 136)
	empty.size = Vector2(224, 18)
	empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	surface.add_child(empty)
	cancel = Button.new()
	cancel.text = "Cancel"
	cancel.position = Vector2(95, 178)
	cancel.size = Vector2(130, 16)
	cancel.add_theme_font_override("font", font)
	cancel.add_theme_font_size_override("font_size", 12)
	for state in ["normal", "hover", "pressed", "focus"]: cancel.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	cancel.pressed.connect(closed.emit)
	cancel.mouse_entered.connect(cancel.grab_focus)
	surface.add_child(cancel)
	message = _label("", font, 9)
	message.position = Vector2(41, 211)
	message.size = Vector2(239, 26)
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message.hide()
	surface.add_child(message)
	resized.connect(_layout)
	visibility_changed.connect(_visibility_changed)
	_layout()
func refresh(save_entries: Array, saving: bool = false) -> void:
	var previous_id: String = str(entries[selected_index]["id"]) if selected_index < entries.size() else ""
	for child in rows.get_children():
		rows.remove_child(child)
		child.queue_free()
	save_mode = saving
	entries = save_entries.duplicate()
	if save_mode: entries.push_front({"id": "", "name": "New Save"})
	buttons.clear()
	selected_index = 0
	set_message("")
	for index in range(entries.size()):
		var entry: Dictionary = entries[index]
		var button := Button.new()
		button.custom_minimum_size.y = 28
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.disabled = not save_mode and not str(entry.get("error", "")).is_empty()
		button.pressed.connect(_choose.bind(str(entry["id"])))
		button.focus_entered.connect(_focus_row.bind(index))
		button.mouse_entered.connect(button.grab_focus)
		rows.add_child(button)
		var content := VBoxContainer.new()
		content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		content.mouse_filter = Control.MOUSE_FILTER_IGNORE
		content.add_theme_constant_override("separation", 0)
		button.add_child(content)
		var top := HBoxContainer.new()
		top.mouse_filter = Control.MOUSE_FILTER_IGNORE
		content.add_child(top)
		var name_label := _label(("Overwrite " if save_mode and not str(entry["id"]).is_empty() else "") + str(entry["name"]), font, 12)
		name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		name_label.custom_minimum_size.x = 110
		top.add_child(name_label)
		var date_text: String = Time.get_datetime_string_from_unix_time(int(entry["saved_at"])).replace("T", " ").replace("-", " ").substr(0, 16) + " UTC" if entry.has("saved_at") else ""
		var date := _label(date_text, font, 7)
		date.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		top.add_child(date)
		var detail_text: String = "Create a new saved game" if str(entry["id"]).is_empty() else str(entry["error"]) if entry.has("error") else "HP %d of %d" % [int(entry["health"]), int(entry["max_health"])]
		var details := _label(detail_text, font, 10)
		details.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		content.add_child(details)
		button.set_meta("labels", [name_label, date, details])
		if str(entry["id"]) == previous_id: selected_index = index
		buttons.append(button)
	empty.visible = entries.is_empty()
	scroll.visible = not entries.is_empty()
	for index in range(buttons.size()):
		var previous: Button = cancel if index == 0 else buttons[index - 1]
		var next: Button = cancel if index == buttons.size() - 1 else buttons[index + 1]
		buttons[index].focus_neighbor_top = buttons[index].get_path_to(previous)
		buttons[index].focus_neighbor_bottom = buttons[index].get_path_to(next)
	if not buttons.is_empty():
		cancel.focus_neighbor_top = cancel.get_path_to(buttons[-1])
		cancel.focus_neighbor_bottom = cancel.get_path_to(buttons[0])
	else:
		cancel.focus_neighbor_top = NodePath("")
		cancel.focus_neighbor_bottom = NodePath("")
	_focus_row(selected_index)
	call_deferred("focus_first")
	queue_redraw()
func set_message(text: String) -> void:
	if message == null: return
	message.text = text
	message.visible = not text.is_empty()
func focus_first() -> void:
	if not is_visible_in_tree(): return
	if selected_index < buttons.size() and not buttons[selected_index].disabled:
		buttons[selected_index].grab_focus()
		return
	for button in buttons:
		if not button.disabled:
			button.grab_focus()
			return
	cancel.grab_focus()
func _label(text: String, face: Font, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_override("font", face)
	label.add_theme_font_size_override("font_size", font_size)
	return label
func _visibility_changed() -> void:
	if visible: call_deferred("focus_first")
func _focus_row(index: int) -> void:
	if index != selected_index and host != null: host.audio.play_ui("menu_move")
	selected_index = index
	for row in range(buttons.size()):
		for label: Label in buttons[row].get_meta("labels"): label.add_theme_color_override("font_color", Color.WHITE if row == index else Color(0.72, 0.68, 0.52))
func _choose(save_id: String) -> void:
	for entry: Dictionary in entries:
		if not save_mode and str(entry["id"]) == save_id and not str(entry.get("error", "")).is_empty():
			set_message(str(entry["error"]))
			return
	set_message("")
	selected.emit(save_id)
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	if event.is_action_pressed("ui_cancel"):
		closed.emit()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("ui_accept"):
		if cancel.has_focus() or entries.is_empty(): closed.emit()
		else: _choose(str(entries[selected_index]["id"]))
		get_viewport().set_input_as_handled()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func _process(delta: float) -> void:
	elapsed += delta
	if visible: queue_redraw()
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	var phase: int = (int(elapsed * 30.0) >> 1) & 63
	var origin := Vector2(phase - 80, phase - 80)
	draw_texture_rect(background, Rect2(Vector2(-offset.x / factor, 0) + origin, Vector2(size.x / factor, 240) + Vector2(160, 160)), true)
	_frame("header", _rect(layout["windows"]["header"]["body_rect"]))
	_frame("prompt", _rect(layout["windows"]["prompt"]["body_rect"]))
	_frame("selector", selector_rect)
	var position: Array = layout["windows"]["header"]["text_position"]
	draw_string(font, Vector2(position[0], position[1] + font.get_ascent(12)), "Save Game" if save_mode else "Load Game", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	position = layout["windows"]["prompt"]["text_position"]
	draw_string(font, Vector2(position[0], position[1] + font.get_ascent(12)), "Select a save to overwrite or create:" if save_mode else "Please select a saved game:", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
func _rect(value: Array) -> Rect2:
	return Rect2(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
func _frame(key: String, rectangle: Rect2) -> void:
	FRAME.draw(self, layout, key, rectangle)
