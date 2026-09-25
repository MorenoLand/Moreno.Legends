extends PanelContainer
signal closed
var host: Node
var cheats := {"invulnerable": false, "free_flight": false, "no_clip": false}
var location_picker: OptionButton
var room_picker: OptionButton
var location_message: Label
func configure(owner: Node) -> void:
	host = owner
	custom_minimum_size.x = 460
	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 12)
	add_child(layout)
	var tabs := TabContainer.new()
	layout.add_child(tabs)
	var settings := VBoxContainer.new()
	settings.name = "Settings"
	settings.add_theme_constant_override("separation", 12)
	tabs.add_child(settings)
	_slider(settings, "Mouse sensitivity", 0.0005, 0.01, 0.0001, float(host.settings.get_value("controls", "mouse_sensitivity", 0.003)), host._sensitivity_changed)
	_slider(settings, "Camera FOV", 45, 100, 1, float(host.settings.get_value("camera", "fov", 65)), _fov_changed)
	_toggle(settings, "Fullscreen", DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN, func(value): DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if value else DisplayServer.WINDOW_MODE_WINDOWED))
	var cheat_page := VBoxContainer.new()
	cheat_page.name = "Cheats"
	cheat_page.add_theme_constant_override("separation", 12)
	tabs.add_child(cheat_page)
	for key in cheats:
		var label: String = {"invulnerable": "Invulnerable", "free_flight": "Flight", "no_clip": "No clip"}[key]
		_toggle(cheat_page, label, cheats[key], func(value): _cheat_changed(key, value))
	var controls := Label.new()
	controls.text = "Flight: Space up / C down"
	cheat_page.add_child(controls)
	_button(cheat_page, "Refill health", func():
		if is_instance_valid(host.gameplay): host.gameplay.player.refill_health())
	_button(cheat_page, "Respawn", func():
		if is_instance_valid(host.gameplay): host.gameplay.player.reset_at(host.gameplay.spawn_position))
	var places := VBoxContainer.new()
	places.name = "Locations"
	places.add_theme_constant_override("separation", 12)
	tabs.add_child(places)
	location_picker = OptionButton.new()
	places.add_child(location_picker)
	for location: Dictionary in host.locations: location_picker.add_item(str(location["name"]))
	room_picker = OptionButton.new()
	places.add_child(room_picker)
	location_picker.item_selected.connect(_location_selected)
	_location_selected(0)
	_button(places, "Load room", _load_room)
	location_message = Label.new()
	location_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	places.add_child(location_message)
	_button(layout, "Close", func(): closed.emit())
func _location_selected(index: int) -> void:
	room_picker.clear()
	if index < 0 or index >= host.locations.size(): return
	for area: Dictionary in host.locations[index]["areas"]: room_picker.add_item(str(area["name"]), int(area["index"]))
func _load_room() -> void:
	set_location_message("")
	if location_picker.selected < 0 or room_picker.selected < 0: return
	var stage := str(host.locations[location_picker.selected]["stage"])
	host._load_location(stage, room_picker.get_selected_id())
func set_location_message(text: String) -> void:
	if location_message != null: location_message.text = text
func _slider(parent: Control, caption: String, minimum: float, maximum: float, step: float, value: float, action: Callable) -> void:
	var label := Label.new()
	label.text = caption
	parent.add_child(label)
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step
	slider.value = value
	slider.value_changed.connect(action)
	parent.add_child(slider)
func _toggle(parent: Control, caption: String, value: bool, action: Callable) -> void:
	var button := CheckButton.new()
	button.text = caption
	button.button_pressed = value
	button.toggled.connect(action)
	parent.add_child(button)
func _button(parent: Control, caption: String, action: Callable) -> void:
	var button := Button.new()
	button.text = caption
	button.pressed.connect(action)
	parent.add_child(button)
func _cheat_changed(key: String, value: bool) -> void:
	cheats[key] = value
	apply_player()
func _fov_changed(value: float) -> void:
	host.settings.set_value("camera", "fov", value)
	host.settings.save("user://settings.cfg")
	if is_instance_valid(host.gameplay): host.gameplay.player.camera.fov = value
func apply_player() -> void:
	if not is_instance_valid(host.gameplay): return
	for key in cheats: host.gameplay.player.set(key, cheats[key])
	host.gameplay.player.camera.fov = float(host.settings.get_value("camera", "fov", 65))
