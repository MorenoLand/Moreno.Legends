extends Node
var host: Node
var actor: Node3D
var elapsed := 0.0
var native_yaw := 0
var yaw_step := 0
var phase := 0
var base_y := 0.0
var bob_samples: Array = []
func configure(gameplay: Node, target: Node3D, entry: Dictionary, _metadata: Dictionary) -> void:
	host = gameplay; actor = target; var raw := str(entry.get("source_bytes_hex", "")).hex_decode()
	if raw.size() != 20: return
	native_yaw = int(entry.get("transform_raw", [0, 0, 0, 0])[3]); yaw_step = int(raw[10]); base_y = actor.position.y; actor.scale = Vector3.ONE * float(int(raw[9]) << 5) / 512.0
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/ST0F/mine_quest.json")); var profile: Dictionary = parsed.get("refractor", {}) if parsed is Dictionary else {}; var binding: Dictionary = actor.get_meta("native_interaction", {})
	bob_samples = profile.get("native_bob", {}).get("samples_raw", []); binding.merge({"stage": "ST0F", "bank_id": "0x8010C000", "message_index": int(raw[11]), "message_call": "0x800BDCF8", "request_call": "0x800F1D90", "request_kind": 0x12, "actor_class": 0x6F, "actor_callback": "0x800F1A8C", "target_flags60": 1, "target_descriptor_raw": profile.get("target_bounds_raw", []), "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": true, "line_of_sight": false}}, true); actor.set_meta("native_interaction", binding); actor.add_to_group("native_interaction_targets")
func _physics_process(delta: float) -> void:
	if not is_instance_valid(actor) or not host.preparation_finished or not host.playable or host.loading or host.native_scenes.active or not actor.is_visible_in_tree(): return
	elapsed += delta * 25.0
	while elapsed >= 1.0:
		elapsed -= 1.0; native_yaw = (native_yaw + yaw_step) & 4095; actor.rotation.y = -float(native_yaw) * TAU / 4096.0; phase = (phase + 1) & 63
		if bob_samples.size() == 64: actor.position.y = base_y - float((int(bob_samples[phase]) >> 8) - 8) / 256.0
