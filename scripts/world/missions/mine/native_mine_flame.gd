extends MeshInstance3D
var native_radius := 115
var native_height := 66
var emit_interval := 3
var countdown := 3
var tick := 0
var accumulator := 0.0
var rising: Array[Dictionary] = []
func configure(entry: Dictionary, _metadata: Dictionary = {}, _directory: String = "") -> void:
	var raw := str(entry.get("source_bytes_hex", entry.get("source_bytes", ""))).hex_decode()
	if raw.size() >= 20:
		native_radius = raw.decode_s16(8); native_height = raw[10] if raw[10] < 128 else raw[10] - 256; emit_interval = raw[11] if raw[11] < 128 else raw[11] - 256; countdown = emit_interval
		position = Vector3(-raw.decode_s16(12), -raw.decode_s16(14), raw.decode_s16(16)) / 256.0
	mesh = ImmediateMesh.new()
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.albedo_texture = load("res://assets/levels/ST0F/mine_flame.png"); material.vertex_color_use_as_albedo = true; material_override = material
	set_meta("native_source_record", str(entry.get("source_record_ram", "0x80100864")))
func _physics_process(delta: float) -> void:
	accumulator += delta
	while accumulator >= 1.0 / 25.0:
		accumulator -= 1.0 / 25.0; tick += 1
		if countdown == 0: rising.append({"tick": 0, "remaining": int(native_height * 8 / 48), "y": 0.0}); countdown = emit_interval
		else: countdown -= 1
		for index in range(rising.size() - 1, -1, -1):
			var flame: Dictionary = rising[index]; flame["tick"] = int(flame["tick"]) + 1; flame["remaining"] = int(flame["remaining"]) - 1; flame["y"] = float(flame["y"]) + 48.0 / 256.0
			if int(flame["remaining"]) <= 0: rising.remove_at(index)
		_redraw()
func _redraw() -> void:
	var geometry := mesh as ImmediateMesh; geometry.clear_surfaces(); geometry.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	_cylinder(geometry, native_radius, 0, 16)
	for flame: Dictionary in rising: _cylinder(geometry, native_radius + 92, float(flame["y"]), int(flame["remaining"]))
	geometry.surface_end()
func _cylinder(geometry: ImmediateMesh, radius: int, y: float, remaining: int) -> void:
	for layer in range(8):
		var scroll := posmod(tick * 12 + 64 - layer * 32, 96); var bottom := y + float(layer * native_height) / 256.0; var top := bottom + native_height / 256.0
		var shade := minf(float(remaining) / 8.0, 1.0) * (0.5 if layer < 4 else 1.0 - float(layer - 4) / 8.0)
		for sector in range(16):
			var first := sector * TAU / 16.0; var second := first + TAU / 16.0
			var points := [Vector3(sin(first) * radius / 256.0, bottom, cos(first) * radius / 256.0), Vector3(sin(first) * radius / 256.0, top, cos(first) * radius / 256.0), Vector3(sin(second) * radius / 256.0, top, cos(second) * radius / 256.0), Vector3(sin(second) * radius / 256.0, bottom, cos(second) * radius / 256.0)]
			var uvs := [Vector2(0, (scroll + 31.0) / 128.0), Vector2(0, scroll / 128.0), Vector2(1, scroll / 128.0), Vector2(1, (scroll + 31.0) / 128.0)]
			for vertex in [0, 1, 2, 0, 2, 3]: geometry.surface_set_color(Color(shade, shade, shade, 1)); geometry.surface_set_uv(uvs[vertex]); geometry.surface_add_vertex(points[vertex])
