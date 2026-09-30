from __future__ import annotations
import hashlib
import math
import struct
import wave
from array import array
from collections import defaultdict
from pathlib import Path
from disc import SECTION_TYPES, write_output
import argparse
import ctypes
import ctypes.util
import sys
import json
import re
import shutil
import subprocess
import urllib.request
import zipfile
import io
import inspect
from functools import lru_cache
ROOT = Path(__file__).resolve().parents[1]
PCM_CACHE = {}
REVERB_CACHE = {}
def wave_metadata(path):
	with wave.open(str(path), "rb") as source:
		pcm = source.readframes(source.getnframes()); channels = source.getnchannels(); frames = source.getnframes(); rate = source.getframerate(); width = source.getsampwidth()
	if width != 2: raise ValueError("Expected signed16 native PCM")
	return {"sample_rate": rate, "channels": channels, "frames": frames, "duration_seconds": frames / rate, "peak": max((abs(value) for value in array("h", pcm)), default=0), "pcm_sha256": hashlib.sha256(pcm).hexdigest()}
def pcm_signature(encoded, pitch, adsr): return hashlib.sha256(encoded + struct.pack("<II", pitch, adsr)).hexdigest()
def bank_signature(bank):
	metadata = bytearray(bank["data"][bank["payload"]:bank["payload"] + bank["programs"] * 328])
	for program in range(bank["programs"]):
		for tone in range(metadata[program * 8]):
			offset = bank["programs"] * 8 + program * 320 + tone * 20; struct.pack_into("<I", metadata, offset, (u32(metadata, offset) - bank["spu_offset"]) & 0xffffffff)
	return hashlib.sha256(metadata + bank["data"][bank["waveform"]:bank["waveform"] + bank["waveform_size"]]).hexdigest()
def reverb_signature(digest, profile, gain): return hashlib.sha256((digest + json.dumps(profile, sort_keys=True) + repr(gain)).encode()).hexdigest()
def seed_audio_cache(executable):
	profile = reverb_profile(executable); archives = {}
	for manifest in sorted((ROOT / "assets/audio").glob("*/manifest.json"), key=lambda path: (path.parent.name != "ST0F", str(path))):
		data = json.loads(manifest.read_text(encoding="utf-8"))
		for entry in data.get("effects", {}).values():
			if not all(key in entry for key in ["source", "adpcm_file_offset", "adpcm_bytes", "raw_tone", "spu_pitch", "file", "pcm_sha256"]): continue
			archive = ROOT / "build/disc-assets" / entry["source"]
			if archive not in archives: archives[archive] = archive.read_bytes()
			source = archives[archive]; offset = int(entry["adpcm_file_offset"], 16); encoded = source[offset:offset + int(entry["adpcm_bytes"])]; raw = bytes.fromhex(entry["raw_tone"]); signature = pcm_signature(encoded, int(entry["spu_pitch"]), struct.unpack_from("<I", raw, 14)[0]); filename = str(entry["file"]); path = ROOT / filename.removeprefix("res://") if filename.startswith("res://") else manifest.parent / filename
			if path.is_file() and signature not in PCM_CACHE:
				metadata = wave_metadata(path)
				if metadata["pcm_sha256"] == entry["pcm_sha256"]: PCM_CACHE[signature] = (path, {**metadata, "dsp": entry.get("dsp", {})})
			wet = entry.get("reverb", {}); filename = str(wet.get("file", "")); path = ROOT / filename.removeprefix("res://") if filename.startswith("res://") else manifest.parent / filename
			if wet.get("profile") == profile["profile"] and wet.get("gain_baked") == entry.get("gain") and reverb_signature(entry["pcm_sha256"], profile, entry["gain"]) not in REVERB_CACHE and path.is_file():
				metadata = wave_metadata(path)
				if metadata["pcm_sha256"] == wet.get("pcm_sha256"): REVERB_CACHE[reverb_signature(entry["pcm_sha256"], profile, entry["gain"])] = (path, dict(wet))
def write_wave(path, channels, rate, pcm):
	buffer = io.BytesIO()
	with wave.open(buffer, "wb") as output: output.setnchannels(channels); output.setsampwidth(2); output.setframerate(rate); output.writeframes(pcm)
	write_output(path, buffer.getvalue())
def referenced_effect(encoded, pitch, raw, destination):
	signature = pcm_signature(encoded, pitch, struct.unpack_from("<I", raw, 14)[0])
	if signature not in PCM_CACHE: render_effect(encoded, pitch, raw, destination.with_name("fx_" + signature[:32] + ".wav"))
	path, metadata = PCM_CACHE[signature]; return {**metadata, "file": "res://" + path.relative_to(ROOT).as_posix(), "owner_stage": path.parent.name}
def referenced_reverb(effect, output, profile):
	source = ROOT / effect["file"].removeprefix("res://"); signature = reverb_signature(effect["pcm_sha256"], profile, effect["gain"])
	if signature not in REVERB_CACHE: render_reverb(source, output / ("fx_" + signature[:32] + "_reverb.wav"), profile, effect["gain"])
	path, metadata = REVERB_CACHE[signature]; return {**metadata, "file": "res://" + path.relative_to(ROOT).as_posix(), "source_waveform": effect["file"], "owner_stage": path.parent.name}
def canonicalize_audio_resources():
	root = ROOT / "assets/audio"; documents = {path: json.loads(path.read_text(encoding="utf-8")) for path in root.glob("*/manifest.json")}; canonical = {}; aliases = {}
	for path in sorted(root.glob("*/*.wav"), key=lambda path: (path.parent.name != "ST0F", str(path))): aliases[path.resolve()] = canonical.setdefault(hashlib.sha256(path.read_bytes()).digest(), path)
	def rewrite(value, directory):
		if isinstance(value, dict):
			filename = value.get("file", "")
			if isinstance(filename, str) and filename.endswith(".wav"):
				path = (ROOT / filename.removeprefix("res://") if filename.startswith("res://") else directory / filename).resolve(); target = aliases.get(path)
				if target is not None: value["file"] = "res://" + target.relative_to(ROOT).as_posix(); value["owner_stage"] = target.parent.name
			filename = value.get("source_waveform", "")
			if isinstance(filename, str) and filename.endswith(".wav"):
				path = (ROOT / filename.removeprefix("res://") if filename.startswith("res://") else directory / filename).resolve(); target = aliases.get(path)
				if target is not None: value["source_waveform"] = "res://" + target.relative_to(ROOT).as_posix()
			for item in value.values(): rewrite(item, directory)
		elif isinstance(value, list):
			for item in value: rewrite(item, directory)
	for path, data in documents.items(): rewrite(data, path.parent)
	baseline = documents[OUTPUT / "manifest.json"]
	for path, data in documents.items():
		stage = path.parent.name; data["audio_dependencies"] = sorted({entry["owner_stage"] for effect in data.get("effects", {}).values() if not effect.get("logical_effect") for entry in [effect, effect.get("reverb", effect)] if entry.get("owner_stage") and entry["owner_stage"] != stage})
		if stage in baseline.get("audio_catalog", {}).get("zones", {}): baseline["audio_catalog"]["zones"][stage]["audio_dependencies"] = data["audio_dependencies"]
	for path, data in documents.items(): write_output(path, json.dumps(data, indent=2) + "\n")
def prune_audio_duplicates():
	references = set(); files = list((ROOT / "assets/audio").glob("*/*.wav"))
	def collect(value, directory):
		if isinstance(value, dict):
			for key, item in value.items():
				if key == "file" and isinstance(item, str) and item.endswith(".wav"): references.add((ROOT / item.removeprefix("res://") if item.startswith("res://") else directory / item).resolve())
				else: collect(item, directory)
		elif isinstance(value, list):
			for item in value: collect(item, directory)
	for manifest in (ROOT / "assets/audio").glob("*/manifest.json"): collect(json.loads(manifest.read_text(encoding="utf-8")), manifest.parent)
	digests = {path: hashlib.sha256(path.read_bytes()).digest() for path in files}; retained = {}; removed = size = 0
	for path in sorted(files, key=lambda path: (path.resolve() not in references, str(path))): retained.setdefault(digests[path], path)
	for path in files:
		if not path.resolve().is_relative_to((ROOT / "assets/audio").resolve()) or not re.fullmatch(r"(?:fx_(?:[0-9a-f]{3}|[0-9a-f]{32})|footstep|music_[0-9a-f]{2})(?:_reverb)?\.wav", path.name) or path.resolve() in references or path == retained[digests[path]]: continue
		size += path.stat().st_size; path.unlink(); path.with_name(path.name + ".import").unlink(missing_ok=True); removed += 1
	return {"removed_files": removed, "removed_bytes": size}
def stage_reverb_flags(directory):
	result = {}
	for path in sorted(Path(directory).glob("*T.BIN")):
		data = path.read_bytes()[0x30:]; calls = []
		for offset in range(0, len(data) - 7, 4):
			word = struct.unpack_from("<I", data, offset)[0]
			if word != 0x0C0075F1: continue
			value = None
			for cursor in [offset + 4] + list(range(offset - 4, max(-1, offset - 260), -4)):
				instruction = struct.unpack_from("<I", data, cursor)[0]; opcode = instruction >> 26; rs = (instruction >> 21) & 31; rt = (instruction >> 16) & 31; rd = (instruction >> 11) & 31
				if cursor != offset + 4 and opcode == 3: break
				if opcode in (9, 13) and rt == 5:
					if rs == 0: value = instruction & 65535
					break
				if opcode == 0 and rd == 5 and (instruction & 63) in (33, 37):
					if rs == 0 and rt == 0: value = 0
					break
			calls.append({"source_pc": hex(0x800E7000 + offset), "flags": value})
		if not calls: continue
		bits = {call["flags"] & 1 for call in calls if call["flags"] is not None}
		if len(bits) != 1 or any(call["flags"] is None for call in calls): continue
		result[path.stem[:-1]] = {"enabled": bool(bits.pop()), "source": path.name, "calls": calls}
	if "ST40" in result: result["ST40"]["areas"] = {"1": True}; result["ST40"]["area_default"] = False; result["ST40"]["area_source"] = "ST40T0x800E7588..0x800E75AC -> SLES0x8001D834"
	return result
def reverb_profile(exe):
	profile = 1; descriptor = 0x800696A8 + profile * 20; file_offset = descriptor - 0x80010000 + 0x800; mask, mode, left, right, delay, feedback = struct.unpack_from("<IIhhII", exe, file_offset); preset = mode & 255; register_offset = 0x80071914 + preset * 68 + 4 - 0x80010000 + 0x800; registers = list(struct.unpack_from("<32H", exe, register_offset)); base = struct.unpack_from("<I", exe, 0x800718E4 + preset * 4 - 0x80010000 + 0x800)[0] << 3
	return {"profile": profile, "mode": preset, "depth": [left, right], "delay": delay, "feedback": feedback, "registers": registers, "work_area_start": base, "source": "SLES0x8001D6A4 ->0x8001FF68 profile1; descriptor0x%08X; SDK0x800540F0" % descriptor}
