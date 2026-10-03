extends Control
# Port-only extra: playable slot machine for the Ruminoa City Restaurant prop (ST1A message 85). Reel symbols are the ones painted on that prop's texture (assets/menu/slot_symbols.png).
signal closed
const FRAME := preload("res://scripts/ui/common/native_menu_frame.gd")
const SHOP := preload("res://scripts/ui/menus/shop_menu.gd")
const STAGE := "ST1A"
const MESSAGE := 85
const BETS := [10, 50, 100]
const STRIP := [0, 1, 2, 0, 3, 1, 0, 4, 2, 0, 1, 5, 0, 2, 1, 0, 3, 1, 0, 2, 4, 0, 1, 3]
const MULTIPLIERS := [5, 10, 25, 50, 150, 500]
const PAIR_SYMBOL := 0
const SPEED := 18.0
const SLOW := 0.4
const STOPS := [0.9, 1.5, 2.1]
const TENSION := 1.1
const PITCH := 30.0
const SYMBOL_SIZE := Vector2(24, 30)
const REEL_X := [32.0, 80.0, 128.0]
const REEL_Y := 48.0
const REEL_SIZE := Vector2(40, PITCH * 3.0)
const REELS_WINDOW := Rect2(20, 36, 160, 114)
const PAYOUTS_WINDOW := Rect2(192, 36, 108, 114)
const STATUS_WINDOW := Rect2(20, 162, 280, 38)
const HINT_WINDOW := Rect2(36, 212, 248, 16)
const HEADER_WINDOW := Rect2(20, 6, 112, 18)
const BET_LEFT := Rect2(104, 174, 12, 18)
const BET_RIGHT := Rect2(188, 174, 12, 18)
const HINTS := {"idle": "Confirm: Spin   Left / Right: Bet   Cancel: Leave", "spin": "Confirm: Stop reel", "result": "Confirm: Continue"}
const BOUNCE_TIME := 0.35
const GOLD := Color8(255, 222, 99)
const TAN := Color(0.72, 0.68, 0.52)
const STRIP_COLOR := Color8(236, 226, 200)
const POPUP_IN := 0.3
const POPUP_OUT := 0.3
const POPUP_HOLD := 0.5
class Reel extends Control:
	var atlas: Texture2D
	var position_index := 0.0
	var lit := false
	var flash := false
	var tense := false
	var blur := 0.0
	var bounce := 0.0
	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), STRIP_COLOR)
		var base := floori(position_index + 0.5); var shift := (position_index - float(base) + bounce) * PITCH; var middle := size.y * 0.5 - PITCH * 0.5; var trails := 3 if blur > 0.3 else 1
		for row in range(-2, 3):
			for trail in trails:
				var y := middle + float(row) * PITCH - shift - float(trail) * blur * 9.0 + (PITCH - SYMBOL_SIZE.y) * 0.5; var alpha: float = 1.0 if trails == 1 else [0.75, 0.3, 0.15][trail]
				draw_texture_rect_region(atlas, Rect2(Vector2((size.x - SYMBOL_SIZE.x) * 0.5, y), SYMBOL_SIZE), Rect2(float(STRIP[posmod(base + row, STRIP.size())]) * 8.0, 0, 8, 10), Color(1, 1, 1, alpha))
		for band in 4: draw_rect(Rect2(0, float(band) * 7.0, size.x, 7), Color(0, 0, 0, 0.22 - float(band) * 0.055)); draw_rect(Rect2(0, size.y - float(band + 1) * 7.0, size.x, 7), Color(0, 0, 0, 0.22 - float(band) * 0.055))
		var color := Color(1, 1, 1, 0.35)
		if lit: color = Color.WHITE if flash else GOLD
		elif tense: color = Color8(255, 90, 70) if flash else GOLD
		draw_rect(Rect2(0, middle, size.x, PITCH), color, false, 2.0 if lit or tense else 1.0)
class Layer extends Control:
	var painter: Callable
	func _draw() -> void: painter.call(self)
