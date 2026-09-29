shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never;
uniform sampler2D snow_texture : source_color, filter_linear, repeat_disable;
uniform int interior_clip_count = 0;
uniform vec3 interior_clip_min[16];
uniform vec3 interior_clip_max[16];
varying vec3 particle_position;
void vertex() {
	particle_position = MODEL_MATRIX[3].xyz;
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(vec4(INV_VIEW_MATRIX[0].xyz * length(MODEL_MATRIX[0].xyz), 0.0), vec4(INV_VIEW_MATRIX[1].xyz * length(MODEL_MATRIX[1].xyz), 0.0), vec4(INV_VIEW_MATRIX[2].xyz * length(MODEL_MATRIX[2].xyz), 0.0), MODEL_MATRIX[3]);
}
void fragment() {
	for (int i = 0; i < interior_clip_count; i++) {
		if (all(greaterThanEqual(particle_position, interior_clip_min[i])) && all(lessThanEqual(particle_position, interior_clip_max[i]))) { discard; }
	}
	vec4 flake = texture(snow_texture, UV); ALBEDO = vec3(1.0); ALPHA = max(flake.r, max(flake.g, flake.b)) * flake.a;
}
