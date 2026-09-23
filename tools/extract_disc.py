from __future__ import annotations
import argparse
import re
import struct
from pathlib import Path

SECTOR_SIZE = 2352
USER_OFFSET = 24
USER_SIZE = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"

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

def extract(cue_path: Path, output: Path, includes: set[str]) -> int:
    bin_path, start_frame, frames = cue_layout(cue_path)
    if output.exists() and any(output.iterdir()):
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

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cue", type=Path)
    parser.add_argument("--output", type=Path, default=Path("assets/extracted"))
    parser.add_argument("--include", action="append", default=[])
    args = parser.parse_args()
    try:
        extract(args.cue.resolve(), args.output.resolve(), {name.upper() for name in args.include})
    except (OSError, ValueError, struct.error) as error:
        parser.error(str(error))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
