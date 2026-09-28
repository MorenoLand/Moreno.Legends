shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_always, shadows_disabled, fog_disabled, skip_vertex_transform;
uniform sampler2D page : source_color, filter_nearest, repeat_disable;
uniform vec2 origin;
uniform float depth;
void vertex() { vec4 clip = PROJECTION_MATRIX * vec4(0.0, 0.0, -depth, 1.0); POSITION = vec4(VERTEX.xy * clip.w, clip.z, clip.w); }
void fragment() {
	float factor = VIEWPORT_SIZE.y / 240.0; vec2 screen = vec2((FRAGCOORD.x - (VIEWPORT_SIZE.x - 320.0 * factor) * 0.5) / factor, FRAGCOORD.y / factor) - origin; vec2 cell = floor(screen / 128.0); vec2 texel = screen - cell * 128.0;
	ALBEDO = texelFetch(page, ivec2(int(mod(cell.y, 2.0)) * 128 + int(texel.x), 128 + int(texel.y)), 0).rgb;
}