def render_reverb(source, destination, profile, gain):
	digest = wave_metadata(source)["pcm_sha256"]; signature = reverb_signature(digest, profile, gain)
	if signature in REVERB_CACHE:
		path, metadata = REVERB_CACHE[signature]; write_output(destination, path.read_bytes()); return {**metadata, "file": destination.name, "source_waveform": source.name}
	with wave.open(str(source), "rb") as original:
		if original.getnchannels() != 1 or original.getframerate() != 44100 or original.getsampwidth() != 2: raise ValueError("Native effect PCM must be mono signed16 at44100Hz")
		samples = array("h", original.readframes(original.getnframes()))
	registers = profile["registers"]; signed = [(value & 32767) - (value & 32768) for value in registers]; memory_size = (0x80000 - profile["work_area_start"]) // 2; memory = array("h", [0]) * memory_size; cursor = 0; wet = [0, 0]; hold = 0; phase = 0; output = array("h"); quiet = 0; peak = 0; tail_start = len(samples)
	feedback = max(abs(signed[index] / 32768.0) for index in (7, 8, 9)); cycles = max(1, math.ceil(math.log(1.0 / 65536.0) / math.log(feedback))) if feedback > 0 else 1; maximum = len(samples) + memory_size * 2 * (cycles + 2)
	def clamp(value): return max(-32768, min(32767, value))
	def read(index, bias=0): return memory[(cursor + registers[index] * 4 + bias) % memory_size]
	def write(index, value): memory[(cursor + registers[index] * 4) % memory_size] = clamp(value)
	def multiply(index, value): return (signed[index] * value) >> 15
	for frame in range(maximum):
		dry = clamp(round(samples[frame] * gain)) if frame < len(samples) else 0
		if phase == 0: hold = dry; reconstructed = wet[:]; phase = 1
		else:
			previous = wet[:]; incoming = (hold + dry) >> 1
			for destination_register, source_register, channel in [(10, 16, 0), (11, 17, 1), (18, 25, 0), (19, 24, 1)]:
				prior = read(destination_register, -1); write(destination_register, multiply(2, multiply(30 + channel, incoming) + multiply(7, read(source_register)) - prior) + prior)
			for channel in range(2):
				value = sum(multiply(3 + index, read(register + channel)) for index, register in enumerate((12, 14, 20, 22)))
				for volume, destination_register, delay_register in [(8, 26 + channel, 0), (9, 28 + channel, 1)]:
					value -= multiply(volume, read(destination_register, -registers[delay_register] * 4)); write(destination_register, value); value = multiply(volume, clamp(value)) + read(destination_register, -registers[delay_register] * 4)
				wet[channel] = (profile["depth"][channel] * clamp(value)) >> 15
			cursor = (cursor + 1) % memory_size; reconstructed = [(previous[channel] + wet[channel]) >> 1 for channel in range(2)]; phase = 0
		values = [clamp(dry + value) for value in reconstructed]; output.extend(values); peak = max(peak, *(abs(value) for value in values))
		if frame >= tail_start:
			quiet = quiet + 1 if max(abs(value) for value in values) <= 8 else 0
			if quiet >= memory_size * 2: break
	write_wave(destination, 2, 44100, output.tobytes())
	metadata = {"file": destination.name, "sample_rate": 44100, "channels": 2, "frames": len(output) // 2, "duration_seconds": len(output) / 88200.0, "tail_frames": len(output) // 2 - len(samples), "volume_db": 0.0, "gain_baked": gain, "peak": peak, "pcm_sha256": hashlib.sha256(output.tobytes()).hexdigest(), "source_waveform": source.name, "profile": profile["profile"], "boundary_filter": "Local SPU reference two-frame input average and linear output reconstruction", "hardware_dsp_parity": "unverified", "tail_threshold_pcm16": 8, "tail_window_frames": memory_size * 2}; REVERB_CACHE[signature] = (destination, metadata); return metadata
def export_reverb(exe, effects, output, stage_directory):
	profile = reverb_profile(exe)
	for key, effect in effects.items():
		if not bytes.fromhex(effect["raw_tone"])[5]: continue
		source = output / effect["file"]; destination = source.with_name(source.stem + "_reverb.wav"); effect["reverb"] = render_reverb(source, destination, profile, effect["gain"])
	return {"profile": profile, "stages": stage_reverb_flags(stage_directory), "selection_source": "SLES0x8001D7C4 ->0x8001D834 flags;0x8001ED94..0x8001EDD4 tone.byte5 andglobalflags.bit0", "reference": "psxrecomp/runtime/src/spu.c reverb_step/rev_reconstruct", "mix_limits": "Each effect is rendered into a cleared reverb work area; simultaneous voices do not share hardware clipping or history"}

SECTION_TYPES.update({9, 16})
OUTPUT = ROOT / "assets/audio/ST0F"
WORK = ROOT / "build/audio"
SPU_GAUSSIAN = (
 -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 3, 3,
 3, 4, 4, 5, 5, 6, 7, 7, 8, 9, 9, 10, 11, 12, 13, 14,
 15, 16, 17, 18, 19, 21, 22, 24, 25, 27, 28, 30, 32, 33, 35, 37,
 39, 41, 44, 46, 48, 51, 53, 56, 58, 61, 64, 67, 70, 73, 77, 80,
 84, 87, 91, 95, 99, 103, 107, 111, 116, 120, 125, 130, 135, 140, 145, 150,
 156, 161, 167, 173, 179, 186, 192, 199, 205, 212, 219, 227, 234, 242, 250, 257,
 266, 274, 283, 291, 300, 309, 319, 328, 338, 348, 358, 369, 379, 390, 401, 412,
 424, 436, 448, 460, 473, 485, 498, 512, 525, 539, 553, 567, 582, 597, 612, 627,
 643, 659, 675, 692, 708, 726, 743, 761, 779, 797, 816, 835, 854, 874, 894, 914,
 935, 956, 977, 999, 1020, 1043, 1066, 1089, 1112, 1136, 1160, 1184, 1209, 1234, 1260, 1286,
 1312, 1339, 1366, 1394, 1422, 1450, 1479, 1508, 1537, 1567, 1598, 1628, 1660, 1691, 1723, 1756,
 1789, 1822, 1856, 1890, 1924, 1959, 1995, 2031, 2067, 2104, 2141, 2179, 2217, 2256, 2295, 2334,
 2374, 2415, 2456, 2497, 2539, 2582, 2624, 2668, 2712, 2756, 2801, 2846, 2892, 2938, 2985, 3032,
 3079, 3128, 3176, 3225, 3275, 3325, 3376, 3427, 3479, 3531, 3584, 3637, 3691, 3745, 3799, 3855,
 3910, 3967, 4023, 4081, 4138, 4197, 4255, 4315, 4374, 4435, 4495, 4557, 4619, 4681, 4744, 4807,
 4871, 4935, 5000, 5065, 5131, 5197, 5264, 5332, 5399, 5468, 5536, 5606, 5676, 5746, 5817, 5888,
 5959, 6032, 6104, 6177, 6251, 6325, 6400, 6475, 6550, 6626, 6702, 6779, 6856, 6934, 7012, 7091,
 7170, 7249, 7329, 7409, 7490, 7571, 7653, 7735, 7817, 7900, 7983, 8066, 8150, 8234, 8319, 8404,
 8489, 8575, 8661, 8748, 8834, 8922, 9009, 9097, 9185, 9273, 9362, 9451, 9541, 9630, 9720, 9811,
 9901, 9992, 10083, 10174, 10266, 10358, 10450, 10542, 10635, 10727, 10820, 10913, 11007, 11100, 11194, 11288,
 11382, 11476, 11571, 11665, 11760, 11855, 11950, 12045, 12140, 12236, 12331, 12427, 12522, 12618, 12714, 12809,
 12905, 13001, 13097, 13193, 13289, 13385, 13481, 13577, 13673, 13769, 13865, 13961, 14056, 14152, 14248, 14343,
 14439, 14534, 14630, 14725, 14820, 14915, 15010, 15104, 15199, 15293, 15387, 15481, 15575, 15669, 15762, 15855,
 15948, 16041, 16133, 16226, 16317, 16409, 16500, 16592, 16682, 16773, 16863, 16953, 17042, 17131, 17220, 17308,
 17396, 17484, 17571, 17658, 17744, 17830, 17916, 18001, 18086, 18170, 18254, 18337, 18420, 18502, 18584, 18665,
 18746, 18826, 18905, 18985, 19063, 19141, 19219, 19295, 19372, 19447, 19522, 19597, 19671, 19744, 19816, 19888,
 19959, 20030, 20100, 20169, 20238, 20306, 20373, 20439, 20505, 20570, 20634, 20698, 20760, 20822, 20884, 20944,
 21004, 21063, 21121, 21178, 21235, 21290, 21345, 21399, 21452, 21505, 21556, 21607, 21657, 21706, 21754, 21801,
 21848, 21893, 21938, 21982, 22025, 22066, 22107, 22148, 22187, 22225, 22262, 22299, 22334, 22369, 22402, 22435,
 22467, 22498, 22527, 22556, 22584, 22611, 22637, 22662, 22686, 22709, 22731, 22752, 22772, 22791, 22809, 22826,
 22842, 22857, 22872, 22885, 22897, 22908, 22918, 22927, 22935, 22942, 22948, 22953, 22957, 22960, 22962, 22963,
)
def u32(data, offset): return struct.unpack_from("<I", data, offset)[0]
def bank_data(path, offset):
	data = path.read_bytes()
	if u32(data, offset) not in (5, 14): raise ValueError(f"Expected original sound bank at {path.name}+{offset:#x}")
	programs = struct.unpack_from("<H", data, offset + 0x1c)[0]; metadata_size = u32(data, offset + 0x14); payload = offset + 0x30; waveform = (payload + metadata_size + 0x7ff) & ~0x7ff
	if any(data[payload + metadata_size:waveform]): raise ValueError(f"Sound bank metadata padding is not empty in {path.name}")
	return {"data": data, "path": path, "offset": offset, "programs": programs, "payload": payload, "waveform": waveform, "waveform_size": u32(data, offset + 0x18), "spu_offset": u32(data, offset + 0x10), "volume": data[offset + 0x1e], "logical_id": struct.unpack_from("<H", data, offset + 0xe)[0], "physical_slot": struct.unpack_from("<H", data, offset + 0xc)[0]}
def tone_data(bank, program, tone):
	if program >= bank["programs"] or tone >= bank["data"][bank["payload"] + program * 8]: raise ValueError(f"Original sound program/tone {program}/{tone} does not exist")
	offset = bank["payload"] + bank["programs"] * 8 + program * 0x140 + tone * 20; raw = bank["data"][offset:offset + 20]; relative = u32(raw, 0) - bank["spu_offset"]; start = bank["waveform"] + relative; end = bank["waveform"] + bank["waveform_size"]; blocks = []; loop_start = None
	if relative < 0 or start >= end: raise ValueError("Original sound address is outside its waveform bank")
	for position in range(start, end - 15, 16):
		block = bank["data"][position:position + 16]
		if block[0] >> 4 > 4 or block[0] & 15 > 12: raise ValueError(f"Invalid original ADPCM header at {bank['path'].name}+{position:#x}")
		if block[1] & 4: loop_start = len(blocks) * 28
		blocks.append(block)
		if block[1] & 1: break
	else: raise ValueError("Original ADPCM sample has no terminal block")
	return raw, b"".join(blocks), {"tone_file_offset": hex(offset), "adpcm_file_offset": hex(start), "adpcm_bytes": len(blocks) * 16, "decoded_frames": len(blocks) * 28, "loop_start_frame": loop_start, "looped": bool(blocks[-1][1] & 2), "adsr1": hex(struct.unpack_from("<H", raw, 0xe)[0]), "adsr2": hex(struct.unpack_from("<H", raw, 0x10)[0]), "raw_tone": raw.hex()}
def native_pitch(exe, semitones):
	octave, note = divmod(abs(semitones), 12); address = 0x8006ae74 if semitones < 0 else 0x8006ae44; multiplier = u32(exe, address - 0x80010000 + 0x800 + note * 4); base = 4096 >> octave if semitones < 0 else 4096 << octave
	return (base * multiplier) >> 16
def spu_adpcm(encoded):
	history1 = history2 = 0; samples = []; filter0 = (0, 60, 115, 98, 122); filter1 = (0, 0, -52, -55, -60)
	for offset in range(0, len(encoded), 16):
		block = encoded[offset:offset + 16]; shift = min(12, block[0] & 15); predictor = block[0] >> 4; predictor = predictor if predictor < 5 else 0
		for packed in block[2:]:
			for nibble in (packed & 15, packed >> 4):
				value = nibble - 16 if nibble & 8 else nibble; value = ((value << 12) >> shift) + ((history1 * filter0[predictor] + history2 * filter1[predictor] + 32) >> 6); value = max(-32768, min(32767, value)); history2, history1 = history1, value; samples.append(value)
	return samples
def spu_envelope(level, phase, divider, adsr):
	if phase == 0 and level == 32767: phase = 1
	if phase == 0: zero_speed, speed, logarithmic, decreasing, inverse, reset = 127, (adsr >> 8) & 127, (adsr >> 15) & 1, 0, 0, 32767
	elif phase == 1: zero_speed, speed, logarithmic, decreasing, inverse, reset = 124, ((adsr >> 4) & 15) << 2, 1, 1, 1, 0
	elif phase == 2: zero_speed, speed, logarithmic, decreasing, inverse, reset = 127, (adsr >> 22) & 127, (adsr >> 31) & 1, (adsr >> 30) & 1, (adsr >> 30) & 1, 0 if adsr & (1 << 30) else 32767
	else: zero_speed, speed, logarithmic, decreasing, inverse, reset = 124, ((adsr >> 16) & 31) << 2, (adsr >> 21) & 1, 1, 1, 0
	increment = 7 - (speed & 3); increment = ~increment if inverse else increment; division_increment = 32768
	if speed < 44: increment <<= (47 - speed) >> 2
	if speed >= 48: division_increment >>= (speed - 44) >> 2
	if logarithmic:
		if decreasing: increment = (level * increment) >> 15
		elif level >= 24576:
			if speed < 40: increment >>= 2
			elif speed >= 44: division_increment >>= 2
			else: increment >>= 1; division_increment >>= 1
	if division_increment == 0 and speed < zero_speed: division_increment = 1
	divider += division_increment
	if divider & 32768:
		previous = level; divider = 0; level = (level + increment) & 65535
		if ((previous ^ level) & level & 32768) if phase == 0 else (level & 32768): level = reset
		if phase == 1 and level < (((adsr & 15) + 1) << 11): phase = 2
	return level, phase, divider
def preserve_effect_pcm(destination):
	path = destination.with_name(destination.name + ".import")
	if not path.is_file(): return
	with path.open("r", encoding="utf-8", newline="") as source: text = source.read()
	updated, count = re.subn(r"(?m)^compress/mode=[^\r\n]*", "compress/mode=0", text)
	if not count and "[params]" in text: updated = text.replace("[params]", "[params]\ncompress/mode=0", 1)
	if updated != text:
		with path.open("w", encoding="utf-8", newline="") as output: output.write(updated)
def render_effect(encoded, pitch, tone, destination):
	if pitch <= 0: raise ValueError("A parked native SPU voice cannot be exported as a finite effect")
	signature = pcm_signature(encoded, pitch, struct.unpack_from("<I", tone, 14)[0])
	if signature in PCM_CACHE:
		path, metadata = PCM_CACHE[signature]; write_output(destination, path.read_bytes()); preserve_effect_pcm(destination); return dict(metadata)
	samples = spu_adpcm(encoded); adsr = struct.unpack_from("<I", tone, 14)[0]; position = fraction = level = phase = divider = 0; pcm = bytearray(); peak = 0
	while position < len(samples):
		index = (fraction >> 4) & 255; accumulator = 0
		for back, coefficient in zip((3, 2, 1, 0), (255 - index, 511 - index, 256 + index, index)): accumulator += SPU_GAUSSIAN[coefficient] * (samples[position - back] if position >= back else 0)
		value = ((accumulator >> 15) + 32768) % 65536 - 32768; value = max(-32768, min(32767, (value * level) >> 15)); pcm.extend(struct.pack("<h", value)); peak = max(peak, abs(value)); level, phase, divider = spu_envelope(level, phase, divider, adsr); fraction += pitch; position += fraction >> 12; fraction &= 4095
	write_wave(destination, 1, 44100, pcm)
	preserve_effect_pcm(destination)
	metadata = {"sample_rate": 44100, "channels": 1, "frames": len(pcm) // 2, "duration_seconds": len(pcm) / 88200, "peak": peak, "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "dsp": {"adpcm": "Reference integer predictor/history/clamp", "interpolation": "Reference four-tap PS1 Gaussian, native pitch counter", "envelope": "Reference PS1 ADSR divider/rate stepping at44100Hz", "gain": "Bank/program/tone gain remains in volume_db", "reverb": "unverified; not rendered", "source": "psxrecomp/runtime/src/spu.c decode_block/calc_vc_delta/adsr_run and runtime/include/spu_gauss.h", "gaussian_table_sha256": hashlib.sha256(struct.pack("<512h", *SPU_GAUSSIAN)).hexdigest()}}; PCM_CACHE[signature] = (destination, metadata); return metadata
def decode_sample(ffmpeg, encoded, sample_rate, destination, stem):
	vag = WORK / (stem + ".vag"); header = struct.pack(">4s4I12x16s", b"VAGp", 0x20, 0, len(encoded), sample_rate, stem.encode("ascii")[:16]); write_output(vag, header + encoded)
	subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(vag), "-c:a", "pcm_s16le", str(destination)], check=True)
	with wave.open(str(destination), "rb") as audio:
		pcm = audio.readframes(audio.getnframes()); samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm); peak = max(abs(sample) for sample in samples) if samples else 0
		return {"sample_rate": audio.getframerate(), "channels": audio.getnchannels(), "frames": audio.getnframes(), "duration_seconds": audio.getnframes() / audio.getframerate(), "peak": peak, "pcm_sha256": hashlib.sha256(pcm).hexdigest()}
