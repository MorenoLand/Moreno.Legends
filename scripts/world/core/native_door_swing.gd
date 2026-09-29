extends Node
signal sound_requested(sound_id: int)
const DIRECTION := -1.0
var closed_yaw := 0.0
var rate := 1.0
var ramp_ticks := 9
var angle := 0
var velocity := 0
var acceleration := 0
var state := 1
var bounces := 0
var ticks := 0
var accumulator := 0.0
func configure(yaw: float, speed: float, ramp: int) -> void:
	closed_yaw = yaw; rate = speed; ramp_ticks = ramp
func release() -> void:
	if state == 1: state = 3; velocity = angle / 17; acceleration = -2
func _physics_process(delta: float) -> void:
	accumulator += delta * rate
	while accumulator >= 1.0 / 30.0: accumulator -= 1.0 / 30.0; _tick()
	(get_parent() as Node3D).rotation.y = closed_yaw + DIRECTION * float(angle) * TAU / 4096.0
	if state == 0: set_physics_process(false)
func _tick() -> void:
	if state == 1: ticks += 1; angle = maxi(angle, 0x3C0 * mini(ticks, ramp_ticks) / ramp_ticks)
	elif state == 3:
		velocity += acceleration; angle += velocity
		if velocity < 0: state = 2; velocity = 0; acceleration = -3
	elif state == 2:
		velocity += acceleration; angle += velocity
		if angle < 0:
			angle = 0
			if bounces == 0: velocity = -(velocity >> 1); acceleration *= 7; sound_requested.emit(0xB9)
			else: state = 0
			bounces += 1
