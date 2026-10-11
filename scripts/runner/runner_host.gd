extends Node
## Runs the original game code of an opted-in stage (assets/runner/manifest.json "attach") beside the port: the port's player, flags and messages feed the emulated game, and its actors, scenes, camera, sound and stage requests drive the port.

const Props := preload("res://scripts/world/actors/native_props.gd")
const Machine := preload("res://scripts/runner/mips_machine.gd")
const Effects := preload("res://scripts/runner/runner_effects.gd")
const Backdrop := preload("res://scripts/runner/runner_backdrop.gd")
const Session := preload("res://scripts/runner/runner_session.gd")
const View := preload("res://scripts/runner/runner_actor_view.gd")
const Barriers := preload("res://scripts/runner/runner_barriers.gd")
const RoomVariants := preload("res://scripts/world/flutter/room_variants.gd")
const NativeFloor := preload("res://scripts/world/core/native_floor.gd")
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
## How far below the hands a carried block starts (metres; negative: its base rests above the hands, over the head).
const CARRY_DROP := -0.12
const LIFE := 0x70
const ZENNY := 0x8009C810  # the wallet word of the game block (+0x28), read by the Status screen at SLES 0x8004FB60
## SLES main loop state word: the tutorial's end (ST4A area 0 handler 0x800E74B8..0x800E7504, after message 0x2D set flag 0x68E) starts the screen wipe, then stores 2 here and points the main loop at the title (0x800128D4(0x80012B48)).
const LOOP_STATE := 0x80078F80
const LOOP_TITLE := 2
const FLAG_BYTES := 256
## Saved halfwords of the game block the dialogue adds to (event_script opcode 0x37 modes 1 and 2: the Pokte donation total spent by ST25's rebuild handler) and the context keys that mirror them.
const COUNTERS := {"native_save_word78": 0x8009C860, "native_save_word7A": 0x8009C862}
const NATIVE_HZ := 25.0
const CAMERA_DISTANCE := 1024
const DOORS := [0x161, 0x261, 0x361]
const RADIO_WINDOW := 4
const STORY_BYTE := 0x8009C7FD
const BANK_POINTER := 0x1F800074
## The map's placement table (4 + 8 bytes per placement; byte +3 low bits are the placement state GAME 0x800C010C writes and 0x800C00D4 reads).
const PLACEMENTS := 0x1F80008C
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
var counter_shadow := {}
var placement_states := {}
var scene_mode := false
var scene_camera: Camera3D
var camera_state: Array = []
var boss_view: Node3D
var barriers := Barriers.new()
var player_scene: Node
var port_classes: Array = []
## Lifter blocks (attach rule lift_classes). Phases: 1 pickup requested, 2 carried, 3 thrown this tick, 4 dropped this tick.
var lift_classes: Array = []
var solid_classes: Array = []
## Life and zenny of the original's player struct as last exchanged with the port: the original collects dropped items by itself, the increases it makes go to the port's player.
var pickup_life := 0
var pickup_zenny := 0
var lift_view: Node3D
var lift_phase := 0
var lift_frames := 0
## A menu start (no arrival transform) of a stage whose attach rule asks for it: the player stands where the original stage set-up put him.
var original_start := false
var last_story := 0
var last_committed := 0
var bank_animations: Dictionary = {}
## Source surfaces of the exported models (part, face stream and default visibility of each mesh surface), keyed like the model keys: index, plus SUB_KEY for the sub-stage bank.
var surfaces: Dictionary = {}
## The interact press, latched until the next original tick: the original runs at 25 Hz, so a physics frame's press would mostly fall between two ticks. A press that advances or closes a message never gets here.
var interact_pending := false
var own_request := false
var pending_shots: Array = []
var pending_area := -1
var scene_grace := 0
var player_control := -1
var finished := false
var busy := false
var loader: Thread
var opening := false
var last_wall := 0
var effects: CanvasLayer
var backdrop: CanvasLayer
var strips: Array = []
var pending_story := 0
var job: Thread
var ticking := false
var closing: Array = []
var hold_released := false
var requested_area := -1
var grab_view: Node3D
var built: Array = []
var built_world: Array = []
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
	host.original_start = bool(rule.get("original_start", false)) and gameplay.entry_route.is_empty()
	host.pin_arrival = bool(rule.get("original_start", false))
	gameplay.add_child(host)
	host.start(parent, area_index, int(context["native_save_byte14"]))

