extends CanvasLayer
## The backdrop of the original frame (GAME 0x800BEFB8): flat strips 32 rows high of the area's colour table, anchored to the camera pitch. They are drawn behind the 3D view through the environment's canvas background; screen rows of the 320 x 240 frame map through the projection distance and the port camera's field of view as in RunnerEffects.

var bands: Array = []
var canvas: Control
var factor := 1.0
var center := Vector2.ZERO


func configure() -> void:
	layer = -10
	canvas = Control.new()
	canvas.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.draw.connect(_draw_bands)
	add_child(canvas)


func show_bands(packets: Array, projection: int, fov: float, size: Vector2) -> void:
	bands = packets
	factor = size.y / (2.0 * float(maxi(projection, 1)) * tan(deg_to_rad(fov) * 0.5))
	center = size * 0.5
	canvas.queue_redraw()


func _draw_bands() -> void:
	var width := canvas.size.x
	for index in bands.size():
		var packet: Dictionary = bands[index]
		var vertices: Array[Vector2] = packet["vertices"]
		var colors: Array[Color] = packet["colors"]
		var top := center.y + (vertices[0].y - 120.0) * factor
		var bottom := center.y + (vertices[2].y - 120.0) * factor
		if index == 0:
			top = -1.0
		if index == bands.size() - 1:
			bottom = canvas.size.y + 1.0
		var shown := PackedColorArray()
		for color in colors:
			shown.append(Color8(_display(color.r8), _display(color.g8), _display(color.b8)))
		canvas.draw_polygon(PackedVector2Array([Vector2(0.0, top), Vector2(width, top), Vector2(width, bottom), Vector2(0.0, bottom)]), PackedColorArray([shown[0], shown[1], shown[3], shown[2]]))


## The framebuffer keeps 5 bits per channel.
func _display(channel: int) -> int:
	return ((channel >> 3) * 255 + 15) / 31
