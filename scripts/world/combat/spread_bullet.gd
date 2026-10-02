extends "res://scripts/world/combat/projectile.gd"
var data: Dictionary = {}
static func spawn(shot: Node, muzzle: Vector3, heading: Vector3, damage: int, lifetime: float) -> void:
	var special: bool = shot.level(4) > 0; var bullet: Dictionary = shot.data["bullet"]; var children := int(bullet["children"]["base"]) + (int(bullet["children"]["perSpecialFactor"]) if special else 0)
	for index in range(children + 1):
		var node := Node3D.new(); node.set_script(shot.bullet_script); node.set("data", shot.data); node.set("damage", damage); node.set("lifetime", lifetime / 30.0); node.set("speed", float(bullet["speedRaw"]) * float(bullet["substepsPerTick"]) * 30.0 / 4096.0); shot.player.get_parent().add_child(node)
		node.launch(muzzle, heading.rotated(Vector3.UP, -float((index - 1 - (1 if special else 0)) << int(bullet["yawStepShift"])) * TAU / 4096.0))
func _ready() -> void:
	super()
	var visual := Node3D.new(); visual.name = "Visual"; visual.set_script(preload("res://scripts/world/combat/spread_bullet_visual.gd")); add_child(visual); visual.configure(data["bullet"]["sprite"])
func _impact(point: Vector3, _actor_hit: bool) -> void:
	var effect := Node3D.new(); effect.set_script(preload("res://scripts/world/combat/native_effect.gd")); get_parent().add_child(effect); effect.global_position = point; var variants: Array = data["impact"]["variants"]; effect.play(variants[randi() % variants.size()])
