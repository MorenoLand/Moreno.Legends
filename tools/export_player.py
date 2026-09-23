import json
import math
import struct
from collections import defaultdict
from pathlib import Path

from export_maps import textures, texture_page

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "build" / "disc-assets" / "COMMON"
OUTPUT = ROOT / "assets" / "player"
SCALE = 1.0 / 2048.0
PARTS = (("Body", 0x80, (0, 8, 9, 10, 12, 13)), ("Head", 0xB60, (1, 1, 1)), ("Feet", 0x1800, (11, 14)), ("Buster", 0x2220, (2, 3, 4)), ("LeftArm", 0x26F0, (5, 6, 7)))
PARENTS = (-1, 0, 0, 2, 3, 0, 5, 6, 0, 8, 9, 10, 8, 12, 13)
MATERIALS = ({"name": "Body", "clut": 0x3C00, "tpage": 5}, {"name": "Body alternate palette", "clut": 0x3C04, "tpage": 5}, {"name": "Face", "clut": 0x3C08, "tpage": 6})
ROT_MAGNITUDE = (90.0, 180.0, 360.0, 720.0)


def signed10(value):
    return value - 1024 if value & 0x200 else value


def point(value):
    factor = (1.0, 2.0, 4.0, 8.0)[value >> 30]
    x = signed10(value & 0x3FF) * SCALE * factor
    y = signed10((value >> 10) & 0x3FF) * SCALE * factor
    z = signed10((value >> 20) & 0x3FF) * SCALE * factor
    return (-x, -y, z)


def bone_point(x, y, z):
    return (-x * SCALE, -y * SCALE, z * SCALE)


