from __future__ import annotations
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def signed16(value): return (value & 32767) - (value & 32768)
def signed32(value): return (value & 0x7FFFFFFF) - (value & 0x80000000)
class NativeCamera:
	def __init__(self):
		sys.path.insert(0, str(ROOT / "build/pydeps")); import unicorn
		from unicorn import mips_const
		self.unicorn = unicorn; self.register = mips_const; self.cpu = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); self.cpu.mem_map(0, 0x200000); self.cpu.mem_map(0x1F800000, 0x2000); self.cpu.mem_write(0x10000, (ROOT / "build/disc-assets/SLES_035.56").read_bytes()[0x800:]); self.cpu.mem_write(0xAD000, (ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes()[0x30:]); self.control = [0] * 32; self.data = [0] * 32; self.gpr = [getattr(mips_const, "UC_MIPS_REG_%d" % index) for index in range(32)]; self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.hardware)
	def write_data(self, index, value): self.data[index] = signed16(value) if index in (1, 3, 5, 8, 9, 10, 11) else value & 0xFFFFFFFF
	def hardware(self, cpu, address, size, context):
		word = struct.unpack("<I", cpu.mem_read(address & 0x1FFFFFFF, 4))[0]; opcode = word >> 26; source, target, index = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
		if opcode == 18:
			if source in (0, 2): cpu.reg_write(self.gpr[target], (self.control if source == 2 else self.data)[index] & 0xFFFFFFFF)
			elif source == 4: self.write_data(index, cpu.reg_read(self.gpr[target]))
			elif source == 6: self.control[index] = cpu.reg_read(self.gpr[target]) & 0xFFFFFFFF
			else: self.operation(word)
		elif opcode in (50, 58):
			pointer = (cpu.reg_read(self.gpr[source]) + signed16(word)) & 0x1FFFFFFF
			if opcode == 50: self.write_data(target, struct.unpack("<I", cpu.mem_read(pointer, 4))[0])
			else: cpu.mem_write(pointer, struct.pack("<I", self.data[target] & 0xFFFFFFFF))
		else: return
		cpu.reg_write(self.register.UC_MIPS_REG_PC, address + 4)
	def operation(self, word):
		function = word & 63; shift = 12 if word & (1 << 19) else 0; lower = 0 if word & 1024 else -32768; result = []; flag = 0
		if function in (61, 62): result = [signed32((self.data[8] * self.data[9 + row] + ((signed32(self.data[25 + row]) << shift) if function == 62 else 0)) >> shift) for row in range(3)]
		elif function == 18:
			matrix_kind, vector_kind, translation_kind = (word >> 17) & 3, (word >> 15) & 3, (word >> 13) & 3
			if matrix_kind == 3 or translation_kind == 2: raise ValueError("Native camera used an unsupported GTE matrix selector")
			base = matrix_kind * 8; packed = b"".join(struct.pack("<I", value & 0xFFFFFFFF) for value in self.control[base:base + 5]); matrix = struct.unpack_from("<9h", packed); vector = self.data[9:12] if vector_kind == 3 else [signed16(self.data[vector_kind * 2]), signed16(self.data[vector_kind * 2] >> 16), signed16(self.data[vector_kind * 2 + 1])]; translation = [0] * 3 if translation_kind == 3 else [signed32(self.control[5 + translation_kind * 8 + row]) for row in range(3)]
			for row in range(3):
				value = translation[row] << 12
				for column in range(3):
					value += matrix[row * 3 + column] * vector[column]
					if not -(1 << 43) <= value < (1 << 43): flag |= 1 << ((30 if value >= 0 else 27) - row)
					value = (value & ((1 << 43) - 1)) - (value & (1 << 43))
				result.append(signed32(value >> shift))
		else: raise ValueError("Native camera used unsupported GTE operation0x%02X" % function)
		for row, value in enumerate(result):
			self.data[25 + row] = value & 0xFFFFFFFF; self.data[9 + row] = max(lower, min(32767, value)); flag |= (1 << (24 - row)) if self.data[9 + row] != value else 0
		if function in (61, 62):
			channels = []
			for row, value in enumerate(result):
				value >>= 4; channels.append(max(0, min(255, value))); flag |= (1 << (21 - row)) if not 0 <= value <= 255 else 0
			self.data[20:23] = [self.data[21], self.data[22], (self.data[6] & 0xFF000000) | channels[0] | channels[1] << 8 | channels[2] << 16]
		self.control[31] = flag | ((1 << 31) if flag & 0x7F87E000 else 0)
	def call(self, function, arguments=()):
		self.cpu.reg_write(self.register.UC_MIPS_REG_SP, 0x801FF000); self.cpu.reg_write(self.register.UC_MIPS_REG_GP, 0x8007890C); self.cpu.reg_write(self.register.UC_MIPS_REG_RA, 0x80000800)
		for index, argument in enumerate(arguments[:4]): self.cpu.reg_write(self.gpr[4 + index], argument & 0xFFFFFFFF)
		if len(arguments) > 4: self.cpu.mem_write(0x1FF010, struct.pack("<I", arguments[4] & 0xFFFFFFFF))
		self.cpu.emu_start(function, 0x80000800, count=500000)
		if self.cpu.reg_read(self.register.UC_MIPS_REG_PC) != 0x80000800: raise ValueError("Native camera helper did not return")
	def orbit(self, focus, distance, pitch, yaw, roll=0):
		self.cpu.mem_write(0x1A0000, struct.pack("<4i", *focus, 0)); self.call(0x80015B6C, (0x801A0000, distance, pitch, yaw, roll)); return {"control": self.control[:8], "camera_state": list(struct.unpack("<40I", self.cpu.mem_read(0x7D010, 160)))}
