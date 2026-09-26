import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
import audio
import area_roofs
import cinematics
import disc
import models
import native_fades
import ui
import world
ROOT = Path(__file__).resolve().parent.parent
def catalog(source):
	return [{"file": path.relative_to(source).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(source.rglob("*")) if path.is_file()]
def export_models(source, stages, report):
	work = ROOT / "build/archives"; work.mkdir(parents=True, exist_ok=True)
	for path in sorted(source.rglob("*.BIN")):
		stage = path.stem[:4] if re.match(r"ST[0-9A-F]{2}", path.stem) else None
		if path.parent.name == "XA" or stages and stage is not None and stage not in stages: continue
		data = path.read_bytes()
		for offset in range(0, max(0, len(data) - 47), 0x400):
			kind, size, count = struct.unpack_from("<3I", data, offset)
			if kind not in (10, 12) or not 16 <= size <= 8 * 1024 * 1024 or not 0 < count <= 4096: continue
			entry = {"file": path.relative_to(source).as_posix(), "offset": offset, "type": kind, "models": []}
			try:
				payload = disc.decompress_section(data, offset)[0] if kind == 12 else data[offset + 48:offset + 48 + size]
				if len(payload) != size: raise ValueError("Truncated model section")
				name = path.stem + "_%05X" % offset; normalized = work / (name + ".bin"); normalized.write_bytes(struct.pack("<3I", 10, len(payload), count) + bytes(36) + payload); archive, payload = models.actor_archive(normalized)
				vram = bytearray(1024 * 512 * 2); uploads = []
				textures = [source / "COMMON/PL00T.BIN", source / "DAT" / (stage + "T.BIN") if stage else path.with_name(path.stem.removesuffix("P000") + "T.BIN"), path]
				for texture in dict.fromkeys(textures):
					if texture.is_file(): uploads.extend(world.texture_uploads(texture.read_bytes(), vram, texture.relative_to(source).as_posix()))
				texture_path = work / (name + "_vram.bin"); texture_path.write_bytes(struct.pack("<3I8H", 2, len(vram), 1, 0, 0, 0, 0, 0, 0, 1024, 512) + bytes(20) + vram)
				destination = ROOT / "assets/levels" / stage / "models" / name if stage else ROOT / "assets/library" / path.parent.name.lower() / name
				destination.mkdir(parents=True, exist_ok=True)
				bulk_root = ROOT / "assets/levels" / stage / "models" if stage else ROOT / "assets/library"; (bulk_root / ".gdignore").touch(exist_ok=True)
				for model in archive["models"]:
					if not model.get("mesh_offset"): continue
					item = {"index": model["index"], "flags": model["flags"]}
					try:
						target = destination / ("model_%03d.glb" % model["index"])
						metadata = models.export_actor_model(payload, model["index"], texture_path, target) if model["mesh"]["bone_count"] else models.export_static_actor(payload, model["index"], texture_path, target, entry["file"])
						item.update(status="exported", file=target.relative_to(ROOT).as_posix(), export=metadata)
					except (ValueError, IndexError, KeyError, struct.error, OverflowError) as error: item.update(status="unsupported", error=str(error))
					entry["models"].append(item)
				entry.update(status="exported" if all(item["status"] == "exported" for item in entry["models"]) else "partial", texture_uploads=uploads, shared_prefix=archive.get("shared_prefix"), model_archive_offset=archive.get("model_archive_offset", 0))
				(destination / "manifest.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
			except (ValueError, IndexError, KeyError, struct.error, OverflowError) as error: entry.update(status="unsupported", error=str(error))
			report["model_archives"].append(entry)
def export_world(source, stages, report):
	for path in sorted((source / "DAT").glob("ST??.BIN")):
		stage = path.stem
		if stages and stage not in stages: continue
		entry = {"stage": stage, "file": path.relative_to(source).as_posix()}
		try:
			data = path.read_bytes()
			if len(data) < 48 or struct.unpack_from("<I", data)[0] != disc.ROOT_TYPE: entry.update(status="not_map_root"); report["stages"].append(entry); continue
			disc.extract_stage(path, ROOT / "build/maps")
			world.export_geometry(source / "DAT", ROOT / "assets/levels", [stage]); manifest = json.loads((ROOT / "assets/levels" / stage / "manifest.json").read_text())
			entry.update(status="exported", areas=len(manifest["areas"]), placements=sum(area["placements"] for area in manifest["areas"]))
			if stage in world.STAGE_BINDINGS: world.export_routes(source / "DAT", ROOT / "assets/levels", [stage])
			props = world.export_props(source / "DAT", ROOT / "assets/stage_props", [stage]); entry["binding_status"] = props["stages"][stage]["binding_status"]
		except (ValueError, IndexError, KeyError, struct.error, OverflowError, OSError) as error: entry.update(status="unsupported", error=str(error))
		report["stages"].append(entry)
def prepare(cue, source, stages, only, report_path=None):
	(ROOT / "build").mkdir(exist_ok=True); (ROOT / "build/.gdignore").touch(exist_ok=True)
	for directory in [ROOT / "assets" / name for name in ("library", "extracted", "converted")] + list((ROOT / "assets/levels").glob("*/models")):
		if directory.is_dir(): (directory / ".gdignore").touch(exist_ok=True)
	if set(only) & {"models", "textures", "audio", "media"}:
		library = ROOT / "assets/library"; library.mkdir(parents=True, exist_ok=True); (library / ".gdignore").touch(exist_ok=True)
	if cue is not None: disc.extract(cue, source, set(), reuse=True)
	if not source.is_dir(): raise FileNotFoundError("Extracted disc directory does not exist: " + str(source))
	report = {"files": catalog(source), "stages": [], "model_archives": [], "tasks": []}
	def task(name, function):
		try:
			result = function(); entry = {"name": name, "status": "exported"}
			if isinstance(result, (dict, list)): entry["details"] = result
			report["tasks"].append(entry)
		except (OSError, ValueError, RuntimeError, IndexError, KeyError, struct.error, OverflowError) as error: report["tasks"].append({"name": name, "status": "unsupported", "error": str(error)})
	if "world" in only: export_world(source, stages, report)
	if "textures" in only: task("textures", lambda: world.export_texture_library(source, ROOT / "assets/library/textures"))
	if "models" in only: export_models(source, stages, report); task("player", models.export_player); task("player_library", lambda: models.export_player_library(ROOT / "assets/library/players"))
	if "ui" in only:
		for name, function in [("hud", ui.hud_cli), ("projectile", ui.export_projectile), ("menu", ui.export_menu), ("dialogue", ui.export_dialogue)]: task(name, function)
		task("fades", lambda: native_fades.export(source, ROOT / "assets/fades"))
	if "audio" in only: task("audio", lambda: audio.export_audio(cue)); task("audio_library", lambda: audio.export_library(source, ROOT / "assets/library/audio")); task("zone_audio", lambda: audio.export_zone_audio(source))
	if "cinematics" in only: task("opening", cinematics.export_opening); task("opening_effects", cinematics.export_opening_effects)
	if "media" in only:
		if cue is None: report["tasks"].append({"name": "disc_media", "status": "requires_disc", "error": "The original CUE is required for raw XA and STR sectors"})
		else: task("opening_audio", lambda: audio.export_opening_audio(cue)); task("xa_library", lambda: audio.export_xa_library(cue, ROOT / "assets/library/voices")); task("movies", lambda: disc.export_movies(cue))
	if "world" in only and (not stages or "ST0F" in stages): task("mine_doors", lambda: models.export_doors(source / "DAT", ROOT / "build/maps", ROOT / "assets/levels/ST0F")); task("minimap", lambda: world.export_minimap(source / "DAT", ROOT / "build/maps", ROOT / "assets/minimap/ST0F"))
	if "world" in only:
		for npc_stage in ["ST0F", *models.NPC_STAGE_BINDINGS]:
			if not stages or npc_stage in stages: task("npcs_" + npc_stage, lambda npc_stage=npc_stage: models.export_npcs(source / "DAT", ROOT / "assets/levels" / npc_stage, npc_stage))
	if "world" in only:
		for scripted_stage in ["ST04", "ST08", *models.INTERIOR_SCRIPT_BINDINGS]:
			if not stages or scripted_stage in stages: task("scripted_actors_" + scripted_stage, lambda scripted_stage=scripted_stage: models.export_stage_scripted_actors(source / "DAT", ROOT / "assets/levels" / scripted_stage, scripted_stage))
	if "world" in only: task("lighting", world.lighting_cli); task("depth_cue", lambda: world.export_depth_cue(source / "DAT", ROOT / "assets/levels")); task("weather", lambda: world.export_weather(source / "DAT", ROOT / "assets/weather"))
	if "world" in only: task("area_roofs", lambda: area_roofs.export(source / "DAT", ROOT / "assets/levels"))
	if "world" in only and all((ROOT / "assets/levels" / stage / "doors.json").is_file() for stage in world.STAGES): task("room_layout", lambda: world.export_room_layout(ROOT / "assets/levels", ROOT / "assets/locations/room_layout.json"))
	report["summary"] = {"source_files": len(report["files"]), "source_bytes": sum(item["bytes"] for item in report["files"]), "stages_exported": sum(item["status"] == "exported" for item in report["stages"]), "models_exported": sum(model["status"] == "exported" for archive in report["model_archives"] for model in archive["models"]), "unsupported": sum(item["status"] == "unsupported" for item in report["stages"] + report["model_archives"] + report["tasks"]) + sum(model["status"] == "unsupported" for archive in report["model_archives"] for model in archive["models"])}
	report_path = report_path or ROOT / "build/asset_coverage.json"; report_path.parent.mkdir(parents=True, exist_ok=True); report_path.write_text(json.dumps(report, indent=2), encoding="utf-8"); print(json.dumps(report["summary"], indent=2)); return report
def main():
	parser = argparse.ArgumentParser(description="Extract the complete disc and export its supported asset formats.")
	parser.add_argument("disc", type=Path, nargs="?")
	parser.add_argument("--source-dir", type=Path, default=ROOT / "build/disc-assets")
	parser.add_argument("--stage", action="append")
	parser.add_argument("--report", type=Path, default=ROOT / "build/asset_coverage.json")
	parser.add_argument("--only", action="append", choices=["world", "models", "textures", "ui", "audio", "cinematics", "media"])
	args = parser.parse_args()
	stages = {stage.upper() for stage in args.stage or []}
	if any(not re.fullmatch(r"ST[0-9A-F]{2}", stage) for stage in stages): parser.error("Stage IDs must be ST00 through STFF")
	sys.argv = [sys.argv[0]]
	try:
		report = prepare(args.disc.resolve() if args.disc else None, args.source_dir.resolve(), stages, set(args.only or ["world", "models", "textures", "ui", "audio", "cinematics", "media"]), args.report.resolve())
		if report["summary"]["unsupported"]: parser.exit(1, "Extraction has unresolved errors; inspect the coverage report.\n")
		if any(entry["status"] == "requires_disc" for entry in report["tasks"]): parser.exit(1, "Full media extraction requires the original CUE.\n")
	except (OSError, ValueError, RuntimeError, struct.error) as error:
		parser.exit(1, f"{error}\n")
if __name__ == "__main__": main()
