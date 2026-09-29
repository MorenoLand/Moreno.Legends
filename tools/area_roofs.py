import json
import math
import struct
from collections import Counter
from pathlib import Path
from disc import write_if_changed
ROOT = Path(__file__).resolve().parents[1]
def camera_table(data):
    call = data.find(struct.pack("<I", 0x0C000000 | ((0x80016270 >> 2) & 0x03FFFFFF)), 48)
    if call < 40: raise ValueError("Native area camera initializer not found")
    upper = None
    for offset in range(call - 40, call, 4):
        word = struct.unpack_from("<I", data, offset)[0]
        if word >> 16 == 0x3C04: upper = (word & 65535) << 16
        if word >> 16 == 0x2484 and upper is not None: return upper + struct.unpack("<h", struct.pack("<H", word & 65535))[0]
    raise ValueError("Native area camera table address unresolved")
def geometry(path, native_map_face_flags=False):
    data = path.read_bytes(); size = struct.unpack_from("<I", data, 12)[0]; document = json.loads(data[20:20 + size]); binary = data[28 + size:]
    def accessor(index):
        record = document["accessors"][index]; view = document["bufferViews"][record["bufferView"]]; width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[record["type"]]; fmt = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[record["componentType"]]; stride = view.get("byteStride", struct.calcsize(fmt) * width); offset = view.get("byteOffset", 0) + record.get("byteOffset", 0)
        return [struct.unpack_from("<" + fmt * width, binary, offset + item * stride) for item in range(record["count"])]
    parents = {child: index for index, node in enumerate(document["nodes"]) for child in node.get("children", [])}
    def point(index, value):
        node = document["nodes"][index]
        if "matrix" in node:
            matrix = node["matrix"]; value = [sum(matrix[column * 4 + row] * value[column] for column in range(3)) + matrix[12 + row] for row in range(3)]
        else:
            value = [value[axis] * node.get("scale", [1, 1, 1])[axis] for axis in range(3)]; x, y, z, w = node.get("rotation", [0, 0, 0, 1]); tx = 2 * (y * value[2] - z * value[1]); ty = 2 * (z * value[0] - x * value[2]); tz = 2 * (x * value[1] - y * value[0]); value = [value[0] + w * tx + y * tz - z * ty, value[1] + w * ty + z * tx - x * tz, value[2] + w * tz + x * ty - y * tx]; value = [value[axis] + node.get("translation", [0, 0, 0])[axis] for axis in range(3)]
        return point(parents[index], value) if index in parents else value
    triangles = []
    for index, node in enumerate(document["nodes"]):
        if "mesh" not in node: continue
        for surface, primitive in enumerate(document["meshes"][node["mesh"]]["primitives"]):
            if primitive.get("mode", 4) != 4: continue
            attributes = primitive["attributes"]; positions = [point(index, value) for value in accessor(attributes["POSITION"])]; uv = accessor(attributes["TEXCOORD_0"]) if "TEXCOORD_0" in attributes else [(0, 0)] * len(positions); colors = accessor(attributes["COLOR_0"]) if "COLOR_0" in attributes else [(0.5, 0.5, 0.5, 1)] * len(positions); indices = [value[0] for value in accessor(primitive["indices"])] if "indices" in primitive else list(range(len(positions)))
            if native_map_face_flags and "TEXCOORD_1" in attributes: colors = [(*value[:3], 1.0) for value in colors]
            for start in range(0, len(indices), 3):
                ids = indices[start:start + 3]
                if len(ids) != 3: continue
                vertices = [positions[item] for item in ids]; u = [vertices[1][axis] - vertices[0][axis] for axis in range(3)]; v = [vertices[2][axis] - vertices[0][axis] for axis in range(3)]; normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; length = math.sqrt(sum(value * value for value in normal))
                if length < 1e-10: continue
                triangles.append({"vertices": vertices, "uv": [uv[item] for item in ids], "colors": [colors[item] for item in ids], "normal_y": normal[1] / length, "area": length / 2, "node": node["name"], "surface": surface})
    return triangles
