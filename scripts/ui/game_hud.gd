extends Control
var textures: Dictionary = {}
var health := 80
var threat_alert := false
var max_health := 80
var trail_height := 24.0
var damage_timer := 0.0
var clock := 0.0
var special_charge := 0
var special_capacity := 0
var special_segment := 1
var special_power := 0
var special_power_max := 0
var lifter_carrying := false
var lifter_grabbing := false
var lifter_target_valid := false
var lifter_target_disabled := false
var lifter_activate_held := false
var minimap: Control
var reticle: Label
var interaction_position := Vector2.ZERO
var interaction_text := ""
var interaction_key := ""
var interaction_layout: Dictionary = {}
var interaction_font: Font
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/hud/manifest.json"))
	if not manifest is Dictionary:
		push_error("Missing extracted HUD manifest")
		return
	var sprites: Dictionary = manifest.get("sprites", {})
	for key in ["life_warning_eye", "life_pupil_frames", "life_tube_piece_a", "life_tube_piece_b", "life_tube_stretch", "special_piece_a", "special_piece_b", "special_piece_c", "special_tube_stretch"]:
		var entry: Variant = sprites.get(key)
		if entry is Dictionary: textures[key] = load("res://assets/hud/" + str(entry["file"])) as Texture2D
	for key in sprites:
		if str(key).ends_with("_alert") or str(key).begins_with("lifter_"): textures[key] = load("res://assets/hud/" + str(sprites[key]["file"])) as Texture2D
	reticle = Label.new()
	reticle.text = "+"
	reticle.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	reticle.position -= Vector2(5, 12)
	reticle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	reticle.visible = false
	add_child(reticle)
	minimap = Control.new()
	minimap.set_script(preload("res://scripts/ui/level_minimap.gd"))
	add_child(minimap)
	resized.connect(_layout_minimap)
	_layout_minimap()
	var menu: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	if menu is Dictionary:
		interaction_layout = menu["load_game_layout"]
		interaction_font = load("res://assets/menu/native_font.fnt") as Font
func set_interaction(position: Vector2, text: String, key: String = "") -> void:
	if interaction_position == position and interaction_text == text and interaction_key == key: return
	interaction_position = position; interaction_text = text; interaction_key = key; queue_redraw()
func _layout_minimap() -> void:
	if minimap == null: return
	var factor := size.y / 240.0
	minimap.position = Vector2(12, 24) * factor
	minimap.size = Vector2(72, 72) * factor
func set_area(index: int) -> void:
	if minimap != null: minimap.set_area(index)
func set_player(position: Vector3, yaw: float) -> void:
	if minimap != null: minimap.set_player(position, yaw)
func set_threat_alert(value: bool) -> void:
	if threat_alert == value: return
	threat_alert = value; queue_redraw()
func _process(delta: float) -> void:
	var pupil_rate := 30.0 if threat_alert else 7.5
	var pupil_frame := int(clock * pupil_rate) % 6
	var warning_phase := int(clock * 30) % 32
	var previous_trail := trail_height
	clock += delta
	damage_timer = maxf(damage_timer - delta, 0)
	if damage_timer <= 0: trail_height = move_toward(trail_height, _life_height(), delta * 15.0)
	if previous_trail != trail_height or pupil_frame != int(clock * pupil_rate) % 6 or (_life_height() == 0 and warning_phase != int(clock * 30) % 32) or ((lifter_target_valid or lifter_activate_held) and (int((clock - delta) * 25) & 4) != (int(clock * 25) & 4)): queue_redraw()
