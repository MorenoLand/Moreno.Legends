shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, fog_disabled;
uniform float sorting_bias = 0.0;
void vertex() {
	mat4 billboard = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	vec4 view_vertex = billboard * vec4(VERTEX, 1.0);
	vec4 clip = PROJECTION_MATRIX * view_vertex;
	vec4 center = VIEW_MATRIX * MODEL_MATRIX[3];
	vec4 sorted = PROJECTION_MATRIX * vec4(0.0, 0.0, -max(0.001, -center.z - sorting_bias), 1.0);
	clip.z = sorted.z / sorted.w * clip.w;
	POSITION = clip;
}
void fragment() {
	ALBEDO = COLOR.rgb;
	ALPHA = 1.0;
}
