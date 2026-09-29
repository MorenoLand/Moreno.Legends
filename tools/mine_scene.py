"""Extract the original abandoned-mine scene commands and emulated callback contracts."""
import argparse, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build/pydeps"))
BASE = 0x800E7000; CTX = 0x8007CEC0; PLAYER = 0x8008C0A0
PROFILES = {0x50: (0x800FD44C, 0x801016A4, 0x801015F0, 0x8010166C, 1), 0x51: (0x800FDEFC, 0x80101800, 0x80101704, 0x801017D8, 11), 0x52: (0x800FE628, 0x801018B4, 0x80101820, 0x8010189C, 12), 0x53: (0x800FE9E0, 0x80101918, 0x801018D4, 0x80101900, 12), 0x54: (0x800FED6C, 0x80101A6C, 0x80101988, 0x80101A3C, 11)}
def load(root=ROOT):
	import fire_mission, intro_scene
	disc = Path(root) / "build/disc-assets"; overlay = (disc / "DAT/ST0FT.BIN").read_bytes(); game = (disc / "COMMON/GAME.BIN").read_bytes(); executable = (disc / "SLES_035.56").read_bytes(); fire_mission.D.update(root=Path(root), disc=disc, ovl=overlay, game=game); intro_scene.SLES = executable; intro_scene.GAME = game; intro_scene.OVL = overlay
	for scene, (handler, states, camera, timeline, area) in PROFILES.items():
		if struct.unpack_from("<I", game, 48 + 0x800DC490 + scene * 4 - 0x800AD000)[0] != handler: raise ValueError("Mine scene handler differs")
	return overlay
def make_emulator(root, overlay):
	import fire_mission, intro_scene, unicorn, models
	e = fire_mission.stage_emulator(0x800E71B8, 0x800F22B8, BASE + struct.unpack_from("<I", overlay, 4)[0], ((0x800201B0, "scene_music", 0, True, False), (0x80020C74, "jingle_ready", 1, False, False), (0x8001B64C, "file_unload", 0, True, False), (0x8003FD4C, "pose_submit", 0, False, False)))(); e.model_bindings = {}; e.source_models = {}; address = 0x80120000
	for name in ("ST0F00.BIN", "ST0F01.BIN"):
		archive, payload = models.actor_archive(Path(root) / "build/disc-assets/DAT" / name); e.cpu.mem_write(address & 0x1FFFFFFF, payload)
		for model in archive["models"]: e.source_models.setdefault(model["flags"] & 0xFFFFFF, {"archive": name, "index": model["index"], "base": address, "control_table": model["control_table_offset"], "metadata": model})
		address += (len(payload) + 0xFFF) & ~0xFFF
	for function in (0x8003F4BC, 0x8003F4E8, 0x8003F768, 0x8003F794, 0x8003F840):
		if function not in e.stubs: e.cpu.hook_add(unicorn.UC_HOOK_CODE, e.stub_hook, begin=function, end=function)
		e.stubs[function] = ("actor_control" if function == 0x8003F4E8 else "animation_native", 0, function == 0x8003F4E8, True)
	def resource(uc, function, size, data):
		actor = e.r(4); source = e.pools.get(actor)
		if source is None: raise ValueError("Resource binding lacks original actor record")
		variant = 0 if function == 0x8003DFA4 else e.u8(e.r(5)); flags = source[2] | e.u8(actor + 4) << 8 | variant << 16
		if flags not in e.source_models: raise ValueError("Unbound native actor resource %#x" % flags)
		model = e.source_models[flags]; e.model_bindings[actor] = model
		if model["control_table"]: e.w32(actor + 0xAC, model["base"] + model["control_table"])
	def animation_bank(uc, function, size, data):
		model = e.model_bindings.get(e.r(4))
		if model: e.w32(0x1F800074, model["base"])
	for function in (0x8003DFA4, 0x8003DFC8): e.cpu.hook_add(unicorn.UC_HOOK_CODE, resource, begin=function, end=function)
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, animation_bank, begin=0x8003F4E8, end=0x8003F4E8)
	return e
