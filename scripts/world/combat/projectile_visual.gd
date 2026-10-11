extends Node3D
const RAW_UNIT := 256.0
const SEGMENT_COUNT := 16
const SOURCE_COLORS := [Color8(255, 32, 32), Color8(32, 192, 32), Color8(160, 160, 32), Color8(32, 32, 255), Color8(240, 255, 16), Color8(248, 255, 8), Color8(240, 255, 16)]
const NORMAL_TEXTURE: Texture2D = preload("res://assets/effects/buster_projectile.png")
const ADDITIVE_TEXTURE: Texture2D = preload("res://assets/effects/buster_projectile_add.png")
## Materials, quad meshes and glow meshes are shared by every shot: building them per shot and compiling their shaders on first use hitches on the web build.
static var materials: Dictionary = {}
static var quad_meshes: Dictionary = {}
static var glow_meshes: Dictionary = {}
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
	instance.mesh = quad_mesh(0.0)
	instance.material_override = quad_material(texture, color, blend, priority)
	return instance
static func quad_mesh(size: float) -> QuadMesh:
	if not quad_meshes.has(size):
		var quad := QuadMesh.new()
		if size > 0.0: quad.size = Vector2.ONE * size
		quad_meshes[size] = quad
	return quad_meshes[size]
static func quad_material(texture: Texture2D, color: Color, blend: int, priority: int) -> StandardMaterial3D:
	var key := "%d|%d|%s" % [blend, priority, color.to_html()]
	if not materials.has(key):
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
		materials[key] = material
	return materials[key]
func make_glow() -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = "SourceGlow"
	return instance
static func glow_material(color: Color) -> StandardMaterial3D:
	var key := "glow|" + color.to_html()
	if not materials.has(key):
		var material := StandardMaterial3D.new()
		material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
		material.billboard_mode = BaseMaterial3D.BILLBOARD_DISABLED
		material.vertex_color_use_as_albedo = true
		material.render_priority = 2
		material.albedo_color = color
		materials[key] = material
	return materials[key]
func update_source_visual() -> void:
	var size := (32.0 + float(source_level * 8)) / RAW_UNIT
	var color: Color = SOURCE_COLORS[source_level >> 1]
	if is_instance_valid(normal_quad): normal_quad.mesh = quad_mesh(size)
	if is_instance_valid(additive_quad):
		additive_quad.mesh = quad_mesh(size)
		additive_quad.material_override = quad_material(ADDITIVE_TEXTURE, color, BaseMaterial3D.BLEND_MODE_ADD, 0)
	if is_instance_valid(source_glow):
		source_glow.mesh = glow_mesh(size)
		source_glow.material_override = glow_material(color)
static func glow_mesh(size: float) -> ArrayMesh:
	if glow_meshes.has(size): return glow_meshes[size]
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
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	glow_meshes[size] = mesh
	return mesh
## Draws one invisible shot and impact so their shaders compile before the first real shot.
static func warm(camera: Camera3D) -> void:
	var holder := Node3D.new()
	camera.add_child(holder)
	holder.position = Vector3(0, 0, -1)
	var clear := Color(1, 1, 1, 0)
	for blend: int in [BaseMaterial3D.BLEND_MODE_MIX, BaseMaterial3D.BLEND_MODE_ADD]:
		var quad := MeshInstance3D.new()
		quad.mesh = quad_mesh(0.1)
		quad.material_override = quad_material(NORMAL_TEXTURE if blend == BaseMaterial3D.BLEND_MODE_MIX else ADDITIVE_TEXTURE, clear, blend, 1)
		holder.add_child(quad)
	var glow := make_glow_static()
	glow.mesh = glow_mesh(0.1)
	glow.material_override = glow_material(clear)
	holder.add_child(glow)
	var impact := MeshInstance3D.new()
	var triangle := ArrayMesh.new()
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, 0, 0), Vector3(0.1, 0, 0), Vector3(0, 0.1, 0)])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color.BLACK, Color.BLACK, Color.BLACK])
	triangle.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	impact.mesh = triangle
	var effect := ShaderMaterial.new()
	effect.shader = preload("res://shaders/native_impact.gdshader")
	impact.material_override = effect
	holder.add_child(impact)
	await camera.get_tree().process_frame
	await camera.get_tree().process_frame
	holder.queue_free()
static func make_glow_static() -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = "SourceGlow"
	return instance
