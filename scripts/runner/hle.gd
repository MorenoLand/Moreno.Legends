extends RefCounted
## Engine services of the original game implemented against the port; every h_XXXXXXXX method replaces the original function at that address.

const Bridge := preload("res://scripts/runner/runner_bridge.gd")

var machine
var R: PackedInt32Array
var ram: PackedByteArray
var gte
var bridge := Bridge.new()
var frame := 0
var rand_seed := 1
var fades: Array = []


## GAME 0x800C3CB4: the original player update runs while a scene drives the player; otherwise the port's player controller stays authoritative.
func h_800C3CB4() -> void:
	if machine.u8(0x8007CEC0) & 1 == 1:
		machine.run_original(0x800C3CB4)


## GAME 0x800C42F4: the original player-versus-hit-volume resolution; the host applies registered hit volumes to the port's player instead.
func h_800C42F4() -> void:
	pass


## SLES 0x80048474(window, bank, message): opens a message window; the bridge shows the stage message.
func h_80048474() -> void:
	bridge.message_open(R[4], R[5], R[6])
	R[2] = 0


## SLES 0x800489A0(window): window state bits (non-zero while the message is open).
func h_800489A0() -> void:
	R[2] = 1 if bridge.message_busy(R[4]) else 0


## SLES 0x80048764(window, flag): closes one message window.
func h_80048764() -> void:
	bridge.message_close(R[4])


## SLES 0x80048944(flag): closes every message window.
func h_80048944() -> void:
	bridge.message_close_all()


## SLES 0x8001392C(type, argument): starts a screen transition.
func h_8001392C() -> void:
	bridge.transition(R[4], R[5])


## SLES 0x800677C4: EnterCriticalSection (BIOS syscall 1); nothing interrupts the runner.
func h_800677C4() -> void:
	R[2] = 1


## SLES 0x800677D4: ExitCriticalSection (BIOS syscall 2).
func h_800677D4() -> void:
	pass


## SLES 0x80020984(mask, step, delay): fades the sequence slots in the mask; their finished bits (word 0x80078CA4) return once the fade has run.
func h_80020984() -> void:
	var mask := R[4]
	var step := maxi(1, -R[5] if R[5] < 0 else R[5])
	bridge.music_fade(mask, step, R[6])
	machine.put32(0x80078CA4, machine.s32(0x80078CA4) & ~mask)
	fades.append({"mask": mask, "due": frame + R[6] + ceili(32767.0 / step)})
	R[2] = 0


## Per-frame bookkeeping of what the audio engine and the CD drive would have finished by now.
func tick() -> void:
	frame += 1
	bridge.frame = frame
	var pending := []
	for fade in fades:
		if int(fade["due"]) <= frame:
			machine.put32(0x80078CA4, machine.s32(0x80078CA4) | int(fade["mask"]))
		else:
			pending.append(fade)
	fades = pending
	machine.put32(0x80078DC8, machine.s32(0x80078DC8) & ~1)
	machine.put16(0x80078DBA, machine.u16(0x80078DBA) & ~1)


## GAME 0x800B0314: the original render submission; the port draws the world.
func h_800B0314() -> void:
	pass


## SLES 0x80067674: BIOS rand() (A0 0x2F), the kernel's linear congruential generator.
func h_80067674() -> void:
	rand_seed = (rand_seed * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
	R[2] = (rand_seed >> 16) & 0x7FFF