def export_actor_catalog(root=ROOT, out=None):
	import models, world, fire_mission
	root = Path(root); overlay = load(root); out = Path(out or root / "assets/levels/ST0F"); out.mkdir(parents=True, exist_ok=True); dat = root / "build/disc-assets/DAT"; vram = bytearray(1024 * 512 * 2); uploads = []
	for path in (dat.parent / "COMMON/GAME.BIN", dat.parent / "COMMON/PL00T.BIN", dat / "ST0FT.BIN", dat / "ST0F.BIN"): uploads.extend(world.texture_uploads(path.read_bytes(), vram, path.name))
	header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture = root / "build/stages/ST0F_mine_scene_vram.bin"; models.write_if_changed(texture, header + vram); archives = {name: models.actor_archive(dat / name) for name in ("ST0F00.BIN", "ST0F01.BIN")}; exported = {}; actors = []
	addresses = [0x801007EC, 0x80100814, 0x80100828, 0x8010083C, 0x80100850, 0x80100864, 0x80100878, 0x8010180C, 0x801016C8, 0x801016DC, 0x801016F0, 0x8010194C, 0x80101960, 0x80101974]
	for _, _, camera, _, _ in PROFILES.values(): addresses.extend(int(command["actor_record"]["source_ram"], 16) for command in fire_mission.commands(camera) if "actor_record" in command)
	for address in dict.fromkeys(addresses):
		record = fire_mission.record(address); raw = bytes.fromhex(record["bytes_hex"]); flags = raw[2] | raw[4] << 8; found = [(name, item, payload) for name, (archive, payload) in archives.items() for item in archive["models"] if item["flags"] & 0xFFFFFF == flags]
		if found: found = [found[0]]
		x, y, z = record["position_raw"]; entry = {"stage": "ST0F", "source_record_ram": record["source_ram"], "source_bytes_hex": record["bytes_hex"], "record_id": raw[1], "record_type": raw[2], "actor_class": raw[4], "actor_state": raw[5], "resource_variant": raw[6], "native_private_raw": list(raw[8:12]), "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": record["yaw_raw"], "yaw_turns": -record["yaw_raw"] / 4096.0, "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": record["yaw_raw"], "yaw_turns": -record["yaw_raw"] / 4096.0, "floor_height": y == -1}}
		if not found: actors.append({"source_ram": record["source_ram"], "entry": entry, "model": None, "source_role": "Native particle record; no PBD resource"}); continue
		name, source_model, payload = found[0]; key = (name, source_model["index"])
		if key not in exported:
			file = "actors/mine/%s_model_%02d.glb" % (Path(name).stem, source_model["index"]); metadata = models.export_actor_model(payload, source_model["index"], texture, out / file, name, preserve_default_hidden=True) if source_model["mesh"]["bone_count"] else models.export_static_actor(payload, source_model["index"], texture, out / file, name); metadata.update(model_file=file, model_index=source_model["index"], native_resource_flags=flags, native_scale_raw=list(struct.unpack_from("<3h", payload, source_model["mesh_offset"] + 0x30))); exported[key] = metadata
		entry.update(model_file=exported[key]["model_file"], model_index=source_model["index"], native_resource_flags=flags)
		if raw[4] in (0x55, 0x60):
			roll = raw[4] == 0x60; constructor, body, target, callback, request = (0x800F128C, 0x80100EF4, 0x80100F00, 0x800F10B8, 0x800F1420) if roll else (0x800F0BF0, 0x80100EB8, 0x80100EC4, 0x800F0AC4, 0x800F0D54); bounds = list(struct.unpack("<6h", fire_mission.rd(body, 12))); descriptor = list(struct.unpack("<6h", fire_mission.rd(target, 12))); entry["native_animation_startup"] = {"control": raw[9], "start_record": 0, "source_constructor": fire_mission.H(constructor)}; entry["native_hitbox"] = {"bounds_raw": bounds, "source_pointer_ram": fire_mission.H(body), "source_constructor": fire_mission.H(constructor)}; entry["native_interaction"] = {"stage": "ST0F", "actor_class": raw[4], "actor_state": raw[5], "actor_callback": fire_mission.H(callback), "request_call": fire_mission.H(request), "request_api": "0x800BE2E0", "request_kind": (0x12 if raw[10] & 0x80 else 2) if roll else 0x12, "message_call": "0x800BDCF8", "message_index": raw[11], "index_source": "LBU actor+F copied from record byte+B", "bank_id": "0x8010C000", "target_descriptor_raw": descriptor, "target_descriptor_source": fire_mission.H(target), "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False}}
		if address == 0x8010180C: entry["source_attributes"] = models.source_combat_attributes(fire_mission.D["game"], 7, raw[7])["normal"]["attributes"]
		if raw[4] == 0x6F:
			entry["native_hitbox"] = {"bounds_raw": list(struct.unpack("<6h", fire_mission.rd(0x80100F84, 12))), "source_pointer_ram": "0x80100f84", "source_constructor": "0x800f1bc8"}; entry["native_interaction"] = {"stage": "ST0F", "actor_class": 0x6F, "actor_state": raw[5], "actor_callback": "0x800f1a8c", "request_call": "0x800f1d90", "request_api": "0x800BE2E0", "request_kind": 0x12, "message_call": "0x800BDCF8", "message_index": raw[11], "index_source": "unsigned actor+F copied from record+B", "bank_id": "0x8010C000", "target_descriptor_raw": list(struct.unpack("<6h", fire_mission.rd(0x80100F90, 12))), "target_descriptor_source": "0x80100f90", "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False}}
		actors.append({"source_ram": record["source_ram"], "entry": entry, "model": exported[key]})
	document = {"stage": "ST0F", "actors": actors, "source": {"script": "tools/mine_scene.py", "texture_uploads": uploads, "archives": list(archives)}}; world.write_if_changed(out / "mine_actors.json", json.dumps(document, indent=1) + "\n", encoding="utf-8"); print("mine actors", len(actors), "models", len(exported)); return document
def export(root=None, out_dir=None):
	import fire_mission, flight_scene, intro_scene, world
	root = Path(root or ROOT); out = Path(out_dir or root / "assets/levels/ST0F"); catalog = export_actor_catalog(root, out); actor_by_record = {item["source_ram"]: item for item in catalog["actors"]}; summaries = []
	for scene_id, (handler, states, camera, timeline, area) in PROFILES.items():
		e, tracks, ticks = probe(scene_id, root)
		if not any(event["kind"] == "restore_C0F58" for event in e.events): raise ValueError("Mine scene did not reach its original finish")
		tl = fire_mission.timeline(timeline); commands = fire_mission.commands(camera); requested = [event["record"] for event in e.events if event["kind"] == "spawn"]
		if scene_id == 0x53: requested.insert(0, "0x8010180c")
		actors = []
		for record in dict.fromkeys(requested):
			item = actor_by_record[record]
			if item["model"] is None: continue
			entry = dict(item["entry"]); entry["area"] = area; actors.append({"source_ram": record, "slot": entry["record_id"], "native_slot": entry["record_id"], "entry": entry, "model": item["model"]})
		slots = {item["source_ram"]: item["slot"] for item in actors}
		ops = {**fire_mission.OPS, **flight_scene.OPS, "skip_lock": lambda event: {"op": "skip_lock", "set": event["value"]}, "scene_music": lambda event: {"op": "play_sound", "id": event["args"][0]}, "spawn": lambda event: {"op": "actor_spawn", "record": event["record"]}, "sound_3d": lambda event: {"op": "play_sound", "id": event["args"][0]}, "file_unload": lambda event: {"op": "file_unload", "file_id": event["args"][0]}}
		director_events = [event for event in e.events if event.get("actor_slot") is None and (event["kind"] != "spawn" or event["record"] in slots)]; segments, initial, finish = fire_mission.programs(director_events, tl, ops); normalized_tracks = {slots[record]: rows for record, rows in tracks.items() if record in slots}; normalized_events = []
		for event in e.events:
			if event.get("actor_slot") in slots: event = {**event, "actor_slot": slots[event["actor_slot"]]}
			normalized_events.append(event)
		saved_events = e.events; e.events = normalized_events; controllers = fire_mission.controllers(e, normalized_tracks, {item["slot"]: item["source_ram"] for item in actors}); e.events = saved_events
		for controller in controllers.values(): controller["source"] = "Original ST0FT controller and SLES control-record clock executed after each source scene update; pose submission and map collision are renderer/physics adapters"
		if scene_id == 0x52:
			program = segments["0:0"]["program"]; index = next(index for index, operation in enumerate(program) if operation["op"] == "player_bank_switch"); program.insert(index, {"op": "wait_resource_ready", "file_id": 0x67, "buffer_index": 1, "source": "ST0FT0x800FE968..FE9B4: jingle15 idle, global78DBA bit0 clear, scratch1F800004==1"})
		if scene_id == 0x53:
			actors[0]["existing_actor"] = "mine_boss"; actors[0]["preserve_live_transform"] = True; controllers["0"]["external_controller"] = "native_mine_boss"; controllers["0"]["track_reference_only"] = True; segments["0:0"]["program"] = [{"op": "wait_actor_inactive", "slot": 0, "source": "ST0FT0x800FED28..FED50 tests8009C900 and actor.byte0"}, {"op": "advance", "source": "ST0FT0x800FED4C"}]
		initialization = {"init_ops": initial, "spawn_records": ["0x8010180c"] if scene_id == 0x53 else [], "source": "Original scene phase0 callback", "hardware_adapter": {"native_buffer_index": 1, "audio_and_file_readiness": "Emulation reports ready; runtime must await the corresponding resource/audio operation"}}
		player_rows = tracks.get("player", []); first = player_rows[0] if player_rows else None
		if first: initialization.update(player_position_raw=[intro_scene.s32(first[axis]) / 65536.0 for axis in (3,4,5)], player_yaw_raw=first[6])
		finish_data = {"ops": finish, "source": fire_mission.H(fire_mission.u32(states + 8)), "restore_calls": [event["kind"] for event in e.events if event["state"] == 2 and event["kind"].startswith("restore_")]}
		registrations = [event for event in e.events if event["state"] == 2 and event["kind"] == "spawn_table"]
		finish_data["registration_records"] = [fire_mission.H((event["args"][0] & 0xFFFFFFFF) + index * 20) for event in registrations for index in range(event["args"][1])]
		for address in finish_data["registration_records"]:
			if address in slots: continue
			item = actor_by_record[address]; entry = {**item["entry"], "area": area}; slot = max([actor["slot"] for actor in actors] + [-1]) + 1; actors.append({"source_ram": address, "slot": slot, "native_slot": entry["record_id"], "entry": entry, "model": item["model"], "activation": "finish_registration"}); slots[address] = slot
		if scene_id == 0x52: finish_data["retain_actor_records"] = ["0x8010180c"]; finish_data["boss_pointer_write"] = {"source_ram": "0x8009c900", "actor_slot": 0, "source": "ST0FT0x800FE888"}
		if scene_id == 0x54: finish_data["progression_scope"] = "This conversation respawns chest/effect/humanoid and sets710; refractor acquisition and5E2 belong to the later native dialogue/item path"
		base = "scene_%02x" % scene_id; contract = {"schema": 1, "stage": "ST0F", "scene_id": scene_id, "tick_basis": "Original ctx+28 at25Hz; native message, fade, resource and actor-lifetime gates retained", "initialization": initialization, "segments": segments, "actor_controllers": controllers, "finish": finish_data}; scene = {"stage": "ST0F", "area": area, "scene_id": scene_id, "native_tick_hz": 25, "callback_contract_file": base + "_callbacks.json", "commands": commands, "timeline": tl, "actors": actors, "player": {"track": intro_scene.compress(player_rows), "track_runtime": True, "floor_follow": True}, "face_tables": {}, "source": {"handler": fire_mission.H(handler), "state_table": fire_mission.H(states), "command_pointer": fire_mission.H(camera), "timeline_pointer": fire_mission.H(timeline), "overlay": "DAT/ST0FT.BIN"}, "emulation": {"script": "tools/mine_scene.py", "native_ticks": ticks, "events": [event for event in e.events if event["kind"] not in ("face_tick", "move_local", "render", "hitbox", "alloc", "released")]}}
		for name, document in ((base + ".json", scene), (base + "_callbacks.json", contract)): world.write_if_changed(out / name, json.dumps(document, indent=1) + "\n", encoding="utf-8")
		summaries.append({"scene_id": scene_id, "native_ticks": ticks, "actors": len(actors), "segments": len(segments), "messages": [event["index"] for event in e.events if event["kind"] == "message"]})
	return {"stage": "ST0F", "actors": len(catalog["actors"]), "scenes": summaries}
def probe(scene_id, root=ROOT):
	import fire_mission, intro_scene, unicorn
	overlay = load(root); handler, states, camera, timeline, area = PROFILES[scene_id]
	e = make_emulator(root, overlay)
	def spawn(uc, address, size, data):
		record = e.r(16); pointer = e.r(4); e.actors[pointer] = fire_mission.H(record); e.pools[pointer] = bytes(uc.mem_read(record & 0x1FFFFFFF, 4)); e.record("spawn", record=fire_mission.H(record), slot=e.u8(record + 1))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn, begin=0x800C1040, end=0x800C1040); e.cpu.mem_write(CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(0x8009C7F9, area); e.events.clear(); e.w8(PLAYER, e.u8(PLAYER) | 2)
	e.w8(0x1F800004, 1)
	if scene_id == 0x53:
		record = 0x8010180C; actor = e.call(0x800C05E0, (record,)); e.actors[actor] = fire_mission.H(record); e.pools[actor] = bytes(e.cpu.mem_read(record & 0x1FFFFFFF, 4)); e.cur = fire_mission.H(record); e.call(0x800EA29C, (actor,)); e.cur = None; e.w16(actor + 0x70, 0xFFFF); e.w8(actor + 8, 3); e.w32(0x8009C900, actor); e.events.clear()
	try: tracks, ticks = fire_mission.run_scene(e, handler, {"skip_lock": (False, lambda e: bool(e.u8(CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(PLAYER) & 2))}, ticks=4000)
	except Exception:
		print("scene failure", hex(scene_id), "flags", e.u8(CTX), "step", e.where(), "actors", e.actors, "npc_table", hex(e.u32(0x80078FA8))); print("latest events", e.events[-16:]); raise
	result = {"scene": hex(scene_id), "ticks": ticks, "state": e.u8(CTX + 4), "phase": e.u8(CTX + 2), "step": e.u8(CTX + 3), "sub6": e.u8(CTX + 6), "sub7": e.u8(CTX + 7), "context_flags": e.u8(CTX), "clock": [e.u32(CTX + offset) for offset in (0x20,0x24,0x28)], "commands": fire_mission.commands(camera), "timeline": fire_mission.timeline(timeline), "events": [event for event in e.events if event["kind"] not in ("face_tick", "move_local", "render", "hitbox")], "tracks": list(tracks)}
	path = Path(root) / "build/maps" / ("mine_scene_%02x_probe.json" % scene_id); path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8"); print("probe", hex(scene_id), ticks, result["state"], result["phase"], result["step"], "events", len(result["events"])); return e, tracks, ticks
def inspect_sources(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); disc = Path(root) / "build/disc-assets"; game = (disc / "COMMON/GAME.BIN").read_bytes()
	def game_word(address): return struct.unpack_from("<I", game, 48 + address - 0x800AD000)[0]
	for stage in ("ST0D", "ST0F"):
		blob = (disc / "DAT" / (stage + "T.BIN")).read_bytes(); code = blob[48:48 + struct.unpack_from("<I", blob, 4)[0]]; print(stage, "init", hex(game_word(0x800DBEA0 + int(stage[2:], 16) * 4)), "update", hex(game_word(0x800DC66C + int(stage[2:], 16) * 4)))
		for offset in range(0, len(code) - 4, 4):
			word = struct.unpack_from("<I", code, offset)[0]
			if word == 0x0C0302C3:
				for ins in decoder.disasm(code[max(0, offset - 16):offset + 8], BASE + max(0, offset - 16)): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for scene in range(0x50, 0x55):
		handler = game_word(0x800DC490 + scene * 4); print("scene", hex(scene), "handler", hex(handler)); blob = (disc / "DAT/ST0FT.BIN").read_bytes()
		for ins in decoder.disasm(blob[48 + handler - BASE:48 + handler - BASE + 0x180], handler): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for start, end in ((0x800FE774, 0x800FE9E0), (0x800FEB64, 0x800FED6C)):
		for ins in decoder.disasm(blob[48 + start - BASE:48 + end - BASE], start): print(hex(ins.address), ins.mnemonic, ins.op_str)
def detail(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	import models, fire_mission
	load(root); decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); game = fire_mission.D["game"]
	for ins in decoder.disasm(game[48 + 0x800C0D70 - 0x800AD000:48 + 0x800C0EA8 - 0x800AD000], 0x800C0D70): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for ins in decoder.disasm(game[48 + 0x800C1204 - 0x800AD000:48 + 0x800C13A0 - 0x800AD000], 0x800C1204): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for start, end in ((0x800C0C5C, 0x800C0D70), (0x800C1B88, 0x800C1CCC)):
		for ins in decoder.disasm(game[48 + start - 0x800AD000:48 + end - 0x800AD000], start): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for name in ("ST0F00.BIN", "ST0F01.BIN"):
		archive, _ = models.actor_archive(Path(root) / "build/disc-assets/DAT" / name); print(name, [(model["index"], hex(model["flags"]), model["mesh"]["bone_count"]) for model in archive["models"]])
	for address in (0x801007EC, 0x80100814, 0x80100828, 0x8010083C, 0x80100850, 0x80100864, 0x80100878): print("ordinary_actor", fire_mission.record(address))
def actor_detail(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	import fire_mission
	overlay = load(root); decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); e = fire_mission.stage_emulator(0x800E71B8, 0x800F22B8, BASE + struct.unpack_from("<I", overlay, 4)[0])(); table = e.u32(0x80078FA8)
	for actor_class in (0x55, 0x60):
		cell = e.u32(table + actor_class * 4); callback = e.u32(cell); print("actor_callback", hex(actor_class), hex(cell), hex(callback))
		for ins in decoder.disasm(overlay[48 + callback - BASE:48 + callback - BASE + 0x500], callback): print(hex(ins.address), ins.mnemonic, ins.op_str)
	executable = fire_mission.D["disc"].joinpath("SLES_035.56").read_bytes()
	for ins in decoder.disasm(executable[0x800 + 0x8003F4BC - 0x80010000:0x800 + 0x8003F5A0 - 0x80010000], 0x8003F4BC): print(hex(ins.address), ins.mnemonic, ins.op_str)
if __name__ == "__main__":
	parser = argparse.ArgumentParser(); parser.add_argument("--inspect", action="store_true"); parser.add_argument("--detail", action="store_true"); parser.add_argument("--actor-detail", action="store_true"); parser.add_argument("--actors", action="store_true"); parser.add_argument("--probe", type=lambda value: int(value, 0)); args = parser.parse_args()
	if args.inspect: inspect_sources()
	if args.detail: detail()
	if args.actor_detail: actor_detail()
	if args.actors: export_actor_catalog()
	if args.probe is not None: probe(args.probe)
	if not (args.inspect or args.detail or args.actor_detail or args.actors or args.probe is not None): print(json.dumps(export(), indent=1))
