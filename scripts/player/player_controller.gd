extends CharacterBody3D
signal health_changed(value: int, maximum: int)
signal fired(projectile: Node3D)
signal interaction_finished(role: String)
signal scripted_walk_finished(completed: bool)
signal footstep
signal jumped
signal landed
signal died
signal special_sound_requested(sound_id: int)
@export var projectile_scene: PackedScene = preload("res://scenes/projectile.tscn")

@export var move_speed := 2.2
@export var turn_speed := 2.3
@export var mouse_sensitivity := 0.003
@export var fire_interval := 11.0 / 30.0
@export var max_health := 80
@export var combat_allowed := true
@export var buster_allowed := true
@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var player_model: Node3D = $PlayerModel
var locked_target: Node3D
var lock_on: Node3D
var input_blocker: Callable
var camera_yaw_constraint: Callable
var camera_shake_raw := 0
var camera_shake_decay := 0
var camera_shake_clock := 0.0
var health := 80
var zenny := 0
var inventory: Dictionary = {"items": {}, "key_items": {}, "special_weapons": {"0": 1}, "body_parts": {}, "buster_parts": {}}
var equipment: Dictionary = {"body_parts": ["", "", ""], "buster_parts": ["", ""]}
var shot_timer := 0.0
var shot_pose := 0.0
var animation_player: AnimationPlayer
var animation_roles: Dictionary = {}
var aiming := false
var body_height := 0.7
var motion_tree: AnimationTree
var locomotion: AnimationNodeAnimation
var upper_body: AnimationNodeAnimation
var upper_modifier: SkeletonModifier3D
var motion_role := ""
var muzzle_node: Node3D
var arm_blend := 0.0
var slow_walking := false
var gun_pose_active := false
var gun_pose_time := 0.0
var footstep_events: Dictionary = {}
var footstep_time := 0.0
var footstep_clip := ""
var invulnerable := false
var free_flight := false
var no_clip := false
var inverse_mouse_y := false
var first_person := false
var first_person_mesh_layers: Dictionary = {}
var camera_default_cull_mask := 0
var first_person_model_hidden := false
var first_person_arm: Node3D
var first_person_arm_skeleton: Skeleton3D
var first_person_source_skeleton: Skeleton3D
var first_person_arm_materials: Array = []
var first_person_muzzle_node: Node3D
var first_person_muzzle_bone := -1
var camera_was_current := false
var controller_layout := 0
var buster_auto_lock := false
var special_auto_lock := false
var vibration_enabled := true
var pending_shot := false
var native_clips: Dictionary = {}
var interaction_roles: Dictionary = {}
var interaction_role := ""
var interaction_elapsed := 0.0
var interaction_duration := 0.0
var interaction_loop := false
var interaction_vertical_speed := 0.0
var interaction_movement_ticks := 0
var interaction_target_y := NAN
var camera_arm_scale := 1.0
var scripted_walk: Dictionary = {}
var special_actions: Dictionary = {}
var equipped_special := 0
# player +0x19F: specials may become active (GAME 0x800CF4A8); stage mode from STxxT area load: 0 none, 1 equipped, 2 force 0x0F.
var special_usable := true
var special_mode := 1
var hose: Node3D
var carried_actor: CharacterBody3D
var special_action := ""
var special_action_time := 0.0
var special_hit_started := false
var special_hits: Dictionary = {}
var carrying_filter := false
var hurt_phase := ""
var hurt_clip := ""
var hurt_ticks := 0.0
var hurt_immunity := 0.0
var hurt_damage := 0
var hurt_hits := 0
enum JumpPhase { GROUNDED, TAKEOFF, RISING, RELEASED, FALLING, LANDING }
var jump_phase := JumpPhase.GROUNDED
var jump_moving := false
var jump_velocity := 0
var jump_ticks := 0
var jump_accumulator := 0.0
var ledge_phase := ""
var ledge_ticks := 0
var ledge_accumulator := 0.0
var ledge_forward := Vector3.ZERO
var ledge_probe := Vector3.ZERO
var ledge_vertical := 0
var look_head_units := 0
var look_root_units := 0
var look_accumulator := 0.0
var camera_distance := -1.0
var camera_world_position := Vector3.ZERO
var camera_world_origin := Vector3.ZERO
var camera_world_valid := false
var camera_world_basis := Basis.IDENTITY

func _ready() -> void:
	if not combat_allowed or not buster_allowed:
		var civilian := load("res://assets/player/megaman_civilian.glb" if not combat_allowed else "res://assets/player/megaman_normal.glb") as PackedScene
		if civilian == null:
			push_error("Missing civilian player model")
			return
		remove_child(player_model)
		player_model.queue_free()
		player_model = civilian.instantiate() as Node3D
		player_model.name = "PlayerModel"
		add_child(player_model)
	if not OS.has_feature("web"): Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	camera.current = true
	camera.reparent(self, true)
	camera.top_level = true
	if camera_pivot is SpringArm3D: (camera_pivot as SpringArm3D).add_excluded_object(get_rid())
	_fit_model()
	_apply_native_materials()
	for mesh: MeshInstance3D in player_model.find_children("*", "MeshInstance3D", true, false): first_person_mesh_layers[mesh] = mesh.layers
	camera_default_cull_mask = camera.cull_mask
	if first_person: camera.set_cull_mask_value(20, false)
	var players := player_model.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty(): animation_player = players[0] as AnimationPlayer
	var metadata: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/manifest_civilian.json" if not combat_allowed else ("res://assets/player/manifest.json" if buster_allowed else "res://assets/player/manifest_normal.json")))
	if metadata is Dictionary:
		animation_roles = metadata.get("animations", {})
		interaction_roles = metadata.get("interactionRoleProvenance", {})
		special_actions = metadata.get("specialActions", {})
	_configure_animation_tree(metadata if metadata is Dictionary else {})
	_configure_first_person_arm()
	hose = preload("res://scripts/player/special_hose.gd").new(); hose.name = "SpecialHose"; add_child(hose)
	if not hose.configure(self): hose.queue_free(); hose = null
	lock_on = preload("res://scripts/player/lock_on.gd").new(); lock_on.name = "LockOn"; add_child(lock_on); lock_on.configure(self)
	if metadata is Dictionary:
		for clip: Dictionary in metadata.get("clips", []):
			native_clips[str(clip["name"])] = clip
			var times: Array[float] = []
			var ticks := 0
			for record: Dictionary in clip.get("records", []):
				if int(record["event"]) & 128: times.append(ticks / 30.0)
				ticks += int(record["durationTicks"])
			footstep_events[str(clip["name"])] = times
	health = max_health
