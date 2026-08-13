class_name RuntimeProfile
extends RefCounted

## Perfil de calidad de la vista Web. La build nativa conserva la densidad y
## geometría originales; el navegador recibe una versión más liviana para
## acelerar la carga y mantener una tasa de cuadros estable.
const WEB_BIOME_DENSITY_SCALE := 0.28
const WEB_OCEAN_SUBDIVISIONS := Vector2i(80, 90)
const NATIVE_OCEAN_SUBDIVISIONS := Vector2i(200, 225)


static func is_web_preview() -> bool:
	return OS.has_feature("web") or OS.has_feature("web_preview")


static func biome_density_scale() -> float:
	return WEB_BIOME_DENSITY_SCALE if is_web_preview() else 1.0


static func ocean_subdivisions() -> Vector2i:
	return (
		WEB_OCEAN_SUBDIVISIONS
		if is_web_preview()
		else NATIVE_OCEAN_SUBDIVISIONS
	)
