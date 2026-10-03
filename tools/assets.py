import argparse
import fnmatch
import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path
import disc
from disc import write_output
ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
	"world": "stage geometry, collision, routes, props, NPCs, lighting, weather, minimaps, shops, location names and every stage-bound scene and mission (use with --stage)",
	"models": "player and player-variant models, special weapons and effects, every actor model archive",
	"textures": "texture upload library",
	"ui": "HUD, title menu, fonts, status menu, dialogue text, mission banner, game over, fades",
	"audio": "sound effects, music, stage and zone audio, scene audio",
	"cinematics": "opening scene, opening effects, Flutter introduction scene and player clips",
	"media": "raw XA voices, opening/intro audio and STR movies (needs the original CUE)",
}
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
				name = path.stem + "_%05X" % offset; normalized = work / (name + ".bin"); write_output(normalized, struct.pack("<3I", 10, len(payload), count) + bytes(36) + payload); archive, payload = models.actor_archive(normalized)
				vram = bytearray(1024 * 512 * 2); uploads = []
				textures = [source / "COMMON/PL00T.BIN", source / "DAT" / (stage + "T.BIN") if stage else path.with_name(path.stem.removesuffix("P000") + "T.BIN"), path]
				for texture in dict.fromkeys(textures):
					if texture.is_file(): uploads.extend(world.texture_uploads(texture.read_bytes(), vram, texture.relative_to(source).as_posix()))
				texture_path = work / (name + "_vram.bin"); write_output(texture_path, struct.pack("<3I8H", 2, len(vram), 1, 0, 0, 0, 0, 0, 0, 1024, 512) + bytes(20) + vram)
				destination = ROOT / "assets/levels" / stage / "models" / name if stage else ROOT / "assets/library" / path.parent.name.lower() / name
				destination.mkdir(parents=True, exist_ok=True)
				ignore_bulk()
				for model in archive["models"]:
					if not model.get("mesh_offset"): continue
					item = {"index": model["index"], "flags": model["flags"]}
					try:
						target = destination / ("model_%03d.glb" % model["index"])
						metadata = models.export_actor_model(payload, model["index"], texture_path, target) if model["mesh"]["bone_count"] else models.export_static_actor(payload, model["index"], texture_path, target, entry["file"])
						if model["mesh"]["bone_count"]: metadata["source_surfaces"] = cinematics.record_source(target, entry["file"], model["index"], payload); metadata["face_dims"] = list(payload[model["mesh_offset"] + 0x38:model["mesh_offset"] + 0x3C])
						metadata["native_scale_raw"] = list(struct.unpack_from("<3h", payload, model["mesh_offset"] + 0x30))
						item.update(status="exported", file=target.relative_to(ROOT).as_posix(), export=metadata)
					except (ValueError, IndexError, KeyError, struct.error, OverflowError) as error: item.update(status="unsupported", error=str(error))
					entry["models"].append(item)
				entry.update(status="exported" if all(item["status"] == "exported" for item in entry["models"]) else "partial", texture_uploads=uploads, shared_prefix=archive.get("shared_prefix"), model_archive_offset=archive.get("model_archive_offset", 0))
				write_output(destination / "manifest.json", json.dumps(entry, indent=2), encoding="utf-8")
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
		except (ValueError, IndexError, KeyError, struct.error, OverflowError, OSError) as error: entry.update(status="unsupported", error=str(error))
		report["stages"].append(entry)
def ignore_bulk():
	for directory in [ROOT / "assets" / name for name in ("library", "extracted", "converted", "audio")] + [ROOT / folder for folder in disc.RUNTIME_LOADED]:
		if directory.is_dir() and not (directory / ".gdignore").exists(): write_output(directory / ".gdignore", "")
def prune_sidecars():
	removed = 0
	for folder in disc.RUNTIME_LOADED:
		for sidecar in (ROOT / folder).rglob("*.import"):
			if disc.runtime_loaded(disc.relative_output(sidecar.with_suffix(""))): sidecar.unlink(); removed += 1
	return removed
def import_sidecars(prune=False):
	ignore_bulk(); written = 0; scanned = 0; removed = prune_sidecars() if prune else 0
	for current, folders, files in os.walk(ROOT / "assets"):
		if ".gdignore" in files: folders.clear(); continue
		if Path(current) == ROOT / "assets/achievements": folders.clear(); continue
		for name in files:
			if name.rsplit(".", 1)[-1].lower() in disc.IMPORT_PRESETS and not name.endswith(".import"): scanned += 1; written += bool(disc.write_import_settings(Path(current) / name))
	return {"assets": scanned, "sidecars_written": written, "sidecars_removed": removed}