def signed_edge(a, b, p): return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
def split(polygon, a, b, sign):
    inside = []; outside = []
    for index, p in enumerate(polygon):
        q = polygon[(index + 1) % len(polygon)]; dp = signed_edge(a, b, p) * sign; dq = signed_edge(a, b, q) * sign
        if dp >= -1e-8: inside.append(p)
        if dp <= 1e-8: outside.append(p)
        if (dp > 1e-8 and dq < -1e-8) or (dp < -1e-8 and dq > 1e-8):
            factor = dp / (dp - dq); cut = [p[axis] + (q[axis] - p[axis]) * factor for axis in range(2)]; inside.append(cut); outside.append(cut)
    return inside, outside
def subtract(polygon, triangle):
    if any(max(p[axis] for p in polygon) < min(p[axis] for p in triangle) or min(p[axis] for p in polygon) > max(p[axis] for p in triangle) for axis in range(2)): return [polygon]
    sign = 1 if signed_edge(triangle[0], triangle[1], triangle[2]) > 0 else -1; remaining = polygon; pieces = []
    for index in range(3):
        remaining, outside = split(remaining, triangle[index], triangle[(index + 1) % 3], sign)
        if len(outside) >= 3: pieces.append(outside)
        if len(remaining) < 3: break
    return pieces
def roof_geometry(triangles):
    floors = [triangle for triangle in triangles if triangle["normal_y"] > 0.999]
    if not floors: return {"reason": "no_horizontal_floor", "vertices": []}
    floor_y = min(min(vertex[1] for vertex in triangle["vertices"]) for triangle in floors); walls = [triangle for triangle in triangles if abs(triangle["normal_y"]) < 0.25]; roof_y = max(vertex[1] for triangle in (walls or triangles) for vertex in triangle["vertices"]); floors = sorted((triangle for triangle in floors if max(vertex[1] for vertex in triangle["vertices"]) <= roof_y + 0.01), key=lambda triangle: triangle["vertices"][0][1])
    floor_area = sum(triangle["area"] for triangle in floors if abs(triangle["vertices"][0][1] - floor_y) < 0.01); ceiling_planes = Counter()
    for triangle in triangles:
        if triangle["normal_y"] < -0.999 and min(vertex[1] for vertex in triangle["vertices"]) > floor_y + 0.75: ceiling_planes[round(triangle["vertices"][0][1], 6)] += triangle["area"]
    if ceiling_planes and floor_area > 0:
        ceiling_y, ceiling_area = ceiling_planes.most_common(1)[0]
        if ceiling_area / floor_area >= 0.8: return {"reason": "existing_ceiling", "height": ceiling_y, "native_ceiling_coverage": ceiling_area / floor_area, "vertices": []}
    if roof_y - floor_y < 0.75: return {"reason": "insufficient_room_height", "vertices": []}
    ceilings = [triangle for triangle in triangles if triangle["normal_y"] < -0.999 and min(vertex[1] for vertex in triangle["vertices"]) >= roof_y - 0.01]; samples = ceilings or walls
    if not samples: return {"reason": "no_material_sample", "vertices": []}
    material_area = Counter()
    for triangle in samples: material_area[(triangle["node"], triangle["surface"])] += triangle["area"]
    material = material_area.most_common(1)[0][0]; sample = max((triangle for triangle in samples if (triangle["node"], triangle["surface"]) == material), key=lambda triangle: triangle["area"]); uv_min = [min(value[axis] for value in sample["uv"]) for axis in range(2)]; uv_max = [max(value[axis] for value in sample["uv"]) for axis in range(2)]; color = [sum(value[axis] for value in sample["colors"]) / 3 for axis in range(3)] + [1]; cuts = [[[vertex[0], vertex[2]] for vertex in triangle["vertices"]] for triangle in ceilings]; vertices = []; uvs = []
    for floor in floors:
        pieces = [[[vertex[0], vertex[2]] for vertex in floor["vertices"]]]
        for cut in cuts:
            pieces = [part for polygon in pieces for part in subtract(polygon, cut)]
            if not pieces: break
        for polygon in pieces:
            low = [min(point[axis] for point in polygon) for axis in range(2)]; high = [max(point[axis] for point in polygon) for axis in range(2)]
            for index in range(1, len(polygon) - 1):
                triangle = [polygon[0], polygon[index], polygon[index + 1]]
                if abs(signed_edge(*triangle)) < 1e-7: continue
                cuts.append(triangle)
                for point in triangle:
                    vertices.append([round(point[0], 6), round(roof_y, 6), round(point[1], 6)]); uvs.append([uv_min[axis] + (point[axis] - low[axis]) / max(high[axis] - low[axis], 1e-8) * (uv_max[axis] - uv_min[axis]) for axis in range(2)])
    return {"reason": "missing_ceiling" if vertices else "existing_ceiling", "height": roof_y, "material_node": material[0], "material_surface": material[1], "material_source": "existing_ceiling" if ceilings else "existing_wall", "sample_uv_min": uv_min, "sample_uv_max": uv_max, "color": color, "vertices": vertices, "uv": uvs}