func _process(delta: float) -> void:
	_update_special_action(delta)
	_set_first_person_model_hidden(first_person and camera.current)
	if first_person_arm != null: first_person_arm.visible = first_person and camera.current and player_model.is_visible_in_tree() and combat_allowed and buster_allowed and active_special() != 15 and special_action.is_empty() and ledge_phase.is_empty() and not is_instance_valid(carried_actor)
	if camera.current != camera_was_current: camera_world_valid = false; camera_distance = -1.0; camera_was_current = camera.current
	if camera.current and interaction_role in ["ladder_up", "ladder_down"]: camera_pivot.rotation = Vector3(deg_to_rad(-12.0), player_model.rotation.y, 0.0); _update_camera(delta)
	if camera.current and first_person:
		camera.global_transform = Transform3D(camera_pivot.global_basis, global_position + Vector3.UP * (body_height * 0.9 + float(camera_shake_raw >> 8) / 256.0))
		camera_world_position = camera.global_position; camera_world_origin = camera_pivot.global_position; camera_world_basis = camera.global_basis; camera_world_valid = true; camera_distance = 0.0
	elif camera.current and camera_pivot is SpringArm3D:
		var allowed := maxf((camera_pivot as SpringArm3D).get_hit_length(), 0.0)
		var basis := camera_pivot.global_basis
		var orbit_changed := camera_world_valid and not basis.is_equal_approx(camera_world_basis)
		if orbit_changed or not camera_world_valid:
			var arm := camera_pivot as SpringArm3D
			var query := PhysicsShapeQueryParameters3D.new()
			query.shape = arm.shape
			query.transform = arm.global_transform
			query.motion = basis.z * arm.spring_length
			query.collision_mask = arm.collision_mask
			query.exclude = [get_rid()]
			query.margin = 0.0
			var fractions := get_world_3d().direct_space_state.cast_motion(query)
			if not fractions.is_empty(): allowed = fractions[0] * arm.spring_length
		var goal := camera_pivot.global_position + camera_pivot.global_basis.z * allowed
		if not camera_world_valid: camera_world_position = goal; camera_world_valid = true
		else: camera_world_position = _move_camera(camera_world_position, camera_world_position + camera_pivot.global_position - camera_world_origin)
		camera_world_origin = camera_pivot.global_position
		camera_world_basis = basis
		camera_world_position = _move_camera(camera_world_position, camera_world_position.lerp(goal, 1.0 - exp(-delta * 10.0)))
		camera.global_position = camera_world_position
		var focus := camera_pivot.global_position - camera_world_position
		if focus.length_squared() > 0.000001 and absf(focus.normalized().y) < 0.999: camera.look_at(camera_pivot.global_position, Vector3.UP)
		camera_distance = (camera_world_position - camera_pivot.global_position).dot(camera_pivot.global_basis.z)
	if motion_tree == null: return
	var time := float(motion_tree.get("parameters/Motion/current_position"))
	if footstep_clip != locomotion.animation:
		footstep_clip = locomotion.animation
		footstep_time = 0.0
	if not interaction_role.is_empty() or (is_on_floor() and Vector2(velocity.x, velocity.z).length_squared() > 0.001):
		for event: float in footstep_events.get(footstep_clip, []):
			if (event > footstep_time and event <= time) if time >= footstep_time else (event > footstep_time or event <= time): footstep.emit()
	footstep_time = time
	if not interaction_role.is_empty():
		interaction_elapsed = minf(interaction_elapsed + delta, interaction_duration)
		if interaction_loop:
			var ticks := mini(floori(interaction_elapsed * 30.0 + 0.000001), roundi(interaction_duration * 30.0))
			global_position.y += float(ticks - interaction_movement_ticks) * interaction_vertical_speed / 30.0
			interaction_movement_ticks = ticks
			if is_finite(interaction_target_y) and (global_position.y - interaction_target_y) * signf(interaction_vertical_speed) >= 0.0: global_position.y = interaction_target_y; interaction_duration = interaction_elapsed
	if not interaction_role.is_empty() and interaction_elapsed >= interaction_duration:
		var finished_role := interaction_role
		interaction_role = ""
		motion_tree.set("parameters/MotionSpeed/scale", 1.0)
		_play_animation("idle")
		interaction_finished.emit(finished_role)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("release_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("ui_cancel") and get_tree().current_scene.get_script() == preload("res://scripts/ui/menus/main_menu.gd"): return
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		get_viewport().set_input_as_handled()
	elif Input.mouse_mode == Input.MOUSE_MODE_VISIBLE and event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		get_viewport().set_input_as_handled()
		return
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if not camera.current or not is_physics_processing() or input_blocker.is_valid() and input_blocker.call() or interaction_role in ["ladder_up", "ladder_down"]: return
		camera_pivot.rotation.y -= event.relative.x * mouse_sensitivity
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x + event.relative.y * mouse_sensitivity * (1.0 if inverse_mouse_y else -1.0), deg_to_rad(-85.0 if first_person else -55.0), deg_to_rad(85.0 if first_person else 25.0))
		camera_pivot.rotation.z = 0.0

func _physics_process(delta: float) -> void:
	if not scripted_walk.is_empty(): _update_scripted_walk(delta); return
	if not interaction_role.is_empty(): return
	if input_blocker.is_valid() and input_blocker.call(): velocity = Vector3.ZERO; return
	if not ledge_phase.is_empty(): _update_ledge(delta); _update_camera(delta); return
	if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and (Input.is_action_just_pressed("special") or active_special() == 15 and Input.is_action_just_pressed("fire")): use_special()
	if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and Input.is_action_just_pressed("kick"): kick()
	lock_on.update(delta, combat_allowed and hurt_phase.is_empty() and not is_instance_valid(carried_actor) and (Input.is_action_pressed("lock_on") or Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and (buster_auto_lock and buster_allowed and active_special() == 0 or special_auto_lock and active_special() != 0) and (Input.is_action_pressed("fire") or Input.is_action_pressed("aim"))))
	if not special_action.is_empty(): return
	if locked_target != null and not is_instance_valid(locked_target): locked_target = null
	shot_timer = maxf(shot_timer - delta, 0.0)
	shot_pose = maxf(shot_pose - delta, 0.0)
	hurt_immunity = maxf(hurt_immunity - delta, 0.0)
	_update_hurt(delta)
	aiming = combat_allowed and buster_allowed and not is_instance_valid(carried_actor) and hurt_phase.is_empty() and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and Input.is_action_pressed("aim")
	var firing := combat_allowed and buster_allowed and active_special() != 15 and not is_instance_valid(carried_actor) and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and Input.is_action_pressed("fire")
	if not hurt_phase.is_empty(): firing = false
	if firing and Input.is_action_just_pressed("fire"): pending_shot = true
	if firing or pending_shot:
		if not gun_pose_active:
			gun_pose_active = true
			gun_pose_time = 0.0
			if motion_tree != null: motion_tree.set("parameters/ArmSeek/seek_request", 0.0)
	elif shot_pose <= 0: gun_pose_active = false
	camera_pivot.rotation.y -= Input.get_axis("turn_left", "turn_right") * turn_speed * delta
	var input_vector := Vector2(Input.get_axis("strafe_left", "strafe_right"), Input.get_axis("move_back", "move_forward")) if health >= 0 else Vector2.ZERO
	var forward := -camera_pivot.global_basis.z
	forward.y = 0.0
	var right := camera_pivot.global_basis.x
	right.y = 0.0
	var direction := (right.normalized() * input_vector.x + forward.normalized() * input_vector.y).normalized()
	slow_walking = Input.is_action_pressed("slow_walk")
	var speed := move_speed * (0.45 if slow_walking else 1.0) * (0.6 if aiming else 1.0)
	if jump_phase in [JumpPhase.GROUNDED, JumpPhase.TAKEOFF, JumpPhase.LANDING] or free_flight:
		velocity.x = direction.x * speed
		velocity.z = direction.z * speed
	else:
		var air_speed := 640.0 * 30.0 / 4096.0 * (0.6 if aiming else 1.0)
		velocity.x = move_toward(velocity.x, direction.x * air_speed, 16.0 * 900.0 / 4096.0 * delta)
		velocity.z = move_toward(velocity.z, direction.z * air_speed, 16.0 * 900.0 / 4096.0 * delta)
	collision_mask = 0 if no_clip else 89
	var grounded := is_on_floor()
	if free_flight:
		jump_phase = JumpPhase.GROUNDED
		jump_velocity = 0
		velocity.y = (float(Input.is_action_pressed("jump")) - float(Input.is_action_pressed("fly_down"))) * speed
	else: _update_jump(delta, grounded, direction)
	if grounded and not free_flight and not no_clip and velocity.y <= 0.0 and hurt_phase.is_empty(): _step_over_seam(Vector3(velocity.x, 0.0, velocity.z) * delta)
	if grounded and not free_flight and not no_clip and jump_phase == JumpPhase.GROUNDED and velocity.y <= 0.0: velocity.y = _slope_velocity()
	var before_slide := global_transform; var intended := Vector3(velocity.x, 0.0, velocity.z) * delta
	move_and_slide()
	if not free_flight and not no_clip and _try_grab_ledge(before_slide.origin, intended): _update_camera(delta); return
	if grounded and jump_phase == JumpPhase.GROUNDED and not free_flight and not no_clip: apply_floor_snap()
	if not free_flight and not no_clip:
		var drift := global_position - before_slide.origin; drift.y = 0.0
		if drift.length() > intended.length() + 0.08:
			global_position = Vector3(before_slide.origin.x + intended.x, global_position.y, before_slide.origin.z + intended.z); velocity.x = intended.x / delta if delta > 0.0 else 0.0; velocity.z = intended.z / delta if delta > 0.0 else 0.0
	if not free_flight and is_on_floor() and jump_phase in [JumpPhase.RISING, JumpPhase.RELEASED, JumpPhase.FALLING]:
		jump_velocity = 0
		_set_jump_phase(JumpPhase.LANDING)
		landed.emit()
	_update_camera(delta)
	if aiming and direction.length_squared() <= 0.001 and not lock_on.locked(): player_model.rotation.y += clampf(wrapf(camera.global_rotation.y - player_model.rotation.y, -PI, PI), -4.5 * delta, 4.5 * delta)
	elif direction.length_squared() > 0.001 and not lock_on.locked(): player_model.rotation.y = lerp_angle(player_model.rotation.y, atan2(-direction.x, -direction.z), minf(delta * 12.0, 1.0))
	var arm_role := "shoot_alternate_upper" if not grounded or (direction.length_squared() > 0.001 and not slow_walking) else "shoot_upper"
	var arm_name := str(animation_roles.get(arm_role, animation_roles.get("shoot_upper", "")))
	if is_instance_valid(carried_actor): arm_name = str(animation_roles["lift_hold"])
	_set_carry_filter(is_instance_valid(carried_actor))
	if upper_body != null and upper_body.animation != arm_name and animation_player.has_animation(arm_name):
		upper_body.animation = arm_name
		motion_tree.set("parameters/ArmSeek/seek_request", minf(gun_pose_time, animation_player.get_animation(arm_name).length))
	if gun_pose_active and upper_body != null:
		var length := animation_player.get_animation(upper_body.animation).length
		var repeat_time := fire_interval
		if firing and (gun_pose_time >= repeat_time or is_equal_approx(gun_pose_time, repeat_time)): pending_shot = true
		if pending_shot and is_zero_approx(shot_timer):
			gun_pose_time = 1.0 / 30.0
			motion_tree.set("parameters/ArmSeek/seek_request", gun_pose_time)
			_fire()
			pending_shot = false
		gun_pose_time += delta
		if gun_pose_time >= length and not firing: gun_pose_active = false
	if hurt_phase.is_empty(): _play_animation("idle" if free_flight else _jump_role() if jump_phase != JumpPhase.GROUNDED else ("walk" if slow_walking else "run") if direction.length_squared() > 0.001 else "idle")
	if motion_tree != null:
		arm_blend = 1.0 if gun_pose_active or is_instance_valid(carried_actor) else 0.0
		motion_tree.set("parameters/UpperBody/blend_amount", arm_blend)
	_update_look(delta)
