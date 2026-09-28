"""Export the ST08 landing scene (scene 0x55, PAL): scene_55.json and scene_55_callbacks.json, from DAT/ST08T.BIN static tables and a
unicorn emulation (tools/fire_mission.stage_emulator) of the unchanged area handler, scene handler and Flutter hull controller."""
import json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STAGE = "ST08"; BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0; AREA_BYTE = 0x8009C7F9; SCENARIO = 0x8009C7FC; OWNER = 0x8009BE08
SCENE_ID = 0x55; HANDLER = 0x800F0718; STATES = 0x800F55FC; CAMERA = 0x800F55C0; TIMELINE = 0x800F55EC; PER_FRAME = 0x800E762C; STAGE_INIT = 0x800E72DC; AREA0 = 0x800E769C; HULL = 0x800F2670; XA = 0x62
D = {}
def H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def load(root):
	import fire_mission, intro_scene
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST08T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != BASE: raise ValueError("unexpected ST08T header")
	D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), st3a=(disc / "DAT/ST3AT.BIN").read_bytes(), code_end=BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_mission.D.update(ovl=ovl, game=D["game"]); intro_scene.SLES = D["sles"]; intro_scene.GAME = D["game"]; intro_scene.OVL = ovl; u32 = fire_mission.u32
	game = lambda a: struct.unpack_from("<I", D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + SCENE_ID * 4), game(0x800DBEA0 + 8 * 4), game(0x800DC66C + 8 * 4)) != (HANDLER, STAGE_INIT, PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST08 scene 0x55")
	if [u32(STATES + i * 4) for i in range(3)] != [0x800F0754, 0x800F08D4, 0x800F0AE4] or [u32(0x800F0894), u32(0x800F0898), u32(0x800F089C), u32(0x800F08A4)] != [0x3C04800F, 0x248455C0, 0x3C05800F, 0x24A555EC]: raise ValueError("scene 0x55 state/camera/timeline binding differs")
	if u32(u32(0x800F261C)) != AREA0 or [u32(0x800E76E0), u32(0x800E76E4)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x24040055]: raise ValueError("ST08 area 0 handler does not request scene 0x55")

def emulate():
	import fire_mission, unicorn
	e = fire_mission.stage_emulator(STAGE_INIT, 0x800F22B8, D["code_end"], ((0x800C0818, "spawn_table", 0, True, True),))()
	def table_spawn(uc, address, size, data): ptr = e.r(3); rec = e.r(17); e.actors[ptr] = H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=H(rec), caller="GAME0x800C0874")
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, table_spawn, begin=0x800C0874, end=0x800C0874)
	e.w8(AREA_BYTE, 0); e.w8(SCENARIO, 0); e.cpu.mem_write(OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(PER_FRAME)
	entry = [x for x in e.events if x["kind"] in ("spawn", "flag_set", "scene_start")]
	if [(x["kind"], x.get("record", x.get("args", [0])[0])) for x in entry] != [("spawn", H(HULL)), ("flag_set", 0x5E4), ("scene_start", SCENE_ID)] or e.u32(OWNER + 4) not in e.actors: raise RuntimeError("ST08 area 0 handler did not spawn the hull and start scene 0x55")
	e.events.clear(); hull = e.u32(OWNER + 4)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(PLAYER, e.u8(PLAYER) | 2)
	tracks, ticks = fire_mission.run_scene(e, HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(CTX) & 0x20)), "scene_flag_04": (False, lambda e: bool(e.u8(CTX) & 4)), "player_render_flag": (True, lambda e: bool(e.u8(PLAYER) & 2)), "hull_fields": ((0, 0, 0), lambda e: (e.u8(hull + 0xA), e.u8(hull + 0xC), e.u8(hull + 0xD)))})
	scene = list(e.events); e.events.clear(); e.actors.clear(); e.call(PER_FRAME); after = list(e.events)
	if any(x["kind"] == "scene_start" for x in after) or [(x["kind"], x["args"][0] & 0xFFFFFFFF, x["args"][1] if x["kind"] == "spawn_table" else None) for x in after if x["kind"] in ("flag_set", "spawn_table")] != [("flag_set", 0x711, None), ("spawn_table", HULL, 5)]: raise RuntimeError("ST08 area 0 handler second pass differs: %s" % [x["kind"] for x in after])
	e.events = scene; return e, tracks, ticks, entry, after

