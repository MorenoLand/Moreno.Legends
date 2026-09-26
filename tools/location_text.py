import json
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SLES = ROOT / "build/disc-assets/SLES_035.56"
RECORD_TABLE = 0x611A0
STRING_BASE = 0x60B05
HEADER = bytes([0xFB, 0x1F, 0xFF])
def decode(raw):
	out = []
	for value in raw:
		if value == 0x4C: out.append(" ")
		elif value in (0x0C, 0x5D): out.append("'")
		elif value == 0x61: out.append("-")
		elif value <= 9: out.append(str(value))
		elif 20 <= value <= 45: out.append(chr(65 + value - 20))
		elif 46 <= value <= 71: out.append(chr(97 + value - 46))
		else: out.append("?")
	return "".join(out)
def read_strings(data):
	entries = []; position = STRING_BASE
	while position < 0x6119A:
		end = data.find(HEADER, position + 3)
		entries.append(decode(data[position + 3:end]) if end >= 0 else ""); position = end if end >= 0 else 0x6119A
	return entries
def export_location_names(hints_path=None, output=None):
	data = SLES.read_bytes(); strings = read_strings(data)
	hints = json.loads(Path(hints_path).read_text(encoding="utf-8"))["areas"] if hints_path else {}
	records = []; cursor = RECORD_TABLE
	while data[cursor] <= 0x5C and (not records or data[cursor] >= records[-1][0]): records.append(tuple(data[cursor:cursor + 4])); cursor += 4
	groups = defaultdict(list)
	for stage, area, sub, main in records:
		label = strings[33 + sub].strip() if sub else ""
		if label and "?" not in label: groups[(stage, label)].append(area)
	areas = {}
	for stage, area, sub, main in records:
		label = strings[33 + sub].strip() if sub else ""
		key = "ST%02X" % stage
		if not label or "?" in label:
			hint = hints.get(key, {}).get(str(area))
			if hint: areas.setdefault(key, {})[str(area)] = hint
			continue
		members = groups[(stage, label)]
		if len(members) > 1:
			hint = hints.get(key, {}).get(str(area), ""); skip = set(label.split()) | {"Floor"} | set(strings[(main & 0x7F) + 1].split()) | {"City", "Ruins", "Island"}
			words = [w for w in hint.replace("(", " ").replace(")", " ").split() if w not in skip and not (len(w) == 2 and w[0] == "B" and w[1].isdigit())]
			number = members.index(area) + 1; label = label + " - " + " ".join(words) if words else (label if number == 1 and not label.startswith("Floor") else label + " - Room %d" % number)
		areas.setdefault(key, {})[str(area)] = label
	result = {"source": "SLES_035.56 location strings 0x60B05 and (stage, area, sub-name, main-name) records at 0x611A0. Repeated labels are numbered.", "areas": areas}
	path = Path(output or ROOT / "tools/location_names.json"); path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
	return result
if __name__ == "__main__":
	result = export_location_names(); print(sum(len(v) for v in result["areas"].values()), "named areas")