def record_source(path, archive, index, payload=None):
	data = path.read_bytes(); size = struct.unpack_from("<I", data, 12)[0]; document = json.loads(data[20:20 + size]); document["asset"]["generator"] = "Native PBD source exporter"; document["extras"]["source_archive"] = archive; document["extras"].setdefault("vertex_color_source", "Source shading stream is not yet bound"); name = Path(archive).stem + "_model_%02d" % index
	if payload is not None and "source_surfaces" not in document["extras"]:
		mesh = struct.unpack_from("<I", payload, 8 + index * 16)[0]; high, hierarchy = struct.unpack_from("<I", payload, mesh + 4)[0], struct.unpack_from("<I", payload, mesh + 20)[0]; bone = struct.unpack_from("<I", payload, mesh + 16)[0]
		if bone:
			old = document["meshes"][0]["primitives"]; source_materials = document["extras"]["source_materials"]; lookup = {(source_materials[primitive["material"]]["slot"], source_materials[primitive["material"]].get("double_sided", False)): primitive for primitive in old}; cursors = {material: 0 for material in lookup}; surfaces = []; primitives = []
			for part in range(payload[mesh]):
				triangles, quads, _, _, tri_offset, quad_offset, _ = struct.unpack_from("<4B3I", payload, high + part * 16); flags = payload[hierarchy + part * 4 + 3]; counts = {}
				for face_count, offset, corners in ((triangles, tri_offset, 3), (quads, quad_offset, 6)):
					for face in range(face_count):
						packed = struct.unpack_from("<I", payload, offset + face * 12 + 8)[0]; material = ((packed >> 28) & 3, corners == 6 and bool(packed & 0x40000000)); counts[material] = counts.get(material, 0) + corners
				for material, count in counts.items():
					primitive = dict(lookup[material]); accessor = dict(document["accessors"][primitive["indices"]]); accessor["byteOffset"] = accessor.get("byteOffset", 0) + cursors[material] * (2 if accessor["componentType"] == 5123 else 4); accessor["count"] = count; accessor.pop("min", None); accessor.pop("max", None); primitive["indices"] = len(document["accessors"]); document["accessors"].append(accessor); cursors[material] += count; source_material = dict(document["materials"][primitive["material"]]); source_material["name"] = f"source_material_{material[0]}_sided_{int(material[1])}_part_{part}_uv_{flags & 3}"; primitive["material"] = len(document["materials"]); document["materials"].append(source_material); surface = {"surface": len(primitives), "source_part": part, "uv_stream": flags & 3, "default_hidden": bool(flags & 128), "source_material": material[0], "double_sided": material[1]}; primitive["extras"] = surface; primitives.append(primitive); surfaces.append(surface)
			document["meshes"][0]["primitives"] = primitives; document["extras"]["source_surfaces"] = surfaces
	for mesh in document.get("meshes", []): mesh["name"] = name
	for node in document.get("nodes", []):
		if "mesh" in node: node["name"] = name
	encoded = json.dumps(document, separators=(",", ":")).encode(); encoded += b" " * (-len(encoded) % 4); tail = data[20 + size:]; write_if_changed(path, struct.pack("<3I", 0x46546C67, 2, 20 + len(encoded) + len(tail)) + struct.pack("<2I", len(encoded), 0x4E4F534A) + encoded + tail)
	return document["extras"].get("source_surfaces", [])
def opening_timeline(overlay):
	start = 0x30 + 0x800F2374 - 0x800E7000; result = []
	for offset in range(start, len(overlay) - 7, 8):
		phase, step, duration, callback = struct.unpack_from("<BBhI", overlay, offset)
		if phase == 255: break
		result.append({"phase": phase, "step": step, "duration": duration, "callback": hex(callback), "source_file_offset": hex(offset), "source_ram": hex(0x800E7000 + offset - 0x30)})
	return result
