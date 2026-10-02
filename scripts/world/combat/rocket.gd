extends Node3D
const TICK := 1.0 / 30.0
const SPEED_UNIT := 4096.0
const SIZE_UNIT := 256.0
const FLAGS := 0x40000
var data: Dictionary = {}
var player: CharacterBody3D
var damage := 0
var life := 0
var level := 0
var special := 0
var target: Node3D
var offset := Vector3.ZERO
var direction := Vector3.FORWARD
var speed := 0.0
var counter := 0
var armed := false
var turn := 0
var nearest := INF
var elapsed := 0.0
var history: Array[Vector3] = []
var trail: MeshInstance3D
var puffs: Node3D
var exploding := false
var blast := 0
var blast_size := 0
var blast_damage := 0
var blast_hit: Dictionary = {}
static func spawn(shot: Node, muzzle: Vector3, heading: Vector3, damage_value: int, range_ticks: float) -> void:
	var rocket := Node3D.new(); rocket.set_script(shot.bullet_script); rocket.set("data", shot.data); rocket.set("player", shot.player); rocket.set("damage", damage_value); rocket.set("life", int(range_ticks)); rocket.set("level", shot.level(shot.player.weapon_stats.ATTACK)); rocket.set("special", shot.level(4))
	var lock: Node3D = shot.aim_target
	if is_instance_valid(lock): rocket.set("target", lock); rocket.set("offset", muzzle + heading - lock.global_position)
	shot.player.get_parent().add_child(rocket); rocket.global_position = muzzle; rocket.set("direction", heading.normalized()); rocket.history.append(muzzle)
func _ready() -> void:
	var bullet: Dictionary = data["bullet"]; var steering: Dictionary = bullet["steering"]; speed = float(bullet["initialSpeedRaw"]); counter = int(steering.get("armDelayBase", steering.get("delayTicks", 0))) - (special if steering["kind"] == "ramp" else 0)
	var material := StandardMaterial3D.new(); material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED; material.vertex_color_use_as_albedo = true; material.cull_mode = BaseMaterial3D.CULL_DISABLED; material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED; material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD; material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if data["trail"]["kind"] == "ribbon": trail = MeshInstance3D.new(); trail.mesh = ImmediateMesh.new(); trail.top_level = true; trail.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; trail.material_override = material; add_child(trail)
	else:
		puffs = Node3D.new(); puffs.set_script(preload("res://scripts/world/combat/native_effect.gd")); get_parent().add_child(puffs); var polygons: Array = []
		for index in (data["trail"]["frames"] as Array).size(): var polygon: Dictionary = (data["trail"]["frames"][index] as Dictionary).duplicate(); polygon["anchor"] = index >> 1; polygons.append(polygon)
		puffs.set("looping", true); puffs.play([polygons], 1.0, data["explosion"]["pages"])
func _physics_process(delta: float) -> void:
	elapsed += delta
	while elapsed >= TICK:
		elapsed -= TICK
		if exploding: _blast_tick()
		else: _tick()
		if is_queued_for_deletion(): return
	if trail != null: _draw_trail()
func _tick() -> void:
	var bullet: Dictionary = data["bullet"]; var steering: Dictionary = bullet["steering"]
	if steering["kind"] == "ramp":
		if counter > 0:
			counter -= 1
			if counter == 0: armed = true
		turn = mini(turn + special + 1, int(steering["limit"]))
		if is_instance_valid(target): _steer(float((turn >> int(steering["divisorShift"])) << (int(steering["armedTurnShift"]) if armed else 0)) * TAU / 4096.0, float(steering["pitchFactor"]))
	elif is_instance_valid(target):
		if counter > 0: counter -= 1
		else:
			_steer(float(steering["yawRate"]) * TAU / 4096.0, float(steering["pitchFactor"])); var distance := (target.global_position + offset - global_position).length() * SIZE_UNIT
			if distance < nearest: nearest = distance
			elif nearest < float(steering["fuseDistanceRaw"]): _explode(global_position); return
	life -= 1
	if life <= 0: _explode(global_position); return
	for substep in int(bullet["substepsPerTick"]):
		var destination := global_position + direction * speed / SPEED_UNIT; var query := PhysicsRayQueryParameters3D.create(global_position, destination, 9); query.exclude = [player.get_rid()]; var hit := get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty():
			var collider := hit["collider"] as Node
			if collider != null and collider.has_method("receive_hit"): collider.receive_hit(damage, FLAGS, direction)
			elif collider != null and collider.has_method("take_hit"): collider.take_hit(damage)
			_explode(hit["position"]); return
		global_position = destination
	speed = minf(speed + float(bullet["accelerationRaw"]), float(bullet["maximumSpeedRaw"])); history.push_front(global_position)
	if history.size() > (int(data["trail"]["history"]) if data["trail"]["kind"] == "ribbon" else 8): history.pop_back()
	if puffs != null: puffs.set("anchors", history.duplicate())
