extends "res://scripts/world/enemies/native_icefield_enemy.gd"
const PROFILE := {"mash": 0x20, "drain_every": 4, "drain": 1}
var timer := 0
func configure(gameplay: Node, entry: Dictionary, metadata: Dictionary, path: String) -> bool:
	if not super(gameplay, entry.merged({"source_attributes": [0]}, true), metadata, path): return false
	top = 1; sub = 0; step = 0; control = 0; control_at_start = 0; clock.play_control(0, 0, true); model.visible = false
	return true
func _run() -> void:
	match sub:
		0: _wait()
		1: _telegraph()
		2: _missed()
		3: _hold()
		4: if (clock.record_flags & 128) != 0: model.visible = false; _go(5)
		5: _retreat()
func _go(value: int) -> void: sub = value; step = 0
func _in_reach() -> bool:
	var offset := (target.global_position - global_position) * 256.0
	return absf(offset.x) < 64.0 and absf(offset.y) < 64.0 and absf(offset.z) < 64.0
func _seize(intro: bool) -> bool:
	if not _in_reach() or not target.begin_hold(self, PROFILE): return false
	if not intro: target.hold_grip()
	return true
func _wait() -> void:
	if step == 0: control = 0; model.visible = false; step = 1
	elif _seize(true): _sound(0x203); _face(roundi(-target.player_model.global_rotation.y * 4096.0 / TAU)); _go(1)
func _telegraph() -> void:
	if step == 0: timer = 0x10; step = 1
	timer -= 1
	if timer != 0: return
	if target.holder == self: target.hold_grip(); control = 1; start_record = 0; _go(3)
	else: _go(2)
func _missed() -> void:
	if step == 0:
		if not target.hurt_phase.is_empty(): _go(5)
		elif target.holder != self: step = 1
	elif _seize(false): control = 1; start_record = 0; _go(3)
	elif target.jump_phase == 0 and target.is_on_floor(): _go(5)
func _hold() -> void:
	match step:
		0: model.visible = true; _set_scale(0x210, 0x210, 0x210); step = 1
		1:
			if clock.record_index == 7: _sound(0x204); step = 2
		2:
			if (clock.record_flags & 128) != 0: target.hold_arm(); step = 3
		3:
			var angle := float(native_ticks & 15) * TAU / 16.0; var wobble := 0x210 + (floori(sin(angle) * 4096.0) >> 8)
			_set_scale(wobble, 0x210 + (floori(cos(angle) * 4096.0) >> 8), wobble)
			if (native_ticks & 15) == 8: _sound(0x205)
	if not target.hurt_phase.is_empty() or target.holder != self: control = 2; start_record = maxi(0xD - clock.record_index, 0); _go(4)
func _retreat() -> void:
	if step == 0: timer = 0x10; step = 1
	timer -= 1
	if timer == 0: _go(0)