def opening_commands(overlay):
	offset = 0x30 + 0x800F1B28 - 0x800E7000; end = 0x30 + 0x800F2374 - 0x800E7000; result = []
	while offset < end:
		word = struct.unpack_from("<I", overlay, offset)[0]; opcode = word >> 24; size = 16 if 0x10 <= opcode <= 0x1A else 8 if opcode in (0x40, 0x41) else 20 if opcode == 0x42 else 4
		if opcode not in set(range(8)) | set(range(0x10, 0x1C)) | set(range(0x20, 0x23)) | set(range(0x30, 0x33)) | set(range(0x40, 0x43)) | set(range(0x50, 0x58)) | {255} or offset + size > end: raise ValueError("Invalid native opening command stream")
		words = list(struct.unpack_from("<" + "I" * (size // 4), overlay, offset)); item = {"opcode": opcode, "words": words, "source_ram": hex(0x800E7000 + offset - 0x30)}
		if opcode in (0x40, 0x41):
			pointer = words[1]; source_offset = 0x30 + pointer - 0x800E7000; item["actor_record"] = {"source_ram": hex(pointer), "bytes": overlay[source_offset:source_offset + 20].hex()}
		result.append(item); offset += size
	if not result or result[-1]["opcode"] != 255 or offset != end: raise ValueError("Opening commands do not terminate at the original timeline")
	return result
def opening_callbacks(overlay):
	def read(address, size):
		offset = 0x30 + address - 0x800E7000
		if offset < 0 or offset + size > len(overlay): raise ValueError("Opening callback data is outside ST02T")
		return overlay[offset:offset + size]
	def props(address):
		result = []; offset = 0
		while True:
			raw = read(address + offset, 12)
			if struct.unpack_from("<i", raw)[0] < 0: break
			variant, x, y, z, yaw = raw[0], *struct.unpack_from("<3hH", raw, 4); record = bytearray(20); record[:8] = bytes((3, 255, 0x60, 10, 0x16, 0, variant, 0)); struct.pack_into("<3hH", record, 12, x, y, z, yaw); result.append({"source_ram": hex(address + offset), "source_bytes": raw.hex(), "bytes": record.hex(), "slot": -(address + offset), "untracked": True, "pool": "type60_flags2", "constructor": "ST02T0x800F025C"}); offset += 12
		return result
	def schedule(address):
		result = []; offset = 0
		while True:
			raw = read(address + offset, 12); tick = struct.unpack_from("<h", raw)[0]
			if tick < 0: break
			x, y, z, parameter = struct.unpack_from("<3hH", raw, 4); result.append({"tick": tick, "source_ram": hex(address + offset), "source_bytes": raw.hex(), "effect": {"class": 14, "variant": raw[2], "slot": -(address + offset), "x": x, "y": y, "z": z, "parameter": parameter}, "constructor": "SLES0x8003E9D8/ST02T0x800F0328"}); offset += 12
		return result
	callbacks = {"%d:%d" % (item["phase"], item["step"]): {"source_callback": item["callback"], "spawn": [], "actions": [], "pool_clears": []} for item in opening_timeline(overlay)}
	for key, address in (("2:0", 0x800F247C), ("2:2", 0x800F24E8), ("2:4", 0x800F2584), ("2:6", 0x800F2584)): callbacks[key]["spawn"] = props(address)
	for key, address in (("2:2", 0x800F2650), ("2:3", 0x800F26B0), ("2:4", 0x800F26E0), ("2:5", 0x800F2734), ("2:6", 0x800F27AC), ("2:12", 0x800F2818), ("2:13", 0x800F2860), ("2:14", 0x800F28F0)): callbacks[key]["actions"].extend(schedule(address)); callbacks[key]["schedule_source"] = hex(address)
	for key in ("2:1", "2:3", "2:5", "2:7"): callbacks[key]["pool_clears"] = [{"tick": 0, "mask": 128, "flags": 128, "source": "SLES0x8003D658", "pool": "type60_flags2"}]
	callbacks["1:6"]["actions"] = [{"tick": 0, "slot": 3, "position": [-24, 3928, 5900], "fields": {"0x0C": 1}, "source": "ST02T0x800EF704; upper-halfwords+0x12/+0x16/+0x1A"}, {"tick": 0, "slot": 5, "fields": {"0x0C": 1}, "source": "ST02T0x800EF754 context+0x40"}]
	callbacks["0:0"]["ready_gate"] = {"source": "ST02T0x800EF4F8", "states": ["wait fade idle;1392C(16);1B9A4(1)", "wait fade idle", "wait XA/CDready;advance1"]}
	callbacks["0:2"]["ready_gate"] = {"tick": 350, "source": "ST02T0x800EF658", "advance": 1}
	callbacks["1:13"]["ready_gate"] = {"tick": 100, "source": "ST02T0x800EF79C", "archive_id": 63, "bank": "ST0201", "xa_id": 12, "pool_clear": {"mask": 4094, "flags": 128}, "advance": 1}
	callbacks["2:6"]["ready_gate"] = {"tick": 40, "source": "ST02T0x800EFAD8", "archive_id": 64, "bank": "ST0202", "xa_id": 13, "advance": 1}
	callbacks["2:11"]["ready_gate"] = {"source": "ST02T0x800EFD08", "archive_id": 65, "bank": "ST0203", "xa_id": 21, "advance": 1}
	callbacks["2:14"]["ready_gate"] = {"source": "ST02T0x800EFEA8", "states": ["set bufferCount3;counter0", "wait phaseTime>0", "VRAMwipe128updates;remove source actors;spawnF2584", "at phaseTime300 requestfade18", "wait fade idle;advance1"], "props_after_wipe": props(0x800F2584), "fade_tick": 300, "advance": 1}
	callbacks["2:9"]["overlay"] = {"ticks": [0, 125], "counter": 4, "source": "ST02T0x800F00E0", "clut": 0x3DC0, "tpage": 37, "uv": [0, 128, 48, 64]}
	callbacks["2:10"]["overlay"] = {"tick_range": [13, 43], "upper_exclusive": True, "source": "ST02T0x800F01A4", "clut": 0x3DC0, "tpage": 37, "uv": [0, 192, 64, 64], "alternate_u": 64}
	records = {"0x800f1a38": [{"source_ram": hex(0x800F1A38 + offset), "bytes": read(0x800F1A38 + offset, 20).hex()} for offset in (0, 20, 40, 60)]}
	return callbacks, records
def opening_xa(overlay):
	entries = []
	for index, phase in ((1, "0:0"), (12, "1:13"), (13, "2:6"), (21, "2:11")):
		address = 0x800F0E0C + index * 8; offset = 0x30 + address - 0x800E7000; raw = overlay[offset:offset + 8]; start = (raw[1] << 16) | struct.unpack_from("<H", raw, 2)[0]; end = (raw[5] << 16) | struct.unpack_from("<H", raw, 6)[0]
		if raw[0] != 2: raise ValueError("Opening XA descriptor no longer selects original PAL_37 archive")
		entries.append({"id": index, "phase": phase, "source_ram": hex(address), "source_bytes": raw.hex(), "archive": "XA/PAL_37.XA", "native_file_index": 337, "sector_start": start, "sector_end": end, "channel": raw[4] & 31, "flags": raw[4] & 128})
	return {"source": "ST02T0x800E71F4 initializes80078DD8=800F0E0C; SLES0x8001B9D0 indexes8-byte descriptors; SLES0x8001B864 resolves800695F4[2]=337", "descriptor_table": "0x800F0E0C", "entries": entries}
def native_actor_controls(overlay, actor_class, functions):
	result = {}; native = NativeCamera(); cpu = native.cpu; cpu.mem_write(0xE7000, overlay[0x30:0x30 + 0xB9B8]); actor = 0x80180000; private = actor + 0x14C; context = 0x8007CEC0; writes = []; active_tick = [-1]
	def write_control(emulator, address, size, userdata):
		word = struct.unpack("<I", emulator.mem_read(address & 0x1FFFFFFF, 4))[0]
		if word >> 26 != 40 or active_tick[0] < 0: return
		base, value = (word >> 21) & 31, (word >> 16) & 31; pointer = (emulator.reg_read(native.gpr[base]) + signed16(word)) & 0x1FFFFFFF
		if pointer == (actor + 0xA0) & 0x1FFFFFFF: writes.append({"tick": active_tick[0], "control": emulator.reg_read(native.gpr[value]) & 255, "source_pc": hex(address)})
	cpu.hook_add(native.unicorn.UC_HOOK_CODE, write_control)
	for mode, function in enumerate(functions):
		steps = {}
		for step in range(15):
			active_tick[0] = -1; cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x400)); writes.clear()
			if actor_class == 22:
				archive, payload = actor_archive(ROOT / "build/opening/ST02_models.bin"); mesh = archive["models"][0]["mesh_offset"]; dimensions = struct.unpack_from("<I", payload, mesh + 0x38)[0]; cpu.mem_write((actor + 0xD8) & 0x1FFFFFFF, struct.pack("<2I", ((dimensions & 0x7F) << 16) | ((dimensions & 0x7F00) << 15), (dimensions & 0x7F0000) | ((dimensions & 0x7F000000) >> 1))); native.call(0x80041318, (private, 0x800F1220, 0x800F12F0)); native.call(0x80041338, (private, 0, 0)); native.call(0x80041348, (private, 0, 0))
			for tick in range(931):
				cpu.mem_write((context + 0x11) & 0x1FFFFFFF, bytes((step,))); cpu.mem_write((context + 0xC) & 0x1FFFFFFF, struct.pack("<I", tick)); active_tick[0] = tick
				try: native.call(function, (actor, private, context))
				except Exception as error: raise RuntimeError(f"Actor controller class{actor_class} mode{mode} step{step} tick{tick} PC{hex(cpu.reg_read(native.register.UC_MIPS_REG_PC))}") from error
			if writes: steps[str(step)] = list(writes)
		result[str(mode)] = steps
	return {str(actor_class): result}
def native_actor_faces(overlay, actor_class, functions):
	native = NativeCamera(); cpu = native.cpu; cpu.mem_write(0xE7000, overlay[0x30:0x30 + 0xB9B8]); actor = 0x80180000; private = actor + 0x14C; context = 0x8007CEC0; archive, payload = actor_archive(ROOT / "build/opening/ST02_models.bin"); model = archive["models"][0 if actor_class == 22 else 1]; mesh = model["mesh_offset"]; dimensions = struct.unpack_from("<I", payload, mesh + 0x38)[0]; hierarchy = model["mesh"]["hierarchy_offset"]; count = model["mesh"]["lod_primitive_counts"][0]; result = {}
	motion = {}
	for mode, function in enumerate(functions):
		cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x400)); cpu.mem_write((actor + 0xEC) & 0x1FFFFFFF, payload[hierarchy:hierarchy + count * 4]); cpu.mem_write((actor + 0xD8) & 0x1FFFFFFF, struct.pack("<2I", ((dimensions & 0x7F) << 16) | ((dimensions & 0x7F00) << 15), (dimensions & 0x7F0000) | ((dimensions & 0x7F000000) >> 1))); steps = {}; motion_steps = {}; previous = None; previous_forward = None
		if actor_class == 22: native.call(0x80041318, (private, 0x800F1220, 0x800F12F0)); native.call(0x80041338, (private, 0, 0)); native.call(0x80041348, (private, 0, 0))
		else: cpu.mem_write(private & 0x1FFFFFFF, struct.pack("<I", 0x800F1338)); native.call(0x800E8E2C, (private, 0, 0))
		for segment in [item for item in opening_timeline(overlay) if item["phase"] == mode + 1]:
			step = segment["step"]; duration = segment["duration"] if segment["duration"] >= 0 else 931; changes = []; movement = []
			for tick in range(duration):
				before_yaw = struct.unpack("<H", cpu.mem_read((actor + 0x2A) & 0x1FFFFFFF, 2))[0]
				cpu.mem_write((context + 0x11) & 0x1FFFFFFF, bytes((step,))); cpu.mem_write((context + 0xC) & 0x1FFFFFFF, struct.pack("<I", tick)); native.call(function, (actor, private, context)); native.call(0x8004152C if actor_class == 22 else 0x800E8E3C, (actor, private)); uv = list(struct.unpack("<2I", cpu.mem_read((actor + 0xD8) & 0x1FFFFFFF, 8))); hidden = [index for index in range(count) if cpu.mem_read((actor + 0xEF + index * 4) & 0x1FFFFFFF, 1)[0] & 128]; state = {"uv_words": uv, "hidden_parts": hidden}
				if state != previous: changes.append({"tick": tick, **state}); previous = state
				forward = struct.unpack("<h", cpu.mem_read((actor + 0x3C) & 0x1FFFFFFF, 2))[0]; yaw_delta = (struct.unpack("<H", cpu.mem_read((actor + 0x2A) & 0x1FFFFFFF, 2))[0] - before_yaw) & 4095
				if tick == 0 or forward != previous_forward or yaw_delta: movement.append({"tick": tick, "forward": forward, "yaw_delta": yaw_delta})
				previous_forward = forward
			if changes: steps[str(step)] = changes
			motion_steps[str(step)] = movement
		result[str(mode)] = steps
		motion[str(mode)] = motion_steps
	return {"faces": {str(actor_class): result}, "motion": {str(actor_class): motion}}
