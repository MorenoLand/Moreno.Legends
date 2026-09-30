extends RefCounted
# Shop rules shared by every junk shop and general store: stock, item lists, prices and purchases. Ported from the stage overlay shop module
# (ST0AT 0x800EBADC..0x800EE4D4) and SLES0x80051534; the state dictionary stands in for the original save fields:
# zenny, progress (byte14), selector (byte44), flags (stock flags 0x480..0x57F), owned (item codes), equipped (codes), canteen/bottle [charge, capacity], max_life, life.
const FIRST := 0x380
const CANCEL := 0x485
const MAX_ZENNY := 9999999
var tables: Dictionary
var catalog: Dictionary
func _init(shop_tables: Dictionary, item_catalog: Dictionary) -> void:
	tables = {"stock_a": _integers(shop_tables["stock_a"]), "stock_b": _integers(shop_tables["stock_b"]), "category_ranges": _integers(shop_tables["category_ranges"]), "unsellable": _integers(shop_tables["unsellable"]), "set_rows": _integers(shop_tables["set_rows"])}; catalog = item_catalog
static func _integers(value: Variant) -> Variant:
	if value is Array:
		var result := []
		for entry: Variant in value: result.append(_integers(entry))
		return result
	return int(value)
static func default_state() -> Dictionary:
	return {"zenny": 0, "progress": 0, "selector": 1, "flags": {}, "owned": {}, "equipped": [], "canteen": [0, 0], "bottle": [0, 0], "max_life": 80, "life": 80, "events": {}, "karma": []}
func flag(state: Dictionary, id: int) -> bool: return bool(state["flags"].get(id, false))
func set_flag(state: Dictionary, id: int) -> void: state["flags"][id] = true
func clear_flag(state: Dictionary, id: int) -> void: state["flags"].erase(id)
func initialize_stock(state: Dictionary) -> void:
	var lists_a: Array = tables["stock_a"]; var lists_b: Array = tables["stock_b"]
	for index in range(mini(int(state["progress"]) + 1, lists_a.size())):
		if flag(state, 0x480 + index): continue
		for id: int in lists_a[index]: set_flag(state, 0x480 + id)
		for id: int in lists_b[index]: set_flag(state, 0x480 + id)
		set_flag(state, 0x480 + index)
func normalize(state: Dictionary) -> void:
	var owned: Dictionary = state["owned"]
	for entry: Array in [[0x394, 0x24], [0x3b8, 4], [0x3bc, 0xc], [0x3c8, 8]]:
		for offset in range(1, entry[1]):
			if owned.has(entry[0] + offset) and flag(state, entry[0] + 0x100 + offset): clear_flag(state, entry[0] + 0x100 + offset)
	for offset in range(0x78):
		if owned.has(0x400 + offset) and flag(state, 0x500 + offset): clear_flag(state, 0x500 + offset)
	for offset in range(7): update_special(state, 0x478 + offset)
	for id in [0x394, 0x3b8, 0x3bc, 0x3c8]: owned.erase(id)
	for id in [0x494, 0x4b8, 0x4bc, 0x4c8]: clear_flag(state, id)
func update_special(state: Dictionary, code: int) -> void:
	match code:
		0x478:
			if (int(state["max_life"]) - 0x50) >> 4 >= 5: clear_flag(state, 0x578)
		0x479: set_special_flag(state, 0x579, state["owned"].has(0x400) and int(state["canteen"][1]) < 99)
		0x47a: set_special_flag(state, 0x57a, state["owned"].has(0x401) and int(state["bottle"][1]) < 99)
func set_special_flag(state: Dictionary, id: int, value: bool) -> void:
	if value: set_flag(state, id)
	else: clear_flag(state, id)
func build_list(state: Dictionary, shop_set: int, selling: bool, parts: bool) -> Array[int]:
	for offset in range(7): update_special(state, 0x478 + offset)
	var result: Array[int] = []; var range_entry: Array = tables["category_ranges"][1 if parts else 0]; var start := int(range_entry[0]); var count := int(range_entry[1])
	if selling:
		var excluded: Array = tables["unsellable"].duplicate()
		if parts: excluded.append_array(state["equipped"])
		for index in range(count):
			var code := FIRST + start + index
			if not code in excluded and state["owned"].has(code): result.append(code)
	else:
		if shop_set == 0 and not parts:
			for offset in range(7):
				if flag(state, 0x578 + offset): result.append(0x478 + offset)
		for index in range(count):
			var number := start + index
			if (shop_set == 0) == (number < 0xbc) and flag(state, 0x480 + number): result.append(FIRST + number)
	result.append(CANCEL); return result
func base_price(state: Dictionary, code: int) -> int:
	var table: Dictionary = catalog["base_prices"]; var specials: Dictionary = catalog["special_prices"]; var value := 0
	match code:
		0x478:
			var index := (int(state["max_life"]) - 0x50) >> 4
			if index < 0 or index >= 5: return 0
			value = int(specials["bionic"][index])
		0x479:
			var capacity := int(state["canteen"][1])
			if capacity < 0 or capacity >= 100: return 0
			value = int(specials["extra"][mini(capacity, 14)])
		0x47a:
			var capacity := int(state["bottle"][1])
			if capacity < 0 or capacity >= 100: return 0
			value = int(specials["medicine"][mini(capacity, 14)])
		_: value = int(table.get(str(code), 0))
	return -value * 500 if value < 0 else value
