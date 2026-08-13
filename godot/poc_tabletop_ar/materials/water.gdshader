shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, diffuse_burley;

uniform sampler2D island_sdf : filter_linear, repeat_disable;
uniform sampler2D island_height : filter_linear, repeat_disable;
uniform sampler2D detail_map : filter_linear, repeat_disable;
uniform sampler2D screen_texture : hint_screen_texture, filter_linear_mipmap;
uniform sampler2D depth_texture : hint_depth_texture, filter_nearest;

uniform vec3 deep_color : source_color = vec3(0.008, 0.115, 0.185);
uniform vec3 shallow_color : source_color = vec3(0.055, 0.47, 0.50);
uniform vec3 foam_color : source_color = vec3(0.86, 0.91, 0.81);
uniform vec3 absorption = vec3(0.32, 0.095, 0.050);
uniform float sea_level_m = 0.75;
uniform float presentation_scale = 0.0025;
uniform float foam_depth_m : hint_range(0.2, 4.0) = 1.15;
uniform float foam_max_opacity : hint_range(0.0, 1.0) = 0.70;
uniform float shore_softness_m : hint_range(0.02, 1.5) = 0.30;
uniform float refraction_strength : hint_range(0.0, 0.02) = 0.006;

varying vec2 map_position_m;
varying vec2 map_uv;
varying float vertex_wave;


float wave_phase(vec2 position_m, vec2 direction, float wavelength_m, float speed) {
	return dot(position_m, normalize(direction)) * (6.2831853 / wavelength_m) + TIME * speed;
}


float scene_depth_at(vec2 screen_uv, mat4 inverse_projection) {
	float raw_depth = texture(depth_texture, screen_uv).r;
	// El proyecto usa GL Compatibility: su NDC Z ocupa [-1, 1].
	vec3 ndc = vec3(screen_uv * 2.0 - 1.0, raw_depth * 2.0 - 1.0);
	vec4 view_position = inverse_projection * vec4(ndc, 1.0);
	return -(view_position.z / view_position.w);
}


void vertex() {
	map_position_m = VERTEX.xz;
	map_uv = map_position_m / vec2(400.0, 720.0) + vec2(0.5);
	float coast = textureLod(island_sdf, map_uv, 0.0).r;
	float ocean_mask = 1.0 - smoothstep(-0.5, 2.5, coast);
	float phase_a = wave_phase(map_position_m, vec2(1.0, 0.34), 19.0, 1.15);
	float phase_b = wave_phase(map_position_m, vec2(-0.28, 1.0), 31.0, 0.74);
	float phase_c = wave_phase(map_position_m, vec2(0.71, 0.70), 8.5, 1.78);
	vec2 dir_a = normalize(vec2(1.0, 0.34));
	vec2 dir_b = normalize(vec2(-0.28, 1.0));
	VERTEX.xz += (dir_a * cos(phase_a) * 0.18 + dir_b * cos(phase_b) * 0.11) * ocean_mask;
	vertex_wave = (sin(phase_a) * 0.34 + sin(phase_b) * 0.22 + sin(phase_c) * 0.09) * ocean_mask;
	VERTEX.y += vertex_wave;
}


