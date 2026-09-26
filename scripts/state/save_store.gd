extends RefCounted
var directory := "user://saves"
const SLOT_COUNT := 5
var error := ""
func entries() -> Array:
	error = ""
	var result: Array = []
	var folder := DirAccess.open(directory)
	if folder == null:
		if DirAccess.dir_exists_absolute(directory): error = "Saved games could not be read."
		else:
			for slot in range(1, SLOT_COUNT + 1): result.append({"id": str(slot), "slot": slot, "empty": true, "name": "No save data", "play_time_seconds": 0.0})
		return result
	for slot in range(1, SLOT_COUNT + 1):
		var id := str(slot)
		if not folder.file_exists(id + ".json"):
			result.append({"id": id, "slot": slot, "empty": true, "name": "No save data", "play_time_seconds": 0.0})
			continue
		var data := read(id)
		if data.is_empty():
			result.append({"id": id, "slot": slot, "empty": false, "name": "Unreadable save", "play_time_seconds": 0.0, "saved_at": 0, "stage": "", "area": -1, "health": 0, "max_health": 0, "error": error})
			continue
		var state: Dictionary = data["state"]
		result.append({"id": id, "slot": slot, "empty": false, "name": str(data["name"]), "play_time_seconds": float(state.get("play_time_seconds", 0.0)), "saved_at": int(data["saved_at"]), "stage": str(state["stage"]), "area": int(state["area"]), "health": int(state["player"]["health"]), "max_health": int(state["player"]["max_health"])})
	error = ""
	return result
func read(id: String) -> Dictionary:
	error = ""
	if not id.is_valid_int() or int(id) < 1 or int(id) > SLOT_COUNT or id != str(int(id)):
		error = "Invalid save selection."
		return {}
	var file := FileAccess.open(directory.path_join(id + ".json"), FileAccess.READ)
	if file == null:
		error = "This save could not be opened."
		return {}
	var json := JSON.new()
	var code := json.parse(file.get_as_text())
	file.close()
	var data: Variant = json.data
	if code != OK or not data is Dictionary or data.get("version") != 1 or not data.get("name") is String or not _integer(data.get("saved_at")) or int(data["saved_at"]) <= 0 or not valid_state(data.get("state")):
		error = "This save is incomplete or unsupported."
		return {}
	return data
func write(state: Dictionary, id: String = "") -> String:
	error = ""
	if not valid_state(state):
		error = "The current game cannot be saved."
		return ""
	if OS.has_feature("web") and not OS.is_userfs_persistent():
		error = "Browser storage is unavailable for saved games."
		return ""
	if not id.is_empty() and (not id.is_valid_int() or int(id) < 1 or int(id) > SLOT_COUNT or id != str(int(id))):
		error = "Invalid save slot."
		return ""
	var code := DirAccess.make_dir_recursive_absolute(directory)
	if code != OK:
		error = "The save folder could not be created."
		return ""
	var timestamp := Time.get_unix_time_from_system()
	if id.is_empty():
		for slot in range(1, SLOT_COUNT + 1):
			if not FileAccess.file_exists(directory.path_join(str(slot) + ".json")): id = str(slot); break
		if id.is_empty(): error = "All five save slots are occupied."; return ""
	var temporary := id + ".json.tmp"
	var file := FileAccess.open(directory.path_join(temporary), FileAccess.WRITE)
	if file == null:
		error = "The save file could not be created."
		return ""
	file.store_string(JSON.stringify({"version": 1, "name": str(state.get("location_name", state["stage"])), "saved_at": int(timestamp), "state": state}, "\t", true, true))
	file.flush()
	code = file.get_error()
	file.close()
	var folder := DirAccess.open(directory)
	var backup := ""
	if code == OK and folder != null and folder.file_exists(id + ".json"):
		backup = id + ".json.previous"
		while folder.file_exists(backup): backup += ".previous"
		code = folder.rename(id + ".json", backup)
	if code == OK and folder != null: code = folder.rename(temporary, id + ".json")
	elif folder == null: code = ERR_CANT_OPEN
	if code != OK:
		var restored := true
		if folder != null and not backup.is_empty() and folder.file_exists(backup) and not folder.file_exists(id + ".json"): restored = folder.rename(backup, id + ".json") == OK
		if folder != null: folder.remove(temporary)
		error = "The save could not be written." if restored else "The save could not be written; the previous save remains in " + backup + "."
		return ""
	if not backup.is_empty(): folder.remove(backup)
	return id
