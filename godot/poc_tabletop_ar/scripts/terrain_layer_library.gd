class_name TerrainLayerLibrary
extends RefCounted

## Construye los tres Texture2DArray del terreno desde PNG independientes.
## Mantener los PNG como fuentes hace que cada set de producción pueda
## reemplazarse sin regenerar escenas ni tocar el shader.

const TEXTURE_ROOT := "res://assets/environment/island_biome/textures/"
const LAYER_ROOT := TEXTURE_ROOT + "layers/"
const LAYER_NAMES: Array[String] = [
	"wet_sand",
	"dry_sand",
	"soil",
	"grass_green",
	"grass_dry",
	"rock",
	"litter",
	"pebbles",
]
const MAP_NAMES: Array[String] = ["albedo", "normal", "orm"]

static var _layer_arrays: Dictionary = {}
static var _mipped_textures: Dictionary = {}


static func layer_path(layer_index: int, map_name: String) -> String:
	if layer_index < 0 or layer_index >= LAYER_NAMES.size():
		return ""
	if not MAP_NAMES.has(map_name):
		return ""
	return LAYER_ROOT + "%02d_%s_%s.png" % [
		layer_index,
		LAYER_NAMES[layer_index],
		map_name,
	]


static func layer_texture(layer_index: int, map_name: String) -> Texture2D:
	var path := layer_path(layer_index, map_name)
	if path.is_empty():
		push_error("Capa de terreno inválida: %d/%s" % [layer_index, map_name])
		return null
	if _mipped_textures.has(path):
		return _mipped_textures[path]
	var image := _load_mipped_image(path)
	if image == null:
		return null
	var texture := ImageTexture.create_from_image(image)
	texture.resource_name = "%s_%s_1k" % [LAYER_NAMES[layer_index], map_name]
	_mipped_textures[path] = texture
	return texture


static func _load_mipped_image(path: String) -> Image:
	var source := ResourceLoader.load(path, "Texture2D") as Texture2D
	if source == null:
		push_error("No se pudo cargar la capa de terreno: %s" % path)
		return null
	var image := source.get_image()
	if image == null or image.is_empty():
		push_error("La capa no contiene imagen: %s" % path)
		return null
	if image.has_mipmaps():
		image.clear_mipmaps()
	var mip_error := image.generate_mipmaps()
	if mip_error != OK:
		push_error("No se pudieron crear mipmaps para %s: %s" % [
			path,
			error_string(mip_error),
		])
		return null
	return image


static func layer_array(map_name: String) -> Texture2DArray:
	if not MAP_NAMES.has(map_name):
		push_error("Array de terreno desconocido: %s" % map_name)
		return null
	if _layer_arrays.has(map_name):
		return _layer_arrays[map_name]
	var images: Array[Image] = []
	for layer_index in range(LAYER_NAMES.size()):
		var image := _load_mipped_image(layer_path(layer_index, map_name))
		if image == null:
			return null
		images.append(image)
	var texture_array := Texture2DArray.new()
	var create_error := texture_array.create_from_images(images)
	if create_error != OK:
		push_error("No se pudo crear Texture2DArray %s: %s" % [
			map_name,
			error_string(create_error),
		])
		return null
	texture_array.resource_name = "island_layers_%s_1k" % map_name
	texture_array.set_meta("layer_order", LAYER_NAMES)
	texture_array.set_meta("orm_channels", "R=height G=roughness B=AO")
	_layer_arrays[map_name] = texture_array
	return texture_array
