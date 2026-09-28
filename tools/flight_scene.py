"""Export the ST3A flight scene (scene 6, PAL): scene_06.json, scene_06_callbacks.json, scene_triggers.json and the scene
actor models, from DAT/ST3AT.BIN static tables and a unicorn emulation (tools/fire_mission.Emu) of the unchanged scene handler."""
import json, shutil, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STAGE = "ST3A"; BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0; REQ = 0x80078D08; AREA_BYTE = 0x8009C7F9; LATCH = 0x8009BE08
SCENE_ID = 6; HANDLER = 0x800F2840; STATES = 0x800F69EC; CAMERA = 0x800F5F7C; TIMELINE = 0x800F6894; PER_FRAME = 0x800E7574; STAGE_INIT = 0x800E7328
D = {}
def load(root):
	import fire_mission, intro_scene
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST3AT.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != BASE: raise ValueError("unexpected ST3AT header")
	D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), code_end=BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_mission.D.update(ovl=ovl, game=D["game"]); intro_scene.SLES = D["sles"]; intro_scene.GAME = D["game"]; intro_scene.OVL = ovl
	game = lambda a: struct.unpack_from("<I", D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + SCENE_ID * 4), game(0x800DBEA0 + 0x3A * 4), game(0x800DC66C + 0x3A * 4)) != (HANDLER, STAGE_INIT, PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST3A scene 6")
	if [fire_mission.u32(0x800F4560), fire_mission.u32(0x800F4668), fire_mission.u32(0x800F466C), fire_mission.u32(0x800F45C8)] != [0x24070000 | BACKDROP_TPAGE, 0x3C040000 | BACKDROP_CLUT, 0x34848000, 0x0C018F75]: raise ValueError("scrolling backdrop draw mode differs")
	if fire_mission.u32(HANDLER + 0xC) & 0xFFFF != 4 or [fire_mission.u32(0x800F28C8), fire_mission.u32(0x800F28CC), fire_mission.u32(0x800F28D0), fire_mission.u32(0x800F28D8)] != [0x3C04800F, 0x24845F7C, 0x3C05800F, 0x24A56894]: raise ValueError("scene 6 camera/timeline binding differs")

def emulator():
	import fire_mission
	class Emu(fire_mission.stage_emulator(STAGE_INIT, 0x800F22B8, D["code_end"], ((0x800F4530, "backdrop", 0, False, False), (0x800F4724, "effect_0f", 0, True, False), (0x800F47E4, "actor_21", 0, True, False)))):
		def stub_hook(self, uc, address, size, data):
			name = self.stubs[address][0]; a = [self.r(4), self.r(5)]; ra = self.r(31)
			if name in ("effect_0f", "actor_21"): self.record(name, entry=bytes(uc.mem_read(a[0] & 0x1FFFFFFF, 8)).hex(), entry_ram=H(a[0]), arg=a[1], caller=H(ra - 8)); return self._ret(uc, 0, ra)
			return super().stub_hook(uc, address, size, data)
	return Emu

def H(v): return "0x%08x" % (v & 0xFFFFFFFF)

def emulate():
	import fire_mission, unicorn
	e = emulator()(); e.requests = []; e.w8(AREA_BYTE, 0); e.w32(LATCH, 0)
	e.call(PER_FRAME); started = [x for x in e.events if x["kind"] == "scene_start"]
	if [x["args"][0] for x in started] != [SCENE_ID] or e.u8(LATCH) != 1: raise RuntimeError("ST3A per-frame handler did not start scene 6 once")
	e.events.clear(); e.call(PER_FRAME)
	if e.events: raise RuntimeError("ST3A per-frame handler restarted scene 6 with the latch set")
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(PLAYER, e.u8(PLAYER) | 2); sb = lambda a: e.u8(a) - (e.u8(a) & 0x80) * 2
	tracks, tick = fire_mission.run_scene(e, HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(PLAYER) & 2)), "sound_latch": (0, lambda e: e.u8(CTX + 0x1A)), "backdrop": ((0, 0, 0), lambda e: (e.u8(CTX + 0x16), sb(CTX + 0x14), sb(CTX + 0x15)))})
	return e, tracks, tick

