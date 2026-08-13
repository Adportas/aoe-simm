extends Node3D

const TERRAIN_SHADER_PATH := "res://materials/terrain.gdshader"
const WATER_SHADER_PATH := "res://materials/water.gdshader"
const OCEAN_FLOOR_SHADER_PATH := "res://materials/ocean_floor.gdshader"
const GROUND_TEXTURE_ROOT := "res://assets/environment/island_biome/textures/"
const ISLAND_BIOME_BUILDER := preload("res://scripts/island_biome_builder.gd")
const TERRAIN_LAYER_LIBRARY := preload("res://scripts/terrain_layer_library.gd")
const RUNTIME_PROFILE := preload("res://scripts/runtime_profile.gd")
const CORNER_NAMES := [
	"frente-izquierda",
	"frente-derecha",
	"fondo-derecha",
	"fondo-izquierda",
]
const VILLAGER_START_XZ := Vector2(-52.0, 288.0)
const CENTRAL_ROCKS_APPROACH_XZ := Vector2(-22.0, 157.0)
const WALK_ROUTE: Array[Vector2] = [
	VILLAGER_START_XZ,
	CENTRAL_ROCKS_APPROACH_XZ,
]
const SHOT_FORWARD_OFFSET_M := 0.055
const SHOT_SIDE_OFFSET_M := 0.115
const SHOT_HEIGHT_M := 0.075
const SHOT_TERRAIN_CLEARANCE_M := 0.050
const CINEMATIC_CHARACTER_BOOST := 1.85

enum DesktopCameraMode {
	CINEMATIC,
	OVERVIEW,
	TOP,
}

var calibration := TabletopCalibration.new()
var diorama_root: Node3D
var terrain_instance: MeshInstance3D
var terrain_material: ShaderMaterial
var ocean_instance: MeshInstance3D
var ocean_material: ShaderMaterial
var unit: UnitController
var target_marker: MeshInstance3D
var physical_table: MeshInstance3D
var camera: Camera3D
var environment: Environment
var ar_adapter: ArSessionAdapter
var camera_background: ArCameraBackground

var status_label: Label
var instruction_label: Label
var capture_corner_button: Button
var grid_button: Button
var walk_button: Button
var camera_button: Button
var crosshair: Label
var _captured_corners := PackedVector3Array()
var _ar_status := "Simulador de escritorio"
var _detected_plane_count := 0
var _mesh_anchor_count := 0
var _grid_enabled := false
var _is_ar_mode := false
var _status_accumulator := 0.0
var _marker_phase := 0.0
var _auto_walk_enabled := true
var _next_walk_route_index := 1
var _journey_complete := false
var _desktop_camera_mode := DesktopCameraMode.CINEMATIC
var _rng := RandomNumberGenerator.new()
var biome_counts: Dictionary = {}
var _is_web_preview := RUNTIME_PROFILE.is_web_preview()


func _ready() -> void:
	_rng.randomize()
	calibration.set_exact_simulation_table()
	_build_camera_background()
	_build_world()
	_build_interface()
	_apply_calibration()
	_start_runtime_mode()
	_start_walking_showcase()
	if not _is_ar_mode:
		_set_desktop_camera_mode(DesktopCameraMode.CINEMATIC)


func _exit_tree() -> void:
	if is_instance_valid(ar_adapter):
		ar_adapter.stop()


func _process(delta: float) -> void:
	_marker_phase += delta
	if is_instance_valid(target_marker) and is_instance_valid(unit):
		var marker_pulse := 1.0 + sin(_marker_phase * 4.0) * 0.08
		target_marker.scale = Vector3(marker_pulse, 1.0, marker_pulse)
		target_marker.visible = unit.has_target and not _auto_walk_enabled

	_status_accumulator += delta
	if _status_accumulator >= 0.15:
		_status_accumulator = 0.0
		_refresh_status()


