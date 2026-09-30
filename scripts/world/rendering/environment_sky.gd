extends Node
var environment: Environment
var previous_background := Environment.BG_COLOR
var previous_sky: Sky
var material: ShaderMaterial
var sky: Sky
var flying := false
func configure(view_camera: Camera3D, view_environment: Environment) -> bool:
	environment = view_environment
	if not is_instance_valid(view_camera) or environment == null: return false
	set_meta("sky_profile", "flight_cloud_layer")
	var path := "res://assets/opening/effects/ST02/atmosphere_1_primary.png"
	if not ResourceLoader.exists(path, "Texture2D"): push_error("Missing flight cloud texture: " + path); return false
	previous_background = environment.background_mode; previous_sky = environment.sky
	material = ShaderMaterial.new(); material.shader = preload("res://shaders/environment_sky.gdshader"); material.set_shader_parameter("sky_zenith", Vector3(157.0 / 255.0, 166.0 / 255.0, 198.0 / 255.0)); material.set_shader_parameter("sky_mid", Vector3(160.0 / 255.0, 173.0 / 255.0, 199.0 / 255.0)); material.set_shader_parameter("sky_horizon", Vector3(160.0 / 255.0, 173.0 / 255.0, 193.0 / 255.0))
	material.set_shader_parameter("cloud_texture", load(path))
	sky = Sky.new(); sky.radiance_size = Sky.RADIANCE_SIZE_32; sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL; sky.sky_material = material
	set_flying(true); return true
func set_flying(value: bool) -> void:
	flying = value
	if environment == null or sky == null: return
	environment.background_mode = Environment.BG_SKY if flying else previous_background; environment.sky = sky if flying else previous_sky
func _exit_tree() -> void:
	if environment != null and environment.sky == sky: environment.background_mode = previous_background; environment.sky = previous_sky
func set_fog(enabled: bool, native_depth_queue: Dictionary = {}) -> void:
	if environment == null: return
	environment.fog_enabled = enabled
	if not enabled: return
	environment.fog_mode = Environment.FOG_MODE_DEPTH
	environment.fog_depth_begin = 12.0
	environment.fog_depth_end = 28.0
	environment.fog_depth_curve = 1.0
	environment.fog_density = 1.0
	environment.fog_light_color = Color(160.0 / 255.0, 173.0 / 255.0, 193.0 / 255.0)
	var setup: Dictionary = native_depth_queue.get("rational_setup", {})
	if not setup.is_empty():
		# GTE depth queue: IR0 = dqb / 2^24 + dqa * h / (65536 * depth), clamped to 0..1, blended toward the far colour.
		var dqa := float(setup["dqa"]); var dqb := float(setup["dqb"]) / 16777216.0; var scale := dqa * float(setup["reference_h"]) / 65536.0
		var begin := -scale / dqb if dqb != 0.0 else 0.0
		var finish := scale / (1.0 - dqb) if dqb != 1.0 else begin + 1.0
		var rgb: Array = native_depth_queue.get("far_rgb", [0, 0, 0])
		var middle := (begin + finish) * 0.5
		environment.fog_depth_begin = begin
		environment.fog_depth_end = finish
		environment.fog_depth_curve = log(clampf(dqb + scale / middle, 0.001, 0.999)) / log(0.5)
		environment.fog_light_color = Color(float(rgb[0]) / 255.0, float(rgb[1]) / 255.0, float(rgb[2]) / 255.0)
	environment.fog_light_energy = 1.0
	environment.fog_sky_affect = 0.0
	environment.fog_height_density = 0.0
	environment.fog_sun_scatter = 0.0
