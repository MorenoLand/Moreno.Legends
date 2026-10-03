extends Control
signal confirmed
signal cancelled
signal moved
const FRAME := preload("res://scripts/ui/common/native_menu_frame.gd")
var layout: Dictionary = {}
var font: Font
var surface: Control
var content: VBoxContainer
var pointer: TextureRect
var prompt := ""
var selection := 0
func configure(text: String) -> void:
	prompt = text; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	layout = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))["load_game_layout"]; font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	content = VBoxContainer.new(); content.position = Vector2(99, 111); content.size = Vector2(126, 32); content.add_theme_constant_override("separation", 0); surface.add_child(content); set_meta("content", content)
	for index in 2:
		var button := Button.new(); button.text = "No" if index == 0 else "Yes"; button.alignment = HORIZONTAL_ALIGNMENT_LEFT; button.custom_minimum_size.y = 16; button.add_theme_font_override("font", font); button.add_theme_font_size_override("font_size", 12); button.add_theme_color_override("font_color", Color(0.72, 0.68, 0.52)); button.add_theme_color_override("font_focus_color", Color.WHITE)
		for state in ["normal", "hover", "pressed", "focus"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.focus_entered.connect(_select.bind(index)); button.mouse_entered.connect(button.grab_focus); button.pressed.connect(_activate.bind(index)); content.add_child(button)
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new(); pointer.configure(Vector2(85, 112)); surface.add_child(pointer)
	resized.connect(_layout); _layout()
func _select(index: int) -> void:
	if index != selection: moved.emit()
	selection = index; pointer.select_at(Vector2(85, 112 + index * 16))
func _activate(index: int) -> void:
	if index == 0: cancelled.emit()
	else: confirmed.emit()
func _input(event: InputEvent) -> void:
	if surface != null and surface.visible and is_visible_in_tree() and not event.is_echo() and event.is_action_pressed("interact"): _activate(selection); get_viewport().set_input_as_handled()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor := size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); surface.size = Vector2(320, 240); queue_redraw()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show(); content.get_child(0).grab_focus()
func animate_exit(context: String) -> void:
	surface.hide(); await FRAME.exit(self, layout, context)
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor); FRAME.draw(self, layout, "prompt", Rect2(76, 87, 168, 60))
	if FRAME.content_visible(self): draw_string(font, Vector2(83, 93 + font.get_ascent(12)), prompt, HORIZONTAL_ALIGNMENT_LEFT, 154, 12, Color.WHITE)
