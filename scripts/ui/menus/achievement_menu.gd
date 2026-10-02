extends Control
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
signal closed
var host: Node
var layout: Dictionary = {}
var font: Font
var surface: Control
var scroll: ScrollContainer
var rows: VBoxContainer
var details: Label
var details_clip: Control
var dragging_bar := false
var grab_offset := 0.0
var marquee_time := 0.0
var footer_time := 0.0
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
	scroll = ScrollContainer.new(); scroll.position = Vector2(53, 71); scroll.size = Vector2(218, 108); scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_NEVER; scroll.follow_focus = true; surface.add_child(scroll)
	rows = VBoxContainer.new(); rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL; rows.add_theme_constant_override("separation", 0); scroll.add_child(rows)
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new(); pointer.configure(Vector2(40, 73)); surface.add_child(pointer)
	details_clip = Control.new(); details_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE; details_clip.clip_contents = true; details_clip.position = Vector2(44, 200); details_clip.size = Vector2(232, 28); surface.add_child(details_clip)
	details = Label.new(); details.mouse_filter = Control.MOUSE_FILTER_IGNORE; details.add_theme_font_override("font", font); details.add_theme_font_size_override("font_size", 9); details.size = Vector2(232, 28); details.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; details_clip.add_child(details)
	scroll.get_v_scroll_bar().value_changed.connect(func(_value: float): _place_pointer(); queue_redraw())
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
		button.gui_input.connect(_debug_click.bind(id, button))
		var line := HBoxContainer.new(); line.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); line.mouse_filter = Control.MOUSE_FILTER_IGNORE; line.add_theme_constant_override("separation", 4); button.add_child(line)
		var badge := TextureRect.new(); badge.mouse_filter = Control.MOUSE_FILTER_IGNORE; badge.custom_minimum_size = Vector2(16, 16); badge.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; badge.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED; badge.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		var path: String = host.achievement_badge(id); badge.texture = load(path) as Texture2D if ResourceLoader.exists(path) else null; line.add_child(badge)
		var clip := Control.new(); clip.mouse_filter = Control.MOUSE_FILTER_IGNORE; clip.clip_contents = true; clip.size_flags_horizontal = Control.SIZE_EXPAND_FILL; line.add_child(clip)
		var title := Label.new(); title.mouse_filter = Control.MOUSE_FILTER_IGNORE; title.text = _readable_text(str(definition["title"])); title.add_theme_font_override("font", font); title.add_theme_font_size_override("font_size", 11); title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS; title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER; clip.add_child(title); clip.resized.connect(_fit_title.bind(title, 0.0))
		button.set_meta("title", title); button.set_meta("unlocked", unlocked); buttons.append(button)
	for index in range(buttons.size()):
		buttons[index].focus_neighbor_top = buttons[index].get_path_to(buttons[index - 1]); buttons[index].focus_neighbor_bottom = buttons[index].get_path_to(buttons[(index + 1) % buttons.size()])
	selected_index = clampi(selected_index, 0, maxi(buttons.size() - 1, 0)); _focus_row(selected_index); queue_redraw()
func _debug_click(event: InputEvent, id: String, button: Button) -> void:
	if not host.debug_achievements or not event is InputEventMouseButton or not event.pressed or event.button_index not in [MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT]: return
	button.accept_event(); host.debug_set_achievement(id, event.button_index == MOUSE_BUTTON_LEFT)
func focus_first() -> void:
	if is_visible_in_tree() and selected_index < buttons.size(): buttons[selected_index].grab_focus()
func _focus_row(index: int) -> void:
	if index != selected_index and host != null: host.audio.play_ui("menu_move")
	selected_index = index; marquee_time = 0.0; footer_time = 0.0; details.position.y = 0.0
	for row in range(buttons.size()): _fit_title(buttons[row].get_meta("title") as Label, 0.0); (buttons[row].get_meta("title") as Label).add_theme_color_override("font_color", Color.WHITE if row == index else Color8(255, 222, 99) if bool(buttons[row].get_meta("unlocked")) else Color8(128, 128, 128))
	if index < ids.size():
		var definition: Dictionary = host.achievement_catalog[ids[index]]; var stamp: int = int(host.achievements.get_value("unlocked", ids[index], 0))
		details.text = "%s\n%d points%s" % [_readable_text(str(definition["description"])), int(definition.get("points", 0)), "  Unlocked " + Time.get_date_string_from_unix_time(stamp) if stamp > 0 else "  Locked"]
	_place_pointer()
