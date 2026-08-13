class_name IslandBiomeBuilder
extends RefCounted

const FOLIAGE_SHADER_PATH := "res://materials/foliage_multimesh.gdshader"
const PALM_FROND_ALBEDO_PATH := (
	"res://assets/environment/island_biome/textures/palms/"
	+ "palm_frond_atlas_albedo_v1.png"
)
const PALM_FROND_NORMAL_PATH := (
	"res://assets/environment/island_biome/textures/palms/"
	+ "palm_frond_atlas_normal_v1.png"
)
const PALM_FROND_MASK_PATH := (
	"res://assets/environment/island_biome/textures/palms/"
	+ "palm_frond_atlas_mask_v1.png"
)
const SHRUB_FOLIAGE_ALBEDO_PATH := (
	"res://assets/environment/island_biome/textures/shrubs/"
	+ "shrub_atlas_albedo_v1.png"
)
const SHRUB_FOLIAGE_NORMAL_PATH := (
	"res://assets/environment/island_biome/textures/shrubs/"
	+ "shrub_atlas_normal_v1.png"
)
const SHRUB_FOLIAGE_MASK_PATH := (
	"res://assets/environment/island_biome/textures/shrubs/"
	+ "shrub_atlas_mask_v1.png"
)
const TERRAIN_LAYER_LIBRARY := preload("res://scripts/terrain_layer_library.gd")

