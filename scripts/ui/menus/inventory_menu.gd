extends "res://scripts/ui/menus/info_page.gd"
const SHOP = preload("res://scripts/ui/menus/shop_menu.gd")
const LIST := Rect2(53, 62, 218, 108)
const ROW := 18.0
const VISIBLE := 6
const GROUPS := {"items": "Items", "key_items": "Key Items", "special_weapons": "Special Weapons", "body_parts": "Body Parts", "buster_parts": "Buster Parts"}
var rows: Array[Dictionary] = []
var selected := -1
var top := 0
var life := 0
var life_max := 1
var zenny := 0
func configure(owner: Node) -> void:
	super(owner); footer_rect = Rect2(44, 187, 232, 24)
func refresh() -> void:
	var player: Node = host.gameplay.player; var catalog: Node = host.status_menu.inventory_view
	life = int(player.health); life_max = maxi(int(player.max_health), 1); zenny = int(player.zenny); rows.clear()
	for group: String in GROUPS:
		var owned: Dictionary = player.inventory.get(group, {}); var ids: Array = owned.keys().filter(func(id): return int(owned[id]) > 0)
		if ids.is_empty(): continue
		ids.sort_custom(func(a, b): return int(a) < int(b)); rows.append({"header": GROUPS[group]})
		for id: String in ids:
			var equipped: bool = str(player.equipped_special) == id if group == "special_weapons" else id in player.equipment.get(group, [])
			rows.append({"id": id, "name": catalog.item_name(group, id), "count": int(owned[id]) if group in ["items", "key_items"] else 0, "equipped": equipped, "icon": SHOP.icon_for_code((0x380 if group == "special_weapons" else 0) + int(id)), "description": str(catalog.definitions.get(group, {}).get(id, {}).get("description", ""))})
	top = 0; selected = -1; _step(1, false); _sync()
func _step(direction: int, sound: bool = true) -> void:
	var index := selected + direction
	while index >= 0 and index < rows.size() and rows[index].has("header"): index += direction
	if index < 0 or index >= rows.size(): return
	if sound and index != selected: host.audio.play_ui("menu_move")
	selected = index; _reveal(); _sync()
func _jump(direction: int) -> void:
	var starts: Array[int] = []
	for index in rows.size(): if rows[index].has("header"): starts.append(index + 1)
	var target := -1
	for start in starts:
		if direction > 0 and start > selected: target = start; break
		if direction < 0 and start < selected: target = start
	if target < 0: return
	selected = target; host.audio.play_ui("menu_move"); _reveal(); _sync()
func _page(direction: int) -> void:
	var before := selected
	for _count in VISIBLE: _step(direction, false)
	if selected != before: host.audio.play_ui("menu_move")
func _reveal() -> void:
	if selected < top or selected >= top + VISIBLE: top = selected if selected < top else selected - VISIBLE + 1
	if selected > 0 and rows[selected - 1].has("header") and selected - 1 < top: top = selected - 1
	top = clampi(top, 0, maxi(rows.size() - VISIBLE, 0))
func _sync() -> void:
	set_footer(str(rows[selected]["description"]) if selected >= 0 else "You are not carrying anything.")
	var y := LIST.position.y + float(selected - top) * ROW + 2.0
	pointer.visible = selected >= 0 and selected >= top and selected < top + VISIBLE
	if pointer.visible: pointer.select_at(Vector2(40, y))
	queue_redraw()
func _scroll(amount: int) -> void:
	top = clampi(top + amount, 0, maxi(rows.size() - VISIBLE, 0)); _sync()
