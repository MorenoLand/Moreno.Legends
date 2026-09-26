extends Node
class_name NativeNpcBehavior
const Motion := preload("res://scripts/world/native_actor_motion.gd")
const RNG_MASK := 0xFFFFFFFF
static var shared_rng_state := 0
static var shared_rng_initialized := false
var actor: Node3D
var profile: Dictionary = {}
var native_context: Dictionary = {}
var nodes_raw: Array = []
var current_node := 0
var previous_node := 0
var elapsed := 0.0
var clock: Node
func configure(target: Node3D, source_profile: Dictionary, context: Dictionary = {}) -> void:
	actor = target; profile = source_profile.duplicate(true); native_context = context; nodes_raw = profile.get("nodes_raw", []); current_node = clampi(int(profile.get("source_route_index", 0)), 0, maxi(0, nodes_raw.size() - 1)); previous_node = current_node; clock = actor.get_node_or_null("NativeAnimationClock")
	if is_instance_valid(clock): clock.set("automatic", false); clock.call("play_control", int(profile.get("animation_control", 1)), 0)
	set_physics_process(true)
func _physics_process(delta: float) -> void:
	if not is_instance_valid(actor) or str(profile.get("kind", "")) != "route_graph": return
	elapsed += delta * 25.0
	while elapsed >= 1.0: elapsed -= 1.0; _native_tick()
func _native_tick() -> void:
	if not nodes_raw.is_empty() and current_node >= 0 and current_node < nodes_raw.size():
		var target_node: Dictionary = nodes_raw[current_node]; var native_x := -actor.position.x * 256.0; var native_z := actor.position.z * 256.0; var delta_x := float(target_node.get("x", 0)) - native_x; var delta_z := float(target_node.get("z", 0)) - native_z
		if delta_x >= -128.0 and delta_x < 128.0 and delta_z >= -128.0 and delta_z < 128.0: _select_next_node(target_node)
		else:
			var direction := Vector3(-delta_x, 0.0, delta_z).normalized(); var desired_yaw := atan2(direction.x, direction.z) + PI; var yaw_delta := desired_yaw - actor.rotation.y
			while yaw_delta > PI: yaw_delta -= TAU
			while yaw_delta < -PI: yaw_delta += TAU
			actor.rotation.y += clampf(yaw_delta, -float(profile.get("turn_step_raw", 24)) * TAU / 4096.0, float(profile.get("turn_step_raw", 24)) * TAU / 4096.0)
			var velocity_raw := int(profile.get("velocity_raw", -int(profile.get("speed_raw", 64)))); var motion := Vector3(-sin(actor.rotation.y), 0.0, -cos(actor.rotation.y)) * float(absi(velocity_raw)) / 4096.0
			Motion.move_actor(actor, motion, profile.get("collision_bounds_raw", []))
	if is_instance_valid(clock): clock.call("native_tick")
func _select_next_node(node: Dictionary) -> void:
	var links: Array = []
	for link in node.get("links", []):
		if int(link) >= 0 and int(link) < nodes_raw.size(): links.append(int(link))
	if links.is_empty(): return
	var selected_index := 0
	if links.size() > 1:
		selected_index = (next_random(native_context) & 0xFFFF) % links.size()
	if links.size() > 1 and int(links[selected_index]) == previous_node: selected_index = (selected_index + 1) % links.size()
	previous_node = current_node; current_node = int(links[selected_index])
static func next_random(context: Dictionary) -> int:
	var state := int(shared_rng_state if shared_rng_initialized else context.get("native_rng_state", Time.get_ticks_usec())) & RNG_MASK; state = (((state << 1) + (state >> 31) + 1) ^ 0x873CA9E5) & RNG_MASK; shared_rng_state = state; shared_rng_initialized = true; context["native_rng_state"] = state; return state
