extends Control
# Junk shop / general store (scene 8 of the stage overlays, ST0AT 0x800EBADC..): the greeting, Buy / Sell / Recharge menus, item lists and purchases.
# The overlay message bank (assets/shops) drives every window; rules and prices live in shop_rules.gd.
signal ticked
const FRAME := preload("res://scripts/ui/common/native_menu_frame.gd")
const RULES := preload("res://scripts/ui/menus/shop_rules.gd")
const HAND := preload("res://scripts/ui/common/native_menu_cursor.gd")
const EVENT_SCRIPT := preload("res://scripts/world/core/event_script.gd")
const TICK := 0.04
var host: Node
var active := false  # event_script reads this to know whether a dialogue window is busy; the shop owns its windows
var rules
var stage := ""
var set_index := 0
var state: Dictionary = {}
var messages: Node
var message_context: Dictionary = {}
var windows: Dictionary = {}
var results: Dictionary = {}
var list: Dictionary = {}
var codes: Array[int] = []
var items: Dictionary = {}
var layout: Dictionary = {}
var font: Font
var colour_fonts: Array[Font] = []
var surface: Control
var list_hand: TextureRect
var choice_hand: TextureRect
var accumulator := 0.0
var ticks := 0
var input: Dictionary = {}
var list_active := false
var list_dimmed := false
var list_selling := false
var description_code := -1
var icon_atlas: Texture2D
static func supports(shop_stage: String) -> bool:
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/manifest.json")) if FileAccess.file_exists("res://assets/shops/manifest.json") else null
	return manifest is Dictionary and manifest.get("banks", {}).has(shop_stage)
func run(gameplay: Node, shop_stage: String, shop_set: int) -> bool:
	host = gameplay; stage = shop_stage; set_index = shop_set
	var shop: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/shop.json")); items = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/items.json"))
	if not shop is Dictionary or not items is Dictionary: push_error("Missing shop data"); return false
	rules = RULES.new(shop["shop"], items); layout = host.dialogue_box.layout; font = host.dialogue_box.font; colour_fonts = host.dialogue_box.colour_fonts
	messages = Node.new(); messages.set_script(EVENT_SCRIPT); add_child(messages)
	if not messages.configure(self, "res://assets/shops/manifest.json", message_context) or not messages.prepare_stage(stage): push_error("Missing shop message bank for " + stage); return false
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; z_index = 20
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	list_hand = HAND.new(); list_hand.configure(Vector2.ZERO); list_hand.hide(); surface.add_child(list_hand); choice_hand = HAND.new(); choice_hand.configure(Vector2.ZERO); choice_hand.hide(); surface.add_child(choice_hand)
	resized.connect(_layout); _layout(); _load_state(); rules.initialize_stock(state); rules.normalize(state); _store_state()
	var mode := 0; var sub := set_index
	while mode >= 0:
		match mode:
			0: mode = await _main_menu(); sub = set_index if mode == 1 else 0
			1, 2:
				var outcome := await _trade_menu(mode == 2, sub)
				mode = int(outcome["mode"]); sub = int(outcome["sub"])
			3: mode = await _recharge_menu()
	await _farewell()
	_store_state(); return true
func _process(delta: float) -> void:
	accumulator += delta
	while accumulator >= TICK:
		accumulator -= TICK; ticks += 1; _step_windows()
		if list_active: _step_list()
		input.clear(); ticked.emit()
	queue_redraw()
func _unhandled_input(event: InputEvent) -> void:
	var handled := false
	for entry: Array in [["confirm", "interact", false], ["confirm", "ui_accept", false], ["cancel", "ui_cancel", false], ["up", "ui_up", true], ["down", "ui_down", true], ["left", "ui_left", false], ["right", "ui_right", false], ["page_up", "ui_page_up", true], ["page_down", "ui_page_down", true]]:
		if event.is_action_pressed(entry[1], entry[2]): input[entry[0]] = true; handled = true
	if handled: get_viewport().set_input_as_handled()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor := size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
func _tick() -> void: await ticked
func _sound(role: String) -> void:
	if not role.is_empty() and is_instance_valid(host.audio): host.audio.play_ui(role)
