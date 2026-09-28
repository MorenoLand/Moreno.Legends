"""Export the ST04 Flutter first-visit scene (scene 0x4C, PAL): scene_4c.json, scene_4c_callbacks.json and the scene actor models, from DAT/ST04T.BIN
static tables and a unicorn emulation (tools/fire_mission.stage_emulator); the trigger is scripted_actors.json spawn set flutter_first_visit_scene."""
import json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STAGE = "ST04"; BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0; AREA_BYTE = 0x8009C7F9; SCENARIO = 0x8009C7FC; OWNER = 0x8009BE08
SCENE_ID = 0x4C; HANDLER = 0x800E7CA0; STATES = 0x800F000C; CAMERA = 0x800EFF04; TIMELINE = 0x800EFFA4; PER_FRAME = 0x800E77B0; STAGE_INIT = 0x800E73C4; AREA0 = 0x800E7B10; EYES = 0x800EFFFC; MOUTH = 0x800F0004
ENTRY_FLAGS = (0x5F0, 0xD0, 0xD1, 0xD2)
D = {}
def H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def load(root):
	import fire_mission, intro_scene
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST04T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != BASE: raise ValueError("unexpected ST04T header")
	D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), st08=(disc / "DAT/ST08T.BIN").read_bytes(), code_end=BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_mission.D.update(ovl=ovl, game=D["game"]); intro_scene.SLES = D["sles"]; intro_scene.GAME = D["game"]; intro_scene.OVL = ovl; u32 = fire_mission.u32
	game = lambda a: struct.unpack_from("<I", D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + SCENE_ID * 4), game(0x800DBEA0 + 4 * 4), game(0x800DC66C + 4 * 4)) != (HANDLER, STAGE_INIT, PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST04 scene 0x4C")
	if [u32(STATES + i * 4) for i in range(3)] != [0x800E7CDC, 0x800E7DC4, 0x800E7E58] or [u32(0x800E7D10), u32(0x800E7D14), u32(0x800E7D18), u32(0x800E7D20)] != [0x3C04800F, 0x2484FF04, 0x3C05800F, 0x24A5FFA4]: raise ValueError("scene 0x4C state/camera/timeline binding differs")
	if u32(u32(0x800EFE4C)) != AREA0 or [u32(0x800E7B50), u32(0x800E7B54)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x2404004C]: raise ValueError("ST04 area 0 handler does not request scene 0x4C")
	if [u32(0x800E7D6C), u32(0x800E7D70), u32(0x800E7D74), u32(0x800E7D7C)] != [0x3C05800F, 0x24A5FFFC, 0x3C06800F, 0x24C60004]: raise ValueError("scene 0x4C face tables moved")

def emulate():
	import fire_mission, unicorn
	e = fire_mission.stage_emulator(STAGE_INIT, 0x800F22B8, D["code_end"])()
	e.w8(AREA_BYTE, 0); e.w8(SCENARIO, 0); e.cpu.mem_write(OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(PER_FRAME)
	entry = [x for x in e.events if x["kind"] in ("flag_set", "scene_start")]
	if [(x["kind"], x["args"][0]) for x in entry] != [("flag_set", f) for f in ENTRY_FLAGS] + [("scene_start", SCENE_ID)]: raise RuntimeError("ST04 area 0 handler did not set the entry flags and start scene 0x4C")
	e.events.clear(); e.call(PER_FRAME); again = list(e.events)
	if any(x["kind"] == "scene_start" for x in again): raise RuntimeError("ST04 area 0 handler restarted scene 0x4C with flag 0x5F0 set")
	e.events.clear()
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(PLAYER, e.u8(PLAYER) | 2)
	tracks, ticks = fire_mission.run_scene(e, HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(PLAYER) & 2))})
	return e, tracks, ticks, entry, again