def ceiling_holes(triangles, height):
    edges = Counter()
    for triangle in triangles:
        if triangle["normal_y"] > -0.999 or abs(triangle["vertices"][0][1] - height) >= 0.01: continue
        points = [tuple(round(value, 6) for value in (vertex[0], vertex[2])) for vertex in triangle["vertices"]]
        for index in range(3): edges[tuple(sorted((points[index], points[(index + 1) % 3])))] += 1
    graph = {}
    for (a, b), count in edges.items():
        if count % 2: graph.setdefault(a, []).append(b); graph.setdefault(b, []).append(a)
    if any(len(neighbors) != 2 for neighbors in graph.values()): raise ValueError("Ceiling opening boundary is not a closed loop")
    loops = []; seen = set()
    for start in graph:
        if start in seen: continue
        loop = []; previous = None; point = start
        while point not in seen:
            seen.add(point); loop.append(point); neighbors = graph[point]; next_point = neighbors[0] if neighbors[0] != previous else neighbors[1]; previous, point = point, next_point
        loops.append(loop)
    if len(loops) < 2: return []
    area = lambda loop: abs(sum(point[0] * loop[(index + 1) % len(loop)][1] - loop[(index + 1) % len(loop)][0] * point[1] for index, point in enumerate(loop)))
    outer = max(loops, key=area); holes = []
    for loop in loops:
        if loop == outer: continue
        x, z = loop[0]; inside = False
        for index, a in enumerate(outer):
            b = outer[(index + 1) % len(outer)]
            if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]: inside = not inside
        if inside: holes.append([[point[0], height + 0.002, point[1]] for point in loop])
    return holes
