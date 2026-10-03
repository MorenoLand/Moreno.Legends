extends RefCounted
static func modifier(stage: String, context: Dictionary) -> int:
	if stage != "ST41" and stage != "ST42": return 0
	var flags: Dictionary = context.get("event_flags", {})
	if _flag(flags, 0x155): return 12
	return -8 if _flag(flags, 0x153) else 0
static func _flag(flags: Dictionary, id: int) -> bool: return bool(flags.get(id, flags.get(str(id), false)))
