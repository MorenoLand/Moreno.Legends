extends Node
## Runs the original game code of an opted-in stage (assets/runner/manifest.json "attach") beside the port: the port's player, flags and messages feed the emulated game, and its actors, scenes, camera, sound and stage requests drive the port.

const Props := preload("res://scripts/world/actors/native_props.gd")
const Machine := preload("res://scripts/runner/mips_machine.gd")
const Effects := preload("res://scripts/runner/runner_effects.gd")
const Session := preload("res://scripts/runner/runner_session.gd")
const View := preload("res://scripts/runner/runner_actor_view.gd")
const Barriers := preload("res://scripts/runner/runner_barriers.gd")
const PlayerScene := preload("res://scripts/runner/runner_player_scene.gd")
const DIRECTORY := "res://assets/runner/"
const PLAYER := 0x8008C0A0
const POINT_LENGTH := 0.25
const POINT_RADIUS := 1.0
## The resolver reports a hit to the attacker through the word its registration points at (the launcher's +0xDC): the struck body's own record word, 0x20008 for an enemy body.
const HIT_FEEDBACK := 0x20008
const PLAYER_SHOT := 0x40000
## Weapons whose launcher lives only while the special button is held (module state 0x8010A108 tests player +0x13C bit 0x40 and pad held +0x10E against the fire mask +0x130).
const HOLD_WEAPONS := [8, 12, 17]
const RAW_PER_METER := 256.0
const BLADE := 11
const PAD_MASK := 0x100
const HOLD_MASK := 0x100
const SCENE_ACTIVE := 0x8007CEC0
## Pad words the original reads: buttons pressed this frame (bit 3 is Start, which GAME 0x800C10B4 turns into a scene skip) and how many ticks the port holds it, so a tap is seen on both parities of the scratch frame byte the skip tests.
const PAD_PRESSED := 0x8009BEEC
const START_MASK := 0x8
const START_TICKS := 3
## The game mode word (GAME block +0) the runner's frames settle at, and the field mode the skip test GAME 0x800C10B4 requires.
const FIELD_IDLE := 0x200
const FIELD_RUNNING := 0x203
const REQUEST := 0x80078D08
const FLAG_BYTES := 256
const NATIVE_HZ := 25.0
const CAMERA_DISTANCE := 1024
const DOORS := [0x161, 0x261, 0x361]
const RADIO_WINDOW := 4
const EXAMINE_REACH := 512.0
const STORY_BYTE := 0x8009C7FD
const BANK_POINTER := 0x1F800074
const SHAKE := 0x800750E8
const EFFECT_MESH_SKEW := 0x24
const HIT_FIRST := 0x1D4
const HIT_SECOND := 0x1E4
const HIT_SOURCE := 0x1DC
## Model keys of the sub-stage bank start here.
const SUB_KEY := 0x10000

var gameplay: Node
var level: Node3D
var stage := ""
var area := 0
var session: Session
var manifest := {}
var animations: Dictionary = {}
var views: Dictionary = {}
var elapsed := 0.0
var flags_shadow := PackedByteArray()
var scene_mode := false
var scene_camera: Camera3D
var camera_state: Array = []
var boss_view: Node3D
var barriers := Barriers.new()
var player_scene: Node
var port_classes: Array = []
var last_story := 0
var last_committed := 0
var bank_animations: Dictionary = {}
var interact_held := false
var own_request := false
var pending_shots: Array = []
var pending_area := -1
var scene_grace := 0
var player_control := -1
var finished := false
var busy := false
var loader: Thread
var effects: CanvasLayer
var pending_story := 0
var job: Thread
var ticking := false
var closing: Array = []
var hold_released := false
var requested_area := -1
var grab_view: Node3D
var built: Array = []
var shake := 0
var holding := 0
var start_ticks := 0
## Blade Arm combo: the shot controller (special_blade.gd) sets the press and the tank here and reads the original handler's answer (control, animation frame, tank, done).
var combo: Dictionary = {}

static func _level_of(gameplay: Node, stage_name: String, area_index: int) -> Node3D:
	return gameplay.room_stream.room_root(stage_name, area_index) if gameplay.streaming_rooms else gameplay.level

static func attach(parent: Node3D, stage_name: String, area_index: int, context: Dictionary) -> void:
	var data := Props._read_manifest(DIRECTORY + "manifest.json")
	var entry: Dictionary = data.get("stages", {}).get(stage_name, {})
	var rule: Dictionary = entry.get("attach", {})
	if not bool(rule.get("enabled", false)):
		return
	if int(context["native_save_byte14"]) < int(rule.get("min_story", 0)):
		return
	var gameplay: Node = parent
	while gameplay != null and gameplay.get_node_or_null("Player") == null:
		gameplay = gameplay.get_parent()
	if gameplay == null or parent != _level_of(gameplay, stage_name, area_index):
		return
	var existing := gameplay.get_node_or_null("RunnerHost")
	if existing != null:
		existing.level_loaded(parent, area_index)
		return
	var host := new()
	host.name = "RunnerHost"
	host.gameplay = gameplay
	host.stage = stage_name
	host.manifest = entry
	gameplay.add_child(host)
	host.start(parent, area_index, int(context["native_save_byte14"]))

