from __future__ import annotations
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
import disc
import shutil
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build/pydeps"))
disc.ensure_package("unicorn", "unicorn==2.1.4")
import unicorn
from unicorn import mips_const as M
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
	encoded = json.dumps(document, separators=(",", ":")).encode(); encoded += b" " * (-len(encoded) % 4); tail = data[20 + size:]; write_output(path, struct.pack("<3I", 0x46546C67, 2, 20 + len(encoded) + len(tail)) + struct.pack("<2I", len(encoded), 0x4E4F534A) + encoded + tail)
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
			payload, section = decompress_section(source, 0x7800); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); archive_path = work / "ST02_models.bin"; write_output(archive_path, header + payload)
		archive, payload = actor_archive(archive_path); vram = native_texture_uploads(source, bytearray(actor_vram)); actor_vram = vram; normalized = work / (bank + "_vram.bin"); header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); write_output(normalized, header + vram); directory = output_dir / bank; directory.mkdir(parents=True, exist_ok=True); models = []
		for model in archive["models"]:
			if not model.get("mesh_offset"): continue
			index = model["index"]; destination = directory / ("model_%02d.glb" % index); metadata = export_actor_model(payload, index, normalized, destination) if model["mesh"]["bone_count"] else export_static_actor(payload, index, normalized, destination); metadata["source_surfaces"] = record_source(destination, path.name, index, payload); metadata["source_archive"] = path.name; metadata["model_file"] = destination.relative_to(output_dir).as_posix(); models.append({**model, "export": metadata})
		banks.append({"archive": "DAT/" + path.name, "sha256": hashlib.sha256(source).hexdigest(), "decoded_section": section, "models": models})
	manifest = {"stage": "ST02", "source": {"overlay": "DAT/ST02T.BIN", "sha256": hashlib.sha256(overlay).hexdigest(), "stage_initializer": "0x800E712C", "area_initializer": "0x800E7228", "startup_driver": "0x800EF1E4", "startup_helper": "GAME0x800C0C5C", "command_stream": "RAM0x800F1B28", "timeline": "RAM0x800F2374", "seed": "0x873CA9E6", "command_interpreter": "GAME0x800C1204", "timeline_update": "GAME0x800C0D70", "timeline_callback_dispatch": "ST02T0x800EF2AC"}, "commands": opening_commands(overlay), "timeline": opening_timeline(overlay), "levels": "levels/ST02/manifest.json", "actor_banks": banks}; callbacks, records = opening_callbacks(overlay); manifest.update(callbacks=callbacks, callback_records=records, xa=opening_xa(overlay), native_floor_shapes=export_floor_shapes(dat_dir / "ST02.BIN"), **opening_actor_timelines(overlay)); target = output_dir / "manifest.json"; write_output(target, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
def opening_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path); parser.add_argument("--output-dir", type=Path); args = parser.parse_args(); manifest = export_opening(args.dat_dir, args.output_dir); print(json.dumps({"actor_models": sum(len(bank["models"]) for bank in manifest["actor_banks"]), "stage": manifest["stage"]}))

def decode_effect_tables():
	path = ROOT / "build/disc-assets/DAT/ST02T.BIN"; source = path.read_bytes(); executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); output = ROOT / "assets/opening/effects"; output.mkdir(parents=True, exist_ok=True); vram, _ = textures(path); vram = native_texture_uploads(source, vram); descriptors = []
	for index in range(7):
		x, y, primary_x, primary_y, alternate_x, alternate_y = struct.unpack_from("<6H", source, 0x30 + 0x800F15B4 - 0x800E7000 + index * 12); tpage = (x >> 6) | ((y & 256) >> 4) | ((y & 512) << 2); item = {"index": index, "tpage": tpage}
		for role, px, py in (("primary", primary_x, primary_y), ("alternate", alternate_x, alternate_y)):
			clut = (py << 6) | (px >> 4); filename = "atmosphere_%d_%s.png" % (index, role); write_output(output / filename, texture_page(vram, clut, tpage)); item[role] = {"texture": "res://assets/opening/effects/" + filename, "clut": clut}
		descriptors.append(item)
	trig = [struct.unpack_from("<2h", executable, 0x800 + 0x80073E4C - 0x80010000 + phase * 64 * 4) for phase in range(64)]; manifest = {"source": {"overlay": "DAT/ST02T.BIN", "sha256": hashlib.sha256(source).hexdigest(), "atmosphere_dispatch": "0x800EAB80", "opening_atmosphere": "0x800ECC24", "texture_table": "0x800F15B4", "lightning_dispatch": "0x800EE430", "lightning_init": "0x800EE46C", "lightning_flash": "0x800EEC58", "lightning_colors": "0x800EF164", "trig_init": "SLES0x800112BC", "rng_xor": "0x873CA9E5"}, "textures": descriptors, "atmosphere": {"variant": 5, "parameter": 16777217, "initial_phases": [index * 512 for index in range(8)], "background_uv_rows": list(source[0x30 + 0x800F1700 - 0x800E7000:0x30 + 0x800F1700 - 0x800E7000 + 10]), "background_columns": 20, "background_rows": 10, "background_uv_y": 224, "background_tile_size": 16, "strip_columns": 11, "strip_size": [32, 80], "strip_y": 160, "phase_limit": 4096, "phase_shift": 4, "camera_yaw_multiplier": 8}, "lightning": {"segments": 16, "colors": [[((value * 8160) >> 8)] * 3 for value in range(7, 0, -1)], "view_center": [0, 0, 192], "radius_depth_numerator": 5, "radius_depth_denominator": 6, "blend": "add", "radial_pattern": list(source[0x30 + 0x800F1794 - 0x800E7000:0x30 + 0x800F1794 - 0x800E7000 + 16])}, "trig64": trig}; return manifest
