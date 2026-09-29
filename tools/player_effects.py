"""Export the player's landing dust ring (GAME class-7 effect spawned by the airborne landing substate) as landing_ring.png and landing_ring.json."""
import json
from pathlib import Path
from disc import write_if_changed
from special_weapons import Image, ref, texel_modes, GAME_BASE, SLES_BASE
from ui import textures, decode_page, hud_crop, png
ROOT = Path(__file__).resolve().parent.parent
def export(output_dir=None):
	common = ROOT / "build/disc-assets/COMMON"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/effects"; output_dir.mkdir(parents=True, exist_ok=True)
	G = Image((common / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); S = Image((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), SLES_BASE, 0x800, "SLES")
	effect_class = G.imm(0x800CC90C)
	if G.word(0x800CC8F4) != 0x0C000000 | (0x8003E918 & 0x0FFFFFFF) >> 2 or S.word(0x8006B44C + effect_class * 4) != 0x800D952C or G.pair(0x800D9530, 0x800D953C) != 0x800DD954: raise ValueError("Landing ring spawner/class binding differs")
	if G.word(0x800AE1DC + 6 * 4) != 0x800C6E94 or G.word(0x800C6ECC) != 0x0C000000 | (0x800CC8E0 & 0x0FFFFFFF) >> 2: raise ValueError("Airborne landing substate binding differs")
	if S.imm(0x800391E8) != 0xF8 or S.word(0x800391EC) & 0xFFFF != (0x8003985C - 0x800391F0) >> 2: raise ValueError("SLES ring record dispatch differs")
	outer, inner, texture, limits = G.pair(0x800D96C0, 0x800D96C4), G.pair(0x800D96D8, 0x800D96DC), G.pair(0x800D96C8, 0x800D96CC), G.pair(0x800D96D0, 0x800D96D4); depth_word = G.word(0x800D972C) & 0xFFFF
	u0, v0, clut, u1, v1, tpage = texture & 0xFF, (texture >> 8) & 0xFF, texture >> 16, limits & 0xFF, (limits >> 8) & 0xFF, limits >> 16; repeat_shift, step_shift = outer >> 24, depth_word & 0xFF
	elevation = lambda header, shift: ((header >> shift & 0xFF) - 0x10 + 32 & 0x3F) - 32
	vram, _ = textures(common / "GAME.BIN"); width, height = u1 - u0 + 1, v1 - v0 + 1
	write_if_changed(output_dir / "landing_ring.png", png(width, height, hud_crop(decode_page(vram, tpage, clut, True), u0, v0, width, height)))
	data = {"source": {"spawner": "GAME 0x800CC8E0(player, 0): SLES 0x8003E918 pool record, class at +4, x/y/z = player +0x12/+0x16/+0x1A, +0xF = player +0x52 (0 -> floor probe GAME 0x800B13FC snaps y in state 0)", "update": "GAME 0x800D952C states 0x800D9568 (init, counter 1) / 0x800D9618 (counter++, free at life)", "draw": "GAME 0x800D966C: two 0xF8 ring records into *0x1F800050", "renderer": "SLES 0x8003985C (0xF8 record): annulus of quads, outer vertices coloured, inner vertices black, GP0 0x3E"},
		"class": ref(effect_class, 0x800CC90C, "GAME"), "texture": "landing_ring.png", "textureSource": {"archive": "COMMON/GAME.BIN", "tpage": hex(tpage), "clut": hex(clut), "uv": [u0, v0, width, height], "texels": texel_modes(vram, tpage, clut, u0, v0, width, height), "source": "GAME 0x800D96C8/0x800D96D0"},
		"blend": "additive (tpage 0x2F semi-transparency mode 1) for STP texels; texel * vertex rgb / 128", "sizeRaw": ref(G.imm(0x800CC988), 0x800CC988, "GAME", formula="size = sizeRaw * n / life (integer), n = 1..life-1"), "lifeTicks": ref(G.imm(0x800CC994), 0x800CC994, "GAME"),
		"rgb": {"formula": "8 * (life - n) on each channel", "source": "GAME 0x800D96E4..0x800D9700"}, "unitsPerGodot": 256,
		"rings": [{"header": hex(outer), "outerRadius": "size", "innerRadius": "(3 * size) >> 2", "outerElevation": elevation(outer, 0), "innerElevation": elevation(outer, 8)}, {"header": hex(inner), "outerRadius": "(3 * size) >> 2", "innerRadius": "size >> 1", "outerElevation": elevation(inner, 0), "innerElevation": elevation(inner, 8)}],
		"ringGeometry": {"angleUnits": 64, "angleStep": 1 << step_shift, "segments": 64 >> step_shift, "startAngle": "frame counter 0x1F800006 & 0x3F at draw (spins one unit per tick)", "elevation": "vertex y += radius * sin(elevation / 64 turn), horizontal radius *= cos(elevation); native +y is down", "uStride": ((u1 - u0) >> repeat_shift) + 1, "uSpan": (u1 - u0) >> repeat_shift, "uRepeatMask": (1 << repeat_shift) - 1, "u": "u0 + uStride * (((start + angleStep * (k + 1)) / angleStep) & uRepeatMask) .. + uSpan for segment k", "v": "outer edge v0, inner edge v1"},
		"triggers": {"state": "player state 8 substate 6 (GAME 0x800C6E94)", "stationary": {"control": ref(G.imm(0x800C6E98), 0x800C6E98, "GAME"), "pose": 0}, "moving": {"control": ref(G.imm(0x800C76C8), 0x800C76C8, "GAME"), "pose": ref(G.imm(0x800C6EA0), 0x800C6EA0, "GAME")}, "landingSound": ref(G.imm(0x800C7768), 0x800C7768, "GAME"), "takeoff": "none on dry ground; GAME 0x800C6A30/0x800C6D54 only add class 0x48 bubbles (0x800CCAE8) when player +0xBE != 0"}}
	write_if_changed(output_dir / "landing_ring.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data
if __name__ == "__main__": print(json.dumps(export(), indent=2))
