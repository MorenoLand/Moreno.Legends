extends Control
signal done(success: bool)
static var manifest_cache: Dictionary = {}
static var atlas_cache: Dictionary = {}
var profile: Dictionary = {}
var canvas: ColorRect
var effect: ShaderMaterial
var busy := false
var manual := false
var elapsed := 0.0
var tick := 0
var settle := 0
var shade := 0
var generation := 0
var keep_mode := false
var visual_finished := false
var atlas: Dictionary = {}
func configure(manual_tick: bool = false) -> bool:
	manual = manual_tick; process_mode = Node.PROCESS_MODE_ALWAYS; mouse_filter = Control.MOUSE_FILTER_IGNORE; set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	if manifest_cache.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/fades/manifest.json"))
		if not parsed is Dictionary: return false
		manifest_cache = parsed
	if canvas == null:
		canvas = ColorRect.new(); canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE; canvas.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); add_child(canvas); effect = ShaderMaterial.new(); effect.shader = preload("res://shaders/native_fade.gdshader"); canvas.material = effect; resized.connect(_resize)
	_resize(); hide(); return true
func _resize() -> void:
	if effect != null: effect.set_shader_parameter("display_size", size); effect.set_shader_parameter("native_size", Vector2(float(manifest_cache.get("viewport", [320, 240])[0]), float(manifest_cache.get("viewport", [320, 240])[1])))
func request(code: int, retain_mode: bool = false) -> bool:
	clear()
	if code == 0xFF: return true
	profile = manifest_cache.get("profiles", {}).get("0x%02X" % code, {})
	if profile.is_empty(): push_error("Unbound native fade code0x%02X" % code); return false
	var token := generation; keep_mode = retain_mode; tick = 0; settle = int(profile["busy_settle_ticks"]); visual_finished = false; elapsed = 0.0
	effect.set_shader_parameter("additive", str(profile.get("blend", "subtract")) == "add"); effect.set_shader_parameter("feedback", bool(profile.get("feedback", false)))
	if bool(profile.get("feedback", false)):
		atlas = manifest_cache.get("atlases", {}).get(str(profile.get("atlas", "")), {}); var path := "res://assets/fades/" + str(atlas.get("file", ""))
		if not atlas_cache.has(path):
			var atlas_texture := load(path) as Texture2D
			if atlas_texture == null: return false
			atlas_cache[path] = atlas_texture
		if not atlas_cache[path] is Texture2D: return false
		effect.set_shader_parameter("mask_atlas", atlas_cache[path]); effect.set_shader_parameter("mask_active", false); await RenderingServer.frame_post_draw
		if token != generation or not is_inside_tree(): return false
		var image := get_viewport().get_texture().get_image()
		if image == null or image.is_empty(): return false
		effect.set_shader_parameter("frozen_scene", ImageTexture.create_from_image(image)); _mask_frame(0)
	else: shade = int(profile["initial_rgb8"]); effect.set_shader_parameter("shade_rgb8", float(shade))
	busy = true; show(); return await done
func _mask_frame(index: int) -> void:
	var columns := int(atlas.get("columns", 8)); var tile: Array = atlas.get("tile_size", [320, 240]); var dimensions: Array = atlas.get("size", [2560, 1920]); effect.set_shader_parameter("atlas_rect", Vector4(float((index % columns) * int(tile[0])) / float(dimensions[0]), float(floori(float(index) / float(columns)) * int(tile[1])) / float(dimensions[1]), float(tile[0]) / float(dimensions[0]), float(tile[1]) / float(dimensions[1])))
func native_tick() -> void:
	if not busy: return
	if tick < int(profile["visible_ticks"]):
		if bool(profile.get("feedback", false)): effect.set_shader_parameter("mask_active", true); _mask_frame(tick)
		else: shade = clampi(shade + int(profile["step_rgb8"]), 0, 255); effect.set_shader_parameter("shade_rgb8", float(shade))
		tick += 1; return
	visual_finished = true
	if bool(profile.get("feedback", false)): _mask_frame(int(atlas.get("endpoint_frame", 63)))
	if keep_mode: return
	if settle > 0: settle -= 1
	if settle == 0:
		busy = false
		if str(profile.get("direction", "cover")) == "reveal": hide()
		done.emit(true)
func _process(delta: float) -> void:
	if manual or not busy: return
	elapsed += delta * float(profile.get("tick_rate", 25))
	while elapsed >= 1.0 and busy: elapsed -= 1.0; native_tick()
func is_idle() -> bool: return not busy
func is_covered() -> bool: return visible and (bool(profile.get("feedback", false)) and visual_finished or not bool(profile.get("feedback", false)) and shade == 255)
func hold(additive: bool = false) -> void:
	clear(); shade = 255; profile = {"feedback": false}; effect.set_shader_parameter("feedback", false); effect.set_shader_parameter("additive", additive); effect.set_shader_parameter("shade_rgb8", 255.0); show()
func release_mode() -> void: keep_mode = false
func clear() -> void:
	generation += 1; var interrupted := busy; busy = false; hide(); elapsed = 0.0; visual_finished = false
	if interrupted: done.emit(false)
