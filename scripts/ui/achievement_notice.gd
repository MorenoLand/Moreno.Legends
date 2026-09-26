extends Control
signal shown(id: String)
signal finished(id: String)
const FRAME := preload("res://scripts/ui/native_menu_frame.gd")
const DISPLAY_SECONDS := 4.0
var layout: Dictionary = {}
var font: Font
var blockers: Array[Control] = []
var pending: Array[Dictionary] = []
var current: Dictionary = {}
var title_lines: Array[String] = []
var description_lines: Array[String] = []
var rectangle := Rect2(120, 12, 188, 40)
var phase := ""
var elapsed := 0.0
var hold_seconds := 0.0
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_PAUSABLE; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; focus_mode = Control.FOCUS_NONE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; hide()
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if manifest is Dictionary: layout = manifest.get("load_game_layout", {})
	font = load("res://assets/menu/native_font.fnt") as Font
func configure(controls: Array[Control]) -> void:
	for control: Control in blockers:
		if is_instance_valid(control) and control.visibility_changed.is_connected(_refresh_visibility): control.visibility_changed.disconnect(_refresh_visibility)
	blockers = controls.duplicate()
	for control: Control in blockers:
		if is_instance_valid(control) and not control.visibility_changed.is_connected(_refresh_visibility): control.visibility_changed.connect(_refresh_visibility)
	_refresh_visibility()
func enqueue(definition: Dictionary) -> void:
	if str(definition.get("id", "")).is_empty() or str(definition.get("title", "")).is_empty(): return
	pending.append({"id": str(definition["id"]), "title": str(definition["title"]), "description": str(definition.get("description", ""))})
func _blocked() -> bool:
	for control: Control in blockers:
		if is_instance_valid(control) and control.is_visible_in_tree(): return true
	return false
func _refresh_visibility() -> void: visible = not phase.is_empty() and not _blocked()
func _begin_next() -> void:
	current = pending.pop_front(); title_lines = _wrap(str(current["title"])); description_lines = _wrap(str(current["description"])) if not str(current["description"]).is_empty() else []
	rectangle.size.y = 12.0 + 14.0 * float(title_lines.size() + description_lines.size()); hold_seconds = 0.0; _begin_animation("opening"); _refresh_visibility(); shown.emit(str(current["id"]))
func _begin_animation(value: String) -> void:
	phase = value; var key := "prompt:%d:%d" % [roundi(rectangle.position.x), roundi(rectangle.position.y)]
	set_meta("native_panel_animation", {"phase": value, "complete": false, "windows": {key: FRAME._window_state(rectangle, value)}}); queue_redraw()
func _process(delta: float) -> void:
	if font == null or layout.is_empty(): return
	_refresh_visibility()
	if _blocked(): return
	if phase.is_empty():
		if not pending.is_empty(): _begin_next()
		return
	elapsed += delta
	var period := 1.0 / float(layout["panel_animation"]["tick_rates"]["gameplay"])
	while elapsed >= period:
		elapsed -= period
		if phase == "holding":
			hold_seconds += period
			if hold_seconds >= DISPLAY_SECONDS: _begin_animation("closing")
		else:
			var animation: Dictionary = get_meta("native_panel_animation"); var complete := true
			for window: Dictionary in animation["windows"].values(): FRAME._advance_window(window, phase); complete = complete and int(window["state"]) == (3 if phase == "opening" else 0)
			animation["complete"] = complete
			if complete:
				if phase == "opening": phase = "holding"
				else:
					var id := str(current["id"]); current.clear(); phase = ""; elapsed = 0.0; hide(); finished.emit(id); return
		queue_redraw()
func _draw() -> void:
	if phase.is_empty() or font == null or layout.is_empty() or size.y <= 0.0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor); FRAME.draw(self, layout, "prompt", rectangle)
	if not FRAME.content_visible(self): return
	var position := rectangle.position + Vector2(7, 6 + font.get_ascent(12))
	for line: String in title_lines: draw_string(font, position, line, HORIZONTAL_ALIGNMENT_LEFT, 174, 12, Color.WHITE); position.y += 14.0
	for line: String in description_lines: draw_string(font, position, line, HORIZONTAL_ALIGNMENT_LEFT, 174, 12, Color.WHITE); position.y += 14.0
func _wrap(text: String) -> Array[String]:
	var result: Array[String] = []
	for paragraph: String in text.replace("\r", "").split("\n"):
		var line := ""
		for word: String in paragraph.split(" ", false):
			var candidate := line + word
			if not line.is_empty() and font.get_string_size(candidate, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x > 174.0: result.append(line); line = ""
			for character: String in word:
				var next := character if line.is_empty() else line + character
				if not line.is_empty() and font.get_string_size(next, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x > 174.0: result.append(line); line = ""
				line += character
			if not line.is_empty(): line += " "
		result.append(line.strip_edges())
	return result
