extends Control
signal advance_requested
signal native_page_started(stage: String, message_index: int, page_index: int)
signal native_choice_cursor_changed(stage: String, message_index: int, choice_index: int, source_position: Vector2)
signal choice_completed(choice_index: int)
signal message_started(stage: String, index: int)
signal message_finished(stage: String, index: int)
signal typing_sound_requested(sound_id: int)
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
var layout: Dictionary = {}
var font: Font
var pages: Array[PackedStringArray] = []
var native_page_sources: Array[int] = []
var native_page_speeds: Array[int] = []
var native_page_wait_updates: Array[int] = []
var native_page_choices: Array[Dictionary] = []
var page_index := 0
var active := false
var active_stage := ""
var active_index := -1
var visible_glyphs := 0
var native_tick_accumulator := 0.0
var native_tick_index := 0
var current_native_speed := 0
var current_native_choice: Dictionary = {}
var current_choice_index := -1
var text_complete := true
var current_layout_origin := Vector2(16, 158)
var current_layout_flags := 0x00010083
var choice_surface: Control
var choice_pointer: TextureRect
var choice_pointer_target := Vector2(INF, INF)
var presentation: Dictionary = {}
var native_page_layouts: Array[Dictionary] = []
var native_glyph_speeds: Array[Array] = []
var current_frame := Rect2(25, 173, 291, 55)
var current_width := 144
var current_lines := 3
var current_arrow := false
var arrow_texture: Texture2D
var glyph_delay := 0
var pending_typing_sound := false
var page_ready := false
var advance_blocker: Callable
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; visible = false
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if manifest is Dictionary: layout = manifest.get("load_game_layout", {})
	font = load("res://assets/menu/native_font.fnt") as Font
	choice_surface = Control.new(); choice_surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(choice_surface)
	choice_pointer = preload("res://scripts/ui/native_menu_cursor.gd").new(); choice_pointer.configure(Vector2.ZERO); choice_pointer.hide(); choice_surface.add_child(choice_pointer)
	native_choice_cursor_changed.connect(_update_choice_pointer)
func configure_native_presentation(source: Dictionary) -> void:
	presentation = source
	arrow_texture = load("res://assets/menu/status_normal_atlas.png") as Texture2D
func _apply_native_layout(commands: Array, choice: Dictionary) -> void:
	current_arrow = false
	if choice.has("window_origin"):
		current_layout_origin = Vector2(choice["window_origin"][0], choice["window_origin"][1]); current_width = int(choice.get("window_width", current_width)); current_lines = maxi(1, int(choice.get("window_lines", current_lines)) & 15); current_layout_flags = int(choice.get("window_flags", current_layout_flags))
	for command: Dictionary in commands:
		var opcode := int(command.get("opcode", -1)); var args: Array = command.get("arguments", [])
		if opcode == 0x06 and args.size() == 6: current_layout_origin = Vector2((int(args[0]) << 8) | int(args[1]), (int(args[2]) << 8) | int(args[3])); current_width = int(args[4]); current_lines = maxi(1, int(args[5]) & 15)
		elif opcode == 0x18: current_arrow = true
		elif opcode == 0x24: current_arrow = false
		elif opcode == 0x09 and args.size() == 1: current_layout_flags = current_layout_flags | 0x40000 if int(args[0]) == 0 else current_layout_flags & ~0x40000
		elif opcode == 0x29 and args.size() == 1: current_layout_flags = current_layout_flags | 0x20000 if int(args[0]) == 0 else current_layout_flags & ~0x20000
		elif opcode == 0x1D: current_layout_flags &= ~0x10000
	current_frame = Rect2(current_layout_origin - Vector2(7, 3), Vector2(2 * current_width + 3, 16 * current_lines + 7))
func _update_choice_pointer(_stage: String, _index: int, _selection: int, point: Vector2) -> void:
	var factor := size.y / 240.0
	if factor <= 0.0: return
	choice_surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); choice_surface.scale = Vector2.ONE * factor
	var target := (point - choice_surface.position) / factor
	if not choice_pointer.visible: choice_pointer.configure(target); choice_pointer.has_selection = false; choice_pointer.selection_steps = Vector2.ZERO; choice_pointer.select_at(target); choice_pointer_target = target
	elif target != choice_pointer_target: choice_pointer.select_at(target); choice_pointer_target = target
	choice_pointer.show()
