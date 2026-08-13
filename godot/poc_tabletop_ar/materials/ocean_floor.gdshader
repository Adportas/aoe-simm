shader_type spatial;
render_mode cull_disabled, diffuse_burley;

uniform sampler2D sand_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;

varying vec2 floor_position_m;


void vertex() {
	floor_position_m = VERTEX.xz;
}


void fragment() {
	// Coincide exactamente con el valor profundo del shader del heightmap.
	ALBEDO = vec3(0.018, 0.085, 0.105);
	NORMAL_MAP = texture(sand_normal, floor_position_m / 12.0 * 0.91).rgb;
	NORMAL_MAP_DEPTH = 0.22;
	ROUGHNESS = 0.93;
	SPECULAR = 0.28;
}