## Las densidades son campos continuos (canopy, shrubs, groundcover, rocks).
## Cada familia ejecuta su propio muestreo Poisson para que el orden del array
## no prive de espacio a las familias posteriores.
const ASSET_DEFINITIONS: Array[Dictionary] = [
	{
		"key": "palm_coconut_a", "path": "res://assets/environment/island_biome/palms/palm_small.glb",
		"count": 280, "seed": 1103, "density_channel": 0, "density_power": 0.92,
		"scale_min": 0.88, "scale_max": 1.10, "edge_min": 5.0, "edge_max": 82.0,
		"height_min": 1.0, "height_max": 30.0, "slope_max": 29.0, "spacing": 6.2,
		"route_clearance": 5.5, "normal_alignment": 0.18, "sink": 0.05,
		"casts_shadow": true, "visibility_end": 4.5, "kind": "tree",
	},
	{
		"key": "palm_date", "path": "res://assets/environment/island_biome/palms/palm_medium.glb",
		"count": 360, "seed": 1201, "density_channel": 0, "density_power": 0.84,
		"scale_min": 0.58, "scale_max": 1.36, "edge_min": 12.0, "edge_max": 165.0,
		"height_min": 2.0, "height_max": 42.0, "slope_max": 31.0, "spacing": 7.2,
		"route_clearance": 6.0, "normal_alignment": 0.16, "sink": 0.05,
		"casts_shadow": true, "visibility_end": 4.8, "kind": "tree",
	},
	{
		"key": "palm_coconut", "path": "res://assets/environment/island_biome/palms/palm_tall.glb",
		"count": 240, "seed": 1301, "density_channel": 0, "density_power": 0.96,
		"scale_min": 0.64, "scale_max": 1.31, "edge_min": 4.0, "edge_max": 96.0,
		"height_min": 1.0, "height_max": 31.0, "slope_max": 27.0, "spacing": 8.4,
		"route_clearance": 5.5, "normal_alignment": 0.13, "sink": 0.06,
		"casts_shadow": true, "visibility_end": 5.2, "kind": "tree",
	},
	{
		"key": "broadleaf_round", "path": "res://assets/environment/island_biome/vegetation/shrub_dense.glb",
		"count": 420, "seed": 1511, "density_channel": 0, "density_power": 0.80,
		"scale_min": 2.30, "scale_max": 4.25, "edge_min": 13.0, "edge_max": 205.0,
		"height_min": 2.0, "height_max": 42.0, "slope_max": 32.0, "spacing": 5.2,
		"route_clearance": 5.0, "normal_alignment": 0.18, "sink": 0.04,
		"casts_shadow": true, "visibility_end": 4.6, "kind": "tree",
	},
	{
		"key": "broadleaf_open", "path": "res://assets/environment/island_biome/vegetation/shrub_wild.glb",
		"count": 280, "seed": 1613, "density_channel": 0, "density_power": 0.86,
		"scale_min": 2.05, "scale_max": 3.85, "edge_min": 10.0, "edge_max": 195.0,
		"height_min": 2.0, "height_max": 40.0, "slope_max": 34.0, "spacing": 5.8,
		"route_clearance": 4.7, "normal_alignment": 0.22, "sink": 0.04,
		"casts_shadow": true, "visibility_end": 4.4, "kind": "tree",
	},
	{
		"key": "rock_boulder", "path": "res://assets/environment/island_biome/rocks/rock_boulder.glb",
		"count": 420, "seed": 2101, "density_channel": 3, "density_power": 0.70,
		"scale_min": 0.48, "scale_max": 2.65, "edge_min": 2.0, "edge_max": 260.0,
		"height_min": 1.0, "height_max": 61.0, "slope_max": 57.0, "spacing": 3.0,
		"route_clearance": 3.8, "normal_alignment": 0.78, "sink": 0.24,
		"tilt_max_degrees": 22.0,
		"casts_shadow": true, "visibility_end": 4.2, "kind": "rock",
	},
	{
		"key": "rock_outcrop", "path": "res://assets/environment/island_biome/rocks/rock_outcrop.glb",
		"count": 110, "seed": 2203, "density_channel": 3, "density_power": 0.56,
		"scale_min": 1.70, "scale_max": 5.20, "edge_min": 18.0, "edge_max": 270.0,
		"height_min": 12.0, "height_max": 61.0, "slope_max": 62.0, "spacing": 7.5,
		"route_clearance": 5.0, "normal_alignment": 0.84, "sink": 0.38,
		"tilt_max_degrees": 12.0,
		"casts_shadow": true, "visibility_end": 5.4, "kind": "rock",
	},
	{
		"key": "stone_cluster", "path": "res://assets/environment/island_biome/rocks/stone_cluster.glb",
		"count": 950, "seed": 2309, "density_channel": 3, "density_power": 0.72,
		"scale_min": 0.38, "scale_max": 1.95, "edge_min": 1.5, "edge_max": 275.0,
		"height_min": 0.8, "height_max": 61.0, "slope_max": 58.0, "spacing": 1.65,
		"route_clearance": 2.7, "normal_alignment": 0.86, "sink": 0.18,
		"tilt_max_degrees": 26.0,
		"casts_shadow": true, "visibility_end": 3.4, "kind": "rock",
	},
	{
		"key": "shrub_dense", "path": "res://assets/environment/island_biome/vegetation/shrub_dense.glb",
		"count": 2200, "seed": 3109, "density_channel": 1, "density_power": 0.78,
		"scale_min": 0.42, "scale_max": 1.72, "edge_min": 7.0, "edge_max": 255.0,
		"height_min": 1.0, "height_max": 47.0, "slope_max": 37.0, "spacing": 1.35,
		"route_clearance": 2.2, "normal_alignment": 0.36, "sink": 0.04,
		"casts_shadow": false, "visibility_end": 2.8, "kind": "shrub",
	},
	{
		"key": "shrub_wild", "path": "res://assets/environment/island_biome/vegetation/shrub_wild.glb",
		"count": 1800, "seed": 3203, "density_channel": 1, "density_power": 0.82,
		"scale_min": 0.38, "scale_max": 1.64, "edge_min": 5.0, "edge_max": 255.0,
		"height_min": 1.0, "height_max": 46.0, "slope_max": 39.0, "spacing": 1.45,
		"route_clearance": 2.1, "normal_alignment": 0.42, "sink": 0.04,
		"casts_shadow": false, "visibility_end": 2.7, "kind": "shrub",
	},
	{
		"key": "grass_green", "path": "res://assets/environment/island_biome/vegetation/grass_green.glb",
		"count": 10000, "seed": 4101, "density_channel": 2, "density_power": 0.70,
		"scale_min": 0.28, "scale_max": 1.18, "edge_min": 5.0, "edge_max": 270.0,
		"height_min": 0.8, "height_max": 43.0, "slope_max": 39.0, "spacing": 0.48,
		"route_clearance": 1.35, "normal_alignment": 0.58, "sink": 0.025,
		"casts_shadow": false, "visibility_end": 1.65, "kind": "ground",
	},
	{
		"key": "grass_dry", "path": "res://assets/environment/island_biome/vegetation/grass_dry.glb",
		"count": 8000, "seed": 4201, "density_channel": 2, "density_power": 0.76,
		"scale_min": 0.30, "scale_max": 1.24, "edge_min": 4.0, "edge_max": 275.0,
		"height_min": 0.8, "height_max": 47.0, "slope_max": 41.0, "spacing": 0.52,
		"route_clearance": 1.30, "normal_alignment": 0.62, "sink": 0.025,
		"casts_shadow": false, "visibility_end": 1.55, "kind": "ground",
	},
]

