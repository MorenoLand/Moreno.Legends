extends Node3D
const RAW_UNIT := 256.0
var frame := 0
var layers: Array[MeshInstance3D] = []
func configure(sprite: Dictionary) -> void:
	var size := float(sprite["sizeRaw"]) / RAW_UNIT
	for layer in [["normal", BaseMaterial3D.BLEND_MODE_MIX, "colorNormal"], ["additive", BaseMaterial3D.BLEND_MODE_ADD, "colorAdditive"]]:
		var quad := QuadMesh.new(); quad.size = Vector2.ONE * size
		var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = layer[1]; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
		material.albedo_texture = load("res://assets/player/weapons/" + str(sprite[layer[0]])) as Texture2D; var color := int(sprite[layer[2]]); material.albedo_color = Color(float(color & 255) / 128.0, float((color >> 8) & 255) / 128.0, float(color >> 16) / 128.0)
		var instance := MeshInstance3D.new(); instance.mesh = quad; instance.material_override = material; add_child(instance); layers.append(instance)
func set_native_level(_value: int) -> void: pass
func set_native_frame(value: int) -> void:
	frame = value; _orient()
func _process(_delta: float) -> void: _orient()
func _orient() -> void:
	if not is_inside_tree() or layers.is_empty(): return
	var camera := get_viewport().get_camera_3d()
	if camera == null: return
	var basis := camera.global_basis * Basis(Vector3.BACK, float(frame & 7) * 256.0 * TAU / 4096.0)
	for layer in layers: layer.global_basis = basis