func start(parent: Node3D, area_index: int, story: int) -> void:
	level = parent
	area = area_index
	pending_story = story
	session = Session.new()
	loader = Thread.new()
	loader.start(_open_worker)

func _open_worker() -> bool:
	return session.open(stage)

func _loaded() -> void:
	var opened: bool = loader.wait_to_finish()
	loader = null
	if not is_instance_valid(level):
		level = _level_of(gameplay, stage, area)
	if not opened:
		push_error("Runner: cannot open stage " + stage)
		finished = true
		return
	session.hle.bridge.manual = true
	effects = Effects.new()
	effects.name = "RunnerEffects"
	add_child(effects)
	effects.configure(DIRECTORY + str(manifest["vram"]))
	session.hle.bridge.grab_handler = Callable(self, "_grab")
	gameplay.player.hold_ended.connect(_hold_ended)
	port_classes = manifest["attach"]["port_classes"]
	barriers.load_stage(stage)
	for scene in manifest["attach"]["port_scenes"]:
		session.hle.bridge.blocked_scenes[int(scene)] = true
	var flags: Dictionary = gameplay.native_context.get("event_flags", {})
	area = int(gameplay.get_meta("runner_start_area", area))
	_read_animations(str(manifest["models_directory"]), animations)
	if manifest.has("bank1"):
		_read_animations(str(manifest["bank1"]["models_directory"]), bank_animations)
	session.begin(int(("0x" + stage.substr(2)).hex_to_int()), area, pending_story, flags)
	flags_shadow = session.read_flags()
	_stop_on_fault()
	last_story = pending_story
	last_committed = pending_story
	_sync_player_in()

func _exit_tree() -> void:
	if loader != null:
		loader.wait_to_finish()
	_join()

func _join() -> void:
	if job != null and job.is_started():
		job.wait_to_finish()

## Animation tables of an exported model bank's models.
func _read_animations(directory: String, into: Dictionary) -> void:
	var section := DIRECTORY.path_join("../levels/%s/models/%s/manifest.json" % [stage, directory]).simplify_path()
	for model: Dictionary in Props._read_manifest(section).get("models", []):
		if model.get("status", "") == "exported":
			into[int(model["index"])] = model["export"].get("animations", [])

func level_loaded(parent: Node3D, area_index: int) -> void:
	level = parent
	for view in views.values():
		if is_instance_valid(view):
			view.queue_free()
	views.clear()
	barriers.clear()
	boss_view = null
	if loader != null:
		area = area_index
		return
	if area_index != area:
		area = area_index
		pending_area = area_index
		requested_area = area_index

func _request_area(area_index: int) -> void:
	var machine: Machine = session.machine
	_sync_player_in()
	own_request = true
	machine.put8(REQUEST, 0xFF)
	machine.put8(REQUEST + 5, area_index)
	machine.put16(REQUEST + 8, 0)
	machine.put16(REQUEST + 0xC, 0)
	machine.put16(REQUEST + 0x10, machine.s16(PLAYER + 0x12))
	machine.put16(REQUEST + 0x12, machine.s16(PLAYER + 0x16))
	machine.put16(REQUEST + 0x14, machine.s16(PLAYER + 0x1A))

func _physics_process(delta: float) -> void:
	if loader != null:
		if not loader.is_alive():
			_loaded()
		return
	if not is_instance_valid(gameplay):
		return
	if not is_instance_valid(level):
		level = _level_of(gameplay, stage, area)
	if finished or busy or session == null or not is_instance_valid(level):
		return
	if not gameplay.preparation_finished or not gameplay.playable or gameplay.loading and not scene_mode or gameplay.native_scenes.active:
		return
	if not scene_mode and (bool(gameplay.dialogue_box.get("active")) and int(gameplay.event_script.active_window_state.get("window", 0)) != RADIO_WINDOW or not gameplay.player.is_physics_processing()):
		return
	if scene_mode and Input.is_action_just_pressed("ui_cancel"):
		start_ticks = START_TICKS
	elapsed += delta * NATIVE_HZ
	if ticking:
		elapsed = minf(elapsed, 2.0)
		return
	while elapsed >= 1.0 and not busy and not finished:
		elapsed -= 1.0
		ticking = true
		await _tick()
		ticking = false

func _flush_ports() -> void:
	var machine: Machine = session.machine
	for view in views.values():
		if is_instance_valid(view):
			view.flush_hits()
	for window: int in closing:
		if window >= 0:
			session.hle.bridge.windows.erase(window)
		else:
			session.hle.bridge.windows.clear()
	closing.clear()
	if hold_released:
		hold_released = false
		machine.put8(PLAYER + 9, 0)
		machine.put32(PLAYER + 0x2AC, 0)
	if requested_area >= 0:
		var wanted := requested_area
		requested_area = -1
		_request_area(wanted)

## The original frame and the render phase run on a worker thread while the port keeps drawing; the port side only touches the emulated memory before and after it.
func _frame(view: Array) -> void:
	job = Thread.new()
	if job.start(_work.bind(view)) != OK:
		_work(view)
		return
	while job.is_alive() and is_inside_tree():
		await get_tree().physics_frame
	_join()

func _work(view: Array) -> void:
	session.frame()
	built = effects.build(session.render(), session.gte_projection(), view[0], view[1]) if not view.is_empty() else []

