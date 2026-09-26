extends Node
signal source_call_started(stage: String, address: String, message_index: int)
signal source_call_finished(stage: String, address: String, message_index: int)
signal native_command_requested(stage: String, message_index: int, opcode: int, arguments: Array, source_command: Dictionary, source_actor: Node3D)
signal native_context_changed(stage: String, context: Dictionary)
var dialogue: Control
var banks: Dictionary = {}
var entries: Dictionary = {}
var native_context: Dictionary = {}
var active_program_stage := ""
var active_program_index := -1
var active_source_actor: Node3D
var active_page_commands: Array = []
var active_tail_commands: Array[Dictionary] = []
var active_window_state: Dictionary = {}
var preflight_results: Dictionary = {}
var preflight_context_hash := 0
func configure(dialogue_node: Control, manifest_path := "res://assets/dialogue/manifest.json", context: Dictionary = {}) -> bool:
	dialogue = dialogue_node; native_context = context
	preflight_results.clear()
	var page_callable := Callable(self, "_on_native_page_started")
	if dialogue.has_signal("native_page_started") and not dialogue.is_connected("native_page_started", page_callable): dialogue.connect("native_page_started", page_callable)
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) if FileAccess.file_exists(manifest_path) else null
	if not data is Dictionary or not data.has("banks"): push_error("Missing extracted native dialogue catalog: " + manifest_path); return false
	if dialogue.has_method("configure_native_presentation"): dialogue.configure_native_presentation(data.get("presentation", {}))
	banks = data["banks"]
	for stage in banks:
		entries[stage] = {}
		for entry: Dictionary in banks[stage].get("messages", []): entries[stage][int(entry["index"])] = entry
	return true
func update_native_context(context: Dictionary) -> void: native_context = context
func play_message(stage: String, index: int, source_address := "", source_actor: Node3D = null) -> bool:
	if dialogue == null or not entries.has(stage) or not entries[stage].has(index): push_error("No source dialogue entry for %s:%02X" % [stage, index]); return false
	return await _present_entry(stage, index, source_address, source_actor)
func can_play_native_call(stage: String, address: String, runtime_index := -1) -> bool:
	if dialogue == null or bool(dialogue.get("active")): return false
	var entry := _native_call_entry(stage, address, runtime_index); return not entry.is_empty() and _can_display_program(stage, int(entry["index"]))
func play_native_call(stage: String, address: String, runtime_index := -1, source_actor: Node3D = null) -> bool:
	var entry := _native_call_entry(stage, address, runtime_index)
	if entry.is_empty(): push_error("Native dialogue call %s:%s has no unique resolved text entry" % [stage, address]); return false
	return await _present_entry(stage, int(entry["index"]), address, source_actor)
func can_play_bound_message(stage: String, bank: String, runtime_index: int) -> bool:
	if dialogue == null or bool(dialogue.get("active")) or not _bound_bank_matches(stage, bank) or not entries.has(stage) or not entries[stage].has(runtime_index): return false
	return _can_display_program(stage, runtime_index)
func _can_display_program(stage: String, index: int) -> bool:
	var context_hash := native_context.hash()
	if context_hash != preflight_context_hash: preflight_results.clear(); preflight_context_hash = context_hash
	var key := "%s:%d" % [stage, index]
	if not preflight_results.has(key): preflight_results[key] = _resolved_displayable(_resolve_program(stage, index))
	return bool(preflight_results[key])
func play_bound_message(stage: String, bank: String, runtime_index: int, source_address: String, source_actor: Node3D = null) -> bool:
	if not can_play_bound_message(stage, bank, runtime_index): push_error("Native message %s:%02X has no resolved page in bank %s" % [stage, runtime_index, bank]); return false
	return await _present_entry(stage, runtime_index, source_address, source_actor)