static var _foliage_hue_ramp: GradientTexture1D
static var _foliage_fallback_textures: Dictionary = {}


class SpatialHash:
	var cell_size: float
	var cells: Dictionary = {}
	var maximum_radius := 0.0

	func _init(new_cell_size: float) -> void:
		cell_size = maxf(new_cell_size, 0.20)

	func permits(position: Vector2, radius: float) -> bool:
		var center := _cell_at(position)
		var reach := ceili((radius + maximum_radius) / cell_size) + 1
		for y in range(center.y - reach, center.y + reach + 1):
			for x in range(center.x - reach, center.x + reach + 1):
				var bucket: Array = cells.get(Vector2i(x, y), [])
				for item in bucket:
					var minimum := radius + float(item["radius"])
					if position.distance_squared_to(item["position"]) < minimum * minimum:
						return false
		return true

	func insert(position: Vector2, radius: float) -> void:
		var cell := _cell_at(position)
		var bucket: Array = cells.get(cell, [])
		bucket.append({"position": position, "radius": radius})
		cells[cell] = bucket
		maximum_radius = maxf(maximum_radius, radius)

	func _cell_at(position: Vector2) -> Vector2i:
		return Vector2i(floori(position.x / cell_size), floori(position.y / cell_size))


static func populate(
	parent: Node3D,
	exclusion_route: Array[Vector2] = [],
	density_scale := 1.0,
) -> Dictionary:
	var biome_root := Node3D.new()
	biome_root.name = "IslandBiome_DensityFields"
	parent.add_child(biome_root)
	var counts: Dictionary = {}
	for definition in ASSET_DEFINITIONS:
		var mesh := _load_first_mesh(definition["path"])
		if mesh == null:
			push_error("No se pudo cargar el asset de bioma %s" % definition["path"])
			continue
		if definition["kind"] == "rock":
			mesh = _prepare_rock_mesh(mesh)
		else:
			mesh = _prepare_foliage_mesh(mesh)
		var placements := _generate_placements(
			definition,
			exclusion_route,
			density_scale
		)
		var expected_count := scaled_count(definition, density_scale)
		if placements.size() != expected_count:
			push_warning("Bioma %s: %d/%d instancias" % [
				definition["key"], placements.size(), expected_count,
			])

		var multi_mesh := MultiMesh.new()
		multi_mesh.transform_format = MultiMesh.TRANSFORM_3D
		multi_mesh.use_colors = true
		multi_mesh.use_custom_data = true
		multi_mesh.instance_count = placements.size()
		multi_mesh.mesh = mesh
		multi_mesh.custom_aabb = AABB(Vector3(-205.0, -18.0, -365.0), Vector3(410.0, 92.0, 730.0))
		for index in range(placements.size()):
			var placement: Dictionary = placements[index]
			multi_mesh.set_instance_transform(index, placement["transform"])
			multi_mesh.set_instance_color(index, placement["color"])
			multi_mesh.set_instance_custom_data(index, placement["custom"])

		var instances := MultiMeshInstance3D.new()
		instances.name = definition["key"]
		instances.multimesh = multi_mesh
		instances.cast_shadow = (
			GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			if definition["casts_shadow"]
			else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		)
		instances.visibility_range_end = float(definition["visibility_end"])
		instances.set_meta("asset_path", definition["path"])
		instances.set_meta("organic_seed", definition["seed"])
		instances.set_meta("density_channel", definition["density_channel"])
		instances.set_meta("kind", definition["kind"])
		biome_root.add_child(instances)
		counts[definition["key"]] = placements.size()
	return counts


