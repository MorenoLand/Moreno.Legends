"""Export the ST1E Flutter fire mission (PAL): doors.json, fire_mission.json, fire_atlas.png and the native scene
contracts for scene 0 (door) and scene 0xD (result), using DAT/ST1ET.BIN static tables, immediate-checked overlay
constants and a unicorn emulation (tools/intro_scene.Emu) of the unchanged area handlers and scene callbacks."""
import argparse, json, shutil, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
import intro_scene
import unicorn
import ui
import world
STAGE = "ST1E"; BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0; ROOM = 0x8009C900; STATE = 0x8009BE08; REQ = 0x80078D08; FLAGS = 0x80098538; NPC_TABLE = 0x800EE94C; CAMERA = 0x80096D50
ROUTES = 0x800EEEA8; SPAWNS = {0: (0x800EF1FC, 4), 1: (0x800EF24C, 13), 2: (0x800EF364, 5)}; EXTRA_FIRE = 0x800EF350; SIZES = 0x800EF474; FRAMES = 0x800EF494
AREA_HANDLERS = 0x800EF1F0; PER_FRAME = 0x800E744C; SCENE_D = 0x800ED7B8; SCENE_0 = 0x800ED1EC
D = {}
def rd(a, n): o = 0x30 + a - BASE; return D["ovl"][o:o + n]
def u8(a): return rd(a, 1)[0]
def u16(a): return struct.unpack("<H", rd(a, 2))[0]
def s16(a): return struct.unpack("<h", rd(a, 2))[0]
def u32(a): return struct.unpack("<I", rd(a, 4))[0]
def s8(v): return v - 256 if v & 128 else v
def H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def K(a, value, game=False):
	word = struct.unpack_from("<I", D["game"], 0x30 + a - 0x800AD000)[0] if game else u32(a)
	if word & 0xFFFF != value & 0xFFFF: raise ValueError(f"{'GAME' if game else 'ST1ET'} instruction {a:#x} immediate {word & 0xFFFF:#x} != {value & 0xFFFF:#x}")
	return value
def SH(a, value):
	if (u32(a) >> 6) & 31 != value: raise ValueError(f"ST1ET instruction {a:#x} shift differs from {value}")
	return value
def load(root):
	disc = Path(root) / "build/disc-assets"; D.update(root=Path(root), disc=disc, sles=(disc / "SLES_035.56").read_bytes(), game=(disc / "COMMON/GAME.BIN").read_bytes(), ovl=(disc / "DAT/ST1ET.BIN").read_bytes(), stage=(disc / "DAT/ST1E.BIN").read_bytes())
	if struct.unpack_from("<4I", D["ovl"], 0)[0] != 1 or struct.unpack_from("<I", D["ovl"], 12)[0] != BASE: raise ValueError("unexpected ST1ET header")
	intro_scene.SLES = D["sles"]; intro_scene.GAME = D["game"]; intro_scene.OVL = D["ovl"]
def record(a):
	b = rd(a, 20); x, y, z, yaw = struct.unpack_from("<3hH", b, 12)
	return {"source_ram": H(a), "bytes_hex": b.hex(), "flags": b[0], "slot": b[1], "pool": b[2], "pool_flags": b[3], "class": b[4], "variant": b[5], "size": b[6], "index": b[8], "contact_damage": b[9], "behaviour": b[10], "position_raw": [x, y, z], "yaw_raw": yaw}

# ------------------------------------------------------------------ doors
def export_doors(dat_dir, levels_dir, out_dir):
	if (K(0x800E73E0, 0x800F) << 16) + K(0x800E73EC, -0x1158) != ROUTES or K(0x800E7404, -0x705C) != -0x705C: raise ValueError("ST1E route table binding differs")
	source = Path(levels_dir) / STAGE; target = Path(out_dir) / STAGE; target.mkdir(parents=True, exist_ok=True); copies = []
	if source.resolve() != target.resolve():
		for item in [source / "manifest.json", *sorted(source.glob("area_??.glb"))]:
			if not (target / item.name).exists(): shutil.copy2(item, target / item.name); copies.append(target / item.name)
	overlay = (Path(dat_dir) / (STAGE + "T.BIN")).read_bytes(); original = world.native_area_tables
	world.native_area_tables = lambda data: {**original(data), "routes": [{"pointer_ram": ROUTES, "source_call": "0x800e73e8"}]} if data == overlay else original(data)
	try: world.export_routes(Path(dat_dir), Path(out_dir), [STAGE])
	finally:
		world.native_area_tables = original
		for item in copies: item.unlink()
	path = target / "doors.json"; doors = json.loads(path.read_text(encoding="utf-8"))
	unlocks = {0x711: {"cleared_by": "area 0 handler when room fire count (0x8009C904) reaches 0", "source": "0x800E766C"}, 0x713: {"cleared_by": "area 1 handler when room fire count reaches 0", "source": "0x800E7878"}}
	for route in doors["area_transitions"]:
		route["locked_message"] = route["blocked_message"]; route["lock_unlocked_by"] = unlocks.get(route["lock_event"], {"cleared_by": None, "note": "ST1ET never clears this flag; the door stays shut (decoy or backward door)"})
		route["lock_set_by"] = {0: "0x800E7504..0x800E7528 (area 0 entry sets 0x711..0x715)", 1: "0x800E7704..0x800E7720 (area 1 entry sets 0x711..0x714)", 2: "0x800E7910..0x800E792C (area 2 entry sets 0x711..0x714)"}[route["source_area"]]
		route["message_bank"] = {"stage": STAGE, "bank_ram": "0x8010C000", "consumer": "GAME0x800B89C4..0x800B8A10 shows record+4 through 0x800BE330 when GAME0x800B89B4 reports the door locked"}
	doors["source"]["area_route_pointer_ram"] = H(ROUTES); doors["source"]["binding"] = "ST1ET 0x800E73E0/0x800E73EC load 0x800EEEA8, indexed by area byte 0x8009C7F9, stored to 0x80078FA4 at 0x800E7404 (delay slot of GAME0x800CF4A8 call; not matched by world.native_area_tables)"; doors["binding_status"] = "bound"
	doors["fire_mission_locks"] = {"global_lock": 0x710, "per_door": "0x710 + (door_id & 0x1F)", "runtime_clears": [0x711, 0x713], "never_cleared": [0x712, 0x714, 0x715]}
	world.write_if_changed(path, json.dumps(doors, indent=2) + "\n", encoding="utf-8"); return doors

# ------------------------------------------------------------------ emulation
EXTRA_STUBS = ((0x800C0818, "spawn_table", 0, True, False), (0x800BE330, "conversation", 0, True, False), (0x8003B918, "overlay_show", 0, True, False), (0x8003B9C4, "overlay_hide", 0, True, False),
	(0x800C0B0C, "scene_start", 0, True, False), (0x800E7B20, "radio_message", 0, True, False), (0x80020984, "jingle", 0, True, False), (0x80043F70, "call_43F70", 0, True, False),
	(0x800CDD8C, "player_busy", 0, False, False), (0x800203F4, "sound_3d", 0, True, False), (0x800C10B4, "skip_check", 0, False, False), (0x80042704, "hitbox", 0, True, False),
	(0x800B1228, "cell_lookup", 0x801F0000, False, False), (0x80038EF4, "placement_visibility", 0, True, False), (0x800B1864, "floor_probe", 0, False, False), (0x800B3564, "floor_snap", 0, False, False),
	(0x800CD084, "player_move", 0, True, False), (0x8003E800, "alloc_actor", 0, True, False), (0x8003E820, "alloc_actor", 0, True, False), (0x8003E918, "alloc_actor", 0, True, False), (0x800411C4, "actor_shape_setup", 0, True, False))
class Emu(intro_scene.Emu):
	def __init__(self):
		super().__init__(()); self.room = False
		for address, name, value, recorded, run in EXTRA_STUBS:
			self.stubs[address] = (name, value, recorded, run); self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=address, end=address)
		for pointer, table in ((0x80078FA8, NPC_TABLE), (0x80078DE0, 0x800EEAE8), (0x80078CFC, 0x800EEBE4), (0x80078DCC, 0x800EEBE8), (0x80078EA0, 0x800EEC34), (0x80078E7C, 0x800EEEB4), (0x80078FB4, 0x800EE2D0)): self.w32(pointer, table)
		self.w16(PLAYER + 0x70, 0x30); self.w16(PLAYER + 0x72, 0x30)
	def w16(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, struct.pack("<H", v & 0xFFFF))
	def flag(self, flag, on=True):
		a = FLAGS + (flag >> 3); self.w8(a, self.u8(a) | (1 << (flag & 7)) if on else self.u8(a) & ~(1 << (flag & 7)))
	def test(self, flag): return bool(self.u8(FLAGS + (flag >> 3)) & (1 << (flag & 7)))
	def record(self, kind, **kw):
		super().record(kind, **kw); self.events[-1]["state"] = self.u8(CTX + 4)
		if self.room: self.events[-1]["room"] = {"fires": self.u8(ROOM + 4), "extinguished": self.u8(ROOM + 5), "timers": [self.u16(ROOM + o) for o in (0xA, 0xC, 0xE)], "idle": self.u16(ROOM + 0x10), "area_state": self.u8(STATE)}
	def stub_hook(self, uc, address, size, data):
		name = self.stubs[address][0]; a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
		if name == "message": self.record("message", window=a[0], bank=H(a[1]), index=a[2], caller=H(ra - 8)); return self._ret(uc, 0, ra)
		if name == "conversation": self.record("conversation", args=[intro_scene.s32(x) for x in a], index=self.u32(self.r(29) + 0x10), caller=H(ra - 8)); return self._ret(uc, 0, ra)
		if name == "alloc_actor":
			pointer = self.free.pop(0); uc.mem_write(pointer & 0x1FFFFFFF, bytes(0x400)); self.record("alloc", function=H(address), ptr=H(pointer), caller=H(ra - 8)); return self._ret(uc, pointer, ra)
		return super().stub_hook(uc, address, size, data)
	def write_data(self, index, value):
		super().write_data(index, value)
		if index == 30: v = value & 0xFFFFFFFF; v = v ^ 0xFFFFFFFF if v & 0x80000000 else v; self.data[31] = 32 - v.bit_length()
	def operation(self, word):
		if word & 63 != 0x28: return super().operation(word)
		shift = 12 if word & (1 << 19) else 0; lower = 0 if word & 1024 else -32768
		for row in range(3): value = (intro_scene.s16(self.data[9 + row]) ** 2) >> shift; self.data[25 + row] = value & 0xFFFFFFFF; self.data[9 + row] = max(lower, min(32767, value))
		self.control[31] = 0
	def init_flags(self, flags):
		for flag in flags: self.flag(flag)

