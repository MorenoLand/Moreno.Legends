extends Control
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
const GOLD := Color8(255, 222, 99)
const FRAME_LIGHT := Color(0.76, 0.79, 0.69)
const FRAME_DARK := Color(0.16, 0.16, 0.23)
var layout: Dictionary = {}
var font: Font
var gear: Texture2D
var title := ""
var state := ""
var received := 0
var total := 0
var elapsed := 0.0
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	process_mode = Node.PROCESS_MODE_ALWAYS
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	font = load("res://assets/menu/native_font.fnt") as Font
	gear = load("res://assets/menu/" + str(manifest["sprites"]["native_gear_background"]["file"])) as Texture2D
func _process(delta: float) -> void:
	if not is_visible_in_tree(): return
	elapsed += delta
	queue_redraw()
func _megabytes(bytes: int) -> String:
	return "%.1f" % (float(bytes) / 1048576.0)
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	var phase: int = (int(elapsed * 30.0) >> 1) & 63
	draw_texture_rect(gear, Rect2(Vector2(-offset.x / factor, 0) + Vector2(phase - 80, phase - 80), Vector2(size.x / factor, 240) + Vector2(160, 160)), true)
	FRAME.draw(self, layout, "prompt", Rect2(34, 88, 252, 64))
	draw_string(font, Vector2(46, 96 + font.get_ascent(12)), title, HORIZONTAL_ALIGNMENT_LEFT, 228, 12, Color.WHITE)
	var bar := Rect2(47, 120, 226, 8)
	draw_rect(bar.grow(1.0), FRAME_DARK)
	draw_rect(bar.grow(1.0), Color(FRAME_LIGHT, 0.8), false, 1.0)
	if total > 0: draw_rect(Rect2(bar.position, Vector2(roundf(bar.size.x * clampf(float(received) / float(total), 0.0, 1.0)), bar.size.y)), GOLD)
	else: draw_rect(Rect2(bar.position.x + fposmod(elapsed * 120.0, bar.size.x - 40.0), bar.position.y, 40, bar.size.y), GOLD)
	var detail := state if total <= 0 or state != "Downloading" else "%s  %s / %s MB" % [state, _megabytes(received), _megabytes(total)]
	draw_string(font, Vector2(46, 134 + font.get_ascent(10)), detail, HORIZONTAL_ALIGNMENT_LEFT, 228, 10, GOLD)
