import json
import struct
from pathlib import Path
from disc import read_u16, write_if_changed
from world import textures, texture_vram, png
from ui import color, decode_page, hud_crop
ROOT = Path(__file__).resolve().parents[1]
def export():
	data = (ROOT / "build/disc-assets/DAT/ST01T.BIN").read_bytes(); base = struct.unpack_from("<I", data, 12)[0]; offset = lambda address: 48 + address - base; records = {}
	for index in range(10):
		address = 0x800E92E4 + index * 16; stage, area, x, z, yaw, px, py, pz, heading = struct.unpack_from("<BB7h", data, offset(address)); records[hex(address)] = {"stage": "ST%02X" % stage, "area": area, "map_position": [x, z], "map_yaw_raw": yaw, "position_raw": [px, py, pz], "yaw_raw": heading}
	scenarios = {}
	for scenario in range(19):
		pointer = struct.unpack_from("<I", data, offset(0x800E94A4 + scenario * 4))[0]; destinations = []
		for index in range(10):
			address = struct.unpack_from("<I", data, offset(pointer + index * 4))[0]
			if not address: break
			destinations.append(dict(records[hex(address)], name=["Calinca", "Forbidden Island", "Sulphur Island", "Manda Island", "Nino Island", "Calbania Island", "Saul Kada"][index]))
		scenarios[str(scenario)] = destinations
	docks = {}; hull_records = {"ST08": (0x800F2670, 0), "ST10": (0x800F7BD0, 0), "ST3F": (0x800EF84C, 0), "ST24": (0x800F224C, 0), "ST17": (0x800FEDCC, 0), "ST23": (0x800EB59C, 0), "ST48": (0x800F8F9C, 0), "ST1F": (0x80101100, 0), "ST3C": (0x800FE658, 3)}
	from models import INTERIOR_SCRIPT_BINDINGS
	for stage, (address, area) in hull_records.items():
		overlay = (ROOT / "build/disc-assets/DAT" / (stage + "T.BIN")).read_bytes(); overlay_base = struct.unpack_from("<I", overlay, 12)[0]; raw = overlay[48 + address - overlay_base:68 + address - overlay_base]
		if len(raw) != 20 or raw[2] | (raw[4] << 8) | (raw[6] << 16) != 0x3020: raise ValueError(stage + " native Flutter hull record differs")
		owner = Path(INTERIOR_SCRIPT_BINDINGS.get(stage, {}).get("actor_archive_file", stage + ".BIN")).stem; scripted = ROOT / "assets/levels" / stage / "scripted_actors.json"; matches = sorted({ROOT / "assets/levels" / stage / instance["model_file"] for instance in json.loads(scripted.read_text())["instances"] if instance["source_record_ram"] == hex(address)}) if scripted.is_file() else []
		for path in [] if matches else (ROOT / "assets/levels" / stage / "models").glob(owner + "_*/manifest.json"):
			for model in json.loads(path.read_text())["models"]:
				if model.get("flags") == 0x3020: matches.append(ROOT / model["file"])
		if len(matches) != 1: raise ValueError(stage + " native Flutter hull model is not uniquely exported")
		model_file = ROOT / "assets/levels" / stage / "flutter_hull.glb"; write_if_changed(model_file, matches[0].read_bytes()); pose = list(struct.unpack_from("<4h", raw, 12)); doors = json.loads((ROOT / "assets/levels" / stage / "doors.json").read_text()); boarding = next(route for route in doors["area_transitions"] if int(route["source_area"]) == area and route["destination_stage"] == "ST04" and int(route["destination_area"]) == 1); docks[stage] = {"area": area, "record": hex(address), "position_raw": pose[:3], "yaw_raw": pose[3], "boarding_raw": boarding["source_transform_raw"], "model_file": "res://" + model_file.relative_to(ROOT).as_posix()}
	landing = json.loads((ROOT / "assets/levels/ST08/scene_55.json").read_text()); contract = json.loads((ROOT / "assets/levels/ST08/scene_55_callbacks.json").read_text()); landing["callback_contract_file"] = "landing_callbacks.json"; landing["actors"][0]["entry"]["model_file"] = docks["ST08"]["model_file"]; contract["initialization"] = {"player_keep_transform": True, "spawn_records": ["0x800f2670"], "init_ops": [{"op": "player_render_flag", "set": False}]}; contract["finish"] = {"ops": [{"op": "player_render_flag", "set": True}]}; write_if_changed(ROOT / "assets/levels/ST01/landing.json", json.dumps(landing, indent=2) + "\n", encoding="utf-8"); write_if_changed(ROOT / "assets/levels/ST01/landing_callbacks.json", json.dumps(contract, indent=2) + "\n", encoding="utf-8")
	vram, _ = texture_vram([ROOT / "build/disc-assets/COMMON/INIT.BIN", ROOT / "build/disc-assets/COMMON/GAME.BIN", ROOT / "build/disc-assets/DAT/ST01T.BIN"]); pixels = bytearray(512 * 512 * 4)
	write_if_changed(ROOT / "assets/levels/ST01/location_pins.png", png(96, 80, b"".join(hud_crop(decode_page(vram, 0x1E, clut, True), 0, 0, 96, 24) + hud_crop(decode_page(vram, 0x1E, clut), 0, 24, 96, 16) for clut in (0x7FC0, 0x7FC1))))
	for quadrant, (tpage, clut) in enumerate(zip([0x95, 0x97, 0x99, 0x9B], [0x7C00, 0x7C40, 0x7C80, 0x7CC0])):
		for y in range(256):
			for x in range(256):
				word = read_u16(vram, (((y + ((tpage >> 4) & 1) * 256) * 1024) + (tpage & 15) * 64 + x // 2) * 2); palette_index = (word >> ((x & 1) * 8)) & 255; palette = read_u16(vram, ((clut >> 6) * 1024 + (clut & 63) * 16 + palette_index) * 2); target = ((y + (quadrant // 2) * 256) * 512 + x + (quadrant & 1) * 256) * 4; pixels[target:target + 4] = bytes(color(palette, True))
	output = ROOT / "assets/levels/ST01"; write_if_changed(output / "flutter.glb", (output / "models/ST01_00800/model_000.glb").read_bytes()); write_if_changed(output / "world_map.png", png(512, 512, pixels)); write_if_changed(output / "flutter_travel.json", json.dumps({"source": "ST01 800E92E4 destination records;800E94A4 scenario lists;800E8D50 map;800E7378 aircraft;800E8AAC pins;800E7B88 targets", "list_override": {"7": [6, 0x582, 7]}, "targets": {"0": [255], "1": [1], "2": [3], "3": [3], "4": [3, 0x3D0, 2], "5": [4], "6": [255], "7": [4, 0x582, 5], "8": [5], "9": [4], "10": [4, 0x3D1, 2], "11": [6], "12": [6], "13": [6, 0x3D2, 2], "14": [0], "15": [0], "16": [0, 0x3D3, 2], "17": [5], "18": [5]}, "launch_ticks": 20, "landing_ticks": 20, "tick_rate": 25, "scenarios": scenarios, "docks": docks}, indent=2) + "\n", encoding="utf-8")
if __name__ == "__main__": export()
