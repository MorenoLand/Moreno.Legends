extends "res://scripts/ui/menus/shop_menu.gd"
# Roll's development scene (scene 0x30 of ST04T, started by dialogue flag 0x6FD; state table 0x800F41CC): item development, special weapon change and improvement.
# The overlay message bank and the recipe, cost and cap tables are exported to assets/development; the windows run on the shop menu's message engine.
const DEVELOPMENT_STAGE := "ST04"
const FIRST_WEAPON := 0x383
const LAST_WEAPON := 0x393
const FIRST_ITEM := 0x408
const LAST_ITEM := 0x437
const STATS := ["Attack", "Energy", "Range", "Rapid", "Special"]
const GAUGE_WIDTH := 56
var dev: Dictionary = {}
var list_y := 56
var list_rows := 3
var list_codes: Array[int] = []
var weapon_panel := false
var preview_stat := -1
var menu_selection := 0
var stat_selection := 0
var panel_code := -1
func develop(gameplay: Node) -> bool:
	host = gameplay; stage = DEVELOPMENT_STAGE
	var source: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/development/development.json")); items = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/items.json"))
	if not source is Dictionary or not items is Dictionary: push_error("Missing development data"); return false
	dev = source["development"]; layout = host.dialogue_box.layout; font = host.dialogue_box.font; colour_fonts = host.dialogue_box.colour_fonts
	messages = Node.new(); messages.set_script(EVENT_SCRIPT); add_child(messages)
	if not messages.configure(self, "res://assets/development/manifest.json", message_context) or not messages.prepare_stage(stage): push_error("Missing development message bank"); return false
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; z_index = 20
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	list_hand = HAND.new(); list_hand.configure(Vector2.ZERO); list_hand.hide(); surface.add_child(list_hand); choice_hand = HAND.new(); choice_hand.configure(Vector2.ZERO); choice_hand.hide(); surface.add_child(choice_hand)
	resized.connect(_layout); _layout(); message_context["event_flags"] = {}; message_context["native_message_number"] = 0; message_context["native_item_name"] = ""; message_context["native_wallet"] = host.player.zenny; state = {"zenny": host.player.zenny}
	_set_flag(0x6FD, false)
	await _notice()
	while true:
		_close_all(); _say(0, 30); _say(2, 0); windows[2]["selection"] = menu_selection
		var choice := await _choice(2); _close(0)
		if choice < 0 or choice > 2: break
		menu_selection = choice
		match choice:
			0: await _development()
			1: await _change_weapon()
			2: await _improve()
	_close_all(); list_active = false; list_dimmed = false; weapon_panel = false; return true
# ---- state shared with the game ----
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag(id: int, value: bool) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id] = value; flags[str(id)] = value; host.native_context["event_flags"] = flags
func _levels(weapon: int) -> Array:
	var all: Dictionary = host.native_context.get("native_special_levels", {})
	if not all.has(str(weapon)): all[str(weapon)] = [0, 0, 0, 0, 0]; host.native_context["native_special_levels"] = all
	return all[str(weapon)]
func _owned(code: int) -> bool:
	var inventory: Dictionary = host.player.inventory
	if code >= 0x400: return inventory["items"].has(str(code))
	if code >= 0x3d0: return inventory["key_items"].has(str(code))
	if code >= 0x3b8: return inventory["body_parts"].has(str(code))
	return inventory["special_weapons"].has(str(code - 0x380))
func _store(code: int, owned: bool) -> void:
	var inventory: Dictionary = host.player.inventory; var group: Dictionary = inventory["items"] if code >= 0x400 else inventory["key_items"] if code >= 0x3d0 else inventory["body_parts"] if code >= 0x3b8 else inventory["special_weapons"]; var key := str(code if code >= 0x3b8 else code - 0x380)
	if owned: group[key] = 1
	else: group.erase(key)
	if code < 0x3b8: _levels(code - 0x380)
	_set_flag(code, owned)
func _name(code: int) -> String: return str(items["names"].get(str(code), ""))
func _wallet(value: int) -> void:
	host.player.zenny = value; host.native_context["native_wallet"] = value; message_context["native_wallet"] = value; state["zenny"] = value
func _say(id: int, index: int, number := -1) -> void:
	message_context["native_wallet"] = host.player.zenny
	_open(id, index, number)
	if windows.has(id): _play_cues(id, index)
