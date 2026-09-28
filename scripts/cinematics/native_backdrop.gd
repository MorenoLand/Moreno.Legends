extends MeshInstance3D
var offset := Vector2i.ZERO
var velocity := Vector2i.ZERO
var material: ShaderMaterial
func configure(texture: Texture2D) -> void:
	material = ShaderMaterial.new(); material.shader = preload("res://shaders/native_backdrop.gdshader"); material.set_shader_parameter("page", texture); material.set_shader_parameter("depth", (get_parent() as Camera3D).far * 0.999)
	var quad := QuadMesh.new(); quad.size = Vector2(2, 2); quad.material = material; mesh = quad; extra_cull_margin = 16384.0; cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; visible = false
func set_state(action: Dictionary) -> void:
	visible = bool(action["enabled"]); velocity = Vector2i(int(action["velocity_raw"][0]), int(action["velocity_raw"][1]))
	if visible: offset = Vector2i(int(action["offset_raw"][0]), int(action["offset_raw"][1])); _apply()
func native_tick() -> void:
	if not visible: return
	offset = Vector2i((offset.x + velocity.x) & 0xFFFF, (offset.y + velocity.y) & 0xFFFF); _apply()
func _apply() -> void:
	material.set_shader_parameter("origin", Vector2(((offset.x >> 4) & 0x7F) - 0x160, ((offset.y >> 4) & 0xFF) - 0x188))
