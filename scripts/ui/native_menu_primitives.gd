extends RefCounted
static func patches(control: Control, texture: Texture2D, target: Rect2, definition: Dictionary) -> void:
	var margin: Array = definition["margin"]; var regions: Array = definition["patches"]; var widths := [float(margin[0]), maxf(0.0, target.size.x - float(margin[0]) * 2.0), float(margin[0])]; var heights := [float(margin[1]), maxf(0.0, target.size.y - float(margin[1]) * 2.0), float(margin[1])]; var positions_x := [target.position.x, target.position.x + float(margin[0]), target.end.x - float(margin[0])]; var positions_y := [target.position.y, target.position.y + float(margin[1]), target.end.y - float(margin[1])]
	for row in 3:
		for column in 3:
			var region: Array = regions[row * 3 + column]
			if widths[column] > 0.0 and heights[row] > 0.0: control.draw_texture_rect_region(texture, Rect2(positions_x[column], positions_y[row], widths[column], heights[row]), Rect2(region[0], region[1], region[2], region[3]))
static func nine_patch(control: Control, texture: Texture2D, target: Rect2, source: Rect2, margin: float = 8.0) -> void:
	var widths := [margin, target.size.x - margin * 2, margin]
	var heights := [margin, target.size.y - margin * 2, margin]
	var source_widths := [margin, source.size.x - margin * 2, margin]
	var source_heights := [margin, source.size.y - margin * 2, margin]
	var y := target.position.y
	var sy := source.position.y
	for row in range(3):
		var x := target.position.x
		var sx := source.position.x
		for column in range(3):
			control.draw_texture_rect_region(texture, Rect2(x, y, widths[column], heights[row]), Rect2(sx, sy, source_widths[column], source_heights[row]))
			x += widths[column]; sx += source_widths[column]
		y += heights[row]; sy += source_heights[row]
static func rectangle(packet: Dictionary) -> Rect2:
	if str(packet["opcode"]) == "0x64": return Rect2(Vector2(packet["xy"][0], packet["xy"][1]), Vector2(packet["size"][0], packet["size"][1]))
	var points: Array = packet["xy"]
	return Rect2(Vector2(points[0][0], points[0][1]), Vector2(points[3][0] - points[0][0], points[3][1] - points[0][1]))
static func draw(control: Control, packets: Array, atlases: Dictionary, skipped: Array = [], palettes: Dictionary = {}) -> void:
	for index in range(packets.size()):
		if index in skipped: continue
		var packet: Dictionary = packets[index]
		if str(packet["opcode"]) not in ["0x64", "0x2c"]: continue
		var page := int(str(packet["tpage"]).hex_to_int()) & 31
		var clut := int(str(packet["clut"]).hex_to_int())
		if palettes.has(index): clut = int(palettes[index])
		var texture: Texture2D = atlases.get("%d:%d" % [page, clut])
		if texture == null: continue
		var target := rectangle(packet)
		var source := Rect2()
		if str(packet["opcode"]) == "0x64": source = Rect2(Vector2(packet["uv"][0], packet["uv"][1]), target.size)
		else:
			var uv: Array = packet["uv"]
			source = Rect2(Vector2(uv[0][0], uv[0][1]), Vector2(uv[3][0] - uv[0][0] + 1, uv[3][1] - uv[0][1] + 1))
		control.draw_texture_rect_region(texture, target, source)
