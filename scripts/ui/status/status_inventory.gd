extends ScrollContainer
signal changed
signal description_changed(text: String)
var host: Node
var rows: VBoxContainer
var definitions: Dictionary = {}
var handlers: Dictionary = {}
var category := "items"
var equipment_slot := -1
var selected_id := ""
func configure(owner: Node, catalog: Dictionary) -> void:
	host = owner
	definitions = catalog.duplicate(true)
	horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	vertical_scroll_mode = ScrollContainer.SCROLL_MODE_SHOW_ALWAYS
	follow_focus = true
	rows = VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 3)
	add_child(rows)
	_add_shop_items()
func _add_shop_items() -> void:
	# Names and descriptions of the purchasable items (native item codes), exported with the shop data.
	var source: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/shops/items.json")) if FileAccess.file_exists("res://assets/shops/items.json") else null
	if not source is Dictionary: return
	for code_text: String in source["names"]:
		var code := int(code_text); var item_name := _plain(str(source["names"][code_text]))
		var weapon := code >= 0x383 and code < 0x394
		if code < 0x383 or code >= 0x478 or item_name.is_empty() or item_name == "Nothing": continue
		var group := "special_weapons" if weapon else "key_items" if code >= 0x3d0 and code < 0x400 else "items" if code >= 0x400 else "body_parts" if code >= 0x3b8 else "buster_parts"; var key := str(code - 0x380) if weapon else code_text
		var definition := {"name": item_name, "description": _plain(str(source["descriptions"].get(code_text, "")))}
		if group == "body_parts": definition["slot"] = 0 if code < 0x3bc else 1 if code < 0x3c8 else 2
		if not definitions.has(group): definitions[group] = {}
		if not definitions[group].has(key): definitions[group][key] = definition
static func _plain(text: String) -> String:
	for entry: Array in [["\ue064", "\u03b1"], ["\ue065", "\u03a9"], ["\ue061", "-"], ["\ue05e", "+"], ["\ue049", "z"], ["\ue050", " "]]: text = text.replace(entry[0], entry[1])
	var plain := ""
	for character in text:
		var code := character.unicode_at(0)
		if code < 0xE0F0 or code > 0xE0FF: plain += character
	return plain
func register_definition(group: String, id: String, definition: Dictionary, action: Callable = Callable()) -> void:
	if not definitions.has(group): definitions[group] = {}
	definitions[group][id] = definition.duplicate(true)
	if action.is_valid(): handlers[group + ":" + id] = action
func item_name(group: String, id: String) -> String:
	return "Nothing" if id.is_empty() else str(definitions.get(group, {}).get(id, {}).get("name", id))
func refresh(group: String, slot: int = -1) -> void:
	category = group
	equipment_slot = slot
	selected_id = ""
	for child in rows.get_children(): rows.remove_child(child); child.queue_free()
	var owned: Dictionary = host.gameplay.player.inventory.get(group, {})
	if slot >= 0: _row("", "Nothing", true)
	for id in owned:
		if int(owned[id]) <= 0: continue
		var definition: Dictionary = definitions.get(group, {}).get(str(id), {})
		if group == "body_parts" and slot >= 0 and definition.has("slot") and int(definition["slot"]) != slot: continue
		if group == "body_parts" and slot >= 0 and definition.has("slots") and slot not in definition["slots"]: continue
		var label := item_name(group, str(id))
		if group in ["items", "key_items"]: label += "  %d" % int(owned[id])
		var usable := handlers.has(group + ":" + str(id)) or (group == "special_weapons" and str(id) == "0")
		_row(str(id), label, usable)
func _row(id: String, caption: String, usable: bool) -> void:
	var button := Button.new()
	button.text = caption
	button.disabled = not usable and category != "key_items"
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.custom_minimum_size.y = 16
	button.add_theme_font_size_override("font_size", 12)
	for state in ["normal", "hover", "pressed", "focus", "disabled"]: button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	button.add_theme_color_override("font_color", Color.WHITE)
	button.add_theme_color_override("font_focus_color", Color8(255, 222, 99))
	button.focus_entered.connect(func(): host.audio.play_ui("menu_move"))
	button.focus_entered.connect(func(): description_changed.emit(str(definitions.get(category, {}).get(id, {}).get("description", ""))))
	button.mouse_entered.connect(button.grab_focus)
	button.pressed.connect(_activate.bind(id))
	button.set_meta("usable", usable)
	button.set_meta("item_id", id)
	button.focus_entered.connect(func(): selected_id = id)
	rows.add_child(button)
func selected_definition() -> Dictionary: return definitions.get(category, {}).get(selected_id, {})
func focus_first() -> void:
	for child: Button in rows.get_children():
		if not child.disabled: child.grab_focus(); return
func _activate(id: String) -> void:
	var key := category + ":" + id
	if handlers.has(key): handlers[key].call(host.gameplay.player, id, equipment_slot)
	elif category == "special_weapons" and id == "0": host.gameplay.player.equipped_special = 0
	elif id.is_empty() and equipment_slot >= 0: host.gameplay.player.equipment[category][equipment_slot] = ""
	else: return
	host.audio.play_ui("menu_confirm")
	changed.emit()
