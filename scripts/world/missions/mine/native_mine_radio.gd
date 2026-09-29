extends Node3D
var host: Node
var data: Dictionary = {}
var started := false
func configure(gameplay: Node, descriptor: Dictionary) -> void: host = gameplay; data = descriptor; set_meta("native_actor_source", {"source_record_ram": str(data["source_record_ram"])})
func _physics_process(_delta: float) -> void:
	if started or not host.preparation_finished or not host.playable or host.loading: return
	if host.player.health < 0 or int(host.native_context.get("native_save_byte14", 0)) > int(data["maximum_scenario"]): queue_free(); return
	if host.native_scenes.active or bool(host.dialogue_box.get("active")): return
	var guard := int(data["skip_when_flag_set"]); var flags: Dictionary = host.native_context.get("event_flags", {})
	if guard >= 0 and bool(flags.get(guard, flags.get(str(guard), false))): queue_free(); return
	started = true; _present()
func _present() -> void:
	await host.event_script.play_bound_message(str(data["stage"]), str(data["bank_id"]), int(data["message_index"]), str(data["message_call"]), null, int(data["window"]))
	if is_inside_tree(): queue_free()
