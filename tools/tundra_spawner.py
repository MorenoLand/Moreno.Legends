import struct
def add(profile, overlay, game, dat_dir, output_dir, archive):
	import models
	import world
	offset = lambda address: 48 + address - 0x800E7000; game_offset = lambda address: address - 0x800AD000 + 0x30; word = lambda data, position: struct.unpack_from("<I", data, position)[0]
	if [word(game, game_offset(0x800DD978 + index * 4)) for index in range(5)] != [0x800DA778, 0x800DA7A0, 0x800DA7E4, 0x800DA91C, 0x800DB130] or [word(game, game_offset(0x800DD98C + index * 4)) for index in range(3)] != [0x800DAB94, 0x800DACF4, 0x800DB108]: raise ValueError("ST0D pop-up spawner callbacks changed")
	if word(overlay, offset(0x800E70E0)) != 0x3C02800F or word(overlay, offset(0x800E70E4)) != 0x24420200 or word(overlay, offset(0x800E7078)) != 0x24040012: raise ValueError("ST0D pop-up spawner registration changed")
	tables = [word(overlay, offset(0x800F0200 + index * 4)) for index in range(5)]
	if tables != [0x800F00B4, 0x800F00D8, 0x800F00FC, 0x800F01BC, 0x800F01FC]: raise ValueError("ST0D pop-up spawner tables changed")
	templates = [overlay[offset(tables[0] + index * 12):offset(tables[0] + index * 12) + 12] for index in range((min(word(overlay, offset(tables[1] + index * 12)) for index in range((tables[2] - tables[1]) // 12)) - tables[0]) // 12)]
	if [template.hex() for template in templates] != ["030020020500000001000000", "030020020500000000000000"]: raise ValueError("ST0D pop-up templates changed")
	def index_list(pointer):
		values = []
		while overlay[offset(pointer) + len(values)] < 128: values.append(overlay[offset(pointer) + len(values)])
		return values
	def node_list(pointer):
		nodes = []
		while True:
			x, y, z, flag = struct.unpack_from("<hhhH", overlay, offset(pointer) + len(nodes) * 8); nodes.append({"x": x, "y": y, "z": z, "flag": flag})
			if flag & 0x8000: return nodes
	zones = []
	for index in range((tables[2] - tables[1]) // 12):
		pointer, flags, spawn_radius, despawn_radius, cooldown = struct.unpack_from("<IHHHH", overlay, offset(tables[1] + index * 12)); zones.append({"index_list_ram": hex(pointer), "indices": index_list(pointer), "flags": flags, "spawn_radius": spawn_radius, "despawn_radius": despawn_radius, "despawn_ticks": cooldown})
	selectors = [list(overlay[offset(tables[4] + index * 2):offset(tables[4] + index * 2) + 2]) for index in range((0x800F0200 - tables[4]) // 2)]; node_sets = []
	for index in range((tables[4] - tables[3]) // 32):
		quadrants = []
		for quadrant in range(4):
			pointer, delay_index, music = struct.unpack_from("<IBB", overlay, offset(tables[3] + index * 32 + quadrant * 8)); quadrants.append({"nodes_ram": hex(pointer), "delay_index": delay_index, "music": music, "nodes": node_list(pointer)})
		node_sets.append(quadrants)
	immediate = lambda address: struct.unpack_from("<h", overlay, offset(address))[0]; gate = {"area": 0, "stage_state": 0, "flags_set": [0x5E1], "flags_clear": [0x5E2], "far_minimum": immediate(0x800EED5C), "release_minimum": immediate(0x800EED64), "band_maximum": immediate(0x800EED94), "band_minimum": immediate(0x800EED9C), "source": "ST0DT800EECD0..800EEDBC toggles GAME800469E0 bit 0x200 from player x; disabled at 800EECAC when the Roll record 800EEB24 is constructed"}
	if [word(overlay, offset(address)) >> 26 for address in (0x800EED5C, 0x800EED64, 0x800EED94, 0x800EED9C)] != [10, 10, 10, 10] or (gate["far_minimum"], gate["release_minimum"], gate["band_maximum"], gate["band_minimum"]) != (-0x1200, -0x7FF, -0x800, -0x11FF): raise ValueError("ST0D pop-up Roll gate changed")
	terrain = world.Stage((dat_dir / "ST0D.BIN").read_bytes()); grids = {}
	for area in (0, 1):
		tiles, _ = terrain.area(area); keys = list(tiles); x0 = min(key[0] for key in keys); x1 = max(key[0] for key in keys); z0 = min(key[1] for key in keys); z1 = max(key[1] for key in keys)
		grids[str(area)] = {"x_minimum": x0, "z_minimum": z0, "width": x1 - x0 + 1, "rows": ["".join("1" if (x, z) in tiles and (value := struct.unpack_from("<H", tiles[(x, z)], 0)[0]) & 0x8000 and value & 0x4000 and not value & 0x400 else "0" for x in range(x0, x1 + 1)) for z in range(z0, z1 + 1)]}
	raw = templates[0] + bytes(8); resource = overlay[offset(0x800F0BE8 + raw[7])]; flags = 0x20 | raw[4] << 8 | resource << 16; matches = [entry for entry in archive["archive"]["models"] if entry["flags"] & 0xFFFFFF == flags]
	if len(matches) != 1: raise ValueError("ST0D pop-up enemy model selector is unresolved")
	index = matches[0]["index"]; model_file = f"actors/ST0D_model_{index:02d}.glb"; model = models.export_actor_model(archive["payload"], index, dat_dir / "ST0DT.BIN", output_dir / "ST0D" / model_file, archive["archive_file"]); model.update(model_index=index, model_file=model_file, native_resource_flags=matches[0]["flags"])
	profile["models"] = [entry for entry in profile["models"] if entry["model_index"] != index] + [model]; combat = models.source_combat_attributes(game, raw[4], raw[7]); bounds = list(struct.unpack_from("<6h", overlay, offset(0x800F0B68)))
	profile["popup_spawner"] = {"source": {"controller_registration": "ST0DT800E7074..800E7110 -> GAME800D97EC(mask 0x12): kind1 controller 800DA644", "controller_states": "GAME800DD978: 800DA778,800DA7A0,800DA7E4,800DA91C,800DB130", "spawn_states": "GAME800DD98C: 800DAB94,800DACF4,800DB108", "despawn_check": "GAME800DB1D0/800DB59C", "tile_check": "GAME800DB85C/800DB924", "tables_ram": hex(0x800F0200), "enemy_callback": "ST0DT800E8FC4", "enemy_constructor": "ST0DT800E9228", "enemy_rise": "ST0DT800E94B8", "enemy_leave": "ST0DT800EB03C"},
		"roll_gate": gate, "tile_shift": 9, "step_thresholds": list(game[game_offset(0x800DD998):game_offset(0x800DD998) + 8]), "chance_words": [word(game, game_offset(0x800DD9A0 + index * 4)) for index in range(16)], "delay_words": [word(game, game_offset(0x800DD9C0 + index * 4)) for index in range(8)], "base_maximum": 6,
		"zone_selector": list(overlay[offset(tables[2]):offset(tables[2]) + 32]), "zones": zones, "node_selectors": selectors, "node_sets": node_sets, "templates": [template.hex() for template in templates], "tile_grids": grids,
		"enemy": {"stage": "ST0D", "actor_class": raw[4], "dispatch_index": raw[6], "actor_resource_key": raw[7], "model_index": index, "model_file": model_file, "source_bytes_hex": raw.hex(), "combat": combat, "source_attributes": combat["normal"]["attributes"], "native_hitbox": {"bounds_raw": bounds}, "startup_control": {"code": 0}, "transform": {"position": [0.0, 0.0, 0.0], "yaw_raw": 0}, "instance_id": -1, "script_area_index": 0, "flags": 0, "flags2": 0},
		"rules": {"rise_depth_raw": 180, "rise_step_raw": 12, "rise_dust_interval": 3, "rise_sound": 0xA3, "leave_sound": 0xA4, "leave_step_raw": 16, "leave_distance_raw": 0x600, "leave_ticks": 30, "attack_gate_slot": overlay[offset(0x800F0BF4 + (raw[6] & 15))], "attack_gate_table": hex(0x800F0214), "attack_distance_raw": 0x2BC, "offscreen_x_limit": 0x140, "offscreen_y_limit": 0xF0, "onscreen_despawn_distance_squared": 0x0A900000}}
