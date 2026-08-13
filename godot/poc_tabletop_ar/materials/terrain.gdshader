shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

// Orden exacto del generador y de TerrainLayerLibrary:
// 0 wet_sand  1 dry_sand  2 soil  3 grass_green
// 4 grass_dry 5 rock      6 litter 7 pebbles
uniform sampler2DArray layer_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray layer_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
// R = altura para height-blend, G = roughness, B = AO del material.
uniform sampler2DArray layer_orm : filter_linear_mipmap_anisotropic, repeat_enable;

uniform sampler2D splat_a : filter_linear, repeat_disable;
uniform sampler2D splat_b : filter_linear, repeat_disable;
uniform sampler2D detail_map : filter_linear, repeat_disable;
uniform sampler2D island_sdf : filter_linear, repeat_disable;
uniform sampler2D terrain_normal : filter_linear, repeat_disable;
uniform sampler2D terrain_ao : filter_linear, repeat_disable;
uniform sampler2D macro_noise : filter_linear_mipmap, repeat_enable;
uniform sampler2D detail_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;

uniform float sea_level_m = 0.75;
// Metros de simulación por repetición; dos vec4 son más portables en GLES3
// que un array uniforme indexado dinámicamente.
uniform vec4 tile_m_a = vec4(2.4, 2.6, 3.1, 1.7);
uniform vec4 tile_m_b = vec4(1.9, 4.2, 2.2, 1.4);
uniform float height_blend_sharpness : hint_range(0.02, 0.6) = 0.18;
uniform float macro_scale_m = 46.0;
uniform float macro_strength : hint_range(0.0, 1.0) = 0.42;
uniform float detail_scale_m = 0.55;
uniform float detail_strength : hint_range(0.0, 2.0) = 0.75;
uniform float terrain_normal_scale : hint_range(0.0, 3.0) = 1.0;
uniform float ao_light_affect : hint_range(0.0, 1.0) = 0.60;
uniform float wet_band_m : hint_range(0.05, 3.0) = 0.85;
uniform float triplanar_start_deg : hint_range(0.0, 90.0) = 26.0;
uniform float triplanar_full_deg : hint_range(0.0, 90.0) = 44.0;

uniform bool grid_enabled = false;
uniform vec3 grid_color : source_color = vec3(0.08, 0.12, 0.09);
uniform float grid_strength : hint_range(0.0, 1.0) = 0.35;

varying float elevation_m;
varying vec3 terrain_position_m;
varying vec3 local_x_view;
varying vec3 local_y_view;
varying vec3 local_z_view;


float layer_tile_m(int layer_index) {
	if (layer_index == 0) { return tile_m_a.x; }
	if (layer_index == 1) { return tile_m_a.y; }
	if (layer_index == 2) { return tile_m_a.z; }
	if (layer_index == 3) { return tile_m_a.w; }
	if (layer_index == 4) { return tile_m_b.x; }
	if (layer_index == 5) { return tile_m_b.y; }
	if (layer_index == 6) { return tile_m_b.z; }
	return tile_m_b.w;
}


vec4 sample_broken(
	sampler2DArray texture_array,
	vec2 uv_m,
	float layer_index,
	float tile_m,
	float macro_value
) {
	vec4 near_scale = texture(texture_array, vec3(uv_m / tile_m, layer_index));
	vec4 far_scale = texture(
		texture_array,
		vec3(uv_m / (tile_m * 3.17) + vec2(0.37, 0.61), layer_index)
	);
	return mix(near_scale, far_scale, macro_value * 0.42);
}


