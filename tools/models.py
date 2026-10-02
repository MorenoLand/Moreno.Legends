from __future__ import annotations
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import disc
import sys
ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "build" / "disc-assets" / "COMMON"
OUTPUT = ROOT / "assets" / "player"
SCALE = 1.0 / 2048.0
PARTS = (("Body", 0x80, (0, 8, 9, 10, 12, 13)), ("Head", 0xB60, (1, 1, 1)), ("Feet", 0x1800, (11, 14)), ("OtherArm", 0x26F0, (2, 3, 4)), ("Buster", 0x2220, (5, 6, 7)))
CIVILIAN_PARTS = (("Body", 0x80, (0, 8, 9, 10, 12, 13)), ("Head", 0xB60, (1, 1, 1)), ("Feet", 0x1800, (11, 14)), ("NormalArmA", 0x26F0, (2, 3, 4)), ("NormalArmB", 0x1DD0, (5, 6, 7)))
PARENTS = (-1, 0, 0, 2, 3, 0, 5, 6, 0, 8, 9, 10, 8, 12, 13)


def signed10(value):
    return value - 1024 if value & 0x200 else value


def packed_components(value, next_value=None, fraction=0):
    shift = 6 - (value >> 30)
    y, z = (value >> 4) & 0xFFFF, (value >> 14) & 0xFFFF
    values = (signed10(value & 0x3FF) << (6 - shift), (y - 65536 if y & 32768 else y) >> shift, (z - 65536 if z & 32768 else z) >> shift)
    if next_value is not None:
        target = packed_components(next_value)
        values = tuple(current + (((other - current) * fraction) >> 4) for current, other in zip(values, target))
    return values


def point(value, next_value=None, fraction=0):
    x, y, z = packed_components(value, next_value, fraction)
    return (-x * SCALE, -y * SCALE, z * SCALE)


def bone_point(x, y, z):
    return (-x * SCALE, -y * SCALE, z * SCALE)


def length3(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def decode_mesh(payload, part_definitions=PARTS):
    bones = [bone_point(*struct.unpack_from("<hhh", payload, i * 6)) for i in range(15)]
    world_bones = []
    for i, p in enumerate(PARENTS):
        v = bones[i] if p < 0 else tuple(bones[i][j] + world_bones[p][j] for j in range(3))
        world_bones.append(v)
    by_material = defaultdict(lambda: {"positions": [], "normals": [], "uvs": [], "colors": [], "joints": [], "weights": []})
    visible_points = []
    muzzle = (0.0, -0.09619140625, 0.0)
    source_materials = set()
    face_count = 0
    vertex_count = 0
    for part_name, part_offset, bone_indices in part_definitions:
        for strip_index, bone_index in enumerate(bone_indices):
            offset = part_offset + strip_index * 0x18
            tri_count, quad_count, count, _, tri_offset, quad_offset, vertex_offset, active_offset, reference_offset = struct.unpack_from("<4B5I", payload, offset)
            if not count and not tri_count and not quad_count: continue
            if not count or vertex_offset + count * 4 > len(payload) or active_offset + count * 4 > len(payload):
                raise ValueError(f"Invalid {part_name} strip {strip_index} vertex or color range")
            if reference_offset + count * 4 > len(payload):
                raise ValueError(f"Invalid {part_name} strip {strip_index} reference color range")
            words = [struct.unpack_from("<I", payload, vertex_offset + i * 4)[0] for i in range(count)]
            if any(word >> 30 for word in words):
                raise ValueError(f"{part_name} strip {strip_index} uses an unhandled vertex scale")
            vertices = [point(word) for word in words]
            colors = [tuple(payload[active_offset + i * 4 + c] / 255.0 for c in range(3)) for i in range(count)]
            faces = []
            for is_quad, number, face_offset in ((False, tri_count, tri_offset), (True, quad_count, quad_offset)):
                if face_offset + number * 12 > len(payload):
                    raise ValueError(f"Invalid {part_name} strip {strip_index} face range")
                for face_index in range(number):
                    face_pos = face_offset + face_index * 12
                    uv_bytes = payload[face_pos:face_pos + 8]
                    packed = struct.unpack_from("<I", payload, face_pos + 8)[0]
                    indices = tuple((packed >> (7 * n)) & 0x7F for n in range(4))
                    material = (packed >> 28) & 3
                    if any(index >= count for index in indices[:4 if is_quad else 3]):
                        raise ValueError(f"Invalid face index in {part_name} strip {strip_index}")
                    source_materials.add(material)
                    uv = tuple((uv_bytes[n * 2] / 256.0 + 0.001953125, uv_bytes[n * 2 + 1] / 256.0 + 0.001953125) for n in range(4))
                    triangles = (((indices[0], indices[2], indices[1]), (0, 2, 1)), ((indices[1], indices[2], indices[3]), (1, 2, 3))) if is_quad else (((indices[0], indices[2], indices[1]), (0, 2, 1)),)
                    for tri, corners in triangles:
                        faces.append((tri, tuple(uv[j] for j in corners), material))
            normal_accum = [[0.0, 0.0, 0.0] for _ in range(count)]
            for tri, _, _ in faces:
                a, b, c = (vertices[i] for i in tri)
                normal = cross(tuple(b[j] - a[j] for j in range(3)), tuple(c[j] - a[j] for j in range(3)))
                for index in tri:
                    for axis in range(3):
                        normal_accum[index][axis] += normal[axis]
            normals = []
            for value in normal_accum:
                size = length3(value)
                normals.append(tuple(axis / size for axis in value) if size else (0.0, 1.0, 0.0))
            stream = strip_index if part_offset == 0xB60 and strip_index in (1, 2) else 0
            for tri, uv, material in faces:
                target = by_material[(material, stream)]
                for corner, vertex_index in enumerate(tri):
                    p = vertices[vertex_index]
                    position = tuple(p[axis] + world_bones[bone_index][axis] for axis in range(3))
                    target["positions"].extend(position)
                    target["normals"].extend(normals[vertex_index])
                    target["uvs"].extend(uv[corner])
                    target["colors"].extend((*colors[vertex_index], 1.0))
                    target["joints"].extend((bone_index, 0, 0, 0))
                    target["weights"].extend((1.0, 0.0, 0.0, 0.0))
                    visible_points.append(position)
                face_count += 1
            vertex_count += count
    if not visible_points or not source_materials:
        raise ValueError("The player mesh has no renderable faces")
    minimum = [min(p[i] for p in visible_points) for i in range(3)]
    maximum = [max(p[i] for p in visible_points) for i in range(3)]
    return by_material, bones, world_bones, minimum, maximum, sorted(source_materials), face_count, vertex_count, muzzle


def decode_rotation(word, next_word=None, fraction=0, order="XYZ"):
    x, y, z = packed_components(word, next_word, fraction)
    angles = (-x * 90.0 / 1024.0, y * 90.0 / 1024.0, -z * 90.0 / 1024.0)
    hx, hy, hz = (math.radians(value) * 0.5 for value in angles)
    sx, sy, sz = math.sin(hx), math.sin(hy), math.sin(hz)
    cx, cy, cz = math.cos(hx), math.cos(hy), math.cos(hz)
    sign = -1.0 if order == "YXZ" else 1.0
    q = (sx * cy * cz + cx * sy * sz, cx * sy * cz - sx * cy * sz, cx * cy * sz + sign * sx * sy * cz, cx * cy * cz - sign * sx * sy * sz)
    return (q[0], -q[1], -q[2], q[3])


def decode_animations(source, binary, bone_node_ids, bones):
    player_address = struct.unpack_from("<I", source, 0x0C)[0]
    banks = [offset for offset in range(0x800, len(source) - 47, 0x800) if struct.unpack_from("<I", source, offset)[0] == 1 and not any(source[offset + 16:offset + 48]) and struct.unpack_from("<I", source, offset + 12)[0] > player_address]
    if len(banks) != 2: raise ValueError("Player archive does not contain two native animation banks")
    track_bank_offset, control_bank_offset = banks
    bank_type, bank_size, _, bank_address = struct.unpack_from("<4I", source, track_bank_offset)
    control_type, control_size, _, control_address = struct.unpack_from("<4I", source, control_bank_offset)
    if bank_type != 1 or control_type != 1 or bank_address <= player_address or control_address <= player_address:
        raise ValueError("PL00P000.BIN does not contain the expected animation bank")
    bank_delta = bank_address - player_address
    bank_file = track_bank_offset + 0x30
    first_track = struct.unpack_from("<I", source, bank_file)[0]
    track_table_size = first_track - bank_delta
    if track_table_size <= 0 or track_table_size & 3:
        raise ValueError("PL00P000 animation track table has an invalid boundary")
    track_offsets = [struct.unpack_from("<I", source, bank_file + i)[0] for i in range(0, track_table_size, 4)]
    bank_end = bank_delta + bank_size
    tracks = {}
    valid_tracks = [(slot, offset) for slot, offset in enumerate(track_offsets) if first_track <= offset < bank_end]
    for track_index, (slot, offset) in enumerate(valid_tracks):
        next_offset = next((other for _, other in valid_tracks[track_index + 1:] if other > offset), bank_end)
        span = next_offset - offset
        frame_count = span // 64
        if span & 63 and next_offset != bank_end:
            raise ValueError(f"Animation track {slot} is not aligned to 64-byte source frames")
        file_offset = bank_file + offset - bank_delta
        if file_offset + frame_count * 64 > len(source):
            raise ValueError(f"Animation track {slot} exceeds PL00P000.BIN")
        tracks[slot] = (file_offset, frame_count, offset)
    control_delta = control_address - player_address
    control_file = control_bank_offset + 0x30
    first_control = struct.unpack_from("<I", source, control_file)[0]
    control_table_size = first_control - control_delta
    if control_table_size <= 0 or control_table_size & 3:
        raise ValueError("PL00P000 animation control table has an invalid boundary")
    control_offsets = [struct.unpack_from("<I", source, control_file + i)[0] for i in range(0, control_table_size, 4)]
    control_end = control_delta + control_size
    control_entries = list(enumerate(control_offsets))
    auxiliary_track_table = bank_file + 0x80121400 - bank_address
    auxiliary_control_table = control_file + 0x80124600 - control_address
    auxiliary_tracks = {}
    for slot in range(2):
        offset = struct.unpack_from("<I", source, auxiliary_track_table + slot * 4)[0]
        end = struct.unpack_from("<I", source, auxiliary_track_table + 4)[0] if slot == 0 else bank_end
        auxiliary_tracks[slot] = (bank_file + offset - bank_delta, (end - offset) // 64, offset)
        control_entries.append((0x70 + slot, struct.unpack_from("<I", source, auxiliary_control_table + slot * 4)[0]))
    clips = []
    clip_manifest = []
    excluded = []
    valid_controls = [(slot, offset) for slot, offset in control_entries if control_delta <= offset < control_end]
    for slot, offset in control_entries:
        if not control_delta <= offset < control_end:
            excluded.append({"slot": slot, "reason": "non-address control pointer", "value": hex(offset)})
            continue
        control_pos = control_file + offset - control_delta
        track_index, frame_count = source[control_pos], source[control_pos + 1]
        record_end = control_pos + 4 + frame_count * 4
        next_record = next((control_file + other - control_delta for _, other in valid_controls[valid_controls.index((slot, offset)) + 1:] if other > offset), control_file + control_end - control_delta)
        if frame_count == 0 or record_end > next_record:
            excluded.append({"slot": slot, "reason": "invalid control length"})
            continue
        selected_tracks = auxiliary_tracks if slot >= 0x70 else tracks
        if track_index not in selected_tracks:
            excluded.append({"slot": slot, "reason": "missing track"})
            continue
        track_file, source_frame_count, track_offset = selected_tracks[track_index]
        records = [struct.unpack_from("<4B", source, control_pos + 4 + frame * 4) for frame in range(frame_count)]
        frame_indices = [record[0] for record in records]
        if any(frame_index & 0x80 for frame_index in frame_indices):
            excluded.append({"slot": slot, "reason": "unresolved high-bit control / overlay dependency", "track": track_index, "codes": sorted(set(frame_index for frame_index in frame_indices if frame_index & 0x80))})
            continue
        if any(frame_index >= source_frame_count for frame_index in frame_indices):
            excluded.append({"slot": slot, "reason": "control references an out-of-range pose frame", "track": track_index})
            continue
        times = []
        samples = []
        ticks = 0
        for frame, (pose, duration, event, flags) in enumerate(records):
            if duration == 0: raise ValueError(f"Animation control {slot} has a zero-duration record")
            target = next((other[0] for other in records[frame + 1:] if other[0] != pose), None) if flags & 0x90 == 0x10 else None
            if flags & 0x90 == 0x10 and target is None: raise ValueError(f"Animation control {slot} has an unresolved interpolation target")
            times.append(ticks / 30.0)
            samples.append((pose, target, flags & 15 if target is not None else 0))
            if duration > 1:
                times.append((ticks + duration - 1) / 30.0)
                samples.append(samples[-1])
            ticks += duration
        final_flags = records[-1][3]
        loop_frame = final_flags & 127 if final_flags & 128 and final_flags != 255 else None
        if loop_frame is not None and loop_frame >= frame_count: raise ValueError(f"Animation control {slot} loops outside its records")
        times.append(ticks / 30.0)
        samples.append(samples[loop_frame] if loop_frame is not None else samples[-1])
        input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True)
        samplers = []
        channels = []
        root_positions = []
        for frame_index, target_index, fraction in samples:
            frame_file = track_file + frame_index * 64
            target_word = struct.unpack_from("<I", source, track_file + target_index * 64)[0] if target_index is not None else None
            root_offset = point(struct.unpack_from("<I", source, frame_file)[0], target_word, fraction)
            root_positions.extend(tuple(bones[0][axis] + root_offset[axis] for axis in range(3)))
        root_accessor = binary.accessor(root_positions, "f", 5126, "VEC3", None)
        samplers.append({"input": input_accessor, "output": root_accessor, "interpolation": "LINEAR"})
        channels.append({"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}})
        for bone_index, node_index in enumerate(bone_node_ids):
            rotations = []
            for frame_index, target_index, fraction in samples:
                packed = struct.unpack_from("<I", source, track_file + frame_index * 64 + (bone_index + 1) * 4)[0]
                target_word = struct.unpack_from("<I", source, track_file + target_index * 64 + (bone_index + 1) * 4)[0] if target_index is not None else None
                rotations.extend(decode_rotation(packed, target_word, fraction, "YXZ" if (slot in (4, 5, 0x40) and bone_index in (2, 3, 4)) or (slot in (0x41,) and bone_index in (5, 6, 7)) or (slot >= 0x70 and bone_index in (5, 6, 7)) else "XYZ"))
            output_accessor = binary.accessor(rotations, "f", 5126, "VEC4", None)
            sampler_index = len(samplers)
            samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"})
            channels.append({"sampler": sampler_index, "target": {"node": node_index, "path": "rotation"}})
        name = f"clip_{slot:03d}"
        event_frames = [{"frame": frame, "id": event} for frame, (_, _, event, _) in enumerate(records) if event]
        control_metadata = {"frameCount": frame_count, "durationTicks": ticks, "durationSeconds": round(ticks / 30.0, 6), "periodTicks": ticks, "periodSeconds": round(ticks / 30.0, 6), "loopFrame": loop_frame, "loops": loop_frame is not None, "finalFlags": final_flags, "holdsLastFrame": final_flags == 255, "events": event_frames, "records": [{"pose": pose, "durationTicks": duration, "event": event, "flags": flags} for pose, duration, event, flags in records]}
        clips.append({"name": name, "samplers": samplers, "channels": channels, "extras": {"sourceControlSlot": slot, "sourceControlOffset": hex(offset), "sourceTrackSlot": track_index, "sourceTrackOffset": hex(track_offset), "frameIndices": frame_indices, "fps": 30, **control_metadata}})
        clip_manifest.append({"name": name, "slot": slot, "track": track_index, **control_metadata})
        if slot in (0, 1, 2, 17):
            for mode, active_arm_bones in ((0x40, (2, 3, 4)), (0x80, (5, 6, 7))):
                mode_samplers = [dict(sampler) for sampler in samplers]
                for bone_index in active_arm_bones:
                    rotations = []
                    for frame_index, target_index, fraction in samples:
                        packed = struct.unpack_from("<I", source, track_file + frame_index * 64 + (bone_index + 1) * 4)[0]
                        target_word = struct.unpack_from("<I", source, track_file + target_index * 64 + (bone_index + 1) * 4)[0] if target_index is not None else None
                        rotations.extend(decode_rotation(packed, target_word, fraction, "YXZ"))
                    mode_samplers[1 + bone_index]["output"] = binary.accessor(rotations, "f", 5126, "VEC4", None)
                mode_name = name + f"_mode{mode:02x}"
                mode_extras = {**clips[-1]["extras"], "sourceContext": f"player+0x13C bit{mode:#04x}; SLES 0x80040830 for bones {active_arm_bones}", "activeArmBones": list(active_arm_bones), "activeArmRotationOrder": "YXZ"}
                clips.append({"name": mode_name, "samplers": mode_samplers, "channels": [dict(channel) for channel in channels], "extras": mode_extras})
                clip_manifest.append({"name": mode_name, "slot": slot, "track": track_index, "context": f"player+0x13C bit{mode:#04x}", **control_metadata})
        if slot in (4, 5, 0x40, 0x41, 0x49, 0x4a) or slot >= 0x70:
            rotations = []
            for frame_index, target_index, fraction in samples:
                packed = struct.unpack_from("<I", source, track_file + frame_index * 64 + 4)[0]
                target_word = struct.unpack_from("<I", source, track_file + target_index * 64 + 4)[0] if target_index is not None else None
                rotations.extend(decode_rotation(packed, target_word, fraction, "YXZ"))
            upper_name = name + "_upper"
            mode = 3 if slot in (0x49, 0x4a) else 1 if slot in (4, 5, 0x40) else 2
            active_arm_bones = [2, 3, 4, 5, 6, 7] if mode == 3 else [2, 3, 4] if mode == 1 else [5, 6, 7]
            upper_bone_indices = [0, *active_arm_bones] if mode == 3 else [0, 1, *active_arm_bones]
            upper_samplers = [dict(samplers[1 + bone_index]) for bone_index in upper_bone_indices]
            upper_samplers[0]["output"] = binary.accessor(rotations, "f", 5126, "VEC4", None)
            upper_channels = [{"sampler": index, "target": channels[1 + bone_index]["target"]} for index, bone_index in enumerate(upper_bone_indices)]
            clips.append({"name": upper_name, "samplers": upper_samplers, "channels": upper_channels, "extras": {**clips[-1]["extras"], "sourceContext": f"C0={mode} upper-root 0x80040830", "rootTranslation": "omitted; use base clip", "rootRotationOrder": "YXZ", "headRotationOrder": "XYZ", "activeArmBones": active_arm_bones, "activeArmRotationOrder": "YXZ"}})
            clip_manifest.append({"name": upper_name, "slot": slot, "track": track_index, "context": f"upperBodyMode{mode}", **control_metadata})
    return clips, clip_manifest, len(track_offsets), len(control_offsets), excluded


def decode_r02_equipment_animations(source, binary, bone_node_ids, bones, player_address):
	track_offset, control_offset = 0x2800, 0x3800
	track_type, track_size, _, track_address = struct.unpack_from("<4I", source, track_offset)
	control_type, control_size, _, control_address = struct.unpack_from("<4I", source, control_offset)
	if track_type != 1 or control_type != 1 or track_address <= player_address or control_address <= player_address: raise ValueError("PL00R02.BIN does not contain the player equipment-action banks")
	track_delta, control_delta = track_address - player_address, control_address - player_address
	track_file, control_file = track_offset + 0x30, control_offset + 0x30
	first_track = struct.unpack_from("<I", source, track_file)[0]; track_table_size = first_track - track_delta
	first_control = struct.unpack_from("<I", source, control_file)[0]; control_table_size = first_control - control_delta
	if track_table_size != 8 or control_table_size != 8: raise ValueError("PL00R02 equipment-action tables do not match two controls and tracks")
	track_offsets = [struct.unpack_from("<I", source, track_file + i)[0] for i in range(0, track_table_size, 4)]
	control_offsets = [struct.unpack_from("<I", source, control_file + i)[0] for i in range(0, control_table_size, 4)]
	track_end, control_end = track_delta + track_size, control_delta + control_size
	tracks = {}
	for index, offset in enumerate(track_offsets):
		if not track_delta <= offset < track_end: raise ValueError(f"PL00R02 track {index} pointer is outside its bank")
		next_offset = track_offsets[index + 1] if index + 1 < len(track_offsets) else track_end; span = next_offset - offset
		if span & 63: raise ValueError(f"PL00R02 track {index} is not aligned to 64-byte source frames")
		file_offset = track_file + offset - track_delta
		if file_offset + span > len(source): raise ValueError(f"PL00R02 track {index} exceeds its file")
		tracks[index] = (file_offset, span // 64, offset)
	clips, clip_manifest = [], []
	for track_slot, offset in enumerate(control_offsets):
		if not control_delta <= offset < control_end: raise ValueError(f"PL00R02 control {track_slot} pointer is outside its bank")
		control_pos = control_file + offset - control_delta; frame_count = source[control_pos + 1]; record_end = control_pos + 4 + frame_count * 4
		next_offset = control_offsets[track_slot + 1] if track_slot + 1 < len(control_offsets) else control_end
		if frame_count == 0 or record_end > control_file + next_offset - control_delta: raise ValueError(f"PL00R02 control {track_slot} has an invalid length")
		track_index = source[control_pos];
		if track_index not in tracks: raise ValueError(f"PL00R02 control {track_slot} references missing track {track_index}")
		track_file, source_frame_count, source_track_offset = tracks[track_index]
		records = [struct.unpack_from("<4B", source, control_pos + 4 + frame * 4) for frame in range(frame_count)]
		frame_indices = [record[0] for record in records]
		if any(frame_index & 0x80 or frame_index >= source_frame_count for frame_index in frame_indices): raise ValueError(f"PL00R02 equipment control {track_slot} has unresolved frames")
		times, samples, ticks = [], [], 0
		for frame, (pose, duration, event, flags) in enumerate(records):
			if duration == 0: raise ValueError(f"PL00R02 control {track_slot} has a zero-duration record")
			target = next((other[0] for other in records[frame + 1:] if other[0] != pose), None) if flags & 0x90 == 0x10 else None
			if flags & 0x90 == 0x10 and target is None: raise ValueError(f"PL00R02 control {track_slot} has an unresolved interpolation target")
			times.append(ticks / 30.0); samples.append((pose, target, flags & 15 if target is not None else 0))
			if duration > 1: times.append((ticks + duration - 1) / 30.0); samples.append(samples[-1])
			ticks += duration
		final_flags = records[-1][3]; loop_frame = final_flags & 127 if final_flags & 128 and final_flags != 255 else None
		if loop_frame is not None and loop_frame >= frame_count: raise ValueError(f"PL00R02 control {track_slot} loops outside its records")
		times.append(ticks / 30.0); samples.append(samples[loop_frame] if loop_frame is not None else samples[-1])
		input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True); samplers, channels = [], []; root_positions = []
		for frame_index, target_index, fraction in samples:
			frame_file = track_file + frame_index * 64; target_word = struct.unpack_from("<I", source, track_file + target_index * 64)[0] if target_index is not None else None
			root_offset = point(struct.unpack_from("<I", source, frame_file)[0], target_word, fraction); root_positions.extend(tuple(bones[0][axis] + root_offset[axis] for axis in range(3)))
		root_accessor = binary.accessor(root_positions, "f", 5126, "VEC3", None); samplers.append({"input": input_accessor, "output": root_accessor, "interpolation": "LINEAR"}); channels.append({"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}})
		for bone_index, node_index in enumerate(bone_node_ids):
			rotations = []
			for frame_index, target_index, fraction in samples:
				frame_file = track_file + frame_index * 64 + (bone_index + 1) * 4; packed = struct.unpack_from("<I", source, frame_file)[0]; target_word = struct.unpack_from("<I", source, track_file + target_index * 64 + (bone_index + 1) * 4)[0] if target_index is not None else None
				rotations.extend(decode_rotation(packed, target_word, fraction, "YXZ" if bone_index in (2, 3, 4) else "XYZ"))
			output_accessor = binary.accessor(rotations, "f", 5126, "VEC4", None); sampler_index = len(samplers); samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"}); channels.append({"sampler": sampler_index, "target": {"node": node_index, "path": "rotation"}})
		slot = 0x60 + track_slot; name = f"clip_{slot:03d}"; events = [{"frame": frame, "id": event} for frame, (_, _, event, _) in enumerate(records) if event]
		metadata = {"frameCount": frame_count, "durationTicks": ticks, "durationSeconds": round(ticks / 30.0, 6), "periodTicks": ticks, "periodSeconds": round(ticks / 30.0, 6), "loopFrame": loop_frame, "loops": loop_frame is not None, "finalFlags": final_flags, "holdsLastFrame": final_flags == 255, "events": events, "records": [{"pose": pose, "durationTicks": duration, "event": event, "flags": flags} for pose, duration, event, flags in records]}
		extras = {"sourceControlSlot": slot, "sourceControlOffset": hex(offset), "sourceTrackSlot": track_index, "sourceTrackOffset": hex(source_track_offset), "frameIndices": frame_indices, "fps": 30, "sourceBank": "PL00R02.BIN", "sourceContext": "player+0x18C equipment action; weapon identity unassigned; mode1 bones2..4", **metadata}
		clips.append({"name": name, "samplers": samplers, "channels": channels, "extras": extras})
		upper_bones = (0, 1, 2, 3, 4); upper_samplers = [dict(samplers[1 + bone]) for bone in upper_bones]; upper_channels = [{"sampler": i, "target": channels[1 + bone]["target"]} for i, bone in enumerate(upper_bones)]
		for i, bone in enumerate(upper_bones):
			if bone not in (0, 2, 3, 4): continue
			rotations = []
			for frame_index, target_index, fraction in samples:
				frame_file = track_file + frame_index * 64 + (bone + 1) * 4; packed = struct.unpack_from("<I", source, frame_file)[0]; target_word = struct.unpack_from("<I", source, track_file + target_index * 64 + (bone + 1) * 4)[0] if target_index is not None else None
				rotations.extend(decode_rotation(packed, target_word, fraction, "YXZ"))
			upper_samplers[i]["output"] = binary.accessor(rotations, "f", 5126, "VEC4", None)
		clips.append({"name": name + "_upper", "samplers": upper_samplers, "channels": upper_channels, "extras": {**extras, "sourceContext": "PL00R02 equipment upper action; weapon identity not assigned", "activeArmBones": [2, 3, 4], "activeArmRotationOrder": "YXZ", "rootTranslation": "omitted; use base clip"}})
		clip_manifest.append({"name": name, "slot": slot, "track": track_index, **metadata, "sourceBank": "PL00R02.BIN", "context": "equipment action mode1 bones2..4"})
		clip_manifest.append({"name": name + "_upper", "slot": slot, "track": track_index, **metadata, "sourceBank": "PL00R02.BIN", "context": "equipment action mode1 bones2..4"})
	return clips, clip_manifest, len(track_offsets), len(control_offsets)


class BinaryGLB:
    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def view(self, data, target=None):
        while len(self.data) & 3:
            self.data.append(0)
        offset = len(self.data)
        self.data.extend(data)
        value = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            value["target"] = target
        self.views.append(value)
        return len(self.views) - 1

    def accessor(self, values, fmt, component, kind, target, bounds=False):
        raw = struct.pack("<" + fmt * len(values), *values)
        view = self.view(raw, target)
        count = len(values) // {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        value = {"bufferView": view, "componentType": component, "count": count, "type": kind}
        if bounds:
            width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[kind]
            value["min"] = [min(values[i::width]) for i in range(width)]
            value["max"] = [max(values[i::width]) for i in range(width)]
        self.accessors.append(value)
        return len(self.accessors) - 1


def export_variant(source_name, model_name, manifest_name, part_definitions, civilian, output_dir=None, texture_name="PL00T.BIN", meshes_only=False):
    output_dir = Path(output_dir) if output_dir is not None else OUTPUT
    source = (COMMON / source_name).read_bytes()
    file_type, size = struct.unpack_from("<II", source)
    if file_type != 1 or size < 0x80 or len(source) < 0x30 + size:
        raise ValueError(f"{source_name} does not match the documented player PBD layout")
    payload = source[0x30:0x30 + size]
    by_material, bones, world_bones, minimum, maximum, source_materials, face_count, vertex_count, muzzle = decode_mesh(payload, part_definitions)
    vram, _ = textures(COMMON / texture_name)
    material_words = struct.unpack_from("<4I", payload, 0x60)
    materials = [{"name": "Source material %d" % index, "clut": word >> 16, "tpage": word & 65535} for index, word in enumerate(material_words)]
    pngs = [texture_page(vram, item["clut"], item["tpage"]) for item in materials]
    binary = BinaryGLB()
    primitive_json = []
    surfaces = sorted(by_material)
    for material, stream in surfaces:
        arrays = by_material[(material, stream)]
        attrs = {
            "POSITION": binary.accessor(arrays["positions"], "f", 5126, "VEC3", 34962, True),
            "NORMAL": binary.accessor(arrays["normals"], "f", 5126, "VEC3", 34962),
            "TEXCOORD_0": binary.accessor(arrays["uvs"], "f", 5126, "VEC2", 34962),
            "COLOR_0": binary.accessor(arrays["colors"], "f", 5126, "VEC4", 34962),
            "JOINTS_0": binary.accessor(arrays["joints"], "H", 5123, "VEC4", 34962),
            "WEIGHTS_0": binary.accessor(arrays["weights"], "f", 5126, "VEC4", 34962),
        }
        primitive_json.append({"attributes": attrs, "material": material, "mode": 4, **({"extras": {"uv_stream": stream, "face_byte": 0x19F + stream}} if stream else {})})
    image_views = [binary.view(png) for png in pngs]
    bone_node_ids = list(range(2, 17))
    children = [[] for _ in bones]
    for i, parent in enumerate(PARENTS):
        if parent >= 0:
            children[parent].append(bone_node_ids[i])
    nodes = [{"name": "MegaMan", "children": [1, bone_node_ids[0]]}, {"name": "MegaManMesh", "mesh": 0, "skin": 0}]
    for i, position in enumerate(bones):
        node = {"name": f"Bone_{i:02d}", "translation": list(position), "extras": {"sourceBone": i}}
        if children[i]:
            node["children"] = children[i]
        nodes.append(node)
    matrices = []
    for position in world_bones:
        matrices.extend((1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -position[0], -position[1], -position[2], 1.0))
    inverse_bind = binary.accessor(matrices, "f", 5126, "MAT4", None)
    animations, clip_manifest, track_slots, control_slots, excluded_controls = ([], [], 0, 0, []) if meshes_only else decode_animations(source, binary, bone_node_ids, bones)
    if not meshes_only: primary_clips, primary_manifest, primary_track_slots, primary_control_slots = decode_r02_equipment_animations((COMMON / "PL00R02.BIN").read_bytes(), binary, bone_node_ids, bones, struct.unpack_from("<I", source, 0x0c)[0]); animations.extend(primary_clips); clip_manifest.extend(primary_manifest)
    idle = {"channels": [], "samplers": []} if meshes_only else next(clip for clip in animations if clip["name"] == "clip_000")
    for channel in idle["channels"]:
        node_index = channel["target"]["node"]; path = channel["target"]["path"]; sampler = idle["samplers"][channel["sampler"]]; accessor = binary.accessors[sampler["output"]]; view = binary.views[accessor["bufferView"]]; offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0); width = 4 if path == "rotation" else 3
        nodes[node_index][path] = list(struct.unpack_from("<" + "f" * width, binary.data, offset))
    document = {
        "asset": {"version": "2.0", "generator": "Native player model exporter", "extras": {"source": source_name, "descriptor_offsets": [part[1] for part in part_definitions], "sourceBoneCount": 16, "unusedSourceBone": 15}},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": [{"name": "MegaManCivilian" if civilian else "MegaMan", "primitives": primitive_json}],
        "skins": [{"name": "MegaManCivilianSkeleton" if civilian else "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse_bind}],
        "animations": animations,
        "materials": [{"name": item["name"], "doubleSided": True, "alphaMode": "MASK", "alphaCutoff": 0.5, "pbrMetallicRoughness": {"baseColorTexture": {"index": i}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "extensions": {"KHR_materials_unlit": {}}} for i, item in enumerate(materials)],
        "textures": [{"sampler": 0, "source": i} for i in range(len(pngs))],
        "images": [{"bufferView": image_views[i], "mimeType": "image/png", "name": materials[i]["name"]} for i in range(len(pngs))],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "bufferViews": binary.views,
        "accessors": binary.accessors,
        "buffers": [{"byteLength": len(binary.data)}],
        "extensionsUsed": ["KHR_materials_unlit"],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) & 3)
    binary.data.extend(b"\0" * ((-len(binary.data)) & 3))
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary.data)
    glb = struct.pack("<4sII", b"glTF", 2, total_length) + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk + struct.pack("<I4s", len(binary.data), b"BIN\0") + binary.data
    output_dir.mkdir(parents=True, exist_ok=True); write_output(output_dir / model_name, glb)
    if meshes_only: return None
    face_surfaces = [{"surface": index, "uv_stream": stream, "material": material, "source": "SLES0x80023438 head sub-objects 0xB78 (eyes, player+0x1A0) / 0xB90 (mouth, player+0x1A1); uv16=(r%4)*64|((r/4)*51)<<8, r=frame%20, tpage+=frame/20 (0x80023814..0x80023950)"} for index, (material, stream) in enumerate(surfaces) if stream]
    manifest = {"faceSurfaces": face_surfaces, "model": model_name, "identity": {"source": source_name, "helmet": not civilian, "shoes": "normal", "weapon": "none" if civilian else "buster"}, "bounds_m": {"min": [round(v, 6) for v in minimum], "max": [round(v, 6) for v in maximum]}, "orientation": {"up": "Y", "forward": "-Z", "sourceTransform": "X 180 degrees, then Y 180 degrees", "sourceScale": "1/2048 map units per PBD unit"}, "skeleton": {"jointCount": len(PARENTS), "sourceBoneCount": 16, "unusedSourceBone": 15, "binding": "SLES 0x80023438 safe descriptor row [0,1,2,4,6]: descriptor 2 uses P010 group 0x26F0 on bones2..4; descriptor4 uses group 0x1DD0 on bones5..7; descriptor6 is feet 0x1800" if civilian else "SLES 0x80023438/80078ADC selects descriptor5 at 8006AEC0: PL00P000 barrel group0x2220 uses bones5..7; descriptor2 at 8006AEC0: other arm group0x26F0 uses bones2..4", "defaultPose": f"{source_name} control0 first pose with matching inverse-bind matrices"}, "animations": {"idle": "clip_000", "run": "clip_001", "walk": "clip_002", "jump": "clip_017", "jump_takeoff": "clip_016", "jump_rise": "clip_017", "jump_fall": "clip_018", "jump_land": "clip_019", "jump_move": "clip_020", "jump_fall_move": "clip_021", "jump_land_move": "clip_022"} if civilian else {"idle": "clip_000", "run": "clip_001", "walk": "clip_002", "jump": "clip_017", "jump_takeoff": "clip_016", "jump_rise": "clip_017", "jump_fall": "clip_018", "jump_land": "clip_019", "jump_move": "clip_020", "jump_fall_move": "clip_021", "jump_land_move": "clip_022", "shoot": "clip_112", "shoot_upper": "clip_112_upper", "shoot_alternate_upper": "clip_113_upper", "equipment_action_96": "clip_096", "equipment_action_96_upper": "clip_096_upper", "equipment_action_97": "clip_097", "equipment_action_97_upper": "clip_097_upper", "secondary_action_112": "clip_112", "secondary_action_112_upper": "clip_112_upper", "secondary_action_113": "clip_113", "secondary_action_113_upper": "clip_113_upper", "kick": "clip_065", "kick_upper": "clip_065_upper"}, "jumpRoleProvenance": "GAME.BIN normal jump sequence at 0x800C68BC: control16 takeoff,17 rise,18 fall/apex,19 landing; controls20/21/22 are moving jump rise/fall/landing. All source controls end with flags0xFF.", "clips": clip_manifest}
    manifest["animations"]["door_open"] = "clip_083"
    manifest["animations"]["ladder_up"] = "clip_088"
    manifest["animations"]["ladder_down"] = "clip_089"
    manifest["animations"].update({"lift_grab": "clip_072", "lift_hold": "clip_074_upper", "lift_throw": "clip_073", "kick": "clip_065"})
    game = (COMMON / "GAME.BIN").read_bytes(); game_offset = lambda address: 0x30 + address - 0x800AD000
    manifest["specialActions"] = {"source": "GAME0x800CC260/0x800CC2F0/0x800CFABC selects native nearby grab; state16 at0x800C9020 uses72/74; throw0x800CF86C uses73 pose2/event1; kick0x800CDCC0/0x800D01F4/0x800D02C4", "grab": {"control": 72, "sound": 0xa1, "range_raw": 128, "cone_units": 512, "capability_mask": 2}, "hold": {"control": 74, "mode": 3, "hand_bones": [4, 7]}, "throw": {"control": 73, "start_pose": 2, "release_pose": 6, "sound": 0xa2, "vertical_raw": -256, "forward_raw": -896, "gravity_raw": 64, "damage_attribute": 8, "source_flags": 0x40000}, "kick": {"control": 65, "emit_pose": 1, "hit_ticks": 8, "bone": 14, "bounds_raw": list(struct.unpack_from("<6h", game, game_offset(0x800DCD5C))), "damage": struct.unpack_from("<h", game, game_offset(0x800DCA98))[0], "source_flags": 0x80000, "sound": 0x95}, "energy_cost": 0}
    manifest["interactionRoleProvenance"] = {"door_open": {"source": "ST05T 0x800E90F0 selects GAME 0x800CDE5C(0x53,0,1) in the ordinary-door timeline at 0x800EBF90", "control": 83, "duration_ticks": 43, "open_tick": 9, "close_tick": 26, "walk_handoff_tick": 43, "walk_control": 2, "walk_start_frame": 8}}
    for role, control, speed in (("ladder_up", 88, -55), ("ladder_down", 89, 55)): manifest["interactionRoleProvenance"][role] = {"source": "ST06T 0x800E8090-0x800E8264 selects control0x58 for route mode2 and0x59 for mode3; 0x800E820C/0x800E8274 counts80 updates; 0x800E832C applies raw vertical speed through SLES0x800417AC", "control": control, "duration_ticks": 80, "loop_ticks": 28, "vertical_raw": speed}
    if civilian:
        manifest["identity"]["hands"] = "normal"
        manifest["normalHands"] = {"source": "PL00P010.BIN; SLES 0x80078ADC safe descriptor row [0,1,2,4,6]", "bones2_4": "PBD group 0x26F0", "bones5_7": "PBD group 0x1DD0", "mirroring": "none; both groups are native PBD geometry"}
        manifest["animationRoleProvenance"] = "Animation controls from PL00P010.BIN match PL00P000.BIN. Safe-zone animation roles omit weapon actions."
        manifest["animationBank"] = {"source": source_name, "trackSlots": track_slots, "controlSlots": control_slots, "fps": 30, "frameStrideBytes": 64, "rotationDecoder": "Original SLES 0x8003F96C/0x8003FAD8 signed shifts and integer fraction interpolation", "rotationOrder": "RotMatrix X*Y*Z, applied Z then Y then X", "basisConversion": "PBD X 180-degree conjugation after packed-axis decode", "excludedControls": excluded_controls}
    else:
        manifest["muzzle"] = {"bone": "Bone_07", "position": [round(v, 6) for v in muzzle], "source": "P000 group0x2220 barrel outlet at strip1 local y=-0.167969; transformed through Bone06/Bone07 rest offset into Bone07 local coordinates"}
        manifest["animationRoleProvenance"] = "GAME.BIN 0x800CDCC0 selects PL00P000 controls112/113 for player+0x18D; SLES 0x80023438 selects descriptor group0x2220 for bones5..7 and group0x26F0 for bones2..4. Source control112/113 upper tracks drive the native Buster arm bones5..7."
        manifest["upperBodyModes"] = {"source": "SLES 0x80040294..0x800405FC", "1": [1, 2, 3, 4], "2": [1, 5, 6, 7], "3": [2, 3, 4, 5, 6, 7], "upperRootBone": 0, "upperRootTranslation": "base", "upperRootRotationOrder": "YXZ", "baseRotationOrder": "XYZ"}
        manifest["animationBank"] = {"source": source_name, "trackSlots": track_slots, "controlSlots": control_slots, "fps": 30, "frameStrideBytes": 64, "rotationDecoder": "Original SLES 0x8003F96C/0x8003FAD8 signed shifts and integer fraction interpolation", "rotationOrder": "RotMatrix X*Y*Z, applied Z then Y then X", "basisConversion": "PBD X 180-degree conjugation after packed-axis decode", "primary": {"source": "PL00R02.BIN", "trackBank": "0x80121E20", "controlBank": "0x801246B0", "tracks": primary_track_slots, "controls": primary_control_slots, "selectedControls": [96, 97], "selector": "GAME.BIN 0x800CDD08", "mode": 1}, "secondary": {"trackTable": "0x80121400", "controlTable": "0x80124600", "controls": [112, 113], "alternateActionStates": [2, 7, 8], "selector": "GAME.BIN 0x800CDCC0", "mode": 2}, "excludedControls": excluded_controls}
    if manifest_name is not None: write_output(output_dir / manifest_name, json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": str(output_dir / model_name), "bytes": len(glb), "triangles": face_count, "sourceVertices": vertex_count, "materials": source_materials, "clips": len(clip_manifest), "track_slots": track_slots, "control_slots": control_slots, "excluded_controls": len(excluded_controls), "bounds_m": manifest["bounds_m"]}, indent=2))
    return manifest


def export_player_library(output_dir):
    executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); offset = 0x800 + 0x8006aec0 - 0x80010000; rows = [struct.unpack_from("<7I", executable, offset + row * 28) for row in range(3)]; results = []
    binding = {0: (0, 8, 9, 10, 12, 13), 1: (1, 1, 1), 2: (2, 3, 4), 4: (5, 6, 7), 5: (5, 6, 7), 6: (11, 14)}
    for path in sorted(COMMON.glob("PL??P???.BIN")):
        source = path.read_bytes(); payload = source[48:48 + struct.unpack_from("<I", source, 4)[0]]; family = payload[0x71]; item = {"source": path.name, "family": family}
        try:
            if family >= len(rows): raise ValueError("Unknown native player descriptor family")
            civilian = path.stem[2:4] != "00" or int(path.stem[-3:]) >= 10; selected = [0, 1, 2, 4 if civilian else 5, 6]; parts = tuple(("Descriptor_%d" % index, rows[family][index] - 0x80110800, binding[index]) for index in selected); texture = path.stem[:4] + "T.BIN"
            directory = Path(output_dir).resolve() / path.stem; result = export_variant(path.name, "model.glb", "manifest.json", parts, civilian, directory, texture); item.update(status="exported", file=(directory / "model.glb").relative_to(ROOT).as_posix(), clips=len(result["clips"]))
        except (ValueError, IndexError, KeyError, struct.error) as error: item.update(status="unsupported", error=str(error))
        results.append(item)
    return results
def export_normal_player():
    normal = export_variant("PL00P010.BIN", "megaman_normal.glb", None, CIVILIAN_PARTS, False); normal["identity"].update(helmet=False, weapon="none", hands="normal", body="armored"); normal["skeleton"]["binding"] = "SLES0x80023438/80078ADC safe descriptor row [0,1,2,4,6]; PL00P010 head0xB60 on bone1, normal arms0x26F0/0x1DD0 on bones2..4/5..7"; normal["headSource"] = {"archive": "PL00P010.BIN", "descriptor_offsets": [0xB60, 0xB78, 0xB90], "bone": 1, "body_preservation": "All body, feet, normal-arm and buster descriptors, faces, vertices and color streams are byte-identical to PL00P000.BIN; only head geometry differs", "animation_preservation": "PL00P010.BIN animation banks from file0x3000 onward are byte-identical to PL00P000.BIN"}; normal["animationRoleProvenance"] = "PL00P010.BIN uses the same animation tracks and controls as PL00P000.BIN; armored body and gameplay action roles are preserved with the bare head and native normal hands."; write_output(OUTPUT / "manifest_normal.json", json.dumps(normal, indent=2) + "\n", encoding="utf-8"); return normal
def export_player():
    normal = export_normal_player()
    manifest = export_variant("PL00P000.BIN", "megaman.glb", "manifest.json", PARTS, False); civilian = export_variant("PL00P010.BIN", "megaman_civilian.glb", None, CIVILIAN_PARTS, True); civilian_identity = {"source": "PL00P010.BIN", "helmet": False, "hands": "normal", "weapon": "none", "safe_render_row": [0, 1, 2, 4, 6], "arms": {"bones2_4": "PBD 0x26F0", "bones5_7": "PBD 0x1DD0"}}; manifest["civilian_model"] = "res://assets/player/megaman_civilian.glb"; manifest["civilian_identity"] = civilian_identity; write_output(OUTPUT / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); civilian["animations"] = manifest["animations"]; civilian["jumpRoleProvenance"] = manifest["jumpRoleProvenance"]; civilian["animationRoleProvenance"] = "PL00P010 animation tracks and controls match PL00P000. The shared role mapping is in manifest.json; this GLB uses the native safe-zone normal-hand descriptor row."; civilian["animationBank"] = dict(manifest["animationBank"]); civilian["animationBank"]["source"] = "PL00P010.BIN"; civilian["identity"] = civilian_identity; civilian["civilian_model"] = "res://assets/player/megaman_civilian.glb"; write_output(OUTPUT / "manifest_civilian.json", json.dumps(civilian, indent=2) + "\n", encoding="utf-8")

GRID_TABLE_INDEX = 13
GRID_BASE = 0x82C4
AREA_POINTER_OFFSET = 0x1A550
AREA_LAYOUT_OFFSET = 0x1A56C
AREA_COUNT = 13
AREA_TRANSITION_POINTER_OFFSET = 0x19384
AREA_TRANSITION_RECORD_SIZE = 24
AREA_OBJECT_POINTER_OFFSET = 0x18B70
AREA_OBJECT_RECORD_SIZE = 20
ACTOR_RESOURCE_MAP_OFFSET = 0x199F4
DOOR_TILE_IDS = range(0x5C, 0x60)
UNIT = 1.0 / 256.0

def sha256(data): return hashlib.sha256(data).hexdigest()

def actor_archive(path):
	source = path.read_bytes(); file_type, size, file_count = struct.unpack_from("<3I", source); payload = source[0x30:0x30 + size]
	if file_type != 0x0A or len(payload) != size: raise ValueError(f"{path.name} is not a complete type-0x0A archive")
	model_archive_offset = 0; shared_prefix = []
	while read_u32(payload, 0) & 0xc0000000:
		flags = read_u32(payload, 0) & 0xc0000000; offset = read_u32(payload, 0) & 0x3fffffff
		if not 8 <= offset <= len(payload) - 4: raise ValueError("Compound model archive offset is outside the payload")
		shared_prefix.append({"offset": model_archive_offset, "flags": flags, "bytes": offset, "sha256": sha256(payload[:offset]), **({"control_table_offset": read_u32(payload, 4), "track_table_offset": 8} if flags & 0x80000000 else {})}); model_archive_offset += offset; payload = payload[offset:]
	count = read_u32(payload, 0); models = []
	if 4 + count * 0x10 > len(payload): raise ValueError(f"{path.name} model table exceeds its payload")
	for index in range(count):
		flags, mesh, tracks, control = struct.unpack_from("<4I", payload, 4 + index * 0x10); item = {"index": index, "flags": flags, "mesh_offset": mesh, "track_table_offset": tracks, "control_table_offset": control}
		if mesh:
			n_high, n_medium, n_low, mesh_extra = struct.unpack_from("<4B", payload, mesh); high, medium, low = struct.unpack_from("<3I", payload, mesh + 4); bone, hierarchy, texture, bounds = struct.unpack_from("<4I", payload, mesh + 0x10); primitives = []
			for part in range(n_high):
				triangles, quads, vertices, scale = struct.unpack_from("<4B", payload, high + part * 0x10); primitives.append({"triangles": triangles, "quads": quads, "vertices": vertices, "scale": scale})
			item["mesh"] = {"lod_primitive_counts": [n_high, n_medium, n_low], "header_extra": mesh_extra, "high_lod_offset": high, "medium_lod_offset": medium, "low_lod_offset": low, "bone_offset": bone, "hierarchy_offset": hierarchy, "texture_offset": texture, "bounds_offset": bounds, "bone_count": payload[hierarchy + 1] if bone else 0, "primitives": primitives}
		for kind, table in (("tracks", tracks), ("controls", control)):
			if not table: item[kind] = []; continue
			first = read_u32(payload, table)
			if first < table or (first - table) & 3: raise ValueError(f"{path.name} model {index} has an invalid {kind} table")
			pointers = [read_u32(payload, table + offset) for offset in range(0, first - table, 4)]
			if kind == "tracks": item[kind] = [{"slot": slot, "offset": pointer} for slot, pointer in enumerate(pointers)]
			else: item[kind] = [{"slot": slot, "offset": pointer, **({"track_slot": payload[pointer], "frame_count": payload[pointer + 1]} if pointer % 4 == 0 and pointer + 4 <= len(payload) else {"status": "unassigned"})} for slot, pointer in enumerate(pointers)]
		models.append(item)
	return {"file": f"build/disc-assets/DAT/{path.name}", "sha256": sha256(source), "header_count": file_count, "payload_size": size, "payload_sha256": sha256(payload), "model_archive_offset": model_archive_offset, "shared_prefix": shared_prefix, "model_count": count, "models": models}, payload

class GlbBuilder:
	def __init__(self): self.data = bytearray(); self.views = []; self.accessors = []
	def view(self, data, target=None):
		while len(self.data) & 3: self.data.append(0)
		offset = len(self.data); self.data.extend(data); value = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
		if target is not None: value["target"] = target
		self.views.append(value); return len(self.views) - 1
	def accessor(self, values, fmt, component, kind, target=None, bounds=False):
		raw = struct.pack("<" + fmt * len(values), *values); view = self.view(raw, target); width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]; value = {"bufferView": view, "componentType": component, "count": len(values) // width, "type": kind}
		if bounds:
			value["min"] = [min(values[i::width]) for i in range(width)]; value["max"] = [max(values[i::width]) for i in range(width)]
		self.accessors.append(value); return len(self.accessors) - 1
	def save(self, path, document):
		while len(self.data) & 3: self.data.append(0)
		document["buffers"] = [{"byteLength": len(self.data)}]; document["bufferViews"] = self.views; document["accessors"] = self.accessors; json_chunk = json.dumps(document, separators=(",", ":")).encode(); json_chunk += b" " * (-len(json_chunk) % 4); total = 12 + 8 + len(json_chunk) + 8 + len(self.data); write_output(path, struct.pack("<3I", 0x46546C67, 2, total) + struct.pack("<2I", len(json_chunk), 0x4E4F534A) + json_chunk + struct.pack("<2I", len(self.data), 0x004E4942) + self.data)


def pbd_position(value, scale):
	return tuple(component * scale * 2048.0 for component in packed_point(value))

def pbd_rotation(value):
	return decode_rotation(value)

def export_actor_model(payload, model_index, texture_path, output_path, source_name="ST0F00.BIN", preserve_default_hidden=False):
	model_name = f"{Path(source_name).stem}_model_{model_index:02d}"
	count = read_u32(payload, 0)
	if model_index >= count: raise ValueError("actor candidate index is outside the archive")
	flags, mesh, track_table, control_table = struct.unpack_from("<4I", payload, 4 + model_index * 16); n_high, n_medium, n_low, mesh_extra = struct.unpack_from("<4B", payload, mesh); high, medium, low, bone_offset, hierarchy_offset, texture_offset, bounds_offset = struct.unpack_from("<7I", payload, mesh + 4); bone_count = payload[hierarchy_offset + 1] if bone_offset else 0; segment_count = (texture_offset - hierarchy_offset) // 4 if bone_offset else 0
	if not bone_count or n_high != segment_count: raise ValueError("actor candidate does not have a complete skinned high-LOD hierarchy")
	parent_ids = [-1] * bone_count; local_bones = [tuple(-c * (1.0 / 2048.0) if axis < 2 else c * (1.0 / 2048.0) for axis, c in enumerate(struct.unpack_from("<hhh", payload, bone_offset + i * 6))) for i in range(bone_count)]
	for i in range(segment_count):
		polygon, parent, child, flags_byte = struct.unpack_from("<4B", payload, hierarchy_offset + i * 4)
		if polygon and flags_byte != 0x80 and child != parent and child < bone_count and parent < bone_count: parent_ids[child] = parent
	world_bones = []
	for i, point in enumerate(local_bones): world_bones.append(point if parent_ids[i] < 0 else tuple(point[axis] + world_bones[parent_ids[i]][axis] for axis in range(3)))
	if not texture_offset or texture_offset + 4 > len(payload): raise ValueError("actor has no valid source texture table")
	texture_info = read_u32(payload, texture_offset); tpage = texture_info & 0xFFFF; clut = texture_info >> 16; vram, _ = textures(texture_path); builder = GlbBuilder(); material_ids = set(); groups = {}; color_offsets = list(struct.unpack_from("<3I", payload, mesh + 0x20)) if mesh_extra & 1 else []; color_cursor = color_offsets[0] if color_offsets else 0; seam_donors = {}; seam_bindings = []
	for part in range(n_high):
		tri_count, quad_count, vertex_count, exponent, tri_offset, quad_offset, vertex_offset = struct.unpack_from("<4B3I", payload, high + part * 16); polygon, parent, bone_index, hierarchy_flags = struct.unpack_from("<4B", payload, hierarchy_offset + part * 4); bone_index = bone_index if bone_index < bone_count else 0; scale = (0.5 if exponent == 0xFF else 1 << exponent) / 2048.0; vertices = [pbd_position(read_u32(payload, vertex_offset + i * 4), scale) for i in range(vertex_count)]
		if color_offsets and (color_cursor <= 0 or color_cursor + vertex_count * 4 > len(payload)): raise ValueError("PBD high-LOD vertex RGB stream is outside its source payload")
		vertex_colors = [tuple(payload[color_cursor + index * 4 + channel] / 255.0 for channel in range(3)) for index in range(vertex_count)] if color_offsets else []; vertex_positions = [tuple(vertex[axis] + world_bones[bone_index][axis] for axis in range(3)) for vertex in vertices]; vertex_joints = [bone_index] * vertex_count
		if color_offsets and hierarchy_flags & 0x40:
			for vertex_index in range(vertex_count):
				marker = payload[color_cursor + vertex_index * 4 + 3]; kind, key = marker & 0xC0, marker & 0x3F
				if kind == 0x80: seam_donors[key] = (vertex_positions[vertex_index], bone_index, part, vertex_index)
				elif kind == 0xC0:
					if key not in seam_donors: raise ValueError(f"PBD seam recipient part{part} vertex{vertex_index} has no earlier donor key{key}")
					donor_position, donor_joint, donor_part, donor_vertex = seam_donors[key]; vertex_positions[vertex_index] = donor_position; vertex_joints[vertex_index] = donor_joint; seam_bindings.append({"part": part, "vertex": vertex_index, "key": key, "donor_part": donor_part, "donor_vertex": donor_vertex, "donor_joint": donor_joint})
		color_cursor += vertex_count * 4
		for is_quad, faces, face_offset in ((False, tri_count, tri_offset), (True, quad_count, quad_offset)):
			for face in range(faces):
				face_offset_at = face_offset + face * 12; uv_bytes = payload[face_offset_at:face_offset_at + 8]; packed = read_u32(payload, face_offset_at + 8); raw_indices = tuple((packed >> (7 * n)) & 0x7F for n in range(4)); material = (packed >> 28) & 3
				if any(index >= vertex_count for index in raw_indices[:4 if is_quad else 3]): raise ValueError(f"actor model {model_index} has an invalid PBD face index")
				group = (material, is_quad and bool(packed & 0x40000000), preserve_default_hidden and bool(hierarchy_flags & 0x80)); material_ids.add(group); target = groups.setdefault(group, {"positions": [], "normals": [], "uvs": [], "colors": [], "joints": [], "weights": [], "indices": []}); triangles = (((raw_indices[0], raw_indices[2], raw_indices[1]), (0, 2, 1)), ((raw_indices[1], raw_indices[2], raw_indices[3]), (1, 2, 3))) if is_quad else (((raw_indices[0], raw_indices[2], raw_indices[1]), (0, 2, 1)),)
				for triangle, corners in triangles:
					points = [vertex_positions[index] for index in triangle]; ab = tuple(points[1][axis] - points[0][axis] for axis in range(3)); ac = tuple(points[2][axis] - points[0][axis] for axis in range(3)); normal = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]); size = math.sqrt(sum(value * value for value in normal)); normal = tuple(value / size for value in normal) if size else (0.0, 1.0, 0.0); base = len(target["positions"]) // 3
					for corner, vertex_index in enumerate(triangle):
						uv_index = corners[corner]; target["positions"].extend(points[corner]); target["normals"].extend(normal); target["uvs"].extend(((uv_bytes[uv_index * 2] + 0.5) / 256.0, (uv_bytes[uv_index * 2 + 1] + 0.5) / 256.0)); target["joints"].extend((vertex_joints[vertex_index], 0, 0, 0)); target["weights"].extend((1.0, 0.0, 0.0, 0.0)); target["indices"].append(base + corner)
						if color_offsets: target["colors"].extend((*(vertex_colors[vertex_index] if not packed & 0x80000000 else (128.0 / 255.0,) * 3), 1.0))
				face_count = sum(len(value["indices"]) for value in groups.values()) // 3
	materials = []; images = []; source_materials = []; material_lookup = {}
	for group in sorted(material_ids):
		material, double_sided, default_hidden = group; word = read_u32(payload, texture_offset + material * 4); page, palette = word & 65535, word >> 16; index = len(materials); material_lookup[group] = index; images.append({"bufferView": builder.view(png(256, 256, decode_page(vram, page, palette))), "mimeType": "image/png"}); materials.append({"name": f"source_material_{material}" + ("_double_sided" if double_sided else "") + ("_default_hidden" if default_hidden else ""), "pbrMetallicRoughness": {"baseColorTexture": {"index": index}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "alphaMode": "BLEND", "doubleSided": double_sided}); source_materials.append({"slot": material, "texture_tpage": page, "texture_clut": palette, "double_sided": double_sided, **({"default_hidden": True, "source": "PBD hierarchy80;SLES2488C..24898"} if default_hidden else {})})
	primitives = []
	for material, values in groups.items():
		attributes = {"POSITION": builder.accessor(values["positions"], "f", 5126, "VEC3", 34962, True), "NORMAL": builder.accessor(values["normals"], "f", 5126, "VEC3", 34962), "TEXCOORD_0": builder.accessor(values["uvs"], "f", 5126, "VEC2", 34962), "JOINTS_0": builder.accessor(values["joints"], "B", 5121, "VEC4", 34962), "WEIGHTS_0": builder.accessor(values["weights"], "f", 5126, "VEC4", 34962)}; indices = builder.accessor(values["indices"], "H", 5123, "SCALAR", 34963); primitives.append({"attributes": attributes, "indices": indices, "material": material_lookup[material], "mode": 4})
		if color_offsets: attributes["COLOR_0"] = builder.accessor(values["colors"], "f", 5126, "VEC4", 34962)
	inv_bind = []
	for position in world_bones: inv_bind.extend((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, -position[0], -position[1], -position[2], 1.0))
	ibm = builder.accessor(inv_bind, "f", 5126, "MAT4"); nodes = [{"name": f"bone_{i:02d}", "translation": list(local_bones[i]), **({"children": [j for j,p in enumerate(parent_ids) if p == i]} if any(p == i for p in parent_ids) else {})} for i in range(bone_count)]; mesh_node = len(nodes); nodes.append({"name": model_name, "mesh": 0, "skin": 0}); root_nodes = [i for i,p in enumerate(parent_ids) if p < 0] + [mesh_node]
	track_count = (read_u32(payload, track_table) - track_table) // 4 if track_table else 0; track_offsets = [read_u32(payload, track_table + i * 4) for i in range(track_count)] if track_table else []; control_count = (read_u32(payload, control_table) - control_table) // 4 if control_table else 0; control_offsets = [read_u32(payload, control_table + i * 4) for i in range(control_count)] if control_table else []; animations = []; animation_meta = []
	for slot, control in enumerate(control_offsets):
		if control % 4 or control + 4 > len(payload): continue
		track_index, frame_count = struct.unpack_from("<2B", payload, control); records = [struct.unpack_from("<4B", payload, control + 4 + i * 4) for i in range(frame_count)]
		if not frame_count: continue
		if track_index >= len(track_offsets): continue
		stride = (bone_count + 1) * 4; track_offset = track_offsets[track_index]; next_track = min((other for other in track_offsets if other > track_offset), default=len(payload)); max_pose = max(record[0] for record in records)
		if track_offset + (max_pose + 1) * stride > len(payload): raise ValueError(f"actor control {slot} references an invalid source pose")
		final_flags = records[-1][3]; loop_frame = final_flags & 127 if final_flags & 128 and final_flags != 255 else None
		if loop_frame is not None and loop_frame >= len(records): raise ValueError(f"actor control {slot} loops outside its records")
		times = []; samples = []; ticks = 0
		for frame, (pose, duration, event, flags_byte) in enumerate(records):
			if duration == 0: raise ValueError(f"actor control {slot} has a zero-length frame")
			target = next((other[0] for other in records[frame + 1:] if other[0] != pose), None) if flags_byte & 0x90 == 0x10 else None
			if flags_byte & 0x90 == 0x10 and target is None and loop_frame is not None: target = next((other[0] for other in records[loop_frame:] if other[0] != pose), None)
			if flags_byte & 0x90 == 0x10 and target is None: raise ValueError(f"actor control {slot} has an unresolved interpolation target")
			times.append(ticks / 30.0); samples.append((pose, target, flags_byte & 15 if target is not None else 0))
			if duration > 1: times.append((ticks + duration - 1) / 30.0); samples.append(samples[-1])
			ticks += duration
		times.append(ticks / 30.0); samples.append(samples[loop_frame] if loop_frame is not None else samples[-1]); input_accessor = builder.accessor(times, "f", 5126, "SCALAR", None, True); samplers = []; channels = []
		root_positions = []
		for frame_index, target_index, fraction in samples:
			frame_offset = track_offset + frame_index * stride; target_word = read_u32(payload, track_offset + target_index * stride) if target_index is not None else None; root_offset = packed_point(read_u32(payload, frame_offset), target_word, fraction); root_positions.extend(tuple(local_bones[0][axis] + root_offset[axis] for axis in range(3)))
		root_accessor = builder.accessor(root_positions, "f", 5126, "VEC3"); samplers.append({"input": input_accessor, "output": root_accessor, "interpolation": "LINEAR"}); channels.append({"sampler": 0, "target": {"node": 0, "path": "translation"}})
		for bone_index in range(bone_count):
			rotations = []
			for pose, target_index, fraction in samples:
				word = read_u32(payload, track_offset + pose * stride + (bone_index + 1) * 4); target_word = read_u32(payload, track_offset + target_index * stride + (bone_index + 1) * 4) if target_index is not None else None; rotations.extend(decode_rotation(word, target_word, fraction))
			output_accessor = builder.accessor(rotations, "f", 5126, "VEC4"); samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"}); channels.append({"sampler": len(samplers) - 1, "target": {"node": bone_index, "path": "rotation"}})
		events = [{"frame": frame, "id": event} for frame, (_, _, event, _) in enumerate(records) if event]; metadata = {"frame_count": frame_count, "duration_ticks": ticks, "duration_seconds": round(ticks / 30.0, 6), "loop_frame": loop_frame, "loops": loop_frame is not None, "holds_last_frame": final_flags == 255, "events": events, "records": [{"pose": pose, "duration": duration, "event": event, "flags": flags_byte} for pose, duration, event, flags_byte in records]}; animations.append({"name": f"control_{slot:02d}", "samplers": samplers, "channels": channels, "extras": {"source_control_slot": slot, "source_track_slot": track_index, **metadata}}); animation_meta.append({"name": f"control_{slot:02d}", "slot": slot, "track": track_index, **metadata})
	control_map = {str(animation["slot"]): animation["name"] for animation in animation_meta}; document = {"asset": {"version": "2.0", "generator": "Native PBD source exporter"}, "scene": 0, "scenes": [{"nodes": root_nodes}], "nodes": nodes, "meshes": [{"name": model_name, "primitives": primitives}], "skins": [{"name": "source_skeleton", "joints": list(range(bone_count)), "skeleton": 0, "inverseBindMatrices": ibm}], "materials": materials, "textures": [{"sampler": 0, "source": index} for index in range(len(images))], "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}], "images": images, "animations": animations, "extras": {"source_archive": source_name, "source_model_index": model_index, "source_flags": flags, "source_mesh_offset": mesh, "texture_tpage": tpage, "texture_clut": clut, "source_materials": source_materials, "semantic_role": "unverified source actor candidate", "control_selector": "actor+0xA0 indexes actor+0xAC control table (SLES 0x8003F4E8); slot N is control_NN", "control_map": control_map, "vertex_color_source": "Packed actor vertices contain no per-vertex color stream", "face_count": face_count, "lod_counts": [n_high, n_medium, n_low]}}
	color_source = {"native_vertex_colors": bool(color_offsets), "vertex_color_offsets": color_offsets, "vertex_color_source": "PBD mesh+20/+24/+28 RGB4 streams; SLES3E190..3E1C0/24770..247D8/250A4..250EC; RGB normalized255, native shader color_scale255; flat-flag faces retain neutral128 modulation" if color_offsets else "PBD mesh header does not enable a native RGB4 stream", "native_seam_bindings": seam_bindings, "native_seam_source": "SLES248A0 enables hierarchy40;24EE4..24F44 RGB4 byte3:80|key caches projected vertex,C0|key copies it; export recipient position/joint uses original donor, opacity remains1"}; document["extras"].update(color_source)
	output_path.parent.mkdir(parents=True, exist_ok=True); builder.save(output_path, document)
	return {"file": str(output_path.resolve().relative_to(ROOT)).replace("\\", "/"), "model_index": model_index, "flags": flags, "mesh_offset": mesh, "texture_tpage": tpage, "texture_clut": clut, "source_materials": source_materials, "bone_count": bone_count, "lod_counts": [n_high, n_medium, n_low], "face_count": face_count, "control_map": control_map, "animations": animation_meta, **color_source}

def transition_metadata(texture):
	base = 0x800E7000; pointer_offset = 0x1A524; pointers = struct.unpack_from("<4I", texture, pointer_offset); configs = []
	for index, address in enumerate(pointers):
		offset = 0x30 + address - base; configs.append({"selector_index": index, "ram_address": address, "file_offset": offset, "bytes_hex": texture[offset:offset + 0x28].hex()})
	callback_offset = 0x1A534; callbacks = struct.unpack_from("<7I", texture, callback_offset)
	return {"trigger_consumer": {"file": "ST0FT.BIN", "ram_address": "0x800FC104", "file_offset": 0x30 + 0x800FC104 - base, "record_table_ram": "0x80098B08", "record_count": 64, "record_stride": 0xCC, "active_test": "(u8(record+0) & 1) != 0", "record_type_offset": 4, "record_type_value": 0x19, "player_pointer_ram": "0x8008C0A0", "player_x_offset": 0x12, "player_z_offset": 0x1A, "trigger_x_offset": 0x12, "trigger_z_offset": 0x1A, "trigger_bounds_raw": {"x": [-0x200, 0x200], "z": [-0x200, 0x200], "upper_bound_exclusive": True}, "units_per_axis": "raw 1/256 map unit; 0x200 equals 2 world units", "static_writer": {"file": "SLES_035.56", "function": "0x8003D3F8", "record_byte2": "0x60 or 0x61", "record_word4": "0x19", "source_list_ram": "0x800FFB40", "source_list_file_offset": AREA_OBJECT_POINTER_OFFSET, "source_record_size": AREA_OBJECT_RECORD_SIZE}}, "target_object": {"record_target_code_offset": 2, "state_target_code_offset": 0x0C, "lookup_file": "SLES_035.56", "lookup_function": "0x8003E440", "class_map_function": "0x8003E408", "area_object_codes": {"base_code": 0x10, "slot_formula": "code - 0x10", "runtime_array_ram": "0x80096DA0", "slot_stride": 0x100}, "destination_transform_source_offsets": {"position": [0x10, 0x14, 0x18], "yaw": 0x2A}, "destination_yaw_transform": "(signed16(destination+0x2A) - 0x800) & 0xFFF", "static_type0F_transition_table": "ST0FT file offset 0x19384; destination area is record byte+7; source/destination transforms are s16/u16 at +8/+16"}, "transition_setup": {"file": "ST0FT.BIN", "ram_address": "0x800FC548", "file_offset": 0x30 + 0x800FC548 - base, "actor_yaw_offset": 0x2A, "config_pointer_table_ram": "0x801014F4", "config_pointer_table_file_offset": pointer_offset, "config_records": configs, "config_selector": {"yaw_0": 0, "yaw_0x400": 1, "yaw_0x800": 2, "other": 3}, "callback_table_ram": "0x80101504", "callback_table_file_offset": callback_offset, "callback_table_words": list(callbacks), "initializer": {"file": "GAME.BIN", "function": "0x800C0C5C", "file_offset": 0x30 + 0x800C0C5C - 0x800AD000}}}

def area_transition_records(texture):
	base = 0x800E7000; pointers = struct.unpack_from("<13I", texture, AREA_TRANSITION_POINTER_OFFSET); boundaries = [0x30 + pointer - base for pointer in pointers] + [AREA_TRANSITION_POINTER_OFFSET]; records = []; other_records = []
	if any(boundaries[index] >= boundaries[index + 1] for index in range(len(pointers))): raise ValueError("ST0FT area transition pointers are not ascending")
	for area_index, start in enumerate(boundaries[:-1]):
		end = boundaries[area_index + 1]
		if (end - start) % AREA_TRANSITION_RECORD_SIZE: raise ValueError(f"ST0FT area {area_index} transition block has a partial record")
		terminated = False
		for record_offset in range(start, end, AREA_TRANSITION_RECORD_SIZE):
			raw = texture[record_offset:record_offset + AREA_TRANSITION_RECORD_SIZE]
			if raw[0] == 0xFF:
				if any(raw[1:]) or record_offset + AREA_TRANSITION_RECORD_SIZE != end: raise ValueError(f"ST0FT area {area_index} has a malformed transition terminator")
				terminated = True; break
			record_type = raw[6]
			if record_type != 0x0F:
				other_records.append({"area_index": area_index, "record_index": (record_offset - start) // AREA_TRANSITION_RECORD_SIZE, "record_type": record_type, "file_offset": record_offset, "bytes_hex": raw.hex()}); continue
			destination_area = raw[7]
			if destination_area >= AREA_COUNT: raise ValueError(f"ST0FT area {area_index} transition targets invalid area {destination_area}")
			sx, sy, sz = struct.unpack_from("<3h", raw, 8); source_yaw = read_u16(raw, 14); dx, dy, dz = struct.unpack_from("<3h", raw, 16); destination_yaw = read_u16(raw, 22)
			records.append({"source_area": area_index, "destination_area": destination_area, "record_index": (record_offset - start) // AREA_TRANSITION_RECORD_SIZE, "file_offset": record_offset, "record_type": record_type, "header_hex": raw[:6].hex(), "source_transform_raw": [sx, sy, sz, source_yaw], "source_transform": {"position": [sx * UNIT, sy * UNIT, sz * UNIT], "yaw_raw": source_yaw, "yaw_turns": source_yaw / 4096.0}, "destination_transform_raw": [dx, dy, dz, destination_yaw], "destination_transform": {"position": [dx * UNIT, dy * UNIT, dz * UNIT], "yaw_raw": destination_yaw, "yaw_turns": destination_yaw / 4096.0}, "bytes_hex": raw.hex()})
		if not terminated: raise ValueError(f"ST0FT area {area_index} transition block has no 0xFF terminator")
	return records, other_records

def transition_edges(records):
	by_edge = defaultdict(list)
	for record in records: by_edge[tuple(sorted((record["source_area"], record["destination_area"])))].append(record)
	edges = []
	for areas, members in sorted(by_edge.items()):
		if len(members) != 2 or {tuple(item["source_transform_raw"][:3]) for item in members} != {tuple(item["destination_transform_raw"][:3]) for item in members}: raise ValueError(f"ST0FT area link {areas} is not represented by a reciprocal pair")
		by_direction = {(item["source_area"], item["destination_area"]): item for item in members}
		if set(by_direction) != {(areas[0], areas[1]), (areas[1], areas[0])}: raise ValueError(f"ST0FT area link {areas} has duplicate direction records")
		forward = by_direction[(areas[0], areas[1])]; reverse = by_direction[(areas[1], areas[0])]
		if forward["source_transform_raw"][:3] != reverse["destination_transform_raw"][:3] or forward["destination_transform_raw"][:3] != reverse["source_transform_raw"][:3]: raise ValueError(f"ST0FT area link {areas} has mismatched reciprocal positions")
		edges.append({"areas": list(areas), "transitions": members, "reciprocal_positions_match": True, "yaw_difference_raw": (reverse["source_transform_raw"][3] - forward["destination_transform_raw"][3]) & 0xFFF})
	return edges

def area_object_records(texture, actor_model_count):
	base = 0x800E7000; pointers = struct.unpack_from("<13I", texture, AREA_OBJECT_POINTER_OFFSET); boundaries = [0x30 + pointer - base for pointer in pointers] + [AREA_OBJECT_POINTER_OFFSET]; actor_resources = list(texture[ACTOR_RESOURCE_MAP_OFFSET:ACTOR_RESOURCE_MAP_OFFSET + 24]); records = []
	if any(boundaries[index] >= boundaries[index + 1] for index in range(len(pointers))): raise ValueError("ST0FT area object pointers are not ascending")
	for area_index, start in enumerate(boundaries[:-1]):
		end = boundaries[area_index + 1]
		if (end - start) % AREA_OBJECT_RECORD_SIZE: raise ValueError(f"ST0FT area {area_index} object block has a partial record")
		terminated = False
		for record_offset in range(start, end, AREA_OBJECT_RECORD_SIZE):
			raw = texture[record_offset:record_offset + AREA_OBJECT_RECORD_SIZE]
			if raw[0] == 0xFF:
				if any(raw[1:]) or record_offset + AREA_OBJECT_RECORD_SIZE != end: raise ValueError(f"ST0FT area {area_index} has a malformed object terminator")
				terminated = True; break
			record_type = raw[2]; item = {"area_index": area_index, "record_index": (record_offset - start) // AREA_OBJECT_RECORD_SIZE, "file_offset": record_offset, "record_type": record_type, "flags": raw[0], "record_class": raw[3], "word_at_4": read_u32(raw, 4), "word_at_8": read_u32(raw, 8), "bytes_hex": raw.hex()}
			if record_type == 0x20:
				resource_slot = raw[7]
				if resource_slot >= len(actor_resources): raise ValueError(f"ST0FT area {area_index} actor has invalid resource slot {resource_slot}")
				model_index = actor_resources[resource_slot]
				if model_index >= actor_model_count: raise ValueError(f"ST0FT area {area_index} actor maps to invalid ST0F00 model {model_index}")
				x, y, z = struct.unpack_from("<3h", raw, 12); yaw = read_u16(raw, 18); item.update({"resource_slot": resource_slot, "resource_model_index": model_index, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x * UNIT, -y * UNIT, z * UNIT], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0}})
			elif record_type in (0x60, 0x61) and read_u32(raw, 4) == 0x19:
				x, y, z = struct.unpack_from("<3h", raw, 12); yaw = read_u16(raw, 18); item.update({"runtime_type": 0x19, "record_table_family": record_type, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x * UNIT, -y * UNIT, z * UNIT], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0}})
			records.append(item)
		if not terminated: raise ValueError(f"ST0FT area {area_index} object block has no 0xFF terminator")
	return records, actor_resources

def bind_trigger_records(records, transitions):
	for record in records:
		if record.get("runtime_type") != 0x19: continue
		matches = [transition for transition in transitions if transition["source_area"] == record["area_index"] and transition["source_transform_raw"][:3] == record["transform_raw"][:3]]
		if len(matches) != 1: raise ValueError(f"ST0FT area {record['area_index']} type-0x19 trigger matches {len(matches)} static area transitions by exact position")
		transition = matches[0]; record["transition_file_offset"] = transition["file_offset"]; record["destination_area"] = transition["destination_area"]; record["source_heading_matches"] = record["transform_raw"][3] == transition["source_transform_raw"][3]; transition["type19_trigger_file_offset"] = record["file_offset"]

def mesh_lists(stage, model_id):
	_, flags, directory = stage.directories[model_id]; count = ((flags >> 24) & 1) + 1; result = []
	for index in range(count):
		directory_offset = stage.base + (directory & 0xFFFF) * 4 + index * 12; pointer = read_u16(stage.data, directory_offset); header_offset = stage.base + pointer * 4; submeshes, materials, shift, extra = struct.unpack_from("<4B", stage.data, header_offset)
		if not submeshes or not materials: raise ValueError(f"door model {model_id} has an invalid mesh list {index}")
		result.append({"list_index": index, "directory_byte_offset": directory_offset, "mesh_pointer_word": pointer, "mesh_header_byte_offset": header_offset, "submesh_count": submeshes, "material_count": materials, "coordinate_shift": shift, "header_extra": extra})
	return {"directory_flags": flags, "mesh_lists": result}

def export_doors(dat_dir, maps_dir, output_dir):
	stage_path = dat_dir / "ST0F.BIN"; texture_path = dat_dir / "ST0FT.BIN"; source = stage_path.read_bytes(); texture = texture_path.read_bytes(); stage = Stage(source); root = stage.data
	if read_u32(source, 0) != 0x0D or read_u32(source, 4) != len(root): raise ValueError("ST0F root is not the expected type-0x0D section")
	if read_u32(root, 8 + GRID_TABLE_INDEX * 4) * 4 != GRID_BASE: raise ValueError("unexpected ST0F minimap grid table")
	if struct.unpack_from("<4I", texture) != (1, 0x1AA88, 0x36, 0x800E7000): raise ValueError("unexpected ST0FT overlay header")
	pointers = struct.unpack_from("<14H", texture, AREA_POINTER_OFFSET)
	if pointers[AREA_COUNT] != 0 or not all(pointers[:AREA_COUNT]): raise ValueError("unexpected ST0FT area pointer table")
	areas = []; endpoints = []
	for area_index, pointer in enumerate(pointers[:AREA_COUNT]):
		origin_x, origin_z, width, height, extra_x, extra_z = struct.unpack_from("<4Bhh", texture, AREA_LAYOUT_OFFSET + area_index * 8); root_offset = GRID_BASE + (pointer - pointers[0]) * 8; cells = root[root_offset:root_offset + width * height]
		if len(cells) != width * height or origin_x + width + 1 != 64 or origin_z + height + 1 != 64: raise ValueError(f"invalid ST0F area grid {area_index}")
		area = {"index": area_index, "pointer": pointer, "root_offset": root_offset, "origin_x": origin_x, "origin_z": origin_z, "width": width, "height": height, "extra_x": extra_x, "extra_z": extra_z}; areas.append(area); stage_area = stage.area(area_index); area_placement_ids = set(stage_area[1]) if stage_area else set()
		for row in range(height):
			for column in range(width):
				tile_id = cells[row * width + column]
				if tile_id not in DOOR_TILE_IDS: continue
				local_x_px = -8 * width + 16 * column + 8; local_y_px = 8 * height - 16 - 16 * row + 8; world_x = -local_x_px / 4; world_z = -local_y_px / 4; matches = []
				for placement_id, (state, model_id, flags, height_word, x, z) in enumerate(stage.placements):
					if placement_id not in area_placement_ids or model_id != tile_id: continue
					_, model_flags, _ = stage.directories[model_id]; placement_x = -((x << 9) * UNIT - (0x7E00 if model_flags & 0x10000000 else 0x7F00) * UNIT); placement_z = (z << 9) * UNIT - (0x7E00 if model_flags & 0x20000000 else 0x7F00) * UNIT
					if (placement_x, placement_z) == (world_x, world_z): matches.append({"placement_id": placement_id, "state_raw": state, "flags_raw": flags, "height_raw": height_word, "tile_position": [x, z], "world_xz": [placement_x, placement_z]})
				if len(matches) != 1: raise ValueError(f"area {area_index} tile {tile_id:#04x} at ({column},{row}) maps to {len(matches)} exact root placements")
				placement = matches[0]; model = mesh_lists(stage, tile_id); global_x_px = extra_x + local_x_px; global_y_px = extra_z + local_y_px
				endpoints.append({"area_index": area_index, "tile_id": tile_id, "grid_cell": [column, row], "root_grid_byte_offset": root_offset + row * width + column, "local_center_pixels": [local_x_px, local_y_px], "full_map_center_pixels": [global_x_px, global_y_px], "model_id": tile_id, "placement": placement, "mesh": model})
	groups = defaultdict(list)
	for endpoint in endpoints: groups[tuple(endpoint["full_map_center_pixels"])].append(endpoint)
	layout_edges = []; shared_locations = []
	for point, members in sorted(groups.items()):
		members.sort(key=lambda item: item["area_index"])
		if len(members) == 2 and members[0]["area_index"] != members[1]["area_index"]:
			layout_edges.append({"areas": [members[0]["area_index"], members[1]["area_index"]], "full_map_center_pixels": list(point), "endpoints": members})
		else: shared_locations.append({"full_map_center_pixels": list(point), "endpoints": members, "status": "multiple area endpoints share this marker coordinate; destination selection is unresolved"})
	area_transitions, other_area_records = area_transition_records(texture); area_edges = transition_edges(area_transitions)
	group_size = stage.placement_count // stage.scripted_count if stage.scripted_count else 0; group_count = stage.scripted_count; group_table_offset = stage.placement_base + 4 + stage.placement_count * 8
	if not group_size or group_size * group_count * 4 != len(root) - group_table_offset: raise ValueError("ST0F placement index table has an unexpected size")
	group_values = struct.unpack_from("<" + "I" * (group_size * group_count), root, group_table_offset); placement_groups = [list(group_values[i * group_size:(i + 1) * group_size]) for i in range(group_count)]
	if sorted(group_values) != list(range(stage.placement_count)): raise ValueError("ST0F placement index groups are not a permutation of placements")
	actor_archives = []; actor_payloads = []
	for name in ("ST0F00.BIN", "ST0F01.BIN"):
		archive, payload = actor_archive(dat_dir / name); actor_archives.append(archive); actor_payloads.append(payload)
	area_objects, actor_resource_models = area_object_records(texture, actor_archives[0]["model_count"]); bind_trigger_records(area_objects, area_transitions)
	actor_candidate = export_actor_model(actor_payloads[0], 7, texture_path, output_dir / "actor_model_07.glb")
	runtime_transition = transition_metadata(texture)
	typec_offset = 0xC800; typec_type, typec_size, typec_count = struct.unpack_from("<3I", source, typec_offset); typec_payload, typec_metadata = actor_payloads[0], None
	if typec_type != 0x0C or typec_size != len(typec_payload): raise ValueError("ST0F embedded type-0x0C section does not match ST0F00 actor archive payload")
	typec_payload = (maps_dir / "ST0F_0C800.bin").read_bytes()
	if typec_payload != actor_payloads[0]: raise ValueError("extracted ST0F type-0x0C payload differs from the ST0F00 archive payload")
	actor_source = {"archive_format": "DashGL type-0x0A scene model list: u32 model count then 16-byte {flags, mesh, animation tracks, animation controls} entries", "archives": actor_archives, "embedded_type_0x0C": {"file_offset": typec_offset, "size": typec_size, "header_count": typec_count, "payload_file": "build/maps/ST0F_0C800.bin", "payload_sha256": sha256(typec_payload), "matches_ST0F00_payload": True}}
	output_dir.mkdir(parents=True, exist_ok=True)
	manifest = {"stage": "ST0F", "source": {"root_file": "build/disc-assets/DAT/ST0F.BIN", "root_sha256": sha256(source), "root_type": 13, "decoded_root_size": len(root), "texture_overlay_file": "build/disc-assets/DAT/ST0FT.BIN", "texture_overlay_sha256": sha256(texture), "area_pointer_offset": AREA_POINTER_OFFSET, "area_layout_offset": AREA_LAYOUT_OFFSET, "area_transition_pointer_offset": AREA_TRANSITION_POINTER_OFFSET, "area_transition_record_size": AREA_TRANSITION_RECORD_SIZE, "area_object_pointer_offset": AREA_OBJECT_POINTER_OFFSET, "area_object_record_size": AREA_OBJECT_RECORD_SIZE, "actor_resource_map_offset": ACTOR_RESOURCE_MAP_OFFSET, "grid_base": GRID_BASE, "grid_table_index": GRID_TABLE_INDEX}, "placement_index_groups": {"placement_base": stage.placement_base, "placement_count": stage.placement_count, "header_scripted_count": stage.scripted_count, "tail_byte_offset": group_table_offset, "group_size": group_size, "interpretation": "raw placement-index permutation; runtime meaning not traced", "groups": placement_groups}, "actor_archives": actor_source, "actor_resource_model_map": actor_resource_models, "area_object_records": area_objects, "actor_model_candidate": actor_candidate, "runtime_transition": runtime_transition, "coordinate_mapping": {"tile_pixels": 16, "world_units_per_tile": 4, "transition_position_units": "signed raw coordinates / 256", "transition_heading": "unsigned 0..4095 turn units; runtime subtracts 0x800 at destination setup", "portal_center": "tile center: local pixel x=-8*width+16*column+8, y=8*height-16-16*row+8; world x=-local_x/4, z=-local_y/4", "full_map_center": "extraX+local_x, extraZ+local_y", "door_mesh_placement_transform": "x=-((placement_x<<9)/256 - directory_x_offset/256); z=(placement_z<<9)/256 - directory_z_offset/256"}, "areas": [{"index": area["index"], "width": area["width"], "height": area["height"], "extra_pixels": [area["extra_x"], area["extra_z"]], "world_offset": [-area["extra_x"] / 4, 0, -area["extra_z"] / 4]} for area in areas], "marker_ids": {"range": [92, 95], "source_grid_values": sorted(set(endpoint["tile_id"] for endpoint in endpoints)), "matched_mesh_model_id": "equal to marker tile ID; each center matched one exact root placement"}, "area_transitions": area_transitions, "area_edges": area_edges, "non_transition_area_records": other_area_records, "layout_adjacency": {"paired_marker_locations": layout_edges, "shared_marker_locations": shared_locations}, "unresolved": {"runtime_destination_state": "type-0x19 writer and trigger positions are now source-bound; the runtime code that maps each area-list route into destination area-object slots is still unresolved", "required_gates": "the type-0x19 record word at +8 is preserved raw but its gate semantics are unresolved", "door_open_animation": "actor model 7 has original control tracks and is exported as a candidate; its binding to portal placements remains unverified"}}
	path = output_dir / "doors.json"; write_output(path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	print(f"ST0F doors: {len(endpoints)} exact mesh endpoints, {len(area_transitions)} source transitions across {len(area_edges)} area links -> {path}")
	return manifest

def doors_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--maps-dir", type=Path, default=Path("build/maps")); parser.add_argument("--output-dir", type=Path, default=Path("assets/levels/ST0F")); args = parser.parse_args(); export_doors(args.dat_dir, args.maps_dir, args.output_dir)

SCRIPT_AREA_POINTER_OFFSET = 0x18F04
SCRIPT_AREA_COUNT = 9
SCRIPT_RECORD_SIZE = 24
GLOBAL_AREA_SCRIPT_POINTER_OFFSET = 0x18FC0
GLOBAL_AREA_SCRIPT_COUNT = 13
GLOBAL_AREA_SCRIPT_RECORD_SIZE = 8
ACTOR_BEHAVIOR_DISPATCH = {0: {"callback": "0x800ED998", "control_codes": [1, 4]}, 1: {"callback": "0x800EDB9C", "control_codes": [0, 1, 4]}, 2: {"callback": "0x800EDF74", "control_codes": [0, 2, 3, 7]}, 3: {"callback": "0x800EE224", "control_codes": [0, 1, 3, 4]}}


def signed8(value): return value - 256 if value & 0x80 else value

def source_combat_attributes(game, actor_class, resource_key):
	base = 0x800AD000; table = 0x800DE8B4; difficulties = []
	for difficulty in range(5):
		class_table = read_u32(game, table - base + 0x30 + difficulty * 4); attribute_table = read_u32(game, class_table - base + 0x30 + actor_class * 4); address = attribute_table + resource_key * 16; attributes = list(game[address - base + 0x30:address - base + 0x30 + 16]); scale = 1 if actor_class == 5 else 4
		difficulties.append({"difficulty_index": difficulty, "class_table_ram": hex(class_table), "attribute_ram": hex(address), "attributes": attributes, "health_scale": scale, "health": attributes[0] * scale, "contact_damage": attributes[1] * scale, "charge_damage": attributes[2] if actor_class == 5 else None, "attack_damage": attributes[2] * 4 if actor_class == 8 else None})
	return {"file": "build/disc-assets/COMMON/GAME.BIN", "difficulty_pointer_table_ram": hex(table), "difficulty_initializer": "GAME.BIN 0x800D97B4", "normal_difficulty_indices": [0, 1], "variants": difficulties, "normal": difficulties[1]}

def parse_global_area_script_routes(texture):
	base = 0x800E7000; pointers = struct.unpack_from("<13I", texture, GLOBAL_AREA_SCRIPT_POINTER_OFFSET); routes = []; script_area_routes = {}
	for global_area_index, pointer in enumerate(pointers):
		file_offset = 0x30 + pointer - base; entries = []
		if file_offset < 0 or file_offset >= len(texture): raise ValueError(f"ST0FT global area {global_area_index} has an invalid script map pointer")
		for entry_index in range(64):
			at = file_offset + entry_index * GLOBAL_AREA_SCRIPT_RECORD_SIZE; raw = texture[at:at + GLOBAL_AREA_SCRIPT_RECORD_SIZE]
			if len(raw) != GLOBAL_AREA_SCRIPT_RECORD_SIZE: raise ValueError(f"ST0FT global area {global_area_index} script map is truncated")
			if raw[0] == 0xFF: break
			script_area_index = raw[2]; flags = raw[3]
			if script_area_index >= SCRIPT_AREA_COUNT: raise ValueError(f"ST0FT global area {global_area_index} maps to invalid script area {script_area_index}")
			condition = {"selector_mask": 1, "selector_value": 0, "selector_input": 0, "player_position_offsets": [0x12, 0x1A], "position_shift": 9, "minimum_bins": [signed8(raw[4]), signed8(raw[5])], "span_bins": [raw[6], raw[7]], "upper_bound_exclusive": True}; entry = {"entry_index": entry_index, "script_area_index": script_area_index, "flags": flags, "yaw_offset_gate": bool(flags & 0x80), "condition": condition, "source_file_offset": at}; entries.append(entry)
			if not (flags & 1): script_area_routes.setdefault(script_area_index, []).append({"global_area_index": global_area_index, **entry})
		routes.append({"global_area_index": global_area_index, "pointer_ram": hex(pointer), "pointer_file_offset": file_offset, "entries": entries})
	return routes, script_area_routes

def export_static_actor(payload, model_index, texture_path, output_path, source_name="ST0F00.BIN"):
	count = read_u32(payload, 0)
	if model_index >= count: raise ValueError("actor model index is outside the archive")
	flags, mesh, tracks, controls = struct.unpack_from("<4I", payload, 4 + model_index * 16); n_high, n_medium, n_low, mesh_extra = struct.unpack_from("<4B", payload, mesh); high, medium, low, bone_offset, hierarchy_offset, texture_offset, bounds_offset = struct.unpack_from("<7I", payload, mesh + 4)
	if bone_offset or not n_high: raise ValueError(f"{source_name} model {model_index} is not a static high-LOD mesh")
	texture_info = read_u32(payload, texture_offset); tpage = texture_info & 0xFFFF; clut = texture_info >> 16; vram, _ = textures(texture_path); texture_png = png(256, 256, decode_page(vram, tpage, clut)); builder = GlbBuilder(); image_view = builder.view(texture_png); groups = {}; face_count = 0
	for part in range(n_high):
		tri_count, quad_count, vertex_count, exponent, tri_offset, quad_offset, vertex_offset = struct.unpack_from("<4B3I", payload, high + part * 16); scale = (0.5 if exponent == 0xFF else 1 << exponent) / 2048.0; vertices = [pbd_position(read_u32(payload, vertex_offset + index * 4), scale) for index in range(vertex_count)]
		for is_quad, faces, face_offset in ((False, tri_count, tri_offset), (True, quad_count, quad_offset)):
			for face in range(faces):
				at = face_offset + face * 12; uv_bytes = payload[at:at + 8]; packed = read_u32(payload, at + 8); raw_indices = tuple((packed >> (7 * index)) & 0x7F for index in range(4)); material = (packed >> 28) & 3
				if any(index >= vertex_count for index in raw_indices[:4 if is_quad else 3]): raise ValueError(f"{source_name} model {model_index} has an invalid face index")
				triangles = (((raw_indices[0], raw_indices[2], raw_indices[1]), (0, 2, 1)), ((raw_indices[1], raw_indices[2], raw_indices[3]), (1, 2, 3))) if is_quad else (((raw_indices[0], raw_indices[2], raw_indices[1]), (0, 2, 1)),)
				for triangle, corners in triangles:
					points = [vertices[index] for index in triangle]; ab = tuple(points[1][axis] - points[0][axis] for axis in range(3)); ac = tuple(points[2][axis] - points[0][axis] for axis in range(3)); normal = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]); size = sum(value * value for value in normal) ** 0.5; normal = tuple(value / size for value in normal) if size else (0.0, 1.0, 0.0); target = groups.setdefault(material, {"positions": [], "normals": [], "uvs": [], "indices": []}); base = len(target["positions"]) // 3
					for corner in range(3):
						target["positions"].extend(points[corner]); target["normals"].extend(normal); uv_index = corners[corner]; target["uvs"].extend(((uv_bytes[uv_index * 2] + 0.5) / 256.0, (uv_bytes[uv_index * 2 + 1] + 0.5) / 256.0)); target["indices"].append(base + corner)
					face_count += 1
	materials = [{"name": f"source_material_{material}", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "alphaMode": "BLEND"} for material in sorted(groups)] or [{"name": "source_material_0", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "alphaMode": "BLEND"}]; primitives = []
	for material, values in groups.items():
		attributes = {"POSITION": builder.accessor(values["positions"], "f", 5126, "VEC3", 34962, True), "NORMAL": builder.accessor(values["normals"], "f", 5126, "VEC3", 34962), "TEXCOORD_0": builder.accessor(values["uvs"], "f", 5126, "VEC2", 34962)}; indices = builder.accessor(values["indices"], "H", 5123, "SCALAR", 34963); primitives.append({"attributes": attributes, "indices": indices, "material": sorted(groups).index(material), "mode": 4})
	model_name = f"{Path(source_name).stem}_model_{model_index:02d}"
	document = {"asset": {"version": "2.0", "generator": "Native static actor exporter"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": model_name, "mesh": 0}], "meshes": [{"name": model_name, "primitives": primitives}], "materials": materials, "textures": [{"sampler": 0, "source": 0}], "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}], "images": [{"bufferView": image_view, "mimeType": "image/png"}], "extras": {"source_archive": source_name, "source_model_index": model_index, "source_flags": flags, "source_mesh_offset": mesh, "texture_tpage": tpage, "texture_clut": clut, "bone_count": 0, "control_count": 0, "face_count": face_count, "lod_counts": [n_high, n_medium, n_low]}}
	output_path.parent.mkdir(parents=True, exist_ok=True); builder.save(output_path, document)
	return {"file": output_path.resolve().relative_to(ROOT).as_posix(), "source_model_index": model_index, "source_flags": flags, "mesh_offset": mesh, "texture_tpage": tpage, "texture_clut": clut, "bone_count": 0, "control_count": 0, "face_count": face_count, "lod_counts": [n_high, n_medium, n_low]}

def parse_actor_instances(texture, model_count):
	base = 0x800E7000; pointers = struct.unpack_from("<13I", texture, AREA_OBJECT_POINTER_OFFSET); boundaries = [0x30 + pointer - base for pointer in pointers] + [AREA_OBJECT_POINTER_OFFSET]; resource_map = list(texture[ACTOR_RESOURCE_MAP_OFFSET:ACTOR_RESOURCE_MAP_OFFSET + 24]); records = []
	if any(boundaries[index] >= boundaries[index + 1] for index in range(AREA_COUNT)): raise ValueError("ST0FT area actor pointers are not ascending")
	for area_index, start in enumerate(boundaries[:-1]):
		end = boundaries[area_index + 1]
		if (end - start) % AREA_OBJECT_RECORD_SIZE: raise ValueError(f"ST0FT area {area_index} actor list has a partial record")
		terminated = False
		for offset in range(start, end, AREA_OBJECT_RECORD_SIZE):
			raw = texture[offset:offset + AREA_OBJECT_RECORD_SIZE]
			if raw[0] == 0xFF:
				if any(raw[1:]) or offset + AREA_OBJECT_RECORD_SIZE != end: raise ValueError(f"ST0FT area {area_index} has a malformed actor-list terminator")
				terminated = True; break
			if raw[2] != 0x20: continue
			resource_slot = raw[7]
			if resource_slot >= len(resource_map): raise ValueError(f"ST0FT area {area_index} has invalid actor resource slot {resource_slot}")
			model_index = resource_map[resource_slot]
			if model_index >= model_count: raise ValueError(f"ST0FT area {area_index} maps to invalid ST0F00 model {model_index}")
			x, y, z = struct.unpack_from("<3h", raw, 12); yaw = struct.unpack_from("<H", raw, 18)[0]; records.append({"area_index": area_index, "record_index": (offset - start) // AREA_OBJECT_RECORD_SIZE, "file_offset": offset, "record_type": raw[2], "flags": raw[0], "record_class": raw[3], "resource_slot": resource_slot, "model_index": model_index, "model_file": f"actors/ST0F00_model_{model_index:02d}.glb", "transform_raw": [x, y, z, yaw], "transform": {"position": [-x * UNIT, -y * UNIT, z * UNIT], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0}, "source_bytes_hex": raw.hex()})
		if not terminated: raise ValueError(f"ST0FT area {area_index} actor list has no 0xFF terminator")
	return records, resource_map

def parse_script_actor_instances(texture, model_count, script_area_routes):
	base = 0x800E7000; pointers = struct.unpack_from("<9I", texture, SCRIPT_AREA_POINTER_OFFSET); boundaries = [0x30 + pointer - base for pointer in pointers] + [SCRIPT_AREA_POINTER_OFFSET]; records = []
	if any(boundaries[index] >= boundaries[index + 1] for index in range(SCRIPT_AREA_COUNT)): raise ValueError("ST0FT script actor pointers are not ascending")
	for area_index, start in enumerate(boundaries[:-1]):
		end = boundaries[area_index + 1]
		if (end - start) % SCRIPT_RECORD_SIZE: raise ValueError(f"ST0FT area {area_index} script list has a partial record")
		terminated = False
		for offset in range(start, end, SCRIPT_RECORD_SIZE):
			raw = texture[offset:offset + SCRIPT_RECORD_SIZE]
			if raw[0] == 0xFF:
				if any(raw[1:]) or offset + SCRIPT_RECORD_SIZE != end: raise ValueError(f"ST0FT area {area_index} has a malformed script-list terminator")
				terminated = True; break
			if raw[2] != 0x20: continue
			actor_class = raw[4]; model_index = 5 if actor_class == 5 and raw[7] == 1 else 6 if actor_class == 8 and raw[7] == 0 else -1
			if model_index < 0 or model_index >= model_count: raise ValueError(f"ST0FT area {area_index} script actor has unresolved source class {actor_class}, resource {raw[7]}")
			x, y, z = struct.unpack_from("<3h", raw, 12); yaw = struct.unpack_from("<H", raw, 18)[0]; instance_id = read_u32(raw, 20); spawn_routes = script_area_routes.get(area_index, []); records.append({"area_index": area_index, "script_area_index": area_index, "global_area_indices": sorted({route["global_area_index"] for route in spawn_routes}), "global_area_spawn_routes": [{**route, "actor_yaw_offset_raw": 0x800 if route["yaw_offset_gate"] and raw[1] & 0x80 else 0} for route in spawn_routes], "record_index": (offset - start) // SCRIPT_RECORD_SIZE, "file_offset": offset, "record_type": raw[2], "flags": raw[0], "flags2": raw[1], "record_class": raw[3], "actor_class": actor_class, "dispatch_index": raw[6], "model_index": model_index, "actor_resource_key": raw[7], "instance_id": instance_id, "activation_flag_id": instance_id, "activation_flag_word": instance_id >> 5, "activation_flag_mask": 0x80000000 >> (instance_id & 31), "model_file": f"actors/ST0F00_model_{model_index:02d}.glb", "transform_raw": [x, y, z, yaw], "transform": {"position": [-x * UNIT, -y * UNIT, z * UNIT], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0}, "source_bytes_hex": raw.hex()})
		if not terminated: raise ValueError(f"ST0FT area {area_index} script list has no 0xFF terminator")
	return records

def export_pickup_data(game, output_dir):
	executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); offset = lambda address: 0x30 + address - 0x800AD000; exe_offset = lambda address: 0x800 + address - 0x80010000
	vertices = [list(struct.unpack_from("<3h", executable, exe_offset(0x8006AF54) + index * 8)) for index in range(10)]; faces = []
	for side in range(4):
		a, b, c, d = 1 + side, 1 + ((side + 1) & 3), 5 + side, 5 + ((side + 1) & 3); faces.extend([[0, a, b], [a, c, b], [b, c, d], [9, d, c]])
	data = {"source": {"drop_factory": "SLES0x80039EA8", "drop_profiles": "GAME0x800DE8DC", "money_geometry": "SLES0x8006AF54 / renderer0x8003A8EC-0x8003ACC8", "color_pairs": "SLES0x8006B060", "pickup_update": "GAME0x800D0DFC", "collection": "GAME0x800D13E8", "wallet": "SLES0x80043E78"}, "profiles": [list(game[offset(0x800DE8DC) + index * 24:offset(0x800DE8DC) + (index + 1) * 24]) for index in range(40)], "values": [list(struct.unpack_from("<7h", game, offset(address))) for address in [0x800DCDA4, 0x800DCDB4, 0x800DCDC4]], "money_vertices_raw": vertices, "money_triangles": faces, "energy_vertices_raw": [list(struct.unpack_from("<3h", executable, exe_offset(0x8006AFA4) + index * 8)) for index in range(6)], "health_vertices_raw": [list(struct.unpack_from("<3h", executable, exe_offset(0x8006AFD4) + index * 8)) for index in range(16)], "colors": [list(struct.unpack_from("<8B", executable, exe_offset(0x8006B060) + index * 8)) for index in range(9)], "pickup_radius_raw": 64, "magnet_radius_raw": 160, "magnet_speed_raw": 576, "lifetime_ticks": 256, "gravity_raw": 48, "sound_ids": [0x85, 0x86, 0x86], "wallet_max": 9999999, "unit_raw": 256, "physics_velocity_raw": 4096}
	from ui import textures, decode_page, hud_crop, png
	vram, _ = textures(ROOT / "build/disc-assets/COMMON/GAME.BIN"); page = decode_page(vram, 0x2F, 0x7C12, True); health_sprite = hud_crop(page, 0x00, 0x20, 32, 32); energy_sprite = hud_crop(page, 0x40, 0x20, 32, 32)
	write_output(output_dir / "pickup_sprites.png", png(64, 32, b"".join(health_sprite[row * 128:(row + 1) * 128] + energy_sprite[row * 128:(row + 1) * 128] for row in range(32))))
	data["sprites"] = {"texture": "res://" + output_dir.relative_to(ROOT).as_posix() + "/pickup_sprites.png", "source": "SLES0x8003A82C (energy) / 0x8003ACD8 (health): GP0 0x2E record, tpage 0x2F (VRAM 960,0), CLUT 0x7C12, rgb 0x80, additive", "energy": {"uv_raw": [0x40, 0x20, 32, 32], "atlas_x": 32, "size_shift": 1}, "health": {"uv_raw": [0, 0x20, 32, 32], "atlas_x": 0, "size_shift": 0}, "size_field": "(size >> shift) = half diagonal in raw units; record+0x18 high half = (spin >> 1) & 0xFFF", "angle_base_raw": 0x600, "consumer": "SLES0x800390F4 case 0x2C (tables 0x800965D8 cos / 0x800968D0 sin, 64 steps); corners A=C-h, B=C+h, C+rot90(h), C-rot90(h) with rot90(x,y)=(-y,x), uv order A,C+rot90(h),C-rot90(h),B"}
	data["tick_rate"] = 25
	data["bob_samples_raw"] = [struct.unpack_from("<h", executable, exe_offset(0x80073E4E) + phase * 256)[0] for phase in range(64)]; data["hitbox_raw"] = list(struct.unpack_from("<6h", game, offset(0x800DCD98))); data["source"]["rest"] = "GAME0x800D0E54 floor GAME0x800B13B4 minus hitbox 0x800DCD98 +6; airborne when above by 0x30; bob GAME0x800D121C table SLES0x80073E4E->0x800965D8"
	data["money_triangle_phases"] = [[(16 * ((side - 1) & 3) + 8 * slot) & 31 for slot in slots] for side in range(4) for slots in ([1, 2, 3], [0, 2, 1], [1, 2, 3], [2, 1, 0])]
	write_output(output_dir / "pickups.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data
SCRIPT_LOCAL_CONTEXT_RESET = {"owner_ram": "0x8009BE08", "initialized_offsets": [0, 1, 2, 3], "initial_value": 0, "source_reset": "GAME.BIN 0x800AEA58 -> 0x800BA374 -> 0x800BA408 -> 0x800C02D0"}
FLUTTER_ROLL_DATA = (0x8ED0, 0x8EE4); FLUTTER_DATA_ALONE = (0x8EF8,); FLUTTER_BYTE45 = {"kind": "native_save_byte_equals", "key": "native_save_byte45", "ram": "0x8009C82D", "default": 1, "default_source": "GAME.BIN 0x800AE3A0 (game-block defaults 0x800AE328: +0x44 = +0x45 = 1)"}
def flutter_revisit_sets(area_dispatch):
	source = lambda caller, pointer, count, note: {"file": "ST04T.BIN", "caller": caller, "consumer": "GAME.BIN 0x800C0818", "record_pointer_ram": pointer, "record_count": count, "area_dispatch": area_dispatch, "script_function": "0x800E7828", "note": note}
	state = lambda value: [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": value}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}]
	late = [{"kind": "stage_state_byte_range", "ram": "0x8009C7FC", "minimum": 3, "maximum": 20}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}]
	flag = lambda id, value: {"kind": "native_event_flag", "id": id, "set": value}
	return [{"id": "revisit_byte14_0_roll_data", "area_index": 0, "source": source("0x800E7998", "0x800EFEA0", 2, "0x800E7B10 calls 0x800E7828 once flag 0x5F0 is set; byte14 < 3 and != 2 -> 0x800E78B4 -> 0x800E7990"), "predicate": {"all": state(0) + [flag(0x5F0, True)]}, "record_offsets": list(FLUTTER_ROLL_DATA)},
		{"id": "revisit_byte14_1_roll_data", "area_index": 0, "source": source("0x800E7998", "0x800EFEA0", 2, "0x800E7B88 calls 0x800E7828; byte14 < 3 and != 2 -> 0x800E78B4 -> 0x800E7990"), "predicate": {"all": state(1)}, "record_offsets": list(FLUTTER_ROLL_DATA)},
		{"id": "late_flag0d3_data", "area_index": 0, "source": source("0x800E7998", "0x800EFEC8", 1, "0x800E7BF0 calls 0x800E7828; byte14 >= 3 after the 0xD1/+0x45 flag script: 0xD3 set -> 0x800E7964 -> 0x800E7980"), "predicate": {"all": late + [flag(0xD3, True)]}, "record_offsets": list(FLUTTER_DATA_ALONE)},
		{"id": "late_flag127_data", "area_index": 0, "source": source("0x800E7998", "0x800EFEC8", 1, "byte14 >= 3: 0xD3 clear and 0x127 set -> 0x800E797C"), "predicate": {"all": late + [flag(0xD3, False), flag(0x127, True)]}, "record_offsets": list(FLUTTER_DATA_ALONE)},
		{"id": "late_roll_data", "area_index": 0, "source": source("0x800E7998", "0x800EFEA0", 2, "byte14 >= 3: 0xD3 and 0x127 clear -> 0x800E798C"), "predicate": {"all": late + [flag(0xD3, False), flag(0x127, False)]}, "record_offsets": list(FLUTTER_ROLL_DATA)}]
def flutter_pre_spawn_scripts():
	flag = lambda id, value: {"kind": "native_event_flag", "id": id, "set": value}; byte45 = lambda value, negate=False: dict(FLUTTER_BYTE45, value=value, negate=negate)
	area0 = {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}; d1 = flag(0xD1, False)
	guard = {"all": [flag(0xDF, True), flag(0x134, False)]}; upkeep = [{"kind": "set_save_byte", "key": "native_save_byte7c", "ram": "0x8009C864", "value": 1, "when": guard, "source": "0x800E7868..0x800E7870 (ordered first: same guard as the 0x134 set it follows natively)"}, {"kind": "set_event_flag", "id": 0x134, "when": guard, "source": "0x800E7834..0x800E7864"}]
	late = [{"kind": "set_event_flag", "id": 0xD3, "when": {"all": [d1, byte45(0), flag(0xDE, False)]}, "source": "0x800E78BC..0x800E78F0"},
		{"kind": "clear_event_flag", "id": 0xD3, "when": {"all": [d1, byte45(0, True)]}, "source": "0x800E78FC..0x800E7910"},
		{"kind": "set_event_flag", "id": 0x127, "when": {"all": [d1, byte45(2), flag(0x128, False)]}, "source": "0x800E7914..0x800E7938"},
		{"kind": "clear_event_flag", "id": 0x127, "when": {"all": [d1, byte45(0, True), byte45(2, True)]}, "source": "0x800E7944..0x800E7958"},
		{"kind": "clear_event_flag", "id": 0x127, "when": {"all": [d1, byte45(2), flag(0x128, True)]}, "source": "0x800E7944..0x800E7958"}]
	note = "ST04T 0x800E7828 runs before 0x800C0818 picks the spawn table; the runtime applies these actions in order before evaluating spawn_sets"
	return [{"id": "flutter_area0_upkeep_byte14_0", "area_index": 0, "predicate": {"all": [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": 0}, area0, flag(0x5F0, True)]}, "actions": upkeep, "source": note},
		{"id": "flutter_area0_upkeep_byte14_1_20", "area_index": 0, "predicate": {"all": [{"kind": "stage_state_byte_range", "ram": "0x8009C7FC", "minimum": 1, "maximum": 20}, area0]}, "actions": upkeep, "source": note},
		{"id": "flutter_area0_late_flags", "area_index": 0, "predicate": {"all": [{"kind": "stage_state_byte_range", "ram": "0x8009C7FC", "minimum": 3, "maximum": 20}, area0]}, "actions": late, "source": note}]
def export_flutter_scripted_actors(dat_dir, output_dir):
	from disc import decompress_section
	import world
	dat_dir = Path(dat_dir).resolve(); output_dir = Path(output_dir); stage = "ST04"; root_path = dat_dir / "ST04.BIN"; overlay_path = dat_dir / "ST04T.BIN"; root = root_path.read_bytes(); overlay = overlay_path.read_bytes(); source, section = decompress_section(root, 0x6800); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(source), section["section_count"]); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); normalized = work / "ST04_models.bin"; write_output(normalized, header + source); archive, payload = actor_archive(normalized)
	area_dispatch = {"table_ram": "0x800EFE4C", "state_byte_offset": 0x14, "state2_row_ram": "0x800EFE40", "area_byte_offset": 0x11, "area0_callback": "0x800E7BF0", "area0_callback_calls": "0x800E7828", "area1_callback": "0x800E7C10", "area2_callback": "0x800E7C98"}; spawn_sets = [{"id": "state2_flag5a0_set", "area_index": 0, "source": {"file": "ST04T.BIN", "caller": "0x800E798C", "consumer": "GAME.BIN 0x800C0818", "record_pointer_ram": "0x800EFEA0", "record_count": 2, "area_dispatch": area_dispatch}, "predicate": {"all": [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": 2}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}, {"kind": "native_event_flag", "id": 0x5A0, "set": True}]}, "record_offsets": [0x8ED0, 0x8EE4]}, {"id": "state2_flag5a0_clear", "area_index": 0, "source": {"file": "ST04T.BIN", "caller": "0x800E78A8", "consumer": "GAME.BIN 0x800C0818", "record_pointer_ram": "0x800EFEC8", "record_count": 1, "area_dispatch": area_dispatch}, "predicate": {"all": [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": 2}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}, {"kind": "native_event_flag", "id": 0x5A0, "set": False}]}, "record_offsets": [0x8EF8]}, {"id": "flutter_first_visit_scene", "area_index": 0, "source": {"file": "ST04T.BIN", "caller": "0x800E7B10", "area_dispatch": {**area_dispatch, "row_ram": "0x800EFE28", "area0_callback": "0x800E7B10"}, "native_side_effects": [{"kind": "set_event_flag", "id": 0x5F0}, {"kind": "set_event_flag", "id": 0xD0}, {"kind": "set_event_flag", "id": 0xD1}, {"kind": "set_event_flag", "id": 0xD2}, {"kind": "call", "function": "GAME.BIN 0x800C0B0C", "argument": 0x4C}], "native_side_effect_sources": ["0x800E7B30", "0x800E7B38", "0x800E7B40", "0x800E7B48", "0x800E7B50"]}, "predicate": {"all": [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": 0}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": 0}, {"kind": "native_event_flag", "id": 0x5F0, "set": False}]}, "record_offsets": []}] + flutter_revisit_sets(area_dispatch); records = []; models = {}
	for spawn_set in spawn_sets:
		for ordinal, offset in enumerate(spawn_set["record_offsets"]):
			raw = overlay[offset:offset + 20]
			if len(raw) != 20 or raw[2] != 0x20: raise ValueError(f"ST04 scripted actor record at {offset:#x} is invalid")
			resource_flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [entry for entry in archive["models"] if entry["flags"] == resource_flags]
			if len(matches) != 1: raise ValueError(f"ST04 scripted actor at {offset:#x} has no unique native model resource")
			model_index = matches[0]["index"]; model_file = f"actors/ST04_model_{model_index:02d}.glb"
			if model_index not in models:
				model = export_actor_model(payload, model_index, overlay_path, output_dir / model_file, root_path.name); model["model_index"] = model_index; model["model_file"] = model_file; model["native_resource_flags"] = resource_flags; model["native_scale_raw"] = list(struct.unpack_from("<3h", payload, matches[0]["mesh_offset"] + 0x30)); model["character_name"] = "Roll" if model_index == 0 else "Data"; models[model_index] = model
			x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); records.append({"stage": stage, "spawn_set": spawn_set["id"], "source_pc": spawn_set["source"]["caller"], "record_ordinal": ordinal, "file_offset": offset, "source_record_ram": hex(0x800E7000 + offset - 0x30), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "resource_variant": raw[6], "resource_key": raw[7], "control": raw[8], "frame": raw[9], "native_private_raw": list(raw[8:12]), "source_bytes_hex": raw.hex(), "model_index": model_index, "model_file": model_file, "character_name": "Roll" if model_index == 0 else "Data", "native_resource_flags": resource_flags, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0, "floor_height": y == -1}})
	manifest = {"stage": stage, "source": {"archive_file": str(root_path.relative_to(ROOT)), "archive_sha256": sha256(root), "archive_section": 0x6800, "archive_section_type": 0x0C, "overlay_file": str(overlay_path.relative_to(ROOT)), "overlay_sha256": sha256(overlay), "record_size": 20, "resource_match": "PBD flags == record byte+2 | byte+4<<8 | byte+6<<16", "record_consumer": "GAME.BIN 0x800C0818 calls 0x800C05E0 and registers each actor by record byte+1", "local_context_reset": SCRIPT_LOCAL_CONTEXT_RESET, "coordinate_unit": "1/256 map unit", "coordinate_basis": "canonical stage mesh (-X,-Y,+Z)"}, "spawn_sets": spawn_sets, "pre_spawn_scripts": flutter_pre_spawn_scripts(), "instances": records, "models": [models[index] for index in sorted(models)], "identity_evidence": {"model_0": {"character": "Roll", "bones": 11, "used_atlas_y": [0.5, 127.5], "features": "Roll head and clothing UV region"}, "model_1": {"character": "Data", "bones": 7, "used_atlas_y": [128.5, 244.5], "features": "Data face and body UV region"}}}
	world.bind_scripted_interactions(stage, records, overlay)
	for record in records:
		hitbox = (0x800F256C, 0x800E9C98) if record["source_record_ram"] == "0x800efea0" else (0x800F0630, 0x800E8350) if record["source_record_ram"] in ("0x800efeb4", "0x800efec8") else None
		if hitbox is not None: record["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 0x30 + hitbox[0] - 0x800E7000)), "source_pointer_ram": hex(hitbox[0]), "source_field": "actor+0x58", "source_constructor": hex(hitbox[1]), "source_consumer": "GAME.BIN0x800B13B4->0x800B13FC and 0x800B3564->0x800B36E8", "anchor": "actor+0x10", "bounds_layout": "signed16 x/y/z min/max pairs in 1/256 stage units"}
	bind_native_lock_on(overlay, records); output_dir.mkdir(parents=True, exist_ok=True); write_output(output_dir / "scripted_actors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"ST04 scripted actors: {len(records)} conditional records, {len(models)} original models -> {output_dir / 'scripted_actors.json'}"); return manifest

def export_st08_scripted_actors(dat_dir, output_dir):
	from disc import decompress_section
	import world
	dat_dir = Path(dat_dir).resolve(); output_dir = Path(output_dir); stage = "ST08"; root_path = dat_dir / "ST08.BIN"; overlay_path = dat_dir / "ST08T.BIN"; root = root_path.read_bytes(); overlay = overlay_path.read_bytes(); source, section = decompress_section(root, 0x8800); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(source), section["section_count"]); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); normalized = work / "ST08_models.bin"; write_output(normalized, header + source); archive, payload = actor_archive(normalized); hitbox_pointer = 0x800F5214; hitbox_bounds = list(struct.unpack_from("<6h", overlay, 0x30 + hitbox_pointer - 0x800E7000))
	dispatch = {"file": "ST08T.BIN", "dispatcher": "0x800E762C", "table_ram": "0x800F261C", "rows": [{"native_save_byte14": 0, "row_ram": "0x800F2604", "area_callbacks": {"0": "0x800E769C", "1": "0x800E7738"}}, {"native_save_byte14": 1, "row_ram": "0x800F260C", "area_callbacks": {"0": "0x800E7834", "1": "0x800E7880"}}, {"native_save_byte14": 2, "row_ram": "0x800F260C", "area_callbacks": {"0": "0x800E7834", "1": "0x800E7880"}}, {"native_save_byte14": 3, "row_ram": "0x800F260C", "area_callbacks": {"0": "0x800E7834", "1": "0x800E7880"}}]}
	definitions = [{"id": "flutter_hull_first_visit", "call_pc": 0x800E76D0, "pointer_ram": 0x800F2670, "count": 1, "area": 0, "save_byte14": 0, "script_function": 0x800E769C, "script_slot": 0, "event_flags": [{"id": 0x5E4, "set": False}], "native_side_effects": [{"kind": "set_event_flag", "id": 0x5E4}, {"kind": "call", "function": "GAME.BIN 0x800C0B0C", "argument": 0x55}]}, {"id": "flutter_hull_revisit_group", "call_pc": 0x800E7710, "pointer_ram": 0x800F2670, "count": 5, "area": 0, "save_byte14": 0, "script_function": 0x800E769C, "script_slot": 0, "event_flags": [{"id": 0x5E4, "set": True}], "native_side_effects": [{"kind": "set_event_flag", "id": 0x711, "when_event_flag_clear": 0x5E1}]}, *[{"id": f"flutter_area0_script_{slot}", "call_pc": 0x800E7858, "pointer_ram": 0x800F2670, "count": 4, "area": 0, "save_byte14": slot, "script_function": 0x800E7834, "script_slot": slot, "event_flags": []} for slot in (1, 2, 3)], {"id": "flutter_area1_script0_props", "call_pc": 0x800E7764, "pointer_ram": 0x800F26D4, "count": 1, "area": 1, "save_byte14": 0, "script_function": 0x800E7738, "script_slot": 0, "event_flags": []}, {"id": "flutter_area1_script0_pair", "call_pc": 0x800E7778, "pointer_ram": 0x800F28B8, "count": 2, "area": 1, "save_byte14": 0, "script_function": 0x800E7738, "script_slot": 0, "event_flags": []}, {"id": "flutter_area1_flag5c3_prop", "call_pc": 0x800E77D8, "pointer_ram": 0x800F2908, "count": 1, "area": 1, "save_byte14": 0, "script_function": 0x800E7738, "script_slot": 0, "event_flags": [{"id": 0x5C3, "set": True}]}, *[{"id": f"flutter_area1_script_{slot}", "call_pc": 0x800E78A4, "pointer_ram": 0x800F26D4, "count": 1, "area": 1, "save_byte14": slot, "script_function": 0x800E7880, "script_slot": slot, "event_flags": []} for slot in (1, 2, 3)]]
	definitions.extend([{"id": "controller10_flag5e1_set", "call_pc": 0x800EE9B8, "pointer_ram": 0x800F5284, "count": 1, "area": 0, "save_byte14": 0, "script_function": 0x800EE95C, "script_slot": 0, "parent_spawn_set": "flutter_hull_revisit_group", "direct_loader": 0x800EEBD0, "event_flags": [{"id": 0x5E1, "set": True}]}, {"id": "controller10_flag5c1_set", "call_pc": 0x800EEA40, "pointer_ram": 0x800F5298, "count": 1, "area": 0, "save_byte14": 0, "script_function": 0x800EE95C, "script_slot": 0, "parent_spawn_set": "flutter_hull_revisit_group", "direct_loader": 0x800EEBD0, "event_flags": [{"id": 0x5E1, "set": False}, {"id": 0x5C1, "set": True}]}, {"id": "controller10_flags_clear", "call_pc": 0x800EEA5C, "pointer_ram": 0x800F5284, "count": 1, "area": 0, "save_byte14": 0, "script_function": 0x800EE95C, "script_slot": 0, "parent_spawn_set": "flutter_hull_revisit_group", "direct_loader": 0x800EEBD0, "event_flags": [{"id": 0x5E1, "set": False}, {"id": 0x5C1, "set": False}]}])
	for definition in definitions:
		set_id = definition["id"]
		if set_id == "flutter_hull_revisit_group": definition["native_local_state_mutations"] = [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e769c", "script_slot": 0, "offset": 0, "amount": 1, "source_pc": "0x800E7718..0x800E7724"}]
		elif set_id.startswith("flutter_area0_script_"): definition["native_local_state_mutations"] = [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e7834", "script_slot": definition["script_slot"], "offset": 0, "amount": 1, "source_pc": "0x800E7860..0x800E786C"}]
		elif set_id == "flutter_area1_script0_props": definition["native_side_effects"] = []; definition["native_local_state_mutations"] = [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e7738", "script_slot": 0, "offset": 0, "amount": 1, "source_pc": "0x800E7810..0x800E781C"}]
		elif set_id.startswith("flutter_area1_script_"): definition["native_local_state_mutations"] = [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e7880", "script_slot": definition["script_slot"], "offset": 0, "amount": 1, "source_pc": "0x800E78AC..0x800E78B8"}]
	all_records = []; spawn_sets = []
	for definition in definitions:
		call_offset = 0x30 + definition["call_pc"] - 0x800E7000; instruction = read_u32(overlay, call_offset); delay = read_u32(overlay, call_offset + 4); target = ((definition["call_pc"] + 4) & 0xF0000000) | ((instruction & 0x03FFFFFF) << 2); delay_count = delay & 0xFFFF
		if instruction >> 26 != 3 or target != definition.get("direct_loader", 0x800C0818): raise ValueError(f"ST08 scripted registration at {definition['call_pc']:#x} does not match its native loader")
		if not definition.get("direct_loader") and (delay >> 26 != 9 or ((delay >> 16) & 31) != 5 or delay_count != definition["count"]): raise ValueError(f"ST08 scripted registration at {definition['call_pc']:#x} does not match its native C0818 count")
		first_offset = 0x30 + definition["pointer_ram"] - 0x800E7000; raw_records = []
		for ordinal in range(definition["count"]):
			offset = first_offset + ordinal * 20; raw = overlay[offset:offset + 20]
			if len(raw) != 20: raise ValueError(f"ST08 scripted actor array at {definition['pointer_ram']:#x} is truncated")
			raw_records.append((offset, raw)); all_records.append({"area": definition["area"], "record": ordinal, "pointer": definition["pointer_ram"], "offset": offset, "raw": raw})
		conditions = [{"kind": "native_event_flag", **flag} for flag in definition["event_flags"]] if definition.get("parent_spawn_set") else [{"kind": "stage_state_byte_equals", "ram": "0x8009C7FC", "value": definition["save_byte14"]}, {"kind": "stage_area_byte_equals", "ram": "0x8009C7F3", "value": definition["area"]}, {"kind": "stage_script_state_byte_equals", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": hex(definition["script_function"]), "script_slot": definition["script_slot"], "offset": 0, "value": 0}, *[{"kind": "native_event_flag", **flag} for flag in definition["event_flags"]]]; spawn_sets.append({"id": definition["id"], "area_index": definition["area"], "source": {"file": "ST08T.BIN", "call_pc": hex(definition["call_pc"]), "record_pointer_ram": hex(definition["pointer_ram"]), "record_count": definition["count"], "consumer": "ST08T0x800EEBD0->SLES0x8003E5B0->GAME0x800DA49C/DA4E8" if definition.get("direct_loader") else "GAME.BIN 0x800C0818 / 0x800C05E0", "native_stage_dispatch": dispatch, "native_side_effects": definition.get("native_side_effects", []), "native_local_state_mutations": definition.get("native_local_state_mutations", [])}, "predicate": {"all": conditions}, "record_offsets": [offset for offset, raw in raw_records], "non_mesh_records": [{"file_offset": offset, "source_bytes_hex": raw.hex(), "record_type": raw[2]} for offset, raw in raw_records if raw[2] not in (0x20, 0x60, 0x61)]})
		if definition.get("parent_spawn_set"):
			spawn_sets[-1]["parent_spawn_set"] = definition["parent_spawn_set"]; spawn_sets[-1]["source"]["controller"] = {"record_ram": "0x800F26C0", "record_id": 4, "area": 0, "class": 10, "callback": "0x800EE920", "constructor": "0x800EE95C", "pool_allocator": "SLES0x8003E9D8", "state_field": 8, "initial_state": 0}
	archive_info = world.actor_archive_for_records(stage, root, all_records, work, dat_dir, 0x8800)
	if not archive_info: raise ValueError("ST08 scripted actor records do not resolve to a unique native PBD archive")
	archive = archive_info["archive"]; payload = archive_info["payload"]; models_by_index = {}; instances = []; texture_vram = bytearray(1024 * 512 * 2); shared = dat_dir.parent / "COMMON/PL00T.BIN"
	if shared.is_file(): world.texture_uploads(shared.read_bytes(), texture_vram, "COMMON/PL00T.BIN")
	world.texture_uploads(overlay, texture_vram, "DAT/ST08T.BIN"); world.texture_uploads(root, texture_vram, "DAT/ST08.BIN"); texture_header = bytearray(48); struct.pack_into("<3I", texture_header, 0, 2, len(texture_vram), 1); struct.pack_into("<8H", texture_header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / "ST08_scripted_vram.bin"; write_output(texture_path, texture_header + texture_vram)
	for spawn_set in spawn_sets:
		for ordinal, offset in enumerate(spawn_set["record_offsets"]):
			raw = overlay[offset:offset + 20]
			if raw[2] not in (0x20, 0x60, 0x61): continue
			resource_flags = raw[2] | (raw[4] << 8) | (raw[6] << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
			if len(matches) != 1: raise ValueError(f"ST08 scripted actor at {offset:#x} has no unique PBD resource {resource_flags:#x}")
			model = matches[0]; index = model["index"]; model_file = f"actors/ST08_model_{index:02d}.glb"
			if index not in models_by_index:
				path = output_dir / model_file; path.parent.mkdir(parents=True, exist_ok=True); metadata = export_actor_model(payload, index, texture_path, path, archive_info["archive_file"]) if model["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, path, archive_info["archive_file"]); metadata["model_index"] = index; metadata["model_file"] = model_file; metadata["native_resource_flags"] = model["flags"]; metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30)); metadata["identity"] = "Flutter hull" if index == 1 else None; models_by_index[index] = metadata
			x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); hull = index == 1 and raw[4] == 0x30 and resource_flags == 0x3020; instance = {"stage": stage, "spawn_set": spawn_set["id"], "area_index": spawn_set["area_index"], "source_pc": spawn_set["source"]["call_pc"], "record_ordinal": ordinal, "file_offset": offset, "source_record_ram": hex(0x800E7000 + offset - 0x30), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "resource_variant": raw[6], "resource_key": raw[7], "control": raw[8], "frame": raw[9], "source_bytes_hex": raw.hex(), "model_index": index, "model_file": model_file, "identity": "Flutter hull" if hull else None, "role": "player_vehicle" if hull else None, "native_resource_flags": resource_flags, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0, "floor_height": y == -1}}
			startup_sources = {"0x800f2684": {"control": raw[8], "start_record": 0, "source_constructor": "0x800EA6B4", "source_update": "0x800EA4F4", "control_source": "actor+C copied from record byte8"}, "0x800f2698": {"control": 1, "start_record": 0, "source_constructor": "0x800E7B1C", "source_update": "0x800E78CC", "control_transition": "ST08T0x800E8F80", "setter": "SLES0x8003F4E8(actor,control,0)"}, "0x800f2908": {"control": 0, "start_record": 0, "source_constructor": "0x800E7B1C", "source_update": "0x800E78CC", "setter": "SLES0x8003F4E8(actor,control,0)"}, "0x800f5284": {"control": 1, "start_record": 0, "source_constructor": "0x800E9740", "source_update": "0x800E93EC", "setter": "SLES0x8003F4E8(actor,control,0)"}, "0x800f5298": {"control": 0, "start_record": 0, "source_constructor": "0x800EC344", "source_update": "0x800EBFFC", "control_source": "constructor sets control 1 and state 1 for one tick; 0x800EC460 substate 0 (0x800EC5B8) then sets control 0", "setter": "SLES0x8003F4E8(actor,control,0)"}}
			if instance["source_record_ram"] in startup_sources: instance["native_animation_startup"] = startup_sources[instance["source_record_ram"]]
			if instance["source_record_ram"] == "0x800f2698": instance["native_movement"] = {"kind": "route_graph", "source_initializer": "ST08T0x800E7388", "source_controller": ["ST08T0x800E7DD4", "ST08T0x800E7FB4", "ST08T0x800E810C", "ST08T0x800E8148"], "source_route_table": "ST08T0x800F1F40", "source_route_index": raw[8], "native_subtype": raw[6], "speed_raw": 64, "velocity_raw": -64, "turn_step_raw": 24, "arrival_tolerance_raw": 128, "animation_control": 1, "nodes_raw": [{"id": 0, "x": 1792, "z": -2304, "links": [1, 2, 3, -1]}, {"id": 1, "x": 1792, "z": -1536, "links": [0, 2, 3, -1]}, {"id": 2, "x": 2560, "z": -1536, "links": [0, 2, 3, -1]}, {"id": 3, "x": 2560, "z": -2304, "links": [0, 1, 2, -1]}], "collision_bounds_raw": list(struct.unpack_from("<6h", overlay, 0x30 + 0x800F291C - 0x800E7000)), "collision_bounds_source": "ST08T.BIN0x800F291C via actor+0x58", "rng": {"state_address": "SLES scratch 0x1F800000", "update": "((state<<1)+(state>>31)+1)^0x873CA9E5", "selector": "(state&0xFFFF)%valid_link_count", "avoid_previous_node": True, "seed_fallback": "runtime counter when native context lacks the scratch state", "sequence_exact": False}}
			hitbox_sources = {"0x800f2684": (0x800F3298, 0x800EA6B4), "0x800f2698": (0x800F291C, 0x800E7B1C), "0x800f2908": (0x800F291C, 0x800E7B1C), "0x800f5284": (0x800F2C44, 0x800E9740), "0x800f5298": (0x800F51D4, 0x800EC344)}
			if instance["source_record_ram"] in hitbox_sources:
				profile_pointer, profile_constructor = hitbox_sources[instance["source_record_ram"]]; instance["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 0x30 + profile_pointer - 0x800E7000)), "source_pointer_ram": hex(profile_pointer), "source_field": "actor+0x58", "source_constructor": hex(profile_constructor), "source_consumer": "GAME.BIN0x800B13B4->0x800B13FC and 0x800B3564->0x800B36E8", "anchor": "actor+0x10", "bounds_layout": "signed16 x/y/z min/max pairs in 1/256 stage units"}
			if raw[4] == 0x30: instance["native_broadphase"] = {"field": "actor+0x58", "source_ram": hex(hitbox_pointer), "bounds_raw": hitbox_bounds, "source_setter": "ST08T.BIN 0x800ED2A8..0x800ED2B8", "source_consumer": "GAME.BIN 0x800B13E0..0x800B13E8 -> 0x800B13FC", "purpose": "actor/map collision broadphase"}
			if instance["source_record_ram"] == "0x800f5284": instance["native_pose_resolver"] = {"source": "ST08T0x800EEABC reads native player12/1A before writing NPC12/1A/2A", "player_pose_key": "native_player_pose_raw", "cases": [{"player_xz": [0, 2560], "actor_xz": [0, 2432], "yaw_raw": 2048, "result": 1}, {"player_xz": [2080, 1536], "actor_xz": [2224, 1536], "yaw_raw": 1024, "result": 2}, {"player_xz": [-1408, 16], "actor_xz": [-1280, 16], "yaw_raw": 1024, "result": 3}, {"player_xz": [1536, -2736], "actor_xz": [1536, -2560], "yaw_raw": 0, "result": 4}], "default": {"actor_xz": [144, -112], "yaw_raw": 1744, "result": 5}}
			instances.append(instance)
	world.bind_scripted_interactions(stage, instances, overlay)
	if stage == "ST08":
		workshop = next(entry for entry in spawn_sets if entry["id"] == "flutter_area1_script0_props"); conditions = workshop["predicate"]["all"] + [{"kind": "native_event_flag", "id": 0x5C2, "set": True}, {"kind": "native_event_flag", "id": 0x5C3, "set": False}]; spawn_sets.append({"id": "workshop_scene_4f", "area_index": 1, "source": {"file": "ST08T.BIN", "call_pc": "0x800E780C", "native_side_effects": [{"kind": "set_event_flag", "id": 0x5C3}, {"kind": "set_event_flag", "id": 0x5E1}, {"kind": "call", "function": "GAME.BIN 0x800C0B0C", "argument": 0x4F}]}, "predicate": {"all": conditions}})
	manifest = {"stage": stage, "source": {"archive_file": archive_info["archive_file"], "archive_section": archive_info["offset"], "archive_sha256": sha256(root), "overlay_file": str(overlay_path.relative_to(ROOT)), "overlay_sha256": sha256(overlay), "record_size": 20, "record_consumer": "GAME.BIN 0x800C0818 calls 0x800C05E0", "local_context_reset": SCRIPT_LOCAL_CONTEXT_RESET, "native_broadphase": {"setter": "ST08T.BIN 0x800ED2A8..0x800ED2B8 stores pointer at actor+0x58", "consumer": "GAME.BIN 0x800B13E0..0x800B13E8 passes actor+0x58 to 0x800B13FC", "bounds_pointer": hex(hitbox_pointer), "bounds_raw": hitbox_bounds, "bounds_layout": "three signed16 min/max pairs used by the native actor/map collision path"}, "collision_adapter": {"geometry": "source PBD hull mesh triangles", "skin": "identity inverse binds, identity rest pose, control_00 constant pose"}, "resource_match": "PBD flags == record byte+2 | byte+4<<8 | byte+6<<16", "coordinate_unit": "1/256 map unit", "coordinate_basis": "canonical stage mesh (-X,-Y,+Z)"}, "spawn_sets": spawn_sets, "instances": instances, "models": [models_by_index[index] for index in sorted(models_by_index)], "identity_evidence": {"model_1": {"character": "Flutter hull", "role": "player_vehicle", "resource_flags": "0x3020", "mesh_bounds_source": "ST08 PBD model1, 3-bone high LOD", "native_transform_source": "ST08T.BIN record at 0xB6A0", "native_broadphase_pointer": hex(hitbox_pointer), "mesh_collision_source": "PBD model1 source triangles; rest/control_00 verified static"}}}
	bind_native_lock_on(overlay, instances); output_dir.mkdir(parents=True, exist_ok=True); write_output(output_dir / "scripted_actors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"ST08 scripted actors: {len(instances)} conditional records, {len(models_by_index)} original models -> {output_dir / 'scripted_actors.json'}"); return manifest

INTERIOR_SCRIPT_BINDINGS = {"ST0A": {"section": 0xA800, "table": 0x800EF500, "dispatcher": 0x800E74E8, "areas": 5, "constructor": 0x800E8B70, "callback": 0x800E8920, "hitbox": 0x800EFA80}, "ST0C": {"section": 0x6000, "table": 0x800EABCC, "dispatcher": 0x800E72B4, "areas": 3, "constructor": 0x800E777C, "callback": 0x800E752C, "hitbox": 0x800EAECC}, "ST47": {"section": 0x5800, "table": 0x800ECABC, "dispatcher": 0x800E7348, "areas": 3, "constructor": 0x800E8850, "callback": 0x800E8600, "hitbox": 0x800ED068}}
for stage, values in {"ST09": (0xE7410, 0xF2300, 1, 0x15000, 0xE81EC, 0xE843C, 0xF2744), "ST0B": (0xE75C8, 0xEEF88, 2, 0x18000, 0xE8174, 0xE83C4, 0xEF450), "ST0D": (0xE72E4, 0xF05B8, 2, 0xB000, 0xE74A4, 0xE76F4, 0xF0840), "ST17": (0xE7788, 0xFED78, 3, 0x9800, 0xE9D00, 0xE9F50, 0x106F3C), "ST18": (0xE760C, 0xFFA70, 6, None, 0xE84C4, 0xE8620, 0x1075D8), "ST1B": (0xE7494, 0xF009C, 5, 0x9800, 0xE78F0, 0xE7B40, 0xF0274), "ST1F": (0xE7B7C, 0x1010A0, 2, 0xA800, 0xE80D4, 0xE8324, 0x1012BC), "ST20": (0xE7508, 0xF1AE4, 2, 0xC800, 0xE8494, 0xE86E4, 0xF207C), "ST24": (0xE75F4, 0xF21F8, 3, 0xE800, 0xE7944, 0xE7BCC, 0xF2448), "ST25": (0xE7570, 0xF9CD4, 7, 0x10800, 0xE7FFC, 0xE824C, 0xF9F38), "ST29": (0xE7838, 0xF6B9C, 2, 0x9000, 0xE7CB4, 0xE7F04, 0xF709C), "ST2B": (0xE7504, 0xF3860, 4, 0x7800, 0xE7B6C, 0xE7C48, 0xF3D00), "ST3B": (0xE7644, 0xFDCBC, 2, 0x6800, 0xE8E24, 0xE9074, 0xFE518), "ST3C": (0xE83B0, 0xFE564, 5, None, 0xE8A2C, 0xE8C7C, 0xFEA68), "ST3D": (0xE73B0, 0xEAFE0, 4, 0x6800, 0xE77C0, 0xE7A10, 0xEB0AC), "ST3E": (0xE75B0, None, 2, 0xA800, 0xE799C, 0xE7BEC, 0xED608), "ST3F": (0xE7530, 0xEF800, 2, 0x6800, 0xE77FC, 0xE7A4C, 0xEF93C), "ST40": (0xE7C70, None, 14, 0xA000, 0xE84E4, 0xE8734, 0xFD558)}.items():
	dispatcher, table, areas, section, callback, constructor, hitbox = values; INTERIOR_SCRIPT_BINDINGS[stage] = {"dispatcher": 0x80000000 + dispatcher, "table": 0x80000000 + table if table is not None else None, "areas": areas, "section": section, "callback": 0x80000000 + callback, "constructor": 0x80000000 + constructor, "hitbox": 0x80000000 + hitbox}
INTERIOR_SCRIPT_BINDINGS["ST18"]["actor_archive_file"] = "ST1800.BIN"
INTERIOR_SCRIPT_BINDINGS["ST3C"]["actor_archive_file"] = "ST3C00.BIN"
INTERIOR_SCRIPT_BINDINGS["ST3E"]["areas"] = 7
INTERIOR_SCRIPT_BINDINGS["ST3F"]["states"] = 19
INTERIOR_SCRIPT_BINDINGS["ST1F"]["states"] = 19
INTERIOR_SCRIPT_BINDINGS["ST17"]["actor_archive_file"] = "ST1705.BIN"
INTERIOR_SCRIPT_BINDINGS["ST1F"]["actor_archive_file"] = "ST1F01.BIN"
INTERIOR_SCRIPT_BINDINGS.update({"ST14": {"dispatcher": 0x800E78FC, "table": 0x80106080, "areas": 5, "section": 0xE000}, "ST23": {"dispatcher": 0x800E75B0, "table": 0x800EB548, "areas": 1, "section": 0x6800}, "ST35": {"dispatcher": 0x800E74DC, "table": 0x800F9BAC, "areas": 6, "section": 0x8800, "actor_archive_file": "ST3501.BIN"}, "ST38": {"dispatcher": 0x800E73E0, "table": 0x800FF0C4, "areas": 13, "section": 0x12800}, "ST48": {"dispatcher": 0x800E7668, "table": 0x800F8F48, "areas": 2, "section": 0x10800}, "ST2F": {"dispatcher": 0x800E76D8, "table": None, "areas": 9, "section": 0xC000}, "ST4C": {"dispatcher": 0x800E751C, "table": None, "areas": 5, "section": 0xC000}, "ST4F": {"dispatcher": 0x800E742C, "table": None, "areas": 14, "section": 0xD000}, "ST50": {"dispatcher": 0x800E7488, "table": None, "areas": 11, "section": 0xB800}, "ST51": {"dispatcher": 0x800E72C8, "table": None, "areas": 3, "section": 0xA000}, "ST58": {"dispatcher": 0x800E73B0, "table": None, "areas": 5, "section": 0xB800}})
INTERIOR_SCRIPT_BINDINGS["ST1F"]["additional_texture_file"] = "ST1F01T.BIN"
INTERIOR_SCRIPT_BINDINGS["ST25"]["actor_archive_file"] = "ST2502.BIN"
INTERIOR_SCRIPT_BINDINGS["ST25"]["additional_texture_file"] = "ST2502T.BIN"
INTERIOR_SCRIPT_BINDINGS["ST3C"]["additional_texture_file"] = "ST3C01T.BIN"
INTERIOR_SCRIPT_BINDINGS["ST29"]["actor_archive_file"] = "ST2901.BIN"
INTERIOR_SCRIPT_BINDINGS["ST29"]["additional_texture_file"] = "ST2901T.BIN"
INTERIOR_SCRIPT_BINDINGS["ST29"]["pickup_table"] = 0x800F6628
INTERIOR_SCRIPT_BINDINGS["ST2B"]["pickup_table"] = 0x800F3294
INTERIOR_SCRIPT_BINDINGS["ST3B"]["pickup_table"] = 0x800FD3E8
INTERIOR_SCRIPT_BINDINGS["ST2C"] = {"dispatcher": 0x800E7358, "table": 0x800EA414, "areas": 1, "section": 0x1800, "callback": 0x800E7454, "constructor": 0x800E76A4, "hitbox": 0x800EA878}
INTERIOR_SCRIPT_BINDINGS["ST10"] = {"dispatcher": 0x800E76D0, "table": 0x800F7A28, "areas": 2, "section": 0xE800}
INTERIOR_SCRIPT_BINDINGS["ST07"] = {"dispatcher": 0x800E72F4, "table": None, "area_callbacks": 0x800E8B28, "registration_function": 0x800E7364, "areas": 3, "section": 0x6800, "constructor": 0x800E74E4, "callback": 0x800E7574, "hitbox": 0x800E8B34}  # stage frame table 0x800E8B28[area]; area 1 frame 0x800E72FC spawns record 0x800E8B10 through 0x800E7364 once when save byte14 is nonzero
INTERIOR_SCRIPT_BINDINGS["ST11"] = {"dispatcher": 0x800E7654, "table": 0x800F2D68, "areas": 1, "section": 0x8000}
INTERIOR_SCRIPT_BINDINGS["ST1D"] = {"dispatcher": 0x800E7728, "table": 0x800FC210, "areas": 3, "section": 0x16000, "states": 19}
SCRIPT_DOCK_RECORDS = {("ST10", 0x800F7A7C), ("ST10", 0x800F7BD0)}  # Flutter arrival craft and parked hull; tools/world.py exports them as docks
SCRIPT_FLOOR_SNAP = {("ST10", 0x60, 29): {"offset_raw": 0x90, "collision_variant": 1, "source": "ST10T0x800F2910 constructor stores GAME0x800B13B4 floor height + 0x90 into actor y; the resource variant 0 record first selects collision variant 1 of its tile through GAME0x800C010C(tile,1) at 0x800F2A94, so the floor query selects the variant box top"}}
SCRIPT_TRANSLUCENCY = {("ST10", 0x60, 29, 0): {"blend": 1, "source": "ST10T0x800F2A1C SLES0x8003F28C(actor,1,0) stores actor+0xBB=0x20; SLES0x80025AE8 ORs it shifted by 20 into the polygon command (SLES0x80025E88 bit25 semi-transparent) and the tpage mode bits, mode 0 averages with the frame"}}
def script_snap_floor(dat_dir, stage, instance, variant):
	import world
	path = Path(dat_dir) / (stage + ".BIN"); source = world.Stage(path.read_bytes()); area = instance["area_index"]; x, _, z, _ = instance["transform_raw"]; tiles, _ = source.area(area)
	placement = struct.unpack_from("<H", tiles[((x >> 9) + 0x40, (z >> 9) + 0x40)], 0)[0] & 0x7FF
	boxes = [box for box in world.export_floor_shapes(path, {placement: variant})[str(area)]["boxes"] if box["placement"] == placement and box["kind"] in (0, 2, 3) and box["x"][0] <= x < box["x"][1] and box["z"][0] <= z < box["z"][1]]
	if not boxes: raise ValueError(f"{stage} placement {placement} variant {variant} has no floor box at ({x}, {z})")
	return min(box["y"][0] for box in boxes)
SCRIPT_RESOURCE_OVERRIDES = {("ST07", 0x20, 0x6D, 0): {"variant": 0, "constructor": 0x800E74E4, "hitbox": 0x800E8B34, "control": 2, "target_flags60": 2}, ("ST3B", 0x20, 0, 1): {"variant": 45, "constructor": 0x800E8B60, "callback": 0x800E8A60, "hitbox": 0x800FE4F8, "control": 0}, ("ST3B", 0x60, 0x49, 0): {"variant": 0, "constructor": 0x800F4F34, "callback": 0x800F4E68, "hitbox": 0x800FECB4}, ("ST1B", 0x20, 0xA, 0): {"variant": 0, "constructor": 0x800E95A8, "hitbox": 0x800F059C, "control": 2, "target_flags60": 2}, ("ST20", 0x20, 0xA, 0): {"variant": 0, "constructor": 0x800EB528, "hitbox": 0x800F23D0, "control": 2, "target_flags60": 2}, ("ST18", 0x20, 0x5E, 1): {"variant": 0, "constructor": 0x800EDA9C, "callback": 0x800ED9B8, "hitbox": 0x801078B0, "control": 1, "target_flags60": 0, "header_flags_or": 0x40}}
def compact_callback_paths(paths):
	groups = {}
	for path in paths:
		key = json.dumps({name: path[name] for name in ("registrations", "actions", "local_bytes")}, sort_keys=True); group = groups.setdefault(key, {"sample": path, "cubes": set()}); group["cubes"].add(tuple(sorted(path["queries"].items())))
	result = []
	for group in groups.values():
		cubes = group["cubes"]
		while True:
			merged = set(); used = set(); buckets = {}
			for cube in cubes:
				for position, (flag, enabled) in enumerate(cube): buckets.setdefault((flag, cube[:position] + cube[position + 1:]), {})[enabled] = cube
			for (_, common), pair in buckets.items():
				if len(pair) == 2: merged.add(common); used.update(pair.values())
			if not used: break
			cubes = (cubes - used) | merged
		for cube in sorted(cubes): result.append({**group["sample"], "queries": dict(cube)})
	return result
def subtract_query_cube(cube, cover):
	if any(flag in cube and cube[flag] != enabled for flag, enabled in cover.items()): return [cube]
	remaining = dict(cube); pieces = []
	for flag, enabled in sorted(cover.items()):
		if flag in remaining: continue
		pieces.append({**remaining, flag: not enabled}); remaining[flag] = enabled
	return pieces
def disjoint_callback_paths(paths):
	result = []
	for path in sorted(compact_callback_paths(paths), key=lambda entry: len(entry["queries"])):
		pieces = [path["queries"]]
		for previous in result:
			pieces = [piece for cube in pieces for piece in subtract_query_cube(cube, previous["queries"])]
			if not pieces: break
		result.extend({**path, "queries": cube} for cube in pieces)
	return result
def audit_query_union(original, reduced):
	before = [dict(cube) for cube in set(tuple(sorted(path["queries"].items())) for path in original)]; after = [path["queries"] for path in reduced]
	for source, covers in ((before, after), (after, before)):
		for cube in source:
			pieces = [cube]
			for cover in covers:
				pieces = [piece for remaining in pieces for piece in subtract_query_cube(remaining, cover)]
				if not pieces: break
			if pieces: raise ValueError("Native registration predicate union changed during compaction")
def native_interior_callback_paths(overlay, callback, state, area, stage=""):
	if stage == "ST24" and callback == 0x800E76E4:
		paths = []
		for minimum, maximum in [(-32768, -1), (0, 4095), (4096, 8191), (8192, 12287), (12288, 16383), (16384, 32767)]:
			for path in _native_interior_callback_paths(overlay, callback, state, area, stage, minimum): paths.append({**path, "native_conditions": [{"kind": "native_save_word40_range", "minimum": minimum, "maximum": maximum, "source": "ST24T0x800E770C/0x800E7744..0x800E7780 signed16 saved+40"}]})
		return paths
	return _native_interior_callback_paths(overlay, callback, state, area, stage)
def _native_interior_callback_paths(overlay, callback, state, area, stage="", native_save_word40=0):
	import sys
	sys.path.insert(0, str(ROOT / "build/pydeps")); import unicorn; from unicorn import mips_const as registers
	executable = (ROOT / "build/disc-assets/SLES_035.56").read_bytes(); game = (ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes(); pending = [{}]; visited = set(); paths = []
	while pending:
		assignment = pending.pop(); identity = tuple(sorted(assignment.items()))
		if identity in visited: continue
		visited.add(identity); cpu = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); cpu.mem_map(0, 0x200000); cpu.mem_map(0x1F800000, 0x1000); cpu.mem_write(0x10000, executable[0x800:]); cpu.mem_write(0xAD000, game[48:]); cpu.mem_write(0xE7000, overlay[48:]); cpu.mem_write(0x9C7FC, bytes((state,))); queries = {}; registrations = []; actions = []; changed_flags = set()
		cpu.mem_write(0x9C7F9, bytes((area,)))
		cpu.mem_write(0x9C828, struct.pack("<h", native_save_word40))
		if stage: cpu.mem_write(0x9C7F8, bytes((int(stage[2:], 16),)))
		if stage in INTERIOR_SCRIPT_BINDINGS and INTERIOR_SCRIPT_BINDINGS[stage].get("pickup_table"): cpu.mem_write(0x78CE0, struct.pack("<I", INTERIOR_SCRIPT_BINDINGS[stage]["pickup_table"]))
		for event, enabled in assignment.items():
			if enabled: address = 0x98538 + (event >> 3); value = cpu.mem_read(address, 1)[0] | (1 << (event & 7)); cpu.mem_write(address, bytes((value,)))
		def observe(machine, address, size, user):
			argument = machine.reg_read(registers.UC_MIPS_REG_A0); caller = machine.reg_read(registers.UC_MIPS_REG_RA) - 8
			if stage == "ST3B" and address == 0x800E7D34:
				actions.append({"kind": "unported_engine_call", "function": "ST3BT.BIN 0x800E7D34", "argument": argument, "source_pc": hex(caller), "reason": "Native pickup placement traversal does not register NPC actors"}); machine.reg_write(registers.UC_MIPS_REG_V0, 0); machine.reg_write(registers.UC_MIPS_REG_PC, machine.reg_read(registers.UC_MIPS_REG_RA))
			elif stage == "ST3B" and address == 0x800C05B4 and caller == 0x800E7750:
				pair = struct.unpack("<2H", machine.mem_read(machine.reg_read(registers.UC_MIPS_REG_S0) & 0x1FFFFFFF, 4)); actions.append({"kind": "set_event_flag", "id": pair[0], "source_pc": "0x800e7764", "conditional_queries": {str(pair[1]): True}}); machine.reg_write(registers.UC_MIPS_REG_V0, 0); machine.reg_write(registers.UC_MIPS_REG_PC, machine.reg_read(registers.UC_MIPS_REG_RA))
			elif address == 0x800C05B4 and argument not in changed_flags: queries[argument] = bool(assignment.get(argument, False))
			elif address in (0x800C0558, 0x800C0584): actions.append({"kind": "set_event_flag" if address == 0x800C0558 else "clear_event_flag", "id": argument, "source_pc": hex(caller)}); changed_flags.add(argument)
			elif address == 0x800C0818 or stage in INTERIOR_SCRIPT_BINDINGS and address == INTERIOR_SCRIPT_BINDINGS[stage].get("registration_function"):
				registrations.append({"call_pc": caller, "pointer": argument, "count": machine.reg_read(registers.UC_MIPS_REG_A1) if address == 0x800C0818 else 1}); machine.reg_write(registers.UC_MIPS_REG_V0, 0); machine.reg_write(registers.UC_MIPS_REG_PC, machine.reg_read(registers.UC_MIPS_REG_RA))
			elif address == 0x800D9B50:
				actions.append({"kind": "unported_engine_call", "function": "GAME.BIN 0x800D9B50", "argument": argument, "source_pc": hex(caller), "reason": "Stage pickup allocation is outside NPC registration observation"}); machine.reg_write(registers.UC_MIPS_REG_V0, 0); machine.reg_write(registers.UC_MIPS_REG_PC, machine.reg_read(registers.UC_MIPS_REG_RA))
			elif address in (0x800C0B0C, 0x800C0B78, 0x800201B0):
				if address == 0x800201B0: actions.append({"kind": "native_audio_cue", "sound_id": argument, "source_pc": hex(caller), "source_function": "SLES0x800201B0"})
				else: actions.append({"kind": "call", "function": "GAME.BIN " + hex(address), "argument": argument, "source_pc": hex(caller)})
				machine.reg_write(registers.UC_MIPS_REG_V0, 0); machine.reg_write(registers.UC_MIPS_REG_PC, machine.reg_read(registers.UC_MIPS_REG_RA))
		cpu.hook_add(unicorn.UC_HOOK_CODE, observe); cpu.reg_write(registers.UC_MIPS_REG_SP, 0x801FF000); cpu.reg_write(registers.UC_MIPS_REG_GP, 0x8007890C); cpu.reg_write(registers.UC_MIPS_REG_RA, 0x80000800); cpu.reg_write(registers.UC_MIPS_REG_A0, 0x8009BE08)
		try: cpu.emu_start(callback, 0x80000800, count=100000)
		except unicorn.UcError as error: raise ValueError(f"{stage} callback{callback:#x} state{state} area{area} PC{cpu.reg_read(registers.UC_MIPS_REG_PC):#x} RA{cpu.reg_read(registers.UC_MIPS_REG_RA):#x}: {error}") from error
		if cpu.reg_read(registers.UC_MIPS_REG_PC) != 0x80000800: raise ValueError(f"Interior callback {callback:#x} did not return")
		for event, enabled in queries.items():
			if event not in assignment: alternate = dict(assignment); alternate[event] = not enabled; pending.append(alternate)
		path = {"queries": queries, "registrations": registrations, "actions": actions, "local_bytes": list(cpu.mem_read(0x9BE08, 4))}
		if path not in paths: paths.append(path)
	return compact_callback_paths(paths)
def export_stage_native_scenes(stage, overlay, payload, archive, texture_path, output_dir, models):
	if stage != "ST0A": return []
	import world
	def read(address, size): return overlay[48 + address - 0x800E7000:48 + address - 0x800E7000 + size]
	commands = []; address = 0x800EF88C; pointers = []; timeline = []
	while address < 0x800EF9E4:
		header = read_u32(read(address, 4), 0); opcode = header >> 24; size = 16 if 0x10 <= opcode <= 0x1A else 8 if opcode in (0x1B, 0x40, 0x41) else 20 if opcode == 0x42 else 4; words = list(struct.unpack("<" + "I" * (size // 4), read(address, size))); command = {"source_ram": hex(address), "opcode": opcode, "words": words}
		if opcode in (0x40, 0x41): command["actor_record_ram"] = hex(words[1]); pointers.append(words[1])
		commands.append(command); address += size
	commands.append({"source_ram": hex(address), "opcode": read_u32(read(address, 4), 0) >> 24, "words": [read_u32(read(address, 4), 0)]})
	address = 0x800EF9E4
	while True:
		phase, step, duration, callback = struct.unpack("<BBhI", read(address, 8))
		if phase == 255: break
		timeline.append({"phase": phase, "step": step, "duration": duration, "callback": hex(callback), "source_ram": hex(address)}); address += 8
	actors = []
	for pointer in dict.fromkeys([*pointers, 0x800EF878]):
		raw = read(pointer, 20); resource_flags = raw[2] | raw[4] << 8 | raw[6] << 16; matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
		if len(matches) != 1: raise ValueError(f"{stage} scene4D actor{pointer:#x} has no unique native resource{resource_flags:#x}")
		index = matches[0]["index"]; model_file = f"actors/{stage}_model_{index:02d}.glb"
		if index not in models:
			metadata = export_actor_model(payload, index, texture_path, output_dir / model_file, stage + ".BIN") if matches[0]["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, output_dir / model_file, stage + ".BIN"); metadata.update(model_file=model_file, native_resource_flags=resource_flags, native_scale_raw=list(struct.unpack_from("<3h", payload, matches[0]["mesh_offset"] + 0x30))); models[index] = metadata
		x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); entry = {"stage": stage, "area_index": 0, "source_record_ram": hex(pointer), "file_offset": 48 + pointer - 0x800E7000, "source_bytes_hex": raw.hex(), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "dispatch_index": raw[5], "resource_variant": raw[6], "resource_key": raw[7], "native_private_raw": list(raw[8:12]), "model_index": index, "model_file": model_file, "native_resource_flags": resource_flags, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256, -y / 256, z / 256], "yaw_raw": yaw, "yaw_turns": -yaw / 4096, "floor_height": y == -1}}
		if pointer in (0x800EF864, 0x800EF878):
			constructor = 0x800EAE4C if pointer == 0x800EF864 else 0x800E8B70; bounds = 0x800EFDB4 if pointer == 0x800EF864 else 0x800EFA80; entry["native_animation_startup"] = {"control": 0, "start_record": 0, "source_constructor": hex(constructor)}; entry["native_hitbox"] = {"bounds_raw": list(struct.unpack("<6h", read(bounds, 12))), "source_pointer_ram": hex(bounds), "source_field": "actor+0x58"}
		if pointer == 0x800EF878: world.bind_scripted_interactions(stage, [entry], overlay)
		actors.append({"source_ram": hex(pointer), "slot": raw[1], "model_file": model_file, "model_index": index, "entry": entry, "model": models[index]})
	profile = {"scene_id": 0x4D, "stage": stage, "area": 0, "native_tick_hz": 25, "source": {"request": "GAME0x800C0B0C", "dispatch_table": "GAME0x800DC490", "handler": "ST0A0x800E7A1C", "state_table": "ST0A0x800EFA74", "initialize": "ST0A0x800E7A58", "update": "ST0A0x800E7B60", "finish": "ST0A0x800E7C9C", "commands": "0x800EF88C", "timeline": "0x800EF9E4"}, "callback_contract_file": "scene_4d_callbacks.json", "commands": commands, "timeline": timeline, "actors": actors, "completion": {"registration_record_ram": "0x800ef878", "registration_call": "GAME0x800C1010", "source_pc": "ST0A0x800E7D5C", "clear_actor_mask": 0x496, "clear_actor_flags": 0x80, "restore_calls": ["GAME0x800CDE4C", "GAME0x800C11F0", "GAME0x800C0F58"], "player_yaw_raw": 0xC00}, "player_initial_pose": {"position_raw": [240, -16, -144], "yaw_raw": 0x400, "source": "ST0A0x800E7AB8..0x800E7AD4"}}
	write_output(output_dir / "scene_4d.json", json.dumps(profile, indent=2) + "\n", encoding="utf-8"); cinematics.scenes_export_callbacks(stage, 0x4D, output_dir); return [{"id": 0x4D, "file": "scene_4d.json"}]
def compact_registration_manifest(manifest):
	sets = {item["id"]: item for item in manifest["spawn_sets"]}; actor_groups = {}; action_groups = {}; rebuilt_sets = []; rebuilt_actors = []; original_count = len(manifest["instances"])
	for actor in manifest["instances"]:
		owner = sets[actor["spawn_set"]]; fixed = [item for item in owner["predicate"]["all"] if item["kind"] != "native_event_flag"]; flags = {item["id"]: item["set"] for item in owner["predicate"]["all"] if item["kind"] == "native_event_flag"}; entry = {key: value for key, value in actor.items() if key not in ("spawn_set", "source_pc")}; key = json.dumps([fixed, entry], sort_keys=True); group = actor_groups.setdefault(key, {"fixed": fixed, "entry": entry, "source": owner["source"], "paths": []}); group["paths"].append({"queries": flags, "registrations": [], "actions": [], "local_bytes": []})
	for owner in manifest["spawn_sets"]:
		fixed = [item for item in owner["predicate"]["all"] if item["kind"] != "native_event_flag"]; flags = {item["id"]: item["set"] for item in owner["predicate"]["all"] if item["kind"] == "native_event_flag"}
		for name in ("native_side_effects", "native_local_state_mutations"):
			for ordinal, action in enumerate(owner["source"].get(name, [])):
				conditional = {int(flag): enabled for flag, enabled in action.get("conditional_queries", {}).items()}
				if any(flag in flags and flags[flag] != enabled for flag, enabled in conditional.items()): continue
				queries = {**flags, **conditional}; action = {key: value for key, value in action.items() if key != "conditional_queries"}; key = json.dumps([fixed, name, action], sort_keys=True); group = action_groups.setdefault(key, {"fixed": fixed, "action": action, "name": name, "source": owner["source"], "paths": []}); group["paths"].append({"queries": queries, "registrations": [], "actions": [], "local_bytes": []})
	for group in actor_groups.values():
		paths = compact_callback_paths(group["paths"]); audit_query_union(group["paths"], paths)
		for path in paths:
			identifier = "native_actor_" + str(len(rebuilt_sets)); conditions = group["fixed"] + [{"kind": "native_event_flag", "id": flag, "set": enabled} for flag, enabled in path["queries"].items()]; source = {**group["source"], "native_side_effects": [], "native_local_state_mutations": []}; rebuilt_sets.append({"id": identifier, "area_index": group["entry"]["area_index"], "predicate": {"all": conditions}, "source": source, "record_offsets": [group["entry"]["file_offset"]], "non_mesh_records": []}); rebuilt_actors.append({**group["entry"], "spawn_set": identifier, "source_pc": source["call_pc"]})
	for group in sorted(action_groups.values(), key=lambda entry: entry["name"] == "native_local_state_mutations"):
		paths = disjoint_callback_paths(group["paths"]); audit_query_union(group["paths"], paths)
		for path in paths:
			identifier = "native_action_" + str(len(rebuilt_sets)); conditions = group["fixed"] + [{"kind": "native_event_flag", "id": flag, "set": enabled} for flag, enabled in path["queries"].items()]; source = {**group["source"], "native_side_effects": [], "native_local_state_mutations": []}; source[group["name"]] = [group["action"]]; area = next(item["value"] for item in group["fixed"] if item["kind"] == "stage_area_byte_equals"); rebuilt_sets.append({"id": identifier, "area_index": area, "predicate": {"all": conditions}, "source": source, "record_offsets": [], "non_mesh_records": []})
	manifest["source"]["registration_compaction"] = {"original_conditional_instances": original_count, "conditional_instances": len(rebuilt_actors), "actor_predicate_groups": len(actor_groups), "action_predicate_groups": len(action_groups), "exact_boolean_union_audited": True, "action_terms_disjoint": True}; manifest["spawn_sets"] = rebuilt_sets; manifest["instances"] = rebuilt_actors; return manifest
ICEFIELD_ENEMIES = {23: {"hitbox": 0x800F3030, "callback": 0x800E79E8, "constructor": 0x800E7B48}, 41: {"hitbox": 0x800F30DC, "callback": 0x800E9740, "constructor": 0x800E981C}, 59: {"hitbox": 0x800F30E8, "callback": 0x800EB5A4, "constructor": 0x800EB6DC}}
def native_lock_on_profile(overlay, entry):
	callback = int(entry.get("native_interaction", {}).get("actor_callback", entry.get("behavior_dispatch", {}).get("class_callback", "0")), 16)
	if not 0x800E7000 <= callback < 0x800E7000 + len(overlay) - 48: return None
	registers = [None] * 32; registers[0] = 0; registers[4] = 0x80090000; registers[29] = 0x801FF000; memory = {0x80090002: 0, 0x80090004: int(entry.get("actor_class", 0)), 0x80090006: int(entry.get("resource_variant", 0)), 0x80090012: 0, 0x80090016: 0, 0x8009001A: 0}; bone_point = False; calls = []; pending = None
	for pc in range(callback, min(callback + 0x3000, 0x800E7000 + len(overlay) - 48), 4):
		word = read_u32(overlay, pc - 0x800E7000 + 48); opcode, rs, rt, rd, shift, func = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31, word >> 6 & 31, word & 63; immediate = word & 65535; signed = immediate - 65536 if immediate & 32768 else immediate; left, right = registers[rs], registers[rt]
		if opcode == 15: registers[rt] = immediate << 16
		elif opcode in (8, 9): registers[rt] = None if left is None else (left + signed) & 0xFFFFFFFF
		elif opcode == 12: registers[rt] = None if left is None else left & immediate
		elif opcode == 13: registers[rt] = None if left is None else left | immediate
		elif opcode == 0 and func in (0, 2, 3): registers[rd] = None if right is None else ((right << shift) & 0xFFFFFFFF if func == 0 else right >> shift if func == 2 else ((right - 0x100000000 if right & 0x80000000 else right) >> shift) & 0xFFFFFFFF)
		elif opcode == 0 and func in (32, 33, 34, 35, 37): registers[rd] = None if left is None or right is None else ((left + right) & 0xFFFFFFFF if func in (32, 33) else (left - right) & 0xFFFFFFFF if func in (34, 35) else left | right)
		elif opcode == 0 and func not in (8, 9, 12, 13, 17, 19, 24, 25, 26, 27): registers[rd] = None
		elif opcode in (10, 11, 14): registers[rt] = None
		elif opcode in (32, 33, 35, 36, 37):
			address = None if left is None else (left + signed) & 0xFFFFFFFF; value = memory.get(address)
			if value is None and address is not None and 0x800E7000 <= address < 0x800E7000 + len(overlay) - 48:
				fmt = {32: "b", 33: "h", 35: "I", 36: "B", 37: "H"}[opcode]; value = struct.unpack_from("<" + fmt, overlay, address - 0x800E7000 + 48)[0]
			registers[rt] = None if value is None else value & 0xFFFFFFFF
		elif opcode in (40, 41, 43) and left is not None: memory[(left + signed) & 0xFFFFFFFF] = right
		registers[0] = 0
		if pending is not None:
			if pending == 0x80042704 and registers[6] is not None and registers[4] is not None:
				flags = registers[6] & 0xE80000; point = registers[4]; bone_point = point == 0x8009C9C0; offset = [memory.get(point + i) for i in (0, 2, 4)]; offset = [((value & 65535) - 65536 if value & 32768 else value & 65535) for value in offset] if all(value is not None for value in offset) else None
				if not flags & 0x80000 and flags & 0xE00000 in (0x400000, 0x800000, 0xA00000) and (offset is not None or bone_point): calls.append({"mask": flags, "source_call": hex(pc - 4), **({"point_bone": 0, "point_source": "SLES0x8003EEC4(actor,0) returns first cached world hit volume from0x8009C9C0"} if bone_point else {"point_offset_raw": offset})})
			returned = 0x8009C9C0 if pending == 0x8003EEC4 and registers[5] == 0 else 0 if pending == 0x800B13B4 else None
			for register in [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25]: registers[register] = None
			registers[2] = returned
			pending = None
		if opcode == 3: pending = 0x80000000 | (word & 0x3FFFFFF) << 2
		if word == 0x03E00008: break
	if not calls or len({json.dumps({key: value for key, value in call.items() if key != "source_call"}, sort_keys=True) for call in calls}) != 1: return None
	return {**calls[0], "callback": hex(callback), "source": "SLES0x80042704 stores registrationmask; 0x80043570 indexes eligibilitybytes0x8006B47C[(mask&0xE00000)>>21]&0x40 and skips primary targets withmask0x80000"}
def bind_native_lock_on(overlay, instances):
	for instance in instances:
		profile = native_lock_on_profile(overlay, instance)
		if profile is not None: instance["native_lock_on"] = profile
		else: instance.pop("native_lock_on", None)
def bind_icefield_enemies(instances, overlay, output_dir):
	game = (ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes(); export_pickup_data(game, Path(output_dir))
	for instance in instances:
		source = ICEFIELD_ENEMIES.get(instance["actor_class"])
		if source is None: continue
		combat = source_combat_attributes(game, instance["actor_class"], instance["resource_key"]); instance["source_attributes"] = combat["normal"]["attributes"]; instance["combat"] = combat; instance["native_enemy"] = {"callback": hex(source["callback"]), "constructor": hex(source["constructor"])}
		instance["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 0x30 + source["hitbox"] - 0x800E7000)), "source_pointer_ram": hex(source["hitbox"]), "source_field": "actor+0x58", "source_constructor": hex(source["constructor"])}
		if instance["actor_class"] == 23: instance["native_enemy"]["lift"] = {"gate": "ST11T0x800E7CE4 -> GAME0x800CFABC, actor capability2", "dispatch": "ST11T0x800E82E4/0x800E8320", "hold_ticks": 120, "struggle_ticks": 20, "controls": {"held": 9, "struggle": 10}, "throw": {"source": "ST11T0x800E83D0 -> SLES0x800421E0", "raw": [0, -256, -1024], "gravity_raw": 64}, "escape": {"source": "ST11T0x800E84FC", "vertical_raw": -128, "forward_raw": 128, "gravity_raw": 64}, "disabled_flags": "0x42"}
def bind_icefield_encounter(dat_dir, overlay, payload, archive, texture_path, output_dir, models, archive_source, instances):
	import world
	T = Image(overlay, 0x800E7000, 0x30, "ST11T"); output_dir = Path(output_dir)
	world.check_overlay_words(overlay, {0x800E7794: 0x28420500, 0x800E77A0: 0x0C0302C3, 0x800E77A4: 0x2404002A, 0x800E77AC: 0x24040591, 0x800E78B4: 0x24040592, 0x800E78B8: 0x2404000F, 0x800E78BC: 0x24050333, 0x800E78D0: 0x24842DF8, 0x800E78D4: 0xA0500008, 0x800E78DC: 0x24050006, 0x800E78E4: 0x0C030206, 0x800E7878: 0x24040001, 0x800E787C: 0x24050002, 0x800F1244: 0x0C030206, 0x800F1248: 0x24050003, 0x800F1274: 0x3C020900, 0x800F127C: 0x3C02FD60, 0x800F1284: 0x3C021600, 0x800F128C: 0x24020800, 0x800F14DC: 0x2404001E, 0x800EF5C8: 0x24040004, 0x800EFCDC: 0x0C030043, 0x800EFCE0: 0x24050001, 0x800F0214: 0x0C030043, 0x800F0218: 0x00002821, 0x800E76FC: 0x24100002}, "ST11 encounter")
	def read(address): return overlay[48 + address - 0x800E7000:48 + address - 0x800E7000 + 20]
	def pose(raw): x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); return {"transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0, "floor_height": y == -1}}
	boss_address = 0x800F3278; raw = read(boss_address)
	if raw[2] != 0x20 or raw[4] != 59: raise ValueError("ST11 encounter boss record differs")
	resource_flags = raw[2] | raw[4] << 8 | raw[6] << 16; matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
	if len(matches) != 1: raise ValueError(f"ST11 boss has no unique native resource {resource_flags:#x}")
	index = matches[0]["index"]; model_file = f"actors/ST11_model_{index:02d}.glb"
	if index not in models:
		metadata = export_actor_model(payload, index, texture_path, output_dir / model_file, archive_source) if matches[0]["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, output_dir / model_file, archive_source); metadata.update(model_file=model_file, native_resource_flags=resource_flags, native_scale_raw=list(struct.unpack_from("<3h", payload, matches[0]["mesh_offset"] + 0x30))); models[index] = metadata
	entry = {"stage": "ST11", "area_index": 0, "source_record_ram": hex(boss_address), "file_offset": 48 + boss_address - 0x800E7000, "source_bytes_hex": raw.hex(), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "resource_variant": raw[6], "resource_key": raw[7], "control": raw[8], "native_private_raw": list(raw[8:12]), "model_index": index, "model_file": model_file, "native_resource_flags": resource_flags, **pose(raw)}
	bind_icefield_enemies([entry], overlay, output_dir); scene_address = 0x800F3264; raw = read(scene_address)
	if raw[2] != 0x20 or raw[4] != 59 or raw[5] != 1: raise ValueError("ST11 scene boss record differs")
	scene_entry = json.loads(json.dumps(entry)); scene_entry.update(source_record_ram=hex(scene_address), file_offset=48 + scene_address - 0x800E7000, source_bytes_hex=raw.hex(), record_id=raw[1], dispatch_index=raw[5], native_private_raw=list(raw[8:12]), **pose(raw)); scene_entry["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 48 + 0x800F3130 - 0x800E7000)), "source_pointer_ram": "0x800f3130", "source_field": "actor+0x58", "source_constructor": "0x800ecd18"}; scene_entry["native_enemy"] = {"callback": "0x800ECBE4", "constructor": "0x800ECD18"}
	stage = world.Stage((Path(dat_dir) / "ST11.BIN").read_bytes()); path = Path(dat_dir) / "ST11.BIN"; grid = stage.area(0)[0]; base = world.export_floor_shapes(path)["0"]["boxes"]; barriers = []
	for address in (0x800F328C, 0x800F32A0):
		raw = read(address)
		if raw[2] != 0x60 or raw[4] != 0x28: raise ValueError("ST11 encounter barrier record differs")
		x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); tile = [(x >> 9) + 0x40, (z >> 9) + 0x40]; flags = struct.unpack_from("<H", grid[tuple(tile)], 0)[0]
		if flags & 0xC000 != 0x8000: raise ValueError(f"ST11 barrier tile {tile} holds no placement")
		placement = flags & 0x7FF; alternate = [box for box in world.export_floor_shapes(path, {placement: 1})["0"]["boxes"] if box["placement"] == placement]; original = [box for box in base if box["placement"] == placement]
		barriers.append({"source_record_ram": hex(address), "source_bytes_hex": raw.hex(), "record_id": raw[1], "tile": tile, "placement": placement, "boxes": [box for box in alternate if box not in original], "source": "ST11T0x800EFC24: GAME0x800C010C(tile, 1) selects collision variant 1; removal at 0x800F019C selects variant 0", **pose(raw)})
	if any(not barrier["boxes"] for barrier in barriers): raise ValueError("ST11 barrier variant adds no collision")
	if (T.imm(0x800E77C4), T.imm(0x800E77CC), T.imm(0x800E7848)) != (0x2F10, 0x2E70, 4): raise ValueError("ST11 roaming burrower registration differs")
	spitters = []
	for ordinal in range(T.imm(0x800E78DC)):
		address = hex(0x800F2DF8 + ordinal * 20); matches = [item for item in instances if item["source_record_ram"] == address]
		if not matches: raise ValueError(f"ST11 spitter record {address} has no exported instance")
		spitters.append(json.loads(json.dumps(matches[0])))
	thresholds = list(struct.unpack_from("<4h", overlay, 48 + 0x800F2F10 - 0x800E7000)); burrowers = []
	for ordinal, threshold in enumerate(thresholds):
		address = hex(0x800F2E70 + ordinal * 20); matches = [item for item in instances if item["source_record_ram"] == address]
		if not matches: raise ValueError(f"ST11 burrower record {address} has no exported instance")
		burrowers.append({"entry": json.loads(json.dumps(matches[0])), "player_z_raw_exclusive_minimum": threshold})
	return {"source": "ST11T0x800E76C4 (story byte14 1) -> GAME0x800C0B0C scene 0x2A (handler 0x800F0FAC, timeline 0x800F33D4)", "story_byte14": 1, "area": 0, "trigger": {"player_z_raw_minimum": T.imm(0x800E7794), "scene": T.imm(0x800E77A4), "flag": T.imm(0x800E77AC), "source": "ST11T0x800E778C..0x800E77B0: player+0x1A < 0x500 keeps the roaming enemies, otherwise starts the scene and sets flag 0x591"}, "arrival": {"position_raw": [T.word(0x800F1274) & 0xFFFF, T.half(0x800F127C), T.word(0x800F1284) & 0xFFFF], "yaw_raw": T.imm(0x800F128C), "source": "ST11T0x800F1214..0x800F1298: scene finish registers the boss and barrier records, then places the player"}, "music_cue": T.imm(0x800F14DC), "radio": {"message": T.imm(0x800E7878), "story_byte14_minimum": T.imm(0x800E787C), "window": T.imm(0x800EF5C8), "bank": "0x8010C000", "source": "ST11T0x800E785C..0x800E7890 registers class 0x1B (0x800EEF04, kind 0 -> 0x800EF5BC) once the scene flag clears"}, "boss": {"entry": entry, "scene_entry": scene_entry, "model_index": index, "source": "ST11T class 59 callback 0x800EB5A4, constructor 0x800EB6DC, state table 0x800F30F4/0x800F3100/0x800F3124"}, "barriers": barriers, "burrowers": burrowers, "defeat": {"spawn": spitters, "flag": T.imm(0x800E78B4), "fade": {"mask": T.imm(0x800E78B8), "speed": T.imm(0x800E78BC), "delay": 0}, "barrier_state": T.imm(0x800E76FC), "register_record": "0x800f2df8", "register_count": T.imm(0x800E78DC), "source": "ST11T0x800E7894..0x800E78F0"}}
def export_interior_scripted_actors(dat_dir, output_dir, stage):
	from disc import decompress_section
	import world
	binding = INTERIOR_SCRIPT_BINDINGS[stage]; dat_dir = Path(dat_dir).resolve(); output_dir = Path(output_dir); root_path = dat_dir / (stage + ".BIN"); overlay_path = dat_dir / (stage + "T.BIN"); root = root_path.read_bytes(); overlay = overlay_path.read_bytes(); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); archive_source = binding.get("actor_archive_file", root_path.name)
	if binding.get("actor_archive_file") and read_u32((dat_dir / archive_source).read_bytes(), 0) == 10: archive_path = dat_dir / archive_source; archive, payload = actor_archive(archive_path); section = None; archive_digest = sha256(archive_path.read_bytes())
	else:
		actor_source = (dat_dir / archive_source).read_bytes(); payload, section = decompress_section(actor_source, binding["section"]); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(payload), section["section_count"]); archive_path = work / (stage + "_models.bin"); write_output(archive_path, header + payload); archive, payload = actor_archive(archive_path); archive_digest = sha256(actor_source)
	dispatch_rows = []; spawn_sets = []; paths_by_callback = {}; instances = []; models = {}; unported_paths = []; controller_models = {}; base_controller_archive = None
	vram = bytearray(1024 * 512 * 2); uploads = []; uploads.extend(world.texture_uploads((dat_dir.parent / "COMMON/PL00T.BIN").read_bytes(), vram, "COMMON/PL00T.BIN")); uploads.extend(world.texture_uploads(overlay, vram, "DAT/" + overlay_path.name)); uploads.extend(world.texture_uploads(root, vram, "DAT/" + root_path.name))
	if binding.get("actor_archive_file"): uploads.extend(world.texture_uploads((dat_dir / archive_source).read_bytes(), vram, "DAT/" + archive_source))
	if binding.get("additional_texture_file"): uploads.extend(world.texture_uploads((dat_dir / binding["additional_texture_file"]).read_bytes(), vram, "DAT/" + binding["additional_texture_file"]))
	texture_header = bytearray(48); struct.pack_into("<3I", texture_header, 0, 2, len(vram), 1); struct.pack_into("<8H", texture_header, 12, 0, 0, 0, 0, 0, 0, 1024, 512); texture_path = work / (stage + "_scripted_vram.bin"); write_output(texture_path, texture_header + vram)
	for state in range(binding.get("states", 21)):
		row = binding["area_callbacks"] if binding.get("area_callbacks") else read_u32(overlay, 48 + binding["table"] + state * 4 - 0x800E7000) if binding["table"] is not None else None; callbacks = list(struct.unpack_from("<" + "I" * binding["areas"], overlay, 48 + row - 0x800E7000)) if row is not None else [binding["dispatcher"]] * binding["areas"]; dispatch_rows.append({"native_save_byte14": state, "row_ram": hex(row) if row is not None else None, "area_callbacks": {str(area): hex(callback) for area, callback in enumerate(callbacks)}})
		for area, callback in enumerate(callbacks):
			callback_key = (callback, state, area)
			if callback_key not in paths_by_callback: paths_by_callback[callback_key] = native_interior_callback_paths(overlay, callback, state, area, stage)
			for path_index, path in enumerate(paths_by_callback[callback_key]):
				conditions = [{"kind": "stage_state_byte_equals", "value": state}, {"kind": "stage_area_byte_equals", "value": area}, {"kind": "stage_script_state_byte_equals", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": hex(callback), "script_slot": state, "offset": 0, "value": 0}, *path.get("native_conditions", []), *[{"kind": "native_event_flag", "id": event, "set": enabled} for event, enabled in path["queries"].items()]]; set_id = f"{stage.lower()}_state{state}_area{area}_path{path_index}"; offsets = []
				for registration in path["registrations"]:
					for ordinal in range(registration["count"]): offsets.append((48 + registration["pointer"] - 0x800E7000 + ordinal * 20, registration["call_pc"], ordinal))
				mutations = [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": hex(callback), "script_slot": state, "offset": offset, "amount": value} for offset, value in enumerate(path["local_bytes"]) if value]; source = {"file": overlay_path.name, "call_pc": hex(path["registrations"][0]["call_pc"]) if path["registrations"] else hex(callback), "callback": hex(callback), "consumer": "GAME0x800C0818/0x800C05E0", "native_side_effects": path["actions"], "native_local_state_mutations": mutations}; spawn_sets.append({"id": set_id, "area_index": area, "source": source, "predicate": {"all": conditions}, "record_offsets": [entry[0] for entry in offsets], "non_mesh_records": []})
				if not offsets and path["actions"]: unported_paths.append({"spawn_set": set_id, "predicate": {"all": conditions}, "source_actions": path["actions"], "source_local_bytes": path["local_bytes"], "reason": "Native engine scene request has no source NPC registration in this callback path"})
				for offset, caller, ordinal in offsets:
					raw = overlay[offset:offset + 20]
					if len(raw) != 20: raise ValueError("Interior registration record is truncated")
					if (stage, 0x800E7000 + offset - 48) in SCRIPT_DOCK_RECORDS: continue
					if raw[2] not in (0x20, 0x60, 0x61) or raw[2] == 0x60 and raw[4] == 2: spawn_sets[-1]["non_mesh_records"].append({"file_offset": offset, "source_bytes_hex": raw.hex(), "record_type": raw[2]}); continue
					kickable = world.kickable_profile(stage, raw); override = SCRIPT_RESOURCE_OVERRIDES.get((stage, raw[2], raw[4], raw[5]), {}); variant = override["variant"] if override else kickable["resource_variant"] if kickable else raw[6]; resource_flags = raw[2] | (raw[4] << 8) | (variant << 16); matches = [model for model in archive["models"] if model["flags"] & 0xFFFFFF == resource_flags]
					if len(matches) != 1:
						if raw[2] == 0x20 and raw[4] == 0 and raw[5] == 0: raise ValueError(f"{stage} NPC at{offset:#x} has no unique PBD resource{resource_flags:#x}")
						if stage == "ST29" and raw[2:7] == bytes((0x20, 2, 1, 0, 0)) or stage == "ST18" and raw[2:7] == bytes((0x60, 8, 0x2D, 0, 3)):
							controller_archive, controller_payload, controller_source = archive, payload, archive_source; controller_flags = raw[2] | raw[4] << 8
							if stage == "ST29":
								if base_controller_archive is None:
									base_payload, base_section = decompress_section(root, 0x9000); base_header = bytearray(48); struct.pack_into("<3I", base_header, 0, 10, len(base_payload), base_section["section_count"]); base_path = work / "ST29_base_models.bin"; write_output(base_path, base_header + base_payload); base_controller_archive = actor_archive(base_path)
								controller_archive, controller_payload = base_controller_archive; controller_source = root_path.name
							controller_match = [entry for entry in controller_archive["models"] if entry["flags"] & 0xFFFFFF == controller_flags]
							if len(controller_match) != 1: raise ValueError("Native combat controller has no unique source resource")
							controller_index = controller_match[0]["index"]; controller_key = (controller_source, controller_index)
							if controller_key not in controller_models:
								controller_file = f"controllers/{Path(controller_source).stem}_model_{controller_index:02d}.glb"; metadata = export_actor_model(controller_payload, controller_index, texture_path, output_dir / controller_file, controller_source) if controller_match[0]["mesh"]["bone_count"] else export_static_actor(controller_payload, controller_index, texture_path, output_dir / controller_file, controller_source); metadata.update(model_file=controller_file, native_resource_flags=controller_flags); controller_models[controller_key] = metadata
							unported_paths.append({"spawn_set": set_id, "file_offset": offset, "source_bytes_hex": raw.hex(), "actor_class": raw[4], "resource_flags": hex(controller_flags), "native_resource": {"model_file": controller_models[controller_key]["model_file"], "source_model_index": controller_index, "native_resource_flags": controller_flags}, "source_controller": "ST29T0x800E97D4 hit registration0x800E9950" if stage == "ST29" else "ST18T0x800F6388;descriptor80107DD4[3] supplies variant0;constructor0x800F6500;flags60=2", "reason": "Native combat controller is unported; original resource has been exported"}); continue
						unported_paths.append({"spawn_set": set_id, "file_offset": offset, "source_bytes_hex": raw.hex(), "actor_class": raw[4], "resource_flags": hex(resource_flags), "reason": "Native non-class0 resource constructor is not bound to this archive"}); continue
					model = matches[0]; index = model["index"]; model_file = f"actors/{stage}_model_{index:02d}.glb"
					if index not in models:
						metadata = export_actor_model(payload, index, texture_path, output_dir / model_file, archive_source, preserve_default_hidden=(stage, index) in (("ST0C", 2), ("ST0B", 2))) if model["mesh"]["bone_count"] else export_static_actor(payload, index, texture_path, output_dir / model_file, archive_source); metadata.update(model_file=model_file, native_resource_flags=resource_flags, native_scale_raw=list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30))); models[index] = metadata
					x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); instances.append({"stage": stage, "spawn_set": set_id, "area_index": area, "source_pc": hex(caller), "native_registration_call_pc": hex(caller), "record_ordinal": ordinal, "file_offset": offset, "source_record_ram": hex(0x800E7000 + offset - 48), "record_id": raw[1], "record_type": raw[2], "record_class": raw[3], "actor_class": raw[4], "resource_variant": raw[6], "resource_key": raw[7], "control": raw[8], "source_bytes_hex": raw.hex(), "native_private_raw": list(raw[8:12]), "model_index": index, "model_file": model_file, "native_resource_flags": resource_flags, "transform_raw": [x, y, z, yaw], "transform": {"position": [-x / 256.0, -y / 256.0, z / 256.0], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0, "floor_height": y == -1}})
					if kickable: instances[-1]["native_kickable"] = kickable
	if stage == "ST0A":
		spawn_sets.append({"id": "st0a_state0_area0_music_step1", "area_index": 0, "predicate": {"all": [{"kind": "stage_state_byte_equals", "value": 0}, {"kind": "stage_area_byte_equals", "value": 0}, {"kind": "stage_script_state_byte_equals", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e7578", "script_slot": 0, "offset": 0, "value": 1}]}, "source": {"file": "ST0AT.BIN", "callback": "0x800e7578", "call_pc": "0x800e75e8", "native_side_effects": [{"kind": "native_audio_cue", "sound_id": 0x16, "source_pc": "0x800e75e8", "source_function": "SLES0x800201B0"}], "native_local_state_mutations": [{"kind": "increment_stage_script_state_byte", "owner_ram": SCRIPT_LOCAL_CONTEXT_RESET["owner_ram"], "source_function": "0x800e7578", "script_slot": 0, "offset": 0, "amount": 1}]}, "record_offsets": [], "non_mesh_records": []})
	for instance in instances:
		if (stage, instance["record_type"], instance["actor_class"]) in SCRIPT_FLOOR_SNAP:
			snap = dict(SCRIPT_FLOOR_SNAP[(stage, instance["record_type"], instance["actor_class"])]); instance["native_floor_snap"] = snap
			if "collision_variant" in snap: snap["floor_raw"] = script_snap_floor(dat_dir, stage, instance, snap["collision_variant"])
		if (stage, instance["record_type"], instance["actor_class"], instance["resource_variant"]) in SCRIPT_TRANSLUCENCY: instance["native_translucency"] = SCRIPT_TRANSLUCENCY[(stage, instance["record_type"], instance["actor_class"], instance["resource_variant"])]
		override = SCRIPT_RESOURCE_OVERRIDES.get((stage, instance["record_type"], instance["actor_class"], bytes.fromhex(instance["source_bytes_hex"])[5]), {})
		if override:
			instance["native_model_selector"] = {"resource_variant": override["variant"], "source_constructor": hex(override["constructor"]), "resource_loader": "SLES0x8003DFC8 explicit constructor key" if override["variant"] else "SLES0x8003DFA4 zero variant key"}; instance["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 48 + override["hitbox"] - 0x800E7000)), "source_pointer_ram": hex(override["hitbox"]), "source_field": "actor+0x58", "source_constructor": hex(override["constructor"])}
			if "control" in override: instance["native_animation_startup"] = {"control": override["control"], "start_record": 0, "source_constructor": hex(override["constructor"])}
			if "target_flags60" in override: instance["native_constructor_target_flags60"] = override["target_flags60"]
			if "header_flags_or" in override: instance["native_constructor_header_flags_or"] = override["header_flags_or"]
		if instance["record_type"] != 0x20 or instance["actor_class"] != 0 or bytes.fromhex(instance["source_bytes_hex"])[5] != 0: continue
		instance["native_animation_startup"] = {"control": 0, "start_record": 0, "source_constructor": hex(binding["constructor"]), "source_update": hex(binding["callback"]), "source_fields": "constructor sets actor+A0=0/A1=FF; privateD80 selects native idle state1, not animation frame128"}; instance["native_hitbox"] = {"bounds_raw": list(struct.unpack_from("<6h", overlay, 48 + binding["hitbox"] - 0x800E7000)), "source_pointer_ram": hex(binding["hitbox"]), "source_field": "actor+0x58", "source_constructor": hex(binding["constructor"])}
	encounter = None
	if stage == "ST11": bind_icefield_enemies(instances, overlay, output_dir); encounter = bind_icefield_encounter(dat_dir, overlay, payload, archive, texture_path, output_dir, models, archive_source, instances)
	world.bind_scripted_interactions(stage, instances, overlay); bind_native_lock_on(overlay, instances); output_dir.mkdir(parents=True, exist_ok=True); scenes = export_stage_native_scenes(stage, overlay, payload, archive, texture_path, output_dir, models); manifest = {"stage": stage, "source": {"archive_file": str((dat_dir / archive_source).relative_to(ROOT)), "archive_section": binding["section"], "archive_sha256": archive_digest, "overlay_file": str(overlay_path.relative_to(ROOT)), "overlay_sha256": sha256(overlay), "local_context_reset": SCRIPT_LOCAL_CONTEXT_RESET, "record_size": 20, "resource_match": "PBD flags == record+2 | record+4<<8 | record+6<<16", "native_stage_dispatch": {"dispatcher": hex(binding["dispatcher"]), "table_ram": hex(binding["table"]) if binding["table"] is not None else None, "rows": dispatch_rows}, "registration_observation": "Original callback/event bitmap instructions executed; registration/scene/audio APIs observed without executing actor allocation or engine scene changes"}, "spawn_sets": spawn_sets, "instances": instances, "models": list(models.values()), "native_scenes": scenes, "unported_native_script_paths": unported_paths}; manifest["source"]["texture_uploads"] = uploads; manifest["unported_controller_models"] = list(controller_models.values()); manifest = compact_registration_manifest(manifest)
	if encounter is not None: manifest["native_encounter"] = encounter
	if encounter is not None:
		staged = {item["spawn_set"] for item in manifest["instances"] if item["actor_class"] == 41}
		for spawn_set in manifest["spawn_sets"]:
			if spawn_set["id"] in staged: spawn_set["predicate"]["all"].append({"kind": "native_encounter_staged"})
	write_output(output_dir / "scripted_actors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"{stage} scripted actors: {len(manifest['instances'])} conditional instances, {len(models)} original models, {len(manifest['spawn_sets'])} source paths"); return manifest
def add_st09_follower(manifest, dat_dir):
	import copy, world
	for entry in manifest["instances"]:
		if entry.get("source_record_ram") == "0x800f2d00": world.bind_scripted_interactions("ST09", [entry], (Path(dat_dir) / "ST09T.BIN").read_bytes()); return manifest
	overlay = (Path(dat_dir) / "ST09T.BIN").read_bytes(); base = struct.unpack_from("<I", overlay, 12)[0]; offset = 48 + 0x800F2D00 - base; raw = overlay[offset:offset + 20]; template = next(entry for entry in manifest["instances"] if entry.get("source_record_ram") == "0x800f2390"); entry = copy.deepcopy(template); pose = list(struct.unpack_from("<4h", raw, 12)); key = "native_roll_follower"
	entry.update(spawn_set=key, source_record_ram="0x800f2d00", file_offset=offset, source_bytes_hex=raw.hex(), source_pc="0x800ef5c4", record_id=0, record_ordinal=0, native_private_raw=list(raw[8:12]), transform_raw=pose, transform={"position": [-pose[0] / 256.0, -pose[1] / 256.0, pose[2] / 256.0], "yaw_raw": pose[3], "yaw_turns": -pose[3] / 4096.0, "floor_height": True}, native_animation_startup={"control": 1, "start_record": 0, "source_constructor": "0x800EA1B0", "source_update": "0x800E9D0C"}); entry.pop("native_interaction", None); world.bind_scripted_interactions("ST09", [entry], overlay)
	cases = [([0,-7680],[0,-7808],2048), ([-960,-6400],[-848,-6400],1024), ([-960,-4864],[-848,-4864],1024), ([-3840,-5568],[-3840,-5456],0), ([848,-5888],[736,-5888],3072), ([-2896,-768],[-2896,-880],2048), ([2432,256],[2352,256],3072), ([2560,-3328],[2464,-3328],3072), ([0,1792],[0,1696],2048)]
	entry["native_pose_resolver"] = {"source": "ST09T800EF610", "player_pose_key": "native_player_pose_raw", "cases": [{"player_xz": player, "actor_xz": actor, "yaw_raw": yaw, "result": index + 1} for index, (player, actor, yaw) in enumerate(cases)], "default": {"actor_xz": [0, -7936], "yaw_raw": 0, "result": 0}}
	manifest["spawn_sets"].append({"id": key, "area_index": 0, "source": {"file": "ST09T.BIN", "call_pc": "0x800EF5C4", "loader": "0x800EF8AC", "controller": {"constructor": "0x800EF56C"}}, "predicate": {"all": [{"kind": "stage_area_byte_equals", "value": 0}, {"kind": "stage_state_byte_equals", "value": 0}, {"kind": "native_event_flag", "id": 0x5C1, "set": False}]}}); manifest["instances"].append(entry); return manifest
def export_stage_scripted_actors(dat_dir, output_dir, stage):
	if stage == "ST04": return export_flutter_scripted_actors(dat_dir, output_dir)
	if stage == "ST08": return export_st08_scripted_actors(dat_dir, output_dir)
	if stage in INTERIOR_SCRIPT_BINDINGS:
		manifest = export_interior_scripted_actors(dat_dir, output_dir, stage)
		if stage == "ST09": add_st09_follower(manifest, dat_dir); bind_native_lock_on((Path(dat_dir) / "ST09T.BIN").read_bytes(), manifest["instances"]); write_output(Path(output_dir) / "scripted_actors.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
		if stage == "ST0D":
			manifest = world.add_tundra_follower(manifest, dat_dir, output_dir)
		return manifest
	raise ValueError(f"No source-authenticated scripted actor export exists for {stage}")

NPC_STAGE_BINDINGS = {"ST19": {"actors": 0x800F55D8, "actor_section": 0x10000, "callback": 0x800E7E3C, "constructor": 0x800E808C, "hitbox": 0x800FDBB4}, "ST1A": {"actors": 0x800EDB98, "actor_section": 0x5800, "callback": 0x800E74B4, "constructor": 0x800E7704, "hitbox": 0x800EDFA4}, "ST1B": {"actors": 0x800EFC14, "actor_section": 0x9800, "callback": 0x800E78F0, "constructor": 0x800E7B40, "hitbox": 0x800F0274}, "ST2A": {"actors": 0x800EFDAC, "actor_section": 0xC000, "callback": 0x800E8038, "constructor": 0x800E8288, "hitbox": 0x800F0990}}
def export_friendly_npcs(dat_dir, output_dir, stage):
	from disc import decompress_section
	binding = NPC_STAGE_BINDINGS[stage]; dat_dir = Path(dat_dir).resolve(); output_dir = Path(output_dir); root_path = dat_dir / (stage + ".BIN"); overlay_path = dat_dir / (stage + "T.BIN"); root = root_path.read_bytes(); overlay = overlay_path.read_bytes(); source, section = decompress_section(root, binding["actor_section"]); header = bytearray(48); struct.pack_into("<3I", header, 0, 10, len(source), section["section_count"]); work = ROOT / "build/stages"; work.mkdir(parents=True, exist_ok=True); normalized = work / (stage + "_models.bin"); write_output(normalized, header + source); archive, payload = actor_archive(normalized); area_count = len(Stage(root).grids); pointers = struct.unpack_from(f"<{area_count}I", overlay, 48 + binding["actors"] - 0x800E7000); instances = []; exported = {}
	for area, pointer in enumerate(pointers):
		at = 48 + pointer - 0x800E7000
		for record_index in range(256):
			offset = at + record_index * 20; raw = overlay[offset:offset + 20]
			if len(raw) != 20: raise ValueError(f"{stage} actor list is truncated")
			if raw[0] == 255: break
			if raw[2] != 0x20 or raw[4] != 0: continue
			resource_flags = (raw[6] << 16) | 0x20; matches = [entry for entry in archive["models"] if entry["flags"] == resource_flags]
			if len(matches) != 1: raise ValueError(f"{stage} class0/subtype{raw[6]} has no unique native resource")
			model_index = matches[0]["index"]; model_file = f"actors/{stage}_model_{model_index:02d}.glb"
			if model_index not in exported:
				model = export_actor_model(payload, model_index, overlay_path, output_dir / model_file, root_path.name); model["startup_control"] = {"code": 0, "clip": model["control_map"].get("0"), "source_function": hex(binding["constructor"])}; exported[model_index] = model
			x, y, z, yaw = struct.unpack_from("<hhhH", raw, 12); instances.append({"stage": stage, "area_index": area, "global_area_indices": [area], "record_index": record_index, "file_offset": offset, "source_record_ram": hex(0x800E7000 + offset - 48), "record_type": raw[2], "record_class": raw[3], "flags": raw[0], "actor_class": raw[4], "resource_variant": raw[6], "actor_resource_key": raw[7], "native_private_raw": list(raw[8:12]), "model_index": model_index, "model_file": model_file, "native_resource_flags": resource_flags, "startup_control": exported[model_index]["startup_control"], "transform_raw": [x, y, z, yaw], "transform": {"position": [-x * UNIT, -y * UNIT, z * UNIT], "yaw_raw": yaw, "yaw_turns": -yaw / 4096.0, "floor_height": y == -1}, "source_bytes_hex": raw.hex(), "native_hitbox": {"field": "actor+0x58", "source_ram": hex(binding["hitbox"]), "bounds_raw": list(struct.unpack_from("<6h", overlay, 48 + binding["hitbox"] - 0x800E7000))}, "behavior_dispatch": {"actor_class": 0, "class_callback": hex(binding["callback"]), "constructor": hex(binding["constructor"]), "resource_lookup": "SLES0x8003DFC8 reads actor+6 subtype; class0 archive flags0x20|subtype<<16", "unresolved": ["Native movement and talk state machine"]}})
		else: raise ValueError(f"{stage} actor list has no terminator")
	manifest = {"stage": stage, "source": {"overlay_file": str(overlay_path.relative_to(ROOT)), "overlay_sha256": sha256(overlay), "archive_file": str(root_path.relative_to(ROOT)), "archive_sha256": sha256(root), "archive_section": binding["actor_section"], "area_object_pointer_ram": hex(binding["actors"]), "actor_list_parser": "SLES0x8003D3F8;20-byte standard records", "archive_model_count": archive["model_count"]}, "npc_instances": instances, "scripted_actor_instances": [], "static_actor_instances": [], "models": list(exported.values()), "runtime_port": {"supported_classes": [0], "unresolved_adapters": ["Native movement and talk state machine"]}}
	bind_native_lock_on(overlay, instances); output_dir.mkdir(parents=True, exist_ok=True); write_output(output_dir / "npcs.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"{stage} ordinary NPCs: {len(instances)} instances, {len(exported)} original models"); return manifest
def export_npcs(dat_dir, output_dir, stage="ST0F"):
	if stage != "ST0F": return export_friendly_npcs(dat_dir, output_dir, stage)
	texture_path = dat_dir / "ST0FT.BIN"; archive_path = dat_dir / "ST0F00.BIN"; texture = texture_path.read_bytes(); archive, payload = actor_archive(archive_path); static_instances, resource_map = parse_actor_instances(texture, archive["model_count"]); global_area_script_routes, script_area_routes = parse_global_area_script_routes(texture); scripted_instances = parse_script_actor_instances(texture, archive["model_count"], script_area_routes); static_models = sorted({instance["model_index"] for instance in static_instances}); scripted_models = sorted({instance["model_index"] for instance in scripted_instances}); models = []; game = (dat_dir.parent / "COMMON" / "GAME.BIN").read_bytes()
	for model_index in static_models:
		metadata = archive["models"][model_index]
		if metadata["mesh"]["bone_count"] or metadata["controls"]: raise ValueError(f"ST0F00 static actor model {model_index} is unexpectedly rigged")
		models.append(export_static_actor(payload, model_index, texture_path, output_dir / "actors" / f"ST0F00_model_{model_index:02d}.glb"))
	for model_index in scripted_models:
		metadata = archive["models"][model_index]
		if not metadata["mesh"]["bone_count"]: raise ValueError(f"ST0FT script actor model {model_index} has no source skeleton")
		models.append(export_actor_model(payload, model_index, texture_path, output_dir / "actors" / f"ST0F00_model_{model_index:02d}.glb"))
	control_runtime = {"control_field": "actor+0xA0", "initializer": {"file": "ST0FT.BIN", "function": "0x800ED1A8", "code": 1, "previous_code": 255}, "apply": {"file": "SLES_035.56", "function": "0x8003F4E8", "table_field": "actor+0xAC", "slot_formula": "control_code indexes actor+0xAC by 4-byte entries", "clip_formula": "control_NN uses source control slot N"}}
	models_by_index = {model["model_index"]: model for model in models if "model_index" in model}
	for model_index in scripted_models:
		model = models_by_index[model_index]; control_map = model.get("control_map", {}); model["source_control_runtime"] = {**control_runtime, "slot_to_clip": control_map}
		if model_index in (5, 6):
			code = 4 if model_index == 5 else 1; model["startup_control"] = {"code": code, "clip": control_map.get(str(code)), "previous_code": 255, "source_function": "ST0FT.BIN 0x800E7B90" if model_index == 5 else "ST0FT.BIN 0x800ED1A8"}
	for instance in scripted_instances:
		model = models_by_index.get(instance["model_index"])
		if not model: continue
		control_map = model.get("control_map", {}); dispatch_index = instance["dispatch_index"]; behavior = ACTOR_BEHAVIOR_DISPATCH.get(dispatch_index); instance["source_control_runtime"] = {**control_runtime, "slot_to_clip": control_map}; instance["behavior_dispatch"] = {"field": "record byte+6 / actor+6", "dispatcher": "ST0FT.BIN 0x800ED2D8", "table_ram": "0x80100B68", "index": dispatch_index, "callback": behavior["callback"] if behavior else None, "control_codes": {str(code): control_map.get(str(code)) for code in behavior["control_codes"]} if behavior else {}, "unresolved": "dispatch index is outside the four source table callbacks" if not behavior else None}
		actor_class = instance["actor_class"]; combat = source_combat_attributes(game, actor_class, instance["actor_resource_key"]); instance["source_attributes"] = combat["normal"]["attributes"]; instance["combat"] = combat; instance["startup_control"] = model["startup_control"]; instance["source_control_runtime"]["initializer"] = {"file": "ST0FT.BIN", "function": "0x800E7B90" if actor_class == 5 else "0x800ED1A8", "code": instance["startup_control"]["code"], "previous_code": 255}; instance["native_hitbox"] = {"file": "ST0FT.BIN", "table_ram": "0x80100948" if actor_class == 5 else "0x80100B78", "bounds_raw": [-32, 32, -160, 0, -32, 32] if actor_class == 5 else [-64, 64, -512, 0, -64, 64], "anchor_bone": 0, "anchor_function": "SLES_035.56 0x8003EEC4"}; instance["native_model_selector"] = {"class_field": "record+4 / actor+4", "resource_key_field": "record+7 / actor+7", "resource_lookup": "SLES_035.56 0x8003DFE8 matches archive flags byte+1 to class and byte+2 to subtype", "selector_table_ram": "0x801009C4" if actor_class == 5 else "0x80100BC8", "selector": 1, "archive_header_class": actor_class, "archive_header_subtype": 1}
		if actor_class == 5:
			states = [3, 0, 12, 10, 1, 2, 13]; instance["behavior_dispatch"] = {"field": "record+6 / actor+6 selects constructor state, not archive model", "actor_class": 5, "class_callback": "0x800E7984", "constructor": "0x800E7B90", "initializer_table_ram": "0x801009CC", "initial_state": states[dispatch_index & 15], "state_table_ram": "0x801009DC", "state_dispatcher": "0x800E7EEC", "hit_handler": "0x800E9F30", "health_helper": "SLES_035.56 0x80044020", "hit_counter_initializer": {"ram_function": "0x800E7CD4", "field": "actor private+0x17", "value": 3}, "hit_counter_mask": "0x001C0000", "death_when": "signed HP < 0", "strong_stagger_when": "hit counter <= 0 resets counter to 3 and enters state15; nonnegative HP recovers after6ticks", "death_state": 15, "unresolved": None}
		else: instance["behavior_dispatch"].update({"actor_class": 8, "class_callback": "0x800ECFC0", "constructor": "0x800ED1A8", "hit_handler": "0x800ED7E8", "health_helper": "SLES_035.56 0x80044020", "hit_damage_mask": "0x00040000", "death_when": "signed HP < 0", "attack_effect": {"allocator": "SLES_035.56 0x8003E8F8", "dispatcher": "SLES_035.56 0x8003CE00", "stage_callback_table_ram": "0x800FF734", "class": 4, "callback": "0x800F4BC4", "collision_registration": "0x800F66A0-0x800F66CC", "damage_formula": "attribute byte2 << 2", "hit_flags": "0x00100000", "bone": 0, "phase_ticks": [8, 7, "while actor refreshes effect+0xC", 8], "radius_formula": "effect+0xF starts at 3 and gains 2 per growth tick; world sphere radius=value/16", "sound_id": 212}})
	global_area_route_source = {"file": "ST0FT.BIN", "pointer_table_file_offset": GLOBAL_AREA_SCRIPT_POINTER_OFFSET, "pointer_table_ram": "0x80078D84 -> 0x800FFF90", "initializer": "ST0FT.BIN 0x800E71B8-0x800E71CC", "consumer": "GAME.BIN 0x800D9A54 reads actor+0x14 and copies mapping byte+2 into actor+0x15/script-area index", "condition_helper": {"game_function": "0x800DA430", "selector": "(mapping byte+3 & 1)==0", "player_position_source_offsets": [0x12, 0x1A], "position_formula": "((signed16(player_position) >> 9) - signed8(mapping byte+4/+5)) < unsigned8(mapping byte+6/+7)", "upper_bound_exclusive": True}, "yaw_offset": "GAME.BIN 0x800D9B50 uses mapping byte+3 bit7 as a gate and adds 0x800 only when script-record byte+1 bit7 is also set; mapping bytes+0/+1 do not translate spawn positions"}
	manifest = {"stage": "ST0F", "source": {"overlay_file": "build/disc-assets/DAT/ST0FT.BIN", "overlay_sha256": sha256(texture), "area_object_pointer_offset": AREA_OBJECT_POINTER_OFFSET, "area_object_record_size": AREA_OBJECT_RECORD_SIZE, "actor_resource_map_offset": ACTOR_RESOURCE_MAP_OFFSET, "actor_resource_map": resource_map, "actor_list_parser": {"file": "build/disc-exe/SLES_035.56", "function": "0x8003D3F8", "record_type": "0x20 allocates through 0x8003E5B0", "actor_pool_ram": "0x8007A140", "actor_pool_count": 24, "actor_pool_stride": 0x16C, "actor_model_resource_byte": 7, "transform_bytes": [12, 14, 16, 18], "position_unit": "signed raw / 256", "yaw_unit": "unsigned / 4096 turns"}, "script_area_pointer_offset": SCRIPT_AREA_POINTER_OFFSET, "script_area_count": SCRIPT_AREA_COUNT, "script_record_size": SCRIPT_RECORD_SIZE, "script_area_global_routing": global_area_route_source, "global_area_script_routes": global_area_script_routes, "script_area_loader": {"file": "build/disc-assets/COMMON/GAME.BIN", "initializer": "ST0FT 0x800E722C sets global 0x80078CE0 to 0x800FFED4", "loader": "GAME 0x800D9B50 selects the script area list and allocates type-0x20 records via SLES 0x8003E5B0", "model_selector": "record byte+4 selects the ST0F00 model; record byte+7 is the resource key copied into actor+7", "record_class_offset": 3, "behavior_dispatch_offset": 6, "instance_id_offset": 20, "activation_test": {"game_function": "0x800D9B50", "helper_file": "build/disc-exe/SLES_035.56", "helper_function": "0x80046090", "flag_table_ram": "0x8009C7E8", "flag_word_offset": 0x5C, "word_formula": "instance_id >> 5", "bit_mask_formula": "0x80000000 >> (instance_id & 31)", "spawn_when": "flag bit is clear; a set bit causes the record to be skipped"}, "behavior_dispatch": {"file": "ST0FT.BIN", "dispatcher": "0x800ED2D8", "table_ram": "0x80100B68", "callbacks": ACTOR_BEHAVIOR_DISPATCH, "control_apply_function": "SLES_035.56 0x8003F4E8"}}, "archive_file": "build/disc-assets/DAT/ST0F00.BIN", "archive_sha256": archive["sha256"], "archive_model_count": archive["model_count"]}, "npc_instances": [instance for instance in scripted_instances if archive["models"][instance["model_index"]]["mesh"]["bone_count"]], "scripted_actor_instances": scripted_instances, "static_actor_instances": static_instances, "models": models, "classification": "Script-list records use source class/model/animation data; health and projectile behavior remain unbound until traced from the source runtime."}
	export_pickup_data(game, output_dir)
	manifest["pickups"] = "pickups.json"
	manifest["classification"] = "Source classes 5 and 8 are combat actors with original resource attributes, hit handling, health and death callbacks."; manifest["source"]["script_area_loader"]["model_selector"] = "record+4 is actor class; constructor selector indexed by record+7 matches archive header class/subtype, resolving class5/key1 to model5 and class8/key0 to model6"; manifest["runtime_port"] = {"tick_rate": 25, "supported_classes": [5, 8], "unresolved_adapters": ["Shared spatial avoidance index is not ported", "Godot movement and floor queries replace native map collision helpers", "Godot meshes and billboards replace native GPU effect projection and STP blending"]}
	output_dir.mkdir(parents=True, exist_ok=True); manifest_path = output_dir / "npcs.json"; write_output(manifest_path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"ST0F area actors: {len(scripted_instances)} script instances ({len(manifest['npc_instances'])} rigged), {len(models)} referenced models -> {manifest_path}"); return manifest

def npcs_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--stage", choices=["ST0F", *NPC_STAGE_BINDINGS], default="ST0F"); parser.add_argument("--output-dir", type=Path); args = parser.parse_args(); export_npcs(args.dat_dir, args.output_dir or ROOT / "assets/levels" / args.stage, args.stage)

def flutter_actors_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--output-dir", type=Path); args = parser.parse_args(); export_flutter_scripted_actors(args.dat_dir, args.output_dir or ROOT / "assets/levels/ST04")

def stage_actors_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--dat-dir", type=Path, default=Path("build/disc-assets/DAT")); parser.add_argument("--stage", choices=["ST04", "ST08", *INTERIOR_SCRIPT_BINDINGS], required=True); parser.add_argument("--output-dir", type=Path); parser.add_argument("--compact-existing", action="store_true"); args = parser.parse_args(); output = args.output_dir or ROOT / "assets/levels" / args.stage
	if args.compact_existing:
		path = output / "scripted_actors.json"; manifest = compact_registration_manifest(json.loads(path.read_text(encoding="utf-8"))); write_output(path, json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); print(f"{args.stage} compacted: {len(manifest['instances'])} conditional instances, {len(manifest['spawn_sets'])} source paths")
	else: export_stage_scripted_actors(args.dat_dir, output, args.stage)
from world import textures
from world import texture_page
from ui import decode_page
from world import Stage
from world import png
packed_point = point
from disc import read_u16, write_output
from disc import read_u32

# ---- special_weapons ----
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
	track_offsets = [value for value in (u32(source, track_file + i) for i in range(0, track_table, 4)) if value]; control_offsets = [value for value in (u32(source, control_file + i) for i in range(0, control_table, 4)) if value]; tracks = {}
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
		def rotations(bone, order): return [value for pose, target, fraction in samples for value in decode_rotation(word(pose, bone + 1), word(target, bone + 1) if target is not None else None, fraction, order)]
		input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True); root = [bones[0][axis] + value for pose, target, fraction in samples for axis, value in enumerate(point(word(pose, 0), word(target, 0) if target is not None else None, fraction))]
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
	document = {"asset": {"version": "2.0", "generator": "tools/models.py", "extras": extras}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": [{"name": mesh_name, "primitives": mesh["primitives"]}], "skins": [{"name": "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse}], "animations": animations, "materials": mesh["materials"], "textures": mesh["textures"], "images": mesh["images"], "samplers": mesh["samplers"], "bufferViews": binary.views, "accessors": binary.accessors, "buffers": [{"byteLength": len(binary.data)}], "extensionsUsed": ["KHR_materials_unlit"]}
	chunk = json.dumps(document, separators=(",", ":")).encode("utf-8"); chunk += b" " * ((-len(chunk)) & 3); binary.data.extend(b"\0" * ((-len(binary.data)) & 3))
	write_output(path, struct.pack("<4sII", b"glTF", 2, 28 + len(chunk) + len(binary.data)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk + struct.pack("<I4s", len(binary.data), b"BIN\0") + binary.data)
def strip(vram, tpage, clut, u, v, width, height, frames):
	page = ui.decode_page(vram, tpage & 0x1F, clut, True); pixels = bytearray()
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
def export_weapon_arm(weapon, output_dir, library, model, arm_name):
	common = ROOT / "build/disc-assets/COMMON"; output_dir.mkdir(parents=True, exist_ok=True); module_file = f"PL00R{weapon - 1:02X}.BIN"
	module_bytes = (common / module_file).read_bytes(); player = (common / "PL00P000.BIN").read_bytes()
	if u32(module_bytes, 0x30) != 0x60 + weapon or u32(module_bytes, 12) != MODULE_BASE: raise ValueError(f"{module_file} is not the weapon {weapon:#x} module")
	R = Image(module_bytes, MODULE_BASE, 0x30, module_file[4:7]); G = Image((common / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); S = Image((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), SLES_BASE, 0x800, "SLES")
	nodes, bones, world_points, bone_node_ids = cinematics.skeleton_nodes(); binary = BinaryGLB(); animations, clips, bank = decode_controls(module_bytes, binary, bone_node_ids, bones, u32(player, 0x0C)) if any(s["type"] == 1 and s["address"] == 0x80121E20 for s in sections(module_bytes).values()) else ([], [], {"note": "module has no equipment-action banks"})
	player_base, player_size, family = u32(player, 0x0C), u32(player, 4), player[0x30 + 0x71]; row_table = 0x8006AEC0 + family * 28; slots = [[S.byte(0x80078ADC + mode * 5 + i) for i in range(5)] for mode in range(4)]; strip_counts = [S.byte(0x80078B04 + i) for i in range(5)]; strip_bones = [S.byte(0x80078AF0 + i) for i in range(sum(strip_counts))]
	part = slots[0].index(2); arm_bones = strip_bones[sum(strip_counts[:part]):sum(strip_counts[:part + 1])]; arm_descriptor, replaced_descriptor = S.word(row_table + slots[1][part] * 4), S.word(row_table + slots[0][part] * 4); arm_section = next((o for o, s in sections(module_bytes).items() if s["type"] == 1 and s["address"] == arm_descriptor), None)
	if S.word(0x80023468) >> 16 != 0x8202 or (S.word(0x80023468) & 0xFFFF) != 0x18C or slots[1][part] != 3 or arm_section is None or arm_descriptor != player_base + player_size: raise ValueError(f"Weapon arm descriptor slot does not match {module_file}")
	arm_payload = player[0x30:0x30 + player_size] + module_bytes[arm_section + 0x30:arm_section + 0x30 + sections(module_bytes)[arm_section]["size"]]; arm, *_, arm_faces, arm_vertices, _ = decode_mesh(arm_payload, ((arm_name, arm_descriptor - player_base, tuple(arm_bones)),))
	player_vram, _ = world.textures(common / "PL00T.BIN"); clut_uploads = world.texture_uploads(module_bytes, player_vram, module_file); material_words = struct.unpack_from("<4I", arm_payload, 0x60); arm_materials = sorted({material for material, _ in arm})
	write_glb(output_dir / model, binary, nodes, bone_node_ids, world_points, animations, {"source": "COMMON/" + module_file, "library": library, "weapon": weapon}, arm_name, arm_mesh(binary, arm, {m: world.texture_page(player_vram, material_words[m] >> 16, material_words[m] & 0xFFFF) for m in arm_materials}))
	arm_manifest = {"model": model, "node": arm_name, "source": f"COMMON/{module_file} section {arm_section:#x} -> {arm_descriptor:#x} (PBD descriptor appended to PL00P000 payload {player_base:#x}+{player_size:#x})", "descriptor": hex(arm_descriptor), "descriptorRow": f"SLES 0x8006AEC0 family {family} slot {slots[1][part]}", "bones": arm_bones, "boneNames": [f"Bone_{b:02d}" for b in arm_bones], "faces": arm_faces, "vertices": arm_vertices,
		"replaces": {"part": "OtherArm", "descriptor": hex(replaced_descriptor), "descriptorSlot": slots[0][part], "pbdGroup": hex(replaced_descriptor - player_base), "bones": arm_bones, "boneNames": [f"Bone_{b:02d}" for b in arm_bones], "rule": "hide every player triangle skinned to these bones (only the OtherArm group uses them)"},
		"condition": {"value": "player+0x18C >= 2", "source": "SLES 0x80023438 (0x80023468..0x8002348C): render mode = (0x18C >= 2) + 2*(0x18D >= 2) picks the descriptor-slot row at SLES 0x80078ADC; strips/bones per part at 0x80078B04/0x80078AF0", "modes": slots, "visibility": "whenever the weapon is the active special (equipped), not only while spraying", "activeWeapon": "GAME 0x800CF4A8/0x800CF540: 0x18C = 0x18E in modes 1/2 when +6 == 0 and 0x19F != 0; mode 0 (safe zones) clears 0x18C"},
		"materials": {str(m): {"clut": hex(material_words[m] >> 16), "tpage": hex(material_words[m] & 0xFFFF)} for m in arm_materials}, "clutUpload": {"section": f"{module_file} {next(o for o, s in sections(module_bytes).items() if s['type'] == 2):#x} type 2", "rect": clut_uploads[0]["palette_rect"] if clut_uploads else None, "note": "material 3 CLUT 0x3C0C is only used by this descriptor; its palette comes from the module, page 6 texels from PL00T.BIN"}, "emitBone": {"bone": 4, "note": "stream origin is the Bone_04 joint (player+0x4B0 cache, SLES 0x80040624); the visible stream starts at segment 1 (billboard size 10*i), past the nozzle"}}
	return {"arm": arm_manifest, "clips": clips, "bank": bank, "module": module_bytes, "image": R, "game": G, "sles": S, "slots": slots, "part": part}
def export_extinguisher(output_dir=None):
	output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/weapons"; common = ROOT / "build/disc-assets/COMMON"
	built = export_weapon_arm(WEAPON_ID, output_dir, "weapon_0f", "hose_clips.glb", "ExtinguisherArm"); arm_manifest, clips, bank, module_bytes, R, G, S, slots, part = built["arm"], built["clips"], built["bank"], built["module"], built["image"], built["game"], built["sles"], built["slots"], built["part"]; library, model = "weapon_0f", "hose_clips.glb"
	if G.half(0x800DBE44 + (WEAPON_ID - 3) * 2) != 0x22 or S.word(0x8006B3A0 + 0x0E * 4) != 0x8010A004 or S.word(0x8006B3E4 + 0x16 * 4) != 0x8010ABA0: raise ValueError("Weapon 0x0F dispatch tables do not match PL00R0E")
	vram, _ = world.textures(common / "GAME.BIN"); stream_word = R.pair(0x8010A9F8, 0x8010A9FC); stream_tpage, stream_clut, stream_v = R.pair(0x8010AA00, 0x8010AA04) >> 16, stream_word >> 16, (stream_word >> 8) & 255
	write_output(output_dir / "hose_stream.png", world.png(128, 32, strip(vram, stream_tpage, stream_clut, 0, stream_v, 32, 32, 4)))
	splash_subtype = R.imm(0x8010A7FC); splash_row = 0x800DD43C + splash_subtype * 8; splash_tpage, splash_clut, splash_flags, splash_sound = G.half(splash_row) & 0xFFFF, G.half(splash_row + 2) & 0xFFFF, G.half(splash_row + 4), G.half(splash_row + 6); frame_table = G.word(0x800DD654 + splash_subtype * 4); splash_frames = []
	for index in range(32):
		record = frame_table + index * 12; splash_frames.append({"rgb": rgb(G.word(record)), "uv": [G.byte(record + 4), G.byte(record + 5), G.byte(record + 6) - G.byte(record + 4) + 1, G.byte(record + 7) - G.byte(record + 5) + 1], "durationTicks": G.byte(record + 8) + 1, "next": G.byte(record + 9), "sizeAdd": G.byte(record + 10), "sizeHigh": G.byte(record + 11)})
		if G.byte(record + 9) == 0xFF: break
	su, sv, sw, sh = splash_frames[0]["uv"]; write_output(output_dir / "hose_splash.png", world.png(sw * len(splash_frames), sh, strip(vram, splash_tpage, splash_clut, su, sv, sw, sh, len(splash_frames))))
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
		"splash": {"spawn": "SLES 0x8003E918 pool, class 0 (GAME 0x800D7FD8)", "subtype": ref(splash_subtype, 0x8010A7FC), "jitter": "pos += ((rand & 63) - 32) * (i + 1) >> 3 per axis (R0E 0x8010A82C)", "size": "12 + 6i, plus each frame's sizeAdd", "texture": "hose_splash.png", "textureSource": {"archive": "COMMON/GAME.BIN section 0x34800", "tpage": hex(splash_tpage), "clut": hex(splash_clut), "row": hex(splash_row), "frameTable": hex(frame_table), "flags": splash_flags}, "blend": "additive (tpage 0x2F)", "frames": splash_frames, "lifetimeTicks": sum(frame["durationTicks"] for frame in splash_frames), "sound": ref(splash_sound, splash_row + 6, "GAME", file=f"res://assets/audio/ST0F/fx_{splash_sound:03x}.ogg", positional=True)},
		"droplets": {"actors": ref(R.imm(0x8010A1DC, (10,)), 0x8010A1DC), "slotsPerActor": ref(R.imm(0x8010AD2C, (10,)), 0x8010AD2C), "lifetimeTicks": ref(R.imm(0x8010B1E4), 0x8010B1E4), "spawn": "bone 4 cache; yaw = player yaw + ((rand >> 16) & 0x1FF) - 0x100", "velocityRaw": ref([0, R.imm(0x8010AFDC), R.imm(0x8010AFE8)], 0x8010AFDC, note="rotated by SLES 0x800421E0, applied along droplet yaw by SLES 0x80041894; raw/16 units per tick assumed"), "inheritPlayerMotion": "half the player's planar displacement, rotated into droplet yaw", "verticalJitter": "((rand >> 8) & 0xFF) - 0x80 + |yawJitter| / 2", "gravityRaw": ref(R.imm(0x8010AE24), 0x8010AE24), "render": "GP0 0x52 shaded line from old to new position, E1 0x220 (additive)", "rgbStart": ref(rgb(R.pair(0x8010AEC8, 0x8010AECC)), 0x8010AEC8, step=[1, 1, 2]), "rgbEnd": ref(rgb(R.pair(0x8010AED4, 0x8010AEF4)), 0x8010AED4, step=[3, 6, 6]), "colourFormula": "base + step * remaining life", "runsWhile": "player+0xC8 set; then live slots drain"},
		"underwater": {"condition": "player+0xBE != 0 (meaning unverified)", "state": "R0E 0x8010A488", "effect": "class 0x48 subtype 0 via SLES 0x8003E800, one per tick; visual unverified", "speed": ref(R.imm(0x8010A5A4), 0x8010A5A4), "life": "0x14 + (rand & 7)", "field0C": ref(R.imm(0x8010A574), 0x8010A574), "field0E": ref(R.imm(0x8010A5D0), 0x8010A5D0)},
		"sounds": {"start": ref(R.imm(0x8010A230), 0x8010A230, file="res://assets/audio/ST0F/fx_10d.ogg", positional=False), "loopIntervalTicks": ref(R.imm(0x8010A164), 0x8010A164), "loopReplay": ref(R.imm(0x8010A368), 0x8010A368), "stop": ref(R.imm(0x8010A390), 0x8010A390, file="res://assets/audio/ST0F/fx_10e.ogg", positional=False), "splash": ref(splash_sound, splash_row + 6, "GAME", file=f"res://assets/audio/ST0F/fx_{splash_sound:03x}.ogg"), "bank": "PL00R0E.BIN section 0x4000 (logical bank 0x0F), exported by tools/audio.py"},
		"hud": hud}
	write_output(output_dir / "weapon_0f.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return {"model": model, "clips": len(clips), "segments": len(segments), "splashFrames": len(splash_frames)}

def export_outfits(output_dir=None):
	"""Player model set per helmet and shoes: GAME 0x800BA6EC selects the halfword at table 0x800DBE10[helmet * 6 + shoes] as the loaded PL00P file index (COMMON directory order starting at 9 = PL00P000)."""
	output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/outfits"; G = Image((COMMON / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); names = sorted(path.stem for path in COMMON.glob("PL00P0??.BIN")); first = 9
	if len(names) != 12 or G.half(0x800DBE44) != first + len(names) + 1 or G.word(0x800BA6EC) & 0xFFFF != 0x1A3 or G.word(0x800BA6F0) & 0xFFFF != 0x1A2: raise ValueError("Player outfit table or file order differs")
	rows = [[names[G.half(0x800DBE10 + (row * 6 + column) * 2) - first] for column in range(6)] for row in range(3)]
	if rows[1] != rows[2]: raise ValueError("Helmet rows one and two differ")
	for name in sorted({name for row in rows for name in row} - {"PL00P000"}): export_variant(name + ".BIN", name + ".glb", None, PARTS, False, output_dir, meshes_only=True)
	result = {"source": "GAME 0x800BA6EC: table 0x800DBE10[helmet * 6 + shoes] of PL00P file indices (9 = PL00P000 ... 0x14 = PL00P015); helmet is player+0x1A2 (row 2 is the Padded Helmet), shoes player+0x1A3 (column)", "rows": rows, "model_dir": "res://assets/player/outfits/", "base": "PL00P000"}
	write_output(output_dir / "outfits.json", json.dumps(result, indent=1) + chr(10), encoding="utf-8"); return result

def export_special_modes(output=None):
	"""Per-stage argument of GAME 0x800CF4A8 (0 none, 1 equipped special, 2 force weapon 0x0F) issued by each STxxT area-load handler."""
	disc.ensure_package("capstone", "capstone==5.0.9"); import capstone
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
	write_output(Path(output) if output else ROOT / "assets/player/special_modes.json", json.dumps(result, indent=1) + "\n", encoding="utf-8"); return result

def export_weapon_stats(output=None):
	"""Weapon stat tables of GAME: levels (attack, energy, range, rapid) per weapon from the accessors 0x800CF3B8/0x800CF40C/0x800CF440/0x800CF474, firing sequence records, special gauge records and the armor/helmet damage constants."""
	G = Image((ROOT / "build/disc-assets/COMMON/GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); table, firing, gauge = 0x800DCCC0, 0x800DC978, 0x800DCA08
	if [G.word(a) for a in (0x800CF3B8, 0x800CF3BC, 0x800CF40C, 0x800CF440, 0x800CF474)] != [0x3C02800E, 0x2442CCC0, 0x3C02800E, 0x3C02800E, 0x3C02800E] or G.word(0x800CF3D0) != 0x808201F4 or G.word(0x800CF434) >> 16 != 0x8442 or G.word(0x800CF434) & 0xFFFF != 2 or G.word(0x800CF468) & 0xFFFF != 4 or G.word(0x800CF49C) & 0xFFFF != 6 or G.word(0x800CF3E0) >> 16 != 0x9442: raise ValueError("Weapon stat accessors differ")
	if G.word(0x800B0A78) != 0xA0430204 or G.word(0x800B0A88) != 0xA0430207 or G.imm(0x800CB69C) != 4 or G.imm(0x800CB6DC) != 0x10 or G.imm(0x800C8E68) != -8 or G.word(0x800CB6A4) != 0x00021643: raise ValueError("Armor and helmet constants differ")
	pointers = [G.word(table + 4 * index) for index in range(18)]; weapons = {}
	for index in range(1, 18):
		pointer = pointers[index]; following = pointers[index + 1] if index < 17 else 0; count = (following - pointer) // 8 if following > pointer else 4
		weapons[str(index)] = {"levels": [[G.half(pointer + 8 * level + 2 * stat) for stat in range(4)] for level in range(count)], "firing": [G.byte(firing + 8 * index + offset) for offset in range(8)], "gauge": list(struct.unpack_from("<3H", G.data, G.offset(gauge + 8 * index))) if index >= 3 else None}
	result = {"source": "GAME 0x800CF3B8/0x800CF40C/0x800CF440/0x800CF474(player, weapon): level byte player+0x1F4+8*weapon+stat indexes the 8-byte records at table[weapon] (table 0x800DCCC0): s16 attack, energy, range, rapid; weapon 2 is the Buster (8 levels, level = Buster part sum, SUBSCN 0x801DE3B4), 0x18C selects the special weapon, 0x18D the Buster/kick weapon; shot spawn GAME 0x800D04FC..0x800D0850: range stat = shot lifetime in ticks, attack stat = damage and sprite level, energy stat = maximum shots in flight (player+0x19C counts them, GAME 0x800CDC3C/0x800D0B40), rapid stat added to the firing record fire pose (record[1]) by GAME 0x800CE8EC/0x800CF0C4",
		"attack_halved_when_save_byte16": 4, "outfit_override": {"source": "GAME 0x800B09D0 saves the outfit and Buster stats to 0x800E0B98, then 0x800B0A4C writes these values; 0x800B0A8C restores them. Called by ST0B/ST1B/ST1B01 when event flag 0x246 is set (and sets 0x24B), restored by ST55 when 0x249 or 0x680 is set and 0x24C is clear", "helmet": G.imm(0x800B0A58), "shoes": 0, "armor": G.imm(0x800B0A60), "buster": [G.imm(0x800B0A60), 0, 0, G.imm(0x800B0A60)], "request_flag": 0x246, "active_flag": 0x24B, "restore_flags": [0x249, 0x680], "restored_blocker_flag": 0x24C, "restored_flag": 0x248}, "underwater_range": G.imm(0x800D0728), "underwater_flags": G.imm(0x800D0720), "firing_record": ["start_pose", "fire_pose", "end_pose", "fires"], "firing_table": hex(firing), "gauge_record": ["drain", "threshold", "recharge"], "gauge_table": hex(gauge), "level_table": hex(table), "weapons": weapons,
		"body_parts": {"source": "GAME 0x800CB678: damage = max(1, damage * (4 - (armor >> 1)) >> 2) and the knockdown test is accumulated damage > 0x10 + 4 * (4 - (armor >> 1)); GAME 0x800C8E54 charges 8 damage on the knockdown landing without a helmet; helmet 2 enables the roll dodge GAME 0x800CA824 -> 0x800CB008", "armor_base": 0x3BC, "armor_field": 0x1A4, "helmet_base": 0x3B8, "helmet_field": 0x1A2, "shoes_base": 0x3C8, "shoes_field": 0x1A3, "armor_multiplier": G.imm(0x800CB69C), "knockdown_base": G.imm(0x800CB6DC), "knockdown_step": 4, "helmetless_landing_damage": -G.imm(0x800C8E68)}}
	write_output(Path(output) if output else ROOT / "assets/player/weapon_stats.json", json.dumps(result, indent=1) + "\n", encoding="utf-8"); return result

def gte_s16(v): v&=0xffff; return v-0x10000 if v&0x8000 else v
def gte_s32(v): v&=0xffffffff; return v-(1<<32) if v&(1<<31) else v
def gte_clamp(v,lo,hi): return max(lo,min(hi,v))
class GTE:
	"""Geometry transformation engine subset used by the SLES record renderers and projection helpers: RTPS, RTPT, MVMVA (rotation, V0-V2, translation), NCLIP and AVSZ4."""
	def __init__(self):
		self.d=[0]*32; self.c=[0]*32; self.c[26]=1024; self.c[29]=0x155; self.c[30]=0x100
	def matrix(self,base):
		c=self.c; return [[gte_s16(c[base]),gte_s16(c[base]>>16),gte_s16(c[base+1])],[gte_s16(c[base+1]>>16),gte_s16(c[base+2]),gte_s16(c[base+2]>>16)],[gte_s16(c[base+3]),gte_s16(c[base+3]>>16),gte_s16(c[base+4])]]
	def rot(self): return self.matrix(0)
	def vec(self,i): return [gte_s16(self.d[2*i]),gte_s16(self.d[2*i]>>16),gte_s16(self.d[2*i+1])] if i<3 else [gte_s16(self.d[9]),gte_s16(self.d[10]),gte_s16(self.d[11])]
	def tr(self): return [gte_s32(self.c[5]),gte_s32(self.c[6]),gte_s32(self.c[7])]
	def set_ir(self,vals,lm):
		lo=0 if lm else -0x8000
		self.d[9],self.d[10],self.d[11]=[gte_clamp(v,lo,0x7fff)&0xffffffff for v in vals]
	def mvmva(self,cmd):
		sf=(cmd>>19)&1; mx=(cmd>>17)&3; v=(cmd>>15)&3; cv=(cmd>>13)&3; lm=(cmd>>10)&1
		if mx==3: raise ValueError('unsupported mvmva matrix')
		r=self.matrix((0,8,16)[mx]); vv=self.vec(v); t=[[gte_s32(self.c[5+k]) for k in range(3)],[gte_s32(self.c[13+k]) for k in range(3)],[gte_s32(self.c[21+k]) for k in range(3)],[0,0,0]][cv]
		mac=[((t[i]<<12)+r[i][0]*vv[0]+r[i][1]*vv[1]+r[i][2]*vv[2])>>(12*sf) for i in range(3)]
		self.d[25],self.d[26],self.d[27]=[m&0xffffffff for m in mac]; self.set_ir(mac,lm)
	def push_sz(self,z):
		self.d[16]=self.d[17]; self.d[17]=self.d[18]; self.d[18]=self.d[19]; self.d[19]=gte_clamp(z,0,0xffff)
	def rtps_one(self,idx,cmd):
		sf=(cmd>>19)&1; lm=(cmd>>10)&1
		r=self.rot(); vv=self.vec(idx); t=self.tr()
		mac=[((t[i]<<12)+r[i][0]*vv[0]+r[i][1]*vv[1]+r[i][2]*vv[2])>>(12*sf) for i in range(3)]
		self.d[25],self.d[26],self.d[27]=[m&0xffffffff for m in mac]; self.set_ir(mac,lm)
		self.push_sz(mac[2]>>((1-sf)*12))
		sz=self.d[19]; h=self.c[26]&0xffff
		q=min(0x1ffff,((h*0x20000//sz)+1)//2) if sz>h//2 and sz else 0x1ffff
		ofx=gte_s32(self.c[24]); ofy=gte_s32(self.c[25])
		sx=gte_clamp((q*gte_s16(self.d[9])+ofx)>>16,-0x400,0x3ff); sy=gte_clamp((q*gte_s16(self.d[10])+ofy)>>16,-0x400,0x3ff)
		self.d[12]=self.d[13]; self.d[13]=self.d[14]; self.d[14]=(sx&0xffff)|((sy&0xffff)<<16); self.d[15]=self.d[14]
		dqa=gte_s16(self.c[27]); dqb=gte_s32(self.c[28]); m0=q*dqa+dqb; self.d[24]=m0&0xffffffff; self.d[8]=gte_clamp(m0>>12,0,0x1000)
	def execute(self,cmd):
		op=cmd&0x3f
		if op==0x01: self.rtps_one(0,cmd)
		elif op==0x30:
			for i in range(3): self.rtps_one(i,cmd)
		elif op==0x12: self.mvmva(cmd)
		elif op==0x06:
			sx=[gte_s16(self.d[12+i]) for i in range(3)]; sy=[gte_s16(self.d[12+i]>>16) for i in range(3)]
			self.d[24]=(sx[0]*sy[1]+sx[1]*sy[2]+sx[2]*sy[0]-sx[0]*sy[2]-sx[1]*sy[0]-sx[2]*sy[1])&0xffffffff
		elif op==0x2e:
			m0=gte_s16(self.c[30])*(self.d[16]+self.d[17]+self.d[18]+self.d[19]); self.d[24]=m0&0xffffffff; self.d[7]=gte_clamp(m0>>12,0,0xffff)
		elif op==0x2d:
			m0=gte_s16(self.c[29])*(self.d[17]+self.d[18]+self.d[19]); self.d[24]=m0&0xffffffff; self.d[7]=gte_clamp(m0>>12,0,0xffff)
		elif op==0x28:
			sf=(cmd>>19)&1; lm=(cmd>>10)&1; mac=[(gte_s16(self.d[9+i])**2)>>(12*sf) for i in range(3)]
			self.d[25],self.d[26],self.d[27]=[m&0xffffffff for m in mac]; self.set_ir(mac,lm)
		elif op==0x0c:
			sf=(cmd>>19)&1; lm=(cmd>>10)&1; r=self.rot(); ir=[gte_s16(self.d[9+i]) for i in range(3)]
			mac=[(r[1][1]*ir[2]-r[2][2]*ir[1])>>(12*sf),(r[2][2]*ir[0]-r[0][0]*ir[2])>>(12*sf),(r[0][0]*ir[1]-r[1][1]*ir[0])>>(12*sf)]
			self.d[25],self.d[26],self.d[27]=[m&0xffffffff for m in mac]; self.set_ir(mac,lm)
		elif op in (0x3d,0x3e):
			sf=(cmd>>19)&1; lm=(cmd>>10)&1; ir0=gte_s16(self.d[8]); mac=[]
			for i in range(3):
				base=0 if op==0x3d else gte_s32(self.d[25+i])<<(12*sf)
				mac.append((base+gte_s16(self.d[9+i])*ir0)>>(12*sf))
			self.d[25],self.d[26],self.d[27]=[m&0xffffffff for m in mac]; self.set_ir(mac,lm)
			self.d[20]=self.d[21]; self.d[21]=self.d[22]; packed=self.d[6]&0xff000000
			for i in range(3): packed|=gte_clamp(mac[i]>>4,0,255)<<(8*i)
			self.d[22]=packed
		else: raise ValueError('unsupported gte op %x'%op)

class NativeMachine:
	"""Original SLES, GAME and one PL00R module executed unchanged in Unicorn (the 64-entry sine tables SLES 0x80011294 builds at 0x800965D8/0x800968D0 are filled in directly). The GTE is emulated for a fixed camera (identity rotation, distance and projection distance 1024, no offset), so projected points and the SLES record renderer output come out as raw 1/256-unit offsets from the effect centre."""
	LIST_RECORDS, LIST_POLYGONS, TABLE = 0x801F2800, 0x80190000, 0x801A0000
	GPR = ("ZERO", "AT", "V0", "V1", "A0", "A1", "A2", "A3", "T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "T8", "T9", "K0", "K1", "GP", "SP", "FP", "RA")
	def __init__(self, module=None):
		disc.ensure_package("unicorn", "unicorn==2.1.4"); import unicorn; from unicorn import mips_const
		self.unicorn, self.registers = unicorn, mips_const; self.machine = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); self.machine.mem_map(0, 0x200000); self.machine.mem_map(0x1F800000, 0x2000)
		self.machine.mem_write(0x10000, (ROOT / "build/disc-assets/SLES_035.56").read_bytes()[0x800:]); self.machine.mem_write(0xAD000, (COMMON / "GAME.BIN").read_bytes()[0x30:])
		if module: self.machine.mem_write(0x10A000, (COMMON / module).read_bytes()[0x30:])
		self.machine.reg_write(mips_const.UC_MIPS_REG_GP, 0x80080000 - 0x76F4); self.machine.reg_write(mips_const.UC_MIPS_REG_SP, 0x801FF000); self.general = [getattr(mips_const, "UC_MIPS_REG_" + name) for name in self.GPR]; self.gte = GTE(); self.freed = False; self.skip = set()
		for index in range(64): self.machine.mem_write(0x965D8 + 2 * index, bytes(self.machine.mem_read(0x73E4E + 4 * index * 64, 2))); self.machine.mem_write(0x968D0 + 2 * index, bytes(self.machine.mem_read(0x73E4C + 4 * index * 64, 2)))
	def ret(self, value=None):
		if value is not None: self.machine.reg_write(self.registers.UC_MIPS_REG_V0, value)
		self.machine.reg_write(self.registers.UC_MIPS_REG_PC, self.machine.reg_read(self.registers.UC_MIPS_REG_RA))
	def word(self, address): return struct.unpack("<I", self.machine.mem_read(address & 0x1FFFFFFF, 4))[0]
	def put(self, address, value, width=4): self.machine.mem_write(address & 0x1FFFFFFF, (value & ((1 << (8 * width)) - 1)).to_bytes(width, "little"))
	def step(self, machine, address, size, data):
		if address == 0x8003EB28: self.freed = True; self.ret(0); return
		if address in self.skip: self.ret(0); return
		instruction = self.word(address); opcode = instruction >> 26
		if opcode not in (0x12, 0x32, 0x3A): return
		source, target, destination = (instruction >> 21) & 31, (instruction >> 16) & 31, (instruction >> 11) & 31; gte = self.gte; read = lambda index: machine.reg_read(self.general[index])
		signed = lambda value: value - 0x10000 if value & 0x8000 else value
		if opcode == 0x32: gte.d[target] = self.word((read(source) + signed(instruction & 0xFFFF)) & 0xFFFFFFFF)
		elif opcode == 0x3A: self.put((read(source) + signed(instruction & 0xFFFF)) & 0xFFFFFFFF, gte.d[target])
		elif instruction & 0x02000000: gte.execute(instruction & 0x1FFFFFF)
		elif source == 0: machine.reg_write(self.general[target], gte.d[destination])
		elif source == 2: machine.reg_write(self.general[target], gte.c[destination])
		elif source == 4: gte.d[destination] = read(target)
		elif source == 6: gte.c[destination] = read(target)
		else: raise ValueError("Unsupported COP2 move")
		machine.reg_write(self.registers.UC_MIPS_REG_PC, address + 4)
	def reset(self, seed):
		self.machine.mem_write(0x150000, bytes(0x400)); self.put(0x1F800050, self.LIST_RECORDS); self.put(0x1F80004C, self.LIST_POLYGONS); self.put(0x1F800048, self.TABLE); self.put(0x1F800000, seed); self.put(0x1F800004, 0, 1); self.put(0x1F80000A, 0, 1); self.put(0x1F800012, 0x7FFF, 2); self.put(0x1F800006, 0, 2); self.put(0x1F8000B5, 0, 1); self.freed = False
		for index, value in enumerate((0x1000, 0, 0x1000, 0, 0x1000, 0, 0, 1024)): self.put(0x1F800014 + 4 * index, value)
		self.gte.c[26], self.gte.c[24], self.gte.c[25], self.gte.c[27], self.gte.c[28] = 1024, 0, 0, 0, 0
		for index, value in enumerate((0x1000, 0, 0x1000, 0, 0x1000, 0, 0, 1024)): self.gte.c[index] = value
	def call(self, function, arguments=()):
		for index, value in enumerate(arguments): self.machine.reg_write(self.registers.UC_MIPS_REG_A0 + index, value)
		self.machine.reg_write(self.registers.UC_MIPS_REG_RA, 0x80000800); handle = self.machine.hook_add(self.unicorn.UC_HOOK_CODE, self.step, begin=0x80000000, end=0x80200000); self.machine.emu_start(function, 0x80000800, count=5000000); self.machine.hook_del(handle)
		if self.machine.reg_read(self.registers.UC_MIPS_REG_PC) != 0x80000800: raise ValueError("Native code did not return")
		return self.machine.reg_read(self.registers.UC_MIPS_REG_V0)
	def polygons(self, render_records=False):
		"""Polygon packets (GP0 0xE1 tpage words, 0x38/0x3A gouraud quads) written to the polygon list since reset, including the record list through the SLES renderer 0x800390EC when requested; both lists are cleared afterwards."""
		records = []
		if render_records:
			end_records = self.word(0x1F800050); pointer = self.LIST_RECORDS; layout = []
			while pointer < end_records:
				command = (self.word(pointer + 4) >> 24) & 0xFC; stride = 0x28 if command == 0x2C else 0x18 if command in (0xF0, 0xF4) else 0x20 if command == 0xF8 else 0
				if not stride: raise ValueError(f"Unsupported native record {command:#x}")
				layout.append((pointer, command)); pointer += stride
			self.call(0x800390EC)
			for pointer, command in layout:
				if command == 0x2C and self.word(pointer) >> 24 == 9: records.append([self.word(pointer + 4 * index) for index in range(1, 10)])
		pointer, end, result, blend = self.LIST_POLYGONS, self.word(0x1F80004C), [], 0
		while pointer < end:
			tag = self.word(pointer); count = tag >> 24; words = [self.word(pointer + 4 + 4 * index) for index in range(count)]; pointer += 4 + 4 * count
			if words and words[0] >> 24 == 0xE1: blend = (words[0] >> 5) & 3
			elif words and words[0] >> 24 in (0x38, 0x3A) and count == 8:
				signed = lambda value: value - 0x10000 if value & 0x8000 else value
				result.append({"blend": blend, "semi": bool(words[0] >> 25 & 1), "colors": [[words[2 * index] & 255, (words[2 * index] >> 8) & 255, (words[2 * index] >> 16) & 255] for index in range(4)], "vertices": [[signed(words[2 * index + 1] & 0xFFFF), signed(words[2 * index + 1] >> 16)] for index in range(4)]})
			elif words and words[0] >> 24 in (0x3C, 0x3E) and count == 12:
				signed = lambda value: value - 0x10000 if value & 0x8000 else value
				result.append({"blend": (words[5] >> 21) & 3, "semi": bool(words[0] >> 25 & 1), "tpage": (words[5] >> 16) & 0x1F, "clut": words[2] >> 16, "colors": [[words[3 * index] & 255, (words[3 * index] >> 8) & 255, (words[3 * index] >> 16) & 255] for index in range(4)], "vertices": [[signed(words[3 * index + 1] & 0xFFFF), signed(words[3 * index + 1] >> 16)] for index in range(4)], "uvs": [[words[3 * index + 2] & 255, (words[3 * index + 2] >> 8) & 255] for index in range(4)]})
			else: raise ValueError(f"Unsupported native packet {words[0] >> 24:#x}")
		for words in records:
			signed = lambda value: value - 0x10000 if value & 0x8000 else value
			result.append({"blend": (words[4] >> 21) & 3, "semi": bool(words[0] >> 25 & 1), "tpage": (words[4] >> 16) & 0x1F, "clut": words[2] >> 16, "colors": [[words[0] & 255, (words[0] >> 8) & 255, (words[0] >> 16) & 255]] * 4, "vertices": [[signed(words[1 + 2 * index] & 0xFFFF), signed(words[1 + 2 * index] >> 16)] for index in range(4)], "uvs": [[words[2 + 2 * index] & 255, (words[2 + 2 * index] >> 8) & 255] for index in range(4)]})
		self.put(0x1F80004C, self.LIST_POLYGONS); self.put(0x1F800050, self.LIST_RECORDS); return result
def capture_effect(module, init, update, setup=(), seeds=range(1, 7), state=0x64, skip=()):
	"""Runs an original effect actor (init state, then the update state until it frees itself) once per random seed and returns the polygon packets of every drawn frame."""
	machine = NativeMachine(module); machine.skip = set(skip); actor = 0x80150000; result = []
	for seed in seeds:
		machine.reset(0x12345678 * seed & 0xFFFFFFFF or 1)
		for offset, value, width in setup: machine.put(actor + offset, value, width)
		machine.call(init, (actor, actor + state)); frames = [machine.polygons(True)]
		while True:
			machine.call(update, (actor, actor + state))
			if machine.freed: break
			frames.append(machine.polygons(True))
		result.append(frames)
	return result
def spread_buster_extension(built, output_dir):
	"""Spread Buster (module PL00R0D): a fan of Buster-style bullets and the module's hit sparks (effect class 0x15)."""
	R, G = built["image"], built["game"]
	if R.word(0x8010A004) != 0x27BDFFE0 or R.imm(0x8010A3E8) != 0x108 or R.pair(0x8010A668, 0x8010A66C) != 0x2EC0C0C0 or R.pair(0x8010A680, 0x8010A684) != 0x2E606060: raise ValueError("Spread Buster module differs")
	vram, _ = world.textures(COMMON / "GAME.BIN"); uv_word, tpage_word, tpage_add = R.pair(0x8010A670, 0x8010A674), R.pair(0x8010A678, 0x8010A67C), R.pair(0x8010A68C, 0x8010A704); clut, u, v = uv_word >> 16, uv_word & 255, (uv_word >> 8) & 255
	page = ui.decode_page(vram, (tpage_word >> 16) & 0x1F, clut, False); pixels = ui.crop(page, u, v, 32, 32); additive = bytearray(pixels)
	for offset in range(3, len(additive), 4): additive[offset] = 255 if additive[offset] else 0
	write_output(output_dir / "weapon_0e_bullet.png", world.png(32, 32, pixels)); write_output(output_dir / "weapon_0e_bullet_add.png", world.png(32, 32, additive))
	impact = capture_effect("PL00R0D.BIN", 0x8010A910, 0x8010AA34, ((6, 0, 1),))
	return {"bullet": {"source": "PL00R0D 0x8010A104 (spawn) / 0x8010A490 (flight) / 0x8010A660 (sprite records)", "children": {"base": R.imm(0x8010A178), "perSpecialFactor": 1 << R.shift(0x8010A174), "rule": "base + factor * (special level > 0) children plus the firing actor itself"}, "yawStepShift": R.shift(0x8010A38C), "yawIndexOffset": "child index - 1 - (special level > 0), 4096 units per turn", "speedRaw": -R.imm(0x8010A214), "substepsPerTick": R.imm(0x8010A59C), "launchSound": R.imm(0x8010A3E8),
		"sprite": {"normal": "weapon_0e_bullet.png", "additive": "weapon_0e_bullet_add.png", "tpageNormal": hex(tpage_word >> 16), "tpageAdditive": hex(tpage_add >> 16), "clut": hex(clut), "uv": [u, v, 32, 32], "colorNormal": R.pair(0x8010A668, 0x8010A66C) & 0xFFFFFF, "colorAdditive": R.pair(0x8010A680, 0x8010A684) & 0xFFFFFF, "sizeRaw": R.imm(0x8010A6D8), "spin": "(frame & 7) << 8 of 4096 per turn"}, "muzzle": "player cache +0x4B0 (Bone_04 joint, as the hose nozzle)", "hit": "stat range = lifetime in ticks, stat attack = damage, two movement sub-steps per tick (0x8010A490)"},
		"impact": {"source": "PL00R0D 0x8010A8D4 states 0x8010A910 / 0x8010AA34, drawn by 0x8010AA78: eight gouraud sparks per frame (GP0 0x3A), eight frames, run unchanged with projection replaced by a fixed centre; offsets are raw 1/256-unit view-plane distances", "variants": impact, "spawn": "dispatcher 0x8010A0B8: hit state 2 registers the hit (0x8010A730) and spawns class 0x15 variant 0; expiry (state 3) spawns variant 1 (flash light only)"}}
EXPLOSION_SKIP = (0x80016B50, 0x800471F0, 0x800203F4, 0x800B786C, 0x800B18A4, 0x800BFF20, 0x80042704)
def export_effect_pages(effects, output_dir):
	"""Writes the GAME VRAM pages (with their CLUT) that textured effect polygons sample and tags every polygon with its page file name."""
	vram, _ = world.textures(COMMON / "GAME.BIN"); names = {}
	for variants in effects:
		for frames in variants:
			for frame in frames:
				for polygon in frame:
					if "uvs" not in polygon: continue
					name = f"effect_page_{polygon['tpage']:02x}_{polygon['clut']:04x}.png"
					if name not in names: names[name] = None; write_output(output_dir / name, world.png(256, 256, ui.decode_page(vram, polygon["tpage"], polygon["clut"], False)))
					polygon["page"] = name; del polygon["tpage"], polygon["clut"]
	return sorted(names)
def homing_missile_extension(built, output_dir):
	"""Homing Missile (module PL00R05): flight and steering constants, the smoke trail (GAME class 6) and the explosion (GAME class 7)."""
	R, G = built["image"], built["game"]
	if R.word(0x8010A004) != 0x27BDFFE0 or R.imm(0x8010A208) != -0x100 or R.imm(0x8010A558) != -0x40 or R.imm(0x8010A570) != -0x600 or R.imm(0x8010A2B0) != 0xBF or R.imm(0x8010A4D4) != 0x40 or R.imm(0x8010A35C) != 4: raise ValueError("Homing Missile module differs")
	if G.pair(0x800D2E6C, 0x800D2E74) != 0x3A343434 or G.pair(0x800D2E84, 0x800D2E8C) != 0x3A363636 or G.pair(0x800D3284, 0x800D3288) != 0xFFFDFDFE or G.imm(0x800D2D30) != 0x1B or G.imm(0x800D2D38) != 0x1A: raise ValueError("Trail renderer differs")
	explosion = capture_effect(None, 0x800D331C, 0x800D3448, ((6, 1, 1), (0xC, R.imm(0x8010A6FC), 2)), range(1, 5), 0x94, EXPLOSION_SKIP); pages = export_effect_pages([explosion], output_dir)
	return {"bullet": {"source": "PL00R05 0x8010A114 (spawn) / 0x8010A3D0 (flight) / 0x8010A694 (explosion spawn), steering GAME 0x800CF1AC", "launchSound": R.imm(0x8010A2B0), "initialSpeedRaw": -R.imm(0x8010A208), "accelerationRaw": -R.imm(0x8010A558), "maximumSpeedRaw": -R.imm(0x8010A570), "substepsPerTick": R.imm(0x8010A544), "turnLimit": R.imm(0x8010A4D4), "turnDivisorShift": R.shift(0x8010A4F8), "steering": {"kind": "ramp", "armDelayBase": R.imm(0x8010A35C), "armedTurnShift": 1, "pitchFactor": 2, "limit": R.imm(0x8010A4D4), "divisorShift": R.shift(0x8010A4F8)}, "rule": "armed after 4 - special ticks; the turn accumulator gains special + 1 per tick up to the limit and the steering rate is accumulator >> 2, doubled once armed, pitch twice the yaw rate", "damageStat": "attack stat on contact, halved when game byte 0x8009C7FE is 4"},
		"trail": {"kind": "ribbon", "source": "GAME 0x800D2C10 class 6 effect following the missile", "history": G.imm(0x800D2D30), "historyCap": G.imm(0x800D2D38), "headScale": [G.shift(0x800D2EB0), G.imm(0x800D2EB8)], "segmentScale": [2, 1], "fade": G.imm(0x800D2FC8), "colorNewEnd": G.pair(0x800D2E84, 0x800D2E8C) & 255, "colorOldEnd": G.pair(0x800D2E6C, 0x800D2E74) & 255, "colorStep": 2, "blend": 1, "rule": "newest to oldest, four gouraud quads per segment (corner-centre wedges of the swept square), half size head (variant << 4 | 8) then (2 * variant + 1) * (16 - remaining / 2), colours newest 0x34 to 0x36 fading 2 per segment"},
		"explosion": {"source": "GAME 0x800D32E0 class 7 effect, run unchanged; the missile spawns variant 1 with size (attack level << 4) + 0x80", "sizeBase": R.imm(0x8010A6FC), "sizeShift": R.shift(0x8010A6F8), "hitDamageBase": R.imm(0x8010A710), "hitDamageShift": R.shift(0x8010A70C), "sound": G.imm(0x800D33A4), "ticks": len(explosion[0]), "area": "each tick damages actors inside (size * (16 - counter)) >> 5 raw units", "pages": pages, "variants": explosion}}
def capture_sprite_trail(owner_steps=12):
	"""GAME class 5 effect (0x800D2884): eight history puffs drawn as textured sprite records; with a stationary owner every history entry sits at the centre, so the quads of one steady-state frame are the puffs from newest to oldest."""
	machine = NativeMachine(None); machine.reset(1); effect, owner = 0x80150000, 0x80151000; machine.machine.mem_write(owner & 0x1FFFFFFF, bytes(0x200)); machine.put(owner, 1, 1); machine.put(effect + 0xC, owner)
	machine.call(0x800D28E0, (effect, effect + 0x64)); frame = []
	for step in range(owner_steps): machine.call(0x800D2950, (effect, effect + 0x64)); frame = machine.polygons(True)
	return frame
def hyper_shell_extension(built, output_dir):
	"""Hyper Shell (module PL00R04): accelerating shell with weak homing, proximity fuse, sprite puff trail (GAME class 5) and the class 7 explosion."""
	R, G = built["image"], built["game"]
	if R.word(0x8010A104) != 0x27BDFFC0 or R.imm(0x8010A278) != -0x180 or R.imm(0x8010A728) != -0x40 or R.imm(0x8010A740) != -0xA00 or R.imm(0x8010A640) != 4 or R.imm(0x8010A3EC) != 0xBE or R.imm(0x8010A714) != 3: raise ValueError("Hyper Shell module differs")
	trail = capture_sprite_trail(); explosion = capture_effect(None, 0x800D331C, 0x800D3448, ((6, 1, 1), (0xC, R.imm(0x8010A820), 2)), range(1, 5), 0x94, EXPLOSION_SKIP); pages = export_effect_pages([[[trail]], explosion], output_dir)
	return {"bullet": {"source": "PL00R04 0x8010A104 (spawn) / 0x8010A530 (flight) / 0x8010A7B8 (hit)", "launchSound": R.imm(0x8010A3EC), "initialSpeedRaw": -R.imm(0x8010A278), "accelerationRaw": -R.imm(0x8010A728), "maximumSpeedRaw": -R.imm(0x8010A740), "substepsPerTick": R.imm(0x8010A714), "steering": {"kind": "fixed", "yawRate": R.imm(0x8010A640), "pitchFactor": 2, "delayTicks": R.imm(0x8010A494), "fuseDistanceRaw": 0x400}, "rule": "steers at a fixed rate toward the lock-on point after the delay when a target is locked; once the distance to the target stops shrinking inside 0x400 raw units the shell detonates"},
		"trail": {"kind": "sprites", "source": "GAME 0x800D287C class 5", "history": 8, "frames": trail},
		"explosion": {"source": "GAME 0x800D32E0 class 7 effect, run unchanged; the shell spawns variant 1 with size (attack level << 5) + 0xC0", "sizeBase": R.imm(0x8010A820), "sizeShift": R.shift(0x8010A81C), "hitDamageBase": R.imm(0x8010A834), "hitDamageShift": R.shift(0x8010A830), "sound": G.imm(0x800D33A4), "ticks": len(explosion[0]), "pages": pages, "variants": explosion}}
def export_special_weapon(weapon, output_dir=None):
	"""Per-weapon arm, animations, firing timeline, tank and actor/effect data of a special weapon module."""
	output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/weapons"; library = f"weapon_{weapon:02x}"; built = export_weapon_arm(weapon, output_dir, library, library + ".glb", f"Weapon{weapon:02X}Arm"); G = built["game"]
	row = [G.byte(0x800DC978 + weapon * 8 + index) for index in range(8)]; tank = struct.unpack_from("<3H", G.data, G.offset(0x800DCA08 + weapon * 8)); clip = built["clips"][0]
	manifest = {"schema": 1, "weapon": weapon, "library": library, "model": library + ".glb", "arm": built["arm"], "libraryUse": "Load the GLB's animation library as its name; while the weapon is active resolve controls 96/97 to library/clip_096(_upper) and clip_097(_upper).",
		"timeline": {"handler": hex(G.word(0x800DCD08 + weapon * 4)), "startPose": row[0], "firePose": row[1], "endPose": row[2], "rapidGate": row[3], "fireWhileMoving": row[4], "actorClass": row[7], "clip": clip["name"], "clipTicks": sum(item["durationTicks"] for item in clip["records"]), "source": "GAME 0x800CE808 states: fire at pose firePose + rapid stat, finish at endPose, restart while the button is held"},
		"tank": {"refillPerTick": tank[0], "costPerShot": tank[1], "capacity": tank[2], "source": "GAME 0x800DCA08 record (player +0x196, +0x198, +0x194); the energy stat is the reserve at +0x190/+0x192 drained by refills (GAME 0x800CF5F4)"}}
	manifest.update(WEAPON_EXTENSIONS[weapon](built, output_dir)); write_output(output_dir / (library + ".json"), json.dumps(manifest, separators=(",", ":")) + chr(10), encoding="utf-8"); return manifest
WEAPON_EXTENSIONS = {5: hyper_shell_extension, 6: homing_missile_extension, 14: spread_buster_extension}

# ---- player_effects ----
# Export the player's landing dust ring (GAME class-7 effect spawned by the airborne landing substate) as landing_ring.png and landing_ring.json.
def export_player_effects(output_dir=None):
	common = ROOT / "build/disc-assets/COMMON"; output_dir = Path(output_dir) if output_dir else ROOT / "assets/player/effects"; output_dir.mkdir(parents=True, exist_ok=True)
	G = Image((common / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); S = Image((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), SLES_BASE, 0x800, "SLES")
	effect_class = G.imm(0x800CC90C)
	if G.word(0x800CC8F4) != 0x0C000000 | (0x8003E918 & 0x0FFFFFFF) >> 2 or S.word(0x8006B44C + effect_class * 4) != 0x800D952C or G.pair(0x800D9530, 0x800D953C) != 0x800DD954: raise ValueError("Landing ring spawner/class binding differs")
	if G.word(0x800AE1DC + 6 * 4) != 0x800C6E94 or G.word(0x800C6ECC) != 0x0C000000 | (0x800CC8E0 & 0x0FFFFFFF) >> 2: raise ValueError("Airborne landing substate binding differs")
	if S.imm(0x800391E8) != 0xF8 or S.word(0x800391EC) & 0xFFFF != (0x8003985C - 0x800391F0) >> 2: raise ValueError("SLES ring record dispatch differs")
	outer, inner, texture, limits = G.pair(0x800D96C0, 0x800D96C4), G.pair(0x800D96D8, 0x800D96DC), G.pair(0x800D96C8, 0x800D96CC), G.pair(0x800D96D0, 0x800D96D4); depth_word = G.word(0x800D972C) & 0xFFFF
	u0, v0, clut, u1, v1, tpage = texture & 0xFF, (texture >> 8) & 0xFF, texture >> 16, limits & 0xFF, (limits >> 8) & 0xFF, limits >> 16; repeat_shift, step_shift = outer >> 24, depth_word & 0xFF
	elevation = lambda header, shift: ((header >> shift & 0xFF) - 0x10 + 32 & 0x3F) - 32
	vram, _ = ui.textures(common / "GAME.BIN"); width, height = u1 - u0 + 1, v1 - v0 + 1
	write_output(output_dir / "landing_ring.png", ui.png(width, height, ui.hud_crop(ui.decode_page(vram, tpage, clut, True), u0, v0, width, height)))
	data = {"source": {"spawner": "GAME 0x800CC8E0(player, 0): SLES 0x8003E918 pool record, class at +4, x/y/z = player +0x12/+0x16/+0x1A, +0xF = player +0x52 (0 -> floor probe GAME 0x800B13FC snaps y in state 0)", "update": "GAME 0x800D952C states 0x800D9568 (init, counter 1) / 0x800D9618 (counter++, free at life)", "draw": "GAME 0x800D966C: two 0xF8 ring records into *0x1F800050", "renderer": "SLES 0x8003985C (0xF8 record): annulus of quads, outer vertices coloured, inner vertices black, GP0 0x3E"},
		"class": ref(effect_class, 0x800CC90C, "GAME"), "texture": "landing_ring.png", "textureSource": {"archive": "COMMON/GAME.BIN", "tpage": hex(tpage), "clut": hex(clut), "uv": [u0, v0, width, height], "texels": texel_modes(vram, tpage, clut, u0, v0, width, height), "source": "GAME 0x800D96C8/0x800D96D0"},
		"blend": "additive (tpage 0x2F semi-transparency mode 1) for STP texels; texel * vertex rgb / 128", "sizeRaw": ref(G.imm(0x800CC988), 0x800CC988, "GAME", formula="size = sizeRaw * n / life (integer), n = 1..life-1"), "lifeTicks": ref(G.imm(0x800CC994), 0x800CC994, "GAME"),
		"rgb": {"formula": "8 * (life - n) on each channel", "source": "GAME 0x800D96E4..0x800D9700"}, "unitsPerGodot": 256,
		"rings": [{"header": hex(outer), "outerRadius": "size", "innerRadius": "(3 * size) >> 2", "outerElevation": elevation(outer, 0), "innerElevation": elevation(outer, 8)}, {"header": hex(inner), "outerRadius": "(3 * size) >> 2", "innerRadius": "size >> 1", "outerElevation": elevation(inner, 0), "innerElevation": elevation(inner, 8)}],
		"ringGeometry": {"angleUnits": 64, "angleStep": 1 << step_shift, "segments": 64 >> step_shift, "startAngle": "frame counter 0x1F800006 & 0x3F at draw (spins one unit per tick)", "elevation": "vertex y += radius * sin(elevation / 64 turn), horizontal radius *= cos(elevation); native +y is down", "uStride": ((u1 - u0) >> repeat_shift) + 1, "uSpan": (u1 - u0) >> repeat_shift, "uRepeatMask": (1 << repeat_shift) - 1, "u": "u0 + uStride * (((start + angleStep * (k + 1)) / angleStep) & uRepeatMask) .. + uSpan for segment k", "v": "outer edge v0, inner edge v1"},
		"triggers": {"state": "player state 8 substate 6 (GAME 0x800C6E94)", "stationary": {"control": ref(G.imm(0x800C6E98), 0x800C6E98, "GAME"), "pose": 0}, "moving": {"control": ref(G.imm(0x800C76C8), 0x800C76C8, "GAME"), "pose": ref(G.imm(0x800C6EA0), 0x800C6EA0, "GAME")}, "landingSound": ref(G.imm(0x800C7768), 0x800C7768, "GAME"), "takeoff": "none on dry ground; GAME 0x800C6A30/0x800C6D54 only add class 0x48 bubbles (0x800CCAE8) when player +0xBE != 0"}}
	write_output(output_dir / "landing_ring.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data

# ---- mine_effects ----
def export_mine_effects():
	output = ROOT / "assets/levels/ST0F"; vram, _ = ui.textures(ROOT / "build/disc-assets/COMMON/GAME.BIN"); page = ui.decode_page(vram, 0x2E, 0x7C10)
	write_output(output / "mine_death.png", ui.png(192, 96, ui.hud_crop(page, 0, 0, 192, 96)))
	write_output(output / "mine_smoke.png", ui.png(192, 96, ui.hud_crop(ui.decode_page(vram, 0x4E, 0x7C91), 0, 0, 192, 96)))
	write_output(output / "mine_flame.png", ui.png(32, 128, ui.hud_crop(ui.decode_page(vram, 0x2E, 0x7DD1), 192, 0, 32, 128)))
	data = {"source": {"factory": "GAME800D3CA4", "update": "GAME800D3D28", "draw": "GAME800D3FCC", "class5_spawn": "ST0F800E9B14..9B60", "class8_spawn": "ST0F800ED374..3C0", "texture_archive": "COMMON/GAME.BIN", "tpage": 46, "clut": 31760}, "tick_rate": 25, "sprite": "mine_death.png", "frames": 8, "frame_size": [48, 48], "columns": 4, "burst_interval": 2, "maximum_bursts": 4, "burst_ticks": 8, "size_base": 64, "size_random_mask": 127, "class5": {"radius_raw": 48, "vertical_offset_raw": -96, "ground_ticks": 20, "air_ticks": 8}, "class8": {"radius_raw": 128, "bone": 0, "ticks": 16}}
	data["energy"] = {"source": "ST0F800F4BC4..6788", "rgb": [192, 128, 96], "initial_radius": 3, "phase_ticks": [8, 7, "while owner refreshes", 8], "radius_growth": 2, "beam_bundles": 3, "beam_segments": 6, "cross_section": "diamond", "initial_vertices_raw": [[-2, 0, 32], [0, -2, 32], [0, 2, 32], [2, 0, 32]], "circle_sectors": 16, "renderer_adapter": "Godot floating point vertices and depth replace GTE projections and GP0 packet ordering"}
	data["smoke"] = {"record_type": "0x60", "class": 3, "callback": "ST0F800F1E2C", "profile": "0x80100FBC", "texture": "mine_smoke.png", "tpage": 78, "clut": 31889, "maximum_particles": 14, "lifetime": [48, 63], "native_blend": "subtract"}
	data["flame"] = {"record": "0x80100864", "record_type": "0xA0", "class": 19, "controller": "ST0F800FA034", "renderer": "ST0F800F25A4 / 800F28A8", "profile": "0x80101078", "texture": "mine_flame.png", "tpage": 46, "clut": 32209, "uv": [192, 0, 32, 128], "radius": 115, "height_step": 66, "layers": 8, "sectors": 16, "scroll_speed": 12, "scroll_modulus": 96, "child_interval": 3, "child_radius_add": 92, "child_vertical_speed": 48}
	write_output(output / "mine_effects.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data

def export_icefield_effects(output_dir=None):
	output = Path(output_dir) if output_dir else ROOT / "assets/levels/ST11"; G = Image((COMMON / "GAME.BIN").read_bytes(), GAME_BASE, 0x30, "GAME"); S = Image((ROOT / "build/disc-assets/SLES_035.56").read_bytes(), SLES_BASE, 0x800, "SLES"); T = Image((ROOT / "build/disc-assets/DAT/ST11T.BIN").read_bytes(), 0x800E7000, 0x30, "ST11T")
	if T.word(0x800F2150 + 12 * 4) != 0x800ED20C or S.word(0x8006B44C) != 0x800D7FD8 or S.word(0x8006B3E4 + 8 * 4) != 0x800D3CA4: raise ValueError("Icefield effect dispatch differs")
	vram, _ = ui.textures(COMMON / "GAME.BIN"); subtype = T.imm(0x800E93E4); row = 0x800DD43C + subtype * 8; tpage, clut, flags, sound = [G.half(row + i) & 65535 for i in range(0, 8, 2)]; table = G.word(0x800DD654 + subtype * 4); frames = []
	for index in range(32):
		record = table + index * 12; u, v, u1, v1 = [G.byte(record + i) for i in range(4, 8)]; width, height = u1 - u + 1, v1 - v + 1; name = f"icefield_dust_{index}.png"; write_output(output / name, ui.png(width, height, ui.hud_crop(ui.decode_page(vram, tpage, clut, True), u, v, width, height))); frames.append({"texture": name, "uv": [u, v, width, height], "rgb": rgb(G.word(record)), "duration_ticks": G.byte(record + 8) + 1, "size_add_raw": G.byte(record + 10), "size_high": G.byte(record + 11)})
		if G.byte(record + 9) == 255: break
	barrier_clut = T.pair(0x800F00C4, 0x800F00D0) >> 16; barrier_page = T.pair(0x800F00DC, 0x800F00E8) >> 16; barrier_uv = [T.imm(0x800F00D0) & 255, T.imm(0x800F00D0) >> 8, T.imm(0x800F00E8) & 255, T.imm(0x800F00E8) >> 8, T.imm(0x800F00F4) & 255, T.imm(0x800F00F4) >> 8, T.imm(0x800F00FC) & 255, T.imm(0x800F00FC) >> 8]
	import world
	stage_vram = bytearray(vram)
	for name in ("COMMON/PL00T.BIN", "DAT/ST11T.BIN", "DAT/ST11.BIN"): world.texture_uploads((ROOT / "build/disc-assets" / name).read_bytes(), stage_vram, name)
	if T.word(0x800F20A8) != 0x800EFBE8 or T.word(0x800F214C) != 0x800F20A8: raise ValueError("Icefield barrier dispatch differs")
	write_output(output / "icefield_barrier.png", ui.png(32, 32, ui.hud_crop(ui.decode_page(stage_vram, barrier_page, barrier_clut, True), 0x80, 0x80, 32, 32)))
	write_output(output / "icefield_death.png", ui.png(192, 96, ui.hud_crop(ui.decode_page(vram, 0x2E, 0x7C10, True), 0, 0, 192, 96)))
	data = {"tick_rate": 25, "units_per_world": 256, "dust": {"source": "ST11T0x800E93C0/0x800EA28C/0x800EB290 -> SLES0x8003E918 class0 subtype3; GAME0x800D7FD8/0x800D8014/0x800D80B0", "tpage": tpage, "clut": clut, "flags": flags, "sound": sound, "frame_table": hex(table), "frames": frames, "size_base_raw": {"spitter": T.imm(0x800E9488), "burrower_burst": T.imm(0x800EA320), "burrower": T.imm(0x800EB330)}, "size_random_mask": 15, "trigger": "scratchpad frame counter bit4", "geometry": "SLES0x80039234 adds0x600 to sprite angle0: full square width=sqrt(2)*size_raw"}, "death": {"source": "ST11T0x800E9558/0x800EAA94/0x800EC9C4 -> SLES0x8003E820 class8; GAME0x800D3CA4/0x800D3D28/0x800D3FCC", "texture": "icefield_death.png", "spitter": {"radius_raw": T.imm(0x800E95B4), "y_offset_raw": -T.imm(0x800E95A8), "ticks": T.imm(0x800E95BC)}, "burrower": {"radius_raw": T.imm(0x800EAAE4), "y_offset_raw": -T.imm(0x800EAAD8), "ticks": T.imm(0x800EAAEC)}, "boss": {"radius_raw": T.imm(0x800ECA20), "y_offset_raw": -T.imm(0x800ECA14), "ticks": T.imm(0x800ECA28)}}, "spit": {"source": "ST11T0x800F2150[12] -> 0x800ED20C; 0x800ED610 three0xF0 annuli -> SLES0x800393D8", "textured": False, "charge_ticks": T.imm(0x800ED258), "charge_size_step_raw": T.imm(0x800ED2D8), "flight_size_raw": T.imm(0x800ED3F8), "life_ticks": T.imm(0x800ED3F0), "colors_rgb": [rgb(T.pair(0x800ED61C, 0x800ED620)), rgb(T.pair(0x800ED64C, 0x800ED650)), rgb(T.pair(0x800ED678, 0x800ED67C))], "segments": 32, "angle_step": 2, "start_index": -16, "blend": "additive GP0 mode1 from record0x2200xxxx", "rings": [["0", "size-(size>>1)"], ["size-(size>>2)", "size-(size>>1)"], ["size", "size-(size>>2)"]]}, "translucency": {"source": "ST11T0x800EA424 calls SLES0x8003F204(actor,1,1): actor+EB=0x22 -> additive", "fade_ticks": 16, "rgb": "counter*8 per channel (packed5-bit RGB counter at actor+E6)"}, "barrier": {"source": "ST11T0x800EFBE8 class 0x28 (pool 0x60 table 0x800F20AC): init 0x800EFC24, draw 0x800EFD00 (GP0 0x2E textured semi-transparent quads, page 0x2E mode additive 0x220)", "texture": "icefield_barrier.png", "texture_uv_raw": barrier_uv, "texture_rect": [128, 128, 32, 32], "page": barrier_page, "clut": barrier_clut, "columns": 2, "column_start_raw": [T.imm(0x800EFDB8), T.imm(0x800EFDAC)], "column_step_raw": [T.imm(0x800EFDB0), T.imm(0x800EFDA0)], "rows": T.imm(0x800F0160), "segments": T.imm(0x800F0150), "row_step_raw": T.imm(0x800F0168), "thickness_raw": T.imm(0x800EFEA4), "random_mask": T.imm(0x800EFDF4), "cell_mask_raw": 0xFE00, "y_offset_raw": T.imm(0x800EFC4C), "z_offset_raw": T.imm(0x800EFC60)}, "trig64": [list(struct.unpack_from("<hh", S.data, S.offset(0x80073E4C + index * 64 * 4))) for index in range(64)]}
	write_output(output / "icefield_effects.json", json.dumps(data, indent=2) + "\n", encoding="utf-8"); return data

import re
# ---- Ahead-of-time recompiler: original MIPS code (SLES, GAME, stage overlays) -> GDScript units run by scripts/runner/mips_machine.gd ----
RUNNER_DIR = ROOT / "assets" / "runner"
RUNNER_HLE = ROOT / "scripts" / "runner"
RUNNER_OVERLAY_BASE, RUNNER_GAME_SIZE, RUNNER_RAM_SIZE = 0x800E7000, 0x3A000, 0x200000
RUNNER_ENGINE_ROOTS = (0x8003C894, 0x8003CAD0, 0x8003CE00, 0x8003CBD0, 0x8003CA14, 0x8003CF08, 0x8003CCE8, 0x8003D0E8, 0x8003D010, 0x800C0818, 0x800C05E0, 0x8003D1EC, 0x800B8A7C, 0x800390C4, 0x800160EC, 0x800AE328, 0x800C0284, 0x800C256C, 0x800BB0F0, 0x800D97B4, 0x800C35B0, 0x800BA374, 0x800BA48C, 0x800B0244, 0x800C042C, 0x800BDBDC, 0x800C3C84, 0x8001D858, 0x800AEB30)
RUNNER_STAGES = {"ST1D": {"overlay": "ST1DT.BIN", "source": "ST1D.BIN", "models": 0x16000}}
RUNNER_MODEL_BANK, RUNNER_ROOT_BANK = 0x80124800, 0x80154800
class MipsImage:
	"""Little-endian code and data segments (base, bytes, name) laid out at their PlayStation RAM addresses."""
	def __init__(self, overlay=None):
		self.segments = [(SLES_BASE, (ROOT / "build/disc-assets/SLES_035.56").read_bytes()[0x800:], "SLES"), (GAME_BASE, (COMMON / "GAME.BIN").read_bytes()[0x30:0x30 + RUNNER_GAME_SIZE], "GAME")]
		if overlay: self.segments.append((RUNNER_OVERLAY_BASE, (ROOT / "build/disc-assets/DAT" / overlay).read_bytes()[0x30:0x30 + RUNNER_MODEL_BANK - RUNNER_OVERLAY_BASE], "OVL"))
	def word(self, address):
		for base, data, _ in self.segments:
			if base <= address <= base + len(data) - 4: return struct.unpack_from("<I", data, address - base)[0]
	def unit(self, address):
		for base, data, name in self.segments:
			if base <= address < base + len(data): return name
	def ram(self, with_overlay=False):
		ram = bytearray(RUNNER_RAM_SIZE)
		for base, data, name in self.segments:
			if name != "OVL" or with_overlay: ram[base - 0x80000000:base - 0x80000000 + len(data)] = data
		return bytes(ram)
def mips_fields(word): return word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 6) & 31, word & 63
def mips_signed(value, bits=16):
	value &= (1 << bits) - 1
	return value - (1 << bits) if value >> (bits - 1) else value
def mips_reads_writes(word):
	"""Registers read and written by a non-branch instruction (used to order delay slots)."""
	op, rs, rt, rd, _, fn = mips_fields(word)
	if op == 0:
		if fn in (0, 2, 3): return {rt}, {rd}
		if fn in (0x10, 0x12): return set(), {rd}
		if fn in (0x11, 0x13, 8): return {rs}, set()
		if fn in (0x18, 0x19, 0x1A, 0x1B): return {rs, rt}, set()
		if fn == 9: return {rs}, {rd}
		return {rs, rt}, {rd}
	if op == 1 or op in (6, 7): return {rs}, set()
	if op == 3: return set(), {31}
	if op == 2: return set(), set()
	if op in (4, 5): return {rs, rt}, set()
	if op in (8, 9, 0xA, 0xB, 0xC, 0xD, 0xE): return {rs}, {rt}
	if op == 0xF: return set(), {rt}
	if op == 0x12: return (set(), set()) if word & 0x2000000 else ((set(), {rt}) if rs in (0, 2) else ({rt}, set()))
	if op in (0x20, 0x21, 0x23, 0x24, 0x25): return {rs}, {rt}
	if op in (0x22, 0x26): return {rs, rt}, {rt}
	if op in (0x28, 0x29, 0x2A, 0x2B, 0x2E): return {rs, rt}, set()
	if op in (0x32, 0x3A): return {rs}, set()
	return {rs, rt}, {rt}
class MipsFunction:
	def __init__(self, entry): self.entry, self.instructions, self.leaders, self.calls, self.tables, self.tails, self.unresolved, self.cop2 = entry, set(), {entry}, set(), {}, {}, [], set()
class MipsRecompiler:
	"""Finds functions by flood fill from an entry (branch and jump-table targets, delay slots) and records their calls."""
	def __init__(self, image):
		self.image, self.functions, self._calls = image, {}, None
	def call_targets(self):
		if self._calls is None:
			self._calls = set()
			for base, data, _ in self.image.segments:
				for offset in range(0, len(data) - 3, 4):
					word = struct.unpack_from("<I", data, offset)[0]
					if word >> 26 == 3: self._calls.add(((base + offset) & 0xF0000000) | ((word & 0x3FFFFFF) << 2))
		return self._calls
	def constant(self, register, position, depth=0):
		"""Value of a register at an address when it was built by lui/addiu/ori/addu in the preceding instructions."""
		if register == 0: return 0
		if depth > 4: return None
		for back in range(1, 40):
			address = position - 4 * back; word = self.image.word(address)
			if word is None: return None
			op, rs, rt, rd, _, fn = mips_fields(word)
			if op == 2 or op == 0 and fn == 8: return None
			if (op == 3 or op == 0 and fn == 9) and not (16 <= register <= 23 or register in (28, 30)): return None
			written = rd if op == 0 and fn in (0, 2, 3, 4, 6, 7, 0x10, 0x12, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2A, 0x2B) else rt if 8 <= op <= 0xF or 0x20 <= op <= 0x26 else None
			if written != register: continue
			if op == 0xF: return (word & 0xFFFF) << 16
			if op in (8, 9, 0xD):
				base = self.constant(rs, address, depth + 1)
				if base is None: return None
				return (base + mips_signed(word)) & 0xFFFFFFFF if op != 0xD else base | (word & 0xFFFF)
			if op == 0 and fn in (0x20, 0x21):
				left, right = self.constant(rs, address, depth + 1), self.constant(rt, address, depth + 1)
				return None if left is None or right is None else (left + right) & 0xFFFFFFFF
			return None
	def jump_table(self, address, register):
		"""Targets of a switch (lui/addiu table base, sltiu bound, lw, jr) or None."""
		image = self.image; load = None
		for back in range(1, 12):
			word = image.word(address - 4 * back)
			if word is None: return None
			op, rs, rt, _, _, _ = mips_fields(word)
			if op == 0x23 and rt == register: load = (address - 4 * back, rs, mips_signed(word)); break
		if load is None: return None
		position, base_register, offset = load; base = self.constant(base_register, position)
		if base is None:
			for back in range(1, 12):
				word = image.word(position - 4 * back); op, rs, rt, rd, _, fn = mips_fields(word)
				if op == 0 and fn == 0x21 and rd == base_register:
					for source in (rs, rt):
						value = self.constant(source, position - 4 * back)
						if value is not None: base = value
					break
		if base is None: return None
		base = (base + offset) & 0xFFFFFFFF; count = None
		for back in range(1, 40):
			word = image.word(position - 4 * back)
			if word is None: break
			if word >> 26 == 0xB: count = word & 0xFFFF; break
		targets = []
		while count is None and len(targets) < 64 or count is not None and len(targets) < count:
			value = image.word(base + 4 * len(targets))
			if value is None or value & 3 or image.unit(value) is None: break
			targets.append(value)
		return (base, targets) if targets and (count is None or len(targets) == count) else None
	def scan(self, entry):
		if entry in self.functions: return self.functions[entry]
		image = self.image; function = MipsFunction(entry); self.functions[entry] = function; work = [entry]
		while work:
			address = work.pop()
			while address not in function.instructions:
				word = image.word(address)
				if word is None: raise ValueError(f"code outside the image at {address:#x} (function {entry:#x})")
				function.instructions.add(address); op, rs, rt, rd, _, fn = mips_fields(word)
				if op == 0 and fn == 8:
					function.instructions.add(address + 4)
					if rs == 31: break
					table = self.jump_table(address, rs)
					if table is None: function.unresolved.append(address); break
					function.tables[address] = table
					for target in table[1]: function.leaders.add(target); work.append(target)
					break
				if op == 0 and fn == 9: function.instructions.add(address + 4); address += 8; continue
				if op in (4, 5, 6, 7) or op == 1 and rt in (0, 1):
					function.instructions.add(address + 4); target = address + 4 + mips_signed(word) * 4; function.leaders.add(target); work.append(target); address += 8; continue
				if op == 1: raise ValueError(f"linked branch at {address:#x} (function {entry:#x})")
				if op == 2:
					function.instructions.add(address + 4); target = ((address + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
					if target != entry and target in self.call_targets() and (target < entry or target > address + 0x2000 or target in self.functions): function.tails[address] = target
					else: function.leaders.add(target); work.append(target)
					break
				if op == 3: function.instructions.add(address + 4); function.calls.add(((address + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)); address += 8; continue
				if op == 0x12: function.cop2.add(word & 0x1FFFFFF if word & 0x2000000 else ("move", rs))
				address += 4
		return function
	def hardware(self, function):
		"""Why a function cannot be translated (BIOS stub, syscall, coprocessor 0, memory-mapped I/O) or None."""
		image = self.image; first, second = image.word(function.entry), image.word(function.entry + 4)
		if first is not None and first & 0xFFFF0000 == 0x240A0000 and first & 0xFFFF in (0xA0, 0xB0, 0xC0) and second == 0x01400008: return "bios"
		for address in sorted(function.instructions):
			word = image.word(address); op, rs, _, _, _, fn = mips_fields(word)
			if op == 0 and fn == 12: return "syscall"
			if op == 0x10: return "cop0"
			if op in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x32, 0x3A) and rs:
				base = self.constant(rs, address)
				if base is not None and 0x1F801000 <= (base + mips_signed(word)) & 0x1FFFFFFF < 0x1F810000: return "io"
class MipsEmitter:
	"""Writes one GDScript method per recovered function: registers are R[n] (signed 32-bit, R[32] HI, R[33] LO), RAM a PackedByteArray, blocks a binary dispatch over pc."""
	def __init__(self, image, unit_of, hle, trace=False): self.image, self.unit_of, self.hle, self.trace = image, unit_of, hle, trace
	@staticmethod
	def reg(number): return "0" if number == 0 else f"R[{number}]"
	def index(self, base, offset): return f"0x{offset & 0x9FFFFF:X}" if base == 0 else (f"(R[{base}] + {offset}) & 0x9FFFFF" if offset else f"R[{base}] & 0x9FFFFF")
	def pointer(self, base, offset): return f"(R[{base}] + {offset})" if base else str(offset)
	def call(self, target, unit):
		if target in self.hle: return f"hle.h_{target:08X}()"
		owner = self.unit_of(target)
		return f"miss(0x{target:X})" if owner is None else (f"f_{target:08X}()" if owner == unit else f"{owner}.f_{target:08X}()")
	def simple(self, word, address):
		op, rs, rt, rd, shift, fn = mips_fields(word); immediate = mips_signed(word); R = self.reg; lines = []
		def put(number, expression):
			if number: lines.append(f"R[{number}] = {expression}")
		def move(number, base, extra): put(number, f"{R(base)} {extra}" if extra else R(base))
		if op == 0:
			if word == 0: return lines
			if fn == 0: put(rd, f"{R(rt)} << {shift}" if shift else R(rt))
			elif fn == 2: put(rd, f"({R(rt)} & 0xFFFFFFFF) >> {shift}" if shift else R(rt))
			elif fn == 3: put(rd, f"{R(rt)} >> {shift}" if shift else R(rt))
			elif fn == 4: put(rd, f"{R(rt)} << ({R(rs)} & 31)")
			elif fn == 6: put(rd, f"({R(rt)} & 0xFFFFFFFF) >> ({R(rs)} & 31)")
			elif fn == 7: put(rd, f"{R(rt)} >> ({R(rs)} & 31)")
			elif fn in (0x20, 0x21): put(rd, f"{R(rs)} + {R(rt)}" if rs and rt else R(rs) if rt == 0 else R(rt))
			elif fn in (0x22, 0x23): put(rd, f"{R(rs)} - {R(rt)}" if rt else R(rs))
			elif fn == 0x24: put(rd, f"{R(rs)} & {R(rt)}")
			elif fn == 0x25: put(rd, f"{R(rs)} | {R(rt)}" if rs and rt else R(rs) if rt == 0 else R(rt))
			elif fn == 0x26: put(rd, f"{R(rs)} ^ {R(rt)}")
			elif fn == 0x27: put(rd, f"~({R(rs)} | {R(rt)})")
			elif fn == 0x2A: put(rd, f"1 if {R(rs)} < {R(rt)} else 0")
			elif fn == 0x2B: put(rd, f"1 if ({R(rs)} & 0xFFFFFFFF) < ({R(rt)} & 0xFFFFFFFF) else 0")
			elif fn == 0x10: put(rd, "R[32]")
			elif fn == 0x12: put(rd, "R[33]")
			elif fn == 0x11: lines.append(f"R[32] = {R(rs)}")
			elif fn == 0x13: lines.append(f"R[33] = {R(rs)}")
			elif fn == 0x18: lines += [f"p = {R(rs)} * {R(rt)}", "R[33] = p", "R[32] = p >> 32"]
			elif fn == 0x19: lines += [f"p = ({R(rs)} & 0xFFFFFFFF) * ({R(rt)} & 0xFFFFFFFF)", "R[33] = p", "R[32] = p >> 32"]
			elif fn == 0x1A: lines.append(f"div({R(rs)}, {R(rt)})")
			elif fn == 0x1B: lines.append(f"divu({R(rs)}, {R(rt)})")
			elif fn == 0x0C: lines.append(f"hle.syscall({(word >> 6) & 0xFFFFF})")
			elif fn != 0x0D: raise ValueError(f"special opcode {fn:#x} at {address:#x}")
		elif op in (8, 9): put(rt, f"{R(rs)} + {immediate}" if rs else str(immediate))
		elif op == 0xA: put(rt, f"1 if {R(rs)} < {immediate} else 0")
		elif op == 0xB: put(rt, f"1 if ({R(rs)} & 0xFFFFFFFF) < {immediate & 0xFFFFFFFF} else 0")
		elif op == 0xC: put(rt, f"{R(rs)} & 0x{word & 0xFFFF:X}")
		elif op == 0xD: put(rt, f"{R(rs)} | 0x{word & 0xFFFF:X}" if rs else f"0x{word & 0xFFFF:X}")
		elif op == 0xE: put(rt, f"{R(rs)} ^ 0x{word & 0xFFFF:X}")
		elif op == 0xF: put(rt, str(mips_signed((word & 0xFFFF) << 16, 32)))
		elif op == 0x20: put(rt, f"ram.decode_s8({self.index(rs, immediate)})")
		elif op == 0x24: put(rt, f"ram[{self.index(rs, immediate)}]")
		elif op == 0x21: put(rt, f"ram.decode_s16({self.index(rs, immediate)})")
		elif op == 0x25: put(rt, f"ram.decode_u16({self.index(rs, immediate)})")
		elif op == 0x23: put(rt, f"ram.decode_s32({self.index(rs, immediate)})")
		elif op == 0x22 and rt: lines.append(f"R[{rt}] = lwl({self.pointer(rs, immediate)}, {R(rt)})")
		elif op == 0x26 and rt: lines.append(f"R[{rt}] = lwr({self.pointer(rs, immediate)}, {R(rt)})")
		elif op == 0x28: lines.append(f"ram[{self.index(rs, immediate)}] = {R(rt)} & 255")
		elif op == 0x29: lines.append(f"ram.encode_s16({self.index(rs, immediate)}, {R(rt)})")
		elif op == 0x2B: lines.append(f"ram.encode_s32({self.index(rs, immediate)}, {R(rt)})")
		elif op == 0x2A: lines.append(f"swl({self.pointer(rs, immediate)}, {R(rt)})")
		elif op == 0x2E: lines.append(f"swr({self.pointer(rs, immediate)}, {R(rt)})")
		elif op == 0x12:
			if word & 0x2000000: lines.append(f"gte.cmd(0x{word & 0x1FFFFFF:X})")
			elif rs == 0: put(rt, f"gte.mfc2({rd})")
			elif rs == 2: put(rt, f"gte.cfc2({rd})")
			elif rs == 4: lines.append(f"gte.mtc2({rd}, {R(rt)})")
			elif rs == 6: lines.append(f"gte.ctc2({rd}, {R(rt)})")
			else: raise ValueError(f"coprocessor 2 move {rs:#x} at {address:#x}")
		elif op == 0x32: lines.append(f"gte.mtc2({rt}, ram.decode_s32({self.index(rs, immediate)}))")
		elif op == 0x3A: lines.append(f"ram.encode_s32({self.index(rs, immediate)}, gte.mfc2({rt}))")
		elif op not in (0x22, 0x26): raise ValueError(f"opcode {op:#x} at {address:#x}")
		return lines
	def condition(self, word):
		op, rs, rt, _, _, _ = mips_fields(word); R = self.reg
		return {4: f"{R(rs)} == {R(rt)}" if rs != rt else "true", 5: f"{R(rs)} != {R(rt)}", 6: f"{R(rs)} <= 0", 7: f"{R(rs)} > 0"}.get(op) or (f"{R(rs)} < 0" if rt == 0 else f"{R(rs)} >= 0")
	def method(self, function, unit):
		image = self.image; leaders = sorted(function.leaders); blocks = {}
		for leader in leaders:
			lines = []; address = leader
			while True:
				word = image.word(address); op, rs, rt, rd, _, fn = mips_fields(word); following = None
				if op == 0 and fn == 8:
					slot = self.simple(image.word(address + 4), address + 4)
					if rs == 31: lines += slot + ["return"]; break
					if address not in function.tables: lines += [f"miss(0x{address:X})", "return"]; break
					lines += [f"t = R[{rs}] & 0xFFFFFFFF"] + slot + ["pc = t", "continue"]; break
				if op == 0 and fn == 9:
					lines.append(f"t = R[{rs}] & 0xFFFFFFFF")
					if rd: lines.append(f"R[{rd}] = {mips_signed(address + 8, 32)}")
					lines += self.simple(image.word(address + 4), address + 4) + ["jalr(t)"]; following = address + 8
				elif op == 3:
					target = ((address + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
					lines += [f"R[31] = {mips_signed(address + 8, 32)}"] + self.simple(image.word(address + 4), address + 4) + [self.call(target, unit)]; following = address + 8
				elif op == 2:
					lines += self.simple(image.word(address + 4), address + 4)
					lines += [self.call(function.tails[address], unit), "return"] if address in function.tails else [f"pc = 0x{((address + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2):X}", "continue"]; break
				elif op in (4, 5, 6, 7) or op == 1 and rt in (0, 1):
					target = address + 4 + mips_signed(word) * 4; slot = image.word(address + 4); condition = self.condition(word)
					if (mips_reads_writes(slot)[1] & mips_reads_writes(word)[0]) - {0}: lines.append("c = " + condition); condition = "c"
					lines += self.simple(slot, address + 4)
					if condition == "true": lines += [f"pc = 0x{target:X}", "continue"]; break
					lines += [f"if {condition}:", f"\tpc = 0x{target:X}", "\tcontinue"]; following = address + 8
				else: lines += self.simple(word, address); following = address + 4
				if following in function.leaders: lines += [f"pc = 0x{following:X}", "continue"]; break
				address = following
			blocks[leader] = lines
		text = "\n".join("\n".join(lines) for lines in blocks.values()); head = [declaration for pattern, declaration in ((r"\bp = ", "var p := 0"), (r"\bt = ", "var t := 0"), (r"\bc = ", "var c := false")) if re.search(pattern, text)]
		out = [f"func f_{function.entry:08X}() -> void:"] + ([f"\ttrace(0x{function.entry:X})"] if self.trace else []) + ["\t" + line for line in head]
		if len(leaders) == 1 and "continue" not in text:
			out += ["\t" + line for line in blocks[leaders[0]]]
			if blocks[leaders[0]][-1] != "return": out.append("\treturn")
			return "\n".join(out)
		out += [f"\tvar pc := 0x{function.entry:X}", "\tvar guard := 0", "\twhile true:", "\t\tguard += 1", "\t\tif guard > 4000000:", "\t\t\tmiss(0xBAD00000 | pc & 0xFFFFF)", "\t\t\treturn"]
		def tree(low, high, indent):
			if high - low == 1: out.extend(indent + line for line in blocks[leaders[low]]); return
			middle = (low + high) // 2; out.append(f"{indent}if pc < 0x{leaders[middle]:X}:"); tree(low, middle, indent + "\t"); out.append(indent + "else:"); tree(middle, high, indent + "\t")
		tree(0, len(leaders), "\t\t")
		return "\n".join(out)
def runner_hle_addresses(directory=None):
	"""Addresses of the original functions replaced by h_XXXXXXXX methods in scripts/runner/hle*.gd."""
	found = set()
	for path in sorted(Path(directory or RUNNER_HLE).glob("hle*.gd")): found |= {int(match, 16) for match in re.findall(r"^func h_([0-9A-F]{8})\(", path.read_text(encoding="utf-8"), re.M)}
	return found
def runner_overlay_entries(recompiler):
	"""Function entries of a stage overlay: after each return, stack-frame prologues, call targets and every code pointer."""
	image = recompiler.image; base, data, _ = next(segment for segment in image.segments if segment[2] == "OVL"); words = [struct.unpack_from("<I", data, offset)[0] for offset in range(0, len(data) - 3, 4)]
	returns = [base + 4 * index for index, word in enumerate(words) if word == 0x03E00008]; end = returns[-1] + 8; calls = recompiler.call_targets()
	frames = {base + 4 * index for index, word in enumerate(words) if base + 4 * index < end and word & 0xFFFF8000 == 0x27BD8000}; after_return = {address + 8 for address in returns if address + 8 < end}
	explicit = {target for target in calls if base <= target < end} | runner_code_constants(image, frames | after_return)
	starts = after_return | frames | explicit
	covered, entries = set(), []
	for address in sorted(starts):
		if address in covered and address not in explicit: continue
		try: function = recompiler.scan(address)
		except ValueError: continue
		covered |= function.instructions; entries.append(address)
	return entries, end
def runner_code_constants(image, starts):
	"""Function starts referenced as data words or as lui+addiu/ori constants (callback tables and pointers stored by code)."""
	found = set()
	for base, data, _ in image.segments:
		words = struct.unpack_from(f"<{len(data) // 4}I", data); found |= {word for word in words if word in starts}
		upper = {}
		for index, word in enumerate(words):
			op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
			if op == 0xF: upper[rt] = (index, (word & 0xFFFF) << 16)
			elif op in (9, 0xD) and rs in upper and index - upper[rs][0] <= 8:
				value = (upper[rs][1] + (mips_signed(word) if op == 9 else word & 0xFFFF)) & 0xFFFFFFFF
				if value in starts: found.add(value)
	return found
def runner_engine_pointers(image):
	"""Engine functions referenced by code pointers anywhere in the images (class state tables, hook tables, constants built by code)."""
	starts = set()
	for base, data, name in image.segments:
		if name == "OVL": continue
		for offset in range(0, len(data) - 3, 4):
			word = struct.unpack_from("<I", data, offset)[0]
			if word == 0x03E00008: starts.add(base + offset + 8)
			elif word & 0xFFFF8000 == 0x27BD8000: starts.add(base + offset)
	return sorted(runner_code_constants(image, starts))
def runner_closure(recompiler, roots):
	"""Functions reachable by direct calls from the roots (HLE-replaced functions are translated too, the HLE object may call the original); hardware-bound ones are returned separately (they need an HLE method)."""
	seen, hardware, work, errors = {}, {}, list(roots), []
	while work:
		entry = work.pop()
		if entry in seen: continue
		try: function = recompiler.scan(entry)
		except ValueError as error: errors.append(str(error)); seen[entry] = None; continue
		reason = recompiler.hardware(function)
		if reason: hardware[entry] = reason; seen[entry] = None; continue
		seen[entry] = function; work.extend(call for call in function.calls if call not in seen)
	return seen, hardware, errors
def runner_stage_blobs(name, image, data=False):
	"""Decompressed stage root and model archive at the addresses the original loader fills for bank 0 (SLES 0x80026770 and 0x80023040 then publish them through scratch 0x1F800080 and 0x1F800074)."""
	source = (ROOT / "build/disc-assets/DAT" / RUNNER_STAGES[name]["source"]).read_bytes(); root = disc.decompress_section(source, 0)[0]; models = disc.decompress_section(source, RUNNER_STAGES[name]["models"])[0]
	if RUNNER_MODEL_BANK + len(models) > RUNNER_ROOT_BANK or RUNNER_ROOT_BANK + len(root) > 0x8017E000: raise ValueError(f"{name} root or model archive overflows its loader bank")
	result = {"root": {"address": RUNNER_ROOT_BANK, "size": len(root), "file": f"{name}.root.bin"}, "models": {"address": RUNNER_MODEL_BANK, "size": len(models), "file": f"{name}.models.bin"}}
	if data: result.update(root_data=root, models_data=models)
	return result
def export_runner(stages=None, output_dir=None, trace=False):
	"""Writes assets/runner: the engine unit shared by every stage, one overlay unit and image per stage, the RAM image and a manifest."""
	output = Path(output_dir) if output_dir else RUNNER_DIR; hle = runner_hle_addresses(); names = sorted(RUNNER_STAGES if not stages else [stage for stage in RUNNER_STAGES if stage in stages])
	engine, overlays, hardware, errors, manifest = {}, {}, {}, [], {"stages": {}, "hle": sorted(hle), "ram": "ram.bin"}
	for name in names:
		image = MipsImage(RUNNER_STAGES[name]["overlay"]); recompiler = MipsRecompiler(image); entries, end = runner_overlay_entries(recompiler)
		seen, found, failed = runner_closure(recompiler, entries + list(RUNNER_ENGINE_ROOTS) + runner_engine_pointers(image) + sorted(hle)); hardware.update(found); errors += failed
		unit_of = lambda address, image=image: ("engine" if image.unit(address) in ("SLES", "GAME") else "ovl") if image.unit(address) and address not in hardware else None
		emitter = MipsEmitter(image, unit_of, hle, trace); overlay = [function for function in seen.values() if function and unit_of(function.entry) == "ovl"]; overlays[name] = (emitter, overlay)
		for function in seen.values():
			if function and unit_of(function.entry) == "engine" and function.entry not in engine: engine[function.entry] = (emitter, function)
		manifest["stages"][name] = {"unit": f"{name}.gd", "image": f"{name}.bin", "base": RUNNER_OVERLAY_BASE, "functions": len(overlay), "code_end": end, **runner_stage_blobs(name, image)}
	def unit_text(items, unit):
		text = ['extends "res://scripts/runner/mips_unit.gd"', ""]
		for emitter, function in items: text += [emitter.method(function, unit), ""]
		text += ["func table(into: Dictionary) -> void:"] + [f"\tinto[0x{function.entry:X}] = f_{function.entry:08X}" for _, function in items] + [""]
		return "\n".join(text)
	write_output(output / "engine.gd", unit_text([engine[entry] for entry in sorted(engine)], "engine"), encoding="utf-8"); manifest["engine_functions"] = len(engine)
	for name, (emitter, overlay) in overlays.items(): write_output(output / f"{name}.gd", unit_text([(emitter, function) for function in sorted(overlay, key=lambda function: function.entry)], "ovl"), encoding="utf-8")
	for name in names:
		image = MipsImage(RUNNER_STAGES[name]["overlay"]); write_output(output / f"{name}.bin", next(segment[1] for segment in image.segments if segment[2] == "OVL"))
		blobs = runner_stage_blobs(name, image, True)
		for kind in ("root", "models"): write_output(output / f"{name}.{kind}.bin", blobs.pop(kind + "_data"))
	write_output(output / "ram.bin", MipsImage().ram()); write_output(output / ".gdignore", "")
	manifest["hardware"] = {f"{address:#010x}": reason for address, reason in sorted(hardware.items())}; manifest["errors"] = errors
	manifest["unresolved_jumps"] = sorted(f"{address:#010x}" for _, function in list(engine.values()) + [(emitter, function) for emitter, overlay in overlays.values() for function in overlay] for address in function.unresolved)
	write_output(output / "manifest.json", json.dumps(manifest, indent=1) + "\n", encoding="utf-8"); return manifest

def runner_testable(recompiler, entries, hardware, hle=()):
	"""Functions whose whole call tree is translated, without indirect calls or coprocessor use (they can run against Unicorn alone)."""
	verdict, image = {}, recompiler.image
	def good(entry, stack=()):
		if entry in verdict: return verdict[entry]
		function = recompiler.functions.get(entry)
		if function is None or entry in hardware or entry in hle: verdict[entry] = False; return False
		if entry in stack: return True
		if function.unresolved or function.cop2 or any(image.word(address) >> 26 == 0 and image.word(address) & 63 == 9 for address in function.instructions): verdict[entry] = False; return False
		verdict[entry] = all(good(call, stack + (entry,)) for call in function.calls); return verdict[entry]
	return sorted(entry for entry in entries if good(entry))
def runner_project(work, driver):
	"""Writes a minimal project in build/ that holds the runner scripts and a main scene running one driver script, so headless checks never start the game's autoloads."""
	import shutil
	(work / "scripts/runner").mkdir(parents=True, exist_ok=True)
	for name in ("mips_unit.gd", "mips_machine.gd", "gte.gd", "hle.gd", "runner_bridge.gd", "runner_session.gd", driver + ".gd"): shutil.copyfile(RUNNER_HLE / name, work / "scripts/runner" / name)
	(work / "project.godot").write_text(f'config_version=5\n[application]\nconfig/name="{driver}"\nrun/main_scene="res://main.tscn"\n', encoding="utf-8")
	(work / "main.tscn").write_text(f'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://scripts/runner/{driver}.gd" id="1"]\n[node name="Driver" type="Node"]\nscript = ExtResource("1")\n', encoding="utf-8")
def runner_pilot(engine, stage="ST1D", directory=None):
	"""Plays the Forbidden Island pilot (scene 0x28, the class-52 boss fight, scene 0x29) through the original code headless and returns the report the probe script writes."""
	import subprocess
	source = Path(directory) if directory else RUNNER_DIR; work = ROOT / "build" / "runner_pilot"; runner_project(work, "runner_probe"); report = work / "report.json"; report.unlink(missing_ok=True)
	completed = subprocess.run([str(engine), "--headless", "--audio-driver", "Dummy", "--path", str(work), "--", str(source), stage, str(report)], capture_output=True, text=True, timeout=3600)
	if not report.is_file(): raise RuntimeError("The engine did not write a report:\n" + completed.stdout[-2000:] + completed.stderr[-2000:])
	return json.loads(report.read_text(encoding="utf-8"))
def runner_gte_cases(rng):
	"""Random GTE register files for RTPS, RTPT, MVMVA, NCLIP, AVSZ3, AVSZ4, SQR, OP, GPF and GPL with the results of the Python GTE that NativeMachine uses (its perspective divide is exact, the engine's follows the hardware reciprocal table, so MAC0 and IR0 get a small tolerance)."""
	def pair(low, high): return (rng.randrange(low, high) & 0xFFFF) | ((rng.randrange(low, high) & 0xFFFF) << 16)
	commands = [(0x01 | (sf << 19) | (lm << 10)) for sf in (0, 1) for lm in (0, 1) for _ in range(40)] + [(0x30 | (sf << 19) | (lm << 10)) for sf in (0, 1) for lm in (0, 1) for _ in range(40)] + [(0x12 | (sf << 19) | (lm << 10) | (rng.randrange(0, 3) << 17) | (rng.randrange(0, 4) << 15) | (rng.choice((0, 1, 3)) << 13)) for sf in (0, 1) for lm in (0, 1) for _ in range(60)]
	commands += [(op | (sf << 19) | (lm << 10)) for op in (0x06, 0x2D, 0x2E, 0x28, 0x0C, 0x3D, 0x3E) for sf in (0, 1) for lm in (0, 1) for _ in range(20)]
	blob, expected = bytearray(struct.pack("<I", len(commands))), []
	for command in commands:
		c, d = [0] * 32, [0] * 32
		for index in range(5): c[index] = pair(-4096, 4096)
		c[4] = rng.randrange(-4096, 4096) & 0xFFFF
		for index in (5, 6, 7): c[index] = rng.randrange(-2000, 2000)
		for index in range(8, 13): c[index] = pair(-4096, 4096)
		for index in range(13, 16): c[index] = rng.randrange(-5000, 5000)
		for index in range(16, 21): c[index] = pair(-4096, 4096)
		c[24], c[25], c[26], c[27], c[28], c[29], c[30] = rng.randrange(-0x8000, 0x8000) << 8, rng.randrange(-0x8000, 0x8000) << 8, rng.randrange(100, 1000), rng.randrange(-0x4000, 0x4000), rng.randrange(-0x400000, 0x400000), rng.randrange(0, 0x1000), rng.randrange(0, 0x1000)
		for index in range(3): d[2 * index], d[2 * index + 1] = pair(-1500, 1500), rng.randrange(-1500, 1500) & 0xFFFF
		d[8] = rng.randrange(0, 0x1000)
		for index in (9, 10, 11): d[index] = rng.randrange(-3000, 3000) & 0xFFFF
		for index in range(12, 15): d[index] = pair(-300, 300)
		for index in range(16, 20): d[index] = rng.randrange(0, 3000)
		d[6], d[25], d[26], d[27] = rng.getrandbits(32), rng.randrange(-100000, 100000), rng.randrange(-100000, 100000), rng.randrange(-100000, 100000)
		d, c = [mips_signed(value, 32) for value in d], [mips_signed(value, 32) for value in c]; reference = GTE(); reference.d, reference.c = [value & 0xFFFFFFFF for value in d], [value & 0xFFFFFFFF for value in c]
		try: reference.execute(command & 0x1FFFFFF); expected.append([mips_signed(value, 32) for value in reference.d])
		except ValueError: expected.append(None)
		blob += struct.pack("<I", command) + struct.pack("<32i", *d) + struct.pack("<32i", *c)
	return bytes(blob), commands, expected
def runner_verify(engine, stage="ST1D", per_function=6, seed=1234, directory=None):
	"""Runs every testable translated function on random inputs in Unicorn and in the engine (headless, dummy audio) and compares registers and RAM digests."""
	import random, subprocess, hashlib, shutil
	disc.ensure_package("unicorn", "unicorn==2.1.4"); import unicorn; from unicorn import mips_const
	source = Path(directory) if directory else RUNNER_DIR; work = ROOT / "build" / "runner_verify"; manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
	if stage not in manifest["stages"]: raise ValueError(f"{stage} is not in the runner manifest; export it with the runner command first")
	image = MipsImage(RUNNER_STAGES[stage]["overlay"]); recompiler = MipsRecompiler(image); entries, _ = runner_overlay_entries(recompiler)
	seen, hardware, _ = runner_closure(recompiler, entries + list(RUNNER_ENGINE_ROOTS) + runner_engine_pointers(image) + sorted(runner_hle_addresses())); functions = runner_testable(recompiler, [entry for entry, function in seen.items() if function], hardware, runner_hle_addresses())
	runner_project(work, "runner_verify")
	arena, arena_size, rng = 0x80150000, 0x8000, random.Random(seed); base = bytearray(image.ram(True))
	for index in range(arena_size): base[arena - 0x80000000 + index] = rng.getrandbits(8)
	scratch = bytes(rng.getrandbits(8) for _ in range(0x1000))
	names = [name.upper() for name in ("zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra")]
	def signed(value): return mips_signed(value, 32)
	def random_registers():
		registers = [0] * 34
		for index in range(1, 32):
			kind = rng.random()
			registers[index] = arena + 4 * rng.randrange(0, arena_size // 4 - 0x400) if kind < 0.45 else rng.randrange(-8, 40) & 0xFFFFFFFF if kind < 0.7 else rng.randrange(0, 0x1000) if kind < 0.8 else rng.randrange(-0x8000, 0x8000) & 0xFFFFFFFF if kind < 0.9 else rng.getrandbits(32)
		registers[29], registers[28], registers[31] = 0x801FF000, 0x8007890C, 0x80000800; return registers
	def reference(address, registers):
		cpu = unicorn.Uc(unicorn.UC_ARCH_MIPS, unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN); cpu.mem_map(0, RUNNER_RAM_SIZE); cpu.mem_map(0x1F800000, 0x1000); cpu.mem_write(0, bytes(base)); cpu.mem_write(0x1F800000, scratch)
		for index in range(1, 32): cpu.reg_write(getattr(mips_const, "UC_MIPS_REG_" + names[index]), registers[index])
		try: cpu.emu_start(address, 0x80000800, count=300000)
		except unicorn.UcError: return None
		if cpu.reg_read(mips_const.UC_MIPS_REG_PC) != 0x80000800: return None
		memory = bytes(cpu.mem_read(0, RUNNER_RAM_SIZE))
		if memory[0x10000:0xE7000] != bytes(base[0x10000:0xE7000]): return None
		result = [0] + [signed(cpu.reg_read(getattr(mips_const, "UC_MIPS_REG_" + names[index]))) for index in range(1, 32)] + [signed(cpu.reg_read(mips_const.UC_MIPS_REG_HI)), signed(cpu.reg_read(mips_const.UC_MIPS_REG_LO))]
		return result, hashlib.sha256(memory).digest(), hashlib.sha256(bytes(cpu.mem_read(0x1F800000, 0x400))).digest()
	cases, expected = [], []
	for entry in functions:
		found = tries = 0
		while found < per_function and tries < per_function * 6:
			tries += 1; registers = random_registers(); result = reference(entry, registers)
			if result: found += 1; cases.append((entry, registers)); expected.append(result)
	(work / "ram_test.bin").write_bytes(bytes(base) + bytes(0x600000) + scratch[:0x400]); results = work / "results.bin"; results.unlink(missing_ok=True)
	with open(work / "cases.bin", "wb") as handle:
		handle.write(struct.pack("<I", len(cases)))
		for entry, registers in cases: handle.write(struct.pack("<I34i", entry, *[signed(value) for value in registers]))
	gte_cases, gte_commands, gte_expected = runner_gte_cases(rng); (work / "gte_cases.bin").write_bytes(gte_cases); (work / "gte_results.bin").unlink(missing_ok=True)
	completed = subprocess.run([str(engine), "--headless", "--audio-driver", "Dummy", "--path", str(work), "--", str(source), stage, str(work)], capture_output=True, text=True, timeout=3600)
	if not results.is_file() or not (work / "gte_results.bin").is_file(): raise RuntimeError("The engine did not write results:\n" + completed.stdout[-2000:] + completed.stderr[-2000:])
	data, record, failures = results.read_bytes(), 34 * 4 + 64, {}
	for index, ((entry, _), (registers, memory, pad)) in enumerate(zip(cases, expected)):
		chunk = data[index * record:(index + 1) * record]; got = list(struct.unpack_from("<34i", chunk))
		if got != registers or chunk[136:168] != memory or chunk[168:200] != pad: failures.setdefault(entry, []).append({"differences": [(number, got[number], registers[number]) for number in range(34) if got[number] != registers[number]][:6], "memory_differs": chunk[136:168] != memory, "scratch_differs": chunk[168:200] != pad, "inputs": [signed(value) for value in cases[index][1]]})
	gte_data, gte_failures = (work / "gte_results.bin").read_bytes(), {}
	for index, reference in enumerate(gte_expected):
		if reference is None: continue
		got = struct.unpack_from("<32i", gte_data, index * 128); command = gte_commands[index]
		wrong = [number for number in (7, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 25, 26, 27) if got[number] != reference[number]] + [number for number in (8, 24) if abs(got[number] - reference[number]) > 2 + abs(reference[number]) // 500]
		if wrong: gte_failures.setdefault(f"{command & 0x3F:#04x} sf{(command >> 19) & 1}", []).append(wrong)
	summary = {"stage": stage, "functions": len(functions), "cases": len(cases), "gte_cases": len(gte_expected), "gte_failures": {key: {"cases": len(value), "registers": value[0]} for key, value in gte_failures.items()}, "failed_functions": {f"{entry:#010x}": value[0] for entry, value in sorted(failures.items())}}
	return summary
def runner_pilot_cli():
	parser = argparse.ArgumentParser(description="Play the Forbidden Island scene, boss fight and ending scene through the original code (headless)")
	parser.add_argument("--engine", type=Path, required=True, help="Redot or Godot editor executable"); parser.add_argument("--stage", default="ST1D"); arguments = parser.parse_args(); print(json.dumps(runner_pilot(arguments.engine, arguments.stage), indent=1))
def runner_cli():
	parser = argparse.ArgumentParser(description="Recompile the original engine and stage overlays into GDScript units under assets/runner")
	parser.add_argument("--stage", action="append", help="limit to this stage (repeatable)"); parser.add_argument("--output", type=Path, help="write the units here instead of assets/runner"); parser.add_argument("--trace", action="store_true", help="emit a trace() call at every function entry (exploration builds)"); parser.add_argument("--overwrite", action="store_true", help="replace existing output files"); parser.add_argument("--overwrite-only", action="append", default=[], metavar="PATTERN", help="replace only existing files matching this glob relative to the repository root"); arguments = parser.parse_args(); disc.configure_overwrite(arguments.overwrite, arguments.overwrite_only)
	manifest = export_runner({stage.upper() for stage in arguments.stage or []} or None, arguments.output, arguments.trace); print(json.dumps({key: manifest[key] for key in ("engine_functions", "stages")}, indent=1)); print(f"{len(manifest['hardware'])} hardware-bound functions need an HLE method or stay unresolved")
def runner_verify_cli():
	parser = argparse.ArgumentParser(description="Differential test of the translated functions against Unicorn")
	parser.add_argument("--engine", type=Path, required=True, help="Redot or Godot editor executable"); parser.add_argument("--stage", default="ST1D"); parser.add_argument("--cases", type=int, default=6, help="random inputs per function"); parser.add_argument("--seed", type=int, default=1234)
	arguments = parser.parse_args(); summary = runner_verify(arguments.engine, arguments.stage, arguments.cases, arguments.seed); print(json.dumps(summary, indent=1))
	if summary["failed_functions"] or summary["gte_failures"]: raise SystemExit(1)

import cinematics
import ui
import world

if __name__ == '__main__':
	import sys
	commands = {'player': 'export_player', 'doors': 'doors_cli', 'npcs': 'npcs_cli', 'flutter-actors': 'flutter_actors_cli', 'stage-actors': 'stage_actors_cli', 'runner': 'runner_cli', 'runner-verify': 'runner_verify_cli', 'runner-pilot': 'runner_pilot_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
