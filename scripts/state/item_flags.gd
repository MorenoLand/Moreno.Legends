extends RefCounted
# Original item ownership is event-flag bit == item code (GAME 0x800C0558/0x800C05B4, bitmap 0x80092538); dialogue 0x26/0x27 give and consume items through those bits.
const FIRST := 0x383
const LAST := 0x451
const NOTHING := [0x394, 0x3b8, 0x3bc, 0x3c8]
static var names: Dictionary = {}
static func group_of(code: int) -> String: return "special_weapons" if code < 0x394 else "buster_parts" if code < 0x3b8 else "body_parts" if code < 0x3d0 else "key_items" if code < 0x400 else "items"
static func key_of(code: int) -> String: return str(code - 0x380) if code < 0x394 else str(code)
static func sync(player: Node, context: Dictionary) -> void:
	if names.is_empty():
		var source: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/items.json")) if FileAccess.file_exists("res://assets/shops/items.json") else null
		if not source is Dictionary: return
		for code_text: String in source["names"]:
			var code := int(code_text)
			if code >= FIRST and code <= LAST and not code in NOTHING and not str(source["names"][code_text]).is_empty(): names[code] = true
	var flags: Dictionary = context.get("event_flags", {}); var last := {}; var now: Array = []
	for code: Variant in context.get("native_item_flags", []): last[int(code)] = true
	for code: int in names:
		var group: Dictionary = player.inventory[group_of(code)]; var key := key_of(code); var flagged := bool(flags.get(code, flags.get(str(code), false))); var owned := group.has(key)
		var final: bool = flagged if flagged == owned else not last.has(code)
		if final:
			group[key] = int(group.get(key, 1)); flags[code] = true; flags.erase(str(code)); now.append(code)
		else:
			group.erase(key); flags.erase(code); flags.erase(str(code))
	context["event_flags"] = flags; context["native_item_flags"] = now
