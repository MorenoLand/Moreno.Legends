import argparse
import ctypes
import hashlib
import json
import struct
from pathlib import Path
from disc import write_if_changed
from world import png
ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, COLUMNS = 320, 240, 8
def _f32(value): return ctypes.c_float(value).value
def _trunc_div(value, divisor): return (abs(value) // divisor) * (-1 if value < 0 else 1)
def _edge_step(dx, dy): return _trunc_div((dx << 32) + (-(dy - 1) if dx < 0 else dy - 1 if dx > 0 else 0), dy)
def _edge(x, step, rows): return ((x << 32) + (1 << 32) - (1 << 11) + step * rows) >> 32
def _color(first, second, numerator, denominator): return first + int(_f32(_f32(second - first) * _f32(_f32(numerator) / _f32(denominator))))
def _triangle(mask, vertices):
	first, second, third = vertices
	if first[1] > second[1]: first, second = second, first
	if first[1] > third[1]: first, third = third, first
	if second[1] > third[1]: second, third = third, second
	(x0, y0, c0), (x1, y1, c1), (x2, y2, c2) = first, second, third; total = y2 - y0
	if total == 0: return
	long_step = _edge_step(x2 - x0, total)
	for y in range(max(0, y0), min(HEIGHT, y2)):
		second = y >= y1; segment = max(1, y2 - y1 if second else y1 - y0); first_x, first_y, first_c = (x1, y1, c1) if second else (x0, y0, c0); last_x, last_c = (x2, c2) if second else (x1, c1)
		xa = _edge(x0, long_step, y - y0); xb = _edge(first_x, _edge_step(last_x - first_x, segment), y - first_y); ca = _color(c0, c2, y - y0, total); cb = _color(first_c, last_c, y - first_y, segment)
		if xa > xb: xa, xb, ca, cb = xb, xa, cb, ca
		span = xb - xa
		for x in range(max(0, xa), min(WIDTH, xb)):
			color = max(0, min(31, _color(ca, cb, x - xa, span))) if span else ca; index = y * WIDTH + x; mask[index] = min(31, mask[index] + color)
def _quad(mask, points, colors):
	vertices = [(int(point[0]), int(point[1]), int(color) >> 3) for point, color in zip(points, colors)]
	_triangle(mask, [vertices[index] for index in (0, 1, 2)]); _triangle(mask, [vertices[index] for index in (1, 2, 3)])
def _geometry(kind, counter, trig):
	if kind == "circle":
		inner, outer = (counter * 3 - 16, counter * 3 + 64) if counter >= 6 else (0, counter * 6); result = []
		for index in range(0, 64, 2):
			first, second = trig[index], trig[(index + 2) & 63]; points = [(160 + (radius * item[1] >> 12), 120 + (radius * item[0] >> 12)) for radius, item in [(inner, first), (inner, second), (outer, first), (outer, second)]]; result.append({"points": points, "colors_rgb8": [0, 0, 255, 255]})
		return result
	span = (64 - counter) * 3
	return [{"points": [(0, span), (WIDTH, span), (0, span - 64), (WIDTH, span - 64)], "colors_rgb8": [0, 0, 40, 40]}, {"points": [(0, HEIGHT - span), (WIDTH, HEIGHT - span), (0, HEIGHT - span + 64), (WIDTH, HEIGHT - span + 64)], "colors_rgb8": [0, 0, 40, 40]}]
def _atlas(kind, trig, output):
	mask = bytearray(WIDTH * HEIGHT); atlas_width, atlas_height = WIDTH * COLUMNS, HEIGHT * 8; pixels = bytearray(atlas_width * atlas_height * 4); frames = []
	for frame, counter in enumerate(range(63, 0, -1)):
		geometry = _geometry(kind, counter, trig)
		for quad in geometry: _quad(mask, quad["points"], quad["colors_rgb8"])
		x, y = (frame % COLUMNS) * WIDTH, (frame // COLUMNS) * HEIGHT
		for row in range(HEIGHT):
			start = ((y + row) * atlas_width + x) * 4; values = mask[row * WIDTH:(row + 1) * WIDTH]; pixels[start:start + WIDTH * 4] = bytes(component for value in values for component in (value, value, value, 255))
		frames.append({"counter": counter, "rect": [x, y, WIDTH, HEIGHT], "mask_sha256": hashlib.sha256(mask).hexdigest(), "quads": geometry})
	x, y = 7 * WIDTH, 7 * HEIGHT
	for row in range(HEIGHT): start = ((y + row) * atlas_width + x) * 4; pixels[start:start + WIDTH * 4] = bytes((31, 31, 31, 255)) * WIDTH
	encoded = png(atlas_width, atlas_height, pixels); write_if_changed(output, encoded)
	return {"file": output.name, "size": [atlas_width, atlas_height], "tile_size": [WIDTH, HEIGHT], "columns": COLUMNS, "animated_frames": 63, "endpoint_frame": 63, "endpoint_rect": [x, y, WIDTH, HEIGHT], "mask_rgb5_max": 31, "storage": "RGB bytes store accumulated native RGB5 units0..31; alpha255; sample without source_color", "raster": "psxrecomp gpu_sw_renderer.c raster_gouraud_triangle; gpu_sw_edges.h biased32.32 exclusive bottom/right; float32 color interpolation", "hardware_pixel_parity": "not independently verified", "sha256": hashlib.sha256(encoded).hexdigest(), "frames": frames}
def export(source_dir=None, output_dir=None):
	source_dir = Path(source_dir) if source_dir else ROOT / "build/disc-assets"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/fades"; output_dir.mkdir(parents=True, exist_ok=True); path = source_dir / "SLES_035.56"; source = path.read_bytes(); offset = lambda address: 0x800 + address - 0x80010000; trig = [list(struct.unpack_from("<2h", source, offset(0x80073E4C) + index * 64 * 4)) for index in range(64)]; speeds = list(struct.unpack_from("<5H", source, offset(0x8007890C + 0x174))); profiles = {}; atlases = {}
	for base, blend in [(0, "subtract"), (8, "add")]:
		for family, direction in [(0, "reveal"), (16, "cover")]:
			for rate in range(5):
				code = base + family + rate
				if rate == 0 and (family == 0 or base == 8): continue
				profiles[f"0x{code:02X}"] = {"kind": "uniform", "blend": blend, "direction": direction, "initial_rgb8": 255 if direction == "reveal" else 0, "step_rgb8": -speeds[rate] if direction == "reveal" else speeds[rate], "endpoint_rgb8": 0 if direction == "reveal" else 255, "visible_ticks": (255 + speeds[rate] - 1) // speeds[rate], "busy_settle_ticks": 3, "tick_rate": 25, "source_controller": "SLES0x80013C40", "source_renderer": "SLES0x80013614"}
	for subtype in range(4):
		step = 16 if subtype & 2 else 8; profiles[f"0x{0x20 + subtype:02X}"] = {"kind": "uniform", "blend": "add" if subtype & 1 else "subtract", "direction": "cover", "initial_rgb8": 0, "step_rgb8": step, "endpoint_rgb8": 255, "visible_ticks": 0x1F if subtype & 2 else 0x3F, "busy_settle_ticks": 3, "tick_rate": 25, "source_controller": "SLES0x80013D8C state table 0x80068228 -> 0x800143CC", "native": "per frame GP0 0x62 full-screen rect colour 0x101010|0x080808 over the retained frame, tpage 0x140 subtract | 0x120 add (0x80063DD4); frames 0x1F|0x3F at -0x7104"}
	for code, kind in [(0x26, "circle"), (0x28, "bands")]:
		atlas = _atlas(kind, trig, output_dir / (kind + ".png"))
		atlases[kind] = atlas
		for subtype in range(2): profiles[f"0x{code + subtype:02X}"] = {"kind": kind, "blend": "add" if subtype else "subtract", "visible_ticks": 63, "tick_rate": 25, "feedback": True, "endpoint_rgb5": 31, "keep_mode": 0, "busy_settle_ticks": 3, "startup_buffer_gate": {"buffer_index": 1, "native_updates_by_request_parity": [1, 2], "source": "SLES0x80014310 waits alternating framebuffer1"}, "cleanup_gate": "GAME0x800AF108 passes keep_mode0;SLES15448 restores on buffer1,buffer0,buffer1 after endpoint", "source_controller": "SLES0x80014E0C" if kind == "circle" else "SLES0x800151BC", "atlas": kind}
	manifest = {"viewport": [WIDTH, HEIGHT], "pal_game_tick_rate": 25, "source": {"file": "SLES_035.56", "sha256": hashlib.sha256(source).hexdigest(), "request": "0x8001392C", "gp": "0x8007890C", "uniform_speed_table": "0x80078A80", "trig_initializer": "0x800112BC", "trig_table": "0x80073E4C sampled every64 entries", "recomp_raster": "build/mega-man-legends-2-recomp/psxrecomp/runtime/src/gpu_sw_renderer.c"}, "uniform_speeds_rgb8": speeds, "trig64_sin_cos": trig, "profiles": profiles, "atlases": atlases}; write_if_changed(output_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
def main():
	parser = argparse.ArgumentParser(); parser.add_argument("--source-dir", type=Path, default=ROOT / "build/disc-assets"); parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/fades"); args = parser.parse_args(); export(args.source_dir, args.output_dir)
if __name__ == "__main__": main()
