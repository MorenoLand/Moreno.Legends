"""Export the ST09 Yosyonke return scene (scene 0x4E, PAL): scene_4e.json and scene_4e_callbacks.json, from DAT/ST09T.BIN static tables and a
unicorn emulation (tools/fire_mission.stage_emulator); the trigger is the ST09 scripted_actors.json call action of area handler 0x800E7480."""
import json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STAGE = "ST09"; BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0; AREA_BYTE = 0x8009C7F9; SCENARIO = 0x8009C7FC; OWNER = 0x8009BE08
SCENE_ID = 0x4E; HANDLER = 0x800E7884; STATES = 0x800F262C; CAMERA = 0x800F2588; TIMELINE = 0x800F25D4; PER_FRAME = 0x800E7410; STAGE_INIT = 0x800E7188; AREA0 = 0x800E7480; WALKER = 0x800F2574; WALKER_HITBOX = 0x800F2AAC; TOWNSFOLK = 0x800F2354; EYES = 0x800F261C; MOUTH = 0x800F2624
D = {}
def H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def load(root):
	import fire_mission, intro_scene
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST09T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != BASE: raise ValueError("unexpected ST09T header")
	D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), code_end=BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_mission.D.update(ovl=ovl, game=D["game"]); intro_scene.SLES = D["sles"]; intro_scene.GAME = D["game"]; intro_scene.OVL = ovl; u32 = fire_mission.u32
	game = lambda a: struct.unpack_from("<I", D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + SCENE_ID * 4), game(0x800DBEA0 + 9 * 4), game(0x800DC66C + 9 * 4)) != (HANDLER, STAGE_INIT, PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST09 scene 0x4E")
	if [u32(STATES + i * 4) for i in range(3)] != [0x800E78C0, 0x800E79A8, 0x800E7AE4] or [u32(0x800E78F4), u32(0x800E78F8), u32(0x800E78FC), u32(0x800E7904)] != [0x3C04800F, 0x24842588, 0x3C05800F, 0x24A525D4]: raise ValueError("scene 0x4E state/camera/timeline binding differs")
	if u32(u32(0x800F2300)) != AREA0 or [u32(0x800E74CC), u32(0x800E74D0)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x2404004E]: raise ValueError("ST09 area 0 handler does not request scene 0x4E")
	if [u32(0x800E7950), u32(0x800E7954), u32(0x800E7958), u32(0x800E7960)] != [0x3C05800F, 0x24A5261C, 0x3C06800F, 0x24C62624]: raise ValueError("scene 0x4E face tables moved")

def emulate():
	import fire_mission, unicorn
	e = fire_mission.stage_emulator(STAGE_INIT, 0x800F22B8, D["code_end"])(); passes = {}
	for name, flags in (("first_visit", ()), ("after_junk_shop", (0x5C1,)), ("revisit", (0x5C1, 0x5C2))):
		e.events.clear(); e.cpu.mem_write(0x98538, bytes(0x100)); e.init_flags(flags); e.w8(AREA_BYTE, 0); e.w8(SCENARIO, 0); e.cpu.mem_write(OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(PER_FRAME)
		passes[name] = [{"kind": x["kind"], "args": [x["args"][0] & 0xFFFFFFFF, x["args"][1]] if x["kind"] == "spawn_table" else [x["args"][0]]} for x in e.events if x["kind"] in ("flag_set", "flag_clear", "scene_start", "spawn_table")]
		e.events.clear(); e.call(PER_FRAME)
		if any(x["kind"] in ("scene_start", "spawn_table", "flag_set") for x in e.events): raise RuntimeError("ST09 area 0 handler ran twice without an area load (%s)" % name)
	expected = {"first_visit": [("flag_set", [0x711])], "after_junk_shop": [("spawn_table", [TOWNSFOLK, 2]), ("scene_start", [SCENE_ID]), ("flag_set", [0x5C2]), ("flag_set", [0x711])], "revisit": [("spawn_table", [TOWNSFOLK, 2]), ("flag_set", [0x711])]}
	if {k: [(x["kind"], x["args"]) for x in v] for k, v in passes.items()} != expected: raise RuntimeError("ST09 area 0 handler passes differ: %s" % passes)
	e.events.clear(); e.cpu.mem_write(0x98538, bytes(0x100)); e.init_flags((0x5C1, 0x5C2))
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(PLAYER, e.u8(PLAYER) | 2); s16 = lambda v: v - 0x10000 if v & 0x8000 else v
	tracks, ticks = fire_mission.run_scene(e, HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(PLAYER) & 2)), "head": ((0, 0), lambda e: (e.u16(CTX + 0x10), s16(e.u16(CTX + 0x14))))})
	for x in e.events:
		if x["kind"] == "head": x["frame"] -= 1; x["head_source"] = "ctx+0x10/+0x14 written by the step callback at ctx+0x28 = frame (sampled after the scene call)"
	return e, tracks, ticks, passes

