extends RefCounted
## One running instance of the original game code for a stage: loads the generated units and the stage images, performs the original stage and area set-up and advances the original gameplay frame.

const Machine := preload("res://scripts/runner/mips_machine.gd")
const Hle := preload("res://scripts/runner/hle.gd")
const Gpu := preload("res://scripts/runner/runner_gpu.gd")
const DIRECTORY := "res://assets/runner/"
const GAME_BLOCK := 0x8009C7E8
## The stage load state (GAME 0x800AFD88) leaves block byte 0 at 3 when it finishes; GAME 0x800BE39C ignores message requests in any other state.
const PLAYING := 3
const STAGE_BYTE := 0x8009C7F8
const AREA_BYTE := 0x8009C7F9
const STORY_PENDING := 0x8009C7FC
const STORY_COMMITTED := 0x8009C7FD
const PLAYER := 0x8008C0A0
const CAMERA_SCRATCH := 0x801F0000
const GEOMETRY := {24: 160 << 16, 25: 120 << 16, 26: 0x180, 27: -0x1062, 28: 0x1400000, 29: 0x155, 30: 0x100}
const RECORD_LIST := 0x8009C2E8
const RECORD_END := 0x1F80006C
const RECORD_BYTES := 20
const RECORD_SLOTS := 64
const PRIMITIVE_RECORDS := 0x801F2800
const PRIMITIVE_END := 0x1F800050
const PRIMITIVE_CURSOR := 0x1F80004C
const RECORD_SHIFT := 0x1F8000B5
const CAMERA_MATRIX := 0x1F800014
## Words of the primitive record types the renderer pass 0x800390EC knows (it stops at any other); 0xF4 holds screen coordinates, the others world positions (0xF0 and 0xF8 scaled by the shift byte).
const PRIMITIVE_WORDS := {0x2C: 10, 0xF0: 6, 0xF4: 6, 0xF8: 8}
const FLAG_BASE := 0x80098538
const FLAG_BYTES := 256
const POOL_BASE := 0x8007A140
const POOL_STRIDE := 0x16C
const POOL_SLOTS := 24
const EFFECT_BASE := 0x80098B08
const EFFECT_STRIDE := 0xCC
const EFFECT_SLOTS := 128
## The disc read queue of the original: SLES 0x8001B2D8 appends a 16 byte command (type 1, file id at +2) and advances this pointer. The runner has no drive, so reads of the stage's sub-stage packs ("bank_loads" of the manifest) are served after each frame.
const READ_QUEUE := 0x80078D64
const NEW_GAME := [[0x8003D1EC, 1], [0x800B8A7C], [0x800390C4], [0x800160EC], [0x800AE328, 0], [0x800C0284, 0], [0x800C256C, 0], [0x800BB0F0, 0], [0x800D97B4, 1], [0x800C35B0, 0]]

var machine: Machine
var hle := Hle.new()
var stage := ""
var manifest := {}
var frame_count := 0
var directory := DIRECTORY
var loaded_module := ""
var read_seen := 0
var area_bank: Dictionary = {}


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
	for kind in ["models", "root", "bank1"]:
		if entry.has(kind):
			machine.load_image(directory + str(entry[kind]["file"]), int(entry[kind]["address"]))
	return machine.load_unit_file("engine", directory + "engine.gd") and machine.load_unit_file("ovl", directory + str(entry["unit"]))