def close_raised_roof(triangles, roof):
    if not roof.get("vertices"): return
    floor_y = min(vertex[1] for triangle in triangles for vertex in triangle["vertices"]); height = float(roof["height"]); wall_tops = Counter(); walls = []
    for triangle in triangles:
        if abs(triangle["normal_y"]) > 0.01: continue
        top = max(vertex[1] for vertex in triangle["vertices"])
        if top < (floor_y + height) * 0.5: continue
        wall_tops[round(top, 6)] += triangle["area"]; walls.append(triangle)
    if not wall_tops: return
    wall_y = wall_tops.most_common(1)[0][0]
    if height - wall_y < 0.01: return
    edges = {}; graph = {}
    for triangle in walls:
        if abs(max(vertex[1] for vertex in triangle["vertices"]) - wall_y) > 1e-6: continue
        indices = [index for index, vertex in enumerate(triangle["vertices"]) if abs(vertex[1] - wall_y) < 1e-6]
        if len(indices) != 2: continue
        a, b = [tuple(round(vertex[axis], 6) for axis in (0, 2)) for vertex in (triangle["vertices"][index] for index in indices)]; key = tuple(sorted((a, b)))
        if a == b or key in edges: continue
        edges[key] = (triangle, indices); graph.setdefault(a, []).append(b); graph.setdefault(b, []).append(a)
    loops = []; seen = set()
    for start in graph:
        if start in seen: continue
        component = []; pending = [start]
        while pending:
            point = pending.pop()
            if point in seen: continue
            seen.add(point); component.append(point); pending.extend(graph[point])
        if any(len(graph[point]) != 2 for point in component): continue
        loop = []; previous = None; point = start
        while point not in loop:
            loop.append(point); neighbors = graph[point]; next_point = neighbors[0] if neighbors[0] != previous else neighbors[1]; previous, point = point, next_point
        if point == start: loops.append(loop)
    if not loops: return
    signed_area = lambda loop: sum(point[0] * loop[(index + 1) % len(loop)][1] - loop[(index + 1) % len(loop)][0] * point[1] for index, point in enumerate(loop))
    outline = max(loops, key=lambda loop: abs(signed_area(loop))); polygon = list(outline)
    while len(polygon) > 3:
        flat = next((index for index in range(len(polygon)) if abs(signed_edge(polygon[index - 1], polygon[index], polygon[(index + 1) % len(polygon)])) < 1e-8), None)
        if flat is None: break
        polygon.pop(flat)
    sign = 1 if signed_area(polygon) > 0 else -1; remaining = list(polygon); faces = []
    while len(remaining) > 3:
        ear = None
        for index in range(len(remaining)):
            a, b, c = remaining[index - 1], remaining[index], remaining[(index + 1) % len(remaining)]
            if signed_edge(a, b, c) * sign <= 1e-8: continue
            if any(all(signed_edge(p, q, point) * sign >= -1e-8 for p, q in ((a, b), (b, c), (c, a))) for point in remaining if point not in (a, b, c)): continue
            ear = index; faces.append([a, b, c]); break
        if ear is None: return
        remaining.pop(ear)
    faces.append(remaining)
    for start in range(0, len(roof["vertices"]), 3):
        uncovered = [[[point[0], point[2]] for point in roof["vertices"][start:start + 3]]]
        for face in faces:
            uncovered = [piece for part in uncovered for piece in subtract(part, face)]
            if not uncovered: break
        uncovered_area = sum(abs(sum(point[0] * part[(index + 1) % len(part)][1] - part[(index + 1) % len(part)][0] * point[1] for index, point in enumerate(part))) / 2 for part in uncovered)
        if uncovered_area > 1e-7:
            roof["rejected_wall_contour"] = "Closed wall component does not cover the existing floor-derived roof"
            perimeter_roof_height(triangles, roof)
            return
    height += 0.01; low = [min(point[axis] for point in polygon) for axis in range(2)]; high = [max(point[axis] for point in polygon) for axis in range(2)]; uv_low = roof["sample_uv_min"]; uv_high = roof["sample_uv_max"]; roof["vertices"] = [[point[0], height, point[1]] for face in faces for point in face]; roof["uv"] = [[uv_low[axis] + (point[axis] - low[axis]) / max(high[axis] - low[axis], 1e-8) * (uv_high[axis] - uv_low[axis]) for axis in range(2)] for face in faces for point in face]; roof["height"] = height; groups = {}; wall_bias = 0.002
    for index, a in enumerate(outline):
        b = outline[(index + 1) % len(outline)]; triangle, indices = edges[tuple(sorted((a, b)))]; ia, ib = indices; va, vb = triangle["vertices"][ia], triangle["vertices"][ib]; ic = next(item for item in range(3) if item not in indices); lower = triangle["vertices"][ic]; match = ia if math.hypot(lower[0] - va[0], lower[2] - va[2]) < math.hypot(lower[0] - vb[0], lower[2] - vb[2]) else ib; fraction = min(1.0, (height - wall_y) / max(wall_y - lower[1], 1e-8)); delta = [(triangle["uv"][ic][axis] - triangle["uv"][match][axis]) * fraction for axis in range(2)]; ua, ub = triangle["uv"][ia], triangle["uv"][ib]; da, db = [[uv[axis] + delta[axis] for axis in range(2)] for uv in (ua, ub)]; ta, tb = [va[0], height, va[2]], [vb[0], height, vb[2]]; key = (triangle["node"], triangle["surface"])
        if key not in groups: groups[key] = {"material_node": key[0], "material_surface": key[1], "vertices": [], "uv": [], "colors": []}
        length = math.hypot(b[0] - a[0], b[1] - a[1]); offset = [-(b[1] - a[1]) * sign * wall_bias / length, 0, (b[0] - a[0]) * sign * wall_bias / length]; va = [va[axis] + offset[axis] for axis in range(3)]; vb = [vb[axis] + offset[axis] for axis in range(3)]; ta = [ta[axis] + offset[axis] for axis in range(3)]; tb = [tb[axis] + offset[axis] for axis in range(3)]; va[1] -= wall_bias; vb[1] -= wall_bias
        group = groups[key]; group["vertices"].extend([va, vb, tb, va, tb, ta]); group["uv"].extend([da, db, ub, da, ub, ua]); group["colors"].extend([triangle["colors"][item] for item in (ia, ib, ib, ia, ib, ia)])
    roof["wall_infills"] = list(groups.values()); roof["wall_top_height"] = wall_y; roof["wall_inward_bias"] = wall_bias
