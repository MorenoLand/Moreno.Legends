extends Control
# Port-only extra: playable slot machine for the Ruminoa City Restaurant prop (ST1A message 85). Reels reuse the status atlas item icons.
signal closed
const FRAME := preload("res://scripts/ui/common/native_menu_frame.gd")
const STAGE := "ST1A"
const MESSAGE := 85
const BETS := [10, 50, 100]
const STRIP := [0, 1, 0, 2, 0, 1, 3, 0, 1, 2, 0, 4, 1, 2, 3, 5]
const ICONS := [Vector2(0x80, 0), Vector2(0x90, 0), Vector2(0xa0, 0), Vector2(0xb0, 0), Vector2(0xc0, 0x10), Vector2(0x70, 0x10)]
const MULTIPLIERS := [6, 10, 20, 40, 100, 500]
const SPEED := 20.0
const PITCH := 32.0
const GOLD := Color8(255, 222, 99)
const TAN := Color(0.72, 0.68, 0.52)
class Reel extends Control:
	var atlas: Texture2D
	var position_index := 0.0
	var lit := false
	func _draw() -> void:
		var base := floori(position_index + 0.5); var shift := (position_index - float(base)) * PITCH; var middle := size.y * 0.5 - PITCH * 0.5
		for row in range(-2, 3): draw_texture_rect_region(atlas, Rect2(4, middle + float(row) * PITCH - shift, 32, 32), Rect2(ICONS[STRIP[posmod(base + row, STRIP.size())]], Vector2(16, 16)))
		draw_rect(Rect2(0, middle, size.x, PITCH), GOLD if lit else Color(1, 1, 1, 0.35), false, 1.0)
var host: Node
var layout: Dictionary = {}
var font: Font
var atlas: Texture2D
var surface: Control
var reels: Array[Reel] = []
var states: Array[Dictionary] = []
var targets: Array[int] = []
var bet_index := 0
var phase := "idle"
var elapsed := 0.0
var flash := 0.0
var last_win := -1
var notice := ""
var ready_for_input := false
var rng := RandomNumberGenerator.new()
static func enabled() -> bool:
	var settings := ConfigFile.new(); settings.load("user://settings.cfg")
	return bool(settings.get_value("extras", "slot_machine", true))
static func applies(stage: String, index: int) -> bool:
	return stage == STAGE and index == MESSAGE and enabled()
static func payout(symbols: Array, bet: int) -> int:
	if symbols[0] == symbols[1] and symbols[1] == symbols[2]: return bet * int(MULTIPLIERS[symbols[0]])
	return bet if symbols.count(0) == 2 else 0
static func play(gameplay: Node, parent: Control) -> void:
	var confirmation := preload("res://scripts/ui/menus/confirmation_menu.gd").new(); parent.add_child(confirmation); confirmation.configure("Play? (bet zenny)")
	var answer := [false]; var done := [false]
	confirmation.confirmed.connect(func(): gameplay.audio.play_ui("menu_confirm"); answer[0] = true; done[0] = true); confirmation.cancelled.connect(func(): gameplay.audio.play_ui("menu_cancel"); done[0] = true); confirmation.moved.connect(func(): gameplay.audio.play_ui("menu_move"))
	await confirmation.animate_enter("gameplay")
	while not done[0] and is_instance_valid(confirmation) and gameplay.is_inside_tree(): await gameplay.get_tree().process_frame
	if is_instance_valid(confirmation): await confirmation.animate_exit("gameplay"); confirmation.queue_free()
	if not answer[0] or not gameplay.is_inside_tree(): return
	var machine := new(); parent.add_child(machine); await machine.run(gameplay)
	if is_instance_valid(machine): machine.queue_free()