# ---- state shared with the game ----
func _load_state() -> void:
	var player: Node = host.player; var context: Dictionary = host.native_context; var inventory: Dictionary = player.inventory
	state = RULES.default_state(); state["zenny"] = player.zenny; state["progress"] = int(context.get("native_save_byte14", 0)); state["selector"] = int(context.get("native_save_byte44", 1)); state["max_life"] = player.max_health; state["life"] = player.health
	for id: Variant in context.get("native_shop_stock", []): state["flags"][int(id)] = true
	state["canteen"] = [int(context.get("native_canteen", [0, 0])[0]), int(context.get("native_canteen", [0, 0])[1])]; state["bottle"] = [int(context.get("native_bottle", [0, 0])[0]), int(context.get("native_bottle", [0, 0])[1])]
	for group: String in ["items", "key_items", "body_parts", "buster_parts"]:
		for id: String in inventory.get(group, {}): state["owned"][int(id)] = true
	for group: String in ["body_parts", "buster_parts"]:
		for id: String in player.equipment.get(group, []):
			if not id.is_empty(): state["equipped"].append(int(id))
	message_context["native_save_byte14"] = state["progress"]; message_context["native_save_byte44"] = state["selector"]; message_context["event_flags"] = {}; message_context["native_message_number"] = 0
func _group_of(code: int) -> String:
	if code >= 0x3d0 and code < 0x400: return "key_items"
	if code >= 0x400: return "items"
	return "body_parts" if code >= 0x3b8 else "buster_parts"
func _store_state() -> void:
	var player: Node = host.player; var context: Dictionary = host.native_context; var inventory: Dictionary = player.inventory
	player.zenny = int(state["zenny"]); context["native_wallet"] = player.zenny
	for group: String in ["items", "key_items", "body_parts", "buster_parts"]:
		for id: String in inventory[group].keys():
			if int(id) >= 0x394 and not state["owned"].has(int(id)): inventory[group].erase(id)
	for code: int in state["owned"]:
		if not inventory[_group_of(code)].has(str(code)): inventory[_group_of(code)][str(code)] = 1
	var stock: Array = state["flags"].keys(); stock.sort(); context["native_shop_stock"] = stock; context["native_canteen"] = state["canteen"].duplicate(); context["native_bottle"] = state["bottle"].duplicate()
	if int(state["max_life"]) != player.max_health or int(state["life"]) != player.health: player.max_health = int(state["max_life"]); player.health = int(state["life"]); player.health_changed.emit(player.health, player.max_health)
	for delta: int in state["karma"]: context.merge(EVENT_SCRIPT.native_stat_mutation(context, delta, "native_save_word42", "native_save_byte45"), true)
	state["karma"] = []
	var flags: Dictionary = context.get("event_flags", {})
	for id: int in state["events"]: flags[id] = true
	state["events"] = {}; context["event_flags"] = flags
# ---- windows ----
func _row(index: int) -> int: return int(rules.tables["set_rows"][set_index][index])
func _open(id: int, index: int, number := -1) -> void:
	if number >= 0: message_context["native_message_number"] = number
	var window_state := {"flags": 0x00010083, "byte23": 2, "choice_index": 0, "text_speed": 2, "origin_x": 24, "origin_y": 172, "window_width": 138, "window_lines": 2}
	var resolved: Dictionary = messages._resolve_program(stage, index, window_state)
	if not bool(resolved.get("supported", false)): push_error("Unresolved shop message %02X" % index); windows.erase(id); return
	var pages: Array = resolved["pages"]; var page_commands: Array = resolved["page_commands"]; var page_choices: Array = resolved["page_choices"]; var origin := Vector2(24, 172); var width := 138; var lines := 2; var layouts: Array[Dictionary] = []
	for page in range(pages.size()):
		var choice: Dictionary = page_choices[page] if page < page_choices.size() else {}
		if choice.has("window_origin"): origin = Vector2(choice["window_origin"][0], choice["window_origin"][1]); width = int(choice.get("window_width", width)); lines = maxi(1, int(choice.get("window_lines", lines)) & 15)
		for command: Dictionary in page_commands[page] if page < page_commands.size() else []:
			var args: Array = command.get("arguments", [])
			if int(command.get("opcode", -1)) == 0x06 and args.size() == 6: origin = Vector2((int(args[0]) << 8) | int(args[1]), (int(args[2]) << 8) | int(args[3])); width = int(args[4]); lines = maxi(1, int(args[5]) & 15)
		layouts.append({"origin": origin, "frame": Rect2(origin - Vector2(7, 3), Vector2(2 * width + 3, 16 * lines + 7)), "choice": choice, "wait": _has_wait(page_commands[page] if page < page_commands.size() else []), "updates": int(resolved["page_wait_updates"][page]) if page < resolved["page_wait_updates"].size() else 0})
	if pages.is_empty(): layouts.append({"origin": origin, "frame": Rect2(origin - Vector2(7, 3), Vector2(2 * width + 3, 16 * lines + 7)), "choice": {}, "wait": false, "updates": 0}); pages = [""]
	var entry: Dictionary = messages.entries[stage][int(resolved["program_index"])]; var commands: Array = entry.get("native_commands", [])
	windows[id] = {"pages": pages, "speeds": resolved["page_speeds"], "layouts": layouts, "page": 0, "glyphs": 0, "delay": 0, "complete": false, "waiting": 0, "persist": not commands.is_empty() and messages._native_opcode(commands[-1]) == 0x2B, "selection": 0, "frame": layouts[0]["frame"]}
	results.erase(id); _start_page(id)
