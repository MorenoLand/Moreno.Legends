extends RefCounted
const SIMPLE_RAMP_ORIENTATION := {0x04: 0, 0x05: 1, 0x06: 2, 0x07: 3, 0x10: 0, 0x11: 1, 0x12: 2, 0x13: 3, 0x25: 0, 0x26: 2, 0x35: 2, 0x36: 1, 0x45: 1, 0x46: 3, 0x55: 3, 0x56: 0}
const DIAGONAL_ORIENTATION := {0x14: 4, 0x16: 2, 0x17: 3, 0x15: 5, 0x23: 2, 0x24: 2, 0x33: 3, 0x34: 3, 0x43: 4, 0x44: 4, 0x53: 5, 0x54: 5}
const BOX_KINDS := [0, 2, 3, 0x1C]
const WALL_KIND := 0x1B
const TRIANGULAR_PRISM := [0x22, 0x32, 0x42, 0x52]
static func active_boxes(source: Dictionary, area: int, native_context: Dictionary = {}) -> Array:
	var data: Dictionary = source.get(str(area), {}); var records: Array = data.get("boxes", []).duplicate()
	for variant: Dictionary in data.get("placement_variants", []):
		if not preload("res://scripts/world/actors/native_props.gd")._conditions_met(variant["predicate"]["all"], native_context, area): continue
		records = records.filter(func(record: Dictionary) -> bool: return int(record["placement"]) != int(variant["placement"])); records.append_array(variant["boxes"])
	return records
static func apply(level: Node3D, source: Dictionary, area: int, native_context: Dictionary = {}) -> int:
	var groups := {}; var automatic := {}; var manual := {}; var elevators := {}; var count := 0
	for terrain: MeshInstance3D in level.find_children("terrain", "MeshInstance3D", true, false):
		for child in terrain.get_children():
			if child is StaticBody3D and child.name == "RoomCollision_1": child.set_meta("native_ledge_floor", true)
	for record: Dictionary in active_boxes(source, area, native_context):
		var placement := int(record["placement"])
		if not groups.has(placement): groups[placement] = []
		if int(record["kind"]) >> 8 == 15 and (int(record["mask"]) & 0x8000) == 0: automatic[placement] = true
		if int(record["kind"]) >= 0x100 and int(record["kind"]) >> 8 not in [1, 15, 16]: manual[placement] = true
		if int(record["kind"]) >> 8 == 4: elevators[placement] = true
		if int(record["kind"]) < 0x100 and (int(record["mask"]) & 1) != 0: groups[placement].append(record)
	for placement: int in groups:
		var records: Array = groups[placement]; var ramp := false; var unported := false
		for record: Dictionary in records:
			var kind := int(record["kind"]); ramp = ramp or (SIMPLE_RAMP_ORIENTATION.has(kind) and kind not in [0x04, 0x05, 0x06, 0x07]) or DIAGONAL_ORIENTATION.has(kind)
			if kind not in BOX_KINDS and kind not in TRIANGULAR_PRISM and not SIMPLE_RAMP_ORIENTATION.has(kind) and not DIAGONAL_ORIENTATION.has(kind): unported = true
		if not elevators.has(placement) and not ramp and not automatic.has(placement) and (unported or records.is_empty()): continue
		var meshes := level.find_children("placement_%03d_model_*" % placement, "MeshInstance3D", true, false)
		if meshes.is_empty(): continue
		var body := StaticBody3D.new(); body.name = "NativePlacementFloor_%03d" % placement; body.collision_layer = 1; body.collision_mask = 0; body.set_meta("native_ledge_floor", true)
		for record: Dictionary in records:
			var kind := int(record["kind"]); var x: Array = record["x"]; var y: Array = record["y"]; var z: Array = record["z"]
			if kind == 0x1C and (elevators.has(placement) or not _volume_enabled(native_context)): continue
			if kind not in BOX_KINDS and kind not in TRIANGULAR_PRISM and not SIMPLE_RAMP_ORIENTATION.has(kind) and not DIAGONAL_ORIENTATION.has(kind): continue
			var shape := CollisionShape3D.new()
			if kind in BOX_KINDS:
				var box := BoxShape3D.new(); box.size = Vector3(float(x[1]) - float(x[0]), float(y[1]) - float(y[0]), float(z[1]) - float(z[0])) / 256.0
				if box.size.x <= 0.0 or box.size.y <= 0.0 or box.size.z <= 0.0: continue
				shape.shape = box; shape.position = Vector3(-float(x[0]) - float(x[1]), -float(y[0]) - float(y[1]), float(z[0]) + float(z[1])) / 512.0; shape.set_meta("native_volume", kind == 0x1C)
			elif kind in TRIANGULAR_PRISM:
				var footprint := _footprint(kind, x, z); var points := PackedVector3Array()
				for corner: Vector2 in footprint: points.append(_point(corner.x, float(y[0]), corner.y)); points.append(_point(corner.x, float(y[1]), corner.y))
				var prism := ConvexPolygonShape3D.new(); prism.points = points; shape.shape = prism
			elif SIMPLE_RAMP_ORIENTATION.has(kind):
				var orientation := int(SIMPLE_RAMP_ORIENTATION[kind]); var footprint := _footprint(kind, x, z); var points := PackedVector3Array(); var flat_top := kind in [0x04, 0x05, 0x06, 0x07]
				for corner: Vector2 in footprint:
					var surface := _axis_height(orientation, corner.x, corner.y, x, y, z)
					points.append(_point(corner.x, float(y[0]) if flat_top else surface, corner.y)); points.append(_point(corner.x, surface if flat_top else float(y[1]), corner.y))
				var wedge := ConvexPolygonShape3D.new(); wedge.points = points; shape.shape = wedge
			else:
				var footprint := _footprint(kind, x, z); var points := PackedVector3Array(); var orientation := int(DIAGONAL_ORIENTATION[kind]); var reverse := kind in [0x23, 0x33, 0x43, 0x53]
				for corner: Vector2 in footprint:
					var surface := _diagonal_height(orientation, reverse, corner.x, corner.y, x, y, z)
					points.append(_point(corner.x, surface, corner.y)); points.append(_point(corner.x, float(y[1]), corner.y))
				var wedge := ConvexPolygonShape3D.new(); wedge.points = points; shape.shape = wedge
			shape.set_meta("native_floor_record", record); body.add_child(shape)
		if body.get_child_count() > 0:
			if not unported and not elevators.has(placement):
				for mesh: MeshInstance3D in meshes:
					for child in mesh.get_children():
						if child is StaticBody3D and (child.collision_layer == 1 or child.name == "RoomCollision_1"): child.collision_layer = 0; child.set_meta("native_floor_replaced", true)
			level.add_child(body); count += 1
		else: body.free()
	var walls: Array = source.get(str(area), {}).get("walls", [])
	var wall_boxes: Array = active_boxes(source, area, native_context).filter(func(record: Dictionary) -> bool: return int(record["kind"]) == WALL_KIND and (int(record["mask"]) & 1) != 0)
	if not walls.is_empty() or not wall_boxes.is_empty():
		var wall_body := StaticBody3D.new(); wall_body.name = "NativeWallCells"; wall_body.collision_layer = 0; wall_body.collision_mask = 0; wall_body.set_script(preload("res://scripts/world/core/native_wall_cells.gd"))
		for rect: Array in walls:
			var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); box.size = Vector3(float(rect[1]) - float(rect[0]), 0x8000, float(rect[3]) - float(rect[2])) / 256.0; shape.shape = box; shape.position = Vector3(-float(rect[0]) - float(rect[1]), 0.0, float(rect[2]) + float(rect[3])) / 512.0; wall_body.add_child(shape)
		for record: Dictionary in wall_boxes:
			var x: Array = record["x"]; var y: Array = record["y"]; var z: Array = record["z"]; var shape := CollisionShape3D.new(); var box := BoxShape3D.new(); box.size = Vector3(float(x[1]) - float(x[0]), float(y[1]) - float(y[0]), float(z[1]) - float(z[0])) / 256.0
			if box.size.x <= 0.0 or box.size.y <= 0.0 or box.size.z <= 0.0: continue
			shape.shape = box; shape.position = Vector3(-float(x[0]) - float(x[1]), -float(y[0]) - float(y[1]), float(z[0]) + float(z[1])) / 512.0; wall_body.add_child(shape)
		level.add_child(wall_body)
	return count
