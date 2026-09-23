extends StaticBody3D

@export var hits_remaining := 3

func _ready() -> void:
	add_to_group("lock_targets")

func take_hit() -> void:
	hits_remaining -= 1
	if hits_remaining <= 0: queue_free()