def native_actor_motion(overlay, actor_class, functions):
	native = NativeCamera(); cpu = native.cpu; cpu.mem_write(0xE7000, overlay[0x30:0x30 + 0xB9B8]); actor = 0x80180000; private = actor + 0x14C; context = 0x8007CEC0; modes = {}
	for mode, function in enumerate(functions):
		steps = {}
		for step in range(15):
			cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x400)); previous = None; changes = []
			for tick in range(931):
				cpu.mem_write((context + 0x11) & 0x1FFFFFFF, bytes((step,))); cpu.mem_write((context + 0xC) & 0x1FFFFFFF, struct.pack("<I", tick)); yaw = struct.unpack("<H", cpu.mem_read((actor + 0x2A) & 0x1FFFFFFF, 2))[0]; native.call(function, (actor, private, context)); forward = struct.unpack("<h", cpu.mem_read((actor + 0x3C) & 0x1FFFFFFF, 2))[0]; next_yaw = struct.unpack("<H", cpu.mem_read((actor + 0x2A) & 0x1FFFFFFF, 2))[0]; delta = (next_yaw - yaw) & 4095
				if forward != previous or delta: changes.append({"tick": tick, "forward": forward, "yaw_delta": delta}); previous = forward
			steps[str(step)] = changes
		modes[str(mode)] = steps
	return {str(actor_class): modes}