def length3(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def decode_mesh(payload):
    bones = [bone_point(*struct.unpack_from("<hhh", payload, i * 6)) for i in range(15)]
    world_bones = []
    for i, p in enumerate(PARENTS):
        v = bones[i] if p < 0 else tuple(bones[i][j] + world_bones[p][j] for j in range(3))
        world_bones.append(v)
    by_material = defaultdict(lambda: {"positions": [], "normals": [], "uvs": [], "colors": [], "joints": [], "weights": []})
    visible_points = []
    muzzle = None
    source_materials = set()
    face_count = 0
    vertex_count = 0
    for part_name, part_offset, bone_indices in PARTS:
        for strip_index, bone_index in enumerate(bone_indices):
            offset = part_offset + strip_index * 0x18
            tri_count, quad_count, count, _, tri_offset, quad_offset, vertex_offset, active_offset, reference_offset = struct.unpack_from("<4B5I", payload, offset)
            if not count or vertex_offset + count * 4 > len(payload) or active_offset + count * 4 > len(payload):
                raise ValueError(f"Invalid {part_name} strip {strip_index} vertex or color range")
            if reference_offset + count * 4 > len(payload):
                raise ValueError(f"Invalid {part_name} strip {strip_index} reference color range")
            words = [struct.unpack_from("<I", payload, vertex_offset + i * 4)[0] for i in range(count)]
            if any(word >> 30 for word in words):
                raise ValueError(f"{part_name} strip {strip_index} uses an unhandled vertex scale")
            vertices = [point(word) for word in words]
            if part_name == "Buster" and strip_index == 2:
                muzzle = [(min(v[i] for v in vertices) + max(v[i] for v in vertices)) * 0.5 for i in range(3)]
                muzzle[1] = min(v[1] for v in vertices)
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
                    if material >= len(MATERIALS):
                        raise ValueError(f"Unhandled material {material} in {part_name} strip {strip_index}")
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
            for tri, uv, material in faces:
                target = by_material[material]
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


def decode_rotation(word):
    x, y, z = word & 0x3FF, (word >> 10) & 0x3FF, (word >> 20) & 0x3FF
    magnitude = ROT_MAGNITUDE[word >> 30]
    angles = (((x & 0x200) - (x & 0x1FF)) / 0x3FF * magnitude, (-(y & 0x200) + (y & 0x1FF)) / 0x3FF * magnitude, ((z & 0x200) - (z & 0x1FF)) / 0x3FF * magnitude)
    hx, hy, hz = (math.radians(value) * 0.5 for value in angles)
    sx, sy, sz = math.sin(hx), math.sin(hy), math.sin(hz)
    cx, cy, cz = math.cos(hx), math.cos(hy), math.cos(hz)
    q = (sx * cy * cz + cx * sy * sz, cx * sy * cz - sx * cy * sz, cx * cy * sz + sx * sy * cz, cx * cy * cz - sx * sy * sz)
    return (q[0], -q[1], -q[2], q[3])


def decode_animations(source, binary, bone_node_ids, bones):
    player_address = struct.unpack_from("<I", source, 0x0C)[0]
    track_bank_offset, control_bank_offset = 0x3000, 0x11800
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
    clips = []
    clip_manifest = []
    excluded = []
    valid_controls = [(slot, offset) for slot, offset in enumerate(control_offsets) if control_delta <= offset < control_end]
    for slot, offset in enumerate(control_offsets):
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
        if track_index not in tracks:
            excluded.append({"slot": slot, "reason": "missing track"})
            continue
        track_file, source_frame_count, track_offset = tracks[track_index]
        frame_indices = [source[control_pos + 4 + frame * 4] for frame in range(frame_count)]
        if any(frame_index & 0x80 for frame_index in frame_indices):
            excluded.append({"slot": slot, "reason": "unresolved high-bit control / overlay dependency", "track": track_index, "codes": sorted(set(frame_index for frame_index in frame_indices if frame_index & 0x80))})
            continue
        if any(frame_index >= source_frame_count for frame_index in frame_indices):
            excluded.append({"slot": slot, "reason": "control references an out-of-range pose frame", "track": track_index})
            continue
        times = [frame / 30.0 for frame in range(frame_count)]
        input_accessor = binary.accessor(times, "f", 5126, "SCALAR", None, True)
        samplers = []
        channels = []
        root_positions = []
        for frame_index in frame_indices:
            frame_file = track_file + frame_index * 64
            root_offset = point(struct.unpack_from("<I", source, frame_file)[0])
            root_positions.extend(tuple(bones[0][axis] + root_offset[axis] for axis in range(3)))
        root_accessor = binary.accessor(root_positions, "f", 5126, "VEC3", None)
        samplers.append({"input": input_accessor, "output": root_accessor, "interpolation": "LINEAR"})
        channels.append({"sampler": 0, "target": {"node": bone_node_ids[0], "path": "translation"}})
        for bone_index, node_index in enumerate(bone_node_ids):
            rotations = []
            for frame_index in frame_indices:
                packed = struct.unpack_from("<I", source, track_file + frame_index * 64 + (bone_index + 1) * 4)[0]
                rotations.extend(decode_rotation(packed))
            output_accessor = binary.accessor(rotations, "f", 5126, "VEC4", None)
            sampler_index = len(samplers)
            samplers.append({"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"})
            channels.append({"sampler": sampler_index, "target": {"node": node_index, "path": "rotation"}})
        name = f"clip_{slot:03d}"
        clips.append({"name": name, "samplers": samplers, "channels": channels, "extras": {"sourceControlSlot": slot, "sourceControlOffset": hex(offset), "sourceTrackSlot": track_index, "sourceTrackOffset": hex(track_offset), "frameCount": frame_count, "frameIndices": frame_indices, "fps": 30}})
        clip_manifest.append({"name": name, "slot": slot, "track": track_index, "frameCount": frame_count, "durationSeconds": round((frame_count - 1) / 30.0, 6)})
    return clips, clip_manifest, len(track_offsets), len(control_offsets), excluded


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


def export():
    source = (COMMON / "PL00P000.BIN").read_bytes()
    file_type, size = struct.unpack_from("<II", source)
    if file_type != 1 or size != 0x2B40 or len(source) < 0x30 + size:
        raise ValueError("PL00P000.BIN does not match the documented player PBD layout")
    payload = source[0x30:0x30 + size]
    by_material, bones, world_bones, minimum, maximum, source_materials, face_count, vertex_count, muzzle = decode_mesh(payload)
    vram, _ = textures(COMMON / "PL00T.BIN")
    pngs = [texture_page(vram, item["clut"], item["tpage"]) for item in MATERIALS]
    binary = BinaryGLB()
    primitive_json = []
    for material in source_materials:
        arrays = by_material[material]
        attrs = {
            "POSITION": binary.accessor(arrays["positions"], "f", 5126, "VEC3", 34962, True),
            "NORMAL": binary.accessor(arrays["normals"], "f", 5126, "VEC3", 34962),
            "TEXCOORD_0": binary.accessor(arrays["uvs"], "f", 5126, "VEC2", 34962),
            "COLOR_0": binary.accessor(arrays["colors"], "f", 5126, "VEC4", 34962),
            "JOINTS_0": binary.accessor(arrays["joints"], "H", 5123, "VEC4", 34962),
            "WEIGHTS_0": binary.accessor(arrays["weights"], "f", 5126, "VEC4", 34962),
        }
        primitive_json.append({"attributes": attrs, "material": material, "mode": 4})
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
    animations, clip_manifest, track_slots, control_slots, excluded_controls = decode_animations(source, binary, bone_node_ids, bones)
    document = {
        "asset": {"version": "2.0", "generator": "export_player.py", "extras": {"source": "PL00P000.BIN", "identity": "Mega Man Legends 2 player, helmet and normal shoes, buster equipped", "sourceBoneCount": 16, "unusedSourceBone": 15}},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": [{"name": "MegaMan", "primitives": primitive_json}],
        "skins": [{"name": "MegaManSkeleton", "skeleton": bone_node_ids[0], "joints": bone_node_ids, "inverseBindMatrices": inverse_bind}],
        "animations": animations,
        "materials": [{"name": item["name"], "doubleSided": True, "alphaMode": "MASK", "alphaCutoff": 0.5, "pbrMetallicRoughness": {"baseColorTexture": {"index": i}, "metallicFactor": 0.0, "roughnessFactor": 1.0}, "extensions": {"KHR_materials_unlit": {}}} for i, item in enumerate(MATERIALS)],
        "textures": [{"sampler": 0, "source": i} for i in range(len(pngs))],
        "images": [{"bufferView": image_views[i], "mimeType": "image/png", "name": MATERIALS[i]["name"]} for i in range(len(pngs))],
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
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "megaman.glb").write_bytes(glb)
    manifest = {
        "model": "megaman.glb",
        "identity": {"source": "PL00P000.BIN", "helmet": True, "shoes": "normal", "weapon": "buster"},
        "bounds_m": {"min": [round(v, 6) for v in minimum], "max": [round(v, 6) for v in maximum]},
        "orientation": {"up": "Y", "forward": "-Z", "sourceTransform": "X 180 degrees, then Y 180 degrees", "sourceScale": "1/2048 map units per PBD unit"},
        "skeleton": {"jointCount": len(PARENTS), "sourceBoneCount": 16, "unusedSourceBone": 15, "binding": "PBD strip-to-bone assignments from DashGL MML2 StateViewer"},
        "muzzle": {"bone": "Bone_04", "position": [round(v, 6) for v in muzzle], "source": "Buster strip 2 geometry; centered X/Z at minimum local Y"},
        "animations": {"idle": "clip_000", "run": "clip_002", "jump": "clip_017", "shoot": "clip_004"},
        "animationRoleProvenance": "Role names describe rendered clip motion; they are not verified original action-enum labels.",
        "clips": clip_manifest,
        "animationBank": {"source": "PL00P000.BIN", "trackSlots": track_slots, "controlSlots": control_slots, "fps": 30, "frameStrideBytes": 64, "rotationDecoder": "DashGL MML2 packed rotation reader", "rotationOrder": "RotMatrix X*Y*Z, applied Z then Y then X", "basisConversion": "PBD X 180-degree conjugation after packed-axis decode", "excludedControls": excluded_controls},
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": str(OUTPUT / "megaman.glb"), "bytes": len(glb), "triangles": face_count, "sourceVertices": vertex_count, "materials": source_materials, "clips": len(clip_manifest), "track_slots": track_slots, "control_slots": control_slots, "excluded_controls": len(excluded_controls), "bounds_m": manifest["bounds_m"]}, indent=2))


if __name__ == "__main__":
    export()
