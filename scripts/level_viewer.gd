extends Node3D
@export_file("*.json") var manifest_path := "res://assets/levels/ST0F/manifest.json"
@onready var camera: Camera3D = $Camera3D
@onready var area_picker: OptionButton = $HUD/AreaPicker
var areas: Array = []
var level: Node3D
var move_speed := 8.0
var bounds := AABB()
func _ready() -> void:
	level = $Level
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary or not manifest.has("areas"):
		push_error("Missing extracted level manifest: " + manifest_path)
		return
	areas = manifest["areas"]
	for area: Dictionary in areas: area_picker.add_item("Area %02d" % int(area["index"]))
	area_picker.item_selected.connect(_select_area)
	_frame_level()
func _select_area(index: int) -> void:
	area_picker.select(index)
	var path := manifest_path.get_base_dir().path_join(str(areas[index]["file"]))
	var scene := load(path) as PackedScene
	if scene == null:
		push_error("Cannot load extracted area: " + path)
		return
	remove_child(level)
	level.queue_free()
	level = scene.instantiate() as Node3D
	level.name = "Level"
	add_child(level)
	await get_tree().process_frame
	_frame_level()
func _frame_level() -> void:
	var first := true
	for node: Node in level.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null: continue
		var box: AABB = mesh_node.global_transform * mesh_node.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
	if first: return
	var center := bounds.get_center()
	var radius := maxf(bounds.size.length() * 0.5, 1.0)
	var direction := Vector3(1.0, 0.85, 1.0).normalized()
	camera.position = center + direction
	camera.look_at(center, Vector3.UP)
	var inverse_basis := camera.global_basis.inverse()
	var viewport_size := get_viewport().get_visible_rect().size
	var tangent := tan(deg_to_rad(camera.fov) * 0.5)
	var aspect := viewport_size.x / maxf(viewport_size.y, 1.0)
	var distance := 1.0
	for x in range(2):
		for y in range(2):
			for z in range(2):
				var corner := bounds.position + bounds.size * Vector3(x, y, z)
				var point := inverse_basis * (corner - center)
				distance = maxf(distance, point.z + maxf(absf(point.x) / (tangent * aspect), absf(point.y) / tangent))
	camera.position = center + direction * distance * 1.1
	camera.far = maxf(radius * 20.0, 200.0)
	move_speed = clampf(radius * 0.5, 3.0, 20.0)
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_RIGHT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if event.pressed else Input.MOUSE_MODE_VISIBLE
	elif event.is_action_pressed("ui_cancel"): Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		camera.rotation.y -= event.relative.x * 0.003
		camera.rotation.x = clampf(camera.rotation.x - event.relative.y * 0.003, deg_to_rad(-89), deg_to_rad(89))
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_F: _frame_level()
func _process(delta: float) -> void:
	var direction := Vector3(Input.get_axis("strafe_left", "strafe_right"), 0, Input.get_axis("move_forward", "move_back"))
	direction = camera.global_basis * direction
	direction.y += Input.get_axis("turn_left", "turn_right")
	if direction.length_squared() > 0: camera.global_position += direction.normalized() * move_speed * (4.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 1.0) * delta
