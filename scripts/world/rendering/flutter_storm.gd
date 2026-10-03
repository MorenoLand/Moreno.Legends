extends Node3D
# Forbidden Island storm outside the Flutter windows while it is airborne there (user-requested presentation: the ST49 capsule-scene strips and rings as a world-fixed skybox, without the screen-space wave overlay).
const SCENE_PATH := "res://assets/levels/ST49/scene_18.json"
const DIRECTORY := "res://assets/levels/ST49"
const WHITE := Color(128.0 / 255.0, 128.0 / 255.0, 128.0 / 255.0, 1.0)
const PIXELS_PER_RADIAN := 4096.0 / TAU * 0.5
const TICKS_PER_SECOND := 25.0
const SHADER := "shader_type spatial; render_mode unshaded, cull_disabled, depth_draw_never, fog_disabled, skip_vertex_transform; uniform sampler2D page: source_color, filter_nearest, repeat_enable; uniform bool view_space = false; uniform vec2 shift = vec2(0.0); void vertex() { vec3 p = view_space ? VERTEX : mat3(VIEW_MATRIX) * VERTEX; p.y += shift.y; vec4 clip = PROJECTION_MATRIX * vec4(p, 1.0); clip.z = clip.w * 0.9999; POSITION = clip; } void fragment() { vec4 pixel = texture(page, UV + vec2(shift.x, 0.0)); ALBEDO = pixel.rgb * COLOR.rgb * (255.0 / 128.0); ALPHA = pixel.a * COLOR.a; }"
var camera: Camera3D
var strips: Array[Dictionary] = []
var rings: Array[Dictionary] = []
var time := 0.0
var signature := Vector2.ZERO
var tan_x := 1.0
var tan_y := 1.0
func configure(view_camera: Camera3D) -> bool:
	camera = view_camera
	var scene: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCENE_PATH))
	if not scene is Dictionary or not is_instance_valid(camera): return false
	name = "FlutterStorm"; var priority := -100
	for actor: Dictionary in scene["branches"]["clear"]["actors"]:
		var entry: Dictionary = actor["entry"]
		if not entry.has("native_backdrop"): continue
		var profile: Dictionary = entry["native_backdrop"]; var kind := str(profile["kind"])
		if kind == "rings":
			var group := {"profile": profile, "layers": [], "phases": []}
			for layer in range(4): group["layers"].append(_surface(profile["textures"]["normal"][layer], priority, false)); group["phases"].append(float(profile["initial_phase"][layer])); priority += 1
			rings.append(group)
		elif kind == "strips":
			var texture: String = profile["textures"]["normal"]; var group := {"profile": profile, "rows": _surface(texture, priority, true), "main": _surface(texture, priority + 1, true), "drift": null}
			if int(profile["variant"]) != 5: group["drift"] = _surface(texture, priority + 2, true)
			priority += 3; strips.append(group)
	return not strips.is_empty() or not rings.is_empty()
func _surface(path: String, priority: int, view_space: bool) -> MeshInstance3D:
	var node := MeshInstance3D.new(); var material := ShaderMaterial.new(); var shader := Shader.new(); shader.code = SHADER; material.shader = shader; material.render_priority = priority
	material.set_shader_parameter("page", load(DIRECTORY.path_join(path))); material.set_shader_parameter("view_space", view_space)
	node.material_override = material; node.custom_aabb = AABB(Vector3.ONE * -1e6, Vector3.ONE * 2e6); node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; add_child(node); return node
func _quad(surface: SurfaceTool, points: Array[Vector3], uv: Array[Vector2], color: Color) -> void:
	for index: int in [0, 1, 2, 2, 1, 3]: surface.set_uv(uv[index] / 256.0); surface.set_color(color); surface.add_vertex(points[index])
func _point(x: float, y: float) -> Vector3: return Vector3((x / 160.0 - 1.0) * tan_x, (1.0 - y / 120.0) * tan_y, -1.0)
func _u(x: float) -> float: return atan((x / 160.0 - 1.0) * tan_x) * PIXELS_PER_RADIAN
func _rect(surface: SurfaceTool, x: float, y: float, width: float, height: float, u0: float, u1: float, v0: float, v1: float) -> void: _quad(surface, [_point(x, y), _point(x + width, y), _point(x, y + height), _point(x + width, y + height)], [Vector2(u0, v0), Vector2(u1, v0), Vector2(u0, v1), Vector2(u1, v1)], WHITE)
func _band(surface: SurfaceTool, y: float, height: float, v: float) -> void:
	for column in range(20): _rect(surface, column * 16.0, y, 16, height, _u(column * 16.0), _u(column * 16.0 + 16.0), v, v + height)
	for column in range(20): _rect(surface, column * 16.0, y + height, 16, 160, _u(column * 16.0), _u(column * 16.0 + 16.0), v + height - 0.5, v + height - 0.5)
