extends Control
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
signal selected(save_id: String)
signal closed
signal completion_acknowledged
var completion_active := false
signal load_confirmed(accepted: bool)
var confirming_load := false
var loading_display := false
var confirmation_text := "Load this data?"
var completion_text := "Save complete!"
var confirmation_buttons: Array[Button] = []
var load_fade: Control
var host: Node
var manifest: Dictionary = {}
var layout: Dictionary = {}
var background: Texture2D
var font: Font
var surface: Control
var scroll: ScrollContainer
var rows: VBoxContainer
var details: Label
var details_time: Label
var pointer: TextureRect
var cancel: Button
var message: Label
var entries: Array = []
var buttons: Array[Button] = []
var selected_index: int = 0
var save_mode := false
var elapsed: float = 0.0
var selector_rect := Rect2(36, 68, 248, 120)
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
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new()
	pointer.configure(Vector2(40, 77))
	surface.add_child(pointer)
	scroll = ScrollContainer.new()
	scroll.position = Vector2(53, 75)
	scroll.size = Vector2(218, 90)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	surface.add_child(scroll)
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 0)
	scroll.add_child(rows)
	details = _label("", font, 9)
	details.position = Vector2(48, 205)
	details.size = Vector2(224, 12)
	details.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	surface.add_child(details)
	details_time = _label("", font, 10); details_time.position = Vector2(196, 213); details_time.size = Vector2(76, 12); details_time.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT; surface.add_child(details_time)
	cancel = Button.new()
	cancel.text = "Cancel"
	cancel.position = Vector2(53, 161)
	cancel.size = Vector2(218, 16)
	cancel.alignment = HORIZONTAL_ALIGNMENT_LEFT
	cancel.add_theme_font_override("font", font)
	cancel.add_theme_font_size_override("font_size", 12)
	for state in ["normal", "hover", "pressed", "focus"]: cancel.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	cancel.pressed.connect(closed.emit)
	cancel.mouse_entered.connect(cancel.grab_focus)
	cancel.focus_entered.connect(func(): _focus_row(entries.size()))
	surface.add_child(cancel)
	for index in 2:
		var button := Button.new(); button.text = "Yes" if index == 0 else "No"; button.position = Vector2(118 + index * 46, 118); button.size = Vector2(40, 16); button.add_theme_font_override("font", font); button.add_theme_font_size_override("font_size", 12)
		for state in ["normal", "hover", "pressed", "focus"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.pressed.connect(func(): load_confirmed.emit(index == 0)); button.focus_entered.connect(func(): _focus_confirmation(button)); button.mouse_entered.connect(button.grab_focus); button.hide(); surface.add_child(button); confirmation_buttons.append(button)
	confirmation_buttons[0].focus_neighbor_right = confirmation_buttons[0].get_path_to(confirmation_buttons[1]); confirmation_buttons[1].focus_neighbor_left = confirmation_buttons[1].get_path_to(confirmation_buttons[0])
	message = _label("", font, 9)
	message.position = Vector2(36, 228)
	message.size = Vector2(248, 12)
	message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message.hide()
	surface.add_child(message)
	resized.connect(_layout)
	visibility_changed.connect(_visibility_changed)
	_layout()
func refresh(save_entries: Array, saving: bool = false) -> void:
	if is_instance_valid(load_fade): load_fade.hide(); load_fade.queue_free(); load_fade = null
	confirming_load = false; loading_display = false
	for button in confirmation_buttons: button.hide()
	completion_active = false; scroll.show(); cancel.show(); pointer.show()
	var previous_id: String = str(entries[selected_index]["id"]) if selected_index < entries.size() else ""
	for child in rows.get_children():
		rows.remove_child(child)
		child.queue_free()
	save_mode = saving
	entries = save_entries.duplicate()
	buttons.clear()
	selected_index = 0
	set_message("")
	for index in range(entries.size()):
		var entry: Dictionary = entries[index]
		var button := Button.new()
		button.custom_minimum_size.y = 18
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.disabled = not save_mode and not str(entry.get("error", "")).is_empty()
		button.pressed.connect(_choose.bind(str(entry["id"])))
		button.focus_entered.connect(_focus_row.bind(index))
		button.mouse_entered.connect(button.grab_focus)
		rows.add_child(button)
		var top := HBoxContainer.new()
		top.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		top.mouse_filter = Control.MOUSE_FILTER_IGNORE
		button.add_child(top)
		var name_label := _label("%d:%s" % [int(entry["slot"]), "No save data" if bool(entry["empty"]) else str(entry["name"])], font, 11)
		name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		name_label.custom_minimum_size.x = 110
		top.add_child(name_label)
		var date := _label("--:--:--" if bool(entry["empty"]) else _playtime(float(entry.get("play_time_seconds", 0))), font, 10)
		date.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		date.custom_minimum_size.x = 56
		top.add_child(date)
		button.set_meta("labels", [name_label, date])
		if str(entry["id"]) == previous_id: selected_index = index
		buttons.append(button)
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
	if loading_display and not text.is_empty(): loading_display = false; scroll.show(); cancel.show(); pointer.show(); queue_redraw()
	message.text = text
	message.visible = not text.is_empty()
func show_completion() -> void:
	completion_text = "Save complete!"
	completion_active = true; scroll.hide(); cancel.hide(); pointer.hide(); set_message(""); queue_redraw()
	await completion_acknowledged
	completion_active = false
func acknowledge_completion() -> void:
	if completion_active: completion_acknowledged.emit()
func _focus_confirmation(button: Button) -> void:
	var text_width := font.get_string_size(button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	pointer.select_at(button.position + Vector2((button.size.x - text_width) * 0.5 - 14.0, (button.size.y - pointer.size.y) * 0.5)); host.audio.play_ui("menu_move")
func confirm_load(overwriting: bool = false) -> bool:
	confirmation_text = "Overwrite existing data?" if overwriting else "Load this data?"
	confirming_load = true; scroll.hide(); cancel.hide(); pointer.show()
	for button in confirmation_buttons: button.show()
	confirmation_buttons[0].grab_focus(); call_deferred("_focus_confirmation", confirmation_buttons[0]); queue_redraw()
	var accepted: bool = await load_confirmed
	confirming_load = false
	for button in confirmation_buttons: button.hide()
	scroll.show(); cancel.show(); _focus_row(selected_index); focus_first(); queue_redraw(); return accepted
func show_loading() -> void:
	loading_display = true; scroll.hide(); cancel.hide(); pointer.hide(); set_message(""); queue_redraw()
func finish_load() -> void:
	loading_display = false; completion_active = true; completion_text = "Load complete!"; queue_redraw()
	load_fade = preload("res://scripts/ui/common/native_fade.gd").new(); add_child(load_fade); load_fade.configure(); await get_tree().process_frame; await load_fade.request(0x26)
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
		for label: Label in buttons[row].get_meta("labels"): label.add_theme_color_override("font_color", Color.WHITE if row == index else Color8(128, 128, 112))
	cancel.add_theme_color_override("font_color", Color.WHITE if index == entries.size() else Color8(128, 128, 112))
	if index < entries.size():
		var entry: Dictionary = entries[index]
		details.text = "%d:%s" % [int(entry["slot"]), "No save data" if bool(entry["empty"]) else str(entry["error"]) if not str(entry.get("error", "")).is_empty() else str(entry["name"])]
		details_time.text = "--:--:--" if bool(entry["empty"]) else _playtime(float(entry.get("play_time_seconds", 0)))
	else: details.text = ""; details_time.text = ""
	pointer.select_at(Vector2(40, 77 + selected_index * 18) if selected_index < entries.size() else Vector2(40, 163))
	queue_redraw()
func _playtime(seconds: float) -> String:
	var total := maxi(int(seconds), 0)
	return "%02d:%02d:%02d" % [int(total / 3600.0), int(total / 60.0) % 60, total % 60]
func _choose(save_id: String) -> void:
	for entry: Dictionary in entries:
		if str(entry["id"]) != save_id: continue
		if not save_mode and (bool(entry["empty"]) or not str(entry.get("error", "")).is_empty()):
			set_message("No save data" if bool(entry["empty"]) else str(entry["error"]))
			return
		set_message("")
		selected.emit(save_id)
		return
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	if confirming_load:
		if event.is_action_pressed("ui_cancel"): load_confirmed.emit(false); get_viewport().set_input_as_handled()
		return
	if loading_display: return
	if completion_active:
		if event.is_action_pressed("ui_cancel") or event.is_action_pressed("ui_accept"): acknowledge_completion(); get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("ui_cancel"):
		closed.emit()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("ui_accept"):
		if cancel.has_focus() or selected_index >= entries.size(): closed.emit()
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
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide()
	await FRAME.exit(self, layout, context)
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	var phase: int = (int(elapsed * 30.0) >> 1) & 63
	var origin := Vector2(phase - 80, phase - 80)
	if not save_mode and not (is_instance_valid(host) and is_instance_valid(host.get("gameplay"))): draw_texture_rect(background, Rect2(Vector2(-offset.x / factor, 0) + origin, Vector2(size.x / factor, 240) + Vector2(160, 160)), true)
	_frame("header", Rect2(20, 4, 106, 22))
	if not confirming_load and not loading_display and not completion_active: _frame("prompt", Rect2(36, 38, 248, 18))
	_frame("selector", Rect2(76, 104, 168, 40) if confirming_load and save_mode else Rect2(104, 104, 112, 40) if confirming_load else Rect2(105, 112, 111, 23) if completion_active or loading_display else selector_rect)
	_frame("prompt", Rect2(36, 200, 248, 26))
	if not FRAME.content_visible(self): return
	if completion_active or loading_display: draw_string(font, Vector2(112, 115 + font.get_ascent(12)), ("Saving..." if save_mode else "Loading...") if loading_display else completion_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	if confirming_load: draw_string(font, Vector2(83 if save_mode else 111, 107 + font.get_ascent(12)), confirmation_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	draw_string(font, Vector2(29, 10 + font.get_ascent(12)), "Save Game" if save_mode else "Load Game", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	if not confirming_load and not loading_display and not completion_active: draw_string(font, Vector2(44, 41 + font.get_ascent(9)), "Please select a save slot:", HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color.WHITE)
func _rect(value: Array) -> Rect2:
	return Rect2(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
func _frame(key: String, rectangle: Rect2) -> void:
	FRAME.draw(self, layout, key, rectangle)