func _tick() -> void:
	var machine: Machine = session.machine
	_flush_ports()
	if not scene_mode:
		_sync_player_in()
	machine.put8(PLAYER + 0x9F, machine.u8(PLAYER + 0x9F) | 0x80 if scene_mode or gameplay.player.is_on_floor() else machine.u8(PLAYER + 0x9F) & 0x7F)
	_sync_flags_in()
	var allow_request := scene_mode or scene_grace > 0 or own_request
	scene_grace = maxi(scene_grace - 1, 0)
	var voice: AudioStreamPlayer = gameplay.voice
	session.hle.bridge.xa_active = gameplay.voice_loading or is_instance_valid(voice) and voice.playing
	_port_camera()
	_fire_pending()
	_examine()
	var mode := machine.u16(Session.GAME_BLOCK)
	if start_ticks > 0:
		start_ticks -= 1
		machine.put16(PAD_PRESSED, START_MASK)
		if mode == FIELD_IDLE:
			machine.put16(Session.GAME_BLOCK, FIELD_RUNNING)
	var camera := _view_camera()
	await _frame([camera.fov, get_viewport().get_visible_rect().size] if camera != null else [])
	if not is_inside_tree() or finished:
		return
	machine.put16(PAD_PRESSED, 0)
	if machine.u16(Session.GAME_BLOCK) == FIELD_RUNNING and mode == FIELD_IDLE:
		machine.put16(Session.GAME_BLOCK, mode)
	if grab_view != null:
		if not gameplay.player.begin_hold(grab_view, {}):
			machine.put8(PLAYER + 9, 0)
		grab_view = null
	own_request = false
	if machine.u8(REQUEST) != 0 and not allow_request:
		machine.put8(REQUEST, 0)
	_sync_flags_out()
	var story: int = machine.u8(STORY_BYTE)
	if story != last_story:
		last_story = story
		gameplay.native_context["native_save_byte15"] = story
	var committed: int = machine.u8(Session.STORY_PENDING)
	if committed != last_committed:
		last_committed = committed
		gameplay.native_context["native_save_byte14"] = committed
	_forward_hits()
	_bridge_segments()
	_sync_actors()
	barriers.sync(machine, level, area)
	_drain_bridge()
	_shake()
	if camera != null:
		effects.show_batches(built)
	var active: bool = machine.u8(SCENE_ACTIVE) != 0
	if active and not scene_mode:
		_begin_scene()
	elif scene_mode and not active:
		_end_scene()
	elif scene_mode:
		_sync_player_out()
		_sync_player_pose()
		if player_scene != null:
			player_scene.sync(machine)
		_apply_camera()
	var runner_area: int = machine.u8(Session.AREA_BYTE)
	if pending_area >= 0:
		if runner_area == pending_area:
			pending_area = -1
	elif runner_area != area and not busy:
		_change_area(runner_area)
	elif machine.u8(REQUEST) == 2 and not busy:
		_stage_request()
	_stop_on_fault()

## The original camera code shakes by subtracting the magnitude from the focus height (SLES 0x80016B1C sets magnitude and decay); the port's camera takes the same value while the original code does not drive the camera.
func _shake() -> void:
	var machine: Machine = session.machine
	var raw := machine.s16(SHAKE)
	if raw > shake and not scene_mode:
		gameplay.player.camera_shake(0, raw, machine.s16(SHAKE + 4))
	shake = raw

func _view_camera() -> Camera3D:
	return get_viewport().get_camera_3d() if scene_mode else gameplay.player.camera

func _stop_on_fault() -> void:
	var faults: Array = session.faults()
	if faults.is_empty() or finished:
		return
	push_error("Runner: unresolved code 0x%08X in %s area %d; the runner stops here" % [int(faults[0]) & 0xFFFFFFFF, stage, area])
	finished = true
	for view in views.values():
		if is_instance_valid(view):
			view.queue_free()
	views.clear()
	if scene_mode:
		_end_scene()

## A shot of the port's special-weapon sequence (special_shot.gd) that the original module supplies: the muzzle and heading come from the port, the original spawns its projectile exactly as at the fire pose (GAME 0x800CE5D4 allocates the launcher actor of the weapon's class).
func fire_weapon(weapon_id: int, muzzle: Vector3, heading: Vector3) -> void:
	pending_shots.append([weapon_id, muzzle, heading])


func _fire_pending() -> void:
	_hold_weapon()
	_combo()
	for shot: Array in pending_shots:
		var id: int = shot[0]
		if id in HOLD_WEAPONS and holding == id:
			continue
		if _spawn_launcher(id, shot[1] as Vector3, shot[2] as Vector3) and id in HOLD_WEAPONS:
			holding = id
			_hold_weapon()
	pending_shots.clear()


