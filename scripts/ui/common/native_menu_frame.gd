extends RefCounted
static func enter(control: Control, layout: Dictionary, context: String = "gameplay") -> bool:
	return await _animate(control, layout, "opening", context)
static func exit(control: Control, layout: Dictionary, context: String = "gameplay") -> bool:
	return await _animate(control, layout, "closing", context)
static func content_visible(control: Control) -> bool:
	var animation: Dictionary = control.get_meta("native_panel_animation", {})
	return animation.is_empty() or str(animation["phase"]) == "opening" and bool(animation["complete"])
static func _animate(control: Control, layout: Dictionary, phase: String, context: String) -> bool:
	if not is_instance_valid(control) or not control.is_inside_tree(): return false
	var source: Dictionary = layout.get("panel_animation", {})
	if source.is_empty() or not source.get("tick_rates", {}).has(context): return false
	var generation := int(control.get_meta("native_panel_generation", 0)) + 1; var windows := {}
	control.set_meta("native_panel_generation", generation)
	for key in control.get_meta("native_panel_rectangles", {}): windows[key] = _window_state(control.get_meta("native_panel_rectangles")[key], phase)
	var animation := {"phase": phase, "complete": false, "windows": windows}; control.set_meta("native_panel_animation", animation); control.queue_redraw()
	var period := 1.0 / float(source["tick_rates"][context]); var elapsed := 0.0; var previous := Time.get_ticks_usec()
	while true:
		await control.get_tree().process_frame
		if not is_instance_valid(control) or not control.is_inside_tree() or int(control.get_meta("native_panel_generation", 0)) != generation: return false
		var now := Time.get_ticks_usec(); elapsed += float(now - previous) / 1000000.0; previous = now
		if elapsed < period: continue
		elapsed = fmod(elapsed, period)
		if windows.is_empty(): continue
		var complete := true
		for window: Dictionary in windows.values():
			var target: Rect2 = window["target"]
			if target.size.x < 8.0 or target.size.y < 8.0: push_error("Native panel animation requires nonzero source byte steps"); control.remove_meta("native_panel_animation"); return false
			_advance_window(window, phase); complete = complete and int(window["state"]) == (3 if phase == "opening" else 0)
		animation["complete"] = complete; control.queue_redraw()
		if complete: return true
	return false
static func _window_state(rectangle: Rect2, phase: String) -> Dictionary:
	var target := Rect2(rectangle.position.round(), rectangle.size.round()); var step := Vector2(float((roundi(target.size.x) >> 3) & 255), float((roundi(target.size.y) >> 3) & 255))
	return {"target": target, "current": Rect2(target.position + Vector2(floorf(target.size.x * 0.5), floorf(target.size.y * 0.5)), Vector2.ZERO) if phase == "opening" else target, "step": step, "state": 1 if phase == "opening" else 3}
static func _advance_window(window: Dictionary, phase: String) -> void:
	var state := int(window["state"]); var target: Rect2 = window["target"]; var current: Rect2 = window["current"]; var step: Vector2 = window["step"]
	if phase == "opening":
		if state == 1: window["state"] = 2; return
		if state == 3: return
		current.position = (current.position - step).max(target.position); current.size += step * 2.0; current.size = current.size.min(target.size).max(Vector2(6, 6))
		if current.size == target.size: current.position = target.position; window["state"] = 3
	else:
		if state == 3: window["state"] = 4; return
		if state == 0: return
		current.position += step; current.size -= step * 2.0
		if current.size.x < 7.0 and current.size.y < 7.0: current.size = Vector2.ZERO; window["state"] = 0
		else:
			if current.size.x < 7.0: current.size.x = 6.0; step.x = 0.0
			if current.size.y < 7.0: current.size.y = 6.0; step.y = 0.0
	window["current"] = current; window["step"] = step
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
	var instance := "%s:%d:%d" % [key, roundi(rectangle.position.x), roundi(rectangle.position.y)]
	var animation: Dictionary = control.get_meta("native_panel_animation", {})
	if control.has_method("animate_enter") or not animation.is_empty():
		var rectangles: Dictionary = control.get_meta("native_panel_rectangles", {}); rectangles[instance] = rectangle; control.set_meta("native_panel_rectangles", rectangles)
	if not animation.is_empty():
		var windows: Dictionary = animation["windows"]
		if not windows.has(instance) or windows[instance]["target"] != Rect2(rectangle.position.round(), rectangle.size.round()):
			if str(animation["phase"]) == "opening" and bool(animation["complete"]): windows[instance] = _window_state(rectangle, "closing")
			else: windows[instance] = _window_state(rectangle, str(animation["phase"])); animation["complete"] = false
		rectangle = windows[instance]["current"]
		if rectangle.size.x <= 0.0 or rectangle.size.y <= 0.0: return
	for primitive: Dictionary in window["frame_primitives"]:
		var words: Array = primitive["words"]
		if str(primitive["opcode"]) == "0x32":
			var points := PackedVector2Array()
			var colors := PackedColorArray()
			for index in [0, 2, 4]:
				var word := str(words[index + 1]).hex_to_int(); var vertex := point(word, source, rectangle)
				if (word & 65535) == roundi(source.position.x): vertex.x -= 1.0
				points.append(vertex)
				colors.append(color(str(words[index]).hex_to_int(), 0.5))
			control.draw_polygon(points, colors)
		elif str(primitive["opcode"]) == "0x48":
			var points := PackedVector2Array()
			for word in words.slice(1):
				if str(word) == "0x55555555": break
				points.append(point(str(word).hex_to_int(), source, rectangle))
			control.draw_polyline(points, color(str(words[0]).hex_to_int(), 1.0), 1.0)
