extends Control
var areas: Array = []
var atlas: Texture2D
var bitmap_mode := false
var stage_directory := ""
var area: Dictionary = {}
var explored: Dictionary = {}
var position_in_area := Vector3.ZERO
var heading := 0.0
var display_enabled := true
var scroll := Vector2.ZERO
var arrow := PackedVector2Array()
var arrow_colors := PackedColorArray([Color8(63, 255, 255), Color8(0, 63, 255), Color8(0, 63, 255)])
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	configure("ST0F")
	set_player(position_in_area, -heading)
func configure(stage: String) -> void:
	areas = []
	area = {}
	explored.clear()
	atlas = null
	bitmap_mode = false
	hide(); queue_redraw()
	var path := "res://assets/minimap/" + stage + "/manifest.json"
	stage_directory = path.get_base_dir()
	if not FileAccess.file_exists(path):
		hide()
		return
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not manifest is Dictionary:
		push_error("Missing original minimap export")
		return
	areas = manifest["areas"]
	bitmap_mode = str(manifest.get("mode", "tiles")) == "bitmap"
	atlas = load(path.get_base_dir().path_join(str(manifest["atlas"]))) as Texture2D
	_refresh_visibility()
func set_display_enabled(value: bool) -> void:
	display_enabled = value
	_refresh_visibility()
# The original draws the HUD map only while the stage or area handler has installed its callback at 0x80078EA8 ("hud" per area).
func _refresh_visibility() -> void:
	visible = display_enabled and atlas != null and not area.is_empty() and bool(area.get("hud", true))
func set_area(index: int) -> void:
	area = {}
	for entry: Dictionary in areas:
		if int(entry["index"]) == index:
			area = entry.duplicate(true); bitmap_mode = area.has("bitmap_origin")
			if bitmap_mode: atlas = load(stage_directory.path_join(str(entry["atlas"]))) as Texture2D
			break
	_refresh_visibility()
	queue_redraw()
func set_player(position: Vector3, yaw: float) -> void:
	position_in_area = position
	heading = -yaw
	var center: Array = area.get("native_center", [0, 0]) if not area.is_empty() else [0, 0]
	var native := Vector2(floorf(-position.x * 4.0) - float(center[0]), float(center[1]) - floorf(position.z * 4.0))
	var limit := Vector2(92, 92) if bitmap_mode else Vector2(8.0 * float(area.get("width", 0)) - 4.0, 8.0 * float(area.get("height", 0)) - 4.0)
	var next_scroll := native.clamp(-limit, limit) if not area.is_empty() else native
	var next_arrow := PackedVector2Array()
	for vertex in [Vector2(0, 6), Vector2(-3, -5), Vector2(3, -5)]:
		var point: Vector2 = vertex.rotated(heading)
		next_arrow.append(Vector2(36, 36) + native - next_scroll + Vector2(floorf(snappedf(point.x, 0.0001)), floorf(snappedf(point.y, 0.0001))))
	var changed := scroll != next_scroll or arrow != next_arrow
	scroll = next_scroll
	arrow = next_arrow
	if not area.is_empty() and not bitmap_mode:
		var column := floori(-position.x / 4.0 + float(area["width"]) * 0.5)
		var row := floori(position.z / 4.0 + float(area["height"]) * 0.5)
		var cell := Vector3i(int(area["index"]), column, row)
		if not explored.has(cell):
			explored[cell] = true
			changed = true
	if changed: queue_redraw()
func _draw() -> void:
	if area.is_empty() or atlas == null: return
	var factor := size.y / 72.0
	draw_set_transform(Vector2.ZERO, 0, Vector2.ONE * factor)
	if area.has("bitmap_origin"):
		var origin: Array = area["bitmap_origin"]; draw_texture_rect(atlas, Rect2(Vector2(36, 36) - scroll + Vector2(float(origin[0]), float(origin[1])), Vector2(256, 256)), false, Color(1.25, 1.25, 1.25, 0.5)); draw_polygon(arrow, arrow_colors)
		var bitmap_outline := arrow.duplicate(); bitmap_outline.append(arrow[0]); draw_polyline(bitmap_outline, Color8(64, 64, 128), 1.0); return
	if not area.has("tiles"): return
	var width := int(area["width"])
	var height := int(area["height"])
	var center := Vector2(36, 36)
	var origin := center - scroll + Vector2(-8 * width, 8 * height - 16)
	var first_column := maxi(floori(-origin.x / 16.0), 0)
	var last_column := mini(ceili((72.0 - origin.x) / 16.0), width)
	var first_row := maxi(floori((origin.y - 72.0) / 16.0) + 1, 0)
	var last_row := mini(ceili((origin.y + 16.0) / 16.0), height)
	for row in range(first_row, last_row):
		for column in range(first_column, last_column):
			var id := int(area["tiles"][row][column])
			if id == 255 or id in [92, 93, 94, 95]: continue
			var seen := explored.has(Vector3i(int(area["index"]), column, row))
			if not seen and int(area["index"]) >= 5: continue
			var offset := Vector2(-8 * width + 16 * column, 8 * height - 16 - 16 * row)
			var color := Color.WHITE if seen else Color(0.375, 0.375, 0.375, 1)
			draw_texture_rect_region(atlas, Rect2(center - scroll + offset, Vector2(16, 16)), Rect2((id & 15) * 16, id & 240, 16, 16), color)
	if arrow.size() != 3: return
	draw_polygon(arrow, arrow_colors)
	var outline := arrow.duplicate()
	outline.append(arrow[0])
	draw_polyline(outline, Color8(64, 64, 128), 1.0)
