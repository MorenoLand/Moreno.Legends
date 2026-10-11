extends Node
const RULES: Array[Dictionary] = [
	{"id": "83061", "flags": [0x583], "stage": "ST0F"},
	{"id": "83067", "flags": [0x589], "stage": "ST25"},
	{"id": "83073", "flags": [0x5B5], "stage": "ST14"},
	{"id": "83083", "messages": [["ST20", 55]]},
	# Fire mission cleared (success flag 0x129, ST1ET 0x800E7A54) = all fires out before the sprinklers.
	{"id": "83148", "flags": [0x129]},
	# Item ownership is the event flag with the item code (ItemFlags): helmets, armors, shoes, buster parts and special weapons are every named code of their range in assets/shops/items.json.
	{"id": "83123", "flags": [0x3B9, 0x3BA]},
	{"id": "83124", "flags": [0x3BD, 0x3BE, 0x3BF, 0x3C0, 0x3C1, 0x3C2, 0x3C3]},
	{"id": "83125", "flags": [0x3C9, 0x3CA, 0x3CB, 0x3CC, 0x3CD]},
	{"id": "83126", "flags": [0x395, 0x396, 0x397, 0x398, 0x399, 0x39A, 0x39B, 0x39C, 0x39D, 0x39E, 0x39F, 0x3A0, 0x3A1, 0x3A2, 0x3A3, 0x3A4, 0x3A5, 0x3A6, 0x3A7, 0x3A8, 0x3A9, 0x3AA, 0x3AB, 0x3AC, 0x3AD, 0x3AE, 0x3AF, 0x3B0, 0x3B1, 0x3B2, 0x3B3]},
	{"id": "83127", "flags": [0x383, 0x384, 0x385, 0x386, 0x387, 0x388, 0x389, 0x38A, 0x38B, 0x38C, 0x38D, 0x38E, 0x38F, 0x390, 0x391]},
	{"id": "83128", "zenny": 2000000},
	{"id": "83129", "messages": [["ST0B", 97], ["ST1B", 136]]},
	{"id": "83130", "messages": [["ST0B", 103], ["ST1B", 142]]},
	{"id": "83133", "flags": [0x8A, 0x2B0, 0x2B1, 0x2B2, 0x2B3, 0x2B4]},
	{"id": "83151", "messages": [["ST32", 47]]},
	{"id": "83152", "flags": [0x10, 0x11, 0x12, 0x13]},
]
var host: Node3D
var awarded: Dictionary = {}
var elapsed := 0.0
func configure(gameplay: Node3D) -> void:
	host = gameplay
	host.dialogue_box.message_started.connect(_message_started)
func _process(delta: float) -> void:
	elapsed += delta
	if elapsed < 0.5: return
	elapsed = 0.0
	if not host.playable or host.loading: return
	evaluate()
func evaluate() -> void:
	var flags: Dictionary = host.native_context.get("event_flags", {}); var stage := str(host.manifest_path.get_base_dir().get_file())
	for rule: Dictionary in RULES:
		if awarded.has(rule["id"]) or (not rule.has("flags") and not rule.has("zenny")) or (rule.has("stage") and rule["stage"] != stage): continue
		var met := true
		for flag: int in rule.get("flags", []): met = met and bool(flags.get(flag, flags.get(str(flag), false)))
		if rule.has("zenny"): met = met and host.player.zenny >= int(rule["zenny"])
		if met: _award(str(rule["id"]))
func _message_started(stage: String, index: int) -> void:
	for rule: Dictionary in RULES:
		for message: Array in rule.get("messages", []):
			if message[0] == stage and message[1] == index: _award(str(rule["id"]))
func _award(id: String) -> void:
	if awarded.has(id): return
	awarded[id] = true
	host.achievement_earned.emit(id)
