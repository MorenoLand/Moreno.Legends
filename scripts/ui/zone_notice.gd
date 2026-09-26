extends Label
var fade: Tween
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	offset_top = 52; offset_bottom = 128
	horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_theme_font_override("font", load("res://assets/menu/native_font.fnt"))
	add_theme_color_override("font_shadow_color", Color.BLACK)
	add_theme_constant_override("shadow_offset_x", 2)
	add_theme_constant_override("shadow_offset_y", 2)
	modulate.a = 0.0
func announce(main_area: String, subarea: String) -> void:
	if fade != null and fade.is_valid(): fade.kill()
	var repeats := subarea.strip_edges().to_lower() == main_area.strip_edges().to_lower()
	text = main_area + ("\n" + subarea if not subarea.is_empty() and not subarea.begins_with("Area ") and not repeats else "")
	add_theme_font_size_override("font_size", maxi(12, roundi(get_viewport_rect().size.y / 240.0 * 10.0)))
	modulate.a = 0.0
	fade = create_tween()
	fade.tween_property(self, "modulate:a", 1.0, 0.35)
	fade.tween_interval(2.0)
	fade.tween_property(self, "modulate:a", 0.0, 0.5)
