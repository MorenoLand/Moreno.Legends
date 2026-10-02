extends RefCounted
## Emulated PlayStation RAM, register file and the generated code units; calls original functions by address and routes intercepted ones to the HLE object.

## RAM mirrors collapse into 0..0x1FFFFF through the 0x9FFFFF mask; the scratchpad (0x1F800000) lands at 0x800000 and the I/O window (0x1F801000) right behind it; the array spans every index the mask can produce.
const RAM_SIZE := 0xA00010
const SCRATCH_OFFSET := 0x800000
const STACK_TOP := 0x801FFF00
const GLOBAL_POINTER := 0x8007890C
const GteScript := preload("res://scripts/runner/gte.gd")
const UnitScript := preload("res://scripts/runner/mips_unit.gd")

var R := PackedInt32Array()
var ram := PackedByteArray()
var gte := GteScript.new()
var hle: RefCounted
var units: Dictionary = {}
var fn: Dictionary = {}
var originals: Dictionary = {}
var replaced: Dictionary = {}
var directory := ""


func _init(code_directory: String) -> void:
	directory = code_directory
	R.resize(34)
	ram.resize(RAM_SIZE + 16)
	R[29] = STACK_TOP
	R[28] = GLOBAL_POINTER


func set_hle(handler: RefCounted) -> void:
	hle = handler
	handler.set("machine", self)
	handler.set("R", R)
	handler.set("ram", ram)
	handler.set("gte", gte)
	for unit in units.values():
		unit.hle = handler
	for method in handler.get_method_list():
		var name: String = method["name"]
		if name.begins_with("h_") and name.length() == 10:
			var address := name.substr(2).hex_to_int()
			replaced[address] = true
			fn[address] = Callable(handler, name)


func load_image(path: String, address: int) -> bool:
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.is_empty():
		return false
	write_bytes(address, bytes)
	return true


func write_bytes(address: int, bytes: PackedByteArray) -> void:
	var start := address & 0x9FFFFF
	ram = ram.slice(0, start) + bytes + ram.slice(start + bytes.size())
	_bind()


func reset_ram(image: PackedByteArray) -> void:
	ram = image.duplicate()
	ram.resize(RAM_SIZE)
	_bind()


func _bind() -> void:
	if hle:
		hle.set("ram", ram)
	for unit in units.values():
		unit.ram = ram


func load_unit(name: String, source: String) -> bool:
	var script := GDScript.new()
	script.source_code = source
	if script.reload() != OK:
		push_error("Runner: unit %s failed to compile" % name)
		return false
	var unit: RefCounted = script.new()
	unit.R = R
	unit.ram = ram
	unit.gte = gte
	unit.hle = hle
	unit.fn = fn
	units[name] = unit
	for other in units.values():
		other.set(name, unit)
	for known in units:
		unit.set(known, units[known])
	var table := {}
	unit.call("table", table)
	for address in table:
		originals[address] = table[address]
		if not replaced.has(address):
			fn[address] = table[address]
	return true


func call_function(address: int, a0 := 0, a1 := 0, a2 := 0, a3 := 0) -> int:
	R[4] = a0
	R[5] = a1
	R[6] = a2
	R[7] = a3
	return run_function(address)


## Runs the translated original of a function that the HLE object replaces.
func run_original(address: int) -> int:
	originals[address & 0xFFFFFFFF].call()
	return R[2]


func run_function(address: int) -> int:
	R[31] = 0x80000800
	var target: Variant = fn.get(address & 0xFFFFFFFF)
	if target == null:
		push_error("Runner: no code for 0x%08X" % (address & 0xFFFFFFFF))
		return 0
	target.call()
	return R[2]


func u32(address: int) -> int:
	return ram.decode_u32(address & 0x9FFFFF)


func s32(address: int) -> int:
	return ram.decode_s32(address & 0x9FFFFF)


func u16(address: int) -> int:
	return ram.decode_u16(address & 0x9FFFFF)


func s16(address: int) -> int:
	return ram.decode_s16(address & 0x9FFFFF)


func u8(address: int) -> int:
	return ram[address & 0x9FFFFF]


func put32(address: int, value: int) -> void:
	ram.encode_s32(address & 0x9FFFFF, value)


func put16(address: int, value: int) -> void:
	ram.encode_s16(address & 0x9FFFFF, value)


func put8(address: int, value: int) -> void:
	ram[address & 0x9FFFFF] = value & 255
