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
	if not FileAccess.file_exists(path): return false
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
	if environment != null: environment.background_mode = previous_background; environment.sky = previous_sky
