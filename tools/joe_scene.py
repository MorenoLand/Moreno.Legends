"""Export the original ST08 workshop scene 0x4F camera, actor motion and dialogue callbacks."""
import json, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
STAGE = "ST08"; SCENE_ID = 0x4F; HANDLER = 0x800EFE40; CAMERA = 0x800F544C; TIMELINE = 0x800F553C; STARTUP = {0x800F5424: "0x800EC344", 0x800F5438: "0x800E7B1C"}; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0
def export(root=None, out_dir=None):
	import landing_scene, fire_mission, flight_scene, intro_scene, unicorn, world
	root = Path(root or ROOT); landing_scene.load(root); game = landing_scene.D["game"]
	if struct.unpack_from("<I", game, 0x30 + 0x800DC490 + SCENE_ID * 4 - 0x800AD000)[0] != HANDLER: raise ValueError("GAME scene 0x4F binding differs")
	if [fire_mission.u32(0x800F55B4 + i * 4) for i in range(3)] != [0x800EFE7C, 0x800EFF94, 0x800F00D0]: raise ValueError("ST08 workshop scene states differ")
	e = fire_mission.stage_emulator(landing_scene.STAGE_INIT, 0x800F22B8, landing_scene.D["code_end"], ((0x800201B0, "scene_music", 0, True, False),))()
	def spawn(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = fire_mission.H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", record=fire_mission.H(rec), slot=e.u8(rec + 1))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn, begin=0x800C1040, end=0x800C1040)
	def fade_state(uc, address, size, data):
		value = e.r(4)
		if value in (0x12, 0x22): e.w8(0x80078F00, 1)
		elif value == 1: e.w8(0x80078F00, 0)
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, fade_state, begin=0x8001392C, end=0x8001392C)
	e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.events.clear(); e.w8(PLAYER, e.u8(PLAYER) | 2)
	tracks, ticks = fire_mission.run_scene(e, HANDLER, {"head": ((0, 0), lambda e: (e.u16(CTX + 0x10), intro_scene.s16(e.u16(CTX + 0x14)))), "ctl": ((), lambda e: tuple(sorted((rec, e.u8(ptr + 0xA0)) for ptr, rec in e.actors.items())))})
	tl = fire_mission.timeline(TIMELINE); commands = fire_mission.commands(CAMERA)
	if len(tl) != 5 or commands[-1]["source_ram"] != fire_mission.H(TIMELINE): raise ValueError("workshop camera/timeline differs")
	if [x["index"] for x in e.events if x["kind"] == "message"] != [50, 51, 52, 53, 57]: raise ValueError("workshop dialogue differs")
	scripted = json.loads((root / "assets/levels/ST08/scripted_actors.json").read_text(encoding="utf-8")); actors = []; slots = {}
	for address, model_index in ((0x800F53FC, 2), (0x800F5410, 3), (0x800F5424, 2), (0x800F5438, 3)):
		rec = fire_mission.record(address); b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; model = dict(next(m for m in scripted["models"] if m["model_index"] == model_index)); model.pop("file", None)
		if model["native_resource_flags"] != b[2] | b[4] << 8 | b[6] << 16: raise ValueError("workshop actor model differs")
		entry = {"stage": STAGE, "area": 1, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": -rec["yaw_raw"] / 4096.0, "control": b[8], "frame": b[9], "model_index": model_index, "model_file": model["model_file"]}
		if address in (0x800F53FC, 0x800F5410): entry["native_hitbox"] = {"bounds_raw": [fire_mission.s16((0x800F51D4 if address == 0x800F53FC else 0x800F291C) + i * 2) for i in range(6)], "source_pointer_ram": "0x800f51d4" if address == 0x800F53FC else "0x800f291c", "source_field": "actor+0x58", "source_constructor": "0x800ec344" if address == 0x800F53FC else "0x800e7b1c", "anchor": "actor+0x10"}
		if False: entry["native_hitbox"] = {"bounds_raw": [fire_mission.s16(0x800F291C + i * 2) for i in range(6)], "source_pointer_ram": "0x800f291c", "source_field": "actor+0x58", "source_constructor": "0x800e7b1c", "anchor": "actor+0x10"}
		if address in STARTUP: entry["native_animation_startup"] = {"control": 0, "start_record": 0, "source_constructor": STARTUP[address], "control_source": "constructor state 1, then substate 0 sets control 0; record byte9 0x80 is not a start record", "setter": "SLES0x8003F4E8(actor,control,0)"}
		slots[rec["source_ram"]] = len(actors); actors.append({"source_ram": rec["source_ram"], "slot": len(actors), "native_slot": rec["slot"], "entry": entry, "model": model})
	for event in e.events:
		if event.get("actor_slot") is not None: event["actor_slot"] = slots.get(event["actor_slot"], event["actor_slot"])
		if event["kind"] == "head": event["frame"] = max(0, event["frame"] - 1)
	ops = {**fire_mission.OPS, **flight_scene.OPS, "head": lambda x: {"op": "head_target", "target": x["value"][0], "speed": x["value"][1]}, "spawn": lambda x: {"op": "actor_spawn", "record": x["record"]}, "scene_music": lambda x: {"op": "play_sound", "id": x["args"][0]}}
	events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("move_local", "actor_free_3EA4C", "ctl") and (x["kind"] != "spawn" or x["record"] in slots) and (x["kind"] != "despawn" or x.get("record") in slots)]
	segments, init, finish = fire_mission.programs(events, tl, ops)
	init = [x for x in init if x["op"] != "actor_spawn"]
	controllers = fire_mission.controllers(e, {slots[k]: rows for k, rows in tracks.items() if k in slots and slots[k] < 2}, {a["slot"]: a["source_ram"] for a in actors})
	seen = {}
	for x in (x for x in e.events if x["kind"] == "ctl"):
		for rec, value in x["value"]:
			if rec not in slots or str(slots[rec]) not in controllers or seen.get(rec) == value: continue
			profile = controllers[str(slots[rec])]
			if rec in seen: profile["events"].append({"op": "control", "control": value, "start_record": 0, "native": "actor+0xA0 written by the class 0 state 3 callback 0x800ECA70 (0x800F5200 table), applied by SLES0x8003F4E8", "step": x["step"], "tick": x["frame"]})
			else: profile["startup_control"] = value
			seen[rec] = value
	for slot, profile in controllers.items(): profile["source"] = "ST08 original class 0 variant 3 actor controller emulated after each scene tick"; profile.setdefault("startup_control", 0)
	controllers["0"]["track"].update(floor_follow=True, floor_above_raw=0, floor_source="GAME0x800B13FC candidate filter 0x800B1648..0x800B1668 (actor y < cell lower y) ignores volumes resting above the feet, so the ray starts at the feet; ST08T 0x800ECB14: the state 3 callback stores y (+0x16) = GAME0x800B13B4(actor) while actor+0xF == 0; the emulation stubs the map query, so the runtime resolves the floor each tick")
	controllers["1"]["track"].update(floor_follow=True, floor_above_raw=0, floor_source="ST08T 0x800E7A20: the girl update (0x800E78CC) stores y (+0x16) = GAME0x800B13B4(actor), the map floor under the actor; the emulation stubs the map query, so the runtime resolves the floor each tick")
	finish = [x for x in finish if x["op"] not in ("pool_clear", "actor_spawn", "fade")]
	close = next(i for i, x in enumerate(finish) if x["op"] == "close_windows")
	finish.insert(close, {"op": "fade", "type": 0x12, "wait": True, "source": "ST08T 0x800F0144; idle wait at 0x800F0170"})
	for operation in init:
		if operation["op"] == "jingle": operation["note"] = "SLES0x80020984(0xF,0x111,0), ST08T 0x800EFF20"
	initial = {"player_position_raw": [320, 0, -16], "player_yaw_raw": 896, "player_floor_follow": True, "spawn_records": [], "init_ops": init, "source": "ST08T 0x800EFED4..0x800EFF0C positions player then resolves floor with GAME0x800B13B4"}
	contract = {"schema": 1, "stage": STAGE, "scene_id": SCENE_ID, "tick_basis": "original ctx+0x28 at 25 Hz; dialogue/fade waits preserved in runtime", "initialization": initial, "segments": segments, "actor_controllers": controllers, "finish": {"ops": finish, "registration_records": ["0x800f5424", "0x800f5438"], "player_yaw_raw": 1024, "player_render_flag": True, "fade_entry": 1, "fade_entry_source": "ST08T 0x800F01C4..0x800F01DC: when covered-screen byte 0x80078F00 is nonzero, SLES0x8001392C(1,0) reveals the restored view; emitted after camera restore by the runtime", "source": "ST08T 0x800F00D0..0x800F022C restores player, respawns ordinary Roll and Joe's daughter, and resumes music 0x15"}}
	scene = {"stage": STAGE, "area": 1, "scene_id": SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4f_callbacks.json", "commands": commands, "timeline": tl, "actors": actors, "player": {"track": intro_scene.compress(tracks["player"]), "track_runtime": True, "floor_follow": True, "camera_opcode_0x42_used": False}, "face_tables": {"player_eyes": intro_scene.face_table(0x800F55A4, 2), "player_mouth": intro_scene.face_table(0x800F55AC, 2)}, "source": {"overlay": "DAT/ST08T.BIN", "handler": fire_mission.H(HANDLER), "command_pointer": fire_mission.H(CAMERA), "timeline_pointer": fire_mission.H(TIMELINE), "messages": [50, 51, 52, 53, 57]}, "emulation": {"script": "tools/joe_scene.py", "native_ticks": ticks, "events": [x for x in e.events if x["kind"] not in ("move_local", "face_tick", "alloc", "released", "ctl")]}}
	out = Path(out_dir or root / "assets/levels") / STAGE
	for name, payload in (("scene_4f.json", scene), ("scene_4f_callbacks.json", contract)): world.write_if_changed(out / name, json.dumps(payload, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "actors": list(slots), "messages": scene["source"]["messages"], "segments": {k: [x["op"] for x in v["program"]] for k, v in segments.items()}}
if __name__ == "__main__": print(json.dumps(export(), indent=1))