static func scaled_count(definition: Dictionary, density_scale := 1.0) -> int:
	return maxi(
		1,
		roundi(int(definition["count"]) * clampf(density_scale, 0.01, 1.0))
	)


static func _load_first_mesh(path: String) -> Mesh:
	var packed := load(path) as PackedScene
	if packed == null:
		return null
	var instance := packed.instantiate()
	var meshes := instance.find_children("*", "MeshInstance3D", true, false)
	if meshes.size() != 1:
		push_warning("%s expone %d mallas; se esperaba una" % [path, meshes.size()])
	if meshes.is_empty():
		instance.free()
		return null
	var mesh := (meshes[0] as MeshInstance3D).mesh
	instance.free()
	return mesh


static func _prepare_rock_mesh(source: Mesh) -> Mesh:
	var mesh := source.duplicate(true) as ArrayMesh
	if mesh == null:
		return source
	var rock_albedo := TERRAIN_LAYER_LIBRARY.layer_texture(5, "albedo")
	var rock_normal := TERRAIN_LAYER_LIBRARY.layer_texture(5, "normal")
	var rock_orm := TERRAIN_LAYER_LIBRARY.layer_texture(5, "orm")
	if rock_albedo == null or rock_normal == null or rock_orm == null:
		push_error("El set PBR triplanar de roca está incompleto")
		return source
	for surface_index in range(mesh.get_surface_count()):
		var original := source.surface_get_material(surface_index)
		var original_name := (
			original.resource_name.to_lower()
			if original != null
			else ""
		)
		var surface_tint := Color(0.94, 0.92, 0.86, 1.0)
		if "dark" in original_name:
			surface_tint = Color(0.70, 0.72, 0.70, 1.0)
		elif "pale" in original_name or "wear" in original_name:
			surface_tint = Color(1.08, 1.04, 0.94, 1.0)
		var material := StandardMaterial3D.new()
		material.resource_name = "Rock_Triplanar_%02d" % surface_index
		material.albedo_color = surface_tint
		material.albedo_texture = rock_albedo
		material.normal_enabled = true
		material.normal_texture = rock_normal
		material.normal_scale = 1.25
		material.roughness = 1.0
		material.roughness_texture = rock_orm
		material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		material.ao_enabled = true
		material.ao_texture = rock_orm
		material.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
		material.ao_light_affect = 0.50
		material.uv1_triplanar = true
		material.uv1_triplanar_sharpness = 1.65
		material.uv1_scale = Vector3(0.55, 0.55, 0.55)
		material.vertex_color_use_as_albedo = true
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		mesh.surface_set_material(surface_index, material)
	return mesh