func _ledge_floor(point: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * (181.0 / 256.0), point + Vector3.UP * (104.0 / 256.0), 1, [get_rid()])
	while true:
		var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if hit.is_empty(): return {}
		var collider := hit["collider"] as CollisionObject3D
		if collider != null and bool(collider.get_meta("native_ledge_floor", false)) and (hit["normal"] as Vector3).y > 0.0: return hit
		var excluded := query.exclude; excluded.append(hit["rid"]); query.exclude = excluded
	return {}
func _try_grab_ledge(previous: Vector3, intended: Vector3) -> bool:
	if is_on_floor() or velocity.y >= 0.0 or not hurt_phase.is_empty() or gun_pose_active or aiming or not special_action.is_empty() or is_instance_valid(carried_actor): return false
	var correction := global_position - previous - intended; correction.y = 0.0
	if maxf(absf(correction.x), absf(correction.z)) > 32.0 / 256.0: return false
	var below := get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(global_position, global_position + Vector3.DOWN * (32767.0 / 256.0), 89, [get_rid()]))
	if not below.is_empty() and global_position.y - (below["position"] as Vector3).y < 64.0 / 256.0: return false
	if not has_meta("native_ledge_trig"):
		var weather: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/weather/manifest.json")); set_meta("native_ledge_trig", weather.get("trig4096", []) if weather is Dictionary else [])
	var trig: Array = get_meta("native_ledge_trig"); if trig.size() != 4096: return false
	var angle := (2048 - roundi(player_model.rotation.y * 4096.0 / TAU)) & 4095; var left: Array = trig[(angle - 512) & 4095]; var right: Array = trig[(angle + 512) & 4095]
	var first_point := global_position + Vector3(-float(int(left[0]) * 52), 0.0, float(int(left[1]) * 52)) / 1048576.0
	var second_point := global_position + Vector3(-float(int(right[0]) * 52), 0.0, float(int(right[1]) * 52)) / 1048576.0
	var first := _ledge_floor(first_point); var second := _ledge_floor(second_point)
	if first.is_empty() or second.is_empty(): return false
	var height := roundi((first["position"] as Vector3).y * 256.0)
	if height != roundi((second["position"] as Vector3).y * 256.0): return false
	var rise := height - roundi(global_position.y * 256.0)
	if rise <= 104 or rise >= 180: return false
	if not animation_player.has_animation("clip_029") or not animation_player.has_animation("clip_030") or not animation_player.has_animation("clip_031"): return false
	global_position.y = float(height - 180) / 256.0; ledge_forward = Vector3(-float(trig[angle][0]), 0.0, float(trig[angle][1])) / 4096.0; ledge_probe = first_point
	velocity = Vector3.ZERO; jump_velocity = 0; jump_accumulator = 0.0; pending_shot = false; gun_pose_active = false; ledge_phase = "grab"; ledge_ticks = 0; ledge_accumulator = 0.0
	_play_ledge_clip("clip_029"); special_sound_requested.emit(0x94); return true
func _play_ledge_clip(clip: String) -> void:
	locomotion.animation = clip; motion_role = ""; motion_tree.set("parameters/MotionSeek/seek_request", 0.0); motion_tree.set("parameters/UpperBody/blend_amount", 0.0)
	animation_player.get_animation(clip).loop_mode = Animation.LOOP_LINEAR if bool(native_clips.get(clip, {}).get("loops", false)) else Animation.LOOP_NONE; motion_tree.set("parameters/MotionSpeed/scale", 25.0 / 30.0)
	if upper_modifier != null: upper_modifier.active = false
func _release_ledge() -> void:
	ledge_phase = ""; ledge_ticks = 0; ledge_accumulator = 0.0; velocity = Vector3.ZERO; jump_velocity = 0; jump_accumulator = 0.0; _set_jump_phase(JumpPhase.FALLING)
	motion_tree.set("parameters/MotionSpeed/scale", 1.0)
	if upper_modifier != null: upper_modifier.active = true
func _update_ledge(delta: float) -> void:
	if free_flight or no_clip or not hurt_phase.is_empty(): _release_ledge(); return
	if ledge_phase == "hang" and Input.is_action_just_pressed("move_back"): _release_ledge(); return
	ledge_accumulator += delta * 25.0
	while ledge_accumulator >= 1.0 and not ledge_phase.is_empty():
		ledge_accumulator -= 1.0; ledge_ticks += 1
		if ledge_phase == "grab":
			if ledge_ticks >= int(native_clips.get("clip_029", {}).get("durationTicks", 5)): ledge_phase = "hang"; ledge_ticks = 0; _play_ledge_clip("clip_030")
		elif ledge_phase == "hang":
			ledge_probe.y = global_position.y
			var top := _ledge_floor(ledge_probe)
			if top.is_empty(): _release_ledge(); return
			var height := (top["position"] as Vector3).y - 180.0 / 256.0
			if absf(height - global_position.y) >= 32.0 / 256.0: _release_ledge(); return
			global_position.y = height
			if Input.is_action_pressed("move_forward"): ledge_phase = "climb"; ledge_ticks = 0; ledge_vertical = 144; _play_ledge_clip("clip_031")
		elif ledge_phase == "climb":
			var event_tick := 0; var elapsed := 0
			for record: Dictionary in native_clips.get("clip_031", {}).get("records", []):
				if int(record["event"]) == 1: event_tick = elapsed; break
				elapsed += int(record["durationTicks"])
			var advance := ledge_ticks > event_tick
			if ledge_ticks == event_tick + 1: ledge_vertical = 432
			elif advance: ledge_vertical -= 48
			velocity = (ledge_forward * (80.0 / 4096.0 if advance else 0.0) + Vector3.UP * (float(ledge_vertical) / 4096.0)) / get_physics_process_delta_time()
			move_and_slide()
			if is_on_floor():
				ledge_phase = ""; jump_velocity = 0; _set_jump_phase(JumpPhase.LANDING); landed.emit()
				motion_tree.set("parameters/MotionSpeed/scale", 1.0)
				if upper_modifier != null: upper_modifier.active = true
			elif ledge_ticks >= int(native_clips.get("clip_031", {}).get("durationTicks", 20)): _release_ledge()
