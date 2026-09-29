shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D albedo_texture : source_color, filter_nearest, repeat_disable;
uniform float color_scale = 255.0;
uniform bool double_sided = false;
uniform vec3 pane_min;
uniform vec3 pane_max;
uniform vec2 pane_uv_min;
uniform vec2 pane_uv_max;
uniform bool snowfall_enabled = false;
uniform sampler2D snow_texture : source_color, filter_nearest, repeat_disable;
uniform sampler2D reflection_texture : source_color, filter_linear, repeat_enable;
varying float pane;
varying vec3 pane_position;
void vertex() {
	pane_position = VERTEX;
	pane = all(greaterThanEqual(VERTEX, pane_min - vec3(0.002))) && all(lessThanEqual(VERTEX, pane_max + vec3(0.002))) && all(greaterThanEqual(UV, pane_uv_min - vec2(0.002))) && all(lessThanEqual(UV, pane_uv_max + vec2(0.002))) ? 1.0 : 0.0;
}
void fragment() {
	if (pane < 0.999 && !double_sided && !FRONT_FACING) { discard; }
	vec4 pixel = texture(albedo_texture, UV);
	if (pixel.a < 0.5 && pane < 0.999) { discard; }
	ALBEDO = pixel.rgb * COLOR.rgb * color_scale / 128.0;
	ALPHA = pane > 0.999 ? pixel.a * 0.12 : pixel.a;
	if (pane > 0.999) {
		vec3 normal = normalize(NORMAL); vec3 view_direction = normalize(VIEW); float fresnel = pow(1.0 - abs(dot(normal, view_direction)), 5.0);
		vec3 reflected = normalize((INV_VIEW_MATRIX * vec4(reflect(-view_direction, normal), 0.0)).xyz); float angle = atan(reflected.z, reflected.x) / 6.28318530718 + 0.5; float row = clamp((0.12 - reflected.y) / 0.4, 0.0, 1.0);
		vec4 reflection = texture(reflection_texture, vec2(fract(angle * 4.0), (row * 127.0 + 0.5) / 256.0));
		ALBEDO = mix(vec3(0.55, 0.71, 0.77), reflection.rgb, reflection.a * (0.3 + 0.5 * fresnel)); ALPHA = 0.065 + 0.22 * fresnel;
	}
	if (pane > 0.999 && snowfall_enabled) {
		vec2 pane_uv = (UV - pane_uv_min) / max(pane_uv_max - pane_uv_min, vec2(0.001));
		float snow = 0.0;
		for (int layer = 0; layer < 3; layer++) {
			float depth = float(layer); vec2 field = pane_uv * vec2(7.0 + depth * 3.0, 4.0 + depth * 2.0) + pane_position.xz * 0.25 + vec2(TIME * (0.12 + depth * 0.04), -TIME * (0.3 + depth * 0.12));
			vec2 cell = floor(field); float seed = fract(sin(dot(cell + vec2(depth * 17.0), vec2(12.9898, 78.233))) * 43758.5453);
			vec2 sprite_uv = (fract(field) - vec2(0.2 + seed * 0.6, 0.2 + fract(seed * 13.0) * 0.6)) / (0.12 - depth * 0.025) + 0.5;
			if (all(greaterThanEqual(sprite_uv, vec2(0.0))) && all(lessThanEqual(sprite_uv, vec2(1.0)))) { vec4 flake = texture(snow_texture, sprite_uv); snow = max(snow, max(flake.r, max(flake.g, flake.b)) * flake.a * (0.9 - depth * 0.2)); }
		}
		float opacity = snow + ALPHA * (1.0 - snow);
		ALBEDO = (vec3(snow) + ALBEDO * ALPHA * (1.0 - snow)) / max(opacity, 0.0001); ALPHA = opacity;
	}
}
