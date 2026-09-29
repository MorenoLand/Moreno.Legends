extends Node3D
const EFFECT_SHADER := preload("res://shaders/native_impact.gdshader")
static var native_rng_state := 0
static var source_data: Dictionary = {}
var attack_level := 0
var profile := "wall"
var remaining := 6
var accumulator := 0.0
var spark_selectors := PackedInt32Array()
var passes: Array[MeshInstance3D] = []
func _ready() -> void:
	if source_data.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/effects/impact.json"))
		if not parsed is Dictionary: set_process(false); queue_free(); return
		source_data = parsed
	remaining = int(source_data["countdown_ticks"])
	if profile == "actor":
		for index in range(int(source_data["profiles"]["actor"]["radial_sparks"])): spark_selectors.append((_random() & 63) | ((_random() & 3) << 6))
	for index in range(3):
		var instance := MeshInstance3D.new()
		instance.mesh = ArrayMesh.new()
		var effect_material := ShaderMaterial.new()
		effect_material.shader = EFFECT_SHADER
		instance.material_override = effect_material
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(instance)
		passes.append(instance)
static func _random() -> int:
	native_rng_state = (((native_rng_state << 1) + (native_rng_state >> 31) + 1) ^ 0x873CA9E5) & 0xFFFFFFFF
	return native_rng_state
func _process(delta: float) -> void:
	accumulator += delta
	var interval := 1.0 / float(source_data.get("tick_rate", 25))
	if accumulator < interval: return
	accumulator = fmod(accumulator, interval)
	if remaining <= 0: queue_free(); return
	_render_frame()
	remaining -= 1
func _color(multiplier: int) -> Color:
	var table: Array = source_data["colors_rgb"]
	var rgb: Array = table[clampi(attack_level >> 1, 0, table.size() - 1)]
	return Color(float((int(rgb[0]) * multiplier) >> 8) / 255.0, float((int(rgb[1]) * multiplier) >> 8) / 255.0, float((int(rgb[2]) * multiplier) >> 8) / 255.0).srgb_to_linear()
func _point(index: int, radius: int) -> Vector3:
	var trig: Array = source_data["trig64"][index & 63]
	return Vector3((int(trig[0]) * radius) >> 12, -((int(trig[1]) * radius) >> 12), 0) / float(source_data["source"]["world_unit_raw"])
func _set_pass(index: int, vertices: PackedVector3Array, colors: PackedColorArray, indices: PackedInt32Array, sorting_radius: float) -> void:
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := passes[index].mesh as ArrayMesh
	mesh.clear_surfaces()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var radius := 0.0
	for vertex in vertices: radius = maxf(radius, vertex.length())
	passes[index].custom_aabb = AABB(Vector3.ONE * -radius, Vector3.ONE * radius * 2)
	(passes[index].material_override as ShaderMaterial).set_shader_parameter("sorting_bias", sorting_radius * 0.5)
func _circle_pass(index: int, first_radius: int, second_radius: int, first_color: Color, second_color: Color) -> void:
	var vertices := PackedVector3Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	var start := int(source_data["circle_start_index"])
	var step := int(source_data["circle_index_step"])
	for segment in range(int(source_data["circle_segments"])):
		var first := vertices.size()
		var angle := start + segment * step
		vertices.append_array(PackedVector3Array([_point(angle, first_radius), _point(angle, second_radius), _point(angle + step, first_radius), _point(angle + step, second_radius)]))
		colors.append_array(PackedColorArray([first_color, second_color, first_color, second_color]))
		indices.append_array(PackedInt32Array([first, first + 1, first + 2, first + 1, first + 2, first + 3]))
	_set_pass(index, vertices, colors, indices, float(maxi(first_radius, second_radius)) / 256.0)
func _render_frame() -> void:
	var maximum := int(source_data["radius_base_raw"]) + attack_level * int(source_data["radius_level_multiplier"])
	var radius := (maximum * (12 - remaining)) >> 4
	var black := Color.BLACK
	if profile == "wall":
		var width := int(source_data["ring_width_raw"])
		var weak := _color(remaining << 4)
		_circle_pass(0, radius, radius - width, weak, black)
		_circle_pass(1, radius, radius + width, weak, black)
		_circle_pass(2, 0, radius - width, _color(remaining << 5), black)
		return
	var brightness := mini(255, (remaining << 6) + 15)
	var white := Color(float(brightness) / 255.0, float(brightness) / 255.0, float(brightness) / 255.0).srgb_to_linear()
	_circle_pass(0, 0, radius >> 1, white, black)
	_circle_pass(1, 0, radius, _color(brightness), black)
	var vertices := PackedVector3Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	var spark_color := _color(brightness >> 1)
	var last_spark_radius := 0
	for selector in spark_selectors:
		var outer := (maximum * ((selector >> 6) + 4) * (8 - remaining)) >> 5
		var inner := outer >> 4
		var angle := selector & 63
		var first := vertices.size()
		vertices.append_array(PackedVector3Array([_point(angle - 8, inner), _point(angle, outer), _point(angle + 8, outer), _point(angle + 8, inner)]))
		colors.append_array(PackedColorArray([black, black, spark_color, black]))
		indices.append_array(PackedInt32Array([first, first + 1, first + 2, first + 1, first + 2, first + 3]))
		last_spark_radius = outer
	_set_pass(2, vertices, colors, indices, float(last_spark_radius) / 256.0)
