extends RefCounted
static var regions: Array = []
static func enter_stage(context: Dictionary, stage: String) -> void:
	if regions.is_empty():
		var data: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/stage_regions.json")) if FileAccess.file_exists("res://assets/locations/stage_regions.json") else null
		if not data is Dictionary: return
		regions = data["regions"]
	var id := stage.substr(2).hex_to_int()
	if id < regions.size() and int(regions[id]) != 0xFF: context["native_save_byte12"] = int(regions[id])
	var region := int(context.get("native_save_byte12", 0))
	if region == int(context.get("native_save_byte84", 0)) or id < 8: return
	context["native_save_byte84"] = region
	for offset in range(8):
		var key := "native_save_byte%x" % (0x7C + offset); var value := int(context.get(key, 0))
		if value != 0 and value < 0xFF: context[key] = value + 1
