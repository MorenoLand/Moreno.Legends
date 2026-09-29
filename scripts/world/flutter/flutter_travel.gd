extends Control
var accept_requested := false
var cancel_requested := false
var heading_only := false
var location_name := ""
var footer_text := ""
var heading_layout: Dictionary = {}
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
const FONT = preload("res://assets/menu/native_font.fnt")
func _input(event: InputEvent) -> void:
	if heading_only: return
	if event.is_action_pressed("ui_cancel"): cancel_requested = true; get_viewport().set_input_as_handled()
	elif event.is_action_pressed("ui_accept") or event.is_action_pressed("interact"): accept_requested = true; get_viewport().set_input_as_handled()
func _draw() -> void:
	if not heading_only: return
	var factor := size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	if not location_name.is_empty():
		var width := FONT.get_string_size(location_name, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 14.0; var rectangle := Rect2(160.0 - width * 0.5, 16, width, 23); FRAME.draw(self, heading_layout, "header", rectangle); draw_string(FONT, rectangle.position + Vector2(7, 3 + FONT.get_ascent(12)), location_name, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
	if not footer_text.is_empty():
		FRAME.draw(self, heading_layout, "prompt", Rect2(32, 184, 256, 48)); var y := 189.0 + FONT.get_ascent(12)
		for line: String in footer_text.split("\n"): draw_string(FONT, Vector2(39, y), line, HORIZONTAL_ALIGNMENT_LEFT, 242, 12, Color.WHITE); y += 16.0
static func available(host: Node3D) -> bool: return int(host.native_context.get("native_save_byte14", 0)) >= 1 or host._native_event_set(0x584)
static func choose(table: Array, host: Node3D) -> int: return int(table[2]) if table.size() > 1 and host._native_event_set(int(table[1])) else int(table[0])
static func run(host: Node3D, bypass_story: bool) -> bool:
	if not await AssetStore.ensure_stage("ST01"):
		push_error("Cannot open Flutter map: " + AssetStore.last_error); await host.dialogue_box.present_message("ST04", {"index": -1, "text": AssetStore.last_error}); return false
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/ST01/flutter_travel.json")); var story := clampi(int(host.native_context.get("native_save_byte14", 0)), 0, 18); var scenario := story if bypass_story else maxi(story, 1); var listing := choose(data["list_override"][str(scenario)], host) if data["list_override"].has(str(scenario)) else scenario; var target := choose(data["targets"][str(scenario)], host); var destinations: Array = data["scenarios"][str(maxi(listing, 1))].duplicate(true); var destination: Dictionary = {}
	if bypass_story:
		var unlocked: Array = data["scenarios"]["0"].duplicate(true)
		for available: Dictionary in destinations:
			for index in unlocked.size():
				if str(unlocked[index]["name"]) == str(available["name"]): unlocked[index] = available; break
		destinations = unlocked
	var scene := load("res://assets/levels/ST01/flutter.glb") as PackedScene
	if scene == null:
		push_error("Cannot load native Flutter world-map model"); await host.dialogue_box.present_message("ST04", {"index": -1, "text": "Unable to load the Flutter world map."}); return false
	var presentation: Control = load("res://scripts/world/flutter/flutter_travel.gd").new(); presentation.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); presentation.mouse_filter = Control.MOUSE_FILTER_STOP; host.get_node("HUD").add_child(presentation)
	var backdrop := ColorRect.new(); backdrop.color = Color.BLACK; backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); presentation.add_child(backdrop)
	var map := TextureRect.new(); map.texture = load("res://assets/levels/ST01/world_map.png"); map.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; map.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; var side: float = host.get_viewport().get_visible_rect().size.y; map.size = Vector2.ONE * side; map.position = Vector2((host.get_viewport().get_visible_rect().size.x - side) * 0.5, 0); presentation.add_child(map)
	var factor := side / 240.0; var viewport_origin := Vector2((host.get_viewport().get_visible_rect().size.x - 320.0 * factor) * 0.5, 0); map.size = Vector2.ONE * 512.0 * factor
	var view := SubViewport.new(); view.size = Vector2i(64, 64); view.transparent_bg = true; view.own_world_3d = true; view.render_target_update_mode = SubViewport.UPDATE_ALWAYS; presentation.add_child(view)
	var ship := scene.instantiate() as Node3D; view.add_child(ship); preload("res://scripts/world/rendering/native_material.gd").apply(ship, 128.0)
	var camera := Camera3D.new(); view.add_child(camera); camera.projection = Camera3D.PROJECTION_ORTHOGONAL; camera.size = 1.8; camera.position = Vector3(0, 2.5, 3.5); camera.look_at(Vector3.ZERO); camera.current = true
	var icon := TextureRect.new(); icon.texture = view.get_texture(); icon.size = Vector2.ONE * 24.0 * factor; icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; presentation.add_child(icon)
	var shadow := TextureRect.new(); shadow.texture = view.get_texture(); shadow.size = icon.size; shadow.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; shadow.modulate = Color(0, 0, 0, 0.5); presentation.add_child(shadow); presentation.move_child(shadow, icon.get_index())
	var pin_texture := load("res://assets/levels/ST01/location_pins.png") as Texture2D; var pins: Array[TextureRect] = []; var pin_shadows: Array[TextureRect] = []
	for record: Dictionary in destinations:
		var row := 0.0 if pins.size() == target else 40.0; var pin := TextureRect.new(); var atlas := AtlasTexture.new(); atlas.atlas = pin_texture; atlas.region = Rect2(0, row, 16, 24); pin.texture = atlas; pin.size = Vector2(16, 24) * factor; pin.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; pin.mouse_filter = Control.MOUSE_FILTER_IGNORE; pin.visible = pins.size() != 2; presentation.add_child(pin); pins.append(pin)
		var pin_shadow := TextureRect.new(); var shadow_atlas := AtlasTexture.new(); shadow_atlas.atlas = pin_texture; shadow_atlas.region = Rect2(0, row + 24.0, 16, 16); pin_shadow.texture = shadow_atlas; pin_shadow.size = Vector2(16, 16) * factor; pin_shadow.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; pin_shadow.mouse_filter = Control.MOUSE_FILTER_IGNORE; pin_shadow.visible = pin.visible; presentation.add_child(pin_shadow); presentation.move_child(pin_shadow, pin.get_index()); pin_shadows.append(pin_shadow)
	var heading: Control = load("res://scripts/world/flutter/flutter_travel.gd").new(); heading.set("heading_only", true); heading.set("heading_layout", JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))["load_game_layout"]); heading.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); heading.mouse_filter = Control.MOUSE_FILTER_IGNORE; presentation.add_child(heading)
	host.event_script.prepare_stage("ST01"); var saved_story: Variant = host.native_context.get("native_save_byte14", 0); host.native_context["native_save_byte14"] = scenario; var footer: Dictionary = host.event_script._resolve_program("ST01", 32); host.native_context["native_save_byte14"] = saved_story; heading.set("footer_text", "\n".join(footer.get("pages", [])) if bool(footer.get("supported", false)) and not (bypass_story and scenario == 0) else ""); heading.queue_redraw()
	var point := Vector2.ZERO
	if host.parked_location.get("map_position", null) is Array:
		var previous: Array = host.parked_location["map_position"]; point = Vector2(float(previous[0]), float(previous[1]))
	else:
		for records: Array in data["scenarios"].values():
			for record: Dictionary in records:
				if str(record["stage"]) == str(host.parked_location.get("stage", "ST08")): point = Vector2(float(record["map_position"][0]), float(record["map_position"][1])); break
	var rate := float(data["tick_rate"]); var launch := int(data["launch_ticks"]); var landing := int(data["landing_ticks"])
	map.position = viewport_origin + Vector2(-96.0 - point.x, point.y - 136.0) * factor
	for tick in launch:
		ship.position.y = float(tick + 1) / 256.0; icon.position = viewport_origin + Vector2(160, 120) * factor - icon.size * 0.5; shadow.position = icon.position + Vector2(-float(tick + 1) * 0.5, tick + 1) * factor; await host.get_tree().create_timer(1.0 / rate, false).timeout
	while destination.is_empty():
		if bool(presentation.get("cancel_requested")): presentation.queue_free(); return false
		var direction := Input.get_vector("ui_left", "ui_right", "ui_down", "ui_up") + Vector2(Input.get_axis("strafe_left", "strafe_right"), Input.get_axis("move_back", "move_forward")); var step := direction.limit_length(1.0) * 4.0; point = (point + step).clamp(Vector2(-208, -200), Vector2(208, 184))
		if not step.is_zero_approx():
			var yaw := atan2(-step.x, step.y); var difference := wrapf(yaw - ship.rotation.y, -PI, PI); ship.rotation.y += clampf(difference * 0.5, -TAU * 192.0 / 4096.0, TAU * 192.0 / 4096.0)
		map.position = viewport_origin + Vector2(-96.0 - point.x, point.y - 136.0) * factor; icon.position = viewport_origin + Vector2(160, 120) * factor - icon.size * 0.5; var nearest: Dictionary = {}
		shadow.position = icon.position + Vector2(-10, 20) * factor
		for index in destinations.size():
			var record: Dictionary = destinations[index]; pins[index].position = map.position + Vector2(256.0 + float(record["map_position"][0]), 256.0 - float(record["map_position"][1])) * factor - Vector2(8, 24) * factor; pin_shadows[index].position = pins[index].position + Vector2(0, 24) * factor; var frame := float((int(Time.get_ticks_msec() * rate / 1000.0) / 12) % 6) * 16.0; (pins[index].texture as AtlasTexture).region.position.x = frame; (pin_shadows[index].texture as AtlasTexture).region.position.x = frame
		for record: Dictionary in destinations:
			var wide := destinations.find(record) == 2
			if absf(point.x - float(record["map_position"][0])) < (52.0 if wide else 17.0) and absf(point.y - float(record["map_position"][1])) < (28.0 if wide else 13.0): nearest = record; break
		heading.set("location_name", ("Calinca   Yosyonke City" if str(nearest["stage"]) == "ST08" else str(nearest["name"])) if not nearest.is_empty() else ""); heading.queue_redraw()
		if bool(presentation.get("accept_requested")):
			presentation.set("accept_requested", false)
			if not nearest.is_empty(): destination = nearest; host.audio.play_ui("menu_confirm")
		await host.get_tree().create_timer(1.0 / rate, false).timeout
	if not await AssetStore.ensure_stage(str(destination["stage"])): presentation.queue_free(); return false
	for tick in landing: ship.position.y = float(landing - tick - 1) / 256.0; shadow.position = icon.position + Vector2(-float(landing - tick - 1) * 0.5, landing - tick - 1) * factor; await host.get_tree().create_timer(1.0 / rate, false).timeout
	host.get_node("HUD").move_child(host.transition_overlay, -1)
	await host.transition_overlay.request(0x22)
	presentation.queue_free()
	var raw: Array = destination["position_raw"]; var arrival := {"position": [float(raw[0]) / 256.0, float(raw[1]) / 256.0, float(raw[2]) / 256.0], "yaw_raw": destination["yaw_raw"]}; host.stage_transition_requested.emit({"destination_stage": destination["stage"], "destination_area": destination["area"], "destination_transform": arrival, "native_entry_fade": 2, "flutter_landing": true, "parked_location": {"stage": destination["stage"], "area": destination["area"], "arrival_transform": arrival, "map_position": destination["map_position"].duplicate()}})
	return true
