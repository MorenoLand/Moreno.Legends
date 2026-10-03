shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D albedo_texture : source_color, filter_nearest, repeat_disable;
uniform vec4 roof_texture_region = vec4(0.0);
uniform vec3 light_rgb = vec3(128.0);
uniform float color_scale = 255.0;
uniform bool double_sided = true;
uniform bool part_visible = true;
uniform vec2 hidden_face_range = vec2(-1.0);
varying float native_source_face_order;
uniform bool coplanar_overlay_flags = false;
uniform int uv_word = 0;
uniform bool native_depth_cue_enabled = false;
uniform bool native_actor_visible = true;
uniform int native_depth_cue_shift = 0;
uniform vec3 native_far_color = vec3(0.0);
uniform bool native_palette_enabled = false;
uniform sampler2D native_palette_atlas : source_color, filter_nearest, repeat_disable;
uniform int native_palette_layers = 1;
uniform int native_palette_offsets[32];
uniform int native_palette_bucket_shift = 9;
varying flat float native_palette_layer;
uniform sampler2D native_map_cells : filter_nearest, repeat_disable;
uniform mat4 native_map_world_to_local;
uniform bool native_map_terrain = false;
uniform bool native_map_placement_visible = true;
uniform int interior_clip_count = 0;
uniform vec3 interior_clip_min[16];
uniform vec3 interior_clip_max[16];
varying vec3 native_vertex_rgb;
uniform bool portal_clip_enabled = false;
uniform vec4 portal_clip_plane = vec4(0.0);
uniform int room_clip_count = 0;
uniform vec4 room_clip_planes[16];
uniform float room_clip_limits[16];
uniform vec4 room_clip_bounds[16];
uniform vec2 room_clip_depths[16];
uniform bool room_clip_bounded[16];
uniform bool room_clip_view_gate[16];
uniform bool room_clip_view_cut[16];
uniform int portal_floor_clip_count = 0;
uniform vec4 portal_floor_clip_planes[16];
uniform vec4 portal_floor_clip_bounds[16];
uniform bool portal_floor_clip_bounded[16];
uniform vec2 portal_floor_clip_depths[16];
uniform bool doorway_aperture_enabled = false;
uniform int doorway_aperture_axis = 0;
uniform vec3 doorway_aperture_center = vec3(0.0);
uniform vec2 doorway_aperture_half = vec2(0.0);
uniform vec2 doorway_aperture_depths = vec2(0.0);
varying vec3 portal_world_position;
void vertex() {
	native_source_face_order = UV2.x;
	portal_world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	native_vertex_rgb = clamp(COLOR.rgb * color_scale + light_rgb - 128.0, vec3(0.0), vec3(255.0));
	native_palette_layer = 0.0;
	if (native_palette_enabled && CUSTOM3.w > 0.5) {
		float depth = max(max(-(MODELVIEW_MATRIX * vec4(CUSTOM0.xyz, 1.0)).z, -(MODELVIEW_MATRIX * vec4(CUSTOM1.xyz, 1.0)).z), max(-(MODELVIEW_MATRIX * vec4(CUSTOM2.xyz, 1.0)).z, -(MODELVIEW_MATRIX * vec4(CUSTOM3.xyz, 1.0)).z));
		int sz = clamp(int(floor(max(depth, 0.0) * 256.0 * float(1 << native_depth_cue_shift))), 0, 65535);
		native_palette_layer = float(native_palette_offsets[clamp(sz >> native_palette_bucket_shift, 0, 31)]);
	}
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
		vec3 toward_eye = normalize(-view_position);
		VERTEX += (inverse_view * vec4(toward_eye * layer / 256.0 / max(abs(dot(view_normal, toward_eye)), 0.25), 0.0)).xyz;
	}
}
void fragment() {
	if (!native_actor_visible) { discard; }
	if (!native_map_placement_visible) { discard; }
	if (native_map_terrain) {
		vec3 local = (native_map_world_to_local * vec4(portal_world_position, 1.0)).xyz;
		ivec2 cell = ivec2(floor((vec2(-local.x, local.z) * 256.0 + 32768.0) / 512.0));
		if (any(lessThan(cell, ivec2(0))) || any(greaterThanEqual(cell, ivec2(128))) || texture(native_map_cells, (vec2(cell) + vec2(0.5)) / 128.0).r < 0.5) { discard; }
	}
	if (hidden_face_range.x >= 0.0 && native_source_face_order >= hidden_face_range.x - 0.25 && native_source_face_order < hidden_face_range.y - 0.25) { discard; }
	for (int i = 0; i < interior_clip_count; i++) {
		if (all(greaterThanEqual(portal_world_position, interior_clip_min[i])) && all(lessThanEqual(portal_world_position, interior_clip_max[i]))) { discard; }
	}
	if (doorway_aperture_enabled) {
		// Doorway depth walls exist only for the view through the opening; hide them wherever the eye ray does not enter through the nearer mouth.
		vec3 eye_point = INV_VIEW_MATRIX[3].xyz; int across = doorway_aperture_axis == 0 ? 2 : 0; float eye_depth = eye_point[doorway_aperture_axis];
		if (eye_depth < doorway_aperture_depths.x || eye_depth > doorway_aperture_depths.y) {
			float mouth = eye_depth < doorway_aperture_depths.x ? doorway_aperture_depths.x : doorway_aperture_depths.y; float span = portal_world_position[doorway_aperture_axis] - eye_depth;
			if (abs(span) < 0.000001) { discard; }
			vec3 crossing = mix(eye_point, portal_world_position, (mouth - eye_depth) / span);
			if (abs(crossing[across] - doorway_aperture_center[across]) > doorway_aperture_half.x + 0.01 || abs(crossing.y - doorway_aperture_center.y) > doorway_aperture_half.y + 0.01) { discard; }
		}
	}
	bool aperture_required = false; bool aperture_visible = false; vec3 eye = INV_VIEW_MATRIX[3].xyz;
	for (int i = 0; i < room_clip_count; i++) {
		if (!room_clip_view_gate[i] && !room_clip_view_cut[i]) { continue; }
		vec4 plane = room_clip_planes[i]; float eye_distance = dot(vec4(eye, 1.0), plane); bool view_gate = room_clip_view_gate[i] || (room_clip_view_cut[i] && eye_distance < 0.0);
		if (view_gate) { aperture_required = true; }
		if (room_clip_view_gate[i] && eye_distance >= 0.0) { aperture_visible = true; continue; }
		float distance = dot(vec4(portal_world_position, 1.0), plane); float denominator = eye_distance - distance;
		if (abs(denominator) < 0.000001) { continue; }
		float fraction = eye_distance / denominator;
		if (fraction < 0.0 || fraction > 1.0) { continue; }
		vec3 crossing = mix(eye, portal_world_position, fraction); float lateral = dot(crossing.xz, vec2(-plane.z, plane.x)); vec4 bounds = room_clip_bounds[i];
		if (lateral >= bounds.x && lateral <= bounds.y && crossing.y >= bounds.z && crossing.y <= bounds.w) {
			if (view_gate) { aperture_visible = true; } else if (room_clip_view_cut[i]) { discard; }
		}
	}
	if (aperture_required && !aperture_visible) { discard; }
	for (int i = 0; i < room_clip_count; i++) {
		float normal_distance = dot(vec4(portal_world_position, 1.0), room_clip_planes[i]);
		if (room_clip_bounded[i]) {
			float lateral = dot(portal_world_position.xz, vec2(-room_clip_planes[i].z, room_clip_planes[i].x));
			vec4 bounds = room_clip_bounds[i]; vec2 depths = room_clip_depths[i];
			if (lateral < bounds.x || lateral > bounds.y || portal_world_position.y < bounds.z || portal_world_position.y > bounds.w || normal_distance < depths.x || normal_distance > depths.y) { continue; }
		}
		if (normal_distance <= room_clip_limits[i]) { discard; }
	}
	if (room_clip_count == 0 && portal_clip_enabled && dot(vec4(portal_world_position, 1.0), portal_clip_plane) <= 0.0001) { discard; }
	if (portal_floor_clip_count > 0 && abs(normalize(cross(dFdx(portal_world_position), dFdy(portal_world_position))).y) >= 0.65) {
		for (int i = 0; i < portal_floor_clip_count; i++) {
			vec4 plane = portal_floor_clip_planes[i];
			vec4 bounds = portal_floor_clip_bounds[i];
			float lateral = abs(plane.x) > 0.5 ? portal_world_position.z : portal_world_position.x;
			float distance = dot(vec4(portal_world_position, 1.0), plane);
			if (portal_floor_clip_bounded[i] && (distance < portal_floor_clip_depths[i].x || distance > portal_floor_clip_depths[i].y)) { continue; }
			if (dot(vec4(portal_world_position, 1.0), plane) < -0.0001 && lateral >= bounds.x && lateral <= bounds.y && portal_world_position.y >= bounds.z && portal_world_position.y <= bounds.w) { discard; }
		}
	}
	if (!part_visible || (!double_sided && !FRONT_FACING)) { discard; }
	vec2 sample_uv = roof_texture_region.z > 0.0 ? roof_texture_region.xy + fract(portal_world_position.xz) * roof_texture_region.zw : UV;
	vec4 pixel = native_palette_enabled ? texture(native_palette_atlas, vec2(sample_uv.x, (clamp(sample_uv.y, 0.0, 1.0) + native_palette_layer) / float(native_palette_layers))) : texture(albedo_texture, sample_uv);
	ALBEDO = pixel.rgb * native_vertex_rgb / 128.0;
	ALPHA = pixel.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
}