func _set_carry_filter(value: bool) -> void:
	if carrying_filter == value or motion_tree == null: return
	carrying_filter = value
	var blend := (motion_tree.tree_root as AnimationNodeBlendTree).get_node("UpperBody") as AnimationNodeBlend2
	var gun_clip := animation_player.get_animation(str(animation_roles["shoot_upper"]))
	for track in range(gun_clip.get_track_count()):
		var path := gun_clip.track_get_path(track)
		if path.get_subname_count() > 0 and str(path.get_subname(0)) == "Bone_01": blend.set_filter_path(path, not value)
	for track in range(animation_player.get_animation(str(animation_roles["lift_hold"])).get_track_count()):
		var path := animation_player.get_animation(str(animation_roles["lift_hold"])).track_get_path(track)
		if path.get_subname_count() > 0 and str(path.get_subname(0)) in ["Bone_02", "Bone_03", "Bone_04"]: blend.set_filter_path(path, value)
	if upper_modifier != null: upper_modifier.active = not value
func lift_anchor(height: float) -> Vector3:
	var skeleton := upper_modifier.get_parent() as Skeleton3D
	var point := Vector3.ZERO
	for bone in [4, 7]: point += skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Bone_%02d" % bone)).origin
	return point * 0.5 - Vector3.UP * height * 0.5
func end_lift(actor: CharacterBody3D) -> void:
	if carried_actor != actor: return
	carried_actor = null
	if special_action == "lift_throw": return
	special_action = ""; motion_role = ""; _set_carry_filter(false)
	if upper_modifier != null: upper_modifier.active = true
	if motion_tree != null: motion_tree.set("parameters/UpperBody/blend_amount", 0.0)
	_play_animation("idle")
func active_special() -> int:
	if special_mode == 2: equipped_special = 15
	return equipped_special if special_mode != 0 and special_usable else 0
func use_special() -> bool:
	if active_special() == 15: return is_instance_valid(hose) and combat_allowed and hurt_phase.is_empty() and interaction_role.is_empty() and special_action.is_empty() and not is_instance_valid(carried_actor) and hose.begin()
	if not combat_allowed or not hurt_phase.is_empty() or not interaction_role.is_empty() or not special_action.is_empty() or special_actions.is_empty() or active_special() != 0 or not is_on_floor(): return false
	if is_instance_valid(carried_actor): return _start_special_action("lift_throw", float(special_actions["throw"]["start_pose"]) / 30.0)
	var nearest := get_lift_target()
	if nearest != null and nearest.begin_lift(self):
		carried_actor = nearest
		special_sound_requested.emit(int(special_actions["grab"]["sound"]))
		return _start_special_action("lift_grab")
	return false
func get_lift_target() -> CharacterBody3D:
	if not combat_allowed or special_actions.is_empty() or active_special() != 0 or is_instance_valid(carried_actor): return null
	var nearest: CharacterBody3D
	var score := INF
	var forward := -player_model.global_basis.z
	for actor in get_tree().get_nodes_in_group("lift_targets"):
		if not actor.can_lift(): continue
		var offset: Vector3 = actor.global_position - global_position
		var horizontal := Vector2(offset.x, offset.z).length()
		if horizontal >= float(special_actions["grab"]["range_raw"] + 64) / 256.0 or absf(offset.y) >= 64.0 / 256.0: continue
		var angle := absf(forward.signed_angle_to(Vector3(offset.x, 0, offset.z).normalized(), Vector3.UP))
		if angle >= float(special_actions["grab"]["cone_units"]) * TAU / 4096.0: continue
		var candidate := horizontal + angle * 4096.0 / TAU / 4.0 / 256.0
		if candidate < score: nearest = actor; score = candidate
	return nearest
func _native_look_pitch() -> int:
	if lock_on.locked() or Input.is_action_pressed("lock_on"): return lock_on.pitch
	return clampi(roundi(-(camera_pivot.rotation.x - deg_to_rad(-12.0)) * 4096.0 / TAU), -0x200, 0x200)
func kick() -> bool:
	if not combat_allowed or not hurt_phase.is_empty() or not interaction_role.is_empty() or not special_action.is_empty() or special_actions.is_empty() or is_instance_valid(carried_actor) or not is_on_floor(): return false
	return _start_special_action("kick")
func _start_special_action(role: String, start_time: float = 0.0) -> bool:
	var clip := str(animation_roles.get(role, ""))
	if motion_tree == null or not animation_player.has_animation(clip): return false
	special_action = role
	special_action_time = start_time
	special_hit_started = false
	special_hits.clear()
	velocity = Vector3.ZERO
	gun_pose_active = false
	pending_shot = false
	aiming = false
	locked_target = null
	motion_tree.set("parameters/UpperBody/blend_amount", 0.0)
	look_head_units = 0
	look_root_units = 0
	if upper_modifier != null: upper_modifier.set_source_aim_angles(0, 0); upper_modifier.active = false
	_play_animation(role)
	motion_tree.set("parameters/MotionSeek/seek_request", start_time)
	motion_tree.advance(0.0)
	return true
func _update_special_action(delta: float) -> void:
	if special_action.is_empty(): return
	var previous_time := special_action_time
	special_action_time += delta
	if special_action == "kick":
		if special_action_time >= float(special_actions["kick"]["emit_pose"]) / 30.0 and previous_time < float(special_actions["kick"]["hit_ticks"]) / 30.0: _kick_contact()
	elif special_action == "hose": hose.action_tick(previous_time)
	elif special_action == "lift_throw" and not special_hit_started and special_action_time >= float(special_actions["throw"]["release_pose"]) / 30.0:
		special_hit_started = true
		if is_instance_valid(carried_actor): carried_actor.release_lift(-player_model.global_basis.z, int(special_actions["throw"]["vertical_raw"]), int(special_actions["throw"]["forward_raw"])); carried_actor = null
		special_sound_requested.emit(int(special_actions["throw"]["sound"]))
	if special_action_time < animation_player.get_animation(str(animation_roles[special_action])).length: return
	special_action = ""
	motion_role = ""
	_set_carry_filter(is_instance_valid(carried_actor))
	if upper_modifier != null: upper_modifier.active = not is_instance_valid(carried_actor)
	_play_animation("idle")
func _kick_contact() -> void:
	if not special_hit_started: special_hit_started = true; special_sound_requested.emit(int(special_actions["kick"]["sound"]))
	var skeleton := upper_modifier.get_parent() as Skeleton3D
	var point := skeleton.global_transform * skeleton.get_bone_global_pose(skeleton.find_bone("Bone_%02d" % int(special_actions["kick"]["bone"]))).origin
	var shape := BoxShape3D.new()
	shape.size = Vector3.ONE * 16.0 / 256.0
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.transform = Transform3D(Basis.IDENTITY, point)
	query.collision_mask = 8
	query.exclude = [get_rid()]
	for hit in get_world_3d().direct_space_state.intersect_shape(query):
		var actor: Node = hit["collider"]
		if actor.has_method("receive_hit") and not special_hits.has(actor.get_instance_id()):
			special_hits[actor.get_instance_id()] = true
			actor.receive_hit(int(special_actions["kick"]["damage"]), int(special_actions["kick"]["source_flags"]), -player_model.global_basis.z)
func _update_look(delta: float) -> void:
	if upper_modifier == null: return
	var relative := wrapf(camera.global_rotation.y - player_model.rotation.y, -PI, PI)
	if is_instance_valid(locked_target):
		var offset := locked_target.global_position - global_position
		relative = wrapf(atan2(-offset.x, -offset.z) - player_model.rotation.y, -PI, PI)
	var target := clampi(roundi(-relative * 4096.0 / TAU), -1024, 1024)
	look_accumulator += delta * 30.0
	while look_accumulator >= 1.0:
		look_accumulator -= 1.0
		var root_goal := target if gun_pose_active else 0
		look_root_units = clampi(root_goal, look_root_units - 128, look_root_units + 128)
		var head_goal := clampi(target - look_root_units, -512, 512)
		if not gun_pose_active and Vector2(velocity.x, velocity.z).length_squared() > 0.001: head_goal = int(head_goal * 3 / 4)
		look_head_units = clampi(head_goal, look_head_units - 256, look_head_units + 256)
	upper_modifier.set_source_aim_angles(look_root_units, look_head_units)
	upper_modifier.track_target = gun_pose_active or is_instance_valid(locked_target)
	if upper_modifier.track_target: upper_modifier.aim_target = _aim_point() if aiming or is_instance_valid(locked_target) else global_position + Vector3.UP * body_height * 0.7 - camera.global_basis.z * 80.0
