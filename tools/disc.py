from __future__ import annotations
import argparse
import re
import struct
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import os
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
SECTOR_SIZE = 2352
USER_OFFSET = 24
USER_SIZE = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
def write_if_changed(path, data, encoding="utf-8"):
    path = Path(path); payload = data.replace("\n", os.linesep).encode(encoding) if isinstance(data, str) else bytes(data)
    if path.is_file() and path.stat().st_size == len(payload) and path.read_bytes() == payload: return False
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_name(path.name + ".tmp"); temporary.write_bytes(payload); temporary.replace(path); return True

def cue_time(value: str) -> int:
    minute, second, frame = (int(part) for part in value.split(":"))
    if second >= 60 or frame >= 75:
        raise ValueError(f"invalid CUE time: {value}")
    return (minute * 60 + second) * 75 + frame

def cue_layout(cue_path: Path) -> tuple[Path, int, int]:
    current_file = None
    track1 = None
    track2 = None
    mode1 = None
    for line in cue_path.read_text(encoding="ascii", errors="strict").splitlines():
        match = re.match(r'\s*FILE\s+"?(.+?)"?\s+BINARY\s*$', line, re.I)
        if match:
            current_file = (cue_path.parent / match.group(1)).resolve()
            continue
        match = re.match(r"\s*TRACK\s+(\d+)\s+(\S+)", line, re.I)
        if match:
            number = int(match.group(1))
            mode = match.group(2).upper()
            if number == 1:
                mode1 = mode
            continue
        match = re.match(r"\s*INDEX\s+01\s+(\d{2}:\d{2}:\d{2})", line, re.I)
        if match and current_file:
            value = cue_time(match.group(1))
            if track1 is None:
                track1 = (current_file, value)
            elif track2 is None:
                track2 = (current_file, value)
    if track1 is None or mode1 != "MODE2/2352":
        raise ValueError("expected Track 01 MODE2/2352 with INDEX 01")
    bin_path, start_frame = track1
    if not bin_path.is_file():
        raise FileNotFoundError(bin_path)
    if track2 and track2[0] == bin_path:
        frames = track2[1] - start_frame
    else:
        data_bytes = bin_path.stat().st_size - start_frame * SECTOR_SIZE
        if data_bytes % SECTOR_SIZE:
            raise ValueError("Track 01 BIN length is not a multiple of 2352 bytes")
        frames = data_bytes // SECTOR_SIZE
    if frames <= 16:
        raise ValueError("Track 01 is too short to contain an ISO9660 filesystem")
    return bin_path, start_frame, frames

class Mode2Track:
    def __init__(self, path: Path, start_frame: int, frames: int):
        self.path = path
        self.start_frame = start_frame
        self.frames = frames
        self.stream = path.open("rb")

    def sector(self, lba: int) -> bytes:
        if lba < 0 or lba >= self.frames:
            raise ValueError(f"sector {lba} is outside Track 01")
        self.stream.seek((self.start_frame + lba) * SECTOR_SIZE)
        raw = self.stream.read(SECTOR_SIZE)
        if len(raw) != SECTOR_SIZE or raw[:12] != SYNC or raw[15] != 2:
            raise ValueError(f"invalid Mode 2 sector at LBA {lba}")
        if raw[16:20] != raw[20:24]:
            raise ValueError(f"mismatched XA subheaders at LBA {lba}")
        payload_size = 2324 if raw[18] & 0x20 else USER_SIZE
        return raw[USER_OFFSET:USER_OFFSET + payload_size]

    def read_file(self, extent: int, size: int) -> bytes:
        data = bytearray()
        remaining = size
        lba = extent
        while remaining:
            block = self.sector(lba)
            chunk = min(remaining, len(block))
            data.extend(block[:chunk])
            remaining -= chunk
            lba += 1
        return bytes(data)

    def copy_file(self, extent: int, size: int, destination: Path, append: bool = False) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        mode = "ab" if append else "wb"
        with destination.open(mode) as output:
            remaining = size
            lba = extent
            while remaining:
                block = self.sector(lba)
                chunk = min(remaining, len(block))
                output.write(block[:chunk])
                remaining -= chunk
                lba += 1