func _draw() -> void:
	var factor := size.y / 240.0
	if factor <= 0: return
	draw_set_transform(Vector2(0, 8) * factor, 0, Vector2.ONE * factor)
	_draw_life()
	var right := size.x / factor - 320.0
	if special_capacity > 0 and special_power_max > 0: _draw_special(right)
	else: _draw_lifter(right)
	if not interaction_text.is_empty() and interaction_font != null and not interaction_layout.is_empty():
		var key_width := interaction_font.get_string_size(interaction_key, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 8.0 if not interaction_key.is_empty() else 0.0
		var width := interaction_font.get_string_size(interaction_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 14.0 + (key_width + 4.0 if key_width > 0.0 else 0.0)
		var height := interaction_font.get_height(12) + 8.0
		var position := interaction_position / factor - Vector2(width * 0.5, height + 8.0)
		position.x = clampf(position.x, 4.0, size.x / factor - width - 4.0); position.y = clampf(position.y, 4.0, size.y / factor - height - 4.0)
		preload("res://scripts/ui/native_menu_frame.gd").draw(self, interaction_layout, "header", Rect2(position, Vector2(width, height)))
		var text_position := position + Vector2(7, 4 + interaction_font.get_ascent(12))
		if key_width > 0.0:
			var key_edge := position + Vector2(7, height - 3); draw_polyline(PackedVector2Array([key_edge + Vector2(0, -2), key_edge, key_edge + Vector2(key_width - 4, 0), key_edge + Vector2(key_width - 4, -2)]), Color8(185, 190, 208), 1.0)
			draw_string(interaction_font, text_position + Vector2(2, -2), interaction_key, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color8(255, 222, 99))
			text_position.x += key_width + 4.0
		draw_string(interaction_font, text_position, interaction_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)
func set_lifter_state(carrying: bool, grabbing: bool, target_valid: bool, target_disabled: bool, activate_held: bool) -> void:
	if lifter_carrying == carrying and lifter_grabbing == grabbing and lifter_target_valid == target_valid and lifter_target_disabled == target_disabled and lifter_activate_held == activate_held: return
	lifter_carrying = carrying; lifter_grabbing = grabbing; lifter_target_valid = target_valid; lifter_target_disabled = target_disabled; lifter_activate_held = activate_held; queue_redraw()
func _draw_lifter(right: float) -> void:
	var closed := lifter_carrying or lifter_grabbing
	var blink := (int(clock * 25.0) & 4) != 0
	var palette := "_ready" if not closed and lifter_target_valid and lifter_target_disabled else ""
	var bottom := "lifter_piece_a_closed" if closed or lifter_target_valid and blink else "lifter_piece_a"
	var claw := "lifter_piece_c_closed" if closed else "lifter_piece_c_active" if lifter_activate_held and blink else "lifter_piece_c"
	_texture(bottom + palette, Rect2(right + 282, 198, 16, 16))
	_texture("lifter_piece_b" + palette, Rect2(right + 282, 182, 16, 16))
	_texture(claw + palette, Rect2(right + (278 if closed else 274), 158, 32, 24))
func _draw_life() -> void:
	var maximum := maxi((max_health * 5) / 16 - 1, 1)
	var body := maxi(maximum - 18, 0)
	_texture("life_warning_eye", Rect2(6, 196, 32, 32))
	var pupils: Texture2D = textures.get("life_pupil_frames_alert" if threat_alert else "life_pupil_frames")
	if pupils != null: draw_texture_rect_region(pupils, Rect2(14, 205, 16, 16), Rect2((int(clock * (30.0 if threat_alert else 7.5)) % 6) * 16, 0, 16, 16))
	_texture("life_tube_piece_a", Rect2(10, 172, 24, 24))
	if body > 0: _texture("life_tube_stretch", Rect2(14, 172 - body, 16, body))
	_texture("life_tube_piece_b", Rect2(10, 148 - body, 24, 24))
	for tick in range(maxi(max_health / 16 - 1, 0)): draw_rect(Rect2(19, 174 - tick * 5, 6, 1), Color8(48, 96, 96))
	var height := _life_height()
	if height == 0:
		var phase := int(clock * 30) % 32
		var red := 127 + phase * 8 if phase <= 16 else 255 - (phase - 16) * 8
		draw_rect(Rect2(19, 179 - maximum, 6, maximum), Color8(clampi(red, 0, 255), 0, 0))
	draw_rect(Rect2(19, 179 - trail_height, 6, trail_height), Color8(140, 82, 0))
	if height > 0:
		draw_rect(Rect2(19, 179 - height, 6, height), Color8(214, 138, 74))
		draw_rect(Rect2(20, 179 - height, 4, height), Color8(255, 222, 99))
func _draw_special(right: float) -> void:
	var height := 4 * ceili(float(special_capacity) / special_segment)
	_texture("special_piece_a", Rect2(right + 282, 204, 24, 24))
	_texture("special_piece_b", Rect2(right + 286, 196, 16, 8))
	_texture("special_tube_stretch", Rect2(right + 286, 201 - height, 16, height - 5))
	_texture("special_piece_c", Rect2(right + 282, 185 - height, 24, 16))
	var segments := special_charge / special_segment
	var charged := segments * 4
	var partial := ceili(float(special_charge % special_segment) * 4 / special_segment)
	draw_rect(Rect2(right + 288, 201 - charged, 4, charged), Color8(0, 128, 0))
	draw_rect(Rect2(right + 288, 201 - charged, 3, charged), Color8(32, 240, 48))
	if partial > 0:
		draw_rect(Rect2(right + 288, 201 - charged - partial, 4, partial), Color8(0, 48, 0))
		draw_rect(Rect2(right + 288, 201 - charged - partial, 3, partial), Color8(16, 176, 16))
	var power := (special_power * height) / special_power_max
	draw_rect(Rect2(right + 294, 201 - power, 6, power), Color8(16, 48, 192))
	draw_rect(Rect2(right + 295, 201 - power, 4, power), Color8(64, 128, 240))
func _texture(key: String, rectangle: Rect2) -> void:
	var texture: Texture2D = textures.get(key + "_alert" if threat_alert and key.begins_with("life_") else key)
	if texture != null: draw_texture_rect(texture, rectangle, false)
func _life_height() -> int:
	return clampi((health * 5 + 15) / 16, 0, maxi((max_health * 5) / 16 - 1, 0))
func set_aiming(value: bool) -> void:
	if reticle != null: reticle.visible = value
func set_health(value: int, maximum: int, immediate: bool = false) -> void:
	if value == health and maximum == max_health and not immediate: return
	if value < health: damage_timer = 25.0 / 30.0
	health = value
	max_health = maximum
	if immediate: damage_timer = 0.0
	trail_height = _life_height() if immediate else clampf(trail_height, _life_height(), maxi((max_health * 5) / 16 - 1, 0))
	queue_redraw()
func set_special_energy(charge: int, capacity: int, segment: int, power: int, power_max: int) -> void:
	charge = clampi(charge, 0, capacity)
	segment = maxi(segment, 1)
	power = clampi(power, 0, power_max)
	if special_charge == charge and special_capacity == capacity and special_segment == segment and special_power == power and special_power_max == power_max: return
	special_charge = charge
	special_capacity = capacity
	special_segment = segment
	special_power = power
	special_power_max = power_max
	queue_redraw()
func pulse_buster() -> void:
	if reticle == null: return
	reticle.modulate = Color(0.4, 0.9, 1, 1)
	reticle.create_tween().tween_property(reticle, "modulate", Color.WHITE, 0.15)