def riff_chunk(name, data): return name + struct.pack("<I", len(data)) + data + (b"\0" if len(data) & 1 else b"")
def riff_list(name, chunks): return riff_chunk(b"LIST", name + b"".join(chunks))
def soundfont(bank, ffmpeg, stem):
	pcm = bytearray(); samples = bytearray(); presets = bytearray(); preset_bags = bytearray(); preset_generators = bytearray(); instruments = bytearray(); instrument_bags = bytearray(); instrument_generators = bytearray(); sample_index = 0; generator_index = 0; zone_index = 0
	for program in range(bank["programs"]):
		presets.extend(struct.pack("<20sHHHIII", f"Original {program}".encode(), program, 0, program, 0, 0, 0)); preset_bags.extend(struct.pack("<HH", program, 0)); preset_generators.extend(struct.pack("<HH", 41, program)); instruments.extend(struct.pack("<20sH", f"Program {program}".encode(), zone_index))
		for tone in range(bank["data"][bank["payload"] + program * 8]):
			raw, encoded, provenance = tone_data(bank, program, tone); wave_path = WORK / f"{stem}_{program}_{tone}.wav"; decode_sample(ffmpeg, encoded, 44100, wave_path, f"{stem}_{program}_{tone}")
			with wave.open(str(wave_path), "rb") as source: data = source.readframes(source.getnframes())
			start = len(pcm) // 2; length = len(data) // 2; pcm.extend(data); pcm.extend(b"\0" * 92); loop_start = provenance["loop_start_frame"] or 0; samples.extend(struct.pack("<20sIIIIIBbHH", f"Sample {sample_index}".encode(), start, start + length, start + loop_start, start + length, 44100, raw[8], 0, 0, 1)); instrument_bags.extend(struct.pack("<HH", generator_index, 0)); gain = bank["volume"] * bank["data"][bank["payload"] + program * 8 + 1] * raw[6] / (127 ** 3); attenuation = round(-200 * math.log10(max(gain, 1e-8))); pan = round((raw[7] - 64) * 500 / 64); fine = round(1200 * math.log2(1 + (raw[9] / 128) * (2 ** (1 / 12) - 1))); release_shift = struct.unpack_from("<H", raw, 0x10)[0] & 31; release_samples = math.ceil(32767 / (8 << max(0, 11 - release_shift))) * (1 << max(0, release_shift - 11)); release = max(1 / 44100, release_samples / 44100); release_tc = max(-12000, min(8000, round(1200 * math.log2(release))))
			attack_rate = (struct.unpack_from("<H", raw, 0xe)[0] >> 8) & 127; attack_shift = attack_rate >> 2; attack_step = (7 - (attack_rate & 3)) << max(0, 11 - attack_shift); attack_samples = math.ceil(32767 / attack_step) * (1 << max(0, attack_shift - 11)); attack_tc = max(-12000, min(8000, round(1200 * math.log2(max(1, attack_samples) / 44100))))
			generators = [(43, raw[10] | (raw[11] << 8)), (48, attenuation), (17, pan), (52, fine), (58, raw[8]), (34, attack_tc), (36, -12000), (37, 0), (38, release_tc), (54, 1 if provenance["looped"] else 0), (53, sample_index)]
			for operator, amount in generators: instrument_generators.extend(struct.pack("<HH", operator, amount & 65535))
			generator_index += len(generators); zone_index += 1; sample_index += 1
	presets.extend(struct.pack("<20sHHHIII", b"EOP", 0, 0, bank["programs"], 0, 0, 0)); preset_bags.extend(struct.pack("<HH", bank["programs"], 0)); preset_generators.extend(b"\0" * 4); instruments.extend(struct.pack("<20sH", b"EOI", zone_index)); instrument_bags.extend(struct.pack("<HH", generator_index, 0)); instrument_generators.extend(b"\0" * 4); samples.extend(struct.pack("<20sIIIIIBbHH", b"EOS", len(pcm) // 2, len(pcm) // 2, len(pcm) // 2, len(pcm) // 2, 44100, 0, 0, 0, 1)); title = stem.encode() + b"\0"; title += b"\0" if len(title) & 1 else b""; info = riff_list(b"INFO", [riff_chunk(b"ifil", struct.pack("<HH", 2, 1)), riff_chunk(b"isng", b"EMU8000\0"), riff_chunk(b"INAM", title)]); sample_data = riff_list(b"sdta", [riff_chunk(b"smpl", bytes(pcm))]); preset_data = riff_list(b"pdta", [riff_chunk(name, bytes(value)) for name, value in [(b"phdr", presets), (b"pbag", preset_bags), (b"pmod", bytearray(10)), (b"pgen", preset_generators), (b"inst", instruments), (b"ibag", instrument_bags), (b"imod", bytearray(10)), (b"igen", instrument_generators), (b"shdr", samples)]]); target = WORK / (stem + ".sf2"); write_output(target, riff_chunk(b"RIFF", b"sfbk" + info + sample_data + preset_data)); return target
def fluid_library():
	if sys.platform != "win32":
		path = ctypes.util.find_library("fluidsynth")
		if not path: raise RuntimeError("The native FluidSynth shared library is required to render the original scores")
		return ctypes.CDLL(path)
	directory = WORK / "fluidsynth/fluidsynth-v2.6.1-win10-x64-cpp11/bin"; path = directory / "libfluidsynth-3.dll"
	if not path.is_file():
		archive = WORK / "fluidsynth-v2.6.1-win10-x64-cpp11.zip"; urllib.request.urlretrieve("https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.1/fluidsynth-v2.6.1-win10-x64-cpp11.zip", archive)
		with zipfile.ZipFile(archive) as package: package.extractall(WORK / "fluidsynth")
	if hasattr(__import__("os"), "add_dll_directory"): __import__("os").add_dll_directory(str(directory))
	return ctypes.CDLL(str(path))
def score_events(path, section):
	raw = path.read_bytes(); size = u32(raw, section + 4)
	if u32(raw, section) not in (8, 9, 15, 16): raise ValueError("Expected original sequence section")
	data = decompress_section(raw, section)[0] if u32(raw, section) in (9, 16) else raw[section + 0x30:section + 0x30 + size]; tempo = u32(data, 4); division = struct.unpack_from("<H", data, 8)[0]; position = 12; time_ns = 0; running = 0; events = []
	while position < len(data):
		offset = position; status = data[position]
		if status >= 128:
			position += 1
			if status < 240: running = status
		else: status = running
		if status == 255:
			command = data[position]; position += 1
			if command == 81:
				tempo = int.from_bytes(data[position:position + 3], "big"); position += 3; values = [command, tempo]
			elif command == 47:
				if data[position] != 0: raise ValueError("Original EOT payload is not zero")
				position += 1; events.append({"time_ns": time_ns, "status": status, "data": [command], "offset": hex(offset)}); break
			else: raise ValueError(f"Unsupported original sequence command {command:#x} at {offset:#x}")
		else:
			kind = status >> 4; count = 1 if kind in (12, 13) else 2; values = list(data[position:position + count]); position += count
			if kind not in range(8, 15) or any(value > 127 for value in values): raise ValueError(f"Invalid original MIDI event at {offset:#x}")
		events.append({"time_ns": time_ns, "status": status, "data": values, "offset": hex(offset)}); delta = 0
		for index in range(4):
			value = data[position]; position += 1; delta = (delta << 7) | (value & 127)
			if value < 128: break
		else: raise ValueError("Original delta exceeds four VLQ bytes")
		time_ns += delta * max(2400000, tempo * 1000 // division)
	else: raise ValueError("Original sequence has no end event")
	return events, {"sequence_section_offset": hex(section), "sequence_bytes": size, "division": division, "initial_tempo_us": u32(data, 4), "events": len(events), "duration_ns": time_ns, "end_offset": hex(position), "sequence_sha256": hashlib.sha256(data).hexdigest()}
def render_music(ffmpeg, archive, sequence_section, bank_section, stem, output_dir=None):
	bank = bank_data(archive, bank_section); events, provenance = score_events(archive, sequence_section); target = (OUTPUT if output_dir is None else Path(output_dir)) / (stem + ".wav"); event_path = WORK / (stem + "_events.json"); bank_signature = hashlib.sha256(bank["data"][bank["payload"]:bank["waveform"] + bank["waveform_size"]]).hexdigest()
	if target.is_file() and event_path.is_file():
		previous = json.loads(event_path.read_text(encoding="utf-8"))
		if previous.get("sequence_sha256") == provenance["sequence_sha256"] and previous.get("source") == archive.name and (previous.get("bank_sha256") == bank_signature or ("bank_sha256" not in previous and archive.stat().st_mtime_ns <= event_path.stat().st_mtime_ns)):
			metadata = wave_metadata(target); notes = sum(event["status"] >> 4 == 9 and bool(event["data"][1]) for event in events)
			if metadata["sample_rate"] == 44100 and metadata["channels"] == 2 and metadata["frames"] == round(events[-1]["time_ns"] * 44100 / 1000000000) and metadata["peak"] > 0:
				write_output(event_path, json.dumps({"source": archive.name, "bank_sha256": bank_signature, **provenance, "events_data": events}, indent=2) + "\n")
				return {"file": target.name, "source": archive.relative_to(ROOT / "build/disc-assets").as_posix(), "logical_bank": bank["logical_id"], "bank_section_offset": hex(bank_section), "note_on_events": notes, "looped": True, "renderer": "FluidSynth with original ADPCM samples, tone zones and score events", "render_gain": 0.5, "spu_dsp_parity": "unverified", **metadata, **provenance}
	font = soundfont(bank, ffmpeg, stem); library = fluid_library(); void = ctypes.c_void_p; integer = ctypes.c_int; text = ctypes.c_char_p
	for name, arguments, result in [("new_fluid_settings", [], void), ("fluid_settings_setnum", [void, text, ctypes.c_double], integer), ("fluid_settings_setint", [void, text, integer], integer), ("new_fluid_synth", [void], void), ("fluid_synth_sfload", [void, text, integer], integer), ("fluid_synth_program_select", [void, integer, integer, integer, integer], integer), ("fluid_synth_set_channel_type", [void, integer, integer], integer), ("fluid_synth_noteon", [void, integer, integer, integer], integer), ("fluid_synth_noteoff", [void, integer, integer], integer), ("fluid_synth_cc", [void, integer, integer, integer], integer), ("fluid_synth_pitch_bend", [void, integer, integer], integer), ("fluid_synth_channel_pressure", [void, integer, integer], integer), ("fluid_synth_key_pressure", [void, integer, integer, integer], integer), ("fluid_synth_write_s16", [void, integer, void, integer, integer, void, integer, integer], integer), ("delete_fluid_synth", [void], None), ("delete_fluid_settings", [void], None)]:
		function = getattr(library, name); function.argtypes = arguments; function.restype = result
	settings = library.new_fluid_settings(); library.fluid_settings_setnum(settings, b"synth.sample-rate", 44100.0); library.fluid_settings_setnum(settings, b"synth.gain", 0.5); library.fluid_settings_setint(settings, b"synth.reverb.active", 0); library.fluid_settings_setint(settings, b"synth.chorus.active", 0); library.fluid_settings_setint(settings, b"synth.polyphony", 24); synth = library.new_fluid_synth(settings); font_id = library.fluid_synth_sfload(synth, str(font).encode(), 0)
	if font_id < 0: raise RuntimeError("FluidSynth rejected the original instrument SoundFont")
	for channel in range(16): library.fluid_synth_set_channel_type(synth, channel, 0); library.fluid_synth_program_select(synth, channel, font_id, 0, 0)
	target = (OUTPUT if output_dir is None else Path(output_dir)) / (stem + ".wav"); cursor = 0; peak = 0; digest = hashlib.sha256(); notes = 0
	wave_buffer = io.BytesIO()
	with wave.open(wave_buffer, "wb") as output:
		output.setnchannels(2); output.setsampwidth(2); output.setframerate(44100)
		for event in events:
			frame = round(event["time_ns"] * 44100 / 1000000000)
			while cursor < frame:
				count = min(4096, frame - cursor); buffer = (ctypes.c_int16 * (count * 2))(); result = library.fluid_synth_write_s16(synth, count, buffer, 0, 2, buffer, 1, 2)
				if result != 0: raise RuntimeError("FluidSynth failed while rendering the original score")
				pcm = bytes(buffer); output.writeframesraw(pcm); digest.update(pcm); peak = max(peak, max(abs(value) for value in buffer)); cursor += count
			status = event["status"]; kind = status >> 4; channel = status & 15; values = event["data"]
			if kind == 9 and values[1]: library.fluid_synth_noteon(synth, channel, values[0], values[1]); notes += 1
			elif kind == 8 or (kind == 9 and values[1] == 0): library.fluid_synth_noteoff(synth, channel, values[0])
			elif kind == 11: library.fluid_synth_cc(synth, channel, values[0], values[1])
			elif kind == 12:
				if values[0] >= bank["programs"]: raise ValueError("Original score selects an absent source program")
				library.fluid_synth_program_select(synth, channel, font_id, 0, values[0])
			elif kind == 14: library.fluid_synth_pitch_bend(synth, channel, values[0] | (values[1] << 7))
			elif kind == 13: library.fluid_synth_channel_pressure(synth, channel, values[0])
			elif kind == 10: library.fluid_synth_key_pressure(synth, channel, values[0], values[1])
	library.delete_fluid_synth(synth); library.delete_fluid_settings(settings)
	if peak == 0 or notes == 0: raise ValueError("Original score rendering produced no audible samples")
	write_output(target, wave_buffer.getvalue())
	write_output(event_path, json.dumps({"source": archive.name, "bank_sha256": bank_signature, **provenance, "events_data": events}, indent=2) + "\n")
	return {"file": target.name, "source": archive.relative_to(ROOT / "build/disc-assets").as_posix(), "logical_bank": bank["logical_id"], "bank_section_offset": hex(bank_section), "sample_rate": 44100, "channels": 2, "frames": cursor, "duration_seconds": cursor / 44100, "note_on_events": notes, "peak": peak, "looped": True, "pcm_sha256": digest.hexdigest(), "renderer": "FluidSynth with original ADPCM samples, tone zones and score events", "render_gain": 0.5, "spu_dsp_parity": "unverified", **provenance}
def native_levels(bank, program, raw, volume_delta):
	level = int(bank["volume"] * bank["data"][bank["payload"] + program * 8 + 1] * (raw[6] + volume_delta) / 16129); voice = level * level * 16383 // 16129; left = voice * raw[7] >> 7; right = voice * (128 - raw[7]) >> 7; gain = (left + right) / 32768
	return {"native_level": level, "voice_volume": voice, "gain": gain, "volume_db": 20 * math.log10(gain) if gain > 0 else -80, "pan": (right - left) / (right + left) if right + left else 0.0}
def native_descriptor(executable, sound_id):
	address = (0x800696e4 if sound_id < 0x53 else 0x8006997c if sound_id < 0x80 else 0x8006957c) + (sound_id * 8 if sound_id < 0x53 or sound_id >= 0x80 else 0)
	return address, executable[0x800 + address - 0x80010000:0x808 + address - 0x80010000]
def native_audio_sections(path):
	data = Path(path).read_bytes(); result = []
	for offset in range(0, len(data) - 47, 0x400):
		kind, size = struct.unpack_from("<2I", data, offset)
		if kind in (5, 14):
			programs = struct.unpack_from("<H", data, offset + 28)[0]; metadata = u32(data, offset + 20); waves = u32(data, offset + 24)
			if not 0 < programs <= 128 or metadata < programs * 328 or not waves or ((offset + 48 + metadata + 2047) & ~2047) + waves > len(data): continue
			result.append({"kind": kind, "offset": offset, "physical_slot": struct.unpack_from("<H", data, offset + 12)[0], "logical_id": struct.unpack_from("<H", data, offset + 14)[0]})
		elif kind in (8, 9, 15, 16) and size > 0 and offset + 48 + size <= len(data): result.append({"kind": kind, "offset": offset, "sequence_id": struct.unpack_from("<H", data, offset + 22)[0]})
	return result
@lru_cache(maxsize=128)
def music_program(path):
	data = Path(path).read_bytes(); base = u32(data, 12); end = min(len(data), 48 + u32(data, 4)); words = {base + offset - 48: u32(data, offset) for offset in range(48, end - 3, 4)}; calls = [address for address, word in words.items() if word in (0x0c0075f1, 0x0c00806c)]; executable = (Path(path).parent.parent / "SLES_035.56").read_bytes(); music_cues = {cue for cue in range(0x310) if native_descriptor(executable, cue)[1][0] >> 4 in (1, 2, 3)}
	return data, base, end, words, calls, music_cues
def trace_music_initializer(path, area, save_byte14):
	data, base, end, words, calls, music_cues = music_program(Path(path))
	if not calls: return []
	starts = sorted({max(candidates) for call in calls if (candidates := [address for address, word in words.items() if call - 1024 <= address <= call and word >> 16 == 0x27bd and word & 0x8000])})
	if not starts: return []
	registers = [None] * 32; registers[0] = 0; registers[29] = 0x1f801000; pending = [(start, registers.copy(), {}, {}, 0) for start in starts]; result = []
	def read(address, size, memory):
		if address is None: return None
		if address in memory: return memory[address]
		if address == 0x8009c7f9: return area
		if address == 0x8009c7fc: return save_byte14
		if address == 0x8009c7f8: return int(Path(path).stem[2:4], 16)
		position = address - base + 48
		if 48 <= position and position + size <= end: return int.from_bytes(data[position:position + size], "little")
		return None
	def step(word, registers, memory):
		op = word >> 26; rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31; imm = (word & 32767) - (word & 32768); value = None; target = None; left, right = registers[rs], registers[rt]
		if op == 15: target = rt; value = (word & 65535) << 16
		elif op in (8, 9, 12, 13, 14, 10, 11):
			target = rt
			if left is not None: value = (left + imm) & 0xffffffff if op in (8, 9) else left & (word & 65535) if op == 12 else left | (word & 65535) if op == 13 else left ^ (word & 65535) if op == 14 else int((left if op == 11 or left < 0x80000000 else left - 0x100000000) < imm)
		elif op == 0 and word & 63 in (0, 2, 3, 33, 35, 36, 37, 38, 42, 43):
			target = rd; fn = word & 63; shift = (word >> 6) & 31
			if fn in (0, 2, 3) and right is not None: value = (right << shift) & 0xffffffff if fn == 0 else right >> shift if fn == 2 else (right if right < 0x80000000 else right - 0x100000000) >> shift
			elif left is not None and right is not None: value = (left + right) & 0xffffffff if fn == 33 else (left - right) & 0xffffffff if fn == 35 else left & right if fn == 36 else left | right if fn == 37 else left ^ right if fn == 38 else int((left if fn == 43 or left < 0x80000000 else left - 0x100000000) < (right if fn == 43 or right < 0x80000000 else right - 0x100000000))
		elif op in (32, 33, 35, 36, 37):
			target = rt; value = read(None if left is None else (left + imm) & 0xffffffff, {32: 1, 33: 2, 35: 4, 36: 1, 37: 2}[op], memory)
			if value is not None and op in (32, 33) and value & (0x80 if op == 32 else 0x8000): value -= 0x100 if op == 32 else 0x10000
		elif op in (40, 41, 43) and left is not None: memory[(left + imm) & 0xffffffff] = right
		if target is not None and target != 0: registers[target] = value
	while pending:
		pc, registers, memory, flags, ticks = pending.pop()
		while pc in words and ticks < 2048:
			ticks += 1; word = words[pc]; op = word >> 26
			if op in (2, 3):
				target = ((pc + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2); step(words.get(pc + 4, 0), registers, memory)
				if target in (0x8001d7c4, 0x800201b0):
					if registers[4] is not None and (registers[4] & 255 in music_cues or target == 0x8001d7c4 and registers[4] == 255): result.append({"cue": registers[4] & 255, "flags": flags, "source_call": hex(pc)})
					break
				if op == 2: pc = target; continue
				if target == 0x800c05b4 and registers[4] is not None:
					flag = str(registers[4]); values = [flags[flag]] if flag in flags else [False, True]
					for value in values:
						branch_registers = registers.copy(); branch_flags = dict(flags); branch_flags[flag] = value; branch_registers[2] = int(value); pending.append((pc + 8, branch_registers, dict(memory), branch_flags, ticks))
					break
				for register in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25]: registers[register] = None
				pc += 8; continue
			if op in (1, 4, 5, 6, 7):
				rs, rt = (word >> 21) & 31, (word >> 16) & 31; left, right = registers[rs], registers[rt]; imm = (word & 32767) - (word & 32768)
				if left is None or (op in (4, 5) and right is None): break
				signed = left if left < 0x80000000 else left - 0x100000000; take = left == right if op == 4 else left != right if op == 5 else signed <= 0 if op == 6 else signed > 0 if op == 7 else signed < 0 if rt == 0 else signed >= 0 if rt == 1 else None
				if take is None: break
				step(words.get(pc + 4, 0), registers, memory); pc = pc + 4 + imm * 4 if take else pc + 8; continue
			if op == 0 and word & 63 == 8: break
			step(word, registers, memory); pc += 4
	return result
def stage_music_rules(path, areas):
	rules = {}
	for area in areas:
		for variant in range(256):
			for selection in trace_music_initializer(path, area, variant):
				key = (selection["cue"], tuple(sorted(selection["flags"].items())), selection["source_call"])
				entry = rules.setdefault(key, {"cue": selection["cue"], "flags": selection["flags"], "source_call": selection["source_call"], "areas": {}}); entry["areas"].setdefault(area, []).append(variant)
	result = []
	for entry in rules.values():
		for area, variants in entry["areas"].items():
			start = previous = variants[0]
			for variant in variants[1:] + [257]:
				if variant != previous + 1: result.append({"cue": entry["cue"], "flags": entry["flags"], "source_call": entry["source_call"], "area": area, "native_save_byte14": [start, previous]}); start = variant
				previous = variant
	return sorted(result, key=lambda entry: entry["cue"] == 255)
def export_audio(cue=None):
	ffmpeg = shutil.which("ffmpeg")
	if not ffmpeg: raise RuntimeError("FFmpeg is required to decode the original PS1 ADPCM samples")
	if cue is not None and not Path(cue).is_file(): raise FileNotFoundError(cue)
	OUTPUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True); exe = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); common_bank = bank_data(ROOT / "build/disc-assets/COMMON/INIT.BIN", 0x9800); banks = {0: common_bank, 1: bank_data(ROOT / "build/disc-assets/DAT/ST0F.BIN", 0x1C800)}; effects = {}
	for sound_id in range(0x80, 0x310):
		address = 0x8006957c + sound_id * 8; offset = address - 0x80010000 + 0x800; descriptor = exe[offset:offset + 8]
		bank = banks.get(descriptor[1])
		if descriptor[0] >> 4 != 0 or bank is None or descriptor[2] >= bank["programs"]: continue
		program = descriptor[2]; tone = descriptor[3] >> 4
		if tone >= bank["data"][bank["payload"] + program * 8]: continue
		raw, encoded, provenance = tone_data(bank, program, tone); note_delta = (descriptor[7] & 31) * (-1 if descriptor[7] & 128 else 1); volume_delta = (descriptor[6] & 63) * (-1 if descriptor[6] & 128 else 1); note = raw[10] + note_delta - raw[8]; pitch = native_pitch(exe, note); pitch += ((native_pitch(exe, note + 1) - pitch) * raw[9]) >> 7; rate = round(44100 * pitch / 4096); name = "footstep" if sound_id == 0x91 else f"fx_{sound_id:03x}"; file = name + ".wav"; decoded = render_effect(encoded, pitch, raw, OUTPUT / file); levels = native_levels(bank, program, raw, volume_delta); gain = levels["gain"]
		effects[f"0x{sound_id:04X}"] = {"file": file, "source": bank["path"].relative_to(ROOT / "build/disc-assets").as_posix(), "bank_section_offset": hex(bank["offset"]), "physical_bank": bank["physical_slot"], "program": program, "tone": tone, "descriptor_address": hex(address), "descriptor": descriptor.hex(), "spu_pitch": pitch, "native_sample_rate": 44100 * pitch / 4096, **levels, **provenance, **decoded}
	manifest = {"stage": "ST0F", "roles": {"footstep": "0x0091", "footstep_alternate": "0x0090"}, "effects": effects, "footstep_events": {"source": "GAME.BIN 0x800CC850..0x800CC8CC, event0x40->sound0x90/event0x80->sound0x91; source surface adds splash actors without changing the cue", "run_control": 1, "run_records": [3, 11], "walk_control": 2, "walk_records": [6, 22]}, "bank_layout": {"source": "SLES 0x800186C4/0x80019798/0x800198BC", "program_header_bytes": 8, "tones_per_program": 16, "tone_bytes": 20, "metadata_file_offset": "0x9830", "waveform_file_offset": hex(common_bank["waveform"]), "waveform_section_alignment": 2048}, "music_source": {"00": {"archive": "DAT/ST0F00.BIN", "sequence_section": "0x13800", "bank_section": "0x16800", "sound_id": "0x0019", "logical_bank": 53, "sequence_id": 21}, "01": {"archive": "DAT/ST0F01.BIN", "sequence_section": "0x11000", "bank_section": "0x14000", "sound_id": "0x0030", "logical_bank": 71, "sequence_id": 39}}, "decoder": "Reference integer PS1 ADPCM + Gaussian + ADSR for effects at44100Hz; original SLES pitch tables control source stepping; FFmpeg ADPCM for score instruments", "reverb": export_reverb(exe, effects, OUTPUT, ROOT / "build/disc-assets/DAT")}
	manifest["stage_music"] = {"ST0F": "music", **{stage: "music_flutter" for stage in ("ST04", "ST05", "ST06", "ST07")}}; manifest["roles"]["music_flutter"] = "0x003B"; manifest["music"] = {"0x003B": render_music(ffmpeg, ROOT / "build/disc-assets/DAT/ST04T.BIN", 0x35800, 0x36000, "music_flutter"), "0x0019": render_music(ffmpeg, ROOT / "build/disc-assets/DAT/ST0F00.BIN", 0x13800, 0x16800, "music_00"), "0x0030": render_music(ffmpeg, ROOT / "build/disc-assets/DAT/ST0F01.BIN", 0x11000, 0x14000, "music_01"), "0x0000": render_music(ffmpeg, ROOT / "build/disc-assets/COMMON/TITLE.BIN", 0x23000, 0x23800, "title_music")}; manifest["roles"].update({"music": "0x0019", "music_alternate": "0x0030", "buster": "0x009A", "kick": "0x0095", "jump": "0x0092", "land": "0x0093", "title_music": "0x0000", "menu_move": "0x0080", "menu_confirm": "0x0081", "menu_cancel": "0x0082"}); manifest["menu_events"] = {"title_music": {"sound_id": "0x0000", "source": "DEMO 0x800AD690 -> SLES 0x80020210, descriptor 0x800696E4=3120000200000000, TITLE compressed type9 sequence0 +0x23000/bank32 +0x23800"}, "menu_move": {"sound_id": "0x0080", "source": "DEMO 0x800AD8E8/0x800AD904, navigation input mask0x50"}, "menu_confirm": {"sound_id": "0x0081", "source": "DEMO 0x800AD750/0x800AD754"}, "menu_cancel": {"sound_id": "0x0082", "source": "DEMO 0x800AD6EC/0x800AD710"}}; manifest["jump_events"] = {"jump": {"sound_id": "0x0092", "source": "GAME 0x800C7810 state; vertical velocity -0x180/-0x2E0 at 0x800C7850/0x800C7860; sound call 0x800C787C, delay-slot ID0x92"}, "land": {"sound_id": "0x0093", "source": "GAME 0x800C81BC -> 0x800C71CC; actor+0x50==0 selects control0x13; sound call 0x800C81E8, delay-slot ID0x93"}}; manifest["kick_event"] = {"weapon_id": 2, "source": "GAME 0x800D03D0 ranged Buster; 0x800D07CC..0x800D07E8 emits sound0x9A; weaponID1/D0194/sound0x95 is kick", "position_source": "player bone7 cache +0x4C8/+0x4CA/+0x4CC"}; write_output(OUTPUT / "manifest.json", json.dumps(manifest, indent=2) + "\n"); return manifest
def export_zone_audio(source_dir=None):
	source_dir = ROOT / "build/disc-assets" if source_dir is None else Path(source_dir); dat = source_dir / "DAT"; ffmpeg = shutil.which("ffmpeg")
	selector_signature = hashlib.sha256("".join(inspect.getsource(function) for function in [music_program, trace_music_initializer, stage_music_rules]).encode()).hexdigest()
	if not ffmpeg: raise RuntimeError("FFmpeg is required to render native zone audio")
	executable = (source_dir / "SLES_035.56").read_bytes(); baseline_path = OUTPUT / "manifest.json"; baseline = json.loads(baseline_path.read_text(encoding="utf-8")); sources = {}; songs = defaultdict(list); seed_audio_cache(executable)
	for path in sorted(source_dir.rglob("*.BIN")):
		sections = native_audio_sections(path)
		if not sections: continue
		sources[path] = sections
		for sequence in [item for item in sections if "sequence_id" in item]:
			for bank in [item for item in sections if "logical_id" in item and item["logical_id"] != 0]: songs[(bank["logical_id"], sequence["sequence_id"])].append((path, sequence["offset"], bank["offset"]))
	catalog = {"source": "SLES0x8001F000 descriptor lookup;0x8001D7C4/0x8001BC4C initializer command7; native bank.logical_id and sequence.header+0x16; type1 logical-bank lookup0x8001EE58 ->0x8001DD3C; cue310 begins loader function table8006ADFC", "music": {}, "music_variants": {}, "effects": {}, "cue_types": {}, "zones": {}, "unresolved_music": []}; known = {**baseline.get("music", {}), **baseline.get("audio_catalog", {}).get("music", {})}
	for sound_id in range(0x310):
		address, descriptor = native_descriptor(executable, sound_id)
		kind = descriptor[0] >> 4
		catalog["cue_types"]["0x%04X" % sound_id] = {"kind": "music" if kind in (2, 3) else "effect", "alias": 0x80 if 0x53 <= sound_id < 0x80 else sound_id}
		if len(descriptor) != 8 or kind not in (2, 3): continue
		candidates = songs.get((descriptor[1], descriptor[2]), []); unique = {}
		for archive, sequence, bank in candidates:
			try:
				_, score = score_events(archive, sequence); native_bank = bank_data(archive, bank); signature = score["sequence_sha256"] + ":" + bank_signature(native_bank); unique.setdefault(signature, (archive, sequence, bank, score))
			except (ValueError, IndexError, struct.error): continue
		if len(unique) != 1:
			resolved = []
			for signature, (archive, sequence, bank, score) in unique.items():
				if not re.fullmatch(r"ST[0-9A-F]{2}T", archive.stem): continue
				owner = archive.stem[:4]; output = ROOT / "assets/audio" / owner; output.mkdir(parents=True, exist_ok=True); entry = baseline.get("audio_catalog", {}).get("music_variants", {}).get(owner, {}).get("0x%04X" % sound_id, {}); entry_path = ROOT / str(entry.get("file", "")).removeprefix("res://")
				if entry.get("bank_sequence_signature") != signature or not entry_path.is_file(): entry = render_music(ffmpeg, archive, sequence, bank, "music_%02x" % sound_id, output); entry["file"] = "res://assets/audio/%s/%s" % (owner, entry["file"])
				else: entry = dict(entry)
				entry.update(owner_stage=owner, cue=sound_id, descriptor=descriptor.hex(), descriptor_address=hex(address), bank_sequence_signature=signature, selection_source="Loaded stage T package bank/sequence; SLES800186E0/800198D8 register logical bank;8001EE58/8001EEE0 resolve loaded IDs")
				catalog["music_variants"].setdefault(owner, {})["0x%04X" % sound_id] = entry; resolved.append(owner)
			catalog["unresolved_music"].append({"cue": sound_id, "descriptor_address": hex(address), "matches": len(unique), "resolved_zones": resolved}); continue
		archive, sequence, bank, score = next(iter(unique.values())); key = "0x%04X" % sound_id; owner = archive.stem[:4] if re.fullmatch(r"ST[0-9A-F]{2}.*", archive.stem) else "ST0F"; output = ROOT / "assets/audio" / owner; output.mkdir(parents=True, exist_ok=True)
		entry = known.get(key, {}); entry_file = str(entry.get("file", "")); entry_path = ROOT / entry_file.removeprefix("res://") if entry_file.startswith("res://") else OUTPUT / entry_file
		if entry.get("sequence_sha256") == score["sequence_sha256"] and int(entry.get("logical_bank", -1)) == descriptor[1] and entry_path.is_file(): entry = dict(entry); entry["file"] = entry_file if entry_file.startswith("res://") else "res://assets/audio/ST0F/" + entry_file; owner = str(entry.get("owner_stage", "ST0F"))
		else:
			entry = render_music(ffmpeg, archive, sequence, bank, "music_%02x" % sound_id, output); entry["file"] = "res://assets/audio/%s/%s" % (owner, entry["file"])
		entry.update(owner_stage=owner, cue=sound_id, descriptor=descriptor.hex(), descriptor_address=hex(address), bank_sequence_signature=next(iter(unique)))
		catalog["music"][key] = entry
	for sound_id in range(0x80, 0x310):
		address, descriptor = native_descriptor(executable, sound_id)
		if descriptor[0] >> 4 != 1: continue
		candidates = {}
		for archive, sections in sources.items():
			for section in sections:
				if section.get("logical_id") != descriptor[1]: continue
				bank = bank_data(archive, section["offset"]); program, tone = descriptor[2], descriptor[3] >> 4
				if program >= bank["programs"] or tone >= bank["data"][bank["payload"] + program * 8]: continue
				raw, encoded, provenance = tone_data(bank, program, tone); signature = hashlib.sha256(raw + encoded).hexdigest(); candidates.setdefault(signature, (bank, raw, encoded, provenance))
		if len(candidates) != 1: continue
		bank, raw, encoded, provenance = next(iter(candidates.values())); archive = bank["path"]; owner = archive.stem[:4] if re.fullmatch(r"ST[0-9A-F]{2}.*", archive.stem) else "ST0F"; output = ROOT / "assets/audio" / owner; output.mkdir(parents=True, exist_ok=True); note_delta = (descriptor[7] & 31) * (-1 if descriptor[7] & 128 else 1); volume_delta = (descriptor[6] & 63) * (-1 if descriptor[6] & 128 else 1); note = raw[10] + note_delta - raw[8]; pitch = native_pitch(executable, note); pitch += ((native_pitch(executable, note + 1) - pitch) * raw[9]) >> 7; filename = "fx_%03x.wav" % sound_id; rendered = referenced_effect(encoded, pitch, raw, output / filename); levels = native_levels(bank, program, raw, volume_delta); gain = levels["gain"]
		catalog["effects"]["0x%04X" % sound_id] = {"file": "res://assets/audio/%s/%s" % (owner, filename), "source": archive.relative_to(source_dir).as_posix(), "owner_stage": owner, "logical_effect": True, "physical_bank": bank["physical_slot"], "logical_bank": bank["logical_id"], "bank_section_offset": hex(bank["offset"]), "descriptor_address": hex(address), "descriptor": descriptor.hex(), "program": program, "tone": tone, "spu_pitch": pitch, **levels, **provenance, **rendered}
	for manifest_path in sorted((ROOT / "assets/levels").glob("ST??/manifest.json")):
		stage = manifest_path.parent.name; overlay = dat / (stage + "T.BIN")
		if not overlay.is_file(): continue
		level = json.loads(manifest_path.read_text(encoding="utf-8")); areas = [int(entry["index"]) for entry in level.get("areas", [])]; output = ROOT / "assets/audio" / stage; output.mkdir(parents=True, exist_ok=True); previous_path = output / "manifest.json"; previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else {}; overlay_hash = hashlib.sha256(overlay.read_bytes()).hexdigest(); previous_rules = previous.get("music_rules", []); rules = previous_rules if previous.get("source", {}).get("sha256") == overlay_hash and previous.get("source", {}).get("selector_sha256") == selector_signature and set(int(rule["area"]) for rule in previous_rules) == set(areas) else stage_music_rules(overlay, areas); effects = {}; loaded_slots = []
		for archive in [dat / (stage + ".BIN"), overlay]:
			for section in sources.get(archive, []):
				if section.get("logical_id") != 0 or section["kind"] not in (5, 14): continue
				bank = bank_data(archive, section["offset"]); slot = bank["physical_slot"]
				if slot == 0: continue
				loaded_slots.append(slot)
				for sound_id in range(0x80, 0x310):
					address, descriptor = native_descriptor(executable, sound_id)
					if len(descriptor) != 8 or descriptor[0] >> 4 != 0 or descriptor[1] != slot or descriptor[2] >= bank["programs"]: continue
					program, tone = descriptor[2], descriptor[3] >> 4
					if tone >= bank["data"][bank["payload"] + program * 8]: continue
					raw, encoded, provenance = tone_data(bank, program, tone); note_delta = (descriptor[7] & 31) * (-1 if descriptor[7] & 128 else 1); volume_delta = (descriptor[6] & 63) * (-1 if descriptor[6] & 128 else 1); note = raw[10] + note_delta - raw[8]; pitch = native_pitch(executable, note); pitch += ((native_pitch(executable, note + 1) - pitch) * raw[9]) >> 7; filename = "fx_%03x.wav" % sound_id; rendered = referenced_effect(encoded, pitch, raw, output / filename); levels = native_levels(bank, program, raw, volume_delta); gain = levels["gain"]
					effects["0x%04X" % sound_id] = {"file": filename, "source": archive.relative_to(source_dir).as_posix(), "physical_bank": slot, "logical_bank": 0, "bank_section_offset": hex(section["offset"]), "descriptor_address": hex(address), "descriptor": descriptor.hex(), "program": program, "tone": tone, "spu_pitch": pitch, **levels, **provenance, **rendered}
		for effect in effects.values():
			if bytes.fromhex(effect["raw_tone"])[5]: effect["reverb"] = referenced_reverb(effect, output, reverb_profile(executable))
		dependencies = sorted({entry["owner_stage"] for effect in effects.values() for entry in [effect, effect.get("reverb", effect)] if entry["owner_stage"] != stage})
		zone = {"stage": stage, "music_rules": rules, "music": {**{key: entry for key, entry in catalog["music"].items() if entry["owner_stage"] == stage}, **catalog["music_variants"].get(stage, {})}, "effects": effects, "audio_dependencies": dependencies, "loaded_effect_slots": sorted(set(loaded_slots)), "source": {"overlay": overlay.relative_to(source_dir).as_posix(), "sha256": overlay_hash, "selector_sha256": selector_signature, "keep_music_cue": 255, "unresolved_selector": not bool(rules)}}; catalog["zones"][stage] = {"manifest": "res://assets/audio/%s/manifest.json" % stage, "music_rules": rules, "audio_dependencies": dependencies, "loaded_effect_slots": zone["loaded_effect_slots"]}
		if stage == "ST0F": preserved_effects = baseline.get("effects", {}); baseline.update(zone); baseline["music"] = {**known, **zone["music"]}; baseline["effects"] = {**preserved_effects, **effects}
		else: write_output(output / "manifest.json", json.dumps(zone, indent=2) + "\n")
		print("Native zone audio %s: %d selector rules, %d effects" % (stage, len(rules), len(effects)), flush=True)
	baseline["audio_catalog"] = catalog; baseline["effects"].update(catalog["effects"]); write_output(baseline_path, json.dumps(baseline, indent=2) + "\n"); canonicalize_audio_resources(); print(json.dumps(prune_audio_duplicates()), flush=True); return json.loads(baseline_path.read_text(encoding="utf-8"))["audio_catalog"]
def export_shared_audio(source_dir=None):
	source_dir = ROOT / "build/disc-assets" if source_dir is None else Path(source_dir); executable = (source_dir / "SLES_035.56").read_bytes(); archive = source_dir / "COMMON/INIT.BIN"; sections = [section for section in native_audio_sections(archive) if section.get("physical_slot") == 0 and section.get("logical_id") == 0]
	if len(sections) != 1: raise ValueError("Expected one native shared physical sound bank")
	bank = bank_data(archive, sections[0]["offset"]); manifest_path = OUTPUT / "manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8")); effects = {}; seed_audio_cache(executable)
	for sound_id in range(0x80, 0x310):
		address, descriptor = native_descriptor(executable, sound_id); program, tone = descriptor[2], descriptor[3] >> 4
		if descriptor[0] >> 4 != 0 or descriptor[1] != 0 or program >= bank["programs"] or tone >= bank["data"][bank["payload"] + program * 8]: continue
		raw, encoded, provenance = tone_data(bank, program, tone); note_delta = (descriptor[7] & 31) * (-1 if descriptor[7] & 128 else 1); volume_delta = (descriptor[6] & 63) * (-1 if descriptor[6] & 128 else 1); note = raw[10] + note_delta - raw[8]; pitch = native_pitch(executable, note); pitch += ((native_pitch(executable, note + 1) - pitch) * raw[9]) >> 7; levels = native_levels(bank, program, raw, volume_delta); gain = levels["gain"]; rendered = referenced_effect(encoded, pitch, raw, OUTPUT / ("fx_%03x.wav" % sound_id))
		effects["0x%04X" % sound_id] = {"source": archive.relative_to(source_dir).as_posix(), "bank_section_offset": hex(bank["offset"]), "physical_bank": 0, "logical_bank": 0, "program": program, "tone": tone, "descriptor_address": hex(address), "descriptor": descriptor.hex(), "spu_pitch": pitch, "native_sample_rate": 44100 * pitch / 4096, **levels, **provenance, **rendered}
	for key, effect in effects.items():
		if bytes.fromhex(effect["raw_tone"])[5]: effect["reverb"] = referenced_reverb(effect, OUTPUT, reverb_profile(executable))
		print("Native shared audio " + key, flush=True)
	manifest["effects"] = {**manifest.get("effects", {}), **effects}; write_output(manifest_path, json.dumps(manifest, indent=2) + "\n"); canonicalize_audio_resources(); print(json.dumps(prune_audio_duplicates()), flush=True); return effects