def opening_actor_timelines(overlay):
	controls = {}; faces = {}; motion = {}
	for actor_class, functions in ((22, (0x800E75F4, 0x800E7D18)), (26, (0x800E87F8, 0x800E8C10))):
		controls.update(native_actor_controls(overlay, actor_class, functions)); state = native_actor_faces(overlay, actor_class, functions); faces.update(state["faces"]); motion.update(state["motion"])
	functions = (0x800E9130, 0x800E9174, 0x800E91EC, 0x800E9264); controls.update(native_actor_controls(overlay, 29, functions)); motion.update(native_actor_motion(overlay, 29, functions))
	return {"actor_controls": controls, "actor_faces": faces, "actor_motion": motion, "actor_face_source": {"class22": "ST02T0x800E73F4 constructor: SLES0x80041318(F1220,F12F0); update0x8004152C; texture state0x80041204", "class26": "ST02T0x800E8614 constructor tableF1338; update0x800E8E3C; cached hierarchy flags part1/part11", "sampling": "Unchanged native MIPS controllers and face update helpers; source positive segment durations, negative ready-gate segments sampled through tick930", "uv_renderer": "SLES0x80024B60 selects hierarchyFlags&3; 0x8002517C packed16-bit UV addition; 0x800251AC adds descriptor top2bits to texture page", "motion": "Controller actor+0x3C forward speed and actor+0x2A yaw changes; SLES0x800417AC rotates -forward into fixed16 position increments"}}
