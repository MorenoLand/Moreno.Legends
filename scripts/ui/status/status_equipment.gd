extends RefCounted
static func list_rect(category: String) -> Rect2: return Rect2(136, 116, 153, 43) if category in ["body_parts", "buster_parts"] else Rect2(136, 90, 153, 69)
static func tabs(category: String) -> Array:
	return [{"label": "Helmet", "rect": Rect2(128, 28, 46, 14)}, {"label": "Armor", "rect": Rect2(184, 28, 46, 14)}, {"label": "Shoes", "rect": Rect2(240, 28, 46, 14)}] if category == "body_parts" else [{"label": "Equip Items", "rect": Rect2(128, 28, 46, 14)}, {"label": "Sort", "rect": Rect2(200, 28, 46, 14)}]
static func draw(owner: Control, inventory: Node, player: Node, category: String, slot: int, mode: String = "equip", stats: Dictionary = {}) -> void:
	if category.is_empty():
		owner.call("_box", Rect2(128, 35, 176, 39)); owner.call("_text", "EQUIPPED SPECIAL WEAPON", Vector2(136, 32), 164, 8); owner.call("_text", inventory.item_name("special_weapons", str(player.equipped_special)), Vector2(150, 44), 144)
		owner.call("_box", Rect2(128, 80, 176, 53)); owner.call("_text", "EQUIPPED BODYPARTS", Vector2(136, 77), 164, 8)
		for index in 3: owner.call("_text", inventory.item_name("body_parts", str(player.equipment["body_parts"][index])), Vector2(150, 87 + 16 * index), 144)
		owner.call("_box", Rect2(16, 144, 288, 38)); owner.call("_text", "EQUIPPED BUSTER", Vector2(24, 141), 272, 8)
		for index in 2: owner.call("_text", inventory.item_name("buster_parts", str(player.equipment["buster_parts"][index])), Vector2(40 + 136 * index, 151), 118)
		return
	if category in ["body_parts", "buster_parts"]:
		var descriptors := tabs(category)
		for index in descriptors.size():
			var rectangle: Rect2 = descriptors[index]["rect"]; var active := index == slot if category == "body_parts" else index == (1 if mode == "sort" else 0); owner.draw_rect(rectangle, Color8(222, 73, 113) if active else Color8(72, 81, 107)); owner.call("_text", str(descriptors[index]["label"]), rectangle.position - Vector2(0, 1), rectangle.size.x, 10, HORIZONTAL_ALIGNMENT_CENTER)
		owner.call("_box", Rect2(128, 48, 176, 57)); owner.call("_text", "EQUIPPED BODYPARTS" if category == "body_parts" else "EQUIPPED BUSTER", Vector2(136, 45), 164, 8)
		var count := 3 if category == "body_parts" else 2
		for index in count: owner.call("_text", inventory.item_name(category, str(player.equipment[category][index])), Vector2(150, 55 + 16 * index), 144)
		owner.call("_box", Rect2(128, 110, 176, 53)); owner.call("_text", "PARTS LIST", Vector2(136, 107), 164, 8); owner.call("_box", Rect2(16, 120, 104 if category == "buster_parts" else 84, 43))
		if category == "buster_parts":
			for index in 4:
				var key: String = ["attack", "energy", "range", "rapid"][index]; owner.call("_text", key.to_upper(), Vector2(20, 126 + index * 8), 34, 8)
				if stats.has(key): owner.call("_text", str(stats[key]), Vector2(56, 126 + index * 8), 58, 8)
	else:
		owner.call("_box", Rect2(128, 35, 176, 39)); owner.call("_text", "EQUIPPED SPECIAL WEAPON", Vector2(136, 32), 164, 8); owner.call("_text", inventory.item_name("special_weapons", str(player.equipped_special)), Vector2(150, 44), 144); owner.call("_box", Rect2(128, 84, 176, 79)); owner.call("_text", "WEAPONS LIST", Vector2(136, 81), 164, 8)