BACKDROP_TPAGE = 0x1B; BACKDROP_CLUT = 0x7C80; BACKDROP_FILE = "scrolling_backdrop.png"
# SLES0x8001392C only starts a fade; these are followed by a 0x80078F01 wait (0x800F4084, 0x800F4284, 0x800F44FC).
WAITED_FADES = {0x800F4060, 0x800F4268, 0x800F44C0}
OPS = {"xa_play": lambda x: {"op": "play_xa", "descriptor": x["args"][0] & 0xFFFF}, "camera_shake": lambda x: {"op": "camera_shake", "magnitude_raw": x["args"][1], "decay_raw": x["args"][2]},
	"face_init": lambda x: {"op": "player_face_init", "eye_table_ram": H(x["args"][1]), "mouth_table_ram": H(x["args"][2])}, "face_eyes": lambda x: {"op": "player_face", "channel": "eyes", "sequence": x["args"][1]}, "face_mouth": lambda x: {"op": "player_face", "channel": "mouth", "sequence": x["args"][1]},
	"face_eyes_frame": lambda x: {"op": "player_face_frame", "channel": "eyes", "frame": x["args"][1]}, "face_mouth_frame": lambda x: {"op": "player_face_frame", "channel": "mouth", "frame": x["args"][1]},
	"effect_0f": lambda x: {"op": "effect_spawn", "class": 0x0F, "pool": "effect (SLES0x8003E8F8)", "spawner": "ST3AT 0x800F4724", "entry_raw": x["entry"], "entry_ram": x["entry_ram"], "arg": x["arg"]},
	"actor_21": lambda x: {"op": "effect_spawn", "class": 0x21, "pool": "0x40 (SLES0x8003E73C)", "spawner": "ST3AT 0x800F47E4", "entry_raw": x["entry"], "entry_ram": x["entry_ram"]},
	"spawn_effect_8": lambda x: {"op": "effect_spawn", "class": 0x0F, "pool": "effect (SLES0x8003E8F8)", "spawner": "inline", "variant": 0x0A},
	"file_load": lambda x: {"op": "file_load", "file_id": x["args"][0], "native": "SLES0x8001B2D8(%#x)" % x["args"][0]}, "player_bank": lambda x: {"op": "player_bank_switch", "native": "scratch 0x1F80000C ^= 1; SLES0x80023040 (player+0x298 scene animation bank)"},
	"skip_lock": lambda x: {"op": "skip_lock", "set": x["value"]}, "player_render_flag": lambda x: {"op": "player_render_flag", "set": x["value"]}, "sound_latch": lambda x: {"op": "sound_latch", "value": x["value"]},
	"backdrop": lambda x: {"op": "scrolling_backdrop", "enabled": bool(x["value"][0]), "velocity_raw": list(x["value"][1:]), "offset_raw": x["offset_raw"], "texture": BACKDROP_FILE, "tpage": BACKDROP_TPAGE, "clut": BACKDROP_CLUT}}