def export_game_over_audio():
	ffmpeg = shutil.which("ffmpeg")
	if not ffmpeg: raise RuntimeError("FFmpeg is required to decode the original PS1 ADPCM samples")
	manifest_path = OUTPUT / "manifest.json"; manifest = json.loads(manifest_path.read_text(encoding="utf-8")); entry = render_music(ffmpeg, ROOT / "build/disc-assets/COMMON/G_OVER00.BIN", 0x9000, 0x9800, "game_over_music"); entry["looped"] = False
	manifest["music"]["0x000C"] = {**entry, "source_cue": "DEMO0x800ADF54 SLES0x800201B0(0xC) after COMMON/G_OVER00.BIN (file id 4)"}; manifest["roles"]["game_over_music"] = "0x000C"; write_output(manifest_path, json.dumps(manifest, indent=2) + "\n"); return entry
def export_library(source_dir, output_dir):
	source_dir = Path(source_dir); output_dir = Path(output_dir); result = []
	for path in sorted(source_dir.rglob("*.BIN")):
		data = path.read_bytes(); banks = []; sequences = []
		for offset in range(0, len(data) - 47, 0x400):
			kind = u32(data, offset)
			if kind in (5, 14):
				programs = struct.unpack_from("<H", data, offset + 28)[0]; metadata_size = u32(data, offset + 20); size = u32(data, offset + 24)
				if 0 < programs <= 128 and metadata_size >= programs * 328 and size > 0 and ((offset + 48 + metadata_size + 2047) & ~2047) + size <= len(data): banks.append(offset)
			elif kind in (8, 9, 15, 16):
				try: events, metadata = score_events(path, offset); sequences.append((offset, metadata))
				except (ValueError, IndexError, struct.error): continue
		if not banks and not sequences: continue
		directory = output_dir / path.parent.name.lower() / path.stem; directory.mkdir(parents=True, exist_ok=True); entry = {"file": path.relative_to(source_dir).as_posix(), "banks": [], "sequences": []}; cache = {}
		for offset in banks:
			bank = bank_data(path, offset); item = {"offset": offset, "logical_id": bank["logical_id"], "programs": []}
			for program in range(bank["programs"]):
				for tone in range(data[bank["payload"] + program * 8]):
					try:
						raw, encoded, metadata = tone_data(bank, program, tone); digest = hashlib.sha256(encoded).hexdigest()
						if digest not in cache:
							target = directory / (digest + ".wav"); pcm = array("h", spu_adpcm(encoded))
							write_wave(target, 1, 44100, pcm.tobytes())
							cache[digest] = target.name
						item["programs"].append({"program": program, "tone": tone, "file": cache[digest], "sample_rate": 44100, **metadata})
					except (ValueError, IndexError, struct.error) as error: item["programs"].append({"program": program, "tone": tone, "error": str(error)})
			entry["banks"].append(item)
		for offset, metadata in sequences:
			events, _ = score_events(path, offset); target = directory / ("sequence_%05X.json" % offset); write_output(target, json.dumps({"source": entry["file"], **metadata, "events": events}, indent=2), encoding="utf-8"); entry["sequences"].append({"file": target.name, **metadata})
		write_output(directory / "manifest.json", json.dumps(entry, indent=2), encoding="utf-8"); result.append(entry)
	return result