def prepare(cue, source, stages, only, report_path=None, tasks=()):
	(ROOT / "build").mkdir(exist_ok=True); write_output(ROOT / "build/.gdignore", "")
	ignore_bulk()
	if set(only) & {"models", "textures", "audio", "media"}:
		library = ROOT / "assets/library"; library.mkdir(parents=True, exist_ok=True); write_output(library / ".gdignore", "")
	if cue is not None: disc.extract(cue, source, set(), reuse=True)
	if not source.is_dir(): raise FileNotFoundError("Extracted disc directory does not exist: " + str(source))
	report = {"files": [] if tasks else catalog(source), "stages": [], "model_archives": [], "tasks": []}
	def task(name, function):
		if tasks and not any(fnmatch.fnmatch(name, pattern) for pattern in tasks): return
		try:
			result = function(); entry = {"name": name, "status": "exported"}
			if isinstance(result, (dict, list)): entry["details"] = result
			report["tasks"].append(entry)
		except (OSError, ValueError, RuntimeError, IndexError, KeyError, struct.error, OverflowError) as error: report["tasks"].append({"name": name, "status": "unsupported", "error": str(error)})
	if "world" in only:
		task("location_names", world.export_location_names)
		if not tasks: export_world(source, stages, report)
		map_stages = [entry["stage"] for entry in report["stages"] if entry["status"] == "exported"]
		if "ST0F" in map_stages: task("mine_doors", lambda: models.export_doors(source / "DAT", ROOT / "build/maps", ROOT / "assets/levels/ST0F"))
		task("routes", lambda: world.export_routes(source / "DAT", ROOT / "assets/levels", map_stages))
		for entry in report["stages"]:
			if entry["status"] != "exported": continue
			stage = entry["stage"]; task("props_" + stage, lambda stage=stage: {"binding_status": world.export_props(source / "DAT", ROOT / "assets/stage_props", [stage])["stages"][stage]["binding_status"]})
			if report["tasks"][-1]["status"] == "exported": entry["binding_status"] = report["tasks"][-1]["details"]["binding_status"]
	if "textures" in only: task("textures", lambda: world.export_texture_library(source, ROOT / "assets/library/textures"))
	if "models" in only:
		if not tasks: export_models(source, stages, report)
		task("player", models.export_player); task("outfits", models.export_outfits); task("special_weapon_0f", models.export_extinguisher); task("player_effects", models.export_player_effects); task("special_modes", models.export_special_modes); task("weapon_stats", models.export_weapon_stats); task("special_weapon_05", lambda: models.export_special_weapon(5)); task("special_weapon_06", lambda: models.export_special_weapon(6)); task("special_weapon_0e", lambda: models.export_special_weapon(14)); task("special_weapon_03", lambda: models.export_special_weapon(3)); task("special_weapon_04", lambda: models.export_special_weapon(4)); task("special_weapon_10", lambda: models.export_special_weapon(16)); task("special_weapon_07", lambda: models.export_special_weapon(7)); task("special_weapon_08", lambda: models.export_special_weapon(8)); task("special_weapon_09", lambda: models.export_special_weapon(9)); task("special_weapon_0a", lambda: models.export_special_weapon(10)); task("special_weapon_0b", lambda: models.export_special_weapon(11)); task("special_weapon_0c", lambda: models.export_special_weapon(12)); task("special_weapon_11", lambda: models.export_special_weapon(17)); task("special_weapon_0d", lambda: models.export_special_weapon(13)); task("player_library", lambda: models.export_player_library(ROOT / "assets/library/players"))
	if set(only) & {"world", "models"} and (not stages or "ST11" in stages): task("icefield_effects", models.export_icefield_effects)
	if set(only) & {"world", "models"} and (not stages or "ST1D" in stages): task("arena_barriers", models.export_arena_barriers)
	for clip_stage in ("ST1C", "ST25", "ST46"):
		if "world" in only and (not stages or clip_stage in stages): task("player_clips_" + clip_stage, lambda clip_stage=clip_stage: cinematics.export_scene_player_clips(clip_stage))
	if "models" in only and (not stages or stages & set(models.RUNNER_STAGES)): task("runner", lambda: models.export_runner(stages or None))
	if "ui" in only:
		for name, function in [("hud", ui.hud_cli), ("projectile", ui.export_projectile), ("menu", ui.export_menu), ("dialogue", ui.export_dialogue), ("mission_banner", ui.export_mission_banner), ("game_over", ui.export_game_over), ("title_font", ui.export_title_font)]: task(name, function)
		task("fades", lambda: ui.export_fades(source, ROOT / "assets/fades")); task("slot_symbols", ui.export_slot_symbols)
	if "audio" in only: task("audio", lambda: audio.export_audio(cue)); task("audio_library", lambda: audio.export_library(source, ROOT / "assets/library/audio")); task("zone_audio", lambda: audio.export_zone_audio(source)); task("game_over_audio", audio.export_game_over_audio)
	if "audio" in only and cue is not None and (not stages or "ST0B" in stages): task("scene_audio", lambda: cinematics.export_scene_audio(cue, source / "DAT", ROOT / "assets/levels/ST0B/audio"))
	if "cinematics" in only: task("opening", cinematics.export_opening); task("opening_effects", cinematics.export_opening_effects); task("intro_scene", cinematics.export_intro_scene); task("intro_player", lambda: cinematics.export_scene_player_clips("ST39"))
	if "media" in only:
		if cue is None: report["tasks"].append({"name": "disc_media", "status": "requires_disc", "error": "The original CUE is required for raw XA and STR sectors"})
		else: task("opening_audio", lambda: audio.export_opening_audio(cue)); task("intro_audio", lambda: cinematics.export_intro_audio(cue)); task("stage_voices", lambda: [audio.export_stage_voices(cue, "COMMON")] + [audio.export_stage_voices(cue, path.name) for path in sorted((ROOT / "assets/levels").glob("ST??")) if (not stages or path.name in stages) and audio.stage_voice_tables(path.name)[1]]);task("xa_library", lambda: audio.export_xa_library(cue, ROOT / "assets/library/voices")); task("movies", lambda: disc.export_movies(cue))
	if "world" in only and (not stages or "ST0F" in stages): task("minimap", lambda: world.export_minimap(source / "DAT", ROOT / "build/maps", ROOT / "assets/minimap/ST0F"))
	if "world" in only:
		for npc_stage in ["ST0F", *models.NPC_STAGE_BINDINGS]:
			if not stages or npc_stage in stages: task("npcs_" + npc_stage, lambda npc_stage=npc_stage: models.export_npcs(source / "DAT", ROOT / "assets/levels" / npc_stage, npc_stage))
	if "world" in only:
		for scripted_stage in ["ST04", "ST08", *models.INTERIOR_SCRIPT_BINDINGS]:
			if not stages or scripted_stage in stages: task("scripted_actors_" + scripted_stage, lambda scripted_stage=scripted_stage: models.export_stage_scripted_actors(source / "DAT", ROOT / "assets/levels" / scripted_stage, scripted_stage))
	if "world" in only and (not stages or "ST1E" in stages): task("fire_mission", cinematics.export_fire_mission)
	if "world" in only and (not stages or "ST3A" in stages): task("flight_scene", cinematics.export_flight_scene)
	if "world" in only and (not stages or "ST08" in stages): task("landing_scene", cinematics.export_landing_scene)
	if "world" in only and (not stages or "ST49" in stages): task("dropship_scene", cinematics.export_dropship_scene)
	if "world" in only and (not stages or "ST04" in stages): task("flutter_scene", cinematics.export_flutter_scene)
	if "world" in only and (not stages or "ST08" in stages): task("joe_workshop_scene", cinematics.export_joe_scene)
	if "world" in only and (not stages or any(stage in stages for stage in ["ST0D", "ST0F"])): task("mine_quest", lambda: world.export_mine_quest(source / "DAT", ROOT / "assets/levels"))
	if "world" in only and (not stages or "ST0F" in stages): task("mine_scenes", cinematics.export_mine_scenes)
	if "world" in only: task("dungeon_lifts", lambda: world.export_dungeon_lifts(source / "DAT", stages))
	if "world" in only and (not stages or "ST32" in stages): task("quiz", lambda: world.export_quiz(source / "DAT", ROOT / "assets/levels"))
	if "world" in only and (not stages or any(stage in stages for stage in ["ST14", "ST28", "ST48", "ST5B"])): task("area_controllers", lambda: world.export_area_controllers(source / "DAT", stages))
	if "world" in only and (not stages or any(stage in stages for stage in ["ST00", "ST1F", "ST20", "ST22", "ST23", "ST48", "ST4C", "ST5B"])): task("vram_animations", lambda: world.export_vram_animations(source / "DAT", stages))
	if "world" in only and (not stages or any(stage in stages for stage in ["ST41", "ST42"])): task("gravity_gates", lambda: world.export_gravity_gates(source / "DAT", stages))
	if "world" in only and (not stages or "ST11" in stages): task("icefield_scene", cinematics.export_icefield_scene)
	if "world" in only and (not stages or "ST0F" in stages): task("mine_effects", models.export_mine_effects)
	if "world" in only and (not stages or "ST01" in stages): task("flutter_travel", world.export_flutter_travel)
	if "world" in only and (not stages or "ST09" in stages): task("yosyonke_scene", cinematics.export_yosyonke_scene)
	if "world" in only and (not stages or "ST47" in stages): task("joseph_room_scene", cinematics.export_joseph_room_scene)
	if "world" in only and (not stages or any(stage in stages for stage in world.SHOP_STAGES)): task("shops", world.export_shops)
	if "world" in only and (not stages or world.DEVELOPMENT_STAGE in stages): task("development", world.export_development)
	if "world" in only and not stages: task("actor_coverage", world.export_actor_coverage)
	if "world" in only: task("lighting", world.lighting_cli); task("depth_cue", lambda: world.export_depth_cue(source / "DAT", ROOT / "assets/levels")); task("weather", lambda: world.export_weather(source / "DAT", ROOT / "assets/weather"))
	if "world" in only: task("area_roofs", lambda: world.export_area_roofs(source / "DAT", ROOT / "assets/levels"))
	if "world" in only: task("stage_regions", lambda: world.export_stage_regions(ROOT / "assets/locations/stage_regions.json"))
	if "world" in only: task("bitmap_minimaps", lambda: world.export_bitmap_minimaps(source / "DAT", ROOT / "assets/minimap", stages))
	if "world" in only and (not stages or stages & set(world.FLUTTER_MAP_STAGES)): task("flutter_map", lambda: world.export_flutter_map(source / "DAT", ROOT / "assets/minimap/Flutter"))
	if "world" in only and all((ROOT / "assets/levels" / stage / "doors.json").is_file() for stage in world.STAGES): task("room_layout", lambda: world.export_room_layout(ROOT / "assets/levels", ROOT / "assets/locations/room_layout.json"))
	for layout, layout_stages in world.TOWN_LAYOUTS.items():
		if "world" in only and all((ROOT / "assets/levels" / stage / "doors.json").is_file() for stage in layout_stages): task(layout + "_room_layout", lambda layout=layout, layout_stages=layout_stages: world.export_room_layout(ROOT / "assets/levels", ROOT / "assets/locations" / (layout + "_room_layout.json"), layout_stages))
	if "world" in only and (ROOT / "assets/levels/ST0F/doors.json").is_file(): task("mine_room_layout", lambda: world.export_room_layout(ROOT / "assets/levels", ROOT / "assets/locations/mine_room_layout.json", ("ST0F",)))
	if "world" in only and (ROOT / "assets/levels/ST08/doors.json").is_file(): task("landing_room_layout", lambda: world.export_room_layout(ROOT / "assets/levels", ROOT / "assets/locations/landing_room_layout.json", ("ST08",)))
	ignore_bulk()
	report["summary"] = {"source_files": len(report["files"]), "source_bytes": sum(item["bytes"] for item in report["files"]), "stages_exported": sum(item["status"] == "exported" for item in report["stages"]), "models_exported": sum(model["status"] == "exported" for archive in report["model_archives"] for model in archive["models"]), "unsupported": sum(item["status"] == "unsupported" for item in report["stages"] + report["model_archives"] + report["tasks"]) + sum(model["status"] == "unsupported" for archive in report["model_archives"] for model in archive["models"])}
	report_path = report_path or ROOT / "build/asset_coverage.json"; report_path.parent.mkdir(parents=True, exist_ok=True); write_output(report_path, json.dumps(report, indent=2), encoding="utf-8"); print(json.dumps(report["summary"], indent=2)); return report
