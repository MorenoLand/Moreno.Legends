extends Control
signal closed
signal changed(key: String, value: int)
signal defaults_reset
var manifest: Dictionary = {}
var layout: Dictionary = {}
var atlases: Dictionary = {}
var values: Dictionary = {}
var hit_regions: Array = []
var selected_row := 0:
	set(value):
		if selected_row != value: selected_column = 0
		selected_row = clampi(value, 0, 8)
var selected_column := 0
var screen_adjust := false
var screen_saved := Vector2i.ZERO
var dragging := ""
var gear_background: Texture2D
var gear_elapsed: float = 0.0
var font: Font
var settings: ConfigFile
var descriptions := ["Select controller layout.", "Select camera direction.", "Select lock-on control.", "Turn vibration on or off.", "Select sound output.", "Adjust BGM and SE volume.", "Adjust screen position.", "Restore default settings.", "Return to the previous menu."]
func configure(config: ConfigFile) -> void:
	settings = config
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if not data is Dictionary: return
	manifest = data
	layout = manifest["options_layout"]
	font = load("res://assets/menu/native_font.fnt") as Font
	gear_background = load("res://assets/menu/" + str(manifest["sprites"]["native_gear_background"]["file"])) as Texture2D
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	for key in manifest["sprites"]:
		var entry: Dictionary = manifest["sprites"][key]
		if not key.begins_with("options_") or not entry["source"].has("clut"): continue
		var clut := int(entry["source"]["clut"])
		var texture := load("res://assets/menu/" + str(entry["file"])) as Texture2D
		if clut in [0x7f50, 0x7f51, 0x7f91]:
			var image := texture.get_image()
			if image.is_compressed(): image.decompress()
			var foreground := Vector3i(165, 140, 140) if clut == 0x7f50 else Vector3i(140, 148, 156)
			for y in range(image.get_height()):
				for x in range(image.get_width()):
					var pixel := image.get_pixel(x, y)
					if Vector3i(pixel.r8, pixel.g8, pixel.b8) == foreground: image.set_pixel(x, y, Color(1, 1, 1, pixel.a))
			texture = ImageTexture.create_from_image(image)
		atlases[clut] = texture
	for key in layout["roles"]["bindings"]:
		var binding: Dictionary = layout["roles"]["bindings"][key]
		binding["bar_fill_indices"] = PackedInt32Array(binding.get("bar_fill_indices", []))
		values[key] = int(settings.get_value("game", key, 1 if key == "view" else int(binding["default"])))
		for choice: Dictionary in binding.get("choices", []):
			choice["primitive_indices"] = PackedInt32Array(choice["primitive_indices"])
			if key == "controller" and int(choice["value"]) == 3: continue
			var primitive: Dictionary = layout["primitives"][int(choice["primitive_indices"][0])]
			hit_regions.append({"key": key, "value": int(choice["value"]), "rect": Rect2(Vector2(primitive["xy"][0], primitive["xy"][1]), Vector2(primitive["size"][0], primitive["size"][1]))})
	values["screen_x"] = int(settings.get_value("game", "screen_x", 0))
	values["screen_y"] = int(settings.get_value("game", "screen_y", 0))
	queue_redraw()
func _native_offset() -> Vector2:
	return Vector2((size.x - 320.0 * size.y / 240.0) * 0.5, 0)
