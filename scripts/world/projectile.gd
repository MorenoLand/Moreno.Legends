extends Node3D
signal hit_surface(position: Vector3, normal: Vector3)
@export var speed := 15.0
@export var lifetime := 14.0 / 30.0
@export var damage := 8
@export var attack_level := 0
@export var hit_flags := 0x40000
@export var impact_texture: Texture2D
var direction := Vector3.FORWARD
var age := 0.0
var resolved := false
func _ready() -> void:
	add_to_group("projectiles")
func launch(origin: Vector3, heading: Vector3) -> void:
	global_position = origin
	direction = heading.normalized()
	$Visual.set_native_level(attack_level)
func _physics_process(delta: float) -> void:
	if resolved: return
	age += delta
	$Visual.set_native_frame(int(age * 30.0))
	if age >= lifetime:
		resolved = true
		set_physics_process(false)
		queue_free()
		return
	var destination := global_position + direction * speed * delta
	var query := PhysicsRayQueryParameters3D.create(global_position, destination, 9)
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		global_position = destination
		return
	var point: Vector3 = hit["position"]
	resolved = true
	set_physics_process(false)
	var normal: Vector3 = hit["normal"]
	var target := hit["collider"] as Node
	if target != null and target.has_method("receive_hit"): target.receive_hit(damage, hit_flags, direction)
	elif target != null and target.has_method("take_hit"): target.take_hit(damage)
	hit_surface.emit(point, normal)
	_impact(point + normal * 0.03)
	queue_free()
func _impact(position: Vector3) -> void:
	if impact_texture == null: return
	var effect := Sprite3D.new()
	effect.texture = impact_texture
	effect.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	effect.pixel_size = 0.004
	effect.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	effect.shaded = false
	get_parent().add_child(effect)
	effect.global_position = position
	var tween := effect.create_tween().set_parallel()
	tween.tween_property(effect, "scale", Vector3.ONE * 1.7, 0.16)
	tween.tween_property(effect, "modulate:a", 0.0, 0.16)
	tween.chain().tween_callback(effect.queue_free)
