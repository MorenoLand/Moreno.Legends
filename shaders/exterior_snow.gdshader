shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;
uniform sampler2D snow_texture : source_color, filter_linear, repeat_disable;
// The parked exterior shows only through the entrance aperture (plane + lateral/vertical bounds, as room_clip_view_gate in native_model).
uniform vec4 room_clip_plane = vec4(0.0);
uniform vec4 room_clip_bound = vec4(0.0);
varying vec3 particle_position;
void vertex() {
	particle_position = MODEL_MATRIX[3].xyz;
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(vec4(INV_VIEW_MATRIX[0].xyz * length(MODEL_MATRIX[0].xyz), 0.0), vec4(INV_VIEW_MATRIX[1].xyz * length(MODEL_MATRIX[1].xyz), 0.0), vec4(INV_VIEW_MATRIX[2].xyz * length(MODEL_MATRIX[2].xyz), 0.0), MODEL_MATRIX[3]);
}
void fragment() {
	vec3 eye = INV_VIEW_MATRIX[3].xyz; float eye_distance = dot(vec4(eye, 1.0), room_clip_plane); float distance = dot(vec4(particle_position, 1.0), room_clip_plane);
	if (distance < 0.0) { discard; }
	if (eye_distance < 0.0) {
		vec3 crossing = mix(eye, particle_position, eye_distance / (eye_distance - distance)); float lateral = dot(crossing.xz, vec2(-room_clip_plane.z, room_clip_plane.x));
		if (lateral < room_clip_bound.x || lateral > room_clip_bound.y || crossing.y < room_clip_bound.z || crossing.y > room_clip_bound.w) { discard; }
	}
	vec4 flake = texture(snow_texture, UV); ALBEDO = vec3(1.0); ALPHA = max(flake.r, max(flake.g, flake.b)) * flake.a;
}
