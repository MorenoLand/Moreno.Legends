extends Control
signal finished
var data: Dictionary = {}
var texture: Texture2D
var audio: Node
var fade: Control
var phase := "in"
var level := 0
var hold := 0
var native_ticks := 0.0
func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_STOP; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/hud/game_over.json"))
	if parsed is Dictionary: data = parsed; texture = load("res://assets/hud/" + str(data["textures"]["file"])) as Texture2D
	fade = preload("res://scripts/ui/common/native_fade.gd").new(); add_child(fade); fade.configure()
	if audio != null: audio.play_music("game_over_music")
func _physics_process(delta: float) -> void:
	if data.is_empty() or phase == "out": return
	native_ticks += delta
	while native_ticks >= 1.0 / float(data["tick_hz"]) and phase != "out":
		native_ticks -= 1.0 / float(data["tick_hz"])
		if phase == "in":
			level += int(data["fade_in_step"])
			if level > int(data["fade_in_max"]): level = int(data["fade_in_max"]); hold = int(data["hold_ticks"]); phase = "hold"
		else:
			hold -= 1
			if hold == 0 or _skipped(): _leave()
		queue_redraw()
func _skipped() -> bool:
	for action in ["status_menu", "jump", "interact", "ui_accept"]:
		if InputMap.has_action(action) and Input.is_action_just_pressed(action): return true
	return false
func _leave() -> void:
	phase = "out"
	await fade.request(0x20)
	if audio != null: audio.music.stop()
	finished.emit()
func _draw() -> void:
	if data.is_empty() or texture == null: return
	var native: Array = data["native_size"]; var factor := size.y / float(native[1]); var origin := Vector2((size.x - float(native[0]) * factor) * 0.5, 0)
	draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, float((level * int(data["background_blue_numerator"])) >> int(data["background_blue_shift"])) / 255.0))
	var source := 0
	for sprite: Array in data["textures"]["sprites"]:
		draw_texture_rect_region(texture, Rect2(origin + Vector2(float(sprite[0]), float(sprite[1])) * factor, Vector2(float(sprite[2]), float(sprite[3])) * factor), Rect2(source, 0, int(sprite[2]), int(sprite[3])), Color(float(level) / 128.0, float(level) / 128.0, float(level) / 128.0))
		source += int(sprite[2])