var host: Node
var layout: Dictionary = {}
var font: Font
var symbols: Texture2D
var surface: Control
var popup_layer: Layer
var fx_layer: Layer
var reels: Array[Reel] = []
var states: Array[Dictionary] = []
var targets: Array[int] = []
var particles: Array[Dictionary] = []
var result: Dictionary = {}
var bet_index := 0
var phase := "idle"
var elapsed := 0.0
var flash := 0.0
var last_win := -1
var win_row := -1
var notice := ""
var notice_time := 0.0
var shown_zenny := 0.0
var screen_flash := 0.0
var tension := false
var ready_for_input := false
var rng := RandomNumberGenerator.new()
static func enabled() -> bool:
	var settings := ConfigFile.new(); settings.load("user://settings.cfg")
	return bool(settings.get_value("extras", "slot_machine", true))
static func applies(stage: String, index: int) -> bool:
	return stage == STAGE and index == MESSAGE and enabled()
static func payout(symbol_list: Array, bet: int) -> int:
	if symbol_list[0] == symbol_list[1] and symbol_list[1] == symbol_list[2]: return bet * int(MULTIPLIERS[symbol_list[0]])
	return bet if symbol_list.count(PAIR_SYMBOL) == 2 else 0
static func payout_row(symbol_list: Array) -> int:
	if symbol_list[0] == symbol_list[1] and symbol_list[1] == symbol_list[2]: return MULTIPLIERS.size() - 1 - int(symbol_list[0])
	return MULTIPLIERS.size() if symbol_list.count(PAIR_SYMBOL) == 2 else -1
static func expected_return() -> float:
	var total := 0.0; var count := float(STRIP.size())
	for symbol in MULTIPLIERS.size():
		var chance := float(STRIP.count(symbol)) / count; total += float(MULTIPLIERS[symbol]) * pow(chance, 3.0)
		if symbol == PAIR_SYMBOL: total += 3.0 * chance * chance * (1.0 - chance)
	return total
static func play(gameplay: Node, parent: Node) -> void:
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
	host = gameplay; layout = host.dialogue_box.layout; font = host.dialogue_box.font; symbols = load("res://assets/menu/slot_symbols.png") as Texture2D; rng.randomize(); setup()
	if await FRAME.enter(self, layout, "gameplay"): surface.show()
	ready_for_input = true; await closed
	ready_for_input = false; surface.hide(); await FRAME.exit(self, layout, "gameplay")
func setup() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE; texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST; z_index = 20
	surface = Control.new(); surface.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(surface); shown_zenny = float(host.player.zenny)
	for index in 3:
		var reel := Reel.new(); reel.atlas = symbols; reel.mouse_filter = Control.MOUSE_FILTER_IGNORE; reel.clip_contents = true; reel.position = Vector2(REEL_X[index], REEL_Y); reel.size = REEL_SIZE; reel.position_index = float(rng.randi_range(0, STRIP.size() - 1)); surface.add_child(reel); reels.append(reel); states.append({"mode": "stopped"}); targets.append(0)
	popup_layer = _layer(_draw_popup); fx_layer = _layer(_draw_fx); resized.connect(_layout); _layout(); _fit_bet(); surface.hide()
func _layer(painter: Callable) -> Layer:
	var layer := Layer.new(); layer.painter = painter; layer.mouse_filter = Control.MOUSE_FILTER_IGNORE; layer.size = Vector2(320, 240); surface.add_child(layer); return layer
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0; surface.scale = Vector2.ONE * factor; surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0); surface.size = Vector2(320, 240); queue_redraw()
func _fit_bet() -> void:
	while bet_index > 0 and int(host.player.zenny) < BETS[bet_index]: bet_index -= 1
func _set_zenny(value: int) -> void:
	host.player.zenny = maxi(value, 0); host.native_context["native_wallet"] = host.player.zenny
func _say(text: String, time: float = 1.6) -> void:
	notice = text; notice_time = time
func _spin() -> void:
	var bet: int = BETS[bet_index]
	if int(host.player.zenny) < bet: _say("Not enough zenny."); host.audio.play_ui("menu_cancel"); return
	_set_zenny(int(host.player.zenny) - bet); shown_zenny = float(host.player.zenny); phase = "spin"; elapsed = 0.0; last_win = -1; win_row = -1; notice = ""; result = {}; tension = false; host.audio.play_ui("menu_confirm")
	for index in 3: targets[index] = rng.randi_range(0, STRIP.size() - 1); states[index] = {"mode": "spin", "stop_at": STOPS[index]}; reels[index].lit = false; reels[index].tense = false; reels[index].bounce = 0.0
	tension = STRIP[targets[0]] == STRIP[targets[1]]
	if tension: states[2]["stop_at"] = float(STOPS[2]) + TENSION
