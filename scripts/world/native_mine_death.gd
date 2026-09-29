extends Node3D
signal sound_requested(sound_id: int, point: Vector3)
var random_source: Callable
var bursts: Array[Dictionary] = []
var remaining := 0
var radius := 48
var accumulator := 0.0
var texture: Texture2D
func configure(point: Vector3, radius_raw: int, ticks: int, random_callback: Callable) -> void:
	top_level = true; global_position = point; radius = radius_raw; remaining = ticks; random_source = random_callback; texture = load("res://assets/levels/ST0F/mine_death.png") as Texture2D
func _physics_process(delta: float) -> void:
	accumulator += delta
	while accumulator >= 1.0 / 25.0:
		accumulator -= 1.0 / 25.0
		if remaining > 0:
			if (remaining & 1) and bursts.size() < 4: _spawn_burst()
			remaining -= 1
		for index in range(bursts.size() - 1, -1, -1):
			var burst: Dictionary = bursts[index]; var frame := 8 - int(burst["remaining"]); var atlas := burst["atlas"] as AtlasTexture
			atlas.region = Rect2((frame & 3) * 48, (frame >> 2) * 48, 48, 48); burst["remaining"] = int(burst["remaining"]) - 1
			if int(burst["remaining"]) == 0: burst["node"].queue_free(); bursts.remove_at(index)
		if remaining == 0 and bursts.is_empty(): queue_free(); return
func _random() -> int: return int(random_source.call()) if random_source.is_valid() else 0
func _spawn_burst() -> void:
	var sprite := Sprite3D.new(); sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED; sprite.shaded = false; sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; sprite.pixel_size = 1.0 / 256.0; sprite.no_depth_test = false
	var atlas := AtlasTexture.new(); atlas.atlas = texture; atlas.region = Rect2(0, 0, 48, 48); sprite.texture = atlas
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.albedo_texture = texture; sprite.material_override = material
	sprite.position = Vector3(-((_random() & 511) - 256), -((_random() & 511) - 256), (_random() & 511) - 256) * radius / 65536.0
	var size := 64 + (_random() & 127); sprite.scale = Vector3.ONE * size / 48.0
	add_child(sprite); bursts.append({"node": sprite, "atlas": atlas, "remaining": 8}); sound_requested.emit(0x89, sprite.global_position)