NEW_OPS = {"player_face_frame": {"params": "channel eyes|mouth, frame", "semantics": "SLES0x80041724/0x8004173C(ctx+0xB0, frame): stop that channel's face sequence and hold the fixed frame (writes player +0x1A0 eyes / +0x1A1 mouth)", "sources": ["0x800F29A0", "0x800F29AC", "0x800F4468", "0x800F44AC"]},
	"scrolling_backdrop": {"params": "enabled, velocity_raw[2] (s8 per tick), offset_raw[2]", "semantics": "ST3AT 0x800F4530 (called every tick while ctx+0x16 != 0): ctx+0x10/+0x12 += s8 ctx+0x14/+0x15; draws an 8x8 grid of 128x128 GP0 0x64 sprites (colour 0x808080, clut 0x7C80, v 0x80, u 0/0x80 alternating by row) at screen x = ((ctx+0x10 >> 4) & 0x7F) - 0x160 + col*0x80, y = ((ctx+0x12 >> 4) & 0xFF) - 0x188 + row*0x80 (culled outside x -0x80..0x140, y -0x80..0xF0), after a DR_MODE (SLES0x80063DD4(dfe 1, dtd 1, tpage 0x1B, no window): 4-bit page at VRAM (704,256)), linked at OT entry *(0x80078DDC)+0x88; every enable resets ctx+0x10/+0x12 to 0; the texture is page 0x1B with CLUT 0x7C80 (VRAM (0,498)), both uploaded by DAT/ST3AT.BIN section 0x1D000 (image 704,256 64x256, palette 0,498 128x1); texture = that 256x256 page (rows 0x80..0xFF used)", "sources": ["0x800F4530", "0x800F4560 (tpage)", "0x800F4668..0x800F466C (clut, v)", "0x800F4684..0x800F468C (u by row)", "0x800F2AD0..0x800F2AE0 (update, after the step callback)", "0x800F2A2C (init)", "0x800F2900..0x800F2918", "0x800F31A4..0x800F31C0", "0x800F3460..0x800F347C", "0x800F377C..0x800F3790"]},
	"effect_spawn": {"params": "class, entry_raw (s16 x,y,z, u16 flags), arg", "semantics": "ST3AT 0x800F4724 spawns effect class 0x0F (byte6 = 5, or 6 when flags bit 0x40; +0xC = arg; +0xD = 0x20; +0xE = flags bit7; +0xF = flags low nibble); 0x800F47E4 spawns pool-0x40 class 0x21 (ST3A_08800 model flags 0x2140) at the entry position with yaw 0x800; inline 0x800F3CCC spawns class 0x0F variant 0x0A every 4 ticks; class 0x0F visuals are not decoded", "sources": ["0x800F31E8", "0x800F32E4", "0x800F34FC", "0x800F35E0", "0x800F36EC", "0x800F380C", "0x800F3960", "0x800F396C", "0x800F3A3C", "0x800F3A54", "0x800F3CCC"]},
	"file_load / player_bank_switch": {"semantics": "SLES0x8001B2D8(0xFC / 0xFD) loads DAT/ST3A01.BIN / ST3A02.BIN (area 3 texture banks, tools/world.py AREA_TEXTURE_BANKS); 0x800F4228..0x800F423C toggles scratch 0x1F80000C and calls SLES0x80023040 so player controls 0x80.. resolve from the ST3A02 section-0 bank"},
	"player_render_flag / sound_latch / skip_lock / camera_shake / play_xa": {"semantics": "as tools/intro_scene.py NEW_OPS; the sound latch is ctx+0x1A (finish plays 0x2A3 when set, 0x800F2B78..0x800F2B90)"}}

def actor_models(root, stage=STAGE, archives=("ST3A_08800", "ST3A02_00000")):
	out = {}
	for archive in archives:
		manifest = json.loads((root / "assets/levels" / stage / "models" / archive / "manifest.json").read_text(encoding="utf-8"))
		for index, model in enumerate(manifest["models"]): out.setdefault(model["flags"], (archive, index, model))
	return out

def actor_entry(rec, area, models, stage=STAGE, variant_key=False):
	b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0; found = models.get((b[6] << 16 if variant_key else 0) | (b[4] << 8) | b[2])
	entry = {"stage": stage, "area": area, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9]}
	if found is None: return {"source_ram": rec["source_ram"], "native_slot": rec["slot"], "entry": entry, "model": None}
	archive, index, model = found; exp = model.get("export", {}); runtime = "assets/levels/%s/actors/%s/%s" % (stage, archive, Path(model["file"]).name); entry.update(model_index=index, model_file=runtime)
	return {"source_ram": rec["source_ram"], "native_slot": rec["slot"], "entry": entry, "model": {"file": runtime, "source_archive": archive, "source_model_index": index, "source_flags": model["flags"], **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp}, "model_file": runtime, "model_index": index}, "source_file": model["file"]}

def copy_actor_models(root, out, actors):
	for item in actors:
		source = root / item.pop("source_file"); folder = out / "actors" / item["model"]["source_archive"]; folder.mkdir(parents=True, exist_ok=True)
		for path in source.parent.glob(source.stem + "*"):
			if path.suffix in (".glb", ".png"): shutil.copy2(path, folder / path.name)

