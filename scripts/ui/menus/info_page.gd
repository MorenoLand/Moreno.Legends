extends Control
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
signal closed
signal page_requested(direction: int)
const TABS := {"inventory": "Items", "equipment": "Equip", "map": "Map"}
var host: Node
var layout: Dictionary = {}
var font: Font
var surface: Control
var pointer: TextureRect
var footer: Label
var footer_clip: Control
var footer_rect := Rect2(44, 200, 232, 28)
var footer_time := 0.0
var dragging_bar := false
var grab_offset := 0.0
func configure(owner: Node) -> void:
	host = owner; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; focus_mode = Control.FOCUS_ALL
	for property in ["focus_neighbor_left", "focus_neighbor_top", "focus_neighbor_right", "focus_neighbor_bottom", "focus_next", "focus_previous"]: set(property, NodePath("."))
	layout = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))["load_game_layout"]; font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new(); pointer.configure(Vector2(40, 42)); pointer.hide(); surface.add_child(pointer)
	footer_clip = Control.new(); footer_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE; footer_clip.clip_contents = true; surface.add_child(footer_clip)
	footer = Label.new(); footer.mouse_filter = Control.MOUSE_FILTER_IGNORE; footer.add_theme_font_override("font", font); footer.add_theme_font_size_override("font_size", 9); footer.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; footer_clip.add_child(footer)
	resized.connect(_layout); visibility_changed.connect(func(): if visible: call_deferred("grab_focus")); _layout()
func set_footer(text: String) -> void:
	footer.text = text; footer_time = 0.0; footer.position.y = 0.0
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); surface.size = Vector2(320, 240); queue_redraw()
func _native(point: Vector2) -> Vector2:
	var factor: float = size.y / 240.0
	return (point - Vector2((size.x - 320.0 * factor) * 0.5, 0)) / factor
func _process(delta: float) -> void:
	if not is_visible_in_tree(): return
	# The footer shows whole lines only and steps a line at a time, so no line is ever cut through the middle.
	footer_time += delta; footer_clip.position = footer_rect.position; footer.size.x = footer_rect.size.x
	var line_height := float(footer.get_line_height() + footer.get_theme_constant("line_spacing")); var shown := maxi(1, floori(footer_rect.size.y / line_height)); var hidden := maxi(footer.get_line_count() - shown, 0)
	footer_clip.size = Vector2(footer_rect.size.x, shown * line_height); footer_clip.position.y = footer_rect.position.y + floorf((footer_rect.size.y - footer_clip.size.y) * 0.5); footer.size.y = maxf(footer.get_line_count() * line_height, footer_clip.size.y)
	footer.position.y = -line_height * mini(int(footer_time / 1.6) % (hidden + 2), hidden)
func _gui_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"): closed.emit(); accept_event()
	elif event.is_action_pressed("menu_page_prev") or event.is_action_pressed("menu_page_next"): page_requested.emit(-1 if event.is_action_pressed("menu_page_prev") else 1); accept_event()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide(); await FRAME.exit(self, layout, context)
func _text(value: String, point: Vector2, font_size: int = 9, color: Color = Color.WHITE, width: float = -1.0, alignment: int = HORIZONTAL_ALIGNMENT_LEFT) -> void:
	draw_string(font, point + Vector2(0, font.get_ascent(font_size)), value, alignment, width, font_size, color)
func _track(list: Rect2) -> Rect2: return Rect2(list.end.x + 6.0, list.position.y + 1.0, 3.0, list.size.y - 2.0)
func _thumb(track: Rect2, shown: float, total: float, offset: float) -> Rect2:
	var thumb := maxf(8.0, track.size.y * shown / total)
	return Rect2(track.position.x, track.position.y + (track.size.y - thumb) * offset / (total - shown), track.size.x, thumb)
func _draw_bar(list: Rect2, shown: float, total: float, offset: float) -> void:
	if total <= shown: return
	var track := _track(list)
	draw_rect(track.grow(1.0), Color(0.16, 0.16, 0.23)); draw_rect(track.grow(1.0), Color(0.76, 0.79, 0.69, 0.7), false, 1.0); draw_rect(_thumb(track, shown, total, offset), Color(0.76, 0.79, 0.69))
func _chrome_frames() -> void:
	FRAME.draw(self, layout, "header", Rect2(20, 4, 112, 22)); FRAME.draw(self, layout, "prompt", Rect2(140, 6, 160, 18)); FRAME.draw(self, layout, "prompt", Rect2(36, 222, 248, 14))
func _chrome_content(title: String, page: String, hint: String) -> void:
	FRAME.title(self, font, title, Rect2(20, 4, 112, 22)); _text("Q", Vector2(146, 11), 8, Color8(150, 205, 220)); _text("E", Vector2(288, 11), 8, Color8(150, 205, 220))
	var x := 160.0
	for key: String in TABS:
		_text(TABS[key], Vector2(x, 11), 9, Color8(255, 222, 99) if key == page else Color8(128, 128, 128), 40, HORIZONTAL_ALIGNMENT_CENTER); x += 44.0
	_text(hint, Vector2(36, 226), 8, Color(1, 1, 1, 0.75), 248, HORIZONTAL_ALIGNMENT_CENTER)
static func life_gauge(canvas: Control, origin: Vector2, health: int, max_health: int, width: float, height: float = 6.0) -> void:
	var peak := maxi(max_health * 5 / 16 - 1, 1); var filled := clampi((health * 5 + 15) / 16, 0, peak); var count := maxi(max_health / 16, 1); var pitch := width / float(count); var gap := 2.0 if pitch >= 6.0 else 1.0
	for index in count:
		var cells := mini(5, peak - index * 5); var x := origin.x + float(index) * pitch; var span := pitch - gap
		if cells <= 0: break
		canvas.draw_rect(Rect2(x, origin.y, span, height), Color8(48, 96, 96))
		var amount := span * clampf(float(filled - index * 5) / float(cells), 0.0, 1.0)
		if amount > 0.0: canvas.draw_rect(Rect2(x, origin.y, amount, height), Color8(214, 138, 74)); canvas.draw_rect(Rect2(x, origin.y, amount, height * 0.5), Color8(255, 222, 99))
func _frames() -> void: pass
func _content() -> void: pass
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	_frames()
	if FRAME.content_visible(self): _content()
