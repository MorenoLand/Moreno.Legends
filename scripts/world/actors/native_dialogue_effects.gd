extends RefCounted
class_name NativeDialogueEffects
static func decode(opcode: int, arguments: Array) -> Dictionary:
	match opcode:
		0x09:
			if arguments.size() != 1: return {}
			var speed := int(arguments[0]); return {"kind": "text_speed", "handler": "SLES text window FB09", "native_updates_per_glyph": speed, "instant": speed == 0, "window_flags_mask": 0x40000, "context_byte7": 0 if speed == 0 else speed - 1, "context_halfword4": 0 if speed == 0 else speed - 1}
		0x0F:
			if arguments.size() != 1: return {}
			return {"kind": "choice_row_marker", "row_index": int(arguments[0]) & 0xF, "handler": "SLES secondary glyph stream"}
		0x11:
			if arguments.is_empty() or arguments.size() != int(arguments[0]) + 1: return {}
			return {"kind": "choice_redirect", "target_count": int(arguments[0]), "candidate_indices": arguments.slice(1), "selection_source": "message_window.flags[8:11]", "fallthrough_index": 255}
		0x21:
			if arguments.size() != 1: return {}
			return {"kind": "native_number", "value_source": "wallet" if int(arguments[0]) & 0x80 else "message_context+0x68", "formatting_flags": int(arguments[0]) & 0x7F, "digit_count": 7, "fixed_width": (int(arguments[0]) & 0x7F) == 0, "padding_character": "\uE050", "negative_character": "-", "formatter": "SLES 0x80048FF8"}
		0x2C:
			if arguments.size() != 1: return {}
			return {"kind": "render_visibility_bit", "address": "0x8008C0A0", "mask": 2, "set": int(arguments[0]) != 0, "handler": "SLES 0x8004DF78"}
		0x15:
			if arguments.size() != 11: return {}
			return {"kind": "camera_setup", "handler": "SLES 0x8004CF14", "native_base": "0x8007D010", "mode": int(arguments[0]), "signed12": [_signed12(int(arguments[1]), int(arguments[2])), _signed12(int(arguments[3]), int(arguments[4])), _signed12(int(arguments[5]), int(arguments[6]))], "fields": {"0x03": int(arguments[0]), "0xBC": _be16(int(arguments[9]), int(arguments[10])), "0xBE": _be16(int(arguments[7]), int(arguments[8]))}}
		0x33:
			if arguments.size() != 1: return {}
			var descriptor := int(arguments[0]) & 0xff; var selector := descriptor & 0xc0; var voice_id := descriptor & 0x3f
			return {"kind": "voice_descriptor", "handler": "SLES 0x8004BEA4", "descriptor": descriptor, "voice_id": 255 if voice_id == 63 else voice_id, "slot": 0 if selector == 0x40 else 1 if selector == 0x80 else -1, "context_offsets": [0x25 if selector == 0x40 else 0x26] if selector in [0x40, 0x80] else [], "global_voice_address": "0x80078CD2" if selector == 0x40 else "0x80078CD3" if selector == 0x80 else "", "global_voice_gate": "0x80078CC8"}
		0x2A:
			if arguments.size() != 5: return {}
			return {"kind": "save_byte16_redirect", "selector_address": "0x8009C7FE", "candidate_indices": arguments.duplicate(), "fallthrough_index": 255}
		0x30:
			if arguments.size() != 1: return {}
			return {"kind": "window_byte_write", "context_offset": 0x23, "value": int(arguments[0])}
		0x10, 0x39:
			if arguments.is_empty() or arguments.size() != 1 + int(arguments[0]) * 2: return {}
			var coordinates: Array = []; for index in range(int(arguments[0])): coordinates.append([int(arguments[1 + index * 2]), int(arguments[2 + index * 2])])
			return {"kind": "native_choice_wait", "choice_count": int(arguments[0]), "native_coordinates": coordinates, "confirm": "Cross", "cancel_index": int(arguments[0]), "cancel": "Triangle", "source": "SLES 0x8004CA14 / 0x8004CCB4"}
		0x3E:
			if arguments.size() != 2: return {}
			return {"kind": "native_signed_delta", "delta": _signed_be16(int(arguments[0]), int(arguments[1])), "source_word": "save+0x40", "source_state": "save+0x44", "saturation": [-32767, 32767], "state_thresholds": {"0_to_1_below": 0x3000, "2_to_1_at_or_above": -0x2FFF, "to_0_above": 0x4000, "to_2_below": -0x4000}}
		0x3F:
			if arguments.size() != 3: return {}
			return {"kind": "native_state_redirect", "selector_address": "0x8009C82C", "candidate_indices": arguments.duplicate(), "fallthrough_index": 255}
		0xFD:
			if arguments.size() != 4: return {}
			return {"kind": "timed_page_reset", "wait_ticks": (int(arguments[0]) << 8) | int(arguments[1]), "effective_updates": ((int(arguments[0]) << 8) | int(arguments[1])) + 1, "header": [int(arguments[2]), int(arguments[3])], "source": "SLES 0x8004C014 / 0x8004BE30"}
	return {}
static func _signed12(high: int, low: int) -> int:
	var value := ((high & 0xff) << 8) | (low & 0xff); value &= 0xfff; return value - 0x1000 if value & 0x800 else value
static func _be16(high: int, low: int) -> int: return ((high & 0xff) << 8) | (low & 0xff)
static func _signed_be16(high: int, low: int) -> int:
	var value := _be16(high, low); return value - 0x10000 if value & 0x8000 else value