## Runs the special-slot spawn consumer (GAME 0x800CE5D4) for a weapon: levels, muzzle and heading go into the player struct first.
func _spawn_launcher(id: int, muzzle: Vector3, heading_world: Vector3) -> bool:
	var machine: Machine = session.machine
	if not session.equip_weapon(id):
		return false
	for stat in 5:
		machine.put8(PLAYER + 0x1F4 + 8 * id + stat, gameplay.player.special_level(id, stat))
	var local := level.to_local(muzzle)
	var raw := Vector3(-local.x, -local.y, local.z) * RAW_PER_METER
	for offset in [0x164, 0x16C]:
		machine.put16(PLAYER + offset, roundi(raw.x))
		machine.put16(PLAYER + offset + 2, roundi(raw.y))
		machine.put16(PLAYER + offset + 4, roundi(raw.z))
	var heading := level.global_basis.inverse() * heading_world
	machine.put16(PLAYER + 0x2A, roundi(-atan2(-heading.x, -heading.z) * 4096.0 / TAU) & 4095)
	machine.put8(PLAYER + 0x18C, id)
	machine.put16(PLAYER + 0x13C, machine.u16(PLAYER + 0x13C) | 0x10)
	machine.call_function(0x800CE5D4, PLAYER)
	machine.put16(PLAYER + 0x13C, machine.u16(PLAYER + 0x13C) & ~0x10)
	return true


func _hold_weapon() -> void:
	if holding == 0:
		return
	var machine: Machine = session.machine
	if not Input.is_action_pressed("special") or scene_mode:
		holding = 0
		machine.put16(PLAYER + 0x10E, 0)
		machine.put16(0x8009BEC0 + 0x28, 0)
		machine.put16(PLAYER + 0x13C, machine.u16(PLAYER + 0x13C) & ~0x40)
		return
	machine.put16(PLAYER + 0x130, HOLD_MASK)
	machine.put16(PLAYER + 0x10E, HOLD_MASK)
	machine.put16(0x8009BEC0 + 0x28, HOLD_MASK)
	machine.put16(PLAYER + 0x13C, machine.u16(PLAYER + 0x13C) | 0x40)
	if holding == 8:
		_vacuum()

## The Blade Arm's sequence handler (GAME 0x800CEC94) is a combo state machine on player +0x13E: it reads the animation frame (+0x9C), the finished flag (+0x9F, -1) and the pad press (+0x110 against the fire mask +0x130), spends tank (+0x19A by +0x198), starts the next swing by setting the player control (+0xA0 through 0x8003F2A8) and keeps +0xC8 non-zero while the blade swings. It runs here once per original tick on the state the shot controller reports; the launcher is spawned when it raises +0x13C bit 0x10, and its blade points (+0x4A8, +0x4B0) come from the port's arm bones.
func _combo() -> void:
	if not combo.get("active", false):
		return
	var machine: Machine = session.machine
	if not combo.get("started", false):
		if not session.equip_weapon(BLADE):
			combo["active"] = false
			return
		combo["started"] = true
		for stat in 5:
			machine.put8(PLAYER + 0x1F4 + 8 * BLADE + stat, gameplay.player.special_level(BLADE, stat))
		machine.put8(PLAYER + 0x18C, BLADE)
		machine.put8(PLAYER + 0x13E, 0)
		machine.put8(PLAYER + 0xA0, int(combo["control"]))
		for offset in [0x38, 0x3A, 0x3C, 0x50]:
			machine.put16(PLAYER + offset, 0)
		machine.put16(PLAYER + 0x130, PAD_MASK)
	var ticks: int = int(gameplay.player.shots[BLADE].data["combo"]["controls"][str(int(combo["control"]))])
	var finished: bool = int(combo["frame"]) >= ticks
	machine.put8(PLAYER + 0x9C, mini(int(combo["frame"]), 127))
	machine.put8(PLAYER + 0x9F, 0xFF if finished else 0)
	machine.put16(PLAYER + 0x110, PAD_MASK if combo["pressed"] else 0)
	combo["pressed"] = false
	machine.put16(PLAYER + 0x198, int(combo["cost"]))
	machine.put16(PLAYER + 0x19A, int(combo["tank"]))
	_blade_points()
	var phase: int = machine.u8(PLAYER + 0x13E)
	session.hle.bridge.drive_blade = true
	machine.call_function(0x800CEC94, PLAYER)
	session.hle.bridge.drive_blade = false
	combo["frame"] = int(combo["frame"]) + 1
	if machine.u8(PLAYER + 0xA0) != int(combo["control"]):
		combo["control"] = machine.u8(PLAYER + 0xA0)
		combo["frame"] = 0
	combo["tank"] = machine.s16(PLAYER + 0x19A)
	_combo_flight()
	combo["velocity"] = Vector3(machine.s16(PLAYER + 0x38), machine.s16(PLAYER + 0x3A), machine.s16(PLAYER + 0x3C))
	if machine.u16(PLAYER + 0x13C) & 0x10 != 0:
		_spawn_launcher(BLADE, combo["muzzle"], combo["heading"])
	if phase == 9 and finished:
		combo["done"] = true
		combo["active"] = false
		combo["velocity"] = Vector3.ZERO
		machine.put8(PLAYER + 0xC8, 0)
		machine.put16(PLAYER + 0x13C, machine.u16(PLAYER + 0x13C) & ~0x3F38)


## The jump slash (control 98) leaves the ground with +0x50 set and the vertical speed +0x3A (negative is up) that the handler changes by 0x30 a tick; the original lands the player when the integrated height returns to zero and clears +0x50. The port's player does not leave the ground, so the same integral decides the landing.
func _combo_flight() -> void:
	var machine: Machine = session.machine
	if machine.u8(PLAYER + 0x50) == 0:
		combo["height"] = 0
		return
	combo["height"] = int(combo.get("height", 0)) + machine.s16(PLAYER + 0x3A)
	if int(combo["height"]) >= 0 and machine.s16(PLAYER + 0x3A) > 0:
		machine.put8(PLAYER + 0x50, 0)
		machine.put16(PLAYER + 0x3A, 0)
		combo["height"] = 0