def export(root=None, out_dir=None):
	import fire_mission, flight_scene, intro_scene, world
	root = Path(root or ROOT); load(root); out = Path(out_dir or root / "assets/levels") / STAGE; out.mkdir(parents=True, exist_ok=True); K = fire_mission.K
	e, tracks, ticks, entry, again = emulate(); tl = fire_mission.timeline(TIMELINE); native = fire_mission.commands(CAMERA)
	if native[-1]["source_ram"] != H(TIMELINE) or [(t["phase"], t["step"], t["duration"]) for t in tl] != [(0, 0, -1), (0, 1, -1), (0, 2, -1)]: raise ValueError("scene 0x4C camera/timeline layout differs")
	messages = [x for x in e.events if x["kind"] == "message"]
	if [(x["bank"], x["index"]) for x in messages] != [("0x8010c000", 0xC9), ("0x8010c000", 0xCA), ("0x8010c000", 0xCB)]: raise ValueError("scene 0x4C messages differ")
	bank = json.loads((root / "assets/dialogue" / json.loads((root / "assets/dialogue/manifest.json").read_text(encoding="utf-8"))["banks"][STAGE]["file"]).read_text(encoding="utf-8"))
	if any(not bank["messages"][i]["display_ready"] for i in (0xC9, 0xCA, 0xCB, 0xCC)): raise ValueError("ST04 dialogue bank does not resolve messages 0xC9..0xCC")
	models = flight_scene.actor_models(root, STAGE, ("ST04_06800",)); actors = []; slot_of = {}
	for c in native:
		if c["opcode"] != 0x40: continue
		item = flight_scene.actor_entry(fire_mission.record(int(c["actor_record"]["source_ram"], 16)), 0, models, STAGE, True)
		if item["model"] is None: raise ValueError("no model for record %s" % item["source_ram"])
		slot_of[item["source_ram"]] = item["slot"] = len(actors); actors.append(item)
	flight_scene.copy_actor_models(root, out, actors)
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = slot_of.get(x["actor_slot"], x["actor_slot"])
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_mission.programs(scene_events, tl, {**fire_mission.OPS, **flight_scene.OPS})
	step1 = segments["0:1"]["program"]
	if [op["op"] for op in step1] != ["delay", "message", "delay", "advance"] or step1[0]["ticks"] != K(0x800E8074, 0x14) or step1[1]["index"] != 0xCA: raise ValueError("scene 0x4C step 1 layout differs")
	step1[2] = {"op": "minimum_tick", "tick": K(0x800E80E0, 0x50), "source": "0x800E80D8..0x800E80F4 (ctx+0x28 >= 0x50 and SLES0x800489A0(1) idle)"}
	trigger = next((t for t in json.loads((root / "assets/levels" / STAGE / "scripted_actors.json").read_text(encoding="utf-8"))["spawn_sets"] if t["id"] == "flutter_first_visit_scene"), None)
	if trigger is None or trigger["source"]["native_side_effects"] != [{"kind": "set_event_flag", "id": f} for f in ENTRY_FLAGS] + [{"kind": "call", "function": "GAME.BIN 0x800C0B0C", "argument": SCENE_ID}]: raise ValueError("ST04 scripted_actors.json lacks the flutter_first_visit_scene trigger (tools/models.py export_flutter_scripted_actors)")
	finish_ops = [op for op in finish if op["op"] not in ("stage_request", "fade")]; close = next((index for index, op in enumerate(finish_ops) if op["op"] == "close_windows"), len(finish_ops))
	finish_ops.append({"op": "player_special_usable", "value": 0, "source": "ST04T 0x800E7FAC sb zero, player+0x19F; GAME0x800CF4D8 only activates the equipped special (+0x18E) while +0x19F != 0"})
	finish_ops.insert(close, {"op": "fade", "type": K(0x800E7EF8, 0x12), "wait": True, "source": "0x800E7EF8 (skipped when ctx byte0 & 0x10), waited at 0x800E7F04 before close_windows/pool_clear"})
	stage_request = fire_mission.request(e.requests[-1])
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"], stage_request["fade_arrival"], stage_request["fade_exit"]) != (2, "ST08", 0, [K(0x800E7F44, 0x40), 0, 0], K(0x800E7F4C, 0x800), K(0x800E7F5C, 3), K(0x800E7F54, 0xFF)): raise ValueError("finish request differs: %s" % stage_request)
	arrival = struct.unpack_from("<I", D["st08"], 0x30 + 0x800F0BA8 - BASE)[0]
	if arrival != 0x2402FFFF: raise ValueError("ST08 scene 0x55 arrival y immediate moved")
	controllers = fire_mission.controllers(e, {slot_of[k]: v for k, v in tracks.items() if k in slot_of}, {item["slot"]: item["source_ram"] for item in actors})
	for slot, profile in controllers.items():
		item = actors[int(slot)]; entry_data = item["entry"]; profile["source"] = "ST04T class 0x%02X variant %d (pool 0x%02X) emulated once per native tick after the scene update; render helpers stubbed" % (entry_data["actor_class"], entry_data["actor_state"], entry_data["pool_type"])
		profile.setdefault("startup_control", entry_data["control"])
	scene = {"stage": STAGE, "area": 0, "scene_id": SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4c_callbacks.json", "commands": native, "timeline": tl, "actors": actors,
		"player": {"track": intro_scene.compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": intro_scene.face_table(EYES, 2), "player_mouth": intro_scene.face_table(MOUTH, 2)},
		"emulation": {"script": "tools/flutter_scene.py", "native_ticks": ticks, "trigger_events": entry, "second_area_pass_events": again, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc", "face_tick")]},
		"source": {"overlay": "DAT/ST04T.BIN (load 0x800E7000, code size 0x%X)" % (D["code_end"] - BASE), "handler": "0x800E7CA0 (GAME table 0x800DC490[0x4C])", "state_table": "0x800F000C {0x800E7CDC init, 0x800E7DC4 update, 0x800E7E58 finish}", "command_pointer": H(CAMERA), "timeline_pointer": H(TIMELINE),
			"trigger": "area handler 0x800E7B10 (table 0x800EFE4C[byte14 0] = 0x800EFE28[area 0], per-frame 0x800E77B0 = GAME table 0x800DC66C[4]): flag 0x5F0 clear -> flag_set 0x5F0, 0xD0, 0xD1, 0xD2, GAME0x800C0B0C(0x4C); otherwise 0x800E7828",
			"actor_tables": "*0x80078FA8 = 0x800EF7F0 (pool 0x20), *0x80078DE0 = 0x800EF990 (pool 0x60) set by stage init 0x800E73C4 (GAME table 0x800DBEA0[4])", "messages": "bank 0x8010C000 (assets/dialogue/manifest.json banks['ST04']): 0xC9, 0xCA, 0xCB (redirects to 0xCC); 0xC9/0xCB/0xCC set flag 0x5E3 (opcode 0x26)", "voices": "stage init clears *0x80078DD8/*0x80078DD4: ST04 has no XA voice tables"}}
	contract = {"schema": 1, "stage": STAGE, "scene_id": SCENE_ID, "source": "ST04T scene 0x4C handler 0x800E7CA0; timeline callbacks %s" % ", ".join(t["callback"] for t in tl),
		"tick_basis": "tick = native ctx+0x28 of the step (GAME0x800C0D70); program delays are the emulated sub-state counters (messages and fades reported idle immediately in emulation)",
		"initialization": {"player_keep_transform": True, "suppress_props": [{"spawn_set": "revisit_byte14_0_roll_data"}], "suppress_note": "the first-visit side effects set 0x5F0, which enables revisit_byte14_0_roll_data on the runtime re-evaluation; natively GAME0x800C042C skips the stage per-frame handler while a scene is active (ctx byte0 != 0), so 0x800E7828 does not run before the scene leaves ST04", "player_position_raw": [0, -1, 0], "player_yaw_raw": 0, "player_note": "scene 0x4C never writes the player transform; this is the ST08 scene 0x55 arrival request (ST08T 0x800F0B9C..0x800F0BD8, y -1 = floor height), so the runtime should keep the arrival transform", "spawn_records": [], "init_ops": init,
			"source": "0x800E7CDC: GAME0x800C0C5C(0x800EFF04, 0x800EFFA4); GAME0x800C1148; player +0xEE/+0xEF/+0xF0/+0xF4 = 0; SLES0x80015A5C(ctx+0xC, ctx+0x18); wait GAME0x800CDD50 == 0; SLES0x80041318(ctx+0xB0, 0x800EFFFC, 0x800F0004); eyes 0, mouth 0; state 1. No fade: the screen is revealed by the arrival fade 2 of the ST08 request"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST04T 0x800E7E58 (called directly by step 2 0x800E8178)", "ops": finish_ops,
			"skip_path": {"source": "0x800E7E04..0x800E7E34", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "player +0x19F = 0", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800E7F2C..0x800E7F7C request block 0x80078D08; 0x800E7F80 waits until it is consumed", "request_bytes": stage_request["bytes"]}},
		"new_ops": {"player_keep_transform": {"semantics": "the scene does not position the player; initialization.player_position_raw is the arrival transform for reference only"}}}
	world.write_if_changed(out / "scene_4c.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_if_changed(out / "scene_4c_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "transition": stage_request, "actors": [(a["source_ram"], a["entry"]["model_file"]) for a in actors], "segments": {k: [op["op"] for op in v["program"]] for k, v in segments.items()}, "init": [op["op"] for op in init], "finish": [op["op"] for op in finish_ops]}

if __name__ == "__main__":
	print(json.dumps(export(), indent=1))
