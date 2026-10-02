extends Node3D
const SOURCE_WHITE := Color(128.0 / 255.0, 128.0 / 255.0, 128.0 / 255.0, 1.0)
var runtime: Node
var profile: Dictionary = {}
var surfaces: Array[MeshInstance3D] = []
var textures: Dictionary = {}
var phases: Array[int] = []
var last_yaw := 0
var phase_x := 0
var phase_y := 0
var alternate := false
func configure(scene: Node, entry: Dictionary) -> void:
	runtime = scene; profile = entry["native_backdrop"]; var point: Array = entry["position"]; position = Vector3(float(point[0]), float(point[1]), float(point[2])); last_yaw = roundi(runtime.orbit.x)
	process_priority = 1000; var count := 4 if str(profile["kind"]) == "rings" else 1
	for index in range(count):
		var node := MeshInstance3D.new(); add_child(node); surfaces.append(node); var material := ShaderMaterial.new(); var shader := Shader.new(); shader.code = "shader_type spatial; render_mode unshaded, cull_disabled, depth_draw_never%s; uniform sampler2D page: source_color, filter_nearest, repeat_disable; void fragment() { vec4 pixel = texture(page, UV); ALBEDO = pixel.rgb * COLOR.rgb * (255.0 / 128.0); ALPHA = pixel.a; }" % (", blend_add" if str(profile["kind"]) == "wave" else ""); material.shader = shader; node.material_override = material
	if str(profile["kind"]) == "wave": textures["normal"] = [load(runtime.directory.path_join(str(profile["texture"])))]
	else:
		for key: String in profile["textures"]:
			var paths: Array = profile["textures"][key] if profile["textures"][key] is Array else [profile["textures"][key]]; var pages: Array[Texture2D] = []
			for path: String in paths: pages.append(load(runtime.directory.path_join(path)))
			textures[key] = pages
	for value in profile.get("initial_phase", []): phases.append(int(value))
	if str(profile["kind"]) == "strips": phase_x = 512; phase_y = 1024
func _process(_delta: float) -> void:
	if str(profile["kind"]) != "rings" and is_instance_valid(runtime.camera): surfaces[0].global_transform = runtime.camera.global_transform
func native_tick(fields: Dictionary) -> void:
	alternate = int(fields.get("0x0C", 0)) != 0; var key := "alternate" if alternate and textures.has("alternate") else "normal"
	for index in range(surfaces.size()): (surfaces[index].material_override as ShaderMaterial).set_shader_parameter("page", textures[key][index])
	match str(profile["kind"]):
		"rings": _rings()
		"strips": _strips()
		"wave": _wave()
	last_yaw = roundi(runtime.orbit.x)
func _quad(surface: SurfaceTool, points: Array[Vector3], uv: Array[Vector2], colors: Array[Color]) -> void:
	for index: int in [0, 1, 2, 2, 1, 3]: surface.set_uv(uv[index] / 256.0); surface.set_color(colors[index]); surface.add_vertex(points[index])
func _screen_point(x: float, y: float, distance: float) -> Vector3:
	var height: float = tan(deg_to_rad(runtime.camera.fov) * 0.5) * distance; var aspect := get_viewport().get_visible_rect().size.x / get_viewport().get_visible_rect().size.y
	return Vector3((x / 160.0 - 1.0) * height * aspect, (1.0 - y / 120.0) * height, -distance)
func _rect(surface: SurfaceTool, x: float, y: float, width: float, height: float, u: float, v: float, distance: float) -> void:
	_quad(surface, [_screen_point(x, y, distance), _screen_point(x + width, y, distance), _screen_point(x, y + height, distance), _screen_point(x + width, y + height, distance)], [Vector2(u, v), Vector2(u + width, v), Vector2(u, v + height), Vector2(u + width, v + height)], [SOURCE_WHITE, SOURCE_WHITE, SOURCE_WHITE, SOURCE_WHITE])