func _blade_points() -> void:
	var machine: Machine = session.machine
	var skeleton := gameplay.player.upper_modifier.get_parent() as Skeleton3D
	for index in 2:
		var bone := skeleton.get_bone_global_pose(skeleton.find_bone("Bone_03" if index == 0 else "Bone_04")).origin
		var local := level.to_local(skeleton.global_transform * bone)
		var raw := Vector3(-local.x, -local.y, local.z) * RAW_PER_METER
		machine.put16(PLAYER + 0x4A8 + 8 * index, roundi(raw.x))
		machine.put16(PLAYER + 0x4AA + 8 * index, roundi(raw.y))
		machine.put16(PLAYER + 0x4AC + 8 * index, roundi(raw.z))


## The Vacuum Arm sets player +0xCA bit 2 while held; each pickup actor then runs GAME 0x800D15B8: within the range of the weapon's range stat (GAME 0x800CF440, raw units) it moves toward the player by (pull stat + 1) * 128 raw units a tick, or jumps onto the player at pull level 3. The port's pickups are port-owned, so the same rule moves them here.
func _vacuum() -> void:
	var player: CharacterBody3D = gameplay.player
	var pickups: Node = gameplay.get("pickups")
	if not is_instance_valid(pickups):
		return
	var raw_reach: int = session.machine.call_function(0x800CF440, PLAYER, 8) & 0xFFFF
	var reach := float(raw_reach - 0x10000 if raw_reach >= 0x8000 else raw_reach) / RAW_PER_METER
	var pull: int = player.special_level(8, 4)
	for pickup: Node3D in pickups.get_children():
		var offset := player.global_position - pickup.global_position
		if pickup.get("taken") or offset.length() > reach:
			continue
		pickup.global_position += offset if pull >= 3 else offset.normalized() * minf(float(pull + 1) * 128.0 / RAW_PER_METER, offset.length())

func _bridge_segments() -> void:
	var segments: Array = session.hle.bridge.segments.duplicate()
	session.hle.bridge.segments.clear()
	if segments.is_empty():
		return
	var space := level.get_world_3d().direct_space_state
	var machine: Machine = session.machine
	for segment: Dictionary in segments:
		var word: int = int(segment["word"]) & 0xFFFFFFFF
		if word & PLAYER_SHOT == 0 and word & 0xA0000 != 0x80000:
			continue
		var start := level.to_global(Vector3(-segment["start"].x, -segment["start"].y, segment["start"].z) / 256.0)
		var finish := level.to_global(Vector3(-segment["end"].x, -segment["end"].y, segment["end"].z) / 256.0)
		var excluded: Array[RID] = []
		for view in views.values():
			if is_instance_valid(view):
				excluded.append(view.get_rid())
		var targets: Array = []
		if start.distance_to(finish) < POINT_LENGTH:
			var sphere := PhysicsShapeQueryParameters3D.new()
			sphere.shape = SphereShape3D.new()
			sphere.shape.radius = POINT_RADIUS
			sphere.transform = Transform3D(Basis.IDENTITY, start)
			sphere.collision_mask = 8
			sphere.exclude = excluded
			for found: Dictionary in space.intersect_shape(sphere, 8):
				targets.append(found["collider"])
		else:
			var query := PhysicsRayQueryParameters3D.create(start, finish, 8)
			query.exclude = excluded
			var hit := space.intersect_ray(query)
			if not hit.is_empty():
				targets.append(hit["collider"])
		targets = targets.filter(func(body: Object) -> bool: return body.has_method("receive_hit"))
		if targets.is_empty():
			continue
		for body: Object in targets:
			body.receive_hit(word & 0xFFF, word & 0xFFFFF000, (finish - start).normalized())
		machine.put32(int(segment["owner"]) & 0xFFFFFFFF, HIT_FEEDBACK)

func _port_camera() -> void:
	var camera := _view_camera()
	if scene_mode or camera == null:
		session.hle.bridge.camera_override = []
		return
	var eye := level.to_local(camera.global_position)
	var forward := (level.global_basis.inverse() * -camera.global_basis.z).normalized()
	var direction := Vector3(-forward.x, -forward.y, forward.z)
	var focus := Vector3(-eye.x, -eye.y, eye.z) * 256.0 + direction * float(CAMERA_DISTANCE)
	var pitch := roundi(asin(clampf(direction.y, -1.0, 1.0)) * 4096.0 / TAU) & 4095
	var yaw := roundi(atan2(direction.x, direction.z) * 4096.0 / TAU) & 4095
	session.hle.bridge.camera_override = [Vector3i(roundi(focus.x), roundi(focus.y), roundi(focus.z)), CAMERA_DISTANCE, yaw, pitch, 0]

