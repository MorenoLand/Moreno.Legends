extends Node3D
const RAW_UNIT := 256.0
const SEGMENT_COUNT := 16
const SOURCE_COLORS := [Color8(255, 32, 32), Color8(32, 192, 32), Color8(160, 160, 32), Color8(32, 32, 255), Color8(240, 255, 16), Color8(248, 255, 8), Color8(240, 255, 16)]
const NORMAL_TEXTURE: Texture2D = preload("res://assets/effects/buster_projectile.png")
const ADDITIVE_TEXTURE: Texture2D = preload("res://assets/effects/buster_projectile_add.png")
var source_level := 0
var source_frame := 0
var normal_quad: MeshInstance3D
var additive_quad: MeshInstance3D
var source_glow: MeshInstance3D
var source_angle := 0.0
func _ready() -> void:
	normal_quad = make_quad(NORMAL_TEXTURE, Color.WHITE, BaseMaterial3D.BLEND_MODE_MIX, 1)
	add_child(normal_quad)
	additive_quad = make_quad(ADDITIVE_TEXTURE, SOURCE_COLORS[0], BaseMaterial3D.BLEND_MODE_ADD, 0)
	add_child(additive_quad)
	source_glow = make_glow()
	add_child(source_glow)
	update_source_visual()
func set_native_level(value: int) -> void:
	source_level = clampi(value, 0, 13)
	update_source_visual()
func set_native_frame(value: int) -> void:
	source_frame = value
	source_angle = TAU * float((source_frame * 128) & 0xfff) / 4096.0
	_apply_camera_orientation()

func _process(_delta: float) -> void:
	_apply_camera_orientation()

func _apply_camera_orientation() -> void:
	if not is_inside_tree(): return
	var camera := get_viewport().get_camera_3d()
	if camera == null: return
	var basis := camera.global_basis * Basis(Vector3.BACK, source_angle)
	for item in [normal_quad, additive_quad, source_glow]:
		if is_instance_valid(item): item.global_basis = basis
func make_quad(texture: Texture2D, color: Color, blend: int, priority: int) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = "AdditiveBillboard" if blend == BaseMaterial3D.BLEND_MODE_ADD else "NormalBillboard"
	var quad := QuadMesh.new()
	instance.mesh = quad
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = blend
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.albedo_texture = texture
	material.albedo_color = color
	material.render_priority = priority
	instance.material_override = material
	return instance
func make_glow() -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = "SourceGlow"
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
	material.vertex_color_use_as_albedo = true
	material.render_priority = 2
	instance.material_override = material
	return instance
func update_source_visual() -> void:
	var size := (32.0 + float(source_level * 8)) / RAW_UNIT
	var color: Color = SOURCE_COLORS[source_level >> 1]
	for item in [normal_quad, additive_quad]:
		if is_instance_valid(item): (item.mesh as QuadMesh).size = Vector2.ONE * size
	if is_instance_valid(additive_quad): (additive_quad.material_override as StandardMaterial3D).albedo_color = color
	if not is_instance_valid(source_glow): return
	var vertices := PackedVector3Array([Vector3.ZERO])
	var colors := PackedColorArray([Color.WHITE])
	var indices := PackedInt32Array()
	for index in range(SEGMENT_COUNT):
		var angle := TAU * float(index) / SEGMENT_COUNT
		vertices.append(Vector3(cos(angle) * size, sin(angle) * size, 0.0))
		colors.append(Color.BLACK)
	for index in range(SEGMENT_COUNT): indices.append_array(PackedInt32Array([0, index + 1, (index + 1) % SEGMENT_COUNT + 1]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var glow_mesh := ArrayMesh.new()
	glow_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	if is_instance_valid(source_glow):
		(source_glow.material_override as StandardMaterial3D).albedo_color = color
		source_glow.mesh = glow_mesh