func present_message(stage: String, entry: Dictionary) -> Dictionary:
	var continuing := active
	page_ready = false; visible_glyphs = 0; text_complete = false; pending_typing_sound = false
	if not continuing: active = true; active_stage = stage; active_index = int(entry.get("index", -1)); message_started.emit(active_stage, active_index)
	else: active_index = int(entry.get("index", active_index))
	pages.clear(); native_page_sources.clear(); native_page_speeds.clear(); native_page_wait_updates.clear(); native_page_choices.clear(); native_page_layouts.clear(); native_glyph_speeds.clear(); var native_pages: Variant = entry.get("native_pages", null); var page_speeds: Array = entry.get("native_page_speeds", []); var page_waits: Array = entry.get("native_page_wait_updates", []); var page_choices: Array = entry.get("native_page_choices", []); var command_pages: Array = entry.get("native_page_commands", [])
	if not continuing: current_layout_origin = Vector2(32, 176); current_width = 144; current_lines = 3; current_layout_flags = 0x00010083; set_meta("native_panel_rectangles", {}); remove_meta("native_panel_animation")
	if native_pages is Array:
		for native_index in range(native_pages.size()):
			var choice: Dictionary = page_choices[native_index] if native_index < page_choices.size() else {}; _apply_native_layout(command_pages[native_index] if native_index < command_pages.size() else [], choice)
			var display_pages := _paginate(str(native_pages[native_index])); pages.append_array(display_pages)
			var source_offset := 0; var speeds: Array = page_speeds[native_index] if native_index < page_speeds.size() and page_speeds[native_index] is Array else []
			for _display_page in display_pages:
				native_page_sources.append(native_index); native_page_speeds.append(_source_speed(page_speeds[native_index]) if native_index < page_speeds.size() else 2); native_page_wait_updates.append(int(page_waits[native_index]) if native_index < page_waits.size() else 0); native_page_choices.append(choice); native_page_layouts.append({"origin": current_layout_origin, "frame": current_frame, "flags": current_layout_flags, "arrow": current_arrow}); native_glyph_speeds.append(speeds.slice(source_offset, source_offset + _page_glyph_count(_display_page))); source_offset += _page_glyph_count(_display_page) + 1
	else:
		_apply_native_layout([], {})
		pages = _paginate(str(entry.get("text", "")))
		for _display_page in pages: native_page_sources.append(0); native_page_speeds.append(2); native_page_wait_updates.append(0); native_page_choices.append({}); native_page_layouts.append({"origin": current_layout_origin, "frame": current_frame, "flags": current_layout_flags, "arrow": false}); native_glyph_speeds.append([])
	page_index = 0
	if pages.is_empty():
		if not entry.get("native_tail_commands", []).is_empty(): native_page_started.emit(active_stage, active_index, 0)
		if continuing: await FRAME.exit(self, layout, "gameplay")
		finish_native_message(); message_finished.emit(active_stage, active_index); return {}
	visible = true
	if not native_page_layouts.is_empty(): current_frame = native_page_layouts[0]["frame"]; current_layout_origin = native_page_layouts[0]["origin"]
	if not continuing: await FRAME.enter(self, layout, "gameplay")
	var last_native_page := -1
	for index in range(pages.size()):
		page_index = index; var native_index := native_page_sources[index]; current_native_speed = native_page_speeds[index]; current_native_choice = native_page_choices[index]; current_choice_index = int(current_native_choice.get("selected_index", -1)); current_layout_origin = native_page_layouts[index]["origin"]; current_frame = native_page_layouts[index]["frame"]; current_layout_flags = int(native_page_layouts[index]["flags"]); current_arrow = bool(native_page_layouts[index]["arrow"]); visible_glyphs = 0; native_tick_accumulator = 0.0; native_tick_index = 0; glyph_delay = 0; pending_typing_sound = false; text_complete = false
		if native_index != last_native_page: native_page_started.emit(active_stage, active_index, native_index); last_native_page = native_index
		page_ready = true
		queue_redraw()
		if not current_native_choice.is_empty():
			await choice_completed
			if bool(entry.get("continue_window", false)): return {"choice_index": current_choice_index}
		elif native_page_wait_updates[index] > 0: await _wait_native_updates(native_page_wait_updates[index])
		else: await advance_requested
	if not entry.get("native_tail_commands", []).is_empty(): native_page_started.emit(active_stage, active_index, native_pages.size() if native_pages is Array else 1)
	for command: Dictionary in entry.get("native_tail_commands", []):
		if int(command.get("opcode", -1)) == 0x08:
			var arguments: Array = command.get("arguments", [])
			if arguments.size() == 2: await _wait_native_updates(((int(arguments[0]) << 8) | int(arguments[1])) + 1)
	if bool(entry.get("continue_window", false)): return {"choice_index": -1}
	await FRAME.exit(self, layout, "gameplay")
	visible = false; active = false; current_native_choice.clear(); queue_redraw(); message_finished.emit(active_stage, active_index); return {}
