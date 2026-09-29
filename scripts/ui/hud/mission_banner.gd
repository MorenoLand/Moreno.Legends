extends Control
var data: Dictionary = {}
var atlas: Texture2D
var origin := Vector2i.ZERO
var style: Dictionary = {}
var letters: Array[Dictionary] = []
var elapsed := 0.0
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; visible = false
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/hud/mission_banner.json"))
	if parsed is Dictionary: data = parsed; atlas = load("res://assets/hud/" + str(data["atlas"])) as Texture2D
func show_banner(x: int, y: int, index: int) -> void:
	if atlas == null or index < 0 or index >= data["styles"].size(): return
	origin = Vector2i(x, y); style = data["styles"][index]; letters.clear(); elapsed = 0.0
	for element: Dictionary in style["elements"]: letters.append({"radius": int(element["radius"]), "offset": Vector2i.ZERO, "blend": false})
	visible = true; _tick()
func hide_banner() -> void:
	visible = false; letters.clear()
func _process(delta: float) -> void:
	if not visible: return
	elapsed += delta * float(data["tick_hz"])
	while elapsed >= 1.0: elapsed -= 1.0; _tick()
func _tick() -> void:
	var step := int(style["radius_step"]); var radial := str(style["motion"]) == "radial"
	for index in letters.size():
		var letter := letters[index]; var element: Dictionary = style["elements"][index]; var base := Vector2i(int(element["offset"][0]), int(element["offset"][1]))
		letter["blend"] = int(letter["radius"]) != 0; var radius := maxi(int(letter["radius"]) - step, 0); letter["radius"] = radius
		letter["offset"] = base + (Vector2i((radius * int(element["sin"])) >> 11, (radius * int(element["cos"])) >> 11) if radial else Vector2i(0, radius * 2))
	queue_redraw()
func _draw() -> void:
	if letters.is_empty(): return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	var top := int(data["atlas_uv"][1])
	for index in letters.size():
		var letter := letters[index]; var uv: Array = style["elements"][index]["uv"]; var at: Vector2i = origin + letter["offset"]
		draw_texture_rect_region(atlas, Rect2(at.x, at.y, int(uv[2]), int(uv[3])), Rect2(int(uv[0]), int(uv[1]) - top, int(uv[2]), int(uv[3])), Color(1, 1, 1, 0.5) if letter["blend"] else Color.WHITE)