func _stop_next() -> void:
	for index in 3:
		if states[index]["mode"] == "spin": states[index]["stop_at"] = 0.0; return
func _final(index: int) -> float:
	var count := float(STRIP.size())
	return float(targets[index]) + count * floorf((reels[index].position_index - 3.0 - float(targets[index])) / count)
func _speed(index: int) -> float:
	return SPEED * (SLOW if index == 2 and tension and states[0]["mode"] == "stopped" and states[1]["mode"] == "stopped" else 1.0)
func advance(delta: float) -> void:
	flash += delta; notice_time = maxf(notice_time - delta, 0.0)
	if notice_time <= 0.0 and phase != "spin": notice = ""
	_advance_particles(delta)
	if phase == "spin": _advance_reels(delta)
	elif phase == "result": _advance_result(delta)
func _advance_reels(delta: float) -> void:
	elapsed += delta; var moving := false
	for index in 3:
		var state: Dictionary = states[index]; var reel := reels[index]; var speed := _speed(index) if state["mode"] == "spin" else SPEED
		reel.blur = clampf(speed / SPEED, 0.0, 1.0) if state["mode"] in ["spin", "seek"] else 0.0
		match state["mode"]:
			"spin":
				reel.position_index -= speed * delta; moving = true
				if elapsed >= float(state["stop_at"]): state["mode"] = "seek"; state["to"] = _final(index)
			"seek":
				reel.position_index -= speed * delta; moving = true; var final: float = state["to"]
				if reel.position_index - final <= 3.0: state["mode"] = "ease"; state["from"] = reel.position_index; state["to"] = final; state["time"] = 0.0; state["length"] = 2.0 * (reel.position_index - final) / speed
			"ease":
				moving = true; state["time"] = float(state["time"]) + delta; var progress := minf(float(state["time"]) / maxf(float(state["length"]), 0.001), 1.0)
				reel.position_index = float(state["to"]) + (float(state["from"]) - float(state["to"])) * (1.0 - progress) * (1.0 - progress)
				if progress >= 1.0: state["mode"] = "bounce"; state["time"] = 0.0; reel.position_index = float(state["to"]); host.audio.play_ui("menu_move")
			"bounce":
				moving = true; state["time"] = float(state["time"]) + delta; var t := float(state["time"]); reel.bounce = -0.2 * sin(t * 32.0) * exp(-t * 9.0)
				if t >= BOUNCE_TIME: state["mode"] = "stopped"; reel.bounce = 0.0
		reel.tense = tension and index == 2 and state["mode"] == "spin" and states[0]["mode"] != "spin" and states[1]["mode"] != "spin"; reel.flash = fmod(flash, 0.2) < 0.1
	if not moving: _resolve()
func _resolve() -> void:
	var symbol_list: Array = []
	for index in 3: symbol_list.append(STRIP[targets[index]])
	var bet: int = BETS[bet_index]; var win := payout(symbol_list, bet); phase = "result"; flash = 0.0; last_win = win; win_row = payout_row(symbol_list); var before := int(host.player.zenny); _set_zenny(before + win)
	var multiplier := win / bet; var count_time := 0.0 if win == 0 else (0.6 if multiplier <= 3 else (1.0 if multiplier <= 25 else 1.6))
	result = {"win": win, "bet": bet, "before": before, "time": 0.0, "count_time": count_time, "jackpot": multiplier >= 100, "total": POPUP_IN + count_time + POPUP_HOLD + POPUP_OUT if win > 0 else 0.35}
	for reel in reels: reel.lit = win > 0
	if win > 0: _burst(win, bet); screen_flash = 0.5 if multiplier >= 25 else 0.0
	if multiplier >= 25: host.audio.play_sound(0xEF)
	elif win > 0: host.audio.play_ui("menu_confirm")
	else: host.audio.play_ui("menu_cancel")
	_fit_bet()
	if int(host.player.zenny) < BETS[0]: _say("Out of zenny.", 4.0)