OPS = {"head": lambda x: {"op": "head_target", "target": x["value"][0], "speed": x["value"][1]}, "despawn": lambda x: {"op": "despawn", "record": x["record"], "native": "GAME0x800C1058(0x800F2574)"}}

def export(root=None, out_dir=None):
	import fire_mission, flight_scene, intro_scene, world
	root = Path(root or ROOT); load(root); out = Path(out_dir or root / "assets/levels") / STAGE; out.mkdir(parents=True, exist_ok=True); K = fire_mission.K
	e, tracks, ticks, passes = emulate(); tl = fire_mission.timeline(TIMELINE); native = fire_mission.commands(CAMERA)
	if native[-1]["source_ram"] != H(TIMELINE) or [(t["phase"], t["step"], t["duration"], t["callback"]) for t in tl] != [(0, 0, -1, "0x800e7be4")]: raise ValueError("scene 0x4E camera/timeline layout differs")
	if [c["actor_record"]["source_ram"] for c in native if c["opcode"] == 0x40] != [H(WALKER)] or any(c["opcode"] == 0x41 for c in native): raise ValueError("scene 0x4E actor commands differ")
	if any(x["kind"] in ("message", "xa_play", "xa_prepare", "stage_request", "request_block") for x in e.events): raise ValueError("scene 0x4E now uses messages, XA or a stage request; bind them")
	scripted = json.loads((root / "assets/levels" / STAGE / "scripted_actors.json").read_text(encoding="utf-8")); call = {"kind": "call", "function": "GAME.BIN 0x800c0b0c", "argument": SCENE_ID}
	trigger = [s for s in scripted["spawn_sets"] if any({k: a.get(k) for k in ("kind", "function", "argument")} == call for a in s["source"].get("native_side_effects", []))]
	if len(trigger) != 1 or {(c["id"], c["set"]) for c in trigger[0]["predicate"]["all"] if c["kind"] == "native_event_flag"} != {(0x5C1, True), (0x5C2, False)} or not {"kind": "stage_state_byte_equals", "value": 0} in trigger[0]["predicate"]["all"]: raise ValueError("ST09 scripted_actors.json lacks the area 0 scene 0x4E call (tools/models.py export_interior_scripted_actors)")
	model = dict(next(m for m in scripted["models"] if m.get("model_index") == 1 and m.get("native_resource_flags") == 0x100020)); model.pop("file", None)
	rec = fire_mission.record(WALKER); b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	if b[2] | b[4] << 8 | b[6] << 16 != model["native_resource_flags"]: raise ValueError("walker record resource differs from ST09 model 1")
	walker = {"source_ram": H(WALKER), "slot": 0, "native_slot": rec["slot"], "class_note": "townsperson (pool 0x20 class 0 variant 2, ST09T class table *0x80078FA8 = 0x800F1A70)",
		"entry": {"stage": STAGE, "area": 0, "source_record_ram": H(WALKER), "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": 1, "model_file": model["model_file"],
		"native_hitbox": {"bounds_raw": [fire_mission.s16(WALKER_HITBOX + i * 2) for i in range(6)], "source_pointer_ram": H(WALKER_HITBOX), "source_field": "actor+0x58", "source_constructor": "0x800eaf34 (0x800F2AA8[actor+0xC = 0], called from 0x800EAE8C; stored at 0x800EAF9C..0x800EAFA8)"}}, "model": model}
	for ev in e.events:
		if ev.get("actor_slot") is not None: ev["actor_slot"] = 0 if ev["actor_slot"] == H(WALKER) else ev["actor_slot"]
	scene_events = [ev for ev in e.events if ev.get("actor_slot") is None and ev["kind"] not in ("move_local", "spawn")]
	segments, init, finish = fire_mission.programs(scene_events, tl, {**fire_mission.OPS, **flight_scene.OPS, **OPS})
	program = segments["0:0"]["program"]
	if [op["op"] for op in program] != ["delay", "player_control", "head_target", "delay", "head_target", "delay", "head_target", "delay", "advance"] or [(op["target"], op["speed"]) for op in program if op["op"] == "head_target"] != [(0, K(0x800E7C18, 0x40)), (K(0x800E7C68, 0xD00), K(0x800E7C70, 0x10)), (K(0x800E7C90, 0xF60), K(0x800E7C98, 4))]: raise ValueError("scene 0x4E step layout differs: %s" % [op["op"] for op in program])
	if [op["ticks"] for op in program if op["op"] == "delay"] != [1, K(0x800E7C54, 0xF) - 1, K(0x800E7C84, 0x21) - 0xF, K(0x800E7CAC, 0x96) - 0x21]: raise ValueError("scene 0x4E step timing differs")
	program.pop(0)
	if [op["op"] for op in finish] != ["vibration", "despawn"] or finish[1]["record"] != H(WALKER): raise ValueError("scene 0x4E finish differs: %s" % [op["op"] for op in finish])
	controllers = fire_mission.controllers(e, {0: [row for row in tracks[H(WALKER)] if row[7] != 0xFF]}, {0: H(WALKER)}); controllers["0"]["source"] = "ST09T class 0 variant 2 (0x800F1A70[0] cell 2 = 0x800EAE14) emulated once per native tick after the scene update; render helpers stubbed"
	for frame in controllers["0"]["track"]["keyframes"]: frame["position_raw"][1] = y
	controllers["0"]["track"].update(floor_follow=True, floor_source="0x800EAEB8: while actor+0xF == 0, y (+0x16) = GAME0x800B13B4(actor) = GAME0x800B13FC(actor+0x10, hitbox actor+0x58, y - previous y (+0x22), cell): the map floor under the actor; the emulation stubs the map query, so the keyframe y is the record y and the runtime resolves the floor each tick")
	arrival = next((r for r in json.loads((root / "assets/levels/ST0A/doors.json").read_text(encoding="utf-8"))["area_transitions"] if r["source_area"] == 0 and r["destination_stage"] == STAGE and r["destination_area"] == 0), None)
	if arrival is None: raise ValueError("ST0A doors.json lacks the area 0 route back to ST09:0")
	scene = {"stage": STAGE, "area": 0, "scene_id": SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4e_callbacks.json", "commands": native, "timeline": tl, "actors": [walker],
		"player": {"track": intro_scene.compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": intro_scene.face_table(EYES, 2), "player_mouth": intro_scene.face_table(MOUTH, 2)},
		"emulation": {"script": "tools/yosyonke_scene.py", "native_ticks": ticks, "area_handler_passes": passes, "events": [{k: v for k, v in ev.items() if k != "sub7"} for ev in e.events if ev["kind"] not in ("move_local", "released", "alloc", "face_tick")]},
		"source": {"overlay": "DAT/ST09T.BIN (load 0x800E7000, code size 0x%X)" % (D["code_end"] - BASE), "handler": "0x800E7884 (GAME table 0x800DC490[0x4E])", "state_table": "0x800F262C {0x800E78C0 init, 0x800E79A8 update, 0x800E7AE4 finish}", "command_pointer": H(CAMERA), "timeline_pointer": H(TIMELINE),
			"trigger": "area handler 0x800E7480 (table 0x800F2300[byte14 0] = 0x800F22E4[area 0], per-frame 0x800E7410 = GAME table 0x800DC66C[9]): state byte 0x8009BE08 == 0 -> flag 0x5C1 set: GAME0x800C0818(0x800F2354, 2), then flag 0x5C2 clear: GAME0x800C0B0C(0x4E), flag_set 0x5C2; always flag_set 0x711; state++. Area init 0x800E7290 -> 0x800E73C8 clears 0x710/0x711 on every load",
			"actor_tables": "*0x80078FA8 = 0x800F1A70 (pool 0x20), *0x80078DE0 = 0x800F1A8C (pool 0x60) set by stage init 0x800E7188 (GAME table 0x800DBEA0[9])", "messages": "none", "voices": "none (no SLES0x8001B714/0x8001B864 call)"}}
	contract = {"schema": 1, "stage": STAGE, "scene_id": SCENE_ID, "source": "ST09T scene 0x4E handler 0x800E7884; timeline 0x800F25D4 has one entry (phase 0 step 0, duration -1, callback 0x800E7BE4)",
		"tick_basis": "tick = native ctx+0x28 of the step (GAME0x800C0D70); the update 0x800E79A8 turns the player head (+0x106) toward ctx+0x10 by ctx+0x14 per tick (dead zone speed/2, clamp +-0x300), as native_scene.gd _head_tick",
		"initialization": {"player_keep_transform": True, "player_position_raw": arrival["destination_transform_raw"][:3], "player_yaw_raw": arrival["destination_transform_raw"][3], "player_note": "scene 0x4E never writes the player transform; this is the ST0A area 0 door arrival (ST0A doors.json, record %d) for reference" % arrival["record_index"], "spawn_records": [], "init_ops": init,
			"source": "0x800E78C0: GAME0x800C0C5C(0x800F2588, 0x800F25D4); GAME0x800C1148; player +0xEE/+0xEF/+0xF0/+0xF4 = 0; SLES0x80015A5C(ctx+0xC, ctx+0x18); wait GAME0x800CDD50 == 0; SLES0x80041318(ctx+0xB0, 0x800F261C, 0x800F2624); eyes 0, mouth 0; state 1. No fade"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST09T 0x800E7AE4 (state 2, reached when the timeline ends after GAME0x800C0EA8(1) at 0x800E7CBC)", "ops": finish,
			"conditional_fade": {"type": K(0x800E7B94, 1), "condition": "0x80078F00 != 0 (screen left covered by a fade; SLES0x8001392C clears it for reveal fades)", "source": "0x800E7B88..0x800E7B9C after waiting 0x80078F01 == 0 (fade idle) at 0x800E7B68", "note": "not emitted: no fade covers the screen during the scene"},
			"skip_path": {"source": "0x800E79E8..0x800E7A18", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "player byte0 |= 2", "GAME0x800C0F58"], "player_render_flag": True},
		"new_ops": {"head_target": {"semantics": "ctx+0x10 = target heading, ctx+0x14 = speed (0x800E7C24/0x800E7C2C, 0x800E7C6C/0x800E7C74, 0x800E7C94/0x800E7C9C); consumed by the update 0x800E7A1C..0x800E7AC0"}}}
	world.write_if_changed(out / "scene_4e.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_if_changed(out / "scene_4e_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "passes": passes, "program": [op["op"] for op in program], "finish": [op["op"] for op in finish], "init": [op["op"] for op in init], "walker_track": len(controllers["0"]["track"]["keyframes"])}

if __name__ == "__main__":
	print(json.dumps(export(), indent=1))
