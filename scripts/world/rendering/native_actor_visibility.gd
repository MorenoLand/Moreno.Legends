extends Node
var source: Node3D
var limit: int
var flags: int
var materials: Array[ShaderMaterial] = []
var shown := -1
func configure(actor: Node3D, parameters: Dictionary, actor_flags: int) -> void:
	process_mode = Node.PROCESS_MODE_PAUSABLE
	source = actor; flags = actor_flags; limit = int(parameters.get("visibility", {}).get("map_cell_ot_depth_limit", 0))
	materials.clear(); shown = -1
	for mesh: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null: continue
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material != null: materials.append(material)
	_process(0.0)
func _process(_delta: float) -> void:
	if not is_instance_valid(source) or not source.is_visible_in_tree(): return
	var camera := get_viewport().get_camera_3d()
	if camera == null: return
	var point := source.global_position; var parent := source.get_parent() as Node3D
	if parent is CharacterBody3D: point = parent.global_position
	var depth := clampi(floori(-camera.to_local(point).z * 256.0), 0, 65535) >> 2
	var visible := limit <= 0 or ((flags & 0x40) != 0 and depth < limit)
	if not visible and depth >= 16 and depth <= limit:
		var viewport_size := get_viewport().get_visible_rect().size; var screen := camera.unproject_position(point) / viewport_size * Vector2(320.0, 240.0)
		visible = screen.x >= -352.0 and screen.x <= 672.0 and screen.y >= -136.0 and screen.y <= 888.0
	if int(visible) == shown: return
	shown = int(visible)
	for material in materials: material.set_shader_parameter("native_actor_visible", visible)