func _play_cues(id: int, index: int) -> void:
	var resolved: Dictionary = messages._resolve_program(stage, index, {"flags": 0x00010083, "byte23": 2, "choice_index": 0, "text_speed": 2, "origin_x": 24, "origin_y": 172, "window_width": 138, "window_lines": 2})
	if not bool(resolved.get("supported", false)): return
	windows[id]["cues"] = resolved["page_commands"]; _page_cues(id)
func _page_cues(id: int) -> void:
	var cues: Array = windows[id].get("cues", []); var page := int(windows[id]["page"])
	if page >= cues.size() or not is_instance_valid(host.audio): return
	for command: Dictionary in cues[page]:
		if int(command.get("opcode", -1)) == 0x19 and command["arguments"].size() == 2: host.audio.play_sound((int(command["arguments"][0]) << 8) | int(command["arguments"][1]))
func _start_page(id: int) -> void:
	super._start_page(id)
	if windows.has(id) and windows[id].has("cues"): _page_cues(id)
func _close_all() -> void:
	for id in [0, 1, 2, 3, 4]: _close(id)
	description_code = -1
func _cost(weapon: int, stat: int) -> int:
	var entry: Dictionary = dev["weapons"].get(str(weapon), {}); var level := int(_levels(weapon)[stat])
	if entry.is_empty() or level >= int(entry["caps"][stat]): return -1
	var cost := int(entry["costs"][level][stat]); var percent: Array = dev["cost_percent_by_byte45"]; var tier := int(host.native_context.get("native_save_byte45", 1))
	if tier >= 0 and tier < percent.size(): cost += cost * int(percent[tier]) / 100
	return mini(cost, int(dev["maximum_cost"]))
# ---- scene states ----
func _notice() -> void:
	# State 0 (0x800EAACC): flags 0x190/0x191/0x192 remember the last price tier Roll announced.
	var tier := clampi(int(host.native_context.get("native_save_byte45", 1)), 0, 2); var notice := -1
	match tier:
		0: notice = 26 if not _flag(0x190) else -1
		1: notice = (27 if _flag(0x190) else 28 if _flag(0x192) else 0) if not _flag(0x191) else -1
		2: notice = 29 if not _flag(0x192) else -1
	if notice < 0: return
	for id in [0x190, 0x191, 0x192]: _set_flag(id, false)
	_set_flag(0x190 + tier, true)
	if notice > 0: _say(2, notice); await _wait_closed(2)
func _development() -> void:
	# State 1 (0x800EBAB0): the owned items 0x408..0x437 plus Cancel; the selected item is matched against the recipe table at 0x800F4088.
	_close_all(); _say(0, 34); var fresh := true
	while true:
		var code := await _pick(FIRST_ITEM, LAST_ITEM, 64, 6, false, fresh); fresh = false
		if code < 0: break
		await _combine(code)
	_close_all()
func _combine(code: int) -> void:
	_close(0); list_dimmed = true; list_active = false
	var recipe := {}; var other := -1; var hint := 0
	for entry: Dictionary in dev["recipes"]:
		if code == int(entry["first"]): recipe = entry; other = int(entry["second"]); hint = int(entry["second_hint"]); break
		if code == int(entry["second"]): recipe = entry; other = int(entry["first"]); hint = int(entry["first_hint"]); break
	if recipe.is_empty(): _say(2, 21); await _wait_closed(2)
	elif other >= 0 and not _owned(other): message_context["native_item_name"] = _name(other); _say(2, hint); await _wait_closed(2)
	else:
		var result := int(recipe["result"]); var kind := int(recipe["kind"]); var make := true
		if kind == 2: message_context["native_item_name"] = _name(result); _say(2, int(recipe["first_hint"])); await _wait_closed(2)
		elif kind == 1: message_context["native_item_name"] = _name(result); _say(2, 17); make = await _choice(2) == 0; _close(2)
		else: message_context["native_item_name"] = _name(other); _say(2, 15); make = await _choice(2) == 0; _close(2)
		if make and kind != 2:
			message_context["native_item_name"] = _name(result); _say(2, 24 if kind in [1, 3] else 23); await _wait_closed(2)
		if make:
			_store(result, true); _store(code, false)
			if other >= 0: _store(other, false)
	list_dimmed = false; _say(0, 34)
