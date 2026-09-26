extends Control
var host: Node
var map: Control
var pan := Vector2.ZERO
var zoom := 1.0
var dragging := false
var source_area_index := -1
var source_records: Array = []
var source_bounds := Rect2()
const SOURCE_FLOOR = preload("res://scripts/world/native_floor.gd")
func configure(owner: Node) -> void:
	host = owner
	process_mode = Node.PROCESS_MODE_ALWAYS
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	clip_contents = true
func refresh() -> void:
	map = host.gameplay.game_hud.minimap
	pan = Vector2.ZERO
	zoom = 1.0
	_refresh_source_area()
	queue_redraw()
func center_player() -> void:
	if _has_tiles(): pan = -Vector2(-map.position_in_area.x * 4.0, -map.position_in_area.z * 4.0) * _scale()
	elif not source_records.is_empty(): pan = -(_source_player_position() - source_bounds.get_center()) * _scale()
	else: return
	queue_redraw()
func _scale() -> float:
	if _has_tiles(): return minf(size.x / maxf(float(map.area["width"]) * 16, 1.0), size.y / maxf(float(map.area["height"]) * 16, 1.0)) * zoom
	if source_bounds.size.x > 0.0 and source_bounds.size.y > 0.0: return minf(maxf(size.x - 16.0, 1.0) / source_bounds.size.x, maxf(size.y - 16.0, 1.0) / source_bounds.size.y) * zoom
	return 1.0
func _draw() -> void:
	if _has_tiles(): _draw_tiles()
	else: _draw_source_floorplan()
func _draw_tiles() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color8(162, 192, 217))
	var scale := _scale()
	var center := size * 0.5 + pan
	var width := int(map.area["width"])
	var height := int(map.area["height"])
	for row in range(height):
		for column in range(width):
			var id := int(map.area["tiles"][row][column])
			if id in [255, 92, 93, 94, 95]: continue
			var seen: bool = map.explored.has(Vector3i(int(map.area["index"]), column, row))
			var point := Vector2(-8 * width + column * 16, 8 * height - 16 - row * 16)
			draw_texture_rect_region(map.atlas, Rect2(center + point * scale, Vector2.ONE * 16 * scale), Rect2((id & 15) * 16, id & 240, 16, 16), Color.WHITE if seen else Color(0.375, 0.375, 0.375))
	var position: Vector2 = center + Vector2(-map.position_in_area.x * 4.0, -map.position_in_area.z * 4.0) * scale
	var arrow := PackedVector2Array()
	for point in [Vector2(0, 6), Vector2(-3, -5), Vector2(3, -5)]: arrow.append(position + point.rotated(map.heading))
	draw_polygon(arrow, map.arrow_colors)
	arrow.append(arrow[0])
	draw_polyline(arrow, Color8(64, 64, 128), 1.0)
func _draw_source_floorplan() -> void:
	if source_records.is_empty() or source_bounds.size.x <= 0.0 or source_bounds.size.y <= 0.0: return
	draw_rect(Rect2(Vector2.ZERO, size), Color8(162, 192, 217))
	var scale := _scale(); var center := size * 0.5 + pan; var source_center := source_bounds.get_center()
	for record: Dictionary in source_records:
		var footprint: Array[Vector2] = SOURCE_FLOOR._footprint(int(record["kind"]), record["x"], record["z"]); var polygon := PackedVector2Array()
		for point: Vector2 in footprint: polygon.append(center + (Vector2(point.x, -point.y) - source_center) * scale)
		if polygon.size() < 3: continue
		draw_colored_polygon(polygon, Color(0.36, 0.54, 0.67, 0.72)); var outline := polygon.duplicate(); outline.append(polygon[0]); draw_polyline(outline, Color8(48, 74, 96), 1.0)
	var position := center + (_source_player_position() - source_center) * scale; var arrow := PackedVector2Array()
	for point in [Vector2(0, 6), Vector2(-3, -5), Vector2(3, -5)]: arrow.append(position + point.rotated(_source_player_heading()))
	draw_polygon(arrow, PackedColorArray([Color8(63, 255, 255), Color8(0, 63, 255), Color8(0, 63, 255)])); arrow.append(arrow[0]); draw_polyline(arrow, Color8(64, 64, 128), 1.0)
func _has_tiles() -> bool: return map != null and is_instance_valid(map) and not map.area.is_empty() and map.atlas != null
func _current_area_index() -> int:
	if host == null or not is_instance_valid(host) or host.gameplay == null or host.gameplay.area_picker.selected < 0: return -1
	return int(host.gameplay.areas[host.gameplay.area_picker.selected]["index"])
func _refresh_source_area() -> void:
	source_area_index = _current_area_index(); source_records.clear(); source_bounds = Rect2()
	if source_area_index < 0: return
	var boxes: Array = host.gameplay.native_floor_collision.get(str(source_area_index), {}).get("boxes", []); var has_bounds := false
	for record: Dictionary in boxes:
		if int(record.get("kind", 0)) >= 0x100 or int(record.get("mask", 0)) == 0: continue
		var x: Array = record["x"]; var z: Array = record["z"]; var x0 := minf(float(x[0]), float(x[1])); var x1 := maxf(float(x[0]), float(x[1])); var z0 := minf(float(z[0]), float(z[1])); var z1 := maxf(float(z[0]), float(z[1])); var first := Vector2(x0, -z1); var last := Vector2(x1, -z0)
		if not has_bounds: source_bounds = Rect2(first, last - first); has_bounds = true
		else: source_bounds = source_bounds.expand(first).expand(last)
		source_records.append(record)
func _source_player_position() -> Vector2:
	var context: Dictionary = host.gameplay.native_context; var raw: Array = context.get("native_player_pose_raw", [])
	if raw.size() >= 3: return Vector2(float(raw[0]), -float(raw[2]))
	var point: Vector3 = host.gameplay._room_local_position(); return Vector2(-point.x * 256.0, -point.z * 256.0)
func _source_player_heading() -> float: return -float(host.gameplay.player.player_model.rotation.y)
func _process(_delta: float) -> void:
	if not visible or host == null or not is_instance_valid(host) or host.gameplay == null: return
	var current_map: Control = host.gameplay.game_hud.minimap
	if current_map != map: map = current_map
	var area_index := _current_area_index()
	if not _has_tiles() and area_index != source_area_index: _refresh_source_area()
	queue_redraw()
func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT: dragging = event.pressed
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]: zoom = clampf(zoom * (1.2 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.2), 0.5, 4.0); queue_redraw()
	elif event is InputEventMouseMotion and dragging: pan += event.relative; queue_redraw()
	accept_event()
