from __future__ import annotations
import json
import struct
import sys
from pathlib import Path
import models
import scene_player
import world
from ui import decode_page
from disc import write_if_changed
ROOT = Path(__file__).resolve().parent.parent
GAME_BASE, SLES_BASE, MODULE_BASE = 0x800AD000, 0x80010000, 0x8010A000
WEAPON_ID = 0x0F
def u32(data, offset): return struct.unpack_from("<I", data, offset)[0]
class Image:
	def __init__(self, data, base, header, name): self.data, self.base, self.header, self.name = data, base, header, name
	def offset(self, address):
		position = self.header + address - self.base
		if not self.header <= position < len(self.data): raise ValueError(f"{self.name} address {address:#x} is outside the image")
		return position
	def word(self, address): return u32(self.data, self.offset(address))
	def half(self, address): return struct.unpack_from("<h", self.data, self.offset(address))[0]
	def byte(self, address): return self.data[self.offset(address)]
	def imm(self, address, opcodes=(9, 10, 11, 12, 13)):
		word = self.word(address)
		if word >> 26 not in opcodes: raise ValueError(f"{self.name} {address:#x} is not an immediate instruction ({word:#010x})")
		value = word & 0xFFFF; return value if word >> 26 in (12, 13) else value - 0x10000 if value & 0x8000 else value
	def shift(self, address):
		word = self.word(address)
		if word >> 26 or word & 63 not in (0, 2, 3): raise ValueError(f"{self.name} {address:#x} is not a shift")
		return (word >> 6) & 31
	def pair(self, lui, low):
		if self.word(lui) >> 26 != 15: raise ValueError(f"{self.name} {lui:#x} is not lui")
		return ((self.word(lui) & 0xFFFF) << 16) + self.imm(low) & 0xFFFFFFFF
def rgb(word): return [word & 255, (word >> 8) & 255, (word >> 16) & 255]
def ref(value, address, image="R0E", **extra): return {"value": value, "source": f"{image} {address:#010x}", **extra}
def sections(data):
	result = {}
	for offset in range(0, len(data) - 47, 0x800):
		kind, size, count, address = struct.unpack_from("<4I", data, offset)
		if kind in (1, 2, 5) and 0 < size <= len(data): result[offset] = {"type": kind, "size": size, "count": count, "address": address}
	return result
