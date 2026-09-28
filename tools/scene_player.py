"""Export stage-scoped player animation controls (0x80..) as a Godot-compatible GLB animation library.

Native path (PAL SLES_035.56 / GAME.BIN):
  * GAME 0x800CDE5C(control, start, 1) stores player(0x8008C0A0)+0xB4/+0xB5; GAME 0x800CC7E8 forwards it to
    0x800CCEBC, which latches +0xA0 (control) / +0x9C (start record).
  * SLES 0x8003F2A8 (base layer) and 0x8003F3C4 (upper layer) resolve the control record:
        control < 0x60  -> table 0x80123000, base 0x80110800 (PL00P000)
        control < 0x70  -> table 0x801246B0 (PL00R02)
        control < 0x80  -> table 0x80124600
        control >= 0x80 -> bank = *(player+0x298); table = bank + *(bank+4); index = control-0x80; base = bank
    record = base + (entry & ~3) + 4, header byte record[-4] = track index (-> player+0xA2).
  * SLES 0x8003F96C/0x8003FAD8 resolve the track: control & 0x80 -> base = *(player+0x298), track table = base+8;
    pose words = base + track_entry + frame*64.
  * player+0x298 is set by SLES 0x80023040 (called from GAME stage init 0x800BA400): it walks the block chain at
    0x80124800 (or 0x8013C800 when scratch byte 0x1F80000C != 0), i.e. the stage actor archive. A block whose first
    word has bit31 set becomes player+0x298; bit30 sets player+0x29C = block+4. Next block = block + (word & 0x3FFFFFFF).
    SLES 0x80018B08..0x80018B4C picks the same 0x80124800/0x8013C800 destination for the streamed address-0 section,
    which for ST39 is DAT/ST39.BIN section 0x3000 (type 0x0C, LZ-compressed; tools/assets.py names it ST39_03000).
"""
from __future__ import annotations
import json
import struct
import sys
from pathlib import Path

LEGENDS = Path(__file__).resolve().parent.parent
import disc
import models

DAT = LEGENDS / "build" / "disc-assets" / "DAT"
COMMON = LEGENDS / "build" / "disc-assets" / "COMMON"
OUT = LEGENDS / "assets" / "levels"
SCENE_CONTROL_BASE = 0x80


def u32(data, offset): return struct.unpack_from("<I", data, offset)[0]


def find_actor_archive(stage, types=(0x0C,)):
	"""Return (decoded payload, section offset) of the stage's address-0 type-0x0C section that starts with the bank chain."""
	source = (DAT / f"{stage}.BIN").read_bytes()
	for offset in range(0, len(source) - 0x30, 0x800):
		if u32(source, offset) not in types or any(source[offset + 0x18:offset + 0x30]) or u32(source, offset + 0x0C) != 0: continue
		try: payload, meta = disc.extract_section(source, offset)
		except ValueError: continue
		if u32(payload, 0) & 0xC0000000: return payload, offset, meta
	raise ValueError(f"{stage}.BIN has no actor archive with a native animation-bank prefix")


def walk_chain(payload):
	"""Mirror of SLES 0x80023040."""
	blocks, position = [], 0
	while position + 4 <= len(payload):
		word = u32(payload, position)
		if not word & 0xC0000000: break
		size = word & 0x3FFFFFFF
		blocks.append({"offset": position, "word": word, "size": size, "role": "player+0x298 (scene player bank)" if word & 0x80000000 else "player+0x29C (block+4)"})
		position += size
	return blocks, position


