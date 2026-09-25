extends Control
var layout: Dictionary = {}
var surface: Control
var content: VBoxContainer
const FRAME = preload("res://scripts/ui/native_menu_frame.gd")
func configure() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	content = VBoxContainer.new()
	content.position = Vector2(110, 79)
	content.size = Vector2(100, 82)
	content.add_theme_constant_override("separation", 3)
	surface.add_child(content)
	set_meta("content", content)
	resized.connect(_layout)
	_layout()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0
	draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "selector", Rect2(98, 70, 124, 100))