func _draw() -> void:
	if layout.is_empty(): return
	var factor := size.y / 240.0
	if factor <= 0: return
	draw_set_transform(_native_offset(), 0, Vector2.ONE * factor)
	if gear_background != null:
		var phase: int = (int(gear_elapsed * 30.0) >> 1) & 63
		var origin := Vector2(phase - 80, phase - 80)
		draw_texture_rect(gear_background, Rect2(Vector2(-_native_offset().x / factor, 0) + origin, Vector2(size.x / factor, 240) + Vector2(160, 160)), true)
	if screen_adjust:
		draw_rect(Rect2(0, 0, 320, 240), Color(0, 0, 0, 0.5))
		for x in range(0, 320, 16): draw_line(Vector2(x, 0), Vector2(x, 240), Color(0.502, 0.502, 0.502), 1.0)
		for y in range(0, 240, 16): draw_line(Vector2(0, y), Vector2(320, y), Color(0.502, 0.502, 0.502), 1.0)
		var marker: Texture2D = atlases.get(0x7f10)
		if marker != null:
			for index in range(4): draw_texture_rect_region(marker, Rect2(Vector2(8 if index % 2 == 0 else 296, 8 if index < 2 else 216), Vector2(16, 16)), Rect2(192 + index * 16, 144, 16, 16))
		draw_rect(Rect2(56, 60, 212, 97), Color(0, 0, 0, 0.5))
		draw_string(font, Vector2(64, 82), "Adjust screen position.", HORIZONTAL_ALIGNMENT_LEFT, 196, 12, Color.WHITE)
		draw_string(font, Vector2(64, 106), "Arrows move the screen", HORIZONTAL_ALIGNMENT_LEFT, 196, 12, Color.WHITE)
		draw_string(font, Vector2(64, 130), "Enter saves  Esc cancels", HORIZONTAL_ALIGNMENT_LEFT, 196, 12, Color.WHITE)
		return
	for index in range(layout["primitives"].size()):
		var primitive: Dictionary = layout["primitives"][index]
		var opcode := str(primitive["opcode"])
		if opcode not in ["0x64", "0x2c"]: continue
		var clut := int(str(primitive["clut"]).hex_to_int())
		var source := Rect2()
		var rectangle := Rect2()
		if opcode == "0x64":
			rectangle = Rect2(Vector2(primitive["xy"][0], primitive["xy"][1]), Vector2(primitive["size"][0], primitive["size"][1]))
			source = Rect2(Vector2(primitive["uv"][0], primitive["uv"][1]), rectangle.size)
		else:
			var xy: Array = primitive["xy"]
			var uv: Array = primitive["uv"]
			rectangle = Rect2(Vector2(xy[0][0], xy[0][1]), Vector2(xy[3][0] - xy[0][0], xy[3][1] - xy[0][1]))
			source = Rect2(Vector2(uv[0][0], uv[0][1]), Vector2(uv[3][0] - uv[0][0], uv[3][1] - uv[0][1]))
		for key in layout["roles"]["bindings"]:
			var binding: Dictionary = layout["roles"]["bindings"][key]
			for choice: Dictionary in binding.get("choices", []):
				if index in choice["primitive_indices"]: clut = 0x7f50 if values[key] == choice["value"] else 0x7f51
			if index in binding.get("bar_fill_indices", []):
				rectangle.size.x = 8 + 3 * ((int(values[key]) + 7) >> 3)
				source.size.x = rectangle.size.x
		if index >= 68 and index <= 76: clut = 0x7f13 if index - 68 == selected_row else 0x7f12
		var texture: Texture2D = atlases.get(clut)
		if texture != null: draw_texture_rect_region(texture, rectangle, source, Color(1, 1, 1, 0.35) if index == 37 else Color.WHITE)
	if font != null: draw_string(font, Vector2(104, 174), descriptions[selected_row], HORIZONTAL_ALIGNMENT_LEFT, 190, 12, Color.WHITE)