def iso_name(raw: bytes) -> str:
    name = raw.decode("ascii", errors="replace")
    if name in ("\x00", "\x01"):
        return ""
    name = name.split(";", 1)[0].rstrip(".")
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)

def directory_records(reader: Mode2Track, extent: int, size: int):
    data = reader.read_file(extent, size)
    offset = 0
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset = ((offset // USER_SIZE) + 1) * USER_SIZE
            continue
        record = data[offset:offset + length]
        if len(record) != length or length < 34:
            raise ValueError(f"invalid ISO directory record at extent {extent}")
        name_length = record[32]
        if 33 + name_length > length:
            raise ValueError(f"invalid ISO filename record at extent {extent}")
        name = iso_name(record[33:33 + name_length])
        if name:
            yield name, struct.unpack_from("<I", record, 2)[0], struct.unpack_from("<I", record, 10)[0], record[25]
        offset += length

def extract(cue_path: Path, output: Path, includes: set[str], reuse: bool = False) -> int:
    bin_path, start_frame, frames = cue_layout(cue_path)
    if output.exists() and any(output.iterdir()) and not reuse:
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    reader = Mode2Track(bin_path, start_frame, frames)
    try:
        pvd = next((reader.sector(lba) for lba in range(16, 32) if reader.sector(lba)[1:6] == b"CD001" and reader.sector(lba)[0] == 1), None)
        if pvd is None:
            raise ValueError("no ISO9660 primary volume descriptor found")
        root = pvd[156:190]
        if len(root) < 34 or root[0] < 34:
            raise ValueError("invalid ISO9660 root directory record")
        root_extent = struct.unpack_from("<I", root, 2)[0]
        root_size = struct.unpack_from("<I", root, 10)[0]
        count = 0
        total_bytes = 0
        visited = set()
        def walk(extent: int, size: int, relative: Path) -> None:
            nonlocal count, total_bytes
            identity = (extent, size)
            if identity in visited:
                return
            visited.add(identity)
            pending_multi = None
            for name, file_extent, file_size, flags in directory_records(reader, extent, size):
                if not relative.parts and includes and name.upper() not in includes:
                    continue
                target = relative / name
                is_dir = bool(flags & 2)
                multi_extent = bool(flags & 0x80)
                if is_dir:
                    walk(file_extent, file_size, target)
                    continue
                append = pending_multi == target
                if reuse and (output / target).is_file() and not append and not multi_extent:
                    if (output / target).read_bytes() != reader.read_file(file_extent, file_size):
                        raise ValueError(f"cached file differs from the selected disc: {target}")
                    count += 1
                    total_bytes += file_size
                    continue
                reader.copy_file(file_extent, file_size, output / target, append)
                pending_multi = target if multi_extent else None
                if not multi_extent:
                    count += 1
                    total_bytes += file_size
                    print(f"{target} ({file_size} bytes)")
        walk(root_extent, root_size, Path())
        print(f"Extracted {count} files, {total_bytes} bytes from {bin_path.name}")
        return count
    finally:
        reader.stream.close()

def disc_cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cue", type=Path)
    parser.add_argument("--output", type=Path, default=Path("assets/extracted"))
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()
    try:
        extract(args.cue.resolve(), args.output.resolve(), {name.upper() for name in args.include}, args.reuse)
    except (OSError, ValueError, struct.error) as error:
        parser.error(str(error))
    return 0

HEADER_SIZE = 0x30
SECTION_TYPES = {0x03, 0x05, 0x0C, 0x0D}
ROOT_TYPE = 0x0D
ALIGNMENT = 0x400
WINDOW_SIZE = 0x2000

def read_u16(data, offset):
	if offset < 0 or offset + 2 > len(data): raise ValueError(f"u16 outside buffer at 0x{offset:x}")
	return struct.unpack_from("<H", data, offset)[0]

def read_u32(data, offset):
	if offset < 0 or offset + 4 > len(data): raise ValueError(f"u32 outside buffer at 0x{offset:x}")
	return struct.unpack_from("<I", data, offset)[0]

def decompress_section(source, section_offset, bitfield_offset=0x10):
	section_type = read_u32(source, section_offset)
	if section_type not in SECTION_TYPES: raise ValueError(f"unsupported section type 0x{section_type:x} at 0x{section_offset:x}")
	full_size = read_u32(source, section_offset + 4)
	section_count = read_u32(source, section_offset + 8)
	bitfield_size = read_u16(source, section_offset + bitfield_offset)
	bitfield_start = section_offset + HEADER_SIZE
	bitfield_end = bitfield_start + bitfield_size
	if full_size == 0 or bitfield_size == 0 or bitfield_size & 3: raise ValueError(f"invalid section header at 0x{section_offset:x}")
	if bitfield_end > len(source): raise ValueError(f"bitfield extends past source at 0x{section_offset:x}")
	bitfield = []
	for offset in range(bitfield_start, bitfield_end, 4):
		word = read_u32(source, offset)
		bitfield.extend((word >> bit) & 1 for bit in range(31, -1, -1))
	payload_offset = bitfield_end
	read_offset = payload_offset
	output = bytearray(full_size + WINDOW_SIZE)
	output_offset = 0
	window_offset = 0
	for bit in bitfield:
		if output_offset == full_size: break
		word = read_u16(source, read_offset)
		read_offset += 2
		if bit == 0:
			if output_offset + 2 > full_size: raise ValueError(f"literal overruns decoded section at 0x{section_offset:x}")
			struct.pack_into("<H", output, output_offset, word)
			output_offset += 2
		elif word == 0xffff:
			window_offset += WINDOW_SIZE
		else:
			copy_from = window_offset + ((word >> 3) & 0x1fff)
			copy_size = ((word & 7) + 2) * 2
			if copy_from >= output_offset or output_offset + copy_size > full_size or copy_from + copy_size > len(output): raise ValueError(f"invalid backreference at 0x{section_offset:x}+0x{read_offset - 2:x}")
			for index in range(copy_size): output[output_offset + index] = output[copy_from + index]
			output_offset += copy_size
	if output_offset != full_size: raise ValueError(f"decoded {output_offset} of {full_size} bytes at 0x{section_offset:x}")
	return bytes(output[:full_size]), {"offset": section_offset, "type": section_type, "full_size": full_size, "section_count": section_count, "bitfield_size": bitfield_size, "compressed_size": read_offset - section_offset, "load_address": read_u32(source, section_offset + 0x0c)}

def extract_section(source, section_offset):
	section_type = read_u32(source, section_offset)
	if section_type == 0x0C: return decompress_section(source, section_offset)
	full_size = read_u32(source, section_offset + 4)
	section_count = read_u32(source, section_offset + 8)
	load_address = read_u32(source, section_offset + 0x0c)
	payload_offset = section_offset + HEADER_SIZE
	if full_size == 0 or payload_offset + full_size > len(source): raise ValueError(f"raw section at 0x{section_offset:x} exceeds source")
	return source[payload_offset:payload_offset + full_size], {"offset": section_offset, "type": section_type, "full_size": full_size, "section_count": section_count, "bitfield_size": 0, "compressed_size": full_size, "load_address": load_address}

def find_sections(source):
	sections = []
	for offset in range(ALIGNMENT, len(source) - HEADER_SIZE + 1, ALIGNMENT):
		section_type = read_u32(source, offset)
		if section_type not in {0x05, 0x0C}: continue
		if section_type == 0x0C and read_u16(source, offset + 0x10) == 0: continue
		if section_type == 0x05 and read_u32(source, offset + 4) == 0: continue
		sections.append(offset)
	return sections

def extract_stage(path, output_dir):
	source = path.read_bytes()
	if len(source) < HEADER_SIZE or read_u32(source, 0) != ROOT_TYPE: return []
	results = []
	root_map, metadata = decompress_section(source, 0)
	metadata["role"] = "stage-root"
	results.append((root_map, metadata, output_dir / f"{path.stem}_map.bin"))
	for offset in find_sections(source):
		try: decoded, metadata = extract_section(source, offset)
		except ValueError as error:
			print(f"{path.name} +0x{offset:X}: ignored non-section candidate ({error})")
			continue
		metadata["role"] = "embedded-section"
		results.append((decoded, metadata, output_dir / f"{path.stem}_{offset:05X}.bin"))
	written = []
	for decoded, metadata, destination in results:
		if destination.exists() and destination.read_bytes() != decoded: raise FileExistsError(f"refusing to replace different output: {destination}")
		destination.parent.mkdir(parents=True, exist_ok=True)
		write_if_changed(destination, decoded)
		metadata["output"] = str(destination)
		written.append(metadata)
	return written

def maps_cli():
	parser = argparse.ArgumentParser()
	parser.add_argument("--input-dir", type=Path, default=Path("build/disc-assets/DAT"))
	parser.add_argument("--output-dir", type=Path, default=Path("build/maps"))
	parser.add_argument("--stage", type=str)
	args = parser.parse_args()
	if args.stage and not re.fullmatch(r"ST[0-9A-Fa-f]{2}", args.stage): parser.error("--stage must be a root name such as ST0F")
	paths = sorted(args.input_dir.glob("ST[0-9A-Fa-f][0-9A-Fa-f].BIN"))
	if args.stage: paths = [path for path in paths if path.stem.upper() == args.stage.upper()]
	for path in paths:
		for section in extract_stage(path, args.output_dir): print(f"{path.name} +0x{section['offset']:X}: decoded 0x{section['full_size']:X} bytes from type 0x{section['type']:X} -> {section['output']}")

OUTPUT = ROOT / "assets/video"
WORK = ROOT / "build/video"
def disc_files(reader):
	pvd = reader.read_file(16, 2048)
	if pvd[1:6] != b"CD001": raise ValueError("The supplied track has no ISO9660 primary volume descriptor")
	root = pvd[156:190]; result = []
	def walk(extent, size, parent):
		for name, file_extent, file_size, flags in directory_records(reader, extent, size):
			path = parent / name
			if flags & 2: walk(file_extent, file_size, path)
			else: result.append({"file": path.as_posix(), "extent": file_extent, "iso_bytes": file_size})
	walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], Path()); return result