func _has_wait(commands: Array) -> bool:
	for command: Dictionary in commands:
		if int(command.get("opcode", -1)) in [0x18, 0x24]: return true
	return false
func _open_description(code: int) -> void:
	var text := str(items["descriptions"].get(str(code), ""))
	windows[4] = {"pages": [text], "speeds": [[0]], "layouts": [{"origin": Vector2(24, 172), "frame": Rect2(17, 169, 279, 39), "choice": {}, "wait": false, "updates": 0}], "page": 0, "glyphs": 0, "delay": 0, "complete": false, "waiting": 0, "persist": true, "selection": 0, "default_speed": 0, "frame": Rect2(17, 169, 279, 39)}
	results.erase(4); _start_page(4)
func _open_frame(id: int, rectangle: Rect2) -> void:
	windows[id] = {"pages": [""], "speeds": [[]], "layouts": [{"origin": rectangle.position + Vector2(7, 3), "frame": rectangle, "choice": {}, "wait": false, "updates": 0}], "page": 0, "glyphs": 0, "delay": 0, "complete": true, "waiting": 0, "persist": true, "selection": 0, "frame": rectangle}
func _close(id: int) -> void: windows.erase(id)
func _close_all() -> void:
	for id in [1, 2, 3, 4]: _close(id)
	description_code = -1
func _start_page(id: int) -> void:
	var window: Dictionary = windows[id]; var layout_entry: Dictionary = window["layouts"][window["page"]]; window["frame"] = layout_entry["frame"]; window["glyphs"] = 0; window["delay"] = 0; window["complete"] = false; window["waiting"] = 0; window["selection"] = int(layout_entry["choice"].get("selected_index", 0)) if not (layout_entry["choice"] as Dictionary).is_empty() else 0
	if str(window["pages"][window["page"]]).is_empty(): window["complete"] = true
func _step_windows() -> void:
	var shared_input := input.duplicate()
	for id: int in windows.keys():
		if not windows.has(id): continue
		input = shared_input.duplicate()
		var window: Dictionary = windows[id]; var page := int(window["page"]); var text := str(window["pages"][page]); var layout_entry: Dictionary = window["layouts"][page]
		if not bool(window["complete"]):
			if input.has("confirm") and id != 4: window["glyphs"] = text.length(); window["complete"] = true; input.erase("confirm"); continue
			if int(window["delay"]) > 0: window["delay"] = int(window["delay"]) - 1; continue
			var speeds: Array = window["speeds"][page] if page < window["speeds"].size() else []
			while int(window["glyphs"]) < text.length():
				var index := int(window["glyphs"]); var speed := int(speeds[index]) if index < speeds.size() else int(window.get("default_speed", 2)); window["glyphs"] = index + 1
				if text[index] != "\n" and text[index] != " " and speed > 0: window["delay"] = speed - 1; break
			if int(window["glyphs"]) >= text.length(): window["complete"] = true
			continue
		_step_page_end(id, window, layout_entry)
	input = shared_input