func run(gameplay: Node) -> void:
	host = gameplay; layout = host.dialogue_box.layout; font = host.dialogue_box.font; atlas = load("res://assets/menu/status_normal_atlas.png") as Texture2D; rng.randomize()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; z_index = 20
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface)
	for index in 3:
		var reel := Reel.new(); reel.atlas = atlas; reel.mouse_filter = Control.MOUSE_FILTER_IGNORE; reel.clip_contents = true; reel.position = Vector2(36 + index * 46, 40); reel.size = Vector2(40, PITCH * 3.0); reel.position_index = float(rng.randi_range(0, STRIP.size() - 1)); surface.add_child(reel); reels.append(reel); states.append({"mode": "stopped"}); targets.append(0)
	resized.connect(_layout); _layout(); _fit_bet(); surface.hide()
	if await FRAME.enter(self, layout, "gameplay"): surface.show()
	ready_for_input = true; await closed
	ready_for_input = false; surface.hide(); await FRAME.exit(self, layout, "gameplay")
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); surface.size = Vector2(320, 240); queue_redraw()
func _fit_bet() -> void:
	while bet_index > 0 and int(host.player.zenny) < BETS[bet_index]: bet_index -= 1
func _set_zenny(value: int) -> void:
	host.player.zenny = maxi(value, 0); host.native_context["native_wallet"] = host.player.zenny
func _spin() -> void:
	var bet: int = BETS[bet_index]
	if int(host.player.zenny) < bet: notice = "Not enough zenny."; host.audio.play_ui("menu_cancel"); return
	_set_zenny(int(host.player.zenny) - bet); phase = "spin"; elapsed = 0.0; last_win = -1; notice = ""; host.audio.play_ui("menu_confirm")
	for index in 3: targets[index] = rng.randi_range(0, STRIP.size() - 1); states[index] = {"mode": "spin", "stop_at": 1.0 + 0.5 * index}; reels[index].lit = false
func _stop_next() -> void:
	for index in 3:
		if states[index]["mode"] == "spin": states[index]["stop_at"] = 0.0; return
func _final(index: int) -> float:
	var count := float(STRIP.size())
	return float(targets[index]) + count * floorf((reels[index].position_index - 3.0 - float(targets[index])) / count)
func advance(delta: float) -> void:
	if phase != "spin": return
	elapsed += delta; var moving := false
	for index in 3:
		var state: Dictionary = states[index]; var reel := reels[index]
		match state["mode"]:
			"spin":
				reel.position_index -= SPEED * delta; moving = true
				if elapsed >= float(state["stop_at"]): state["mode"] = "seek"; state["to"] = _final(index)
			"seek":
				reel.position_index -= SPEED * delta; moving = true; var final: float = state["to"]
				if reel.position_index - final <= 3.0: state["mode"] = "ease"; state["from"] = reel.position_index; state["to"] = final; state["time"] = 0.0; state["length"] = 2.0 * (reel.position_index - final) / SPEED
			"ease":
				moving = true; state["time"] = float(state["time"]) + delta; var progress := minf(float(state["time"]) / maxf(float(state["length"]), 0.001), 1.0)
				reel.position_index = float(state["to"]) + (float(state["from"]) - float(state["to"])) * (1.0 - progress) * (1.0 - progress)
				if progress >= 1.0: state["mode"] = "stopped"; reel.position_index = float(state["to"]); host.audio.play_ui("menu_move")
	if not moving: _resolve()
func _process(delta: float) -> void:
	if ready_for_input: flash += delta; advance(delta)
	queue_redraw()
	for reel in reels: reel.queue_redraw()
func _resolve() -> void:
	var symbols: Array = []
	for index in 3: symbols.append(STRIP[targets[index]])
	var bet: int = BETS[bet_index]; var win := payout(symbols, bet); phase = "idle"; flash = 0.0; last_win = win; _set_zenny(int(host.player.zenny) + win)
	for reel in reels: reel.lit = win > 0
	if win >= bet * 20: host.audio.play_sound(0xEF)
	elif win > 0: host.audio.play_ui("menu_confirm")
	else: host.audio.play_ui("menu_cancel")
	notice = "Jackpot! " if win >= bet * 100 else ""
	_fit_bet()
	if int(host.player.zenny) < BETS[0]: notice += "Out of zenny."
