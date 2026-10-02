extends Node3D
const TICK := 1.0 / 30.0
const RAW_UNIT := 256.0
var frames: Array = []
var frame := 0
var elapsed := 0.0
var factor := 1.0
var pages: Dictionary = {}
var groups: Dictionary = {}
var anchors: Array[Vector3] = [Vector3.ZERO]
var looping := false
func play(effect_frames: Array, scale := 1.0, page_names: Array = []) -> void:
	frames = effect_frames; factor = scale; top_level = true
	for name: String in page_names: pages[name] = load("res://assets/player/weapons/" + name) as Texture2D
	_draw()
func _process(delta: float) -> void:
	if looping: _draw(); return
	elapsed += delta
	while elapsed >= TICK:
		elapsed -= TICK; frame += 1
		if frame >= frames.size(): queue_free(); return
	_draw()
func _group(polygon: Dictionary) -> ImmediateMesh:
	var key := "%s|%d|%s" % [polygon.get("page", ""), int(polygon["blend"]), str(polygon["semi"])]
	if not groups.has(key):
		var mesh := ImmediateMesh.new(); var instance := MeshInstance3D.new(); instance.mesh = mesh; instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		if polygon.has("page"): material.albedo_texture = pages[polygon["page"]]
		if polygon["semi"]: material.blend_mode = BaseMaterial3D.BLEND_MODE_SUB if int(polygon["blend"]) == 2 else BaseMaterial3D.BLEND_MODE_MIX if int(polygon["blend"]) == 0 else BaseMaterial3D.BLEND_MODE_ADD
		instance.material_override = material; add_child(instance); groups[key] = mesh
	return groups[key]
func _draw() -> void:
	for mesh: ImmediateMesh in groups.values(): mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d()
	if camera == null or frame >= frames.size(): return
	var right := camera.global_basis.x * factor / RAW_UNIT; var up := camera.global_basis.y * factor / RAW_UNIT; var open: Array = []
	for polygon: Dictionary in frames[frame]:
		var mesh := _group(polygon)
		if not mesh in open: mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES); open.append(mesh)
		var textured: bool = polygon.has("uvs"); var weight := 1.0 / 128.0 if textured else 1.0 / 255.0; var alpha := 0.5 if polygon["semi"] and int(polygon["blend"]) == 0 else 1.0; var light := 0.25 if polygon["semi"] and int(polygon["blend"]) == 3 else 1.0
		for index in [0, 1, 2, 1, 2, 3]:
			var vertex: Array = polygon["vertices"][index]; var color: Array = polygon["colors"][index]
			mesh.surface_set_color(Color(float(color[0]) * weight * light, float(color[1]) * weight * light, float(color[2]) * weight * light, alpha))
			if textured: mesh.surface_set_uv(Vector2(float(polygon["uvs"][index][0]) / 256.0, float(polygon["uvs"][index][1]) / 256.0))
			mesh.surface_add_vertex(anchors[mini(int(polygon.get("anchor", 0)), anchors.size() - 1)] + right * float(vertex[0]) - up * float(vertex[1]))
	for mesh: ImmediateMesh in open: mesh.surface_end()