def main():
	global audio, cinematics, models, ui, world
	parser = argparse.ArgumentParser(description="Extract the complete disc and export its supported asset formats. Existing output files are kept unless an overwrite flag allows replacing them.", formatter_class=argparse.RawDescriptionHelpFormatter, epilog="groups for --only:\n" + "\n".join(f"  {name:<11}{text}" for name, text in GROUPS.items()) + "\n\nexamples:\n  python tools/assets.py path/to/disc.cue\n  python tools/assets.py --only ui --only audio\n  python tools/assets.py --stage ST10 --overwrite-only \"assets/levels/ST10/**\"\n  python tools/assets.py path/to/disc.cue --overwrite")
	parser.add_argument("disc", type=Path, nargs="?", help="PAL SLES-03556 disc image (.cue); omit to reuse the already extracted --source-dir")
	parser.add_argument("--source-dir", type=Path, default=ROOT / "build/disc-assets", help="directory that receives the extracted disc files (default: build/disc-assets)")
	parser.add_argument("--stage", action="append", help="limit stage-bound exports to this stage, e.g. ST10 (repeatable)")
	parser.add_argument("--report", type=Path, default=ROOT / "build/asset_coverage.json", help="coverage report path")
	parser.add_argument("--only", action="append", choices=list(GROUPS), help="run only this export group (repeatable; default: all groups)")
	parser.add_argument("--overwrite", action="store_true", help="replace every existing output file")
	parser.add_argument("--task", action="append", default=[], metavar="NAME", help="run only the tasks whose name matches this glob, e.g. '*_room_layout' (repeatable; skips the per-stage geometry pass and reads earlier output)")
	parser.add_argument("--overwrite-only", action="append", default=[], metavar="PATTERN", help="replace only existing files matching this glob relative to the repository root, e.g. 'assets/dialogue/*' or 'assets/levels/ST10/**' (repeatable)")
	parser.add_argument("--import-sidecars", action="store_true", help="only write Redot .import presets and .gdignore markers for assets already in assets/ (no disc needed); existing sidecars are kept unless --overwrite or a matching --overwrite-only pattern such as 'assets/**/*.import' allows retrofitting them")
	parser.add_argument("--prune-sidecars", action="store_true", help="with --import-sidecars: delete the stale .import files of GLB/PNG assets under the runtime-loaded folders (assets/levels, stage_props, opening, flutter, minimap); the game loads those files directly")
	parser.add_argument("--convert-audio", action="store_true", help="only convert the WAV files already in assets/ to Ogg Vorbis (no disc needed): each .ogg is written next to its .wav (existing .ogg files are kept unless --overwrite or a matching --overwrite-only pattern succeeds), decoded and length-checked, the manifests are rewritten to the .ogg paths, and a .wav is deleted only after its .ogg verified")
	parser.add_argument("--verbose", action="store_true", help="print every kept file")
	args = parser.parse_args()
	disc.configure_overwrite(args.overwrite, args.overwrite_only, args.verbose)
	if args.import_sidecars: print(json.dumps(import_sidecars(args.prune_sidecars))); print(disc.kept_summary() or ""); return
	if args.convert_audio:
		import audio; result = audio.convert_audio(); print(json.dumps(result, indent=2)); print(disc.kept_summary() or "")
		if result["failed"]: parser.exit(1, "Some WAV files were not converted; they were kept.\n")
		return
	import audio, cinematics, models, ui, world
	stages = {stage.upper() for stage in args.stage or []}
	if any(not re.fullmatch(r"ST[0-9A-F]{2}", stage) for stage in stages): parser.error("Stage IDs must be ST00 through STFF")
	sys.argv = [sys.argv[0]]
	try:
		report = prepare(args.disc.resolve() if args.disc else None, args.source_dir.resolve(), stages, set(args.only or ["world", "models", "textures", "ui", "audio", "cinematics", "media"]), args.report.resolve(), tuple(args.task))
		if disc.kept_summary(): print(disc.kept_summary())
		if report["summary"]["unsupported"]: parser.exit(1, "Extraction has unresolved errors; inspect the coverage report.\n")
		if any(entry["status"] == "requires_disc" for entry in report["tasks"]): parser.exit(1, "Full media extraction requires the original CUE.\n")
	except (OSError, ValueError, RuntimeError, struct.error) as error:
		parser.exit(1, f"{error}\n")

if __name__ == "__main__": main()