func _step_page_end(id: int, window: Dictionary, layout_entry: Dictionary) -> void:
	var choice: Dictionary = layout_entry["choice"]
	if not choice.is_empty():
		var rows: Array = choice.get("rows", []); var count := rows.size()
		if bool(input.get("cancel", false)) and not bool(choice.get("cancel_disabled", false)): results[id] = count; _sound("menu_cancel"); windows.erase(id); input.erase("cancel"); return
		var selected := _move_selection(rows, int(window["selection"]))
		if selected != int(window["selection"]): window["selection"] = selected; _sound("menu_move")
		if bool(input.get("confirm", false)): results[id] = selected; _sound("menu_confirm"); windows.erase(id); input.erase("confirm")
		return
	if int(layout_entry["updates"]) > 0:
		window["waiting"] = int(window["waiting"]) + 1
		if int(window["waiting"]) >= int(layout_entry["updates"]): _advance_page(id)
		return
	if bool(layout_entry["wait"]):
		if bool(input.get("confirm", false)) or bool(input.get("cancel", false)): input.erase("confirm"); input.erase("cancel"); _advance_page(id)
		return
	_advance_page(id)
func _advance_page(id: int) -> void:
	var window: Dictionary = windows[id]
	if int(window["page"]) + 1 < window["pages"].size(): window["page"] = int(window["page"]) + 1; _start_page(id)
	elif not bool(window["persist"]): windows.erase(id)
func _move_selection(rows: Array, current: int) -> int:
	if rows.size() <= 1: return current
	var source: Array = rows[current]["native_coordinates"]; var best := -1; var best_distance := 256
	for entry: Array in [["up", 0, -1], ["down", 0, 1], ["left", -1, 0], ["right", 1, 0]]:
		if not bool(input.get(entry[0], false)): continue
		best = -1; best_distance = 256
		for candidate in range(rows.size()):
			if candidate == current: continue
			var point: Array = rows[candidate]["native_coordinates"]; var distance := 0
			if int(entry[2]) != 0 and int(point[0]) == int(source[0]): distance = posmod((int(point[1]) - int(source[1])) * int(entry[2]), 256)
			elif int(entry[1]) != 0 and int(point[1]) == int(source[1]): distance = posmod((int(point[0]) - int(source[0])) * int(entry[1]), 256)
			if distance > 0 and distance < best_distance: best = candidate; best_distance = distance
		if best >= 0: return best
	return current
func _wait_closed(id: int) -> void:
	while windows.has(id): await _tick()
func _choice(id: int) -> int:
	while windows.has(id): await _tick()
	return int(results.get(id, -1))
# ---- flow (the original scene states) ----
func _main_menu() -> int:
	_close_all(); _open(4, _row(0)); _open(2, 3)
	var choice := await _choice(2); _close(4)
	match choice:
		0: return 1
		1: return 2
		2: return 3
	return -1
func _trade_menu(selling: bool, sub: int) -> Dictionary:
	while true:
		if sub == 0:
			_close_all(); _open(4, _row(1 if selling else 2)); _open(2, 4)
			var choice := await _choice(2); _close(4)
			if choice == 0: sub = 1
			elif choice == 1: sub = 2
			elif choice < 0 or choice in [2, 3]: return {"mode": 0, "sub": 0}
		else:
			await _list_menu(selling, sub == 2)
			if set_index == 0 or selling: sub = 0
			else: return {"mode": 0, "sub": 0}
	return {"mode": 0, "sub": 0}
func _list_menu(selling: bool, parts: bool) -> void:
	_close(2); list = {"cursor": 0, "scroll": 0, "count": 0, "rows": 6, "move": 0, "scrolling": 0, "sound": ""}; list_selling = selling; list_dimmed = false
	_open_frame(2, Rect2(17, 58, 279, 103)); _close(1); _rebuild_list(parts, selling)
	_open_frame(1, Rect2(17, 169, 279, 39)); await _tick(); list_active = true
	while true:
		await _tick()
		var item := codes[int(list["scroll"]) + int(list["cursor"])] if int(list["cursor"]) != 0xff and int(list["scroll"]) + int(list["cursor"]) < codes.size() else -1
		if item != description_code and item >= 0: description_code = item; _close(4); _open_description(item)
		var result := int(list["step"]) if list.has("step") else 0
		list.erase("step")
		if result == 0: continue
		if item == RULES.CANCEL: result = -1
		if result > 0:
			list_active = false; list_dimmed = true; await _confirm(item, selling, parts); list_dimmed = false; description_code = -1; _close(4); list_active = true
		else: list_active = false; _close(4); _close(1); _close(2); description_code = -1; return