func _fit_title(title: Label, offset: float) -> void:
	var clip := title.get_parent() as Control; var wide := offset > 0.0 or title.text_overrun_behavior == TextServer.OVERRUN_NO_TRIMMING
	title.position = Vector2(-offset, 0); title.size = Vector2(maxf(clip.size.x, font.get_string_size(title.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x) if wide else clip.size.x, clip.size.y)
func _cycle(time: float, travel: float, speed: float) -> float:
	var move := travel / speed; var phase := fmod(time, move + 2.4)
	return clampf(phase - 1.2, 0.0, move) * speed
func _process(delta: float) -> void:
	if not is_visible_in_tree() or selected_index >= buttons.size(): return
	marquee_time += delta; footer_time += delta
	var title := buttons[selected_index].get_meta("title") as Label; var clip := title.get_parent() as Control; var travel := font.get_string_size(title.text, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x - clip.size.x
	var trimmed := travel <= 0.0 or clip.size.x <= 0.0; title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS if trimmed else TextServer.OVERRUN_NO_TRIMMING
	_fit_title(title, 0.0 if trimmed else roundf(_cycle(marquee_time, travel, 28.0)))
	# The footer shows whole lines only and steps a line at a time, so no line is ever cut through the middle.
	var line_height := float(details.get_line_height() + details.get_theme_constant("line_spacing")); var shown := maxi(1, floori(28.0 / line_height)); var hidden := maxi(details.get_line_count() - shown, 0)
	details_clip.size.y = shown * line_height; details_clip.position.y = 200.0 + floorf((28.0 - details_clip.size.y) * 0.5); details.size.y = maxf(details.get_line_count() * line_height, details_clip.size.y)
	details.position.y = -line_height * mini(int(footer_time / 1.6) % (hidden + 2), hidden)
func _track() -> Rect2: return Rect2(scroll.position.x + scroll.size.x + 6.0, scroll.position.y + 1.0, 3.0, scroll.size.y - 2.0)
func _thumb(track: Rect2, maximum: float) -> Rect2:
	var thumb := maxf(8.0, track.size.y * scroll.size.y / rows.size.y)
	return Rect2(track.position.x, track.position.y + (track.size.y - thumb) * float(scroll.scroll_vertical) / maximum, track.size.x, thumb)
func _native(point: Vector2) -> Vector2:
	var factor: float = size.y / 240.0
	return (point - Vector2((size.x - 320.0 * factor) * 0.5, 0)) / factor
func _gui_input(event: InputEvent) -> void:
	var maximum := maxf(rows.size.y - scroll.size.y, 0.0)
	if maximum <= 0.0: return
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		if event.pressed: scroll.scroll_vertical = clampi(scroll.scroll_vertical + (36 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -36), 0, int(maximum))
		accept_event()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed: dragging_bar = false; return
		var track := _track(); var point := _native(event.position)
		if not Rect2(track.position.x - 4.0, track.position.y - 1.0, track.size.x + 8.0, track.size.y + 2.0).has_point(point): return
		var thumb := _thumb(track, maximum); accept_event()
		if point.y >= thumb.position.y and point.y <= thumb.end.y: dragging_bar = true; grab_offset = point.y - thumb.position.y
		else: scroll.scroll_vertical = clampi(scroll.scroll_vertical + int(scroll.size.y - 18.0) * (1 if point.y > thumb.end.y else -1), 0, int(maximum))
	elif event is InputEventMouseMotion and dragging_bar:
		var track := _track(); var travel := track.size.y - _thumb(track, maximum).size.y
		scroll.scroll_vertical = int(roundf(clampf((_native(event.position).y - grab_offset - track.position.y) / travel, 0.0, 1.0) * maximum)); accept_event()
func _place_pointer() -> void:
	if pointer == null or selected_index >= buttons.size(): return
	var y := 73.0 + float(selected_index) * 18.0 - float(scroll.scroll_vertical)
	pointer.visible = y >= 69.0 and y <= 71.0 + scroll.size.y - 10.0;pointer.select_at(Vector2(40, y)); queue_redraw()
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
	FRAME.draw(self, layout, "header", Rect2(20, 4, 112, 22)); FRAME.draw(self, layout, "prompt", Rect2(36, 38, 248, 14)); FRAME.draw(self, layout, "selector", Rect2(36, 64, 248, 120)); FRAME.draw(self, layout, "prompt", Rect2(36, 196, 248, 34))
	if not FRAME.content_visible(self): return
	FRAME.title(self, font, "Achievements", Rect2(20, 4, 112, 22))
	draw_string(font, Vector2(44, 40 + font.get_ascent(9)), "%d / %d unlocked   %d / %d points" % [unlocked_count, ids.size(), earned_points, total_points], HORIZONTAL_ALIGNMENT_LEFT, -1, 9, Color.WHITE)
	# Scrollbar in the native frame colours, matching the options list (thin track + thumb inside the selector frame).
	var maximum := maxf(rows.size.y - scroll.size.y, 0.0)
	if maximum > 0.0:
		var track := _track()
		draw_rect(track.grow(1.0), Color(0.16, 0.16, 0.23)); draw_rect(track.grow(1.0), Color(0.76, 0.79, 0.69, 0.7), false, 1.0)
		draw_rect(_thumb(track, maximum), Color(0.76, 0.79, 0.69))
func _readable_text(value: String) -> String: return value.replace("[", "(").replace("]", ")").replace("|", ",")
