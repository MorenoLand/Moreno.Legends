extends Node3D
var random_source: Callable
var particles: Array[Dictionary] = []
var remaining := 16
var countdown := 0
var accumulator := 0.0
var texture: Texture2D
func configure(entry: Dictionary, random_callback: Callable) -> void:
	random_source = random_callback; texture = load("res://assets/levels/ST0F/mine_smoke.png") as Texture2D
	var raw := str(entry.get("source_bytes_hex", entry.get("source_bytes", ""))).hex_decode()
	if raw.size() >= 20: remaining = raw.decode_u16(10); position = Vector3(-raw.decode_s16(12), -raw.decode_s16(14), raw.decode_s16(16)) / 256.0
	set_meta("native_effect_callback", "0x800f1e2c")
	if entry.has("source_record_ram"): set_meta("native_source_record", str(entry["source_record_ram"]))
func _random() -> int: return int(random_source.call())
func _physics_process(delta: float) -> void:
	accumulator += delta
	while accumulator >= 1.0 / 25.0:
		accumulator -= 1.0 / 25.0
		if remaining > 0:
			remaining -= 1
			if countdown == 0 and particles.size() < 14: _spawn(); countdown = 4 + (_random() & 65535) % 4
			else: countdown = maxi(countdown - 1, 0)
		for index in range(particles.size() - 1, -1, -1):
			var particle: Dictionary = particles[index]; particle["life"] = int(particle["life"]) - 1
			if int(particle["life"]) <= 0: particle["node"].queue_free(); particles.remove_at(index); continue
			var dx := int(particle["dx"]); var dz := int(particle["dz"]); var sprite := particle["node"] as Sprite3D
			sprite.position += Vector3(-signi(dx), float(5 + (_random() & 7)), 32 + signi(dz)) / 256.0
			particle["dx"] = dx - signi(dx) if dx != 0 else ((_random() >> 4) & 15) - 8; particle["dz"] = dz - signi(dz) if dz != 0 else ((_random() >> 8) & 15) - 8
			var age := 64 - int(particle["life"]); var frame := age >> 3; (particle["atlas"] as AtlasTexture).region = Rect2((frame & 3) * 48, (frame >> 2) * 48, 48, 48)
			sprite.scale = Vector3.ONE * ((age * 4 + 64) * 48 / 64.0) / 48.0
			var shade := (int(particle["life"]) * 2 + 16) / 128.0; sprite.modulate = Color(shade, shade, shade, 1)
		if remaining == 0 and particles.is_empty(): queue_free(); return
func _spawn() -> void:
	var sprite := Sprite3D.new(); sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED; sprite.pixel_size = 1.0 / 256.0; sprite.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	var atlas := AtlasTexture.new(); atlas.atlas = texture; atlas.region = Rect2(0, 0, 48, 48); sprite.texture = atlas
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA; material.blend_mode = BaseMaterial3D.BLEND_MODE_SUB; material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED; material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST; material.albedo_texture = texture; material.vertex_color_use_as_albedo = true; sprite.material_override = material
	add_child(sprite); particles.append({"node": sprite, "atlas": atlas, "life": 48 + (_random() & 15), "dx": ((_random() >> 4) & 15) - 8, "dz": ((_random() >> 8) & 15) - 8})
