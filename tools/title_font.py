import json
from pathlib import Path
from ui import textures, rgba, menu_crop, png, write_if_changed
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets/menu/title_font"
ROWS = [(0, "GAME", [(0, 24), (24, 51), (51, 79), (79, 102)]), (40, "CONTINUE", [(3, 32), (32, 61), (61, 90), (90, 117), (117, 127), (127, 157), (157, 185), (185, 213)]), (80, "TUTORIAL", [(1, 30), (30, 57), (57, 85), (85, 115), (115, 144), (144, 155), (155, 187), (187, 214)]), (120, "OPTIONS", [(15, 47), (47, 76), (76, 103), (103, 114), (114, 146), (146, 175), (175, 201)])]
def export():
    vram, _ = textures(ROOT / "build/disc-assets/COMMON/TITLE.BIN")
    atlases = {"normal": rgba(vram, 704, 0, 256, 256, 4, 0, 497), "selected": rgba(vram, 704, 0, 256, 256, 4, 0, 496)}
    glyphs = {}; masks = {}
    for y, text, ranges in ROWS:
        for letter, (left, right) in zip(text, ranges):
            if letter not in glyphs:
                glyphs[letter] = [left, y, right - left, 40]
                cores = [(x, row, owner) for owner, (start, end) in enumerate(ranges) for row in range(40) for x in range(start, end) if atlases["normal"][((y + row) * 256 + x) * 4] > 180 and atlases["normal"][((y + row) * 256 + x) * 4 + 1] > 180 and atlases["normal"][((y + row) * 256 + x) * 4 + 2] < 160]
                own = text.index(letter); masks[letter] = []
                for row in range(40):
                    for x in range(left, right):
                        nearby = [( (cx - x) ** 2 + (cy - row) ** 2, owner) for cx, cy, owner in cores if abs(cx - x) <= 5 and abs(cy - row) <= 5]
                        masks[letter].append(bool(nearby) and min(distance for distance, owner in nearby if owner == own) <= min((distance for distance, owner in nearby if owner != own), default=999) if any(owner == own for distance, owner in nearby) else False)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for style, atlas in atlases.items():
        sheet = bytearray(256 * 80 * 4)
        lines = [f'info face="Title Buttons {style}" size=40 bold=0 italic=0 charset="" unicode=1 stretchH=100 smooth=0 aa=1 padding=0,0,0,0 spacing=0,0', 'common lineHeight=40 base=34 scaleW=256 scaleH=80 pages=1 packed=0', f'page id=0 file="{style}.png"', f'chars count={len(glyphs) + 1}', 'char id=32 x=0 y=0 width=0 height=0 xoffset=0 yoffset=0 xadvance=10 page=0 chnl=15']
        for index, letter in enumerate(sorted(glyphs)):
            rectangle = glyphs[letter]; width = rectangle[2]; pixels = bytearray(menu_crop(atlas, 256, rectangle)); x = index % 8 * 32; y = index // 8 * 40
            for pixel, keep in enumerate(masks[letter]):
                if not keep: pixels[pixel * 4:pixel * 4 + 4] = bytes(4)
            for row in range(40): sheet[((y + row) * 256 + x) * 4:((y + row) * 256 + x + width) * 4] = pixels[row * width * 4:(row + 1) * width * 4]
            lines.append(f'char id={ord(letter)} x={x} y={y} width={width} height=40 xoffset=0 yoffset=0 xadvance={width} page=0 chnl=15')
        write_if_changed(OUTPUT / f"{style}.png", png(256, 80, sheet))
        write_if_changed(OUTPUT / f"{style}.fnt", "\n".join(lines) + "\n", encoding="utf-8")
    metadata = {"source": "COMMON/TITLE.BIN", "source_atlas": "title_tutorial_atlas.png", "tpage": 11, "palette_y": {"normal": 497, "selected": 496}, "available_characters": " " + "".join(sorted(glyphs)), "missing_uppercase": "".join(letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if letter not in glyphs), "glyph_source_rectangles": glyphs, "limitations": "Original word sprites manually segmented into glyphs; no missing letters synthesized. Selected sheet uses the original selected palette; selection extrusion is a separate title renderer effect."}
    write_if_changed(OUTPUT / "manifest.json", json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(metadata["available_characters"])
if __name__ == "__main__": export()
