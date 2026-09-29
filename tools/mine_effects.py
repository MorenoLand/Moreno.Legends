import json
from pathlib import Path
from ui import textures, decode_page, hud_crop, png, write_if_changed, ROOT
def export():
	output = ROOT / "assets/levels/ST0F"; vram, _ = textures(ROOT / "build/disc-assets/COMMON/GAME.BIN"); page = decode_page(vram, 0x2E, 0x7C10)
	write_if_changed(output / "mine_death.png", png(192, 96, hud_crop(page, 0, 0, 192, 96)))
	write_if_changed(output / "mine_smoke.png", png(192, 96, hud_crop(decode_page(vram, 0x4E, 0x7C91), 0, 0, 192, 96)))
	write_if_changed(output / "mine_flame.png", png(32, 128, hud_crop(decode_page(vram, 0x2E, 0x7DD1), 192, 0, 32, 128)))
	data = {"source": {"factory": "GAME800D3CA4", "update": "GAME800D3D28", "draw": "GAME800D3FCC", "class5_spawn": "ST0F800E9B14..9B60", "class8_spawn": "ST0F800ED374..3C0", "texture_archive": "COMMON/GAME.BIN", "tpage": 46, "clut": 31760}, "tick_rate": 25, "sprite": "mine_death.png", "frames": 8, "frame_size": [48, 48], "columns": 4, "burst_interval": 2, "maximum_bursts": 4, "burst_ticks": 8, "size_base": 64, "size_random_mask": 127, "class5": {"radius_raw": 48, "vertical_offset_raw": -96, "ground_ticks": 20, "air_ticks": 8}, "class8": {"radius_raw": 128, "bone": 0, "ticks": 16}}
	data["energy"] = {"source": "ST0F800F4BC4..6788", "rgb": [192, 128, 96], "initial_radius": 3, "phase_ticks": [8, 7, "while owner refreshes", 8], "radius_growth": 2, "beam_bundles": 3, "beam_segments": 6, "cross_section": "diamond", "initial_vertices_raw": [[-2, 0, 32], [0, -2, 32], [0, 2, 32], [2, 0, 32]], "circle_sectors": 16, "renderer_adapter": "Godot floating point vertices and depth replace GTE projections and GP0 packet ordering"}
	data["smoke"] = {"record_type": "0x60", "class": 3, "callback": "ST0F800F1E2C", "profile": "0x80100FBC", "texture": "mine_smoke.png", "tpage": 78, "clut": 31889, "maximum_particles": 14, "lifetime": [48, 63], "native_blend": "subtract"}
	data["flame"] = {"record": "0x80100864", "record_type": "0xA0", "class": 19, "controller": "ST0F800FA034", "renderer": "ST0F800F25A4 / 800F28A8", "profile": "0x80101078", "texture": "mine_flame.png", "tpage": 46, "clut": 32209, "uv": [192, 0, 32, 128], "radius": 115, "height_step": 66, "layers": 8, "sectors": 16, "scroll_speed": 12, "scroll_modulus": 96, "child_interval": 3, "child_radius_add": 92, "child_vertical_speed": 48}
	write_if_changed(output / "mine_effects.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data
if __name__ == "__main__": export()