def parse_bank(payload, bank):
	size = u32(payload, bank) & 0x3FFFFFFF; control_table = u32(payload, bank + 4); first_track = u32(payload, bank + 8)
	if not 8 < first_track <= control_table < size or first_track & 3 or (control_table - 8) & 3: raise ValueError("Invalid scene player bank header")
	track_offsets = [u32(payload, bank + offset) for offset in range(8, first_track, 4)]
	first_control = u32(payload, bank + control_table)
	control_offsets = [u32(payload, bank + offset) for offset in range(control_table, first_control & ~3, 4)]
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
		target_word = u32(payload, track_file + target_index * 64) if target_index is not None else None
		offset = models.point(u32(payload, track_file + frame_index * 64), target_word, fraction)
		root_positions.extend(bones[0][axis] + offset[axis] for axis in range(3))
	samplers = [{"input": input_accessor, "output": binary.accessor(root_positions, "f", 5126, "VEC3", None), "interpolation": "LINEAR"}]
	channels = [{"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}}]
	for bone_index, node_index in enumerate(bone_node_ids):
		rotations = []
		for frame_index, target_index, fraction in samples:
			packed = u32(payload, track_file + frame_index * 64 + (bone_index + 1) * 4)
			target_word = u32(payload, track_file + target_index * 64 + (bone_index + 1) * 4) if target_index is not None else None
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
	reference = LEGENDS / "assets" / "player" / "megaman.glb"
	if reference.exists():
		data = reference.read_bytes(); document = json.loads(data[20:20 + u32(data, 12)])
		for index in bone_node_ids:
			for key in ("translation", "rotation"):
				if key in document["nodes"][index]: nodes[index][key] = document["nodes"][index][key]
	return nodes, bones, world, bone_node_ids


def export_scene_player_clips(stage, output_dir=None, types=(0x0C,)):
	stage = stage.upper(); output_dir = Path(output_dir) if output_dir else OUT / stage; output_dir.mkdir(parents=True, exist_ok=True)
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
	document = {"asset": {"version": "2.0", "generator": "tools/scene_player.py", "extras": {"stage": stage, "source": f"DAT/{stage}.BIN", "section": hex(section_offset), "bank": hex(bank)}}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
		"meshes": [{"name": "SceneBankPlaceholder", "primitives": [{"attributes": attributes, "mode": 4}]}], "skins": [{"name": "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse_bind}],
		"animations": animations, "bufferViews": binary.views, "accessors": binary.accessors, "buffers": [{"byteLength": len(binary.data)}]}
	json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8"); json_chunk += b" " * ((-len(json_chunk)) & 3)
	binary.data.extend(b"\0" * ((-len(binary.data)) & 3))
	glb = struct.pack("<4sII", b"glTF", 2, 28 + len(json_chunk) + len(binary.data)) + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk + struct.pack("<I4s", len(binary.data), b"BIN\0") + binary.data
	model_name = f"player_scene_{stage}.glb"; (output_dir / model_name).write_bytes(glb)
	manifest = {"stage": stage, "model": model_name, "library": f"scene_{stage}", "controlRange": [SCENE_CONTROL_BASE, SCENE_CONTROL_BASE + len(control_offsets) - 1],
		"animationBank": {"source": f"DAT/{stage}.BIN", "section": hex(section_offset), "sectionType": section_meta["type"], "decodedSize": section_meta["full_size"], "blockOffset": hex(bank), "blockSize": hex(bank_size), "runtimeAddress": hex(0x80124800 + bank), "alternateRuntimeAddress": hex(0x8013C800 + bank), "trackTable": "block+0x8", "controlTable": hex(control_table), "trackSlots": len(track_offsets), "controlSlots": len(control_offsets), "chain": [{**b, "offset": hex(b["offset"]), "word": hex(b["word"]), "size": hex(b["size"])} for b in blocks], "modelArchiveOffset": hex(archive_offset),
			"fps": 30, "frameStrideBytes": 64, "rotationOrder": "XYZ for all bones (base layer, upper-body mode 0)", "resolver": "SLES 0x8003F2A8/0x8003F3C4 controls>=0x80 -> *(player+0x298)+*(bank+4); SLES 0x8003F96C/0x8003FAD8 tracks -> bank+8; SLES 0x80023040 sets player+0x298", "excludedControls": excluded},
		"skeleton": {"jointCount": 15, "nodes": "MegaMan/MegaManMesh/Bone_00..Bone_14 identical to assets/player/megaman*.glb", "restSource": "PL00P000.BIN bone table; rest rotations copied from megaman.glb"},
		"clips": clips}
	(output_dir / "player_scene.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	return manifest


if __name__ == "__main__":
	for stage in sys.argv[1:] or ["ST39"]:
		result = export_scene_player_clips(stage)
		print(json.dumps({"stage": result["stage"], "clips": len(result["clips"]), "range": result["controlRange"], "excluded": result["animationBank"]["excludedControls"], "bank": result["animationBank"]["blockOffset"]}))
