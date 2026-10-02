extends RefCounted
## PlayStation Geometry Transformation Engine (COP2) as used by the translated original code: RTPS, RTPT, MVMVA, NCLIP, OP, SQR, AVSZ3/4, GPF and GPL.

const FLAG_ERROR_MASK := 0x7F87E000

var d := PackedInt32Array()
var c := PackedInt32Array()
var unr := PackedInt32Array()


func _init() -> void:
	d.resize(32)
	c.resize(32)
	unr.resize(0x101)
	for i in 0x101:
		unr[i] = maxi(0, (0x40000 / (i + 0x100) + 1) / 2 - 0x101)


static func s16(value: int) -> int:
	return ((value & 0xFFFF) ^ 0x8000) - 0x8000


func _flag(bit: int) -> void:
	c[31] |= 1 << bit


func _clamp_ir(index: int, value: int, lm: bool) -> int:
	var low := 0 if lm else -0x8000
	if value > 0x7FFF:
		_flag(25 - index)
		return 0x7FFF
	if value < low:
		_flag(25 - index)
		return low
	return value


func _mac(index: int, value: int) -> int:
	if value >= 0x80000000000:
		_flag(31 - index)
	elif value < -0x80000000000:
		_flag(28 - index)
	return value


func _store_mac(index: int, value: int, shift: int) -> int:
	var result := _mac(index, value) >> shift
	d[24 + index] = result
	return result


func _push_sz(value: int) -> void:
	d[16] = d[17]
	d[17] = d[18]
	d[18] = d[19]
	if value < 0:
		_flag(18)
		value = 0
	elif value > 0xFFFF:
		_flag(18)
		value = 0xFFFF
	d[19] = value


func _push_sxy(x: int, y: int) -> void:
	d[12] = d[13]
	d[13] = d[14]
	if x < -0x400:
		_flag(14)
		x = -0x400
	elif x > 0x3FF:
		_flag(14)
		x = 0x3FF
	if y < -0x400:
		_flag(13)
		y = -0x400
	elif y > 0x3FF:
		_flag(13)
		y = 0x3FF
	d[14] = (x & 0xFFFF) | ((y & 0xFFFF) << 16)
	d[15] = d[14]


func _matrix(base: int) -> Array:
	return [
		[s16(c[base]), s16(c[base] >> 16), s16(c[base + 1])],
		[s16(c[base + 1] >> 16), s16(c[base + 2]), s16(c[base + 2] >> 16)],
		[s16(c[base + 3]), s16(c[base + 3] >> 16), s16(c[base + 4])]]


func _vector(index: int) -> Array:
	if index < 3:
		return [s16(d[2 * index]), s16(d[2 * index] >> 16), s16(d[2 * index + 1])]
	return [s16(d[9]), s16(d[10]), s16(d[11])]


func _divide(h: int, sz3: int) -> int:
	if h >= sz3 * 2:
		_flag(17)
		return 0x1FFFF
	var z := 0
	var probe := sz3
	if probe < 0x100:
		z = 8
		probe <<= 8
	if probe < 0x1000:
		z += 4
		probe <<= 4
	if probe < 0x4000:
		z += 2
		probe <<= 2
	if probe < 0x8000:
		z += 1
	var n := h << z
	var den := sz3 << z
	var u := unr[(den - 0x7FC0) >> 7] + 0x101
	den = (0x2000080 - den * u) >> 8
	den = (0x0000080 + den * u) >> 8
	return mini(0x1FFFF, ((n * den) + 0x8000) >> 16)