func _native_call_entry(stage: String, address: String, runtime_index: int) -> Dictionary:
	if not banks.has(stage) or not entries.has(stage): return {}
	var matches: Array[Dictionary] = []
	for call: Dictionary in banks[stage].get("message_calls", []):
		if str(call.get("address", "")) != address: continue
		if call.has("index") and runtime_index >= 0 and int(call["index"]) != runtime_index: continue
		matches.append(call)
	if matches.size() != 1: return {}
	var index := int(matches[0].get("index", runtime_index))
	if index < 0 or not entries[stage].has(index): return {}
	return entries[stage][index]
func _bound_bank_matches(stage: String, bank: String) -> bool:
	if not banks.has(stage): return false
	var runtime_bank := str(banks[stage].get("source", {}).get("runtime_message_base", "")); return _normalize_bank(runtime_bank) == _normalize_bank(bank)
func _normalize_bank(value: String) -> String:
	var normalized := value.strip_edges().to_lower()
	return "0x%08x" % normalized.substr(2).hex_to_int() if normalized.begins_with("0x") else normalized
func _present_entry(stage: String, index: int, source_address: String, source_actor: Node3D = null) -> bool:
	if dialogue == null or not entries.has(stage) or not entries[stage].has(index) or bool(dialogue.get("active")): return false
	if source_address != "": source_call_started.emit(stage, source_address, index)
	active_program_stage = stage; active_program_index = index; active_source_actor = source_actor; active_window_state = {"flags": 0x00010083, "byte23": 2, "choice_index": 0, "text_speed": 2, "origin_x": 32, "origin_y": 176, "window_width": 144, "window_lines": 3}; var program_index := index; var program_offset := -1; var continuation := false; var choice_cancelled := false
	for _step in range(128):
		var resolved := _resolve_program(stage, program_index, active_window_state, program_offset)
		if not bool(resolved.get("supported", false)):
			if continuation and dialogue.has_method("finish_native_message"): dialogue.finish_native_message()
			push_error("Native message %s:%02X has an unresolved native command path" % [stage, index]); active_program_stage = ""; active_program_index = -1; active_source_actor = null; active_page_commands.clear(); active_tail_commands.clear(); active_window_state.clear(); return false
		var pages: Array = resolved.get("pages", []); var has_text := false
		for page: String in pages:
			if not page.strip_edges().is_empty(): has_text = true; break
		if not has_text and not bool(resolved.get("needs_choice", false)) and resolved.get("tail_commands", []).is_empty():
			push_error("Native message %s:%02X resolves to no displayable text" % [stage, index]); active_program_stage = ""; active_program_index = -1; active_source_actor = null; active_page_commands.clear(); active_tail_commands.clear(); active_window_state.clear(); return false
		active_program_index = int(resolved.get("program_index", program_index)); active_page_commands = resolved.get("page_commands", []); active_tail_commands = resolved.get("tail_commands", [])
		var entry: Dictionary = {"index": active_program_index, "text": "\n".join(pages), "native_pages": pages, "native_page_speeds": resolved.get("page_speeds", []), "native_page_wait_updates": resolved.get("page_wait_updates", []), "native_page_choices": resolved.get("page_choices", []), "native_page_commands": active_page_commands, "native_tail_commands": active_tail_commands, "continue_window": bool(resolved.get("needs_choice", false))}
		var result: Dictionary = await dialogue.present_message(stage, entry)
		if not bool(resolved.get("needs_choice", false)): break
		var selected := int(result.get("choice_index", -1))
		if selected < 0: if dialogue.has_method("finish_native_message"): dialogue.finish_native_message(); choice_cancelled = true; break
		active_window_state["choice_index"] = selected; active_window_state["flags"] = (int(active_window_state.get("flags", 0)) & ~0xF00) | ((selected & 0xF) << 8); program_index = int(resolved["resume_index"]); program_offset = int(resolved["resume_offset"]); continuation = true
	active_program_stage = ""; active_program_index = -1; active_source_actor = null; active_page_commands.clear(); active_tail_commands.clear(); active_window_state.clear()
	if source_address != "": source_call_finished.emit(stage, source_address, index)
	return not choice_cancelled
