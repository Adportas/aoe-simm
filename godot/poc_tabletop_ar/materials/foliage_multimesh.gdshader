shader_type spatial;
render_mode blend_mix, depth_prepass_alpha, cull_disabled, diffuse_burley, specular_schlick_ggx;

// Frondas y arbustos usan cards con alfa; tronco, frutos y la vegetación sólida
// comparten el shader sin pagar esos muestreos.
uniform bool card_mode = false;
uniform vec4 base_color : source_color = vec4(0.16, 0.34, 0.12, 1.0);
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_texture : hint_normal, filter_linear_mipmap_anisotropic;
// R = roughness, G = translucidez de lámina.
uniform sampler2D mask_texture : filter_linear_mipmap_anisotropic;
uniform sampler2D hue_ramp : source_color, filter_linear, repeat_disable;
uniform bool has_normal_texture = false;

uniform float surface_roughness : hint_range(0.0, 1.0) = 0.90;
uniform float alpha_cutoff : hint_range(0.0, 1.0) = 0.42;
uniform float translucency : hint_range(0.0, 1.0) = 0.55;
uniform vec3 translucency_tint : source_color = vec3(0.42, 0.68, 0.22);
uniform float hue_variation : hint_range(0.0, 1.0) = 0.72;

uniform float wind_amplitude_m = 0.16;
uniform float wind_speed = 0.85;
uniform vec2 wind_direction = vec2(0.82, 0.57);
uniform float pivot_height_m = 1.0;
uniform float wind_base_height_m = 0.0;
uniform float wind_response : hint_range(0.0, 1.0) = 1.0;
uniform float foliage_tint_response : hint_range(0.0, 1.0) = 1.0;
uniform float presentation_scale = 0.0025;

varying vec3 instance_tint;
varying float leaf_translucency;


void vertex() {
	// x=fase, y=índice verde->amarillo->pardo, z=flexibilidad, w=edad.
	float phase = INSTANCE_CUSTOM.x * 6.2831853;
	float flexibility = INSTANCE_CUSTOM.z;
	float age = INSTANCE_CUSTOM.w;

	float relative_height = clamp(
		(VERTEX.y - wind_base_height_m)
		/ max(pivot_height_m - wind_base_height_m, 0.05),
		0.0,
		1.0
	);
	// El cubo mantiene fija la base; una máscara lineal dobla la planta como goma.
	float bend = relative_height * relative_height * relative_height;
	float sway = (
		sin(TIME * wind_speed + phase)
		+ sin(TIME * wind_speed * 2.37 + phase * 1.7) * 0.35
	);
	vec3 world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 simulation_position = world_position.xz / max(presentation_scale, 0.00001);
	float gust = 0.65 + 0.35 * sin(
		dot(simulation_position, wind_direction) * 0.012 - TIME * 0.31
	);
	VERTEX.xz += (
		wind_direction
		* sway
		* gust
		* bend
		* flexibility
		* wind_response
		* wind_amplitude_m
	);
	VERTEX.y -= (
		abs(sway)
		* gust
		* bend
		* flexibility
		* wind_response
		* wind_amplitude_m
		* 0.22
	);

	float ramp_coordinate = mix(0.5, INSTANCE_CUSTOM.y, hue_variation);
	instance_tint = texture(hue_ramp, vec2(ramp_coordinate, 0.5)).rgb;
	instance_tint *= mix(1.12, 0.92, age);
	leaf_translucency = mix(1.0, 0.70, age);
}


void fragment() {
	vec4 base = base_color;
	vec2 mask = vec2(surface_roughness, 0.0);
	if (card_mode) {
		base *= texture(albedo_texture, UV);
		mask = texture(mask_texture, UV).rg;
	}

	ALPHA = base.a;
	ALPHA_SCISSOR_THRESHOLD = card_mode ? alpha_cutoff : 0.0;
	ALBEDO = (
		base.rgb
		* mix(vec3(1.0), instance_tint, foliage_tint_response)
		* COLOR.rgb
	);
	ROUGHNESS = clamp(mask.r, 0.18, 1.0);
	SPECULAR = 0.42;

	if (card_mode && has_normal_texture) {
		vec3 normal = texture(normal_texture, UV).rgb * 2.0 - 1.0;
		if (!FRONT_FACING) {
			normal.z = -normal.z;
		}
		NORMAL_MAP = normal * 0.5 + 0.5;
	}
	BACKLIGHT = (
		translucency_tint
		* translucency
		* mask.g
		* leaf_translucency
		* float(card_mode)
	);
}