## Examine objects (terminals, switches: GAME 0x800D0154) run when the player's selection word (+0x1D0) holds their address with bit 24 set. Actors raise +0x60 to 1 while the player faces them in reach; the interact button selects the nearest of those for one tick.
func _examine() -> void:
	var machine: Machine = session.machine
	machine.put32(PLAYER + 0x1D0, 0)
	if scene_mode or not Input.is_action_just_pressed("interact") or bool(gameplay.dialogue_box.get("active")):
		return
	var best := 0
	var nearest := EXAMINE_REACH
	for actor: int in session.actor_slots():
		if machine.u8(actor + 0x60) != 1:
			continue
		var reach := Vector2(machine.s16(actor + 0x12) - machine.s16(PLAYER + 0x12), machine.s16(actor + 0x1A) - machine.s16(PLAYER + 0x1A)).length()
		if reach < nearest:
			nearest = reach
			best = actor
	if best != 0:
		machine.put32(PLAYER + 0x1D0, (best & 0xFFFFFF) | 0x1000000)

func _sync_player_in() -> void:
	var machine: Machine = session.machine
	var local := level.to_local(gameplay.player.global_position)
	machine.put32(PLAYER + 0x10, roundi(-local.x * 256.0 * 65536.0))
	machine.put32(PLAYER + 0x14, roundi(-local.y * 256.0 * 65536.0))
	machine.put32(PLAYER + 0x18, roundi(local.z * 256.0 * 65536.0))
	machine.put16(PLAYER + 0x2A, roundi(-gameplay.player.player_model.rotation.y * 4096.0 / TAU) & 4095)

func _sync_player_pose() -> void:
	var control: int = session.machine.u8(PLAYER + 0xA0)
	if control == player_control:
		return
	player_control = control
	var clip := "clip_%03d" % control
	if gameplay.player.native_clips.has(clip):
		gameplay.player.call("_play_ledge_clip", clip)

func _sync_player_out() -> void:
	var machine: Machine = session.machine
	var point := Vector3(-machine.s16(PLAYER + 0x12), -machine.s16(PLAYER + 0x16), machine.s16(PLAYER + 0x1A)) / 256.0
	gameplay.player.global_position = level.to_global(point)
	gameplay.player.player_model.rotation.y = -float(machine.s16(PLAYER + 0x2A) & 4095) * TAU / 4096.0

func _grab(actor: int, reach: int, _mode: int) -> int:
	var machine: Machine = session.machine
	var view = views.get(actor)
	if view == null or not is_instance_valid(view) or gameplay.player.holder != null:
		return 0
	for offset in [0x12, 0x16, 0x1A]:
		if absi(machine.s16(actor + offset) - machine.s16(PLAYER + offset)) > reach:
			return 0
	grab_view = view
	machine.put8(PLAYER + 9, 0x11)
	return 1

func _hold_ended(_holder: Node3D, _escaped: bool) -> void:
	hold_released = true

func _forward_hits() -> void:
	var machine: Machine = session.machine
	if gameplay.player.holder == null:
		machine.put8(PLAYER + 9, 0)
	var first := machine.u32(PLAYER + HIT_FIRST)
	var second := machine.u32(PLAYER + HIT_SECOND)
	machine.put32(PLAYER + HIT_FIRST, 0)
	machine.put32(PLAYER + HIT_SECOND, 0)
	var damage := (first & 0xFFF) + (second & 0xFFF)
	if damage == 0 or gameplay.player.no_clip:
		return
	var source := level.to_global(Vector3(-machine.s16(PLAYER + HIT_SOURCE), -machine.s16(PLAYER + HIT_SOURCE + 2), machine.s16(PLAYER + HIT_SOURCE + 4)) / 256.0)
	gameplay.player.take_hit(damage, (first | second) & 0xFFFFF000, gameplay.player.global_position - source)

func _sync_flags_in() -> void:
	var flags: Dictionary = gameplay.native_context.get("event_flags", {})
	var seen := {}
	for key in flags:
		var id := int(key)
		if id < 0 or id >= FLAG_BYTES * 8:
			continue
		seen[id] = true
		var held: bool = flags_shadow[id >> 3] & (1 << (id & 7)) != 0
		if bool(flags[key]) != held:
			_set_runner_flag(id, bool(flags[key]))
	for id in FLAG_BYTES * 8:
		if flags_shadow[id >> 3] & (1 << (id & 7)) != 0 and not seen.has(id):
			_set_runner_flag(id, false)

func _set_runner_flag(id: int, value: bool) -> void:
	if value:
		session.set_flag(id)
		flags_shadow[id >> 3] |= 1 << (id & 7)
	else:
		session.clear_flag(id)
		flags_shadow[id >> 3] &= ~(1 << (id & 7))

func _sync_flags_out() -> void:
	var now: PackedByteArray = session.read_flags()
	if now == flags_shadow:
		return
	var flags: Dictionary = gameplay.native_context.get("event_flags", {})
	for index in FLAG_BYTES:
		var changed := now[index] ^ flags_shadow[index]
		if changed == 0:
			continue
		for bit in 8:
			if changed & (1 << bit) != 0:
				var id := index * 8 + bit
				flags.erase(str(id))
				flags[id] = now[index] & (1 << bit) != 0
	gameplay.native_context["event_flags"] = flags
	flags_shadow = now