def native_texture_uploads(source, vram):
	for offset in range(0, len(source) - 47, 0x800):
		kind, size = struct.unpack_from("<2I", source, offset)
		if kind != 2: continue
		px, py, colors, palettes, x, y, width, height = struct.unpack_from("<8H", source, offset + 12); palette_size, image_size = colors * palettes * 2, width * height * 2
		if not palette_size + image_size or px + colors > 1024 or py + palettes > 512 or x + width > 1024 or y + height > 512: continue
		if image_size and size == image_size + 0x7D0: image_start = offset + 0x800
		elif size == palette_size + image_size: image_start = offset + 0x30 + palette_size
		else: continue
		if offset + 0x30 + palette_size > len(source) or image_start + image_size > len(source): raise ValueError("Native opening texture upload exceeds source archive")
		cursor = offset + 0x30
		for row in range(palettes):
			start = ((py + row) * 1024 + px) * 2; count = colors * 2; vram[start:start + count] = source[cursor:cursor + count]; cursor += count
		cursor = image_start
		for row in range(height):
			start = ((y + row) * 1024 + x) * 2; count = width * 2; vram[start:start + count] = source[cursor:cursor + count]; cursor += count
	return vram
def export_opening(dat_dir=None, output_dir=None):
	dat_dir = Path(dat_dir) if dat_dir else ROOT / "build/disc-assets/DAT"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/opening"; output_dir.mkdir(parents=True, exist_ok=True); work = ROOT / "build/opening"; work.mkdir(parents=True, exist_ok=True); export_maps("ST02", dat_dir, output_dir / "levels"); overlay_path = dat_dir / "ST02T.BIN"; overlay = overlay_path.read_bytes(); stage_vram, _ = textures(overlay_path); stage_vram = native_texture_uploads(overlay, stage_vram); banks = []
	actor_vram = bytearray(stage_vram)
	for bank in ("ST02", "ST0201", "ST0202", "ST0203"):
		path = dat_dir / (bank + ".BIN"); source = path.read_bytes(); archive_path = path; section = None
		if bank == "ST02":
			payload, section = decompress_section(source, 0x7800); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); archive_path = work / "ST02_models.bin"; write_if_changed(archive_path, header + payload)
		archive, payload = actor_archive(archive_path); vram = native_texture_uploads(source, bytearray(actor_vram)); actor_vram = vram; normalized = work / (bank + "_vram.bin"); header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); write_if_changed(normalized, header + vram); directory = output_dir / bank; directory.mkdir(parents=True, exist_ok=True); models = []
		for model in archive["models"]:
			if not model.get("mesh_offset"): continue
			index = model["index"]; destination = directory / ("model_%02d.glb" % index); metadata = export_actor_model(payload, index, normalized, destination) if model["mesh"]["bone_count"] else export_static_actor(payload, index, normalized, destination); metadata["source_surfaces"] = record_source(destination, path.name, index, payload); metadata["source_archive"] = path.name; metadata["model_file"] = destination.relative_to(output_dir).as_posix(); models.append({**model, "export": metadata})
		banks.append({"archive": "DAT/" + path.name, "sha256": hashlib.sha256(source).hexdigest(), "decoded_section": section, "models": models})
	manifest = {"stage": "ST02", "source": {"overlay": "DAT/ST02T.BIN", "sha256": hashlib.sha256(overlay).hexdigest(), "stage_initializer": "0x800E712C", "area_initializer": "0x800E7228", "startup_driver": "0x800EF1E4", "startup_helper": "GAME0x800C0C5C", "command_stream": "RAM0x800F1B28", "timeline": "RAM0x800F2374", "seed": "0x873CA9E6", "command_interpreter": "GAME0x800C1204", "timeline_update": "GAME0x800C0D70", "timeline_callback_dispatch": "ST02T0x800EF2AC"}, "commands": opening_commands(overlay), "timeline": opening_timeline(overlay), "levels": "levels/ST02/manifest.json", "actor_banks": banks}; callbacks, records = opening_callbacks(overlay); manifest.update(callbacks=callbacks, callback_records=records, xa=opening_xa(overlay), native_floor_shapes=export_floor_shapes(dat_dir / "ST02.BIN"), **opening_actor_timelines(overlay)); target = output_dir / "manifest.json"; write_if_changed(target, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
def opening_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path); parser.add_argument("--output-dir", type=Path); args = parser.parse_args(); manifest = export_opening(args.dat_dir, args.output_dir); print(json.dumps({"actor_models": sum(len(bank["models"]) for bank in manifest["actor_banks"]), "stage": manifest["stage"]}))

