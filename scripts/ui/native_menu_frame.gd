extends RefCounted
static func rect(value: Array) -> Rect2:
	return Rect2(float(value[0]), float(value[1]), float(value[2]), float(value[3]))
static func coordinate(value: float, start: float, length: float, target_start: float, target_length: float) -> float:
	if value <= start + 3: return target_start + value - start
	if value >= start + length - 3: return target_start + target_length - (start + length - value)
	if value == start + floorf(length * 0.5): return target_start + floorf(target_length * 0.5)
	return target_start + (value - start) * target_length / length
static func point(word: int, from: Rect2, to: Rect2) -> Vector2:
	var x: int = word & 65535
	var y: int = (word >> 16) & 65535
	if x >= 32768: x -= 65536
	if y >= 32768: y -= 65536
	return Vector2(coordinate(x, from.position.x, from.size.x, to.position.x, to.size.x), coordinate(y, from.position.y, from.size.y, to.position.y, to.size.y))
static func color(word: int, alpha: float) -> Color:
	return Color(float(word & 255) / 255.0, float((word >> 8) & 255) / 255.0, float((word >> 16) & 255) / 255.0, alpha)
static func draw(control: Control, layout: Dictionary, key: String, rectangle: Rect2) -> void:
	var window: Dictionary = layout["windows"][key]
	var source := rect(window["body_rect"])
	for primitive: Dictionary in window["frame_primitives"]:
		var words: Array = primitive["words"]
		if str(primitive["opcode"]) == "0x32":
			var points := PackedVector2Array()
			var colors := PackedColorArray()
			for index in [0, 2, 4]:
				points.append(point(str(words[index + 1]).hex_to_int(), source, rectangle))
				colors.append(color(str(words[index]).hex_to_int(), 0.5))
			control.draw_polygon(points, colors)
		elif str(primitive["opcode"]) == "0x48":
			var points := PackedVector2Array()
			for word in words.slice(1):
				if str(word) == "0x55555555": break
				points.append(point(str(word).hex_to_int(), source, rectangle))
			control.draw_polyline(points, color(str(words[0]).hex_to_int(), 1.0), 1.0)