ST3A_ARRIVAL = (0x800F2C4C, 0x800F2C54, 0x800F2C5C, 0x800F2C64)
def arrival():
	words = [struct.unpack_from("<I", D["st3a"], 0x30 + a - BASE)[0] for a in ST3A_ARRIVAL]
	if any(w >> 26 != 9 for w in words): raise ValueError("ST3AT arrival immediates moved")
	return [struct.unpack("<h", struct.pack("<H", w & 0xFFFF))[0] for w in words[:3]], words[3] & 0xFFFF

OPS = {"actor_free_3EA4C": lambda x: {"op": "despawn", "record": H(HULL), "native": "SLES0x8003EA4C(ctx+0x2C)"}, "scene_flag_04": lambda x: {"op": "scene_flag", "mask": 4, "set": x["value"], "native": "ctx byte0 |= 4"},
	"hull_fields": lambda x: {"op": "actor_fields", "record": H(HULL), "fields_raw": {"0x0A": x["value"][0], "0x0C": x["value"][1], "0x0D": x["value"][2]}}}
NEW_OPS = {"actor_fields": {"params": "record, fields_raw {offset: u8}", "semantics": "scene writes to the hull actor: init 0x800F080C/0x800F0810 sets +0xC = 1, +0xD = 0; update sub 0 (0x800F0918..0x800F094C) sets +0xD = 0x40 and increments +0xA once the hull is within 0x200 of its landed height. ST08T class 0x30 variant 0 (0x800ED230) never reads them; 0x800ED318 (dust ring: 16 class-3 effects every 8 ticks while +0xD counts down) reads +0xD but has no caller or pointer in ST08T, and +0xD stays 0x40 in emulation", "sources": ["0x800F080C", "0x800F0810", "0x800F0944", "0x800F094C"]},
	"scene_flag": {"params": "mask, set", "semantics": "ctx byte0 |= 4 at 0x800F0A48 together with fade 0x12; not the skip gate (GAME0x800C10B4 tests ctx byte0 & 0x20); no reader found in GAME/SLES", "sources": ["0x800F0A40..0x800F0A50"]},
	"native_prop_actor": {"semantics": "the scene subject is the hull spawned by the area handler (GAME0x800C0818(0x800F2670, 1) at 0x800E76D0, slot pointer 0x8009BE0C, copied to ctx+0x2C at 0x800F07CC); camera 0x11 targets native slot 0 = ctx+0x2C. The runtime spawns its own copy (scene slot 0) while native_props.gd keeps NativeStaticActor_ST08_46752 (same record, landed transform) visible; the runtime should drive or hide that prop for the scene and free it at 0x800F0B88 semantics (SLES0x8003EA4C) until the stage reloads"}}