func _advance_result(delta: float) -> void:
	result["time"] = float(result["time"]) + delta; var time := float(result["time"]); screen_flash = maxf(screen_flash - delta, 0.0)
	var win := int(result["win"]); var counting := clampf((time - POPUP_IN) / maxf(float(result["count_time"]), 0.001), 0.0, 1.0) if win > 0 else 1.0
	shown_zenny = float(int(result["before"])) + float(win) * counting
	if time >= float(result["total"]): _finish_result()
func _finish_result() -> void:
	phase = "idle"; shown_zenny = float(host.player.zenny)
func _burst(win: int, bet: int) -> void:
	var multiplier := win / bet; var amount := 10 if multiplier <= 3 else (36 if multiplier < 100 else 80)
	for index in amount:
		var coin := multiplier > 3 and index % 3 == 0
		particles.append({"kind": "coin" if coin else "spark", "position": Vector2(rng.randf_range(24.0, 296.0), rng.randf_range(-24.0, 30.0)) if coin else Vector2(rng.randf_range(40.0, 280.0), rng.randf_range(40.0, 130.0)), "velocity": Vector2(rng.randf_range(-30.0, 30.0), rng.randf_range(20.0, 80.0)) if coin else Vector2(rng.randf_range(-20.0, 20.0), rng.randf_range(-30.0, 10.0)), "life": rng.randf_range(0.9, 1.9) if coin else rng.randf_range(0.5, 1.1), "age": 0.0, "phase": rng.randf() * TAU, "size": rng.randf_range(2.0, 5.0)})
func _advance_particles(delta: float) -> void:
	for particle in particles:
		particle["age"] = float(particle["age"]) + delta; particle["position"] += particle["velocity"] * delta
		if particle["kind"] == "coin": particle["velocity"] += Vector2(0, 260.0) * delta
	particles = particles.filter(func(particle): return float(particle["age"]) < float(particle["life"]))
func _process(delta: float) -> void:
	if ready_for_input: advance(delta)
	queue_redraw(); popup_layer.queue_redraw(); fx_layer.queue_redraw()
	for reel in reels: reel.queue_redraw()
func _leave() -> void:
	host.audio.play_ui("menu_cancel"); closed.emit()
func _confirm() -> void:
	if phase == "spin": _stop_next()
	elif phase == "result": _finish_result()
	else: _spin()
func _bet_step(direction: int) -> void:
	if phase != "idle": return
	var next := clampi(bet_index + direction, 0, BETS.size() - 1)
	if int(host.player.zenny) < BETS[next]: _say("Not enough zenny."); host.audio.play_ui("menu_cancel")
	elif next != bet_index: bet_index = next; notice = ""; host.audio.play_ui("menu_move")
func handle(event: InputEvent) -> bool:
	if not ready_for_input or event.is_echo() or not event.is_pressed(): return false
	if event is InputEventMouseButton:
		var factor: float = size.y / 240.0; var point: Vector2 = (event.position - Vector2((size.x - 320.0 * factor) * 0.5, 0)) / factor
		if event.button_index == MOUSE_BUTTON_RIGHT:
			if phase != "spin": _leave()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if BET_LEFT.has_point(point): _bet_step(-1)
			elif BET_RIGHT.has_point(point): _bet_step(1)
			elif REELS_WINDOW.has_point(point) or STATUS_WINDOW.has_point(point): _confirm()
		else: return false
	elif event.is_action_pressed("ui_cancel"):
		if phase != "spin": _leave()
	elif event.is_action_pressed("ui_accept") or event.is_action_pressed("interact"): _confirm()
	elif event.is_action_pressed("ui_left") or event.is_action_pressed("ui_right"): _bet_step(1 if event.is_action_pressed("ui_right") else -1)
	else: return false
	return true
func _input(event: InputEvent) -> void:
	if handle(event): get_viewport().set_input_as_handled()
func _text(canvas: CanvasItem, value: String, point: Vector2, font_size: int = 9, color: Color = Color.WHITE, width: float = -1.0, alignment: int = HORIZONTAL_ALIGNMENT_LEFT) -> void:
	canvas.draw_string(font, point + Vector2(0, font.get_ascent(font_size)), value, alignment, width, font_size, color)
func _symbols(canvas: CanvasItem, symbol: int, origin: Vector2, count: int) -> void:
	for column in count:
		var cell := Vector2(origin.x + float(column) * 13.0, origin.y); canvas.draw_rect(Rect2(cell, Vector2(12, 12)), STRIP_COLOR); canvas.draw_texture_rect_region(symbols, Rect2(cell + Vector2(1.2, 0), Vector2(9.6, 12)), Rect2(symbol * 8, 0, 8, 10))
