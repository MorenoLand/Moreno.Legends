extends RefCounted
## The GPU packets the original code links into its ordering table: emptied before the render phase (every slot ends the list, so the slots are read from the farthest down; the chain ClearOTagR builds between the slots is not needed), read in draw order afterwards.

const ENTRIES := 0x1000
const END := 0xFFFFFF
const TABLE_POINTER := 0x1F800048


static func clear(machine) -> void:
	var start: int = machine.u32(TABLE_POINTER) & 0x9FFFFF
	var ram: PackedByteArray = machine.ram
	for index in ENTRIES:
		ram.encode_u32(start + index * 4, END)


## Packets farthest first: polygons {vertices, colors, uvs, tpage, clut, textured, translucent, abr} and rectangles. The GPU keeps one blend mode (abr) that a draw-mode packet (0xE1) or the tpage of any textured polygon sets and untextured translucent polygons use.
static func read(machine) -> Array:
	var start: int = machine.u32(TABLE_POINTER) & 0x9FFFFF
	var slots: PackedInt32Array = machine.ram.slice(start, start + ENTRIES * 4).to_int32_array()
	var result := []
	var guard := 0
	var abr := 0
	for index in range(ENTRIES - 1, -1, -1):
		var next: int = slots[index] & 0xFFFFFF
		while next != END and guard < 6000 and next < 0x200000:
			guard += 1
			var address := next | 0x80000000
			var tag: int = machine.u32(address)
			if tag >> 24 > 0:
				var packet := _decode(machine, address)
				if packet.is_empty():
					if machine.u8(address + 7) == 0xE1:
						abr = (machine.u16(address + 4) >> 5) & 3
				else:
					if packet["textured"]:
						abr = (int(packet["tpage"]) >> 5) & 3
					packet["abr"] = abr
					result.append(packet)
			next = tag & 0xFFFFFF
	return result


static func _decode(machine, address: int) -> Dictionary:
	var command: int = machine.u8(address + 7)
	var textured := command & 4 != 0
	if command >> 5 == 1:
		var quad := command & 8 != 0
		var gouraud := command & 0x10 != 0
		var vertices: Array[Vector2] = []
		var colors: Array[Color] = []
		var uvs: Array[Vector2] = []
		var packet := {"cmd": command, "textured": textured, "translucent": command & 2 != 0, "tpage": 0, "clut": 0}
		var position := address + 4
		var color: int = machine.u32(position) & 0xFFFFFF
		for index in 4 if quad else 3:
			if gouraud and index > 0:
				color = machine.u32(position) & 0xFFFFFF
				position += 4
			elif index == 0:
				position += 4
			colors.append(Color8(color & 255, (color >> 8) & 255, (color >> 16) & 255))
			vertices.append(Vector2(machine.s16(position), machine.s16(position + 2)))
			position += 4
			if textured:
				uvs.append(Vector2(machine.u8(position), machine.u8(position + 1)))
				if index == 0:
					packet["clut"] = machine.u16(position + 2)
				elif index == 1:
					packet["tpage"] = machine.u16(position + 2)
				position += 4
		packet.merge({"vertices": vertices, "colors": colors, "uvs": uvs})
		return packet
	return {}
