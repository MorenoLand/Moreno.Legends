extends CanvasLayer
# F1 performance overlay: frame rate, tick rate, frame/physics time and scene counters, refreshed twice a second.
var host: Node
var label: Label
var elapsed := 0.0
var frames := 0
var physics_ticks := 0
var worst_frame := 0.0
func configure(menu: Node) -> void:
	host = menu; layer = 128; visible = false; process_mode = Node.PROCESS_MODE_ALWAYS
	var panel := PanelContainer.new(); panel.position = Vector2(8, 8); panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new(); style.bg_color = Color(0, 0, 0, 0.6); style.set_content_margin_all(6); panel.add_theme_stylebox_override("panel", style); add_child(panel)
	label = Label.new(); label.add_theme_font_size_override("font_size", 14); label.add_theme_constant_override("line_spacing", 0); panel.add_child(label)
func toggle() -> void:
	visible = not visible; elapsed = 0.0; frames = 0; physics_ticks = 0; worst_frame = 0.0
	if visible: _refresh()
func _process(delta: float) -> void:
	if not visible: return
	elapsed += delta; frames += 1; worst_frame = maxf(worst_frame, delta)
	if elapsed >= 0.5: _refresh()
func _physics_process(_delta: float) -> void:
	if visible: physics_ticks += 1
func _refresh() -> void:
	var fps := frames / elapsed if elapsed > 0.0 else Engine.get_frames_per_second(); var tps := physics_ticks / elapsed if elapsed > 0.0 else 0.0
	var lines := PackedStringArray([
		"FPS %.0f   TPS %.0f / %d" % [fps, tps, Engine.physics_ticks_per_second],
		"Frame %.2f ms   worst %.2f ms" % [1000.0 / maxf(fps, 0.001), worst_frame * 1000.0],
		"Process %.2f ms   Physics %.2f ms" % [Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0, Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0],
		"Draw calls %d   Objects %d   Primitives %d" % [RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME), RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME), RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)],
		"Nodes %d   Orphans %d   Physics bodies %d" % [Performance.get_monitor(Performance.OBJECT_NODE_COUNT), Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT), Performance.get_monitor(Performance.PHYSICS_3D_ACTIVE_OBJECTS)],
		"Memory %.1f MB   Video %.1f MB" % [Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0]])
	var gameplay: Variant = host.get("gameplay") if is_instance_valid(host) else null
	if gameplay is Node3D and is_instance_valid(gameplay) and is_instance_valid(gameplay.get("player")):
		var areas: Array = gameplay.get("areas"); var picker: OptionButton = gameplay.get("area_picker"); var point: Vector3 = gameplay.player.global_position
		var area := int(areas[picker.selected]["index"]) if picker != null and picker.selected >= 0 and picker.selected < areas.size() else -1
		lines.append("%s area %d   pos %.2f, %.2f, %.2f" % [str(gameplay.get("manifest_path")).get_base_dir().get_file(), area, point.x, point.y, point.z])
	label.text = "\n".join(lines); elapsed = 0.0; frames = 0; physics_ticks = 0; worst_frame = 0.0