func _unhandled_input(event: InputEvent) -> void:
	var screen_position := Vector2.ZERO
	var pressed := false
	if event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton
		pressed = mouse_event.button_index == MOUSE_BUTTON_LEFT and mouse_event.pressed
		screen_position = mouse_event.position
	elif event is InputEventScreenTouch:
		var touch_event := event as InputEventScreenTouch
		pressed = touch_event.pressed
		screen_position = touch_event.position
	if not pressed or not calibration.is_valid:
		return

	var hit := _screen_to_terrain(screen_position)
	if hit.get("ok", false):
		_set_manual_target(hit["position"])
		get_viewport().set_input_as_handled()


func _build_camera_background() -> void:
	var background_layer := CanvasLayer.new()
	background_layer.name = "ARCameraLayer"
	background_layer.layer = -5
	add_child(background_layer)
	camera_background = ArCameraBackground.new()
	background_layer.add_child(camera_background)


func _build_world() -> void:
	environment = Environment.new()
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("477fa8")
	sky_material.sky_horizon_color = Color("aacbd5")
	sky_material.ground_horizon_color = Color("8db8c3")
	sky_material.ground_bottom_color = Color("184b5c")
	sky_material.sky_curve = 0.18
	sky_material.ground_curve = 0.14
	sky_material.sun_angle_max = 4.2
	sky_material.sun_curve = 0.06
	var sky := Sky.new()
	sky.sky_material = sky_material
	environment.sky = sky
	environment.background_mode = Environment.BG_SKY
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	environment.ambient_light_energy = 0.46
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_exposure = 0.84
	environment.fog_enabled = true
	environment.fog_light_color = Color("c9d4cc")
	environment.fog_light_energy = 0.34
	environment.fog_density = 0.10
	environment.fog_sky_affect = 0.38
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	add_child(world_environment)

	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-32.0, -31.0, 0.0)
	sun.light_color = Color("fff2d2")
	sun.light_energy = 1.18
	sun.light_angular_distance = 0.85
	sun.shadow_bias = 0.035
	sun.directional_shadow_max_distance = 5.0
	sun.shadow_enabled = true
	add_child(sun)

	camera = Camera3D.new()
	camera.name = "ARCamera"
	camera.current = true
	camera.near = 0.005
	camera.far = 20.0
	add_child(camera)
	_set_desktop_camera(false)

	physical_table = MeshInstance3D.new()
	physical_table.name = "SimulatedPhysicalTable"
	var table_mesh := BoxMesh.new()
	table_mesh.size = Vector3(1.06, 0.045, 1.86)
	physical_table.mesh = table_mesh
	physical_table.position.y = -0.027
	var table_material := StandardMaterial3D.new()
	table_material.albedo_color = Color("5c3a27")
	table_material.roughness = 0.76
	physical_table.material_override = table_material
	# La mesa es una ayuda de calibración, no parte de la presentación de la isla.
	physical_table.visible = false
	add_child(physical_table)

	diorama_root = Node3D.new()
	diorama_root.name = "DioramaRoot_1_to_400"
	add_child(diorama_root)

	terrain_instance = MeshInstance3D.new()
	terrain_instance.name = "Terrain_400x720m"
	terrain_instance.mesh = TerrainMeshBuilder.build()
	terrain_material = ShaderMaterial.new()
	terrain_material.shader = load(TERRAIN_SHADER_PATH)
	_configure_terrain_material()
	terrain_instance.material_override = terrain_material
	diorama_root.add_child(terrain_instance)
	_build_ocean()

	biome_counts = ISLAND_BIOME_BUILDER.populate(
		diorama_root,
		WALK_ROUTE,
		RUNTIME_PROFILE.biome_density_scale()
	)

	unit = UnitController.new()
	unit.name = "Human_1_to_180"
	diorama_root.add_child(unit)

	target_marker = _build_target_marker()
	diorama_root.add_child(target_marker)


func _build_target_marker() -> MeshInstance3D:
	var marker := MeshInstance3D.new()
	marker.name = "TargetMarker"
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 4.5
	cylinder.bottom_radius = 4.5
	cylinder.height = 0.7
	marker.mesh = cylinder
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(1.0, 0.28, 0.12, 0.85)
	material.emission_enabled = true
	material.emission = Color("f05b32")
	material.emission_energy_multiplier = 0.65
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	marker.material_override = material
	return marker


