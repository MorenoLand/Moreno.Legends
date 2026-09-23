extends CharacterBody3D
signal health_changed(value: int, maximum: int)
signal fired(projectile: Node3D)
const PROJECTILE_SCENE = preload("res://scenes/buster_projectile.tscn")

@export var move_speed := 2.2
@export var turn_speed := 2.3
@export var gravity := 9.0
@export var mouse_sensitivity := 0.003
@export var jump_speed := 3.5
@export var fire_interval := 0.18
@export var max_health := 10
@onready var camera_pivot: Node3D = $CameraPivot
@onready var camera: Camera3D = $CameraPivot/Camera3D
@onready var player_model: Node3D = $PlayerModel
var locked_target: Node3D
var health := 10
var shot_timer := 0.0
var shot_pose := 0.0
var animation_player: AnimationPlayer
var animation_roles: Dictionary = {}
var aiming := false
var body_height := 0.7
var motion_tree: AnimationTree
var locomotion: AnimationNodeAnimation
var upper_body: AnimationNodeAnimation
var motion_role := ""
var muzzle_node: Node3D
var arm_blend := 0.0

func _ready() -> void:
	if not OS.has_feature("web"): Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	camera.current = true
	if camera_pivot is SpringArm3D: (camera_pivot as SpringArm3D).add_excluded_object(get_rid())
	_fit_model()
	var players := player_model.find_children("*", "AnimationPlayer", true, false)
	if not players.is_empty(): animation_player = players[0] as AnimationPlayer
	var metadata: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/manifest.json"))
	if metadata is Dictionary: animation_roles = metadata.get("animations", {})
	_configure_animation_tree(metadata if metadata is Dictionary else {})
	health = max_health

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		get_viewport().set_input_as_handled()
	elif Input.mouse_mode == Input.MOUSE_MODE_VISIBLE and event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		get_viewport().set_input_as_handled()
		return
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		camera_pivot.rotation.y -= event.relative.x * mouse_sensitivity
		camera_pivot.rotation.x = clampf(camera_pivot.rotation.x - event.relative.y * mouse_sensitivity, deg_to_rad(-55.0), deg_to_rad(25.0))
		camera_pivot.rotation.z = 0.0

