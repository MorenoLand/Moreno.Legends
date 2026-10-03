extends RefCounted
## What the original code asks of the port: the host drains `log` every tick and answers message and transition requests; without a host (`manual` false) every request completes after a fixed delay so the code can run alone.

const MESSAGE_FRAMES := 45
const TRANSITION_FRAMES := 25

var frame := 0
var manual := false
var windows := {}
var transition_until := -1
var log: Array = []
var xa_active := false
var grab_handler := Callable()
var blocked_scenes := {}
var segments: Array = []
## True while the host drives the Blade Arm sequence handler (GAME 0x800CEC94); otherwise that handler is a no-op.
var drive_blade := false
var camera_override: Array = []
var camera_last: Array = []


func message_open(window: int, bank: int, index: int) -> void:
	windows[window] = {"bank": bank, "index": index, "until": INF if manual else frame + MESSAGE_FRAMES}
	log.append(["message", window, bank, index])


func message_busy(window: int) -> bool:
	return windows.has(window) and (manual or int(windows[window]["until"]) > frame)


func message_close(window: int) -> void:
	windows.erase(window)
	log.append(["message_close", window])


func message_close_all() -> void:
	windows.clear()
	log.append(["message_close", -1])


func transition(kind: int, argument: int) -> void:
	transition_until = frame + TRANSITION_FRAMES
	log.append(["transition", kind, argument])


func transition_busy() -> bool:
	return transition_until > frame


func music_fade(mask: int, step: int, delay: int) -> void:
	log.append(["music_fade", mask, step, delay])


func music(id: int) -> void:
	log.append(["music", id])


func sound(id: int, x: int, y: int, z: int, positioned := true) -> void:
	log.append(["sound", id, x, y, z, positioned])


func camera(focus: Vector3i, distance: int, yaw: int, pitch: int, roll: int) -> void:
	camera_last = [focus, distance, yaw, pitch, roll]
	log.append(["camera", focus, distance, yaw, pitch, roll])


func boss(actor: int, mode: int, shift: int, color: int) -> void:
	log.append(["boss", actor, mode, shift, color])


func xa(id: int) -> void:
	log.append(["xa", id])


func xa_fade(speed: int) -> void:
	log.append(["xa_fade", speed])