## Runs the new-game initialisers, then the original stage set-up (GAME 0x800BA374) and area set-up (GAME 0x800BA48C) for the given stage number and area.
func begin(stage_number: int, area: int, story: int, flags := {}) -> void:
	machine.put8(0x1F80000D, 0)
	for call in NEW_GAME:
		machine.call_function(call[0], call[1] if call.size() > 1 else 0)
	for section: Dictionary in manifest.get("player", []):
		machine.load_image(directory + str(section["file"]), int(section["address"]))
	for index in 64:
		machine.put16(0x800965D8 + 2 * index, machine.s16(0x80073E4E + 4 * index * 64))
		machine.put16(0x800968D0 + 2 * index, machine.s16(0x80073E4C + 4 * index * 64))
	for register in GEOMETRY:
		machine.gte.ctc2(register, GEOMETRY[register])
	apply_area_bank(area)
	machine.put8(STAGE_BYTE, stage_number)
	machine.put8(AREA_BYTE, area)
	machine.put8(STORY_PENDING, story)
	machine.put8(STORY_COMMITTED, story)
	for id in flags:
		if flags[id]:
			set_flag(int(id))
	machine.call_function(0x800BA374)
	machine.call_function(0x800BA48C, 0)
	machine.put8(GAME_BLOCK, PLAYING)
	read_seen = machine.u32(READ_QUEUE)


## The model archive of the area's sub-stage (manifest area_banks, e.g. the ST13 boss arena, whose actors are only in ST1301.BIN) replaces the stage's own at the loader's bank; the stage's archive returns when another area is entered. The host switches its model directory on the "bank" event.
func apply_area_bank(area: int) -> void:
	var entry: Dictionary = manifest["stages"][stage]
	var banks: Dictionary = entry.get("area_banks", {})
	if banks.is_empty():
		return
	var wanted: Dictionary = banks.get(str(area), {"models": entry["models"], "models_directory": entry["models_directory"]})
	if wanted == area_bank:
		return
	area_bank = wanted
	machine.load_image(directory + str(wanted["models"]["file"]), int(wanted["models"]["address"]))
	hle.bridge.log.append(["bank", {"bank": 0, "models_directory": wanted["models_directory"]}])


## Re-creates the per-frame renderer bookkeeping of the original main loop (SLES 0x80011000..0x800110B0) that the update code writes through: buffer parity, the primitive list pointers and the two record lists the renderer drains (GAME 0x800390C4 resets them; the renderer itself only does so when the frame drew primitives, which the original's HUD always guarantees: without it the 64 slot list at 0x8009C2E8 that every dropped item appends to overflows into the game block).
func begin_frame() -> void:
	machine.gte.depths = {}
	machine.call_function(0x800390C4)
	var parity := (machine.u8(0x1F800004) ^ 1) & 1
	machine.put8(0x1F800004, parity)
	machine.put16(0x1F800006, machine.u16(0x1F800006) + 1)
	machine.put32(0x1F800048, 0x8007D120 + (parity << 14))
	machine.put32(0x1F800050, 0x801F2800 + parity * 0x6000)
	machine.put32(0x1F80004C, machine.u32(0x80068088 + parity * 4 + machine.u8(0x1F80000B) * 8))


## One original gameplay frame: the game state function (stage hook, update pass, area and stage requests), then the main loop's pool sweep (SLES 0x8003EC04 clears the pool bits that actor and object frees only queue; without it every spawn keeps its slot and the 24 actor slots run out).
func frame() -> void:
	begin_frame()
	hle.tick()
	machine.call_function(0x8001D858)
	machine.call_function(0x800AEB30, GAME_BLOCK)
	machine.call_function(0x8003EC04)
	_serve_reads()
	frame_count += 1


func _serve_reads() -> void:
	var head := machine.u32(READ_QUEUE)
	if read_seen == 0 or head < read_seen:
		read_seen = head
	var loads: Dictionary = manifest["stages"][stage].get("bank_loads", {})
	while read_seen < head:
		var entry: Dictionary = loads.get(str(machine.u16(read_seen + 2)), {})
		if machine.u8(read_seen) == 1 and not entry.is_empty() and machine.load_image(directory + str(entry["file"]), int(entry["address"])):
			hle.bridge.log.append(["bank", entry])
		read_seen += 0x10


## Rebuilds the camera matrix the frame's later code overwrote in the scratchpad, runs the effect record renderer (SLES 0x800390EC) on the records of the frame just played and returns its GPU packets.
func render() -> Array:
	prepare_camera()
	return draw()