def emulate_area(area, clear_at=None, trigger_at=None, ticks=6000):
	e = Emu(); e.room = True; e.w8(0x8009C7F9, area); e.w8(STATE, 0); e.cpu.mem_write(ROOM & 0x1FFFFFFF, bytes(0x3C))
	for tick in range(ticks):
		e.call(PER_FRAME)
		if area == 2 and e.u8(STATE) == 1 and e.test(0x681): e.flag(0x681, False); e.record("simulated_message_end", flag=0x681, note="Data's message 0x03 closes (class 0x1D actor not emulated)")
		if trigger_at is not None and tick == trigger_at: e.w16(ROOM + 6, 1); e.record("simulated_trigger", field="room+6", note="fire with +0xE bit1 extinguished")
		if clear_at is not None and tick == clear_at: e.w8(ROOM + 4, 0); e.record("simulated_room_clear", field="room+4")
		if any(x["kind"] == "scene_start" for x in e.events): break
	return e, tick

def fire_math():
	e = Emu(); actor = 0x80190000; rows = []
	for size in range(4):
		for distance in (0x40, 0x80, 0xC0, 0x100, 0x140):
			for hit in (0x40010, 0x42010, 0x2010, 0x10000, 0):
				e.cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x100)); e.w8(actor + 6, size); e.w32(actor + 0x10, 0); e.w32(actor + 0x14, 0); e.w32(actor + 0x18, 0); e.w32(PLAYER + 0x10, distance << 16); e.w32(PLAYER + 0x14, 0); e.w32(PLAYER + 0x18, 0)
				maximum = u16(SIZES + size * 8 + 4); e.w32(actor + 0x74, hit); e.w32(actor + 0x7C, 0x700); e.w32(actor + 0x80, maximum); result = intro_scene.s32(e.call(0x800EA600, (actor,)))
				rows.append({"size": size, "player_distance_raw": distance, "hit_word": H(hit), "strength_before": 0x700, "result": result, "strength_after": intro_scene.s32(e.u32(actor + 0x7C))})
	boxes = []
	for size in range(4):
		for strength in (0x200, 0x800, 0x1000, 0x1C00):
			e.events.clear(); e.cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x100)); e.w8(actor + 2, 0x60); e.w8(actor + 6, size); e.w8(actor + 0xD, 8); e.w32(actor + 0x10, 0x100 << 16); e.w32(actor + 0x14, 0); e.w32(actor + 0x18, 0x200 << 16); e.w32(actor + 0x7C, strength); e.call(0x800EA6E4, (actor,))
			hit = [x for x in e.events if x["kind"] == "hitbox"][0]; center = [struct.unpack("<h", bytes(e.cpu.mem_read((0x1F800120 + k * 2) & 0x1FFFFFFF, 2)))[0] for k in range(3)]
			boxes.append({"size": size, "strength": strength, "center_raw": center, "a2": H(hit["args"][2]), "a3": H(hit["args"][3]), "radius_raw": (hit["args"][2] & 0xFFFF) * 4})
	return rows, boxes

def formula(hit, distance, strength=0x700, maximum=0x800):
	if not hit & 0x42000: return strength
	damage = (hit & 0xFFF) << 5
	if hit & 0x2000: d = 0x100 if distance > 0x100 else 0x80 if distance < 0x80 else distance; damage += ((((0x100 - d) * 13) << 6 >> 7) + 0x3C0) >> 3
	if not damage: return strength
	return 0 if strength - damage <= 0x200 else strength - damage

def actor_update(e, tracks, w):
	for ptr, slot in list(e.actors.items()):
		if ptr not in e.actors: continue
		function = e.u32(e.u32(NPC_TABLE + e.u8(ptr + 4) * 4) + e.u8(ptr + 5) * 4); e.cur = slot; e.call(function, (ptr,))
		tracks.setdefault(slot, []).append((0, w["step"], w["frame"], intro_scene.s32(e.u32(ptr + 0x10)), intro_scene.s32(e.u32(ptr + 0x14)), intro_scene.s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, 0))
	e.cur = None

def player_row(e, w): return (0, w["step"], w["frame"], intro_scene.s32(e.u32(PLAYER + 0x10)), intro_scene.s32(e.u32(PLAYER + 0x14)), intro_scene.s32(e.u32(PLAYER + 0x18)), e.u16(PLAYER + 0x2A) & 4095, 0)

def emulate_result(success):
	e = Emu(); e.cpu.mem_write(ROOM & 0x1FFFFFFF, bytes(0x3C)); e.w8(0x8009C7F9, 2)
	if success: e.flag(0x129); e.w16(ROOM + 0xA, 0x400); e.w16(ROOM + 0xC, 0x400); e.w16(ROOM + 0xE, 0x400); e.w8(ROOM + 5, 23)
	else: e.w16(ROOM + 0xA, 0x708); e.w8(ROOM + 5, 4)
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1); e.actors[ptr] = slot; e.record("spawn", slot=slot, record=H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); tracks = {}; requests = []; skip = []; previous = None
	for tick in range(6000):
		state = e.u8(CTX + 4)
		if state > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.cur = None; e.call(SCENE_D, (CTX,)); w = e.where()
		lock = bool(e.u8(CTX) & 0x20)
		if lock != previous: e.record("skip_lock", set=lock); previous = lock
		if e.u8(REQ):
			raw = bytes(e.cpu.mem_read(REQ & 0x1FFFFFFF, 0x1A)); e.record("request_block", bytes=raw.hex()); requests.append(raw); e.w8(REQ, 0)
		actor_update(e, tracks, w); tracks.setdefault("player", []).append(player_row(e, w))
	return e, tracks, requests, tick

def emulate_door(route):
	e = Emu(); raw = bytes.fromhex(route["bytes_hex"]); e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(0x8009C7F9, route["source_area"])
	block = bytearray(0x1A); block[0] = 1; block[2] = raw[0]; block[3] = raw[1]; block[4] = raw[6]; block[5] = raw[7]; block[7] = raw[2]; block[8:0x18] = raw[8:24]; e.cpu.mem_write(REQ & 0x1FFFFFFF, bytes(block))
	x, y, z, yaw = route["source_transform_raw"]; e.w32(PLAYER + 0x10, x << 16); e.w32(PLAYER + 0x14, y << 16); e.w32(PLAYER + 0x18, z << 16); e.w16(PLAYER + 0x2A, yaw); e.flag(0x700)
	door = None; tracks = {"player": []}; door_rows = []; camera = None
	for tick in range(400):
		state = e.u8(CTX + 4)
		if state > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.call(SCENE_0, (CTX,)); w = e.where()
		if camera is None and e.u8(CTX + 4) == 1:
			door = e.u32(CTX + 0x2C); camera = {"focus_raw": [intro_scene.s32(e.u32(CAMERA + o)) / 65536 for o in (8, 0xC, 0x10)], "orbit_raw": [intro_scene.s32(e.u32(CAMERA + o)) / 65536 for o in (0x58, 0x5C, 0x60)], "player_after_setup_raw": [intro_scene.s32(e.u32(PLAYER + o)) / 65536 for o in (0x10, 0x14, 0x18)] + [e.u16(PLAYER + 0x2A)], "door_actor": {"class": e.u8(door + 4), "variant_byte6": e.u8(door + 6), "position_raw": [intro_scene.s32(e.u32(door + o)) >> 16 for o in (0x10, 0x14, 0x18)]}}
		if door: door_rows.append({"step": w["step"], "tick": w["frame"] - 1, "byte8": e.u8(door + 8), "byte9": e.u8(door + 9), "half4A": struct.unpack("<h", struct.pack("<H", e.u16(door + 0x4A)))[0], "half4E": struct.unpack("<h", struct.pack("<H", e.u16(door + 0x4E)))[0]})
		if e.u8(CTX + 4) == 2 and e.u8(REQ) == 1: e.w8(REQ, 2); e.record("simulated_request_ready", value=2)
		if e.u8(REQ) == 3: e.record("request_block", bytes=bytes(e.cpu.mem_read(REQ & 0x1FFFFFFF, 0x1A)).hex()); e.w8(REQ, 0)
		tracks["player"].append(player_row(e, w))
	return e, tracks, door_rows, camera, tick

SCENE_STUBS = ((0x800D97EC, "stage_setup", 0, False, False), (0x8001D7C4, "stage_audio", 0, False, False), (0x80041724, "face_eyes_frame", 0, True, True), (0x8004173C, "face_mouth_frame", 0, True, True), (0x8001B2D8, "file_load", 0, True, False), (0x80023040, "player_bank", 0, True, False),
	(0x800C0EA8, "advance", 0, True, True), (0x80041358, "face_tick", 0, False, False), (0x8003DFC8, "resource_ready", 1, False, False), (0x80041204, "face_dims", 0, False, False))