func start(parent: Node3D, area_index: int, story: int) -> void:
	level = parent
	area = area_index
	pending_story = story
	session = Session.new()
	if OS.has_feature("nothreads"):
		opening = true
		_open_sync.call_deferred()
		return
	loader = Thread.new()
	if loader.start(_open_worker) != OK:
		loader = null
		opening = true
		_open_sync.call_deferred()

## No worker threads (web build): the stage opens on the main thread once the caller has returned.
func _open_sync() -> void:
	# Compiling the original code blocks the only thread for seconds on the web: put the loading screen up and let it draw first.
	AssetStore._block(AssetStore._stage_title(stage))
	for frame in 40:
		if AssetStore.screen != null and AssetStore.layer.visible: break
		await get_tree().process_frame
	await get_tree().process_frame
	var opened := _open_worker()
	AssetStore._unblock()
	opening = false
	_loaded(opened)

func _open_worker() -> bool:
	return session.open(stage)

func _loaded(opened := true) -> void:
	if loader != null:
		opened = loader.wait_to_finish()
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
	add_child(effects.world)
	backdrop = Backdrop.new()
	backdrop.name = "RunnerBackdrop"
	add_child(backdrop)
	backdrop.configure()
	session.hle.bridge.grab_handler = Callable(self, "_grab")
	gameplay.player.hold_ended.connect(_hold_ended)
	port_classes = manifest["attach"]["port_classes"]
	lift_classes = manifest["attach"].get("lift_classes", [])
	solid_classes = manifest["attach"].get("solid_classes", [])
	barriers.load_stage(stage)
	for scene in manifest["attach"]["port_scenes"]:
		session.hle.bridge.blocked_scenes[int(scene)] = true
	var flags: Dictionary = gameplay.native_context.get("event_flags", {})
	area = int(gameplay.get_meta("runner_start_area", area))
	_read_animations(str(manifest["models_directory"]), animations)
	if manifest.has("bank1"):
		_read_animations(str(manifest["bank1"]["models_directory"]), bank_animations, SUB_KEY)
	session.begin(int(("0x" + stage.substr(2)).hex_to_int()), area, pending_story, flags)
	flags_shadow = session.read_flags()
	_stop_on_fault()
	last_story = pending_story
	last_committed = pending_story
	if original_start:
		_adopt_start()
	_sync_player_in()

func _adopt_start() -> void:
	_sync_player_out()
	var point: Vector3 = gameplay.player.global_position
	gameplay.player.reset_at(point)
	gameplay.player.camera_pivot.rotation.y = gameplay.player.player_model.rotation.y
	gameplay.spawn_position = point

# A stage handover reparents the host while its session is still loading; only a host that is going away joins its threads.
func _exit_tree() -> void:
	if is_queued_for_deletion():
		if loader != null:
			loader.wait_to_finish()
		_join()
	if is_instance_valid(gameplay) and is_instance_valid(gameplay.get("sky")):
		gameplay.sky.set_canvas_backdrop(false)

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		if loader != null and loader.is_started(): loader.wait_to_finish()
		_join()

func _join() -> void:
	if job != null and job.is_started():
		job.wait_to_finish()

## Animation tables of an exported model bank's models.
func _read_animations(directory: String, into: Dictionary, key_base := 0) -> void:
	var section := DIRECTORY.path_join("../levels/%s/models/%s/manifest.json" % [stage, directory]).simplify_path()
	for model: Dictionary in Props._read_manifest(section).get("models", []):
		if model.get("status", "") == "exported":
			into[int(model["index"])] = model["export"].get("animations", [])
			surfaces[key_base + int(model["index"])] = model["export"].get("source_surfaces", [])

