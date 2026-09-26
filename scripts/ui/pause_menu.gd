extends Control
var layout: Dictionary = {}
var surface: Control
var content: VBoxContainer
var font: Font
var pointer: TextureRect
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
func configure() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	content = VBoxContainer.new()
	content.position = Vector2(100, 68)
	content.size = Vector2(120, 0)
	content.add_theme_constant_override("separation", 2)
	content.minimum_size_changed.connect(queue_redraw)
	surface.add_child(content)
	set_meta("content", content)
	pointer = preload("res://scripts/ui/native_menu_cursor.gd").new()
	pointer.configure(Vector2.ZERO)
	pointer.hide()
	surface.add_child(pointer)
	resized.connect(_layout)
	_layout()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide()
	await FRAME.exit(self, layout, context)
func focus_first() -> void:
	for child in content.get_children():
		if child is Button and not child.disabled: child.grab_focus(); return
func select_button(button: Button) -> void:
	pointer.select_at(content.position + button.position + Vector2(2, (button.size.y - 12) * 0.5))
	pointer.show()
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "header", Rect2(88, 25, 144, 24))
	FRAME.draw(self, layout, "selector", Rect2(88, 60, 144, content.get_combined_minimum_size().y + 12))
	if FRAME.content_visible(self): draw_string(font, Vector2(100, 32 + font.get_ascent(12)), "Pause", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