## Rebuilds the camera matrix in the scratchpad from the frame's last camera call.
func prepare_camera() -> void:
	var view: Array = hle.bridge.camera_last
	if view.is_empty():
		return
	machine.put32(CAMERA_SCRATCH, view[0].x)
	machine.put32(CAMERA_SCRATCH + 4, view[0].y)
	machine.put32(CAMERA_SCRATCH + 8, view[0].z)
	var stack: int = machine.R[29]
	machine.R[29] = CAMERA_SCRATCH + 0x100
	machine.put32(CAMERA_SCRATCH + 0x110, view[4])
	machine.call_function(0x80015B6C, CAMERA_SCRATCH, view[1], view[2], view[3])
	machine.R[29] = stack


## The frame's effect records drawn one at a time (the list pass 0x8003A2D4 over the 20 byte records of dropped items and their shadows, which GAME 0x800B0314 runs before the primitive pass 0x800390EC), so that each record's GPU packets stay tied to its world position: {"world": [{position (game units; absent for the prebuilt quads), packets}], "depths" (screen position to projection depth of the frame), "screen": packets of the records that hold screen coordinates, "camera": {rows, translation, projection, centre}}. The renderer is single record by moving the record to the start of its buffer and ending the list after it.
func render_world() -> Dictionary:
	prepare_camera()
	var world := []
	var screen := []
	if machine.u8(0x1F80000A) == 0:
		var state := {}
		var cursor := machine.u32(PRIMITIVE_CURSOR)
		var list_end := machine.u32(RECORD_END)
		var primitive_end := machine.u32(PRIMITIVE_END)
		var start := PRIMITIVE_RECORDS + machine.u8(0x1F800004) * 0x6000
		var shift := machine.u8(RECORD_SHIFT)
		machine.call_function(0x800158D4)
		var count := clampi((list_end - RECORD_LIST) / RECORD_BYTES, 0, RECORD_SLOTS)
		var listed := []
		for slot in count:
			var base := RECORD_LIST + slot * RECORD_BYTES
			listed.append([_words(base, RECORD_BYTES / 4), Vector3(machine.s16(base + 4), machine.s16(base + 6), machine.s16(base + 8)) * float(1 << shift)])
		var primitives := []
		var address := start
		while address < primitive_end:
			var type := machine.u8(address + 7)
			var words: int = PRIMITIVE_WORDS.get(type & 0xFC, 0)
			if words == 0:
				break
			var scale := 1.0 if type & 0xFC == 0x2C else float(1 << shift)
			primitives.append([_words(address, words), Vector3(machine.s16(address + 8), machine.s16(address + 10), machine.s16(address + 0x10)) * scale, type & 0xFC == 0xF4])
			address += words * 4
		for record: Array in listed:
			_put_words(RECORD_LIST, record[0])
			machine.put32(RECORD_END, RECORD_LIST + RECORD_BYTES)
			var packets := _record_packets(0x8003A2D4, cursor, state)
			if not packets.is_empty():
				world.append({"position": record[1], "packets": packets})
		var index := 0
		while index < primitives.size():
			var record: Array = primitives[index]
			var run: Array = [record]
			if int(record[0][1]) >> 24 & 0xFC == 0x2C:  # the quads of one effect (the lightning of a pylon pair) are drawn as one run: a lone quad record emits nothing
				while index + run.size() < primitives.size() and int(primitives[index + run.size()][0][1]) >> 24 & 0xFC == 0x2C:
					run.append(primitives[index + run.size()])
			index += run.size()
			var words := []
			for part: Array in run:
				words.append_array(part[0])
			_put_words(start, words)
			machine.put32(PRIMITIVE_END, start + words.size() * 4)
			var linked: bool = int(record[0][1]) >> 24 & 0xFC == 0x2C  # these records are the packets themselves: the pass finishes them in place and links them into the ordering table without allocating primitives
			if linked:
				Gpu.clear(machine)
			var packets := _record_packets(0x800390EC, cursor, state)
			if linked:
				packets = Gpu.read(machine)
			if record[2]:
				screen.append_array(packets)
			elif not packets.is_empty():
				world.append({"packets": packets} if linked else {"position": record[1], "packets": packets})
		machine.call_function(0x800158F8)
		machine.put32(RECORD_END, list_end)
		machine.put32(PRIMITIVE_END, primitive_end)
		machine.put32(PRIMITIVE_CURSOR, cursor)
	var rows := []
	for row in 3:
		rows.append(Vector3(machine.s16(CAMERA_MATRIX + row * 6), machine.s16(CAMERA_MATRIX + row * 6 + 2), machine.s16(CAMERA_MATRIX + row * 6 + 4)) / 4096.0)
	return {"world": world, "screen": screen, "depths": machine.gte.depths, "camera": {"rows": rows, "translation": Vector3(machine.s32(CAMERA_MATRIX + 0x14), machine.s32(CAMERA_MATRIX + 0x18), machine.s32(CAMERA_MATRIX + 0x1C)), "projection": gte_projection(), "centre": Vector2(machine.gte.c[24] >> 16, machine.gte.c[25] >> 16)}}