func _sin(angle: int) -> int: return int(runtime.trig[angle & 4095][0])
func _cos(angle: int) -> int: return int(runtime.trig[angle & 4095][1])
func _rings() -> void:
	var right: Vector3 = global_basis.inverse() * runtime.camera.global_basis.x; var up: Vector3 = global_basis.inverse() * runtime.camera.global_basis.y
	for layer in range(4):
		phases[layer] = (phases[layer] + int(profile["phase_velocity"][layer])) & 4095; var surface := SurfaceTool.new(); surface.begin(Mesh.PRIMITIVE_TRIANGLES); var radius := int(profile["radii"][layer]); var half_size := float(profile["half_sizes"][layer]) / 256.0
		for segment in range(int(profile["segments"])):
			var angle := (phases[layer] + segment * int(profile["angle_step"])) & 4095; var difference := ((roundi(runtime.orbit.x) + 1024 - (4096 - angle) + 2048) & 4095) - 2048
			if layer != 0 and abs(difference) < int(profile["camera_cull_angle"]): continue
			var center := Vector3(-float((_cos(angle) * radius) >> 12), -float(profile["heights"][layer]), float((_sin(angle) * radius) >> 12)) / 256.0; var u := float(profile["u_offsets"][segment & 7]); var v := float(profile["v"])
			_quad(surface, [center - right * half_size + up * half_size, center + right * half_size + up * half_size, center - right * half_size - up * half_size, center + right * half_size - up * half_size], [Vector2(u, v), Vector2(u + 63, v), Vector2(u, v + 63), Vector2(u + 63, v + 63)], [SOURCE_WHITE, SOURCE_WHITE, SOURCE_WHITE, SOURCE_WHITE])
		surfaces[layer].mesh = surface.commit()
func _strips() -> void:
	var surface := SurfaceTool.new(); surface.begin(Mesh.PRIMITIVE_TRIANGLES); var distance: float = runtime.camera.far * 0.98
	for row in range(profile["strip_u"].size()):
		for column in range(20): _rect(surface, float(column * 16), float(int(profile["strip_top"]) - row * 16), 16, 16, float(profile["strip_u"][row]), 224, distance)
	var delta := last_yaw - roundi(runtime.orbit.x); phase_x = (phase_x + delta * 8 + 1) & 65535; phase_x = phase_x - 65536 if phase_x >= 32768 else phase_x; phase_x = 0 if phase_x >= 4096 else phase_x; var offset := (phase_x >> 4) & 31; var shift := phase_x >> 9; var lower := int(profile["variant"]) == 5
	for column in range(11): _rect(surface, float(column * 32 + offset - 32), 160.0 if lower else 80.0, 32, 80 if lower else 160, float(((column - shift) * 32) & 224), 0, distance)
	if not lower:
		phase_y = (phase_y + 1 - delta * 2) & 65535; phase_y = phase_y - 65536 if phase_y >= 32768 else phase_y; phase_y = 0 if phase_y >= 1024 else phase_y; offset = (phase_y >> 2) & 31; shift = phase_y >> 7
		for column in range(11): _rect(surface, float(column * 32 - offset), 176, 32, 64, float(((column + shift) * 32) & 224), 160, distance)
	surfaces[0].mesh = surface.commit()
func _wave() -> void:
	var flags := int(profile["flags"]); phase_x = (phase_x + int(profile["velocity"][0]) * (-1 if (flags & 1) != 0 else 1)) & 65535; phase_y = (phase_y + int(profile["velocity"][1]) * (-1 if (flags & 2) != 0 else 1)) & 65535
	var x_angle := ((phase_x - 65536 if phase_x >= 32768 else phase_x) >> 4) + roundi(runtime.orbit.x); var y_angle := ((phase_y - 65536 if phase_y >= 32768 else phase_y) >> 4) + roundi(runtime.orbit.y); var surface := SurfaceTool.new(); surface.begin(Mesh.PRIMITIVE_TRIANGLES); var distance: float = runtime.camera.near * 2.0
	for row in range(9):
		for column in range(11):
			var x := column * 32 - (x_angle & 31); var y := row * 32 - (y_angle & 31); var a := x_angle + column * 32; var b := y_angle + row * 32; var u := ((~a if (flags & 1) != 0 else a) & 96); var v := 224 - (b & 96) if (flags & 2) != 0 else 128 + (b & 96); var left := 31 if (flags & 1) != 0 else 0; var right := 0 if (flags & 1) != 0 else 31; var top := 31 if (flags & 2) != 0 else 0; var bottom := 0 if (flags & 2) != 0 else 31; var colors: Array[Color] = []
			for angle: int in [a + b, a + 32 + b, a + b + 32, a + b + 64]: var shade := float(int(profile["base"]) + ((_sin(angle) * int(profile["amplitude"])) >> 12)) / 255.0; colors.append(Color(shade, shade, shade, 1))
			_quad(surface, [_screen_point(x, y, distance), _screen_point(x + 32, y, distance), _screen_point(x, y + 32, distance), _screen_point(x + 32, y + 32, distance)], [Vector2(u + left, v + top), Vector2(u + right, v + top), Vector2(u + left, v + bottom), Vector2(u + right, v + bottom)], colors)
	surfaces[0].mesh = surface.commit()