func _step_list() -> void:
	var result := RULES.cursor_step(list, {"cancel": input.has("cancel"), "confirm": input.has("confirm"), "up": input.has("up"), "down": input.has("down"), "page_up": input.has("page_up"), "page_down": input.has("page_down")})
	_sound(str(list["sound"])); list["step"] = result
func _rebuild_list(parts: bool, selling: bool) -> void:
	codes = rules.build_list(state, set_index, selling, parts); list["count"] = codes.size()
	RULES.cursor_step(list, {})
	if int(list["count"]) == 0: list["cursor"] = 0xff
func _confirm(item: int, selling: bool, parts: bool) -> void:
	_close(4); _close(3)
	if not selling and int(state["zenny"]) < rules.price(state, item, true): _open(4, _row(0xb)); await _wait_closed(4); return
	_open(3, _row(0xe if rules.is_delivery(item) else 3))
	var choice := await _choice(3)
	if choice != 0: return
	if selling: rules.sell(state, item)
	else: rules.purchase(state, item)
	_store_state(); _rebuild_list(parts, selling); _open(4, _row(4)); await _wait_closed(4)
func _recharge_menu() -> int:
	while true:
		_close_all(); _open(4, _row(5)); _open(2, 5)
		var choice := await _choice(2); _close(4)
		if choice == 0 or choice == 1:
			if await _recharge(choice == 1): return 0
		else: return 0
	return 0
func _recharge(bottle: bool) -> bool:
	var tank: Array = state["bottle"] if bottle else state["canteen"]; var code := 0x401 if bottle else 0x400
	_close(3)
	if not state["owned"].has(code): _open(4, _row(0xa)); await _wait_closed(4); return false
	if int(tank[0]) == int(tank[1]): _open(4, _row(9)); await _wait_closed(4); return false
	var price := (1000 if bottle else 100) * (int(tank[1]) - int(tank[0]))
	_open(3, _row(7 if bottle else 6), price)
	if await _choice(3) != 0: return false
	if int(state["zenny"]) < price: _open(4, _row(0xd)); await _wait_closed(4); return false
	rules.add_zenny(state, -price); tank[0] = tank[1]; _store_state(); _close(4); _open(4, _row(8)); await _wait_closed(4)
	return true
func _farewell() -> void:
	_close_all(); _open(4, _row(0xc)); await _wait_closed(4); _close_all()
	var flags: Dictionary = host.native_context.get("event_flags", {})
	for id in [0x6ff, 0x6fe]: flags[id] = false; flags[str(id)] = false
	host.native_context["event_flags"] = flags
# ---- drawing ----
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "prompt", Rect2(17, 27, 97, 23)); _draw_text(Vector2(24, 33 + font.get_ascent(12)), _zenny_text(), Color.WHITE)
	var hand_visible := false
	for id in [2, 1, 4, 3]:
		if not windows.has(id) or id == 1 and (windows.has(3) or windows.has(4)): continue
		var window: Dictionary = windows[id]; var frame: Rect2 = window["frame"]; FRAME.draw(self, layout, "prompt", frame)
		if id == 2 and list_active or id == 2 and list_dimmed: _draw_list(); continue
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
	choice_hand.visible = hand_visible
	if list_active or list_dimmed: _update_list_hand()
	else: list_hand.hide()
func _zenny_text() -> String:
	var digits := str(int(state.get("zenny", 0))); return "\ue050".repeat(maxi(7 - digits.length(), 0)) + digits + "\ue049"
func _draw_list() -> void:
	var count := int(list["count"]); var scroll := int(list["scroll"]); var shifting := int(list["scrolling"]); var offset := 0
	if shifting != 0 and absi(shifting) < 3:
		var phase := absi(shifting) % 3
		if shifting > 0: offset = 10 if phase == 1 else 5 if phase == 2 else 0
		else: offset = 5 if phase == 1 else 10 if phase == 2 else 0
	var base := scroll - (1 if shifting < 0 else 0)
	for row in range(mini(count, 6) + 1):
		var index := base + row; var y := 63 - offset + 16 * row
		if index >= 0 and index < count and y >= 61 and y <= 148: _draw_list_row(codes[index], y)
	if scroll > 0: _draw_arrow(PackedVector2Array([Vector2(148, 60), Vector2(164, 60), Vector2(156, 52)]))
	if count - scroll > 6: _draw_arrow(PackedVector2Array([Vector2(148, 158), Vector2(164, 158), Vector2(156, 166)]))
