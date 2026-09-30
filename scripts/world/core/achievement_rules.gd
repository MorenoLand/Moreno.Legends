extends Node
const RULES: Array[Dictionary] = [
	{"id": "83061", "flags": [0x583], "stage": "ST0F"},
	{"id": "83083", "messages": [["ST20", 55]]},
	# Fire mission cleared (success flag 0x129, ST1ET 0x800E7A54) = all fires out before the sprinklers.
	{"id": "83148", "flags": [0x129]},
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
