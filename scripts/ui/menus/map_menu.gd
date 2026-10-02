extends "res://scripts/ui/menus/info_page.gd"
const VIEW := Rect2(42, 62, 236, 108)
const ZOOMS := [0.5, 1.0, 2.0, 3.0]
const ARROW := [Vector2(0, 6), Vector2(-3, -5), Vector2(3, -5)]
var canvas: Control
var minimap: Control
var view_areas: Array = []
var names: Dictionary = {}
var textures: Dictionary = {}
var current := -1
var view := 0
var zoom_index := 1
var center := Vector2.ZERO
var location := ""
var flutter: Dictionary = {}
var flutter_atlas: Texture2D
func configure(owner: Node) -> void:
	super(owner); footer_rect = Rect2(44, 187, 232, 24)
	canvas = Control.new(); canvas.position = VIEW.position; canvas.size = VIEW.size; canvas.clip_contents = true; canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE; canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; canvas.draw.connect(_draw_canvas); surface.add_child(canvas)
func refresh() -> void:
	var gameplay: Node3D = host.gameplay; minimap = gameplay.game_hud.minimap; location = str(gameplay.get_location_names()["main"]); names.clear(); view_areas.clear(); textures.clear()
	for index in gameplay.areas.size(): names[int(gameplay.areas[index]["index"])] = gameplay.area_picker.get_item_text(index)
	current = int(minimap.area.get("index", -1))
	for entry: Dictionary in minimap.areas:
		var index := int(entry["index"]); var bitmap := entry.has("bitmap_origin")
		if index == current or bitmap and bool(entry.get("hud", true)) or not bitmap and _visited(index): view_areas.append(entry)
	flutter = {}
	if view_areas.is_empty() and FileAccess.file_exists("res://assets/minimap/Flutter/manifest.json"):
		var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/minimap/Flutter/manifest.json")); var stage := str(gameplay.manifest_path.get_base_dir().get_file())
		if source["stages"].has(stage):
			flutter = source; flutter["entry"] = source["entries"][int(source["stages"][stage]) + int(gameplay.areas[gameplay.area_picker.selected]["index"])]; flutter_atlas = load("res://assets/minimap/Flutter/" + str(source["atlas"])) as Texture2D; current = int(flutter["entry"]["deck"])
			for deck in source["decks"].size(): view_areas.append({"index": deck, "flutter": true})
	view = 0
	for index in view_areas.size(): if int(view_areas[index]["index"]) == current: view = index
	zoom_index = 1; _focus_player(); set_footer("Move: Pan   Enter: Zoom   PgUp/PgDn: Area   Home: Center"); canvas.visible = not view_areas.is_empty(); canvas.queue_redraw(); queue_redraw()
func _visited(index: int) -> bool:
	for cell: Vector3i in minimap.explored: if cell.x == index: return true
	return false
func _bounds(entry: Dictionary) -> Rect2:
	if entry.has("flutter"): return Rect2(-72, -80, 144, 160)
	if entry.has("bitmap_origin"): return Rect2(Vector2(float(entry["bitmap_origin"][0]), float(entry["bitmap_origin"][1])), Vector2(256, 256))
	return Rect2(Vector2(-8.0 * float(entry["width"]), -8.0 * float(entry["height"])), Vector2(16.0 * float(entry["width"]), 16.0 * float(entry["height"])))
func flutter_marker() -> Vector2:
	var entry: Dictionary = flutter["entry"]; var marker := Vector2(float(entry["x"]), float(entry["y"]))
	if int(entry["rule"]) == 255: return marker
	var rule: Dictionary = flutter["rules"][int(entry["rule"])]; var point: Vector3 = minimap.position_in_area; var z_cell := str(((roundi(point.z * 256.0) + 0x8000) & 0xFFFF) >> 9); var x_cell := str(((roundi(-point.x * 256.0) + 0x8000) & 0xFFFF) >> 9)
	if rule["y_by_z_cell"].has(z_cell): marker.y = float(rule["y_by_z_cell"][z_cell]); return marker
	if rule.has("x_by_x_cell"): marker.x = float(rule["x_by_x_cell"].get(x_cell, rule["default_x"]))
	marker.y = float(rule["default_y"]); return marker
func player_native() -> Vector2:
	if not flutter.is_empty(): return flutter_marker()
	var area_center: Array = minimap.area.get("native_center", [0, 0]); var point: Vector3 = minimap.position_in_area
	return Vector2(floorf(-point.x * 4.0) - float(area_center[0]), float(area_center[1]) - floorf(point.z * 4.0))
func _here() -> bool: return not view_areas.is_empty() and int(view_areas[view]["index"]) == current
func _focus_player() -> void:
	if view_areas.is_empty(): return
	var bounds := _bounds(view_areas[view]); center = player_native().clamp(bounds.position, bounds.end) if _here() else bounds.get_center()
func _pan(amount: Vector2) -> void:
	var bounds := _bounds(view_areas[view]); center = (center + amount).clamp(bounds.position, bounds.end); canvas.queue_redraw()
func _switch(direction: int) -> void:
	if view_areas.size() < 2: return
	view = posmod(view + direction, view_areas.size()); host.audio.play_ui("menu_move"); _focus_player(); canvas.queue_redraw(); queue_redraw()
func _zoom(step: int, wrap: bool = false) -> void:
	var next := posmod(zoom_index + step, ZOOMS.size()) if wrap else clampi(zoom_index + step, 0, ZOOMS.size() - 1)
	if next != zoom_index: zoom_index = next; host.audio.play_ui("menu_move"); canvas.queue_redraw()
