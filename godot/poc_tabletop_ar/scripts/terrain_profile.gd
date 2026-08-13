class_name TerrainProfile
extends RefCounted

## Territorio de 720 x 400 m presentado a escala 1:400 sobre una mesa AR.
## Costa, relieve y biomas provienen de campos horneados compartidos por CPU
## y GPU; no hay una segunda aproximación analítica de la isla.
const WIDTH_M := 400.0
const LENGTH_M := 720.0
const HALF_WIDTH_M := WIDTH_M * 0.5
const HALF_LENGTH_M := LENGTH_M * 0.5
const TERRAIN_PRESENTATION_SCALE := 1.0 / 400.0
const SEA_LEVEL_M := 0.75

const CHARACTER_PRESENTATION_SCALE := 1.0 / 180.0
const CHARACTER_RELATIVE_SCALE := (
	CHARACTER_PRESENTATION_SCALE / TERRAIN_PRESENTATION_SCALE
)

const WORLD_ROOT := "res://assets/environment/island_biome/world/"
const DATA_MAP_WIDTH := 576
const DATA_MAP_HEIGHT := 1024
const FLOAT32_BYTES_PER_PIXEL := 4
const SDF_PATH := WORLD_ROOT + "island_sdf_f32.bin"
const HEIGHT_PATH := WORLD_ROOT + "island_height_f32.bin"
const SDF_AUTHORING_PATH := WORLD_ROOT + "island_sdf.exr"
const HEIGHT_AUTHORING_PATH := WORLD_ROOT + "island_height.exr"
const DENSITY_PATH := WORLD_ROOT + "island_biome_density.png"
const SPLAT_A_PATH := WORLD_ROOT + "island_splat_a.png"
const SPLAT_B_PATH := WORLD_ROOT + "island_splat_b.png"
const DETAIL_PATH := WORLD_ROOT + "island_detail.png"
const TERRAIN_NORMAL_PATH := WORLD_ROOT + "island_terrain_normal.png"
const TERRAIN_AO_PATH := WORLD_ROOT + "island_terrain_ao.png"

enum DensityChannel {
	CANOPY,
	SHRUBS,
	GROUNDCOVER,
	ROCKS,
}

static var _sdf_image: Image
static var _height_image: Image
static var _density_image: Image
static var _data_textures: Dictionary = {}


static func coast_distance_at(position_xz: Vector2) -> float:
	_ensure_cpu_maps()
	return _sample_channel_bilinear(_sdf_image, position_xz, 0)


static func height_at(position_xz: Vector2) -> float:
	_ensure_cpu_maps()
	return _sample_channel_bilinear(_height_image, position_xz, 0)


static func biome_density_at(position_xz: Vector2, channel: int) -> float:
	_ensure_cpu_maps()
	return clampf(
		_sample_channel_bilinear(_density_image, position_xz, channel),
		0.0,
		1.0
	)


static func normal_at(position_xz: Vector2, sample_step_m := 1.4) -> Vector3:
	var left := height_at(position_xz - Vector2(sample_step_m, 0.0))
	var right := height_at(position_xz + Vector2(sample_step_m, 0.0))
	var near := height_at(position_xz - Vector2(0.0, sample_step_m))
	var far := height_at(position_xz + Vector2(0.0, sample_step_m))
	return Vector3(left - right, sample_step_m * 2.0, near - far).normalized()


static func is_inside(position_xz: Vector2, coast_margin_m := 0.0) -> bool:
	if (
		absf(position_xz.x) > HALF_WIDTH_M
		or absf(position_xz.y) > HALF_LENGTH_M
	):
		return false
	return coast_distance_at(position_xz) >= coast_margin_m


static func clamp_to_map_extents(position_xz: Vector2) -> Vector2:
	return Vector2(
		clampf(position_xz.x, -HALF_WIDTH_M, HALF_WIDTH_M),
		clampf(position_xz.y, -HALF_LENGTH_M, HALF_LENGTH_M)
	)