func _steer(limit: float, pitch_factor: float) -> void:
	var goal := (target.global_position + offset - global_position).normalized(); var yaw := atan2(direction.x, direction.z); var pitch := asin(clampf(direction.y, -1.0, 1.0))
	yaw += clampf(wrapf(atan2(goal.x, goal.z) - yaw, -PI, PI), -limit, limit); pitch += clampf(asin(clampf(goal.y, -1.0, 1.0)) - pitch, -limit * pitch_factor, limit * pitch_factor)
	direction = Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
func _explode(point: Vector3) -> void:
	var explosion: Dictionary = data["explosion"]; exploding = true; global_position = point; blast_size = int(explosion["sizeBase"]) + (level << int(explosion["sizeShift"])); blast_damage = int(explosion["hitDamageBase"]) + (level << int(explosion["hitDamageShift"])); blast = 12
	var effect := Node3D.new(); effect.set_script(preload("res://scripts/world/combat/native_effect.gd")); get_parent().add_child(effect); effect.global_position = point; var variants: Array = explosion["variants"]; effect.play(variants[randi() % variants.size()], float(blast_size) / float(explosion["sizeBase"]), explosion["pages"])
	player.special_sound_requested.emit(int(explosion["sound"]))
	if trail != null: trail.mesh = ImmediateMesh.new()
	if puffs != null: puffs.queue_free()
func _blast_tick() -> void:
	var shape := SphereShape3D.new(); shape.radius = maxf(float((blast_size * (16 - blast)) >> 5) / SIZE_UNIT, 0.05); var query := PhysicsShapeQueryParameters3D.new(); query.shape = shape; query.transform = Transform3D(Basis.IDENTITY, global_position); query.collision_mask = 9
	for result: Dictionary in get_world_3d().direct_space_state.intersect_shape(query, 16):
		var collider := result["collider"] as Node
		if collider == null or blast_hit.has(collider.get_instance_id()) or not collider.has_method("receive_hit"): continue
		blast_hit[collider.get_instance_id()] = true; collider.receive_hit(blast_damage, FLAGS, Vector3.UP)
	blast -= 1
	if blast <= 0: queue_free()
func _corner(index: int, radius: float) -> Vector2: return [Vector2(-radius, -radius), Vector2(radius + 1.0, -radius), Vector2(radius + 1.0, radius + 1.0), Vector2(-radius, radius + 1.0)][index]
func _draw_trail() -> void:
	var mesh := trail.mesh as ImmediateMesh; mesh.clear_surfaces()
	var camera := get_viewport().get_camera_3d(); var settings: Dictionary = data["trail"]
	if camera == null or exploding or history.size() < 2: return
	var right := camera.global_basis.x / SIZE_UNIT; var up := camera.global_basis.y / SIZE_UNIT; var count := mini(history.size() - 1, int(settings["historyCap"])); var newer_radius := float(settings["headScale"][1])
	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	for segment in count:
		var newer := history[segment]; var older := history[segment + 1]; var older_radius := float(int(settings["segmentScale"][1]) * (int(settings["fade"]) - ((count - segment) >> 1)))
		var shade_old := (float(settings["colorOldEnd"]) - float(segment * int(settings["colorStep"]))) / 255.0; var shade_new := shade_old + float(int(settings["colorStep"])) / 255.0
		for wedge in [[0, false], [2, true], [1, false], [3, true]]:
			var old_corner := _corner(wedge[0], older_radius); var new_corner := _corner(wedge[0], newer_radius)
			var corner_old := older + right * old_corner.x - up * old_corner.y; var corner_new := newer + right * new_corner.x - up * new_corner.y
			var points := [corner_old, older, corner_new, newer] if not wedge[1] else [older, corner_old, newer, corner_new]
			var shades := [0.0, shade_old, 0.0, shade_new] if not wedge[1] else [shade_old, 0.0, shade_new, 0.0]
			for vertex in [0, 1, 2, 1, 2, 3]: mesh.surface_set_color(Color(shades[vertex], shades[vertex], shades[vertex])); mesh.surface_add_vertex(points[vertex])
		newer_radius = older_radius
	mesh.surface_end()