func _sync_actors() -> void:
	var machine: Machine = session.machine
	var live := {}
	for actor: int in session.actor_slots() + session.effect_slots():
		var passive := actor >= Session.EFFECT_BASE
		if port_classes.has(float(machine.u8(actor + 4))):
			if not passive:
				machine.put8(actor, machine.u8(actor) & 0xFE)
			continue
		var index := _model_index(actor)
		if index < 0 or DOORS.has(machine.u32(bank_address(index >= SUB_KEY) + 4 + (index & SUB_KEY - 1) * 16) & 0xFFFF):
			continue
		live[actor] = true
		var view = views.get(actor)
		if view == null or not is_instance_valid(view) or view.model_index != index:
			if view != null and is_instance_valid(view):
				view.queue_free()
			view = _create_view(actor, index, passive)
			if view == null:
				continue
			views[actor] = view
		view.sync()
	for actor in views.keys():
		if not live.has(actor):
			if is_instance_valid(views[actor]):
				views[actor].queue_free()
			views.erase(actor)

## The model table starts after a leading player-clip block (first word with bit 31 set, its size in the low bits) when the stage's archive has one (ST1C); the sub-stage bank (manifest "bank1") is preloaded at its address and has none.
func bank_address(sub := false) -> int:
	if sub:
		return int(manifest["bank1"]["address"])
	var address := int(session.manifest["stages"][stage]["models"]["address"])
	var head: int = session.machine.u32(address)
	return address + (head & 0x3FFFFFFF if head & 0x80000000 != 0 else 0)

## The model an object's mesh pointer belongs to: its index in the stage's table, plus SUB_KEY when the pointer lies in the sub-stage bank (original code addresses that bank directly, whichever bank the model pointer scratch word names), -1 when it is no model.
func _model_index(actor: int) -> int:
	var machine: Machine = session.machine
	var mesh: int = machine.u32(actor + View.MESH)
	for sub in [false, true]:
		if sub and not manifest.has("bank1"):
			break
		var bank := bank_address(sub)
		if mesh < bank or sub and mesh >= bank + int(manifest["bank1"]["size"]):
			continue
		var count: int = machine.u32(bank)
		for index in count:
			var entry: int = machine.u32(bank + 4 + index * 16 + 4) + bank
			if entry == mesh or actor >= Session.EFFECT_BASE and entry == mesh + EFFECT_MESH_SKEW:
				return index + (SUB_KEY if sub else 0)
	return -1

func _create_view(actor: int, key: int, passive: bool) -> Node3D:
	var machine: Machine = session.machine
	var sub := key >= SUB_KEY
	var index := key & SUB_KEY - 1
	var path := "%s../levels/%s/models/%s/model_%03d.glb" % [DIRECTORY, stage, str(manifest["bank1"]["models_directory"]) if sub else str(manifest["models_directory"]), index]
	var view := View.new()
	var mesh: int = machine.u32(bank_address(sub) + 4 + index * 16 + 4) + bank_address(sub)  # the header of the model the object points at (an effect object's pointer is EFFECT_MESH_SKEW short of it)
	var scale := Vector3(machine.s16(mesh + 0x30), machine.s16(mesh + 0x32), machine.s16(mesh + 0x34))
	view.name = "RunnerActor_%08X" % actor
	level.add_child(view)
	if not view.configure(machine, actor, path.simplify_path(), (bank_animations if sub else animations).get(index, []), scale, gameplay.depth_cue_parameters):
		view.queue_free()
		return null
	view.model_index = key
	view.passive = passive
	return view

func _drain_bridge() -> void:
	var bridge = session.hle.bridge
	var events: Array = bridge.log.duplicate()
	bridge.log.clear()
	for event: Array in events:
		match event[0]:
			"message": _message(int(event[1]), int(event[2]), int(event[3]))
			"message_close": _close_window(int(event[1]))
			"transition": gameplay.transition_overlay.request(int(event[1]))
			"sound": _sound(event)
			"music": gameplay.audio.play_sound(int(event[1]))
			"music_fade": gameplay.audio.fade_sequences(int(event[1]), int(event[2]), int(event[3]))
			"camera": camera_state = event
			"xa": _play_xa(int(event[1]))
			"xa_fade": _fade_xa(int(event[1]))
			"boss": _bind_boss(int(event[1]) & 0xFFFFFFFF, int(event[3]), int(event[4]) & 0xFFFFFF)

func _sound(event: Array) -> void:
	if event[5]:
		gameplay.audio.play_at(int(event[1]), level.to_global(Vector3(-event[2], -event[3], event[4]) / 256.0))
	else:
		gameplay.audio.play_sound(int(event[1]))

func _play_xa(id: int) -> void:
	if is_instance_valid(gameplay.voice):
		gameplay.voice.volume_db = 0.0
	gameplay.play_voice(stage, id)

func _fade_xa(speed: int) -> void:
	var voice: AudioStreamPlayer = gameplay.voice
	if is_instance_valid(voice) and voice.playing and speed > 0:
		var tween := create_tween()
		tween.tween_property(voice, "volume_db", -60.0, 127.0 / float(speed) / NATIVE_HZ)
		tween.tween_callback(voice.stop)

func _close_window(window: int) -> void:
	closing.append(window)

