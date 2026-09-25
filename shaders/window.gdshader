shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D albedo_texture : source_color, filter_nearest, repeat_disable;
uniform float color_scale = 255.0;
uniform bool double_sided = false;
uniform vec3 pane_min;
uniform vec3 pane_max;
uniform vec2 pane_uv_min;
uniform vec2 pane_uv_max;
varying float pane;
void vertex() {
	pane = all(greaterThanEqual(VERTEX, pane_min - vec3(0.002))) && all(lessThanEqual(VERTEX, pane_max + vec3(0.002))) && all(greaterThanEqual(UV, pane_uv_min - vec2(0.002))) && all(lessThanEqual(UV, pane_uv_max + vec2(0.002))) ? 1.0 : 0.0;
}
void fragment() {
	if (!double_sided && !FRONT_FACING) { discard; }
	vec4 pixel = texture(albedo_texture, UV);
	if (pixel.a < 0.5) { discard; }
	ALBEDO = pixel.rgb * COLOR.rgb * color_scale / 128.0;
	ALPHA = pixel.a * (pane > 0.999 ? 0.12 : 1.0);
}
