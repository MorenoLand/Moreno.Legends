from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys
import subprocess
import argparse
ROOT = Path(__file__).resolve().parents[1]
SPRITES = {
 "health_frame": {"file": "health_frame.png", "tpage": 13, "clut": 0x7fd0, "uv": (0, 180, 32, 16), "semantic_verified": False, "evidence": "GAME.BIN page 13 meter artwork; gameplay HUD placement and role are not verified."},
 "health_fill": {"file": "health_fill.png", "tpage": 13, "clut": 0x7fd0, "uv": (12, 182, 20, 8), "semantic_verified": False, "evidence": "Interior crop from the same GAME.BIN page 13 meter artwork; this is not a separately referenced runtime sprite."},
 "buster": {"file": "buster_icon_candidate.png", "tpage": 13, "clut": 0x7fd3, "uv": (0xb8, 0x88, 0x18, 0x18), "semantic_verified": False, "evidence": "GAME.BIN overlay selects this 24x24 icon at 0x800BBB24-0x800BBB9C with four UV orientations; its Buster role is unverified."},
 "projectile": {"file": "projectile_orb.png", "tpage": 15, "clut": 0x7f91, "uv": (0, 32, 32, 32), "semantic_verified": False, "evidence": "Cyan orb crop from the original GAME.BIN effects atlas; exact buster-projectile use is unverified."},
 "impact": {"file": "impact_burst.png", "tpage": 15, "clut": 0x7f91, "uv": (0, 64, 32, 32), "semantic_verified": False, "evidence": "Cyan burst crop from the original GAME.BIN effects atlas; exact buster-impact use is unverified."},
 "life_meter": {"file": "life_meter.png", "tpage": 13, "clut": 0x7fd0, "uv": (216, 112, 40, 64), "semantic_verified": False, "evidence": "Status-menu LIFE artwork; it is not the gameplay gauge."},
 "life_warning_eye": {"file": "life_warning_eye.png", "tpage": 13, "clut": 0x7fd0, "uv": (0, 144, 32, 32), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-0 descriptor 0; native draw packet at 0x800BD9E8, x=anchor, y=196."},
 "life_pupil_frames": {"file": "life_pupil_frames.png", "tpage": 13, "clut": 0x7fd0, "uv": (0, 128, 96, 16), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-0 descriptor 1 selects one of six 16x16 animation frames; native capture selects U=32."},
 "life_tube_piece_a": {"file": "life_tube_piece_a.png", "tpage": 13, "clut": 0x7fd0, "uv": (56, 144, 24, 24), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-0 descriptor 2; cumulative draw position x=anchor+4, y=172."},
 "life_tube_piece_b": {"file": "life_tube_piece_b.png", "tpage": 13, "clut": 0x7fd0, "uv": (32, 144, 24, 24), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-0 descriptor 4; cumulative draw position x=anchor+4, y=117."},
 "life_tube_stretch": {"file": "life_tube_stretch.png", "tpage": 13, "clut": 0x7fd0, "uv": (80, 144, 16, 1), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-0 descriptor 3 uses GP0 0x2C with semitransparency disabled; native packet stretches this 16x1 source row from (14,141) to (30,172)."},
 "lifter_piece_a": {"file": "lifter_piece_a.png", "tpage": 13, "clut": 0x7fd0, "uv": (120, 144, 16, 16), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-1 HUD descriptor 5; 0x800BC8DC can switch this descriptor to a state-specific UV."},
 "lifter_piece_b": {"file": "lifter_piece_b.png", "tpage": 13, "clut": 0x7fd0, "uv": (120, 128, 16, 16), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-1 HUD descriptor 6; 0x800BC8DC can switch this descriptor to a state-specific UV."},
 "lifter_piece_c": {"file": "lifter_piece_c.png", "tpage": 13, "clut": 0x7fd0, "uv": (80, 168, 32, 24), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-1 HUD descriptor 7, updated by 0x800BC8DC."},
 "special_piece_a": {"file": "special_piece_a.png", "tpage": 13, "clut": 0x7fd0, "uv": (96, 128, 24, 24), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-2 HUD descriptor 8, drawn by 0x800BCB90; runtime CLUT is read from the type-2 state record."},
 "special_piece_b": {"file": "special_piece_b.png", "tpage": 13, "clut": 0x7fd0, "uv": (104, 160, 16, 8), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-2 HUD descriptor 9, drawn by 0x800BCB90; runtime CLUT is read from the type-2 state record."},
 "special_piece_c": {"file": "special_piece_c.png", "tpage": 13, "clut": 0x7fd0, "uv": (80, 152, 24, 16), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN type-2 HUD descriptor 11, drawn by 0x800BCB90; runtime CLUT is read from the type-2 state record."},
 "special_tube_stretch": {"file": "special_tube_stretch.png", "tpage": 13, "clut": 0x7fd0, "uv": (104, 152, 16, 1), "opaque": True, "semantic_verified": True, "evidence": "GAME.BIN Special HUD path uses this 16x1 palette row as the source for its stretched meter."},
}

GAUGES = {
 "coordinate_space": {"resolution": [320, 240], "reference_capture": [960, 720], "scale": 3},
 "life": {"draw_function": "0x800BC5E8", "update_function": "0x800BC364", "record": {"address": "0x800E0BD8", "callback_index": 0, "type": 0, "initial_anchor": [-38, 228], "steady_anchor_x": 6}, "player_state": {"pointer": "0x8008C0A0", "max_hp_offset": "0x72", "current_hp_offset": "0x70"}, "bar": {"x": [19, 25], "bottom_y": 179, "max_height": "max(0,floor(max_hp*5/16)-1)", "target_fill_height": "min(ceil(current_hp*5/16),max_height)", "delayed_fill_height": "record+0x14", "tick_start_y": 174, "tick_step_y": -5, "tick_rate": "one tick per 16 max HP"}, "native_trace_example": {"max_hp": 160, "current_hp": 160, "tube_height": 49, "target_fill": 49, "fill_rect": [19, 130, 25, 179]}, "colors": [{"gp0": "0x2800528C", "rgb": [140, 82, 0], "role": "damage trail"}, {"gp0": "0x284A8AD6", "rgb": [214, 138, 74], "role": "gold fill"}, {"gp0": "0x2863DEFF", "rgb": [255, 222, 99], "role": "highlight"}, {"gp0": "0x40606030", "rgb": [48, 96, 96], "role": "ticks"}], "reference_bounds_inclusive": {"tube": [14, 118, 30, 194], "warning_eye": [8, 198, 34, 226]}, "sprites": {"warning_eye": "life_warning_eye", "pupil_frames": "life_pupil_frames", "tube_piece_a": "life_tube_piece_a", "tube_piece_b": "life_tube_piece_b", "tube_stretch": "life_tube_stretch"}, "source_descriptors": [{"id": 0, "uv": [0, 144, 32, 32], "draw_xy": [6, 196]}, {"id": 1, "uv_strip": [0, 128, 96, 16], "selected_u": 32, "draw_xy": [14, 205]}, {"id": 2, "uv": [56, 144, 24, 24], "draw_xy": [10, 172]}, {"id": 3, "uv": [80, 144, 16, 1], "draw_rect": [14, 141, 30, 172]}, {"id": 4, "uv": [32, 144, 24, 24], "draw_xy": [10, 117]}], "normal_clut": "0x7FD0", "alternate_clut": "0x7FD2"},
 "lifter": {"draw_function": "0x800BCA88", "update_function": "0x800BC8DC", "record": {"address": "0x800E0BF4", "callback_index": 1, "type": 1, "initial_anchor": [314, 214]}, "reference_bounds_inclusive": [284, 124, 300, 214], "sprites": ["lifter_piece_a", "lifter_piece_b", "lifter_piece_c"], "source_descriptors": [{"id": 5, "uv": [120, 144, 16, 16], "offset": [0, 16], "draw_y": 198}, {"id": 6, "uv": [120, 128, 16, 16], "offset": [0, 16], "draw_y": 198}, {"id": 7, "uv": [80, 168, 32, 24], "offset": [-8, 24], "draw_y": 190}], "normal_clut": "0x7FD0", "alternate_clut": "0x7FD2", "notes": ["Update code rewrites descriptor UVs and CLUT from player equipment state."]},
 "special": {"draw_function": "0x800BCB90", "update_function": "0x800BCAF0", "record": {"address": "0x800E0C10", "callback_index": 2, "type": 2, "initial_anchor": [314, 228]}, "player_state_offsets": ["0x190", "0x192", "0x194", "0x198", "0x19A"], "reference_bounds_inclusive": [284, 124, 300, 214], "sprites": ["special_piece_a", "special_piece_b", "special_piece_c", "special_tube_stretch"], "source_descriptors": [{"id": 8, "uv": [96, 128, 24, 24]}, {"id": 9, "uv": [104, 160, 16, 8]}, {"id": 10, "stretch_uv": [104, 152, 16, 1]}, {"id": 11, "uv": [80, 152, 24, 16]}], "runtime_clut": "record+0x0E is loaded from the type-2 CLUT lookup table", "gpu_color_words": ["0x28008000", "0x2830F020", "0x2810B010", "0x28C03010", "0x28F08040"]}
}

def color(word, opaque=False): return (((word & 31) * 255 + 15) // 31, (((word >> 5) & 31) * 255 + 15) // 31, (((word >> 10) & 31) * 255 + 15) // 31, 0 if word == 0 else (255 if opaque or not word & 0x8000 else 128))

def decode_page(vram, tpage, clut, opaque=False):
	depth = (tpage >> 7) & 3
	if depth != 0: raise ValueError(f"unsupported HUD texture depth {depth:#x}")
	x = (tpage & 15) * 64; y = ((tpage >> 4) & 1) * 256; pixels = bytearray(256 * 256 * 4)
	for v in range(256):
		for u in range(256):
			word = read_u16(vram, ((y + v) * 1024 + x + (u >> 2)) * 2); index = (word >> ((u & 3) * 4)) & 15; palette = read_u16(vram, ((clut >> 6) * 1024 + (clut & 63) * 16 + index) * 2); offset = (v * 256 + u) * 4; pixels[offset:offset + 4] = bytes(color(palette, opaque))
	return pixels

def hud_crop(pixels, x, y, width, height):
	return b"".join(pixels[((y + row) * 256 + x) * 4:((y + row) * 256 + x + width) * 4] for row in range(height))

def glyph(char):
	return {"0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7), "3": (7, 1, 7, 1, 7), "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7), "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 1, 1), "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7), "a": (2, 5, 7, 5, 5), "c": (7, 4, 4, 4, 7), "e": (7, 4, 6, 4, 7), "g": (7, 5, 7, 1, 7), "i": (7, 2, 2, 2, 7), "l": (4, 4, 4, 4, 7), "p": (6, 5, 6, 4, 4), "t": (7, 2, 2, 2, 2), "u": (5, 5, 5, 5, 7), "x": (5, 2, 2, 2, 5), " ": (0, 0, 0, 0, 0)}.get(char.lower(), (0, 0, 0, 0, 0))

def draw_text(pixels, width, height, x, y, text):
	for char in text:
		for row, bits in enumerate(glyph(char)):
			for col in range(3):
				offset = ((y + row) * width + x + col) * 4; pixels[offset:offset + 4] = bytes((255, 255, 255, 255) if bits & (1 << (2 - col)) else (0, 0, 0, 255))
		x += 4

def contact_sheet(vram, pages, clut, destination):
	margin = 16; title = 14; width = len(pages) * 256 + (len(pages) - 1) * margin; height = title + 256; pixels = bytearray(width * height * 4)
	for column, page in enumerate(pages):
		x0 = column * (256 + margin); draw_text(pixels, width, height, x0 + 2, 2, f"page {page:02x} clut {clut:04x}"); page_pixels = decode_page(vram, page, clut)
		for y in range(256):
			for x in range(256):
				offset = ((title + y) * width + x0 + x) * 4; source = (y * 256 + x) * 4
				if x % 16 == 0 or y % 16 == 0: pixels[offset:offset + 4] = bytes((255, 32, 32, 255))
				else: pixels[offset:offset + 4] = page_pixels[source:source + 4]
				if x % 32 == 0 and y < 8: draw_text(pixels, width, height, x0 + x + 1, title + 1, str(x))
				if y % 32 == 0 and x < 8: draw_text(pixels, width, height, x0 + 1, title + y + 1, str(y))
	destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(png(width, height, pixels))

def hud_cli():
	input_path = ROOT / "build/disc-assets/COMMON/GAME.BIN"; output_dir = ROOT / "assets/hud"; contact_dir = ROOT / "build/maps"; output_dir.mkdir(parents=True, exist_ok=True); vram, loaded = textures(input_path); pages = {}; entries = {}
	sprites = dict(SPRITES)
	for name, spec in SPRITES.items():
		if name.startswith("life_") and spec["semantic_verified"]: sprites[name + "_alert"] = {**spec, "file": name + "_alert.png", "clut": 0x7fd2, "evidence": "GAME 0x800BC430 threat warning selects native CLUT 0x7FD2."}
	for name, spec in sprites.items():
		opaque = spec.get("opaque", False); key = (spec["tpage"], spec["clut"], opaque); pages.setdefault(key, decode_page(vram, key[0], key[1], opaque)); x, y, width, height = spec["uv"]; file_path = output_dir / spec["file"]; file_path.write_bytes(png(width, height, hud_crop(pages[key], x, y, width, height))); entries[name] = {"file": spec["file"], "dimensions": [width, height], "source": {"archive": "COMMON/GAME.BIN", "tpage": f"0x{spec['tpage']:02X}", "clut": f"0x{spec['clut']:04X}", "uv": [x, y, width, height]}, "alpha_mode": "zero palette word transparent; nonzero opaque" if opaque else "STP bit uses half alpha", "semantic_verified": spec["semantic_verified"], "evidence": spec["evidence"]}
	contact_sheet(vram, [13, 14, 15], 0x7c10, contact_dir / "HUD_GAME_tpages13-15_grid_exported.png"); contact_sheet(vram, [13], 0x7fd0, contact_dir / "HUD_GAME_UI_page13_clut7fd0_exported.png"); contact_sheet(vram, [14, 15], 0x7f91, contact_dir / "HUD_GAME_effects_page14-15_clut7f91_exported.png"); manifest = {"source": {"archive": "COMMON/GAME.BIN", "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "loaded_texture_sections": loaded}, "sprites": entries, "gauges": GAUGES, "notes": ["Verified GP0 0x64/0x2C HUD sprites use index-zero transparency and opaque nonzero texels; unverified effect crops retain STP half-alpha preview behavior.", "Native 320x240 coordinates are recorded from the supplied 3x gameplay capture and executed GAME.BIN MIPS packets."]}; (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"Exported {len(entries)} sprite crops from {loaded} GAME.BIN texture sections to {output_dir}")

SOURCE = ROOT / "build" / "disc-assets" / "COMMON" / "GAME.BIN"
PROJECTILE_OUTPUT = ROOT / "assets" / "effects"


def export_projectile():
	vram, sections = textures(SOURCE)
	page = decode_page(vram, 0x0F, 0x7C92, False)
	pixels = crop(page, 0, 32, 32, 32)
	additive = bytearray(pixels)
	for offset in range(3, len(additive), 4): additive[offset] = 255 if additive[offset] else 0
	PROJECTILE_OUTPUT.mkdir(parents=True, exist_ok=True)
	source = SOURCE.read_bytes()
	stats_pointer = struct.unpack_from("<I", source, 0x30 + 0x800DCCC8 - 0x800AD000)[0]
	stats_offset = 0x30 + stats_pointer - 0x800AD000
	stat_rows = [list(struct.unpack_from("<4h", source, stats_offset + level * 8)) for level in range(8)]
	controller_offset = 0x30 + 0x800DC978 - 0x800AD000 + 2 * 8
	controller = list(source[controller_offset:controller_offset + 8])
	(PROJECTILE_OUTPUT / "buster_projectile.png").write_bytes(png(32, 32, pixels))
	(PROJECTILE_OUTPUT / "buster_projectile_add.png").write_bytes(png(32, 32, additive))
	manifest = {"source": "COMMON/GAME.BIN 0x800D0A04", "textures": {"normal": "buster_projectile.png", "additive": "buster_projectile_add.png", "tpage_normal": "0x000F", "tpage_additive": "0x002F", "clut": "0x7C92", "uv": [0, 32, 32, 32], "page_decode_tpage": "0x000F", "alpha": "CLUT STP bit from VRAM"}, "geometry": {"billboards": 2, "width_raw": "0x20 + (source_level * 8)", "world_unit_raw": 256, "rotation": "(source_frame << 7) & 0xFFF"}, "source_color_table": {"address": "0x800DCD70", "index": "source_level >> 1", "new_game_source_level": 0, "new_game_source": "GAME.BIN 0x800C35B0(a0=0), 0x800C3688-0x800C36A8 clears all weapon-stat rows; normal difficulty branches preserve zero Buster levels", "temporary_preset_level": 2, "temporary_preset_source": "0x800B09D0 backs up current stats and installs level two; 0x800B0A8C restores the backup", "rgb": [[255, 32, 32], [32, 192, 32], [160, 160, 32], [32, 32, 255], [240, 255, 16], [248, 255, 8], [240, 255, 16]]}, "buster_stats": {"address": hex(stats_pointer), "columns": ["damage", "maximum_shots", "lifetime_ticks", "rapid_delay_ticks"], "rows": stat_rows, "new_game_indices": [0, 0, 0, 0], "source": "0x800CF3B8/0x800CF40C/0x800CF440/0x800CF474 index separate attack/energy/range/rapid levels"}, "buster_controller": {"address": hex(0x800DC978 + 2 * 8), "bytes": controller, "repeat_pose": "controller[1] + rapid_delay_ticks", "base_repeat_ticks": controller[1] + stat_rows[0][3], "source": "GAME 0x800CF0E8-0x800CF16C schedules held-fire restart at the rapid threshold, without waiting for marker thirteen", "animation_restart_pose": controller[0], "runtime_tick_rate": 30}, "source_sections": sections}
	(PROJECTILE_OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest

MENU_OUTPUT = ROOT / "assets/menu"
DIALOGUE_OUTPUT = ROOT / "assets/dialogue"
def rgba(vram, x, y, width, height, depth, palette_x, palette_y):
	pixels = bytearray()
	for row in range(height):
		for column in range(width):
			if depth == 8: index = vram[((y + row) * 1024 + x) * 2 + column]
			else:
				word = struct.unpack_from("<H", vram, ((y + row) * 1024 + x + column // 4) * 2)[0]; index = (word >> ((column & 3) * 4)) & 15
			color = struct.unpack_from("<H", vram, (palette_y * 1024 + palette_x + index) * 2)[0]; pixels.extend((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 0 if color == 0 else 255))
	return pixels
def menu_crop(pixels, atlas_width, rectangle):
	x, y, width, height = rectangle
	return b"".join(pixels[((y + row) * atlas_width + x) * 4:((y + row) * atlas_width + x + width) * 4] for row in range(height))
def selected_title_label(vram, rectangle):
	width, height = rectangle[2:]; letters = menu_crop(rgba(vram, 704, 0, 256, 256, 4, 0, 496), 256, rectangle); selected = bytearray(width * height * 4); shades = {}
	for index in (3, 5):
		color = struct.unpack_from("<H", vram, (496 * 1024 + index) * 2)[0]; shades[index] = bytes((((color & 31) * 255 + 15) // 31, (((color >> 5) & 31) * 255 + 15) // 31, (((color >> 10) & 31) * 255 + 15) // 31, 255))
	for y in range(height):
		for x in range(width):
			if not letters[(y * width + x) * 4 + 3]: continue
			for dy in range(4):
				for dx in (-1, 0, 1):
					px, py = x + dx, y + dy - 1
					if 0 <= px < width and 0 <= py < height: selected[(py * width + px) * 4:(py * width + px + 1) * 4] = shades[3 if dy == 0 else 5]
	for y in range(1, height):
		for x in range(width):
			offset = (y * width + x) * 4
			if letters[offset + 3]: selected[((y - 1) * width + x) * 4:((y - 1) * width + x + 1) * 4] = letters[offset:offset + 4]
	return selected
def options_roles(exe, primitives):
	def indices(x, y, u=None): return [index for index, item in enumerate(primitives) if item.get("opcode") == "0x64" and item.get("xy") == [x, y] and (u is None or item.get("uv", [None])[0] == u)]
	bindings = [("controller", 0x4C, ["A", "B", "C", "Select"], [(136, 38), (160, 38), (184, 38), (232, 38)]), ("view", 0x4E, ["Reverse", "Normal"], [(136, 56), (232, 56)]), ("buster_lock_on", 0x51, ["Man.", "Auto"], [(136, 74), (160, 74)]), ("special_lock_on", 0x50, ["Man.", "Auto"], [(232, 74), (256, 74)]), ("vibration", 0x4F, ["ON", "OFF"], [(136, 92), (232, 92)]), ("sound", 0x48, ["Stereo", "Monaural"], [(136, 110), (232, 110)])]
	roles = {role: {"state_address": hex(0x8009C7E8 + offset), "state_offset": hex(offset), "default": 0, "choices": [{"value": value, "label": label, "primitive_indices": indices(*position)} for value, (label, position) in enumerate(zip(labels, positions))]} for role, offset, labels, positions in bindings}
	for role, address, x in (("bgm_volume", 0x8007CFB1, 120), ("se_volume", 0x8007CFB0, 216)): roles[role] = {"state_address": hex(address), "minimum": 0, "maximum": 127, "default": 127, "bar_background_indices": indices(x, 128, 0), "bar_fill_indices": indices(x, 128, 64), "fill_width_expression": "8+3*((volume+7)>>3)", "native_renderer": "SUBSCN 0x801E08AC..0x801E0928"}
	schemes = {}
	for index, name in enumerate(("A", "B", "C", "A_mode7", "B_mode7", "C_mode7")):
		masks = struct.unpack_from("<16H", exe, 0x8006B494 - 0x80010000 + 0x800 + index * 32); schemes[name] = {"native_profile_index": index, "player_field_masks": {hex(0x11C + offset * 2): hex(mask) for offset, mask in enumerate(masks)}}
	return {"bindings": roles, "controller_schemes": schemes, "controller_source": "SLES 0x80046F70 copies original table 0x8006B494 into player+0x11C..0x13A", "controller_mode7": "Save+0x4D, profile_index=value+3; other modes use save+0x4C", "default_source": "SUBSCN 0x801E0308..0x801E0380", "palettes": {"selected_choice": "0x7F50", "other_choice": "0x7F51", "selected_label": "0x7F13", "other_label": "0x7F12"}}
def native_options_geometry():
	sys.path.insert(0, str(ROOT / "build/pydeps"))
	try: import unicorn
	except ImportError:
		subprocess.run([sys.executable, "-m", "pip", "install", "--target", str(ROOT / "build/pydeps"), "--no-cache-dir", "unicorn==2.1.4"], check=True); import unicorn
	from unicorn.mips_const import UC_MIPS_REG_SP, UC_MIPS_REG_GP, UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_RA
	emulator = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); emulator.mem_map(0, 0x200000); emulator.mem_map(0x1F800000, 0x2000); emulator.mem_write(0x10000, (ROOT / "build/disc-assets/SLES_035.56").read_bytes()[0x800:]); emulator.mem_write(0xAD000, (ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes()[0x30:]); emulator.mem_write(0x1D6800, (ROOT / "build/disc-assets/COMMON/SUBSCN.BIN").read_bytes()[0x2A830:]); gpu = 0x80180000; emulator.mem_write(0x1F80004C, struct.pack("<I", gpu)); emulator.mem_write(0x78DDC, struct.pack("<I", 0x80190000)); node = 0x801A0000; emulator.mem_write((node + 0x14) & 0x1FFFFFFF, b"\x06\x06"); emulator.reg_write(UC_MIPS_REG_GP, 0x80080000 - 0x76F4); emulator.reg_write(UC_MIPS_REG_SP, 0x801FF000)
	for function, argument in ((0x801E03CC, 0), (0x801D8960, 3)):
		emulator.reg_write(UC_MIPS_REG_A0, node); emulator.reg_write(UC_MIPS_REG_A1, argument); emulator.reg_write(UC_MIPS_REG_RA, 0x80000800); emulator.emu_start(function, 0x80000800, count=500000)
		if emulator.reg_read(unicorn.mips_const.UC_MIPS_REG_PC) != 0x80000800: raise ValueError("Native Options renderer did not return")
	end = struct.unpack("<I", emulator.mem_read(0x1F80004C, 4))[0]; pointer = gpu; primitives = []; page = 0
	while pointer < end:
		count = struct.unpack("<I", emulator.mem_read(pointer & 0x1FFFFFFF, 4))[0] >> 24
		if not 0 < count <= 16: raise ValueError("Invalid native menu GPU packet")
		words = struct.unpack("<" + "I" * count, emulator.mem_read((pointer + 4) & 0x1FFFFFFF, count * 4)); opcode = words[0] >> 24; record = {"opcode": hex(opcode), "words": [hex(word) for word in words]}
		if opcode == 0xE1: page = words[0] & 0x1FF
		if opcode == 0x64: record.update(xy=[words[1] & 65535, words[1] >> 16], uv=[words[2] & 255, (words[2] >> 8) & 255], clut=hex(words[2] >> 16), size=[words[3] & 65535, words[3] >> 16], tpage=hex(page))
		elif opcode == 0x2C: record.update(xy=[[words[i] & 65535, words[i] >> 16] for i in (1, 3, 5, 7)], uv=[[words[i] & 255, (words[i] >> 8) & 255] for i in (2, 4, 6, 8)], clut=hex(words[2] >> 16), tpage=hex(words[4] >> 16))
		primitives.append(record); pointer += 4 + count * 4
	return {"viewport": [320, 240], "source": "Original SUBSCN 0x801E03CC and 0x801D8960(node,3), executed unchanged in Unicorn", "fixture": {"selected_item": 6, "saved_options_zero": True}, "primitives": primitives, "roles": options_roles((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), primitives), "main_frame": [16, 31, 288, 122], "left_frame": [16, 32, 64, 174], "help_frame": [88, 153, 216, 64], "title": [112, 16, 96, 16], "row_y": [38 + index * 18 for index in range(9)], "label_x": 19, "value_columns_x": [136, 160, 184, 232, 256]}
def native_load_game_geometry():
	sys.path.insert(0, str(ROOT / "build/pydeps")); import unicorn
	from unicorn.mips_const import UC_MIPS_REG_SP, UC_MIPS_REG_GP, UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_RA, UC_MIPS_REG_PC
	emulator = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); emulator.mem_map(0, 0x200000); emulator.mem_map(0x1F800000, 0x2000); emulator.mem_write(0x10000, (ROOT / "build/disc-assets/SLES_035.56").read_bytes()[0x800:]); emulator.mem_write(0xAD000, (ROOT / "build/disc-assets/COMMON/DEMO.BIN").read_bytes()[0x30:]); emulator.mem_write(0x1F80004C, struct.pack("<I", 0x80180000)); emulator.mem_write(0x78DDC, struct.pack("<I", 0x80190000)); emulator.reg_write(UC_MIPS_REG_SP, 0x801FF000); emulator.reg_write(UC_MIPS_REG_GP, 0x8007890C)
	def call(function, arguments=()):
		for register, argument in zip((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2), arguments): emulator.reg_write(register, argument)
		emulator.reg_write(UC_MIPS_REG_RA, 0x80000800); emulator.emu_start(function, 0x80000800, count=500000)
		if emulator.reg_read(UC_MIPS_REG_PC) != 0x80000800: raise ValueError("Native Load Game renderer did not return")
	for slot, index in ((1, 6), (4, 0), (3, 4)): call(0x80048474, (slot, 0x800B116C, index))
	for _ in range(12): call(0x800490D8)
	windows = {}
	for role, slot, index in (("header", 1, 6), ("prompt", 4, 0), ("selector", 3, 4)):
		context = 0x8009F5B0 + slot * 128; body = list(struct.unpack("<4H", emulator.mem_read((context + 0x54) & 0x1FFFFFFF, 8))); text_position = list(struct.unpack("<2H", emulator.mem_read((context + 8) & 0x1FFFFFFF, 4))); start = struct.unpack("<I", emulator.mem_read(0x1F80004C, 4))[0]; call(0x80049F00, (context,)); end = struct.unpack("<I", emulator.mem_read(0x1F80004C, 4))[0]; pointer = start; primitives = []
		while pointer < end:
			count = struct.unpack("<I", emulator.mem_read(pointer & 0x1FFFFFFF, 4))[0] >> 24
			if not 0 < count <= 16: raise ValueError("Invalid native Load Game GPU packet")
			words = struct.unpack("<" + "I" * count, emulator.mem_read((pointer + 4) & 0x1FFFFFFF, count * 4)); primitives.append({"opcode": hex(words[0] >> 24), "words": [hex(word) for word in words]}); pointer += 4 + count * 4
		windows[role] = {"message_index": index, "context": hex(context), "body_rect": body, "text_position": text_position, "frame_style": emulator.mem_read((context + 0x4C) & 0x1FFFFFFF, 1)[0] >> 4, "frame_primitives": primitives}
	return {"viewport": [320, 240], "source": "COMMON/DEMO.BIN message bank RAM0x800B116C/file0x419C; original SLES0x80048474/0x800490D8/0x80049F00 executed unchanged", "header_text": "Load Game", "prompt_text": "Please select a MEMORY CARD slot:", "selector_text": ["MEMORY CARD slot 1", "MEMORY CARD slot 2", "Cancel"], "frame_renderer": "SLES0x8004A4C4", "frame_colors": [list(emulator.mem_read(0x78C18 + index * 4, 3)) for index in range(3)], "fixture": {"update_count": 12, "input": 0, "selector": 0}, "windows": windows}

def export_menu():
	MENU_OUTPUT.mkdir(parents=True, exist_ok=True); title = ROOT / "build/disc-assets/COMMON/TITLE.BIN"; vram, section_count = textures(title); sprites = {}
	logo = rgba(vram, 640, 256, 544, 240, 8, 0, 503); (MENU_OUTPUT / "title_logo.png").write_bytes(png(544, 240, logo)); sprites["title_logo"] = {"file": "title_logo.png", "dimensions": [544, 240], "source": {"archive": "COMMON/TITLE.BIN", "sections": ["0x5800", "0x7800", "0xB000", "0xF000"], "vram_words": [640, 256, 272, 240], "palette": [0, 503], "bits": 8}}
	(MENU_OUTPUT / "native_gear_background.png").write_bytes(png(64, 64, rgba(vram, 844, 32, 64, 64, 4, 288, 510))); sprites["native_gear_background"] = {"file": "native_gear_background.png", "dimensions": [64, 64], "source": {"archive": "COMMON/TITLE.BIN", "tpage": 13, "clut": 0x7F92, "uv": [48, 32, 64, 64], "renderer": "SLES0x80050C20"}}
	for language, word_x, palette_y in [("training", 640, 496), ("tutorial", 704, 497)]:
		atlas = rgba(vram, word_x, 0, 256, 256, 4, 0, palette_y); name = f"title_{language}_atlas.png"; (MENU_OUTPUT / name).write_bytes(png(256, 256, atlas)); sprites[f"title_{language}_atlas"] = {"file": name, "dimensions": [256, 256], "source": {"archive": "COMMON/TITLE.BIN", "section": "0x11000" if language == "training" else "0x14000", "tpage": word_x // 64, "clut": palette_y * 64}}
		for index, role in enumerate(("game_start", "continue", "tutorial", "options")):
			rectangle = [0, index * 40, 216, 40]; name = f"title_{language}_{role}.png"; (MENU_OUTPUT / name).write_bytes(png(216, 40, menu_crop(atlas, 256, rectangle))); sprites[f"title_{language}_{role}"] = {"file": name, "dimensions": [216, 40], "source": {"archive": "COMMON/TITLE.BIN", "tpage": word_x // 64, "clut": palette_y * 64, "uv": rectangle}}
	(MENU_OUTPUT / "title_tutorial_tutorial_selected.png").write_bytes(png(216, 40, selected_title_label(vram, [0, 80, 216, 40]))); sprites["title_tutorial_tutorial_selected"] = {"file": "title_tutorial_tutorial_selected.png", "dimensions": [216, 40], "source": {"archive": "COMMON/TITLE.BIN", "tpage": 11, "clut": 0x7C00, "uv": [0, 80, 216, 40], "selected_outline_palette_indices": [3, 5]}, "adaptation": "Original TUTORIAL letter mask, original selected-label palette, and cyan extrusion; the title keeps the same word when selected"}
	prompt_atlas = rgba(vram, 704, 0, 256, 256, 4, 16, 497); prompt = bytearray(360 * 40 * 4)
	for destination_x, rectangle in ((0, [0, 176, 256, 40]), (256, [0, 216, 104, 40])):
		part = menu_crop(prompt_atlas, 256, rectangle)
		for row in range(40): prompt[(row * 360 + destination_x) * 4:(row * 360 + destination_x + rectangle[2]) * 4] = part[row * rectangle[2] * 4:(row + 1) * rectangle[2] * 4]
	(MENU_OUTPUT / "title_press_start.png").write_bytes(png(360, 40, prompt)); sprites["title_press_start"] = {"file": "title_press_start.png", "dimensions": [360, 40], "native_rect": [140, 336, 360, 40], "source": {"archive": "COMMON/TITLE.BIN", "tpage": 11, "clut": 0x7C41, "uv_parts": [[0, 176, 256, 40], [0, 216, 104, 40]], "renderer": "DEMO 0x800AE3A0"}}
	copyright_atlas = rgba(vram, 640, 0, 256, 256, 4, 32, 496); copyright_pixels = bytearray(512 * 48 * 4)
	for destination_x, destination_y, rectangle in ((0, 0, [0, 176, 256, 48]), (256, 12, [0, 224, 256, 32])):
		part = menu_crop(copyright_atlas, 256, rectangle)
		for row in range(rectangle[3]): copyright_pixels[((row + destination_y) * 512 + destination_x) * 4:((row + destination_y) * 512 + destination_x + rectangle[2]) * 4] = part[row * rectangle[2] * 4:(row + 1) * rectangle[2] * 4]
	(MENU_OUTPUT / "title_copyright.png").write_bytes(png(512, 48, copyright_pixels)); sprites["title_copyright"] = {"file": "title_copyright.png", "dimensions": [512, 48], "native_rect": [64, 404, 512, 48], "source": {"archive": "COMMON/TITLE.BIN", "tpage": 10, "clut": 0x7C02, "renderer": "DEMO 0x800AE3A0"}}
	logo_archive = ROOT / "build/disc-assets/COMMON/LOGO.BIN"; logo_vram, _ = textures(logo_archive); (MENU_OUTPUT / "startup_capcom.png").write_bytes(png(544, 96, rgba(logo_vram, 640, 0, 544, 96, 4, 0, 496))); sprites["startup_capcom"] = {"file": "startup_capcom.png", "dimensions": [544, 96], "native_rect": [48, 192, 544, 96], "source": {"archive": "COMMON/LOGO.BIN", "tpage": 10, "clut": 0x7C00, "renderer": "SLES 0x800132F8"}}
	cursor_atlas = rgba(vram, 640, 0, 256, 256, 4, 16, 496); rectangle = [224, 0, 32, 32]; (MENU_OUTPUT / "title_cursor.png").write_bytes(png(32, 32, menu_crop(cursor_atlas, 256, rectangle))); sprites["title_cursor"] = {"file": "title_cursor.png", "dimensions": [32, 32], "source": {"archive": "COMMON/TITLE.BIN", "tpage": 10, "clut": 496 * 64 + 1, "uv": rectangle}}
	pause = ROOT / "build/disc-assets/COMMON/SUBSCN.BIN"; pause_data = pause.read_bytes(); pause_vram, _ = textures(pause)
	for role, section in [("map", 0), ("equipment", 0xD800), ("options", 0x18800), ("controller", 0x21000)]:
		_, _, _, _, x, y, width, height = struct.unpack_from("<8H", pause_data, section + 12); body = section + 0x800
		if struct.unpack_from("<I", pause_data, section + 4)[0] != width * height * 2 + 0x7D0: raise ValueError("Unexpected native sector-padded menu texture size")
		for row in range(height):
			start = ((y + row) * 1024 + x) * 2; pause_vram[start:start + width * 2] = pause_data[body + row * width * 2:body + (row + 1) * width * 2]
		for palette in range(4):
			name = f"pause_{role}_{palette}.png"; pixels = rgba(pause_vram, x, y, width * 4, height, 4, 256, 250 + palette); (MENU_OUTPUT / name).write_bytes(png(width * 4, height, pixels)); sprites[f"pause_{role}_{palette}"] = {"file": name, "dimensions": [width * 4, height], "source": {"archive": "COMMON/SUBSCN.BIN", "section": hex(section), "pixel_file_offset": hex(body), "tpage": x // 64 + (y // 256) * 16, "clut": (250 + palette) * 64 + 16}}
			if role == "options" and palette == 0:
				for panel, rectangle in [("native_menu_panel", [64, 16, 48, 48]), ("native_button_panel", [0, 16, 64, 48]), ("pause_sound_label", [0, 80, 48, 16]), ("pause_volume_label", [48, 80, 48, 16])]:
					name = panel + ".png"; (MENU_OUTPUT / name).write_bytes(png(rectangle[2], rectangle[3], menu_crop(pixels, 256, rectangle))); sprites[panel] = {"file": name, "dimensions": rectangle[2:], "source": {"archive": "COMMON/SUBSCN.BIN", "section": "0x18800", "tpage": 7, "clut": 250 * 64 + 16, "uv": rectangle}, "semantic_use": "Original menu artwork; PC placement differs from unresolved native placement"}
	options_vram = bytearray(vram)
	for row in range(256): options_vram[(row * 1024 + 448) * 2:(row * 1024 + 512) * 2] = pause_data[0x19000 + row * 128:0x19000 + (row + 1) * 128]
	for role, clut in (("frame", 0x7F12), ("help_frame", 0x7F10), ("labels", 0x7F90), ("selected_label", 0x7F13), ("selected_choice", 0x7F50), ("other_choice", 0x7F51), ("volume", 0x7F91)):
		name = f"options_{role}_atlas.png"; pixels = rgba(options_vram, 448, 0, 256, 256, 4, (clut & 63) * 16, clut >> 6); (MENU_OUTPUT / name).write_bytes(png(256, 256, pixels)); sprites[f"options_{role}_atlas"] = {"file": name, "dimensions": [256, 256], "source": {"archive": "COMMON/SUBSCN.BIN", "section": "0x18800", "tpage": 7, "clut": clut, "palette_archive": "COMMON/TITLE.BIN", "palette_section": "0x21800"}}
	init = ROOT / "build/disc-assets/COMMON/INIT.BIN"; init_data = init.read_bytes(); font_vram, _ = textures(init); _, _, _, _, x, y, width, height = struct.unpack_from("<8H", init_data, 12)
	for row in range(height):
		start = ((y + row) * 1024 + x) * 2; font_vram[start:start + width * 2] = init_data[0x800 + row * width * 2:0x800 + (row + 1) * width * 2]
	palette_x, palette_y, palette_width, palette_height = struct.unpack_from("<4H", init_data, 0x880C)
	for row in range(palette_height):
		start = ((palette_y + row) * 1024 + palette_x) * 2; font_vram[start:start + palette_width * 2] = init_data[0x8830 + row * palette_width * 2:0x8830 + (row + 1) * palette_width * 2]
	font = rgba(font_vram, x, y, 256, 256, 4, 960, 508); (MENU_OUTPUT / "font_atlas.png").write_bytes(png(256, 256, font)); sprites["font_atlas"] = {"file": "font_atlas.png", "dimensions": [256, 256], "source": {"archive": "COMMON/INIT.BIN", "section": "0x0", "pixel_file_offset": "0x800", "tpage": 31, "clut": 508 * 64 + 60}}
	(MENU_OUTPUT / "native_load_cursor.png").write_bytes(png(12, 12, menu_crop(font, 256, [192, 144, 12, 12]))); sprites["native_load_cursor"] = {"file": "native_load_cursor.png", "dimensions": [12, 12], "source": {"archive": "COMMON/INIT.BIN", "tpage": 31, "clut": 0x7F3C, "uv": [192, 144, 12, 12], "renderer": "SLES0x8004BC44..0x8004BD14", "branch": "window+0x20==0"}}
	exe = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); codes = {**{str(i): i for i in range(10)}, **{chr(65 + i): 20 + i for i in range(26)}, **{chr(97 + i): 46 + i for i in range(26)}, "'": 12, "/": 75, ",": 89, ".": 91, ":": 19}; glyphs = {}
	for char, code in codes.items():
		advance = exe[0x8006B8F8 - 0x80010000 + 0x800 + code]; y_offset = 1 if code in (52, 55, 89, 91) else (2 if code in (61, 62, 70) else 0); glyphs[char] = {"native_code": code, "uv": [(code % 20) * 12, (code // 20) * 12, advance, 12], "advance": advance, "y_offset": y_offset}
	font_lines = ['info face="Native Menu" size=12 bold=0 italic=0 charset="ASCII" unicode=1 stretchH=100 smooth=0 aa=1 padding=0,0,0,0 spacing=0,0', 'common lineHeight=12 base=12 scaleW=256 scaleH=256 pages=1 packed=0', 'page id=0 file="font_atlas.png"', f'chars count={len(glyphs) + 1}', 'char id=32 x=0 y=0 width=0 height=0 xoffset=0 yoffset=0 xadvance=6 page=0 chnl=15']
	for char, glyph in glyphs.items():
		x, y, width, height = glyph["uv"]; font_lines.append(f'char id={ord(char)} x={x} y={y} width={width} height={height} xoffset=0 yoffset={glyph['y_offset']} xadvance={glyph['advance']} page=0 chnl=15')
	background = bytearray()
	for row in range(480):
		fraction = max(0, min(224, row - 128)); rgb = tuple(start + (end - start) * fraction // 224 for start, end in zip((69, 71, 255), (207, 255, 255))); background.extend(bytes((*rgb, 255)) * 640)
	(MENU_OUTPUT / "title_background.png").write_bytes(png(640, 480, background))
	(MENU_OUTPUT / "native_font.fnt").write_text("\n".join(font_lines) + "\n", encoding="utf-8")
	manifest = {"sources": {"title": {"archive": "COMMON/TITLE.BIN", "sha256": hashlib.sha256(title.read_bytes()).hexdigest(), "texture_sections": section_count}, "pause": {"archive": "COMMON/SUBSCN.BIN", "sha256": hashlib.sha256(pause_data).hexdigest()}, "font": {"archive": "COMMON/INIT.BIN", "sha256": hashlib.sha256(init_data).hexdigest()}}, "sprites": sprites, "bitmap_font": {"atlas": "font_atlas", "glyphs": glyphs, "space_advance": 6, "native_space_code": 76, "native_width_table": "SLES 0x8006B8F8", "native_uv_formula": "u=(code%20)*12; v=(code//20)*12", "native_renderer": "SLES 0x800498CC", "cell_dimensions": [12, 12]}, "title_reference_layout": {"viewport": [640, 480], "logo_rect": [48, 32, 544, 240], "button_rects": [[212, 272 + index * 40, 216, 40] for index in range(4)], "cursor_rect": [172, 276, 32, 32], "provenance": "Native COMMON/DEMO.BIN functions 0x800AE0D0 and 0x800AE584", "selection_source": "selected page10/clut7C00; others page11/clut7C40", "cursor_animation": "x=172+(signed16(sine(counter<<8))/1024); y=276+40*currentSelection+10*(previousSelection-currentSelection)*transitionByte", "entry_order": ["game_start", "continue", "tutorial", "options"]}, "native_background": {"source": "COMMON/DEMO.BIN 0x800AE0D0, GP0 G4 construction 0x800AE164..0x800AE288", "file": "title_background.png", "viewport": [640, 480], "fade": 128, "rgb_scale": "channel*fade>>7", "top_rgb": [69, 71, 255], "bottom_rgb": [207, 255, 255], "quads": [{"y": [0, 128], "top_rgb": [69, 71, 255], "bottom_rgb": [69, 71, 255]}, {"y": [128, 352], "top_rgb": [69, 71, 255], "bottom_rgb": [207, 255, 255]}, {"y": [352, 480], "top_rgb": [207, 255, 255], "bottom_rgb": [207, 255, 255]}], "bitmap_in_logo": False, "rasterization": "Linear native G4 vertex-color interpolation; PS1 dithering not included"}, "alpha": "Native palette word zero is transparent; nonzero texels are opaque"}; demo = (ROOT / "build/disc-assets/COMMON/DEMO.BIN").read_bytes(); manifest["sources"]["title_overlay"] = {"archive": "COMMON/DEMO.BIN", "sha256": hashlib.sha256(demo).hexdigest(), "native_draw_functions": ["0x800AE0D0", "0x800AE584"]}; manifest["title_entries"] = [{"role": role, "normal_sprite": "title_tutorial_" + role, "selected_sprite": "title_tutorial_tutorial_selected" if role == "tutorial" else "title_training_" + role} for role in ("game_start", "continue", "tutorial", "options")]; manifest["options_layout"] = native_options_geometry(); manifest["press_start_phase"] = {"source": "DEMO 0x800AD308/0x800AE3A0", "prompt_rect": [140, 336, 360, 40], "copyright_rect": [64, 404, 512, 48], "fade_step": 2, "fade_max": 128, "fade_updates": 64, "blink_visible_expression": "(u16(titleState+4)&0x20)!=0", "blink_half_period_updates": 32, "idle_counter_expression": "(3-u8(0x1F800005))*256", "title_buffer_count": 1, "idle_updates": 512, "enter_menu_input_mask": "0x4008", "press_start_audio": "0x0081"}; manifest["startup_logo_phase"] = {"source": "SLES 0x80012D7C..0x80012F28", "resource": "COMMON/LOGO.BIN", "sprite": "startup_capcom", "fade_step": 4, "fade_max": 128, "fade_updates": 32, "hold_counter_initial": 180, "background_at_full_fade_rgb": [255, 255, 255], "next_engine_stage": "ST02", "trial_disclaimer_bitmap_used": False}; manifest["shared_menu_background"] = {"sprite": "native_gear_background", "viewport": [320, 240], "source": "SLES0x80050C20 called by0x80050AB0", "effective_tick": "u16(scratch+6)>>1 when u8(scratch+5)==1; otherwise u16(scratch+6)", "tile_origin_expression": "((effective_tick&63)-16,(effective_tick&63)-16), repeated every64pixels", "native_sprite_grid": [21, 16], "native_sprite_size": [16, 16]}; manifest["load_game_layout"] = native_load_game_geometry(); (MENU_OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
NATIVE_TEXT_CHARACTERS = {12: "'", 19: ":", 75: "/", 76: " ", 89: ",", 91: "."}
NATIVE_TEXT_CALLS = {
	"ST04": [{"address": "0x800E800C", "index": 0xC9, "state": "opens on state 0; waits through 0x800489A0"}, {"address": "0x800E80C4", "index": 0xCA, "state": "opens after the source timer reaches zero"}, {"address": "0x800E8154", "index": 0xCB, "state": "opens on state 0; continuation enters 0x800E7E58"}],
	"ST0F": [{"address": "0x800FB124", "index_source": "context+0x0C"}, {"address": "0x800FDB80", "index": 0x9B, "condition": "initial branch from 0x800FDB5C"}, {"address": "0x800FDB80", "index": 0x9C, "condition": "after poll at 0x800FDB64"}, {"address": "0x800FE590", "index": 0xA4, "condition": "initial branch from 0x800FE56C"}, {"address": "0x800FE590", "index": 0xA5, "condition": "after poll at 0x800FE574"}, {"address": "0x800FF240", "index": 0xAA}, {"address": "0x800FF3C0", "index": 0xAC, "condition": "initial branch from 0x800FF3A0"}, {"address": "0x800FF3C0", "index": 0xAD, "condition": "after poll at 0x800FF3A8"}, {"address": "0x800FF420", "index": 0xAE, "condition": "initial branch from 0x800FF3FC"}, {"address": "0x800FF420", "index": 0xAF, "condition": "after poll at 0x800FF404"}]
}
NATIVE_TEXT_BANKS = {"ST04": {"file": "DAT/ST04.BIN", "section_offset": 0x6800, "file_offset": 0xE800, "index_count": 0xCC, "overlay": "DAT/ST04T.BIN"}, "ST0F": {"file": "DAT/ST0F.BIN", "section_offset": 0xC800, "file_offset": 0x1B000, "index_count": 0xB0, "overlay": "DAT/ST0FT.BIN"}}
def decode_native_text(raw):
	characters = []
	for value in raw:
		if value in NATIVE_TEXT_CHARACTERS: characters.append(NATIVE_TEXT_CHARACTERS[value])
		elif value == 0x0D or value == 0xFC: characters.append("\n")
		elif value == 0x0E: characters.append("\n")
		elif 0 <= value <= 9: characters.append(str(value))
		elif 20 <= value <= 45: characters.append(chr(65 + value - 20))
		elif 46 <= value <= 71: characters.append(chr(97 + value - 46))
		elif value in (0, 0xFF): break
		else: characters.append(f"⟦{value:02X}⟧")
	return "".join(characters).strip()
def native_text_record(data, start):
	text_start = start + 4; cursor = text_start
	while cursor < len(data) and data[cursor] not in (0xFB, 0xFF, 0): cursor += 1
	return {"file_offset": start, "raw_body_hex": data[text_start:cursor].hex(), "text": decode_native_text(data[text_start:cursor])}
def export_dialogue(source_dir=None, output_dir=None):
	source_dir = Path(source_dir) if source_dir else ROOT / "build/disc-assets"; output_dir = Path(output_dir) if output_dir else DIALOGUE_OUTPUT; output_dir.mkdir(parents=True, exist_ok=True); banks = {}
	for stage, binding in NATIVE_TEXT_BANKS.items():
		path = source_dir / binding["file"]; data = path.read_bytes(); base = binding["file_offset"]; count = binding["index_count"]; _, section = decompress_section(data, binding["section_offset"]); section_end = binding["section_offset"] + section["compressed_size"]; aligned_bank = (section_end + 0x7FF) & ~0x7FF
		if aligned_bank != base: raise ValueError(f"{stage} native message bank does not follow its aligned type-0x0C section")
		if base + count * 2 > len(data): raise ValueError(f"{stage} native text index table is truncated")
		record_starts = []; cursor = base + count * 2
		while True:
			cursor = data.find(bytes.fromhex("fb050108"), cursor)
			if cursor < 0: break
			record_starts.append(cursor); cursor += 4
		records = [native_text_record(data, start) for start in record_starts]; messages = []
		for index in range(count):
			relative = struct.unpack_from("<H", data, base + index * 2)[0]
			if relative < count * 2 or relative == 0xFFFF or base + relative >= len(data): continue
			target = base + relative; nearest = min(record_starts, key=lambda start: abs(start - target)) if record_starts else -1
			record = next((item for item in records if item["file_offset"] == nearest), None) if nearest >= 0 and abs(nearest - target) <= 0x80 else None
			fragment_end = data.find(b"\xfb", target); fragment_end = len(data) if fragment_end < 0 else fragment_end
			messages.append({"index": index, "index_hex": f"0x{index:02X}", "relative_offset": relative, "file_offset": target, "record_file_offset": record["file_offset"] if record else None, "text": record["text"] if record else decode_native_text(data[target:fragment_end]), "raw_fragment_hex": data[target:fragment_end].hex()})
		banks[stage] = {"source": {"file": binding["file"], "sha256": hashlib.sha256(data).hexdigest(), "overlay": binding["overlay"], "runtime_message_base": "0x8010C000", "index_table_file_offset": f"0x{base:X}", "index_table_end_file_offset": f"0x{base + count * 2:X}", "index_format": "u16 offset from runtime message base", "index_count": count, "consumer": "SLES 0x80048474", "preceding_section": {"offset": f"0x{binding['section_offset']:X}", "type": f"0x{section['type']:X}", "decoded_size": f"0x{section['full_size']:X}", "compressed_end_file_offset": f"0x{section_end:X}", "bank_alignment": "0x800", "bank_file_offset": f"0x{aligned_bank:X}"}, "bank_pointer_validation": "The stage overlay passes 0x8010C000 to SLES 0x80048474; the indexed u16 offset resolves to this bank's original file payload."}, "message_calls": NATIVE_TEXT_CALLS[stage], "records": records, "messages": messages}
	manifest = {"schema": 1, "font": {"file": "../menu/native_font.fnt", "atlas": "../menu/font_atlas.png", "source": "SLES 0x8006B8F8 width table; native 12x12 glyph cells"}, "banks": banks}; target = output_dir / "manifest.json"; target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"); print(f"Extracted native ST04/ST0F text banks -> {target}"); return manifest
def dialogue_cli():
	manifest = export_dialogue(); print(json.dumps({"banks": {stage: {"records": len(bank["records"]), "indexed_messages": len(bank["messages"])} for stage, bank in manifest["banks"].items()}, "manifest": str(DIALOGUE_OUTPUT / "manifest.json")}))
def menu_cli():
	manifest = export_menu(); print(json.dumps({"sprites": len(manifest["sprites"]), "manifest": str(MENU_OUTPUT / "manifest.json")}))

sys.path.insert(0, str(ROOT / "build/pydeps"))
def trace_hud_cli():
	sys.path.insert(0, str(ROOT / "build/pydeps"))
	from unicorn import Uc, UcError, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
	from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_SP, UC_MIPS_REG_RA, UC_MIPS_REG_PC
	p = argparse.ArgumentParser(); p.add_argument("--exe", type=Path, required=True); p.add_argument("--game", type=Path, default=ROOT / "build/disc-assets/COMMON/GAME.BIN"); p.add_argument("--output", type=Path); p.add_argument("--gauge", choices=("life", "special", "lifter"), default="life"); p.add_argument("--hp", type=int, default=160); p.add_argument("--max-hp", type=int, default=160); p.add_argument("--frames", type=int, default=32); p.add_argument("--damage-hp", type=int); p.add_argument("--damage-frames", type=int, default=1); a = p.parse_args(); a.output = a.output or ROOT / f"build/reference_hud/{a.gauge}-primitives.json"
	m = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN); m.mem_map(0, 0x200000); m.mem_map(0x1f800000, 0x1000); m.mem_write(0x10000, a.exe.read_bytes()[0x800:]); m.mem_write(0xad000, a.game.read_bytes()[0x30:]); stores = []; calls = []; current = [0]
	def phys(address): return address & 0x1fffffff
	def read(address, size): return bytes(m.mem_read(phys(address), size))
	def put(address, fmt, value): m.mem_write(phys(address), struct.pack(fmt, value))
	def code(uc, address, size, data):
		current[0] = address
		if address in (0x800bc178, 0x800bc364, 0x800bc5e8, 0x800bcaf0, 0x800bcb90, 0x800bc8dc, 0x800bca88, 0x800bd794, 0x800bd930, 0x80015a5c): calls.append(f"0x{address:08X}")
	def write(uc, access, address, size, value, data):
		if 0x190000 <= phys(address) < 0x194000: stores.append({"address": f"0x{address:08X}", "pc": f"0x{current[0]:08X}", "size": size, "value": value})
	m.hook_add(UC_HOOK_CODE, code); m.hook_add(UC_HOOK_MEM_WRITE, write)
	def call(address, arg=0):
		m.reg_write(UC_MIPS_REG_SP, 0x801ff000); m.reg_write(UC_MIPS_REG_RA, 0x801fe000); m.reg_write(UC_MIPS_REG_A0, arg)
		try: m.emu_start(address, 0x801fe000, count=1000000)
		except UcError as error: raise RuntimeError(f"{address:#x} failed at {m.reg_read(UC_MIPS_REG_PC):#x}: {error}") from error
		if m.reg_read(UC_MIPS_REG_PC) != 0x801fe000: raise RuntimeError(f"{address:#x} did not return")
	call(0x800bc178)
	player = 0x80090000 - 0x3f60; record, update, render = {"life": (0x800e0bd8, 0x800bc364, 0x800bc5e8), "special": (0x800e0c10, 0x800bcaf0, 0x800bcb90), "lifter": (0x800e0bf4, 0x800bc8dc, 0x800bca88)}[a.gauge]; put(player + 0x70, "<h", a.hp); put(player + 0x72, "<h", a.max_hp); special_fixture = {"0x18C": 1, "0x194": 1600, "0x198": 100, "0x19A": 1440, "0x190": 1000, "0x192": 1000} if a.gauge == "special" else {}
	for offset, value in special_fixture.items(): put(player + int(offset, 16), "<B" if offset == "0x18C" else "<h", value)
	for flag in (0x80080000 - 0x3140, 0x80080000 - 0x70ff, 0x80080000 - 0x7338): put(flag, "<B", 0)
	for frame in range(a.frames): put(0x1f800006, "<H", frame); call(update, record)
	if a.damage_hp is not None:
		put(player + 0x70, "<h", a.damage_hp)
		for frame in range(a.frames, a.frames + a.damage_frames): put(0x1f800006, "<H", frame); call(update, record)
	put(0x80080000 - 0x7224, "<I", 0x80180000); put(0x80180078, "<I", 0x00ffffff); put(0x1f80004c, "<I", 0x80190000); call(render, record)
	end = struct.unpack("<I", read(0x1f80004c, 4))[0]; address = 0x80190000; packets = []; tpage = 0
	while address < end:
		tag = struct.unpack("<I", read(address, 4))[0]; count = tag >> 24
		if count == 0: raise RuntimeError(f"Zero-length packet {address:#x}, end={end:#x}, previous={packets[-1] if packets else None}, buffer={read(0x80190000, end - 0x80190000).hex()}")
		words = list(struct.unpack(f"<{count}I", read(address + 4, count * 4))); op = words[0] >> 24; item = {"address": f"0x{address:08X}", "tag": f"0x{tag:08X}", "op": f"0x{op:02X}", "words": [f"0x{word:08X}" for word in words]}
		if op == 0xe1: tpage = words[0] & 0xffff
		if op in (0x64, 0x2c, 0x28, 0x40):
			item["color"] = [words[0] & 255, words[0] >> 8 & 255, words[0] >> 16 & 255]; indices = (1,) if op == 0x64 else (1, 3, 5, 7) if op == 0x2c else (1, 2, 3, 4) if op == 0x28 else (1, 2); item["xy"] = [list(struct.unpack("<hh", struct.pack("<I", words[index]))) for index in indices]
			if op == 0x64: item.update({"uv": [words[2] & 255, words[2] >> 8 & 255], "clut": f"0x{words[2] >> 16:04X}", "dimensions": [words[3] & 65535, words[3] >> 16], "tpage": tpage})
			if op == 0x2c: item.update({"uv": [[words[index] & 255, words[index] >> 8 & 255] for index in (2, 4, 6, 8)], "clut": f"0x{words[2] >> 16:04X}", "tpage": words[4] >> 16})
		item["store_pcs"] = sorted({entry["pc"] for entry in stores if phys(address) <= phys(int(entry["address"], 16)) < phys(address + (count + 1) * 4)})
		packets.append(item)
		if tag & 0xffffff == 0xffffff: break
		address = 0x80000000 | (tag & 0xffffff)
	result = {"execution": "Original PAL SLES and GAME MIPS instructions executed by Unicorn; no routine stubs", "gauge": a.gauge, "special_test_fixture_not_game_defaults": special_fixture, "inputs": {"max_hp": a.max_hp, "current_hp": a.hp if a.damage_hp is None else a.damage_hp, "update_frames": a.frames, "damage_frames": a.damage_frames if a.damage_hp is not None else 0, "gameplay_guard_flags": 0, "scratch_frame_counter": frame, "ot_base": "0x80180000", "gpu_buffer": "0x80190000"}, "player_state": f"0x{player:08X}", "record": read(record, 0x1c).hex(), "anchor_x": struct.unpack("<h", read(record + 0xc, 2))[0], "heights": {name: struct.unpack("<h", read(record + offset, 2))[0] for name, offset in (("target_fill", 0x12), ("displayed_fill", 0x14), ("tube", 0x16))}, "packet_count": len(packets), "packets": packets, "calls": calls}
	a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8"); print(json.dumps({"output": str(a.output), "anchor_x": result["anchor_x"], "packet_count": len(packets), "packets": [{k: v for k, v in item.items() if k in ("op", "xy", "uv", "dimensions", "clut", "color")} for item in packets]}))
from world import png
from world import textures
from disc import read_u16, decompress_section
crop = hud_crop
if __name__ == '__main__':
	import sys
	commands = {'hud': 'hud_cli', 'projectile': 'export_projectile', 'menu': 'menu_cli', 'dialogue': 'dialogue_cli', 'trace-hud': 'trace_hud_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
