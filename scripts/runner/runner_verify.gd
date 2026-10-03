extends Node
## Headless differential-test driver for tools/models.py runner-verify: runs recorded function cases through the translated units and GTE cases through the GTE, writing registers plus RAM digests.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Gte := preload("res://scripts/runner/gte.gd")
const Session := preload("res://scripts/runner/runner_session.gd")
const PLAYER := 0x8008C0A0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var source := args[0].trim_suffix("/") + "/"
	var work := args[2].trim_suffix("/") + "/"
	_functions(source, args[1], work)
	_gte(work)
	_effects(source, args[1], work)
	get_tree().quit()


func _functions(source: String, stage: String, work: String) -> void:
	var machine := Machine.new(source)
	machine.load_unit("engine", FileAccess.get_file_as_string(source + "engine.gd"))
	machine.load_unit("ovl", FileAccess.get_file_as_string(source + stage + ".gd"))
	var base := FileAccess.get_file_as_bytes(work + "ram_test.bin")
	var cases := FileAccess.get_file_as_bytes(work + "cases.bin")
	var out := FileAccess.open(work + "results.bin", FileAccess.WRITE)
	var position := 4
	for _case in cases.decode_u32(0):
		var address := cases.decode_u32(position)
		position += 4
		machine.reset_ram(base)
		for index in 34:
			machine.R[index] = cases.decode_s32(position)
			position += 4
		machine.run_function(address)
		var registers := PackedByteArray()
		registers.resize(34 * 4)
		for index in 34:
			registers.encode_s32(index * 4, machine.R[index])
		out.store_buffer(registers)
		out.store_buffer(_digest(machine.ram.slice(0, 0x200000)))
		out.store_buffer(_digest(machine.ram.slice(0x800000, 0x800400)))
	out.close()


func _gte(work: String) -> void:
	var cases := FileAccess.get_file_as_bytes(work + "gte_cases.bin")
	var out := FileAccess.open(work + "gte_results.bin", FileAccess.WRITE)
	var gte := Gte.new()
	var position := 4
	for _case in cases.decode_u32(0):
		var command := cases.decode_u32(position)
		position += 4
		for index in 32:
			gte.d[index] = cases.decode_s32(position + index * 4)
			gte.c[index] = cases.decode_s32(position + 128 + index * 4)
		position += 256
		gte.cmd(command)
		var registers := PackedByteArray()
		registers.resize(128)
		for index in 32:
			registers.encode_s32(index * 4, gte.d[index])
		out.store_buffer(registers)
	out.close()


func _digest(bytes: PackedByteArray) -> PackedByteArray:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish()


## Plays the ST1D boss fight until the effect renderer has produced at least 16 packets, one of them with a visible size, then stores the state before the render (RAM, scratchpad, GTE registers) and the packets it produced.
func _effects(source: String, stage: String, work: String) -> void:
	var session := Session.new()
	if not session.open(stage, source):
		return
	var machine = session.machine
	session.hle.bridge.manual = true
	session.begin(0x1D, 1, 1)
	session.set_flag(0x681)
	machine.put32(PLAYER + 0x10, 512 * 65536)
	machine.put32(PLAYER + 0x14, 0)
	machine.put32(PLAYER + 0x18, 3000 * 65536)
	var boss := 0
	for tick in 1500:
		for event: Array in session.hle.bridge.log:
			if event[0] == "message":
				session.hle.bridge.windows.erase(event[1])
		session.hle.bridge.log.clear()
		machine.put8(PLAYER + 0x9F, machine.u8(PLAYER + 0x9F) | 0x80)
		session.frame()
		if boss == 0:
			for actor in session.actor_slots():
				if machine.u8(actor + 4) == 0x34 and machine.u8(actor + 5) == 2:
					boss = actor
		elif tick % 15 == 0 and machine.s16(boss + 0x70) >= 0:
			machine.put32(boss + 0x14C, 0x40000 | 60)
		if boss == 0 or tick % 3 != 0:
			continue
		session.prepare_camera()
		var ram: PackedByteArray = machine.ram.slice(0, 0x200000)
		var scratch: PackedByteArray = machine.ram.slice(0x800000, 0x800400)
		var registers := PackedByteArray()
		registers.resize(256)
		for index in 32:
			registers.encode_s32(index * 4, machine.gte.d[index])
			registers.encode_s32(128 + index * 4, machine.gte.c[index])
		machine.gte.trace = []
		var packets: Array = session.draw()
		var spread := 0
		for packet: Dictionary in packets:
			spread = maxi(spread, int(((packet["vertices"] as Array[Vector2])[0] - (packet["vertices"] as Array[Vector2])[2]).length()))
		if packets.size() < 16 or spread < 4:
			continue
		var trace := PackedByteArray()
		for entry: Array in machine.gte.trace:
			var record := PackedByteArray()
			record.resize(4 + 128 * 3 + 4)
			record.encode_u32(0, entry[0])
			for index in 32:
				record.encode_s32(4 + index * 4, (entry[1] as PackedInt32Array)[index])
				record.encode_s32(132 + index * 4, (entry[2] as PackedInt32Array)[index])
				record.encode_s32(260 + index * 4, (entry[3] as PackedInt32Array)[index])
			record.encode_s32(388, entry[4])
			trace.append_array(record)
		machine.gte.trace = null
		var trace_file := FileAccess.open(work + "effects_gte_trace.bin", FileAccess.WRITE)
		trace_file.store_buffer(trace)
		trace_file.close()
		for pair in [["effects_ram.bin", ram], ["effects_scratch.bin", scratch], ["effects_gte.bin", registers]]:
			var file := FileAccess.open(work + pair[0], FileAccess.WRITE)
			file.store_buffer(pair[1])
			file.close()
		var listing := []
		for packet: Dictionary in packets:
			var vertices := []
			for vertex: Vector2 in packet["vertices"]:
				vertices.append([int(vertex.x), int(vertex.y)])
			listing.append({"cmd": packet["cmd"], "vertices": vertices})
		var report := FileAccess.open(work + "effects_packets.json", FileAccess.WRITE)
		report.store_string(JSON.stringify(listing))
		report.close()
		return
