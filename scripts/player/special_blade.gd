extends "res://scripts/player/special_shot.gd"
## Blade Arm (weapon 11): the swing sequence is the original's combo handler (GAME 0x800CEC94), driven by the runner host once per original tick. This controller plays the clip of the control the handler asks for (96 to 99) at the frame the host counts, passes the presses and the tank, and ends the action when the handler does.
var control := 96
var shown_frame := -1
var held := false
func begin() -> bool:
	var host: Node = player.get_parent().get_node_or_null("RunnerHost")
	if host == null or tank < int(data["tank"]["costPerShot"]) or not player.is_on_floor(): return false
	control = int(data["combo"]["firstControl"])
	if not _play(control): return false
	var muzzle := _muzzle(); var heading: Vector3 = player.aim_heading(muzzle)
	host.combo = {"active": true, "control": control, "frame": 0, "pressed": false, "tank": tank, "cost": int(data["tank"]["costPerShot"]), "muzzle": muzzle, "heading": heading}
	shown_frame = -1; held = Input.is_action_pressed("special"); return true
func action_tick(_previous_time: float) -> void:
	var host: Node = player.get_parent().get_node_or_null("RunnerHost")
	if host == null or host.combo.is_empty(): player.special_action_time = _length(); return
	var combo: Dictionary = host.combo
	var now := Input.is_action_pressed("special")
	if now and not held: combo["pressed"] = true
	held = now
	if int(combo["control"]) != control and _play(int(combo["control"])): control = int(combo["control"]); shown_frame = -1
	tank = int(combo["tank"])
	if int(combo["frame"]) != shown_frame: shown_frame = int(combo["frame"]); _seek(minf(float(shown_frame) / 30.0, _length()))
	if combo.get("done", false): host.combo = {}; player.special_action_time = _length(); player.velocity = Vector3.ZERO; return
	_move(combo, host)
	player.special_action_time = minf(player.special_action_time, _length() - 0.002)  # the handler decides when a swing ends, not the clip
## The handler moves the player with the speeds it keeps at +0x38, +0x3A (negative is up) and +0x3C (negative is forward), in 1/4096 m per original tick; the port's player does not leave its special action state otherwise, so they are applied here through move_and_slide.
func _move(combo: Dictionary, host: Node) -> void:
	var speeds: Vector3 = combo.get("velocity", Vector3.ZERO)
	var forward: Vector3 = (combo["heading"] as Vector3) * Vector3(1.0, 0.0, 1.0)
	forward = forward.normalized() if forward.length_squared() > 0.0001 else -player.global_basis.z
	var scale: float = host.NATIVE_HZ / 4096.0
	player.velocity = forward * (-speeds.z * scale) + Vector3.UP * (-speeds.y * scale)
	player.move_and_slide()
func _length() -> float: return player.animation_player.get_animation(str(player.animation_roles["shot"])).length
func _play(id: int) -> bool:
	var clip := "%s/clip_%03d" % [data["library"], id]
	if not player.animation_player.has_animation(clip): return false
	player.animation_roles["shot"] = clip
	return player._start_special_action("shot")
func _muzzle() -> Vector3:
	var skeleton := player.upper_modifier.get_parent() as Skeleton3D
	return skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Bone_04")).origin