func _aim_point() -> Vector3:
	var ray_start := camera.global_position
	var direction := (locked_target.global_position + Vector3.UP - ray_start).normalized() if is_instance_valid(locked_target) else -camera.global_basis.z
	var chest := global_position + Vector3.UP * body_height * 0.7
	var distance := maxf((chest - ray_start).dot(direction), 0.0) + body_height * 0.45
	var end := ray_start + direction * 80.0
	var query := PhysicsRayQueryParameters3D.create(ray_start + direction * distance, end, 9)
	query.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return hit["position"] if not hit.is_empty() else end
func _set_jump_phase(phase: JumpPhase) -> void:
	jump_phase = phase
	jump_ticks = 0
func _launch_jump() -> void:
	jump_velocity = -800
	_set_jump_phase(JumpPhase.RISING)
	jumped.emit()
func _update_jump(delta: float, grounded: bool, direction: Vector3) -> void:
	if grounded and jump_phase == JumpPhase.GROUNDED:
		jump_velocity = 0
		if Input.is_action_just_pressed("jump") and hurt_phase.is_empty():
			jump_moving = direction.length_squared() > 0.001
			jump_accumulator = 0.0
			if jump_moving:
				velocity.x = direction.x * 512.0 * 30.0 / 4096.0
				velocity.z = direction.z * 512.0 * 30.0 / 4096.0
				_launch_jump()
			else: _set_jump_phase(JumpPhase.TAKEOFF)
	elif not grounded and jump_phase == JumpPhase.GROUNDED:
		jump_moving = direction.length_squared() > 0.001
		_set_jump_phase(JumpPhase.FALLING)
	jump_accumulator += delta * 30.0
	while jump_accumulator >= 1.0:
		jump_accumulator -= 1.0
		jump_ticks += 1
		match jump_phase:
			JumpPhase.TAKEOFF:
				if jump_ticks >= 3 and _jump_clip_ended(): _launch_jump()
			JumpPhase.RISING:
				if Input.is_action_pressed("jump"):
					jump_velocity += 48
					if jump_velocity >= 0: _set_jump_phase(JumpPhase.FALLING)
				else:
					_set_jump_phase(JumpPhase.RELEASED)
					_release_jump()
			JumpPhase.RELEASED: _release_jump()
			JumpPhase.FALLING: jump_velocity += 48
			JumpPhase.LANDING:
				if jump_ticks == (3 if jump_moving else 1): var ring := preload("res://scripts/player/ground_effect.gd").new() as Node3D; get_parent().add_child(ring); ring.global_position = global_position
				if jump_ticks >= 3 and _jump_clip_ended(): _set_jump_phase(JumpPhase.GROUNDED)
	velocity.y = -float(jump_velocity) * 30.0 / 4096.0
func _release_jump() -> void:
	if -jump_velocity > 576: jump_velocity += 576
	else:
		jump_velocity = 0
		_set_jump_phase(JumpPhase.FALLING)
func _jump_role() -> String:
	if jump_phase == JumpPhase.TAKEOFF: return "jump_takeoff"
	if jump_phase in [JumpPhase.RISING, JumpPhase.RELEASED]: return "jump_move" if jump_moving else "jump"
	if jump_phase == JumpPhase.LANDING: return "jump_land_move" if jump_moving else "jump_land"
	return "jump_fall_move" if jump_moving else "jump_fall"
func _jump_clip_ended() -> bool:
	var name := str(animation_roles.get(_jump_role(), ""))
	if animation_player == null or not animation_player.has_animation(name) or motion_role != _jump_role(): return false
	var time := float(motion_tree.get("parameters/Motion/current_position")) if motion_tree != null else animation_player.current_animation_position
	var length := animation_player.get_animation(name).length
	return time >= length or is_equal_approx(time, length)

func _toggle_lock_target() -> void:
	if is_instance_valid(locked_target):
		locked_target = null
		return
	var nearest_distance := INF
	for candidate in get_tree().get_nodes_in_group("lock_targets"):
		var candidate_node := candidate as Node3D
		if candidate_node == null: continue
		var target_point: Vector3 = candidate_node.global_position + Vector3.UP
		var offset: Vector3 = target_point - camera.global_position
		var distance := offset.length()
		if -camera.global_basis.z.dot(offset.normalized()) > 0.25 and distance < nearest_distance:
			nearest_distance = distance
			locked_target = candidate_node
	if is_instance_valid(locked_target):
		var facing := locked_target.global_position - global_position
		facing.y = 0.0
		rotation.y = atan2(-facing.x, -facing.z)

func _fire() -> void:
	if not combat_allowed or not buster_allowed or not is_zero_approx(shot_timer): return
	shot_timer = fire_interval
	shot_pose = maxf(animation_player.get_animation(upper_body.animation).length - gun_pose_time, 0.2) if motion_tree != null else 0.2
	var aim := _aim_point()
	var muzzle := global_position + Vector3.UP * body_height * 0.7 + Basis(Vector3.UP, player_model.rotation.y) * Vector3(body_height * 0.22, 0, -body_height * 0.22)
	if muzzle_node != null: muzzle = muzzle_node.global_position
	var view_muzzle := first_person and camera.current and first_person_muzzle_node != null
	if view_muzzle:
		_update_first_person_arm(true)
		muzzle = first_person_arm_skeleton.global_transform * first_person_arm_skeleton.get_bone_global_pose(first_person_muzzle_bone) * first_person_muzzle_node.position
	var heading := aim - muzzle if first_person or aiming or is_instance_valid(locked_target) else -camera.global_basis.z
	var chest := global_position + Vector3.UP * body_height * 0.7
	var obstruction := get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(chest, muzzle, 1))
	if view_muzzle and obstruction.is_empty(): obstruction = get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(camera.global_position, muzzle, 1))
	var projectile := projectile_scene.instantiate() as Node3D
	get_parent().add_child(projectile)
	projectile.launch(muzzle, heading)
	fired.emit(projectile)
	if not obstruction.is_empty():
		projectile.hit_surface.emit(obstruction["position"], obstruction["normal"])
		projectile._impact(obstruction["position"] + obstruction["normal"] * 0.03, false)
		projectile.queue_free()
func _fit_model() -> void:
	var bounds := AABB()
	var first := true
	for node in player_model.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null: continue
		var transform := player_model.global_transform.affine_inverse() * mesh_node.global_transform
		var box: AABB = transform * mesh_node.get_aabb()
		bounds = box if first else bounds.merge(box)
		first = false
	if first or bounds.size.y <= 0: return
	body_height = bounds.size.y
	player_model.scale = Vector3.ONE
	player_model.position = Vector3(-bounds.get_center().x, -bounds.position.y, -bounds.get_center().z)
	var capsule := $Collision.shape as CapsuleShape3D
	capsule.height = body_height
	capsule.radius = bounds.size.x * 0.45
	$Collision.position.y = body_height * 0.5
	camera_pivot.position.y = body_height * 0.78
	if camera_pivot is SpringArm3D: (camera_pivot as SpringArm3D).spring_length = body_height * 3.4
	if camera_pivot is SpringArm3D: ((camera_pivot as SpringArm3D).shape as SphereShape3D).radius = capsule.radius * 0.8