func price(state: Dictionary, code: int, buying: bool) -> int:
	var value := base_price(state, code)
	if buying:
		match int(state["selector"]):
			0: value = value * 4 / 5
			2: value = value * 6 / 5
	return mini(value, MAX_ZENNY)
func sell_price(state: Dictionary, code: int) -> int: return (price(state, code, false) + 3) >> 2
func add_zenny(state: Dictionary, delta: int) -> bool:
	if int(state["zenny"]) < -delta: return false
	state["zenny"] = mini(int(state["zenny"]) + delta, MAX_ZENNY); return true
const DELIVERY := {0x45a: [0x131, 1000], 0x45b: [0x12c, 1000], 0x45c: [0x12d, 1000], 0x45d: [0x12b, 1000], 0x45e: [0x12f, 10000], 0x45f: [0x12e, 1000], 0x460: [0x130, 1000]}
func is_delivery(code: int) -> bool: return DELIVERY.has(code)
func purchase(state: Dictionary, code: int) -> void:
	add_zenny(state, -price(state, code, true))
	if code >= 0x394 and code < 0x478:
		clear_flag(state, code + 0x100); state["owned"][code] = true
		match code:
			0x400: state["canteen"] = [5, 5]
			0x401: state["bottle"] = [3, 3]
		if DELIVERY.has(code):
			state["owned"].erase(code); state["karma"].append(DELIVERY[code][1]); state["events"][DELIVERY[code][0]] = true
		return
	match code:
		0x478:
			if (int(state["max_life"]) - 0x50) >> 4 < 5: state["max_life"] = int(state["max_life"]) + 0x10; state["life"] = state["max_life"]
		0x479:
			if int(state["canteen"][1]) < 99: state["canteen"] = [int(state["canteen"][1]) + 1, int(state["canteen"][1]) + 1]
		0x47a:
			if int(state["bottle"][1]) < 99: state["bottle"] = [int(state["bottle"][1]) + 1, int(state["bottle"][1]) + 1]
	update_special(state, code)
func sell(state: Dictionary, code: int) -> void:
	set_flag(state, code + 0x100); state["owned"].erase(code)
	if code == 0x441: state["karma"].append(-5000); clear_flag(state, code + 0x100)
	elif code >= 0x44d and code < 0x450: clear_flag(state, code + 0x100)
	add_zenny(state, sell_price(state, code))
# List cursor (ST0AT 0x800ECDEC). list = {cursor, scroll, count, rows, move, scrolling} (0xFF cursor = none); input = {cancel, confirm, up, down, page_up, page_down, both_pages};
# the animation counters mirror ctx+8 / ctx+9 and gate input exactly like the original. Returns 0 (nothing), 1 (confirm) or -1 (cancel); "sound" holds the menu sound role.
static func cursor_step(list: Dictionary, input: Dictionary) -> int:
	list["sound"] = ""
	var move := int(list["move"]); var scrolling := int(list["scrolling"])
	if move != 0: list["move"] = move - signi(move); return 0
	if scrolling != 0:
		if absi(scrolling) < 3:
			list["scrolling"] = scrolling - signi(scrolling)
			if int(list["scrolling"]) == 0: list["scroll"] = int(list["scroll"]) + signi(scrolling)
		else:
			list["scrolling"] = scrolling - 3 * signi(scrolling); list["scroll"] = int(list["scroll"]) + signi(scrolling)
		return 0
	if bool(input.get("cancel", false)): list["sound"] = "menu_cancel"; return -1
	var count := int(list["count"]); var rows := int(list["rows"]); var cursor := int(list["cursor"]); var scroll := int(list["scroll"])
	if count == 0: list["cursor"] = 0xff; return 0
	if count < scroll + rows:
		if scroll != 0: scroll -= 1
		elif cursor >= count: cursor = count - 1
	list["cursor"] = cursor; list["scroll"] = scroll
	var new_cursor := cursor; var new_scroll := scroll
	if not bool(input.get("both_pages", false)):
		if bool(input.get("page_down", false)):
			if cursor == rows - 1: new_scroll = scroll + rows - 1
			else: new_cursor = rows - 1
		if bool(input.get("page_up", false)):
			if cursor != 0: new_cursor = 0
			else: new_scroll = scroll - (rows - 1)
	if bool(input.get("up", false)): new_cursor -= 1
	if bool(input.get("down", false)): new_cursor += 1
	if new_scroll < 0: new_cursor = 0; new_scroll = 0
	if new_cursor < 0:
		new_scroll = new_scroll - 1 if new_cursor + new_scroll >= 0 else 0
		new_cursor = 0
	if rows < count:
		if new_cursor + new_scroll >= count: new_cursor = rows - 1; new_scroll = count - rows
		elif new_cursor >= rows: new_scroll += 1; new_cursor = rows - 1
	else:
		new_scroll = 0
		if new_cursor >= count: new_cursor = count - 1
	if new_cursor != cursor:
		list["move"] = new_cursor - cursor; list["cursor"] = new_cursor; list["sound"] = "menu_move"; return 0
	if new_scroll != scroll:
		var delta := new_scroll - scroll; list["scrolling"] = delta * 2 if absi(delta) < 2 else delta * 3; list["sound"] = "menu_move"; return 0
	if bool(input.get("confirm", false)): list["sound"] = "menu_confirm"; return 1
	return 0