func _unhandled_input(event: InputEvent) -> void:
	if not active or not page_ready or not FRAME.content_visible(self): return
	if not current_native_choice.is_empty():
		var count := int(current_native_choice.get("rows", []).size()); var repeat_input: bool = event is InputEventKey and (event as InputEventKey).echo
		if count <= 2 and repeat_input: return
		if event.is_action_pressed("ui_up"): _move_native_choice(0, -1); get_viewport().set_input_as_handled(); return
		if event.is_action_pressed("ui_down"): _move_native_choice(0, 1); get_viewport().set_input_as_handled(); return
		if event.is_action_pressed("ui_left"): _move_native_choice(-1, 0); get_viewport().set_input_as_handled(); return
		if event.is_action_pressed("ui_right"): _move_native_choice(1, 0); get_viewport().set_input_as_handled(); return
		if not (event.is_action_pressed("interact") or event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_cancel")): return
		get_viewport().set_input_as_handled()
		if event.is_action_pressed("ui_cancel"): current_choice_index = count
		choice_completed.emit(current_choice_index); return
	if not (event.is_action_pressed("interact") or event.is_action_pressed("ui_accept")): return
	get_viewport().set_input_as_handled()
	if not text_complete: pending_typing_sound = not "\n".join(pages[page_index]).substr(visible_glyphs).strip_edges().is_empty(); visible_glyphs = _page_glyph_count(pages[page_index]); text_complete = true; queue_redraw(); return
	if not current_native_choice.is_empty(): choice_completed.emit(current_choice_index); return
	if advance_blocker.is_valid() and advance_blocker.call(): return
	advance_requested.emit()
func _process(delta: float) -> void:
	if is_instance_valid(choice_pointer) and not (active and FRAME.content_visible(self) and not current_native_choice.is_empty() and current_choice_index >= 0 and current_choice_index < int(current_native_choice.get("rows", []).size())): choice_pointer.hide()
	if not active or not page_ready or not FRAME.content_visible(self) or page_index >= pages.size(): return
	native_tick_accumulator += delta
	while native_tick_accumulator >= 0.04:
		native_tick_accumulator -= 0.04; native_tick_index += 1
		if not text_complete: _type_native_tick()
		if pending_typing_sound:
			if (current_layout_flags & 0xC0010000) == 0x00010000: typing_sound_requested.emit(int(presentation.get("typing", {}).get("sound_id", 0x84)))
			pending_typing_sound = false
	queue_redraw()
func _type_native_tick() -> void:
	if glyph_delay > 0: glyph_delay -= 1; return
	var text := "\n".join(pages[page_index]); var speeds: Array = native_glyph_speeds[page_index]
	while visible_glyphs < text.length():
		var character := text.substr(visible_glyphs, 1); var speed := int(speeds[visible_glyphs]) if visible_glyphs < speeds.size() else current_native_speed; visible_glyphs += 1
		if character == "\n": continue
		if character != " ": pending_typing_sound = true
		if speed > 0: glyph_delay = speed - 1; break
	text_complete = visible_glyphs >= text.length()
func _draw() -> void:
	if not active or font == null or layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "prompt", current_frame)
	if pages.is_empty() or not FRAME.content_visible(self): return
	var remaining := visible_glyphs; var y := current_layout_origin.y + 3.0 + font.get_ascent(12)
	for line_index in range(pages[page_index].size()):
		var line := pages[page_index][line_index]; var shown := mini(remaining, line.length()); if shown > 0: draw_string(font, Vector2(current_layout_origin.x, y), line.substr(0, shown), HORIZONTAL_ALIGNMENT_LEFT, current_frame.size.x - 10, 12, Color.WHITE)
		remaining = maxi(remaining - line.length() - (1 if line_index < pages[page_index].size() - 1 else 0), 0); y += 16
	if not current_native_choice.is_empty(): _draw_native_choices(current_native_choice)
	elif text_complete and current_arrow and arrow_texture != null:
		var frames: Array = presentation.get("continuation_arrow", {}).get("frames", []); var frame_index := (native_tick_index / 2) % 6
		if not frames.is_empty():
			var uv: Array = frames[frame_index]; draw_texture_rect_region(arrow_texture, Rect2(current_layout_origin.x + current_frame.size.x - 16, current_frame.end.y - 9, 8, 8), Rect2(uv[0], uv[1], uv[2], uv[3]))