func valid_state(value: Variant) -> bool:
	if not value is Dictionary or not value.get("stage") is String or not _integer(value.get("area")) or int(value["area"]) < 0: return false
	var stage: String = value["stage"]
	if stage.length() != 4 or not stage.begins_with("ST") or not stage.substr(2).is_valid_hex_number(): return false
	if value.has("location_name") and (not value["location_name"] is String or value["location_name"].is_empty()): return false
	var player: Variant = value.get("player")
	if not player is Dictionary or not _vector(player.get("position")) or not _vector(player.get("camera_rotation")) or not _number(player.get("yaw")): return false
	if not _integer(player.get("health")) or not _integer(player.get("max_health")) or int(player["max_health"]) <= 0 or int(player["health"]) < 0 or int(player["health"]) > int(player["max_health"]): return false
	if player.has("zenny") and (not _integer(player["zenny"]) or int(player["zenny"]) < 0 or int(player["zenny"]) > 9999999): return false
	if value.has("play_time_seconds") and (not _number(value["play_time_seconds"]) or float(value["play_time_seconds"]) < 0): return false
	if player.has("inventory"):
		if not player["inventory"] is Dictionary: return false
		for category in ["items", "key_items", "special_weapons", "body_parts", "buster_parts"]:
			if not player["inventory"].get(category) is Dictionary: return false
			for item in player["inventory"][category]:
				if not item is String or item.is_empty() or not _integer(player["inventory"][category][item]) or int(player["inventory"][category][item]) <= 0: return false
	if player.has("equipment"):
		if not player["equipment"] is Dictionary: return false
		for category in ["body_parts", "buster_parts"]:
			var slots: Variant = player["equipment"].get(category)
			if not slots is Array or slots.size() != (3 if category == "body_parts" else 2): return false
			for item in slots:
				if not item is String or not item.is_empty() and (not player.has("inventory") or not player["inventory"][category].has(item)): return false
	if player.has("equipped_special") and (not _integer(player["equipped_special"]) or int(player["equipped_special"]) < 0 or not player.get("inventory", {}).get("special_weapons", {}).has(str(int(player["equipped_special"])))): return false
	if value.has("native_context"):
		var context: Variant = value["native_context"]
		if not context is Dictionary or not _integer(context.get("native_save_byte14")) or int(context["native_save_byte14"]) < 0 or int(context["native_save_byte14"]) > 255 or not context.get("event_flags") is Dictionary: return false
		for flag in context["event_flags"]:
			if not str(flag).is_valid_int() or int(flag) < 0 or int(flag) > 65535 or not context["event_flags"][flag] is bool: return false
	if value.has("parked_location"):
		var parked: Variant = value["parked_location"]
		if not parked is Dictionary: return false
		if not parked.is_empty():
			if not parked.get("stage") is String or not _integer(parked.get("area")) or int(parked["area"]) < 0: return false
			var parked_stage: String = parked["stage"]
			if parked_stage.length() != 4 or not parked_stage.begins_with("ST") or not parked_stage.substr(2).is_valid_hex_number(): return false
	if not value.get("defeated_actors") is Array or not value.get("minimap") is Array: return false
	for id: Variant in value["defeated_actors"]:
		if not _integer(id) or int(id) < 0: return false
	for cell: Variant in value["minimap"]:
		if not cell is Array or cell.size() != 3: return false
		for part: Variant in cell:
			if not _integer(part): return false
	for field in ["stage_events", "explored_stages"]:
		if not value.has(field): continue
		if not value[field] is Dictionary: return false
		for stage_id in value[field]:
			if not stage_id is String or stage_id.length() != 4 or not stage_id.begins_with("ST") or not stage_id.substr(2).is_valid_hex_number() or not value[field][stage_id] is Array: return false
			for entry in value[field][stage_id]:
				if field == "stage_events":
					if not _integer(entry) or int(entry) < 0: return false
				else:
					if not entry is Array or entry.size() != 3: return false
					for part in entry:
						if not _integer(part): return false
	return true
func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))
func _integer(value: Variant) -> bool:
	return _number(value) and float(value) == floorf(float(value))
func _vector(value: Variant) -> bool:
	return value is Array and value.size() == 3 and _number(value[0]) and _number(value[1]) and _number(value[2]) and Vector3(float(value[0]), float(value[1]), float(value[2])).is_finite()
