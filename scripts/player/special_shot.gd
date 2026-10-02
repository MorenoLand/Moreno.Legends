extends Node3D
signal gauge_changed(charge: int, capacity: int, segment: int, power: int, power_max: int)
const TICK := 1.0 / 30.0
const INFINITE := 0x7FFF
var player: CharacterBody3D
var data: Dictionary = {}
var weapon := 0
var arm := preload("res://scripts/player/special_arm.gd").new()
var tank := 0
var reserve := 0
var elapsed := 0.0
var fired := false
var aim_target: Node3D
var bullet_script: GDScript
func configure(owner: CharacterBody3D, id: int) -> bool:
	player = owner; weapon = id
	var path := "res://assets/player/weapons/weapon_%02x.json" % id
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if not parsed is Dictionary: return false
	data = parsed; var library_name := str(data["library"]); var packed := load("res://assets/player/weapons/" + str(data["model"])) as PackedScene
	if packed == null: return false
	var instance := packed.instantiate(); var players: Array[Node] = instance.find_children("*", "AnimationPlayer", true, false)
	if players.is_empty(): instance.free(); return false
	if not player.animation_player.has_animation_library(library_name): player.animation_player.add_animation_library(library_name, (players[0] as AnimationPlayer).get_animation_library("").duplicate(true))
	arm.configure(player, instance, data["arm"]); instance.free()
	top_level = true; tank = int(data["tank"]["capacity"]); reserve = reserve_limit()
	_emit_gauge()
	return true
func level(stat: int) -> int: return player.special_level(weapon, stat)
func reserve_limit() -> int: return player.weapon_stats.value(weapon, player.weapon_stats.ENERGY, level(player.weapon_stats.ENERGY))
func rapid() -> int: return player.weapon_stats.value(weapon, player.weapon_stats.RAPID, level(player.weapon_stats.RAPID))
func begin() -> bool:
	if tank < int(data["tank"]["costPerShot"]) or not player.is_on_floor(): return false
	player.animation_roles["shot"] = str(data["library"]) + "/" + str(data["timeline"]["clip"])
	var lock: Node3D = player.locked_target
	if not player._start_special_action("shot"): return false
	aim_target = lock; fired = false; return true
func action_tick(_previous_time: float) -> void:
	var timeline: Dictionary = data["timeline"]; var pose := int(player.special_action_time * 30.0); var fire_pose := int(timeline["firePose"]) + rapid()
	if not fired and pose >= fire_pose:
		fired = true; _spawn()
		if Input.is_action_pressed("special") and tank >= int(data["tank"]["costPerShot"]): fired = false; _seek(float(int(timeline["startPose"]) - 1) / 30.0)
	if fired and pose >= int(timeline["endPose"]): player.special_action_time = player.animation_player.get_animation(str(player.animation_roles["shot"])).length
func _seek(time: float) -> void:
	player.special_action_time = time; player.motion_tree.set("parameters/MotionSeek/seek_request", time); player.motion_tree.advance(0.0)
func _spawn() -> void:
	tank -= int(data["tank"]["costPerShot"])
	var skeleton := player.upper_modifier.get_parent() as Skeleton3D; var muzzle: Vector3 = skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Bone_04")).origin
	player.locked_target = aim_target; var heading: Vector3 = player.aim_heading(muzzle); player.locked_target = null
	var damage: int = player.weapon_stats.value(weapon, player.weapon_stats.ATTACK, level(player.weapon_stats.ATTACK)); var context: Variant = player.get_parent().get("native_context")
	if context is Dictionary and int(context.get("native_save_byte16", 0)) == int(player.weapon_stats.data["attack_halved_when_save_byte16"]): damage >>= 1
	bullet_script.spawn(self, muzzle, heading, damage, float(player.weapon_stats.value(weapon, player.weapon_stats.RANGE, level(player.weapon_stats.RANGE))))
	player.special_sound_requested.emit(int(data["bullet"]["launchSound"]))
func _physics_process(delta: float) -> void:
	if player == null: return
	arm.show(player.active_special() == weapon and player.combat_allowed)
	elapsed += delta
	while elapsed >= TICK: elapsed -= TICK; _tick()
func _tick() -> void:
	if player.special_action != "shot":
		var step := mini(mini(int(data["tank"]["refillPerTick"]), int(data["tank"]["capacity"]) - tank), reserve)
		tank += step
		if reserve < INFINITE: reserve -= step
	_emit_gauge()
func _emit_gauge() -> void: gauge_changed.emit(tank, int(data["tank"]["capacity"]), int(data["tank"]["costPerShot"]), reserve, reserve_limit())
func refill_energy() -> void:
	tank = int(data["tank"]["capacity"]); reserve = reserve_limit(); _emit_gauge()