func _physics_process(delta: float) -> void:
	if locked_target != null and not is_instance_valid(locked_target): locked_target = null
	shot_timer = maxf(shot_timer - delta, 0.0)
	shot_pose = maxf(shot_pose - delta, 0.0)
	aiming = Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and Input.is_action_pressed("aim")
	if camera_pivot is SpringArm3D:
		var arm := camera_pivot as SpringArm3D
		arm.spring_length = lerpf(arm.spring_length, body_height * (1.8 if aiming else 3.4), minf(delta * 10, 1))
		arm.position.x = lerpf(arm.position.x, body_height * 0.3 if aiming else 0.0, minf(delta * 10, 1))
	camera_pivot.rotation.y -= Input.get_axis("turn_left", "turn_right") * turn_speed * delta
	var input_vector := Vector2(Input.get_axis("strafe_left", "strafe_right"), Input.get_axis("move_back", "move_forward"))
	var forward := -camera.global_basis.z
	forward.y = 0.0
	var right := camera.global_basis.x
	right.y = 0.0
	var direction := (right.normalized() * input_vector.x + forward.normalized() * input_vector.y).normalized()
	var speed := move_speed * (0.6 if aiming else 1.0)
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	if is_on_floor():
		velocity.y = jump_speed if Input.is_action_just_pressed("jump") else 0.0
	else: velocity.y -= gravity * delta
	move_and_slide()
	if aiming: player_model.rotation.y += clampf(wrapf(camera_pivot.rotation.y - player_model.rotation.y, -PI, PI), -4.5 * delta, 4.5 * delta)
	elif direction.length_squared() > 0.001 and shot_pose <= 0: player_model.rotation.y = lerp_angle(player_model.rotation.y, atan2(-direction.x, -direction.z), minf(delta * 12.0, 1.0))
	if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and Input.is_action_pressed("fire") and shot_timer <= 0: _fire()
	_play_animation("jump" if not is_on_floor() else "run" if direction.length_squared() > 0.001 else "idle")
	if motion_tree != null:
		arm_blend = move_toward(arm_blend, 1.0 if aiming or shot_pose > 0 else 0.0, delta * 12.0)
		motion_tree.set("parameters/UpperBody/blend_amount", arm_blend)
		if aiming and shot_pose <= 0: motion_tree.set("parameters/ArmSeek/seek_request", animation_player.get_animation(upper_body.animation).length * 0.4)

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
	if shot_timer > 0: return
	shot_timer = fire_interval
	shot_pose = 0.2
	if motion_tree != null: motion_tree.set("parameters/ArmSeek/seek_request", 0.0)
	var ray_start := camera.global_position
	var ray_direction := -camera.global_basis.z if aiming else Basis(Vector3.UP, player_model.rotation.y) * Vector3.FORWARD
	if is_instance_valid(locked_target): ray_direction = (locked_target.global_position + Vector3.UP - ray_start).normalized()
	var query := PhysicsRayQueryParameters3D.create(ray_start, ray_start + ray_direction * 80.0, 1)
	query.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	var aim: Vector3 = hit["position"] if not hit.is_empty() else ray_start + ray_direction * 80.0
	var muzzle := global_position + Vector3.UP * body_height * 0.7 + Basis(Vector3.UP, player_model.rotation.y) * Vector3(body_height * 0.22, 0, -body_height * 0.22)
	if muzzle_node != null: muzzle = muzzle_node.global_position
	var heading := aim - muzzle if aiming else ray_direction
	if aiming:
		var yaw := atan2(-heading.x, -heading.z)
		var limit := deg_to_rad(15.0)
		yaw = player_model.rotation.y + clampf(wrapf(yaw - player_model.rotation.y, -PI, PI), -limit, limit)
		heading = Vector3(-sin(yaw), heading.y / maxf(Vector2(heading.x, heading.z).length(), 0.001), -cos(yaw)).normalized()
	var chest := global_position + Vector3.UP * body_height * 0.7
	var obstruction := get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(chest, muzzle, 1))
	if not obstruction.is_empty():
		muzzle = chest
		heading = obstruction["position"] - chest
	var projectile := PROJECTILE_SCENE.instantiate() as Node3D
	get_tree().current_scene.add_child(projectile)
	projectile.launch(muzzle, heading)
	fired.emit(projectile)
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
func _configure_animation_tree(metadata: Dictionary) -> void:
	if animation_player == null or not animation_roles.has("idle") or not animation_roles.has("shoot"): return
	var idle := str(animation_roles["idle"])
	var shoot := str(animation_roles["shoot"])
	if not animation_player.has_animation(idle) or not animation_player.has_animation(shoot): return
	for role in ["idle", "run"]:
		var name := str(animation_roles.get(role, ""))
		if animation_player.has_animation(name): animation_player.get_animation(name).loop_mode = Animation.LOOP_LINEAR
	var blend_tree := AnimationNodeBlendTree.new()
	locomotion = AnimationNodeAnimation.new()
	locomotion.animation = idle
	upper_body = AnimationNodeAnimation.new()
	upper_body.animation = shoot
	var blend := AnimationNodeBlend2.new()
	blend.filter_enabled = true
	var clip := animation_player.get_animation(shoot)
	for track in range(clip.get_track_count()):
		var path := clip.track_get_path(track)
		if path.get_subname_count() > 0 and str(path.get_subname(0)) in ["Bone_02", "Bone_03", "Bone_04"]: blend.set_filter_path(path, true)
	blend_tree.add_node("Motion", locomotion)
	blend_tree.add_node("MotionSeek", AnimationNodeTimeSeek.new())
	blend_tree.add_node("Arm", upper_body)
	blend_tree.add_node("ArmSeek", AnimationNodeTimeSeek.new())
	blend_tree.add_node("UpperBody", blend)
	blend_tree.connect_node("MotionSeek", 0, "Motion")
	blend_tree.connect_node("ArmSeek", 0, "Arm")
	blend_tree.connect_node("UpperBody", 0, "MotionSeek")
	blend_tree.connect_node("UpperBody", 1, "ArmSeek")
	blend_tree.connect_node("output", 0, "UpperBody")
	motion_tree = AnimationTree.new()
	animation_player.get_parent().add_child(motion_tree)
	motion_tree.tree_root = blend_tree
	motion_tree.anim_player = motion_tree.get_path_to(animation_player)
	motion_tree.root_node = animation_player.root_node
	motion_tree.active = true
	var skeletons := player_model.find_children("*", "Skeleton3D", true, false)
	var muzzle: Variant = metadata.get("muzzle", {})
	if skeletons.is_empty() or not muzzle is Dictionary or not muzzle.has("position"): return
	var attachment := BoneAttachment3D.new()
	(skeletons[0] as Skeleton3D).add_child(attachment)
	attachment.bone_name = str(muzzle.get("bone", "Bone_04"))
	muzzle_node = Node3D.new()
	attachment.add_child(muzzle_node)
	var position: Array = muzzle["position"]
	muzzle_node.position = Vector3(float(position[0]), float(position[1]), float(position[2]))
func reset_at(position: Vector3) -> void:
	global_position = position
	velocity = Vector3.ZERO
	shot_timer = 0.0
	shot_pose = 0.0
	camera_pivot.rotation = Vector3(deg_to_rad(-12), 0, 0)
	player_model.rotation.y = 0.0
	_play_animation("idle")
func take_hit(amount: int = 1) -> void:
	health = clampi(health - amount, 0, max_health)
	health_changed.emit(health, max_health)
