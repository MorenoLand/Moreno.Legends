extends Node
## Headless differential-test driver for tools/models.py runner-verify: runs recorded function cases through the translated units and GTE cases through the GTE, writing registers plus RAM digests.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Gte := preload("res://scripts/runner/gte.gd")


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	var source := args[0].trim_suffix("/") + "/"
	var work := args[2].trim_suffix("/") + "/"
	_functions(source, args[1], work)
	_gte(work)
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