def stage_emulator(stage_init, gte_start, code_end, stubs=(), area_byte=0x8009C7F9):
	class StageEmu(Emu):
		def __init__(self):
			super().__init__(); self.phase_events = True; self.pools = {}; self.requests = []
			code = D["ovl"][0x30:]
			for off in range(gte_start - BASE, code_end - BASE, 4):
				w = struct.unpack_from("<I", code, off)[0]; op = w >> 26
				if op == 18 and ((w >> 25) & 1 or (w >> 21) & 31 in (0, 2, 4, 6)) or op in (50, 58): self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.gte, begin=BASE + off, end=BASE + off)
			hooked = set(self.stubs)
			for address in [a for a in self.stubs if BASE <= a < 0x80180000]: del self.stubs[address]
			for address, name, value, recorded, run in SCENE_STUBS + tuple(stubs):
				if address not in hooked: self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=address, end=address); hooked.add(address)
				self.stubs[address] = (name, value, recorded, run)
			for address in (0x8003E5B0, 0x8003E800, 0x8003E820, 0x8003E918, 0x8003EA4C, 0x8003EB7C, 0x8003D658): self.stubs[address] = (self.stubs.get(address, ("native",))[0], 0, True, True)
			for pointer in (0x80078FA8, 0x80078DE0, 0x80078CFC, 0x80078DCC, 0x80078EA0, 0x80078E7C, 0x80078FB4): self.w32(pointer, 0)
			self.call(stage_init)
		def where(self): return dict(super().where(), phase=self.u8(CTX + 2))
		def call(self, function, args=()):
			self.w32(0x1F80004C, 0x801C0000); self.w32(0x1F800050, 0x801D0000); return super().call(function, args)
		def stub_hook(self, uc, address, size, data):
			if address not in self.stubs: return
			name = self.stubs[address][0]; a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
			if name == "advance" and self.u8(REQ): self.request()
			if name == "despawn": self.record("despawn", record=self.actors.pop(a[0], None), caller=H(ra - 8)); return
			if name == "alloc_actor": self.record("alloc", function=H(address), caller=H(ra - 8)); return
			return super().stub_hook(uc, address, size, data)
		def request(self):
			raw = bytes(self.cpu.mem_read(REQ & 0x1FFFFFFF, 0x1A)); self.record("request_block", bytes=raw.hex()); self.requests.append(raw)
			if raw[0] == 0xFF: self.w8(area_byte, raw[5])
			self.w8(REQ, 0)
	return StageEmu
def run_scene(e, handler, watch, ticks=20000):
	tracks = {}; previous = {kind: initial for kind, (initial, _) in watch.items()}
	for tick in range(ticks):
		if e.u8(CTX + 4) > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.cur = None; e.call(handler, (CTX,)); w = e.where()
		for kind, (_, read) in watch.items():
			value = read(e)
			if value != previous[kind]: e.record(kind, value=value, offset_raw=[e.u16(CTX + 0x10), e.u16(CTX + 0x12)]); previous[kind] = value
		if e.u8(REQ): e.request()
		for ptr, rec in list(e.actors.items()):
			if ptr not in e.actors: continue
			if not e.u8(ptr) & e.u8(ptr + 1) & 1: e.actors.pop(ptr); e.record("released", record=rec); continue
			flags = e.u8(ptr + 3)
			if e.pools[ptr][2] != 0x20 and (flags & 4 or not flags & 8): continue
			e.cur = rec; e.call(e.u32(e.u32(e.u32(0x80078FA8 if e.pools[ptr][2] == 0x20 else 0x80078DE0) + e.u8(ptr + 4) * 4) + e.u8(ptr + 5) * 4), (ptr,))
			tracks.setdefault(rec, []).append((0, w["step"], w["frame"], intro_scene.s32(e.u32(ptr + 0x10)), intro_scene.s32(e.u32(ptr + 0x14)), intro_scene.s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, w["phase"]))
		e.cur = None; tracks.setdefault("player", []).append(player_row(e, w) + ())
	return tracks, tick

# ------------------------------------------------------------------ sprites
def vram():
	memory = bytearray(1024 * 512 * 2); uploads = []
	for name in ("COMMON/GAME.BIN", "COMMON/PL00T.BIN", "DAT/ST1ET.BIN"): uploads.extend({k: v for k, v in item.items() if k in ("file", "section_offset", "palette_rect", "image_rect")} for item in world.texture_uploads((D["disc"] / name).read_bytes(), memory, name))
	return memory, uploads
def fire_frames(size):
	out = []; a = FRAMES + size * 0x80
	for index in range(16):
		u, v, w, h, ticks, end = rd(a + index * 8, 6); out.append({"index": index, "source_ram": H(a + index * 8), "u": u, "v": v, "w": w, "h": h, "ticks": ticks, "last": end == 0xFF})
		if end == 0xFF: break
	return out
EFFECTS = {1: {"name": "steam_puff", "anim": 0x800F03C0, "page": 0x800F0398, "count": 5, "size": 0x800F0780, "rise": 0x800F078C, "init": "0x800EC2D0", "update": "0x800EC360"}, 2: {"name": "explosion_flame", "anim": 0x800F07A0, "page": 0x800F0798, "count": 1, "size": 0x800F0860, "init": "0x800EC3CC", "update": "0x800EC464"},
	4: {"name": "explosion_debris", "anim": 0x800F087C, "page": 0x800F0864, "count": 3, "size": 0x800F0ABC, "init": "0x800EC69C", "update": "0x800EC760"}, 5: {"name": "ember", "anim": 0x800F0ACC, "page": 0x800F0AC4, "count": 1, "size": 0x800F0B8C, "init": "0x800EC8A8", "update": "0x800EC938"}, 6: {"name": "data_flame", "anim": 0x800F0ACC, "page": 0x800F0AC4, "count": 1, "init": "0x800ECC7C", "update": "0x800ECCF0"}}
def effect_frames(spec, sub):
	out = []; a = spec["anim"] + sub * 0xC0
	for index in range(16):
		b = rd(a + index * 12, 12); command = struct.unpack_from("<I", b)[0]
		out.append({"index": index, "source_ram": H(a + index * 12), "command": H(command), "rgb": [command & 255, (command >> 8) & 255, (command >> 16) & 255], "u0": b[4], "v0": b[5], "u1": b[6], "v1": b[7], "ticks": b[8], "next": {0xFF: "die", 0x80: "loop"}.get(b[9], "next"), "next_raw": b[9], "size_delta_per_tick": s8(b[10]), "rotation_delta_per_tick": s8(b[11])})
		if b[9] in (0xFF, 0x80): break
	return out
class Atlas:
	def __init__(self, memory): self.memory = memory; self.pages = {}; self.items = []; self.keys = {}; self.x = self.y = self.row = 0; self.width = 256
	def add(self, tpage, clut, u, v, w, h):
		key = (tpage, clut, u, v, w, h)
		if key in self.keys: return self.keys[key]
		if self.x + w > self.width: self.x = 0; self.y += self.row; self.row = 0
		self.items.append({"id": len(self.items), "uv": [self.x, self.y, w, h], "tpage": H(tpage)[-4:], "clut": H(clut)[-4:], "source_uv": [u, v, w, h]}); self.keys[key] = len(self.items) - 1; self.x += w; self.row = max(self.row, h)
		return self.keys[key]
	def save(self, path):
		height = self.y + self.row; height += -height % 4; pixels = bytearray(self.width * height * 4)
		for item in self.items:
			tpage, clut = int(item["tpage"], 16), int(item["clut"], 16)
			if (tpage, clut) not in self.pages: self.pages[(tpage, clut)] = ui.decode_page(self.memory, tpage, clut, True)
			page = self.pages[(tpage, clut)]; x, y, w, h = item["uv"]; u, v = item["source_uv"][:2]
			for row in range(h):
				start = ((v + row) * 256 + u) * 4; pixels[((y + row) * self.width + x) * 4:((y + row) * self.width + x + w) * 4] = page[start:start + w * 4]
		world.write_if_changed(path, world.png(self.width, height, bytes(pixels))); return [self.width, height]

# ------------------------------------------------------------------ scene contract helpers
OPS = {"screen_transition": lambda x: {"op": "fade", "type": x["args"][0]}, "pool_clear": lambda x: {"op": "pool_clear", "mask": x["args"][0], "flags": x["args"][1]}, "sound": lambda x: {"op": "play_sound", "id": x["args"][0]},
	"player_control": lambda x: {"op": "player_control", "control": x["args"][0], "start_record": x["args"][1]}, "xa_prepare": lambda x: {"op": "music_prepare", "id": x["args"][0] & 0xFFFF, "unverified": True, "note": "SLES0x8001B714(0xFF01): XA/music descriptor 0xFF01 (music stop/hold); no XA asset bound"},
	"xa_play": lambda x: {"op": "music_play", "id": x["args"][0] & 0xFFFF, "unverified": True, "note": "SLES0x8001B864(0xFF01) after the result message"}, "overlay_show": lambda x: {"op": "result_banner", "args_raw": x["args"][:3], "unverified": True, "note": "SLES0x8003B918(0x44,0x30,2): screen overlay/banner (style table 0x8006B324)"},
	"overlay_hide": lambda x: {"op": "result_banner_hide"}, "jingle": lambda x: {"op": "jingle", "args_raw": x["args"][:3], "unverified": True, "note": "SLES0x80020984(0xF,0x333,0)"}, "call_43F70": lambda x: {"op": "native_call", "function": "SLES0x80043F70", "args_raw": x["args"][:1], "unverified": True},
	"skip_lock": lambda x: {"op": "skip_lock", "set": x["set"]}, "flag_set": lambda x: {"op": "event_set", "id": x["args"][0]}, "flag_clear": lambda x: {"op": "event_clear", "id": x["args"][0]}, "close_windows": lambda x: {"op": "close_windows"}, "vibration": lambda x: {"op": "vibration", "args_raw": [a & 0xFFFFFFFF for a in x["args"][:2]]},
	"message": lambda x: {"op": "message", "index": x["index"]}, "advance": lambda x: {"op": "advance"}, "xa_fade_out": lambda x: {"op": "xa_fade_out", "speed": x["args"][0]}}