func _arrow(canvas: CanvasItem, rect: Rect2, direction: int, color: Color) -> void:
	var middle := rect.get_center(); var half := Vector2(3, 5)
	canvas.draw_colored_polygon(PackedVector2Array([middle + Vector2(-half.x * direction, 0), middle + Vector2(half.x * direction, -half.y), middle + Vector2(half.x * direction, half.y)]), color)
func _star(canvas: CanvasItem, center: Vector2, radius: float, color: Color) -> void:
	var inner := radius * 0.3; canvas.draw_colored_polygon(PackedVector2Array([center + Vector2(0, -radius), center + Vector2(inner, -inner), center + Vector2(radius, 0), center + Vector2(inner, inner), center + Vector2(0, radius), center + Vector2(-inner, inner), center + Vector2(-radius, 0), center + Vector2(-inner, -inner)]), color)
func _draw() -> void:
	if layout.is_empty() or size.y <= 0 or font == null: return
	var factor: float = size.y / 240.0; draw_set_transform(Vector2((size.x - 320.0 * factor) * 0.5, 0), 0, Vector2.ONE * factor)
	FRAME.draw(self, layout, "header", HEADER_WINDOW); FRAME.draw(self, layout, "prompt", REELS_WINDOW); FRAME.draw(self, layout, "prompt", PAYOUTS_WINDOW); FRAME.draw(self, layout, "prompt", STATUS_WINDOW); FRAME.draw(self, layout, "prompt", HINT_WINDOW)
	if not FRAME.content_visible(self): return
	FRAME.title(self, font, "Slots", HEADER_WINDOW); FRAME.title(self, font, "Payouts", Rect2(192, 38, 108, 16), GOLD)
	var line_y := REEL_Y + REEL_SIZE.y * 0.5; var lit := phase == "result" and last_win > 0; var marker := (Color.WHITE if fmod(flash, 0.25) < 0.125 else GOLD) if lit else Color(1, 1, 1, 0.45)
	_arrow(self, Rect2(22, line_y - 6, 8, 12), 1, marker); _arrow(self, Rect2(170, line_y - 6, 8, 12), -1, marker)
	for row in MULTIPLIERS.size() + 1:
		var y := 57.0 + float(row) * 12.5; var hit := row == win_row and phase != "spin"
		if hit: draw_rect(Rect2(196, y - 1, 96, 14), Color(GOLD, 0.45 if fmod(flash, 0.5) < 0.3 else 0.15))
		_symbols(self, MULTIPLIERS.size() - 1 - row if row < MULTIPLIERS.size() else PAIR_SYMBOL, Vector2(200, y), 3 if row < MULTIPLIERS.size() else 2)
		_text(self, "x%d" % (MULTIPLIERS[MULTIPLIERS.size() - 1 - row] if row < MULTIPLIERS.size() else 1), Vector2(244, y + 1), 9, GOLD if hit else Color.WHITE, 44, HORIZONTAL_ALIGNMENT_RIGHT)
	_text(self, "Zenny", Vector2(32, 167), 9, TAN); _text(self, "%07d" % int(roundf(shown_zenny)), Vector2(32, 178), 12, Color.WHITE, 72, HORIZONTAL_ALIGNMENT_RIGHT)
	_text(self, "Bet", Vector2(120, 167), 9, TAN); _arrow(self, BET_LEFT, 1, Color(1, 1, 1, 0.9 if bet_index > 0 and phase == "idle" else 0.3)); _arrow(self, BET_RIGHT, -1, Color(1, 1, 1, 0.9 if bet_index < BETS.size() - 1 and phase == "idle" else 0.3))
	for chip in bet_index + 1: SHOP.draw_item_icon(self, 0, Rect2(120 + chip * 9, 177, 12, 12))
	_text(self, "%d" % BETS[bet_index], Vector2(152, 178), 12, GOLD, 32, HORIZONTAL_ALIGNMENT_RIGHT)
	_text(self, "Win", Vector2(214, 167), 9, TAN); _text(self, str(last_win) if last_win >= 0 and phase != "spin" else "-", Vector2(214, 178), 12, (GOLD if fmod(flash, 0.5) < 0.3 else Color.WHITE) if last_win > 0 else Color(1, 1, 1, 0.5), 74, HORIZONTAL_ALIGNMENT_RIGHT)
	_text(self, notice if notice != "" else HINTS[phase], Vector2(36, 216), 8, Color.WHITE if notice != "" else Color(1, 1, 1, 0.75), 248, HORIZONTAL_ALIGNMENT_CENTER)
