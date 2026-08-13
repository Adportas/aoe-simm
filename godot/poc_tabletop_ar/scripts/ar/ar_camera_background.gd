class_name ArCameraBackground
extends ColorRect

## Primera implementación deliberadamente simple: copia los dos planos Y/CbCr
## de ARFrame a texturas de Godot. El diagnóstico mide su costo para decidir si
## el siguiente paso necesita un puente Metal de copia cero.

@export var maximum_updates_per_second := 20.0

var last_copy_time_ms := 0.0
var source_resolution := Vector2.ZERO
var _last_update_ms := -100000
var _luma_texture: ImageTexture
var _chroma_texture: ImageTexture
var _shader_material: ShaderMaterial


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_shader_material = ShaderMaterial.new()
	_shader_material.shader = load("res://materials/ar_camera_ycbcr.gdshader")
	material = _shader_material
	visible = false


func update_from_frame(frame: Variant, interface_orientation: int) -> void:
	if frame == null:
		return
	var now_ms := Time.get_ticks_msec()
	var minimum_interval := int(1000.0 / maximum_updates_per_second)
	if now_ms - _last_update_ms < minimum_interval:
		return
	_last_update_ms = now_ms

	if int(frame.call("get_captured_image_plane_count")) < 2:
		return
	var started_us := Time.get_ticks_usec()
	var luma_size: Vector2 = frame.call("get_captured_image_plane_size", 0)
	var chroma_size: Vector2 = frame.call("get_captured_image_plane_size", 1)
	var luma_stride := int(frame.call("get_captured_image_plane_stride", 0))
	var chroma_stride := int(frame.call("get_captured_image_plane_stride", 1))
	var luma_data: PackedByteArray = frame.call("get_captured_image_plane_data", 0)
	var chroma_data: PackedByteArray = frame.call("get_captured_image_plane_data", 1)
	if luma_size.x <= 0.0 or chroma_size.x <= 0.0:
		return
	if luma_data.is_empty() or chroma_data.is_empty():
		return

	_luma_texture = _update_texture(
		_luma_texture, luma_data, luma_stride, int(luma_size.y), 1, Image.FORMAT_L8
	)
	_chroma_texture = _update_texture(
		_chroma_texture, chroma_data, chroma_stride, int(chroma_size.y), 2, Image.FORMAT_RG8
	)
	_shader_material.set_shader_parameter("luma_texture", _luma_texture)
	_shader_material.set_shader_parameter("chroma_texture", _chroma_texture)
	_shader_material.set_shader_parameter(
		"valid_uv_scale",
		Vector2(luma_size.x / float(luma_stride), 1.0)
	)

	var viewport_size := get_viewport_rect().size
	var display_values: PackedFloat32Array = frame.call(
		"display_transform", interface_orientation, viewport_size
	)
	if display_values.size() == 6:
		var image_to_display := Transform2D(
			Vector2(display_values[0], display_values[1]),
			Vector2(display_values[2], display_values[3]),
			Vector2(display_values[4], display_values[5])
		)
		var display_to_image := image_to_display.affine_inverse()
		_shader_material.set_shader_parameter("uv_column_0", display_to_image.x)
		_shader_material.set_shader_parameter("uv_column_1", display_to_image.y)
		_shader_material.set_shader_parameter("uv_origin", display_to_image.origin)

	source_resolution = frame.get("captured_image_size")
	last_copy_time_ms = float(Time.get_ticks_usec() - started_us) / 1000.0
	visible = true


func _update_texture(
	existing: ImageTexture,
	data: PackedByteArray,
	stride_bytes: int,
	height: int,
	bytes_per_pixel: int,
	format: Image.Format
) -> ImageTexture:
	var texture_width := stride_bytes / bytes_per_pixel
	var expected_bytes := stride_bytes * height
	if data.size() != expected_bytes:
		return existing
	var image := Image.create_from_data(texture_width, height, false, format, data)
	if existing == null or existing.get_width() != texture_width or existing.get_height() != height:
		return ImageTexture.create_from_image(image)
	existing.update(image)
	return existing