func _configure_terrain_material() -> void:
	var layer_arrays := {
		"layer_albedo": TERRAIN_LAYER_LIBRARY.layer_array("albedo"),
		"layer_normal": TERRAIN_LAYER_LIBRARY.layer_array("normal"),
		"layer_orm": TERRAIN_LAYER_LIBRARY.layer_array("orm"),
	}
	for parameter in layer_arrays:
		var texture_array := layer_arrays[parameter] as Texture2DArray
		if texture_array == null:
			push_error("Falta el array de terreno: %s" % parameter)
			continue
		terrain_material.set_shader_parameter(parameter, texture_array)
	var shared_textures := {
		"macro_noise": GROUND_TEXTURE_ROOT + "terrain_macro_noise.png",
		"detail_normal": GROUND_TEXTURE_ROOT + "terrain_detail_normal.png",
	}
	for parameter in shared_textures:
		var texture := load(shared_textures[parameter]) as Texture2D
		if texture == null:
			push_error("Falta textura compartida de terreno: %s" % shared_textures[parameter])
			continue
		terrain_material.set_shader_parameter(parameter, texture)
	var data_maps := {
		"splat_a": TerrainProfile.SPLAT_A_PATH,
		"splat_b": TerrainProfile.SPLAT_B_PATH,
		"detail_map": TerrainProfile.DETAIL_PATH,
		"island_sdf": TerrainProfile.SDF_PATH,
		"terrain_normal": TerrainProfile.TERRAIN_NORMAL_PATH,
		"terrain_ao": TerrainProfile.TERRAIN_AO_PATH,
	}
	for parameter in data_maps:
		var texture := TerrainProfile.data_texture(data_maps[parameter])
		if texture != null:
			terrain_material.set_shader_parameter(parameter, texture)
	terrain_material.set_shader_parameter("sea_level_m", TerrainProfile.SEA_LEVEL_M)
	terrain_material.set_shader_parameter("grid_enabled", _grid_enabled)


func _build_ocean() -> void:
	var ocean_floor := MeshInstance3D.new()
	ocean_floor.name = "OceanFloor_Extended"
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(1600.0, 1800.0)
	ocean_floor.mesh = floor_mesh
	ocean_floor.position.y = -14.82
	ocean_floor.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var floor_material := ShaderMaterial.new()
	floor_material.shader = load(OCEAN_FLOOR_SHADER_PATH)
	floor_material.set_shader_parameter(
		"sand_normal",
		load(GROUND_TEXTURE_ROOT + "ground_sand_normal.png") as Texture2D
	)
	ocean_floor.material_override = floor_material
	diorama_root.add_child(ocean_floor)

	ocean_instance = MeshInstance3D.new()
	ocean_instance.name = "Ocean_400x720m"
	var ocean_mesh := PlaneMesh.new()
	# El plano excede el mapa para que la cámara nunca revele un diorama rectangular.
	ocean_mesh.size = Vector2(1600.0, 1800.0)
	var ocean_subdivisions := RUNTIME_PROFILE.ocean_subdivisions()
	ocean_mesh.subdivide_width = ocean_subdivisions.x
	ocean_mesh.subdivide_depth = ocean_subdivisions.y
	ocean_instance.mesh = ocean_mesh
	ocean_instance.position.y = TerrainProfile.SEA_LEVEL_M
	ocean_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ocean_material = ShaderMaterial.new()
	ocean_material.shader = load(WATER_SHADER_PATH)
	ocean_material.render_priority = 1
	ocean_material.set_shader_parameter(
		"island_sdf",
		TerrainProfile.data_texture(TerrainProfile.SDF_PATH)
	)
	ocean_material.set_shader_parameter(
		"island_height",
		TerrainProfile.data_texture(TerrainProfile.HEIGHT_PATH)
	)
	ocean_material.set_shader_parameter(
		"detail_map",
		TerrainProfile.data_texture(TerrainProfile.DETAIL_PATH)
	)
	ocean_material.set_shader_parameter("sea_level_m", TerrainProfile.SEA_LEVEL_M)
	ocean_material.set_shader_parameter(
		"presentation_scale",
		TerrainProfile.TERRAIN_PRESENTATION_SCALE
	)
	ocean_material.set_shader_parameter("foam_depth_m", 1.15)
	ocean_material.set_shader_parameter("foam_max_opacity", 0.70)
	ocean_material.set_shader_parameter("shore_softness_m", 0.30)
	ocean_instance.material_override = ocean_material
	ocean_instance.extra_cull_margin = 2.0
	diorama_root.add_child(ocean_instance)


