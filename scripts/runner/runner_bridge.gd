extends RefCounted
## What the original code asks of the port: the host overrides these to drive dialogue, fades, audio and camera; the defaults complete every request after a fixed delay so the code can run without a game around it.

const MESSAGE_FRAMES := 45
const TRANSITION_FRAMES := 25

var frame := 0
var windows := {}
var transition_until := -1
var log: Array = []


func message_open(window: int, bank: int, index: int) -> void:
	windows[window] = {"bank": bank, "index": index, "until": frame + MESSAGE_FRAMES}
	log.append(["message", window, bank, index])


func message_busy(window: int) -> bool:
	return windows.has(window) and int(windows[window]["until"]) > frame


func message_close(window: int) -> void:
	windows.erase(window)


func message_close_all() -> void:
	windows.clear()


func transition(kind: int, argument: int) -> void:
	transition_until = frame + TRANSITION_FRAMES
	log.append(["transition", kind, argument])


func transition_busy() -> bool:
	return transition_until > frame


func music_fade(mask: int, step: int, delay: int) -> void:
	log.append(["music_fade", mask, step, delay])