def decode_effect_tables():
	path = ROOT / "build/disc-assets/DAT/ST02T.BIN"; source = path.read_bytes(); executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); output = ROOT / "assets/opening/effects"; output.mkdir(parents=True, exist_ok=True); vram, _ = textures(path); vram = native_texture_uploads(source, vram); descriptors = []
	for index in range(7):
		x, y, primary_x, primary_y, alternate_x, alternate_y = struct.unpack_from("<6H", source, 0x30 + 0x800F15B4 - 0x800E7000 + index * 12); tpage = (x >> 6) | ((y & 256) >> 4) | ((y & 512) << 2); item = {"index": index, "tpage": tpage}
		for role, px, py in (("primary", primary_x, primary_y), ("alternate", alternate_x, alternate_y)):
			clut = (py << 6) | (px >> 4); filename = "atmosphere_%d_%s.png" % (index, role); write_if_changed(output / filename, texture_page(vram, clut, tpage)); item[role] = {"texture": "res://assets/opening/effects/" + filename, "clut": clut}
		descriptors.append(item)
	trig = [struct.unpack_from("<2h", executable, 0x800 + 0x80073E4C - 0x80010000 + phase * 64 * 4) for phase in range(64)]; manifest = {"source": {"overlay": "DAT/ST02T.BIN", "sha256": hashlib.sha256(source).hexdigest(), "atmosphere_dispatch": "0x800EAB80", "opening_atmosphere": "0x800ECC24", "texture_table": "0x800F15B4", "lightning_dispatch": "0x800EE430", "lightning_init": "0x800EE46C", "lightning_flash": "0x800EEC58", "lightning_colors": "0x800EF164", "trig_init": "SLES0x800112BC", "rng_xor": "0x873CA9E5"}, "textures": descriptors, "atmosphere": {"variant": 5, "parameter": 16777217, "initial_phases": [index * 512 for index in range(8)], "background_uv_rows": list(source[0x30 + 0x800F1700 - 0x800E7000:0x30 + 0x800F1700 - 0x800E7000 + 10]), "background_columns": 20, "background_rows": 10, "background_uv_y": 224, "background_tile_size": 16, "strip_columns": 11, "strip_size": [32, 80], "strip_y": 160, "phase_limit": 4096, "phase_shift": 4, "camera_yaw_multiplier": 8}, "lightning": {"segments": 16, "colors": [[((value * 8160) >> 8)] * 3 for value in range(7, 0, -1)], "view_center": [0, 0, 192], "radius_depth_numerator": 5, "radius_depth_denominator": 6, "blend": "add", "radial_pattern": list(source[0x30 + 0x800F1794 - 0x800E7000:0x30 + 0x800F1794 - 0x800E7000 + 16])}, "trig64": trig}; return manifest
