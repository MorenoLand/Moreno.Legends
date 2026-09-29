extends TextureRect
static var animation: Dictionary = {}
var cursor_origin := Vector2.ZERO
var cursor_point := Vector2.ZERO
var selection_steps := Vector2.ZERO
var has_selection := false
var elapsed := 0.0
var ticks := 0
func configure(origin: Vector2) -> void:
	if animation.is_empty(): animation = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))["hand_cursor_animation"]
	texture = load("res://assets/menu/" + str(animation["file"])) as Texture2D
	expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	size = Vector2(12, 12)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	cursor_origin = origin
	cursor_point = origin
	position = origin
func select_at(point: Vector2) -> void:
	point = point.round()
	if has_selection and point == cursor_origin: return
	cursor_origin = point
	if not has_selection: position += point - cursor_point; cursor_point = point; has_selection = true; return
	for axis in range(2):
		var delta: int = roundi(cursor_origin[axis] - cursor_point[axis])
		var step: int = floori(float(delta) / 2.0) if absi(delta) >= 4 else 1 if delta >= 0 else -1
		step &= 255
		selection_steps[axis] = step - 256 if step >= 128 else step
func _process(delta: float) -> void:
	elapsed += delta
	var interval: float = 1.0 / float(animation["tick_rate"])
	if elapsed >= interval:
		ticks = (ticks + 1) & 65535; elapsed = fmod(elapsed, interval)
		for axis in range(2):
			cursor_point[axis] += selection_steps[axis]
			if selection_steps[axis] > 0 and cursor_point[axis] > cursor_origin[axis] or selection_steps[axis] < 0 and cursor_point[axis] < cursor_origin[axis]: cursor_point[axis] = cursor_origin[axis]; selection_steps[axis] = 0
	var phase: int = (ticks >> int(animation["phase_shift"])) % animation["wave"].size()
	position = cursor_point + Vector2(int(animation["wave"][phase]) + int(animation["x_bias"]), 0)