func _process(delta: float) -> void:
	super(delta)
	if not is_visible_in_tree() or not surface.visible or view_areas.is_empty(): return
	var direction := Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	if direction != Vector2.ZERO: _pan(direction * 140.0 * delta / float(ZOOMS[zoom_index]))
func _gui_input(event: InputEvent) -> void:
	super(event)
	if view_areas.is_empty(): return
	if event.is_action_pressed("ui_page_down"): _switch(1); accept_event()
	elif event.is_action_pressed("ui_page_up"): _switch(-1); accept_event()
	elif event.is_action_pressed("ui_accept"): _zoom(1, true); accept_event()
	elif event.is_action_pressed("ui_home"): _focus_player(); canvas.queue_redraw(); accept_event()
	elif event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		if event.pressed: _zoom(1 if event.button_index == MOUSE_BUTTON_WHEEL_UP else -1)
		accept_event()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		var point := _native(event.position); dragging_bar = event.pressed and VIEW.has_point(point)
		if event.pressed:
			if Rect2(36, 34, 20, 14).has_point(point): _switch(-1)
			elif Rect2(264, 34, 20, 14).has_point(point): _switch(1)
		accept_event()
	elif event is InputEventMouseMotion and dragging_bar: _pan(-event.relative / (size.y / 240.0) / float(ZOOMS[zoom_index])); accept_event()
func _draw_canvas() -> void:
	if view_areas.is_empty(): return
	var entry: Dictionary = view_areas[view]; var zoom: float = ZOOMS[zoom_index]; var bounds := _bounds(entry); var index := int(entry["index"])
	canvas.draw_rect(Rect2(Vector2.ZERO, canvas.size), Color8(30, 38, 56)); canvas.draw_set_transform(canvas.size * 0.5 - center * zoom, 0, Vector2.ONE * zoom)
	if entry.has("flutter"):
		for sprite: Dictionary in flutter["decks"][index]: canvas.draw_texture_rect_region(flutter_atlas, Rect2(float(sprite["x"]), float(sprite["y"]), float(sprite["width"]), float(sprite["height"])), Rect2(float(sprite["u"]), float(sprite["v"]), float(sprite["width"]), float(sprite["height"])))
	elif entry.has("bitmap_origin"):
		var path: String = minimap.stage_directory.path_join(str(entry["atlas"]))
		if not textures.has(path): textures[path] = load(path) as Texture2D
		canvas.draw_texture_rect(textures[path], bounds, false)
	else:
		canvas.draw_rect(bounds, Color8(162, 192, 217)); var width := int(entry["width"]); var height := int(entry["height"])
		for row in height:
			for column in width:
				var id := int(entry["tiles"][row][column])
				if id == 255 or id in [92, 93, 94, 95]: continue
				var seen: bool = minimap.explored.has(Vector3i(index, column, row))
				if not seen and index >= 5: continue
				canvas.draw_texture_rect_region(minimap.atlas, Rect2(Vector2(-8 * width + 16 * column, 8 * height - 16 - 16 * row), Vector2(16, 16)), Rect2((id & 15) * 16, id & 240, 16, 16), Color.WHITE if seen else Color(0.375, 0.375, 0.375, 1))
	canvas.draw_set_transform(Vector2.ZERO, 0, Vector2.ONE)
	if index != current: return
	var origin := (canvas.size * 0.5 + (player_native() - center) * zoom).round(); var arrow := PackedVector2Array()
	for vertex: Vector2 in ARROW:
		var rotated := vertex.rotated(minimap.heading); arrow.append(origin + Vector2(floorf(snappedf(rotated.x, 0.0001)), floorf(snappedf(rotated.y, 0.0001))))
	canvas.draw_polygon(arrow, minimap.arrow_colors); arrow.append(arrow[0]); canvas.draw_polyline(arrow, Color8(64, 64, 128), 1.0)
func _frames() -> void:
	_chrome_frames(); FRAME.draw(self, layout, "prompt", Rect2(36, 34, 248, 14)); FRAME.draw(self, layout, "selector", Rect2(36, 56, 248, 120)); FRAME.draw(self, layout, "prompt", Rect2(36, 184, 248, 30))
func _content() -> void:
	_chrome_content("Map", "map", "Q/E: Page   Esc: Back")
	if view_areas.is_empty(): _text(location, Vector2(44, 37), 9, Color.WHITE, 232); _text("No map data", Vector2(36, 110), 12, Color8(128, 128, 128), 248, HORIZONTAL_ALIGNMENT_CENTER); return
	var index := int(view_areas[view]["index"]); var area := "Deck %d" % (index + 1) if not flutter.is_empty() else str(names.get(index, "Area %d" % index)); var label := location if area == location else location + " - " + area; _text(label + ("  (You are here)" if index == current else ""), Vector2(48, 37), 9, Color.WHITE, 190)
	if view_areas.size() > 1:
		_text("%d / %d" % [view + 1, view_areas.size()], Vector2(222, 37), 9, Color.WHITE, 48, HORIZONTAL_ALIGNMENT_RIGHT)
		for side in [-1.0, 1.0]:
			var x := 42.0 if side < 0 else 278.0
			draw_colored_polygon(PackedVector2Array([Vector2(x + 3.0 * side, 41), Vector2(x - 3.0 * side, 38), Vector2(x - 3.0 * side, 44)]), Color8(255, 222, 99))
