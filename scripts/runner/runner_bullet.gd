extends RefCounted
## Projectile of a special weapon whose shot comes from the original module: the port's shot sequence (special_shot.gd) asks the runner host to spawn it.


static func spawn(shot: Node, muzzle: Vector3, heading: Vector3, _damage: int, _range_ticks: float) -> void:
	var host: Node = shot.player.get_parent().get_node_or_null("RunnerHost")
	if host != null:
		host.fire_weapon(shot.weapon, muzzle, heading)
