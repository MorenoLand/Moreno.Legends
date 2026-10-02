extends "res://scripts/ui/menus/info_page.gd"
const SLOTS := [["Special Weapon", "special_weapons", 0], ["Helmet", "body_parts", 0], ["Armor", "body_parts", 1], ["Shoes", "body_parts", 2], ["Buster 1", "buster_parts", 0], ["Buster 2", "buster_parts", 1]]
const STATS := ["Attack", "Energy", "Range", "Rapid"]
const LEFT := Rect2(41, 40, 122, 132)
const RIGHT := Rect2(179, 40, 100, 72)
const SLOT_ROW := 22.0
const ROW := 18.0
const VISIBLE := 4
var slot := 0
var choosing := false
var choice := 0
var top := 0
var buster: Dictionary = {}
var caps: Dictionary = {}
func configure(owner: Node) -> void:
	super(owner); footer_rect = Rect2(44, 188, 232, 24)
	buster = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/status.json"))["buster_parts"]
	caps = JSON.parse_string(FileAccess.get_file_as_string("res://assets/development/development.json"))["development"]["weapons"] if FileAccess.file_exists("res://assets/development/development.json") else {}
func refresh() -> void:
	slot = 0; choosing = false; choice = 0; top = 0; _sync()
func _catalog() -> Node: return host.status_menu.inventory_view
func _equipped(index: int) -> String:
	var player: Node = host.gameplay.player
	return str(player.equipped_special) if index == 0 else str(player.equipment[SLOTS[index][1]][SLOTS[index][2]])
func _candidates() -> Array:
	var group: String = SLOTS[slot][1]; var owned: Dictionary = host.gameplay.player.inventory.get(group, {}); var list: Array = [{"id": "", "name": "Nothing", "description": "Remove the equipped part."}]
	var ids: Array = owned.keys().filter(func(id): return int(owned[id]) > 0); ids.sort_custom(func(a, b): return int(a) < int(b))
	for id: String in ids:
		var definition: Dictionary = _catalog().definitions.get(group, {}).get(id, {})
		if group == "body_parts" and definition.has("slot") and int(definition["slot"]) != int(SLOTS[slot][2]): continue
		list.append({"id": id, "name": _catalog().item_name(group, id), "description": str(definition.get("description", ""))})
	return list
func buster_stats(replace_slot: int = -1, replacement: String = "") -> Array:
	var equipped: Array = host.gameplay.player.equipment["buster_parts"].duplicate()
	if replace_slot >= 0: equipped[replace_slot] = replacement
	return host.gameplay.player.weapon_stats.buster_levels(equipped)
func _sync() -> void:
	var text: String
	if slot == 0:
		var partner: String = host.special_partner(); text = "Swap the special weapon with %s." % (_catalog().item_name("special_weapons", partner) if not partner.is_empty() else "another weapon")
	elif choosing:
		var list := _candidates(); text = str(list[clampi(choice, 0, list.size() - 1)]["description"]); text = text if not text.is_empty() else "Equip this part."
	else: text = "Change equipped %s." % SLOTS[slot][0]
	set_footer(text)
	pointer.select_at(Vector2(166.0 if choosing else 40.0, (RIGHT.position.y + float(choice - top) * ROW if choosing else LEFT.position.y + float(slot) * SLOT_ROW + 5.0) + 2.0)); pointer.show(); queue_redraw()
func _confirm() -> void:
	if slot == 0: host.swap_special(); _sync(); return
	if not choosing: choosing = true; choice = 0; top = 0; host.audio.play_ui("menu_confirm"); _sync(); return
	var list := _candidates(); var picked: String = list[choice]["id"]; var player: Node = host.gameplay.player; var group: String = SLOTS[slot][1]
	if not picked.is_empty() and player.equipment[group].count(picked) - int(player.equipment[group][SLOTS[slot][2]] == picked) >= int(player.inventory[group].get(picked, 0)): host.audio.play_ui("menu_cancel"); return
	player.equipment[group][SLOTS[slot][2]] = picked; host.audio.play_ui("menu_confirm"); _sync()
func _move(direction: int) -> void:
	if choosing:
		var count := _candidates().size(); choice = clampi(choice + direction, 0, count - 1); top = clampi(maxi(mini(top, choice), choice - VISIBLE + 1), 0, maxi(count - VISIBLE, 0))
	else: slot = clampi(slot + direction, 0, SLOTS.size() - 1); choice = 0; top = 0
	host.audio.play_ui("menu_move"); _sync()