static func _volume_enabled(native_context: Dictionary) -> bool:
	if int(native_context.get("native_engine_active_7cec0", 0)) == 0: return true
	var flags: Variant = native_context.get("event_flags", null)
	if not flags is Dictionary: return true
	return bool(flags.get("1795", flags.get(0x703, false)))
static func _footprint(kind: int, x: Array, z: Array) -> Array[Vector2]:
	var x0 := float(x[0]); var x1 := float(x[1]); var z0 := float(z[0]); var z1 := float(z[1]); var corners: Array[Vector2] = []
	match kind >> 4:
		2: corners = [Vector2(x1, z0), Vector2(x1, z1), Vector2(x0, z1)]
		3: corners = [Vector2(x0, z0), Vector2(x1, z0), Vector2(x1, z1)]
		4: corners = [Vector2(x0, z0), Vector2(x1, z0), Vector2(x0, z1)]
		5: corners = [Vector2(x0, z0), Vector2(x0, z1), Vector2(x1, z1)]
		_: corners = [Vector2(x0, z0), Vector2(x1, z0), Vector2(x0, z1), Vector2(x1, z1)]
	return corners
static func _axis_height(orientation: int, x_value: float, z_value: float, x: Array, y: Array, z: Array) -> float:
	var start := float(y[0]); var span := float(y[1]) - start; var progress := 0.0
	if orientation < 2:
		var length := float(z[1]) - float(z[0]); if length == 0.0: return start
		progress = (z_value - float(z[0])) / length if orientation == 0 else (float(z[1]) - z_value) / length
	else:
		var length := float(x[1]) - float(x[0]); if length == 0.0: return start
		progress = (x_value - float(x[0])) / length if orientation == 2 else (float(x[1]) - x_value) / length
	return start + span * progress
static func _diagonal_height(orientation: int, reverse: bool, x_value: float, z_value: float, x: Array, y: Array, z: Array) -> float:
	var x0 := float(x[0]); var x1 := float(x[1]); var z0 := float(z[0]); var z1 := float(z[1]); var y0 := float(y[0]); var y1 := float(y[1]); var width := x1 - x0
	if width == 0.0: return y0
	var distance := 0.0
	match orientation:
		2: distance = (x1 - x_value) + (z1 - z_value)
		3: distance = (x1 - x_value) + (z_value - z0)
		4: distance = (x_value - x0) + (z_value - z0)
		5: distance = (x_value - x0) + (z1 - z_value)
	var height := y1 - (y1 - y0) * distance / width if reverse else y0 + (y1 - y0) * distance / width
	return maxf(y0, height)
static func _point(x: float, y: float, z: float) -> Vector3: return Vector3(-x, -y, z) / 256.0
