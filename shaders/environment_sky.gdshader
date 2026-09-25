shader_type sky;
uniform vec3 sky_zenith : source_color;
uniform vec3 sky_mid : source_color;
uniform vec3 sky_horizon : source_color;
uniform sampler2D cloud_texture : source_color, filter_nearest, repeat_disable;
void sky() {
	float vertical = clamp((0.1 - EYEDIR.y) / 0.26, 0.0, 1.0);
	vec3 upper = mix(sky_zenith, sky_mid, smoothstep(0.0, 0.5, vertical));
	COLOR = mix(upper, sky_horizon, smoothstep(0.5, 1.0, vertical));
	float angle = atan(EYEDIR.z, EYEDIR.x) / 6.28318530718 + 0.5;
	float row = clamp((0.12 - EYEDIR.y) / 0.4, 0.0, 1.0);
	vec4 clouds = texture(cloud_texture, vec2((fract(angle * 4.0) * 255.0 + 0.5) / 256.0, (row * 127.0 + 0.5) / 256.0));
	COLOR = mix(COLOR, clouds.rgb, clouds.a * (1.0 - smoothstep(-0.04, 0.12, EYEDIR.y)));
}