func _paginate(text: String) -> Array[PackedStringArray]:
	var lines: Array[String] = []
	for source_line in text.replace("\r", "").split("\n"):
		var current := ""
		for word in source_line.split(" ", false):
			var candidate := word if current.is_empty() else current + " " + word
			if not current.is_empty() and font != null and font.get_string_size(candidate, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x > current_width * 2:
				lines.append(current); current = word
			else: current = candidate
		lines.append(current)
	while lines.size() > 1 and lines[-1].strip_edges().is_empty(): lines.pop_back()
	var result: Array[PackedStringArray] = []
	for offset in range(0, lines.size(), current_lines): result.append(PackedStringArray(lines.slice(offset, mini(offset + current_lines, lines.size()))))
	if result.is_empty(): result.append(PackedStringArray([""]))
	return result
func _native_layout_origin(commands: Array, choice: Dictionary) -> Vector2:
	if choice.has("window_origin"): return Vector2(float(choice["window_origin"][0]), float(choice["window_origin"][1]))
	for command: Dictionary in commands:
		if int(command.get("opcode", -1)) == 0x06:
			var args: Array = command.get("arguments", []); if args.size() == 6: return Vector2((int(args[0]) << 8) | int(args[1]), (int(args[2]) << 8) | int(args[3]))
	return Vector2(16, 158)
func _draw_native_choices(choice: Dictionary) -> void:
	var rows: Array = choice.get("rows", []); var coordinates: Array = choice.get("native_coordinates", []); var factor := size.y / 240.0; var offset_x := (size.x - 320.0 * factor) * 0.5
	for index in range(mini(rows.size(), coordinates.size())):
		var point: Array = coordinates[index]; var column := int(point[0]); var line := int(point[1]); var x := int(current_layout_origin.x) + (12 * column - 8 if current_layout_flags & 0x800000 else 2 * column); var y := int(current_layout_origin.y) + (16 * line + 7 if current_layout_flags & 0x800000 else 16 * line); var label := str(rows[index].get("text", "")); draw_string(font, Vector2(x + 14, y + font.get_ascent(12)), label, HORIZONTAL_ALIGNMENT_LEFT, 250, 12, Color.WHITE)
	var selected := current_choice_index
	if selected >= 0 and selected < coordinates.size():
		var point: Array = coordinates[selected]; var column := int(point[0]); var line := int(point[1]); var x := int(current_layout_origin.x) + (12 * column - 8 if current_layout_flags & 0x800000 else 2 * column); var y := int(current_layout_origin.y) + (16 * line + 7 if current_layout_flags & 0x800000 else 16 * line); native_choice_cursor_changed.emit(active_stage, active_index, selected, Vector2(offset_x + x * factor, y * factor))
func _move_native_choice(dx: int, dy: int) -> void:
	var coordinates: Array = current_native_choice.get("native_coordinates", []); if coordinates.size() <= 1: return
	var current := clampi(current_choice_index, 0, coordinates.size() - 1); var source: Array = coordinates[current]; var best := -1; var best_distance := 256
	for candidate in range(coordinates.size()):
		if candidate == current: continue
		var point: Array = coordinates[candidate]; var distance := 0
		if dy != 0 and int(point[0]) == int(source[0]): distance = posmod((int(point[1]) - int(source[1])) * dy, 256)
		elif dx != 0 and int(point[1]) == int(source[1]): distance = posmod((int(point[0]) - int(source[0])) * dx, 256)
		if distance > 0 and distance < best_distance: best = candidate; best_distance = distance
	if best >= 0: current_choice_index = best; queue_redraw()
func _source_speed(value: Variant) -> int:
	if typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT: return int(value)
	if value is Array or value is PackedInt32Array:
		var speed := 0
		for item in value: speed = maxi(speed, int(item))
		return speed
	return 0
func finish_native_message() -> void:
	visible = false; active = false; page_ready = false; current_native_choice.clear(); queue_redraw()
func _page_glyph_count(lines: PackedStringArray) -> int:
	var count := 0
	for index in range(lines.size()): count += lines[index].length() + (1 if index < lines.size() - 1 else 0)
	return count
func _wait_native_updates(updates: int) -> void:
	await get_tree().create_timer(float(updates) / 25.0).timeout
