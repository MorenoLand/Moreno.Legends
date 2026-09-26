shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D albedo_texture : source_color, filter_nearest, repeat_disable;
uniform vec4 roof_texture_region = vec4(0.0);
uniform vec3 light_rgb = vec3(128.0);
uniform float color_scale = 255.0;
uniform bool double_sided = true;
uniform bool part_visible = true;
uniform bool coplanar_overlay_flags = false;
uniform int uv_word = 0;
uniform bool native_depth_cue_enabled = false;
uniform int native_depth_cue_shift = 0;
uniform vec3 native_far_color = vec3(0.0);
varying vec3 native_vertex_rgb;
uniform bool portal_clip_enabled = false;
uniform vec4 portal_clip_plane = vec4(0.0);
uniform int room_clip_count = 0;
uniform vec4 room_clip_planes[16];
uniform float room_clip_limits[16];
uniform int portal_floor_clip_count = 0;
uniform vec4 portal_floor_clip_planes[16];
uniform vec4 portal_floor_clip_bounds[16];
varying vec3 portal_world_position;
void vertex() {
	portal_world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	native_vertex_rgb = clamp(COLOR.rgb * color_scale + light_rgb - 128.0, vec3(0.0), vec3(255.0));
	if (native_depth_cue_enabled) {
		int sz = clamp(int(floor(max(-(VIEW_MATRIX * vec4(portal_world_position, 1.0)).z, 0.0) * 256.0 * float(1 << native_depth_cue_shift))), 0, 65535);
		int ir0 = sz >> native_depth_cue_shift;
		ivec3 active = ivec3(round(native_vertex_rgb));
		ivec3 far_rgb = ivec3(native_far_color);
		native_vertex_rgb = vec3(clamp((active * (4096 - ir0) + far_rgb * ir0) >> 12, ivec3(0), ivec3(255)));
	}
	if (uv_word != 0) {
		ivec2 pixel = ivec2(floor(UV * 256.0));
		int packed = (pixel.x + (pixel.y << 8) + (uv_word & 65535)) & 65535;
		UV = (vec2(float(packed & 255), float((packed >> 8) & 255)) + vec2(0.5)) / 256.0;
	}
	if (coplanar_overlay_flags && COLOR.a < 0.5) {
		float layer = max(1.0, round(COLOR.a * 255.0));
		mat4 inverse_view = inverse(MODELVIEW_MATRIX);
		vec3 view_normal = normalize((transpose(inverse_view) * vec4(NORMAL, 0.0)).xyz);
		vec3 view_position = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
		float facing = dot(view_normal, -view_position) >= 0.0 ? 1.0 : -1.0;
		VERTEX += (inverse_view * vec4(view_normal * facing * layer / 256.0, 0.0)).xyz;
	}
}
void fragment() {
	for (int i = 0; i < room_clip_count; i++) {
		if (dot(vec4(portal_world_position, 1.0), room_clip_planes[i]) <= room_clip_limits[i]) { discard; }
	}
	if (room_clip_count == 0 && portal_clip_enabled && dot(vec4(portal_world_position, 1.0), portal_clip_plane) <= 0.0001) { discard; }
	if (portal_floor_clip_count > 0 && abs(normalize(cross(dFdx(portal_world_position), dFdy(portal_world_position))).y) >= 0.65) {
		for (int i = 0; i < portal_floor_clip_count; i++) {
			vec4 plane = portal_floor_clip_planes[i];
			vec4 bounds = portal_floor_clip_bounds[i];
			float lateral = abs(plane.x) > 0.5 ? portal_world_position.z : portal_world_position.x;
			if (dot(vec4(portal_world_position, 1.0), plane) < -0.0001 && lateral >= bounds.x && lateral <= bounds.y && portal_world_position.y >= bounds.z && portal_world_position.y <= bounds.w) { discard; }
		}
	}
	if (!part_visible || (!double_sided && !FRONT_FACING)) { discard; }
	vec2 sample_uv = roof_texture_region.z > 0.0 ? roof_texture_region.xy + fract(portal_world_position.xz) * roof_texture_region.zw : UV;
	vec4 pixel = texture(albedo_texture, sample_uv);
	ALBEDO = pixel.rgb * native_vertex_rgb / 128.0;
	ALPHA = pixel.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
}