func _message(window: int, bank: int, index: int) -> void:
	while bool(gameplay.dialogue_box.get("active")):
		await get_tree().physics_frame
	if gameplay.event_script.can_play_bound_message(stage, "0x%08X" % (bank & 0xFFFFFFFF), index):
		await gameplay.event_script.play_bound_message(stage, "0x%08X" % (bank & 0xFFFFFFFF), index, "runner", null, window)
	else:
		push_error("Runner: message %d of bank 0x%08X has no page" % [index, bank & 0xFFFFFFFF])
	closing.append(window)

func _bind_boss(actor: int, shift: int, color: int) -> void:
	var view = views.get(actor)
	if view != null and is_instance_valid(view):
		boss_view = view
		gameplay.game_hud.bind_boss(view, shift, Color8(color & 255, (color >> 8) & 255, (color >> 16) & 255))

func _begin_scene() -> void:
	scene_mode = true
	gameplay.loading = true
	gameplay.area_picker.disabled = true
	gameplay.player.velocity = Vector3.ZERO
	gameplay.player.set_physics_process(false)
	gameplay.set_scene_presentation(true)
	_begin_scene_camera()
	if PlayerScene.available(stage):
		player_scene = PlayerScene.new()
		add_child(player_scene)
		if player_scene.open(gameplay, stage):
			player_scene.begin()
		else:
			player_scene.queue_free()
			player_scene = null

func _end_scene() -> void:
	scene_mode = false
	scene_grace = 3
	player_control = -1
	if player_scene != null:
		player_scene.end()
		player_scene.queue_free()
		player_scene = null
	if scene_camera != null:
		scene_camera.queue_free()
		scene_camera = null
	gameplay.player.camera.make_current()
	gameplay.set_scene_presentation(false)
	gameplay.player.set_physics_process(true)
	gameplay.area_picker.disabled = false
	gameplay.loading = false

func _apply_camera() -> void:
	if camera_state.is_empty() or scene_camera == null:
		return
	var focus: Vector3i = camera_state[1]
	var target := Vector3(focus)
	var yaw := float(camera_state[3]) * TAU / 4096.0
	var pitch := float(camera_state[4]) * TAU / 4096.0
	var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * float(camera_state[2])
	var rotation := Basis(Vector3.RIGHT, pitch) * Basis(Vector3.UP, -yaw)
	var rows: Array[Vector3] = [Vector3(rotation.x.x, rotation.y.x, rotation.z.x), Vector3(rotation.x.y, rotation.y.y, rotation.z.y), Vector3(rotation.x.z, rotation.y.z, rotation.z.z)]
	scene_camera.basis = Basis(Vector3(-rows[0].x, rows[1].x, rows[2].x), Vector3(-rows[0].y, rows[1].y, rows[2].y), Vector3(rows[0].z, -rows[1].z, -rows[2].z)).inverse()
	var eye := target - offset
	scene_camera.position = Vector3(-eye.x, -eye.y, eye.z) / 256.0
	if int(camera_state[5]) != 0:
		scene_camera.rotate_object_local(Vector3.BACK, -float(camera_state[5]) * TAU / 4096.0)

func _change_area(runner_area: int) -> void:
	busy = true
	var machine: Machine = session.machine
	var scene_after := scene_mode
	var raw := [machine.s16(PLAYER + 0x12), machine.s16(PLAYER + 0x16), machine.s16(PLAYER + 0x1A), machine.s16(PLAYER + 0x2A) & 4095]
	var was_loading: bool = gameplay.loading
	area = runner_area
	gameplay.audio.hold_music = true
	await gameplay.native_scene_area(runner_area, raw, raw[3])
	gameplay.audio.hold_music = false
	busy = false
	gameplay.loading = was_loading or scene_after
	if scene_after:
		_begin_scene_camera()
	else:
		gameplay.area_picker.disabled = false
		gameplay.player.set_physics_process(true)

func _begin_scene_camera() -> void:
	scene_camera = Camera3D.new()
	scene_camera.name = "RunnerSceneCamera"
	scene_camera.near = gameplay.player.camera.near
	scene_camera.far = gameplay.player.camera.far
	scene_camera.fov = rad_to_deg(2.0 * atan(120.0 / 384.0))
	level.add_child(scene_camera)
	scene_camera.make_current()

func _stage_request() -> void:
	busy = true
	var machine: Machine = session.machine
	var raw := [machine.s16(REQUEST + 0x10), machine.s16(REQUEST + 0x12), machine.s16(REQUEST + 0x14), machine.s16(REQUEST + 0x16) & 4095]
	var route := {"destination_stage": "ST%02X" % machine.u8(REQUEST + 4), "destination_area": machine.u8(REQUEST + 5), "destination_transform_raw": raw, "destination_transform": {"position": [float(raw[0]) / 256.0, float(raw[1]) / 256.0, float(raw[2]) / 256.0], "yaw_raw": raw[3], "floor_height": int(raw[1]) == -1}, "native_transition_mode": 2, "native_entry_fade": machine.u8(REQUEST + 0x18), "native_exit_fade": machine.u8(REQUEST + 0x19)}
	machine.put8(REQUEST, 0)
	session.frame()
	var story: int = machine.u8(STORY_BYTE)
	if story != last_story:
		last_story = story
		gameplay.native_context["native_save_byte15"] = story
	finished = true
	gameplay.loading = true
	await gameplay.transition_overlay.request(int(route["native_exit_fade"]))
	if scene_camera != null:
		scene_camera.queue_free()
	gameplay.stage_transition_requested.emit(route)
