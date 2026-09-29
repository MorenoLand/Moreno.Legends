extends RefCounted
static func fade_profile(route: Dictionary) -> Dictionary:
	for contact: Dictionary in route.get("native_contacts", []):
		var type := int(contact.get("type", -1)); var cover := -1; var reveal := 0x02; var source := ""
		if type in [2, 3, 8, 9]:
			var stage := str(route.get("source_stage", ""))
			if stage.is_empty(): return {}
			cover = 0xFF if stage == str(route.get("destination_stage", "")) else 0x28; reveal = 0xFF if cover == 0xFF else 0x02; source = "GAME0x800B7C40"
		elif type in [4, 5, 6, 7, 11]: cover = 0x26; source = "GAME0x800B7E4C"
		elif type == 13: cover = 0x1A; reveal = 0x0A; source = "GAME0x800B7FBC"
		elif type == 12: cover = 0x28; source = "GAME0x800B8108"
		elif type == 15: cover = 0x28; source = "GAME0x800B844C"
		elif type in [16, 17]: cover = 0x28; source = "GAME0x800B84FC"
		if cover >= 0: return {"exit": cover, "entry": reveal, "native_contact_type": type, "source": source}
	return {}
static func is_elevator(route: Dictionary) -> bool:
	if str(route.get("native_door", {}).get("style", "")) == "elevator": return true
	for contact: Dictionary in route.get("native_contacts", []):
		if int(contact.get("type", -1)) == 4: return true
	return false
static func is_ladder(route: Dictionary) -> bool:
	for contact: Dictionary in route.get("native_contacts", []):
		if int(contact.get("type", -1)) == 11: return true
	return false
static func manual_contact(route: Dictionary, position: Vector3, yaw: float) -> bool:
	var start := Vector3(-position.x, -position.y, position.z) * 256.0
	for contact: Dictionary in route.get("native_contacts", []):
		if bool(contact.get("automatic", false)): continue
		var step := float(contact.get("probe_forward_raw", 0)); var finish := start + Vector3(-sin(yaw) * step, 0, cos(yaw) * step); var minimum := Vector3(contact["x"][0], contact["y"][0], contact["z"][0]) - Vector3.ONE; var maximum := Vector3(contact["x"][1], contact["y"][1], contact["z"][1]) + Vector3.ONE; var direction := finish - start; var entry := 0.0; var exit := 1.0
		for axis in 3:
			if is_zero_approx(direction[axis]):
				if start[axis] < minimum[axis] or start[axis] > maximum[axis]: exit = -1.0; break
			else:
				var first := (minimum[axis] - start[axis]) / direction[axis]; var last := (maximum[axis] - start[axis]) / direction[axis]; entry = maxf(entry, minf(first, last)); exit = minf(exit, maxf(first, last))
		if entry <= exit: return true
	return false
static func automatic_route(routes: Array, position: Vector3) -> Dictionary:
	var native := Vector3i(int(-position.x * 256.0), int(-position.y * 256.0), int(position.z * 256.0))
	for route: Dictionary in routes:
		for contact: Dictionary in route.get("native_contacts", []):
			if not bool(contact.get("automatic", false)) or int(contact["mask"]) & 0x8000: continue
			var x: Array = contact["x"]; var y: Array = contact["y"]; var z: Array = contact["z"]
			if native.x > int(x[0]) - 1 and native.x < int(x[1]) + 1 and native.y > int(y[0]) - 1 and native.y < int(y[1]) + 1 and native.z > int(z[0]) - 1 and native.z < int(z[1]) + 1: return route
	return {}
static func is_automatic(route: Dictionary) -> bool:
	for contact: Dictionary in route.get("native_contacts", []):
		if bool(contact.get("automatic", false)): return true
	return false
