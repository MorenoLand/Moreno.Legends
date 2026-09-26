extends Control
signal options_requested
signal closed
const ART = preload("res://scripts/ui/native_menu_primitives.gd")
const EQUIPMENT = preload("res://scripts/ui/status_equipment.gd")
var host: Node
var data: Dictionary = {}
var page_definitions: Dictionary = {}
var page_actions: Dictionary = {}
var page := "status"
var selection := 0
var font: Font
var background: Texture2D
var frame: Texture2D
var help_frame: Texture2D
var normal: Texture2D
var selected: Texture2D
var surface: Control
var map_view: Control
var inventory_view: Control
var buttons: Array[Button] = []
var elapsed := 0.0
var equipment_category := ""
var equipment_slot := -1
var item_description := ""
var frame_textures: Dictionary = {}
var equipment_buttons: Array[Button] = []
var minimap_choice := -1
var minimap_pointer: TextureRect
var minimap_panel: Panel
var minimap_buttons: Array[Button] = []
func configure(owner: Node) -> void:
	host = owner
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
	data = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/status.json"))
	page_definitions = data["pages"].duplicate(true)
	font = load("res://assets/menu/native_font.fnt") as Font
	background = load("res://assets/menu/native_gear_background.png") as Texture2D
	frame = load("res://assets/menu/options_frame_atlas.png") as Texture2D
	help_frame = load("res://assets/menu/options_help_frame_atlas.png") as Texture2D
	normal = _atlas("res://assets/menu/" + str(data["atlases"]["normal"]["file"]))
	selected = _atlas("res://assets/menu/" + str(data["atlases"]["selected"]["file"]))
	for key in data.get("frames", {}): frame_textures[key] = _atlas("res://assets/menu/" + str(data["frames"][key]["texture"]))
	var native_theme := Theme.new()
	native_theme.default_font = font
	native_theme.default_font_size = 12
	theme = native_theme
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	map_view = preload("res://scripts/ui/status_map.gd").new()
	map_view.position = Vector2(88, 32)
	map_view.size = Vector2(212, 144)
	surface.add_child(map_view)
	map_view.configure(host)
	inventory_view = preload("res://scripts/ui/status_inventory.gd").new()
	inventory_view.position = Vector2(20, 53)
	inventory_view.size = Vector2(277, 107)
	surface.add_child(inventory_view)
	inventory_view.configure(host, data["equipment_definitions"])
	inventory_view.changed.connect(queue_redraw)
	inventory_view.description_changed.connect(func(text): item_description = text; queue_redraw())
	minimap_panel = Panel.new(); minimap_panel.position = Vector2(108, 80); minimap_panel.size = Vector2(108, 58); minimap_panel.z_index = 3; surface.add_child(minimap_panel)
	var popup_style := StyleBoxTexture.new(); popup_style.texture = help_frame; popup_style.region_rect = Rect2(112, 16, 24, 24)
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: popup_style.set_texture_margin(side, 8)
	minimap_panel.add_theme_stylebox_override("panel", popup_style)
	var popup_title := Label.new(); popup_title.text = "MiniMap Display"; popup_title.position = Vector2(8, 6); popup_title.size = Vector2(92, 14); popup_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; minimap_panel.add_child(popup_title)
	for index in 2:
		var button := Button.new(); button.text = "ON" if index == 0 else "OFF"; button.position = Vector2(38, 23 + index * 16); button.size = Vector2(54, 16); button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		for state in ["normal", "hover", "pressed", "focus"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.focus_entered.connect(_choose_minimap.bind(index)); button.mouse_entered.connect(button.grab_focus); button.pressed.connect(_set_minimap_value.bind(index == 0)); minimap_panel.add_child(button); minimap_buttons.append(button)
	minimap_pointer = preload("res://scripts/ui/native_menu_cursor.gd").new(); minimap_pointer.configure(Vector2.ZERO); minimap_panel.add_child(minimap_pointer); minimap_panel.hide()
	resized.connect(_layout)
	_layout()
func _atlas(path: String) -> Texture2D:
	if FileAccess.file_exists(path + ".import"): return load(path) as Texture2D
	var image := Image.load_from_file(path)
	return ImageTexture.create_from_image(image) if image != null and not image.is_empty() else null
func register_page(id: String, definition: Dictionary, actions: Dictionary) -> void:
	page_definitions[id] = definition.duplicate(true)
	page_actions[id] = actions.duplicate()
func refresh() -> void:
	show_page(page)
func show_page(id: String) -> void:
	if not page_definitions.has(id) or not is_instance_valid(host.gameplay): return
	page = id
	selection = 0
	equipment_category = ""
	equipment_slot = -1
	item_description = ""
	minimap_choice = -1
	minimap_panel.hide()
	_clear_equipment_buttons()
	map_view.visible = page == "map"
	inventory_view.visible = page == "items"
	if page == "map": map_view.refresh()
	if page == "items": inventory_view.position = Vector2(20, 53); inventory_view.size = Vector2(277, 107); inventory_view.refresh("items")
	for button in buttons: surface.remove_child(button); button.queue_free()
	buttons.clear()
	var descriptor: Dictionary = page_definitions[page]
	for index in range(descriptor["entries"].size()):
		var entry: Dictionary = descriptor["entries"][index]
		var rectangle := Rect2(float(descriptor["button_rects"][index][0]), float(descriptor["button_rects"][index][1]), float(descriptor["button_rects"][index][2]), float(descriptor["button_rects"][index][3]))
		var button := Button.new()
		button.position = rectangle.position
		button.size = rectangle.size
		for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.disabled = str(entry["id"]) == "auto_nav"
		button.mouse_entered.connect(button.grab_focus)
		button.focus_entered.connect(_select.bind(index))
		button.pressed.connect(_activate.bind(str(entry["id"])))
		surface.add_child(button)
		buttons.append(button)
	call_deferred("focus_first")
	queue_redraw()
func focus_first() -> void:
	if is_visible_in_tree() and not buttons.is_empty(): buttons[selection].grab_focus()
func _select(index: int) -> void:
	if selection != index: host.audio.play_ui("menu_move")
	selection = index
	item_description = ""
	if page == "items" and index < 2: inventory_view.refresh(str(page_definitions[page]["entries"][index]["id"]))
	queue_redraw()
func _activate(id: String) -> void:
	host.audio.play_ui("menu_cancel" if id == "back" else "menu_confirm")
	if page_actions.get(page, {}).has(id): page_actions[page][id].call(); return
	if id == "back": back(); return
	if page == "status":
		if id == "options": options_requested.emit()
		else: show_page(id)
	elif page == "map":
		if id == "search": map_view.center_player()
		elif id == "minimap":
			minimap_choice = 0 if host.gameplay.game_hud.minimap.display_enabled else 1
			minimap_panel.show(); _choose_minimap(minimap_choice); minimap_buttons[minimap_choice].grab_focus(); map_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
			for button in buttons: button.disabled = true
	elif page == "equipment":
		_equipment_list(id, 0 if id in ["body_parts", "buster_parts"] else -1)
	queue_redraw()
func _equipment_list(category: String, slot: int) -> void:
	equipment_category = category
	equipment_slot = slot
	inventory_view.visible = true
	var rectangle: Rect2 = EQUIPMENT.list_rect(category); inventory_view.position = rectangle.position; inventory_view.size = rectangle.size
	inventory_view.refresh(category, slot)
	_clear_equipment_buttons()
	var tabs: Array = EQUIPMENT.tabs(category) if category in ["body_parts", "buster_parts"] else []
	for index in tabs.size():
		var button := Button.new(); rectangle = tabs[index]["rect"]; button.position = rectangle.position; button.size = rectangle.size
		for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.disabled = category == "buster_parts" and index == 1
		button.pressed.connect(_equipment_tab.bind(index)); surface.add_child(button); equipment_buttons.append(button)
func _equipment_tab(index: int) -> void:
	if equipment_category == "body_parts": equipment_slot = index; inventory_view.refresh(equipment_category, index); item_description = "Change equipped " + ["Helmet", "Armor", "Shoes"][index] + "."; queue_redraw()
	else: inventory_view.focus_first()
func _clear_equipment_buttons() -> void:
	for button in equipment_buttons: surface.remove_child(button); button.queue_free()
	equipment_buttons.clear()
func cycle_page(direction: int) -> void:
	var order := ["map", "items", "equipment", "options"]
	var index := order.find(page)
	var target: String = order[posmod(index + direction, order.size())]
	if target == "options": options_requested.emit()
	else: show_page(target)
func _unhandled_input(event: InputEvent) -> void:
	if not visible: return
	if minimap_choice >= 0:
		if event.is_action_pressed("ui_up") or event.is_action_pressed("ui_down"): minimap_choice = 1 - minimap_choice; host.audio.play_ui("menu_move")
		elif event.is_action_pressed("ui_accept") or event.is_action_pressed("interact"):
			_set_minimap_value(minimap_choice == 0)
		elif event.is_action_pressed("ui_cancel"): _close_minimap_choice()
		if minimap_choice >= 0: _choose_minimap(minimap_choice); minimap_buttons[minimap_choice].grab_focus()
		queue_redraw(); get_viewport().set_input_as_handled(); return
	if event is InputEventJoypadButton and event.pressed and event.button_index in [JOY_BUTTON_LEFT_SHOULDER, JOY_BUTTON_RIGHT_SHOULDER]:
		cycle_page(-1 if event.button_index == JOY_BUTTON_LEFT_SHOULDER else 1)
		get_viewport().set_input_as_handled()
	elif page == "equipment" and equipment_slot >= 0 and (event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right")):
		var count := 3 if equipment_category == "body_parts" else 2
		_equipment_list(equipment_category, posmod(equipment_slot + (1 if event.is_action_pressed("ui_right") else -1), count))
		queue_redraw()
		get_viewport().set_input_as_handled()
func back() -> void:
	if minimap_choice >= 0: _close_minimap_choice()
	elif not equipment_category.is_empty(): equipment_category = ""; inventory_view.hide(); _clear_equipment_buttons(); queue_redraw()
	elif page != "status": show_page("status")
	else: closed.emit()
func _close_minimap_choice() -> void:
	minimap_choice = -1
	minimap_panel.hide(); map_view.mouse_filter = Control.MOUSE_FILTER_STOP
	for button in buttons: button.disabled = str(page_definitions[page]["entries"][buttons.find(button)]["id"]) == "auto_nav"
	focus_first(); queue_redraw()
func _choose_minimap(index: int) -> void:
	minimap_choice = index; minimap_pointer.select_at(Vector2(20, 23 + index * 16))
func _set_minimap_value(value: bool) -> void:
	host.settings.set_value("interface", "show_minimap", value); host.settings.save("user://settings.cfg"); host.gameplay.set_minimap_visible(value); _close_minimap_choice()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor := size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func _process(delta: float) -> void:
	elapsed += delta
	if visible: queue_redraw()
func _box(rectangle: Rect2, green: bool = false) -> void:
	if not green: draw_rect(rectangle.grow(-3), Color8(54, 48, 63))
	var key := "green" if green else "plain"
	if frame_textures.has(key): ART.patches(self, frame_textures[key], rectangle, data["frames"][key])
func _help_box(rectangle: Rect2) -> void:
	draw_rect(rectangle.grow(-3), Color8(54, 48, 63))
	if frame_textures.has("help"): ART.patches(self, frame_textures["help"], rectangle, data["frames"]["help"])
func _text(value: String, position: Vector2, width: float = -1, size: int = 12, alignment: int = HORIZONTAL_ALIGNMENT_LEFT, color: Color = Color.WHITE) -> void:
	draw_string(font, position + Vector2(0, font.get_ascent(size)), value, alignment, width, size, color)
func _heading(value: String, position: Vector2, width: float) -> void:
	for shift in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]: _text(value, position + shift, width, 12, HORIZONTAL_ALIGNMENT_CENTER, Color8(39, 125, 142))
	_text(value, position, width, 12, HORIZONTAL_ALIGNMENT_CENTER, Color8(235, 250, 245))
func _draw() -> void:
	if data.is_empty() or size.y <= 0 or not is_instance_valid(host.gameplay): return
	var factor := size.y / 240.0
	var offset := Vector2((size.x - 320 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	var phase: int = (int(elapsed * 30.0) >> 1) & 63
	draw_texture_rect(background, Rect2(Vector2(-offset.x / factor + phase - 80, phase - 80), Vector2(size.x / factor + 160, 400)), true)
	var descriptor: Dictionary = page_definitions[page]
	_heading(str(descriptor["title"]), Vector2(96, 13), 128)
	var title_width := font.get_string_size(str(descriptor["title"]), HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	for x in [160.0 - title_width * 0.5 - 14.0, 160.0 + title_width * 0.5 + 6.0]: draw_texture_rect_region(normal, Rect2(x, 15, 8, 8), Rect2(0, 16, 8, 8))
	if page != "status":
		var order := ["map", "items", "equipment", "options"]; var index := order.find(page)
		if index >= 0: _text("L2 " + str(order[posmod(index - 1, 4)]).to_upper(), Vector2(16, 14), 80, 8); _text(str(order[posmod(index + 1, 4)]).to_upper() + " R2", Vector2(224, 14), 80, 8, HORIZONTAL_ALIGNMENT_RIGHT)
	if descriptor.has("menu_rect"): _box(Rect2(descriptor["menu_rect"][0], descriptor["menu_rect"][1], descriptor["menu_rect"][2], descriptor["menu_rect"][3]), true)
	var help: Array = descriptor["help_rect"]
	_help_box(Rect2(help[0], help[1], help[2], help[3]))
	var description := str(descriptor["descriptions"][selection])
	if not item_description.is_empty(): description = item_description
	elif page == "equipment" and equipment_category == "body_parts" and equipment_slot >= 0: description = "Change equipped " + ["Helmet", "Armor", "Shoes"][equipment_slot] + "."
	if page == "map" and selection == 2: description = "Hide MiniMap." if host.gameplay.game_hud.minimap.display_enabled else "Display MiniMap."
	var line := ""; var line_y := float(help[1]) + 5.0
	for word: String in description.split(" ", false):
		var candidate := word if line.is_empty() else line + " " + word
		if not line.is_empty() and font.get_string_size(candidate, HORIZONTAL_ALIGNMENT_LEFT, -1, 11).x > float(help[2]) - 20.0: _text(line, Vector2(help[0] + 12, line_y), help[2] - 20, 11); line_y += 13.0; line = word
		else: line = candidate
	_text(line, Vector2(help[0] + 12, line_y), help[2] - 20, 11)
	for index in range(descriptor["entries"].size()):
		var entry: Dictionary = descriptor["entries"][index]
		var region: Array = descriptor["button_rects"][index]
		var target := Rect2(region[0], region[1], region[2], region[3])
		if entry.has("uv"):
			var uv: Array = entry["uv"]
			draw_texture_rect_region(selected if index == selection else normal, target, Rect2(uv[0], uv[1], uv[2], uv[3]))
		else:
			draw_rect(target, Color8(163, 61, 89) if index == selection else Color8(82, 90, 107))
			_text(str(entry["label"]), target.position + Vector2(1, 1), target.size.x - 2, 10, HORIZONTAL_ALIGNMENT_CENTER, Color(1, 1, 1, 0.35) if str(entry["id"]) == "auto_nav" else Color.WHITE)
	draw_texture_rect_region(help_frame, Rect2(104, 214, 112, 16), Rect2(16, 0, 112, 16))
	if page == "status": _status_values()
	elif page == "items": _box(Rect2(12, 47, 294, 120))
	elif page == "equipment": _equipment_values()
func _status_values() -> void:
	var names: Dictionary = host.gameplay.get_location_names()
	_heading("Location", Vector2(96, 28), 128)
	draw_rect(Rect2(88, 42, 144, 30), Color8(48, 74, 88))
	_text(str(names["main"]), Vector2(92, 44), 136, 12, HORIZONTAL_ALIGNMENT_CENTER)
	_text(str(names["area"]), Vector2(92, 57), 136, 12, HORIZONTAL_ALIGNMENT_CENTER)
	_text("%07d Z" % int(host.gameplay.player.zenny), Vector2(104, 80), 120, 14, HORIZONTAL_ALIGNMENT_CENTER)
	var time := int(host.gameplay.play_time_seconds)
	_text("%d:%02d:%02d" % [time / 3600, (time / 60) % 60, time % 60], Vector2(104, 104), 120, 14, HORIZONTAL_ALIGNMENT_CENTER)
	draw_rect(Rect2(88, 128, 144, 22), Color8(48, 74, 88))
	_text(inventory_view.item_name("special_weapons", str(host.gameplay.player.equipped_special)), Vector2(96, 131), 128, 12, HORIZONTAL_ALIGNMENT_CENTER)
	_text("Spec.Weapon  " + inventory_view.item_name("special_weapons", str(host.gameplay.player.equipped_special)), Vector2(92, 146), 136, 8, HORIZONTAL_ALIGNMENT_CENTER)
	_box(Rect2(240, 30, 64, 128), true)
	draw_texture_rect_region(normal, Rect2(244, 72, 56, 72), Rect2(128, 32, 64, 72))
	var height := clampf(float(host.gameplay.player.health) / maxf(float(host.gameplay.player.max_health), 1.0), 0, 1) * 80.0
	draw_rect(Rect2(258, 43, 8, 80), Color8(49, 106, 83))
	draw_rect(Rect2(259, 123 - height, 6, height), Color8(181, 247, 190))
	for y in range(43, 123, 8): draw_line(Vector2(258, y), Vector2(266, y), Color8(49, 91, 78), 1)
func _equipment_values() -> void:
	EQUIPMENT.draw(self, inventory_view, host.gameplay.player, equipment_category, equipment_slot)