void fragment() {
	float coast = texture(island_sdf, map_uv).r;
	float seabed_height = texture(island_height, map_uv).r;
	float water_mask = 1.0 - smoothstep(-0.35, 1.35, coast);
	float baked_depth_m = max(sea_level_m + vertex_wave - seabed_height, 0.0);
	float surface_depth = -VERTEX.z;
	float scene_depth = scene_depth_at(SCREEN_UV, INV_PROJECTION_MATRIX);
	float screen_thickness_m = max(
		scene_depth - surface_depth,
		0.0
	) / max(presentation_scale, 0.000001);

	// La batimetría da una profundidad estable en metros de simulación. La
	// profundidad de pantalla sólo puede reducirla: así rocas emergentes
	// generan contacto sin que el fondo o el cielo falseen el océano profundo.
	float optical_depth_m = min(baked_depth_m, screen_thickness_m);

	float phase_a = wave_phase(map_position_m, vec2(1.0, 0.34), 19.0, 1.15);
	float phase_b = wave_phase(map_position_m, vec2(-0.28, 1.0), 31.0, 0.74);
	float phase_c = wave_phase(map_position_m, vec2(0.71, 0.70), 8.5, 1.78);
	vec2 wave_normal = vec2(
		cos(phase_a) * 0.105 + cos(phase_c) * 0.045,
		cos(phase_b) * 0.085 - cos(phase_c) * 0.042
	);
	NORMAL_MAP = vec3(0.5 + wave_normal.x, 0.5 + wave_normal.y, 1.0);
	NORMAL_MAP_DEPTH = 0.58;

	float distortion = clamp(optical_depth_m / 18.0, 0.0, 1.0);
	vec2 refracted_uv = SCREEN_UV + wave_normal * mix(
		0.0015,
		refraction_strength,
		distortion
	);
	float refracted_scene_depth = scene_depth_at(
		refracted_uv,
		INV_PROJECTION_MATRIX
	);
	if (refracted_scene_depth + 0.00005 < surface_depth) {
		refracted_uv = SCREEN_UV;
	}
	vec3 refracted_scene = textureLod(screen_texture, refracted_uv, distortion * 1.6).rgb;
	vec3 transmittance = exp(-absorption * optical_depth_m);
	vec3 volume_color = mix(shallow_color, deep_color, smoothstep(1.5, 14.0, optical_depth_m));
	vec3 water_color = refracted_scene * transmittance + volume_color * (vec3(1.0) - transmittance);
	water_color = mix(water_color, volume_color, 0.28 + distortion * 0.22);

	// La rompiente depende de la columna de agua, no de una franja fija del
	// SDF. Dos octavas periódicas rompen el borde y se desplazan por separado.
	float depth_band = 1.0 - smoothstep(0.0, foam_depth_m, optical_depth_m);
	float foam_noise_a = texture(
		detail_map,
		fract(map_uv * 3.70 + vec2(TIME * 0.014, TIME * -0.011))
	).r;
	float foam_noise_b = texture(
		detail_map,
		fract(map_uv * 1.85 + vec2(TIME * -0.007, TIME * 0.009))
	).g;
	float foam_edge = foam_noise_a * 0.62 + foam_noise_b * 0.38;
	float shore_foam = smoothstep(
		0.42,
		0.88,
		depth_band * (0.68 + foam_edge * 0.64)
	);
	float crest = smoothstep(
		0.62,
		0.96,
		sin(phase_a) * 0.53 + sin(phase_c) * 0.47
	);
	float foam = clamp(shore_foam + crest * depth_band * 0.30, 0.0, 1.0);

	float caustic_lines = abs(sin(phase_a * 1.9) + sin(phase_b * 2.2));
	float caustics = smoothstep(1.22, 1.88, caustic_lines) * (1.0 - smoothstep(1.5, 8.5, optical_depth_m));
	water_color += vec3(0.10, 0.19, 0.15) * caustics * 0.42;
	water_color = mix(water_color, foam_color, foam * 0.82);

	float fresnel = pow(1.0 - clamp(dot(normalize(NORMAL), normalize(VIEW)), 0.0, 1.0), 4.0);
	ALBEDO = water_color;
	EMISSION = foam_color * foam * 0.14 + vec3(0.03, 0.11, 0.10) * caustics;
	ROUGHNESS = mix(0.075, 0.28, foam);
	SPECULAR = 0.86;
	float edge_alpha = smoothstep(0.0, shore_softness_m, optical_depth_m);
	float water_opacity = 0.24 + (1.0 - transmittance.g) * 0.48 + fresnel * 0.18;
	ALPHA = water_mask * edge_alpha * clamp(
		max(water_opacity, foam * foam_max_opacity),
		0.0,
		0.88
	);
}
