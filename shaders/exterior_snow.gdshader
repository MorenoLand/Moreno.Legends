shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;
uniform sampler2D snow_texture : source_color, filter_linear, repeat_disable;
// The parked exterior shows only through the entrance door and window pane apertures (gate planes + lateral/vertical bounds, as room_clip_view_gate in native_model).
uniform int gate_count = 0;
uniform vec4 gate_planes[8];
uniform vec4 gate_bounds[8];
varying vec3 particle_position;
void vertex() {
	particle_position = MODEL_MATRIX[3].xyz;
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(vec4(INV_VIEW_MATRIX[0].xyz * length(MODEL_MATRIX[0].xyz), 0.0), vec4(INV_VIEW_MATRIX[1].xyz * length(MODEL_MATRIX[1].xyz), 0.0), vec4(INV_VIEW_MATRIX[2].xyz * length(MODEL_MATRIX[2].xyz), 0.0), MODEL_MATRIX[3]);
}
void fragment() {
	vec3 eye = INV_VIEW_MATRIX[3].xyz; bool seen = false;
	for (int i = 0; i < gate_count; i++) {
		float eye_distance = dot(vec4(eye, 1.0), gate_planes[i]); float distance = dot(vec4(particle_position, 1.0), gate_planes[i]);
		if (eye_distance >= 0.0 || distance < 0.0) { continue; }
		vec3 crossing = mix(eye, particle_position, eye_distance / (eye_distance - distance)); float lateral = dot(crossing.xz, vec2(-gate_planes[i].z, gate_planes[i].x));
		if (lateral >= gate_bounds[i].x && lateral <= gate_bounds[i].y && crossing.y >= gate_bounds[i].z && crossing.y <= gate_bounds[i].w) { seen = true; }
	}
	if (!seen) { discard; }
	vec4 flake = texture(snow_texture, UV); ALBEDO = vec3(1.0); ALPHA = max(flake.r, max(flake.g, flake.b)) * flake.a;
}