func _gui_input(event: InputEvent) -> void:
	if screen_adjust: return
	if event is InputEventMouseMotion:
		var point: Vector2 = (event.position - _native_offset()) * 240.0 / size.y
		for index in range(layout.get("row_y", []).size()):
			if Rect2(19, layout["row_y"][index], 48, 16).has_point(point): selected_row = index
		for region: Dictionary in hit_regions:
			if region["rect"].has_point(point): selected_row = _row_for(str(region["key"]))
		if not dragging.is_empty() and event.button_mask & MOUSE_BUTTON_MASK_LEFT: _volume_at(dragging, point.x)
		queue_redraw()
	elif event is InputEventMouseButton and not event.pressed: dragging = ""
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var point: Vector2 = (event.position - _native_offset()) * 240.0 / size.y
		for region: Dictionary in hit_regions:
			if region["rect"].has_point(point):
				_set_value(region["key"], region["value"])
				accept_event()
				return
		if Rect2(120, 128, 64, 16).has_point(point):
			dragging = "bgm_volume"
			_volume_at(dragging, point.x)
		elif Rect2(216, 128, 64, 16).has_point(point):
			dragging = "se_volume"
			_volume_at(dragging, point.x)
		elif point.x >= 19 and point.x < 67:
			for index in range(9):
				if Rect2(19, layout["row_y"][index], 48, 16).has_point(point):
					selected_row = index
					_activate_row()
					break
		accept_event()
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	if screen_adjust:
		if event.is_action_pressed("ui_cancel") or (event is InputEventJoypadButton and event.pressed and event.button_index == JOY_BUTTON_Y): _finish_screen(false)
		elif event.is_action_pressed("ui_accept"): _finish_screen(true)
		elif (event is InputEventKey and event.pressed and event.physical_keycode == KEY_R) or (event is InputEventJoypadButton and event.pressed and event.button_index == JOY_BUTTON_X): _screen_value(0, 0)
		elif event.is_action_pressed("ui_left"): _screen_value(int(values["screen_x"]) - 1, int(values["screen_y"]))
		elif event.is_action_pressed("ui_right"): _screen_value(int(values["screen_x"]) + 1, int(values["screen_y"]))
		elif event.is_action_pressed("ui_up"): _screen_value(int(values["screen_x"]), int(values["screen_y"]) - 1)
		elif event.is_action_pressed("ui_down"): _screen_value(int(values["screen_x"]), int(values["screen_y"]) + 1)
		else: return
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("ui_up"):
		selected_row = posmod(selected_row - 1, 9)
		selected_column = 0
	elif event.is_action_pressed("ui_down"):
		selected_row = (selected_row + 1) % 9
		selected_column = 0
	elif event is InputEventKey and event.pressed and event.physical_keycode == KEY_TAB:
		selected_column = (selected_column + 1) % _row_keys().size() if not _row_keys().is_empty() else 0
	elif event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right"):
		var keys: Array = _row_keys()
		selected_column = clampi(selected_column, 0, maxi(keys.size() - 1, 0))
		var key: String = str(keys[selected_column]) if not keys.is_empty() else ""
		if not key.is_empty():
			var direction := 1 if event.is_action_pressed("ui_right") else -1
			var binding: Dictionary = layout["roles"]["bindings"][key]
			_set_value(key, clampi(int(values[key]) + direction * (8 if selected_row == 5 else 1), 0, int(binding.get("maximum", 2 if selected_row == 0 else 1))))
	elif event.is_action_pressed("ui_accept"): _activate_row()
	else: return
	get_viewport().set_input_as_handled()
	queue_redraw()
func _row_for(key: String) -> int:
	return {"controller": 0, "view": 1, "buster_lock_on": 2, "special_lock_on": 2, "vibration": 3, "sound": 4, "bgm_volume": 5, "se_volume": 5}.get(key, 0)
func _set_value(key: String, value: int) -> void:
	if key == "controller" and value == 3: return
	values[key] = value
	settings.set_value("game", key, value)
	settings.save("user://settings.cfg")
	changed.emit(key, value)
	queue_redraw()
func _activate_row() -> void:
	if selected_row == 8: closed.emit()
	elif selected_row == 7:
		for key in layout["roles"]["bindings"]: _set_value(key, 1 if key == "view" else int(layout["roles"]["bindings"][key]["default"]))
		_screen_value(0, 0)
		_finish_screen(true)
		defaults_reset.emit()
	elif selected_row == 6:
		screen_saved = Vector2i(int(values["screen_x"]), int(values["screen_y"]))
		screen_adjust = true
		queue_redraw()
	elif selected_row in [2, 5]:
		selected_column = (selected_column + 1) % 2
		queue_redraw()
	else:
		var keys: Array = _row_keys()
		if not keys.is_empty():
			var key: String = str(keys[0])
			_set_value(key, (int(values[key]) + 1) % (3 if selected_row == 0 else 2))
func _row_keys() -> Array:
	return [["controller"], ["view"], ["buster_lock_on", "special_lock_on"], ["vibration"], ["sound"], ["bgm_volume", "se_volume"], [], [], []][selected_row]
func _volume_at(key: String, x: float) -> void:
	selected_row = 5
	selected_column = 0 if key == "bgm_volume" else 1
	_set_value(key, clampi(roundi((x - (128.0 if key == "bgm_volume" else 224.0)) * 127.0 / 48.0), 0, 127))
func _screen_value(x: int, y: int) -> void:
	values["screen_x"] = clampi(x, -12, 12)
	values["screen_y"] = clampi(y, 0, 12)
	changed.emit("screen_x", int(values["screen_x"]))
	queue_redraw()
func _finish_screen(accept: bool) -> void:
	if not accept: _screen_value(screen_saved.x, screen_saved.y)
	else:
		settings.set_value("game", "screen_x", int(values["screen_x"]))
		settings.set_value("game", "screen_y", int(values["screen_y"]))
		settings.save("user://settings.cfg")
	screen_adjust = false
	queue_redraw()
func _process(delta: float) -> void:
	gear_elapsed += delta
	if visible: queue_redraw()