def export(root=None, out_dir=None):
	import fire_mission, flight_scene, intro_scene, world
	root = Path(root or ROOT); load(root); out = Path(out_dir or root / "assets/levels") / STAGE; out.mkdir(parents=True, exist_ok=True)
	e, tracks, ticks, entry, after = emulate(); tl = fire_mission.timeline(TIMELINE); native = fire_mission.commands(CAMERA)
	if native[-1]["source_ram"] != H(TIMELINE - 4) or [(t["phase"], t["step"], t["duration"], t["callback"]) for t in tl] != [(0, 0, -1, "0x0")]: raise ValueError("scene 0x55 camera/timeline layout differs")
	if any(x["kind"] == "message" for x in e.events): raise ValueError("scene 0x55 uses messages; bind the ST08 bank")
	scripted = json.loads((root / "assets/levels" / STAGE / "scripted_actors.json").read_text(encoding="utf-8")); instance = next(i for i in scripted["instances"] if i["spawn_set"] == "flutter_hull_first_visit" and i["source_record_ram"] == H(HULL))
	model = dict(next(m for m in scripted["models"] if m["model_index"] == instance["model_index"])); model.pop("file", None)
	rec = fire_mission.record(HULL); x, y, z = rec["position_raw"]; y += fire_mission.K(0x800F07F4, -0x400); z += fire_mission.K(0x800F0814, 0x80)
	b = bytes.fromhex(rec["bytes_hex"]); turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	hull = {"source_ram": H(HULL), "slot": 0, "native_slot": rec["slot"], "class_note": "Flutter hull (class 0x30, pool 0x20; controller ST08T 0x800ED230); native_props instance %s file offset %d" % (instance["spawn_set"], instance["file_offset"]),
		"entry": {"stage": STAGE, "area": 0, "source_record_ram": H(HULL), "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "record_position_raw": rec["position_raw"], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "position_note": "record position after scene init (0x800F07F4: y -= 0x400; 0x800F0814: z += 0x80)", "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": instance["model_index"], "model_file": instance["model_file"]},
		"model": model}
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = 0 if x["actor_slot"] == H(HULL) else x["actor_slot"]
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_mission.programs(scene_events, tl, {**fire_mission.OPS, **flight_scene.OPS, **OPS})
	opening = next(op for op in init if op["op"] == "fade"); init.remove(opening); program = segments["0:0"]["program"]
	program.insert(0, dict(opening, wait=False, note="issued at the end of init (state 0 sub 3) with GAME0x800C0C5C; SLES0x8001392C only starts it and the update never waits; native_scene.gd init_ops ignore fades, so it opens segment 0:0"))
	exit_fade = next(i for i, op in enumerate(program) if op["op"] == "fade" and op["type"] == 0x12); flag = next(i for i, op in enumerate(program) if op["op"] == "scene_flag")
	if [op["op"] for op in program[exit_fade:]] != ["fade", "delay", "scene_flag", "advance"] or program[exit_fade + 1]["ticks"] != 1: raise ValueError("scene 0x55 sub 4/5 layout differs")
	program[exit_fade:] = [dict(program[flag], note="same native tick as the fade (0x800F0A38..0x800F0A50)"), dict(program[exit_fade], wait=True, wait_source="sub 5 (0x800F0A64..0x800F0A7C) waits 0x80078F01 == 0"), {"op": "finish", "source": "0x800F0A78 (ctx+4 = 2); the timeline step is never advanced"}]
	finish_ops = [op for op in finish if op["op"] != "stage_request"]; finish_ops.insert(next(i for i, op in enumerate(finish_ops) if op["op"] == "xa_fade_out") + 1, {"op": "wait_xa_idle", "source": "0x800F0B64..0x800F0B80 (SLES0x8001AFD0 and 0x80078F01 == 0)"})
	stage_request = fire_mission.request(e.requests[-1]); K = fire_mission.K
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"], stage_request["fade_arrival"], stage_request["fade_exit"]) != (2, "ST04", 0, [0, -1, 0], 0, K(0x800F0B9C, 2), K(0x800F0BB0, 0xFF)): raise ValueError("finish request differs: %s" % stage_request)
	controllers = fire_mission.controllers(e, {0: tracks[H(HULL)]}, {0: H(HULL)}); controllers["0"]["source"] = "ST08T class 0x30 variant 0 (0x800ED230) emulated once per native tick after the scene update; position driven by the scene's SLES0x800417AC(hull, 0, +0x3A, +0x3C) at 0x800F0A8C"
	position, facing = arrival(); xa_entry = None; audio_path = root / "assets/levels" / STAGE / "audio/manifest.json"
	if audio_path.is_file(): xa_entry = next((item for item in json.loads(audio_path.read_text(encoding="utf-8"))["entries"] if int(item["id"]) == XA), None)
	if xa_entry is None: raise ValueError("ST08 audio manifest lacks XA id %#x; run audio.export_stage_voices(cue, 'ST08')" % XA)
	commands = [dict(c, target_record=H(HULL), note="native slot 0 = ctx+0x2C = hull (0x800F07CC); runtime slot 0") if c["opcode"] == 0x11 else c for c in native]
	scene = {"stage": STAGE, "area": 0, "scene_id": SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_55_callbacks.json", "commands": commands, "timeline": tl, "actors": [hull],
		"player": {"hidden": True, "track": intro_scene.compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)}, "face_tables": {},
		"emulation": {"script": "tools/landing_scene.py", "native_ticks": ticks, "trigger_events": entry, "second_area_pass_events": after, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc")]},
		"source": {"overlay": "DAT/ST08T.BIN (load 0x800E7000, code size 0x%X)" % (D["code_end"] - BASE), "handler": "0x800F0718 (GAME table 0x800DC490[0x55])", "state_table": "0x800F55FC {0x800F0754 init, 0x800F08D4 update (sub table 0x800E71D4), 0x800F0AE4 finish}", "command_pointer": H(CAMERA), "timeline_pointer": H(TIMELINE),
			"trigger": "area handler 0x800E769C (table 0x800F261C[byte14 0][area 0], per-frame 0x800E762C = GAME table 0x800DC66C[8]): state byte 0x8009BE08 == 0 and flag 0x5E4 clear -> GAME0x800C0818(0x800F2670, 1), flag_set 0x5E4, GAME0x800C0B0C(0x55)",
			"actor_tables": "*0x80078FA8 = 0x800F1BA0 (pool 0x20) set by stage init 0x800E72DC (GAME table 0x800DBEA0[8])", "voice_descriptors": "table 0 = *0x80078DD8 = 0x800F22AC (id 0x62 = %s)" % xa_entry["descriptor_ram"]}}
	contract = {"schema": 1, "stage": STAGE, "scene_id": SCENE_ID, "source": "ST08T scene 0x55 handler 0x800F0718; timeline 0x800F55EC has one entry (phase 0 step 0, duration -1, no callback), the update runs its own sub-state machine",
		"tick_basis": "tick = native ctx+0x28 (GAME0x800C0D70); program delays are the emulated sub-state counters (fades and XA reported idle immediately in emulation)",
		"initialization": {"player_keep_transform": True, "suppress_props": [{"spawn_set": "flutter_hull_revisit_group", "identity": "Flutter hull"}], "suppress_note": "native spawns only the scene hull here (0x800E76C4: flag 0x5E4 clear); the revisit group (0x800E7710) is gated on 0x5E4, which the port evaluates in the same pass, so hide its landed hull for the scene", "player_position_raw": position, "player_yaw_raw": facing, "player_note": "scene 0x55 never writes the player transform; this is the ST3A scene 6 arrival request (ST3AT 0x800F2C4C..0x800F2C64); the player is hidden for the whole scene", "spawn_records": [H(HULL)], "init_ops": init,
			"source": "0x800F07AC..0x800F08BC: GAME0x800C1148; player byte0 &= ~2; ctx+0x2C = *(0x8009BE0C); ctx+0xC/+0xE = hull y/z; hull +0x3A = 0x100, +0x42 = -0x10, y -= 0x400, z += 0x80; wait !(0x80078DBA & 1) -> SLES0x8001B714(0x62); wait !(0x80078DBA & 2) -> SLES0x8001B864(0x62); wait SLES0x8001AF94 -> GAME0x800C0C5C(0x800F55C0, 0x800F55EC), GAME0x800C0D70, SLES0x8001392C(2, 0), state 1"},
		"segments": segments, "actor_controllers": controllers,
		"update": {"source": "0x800F08D4 (sub table 0x800E71D4); every tick SLES0x800417AC(hull, 0, +0x3A, +0x3C), skip check, GAME0x800C0D70", "subs": ["0 (0x800F0918): descend at +0x3A = 0x100 until y >= target - 0x100 (+0xD = 0x40 at target - 0x200)", "1 (0x800F0974): +0x3A += -0x10 per tick down to 0x20", "2 (0x800F09B0): descend until y >= target, snap, +0x3C = -0x20", "3 (0x800F09EC): slide z until <= target, snap, ctx+0x1C = 0", "4 (0x800F0A24): after 0x1E ticks fade 0x12 and ctx byte0 |= 4", "5 (0x800F0A64): wait 0x80078F01 == 0, state 2"]},
		"finish": {"source": "ST08T 0x800F0AE4", "fade_exit": 0x12, "fade_exit_source": "issued by update sub 4 (0x800F0A38)", "ops": finish_ops,
			"skip_path": {"source": "0x800F0A94..0x800F0AC4", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0 (never locked: the scene does not set ctx byte0 & 0x20)", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800F0B9C..0x800F0BD8 request block 0x80078D08 (y -1 = floor height); 0x800F0BF0 waits until it is consumed, then flag 0x780", "request_bytes": stage_request["bytes"]}},
		"xa": {"descriptor_index": XA, "table": "0x800F22AC", "answers": []}, "new_ops": NEW_OPS}
	world.write_if_changed(out / "scene_55.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_if_changed(out / "scene_55_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "transition": stage_request, "xa": xa_entry["file"], "program": [op["op"] for op in program], "finish": [op["op"] for op in finish_ops], "init": [op["op"] for op in init]}

if __name__ == "__main__":
	print(json.dumps(export(), indent=1))