def export_opening_effects():
	manifest = decode_effect_tables(); source = (ROOT / "build/disc-assets/DAT/ST02T.BIN").read_bytes(); executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); output = ROOT / "assets/opening/effects"; vram, _ = textures(ROOT / "build/disc-assets/DAT/ST02T.BIN"); vram = native_texture_uploads(source, vram); banks = {}
	for bank in ("ST02", "ST0201", "ST0202", "ST0203"):
		vram = native_texture_uploads((ROOT / ("build/disc-assets/DAT/" + bank + ".BIN")).read_bytes(), vram); directory = output / bank; directory.mkdir(exist_ok=True); descriptors = []
		for entry in manifest["textures"]:
			item = {"index": entry["index"], "tpage": entry["tpage"]}
			for role in ("primary", "alternate"):
				filename = "atmosphere_%d_%s.png" % (item["index"], role); write_output(directory / filename, texture_page(vram, entry[role]["clut"], entry["tpage"])); item[role] = {"texture": "res://assets/opening/effects/" + bank + "/" + filename, "clut": entry[role]["clut"]}
			descriptors.append(item)
		cloud_palettes = {}
		for offset in (0, 1, 2, 3, 4, 8, 9, 10, 11, 12):
			filename = "cloud_%02d.png" % offset; write_output(directory / filename, texture_page(vram, 0x7DC0 + offset, 28)); cloud_palettes[str(offset)] = "res://assets/opening/effects/" + bank + "/" + filename
		banks[bank] = {"textures": descriptors, "cloud_palettes": cloud_palettes}
	def table(address, count, fmt): return list(struct.unpack_from("<" + fmt * count, source, 0x30 + address - 0x800E7000))
	manifest["texture_banks"] = banks; manifest["trig4096"] = [list(struct.unpack_from("<2h", executable, 0x800 + 0x80073E4C - 0x80010000 + phase * 4)) for phase in range(4096)]; manifest["clouds"] = {"variant0": {"height": table(0x800F1638, 9, "h"), "radius": table(0x800F164C, 9, "h"), "half_size": table(0x800F1660, 9, "h"), "clut_offset": table(0x800F167C, 9, "b"), "uv_x": table(0x800F1674, 8, "B")}, "variant2": {"height": table(0x800F16C0, 4, "h"), "radius": table(0x800F16CC, 4, "h"), "half_size": table(0x800F16D8, 4, "h"), "clut_offset": table(0x800F16EC, 4, "b"), "uv_x": table(0x800F16E4, 8, "B")}}; manifest["screen_atmosphere"] = {"variant3_rows": table(0x800F16F4, 5, "B"), "variant4_rows": table(0x800F16FC, 6, "B"), "variant5_rows": table(0x800F1700, 10, "B")}; manifest["variant6_vertices"] = [table(0x800F170C + index * 8, 3, "h") for index in range(4)]; manifest["supported_variants"] = {"class18": [0, 2, 3, 4, 5, 6], "class14": [1, 2]}; manifest["renderer_adapters"] = ["Screen atmosphere backgrounds use CanvasLayer -1; native ordering-table interleaving with scene geometry is not reproduced.", "World cloud billboards use depth-tested Godot meshes; native GTE saturation and PSX affine texture sampling are not reproduced."]
	manifest["clouds"]["variant1"] = {"height": table(0x800F1688, 4, "h"), "radius": table(0x800F1698, 4, "h"), "half_size": table(0x800F16A8, 4, "h"), "radius_jitter": table(0x800F16A8, 8, "h"), "clut_offset": table(0x800F16B8, 4, "b"), "uv_x": [0, 64, 128, 0, 64, 128, 0, 64]}; manifest["supported_variants"]["class18"].append(1); manifest["source"]["companion_constructor"] = "0x800EABF4..0x800EAC54"
	destination = output / "manifest.json"; write_output(destination, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
from models import actor_archive
from models import export_actor_model
from world import export_maps
from world import textures
from models import export_static_actor
from disc import decompress_section, write_output
from world import export_floor_shapes
from world import texture_page
DS_STAGE = "ST49"; DS_BASE = 0x800E7000; DS_CTX = 0x8007CEC0; DS_PLAYER = 0x8008C0A0; DS_AREA_BYTE = 0x8009C7F9; DS_STATE_BYTE = 0x8009C7FC; DS_FLAGS = 0x80098538; DS_OWNER = 0x8009BE08
DS_SCENE_ID = 0x18; DS_HANDLER = 0x800E72B0; DS_STATES = 0x800ECBDC; DS_CAMERA = 0x800EC850; DS_TIMELINE = 0x800ECB20; DS_PER_FRAME = 0x800E7270; DS_STAGE_INIT = 0x800E701C; DS_GTE_START = 0x800E8DE8
DS_ENTRY_FLAG = 0x5C0; DS_CLEAR_VARIANT_FLAG = 0x5C1; DS_EYES = 0x800ECBAC; DS_MOUTH = 0x800ECBD0; DS_ARCHIVE = "ST49_0B800"
DS_D = {}
def DS_H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def dropship_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST49T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != DS_BASE: raise ValueError("unexpected ST49T header")
	DS_D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), code_end=DS_BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_D.update(ovl=ovl, game=DS_D["game"]); intro_SLES = DS_D["sles"]; intro_GAME = DS_D["game"]; intro_OVL = ovl
	game = lambda a: struct.unpack_from("<I", DS_D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + DS_SCENE_ID * 4), game(0x800DBEA0 + 0x49 * 4), game(0x800DC66C + 0x49 * 4)) != (DS_HANDLER, DS_STAGE_INIT, DS_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST49 scene 0x18")
	u32 = fire_u32
	if [u32(0x800E727C), u32(0x800E728C), u32(0x800E729C)] != [0x24040000 | 0x5C1, 0x24040000 | 0x5C0, 0x24040018]: raise ValueError("ST49 per-frame trigger flags differ")
	if [u32(0x800E7344), u32(0x800E7350)] != [0x24840000 | 0xC850, 0x24A50000 | 0xCB20] or u32(0x800E7354) != 0x24040000 | 0x7A0: raise ValueError("scene 0x18 camera/timeline binding differs")

def dropship_emulate():
	import unicorn
	e = stage_emulator(DS_STAGE_INIT, DS_GTE_START, DS_D["code_end"], ())(); e.requests = []
	def flag(identifier, on=True):
		address = DS_FLAGS + (identifier >> 3); e.w8(address, e.u8(address) | (1 << (identifier & 7)) if on else e.u8(address) & ~(1 << (identifier & 7)))
	flag(DS_ENTRY_FLAG); e.w8(DS_AREA_BYTE, 2); e.w8(DS_STATE_BYTE, 1); e.cpu.mem_write(DS_OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(DS_PER_FRAME)
	started = [x for x in e.events if x["kind"] == "scene_start"]
	if [x["args"][0] for x in started] != [DS_SCENE_ID]: raise RuntimeError("ST49 per-frame handler did not start scene 0x18")
	e.events.clear()
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = DS_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=DS_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(DS_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(DS_PLAYER, e.u8(DS_PLAYER) | 2)
	tracks, tick = run_scene(e, DS_HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(DS_CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(DS_PLAYER) & 2))})
	return e, tracks, tick

DS_OPS = {"xa_play": lambda x: {"op": "play_xa", "descriptor": x["args"][0] & 0xFFFF}, "camera_shake": lambda x: {"op": "camera_shake", "magnitude_raw": x["args"][1], "decay_raw": x["args"][2]},
	"face_init": lambda x: {"op": "player_face_init", "eye_table_ram": DS_H(x["args"][1]), "mouth_table_ram": DS_H(x["args"][2])}, "face_eyes": lambda x: {"op": "player_face", "channel": "eyes", "sequence": x["args"][1]}, "face_mouth": lambda x: {"op": "player_face", "channel": "mouth", "sequence": x["args"][1]},
	"spawn_effect_8": lambda x: {"op": "effect_spawn", "class": 0x0F, "pool": "effect (SLES0x8003E8F8)", "spawner": "inline", "variant": 0x0A},
	"player_render_flag": lambda x: {"op": "player_render_flag", "set": x["value"]}}
def dropship_actor_models(root):
	manifest = json.loads((root / "assets/levels" / DS_STAGE / "models" / DS_ARCHIVE / "manifest.json").read_text(encoding="utf-8")); out = {}
	for index, model in enumerate(manifest["models"]): out.setdefault(model["flags"] & 0xFFFFFF, (DS_ARCHIVE, index, model))
	return out

def export_dropship_scene(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); dropship_load(root); out = Path(out_dir or root / "assets/levels") / DS_STAGE; out.mkdir(parents=True, exist_ok=True)
	e, tracks, ticks = dropship_emulate(); tl = fire_timeline(DS_TIMELINE); native = fire_commands(DS_CAMERA); K = fire_K
	if native[-1]["opcode"] != 0xFF: raise ValueError("camera stream is not terminated")
	models = dropship_actor_models(root); area_of = {}; current = 0
	for x in e.events:
		if x["kind"] == "request_block" and x["state"] == 1: current = bytes.fromhex(x["bytes"])[5]
		if x["kind"] == "spawn": area_of.setdefault(x["record"], current)
	order = []
	for c in native:
		if c["opcode"] == 0x40 and c["actor_record"]["source_ram"] not in order: order.append(c["actor_record"]["source_ram"])
	actors = []; slot_of = {}; omitted = []
	for address in order:
		item = flight_actor_entry(fire_record(int(address, 16)), area_of.get(address, 0), models, DS_STAGE, True)
		if item["model"] is None: omitted.append({"record": address, "class": item["entry"]["actor_class"], "pool": item["entry"]["pool_type"], "reason": "no exported model for this (class, pool); not representable by native_scene.gd"}); continue
		slot_of[address] = item["slot"] = len(actors); actors.append(item)
	copy_actor_models(root, out, actors)
	commands = []; occupant = {}; adaptations = []
	for c in native:
		item = dict(c); op = c["opcode"]
		if op in (0x40, 0x41):
			address = c["actor_record"]["source_ram"]; occupant[fire_record(int(address, 16))["slot"]] = address if op == 0x40 else None
			if address not in slot_of: adaptations.append({"source_ram": c["source_ram"], "action": "omitted", "reason": "record %s has no model" % address}); continue
		if op == 0x11:
			native_slot = (c["words"][0] >> 16) & 255; address = occupant.get(native_slot); item["target_record"] = address
			if address in slot_of: item["native_words"] = c["words"]; item["words"] = [(c["words"][0] & 0xFF00FFFF) | (slot_of[address] << 16)] + c["words"][1:]; adaptations.append({"source_ram": c["source_ram"], "action": "retargeted", "reason": "native slot %d -> runtime slot %d (%s)" % (native_slot, slot_of[address], address)})
			else: adaptations.append({"source_ram": c["source_ram"], "action": "kept", "reason": "relative-focus target slot %d holds %s (not spawned at runtime)" % (native_slot, address)})
		commands.append(item)
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local") and not (x["kind"] == "screen_transition" and x.get("phase") == 0xFF)]
	segments, init, finish = fire_programs(scene_events, tl, {**fire_OPS, **DS_OPS})
	for x in e.events:
		if x["kind"] != "move_local" or x.get("actor_slot") is not None or not x["args"][3]: continue
		motion = segments["%d:%d" % (x["phase"], x["step"])].setdefault("motion", []); velocity = [x["args"][1], x["args"][2], x["args"][3]]
		if motion and motion[-1]["velocity_raw"] == velocity and motion[-1]["through_tick"] == x["frame"] - 1: motion[-1]["through_tick"] = x["frame"]
		else: motion.append({"actor": "player", "from_tick": x["frame"], "through_tick": x["frame"], "velocity_raw": velocity, "source": "SLES0x800417AC(player, 0, 0, ctx+0x18) at %s" % x["caller"]})
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = slot_of.get(x["actor_slot"], x["actor_slot"])
	controllers = fire_controllers(e, {slot_of[k]: v for k, v in tracks.items() if k in slot_of}, {item["slot"]: item["source_ram"] for item in actors})
	for slot, profile in controllers.items():
		entry = actors[int(slot)]["entry"]; profile["source"] = "ST49T class 0x%02X (pool 0x%02X) update emulated once per native tick after the scene update; render helpers stubbed" % (entry["actor_class"], entry["pool_type"])
	stage_request = fire_request(e.requests[-1])
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"]) != (2, "ST%02X" % K(0x800E7358, 0x10), 0, [K(0x800E735C, 0x800), K(0x800E7364, -0x371), K(0x800E736C, -0x3400)], 0x800): raise ValueError("finish request differs: %s" % stage_request)
	bank = export_scene_player_clips(DS_STAGE, out)
	scene = {"stage": DS_STAGE, "area": 2, "scene_id": DS_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_18_callbacks.json", "commands": commands, "native_commands": native, "command_adaptations": adaptations, "omitted_actors": omitted, "timeline": tl, "actors": actors,
		"player": {"scene_init": {"position_raw": [0, 0, 0], "source": "scene state 0 does not write the player position"}, "track": compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": face_table(DS_EYES, 3), "player_mouth": face_table(DS_MOUTH, 3)},
		"emulation": {"script": "tools/cinematics.py export_dropship_scene", "native_ticks": ticks, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc", "actor_free_3EA4C", "actor_free_3EB7C")]},
		"source": {"overlay": "DAT/ST49T.BIN (load 0x800E7000, code size 0x%X)" % (DS_D["code_end"] - DS_BASE), "handler": "0x800E72B0 (GAME table 0x800DC490[0x18])", "state_table": DS_H(DS_STATES), "command_pointer": DS_H(DS_CAMERA), "timeline_pointer": DS_H(DS_TIMELINE), "trigger": "per-frame 0x800E7270 (GAME table 0x800DC66C[0x49])",
			"player_bank": "DAT/ST49.BIN actor archive bank -> player_scene.json (%d clips)" % len(bank["clips"])}}
	finish_ops = [op for op in finish if op["op"] != "stage_request"]
	contract = {"schema": 1, "stage": DS_STAGE, "scene_id": DS_SCENE_ID, "source": "ST49T scene 0x18 handler 0x800E72B0; timeline callbacks %s" % ", ".join(sorted({t["callback"] for t in tl})),
		"tick_basis": "tick = native ctx+0x28 of the step; program delays are the emulated substate counters (fades and XA reported idle immediately in emulation)",
		"initialization": {"player_position_raw": [0, 0, 0], "player_yaw_raw": 0, "player_yaw_unverified": True, "player_yaw_note": "scene state 0 does not write the player transform", "spawn_records": [], "init_ops": init, "source": "0x800E72EC (GAME0x800C0C5C(0x800EC850, 0x800ECB20) at 0x800E734C; destination ST10:0 stored in ctx+0xC at 0x800E7358..0x800E7378)"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST49T 0x800E7500", "fade_exit": 0x22, "fade_exit_source": "0x800E74CC (state 1 -> 2 after the timeline ends or the scene is skipped)", "ops": finish_ops,
			"skip_path": {"source": "0x800E74A8..0x800E74D4", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800E7560..0x800E7620 request block 0x80078D08", "request_bytes": stage_request["bytes"]}},
		"xa": {"descriptor_index": 0x48, "table": "SLES0x8001B9B0", "answers": []}, "new_ops": flight_NEW_OPS}
	world.write_output(out / "scene_18.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / "scene_18_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	triggers = {"stage": DS_STAGE, "triggers": [{"entry_area": 2, "scene_id": DS_SCENE_ID, "source_function": "GAME0x800C0B0C", "file": "scene_18.json", "requires_event_flags_set": [DS_ENTRY_FLAG], "requires_event_flags_clear": [DS_CLEAR_VARIANT_FLAG],
		"source": "ST49T per-frame 0x800E7270 (GAME table 0x800DC66C[0x49]) starts scene 0x18 while flag 0x5C0 or 0x5C1 is set; 0x5C0 is set by the ST01T Forbidden Island destination callback 0x800E8788 (0x800E87B0..0x800E87C4) that redirects the request to ST49 area 2; with 0x5C1 clear the scene ends at ST10:0"}]}
	world.write_output(out / "scene_triggers.json", json.dumps(triggers, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "actors": len(actors), "omitted_actors": [o["record"] for o in omitted], "adaptations": len(adaptations), "transition": stage_request, "player_clips": len(bank["clips"]), "segments": len(segments)}


# ---- scenes ----
def scenes_export_church(source_dir, output_dir):
	from world import Stage
	source_dir = Path(source_dir); output_dir = Path(output_dir); overlay = (source_dir / "ST0BT.BIN").read_bytes(); doors = json.loads((output_dir / "scene_27_doors.json").read_text(encoding="utf-8")); stage = Stage((source_dir / "ST0B.BIN").read_bytes()); branches = {}
	for group in doors["groups"]:
		area = int(group["area"]); start = 0x800EF364 if area == 0 else 0x800EF3B0; commands = []; address = start
		while address < start + 0x4C:
			offset = 48 + address - 0x800E7000; header = struct.unpack_from("<I", overlay, offset)[0]; opcode = header >> 24; size = 16 if 0x10 <= opcode <= 0x1A else 4; commands.append({"source_ram": hex(address), "opcode": opcode, "words": list(struct.unpack_from("<" + "I" * (size // 4), overlay, offset))}); address += size
		timeline = []; address = 0x800EF3FC
		while True:
			phase, step, duration, callback = struct.unpack_from("<BBhI", overlay, 48 + address - 0x800E7000)
			if phase == 255: break
			timeline.append({"phase": phase, "step": step, "duration": duration, "callback": hex(callback), "source_ram": hex(address)}); address += 8
		cells = [(63, 66), (64, 66)] if area == 0 else [(63, 62)]; tiles = stage.area(area)[0]; placements = [(struct.unpack_from("<H", tiles[cell])[0] & 0x7FF) for cell in cells]; target = 1 if area == 0 else 0; initial = [0, -896, 944] if area == 0 else [0, 0, -336]; arrival = [0, 0, -464, 2048] if area == 0 else [0, -896, 896, 0]
		contract = {"schema": 1, "stage": "ST0B", "scene_id": 39, "initialization": {"player_position_raw": initial, "player_yaw_raw": 2048 if area == 0 else 0, "spawn_records": [item["source_ram"] for item in group["actors"]], "suppress_placements": placements, "source": "ST0B0x800E7B28..7D70"}, "segments": {"0:0": {"program": [{"op": "player_control", "control": 0}]}, "0:1": {"program": []}, "0:2": {"program": []}, "0:3": {"program": [{"op": "player_control", "control": 2, "start_record": 8}], "motion": [{"actor": "player", "from_tick": 0, "velocity_raw": [0, 0, -8]}, {"actor": "player", "from_tick": 20, "velocity_raw": [0, 0, -30]}]}}, "actor_controllers": {"0": {"total_yaw_increment": {"from_tick": 10, "through_tick": 120, "shift": 3, "maximum": 8, "sign": 1}}, "1": {"total_yaw_increment": {"from_tick": 10, "through_tick": 120, "shift": 3, "maximum": 8, "sign": -1}}}, "finish": {"source": "ST0B0x800E7E98..8004", "restore_calls": ["GAME0x800C11F0", "GAME0x800C0F58"], "transition": {"destination_stage": "ST0B", "destination_area": target, "destination_transform_raw": arrival, "native_transition_mode": 3, "native_entry_fade": 0xFF}}, "xa": {"descriptor_index": 99, "prepare": "SLES0x8001B714", "play": "SLES0x8001B864", "ready": "SLES0x8001AF94", "descriptor_ram": "0x800EEF28", "archive": "XA/PAL_37.XA", "sector_start": 124224, "sector_end": 125295, "channel": 7, "binding_status": "original_xa_pcm"}}
		file = f"scene_27_area{area}_callbacks.json"; write_output(output_dir / file, json.dumps(contract, indent=2) + "\n", encoding="utf-8"); branches[str(area)] = {"stage": "ST0B", "area": area, "scene_id": 39, "native_tick_hz": 25, "callback_contract_file": file, "commands": commands, "timeline": timeline, "actors": group["actors"], "source": {"handler": "0x800E7AEC", "initialize": "0x800E7B28", "update": "0x800E7E20", "finish": "0x800E7E98", "area_selector": "native save+0x11", "command_pointer": hex(start)}}
	profile = {"stage": "ST0B", "scene_id": 39, "branches": branches}; write_output(output_dir / "scene_27.json", json.dumps(profile, indent=2) + "\n", encoding="utf-8"); write_output(output_dir / "scene_triggers.json", json.dumps({"stage": "ST0B", "triggers": [{"event_flag": 0x80, "scene_id": 0x27, "source_function": "GAME0x800C0B0C", "source": "ST0B0x800E7640 tests80; E7650 clears80; E7658 requests27"}]}, indent=2) + "\n", encoding="utf-8"); return profile
def export_scene_audio(cue, source_dir, output_dir):
	import audio
	source_dir = Path(source_dir); output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True); overlay = (source_dir / "ST0BT.BIN").read_bytes(); descriptor = overlay[48 + 0x800EEF28 - 0x800E7000:48 + 0x800EEF28 - 0x800E7000 + 8]; entry = {"id": 99, "archive": "XA/PAL_37.XA", "sector_start": descriptor[1] * 65536 + struct.unpack_from("<H", descriptor, 2)[0], "sector_end": descriptor[5] * 65536 + struct.unpack_from("<H", descriptor, 6)[0], "channel": descriptor[4] & 31, "descriptor_ram": "0x800EEF28", "descriptor_bytes": descriptor.hex()}; path, start, frames = audio.cue_layout(Path(cue)); reader = audio.Mode2Track(path, start, frames)
	try:
		extent, _ = audio.archive_record(reader, entry["archive"]); result = audio.export_entry(reader, extent, entry, output_dir); result["file"] = "res://" + (output_dir / "xa_099.wav").resolve().relative_to(Path(__file__).resolve().parents[1]).as_posix(); write_output(output_dir / "manifest.json", json.dumps(result, indent=2) + "\n", encoding="utf-8"); return result
	finally: reader.stream.close()
def scenes_export_callbacks(stage, scene_id, output_dir):
	if (stage, scene_id) != ("ST0A", 0x4D): raise ValueError(f"Native scene callback binding is unbound: {stage}:{scene_id:02X}")
	def message(index, state): return {"op": "message", "index": index, "state": state, "source": "SLES0x80048474/0x800489A0"}
	def head(target, speed): return {"op": "head_target", "target": target, "speed": speed, "source": "ST0A0x800E7BD8..7C7C"}
	def turn(heading, speed): return {"op": "turn_wait", "actor": "player", "heading": heading, "speed": speed, "source": "SLES0x80042128"}
	segments = {"0:0": {"source": "0x800E7DCC", "program": [{"op": "player_control", "control": 0}, message(0xC8, 1), {"op": "advance"}]}, "0:1": {"source": "0x800E7E64", "program": [message(0xC9, 1), message(0xCA, 2), message(0xCB, 3), {"op": "event_set", "id": 0x680}, {"op": "delay", "ticks": 16, "state": 4}, {"op": "advance"}]}, "0:2": {"source": "0x800E7F84", "program": [head(0, 32), message(0xCC, 1), {"op": "minimum_tick", "tick": 140}, {"op": "advance"}], "sounds": [{"tick": 80, "id": 0xB8, "position_raw": [-432, 0, 256]}, {"tick": 130, "id": 0xB9, "position_raw": [-432, 0, 256]}]}, "0:3": {"source": "0x800E80D8", "program": [head(0x970, 128), {"op": "message_start", "index": 0xCD, "state": 1}, {"op": "delay", "ticks": 3}, turn(0x770, 64), {"op": "message_wait"}, {"op": "despawn", "record": "0x800ef83c"}, message(0xCE, 2), message(0xCF, 3), message(0xD0, 4), head(0x300, 160), message(0xD1, 5), {"op": "advance"}]}, "0:4": {"source": "0x800E831C", "program": [head(0x380, 160), {"op": "minimum_tick", "tick": 110}, {"op": "advance"}], "motion": [{"actor": "player", "from_tick": 0, "through_tick": 5, "point_raw": [32, -16, -176], "turn_speed": 64}, {"actor": "player", "from_tick": 6, "through_tick": 42, "point_raw": [32, -16, -176], "turn_speed": 64, "speed_raw": -80}, {"actor": "player", "from_tick": 43, "through_tick": 45, "heading": 0x400, "turn_speed": 16, "point_raw": [32, -16, -176], "speed_raw": -80}], "actions": [{"tick": 5, "op": "player_control", "control": 2}, {"tick": 45, "op": "player_control", "control": 0}]}, "0:5": {"source": "0x800E84E4", "program": [message(0xD2, 1), {"op": "minimum_tick", "tick": 80}, {"op": "advance"}]}, "0:6": {"source": "0x800E8580", "program": [message(0xD3, 1), message(0xD4, 2), message(0xD5, 3), head(0xF00, 128), {"op": "message_start", "index": 0xD6, "state": 4}, {"op": "delay", "ticks": 3}, turn(0x100, 128), {"op": "message_wait"}, {"op": "advance"}]}, "0:7": {"source": "0x800E8740", "program": [head(0xC00, 32), {"op": "message_start", "index": 0xD7, "state": 1}, {"op": "delay", "ticks": 3}, turn(0x100, 128), {"op": "message_wait"}, {"op": "minimum_tick", "tick": 80}, {"op": "despawn", "record": "0x800ef828"}, {"op": "finish"}], "sounds": [{"tick": 35, "id": 0xB8, "position_raw": [-432, 0, 256]}, {"tick": 65, "id": 0xB9, "position_raw": [-432, 0, 256]}]}}
	actors = {"0": {"source": "ST0A0x800EA770", "startup_control": 0, "events": [{"step": 2, "tick": 30, "op": "actor_head", "target": 0xDA0, "speed": 64}, {"step": 6, "state": 4, "op": "actor_head", "target": 0x500, "speed": 64}, {"step": 4, "tick": 45, "op": "control", "control": 1}, {"step": 4, "tick": 110, "op": "control", "control": 0}, {"step": 7, "tick": 8, "op": "control", "control": 2, "start_record": 6}], "motion": [{"step": 2, "from_tick": 41, "heading": 0x100, "turn_speed": 64}, {"step": 4, "from_tick": 41, "through_tick": 100, "point_raw": [80, -16, -256], "turn_speed": 64}, {"step": 4, "from_tick": 46, "through_tick": 110, "point_raw": [80, -16, -256], "speed_raw": -64}, {"step": 4, "from_tick": 101, "through_tick": 110, "heading": 0x400, "turn_speed": 32}, {"step": 7, "from_tick": 3, "through_tick": 8, "point_raw": [576, -16, -256], "turn_speed": 256}, {"step": 7, "from_tick": 9, "through_tick": 50, "point_raw": [576, -16, -256], "turn_speed": 128, "speed_raw": -384}]}, "1": {"source": "ST0A0x800EABEC", "startup_control": 6, "event_flag_start": {"step": 1, "id": 0x680, "control": 7}, "motion": [{"step": 1, "requires_flag": 0x680, "heading": 0xC00, "turn_speed": 128, "speed_raw": -64}, {"step": 2, "heading": 0xC00, "turn_speed": 128, "speed_raw": -64}]}, "3": {"source": "ST0A0x800EAE04", "startup_control": 0, "events": [{"step": 1, "tick": 2, "op": "position", "position_raw": [-200, 0, -208]}]}}
	actors["2"] = {"source": "ST0A0x800EAF4C/EAFCC..EB020", "motion": [{"step": 5, "from_tick": 32, "through_tick": 45, "velocity_raw": [128, 0, 0]}]}
	result = {"schema": 1, "stage": stage, "scene_id": scene_id, "source": "Original ST0AT director0x800E7A58..7DCC and callbacks0x800E7DCC..8918; actor controllers0x800EA770/0x800EABEC/0x800EAE04", "initialization": {"player_position_raw": [240, -16, -144], "player_yaw_raw": 1024, "player_state_gate": 1, "source_enter": "GAME0x800CDD50/0x800CDDF8"}, "segments": segments, "actor_controllers": actors, "finish": {"source": "ST0A0x800E7C9C", "fade_exit": 0x12, "close_window": 1, "clear_actor_mask": 0x496, "clear_actor_flags": 128, "registration_record": "0x800ef878", "fade_entry": 1, "player_yaw_raw": 0xC00, "restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "GAME0x800C0F58"]}}
	result["initialization"]["music_cue"] = 0x16
	path = Path(output_dir) / f"scene_{scene_id:02x}_callbacks.json"; path.parent.mkdir(parents=True, exist_ok=True); write_output(path, json.dumps(result, indent=2) + "\n", encoding="utf-8"); return result

# ---- scene_player ----
# Export stage-scoped player animation controls (0x80..) as a Godot-compatible GLB animation library.
#
# Native path (PAL SLES_035.56 / GAME.BIN):
#   * GAME 0x800CDE5C(control, start, 1) stores player(0x8008C0A0)+0xB4/+0xB5; GAME 0x800CC7E8 forwards it to
#     0x800CCEBC, which latches +0xA0 (control) / +0x9C (start record).
#   * SLES 0x8003F2A8 (base layer) and 0x8003F3C4 (upper layer) resolve the control record:
#         control < 0x60  -> table 0x80123000, base 0x80110800 (PL00P000)
#         control < 0x70  -> table 0x801246B0 (PL00R02)
#         control < 0x80  -> table 0x80124600
#         control >= 0x80 -> bank = *(player+0x298); table = bank + *(bank+4); index = control-0x80; base = bank
#     record = base + (entry & ~3) + 4, header byte record[-4] = track index (-> player+0xA2).
#   * SLES 0x8003F96C/0x8003FAD8 resolve the track: control & 0x80 -> base = *(player+0x298), track table = base+8;
#     pose words = base + track_entry + frame*64.
#   * player+0x298 is set by SLES 0x80023040 (called from GAME stage init 0x800BA400): it walks the block chain at
#     0x80124800 (or 0x8013C800 when scratch byte 0x1F80000C != 0), i.e. the stage actor archive. A block whose first
#     word has bit31 set becomes player+0x298; bit30 sets player+0x29C = block+4. Next block = block + (word & 0x3FFFFFFF).
#     SLES 0x80018B08..0x80018B4C picks the same 0x80124800/0x8013C800 destination for the streamed address-0 section,
#     which for ST39 is DAT/ST39.BIN section 0x3000 (type 0x0C, LZ-compressed; tools/assets.py names it ST39_03000).
DAT = ROOT / "build" / "disc-assets" / "DAT"
COMMON = ROOT / "build" / "disc-assets" / "COMMON"
clip_OUT = ROOT / "assets" / "levels"
SCENE_CONTROL_BASE = 0x80


def clip_u32(data, offset): return struct.unpack_from("<I", data, offset)[0]


def find_actor_archive(stage, types=(0x0C,)):
	"""Return (decoded payload, section offset) of the stage's address-0 type-0x0C section that starts with the bank chain."""
	source = (DAT / f"{stage}.BIN").read_bytes()
	for offset in range(0, len(source) - 0x30, 0x800):
		if clip_u32(source, offset) not in types or any(source[offset + 0x18:offset + 0x30]) or clip_u32(source, offset + 0x0C) != 0: continue
		try: payload, meta = disc.extract_section(source, offset)
		except ValueError: continue
		if clip_u32(payload, 0) & 0xC0000000: return payload, offset, meta
	raise ValueError(f"{stage}.BIN has no actor archive with a native animation-bank prefix")


def walk_chain(payload):
	"""Mirror of SLES 0x80023040."""
	blocks, position = [], 0
	while position + 4 <= len(payload):
		word = clip_u32(payload, position)
		if not word & 0xC0000000: break
		size = word & 0x3FFFFFFF
		blocks.append({"offset": position, "word": word, "size": size, "role": "player+0x298 (scene player bank)" if word & 0x80000000 else "player+0x29C (block+4)"})
		position += size
	return blocks, position


def parse_bank(payload, bank):
	size = clip_u32(payload, bank) & 0x3FFFFFFF; control_table = clip_u32(payload, bank + 4); first_track = clip_u32(payload, bank + 8)
	if not 8 < first_track <= control_table < size or first_track & 3 or (control_table - 8) & 3: raise ValueError("Invalid scene player bank header")
	track_offsets = [clip_u32(payload, bank + offset) for offset in range(8, first_track, 4)]
	first_control = clip_u32(payload, bank + control_table)
	control_offsets = [clip_u32(payload, bank + offset) for offset in range(control_table, first_control & ~3, 4)]
	ordered = sorted(set(track_offsets)) + [control_table]
	tracks = {}
	for slot, offset in enumerate(track_offsets):
		end = next(other for other in ordered if other > offset)
		if (end - offset) & 63: raise ValueError(f"Scene track {slot} is not aligned to 64-byte source frames")
		tracks[slot] = (bank + offset, (end - offset) // 64, offset)
	return size, control_table, track_offsets, control_offsets, tracks


def decode_clip(payload, binary, bone_node_ids, bones, slot, record_pos, track, pose_limit):
	"""Same conventions as tools/models.py decode_animations for a base (non-upper, mode 0) clip.
	The native resolver never bounds-checks a pose index; several transition controls address one pose past their
	track, which reads the next track's first frame. pose_limit (file offset of the control table) bounds that."""
	track_file, _, _ = track
	source_frame_count = (pose_limit - track_file) // 64
	frame_count = payload[record_pos - 3]
	records = [struct.unpack_from("<4B", payload, record_pos + frame * 4) for frame in range(frame_count)]
	frame_indices = [record[0] for record in records]
	if any(index & 0x80 or index >= source_frame_count for index in frame_indices): raise ValueError(f"Scene control {slot} references an invalid pose")
	times, samples, ticks = [], [], 0
	for frame, (pose, duration, event, flags) in enumerate(records):
		if duration == 0: raise ValueError(f"Scene control {slot} has a zero-duration record")
		target = next((other[0] for other in records[frame + 1:] if other[0] != pose), None) if flags & 0x90 == 0x10 else None
		times.append(ticks / 30.0); samples.append((pose, target, flags & 15 if target is not None else 0))
		if duration > 1: times.append((ticks + duration - 1) / 30.0); samples.append(samples[-1])
		ticks += duration
	final_flags = records[-1][3]; loop_frame = final_flags & 127 if final_flags & 128 and final_flags != 255 else None
	if loop_frame is not None and loop_frame >= frame_count: raise ValueError(f"Scene control {slot} loops outside its records")
	times.append(ticks / 30.0); samples.append(samples[loop_frame] if loop_frame is not None else samples[-1])
	input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True)
	root_positions = []
	for frame_index, target_index, fraction in samples:
		target_word = clip_u32(payload, track_file + target_index * 64) if target_index is not None else None
		offset = models.point(clip_u32(payload, track_file + frame_index * 64), target_word, fraction)
		root_positions.extend(bones[0][axis] + offset[axis] for axis in range(3))
	samplers = [{"input": input_accessor, "output": binary.accessor(root_positions, "f", 5126, "VEC3", None), "interpolation": "LINEAR"}]
	channels = [{"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}}]
	for bone_index, node_index in enumerate(bone_node_ids):
		rotations = []
		for frame_index, target_index, fraction in samples:
			packed = clip_u32(payload, track_file + frame_index * 64 + (bone_index + 1) * 4)
			target_word = clip_u32(payload, track_file + target_index * 64 + (bone_index + 1) * 4) if target_index is not None else None
			rotations.extend(models.decode_rotation(packed, target_word, fraction, "XYZ"))
		samplers.append({"input": input_accessor, "output": binary.accessor(rotations, "f", 5126, "VEC4", None), "interpolation": "LINEAR"})
		channels.append({"sampler": len(samplers) - 1, "target": {"node": node_index, "path": "rotation"}})
	native_frames = track[1]
	metadata = {"frameCount": frame_count, "durationTicks": ticks, "durationSeconds": round(ticks / 30.0, 6), "periodTicks": ticks, "periodSeconds": round(ticks / 30.0, 6), "loopFrame": loop_frame, "loops": loop_frame is not None, "finalFlags": final_flags, "holdsLastFrame": final_flags == 255, "events": [{"frame": frame, "id": event} for frame, (_, _, event, _) in enumerate(records) if event], "records": [{"pose": pose, "durationTicks": duration, "event": event, "flags": flags} for pose, duration, event, flags in records]}
	overflow = sorted({index for index in frame_indices if index >= native_frames})
	if overflow: metadata["posesBeyondTrack"] = {"trackFrames": native_frames, "poses": overflow, "note": "native reads continue into the following track's frames (contiguous 64-byte poses)"}
	return samplers, channels, frame_indices, metadata


def skeleton_nodes():
	"""Same node layout as tools/models.py export_variant (node0 MegaMan, node1 MegaManMesh, nodes2..16 Bone_00..14)."""
	source = (COMMON / "PL00P000.BIN").read_bytes(); payload = source[0x30:]
	bones = [models.bone_point(*struct.unpack_from("<hhh", payload, i * 6)) for i in range(15)]
	world = []
	for i, parent in enumerate(models.PARENTS): world.append(bones[i] if parent < 0 else tuple(bones[i][j] + world[parent][j] for j in range(3)))
	bone_node_ids = list(range(2, 17)); children = [[] for _ in bones]
	for i, parent in enumerate(models.PARENTS):
		if parent >= 0: children[parent].append(bone_node_ids[i])
	nodes = [{"name": "MegaMan", "children": [1, bone_node_ids[0]]}, {"name": "MegaManMesh", "mesh": 0, "skin": 0}]
	for i, position in enumerate(bones):
		node = {"name": f"Bone_{i:02d}", "translation": list(position), "extras": {"sourceBone": i}}
		if children[i]: node["children"] = children[i]
		nodes.append(node)
	# Keep the exported player's rest rotations (clip_000 first pose) when the port's GLB is present.
	reference = ROOT / "assets" / "player" / "megaman.glb"
	if reference.exists():
		data = reference.read_bytes(); document = json.loads(data[20:20 + clip_u32(data, 12)])
		for index in bone_node_ids:
			for key in ("translation", "rotation"):
				if key in document["nodes"][index]: nodes[index][key] = document["nodes"][index][key]
	return nodes, bones, world, bone_node_ids


def export_scene_player_clips(stage, output_dir=None, types=(0x0C,)):
	stage = stage.upper(); output_dir = Path(output_dir) if output_dir else clip_OUT / stage; output_dir.mkdir(parents=True, exist_ok=True)
	payload, section_offset, section_meta = find_actor_archive(stage, types)
	blocks, archive_offset = walk_chain(payload)
	player_blocks = [block for block in blocks if block["word"] & 0x80000000]
	if not player_blocks: raise ValueError(f"{stage} actor archive has no player bank (bit31 block)")
	bank = player_blocks[-1]["offset"]  # SLES 0x80023040 keeps the last bit31 block
	bank_size, control_table, track_offsets, control_offsets, tracks = parse_bank(payload, bank)
	nodes, bones, world, bone_node_ids = skeleton_nodes()
	binary = models.BinaryGLB(); animations, clips, excluded = [], [], []
	for index, entry in enumerate(control_offsets):
		slot = SCENE_CONTROL_BASE + index; record_pos = bank + (entry & ~3) + 4; track_index = payload[record_pos - 4]
		if track_index not in tracks: excluded.append({"slot": slot, "reason": "missing track", "track": track_index}); continue
		try: samplers, channels, frame_indices, metadata = decode_clip(payload, binary, bone_node_ids, bones, slot, record_pos, tracks[track_index], bank + control_table)
		except ValueError as error: excluded.append({"slot": slot, "reason": str(error)}); continue
		name = f"clip_{slot:03d}"; source = {"sourceBank": f"DAT/{stage}.BIN section {section_offset:#x} block {bank:#x}", "context": "scene player bank (player+0x298), base layer mode0"}
		animations.append({"name": name, "samplers": samplers, "channels": channels, "extras": {"sourceControlSlot": slot, "sourceControlOffset": hex(entry), "sourceTrackSlot": track_index, "sourceTrackOffset": hex(tracks[track_index][2]), "frameIndices": frame_indices, "fps": 30, **metadata, **source}})
		clips.append({"name": name, "slot": slot, "track": track_index, **metadata, **source})
	# Minimal degenerate skinned triangle so Godot builds the same MegaMan/Skeleton3D hierarchy as megaman*.glb.
	position = list(world[0]) * 3
	attributes = {"POSITION": binary.accessor(position, "f", 5126, "VEC3", 34962, True), "JOINTS_0": binary.accessor([0, 0, 0, 0] * 3, "H", 5123, "VEC4", 34962), "WEIGHTS_0": binary.accessor([1.0, 0.0, 0.0, 0.0] * 3, "f", 5126, "VEC4", 34962)}
	matrices = []
	for p in world: matrices.extend((1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -p[0], -p[1], -p[2], 1.0))
	inverse_bind = binary.accessor(matrices, "f", 5126, "MAT4", None)
	document = {"asset": {"version": "2.0", "generator": "tools/cinematics.py", "extras": {"stage": stage, "source": f"DAT/{stage}.BIN", "section": hex(section_offset), "bank": hex(bank)}}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
		"meshes": [{"name": "SceneBankPlaceholder", "primitives": [{"attributes": attributes, "mode": 4}]}], "skins": [{"name": "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse_bind}],
		"animations": animations, "bufferViews": binary.views, "accessors": binary.accessors, "buffers": [{"byteLength": len(binary.data)}]}
	json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8"); json_chunk += b" " * ((-len(json_chunk)) & 3)
	binary.data.extend(b"\0" * ((-len(binary.data)) & 3))
	glb = struct.pack("<4sII", b"glTF", 2, 28 + len(json_chunk) + len(binary.data)) + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk + struct.pack("<I4s", len(binary.data), b"BIN\0") + binary.data
	model_name = f"player_scene_{stage}.glb"; write_output(output_dir / model_name, glb)
	manifest = {"stage": stage, "model": model_name, "library": f"scene_{stage}", "controlRange": [SCENE_CONTROL_BASE, SCENE_CONTROL_BASE + len(control_offsets) - 1],
		"animationBank": {"source": f"DAT/{stage}.BIN", "section": hex(section_offset), "sectionType": section_meta["type"], "decodedSize": section_meta["full_size"], "blockOffset": hex(bank), "blockSize": hex(bank_size), "runtimeAddress": hex(0x80124800 + bank), "alternateRuntimeAddress": hex(0x8013C800 + bank), "trackTable": "block+0x8", "controlTable": hex(control_table), "trackSlots": len(track_offsets), "controlSlots": len(control_offsets), "chain": [{**b, "offset": hex(b["offset"]), "word": hex(b["word"]), "size": hex(b["size"])} for b in blocks], "modelArchiveOffset": hex(archive_offset),
			"fps": 30, "frameStrideBytes": 64, "rotationOrder": "XYZ for all bones (base layer, upper-body mode 0)", "resolver": "SLES 0x8003F2A8/0x8003F3C4 controls>=0x80 -> *(player+0x298)+*(bank+4); SLES 0x8003F96C/0x8003FAD8 tracks -> bank+8; SLES 0x80023040 sets player+0x298", "excludedControls": excluded},
		"skeleton": {"jointCount": 15, "nodes": "MegaMan/MegaManMesh/Bone_00..Bone_14 identical to assets/player/megaman*.glb", "restSource": "PL00P000.BIN bone table; rest rotations copied from megaman.glb"},
		"clips": clips}
	write_output(output_dir / "player_scene.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest

# ---- intro_scene ----
# Emulate ST39 scene 5 (scene handler, timeline callbacks, GAME timeline/camera interpreter and actor class
# controllers) with unicorn, stubbing hardware/audio/render calls and recording every observable event.
# Build assets/levels/ST39/scene_05.json and scene_05_callbacks.json for ST39 scene 5 (Game Start intro).
# Static data is decoded from DAT/ST39T.BIN; callback programs are hand-translated from the ST39T disassembly
# (0x800EB790..0x800ECC10) and cross-checked against a unicorn emulation (Emu above) of the original code;
# actor controller events/tracks are taken from that emulation of the unchanged ST39T class controllers.
intro_ROOT = str(Path(__file__).resolve().parent.parent)

def intro_s16(v): return (v & 32767) - (v & 32768)
def s32(v): return (v & 0x7FFFFFFF) - (v & 0x80000000)

intro_SLES = intro_GAME = intro_OVL = b""
intro_CTX = 0x8007CEC0
intro_PLAYER = 0x8008C0A0

class intro_Emu:
	def __init__(self, answers):
		self.cpu = cpu = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN)
		cpu.mem_map(0, 0x200000); cpu.mem_map(0x1F800000, 0x2000)
		cpu.mem_write(0x10000, intro_SLES[0x800:]); cpu.mem_write(0xAD000, intro_GAME[0x30:]); cpu.mem_write(0xE7000, intro_OVL[0x30:0x30 + 0x30000])
		self.gpr = [getattr(M, "UC_MIPS_REG_%d" % i) for i in range(32)]
		self.control = [0] * 32; self.data = [0] * 32
		self.events = []; self.tick_info = {}
		self.answers = list(answers); self.answer_log = []
		self.actors = {}  # ptr -> slot
		self.free = [0x80180000 + i * 0x400 for i in range(16)]
		self.unknown = {}
		# GTE hooks at exact addresses
		for base, blob, start, end in ((0x80010000, intro_SLES[0x800:], 0x80010000, 0x80070000), (0x800AD000, intro_GAME[0x30:], 0x800AD000, 0x800E0000), (0x800E7000, intro_OVL[0x30:], 0x800E7000, 0x800F22B8)):
			for off in range(0, min(len(blob), end - base) - 3, 4):
				w = struct.unpack_from("<I", blob, off)[0]; op = w >> 26
				if op == 18 and (w >> 25) & 1 == 0 and ((w >> 21) & 31) in (0, 2, 4, 6) or op == 18 and (w >> 25) & 1 or op in (50, 58):
					a = base + off; cpu.hook_add(unicorn.UC_HOOK_CODE, self.gte, begin=a, end=a)
		self.stubs = {}
		def stub(addr, name, ret=0, record=True, run=False):
			self.stubs[addr] = (name, ret, record, run); cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=addr, end=addr)
		# scene side
		for a, n in ((0x80047180, "vibration"), (0x8003D658, "pool_clear"), (0x80048944, "close_windows"), (0x80020160, "sound"),
					 (0x8001BA44, "xa_fade_out"), (0x8001B714, "xa_prepare"), (0x8001B864, "xa_play"), (0x8001392C, "screen_transition"),
					 (0x800CDE4C, "restore_CDE4C"), (0x800C11F0, "restore_C11F0"), (0x800C0F58, "restore_C0F58"), (0x8001B7E8, "xa_select_1B7E8"),
					 (0x80026D10, "depth_cue_mode"), (0x800C0928, "despawn"), (0x8003EA4C, "actor_free_3EA4C"), (0x8003EB7C, "actor_free_3EB7C"),
					 (0x8003E8F8, "spawn_effect_8"), (0x800204DC, "sound_3d_204DC"), (0x800CDD50, "player_ready_CDD50")):
			stub(a, n)
		stub(0x800CDE5C, "player_control")
		stub(0x8001AF94, "xa_ready", 1); stub(0x8001AFD0, "xa_idle", 1)
		stub(0x80048474, "message"); stub(0x800489A0, "message_busy", 0, False)
		stub(0x80016B1C, "camera_shake", 0, True, True)
		stub(0x800C0584, "flag_clear", 0, True, True); stub(0x800C0558, "flag_set", 0, True, True)
		for a, n in ((0x80041318, "face_init"), (0x80041338, "face_eyes"), (0x80041348, "face_mouth"), (0x800417AC, "move_local")):
			stub(a, n, 0, True, True)
		# actor side render/resource
		stub(0x8003DFA4, "resource_ready", 1, False); stub(0x8003F4BC, "actor_control")
		for a in (0x80015A5C, 0x8003F840, 0x80040B04, 0x8003F768, 0x8003B268, 0x800B13B4, 0x8004152C, 0x8003E440, 0x800B13FC, 0x8003B3E4, 0x8003C304, 0x8003EDEC):
			stub(a, "render_%08X" % a, 0, False)
		stub(0x8003E5B0, "alloc_actor", 0, False)
		cpu.hook_add(unicorn.UC_HOOK_MEM_UNMAPPED, self.unmapped)
		self.cur = None
	def unmapped(self, uc, access, address, size, value, data):
		raise RuntimeError("unmapped access %08x at pc %08x" % (address, uc.reg_read(M.UC_MIPS_REG_PC)))
	def r(self, i): return self.cpu.reg_read(self.gpr[i])
	def u8(self, a): return self.cpu.mem_read(a & 0x1FFFFFFF, 1)[0]
	def u16(self, a): return struct.unpack("<H", self.cpu.mem_read(a & 0x1FFFFFFF, 2))[0]
	def u32(self, a): return struct.unpack("<I", self.cpu.mem_read(a & 0x1FFFFFFF, 4))[0]
	def w8(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, bytes((v & 255,)))
	def w32(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, struct.pack("<I", v & 0xFFFFFFFF))
	def where(self):
		return {"step": self.u8(intro_CTX + 3), "frame": s32(self.u32(intro_CTX + 0x28)), "sub6": self.u8(intro_CTX + 6), "sub7": self.u8(intro_CTX + 7)}
	def record(self, kind, **kw):
		e = {"kind": kind, **self.where(), **kw}
		if self.cur is not None: e["actor_slot"] = self.cur
		self.events.append(e)
	def stub_hook(self, uc, address, size, data):
		name, ret, record, run = self.stubs[address]
		a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
		if name == "alloc_actor":
			p = self.free.pop(0); uc.mem_write(p & 0x1FFFFFFF, bytes(0x400)); self.pending_alloc = p; ret = p
		elif name == "despawn":
			slot = self.actors.pop(a[0], None); self.record("despawn", slot=slot, ptr=hex(a[0])); self.free.append(a[0]) if a[0] else None
		elif name == "message":
			ans = self.answers.pop(0) if self.answers else 3
			self.answer_log.append(ans); flag = 0x680 + ans
			self.cpu.mem_write((0x800A0000 - 0x7AC8 + (flag >> 3)) & 0x1FFFFFFF, bytes((self.u8(0x800A0000 - 0x7AC8 + (flag >> 3)) | (1 << (flag & 7)),)))
			self.record("message", args=[hex(x) for x in a[:3]], simulated_answer=ans, flag_set=hex(flag)); return self._ret(uc, 0, ra)
		if record and name != "despawn":
			caller = ra - 8
			self.record(name, args=[s32(x) for x in a], caller=hex(caller))
		if run: return
		self._ret(uc, ret, ra)
	def _ret(self, uc, ret, ra):
		uc.reg_write(M.UC_MIPS_REG_V0, ret & 0xFFFFFFFF); uc.reg_write(M.UC_MIPS_REG_PC, ra)
	# ---- GTE (copied semantics from tools/cinematics.py NativeCamera) ----
	def write_data(self, index, value): self.data[index] = intro_s16(value) if index in (1, 3, 5, 8, 9, 10, 11) else value & 0xFFFFFFFF
	def gte(self, cpu, address, size, context):
		word = struct.unpack("<I", cpu.mem_read(address & 0x1FFFFFFF, 4))[0]; opcode = word >> 26; source, target, index = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
		if opcode == 18:
			if source in (0, 2): cpu.reg_write(self.gpr[target], (self.control if source == 2 else self.data)[index] & 0xFFFFFFFF)
			elif source == 4: self.write_data(index, cpu.reg_read(self.gpr[target]))
			elif source == 6: self.control[index] = cpu.reg_read(self.gpr[target]) & 0xFFFFFFFF
			else: self.operation(word)
		elif opcode in (50, 58):
			pointer = (cpu.reg_read(self.gpr[source]) + intro_s16(word)) & 0x1FFFFFFF
			if opcode == 50: self.write_data(target, struct.unpack("<I", cpu.mem_read(pointer, 4))[0])
			else: cpu.mem_write(pointer, struct.pack("<I", self.data[target] & 0xFFFFFFFF))
		else: return
		cpu.reg_write(M.UC_MIPS_REG_PC, address + 4)
	def operation(self, word):
		function = word & 63; shift = 12 if word & (1 << 19) else 0; lower = 0 if word & 1024 else -32768; result = []; flag = 0
		if function in (61, 62): result = [s32((self.data[8] * self.data[9 + row] + ((s32(self.data[25 + row]) << shift) if function == 62 else 0)) >> shift) for row in range(3)]
		elif function == 18:
			mk, vk, tk = (word >> 17) & 3, (word >> 15) & 3, (word >> 13) & 3
			base = mk * 8; packed = b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in self.control[base:base + 5]); matrix = struct.unpack_from("<9h", packed)
			vector = self.data[9:12] if vk == 3 else [intro_s16(self.data[vk * 2]), intro_s16(self.data[vk * 2] >> 16), intro_s16(self.data[vk * 2 + 1])]
			translation = [0] * 3 if tk == 3 else [s32(self.control[5 + tk * 8 + row]) for row in range(3)]
			for row in range(3):
				value = translation[row] << 12
				for column in range(3): value += matrix[row * 3 + column] * vector[column]
				result.append(s32(value >> shift))
		else: raise ValueError("GTE op %02x at" % function)
		for row, value in enumerate(result):
			self.data[25 + row] = value & 0xFFFFFFFF; self.data[9 + row] = max(lower, min(32767, value))
		self.control[31] = flag
	def call(self, function, args=()):
		cpu = self.cpu
		cpu.reg_write(M.UC_MIPS_REG_SP, 0x801FF000); cpu.reg_write(M.UC_MIPS_REG_GP, 0x8007890C); cpu.reg_write(M.UC_MIPS_REG_RA, 0x80000800)
		for i, v in enumerate(args[:4]): cpu.reg_write(self.gpr[4 + i], v & 0xFFFFFFFF)
		try: cpu.emu_start(function, 0x80000800, count=2000000)
		except unicorn.UcError as e: raise RuntimeError("emu error %s pc=%08x fn=%08x" % (e, cpu.reg_read(M.UC_MIPS_REG_PC), function))
		if cpu.reg_read(M.UC_MIPS_REG_PC) != 0x80000800: raise RuntimeError("did not return from %08x pc=%08x" % (function, cpu.reg_read(M.UC_MIPS_REG_PC)))
		return cpu.reg_read(M.UC_MIPS_REG_V0)

def run(answers=(0, 1, 2, 3), max_ticks=12000):
	e = intro_Emu(answers)
	# spawn hook: after 0x800C1010 returns, register slot by record pointer; hook 0x800C1040 (store into ctx+0x2c+slot*4)
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1)
		e.actors[ptr] = slot; e.record("spawn", slot=slot, record=hex(rec), ptr=hex(ptr), record_bytes=bytes(uc.mem_read(rec & 0x1FFFFFFF, 20)).hex())
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	# scene object = CTX; start scene: state 0 init
	e.w8(intro_CTX + 4, 0); e.w8(intro_CTX + 5, 0)
	table = 0x800F2204
	snapshots = []
	prev = {}
	for tick in range(max_ticks):
		state = e.u8(intro_CTX + 4)
		if state > 2: break
		handler = e.u32(table + state * 4)
		e.cur = None
		e.call(handler, (intro_CTX,))
		if state == 2 and e.u8(intro_CTX + 5) == 2:
			req = bytes(e.cpu.mem_read(0x80078D08 & 0x1FFFFFFF, 0x1A)); e.record("request_block", bytes=req.hex())
			e.w8(0x80078D08, 0); e.call(handler, (intro_CTX,)); break
		# actor updates
		for ptr, slot in list(e.actors.items()):
			if ptr not in e.actors: continue
			cls = e.u8(ptr + 4); cell = e.u32(0x800ED028 + cls * 4); fn = e.u32(cell)
			e.cur = slot
			e.call(fn, (ptr,))
			# snapshot pose
			pose = (s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 0xFFFF, e.u8(ptr + 0xA0), e.u8(ptr + 8), e.u8(ptr + 9), e.u8(ptr + 0xC))
			if prev.get(slot) != pose:
				snapshots.append({"t": tick, **e.where(), "slot": slot, "pos16": pose[:3], "yaw": pose[3], "control": pose[4], "mode8": pose[5], "mode9": pose[6], "modeC": pose[7]})
				prev[slot] = pose
		e.cur = None
		ppose = (s32(e.u32(intro_PLAYER + 0x10)), s32(e.u32(intro_PLAYER + 0x14)), s32(e.u32(intro_PLAYER + 0x18)), e.u16(intro_PLAYER + 0x2A), e.u8(intro_PLAYER + 0x1A0), e.u8(intro_PLAYER + 0x1A1), e.u8(intro_PLAYER) & 2)
		if prev.get("player") != ppose:
			snapshots.append({"t": tick, **e.where(), "slot": "player", "pos16": ppose[:3], "yaw": ppose[3], "face_eye_frame": ppose[4], "face_mouth_frame": ppose[5], "flag2": ppose[6]})
			prev["player"] = ppose
		if state == 2 and e.u8(intro_CTX + 5) >= 3: break
	return e, snapshots, tick


def intro_rd(a, n): o = 0x30 + a - 0x800E7000; return intro_OVL[o:o + n]
def intro_u32(a): return struct.unpack("<I", intro_rd(a, 4))[0]
intro_OUT = intro_ROOT + "/assets/levels/ST39/"
intro_H = lambda v: "0x%08x" % v
SRC_MSG = "SLES0x80048474/0x800489A0"

# ---------------------------------------------------------------- camera stream / timeline
def intro_commands():
	out = []; a = 0x800F1BAC
	while True:
		w = intro_u32(a); op = w >> 24
		size = 16 if 0x10 <= op <= 0x1A else 8 if op in (0x40, 0x41) else 20 if op == 0x42 else 4
		words = list(struct.unpack("<%dI" % (size // 4), intro_rd(a, size)))
		item = {"source_ram": intro_H(a), "opcode": op, "words": words}
		if op in (0x40, 0x41): item["actor_record"] = {"source_ram": intro_H(words[1]), "bytes": intro_rd(words[1], 20).hex()}
		if op in (0x18, 0x19):
			mode = (w >> 16) & 7
			item["interpolation"] = {"ticks": w & 0xFFFF, "ease_mode": mode, "ease": {0: "linear", 1: "cosine_in_out", 2: "quadratic_ease_out", 3: "quadratic_ease_in"}.get(mode, "linear"),
									 "target_fixed": [s32(x) / 65536 for x in words[1:]], "channel": "focus" if op == 0x18 else "orbit"}
		out.append(item); a += size
		if op == 0xFF: break
	assert a == 0x800F1F14, hex(a)
	return out
def intro_timeline():
	out = []; a = 0x800F1F14
	while True:
		p, s, d, cb = struct.unpack("<BBhI", intro_rd(a, 8))
		if p == 255: break
		out.append({"phase": p, "step": s, "duration": d, "callback": "0x%x" % cb, "source_ram": "0x%x" % a}); a += 8
	return out

# ---------------------------------------------------------------- actor records
MANIFEST = {}
CLASS_MODEL = {0x30: 0, 0x39: 1, 0x47: 2, 0x63: 3}
CLASS_NOTE = {0x30: "Flutter exterior (largest model, ~6 units; pool type 0x20 class 0x30, controller ST39T 0x800E7594)",
			  0x39: "humanoid with face channels, 0.68 units tall, 21 controls (class 0x39; variant 0 controller 0x800E7B34, variant 1 controller 0x800E7E58 + answer lip-sync 0x800E897C) - identity unverified (likely Roll)",
			  0x47: "flat 2-node prop 0.3x0.3 units, 6 controls (class 0x47, controller ST39T 0x800E8ED0) - identity unverified",
			  0x63: "small 8-node character with face channel, 0.19 units tall, 13 controls (class 0x63; variant 0 0x800E9178, variant 1 0x800E9514) - identity unverified (likely Data)"}
RECORD_AREA = {0x800F1B0C: 0, 0x800F1B20: 1, 0x800F1B34: 1, 0x800F1B48: 1, 0x800F1B5C: 0, 0x800F1B70: 1, 0x800F1B84: 1, 0x800F1B98: 1}
def actor_records():
	out = []
	for a in sorted(RECORD_AREA):
		b = intro_rd(a, 20); cls = b[4]; x, y, z, yaw = struct.unpack_from("<3hH", b, 12); idx = CLASS_MODEL[cls]
		model = MANIFEST["models"][idx]; exp = model.get("export", {})
		turns = -(yaw / 4096.0)
		if turns < -0.5: turns += 1.0
		mfile = model["file"]
		out.append({"source_ram": intro_H(a), "slot": b[1], "class_note": CLASS_NOTE[cls],
					"entry": {"stage": "ST39", "area": RECORD_AREA[a], "source_record_ram": intro_H(a), "source_bytes_hex": b.hex(), "pool_type": b[2], "actor_class": cls, "actor_state": b[5], "resource_variant": b[6],
							  "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": idx, "model_file": mfile},
					"model": {"file": mfile, "source_archive": "DAT/ST39.BIN section 0x3000 (ST39_03000)", "source_model_index": idx, "source_flags": model["flags"], "class_from_flags": model["flags"] >> 8,
							  **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp},
							  "model_file": mfile, "model_index": idx,
							  "alternate_bank": {0x47: "ST3901_03000/model_001.glb (flags 0x4720)", 0x63: "ST3901_03000/model_002.glb (flags 0x6320)"}.get(cls)}})
	return out

# ---------------------------------------------------------------- XA descriptors, face tables
def xa_desc(i):
	a = 0x800ED774 + i * 8; raw = intro_rd(a, 8)
	return {"id": i, "descriptor_ram": intro_H(a), "descriptor_bytes": raw.hex(), "archive_index": raw[0], "archive": "XA/PAL_37.XA" if raw[0] == 2 else None,
			"sector_start": (raw[1] << 16) | struct.unpack_from("<H", raw, 2)[0], "sector_end": (raw[5] << 16) | struct.unpack_from("<H", raw, 6)[0], "channel": raw[4] & 31, "flags": raw[4] & 0xE0}
def face_table(base, limit):
	seqs = []
	ptrs = [intro_u32(base + i * 4) for i in range(limit)]
	for i, p in enumerate(ptrs):
		frames = []; a = p
		while True:
			f, dur, op, arg = intro_rd(a, 4)
			frames.append({"frame": f, "ticks": dur, "op": op, "arg": arg}); a += 4
			if op in (1, 2, 4) or len(frames) > 64: break
		seqs.append({"sequence": i, "source_ram": intro_H(p), "entries": frames})
	return {"table_ram": intro_H(base), "semantics": "SLES0x80041358: each tick writes entry.frame to the channel byte, counts entry.ticks, then op 1=hold (channel stops), 2=restart at entry 0, 4=index+=arg, other=next entry", "sequences": seqs}

# ---------------------------------------------------------------- emulation
def intro_emulate(answers=(0, 1, 2, 3)):
	e = intro_Emu(answers)
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1); e.actors[ptr] = slot
		e.record("spawn", slot=slot, record=intro_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	tracks = {}; ticks = 0
	for tick in range(20000):
		st = e.u8(intro_CTX + 4)
		if st > 2: break
		h = e.u32(0x800F2204 + st * 4); e.cur = None
		if st == 2 and e.u8(intro_CTX + 5) == 2:
			e.record("request_block", bytes=bytes(e.cpu.mem_read(0x80078D08 & 0x1FFFFFFF, 0x1A)).hex()); e.w8(0x80078D08, 0); e.call(h, (intro_CTX,)); break
		e.call(h, (intro_CTX,))
		w = e.where()
		for ptr, slot in list(e.actors.items()):
			if ptr not in e.actors: continue
			fn = e.u32(e.u32(0x800ED028 + e.u8(ptr + 4) * 4)); e.cur = slot; e.call(fn, (ptr,))
			tracks.setdefault(slot, []).append((tick, w["step"], w["frame"], s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, w["sub7"]))
		e.cur = None; ticks = tick
	return e, tracks, ticks

def compress(rows):
	"""keep keyframes where per-tick delta changes (piecewise linear in native ticks)"""
	if not rows: return []
	keep = [rows[0]]
	for i in range(1, len(rows) - 1):
		a, b, c = rows[i - 1], rows[i], rows[i + 1]
		d1 = tuple(b[k] - a[k] for k in (3, 4, 5, 6)); d2 = tuple(c[k] - b[k] for k in (3, 4, 5, 6))
		if d1 != d2 or b[1] != a[1] or c[1] != b[1]: keep.append(b)
	keep.append(rows[-1])
	out = []
	for r in keep:
		k = {"step": r[1], "tick": r[2], "position_raw": [round(r[3] / 65536, 5), round(r[4] / 65536, 5), round(r[5] / 65536, 5)], "yaw_raw": r[6]}
		if not out or out[-1] != k: out.append(k)
	return out

def export_intro_scene():
	global intro_SLES, intro_GAME, intro_OVL, MANIFEST
	intro_SLES = open(intro_ROOT + "/build/disc-assets/SLES_035.56", "rb").read(); intro_GAME = open(intro_ROOT + "/build/disc-assets/COMMON/GAME.BIN", "rb").read(); intro_OVL = open(intro_ROOT + "/build/disc-assets/DAT/ST39T.BIN", "rb").read()
	MANIFEST = json.load(open(intro_ROOT + "/assets/levels/ST39/models/ST39_03000/manifest.json", encoding="utf-8"))
	cmds = intro_commands(); tl = intro_timeline(); recs = actor_records()
	import models as player_models, world
	disc = Path(intro_ROOT) / "build/disc-assets"; player_payload = (disc / "COMMON/PL00P000.BIN").read_bytes()[0x30:]; face_word = struct.unpack_from("<4I", player_payload, 0x60)[2]
	vram, _ = player_models.textures(disc / "COMMON/PL00T.BIN"); world.texture_uploads((disc / "DAT/ST39T.BIN").read_bytes(), vram, "DAT/ST39T.BIN")
	write_output(Path(intro_OUT) / "player_face_page1.png", player_models.texture_page(vram, face_word >> 16, (face_word & 0xFFFF) + 1))
	actors = Path(intro_OUT) / "actors"; actors.mkdir(parents=True, exist_ok=True)
	for record in recs:
		source = Path(intro_ROOT) / record["model"]["file"]; runtime = "assets/levels/ST39/actors/" + source.name
		for item in source.parent.glob(source.stem + "*"):
			if item.suffix in (".glb", ".png"): write_output(actors / item.name, item.read_bytes())
		record["entry"]["model_file"] = record["model"]["model_file"] = runtime
	e, tracks, ticks = intro_emulate()
	ev = e.events
	# ---------------- cross-check hand translation against emulation (player controls / faces)
	emu_player = [(x["step"], x["frame"], x["args"][0], x["args"][1]) for x in ev if x["kind"] == "player_control"]
	emu_face = [(x["step"], x["frame"], x["kind"], x["args"][1]) for x in ev if x["kind"] in ("face_eyes", "face_mouth") and x.get("actor_slot") is None]

	P = lambda c, src, start=0: {"op": "player_control", "control": c, "start_record": start, "source": src, "native": "GAME0x800CDE5C(%d,%d,1)" % (c, start)}
	EY = lambda s, src: {"op": "player_face", "channel": "eyes", "sequence": s, "source": src, "native": "SLES0x80041338(ctx+0xB0,%d,0)" % s}
	MO = lambda s, src: {"op": "player_face", "channel": "mouth", "sequence": s, "source": src, "native": "SLES0x80041348(ctx+0xB0,%d,0)" % s}
	VIS = lambda on, src: {"op": "player_render_flag", "set": on, "source": src, "native": "0x8008C0A0 byte0 %s 0x02" % ("|=" if on else "&=~")}
	SKY = lambda h, p, src: dict({"op": "sky_gradient", "horizon_raw": h, "source": src, "native": "0x800966C0+0x16" + ("/+0x18" if p is not None else "")}, **({"param_18_raw": p} if p is not None else {}))
	SND = lambda i, src: {"op": "play_sound", "id": i, "source": src, "native": "SLES0x80020160(0x%X)" % i}
	AREA = lambda area, pos, facing, src: {"op": "area_change", "stage": "ST39", "area": area, "position_raw": pos, "facing_raw": facing, "fade_arrival": 255, "fade_exit": 255, "request_type": -1, "source": src,
										  "native": "request block 0x80078D08: +0=-1 +4=0x39 +5=%d +0x10/12/14=%s +0x16=%d +0x18=0xFF +0x19=0xFF; ctx+6=0; GAME0x800C0EA8(1)" % (area, pos, facing)}
	ASTATE = lambda slot, rec, v, src: {"op": "actor_state", "slot": slot, "record": rec, "field_0x0C": v, "field_0x0D": 0, "source": src}
	def act(tick, *ops): return [dict(o, tick=tick) for o in ops]

	seg = {}
	# step 0 (0x800EBB7C): frame-switched, callback-advanced
	seg["0:0"] = {"source": "0x800EBB7C", "area": 0, "actions": act(300, SKY(0x280, 0, "0x800EBBAC")),
				  "program": [{"op": "minimum_tick", "tick": 565, "source": "0x800EBB9C"}, AREA(1, [0, 0, -184], 0, "0x800EBBC4..0x800EBC14"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EBC10"}]}
	# step 1 (0x800EBC28) duration 130
	seg["0:1"] = {"source": "0x800EBC28", "area": 1,
				  "actions": act(0, {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EBC50", "native": "SLES0x8003D658(0xFFE,0x80)"}, VIS(True, "0x800EBC68"), SKY(0x190, 0x180, "0x800EBC78/0x800EBC84"),
								 SND(0x29F, "0x800EBC80"), {"op": "sound_latch", "value": 1, "source": "0x800EBC8C", "native": "ctx+0x0D=1 (finish plays 0x2A0 when set)"},
								 P(0x80, "0x800EBCD8"), EY(0, "0x800EBCEC"), MO(0, "0x800EBCFC"))
				  + act(30, EY(1, "0x800EBD50"))
				  + act(65, P(0x81, "0x800EBD20"), EY(0, "0x800EBD30"), ASTATE(2, "0x800f1b34", 1, "0x800EBD38..0x800EBD48 (ctx+0x34 -> slot 2)"))
				  + act(110, EY(2, "0x800EBD50")),
				  "program": []}
	seg["0:2"] = {"source": "0x800EBD6C", "area": 1, "actions": act(0, SKY(0x26C, None, "0x800EBD88"), VIS(False, "0x800EBD90")), "program": []}
	# step 3 (0x800EBD9C) duration 1020
	roll = []
	for f in range(0x14A, 0x14A + 0x21):
		v1 = f - 0x14A; off = 0x800 + 0x80073E4C - 0x80010000 + ((v1 << 8) & 0x3F00)
		roll.append(intro_s16(struct.unpack_from("<H", intro_SLES, off)[0]) >> 5)
	seg["0:3"] = {"source": "0x800EBD9C", "area": 1,
				  "actions": act(0, VIS(True, "0x800EBDCC"), P(0x82, "0x800EBE68"), EY(3, "0x800EBE7C"), MO(1, "0x800EBFB0"))
				  + act(100, MO(2, "0x800EBE90/0x800EBFB0")) + act(240, MO(1, "0x800EBE9C/0x800EBFB0"))
				  + act(330, P(0x83, "0x800EBEAC"), EY(4, "0x800EBEC0"), MO(3, "0x800EBED0"), ASTATE(2, "0x800f1b34", 2, "0x800EBEE4..0x800EBEF4"),
						{"op": "camera_shake", "magnitude_raw": 0x200, "decay_raw": 0x10, "source": "0x800EBEF0", "native": "SLES0x80016B1C(0,0x200,0x10): camera state 0x8007D010+0xD8=0x200,+0xDC=0x10; GAME0x800C24C0 subtracts (+0xD8>>8) from focus Y"},
						{"op": "vibration", "args_raw": [0, 0x011820FF], "source": "0x800EBF00", "native": "SLES0x80047180(0,0x011820FF) -> gp+0x750..0x754 = 0x00,0x00,0xFF,0x20,0x18", "unverified": True, "note": "pad actuator request; byte meaning (strength/duration) unverified"})
				  + act(350, EY(5, "0x800EBF1C"), MO(4, "0x800EBFB0")) + act(440, EY(6, "0x800EBF38"), MO(5, "0x800EBFB0")) + act(520, MO(4, "0x800EBF4C/0x800EBFB0"))
				  + act(820, P(0x84, "0x800EBF60"), EY(7, "0x800EBF74"), MO(6, "0x800EBFB0")) + act(920, P(0x85, "0x800EBF8C"), EY(8, "0x800EBFA0"), MO(7, "0x800EBFB0")),
				  "camera_roll": {"op": "camera_roll", "from_tick": 330, "through_tick": 362, "values_raw": roll, "otherwise": 0, "source": "0x800EBFB8..0x800EBFF8",
								  "native": "0x80096D64 (= camera ctx 0x80096D50+0x14) = s16(SLES trig 0x80073E4C[(frame-330)*64].sin)>>5, else 0; GAME0x800C2518 passes it as roll to SLES0x80015B6C"},
				  "program": []}
	seg["0:4"] = {"source": "0x800EC010", "area": 1,
				  "actions": act(0, P(0x86, "0x800EC074"), EY(9, "0x800EC088"), MO(9, "0x800EC098"), ASTATE(2, "0x800f1b34", 5, "0x800EC0A0..0x800EC0B0"))
				  + act(240, EY(10, "0x800EC0BC"), MO(8, "0x800EC108")) + act(390, MO(9, "0x800EC0D0/0x800EC108")) + act(530, P(0x87, "0x800EC0E4"), EY(11, "0x800EC0F8"), MO(10, "0x800EC108")),
				  "program": [{"op": "minimum_tick", "tick": 605, "source": "0x800EC05C"}, AREA(0, [0, 0, 0], 0, "0x800EC118..0x800EC160"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EC15C"}]}
	seg["0:5"] = {"source": "0x800EC178", "area": 0,
				  "actions": act(0, SKY(0x244, -0x180, "0x800EC1AC/0x800EC1B8"), VIS(False, "0x800EC1C4"), SND(0x2A0, "0x800EC1C0"), {"op": "sound_latch", "value": 0, "source": "0x800EC1CC"}),
				  "program": [{"op": "minimum_tick", "tick": 120, "source": "0x800EC1D0"}, AREA(1, [0x40, 0, -0xA0], 0, "0x800EC1D8..0x800EC22C"), {"op": "advance", "source": "GAME0x800C0EA8(1) at 0x800EC228"}]}
	seg["0:6"] = {"source": "0x800EC240", "area": 1, "substate_gate": "actions run only while ctx+6 == 0",
				  "actions": act(0, {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EC3A0"}, VIS(True, "0x800EC3C4"), P(0x88, "0x800EC3C0"), EY(12, "0x800EC3D4"), MO(10, "0x800EC3E4"), SND(0x29F, "0x800EC3EC"), {"op": "sound_latch", "value": 1, "source": "0x800EC3FC"})
				  + act(390, P(0x89, "0x800EC408"), EY(11, "0x800EC41C"), MO(12, "0x800EC530")) + act(520, P(0x8A, "0x800EC434"), EY(11, "0x800EC448"), MO(13, "0x800EC530"))
				  + act(750, MO(14, "0x800EC45C")) + act(770, MO(15, "0x800EC468")) + act(780, MO(14, "0x800EC470")) + act(790, MO(15, "0x800EC47C"))
				  + act(1500, P(0x8B, "0x800EC48C"), EY(14, "0x800EC4A0"), MO(11, "0x800EC530")) + act(1690, P(0x8C, "0x800EC4B4/0x800EC55C"))
				  + act(1875, P(0x8D, "0x800EC4C0"), EY(12, "0x800EC4D4"), MO(10, "0x800EC52C/0x800EC530")) + act(1920, ASTATE(7, "0x800f1b98", 3, "0x800EC4E4..0x800EC550 (ctx+0x48 -> slot 7)"))
				  + act(2140, P(0x8E, "0x800EC4F8"), EY(12, "0x800EC50C"), MO(16, "0x800EC530")) + act(2150, MO(10, "0x800EC52C")) + act(2160, MO(16, "0x800EC520")) + act(2190, MO(10, "0x800EC52C"))
				  + act(2290, ASTATE(7, "0x800f1b98", 4, "0x800EC540..0x800EC550")) + act(2310, P(0x8F, "0x800EC55C")),
				  "program": [{"op": "minimum_tick", "tick": 2420, "source": "0x800EC390"},
							  {"op": "xa_fade_out", "speed": 8, "only_if_xa_ready": True, "source": "0x800EC56C..0x800EC580", "native": "if SLES0x8001AF94(): SLES0x8001BA44(8)"},
							  {"op": "skip_lock", "set": True, "source": "0x800EC58C", "native": "ctx 0x8007CEC0 byte0 |= 0x20 (GAME0x800C10B4 ignores Start while set)"},
							  {"op": "wait_xa_idle", "source": "0x800EC5A0", "native": "SLES0x8001AFD0() (0x80078DC8 bit0 clear)"},
							  {"op": "advance", "source": "0x800EC5B0..0x800EC5B4"}]}
	seg["0:7"] = {"source": "0x800EC5D0", "area": 1,
				  "motion": [{"actor": "player", "op": "player_axis_set", "axis": "x", "from_tick": 0, "through_tick": 16, "value_raw": "0x40 + tick", "source": "0x800EC600..0x800EC60C", "native": "0x8008C0B2 (player +0x12, X integer) = ctx+0x28 + 0x40 while ctx+6==0"}],
				  "program": [{"op": "minimum_tick", "tick": 16, "source": "0x800EC614"},
							  {"op": "label", "name": "ask", "source": "0x800EC668 (ctx+7 state 0)"},
							  {"op": "message", "index": 0, "state": 1, "source": SRC_MSG + " at 0x800EC674/0x800EC68C", "note": "4-way choice; bank messages 1..4 set event flags 0x680..0x683 (cancel -> 4 -> 0x683)"},
							  {"op": "select_by_flags", "flags": [0x680, 0x681, 0x682, 0x683], "store": "answer", "keep_previous_if_none": True, "initial": 0, "source": "0x800EC69C..0x800EC6E8"},
							  {"op": "play_xa", "descriptor_by_answer": [0x58, 0x59, 0x5A, 0x5B], "select": "answer", "descriptor_table_ram": "0x800F2210", "source": "0x800EC6EC..0x800EC774", "native": "wait !(0x80078DBA&1); SLES0x8001B714(id); wait !(0x80078DBA&2); SLES0x8001B864(id); wait SLES0x8001AF94()"},
							  {"op": "director_state", "state": 5, "source": "ctx+7 = 5 (actor slot 5 controller 0x800E897C starts the answer reaction on this value)"},
							  {"op": "jump_if", "answer": 3, "to": "leave", "source": "0x800EC788..0x800EC794"},
							  {"op": "wait_flag_clear", "flag": "0x680 + answer", "source": "0x800EC798..0x800EC7A0"},
							  {"op": "wait_xa_idle", "source": "0x800EC7A8"},
							  {"op": "jump", "to": "ask", "source": "0x800EC7B8 (ctx+7 = 0)"},
							  {"op": "label", "name": "leave"},
							  {"op": "wait_flag_clear", "flag": 0x683, "source": "0x800EC7C0..0x800EC7C8"},
							  {"op": "advance", "source": "0x800EC7D0..0x800EC7D4"}]}
	seg["0:8"] = {"source": "0x800EC7EC", "area": 1,
				  "motion": [{"actor": "player", "op": "player_axis_set", "axis": "x", "from_tick": 0, "through_tick": 16, "value_raw": "0x50 - tick", "source": "0x800EC81C..0x800EC82C"}],
				  "actions": act(16, {"op": "skip_lock", "set": False, "source": "0x800EC840..0x800EC850", "native": "ctx byte0 &= ~0x20; ctx+6 = 1"})
				  + act(40, P(0x90, "0x800EC8B0"), EY(16, "0x800EC8C4"), MO(11, "0x800EC934")) + act(80, MO(20, "0x800EC8D8/0x800EC934")) + act(130, MO(11, "0x800EC8E0/0x800EC934"))
				  + act(230, EY(17, "0x800EC8F8"), MO(21, "0x800EC934")) + act(280, P(0x91, "0x800EC910"), EY(18, "0x800EC924"), MO(17, "0x800EC934")),
				  "substate_gate": "ticks 40..280 actions run only after ctx+6 became 1 at tick 16", "program": []}
	seg["0:9"] = {"source": "0x800EC94C", "area": 1,
				  "actions": act(0, P(0x92, "0x800ECA50"), EY(19, "0x800ECA64"), MO(18, "0x800ECA74"),
								 {"op": "player_axis_set", "axis": "x", "value_raw": 0x50, "source": "0x800ECA80", "native": "player +0x12 = 0x50"},
								 {"op": "player_yaw_set", "yaw_raw": 0x60, "source": "0x800ECA84", "native": "player +0x2A = 0x60"})
				  + act(5, P(0x93, "0x800ECA9C")) + act(30, P(0x94, "0x800ECA9C")) + act(40, P(0x95, "0x800ECAB0"), EY(12, "0x800ECAC0"))
				  + act(80, MO(19, "0x800ECAD0/0x800ECB30")) + act(120, MO(13, "0x800ECADC/0x800ECB30")) + act(200, P(0x96, "0x800ECAF0"), EY(13, "0x800ECB04"), MO(16, "0x800ECB30"))
				  + act(220, P(0x97, "0x800ECB20"), MO(10, "0x800ECB30"))
				  + act(225, P(1, "0x800ECB4C (ctx+6==1, one tick after tick 224 set it)", 4), {"op": "player_yaw_add", "delta_raw": 0x800, "source": "0x800ECB54..0x800ECB60"}),
				  "motion": [{"actor": "player", "from_tick": 225, "velocity_raw": [0, 0, -0x200], "source": "0x800ECB74..0x800ECB84", "native": "SLES0x800417AC(player,0,0,-0x200) each tick while ctx+6==2 (emulated: 32 raw units/tick along facing)"}],
				  "program": [{"op": "minimum_tick", "tick": 250, "source": "0x800ECBA8..0x800ECBB0"},
							  {"op": "fade", "type": 0x12, "wait": True, "source": "0x800ECBBC (SLES0x8001392C(0x12,0)); wait 0x80078F01==0 at 0x800ECBE0", "native": "also ctx byte0 |= 0x04 (blocks skip)"},
							  {"op": "advance", "source": "0x800ECBF0..0x800ECBF4 (timeline ends -> finish handler 0x800EB9F4)"}]}
	for k, v in seg.items(): v.setdefault("program", [])

	# cross-check
	hand_p = []; hand_f = []
	for k, v in seg.items():
		step = int(k.split(":")[1])
		for a in v.get("actions", []):
			if a["op"] == "player_control": hand_p.append((step, a["tick"], a["control"], a["start_record"]))
			if a["op"] == "player_face": hand_f.append((step, a["tick"], "face_eyes" if a["channel"] == "eyes" else "face_mouth", a["sequence"]))
	emu_p_scene = [x for x in emu_player if not (x[0] == 0 and x[1] == 0 and x[2] == 0)]  # drop finish-handler call
	emu_f_scene = [x for x in emu_face if not (x[0] == 0 and x[1] in (0, 1))]
	cross = {"player_control_match": sorted(hand_p) == sorted(emu_p_scene), "player_face_match": sorted(set(hand_f)) == sorted(set(emu_f_scene)),
			 "player_control_only_hand": sorted(set(hand_p) - set(emu_p_scene)), "player_control_only_emu": sorted(set(emu_p_scene) - set(hand_p)),
			 "face_only_hand": sorted(set(hand_f) - set(emu_f_scene)), "face_only_emu": sorted(set(emu_f_scene) - set(hand_f))}

	# ---------------- actor controllers from emulation
	ctrl = {}
	rec_by_slot = {r["slot"]: r for r in recs}
	xa_ready7 = [x["frame"] for x in ev if x["kind"] == "xa_ready" and x["step"] == 7]
	def answer_of(frame):
		k = -1
		for i, f in enumerate(xa_ready7):
			if frame > f: k = i
		return k
	for slot, rows in sorted(tracks.items(), key=lambda kv: str(kv[0])):
		r = rec_by_slot[slot]; cls = r["entry"]["actor_class"]; var = r["entry"]["resource_variant"]
		fn = {0x30: "0x800E7594", 0x47: "0x800E8ED0", 0x39: ["0x800E7B34", "0x800E7E58"][var], 0x63: ["0x800E9178", "0x800E9514", "0x800E96C0"][var]}[cls]
		sev = [x for x in ev if x.get("actor_slot") == slot]
		controls = [x for x in sev if x["kind"] == "actor_control"]
		startup = controls[0] if controls else None
		events = []; answer_events = {}
		for x in sev:
			item = None
			if x["kind"] == "actor_control" and x is not startup: item = {"op": "control", "control": x["args"][1], "start_record": x["args"][2], "native": "SLES0x8003F4BC via %s" % x["caller"]}
			elif x["kind"] in ("face_eyes", "face_mouth"): item = {"op": "actor_face", "channel": "eyes" if x["kind"] == "face_eyes" else "mouth", "sequence": x["args"][1], "native": "%s via %s" % ("SLES0x80041338" if x["kind"] == "face_eyes" else "SLES0x80041348", x["caller"])}
			elif x["kind"] == "face_init": item = {"op": "actor_face_init", "eye_table_ram": intro_H(x["args"][1] & 0xFFFFFFFF), "mouth_table_ram": intro_H(x["args"][2] & 0xFFFFFFFF) if x["args"][2] else None, "native": "SLES0x80041318 via %s" % x["caller"]}
			elif x["kind"] == "flag_clear": item = {"op": "event_clear", "id": x["args"][0], "native": "GAME0x800C0584 via %s" % x["caller"]}
			elif x["kind"] == "spawn_effect_8": item = {"op": "effect_spawn", "native": "SLES0x8003E8F8 (pool 8) via %s" % x["caller"], "args_raw": [a & 0xFFFFFFFF for a in x["args"][:2]], "unverified": True}
			if item is None: continue
			if x["step"] == 7 and slot == 5 and answer_of(x["frame"]) >= 0:
				ans = answer_of(x["frame"]); answer_events.setdefault(str(ans), []).append(dict(item, after_xa_ready_ticks=x["frame"] - xa_ready7[ans]))
			else:
				events.append(dict(item, step=x["step"], tick=x["frame"]))
		prof = {"tick_note": "tick = ctx+0x28 as read by the actor after GAME0x800C0D70 incremented it (actors emulated after the scene update; native ordering of scene vs actor update is unverified, +-1 tick)", "source": "ST39T " + fn + " (emulated with unicorn: class function run once per native tick after the scene update; render/animation helpers stubbed)", "class": cls, "variant": var, "record": r["source_ram"]}
		if startup: prof["startup_control"] = startup["args"][1]; prof["startup_start_record"] = startup["args"][2]
		prof["events"] = events
		if answer_events: prof["answer_reactions"] = {"relative_to": "frame at which play_xa reported ready (ctx+7 becomes 5) for that answer", "source": "ST39T 0x800E897C (called from 0x800E8764 while ctx+3==7)", "by_answer": answer_events,
													  "flag_clear_after_ticks": {"0": 450, "1": 310, "2": 270, "3": 120}, "flag_clear_source": "0x800E8BE8 (0x680@0x1C2), 0x800E8CDC (0x681@0x136), 0x800E8D8C (0x682@0x10E), 0x800E8E3C (0x683@0x78, then mode 5)"}
		prof["track"] = {"op": "actor_track", "interpolation": "linear between keyframes in native ticks (keyframes where per-tick delta changes)", "keyframes": compress(rows)}
		ctrl[str(slot)] = prof

	# player face tables & actor face tables
	faces = {"player_eyes": face_table(0x800F2018, 20), "player_mouth": face_table(0x800F21AC, 22)}
	for prof in ctrl.values():
		events = prof["events"] + [e for group in prof.get("answer_reactions", {}).get("by_answer", {}).values() for e in group]
		for channel, key in (("eyes", "eye_table_ram"), ("mouth", "mouth_table_ram")):
			tables = {e[key].lower() for e in events if e["op"] == "actor_face_init" and e.get(key)}; used = [e["sequence"] for e in events if e["op"] == "actor_face" and e["channel"] == channel]
			for table in tables:
				if used: faces[table] = face_table(int(table, 16), max(used) + 1)

	xa = {"intro": xa_desc(0x47), "answers": [xa_desc(i) for i in (0x58, 0x59, 0x5A, 0x5B)], "descriptor_table": "0x800ED774 (ST39T 0x800E7148 stores it at 0x80078DD8; SLES0x8001B9D0 indexes 8-byte descriptors)",
		  "prepare": "SLES0x8001B714", "play": "SLES0x8001B864", "ready": "SLES0x8001AF94", "idle": "SLES0x8001AFD0", "fade_out": "SLES0x8001BA44"}

	req = [x for x in ev if x["kind"] == "request_block"][0]["bytes"]
	scene = {"stage": "ST39", "area": 0, "scene_id": 5, "native_tick_hz": 25, "callback_contract_file": "scene_05_callbacks.json",
			 "commands": cmds, "timeline": tl, "actors": recs,
			 "player": {"scene_init": {"position_raw": [0, 0, 0], "yaw_raw": None, "yaw_note": "init (0x800EB86C..0x800EB89C) zeroes player +0x10/+0x14/+0x18 (+0xF0/+0xF4, face bytes +0x1A0/+0x1A1); yaw +0x2A is not written (inherits area-entry yaw)", "unverified_yaw": True},
						"per_area_entries": [
							{"area": 0, "when": "scene start (Game Start enters ST39:0)", "position_raw": [0, 0, 0], "source": "0x800EB890..0x800EB898"},
							{"area": 1, "when": "step 0 tick 565", "position_raw": [0, 0, -184], "facing_raw": 0, "source": "0x800EBBC4..0x800EBC14"},
							{"area": 0, "when": "step 4 tick 605", "position_raw": [0, 0, 0], "facing_raw": 0, "source": "0x800EC118..0x800EC160"},
							{"area": 1, "when": "step 5 tick 120", "position_raw": [0x40, 0, -0xA0], "facing_raw": 0, "source": "0x800EC1D8..0x800EC22C"},
							{"area": 1, "when": "step 9 tick 0", "position_raw": [0x50, None, None], "yaw_raw": 0x60, "source": "0x800ECA7C..0x800ECA84 (only X and yaw written)"}],
						"camera_opcode_0x42_used": False},
			 "face_tables": faces,
			 "xa": xa,
			 "audio_cues": [{"kind": "xa", "id": 0x47, "when": "scene init states 2..4 (0x800EB8F0/0x800EB918); timeline starts only after SLES0x8001AF94 reports ready (0x800EB934)"},
							{"kind": "xa", "id": "0x58..0x5B by answer", "when": "step 7 answer loop (0x800EC718/0x800EC754)"},
							{"kind": "xa_fade_out", "speed": 8, "when": "step 6 tick 2420 (0x800EC57C) and finish if still playing (0x800EBAAC)"},
							{"kind": "sound", "id": 0x29F, "when": "step 1 tick 0 (0x800EBC80), step 6 tick 0 (0x800EC3EC)"},
							{"kind": "sound", "id": 0x2A0, "when": "step 5 tick 0 (0x800EC1C0), finish if ctx+0xD latched (0x800EBA90)", "note": "pairs with 0x29F (latched in ctx+0xD); stop-cue semantics unverified"},
							{"kind": "music", "note": "no music cue call in scene 5 code; finish calls SLES0x8001B7E8(-1) which stores 0xFFFF at 0x800966BA (XA/music selection reset, semantics unverified)"}],
			 "camera_interpolation": {"opcodes": {"0x18": "focus interpolation: header bits16..18 = ease mode, low16 = ticks; from current focus (absolute or actor-relative) to words[1..3] (GAME0x800C174C)", "0x19": "orbit interpolation: same header layout; from current orbit (+0x58..+0x60) to words[1..3] (GAME0x800C182C)"},
									  "ease_table": "GAME0x800DC7E0: 0 linear 0x800C1EC4, 1 cosine in-out 0x800C2114, 2 quadratic ease-out 0x800C2234, 3 quadratic ease-in 0x800C2318, 4..7 linear",
									  "runtime_support": "native_scene.gd _commands() treats opcodes 24/25 as unknown (sets message_failed) - must be added"},
			 "emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "simulated_answers": e.answer_log, "finish_request_block": req, "cross_check": cross},
			 "source": {"overlay": "DAT/ST39T.BIN (load 0x800E7000; ST3901T.BIN code region 0x30..0x1E000 byte-identical)", "handler_table": "0x800F2204 (init 0x800EB7CC, update 0x800EB960, finish 0x800EB9F4)", "dispatch": "0x800EB790",
						"initialize": "0x800EB7CC (jump table 0x800E7048)", "update": "0x800EB960", "finish": "0x800EB9F4", "command_pointer": "0x800f1bac", "timeline_pointer": "0x800f1f14",
						"command_interpreter": "GAME0x800C1204 (sizes verified: 0x10..0x1A=16, 0x40/0x41=8, 0x42=20, else 4; stream ends exactly at timeline)", "timeline_runner": "GAME0x800C0D70", "advance": "GAME0x800C0EA8",
						"scene_context": "0x8007CEC0 (+2 phase,+3 step,+4/+5 handler state,+6/+7 callback substates,+0xC answer,+0xD sound latch,+0x28 step frame,+0x2C+slot*4 actor pointers,+0xAC timeline ptr,+0xB0 player face controller)",
						"actor_class_table": "0x800ED028 (class->cell): 0x02->0x800E7370, 0x30->0x800E7594, 0x39->0x800E79E0 (variants 0x800EDB94), 0x47->0x800E8ED0, 0x63->0x800E8FCC (variants 0x800EDDD4)"}}

	contract = {"schema": 1, "stage": "ST39", "scene_id": 5,
				"source": "Original ST39T scene handler 0x800EB790 (init 0x800EB7CC, update 0x800EB960, finish 0x800EB9F4) and timeline callbacks 0x800EBB7C..0x800ECC10; actor controllers ST39T 0x800E7594/0x800E79E0/0x800E8ED0/0x800E8FCC",
				"tick_basis": "tick = native ctx+0x28 value seen by the callback (step 0 starts at 1 because init state 0 runs GAME0x800C0D70 once; other steps start at 0). A callback-driven advance (GAME0x800C0EA8) sets ctx byte0 bit 0x08 so GAME0x800C0D70 skips the camera interpreter and frame increment on that tick.",
				"initialization": {"player_position_raw": [0, 0, 0], "player_yaw_raw": 0, "player_yaw_unverified": True, "player_yaw_note": "native init does not write yaw (+0x2A); 0 is a placeholder; player render flag is cleared during the area-0 shots", "source": "0x800EB86C..0x800EB8CC", "player_state_gate": "GAME0x800CDD50()==0 (0x800EB86C)",
								   "spawn_records": [], "spawn_note": "slot 0 (0x800f1b0c) is activated by camera opcode 0x40 at total tick 0; every other record by later 0x40 commands",
								   "init_ops": [{"op": "camera_start", "commands": "0x800F1BAC", "timeline": "0x800F1F14", "source": "0x800EB818..0x800EB828 GAME0x800C0C5C"},
												{"op": "restore_call", "native": "GAME0x800C1148", "source": "0x800EB82C"},
												SKY(0x258, -0x300, "0x800EB83C..0x800EB84C"), VIS(False, "0x800EB850..0x800EB858"),
												{"op": "player_face_init", "eye_table_ram": "0x800F2018", "mouth_table_ram": "0x800F21AC", "source": "0x800EB87C..0x800EB8A8 SLES0x80041318(ctx+0xB0,...)"},
												EY(0, "0x800EB8B8"), MO(0, "0x800EB8C8"),
												{"op": "play_xa", "descriptor": 0x47, "wait_ready": True, "source": "0x800EB8D8..0x800EB944"}],
								   "xa_start": {"descriptor_index": 0x47, "note": "timeline starts after XA 0x47 reports ready"}},
				"segments": seg, "actor_controllers": ctrl,
				"finish": {"source": "ST39T 0x800EB9F4", "fade_exit": 0x12, "fade_exit_source": "issued by step 9 at tick 250 (0x800ECBBC)",
						   "ops": [{"op": "vibration", "args_raw": [0, 0x01000000], "source": "0x800EBA54", "note": "bit24 forces the request; stops vibration (unverified)"},
								   P(0, "0x800EBA64"), {"op": "pool_clear", "mask": 0xFFE, "flags": 0x80, "source": "0x800EBA70"}, {"op": "close_windows", "source": "0x800EBA78 SLES0x80048944(0)"},
								   {"op": "play_sound_if_latched", "id": 0x2A0, "source": "0x800EBA80..0x800EBA98"}, {"op": "xa_fade_out", "speed": 8, "only_if_xa_ready": True, "source": "0x800EBA9C..0x800EBAB0"},
								   {"op": "wait_xa_idle", "source": "0x800EBAC4"}],
						   "skip_path": {"source": "0x800EB9A0..0x800EB9CC", "condition": "GAME0x800C10B4() (Start pressed, ctx byte0 bits 0x20/0x04 clear, fade idle, game mode 0x203) AND scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0) then handler state 2", "unverified": "meaning of 0x1F800004 (if 0, a skip request is ignored)"},
						   "restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
						   "transition": {"destination_stage": "ST1E", "destination_area": 0, "destination_transform_raw": [0x300, -1, 0x300, 0x400], "native_transition_mode": 2, "native_entry_fade": 2, "native_exit_fade": 0xFF,
										  "source": "0x800EBAD4..0x800EBB24 request block 0x80078D08", "request_bytes": req}},
				"xa": {"descriptor_index": 0x47, "prepare": "SLES0x8001B714", "play": "SLES0x8001B864", "ready": "SLES0x8001AF94", "descriptor_ram": xa["intro"]["descriptor_ram"], "archive": "XA/PAL_37.XA",
					   "sector_start": xa["intro"]["sector_start"], "sector_end": xa["intro"]["sector_end"], "channel": xa["intro"]["channel"], "binding_status": "descriptor decoded; audio not exported", "answers": xa["answers"]},
				"new_ops": intro_NEW_OPS,
				"integration_notes": ["native_scene.gd _commands() rejects camera opcodes 0x18/0x19 (24/25, used 9 times) -> message_failed; add focus/orbit interpolation with the ease table", "native skips the frame increment on the tick a callback advances (ctx byte0 bit 0x08), so the next step sees tick 0; native_scene increments segment_tick after a program advance, which would skip tick-0 actions of steps 1,5,6,7,8 (callback-advanced predecessors 0,4,5,6,7)", "records span areas 0 and 1 and the scene performs three same-stage area changes; runtime spawns all records once into the starting area", "player controls 0x80..0x97 (and 1 with start_record 4) must exist in the player clip set for ST39", "opcode 0x11 targets actor slot 4 (ship 0x800f1b5c) at step 5"]}
	write_output(intro_OUT + "scene_05.json", json.dumps(scene, indent=1))
	write_output(intro_OUT + "scene_05_callbacks.json", json.dumps(contract, indent=1))
	write_output(intro_OUT + "scene_triggers.json", json.dumps({"stage": "ST39", "triggers": [{"entry_area": 0, "native_save_byte14": 0, "scene_id": 5, "source_function": "GAME0x800C0B0C", "source": "ST39T 0x800E72D8 starts scene 5 once per stage load (latch 0x80095E08) when +0x14 == 0"}]}, indent=1))
	print(json.dumps(cross)); print("ticks", ticks, "answers", e.answer_log)

intro_NEW_OPS = {
	"area_change": {"params": "stage, area, position_raw[3], facing_raw, fade_arrival, fade_exit, request_type(-1)", "semantics": "same-stage area change through request block 0x80078D08 (type -1, GAME0x800AEC4C); scene keeps running; player placed at position/facing", "sources": ["0x800EBBC4", "0x800EC118", "0x800EC1D8"]},
	"player_face / player_face_init": {"params": "channel eyes|mouth, sequence", "semantics": "SLES0x80041338/0x80041348 select a sequence in face controller ctx+0xB0 (tables 0x800F2018/0x800F21AC); SLES0x80041358 (called every update at 0x800EB9DC) writes the frame byte to player +0x1A0 (eyes) / +0x1A1 (mouth)", "sources": ["many, see segments"]},
	"actor_face / actor_face_init": {"params": "channel, sequence / table addresses", "semantics": "same face controller API on actor private +0x14C; actor class update (e.g. SLES0x8004152C for class 0x39) applies it", "sources": ["0x800E7BE0", "0x800E7F2C", "0x800E9230", "0x800E95DC", "0x800E897C"]},
	"player_render_flag": {"params": "set bool", "semantics": "0x8008C0A0 byte0 bit 0x02; gates SLES0x800231C8/0x80023438 player draw path (likely player visibility; unverified)", "sources": ["0x800EB850", "0x800EBC68", "0x800EBD90", "0x800EBDCC", "0x800EC1C4", "0x800EC3C4", "0x800EBB50"]},
	"sky_gradient": {"params": "horizon_raw (+0x16), param_18_raw (+0x18)", "semantics": "0x800966C0 sky gradient block; GAME0x800BEFF0 uses +0x16 as horizon base (default 0x240) when 0x800966C0 bit1 set; +0x18 consumer not found (unverified)", "sources": ["0x800EB840", "0x800EBBB8", "0x800EBC78", "0x800EBD88", "0x800EC1AC"]},
	"play_sound": {"params": "id", "semantics": "SLES0x80020160(id) non-positional sound cue (host.audio.play_sound)", "sources": ["0x800EBC80", "0x800EC1C0", "0x800EC3EC"]},
	"sound_latch / play_sound_if_latched": {"params": "value / id", "semantics": "ctx+0x0D remembers 0x29F is running; finish plays 0x2A0 when latched", "sources": ["0x800EBC8C", "0x800EC1CC", "0x800EC3FC", "0x800EBA80"]},
	"actor_state": {"params": "slot, record, field_0x0C", "semantics": "writes actor+0x0C=value,+0x0D=0 on the actor stored at ctx+0x2C+slot*4; the actor's class controller switches behaviour/control on it", "sources": ["0x800EBD40", "0x800EBEEC", "0x800EC0A8", "0x800EC548"]},
	"camera_shake": {"params": "magnitude_raw, decay_raw", "semantics": "SLES0x80016B1C(0,mag,decay) -> 0x8007D010+0xD8/+0xDC; focus Y -= (+0xD8>>8) in GAME0x800C24C0", "sources": ["0x800EBEF0"]},
	"camera_roll": {"params": "from_tick, through_tick, values_raw[]", "semantics": "0x80096D64 = camera ctx+0x14 = roll passed to SLES0x80015B6C", "sources": ["0x800EBFB8..0x800EBFF8"]},
	"vibration": {"params": "args_raw[2]", "semantics": "SLES0x80047180 pad actuator request (unverified byte meaning)", "sources": ["0x800EBF00", "0x800EBA54"]},
	"pool_clear": {"params": "mask, flags", "semantics": "SLES0x8003D658(mask,flags) clears pooled actors (as cinematics.py pool_clears)", "sources": ["0x800EBC50", "0x800EC3A0", "0x800EBA70"]},
	"close_windows": {"params": "-", "semantics": "SLES0x80048944(0) closes message windows", "sources": ["0x800EBA78"]},
	"player_axis_set / player_yaw_set / player_yaw_add": {"params": "axis, value_raw (expression of tick allowed) / yaw_raw / delta_raw", "semantics": "direct writes to player struct 0x8008C0A0 (+0x12 X integer, +0x2A yaw)", "sources": ["0x800EC60C", "0x800EC82C", "0x800ECA80", "0x800ECA84", "0x800ECB60"]},
	"play_xa / xa_fade_out / wait_xa_idle": {"params": "descriptor | descriptor_by_answer+select / speed / -", "semantics": "SLES0x8001B714 prepare, 0x8001B864 play, 0x8001AF94 ready, 0x8001BA44(speed) fade-out, 0x8001AFD0 idle", "sources": ["0x800EB8F0", "0x800EB918", "0x800EC718", "0x800EC754", "0x800EC57C", "0x800EBAAC", "0x800EC5A0", "0x800EC7A8", "0x800EBAC4"]},
	"skip_lock": {"params": "set bool", "semantics": "ctx 0x8007CEC0 byte0 bit 0x20; while set GAME0x800C10B4 ignores Start (scene skip)", "sources": ["0x800EC58C", "0x800EC848"]},
	"select_by_flags / jump_if / jump / label / wait_flag_clear / director_state": {"params": "see step 0:7", "semantics": "control flow of the step-7 question loop (ctx+7 jump table 0x800E7060)", "sources": ["0x800EC5D0..0x800EC7E8"]},
	"fade": {"params": "type, wait", "semantics": "SLES0x8001392C(type,0) screen transition; wait until 0x80078F01==0", "sources": ["0x800ECBBC", "0x800ECBE0"]},
	"actor_track": {"params": "keyframes[{step,tick,position_raw,yaw_raw}]", "semantics": "emulated actor position/yaw (16.16 raw units) of the unchanged class controllers, piecewise linear per native tick", "sources": ["class controllers"]},
	"effect_spawn": {"params": "args_raw", "semantics": "class 0x30 spawns SLES pool-8 effect actors (class 0x0F variant 4 attached at init 0x800E7674; variant 5 every 32 ticks via 0x800E7948 from position table a0, a1 bit7/low nibble params); effect visuals not decoded", "sources": ["0x800E7674", "0x800E7760", "0x800E7914"]},
	"camera opcodes 0x18/0x19": {"params": "header ease mode bits16..18, ticks low16; words[1..3] target", "semantics": "focus/orbit interpolation (see scene_05.json camera_interpolation)", "sources": ["GAME0x800C174C", "GAME0x800C182C", "GAME0x800DC7E0"]},
}

def export_intro_audio(cue):
	import audio
	from disc import Mode2Track, cue_layout
	xa = json.load(open(intro_OUT + "scene_05_callbacks.json", encoding="utf-8"))["xa"]; output = Path(intro_OUT) / "audio"; output.mkdir(parents=True, exist_ok=True); bin_path, start, frames = cue_layout(cue); reader = Mode2Track(bin_path, start, frames); entries = []
	try:
		for source in [{"id": xa["descriptor_index"], **{key: xa[key] for key in ("archive", "sector_start", "sector_end", "channel")}}] + [{key: answer[key] for key in ("id", "archive", "sector_start", "sector_end", "channel")} for answer in xa["answers"]]:
			extent, size = audio.archive_record(reader, source["archive"])
			if int(source["sector_end"]) >= (size + 2047) // 2048: raise ValueError("XA descriptor exceeds its ISO file")
			item = audio.export_entry(reader, extent, source, output); item["file"] = "res://assets/levels/ST39/audio/" + Path(item["file"]).name; entries.append(item)
	finally: reader.stream.close()
	manifest = {"source": "ST39T scene 5 XA descriptors 0x800ED9AC and 0x800EDA34", "entries": entries}; write_output(output / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest

# ---- fire_mission ----
# Export the ST1E Flutter fire mission (PAL): doors.json, fire_mission.json, fire_atlas.png and the native scene
# contracts for scene 0 (door) and scene 0xD (result), using DAT/ST1ET.BIN static tables, immediate-checked overlay
# constants and a unicorn emulation (tools/cinematics.py Emu) of the unchanged area handlers and scene callbacks.
fire_STAGE = "ST1E"; fire_BASE = 0x800E7000; fire_CTX = 0x8007CEC0; fire_PLAYER = 0x8008C0A0; ROOM = 0x8009C900; STATE = 0x8009BE08; fire_REQ = 0x80078D08; FLAGS = 0x80098538; NPC_TABLE = 0x800EE94C; fire_CAMERA = 0x80096D50
ROUTES = 0x800EEEA8; SPAWNS = {0: (0x800EF1FC, 4), 1: (0x800EF24C, 13), 2: (0x800EF364, 5)}; EXTRA_FIRE = 0x800EF350; SIZES = 0x800EF474; FRAMES = 0x800EF494
AREA_HANDLERS = 0x800EF1F0; fire_PER_FRAME = 0x800E744C; SCENE_D = 0x800ED7B8; SCENE_0 = 0x800ED1EC
fire_D = {}
def fire_rd(a, n): o = 0x30 + a - fire_BASE; return fire_D["ovl"][o:o + n]
def u8(a): return fire_rd(a, 1)[0]
def u16(a): return struct.unpack("<H", fire_rd(a, 2))[0]
def fire_s16(a): return struct.unpack("<h", fire_rd(a, 2))[0]
def fire_u32(a): return struct.unpack("<I", fire_rd(a, 4))[0]
def s8(v): return v - 256 if v & 128 else v
def fire_H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def fire_K(a, value, game=False):
	word = struct.unpack_from("<I", fire_D["game"], 0x30 + a - 0x800AD000)[0] if game else fire_u32(a)
	if word & 0xFFFF != value & 0xFFFF: raise ValueError(f"{'GAME' if game else 'ST1ET'} instruction {a:#x} immediate {word & 0xFFFF:#x} != {value & 0xFFFF:#x}")
	return value
def SH(a, value):
	if (fire_u32(a) >> 6) & 31 != value: raise ValueError(f"ST1ET instruction {a:#x} shift differs from {value}")
	return value
def fire_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; fire_D.update(root=Path(root), disc=disc, sles=(disc / "SLES_035.56").read_bytes(), game=(disc / "COMMON/GAME.BIN").read_bytes(), ovl=(disc / "DAT/ST1ET.BIN").read_bytes(), stage=(disc / "DAT/ST1E.BIN").read_bytes())
	if struct.unpack_from("<4I", fire_D["ovl"], 0)[0] != 1 or struct.unpack_from("<I", fire_D["ovl"], 12)[0] != fire_BASE: raise ValueError("unexpected ST1ET header")
	intro_SLES = fire_D["sles"]; intro_GAME = fire_D["game"]; intro_OVL = fire_D["ovl"]
def fire_record(a):
	b = fire_rd(a, 20); x, y, z, yaw = struct.unpack_from("<3hH", b, 12)
	return {"source_ram": fire_H(a), "bytes_hex": b.hex(), "flags": b[0], "slot": b[1], "pool": b[2], "pool_flags": b[3], "class": b[4], "variant": b[5], "size": b[6], "index": b[8], "contact_damage": b[9], "behaviour": b[10], "position_raw": [x, y, z], "yaw_raw": yaw}

# ------------------------------------------------------------------ doors
def export_doors(dat_dir, levels_dir, out_dir):
	if (fire_K(0x800E73E0, 0x800F) << 16) + fire_K(0x800E73EC, -0x1158) != ROUTES or fire_K(0x800E7404, -0x705C) != -0x705C: raise ValueError("ST1E route table binding differs")
	source = Path(levels_dir) / fire_STAGE; target = Path(out_dir) / fire_STAGE; target.mkdir(parents=True, exist_ok=True); copies = []
	if source.resolve() != target.resolve():
		for item in [source / "manifest.json", *sorted(source.glob("area_??.glb"))]:
			if not (target / item.name).exists(): shutil.copy2(item, target / item.name); copies.append(target / item.name)
	overlay = (Path(dat_dir) / (fire_STAGE + "T.BIN")).read_bytes(); original = world.native_area_tables
	world.native_area_tables = lambda data: {**original(data), "routes": [{"pointer_ram": ROUTES, "source_call": "0x800e73e8"}]} if data == overlay else original(data)
	try: world.export_routes(Path(dat_dir), Path(out_dir), [fire_STAGE])
	finally:
		world.native_area_tables = original
		for item in copies: item.unlink()
	path = target / "doors.json"; doors = json.loads(path.read_text(encoding="utf-8"))
	unlocks = {0x711: {"cleared_by": "area 0 handler when room fire count (0x8009C904) reaches 0", "source": "0x800E766C"}, 0x713: {"cleared_by": "area 1 handler when room fire count reaches 0", "source": "0x800E7878"}}
	for route in doors["area_transitions"]:
		route["locked_message"] = route["blocked_message"]; route["lock_unlocked_by"] = unlocks.get(route["lock_event"], {"cleared_by": None, "note": "ST1ET never clears this flag; the door stays shut (decoy or backward door)"})
		route["lock_set_by"] = {0: "0x800E7504..0x800E7528 (area 0 entry sets 0x711..0x715)", 1: "0x800E7704..0x800E7720 (area 1 entry sets 0x711..0x714)", 2: "0x800E7910..0x800E792C (area 2 entry sets 0x711..0x714)"}[route["source_area"]]
		route["message_bank"] = {"stage": fire_STAGE, "bank_ram": "0x8010C000", "consumer": "GAME0x800B89C4..0x800B8A10 shows record+4 through 0x800BE330 when GAME0x800B89B4 reports the door locked"}
	doors["source"]["area_route_pointer_ram"] = fire_H(ROUTES); doors["source"]["binding"] = "ST1ET 0x800E73E0/0x800E73EC load 0x800EEEA8, indexed by area byte 0x8009C7F9, stored to 0x80078FA4 at 0x800E7404 (delay slot of GAME0x800CF4A8 call; not matched by world.native_area_tables)"; doors["binding_status"] = "bound"
	doors["fire_mission_locks"] = {"global_lock": 0x710, "per_door": "0x710 + (door_id & 0x1F)", "runtime_clears": [0x711, 0x713], "never_cleared": [0x712, 0x714, 0x715]}
	world.write_output(path, json.dumps(doors, indent=2) + "\n", encoding="utf-8"); return doors

# ------------------------------------------------------------------ emulation
EXTRA_STUBS = ((0x800C0818, "spawn_table", 0, True, False), (0x800BE330, "conversation", 0, True, False), (0x8003B918, "overlay_show", 0, True, False), (0x8003B9C4, "overlay_hide", 0, True, False),
	(0x800C0B0C, "scene_start", 0, True, False), (0x800E7B20, "radio_message", 0, True, False), (0x80020984, "jingle", 0, True, False), (0x80043F70, "call_43F70", 0, True, False),
	(0x800CDD8C, "player_busy", 0, False, False), (0x800203F4, "sound_3d", 0, True, False), (0x800C10B4, "skip_check", 0, False, False), (0x80042704, "hitbox", 0, True, False),
	(0x800B1228, "cell_lookup", 0x801F0000, False, False), (0x80038EF4, "placement_visibility", 0, True, False), (0x800B1864, "floor_probe", 0, False, False), (0x800B3564, "floor_snap", 0, False, False),
	(0x800CD084, "player_move", 0, True, False), (0x8003E800, "alloc_actor", 0, True, False), (0x8003E820, "alloc_actor", 0, True, False), (0x8003E918, "alloc_actor", 0, True, False), (0x800411C4, "actor_shape_setup", 0, True, False))
class fire_Emu(intro_Emu):
	def __init__(self):
		super().__init__(()); self.room = False
		for address, name, value, recorded, run in EXTRA_STUBS:
			self.stubs[address] = (name, value, recorded, run); self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=address, end=address)
		for pointer, table in ((0x80078FA8, NPC_TABLE), (0x80078DE0, 0x800EEAE8), (0x80078CFC, 0x800EEBE4), (0x80078DCC, 0x800EEBE8), (0x80078EA0, 0x800EEC34), (0x80078E7C, 0x800EEEB4), (0x80078FB4, 0x800EE2D0)): self.w32(pointer, table)
		self.w16(fire_PLAYER + 0x70, 0x30); self.w16(fire_PLAYER + 0x72, 0x30)
	def w16(self, a, v): self.cpu.mem_write(a & 0x1FFFFFFF, struct.pack("<H", v & 0xFFFF))
	def flag(self, flag, on=True):
		a = FLAGS + (flag >> 3); self.w8(a, self.u8(a) | (1 << (flag & 7)) if on else self.u8(a) & ~(1 << (flag & 7)))
	def test(self, flag): return bool(self.u8(FLAGS + (flag >> 3)) & (1 << (flag & 7)))
	def record(self, kind, **kw):
		super().record(kind, **kw); self.events[-1]["state"] = self.u8(fire_CTX + 4)
		if self.room: self.events[-1]["room"] = {"fires": self.u8(ROOM + 4), "extinguished": self.u8(ROOM + 5), "timers": [self.u16(ROOM + o) for o in (0xA, 0xC, 0xE)], "idle": self.u16(ROOM + 0x10), "area_state": self.u8(STATE)}
	def stub_hook(self, uc, address, size, data):
		name = self.stubs[address][0]; a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
		if name == "message": self.record("message", window=a[0], bank=fire_H(a[1]), index=a[2], caller=fire_H(ra - 8)); return self._ret(uc, 0, ra)
		if name == "conversation": self.record("conversation", args=[s32(x) for x in a], index=self.u32(self.r(29) + 0x10), caller=fire_H(ra - 8)); return self._ret(uc, 0, ra)
		if name == "alloc_actor":
			pointer = self.free.pop(0); uc.mem_write(pointer & 0x1FFFFFFF, bytes(0x400)); self.record("alloc", function=fire_H(address), ptr=fire_H(pointer), caller=fire_H(ra - 8)); return self._ret(uc, pointer, ra)
		return super().stub_hook(uc, address, size, data)
	def write_data(self, index, value):
		super().write_data(index, value)
		if index == 30: v = value & 0xFFFFFFFF; v = v ^ 0xFFFFFFFF if v & 0x80000000 else v; self.data[31] = 32 - v.bit_length()
	def operation(self, word):
		if word & 63 != 0x28: return super().operation(word)
		shift = 12 if word & (1 << 19) else 0; lower = 0 if word & 1024 else -32768
		for row in range(3): value = (intro_s16(self.data[9 + row]) ** 2) >> shift; self.data[25 + row] = value & 0xFFFFFFFF; self.data[9 + row] = max(lower, min(32767, value))
		self.control[31] = 0
	def init_flags(self, flags):
		for flag in flags: self.flag(flag)

def emulate_area(area, clear_at=None, trigger_at=None, ticks=6000):
	e = fire_Emu(); e.room = True; e.w8(0x8009C7F9, area); e.w8(STATE, 0); e.cpu.mem_write(ROOM & 0x1FFFFFFF, bytes(0x3C))
	for tick in range(ticks):
		e.call(fire_PER_FRAME)
		if area == 2 and e.u8(STATE) == 1 and e.test(0x681): e.flag(0x681, False); e.record("simulated_message_end", flag=0x681, note="Data's message 0x03 closes (class 0x1D actor not emulated)")
		if trigger_at is not None and tick == trigger_at: e.w16(ROOM + 6, 1); e.record("simulated_trigger", field="room+6", note="fire with +0xE bit1 extinguished")
		if clear_at is not None and tick == clear_at: e.w8(ROOM + 4, 0); e.record("simulated_room_clear", field="room+4")
		if any(x["kind"] == "scene_start" for x in e.events): break
	return e, tick

def fire_math():
	e = fire_Emu(); actor = 0x80190000; rows = []
	for size in range(4):
		for distance in (0x40, 0x80, 0xC0, 0x100, 0x140):
			for hit in (0x40010, 0x42010, 0x2010, 0x10000, 0):
				e.cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x100)); e.w8(actor + 6, size); e.w32(actor + 0x10, 0); e.w32(actor + 0x14, 0); e.w32(actor + 0x18, 0); e.w32(fire_PLAYER + 0x10, distance << 16); e.w32(fire_PLAYER + 0x14, 0); e.w32(fire_PLAYER + 0x18, 0)
				maximum = u16(SIZES + size * 8 + 4); e.w32(actor + 0x74, hit); e.w32(actor + 0x7C, 0x700); e.w32(actor + 0x80, maximum); result = s32(e.call(0x800EA600, (actor,)))
				rows.append({"size": size, "player_distance_raw": distance, "hit_word": fire_H(hit), "strength_before": 0x700, "result": result, "strength_after": s32(e.u32(actor + 0x7C))})
	boxes = []
	for size in range(4):
		for strength in (0x200, 0x800, 0x1000, 0x1C00):
			e.events.clear(); e.cpu.mem_write(actor & 0x1FFFFFFF, bytes(0x100)); e.w8(actor + 2, 0x60); e.w8(actor + 6, size); e.w8(actor + 0xD, 8); e.w32(actor + 0x10, 0x100 << 16); e.w32(actor + 0x14, 0); e.w32(actor + 0x18, 0x200 << 16); e.w32(actor + 0x7C, strength); e.call(0x800EA6E4, (actor,))
			hit = [x for x in e.events if x["kind"] == "hitbox"][0]; center = [struct.unpack("<h", bytes(e.cpu.mem_read((0x1F800120 + k * 2) & 0x1FFFFFFF, 2)))[0] for k in range(3)]
			boxes.append({"size": size, "strength": strength, "center_raw": center, "a2": fire_H(hit["args"][2]), "a3": fire_H(hit["args"][3]), "radius_raw": (hit["args"][2] & 0xFFFF) * 4})
	return rows, boxes

def formula(hit, distance, strength=0x700, maximum=0x800):
	if not hit & 0x42000: return strength
	damage = (hit & 0xFFF) << 5
	if hit & 0x2000: d = 0x100 if distance > 0x100 else 0x80 if distance < 0x80 else distance; damage += ((((0x100 - d) * 13) << 6 >> 7) + 0x3C0) >> 3
	if not damage: return strength
	return 0 if strength - damage <= 0x200 else strength - damage

def actor_update(e, tracks, w):
	for ptr, slot in list(e.actors.items()):
		if ptr not in e.actors: continue
		function = e.u32(e.u32(NPC_TABLE + e.u8(ptr + 4) * 4) + e.u8(ptr + 5) * 4); e.cur = slot; e.call(function, (ptr,))
		tracks.setdefault(slot, []).append((0, w["step"], w["frame"], s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, 0))
	e.cur = None

def player_row(e, w): return (0, w["step"], w["frame"], s32(e.u32(fire_PLAYER + 0x10)), s32(e.u32(fire_PLAYER + 0x14)), s32(e.u32(fire_PLAYER + 0x18)), e.u16(fire_PLAYER + 0x2A) & 4095, 0)

def emulate_result(success):
	e = fire_Emu(); e.cpu.mem_write(ROOM & 0x1FFFFFFF, bytes(0x3C)); e.w8(0x8009C7F9, 2)
	if success: e.flag(0x129); e.w16(ROOM + 0xA, 0x400); e.w16(ROOM + 0xC, 0x400); e.w16(ROOM + 0xE, 0x400); e.w8(ROOM + 5, 23)
	else: e.w16(ROOM + 0xA, 0x708); e.w8(ROOM + 5, 4)
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); slot = e.u8(rec + 1); e.actors[ptr] = slot; e.record("spawn", slot=slot, record=fire_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(fire_CTX & 0x1FFFFFFF, bytes(0xC0)); tracks = {}; requests = []; skip = []; previous = None
	for tick in range(6000):
		state = e.u8(fire_CTX + 4)
		if state > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.cur = None; e.call(SCENE_D, (fire_CTX,)); w = e.where()
		lock = bool(e.u8(fire_CTX) & 0x20)
		if lock != previous: e.record("skip_lock", set=lock); previous = lock
		if e.u8(fire_REQ):
			raw = bytes(e.cpu.mem_read(fire_REQ & 0x1FFFFFFF, 0x1A)); e.record("request_block", bytes=raw.hex()); requests.append(raw); e.w8(fire_REQ, 0)
		actor_update(e, tracks, w); tracks.setdefault("player", []).append(player_row(e, w))
	return e, tracks, requests, tick

def emulate_door(route):
	e = fire_Emu(); raw = bytes.fromhex(route["bytes_hex"]); e.cpu.mem_write(fire_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(0x8009C7F9, route["source_area"])
	block = bytearray(0x1A); block[0] = 1; block[2] = raw[0]; block[3] = raw[1]; block[4] = raw[6]; block[5] = raw[7]; block[7] = raw[2]; block[8:0x18] = raw[8:24]; e.cpu.mem_write(fire_REQ & 0x1FFFFFFF, bytes(block))
	x, y, z, yaw = route["source_transform_raw"]; e.w32(fire_PLAYER + 0x10, x << 16); e.w32(fire_PLAYER + 0x14, y << 16); e.w32(fire_PLAYER + 0x18, z << 16); e.w16(fire_PLAYER + 0x2A, yaw); e.flag(0x700)
	door = None; tracks = {"player": []}; door_rows = []; camera = None
	for tick in range(400):
		state = e.u8(fire_CTX + 4)
		if state > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.call(SCENE_0, (fire_CTX,)); w = e.where()
		if camera is None and e.u8(fire_CTX + 4) == 1:
			door = e.u32(fire_CTX + 0x2C); camera = {"focus_raw": [s32(e.u32(fire_CAMERA + o)) / 65536 for o in (8, 0xC, 0x10)], "orbit_raw": [s32(e.u32(fire_CAMERA + o)) / 65536 for o in (0x58, 0x5C, 0x60)], "player_after_setup_raw": [s32(e.u32(fire_PLAYER + o)) / 65536 for o in (0x10, 0x14, 0x18)] + [e.u16(fire_PLAYER + 0x2A)], "door_actor": {"class": e.u8(door + 4), "variant_byte6": e.u8(door + 6), "position_raw": [s32(e.u32(door + o)) >> 16 for o in (0x10, 0x14, 0x18)]}}
		if door: door_rows.append({"step": w["step"], "tick": w["frame"] - 1, "byte8": e.u8(door + 8), "byte9": e.u8(door + 9), "half4A": struct.unpack("<h", struct.pack("<H", e.u16(door + 0x4A)))[0], "half4E": struct.unpack("<h", struct.pack("<H", e.u16(door + 0x4E)))[0]})
		if e.u8(fire_CTX + 4) == 2 and e.u8(fire_REQ) == 1: e.w8(fire_REQ, 2); e.record("simulated_request_ready", value=2)
		if e.u8(fire_REQ) == 3: e.record("request_block", bytes=bytes(e.cpu.mem_read(fire_REQ & 0x1FFFFFFF, 0x1A)).hex()); e.w8(fire_REQ, 0)
		tracks["player"].append(player_row(e, w))
	return e, tracks, door_rows, camera, tick

SCENE_STUBS = ((0x800D97EC, "stage_setup", 0, False, False), (0x8001D7C4, "stage_audio", 0, False, False), (0x80041724, "face_eyes_frame", 0, True, True), (0x8004173C, "face_mouth_frame", 0, True, True), (0x8001B2D8, "file_load", 0, True, False), (0x80023040, "player_bank", 0, True, False),
	(0x800C0EA8, "advance", 0, True, True), (0x80041358, "face_tick", 0, False, False), (0x8003DFC8, "resource_ready", 1, False, False), (0x80041204, "face_dims", 0, False, False))
def stage_emulator(stage_init, gte_start, code_end, stubs=(), area_byte=0x8009C7F9):
	class StageEmu(fire_Emu):
		def __init__(self):
			super().__init__(); self.phase_events = True; self.pools = {}; self.requests = []
			code = fire_D["ovl"][0x30:]
			for off in range(gte_start - fire_BASE, code_end - fire_BASE, 4):
				w = struct.unpack_from("<I", code, off)[0]; op = w >> 26
				if op == 18 and ((w >> 25) & 1 or (w >> 21) & 31 in (0, 2, 4, 6)) or op in (50, 58): self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.gte, begin=fire_BASE + off, end=fire_BASE + off)
			hooked = set(self.stubs)
			for address in [a for a in self.stubs if fire_BASE <= a < 0x80180000]: del self.stubs[address]
			for address, name, value, recorded, run in SCENE_STUBS + tuple(stubs):
				if address not in hooked: self.cpu.hook_add(unicorn.UC_HOOK_CODE, self.stub_hook, begin=address, end=address); hooked.add(address)
				self.stubs[address] = (name, value, recorded, run)
			for address in (0x8003E5B0, 0x8003E800, 0x8003E820, 0x8003E918, 0x8003EA4C, 0x8003EB7C, 0x8003D658): self.stubs[address] = (self.stubs.get(address, ("native",))[0], 0, True, True)
			for pointer in (0x80078FA8, 0x80078DE0, 0x80078CFC, 0x80078DCC, 0x80078EA0, 0x80078E7C, 0x80078FB4): self.w32(pointer, 0)
			self.call(stage_init)
		def where(self): return dict(super().where(), phase=self.u8(fire_CTX + 2))
		def call(self, function, args=()):
			self.w32(0x1F80004C, 0x801C0000); self.w32(0x1F800050, 0x801D0000); return super().call(function, args)
		def stub_hook(self, uc, address, size, data):
			if address not in self.stubs: return
			name = self.stubs[address][0]; a = [self.r(4), self.r(5), self.r(6), self.r(7)]; ra = self.r(31)
			if name == "advance" and self.u8(fire_REQ): self.request()
			if name == "despawn": self.record("despawn", record=self.actors.pop(a[0], None), caller=fire_H(ra - 8)); return
			if name == "alloc_actor": self.record("alloc", function=fire_H(address), caller=fire_H(ra - 8)); return
			return super().stub_hook(uc, address, size, data)
		def request(self):
			raw = bytes(self.cpu.mem_read(fire_REQ & 0x1FFFFFFF, 0x1A)); self.record("request_block", bytes=raw.hex()); self.requests.append(raw)
			if raw[0] == 0xFF: self.w8(area_byte, raw[5])
			self.w8(fire_REQ, 0)
	return StageEmu
def run_scene(e, handler, watch, ticks=20000):
	tracks = {}; previous = {kind: initial for kind, (initial, _) in watch.items()}
	for tick in range(ticks):
		if e.u8(fire_CTX + 4) > 2 or any(x["kind"] == "restore_C0F58" for x in e.events): break
		e.cur = None; e.call(handler, (fire_CTX,)); w = e.where()
		for kind, (_, read) in watch.items():
			value = read(e)
			if value != previous[kind]: e.record(kind, value=value, offset_raw=[e.u16(fire_CTX + 0x10), e.u16(fire_CTX + 0x12)]); previous[kind] = value
		if e.u8(fire_REQ): e.request()
		for ptr, rec in list(e.actors.items()):
			if ptr not in e.actors: continue
			if not e.u8(ptr) & e.u8(ptr + 1) & 1: e.actors.pop(ptr); e.record("released", record=rec); continue
			flags = e.u8(ptr + 3)
			if e.pools[ptr][2] != 0x20 and (flags & 4 or not flags & 8): continue
			e.cur = rec; e.call(e.u32(e.u32(e.u32(0x80078FA8 if e.pools[ptr][2] == 0x20 else 0x80078DE0) + e.u8(ptr + 4) * 4) + e.u8(ptr + 5) * 4), (ptr,))
			tracks.setdefault(rec, []).append((0, w["step"], w["frame"], s32(e.u32(ptr + 0x10)), s32(e.u32(ptr + 0x14)), s32(e.u32(ptr + 0x18)), e.u16(ptr + 0x2A) & 4095, w["phase"]))
		e.cur = None; tracks.setdefault("player", []).append(player_row(e, w) + ())
	return tracks, tick

# ------------------------------------------------------------------ sprites
def vram():
	memory = bytearray(1024 * 512 * 2); uploads = []
	for name in ("COMMON/GAME.BIN", "COMMON/PL00T.BIN", "DAT/ST1ET.BIN"): uploads.extend({k: v for k, v in item.items() if k in ("file", "section_offset", "palette_rect", "image_rect")} for item in world.texture_uploads((fire_D["disc"] / name).read_bytes(), memory, name))
	return memory, uploads
def fire_frames(size):
	out = []; a = FRAMES + size * 0x80
	for index in range(16):
		u, v, w, h, ticks, end = fire_rd(a + index * 8, 6); out.append({"index": index, "source_ram": fire_H(a + index * 8), "u": u, "v": v, "w": w, "h": h, "ticks": ticks, "last": end == 0xFF})
		if end == 0xFF: break
	return out
EFFECTS = {1: {"name": "steam_puff", "anim": 0x800F03C0, "page": 0x800F0398, "count": 5, "size": 0x800F0780, "rise": 0x800F078C, "init": "0x800EC2D0", "update": "0x800EC360"}, 2: {"name": "explosion_flame", "anim": 0x800F07A0, "page": 0x800F0798, "count": 1, "size": 0x800F0860, "init": "0x800EC3CC", "update": "0x800EC464"},
	4: {"name": "explosion_debris", "anim": 0x800F087C, "page": 0x800F0864, "count": 3, "size": 0x800F0ABC, "init": "0x800EC69C", "update": "0x800EC760"}, 5: {"name": "ember", "anim": 0x800F0ACC, "page": 0x800F0AC4, "count": 1, "size": 0x800F0B8C, "init": "0x800EC8A8", "update": "0x800EC938"}, 6: {"name": "data_flame", "anim": 0x800F0ACC, "page": 0x800F0AC4, "count": 1, "init": "0x800ECC7C", "update": "0x800ECCF0"}}
def effect_frames(spec, sub):
	out = []; a = spec["anim"] + sub * 0xC0
	for index in range(16):
		b = fire_rd(a + index * 12, 12); command = struct.unpack_from("<I", b)[0]
		out.append({"index": index, "source_ram": fire_H(a + index * 12), "command": fire_H(command), "rgb": [command & 255, (command >> 8) & 255, (command >> 16) & 255], "u0": b[4], "v0": b[5], "u1": b[6], "v1": b[7], "ticks": b[8], "next": {0xFF: "die", 0x80: "loop"}.get(b[9], "next"), "next_raw": b[9], "size_delta_per_tick": s8(b[10]), "rotation_delta_per_tick": s8(b[11])})
		if b[9] in (0xFF, 0x80): break
	return out
class Atlas:
	def __init__(self, memory): self.memory = memory; self.pages = {}; self.items = []; self.keys = {}; self.x = self.y = self.row = 0; self.width = 256
	def add(self, tpage, clut, u, v, w, h):
		key = (tpage, clut, u, v, w, h)
		if key in self.keys: return self.keys[key]
		if self.x + w > self.width: self.x = 0; self.y += self.row; self.row = 0
		self.items.append({"id": len(self.items), "uv": [self.x, self.y, w, h], "tpage": fire_H(tpage)[-4:], "clut": fire_H(clut)[-4:], "source_uv": [u, v, w, h]}); self.keys[key] = len(self.items) - 1; self.x += w; self.row = max(self.row, h)
		return self.keys[key]
	def save(self, path):
		height = self.y + self.row; height += -height % 4; pixels = bytearray(self.width * height * 4)
		for item in self.items:
			tpage, clut = int(item["tpage"], 16), int(item["clut"], 16)
			if (tpage, clut) not in self.pages: self.pages[(tpage, clut)] = ui.decode_page(self.memory, tpage, clut, True)
			page = self.pages[(tpage, clut)]; x, y, w, h = item["uv"]; u, v = item["source_uv"][:2]
			for row in range(h):
				start = ((v + row) * 256 + u) * 4; pixels[((y + row) * self.width + x) * 4:((y + row) * self.width + x + w) * 4] = page[start:start + w * 4]
		world.write_output(path, world.png(self.width, height, bytes(pixels))); return [self.width, height]

# ------------------------------------------------------------------ scene contract helpers
fire_OPS = {"screen_transition": lambda x: {"op": "fade", "type": x["args"][0]}, "pool_clear": lambda x: {"op": "pool_clear", "mask": x["args"][0], "flags": x["args"][1]}, "sound": lambda x: {"op": "play_sound", "id": x["args"][0]},
	"player_control": lambda x: {"op": "player_control", "control": x["args"][0], "start_record": x["args"][1]}, "xa_prepare": lambda x: {"op": "music_prepare", "id": x["args"][0] & 0xFFFF, "unverified": True, "note": "SLES0x8001B714(0xFF01): XA/music descriptor 0xFF01 (music stop/hold); no XA asset bound"},
	"xa_play": lambda x: {"op": "music_play", "id": x["args"][0] & 0xFFFF, "unverified": True, "note": "SLES0x8001B864(0xFF01) after the result message"}, "overlay_show": lambda x: {"op": "result_banner", "args_raw": x["args"][:3], "unverified": True, "note": "SLES0x8003B918(0x44,0x30,2): screen overlay/banner (style table 0x8006B324)"},
	"overlay_hide": lambda x: {"op": "result_banner_hide"}, "jingle": lambda x: {"op": "jingle", "args_raw": x["args"][:3], "unverified": True, "note": "SLES0x80020984(0xF,0x333,0)"}, "call_43F70": lambda x: {"op": "native_call", "function": "SLES0x80043F70", "args_raw": x["args"][:1], "unverified": True},
	"skip_lock": lambda x: {"op": "skip_lock", "set": x["set"]}, "flag_set": lambda x: {"op": "event_set", "id": x["args"][0]}, "flag_clear": lambda x: {"op": "event_clear", "id": x["args"][0]}, "close_windows": lambda x: {"op": "close_windows"}, "vibration": lambda x: {"op": "vibration", "args_raw": [a & 0xFFFFFFFF for a in x["args"][:2]]},
	"message": lambda x: {"op": "message", "index": x["index"]}, "advance": lambda x: {"op": "advance"}, "xa_fade_out": lambda x: {"op": "xa_fade_out", "speed": x["args"][0]}}
def fire_request(raw):
	x, y, z, facing = struct.unpack_from("<3hH", raw, 0x10); return {"type": struct.unpack("b", raw[:1])[0], "stage": "ST%02X" % raw[4], "area": raw[5], "position_raw": [x, y, z], "facing_raw": facing, "fade_arrival": raw[0x18], "fade_exit": raw[0x19], "bytes": raw.hex()}
def fire_programs(events, fire_timeline, ops=fire_OPS):
	segments = {"%d:%d" % (t["phase"], t["step"]): {"source": t["callback"], "program": [], "emulated_events": []} for t in fire_timeline}; init = []; finish = []; last = {}
	for x in events:
		op = None
		if x["kind"] in ops: op = dict(ops[x["kind"]](x), source=x.get("caller", "emulated state change"))
		elif x["kind"] == "request_block":
			r = fire_request(bytes.fromhex(x["bytes"]))
			op = {"op": "area_change", "stage": r["stage"], "area": r["area"], "position_raw": r["position_raw"], "facing_raw": r["facing_raw"], "fade_arrival": r["fade_arrival"], "fade_exit": r["fade_exit"], "request_type": -1, "source": "request block 0x80078D08 (type -1)"} if r["type"] == -1 else {"op": "stage_request", **r}
		if op is None: continue
		if op["op"] == "event_set" and op["id"] == 0x12A: op = {"op": "event_set_conditional", "id": 0x12A, "condition": "success: room timers +0xA + +0xC + +0xE < 0xD49; failure: room+5 >= 0x12", "source": op["source"], "note": "gameplay must evaluate; native_scene.gd ignores this op"}
		if x["state"] == 0: init.append(op); continue
		if x["state"] == 2: finish.append(op); continue
		key = "%d:%d" % (x.get("phase", 0), x["step"]); segment = segments[key]; gap = x["frame"] - last.get(key, 0)
		if gap > 1 or (gap == 1 and op["op"] not in ("message", "fade")): segment["program"].append({"op": "delay", "ticks": gap, "source": "emulated substate counter"})
		last[key] = x["frame"]; segment["program"].append(op); segment["emulated_events"].append({"kind": x["kind"], "tick": x["frame"]})
	for index, t in enumerate(fire_timeline):
		segment = segments["%d:%d" % (t["phase"], t["step"])]
		if t["duration"] < 0 and (not segment["program"] or segment["program"][-1]["op"] != "advance"): segment["program"].append({"op": "advance", "source": "GAME0x800C0EA8(1) (callback-advanced step, duration -1)"})
		program = segment["program"]
		if index + 1 < len(fire_timeline) and len(program) >= 2 and program[-1]["op"] == "advance" and program[-2]["op"] == "fade": program[-2]["wait"] = False; program[-2]["wait_source"] = "callback advances in the same tick it starts the fade (native does not wait)"
	return segments, init, finish
def fire_actor_entry(rec, area, manifest, runtime):
	b = bytes.fromhex(rec["bytes_hex"]); model = manifest["models"][0]; exp = model["export"]; x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	if model["flags"] >> 8 != rec["class"]: raise ValueError("ST1E_04800 model 0 is not class %#x" % rec["class"])
	return {"source_ram": rec["source_ram"], "slot": rec["slot"], "class_note": "Data (class 0x63, NPC pool 0x20; scene controller ST1ET 0x800E9958 = class cell 0x800EE944 variant 1)",
		"entry": {"stage": fire_STAGE, "area": area, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": 0, "model_file": runtime},
		"model": {"file": runtime, "source_archive": "DAT/ST1E.BIN section 0x4800 (ST1E_04800)", "source_model_index": 0, "source_flags": model["flags"], "class_from_flags": model["flags"] >> 8, **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp}, "model_file": runtime, "model_index": 0}}
def fire_controllers(e, tracks, records):
	out = {}
	for slot, rows in tracks.items():
		if slot == "player": continue
		events = [x for x in e.events if x.get("actor_slot") == slot]; controls = [x for x in events if x["kind"] == "actor_control"]; startup = controls[0] if controls else None
		items = [dict({"op": "control", "control": x["args"][1], "start_record": x["args"][2], "native": "SLES0x8003F4BC via %s" % x["caller"]}, step=x["step"], tick=x["frame"]) for x in controls if x is not startup]
		items += [dict({"op": "actor_face", "channel": "eyes" if x["kind"] == "face_eyes" else "mouth", "sequence": x["args"][1], "native": x["caller"]}, step=x["step"], tick=x["frame"]) for x in events if x["kind"] in ("face_eyes", "face_mouth")]
		profile = {"source": "ST1ET 0x800E9958 (Data class 0x63 variant 1), emulated once per native tick after the scene update; render helpers stubbed", "record": records[slot], "events": items, "track": {"op": "actor_track", "interpolation": "linear between keyframes in native ticks", "keyframes": compress(rows)}}
		if startup: profile["startup_control"] = startup["args"][1]; profile["startup_start_record"] = startup["args"][2]
		out[str(slot)] = profile
	return out
def fire_commands(address):
	out = []; a = address
	while True:
		w = fire_u32(a); op = w >> 24; size = 16 if 0x10 <= op <= 0x1A else 8 if op in (0x40, 0x41) else 20 if op == 0x42 else 4; words = list(struct.unpack("<%dI" % (size // 4), fire_rd(a, size))); item = {"source_ram": fire_H(a), "opcode": op, "words": words}
		if op in (0x40, 0x41): item["actor_record"] = {"source_ram": fire_H(words[1]), "bytes": fire_rd(words[1], 20).hex()}
		if op == 0x42: item["player_transform"] = {"position_raw": [s32(x) / 65536 for x in words[1:4]], "yaw_raw": words[4] & 0xFFFF, "native": "GAME0x800C1A58: player(0x8008C0A0)+0x10/+0x14/+0x18 = words[1..3], +0x2A = halfword +0x10"}
		out.append(item); a += size
		if op == 0xFF: break
	return out
def fire_timeline(address):
	out = []; a = address
	while True:
		p, s, d, cb = struct.unpack("<BBhI", fire_rd(a, 8))
		if p == 255: break
		out.append({"phase": p, "step": s, "duration": d, "callback": "0x%x" % cb, "source_ram": "0x%x" % a}); a += 8
	return out

def build_result(success, manifest, runtime, out):
	camera_address = fire_u32(0x800F0D2C + (0 if success else 4)); timeline_address = fire_u32(0x800F0D64 + (0 if success else 4))
	if (camera_address, timeline_address) != ((0x800F0C5C, 0x800F0D34) if success else (0x800F0CC4, 0x800F0D4C)): raise ValueError("scene 0xD camera/timeline tables differ")
	e, tracks, requests, ticks = emulate_result(success); cmds = fire_commands(camera_address); tl = fire_timeline(timeline_address)
	spawned = [c["actor_record"]["source_ram"] for c in cmds if c["opcode"] == 0x40]; recs = [fire_actor_entry(fire_record(int(a, 16)), 2, manifest, runtime) for a in spawned]
	segments, init, finish = fire_programs(e.events, tl); stage_request = fire_request(requests[-1]); player = next(c["player_transform"] for c in cmds if c["opcode"] == 0x42)
	name = "success" if success else "failure"; base = "scene_0d_%s" % name
	scene = {"stage": fire_STAGE, "area": 2, "scene_id": 0xD, "branch": name, "native_tick_hz": 25, "callback_contract_file": base + "_callbacks.json", "commands": cmds, "timeline": tl, "actors": recs,
		"player": {"camera_opcode_0x42_used": True, "transform_raw": player, "track": compress(tracks["player"])}, "face_tables": {},
		"emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "events": [{k: v for k, v in x.items() if k not in ("sub6",)} for x in e.events if x["kind"] not in ("render", "actor_control")]},
		"source": {"overlay": "DAT/ST1ET.BIN", "handler": "0x800ED7B8 (GAME table 0x800DC490[0xD])", "phase_table": "0x800F0D6C {0x800ED800 init, 0x800ED9DC update, 0x800EDA6C finish}", "camera_table": "0x800F0D2C", "timeline_table": "0x800F0D64", "command_pointer": fire_H(camera_address), "timeline_pointer": fire_H(timeline_address),
			"branch_select": "0x800ED88C: flag 0x129 set -> ctx+7=0 (success) else ctx+7=1 (failure)", "callback_tables": {"success_step1": "0x800E71A4", "failure_step0": "0x800E71BC", "failure_step1": "0x800E71DC"}}}
	if not success: scene = {"branches": {str(area): dict(scene, area=area, area_note="failure starts in the room where the timer expired or HP reached 0; step 0 moves to area 2") for area in (0, 1, 2)}}
	hp = fire_K(0x800EDB74, 0x72) == 0x72 and fire_K(0x800EDB84, 0x70) == 0x70
	contract = {"schema": 1, "stage": fire_STAGE, "scene_id": 0xD, "branch": name, "source": "ST1ET scene 0xD handler 0x800ED7B8; timeline callbacks %s" % ", ".join(t["callback"] for t in tl),
		"tick_basis": "tick = native ctx+0x28 of the step; program delays are the emulated substate counters (fades, messages and XA reported idle immediately in emulation; the native callbacks wait for message/fade/XA idle before the next substate)",
		"initialization": {"player_position_raw": [round(v) for v in player["position_raw"]], "player_yaw_raw": player["yaw_raw"], "player_note": "camera opcode 0x42 at step 1 tick 0 sets the player transform; until then the player keeps the gameplay transform behind fade 0x11", "spawn_records": [], "init_ops": init,
			"phase0": {"source": "0x800ED800", "ops": ["GAME0x800C1148", "event_set 0x703 (0x800ED86C)", "SLES0x80048944(1)", "ctx byte0 |= 0x20 (skip locked)", "flag 0x129 -> success; else failure", "wait GAME0x800CDD8C()==0, then GAME0x800CDE5C(0,0,1)", "success waits 0x60 ticks (0x800ED934..0x800ED940), failure starts at once", "clear player +0xF0/+0xF4/+0x1A0/+0x1A1/+0x38..+0x44", "GAME0x800C0C5C(camera, timeline)"],
				"fast_flag": {"flag": 0x12A, "success_condition": "timers +0xA + +0xC + +0xE < 0x%X" % fire_K(0x800ED8B4, 0xD49), "failure_condition": "room+5 (fires extinguished) >= 0x%X" % fire_K(0x800ED8D4, 0x12), "source": "0x800ED8A0..0x800ED8E4"}}},
		"segments": segments, "actor_controllers": fire_controllers(e, tracks, {r["slot"]: r["source_ram"] for r in recs}),
		"finish": {"source": "ST1ET 0x800EDA6C", "fade_exit": 0x12, "fade_exit_source": "issued by the last timeline step", "ops": finish + [{"op": "hp_refill", "native": "player+0x70 = player+0x72", "source": "0x800EDB74..0x800EDB84", "verified": hp}],
			"skip_path": {"source": "0x800ED9DC..0x800EDA50", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x80048944(1); SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800EDB44..0x800EDB80 request block 0x80078D08", "request_bytes": stage_request["bytes"]}},
		"new_ops": fire_NEW_OPS, "integration_notes": ["camera opcode 0x42 (66) is used at step 1 tick 0: native_scene.gd _commands() treats it as unknown and fails the scene; add 'player transform set' (position words[1..3] 16.16, yaw = low half of words[4])", "fade ops in steps that the native code does not wait for (fade 1 / fade 2 reveals) block in native_scene.gd; harmless but adds the fade time", "player controls %s must exist in the ST1E player clip set" % sorted({op["control"] for s in segments.values() for op in s["program"] if op["op"] == "player_control"}), "unknown ops (music_prepare, music_play, result_banner, jingle, native_call, close_windows, event_clear) are ignored by native_scene.gd _action()"]}
	world.write_output(out / (base + ".json"), json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / (base + "_callbacks.json"), json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"file": base + ".json", "callbacks": base + "_callbacks.json", "ticks": ticks, "messages": [x["index"] for x in e.events if x["kind"] == "message"], "transition": stage_request, "flags_set": [x["args"][0] for x in e.events if x["kind"] == "flag_set"]}

def build_door(doors, out):
	runs = []; tl = fire_timeline(0x800F0BB8)
	if fire_u32(0x800F0BB4) != 0xFFFFFFFF or [fire_u32(0x800F0C20 + i * 4) for i in range(3)] != [0x800ED228, 0x800ED510, 0x800ED57C]: raise ValueError("scene 0 tables differ")
	for route in doors["area_transitions"]:
		e, tracks, door_rows, camera, ticks = emulate_door(route); segments, init, finish = fire_programs(e.events, tl)
		for key in segments: segments[key]["program"] = [op for op in segments[key]["program"] if op["op"] != "advance"]
		moves = {}
		for x in e.events:
			if x["kind"] == "player_move": moves.setdefault((x["step"], x["frame"]), [0, 0, 0]); moves[(x["step"], x["frame"])] = [m + v for m, v in zip(moves[(x["step"], x["frame"])], x["args"][1:4])]
		for (step, tick), velocity in sorted(moves.items()):
			motion = segments["0:%d" % step].setdefault("motion", [])
			if motion and motion[-1]["velocity_raw"] == velocity and motion[-1]["through_tick"] == tick - 1: motion[-1]["through_tick"] = tick
			else: motion.append({"actor": "player", "from_tick": tick, "through_tick": tick, "velocity_raw": velocity, "source": "GAME0x800CD084(player,dx,dy,dz) from 0x800ED6E4"})
		changes = []; last = None
		for row in door_rows:
			key = (row["byte8"], row["byte9"], row["half4A"], row["half4E"])
			if key != last: changes.append(row); last = key
		runs.append({"source_area": route["source_area"], "record_index": route["record_index"], "lock_event": route["lock_event"], "camera_setup": camera, "segments": segments, "door_actor_fields": changes, "door_actor_fields_note": "sampled after each scene update; tick = step frame - 1 (the callback tick that wrote the field)", "player_track": compress(tracks["player"]), "finish_ops": [op for op in finish if op["op"] != "stage_request"], "transition": {"destination_stage": route["destination_stage"], "destination_area": route["destination_area"], "destination_transform_raw": route["destination_transform_raw"], "note": "request block filled by GAME door logic before the scene (simulated from the door record)"}, "init_ops": init, "native_ticks": ticks})
	contract = {"schema": 1, "stage": fire_STAGE, "scene_id": 0, "source": "ST1ET door scene 0x800ED1EC (setup 0x800ED228, run 0x800ED510, finish 0x800ED57C); timeline 0x800F0BB8; camera stream word 0x800F0BB4 = -1 (no command stream)",
		"timeline": tl, "camera_offsets": {"table_ram": "0x800F0BE0", "stride": 8, "index": "door record +2 (door_mode)", "rows_raw": [list(struct.unpack("<3h", fire_rd(0x800F0BE0 + i * 8, 6))) for i in range(8)], "formula": "focus = ((doorX+playerX)/2, floorY-0xA0, (doorZ+playerZ)/2); orbit = (playerYaw+row[1], row[0], row[2]) (camera ctx 0x80096D50 +8/+C/+10, +58/+5C/+60)"},
		"player_placement": {"table_ram": "0x800F0C2C", "rows_raw": [list(struct.unpack("<2b", fire_rd(0x800F0C2C + q, 2))) for q in range(4)], "formula": "q = door yaw >> 10; (a,b) = table[q], table[q+1]; x += 124*b - 36*a; z += -36*b - 124*a", "source": "0x800ED330..0x800ED39C"},
		"door_actor": {"pool": "global (SLES0x8003E820)", "class": 1, "variant_byte6": "request+3 (door slot)", "state_writes": {"0x800ED65C": "+9 = 1 at step 1 tick 0", "0x800ED680": "+9 = 3, +0x4A = +0xBC/17, +0x4E = -2 at step 2 tick 0", "0x800ED5E8": "+8 = 2 in finish"}},
		"runs": runs, "finish": {"event_clear": 0x700, "waits": "request byte 0x80078D08 == 2 -> 3, then == 0 (area load done); values set by GAME (simulated)", "unverified": "which GAME routine sets the request byte to 2"},
		"runtime_note": "gameplay.gd already performs door use natively (begin_interaction('door_open'), native_door hinge profiles); this contract documents the original ST1E door scene timing for parity checks"}
	world.write_output(out / "scene_00_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	world.write_output(out / "scene_00.json", json.dumps({"stage": fire_STAGE, "area": 0, "scene_id": 0, "native_tick_hz": 25, "callback_contract_file": "scene_00_callbacks.json", "commands": [], "timeline": tl, "actors": [], "contract_kind": "door_transition_reference"}, indent=1) + "\n", encoding="utf-8")
	return {"runs": len(runs), "controls": sorted({op["control"] for run in runs for s in run["segments"].values() for op in s["program"] if op["op"] == "player_control"})}

fire_NEW_OPS = {"music_prepare / music_play": {"semantics": "SLES0x8001B714 / 0x8001B864 with id 0xFF01 (music hold/resume around the result jingle); unverified"}, "result_banner / result_banner_hide": {"semantics": "SLES0x8003B918(0x44,0x30,2) / 0x8003B9C4 screen overlay (style table 0x8006B324); unverified"},
	"jingle": {"semantics": "SLES0x80020984(0xF,0x333,0); unverified (likely the mission-result jingle)"}, "native_call": {"semantics": "SLES0x80043F70(-5000) before the failure sprinklers; unverified"}, "event_clear": {"semantics": "GAME0x800C0584(id)"}, "hp_refill": {"semantics": "player +0x70 = +0x72"},
	"stage_request": {"semantics": "request block 0x80078D08 type 2 stage change (finish transition)"}, "camera opcode 0x42": {"semantics": "GAME0x800C1A58 player transform set from the command stream"}}

# ------------------------------------------------------------------ fire mission data
def map_change(fire_record, area):
	stage = world.Stage(fire_D["stage"]); x, z = fire_record["position_raw"][0], fire_record["position_raw"][2]; base = fire_K(0x800EAB98, 0x40); SH(0x800EAB94, 0x19); fire_K(0x800EABE4, 0x0043); fire_K(0x800EABE8, 1); tile = [(x >> 9) + base, (z >> 9) + base]
	flags = struct.unpack_from("<H", stage.area(area)[0][tuple(tile)], 0)[0]
	if flags & 0xC000 != 0x8000: raise ValueError(f"ST1E area {area} tile {tile} holds no placement")
	placement = flags & 0x7FF; model = stage.placements[placement][1]
	return {"tile": tile, "placement": placement, "model": model, "state": 1, "node": f"placement_{placement:03d}_model_{model:03d}", "variant_node": f"placement_{placement:03d}_model_{model:03d}_variant_1", "source": "0x800EAB7C..0x800EABE8: tile = ((x >> 9) + 0x40, (z >> 9) + 0x40) of the fire; GAME 0x800C010C(tile word, 1) sets placement state byte +3 low bits = 1 (model variant 1)", "manifest": "manifest.json areas[%d].placement_variants (runtime)" % area}
def area_data(area):
	e, ticks = emulate_area(area); clear, _ = emulate_area(area, clear_at=40 if area != 2 else 60, trigger_at=30 if area == 1 else None)
	trigger = emulate_area(1, trigger_at=30, ticks=200)[0] if area == 1 else None; ev = e.events
	table, count = SPAWNS[area]; spawns = [x for x in ev if x["kind"] == "spawn_table"]
	if (spawns[0]["args"][0] & 0xFFFFFFFF, spawns[0]["args"][1]) != (table, count): raise ValueError(f"area {area} fire spawn differs: {spawns[0]}")
	fires = []
	for i in range(count):
		r = fire_record(table + i * 20)
		if r["class"] != 0x36: raise ValueError("non-fire record %s" % r["source_ram"])
		fires.append({"index": r["index"], "position_raw": r["position_raw"], "size": r["size"], "strength_max": u16(SIZES + r["size"] * 8 + 4), "variant": r["variant"], "behaviour": r["behaviour"], "contact_damage": r["contact_damage"], "child_submode": 1 if r["behaviour"] & 1 else 3, "triggers_explosion": bool(r["behaviour"] & 2), "throws_embers": bool(r["behaviour"] & 4), "source_ram": r["source_ram"], "bytes_hex": r["bytes_hex"]})
	limit = {0: fire_K(0x800E75E4, 0x708), 1: 0xE10, 2: fire_K(0x800E79B0, 0x1518)}[area]; field = {0: 0xA, 1: 0xC, 2: 0xE}[area]
	radio = [{"tick": x["room"]["timers"][area], "message": x["args"][0]} for x in ev if x["kind"] == "radio_message"]
	warnings = [r for r in radio if r["message"] != 0x2A]; hints = [r for r in radio if r["message"] == 0x2A]; timeout = [x for x in ev if x["kind"] == "scene_start"]
	entry = {"fires": fires, "fire_count_initial": next(x["room"]["fires"] for x in ev if x["kind"] == "conversation" or x["state"] == 0 and x["kind"] in ("spawn_table",)) if False else None,
		"entry_flags": [x["args"][0] for x in ev if x["kind"] == "flag_set" and x["room"]["area_state"] == 0], "unlock_flag": next((x["args"][0] for x in clear.events if x["kind"] == "flag_clear"), None),
		"timer_field": "0x8009C9%02X" % field, "timer_limit": limit, "timer_runs": "+1 per gameplay tick while below the limit and player HP (0x8008C110) != 0 (0x800E7B88); scene 0xD starts when it returns 1 (limit reached or HP 0) and no conversation (0x80078CC8) is active",
		"timeout_tick": timeout[0]["room"]["timers"][area] if timeout else None, "timeout_scene": timeout[0]["args"][0] if timeout else None, "warnings": warnings,
		"hint": {"idle_ticks": 0x384, "message": 0x2A, "counter": "0x8009C910", "resets_on": "player +0x13C bit 0x40 (spraying, unverified) or flag 0x681 (blocking message)", "emulated_ticks": [h["tick"] for h in hints], "source": "0x800E7A8C"}}
	entry["fire_count_initial"] = next((x["room"]["fires"] for x in ev if x["kind"] in ("conversation", "radio_message", "scene_start", "spawn_table") and x["room"]["fires"]), None) or e.u8(ROOM + 4) or count
	completion = [x for x in clear.events if x["kind"] in ("flag_set", "flag_clear", "scene_start") and x["room"]["fires"] == 0]
	entry["on_clear"] = [{"kind": x["kind"], "value": x["args"][0], "caller": x["caller"]} for x in completion]
	if area == 0: entry["start_sequence"] = [{"op": "conversation", "message": x["index"], "window": x["args"][2], "caller": x["caller"]} if x["kind"] == "conversation" else {"op": x["kind"], "args_raw": x["args"][:3], "caller": x["caller"]} for x in ev if x["kind"] in ("conversation", "overlay_show", "overlay_hide")]
	if area == 1:
		extra = fire_record(EXTRA_FIRE); spawned = [x for x in trigger.events if x["kind"] == "spawn_table" and x["args"][0] & 0xFFFFFFFF == EXTRA_FIRE]
		entry["triggered_fires"] = [{"index": extra["index"], "position_raw": extra["position_raw"], "yaw_raw": extra["yaw_raw"], "size": extra["size"], "strength_max": fire_K(0x800EAA50, 0x1000), "variant": extra["variant"], "contact_damage": extra["contact_damage"], "behaviour": extra["behaviour"], "source_ram": extra["source_ram"], "bytes_hex": extra["bytes_hex"], "trigger": "room+6 (0x8009C906) set by extinguishing a fire with behaviour bit1 (0x800EA030); area 1 state 1 spawns it and adds 1 to the room fire count (0x800E7774)", "emulated": bool(spawned), "fire_count_after": spawned[0]["room"]["fires"] + 1 if spawned else None, "map_change": map_change(extra, area)}]
	if area == 2:
		entry["npcs"] = [{"record": fire_record(0x800EF3C8), "role": "Data (class 0x63 v0, handler 0x800E7BD4)"}, {"record": fire_record(0x800EF3F0), "role": "script actor class 0x1D playing message 0x03 (0x800EC130)"}]
		entry["intro"] = {"flag": 0x681, "ember_block": "room+8 = 1 until flag 0x681 clears (0x800E797C/0x800E79A8); the timer is not ticked in state 1"}
	return entry

def blast():
	for a, v in ((0x800EAB2C, 7), (0x800EAB50, 0xE), (0x800EAB94, 0x19), (0x800EAEA0, 7), (0x800EC4A4, 0x14)): SH(a, v)
	return {"source": "ST1ET variant 1 fire 0x800EA994 (dispatch), init 0x800EAA18, burning 0x800EAC2C, hitbox 0x800EB23C; effect class 0x12 (pool 8) init/update 0x800EC3CC/0x800EC464 flame, 0x800EC600/0x800EC648 flash, 0x800EC69C/0x800EC760 debris",
		"init": {"flash_variant": fire_K(0x800EAA78, 3), "debris_variant": fire_K(0x800EAACC, 4), "debris_count": fire_K(0x800EAB70, 0x10), "debris_subtypes": fire_K(0x800EAA94, 3), "debris_y_raise": fire_K(0x800EAAF4, 0x40), "debris_y_mask": fire_K(0x800EAB0C, 0x7F), "debris_yaw_wobble": [fire_K(0x800EAB3C, 0x40), fire_K(0x800EAB30, 0x7F), 7], "debris_speed": [fire_K(0x800EAB58, 0x18), fire_K(0x800EAB54, 0xF), 14],
			"yaw_byte_shift": 4, "shake": {"mode": fire_K(0x800EABEC, 1), "magnitude": fire_K(0x800EABF0, 0x6000), "decay": fire_K(0x800EABF8, 0x800), "source": "SLES0x80016B1C(mode, magnitude, decay): +0xD8 = magnitude if mode == 0 or magnitude > current, +0xDC = decay; GAME0x800C24C0 subtracts (+0xD8 >> 8) from the camera focus Y"}, "sound": fire_K(0x800EABFC, 0x8B), "map_change": "GAME0x800C010C(tile word, 1) at 0x800EABE4"},
		"burning": {"flame_period_ticks": fire_K(0x800EADAC, 4), "flame_variant": fire_K(0x800EADE0, 2), "flame_jitter": {"offset": fire_K(0x800EADF4, 0xF), "mask": fire_K(0x800EAE0C, 0x1F), "shifts": [0, SH(0x800EAE14, 5), SH(0x800EAE2C, 10)], "check": [fire_K(0x800EAE24, 0xF), fire_K(0x800EAE3C, 0xF), fire_K(0x800EAE20, 0x1F), fire_K(0x800EAE38, 0x1F)]}, "wobble": {"phase_bit": fire_K(0x800EAE50, 0x20), "mask": fire_K(0x800EAE5C, 0x1F), "center": fire_K(0x800EAE60, 0x10)}, "flame_size_shift": 7, "debris_ticks": fire_K(0x800EAEB0, 9), "debris_variant": fire_K(0x800EAEDC, 4), "debris_subtypes": 3,
			"hitbox": {"forward_raw": fire_K(0x800EB26C, 0x20), "radius_raw": fire_K(0x800EB28C, 0x10) * 4, "center": "(x + out.x, y, z + out.z) with out = trig(yaw) * 0x20 (0x800EB270, 0x800EB2B4..0x800EB2E0); a2 = byte2 << 24 | 0x400010, a3 = 0x8A0000 | damage"}},
		"flame": {"init_velocity": fire_K(0x800EC440, 0x80), "gravity": fire_K(0x800EC498, -0x20), "velocity_shift": 4, "move": "x/z += trig(yaw byte * 16 + 0x800)[0/1] * speed >> 12 (SLES0x80042674); y += (velocity << 16) >> 20; speed = effect +0xE = strength >> 7", "hitbox": {"size_shift": 3, "damage": "0x980000 | effect +0xD (contact damage 0x0A), a2 = byte2 << 24 | 0x480000 | size >> 3", "source": "0x800ED0CC"}},
		"debris": {"init_velocity": [fire_K(0x800EC734, 0xA8), fire_K(0x800EC730, 0x3F)], "gravity": fire_K(0x800EC78C, 0x18), "velocity_shift": 4, "floor_probe_after": fire_K(0x800EC838, 0x11) - 1, "max_age": fire_K(0x800EC888, 0x40), "move": "x/z += trig(yaw byte * 16 + 0x800)[0/1] * speed >> 12 (SLES0x80042674); +0xD age counter"},
		"flash": {"initial": 0xFF, "decay": -fire_K(0x800EC66C, -0x20), "end_below": fire_K(0x800EC658, 0x20), "draw": "GP0 0x62 gray (c, c, c) full-screen rectangle at (0,0), draw mode 0xE1000220 (additive), 0x800ECDF8", "initial_source": "0x800EC620 (sb -1 +0xC)"}}
def fire_block(atlas, rows, boxes):
	sizes = []
	for size in range(4):
		tpage, clut, maximum = struct.unpack("<3H", fire_rd(SIZES + size * 8, 6)); frames = fire_frames(size)
		for f in frames: f["atlas_id"] = atlas.add(tpage, clut, f["u"], f["v"], f["w"] + 1, f["h"] + 1)
		sizes.append({"size": size, "tpage": fire_H(tpage)[-4:], "clut": fire_H(clut)[-4:], "strength_max": maximum, "blend": "additive" if (tpage >> 5) & 3 == 1 else "normal", "semi_transparency_mode": (tpage >> 5) & 3, "frames": frames, "sequence": [[f["atlas_id"], f["ticks"]] for f in frames], "source_ram": fire_H(SIZES + size * 8), "frames_ram": fire_H(FRAMES + size * 0x80)})
	mismatches = [r for r in rows if r["result"] != -1 and r["strength_after"] != formula(int(r["hit_word"], 16), r["player_distance_raw"], 0x700, sizes[r["size"]]["strength_max"]) or r["result"] == -1 and r["strength_after"] != 0]
	return {"class": 0x36, "pool": "enemy pool 0xCC stride (list byte 0x60)", "handlers": {"variant0": "0x800E9DE4", "variant0_states": {"init": "0x800E9E68", "burning": "0x800E9FD8", "dying": "0x800EA3CC", "table": "0x800EF468"}, "variant1": "0x800EA994", "variant1_states": {"init": "0x800EAA18", "burning": "0x800EAC2C", "dying": "0x800EB014", "table": "0x800EF694"}},
		"regrow_per_tick": fire_K(0x800EA074, 0x10), "regrow_rule": "when not hit and strength < max: strength = min(strength + 0x10, max) (0x800EA060..0x800EA090)", "out_threshold": fire_K(0x800EA6B0, 0x201) - 1, "out_rule": "after damage, strength <= 0x200 -> strength = 0 and the fire is out (0x800EA6B0)",
		"hit_mask": (fire_K(0x800EA608, 4) << 16) | fire_K(0x800EA60C, 0x2000), "damage_scale": 1 << SH(0x800EA630, 5), "damage_rule": "damage = (hit_word & 0xFFF) << 5 (0x800EA624/0x800EA630); hit word = actor+0x74, cleared each tick by the hitbox registration (0x800EA714)",
		"close_bonus": {"requires_hit_bit": fire_K(0x800EA634, 0x2000), "distance_function": "SLES0x80041BEC(player 0x8008C0A0, fire)", "distance_clamp": [fire_K(0x800EA654, 0x80), fire_K(0x800EA65C, 0x100)], "scale_numerator": 13, "scale_shift_left": SH(0x800EA684, 6), "scale_shift_right": SH(0x800EA688, 7), "offset": fire_K(0x800EA68C, 0x3C0), "final_shift": SH(0x800EA690, 3),
			"formula": "d = clamp(distance, 0x80, 0x100); bonus = (((((0x100 - d) * 13) << 6) >> 7) + 0x3C0) >> 3  (0x78 at d>=0x100 .. 0xE0 at d<=0x80); added to damage", "source": "0x800EA634..0x800EA694"},
		"verification": {"emulated_samples": len(rows), "formula_mismatches": mismatches, "samples": rows},
		"contact_damage": 8, "contact_damage_source": "spawn record +0xD (actor +0xD), hitbox a3 = 0x8A0000 | actor+0xD (0x800EA778..0x800EA790); flag meaning unverified", "contact_damage_unverified": True,
		"hitbox_raw": {"function": "SLES0x80042704", "radius": "max(0x40, strength >> shift); shift = 5 for size 0, 6 otherwise (0x800EA70C..0x800EA738)", "center": "(x, y - radius, z) integer position", "a2": "(actor byte2 << 24) | 0x400000 | (radius >> 2)", "a3": "0x8A0000 | contact_damage", "emulated": boxes},
		"heat": {"rule": "if distance(player, fire) < strength >> 2: room+0 += (strength >> 2) - distance (0x800EA938)", "consumer": "effect class 0x12 v0 (0x800EC220): heat += rand & 0x1FF when non-zero; full-screen additive rectangle (0x800ECDF8, GP0 0x62 with draw mode 0xE1000220) red = (heat << 7) >> 12, green = (heat * 48) >> 12; heat cleared every tick"},
		"sounds": {"loop": fire_K(0x800EA378, 0x152), "loop_period_ticks": fire_K(0x800EA370, 0x21) + 1, "loop_first_delay": "(actor byte2 & 0xF) * 2 (0x800E9F14..0x800E9F28)", "extinguished": fire_K(0x800EA448, 0x153), "explosion": fire_K(0x800EABFC, 0x8B), "explosion_fire_loop": fire_K(0x800EAFD4, 0x158), "explosion_fire_loop_period_ticks": fire_K(0x800EAFCC, 0x1C) + 1, "data_ignite": fire_K(0x800E8328, 0x154), "api": "SLES0x800203F4(id, position)"},
		"sprite": {"atlas": "fire_atlas.png", "by_size": sizes, "blend": "additive", "packet": "POLY_FT4-shaped world sprite at *0x1F800050 (0x800EA7A4): cmd 0x2E808080 (semi-transparent), xy0 = (y - (strength >> 5)) << 16 | x, xy1 = z, word 0x18 = (strength >> 4) - (strength >> 6), uv from frame table, tpage/clut from size table",
			"size_raw": "(strength >> 4) - (strength >> 6)", "anchor_raise_raw": "strength >> 5", "size_semantics_unverified": True, "size_note": "the SLES consumer of the 0x1F800050 sprite packets was not traced; GAME buster projectiles use the same layout with word 0x18 = width_raw | rotation << 16", "uv_note": "frame w/h (and effect u1/v1) are inclusive end offsets: the drawn quad spans u..u+w, so the atlas cells are (w+1)x(h+1)", "animation": "each frame shows for frame.ticks ticks; after a frame with last=true the sequence restarts at 0 (0x800EA8B4..0x800EA92C)"},
		"init": {"strength": "size table max", "ember_timer": "0x90 + (rand & 0x3F) (0x800E9F08..0x800E9F10)", "child": {"class": 0x3E, "handler": "0x800EB314", "submode": "1 if behaviour bit0 (child +0xE = record index & 1) else 3", "unverified": "visual role of class 0x3E"}},
		"splash": {"rule": "hit with bit 0x2000 spawns class 0x3E submode 0 at the fire, killed after 8 ticks (0x800EA094..0x800EA15C)", "unverified": True},
		"dying": {"rule": "kill children, sound 0x153; on odd ticks spawn effect 0x12 v1 (+6=2 steam) at (x+0x20-(rand&0x3F), y-((rand>>6)&7), z+0x20-((rand>>9)&0x3F)); after 3 puffs spawn global class 0x14 (smoke/scorch, unverified); free after 0x%X ticks" % fire_K(0x800EA5C4, 0x1D0), "counts": "room+4 -= 1, room+5 += 1, behaviour bit1 sets room+6 (0x800EA01C..0x800EA054)"},
		"explosion": {"variant": 1, "record": fire_H(EXTRA_FIRE), "init": "0x800EAA18: strength = max = 0x1000; spawn effect 0x12 v3 (white additive flash 0xFFFFFF fading by 0x20 per tick, 0x800EC600/0x800EC648) and 16 effect 0x12 v4 debris (+6 cycling 0..2); GAME0x800C010C(map cell word at fire x/z, 1) (map change, unverified); SLES0x80016B1C(1,0x6000,0x800) camera shake; sound 0x8B",
			"burning": "0x800EAC2C: same damage/regrow/out rules (0x800EA600) without room+6; every 4 ticks spawn effect 0x12 v2 flame (+0xE = strength >> 7); first 9 ticks also spawn v4 debris; hitbox offset 0x20 along yaw, radius 0x40 (a2 low 0x10), a3 0x8A0000|0x0A; no sprite of its own", "contact_damage": 0x0A, "blast": blast(),
			"trigger": "Living Room fire index 12 (record 0x800EF33C, behaviour 2) extinguished -> room+6 -> area 1 state 1 spawns 0x800EF350"},
		"embers": {"room": 2, "source_fires": "behaviour bit2 (Kitchen records)", "strength_gate": fire_K(0x800EA17C, 0xC00), "blocked_by": "room+8 bit0 (Data intro or Data burning)", "interval": "0x90 + (rand & 0x7F) ticks (0x800EA1DC..0x800EA1E8)", "target_raw": list(struct.unpack("<3h", fire_rd(0x800E719C, 6))), "target_source": "0x800E719C (Data spawn point)",
			"target_jitter": {"x": "- ((rand & 0xFF) - 0x80)", "z": "- (((rand >> 8) & 0x7F) - 0x40)"}, "launch": {"speed_raw": fire_K(0x800EA28C, 0x300), "y_offset": "-0x40 - (rand & 0xF)", "arc": "SLES0x80042298(start, target, 0x100, 0xC, -1) -> ember +0x16 (initial vertical speed, unverified)"},
			"flight": {"horizontal_speed_raw": fire_K(0x800EC99C, 0x100), "gravity_per_tick": fire_K(0x800EC9B0, 0xC), "lifetime_ticks": fire_K(0x800ECC3C, 0x80), "water_mask": (fire_K(0x800ECB94, 5) << 16) | fire_K(0x800ECB9C, 0x2000), "floor": "GAME0x800B18A4/0x800B13FC; landing spawns global class 0 variant 3 (+0xC = 0x30 + rand&0xF, unverified scorch)"},
			"hitbox": {"a3": "0x900004 (damage 4; includes bit 0x100000)", "source": "0x800ED154", "radius": "0x800F0B8C[+6] >> 3"}, "effect": "class 0x12 variant 5",
			"data_burning": {"ignite_bit": (fire_K(0x800E7DF4, 0x10) << 16), "ignite_bit_source": "Data hit word ext+0 tested at 0x800E7DF4; the ember (0x900004) and explosion flame (0x98xxxx) hitboxes carry bit 0x100000, fire hitboxes (0x8Axxxx) do not (inferred)", "on_ignite": "state 0x800E8258: room+8 |= 1, ext+0xC |= 4, effect 0x12 v6 flame child, strength +0x70 = max HP +0x72, room+4 += 1, sound 0x154",
				"extinguish": "0x800E9464: same 0x42000 mask, damage and close bonus; strength <= 0x200 -> out, flame killed, room+4 -= 1 (0x800E7E10..0x800E7E54)", "no_damage_while": "ext+0xC bit 0x4 set (0x800E951C), unverified window", "unverified": True}},
		"effects": {str(v): dict({k: (fire_H(x) if isinstance(x, int) and k in ("anim", "page", "size", "rise") else x) for k, x in spec.items()}, subtypes=[effect_sub(atlas, spec, s) for s in range(spec["count"])]) for v, spec in EFFECTS.items()}}
def effect_sub(atlas, spec, sub):
	tpage, clut, semi = struct.unpack("<3H", fire_rd(spec["page"] + sub * 8, 6)); frames = effect_frames(spec, sub); item = {"subtype": sub, "tpage": fire_H(tpage)[-4:], "clut": fire_H(clut)[-4:], "semi_transparent": bool(semi), "blend": ("additive" if (tpage >> 5) & 3 == 1 else "subtractive" if (tpage >> 5) & 3 == 2 else "average" if (tpage >> 5) & 3 == 0 else "quarter") if semi else "normal", "frames": frames}
	if "size" in spec: item["initial_size_raw"] = u16(spec["size"] + sub * 2)
	if "rise" in spec: item["rise_per_tick_raw"] = u16(spec["rise"] + sub * 2)
	for f in frames:
		u, v, w, h = min(f["u0"], f["u1"]), min(f["v0"], f["v1"]), abs(f["u1"] - f["u0"]) + 1, abs(f["v1"] - f["v0"]) + 1
		if w and h and (tpage >> 7) & 3 == 0: f["atlas_id"] = atlas.add(tpage, clut, u, v, w, h); f["mirror_u"] = f["u1"] < f["u0"]; f["mirror_v"] = f["v1"] < f["v0"]
		else: f["atlas_id"] = None
	return item

def kitchen_data(manifest, runtime):
	actor = fire_actor_entry(fire_record(0x800EF3C8), 2, manifest, runtime); actor["class_note"] = "Data (class 0x63 variant 0, NPC pool 0x20; handler 0x800E7BD4 = class cell 0x800EE944 variant 0)"
	if [fire_u32(0x800EE944 + i * 4) for i in range(2)] != [0x800E7BD4, 0x800E9958] or [fire_u32(0x800EF404 + i * 4) for i in range(3)] != [0x800E7CF0, 0x800E7DB8, 0x800E9354]: raise ValueError("Data class tables differ")
	states = [fire_H(fire_u32(0x800EF410 + i * 4)) for i in range(9)]; route_modes = [fire_H(fire_u32(0x800EF434 + i * 4)) for i in range(3)]
	routes = [[list(struct.unpack("<3hH", fire_rd(0x800E7020 + r * 64 + i * 8, 8))) for i in range(8)] for r in range(4)]
	return {"actor": actor, "source": {"handler": "0x800E7BD4", "init": "0x800E7CF0", "main": "0x800E7DB8", "states_table": "0x800EF410", "states": states, "route_modes_table": "0x800EF434", "route_modes": route_modes, "mover": "0x800E9718", "bounds_clamp": "0x800E96A4", "wall_reflect": "GAME0x800B32B8", "hitbox": "0x800E9574", "extinguish": "0x800E9464", "scream": "0x800E98B8", "floor": "0x800E9374"},
		"ext": "actor +0x14C (pointer 0x800F0E6C): +0 hit word, +8 flame effect, +0xC flags (bit0 done, bit1 burning, bit2 ignite grace), +0xE counter, +0x10 route, +0x11 route point, +0x12 sound timer",
		"center_raw": list(struct.unpack("<3h", fire_rd(0x800E7018, 6))), "routes_raw": routes, "route_note": "point = (x, y, z, flags); (flags >> 12) & 3 selects walk/jump/climb; flags bit15 ends the route and loops to flags & 0xF while counter +0xE > 0",
		"bounds_raw": {"x": [fire_K(0x800E96AC, 0x20), fire_K(0x800E96C8, 0x131) - 1], "z": [fire_K(0x800E96E4, 0x50), fire_K(0x800E96FC, 0x151) - 1], "flags": {"x_low": 0x200, "x_high": 0x100, "z_high": 0x400, "z_low": 0x800}},
		"strength_max": fire_K(0x800E7D30, 0x800), "regrow": fire_K(0x800E7E80, 0x10), "gravity": fire_K(0x800E7D38, 0x28), "spin_speed": fire_K(0x800E8DC4, 0x230), "spin_ticks": fire_K(0x800E8DB8, 0x4B), "circle_ticks": fire_K(0x800E8630, 0x5B), "circle_radius": fire_K(0x800E858C, 0x71) - 1, "circle_yaw_offset": fire_K(0x800E8580, 0x400),
		"panic_speed": fire_K(0x800E813C, -0xC0), "burning_speed": fire_K(0x800E845C, -0x190), "avoid_distance": fire_K(0x800E900C, 0x100), "avoid_jump": fire_K(0x800E9014, -0x190), "run_target": {"yaw": fire_K(0x800E83AC, 0x800), "distance": fire_K(0x800E83B8, 0x700), "source": "SLES0x800425FC(out, 0x800, 0x700) + center"},
		"controls": {"panic": fire_K(0x800E7D20, 1), "ignite": fire_K(0x800E82CC, 2), "burning": fire_K(0x800E8454, 3), "ignite_end": "actor +0x9F bit7 (animation reached its held record)"},
		"sounds": {"panic": [fire_u32(0x800E7138 + i * 4) for i in range(4)], "panic_interval": [fire_K(0x800E8168, 0x78), fire_K(0x800E8160, 0x1F)], "ignite": fire_K(0x800E8328, 0x154), "ignite_timer": fire_K(0x800E8344, 0x28), "scream": [fire_K(0x800E98C0, 0x155), fire_K(0x800E98D0, 0x15E)], "scream_interval": [fire_K(0x800E9910, 0xB4), fire_K(0x800E990C, 0x1F)], "jump": [fire_u32(0x800E7148 + i * 4) for i in range(16)]},
		"hitbox": {"offset_y_raw": fire_K(0x800E95A8, -0x200) >> 4, "radius_raw": (fire_u32(0x800E968C) & 0xFF) * 4, "burning_contact_damage": fire_K(0x800E9638, 0x10), "ignite_bit": fire_K(0x800E7DF4, 0x10) << 16, "source": "0x800E9574: SLES0x80042704 a2 = byte2<<24 | (burning ? 0x400000 : 0x280000) | 8, a3 = 0x800000 | (burning ? 0xA0010 : 0x40000)"},
		"flame": {"effect": 6, "bone": 6, "bone_offset_y_raw": -0x20, "size_shift": 6, "source": "0x800E7FBC SLES0x8003EFF4(actor, 6, -0x20); flame +0xC = strength >> 6 (0x800E8068..0x800E807C)"},
		"ember_init_timer": [fire_K(0x800E9F0C, 0x90), fire_K(0x800E9F08, 0x3F)], "ember_interval": [fire_K(0x800EA1E0, 0x90), fire_K(0x800EA1DC, 0x7F)], "ember_target_jitter": {"x": [fire_K(0x800EA23C, 0xFF), fire_K(0x800EA240, -0x80)], "z": [fire_K(0x800EA258, 0x7F), fire_K(0x800EA268, -0x40)], "rule": "target = data spawn - ((rand & mask) + bias); z uses rand >> 8"},
		"ember_launch": {"distance": fire_K(0x800EA28C, 0x300), "y": [fire_K(0x800EA2E0, -0x40), fire_K(0x800EA2F8, 0xF)], "arc_speed": fire_K(0x800EA32C, 0x100), "arc_gravity": fire_K(0x800EA344, 0xC), "rule": "yaw = ratan2(fire - target); start = fire + SLES0x800425FC(yaw, distance) (x/z), y = fire.y - 0x40 - (rand & 0xF); vertical = SLES0x80042298(start, target, 0x100, 0xC)"}, "ember_hitbox": {"radius_raw": (u16(0x800F0B8C) >> 3) * 4, "word": 0x900004, "source": "0x800ED154"}, "ember_size_raw": u16(0x800F0B8C), "ember_land_shrink_until": fire_K(0x800ECACC, 9),
		"unverified": ["Data state 8 (0x800E9248) is only reachable when +9 is already 8; nothing in ST1ET writes it", "smoke puffs from the flame effect and steam from hits (effect 0x12 v1) are not exported", "state 7 hit bit 0x10000 source"]}

def export_fire_mission(root=None, out_dir=None, levels_dir=None):
	root = Path(root or ROOT); fire_load(root); out = Path(out_dir or root / "assets/levels") / fire_STAGE; levels = Path(levels_dir or root / "assets/levels"); out.mkdir(parents=True, exist_ok=True)
	doors = export_doors(fire_D["disc"] / "DAT", levels, out.parent)
	memory, uploads = vram(); atlas = Atlas(memory); rows, boxes = fire_math(); fire = fire_block(atlas, rows, boxes); atlas_size = atlas.save(out / "fire_atlas.png"); fire["sprite"]["atlas_size"] = atlas_size; fire["atlas_frames"] = atlas.items; fire["vram_uploads"] = uploads
	areas = {str(area): area_data(area) for area in range(3)}
	manifest = json.loads((levels / fire_STAGE / "models/ST1E_04800/manifest.json").read_text(encoding="utf-8")); source = root / manifest["models"][0]["file"]; actors = out / "actors"; actors.mkdir(exist_ok=True)
	for item in source.parent.glob(source.stem + "*"):
		if item.suffix in (".glb", ".png"): write_output(actors / item.name, item.read_bytes())
	runtime = "assets/levels/%s/actors/%s" % (fire_STAGE, source.name); results = {name: build_result(name == "success", manifest, runtime, out) for name in ("success", "failure")}; door_scene = build_door(doors, out)
	mission = {"stage": fire_STAGE, "native_tick_hz": 25, "areas": areas, "fire": fire, "kitchen_data": kitchen_data(manifest, runtime),
		"messages": {"bank": "DAT/ST1E.BIN 0x6030 (runtime 0x8010C000)", "start": 0x00, "yes": 0x01, "no": 0x02, "yes_no_unverified": True, "objective": 0x32, "objective_window": 9, "kitchen": 0x03, "locked_forward": 0x0A, "locked_back": 0x0B, "hint": 0x2A, "timeout_warnings": {k: v["warnings"] for k, v in areas.items()}, "success": results["success"]["messages"], "failure": results["failure"]["messages"]},
		"failure": {"timeout": "area timer reaches its limit (0x800E7B88 returns 1) -> GAME0x800C0B0C(0xD) without flag 0x129", "hp_zero": "player HP 0x8008C110 == 0 makes 0x800E7B88 return 1 -> scene 0xD (failure); precedence over GAME death handling unverified", "hp_zero_unverified": True, "scene": 0xD, "branch_file": results["failure"]["file"]},
		"completion": {"flag": 0x129, "fast_flag": 0x12A, "fast_limit": fire_K(0x800ED8B4, 0xD49), "fast_rule": "success: timers 0x8009C90A + 0x8009C90C + 0x8009C90E < fast_limit", "failure_fast_count": fire_K(0x800ED8D4, 0x12), "failure_fast_rule": "failure: fires extinguished 0x8009C905 >= failure_fast_count", "scene": 0xD, "source": "0x800E7A54 (Kitchen clear sets 0x129, starts scene 0xD); 0x800ED800 (0x12A)", "next_stage": results["success"]["transition"]},
		"room_block": {"address": fire_H(ROOM), "fields": {"0x00": "heat accumulator", "0x04": "fires left", "0x05": "fires extinguished (mission)", "0x06": "explosion trigger", "0x08": "ember block bit0", "0x0A": "Deck timer", "0x0C": "Living Room timer", "0x0E": "Kitchen timer", "0x10": "idle counter"}, "cleared": "area 0 entry only (0x800E74FC)"},
		"scene_triggers": "scene_triggers.json",
		"source": {"overlay": "DAT/ST1ET.BIN (load 0x800E7000, code size 0x%X)" % struct.unpack_from("<I", fire_D["ovl"], 4)[0], "area_handlers": fire_H(AREA_HANDLERS), "per_frame": fire_H(fire_PER_FRAME), "spawn_tables": {k: fire_H(v[0]) for k, v in SPAWNS.items()}, "extra_fire": fire_H(EXTRA_FIRE), "sizes": fire_H(SIZES), "frames": fire_H(FRAMES), "timer_tick": "0x800E7B88", "idle_hint": "0x800E7A8C", "radio": "0x800E7B20 (class 0x1B script actor, window 4)", "scene_0xD": "0x800ED7B8", "scene_0": "0x800ED1EC", "emulator": "tools/cinematics.py Emu (unicorn) with ST1E stubs in tools/cinematics.py"},
		"unverified": ["sprite packet size semantics (half vs full extent)", "class 0x3E / effect 0x12 v1..v6 / global class 0x14 roles", "ember arc helper SLES0x80042298 meaning", "Data damage gate ext+0xC bit 4", "weapon module providing hit bit 0x2000", "message 0x00 yes/no branch targets", "SLES0x8003B918 / 0x80020984 / 0x80043F70 effects", "GAME death handling vs HP==0 failure path"]}
	world.write_output(out / "fire_mission.json", json.dumps(mission, indent=1) + "\n", encoding="utf-8")
	triggers = {"stage": fire_STAGE, "triggers": [{"scene_id": 0, "file": "scene_00.json", "when": "door use: GAME door logic (0x800B7DA4..0x800B7E0C) fills request 0x80078D08 and sets flag 0x700; ST1ET per-frame 0x800E7488 starts scene 0 while 0x700 is set", "source_function": "GAME0x800C0B0C(0) at 0x800E7498", "runtime": "gameplay.gd _use_door already performs this natively"},
		{"scene_id": 0xD, "branch": "success", "file": results["success"]["file"], "entry_area": 2, "when": "Kitchen (area 2, state 2) fire count reaches 0: flag 0x129 set then scene 0xD (0x800E7A54..0x800E7A60)", "requires_flag": 0x129, "source_function": "GAME0x800C0B0C(0xD)"},
		{"scene_id": 0xD, "branch": "failure", "file": results["failure"]["file"], "entry_area": [0, 1, 2], "when": "area timer limit or player HP 0 (0x800E7B88 returns 1, no conversation active): Deck 0x800E75F8, Living Room 0x800E7804, Kitchen 0x800E79C4", "requires_flag_clear": 0x129, "source_function": "GAME0x800C0B0C(0xD)"}]}
	world.write_output(out / "scene_triggers.json", json.dumps(triggers, indent=1) + "\n", encoding="utf-8")
	return {"doors": len(doors["area_transitions"]), "atlas": atlas_size, "areas": {k: (len(v["fires"]), v["timer_limit"], v["unlock_flag"], v["warnings"]) for k, v in areas.items()}, "results": {k: (v["ticks"], v["messages"], v["flags_set"]) for k, v in results.items()}, "door_scene": door_scene, "fire_formula_mismatches": len(fire["verification"]["formula_mismatches"])}

# ---- flight_scene ----
# Export the ST3A flight scene (scene 6, PAL): scene_06.json, scene_06_callbacks.json, scene_triggers.json and the scene
# actor models, from DAT/ST3AT.BIN static tables and a unicorn emulation (tools/cinematics.py Emu) of the unchanged scene handler.
flight_STAGE = "ST3A"; flight_BASE = 0x800E7000; flight_CTX = 0x8007CEC0; flight_PLAYER = 0x8008C0A0; flight_REQ = 0x80078D08; flight_AREA_BYTE = 0x8009C7F9; LATCH = 0x8009BE08
flight_SCENE_ID = 6; flight_HANDLER = 0x800F2840; flight_STATES = 0x800F69EC; flight_CAMERA = 0x800F5F7C; flight_TIMELINE = 0x800F6894; flight_PER_FRAME = 0x800E7574; flight_STAGE_INIT = 0x800E7328
flight_D = {}
def flight_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST3AT.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != flight_BASE: raise ValueError("unexpected ST3AT header")
	flight_D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), code_end=flight_BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_D.update(ovl=ovl, game=flight_D["game"]); intro_SLES = flight_D["sles"]; intro_GAME = flight_D["game"]; intro_OVL = ovl
	game = lambda a: struct.unpack_from("<I", flight_D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + flight_SCENE_ID * 4), game(0x800DBEA0 + 0x3A * 4), game(0x800DC66C + 0x3A * 4)) != (flight_HANDLER, flight_STAGE_INIT, flight_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST3A scene 6")
	if [fire_u32(0x800F4560), fire_u32(0x800F4668), fire_u32(0x800F466C), fire_u32(0x800F45C8)] != [0x24070000 | BACKDROP_TPAGE, 0x3C040000 | BACKDROP_CLUT, 0x34848000, 0x0C018F75]: raise ValueError("scrolling backdrop draw mode differs")
	if fire_u32(flight_HANDLER + 0xC) & 0xFFFF != 4 or [fire_u32(0x800F28C8), fire_u32(0x800F28CC), fire_u32(0x800F28D0), fire_u32(0x800F28D8)] != [0x3C04800F, 0x24845F7C, 0x3C05800F, 0x24A56894]: raise ValueError("scene 6 camera/timeline binding differs")

def emulator():
	class Emu(stage_emulator(flight_STAGE_INIT, 0x800F22B8, flight_D["code_end"], ((0x800F4530, "backdrop", 0, False, False), (0x800F4724, "effect_0f", 0, True, False), (0x800F47E4, "actor_21", 0, True, False)))):
		def stub_hook(self, uc, address, size, data):
			name = self.stubs[address][0]; a = [self.r(4), self.r(5)]; ra = self.r(31)
			if name in ("effect_0f", "actor_21"): self.record(name, entry=bytes(uc.mem_read(a[0] & 0x1FFFFFFF, 8)).hex(), entry_ram=flight_H(a[0]), arg=a[1], caller=flight_H(ra - 8)); return self._ret(uc, 0, ra)
			return super().stub_hook(uc, address, size, data)
	return Emu

def flight_H(v): return "0x%08x" % (v & 0xFFFFFFFF)

def flight_emulate():
	import unicorn
	e = emulator()(); e.requests = []; e.w8(flight_AREA_BYTE, 0); e.w32(LATCH, 0)
	e.call(flight_PER_FRAME); started = [x for x in e.events if x["kind"] == "scene_start"]
	if [x["args"][0] for x in started] != [flight_SCENE_ID] or e.u8(LATCH) != 1: raise RuntimeError("ST3A per-frame handler did not start scene 6 once")
	e.events.clear(); e.call(flight_PER_FRAME)
	if e.events: raise RuntimeError("ST3A per-frame handler restarted scene 6 with the latch set")
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = flight_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=flight_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(flight_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(flight_PLAYER, e.u8(flight_PLAYER) | 2); sb = lambda a: e.u8(a) - (e.u8(a) & 0x80) * 2
	tracks, tick = run_scene(e, flight_HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(flight_CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(flight_PLAYER) & 2)), "sound_latch": (0, lambda e: e.u8(flight_CTX + 0x1A)), "backdrop": ((0, 0, 0), lambda e: (e.u8(flight_CTX + 0x16), sb(flight_CTX + 0x14), sb(flight_CTX + 0x15)))})
	return e, tracks, tick

BACKDROP_TPAGE = 0x1B; BACKDROP_CLUT = 0x7C80; BACKDROP_FILE = "scrolling_backdrop.png"
# SLES0x8001392C only starts a fade; these are followed by a 0x80078F01 wait (0x800F4084, 0x800F4284, 0x800F44FC).
WAITED_FADES = {0x800F4060, 0x800F4268, 0x800F44C0}
flight_OPS = {"xa_play": lambda x: {"op": "play_xa", "descriptor": x["args"][0] & 0xFFFF}, "camera_shake": lambda x: {"op": "camera_shake", "magnitude_raw": x["args"][1], "decay_raw": x["args"][2]},
	"face_init": lambda x: {"op": "player_face_init", "eye_table_ram": flight_H(x["args"][1]), "mouth_table_ram": flight_H(x["args"][2])}, "face_eyes": lambda x: {"op": "player_face", "channel": "eyes", "sequence": x["args"][1]}, "face_mouth": lambda x: {"op": "player_face", "channel": "mouth", "sequence": x["args"][1]},
	"face_eyes_frame": lambda x: {"op": "player_face_frame", "channel": "eyes", "frame": x["args"][1]}, "face_mouth_frame": lambda x: {"op": "player_face_frame", "channel": "mouth", "frame": x["args"][1]},
	"effect_0f": lambda x: {"op": "effect_spawn", "class": 0x0F, "pool": "effect (SLES0x8003E8F8)", "spawner": "ST3AT 0x800F4724", "entry_raw": x["entry"], "entry_ram": x["entry_ram"], "arg": x["arg"]},
	"actor_21": lambda x: {"op": "effect_spawn", "class": 0x21, "pool": "0x40 (SLES0x8003E73C)", "spawner": "ST3AT 0x800F47E4", "entry_raw": x["entry"], "entry_ram": x["entry_ram"]},
	"spawn_effect_8": lambda x: {"op": "effect_spawn", "class": 0x0F, "pool": "effect (SLES0x8003E8F8)", "spawner": "inline", "variant": 0x0A},
	"file_load": lambda x: {"op": "file_load", "file_id": x["args"][0], "native": "SLES0x8001B2D8(%#x)" % x["args"][0]}, "player_bank": lambda x: {"op": "player_bank_switch", "native": "scratch 0x1F80000C ^= 1; SLES0x80023040 (player+0x298 scene animation bank)"},
	"skip_lock": lambda x: {"op": "skip_lock", "set": x["value"]}, "player_render_flag": lambda x: {"op": "player_render_flag", "set": x["value"]}, "sound_latch": lambda x: {"op": "sound_latch", "value": x["value"]},
	"backdrop": lambda x: {"op": "scrolling_backdrop", "enabled": bool(x["value"][0]), "velocity_raw": list(x["value"][1:]), "offset_raw": x["offset_raw"], "texture": BACKDROP_FILE, "tpage": BACKDROP_TPAGE, "clut": BACKDROP_CLUT}}
flight_NEW_OPS = {"player_face_frame": {"params": "channel eyes|mouth, frame", "semantics": "SLES0x80041724/0x8004173C(ctx+0xB0, frame): stop that channel's face sequence and hold the fixed frame (writes player +0x1A0 eyes / +0x1A1 mouth)", "sources": ["0x800F29A0", "0x800F29AC", "0x800F4468", "0x800F44AC"]},
	"scrolling_backdrop": {"params": "enabled, velocity_raw[2] (s8 per tick), offset_raw[2]", "semantics": "ST3AT 0x800F4530 (called every tick while ctx+0x16 != 0): ctx+0x10/+0x12 += s8 ctx+0x14/+0x15; draws an 8x8 grid of 128x128 GP0 0x64 sprites (colour 0x808080, clut 0x7C80, v 0x80, u 0/0x80 alternating by row) at screen x = ((ctx+0x10 >> 4) & 0x7F) - 0x160 + col*0x80, y = ((ctx+0x12 >> 4) & 0xFF) - 0x188 + row*0x80 (culled outside x -0x80..0x140, y -0x80..0xF0), after a DR_MODE (SLES0x80063DD4(dfe 1, dtd 1, tpage 0x1B, no window): 4-bit page at VRAM (704,256)), linked at OT entry *(0x80078DDC)+0x88; every enable resets ctx+0x10/+0x12 to 0; the texture is page 0x1B with CLUT 0x7C80 (VRAM (0,498)), both uploaded by DAT/ST3AT.BIN section 0x1D000 (image 704,256 64x256, palette 0,498 128x1); texture = that 256x256 page (rows 0x80..0xFF used)", "sources": ["0x800F4530", "0x800F4560 (tpage)", "0x800F4668..0x800F466C (clut, v)", "0x800F4684..0x800F468C (u by row)", "0x800F2AD0..0x800F2AE0 (update, after the step callback)", "0x800F2A2C (init)", "0x800F2900..0x800F2918", "0x800F31A4..0x800F31C0", "0x800F3460..0x800F347C", "0x800F377C..0x800F3790"]},
	"effect_spawn": {"params": "class, entry_raw (s16 x,y,z, u16 flags), arg", "semantics": "ST3AT 0x800F4724 spawns effect class 0x0F (byte6 = 5, or 6 when flags bit 0x40; +0xC = arg; +0xD = 0x20; +0xE = flags bit7; +0xF = flags low nibble); 0x800F47E4 spawns pool-0x40 class 0x21 (ST3A_08800 model flags 0x2140) at the entry position with yaw 0x800; inline 0x800F3CCC spawns class 0x0F variant 0x0A every 4 ticks; class 0x0F visuals are not decoded", "sources": ["0x800F31E8", "0x800F32E4", "0x800F34FC", "0x800F35E0", "0x800F36EC", "0x800F380C", "0x800F3960", "0x800F396C", "0x800F3A3C", "0x800F3A54", "0x800F3CCC"]},
	"file_load / player_bank_switch": {"semantics": "SLES0x8001B2D8(0xFC / 0xFD) loads DAT/ST3A01.BIN / ST3A02.BIN (area 3 texture banks, tools/world.py AREA_TEXTURE_BANKS); 0x800F4228..0x800F423C toggles scratch 0x1F80000C and calls SLES0x80023040 so player controls 0x80.. resolve from the ST3A02 section-0 bank"},
	"player_render_flag / sound_latch / skip_lock / camera_shake / play_xa": {"semantics": "as tools/cinematics.py NEW_OPS; the sound latch is ctx+0x1A (finish plays 0x2A3 when set, 0x800F2B78..0x800F2B90)"}}

def actor_models(root, stage=flight_STAGE, archives=("ST3A_08800", "ST3A02_00000")):
	out = {}
	for archive in archives:
		manifest = json.loads((root / "assets/levels" / stage / "models" / archive / "manifest.json").read_text(encoding="utf-8"))
		for index, model in enumerate(manifest["models"]): out.setdefault(model["flags"], (archive, index, model))
	return out

def flight_actor_entry(rec, area, models, stage=flight_STAGE, variant_key=False):
	b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0; found = models.get((b[6] << 16 if variant_key else 0) | (b[4] << 8) | b[2])
	entry = {"stage": stage, "area": area, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9]}
	if found is None: return {"source_ram": rec["source_ram"], "native_slot": rec["slot"], "entry": entry, "model": None}
	archive, index, model = found; exp = model.get("export", {}); runtime = "assets/levels/%s/actors/%s/%s" % (stage, archive, Path(model["file"]).name); entry.update(model_index=index, model_file=runtime)
	return {"source_ram": rec["source_ram"], "native_slot": rec["slot"], "entry": entry, "model": {"file": runtime, "source_archive": archive, "source_model_index": index, "source_flags": model["flags"], **{k: exp[k] for k in ("mesh_offset", "texture_tpage", "texture_clut", "bone_count", "control_count", "face_count", "lod_counts", "native_scale_raw", "animations", "control_map", "source_materials", "source_surfaces", "face_dims") if k in exp}, "model_file": runtime, "model_index": index}, "source_file": model["file"]}

def copy_actor_models(root, out, actors):
	for item in actors:
		source = root / item.pop("source_file"); folder = out / "actors" / item["model"]["source_archive"]; folder.mkdir(parents=True, exist_ok=True)
		for path in source.parent.glob(source.stem + "*"):
			if path.suffix in (".glb", ".png"): write_output(folder / path.name, path.read_bytes())

def export_flight_scene(root=None, out_dir=None):
	import models as player_models, world
	root = Path(root or ROOT); flight_load(root); out = Path(out_dir or root / "assets/levels") / flight_STAGE; out.mkdir(parents=True, exist_ok=True)
	e, tracks, ticks = flight_emulate(); tl = fire_timeline(flight_TIMELINE); native = fire_commands(flight_CAMERA)
	if native[-1]["source_ram"] != flight_H(flight_TIMELINE - 4): raise ValueError("camera stream does not end at the timeline")
	models = actor_models(root); area_of = {}; current = 0
	for x in e.events:
		if x["kind"] == "request_block" and x["state"] == 1: current = bytes.fromhex(x["bytes"])[5]
		if x["kind"] == "spawn": area_of.setdefault(x["record"], current)
	order = []
	for c in native:
		if c["opcode"] == 0x40 and c["actor_record"]["source_ram"] not in order: order.append(c["actor_record"]["source_ram"])
	actors = []; slot_of = {}; omitted = []
	for address in order:
		item = flight_actor_entry(fire_record(int(address, 16)), area_of.get(address, 0), models)
		if item["model"] is None: omitted.append({"record": address, "class": item["entry"]["actor_class"], "pool": item["entry"]["pool_type"], "reason": "no exported model for this (class, pool); not representable by native_scene.gd"}); continue
		slot_of[address] = item["slot"] = len(actors); actors.append(item)
	copy_actor_models(root, out, actors)
	commands = []; occupant = {}; adaptations = []
	for c in native:
		item = dict(c); op = c["opcode"]
		if op in (0x40, 0x41):
			address = c["actor_record"]["source_ram"]; occupant[fire_record(int(address, 16))["slot"]] = address if op == 0x40 else None
			if address not in slot_of: adaptations.append({"source_ram": c["source_ram"], "action": "omitted", "reason": "record %s has no model" % address}); continue
		if op == 0x11:
			native_slot = (c["words"][0] >> 16) & 255; address = occupant.get(native_slot); item["target_record"] = address
			if address in slot_of: item["native_words"] = c["words"]; item["words"] = [(c["words"][0] & 0xFF00FFFF) | (slot_of[address] << 16)] + c["words"][1:]; adaptations.append({"source_ram": c["source_ram"], "action": "retargeted", "reason": "native slot %d -> runtime slot %d (%s)" % (native_slot, slot_of[address], address)})
			else: adaptations.append({"source_ram": c["source_ram"], "action": "kept", "reason": "relative-focus target slot %d holds %s (not spawned at runtime)" % (native_slot, address)})
		commands.append(item)
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_programs(scene_events, tl, {**fire_OPS, **flight_OPS})
	for operation in (operation for segment in (segments.values() if isinstance(segments, dict) else segments) for operation in segment.get("program", [])):
		if operation["op"] == "fade": operation["wait"] = int(operation["source"], 16) in WAITED_FADES
	for x in e.events:
		if x["kind"] != "move_local" or x.get("actor_slot") is not None or not x["args"][3]: continue
		motion = segments["%d:%d" % (x["phase"], x["step"])].setdefault("motion", []); velocity = [x["args"][1], x["args"][2], x["args"][3]]
		if motion and motion[-1]["velocity_raw"] == velocity and motion[-1]["through_tick"] == x["frame"] - 1: motion[-1]["through_tick"] = x["frame"]
		else: motion.append({"actor": "player", "from_tick": x["frame"], "through_tick": x["frame"], "velocity_raw": velocity, "source": "SLES0x800417AC(player, 0, 0, ctx+0x18) at %s" % x["caller"]})
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = slot_of.get(x["actor_slot"], x["actor_slot"])
	controllers = fire_controllers(e, {slot_of[k]: v for k, v in tracks.items() if k in slot_of}, {item["slot"]: item["source_ram"] for item in actors})
	for slot, profile in controllers.items():
		entry = actors[int(slot)]["entry"]; profile["source"] = "ST3AT class 0x%02X (pool 0x%02X) update emulated once per native tick after the scene update; render helpers stubbed" % (entry["actor_class"], entry["pool_type"])
	stage_request = fire_request(e.requests[-1]); K = fire_K
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"]) != (2, "ST08", 0, [K(0x800F2C4C, -0x580), K(0x800F2C54, -0x400), K(0x800F2C5C, 0x10)], K(0x800F2C64, 0xC00)): raise ValueError("finish request differs: %s" % stage_request)
	disc = root / "build/disc-assets"; payload = (disc / "COMMON/PL00P000.BIN").read_bytes()[0x30:]; face_word = struct.unpack_from("<4I", payload, 0x60)[2]
	vram, _ = player_models.textures(disc / "COMMON/PL00T.BIN"); world.texture_uploads(flight_D["ovl"], vram, "DAT/ST3AT.BIN"); world.write_output(out / "player_face_page1.png", player_models.texture_page(vram, face_word >> 16, (face_word & 0xFFFF) + 1)); world.write_output(out / BACKDROP_FILE, world.texture_page(vram, BACKDROP_CLUT, BACKDROP_TPAGE))
	bank = export_scene_player_clips("ST3A02", out, (0x0A,))
	scene = {"stage": flight_STAGE, "area": 0, "scene_id": flight_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_06_callbacks.json", "commands": commands, "native_commands": native, "command_adaptations": adaptations, "omitted_actors": omitted, "timeline": tl, "actors": actors,
		"player": {"scene_init": {"position_raw": [0, 0, 0], "source": "0x800F2980..0x800F2988 (player +0x10/+0x14/+0x18 = 0, +0xF4/+0x1A0/+0x1A1 = 0; yaw +0x2A not written)"}, "track": compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": face_table(0x800F6994, 4), "player_mouth": face_table(0x800F69E4, 2)},
		"emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc", "actor_free_3EA4C", "actor_free_3EB7C")]},
		"source": {"overlay": "DAT/ST3AT.BIN (load 0x800E7000, code size 0x%X)" % (flight_D["code_end"] - flight_BASE), "handler": "0x800F2840 (GAME table 0x800DC490[6])", "state_table": "0x800F69EC {0x800F287C init, 0x800F2A4C update, 0x800F2AF8 finish}", "command_pointer": flight_H(flight_CAMERA), "timeline_pointer": flight_H(flight_TIMELINE), "trigger": "per-frame 0x800E7574 (GAME table 0x800DC66C[0x3A])",
			"actor_tables": "*0x80078FA8 = 0x800F48A0 (pool 0x20), *0x80078DE0 = 0x800F4AB8 (pool 0x60), set by stage init 0x800E7328 (GAME table 0x800DBEA0[0x3A])", "voice_descriptors": "table 0 = 0x800F5238 (ids 0x16, 0x27, 0x30)", "player_bank": "DAT/ST3A02.BIN section 0 (type 0x0A) -> player_scene.json (%d clips)" % len(bank["clips"])}}
	finish_ops = [op for op in finish if op["op"] != "stage_request"]
	finish_ops.insert(next(i for i, op in enumerate(finish_ops) if op["op"] == "close_windows") + 1, {"op": "play_sound_if_latched", "id": K(0x800F2B8C, 0x2A3), "source": "0x800F2B78..0x800F2B90 (ctx+0x1A)"})
	contract = {"schema": 1, "stage": flight_STAGE, "scene_id": flight_SCENE_ID, "source": "ST3AT scene 6 handler 0x800F2840; timeline callbacks %s" % ", ".join(sorted({t["callback"] for t in tl})),
		"tick_basis": "tick = native ctx+0x28 of the step; program delays are the emulated substate counters (fades and XA reported idle immediately in emulation)",
		"initialization": {"player_position_raw": [0, 0, 0], "player_yaw_raw": 0, "player_yaw_unverified": True, "player_yaw_note": "native init does not write yaw (+0x2A)", "spawn_records": [], "init_ops": init, "source": "0x800F287C (GAME0x800C0C5C(0x800F5F7C, 0x800F6894) at 0x800F28D4)"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST3AT 0x800F2AF8", "fade_exit": 0x12, "fade_exit_source": "issued by phase 2 step 0 at tick 0x244 (0x800F44C0)", "ops": finish_ops,
			"skip_path": {"source": "0x800F2A8C..0x800F2ABC", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2", "note": "finish loads ST3A02 (SLES0x8001B2D8(0xFD), 0x800F2BF8) when ctx+0x17 is clear (skip before phase 1 step 11)"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800F2C34..0x800F2C88 request block 0x80078D08", "request_bytes": stage_request["bytes"]}},
		"xa": {"descriptor_index": 0x16, "table": "0x800F5238", "answers": []}, "new_ops": flight_NEW_OPS}
	world.write_output(out / "scene_06.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / "scene_06_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	triggers = {"stage": flight_STAGE, "triggers": [{"entry_area": 0, "native_save_byte14": 0, "scene_id": flight_SCENE_ID, "source_function": "GAME0x800C0B0C", "file": "scene_06.json",
		"source": "ST3AT per-frame 0x800E7574 (GAME table 0x800DC66C[0x3A]) starts scene 6 when area byte 0x8009C7F9 == 0 and latch 0x8009BE08 == 0, then sets the latch; 0x800E7544 (from area init 0x800E7414) clears the latch on every area load; no +0x14 or event-flag test (0 is the +0x14 value on arrival from ST1E)"}]}
	world.write_output(out / "scene_triggers.json", json.dumps(triggers, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "actors": len(actors), "omitted_actors": [o["record"] for o in omitted], "adaptations": len(adaptations), "transition": stage_request, "player_clips": len(bank["clips"]), "segments": len(segments)}

# ---- landing_scene ----
# Export the ST08 landing scene (scene 0x55, PAL): scene_55.json and scene_55_callbacks.json, from DAT/ST08T.BIN static tables and a
# unicorn emulation (tools/cinematics.py stage_emulator) of the unchanged area handler, scene handler and Flutter hull controller.
landing_STAGE = "ST08"; landing_BASE = 0x800E7000; landing_CTX = 0x8007CEC0; landing_PLAYER = 0x8008C0A0; landing_AREA_BYTE = 0x8009C7F9; landing_SCENARIO = 0x8009C7FC; landing_OWNER = 0x8009BE08
landing_SCENE_ID = 0x55; landing_HANDLER = 0x800F0718; landing_STATES = 0x800F55FC; landing_CAMERA = 0x800F55C0; landing_TIMELINE = 0x800F55EC; landing_PER_FRAME = 0x800E762C; landing_STAGE_INIT = 0x800E72DC; landing_AREA0 = 0x800E769C; HULL = 0x800F2670; XA = 0x62
landing_D = {}
def landing_H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def landing_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST08T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != landing_BASE: raise ValueError("unexpected ST08T header")
	landing_D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), st3a=(disc / "DAT/ST3AT.BIN").read_bytes(), code_end=landing_BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_D.update(ovl=ovl, game=landing_D["game"]); intro_SLES = landing_D["sles"]; intro_GAME = landing_D["game"]; intro_OVL = ovl; u32 = fire_u32
	game = lambda a: struct.unpack_from("<I", landing_D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + landing_SCENE_ID * 4), game(0x800DBEA0 + 8 * 4), game(0x800DC66C + 8 * 4)) != (landing_HANDLER, landing_STAGE_INIT, landing_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST08 scene 0x55")
	if [u32(landing_STATES + i * 4) for i in range(3)] != [0x800F0754, 0x800F08D4, 0x800F0AE4] or [u32(0x800F0894), u32(0x800F0898), u32(0x800F089C), u32(0x800F08A4)] != [0x3C04800F, 0x248455C0, 0x3C05800F, 0x24A555EC]: raise ValueError("scene 0x55 state/camera/timeline binding differs")
	if u32(u32(0x800F261C)) != landing_AREA0 or [u32(0x800E76E0), u32(0x800E76E4)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x24040055]: raise ValueError("ST08 area 0 handler does not request scene 0x55")

def landing_emulate():
	import unicorn
	e = stage_emulator(landing_STAGE_INIT, 0x800F22B8, landing_D["code_end"], ((0x800C0818, "spawn_table", 0, True, True),))()
	def table_spawn(uc, address, size, data): ptr = e.r(3); rec = e.r(17); e.actors[ptr] = landing_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=landing_H(rec), caller="GAME0x800C0874")
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, table_spawn, begin=0x800C0874, end=0x800C0874)
	e.w8(landing_AREA_BYTE, 0); e.w8(landing_SCENARIO, 0); e.cpu.mem_write(landing_OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(landing_PER_FRAME)
	entry = [x for x in e.events if x["kind"] in ("spawn", "flag_set", "scene_start")]
	if [(x["kind"], x.get("record", x.get("args", [0])[0])) for x in entry] != [("spawn", landing_H(HULL)), ("flag_set", 0x5E4), ("scene_start", landing_SCENE_ID)] or e.u32(landing_OWNER + 4) not in e.actors: raise RuntimeError("ST08 area 0 handler did not spawn the hull and start scene 0x55")
	e.events.clear(); hull = e.u32(landing_OWNER + 4)
	e.cpu.mem_write(landing_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(landing_PLAYER, e.u8(landing_PLAYER) | 2)
	tracks, ticks = run_scene(e, landing_HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(landing_CTX) & 0x20)), "scene_flag_04": (False, lambda e: bool(e.u8(landing_CTX) & 4)), "player_render_flag": (True, lambda e: bool(e.u8(landing_PLAYER) & 2)), "hull_fields": ((0, 0, 0), lambda e: (e.u8(hull + 0xA), e.u8(hull + 0xC), e.u8(hull + 0xD)))})
	scene = list(e.events); e.events.clear(); e.actors.clear(); e.call(landing_PER_FRAME); after = list(e.events)
	if any(x["kind"] == "scene_start" for x in after) or [(x["kind"], x["args"][0] & 0xFFFFFFFF, x["args"][1] if x["kind"] == "spawn_table" else None) for x in after if x["kind"] in ("flag_set", "spawn_table")] != [("flag_set", 0x711, None), ("spawn_table", HULL, 5)]: raise RuntimeError("ST08 area 0 handler second pass differs: %s" % [x["kind"] for x in after])
	e.events = scene; return e, tracks, ticks, entry, after

ST3A_ARRIVAL = (0x800F2C4C, 0x800F2C54, 0x800F2C5C, 0x800F2C64)
def arrival():
	words = [struct.unpack_from("<I", landing_D["st3a"], 0x30 + a - landing_BASE)[0] for a in ST3A_ARRIVAL]
	if any(w >> 26 != 9 for w in words): raise ValueError("ST3AT arrival immediates moved")
	return [struct.unpack("<h", struct.pack("<H", w & 0xFFFF))[0] for w in words[:3]], words[3] & 0xFFFF

landing_OPS = {"actor_free_3EA4C": lambda x: {"op": "despawn", "record": landing_H(HULL), "native": "SLES0x8003EA4C(ctx+0x2C)"}, "scene_flag_04": lambda x: {"op": "scene_flag", "mask": 4, "set": x["value"], "native": "ctx byte0 |= 4"},
	"hull_fields": lambda x: {"op": "actor_fields", "record": landing_H(HULL), "fields_raw": {"0x0A": x["value"][0], "0x0C": x["value"][1], "0x0D": x["value"][2]}}}
landing_NEW_OPS = {"actor_fields": {"params": "record, fields_raw {offset: u8}", "semantics": "scene writes to the hull actor: init 0x800F080C/0x800F0810 sets +0xC = 1, +0xD = 0; update sub 0 (0x800F0918..0x800F094C) sets +0xD = 0x40 and increments +0xA once the hull is within 0x200 of its landed height. ST08T class 0x30 variant 0 (0x800ED230) never reads them; 0x800ED318 (dust ring: 16 class-3 effects every 8 ticks while +0xD counts down) reads +0xD but has no caller or pointer in ST08T, and +0xD stays 0x40 in emulation", "sources": ["0x800F080C", "0x800F0810", "0x800F0944", "0x800F094C"]},
	"scene_flag": {"params": "mask, set", "semantics": "ctx byte0 |= 4 at 0x800F0A48 together with fade 0x12; not the skip gate (GAME0x800C10B4 tests ctx byte0 & 0x20); no reader found in GAME/SLES", "sources": ["0x800F0A40..0x800F0A50"]},
	"native_prop_actor": {"semantics": "the scene subject is the hull spawned by the area handler (GAME0x800C0818(0x800F2670, 1) at 0x800E76D0, slot pointer 0x8009BE0C, copied to ctx+0x2C at 0x800F07CC); camera 0x11 targets native slot 0 = ctx+0x2C. The runtime spawns its own copy (scene slot 0) while native_props.gd keeps NativeStaticActor_ST08_46752 (same record, landed transform) visible; the runtime should drive or hide that prop for the scene and free it at 0x800F0B88 semantics (SLES0x8003EA4C) until the stage reloads"}}

def export_landing_scene(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); landing_load(root); out = Path(out_dir or root / "assets/levels") / landing_STAGE; out.mkdir(parents=True, exist_ok=True)
	e, tracks, ticks, entry, after = landing_emulate(); tl = fire_timeline(landing_TIMELINE); native = fire_commands(landing_CAMERA)
	if native[-1]["source_ram"] != landing_H(landing_TIMELINE - 4) or [(t["phase"], t["step"], t["duration"], t["callback"]) for t in tl] != [(0, 0, -1, "0x0")]: raise ValueError("scene 0x55 camera/timeline layout differs")
	if any(x["kind"] == "message" for x in e.events): raise ValueError("scene 0x55 uses messages; bind the ST08 bank")
	scripted = json.loads((root / "assets/levels" / landing_STAGE / "scripted_actors.json").read_text(encoding="utf-8")); instance = next(i for i in scripted["instances"] if i["spawn_set"] == "flutter_hull_first_visit" and i["source_record_ram"] == landing_H(HULL))
	model = dict(next(m for m in scripted["models"] if m["model_index"] == instance["model_index"])); model.pop("file", None)
	rec = fire_record(HULL); x, y, z = rec["position_raw"]; y += fire_K(0x800F07F4, -0x400); z += fire_K(0x800F0814, 0x80)
	b = bytes.fromhex(rec["bytes_hex"]); turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	hull = {"source_ram": landing_H(HULL), "slot": 0, "native_slot": rec["slot"], "class_note": "Flutter hull (class 0x30, pool 0x20; controller ST08T 0x800ED230); native_props instance %s file offset %d" % (instance["spawn_set"], instance["file_offset"]),
		"entry": {"stage": landing_STAGE, "area": 0, "source_record_ram": landing_H(HULL), "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "record_position_raw": rec["position_raw"], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "position_note": "record position after scene init (0x800F07F4: y -= 0x400; 0x800F0814: z += 0x80)", "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": instance["model_index"], "model_file": instance["model_file"]},
		"model": model}
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = 0 if x["actor_slot"] == landing_H(HULL) else x["actor_slot"]
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_programs(scene_events, tl, {**fire_OPS, **flight_OPS, **landing_OPS})
	opening = next(op for op in init if op["op"] == "fade"); init.remove(opening); program = segments["0:0"]["program"]
	program.insert(0, dict(opening, wait=False, note="issued at the end of init (state 0 sub 3) with GAME0x800C0C5C; SLES0x8001392C only starts it and the update never waits; native_scene.gd init_ops ignore fades, so it opens segment 0:0"))
	exit_fade = next(i for i, op in enumerate(program) if op["op"] == "fade" and op["type"] == 0x12); flag = next(i for i, op in enumerate(program) if op["op"] == "scene_flag")
	if [op["op"] for op in program[exit_fade:]] != ["fade", "delay", "scene_flag", "advance"] or program[exit_fade + 1]["ticks"] != 1: raise ValueError("scene 0x55 sub 4/5 layout differs")
	program[exit_fade:] = [dict(program[flag], note="same native tick as the fade (0x800F0A38..0x800F0A50)"), dict(program[exit_fade], wait=True, wait_source="sub 5 (0x800F0A64..0x800F0A7C) waits 0x80078F01 == 0"), {"op": "finish", "source": "0x800F0A78 (ctx+4 = 2); the timeline step is never advanced"}]
	finish_ops = [op for op in finish if op["op"] != "stage_request"]; finish_ops.insert(next(i for i, op in enumerate(finish_ops) if op["op"] == "xa_fade_out") + 1, {"op": "wait_xa_idle", "source": "0x800F0B64..0x800F0B80 (SLES0x8001AFD0 and 0x80078F01 == 0)"})
	stage_request = fire_request(e.requests[-1]); K = fire_K
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"], stage_request["fade_arrival"], stage_request["fade_exit"]) != (2, "ST04", 0, [0, -1, 0], 0, K(0x800F0B9C, 2), K(0x800F0BB0, 0xFF)): raise ValueError("finish request differs: %s" % stage_request)
	controllers = fire_controllers(e, {0: tracks[landing_H(HULL)]}, {0: landing_H(HULL)}); controllers["0"]["source"] = "ST08T class 0x30 variant 0 (0x800ED230) emulated once per native tick after the scene update; position driven by the scene's SLES0x800417AC(hull, 0, +0x3A, +0x3C) at 0x800F0A8C"
	position, facing = arrival(); xa_entry = None; audio_path = root / "assets/levels" / landing_STAGE / "audio/manifest.json"
	if audio_path.is_file(): xa_entry = next((item for item in json.loads(audio_path.read_text(encoding="utf-8"))["entries"] if int(item["id"]) == XA), None)
	if xa_entry is None: raise ValueError("ST08 audio manifest lacks XA id %#x; run audio.export_stage_voices(cue, 'ST08')" % XA)
	commands = [dict(c, target_record=landing_H(HULL), note="native slot 0 = ctx+0x2C = hull (0x800F07CC); runtime slot 0") if c["opcode"] == 0x11 else c for c in native]
	scene = {"stage": landing_STAGE, "area": 0, "scene_id": landing_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_55_callbacks.json", "commands": commands, "timeline": tl, "actors": [hull],
		"player": {"hidden": True, "track": compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)}, "face_tables": {},
		"emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "trigger_events": entry, "second_area_pass_events": after, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc")]},
		"source": {"overlay": "DAT/ST08T.BIN (load 0x800E7000, code size 0x%X)" % (landing_D["code_end"] - landing_BASE), "handler": "0x800F0718 (GAME table 0x800DC490[0x55])", "state_table": "0x800F55FC {0x800F0754 init, 0x800F08D4 update (sub table 0x800E71D4), 0x800F0AE4 finish}", "command_pointer": landing_H(landing_CAMERA), "timeline_pointer": landing_H(landing_TIMELINE),
			"trigger": "area handler 0x800E769C (table 0x800F261C[byte14 0][area 0], per-frame 0x800E762C = GAME table 0x800DC66C[8]): state byte 0x8009BE08 == 0 and flag 0x5E4 clear -> GAME0x800C0818(0x800F2670, 1), flag_set 0x5E4, GAME0x800C0B0C(0x55)",
			"actor_tables": "*0x80078FA8 = 0x800F1BA0 (pool 0x20) set by stage init 0x800E72DC (GAME table 0x800DBEA0[8])", "voice_descriptors": "table 0 = *0x80078DD8 = 0x800F22AC (id 0x62 = %s)" % xa_entry["descriptor_ram"]}}
	contract = {"schema": 1, "stage": landing_STAGE, "scene_id": landing_SCENE_ID, "source": "ST08T scene 0x55 handler 0x800F0718; timeline 0x800F55EC has one entry (phase 0 step 0, duration -1, no callback), the update runs its own sub-state machine",
		"tick_basis": "tick = native ctx+0x28 (GAME0x800C0D70); program delays are the emulated sub-state counters (fades and XA reported idle immediately in emulation)",
		"initialization": {"player_keep_transform": True, "suppress_props": [{"spawn_set": "flutter_hull_revisit_group", "identity": "Flutter hull"}], "suppress_note": "native spawns only the scene hull here (0x800E76C4: flag 0x5E4 clear); the revisit group (0x800E7710) is gated on 0x5E4, which the port evaluates in the same pass, so hide its landed hull for the scene", "player_position_raw": position, "player_yaw_raw": facing, "player_note": "scene 0x55 never writes the player transform; this is the ST3A scene 6 arrival request (ST3AT 0x800F2C4C..0x800F2C64); the player is hidden for the whole scene", "spawn_records": [landing_H(HULL)], "init_ops": init,
			"source": "0x800F07AC..0x800F08BC: GAME0x800C1148; player byte0 &= ~2; ctx+0x2C = *(0x8009BE0C); ctx+0xC/+0xE = hull y/z; hull +0x3A = 0x100, +0x42 = -0x10, y -= 0x400, z += 0x80; wait !(0x80078DBA & 1) -> SLES0x8001B714(0x62); wait !(0x80078DBA & 2) -> SLES0x8001B864(0x62); wait SLES0x8001AF94 -> GAME0x800C0C5C(0x800F55C0, 0x800F55EC), GAME0x800C0D70, SLES0x8001392C(2, 0), state 1"},
		"segments": segments, "actor_controllers": controllers,
		"update": {"source": "0x800F08D4 (sub table 0x800E71D4); every tick SLES0x800417AC(hull, 0, +0x3A, +0x3C), skip check, GAME0x800C0D70", "subs": ["0 (0x800F0918): descend at +0x3A = 0x100 until y >= target - 0x100 (+0xD = 0x40 at target - 0x200)", "1 (0x800F0974): +0x3A += -0x10 per tick down to 0x20", "2 (0x800F09B0): descend until y >= target, snap, +0x3C = -0x20", "3 (0x800F09EC): slide z until <= target, snap, ctx+0x1C = 0", "4 (0x800F0A24): after 0x1E ticks fade 0x12 and ctx byte0 |= 4", "5 (0x800F0A64): wait 0x80078F01 == 0, state 2"]},
		"finish": {"source": "ST08T 0x800F0AE4", "fade_exit": 0x12, "fade_exit_source": "issued by update sub 4 (0x800F0A38)", "ops": finish_ops,
			"skip_path": {"source": "0x800F0A94..0x800F0AC4", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0 (never locked: the scene does not set ctx byte0 & 0x20)", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800C11F0", "SLES0x8001B7E8(-1)", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800F0B9C..0x800F0BD8 request block 0x80078D08 (y -1 = floor height); 0x800F0BF0 waits until it is consumed, then flag 0x780", "request_bytes": stage_request["bytes"]}},
		"xa": {"descriptor_index": XA, "table": "0x800F22AC", "answers": []}, "new_ops": landing_NEW_OPS}
	world.write_output(out / "scene_55.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / "scene_55_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "transition": stage_request, "xa": xa_entry["file"], "program": [op["op"] for op in program], "finish": [op["op"] for op in finish_ops], "init": [op["op"] for op in init]}

# ---- flutter_scene ----
# Export the ST04 Flutter first-visit scene (scene 0x4C, PAL): scene_4c.json, scene_4c_callbacks.json and the scene actor models, from DAT/ST04T.BIN
# static tables and a unicorn emulation (tools/cinematics.py stage_emulator); the trigger is scripted_actors.json spawn set flutter_first_visit_scene.
flutter_STAGE = "ST04"; flutter_BASE = 0x800E7000; flutter_CTX = 0x8007CEC0; flutter_PLAYER = 0x8008C0A0; flutter_AREA_BYTE = 0x8009C7F9; flutter_SCENARIO = 0x8009C7FC; flutter_OWNER = 0x8009BE08
flutter_SCENE_ID = 0x4C; flutter_HANDLER = 0x800E7CA0; flutter_STATES = 0x800F000C; flutter_CAMERA = 0x800EFF04; flutter_TIMELINE = 0x800EFFA4; flutter_PER_FRAME = 0x800E77B0; flutter_STAGE_INIT = 0x800E73C4; flutter_AREA0 = 0x800E7B10; flutter_EYES = 0x800EFFFC; flutter_MOUTH = 0x800F0004
ENTRY_FLAGS = (0x5F0, 0xD0, 0xD1, 0xD2)
flutter_D = {}
def flutter_H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def flutter_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST04T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != flutter_BASE: raise ValueError("unexpected ST04T header")
	flutter_D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), st08=(disc / "DAT/ST08T.BIN").read_bytes(), code_end=flutter_BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_D.update(ovl=ovl, game=flutter_D["game"]); intro_SLES = flutter_D["sles"]; intro_GAME = flutter_D["game"]; intro_OVL = ovl; u32 = fire_u32
	game = lambda a: struct.unpack_from("<I", flutter_D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + flutter_SCENE_ID * 4), game(0x800DBEA0 + 4 * 4), game(0x800DC66C + 4 * 4)) != (flutter_HANDLER, flutter_STAGE_INIT, flutter_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST04 scene 0x4C")
	if [u32(flutter_STATES + i * 4) for i in range(3)] != [0x800E7CDC, 0x800E7DC4, 0x800E7E58] or [u32(0x800E7D10), u32(0x800E7D14), u32(0x800E7D18), u32(0x800E7D20)] != [0x3C04800F, 0x2484FF04, 0x3C05800F, 0x24A5FFA4]: raise ValueError("scene 0x4C state/camera/timeline binding differs")
	if u32(u32(0x800EFE4C)) != flutter_AREA0 or [u32(0x800E7B50), u32(0x800E7B54)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x2404004C]: raise ValueError("ST04 area 0 handler does not request scene 0x4C")
	if [u32(0x800E7D6C), u32(0x800E7D70), u32(0x800E7D74), u32(0x800E7D7C)] != [0x3C05800F, 0x24A5FFFC, 0x3C06800F, 0x24C60004]: raise ValueError("scene 0x4C face tables moved")

def flutter_emulate():
	import unicorn
	e = stage_emulator(flutter_STAGE_INIT, 0x800F22B8, flutter_D["code_end"])()
	e.w8(flutter_AREA_BYTE, 0); e.w8(flutter_SCENARIO, 0); e.cpu.mem_write(flutter_OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(flutter_PER_FRAME)
	entry = [x for x in e.events if x["kind"] in ("flag_set", "scene_start")]
	if [(x["kind"], x["args"][0]) for x in entry] != [("flag_set", f) for f in ENTRY_FLAGS] + [("scene_start", flutter_SCENE_ID)]: raise RuntimeError("ST04 area 0 handler did not set the entry flags and start scene 0x4C")
	e.events.clear(); e.call(flutter_PER_FRAME); again = list(e.events)
	if any(x["kind"] == "scene_start" for x in again): raise RuntimeError("ST04 area 0 handler restarted scene 0x4C with flag 0x5F0 set")
	e.events.clear()
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = flutter_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=flutter_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(flutter_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(flutter_PLAYER, e.u8(flutter_PLAYER) | 2)
	tracks, ticks = run_scene(e, flutter_HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(flutter_CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(flutter_PLAYER) & 2))})
	return e, tracks, ticks, entry, again

def export_flutter_scene(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); flutter_load(root); out = Path(out_dir or root / "assets/levels") / flutter_STAGE; out.mkdir(parents=True, exist_ok=True); K = fire_K
	e, tracks, ticks, entry, again = flutter_emulate(); tl = fire_timeline(flutter_TIMELINE); native = fire_commands(flutter_CAMERA)
	if native[-1]["source_ram"] != flutter_H(flutter_TIMELINE) or [(t["phase"], t["step"], t["duration"]) for t in tl] != [(0, 0, -1), (0, 1, -1), (0, 2, -1)]: raise ValueError("scene 0x4C camera/timeline layout differs")
	messages = [x for x in e.events if x["kind"] == "message"]
	if [(x["bank"], x["index"]) for x in messages] != [("0x8010c000", 0xC9), ("0x8010c000", 0xCA), ("0x8010c000", 0xCB)]: raise ValueError("scene 0x4C messages differ")
	bank = json.loads((root / "assets/dialogue" / json.loads((root / "assets/dialogue/manifest.json").read_text(encoding="utf-8"))["banks"][flutter_STAGE]["file"]).read_text(encoding="utf-8"))
	if any(not bank["messages"][i]["display_ready"] for i in (0xC9, 0xCA, 0xCB, 0xCC)): raise ValueError("ST04 dialogue bank does not resolve messages 0xC9..0xCC")
	models = actor_models(root, flutter_STAGE, ("ST04_06800",)); actors = []; slot_of = {}
	for c in native:
		if c["opcode"] != 0x40: continue
		item = flight_actor_entry(fire_record(int(c["actor_record"]["source_ram"], 16)), 0, models, flutter_STAGE, True)
		if item["model"] is None: raise ValueError("no model for record %s" % item["source_ram"])
		slot_of[item["source_ram"]] = item["slot"] = len(actors); actors.append(item)
	copy_actor_models(root, out, actors)
	for x in e.events:
		if x.get("actor_slot") is not None: x["actor_slot"] = slot_of.get(x["actor_slot"], x["actor_slot"])
	scene_events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("xa_prepare", "move_local")]
	segments, init, finish = fire_programs(scene_events, tl, {**fire_OPS, **flight_OPS})
	step1 = segments["0:1"]["program"]
	if [op["op"] for op in step1] != ["delay", "message", "delay", "advance"] or step1[0]["ticks"] != K(0x800E8074, 0x14) or step1[1]["index"] != 0xCA: raise ValueError("scene 0x4C step 1 layout differs")
	step1[2] = {"op": "minimum_tick", "tick": K(0x800E80E0, 0x50), "source": "0x800E80D8..0x800E80F4 (ctx+0x28 >= 0x50 and SLES0x800489A0(1) idle)"}
	trigger = next((t for t in json.loads((root / "assets/levels" / flutter_STAGE / "scripted_actors.json").read_text(encoding="utf-8"))["spawn_sets"] if t["id"] == "flutter_first_visit_scene"), None)
	if trigger is None or trigger["source"]["native_side_effects"] != [{"kind": "set_event_flag", "id": f} for f in ENTRY_FLAGS] + [{"kind": "call", "function": "GAME.BIN 0x800C0B0C", "argument": flutter_SCENE_ID}]: raise ValueError("ST04 scripted_actors.json lacks the flutter_first_visit_scene trigger (tools/models.py export_flutter_scripted_actors)")
	finish_ops = [op for op in finish if op["op"] not in ("stage_request", "fade")]; close = next((index for index, op in enumerate(finish_ops) if op["op"] == "close_windows"), len(finish_ops))
	finish_ops.append({"op": "player_special_usable", "value": 0, "source": "ST04T 0x800E7FAC sb zero, player+0x19F; GAME0x800CF4D8 only activates the equipped special (+0x18E) while +0x19F != 0"})
	finish_ops.insert(close, {"op": "fade", "type": K(0x800E7EF8, 0x12), "wait": True, "source": "0x800E7EF8 (skipped when ctx byte0 & 0x10), waited at 0x800E7F04 before close_windows/pool_clear"})
	stage_request = fire_request(e.requests[-1])
	if (stage_request["type"], stage_request["stage"], stage_request["area"], stage_request["position_raw"], stage_request["facing_raw"], stage_request["fade_arrival"], stage_request["fade_exit"]) != (2, "ST08", 0, [K(0x800E7F44, 0x40), 0, 0], K(0x800E7F4C, 0x800), K(0x800E7F5C, 3), K(0x800E7F54, 0xFF)): raise ValueError("finish request differs: %s" % stage_request)
	arrival = struct.unpack_from("<I", flutter_D["st08"], 0x30 + 0x800F0BA8 - flutter_BASE)[0]
	if arrival != 0x2402FFFF: raise ValueError("ST08 scene 0x55 arrival y immediate moved")
	controllers = fire_controllers(e, {slot_of[k]: v for k, v in tracks.items() if k in slot_of}, {item["slot"]: item["source_ram"] for item in actors})
	for slot, profile in controllers.items():
		item = actors[int(slot)]; entry_data = item["entry"]; profile["source"] = "ST04T class 0x%02X variant %d (pool 0x%02X) emulated once per native tick after the scene update; render helpers stubbed" % (entry_data["actor_class"], entry_data["actor_state"], entry_data["pool_type"])
		profile.setdefault("startup_control", entry_data["control"])
	segments["0:1"]["camera_offset_raw"] = [-524, 0, 0]; controllers["1"]["render_offset_by_step"] = {"1": [-524, 0, 0]}
	segments["0:1"]["visible_actor_slots"] = [1]; segments["0:1"]["player_visible"] = False
	scene = {"stage": flutter_STAGE, "area": 0, "scene_id": flutter_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4c_callbacks.json", "commands": native, "timeline": tl, "actors": actors,
		"player": {"track": compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": face_table(flutter_EYES, 2), "player_mouth": face_table(flutter_MOUTH, 2)},
		"emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "trigger_events": entry, "second_area_pass_events": again, "events": [{k: v for k, v in x.items() if k != "sub7"} for x in e.events if x["kind"] not in ("move_local", "released", "alloc", "face_tick")]},
		"source": {"overlay": "DAT/ST04T.BIN (load 0x800E7000, code size 0x%X)" % (flutter_D["code_end"] - flutter_BASE), "handler": "0x800E7CA0 (GAME table 0x800DC490[0x4C])", "state_table": "0x800F000C {0x800E7CDC init, 0x800E7DC4 update, 0x800E7E58 finish}", "command_pointer": flutter_H(flutter_CAMERA), "timeline_pointer": flutter_H(flutter_TIMELINE),
			"trigger": "area handler 0x800E7B10 (table 0x800EFE4C[byte14 0] = 0x800EFE28[area 0], per-frame 0x800E77B0 = GAME table 0x800DC66C[4]): flag 0x5F0 clear -> flag_set 0x5F0, 0xD0, 0xD1, 0xD2, GAME0x800C0B0C(0x4C); otherwise 0x800E7828",
			"actor_tables": "*0x80078FA8 = 0x800EF7F0 (pool 0x20), *0x80078DE0 = 0x800EF990 (pool 0x60) set by stage init 0x800E73C4 (GAME table 0x800DBEA0[4])", "messages": "bank 0x8010C000 (assets/dialogue/manifest.json banks['ST04']): 0xC9, 0xCA, 0xCB (redirects to 0xCC); 0xC9/0xCB/0xCC set flag 0x5E3 (opcode 0x26)", "voices": "stage init clears *0x80078DD8/*0x80078DD4: ST04 has no XA voice tables"}}
	contract = {"schema": 1, "stage": flutter_STAGE, "scene_id": flutter_SCENE_ID, "source": "ST04T scene 0x4C handler 0x800E7CA0; timeline callbacks %s" % ", ".join(t["callback"] for t in tl),
		"tick_basis": "tick = native ctx+0x28 of the step (GAME0x800C0D70); program delays are the emulated sub-state counters (messages and fades reported idle immediately in emulation)",
		"initialization": {"player_keep_transform": True, "suppress_props": [{"spawn_set": "revisit_byte14_0_roll_data"}], "suppress_note": "the first-visit side effects set 0x5F0, which enables revisit_byte14_0_roll_data on the runtime re-evaluation; natively GAME0x800C042C skips the stage per-frame handler while a scene is active (ctx byte0 != 0), so 0x800E7828 does not run before the scene leaves ST04", "player_position_raw": [0, -1, 0], "player_yaw_raw": 0, "player_note": "scene 0x4C never writes the player transform; this is the ST08 scene 0x55 arrival request (ST08T 0x800F0B9C..0x800F0BD8, y -1 = floor height), so the runtime should keep the arrival transform", "spawn_records": [], "init_ops": init,
			"source": "0x800E7CDC: GAME0x800C0C5C(0x800EFF04, 0x800EFFA4); GAME0x800C1148; player +0xEE/+0xEF/+0xF0/+0xF4 = 0; SLES0x80015A5C(ctx+0xC, ctx+0x18); wait GAME0x800CDD50 == 0; SLES0x80041318(ctx+0xB0, 0x800EFFFC, 0x800F0004); eyes 0, mouth 0; state 1. No fade: the screen is revealed by the arrival fade 2 of the ST08 request"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST04T 0x800E7E58 (called directly by step 2 0x800E8178)", "ops": finish_ops,
			"skip_path": {"source": "0x800E7E04..0x800E7E34", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "player +0x19F = 0", "GAME0x800C0F58"], "player_render_flag": True,
			"transition": {"destination_stage": stage_request["stage"], "destination_area": stage_request["area"], "destination_transform_raw": stage_request["position_raw"] + [stage_request["facing_raw"]], "native_transition_mode": stage_request["type"], "native_entry_fade": stage_request["fade_arrival"], "native_exit_fade": stage_request["fade_exit"], "source": "0x800E7F2C..0x800E7F7C request block 0x80078D08; 0x800E7F80 waits until it is consumed", "request_bytes": stage_request["bytes"]}},
		"new_ops": {"player_keep_transform": {"semantics": "the scene does not position the player; initialization.player_position_raw is the arrival transform for reference only"}}}
	world.write_output(out / "scene_4c.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / "scene_4c_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "transition": stage_request, "actors": [(a["source_ram"], a["entry"]["model_file"]) for a in actors], "segments": {k: [op["op"] for op in v["program"]] for k, v in segments.items()}, "init": [op["op"] for op in init], "finish": [op["op"] for op in finish_ops]}

# ---- yosyonke_scene ----
# Export the ST09 Yosyonke return scene (scene 0x4E, PAL): scene_4e.json and scene_4e_callbacks.json, from DAT/ST09T.BIN static tables and a
# unicorn emulation (tools/cinematics.py stage_emulator); the trigger is the ST09 scripted_actors.json call action of area handler 0x800E7480.
yosyonke_STAGE = "ST09"; yosyonke_BASE = 0x800E7000; yosyonke_CTX = 0x8007CEC0; yosyonke_PLAYER = 0x8008C0A0; yosyonke_AREA_BYTE = 0x8009C7F9; yosyonke_SCENARIO = 0x8009C7FC; yosyonke_OWNER = 0x8009BE08
yosyonke_SCENE_ID = 0x4E; yosyonke_HANDLER = 0x800E7884; yosyonke_STATES = 0x800F262C; yosyonke_CAMERA = 0x800F2588; yosyonke_TIMELINE = 0x800F25D4; yosyonke_PER_FRAME = 0x800E7410; yosyonke_STAGE_INIT = 0x800E7188; yosyonke_AREA0 = 0x800E7480; WALKER = 0x800F2574; WALKER_HITBOX = 0x800F2AAC; TOWNSFOLK = 0x800F2354; yosyonke_EYES = 0x800F261C; yosyonke_MOUTH = 0x800F2624
yosyonke_D = {}
def yosyonke_H(v): return "0x%08x" % (v & 0xFFFFFFFF)
def yosyonke_load(root):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; ovl = (disc / "DAT/ST09T.BIN").read_bytes()
	if struct.unpack_from("<4I", ovl, 0)[0] != 1 or struct.unpack_from("<I", ovl, 12)[0] != yosyonke_BASE: raise ValueError("unexpected ST09T header")
	yosyonke_D.update(root=Path(root), disc=disc, ovl=ovl, game=(disc / "COMMON/GAME.BIN").read_bytes(), sles=(disc / "SLES_035.56").read_bytes(), code_end=yosyonke_BASE + struct.unpack_from("<I", ovl, 4)[0])
	fire_D.update(ovl=ovl, game=yosyonke_D["game"]); intro_SLES = yosyonke_D["sles"]; intro_GAME = yosyonke_D["game"]; intro_OVL = ovl; u32 = fire_u32
	game = lambda a: struct.unpack_from("<I", yosyonke_D["game"], 0x30 + a - 0x800AD000)[0]
	if (game(0x800DC490 + yosyonke_SCENE_ID * 4), game(0x800DBEA0 + 9 * 4), game(0x800DC66C + 9 * 4)) != (yosyonke_HANDLER, yosyonke_STAGE_INIT, yosyonke_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST09 scene 0x4E")
	if [u32(yosyonke_STATES + i * 4) for i in range(3)] != [0x800E78C0, 0x800E79A8, 0x800E7AE4] or [u32(0x800E78F4), u32(0x800E78F8), u32(0x800E78FC), u32(0x800E7904)] != [0x3C04800F, 0x24842588, 0x3C05800F, 0x24A525D4]: raise ValueError("scene 0x4E state/camera/timeline binding differs")
	if u32(u32(0x800F2300)) != yosyonke_AREA0 or [u32(0x800E74CC), u32(0x800E74D0)] != [0x0C000000 | (0x800C0B0C >> 2 & 0x3FFFFFF), 0x2404004E]: raise ValueError("ST09 area 0 handler does not request scene 0x4E")
	if [u32(0x800E7950), u32(0x800E7954), u32(0x800E7958), u32(0x800E7960)] != [0x3C05800F, 0x24A5261C, 0x3C06800F, 0x24C62624]: raise ValueError("scene 0x4E face tables moved")

def yosyonke_emulate():
	import unicorn
	e = stage_emulator(yosyonke_STAGE_INIT, 0x800F22B8, yosyonke_D["code_end"])(); passes = {}
	for name, flags in (("first_visit", ()), ("after_junk_shop", (0x5C1,)), ("revisit", (0x5C1, 0x5C2))):
		e.events.clear(); e.cpu.mem_write(0x98538, bytes(0x100)); e.init_flags(flags); e.w8(yosyonke_AREA_BYTE, 0); e.w8(yosyonke_SCENARIO, 0); e.cpu.mem_write(yosyonke_OWNER & 0x1FFFFFFF, bytes(0x88)); e.call(yosyonke_PER_FRAME)
		passes[name] = [{"kind": x["kind"], "args": [x["args"][0] & 0xFFFFFFFF, x["args"][1]] if x["kind"] == "spawn_table" else [x["args"][0]]} for x in e.events if x["kind"] in ("flag_set", "flag_clear", "scene_start", "spawn_table")]
		e.events.clear(); e.call(yosyonke_PER_FRAME)
		if any(x["kind"] in ("scene_start", "spawn_table", "flag_set") for x in e.events): raise RuntimeError("ST09 area 0 handler ran twice without an area load (%s)" % name)
	expected = {"first_visit": [("flag_set", [0x711])], "after_junk_shop": [("spawn_table", [TOWNSFOLK, 2]), ("scene_start", [yosyonke_SCENE_ID]), ("flag_set", [0x5C2]), ("flag_set", [0x711])], "revisit": [("spawn_table", [TOWNSFOLK, 2]), ("flag_set", [0x711])]}
	if {k: [(x["kind"], x["args"]) for x in v] for k, v in passes.items()} != expected: raise RuntimeError("ST09 area 0 handler passes differ: %s" % passes)
	e.events.clear(); e.cpu.mem_write(0x98538, bytes(0x100)); e.init_flags((0x5C1, 0x5C2))
	def spawn_hook(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = yosyonke_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", slot=e.u8(rec + 1), record=yosyonke_H(rec))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn_hook, begin=0x800C1040, end=0x800C1040)
	e.cpu.mem_write(yosyonke_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(yosyonke_PLAYER, e.u8(yosyonke_PLAYER) | 2); s16 = lambda v: v - 0x10000 if v & 0x8000 else v
	tracks, ticks = run_scene(e, yosyonke_HANDLER, {"skip_lock": (False, lambda e: bool(e.u8(yosyonke_CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(yosyonke_PLAYER) & 2)), "head": ((0, 0), lambda e: (e.u16(yosyonke_CTX + 0x10), s16(e.u16(yosyonke_CTX + 0x14))))})
	for x in e.events:
		if x["kind"] == "head": x["frame"] -= 1; x["head_source"] = "ctx+0x10/+0x14 written by the step callback at ctx+0x28 = frame (sampled after the scene call)"
	return e, tracks, ticks, passes

yosyonke_OPS = {"head": lambda x: {"op": "head_target", "target": x["value"][0], "speed": x["value"][1]}, "despawn": lambda x: {"op": "despawn", "record": x["record"], "native": "GAME0x800C1058(0x800F2574)"}}

def export_yosyonke_scene(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); yosyonke_load(root); out = Path(out_dir or root / "assets/levels") / yosyonke_STAGE; out.mkdir(parents=True, exist_ok=True); K = fire_K
	e, tracks, ticks, passes = yosyonke_emulate(); tl = fire_timeline(yosyonke_TIMELINE); native = fire_commands(yosyonke_CAMERA)
	if native[-1]["source_ram"] != yosyonke_H(yosyonke_TIMELINE) or [(t["phase"], t["step"], t["duration"], t["callback"]) for t in tl] != [(0, 0, -1, "0x800e7be4")]: raise ValueError("scene 0x4E camera/timeline layout differs")
	if [c["actor_record"]["source_ram"] for c in native if c["opcode"] == 0x40] != [yosyonke_H(WALKER)] or any(c["opcode"] == 0x41 for c in native): raise ValueError("scene 0x4E actor commands differ")
	if any(x["kind"] in ("message", "xa_play", "xa_prepare", "stage_request", "request_block") for x in e.events): raise ValueError("scene 0x4E now uses messages, XA or a stage request; bind them")
	scripted = json.loads((root / "assets/levels" / yosyonke_STAGE / "scripted_actors.json").read_text(encoding="utf-8")); call = {"kind": "call", "function": "GAME.BIN 0x800c0b0c", "argument": yosyonke_SCENE_ID}
	trigger = [s for s in scripted["spawn_sets"] if any({k: a.get(k) for k in ("kind", "function", "argument")} == call for a in s["source"].get("native_side_effects", []))]
	if len(trigger) != 1 or {(c["id"], c["set"]) for c in trigger[0]["predicate"]["all"] if c["kind"] == "native_event_flag"} != {(0x5C1, True), (0x5C2, False)} or not {"kind": "stage_state_byte_equals", "value": 0} in trigger[0]["predicate"]["all"]: raise ValueError("ST09 scripted_actors.json lacks the area 0 scene 0x4E call (tools/models.py export_interior_scripted_actors)")
	model = dict(next(m for m in scripted["models"] if m.get("model_index") == 1 and m.get("native_resource_flags") == 0x100020)); model.pop("file", None)
	rec = fire_record(WALKER); b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; turns = -(rec["yaw_raw"] / 4096.0); turns += 1.0 if turns < -0.5 else 0.0
	if b[2] | b[4] << 8 | b[6] << 16 != model["native_resource_flags"]: raise ValueError("walker record resource differs from ST09 model 1")
	walker = {"source_ram": yosyonke_H(WALKER), "slot": 0, "native_slot": rec["slot"], "class_note": "townsperson (pool 0x20 class 0 variant 2, ST09T class table *0x80078FA8 = 0x800F1A70)",
		"entry": {"stage": yosyonke_STAGE, "area": 0, "source_record_ram": yosyonke_H(WALKER), "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": turns, "control": b[8], "frame": b[9], "model_index": 1, "model_file": model["model_file"],
		"native_hitbox": {"bounds_raw": [fire_s16(WALKER_HITBOX + i * 2) for i in range(6)], "source_pointer_ram": yosyonke_H(WALKER_HITBOX), "source_field": "actor+0x58", "source_constructor": "0x800eaf34 (0x800F2AA8[actor+0xC = 0], called from 0x800EAE8C; stored at 0x800EAF9C..0x800EAFA8)"}}, "model": model}
	for ev in e.events:
		if ev.get("actor_slot") is not None: ev["actor_slot"] = 0 if ev["actor_slot"] == yosyonke_H(WALKER) else ev["actor_slot"]
	scene_events = [ev for ev in e.events if ev.get("actor_slot") is None and ev["kind"] not in ("move_local", "spawn")]
	segments, init, finish = fire_programs(scene_events, tl, {**fire_OPS, **flight_OPS, **yosyonke_OPS})
	program = segments["0:0"]["program"]
	if [op["op"] for op in program] != ["delay", "player_control", "head_target", "delay", "head_target", "delay", "head_target", "delay", "advance"] or [(op["target"], op["speed"]) for op in program if op["op"] == "head_target"] != [(0, K(0x800E7C18, 0x40)), (K(0x800E7C68, 0xD00), K(0x800E7C70, 0x10)), (K(0x800E7C90, 0xF60), K(0x800E7C98, 4))]: raise ValueError("scene 0x4E step layout differs: %s" % [op["op"] for op in program])
	if [op["ticks"] for op in program if op["op"] == "delay"] != [1, K(0x800E7C54, 0xF) - 1, K(0x800E7C84, 0x21) - 0xF, K(0x800E7CAC, 0x96) - 0x21]: raise ValueError("scene 0x4E step timing differs")
	program.pop(0)
	if [op["op"] for op in finish] != ["vibration", "despawn"] or finish[1]["record"] != yosyonke_H(WALKER): raise ValueError("scene 0x4E finish differs: %s" % [op["op"] for op in finish])
	controllers = fire_controllers(e, {0: [row for row in tracks[yosyonke_H(WALKER)] if row[7] != 0xFF]}, {0: yosyonke_H(WALKER)}); controllers["0"]["source"] = "ST09T class 0 variant 2 (0x800F1A70[0] cell 2 = 0x800EAE14) emulated once per native tick after the scene update; render helpers stubbed"
	for frame in controllers["0"]["track"]["keyframes"]: frame["position_raw"][1] = y
	controllers["0"]["track"].update(floor_follow=True, floor_source="0x800EAEB8: while actor+0xF == 0, y (+0x16) = GAME0x800B13B4(actor) = GAME0x800B13FC(actor+0x10, hitbox actor+0x58, y - previous y (+0x22), cell): the map floor under the actor; the emulation stubs the map query, so the keyframe y is the record y and the runtime resolves the floor each tick")
	arrival = next((r for r in json.loads((root / "assets/levels/ST0A/doors.json").read_text(encoding="utf-8"))["area_transitions"] if r["source_area"] == 0 and r["destination_stage"] == yosyonke_STAGE and r["destination_area"] == 0), None)
	if arrival is None: raise ValueError("ST0A doors.json lacks the area 0 route back to ST09:0")
	scene = {"stage": yosyonke_STAGE, "area": 0, "scene_id": yosyonke_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4e_callbacks.json", "commands": native, "timeline": tl, "actors": [walker],
		"player": {"track": compress(tracks["player"]), "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in native)},
		"face_tables": {"player_eyes": face_table(yosyonke_EYES, 2), "player_mouth": face_table(yosyonke_MOUTH, 2)},
		"emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "area_handler_passes": passes, "events": [{k: v for k, v in ev.items() if k != "sub7"} for ev in e.events if ev["kind"] not in ("move_local", "released", "alloc", "face_tick")]},
		"source": {"overlay": "DAT/ST09T.BIN (load 0x800E7000, code size 0x%X)" % (yosyonke_D["code_end"] - yosyonke_BASE), "handler": "0x800E7884 (GAME table 0x800DC490[0x4E])", "state_table": "0x800F262C {0x800E78C0 init, 0x800E79A8 update, 0x800E7AE4 finish}", "command_pointer": yosyonke_H(yosyonke_CAMERA), "timeline_pointer": yosyonke_H(yosyonke_TIMELINE),
			"trigger": "area handler 0x800E7480 (table 0x800F2300[byte14 0] = 0x800F22E4[area 0], per-frame 0x800E7410 = GAME table 0x800DC66C[9]): state byte 0x8009BE08 == 0 -> flag 0x5C1 set: GAME0x800C0818(0x800F2354, 2), then flag 0x5C2 clear: GAME0x800C0B0C(0x4E), flag_set 0x5C2; always flag_set 0x711; state++. Area init 0x800E7290 -> 0x800E73C8 clears 0x710/0x711 on every load",
			"actor_tables": "*0x80078FA8 = 0x800F1A70 (pool 0x20), *0x80078DE0 = 0x800F1A8C (pool 0x60) set by stage init 0x800E7188 (GAME table 0x800DBEA0[9])", "messages": "none", "voices": "none (no SLES0x8001B714/0x8001B864 call)"}}
	contract = {"schema": 1, "stage": yosyonke_STAGE, "scene_id": yosyonke_SCENE_ID, "source": "ST09T scene 0x4E handler 0x800E7884; timeline 0x800F25D4 has one entry (phase 0 step 0, duration -1, callback 0x800E7BE4)",
		"tick_basis": "tick = native ctx+0x28 of the step (GAME0x800C0D70); the update 0x800E79A8 turns the player head (+0x106) toward ctx+0x10 by ctx+0x14 per tick (dead zone speed/2, clamp +-0x300), as native_scene.gd _head_tick",
		"initialization": {"player_keep_transform": True, "player_position_raw": arrival["destination_transform_raw"][:3], "player_yaw_raw": arrival["destination_transform_raw"][3], "player_note": "scene 0x4E never writes the player transform; this is the ST0A area 0 door arrival (ST0A doors.json, record %d) for reference" % arrival["record_index"], "spawn_records": [], "init_ops": init,
			"source": "0x800E78C0: GAME0x800C0C5C(0x800F2588, 0x800F25D4); GAME0x800C1148; player +0xEE/+0xEF/+0xF0/+0xF4 = 0; SLES0x80015A5C(ctx+0xC, ctx+0x18); wait GAME0x800CDD50 == 0; SLES0x80041318(ctx+0xB0, 0x800F261C, 0x800F2624); eyes 0, mouth 0; state 1. No fade"},
		"segments": segments, "actor_controllers": controllers,
		"finish": {"source": "ST09T 0x800E7AE4 (state 2, reached when the timeline ends after GAME0x800C0EA8(1) at 0x800E7CBC)", "ops": finish,
			"conditional_fade": {"type": K(0x800E7B94, 1), "condition": "0x80078F00 != 0 (screen left covered by a fade; SLES0x8001392C clears it for reveal fades)", "source": "0x800E7B88..0x800E7B9C after waiting 0x80078F01 == 0 (fade idle) at 0x800E7B68", "note": "not emitted: no fade covers the screen during the scene"},
			"skip_path": {"source": "0x800E79E8..0x800E7A18", "condition": "GAME0x800C10B4() and scratch byte 0x1F800004 != 0", "fade": 0x22, "native": "SLES0x8001392C(0x22,0); handler state 2"},
			"restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "player byte0 |= 2", "GAME0x800C0F58"], "player_render_flag": True},
		"new_ops": {"head_target": {"semantics": "ctx+0x10 = target heading, ctx+0x14 = speed (0x800E7C24/0x800E7C2C, 0x800E7C6C/0x800E7C74, 0x800E7C94/0x800E7C9C); consumed by the update 0x800E7A1C..0x800E7AC0"}}}
	world.write_output(out / "scene_4e.json", json.dumps(scene, indent=1) + "\n", encoding="utf-8"); world.write_output(out / "scene_4e_callbacks.json", json.dumps(contract, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "passes": passes, "program": [op["op"] for op in program], "finish": [op["op"] for op in finish], "init": [op["op"] for op in init], "walker_track": len(controllers["0"]["track"]["keyframes"])}

# ---- joseph_room_scene ----
# Export the original ST47 Joseph's Room bedside scene 0x12 camera, actor motion and dialogue callbacks.
joseph_STAGE = "ST47"; joseph_SCENE_ID = 0x12; joseph_BASE = 0x800E7000; joseph_HANDLER = 0x800E77B4; joseph_STAGE_INIT = 0x800E70BC; joseph_PER_FRAME = 0x800E7348; joseph_CAMERA = 0x800ECD94; joseph_TIMELINE = 0x800ECE2C; joseph_STATES = 0x800ECE84; joseph_EYES = 0x800ECE74; joseph_MOUTH = 0x800ECE7C; ROLL = 0x800ECD80; joseph_CTX = 0x8007CEC0; joseph_PLAYER = 0x8008C0A0
def export_joseph_room_scene(root=None, out_dir=None):
	global intro_GAME, intro_OVL, intro_SLES
	import models, unicorn, world
	root = Path(root or ROOT); disc = root / "build/disc-assets"; overlay = (disc / "DAT/ST47T.BIN").read_bytes(); game = (disc / "COMMON/GAME.BIN").read_bytes(); executable = (disc / "SLES_035.56").read_bytes()
	if struct.unpack_from("<I", overlay, 0)[0] != 1 or struct.unpack_from("<I", overlay, 12)[0] != joseph_BASE: raise ValueError("unexpected ST47T header")
	fire_D.update(root=root, disc=disc, ovl=overlay, game=game); intro_SLES = executable; intro_GAME = game; intro_OVL = overlay; u32 = fire_u32; gtable = lambda address: struct.unpack_from("<I", game, 0x30 + address - 0x800AD000)[0]
	if (gtable(0x800DC490 + joseph_SCENE_ID * 4), gtable(0x800DBEA0 + 0x47 * 4), gtable(0x800DC66C + 0x47 * 4)) != (joseph_HANDLER, joseph_STAGE_INIT, joseph_PER_FRAME): raise ValueError("GAME scene/stage tables do not bind ST47 scene 0x12")
	if [u32(joseph_STATES + i * 4) for i in range(3)] != [0x800E77F0, 0x800E78F4, 0x800E7988]: raise ValueError("ST47 scene 0x12 state table differs")
	e = stage_emulator(joseph_STAGE_INIT, 0x800F22B8, joseph_BASE + struct.unpack_from("<I", overlay, 4)[0], ((0x800201B0, "scene_music", 0, True, False),))()
	def spawn(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = fire_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", record=fire_H(rec), slot=e.u8(rec + 1))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn, begin=0x800C1040, end=0x800C1040)
	def fade_state(uc, address, size, data):
		value = e.r(4)
		if value in (0x12, 0x22): e.w8(0x80078F00, 1)
		elif value == 1: e.w8(0x80078F00, 0)
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, fade_state, begin=0x8001392C, end=0x8001392C)
	e.cpu.mem_write(0x98538, bytes(0x100)); e.init_flags(()); e.w8(0x8009C7F9, 2); e.w8(0x8009C7FC, 1); e.cpu.mem_write(0x8009BE08 & 0x1FFFFFFF, bytes(0x88)); e.call(joseph_PER_FRAME)
	trigger = [(x["kind"], x["args"][0] & 0xFFFFFFFF if x["kind"] == "spawn_table" else x["args"][0]) for x in e.events if x["kind"] in ("flag_set", "scene_start", "spawn_table")]
	if trigger != [("flag_set", 0x5B0), ("scene_start", joseph_SCENE_ID), ("spawn_table", 0x800ECB38)]: raise ValueError("ST47 area 2 handler does not start scene 0x12: %s" % trigger)
	e.events.clear(); e.cpu.mem_write(joseph_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(joseph_PLAYER, e.u8(joseph_PLAYER) | 2)
	tracks, ticks = run_scene(e, joseph_HANDLER, {"ctl": ((), lambda e: tuple(sorted((rec, e.u8(ptr + 0xA0)) for ptr, rec in e.actors.items())))})
	tl = fire_timeline(joseph_TIMELINE); commands = fire_commands(joseph_CAMERA)
	if [(t["phase"], t["step"], t["duration"], t["callback"]) for t in tl] != [(0, 0, -1, "0x800e7ad4")] or commands[-1]["source_ram"] != fire_H(joseph_TIMELINE): raise ValueError("ST47 scene 0x12 camera/timeline differs")
	if [x["index"] for x in e.events if x["kind"] == "message"] != [100, 103, 105, 114, 115]: raise ValueError("ST47 scene 0x12 dialogue differs")
	disc_dat = disc / "DAT"; out = Path(out_dir or root / "assets/levels") / joseph_STAGE; (out / "actors").mkdir(parents=True, exist_ok=True)
	archive, payload = models.actor_archive(root / "build/stages/ST47_models.bin"); rec = fire_record(ROLL); b = bytes.fromhex(rec["bytes_hex"]); flags = b[2] | b[4] << 8 | b[6] << 16; match = [m for m in archive["models"] if m["flags"] & 0xFFFFFF == flags]
	if len(match) != 1: raise ValueError("ST47 scene actor has no unique native resource %#x" % flags)
	index = match[0]["index"]; model_file = "actors/ST47_model_%02d.glb" % index; texture = root / "build/stages/ST47_scripted_vram.bin"
	model = models.export_actor_model(payload, index, texture, out / model_file, "ST47.BIN") if match[0]["mesh"]["bone_count"] else models.export_static_actor(payload, index, texture, out / model_file, "ST47.BIN"); model.update(model_file=model_file, model_index=index, native_resource_flags=flags, native_scale_raw=list(struct.unpack_from("<3h", payload, match[0]["mesh_offset"] + 0x30)))
	x, y, z = rec["position_raw"]; entry = {"stage": joseph_STAGE, "area": 2, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": -rec["yaw_raw"] / 4096.0, "control": b[8], "frame": b[9], "model_index": index, "model_file": model_file}
	actors = [{"source_ram": rec["source_ram"], "slot": 0, "native_slot": rec["slot"], "entry": entry, "model": model}]; slots = {rec["source_ram"]: 0}
	for event in e.events:
		if event.get("actor_slot") is not None: event["actor_slot"] = slots.get(event["actor_slot"], event["actor_slot"])
	ops = {**fire_OPS, **flight_OPS, "spawn": lambda x: {"op": "actor_spawn", "record": x["record"]}, "scene_music": lambda x: {"op": "play_sound", "id": x["args"][0]}, "despawn": lambda x: {"op": "despawn", "record": x["record"]}}
	events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("move_local", "actor_free_3EA4C", "ctl") and (x["kind"] != "spawn" or x["record"] in slots) and (x["kind"] != "despawn" or x.get("record") in slots)]
	segments, init, finish = fire_programs(events, tl, ops); segments["0:0"]["program"].insert(-1, {"op": "delay", "ticks": fire_K(0x800E7BE4, 0x32), "source": "ST47T 0x800E7BE4 sets ctx+0x10 = 0x32 after the last message; 0x800E7BF4 decrements it per tick and enters the finish state at zero"}); init = [x for x in init if x["op"] != "actor_spawn"]
	controllers = fire_controllers(e, {slots[k]: rows for k, rows in tracks.items() if k in slots}, {a["slot"]: a["source_ram"] for a in actors}); seen = {}
	for x in (x for x in e.events if x["kind"] == "ctl"):
		for record, value in x["value"]:
			if record not in slots or str(slots[record]) not in controllers or seen.get(record) == value: continue
			profile = controllers[str(slots[record])]
			if record in seen: profile["events"].append({"op": "control", "control": value, "start_record": 0, "native": "actor+0xA0 written by the ST47 class 0 callback, applied by SLES0x8003F4E8", "step": x["step"], "tick": x["frame"]})
			else: profile["startup_control"] = value
			seen[record] = value
	for profile in controllers.values(): profile["source"] = "ST47 original class 0 actor controller emulated after each scene tick"; profile.setdefault("startup_control", 0); profile["track"].update(floor_follow=True, floor_above_raw=0)
	finish = [x for x in finish if x["op"] not in ("pool_clear", "actor_spawn", "fade", "head_target")]; close = next(i for i, x in enumerate(finish) if x["op"] == "close_windows"); finish.insert(close, {"op": "fade", "type": 0x12, "wait": True, "source": "ST47T 0x800E79DC..0x800E7A28; the scene fades out before the actor is removed"})
	initial = {"player_position_raw": [-16, 0, 64], "player_yaw_raw": 0xAB8, "player_floor_follow": True, "spawn_records": [], "init_ops": init, "source": "ST47T 0x800E7850..0x800E7870 positions the player (+0x12 = -0x10, +0x16 = 0, +0x1A = 0x40, yaw +0x2A = 0xAB8)"}
	contract = {"schema": 1, "stage": joseph_STAGE, "scene_id": joseph_SCENE_ID, "tick_basis": "original ctx+0x28 at 25 Hz; dialogue waits preserved in runtime", "initialization": initial, "segments": segments, "actor_controllers": controllers, "finish": {"ops": finish, "registration_records": [], "player_render_flag": True, "fade_entry": 1, "fade_entry_source": "ST47T 0x800E7A60..0x800E7A74: when covered-screen byte 0x80078F00 is nonzero, SLES0x8001392C(1,0) reveals the restored view", "source": "ST47T 0x800E7988..0x800E7AC0"}}
	scene = {"stage": joseph_STAGE, "area": 2, "scene_id": joseph_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_12_callbacks.json", "commands": commands, "timeline": tl, "actors": actors, "player": {"track": compress(tracks["player"]), "track_runtime": True, "floor_follow": True, "camera_opcode_0x42_used": any(c["opcode"] == 0x42 for c in commands)}, "face_tables": {"player_eyes": face_table(joseph_EYES, 2), "player_mouth": face_table(joseph_MOUTH, 2)}, "source": {"overlay": "DAT/ST47T.BIN", "handler": fire_H(joseph_HANDLER), "state_table": fire_H(joseph_STATES), "command_pointer": fire_H(joseph_CAMERA), "timeline_pointer": fire_H(joseph_TIMELINE), "messages": [100, 103, 105, 114, 115], "trigger": "area 2 handler 0x800E74F4 (table 0x800ECABC row byte14 1): flag 0x5B0 clear -> set 0x5B0, GAME0x800C0B0C(0x12) at 0x800E753C"}, "emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "events": [x for x in e.events if x["kind"] not in ("move_local", "face_tick", "alloc", "released", "ctl")]}}
	for name, document in (("scene_12.json", scene), ("scene_12_callbacks.json", contract)): world.write_output(out / name, json.dumps(document, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "model": model_file, "segments": {k: [x["op"] for x in v["program"]] for k, v in segments.items()}, "finish": [x["op"] for x in finish]}

# ---- joe_scene ----
# Export the original ST08 workshop scene 0x4F camera, actor motion and dialogue callbacks.
joe_STAGE = "ST08"; joe_SCENE_ID = 0x4F; joe_HANDLER = 0x800EFE40; joe_CAMERA = 0x800F544C; joe_TIMELINE = 0x800F553C; STARTUP = {0x800F5424: "0x800EC344", 0x800F5438: "0x800E7B1C"}; joe_CTX = 0x8007CEC0; joe_PLAYER = 0x8008C0A0
def export_joe_scene(root=None, out_dir=None):
	import unicorn, world
	root = Path(root or ROOT); landing_load(root); game = landing_D["game"]
	if struct.unpack_from("<I", game, 0x30 + 0x800DC490 + joe_SCENE_ID * 4 - 0x800AD000)[0] != joe_HANDLER: raise ValueError("GAME scene 0x4F binding differs")
	if [fire_u32(0x800F55B4 + i * 4) for i in range(3)] != [0x800EFE7C, 0x800EFF94, 0x800F00D0]: raise ValueError("ST08 workshop scene states differ")
	e = stage_emulator(landing_STAGE_INIT, 0x800F22B8, landing_D["code_end"], ((0x800201B0, "scene_music", 0, True, False),))()
	def spawn(uc, address, size, data):
		rec = e.r(16); ptr = e.r(4); e.actors[ptr] = fire_H(rec); e.pools[ptr] = bytes(uc.mem_read(rec & 0x1FFFFFFF, 4)); e.record("spawn", record=fire_H(rec), slot=e.u8(rec + 1))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn, begin=0x800C1040, end=0x800C1040)
	def fade_state(uc, address, size, data):
		value = e.r(4)
		if value in (0x12, 0x22): e.w8(0x80078F00, 1)
		elif value == 1: e.w8(0x80078F00, 0)
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, fade_state, begin=0x8001392C, end=0x8001392C)
	e.cpu.mem_write(joe_CTX & 0x1FFFFFFF, bytes(0xC0)); e.events.clear(); e.w8(joe_PLAYER, e.u8(joe_PLAYER) | 2)
	tracks, ticks = run_scene(e, joe_HANDLER, {"head": ((0, 0), lambda e: (e.u16(joe_CTX + 0x10), intro_s16(e.u16(joe_CTX + 0x14)))), "ctl": ((), lambda e: tuple(sorted((rec, e.u8(ptr + 0xA0)) for ptr, rec in e.actors.items())))})
	tl = fire_timeline(joe_TIMELINE); commands = fire_commands(joe_CAMERA)
	if len(tl) != 5 or commands[-1]["source_ram"] != fire_H(joe_TIMELINE): raise ValueError("workshop camera/timeline differs")
	if [x["index"] for x in e.events if x["kind"] == "message"] != [50, 51, 52, 53, 57]: raise ValueError("workshop dialogue differs")
	scripted = json.loads((root / "assets/levels/ST08/scripted_actors.json").read_text(encoding="utf-8")); actors = []; slots = {}
	for address, model_index in ((0x800F53FC, 2), (0x800F5410, 3), (0x800F5424, 2), (0x800F5438, 3)):
		rec = fire_record(address); b = bytes.fromhex(rec["bytes_hex"]); x, y, z = rec["position_raw"]; model = dict(next(m for m in scripted["models"] if m["model_index"] == model_index)); model.pop("file", None)
		if model["native_resource_flags"] != b[2] | b[4] << 8 | b[6] << 16: raise ValueError("workshop actor model differs")
		entry = {"stage": joe_STAGE, "area": 1, "source_record_ram": rec["source_ram"], "source_bytes_hex": rec["bytes_hex"], "pool_type": b[2], "actor_class": b[4], "actor_state": b[5], "resource_variant": b[6], "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": rec["yaw_raw"], "yaw_turns": -rec["yaw_raw"] / 4096.0, "control": b[8], "frame": b[9], "model_index": model_index, "model_file": model["model_file"]}
		if address in (0x800F53FC, 0x800F5410): entry["native_hitbox"] = {"bounds_raw": [fire_s16((0x800F51D4 if address == 0x800F53FC else 0x800F291C) + i * 2) for i in range(6)], "source_pointer_ram": "0x800f51d4" if address == 0x800F53FC else "0x800f291c", "source_field": "actor+0x58", "source_constructor": "0x800ec344" if address == 0x800F53FC else "0x800e7b1c", "anchor": "actor+0x10"}
		if False: entry["native_hitbox"] = {"bounds_raw": [fire_s16(0x800F291C + i * 2) for i in range(6)], "source_pointer_ram": "0x800f291c", "source_field": "actor+0x58", "source_constructor": "0x800e7b1c", "anchor": "actor+0x10"}
		if address in STARTUP: entry["native_animation_startup"] = {"control": 0, "start_record": 0, "source_constructor": STARTUP[address], "control_source": "constructor state 1, then substate 0 sets control 0; record byte9 0x80 is not a start record", "setter": "SLES0x8003F4E8(actor,control,0)"}
		slots[rec["source_ram"]] = len(actors); actors.append({"source_ram": rec["source_ram"], "slot": len(actors), "native_slot": rec["slot"], "entry": entry, "model": model})
	for event in e.events:
		if event.get("actor_slot") is not None: event["actor_slot"] = slots.get(event["actor_slot"], event["actor_slot"])
		if event["kind"] == "head": event["frame"] = max(0, event["frame"] - 1)
	ops = {**fire_OPS, **flight_OPS, "head": lambda x: {"op": "head_target", "target": x["value"][0], "speed": x["value"][1]}, "spawn": lambda x: {"op": "actor_spawn", "record": x["record"]}, "scene_music": lambda x: {"op": "play_sound", "id": x["args"][0]}}
	events = [x for x in e.events if x.get("actor_slot") is None and x["kind"] not in ("move_local", "actor_free_3EA4C", "ctl") and (x["kind"] != "spawn" or x["record"] in slots) and (x["kind"] != "despawn" or x.get("record") in slots)]
	segments, init, finish = fire_programs(events, tl, ops)
	init = [x for x in init if x["op"] != "actor_spawn"]
	controllers = fire_controllers(e, {slots[k]: rows for k, rows in tracks.items() if k in slots and slots[k] < 2}, {a["slot"]: a["source_ram"] for a in actors})
	seen = {}
	for x in (x for x in e.events if x["kind"] == "ctl"):
		for rec, value in x["value"]:
			if rec not in slots or str(slots[rec]) not in controllers or seen.get(rec) == value: continue
			profile = controllers[str(slots[rec])]
			if rec in seen: profile["events"].append({"op": "control", "control": value, "start_record": 0, "native": "actor+0xA0 written by the class 0 state 3 callback 0x800ECA70 (0x800F5200 table), applied by SLES0x8003F4E8", "step": x["step"], "tick": x["frame"]})
			else: profile["startup_control"] = value
			seen[rec] = value
	for slot, profile in controllers.items(): profile["source"] = "ST08 original class 0 variant 3 actor controller emulated after each scene tick"; profile.setdefault("startup_control", 0)
	controllers["0"]["track"].update(floor_follow=True, floor_above_raw=0, floor_source="GAME0x800B13FC candidate filter 0x800B1648..0x800B1668 (actor y < cell lower y) ignores volumes resting above the feet, so the ray starts at the feet; ST08T 0x800ECB14: the state 3 callback stores y (+0x16) = GAME0x800B13B4(actor) while actor+0xF == 0; the emulation stubs the map query, so the runtime resolves the floor each tick")
	controllers["1"]["track"].update(floor_follow=True, floor_above_raw=0, floor_source="ST08T 0x800E7A20: the girl update (0x800E78CC) stores y (+0x16) = GAME0x800B13B4(actor), the map floor under the actor; the emulation stubs the map query, so the runtime resolves the floor each tick")
	finish = [x for x in finish if x["op"] not in ("pool_clear", "actor_spawn", "fade")]
	close = next(i for i, x in enumerate(finish) if x["op"] == "close_windows")
	finish.insert(close, {"op": "fade", "type": 0x12, "wait": True, "source": "ST08T 0x800F0144; idle wait at 0x800F0170"})
	for operation in init:
		if operation["op"] == "jingle": operation["note"] = "SLES0x80020984(0xF,0x111,0), ST08T 0x800EFF20"
	initial = {"player_position_raw": [320, 0, -16], "player_yaw_raw": 896, "player_floor_follow": True, "spawn_records": [], "init_ops": init, "source": "ST08T 0x800EFED4..0x800EFF0C positions player then resolves floor with GAME0x800B13B4"}
	contract = {"schema": 1, "stage": joe_STAGE, "scene_id": joe_SCENE_ID, "tick_basis": "original ctx+0x28 at 25 Hz; dialogue/fade waits preserved in runtime", "initialization": initial, "segments": segments, "actor_controllers": controllers, "finish": {"ops": finish, "registration_records": ["0x800f5424", "0x800f5438"], "player_yaw_raw": 1024, "player_render_flag": True, "fade_entry": 1, "fade_entry_source": "ST08T 0x800F01C4..0x800F01DC: when covered-screen byte 0x80078F00 is nonzero, SLES0x8001392C(1,0) reveals the restored view; emitted after camera restore by the runtime", "source": "ST08T 0x800F00D0..0x800F022C restores player, respawns ordinary Roll and Joe's daughter, and resumes music 0x15"}}
	scene = {"stage": joe_STAGE, "area": 1, "scene_id": joe_SCENE_ID, "native_tick_hz": 25, "callback_contract_file": "scene_4f_callbacks.json", "commands": commands, "timeline": tl, "actors": actors, "player": {"track": compress(tracks["player"]), "track_runtime": True, "floor_follow": True, "camera_opcode_0x42_used": False}, "face_tables": {"player_eyes": face_table(0x800F55A4, 2), "player_mouth": face_table(0x800F55AC, 2)}, "source": {"overlay": "DAT/ST08T.BIN", "handler": fire_H(joe_HANDLER), "command_pointer": fire_H(joe_CAMERA), "timeline_pointer": fire_H(joe_TIMELINE), "messages": [50, 51, 52, 53, 57]}, "emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "events": [x for x in e.events if x["kind"] not in ("move_local", "face_tick", "alloc", "released", "ctl")]}}
	out = Path(out_dir or root / "assets/levels") / joe_STAGE
	for name, payload in (("scene_4f.json", scene), ("scene_4f_callbacks.json", contract)): world.write_output(out / name, json.dumps(payload, indent=1) + "\n", encoding="utf-8")
	return {"ticks": ticks, "actors": list(slots), "messages": scene["source"]["messages"], "segments": {k: [x["op"] for x in v["program"]] for k, v in segments.items()}}

# ---- mine_scene ----
# Extract the original abandoned-mine scene commands and emulated callback contracts.
mine_BASE = 0x800E7000; mine_CTX = 0x8007CEC0; mine_PLAYER = 0x8008C0A0
PROFILES = {0x50: (0x800FD44C, 0x801016A4, 0x801015F0, 0x8010166C, 1), 0x51: (0x800FDEFC, 0x80101800, 0x80101704, 0x801017D8, 11), 0x52: (0x800FE628, 0x801018B4, 0x80101820, 0x8010189C, 12), 0x53: (0x800FE9E0, 0x80101918, 0x801018D4, 0x80101900, 12), 0x54: (0x800FED6C, 0x80101A6C, 0x80101988, 0x80101A3C, 11)}
def mine_load(root=ROOT):
	global intro_GAME, intro_OVL, intro_SLES
	disc = Path(root) / "build/disc-assets"; overlay = (disc / "DAT/ST0FT.BIN").read_bytes(); game = (disc / "COMMON/GAME.BIN").read_bytes(); executable = (disc / "SLES_035.56").read_bytes(); fire_D.update(root=Path(root), disc=disc, ovl=overlay, game=game); intro_SLES = executable; intro_GAME = game; intro_OVL = overlay
	for scene, (handler, states, camera, timeline, area) in PROFILES.items():
		if struct.unpack_from("<I", game, 48 + 0x800DC490 + scene * 4 - 0x800AD000)[0] != handler: raise ValueError("Mine scene handler differs")
	return overlay
def make_emulator(root, overlay):
	import unicorn, models
	e = stage_emulator(0x800E71B8, 0x800F22B8, mine_BASE + struct.unpack_from("<I", overlay, 4)[0], ((0x800201B0, "scene_music", 0, True, False), (0x80020C74, "jingle_ready", 1, False, False), (0x8001B64C, "file_unload", 0, True, False), (0x8003FD4C, "pose_submit", 0, False, False)))(); e.model_bindings = {}; e.source_models = {}; address = 0x80120000
	for name in ("ST0F00.BIN", "ST0F01.BIN"):
		archive, payload = models.actor_archive(Path(root) / "build/disc-assets/DAT" / name); e.cpu.mem_write(address & 0x1FFFFFFF, payload)
		for model in archive["models"]: e.source_models.setdefault(model["flags"] & 0xFFFFFF, {"archive": name, "index": model["index"], "base": address, "control_table": model["control_table_offset"], "metadata": model})
		address += (len(payload) + 0xFFF) & ~0xFFF
	for function in (0x8003F4BC, 0x8003F4E8, 0x8003F768, 0x8003F794, 0x8003F840):
		if function not in e.stubs: e.cpu.hook_add(unicorn.UC_HOOK_CODE, e.stub_hook, begin=function, end=function)
		e.stubs[function] = ("actor_control" if function == 0x8003F4E8 else "animation_native", 0, function == 0x8003F4E8, True)
	def resource(uc, function, size, data):
		actor = e.r(4); source = e.pools.get(actor)
		if source is None: raise ValueError("Resource binding lacks original actor record")
		variant = 0 if function == 0x8003DFA4 else e.u8(e.r(5)); flags = source[2] | e.u8(actor + 4) << 8 | variant << 16
		if flags not in e.source_models: raise ValueError("Unbound native actor resource %#x" % flags)
		model = e.source_models[flags]; e.model_bindings[actor] = model
		if model["control_table"]: e.w32(actor + 0xAC, model["base"] + model["control_table"])
	def animation_bank(uc, function, size, data):
		model = e.model_bindings.get(e.r(4))
		if model: e.w32(0x1F800074, model["base"])
	for function in (0x8003DFA4, 0x8003DFC8): e.cpu.hook_add(unicorn.UC_HOOK_CODE, resource, begin=function, end=function)
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, animation_bank, begin=0x8003F4E8, end=0x8003F4E8)
	return e
def export_actor_catalog(root=ROOT, out=None):
	import models, world
	root = Path(root); overlay = mine_load(root); out = Path(out or root / "assets/levels/ST0F"); out.mkdir(parents=True, exist_ok=True); dat = root / "build/disc-assets/DAT"; vram = bytearray(1024 * 512 * 2); uploads = []
	for path in (dat.parent / "COMMON/GAME.BIN", dat.parent / "COMMON/PL00T.BIN", dat / "ST0FT.BIN", dat / "ST0F.BIN"): uploads.extend(world.texture_uploads(path.read_bytes(), vram, path.name))
	header = bytearray(48); struct.pack_into("<3I", header, 0, 2, len(vram), 1); struct.pack_into("<8H", header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture = root / "build/stages/ST0F_mine_scene_vram.bin"; models.write_output(texture, header + vram); archives = {name: models.actor_archive(dat / name) for name in ("ST0F00.BIN", "ST0F01.BIN")}; exported = {}; actors = []
	addresses = [0x801007EC, 0x80100814, 0x80100828, 0x8010083C, 0x80100850, 0x80100864, 0x80100878, 0x8010180C, 0x801016C8, 0x801016DC, 0x801016F0, 0x8010194C, 0x80101960, 0x80101974]
	for _, _, camera, _, _ in PROFILES.values(): addresses.extend(int(command["actor_record"]["source_ram"], 16) for command in fire_commands(camera) if "actor_record" in command)
	for address in dict.fromkeys(addresses):
		record = fire_record(address); raw = bytes.fromhex(record["bytes_hex"]); flags = raw[2] | raw[4] << 8; found = [(name, item, payload) for name, (archive, payload) in archives.items() for item in archive["models"] if item["flags"] & 0xFFFFFF == flags]
		if found: found = [found[0]]
		x, y, z = record["position_raw"]; entry = {"stage": "ST0F", "source_record_ram": record["source_ram"], "source_bytes_hex": record["bytes_hex"], "record_id": raw[1], "record_type": raw[2], "actor_class": raw[4], "actor_state": raw[5], "resource_variant": raw[6], "native_private_raw": list(raw[8:12]), "position_raw": [x, y, z], "position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": record["yaw_raw"], "yaw_turns": -record["yaw_raw"] / 4096.0, "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": record["yaw_raw"], "yaw_turns": -record["yaw_raw"] / 4096.0, "floor_height": y == -1}}
		if not found: actors.append({"source_ram": record["source_ram"], "entry": entry, "model": None, "source_role": "Native particle record; no PBD resource"}); continue
		name, source_model, payload = found[0]; key = (name, source_model["index"])
		if key not in exported:
			file = "actors/mine/%s_model_%02d.glb" % (Path(name).stem, source_model["index"]); metadata = models.export_actor_model(payload, source_model["index"], texture, out / file, name, preserve_default_hidden=True) if source_model["mesh"]["bone_count"] else models.export_static_actor(payload, source_model["index"], texture, out / file, name); metadata.update(model_file=file, model_index=source_model["index"], native_resource_flags=flags, native_scale_raw=list(struct.unpack_from("<3h", payload, source_model["mesh_offset"] + 0x30))); exported[key] = metadata
		entry.update(model_file=exported[key]["model_file"], model_index=source_model["index"], native_resource_flags=flags)
		if raw[4] in (0x55, 0x60):
			roll = raw[4] == 0x60; constructor, body, target, callback, request = (0x800F128C, 0x80100EF4, 0x80100F00, 0x800F10B8, 0x800F1420) if roll else (0x800F0BF0, 0x80100EB8, 0x80100EC4, 0x800F0AC4, 0x800F0D54); bounds = list(struct.unpack("<6h", fire_rd(body, 12))); descriptor = list(struct.unpack("<6h", fire_rd(target, 12))); entry["native_animation_startup"] = {"control": raw[9], "start_record": 0, "source_constructor": fire_H(constructor)}; entry["native_hitbox"] = {"bounds_raw": bounds, "source_pointer_ram": fire_H(body), "source_constructor": fire_H(constructor)}; entry["native_interaction"] = {"stage": "ST0F", "actor_class": raw[4], "actor_state": raw[5], "actor_callback": fire_H(callback), "request_call": fire_H(request), "request_api": "0x800BE2E0", "request_kind": (0x12 if raw[10] & 0x80 else 2) if roll else 0x12, "message_call": "0x800BDCF8", "message_index": raw[11], "index_source": "LBU actor+F copied from record byte+B", "bank_id": "0x8010C000", "target_descriptor_raw": descriptor, "target_descriptor_source": fire_H(target), "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False}}
		if address == 0x8010180C: entry["source_attributes"] = models.source_combat_attributes(fire_D["game"], 7, raw[7])["normal"]["attributes"]
		if raw[4] == 0x6F:
			entry["native_hitbox"] = {"bounds_raw": list(struct.unpack("<6h", fire_rd(0x80100F84, 12))), "source_pointer_ram": "0x80100f84", "source_constructor": "0x800f1bc8"}; entry["native_interaction"] = {"stage": "ST0F", "actor_class": 0x6F, "actor_state": raw[5], "actor_callback": "0x800f1a8c", "request_call": "0x800f1d90", "request_api": "0x800BE2E0", "request_kind": 0x12, "message_call": "0x800BDCF8", "message_index": raw[11], "index_source": "unsigned actor+F copied from record+B", "bank_id": "0x8010C000", "target_descriptor_raw": list(struct.unpack("<6h", fire_rd(0x80100F90, 12))), "target_descriptor_source": "0x80100f90", "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "descriptor_xyz_rotated": False, "score": "integer3Ddistance+(absYawDelta>>2)", "line_of_sight": False}}
		actors.append({"source_ram": record["source_ram"], "entry": entry, "model": exported[key]})
	document = {"stage": "ST0F", "actors": actors, "source": {"script": "tools/cinematics.py", "texture_uploads": uploads, "archives": list(archives)}}; world.write_output(out / "mine_actors.json", json.dumps(document, indent=1) + "\n", encoding="utf-8"); print("mine actors", len(actors), "models", len(exported)); return document
def export_lifts(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); mine_load(root); out = Path(out_dir or root / "assets/levels/ST0F"); K = fire_K; u32 = fire_u32; H = fire_H
	if u32(0x800FF6AC + 0x19 * 4) != 0x800FF6A8 or u32(0x800FF6A8) != 0x800F2E4C: raise ValueError("ST0FT class 0x19 lift pad callback differs")
	for address, value in ((0x800F2F0C, 0x400), (0x800F2FA8, 0x200), (0x800F2FB0, 0x800), (0x800F2FC0, 0x400), (0x800F300C, 0x710), (0x800F3060, 0x702), (0x800F306C, 0xE), (0x800F3078, 0x700), (0x800FC5A0, -0x40), (0x800FC5B0, -0x800), (0x800FC5E8, 0x3C), (0x800FC5F4, 0x12), (0x800FC648, 0x30), (0x800FC650, 4), (0x800FC6C8, 0x40), (0x800FC6D0, 3), (0x800FC72C, 0x13F), (0x800FC440, 2), (0x800FC6E8, 0x5556), (0x800FC708, 0x8E39)): K(address, value)
	pads = []; doors = json.loads((out / "doors.json").read_text(encoding="utf-8"))["area_object_records"]
	for address in (0x800FF898, 0x800FF960, 0x800FFA64, 0x800FFAA0):
		record = fire_record(address); raw = bytes.fromhex(record["bytes_hex"])
		if raw[2] != 0x60 or raw[4] != 0x19: raise ValueError("ST0F lift pad record differs")
		area = next(item["area_index"] for item in doors if item["bytes_hex"] == record["bytes_hex"]); pads.append({"area": area, "source_ram": record["source_ram"], "source_bytes_hex": record["bytes_hex"], "position_raw": record["position_raw"], "yaw_raw": record["yaw_raw"], "message_index": raw[8], "direction": raw[9], "lock_flag_offset": raw[10], "locked_message_index": raw[11]})
	descriptors = {str(yaw): list(struct.unpack("<6h", fire_rd(pointer, 12))) for yaw, pointer in ((0, 0x8010109C), (0x400, 0x801010A8), (0x800, 0x801010B4), (0xC00, 0x801010C0))}
	document = {"stage": "ST0F", "source": {"script": "tools/cinematics.py", "pad_callback": "ST0FT0x800F2E4C (class 0x19 via class table 0x800FF6AC)", "scene_start": "ST0FT0x800F3048: event flag 0x702 -> request byte 0x80078D0E=0xE and flag 0x700; GAME0x800C04C8 dispatches request type 0xE through table 0x80100388 to ST0FT0x800FC0C8", "scene_callbacks": {"setup": "0x800FC104", "run": "0x800FC460", "finish": "0x800FC4BC", "ride": "0x800FC548"}},
		"pad": {"model_index": 12, "hitbox_raw": list(struct.unpack("<6h", fire_rd(0x80101090, 12))), "hitbox_source": "0x80101090", "target_descriptors_by_yaw": descriptors, "target_descriptor_source": "0x8010109C/0x801010A8/0x801010B4/0x801010C0 selected by actor yaw 0/0x400/0x800/else at 0x800F2F2C", "target_flags60": 1, "target_criteria": {"range_extra_raw": 192, "yaw_half_cone_raw": 512, "strict_bounds": True, "line_of_sight": False}, "facing": {"player_yaw_bias": 0x200, "actor_yaw_bias": 0x800, "half_range": 0x400, "source": "ST0FT0x800F2FA0..0x800F2FDC"}, "bank_id": "0x8010C000", "message_call": "0x800BE330", "lock_flag_base": 0x710, "answer_flag": 0x702, "scene_flag": 0x700, "scene_request_type": 0xE},
		"ride": {"first_frame": {"player_height_raw": -0x40, "yaw_offset_raw": -0x800}, "acceleration_raw": 4, "maximum_speed_raw": 0x30, "fade_frame": 0x3C, "fade_code": 0x12, "entry_fade_code": 2, "motor_sound": 0x13F, "motor_sound_frames": 0x40, "motor_sound_period_by_tick_mode": {"3": 3, "default": 9}, "tick_hz": 25, "direction_byte": "pad record byte 9: 0 raises the player and pad (-Y), nonzero lowers them (+Y)", "source": "ST0FT0x800FC548"},
		"lifts": pads}
	world.write_output(out / "mine_lifts.json", json.dumps(document, indent=1) + "\n", encoding="utf-8"); return document
def export_mine_scenes(root=None, out_dir=None):
	import world
	root = Path(root or ROOT); out = Path(out_dir or root / "assets/levels/ST0F"); catalog = export_actor_catalog(root, out); export_lifts(root, out); actor_by_record = {item["source_ram"]: item for item in catalog["actors"]}; summaries = []
	for scene_id, (handler, states, camera, timeline, area) in PROFILES.items():
		e, tracks, ticks = probe(scene_id, root)
		if not any(event["kind"] == "restore_C0F58" for event in e.events): raise ValueError("Mine scene did not reach its original finish")
		tl = fire_timeline(timeline); commands = fire_commands(camera); requested = [event["record"] for event in e.events if event["kind"] == "spawn"]
		if scene_id == 0x53: requested.insert(0, "0x8010180c")
		actors = []
		for record in dict.fromkeys(requested):
			item = actor_by_record[record]
			if item["model"] is None: continue
			entry = dict(item["entry"]); entry["area"] = area; actors.append({"source_ram": record, "slot": entry["record_id"], "native_slot": entry["record_id"], "entry": entry, "model": item["model"]})
		slots = {item["source_ram"]: item["slot"] for item in actors}
		ops = {**fire_OPS, **flight_OPS, "skip_lock": lambda event: {"op": "skip_lock", "set": event["value"]}, "scene_music": lambda event: {"op": "play_sound", "id": event["args"][0]}, "spawn": lambda event: {"op": "actor_spawn", "record": event["record"]}, "sound_3d": lambda event: {"op": "play_sound", "id": event["args"][0]}, "file_unload": lambda event: {"op": "file_unload", "file_id": event["args"][0]}}
		director_events = [event for event in e.events if event.get("actor_slot") is None and (event["kind"] != "spawn" or event["record"] in slots)]; segments, initial, finish = fire_programs(director_events, tl, ops); normalized_tracks = {slots[record]: rows for record, rows in tracks.items() if record in slots}; normalized_events = []
		for event in e.events:
			if event.get("actor_slot") in slots: event = {**event, "actor_slot": slots[event["actor_slot"]]}
			normalized_events.append(event)
		saved_events = e.events; e.events = normalized_events; controllers = fire_controllers(e, normalized_tracks, {item["slot"]: item["source_ram"] for item in actors}); e.events = saved_events
		for controller in controllers.values(): controller["source"] = "Original ST0FT controller and SLES control-record clock executed after each source scene update; pose submission and map collision are renderer/physics adapters"
		if scene_id == 0x52:
			program = segments["0:0"]["program"]; index = next(index for index, operation in enumerate(program) if operation["op"] == "player_bank_switch"); program.insert(index, {"op": "wait_resource_ready", "file_id": 0x67, "buffer_index": 1, "source": "ST0FT0x800FE968..FE9B4: jingle15 idle, global78DBA bit0 clear, scratch1F800004==1"})
		if scene_id == 0x53:
			actors[0]["existing_actor"] = "mine_boss"; actors[0]["preserve_live_transform"] = True; controllers["0"]["external_controller"] = "native_mine_boss"; controllers["0"]["track_reference_only"] = True; segments["0:0"]["program"] = [{"op": "wait_actor_inactive", "slot": 0, "source": "ST0FT0x800FED28..FED50 tests8009C900 and actor.byte0"}, {"op": "advance", "source": "ST0FT0x800FED4C"}]
		initialization = {"init_ops": initial, "spawn_records": ["0x8010180c"] if scene_id == 0x53 else [], "source": "Original scene phase0 callback", "hardware_adapter": {"native_buffer_index": 1, "audio_and_file_readiness": "Emulation reports ready; runtime must await the corresponding resource/audio operation"}}
		player_rows = tracks.get("player", []); first = player_rows[0] if player_rows else None; settled = [index for index, row in enumerate(player_rows) if row[2] > 0]; final_row = player_rows[-1] if player_rows else None; trailing = bool(settled) and settled[-1] < len(player_rows) - 1 and player_rows[-1][3:6] != player_rows[settled[-1]][3:6]; player_rows = player_rows[:settled[-1] + 1] if trailing else player_rows
		if first: initialization.update(player_position_raw=[s32(first[axis]) / 65536.0 for axis in (3,4,5)], player_yaw_raw=first[6])
		finish_data = {"ops": finish, "source": fire_H(fire_u32(states + 8)), "restore_calls": [event["kind"] for event in e.events if event["state"] == 2 and event["kind"].startswith("restore_")]}
		registrations = [event for event in e.events if event["state"] == 2 and event["kind"] == "spawn_table"]
		finish_data.update(player_position_raw=[s32(final_row[axis]) / 65536.0 for axis in (3, 4, 5)], player_yaw_raw=final_row[6]) if trailing else None; finish_data["registration_records"] = [fire_H((event["args"][0] & 0xFFFFFFFF) + index * 20) for event in registrations for index in range(event["args"][1])]
		for address in finish_data["registration_records"]:
			if address in slots: continue
			item = actor_by_record[address]; entry = {**item["entry"], "area": area}; slot = max([actor["slot"] for actor in actors] + [-1]) + 1; actors.append({"source_ram": address, "slot": slot, "native_slot": entry["record_id"], "entry": entry, "model": item["model"], "activation": "finish_registration"}); slots[address] = slot
		if scene_id == 0x52: finish_data["retain_actor_records"] = ["0x8010180c"]; finish_data["boss_pointer_write"] = {"source_ram": "0x8009c900", "actor_slot": 0, "source": "ST0FT0x800FE888"}
		if scene_id == 0x54:
			if fire_u32(0x800FF024) != 0x0C000000 | (0x800C0360 >> 2 & 0x3FFFFFF): raise ValueError("Mine scene 0x54 no longer advances the story byte")
			index = next(index for index, operation in enumerate(finish_data["ops"]) if operation["op"] == "event_set"); finish_data["ops"].insert(index + 1, {"op": "story_advance", "source": "0x800ff024", "native": "GAME0x800C0360: +0x15 of 0x8009C7E8 (pending story byte) += 1; committed to +0x14 and flags 0x580..0x65F cleared by GAME0x800B04B4..0x800B04E0 on the next area request"})
		if scene_id == 0x54: finish_data["progression_scope"] = "This conversation respawns chest/effect/humanoid, sets710 and advances the pending story byte; the refractor talk (message 30 -> 34 -> 35, opcode 0x3C) requests ST47 area 2"
		base = "scene_%02x" % scene_id; contract = {"schema": 1, "stage": "ST0F", "scene_id": scene_id, "tick_basis": "Original ctx+28 at25Hz; native message, fade, resource and actor-lifetime gates retained", "initialization": initialization, "segments": segments, "actor_controllers": controllers, "finish": finish_data}; scene = {"stage": "ST0F", "area": area, "scene_id": scene_id, "native_tick_hz": 25, "callback_contract_file": base + "_callbacks.json", "commands": commands, "timeline": tl, "actors": actors, "player": {"track": compress(player_rows), "track_runtime": True, "floor_follow": True}, "face_tables": {}, "source": {"handler": fire_H(handler), "state_table": fire_H(states), "command_pointer": fire_H(camera), "timeline_pointer": fire_H(timeline), "overlay": "DAT/ST0FT.BIN"}, "emulation": {"script": "tools/cinematics.py", "native_ticks": ticks, "events": [event for event in e.events if event["kind"] not in ("face_tick", "move_local", "render", "hitbox", "alloc", "released")]}}
		for name, document in ((base + ".json", scene), (base + "_callbacks.json", contract)): world.write_output(out / name, json.dumps(document, indent=1) + "\n", encoding="utf-8")
		summaries.append({"scene_id": scene_id, "native_ticks": ticks, "actors": len(actors), "segments": len(segments), "messages": [event["index"] for event in e.events if event["kind"] == "message"]})
	return {"stage": "ST0F", "actors": len(catalog["actors"]), "scenes": summaries}
def probe(scene_id, root=ROOT):
	import unicorn
	overlay = mine_load(root); handler, states, camera, timeline, area = PROFILES[scene_id]
	e = make_emulator(root, overlay)
	def spawn(uc, address, size, data):
		record = e.r(16); pointer = e.r(4); e.actors[pointer] = fire_H(record); e.pools[pointer] = bytes(uc.mem_read(record & 0x1FFFFFFF, 4)); e.record("spawn", record=fire_H(record), slot=e.u8(record + 1))
	e.cpu.hook_add(unicorn.UC_HOOK_CODE, spawn, begin=0x800C1040, end=0x800C1040); e.cpu.mem_write(mine_CTX & 0x1FFFFFFF, bytes(0xC0)); e.w8(0x8009C7F9, area); e.events.clear(); e.w8(mine_PLAYER, e.u8(mine_PLAYER) | 2)
	e.w8(0x1F800004, 1)
	if scene_id == 0x53:
		record = 0x8010180C; actor = e.call(0x800C05E0, (record,)); e.actors[actor] = fire_H(record); e.pools[actor] = bytes(e.cpu.mem_read(record & 0x1FFFFFFF, 4)); e.cur = fire_H(record); e.call(0x800EA29C, (actor,)); e.cur = None; e.w16(actor + 0x70, 0xFFFF); e.w8(actor + 8, 3); e.w32(0x8009C900, actor); e.events.clear()
	try: tracks, ticks = run_scene(e, handler, {"skip_lock": (False, lambda e: bool(e.u8(mine_CTX) & 0x20)), "player_render_flag": (True, lambda e: bool(e.u8(mine_PLAYER) & 2))}, ticks=4000)
	except Exception:
		print("scene failure", hex(scene_id), "flags", e.u8(mine_CTX), "step", e.where(), "actors", e.actors, "npc_table", hex(e.u32(0x80078FA8))); print("latest events", e.events[-16:]); raise
	result = {"scene": hex(scene_id), "ticks": ticks, "state": e.u8(mine_CTX + 4), "phase": e.u8(mine_CTX + 2), "step": e.u8(mine_CTX + 3), "sub6": e.u8(mine_CTX + 6), "sub7": e.u8(mine_CTX + 7), "context_flags": e.u8(mine_CTX), "clock": [e.u32(mine_CTX + offset) for offset in (0x20,0x24,0x28)], "commands": fire_commands(camera), "timeline": fire_timeline(timeline), "events": [event for event in e.events if event["kind"] not in ("face_tick", "move_local", "render", "hitbox")], "tracks": list(tracks)}
	path = Path(root) / "build/maps" / ("mine_scene_%02x_probe.json" % scene_id); write_output(path, json.dumps(result, indent=1) + "\n", encoding="utf-8"); print("probe", hex(scene_id), ticks, result["state"], result["phase"], result["step"], "events", len(result["events"])); return e, tracks, ticks
def inspect_sources(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); disc = Path(root) / "build/disc-assets"; game = (disc / "COMMON/GAME.BIN").read_bytes()
	def game_word(address): return struct.unpack_from("<I", game, 48 + address - 0x800AD000)[0]
	for stage in ("ST0D", "ST0F"):
		blob = (disc / "DAT" / (stage + "T.BIN")).read_bytes(); code = blob[48:48 + struct.unpack_from("<I", blob, 4)[0]]; print(stage, "init", hex(game_word(0x800DBEA0 + int(stage[2:], 16) * 4)), "update", hex(game_word(0x800DC66C + int(stage[2:], 16) * 4)))
		for offset in range(0, len(code) - 4, 4):
			word = struct.unpack_from("<I", code, offset)[0]
			if word == 0x0C0302C3:
				for ins in decoder.disasm(code[max(0, offset - 16):offset + 8], mine_BASE + max(0, offset - 16)): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for scene in range(0x50, 0x55):
		handler = game_word(0x800DC490 + scene * 4); print("scene", hex(scene), "handler", hex(handler)); blob = (disc / "DAT/ST0FT.BIN").read_bytes()
		for ins in decoder.disasm(blob[48 + handler - mine_BASE:48 + handler - mine_BASE + 0x180], handler): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for start, end in ((0x800FE774, 0x800FE9E0), (0x800FEB64, 0x800FED6C)):
		for ins in decoder.disasm(blob[48 + start - mine_BASE:48 + end - mine_BASE], start): print(hex(ins.address), ins.mnemonic, ins.op_str)
def detail(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	import models
	mine_load(root); decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); game = fire_D["game"]
	for ins in decoder.disasm(game[48 + 0x800C0D70 - 0x800AD000:48 + 0x800C0EA8 - 0x800AD000], 0x800C0D70): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for ins in decoder.disasm(game[48 + 0x800C1204 - 0x800AD000:48 + 0x800C13A0 - 0x800AD000], 0x800C1204): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for start, end in ((0x800C0C5C, 0x800C0D70), (0x800C1B88, 0x800C1CCC)):
		for ins in decoder.disasm(game[48 + start - 0x800AD000:48 + end - 0x800AD000], start): print(hex(ins.address), ins.mnemonic, ins.op_str)
	for name in ("ST0F00.BIN", "ST0F01.BIN"):
		archive, _ = models.actor_archive(Path(root) / "build/disc-assets/DAT" / name); print(name, [(model["index"], hex(model["flags"]), model["mesh"]["bone_count"]) for model in archive["models"]])
	for address in (0x801007EC, 0x80100814, 0x80100828, 0x8010083C, 0x80100850, 0x80100864, 0x80100878): print("ordinary_actor", fire_record(address))
def actor_detail(root=ROOT):
	from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN
	overlay = mine_load(root); decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN); e = stage_emulator(0x800E71B8, 0x800F22B8, mine_BASE + struct.unpack_from("<I", overlay, 4)[0])(); table = e.u32(0x80078FA8)
	for actor_class in (0x55, 0x60):
		cell = e.u32(table + actor_class * 4); callback = e.u32(cell); print("actor_callback", hex(actor_class), hex(cell), hex(callback))
		for ins in decoder.disasm(overlay[48 + callback - mine_BASE:48 + callback - mine_BASE + 0x500], callback): print(hex(ins.address), ins.mnemonic, ins.op_str)
	executable = fire_D["disc"].joinpath("SLES_035.56").read_bytes()
	for ins in decoder.disasm(executable[0x800 + 0x8003F4BC - 0x80010000:0x800 + 0x8003F5A0 - 0x80010000], 0x8003F4BC): print(hex(ins.address), ins.mnemonic, ins.op_str)

import models
import ui
import world

if __name__ == '__main__':
	import sys
	commands = {'opening': 'opening_cli', 'opening-effects': 'export_opening_effects'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