func handle(event: InputEvent) -> bool:
	if not ready_for_input or event.is_echo() or not event.is_pressed(): return false
	if event.is_action_pressed("ui_cancel"):
		if phase == "idle": host.audio.play_ui("menu_cancel"); closed.emit()
	elif event.is_action_pressed("ui_accept"):
		if phase == "spin": _stop_next()
		else: _spin()
	elif event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right"):
		if phase == "idle":
			var next := clampi(bet_index + (1 if event.is_action_pressed("ui_right") else -1), 0, BETS.size() - 1)
			if int(host.player.zenny) < BETS[next]: notice = "Not enough zenny."; host.audio.play_ui("menu_cancel")
			elif next != bet_index: bet_index = next; notice = ""; host.audio.play_ui("menu_move")
	else: return false
	return true
func _input(event: InputEvent) -> void:
	if handle(event): get_viewport().set_input_as_handled()
func _zenny_text(value: int) -> String:
	var digits := str(value); return "".repeat(maxi(7 - digits.length(), 0)) + digits + ""
func _text(value: String, point: Vector2, font_size: int = 9, color: Color = Color.WHITE, width: float = -1.0, alignment: int = HORIZONTAL_ALIGNMENT_LEFT) -> void:
	draw_string(font, point + Vector2(0, font.get_ascent(font_size)), value, alignment, width, font_size, color)
func _icons(symbol: int, origin: Vector2, count: int) -> void:
	for column in count: draw_texture_rect_region(atlas, Rect2(origin + Vector2(column * 12, 0), Vector2(12, 12)), Rect2(ICONS[symbol], Vector2(16, 16)))
func _draw() -> void:
	if layout.is_empty() or size.y <= 0 or font == null: return
	var factor: float = size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "header", Rect2(20, 4, 112, 22)); FRAME.draw(self, layout, "prompt", Rect2(20, 28, 280, 112)); FRAME.draw(self, layout, "prompt", Rect2(20, 144, 280, 68)); FRAME.draw(self, layout, "prompt", Rect2(36, 222, 248, 14))
	if not FRAME.content_visible(self): return
	FRAME.title(self, font, "Slots", Rect2(20, 4, 112, 22)); _text("Payouts", Vector2(190, 33), 9, GOLD)
	for row in 6: _icons(5 - row, Vector2(180, 46 + row * 13), 3); _text("x%d" % MULTIPLIERS[5 - row], Vector2(222, 47 + row * 13), 9, Color.WHITE, 70, HORIZONTAL_ALIGNMENT_RIGHT)
	_icons(0, Vector2(180, 124), 2); _text("x1", Vector2(222, 125), 9, Color.WHITE, 70, HORIZONTAL_ALIGNMENT_RIGHT)
	_text("Zenny", Vector2(34, 149), 9, TAN); _text(_zenny_text(int(host.player.zenny)), Vector2(110, 149), 12, Color.WHITE, 180, HORIZONTAL_ALIGNMENT_RIGHT)
	_text("Bet", Vector2(34, 165), 9, TAN); _text("%d" % BETS[bet_index], Vector2(110, 165), 12, GOLD, 180, HORIZONTAL_ALIGNMENT_RIGHT)
	_text("Win", Vector2(34, 181), 9, TAN); _text(str(last_win) if last_win >= 0 else "-", Vector2(110, 181), 12, GOLD if last_win > 0 and fmod(flash, 0.5) < 0.3 else Color.WHITE, 180, HORIZONTAL_ALIGNMENT_RIGHT)
	_text(notice if notice != "" else ("No luck." if last_win == 0 else ("You win!" if last_win > 0 else "")), Vector2(34, 196), 9, Color.WHITE, 252, HORIZONTAL_ALIGNMENT_CENTER)
	_text("Confirm: Spin   Left / Right: Bet   Cancel: Leave" if phase == "idle" else "Confirm: Stop reel", Vector2(36, 226), 8, Color(1, 1, 1, 0.75), 248, HORIZONTAL_ALIGNMENT_CENTER)
