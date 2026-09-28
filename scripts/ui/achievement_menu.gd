extends Control
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
signal closed
var host: Node
var layout: Dictionary = {}
var font: Font
var surface: Control
var scroll: ScrollContainer
var rows: VBoxContainer
var details: Label
var pointer: TextureRect
var ids: Array[String] = []
var buttons: Array[Button] = []
var selected_index := 0
var unlocked_count := 0
var total_points := 0
var earned_points := 0
func configure(owner: Node) -> void:
	host = owner; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json")); layout = manifest["load_game_layout"]; font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	scroll = ScrollContainer.new(); scroll.position = Vector2(53, 69); scroll.size = Vector2(218, 108); scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER; scroll.follow_focus = true; surface.add_child(scroll)
	rows = VBoxContainer.new(); rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL; rows.add_theme_constant_override("separation", 0); scroll.add_child(rows)
	pointer = preload("res://scripts/ui/native_menu_cursor.gd").new(); pointer.configure(Vector2(40, 71)); surface.add_child(pointer)
	details = Label.new(); details.mouse_filter = Control.MOUSE_FILTER_IGNORE; details.add_theme_font_override("font", font); details.add_theme_font_size_override("font_size", 9); details.position = Vector2(44, 192); details.size = Vector2(232, 32); details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; details.clip_text = true; surface.add_child(details)
	scroll.get_v_scroll_bar().value_changed.connect(func(_value: float): _place_pointer())
	resized.connect(_layout); visibility_changed.connect(func(): if visible: call_deferred("focus_first"))
	_layout()
func refresh() -> void:
	for child in rows.get_children(): rows.remove_child(child); child.queue_free()
	ids.clear(); buttons.clear(); unlocked_count = 0; total_points = 0; earned_points = 0
	for id: String in host.achievement_catalog:
		var definition: Dictionary = host.achievement_catalog[id]; var unlocked: bool = host.achievements.has_section_key("unlocked", id); ids.append(id); total_points += int(definition.get("points", 0))
		if unlocked: unlocked_count += 1; earned_points += int(definition.get("points", 0))
		var button := Button.new(); button.custom_minimum_size.y = 18; button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.focus_entered.connect(_focus_row.bind(buttons.size())); button.mouse_entered.connect(button.grab_focus); rows.add_child(button)
		var line := HBoxContainer.new(); line.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); line.mouse_filter = Control.MOUSE_FILTER_IGNORE; line.add_theme_constant_override("separation", 4); button.add_child(line)
		var badge := TextureRect.new(); badge.mouse_filter = Control.MOUSE_FILTER_IGNORE; badge.custom_minimum_size = Vector2(16, 16); badge.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; badge.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED; badge.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		var path: String = host.achievement_badge(id); badge.texture = load(path) as Texture2D if ResourceLoader.exists(path) else null; line.add_child(badge)
		var title := Label.new(); title.mouse_filter = Control.MOUSE_FILTER_IGNORE; title.text = _readable_text(str(definition["title"])); title.add_theme_font_override("font", font); title.add_theme_font_size_override("font_size", 11); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS; title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER; line.add_child(title)
		button.set_meta("title", title); button.set_meta("unlocked", unlocked); buttons.append(button)
	for index in range(buttons.size()):
		buttons[index].focus_neighbor_top = buttons[index].get_path_to(buttons[index - 1]); buttons[index].focus_neighbor_bottom = buttons[index].get_path_to(buttons[(index + 1) % buttons.size()])
	selected_index = clampi(selected_index, 0, maxi(buttons.size() - 1, 0)); _focus_row(selected_index); queue_redraw()
func focus_first() -> void:
	if is_visible_in_tree() and selected_index < buttons.size(): buttons[selected_index].grab_focus()
func _focus_row(index: int) -> void:
	if index != selected_index and host != null: host.audio.play_ui("menu_move")
	selected_index = index
	for row in range(buttons.size()): (buttons[row].get_meta("title") as Label).add_theme_color_override("font_color", Color.WHITE if row == index else Color8(255, 222, 99) if bool(buttons[row].get_meta("unlocked")) else Color8(128, 128, 128))
	if index < ids.size():
		var definition: Dictionary = host.achievement_catalog[ids[index]]; var stamp: int = int(host.achievements.get_value("unlocked", ids[index], 0))
		details.text = "%s\n%d points%s" % [_readable_text(str(definition["description"])), int(definition.get("points", 0)), "  Unlocked " + Time.get_date_string_from_unix_time(stamp) if stamp > 0 else "  Locked"]
	_place_pointer()
func _place_pointer() -> void:
	if pointer == null or selected_index >= buttons.size(): return
	var y := 71.0 + float(selected_index) * 18.0 - float(scroll.scroll_vertical)
	pointer.visible = y >= 67.0 and y <= 69.0 + scroll.size.y - 10.0;pointer.select_at(Vector2(40, y)); queue_redraw()
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	if event.is_action_pressed("ui_cancel") or event.is_action_pressed("ui_accept"): closed.emit(); get_viewport().set_input_as_handled()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); surface.size = Vector2(320, 240); queue_redraw()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide(); await FRAME.exit(self, layout, context)
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "header", Rect2(20, 16, 112, 24)); FRAME.draw(self, layout, "prompt", Rect2(36, 43, 248, 14)); FRAME.draw(self, layout, "selector", Rect2(36, 62, 248, 122)); FRAME.draw(self, layout, "prompt", Rect2(36, 188, 248, 40))
	if not FRAME.content_visible(self): return
	draw_string(font, Vector2(29, 22 + font.get_ascent(12)), "Achievements", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	draw_string(font, Vector2(44, 45 + font.get_ascent(9)), "%d / %d unlocked   %d / %d points" % [unlocked_count, ids.size(), earned_points, total_points], HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color.WHITE)
func _readable_text(value: String) -> String: return value.replace("[", "(").replace("]", ")").replace("|", ",")