static func _prepare_foliage_mesh(source: Mesh) -> Mesh:
	var mesh := source.duplicate(true) as ArrayMesh
	if mesh == null:
		return source
	var shader := load(FOLIAGE_SHADER_PATH) as Shader
	var height_m := maxf(mesh.get_aabb().size.y, 0.25)
	for surface_index in range(mesh.get_surface_count()):
		var original := source.surface_get_material(surface_index)
		var original_name := (
			original.resource_name.to_lower()
			if original != null
			else ""
		)
		var is_palm_frond := (
			"palm_frond_cards" in original_name
			or "frond_cards" in original_name
		)
		var is_shrub_card := (
			"shrub_foliage_cards" in original_name
			or "shrub_cards" in original_name
		)
		var is_woody_surface := (
			"trunk" in original_name
			or "crown_fiber" in original_name
			or "dates" in original_name
			or "stem" in original_name
			or "bark" in original_name
		)
		var base_color := Color("356b2d")
		var roughness := 0.90
		var card_mode := false
		var albedo_texture := _foliage_fallback_texture(
			"white",
			Color.WHITE
		)
		var normal_texture := _foliage_fallback_texture(
			"flat_normal",
			Color(0.5, 0.5, 1.0, 1.0)
		)
		var mask_texture := _foliage_fallback_texture(
			"default_leaf_mask",
			Color(0.86, 0.82, 0.0, 1.0)
		)
		var has_normal_texture := false
		var wind_response := 0.08 if is_woody_surface else 1.0
		var foliage_tint_response := 0.0 if is_woody_surface else 1.0
		var alpha_cutoff := 0.42
		var translucency := 0.55
		if original is BaseMaterial3D:
			var base_material := original as BaseMaterial3D
			base_color = base_material.albedo_color
			roughness = base_material.roughness
			if base_material.albedo_texture != null:
				albedo_texture = base_material.albedo_texture
				card_mode = (
					base_material.transparency
					!= BaseMaterial3D.TRANSPARENCY_DISABLED
				)
			if base_material.normal_enabled and base_material.normal_texture != null:
				normal_texture = base_material.normal_texture
				has_normal_texture = true
			if base_material.roughness_texture != null:
				mask_texture = base_material.roughness_texture
		if is_palm_frond:
			var palm_albedo := load(PALM_FROND_ALBEDO_PATH) as Texture2D
			var palm_normal := load(PALM_FROND_NORMAL_PATH) as Texture2D
			var palm_mask := load(PALM_FROND_MASK_PATH) as Texture2D
			if palm_albedo == null or palm_normal == null or palm_mask == null:
				push_error("El atlas PBR de frondas de palmera está incompleto")
			else:
				card_mode = true
				base_color = Color.WHITE
				roughness = 0.82
				albedo_texture = palm_albedo
				normal_texture = palm_normal
				mask_texture = palm_mask
				has_normal_texture = true
				wind_response = 1.0
				foliage_tint_response = 0.68
		if is_shrub_card:
			var shrub_albedo := load(SHRUB_FOLIAGE_ALBEDO_PATH) as Texture2D
			var shrub_normal := load(SHRUB_FOLIAGE_NORMAL_PATH) as Texture2D
			var shrub_mask := load(SHRUB_FOLIAGE_MASK_PATH) as Texture2D
			if shrub_albedo == null or shrub_normal == null or shrub_mask == null:
				push_error("El atlas PBR de follaje de arbustos está incompleto")
			else:
				card_mode = true
				base_color = Color.WHITE
				roughness = 0.84
				albedo_texture = shrub_albedo
				normal_texture = shrub_normal
				mask_texture = shrub_mask
				has_normal_texture = true
				# El atlas ya trae variación cromática real. Una respuesta intensa
				# a la LUT lo convertía en verde neón a escala de mesa.
				wind_response = 0.34
				foliage_tint_response = 0.16
				alpha_cutoff = 0.31
				translucency = 0.32
		var material := ShaderMaterial.new()
		material.resource_name = (
			"Foliage_Card_%02d" % surface_index
			if card_mode
			else "Foliage_Solid_%02d" % surface_index
		)
		material.shader = shader
		material.set_shader_parameter("card_mode", card_mode)
		material.set_shader_parameter("base_color", base_color)
		material.set_shader_parameter("albedo_texture", albedo_texture)
		material.set_shader_parameter("normal_texture", normal_texture)
		material.set_shader_parameter("mask_texture", mask_texture)
		material.set_shader_parameter("hue_ramp", _get_foliage_hue_ramp())
		material.set_shader_parameter("has_normal_texture", has_normal_texture)
		material.set_shader_parameter("surface_roughness", roughness)
		material.set_shader_parameter("alpha_cutoff", alpha_cutoff)
		material.set_shader_parameter("translucency", translucency)
		material.set_shader_parameter(
			"wind_amplitude_m",
			clampf(height_m * 0.012, 0.02, 0.18)
		)
		material.set_shader_parameter("pivot_height_m", height_m)
		material.set_shader_parameter(
			"wind_base_height_m",
			(
				height_m * 0.69
				if is_palm_frond
				else height_m * 0.06 if is_shrub_card else 0.0
			)
		)
		material.set_shader_parameter("wind_response", wind_response)
		material.set_shader_parameter(
			"foliage_tint_response",
			foliage_tint_response
		)
		material.set_shader_parameter(
			"presentation_scale",
			TerrainProfile.TERRAIN_PRESENTATION_SCALE
		)
		mesh.surface_set_material(surface_index, material)
	return mesh