func _on_native_page_started(stage: String, index: int, page_index: int) -> void:
	if stage != active_program_stage or index != active_program_index or page_index < 0: return
	if page_index == active_page_commands.size():
		for command: Dictionary in active_tail_commands: native_command_requested.emit(stage, index, int(command["opcode"]), command.get("arguments", []), command.get("source_command", {}), active_source_actor)
		return
	if page_index >= active_page_commands.size(): return
	var flags_changed := false
	for command: Dictionary in active_page_commands[page_index]:
		var opcode := int(command["opcode"]); var arguments: Array = command.get("arguments", [])
		if opcode in [0x26, 0x27] and arguments.size() == 2 and native_context.get("event_flags", null) is Dictionary:
			var flag_id := (int(arguments[0]) << 8) | int(arguments[1]); var flags: Dictionary = native_context["event_flags"]; var flag_key: Variant = flag_id if flags.has(flag_id) or not flags.has(str(flag_id)) else str(flag_id); flags[flag_key] = opcode == 0x26; native_context["event_flags"] = flags; flags_changed = true
		if command.get("native_context_mutation", null) is Dictionary:
			for key in command["native_context_mutation"]: native_context[key] = command["native_context_mutation"][key]
			flags_changed = true
		native_command_requested.emit(stage, index, opcode, arguments, command.get("source_command", {}), active_source_actor)
	if flags_changed: native_context_changed.emit(stage, native_context)
func _resolved_displayable(resolved: Dictionary) -> bool:
	if not bool(resolved.get("supported", false)): return false
	for page: String in resolved.get("pages", []):
		if not page.strip_edges().is_empty(): return true
	return false
