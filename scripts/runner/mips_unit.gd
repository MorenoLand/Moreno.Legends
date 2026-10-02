extends RefCounted
## Base of every generated unit: original MIPS functions compiled to GDScript over the shared register file and RAM (registers are signed 32-bit, R[32] is HI, R[33] is LO).

var R: PackedInt32Array
var ram: PackedByteArray
var gte
var hle
var engine
var fn: Dictionary
var faults: Array = []
var trace_log: Array = []


func miss(address: int) -> void:
	if not faults.has(address):
		faults.append(address)
		push_error("Runner: unresolved MIPS target 0x%08X (a0=0x%08X ra=0x%08X)" % [address & 0xFFFFFFFF, R[4] & 0xFFFFFFFF, R[31] & 0xFFFFFFFF])


func jalr(address: int) -> void:
	var target: Variant = fn.get(address)
	if target == null:
		miss(address)
		return
	target.call()


func div(a: int, b: int) -> void:
	if b == 0:
		R[33] = -1 if a >= 0 else 1
		R[32] = a
	elif a == -0x80000000 and b == -1:
		R[33] = -0x80000000
		R[32] = 0
	else:
		R[33] = a / b
		R[32] = a % b


func divu(a: int, b: int) -> void:
	a &= 0xFFFFFFFF
	b &= 0xFFFFFFFF
	if b == 0:
		R[33] = -1
		R[32] = a
	else:
		R[33] = a / b
		R[32] = a % b


func lwl(address: int, current: int) -> int:
	var n := address & 3
	var word := ram.decode_u32((address & 0x9FFFFC))
	return (current & (0x00FFFFFF >> (8 * n))) | ((word << (24 - 8 * n)) & 0xFFFFFFFF)


func lwr(address: int, current: int) -> int:
	var n := address & 3
	var word := ram.decode_u32((address & 0x9FFFFC))
	var keep := (0xFFFFFF00 << (8 * (3 - n))) & 0xFFFFFFFF
	return (current & keep) | (word >> (8 * n))


func swl(address: int, value: int) -> void:
	var n := address & 3
	var index := address & 0x9FFFFC
	var word := ram.decode_u32(index)
	var keep := (0xFFFFFF00 << (8 * n)) & 0xFFFFFFFF
	ram.encode_u32(index, (word & keep) | ((value & 0xFFFFFFFF) >> (24 - 8 * n)))


func swr(address: int, value: int) -> void:
	var n := address & 3
	var index := address & 0x9FFFFC
	var word := ram.decode_u32(index)
	var keep := 0x00FFFFFF >> (8 * (3 - n))
	ram.encode_u32(index, (word & keep) | (((value & 0xFFFFFFFF) << (8 * n)) & 0xFFFFFFFF))


func trace(address: int) -> void:
	trace_log.append(address)
