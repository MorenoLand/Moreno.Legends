extends CharacterBody3D
## The port's body for one actor of the original code: the model, its animation control and a hit volume follow the actor record in emulated RAM, and hits received here are written back into the record.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const NativeMaterial := preload("res://scripts/world/rendering/native_material.gd")
const HIT_WORD := 0x14C
const BOUNDS := 0x58
## Actors of the larger bosses keep their hit word in a separate record (pointer at +0x154, hit volumes at record +0x30) instead of +0x14C.
const RECORD_POINTER := 0x154
const RECORD_BOUNDS := 0x30
## Multi-part actors (the Manda ruins guardian) keep part positions at +0x158 and, 80 bytes further, a hit record in the model's part block at +0x15C (hit words at +0 and +8); their code reads those words (ST14 0x800F4510 and 0x800F4580) instead of +0x14C.
const PART_POSITIONS := 0x158
const PART_HIT := 0x15C
const MESH := 0xA4
## A solid body blocks the player's step-over: the volume reaches at least this high (raw units, the player's body is 0.7 m tall) from the object's floor.
const SOLID_HEIGHT := 192.0
## Effect objects draw the model whose header is at +0x94 (GAME 0x80025540): the matrix is RotMatrix (SLES 0x80060824) of the angles at +0x28, +0x2A and +0x2C with its columns scaled by the halfwords at +0xB0, +0xB2 and +0xB4 (4096 is one).
const HEADER := 0x94
const ANGLES := 0x28
const SCALE := 0xB0
const ROT_MATRIX := 0x80060824
const SCRATCH := 0x801F0400
const CONTROL := 0xA0
const RECORD := 0xA3
const HEALTH := 0x70
const LIGHT := 0xE6
## The hierarchy table the actor keeps (4 bytes per model part from +0xEC; the flag byte at +0xEF hides the part with bit 0x80, SLES 0x80024894) and the face UV words (+0xD8 eyes, +0xDC mouth: parts with flag 1 or 2 add the low halfword to their texture coordinates, SLES 0x80025180); actor code swaps mouth, hand and head variants through them.
const PART_FLAGS := 0xEF
const FACE_WORDS := 0xD8

var machine: Machine
var address := 0
var clock: NativeAnimation
var model: Node3D
var shape: CollisionShape3D
var health := 0
var max_health := 0
var hittable := false
var hit_center := Vector3.ZERO
var control := -1
var model_index := -1
var removed := false
var passive := false
var materials: Array[ShaderMaterial] = []
var light := Vector3(128, 128, 128)
var queued_damage := 0
var queued_flags := 0
var base_scale := Vector3.ONE
var body := AABB()
var parts: Array[Dictionary] = []
## Liftable blocks (the attach rule's lift_classes) belong to the port's Lifter: the host drives the original block code through the player's lift fields.
var lift_host: Node
var solid_always := false
var blocker: StaticBody3D
var blocker_shape: CollisionShape3D


func configure(runner_machine: Machine, actor: int, path: String, animations: Array, scale_raw: Vector3, depth_cue: Dictionary, source_surfaces: Array = []) -> bool:
	machine = runner_machine
	address = actor
	var packed := load(path) as PackedScene
	if packed == null:
		return false
	model = packed.instantiate() as Node3D
	if model == null:
		return false
	add_child(model)
	model.scale = scale_raw / 512.0
	base_scale = model.scale
	NativeMaterial.apply(model, 128.0)
	var meshes := model.find_children("*", "MeshInstance3D", true, false)
	for mesh: MeshInstance3D in meshes:
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material != null:
				materials.append(material)
				if mesh == meshes[0] and surface < source_surfaces.size():
					parts.append({"material": material, "part": int(source_surfaces[surface]["source_part"]), "stream": int(source_surfaces[surface]["uv_stream"])})
	if not depth_cue.is_empty():
		NativeMaterial.depth_cue(model, depth_cue)
	clock = NativeAnimation.new()
	clock.name = "NativeAnimationClock"
	add_child(clock)
	clock.configure(model.find_child("AnimationPlayer", true, false) as AnimationPlayer, animations)
	clock.automatic = false
	shape = CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	add_child(shape)
	collision_layer = 0
	collision_mask = 0
	return true


func make_solid() -> void:
	solid_always = true
	_blocker()


func make_lift(host: Node) -> void:
	lift_host = host
	_blocker()
	add_to_group("lift_targets")


## Kinematic bodies do not stop each other, so a solid actor carries a static body of its own for the player.
func _blocker() -> void:
	if blocker != null:
		return
	blocker = StaticBody3D.new()
	blocker.collision_layer = 0
	blocker.collision_mask = 0
	blocker_shape = CollisionShape3D.new()
	blocker_shape.shape = BoxShape3D.new()
	blocker.add_child(blocker_shape)
	add_child(blocker)


## The block's own states (+8): 1 idle, 2 carried, 3 thrown, 4 broken.
func can_lift() -> bool:
	return lift_host != null and not removed and machine.u8(address + 8) == 1


func begin_lift(_carrier: Node3D) -> bool:
	return can_lift() and lift_host.lift_begin(self)


func release_lift(_direction: Vector3, _vertical_raw: int, _forward_raw: int) -> void:
	lift_host.lift_release(self)