func _resolve_program(stage: String, initial_index: int, window_state: Dictionary = {}, initial_offset := -1) -> Dictionary:
	if window_state.is_empty(): window_state = {"flags": 0x00010083, "byte23": 2, "choice_index": 0, "text_speed": 2, "origin_x": 32, "origin_y": 176, "window_width": 144, "window_lines": 3}
	if not entries.has(stage): return {"supported": false}
	var pages: Array[String] = []; var page_speeds: Array[Array] = []; var page_wait_updates: Array[int] = []; var page_choices: Array[Dictionary] = []; var page_commands: Array = []; var current_page_commands: Array[Dictionary] = []; var tail_commands: Array[Dictionary] = []; var visited := {}; var simulated_context: Dictionary = native_context.duplicate(true); var message_index := initial_index; var start_offset := initial_offset; var page_text := ""; var page_speed := int(window_state.get("text_speed", 2)); var page_speed_counts: Array[int] = []; var choice_text_offsets := {}
	for _step in range(128):
		if visited.has(message_index) or not entries[stage].has(message_index): return {"supported": false}
		visited[message_index] = true; var entry: Dictionary = entries[stage][message_index]; var trace: Dictionary = entry.get("program_trace", {}); var runs: Array = entry.get("text_runs", trace.get("text_runs", entry.get("text_blocks", trace.get("display_text_runs", [])))); var commands: Array = entry.get("native_commands", trace.get("commands", [])); var events: Array[Dictionary] = []; var order := 0
		for raw_command: Dictionary in commands:
			if _native_opcode(raw_command) != 0x39: continue
			for row: Dictionary in raw_command.get("choice_rows", []):
				for source_run: Dictionary in row.get("text_runs", []): choice_text_offsets[_integer(source_run.get("file_offset", -1), -1)] = true
		if commands.is_empty() and (bool(trace.get("partial_display", false)) or str(entry.get("display_resolution", {}).get("status", "")).contains("partial_native_page")): return {"supported": false}
		for run: Dictionary in runs:
			events.append({"kind": "text", "offset": _integer(run.get("file_offset", run.get("relative_offset", order)), order), "order": order, "text": str(run.get("text", ""))}); order += 1
		for command: Dictionary in commands:
			events.append({"kind": "command", "offset": _integer(command.get("file_offset", command.get("relative_offset", order)), order), "order": order, "command": command}); order += 1
		if commands.is_empty() and runs.is_empty():
			if not _has_displayable_text(entry): return {"supported": false}
			var fallback_text := str(entry.get("text", "")); page_text += fallback_text; _append_speed(page_speed_counts, fallback_text, page_speed); pages.append(page_text); page_speeds.append(page_speed_counts.duplicate()); page_wait_updates.append(0); page_choices.append({}); page_commands.append(current_page_commands); return {"supported": true, "program_index": message_index, "pages": pages, "page_speeds": page_speeds, "page_wait_updates": page_wait_updates, "page_choices": page_choices, "page_commands": page_commands, "tail_commands": tail_commands}
		events.sort_custom(func(a: Dictionary, b: Dictionary): return int(a["offset"]) < int(b["offset"]) if int(a["offset"]) != int(b["offset"]) else int(a["order"]) < int(b["order"]))
		var redirected := false
		for event: Dictionary in events:
			if start_offset >= 0 and int(event["offset"]) < start_offset: continue
			if str(event["kind"]) == "text":
				if choice_text_offsets.has(int(event["offset"])): continue
				var value := str(event["text"])
				if value.contains("⟦"): return {"supported": false}
				page_text += value; _append_speed(page_speed_counts, value, page_speed); continue
			var command: Dictionary = event["command"]; var opcode := _native_opcode(command); var arguments := _native_arguments(command); var target := -1; var command_length := _integer(command.get("native_length", 0), 0)
			match opcode:
				0x2B:
					if not arguments.is_empty() or dialogue == null or bool(dialogue.get("active")): return {"supported": false}
				0x18, 0x24:
					current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
					pages.append(page_text); page_speeds.append(page_speed_counts.duplicate()); page_wait_updates.append(0); page_choices.append({}); page_commands.append(current_page_commands); current_page_commands = []; page_text = ""; page_speed_counts.clear()
				0x09:
					if arguments.size() != 1: return {"supported": false}
					page_speed = arguments[0]; window_state["text_speed"] = page_speed
					var local_flags := int(window_state.get("flags", 0)); window_state["flags"] = local_flags | 0x40000 if page_speed == 0 else local_flags & ~0x40000
					window_state["byte7"] = 0 if page_speed == 0 else page_speed - 1; window_state["halfword4"] = 0 if page_speed == 0 else page_speed - 1
					current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
				0x0F:
					if arguments.size() != 1: return {"supported": false}
					window_state["choice_marker"] = arguments[0] & 0xF
				0x16:
					if arguments.size() < 4 or not simulated_context.has("native_save_byte14"): return {"supported": false}
					var value := int(simulated_context["native_save_byte14"]); target = int(command.get("selected_index", arguments[1] if value > arguments[0] else arguments[2] if value == arguments[0] else arguments[3]))
				0x11:
					var target_count := int(arguments[0]) if not arguments.is_empty() else -1; var selected := int(window_state.get("choice_index", -1))
					if target_count < 0 or arguments.size() < target_count + 1 or selected < 0 or selected >= target_count: return {"supported": false}
					target = int(arguments[selected + 1])
				0x28:
					if arguments.size() < 4 or not simulated_context.has("event_flags") or not simulated_context["event_flags"] is Dictionary: return {"supported": false}
					var flag_id := (int(arguments[0]) << 8) | int(arguments[1]); var flags: Dictionary = simulated_context["event_flags"]; var flag_set := bool(flags.get(flag_id, flags.get(str(flag_id), false))); target = int(command.get("selected_index", arguments[2] if flag_set else arguments[3]))
				0x0E:
					target = int(command.get("target_index", command.get("message_index", arguments[-1] if not arguments.is_empty() else -1)))
				0x21:
					if arguments.size() != 1: return {"supported": false}
					var dynamic: Dictionary = command.get("dynamic_text", {}); var value_key := str(dynamic.get("value_key", "zenny" if arguments[0] & 0x80 else "")); if value_key.is_empty() or not simulated_context.has("native_wallet") and value_key == "zenny": return {"supported": false}
					if value_key != "zenny" or not simulated_context.has("native_wallet"): return {"supported": false}
					var inserted := _format_native_number(int(simulated_context["native_wallet"]), arguments[0], dynamic); page_text += inserted; _append_speed(page_speed_counts, inserted, page_speed)
				0x2A:
					if arguments.size() != 5 or not simulated_context.has("native_save_byte16"): return {"supported": false}
					var selector := int(simulated_context["native_save_byte16"]); if selector < 0 or selector >= arguments.size(): return {"supported": false}; target = arguments[selector]
				0x30:
					if arguments.size() != 1: return {"supported": false}
					window_state["byte23"] = arguments[0]; current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
				0x06:
					if arguments.size() != 6: return {"supported": false}
					window_state["origin_x"] = (int(arguments[0]) << 8) | int(arguments[1]); window_state["origin_y"] = (int(arguments[2]) << 8) | int(arguments[3]); window_state["window_width"] = arguments[4]; window_state["window_lines"] = arguments[5]; current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
				0x39:
					if arguments.is_empty(): return {"supported": false}
					var count := arguments[0]; if arguments.size() != 1 + count * 2: return {"supported": false}
					var choice_rows: Array = command.get("choice_rows", []); if choice_rows.size() != count: return {"supported": false}
					var coordinates: Array = []; for row_index in range(count): coordinates.append([arguments[1 + row_index * 2], arguments[2 + row_index * 2]])
					for row_index in range(count): choice_rows[row_index]["native_coordinates"] = coordinates[row_index]
					current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
					pages.append(page_text); page_speeds.append(page_speed_counts.duplicate()); page_wait_updates.append(0); page_choices.append({"rows": choice_rows, "native_coordinates": coordinates, "selected_index": int(window_state.get("choice_index", -1)), "window_flags": int(window_state.get("flags", 0)), "window_origin": [int(window_state.get("origin_x", 32)), int(window_state.get("origin_y", 176))], "window_width": int(window_state.get("window_width", 144)), "window_lines": int(window_state.get("window_lines", 3))}); page_commands.append(current_page_commands); current_page_commands = []; page_text = ""; page_speed_counts.clear(); start_offset = -1
					return {"supported": true, "program_index": message_index, "pages": pages, "page_speeds": page_speeds, "page_wait_updates": page_wait_updates, "page_choices": page_choices, "page_commands": page_commands, "tail_commands": tail_commands, "needs_choice": true, "resume_index": message_index, "resume_offset": int(event["offset"]) + command_length}
				0x3E:
					if arguments.size() != 2 or not simulated_context.has("native_save_word40") or not simulated_context.has("native_save_byte44"): return {"supported": false}
					var delta := _signed_be16(arguments[0], arguments[1]); var value := clampi(int(simulated_context["native_save_word40"]) + delta, -32767, 32767); var state := int(simulated_context["native_save_byte44"]); if state == 0 and value < 0x3000 or state == 2 and value >= -0x2fff: state = 1
					if value > 0x4000: state = 0
					elif value < -0x4000: state = 2
					simulated_context["native_save_word40"] = value; simulated_context["native_save_byte44"] = state; current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true), "native_context_mutation": {"native_save_word40": value, "native_save_byte44": state}})
				0x3F:
					if arguments.size() != 3 or not simulated_context.has("native_save_byte44"): return {"supported": false}
					var state := int(simulated_context["native_save_byte44"]); target = int(arguments[state]) if state >= 0 and state < 3 else 0xFF
				0xFD:
					if arguments.size() != 4: return {"supported": false}
					var wait := (int(arguments[0]) << 8) | int(arguments[1]); pages.append(page_text); page_speeds.append(page_speed_counts.duplicate()); page_wait_updates.append(wait + 1); page_choices.append({}); page_commands.append(current_page_commands); current_page_commands = []; page_text = ""; page_speed_counts.clear()
				0x05, 0x06, 0x2C, 0x15, 0x26, 0x27, 0x33:
					if opcode == 0x05 and arguments.size() != 2 or opcode == 0x06 and arguments.size() != 6 or opcode == 0x2C and arguments.size() != 1 or opcode == 0x15 and arguments.size() != 11 or opcode in [0x26, 0x27] and arguments.size() != 2 or opcode == 0x33 and arguments.size() != 1: return {"supported": false}
					if opcode in [0x26, 0x27]:
						if not simulated_context.has("event_flags") or not simulated_context["event_flags"] is Dictionary: return {"supported": false}
						var event_id := (int(arguments[0]) << 8) | int(arguments[1]); var simulated_flags: Dictionary = simulated_context["event_flags"]; var event_key: Variant = event_id if simulated_flags.has(event_id) or not simulated_flags.has(str(event_id)) else str(event_id); simulated_flags[event_key] = opcode == 0x26; simulated_context["event_flags"] = simulated_flags
					current_page_commands.append({"opcode": opcode, "arguments": arguments, "source_command": command.duplicate(true)})
				0x31:
					pass
				_:
					return {"supported": false}
			if opcode in [0x0E, 0x11, 0x16, 0x28, 0x2A, 0x3F] and target < 0: return {"supported": false}
			if opcode in [0x11, 0x16, 0x28, 0x2A, 0x3F] and target == 0xFF: continue
			if opcode in [0x0E, 0x11, 0x16, 0x28, 0x2A, 0x3F] and target >= 0:
				message_index = target; start_offset = -1; redirected = true; break
		if redirected: continue
		if not page_text.strip_edges().is_empty(): pages.append(page_text); page_speeds.append(page_speed_counts.duplicate()); page_wait_updates.append(0); page_choices.append({}); page_commands.append(current_page_commands)
		elif not current_page_commands.is_empty(): tail_commands = current_page_commands
		return {"supported": true, "program_index": message_index, "pages": pages, "page_speeds": page_speeds, "page_wait_updates": page_wait_updates, "page_choices": page_choices, "page_commands": page_commands, "tail_commands": tail_commands}
	return {"supported": false}
