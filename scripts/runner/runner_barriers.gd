extends RefCounted
## Class 0x28 barrier actors of the original code (effect pool): each live one gets the port's shimmer and a collision body for the tile variant the original selects. The class 0x20 variant 1 ice pillars of the same pool get a hit target for the port's shots (the original resolver ORs the attack word's flags 0x00FFF000 into the object's hit word at +0xBC and adds the damage) and, once the original breaks one (state 2: tile variant 1), the rubble mesh and floor shapes of that tile.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Visual := preload("res://scripts/world/enemies/native_icefield_barrier.gd")
const POOL := 0x80098B08
const STRIDE := 0xCC
const COUNT := 128
const CLASS := 0x28
const PILLAR := 0x20
const HIT_WORD := 0xBC
const HIT_FLAGS := 0x00FFF000
const RoomVariants := preload("res://scripts/world/flutter/room_variants.gd")
const NativeFloor := preload("res://scripts/world/core/native_floor.gd")


## Hit target of one pillar: the port's shots call receive_hit and the next runner tick writes what arrived into the object's hit word.
class Target extends StaticBody3D:
	var damage := 0
	var flags := 0

	func receive_hit(hit_damage: int, hit_flags: int, _direction: Vector3 = Vector3.ZERO) -> bool:
		damage += hit_damage
		flags |= hit_flags
		return true


var data: Dictionary = {}
var bodies: Dictionary = {}
var targets: Dictionary = {}
var broken: Dictionary = {}
var directory := ""


func load_stage(stage: String) -> void:
	directory = "res://assets/levels/%s/" % stage
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(directory + "arena_barrier.json")) if FileAccess.file_exists(directory + "arena_barrier.json") else null
	data = parsed if parsed is Dictionary else {}


func sync(machine: Machine, level: Node3D, area: int, context: Dictionary = {}) -> void:
	if data.is_empty():
		return
	var live := {}
	for index in COUNT:
		var actor := POOL + index * STRIDE
		if machine.u8(actor + 4) != CLASS or machine.u8(actor) & 1 == 0 or machine.u8(actor + 8) != 1 or machine.u16(actor + 0xBC) != machine.u16(actor + 0x12) & 0xFE00:
			continue
		live[actor] = true
		if not bodies.has(actor):
			var tile := [(machine.s16(actor + 0x12) >> 9) + 0x40, (machine.s16(actor + 0x1A) >> 9) + 0x40]
			for barrier: Dictionary in data["barriers"]:
				if int(barrier["area"]) == area and barrier["tile"][0] == tile[0] and barrier["tile"][1] == tile[1]:
					bodies[actor] = _create(level, barrier)
	for actor in bodies.keys():
		if not live.has(actor):
			clear(actor)
	_sync_pillars(machine, level, area, context)


func _sync_pillars(machine: Machine, level: Node3D, area: int, context: Dictionary) -> void:
	var live := {}
	for index in COUNT:
		var actor := POOL + index * STRIDE
		if machine.u8(actor + 4) != PILLAR or machine.u8(actor + 5) != 1 or machine.u8(actor) & 1 == 0:
			continue
		var tile := [(machine.s16(actor + 0x12) >> 9) + 0x40, (machine.s16(actor + 0x1A) >> 9) + 0x40]
		for pillar: Dictionary in data.get("pillars", []):
			if int(pillar["area"]) != area or pillar["tile"][0] != tile[0] or pillar["tile"][1] != tile[1]:
				continue
			if machine.u8(actor + 8) == 1:
				live[actor] = pillar
				if not targets.has(actor):
					targets[actor] = _target(level, machine, actor)
			elif not broken.has(pillar["node"]):
				_break(level, pillar, area, context)
	for actor in targets.keys():
		if not live.has(actor):
			if is_instance_valid(targets[actor]):
				targets[actor].queue_free()
			targets.erase(actor)


func _target(level: Node3D, machine: Machine, actor: int) -> Target:
	var volume: Dictionary = data["pillar_volume"]
	var body := Target.new()
	body.name = "ArenaPillar_%08X" % actor
	body.collision_layer = 8
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = float(volume["radius_raw"]) / 256.0
	shape.shape = sphere
	body.add_child(shape)
	level.add_child(body)
	body.position = Vector3(-machine.s16(actor + 0x12), -(machine.s16(actor + 0x16) + int(volume["center_offset_raw"])), machine.s16(actor + 0x1A)) / 256.0
	return body


## What the port's shots did to the pillar objects since the last tick, in the form the original resolver leaves in the hit word.
func flush(machine: Machine) -> void:
	for actor: int in targets:
		var body: Target = targets[actor]
		if not is_instance_valid(body) or body.damage == 0 and body.flags == 0:
			continue
		var word := machine.u32(actor + HIT_WORD)
		machine.put32(actor + HIT_WORD, ((word | body.flags & HIT_FLAGS) & 0xFFFFF000) | mini((word & 0xFFF) + body.damage, 0xFFF))
		body.damage = 0
		body.flags = 0


func _break(level: Node3D, pillar: Dictionary, area: int, context: Dictionary) -> void:
	broken[pillar["node"]] = true
	RoomVariants.apply_runtime(level, str(pillar["node"]))
	var floor_body := level.get_node_or_null("NativePlacementFloor_%03d" % int(pillar["placement"]))
	if floor_body != null:
		floor_body.name = "Broken_" + str(floor_body.name)
		(floor_body as StaticBody3D).collision_layer = 0
		floor_body.queue_free()
	NativeFloor.apply(level, {str(area): {"boxes": pillar["broken_boxes"]}}, area, context)


func clear(actor: int = -1) -> void:
	if actor < 0:
		for key in targets.keys():
			if is_instance_valid(targets[key]):
				targets[key].queue_free()
		targets.clear()
		broken.clear()
	for key in bodies.keys() if actor < 0 else [actor]:
		if is_instance_valid(bodies[key]):
			bodies[key].queue_free()
		bodies.erase(key)


func _create(level: Node3D, barrier: Dictionary) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "ArenaBarrier_%d" % int(barrier["record_id"])
	body.collision_layer = 1
	body.collision_mask = 0
	level.add_child(body)
	for box: Dictionary in barrier["boxes"]:
		var x: Array = box["x"]
		var y: Array = box["y"]
		var z: Array = box["z"]
		var shape := CollisionShape3D.new()
		var volume := BoxShape3D.new()
		volume.size = Vector3(float(x[1]) - float(x[0]), float(y[1]) - float(y[0]), float(z[1]) - float(z[0])) / 256.0
		shape.shape = volume
		shape.position = Vector3(-(float(x[0]) + float(x[1])) * 0.5, -(float(y[0]) + float(y[1])) * 0.5, (float(z[0]) + float(z[1])) * 0.5) / 256.0
		body.add_child(shape)
	var visual := Visual.new()
	body.add_child(visual)
	visual.configure(level, barrier["transform_raw"], int(barrier["brightness"]), data["profile"], directory + str(data["texture"]))
	return body