func _change_weapon() -> void:
	# State 2 (0x800EADD4): picking a weapon sets the equipped special weapon byte (player+0x18E) after a confirmation.
	_close_all(); _say(0, 31); var fresh := true
	while true:
		var code := await _pick(FIRST_WEAPON, LAST_WEAPON, 56, 3, true, fresh); fresh = false
		if code < 0: break
		_close(0); list_dimmed = true; list_active = false; message_context["native_item_name"] = _name(code); _say(2, 2)
		var answer := await _choice(2); _close(2)
		if answer == 0:
			host.player.equipped_special = code - 0x380; _say(2, 6); await _wait_closed(2); list_dimmed = false; break
		list_dimmed = false; _say(0, 31)
	_close_all(); weapon_panel = false
func _improve() -> void:
	# State 3 (0x800EB1FC): weapon, then stat; the cost comes from ST04T 0x800EDBA4.
	_close_all(); _say(0, 32); var fresh := true
	while true:
		var code := await _pick(FIRST_WEAPON, LAST_WEAPON, 56, 3, true, fresh); fresh = false
		if code < 0: break
		_close(0); list_dimmed = true; list_active = false
		while true:
			_say(0, 33); _say(2, 1); windows[2]["selection"] = stat_selection; preview_stat = stat_selection
			var stat := await _choice(2); _close(0); _close(2); preview_stat = -1
			if stat < 0 or stat > 4: break
			stat_selection = stat
			await _spend(code - 0x380, stat)
		list_dimmed = false; _say(0, 32)
	_close_all(); weapon_panel = false
func _spend(weapon: int, stat: int) -> void:
	var cost := _cost(weapon, stat)
	if cost < 0: _say(3, 8); await _wait_closed(3); return
	_say(0, 5); _say(3, 3, cost)
	var answer := await _choice(3); _close(3)
	if answer == 0 and host.player.zenny < cost: _say(3, 9); await _wait_closed(3)
	elif answer == 0:
		_wallet(host.player.zenny - cost); _levels(weapon)[stat] = int(_levels(weapon)[stat]) + 1; _say(3, 7); await _wait_closed(3)
	_close(0)
# ---- item and weapon lists (EC4F8 / EC0C8 / EC5E8) ----
func _owned_codes(first: int, last: int) -> Array[int]:
	var result: Array[int] = []
	for code in range(first, last + 1):
		if _owned(code): result.append(code)
	result.append(RULES.CANCEL); return result
func _pick(first: int, last: int, top: int, rows: int, weapons: bool, fresh: bool) -> int:
	list_y = top; list_rows = rows; weapon_panel = weapons; list_codes = _owned_codes(first, last); description_code = -1
	if fresh: list = {"cursor": 0, "scroll": 0, "count": list_codes.size(), "rows": rows, "move": 0, "scrolling": 0, "sound": ""}
	list["count"] = list_codes.size(); RULES.cursor_step(list, {}); list_active = true; list_dimmed = false; _close(4)
	while true:
		await _tick()
		list_codes = _owned_codes(first, last); list["count"] = list_codes.size()
		var index := int(list["scroll"]) + int(list["cursor"]); var code := list_codes[index] if index < list_codes.size() else RULES.CANCEL
		if code != description_code: description_code = code; panel_code = code; _close(4); _open_description(code)
		var result := int(list["step"]) if list.has("step") else 0
		list.erase("step")
		if result == 0: continue
		list_active = false; _close(4); description_code = -1
		return -1 if result < 0 or code == RULES.CANCEL else code
	return -1
# ---- drawing ----
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	var browsing := list_active or list_dimmed
	if browsing: _draw_list()
	var hand_visible := false
	for id in [4, 0, 2, 3]:
		if not windows.has(id): continue
		var window: Dictionary = windows[id]; var frame: Rect2 = window["frame"]; FRAME.draw(self, layout, "prompt", frame)
		var layout_entry: Dictionary = window["layouts"][window["page"]]; var origin: Vector2 = layout_entry["origin"]; var remaining := int(window["glyphs"]); var y := origin.y + 3.0 + font.get_ascent(12)
		for line in str(window["pages"][window["page"]]).split("\n"):
			var shown := mini(remaining, line.length())
			if shown > 0: _draw_text(Vector2(origin.x, y), line.substr(0, shown), Color.WHITE)
			remaining = maxi(remaining - line.length() - 1, 0); y += 16.0
		var choice: Dictionary = layout_entry["choice"]
		if not choice.is_empty() and bool(window["complete"]):
			var rows: Array = choice["rows"]
			for index in range(rows.size()):
				var point: Array = rows[index]["native_coordinates"]; var x := origin.x + 2.0 * float(point[0]); var row_y := origin.y + 16.0 * float(point[1]); _draw_text(Vector2(x + 14.0, row_y + font.get_ascent(12)), str(rows[index]["text"]), Color.WHITE)
				if index == int(window["selection"]): choice_hand.select_at(Vector2(x, row_y)); hand_visible = true
			if id == 2 and preview_stat >= 0: preview_stat = int(window["selection"])
	choice_hand.visible = hand_visible
	if browsing: _update_list_hand()
	else: list_hand.hide()