func _draw_arrow(points: PackedVector2Array) -> void:
	var phase := ticks & 31; var value := (0x7f + phase * 8 if phase <= 16 else 255 - (phase - 16) * 8) / 255.0; draw_colored_polygon(points, Color(value, value, value))
func _draw_list_row(code: int, y: int) -> void:
	var tint := Color(0.55, 0.55, 0.55) if list_dimmed else Color.WHITE
	if code == RULES.CANCEL: _draw_text(Vector2(52, y + font.get_ascent(12)), str(items["names"].get(str(code), "Cancel")), tint); return
	var price: int = rules.sell_price(state, code) if list_selling else rules.price(state, code, true)
	if not list_selling and int(state["zenny"]) < price: tint = Color(0.55, 0.55, 0.55)
	var digits := str(price)
	_draw_icon(code, y)
	_draw_text(Vector2(52, y + font.get_ascent(12)), str(items["names"].get(str(code), "")), tint); _draw_text(Vector2(187, y + font.get_ascent(12)), "\ue050".repeat(maxi(7 - digits.length(), 0)) + digits, tint)
func _update_list_hand() -> void:
	if int(list["cursor"]) == 0xff: list_hand.hide(); return
	var bob: int = [2, 2, 2, 1, 1, 0, -1, -1, -2, -2, -2, -1, -1, 0, 1, 1][(ticks >> 1) & 15]; var point := Vector2(24 if list_dimmed else 24 + bob, 63 + 16 * int(list["cursor"]))
	list_hand.show(); list_hand.modulate = Color(0.75, 0.75, 0.75) if list_dimmed else Color.WHITE; list_hand.select_at(point)
func _draw_text(origin: Vector2, text: String, tint: Color) -> void:
	var colour := 0; var previous := 0; var segment := ""; var x := origin.x
	for character in text + String.chr(0xE0FF):
		var code := character.unicode_at(0)
		if code == 0xE064 or code == 0xE065:
			x = _flush_segment(segment, x, origin.y, colour, tint); segment = ""; draw_string(ThemeDB.fallback_font, Vector2(x, origin.y), "\u03b1" if code == 0xE064 else "\u03a9", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, tint); x += 10.0; continue
		if code < 0xE0F0 or code > 0xE0FF: segment += character; continue
		x = _flush_segment(segment, x, origin.y, colour, tint); segment = ""
		if code == 0xE0FF: colour = previous
		else: previous = colour; colour = code - 0xE0F0
func _flush_segment(segment: String, x: float, baseline: float, colour: int, tint: Color) -> float:
	if segment.is_empty(): return x
	var segment_font: Font = colour_fonts[colour] if colour < colour_fonts.size() and colour_fonts[colour] != null else font
	draw_string(segment_font, Vector2(x, baseline), segment, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, tint); return x + segment_font.get_string_size(segment, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
const ICONS := [Vector2(0x80, 0), Vector2(0x90, 0), Vector2(0xa0, 0), Vector2(0xb0, 0), Vector2(0xc0, 0), Vector2(0xd0, 0), Vector2(0xe0, 0), Vector2(0xc0, 0x10), Vector2(0xf0, 0), Vector2(0xb0, 0x10), Vector2(0x70, 0x10)]
static func _icon_index(code: int) -> int:
	# SLES-independent icon classes of the overlay list draw routine (ST0AT 0x800EE35C), by item index code - 0x380.
	var index := code - 0x380
	for entry: Array in [[0x14, 0x24, 0], [0x38, 4, 2], [0x3c, 0xc, 3], [0x48, 8, 1], [0x83, 5, 9], [0x88, 0x34, 6], [0xcd, 3, 10], [0xbc, 2, 8], [0xbe, 3, 7], [0xc3, 0x34, 5]]:
		if index >= entry[0] and index < entry[0] + entry[1]: return entry[2]
	return 8
func _draw_icon(code: int, y: int) -> void:
	if icon_atlas == null: icon_atlas = load("res://assets/menu/status_normal_atlas.png") as Texture2D
	draw_texture_rect_region(icon_atlas, Rect2(37, y - 2, 16, 16), Rect2(ICONS[_icon_index(code)], Vector2(16, 16)), Color(0.55, 0.55, 0.55) if list_dimmed else Color.WHITE)
