extends RefCounted
## Kernel A0 table functions of the PlayStation BIOS (C library) the original code calls through the SLES stubs at 0x80067624..0x80067694.

var machine
var R: PackedInt32Array
var ram: PackedByteArray
var rand_seed := 1


## A0 0x28 bzero(destination, count)
func h_80067654() -> void:
	var start := R[4] & 0x9FFFFF
	for index in R[5]:
		ram[start + index] = 0


## A0 0x2A memcpy(destination, source, count)
func h_80067664() -> void:
	var to := R[4] & 0x9FFFFF
	var from := R[5] & 0x9FFFFF
	for index in R[6]:
		ram[to + index] = ram[from + index]
	R[2] = R[4]


## A0 0x2B memset(destination, value, count)
func h_80067674() -> void:
	var start := R[4] & 0x9FFFFF
	for index in R[6]:
		ram[start + index] = R[5] & 255
	R[2] = R[4]


## A0 0x2F rand: the kernel's linear congruential generator.
func h_80067684() -> void:
	rand_seed = (rand_seed * 0x41C64E6D + 0x3039) & 0xFFFFFFFF
	R[2] = (rand_seed >> 16) & 0x7FFF


## A0 0x17 strcmp(a, b)
func h_80067634() -> void:
	var left := R[4] & 0x9FFFFF
	var right := R[5] & 0x9FFFFF
	var difference := 0
	while difference == 0:
		difference = ram[left] - ram[right]
		if ram[left] == 0:
			break
		left += 1
		right += 1
	R[2] = difference


## A0 0x18 strncmp(a, b, count)
func h_80067644() -> void:
	var left := R[4] & 0x9FFFFF
	var right := R[5] & 0x9FFFFF
	var difference := 0
	for index in R[6]:
		difference = ram[left + index] - ram[right + index]
		if difference != 0 or ram[left + index] == 0:
			break
	R[2] = difference


## A0 0x3F printf: console output is not kept.
func h_80067694() -> void:
	R[2] = 0