## The original queued a read of a pack (SLES 0x8001B2D8) and the session loaded its model archive over the sub-stage bank (entry bank 1, 0x8013C800) or over the stage's own bank (entry bank 0, ST1C02), so the port's model files and animation tables follow the replaced bank.
func _bank_loaded(entry: Dictionary) -> void:
	if entry.has("vram"):
		effects.vram = FileAccess.get_file_as_bytes(DIRECTORY + str(entry["vram"]))
		effects.textures.clear()
	var sub := int(entry["bank"]) == 1
	if sub:
		manifest["bank1"] = entry
	else:
		manifest["models_directory"] = entry["models_directory"]
	(bank_animations if sub else animations).clear()
	for key in surfaces.keys():
		if (int(key) >= SUB_KEY) == sub:
			surfaces.erase(key)
	_read_animations(str(entry["models_directory"]), bank_animations if sub else animations, SUB_KEY if sub else 0)
	for actor in views.keys():
		if is_instance_valid(views[actor]) and (views[actor].model_index >= SUB_KEY) == sub:
			views[actor].queue_free()
			views.erase(actor)

func level_loaded(parent: Node3D, area_index: int) -> void:
	level = parent
	placement_states.clear()
	for view in views.values():
		if is_instance_valid(view):
			view.queue_free()
	views.clear()
	barriers.clear()
	boss_view = null
	if loader != null or opening:
		area = area_index
		return
	if area_index != area:
		arrival_from = area
		area = area_index
		pending_area = area_index
		requested_area = area_index

## The area the room streaming handed over from (-1 when the session loaded straight into its area).
var arrival_from := -1
var arrival_pinned := false
## Stages whose attach rule restores the original's start (the training levels) also give the runner the door's destination on a streamed handover.
var pin_arrival := false
var arrival_hold := 0
var arrival_point: Array = []
## Ticks the first position is kept: the area's region lists read it on the frames after the area set-up, before the port's own position is mirrored again.
const ARRIVAL_TICKS := 4

## The original enters an area at its door's destination, and the area's region lists (spawn sets such as the Area 03 blocks) read that first position. Streamed rooms hand over wherever the player has walked to by the time the session catches up, which can be past the region; the first frame sees the destination of the door the player came through (the route between the two areas whose destination lies nearest to him) instead.
func _arrival_raw(machine: Machine) -> Array:
	arrival_pinned = false
	var here := Vector2(machine.s16(PLAYER + 0x12), machine.s16(PLAYER + 0x1A))
	var best: Array = [machine.s16(PLAYER + 0x12), machine.s16(PLAYER + 0x16), machine.s16(PLAYER + 0x1A)]
	var nearest := INF
	for route: Dictionary in gameplay.routes if pin_arrival else []:
		if int(route["source_area"]) != arrival_from or int(route["destination_area"]) != area or str(route.get("destination_stage", stage)) != stage or not route.has("destination_transform_raw"):
			continue
		var raw: Array = route["destination_transform_raw"]
		var distance := here.distance_to(Vector2(int(raw[0]), int(raw[2])))
		if distance < nearest:
			nearest = distance
			best = [int(raw[0]), best[1] if int(raw[1]) == -1 else int(raw[1]), int(raw[2])]
	arrival_pinned = nearest < INF
	arrival_from = -1
	return best

func _request_area(area_index: int) -> void:
	var machine: Machine = session.machine
	session.apply_area_bank(area_index)
	_sync_player_in()
	own_request = true
	machine.put8(REQUEST, 0xFF)
	machine.put8(REQUEST + 5, area_index)
	machine.put16(REQUEST + 8, 0)
	machine.put16(REQUEST + 0xC, 0)
	var arrival := _arrival_raw(machine)
	arrival_hold = ARRIVAL_TICKS if arrival_pinned else 0
	arrival_point = arrival
	machine.put16(REQUEST + 0x10, arrival[0])
	machine.put16(REQUEST + 0x12, arrival[1])
	machine.put16(REQUEST + 0x14, arrival[2])

func _physics_process(delta: float) -> void:
	if opening:
		return
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
	if OS.has_feature("nothreads"):
		# A slow single-threaded frame gets fewer physics steps than real time; the original's clock is the vblank counter, so follow the wall clock (the voice plays in real time).
		var now := Time.get_ticks_usec()
		delta = clampf(float(now - last_wall) / 1000000.0, 0.0, 0.5) if last_wall > 0 else delta
		last_wall = now
	elapsed += delta * NATIVE_HZ
	if ticking:
		elapsed = minf(elapsed, 2.0 if not OS.has_feature("nothreads") else 12.0)
		return
	var single := OS.has_feature("nothreads")
	while elapsed >= 1.0 and not busy and not finished:
		elapsed -= 1.0
		ticking = true
		await _tick()
		ticking = false
		if single:
			elapsed = minf(elapsed, 12.0)
			break