func _update_camera(delta: float) -> void:
	camera_shake_clock += delta * 25.0
	while camera_shake_clock >= 1.0: camera_shake_clock -= 1.0; camera_shake_raw = maxi(camera_shake_raw - camera_shake_decay, 0)
	if not camera.current: return
	if first_person:
		camera_pivot.position = Vector3(0.0, body_height * 0.9 + float(camera_shake_raw >> 8) / 256.0, 0.0)
		if camera_pivot is SpringArm3D: (camera_pivot as SpringArm3D).spring_length = 0.0
		return
	if camera_yaw_constraint.is_valid(): camera_pivot.rotation.y = lerp_angle(camera_pivot.rotation.y, camera_yaw_constraint.call(global_position, camera_pivot.rotation.y), 1.0 - exp(-delta * 10.0))
	if not camera_pivot is SpringArm3D: return
	var arm := camera_pivot as SpringArm3D
	arm.spring_length = lerpf(arm.spring_length, body_height * (1.8 if aiming else 3.4) * camera_arm_scale, minf(delta * 10, 1))
	var offset := arm.basis.x * (body_height * 0.3 if aiming else 0.0)
	var current := Vector3(arm.position.x, 0, arm.position.z)
	offset = current.lerp(offset, minf(delta * 10, 1))
	var origin := global_position + Vector3.UP * body_height * 0.78
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = arm.shape
	query.transform = Transform3D(Basis.IDENTITY, origin)
	query.collision_mask = 4
	query.motion = offset
	query.margin = 0.01
	var fractions := get_world_3d().direct_space_state.cast_motion(query)
	if not fractions.is_empty(): offset *= fractions[0]
	arm.position = Vector3(offset.x, body_height * 0.78 + float(camera_shake_raw >> 8) / 256.0, offset.z)
func _slope_velocity() -> float:
	var normal := get_floor_normal()
	return -(normal.x * velocity.x + normal.z * velocity.z) / normal.y if normal.y > 0.1 and normal.y < 0.9999 else velocity.y
func _step_over_seam(motion: Vector3) -> void:
	if motion.is_zero_approx(): return
	var contact := KinematicCollision3D.new()
	if not test_move(global_transform, motion, contact): return
	if contact.get_normal().y + 0.001 >= cos(floor_max_angle): return
	var collider := contact.get_collider() as Node
	if collider != null and (collider.is_in_group("world_npcs") or collider.name == "NativeActorCollision"): return
	var height := minf(0.25 + safe_margin * 4.0, body_height * 0.375); var up := Vector3.UP * height
	if test_move(global_transform, up): return
	var raised := global_transform; raised.origin += up
	if test_move(raised, motion): return
	var ahead := global_position + motion.normalized() * (motion.length() + ($Collision.shape as CapsuleShape3D).radius + 0.03)
	var query := PhysicsRayQueryParameters3D.create(ahead + up + Vector3.UP * safe_margin, ahead + Vector3.DOWN * safe_margin * 2.0, collision_mask, [get_rid()])
	var landing := get_world_3d().direct_space_state.intersect_ray(query)
	if landing.is_empty() or (landing["normal"] as Vector3).y + 0.001 < cos(floor_max_angle): return
	var rise := (landing["position"] as Vector3).y - global_position.y
	if rise <= safe_margin or rise > height: return
	global_position.y += rise; velocity.y = 0.0
func _move_camera(start: Vector3, destination: Vector3) -> Vector3:
	var arm := camera_pivot as SpringArm3D
	var position := start
	var remaining := destination - start
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = arm.shape
	query.collision_mask = arm.collision_mask
	query.exclude = [get_rid()]
	query.margin = 0.01
	for iteration in max_slides:
		if remaining.is_zero_approx(): break
		query.transform = Transform3D(Basis.IDENTITY, position)
		query.motion = remaining
		var fractions := get_world_3d().direct_space_state.cast_motion(query)
		if fractions.is_empty() or fractions[0] >= 1.0: position += remaining; break
		var origin := position
		position += remaining * fractions[0]
		query.transform.origin = origin + remaining * fractions[1]
		query.motion = Vector3.ZERO
		var contact := get_world_3d().direct_space_state.get_rest_info(query)
		if contact.is_empty(): break
		remaining = (remaining * (1.0 - fractions[0])).slide(contact["normal"])
	return position
func _play_animation(role: String) -> void:
	var name := str(animation_roles.get(role, ""))
	if animation_player == null or name.is_empty() or not animation_player.has_animation(name): return
	if motion_tree != null:
		if motion_role != role:
			locomotion.animation = name
			motion_tree.set("parameters/MotionSeek/seek_request", 0.0)
			motion_role = role
		return
	if animation_player.current_animation == name and animation_player.is_playing(): return
	animation_player.play(name, 0.1)
func begin_interaction(role: String = "door_open", quick: bool = false, target_y: float = NAN) -> Dictionary:
	var name := str(animation_roles.get(role, ""))
	if motion_tree == null or animation_player == null or not animation_player.has_animation(name) or not interaction_roles.has(role): return {}
	if is_instance_valid(carried_actor): carried_actor.release_lift(-player_model.global_basis.z, -256, -896)
	carried_actor = null
	special_action = ""
	_set_carry_filter(false)
	if upper_modifier != null: upper_modifier.active = true
	var source: Dictionary = interaction_roles[role]
	interaction_role = role
	interaction_elapsed = 0.0
	var rate := 3.0 if quick and role == "door_open" else 1.0
	interaction_target_y = target_y if int(source.get("loop_ticks", 0)) > 0 else NAN
	interaction_duration = 3600.0 if is_finite(interaction_target_y) else float(source["duration_ticks"]) / (30.0 * rate)
	interaction_loop = int(source.get("loop_ticks", 0)) > 0
	interaction_vertical_speed = -float(source.get("vertical_raw", 0)) * 30.0 / 4096.0
	interaction_movement_ticks = 0
	animation_player.get_animation(name).loop_mode = Animation.LOOP_LINEAR if interaction_loop else Animation.LOOP_NONE
	velocity = Vector3.ZERO
	aiming = false
	locked_target = null
	gun_pose_active = false
	gun_pose_time = 0.0
	pending_shot = false
	shot_pose = 0.0
	arm_blend = 0.0
	look_head_units = 0
	look_root_units = 0
	look_accumulator = 0.0
	motion_tree.set("parameters/UpperBody/blend_amount", 0.0)
	if upper_modifier != null:
		upper_modifier.track_target = false
		upper_modifier.set_source_aim_angles(0, 0)
	motion_role = ""
	motion_tree.set("parameters/MotionSpeed/scale", rate)
	_play_animation(role)
	motion_tree.advance(0.0)
	return {"duration": interaction_duration, "vertical_speed": interaction_vertical_speed} if interaction_loop else {"duration": interaction_duration, "rate": rate, "open_at": float(source["open_tick"]) / (30.0 * rate), "close_at": float(source["close_tick"]) / (30.0 * rate), "walk_at": float(source["walk_handoff_tick"]) / (30.0 * rate)}
func begin_scripted_walk(source: Dictionary, yaw: float) -> bool:
	var role := "walk" if int(source.get("control", -1)) == 2 else "run"; var clip := str(animation_roles.get(role, "")); var step: Array = source.get("local_step_raw", []); var rate := float(source.get("tick_rate", 0)); var ticks := int(source.get("ticks", 0))
	if motion_tree == null or animation_player == null or not animation_player.has_animation(clip) or int(source.get("control", -1)) not in [1, 2] or step.size() != 3 or rate <= 0.0 or ticks <= 0: return false
	if is_instance_valid(carried_actor): carried_actor.release_lift(-player_model.global_basis.z, -256, -896)
	carried_actor = null; special_action = ""; interaction_role = ""; _set_carry_filter(false); aiming = false; locked_target = null; gun_pose_active = false; pending_shot = false; shot_pose = 0.0; arm_blend = 0.0; velocity = Vector3.ZERO; jump_phase = JumpPhase.GROUNDED; jump_velocity = 0
	if upper_modifier != null: upper_modifier.active = true; upper_modifier.track_target = false; upper_modifier.set_source_aim_angles(0, 0)
	motion_tree.set("parameters/UpperBody/blend_amount", 0.0); motion_tree.set("parameters/MotionSpeed/scale", rate / 30.0); player_model.rotation.y = yaw; scripted_walk = {"elapsed": 0.0, "duration": float(ticks) / rate, "velocity": Basis(Vector3.UP, yaw) * Vector3(-float(step[0]), -float(step[1]), float(step[2])) * rate / 4096.0}; motion_role = ""; _play_animation(role); motion_tree.advance(0.0)
	return true
func camera_shake(mode: int, magnitude: int, decay: int) -> void:
	if mode == 0 or magnitude > camera_shake_raw: camera_shake_raw = magnitude; camera_shake_decay = decay
