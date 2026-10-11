extends MeshInstance3D
## Flutter engine effects of the original (tools/cinematics.py export_flutter_exhaust): the GPU effect records its effect objects write, drawn as camera-facing squares. flutter_plume repeats the frames of the object attached to the hull; flutter_smoke puffs are spawned by the hull every few ticks and then drift along their own track in world space.
const MANIFEST := "res://assets/flutter/exhaust/manifest.json"
const BLENDS := {"add": BaseMaterial3D.BLEND_MODE_ADD, "sub": BaseMaterial3D.BLEND_MODE_SUB, "mix": BaseMaterial3D.BLEND_MODE_MIX}
static var manifest: Dictionary = {}
var effect: Dictionary = {}
var size := Vector2.ONE
var counter := 0
var puffs: Array[Dictionary] = []
static func available(name: String) -> bool:
	if manifest.is_empty() and FileAccess.file_exists(MANIFEST): manifest = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
	return manifest.get("effects", {}).has(name)
func configure(name: String) -> bool:
	if not available(name): return false
	effect = manifest["effects"][name]; var texture := load(MANIFEST.get_base_dir().path_join(str(effect["texture"]))) as Texture2D
	if texture == null: return false
	size = texture.get_size(); top_level = true; global_transform = Transform3D.IDENTITY; mesh = ArrayMesh.new(); cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.albedo_texture = texture; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.vertex_color_use_as_albedo = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BLENDS[str(effect["blend"])]; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.no_depth_test = effect.has("frames"); material_override = material
	return true
## Plume: value is the tick counter. Smoke: one call per native tick; the hull's own counter starts at 0 on the first call.
func native_tick(value: int) -> void:
	if not effect.has("tracks"): counter = value; return
	var parent := get_parent() as Node3D; var live: Array[Dictionary] = []
	for puff: Dictionary in puffs:
		puff["age"] += 1
		if int(puff["age"]) < (puff["track"] as Array).size(): live.append(puff)
	puffs = live
	if counter % int(effect["every"]) == 0 and parent != null:
		var yaw := roundi(-parent.rotation.y * 4096.0 / TAU); var angle := str((-yaw - ((counter << int(effect["phase_shift"])) & int(effect["phase_mask"]))) & 0xFFF)
		if effect["tracks"].has(angle): var offset: Array = effect["offset_raw"]; puffs.append({"track": effect["tracks"][angle], "age": 0, "origin": parent.global_position + Vector3(-float(offset[0]), -float(offset[1]), float(offset[2])) / 256.0})
	counter += 1
func _process(_delta: float) -> void:
	var view := get_viewport().get_camera_3d(); var parent := get_parent() as Node3D; (mesh as ArrayMesh).clear_surfaces()
	if view == null or parent == null: return
	var sprites: Array = []
	if effect.has("tracks"):
		for puff: Dictionary in puffs:
			var record: Array = puff["track"][int(puff["age"])]; sprites.append([puff["origin"] + Vector3(-float(record[0]), -float(record[1]), float(record[2])) / 256.0, record])
	elif parent.is_visible_in_tree():
		for record: Array in effect["frames"][counter % int(effect["period"])]: sprites.append([parent.to_global(Vector3(-float(record[0]), -float(record[1]), float(record[2])) / 256.0), record])
	if sprites.is_empty(): return
	var surface := SurfaceTool.new(); surface.begin(Mesh.PRIMITIVE_TRIANGLES); var right := view.global_basis.x; var up := view.global_basis.y
	for sprite: Array in sprites:
		var record: Array = sprite[1]; var turn := TAU * float(((int(record[4]) + 0x600) & 0xFFF) >> 6) / 64.0; var half := Vector2(cos(turn), sin(turn)) * float(record[3]) / 256.0; var rotated := Vector2(-half.y, half.x)
		var color := Color(minf(float(record[5]) / 127.5, 1.0), minf(float(record[6]) / 127.5, 1.0), minf(float(record[7]) / 127.5, 1.0)); var corners: Array[Vector2] = [-half, rotated, -rotated, half]
		for index: int in [0, 1, 2, 2, 1, 3]:
			surface.set_color(color); surface.set_uv(Vector2(float(record[8 + index * 2]), float(record[9 + index * 2])) / size); surface.add_vertex(sprite[0] + right * corners[index].x - up * corners[index].y)
	surface.commit(mesh as ArrayMesh)