def export_xa_library(cue, output_dir):
	path, start, frames = cue_layout(Path(cue)); reader = Mode2Track(path, start, frames); result = []
	try:
		for entry in disc_files(reader):
			if not entry["file"].upper().startswith("XA/"): continue
			directory = Path(output_dir) / Path(entry["file"]).stem; directory.mkdir(parents=True, exist_ok=True); active = {}; counters = {}; streams = []
			def finish(key):
				item = active.pop(key); item.pop("writer").close(); write_output(directory / item["file"], item.pop("buffer").getvalue()); item.pop("history"); item["duration_seconds"] = item["sample_frames"] / item["sample_rate"]; streams.append(item)
			try:
				for offset in range((entry["iso_bytes"] + 2047) // 2048):
					lba = entry["extent"] + offset; reader.stream.seek((reader.start_frame + lba) * SECTOR_SIZE); raw = reader.stream.read(SECTOR_SIZE)
					if len(raw) != SECTOR_SIZE or raw[:12] != SYNC or raw[15] != 2 or raw[16:20] != raw[20:24]: raise ValueError("Invalid XA source sector")
					if raw[18] & 14 != 4: continue
					channels, rate, bits = xa_format(raw[19]); key = (raw[16], raw[17], raw[19])
					if key not in active:
						number = counters.get(key, 0); counters[key] = number + 1; filename = "file_%02d_channel_%02d_%03d.wav" % (key[0], key[1], number); buffer = io.BytesIO(); writer = wave.open(buffer, "wb"); writer.setnchannels(channels); writer.setsampwidth(2); writer.setframerate(rate)
						active[key] = {"file": filename, "file_number": key[0], "channel": key[1], "coding": key[2], "channels": channels, "sample_rate": rate, "bits": bits, "first_sector": offset, "last_sector": offset, "sample_frames": 0, "writer": writer, "buffer": buffer, "history": [(0, 0)] * channels}
					item = active[key]; pcm = decode_sector(raw, channels, bits, item["history"]); item["writer"].writeframesraw(pcm.tobytes()); item["sample_frames"] += len(pcm) // channels; item["last_sector"] = offset
					if raw[18] & 0x81: finish(key)
			finally:
				for key in list(active): finish(key)
			item = {"source": entry, "streams": streams}; write_output(directory / "manifest.json", json.dumps(item, indent=2), encoding="utf-8"); result.append(item)
	finally: reader.stream.close()
	return result
def audio_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--cue", type=Path); args = parser.parse_args(); manifest = export_audio(args.cue); print(json.dumps({"effects": len(manifest["effects"]), "manifest": str(OUTPUT / "manifest.json"), "roles": manifest["roles"]}))

FILTERS = ((0, 0), (60, 0), (115, -52), (98, -55))
def xa_format(coding):
	channel_mode, rate_mode, bit_mode = coding & 3, (coding >> 2) & 3, (coding >> 4) & 3
	if channel_mode > 1 or rate_mode > 1 or bit_mode > 1 or coding & 128: raise ValueError("Reserved XA coding info0x%02X" % coding)
	if coding & 64: raise ValueError("XA emphasis requires its original filter; no selected opening sector uses it")
	return channel_mode + 1, 18900 if rate_mode else 37800, 8 if bit_mode else 4
def decode_sector(raw, channels, bits, history):
	decoded = [[] for _ in range(channels)]; units = 4 if bits == 8 else 8
	for group_index in range(18):
		group = raw[24 + group_index * 128:24 + (group_index + 1) * 128]
		if bits == 4:
			if group[0:4] != group[4:8] or group[8:12] != group[12:16]: raise ValueError("XA sound-parameter copies disagree")
		elif group[0:4] != group[4:8] or group[0:4] != group[8:12] or group[0:4] != group[12:16]: raise ValueError("XA8 sound-parameter copies disagree")
		for unit in range(units):
			channel = unit % channels; parameter = group[4 + unit]; shift = parameter & 15; shift = 9 if shift > 12 else shift; f0, f1 = FILTERS[(parameter >> 4) & 3]; old, older = history[channel]; lane = unit if bits == 8 else unit >> 1; samples = decoded[channel]
			for sample_index in range(28):
				value = group[16 + sample_index * 4 + lane]
				if bits == 4: value = (value >> ((unit & 1) * 4)) & 15
				value -= (1 << bits) if value & (1 << (bits - 1)) else 0; value = ((value << (16 - bits)) >> shift) + ((old * f0 + older * f1 + 32) >> 6); value = max(-32768, min(32767, value)); samples.append(value); older, old = old, value
			history[channel] = old, older
	pcm = array("h", decoded[0]) if channels == 1 else array("h", (value for frame in zip(*decoded) for value in frame))
	if sys.byteorder != "little": pcm.byteswap()
	return pcm
def archive_record(reader, archive):
	pvd = reader.sector(16)
	if pvd[1:6] != b"CD001": raise ValueError("The selected disc has no ISO9660 primary descriptor atsector16")
	extent, size = struct.unpack_from("<I", pvd, 158)[0], struct.unpack_from("<I", pvd, 166)[0]; parts = archive.split("/")
	for index, part in enumerate(parts):
		matches = [entry for entry in directory_records(reader, extent, size) if entry[0] == part]
		if len(matches) != 1: raise ValueError("The selected disc has no unique " + archive)
		name, extent, size, flags = matches[0]
		if index < len(parts) - 1 and not flags & 2: raise ValueError("XA path component is not a directory: " + name)
	return extent, size
def export_entry(reader, extent, entry, output):
	filename = "xa_%03d.wav" % int(entry["id"]); destination = output / filename; history = None; format_info = None; wave_buffer = None; sector_count = 0; sample_frames = 0; first_sector = None; last_sector = None; digest = hashlib.sha256(); peak = 0; square_sum = 0; wave_output = None
	try:
		for offset in range(int(entry["sector_start"]), int(entry["sector_end"]) + 1):
			lba = extent + offset
			if not 0 <= lba < reader.frames: raise ValueError("Opening XA sector outside Track01")
			reader.stream.seek((reader.start_frame + lba) * SECTOR_SIZE); raw = reader.stream.read(SECTOR_SIZE)
			if len(raw) != SECTOR_SIZE or raw[:12] != SYNC or raw[15] != 2 or raw[16:20] != raw[20:24]: raise ValueError("Invalid Mode2/XA sector atLBA%d" % lba)
			if (raw[18] & 14) != 4 or raw[17] != int(entry["channel"]): continue
			if not raw[18] & 32: raise ValueError("XA audio was not stored in Form2")
			info = xa_format(raw[19])
			if format_info is None:
				format_info = info; channels, sample_rate, bits = info; history = [(0, 0)] * channels; wave_buffer = io.BytesIO(); wave_output = wave.open(wave_buffer, "wb"); wave_output.setnchannels(channels); wave_output.setsampwidth(2); wave_output.setframerate(sample_rate); first_sector = offset
			elif format_info != info: raise ValueError("XA coding changed inside the original descriptor")
			pcm = decode_sector(raw, channels, bits, history); wave_output.writeframesraw(pcm.tobytes()); digest.update(raw); sector_count += 1; sample_frames += len(pcm) // channels; last_sector = offset; peak = max(peak, max(abs(value) for value in pcm)); square_sum += sum(value * value for value in pcm)
	finally:
		if wave_output is not None: wave_output.close()
	if not sector_count: raise ValueError("Original XA descriptor contains no audio sectors onitschannel")
	write_output(destination, wave_buffer.getvalue())
	return {**entry, "file": "res://assets/opening/audio/" + filename, "extent": extent, "sector_end_inclusive": True, "first_selected_sector": first_sector, "last_selected_sector": last_sector, "audio_sectors": sector_count, "source_coding_info": raw[19], "sample_rate": sample_rate, "channels": channels, "adpcm_bits": bits, "sample_frames": sample_frames, "duration_seconds": sample_frames / sample_rate, "source_sectors_sha256": digest.hexdigest(), "wav_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "peak_pcm16": peak, "rms_pcm16": (square_sum / (sample_frames * channels)) ** 0.5, "decoder": "XA4/XA8 signed samples, four native predictors, +32 rounding, signed16 clipping, persistent channel histories", "resampling": "Native37800/18900Hz WAV; hardware44100Hz zigzag interpolation is not baked"}
def export_opening_audio(cue):
	manifest_path = ROOT / "assets/opening/manifest.json"; source = json.loads(manifest_path.read_text(encoding="utf-8")); xa = source["xa"]; bin_path, start, frames = cue_layout(cue); reader = Mode2Track(bin_path, start, frames); output = ROOT / "assets/opening/audio"; output.mkdir(parents=True, exist_ok=True); entries = []
	try:
		for entry in xa["entries"]:
			extent, size = archive_record(reader, entry["archive"])
			if int(entry["sector_end"]) >= (size + 2047) // 2048: raise ValueError("XA descriptor exceeds its ISO file")
			item = export_entry(reader, extent, entry, output); entries.append(item); print(json.dumps({key: item[key] for key in ("id", "audio_sectors", "duration_seconds", "sample_rate", "channels", "peak_pcm16")}))
	finally: reader.stream.close()
	manifest = {"source": xa["source"], "descriptor_table": xa["descriptor_table"], "disc_track": bin_path.name, "decoder_reference": "https://psx-spx.consoledev.net/ps1/cdr/cdromformat/#cdrom-xa-audio-adpcm-compression", "entries": entries}; pending = output / "manifest.json.next"; write_output(pending, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); pending.replace(output / "manifest.json"); return manifest
def opening_audio_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("cue", type=Path); args = parser.parse_args(); export_opening_audio(args.cue.resolve())
def stage_voice_tables(stage):
	overlay = (ROOT / "build/disc-assets/DAT" / (stage + "T.BIN")).read_bytes(); code = overlay[0x30:]; tables = {}
	for index in range(8, len(code) - 3, 4):
		word = struct.unpack_from("<I", code, index)[0]
		if word >> 16 != 0xAC62 or (word & 0xFFFF) not in (0x8DD4, 0x8DD8): continue
		window = [struct.unpack_from("<I", code, cursor)[0] for cursor in range(max(0, index - 24), index, 4)]; highs = [value for value in window if value >> 16 == 0x3C02]; lows = [value for value in window if value >> 16 == 0x2442]
		if not highs or not lows: continue
		high, low = highs[-1], lows[-1]
		tables[0x8000 if word & 0xFFFF == 0x8DD4 else 0] = ((high & 0xFFFF) << 16) + (low & 0xFFFF) - (0x10000 if low & 0x8000 else 0)
	return overlay, tables
def export_stage_voices(cue, stage, ids=None):
	if stage == "COMMON": overlay, origin, tables = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(), 0x80010000 - 0x800, {0xFF00: 0x80069624}
	else: (overlay, tables), origin = stage_voice_tables(stage), 0x800E7000 - 0x30
	executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); archive_ids = struct.unpack_from("<16H", executable, 0x800695F4 - 0x80010000 + 0x800)
	bin_path, start, frames = cue_layout(Path(cue)); reader = Mode2Track(bin_path, start, frames); folder = "assets/audio/common_voices" if stage == "COMMON" else "assets/levels/%s/audio" % stage; output = ROOT / folder; output.mkdir(parents=True, exist_ok=True); manifest_path = output / "manifest.json"
	manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"source": ("SLES" if stage == "COMMON" else stage + "T") + " XA descriptor tables", "entries": []}; entries = {int(entry["id"]): entry for entry in manifest["entries"]}
	try:
		files = sorted(disc_files(reader), key=lambda entry: entry["extent"])
		for base, address in tables.items():
			for index in range(min([0x7F00] + [(other - address) // 8 for other in tables.values() if other > address])):
				offset = address - origin + index * 8; raw = overlay[offset:offset + 8]
				if len(raw) < 8 or not any(raw) or raw[0] >= 16 or not archive_ids[raw[0]] or archive_ids[raw[0]] >= len(files): break
				archive = files[archive_ids[raw[0]]]; first = (raw[1] << 16) | struct.unpack_from("<H", raw, 2)[0]; last = (raw[5] << 16) | struct.unpack_from("<H", raw, 6)[0]
				if not archive["file"].upper().startswith("XA/") or first > last or last >= (archive["iso_bytes"] + 2047) // 2048: break
				if ids is not None and (base | index) not in ids: continue
				source = {"id": base | index, "descriptor_ram": "0x%08X" % (address + index * 8), "descriptor_bytes": raw.hex(), "archive": archive["file"], "sector_start": first, "sector_end": last, "channel": raw[4] & 31, "flags": raw[4] & 0xE0}
				item = export_entry(reader, archive["extent"], source, output); item["file"] = "res://%s/%s" % (folder, Path(item["file"]).name); entries[source["id"]] = item
	finally: reader.stream.close()
	manifest["entries"] = [entries[key] for key in sorted(entries)]; manifest["voice_tables"] = {"0x%04X" % base: "0x%08X" % address for base, address in tables.items()}; manifest["voice_lookup"] = "SLES0x8001B9D0: id&0x8000 -> *(0x80078DD4)+(id&0x7FFF)*8 else *(0x80078DD8)+id*8; archive byte -> u16 file id table SLES0x800695F4"
	write_output(manifest_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
from disc import decompress_section
from disc import Mode2Track
from disc import cue_layout
from disc import directory_records
from disc import SECTOR_SIZE
from disc import SYNC
from disc import disc_files

if __name__ == '__main__':
	import sys
	commands = {'audio': 'audio_cli', 'opening-audio': 'opening_audio_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