def perimeter_roof_height(triangles, roof):
    floor = [[[point[0], point[2]] for point in roof["vertices"][start:start + 3]] for start in range(0, len(roof["vertices"]), 3)]; tops = []
    def inside(point): return any(all(signed_edge(a, b, point) >= -1e-8 for a, b in zip(face, face[1:] + face[:1])) or all(signed_edge(a, b, point) <= 1e-8 for a, b in zip(face, face[1:] + face[:1])) for face in floor)
    for triangle in triangles:
        if abs(triangle["normal_y"]) > 0.01: continue
        top = max(point[1] for point in triangle["vertices"]); points = [point for point in triangle["vertices"] if abs(point[1] - top) < 1e-6]
        if len(points) != 2: continue
        a, b = points; dx, dz = b[0] - a[0], b[2] - a[2]; length = math.hypot(dx, dz)
        if length < 1e-8: continue
        middle = [(a[0] + b[0]) / 2, (a[2] + b[2]) / 2]; left = inside([middle[0] - dz * 0.002 / length, middle[1] + dx * 0.002 / length]); right = inside([middle[0] + dz * 0.002 / length, middle[1] - dx * 0.002 / length])
        if left != right: tops.append(top)
    if not tops: return
    height = max(tops)
    if height >= float(roof["height"]): return
    roof["height"] = height; roof["wall_top_height"] = height
    for point in roof["vertices"]: point[1] = height
def export(dat_dir=None, output_dir=None, stages=None):
    dat_dir = Path(dat_dir or ROOT / "build/disc-assets/DAT"); output_dir = Path(output_dir or ROOT / "assets/levels"); summary = Counter()
    for path in sorted(dat_dir.glob("ST??T.BIN")):
        stage = path.stem[:-1]; lighting_path = output_dir / stage / "lighting.json"
        if stages is not None and stage not in stages: continue
        if not lighting_path.is_file(): continue
        data = path.read_bytes(); base = struct.unpack_from("<I", data, 12)[0]; table = camera_table(data); lighting = json.loads(lighting_path.read_text()); records = []; map_manifest_path = output_dir / stage / "manifest.json"; map_manifest = json.loads(map_manifest_path.read_text()) if map_manifest_path.is_file() else {}; area_flags = {int(area["index"]): bool(area.get("native_map_face_flags_in_alpha", False)) for area in map_manifest.get("areas", [])}
        for area in lighting["native_color_pipeline"]["depth_cue"]["area_parameters"]:
            index = int(area["area"]); offset = 48 + table - base + index * 12
            if offset < 48 or offset + 12 > 48 + struct.unpack_from("<I", data, 4)[0]: raise ValueError(stage + " camera record outside native section")
            values = struct.unpack_from("<BB5h", data, offset); record = {"area": index, "native_camera_record": list(values), "fixed_pitch": values[1] == 2, "source_offset": hex(offset), "roof": {"reason": "camera_allows_pitch", "vertices": []}}; mesh_path = output_dir / stage / ("area_%02d.glb" % index)
            if record["fixed_pitch"] and mesh_path.is_file():
                triangles = geometry(mesh_path, area_flags.get(index, False)); record["roof"] = roof_geometry(triangles); close_raised_roof(triangles, record["roof"])
            if stage in ("ST04", "ST06", "ST07") and index == 0 and mesh_path.is_file():
                triangles = geometry(mesh_path, area_flags.get(index, False)); ceiling = roof_geometry(triangles)
                if ceiling["reason"] == "existing_ceiling": record["roof"]["blackouts"] = ceiling_holes(triangles, ceiling["height"])
            summary[record["roof"]["reason"]] += 1; records.append(record)
        manifest = {"stage": stage, "source": {"archive": "DAT/" + path.name, "camera_table": hex(table), "record_stride": 12, "loader": "SLES80016270", "fixed_pitch_branch": "SLES800163EC..80016404; mode2 ignores look offset", "classification": "Fixed pitch is a roof candidate hint, not an indoor flag; generated geometry is a Godot adaptation"}, "areas": records}; write_if_changed(output_dir / stage / "area_roofs.json", json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")
    return dict(summary)
if __name__ == "__main__": print(json.dumps(export(), indent=2))