func _gui_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel") and choosing: choosing = false; host.audio.play_ui("menu_cancel"); _sync(); accept_event(); return
	super(event)
	if event.is_action_pressed("ui_down", true): _move(1); accept_event()
	elif event.is_action_pressed("ui_up", true): _move(-1); accept_event()
	elif event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_right") and slot > 0 and not choosing: _confirm(); accept_event()
	elif event.is_action_pressed("ui_left") and choosing: choosing = false; host.audio.play_ui("menu_cancel"); _sync(); accept_event()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var point := _native(event.position)
		if choosing and RIGHT.has_point(point):
			var row := top + int((point.y - RIGHT.position.y) / ROW)
			if row < _candidates().size(): choice = row; _confirm()
		elif LEFT.has_point(point): choosing = false; slot = clampi(int((point.y - LEFT.position.y) / SLOT_ROW), 0, SLOTS.size() - 1); _confirm()
		accept_event()
	elif event is InputEventMouseButton and event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN] and choosing: _move(1 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -1); accept_event()
func _frames() -> void:
	_chrome_frames(); FRAME.draw(self, layout, "selector", Rect2(36, 34, 130, 144)); FRAME.draw(self, layout, "selector", Rect2(174, 34, 110, 84)); FRAME.draw(self, layout, "selector", Rect2(174, 126, 110, 52)); FRAME.draw(self, layout, "prompt", Rect2(36, 186, 248, 28))
func _bars(values: Array, maxima: Array, compare: Array = []) -> void:
	for stat in 4:
		var y := 134.0 + float(stat) * 10.0; var maximum := int(maxima[stat]); _text(STATS[stat], Vector2(181, y), 8, Color8(150, 205, 220))
		if maximum <= 0: _text("-", Vector2(219, y), 8, Color8(128, 128, 128)); continue
		var width := minf(8.0, 56.0 / float(maximum)) - 1.0
		for segment in maximum:
			var x := 219.0 + float(segment) * (width + 1.0); var base := int(values[stat]); var shown := base; var color := Color8(214, 138, 74)
			if not compare.is_empty(): shown = int(compare[stat]); color = Color8(214, 138, 74) if segment < mini(base, shown) else Color8(140, 230, 170) if segment < shown else Color8(160, 60, 60)
			draw_rect(Rect2(x, y + 1.0, width, 5.0), Color8(48, 96, 96))
			if segment < maxi(base, shown): draw_rect(Rect2(x, y + 1.0, width, 5.0), color); draw_rect(Rect2(x, y + 1.0, width, 2.0), color.lightened(0.35))
func _content() -> void:
	_chrome_content("Equipment", "equipment", "Q/E: Page   X: Swap Weapon   Esc: Back")
	for index in SLOTS.size():
		var y := LEFT.position.y + float(index) * SLOT_ROW; var id := _equipped(index); var group: String = SLOTS[index][1]; var active := index == slot and not choosing
		if index == slot and choosing: draw_rect(Rect2(LEFT.position.x - 2, y, LEFT.size.x + 2, SLOT_ROW - 2), Color(1, 1, 1, 0.12))
		_text(str(SLOTS[index][0]), Vector2(LEFT.position.x + 14, y + 1), 8, Color8(150, 205, 220))
		var named: String = _catalog().item_name(group, id) if not id.is_empty() or index > 0 else "Nothing"
		_text(named, Vector2(LEFT.position.x + 14, y + 10), 10, Color.WHITE if active else Color8(255, 222, 99), LEFT.size.x - 16)
	if slot == 0:
		var weapon := str(host.gameplay.player.equipped_special); var levels: Array = host.gameplay.native_context.get("native_special_levels", {}).get(weapon, [0, 0, 0, 0, 0]); var limit: Array = caps.get(weapon, {}).get("caps", [0, 0, 0, 0, 0])
		_text("Lifter / Weapon", Vector2(RIGHT.position.x, RIGHT.position.y + 4), 8, Color8(128, 128, 128), RIGHT.size.x, HORIZONTAL_ALIGNMENT_CENTER)
		if limit.slice(0, 4).any(func(cap): return int(cap) > 0): _bars(levels, limit)
		else: _text("No stats", Vector2(174, 146), 9, Color8(128, 128, 128), 110, HORIZONTAL_ALIGNMENT_CENTER)
		return
	var list := _candidates(); var current := _equipped(slot)
	for index in range(top, mini(top + VISIBLE, list.size())):
		var y := RIGHT.position.y + float(index - top) * ROW
		_text(str(list[index]["name"]), Vector2(RIGHT.position.x + 14, y + 4), 10, Color.WHITE if choosing and index == choice else Color8(255, 222, 99), RIGHT.size.x - 30)
		if str(list[index]["id"]) == current: _text("E", Vector2(RIGHT.end.x - 12, y + 5), 8, Color8(140, 230, 170))
	if SLOTS[slot][1] == "buster_parts":
		var maxima := [buster["maximum"], buster["maximum"], buster["maximum"], buster["maximum"]]
		_bars(buster_stats(), maxima, buster_stats(int(SLOTS[slot][2]), str(list[choice]["id"])) if choosing else [])
	else: _text("-", Vector2(174, 146), 9, Color8(128, 128, 128), 110, HORIZONTAL_ALIGNMENT_CENTER)