func _draw_list() -> void:
	var count := int(list["count"]); var scroll := int(list["scroll"]); var shifting := int(list["scrolling"]); var offset := 0; var rows := mini(list_rows, count)
	FRAME.draw(self, layout, "prompt", Rect2(16, list_y - 1, 146, 16 * rows + 7))
	if shifting != 0 and absi(shifting) < 3:
		var phase := absi(shifting) % 3
		if shifting > 0: offset = 10 if phase == 1 else 5 if phase == 2 else 0
		else: offset = 5 if phase == 1 else 10 if phase == 2 else 0
	var base := scroll - (1 if shifting < 0 else 0)
	for row in range(rows + 1):
		var index := base + row; var y := list_y + 4 - offset + 16 * row
		if index >= 0 and index < mini(count, list_codes.size()) and y >= list_y + 2 and y <= list_y + 4 + 16 * (rows - 1) + 4: _draw_text(Vector2(43, y + font.get_ascent(12)), _name(list_codes[index]), Color(0.55, 0.55, 0.55) if list_dimmed else Color.WHITE)
	if scroll > 0: _draw_arrow(PackedVector2Array([Vector2(166, list_y + 6), Vector2(178, list_y + 6), Vector2(172, list_y - 2)]))
	if count - scroll > list_rows: _draw_arrow(PackedVector2Array([Vector2(166, list_y + 16 * rows - 2), Vector2(178, list_y + 16 * rows - 2), Vector2(172, list_y + 16 * rows + 6)]))
	if weapon_panel and panel_code >= FIRST_WEAPON and panel_code <= LAST_WEAPON: _draw_weapon(panel_code - 0x380)
func _draw_weapon(weapon: int) -> void:
	# Gauges are 56 pixels wide, filled level * 56 / cap (ST04T 0x800ECBE4..); the selected stat previews one more level.
	var entry: Dictionary = dev["weapons"].get(str(weapon), {}); var caps: Array = entry.get("caps", [0, 0, 0, 0, 0]); var levels := _levels(weapon)
	FRAME.draw(self, layout, "prompt", Rect2(16, 114, 288, 51))
	for stat in range(5):
		var cap := int(caps[stat]); var level := int(levels[stat]) + (1 if stat == preview_stat and int(levels[stat]) < cap else 0); var column := 0 if stat < 3 else 1; var row := stat if stat < 3 else stat - 3
		var origin := Vector2(28 + 144 * column, 119 + 15 * row); var tint := Color(0.55, 0.55, 0.55) if cap == 0 else Color.WHITE
		_draw_text(Vector2(origin.x, origin.y + font.get_ascent(12) - 2), STATS[stat], tint)
		draw_rect(Rect2(origin.x + 66, origin.y + 3, GAUGE_WIDTH, 6), Color(0.12, 0.12, 0.2))
		if cap > 0: draw_rect(Rect2(origin.x + 66, origin.y + 3, GAUGE_WIDTH * level / cap, 6), Color(1.0, 0.85, 0.3) if stat == preview_stat and level > int(levels[stat]) else Color(0.35, 0.85, 1.0))
func _update_list_hand() -> void:
	if int(list["cursor"]) == 0xff: list_hand.hide(); return
	var bob: int = [2, 2, 2, 1, 1, 0, -1, -1, -2, -2, -2, -1, -1, 0, 1, 1][(ticks >> 1) & 15]; var point := Vector2(27 if list_dimmed else 27 + bob, list_y + 4 + 16 * int(list["cursor"]))
	list_hand.show(); list_hand.modulate = Color(0.55, 0.55, 0.55) if list_dimmed else Color.WHITE; list_hand.select_at(point)
