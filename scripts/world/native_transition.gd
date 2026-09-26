extends RefCounted
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
