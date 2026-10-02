extends Control
var layout: Dictionary = {}
var surface: Control
var content: VBoxContainer
var font: Font
var pointer: TextureRect
var host: Node
const FRAME = preload("res://scripts/ui/common/native_menu_frame.gd")
func configure() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/menu/manifest.json"))
	layout = manifest["load_game_layout"]
	font = load("res://assets/menu/native_font.fnt") as Font
	surface = Control.new()
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(surface)
	content = VBoxContainer.new()
	content.position = Vector2(24, 40)
	content.size = Vector2(108, 0)
	content.add_theme_constant_override("separation", 2)
	content.minimum_size_changed.connect(queue_redraw)
	surface.add_child(content)
	set_meta("content", content)
	pointer = preload("res://scripts/ui/common/native_menu_cursor.gd").new()
	pointer.configure(Vector2.ZERO)
	pointer.hide()
	surface.add_child(pointer)
	resized.connect(_layout)
	_layout()
func _layout() -> void:
	if surface == null or size.y <= 0: return
	var factor: float = size.y / 240.0
	surface.scale = Vector2.ONE * factor
	surface.position = Vector2((size.x - 320.0 * factor) * 0.5, 0)
	surface.size = Vector2(320, 240)
	queue_redraw()
func animate_enter(context: String) -> void:
	surface.hide()
	if await FRAME.enter(self, layout, context): surface.show()
func animate_exit(context: String) -> void:
	surface.hide()
	await FRAME.exit(self, layout, context)
func focus_first() -> void:
	for child in content.get_children():
		if child is Button and not child.disabled: child.grab_focus(); return
func select_button(button: Button) -> void:
	pointer.select_at(content.position + button.position + Vector2(2, (button.size.y - 12) * 0.5))
	pointer.show()
func _process(_delta: float) -> void:
	if visible: queue_redraw()
func _draw() -> void:
	if layout.is_empty() or size.y <= 0: return
	var factor: float = size.y / 240.0
	var offset := Vector2((size.x - 320.0 * factor) * 0.5, 0)
	draw_set_transform(offset, 0, Vector2.ONE * factor)
	var live: bool = host != null and is_instance_valid(host.gameplay)
	FRAME.draw(self, layout, "header", Rect2(12, 4, 124, 22))
	FRAME.draw(self, layout, "selector", Rect2(12, 34, 124, content.get_combined_minimum_size().y + 12))
	if live:
		for window: Rect2 in [Rect2(146, 34, 164, 42), Rect2(146, 84, 164, 28), Rect2(146, 120, 164, 40), Rect2(146, 168, 164, 24)]: FRAME.draw(self, layout, "prompt", window)
	if not FRAME.content_visible(self): return
	FRAME.title(self, font, "Pause", Rect2(12, 4, 124, 22))
	if not live: return
	var gameplay: Node3D = host.gameplay; var names: Dictionary = gameplay.get_location_names(); var player: Node = gameplay.player; var catalog: Node = host.status_menu.inventory_view; var seconds := int(gameplay.play_time_seconds); var partner: String = host.special_partner()
	_text("Location", Vector2(152, 37), 8, Color8(150, 205, 220)); _text(str(names["main"]), Vector2(152, 47), 11, Color.WHITE, 152); _text(str(names["area"]) if str(names["area"]) != str(names["main"]) else "", Vector2(152, 60), 9, Color8(255, 222, 99), 152)
	_text("%07d Z" % int(player.zenny), Vector2(152, 91), 11, Color.WHITE, 80); _text("%d:%02d:%02d" % [seconds / 3600, (seconds / 60) % 60, seconds % 60], Vector2(232, 92), 9, Color.WHITE, 72, HORIZONTAL_ALIGNMENT_RIGHT)
	_text("Spec.Weapon", Vector2(152, 123), 8, Color8(150, 205, 220)); _text(catalog.item_name("special_weapons", str(player.equipped_special)), Vector2(152, 133), 11, Color.WHITE, 152); _text("X: Swap to " + catalog.item_name("special_weapons", partner) if not partner.is_empty() else "No other weapon", Vector2(152, 148), 8, Color8(255, 222, 99) if not partner.is_empty() else Color8(128, 128, 128), 152)
	_text("Life", Vector2(152, 174), 8, Color8(150, 205, 220)); preload("res://scripts/ui/menus/info_page.gd").life_gauge(self, Vector2(174, 175), int(player.health), int(player.max_health), 78.0); _text("%d/%d" % [int(player.health), int(player.max_health)], Vector2(256, 174), 8, Color.WHITE, 48, HORIZONTAL_ALIGNMENT_RIGHT)
func _text(value: String, point: Vector2, font_size: int = 9, color: Color = Color.WHITE, width: float = -1.0, alignment: int = HORIZONTAL_ALIGNMENT_LEFT) -> void:
	draw_string(font, point + Vector2(0, font.get_ascent(font_size)), value, alignment, width, font_size, color)