## Start in a scene is the original's skip (GAME 0x800C10B4); taking the event here keeps the pause menu from opening over it.
func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("interact") and not bool(gameplay.dialogue_box.get("active")):
		interact_pending = true
	if scene_mode and event.is_action_pressed("ui_cancel"):
		start_ticks = START_TICKS
		get_viewport().set_input_as_handled()

func _flush_ports() -> void:
	var machine: Machine = session.machine
	for view in views.values():
		if is_instance_valid(view):
			view.flush_hits()
	barriers.flush(machine)
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
	if OS.has_feature("nothreads"):
		session.frame()
		if not view.is_empty():
			if elapsed < 1.0:
				await get_tree().physics_frame
			if is_inside_tree() and not finished:
				_render(view)
		return
	job = Thread.new()
	if job.start(_work.bind(view)) != OK:
		job = null
		_work(view)
		return
	while job.is_alive() and is_inside_tree():
		await get_tree().physics_frame
	_join()

func _work(view: Array) -> void:
	session.frame()
	_render(view)

## The render phase of an original frame; without worker threads it runs a physics frame after the frame itself, so the two halves do not land in one spike.
func _render(view: Array) -> void:
	var drawn: Dictionary = session.render_world() if not view.is_empty() else {}
	built = effects.build(drawn["screen"], session.gte_projection(), view[0], view[1]) if not view.is_empty() else []
	built_world = effects.build_world(drawn) if not view.is_empty() else []
	strips = session.background() if not view.is_empty() else []

func _tick() -> void:
	var machine: Machine = session.machine
	_flush_ports()
	if not scene_mode:
		_sync_player_in()
		if arrival_hold > 0:
			arrival_hold -= 1
			machine.put16(PLAYER + 0x12, arrival_point[0])
			machine.put16(PLAYER + 0x16, arrival_point[1])
			machine.put16(PLAYER + 0x1A, arrival_point[2])
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
	_hold_block(machine)
	_forward_hits()
	_bridge_segments()
	_sync_actors()
	_sync_placements()
	barriers.sync(machine, level, area, gameplay.native_context)
	_drain_bridge()
	_shake()
	if camera != null:
		effects.show_batches(built)
		effects.show_world(built_world, level.global_transform)
		backdrop.show_bands(strips, session.gte_projection(), camera.fov, get_viewport().get_visible_rect().size)
		gameplay.sky.set_canvas_backdrop(not strips.is_empty())
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
		else:
			gameplay.player.player_model.visible = machine.u8(PLAYER) & 2 != 0  # the struct's render flag, as in runner_player_scene.gd
		_apply_camera()
	var runner_area: int = machine.u8(Session.AREA_BYTE)
	if pending_area >= 0:
		if runner_area == pending_area:
			pending_area = -1
	elif runner_area != area and not busy:
		_change_area(runner_area)
	elif machine.u8(REQUEST) == 2 and not busy:
		_stage_request()
	elif machine.u32(LOOP_STATE) == LOOP_TITLE and not busy:
		_return_to_title()
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

## Examine objects (terminals, switches, NPCs: GAME 0x800D0154) run when the player's selection word (+0x1D0) holds their address with bit 24 set. The interact press runs the original's own selection (GAME 0x800CC2F0, mode 0) for one tick: it scans the actor, object and effect pools for bodies flagged +0x60 bit 0 and keeps the nearest one inside its shape record (+0x5C: reach 0xC0 plus the record's radius, height window, a 45 degree cone around the player's heading) and writes the word.
func _examine() -> void:
	var machine: Machine = session.machine
	machine.put32(PLAYER + 0x1D0, 0)
	if lift_phase != 0:
		_lift_fields(machine)
		return
	var pressed := interact_pending
	interact_pending = false
	if scene_mode or not pressed or bool(gameplay.dialogue_box.get("active")):
		return
	machine.call_function(0x800CC2F0, PLAYER, 0)

