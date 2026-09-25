extends Control
signal advance_requested
signal message_started(stage: String, index: int)
signal message_finished(stage: String, index: int)
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
var layout: Dictionary = {}
var font: Font
var pages: Array[PackedStringArray] = []
var page_index := 0
var active := false
var active_stage := ""
var active_index := -1
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; visible = false
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if manifest is Dictionary: layout = manifest.get("load_game_layout", {})
	font = load("res://assets/menu/native_font.fnt") as Font
func present_message(stage: String, entry: Dictionary) -> void:
	if active: return
	active = true; active_stage = stage; active_index = int(entry.get("index", -1)); pages = _paginate(str(entry.get("text", ""))); page_index = 0; visible = true; message_started.emit(active_stage, active_index)
	for index in range(pages.size()):
		page_index = index; queue_redraw(); await advance_requested
	visible = false; active = false; queue_redraw(); message_finished.emit(active_stage, active_index)
func _unhandled_input(event: InputEvent) -> void:
	if not active or not (event.is_action_pressed("interact") or event.is_action_pressed("ui_accept")): return
	get_viewport().set_input_as_handled(); advance_requested.emit()
func _draw() -> void:
	if not active or font == null or layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	var rectangle := Rect2(16, 158, 288, 68); FRAME.draw(self, layout, "prompt", rectangle)
	if pages.is_empty(): return
	var y := 166.0 + font.get_ascent(12)
	for line in pages[page_index]:
		draw_string(font, Vector2(25, y), line, HORIZONTAL_ALIGNMENT_LEFT, 270, 12, Color.WHITE); y += 14
func _paginate(text: String) -> Array[PackedStringArray]:
	var lines: Array[String] = []
	for source_line in text.replace("\r", "").split("\n"):
		var current := ""
		for word in source_line.split(" ", false):
			var candidate := word if current.is_empty() else current + " " + word
			if not current.is_empty() and font != null and font.get_string_size(candidate, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x > 270:
				lines.append(current); current = word
			else: current = candidate
		lines.append(current)
	var result: Array[PackedStringArray] = []
	for offset in range(0, lines.size(), 3): result.append(PackedStringArray(lines.slice(offset, mini(offset + 3, lines.size()))))
	if result.is_empty(): result.append(PackedStringArray([""]))
	return result