def decode_controls(source, binary, bone_node_ids, bones, player_address, track_address=0x80121E20, control_address=0x801246B0, name="PL00R0E.BIN", base_slot=0x60):
	found = sections(source); track_offset = next(o for o, s in found.items() if s["type"] == 1 and s["address"] == track_address); control_offset = next(o for o, s in found.items() if s["type"] == 1 and s["address"] == control_address)
	track_delta, control_delta = track_address - player_address, control_address - player_address; track_file, control_file = track_offset + 0x30, control_offset + 0x30; track_end, control_end = track_delta + found[track_offset]["size"], control_delta + found[control_offset]["size"]
	track_table, control_table = u32(source, track_file) - track_delta, u32(source, control_file) - control_delta
	if track_table <= 0 or track_table & 3 or control_table <= 0 or control_table & 3: raise ValueError(f"{name} equipment-action tables are invalid")
	track_offsets = [u32(source, track_file + i) for i in range(0, track_table, 4)]; control_offsets = [u32(source, control_file + i) for i in range(0, control_table, 4)]; tracks = {}
	for index, offset in enumerate(track_offsets):
		end = track_offsets[index + 1] if index + 1 < len(track_offsets) else track_end
		if not track_delta <= offset < track_end or (end - offset) & 63: raise ValueError(f"{name} track {index} is invalid")
		tracks[index] = (track_file + offset - track_delta, (end - offset) // 64, offset)
	clips, manifest = [], []
	for index, offset in enumerate(control_offsets):
		if not control_delta <= offset < control_end: raise ValueError(f"{name} control {index} pointer is outside its bank")
		position = control_file + offset - control_delta; track_index, frame_count = source[position], source[position + 1]; end = control_offsets[index + 1] if index + 1 < len(control_offsets) else control_end
		if not frame_count or position + 4 + frame_count * 4 > control_file + end - control_delta or track_index not in tracks: raise ValueError(f"{name} control {index} is invalid")
		track, source_frames, source_track = tracks[track_index]; records = [struct.unpack_from("<4B", source, position + 4 + frame * 4) for frame in range(frame_count)]; poses = [record[0] for record in records]
		if any(pose & 0x80 or pose >= source_frames for pose in poses): raise ValueError(f"{name} control {index} has unresolved poses")
		times, samples, ticks = [], [], 0
		for frame, (pose, duration, event, flags) in enumerate(records):
			if not duration: raise ValueError(f"{name} control {index} has a zero-duration record")
			target = next((other[0] for other in records[frame + 1:] if other[0] != pose), None) if flags & 0x90 == 0x10 else None
			if flags & 0x90 == 0x10 and target is None: raise ValueError(f"{name} control {index} has an unresolved interpolation target")
			times.append(ticks / 30.0); samples.append((pose, target, flags & 15 if target is not None else 0))
			if duration > 1: times.append((ticks + duration - 1) / 30.0); samples.append(samples[-1])
			ticks += duration
		final_flags = records[-1][3]; loop_frame = final_flags & 127 if final_flags & 128 and final_flags != 255 else None
		if loop_frame is not None and loop_frame >= frame_count: raise ValueError(f"{name} control {index} loops outside its records")
		times.append(ticks / 30.0); samples.append(samples[loop_frame] if loop_frame is not None else samples[-1])
		def word(pose, slot): return u32(source, track + pose * 64 + slot * 4)
		def rotations(bone, order): return [value for pose, target, fraction in samples for value in models.decode_rotation(word(pose, bone + 1), word(target, bone + 1) if target is not None else None, fraction, order)]
		input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True); root = [bones[0][axis] + value for pose, target, fraction in samples for axis, value in enumerate(models.point(word(pose, 0), word(target, 0) if target is not None else None, fraction))]
		samplers = [{"input": input_accessor, "output": binary.accessor(root, "f", 5126, "VEC3", None), "interpolation": "LINEAR"}]; channels = [{"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}}]
		for bone, node in enumerate(bone_node_ids): samplers.append({"input": input_accessor, "output": binary.accessor(rotations(bone, "YXZ" if bone in (2, 3, 4) else "XYZ"), "f", 5126, "VEC4", None), "interpolation": "LINEAR"}); channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
		slot = base_slot + index; clip_name = f"clip_{slot:03d}"; metadata = {"frameCount": frame_count, "durationTicks": ticks, "durationSeconds": round(ticks / 30.0, 6), "periodTicks": ticks, "periodSeconds": round(ticks / 30.0, 6), "loopFrame": loop_frame, "loops": loop_frame is not None, "finalFlags": final_flags, "holdsLastFrame": final_flags == 255, "events": [{"frame": frame, "id": event} for frame, (_, _, event, _) in enumerate(records) if event], "records": [{"pose": pose, "durationTicks": duration, "event": event, "flags": flags} for pose, duration, event, flags in records]}
		extras = {"sourceControlSlot": slot, "sourceControlOffset": hex(offset), "sourceTrackSlot": track_index, "sourceTrackOffset": hex(source_track), "frameIndices": poses, "fps": 30, "sourceBank": name, "sourceContext": f"weapon {WEAPON_ID:#04x} equipment action; player+0x13C bit0x40 mode bones2..4", **metadata}
		clips.append({"name": clip_name, "samplers": samplers, "channels": channels, "extras": extras})
		upper = (0, 1, 2, 3, 4); upper_samplers = [dict(samplers[1 + bone]) for bone in upper]
		for i, bone in enumerate(upper):
			if bone != 1: upper_samplers[i]["output"] = binary.accessor(rotations(bone, "YXZ"), "f", 5126, "VEC4", None)
		clips.append({"name": clip_name + "_upper", "samplers": upper_samplers, "channels": [{"sampler": i, "target": channels[1 + bone]["target"]} for i, bone in enumerate(upper)], "extras": {**extras, "activeArmBones": [2, 3, 4], "activeArmRotationOrder": "YXZ", "rootTranslation": "omitted; use base clip"}})
		for suffix in ("", "_upper"): manifest.append({"name": clip_name + suffix, "slot": slot, "track": track_index, **metadata, "sourceBank": name, "context": "equipment action mode1 bones2..4"})
	return clips, manifest, {"source": name, "trackBank": hex(track_address), "trackSection": hex(track_offset), "controlBank": hex(control_address), "controlSection": hex(control_offset), "tracks": len(track_offsets), "controls": len(control_offsets), "trackFrames": [tracks[index][1] for index in sorted(tracks)]}
def arm_mesh(binary, by_material, pngs):
	surfaces = sorted(by_material); primitives = []
	for material, stream in surfaces:
		arrays = by_material[(material, stream)]; primitives.append({"attributes": {"POSITION": binary.accessor(arrays["positions"], "f", 5126, "VEC3", 34962, True), "NORMAL": binary.accessor(arrays["normals"], "f", 5126, "VEC3", 34962), "TEXCOORD_0": binary.accessor(arrays["uvs"], "f", 5126, "VEC2", 34962), "COLOR_0": binary.accessor(arrays["colors"], "f", 5126, "VEC4", 34962), "JOINTS_0": binary.accessor(arrays["joints"], "H", 5123, "VEC4", 34962), "WEIGHTS_0": binary.accessor(arrays["weights"], "f", 5126, "VEC4", 34962)}, "material": len(primitives), "mode": 4, "extras": {"sourceMaterial": material}})
	views = [binary.view(pngs[material]) for material, _ in surfaces]
	return {"primitives": primitives, "materials": [{"name": "Source material %d" % material, "doubleSided": True, "alphaMode": "MASK", "alphaCutoff": 0.5, "pbrMetallicRoughness": {"baseColorTexture": {"index": i}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "extensions": {"KHR_materials_unlit": {}}} for i, (material, _) in enumerate(surfaces)], "textures": [{"sampler": 0, "source": i} for i in range(len(surfaces))], "images": [{"bufferView": view, "mimeType": "image/png", "name": "Source material %d" % material} for view, (material, _) in zip(views, surfaces)], "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}]}
def write_glb(path, binary, nodes, bone_node_ids, world_points, animations, extras, mesh_name, mesh):
	inverse = binary.accessor([value for p in world_points for value in (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -p[0], -p[1], -p[2], 1.0)], "f", 5126, "MAT4", None); nodes[1]["name"] = mesh_name
	document = {"asset": {"version": "2.0", "generator": "tools/special_weapons.py", "extras": extras}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": [{"name": mesh_name, "primitives": mesh["primitives"]}], "skins": [{"name": "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse}], "animations": animations, "materials": mesh["materials"], "textures": mesh["textures"], "images": mesh["images"], "samplers": mesh["samplers"], "bufferViews": binary.views, "accessors": binary.accessors, "buffers": [{"byteLength": len(binary.data)}], "extensionsUsed": ["KHR_materials_unlit"]}
	chunk = json.dumps(document, separators=(",", ":")).encode("utf-8"); chunk += b" " * ((-len(chunk)) & 3); binary.data.extend(b"\0" * ((-len(binary.data)) & 3))
	write_if_changed(path, struct.pack("<4sII", b"glTF", 2, 28 + len(chunk) + len(binary.data)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk + struct.pack("<I4s", len(binary.data), b"BIN\0") + binary.data)
def strip(vram, tpage, clut, u, v, width, height, frames):
	page = decode_page(vram, tpage & 0x1F, clut, True); pixels = bytearray()
	for row in range(height):
		for frame in range(frames): start = ((v + row) * 256 + u + frame * width) * 4; pixels.extend(page[start:start + width * 4])
	return pixels
def texel_modes(vram, tpage, clut, u, v, width, height):
	x, y = (tpage & 15) * 64, ((tpage >> 4) & 1) * 256; counts = {"transparent": 0, "stp": 0, "opaque": 0}
	for row in range(height):
		for column in range(width):
			index = (struct.unpack_from("<H", vram, ((y + v + row) * 1024 + x + ((u + column) >> 2)) * 2)[0] >> (((u + column) & 3) * 4)) & 15; colour = struct.unpack_from("<H", vram, ((clut >> 6) * 1024 + (clut & 63) * 16 + index) * 2)[0]
			counts["transparent" if colour == 0 else "stp" if colour & 0x8000 else "opaque"] += 1
	return counts
def export_extinguisher(output_dir=None):
	common = ROOT / "build/disc-assets/COMMON"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/weapons"; output_dir.mkdir(parents=True, exist_ok=True)
	module_bytes = (common / "PL00R0E.BIN").read_bytes(); player = (common / "PL00P000.BIN").read_bytes()
	if u32(module_bytes, 0x30) != 0x60 + WEAPON_ID or u32(module_bytes, 12) != MODULE_BASE: raise ValueError("PL00R0E.BIN is not the weapon 0x0F module")
	R = Image(module_bytes, MODULE_BASE, 0x30, "R0E"); G = Image((common / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); S = Image((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), SLES_BASE, 0x800, "SLES")
	if G.half(0x800DBE44 + (WEAPON_ID - 3) * 2) != 0x22 or S.word(0x8006B3A0 + 0x0E * 4) != 0x8010A004 or S.word(0x8006B3E4 + 0x16 * 4) != 0x8010ABA0: raise ValueError("Weapon 0x0F dispatch tables do not match PL00R0E")
	nodes, bones, world_points, bone_node_ids = scene_player.skeleton_nodes(); binary = models.BinaryGLB(); animations, clips, bank = decode_controls(module_bytes, binary, bone_node_ids, bones, u32(player, 0x0C))
	player_base, player_size, family = u32(player, 0x0C), u32(player, 4), player[0x30 + 0x71]; row_table = 0x8006AEC0 + family * 28; slots = [[S.byte(0x80078ADC + mode * 5 + i) for i in range(5)] for mode in range(4)]; strip_counts = [S.byte(0x80078B04 + i) for i in range(5)]; strip_bones = [S.byte(0x80078AF0 + i) for i in range(sum(strip_counts))]
	part = slots[0].index(2); arm_bones = strip_bones[sum(strip_counts[:part]):sum(strip_counts[:part + 1])]; arm_descriptor, replaced_descriptor = S.word(row_table + slots[1][part] * 4), S.word(row_table + slots[0][part] * 4); arm_section = next((o for o, s in sections(module_bytes).items() if s["type"] == 1 and s["address"] == arm_descriptor), None)
	if S.word(0x80023468) >> 16 != 0x8202 or (S.word(0x80023468) & 0xFFFF) != 0x18C or slots[1][part] != 3 or arm_section is None or arm_descriptor != player_base + player_size: raise ValueError("Weapon arm descriptor slot does not match PL00R0E")
	arm_payload = player[0x30:0x30 + player_size] + module_bytes[arm_section + 0x30:arm_section + 0x30 + sections(module_bytes)[arm_section]["size"]]; arm, *_, arm_faces, arm_vertices, _ = models.decode_mesh(arm_payload, (("ExtinguisherArm", arm_descriptor - player_base, tuple(arm_bones)),))
	player_vram, _ = world.textures(common / "PL00T.BIN"); clut_uploads = world.texture_uploads(module_bytes, player_vram, "PL00R0E.BIN"); material_words = struct.unpack_from("<4I", arm_payload, 0x60); arm_materials = sorted({material for material, _ in arm})
	library, model, arm_name = "weapon_0f", "hose_clips.glb", "ExtinguisherArm"; write_glb(output_dir / model, binary, nodes, bone_node_ids, world_points, animations, {"source": "COMMON/PL00R0E.BIN", "library": library, "weapon": WEAPON_ID}, arm_name, arm_mesh(binary, arm, {m: world.texture_page(player_vram, material_words[m] >> 16, material_words[m] & 0xFFFF) for m in arm_materials}))
	arm_manifest = {"model": model, "node": arm_name, "source": f"COMMON/PL00R0E.BIN section {arm_section:#x} -> {arm_descriptor:#x} (PBD descriptor appended to PL00P000 payload {player_base:#x}+{player_size:#x})", "descriptor": hex(arm_descriptor), "descriptorRow": f"SLES 0x8006AEC0 family {family} slot {slots[1][part]}", "bones": arm_bones, "boneNames": [f"Bone_{b:02d}" for b in arm_bones], "faces": arm_faces, "vertices": arm_vertices,
		"replaces": {"part": "OtherArm", "descriptor": hex(replaced_descriptor), "descriptorSlot": slots[0][part], "pbdGroup": hex(replaced_descriptor - player_base), "bones": arm_bones, "boneNames": [f"Bone_{b:02d}" for b in arm_bones], "rule": "hide every player triangle skinned to these bones (only the OtherArm group uses them)"},
		"condition": {"value": "player+0x18C >= 2", "source": "SLES 0x80023438 (0x80023468..0x8002348C): render mode = (0x18C >= 2) + 2*(0x18D >= 2) picks the descriptor-slot row at SLES 0x80078ADC; strips/bones per part at 0x80078B04/0x80078AF0", "modes": slots, "visibility": "whenever the weapon is the active special (equipped), not only while spraying", "activeWeapon": "GAME 0x800CF4A8/0x800CF540: 0x18C = 0x18E in modes 1/2 when +6 == 0 and 0x19F != 0; mode 0 (safe zones) clears 0x18C"},
		"materials": {str(m): {"clut": hex(material_words[m] >> 16), "tpage": hex(material_words[m] & 0xFFFF)} for m in arm_materials}, "clutUpload": {"section": "PL00R0E.BIN 0x3800 type 2", "rect": clut_uploads[0]["palette_rect"] if clut_uploads else None, "note": "material 3 CLUT 0x3C0C is only used by this descriptor; its palette comes from the module, page 6 texels from PL00T.BIN"}, "emitBone": {"bone": 4, "note": "stream origin is the Bone_04 joint (player+0x4B0 cache, SLES 0x80040624); the visible stream starts at segment 1 (billboard size 10*i), past the nozzle"}}
	vram, _ = world.textures(common / "GAME.BIN"); stream_word = R.pair(0x8010A9F8, 0x8010A9FC); stream_tpage, stream_clut, stream_v = R.pair(0x8010AA00, 0x8010AA04) >> 16, stream_word >> 16, (stream_word >> 8) & 255
	write_if_changed(output_dir / "hose_stream.png", world.png(128, 32, strip(vram, stream_tpage, stream_clut, 0, stream_v, 32, 32, 4)))
	splash_subtype = R.imm(0x8010A7FC); splash_row = 0x800DD43C + splash_subtype * 8; splash_tpage, splash_clut, splash_flags, splash_sound = G.half(splash_row) & 0xFFFF, G.half(splash_row + 2) & 0xFFFF, G.half(splash_row + 4), G.half(splash_row + 6); frame_table = G.word(0x800DD654 + splash_subtype * 4); splash_frames = []
	for index in range(32):
		record = frame_table + index * 12; splash_frames.append({"rgb": rgb(G.word(record)), "uv": [G.byte(record + 4), G.byte(record + 5), G.byte(record + 6) - G.byte(record + 4) + 1, G.byte(record + 7) - G.byte(record + 5) + 1], "durationTicks": G.byte(record + 8) + 1, "next": G.byte(record + 9), "sizeAdd": G.byte(record + 10), "sizeHigh": G.byte(record + 11)})
		if G.byte(record + 9) == 0xFF: break
	su, sv, sw, sh = splash_frames[0]["uv"]; write_if_changed(output_dir / "hose_splash.png", world.png(sw * len(splash_frames), sh, strip(vram, splash_tpage, splash_clut, su, sv, sw, sh, len(splash_frames))))
	row_address, energy_address = 0x800DC978 + WEAPON_ID * 8, 0x800DCA08 + WEAPON_ID * 8; row = [G.byte(row_address + i) for i in range(8)]; energy = [G.half(energy_address + i * 2) for i in range(4)]; levels = [[G.half(0x800DCC60 + level * 8 + i * 2) for i in range(4)] for level in range(4)]
	step_base, step_shift, droop_base, droop_shift = -R.imm(0x8010A96C), R.shift(0x8010A71C), R.imm(0x8010A964), R.shift(0x8010A70C); count_max = R.imm(0x8010A64C, (11,)); size_base, size_step = R.imm(0x8010A6C0), R.imm(0x8010AB14)
	colour, colour_step, glow, glow_step = R.pair(0x8010A9F0, 0x8010A9F4), R.pair(0x8010AB3C, 0x8010AB40), R.pair(0x8010AA0C, 0x8010AA10), R.pair(0x8010AB18, 0x8010AB1C); segments = []; travel = 0.0
	for i in range(count_max):
		triangle = i * (i + 1) // 2; step = step_base + (triangle << step_shift); droop = (droop_base + (triangle << droop_shift)) >> 4; travel += step / 16; size = size_base + size_step * i
		segments.append({"index": i, "stepRaw": step, "stepUnits": step / 16, "cumulativeUnits": travel, "droopUnits": droop, "aimLagTicks": i, "hitRadius": size >> 2, "glowRadius": size, "billboardSize": 10 * i, "rgb": rgb(colour - colour_step * i), "glowRgb": rgb(glow - glow_step * i), "uFrameOffset": i})
	hud = {"draw": "GAME 0x800BCB90", "visibility": "GAME 0x800BCAF0 (player+0x18C != 0)", "coordinateSpace": [320, 240], "anchorX": "HUD record+0x0C (assets/hud/manifest.json gauges.special.record.initial_anchor)", "bottomY": ref(G.imm(0x800BCC0C), 0x800BCC0C, "GAME"), "heightPx": ref(G.imm(0x800BCC34), 0x800BCC34, "GAME"), "drawOrder": "flat GP0 0x28 quads chained in order: base, then core over it; whole part at the bottom, remainder stacked above",
		"tank": {"value": "player+0x19A", "max": "player+0x194", "unit": "player+0x198", "xOffset": ref(G.imm(0x800BCC10), 0x800BCC10, "GAME"), "width": ref(G.imm(0x800BCD28), 0x800BCD28, "GAME"), "coreWidth": ref(G.imm(0x800BCD70), 0x800BCD70, "GAME"), "wholeHeight": "((v - v % unit) * 64 + max / 2) / max", "remainderHeight": "((v % unit) * 64 + max / 2) / max, at least 1 when v % unit != 0", "full": "v == max -> whole 64 (remainder 64 when max < unit)",
			"wholeRgb": ref(rgb(G.pair(0x800BCD0C, 0x800BCD10)), 0x800BCD0C, "GAME"), "wholeCoreRgb": ref(rgb(G.pair(0x800BCD58, 0x800BCD5C)), 0x800BCD58, "GAME"), "remainderRgb": ref(rgb(G.pair(0x800BCDAC, 0x800BCDB0)), 0x800BCDAC, "GAME"), "remainderCoreRgb": ref(rgb(G.pair(0x800BCDFC, 0x800BCE00)), 0x800BCDFC, "GAME")},
		"reserve": {"value": "player+0x192", "max": "player+0x190", "height": "(v * 64 - 1 + max) / max; 64 when max == 0", "xOffsets": [G.imm(0x800BCEF0), G.imm(0x800BCEF4)], "coreXOffsets": [G.imm(0x800BCF0C), G.imm(0x800BCF14)], "xSource": "GAME 0x800BCEF0/0x800BCEF4/0x800BCF0C/0x800BCF14", "rgb": ref(rgb(G.pair(0x800BCEA0, 0x800BCEA4)), 0x800BCEA0, "GAME"), "coreRgb": ref(rgb(G.pair(0x800BCEA8, 0x800BCEAC)), 0x800BCEA8, "GAME"), "note": "0x7FFF reserve is never consumed for weapon 0x0F, so this bar is always full"},
		"sprites": {name: f"res://assets/hud/{name}.png" for name in ("special_piece_a", "special_piece_b", "special_piece_c", "special_tube_stretch")}, "spriteSource": "frame sprites already exported by tools/ui.py hud_cli (GAME descriptors 8-11 drawn via 0x800BD930)"}
	manifest = {"schema": 1, "weapon": WEAPON_ID, "name": "extinguisher",
		"module": {"file": "COMMON/PL00R0E.BIN", "loadAddress": hex(MODULE_BASE), "fileIndex": ref(0x22, 0x800DBE44 + (WEAPON_ID - 3) * 2, "GAME"), "sections": {hex(o): {**s, "address": hex(s["address"]), "size": hex(s["size"])} for o, s in sections(module_bytes).items()}, "actorClass": ref(row[7], row_address + 7, "GAME"), "actorEntry": "0x8010A004 (SLES pool-A table 0x8006B3A0[0x0E])", "states": [hex(R.word(0x8010B288 + i * 4)) for i in range(4)], "dropletEntry": "0x8010ABA0 (SLES effect table 0x8006B3E4[0x16])", "dropletStates": [hex(R.word(0x8010B298 + i * 4)) for i in range(3)]},
		"model": model, "arm": arm_manifest, "library": library, "libraryUse": "Load the GLB's animation library as 'weapon_0f'; while player+0x18C == 0x0F resolve controls 96/97 to weapon_0f/clip_096(_upper) and weapon_0f/clip_097(_upper) instead of the PL00R02 clips in megaman.glb.",
		"animationBank": {**bank, "resolver": "SLES 0x8003F2A8 controls 0x60..0x6F -> table 0x801246B0 (the loaded weapon module)", "selector": "GAME 0x800CDD08: 0x60, or 0x61 when movement state +9 is 2/7/8", "fps": 30, "rotationOrder": "YXZ for bones2..4 (player+0x13C bit0x40), XYZ otherwise", "skeleton": "node layout identical to assets/player/megaman.glb"}, "clips": clips,
		"timeline": {"handler": "GAME 0x800CEB20 (0x800DCD08[0x0F], dispatched by 0x800CE5D4; substates via 0x800AE2D4)", "spawnPose": ref(row[0], row_address, "GAME"), "loopStartPose": ref(row[1], row_address + 1, "GAME"), "loopRewindAtPose": 8, "holdLoopPoses": [6, 7], "releasePose": ref(row[2], row_address + 2, "GAME"), "endCondition": "final record (+0x9F == -1), then player+0x13C &= 0x3F38", "rowBytes": ref(row, row_address, "GAME"), "interruptBytes": {"value": row[5:7], "note": "semantics unverified"}},
		"input": {"fire": "GAME 0x800CB8D8/0x800CBAF8: (pad+0x10E & mask+0x130) or buffered 0x13C&0x1000, requires (0x13C&0x300)==0x300; physical button unverified", "hold": "S1 continues while (0x10E&0x130) and 0x13C&0x40", "readyBit": "player+0x13C bit 0x200 set when tank >= cost", "categories": {"standing": "states 0,1,4,6,13 -> mode 0x40, control 0x60", "locomotion": "state 2 with row[4]==0 -> forced to state 0, fires next tick", "airborne": "states 7/8 -> no fire"}},
		"movement": {"fireWhileMoving": ref(bool(row[4]), row_address + 4, "GAME"), "stationaryWhileSpraying": "hold handler zeroes player+0x38/+0x3C each tick when +0xBD == 0", "playerFlagC8": "set to 1 each spraying tick; droplets run while set"},
		"tank": {"refillPerTick": ref(energy[0], energy_address, "GAME"), "costPerTick": ref(energy[1], energy_address + 2, "GAME"), "capacity": ref(energy[2], energy_address + 4, "GAME"), "reserve": ref(levels[0][1], 0x800DCC62, "GAME", note="player+0x190/0x192; 0x7FFF is never drained"), "drain": "R0E 0x8010A2DC: tank -= cost each held tick; release when tank < cost", "refill": "GAME 0x800CF5F4: when !(0x13C&0x40) and +0xC9==0, tank += min(refill, capacity - tank, reserve)", "fullRefillTicks": energy[2] // max(1, energy[0]), "fireCheck": "GAME 0x800CC064: fires only if tank >= cost"},
		"levels": {"source": "GAME 0x800DCC60 rows {attack, energy, range, rapid}; player+0x26C..0x26F", "rows": levels, "rangeNote": "stored at private+0 and never read by the module"},
		"stream": {"update": "R0E 0x8010A608", "segmentCountMax": ref(count_max, 0x8010A64C), "growthPerTick": 1, "origin": "bone 4 (Bone_04, left hand) world cache player+0x4B0/2/4, shifted by scratch byte 0x1F8000B5", "emitBone": 4, "segment0": {"stepRaw": ref(step_base, 0x8010A96C), "droopRaw": ref(droop_base, 0x8010A964), "angles": "current player +0x28/+0x2A"}, "stepFormula": "0x120 + (i(i+1)/2 << 4) raw, rotated by aim via SLES 0x800419E8 (raw/16 units)", "droopFormula": "y += (-0x40 + (i(i+1)/2 << 2)) >> 4; +y is down", "aimLag": "segment i uses the aim segment i-1 had on the previous tick (pitch[16] block+8, yaw[16] block+0x28)", "unitsPerGodot": 256, "segments": segments,
			"collision": {"sweep": "GAME 0x800B18A4 from nozzle to point i (segment 0 is never tested)", "hitbox": ref([R.half(0x8010B27C + i * 2) for i in range(6)], 0x8010B27C), "actorHitMask": ref(0x220000, 0x8010A7BC), "onBlock": "spawn splash; new count = i (actor hit) or i - 1 (map); segment i is neither drawn nor hit this tick; records i..15 cleared"},
			"hit": {"register": "SLES 0x80042704(point, record, (actor[2]<<24)|0x200000|radius, damage|0x2000)", "hitWord": ref(0x2000, 0x8010AAE8, note="damage is 0 for every level (GAME 0x800CF3B8); halved when 0x8009C7FE==4"), "flags": ref(0x200000, 0x8010AABC), "radius": "(12 + 6i) >> 2", "recordOrigin": "record +4/+6 = nozzle X/Z", "targetResponse": "ST1ET 0x800EA600: hit word & 0x2000 -> dmg += ((0x100 - clamp(dist,0x80,0x100))*832>>7 + 0x3C0) >> 3 (224/tick within 128 units, 120 at 256+); fire out at strength <= 0x200; regrows 0x10/tick without hits"},
			"release": {"state": "R0E 0x8010A3B8", "detachPerTick": 1, "note": "segments below the detach count are not drawn or hit; both actors freed when detach == count"},
			"render": {"primitive": "textured billboard, GP0 0x2E (semi-transparent)", "texture": "hose_stream.png", "textureSource": {"archive": "COMMON/GAME.BIN section 0x34800 (VRAM 960,0 64x256 and CLUT row 496); no other COMMON/DAT upload touches this page region or CLUT", "tpage": hex(stream_tpage), "clut": hex(stream_clut), "v": stream_v, "frameSize": 32, "frames": 4, "texels": texel_modes(vram, stream_tpage, stream_clut, 0, stream_v, 128, 32)}, "blend": "additive (tpage 0x2F semi-transparency mode 1, B+F) for STP texels", "modulation": "texel * rgb / 128", "uFrame": "((frame@0x1F800006 + i) & 3) * 32, advances each tick", "rgb": ref(rgb(colour), 0x8010A9F0), "rgbStepPerSegment": ref(rgb(colour_step), 0x8010AB3C), "billboardSize": "10 * i (render entry +0x18, the field the splash particle fills with its size)",
				"glow": {"entry": "type 0x4000 light entry (consumer untraced)", "rgb": ref(rgb(glow), 0x8010AA0C), "rgbStepPerSegment": ref(rgb(glow_step), 0x8010AB18), "flagsByte": glow >> 24, "radius": "12 + 6i", "word": "0x22000000"}}},
		"splash": {"spawn": "SLES 0x8003E918 pool, class 0 (GAME 0x800D7FD8)", "subtype": ref(splash_subtype, 0x8010A7FC), "jitter": "pos += ((rand & 63) - 32) * (i + 1) >> 3 per axis (R0E 0x8010A82C)", "size": "12 + 6i, plus each frame's sizeAdd", "texture": "hose_splash.png", "textureSource": {"archive": "COMMON/GAME.BIN section 0x34800", "tpage": hex(splash_tpage), "clut": hex(splash_clut), "row": hex(splash_row), "frameTable": hex(frame_table), "flags": splash_flags}, "blend": "additive (tpage 0x2F)", "frames": splash_frames, "lifetimeTicks": sum(frame["durationTicks"] for frame in splash_frames), "sound": ref(splash_sound, splash_row + 6, "GAME", file=f"res://assets/audio/ST0F/fx_{splash_sound:03x}.wav", positional=True)},
		"droplets": {"actors": ref(R.imm(0x8010A1DC, (10,)), 0x8010A1DC), "slotsPerActor": ref(R.imm(0x8010AD2C, (10,)), 0x8010AD2C), "lifetimeTicks": ref(R.imm(0x8010B1E4), 0x8010B1E4), "spawn": "bone 4 cache; yaw = player yaw + ((rand >> 16) & 0x1FF) - 0x100", "velocityRaw": ref([0, R.imm(0x8010AFDC), R.imm(0x8010AFE8)], 0x8010AFDC, note="rotated by SLES 0x800421E0, applied along droplet yaw by SLES 0x80041894; raw/16 units per tick assumed"), "inheritPlayerMotion": "half the player's planar displacement, rotated into droplet yaw", "verticalJitter": "((rand >> 8) & 0xFF) - 0x80 + |yawJitter| / 2", "gravityRaw": ref(R.imm(0x8010AE24), 0x8010AE24), "render": "GP0 0x52 shaded line from old to new position, E1 0x220 (additive)", "rgbStart": ref(rgb(R.pair(0x8010AEC8, 0x8010AECC)), 0x8010AEC8, step=[1, 1, 2]), "rgbEnd": ref(rgb(R.pair(0x8010AED4, 0x8010AEF4)), 0x8010AED4, step=[3, 6, 6]), "colourFormula": "base + step * remaining life", "runsWhile": "player+0xC8 set; then live slots drain"},
		"underwater": {"condition": "player+0xBE != 0 (meaning unverified)", "state": "R0E 0x8010A488", "effect": "class 0x48 subtype 0 via SLES 0x8003E800, one per tick; visual unverified", "speed": ref(R.imm(0x8010A5A4), 0x8010A5A4), "life": "0x14 + (rand & 7)", "field0C": ref(R.imm(0x8010A574), 0x8010A574), "field0E": ref(R.imm(0x8010A5D0), 0x8010A5D0)},
		"sounds": {"start": ref(R.imm(0x8010A230), 0x8010A230, file="res://assets/audio/ST0F/fx_10d.wav", positional=False), "loopIntervalTicks": ref(R.imm(0x8010A164), 0x8010A164), "loopReplay": ref(R.imm(0x8010A368), 0x8010A368), "stop": ref(R.imm(0x8010A390), 0x8010A390, file="res://assets/audio/ST0F/fx_10e.wav", positional=False), "splash": ref(splash_sound, splash_row + 6, "GAME", file=f"res://assets/audio/ST0F/fx_{splash_sound:03x}.wav"), "bank": "PL00R0E.BIN section 0x4000 (logical bank 0x0F), exported by tools/audio.py"},
		"hud": hud}
	write_if_changed(output_dir / "weapon_0f.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return {"model": model, "clips": len(clips), "segments": len(segments), "splashFrames": len(splash_frames)}
if __name__ == "__main__": print(json.dumps(export_extinguisher(sys.argv[1] if len(sys.argv) > 1 else None)))

def export_special_modes(output=None):
	"""Per-stage argument of GAME 0x800CF4A8 (0 none, 1 equipped special, 2 force weapon 0x0F) issued by each STxxT area-load handler."""
	import capstone
	md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_LITTLE_ENDIAN); target = 0x0C000000 | ((0x800CF4A8 >> 2) & 0x3FFFFFF); stages = {}
	def a0_value(instruction):
		if instruction.mnemonic == "addiu" and instruction.op_str.startswith("$a0, $zero, "): return int(instruction.op_str.split(", ")[2], 0)
		if instruction.mnemonic in ("move", "addu", "or") and instruction.op_str in ("$a0, $zero", "$a0, $zero, $zero"): return 0
		if instruction.op_str.startswith("$a0,"): return None
		return False
	for path in sorted((ROOT / "build/disc-assets/DAT").glob("ST*T.BIN")):
		data = path.read_bytes(); stage = path.stem[:-1]; calls = []
		for offset in range(0x30, len(data) - 4, 4):
			if u32(data, offset) != target: continue
			address = 0x800E7000 + offset - 0x30; delay = next(md.disasm(data[offset + 4:offset + 8], address + 4)); slot = a0_value(delay)
			if slot is not False: calls.append({"call": "%#010x" % address, "values": [slot]}); continue
			window = list(md.disasm(data[offset - 64:offset], address - 64)); values = set(); index = len(window) - 1
			while index >= 0:
				value = a0_value(window[index])
				if value is not False: values.add(value); break
				index -= 1
			for position, instruction in enumerate(window):
				if not instruction.mnemonic.startswith("b") or instruction.mnemonic == "break": continue
				branch_target = int(instruction.op_str.split(", ")[-1], 0)
				if index >= 0 and window[index].address < branch_target <= address and position + 1 < len(window) and (value := a0_value(window[position + 1])) is not False: values.add(value)
			calls.append({"call": "%#010x" % address, "values": sorted(values, key=lambda value: -1 if value is None else value)})
		modes = sorted({value for call in calls for value in call["values"] if isinstance(value, int)})
		if calls: stages[stage] = {"mode": modes[0] if len(modes) == 1 else None, "candidates": modes, "calls": calls}
	result = {"source": "GAME 0x800CF4A8(mode): mode 0 -> active special 0x18C = 0; mode 1 -> 0x18C = 0x18E when +6 == 0 and +0x19F != 0; mode 2 -> 0x18E = 0x0F, then the mode-1 rule", "stages": stages}
	write_if_changed(Path(output) if output else ROOT / "assets/player/special_modes.json", json.dumps(result, indent=1) + "\n", encoding="utf-8"); return result