def request(raw):
	x, y, z, facing = struct.unpack_from("<3hH", raw, 0x10); return {"type": struct.unpack("b", raw[:1])[0], "stage": "ST%02X" % raw[4], "area": raw[5], "position_raw": [x, y, z], "facing_raw": facing, "fade_arrival": raw[0x18], "fade_exit": raw[0x19], "bytes": raw.hex()}
def programs(events, timeline, ops=OPS):
	segments = {"%d:%d" % (t["phase"], t["step"]): {"source": t["callback"], "program": [], "emulated_events": []} for t in timeline}; init = []; finish = []; last = {}
	for x in events:
		op = None
		if x["kind"] in ops: op = dict(ops[x["kind"]](x), source=x.get("caller", "emulated state change"))
		elif x["kind"] == "request_block":
			r = request(bytes.fromhex(x["bytes"]))
			op = {"op": "area_change", "stage": r["stage"], "area": r["area"], "position_raw": r["position_raw"], "facing_raw": r["facing_raw"], "fade_arrival": r["fade_arrival"], "fade_exit": r["fade_exit"], "request_type": -1, "source": "request block 0x80078D08 (type -1)"} if r["type"] == -1 else {"op": "stage_request", **r}
		if op is None: continue
		if op["op"] == "event_set" and op["id"] == 0x12A: op = {"op": "event_set_conditional", "id": 0x12A, "condition": "success: room timers +0xA + +0xC + +0xE < 0xD49; failure: room+5 >= 0x12", "source": op["source"], "note": "gameplay must evaluate; native_scene.gd ignores this op"}
		if x["state"] == 0: init.append(op); continue
		if x["state"] == 2: finish.append(op); continue
		key = "%d:%d" % (x.get("phase", 0), x["step"]); segment = segments[key]; gap = x["frame"] - last.get(key, 0)
		if gap > 1 or (gap == 1 and op["op"] not in ("message", "fade")): segment["program"].append({"op": "delay", "ticks": gap, "source": "emulated substate counter"})
		last[key] = x["frame"]; segment["program"].append(op); segment["emulated_events"].append({"kind": x["kind"], "tick": x["frame"]})
	for index, t in enumerate(timeline):
		segment = segments["%d:%d" % (t["phase"], t["step"])]
		if t["duration"] < 0 and (not segment["program"] or segment["program"][-1]["op"] != "advance"): segment["program"].append({"op": "advance", "source": "GAME0x800C0EA8(1) (callback-advanced step, duration -1)"})
		program = segment["program"]
		if index + 1 < len(timeline) and len(program) >= 2 and program[-1]["op"] == "advance" and program[-2]["op"] == "fade": program[-2]["wait"] = False; program[-2]["wait_source"] = "callback advances in the same tick it starts the fade (native does not wait)"
	return segments, init, finish
def actor_entry(rec, area, manifest, runtime):
	b = bytes.fromhex(rec["bytes_hex"]); model = manifest["models"][0]; exp = model["export"]; x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	if model["flags"] >> 8 != rec["class"]: raise ValueError("ST1E_04800 model 0 is not class %#x" % rec["class"])
	return {"source_ram": rec["source_ram"], "slot": rec["slot"], "class_note": "Data (class 0x63, NPC pool 0x20; scene controller ST1ET 0x800E9958 = class cell 0x800EE944 variant 1)",
		"entry": {"stage": STAGE, "area": area, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": 0, "model_file": runtime},
		"model": {"file": runtime, "source_archive": "DAT/ST1E.BIN section 0x4800 (ST1E_04800)", "source_model_index": 0, "source_flags": model["flags"], "class_from_flags": model["flags"] >> 8, **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp}, "model_file": runtime, "model_index": 0}}
def controllers(e, tracks, records):
	out = {}
	for slot, rows in tracks.items():
		if slot == "player": continue
		events = [x for x in e.events if x.get("actor_slot") == slot]; controls = [x for x in events if x["kind"] == "actor_control"]; startup = controls[0] if controls else None
		items = [dict({"op": "control", "control": x["args"][1], "start_record": x["args"][2], "native": "SLES0x8003F4BC via %s" % x["caller"]}, step=x["step"], tick=x["frame"]) for x in controls if x is not startup]
		items += [dict({"op": "actor_face", "channel": "eyes" if x["kind"] == "face_eyes" else "mouth", "sequence": x["args"][1], "native": x["caller"]}, step=x["step"], tick=x["frame"]) for x in events if x["kind"] in ("face_eyes", "face_mouth")]
		profile = {"source": "ST1ET 0x800E9958 (Data class 0x63 variant 1), emulated once per native tick after the scene update; render helpers stubbed", "record": records[slot], "events": items, "track": {"op": "actor_track", "interpolation": "linear between keyframes in native ticks", "keyframes": intro_scene.compress(rows)}}
		if startup: profile["startup_control"] = startup["args"][1]; profile["startup_start_record"] = startup["args"][2]
		out[str(slot)] = profile
	return out
