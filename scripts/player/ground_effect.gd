extends MeshInstance3D
static var data: Dictionary
static var ring_material: StandardMaterial3D
var tick := 1
var spin := 0
var accumulator := 0.0
func _ready() -> void:
	if data.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/effects/landing_ring.json")) if FileAccess.file_exists("res://assets/player/effects/landing_ring.json") else null
		if not (parsed is Dictionary): queue_free(); return
		data = parsed; ring_material = StandardMaterial3D.new(); ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; ring_material.vertex_color_use_as_albedo = true; ring_material.cull_mode = BaseMaterial3D.CULL_DISABLED; ring_material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; ring_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; ring_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; ring_material.albedo_texture = load("res://assets/player/effects/" + str(data["texture"])) as Texture2D
	mesh = ImmediateMesh.new(); material_override = ring_material; cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; spin = int(Time.get_ticks_msec() * 0.03) & 63; _draw()
func _physics_process(delta: float) -> void:
	accumulator += delta * 30.0
	if accumulator < 1.0: return
	while accumulator >= 1.0: accumulator -= 1.0; tick += 1; spin += 1
	if tick >= int(data["lifeTicks"]["value"]): queue_free(); return
	_draw()
func _draw() -> void:
	var life := int(data["lifeTicks"]["value"]); var size := int(data["sizeRaw"]["value"]) * tick / life; var shade := float(8 * (life - tick)) / 128.0; var geometry: Dictionary = data["ringGeometry"]; var uv: Array = data["textureSource"]["uv"]
	var step := int(geometry["angleStep"]); var stride := float(geometry["uStride"]) / float(uv[2]); var span := float(geometry["uSpan"]) / float(uv[2]); var inner_v := float(int(uv[3]) - 1) / float(uv[3]); var rings: Array = data["rings"]
	var radii := [[size, (3 * size) >> 2], [(3 * size) >> 2, size >> 1]]; var immediate := mesh as ImmediateMesh; immediate.clear_surfaces(); immediate.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in 2:
		var ring: Dictionary = rings[index]; var outer := float(radii[index][0]); var inner := float(radii[index][1]); var outer_elevation := float(ring["outerElevation"]) * TAU / 64.0; var inner_elevation := float(ring["innerElevation"]) * TAU / 64.0
		for segment in int(geometry["segments"]):
			var start := spin + segment * step; var u := stride * float(((start + step) / step) & int(geometry["uRepeatMask"]))
			var corners := [_point(inner, inner_elevation, start), _point(outer, outer_elevation, start), _point(inner, inner_elevation, start + step), _point(outer, outer_elevation, start + step)]; var uvs := [Vector2(u, inner_v), Vector2(u, 0.0), Vector2(u + span, inner_v), Vector2(u + span, 0.0)]; var colors := [Color.BLACK, Color(shade, shade, shade), Color.BLACK, Color(shade, shade, shade)]
			for corner in [0, 1, 2, 1, 2, 3]: immediate.surface_set_color(colors[corner]); immediate.surface_set_uv(uvs[corner]); immediate.surface_add_vertex(corners[corner])
	immediate.surface_end()
func _point(radius: float, elevation: float, angle: int) -> Vector3:
	var turn := float(angle & 63) * TAU / 64.0; var flat := radius * cos(elevation)
	return Vector3(-flat * cos(turn), -radius * sin(elevation) + 1.0, flat * sin(turn)) / 256.0
