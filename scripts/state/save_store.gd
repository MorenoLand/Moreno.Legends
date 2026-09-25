extends RefCounted
var directory := "user://saves"
var error := ""
func entries() -> Array:
	error = ""
	var result: Array = []
	var folder := DirAccess.open(directory)
	if folder == null:
		if DirAccess.dir_exists_absolute(directory): error = "Saved games could not be read."
		return result
	for filename in folder.get_files():
		if not filename.ends_with(".json") or not filename.get_basename().is_valid_int(): continue
		var id := filename.get_basename()
		var data := read(id)
		if data.is_empty():
			result.append({"id": id, "name": "Unreadable save", "saved_at": 0, "stage": "", "area": -1, "health": 0, "max_health": 0, "error": error})
			continue
		var state: Dictionary = data["state"]
		result.append({"id": id, "name": str(data["name"]), "saved_at": int(data["saved_at"]), "stage": str(state["stage"]), "area": int(state["area"]), "health": int(state["player"]["health"]), "max_health": int(state["player"]["max_health"])})
	result.sort_custom(func(a: Dictionary, b: Dictionary): return int(a["saved_at"]) > int(b["saved_at"]) if a["saved_at"] != b["saved_at"] else int(a["id"]) > int(b["id"]))
	error = ""
	return result
func read(id: String) -> Dictionary:
	error = ""
	if not id.is_valid_int():
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
	if not id.is_empty() and (not id.is_valid_int() or not FileAccess.file_exists(directory.path_join(id + ".json"))):
		error = "The selected save no longer exists."
		return ""
	var code := DirAccess.make_dir_recursive_absolute(directory)
	if code != OK:
		error = "The save folder could not be created."
		return ""
	var timestamp := Time.get_unix_time_from_system()
	if id.is_empty():
		var number := int(timestamp * 1000000.0)
		while FileAccess.file_exists(directory.path_join(str(number) + ".json")) or FileAccess.file_exists(directory.path_join(str(number) + ".json.tmp")): number += 1
		id = str(number)
	var temporary := id + ".json.tmp"
	var file := FileAccess.open(directory.path_join(temporary), FileAccess.WRITE)
	if file == null:
		error = "The save file could not be created."
		return ""
	file.store_string(JSON.stringify({"version": 1, "name": "Area %02d" % int(state["area"]), "saved_at": int(timestamp), "state": state}, "\t", true, true))
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
	var player: Variant = value.get("player")
	if not player is Dictionary or not _vector(player.get("position")) or not _vector(player.get("camera_rotation")) or not _number(player.get("yaw")): return false
	if not _integer(player.get("health")) or not _integer(player.get("max_health")) or int(player["max_health"]) <= 0 or int(player["health"]) < 0 or int(player["health"]) > int(player["max_health"]): return false
	if player.has("zenny") and (not _integer(player["zenny"]) or int(player["zenny"]) < 0 or int(player["zenny"]) > 9999999): return false
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