## An idle block is solid for the port's player; its volume is the actor's bounds record (+0x58).
func _lift_body() -> void:
	var bounds := machine.u32(address + BOUNDS)
	blocker.collision_layer = 1 if (solid_always or machine.u8(address + 8) == 1) and bounds != 0 else 0
	if bounds == 0:
		return
	var box := blocker_shape.shape as BoxShape3D
	var low := Vector3(machine.s16(bounds), machine.s16(bounds + 4), machine.s16(bounds + 8))
	var high := Vector3(machine.s16(bounds + 2), machine.s16(bounds + 6), machine.s16(bounds + 10))
	box.size = Vector3(high.x - low.x, maxf(high.y - low.y, SOLID_HEIGHT), high.z - low.z) / 256.0
	blocker_shape.position = Vector3(-(low.x + high.x) * 0.5 / 256.0, -high.y / 256.0 + box.size.y * 0.5, (low.z + high.z) * 0.5 / 256.0)


func class_id() -> int:
	return machine.u8(address + 4)


func sync() -> void:
	var x := machine.s16(address + 0x12)
	var y := machine.s16(address + 0x16)
	var z := machine.s16(address + 0x1A)
	position = Vector3(-x, -y, z) / 256.0
	if passive and machine.u32(address + HEADER) != 0:
		_orient()
	else:
		rotation.y = -float(machine.s16(address + 0x2A) & 4095) * TAU / 4096.0
	max_health = machine.s16(address + HEALTH + 2)
	health = machine.s16(address + HEALTH)
	var bounds := machine.u32(address + BOUNDS)
	hittable = not passive and (bounds != 0 or _part_hit() != 0) and max_health > 1 and health >= 0
	collision_layer = 8 if hittable else 0
	if hittable and not is_in_group("lock_targets"):
		add_to_group("lock_targets")
	elif not hittable and is_in_group("lock_targets"):
		remove_from_group("lock_targets")
	if hittable and bounds == 0:
		_body_shape()
	elif hittable:
		var box := shape.shape as BoxShape3D
		var low := Vector3(machine.s16(bounds), machine.s16(bounds + 4), machine.s16(bounds + 8))
		var high := Vector3(machine.s16(bounds + 2), machine.s16(bounds + 6), machine.s16(bounds + 10))
		box.size = Vector3(high.x - low.x, high.y - low.y, high.z - low.z) / 256.0
		shape.position = Vector3(-(low.x + high.x), -(low.y + high.y), low.z + high.z) * 0.5 / 256.0
		hit_center = to_global(shape.position)
	var tint := 0x4210 if passive else machine.u16(address + LIGHT)
	var color := Vector3((tint & 31) << 3, ((tint >> 5) & 31) << 3, ((tint >> 10) & 31) << 3)
	if color != light:
		light = color
		for material in materials:
			material.set_shader_parameter("light_rgb", color)
	if lift_host != null or solid_always:
		_lift_body()
	if not passive:
		_parts()
	animate()


func _parts() -> void:
	for part in parts:
		var material := part["material"] as ShaderMaterial
		material.set_shader_parameter("part_visible", machine.u8(address + PART_FLAGS + 4 * int(part["part"])) & 0x80 == 0)
		if int(part["stream"]) != 0:
			material.set_shader_parameter("uv_word", machine.u16(address + FACE_WORDS + 4 * (int(part["stream"]) - 1)))


func _part_hit() -> int:
	var hit := machine.u32(address + PART_HIT)
	if hit < 0x80000000 or hit >= 0x80200000 or machine.u32(address + PART_POSITIONS) + 80 != hit:
		return 0
	return hit


## The part block carries no bounds record the port can read, so the hit volume is the model's own box (an approximation of the original volume).
func _body_shape() -> void:
	if body.size == Vector3.ZERO:
		var inverse := global_transform.affine_inverse()
		for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
			var box := (inverse * mesh.global_transform) * mesh.mesh.get_aabb()
			body = box if body.size == Vector3.ZERO else body.merge(box)
	(shape.shape as BoxShape3D).size = body.size
	shape.position = body.get_center()
	hit_center = to_global(shape.position)


func _orient() -> void:
	for index in 3:
		machine.put16(SCRATCH + 2 * index, machine.u16(address + ANGLES + 2 * index))
	machine.call_function(ROT_MATRIX, SCRATCH, SCRATCH + 8)
	var m := PackedFloat32Array()
	for index in 9:
		m.append(float(machine.s16(SCRATCH + 8 + 2 * index)) / 4096.0)
	basis = Basis(Vector3(m[0], m[3], -m[6]), Vector3(m[1], m[4], -m[7]), Vector3(-m[2], -m[5], m[8]))
	var factor := Vector3(machine.s16(address + SCALE), machine.s16(address + SCALE + 2), machine.s16(address + SCALE + 4)) / 4096.0
	model.scale = base_scale * (factor if factor.x != 0.0 and factor.y != 0.0 and factor.z != 0.0 else Vector3.ONE)


func animate() -> void:
	var wanted := machine.u8(address + CONTROL)
	if wanted != control:
		control = wanted
		clock.play_control(wanted, machine.u8(address + RECORD), true)
	else:
		clock.native_tick()


## Hits arrive between ticks; the next tick writes them into the actor's hit word.
func receive_hit(damage: int, hit_flags: int, _direction: Vector3 = Vector3.ZERO) -> bool:
	if not hittable:
		return false
	queued_damage += damage
	queued_flags |= hit_flags
	return true


func flush_hits() -> void:
	if queued_damage == 0 and queued_flags == 0:
		return
	var target := address + HIT_WORD
	if machine.u32(address + BOUNDS) == 0 and _part_hit() != 0:
		target = _part_hit()
	var record := machine.u32(address + RECORD_POINTER)
	if record >= 0x80000000 and record < 0x80200000 and machine.u32(address + BOUNDS) == record + RECORD_BOUNDS:
		target = record
	var word := machine.u32(target)
	machine.put32(target, ((word | queued_flags) & 0xFFFFF000) | mini((word & 0xFFF) + queued_damage, 0xFFF))
	queued_damage = 0
	queued_flags = 0
