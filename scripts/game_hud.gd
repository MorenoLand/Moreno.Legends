extends Control
var health_fill: TextureRect
var weapon: TextureRect
var health_label: Label
var fill_size := Vector2.ZERO
var reticle: Label
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/hud/manifest.json"))
	if not manifest is Dictionary:
		push_error("Missing extracted HUD manifest")
		return
	var sprites: Dictionary = manifest.get("sprites", {})
	var frame := _sprite(sprites, "health_frame", Vector2(24, 24), 3.0)
	health_fill = _sprite(sprites, "health_fill", Vector2(60, 30), 3.0)
	if health_fill != null: fill_size = health_fill.size
	health_label = Label.new()
	health_label.position = Vector2(24, (frame.size.y if frame != null else 96.0) + 30)
	health_label.add_theme_font_size_override("font_size", 16)
	health_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(health_label)
	weapon = _sprite(sprites, "buster", Vector2(24, (frame.size.y if frame != null else 96.0) + 60), 3.0)
	reticle = Label.new()
	reticle.text = "+"
	reticle.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	reticle.position -= Vector2(5, 12)
	reticle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(reticle)
func set_aiming(value: bool) -> void:
	if reticle != null: reticle.visible = value
func _sprite(sprites: Dictionary, key: String, position: Vector2, factor: float) -> TextureRect:
	var entry: Variant = sprites.get(key)
	if not entry is Dictionary or not entry.has("file"): return null
	var texture := load("res://assets/hud/" + str(entry["file"])) as Texture2D
	if texture == null: return null
	var node := TextureRect.new()
	node.texture = texture
	node.position = position
	node.size = texture.get_size() * factor
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(node)
	return node
func set_health(value: int, maximum: int) -> void:
	if health_label != null: health_label.text = "HP %d / %d" % [value, maximum]
	if health_fill == null: return
	var fraction := clampf(float(value) / maxf(maximum, 1), 0, 1)
	health_fill.size.x = fill_size.x * fraction
	health_fill.visible = value > 0
func pulse_buster() -> void:
	if weapon == null: return
	weapon.modulate = Color(2, 2, 2, 1)
	weapon.create_tween().tween_property(weapon, "modulate", Color.WHITE, 0.15)
