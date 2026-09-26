extends Node3D
signal hit_surface(position: Vector3, normal: Vector3)
signal impact_sound_requested(sound_id: int, position: Vector3)
@export var speed := 15.0
@export var lifetime := 14.0 / 30.0
@export var damage := 8
@export var attack_level := 0
@export var hit_flags := 0x40000
const NativeImpact := preload("res://scripts/world/native_impact.gd")
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
	var actor_hit := target != null and (target.has_method("receive_hit") or target.has_method("take_hit"))
	if target != null and target.has_method("receive_hit"): target.receive_hit(damage, hit_flags, direction)
	elif target != null and target.has_method("take_hit"): target.take_hit(damage)
	hit_surface.emit(point, normal)
	_impact(point, actor_hit)
	queue_free()
func _impact(position: Vector3, actor_hit: bool) -> void:
	if actor_hit: impact_sound_requested.emit(0x9B, position)
	var effect := NativeImpact.new()
	effect.attack_level = attack_level
	effect.profile = "actor" if actor_hit else "wall"
	get_parent().add_child(effect)
	effect.global_position = position
