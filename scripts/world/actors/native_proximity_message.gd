extends Node
var host: Node
var actor: Node3D
var data: Dictionary = {}
var busy := false
func configure(gameplay: Node, target: Node3D, descriptor: Dictionary) -> void:
	host = gameplay; actor = target; data = descriptor; set_physics_process(not _flag())
func _physics_process(_delta: float) -> void:
	if busy or not is_instance_valid(actor) or not is_instance_valid(host) or bool(host.get("loading")) or bool(host.dialogue_box.get("active")): return
	var player: Node3D = host.player; var offset := Vector3(-(player.global_position.x - actor.global_position.x), -(player.global_position.y - actor.global_position.y) - float(data["y_offset_raw"]) / 256.0, player.global_position.z - actor.global_position.z) * 256.0
	if offset.length() >= float(data["radius_raw"]): return
	busy = true; _set_flag(); host.event_script.update_native_context(host.native_context); host.event_script.native_context_changed.emit(str(data["stage"]), host.native_context)
	await host.event_script.play_bound_message(str(data["stage"]), str(data["bank_id"]), int(data["message_index"]), str(data["request_call"]), null, 0)
	if is_instance_valid(actor): actor.queue_free()
func _flag() -> bool:
	var flags: Dictionary = host.native_context.get("event_flags", {}) if is_instance_valid(host) else {}; var id := int(data["event_flag"]); return bool(flags.get(id, flags.get(str(id), false)))
func _set_flag() -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); var id := int(data["event_flag"]); flags[id if flags.has(id) or not flags.has(str(id)) else str(id)] = true; host.native_context["event_flags"] = flags
