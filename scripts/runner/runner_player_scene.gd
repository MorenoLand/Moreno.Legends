extends Node
## Mega Man in a runner scene: the stage's scene player bank (assets/levels/STxx/player_scene.json, controls 0x80 and up) poses the port player from the original player struct (control +0xA0, record +0x9C) and the struct's render flag (byte 0, bit 1) shows the model.

const Clock := preload("res://scripts/world/actors/native_animation.gd")
const PLAYER := 0x8008C0A0
const RENDER_FLAG := 2
const FIRST_CONTROL := 0x80
const EYES := 0x1A0
const MOUTH := 0x1A1
const FACE_PAGE := "res://assets/levels/ST39/player_face_page1.png"

var player: CharacterBody3D
var clock: Node
var control := -1
var saved_motion := false
var faces: Array = []
var face_page: Texture2D
var frames := [-1, -1]


static func available(stage_name: String) -> bool:
	return FileAccess.file_exists("res://assets/levels/%s/player_scene.json" % stage_name)


func open(gameplay: Node, stage_name: String) -> bool:
	player = gameplay.player
	var directory := "res://assets/levels/%s/" % stage_name
	var bank: Variant = JSON.parse_string(FileAccess.get_file_as_string(directory + "player_scene.json"))
	if not bank is Dictionary:
		return false
	var library := str(bank["library"])
	if not player.animation_player.has_animation_library(library):
		var packed := load(directory + str(bank["model"])) as PackedScene
		if packed == null:
			return false
		var instance := packed.instantiate()
		var players: Array[Node] = instance.find_children("*", "AnimationPlayer", true, false)
		if players.is_empty():
			instance.free()
			return false
		player.animation_player.add_animation_library(library, (players[0] as AnimationPlayer).get_animation_library("").duplicate(true))
		instance.free()
	var clips: Array = []
	for clip: Dictionary in bank["clips"]:
		var adapted: Dictionary = clip.duplicate(true)
		adapted["name"] = library + "/" + str(clip["name"])
		clips.append(adapted)
	clock = Clock.new()
	clock.automatic = false
	add_child(clock)
	face_page = load(FACE_PAGE) as Texture2D if ResourceLoader.exists(FACE_PAGE) else null
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/player/manifest.json"))
	var meshes: Array[Node] = player.player_model.find_children("*", "MeshInstance3D", true, false)
	if manifest is Dictionary and not meshes.is_empty():
		var mesh := meshes[0] as MeshInstance3D
		for source: Dictionary in manifest.get("faceSurfaces", []):
			var material := mesh.get_surface_override_material(int(source["surface"])) as ShaderMaterial if int(source["surface"]) < mesh.mesh.get_surface_count() else null
			if material != null:
				faces.append({"stream": int(source["uv_stream"]), "material": material, "texture": material.get_shader_parameter("albedo_texture")})
	return clock.configure(player.animation_player, clips)


func begin() -> void:
	saved_motion = player.motion_tree != null and player.motion_tree.active
	if player.motion_tree != null:
		player.motion_tree.active = false


func sync(machine) -> void:
	player.player_model.visible = machine.u8(PLAYER) & RENDER_FLAG != 0
	var current: int = machine.u8(PLAYER + 0xA0)
	if current != control and current >= FIRST_CONTROL:
		control = current
		clock.play_control(current, machine.u8(PLAYER + 0x9C))
	clock.native_tick()
	for channel in 2:
		var frame: int = machine.u8(PLAYER + (EYES if channel == 0 else MOUTH))
		if frame != frames[channel]:
			frames[channel] = frame
			_face(channel + 1, frame)


func _face(stream: int, frame: int) -> void:
	var cell := frame % 20
	var page := frame / 20
	for surface: Dictionary in faces:
		if int(surface["stream"]) != stream:
			continue
		var material: ShaderMaterial = surface["material"]
		material.set_shader_parameter("uv_word", (cell % 4) * 64 | ((cell / 4) * 51) << 8)
		material.set_shader_parameter("albedo_texture", face_page if page == 1 and face_page != null else surface["texture"])


func end() -> void:
	for surface: Dictionary in faces:
		(surface["material"] as ShaderMaterial).set_shader_parameter("uv_word", 0)
		(surface["material"] as ShaderMaterial).set_shader_parameter("albedo_texture", surface["texture"])
	if player.motion_tree != null:
		player.motion_tree.active = saved_motion