def commands(address):
	out = []; a = address
	while True:
		w = u32(a); op = w >> 24; size = 16 if 0x10 <= op <= 0x1A else 8 if op in (0x40, 0x41) else 20 if op == 0x42 else 4; words = list(struct.unpack("<%dI" % (size // 4), rd(a, size))); item = {"source_ram": H(a), "opcode": op, "words": words}
		if op in (0x40, 0x41): item["actor_record"] = {"source_ram": H(words[1]), "bytes": rd(words[1], 20).hex()}
		if op == 0x42: item["player_transform"] = {"position_raw": [intro_scene.s32(x) / 65536 for x in words[1:4]], "yaw_raw": words[4] & 0xFFFF, "native": "GAME0x800C1A58: player(0x8008C0A0)+0x10/+0x14/+0x18 = words[1..3], +0x2A = halfword +0x10"}
		out.append(item); a += size
		if op == 0xFF: break
	return out
def timeline(address):
	out = []; a = address
	while True:
		p, s, d, cb = struct.unpack("<BBhI", rd(a, 8))
		if p == 255: break
		out.append({"phase": p, "step": s, "duration": d, "callback": "0x%x" % cb, "source_ram": "0x%x" % a}); a += 8
	return out

def build_result(success, manifest, runtime, out):
	camera_address = u32(0x800F0D2C + (0 if success else 4)); timeline_address = u32(0x800F0D64 + (0 if success else 4))
	if (camera_address, timeline_address) != ((0x800F0C5C, 0x800F0D34) if success else (0x800F0CC4, 0x800F0D4C)): raise ValueError("scene 0xD camera/timeline tables differ")
	e, tracks, requests, ticks = emulate_result(success); cmds = commands(camera_address); tl = timeline(timeline_address)
	spawned = [c["actor_record"]["source_ram"] for c in cmds if c["opcode"] == 0x40]; recs = [actor_entry(record(int(a, 16)), 2, manifest, runtime) for a in spawned]
	segments, init, finish = programs(e.events, tl); stage_request = request(requests[-1]); player = next(c["player_transform"] for c in cmds if c["opcode"] == 0x42)
	name = "success" if success else "failure"; base = "scene_0d_%s" % name
	scene = {"stage": STAGE, "area": 2, "scene_id": 0xD, "branch": name, "native_tick_hz": 25, "callback_contract_file": base + "_callbacks.json", "commands": cmds, "timeline": tl, "actors": recs,
		"player": {"camera_opcode_0x42_used": True, "transform_raw": player, "track": intro_scene.compress(tracks["player"])}, "face_tables": {},
		"emulation": {"script": "tools/fire_mission.py", "native_ticks": ticks, "events": [{k: v for k, v in x.items() if k not in ("sub6",)} for x in e.events if x["kind"] not in ("render", "actor_control")]},
		"source": {"overlay": "DAT/ST1ET.BIN", "handler": "0x800ED7B8 (GAME table 0x800DC490[0xD])", "phase_table": "0x800F0D6C {0x800ED800 init, 0x800ED9DC update, 0x800EDA6C finish}", "camera_table": "0x800F0D2C", "timeline_table": "0x800F0D64", "command_pointer": H(camera_address), "timeline_pointer": H(timeline_address),
			"branch_select": "0x800ED88C: flag 0x129 set -> ctx+7=0 (success) else ctx+7=1 (failure)", "callback_tables": {"success_step1": "0x800E71A4", "failure_step0": "0x800E71BC", "failure_step1": "0x800E71DC"}}}
	if not success: scene = {"branches": {str(area): dict(scene, area=area, area_note="failure starts in the room where the timer expired or HP reached 0; step 0 moves to area 2") for area in (0, 1, 2)}}
	hp = K(0x800EDB74, 0x72) == 0x72 and K(0x800EDB84, 0x70) == 0x70
	contract = {"schema": 1, "stage": STAGE, "scene_id": 0xD, "branch": name, "source": "ST1ET scene 0xD handler 0x800ED7B8; timeline callbacks %s" % ", ".join(t["callback"] for t in tl),
		"tick_basis": "tick = native ctx+0x28 of the step; program delays are the emulated substate counters (fades, messages and XA reported idle immediately in emulation; the native callbacks wait for message/fade/XA idle before the next substate)",
		"initialization": {"player_position_raw": [round(v) for v in player["position_raw"]], "player_yaw_raw": player["yaw_raw"], "player_note": "camera opcode 0x42 at step 1 tick 0 sets the player transform; until then the player keeps the gameplay transform behind fade 0x11", "spawn_records": [], "init_ops": init,
			"phase0": {"source": "0x800ED800", "ops": ["GAME0x800C1148", "event_set 0x703 (0x800ED86C)", "SLES0x80048944(1)", "ctx byte0 |= 0x20 (skip locked)", "flag 0x129 -> success; else failure", "wait GAME0x800CDD8C()==0, then GAME0x800CDE5C(0,0,1)", "success waits 0x60 ticks (0x800ED934..0x800ED940), failure starts at once", "clear player +0xF0/+0xF4/+0x1A0/+0x1A1/+0x38..+0x44", "GAME0x800C0C5C(camera, timeline)"],
				"fast_flag": {"flag": 0x12A, "success_condition": "timers +0xA + +0xC + +0xE < 0x%X" % K(0x800ED8B4, 0xD49), "failure_condition": "room+5 (fires extinguished) >= 0x%X" % K(0x800ED8D4, 0x12), "source": "0x800ED8A0..0x800ED8E4"}}},
		"segments": segments, "actor_controllers": controllers(e, tracks, {r["slot"]: r["source_ram"] for r in recs}),
		"finish": {"source": "ST1ET 0x800EDA6C", "fade_exit": 0x12, "fade_exit_source": "issued by the last timeline step", "ops": finish + [{"op": "hp_refill", "native": "player+0x70 = player+0x72", "source": "0x800EDB74..0x800EDB84", "verified": hp}],
			"skip_path": {"source": "0x800ED9DC..0x800EDA50", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x80048944(1); SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800EDB44..0x800EDB80 request block 0x80078D08", "request_bytes": stage_request["bytes"]}},
		"new_ops": NEW_OPS, "integration_notes": ["camera opcode 0x42 (66) is used at step 1 tick 0: native_scene.gd _commands() treats it as unknown and fails the scene; add 'player transform set' (position words[1..3] 16.16, yaw = low half of words[4])", "fade ops in steps that the native code does not wait for (fade 1 / fade 2 reveals) block in native_scene.gd; harmless but adds the fade time", "player controls %s must exist in the ST1E player clip set" % sorted({op["control"] for s in segments.values() for op in s["program"] if op["op"] == "player_control"}), "unknown ops (music_prepare, music_play, result_banner, jingle, native_call, close_windows, event_clear) are ignored by native_scene.gd _action()"]}
	world.write_if_changed(out / (base + ".json"), json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_if_changed(out / (base + "_callbacks.json"), json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"file": base + ".json", "callbacks": base + "_callbacks.json", "ticks": ticks, "messages": [x["index"] for x in e.events if x["kind"] == "message"], "transition": stage_request, "flags_set": [x["args"][0] for x in e.events if x["kind"] == "flag_set"]}

def build_door(doors, out):
	runs = []; tl = timeline(0x800F0BB8)
	if u32(0x800F0BB4) != 0xFFFFFFFF or [u32(0x800F0C20 + i * 4) for i in range(3)] != [0x800ED228, 0x800ED510, 0x800ED57C]: raise ValueError("scene 0 tables differ")
	for route in doors["area_transitions"]:
		e, tracks, door_rows, camera, ticks = emulate_door(route); segments, init, finish = programs(e.events, tl)
		for key in segments: segments[key]["program"] = [op for op in segments[key]["program"] if op["op"] != "advance"]
		moves = {}
		for x in e.events:
			if x["kind"] == "player_move": moves.setdefault((x["step"], x["frame"]), [0, 0, 0]); moves[(x["step"], x["frame"])] = [m + v for m, v in zip(moves[(x["step"], x["frame"])], x["args"][1:4])]
		for (step, tick), velocity in sorted(moves.items()):
			motion = segments["0:%d" % step].setdefault("motion", [])
			if motion and motion[-1]["velocity_raw"] == velocity and motion[-1]["through_tick"] == tick - 1: motion[-1]["through_tick"] = tick
			else: motion.append({"actor": "player", "from_tick": tick, "through_tick": tick, "velocity_raw": velocity, "source": "GAME0x800CD084(player,dx,dy,dz) from 0x800ED6E4"})
		changes = []; last = None
		for row in door_rows:
			key = (row["byte8"], row["byte9"], row["half4A"], row["half4E"])
			if key != last: changes.append(row); last = key
		runs.append({"source_area": route["source_area"], "record_index": route["record_index"], "lock_event": route["lock_event"], "camera_setup": camera, "segments": segments, "door_actor_fields": changes, "door_actor_fields_note": "sampled after each scene update; tick = step frame - 1 (the callback tick that wrote the field)", "player_track": intro_scene.compress(tracks["player"]), "finish_ops": [op for op in finish if op["op"] != "stage_request"], "transition": {"destination_stage": route["destination_stage"], "destination_area": route["destination_area"], "destination_transform_raw": route["destination_transform_raw"], "note": "request block filled by GAME door logic before the scene (simulated from the door record)"}, "init_ops": init, "native_ticks": ticks})
	contract = {"schema": 1, "stage": STAGE, "scene_id": 0, "source": "ST1ET door scene 0x800ED1EC (setup 0x800ED228, run 0x800ED510, finish 0x800ED57C); timeline 0x800F0BB8; camera stream word 0x800F0BB4 = -1 (no command stream)",
		"timeline": tl, "camera_offsets": {"table_ram": "0x800F0BE0", "stride": 8, "index": "door record +2 (door_mode)", "rows_raw": [list(struct.unpack("<3h", rd(0x800F0BE0 + i * 8, 6))) for i in range(8)], "formula": "focus = ((doorX+playerX)/2, floorY-0xA0, (doorZ+playerZ)/2); orbit = (playerYaw+row[1], row[0], row[2]) (camera ctx 0x80096D50 +8/+C/+10, +58/+5C/+60)"},
		"player_placement": {"table_ram": "0x800F0C2C", "rows_raw": [list(struct.unpack("<2b", rd(0x800F0C2C + q, 2))) for q in range(4)], "formula": "q = door yaw >> 10; (a,b) = table[q], table[q+1]; x += 124*b - 36*a; z += -36*b - 124*a", "source": "0x800ED330..0x800ED39C"},
		"door_actor": {"pool": "global (SLES0x8003E820)", "class": 1, "variant_byte6": "request+3 (door slot)", "state_writes": {"0x800ED65C": "+9 = 1 at step 1 tick 0", "0x800ED680": "+9 = 3, +0x4A = +0xBC/17, +0x4E = -2 at step 2 tick 0", "0x800ED5E8": "+8 = 2 in finish"}},
		"runs": runs, "finish": {"event_clear": 0x700, "waits": "request byte 0x80078D08 == 2 -> 3, then == 0 (area load done); values set by GAME (simulated)", "unverified": "which GAME routine sets the request byte to 2"},
		"runtime_note": "gameplay.gd already performs door use natively (begin_interaction('door_open'), native_door hinge profiles); this contract documents the original ST1E door scene timing for parity checks"}
	world.write_if_changed(out / "scene_00_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	world.write_if_changed(out / "scene_00.json", json.dumps({"stage": STAGE, "area": 0, "scene_id": 0, "native_tick_hz": 25, "callback_contract_file": "scene_00_callbacks.json", "commands": [], "timeline": tl, "actors": [], "contract_kind": "door_transition_reference"}, indent=1) + "\n", encoding="utf-8")
	return {"runs": len(runs), "controls": sorted({op["control"] for run in runs for s in run["segments"].values() for op in s["program"] if op["op"] == "player_control"})}

NEW_OPS = {"music_prepare / music_play": {"semantics": "SLES0x8001B714 / 0x8001B864 with id 0xFF01 (music hold/resume around the result jingle); unverified"}, "result_banner / result_banner_hide": {"semantics": "SLES0x8003B918(0x44,0x30,2) / 0x8003B9C4 screen overlay (style table 0x8006B324); unverified"},
	"jingle": {"semantics": "SLES0x80020984(0xF,0x333,0); unverified (likely the mission-result jingle)"}, "native_call": {"semantics": "SLES0x80043F70(-5000) before the failure sprinklers; unverified"}, "event_clear": {"semantics": "GAME0x800C0584(id)"}, "hp_refill": {"semantics": "player +0x70 = +0x72"},
	"stage_request": {"semantics": "request block 0x80078D08 type 2 stage change (finish transition)"}, "camera opcode 0x42": {"semantics": "GAME0x800C1A58 player transform set from the command stream"}}

# ------------------------------------------------------------------ fire mission data
def area_data(area):
	e, ticks = emulate_area(area); clear, _ = emulate_area(area, clear_at=40 if area != 2 else 60, trigger_at=30 if area == 1 else None)
	trigger = emulate_area(1, trigger_at=30, ticks=200)[0] if area == 1 else None; ev = e.events
	table, count = SPAWNS[area]; spawns = [x for x in ev if x["kind"] == "spawn_table"]
	if (spawns[0]["args"][0] & 0xFFFFFFFF, spawns[0]["args"][1]) != (table, count): raise ValueError(f"area {area} fire spawn differs: {spawns[0]}")
	fires = []
	for i in range(count):
		r = record(table + i * 20)
		if r["class"] != 0x36: raise ValueError("non-fire record %s" % r["source_ram"])
		fires.append({"index": r["index"], "position_raw": r["position_raw"], "size": r["size"], "strength_max": u16(SIZES + r["size"] * 8 + 4), "variant": r["variant"], "behaviour": r["behaviour"], "contact_damage": r["contact_damage"], "child_submode": 1 if r["behaviour"] & 1 else 3, "triggers_explosion": bool(r["behaviour"] & 2), "throws_embers": bool(r["behaviour"] & 4), "source_ram": r["source_ram"], "bytes_hex": r["bytes_hex"]})
	limit = {0: K(0x800E75E4, 0x708), 1: 0xE10, 2: K(0x800E79B0, 0x1518)}[area]; field = {0: 0xA, 1: 0xC, 2: 0xE}[area]
	radio = [{"tick": x["room"]["timers"][area], "message": x["args"][0]} for x in ev if x["kind"] == "radio_message"]
	warnings = [r for r in radio if r["message"] != 0x2A]; hints = [r for r in radio if r["message"] == 0x2A]; timeout = [x for x in ev if x["kind"] == "scene_start"]
	entry = {"fires": fires, "fire_count_initial": next(x["room"]["fires"] for x in ev if x["kind"] == "conversation" or x["state"] == 0 and x["kind"] in ("spawn_table",)) if False else None,
		"entry_flags": [x["args"][0] for x in ev if x["kind"] == "flag_set" and x["room"]["area_state"] == 0], "unlock_flag": next((x["args"][0] for x in clear.events if x["kind"] == "flag_clear"), None),
		"timer_field": "0x8009C9%02X" % field, "timer_limit": limit, "timer_runs": "+1 per gameplay tick while below the limit and player HP (0x8008C110) != 0 (0x800E7B88); scene 0xD starts when it returns 1 (limit reached or HP 0) and no conversation (0x80078CC8) is active",
		"timeout_tick": timeout[0]["room"]["timers"][area] if timeout else None, "timeout_scene": timeout[0]["args"][0] if timeout else None, "warnings": warnings,
		"hint": {"idle_ticks": 0x384, "message": 0x2A, "counter": "0x8009C910", "resets_on": "player +0x13C bit 0x40 (spraying, unverified) or flag 0x681 (blocking message)", "emulated_ticks": [h["tick"] for h in hints], "source": "0x800E7A8C"}}
	entry["fire_count_initial"] = next((x["room"]["fires"] for x in ev if x["kind"] in ("conversation", "radio_message", "scene_start", "spawn_table") and x["room"]["fires"]), None) or e.u8(ROOM + 4) or count
	completion = [x for x in clear.events if x["kind"] in ("flag_set", "flag_clear", "scene_start") and x["room"]["fires"] == 0]
	entry["on_clear"] = [{"kind": x["kind"], "value": x["args"][0], "caller": x["caller"]} for x in completion]
	if area == 0: entry["start_sequence"] = [{"op": "conversation", "message": x["index"], "window": x["args"][2], "caller": x["caller"]} if x["kind"] == "conversation" else {"op": x["kind"], "args_raw": x["args"][:3], "caller": x["caller"]} for x in ev if x["kind"] in ("conversation", "overlay_show", "overlay_hide")]
	if area == 1:
		extra = record(EXTRA_FIRE); spawned = [x for x in trigger.events if x["kind"] == "spawn_table" and x["args"][0] & 0xFFFFFFFF == EXTRA_FIRE]
		entry["triggered_fires"] = [{"index": extra["index"], "position_raw": extra["position_raw"], "yaw_raw": extra["yaw_raw"], "size": extra["size"], "strength_max": K(0x800EAA50, 0x1000), "variant": extra["variant"], "contact_damage": extra["contact_damage"], "behaviour": extra["behaviour"], "source_ram": extra["source_ram"], "bytes_hex": extra["bytes_hex"], "trigger": "room+6 (0x8009C906) set by extinguishing a fire with behaviour bit1 (0x800EA030); area 1 state 1 spawns it and adds 1 to the room fire count (0x800E7774)", "emulated": bool(spawned), "fire_count_after": spawned[0]["room"]["fires"] + 1 if spawned else None}]
	if area == 2:
		entry["npcs"] = [{"record": record(0x800EF3C8), "role": "Data (class 0x63 v0, handler 0x800E7BD4)"}, {"record": record(0x800EF3F0), "role": "script actor class 0x1D playing message 0x03 (0x800EC130)"}]
		entry["intro"] = {"flag": 0x681, "ember_block": "room+8 = 1 until flag 0x681 clears (0x800E797C/0x800E79A8); the timer is not ticked in state 1"}
	return entry

def fire_block(atlas, rows, boxes):
	sizes = []
	for size in range(4):
		tpage, clut, maximum = struct.unpack("<3H", rd(SIZES + size * 8, 6)); frames = fire_frames(size)
		for f in frames: f["atlas_id"] = atlas.add(tpage, clut, f["u"], f["v"], f["w"] + 1, f["h"] + 1)
		sizes.append({"size": size, "tpage": H(tpage)[-4:], "clut": H(clut)[-4:], "strength_max": maximum, "blend": "additive" if (tpage >> 5) & 3 == 1 else "normal", "semi_transparency_mode": (tpage >> 5) & 3, "frames": frames, "sequence": [[f["atlas_id"], f["ticks"]] for f in frames], "source_ram": H(SIZES + size * 8), "frames_ram": H(FRAMES + size * 0x80)})
	mismatches = [r for r in rows if r["result"] != -1 and r["strength_after"] != formula(int(r["hit_word"], 16), r["player_distance_raw"], 0x700, sizes[r["size"]]["strength_max"]) or r["result"] == -1 and r["strength_after"] != 0]
	return {"class": 0x36, "pool": "enemy pool 0xCC stride (list byte 0x60)", "handlers": {"variant0": "0x800E9DE4", "variant0_states": {"init": "0x800E9E68", "burning": "0x800E9FD8", "dying": "0x800EA3CC", "table": "0x800EF468"}, "variant1": "0x800EA994", "variant1_states": {"init": "0x800EAA18", "burning": "0x800EAC2C", "dying": "0x800EB014", "table": "0x800EF694"}},
		"regrow_per_tick": K(0x800EA074, 0x10), "regrow_rule": "when not hit and strength < max: strength = min(strength + 0x10, max) (0x800EA060..0x800EA090)", "out_threshold": K(0x800EA6B0, 0x201) - 1, "out_rule": "after damage, strength <= 0x200 -> strength = 0 and the fire is out (0x800EA6B0)",
		"hit_mask": (K(0x800EA608, 4) << 16) | K(0x800EA60C, 0x2000), "damage_scale": 1 << SH(0x800EA630, 5), "damage_rule": "damage = (hit_word & 0xFFF) << 5 (0x800EA624/0x800EA630); hit word = actor+0x74, cleared each tick by the hitbox registration (0x800EA714)",
		"close_bonus": {"requires_hit_bit": K(0x800EA634, 0x2000), "distance_function": "SLES0x80041BEC(player 0x8008C0A0, fire)", "distance_clamp": [K(0x800EA654, 0x80), K(0x800EA65C, 0x100)], "scale_numerator": 13, "scale_shift_left": SH(0x800EA684, 6), "scale_shift_right": SH(0x800EA688, 7), "offset": K(0x800EA68C, 0x3C0), "final_shift": SH(0x800EA690, 3),
			"formula": "d = clamp(distance, 0x80, 0x100); bonus = (((((0x100 - d) * 13) << 6) >> 7) + 0x3C0) >> 3  (0x78 at d>=0x100 .. 0xE0 at d<=0x80); added to damage", "source": "0x800EA634..0x800EA694"},
		"verification": {"emulated_samples": len(rows), "formula_mismatches": mismatches, "samples": rows},
		"contact_damage": 8, "contact_damage_source": "spawn record +0xD (actor +0xD), hitbox a3 = 0x8A0000 | actor+0xD (0x800EA778..0x800EA790); flag meaning unverified", "contact_damage_unverified": True,
		"hitbox_raw": {"function": "SLES0x80042704", "radius": "max(0x40, strength >> shift); shift = 5 for size 0, 6 otherwise (0x800EA70C..0x800EA738)", "center": "(x, y - radius, z) integer position", "a2": "(actor byte2 << 24) | 0x400000 | (radius >> 2)", "a3": "0x8A0000 | contact_damage", "emulated": boxes},
		"heat": {"rule": "if distance(player, fire) < strength >> 2: room+0 += (strength >> 2) - distance (0x800EA938)", "consumer": "effect class 0x12 v0 (0x800EC220): heat += rand & 0x1FF when non-zero; full-screen additive rectangle (0x800ECDF8, GP0 0x62 with draw mode 0xE1000220) red = (heat << 7) >> 12, green = (heat * 48) >> 12; heat cleared every tick"},
		"sounds": {"loop": K(0x800EA378, 0x152), "loop_period_ticks": K(0x800EA370, 0x21) + 1, "loop_first_delay": "(actor byte2 & 0xF) * 2 (0x800E9F14..0x800E9F28)", "extinguished": K(0x800EA448, 0x153), "explosion": K(0x800EABFC, 0x8B), "explosion_fire_loop": K(0x800EAFD4, 0x158), "explosion_fire_loop_period_ticks": K(0x800EAFCC, 0x1C) + 1, "data_ignite": K(0x800E8328, 0x154), "api": "SLES0x800203F4(id, position)"},
		"sprite": {"atlas": "fire_atlas.png", "by_size": sizes, "blend": "additive", "packet": "POLY_FT4-shaped world sprite at *0x1F800050 (0x800EA7A4): cmd 0x2E808080 (semi-transparent), xy0 = (y - (strength >> 5)) << 16 | x, xy1 = z, word 0x18 = (strength >> 4) - (strength >> 6), uv from frame table, tpage/clut from size table",
			"size_raw": "(strength >> 4) - (strength >> 6)", "anchor_raise_raw": "strength >> 5", "size_semantics_unverified": True, "size_note": "the SLES consumer of the 0x1F800050 sprite packets was not traced; GAME buster projectiles use the same layout with word 0x18 = width_raw | rotation << 16", "uv_note": "frame w/h (and effect u1/v1) are inclusive end offsets: the drawn quad spans u..u+w, so the atlas cells are (w+1)x(h+1)", "animation": "each frame shows for frame.ticks ticks; after a frame with last=true the sequence restarts at 0 (0x800EA8B4..0x800EA92C)"},
		"init": {"strength": "size table max", "ember_timer": "0x90 + (rand & 0x3F) (0x800E9F08..0x800E9F10)", "child": {"class": 0x3E, "handler": "0x800EB314", "submode": "1 if behaviour bit0 (child +0xE = record index & 1) else 3", "unverified": "visual role of class 0x3E"}},
		"splash": {"rule": "hit with bit 0x2000 spawns class 0x3E submode 0 at the fire, killed after 8 ticks (0x800EA094..0x800EA15C)", "unverified": True},
		"dying": {"rule": "kill children, sound 0x153; on odd ticks spawn effect 0x12 v1 (+6=2 steam) at (x+0x20-(rand&0x3F), y-((rand>>6)&7), z+0x20-((rand>>9)&0x3F)); after 3 puffs spawn global class 0x14 (smoke/scorch, unverified); free after 0x%X ticks" % K(0x800EA5C4, 0x1D0), "counts": "room+4 -= 1, room+5 += 1, behaviour bit1 sets room+6 (0x800EA01C..0x800EA054)"},
		"explosion": {"variant": 1, "record": H(EXTRA_FIRE), "init": "0x800EAA18: strength = max = 0x1000; spawn effect 0x12 v3 (white additive flash 0xFFFFFF fading by 0x20 per tick, 0x800EC600/0x800EC648) and 16 effect 0x12 v4 debris (+6 cycling 0..2); GAME0x800C010C(map cell word at fire x/z, 1) (map change, unverified); SLES0x80016B1C(1,0x6000,0x800) camera shake; sound 0x8B",
			"burning": "0x800EAC2C: same damage/regrow/out rules (0x800EA600) without room+6; every 4 ticks spawn effect 0x12 v2 flame (+0xE = strength >> 7); first 9 ticks also spawn v4 debris; hitbox offset 0x20 along yaw, radius 0x40 (a2 low 0x10), a3 0x8A0000|0x0A; no sprite of its own", "contact_damage": 0x0A,
			"trigger": "Living Room fire index 12 (record 0x800EF33C, behaviour 2) extinguished -> room+6 -> area 1 state 1 spawns 0x800EF350"},
		"embers": {"room": 2, "source_fires": "behaviour bit2 (Kitchen records)", "strength_gate": K(0x800EA17C, 0xC00), "blocked_by": "room+8 bit0 (Data intro or Data burning)", "interval": "0x90 + (rand & 0x7F) ticks (0x800EA1DC..0x800EA1E8)", "target_raw": list(struct.unpack("<3h", rd(0x800E719C, 6))), "target_source": "0x800E719C (Data spawn point)",
			"target_jitter": {"x": "- ((rand & 0xFF) - 0x80)", "z": "- (((rand >> 8) & 0x7F) - 0x40)"}, "launch": {"speed_raw": K(0x800EA28C, 0x300), "y_offset": "-0x40 - (rand & 0xF)", "arc": "SLES0x80042298(start, target, 0x100, 0xC, -1) -> ember +0x16 (initial vertical speed, unverified)"},
			"flight": {"horizontal_speed_raw": K(0x800EC99C, 0x100), "gravity_per_tick": K(0x800EC9B0, 0xC), "lifetime_ticks": K(0x800ECC3C, 0x80), "water_mask": (K(0x800ECB94, 5) << 16) | K(0x800ECB9C, 0x2000), "floor": "GAME0x800B18A4/0x800B13FC; landing spawns global class 0 variant 3 (+0xC = 0x30 + rand&0xF, unverified scorch)"},
			"hitbox": {"a3": "0x900004 (damage 4; includes bit 0x100000)", "source": "0x800ED154", "radius": "0x800F0B8C[+6] >> 3"}, "effect": "class 0x12 variant 5",
			"data_burning": {"ignite_bit": (K(0x800E7DF4, 0x10) << 16), "ignite_bit_source": "Data hit word ext+0 tested at 0x800E7DF4; the ember (0x900004) and explosion flame (0x98xxxx) hitboxes carry bit 0x100000, fire hitboxes (0x8Axxxx) do not (inferred)", "on_ignite": "state 0x800E8258: room+8 |= 1, ext+0xC |= 4, effect 0x12 v6 flame child, strength +0x70 = max HP +0x72, room+4 += 1, sound 0x154",
				"extinguish": "0x800E9464: same 0x42000 mask, damage and close bonus; strength <= 0x200 -> out, flame killed, room+4 -= 1 (0x800E7E10..0x800E7E54)", "no_damage_while": "ext+0xC bit 0x4 set (0x800E951C), unverified window", "unverified": True}},
		"effects": {str(v): dict({k: (H(x) if isinstance(x, int) and k in ("anim", "page", "size", "rise") else x) for k, x in spec.items()}, subtypes=[effect_sub(atlas, spec, s) for s in range(spec["count"])]) for v, spec in EFFECTS.items()}}
def effect_sub(atlas, spec, sub):
	tpage, clut, semi = struct.unpack("<3H", rd(spec["page"] + sub * 8, 6)); frames = effect_frames(spec, sub); item = {"subtype": sub, "tpage": H(tpage)[-4:], "clut": H(clut)[-4:], "semi_transparent": bool(semi), "blend": ("additive" if (tpage >> 5) & 3 == 1 else "subtractive" if (tpage >> 5) & 3 == 2 else "average" if (tpage >> 5) & 3 == 0 else "quarter") if semi else "normal", "frames": frames}
	if "size" in spec: item["initial_size_raw"] = u16(spec["size"] + sub * 2)
	if "rise" in spec: item["rise_per_tick_raw"] = u16(spec["rise"] + sub * 2)
	for f in frames:
		u, v, w, h = min(f["u0"], f["u1"]), min(f["v0"], f["v1"]), abs(f["u1"] - f["u0"]) + 1, abs(f["v1"] - f["v0"]) + 1
		if w and h and (tpage >> 7) & 3 == 0: f["atlas_id"] = atlas.add(tpage, clut, u, v, w, h); f["mirror_u"] = f["u1"] < f["u0"]; f["mirror_v"] = f["v1"] < f["v0"]
		else: f["atlas_id"] = None
	return item

def kitchen_data(manifest, runtime):
	actor = actor_entry(record(0x800EF3C8), 2, manifest, runtime); actor["class_note"] = "Data (class 0x63 variant 0, NPC pool 0x20; handler 0x800E7BD4 = class cell 0x800EE944 variant 0)"
	if [u32(0x800EE944 + i * 4) for i in range(2)] != [0x800E7BD4, 0x800E9958] or [u32(0x800EF404 + i * 4) for i in range(3)] != [0x800E7CF0, 0x800E7DB8, 0x800E9354]: raise ValueError("Data class tables differ")
	states = [H(u32(0x800EF410 + i * 4)) for i in range(9)]; route_modes = [H(u32(0x800EF434 + i * 4)) for i in range(3)]
	routes = [[list(struct.unpack("<3hH", rd(0x800E7020 + r * 64 + i * 8, 8))) for i in range(8)] for r in range(4)]
	return {"actor": actor, "source": {"handler": "0x800E7BD4", "init": "0x800E7CF0", "main": "0x800E7DB8", "states_table": "0x800EF410", "states": states, "route_modes_table": "0x800EF434", "route_modes": route_modes, "mover": "0x800E9718", "bounds_clamp": "0x800E96A4", "wall_reflect": "GAME0x800B32B8", "hitbox": "0x800E9574", "extinguish": "0x800E9464", "scream": "0x800E98B8", "floor": "0x800E9374"},
		"ext": "actor +0x14C (pointer 0x800F0E6C): +0 hit word, +8 flame effect, +0xC flags (bit0 done, bit1 burning, bit2 ignite grace), +0xE counter, +0x10 route, +0x11 route point, +0x12 sound timer",
		"center_raw": list(struct.unpack("<3h", rd(0x800E7018, 6))), "routes_raw": routes, "route_note": "point = (x, y, z, flags); (flags >> 12) & 3 selects walk/jump/climb; flags bit15 ends the route and loops to flags & 0xF while counter +0xE > 0",
		"bounds_raw": {"x": [K(0x800E96AC, 0x20), K(0x800E96C8, 0x131) - 1], "z": [K(0x800E96E4, 0x50), K(0x800E96FC, 0x151) - 1], "flags": {"x_low": 0x200, "x_high": 0x100, "z_high": 0x400, "z_low": 0x800}},
		"strength_max": K(0x800E7D30, 0x800), "regrow": K(0x800E7E80, 0x10), "gravity": K(0x800E7D38, 0x28), "spin_speed": K(0x800E8DC4, 0x230), "spin_ticks": K(0x800E8DB8, 0x4B), "circle_ticks": K(0x800E8630, 0x5B), "circle_radius": K(0x800E858C, 0x71) - 1, "circle_yaw_offset": K(0x800E8580, 0x400),
		"panic_speed": K(0x800E813C, -0xC0), "burning_speed": K(0x800E845C, -0x190), "avoid_distance": K(0x800E900C, 0x100), "avoid_jump": K(0x800E9014, -0x190), "run_target": {"yaw": K(0x800E83AC, 0x800), "distance": K(0x800E83B8, 0x700), "source": "SLES0x800425FC(out, 0x800, 0x700) + center"},
		"controls": {"panic": K(0x800E7D20, 1), "ignite": K(0x800E82CC, 2), "burning": K(0x800E8454, 3), "ignite_end": "actor +0x9F bit7 (animation reached its held record)"},
		"sounds": {"panic": [u32(0x800E7138 + i * 4) for i in range(4)], "panic_interval": [K(0x800E8168, 0x78), K(0x800E8160, 0x1F)], "ignite": K(0x800E8328, 0x154), "ignite_timer": K(0x800E8344, 0x28), "scream": [K(0x800E98C0, 0x155), K(0x800E98D0, 0x15E)], "scream_interval": [K(0x800E9910, 0xB4), K(0x800E990C, 0x1F)], "jump": [u32(0x800E7148 + i * 4) for i in range(16)]},
		"hitbox": {"offset_y_raw": K(0x800E95A8, -0x200) >> 4, "radius_raw": (u32(0x800E968C) & 0xFF) * 4, "burning_contact_damage": K(0x800E9638, 0x10), "ignite_bit": K(0x800E7DF4, 0x10) << 16, "source": "0x800E9574: SLES0x80042704 a2 = byte2<<24 | (burning ? 0x400000 : 0x280000) | 8, a3 = 0x800000 | (burning ? 0xA0010 : 0x40000)"},
		"flame": {"effect": 6, "bone": 6, "bone_offset_y_raw": -0x20, "size_shift": 6, "source": "0x800E7FBC SLES0x8003EFF4(actor, 6, -0x20); flame +0xC = strength >> 6 (0x800E8068..0x800E807C)"},
		"ember_init_timer": [K(0x800E9F0C, 0x90), K(0x800E9F08, 0x3F)], "ember_interval": [K(0x800EA1E0, 0x90), K(0x800EA1DC, 0x7F)], "ember_target_jitter": {"x": [K(0x800EA23C, 0xFF), K(0x800EA240, -0x80)], "z": [K(0x800EA258, 0x7F), K(0x800EA268, -0x40)], "rule": "target = data spawn - ((rand & mask) + bias); z uses rand >> 8"},
		"ember_launch": {"distance": K(0x800EA28C, 0x300), "y": [K(0x800EA2E0, -0x40), K(0x800EA2F8, 0xF)], "arc_speed": K(0x800EA32C, 0x100), "arc_gravity": K(0x800EA344, 0xC), "rule": "yaw = ratan2(fire - target); start = fire + SLES0x800425FC(yaw, distance) (x/z), y = fire.y - 0x40 - (rand & 0xF); vertical = SLES0x80042298(start, target, 0x100, 0xC)"}, "ember_hitbox": {"radius_raw": (u16(0x800F0B8C) >> 3) * 4, "word": 0x900004, "source": "0x800ED154"}, "ember_size_raw": u16(0x800F0B8C), "ember_land_shrink_until": K(0x800ECACC, 9),
		"unverified": ["Data state 8 (0x800E9248) is only reachable when +9 is already 8; nothing in ST1ET writes it", "smoke puffs from the flame effect and steam from hits (effect 0x12 v1) are not exported", "state 7 hit bit 0x10000 source"]}

def export(root=None, out_dir=None, levels_dir=None):
	root = Path(root or ROOT); load(root); out = Path(out_dir or root / "assets/levels") / STAGE; levels = Path(levels_dir or root / "assets/levels"); out.mkdir(parents=True, exist_ok=True)
	doors = export_doors(D["disc"] / "DAT", levels, out.parent)
	memory, uploads = vram(); atlas = Atlas(memory); rows, boxes = fire_math(); fire = fire_block(atlas, rows, boxes); atlas_size = atlas.save(out / "fire_atlas.png"); fire["sprite"]["atlas_size"] = atlas_size; fire["atlas_frames"] = atlas.items; fire["vram_uploads"] = uploads
	areas = {str(area): area_data(area) for area in range(3)}
	manifest = json.loads((levels / STAGE / "models/ST1E_04800/manifest.json").read_text(encoding="utf-8")); source = root / manifest["models"][0]["file"]; actors = out / "actors"; actors.mkdir(exist_ok=True)
	for item in source.parent.glob(source.stem + "*"):
		if item.suffix in (".glb", ".png"): shutil.copy2(item, actors / item.name)
	runtime = "assets/levels/%s/actors/%s" % (STAGE, source.name); results = {name: build_result(name == "success", manifest, runtime, out) for name in ("success", "failure")}; door_scene = build_door(doors, out)
	mission = {"stage": STAGE, "native_tick_hz": 25, "areas": areas, "fire": fire, "kitchen_data": kitchen_data(manifest, runtime),
		"messages": {"bank": "DAT/ST1E.BIN 0x6030 (runtime 0x8010C000)", "start": 0x00, "yes": 0x01, "no": 0x02, "yes_no_unverified": True, "objective": 0x32, "objective_window": 9, "kitchen": 0x03, "locked_forward": 0x0A, "locked_back": 0x0B, "hint": 0x2A, "timeout_warnings": {k: v["warnings"] for k, v in areas.items()}, "success": results["success"]["messages"], "failure": results["failure"]["messages"]},
		"failure": {"timeout": "area timer reaches its limit (0x800E7B88 returns 1) -> GAME0x800C0B0C(0xD) without flag 0x129", "hp_zero": "player HP 0x8008C110 == 0 makes 0x800E7B88 return 1 -> scene 0xD (failure); precedence over GAME death handling unverified", "hp_zero_unverified": True, "scene": 0xD, "branch_file": results["failure"]["file"]},
		"completion": {"flag": 0x129, "fast_flag": 0x12A, "fast_limit": K(0x800ED8B4, 0xD49), "fast_rule": "success: timers 0x8009C90A + 0x8009C90C + 0x8009C90E < fast_limit", "failure_fast_count": K(0x800ED8D4, 0x12), "failure_fast_rule": "failure: fires extinguished 0x8009C905 >= failure_fast_count", "scene": 0xD, "source": "0x800E7A54 (Kitchen clear sets 0x129, starts scene 0xD); 0x800ED800 (0x12A)", "next_stage": results["success"]["transition"]},
		"room_block": {"address": H(ROOM), "fields": {"0x00": "heat accumulator", "0x04": "fires left", "0x05": "fires extinguished (mission)", "0x06": "explosion trigger", "0x08": "ember block bit0", "0x0A": "Deck timer", "0x0C": "Living Room timer", "0x0E": "Kitchen timer", "0x10": "idle counter"}, "cleared": "area 0 entry only (0x800E74FC)"},
		"scene_triggers": "scene_triggers.json",
		"source": {"overlay": "DAT/ST1ET.BIN (load 0x800E7000, code size 0x%X)" % struct.unpack_from("<I", D["ovl"], 4)[0], "area_handlers": H(AREA_HANDLERS), "per_frame": H(PER_FRAME), "spawn_tables": {k: H(v[0]) for k, v in SPAWNS.items()}, "extra_fire": H(EXTRA_FIRE), "sizes": H(SIZES), "frames": H(FRAMES), "timer_tick": "0x800E7B88", "idle_hint": "0x800E7A8C", "radio": "0x800E7B20 (class 0x1B script actor, window 4)", "scene_0xD": "0x800ED7B8", "scene_0": "0x800ED1EC", "emulator": "tools/intro_scene.Emu (unicorn) with ST1E stubs in tools/fire_mission.py"},
		"unverified": ["sprite packet size semantics (half vs full extent)", "class 0x3E / effect 0x12 v1..v6 / global class 0x14 roles", "ember arc helper SLES0x80042298 meaning", "Data damage gate ext+0xC bit 4", "weapon module providing hit bit 0x2000", "message 0x00 yes/no branch targets", "SLES0x8003B918 / 0x80020984 / 0x80043F70 effects", "GAME death handling vs HP==0 failure path"]}
	world.write_if_changed(out / "fire_mission.json", json.dumps(mission, indent=1) + "\n", encoding="utf-8")
	triggers = {"stage": STAGE, "triggers": [{"scene_id": 0, "file": "scene_00.json", "when": "door use: GAME door logic (0x800B7DA4..0x800B7E0C) fills request 0x80078D08 and sets flag 0x700; ST1ET per-frame 0x800E7488 starts scene 0 while 0x700 is set", "source_function": "GAME0x800C0B0C(0) at 0x800E7498", "runtime": "gameplay.gd _use_door already performs this natively"},
		{"scene_id": 0xD, "branch": "success", "file": results["success"]["file"], "entry_area": 2, "when": "Kitchen (area 2, state 2) fire count reaches 0: flag 0x129 set then scene 0xD (0x800E7A54..0x800E7A60)", "requires_flag": 0x129, "source_function": "GAME0x800C0B0C(0xD)"},
		{"scene_id": 0xD, "branch": "failure", "file": results["failure"]["file"], "entry_area": [0, 1, 2], "when": "area timer limit or player HP 0 (0x800E7B88 returns 1, no conversation active): Deck 0x800E75F8, Living Room 0x800E7804, Kitchen 0x800E79C4", "requires_flag_clear": 0x129, "source_function": "GAME0x800C0B0C(0xD)"}]}
	world.write_if_changed(out / "scene_triggers.json", json.dumps(triggers, indent=1) + "\n", encoding="utf-8")
	return {"doors": len(doors["area_transitions"]), "atlas": atlas_size, "areas": {k: (len(v["fires"]), v["timer_limit"], v["unlock_flag"], v["warnings"]) for k, v in areas.items()}, "results": {k: (v["ticks"], v["messages"], v["flags_set"]) for k, v in results.items()}, "door_scene": door_scene, "fire_formula_mismatches": len(fire["verification"]["formula_mismatches"])}

def main():
	parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=ROOT); parser.add_argument("--output-dir", type=Path); parser.add_argument("--levels-dir", type=Path); args = parser.parse_args()
	print(json.dumps(export(args.root, args.output_dir, args.levels_dir), indent=1))

if __name__ == "__main__":
	main()
