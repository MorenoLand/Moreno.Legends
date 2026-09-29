extends StaticBody3D
func _physics_process(_delta: float) -> void:
	var layer := 64 if is_visible_in_tree() else 0
	if collision_layer != layer: collision_layer = layer