def copy_raw_sectors(reader, first, last, destination):
	if first < 0 or last > reader.frames or first >= last: raise ValueError("Movie extent is outside the original data track")
	reader.stream.seek((reader.start_frame + first) * 2352)
	with destination.open("wb") as output:
		remaining = (last - first) * 2352
		while remaining:
			data = reader.stream.read(min(remaining, 2352 * 4096))
			if not data: raise ValueError("Truncated original raw movie sectors")
			output.write(data); remaining -= len(data)
def audit_track(reader):
	reader.stream.seek(reader.start_frame * 2352); counts = Counter(); groups = []; current = {}; digest = hashlib.sha256()
	for first in range(0, reader.frames, 4096):
		data = reader.stream.read(min(4096, reader.frames - first) * 2352)
		if len(data) != min(4096, reader.frames - first) * 2352: raise ValueError("Truncated original data track")
		digest.update(data)
		for offset in range(0, len(data), 2352):
			sector = data[offset:offset + 2352]; lba = first + offset // 2352
			if sector[15] != 2: continue
			counts[sector[18]] += 1
			if sector[24:28] != b"\x60\x01\x01\x80": continue
			chunk, chunks, frame, size, width, height = struct.unpack_from("<HHIIHH", sector, 28)
			if not 0 < chunks <= 128 or chunk >= chunks or not 0 < width <= 640 or not 0 < height <= 480: raise ValueError("Malformed original STR frame header")
			key = tuple(sector[16:18]); previous = current.get(key)
			if previous is None or frame < previous["last_frame"] or lba - previous["last_lba"] > 150:
				previous = {"file_number": key[0], "channel": key[1], "first_lba": lba, "last_lba": lba, "first_frame": frame, "last_frame": frame, "width": width, "height": height}; groups.append(previous); current[key] = previous
			previous["last_lba"] = lba; previous["last_frame"] = frame
	return {"data_track_sectors": reader.frames, "data_track_sha256": digest.hexdigest(), "xa_video_submode_sectors": sum(number for mode, number in counts.items() if mode & 2), "xa_submode_counts": {hex(mode): count for mode, count in sorted(counts.items())}, "str_groups": groups}
