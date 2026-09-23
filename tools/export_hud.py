import hashlib
import json
from pathlib import Path
from export_maps import png, textures
from extract_maps import read_u16

ROOT = Path(__file__).resolve().parent.parent
SPRITES = {
	"health_frame": {"file": "health_frame.png", "tpage": 13, "clut": 0x7fd0, "uv": (0, 180, 32, 16), "semantic_verified": False, "evidence": "GAME.BIN page 13 meter artwork; gameplay HUD placement and role are not verified."},
	"health_fill": {"file": "health_fill.png", "tpage": 13, "clut": 0x7fd0, "uv": (12, 182, 20, 8), "semantic_verified": False, "evidence": "Interior crop from the same GAME.BIN page 13 meter artwork; this is not a separately referenced runtime sprite."},
	"buster": {"file": "buster_icon_candidate.png", "tpage": 13, "clut": 0x7fd3, "uv": (0xb8, 0x88, 0x18, 0x18), "semantic_verified": False, "evidence": "GAME.BIN overlay selects this 24x24 icon at 0x800BBB24-0x800BBB9C with four UV orientations; its Buster role is unverified."},
	"projectile": {"file": "projectile_orb.png", "tpage": 15, "clut": 0x7f91, "uv": (0, 32, 32, 32), "semantic_verified": False, "evidence": "Cyan orb crop from the original GAME.BIN effects atlas; exact buster-projectile use is unverified."},
	"impact": {"file": "impact_burst.png", "tpage": 15, "clut": 0x7f91, "uv": (0, 64, 32, 32), "semantic_verified": False, "evidence": "Cyan burst crop from the original GAME.BIN effects atlas; exact buster-impact use is unverified."},
	"life_meter": {"file": "life_meter.png", "tpage": 13, "clut": 0x7fd0, "uv": (216, 112, 40, 64), "semantic_verified": True, "evidence": "The crop includes the original LIFE label beside its vertical meter in the GAME.BIN page 13 atlas; it is menu artwork, not verified gameplay HUD placement."},
}

def color(word): return (((word & 31) * 255 + 15) // 31, (((word >> 5) & 31) * 255 + 15) // 31, (((word >> 10) & 31) * 255 + 15) // 31, 0 if word == 0 else (128 if word & 0x8000 else 255))

def decode_page(vram, tpage, clut):
	depth = (tpage >> 7) & 3
	if depth != 0: raise ValueError(f"unsupported HUD texture depth {depth:#x}")
	x = (tpage & 15) * 64; y = ((tpage >> 4) & 1) * 256; pixels = bytearray(256 * 256 * 4)
	for v in range(256):
		for u in range(256):
			word = read_u16(vram, ((y + v) * 1024 + x + (u >> 2)) * 2); index = (word >> ((u & 3) * 4)) & 15; palette = read_u16(vram, ((clut >> 6) * 1024 + (clut & 63) * 16 + index) * 2); offset = (v * 256 + u) * 4; pixels[offset:offset + 4] = bytes(color(palette))
	return pixels

def crop(pixels, x, y, width, height):
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

def main():
	input_path = ROOT / "build/disc-assets/COMMON/GAME.BIN"; output_dir = ROOT / "assets/hud"; contact_dir = ROOT / "build/maps"; output_dir.mkdir(parents=True, exist_ok=True); vram, loaded = textures(input_path); pages = {}; entries = {}
	for name, spec in SPRITES.items():
		key = (spec["tpage"], spec["clut"]); pages.setdefault(key, decode_page(vram, *key)); x, y, width, height = spec["uv"]; file_path = output_dir / spec["file"]; file_path.write_bytes(png(width, height, crop(pages[key], x, y, width, height))); entries[name] = {"file": spec["file"], "dimensions": [width, height], "source": {"archive": "COMMON/GAME.BIN", "tpage": f"0x{spec['tpage']:02X}", "clut": f"0x{spec['clut']:04X}", "uv": [x, y, width, height]}, "semantic_verified": spec["semantic_verified"], "evidence": spec["evidence"]}
	contact_sheet(vram, [13, 14, 15], 0x7c10, contact_dir / "HUD_GAME_tpages13-15_grid_exported.png"); contact_sheet(vram, [13], 0x7fd0, contact_dir / "HUD_GAME_UI_page13_clut7fd0_exported.png"); contact_sheet(vram, [14, 15], 0x7f91, contact_dir / "HUD_GAME_effects_page14-15_clut7f91_exported.png"); manifest = {"source": {"archive": "COMMON/GAME.BIN", "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(), "loaded_texture_sections": loaded}, "sprites": entries, "notes": ["Image crops preserve PS1 RGB555 palette colors, zero-index transparency, and the STP bit as half alpha.", "No native screen coordinates were verified; HUD behavior and placement remain reconstructed by the Godot project."]}; (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"Exported {len(entries)} sprite crops from {loaded} GAME.BIN texture sections to {output_dir}")

if __name__ == "__main__": main()
