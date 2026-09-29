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
		// Port-only glass look (the original shows no outside view): tint, sliding diagonal sheen, heavier edges.
		vec2 glass_uv = (UV - pane_uv_min) / max(pane_uv_max - pane_uv_min, vec2(0.001));
		float edge = 1.0 - smoothstep(0.0, 0.1, min(min(glass_uv.x, 1.0 - glass_uv.x), min(glass_uv.y, 1.0 - glass_uv.y)));
		float slide = (INV_VIEW_MATRIX * vec4(view_direction, 0.0)).x * 0.35 + (INV_VIEW_MATRIX * vec4(view_direction, 0.0)).z * 0.2;
		float band = fract((glass_uv.x + glass_uv.y * 0.55) * 0.9 + slide);
		float sheen = smoothstep(0.30, 0.36, band) * (1.0 - smoothstep(0.36, 0.46, band)) + 0.55 * smoothstep(0.52, 0.54, band) * (1.0 - smoothstep(0.54, 0.58, band));
		ALBEDO = mix(vec3(0.58, 0.74, 0.80), reflection.rgb, reflection.a * (0.3 + 0.5 * fresnel)) + vec3(sheen * 0.3);
		ALPHA = clamp(0.13 + 0.3 * fresnel + sheen * 0.12 + edge * 0.1, 0.0, 0.75);
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
