extends RefCounted
const BUSTER := 2
const ATTACK := 0
const ENERGY := 1
const RANGE := 2
const RAPID := 3
const SLOTS := ["helmet", "armor", "shoes"]
var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/weapon_stats.json"))
var outfits: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/outfits/outfits.json"))
var outfit_meshes: Dictionary = {}
var parts: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/status.json"))["buster_parts"]
func buster_levels(equipped: Array) -> Array:
	var total := [0, 0, 0, 0]
	for id: Variant in equipped:
		for stat in 4: total[stat] += int(parts["stats"].get(str(id), [0, 0, 0, 0, 0])[stat])
	for stat in 4: total[stat] = mini(total[stat], int(parts["maximum"]))
	return total
func value(weapon: int, stat: int, level: int) -> int:
	var levels: Array = data["weapons"][str(weapon)]["levels"]
	return int(levels[clampi(level, 0, levels.size() - 1)][stat])
func fire_pose(weapon: int) -> int: return int(data["weapons"][str(weapon)]["firing"][1])
func body_part(equipped: Array, slot: String) -> int:
	var id := str(equipped[SLOTS.find(slot)])
	return 0 if id.is_empty() else maxi(int(id) - int(data["body_parts"][slot + "_base"]), 0)
func outfit(helmet: int, shoes: int) -> String: return outfits["rows"][mini(helmet, 2)][clampi(shoes, 0, 5)]
func outfit_mesh(name: String) -> Mesh:
	if not outfit_meshes.has(name):
		var scene := load("res://assets/player/megaman.glb" if name == outfits["base"] else str(outfits["model_dir"]) + name + ".glb") as PackedScene
		var instance := scene.instantiate()
		outfit_meshes[name] = (instance.find_children("*", "MeshInstance3D", true, false)[0] as MeshInstance3D).mesh
		instance.free()
	return outfit_meshes[name]