func _build_strips() -> void:
	for group in strips:
		var profile: Dictionary = group["profile"]; var columns: Array = profile["strip_u"]; var lower := int(profile["variant"]) == 5
		var rows := SurfaceTool.new(); rows.begin(Mesh.PRIMITIVE_TRIANGLES)
		for row in range(columns.size() + 8):
			for column in range(20): _rect(rows, column * 16.0, float(int(profile["strip_top"]) - row * 16), 16, 16, float(columns[mini(row, columns.size() - 1)]), float(columns[mini(row, columns.size() - 1)]) + 16.0, 224, 240)
		group["rows"].mesh = rows.commit()
		var main := SurfaceTool.new(); main.begin(Mesh.PRIMITIVE_TRIANGLES); _band(main, 160.0 if lower else 80.0, 80.0 if lower else 160.0, 0.0); group["main"].mesh = main.commit()
		if group["drift"] != null: var drift := SurfaceTool.new(); drift.begin(Mesh.PRIMITIVE_TRIANGLES); _band(drift, 176.0, 64.0, 160.0); group["drift"].mesh = drift.commit()
func _build_rings(group: Dictionary, delta: float, right: Vector3, up: Vector3, orbit: float) -> void:
	var profile: Dictionary = group["profile"]
	for layer in range(4):
		group["phases"][layer] = fposmod(group["phases"][layer] + float(profile["phase_velocity"][layer]) * TICKS_PER_SECOND * delta, 4096.0)
		var surface := SurfaceTool.new(); surface.begin(Mesh.PRIMITIVE_TRIANGLES); var radius := float(profile["radii"][layer]); var half_size := float(profile["half_sizes"][layer]) / 256.0
		for segment in range(int(profile["segments"])):
			var angle: float = group["phases"][layer] + segment * int(profile["angle_step"]); var fade := 1.0
			if layer != 0: fade = clampf((absf(fposmod(orbit + 1024.0 - (4096.0 - angle) + 2048.0, 4096.0) - 2048.0) - float(profile["camera_cull_angle"])) / 128.0, 0.0, 1.0)
			if fade <= 0.0: continue
			var radians := angle * TAU / 4096.0; var center := Vector3(-cos(radians) * radius, -float(profile["heights"][layer]), sin(radians) * radius) / 256.0; var u := float(profile["u_offsets"][segment & 7]); var v := float(profile["v"])
			_quad(surface, [center - right * half_size + up * half_size, center + right * half_size + up * half_size, center - right * half_size - up * half_size, center + right * half_size - up * half_size], [Vector2(u, v), Vector2(u + 63, v), Vector2(u, v + 63), Vector2(u + 63, v + 63)], Color(WHITE.r, WHITE.g, WHITE.b, fade))
		group["layers"][layer].mesh = surface.commit()
func _process(delta: float) -> void:
	if not is_instance_valid(camera): return
	time += delta; var size := get_viewport().get_visible_rect().size; var next := Vector2(camera.fov, size.x / size.y)
	if next != signature: signature = next; tan_y = tan(deg_to_rad(camera.fov) * 0.5); tan_x = tan_y * next.y; _build_strips()
	var forward := -camera.global_basis.z; var yaw := atan2(-forward.x, -forward.z); var lift := -clampf(tan(asin(clampf(forward.y, -1.0, 1.0))), -tan_y, tan_y)
	for group in strips:
		group["rows"].material_override.set_shader_parameter("shift", Vector2(0.0, lift))
		group["main"].material_override.set_shader_parameter("shift", Vector2(fposmod((-yaw * PIXELS_PER_RADIAN - time * 1.5625) / 256.0, 1.0), lift))
		if group["drift"] != null: group["drift"].material_override.set_shader_parameter("shift", Vector2(fposmod((-yaw * PIXELS_PER_RADIAN + time * 6.25) / 256.0, 1.0), lift))
	for group in rings: _build_rings(group, delta, camera.global_basis.x, camera.global_basis.y, atan2(-forward.x, forward.z) * 4096.0 / TAU)
