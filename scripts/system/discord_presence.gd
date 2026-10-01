extends Node
const APP_ID := "1557074698515251251"
const APP_NAME := "Mega Man Legends 2"
const INTERVAL := 15.0
const BRIDGE := """$ErrorActionPreference = 'Stop'
$p = $null
for ($i = 0; $i -lt 10; $i++) { try { $c = New-Object System.IO.Pipes.NamedPipeClientStream('.', ('discord-ipc-' + $i), [System.IO.Pipes.PipeDirection]::InOut); $c.Connect(250); $p = $c; break } catch {} }
if (-not $p) { [Console]::Out.WriteLine('NOPIPE'); exit 2 }
function Send($op, $text) { $b = [Text.Encoding]::UTF8.GetBytes($text); $h = New-Object byte[] 8; [BitConverter]::GetBytes([int]$op).CopyTo($h, 0); [BitConverter]::GetBytes([int]$b.Length).CopyTo($h, 4); $p.Write($h, 0, 8); $p.Write($b, 0, $b.Length); $p.Flush() }
function Fill($n) { $b = New-Object byte[] $n; $o = 0; while ($o -lt $n) { $r = $p.Read($b, $o, $n - $o); if ($r -le 0) { throw 'closed' }; $o += $r }; return ,$b }
function Recv() { $h = Fill 8; $b = Fill ([BitConverter]::ToInt32($h, 4)); return [Text.Encoding]::UTF8.GetString($b) }
try {
	Send 0 '{"v":1,"client_id":"%s"}'
	[Console]::Out.WriteLine((Recv))
	while ($null -ne ($l = [Console]::In.ReadLine())) { Send 1 ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($l))); [Console]::Out.WriteLine((Recv)) }
} catch { [Console]::Out.WriteLine('ERR ' + $_.Exception.Message); exit 3 }
exit 0"""
var enabled := true
var status := "idle"
var process: Dictionary = {}
var reader: Thread
var inbox: PackedStringArray = []
var lock := Mutex.new()
var linked := false
var retry := 0.0
var since_send := INTERVAL
var poll := 0.0
var last_sent: Dictionary = {}
var nonce := 0
var started := int(Time.get_unix_time_from_system() * 1000.0)  # Discord IPC timestamps are milliseconds
func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var settings := ConfigFile.new()
	settings.load("user://settings.cfg")
	enabled = bool(settings.get_value("interface", "discord_status", true))
	set_process(OS.get_name() == "Windows" and not OS.has_feature("web"))
func set_enabled(value: bool) -> void:
	enabled = value
	if not enabled: _stop(0.0)
func _process(delta: float) -> void:
	since_send += delta
	retry -= delta
	poll += delta
	lock.lock()
	var lines := inbox.duplicate()
	inbox.clear()
	lock.unlock()
	for line in lines: _reply(line)
	if not process.is_empty() and not OS.is_process_running(int(process["pid"])): _stop(INTERVAL)
	if not enabled: return
	if process.is_empty():
		if retry <= 0.0: _start()
		return
	if linked and poll >= 1.0:
		poll = 0.0
		var wanted := _build()
		if wanted != last_sent and since_send >= INTERVAL: _send(wanted)
func _start() -> void:
	var script := BRIDGE % APP_ID
	process = OS.execute_with_pipe("powershell", PackedStringArray(["-NoProfile", "-NonInteractive", "-EncodedCommand", Marshalls.raw_to_base64(script.to_utf16_buffer())]), false)
	if process.is_empty(): retry = INTERVAL; return
	linked = false
	last_sent = {}
	since_send = INTERVAL
	status = "connecting"
	reader = Thread.new()
	reader.start(_read.bind(process["stdio"], int(process["pid"])))
func _read(pipe: FileAccess, pid: int) -> void:
	while pipe.is_open():
		var line := pipe.get_line()
		if line.is_empty():
			if not OS.is_process_running(pid): break
			continue
		lock.lock()
		inbox.append(line)
		lock.unlock()
func _reply(line: String) -> void:
	var data: Variant = JSON.parse_string(line) if line.begins_with("{") else null
	if data is Dictionary:
		if data.get("evt") == "READY": linked = true; status = "ready"
		elif data.get("evt") == "ERROR": status = "error: " + str(data.get("data", {}).get("message", ""))
	else: status = line.strip_edges()
func _stop(delay: float) -> void:
	if not process.is_empty():
		OS.kill(int(process["pid"]))
		if reader != null: reader.wait_to_finish()
		reader = null
		process.clear()
	linked = false
	retry = delay
	status = "idle"
func _build() -> Dictionary:
	var scene := get_tree().current_scene
	var game: Variant = scene.get("gameplay") if scene != null else null
	if not is_instance_valid(game) or game.get("area_picker") == null: return {"details": "Mega Man Legends 2 (port)", "state": "Title screen"}
	var names: Dictionary = game.get_location_names()
	var main := str(names["main"])
	var area := str(names["area"])
	var details := main if area.is_empty() or area == main else main + " — " + area
	var state := "Exploring"
	var fire: Variant = game.get("fire_mission")
	var mine: Variant = game.get("mine_quest")
	if game.loading: state = "Loading"
	elif not game.scene_ui_state.is_empty(): state = "In a cutscene"
	elif is_instance_valid(fire) and fire.started and not fire.finished: state = "Fire mission"
	elif is_instance_valid(mine) and is_instance_valid(mine.boss): state = "Mine boss fight"
	elif get_tree().paused: state = "Paused"
	return {"details": details.left(100) if details.length() > 1 else "Exploring", "state": state}
func _send(wanted: Dictionary) -> void:
	nonce += 1
	var activity := {"name": APP_NAME, "type": 0, "details": wanted["details"], "state": wanted["state"], "timestamps": {"start": started}}
	var frame := JSON.stringify({"cmd": "SET_ACTIVITY", "args": {"pid": OS.get_process_id(), "activity": activity}, "nonce": "%d-%d" % [Time.get_ticks_msec(), nonce]})
	var pipe: FileAccess = process["stdio"]
	pipe.store_line(Marshalls.raw_to_base64(frame.to_utf8_buffer()))
	pipe.flush()
	last_sent = wanted
	since_send = 0.0
func _exit_tree() -> void:
	_stop(0.0)