static func clamp_to_bounds(position_xz: Vector2, margin_m := 0.0) -> Vector2:
	var candidate := clamp_to_map_extents(position_xz)
	var safe_margin := maxf(0.0, margin_m)
	if is_inside(candidate, safe_margin):
		return candidate

	# Un SDF euclídeo permite proyectar puntos fuera de costa en la dirección
	# de su gradiente incluso en bahías y cabos cóncavos.
	for iteration in range(18):
		var distance := coast_distance_at(candidate)
		if distance >= safe_margin:
			return candidate
		var step := 1.25
		var gradient := Vector2(
			coast_distance_at(candidate + Vector2(step, 0.0))
				- coast_distance_at(candidate - Vector2(step, 0.0)),
			coast_distance_at(candidate + Vector2(0.0, step))
				- coast_distance_at(candidate - Vector2(0.0, step))
		)
		if gradient.length_squared() < 0.000001:
			break
		candidate += gradient.normalized() * (safe_margin - distance + 0.35)
		candidate = clamp_to_map_extents(candidate)

	# Respaldo determinista para un punto degenerado del gradiente.
	var inside := Vector2.ZERO
	var outside := candidate
	for iteration in range(26):
		var midpoint := (inside + outside) * 0.5
		if is_inside(midpoint, safe_margin):
			inside = midpoint
		else:
			outside = midpoint
	return inside


static func data_texture(path: String) -> Texture2D:
	if _data_textures.has(path):
		return _data_textures[path]
	var texture: Texture2D
	if path.get_extension().to_lower() == "bin":
		var image := data_image(path)
		if image.is_empty():
			return null
		texture = ImageTexture.create_from_image(image)
	else:
		texture = ResourceLoader.load(path, "Texture2D") as Texture2D
		if texture == null:
			push_error("No se pudo cargar la textura de datos: %s" % path)
			return null
	_data_textures[path] = texture
	return texture


static func data_image(path: String) -> Image:
	if path.get_extension().to_lower() == "bin":
		return _load_float32_map(path)
	var texture := ResourceLoader.load(path, "Texture2D") as Texture2D
	if texture == null:
		push_error("No se pudo cargar el mapa importado: %s" % path)
		return Image.new()
	var image := texture.get_image()
	if image == null or image.is_empty():
		push_error("El mapa importado no contiene una imagen: %s" % path)
		return Image.new()
	return image


static func simulation_to_physical_meters(value_m: float) -> float:
	return value_m * TERRAIN_PRESENTATION_SCALE


static func physical_to_simulation_meters(value_m: float) -> float:
	return value_m / TERRAIN_PRESENTATION_SCALE


static func _ensure_cpu_maps() -> void:
	if _sdf_image != null and _height_image != null and _density_image != null:
		return
	_sdf_image = _load_required_image(SDF_PATH)
	_height_image = _load_required_image(HEIGHT_PATH)
	_density_image = _load_required_image(DENSITY_PATH)


static func _load_required_image(path: String) -> Image:
	var image := data_image(path)
	if image.is_empty():
		push_error("Falta mapa horneado obligatorio: %s" % path)
	return image


static func _load_float32_map(path: String) -> Image:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error(
			"No se pudo abrir el mapa float32 %s: %s"
			% [path, error_string(FileAccess.get_open_error())]
		)
		return Image.new()
	var expected_size := (
		DATA_MAP_WIDTH
		* DATA_MAP_HEIGHT
		* FLOAT32_BYTES_PER_PIXEL
	)
	var bytes := file.get_buffer(file.get_length())
	if bytes.size() != expected_size:
		push_error(
			"Mapa float32 inválido %s: %d bytes; se esperaban %d"
			% [path, bytes.size(), expected_size]
		)
		return Image.new()
	return Image.create_from_data(
		DATA_MAP_WIDTH,
		DATA_MAP_HEIGHT,
		false,
		Image.FORMAT_RF,
		bytes
	)


static func _sample_channel_bilinear(
	image: Image,
	position_xz: Vector2,
	channel: int,
) -> float:
	if image == null or image.is_empty():
		return 0.0
	var pixel_x := clampf(
		(position_xz.x / WIDTH_M + 0.5) * float(image.get_width() - 1),
		0.0,
		float(image.get_width() - 1)
	)
	var pixel_y := clampf(
		(position_xz.y / LENGTH_M + 0.5) * float(image.get_height() - 1),
		0.0,
		float(image.get_height() - 1)
	)
	var x0 := floori(pixel_x)
	var y0 := floori(pixel_y)
	var x1 := mini(x0 + 1, image.get_width() - 1)
	var y1 := mini(y0 + 1, image.get_height() - 1)
	var tx := pixel_x - float(x0)
	var ty := pixel_y - float(y0)
	var top := lerpf(
		_channel_value(image.get_pixel(x0, y0), channel),
		_channel_value(image.get_pixel(x1, y0), channel),
		tx
	)
	var bottom := lerpf(
		_channel_value(image.get_pixel(x0, y1), channel),
		_channel_value(image.get_pixel(x1, y1), channel),
		tx
	)
	return lerpf(top, bottom, ty)


static func _channel_value(color: Color, channel: int) -> float:
	match channel:
		1:
			return color.g
		2:
			return color.b
		3:
			return color.a
		_:
			return color.r