static func _get_foliage_hue_ramp() -> GradientTexture1D:
	if _foliage_hue_ramp != null:
		return _foliage_hue_ramp
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.38, 0.72, 1.0])
	gradient.colors = PackedColorArray([
		Color(0.72, 1.00, 0.68, 1.0),
		Color(0.90, 0.98, 0.74, 1.0),
		Color(1.00, 0.82, 0.44, 1.0),
		Color(0.72, 0.48, 0.28, 1.0),
	])
	_foliage_hue_ramp = GradientTexture1D.new()
	_foliage_hue_ramp.resource_name = "Foliage_Green_To_Brown_LUT"
	_foliage_hue_ramp.width = 256
	_foliage_hue_ramp.gradient = gradient
	return _foliage_hue_ramp


static func _foliage_fallback_texture(key: String, color: Color) -> Texture2D:
	if _foliage_fallback_textures.has(key):
		return _foliage_fallback_textures[key]
	var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
	image.fill(color)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	texture.resource_name = "Foliage_Fallback_%s" % key
	_foliage_fallback_textures[key] = texture
	return texture


static func _generate_placements(
	definition: Dictionary,
	exclusion_route: Array[Vector2] = [],
	density_scale := 1.0,
) -> Array[Dictionary]:
	var rng := RandomNumberGenerator.new()
	rng.seed = int(definition["seed"])
	var placements: Array[Dictionary] = []
	var spacing := float(definition["spacing"])
	var spatial_hash := SpatialHash.new(spacing)
	var target_count := scaled_count(definition, density_scale)
	# Sparse highland habitats need a longer deterministic Poisson pass after
	# erosion divides the ridge into smaller terraces and drainage channels.
	var maximum_attempts := maxi(target_count * 96, 2400)
	var golden_x := rng.randf()
	var golden_z := rng.randf()
	for attempt in range(maximum_attempts):
		if placements.size() >= target_count:
			break
		# Secuencia de baja discrepancia con jitter: cubre el territorio antes de
		# volver a llenar los mismos claros del campo de densidad.
		var u := fmod(golden_x + float(attempt) * 0.61803398875 + rng.randf() * 0.035, 1.0)
		var v := fmod(golden_z + float(attempt) * 0.75487766624 + rng.randf() * 0.035, 1.0)
		var candidate := Vector2(
			lerpf(-TerrainProfile.HALF_WIDTH_M, TerrainProfile.HALF_WIDTH_M, u),
			lerpf(-TerrainProfile.HALF_LENGTH_M, TerrainProfile.HALF_LENGTH_M, v)
		)
		var edge_distance := TerrainProfile.coast_distance_at(candidate)
		if edge_distance < float(definition["edge_min"]) or edge_distance > float(definition["edge_max"]):
			continue
		var density := TerrainProfile.biome_density_at(candidate, int(definition["density_channel"]))
		density = pow(density, float(definition["density_power"]))
		var species_pattern := 0.76 + 0.24 * sin(
			candidate.x * 0.043 + candidate.y * 0.017 + float(definition["seed"]) * 0.013
		)
		if rng.randf() > density * species_pattern:
			continue
		var height := TerrainProfile.height_at(candidate)
		if height < float(definition["height_min"]) or height > float(definition["height_max"]):
			continue
		var normal := TerrainProfile.normal_at(candidate)
		var slope_degrees := rad_to_deg(acos(clampf(normal.y, -1.0, 1.0)))
		if slope_degrees > float(definition["slope_max"]):
			continue
		if (
			not exclusion_route.is_empty()
			and _distance_to_route(candidate, exclusion_route) < float(definition["route_clearance"])
		):
			continue
		var radius := spacing * 0.5
		if not spatial_hash.permits(candidate, radius):
			continue

		var age := pow(rng.randf(), 0.62)
		var scale_factor := lerpf(float(definition["scale_min"]), float(definition["scale_max"]), age)
		var width_variation := rng.randf_range(0.86, 1.13)
		var height_variation := rng.randf_range(0.92, 1.12)
		var yaw := rng.randf_range(0.0, TAU)
		var up := Vector3.UP.slerp(normal, float(definition["normal_alignment"])).normalized()
		var forward := Vector3(sin(yaw), 0.0, cos(yaw)).slide(up).normalized()
		var right := up.cross(forward).normalized()
		var orientation := Basis(right, up, forward)
		if definition["kind"] == "rock":
			var maximum_tilt := deg_to_rad(float(definition["tilt_max_degrees"]))
			orientation = orientation.rotated(
				orientation.x.normalized(),
				rng.randf_range(-maximum_tilt, maximum_tilt)
			)
			orientation = orientation.rotated(
				orientation.z.normalized(),
				rng.randf_range(-maximum_tilt, maximum_tilt)
			)
		var basis := Basis(
			orientation.x * scale_factor * width_variation,
			orientation.y * scale_factor * height_variation,
			orientation.z * scale_factor / width_variation
		)
		var sink := float(definition["sink"]) * scale_factor
		var origin := Vector3(candidate.x, height - sink, candidate.y)
		var color_axis := rng.randf()
		var instance_color := Color.WHITE
		if definition["kind"] == "rock":
			var tone := color_axis - 0.5
			instance_color = Color(
				1.0 + tone * 0.16,
				1.0 + tone * 0.07,
				1.0 - tone * 0.10,
				1.0
			)
		placements.append({
			"transform": Transform3D(basis, origin),
			"color": instance_color,
			# fase de viento, variación cromática, flexibilidad y edad
			"custom": Color(
				rng.randf(),
				_foliage_hue_index(definition, color_axis),
				rng.randf_range(0.25, 0.95),
				age
			),
		})
		spatial_hash.insert(candidate, radius)
	return placements