func _words(address: int, count: int) -> Array:
	var result := []
	for index in count:
		result.append(machine.u32(address + index * 4))
	return result


func _put_words(address: int, words: Array) -> void:
	for index in words.size():
		machine.put32(address + index * 4, words[index])


## Runs one renderer pass on the record in place and returns the packets it wrote after the buffer cursor, which is then reset.
func _record_packets(pass_address: int, cursor: int, state: Dictionary) -> Array:
	machine.put32(PRIMITIVE_CURSOR, cursor)
	machine.call_function(pass_address)
	return Gpu.span(machine, cursor, machine.u32(PRIMITIVE_CURSOR), state)


func draw() -> Array:
	Gpu.clear(machine)
	machine.call_function(0x800158D4)
	machine.call_function(0x800390EC)
	machine.call_function(0x800158F8)
	return Gpu.read(machine)


## The backdrop strips of the area's colour table for the camera of the frame just rendered (empty when the area has no backdrop).
func background() -> Array:
	machine.call_function(0x800158D4)
	var packets: Array = Gpu.bands(machine)
	machine.call_function(0x800158F8)
	return packets


## The GTE projection plane distance (control register 26) of the last render.
func gte_projection() -> int:
	return machine.gte.c[26] & 0xFFFF


## Loads the module of the original code for a special weapon (PL00R(weapon - 1)) and its animation sections.
func equip_weapon(weapon: int) -> bool:
	var module := "PL00R%02X" % (weapon - 1)
	var entry: Dictionary = manifest.get("modules", {}).get(module, {})
	if entry.is_empty():
		return false
	# Weapons without a sequence handler in the table at 0x800DCD08 (the Shield Arm) would jump to address 0; the empty handler 0x800CE808 stands in.
	var handler := 0x800DCD08 + 4 * weapon
	if machine.u32(handler) == 0:
		machine.put32(handler, 0x800CE808)
	if loaded_module != module:
		for section: Dictionary in entry["sections"]:
			machine.load_image(directory + str(section["file"]), int(section["address"]))
		if not machine.load_unit_file("module", directory + str(entry["unit"])):
			return false
		loaded_module = module
	return true


func set_flag(id: int) -> void:
	machine.call_function(0x800C0558, id)


func clear_flag(id: int) -> void:
	machine.call_function(0x800C0584, id)


func flag(id: int) -> bool:
	return machine.call_function(0x800C05B4, id) != 0


func read_flags() -> PackedByteArray:
	return machine.ram.slice(FLAG_BASE & 0x9FFFFF, (FLAG_BASE & 0x9FFFFF) + FLAG_BYTES)


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


## Live objects of the effect pool (debris and other short-lived objects); their models are drawn by the port, their records are not actors.
func effect_slots() -> Array:
	var result := []
	for slot in EFFECT_SLOTS:
		var object := EFFECT_BASE + slot * EFFECT_STRIDE
		if machine.u8(object) & machine.u8(object + 1) & 1 == 1:
			result.append(object)
	return result
