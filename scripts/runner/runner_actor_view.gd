extends CharacterBody3D
## The port's body for one actor of the original code: the model, its animation control and a hit volume follow the actor record in emulated RAM, and hits received here are written back into the record.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const NativeMaterial := preload("res://scripts/world/rendering/native_material.gd")
const HIT_WORD := 0x14C
const BOUNDS := 0x58
## Actors of the larger bosses keep their hit word in a separate record (pointer at +0x154, hit volumes at record +0x30) instead of +0x14C.
const RECORD_POINTER := 0x154
const RECORD_BOUNDS := 0x30
const MESH := 0xA4
const CONTROL := 0xA0
const RECORD := 0xA3
const HEALTH := 0x70
const LIGHT := 0xE6

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


func configure(runner_machine: Machine, actor: int, path: String, animations: Array, scale_raw: Vector3, depth_cue: Dictionary) -> bool:
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
	NativeMaterial.apply(model, 128.0)
	for mesh: MeshInstance3D in model.find_children("*", "MeshInstance3D", true, false):
		for surface in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material != null:
				materials.append(material)
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


func class_id() -> int:
	return machine.u8(address + 4)


func sync() -> void:
	var x := machine.s16(address + 0x12)
	var y := machine.s16(address + 0x16)
	var z := machine.s16(address + 0x1A)
	position = Vector3(-x, -y, z) / 256.0
	rotation.y = -float(machine.s16(address + 0x2A) & 4095) * TAU / 4096.0
	max_health = machine.s16(address + HEALTH + 2)
	health = machine.s16(address + HEALTH)
	var bounds := machine.u32(address + BOUNDS)
	hittable = not passive and bounds != 0 and max_health > 1 and health >= 0
	collision_layer = 8 if hittable else 0
	if hittable and not is_in_group("lock_targets"):
		add_to_group("lock_targets")
	elif not hittable and is_in_group("lock_targets"):
		remove_from_group("lock_targets")
	if hittable:
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
	animate()


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
	var record := machine.u32(address + RECORD_POINTER)
	if record >= 0x80000000 and record < 0x80200000 and machine.u32(address + BOUNDS) == record + RECORD_BOUNDS:
		target = record
	var word := machine.u32(target)
	machine.put32(target, ((word | queued_flags) & 0xFFFFF000) | mini((word & 0xFFF) + queued_damage, 0xFFF))
	queued_damage = 0
	queued_flags = 0
