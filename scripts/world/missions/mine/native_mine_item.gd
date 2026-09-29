extends Node
var host: Node
var actor: Node3D
var entry: Dictionary = {}
var data: Dictionary = {}
var busy := false
func configure(gameplay: Node, target: Node3D, source: Dictionary, descriptor: Dictionary) -> void:
	host = gameplay; actor = target; entry = source; data = descriptor; actor.set_meta("native_item_controller", self); actor.set_meta("native_interaction_label", "Open"); _control(2 if _flag(int(data["collected_flag"])) else 0, 16 if _flag(int(data["collected_flag"])) else 0)
func can_interact() -> bool: return not busy and is_instance_valid(actor) and not _flag(int(data["collected_flag"]))
func interact() -> bool:
	if not can_interact(): return false
	busy = true; host.audio.play_at(0xF1, actor.global_position); _control(1)
	await host.event_script.play_bound_message(str(entry["stage"]), "0x8010C000", int(data["message_index"]), str(data.get("message_call", "0x800BE330")), actor, 0)
	if not is_instance_valid(actor): return false
	await _wait_terminal()
	var reward := int(data["reward_word"]); var kind := (reward >> 24) & 255
	if kind == 1: host.native_context["native_save_byte46"] = reward & 255
	elif kind in [3, 6] and (reward & 0xFFFFFF) != 0: _set_flag(reward & 0xFFFFFF)
	_set_flag(int(data["collected_flag"])); host.event_script.update_native_context(host.native_context); host.event_script.native_context_changed.emit(str(entry["stage"]), host.native_context); host.audio.play_at(0xF2, actor.global_position); _control(2); await _wait_terminal(); busy = false; return true
func _flag(id: int) -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag(id: int) -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); flags[id if flags.has(id) or not flags.has(str(id)) else str(id)] = true; host.native_context["event_flags"] = flags
func _clock() -> NativeAnimation: return actor.find_child("NativeAnimationClock", true, false) as NativeAnimation
func _control(code: int, start_record := 0) -> void:
	var clock := _clock()
	if is_instance_valid(clock): clock.play_control(code, start_record, true)
func _wait_terminal() -> void:
	var clock := _clock()
	while is_instance_valid(actor) and is_instance_valid(clock) and not clock.held: await get_tree().physics_frame
