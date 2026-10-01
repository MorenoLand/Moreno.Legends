extends Sprite3D
static var source_data: Dictionary = {}
static var random_state := 0
var frames: Array = []
var effect_frame := 0
var ticks := 0
var size_raw := 0
var accumulator := 0.0
var host: Node
var material: StandardMaterial3D
static func data() -> Dictionary:
	if source_data.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/levels/ST11/icefield_effects.json"))
		if parsed is Dictionary: source_data = parsed
	return source_data
static func random() -> int: random_state = (((random_state << 1) + (random_state >> 31) + 1) ^ 0x873CA9E5) & 0xFFFFFFFF; return random_state
func configure(gameplay: Node, point: Vector3, size: int) -> void:
	host = gameplay; size_raw = size; top_level = true; global_position = point; frames = data().get("dust", {}).get("frames", []); billboard = BaseMaterial3D.BILLBOARD_ENABLED; shaded = false; texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	material = StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material_override = material; _frame()
func _frame() -> void:
	if effect_frame >= frames.size(): queue_free(); return
	var row: Dictionary = frames[effect_frame]; var color: Array = row["rgb"]; texture = load("res://assets/levels/ST11/" + str(row["texture"])) as Texture2D; material.albedo_texture = texture; material.albedo_color = Color(float(color[0]) / 128.0, float(color[1]) / 128.0, float(color[2]) / 128.0); pixel_size = sqrt(2.0) * float(size_raw + int(row["size_add_raw"])) / (256.0 * float(texture.get_width())); ticks = int(row["duration_ticks"])
func _physics_process(delta: float) -> void:
	if not is_instance_valid(host) or bool(host.loading) or not host.player.is_physics_processing(): return
	accumulator += delta * 25.0
	while accumulator >= 1.0 and not is_queued_for_deletion():
		accumulator -= 1.0; ticks -= 1
		if ticks == 0: effect_frame += 1; _frame()
