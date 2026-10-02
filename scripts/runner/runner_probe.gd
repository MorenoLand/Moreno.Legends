extends Node
## Headless pilot scenario for tools/models.py runner-pilot: plays Forbidden Island scene 0x28, the class-52 boss fight and scene 0x29 through the original code and writes a JSON report.

const Session := preload("res://scripts/runner/runner_session.gd")
const PLAYER := 0x8008C0A0
const BOSS_CLASS := 0x34
const HIT_DAMAGE := 60
const HIT_INTERVAL := 15
const FIGHT_START_DELAY := 100


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var report := _play(args[0], args[1])
	var file := FileAccess.open(args[2], FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	get_tree().quit()


func _play(source: String, stage: String) -> Dictionary:
	var session := Session.new()
	var report := {"stage": stage}
	var opened := Time.get_ticks_msec()
	if not session.open(stage, source.trim_suffix("/") + "/"):
		report["error"] = "open failed"
		return report
	report["load_ms"] = Time.get_ticks_msec() - opened
	var machine = session.machine
	var bridge = session.hle.bridge
	session.begin(0x1D, 1, 1)
	session.set_flag(0x681)
	machine.put32(PLAYER + 0x10, 512 * 65536)
	machine.put32(PLAYER + 0x14, 0)
	machine.put32(PLAYER + 0x18, 3000 * 65536)
	machine.put8(PLAYER + 8, 1)
	var boss := 0
	var times: Array = []
	var fight_start := -1
	var events := {}
	for frame in 3000:
		machine.put8(PLAYER + 0x9F, machine.u8(PLAYER + 0x9F) | 0x80)
		var started := Time.get_ticks_usec()
		session.frame()
		var elapsed := Time.get_ticks_usec() - started
		if not events.has("scene_0x28_started") and machine.u8(0x8007CEC1) == 0x28:
			events["scene_0x28_started"] = frame
		if boss == 0:
			for actor in session.actor_slots():
				if machine.u8(actor + 4) == BOSS_CLASS and machine.u8(actor + 5) == 2:
					boss = actor
					fight_start = frame
					events["fight_boss_spawned"] = frame
					report["boss_hp"] = [machine.s16(boss + 0x70), machine.s16(boss + 0x72)]
					report["boss_position"] = [machine.s32(boss + 0x10) >> 16, machine.s32(boss + 0x14) >> 16, machine.s32(boss + 0x18) >> 16]
		elif not events.has("boss_dead"):
			times.append(elapsed)
			if frame - fight_start >= FIGHT_START_DELAY and (frame - fight_start) % HIT_INTERVAL == 0 and machine.s16(boss + 0x70) >= 0:
				machine.put32(boss + 0x14C, 0x40000 | HIT_DAMAGE)
			if machine.s16(boss + 0x70) < 0:
				events["boss_dead"] = frame
		if events.has("boss_dead") and not events.has("flag_0x682") and session.flag(0x682):
			events["flag_0x682"] = frame
		if events.has("flag_0x682") and not events.has("scene_0x29_started") and machine.u8(0x8007CEC1) == 0x29 and machine.u8(0x8007CEC0) != 0:
			events["scene_0x29_started"] = frame
		if events.has("scene_0x29_started") and machine.u8(0x8007CEC0) == 0:
			events["scene_0x29_finished"] = frame
		if events.has("scene_0x29_started") and machine.u8(0x80078D08) != 0 and not events.has("stage_request"):
			events["stage_request"] = frame
			report["request"] = {"type": machine.u8(0x80078D08), "stage": machine.u8(0x80078D0C), "area": machine.u8(0x80078D0D), "position": [machine.s16(0x80078D18), machine.s16(0x80078D1A), machine.s16(0x80078D1C)], "facing": machine.s16(0x80078D1E), "arrival_fade": machine.u8(0x80078D20)}
		if events.has("stage_request"):
			break
	report["frames"] = session.frame_count
	report["events"] = events
	report["fight_frame_ms"] = _statistics(times)
	report["faults"] = session.faults().map(func(address: int) -> String: return "0x%08X" % (address & 0xFFFFFFFF))
	report["messages"] = bridge.log.filter(func(entry: Array) -> bool: return entry[0] == "message").map(func(entry: Array) -> int: return int(entry[3]))
	report["transitions"] = bridge.log.filter(func(entry: Array) -> bool: return entry[0] == "transition").map(func(entry: Array) -> Array: return [entry[1], entry[2]])
	return report


func _statistics(values: Array) -> Dictionary:
	if values.is_empty():
		return {}
	var sorted := values.duplicate()
	sorted.sort()
	var total := 0
	for value in sorted:
		total += int(value)
	return {"mean": snappedf(float(total) / sorted.size() / 1000.0, 0.01), "p95": snappedf(float(sorted[int(sorted.size() * 0.95)]) / 1000.0, 0.01), "max": snappedf(float(sorted[-1]) / 1000.0, 0.01)}