## The original block code reads the player's lift fields: GAME 0x800CFABC takes the pickup from a selection word with bit 25 (and starts the player's lift mode 0x10), 0x800CFB24 holds the block at the hands by the lift frame (+0x9C, 0 to 12), 0x800CF998 reports a throw when the selection word is zero again and a drop when the mode is 0x0E or 0x0F.
func lift_begin(view: Node3D) -> bool:
	if lift_phase != 0:
		return false
	lift_view = view
	lift_phase = 1
	lift_frames = 0
	return true

func lift_release(view: Node3D) -> void:
	if view == lift_view and lift_phase in [1, 2]:
		lift_phase = 3

## The original places a carried block from the hand joints of its own player model (GAME 0x800CFB24, struct +0x4B0), which the port's animated player replaces: the block's position words follow the port player's hands, so the view and the throw both start there.
func _hold_block(machine: Machine) -> void:
	if lift_phase != 2 or not is_instance_valid(lift_view):
		return
	var hands: Vector3 = level.to_local(gameplay.player.carry_point()) - Vector3(0, CARRY_DROP, 0)
	var address := int(lift_view.get("address"))
	machine.put32(address + 0x10, (roundi(-hands.x * 256.0) << 16) & 0xFFFFFFFF)
	machine.put32(address + 0x14, (roundi(-hands.y * 256.0) << 16) & 0xFFFFFFFF)
	machine.put32(address + 0x18, (roundi(hands.z * 256.0) << 16) & 0xFFFFFFFF)

func _lift_fields(machine: Machine) -> void:
	if not is_instance_valid(lift_view) or lift_phase != 4 and lift_phase != 3 and machine.u8(int(lift_view.get("address")) + 8) not in [1, 2]:
		lift_phase = 0
		lift_view = null
		return
	var selection: int = (int(lift_view.get("address")) & 0xFFFFFF) | 0x2000000
	machine.put8(PLAYER + 0x50, 0)
	match lift_phase:
		1:
			machine.put32(PLAYER + 0x1D0, selection)
			lift_phase = 2
		2:
			lift_frames = mini(lift_frames + 1, 12)
			machine.put8(PLAYER + 9, 0x10)
			machine.put8(PLAYER + 0x9C, lift_frames)
			machine.put32(PLAYER + 0x1D0, selection)
		3:
			machine.put8(PLAYER + 9, 0x10)
			machine.put8(PLAYER + 0x9C, lift_frames)
			lift_phase = 0
			lift_view = null
		4:
			machine.put8(PLAYER + 9, 0x0E)
			lift_phase = 0
			lift_view = null

func _sync_player_in() -> void:
	var machine: Machine = session.machine
	pickup_life = gameplay.player.health
	pickup_zenny = gameplay.player.zenny
	machine.put16(PLAYER + LIFE, pickup_life)
	machine.put16(PLAYER + LIFE + 2, gameplay.player.max_health)
	machine.put32(ZENNY, pickup_zenny)
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
	var life := machine.s16(PLAYER + LIFE)
	var zenny := machine.s32(ZENNY)
	if life > pickup_life and gameplay.player.health >= 0:
		gameplay.player.health = mini(gameplay.player.max_health, gameplay.player.health + life - pickup_life)
		gameplay.player.health_changed.emit(gameplay.player.health, gameplay.player.max_health)
	if zenny > pickup_zenny:
		gameplay.player.zenny = clampi(gameplay.player.zenny + zenny - pickup_zenny, 0, 9999999)
	pickup_life = life
	pickup_zenny = zenny
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
	for key: String in COUNTERS:
		var value := int(gameplay.native_context.get(key, 0))
		if value != int(counter_shadow.get(key, 0)):
			session.machine.put16(COUNTERS[key], value)
			counter_shadow[key] = value
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
	for key: String in COUNTERS:
		var value: int = session.machine.u16(COUNTERS[key])
		if value != int(counter_shadow.get(key, 0)):
			counter_shadow[key] = value
			gameplay.native_context[key] = value
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

