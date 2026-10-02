extends Node3D
var host: Node
var radius_raw := 24
var scale_param := 0x100
var damage := 0
var remaining := 12
var elapsed := 0.0
var sprite: Sprite3D
var atlas: AtlasTexture
static func spawn(turret: Node, point: Vector3, size_param: int, hit_damage: int) -> void:
	var effect := new(); turret.get_parent().add_child(effect); effect.configure(turret.host, point, size_param, hit_damage)
static func spawn_burst(gameplay: Node, parent: Node, point: Vector3) -> void:
	var effect := new(); parent.add_child(effect); effect.configure(gameplay, point, 0, 0)
func configure(gameplay: Node, point: Vector3, size_param: int, hit_damage: int) -> void:
	host = gameplay; top_level = true; global_position = point; scale_param = size_param; damage = hit_damage
	var texture := load("res://assets/levels/ST13/effect_burst.png") as Texture2D
	atlas = AtlasTexture.new(); atlas.atlas = texture; atlas.region = Rect2(0, 0, 48, 48)
	sprite = Sprite3D.new(); sprite.texture = atlas; sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED; sprite.shaded = false; sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; sprite.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD; add_child(sprite)
	if scale_param == 0:
		radius_raw = 16; remaining = 15; sprite.pixel_size = 128.0 / 256.0 / 48.0; host.audio.play_at(0x89, point)
	else:
		radius_raw = (scale_param * 3) >> 5; remaining = 12; host.audio.play_at(0x8A, point); _render()
func _physics_process(delta: float) -> void:
	if not is_instance_valid(host) or bool(host.loading): return
	elapsed += delta * 25.0
	while elapsed >= 1.0 and is_inside_tree(): elapsed -= 1.0; _tick()
func _tick() -> void:
	if scale_param == 0:
		var frame := mini((15 - remaining) >> 1, 7); atlas.region = Rect2((frame & 3) * 48, (frame >> 2) * 48, 48, 48); remaining -= 1
		if remaining < 0: queue_free()
		return
	if remaining == 0: queue_free(); return
	radius_raw = scale_param * (0x10 - remaining) >> 5; remaining -= 1; _render()
	if damage > 0 and not bool(host.player.no_clip):
		var query := PhysicsShapeQueryParameters3D.new(); var sphere := SphereShape3D.new(); sphere.radius = float(radius_raw * 4) / 256.0; query.shape = sphere; query.transform = Transform3D(Basis.IDENTITY, global_position); query.collision_mask = host.player.collision_layer
		for hit in get_world_3d().direct_space_state.intersect_shape(query):
			if hit["collider"] == host.player: host.player.take_hit(damage, 0x20000, host.player.global_position - global_position); break
func _render() -> void:
	var frame := mini(((12 - remaining) * 8) / 13, 7); atlas.region = Rect2((frame & 3) * 48, (frame >> 2) * 48, 48, 48)
	sprite.pixel_size = float(radius_raw * 4) / 256.0 / 48.0; var fade := float(remaining) * 8.0 / 128.0; sprite.modulate = Color(fade, fade, fade, 1.0)
