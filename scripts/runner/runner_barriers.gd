extends RefCounted
## Class 0x28 barrier actors of the original code (effect pool): each live one gets the port's shimmer and a collision body for the tile variant the original selects.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Visual := preload("res://scripts/world/enemies/native_icefield_barrier.gd")
const POOL := 0x80098B08
const STRIDE := 0xCC
const COUNT := 128
const CLASS := 0x28

var data: Dictionary = {}
var bodies: Dictionary = {}
var directory := ""


func load_stage(stage: String) -> void:
	directory = "res://assets/levels/%s/" % stage
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(directory + "arena_barrier.json")) if FileAccess.file_exists(directory + "arena_barrier.json") else null
	data = parsed if parsed is Dictionary else {}


func sync(machine: Machine, level: Node3D, area: int) -> void:
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


func clear(actor: int = -1) -> void:
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