func _rtp(index: int, sf: int, lm: bool) -> void:
	var packed := d[2 * index]
	var vx := ((packed & 0xFFFF) ^ 0x8000) - 0x8000
	var vy := (((packed >> 16) & 0xFFFF) ^ 0x8000) - 0x8000
	var vz := ((d[2 * index + 1] & 0xFFFF) ^ 0x8000) - 0x8000
	var w0 := c[0]
	var w1 := c[1]
	var w2 := c[2]
	var w3 := c[3]
	var shift := 12 * sf
	var raw1 := (c[5] << 12) + (((w0 & 0xFFFF) ^ 0x8000) - 0x8000) * vx + ((((w0 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * vy + (((w1 & 0xFFFF) ^ 0x8000) - 0x8000) * vz
	var raw2 := (c[6] << 12) + ((((w1 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * vx + (((w2 & 0xFFFF) ^ 0x8000) - 0x8000) * vy + ((((w2 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * vz
	var raw3 := (c[7] << 12) + (((w3 & 0xFFFF) ^ 0x8000) - 0x8000) * vx + ((((w3 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * vy + (((c[4] & 0xFFFF) ^ 0x8000) - 0x8000) * vz
	if raw1 >= 0x80000000000:
		_flag(30)
	elif raw1 < -0x80000000000:
		_flag(27)
	if raw2 >= 0x80000000000:
		_flag(29)
	elif raw2 < -0x80000000000:
		_flag(26)
	if raw3 >= 0x80000000000:
		_flag(28)
	elif raw3 < -0x80000000000:
		_flag(25)
	var mac1 := raw1 >> shift
	var mac2 := raw2 >> shift
	var mac3 := raw3 >> shift
	d[25] = mac1
	d[26] = mac2
	d[27] = mac3
	var low := 0 if lm else -0x8000
	if mac1 > 0x7FFF:
		_flag(24)
		d[9] = 0x7FFF
	elif mac1 < low:
		_flag(24)
		d[9] = low
	else:
		d[9] = mac1
	if mac2 > 0x7FFF:
		_flag(23)
		d[10] = 0x7FFF
	elif mac2 < low:
		_flag(23)
		d[10] = low
	else:
		d[10] = mac2
	var test3 := raw3 >> 12
	if test3 > 0x7FFF or test3 < -0x8000:
		_flag(22)
	d[11] = clampi(mac3, low, 0x7FFF)
	_push_sz(test3)
	var q := _divide(c[26] & 0xFFFF, d[19] & 0xFFFF)
	var sx := c[24] + d[9] * q
	var sy := c[25] + d[10] * q
	if sx >= 0x80000000 or sx < -0x80000000:
		_flag(16 if sx > 0 else 15)
	if sy >= 0x80000000 or sy < -0x80000000:
		_flag(16 if sy > 0 else 15)
	_push_sxy(sx >> 16, sy >> 16)
	var mac0 := q * (((c[27] & 0xFFFF) ^ 0x8000) - 0x8000) + c[28]
	if mac0 >= 0x80000000 or mac0 < -0x80000000:
		_flag(16 if mac0 > 0 else 15)
	d[24] = mac0
	var ir0 := mac0 >> 12
	if ir0 > 0x1000:
		_flag(12)
		ir0 = 0x1000
	elif ir0 < 0:
		_flag(12)
		ir0 = 0
	d[8] = ir0


func _mvmva(sf: int, mx: int, vx: int, cv: int, lm: bool) -> void:
	if mx == 3 or cv == 2:
		_mvmva_special(sf, mx, vx, cv, lm)
		return
	var base := mx << 3
	var w0 := c[base]
	var w1 := c[base + 1]
	var w2 := c[base + 2]
	var w3 := c[base + 3]
	var x: int
	var y: int
	var z: int
	if vx < 3:
		var packed := d[2 * vx]
		x = ((packed & 0xFFFF) ^ 0x8000) - 0x8000
		y = (((packed >> 16) & 0xFFFF) ^ 0x8000) - 0x8000
		z = ((d[2 * vx + 1] & 0xFFFF) ^ 0x8000) - 0x8000
	else:
		x = ((d[9] & 0xFFFF) ^ 0x8000) - 0x8000
		y = ((d[10] & 0xFFFF) ^ 0x8000) - 0x8000
		z = ((d[11] & 0xFFFF) ^ 0x8000) - 0x8000
	var shift := 12 * sf
	var raw1 := (((w0 & 0xFFFF) ^ 0x8000) - 0x8000) * x + ((((w0 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * y + (((w1 & 0xFFFF) ^ 0x8000) - 0x8000) * z
	var raw2 := ((((w1 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * x + (((w2 & 0xFFFF) ^ 0x8000) - 0x8000) * y + ((((w2 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * z
	var raw3 := (((w3 & 0xFFFF) ^ 0x8000) - 0x8000) * x + ((((w3 >> 16) & 0xFFFF) ^ 0x8000) - 0x8000) * y + (((c[base + 4] & 0xFFFF) ^ 0x8000) - 0x8000) * z
	if cv != 3:
		var t := 5 + 8 * cv
		raw1 += c[t] << 12
		raw2 += c[t + 1] << 12
		raw3 += c[t + 2] << 12
	_store_mvmva(raw1, raw2, raw3, shift, lm)


func _store_mvmva(raw1: int, raw2: int, raw3: int, shift: int, lm: bool) -> void:
	if raw1 >= 0x80000000000:
		_flag(30)
	elif raw1 < -0x80000000000:
		_flag(27)
	if raw2 >= 0x80000000000:
		_flag(29)
	elif raw2 < -0x80000000000:
		_flag(26)
	if raw3 >= 0x80000000000:
		_flag(28)
	elif raw3 < -0x80000000000:
		_flag(25)
	var mac1 := raw1 >> shift
	var mac2 := raw2 >> shift
	var mac3 := raw3 >> shift
	d[25] = mac1
	d[26] = mac2
	d[27] = mac3
	var low := 0 if lm else -0x8000
	if mac1 > 0x7FFF:
		_flag(24)
		d[9] = 0x7FFF
	elif mac1 < low:
		_flag(24)
		d[9] = low
	else:
		d[9] = mac1
	if mac2 > 0x7FFF:
		_flag(23)
		d[10] = 0x7FFF
	elif mac2 < low:
		_flag(23)
		d[10] = low
	else:
		d[10] = mac2
	if mac3 > 0x7FFF:
		_flag(22)
		d[11] = 0x7FFF
	elif mac3 < low:
		_flag(22)
		d[11] = low
	else:
		d[11] = mac3


func _mvmva_special(sf: int, mx: int, vx: int, cv: int, lm: bool) -> void:
	var rows: Array
	if mx == 3:
		rows = [[-(s16(d[6] & 0xFF) << 4), s16(d[6] & 0xFF) << 4, s16(d[8])], [s16(c[1]), s16(c[1]), s16(c[1])], [s16(c[2]), s16(c[2]), s16(c[2])]]
	else:
		rows = _matrix([0, 8, 16][mx])
	var v := _vector(vx)
	var t := [0, 0, 0]
	if cv != 3:
		var base: int = [5, 13, 21][cv]
		t = [c[base], c[base + 1], c[base + 2]]
	var shift := 12 * sf
	var out := [0, 0, 0]
	for i in 3:
		var value: int = (t[i] << 12)
		if cv == 2:
			var fc: int = (value + rows[i][0] * v[0])
			_mac(i + 1, fc)
			_clamp_ir(i + 1, fc >> shift, false)
			value = rows[i][1] * v[1] + rows[i][2] * v[2]
		else:
			value += rows[i][0] * v[0] + rows[i][1] * v[1] + rows[i][2] * v[2]
		out[i] = _store_mac(i + 1, value, shift)
	for i in 3:
		d[9 + i] = _clamp_ir(i + 1, out[i], lm)


func cmd(command: int) -> void:
	var op := command & 0x3F
	var sf := (command >> 19) & 1
	var lm := ((command >> 10) & 1) == 1
	c[31] = 0
	match op:
		0x01:
			_rtp(0, sf, lm)
		0x30:
			for i in 3:
				_rtp(i, sf, lm)
		0x12:
			_mvmva(sf, (command >> 17) & 3, (command >> 15) & 3, (command >> 13) & 3, lm)
		0x06:
			var sx := [s16(d[12]), s16(d[13]), s16(d[14])]
			var sy := [s16(d[12] >> 16), s16(d[13] >> 16), s16(d[14] >> 16)]
			var value: int = sx[0] * sy[1] + sx[1] * sy[2] + sx[2] * sy[0] - sx[0] * sy[2] - sx[1] * sy[0] - sx[2] * sy[1]
			if value >= 0x80000000 or value < -0x80000000:
				_flag(16 if value > 0 else 15)
			d[24] = value
		0x0C:
			var rot := _matrix(0)
			var ir := [s16(d[9]), s16(d[10]), s16(d[11])]
			var shift := 12 * sf
			var a := _store_mac(1, rot[1][1] * ir[2] - rot[2][2] * ir[1], shift)
			var b := _store_mac(2, rot[2][2] * ir[0] - rot[0][0] * ir[2], shift)
			var e := _store_mac(3, rot[0][0] * ir[1] - rot[1][1] * ir[0], shift)
			d[9] = _clamp_ir(1, a, lm)
			d[10] = _clamp_ir(2, b, lm)
			d[11] = _clamp_ir(3, e, lm)
		0x28:
			var shift2 := 12 * sf
			for i in 3:
				var q := s16(d[9 + i])
				d[25 + i] = _mac(i + 1, q * q) >> shift2
			for i in 3:
				d[9 + i] = _clamp_ir(i + 1, d[25 + i], lm)
		0x2D:
			var m0 := s16(c[29]) * (d[17] + d[18] + d[19])
			d[24] = m0
			_otz(m0)
		0x2E:
			var m1 := s16(c[30]) * (d[16] + d[17] + d[18] + d[19])
			d[24] = m1
			_otz(m1)
		0x3D:
			var shift3 := 12 * sf
			var ir0 := s16(d[8])
			for i in 3:
				d[25 + i] = _mac(i + 1, s16(d[9 + i]) * ir0) >> shift3
			for i in 3:
				d[9 + i] = _clamp_ir(i + 1, d[25 + i], lm)
			_push_color()
		0x3E:
			var shift4 := 12 * sf
			var ir0b := s16(d[8])
			for i in 3:
				d[25 + i] = _mac(i + 1, (d[25 + i] << shift4) + s16(d[9 + i]) * ir0b) >> shift4
			for i in 3:
				d[9 + i] = _clamp_ir(i + 1, d[25 + i], lm)
			_push_color()
		_:
			push_error("Unsupported GTE command 0x%X" % command)


func _otz(value: int) -> void:
	var result := value >> 12
	if result < 0:
		_flag(18)
		result = 0
	elif result > 0xFFFF:
		_flag(18)
		result = 0xFFFF
	d[7] = result


func _push_color() -> void:
	d[20] = d[21]
	d[21] = d[22]
	var packed := d[6] & 0xFF000000
	for i in 3:
		var value := d[25 + i] >> 4
		if value < 0:
			_flag(21 - i)
			value = 0
		elif value > 255:
			_flag(21 - i)
			value = 255
		packed |= value << (8 * i)
	d[22] = packed


func mfc2(index: int) -> int:
	match index:
		1, 3, 5, 8, 9, 10, 11:
			return s16(d[index])
		7, 16, 17, 18, 19:
			return d[index] & 0xFFFF
		15:
			return d[14]
		29:
			return _orgb()
		_:
			return d[index]


func _orgb() -> int:
	var result := 0
	for i in 3:
		result |= clampi(s16(d[9 + i]) >> 7, 0, 31) << (5 * i)
	return result


func mtc2(index: int, value: int) -> void:
	match index:
		15:
			_push_raw_sxy(value)
		28:
			d[28] = value & 0x7FFF
			for i in 3:
				d[9 + i] = ((value >> (5 * i)) & 0x1F) * 0x80
		29:
			pass
		30:
			d[30] = value
			var probe := value if value >= 0 else ~value
			var count := 32
			for bit in range(31, -1, -1):
				if (probe >> bit) & 1:
					count = 31 - bit
					break
			d[31] = count
		31:
			pass
		_:
			d[index] = value


func _push_raw_sxy(value: int) -> void:
	d[12] = d[13]
	d[13] = d[14]
	d[14] = value
	d[15] = value


func cfc2(index: int) -> int:
	match index:
		4, 12, 20, 26, 27, 28, 29, 30:
			return s16(c[index]) if index != 28 else c[index]
		31:
			var flag := c[31] & 0x7FFFF000
			if c[31] & FLAG_ERROR_MASK:
				flag |= 0x80000000
			return flag
		_:
			return c[index]


func ctc2(index: int, value: int) -> void:
	c[index] = value