func _gui_input(event: InputEvent) -> void:
	super(event)
	if event.is_action_pressed("ui_down", true): _step(1); accept_event()
	elif event.is_action_pressed("ui_up", true): _step(-1); accept_event()
	elif event.is_action_pressed("ui_page_down", true): _page(1); accept_event()
	elif event.is_action_pressed("ui_page_up", true): _page(-1); accept_event()
	elif event.is_action_pressed("ui_right"): _jump(1); accept_event()
	elif event.is_action_pressed("ui_left"): _jump(-1); accept_event()
	var maximum := float(rows.size() - VISIBLE)
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
		if event.pressed: _scroll(3 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -3)
		accept_event()
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if not event.pressed: dragging_bar = false; return
		var track := _track(LIST); var point := _native(event.position)
		if maximum <= 0.0 or not Rect2(track.position.x - 4.0, track.position.y - 1.0, track.size.x + 8.0, track.size.y + 2.0).has_point(point): return
		var thumb := _thumb(track, VISIBLE, rows.size(), top); accept_event()
		if point.y >= thumb.position.y and point.y <= thumb.end.y: dragging_bar = true; grab_offset = point.y - thumb.position.y
		else: _scroll(VISIBLE * (1 if point.y > thumb.end.y else -1))
	elif event is InputEventMouseMotion:
		var point := _native(event.position)
		if dragging_bar and maximum > 0.0:
			var track := _track(LIST); var travel := track.size.y - _thumb(track, VISIBLE, rows.size(), top).size.y
			top = int(roundf(clampf((point.y - grab_offset - track.position.y) / travel, 0.0, 1.0) * maximum)); _sync(); accept_event()
		elif Rect2(LIST.position.x - 14.0, LIST.position.y, LIST.size.x + 14.0, LIST.size.y).has_point(point):
			var index := top + int((point.y - LIST.position.y) / ROW)
			if index < rows.size() and not rows[index].has("header") and index != selected: host.audio.play_ui("menu_move"); selected = index; _sync()
func _frames() -> void:
	_chrome_frames(); FRAME.draw(self, layout, "prompt", Rect2(36, 34, 248, 14)); FRAME.draw(self, layout, "selector", Rect2(36, 56, 248, 120)); FRAME.draw(self, layout, "prompt", Rect2(36, 184, 248, 30))
func _content() -> void:
	_chrome_content("Inventory", "inventory", "Q/E: Page   PgUp/PgDn: Scroll   Esc: Back")
	_text("Life", Vector2(46, 37)); life_gauge(self, Vector2(70, 38), life, life_max, 90.0)
	_text("%07d Z" % zenny, Vector2(176, 37), 9, Color.WHITE, 100, HORIZONTAL_ALIGNMENT_RIGHT)
	if rows.is_empty(): _text("Nothing carried", LIST.position, 11, Color8(128, 128, 128), LIST.size.x, HORIZONTAL_ALIGNMENT_CENTER); return
	for index in range(top, mini(top + VISIBLE, rows.size())):
		var row: Dictionary = rows[index]; var y := LIST.position.y + float(index - top) * ROW
		if row.has("header"): _text(str(row["header"]), Vector2(LIST.position.x + 2, y + 5), 9, Color8(150, 205, 220)); draw_line(Vector2(LIST.position.x, y + 16.5), Vector2(LIST.end.x, y + 16.5), Color8(70, 96, 120)); continue
		var color := Color.WHITE if index == selected else Color8(255, 222, 99); var right := LIST.end.x - 2.0
		SHOP.draw_item_icon(self, int(row["icon"]), Rect2(LIST.position.x + 1, y + 1, 16, 16))
		_text(str(row["name"]), Vector2(LIST.position.x + 22, y + 3), 11, color)
		if int(row["count"]) > 0: var count := "x%d" % int(row["count"]); _text(count, Vector2(right - 40, y + 4), 9, color, 40, HORIZONTAL_ALIGNMENT_RIGHT); right -= font.get_string_size(count, HORIZONTAL_ALIGNMENT_LEFT, -1, 9).x + 6.0
		if bool(row["equipped"]): _text("Equipped", Vector2(right - 50, y + 5), 8, Color8(140, 230, 170), 50, HORIZONTAL_ALIGNMENT_RIGHT)
	_draw_bar(LIST, VISIBLE, rows.size(), top)
