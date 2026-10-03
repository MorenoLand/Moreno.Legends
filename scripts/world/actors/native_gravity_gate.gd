extends Node
class_name NativeGravityGate
var level: Node3D
var player: Node3D
var audio: Node
var context: Dictionary
var source: Dictionary
var gate: Dictionary
var previous := 0
var elapsed := 0.0
func configure(parent: Node3D, owner_game: Node, flags_context: Dictionary, document: Dictionary, entry: Dictionary) -> void:
	level = parent; context = flags_context; source = document["source"]; gate = entry; audio = owner_game.get("audio")
	var ancestor: Node = parent
	while ancestor != null and player == null: player = ancestor.get_node_or_null("Player") as Node3D; ancestor = ancestor.get_parent()
func _physics_process(delta: float) -> void:
	if not is_instance_valid(level) or not is_instance_valid(player): return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func _native_tick() -> void:
	var record := Vector3(gate["position"][0], gate["position"][1], gate["position"][2]); var offset := (level.to_local(player.global_position) - record) * 256.0
	var bearing := roundi(atan2(offset.x, -offset.z) * 4096.0 / TAU) & 0xFFF; var difference := (((int(gate["angle_raw"]) & 0xFFF) - bearing + 0x800) & 0xFFF) - 0x800; var crossed := ((difference ^ previous) & 0x800) != 0
	if offset.length() < float(gate["radius_raw"]) and crossed: _fire()
	previous = difference & 0xFFFF
func _fire() -> void:
	var flags: Dictionary = context.get("event_flags", {})
	for id in source["clear_flags"]: flags[_key(flags, int(str(id).hex_to_int()))] = false
	flags[_key(flags, str(source["set_flag"]).hex_to_int())] = true
	if audio != null and audio.has_method("play_sound"): audio.play_sound(str(source["sound"]).hex_to_int())
func _key(flags: Dictionary, id: int) -> Variant: return id if flags.has(id) or not flags.has(str(id)) else str(id)
