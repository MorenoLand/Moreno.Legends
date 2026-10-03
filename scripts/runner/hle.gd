extends "res://scripts/runner/hle_bios.gd"
## Engine services of the original game implemented against the port; every h_XXXXXXXX method replaces the original function at that address.

const Bridge := preload("res://scripts/runner/runner_bridge.gd")

var gte
var bridge := Bridge.new()
var frame := 0
var fades: Array = []


## GAME 0x800C3CB4: the original player update runs while a scene drives the player; otherwise the port's player controller stays authoritative.
func h_800C3CB4() -> void:
	if machine.u8(0x8007CEC0) & 1 == 1:
		machine.run_original(0x800C3CB4)


## GAME 0x800CB4DC: the player's reaction to its hit words (also reached during scenes); the host forwards the words to the port's player instead.
func h_800CB4DC() -> void:
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


## SLES 0x800203F4(id, position): queues a positional sound effect; the position is the actor's 16.16 vector (halfwords at +2, +6 and +10).
func h_800203F4() -> void:
	var point := R[5]
	if point == 0:
		bridge.sound(R[4], 0, 0, 0, false)
	else:
		bridge.sound(R[4], machine.s16(point + 2), machine.s16(point + 6), machine.s16(point + 10))
	R[2] = 0


## SLES 0x80020384(id, a, b): queues a sound effect without a position.
func h_80020384() -> void:
	bridge.sound(R[4], 0, 0, 0, false)
	R[2] = 0


## SLES 0x800201B0(id): starts a music sequence.
func h_800201B0() -> void:
	bridge.music(R[4])
	R[2] = 0


## SLES 0x80015B6C(focus, distance, yaw, pitch, roll): builds the view matrix; the host takes the arguments as the scene camera, may replace them with the port camera, and the original still runs.
func h_80015B6C() -> void:
	var focus := R[4]
	if not bridge.camera_override.is_empty():
		var view: Array = bridge.camera_override
		machine.put32(focus, view[0].x)
		machine.put32(focus + 4, view[0].y)
		machine.put32(focus + 8, view[0].z)
		R[5] = view[1]
		R[6] = view[2]
		R[7] = view[3]
		machine.put32(R[29] + 16, view[4])
	bridge.camera(Vector3i(machine.s32(focus), machine.s32(focus + 4), machine.s32(focus + 8)), R[5], R[6], R[7], machine.s32(R[29] + 16))
	machine.run_original(0x80015B6C)


## GAME 0x800BBDD8(actor, mode, shift, colour): registers a boss gauge; the host binds the port's gauge and the original still fills its slot.
func h_800BBDD8() -> void:
	bridge.boss(R[4], R[5], R[6], R[7])
	machine.run_original(0x800BBDD8)


## SLES 0x8001B9A4(descriptor): prepares and starts an XA voice or music stream.
func h_8001B9A4() -> void:
	bridge.xa(R[4])


## SLES 0x8001B864(id | volume << 16): the play half of 0x8001B9A4 (0x8001B714 only queues the seek); scenes call it directly.
func h_8001B864() -> void:
	bridge.xa(R[4] & 0xFFFF)


## SLES 0x8001AF94: non-zero while an XA stream is playing.
func h_8001AF94() -> void:
	R[2] = 1 if bridge.xa_active else 0


## SLES 0x8001AFD0: non-zero once no XA stream is playing.
func h_8001AFD0() -> void:
	R[2] = 0 if bridge.xa_active else 1


## SLES 0x8001BA44(speed): fades the playing XA stream out.
func h_8001BA44() -> void:
	bridge.xa_fade(R[4])


## GAME 0x800CFF88(actor, reach, mode): an actor tries to seize the player; the host answers through the port's hold API.
func h_800CFF88() -> void:
	R[2] = int(bridge.grab_handler.call(R[4] & 0xFFFFFFFF, R[5], R[6])) if bridge.grab_handler.is_valid() else 0


## GAME 0x800D008C: the per-tick hold update (position copy, mash counter, health drain); the port's hold runs it.
func h_800D008C() -> void:
	pass


## GAME 0x800C0B0C(scene): starts a scene unless the port plays that scene from its own contract.
func h_800C0B0C() -> void:
	if not bridge.blocked_scenes.has(R[4]):
		machine.run_original(0x800C0B0C)


## SLES 0x800427A0(start, kind, end, second_kind, owner, flags, hit_word): registers an attack segment; the host also tests it against the port's enemies.
func h_800427A0() -> void:
	var start := R[4]
	var finish := R[6]
	var stack := R[29]
	bridge.segments.append({"owner": machine.u32(stack + 0x10), "start": Vector3i(machine.s16(start), machine.s16(start + 2), machine.s16(start + 4)), "end": Vector3i(machine.s16(finish), machine.s16(finish + 2), machine.s16(finish + 4)), "kind": R[5] & 0xFFFF, "flags": machine.u32(stack + 0x14), "word": machine.u32(stack + 0x18)})
	machine.run_original(0x800427A0)


## SLES 0x80042704(start, owner data, category, attack word): registers a point or short attack (the special-weapon launchers use it); the end point is the previous position stored at owner data +4/+6, the attack word's low 12 bits are the damage and its upper bits the hit flags (0x40000 player shot, 0x80000 player melee).
func h_80042704() -> void:
	var start := R[4]
	var finish := R[5]
	var begin := Vector3i(machine.s16(start), machine.s16(start + 2), machine.s16(start + 4))
	bridge.segments.append({"owner": finish, "start": begin, "end": Vector3i(machine.s16(finish + 4), begin.y, machine.s16(finish + 6)) if machine.s32(finish + 4) != 0 else begin, "kind": 0, "flags": 0, "word": R[7]})
	machine.run_original(0x80042704)


## GAME 0x800CE808, 0x800CEA04, 0x800CEB20, 0x800CEC94: the player's special-weapon firing states; the port's shot sequence (special_shot.gd) plays them and asks the host to spawn the projectile through GAME 0x800CE5D4.
func h_800CE808() -> void:
	pass


func h_800CEA04() -> void:
	pass


func h_800CEB20() -> void:
	pass


func h_800CEC94() -> void:
	if bridge.drive_blade:
		machine.run_original(0x800CEC94)
