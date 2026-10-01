import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
PACK_SCRIPT = '''extends SceneTree
func _initialize() -> void:
\tvar config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://build/web/packs.json"))
\tfor group: String in config:
\t\tvar packer := PCKPacker.new()
\t\tif packer.pck_start(config[group].output) != OK: quit(1); return
\t\tfor entry: Array in config[group].files:
\t\t\tif packer.add_file(entry[0], entry[1]) != OK: quit(1); return
\t\tif packer.flush() != OK: quit(1); return
\tquit()
'''

def run(engine, *arguments):
    subprocess.run([str(engine), "--headless", "--audio-driver", "Dummy", "--path", str(ROOT), *arguments], cwd=ROOT, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

def group_files(directory):
    entries = {}
    single = directory.is_file()
    for path in [directory] if single else sorted(directory.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.suffix == ".import":
            continue
        relative = "res://" + path.relative_to(ROOT).as_posix()
        voice_audio = relative.startswith("res://assets/levels/") and path.parent.name == "audio" or relative.startswith(("res://assets/opening/audio/", "res://assets/audio/common_voices/", "res://assets/audio/voices/"))
        if not single and voice_audio and path.suffix.lower() == ".ogg" and path not in voice_sources(ROOT)[1]: continue
        import_path = path.with_name(path.name + ".import")
        if path.suffix.lower() == ".ogg":
            entries[relative] = str(path)
        elif import_path.exists():
            entries[relative + ".import"] = str(import_path)
            for target in set(re.findall(r'"(res://\.godot/imported/[^"\n]+)"', import_path.read_text(encoding="utf-8"))):
                imported = ROOT / target.removeprefix("res://")
                if not imported.is_file():
                    raise FileNotFoundError(imported)
                entries[target] = str(imported)
        else:
            entries[relative] = str(path)
    return entries

@lru_cache(maxsize=1)
def voice_sources(root):
    groups = {}; legacy = set()
    manifests = [*(root / "assets" / "levels").glob("*/audio/manifest.json"), root / "assets" / "audio" / "common_voices" / "manifest.json", root / "assets" / "opening" / "audio" / "manifest.json"]
    for path in manifests:
        if not path.is_file(): continue
        bank = json.loads(path.read_text(encoding="utf-8"))
        for entry in [*bank.get("entries", []), *([bank] if bank.get("file") and bank.get("id") is not None else [])]:
            file = root / entry["file"].removeprefix("res://") if entry["file"].startswith("res://") else path.parent / entry["file"]
            if not file.is_file(): raise FileNotFoundError(file)
            if entry.get("asset_group"): groups.setdefault(entry["asset_group"], set()).add(file)
            else: legacy.add(file)
    return groups, legacy

def voice_groups():
    groups, _ = voice_sources(ROOT)
    return {group: sorted(paths) for group, paths in groups.items()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True, metavar="EDITOR_EXECUTABLE", help="Path to the Godot or Redot editor executable (.exe on Windows); not an exported .pck, .html, or .wasm file")
    parser.add_argument("--chunk-mib", type=int, default=4)
    parser.add_argument("--output", type=Path, default=None, help="Folder to export into (index.html + packs/); defaults to bin/web")
    args = parser.parse_args()
    if args.engine.suffix.lower() in {".pck", ".html", ".wasm", ".zip"}:
        parser.error("--engine must point to the Godot or Redot editor executable, not an exported game asset")
    if not args.engine.is_file():
        parser.error("--engine must point to an existing Godot or Redot editor executable")
    if os.name == "nt":
        if args.engine.suffix.lower() != ".exe":
            parser.error("--engine must point to the Godot or Redot editor .exe on Windows")
        with args.engine.open("rb") as stream:
            if stream.read(2) != b"MZ":
                parser.error("--engine is not a Windows executable")
    elif not os.access(args.engine, os.X_OK):
        parser.error("--engine must point to an executable Godot or Redot editor file")
    if args.chunk_mib < 1 or args.chunk_mib > 16:
        parser.error("--chunk-mib must be between 1 and 16")
    build = ROOT / "build" / "web"
    output = args.output.resolve() if args.output else ROOT / "bin" / "web"
    packs = output / "packs"
    build.mkdir(parents=True, exist_ok=True)
    packs.mkdir(parents=True, exist_ok=True)
    run(args.engine, "--editor", "--import")
    core_paths = {path for name in ("menu", "fades") for path in group_files(ROOT / "assets" / name)}
    groups = {"stage-" + path.name: [path] for path in sorted((ROOT / "assets" / "levels").iterdir()) if path.is_dir()}
    groups.update({"audio-" + path.name: [path] for path in sorted((ROOT / "assets" / "audio").iterdir()) if path.is_dir() and path.name != "voices"})
    library = ROOT / "assets" / "library"
    if library.is_dir():
        groups.update({"library-" + path.parent.name + "-" + path.name: [path] for path in sorted(library.glob("*/*")) if path.is_dir()})
    dialogue = json.loads((ROOT / "assets" / "dialogue" / "manifest.json").read_text(encoding="utf-8"))
    groups.update({"dialogue-" + stage: [ROOT / "assets" / "dialogue" / bank["file"]] for stage, bank in sorted(dialogue["banks"].items())})
    groups["opening"] = [ROOT / "assets" / "opening", ROOT / "assets" / "video"]
    groups["shared"] = [ROOT / "assets" / name for name in ("minimap", "flutter", "stage_props", "weather", "shops")]
    groups["shared"].append(ROOT / "assets" / "opening" / "effects")
    audio_directory = ROOT / "assets" / "audio" / "ST0F"
    audio = json.loads((audio_directory / "manifest.json").read_text(encoding="utf-8"))
    title_key = audio["roles"]["title_music"]
    menu_keys = {key for role, key in audio["roles"].items() if role.startswith("menu_")}
    audio_path = lambda value: ROOT / value.removeprefix("res://") if value.startswith("res://") else audio_directory / value
    groups["menu-audio"] = [audio_directory / "manifest.json", audio_path(audio["music"][title_key]["file"]), *[audio_path(audio["effects"][key]["file"]) for key in sorted(menu_keys)]]
    groups.update(voice_groups())
    config = {}
    for group, directories in groups.items():
        files = {}
        for directory in directories:
            files.update(group_files(directory))
        files = {path: source for path, source in files.items() if path not in core_paths}
        config[group] = {"output": str(build / (group + ".pck")), "files": sorted(files.items())}
    menu_paths = {entry[0] for entry in config["menu-audio"]["files"]}
    config["audio-ST0F"]["files"] = [entry for entry in config["audio-ST0F"]["files"] if entry[0] not in menu_paths]
    shared_paths = {entry[0] for entry in config["shared"]["files"]}
    config["opening"]["files"] = [entry for entry in config["opening"]["files"] if entry[0] not in shared_paths]
    legacy_paths = {path for file in voice_sources(ROOT)[1] for path in group_files(file)}
    voice_paths = {entry[0] for group, data in config.items() if group.startswith("voice-") for entry in data["files"]} - legacy_paths
    for group in config:
        if not group.startswith("voice-"): config[group]["files"] = [entry for entry in config[group]["files"] if entry[0] not in voice_paths]
    (build / "packs.json").write_text(json.dumps(config), encoding="utf-8")
    script = build / "pack.gd"
    script.write_text(PACK_SCRIPT, encoding="utf-8")
    run(args.engine, "--script", "res://build/web/pack.gd")
    manifest = {"version": 1, "groups": {}}
    for group, entry in config.items():
        source = Path(entry["output"])
        digest = hashlib.sha256()
        chunks = []
        with source.open("rb") as stream:
            while data := stream.read(args.chunk_mib * 1024 * 1024):
                digest.update(data)
                chunk_hash = hashlib.sha256(data).hexdigest()
                name = chunk_hash + ".part"
                (packs / name).write_bytes(data)
                chunks.append({"path": "packs/" + name, "bytes": len(data), "sha256": chunk_hash})
        manifest["groups"][group] = {"bytes": source.stat().st_size, "sha256": digest.hexdigest(), "chunks": chunks}
    (packs / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    current_paths = {chunk["path"] for entry in manifest["groups"].values() for chunk in entry["chunks"]}
    for chunk_path in packs.glob("*.part"):
        if "packs/" + chunk_path.name not in current_paths and re.fullmatch(r"[a-f0-9]{64}\.part", chunk_path.name):
            chunk_path.unlink()
    run(args.engine, "--export-release", "Web", str(output / "index.html"))
    shutil.copyfile(ROOT / "assets" / "menu" / "native_gear_background.png", output / "loading_background.png")
    print(json.dumps({"core_bytes": (output / "index.pck").stat().st_size, "groups": {group: {"bytes": entry["bytes"], "chunks": len(entry["chunks"])} for group, entry in manifest["groups"].items()}}, indent=2))

if __name__ == "__main__":
    main()
