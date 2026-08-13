shader_type canvas_item;

uniform sampler2D luma_texture : filter_linear, repeat_disable;
uniform sampler2D chroma_texture : filter_linear, repeat_disable;
uniform vec2 uv_column_0 = vec2(1.0, 0.0);
uniform vec2 uv_column_1 = vec2(0.0, 1.0);
uniform vec2 uv_origin = vec2(0.0, 0.0);
uniform vec2 valid_uv_scale = vec2(1.0, 1.0);

void fragment() {
	vec2 camera_uv = uv_column_0 * UV.x + uv_column_1 * UV.y + uv_origin;
	camera_uv *= valid_uv_scale;
	bool outside = camera_uv.x < 0.0 || camera_uv.y < 0.0 || camera_uv.x > valid_uv_scale.x || camera_uv.y > valid_uv_scale.y;
	if (outside) {
		COLOR = vec4(0.0, 0.0, 0.0, 1.0);
	} else {
		float y = texture(luma_texture, camera_uv).r;
		vec2 cbcr = texture(chroma_texture, camera_uv).rg - vec2(0.5);
		vec3 rgb = vec3(
			y + 1.402 * cbcr.y,
			y - 0.344136 * cbcr.x - 0.714136 * cbcr.y,
			y + 1.772 * cbcr.x
		);
		COLOR = vec4(clamp(rgb, vec3(0.0), vec3(1.0)), 1.0);
	}
}
