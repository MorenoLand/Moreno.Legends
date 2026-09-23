import argparse
import re
import struct
from pathlib import Path

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
		destination.write_bytes(decoded)
		metadata["output"] = str(destination)
		written.append(metadata)
	return written

def main():
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

if __name__ == "__main__": main()
