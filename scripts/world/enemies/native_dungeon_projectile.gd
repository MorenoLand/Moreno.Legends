extends Node3D
const Explosion := preload("res://scripts/world/enemies/native_dungeon_explosion.gd")
var host: Node
var yaw := 0
var lift := 0
var forward := 0
var life := 100
var exploding := false
var elapsed := 0.0
var sprite: Sprite3D
static func spawn(turret: Node, origin: Vector3, spawn_yaw: int, spawn_lift: int, spawn_forward: int) -> void:
	var projectile := new(); turret.get_parent().add_child(projectile); projectile.configure(turret.host, origin, spawn_yaw, spawn_lift, spawn_forward)
func configure(gameplay: Node, origin: Vector3, spawn_yaw: int, spawn_lift: int, spawn_forward: int) -> void:
	host = gameplay; top_level = true; global_position = origin; yaw = spawn_yaw; lift = spawn_lift; forward = spawn_forward
	var texture := load("res://assets/levels/ST13/effect_projectile.png") as Texture2D
	sprite = Sprite3D.new(); sprite.texture = texture; sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED; sprite.shaded = false; sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD; sprite.pixel_size = 40.0 / 256.0 / 24.0; add_child(sprite)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(host) or bool(host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and is_inside_tree(): elapsed -= 1.0; _tick()
func _tick() -> void:
	if exploding:
		Explosion.spawn_burst(host, get_parent(), global_position); queue_free(); return
	life -= 1; var expired := life == 0
	lift = ((lift + 0x10 + 0x8000) & 0xFFFF) - 0x8000
	var angle := float(yaw) * TAU / 4096.0; var previous := global_position; var distance := float(forward) / 16.0
	global_position += Vector3(-sin(angle) * distance, -float(lift) / 16.0, cos(angle) * distance) / 256.0
	var query := PhysicsRayQueryParameters3D.create(previous, global_position, 1); query.collide_with_areas = false
	var blocked := not get_world_3d().direct_space_state.intersect_ray(query).is_empty()
	var touched := false
	var shape_query := PhysicsShapeQueryParameters3D.new(); var sphere := SphereShape3D.new(); sphere.radius = 16.0 / 256.0; shape_query.shape = sphere; shape_query.transform = Transform3D(Basis.IDENTITY, global_position); shape_query.collision_mask = host.player.collision_layer
	for hit in get_world_3d().direct_space_state.intersect_shape(shape_query):
		if hit["collider"] == host.player: touched = true
	if touched and not bool(host.player.no_clip): host.player.take_hit(8, 0x180000, host.player.global_position - global_position)
	if expired or blocked or touched: exploding = true
