extends Control
signal help_changed(text: String)
signal sound(name: String)
const ROW := 14.0
const HEADING := 16.0
const PAD := 2.0
const TAN := Color(0.72, 0.68, 0.52)
const GOLD := Color8(255, 222, 99)
const FRAME_LIGHT := Color(0.76, 0.79, 0.69)
const FRAME_DARK := Color(0.16, 0.16, 0.23)
var font: Font
var rows: Array = []
var tops: PackedFloat32Array = []
var selected := 0
var scroll := 0.0
var target := 0.0
var hover_arrow := 0
var dragging_bar := false
var pointer: TextureRect
var cell_width := 90.0
func configure(native_font: Font) -> void:
	font = native_font
	clip_contents = true
	focus_mode = Control.FOCUS_ALL
	mouse_filter = Control.MOUSE_FILTER_STOP
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new()
	pointer.configure(Vector2(2, 0))
	add_child(pointer)
func set_rows(value: Array) -> void:
	rows = value
	tops.resize(rows.size() + 1)
	var y := PAD
	for index in rows.size(): tops[index] = y; y += HEADING if rows[index]["kind"] == "heading" else ROW
	tops[rows.size()] = y + PAD
	var widest := 0.0
	for row in rows: widest = maxf(widest, font.get_string_size(str(row["label"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x)
	cell_width = clampf(size.x - 8.0 - 12.0 - (20.0 + widest + 8.0), 70.0, 130.0)
	reset_view()
func reset_view() -> void:
	selected = _next(-1, 1)
	scroll = 0.0
	target = 0.0
	_place(true)
	_emit_help()
	queue_redraw()
func _max_scroll() -> float:
	return maxf(0.0, tops[rows.size()] - size.y)
func _next(from: int, direction: int, wrap := false) -> int:
	var index := from
	for count in rows.size():
		index += direction
		if index < 0 or index >= rows.size():
			if not wrap: return from
			index = posmod(index, rows.size())
		if rows[index]["kind"] != "heading": return index
	return from
func _select(index: int, quiet := false) -> void:
	if index == selected or index < 0 or index >= rows.size() or rows[index]["kind"] == "heading": return
	selected = index
	if not quiet: sound.emit("menu_move")
	_reveal()
	_place(false)
	_emit_help()
	queue_redraw()
func _reveal() -> void:
	var need_top := tops[selected] - (HEADING if selected > 0 and rows[selected - 1]["kind"] == "heading" else PAD)
	var need_bottom := tops[selected] + ROW + PAD
	if target > need_top: target = need_top
	elif target + size.y < need_bottom: target = need_bottom - size.y
	target = clampf(target, 0.0, _max_scroll())
func _place(snap: bool) -> void:
	if pointer == null or rows.is_empty(): return
	pointer.select_at(Vector2(2, tops[selected] + (ROW - 12.0) * 0.5 - target))
	if snap: pointer.cursor_point = pointer.cursor_origin; pointer.position = pointer.cursor_origin; pointer.selection_steps = Vector2.ZERO
func _emit_help() -> void:
	if not rows.is_empty(): help_changed.emit(str(rows[selected].get("help", "")))
func _process(delta: float) -> void:
	if not is_visible_in_tree(): return
	if absf(scroll - target) > 0.01:
		scroll = target if absf(scroll - target) < 0.5 else lerpf(scroll, target, 1.0 - exp(-delta * 20.0))
		queue_redraw()
func _row_at(y: float) -> int:
	y += scroll
	for index in rows.size():
		if y >= tops[index] and y < tops[index + 1] - (PAD if index == rows.size() - 1 else 0.0): return index
	return -1
func _value_rect(top: float) -> Rect2:
	return Rect2(size.x - 12.0 - cell_width, top, cell_width, ROW)
func _text(row: Dictionary) -> String:
	var value: Variant = row["get"].call()
	if row["kind"] == "choice": return str(row["choices"][clampi(int(value), 0, row["choices"].size() - 1)])
	return row.get("format", "%d") % (float(value) * float(row.get("scale", 1.0)) if row.has("scale") else value)
func _change(row: Dictionary, direction: int, wrap := false) -> void:
	var value: Variant = row["get"].call()
	var result: Variant
	if row["kind"] == "choice": result = posmod(int(value) + direction, row["choices"].size())
	else:
		result = float(value) + direction * float(row["step"])
		if wrap and result > float(row["max"]) + 0.00001: result = float(row["min"])
		result = snappedf(clampf(result, float(row["min"]), float(row["max"])), float(row["step"]) * 0.1)
		if absf(result - float(value)) < 0.000001: return
		if not row.get("float", false): result = int(result)
	row["set"].call(result)
	if not row.get("silent", false): sound.emit("menu_move")
	queue_redraw()
func _activate(wrap := true) -> void:
	var row: Dictionary = rows[selected]
	if row["kind"] == "action": sound.emit("menu_cancel" if row.get("cancel", false) else "menu_confirm"); row["do"].call()
	else: _change(row, 1, wrap)
func _set_from_x(row: Dictionary, x: float) -> void:
	var bar := _bar_rect(0.0)
	var fraction := clampf((x - bar.position.x) / bar.size.x, 0.0, 1.0)
	var value := float(row["min"]) + fraction * (float(row["max"]) - float(row["min"]))
	value = snappedf(value, float(row["step"]))
	if absf(value - float(row["get"].call())) < 0.000001: return
	row["set"].call(value if row.get("float", false) else int(value))
	queue_redraw()
func _bar_rect(top: float) -> Rect2:
	var cell := _value_rect(top)
	return Rect2(cell.position.x + 12.0, top + 5.0, maxf(16.0, cell_width - 24.0 - 36.0), 4.0)
func _arrow_hit(position: Vector2, top: float) -> int:
	var cell := _value_rect(top)
	if Rect2(cell.position.x - 2.0, top, 13.0, ROW).has_point(position): return -1
	if Rect2(cell.end.x - 11.0, top, 13.0, ROW).has_point(position): return 1
	return 0
func _gui_input(event: InputEvent) -> void:
	if rows.is_empty(): return
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN, MOUSE_BUTTON_WHEEL_LEFT, MOUSE_BUTTON_WHEEL_RIGHT]:
		if event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_UP: target = clampf(target - ROW * 2.0, 0.0, _max_scroll())
		elif event.pressed and event.button_index == MOUSE_BUTTON_WHEEL_DOWN: target = clampf(target + ROW * 2.0, 0.0, _max_scroll())
		accept_event()
		_place(false)
		queue_redraw()
	elif event is InputEventPanGesture:
		target = clampf(target + event.delta.y * ROW, 0.0, _max_scroll()); scroll = target; accept_event(); _place(false); queue_redraw()
	elif event is InputEventMouseMotion:
		if dragging_bar:
			var travel := size.y - 4.0
			target = clampf((event.position.y - 2.0) / travel * tops[rows.size()] - size.y * 0.5, 0.0, _max_scroll()); scroll = target; _place(false); queue_redraw(); accept_event(); return
		var index := _row_at(event.position.y)
		if index >= 0 and rows[index]["kind"] != "heading":
			var arrow := _arrow_hit(event.position, tops[index] - scroll) if rows[index]["kind"] != "action" else 0
			if index != selected: _select(index)
			if arrow != hover_arrow: hover_arrow = arrow; queue_redraw()
			if not has_focus(): grab_focus()
		elif hover_arrow != 0: hover_arrow = 0; queue_redraw()
	elif event is InputEventMouseButton and not event.pressed and event.button_index == MOUSE_BUTTON_LEFT: dragging_bar = false
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		accept_event()
		if _max_scroll() > 0.0 and event.position.x >= size.x - 8.0:
			dragging_bar = true
			target = clampf((event.position.y - 2.0) / (size.y - 4.0) * tops[rows.size()] - size.y * 0.5, 0.0, _max_scroll()); scroll = target; _place(false); queue_redraw()
			return
		var index := _row_at(event.position.y)
		if index < 0 or rows[index]["kind"] == "heading": return
		_select(index)
		var row: Dictionary = rows[index]
		var top := tops[index] - scroll
		if row["kind"] == "action": _activate()
		elif _value_rect(top).grow(2.0).has_point(event.position):
			var arrow := _arrow_hit(event.position, top)
			if arrow != 0: _change(row, arrow)
			elif row["kind"] == "range" and _bar_rect(top).grow_individual(2, 5, 2, 5).has_point(event.position): _set_from_x(row, event.position.x); dragging_bar = false
			else: _activate()
	elif event is InputEventKey or event is InputEventJoypadButton or event is InputEventJoypadMotion:
		var row: Dictionary = rows[selected]
		if event.is_action_pressed("ui_down", true): _select(_next(selected, 1, not event.is_echo()))
		elif event.is_action_pressed("ui_up", true): _select(_next(selected, -1, not event.is_echo()))
		elif event.is_action_pressed("ui_page_down", true): _select(_next(mini(selected + 5, rows.size() - 1) - 1, 1))
		elif event.is_action_pressed("ui_page_up", true): _select(_next(maxi(selected - 5, 0) + 1, -1))
		elif row["kind"] != "action" and event.is_action_pressed("ui_left", row["kind"] == "range"): _change(row, -1)
		elif row["kind"] != "action" and event.is_action_pressed("ui_right", row["kind"] == "range"): _change(row, 1)
		elif event.is_action_pressed("ui_accept"): _activate()
		else: return
		accept_event()
func _draw() -> void:
	if font == null or rows.is_empty(): return
	var width := size.x - (8.0 if _max_scroll() > 0.0 else 0.0)
	var baseline := roundf((ROW - font.get_height(10)) * 0.5 + font.get_ascent(10))
	for index in rows.size():
		var top := roundf(tops[index] - scroll)
		if top + HEADING < 0.0 or top > size.y: continue
		var row: Dictionary = rows[index]
		if row["kind"] == "heading":
			if str(row["label"]).is_empty(): continue
			draw_string(font, Vector2(8, top + HEADING - 4.0), str(row["label"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, GOLD)
			var line := font.get_string_size(str(row["label"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x + 14.0
			draw_line(Vector2(line, top + HEADING - 7.0), Vector2(width - 6.0, top + HEADING - 7.0), Color(GOLD, 0.35), 1.0)
			continue
		var active := index == selected
		if active:
			draw_rect(Rect2(0, top, width, ROW), Color(FRAME_LIGHT, 0.17))
			draw_rect(Rect2(0, top, width, 1), Color(FRAME_LIGHT, 0.45))
			draw_rect(Rect2(0, top + ROW - 1.0, width, 1), Color(FRAME_LIGHT, 0.45))
		var color := Color.WHITE if active else TAN
		draw_string(font, Vector2(20, top + baseline), str(row["label"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, color)
		if row["kind"] == "action": continue
		var cell := _value_rect(top)
		var current := float(row["get"].call())
		var left_on := true
		var right_on := true
		if row["kind"] == "range": left_on = current > float(row["min"]) + 0.000001; right_on = current < float(row["max"]) - 0.000001
		var center := top + ROW * 0.5
		var tint := Color.WHITE if active else TAN
		_arrow(Vector2(cell.position.x + 2.0, center), -1, (GOLD if hover_arrow == -1 and active else tint) if left_on else Color(TAN, 0.3))
		_arrow(Vector2(cell.end.x - 2.0, center), 1, (GOLD if hover_arrow == 1 and active else tint) if right_on else Color(TAN, 0.3))
		var text := _text(row)
		if row["kind"] == "range":
			var bar := _bar_rect(top)
			draw_rect(bar.grow(1.0), FRAME_DARK)
			draw_rect(bar.grow(1.0), Color(FRAME_LIGHT, 0.8 if active else 0.45), false, 1.0)
			var fraction := clampf((current - float(row["min"])) / (float(row["max"]) - float(row["min"])), 0.0, 1.0)
			draw_rect(Rect2(bar.position, Vector2(roundf(bar.size.x * fraction), bar.size.y)), GOLD if active else TAN)
			draw_string(font, Vector2(bar.end.x + 5.0, top + baseline), text, HORIZONTAL_ALIGNMENT_LEFT, cell.end.x - 14.0 - bar.end.x - 5.0, 10, color)
		else: draw_string(font, Vector2(cell.position.x + 12.0, top + baseline), text, HORIZONTAL_ALIGNMENT_CENTER, cell.size.x - 24.0, 10, GOLD if active else TAN)
	var maximum := _max_scroll()
	if maximum <= 0.0: return
	var track := Rect2(size.x - 5.0, 2.0, 3.0, size.y - 4.0)
	draw_rect(track.grow(1.0), FRAME_DARK)
	draw_rect(track.grow(1.0), Color(FRAME_LIGHT, 0.7), false, 1.0)
	var thumb := maxf(8.0, track.size.y * size.y / tops[rows.size()])
	draw_rect(Rect2(track.position.x, track.position.y + (track.size.y - thumb) * scroll / maximum, track.size.x, thumb), FRAME_LIGHT)
func _arrow(point: Vector2, direction: int, color: Color) -> void:
	draw_colored_polygon(PackedVector2Array([point + Vector2(direction * 2.5, 0), point + Vector2(-direction * 2.5, -4), point + Vector2(-direction * 2.5, 4)]), color)