func set_first_person(enabled: bool) -> void:
	first_person = enabled
	if not is_node_ready(): return
	camera.cull_mask = camera_default_cull_mask & ~(1 << 19) if enabled else camera_default_cull_mask
	camera_world_valid = false; camera_distance = -1.0
	if not enabled: camera_pivot.rotation.x = clampf(camera_pivot.rotation.x, deg_to_rad(-55.0), deg_to_rad(25.0))
	if camera_pivot is SpringArm3D: (camera_pivot as SpringArm3D).spring_length = 0.0 if enabled else body_height * (1.8 if aiming else 3.4)
	_set_first_person_model_hidden(enabled and camera.current)
	_update_camera(0.0)
func _set_first_person_model_hidden(hidden: bool) -> void:
	if first_person_model_hidden == hidden: return
	for mesh: MeshInstance3D in first_person_mesh_layers:
		if is_instance_valid(mesh): mesh.layers = (1 << 19) if hidden else int(first_person_mesh_layers[mesh])
	first_person_model_hidden = hidden
func _configure_first_person_arm() -> void:
	if not combat_allowed or not buster_allowed or upper_modifier == null: return
	first_person_source_skeleton = upper_modifier.get_parent() as Skeleton3D
	first_person_arm = Node3D.new(); first_person_arm.name = "FirstPersonArm"; camera.add_child(first_person_arm); first_person_arm.position = Vector3(0.0, -body_height * 0.9, -body_height * 0.2); first_person_arm.visible = false
	first_person_arm_skeleton = Skeleton3D.new(); first_person_arm_skeleton.name = "Skeleton3D"; first_person_arm.add_child(first_person_arm_skeleton)
	first_person_arm_skeleton.transform = player_model.global_transform.affine_inverse() * first_person_source_skeleton.global_transform
	for bone in range(first_person_source_skeleton.get_bone_count()):
		first_person_arm_skeleton.add_bone(first_person_source_skeleton.get_bone_name(bone)); first_person_arm_skeleton.set_bone_parent(bone, first_person_source_skeleton.get_bone_parent(bone)); first_person_arm_skeleton.set_bone_rest(bone, first_person_source_skeleton.get_bone_rest(bone))
	if muzzle_node != null:
		var attachment := BoneAttachment3D.new(); first_person_arm_skeleton.add_child(attachment); attachment.bone_name = (muzzle_node.get_parent() as BoneAttachment3D).bone_name
		first_person_muzzle_bone = first_person_arm_skeleton.find_bone(attachment.bone_name); first_person_muzzle_node = Node3D.new(); attachment.add_child(first_person_muzzle_node); first_person_muzzle_node.position = muzzle_node.position
	var arm_bones: Array[int] = []
	for bone_name in ["Bone_05", "Bone_06", "Bone_07"]: arm_bones.append(first_person_source_skeleton.find_bone(bone_name))
	for source: MeshInstance3D in first_person_mesh_layers:
		if source.mesh == null or source.skin == null: continue
		var arm_mesh := ArrayMesh.new()
		for surface in range(source.mesh.get_surface_count()):
			var arrays := source.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
			var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
			if vertices.is_empty() or bones.is_empty(): continue
			var influences := bones.size() / vertices.size()
			var source_indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX] if arrays[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
			if source_indices.is_empty():
				for vertex in range(vertices.size()): source_indices.append(vertex)
			var indices := PackedInt32Array()
			for triangle in range(0, source_indices.size(), 3):
				var keep := true
				for corner in range(3):
					var vertex := source_indices[triangle + corner]
					for influence in range(influences):
						var slot := vertex * influences + influence
						if weights[slot] <= 0.0: continue
						var bind := bones[slot]
						var bone := first_person_source_skeleton.find_bone(source.skin.get_bind_name(bind)) if not source.skin.get_bind_name(bind).is_empty() else source.skin.get_bind_bone(bind)
						if bone not in arm_bones: keep = false; break
				if keep: indices.append_array(source_indices.slice(triangle, triangle + 3))
			if indices.is_empty(): continue
			arrays[Mesh.ARRAY_INDEX] = indices
			arm_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, source.mesh.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
			var source_material := source.get_active_material(surface) as ShaderMaterial
			var material := source_material.duplicate() as ShaderMaterial
			for parameter in ["native_actor_visible", "native_map_placement_visible", "part_visible"]: material.set_shader_parameter(parameter, true)
			for parameter in ["native_depth_cue_enabled", "native_palette_enabled", "native_map_terrain", "portal_clip_enabled"]: material.set_shader_parameter(parameter, false)
			for parameter in ["interior_clip_count", "room_clip_count", "portal_floor_clip_count"]: material.set_shader_parameter(parameter, 0)
			material.set_shader_parameter("hidden_face_range", Vector2(-1.0, -1.0)); first_person_arm_materials.append([source_material, material]); arm_mesh.surface_set_material(arm_mesh.get_surface_count() - 1, material)
		if arm_mesh.get_surface_count() == 0: continue
		var mesh := MeshInstance3D.new(); mesh.mesh = arm_mesh; mesh.skin = source.skin; mesh.layers = 1 << 18; mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; first_person_arm.add_child(mesh); mesh.skeleton = mesh.get_path_to(first_person_arm_skeleton)
	first_person_source_skeleton.skeleton_updated.connect(_update_first_person_arm)
func _update_first_person_arm(force: bool = false) -> void:
	if first_person_arm == null or not first_person_arm.visible and not force: return
	for pair: Array in first_person_arm_materials:
		for parameter in ["light_rgb", "color_scale"]: (pair[1] as ShaderMaterial).set_shader_parameter(parameter, (pair[0] as ShaderMaterial).get_shader_parameter(parameter))
	for bone in range(first_person_source_skeleton.get_bone_count()): first_person_arm_skeleton.set_bone_pose(bone, first_person_source_skeleton.get_bone_pose(bone))
	var shoulder := first_person_arm_skeleton.transform * first_person_arm_skeleton.get_bone_global_pose(first_person_arm_skeleton.find_bone("Bone_05")).origin
	var barrel := first_person_arm_skeleton.transform.basis * -first_person_arm_skeleton.get_bone_global_pose(first_person_arm_skeleton.find_bone("Bone_06")).basis.y
	first_person_arm.basis = Basis(Quaternion(barrel.normalized(), Vector3.FORWARD))
	first_person_arm.position = Vector3(-body_height * 0.18, -body_height * 0.2, -body_height * 0.12) - first_person_arm.basis * shoulder
func refresh_room_camera(preserve_world: bool = false) -> void:
	if not preserve_world: camera_world_valid = false; camera_distance = -1.0
	_update_camera(0.0)
func _update_scripted_walk(delta: float) -> void:
	var elapsed := float(scripted_walk["elapsed"]); var duration := float(scripted_walk["duration"]); var advance := minf(delta, duration - elapsed)
	velocity = (scripted_walk["velocity"] as Vector3) * advance / delta; move_and_slide(); apply_floor_snap(); _update_camera(delta); scripted_walk["elapsed"] = elapsed + advance
	if elapsed + advance >= duration: scripted_walk.clear(); velocity = Vector3.ZERO; motion_tree.set("parameters/MotionSpeed/scale", 1.0); _play_animation("idle"); scripted_walk_finished.emit(true)
func cancel_scripted_walk() -> void:
	if scripted_walk.is_empty(): return
	scripted_walk.clear(); velocity = Vector3.ZERO; motion_tree.set("parameters/MotionSpeed/scale", 1.0); _play_animation("idle"); scripted_walk_finished.emit(false)
func _configure_animation_tree(metadata: Dictionary) -> void:
	if animation_player == null or not animation_roles.has("idle"): return
	var idle := str(animation_roles["idle"])
	var shoot := str(animation_roles.get("shoot_upper", animation_roles.get("shoot", idle)))
	if not animation_player.has_animation(idle) or not animation_player.has_animation(shoot): return
	for role in ["idle", "run", "walk"]:
		var name := str(animation_roles.get(role, ""))
		if animation_player.has_animation(name): animation_player.get_animation(name).loop_mode = Animation.LOOP_LINEAR
	var blend_tree := AnimationNodeBlendTree.new()
	locomotion = AnimationNodeAnimation.new()
	locomotion.animation = idle
	upper_body = AnimationNodeAnimation.new()
	upper_body.animation = shoot
	animation_player.get_animation(shoot).loop_mode = Animation.LOOP_NONE
	var blend := AnimationNodeBlend2.new()
	blend.filter_enabled = true
	var clip := animation_player.get_animation(shoot)
	for track in range(clip.get_track_count()):
		var path := clip.track_get_path(track)
		if path.get_subname_count() > 0 and str(path.get_subname(0)) in ["Bone_00", "Bone_01", "Bone_05", "Bone_06", "Bone_07"] and clip.track_get_type(track) == Animation.TYPE_ROTATION_3D: blend.set_filter_path(path, true)
	blend_tree.add_node("Motion", locomotion)
	blend_tree.add_node("MotionSpeed", AnimationNodeTimeScale.new())
	blend_tree.add_node("MotionSeek", AnimationNodeTimeSeek.new())
	blend_tree.add_node("Arm", upper_body)
	blend_tree.add_node("ArmSeek", AnimationNodeTimeSeek.new())
	blend_tree.add_node("UpperBody", blend)
	blend_tree.connect_node("MotionSpeed", 0, "Motion")
	blend_tree.connect_node("MotionSeek", 0, "MotionSpeed")
	blend_tree.connect_node("ArmSeek", 0, "Arm")
	blend_tree.connect_node("UpperBody", 0, "MotionSeek")
	blend_tree.connect_node("UpperBody", 1, "ArmSeek")
	blend_tree.connect_node("output", 0, "UpperBody")
	motion_tree = AnimationTree.new()
	motion_tree.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_PHYSICS
	animation_player.get_parent().add_child(motion_tree)
	motion_tree.tree_root = blend_tree
	motion_tree.set("parameters/MotionSpeed/scale", 1.0)
	motion_tree.anim_player = motion_tree.get_path_to(animation_player)
	motion_tree.root_node = animation_player.root_node
	motion_tree.active = true
	var skeletons := player_model.find_children("*", "Skeleton3D", true, false)
	if not skeletons.is_empty():
		upper_modifier = preload("res://scripts/player/native_upper_body.gd").new()
		(skeletons[0] as Skeleton3D).add_child(upper_modifier)
		upper_modifier.tree = motion_tree
		upper_modifier.animations = animation_player
		upper_modifier.motion = locomotion
		for entry: Dictionary in metadata.get("clips", []): upper_modifier.clip_contexts[str(entry["name"])] = str(entry.get("context", ""))
	var muzzle: Variant = metadata.get("muzzle", {})
	if skeletons.is_empty() or not muzzle is Dictionary or not muzzle.has("position"): return
	var attachment := BoneAttachment3D.new()
	(skeletons[0] as Skeleton3D).add_child(attachment)
	attachment.bone_name = str(muzzle.get("bone", "Bone_04"))
	muzzle_node = Node3D.new()
	attachment.add_child(muzzle_node)
	var position: Array = muzzle["position"]
	muzzle_node.position = Vector3(float(position[0]), float(position[1]), float(position[2]))
	if upper_modifier != null: upper_modifier.muzzle_offset = muzzle_node.position
func _apply_native_materials() -> void:
	for node in player_model.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		for surface in range(mesh.mesh.get_surface_count()):
			var source := mesh.get_active_material(surface) as BaseMaterial3D
			if source == null: continue
			var material := ShaderMaterial.new()
			material.shader = preload("res://shaders/native_model.gdshader")
			material.set_shader_parameter("albedo_texture", source.albedo_texture)
			mesh.set_surface_override_material(surface, material)
func reset_at(point: Vector3) -> void:
	cancel_scripted_walk()
	ledge_phase = ""; ledge_ticks = 0; ledge_accumulator = 0.0
	if motion_tree != null: motion_tree.set("parameters/MotionSpeed/scale", 1.0)
	interaction_role = ""
	if is_instance_valid(carried_actor): carried_actor.release_lift(-player_model.global_basis.z, -768, -64)
	carried_actor = null
	special_action = ""
	_set_carry_filter(false)
	if upper_modifier != null: upper_modifier.active = true
	global_position = point
	camera_distance = -1.0
	camera_world_valid = false
	velocity = Vector3.ZERO
	shot_timer = 0.0
	shot_pose = 0.0
	gun_pose_active = false
	gun_pose_time = 0.0
	pending_shot = false
	hurt_phase = ""
	hurt_immunity = 0.0
	hurt_damage = 0
	hurt_hits = 0
	jump_phase = JumpPhase.GROUNDED
	jump_velocity = 0
	jump_accumulator = 0.0
	jump_ticks = 0
	# Arrivals and scenes disable physics right after placement, so set the idle pose now instead of waiting for the next movement tick.
	if hurt_phase.is_empty() and animation_player != null: _play_animation("idle")
	look_head_units = 0
	look_root_units = 0
	look_accumulator = 0.0
	if upper_modifier != null: upper_modifier.set_source_aim_angles(0, 0)
	camera_pivot.rotation = Vector3(deg_to_rad(-12), 0, 0)
	player_model.rotation.y = 0.0
	_play_animation("idle")
func take_hit(amount: int = 16, flags: int = 0, incoming: Vector3 = Vector3.ZERO) -> void:
	if invulnerable or hurt_immunity > 0 or not hurt_phase.is_empty() or health < 0: return
	if not ledge_phase.is_empty(): _release_ledge()
	if is_instance_valid(carried_actor): carried_actor.release_lift(-player_model.global_basis.z, -768, -64)
	carried_actor = null
	special_action = ""
	_set_carry_filter(false)
	if upper_modifier != null: upper_modifier.active = true
	hurt_damage += amount
	hurt_hits += 1
	var lethal := health - amount < 0
	health = maxi(health - amount, 0 if health > 0 else -1)
	health_changed.emit(maxi(health, 0), max_health)
	var strong := hurt_damage >= 28 or hurt_hits >= 4 or (flags & 0x80000) != 0 or not is_on_floor() or lethal
	var back := incoming.dot(Basis(Vector3.UP, player_model.rotation.y) * Vector3.FORWARD) > 0
	hurt_phase = "launch" if strong else "weak"
	hurt_clip = "clip_%03d" % ((38 if back else 34) if strong else (33 if back else 32))
	hurt_ticks = 0.0
	gun_pose_active = false
	pending_shot = false
	special_sound_requested.emit(0x97 if strong else 0x96)
	_play_hurt_clip()
func _play_hurt_clip() -> void:
	if animation_player == null or not animation_player.has_animation(hurt_clip): return
	if motion_tree != null:
		locomotion.animation = hurt_clip
		motion_tree.set("parameters/MotionSeek/seek_request", 0.0)
		motion_role = ""
	else: animation_player.play(hurt_clip)
func _update_hurt(delta: float) -> void:
	if hurt_phase.is_empty(): return
	hurt_ticks += delta * 30.0
	var info: Dictionary = native_clips.get(hurt_clip, {})
	var length := int(info.get("durationTicks", 0))
	if hurt_phase == "weak":
		var ticks := 0
		for record: Dictionary in info.get("records", []):
			if hurt_ticks < ticks + int(record["durationTicks"]):
				if int(record["pose"]) >= 5: hurt_phase = ""
				break
			ticks += int(record["durationTicks"])
	elif hurt_phase == "launch" and (is_on_floor() or hurt_ticks >= length):
		hurt_phase = "land"
		hurt_clip = "clip_039" if hurt_clip == "clip_038" else "clip_035"
		hurt_ticks = 0.0
		_play_hurt_clip()
		special_sound_requested.emit(0x99)
	elif hurt_phase == "land" and hurt_ticks >= length and health < 0:
		hurt_phase = "dead"
		died.emit()
	elif hurt_phase == "land" and hurt_ticks >= length:
		hurt_phase = "recover"
		hurt_clip = "clip_041" if hurt_clip == "clip_039" else "clip_037"
		hurt_ticks = 0.0
		_play_hurt_clip()
	elif hurt_phase == "recover" and hurt_ticks >= length:
		hurt_phase = ""
		hurt_immunity = 65.0 / 30.0
		hurt_damage = 0
		hurt_hits = 0
func refill_health() -> void:
	health = max_health
	health_changed.emit(health, max_health)