func _build_interface() -> void:
	var interface_layer := CanvasLayer.new()
	interface_layer.name = "Interface"
	interface_layer.layer = 10
	add_child(interface_layer)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 18)
	margin.add_theme_constant_override("margin_top", 18)
	margin.add_theme_constant_override("margin_right", 18)
	margin.add_theme_constant_override("margin_bottom", 18)
	interface_layer.add_child(margin)

	var layout := VBoxContainer.new()
	layout.alignment = BoxContainer.ALIGNMENT_BEGIN
	margin.add_child(layout)

	var panel := PanelContainer.new()
	panel.custom_minimum_size = Vector2(430.0, 0.0)
	panel.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.025, 0.04, 0.065, 0.88)
	panel_style.border_color = Color(0.28, 0.45, 0.58, 0.75)
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(9)
	panel_style.content_margin_left = 15.0
	panel_style.content_margin_right = 15.0
	panel_style.content_margin_top = 12.0
	panel_style.content_margin_bottom = 12.0
	panel.add_theme_stylebox_override("panel", panel_style)
	layout.add_child(panel)

	var panel_content := VBoxContainer.new()
	panel_content.add_theme_constant_override("separation", 8)
	panel.add_child(panel_content)
	var title := Label.new()
	title.text = (
		"Isla AR · Vista web · 720 × 400 m"
		if _is_web_preview
		else "Isla AR · 720 × 400 m"
	)
	title.add_theme_font_size_override("font_size", 22)
	panel_content.add_child(title)

	status_label = Label.new()
	status_label.text = "Inicializando…"
	status_label.add_theme_font_size_override("font_size", 14)
	panel_content.add_child(status_label)

	var actions := GridContainer.new()
	actions.columns = 2
	actions.add_theme_constant_override("h_separation", 7)
	actions.add_theme_constant_override("v_separation", 7)
	panel_content.add_child(actions)
	actions.add_child(_make_button("Destino aleatorio", _on_random_target))
	walk_button = _make_button("Paseo: hacia las rocas", _on_toggle_auto_walk)
	actions.add_child(walk_button)
	grid_button = _make_button("Mostrar cuadrícula", _on_toggle_grid)
	actions.add_child(grid_button)
	camera_button = _make_button("Cámara: plano fijo", _on_cycle_camera)
	actions.add_child(camera_button)

	capture_corner_button = _make_button("Capturar esquina 1", _on_capture_corner)
	capture_corner_button.visible = false
	panel_content.add_child(capture_corner_button)

	instruction_label = Label.new()
	instruction_label.text = (
		"El aldeano cruzará desde el cabo izquierdo hasta las rocas centrales. "
		+ "Haz clic sobre el terreno para darle un destino manual."
	)
	instruction_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	instruction_label.custom_minimum_size.x = 350.0
	panel_content.add_child(instruction_label)

	crosshair = Label.new()
	crosshair.text = "+"
	crosshair.add_theme_font_size_override("font_size", 36)
	crosshair.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	crosshair.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.position = Vector2(-12.0, -24.0)
	crosshair.size = Vector2(24.0, 48.0)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	interface_layer.add_child(crosshair)