def export(root=None, out_dir=None):
	import fire_mission, intro_scene, models as player_models, scene_player, world
	root = Path(root or ROOT); load(root); out = Path(out_dir or root / "assets/levels") / STAGE; out.mkdir(parents=True, exist_ok=True)
	e, tracks, ticks = emulate(); tl = fire_mission.timeline(TIMELINE); native = fire_mission.commands(CAMERA)
	if native[-1]["source_ram"] != H(TIMELINE - 4): raise ValueError("camera stream does not end at the timeline")
	models = actor_models(root); area_of = {}; current = 0
	for x in e.events:
		if x["kind"] == "request_block" and x["state"] == 1: current = bytes.fromhex(x["bytes"])[5]
		if x["kind"] == "spawn": area_of.setdefault(x["record"], current)
	order = []
	for c in native:
		if c["opcode"] == 0x40 and c["actor_record"]["source_ram"] not in order: order.append(c["actor_record"]["source_ram"])
	actors = []; slot_of = {}; omitted = []
	for address in order:
		item = actor_entry(fire_mission.record(int(address, 16)), area_of.get(address, 0), models)
		if item["model"] is None: omitted.append({"record": address, "class": item["entry"]["actor_class"], "pool": item["entry"]["pool_type"], "reason": "no exported model for this (class, pool); not representable by native_scene.gd"}); continue
		slot_of[address] = item["slot"] = len(actors); actors.append(item)
	copy_actor_models(root, out, actors)
	commands = []; occupant = {}; adaptations = []
	for c in native:
		item = dict(c); op = c["opcode"]
		if op in (0x40, 0x41):
			address = c["actor_record"]["source_ram"]; occupant[fire_mission.record(int(address, 16))["slot"]] = address if op == 0x40 else None
			if address not in slot_of: adaptations.append({"source_ram": c["source_ram"], "action": "omitted", "reason": "record %s has no model" % address}); continue
		if op == 0x11:
			native_slot = (c["words"][0] >> 16) & 255; address = occupant.get(native_slot); item["target_record"] = address
			if address in slot_of: item["native_words"] = c["words"]; item["words"] = [(c["words"][0] & 0xFF00FFFF) | (slot_of[address] << 16)] + c["words"][1:]; adaptations.append({"source_ram": c["source_ram"], "action": "retargeted", "reason": "native slot %d -> runtime slot %d (%s)" % (native_slot, slot_of[address], address)})
			else: adaptations.append({"source_ram": c["source_ram"], "action": "kept", "reason": "relative-focus target slot %d holds %s (not spawned at runtime)" % (native_slot, address)})
		commands.append(item)
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_mission.programs(scene_events, tl, {**fire_mission.OPS, **OPS})
	for operation in (operation for segment in (segments.values() if isinstance(segments, dict) else segments) for operation in segment.get("program", [])):
		if operation["op"] == "fade": operation["wait"] = int(operation["source"], 16) in WAITED_FADES
	for x in e.events:
		if x["kind"] != "move_local" or x.get("actor_slot") is not None or not x["args"][3]: continue
		motion = segments["%d:%d" % (x["phase"], x["step"])].setdefault("motion", []); velocity = [x["args"][1], x["args"][2], x["args"][3]]
		if motion and motion[-1]["velocity_raw"] == velocity and motion[-1]["through_tick"] == x["frame"] - 1: motion[-1]["through_tick"] = x["frame"]
		else: motion.append({"actor": "player", "from_tick": x["frame"], "through_tick": x["frame"], "velocity_raw": velocity, "source": "SLES0x800417AC(player, 0, 0, ctx+0x18) at %s" % x["caller"]})
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = slot_of.get(x["actor_slot"], x["actor_slot"])
	controllers = fire_mission.controllers(e, {slot_of[k]: v for k, v in tracks.items() if k in slot_of}, {item["slot"]: item["source_ram"] for item in actors})
	for slot, profile in controllers.items():
		entry = actors[int(slot)]["entry"]; profile["source"] = "ST3AT class 0x%02X (pool 0x%02X) update emulated once per native tick after the scene update; render helpers stubbed" % (entry["actor_class"], entry["pool_type"])
	stage_request = fire_mission.request(e.requests[-1]); K = fire_mission.K
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"]) != (2, "ST08", 0, [K(0x800F2C4C, -0x580), K(0x800F2C54, -0x400), K(0x800F2C5C, 0x10)], K(0x800F2C64, 0xC00)): raise ValueError("finish request differs: %s" % stage_request)
	disc = root / "build/disc-assets"; payload = (disc / "COMMON/PL00P000.BIN").read_bytes()[0x30:]; face_word = struct.unpack_from("<4I", payload, 0x60)[2]
	vram, _ = player_models.textures(disc / "COMMON/PL00T.BIN"); world.texture_uploads(D["ovl"], vram, "DAT/ST3AT.BIN"); world.write_if_changed(out / "player_face_page1.png", player_models.texture_page(vram, face_word >> 16, (face_word & 0xFFFF) + 1)); world.write_if_changed(out / BACKDROP_FILE, world.texture_page(vram, BACKDROP_CLUT, BACKDROP_TPAGE))
	bank = scene_player.export_scene_player_clips("ST3A02", out, (0x0A,))
	scene = {"stage": STAGE, "area": 0, "scene_id": SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_06_callbacks.json", "commands": commands, "native_commands": native, "command_adaptations": adaptations, "omitted_actors": omitted, "timeline": tl, "actors": actors,
		"player": {"scene_init": {"position_raw": [0, 0, 0], "source": "0x800F2980..0x800F2988 (player +0x10/+0x14/+0x18 = 0, +0xF4/+0x1A0/+0x1A1 = 0; yaw +0x2A not written)"}, "track": intro_scene.compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": intro_scene.face_table(0x800F6994, 4), "player_mouth": intro_scene.face_table(0x800F69E4, 2)},
		"emulation": {"script": "tools/flight_scene.py", "native_ticks": ticks, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc", "actor_free_3EA4C", "actor_free_3EB7C")]},
		"source": {"overlay": "DAT/ST3AT.BIN (load 0x800E7000, code size 0x%X)" % (D["code_end"] - BASE), "handler": "0x800F2840 (GAME table 0x800DC490[6])", "state_table": "0x800F69EC {0x800F287C init, 0x800F2A4C update, 0x800F2AF8 finish}", "command_pointer": H(CAMERA), "timeline_pointer": H(TIMELINE), "trigger": "per-frame 0x800E7574 (GAME table 0x800DC66C[0x3A])",
			"actor_tables": "*0x80078FA8 = 0x800F48A0 (pool 0x20), *0x80078DE0 = 0x800F4AB8 (pool 0x60), set by stage init 0x800E7328 (GAME table 0x800DBEA0[0x3A])", "voice_descriptors": "table 0 = 0x800F5238 (ids 0x16, 0x27, 0x30)", "player_bank": "DAT/ST3A02.BIN section 0 (type 0x0A) -> player_scene.json (%d clips)" % len(bank["clips"])}}
	finish_ops = [op for op in finish if op["op"] != "stage_request"]
	finish_ops.insert(next(i for i, op in enumerate(finish_ops) if op["op"] == "close_windows") + 1, {"op": "play_sound_if_latched", "id": K(0x800F2B8C, 0x2A3), "source": "0x800F2B78..0x800F2B90 (ctx+0x1A)"})
	contract = {"schema": 1, "stage": STAGE, "scene_id": SCENE_ID, "source": "ST3AT scene 6 handler 0x800F2840; timeline callbacks %s" % ", ".join(sorted({t["callback"] for t in tl})),
		"tick_basis": "tick = native ctx+0x28 of the step; program delays are the emulated substate counters (fades and XA reported idle immediately in emulation)",
		"initialization": {"player_position_raw": [0, 0, 0], "player_yaw_raw": 0, "player_yaw_unverified": True, "player_yaw_note": "native init does not write yaw (+0x2A)", "spawn_records": [], "init_ops": init, "source": "0x800F287C (GAME0x800C0C5C(0x800F5F7C, 0x800F6894) at 0x800F28D4)"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST3AT 0x800F2AF8", "fade_exit": 0x12, "fade_exit_source": "issued by phase 2 step 0 at tick 0x244 (0x800F44C0)", "ops": finish_ops,
			"skip_path": {"source": "0x800F2A8C..0x800F2ABC", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2", "note": "finish loads ST3A02 (SLES0x8001B2D8(0xFD), 0x800F2BF8) when ctx+0x17 is clear (skip before phase 1 step 11)"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800F2C34..0x800F2C88 request block 0x80078D08", "request_bytes": stage_request["bytes"]}},
		"xa": {"descriptor_index": 0x16, "table": "0x800F5238", "answers": []}, "new_ops": NEW_OPS}
	world.write_if_changed(out / "scene_06.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_if_changed(out / "scene_06_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	triggers = {"stage": STAGE, "triggers": [{"entry_area": 0, "native_save_byte14": 0, "scene_id": SCENE_ID, "source_function": "GAME0x800C0B0C", "file": "scene_06.json",
		"source": "ST3AT per-frame 0x800E7574 (GAME table 0x800DC66C[0x3A]) starts scene 6 when area byte 0x8009C7F9 == 0 and latch 0x8009BE08 == 0, then sets the latch; 0x800E7544 (from area init 0x800E7414) clears the latch on every area load; no +0x14 or event-flag test (0 is the +0x14 value on arrival from ST1E)"}]}
	world.write_if_changed(out / "scene_triggers.json", json.dumps(triggers, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "actors": len(actors), "omitted_actors": [o["record"] for o in omitted], "adaptations": len(adaptations), "transition": stage_request, "player_clips": len(bank["clips"]), "segments": len(segments)}

if __name__ == "__main__":
	print(json.dumps(export(), indent=1))