## Placements with several runtime states (the Pokte houses: the rebuild handler and the Krabbe fight write the state byte): the port shows the state's model and collision, and mirrors it into the context key the door and floor predicates read.
func _sync_placements() -> void:
	var machine: Machine = session.machine
	var table := machine.u32(PLACEMENTS)
	if table == 0 or not is_instance_valid(level):
		return
	for entry: Dictionary in gameplay.areas[_area_slot()].get("placement_variants", []):
		if not entry.has("state_key"):
			continue
		var key := str(entry["state_key"])
		var state := machine.u8(table + 4 + int(entry["placement"]) * 8 + 3) & 3
		if int(placement_states.get(key, -1)) == state:
			continue
		placement_states[key] = state
		gameplay.native_context[key] = state
		if RoomVariants.set_state(level, str(entry["base_node"]), state):
			NativeFloor.replace_placement(level, Props._read_manifest("res://assets/levels/%s/manifest.json" % stage)["native_floor_collision"], area, int(entry["placement"]), gameplay.native_context)

func _area_slot() -> int:
	for slot in gameplay.areas.size():
		if int(gameplay.areas[slot]["index"]) == area:
			return slot
	return 0

func _sync_actors() -> void:
	var machine: Machine = session.machine
	var live := {}
	# The port only owns its classes outside scenes: a scene's actors (Bluecher, Barrel, Roll) are the original's own spawns and the port has no copy of them yet.
	var in_scene := scene_mode or machine.u8(SCENE_ACTIVE) != 0
	for actor: int in session.actor_slots() + session.effect_slots():
		var passive := actor >= Session.EFFECT_BASE
		if not in_scene and port_classes.has(float(machine.u8(actor + 4))):
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
	var header: int = machine.u32(actor + View.HEADER) if actor >= Session.EFFECT_BASE else 0  # the model header an effect object draws (GAME 0x80025540 reads LODs from +0xA0..+0xA8 of it)
	for sub in ([false, true] if header != 0 else []):
		if sub and not manifest.has("bank1"):
			break
		var bank := bank_address(sub)
		if header < bank or sub and header >= bank + int(manifest["bank1"]["size"]):
			continue
		for index in machine.u32(bank):
			if machine.u32(bank + 4 + index * 16 + 4) + bank == header:
				return index + (SUB_KEY if sub else 0)
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
	if not view.configure(machine, actor, path.simplify_path(), (bank_animations if sub else animations).get(index, []), scale, gameplay.depth_cue_parameters, surfaces.get(key, [])):
		view.queue_free()
		return null
	view.model_index = key
	view.passive = passive
	if lift_classes.has(float(machine.u8(actor + 4))):
		view.make_lift(self)
	if solid_classes.has(float(machine.u8(actor + 4))):
		view.make_solid()
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
			"bank": _bank_loaded(event[1])

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
	session.apply_area_bank(runner_area)  # areas the original code enters itself (scene requests) still follow the sub-stage archive rule
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

## The original's own exit to the title: its wipe is already running (bridge transition event), the port then leaves the session for the title screen.
func _return_to_title() -> void:
	busy = true
	finished = true
	while not gameplay.transition_overlay.is_idle():
		await get_tree().physics_frame
	gameplay.title_requested.emit()

func _stage_request() -> void:
	busy = true
	var machine: Machine = session.machine
	var raw := [machine.s16(REQUEST + 0x10), machine.s16(REQUEST + 0x12), machine.s16(REQUEST + 0x14), machine.s16(REQUEST + 0x16) & 4095]
	var route := {"destination_stage": "ST%02X" % machine.u8(REQUEST + 4), "destination_area": machine.u8(REQUEST + 5), "destination_transform_raw": raw, "destination_transform": {"position": [float(raw[0]) / 256.0, float(raw[1]) / 256.0, float(raw[2]) / 256.0], "yaw_raw": raw[3], "floor_height": int(raw[1]) == -1}, "native_transition_mode": 2, "native_entry_fade": machine.u8(REQUEST + 0x18), "native_exit_fade": machine.u8(REQUEST + 0x19)}
	machine.put8(REQUEST, 0)
	session.frame()
	_sync_flags_out()  # flags the exit state clears in this frame (ST3E scenes 0x65 to 0x67 clear 0x3D0 to 0x3D2)
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