def export_opening_effects():
	manifest = decode_effect_tables(); source = (ROOT / "build/disc-assets/DAT/ST02T.BIN").read_bytes(); executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); output = ROOT / "assets/opening/effects"; vram, _ = textures(ROOT / "build/disc-assets/DAT/ST02T.BIN"); vram = native_texture_uploads(source, vram); banks = {}
	for bank in ("ST02", "ST0201", "ST0202", "ST0203"):
		vram = native_texture_uploads((ROOT / ("build/disc-assets/DAT/" + bank + ".BIN")).read_bytes(), vram); directory = output / bank; directory.mkdir(exist_ok=True); descriptors = []
		for entry in manifest["textures"]:
			item = {"index": entry["index"], "tpage": entry["tpage"]}
			for role in ("primary", "alternate"):
				filename = "atmosphere_%d_%s.png" % (item["index"], role); write_if_changed(directory / filename, texture_page(vram, entry[role]["clut"], entry["tpage"])); item[role] = {"texture": "res://assets/opening/effects/" + bank + "/" + filename, "clut": entry[role]["clut"]}
			descriptors.append(item)
		cloud_palettes = {}
		for offset in (0, 1, 2, 3, 4, 8, 9, 10, 11, 12):
			filename = "cloud_%02d.png" % offset; write_if_changed(directory / filename, texture_page(vram, 0x7DC0 + offset, 28)); cloud_palettes[str(offset)] = "res://assets/opening/effects/" + bank + "/" + filename
		banks[bank] = {"textures": descriptors, "cloud_palettes": cloud_palettes}
	def table(address, count, fmt): return list(struct.unpack_from("<" + fmt * count, source, 0x30 + address - 0x800E7000))
	manifest["texture_banks"] = banks; manifest["trig4096"] = [list(struct.unpack_from("<2h", executable, 0x800 + 0x80073E4C - 0x80010000 + phase * 4)) for phase in range(4096)]; manifest["clouds"] = {"variant0": {"height": table(0x800F1638, 9, "h"), "radius": table(0x800F164C, 9, "h"), "half_size": table(0x800F1660, 9, "h"), "clut_offset": table(0x800F167C, 9, "b"), "uv_x": table(0x800F1674, 8, "B")}, "variant2": {"height": table(0x800F16C0, 4, "h"), "radius": table(0x800F16CC, 4, "h"), "half_size": table(0x800F16D8, 4, "h"), "clut_offset": table(0x800F16EC, 4, "b"), "uv_x": table(0x800F16E4, 8, "B")}}; manifest["screen_atmosphere"] = {"variant3_rows": table(0x800F16F4, 5, "B"), "variant4_rows": table(0x800F16FC, 6, "B"), "variant5_rows": table(0x800F1700, 10, "B")}; manifest["variant6_vertices"] = [table(0x800F170C + index * 8, 3, "h") for index in range(4)]; manifest["supported_variants"] = {"class18": [0, 2, 3, 4, 5, 6], "class14": [1, 2]}; manifest["renderer_adapters"] = ["Screen atmosphere backgrounds use CanvasLayer -1; native ordering-table interleaving with scene geometry is not reproduced.", "World cloud billboards use depth-tested Godot meshes; native GTE saturation and PSX affine texture sampling are not reproduced."]
	manifest["clouds"]["variant1"] = {"height": table(0x800F1688, 4, "h"), "radius": table(0x800F1698, 4, "h"), "half_size": table(0x800F16A8, 4, "h"), "radius_jitter": table(0x800F16A8, 8, "h"), "clut_offset": table(0x800F16B8, 4, "b"), "uv_x": [0, 64, 128, 0, 64, 128, 0, 64]}; manifest["supported_variants"]["class18"].append(1); manifest["source"]["companion_constructor"] = "0x800EABF4..0x800EAC54"
	destination = output / "manifest.json"; write_if_changed(destination, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
from models import actor_archive
from models import export_actor_model
from world import export_maps
from world import textures
from models import export_static_actor
from disc import decompress_section, write_if_changed
from world import export_floor_shapes
from world import texture_page
if __name__ == '__main__':
	import sys
	commands = {'opening': 'opening_cli', 'opening-effects': 'export_opening_effects'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