func popup_state() -> Dictionary:
	if phase != "result" or int(result.get("win", 0)) <= 0: return {"alpha": 0.0, "scale": 0.0, "count": 0}
	var time := float(result["time"]); var total := float(result["total"]); var scale_value := 1.0; var alpha := 1.0
	if time < POPUP_IN: var u := time / POPUP_IN; scale_value = 1.0 + 2.70158 * pow(u - 1.0, 3.0) + 1.70158 * pow(u - 1.0, 2.0); alpha = u
	elif time > total - POPUP_OUT: var u := (total - time) / POPUP_OUT; scale_value = 0.6 + 0.4 * u; alpha = u
	var counting := clampf((time - POPUP_IN) / maxf(float(result["count_time"]), 0.001), 0.0, 1.0)
	return {"alpha": clampf(alpha, 0.0, 1.0), "scale": maxf(scale_value, 0.0), "count": int(roundf(float(result["win"]) * counting))}
func _draw_popup(canvas: Control) -> void:
	var state := popup_state()
	if float(state["alpha"]) <= 0.0 or font == null: return
	var jackpot := bool(result["jackpot"]); var scale_value: float = state["scale"] * (1.0 + 0.04 * sin(flash * 14.0) if jackpot else 1.0); var center := Vector2(160, 93); var base := Vector2(136, 50)
	canvas.modulate = Color(1, 1, 1, state["alpha"]); FRAME.draw(canvas, layout, "prompt", Rect2(center - base * scale_value * 0.5, base * scale_value))
	var title := "JACKPOT!" if jackpot else "WIN!"; var tint := (Color.WHITE if fmod(flash, 0.2) < 0.1 else GOLD) if jackpot else GOLD; var width := font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x
	canvas.draw_set_transform(center + Vector2(0, -9) * scale_value, 0, Vector2.ONE * scale_value * 1.6); canvas.draw_string(font, Vector2(-width * 0.5, 4), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, tint)
	var amount := "%d" % int(state["count"]); width = font.get_string_size(amount, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 16.0; canvas.draw_set_transform(center + Vector2(0, 12) * scale_value, 0, Vector2.ONE * scale_value); SHOP.draw_item_icon(canvas, 0, Rect2(-width * 0.5, -3, 12, 12)); canvas.draw_string(font, Vector2(-width * 0.5 + 16.0, 4), amount, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE); canvas.draw_set_transform(Vector2.ZERO, 0, Vector2.ONE)
func _draw_fx(canvas: Control) -> void:
	if screen_flash > 0.0: canvas.draw_rect(Rect2(0, 0, 320, 240), Color(1, 1, 1, screen_flash * 0.5))
	# Particles draw above the popup window but skip its box while it is showing, so the shower stays visible and the WIN text stays readable.
	var state := popup_state(); var box := Rect2()
	if float(state["alpha"]) > 0.0: var half := Vector2(136, 50) * float(state["scale"]) * 0.5; box = Rect2(Vector2(160, 93) - half, half * 2.0)
	for particle in particles:
		var life := float(particle["age"]) / float(particle["life"]); var position_value: Vector2 = particle["position"]
		if box.has_area() and box.grow(4.0).has_point(position_value): continue
		if particle["kind"] == "coin": var squash := absf(cos(float(particle["phase"]) + float(particle["age"]) * 9.0)); SHOP.draw_item_icon(canvas, 0, Rect2(position_value - Vector2(6.0 * squash, 6), Vector2(12.0 * squash, 12)))
		else: _star(canvas, position_value, float(particle["size"]) * (0.4 + 0.6 * absf(sin(float(particle["phase"]) + float(particle["age"]) * 12.0))) * (1.0 - life * 0.5), Color(1, 1, 1, 1.0 - life) if int(float(particle["phase"]) * 3.0) % 2 == 0 else Color(GOLD, 1.0 - life))