static func _foliage_hue_index(definition: Dictionary, color_axis: float) -> float:
	var key := String(definition["key"])
	var center := 0.48
	var spread := 0.32
	if key == "grass_green":
		center = 0.28
	elif key == "grass_dry":
		center = 0.78
	elif key.begins_with("palm_"):
		center = 0.36
	elif key.begins_with("broadleaf_"):
		center = 0.44
	elif key.begins_with("shrub_"):
		center = 0.52
	return clampf(center + (color_axis - 0.5) * spread, 0.0, 1.0)


static func _distance_to_route(candidate: Vector2, route: Array[Vector2]) -> float:
	if route.is_empty():
		return INF
	var minimum_distance := INF
	# El corredor del aldeano es un trayecto abierto: no debe despejarse una
	# línea artificial que una las rocas finales con el cabo de partida.
	for index in range(route.size() - 1):
		var start := route[index]
		var end := route[index + 1]
		minimum_distance = minf(minimum_distance, _distance_to_segment(candidate, start, end))
	return minimum_distance


static func _distance_to_segment(point: Vector2, start: Vector2, end: Vector2) -> float:
	var segment := end - start
	var length_squared := segment.length_squared()
	if is_zero_approx(length_squared):
		return point.distance_to(start)
	var t := clampf((point - start).dot(segment) / length_squared, 0.0, 1.0)
	return point.distance_to(start + segment * t)
