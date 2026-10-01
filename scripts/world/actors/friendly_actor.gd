extends StaticBody3D
var source: Dictionary = {}
var model: Node3D
var animation_player: AnimationPlayer
var animation_clock: NativeAnimation
var clips: Dictionary = {}
var current_control := -1
func configure(entry: Dictionary, metadata: Dictionary, directory: String) -> bool:
	source = entry
	var packed := load(directory.path_join(str(entry["model_file"]))) as PackedScene
	if packed == null: return false
	model = packed.instantiate() as Node3D
	if model == null: return false
	add_child(model)
	preload("res://scripts/world/rendering/native_material.gd").apply(model, 128.0)
	var coordinates: Array = entry["transform"]["position"]
	position = Vector3(float(coordinates[0]), float(coordinates[1]), float(coordinates[2]))
	rotation.y = float(entry["transform"]["yaw_turns"]) * TAU
	var bounds: Array = entry["native_hitbox"]["bounds_raw"]
	var minimum := Vector3(-float(bounds[1]), -float(bounds[3]), float(bounds[4])) / 256.0
	var maximum := Vector3(-float(bounds[0]), -float(bounds[2]), float(bounds[5])) / 256.0
	var collision := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = maximum - minimum
	collision.shape = box
	collision.position = (maximum + minimum) * 0.5
	add_child(collision)
	collision_layer = 1
	collision_mask = 0
	clips = metadata["control_map"]
	animation_player = model.find_child("AnimationPlayer", true, false) as AnimationPlayer
	animation_clock = preload("res://scripts/world/actors/native_animation.gd").new(); animation_clock.name = "NativeAnimationClock"; add_child(animation_clock); animation_clock.configure(animation_player, metadata.get("animations", []))
	play_control(int(entry["startup_control"]["code"]) if entry.has("startup_control") else int(entry.get("native_animation_startup", {}).get("control", 0)))
	add_to_group("world_npcs")
	if entry.get("native_lock_on", null) is Dictionary: set_meta("native_lock_on", entry["native_lock_on"]); add_to_group("lock_targets")
	return true
func play_control(code: int) -> void:
	if current_control == code or animation_player == null or not clips.has(str(code)): return
	if animation_clock.play_control(code): current_control = code