func _make_button(text_value: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text_value
	button.pressed.connect(callback)
	return button


func _start_runtime_mode() -> void:
	ar_adapter = ArSessionAdapter.new()
	ar_adapter.name = "ARKitAdapter"
	add_child(ar_adapter)
	ar_adapter.frame_ready.connect(_on_ar_frame)
	ar_adapter.status_changed.connect(_on_ar_status_changed)
	ar_adapter.plane_count_changed.connect(_on_plane_count_changed)
	ar_adapter.mesh_count_changed.connect(_on_mesh_count_changed)
	_is_ar_mode = ar_adapter.start()
	crosshair.visible = _is_ar_mode
	_refresh_camera_button()
	if _is_ar_mode:
		calibration.clear()
		diorama_root.visible = false
		physical_table.visible = false
		environment.background_mode = Environment.BG_CANVAS
		environment.set("background_canvas_max_layer", -1)
		capture_corner_button.visible = true
		instruction_label.text = (
			"Apunta la cruz al vértice frente-izquierda y pulsa Capturar. "
			+ "Repite las cuatro esquinas desde el mismo lado de la mesa."
		)
	else:
		_ar_status = (
			"Vista web optimizada (ARKit solo está disponible en iOS)"
			if _is_web_preview
			else "Simulador de escritorio (ARKit se activará en iOS)"
		)


func _apply_calibration() -> void:
	if not calibration.is_valid:
		return
	diorama_root.global_transform = calibration.table_transform
	diorama_root.visible = true


func _start_walking_showcase() -> void:
	unit.target_reached.connect(_on_unit_target_reached)
	_restart_walk_route()


func _restart_walk_route() -> void:
	unit.teleport(VILLAGER_START_XZ)
	unit.distance_walked_m = 0.0
	_next_walk_route_index = 1
	_journey_complete = false
	_auto_walk_enabled = true
	_refresh_walk_button()
	_advance_walk_route()


func _advance_walk_route() -> void:
	if (
		not _auto_walk_enabled
		or not calibration.is_valid
		or not diorama_root.visible
		or _next_walk_route_index >= WALK_ROUTE.size()
	):
		return
	var destination_index := _next_walk_route_index
	_set_target(WALK_ROUTE[destination_index])
	_next_walk_route_index += 1


func _on_unit_target_reached() -> void:
	if _auto_walk_enabled:
		if _next_walk_route_index < WALK_ROUTE.size():
			_advance_walk_route()
			return
		_auto_walk_enabled = false
		_journey_complete = true
		_refresh_walk_button()
		instruction_label.text = (
			"El aldeano llegó a las primeras rocas del centro. "
			+ "Pulsa Repetir paseo para verlo otra vez."
		)
		return
	instruction_label.text = (
		"Destino alcanzado. Haz clic en otro punto o reinicia el paseo a las rocas."
	)


func _set_manual_target(target_xz: Vector2) -> void:
	_auto_walk_enabled = false
	_journey_complete = false
	_refresh_walk_button()
	_set_target(target_xz)
	instruction_label.text = (
		"Destino manual activo. Pulsa Iniciar paseo para volver al cabo izquierdo."
	)


func _set_target(target_xz: Vector2) -> void:
	var clamped := TerrainProfile.clamp_to_bounds(target_xz, 4.0)
	var start_xz := Vector2(unit.position.x, unit.position.z)
	unit.set_target(clamped)
	if (
		not _is_ar_mode
		and _desktop_camera_mode == DesktopCameraMode.CINEMATIC
	):
		_frame_cinematic_segment(start_xz, clamped)
	target_marker.position = Vector3(
		clamped.x,
		TerrainProfile.height_at(clamped) + 0.5,
		clamped.y
	)


func _screen_to_terrain(screen_position: Vector2) -> Dictionary:
	var ray_origin_world := camera.project_ray_origin(screen_position)
	var ray_direction_world := camera.project_ray_normal(screen_position)
	var inverse := diorama_root.global_transform.affine_inverse()
	var ray_origin := inverse * ray_origin_world
	var ray_direction := inverse.basis * ray_direction_world
	if absf(ray_direction.y) < 0.000001:
		return {"ok": false}

	var estimate_height := TerrainProfile.height_at(Vector2.ZERO)
	var distance := (estimate_height - ray_origin.y) / ray_direction.y
	if distance < 0.0:
		return {"ok": false}
	var candidate := ray_origin + ray_direction * distance
	for iteration in range(7):
		var candidate_xz := Vector2(candidate.x, candidate.z)
		estimate_height = TerrainProfile.height_at(candidate_xz)
		distance = (estimate_height - ray_origin.y) / ray_direction.y
		candidate = ray_origin + ray_direction * distance

	var result_xz := Vector2(candidate.x, candidate.z)
	if not TerrainProfile.is_inside(result_xz):
		return {"ok": false}
	return {"ok": true, "position": result_xz}


func _on_random_target() -> void:
	for attempt in range(32):
		var candidate := Vector2(
			_rng.randf_range(-TerrainProfile.HALF_WIDTH_M, TerrainProfile.HALF_WIDTH_M),
			_rng.randf_range(-TerrainProfile.HALF_LENGTH_M, TerrainProfile.HALF_LENGTH_M)
		)
		if TerrainProfile.is_inside(candidate, 12.0):
			_set_manual_target(candidate)
			return
	_set_manual_target(Vector2.ZERO)


func _on_toggle_auto_walk() -> void:
	if _auto_walk_enabled:
		_auto_walk_enabled = false
		_journey_complete = false
		_next_walk_route_index = 1
		unit.stop()
		_refresh_walk_button()
		instruction_label.text = (
			"Paseo en pausa. Pulsa Iniciar paseo para comenzar otra vez desde la izquierda."
		)
		return
	_restart_walk_route()
	instruction_label.text = (
		"El aldeano avanza desde el cabo izquierdo hacia las rocas centrales."
	)


func _refresh_walk_button() -> void:
	if not is_instance_valid(walk_button):
		return
	if _auto_walk_enabled:
		walk_button.text = "Paseo: hacia las rocas"
	elif _journey_complete:
		walk_button.text = "Repetir paseo"
	else:
		walk_button.text = "Iniciar paseo"


func _on_toggle_grid() -> void:
	_grid_enabled = not _grid_enabled
	terrain_material.set_shader_parameter("grid_enabled", _grid_enabled)
	grid_button.text = "Ocultar cuadrícula" if _grid_enabled else "Mostrar cuadrícula"


func _on_cycle_camera() -> void:
	if _is_ar_mode:
		return
	match _desktop_camera_mode:
		DesktopCameraMode.CINEMATIC:
			_set_desktop_camera_mode(DesktopCameraMode.OVERVIEW)
		DesktopCameraMode.OVERVIEW:
			_set_desktop_camera_mode(DesktopCameraMode.TOP)
		_:
			_set_desktop_camera_mode(DesktopCameraMode.CINEMATIC)


func _set_desktop_camera_mode(mode: int) -> void:
	_desktop_camera_mode = mode
	_apply_character_presentation_scale()
	match _desktop_camera_mode:
		DesktopCameraMode.CINEMATIC:
			camera.fov = 32.0
			_frame_cinematic_segment(
				Vector2(unit.position.x, unit.position.z),
				unit.target_xz
			)
		DesktopCameraMode.OVERVIEW:
			camera.fov = 36.0
			_set_desktop_camera(false)
		DesktopCameraMode.TOP:
			camera.fov = 50.0
			_set_desktop_camera(true)
	_refresh_camera_button()


func _apply_character_presentation_scale() -> void:
	if not is_instance_valid(unit) or not is_instance_valid(unit._visual_root):
		return
	var scale_factor := TerrainProfile.CHARACTER_RELATIVE_SCALE
	# El plano fijo abarca 134 m: este refuerzo solo de presentación mantiene
	# legible la silueta y el ciclo Walk sin alterar pies, velocidad ni ruta.
	if not _is_ar_mode and _desktop_camera_mode == DesktopCameraMode.CINEMATIC:
		scale_factor *= CINEMATIC_CHARACTER_BOOST
	unit._visual_root.scale = Vector3.ONE * scale_factor


func _frame_cinematic_segment(start_xz: Vector2, end_xz: Vector2) -> void:
	if not is_instance_valid(camera) or not is_instance_valid(unit):
		return
	var start_world := calibration.simulation_to_world(Vector3(
		start_xz.x,
		TerrainProfile.height_at(start_xz),
		start_xz.y
	))
	var end_world := calibration.simulation_to_world(Vector3(
		end_xz.x,
		TerrainProfile.height_at(end_xz),
		end_xz.y
	))
	var segment_direction := end_world - start_world
	segment_direction.y = 0.0
	if segment_direction.length_squared() < 0.000001:
		segment_direction = -unit.global_transform.basis.z
		segment_direction.y = 0.0
	segment_direction = segment_direction.normalized()
	var side := segment_direction.cross(Vector3.UP).normalized()
	var segment_length_m := start_world.distance_to(end_world)
	var shot_forward_offset := maxf(
		SHOT_FORWARD_OFFSET_M,
		segment_length_m * 0.18
	)
	var shot_side_offset := maxf(
		SHOT_SIDE_OFFSET_M,
		segment_length_m * 1.05
	)
	var shot_height := maxf(
		SHOT_HEIGHT_M,
		segment_length_m * 0.42
	)
	var look_target := (
		(start_world + end_world) * 0.5
		+ Vector3.UP * 0.007
	)
	var desired_position := (
		look_target
		+ segment_direction * shot_forward_offset
		+ side * shot_side_offset
		+ Vector3.UP * shot_height
	)
	var camera_simulation_position := calibration.world_to_simulation(
		desired_position
	)
	var camera_terrain_xz := Vector2(
		camera_simulation_position.x,
		camera_simulation_position.z
	)
	# La cámara puede quedar sobre el océano. Conservar este lado del eje hace
	# que el cabo de partida siempre aparezca a la izquierda del plano y evita
	# invertir visualmente el recorrido por la silueta irregular de la isla.
	if TerrainProfile.is_inside(camera_terrain_xz):
		var terrain_world_position := calibration.simulation_to_world(Vector3(
			camera_terrain_xz.x,
			TerrainProfile.height_at(camera_terrain_xz),
			camera_terrain_xz.y
		))
		desired_position.y = maxf(
			desired_position.y,
			terrain_world_position.y + SHOT_TERRAIN_CLEARANCE_M
		)
	camera.global_position = desired_position
	camera.look_at(look_target, Vector3.UP)


func _refresh_camera_button() -> void:
	if not is_instance_valid(camera_button):
		return
	if _is_ar_mode:
		camera_button.text = "Cámara: AR"
		camera_button.disabled = true
		return
	camera_button.disabled = false
	match _desktop_camera_mode:
		DesktopCameraMode.CINEMATIC:
			camera_button.text = "Cámara: plano fijo"
		DesktopCameraMode.OVERVIEW:
			camera_button.text = "Cámara: general"
		_:
			camera_button.text = "Cámara: cenital"


func _set_desktop_camera(top_view: bool) -> void:
	if top_view:
		camera.position = Vector3(0.01, 2.35, 0.0)
		camera.look_at(Vector3.ZERO, Vector3.RIGHT)
	else:
		camera.position = Vector3(0.88, 1.72, 0.02)
		camera.look_at(Vector3(0.0, 0.06, 0.0), Vector3.UP)


func _on_capture_corner() -> void:
	if not _is_ar_mode:
		return
	var result := ar_adapter.raycast_from_camera_center()
	if not result.get("ok", false):
		_ar_status = "Captura fallida: %s" % result.get("reason", "sin superficie")
		return
	_captured_corners.append(result["position"])
	if _captured_corners.size() < 4:
		var next_index := _captured_corners.size()
		capture_corner_button.text = "Capturar esquina %d" % (next_index + 1)
		instruction_label.text = "Ahora apunta a la esquina %s." % CORNER_NAMES[next_index]
		return

	if calibration.set_corners(_captured_corners):
		_apply_calibration()
		if _auto_walk_enabled and not unit.has_target:
			_advance_walk_route()
		capture_corner_button.text = "Recalibrar mesa"
		instruction_label.text = (
			"Mesa fijada. El aldeano ya recorre el paisaje; "
			+ "toca el terreno para cambiar su destino."
		)
		_ar_status = "Mesa calibrada y terreno bloqueado"
	else:
		_ar_status = "Calibración rechazada: %s" % calibration.validation_message
		_captured_corners.clear()
		capture_corner_button.text = "Capturar esquina 1"


func _on_ar_frame(frame: Variant, ar_camera: Variant) -> void:
	if ar_camera == null:
		return
	camera.global_transform = ar_camera.get("transform") as Transform3D
	var orientation := _ui_interface_orientation()
	var projection: PackedFloat32Array = ar_camera.call(
		"projection_matrix_for_orientation",
		orientation,
		get_viewport().get_visible_rect().size,
		camera.near,
		camera.far
	)
	if projection.size() == 16 and absf(projection[5]) > 0.0001:
		camera.fov = rad_to_deg(2.0 * atan(1.0 / absf(projection[5])))
	camera_background.update_from_frame(frame, orientation)


func _ui_interface_orientation() -> int:
	# UIInterfaceOrientation: portrait=1, landscapeLeft=3. La exportación inicial
	# se restringe a paisaje; validaremos el sentido exacto en el primer dispositivo.
	var viewport_size := get_viewport().get_visible_rect().size
	return 3 if viewport_size.x >= viewport_size.y else 1


func _on_ar_status_changed(message: String) -> void:
	_ar_status = message


func _on_plane_count_changed(count: int) -> void:
	_detected_plane_count = count


func _on_mesh_count_changed(count: int) -> void:
	_mesh_anchor_count = count


func _refresh_status() -> void:
	if not is_instance_valid(status_label) or not is_instance_valid(unit):
		return
	var unit_xz := Vector2(unit.position.x, unit.position.z)
	var elevation_m := TerrainProfile.height_at(unit_xz)
	var physical_elevation_cm := elevation_m * TerrainProfile.TERRAIN_PRESENTATION_SCALE * 100.0
	var movement_status := "quieto"
	if unit.has_target:
		movement_status = "caminando"
	elif _journey_complete:
		movement_status = "junto a las rocas"
	var journey_length := VILLAGER_START_XZ.distance_to(
		CENTRAL_ROCKS_APPROACH_XZ
	)
	var journey_progress := clampf(
		1.0
		- unit_xz.distance_to(CENTRAL_ROCKS_APPROACH_XZ)
		/ journey_length,
		0.0,
		1.0
	)
	var camera_status := "AR"
	if not _is_ar_mode:
		match _desktop_camera_mode:
			DesktopCameraMode.CINEMATIC:
				camera_status = "plano fijo"
			DesktopCameraMode.OVERVIEW:
				camera_status = "general"
			_:
				camera_status = "cenital"
	var camera_diagnostic := ""
	var biome_instance_count := 0
	for count in biome_counts.values():
		biome_instance_count += int(count)
	if _is_ar_mode:
		camera_diagnostic = "\nPlanos AR: %d · mallas LiDAR: %d · copia cámara: %.1f ms" % [
			_detected_plane_count,
			_mesh_anchor_count,
			camera_background.last_copy_time_ms,
		]
	status_label.text = (
		"%s\n"
		+ "Mesa: %.2f × %.2f m · territorio: 720 × 400 m\n"
		+ "Terreno 1:400 · personaje 1:180 (10 mm)\n"
		+ "Aldeano: %s · avance %.0f%% · recorrido %.0f m · cámara %s\n"
		+ "Bioma tropical: %d instancias en %d familias\n"
		+ "Unidad: x %.1f · z %.1f · altura %.1f m (%.1f cm físicos)\n"
		+ "Error de apoyo: %.3f m virtuales · FPS: %d%s"
	) % [
		_ar_status,
		calibration.measured_width_m,
		calibration.measured_length_m,
		movement_status,
		journey_progress * 100.0,
		unit.distance_walked_m,
		camera_status,
		biome_instance_count,
		biome_counts.size(),
		unit.position.x,
		unit.position.z,
		elevation_m,
		physical_elevation_cm,
		unit.ground_error_m(),
		Engine.get_frames_per_second(),
		camera_diagnostic,
	]
