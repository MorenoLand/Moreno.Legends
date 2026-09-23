extends Node3D
@export_file("*.json") var manifest_path := "res://assets/levels/ST0F/manifest.json"
@onready var area_picker: OptionButton = $HUD/AreaPicker
@onready var player: CharacterBody3D = $Player
@onready var game_hud: Control = $HUD/GameHUD
var areas: Array = []
var level: Node3D
var bounds := AABB()
var spawn_position := Vector3.ZERO
var loading := false
func _ready() -> void:
	level = $Level
	player.set_physics_process(false)
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(manifest_path))
	if not manifest is Dictionary or not manifest.has("areas"):
		push_error("Missing extracted level manifest: " + manifest_path)
		return
	areas = manifest["areas"]
	for area: Dictionary in areas: area_picker.add_item("Area %02d" % int(area["index"]))
	area_picker.item_selected.connect(_select_area)
	player.health_changed.connect(game_hud.set_health)
	player.fired.connect(_on_player_fired)
	await _prepare_area()
func _select_area(index: int) -> void:
	if loading: return
	loading = true
	area_picker.disabled = true
	area_picker.select(index)
	player.set_physics_process(false)
	var scene := load(manifest_path.get_base_dir().path_join(str(areas[index]["file"]))) as PackedScene
	if scene == null:
		push_error("Cannot load extracted area")
		loading = false
		area_picker.disabled = false
		return
	for projectile in get_tree().get_nodes_in_group("buster_projectiles"): projectile.queue_free()
	remove_child(level)
	level.queue_free()
	level = scene.instantiate() as Node3D
	level.name = "Level"
	add_child(level)
	await _prepare_area()
	area_picker.disabled = false
	loading = false
func _prepare_area() -> void:
	var first := true
	for node in level.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null: continue
		var box: AABB = mesh_node.global_transform * mesh_node.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
		var body := StaticBody3D.new()
		body.collision_layer = 1
		body.collision_mask = 0
		var shape := CollisionShape3D.new()
		shape.shape = mesh_node.mesh.create_trimesh_shape()
		body.add_child(shape)
		mesh_node.add_child(body)
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not _find_spawn():
		push_error("Extracted area has no clear walkable spawn")
		return
	player.reset_at(spawn_position)
	player.set_physics_process(true)
	game_hud.set_health(player.health, player.max_health)
func _find_spawn() -> bool:
	var world := get_world_3d().direct_space_state
	var capsule: Shape3D = $Player/Collision.shape
	var closest := INF
	var found := false
	for x in range(1, 12):
		for z in range(1, 12):
			var point := Vector3(bounds.position.x + bounds.size.x * x / 12.0, bounds.end.y + 1.0, bounds.position.z + bounds.size.z * z / 12.0)
			var ray := PhysicsRayQueryParameters3D.create(point, Vector3(point.x, bounds.position.y - 1.0, point.z), 1)
			var hit := world.intersect_ray(ray)
			if hit.is_empty() or hit["normal"].y < 0.65: continue
			var foot: Vector3 = hit["position"] + Vector3.UP * 0.05
			var query := PhysicsShapeQueryParameters3D.new()
			query.shape = capsule
			query.transform = Transform3D(Basis.IDENTITY, foot + Vector3.UP * ($Player/Collision.shape as CapsuleShape3D).height * 0.5)
			query.collision_mask = 1
			query.margin = 0.01
			if not world.intersect_shape(query, 1).is_empty(): continue
			var score := foot.distance_squared_to(bounds.get_center())
			if score < closest:
				closest = score
				spawn_position = foot
				found = true
	return found
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_F: player.reset_at(spawn_position)
func _physics_process(_delta: float) -> void:
	game_hud.set_aiming(player.aiming)
	if not loading and player.global_position.y < bounds.position.y - 12.0: player.reset_at(spawn_position)
func _on_player_fired(_projectile: Node3D) -> void:
	game_hud.pulse_buster()
