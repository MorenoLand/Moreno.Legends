extends Node
class_name NativeQuiz
const Behavior := preload("res://scripts/world/actors/native_npc_behavior.gd")
var gameplay: Node
var context: Dictionary
var data: Dictionary
var running := false
var last_row := -1
var label: Label
var choice := -1
var current_question := -1
func configure(owner_game: Node, flags_context: Dictionary, document: Dictionary) -> void:
	gameplay = owner_game; context = flags_context; data = document
	var bank: Dictionary = data["bank"]; var indexed := {}
	for entry: Dictionary in bank["messages"]: indexed[int(entry["index"])] = entry
	var event_script: Node = gameplay.event_script; event_script.catalog["banks"]["ST32Q"] = bank; event_script.catalog["entries"]["ST32Q"] = indexed
func _process(_delta: float) -> void:
	if running or not is_instance_valid(gameplay) or gameplay.get("loading") == true or bool(gameplay.dialogue_box.get("active")): return
	if _flag(int(data["scene_flag"])): _run()
func _flags() -> Dictionary: return context.get("event_flags", {})
func _flag(id: int) -> bool: return bool(_flags().get(id, _flags().get(str(id), false)))
func _write_flag(id: int, value: bool) -> void:
	var flags := _flags(); flags[id if flags.has(id) or not flags.has(str(id)) else str(id)] = value
func _show(stage: String, index: int) -> void: await gameplay.event_script.play_message(stage, index)
func _run() -> void:
	running = true
	var kind := 3
	for candidate in 3:
		if _flag(int(data["start_flags"][str(candidate)])): kind = candidate; break
	_write_flag(int(data["scene_flag"]), false)
	for candidate in 4: _write_flag(int(data["start_flags"][str(candidate)]), false)
	var progress: Dictionary = context.get("native_quiz_progress", {}); var slot := str(mini(kind, 2)); var saved := int(progress.get(slot, 0)); var wrong := saved >> 4; var passes := saved & 15
	var row := 0
	while true:
		row = Behavior.next_random(context) & (7 if kind < 2 else 15)
		if row != last_row: break
	last_row = row
	var total := int(data["totals"][str(kind)]); var base := int(data["message_bases"][str(kind)]); var answered := 0; var questions: Array = data["rows"][str(kind)][row]; var passed := false
	_hud(total - answered)
	var dialogue: Control = gameplay.dialogue_box
	dialogue.choice_completed.connect(_on_choice)
	while answered < total:
		var question := int(questions[answered]); choice = -1; current_question = question
		await _show("ST32Q", question)
		if choice + 1 == int(data["answers"][question]):
			answered += 1; _hud(total - answered)
			if answered >= total: break
			var message := base + 4
			if kind == 3: message = base + ({50: 0, 80: 1, 90: 2, 99: 3}[answered] if {50: 0, 80: 1, 90: 2, 99: 3}.has(answered) else 4)
			else: message = base if answered == total - 1 else base + 1
			await _show("ST32", message)
		else:
			wrong += 1
			var failure := base + 5 if kind == 3 and answered < 80 else base + 6 if kind == 3 else base + 3 if answered == total - 1 else base + 2
			await _show("ST32", failure); break
	if answered >= total:
		passed = true
		var prizes: Array = data["teacher_prize_flags"]
		if kind < 2 and passes < 4: _write_flag(int(prizes[kind * 4 + passes]), true)
		if kind < 2 and passes == 3: _write_flag(0x11e if kind == 0 else 0x11f, true)
		await _show("ST32", base + 7 if kind == 3 else base + 4 if kind == 2 or passes < 4 else base + 5)
		passes = 0 if kind == 3 else passes + 1
		if kind == 3: wrong = 0
	dialogue.choice_completed.disconnect(_on_choice)
	if kind == 2 and wrong >= 10: _write_flag(0x11d, true)
	progress[slot] = (mini(wrong, 15) << 4) | mini(passes, 15); context["native_quiz_progress"] = progress
	if is_instance_valid(label): label.queue_free()
	running = false
func _on_choice(index: int) -> void: choice = index
func _hud(left: int) -> void:
	var counter: Dictionary = data["counter"]
	if not is_instance_valid(label):
		label = Label.new(); label.mouse_filter = Control.MOUSE_FILTER_IGNORE; label.text = "Left:"; gameplay.get_node("HUD").add_child(label)
		var sheet := load("res://assets/levels/ST32/%s" % str(counter["file"])) as Texture2D
		for index in 3:
			var digit := TextureRect.new(); digit.name = "Digit%d" % index; digit.texture = AtlasTexture.new(); (digit.texture as AtlasTexture).atlas = sheet; digit.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; digit.mouse_filter = Control.MOUSE_FILTER_IGNORE; label.add_child(digit)
	var size: Vector2 = gameplay.get_viewport().get_visible_rect().size; var scale := size.y / 240.0; var origin := Vector2((size.x - 320.0 * scale) * 0.5, 0.0); var window: Array = counter["window"]
	label.position = origin + Vector2(float(window[0]) + 4.0, float(window[1]) + 4.0) * scale; label.add_theme_font_size_override("font_size", int(12.0 * scale)); label.size = Vector2(32.0, 14.0) * scale
	var digits := [left / 100, (left / 10) % 10, left % 10]; var suppress := true; var cell: Array = counter["digit_size"]
	for index in 3:
		var digit := label.get_node("Digit%d" % index) as TextureRect; suppress = suppress and digits[index] == 0 and index < 2; digit.visible = not suppress
		(digit.texture as AtlasTexture).region = Rect2(float(digits[index]) * float(cell[0]), 0.0, float(cell[0]), float(cell[1])); digit.position = Vector2(float(counter["origin"][0]) + float(counter["pitch"]) * index - float(label.position.x - origin.x) / scale, float(counter["origin"][1]) - float(label.position.y) / scale) * scale; digit.size = Vector2(float(cell[0]), float(cell[1])) * scale; digit.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
