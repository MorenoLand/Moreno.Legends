extends Node
class_name NativeAnimation
signal record_entered(index: int, event: int)
signal terminal_record
const NATIVE_HZ := 25.0
const EXPORTED_POSE_HZ := 30.0
var animation_player: AnimationPlayer
var controls: Dictionary = {}
var current_control := -1
var record_index := -1
var record_counter := 0
var pose := 0
var event_code := 0
var record_flags := 0
var remaining_ticks := 0
var held := false
var automatic := true
var elapsed := 0.0
var revision := 0
var records: Array = []
var offsets: Array[int] = []
func configure(player: AnimationPlayer, animations: Array) -> bool:
	animation_player = player; controls.clear(); current_control = -1; records.clear(); offsets.clear(); elapsed = 0.0; held = false; revision += 1
	if not is_instance_valid(animation_player): return false
	for clip: Dictionary in animations:
		if clip.has("slot") and clip.has("records") and animation_player.has_animation(str(clip.get("name", ""))): controls[int(clip["slot"])] = clip
	return not controls.is_empty()
func play_control(code: int, start_record: int = 0, restart: bool = false) -> bool:
	if not is_instance_valid(animation_player) or not controls.has(code): return false
	if current_control == code and not restart: return true
	var clip: Dictionary = controls[code]; var source_records: Array = clip["records"]
	if start_record < 0 or start_record >= source_records.size(): return false
	if (int(source_records[-1].get("flags", 0)) & 128) == 0: return false
	var source_offsets: Array[int] = []; var ticks := 0
	for record: Dictionary in source_records:
		var duration: int = int(record.get("duration", record.get("durationTicks", 0))); var flags: int = int(record.get("flags", 0))
		if duration <= 0 or ((flags & 128) != 0 and flags != 255 and (flags & 127) >= source_records.size()): return false
		source_offsets.append(ticks); ticks += duration
	current_control = code; records = source_records; offsets = source_offsets; record_counter = start_record & 255; held = false; revision += 1
	animation_player.play(str(clip["name"])); animation_player.advance(0.0); animation_player.pause(); _enter_record(start_record)
	return true
func native_tick() -> void:
	if current_control < 0 or not is_instance_valid(animation_player): return
	remaining_ticks -= 1
	if remaining_ticks == 0:
		if record_flags == 255: remaining_ticks = _duration(records[record_index])
		elif (record_flags & 128) != 0: record_counter = 0; _enter_record(record_flags & 127); return
		else:
			if record_index + 1 >= records.size(): return
			record_counter = (record_counter + 1) & 255; _enter_record(record_index + 1); return
	_apply_pose()
func _enter_record(index: int) -> void:
	var previously_held := held; var entry_revision := revision; record_index = index; var record: Dictionary = records[index]; pose = int(record.get("pose", 0)); event_code = int(record.get("event", 0)); record_flags = int(record.get("flags", 0)); remaining_ticks = _duration(record); held = record_flags == 255; _apply_pose(); record_entered.emit(record_index, event_code)
	if entry_revision == revision and held and not previously_held: terminal_record.emit()
func _duration(record: Dictionary) -> int: return int(record.get("duration", record.get("durationTicks", 0)))
func _apply_pose() -> void:
	var tick: int = offsets[record_index] + _duration(records[record_index]) - remaining_ticks
	animation_player.seek(float(tick) / EXPORTED_POSE_HZ, true)
func _physics_process(delta: float) -> void:
	if not automatic or current_control < 0: return
	elapsed += delta * NATIVE_HZ
	while elapsed >= 1.0: elapsed -= 1.0; native_tick()
