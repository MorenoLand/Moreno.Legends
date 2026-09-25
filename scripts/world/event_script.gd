extends Node
signal source_call_started(stage: String, address: String, message_index: int)
signal source_call_finished(stage: String, address: String, message_index: int)
var dialogue: Control
var banks: Dictionary = {}
var entries: Dictionary = {}
func configure(dialogue_node: Control, manifest_path := "res://assets/dialogue/manifest.json") -> bool:
	dialogue = dialogue_node
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) if FileAccess.file_exists(manifest_path) else null
	if not data is Dictionary or not data.has("banks"): push_error("Missing extracted native dialogue catalog: " + manifest_path); return false
	banks = data["banks"]
	for stage in banks:
		entries[stage] = {}
		for entry: Dictionary in banks[stage].get("messages", []): entries[stage][int(entry["index"])] = entry
	return true
func play_message(stage: String, index: int, source_address := "") -> bool:
	if dialogue == null or not entries.has(stage) or not entries[stage].has(index): push_error("No source dialogue entry for %s:%02X" % [stage, index]); return false
	var entry: Dictionary = entries[stage][index]
	if source_address != "": source_call_started.emit(stage, source_address, index)
	await dialogue.present_message(stage, entry)
	if source_address != "": source_call_finished.emit(stage, source_address, index)
	return true
func play_native_call(stage: String, address: String, runtime_index := -1) -> bool:
	if not banks.has(stage): push_error("No source dialogue bank for " + stage); return false
	var matches: Array[Dictionary] = []
	for call: Dictionary in banks[stage].get("message_calls", []):
		if str(call.get("address", "")) != address: continue
		if call.has("index") and runtime_index >= 0 and int(call["index"]) != runtime_index: continue
		matches.append(call)
	if matches.size() != 1: push_error("Native dialogue call %s requires a unique source state/index" % address); return false
	var index := int(matches[0].get("index", runtime_index))
	if index < 0: push_error("Native dialogue call %s requires its source runtime index" % address); return false
	return await play_message(stage, index, address)
