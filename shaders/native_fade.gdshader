shader_type canvas_item;
render_mode unshaded;
uniform sampler2D screen_texture : hint_screen_texture, repeat_disable, filter_nearest;
uniform sampler2D frozen_scene : repeat_disable, filter_nearest;
uniform sampler2D mask_atlas : repeat_disable, filter_nearest;
uniform bool feedback = false;
uniform bool mask_active = false;
uniform bool additive = false;
uniform float shade_rgb8 = 0.0;
uniform vec4 atlas_rect = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec2 native_size = vec2(320.0, 240.0);
uniform vec2 display_size = vec2(320.0, 240.0);
uniform bool preserve_pixel_aspect = true;
void fragment() {
	vec3 source = feedback ? texture(frozen_scene, SCREEN_UV).rgb : texture(screen_texture, SCREEN_UV).rgb;
	vec3 rgb5 = floor(clamp(source, vec3(0.0), vec3(1.0)) * 255.0 / 8.0);
	vec2 native_uv = UV;
	if (preserve_pixel_aspect) { native_uv = (UV - vec2(0.5)) * display_size / (display_size.y / native_size.y) / native_size + vec2(0.5); }
	native_uv = (clamp(floor(native_uv * native_size), vec2(0.0), native_size - vec2(1.0)) + vec2(0.5)) / native_size;
	vec3 amount = feedback ? (mask_active ? floor(texture(mask_atlas, atlas_rect.xy + native_uv * atlas_rect.zw).rgb * 255.0 + vec3(0.5)) : vec3(0.0)) : vec3(floor(shade_rgb8 / 8.0));
	COLOR = vec4(clamp(rgb5 + (additive ? amount : -amount), vec3(0.0), vec3(31.0)) / 31.0, 1.0);
}