void vertex() {
	// VERTEX conserva metros de simulación aunque el padre presente todo a
	// 1:400; MODEL_MATRIX no sirve para tilear en este proyecto.
	elevation_m = VERTEX.y;
	terrain_position_m = VERTEX;
	local_x_view = normalize((MODELVIEW_MATRIX * vec4(1.0, 0.0, 0.0, 0.0)).xyz);
	local_y_view = normalize((MODELVIEW_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
	local_z_view = normalize((MODELVIEW_MATRIX * vec4(0.0, 0.0, 1.0, 0.0)).xyz);
}


void fragment() {
	vec2 map_uv = UV;
	vec4 weights_a = texture(splat_a, map_uv);
	vec4 weights_b = texture(splat_b, map_uv);
	float weight[8];
	weight[0] = weights_a.r;
	weight[1] = weights_a.g;
	weight[2] = weights_a.b;
	weight[3] = weights_a.a;
	weight[4] = weights_b.r;
	weight[5] = weights_b.g;
	weight[6] = weights_b.b;
	weight[7] = weights_b.a;

	float macro_value = texture(
		macro_noise,
		terrain_position_m.xz / macro_scale_m
	).r;
	vec3 encoded_macro_normal = texture(terrain_normal, map_uv).rgb * 2.0 - 1.0;
	// El bake guarda X, Z y up. El signo de Z compensa el eje vertical de imagen.
	vec3 macro_normal_local = normalize(vec3(
		encoded_macro_normal.r * terrain_normal_scale,
		encoded_macro_normal.b,
		-encoded_macro_normal.g * terrain_normal_scale
	));

	float slope_cos = clamp(macro_normal_local.y, 0.0, 1.0);
	float slope_deg = degrees(acos(slope_cos));
	float triplanar = smoothstep(
		triplanar_start_deg,
		triplanar_full_deg,
		slope_deg
	);
	vec2 side_uv = mix(
		terrain_position_m.zy,
		terrain_position_m.xy,
		step(abs(macro_normal_local.z), abs(macro_normal_local.x))
	);
	vec2 layer_uv_m = mix(terrain_position_m.xz, side_uv, triplanar);

	// Primera pasada: solo las capas que sobrevivieron al splat endurecido.
	float layer_height[8];
	float highest = -1.0;
	for (int layer_index = 0; layer_index < 8; layer_index++) {
		layer_height[layer_index] = -1.0;
		if (weight[layer_index] < 0.004) {
			continue;
		}
		float tile_m = layer_tile_m(layer_index);
		float sampled_height = texture(
			layer_orm,
			vec3(layer_uv_m / tile_m, float(layer_index))
		).r;
		layer_height[layer_index] = sampled_height + weight[layer_index];
		highest = max(highest, layer_height[layer_index]);
	}

	vec3 albedo = vec3(0.0);
	vec3 normal_sum = vec3(0.0);
	float roughness = 0.0;
	float material_ao = 0.0;
	float total = 0.0;
	for (int layer_index = 0; layer_index < 8; layer_index++) {
		if (
			layer_height[layer_index]
			< highest - height_blend_sharpness
		) {
			continue;
		}
		float blend_weight = max(
			layer_height[layer_index] - (highest - height_blend_sharpness),
			0.0
		);
		float tile_m = layer_tile_m(layer_index);
		vec4 base = sample_broken(
			layer_albedo,
			layer_uv_m,
			float(layer_index),
			tile_m,
			macro_value
		);
		vec3 sampled_normal = sample_broken(
			layer_normal,
			layer_uv_m,
			float(layer_index),
			tile_m,
			macro_value
		).rgb * 2.0 - 1.0;
		vec3 orm = sample_broken(
			layer_orm,
			layer_uv_m,
			float(layer_index),
			tile_m,
			macro_value
		).rgb;
		albedo += base.rgb * blend_weight;
		normal_sum += sampled_normal * blend_weight;
		roughness += orm.g * blend_weight;
		material_ao += orm.b * blend_weight;
		total += blend_weight;
	}
	total = max(total, 0.0001);
	albedo /= total;
	roughness /= total;
	material_ao /= total;
	vec3 layer_micro_normal = normalize(normal_sum / total);

	// Dos escalas y dos campos independientes rompen el aspecto de baldosa.
	albedo *= mix(
		1.0 - macro_strength * 0.5,
		1.0 + macro_strength * 0.5,
		macro_value
	);
	albedo *= mix(0.94, 1.06, texture(detail_map, map_uv).r);
	vec3 detail_micro_normal = texture(
		detail_normal,
		terrain_position_m.xz / detail_scale_m
	).rgb * 2.0 - 1.0;
	detail_micro_normal.xy *= detail_strength;
	vec3 micro_normal = normalize(vec3(
		layer_micro_normal.xy + detail_micro_normal.xy,
		layer_micro_normal.z * detail_micro_normal.z
	));

	// TBN alrededor de la normal topográfica de alta resolución. Así no se suma
	// dos veces la pendiente ya presente en la malla.
	vec3 tangent_local = normalize(vec3(
		max(macro_normal_local.y, 0.001),
		-macro_normal_local.x,
		0.0
	));
	vec3 bitangent_local = normalize(cross(tangent_local, macro_normal_local));
	vec3 final_normal_local = normalize(
		tangent_local * micro_normal.x
		+ bitangent_local * micro_normal.y
		+ macro_normal_local * micro_normal.z
	);

	float wetness = 1.0 - smoothstep(
		sea_level_m - 0.15,
		sea_level_m + wet_band_m,
		elevation_m
	);
	wetness *= clamp(weight[0] + weight[1] + weight[7], 0.0, 1.0);
	albedo = mix(albedo, albedo * 0.52, wetness);
	roughness = mix(roughness, 0.10, wetness);

	// Conserva el fundido submarino del mapa anterior: el terreno de 400x720 m
	// desaparece en el plano oceánico extendido sin revelar un rectángulo.
	float coast_distance_m = texture(island_sdf, map_uv).r;
	float land_mask = smoothstep(-0.65, 0.65, coast_distance_m);
	float seabed_depth = smoothstep(0.0, 105.0, -coast_distance_m);
	vec2 edge_distance_m = min(map_uv, vec2(1.0) - map_uv) * vec2(400.0, 720.0);
	float outer_deepening = 1.0 - smoothstep(
		0.0,
		72.0,
		min(edge_distance_m.x, edge_distance_m.y)
	);
	seabed_depth = max(seabed_depth, outer_deepening);
	vec3 seabed_color = mix(
		albedo * vec3(0.34, 0.45, 0.43),
		vec3(0.018, 0.085, 0.105),
		seabed_depth
	);
	albedo = mix(seabed_color, albedo, land_mask);
	roughness = mix(0.93, roughness, land_mask);

	vec2 cells = map_uv * vec2(40.0, 72.0);
	vec2 edge_distance = min(fract(cells), 1.0 - fract(cells));
	float grid = 1.0 - smoothstep(
		0.0,
		0.075,
		min(edge_distance.x, edge_distance.y)
	);
	float contour_distance = min(
		fract(elevation_m / 10.0),
		1.0 - fract(elevation_m / 10.0)
	);
	float contour = 1.0 - smoothstep(0.0, 0.055, contour_distance);
	float lines = grid_enabled ? max(grid, contour * 0.65) : 0.0;

	ALBEDO = mix(albedo, grid_color, lines * grid_strength);
	NORMAL = normalize(
		local_x_view * final_normal_local.x
		+ local_y_view * final_normal_local.y
		+ local_z_view * final_normal_local.z
	);
	float baked_ao = texture(terrain_ao, map_uv).r;
	AO = mix(
		1.0,
		clamp(baked_ao * material_ao, 0.0, 1.0),
		land_mask * 0.78
	);
	AO_LIGHT_AFFECT = ao_light_affect;
	ROUGHNESS = clamp(roughness, 0.04, 1.0);
	SPECULAR = mix(0.50, 0.62, wetness * land_mask);
}
