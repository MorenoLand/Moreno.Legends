extends RefCounted
## One running instance of the original game code for a stage: loads the generated units and the stage images, performs the original stage and area set-up and advances the original gameplay frame.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Hle := preload("res://scripts/runner/hle.gd")
const DIRECTORY := "res://assets/runner/"
const GAME_BLOCK := 0x8009C7E8
const STAGE_BYTE := 0x8009C7F8
const AREA_BYTE := 0x8009C7F9
const STORY_PENDING := 0x8009C7FC
const STORY_COMMITTED := 0x8009C7FD
const PLAYER := 0x8008C0A0
const POOL_BASE := 0x8007A140
const POOL_STRIDE := 0x16C
const POOL_SLOTS := 24
const NEW_GAME := [[0x8003D1EC, 1], [0x800B8A7C], [0x800390C4], [0x800160EC], [0x800AE328, 0], [0x800C0284, 0], [0x800C256C, 0], [0x800BB0F0, 0], [0x800D97B4, 1], [0x800C35B0, 0]]

var machine: Machine
var hle := Hle.new()
var stage := ""
var manifest := {}
var frame_count := 0
var directory := DIRECTORY


func open(stage_name: String, source := DIRECTORY) -> bool:
	directory = source
	var text := FileAccess.get_file_as_string(directory + "manifest.json")
	if text.is_empty():
		return false
	manifest = JSON.parse_string(text)
	if not manifest["stages"].has(stage_name):
		return false
	stage = stage_name
	var entry: Dictionary = manifest["stages"][stage]
	machine = Machine.new(directory)
	machine.set_hle(hle)
	machine.load_image(directory + str(manifest["ram"]), 0x80000000)
	machine.load_image(directory + str(entry["image"]), int(entry["base"]))
	for kind in ["models", "root"]:
		machine.load_image(directory + str(entry[kind]["file"]), int(entry[kind]["address"]))
	return machine.load_unit("engine", FileAccess.get_file_as_string(directory + "engine.gd")) and machine.load_unit("ovl", FileAccess.get_file_as_string(directory + str(entry["unit"])))


## Runs the new-game initialisers, then the original stage set-up (GAME 0x800BA374) and area set-up (GAME 0x800BA48C) for the given stage number and area.
func begin(stage_number: int, area: int, story: int) -> void:
	machine.put8(0x1F80000D, 0)
	for call in NEW_GAME:
		machine.call_function(call[0], call[1] if call.size() > 1 else 0)
	machine.put8(STAGE_BYTE, stage_number)
	machine.put8(AREA_BYTE, area)
	machine.put8(STORY_PENDING, story)
	machine.put8(STORY_COMMITTED, story)
	machine.call_function(0x800BA374)
	machine.call_function(0x800BA48C, 0)


## Re-creates the per-frame renderer bookkeeping of the original main loop (SLES 0x80011000..0x800110B0) that the update code writes through: buffer parity and the primitive list pointers.
func begin_frame() -> void:
	var parity := (machine.u8(0x1F800004) ^ 1) & 1
	machine.put8(0x1F800004, parity)
	machine.put16(0x1F800006, machine.u16(0x1F800006) + 1)
	machine.put32(0x1F800048, 0x8007D120 + (parity << 14))
	machine.put32(0x1F800050, 0x801F2800 + parity * 0x6000)
	machine.put32(0x1F80004C, machine.u32(0x80068088 + parity * 4 + machine.u8(0x1F80000B) * 8))


## One original gameplay frame: the game state function (stage hook, update pass, area and stage requests).
func frame() -> void:
	begin_frame()
	hle.tick()
	machine.call_function(0x8001D858)
	machine.call_function(0x800AEB30, GAME_BLOCK)
	frame_count += 1


func set_flag(id: int) -> void:
	machine.call_function(0x800C0558, id)


func clear_flag(id: int) -> void:
	machine.call_function(0x800C0584, id)


func flag(id: int) -> bool:
	return machine.call_function(0x800C05B4, id) != 0


func faults() -> Array:
	var result := []
	for unit in machine.units.values():
		for address in unit.faults:
			if not result.has(address):
				result.append(address)
	return result


func actor_slots() -> Array:
	var result := []
	for slot in POOL_SLOTS:
		var actor := POOL_BASE + slot * POOL_STRIDE
		if machine.u8(actor) & machine.u8(actor + 1) & 1 == 1:
			result.append(actor)
	return result