def export_movies(cue):
	OUTPUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True); path, start, frames = cue_layout(Path(cue)); reader = Mode2Track(path, start, frames)
	try:
		files = disc_files(reader); audit = audit_track(reader); movies = []
		for index, group in enumerate(audit["str_groups"]):
			ffmpeg = shutil.which("ffmpeg")
			if not ffmpeg: raise RuntimeError("FFmpeg is required to transcode original STR movies")
			name = f"native_{index:03d}"; raw = WORK / (name + ".str"); destination = OUTPUT / (name + ".ogv"); copy_raw_sectors(reader, group["first_lba"], group["last_lba"] + 1, raw); subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libtheora", "-q:v", "9", "-c:a", "libvorbis", "-q:a", "6", str(destination)], check=True); movies.append({"file": destination.name, "source": group, "raw_sector_bytes": 2352, "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
	finally: reader.stream.close()
	manifest = {"movies": movies, "transport_audit": audit, "xa_archives": [entry for entry in files if entry["file"].startswith("XA/")], "native_startup": {"source": "SLES 0x80012D7C..0x80012F28", "logo_resource": "COMMON/LOGO.BIN", "logo_renderer": "0x800132F8", "logo_rect": [48, 192, 544, 96], "logo_fade_step": 4, "logo_fade_max": 128, "logo_hold_counter": 180, "next_scene": {"stage": "ST02", "area": 0, "engine_phase": 4}, "intro_type": "Original engine scene; no standard STR/XA video sectors present on this disc"}, "native_attract": {"source": "DEMO 0x800AD308..0x800AD5FC", "counter_updates": 512, "counter_formula": "(3-titleFrameBufferCount)*256; titleFrameBufferCount=1", "cycle_index_update": "(index+1)&3", "stages": [{"cycle_index": 0, "stage": "ST02", "demo_mode": 0, "source_pc": "0x800AD48C"}, {"cycle_index": 1, "stage": "ST50", "demo_mode": 2, "area_fields": [13, 13], "source_pc": "0x800AD4B4"}, {"cycle_index": 2, "stage": "ST22", "demo_mode": 3, "area_fields": [8, 8], "source_pc": "0x800AD4F8"}, {"cycle_index": 3, "stage": "ST51", "demo_mode": 4, "area_fields": [0, 0], "source_pc": "0x800AD548"}], "mode_consumer": "GAME 0x800C3780 and jump table 0x800AE154 configure native player equipment for modes2/3/4", "recorded_input_stream": "not yet identified; stages are engine scenes rather than STR movie playback"}, "limits": ["No substitute movies are generated for native engine scenes", "Tick counts are verified; PAL wall-clock conversion remains unverified"]}; write_if_changed(OUTPUT / "manifest.json", json.dumps(manifest, indent=2) + "\n", encoding="utf-8"); return manifest
def movies_cli():
	parser = argparse.ArgumentParser(); parser.add_argument("--cue", type=Path, required=True); args = parser.parse_args(); manifest = export_movies(args.cue); print(json.dumps({"movies": len(manifest["movies"]), "video_submode_sectors": manifest["transport_audit"]["xa_video_submode_sectors"], "manifest": str(OUTPUT / "manifest.json")}))

if __name__ == '__main__':
	import sys
	commands = {'disc': 'disc_cli', 'maps': 'maps_cli', 'movies': 'movies_cli'}
	if len(sys.argv) < 2 or sys.argv[1] not in commands: raise SystemExit('Choose: ' + ', '.join(commands))
	command = sys.argv.pop(1)
	globals()[commands[command]]()