func _append_speed(speeds: Array[int], value: String, speed: int) -> void:
	for _character in value: speeds.append(maxi(speed, 0))
func _format_native_number(value: int, descriptor: int, metadata: Dictionary) -> String:
	if value < 0: return str(metadata.get("negative_character", "-"))
	var digits := str(value); var fixed_width := bool(metadata.get("fixed_width", (descriptor & 0x7F) == 0)); var count := int(metadata.get("digit_count", 7))
	return str(metadata.get("padding_character", "\uE050")).repeat(maxi(count - digits.length(), 0)) + digits if fixed_width else digits
func _signed_be16(high: int, low: int) -> int:
	var value := ((high & 0xFF) << 8) | (low & 0xFF); return value - 0x10000 if value & 0x8000 else value
func _integer(value: Variant, fallback := 0) -> int:
	if typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT: return int(value)
	var text := str(value); return text.hex_to_int() if text.begins_with("0x") and text.substr(2).is_valid_hex_number(false) else int(text) if text.is_valid_int() else fallback
func _native_opcode(command: Dictionary) -> int:
	var value: Variant = command.get("opcode", command.get("opcode_value", -1)); if typeof(value) == TYPE_INT: return int(value)
	var text := str(value).to_lower(); text = text.substr(2) if text.begins_with("0x") or text.begins_with("fb") else text; return text.hex_to_int() if text.is_valid_hex_number(false) else int(text)
func _native_arguments(command: Dictionary) -> Array[int]:
	var value: Variant = command.get("arguments", command.get("args", null)); var result: Array[int] = []
	if value is Array:
		for item in value: result.append(int(item))
		return result
	var raw := str(command.get("raw_arguments_hex", command.get("arguments_hex", "")))
	if raw.is_empty(): return result
	for item in raw.hex_decode(): result.append(int(item))
	return result
func _has_displayable_text(entry: Dictionary) -> bool:
	var text := str(entry.get("text", ""))
	var trace: Variant = entry.get("program_trace", {}); var resolution: Variant = entry.get("display_resolution", {})
	if trace is Dictionary and bool(trace.get("partial_display", false)): return false
	if resolution is Dictionary and str(resolution.get("status", "")).contains("partial_native_page"): return false
	return bool(entry.get("display_ready", not text.strip_edges().is_empty())) and not text.strip_edges().is_empty()
