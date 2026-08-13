extends SceneTree

const ISLAND_BIOME_BUILDER := preload("res://scripts/island_biome_builder.gd")
const TERRAIN_LAYER_LIBRARY := preload("res://scripts/terrain_layer_library.gd")
const RUNTIME_PROFILE := preload("res://scripts/runtime_profile.gd")

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	_test_scales()
	_test_exact_calibration()
	_test_rotated_calibration()
	_test_terrain_profile()
	_test_unit_ground_following()
	_test_mesh_shape()
	_test_web_preview_profile()
	_test_island_biome_assets()
	_test_blender_character()
	_test_villager_asset()
	_test_walking_showcase()

	if failures.is_empty():
		print("TABLETOP_POC_TESTS_OK")
		quit(0)
		return
	for failure in failures:
		push_error(failure)
	print("TABLETOP_POC_TESTS_FAILED=%d" % failures.size())
	quit(1)


func _test_scales() -> void:
	_expect_near(TerrainProfile.WIDTH_M * TerrainProfile.TERRAIN_PRESENTATION_SCALE, 1.0, 0.000001, "ancho físico")
	_expect_near(TerrainProfile.LENGTH_M * TerrainProfile.TERRAIN_PRESENTATION_SCALE, 1.8, 0.000001, "largo físico")
	_expect_near(1.8 * TerrainProfile.CHARACTER_PRESENTATION_SCALE, 0.01, 0.000001, "altura visible del humano")
	_expect_near(TerrainProfile.CHARACTER_RELATIVE_SCALE, 400.0 / 180.0, 0.000001, "exageración relativa")


func _test_exact_calibration() -> void:
	var result := TabletopCalibration.new()
	result.set_exact_simulation_table()
	_expect(result.is_valid, "la calibración exacta debe ser válida")
	_expect_near(result.measured_width_m, 1.0, 0.000001, "ancho medido")
	_expect_near(result.measured_length_m, 1.8, 0.000001, "largo medido")
	var right_edge := result.simulation_to_world(Vector3(TerrainProfile.HALF_WIDTH_M, 0.0, 0.0))
	_expect_near(right_edge.x, 0.5, 0.000001, "borde derecho transformado")


func _test_rotated_calibration() -> void:
	var yaw := Basis(Vector3.UP, deg_to_rad(31.0))
	var center := Vector3(2.0, 0.78, -1.3)
	var local_corners := [
		Vector3(-0.5, 0.0, -0.9),
		Vector3(0.5, 0.0, -0.9),
		Vector3(0.5, 0.0, 0.9),
		Vector3(-0.5, 0.0, 0.9),
	]
	var world_corners := PackedVector3Array()
	for corner in local_corners:
		world_corners.append(center + yaw * corner)
	var result := TabletopCalibration.new()
	_expect(result.set_corners(world_corners), "la mesa rotada debe calibrarse")
	var mapped_center := result.simulation_to_world(Vector3.ZERO)
	_expect(mapped_center.distance_to(center) < 0.00001, "el centro calibrado debe conservarse")


func _test_terrain_profile() -> void:
	var land_samples := [
		Vector2(-78.0, -236.0),
		Vector2.ZERO,
		Vector2(88.0, 170.0),
		Vector2(35.0, -148.0),
	]
	for sample in land_samples:
		var height := TerrainProfile.height_at(sample)
		_expect(TerrainProfile.is_inside(sample), "la muestra debe caer dentro de la isla: %s" % sample)
		_expect(height > 0.0 and height <= 60.1, "altura horneada razonable en %s" % sample)
		_expect_near(TerrainProfile.normal_at(sample).length(), 1.0, 0.0001, "normal unitaria")
	for sea_sample in [Vector2(-198.0, -355.0), Vector2(198.0, 355.0)]:
		_expect(not TerrainProfile.is_inside(sea_sample), "las esquinas del mapa deben ser océano")
		_expect(
			TerrainProfile.height_at(sea_sample) < TerrainProfile.SEA_LEVEL_M,
			"el lecho marino debe quedar bajo el nivel del agua"
		)
	_expect(
		TerrainProfile.height_at(Vector2(20.52, -67.92)) > 59.5,
		"la isla debe alcanzar una cumbre rocosa de unos 60 m"
	)
	var cliff_normal := TerrainProfile.normal_at(Vector2(40.0, -85.0), 0.75)
	_expect(
		rad_to_deg(acos(clampf(cliff_normal.y, -1.0, 1.0))) > 55.0,
		"el heightmap debe conservar al menos un frente de acantilado"
	)
	var center_distances := [
		TerrainProfile.coast_distance_at(Vector2(-0.02, 0.0)),
		TerrainProfile.coast_distance_at(Vector2.ZERO),
		TerrainProfile.coast_distance_at(Vector2(0.02, 0.0)),
	]
	_expect(
		absf(center_distances[0] - center_distances[1]) < 0.08
		and absf(center_distances[2] - center_distances[1]) < 0.08,
		"el SDF no debe tener una discontinuidad en el origen"
	)
	var clamped_coast := TerrainProfile.clamp_to_bounds(Vector2(200.0, 360.0), 8.0)
	_expect(
		TerrainProfile.is_inside(clamped_coast, 7.99),
		"el ajuste de destinos debe respetar la costa irregular"
	)

	for data_path in [
		TerrainProfile.SDF_PATH,
		TerrainProfile.HEIGHT_PATH,
		TerrainProfile.DENSITY_PATH,
		TerrainProfile.SPLAT_A_PATH,
		TerrainProfile.SPLAT_B_PATH,
		TerrainProfile.DETAIL_PATH,
		TerrainProfile.TERRAIN_NORMAL_PATH,
		TerrainProfile.TERRAIN_AO_PATH,
	]:
		var image := TerrainProfile.data_image(data_path)
		_expect(not image.is_empty(), "debe cargar el campo horneado %s" % data_path)
		_expect(image.get_size() == Vector2i(576, 1024), "resolución del campo %s" % data_path)
	for float_path in [TerrainProfile.SDF_PATH, TerrainProfile.HEIGHT_PATH]:
		var float_image := TerrainProfile.data_image(float_path)
		_expect(
			float_image.get_format() == Image.FORMAT_RF,
			"el campo métrico %s debe conservar float32 de un canal" % float_path
		)
	for channel in range(4):
		var maximum_density := 0.0
		for z in range(-300, 301, 30):
			for x in range(-170, 171, 30):
				maximum_density = maxf(
					maximum_density,
					TerrainProfile.biome_density_at(Vector2(x, z), channel)
				)
		_expect(maximum_density > 0.45, "el canal ecológico %d debe contener hábitat" % channel)
	var report_file := FileAccess.open(
		"res://assets/environment/island_biome/world/island_world_report.json",
		FileAccess.READ
	)
	_expect(report_file != null, "debe existir el informe reproducible del mundo")
	if report_file != null:
		var report = JSON.parse_string(report_file.get_as_text())
		_expect(report is Dictionary, "el informe del mundo debe ser JSON válido")
		if report is Dictionary:
			var soil_patches: Dictionary = report.get("dominant_soil_patches", {})
			var terrain_detail: Dictionary = report.get("terrain_detail_maps", {})
			_expect(
				int(soil_patches.get("count", 0)) > 5000,
				"el suelo desnudo debe dividirse en parcelas orgánicas"
			)
			_expect(
				float(soil_patches.get("largest_hectares", 1.0)) < 0.07,
				"ninguna calva de suelo debe volver a formar un continente"
			)
			_expect(
				float(terrain_detail.get(
					"normal_pixels_over_20_degrees_percent", 0.0
				)) > 20.0,
				"la normal topográfica debe conservar cárcavas y laderas"
			)
			_expect(
				float(terrain_detail.get("ao_p01", 1.0)) < 0.70,
				"el AO debe oscurecer el fondo de los barrancos"
			)


func _test_unit_ground_following() -> void:
	var terrain_parent := Node3D.new()
	root.add_child(terrain_parent)
	var controller := UnitController.new()
	terrain_parent.add_child(controller)
	controller.set_process(false)
	controller.teleport(Vector2(-130.0, -250.0))
	var walk_animation := controller._animation_player.get_animation("Walk")
	_expect(
		walk_animation.get_meta("motion_reference", "")
			== VillagerWalkAnimation.MOTION_REFERENCE,
		"Walk debe provenir del ciclo CC0 de referencia"
	)
	_expect_near(
		walk_animation.length,
		VillagerWalkAnimation.LENGTH_SECONDS,
		0.0001,
		"Walk debe conservar las ocho fases del ciclo de referencia"
	)
	_expect(
		walk_animation.loop_mode == Animation.LOOP_LINEAR,
		"Walk debe repetirse mientras la unidad siga avanzando"
	)
	_expect(
		int(walk_animation.get_meta("motion_revision", 0))
			== VillagerWalkAnimation.MOTION_REVISION,
		"Walk debe usar la revisión con el eje sagital corregido"
	)
	_expect(
		controller._skeleton != null,
		"el controlador debe resolver el esqueleto del aldeano"
	)
	_expect(
		is_instance_valid(controller._left_foot_ik)
			and is_instance_valid(controller._right_foot_ik),
		"cada pierna debe recibir un TwoBoneIK3D de apoyo"
	)
	if (
		is_instance_valid(controller._left_foot_ik)
		and is_instance_valid(controller._right_foot_ik)
	):
		_expect(
			controller._left_foot_ik.get_root_bone_name(0) == "Thigh.L"
				and controller._left_foot_ik.get_middle_bone_name(0) == "Shin.L"
				and controller._left_foot_ik.get_end_bone_name(0) == "Foot.L",
			"el IK izquierdo debe resolver muslo, rodilla y pie"
		)
		_expect(
			controller._right_foot_ik.get_root_bone_name(0) == "Thigh.R"
				and controller._right_foot_ik.get_middle_bone_name(0) == "Shin.R"
				and controller._right_foot_ik.get_end_bone_name(0) == "Foot.R",
			"el IK derecho debe resolver muslo, rodilla y pie"
		)
		_expect(
			controller._foot_plant_driver.get_index()
				< controller._left_foot_ik.get_index()
				and controller._foot_plant_driver.get_index()
					< controller._right_foot_ik.get_index(),
			"el driver debe actualizar objetivos antes de resolver ambos IK"
		)
		_expect(
			controller._foot_orientation_lock.get_index()
				> controller._left_foot_ik.get_index()
				and controller._foot_orientation_lock.get_index()
					< controller._right_foot_ik.get_index(),
			"el bloqueo izquierdo debe ejecutarse despues de su IK y antes del derecho"
		)
	_test_reference_walk_tracks(controller, walk_animation)
	_test_forward_walk_geometry(controller, walk_animation)
	_test_horizontal_foot_plant(controller, walk_animation)
	controller._update_foot_ik(0.0)
	_expect(
		controller._left_foot_ik.get_influence() > 0.9
			and controller._right_foot_ik.get_influence() < 0.1,
		"el contacto izquierdo debe fijar el pie delantero"
	)
	controller.set_target(Vector2(120.0, 220.0))
	_expect(controller._current_animation == "Walk", "la marcha debe activar la animación Walk")
	controller._process(
		controller.walk_stride_m * 0.5 / controller.speed_mps
	)
	# En runtime lo ejecuta FootPlantDriver despues de AnimationPlayer. Esta
	# llamada explicita reproduce ese paso en la prueba determinista manual.
	controller._update_foot_ik(controller._current_walk_cycle_phase())
	_expect(
		controller._right_foot_ik.get_influence() > 0.9
			and controller._left_foot_ik.get_influence() < 0.1,
		"el contacto derecho debe completar el relevo del apoyo"
	)
	controller._update_foot_ik(0.4375)
	_expect_near(
		controller._right_foot_ik.get_influence()
			+ controller._left_foot_ik.get_influence(),
		1.0,
		0.001,
		"la transferencia debe mantener un apoyo combinado completo"
	)
	_expect(
		controller._left_foot_planted
			and not controller._right_foot_planted,
		"el pie entrante no debe anclarse horizontalmente antes del contacto"
	)
	_expect_near(
		controller._animation_player.speed_scale,
		controller.speed_mps * walk_animation.length
			/ controller.walk_stride_m,
		0.001,
		"la reproducción de Walk debe sincronizarse con la zancada recorrida"
	)
	var travel_test_steps := ceili(
		Vector2(controller.position.x, controller.position.z).distance_to(
			controller.target_xz
		) / controller.speed_mps * 60.0
	) + 120
	for iteration in range(travel_test_steps):
		controller._process(1.0 / 60.0)
		_expect(controller.ground_error_m() < 0.0001, "la unidad debe permanecer sobre el mapa de alturas")
		if not controller.has_target:
			break
	_expect(not controller.has_target, "la unidad debe alcanzar el destino")
	_expect(controller._current_animation == "Idle", "la llegada debe restaurar la animación Idle")
	_expect_near(
		controller._left_foot_ik.get_influence()
			+ controller._right_foot_ik.get_influence(),
		0.0,
		0.0001,
		"el IK de apoyo debe apagarse al quedar en Idle"
	)
	controller.set_target(Vector2.ZERO)
	controller.stop()
	_expect(not controller.has_target, "stop debe detener un desplazamiento activo")
	terrain_parent.queue_free()


func _test_reference_walk_tracks(
	controller: UnitController,
	walk: Animation
) -> void:
	for bone_name in [
		"Spine",
		"Chest",
		"Head",
		"LowerArm.L",
		"LowerArm.R",
		"Foot.L",
		"Foot.R",
	]:
		var track := _find_bone_track(
			walk,
			bone_name,
			Animation.TYPE_ROTATION_3D
		)
		_expect(
			track >= 0 and walk.track_get_key_count(track) == 9,
			"Walk debe animar %s en sus ocho fases" % bone_name
		)

	var left_knee_peak := _maximum_bone_x_rotation(
		controller._skeleton,
		walk,
		"Shin.L"
	)
	var right_knee_peak := _maximum_bone_x_rotation(
		controller._skeleton,
		walk,
		"Shin.R"
	)
	_expect(
		left_knee_peak >= 62.0 and right_knee_peak >= 62.0,
		"las rodillas deben superar 62 grados durante el paso"
	)
	var head_peak := _maximum_bone_rotation(
		controller._skeleton,
		walk,
		"Head"
	)
	_expect(
		head_peak >= 0.5 and head_peak <= 2.0,
		"la cabeza debe compensar sutilmente sin cabecear"
	)
	var left_arm_start := _bone_x_rotation_at_key(
		controller._skeleton,
		walk,
		"UpperArm.L",
		0
	)
	var right_arm_start := _bone_x_rotation_at_key(
		controller._skeleton,
		walk,
		"UpperArm.R",
		0
	)
	_expect(
		left_arm_start >= 12.0 and right_arm_start <= -12.0,
		"al contactar el pie izquierdo, el brazo derecho debe ir delante"
	)
	var left_thigh_start := _bone_x_rotation_at_key(
		controller._skeleton,
		walk,
		"Thigh.L",
		0
	)
	var right_thigh_start := _bone_x_rotation_at_key(
		controller._skeleton,
		walk,
		"Thigh.R",
		0
	)
	_expect(
		left_thigh_start <= -20.0 and right_thigh_start >= 16.0,
		"el contacto izquierdo debe colocar esa pierna delante, no detrás"
	)
	var root_track := _find_bone_track(
		walk,
		"Root",
		Animation.TYPE_POSITION_3D
	)
	_expect(root_track >= 0, "Walk debe incluir transferencia de peso en Root")
	if root_track >= 0:
		var minimum_y := INF
		var maximum_y := -INF
		var maximum_z := 0.0
		for key in range(walk.track_get_key_count(root_track)):
			var value: Vector3 = walk.track_get_key_value(root_track, key)
			minimum_y = minf(minimum_y, value.y)
			maximum_y = maxf(maximum_y, value.y)
			maximum_z = maxf(maximum_z, absf(value.z))
		_expect(
			maximum_y - minimum_y >= 0.025,
			"Root debe subir y bajar durante la marcha"
		)
		_expect(
			maximum_z < 0.0001,
			"el rebote de Root no debe desplazar al aldeano hacia delante"
		)


func _test_forward_walk_geometry(
	controller: UnitController,
	walk: Animation
) -> void:
	var player := controller._animation_player
	player.play("Walk", 0.0)
	player.advance(0.0)
	player.seek(0.0, true)
	player.advance(0.0)
	var left_contact := _bone_position_in_controller(controller, "Foot.L")
	var right_trailing := _bone_position_in_controller(controller, "Foot.R")
	var left_hand := _bone_position_in_controller(controller, "Hand.L")
	var right_hand := _bone_position_in_controller(controller, "Hand.R")
	_expect(
		-left_contact.z > -right_trailing.z + 0.5,
		"en contacto izquierdo, el pie izquierdo debe estar delante"
	)
	_expect(
		left_contact.y < right_trailing.y,
		"en contacto izquierdo, el pie derecho debe estar en salida/swing"
	)
	_expect(
		-right_hand.z > -left_hand.z + 0.3,
		"el brazo derecho debe contrapesar la pierna izquierda adelantada"
	)

	player.seek(walk.length * 0.25, true)
	player.advance(0.0)
	var left_stance := _bone_position_in_controller(controller, "Foot.L")
	var right_passing := _bone_position_in_controller(controller, "Foot.R")
	var early_stance_world_forward := (
		controller.walk_stride_m * 0.25 - left_stance.z
	)
	_expect_near(
		early_stance_world_forward,
		-left_contact.z,
		0.1,
		"el pie apoyado no debe patinar durante el apoyo temprano"
	)
	_expect(
		right_passing.y > left_stance.y + 0.2,
		"durante el paso derecho, la rodilla debe dar altura libre al pie"
	)

	player.seek(walk.length * 0.375, true)
	player.advance(0.0)
	var right_hip := _bone_position_in_controller(controller, "Thigh.R")
	var right_knee := _bone_position_in_controller(controller, "Shin.R")
	var left_late_stance := _bone_position_in_controller(
		controller, "Foot.L"
	)
	var inferred_stride := (
		(-left_contact.z) - (-left_late_stance.z)
	) / 0.375
	_expect_near(
		controller.walk_stride_m,
		inferred_stride,
		0.02,
		"la distancia del ciclo debe coincidir con la apertura completa del paso"
	)
	_expect(
		-right_knee.z > -right_hip.z + 0.18,
		"durante la elevación, la rodilla derecha debe proyectarse al frente"
	)

	player.seek(walk.length * 0.5, true)
	player.advance(0.0)
	var left_trailing := _bone_position_in_controller(controller, "Foot.L")
	var right_contact := _bone_position_in_controller(controller, "Foot.R")
	_expect(
		-right_contact.z > -left_trailing.z + 0.5,
		"el segundo contacto debe adelantar el pie derecho"
	)
	player.play("Idle", 0.0)
	player.advance(0.0)


func _bone_position_in_controller(
	controller: UnitController,
	bone_name: String
) -> Vector3:
	var skeleton := controller._skeleton
	var bone := skeleton.find_bone(bone_name)
	var world_position := skeleton.to_global(
		skeleton.get_bone_global_pose(bone).origin
	)
	return controller.to_local(world_position)


func _test_horizontal_foot_plant(
	controller: UnitController,
	walk: Animation
) -> void:
	var player := controller._animation_player
	var parent_3d := controller.get_parent() as Node3D
	controller._reset_foot_plants()
	player.play("Walk", 0.0)
	player.seek(0.0, true)
	player.advance(0.0)
	controller._update_foot_ik(0.0)
	var planted_target := parent_3d.to_local(
		controller._left_foot_target.global_position
	)
	var original_position := controller.position
	controller.position.z -= 0.75
	player.seek(walk.length * 0.25, true)
	player.advance(0.0)
	controller._update_foot_ik(0.25)
	var held_target := parent_3d.to_local(
		controller._left_foot_target.global_position
	)
	_expect_near(
		Vector2(held_target.x, held_target.z).distance_to(
			Vector2(planted_target.x, planted_target.z)
		),
		0.0,
		0.001,
		"el punto de apoyo de la suela debe quedar anclado al suelo"
	)
	_expect(
		controller._left_foot_planted,
		"el pie izquierdo debe permanecer marcado como plantado durante apoyo"
	)
	controller._update_foot_ik(0.5)
	_expect(
		not controller._left_foot_planted
			and controller._right_foot_planted,
		"el anclaje debe completar el relevo en el siguiente contacto"
	)
	controller.position = original_position
	controller._reset_foot_plants()
	controller._set_foot_ik_influence(0.0, 0.0)
	player.play("Idle", 0.0)
	player.advance(0.0)


func _find_bone_track(
	animation: Animation,
	bone_name: String,
	type: Animation.TrackType
) -> int:
	for track in range(animation.get_track_count()):
		if (
			animation.track_get_type(track) == type
			and String(animation.track_get_path(track)).ends_with(
				":%s" % bone_name
			)
		):
			return track
	return -1


func _bone_x_rotation_at_key(
	skeleton: Skeleton3D,
	animation: Animation,
	bone_name: String,
	key: int
) -> float:
	var track := _find_bone_track(
		animation,
		bone_name,
		Animation.TYPE_ROTATION_3D
	)
	if track < 0:
		return 0.0
	var bone := skeleton.find_bone(bone_name)
	var rest_rotation := (
		skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
	)
	var value: Quaternion = animation.track_get_key_value(track, key)
	var pose_rotation := rest_rotation.inverse() * value
	return rad_to_deg(
		Basis(pose_rotation).get_euler(EULER_ORDER_XYZ).x
	)


func _maximum_bone_x_rotation(
	skeleton: Skeleton3D,
	animation: Animation,
	bone_name: String
) -> float:
	var track := _find_bone_track(
		animation,
		bone_name,
		Animation.TYPE_ROTATION_3D
	)
	var maximum := 0.0
	if track < 0:
		return maximum
	for key in range(animation.track_get_key_count(track)):
		maximum = maxf(
			maximum,
			absf(_bone_x_rotation_at_key(
				skeleton,
				animation,
				bone_name,
				key
			))
		)
	return maximum


func _maximum_bone_rotation(
	skeleton: Skeleton3D,
	animation: Animation,
	bone_name: String
) -> float:
	var track := _find_bone_track(
		animation,
		bone_name,
		Animation.TYPE_ROTATION_3D
	)
	var maximum := 0.0
	if track < 0:
		return maximum
	var bone := skeleton.find_bone(bone_name)
	var rest_rotation := (
		skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
	)
	for key in range(animation.track_get_key_count(track)):
		var value: Quaternion = animation.track_get_key_value(track, key)
		var pose_rotation := rest_rotation.inverse() * value
		var euler := Basis(pose_rotation).get_euler(EULER_ORDER_XYZ)
		maximum = maxf(
			maximum,
			maxf(
				absf(rad_to_deg(euler.x)),
				maxf(
					absf(rad_to_deg(euler.y)),
					absf(rad_to_deg(euler.z))
				)
			)
		)
	return maximum


func _test_mesh_shape() -> void:
	var mesh := TerrainMeshBuilder.build()
	_expect(mesh.get_surface_count() == 1, "el terreno debe tener una superficie")
	var arrays := mesh.surface_get_arrays(0)
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
	var uv2s: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2]
	var expected_count := (TerrainMeshBuilder.WIDTH_SEGMENTS + 1) * (TerrainMeshBuilder.LENGTH_SEGMENTS + 1)
	_expect(vertices.size() == expected_count, "cantidad de vértices del terreno")
	_expect(vertices.size() > 35000, "la malla debe resolver crestas y canales del heightmap")
	_expect(
		tangents.size() == expected_count * 4,
		"cada vértice del terreno debe incluir tangente para normales PBR"
	)
	_expect(
		uv2s.size() == expected_count,
		"cada vértice debe incluir distancia de costa para mezclar los materiales"
	)
	var godot_front_normal := (
		vertices[indices[2]] - vertices[indices[0]]
	).cross(
		vertices[indices[1]] - vertices[indices[0]]
	).normalized()
	_expect(
		godot_front_normal.dot(Vector3.UP) > 0.9,
		"el frente horario del terreno debe ser visible desde arriba"
	)


func _test_web_preview_profile() -> void:
	var native_total := 0
	var web_total := 0
	for definition in ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS:
		native_total += ISLAND_BIOME_BUILDER.scaled_count(definition, 1.0)
		web_total += ISLAND_BIOME_BUILDER.scaled_count(
			definition,
			RUNTIME_PROFILE.WEB_BIOME_DENSITY_SCALE
		)
	_expect(
		native_total == 25060,
		"el perfil nativo debe conservar las 25.060 instancias"
	)
	_expect(
		web_total >= 6500 and web_total <= 7500,
		"el perfil Web debe limitar el bioma a unas 7.000 instancias"
	)
	_expect(
		RUNTIME_PROFILE.WEB_OCEAN_SUBDIVISIONS.x
			* RUNTIME_PROFILE.WEB_OCEAN_SUBDIVISIONS.y
			< RUNTIME_PROFILE.NATIVE_OCEAN_SUBDIVISIONS.x
				* RUNTIME_PROFILE.NATIVE_OCEAN_SUBDIVISIONS.y / 4,
		"el océano Web debe usar menos de un cuarto de la teselación nativa"
	)


func _test_island_biome_assets() -> void:
	var expected_total := 0
	for definition in ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS:
		expected_total += int(definition["count"])
		var packed := load(definition["path"]) as PackedScene
		_expect(
			packed != null,
			"el asset del bioma debe cargar: %s" % definition["path"]
		)
		if packed == null:
			continue
		var model := packed.instantiate()
		var meshes := model.find_children("*", "MeshInstance3D", true, false)
		_expect(
			meshes.size() == 1,
			"cada GLB de bioma debe exponer una sola malla instanciable"
		)
		if not meshes.is_empty():
			var triangle_count := 0
			var mesh := (meshes[0] as MeshInstance3D).mesh
			for surface_index in range(mesh.get_surface_count()):
				var arrays := mesh.surface_get_arrays(surface_index)
				var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
				var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
				triangle_count += (
					indices.size() / 3
					if not indices.is_empty()
					else vertices.size() / 3
				)
			_expect(
				triangle_count > 0 and triangle_count < 1200,
				"el prop %s debe respetar el presupuesto móvil" % definition["key"]
			)
		model.free()
	_expect(
		expected_total >= 24000,
		"la composición debe superar 24.000 instancias de vegetación y roca"
	)

	for material_name in ["grass", "soil", "sand"]:
		for map_name in ["albedo", "normal", "roughness"]:
			var texture_path := (
				"res://assets/environment/island_biome/textures/ground_%s_%s.png"
				% [material_name, map_name]
			)
			_expect(
				load(texture_path) is Texture2D,
				"debe cargar la textura PBR %s" % texture_path
			)

	var expected_layers: Array[String] = [
		"wet_sand", "dry_sand", "soil", "grass_green",
		"grass_dry", "rock", "litter", "pebbles",
	]
	_expect(
		TERRAIN_LAYER_LIBRARY.LAYER_NAMES == expected_layers,
		"el orden de capas debe coincidir exactamente con los dos splat maps"
	)
	for layer_index in range(expected_layers.size()):
		for map_name in ["albedo", "normal", "orm"]:
			var layer_path := TERRAIN_LAYER_LIBRARY.layer_path(layer_index, map_name)
			var layer_texture := load(layer_path) as Texture2D
			_expect(
				layer_texture != null,
				"debe cargar la capa 1K %s" % layer_path
			)
			if layer_texture != null:
				_expect(
					layer_texture.get_size() == Vector2(1024.0, 1024.0),
					"la capa debe conservar resolución 1K: %s" % layer_path
				)
		var orm_texture := load(
			TERRAIN_LAYER_LIBRARY.layer_path(layer_index, "orm")
		) as Texture2D
		if orm_texture != null:
			var orm_image := orm_texture.get_image()
			var minimum_height := 1.0
			var maximum_height := 0.0
			for sample_y in range(0, 1024, 128):
				for sample_x in range(0, 1024, 128):
					var height_sample := orm_image.get_pixel(sample_x, sample_y).r
					minimum_height = minf(minimum_height, height_sample)
					maximum_height = maxf(maximum_height, height_sample)
			_expect(
				maximum_height - minimum_height > 0.04,
				"el canal R del ORM debe contener altura útil en %s"
				% expected_layers[layer_index]
			)
	for shared_name in ["terrain_macro_noise.png", "terrain_detail_normal.png"]:
		_expect(
			load(
				"res://assets/environment/island_biome/textures/" + shared_name
			) is Texture2D,
			"debe cargar la textura compartida %s" % shared_name
		)

	for palm_map in ["albedo", "normal", "mask"]:
		var palm_texture_path := (
			"res://assets/environment/island_biome/textures/palms/"
			+ "palm_frond_atlas_%s_v1.png" % palm_map
		)
		var palm_texture := load(palm_texture_path) as Texture2D
		_expect(
			palm_texture != null,
			"debe cargar el mapa 2K de frondas %s" % palm_map
		)
		if palm_texture != null:
			_expect(
				palm_texture.get_size() == Vector2(2048.0, 2048.0),
				"el mapa de frondas debe conservar resolución 2K: %s"
				% palm_map
			)

	for shrub_map in ["albedo", "normal", "mask"]:
		var shrub_texture_path := (
			"res://assets/environment/island_biome/textures/shrubs/"
			+ "shrub_atlas_%s_v1.png" % shrub_map
		)
		var shrub_texture := load(shrub_texture_path) as Texture2D
		_expect(
			shrub_texture != null,
			"debe cargar el mapa 2K de arbustos %s" % shrub_map
		)
		if shrub_texture != null:
			_expect(
				shrub_texture.get_size() == Vector2(2048.0, 2048.0),
				"el mapa de arbustos debe conservar resolución 2K: %s"
				% shrub_map
			)
			var shrub_image := shrub_texture.get_image()
			_expect(
				shrub_image != null and shrub_image.has_mipmaps(),
				"el mapa de arbustos debe incluir mipmaps: %s" % shrub_map
			)

	var expected_palm_cards := {
		"res://assets/environment/island_biome/palms/palm_small.glb": 28,
		"res://assets/environment/island_biome/palms/palm_medium.glb": 32,
		"res://assets/environment/island_biome/palms/palm_tall.glb": 34,
	}
	for palm_path in expected_palm_cards:
		var palm_scene := load(palm_path) as PackedScene
		if palm_scene == null:
			continue
		var palm_model := palm_scene.instantiate()
		var palm_meshes := palm_model.find_children(
			"*", "MeshInstance3D", true, false
		)
		if palm_meshes.is_empty():
			palm_model.free()
			continue
		var palm_mesh := (palm_meshes[0] as MeshInstance3D).mesh
		var prepared_palm := ISLAND_BIOME_BUILDER._prepare_foliage_mesh(
			palm_mesh
		)
		var found_card_surface := false
		for surface_index in range(palm_mesh.get_surface_count()):
			var source_material := palm_mesh.surface_get_material(surface_index)
			if (
				source_material == null
				or "palm_frond_cards" not in source_material.resource_name.to_lower()
			):
				continue
			found_card_surface = true
			var arrays := palm_mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
			var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
			_expect(
				indices.size() == int(expected_palm_cards[palm_path]) * 24,
				"%s debe contener %d frond cards de ocho triángulos"
				% [palm_path, expected_palm_cards[palm_path]]
			)
			_expect(not uvs.is_empty(), "las frondas deben exportar UV0")
			_expect(not tangents.is_empty(), "las frondas deben exportar tangentes")
			var prepared_material := prepared_palm.surface_get_material(
				surface_index
			) as ShaderMaterial
			_expect(
				prepared_material != null
				and bool(prepared_material.get_shader_parameter("card_mode")),
				"Godot debe activar alpha-clip para %s" % palm_path
			)
		_expect(found_card_surface, "%s debe exponer una superficie de cards" % palm_path)
		palm_model.free()

	var expected_shrub_cards := {
		"res://assets/environment/island_biome/vegetation/shrub_dense.glb": 6,
		"res://assets/environment/island_biome/vegetation/shrub_wild.glb": 6,
	}
	for shrub_path in expected_shrub_cards:
		var shrub_scene := load(shrub_path) as PackedScene
		if shrub_scene == null:
			continue
		var shrub_model := shrub_scene.instantiate()
		var shrub_meshes := shrub_model.find_children(
			"*", "MeshInstance3D", true, false
		)
		if shrub_meshes.is_empty():
			shrub_model.free()
			continue
		var shrub_mesh := (shrub_meshes[0] as MeshInstance3D).mesh
		var prepared_shrub := ISLAND_BIOME_BUILDER._prepare_foliage_mesh(
			shrub_mesh
		)
		var found_shrub_cards := false
		for surface_index in range(shrub_mesh.get_surface_count()):
			var source_material := shrub_mesh.surface_get_material(surface_index)
			if (
				source_material == null
				or "shrub_foliage_cards"
					not in source_material.resource_name.to_lower()
			):
				continue
			found_shrub_cards = true
			var arrays := shrub_mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
			var tangents: PackedFloat32Array = arrays[Mesh.ARRAY_TANGENT]
			_expect(
				indices.size() == int(expected_shrub_cards[shrub_path]) * 12,
				"%s debe contener %d cards curvas de cuatro triángulos"
				% [shrub_path, expected_shrub_cards[shrub_path]]
			)
			_expect(not uvs.is_empty(), "los arbustos deben exportar UV0")
			_expect(not tangents.is_empty(), "los arbustos deben exportar tangentes")
			if not uvs.is_empty():
				var uv_min := Vector2(INF, INF)
				var uv_max := Vector2(-INF, -INF)
				for uv in uvs:
					uv_min = uv_min.min(uv)
					uv_max = uv_max.max(uv)
				_expect(
					uv_max.x - uv_min.x < 0.82,
					"las cards deben recortar el margen vacío 2:1 del atlas"
				)
			var prepared_material := prepared_shrub.surface_get_material(
				surface_index
			) as ShaderMaterial
			_expect(
				prepared_material != null
					and bool(prepared_material.get_shader_parameter("card_mode")),
				"Godot debe activar alpha-clip para %s" % shrub_path
			)
			if prepared_material != null:
				_expect(
					prepared_material.get_shader_parameter("albedo_texture")
						== load(ISLAND_BIOME_BUILDER.SHRUB_FOLIAGE_ALBEDO_PATH),
					"los arbustos deben usar el atlas RGBA compartido"
				)
				_expect_near(
					float(prepared_material.get_shader_parameter("alpha_cutoff")),
					0.31,
					0.0001,
					"alpha-clip suave del arbusto"
				)
		_expect(
			found_shrub_cards,
			"%s debe exponer una superficie de cards" % shrub_path
		)
		shrub_model.free()

	var empty_route: Array[Vector2] = []
	var all_instances_grounded := true
	var all_instances_upright := true
	var all_instances_in_habitat := true
	var tilted_rock_instances := 0
	for definition in ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS:
		var sample_definition: Dictionary = definition.duplicate(true)
		sample_definition["count"] = 48
		var generated: Array[Dictionary] = ISLAND_BIOME_BUILDER._generate_placements(
			sample_definition, empty_route
		)
		_expect(generated.size() == 48, "el campo debe poblar la familia %s" % definition["key"])
		for placement in generated:
			var transform: Transform3D = placement["transform"]
			var position_xz := Vector2(
				transform.origin.x,
				transform.origin.z
			)
			var ground_height := TerrainProfile.height_at(position_xz)
			var maximum_sink := (
				float(definition["sink"])
				* float(definition["scale_max"])
				* 1.13
				+ 0.01
			)
			all_instances_grounded = (
				all_instances_grounded
				and ground_height - transform.origin.y >= -0.0001
				and ground_height - transform.origin.y <= maximum_sink
			)
			if definition["kind"] != "rock":
				all_instances_upright = (
					all_instances_upright
					and transform.basis.y.normalized().dot(Vector3.UP) > 0.70
				)
			else:
				var ground_normal := TerrainProfile.normal_at(position_xz)
				var slope_aligned_up := Vector3.UP.slerp(
					ground_normal,
					float(definition["normal_alignment"])
				).normalized()
				if (
					transform.basis.y.normalized().dot(slope_aligned_up)
					< 0.999
				):
					tilted_rock_instances += 1
			all_instances_in_habitat = (
				all_instances_in_habitat
				and TerrainProfile.biome_density_at(
					position_xz, int(definition["density_channel"])
				) > 0.0
			)
		for first_index in range(generated.size()):
			for second_index in range(first_index + 1, generated.size()):
				var first: Transform3D = generated[first_index]["transform"]
				var second: Transform3D = generated[second_index]["transform"]
				_expect(
					Vector2(first.origin.x, first.origin.z).distance_to(
						Vector2(second.origin.x, second.origin.z)
					) >= float(definition["spacing"]) - 0.001,
					"el hash espacial debe respetar el Poisson de %s" % definition["key"]
				)
	_expect(
		all_instances_grounded,
		"los assets deben hundirse según su escala sin flotar"
	)
	_expect(
		all_instances_upright,
		"árboles y cobertura deben crecer verticales sin copiar toda la pendiente"
	)
	_expect(
		all_instances_in_habitat,
		"cada familia debe proceder del canal ecológico que le corresponde"
	)
	_expect(
		tilted_rock_instances > 100,
		"las rocas deben variar pitch y roll además de yaw y pendiente"
	)
	var deterministic_definition: Dictionary = ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS[0].duplicate(true)
	deterministic_definition["count"] = 32
	var first_pass: Array[Dictionary] = ISLAND_BIOME_BUILDER._generate_placements(
		deterministic_definition, empty_route
	)
	var second_pass: Array[Dictionary] = ISLAND_BIOME_BUILDER._generate_placements(
		deterministic_definition, empty_route
	)
	_expect(
		first_pass.size() == second_pass.size(),
		"el scatter debe ser determinista"
	)
	for index in range(first_pass.size()):
		var first_transform: Transform3D = first_pass[index]["transform"]
		var second_transform: Transform3D = second_pass[index]["transform"]
		_expect(
			first_transform.origin.distance_to(second_transform.origin) < 0.000001,
			"las semillas deben reproducir exactamente las posiciones"
		)


func _test_blender_character() -> void:
	var packed := load("res://assets/units/human_base.glb") as PackedScene
	_expect(packed != null, "el personaje Blender debe importarse como PackedScene")
	if packed == null:
		return
	var model := packed.instantiate()
	root.add_child(model)
	var players := model.find_children("*", "AnimationPlayer", true, false)
	_expect(not players.is_empty(), "el personaje debe contener AnimationPlayer")
	if not players.is_empty():
		var player := players[0] as AnimationPlayer
		_expect(player.has_animation("Idle"), "el personaje debe contener la animación Idle")
		_expect(player.has_animation("Walk"), "el personaje debe contener la animación Walk")
		_expect(player.has_animation("Attack"), "el personaje debe contener la animación Attack")
		if player.has_animation("Idle"):
			_expect(player.get_animation("Idle").length >= 1.9, "Idle debe incluir un ciclo respiratorio completo")
		if player.has_animation("Walk"):
			_expect(player.get_animation("Walk").length >= 0.9, "Walk debe incluir un ciclo de marcha completo")
		if player.has_animation("Attack"):
			_expect(player.get_animation("Attack").length >= 1.2, "Attack debe incluir preparación y recuperación")

	var minimum_y := INF
	var maximum_y := -INF
	var triangle_count := 0
	var material_count := 0
	var textured_material_count := 0
	var normal_mapped_material_count := 0
	var meshes := model.find_children("*", "MeshInstance3D", true, false)
	_expect(meshes.size() == 17, "el guardia debe conservar sus 17 adjuntos rígidos optimizados")
	for child in meshes:
		var mesh_instance := child as MeshInstance3D
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			material_count += 1
			var arrays := mesh_instance.mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var surface_vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			triangle_count += indices.size() / 3 if not indices.is_empty() else surface_vertices.size() / 3
			var active_material := mesh_instance.get_active_material(surface_index) as StandardMaterial3D
			if active_material != null and active_material.albedo_texture != null:
				textured_material_count += 1
			if active_material != null and active_material.normal_texture != null:
				normal_mapped_material_count += 1
		var box := mesh_instance.get_aabb()
		for x_index in range(2):
			for y_index in range(2):
				for z_index in range(2):
					var local_corner := box.position + Vector3(
						box.size.x * x_index,
						box.size.y * y_index,
						box.size.z * z_index
					)
					var world_corner := mesh_instance.global_transform * local_corner
					minimum_y = minf(minimum_y, world_corner.y)
					maximum_y = maxf(maximum_y, world_corner.y)
	var visible_height := maximum_y - minimum_y
	_expect(visible_height >= 1.75 and visible_height <= 1.85, "el modelo Blender debe medir aproximadamente 1,80 m")
	_expect(triangle_count >= 58000, "el asset héroe debe conservar su detalle geométrico")
	_expect(material_count >= 50, "el asset debe conservar sus capas de materiales PBR")
	_expect(textured_material_count >= 40, "los materiales principales deben conservar texturas embebidas")
	_expect(normal_mapped_material_count >= 40, "los materiales principales deben conservar mapas normales")
	model.queue_free()


func _test_villager_asset() -> void:
	var packed := load("res://assets/units/villager_trellis.glb") as PackedScene
	_expect(packed != null, "el aldeano TRELLIS debe importarse como PackedScene")
	if packed == null:
		return
	var model := packed.instantiate()
	root.add_child(model)

	var players := model.find_children("*", "AnimationPlayer", true, false)
	_expect(not players.is_empty(), "el aldeano debe contener AnimationPlayer")
	if not players.is_empty():
		var player := players[0] as AnimationPlayer
		for animation_name in ["Idle", "Walk", "Attack"]:
			_expect(
				player.has_animation(animation_name),
				"el aldeano debe contener la animación %s" % animation_name
			)
		if player.has_animation("Idle"):
			_expect(player.get_animation("Idle").length >= 1.9, "Idle del aldeano debe durar 2 s")
		if player.has_animation("Walk"):
			_expect(player.get_animation("Walk").length >= 0.9, "Walk del aldeano debe durar 1 s")
		if player.has_animation("Attack"):
			_expect(player.get_animation("Attack").length >= 1.2, "Attack del aldeano debe durar 1,25 s")

	var skeletons := model.find_children("*", "Skeleton3D", true, false)
	_expect(skeletons.size() == 1, "el aldeano debe conservar un esqueleto humanoide")
	if skeletons.size() == 1:
		var skeleton := skeletons[0] as Skeleton3D
		_expect(skeleton.get_bone_count() == 18, "el rig del aldeano debe tener 18 huesos")

	var minimum_y := INF
	var maximum_y := -INF
	var triangle_count := 0
	var textured_material_count := 0
	var normal_mapped_material_count := 0
	var ao_material_count := 0
	var meshes := model.find_children("*", "MeshInstance3D", true, false)
	_expect(meshes.size() == 1, "el LOD0 del aldeano debe ser una sola malla skinned")
	for child in meshes:
		var mesh_instance := child as MeshInstance3D
		for surface_index in range(mesh_instance.mesh.get_surface_count()):
			var arrays := mesh_instance.mesh.surface_get_arrays(surface_index)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			var surface_vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			triangle_count += indices.size() / 3 if not indices.is_empty() else surface_vertices.size() / 3
			var active_material := mesh_instance.get_active_material(surface_index) as StandardMaterial3D
			if active_material != null and active_material.albedo_texture != null:
				textured_material_count += 1
			if active_material != null and active_material.normal_texture != null:
				normal_mapped_material_count += 1
			if active_material != null and active_material.ao_texture != null:
				ao_material_count += 1
		var box := mesh_instance.get_aabb()
		for x_index in range(2):
			for y_index in range(2):
				for z_index in range(2):
					var local_corner := box.position + Vector3(
						box.size.x * x_index,
						box.size.y * y_index,
						box.size.z * z_index
					)
					var world_corner := mesh_instance.global_transform * local_corner
					minimum_y = minf(minimum_y, world_corner.y)
					maximum_y = maxf(maximum_y, world_corner.y)
	var visible_height := maximum_y - minimum_y
	_expect(
		visible_height >= 1.79 and visible_height <= 1.84,
		"el aldeano debe conservar su altura autoral de 1,82 m"
	)
	_expect(
		triangle_count >= 68000 and triangle_count <= 76000,
		"el aldeano debe respetar el presupuesto LOD0 de 72k triángulos"
	)
	_expect(textured_material_count >= 1, "el aldeano debe conservar BaseColor 2K")
	_expect(normal_mapped_material_count >= 1, "el aldeano debe conservar el normal bake 2K")
	_expect(ao_material_count >= 1, "el aldeano debe conservar ambient occlusion 2K")
	model.queue_free()

	var asset_scene := load("res://scenes/units/villager_asset.tscn") as PackedScene
	_expect(asset_scene != null, "debe existir la escena reutilizable del aldeano")
	if asset_scene != null:
		var asset_instance := asset_scene.instantiate()
		root.add_child(asset_instance)
		_expect(
			asset_instance.get_meta("_authored_forward_axis") == "+Z"
			and asset_instance.get_meta("_runtime_forward_axis") == "-Z",
			"la escena debe declarar la conversión de frente Blender/glTF a Godot"
		)
		var collisions := asset_instance.find_children("*", "CollisionShape3D", true, false)
		_expect(collisions.size() == 1, "la escena del aldeano debe incluir cápsula de selección")
		asset_instance.queue_free()


func _test_walking_showcase() -> void:
	var packed := load("res://scenes/main.tscn") as PackedScene
	_expect(packed != null, "la escena principal del paseo debe poder cargarse")
	if packed == null:
		return
	var showcase := packed.instantiate()
	root.add_child(showcase)
	var controller := showcase.get("unit") as UnitController
	var showcase_camera := showcase.get("camera") as Camera3D
	var showcase_ocean := showcase.get("ocean_instance") as MeshInstance3D
	var biome_counts: Dictionary = showcase.get("biome_counts")
	var showcase_environment := showcase.get("environment") as Environment
	var physical_table := showcase.get("physical_table") as MeshInstance3D
	var terrain_material := showcase.get("terrain_material") as ShaderMaterial
	var diorama_root := showcase.get("diorama_root") as Node3D
	var zoom_out_button := showcase.get("zoom_out_button") as Button
	var zoom_in_button := showcase.get("zoom_in_button") as Button
	var rotate_left_button := showcase.get("rotate_left_button") as Button
	var rotate_right_button := showcase.get("rotate_right_button") as Button
	var view_status_label := showcase.get("view_status_label") as Label
	_expect(controller != null, "el paisaje debe instanciar un controlador de aldeano")
	_expect(showcase_camera != null, "el paseo debe crear una cámara")
	_expect(showcase_ocean != null, "el paisaje debe incluir el océano alrededor de la isla")
	_expect(
		zoom_out_button != null
		and zoom_in_button != null
		and rotate_left_button != null
		and rotate_right_button != null,
		"el visor debe exponer controles de zoom y giro en ambos sentidos"
	)
	_expect(
		view_status_label != null and "Zoom 100%" in view_status_label.text,
		"el visor debe informar el nivel de zoom actual"
	)
	if showcase_ocean != null:
		_expect_near(
			showcase_ocean.position.y,
			TerrainProfile.SEA_LEVEL_M,
			0.000001,
			"nivel del océano"
		)
		var water_mesh := showcase_ocean.mesh as PlaneMesh
		_expect(
			water_mesh != null and water_mesh.subdivide_width >= 90,
			"el océano debe tener geometría para oleaje Gerstner"
		)
		var water_material := showcase_ocean.material_override as ShaderMaterial
		_expect(
			water_material != null
			and is_equal_approx(
				float(water_material.get_shader_parameter("foam_depth_m")),
				1.15
			),
			"la rompiente debe limitarse a 1,15 m de profundidad"
		)
	_expect(physical_table != null and not physical_table.visible, "la presentación no debe mostrar la mesa marrón")
	_expect(
		showcase_environment != null
		and showcase_environment.background_mode == Environment.BG_SKY
		and showcase_environment.fog_enabled,
		"la vista debe incluir cielo, reflexión y perspectiva atmosférica"
	)
	if terrain_material != null:
		for parameter in [
			"splat_a", "splat_b", "detail_map", "island_sdf",
			"terrain_normal", "terrain_ao", "macro_noise", "detail_normal",
		]:
			_expect(
				terrain_material.get_shader_parameter(parameter) is Texture2D,
				"el terreno debe recibir el mapa compartido %s" % parameter
			)
		for parameter in ["layer_albedo", "layer_normal", "layer_orm"]:
			var layer_array := (
				terrain_material.get_shader_parameter(parameter)
				as Texture2DArray
			)
			_expect(
				layer_array != null,
				"el terreno debe recibir Texture2DArray %s" % parameter
			)
			if layer_array != null:
				_expect(
					layer_array.get_layers() == 8
					and layer_array.get_width() == 1024
					and layer_array.get_height() == 1024,
					"el array %s debe contener ocho capas 1K" % parameter
				)
	_expect(
		biome_counts.size() == ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS.size(),
		"la escena principal debe integrar todas las familias del bioma"
	)
	var expected_total := 0
	for definition in ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS:
		expected_total += int(definition["count"])
	var actual_total := 0
	for count in biome_counts.values():
		actual_total += int(count)
	_expect(actual_total == expected_total, "el scatter debe completar las %d instancias" % expected_total)
	var biome_root := diorama_root.get_node_or_null("IslandBiome_DensityFields") as Node3D
	_expect(biome_root != null, "el paisaje debe crear el bioma gobernado por densidades")
	if biome_root != null:
		for child in biome_root.get_children():
			var instances := child as MultiMeshInstance3D
			_expect(instances != null, "cada familia debe usar MultiMesh")
			if instances != null:
				_expect(
					instances.multimesh.use_colors and instances.multimesh.use_custom_data,
					"cada MultiMesh debe guardar color, edad y fase de viento"
				)
				if instances.get_meta("kind") != "rock":
					var foliage_material := (
						instances.multimesh.mesh.surface_get_material(0)
						as ShaderMaterial
					)
					_expect(
						foliage_material != null,
						"el follaje debe consumir sus variaciones mediante shader GPU"
					)
					if foliage_material != null:
						_expect(
							foliage_material.get_shader_parameter("hue_ramp")
							is GradientTexture1D,
							"el follaje debe usar la LUT verde-amarillo-pardo"
						)
						_expect(
							not bool(foliage_material.get_shader_parameter("card_mode")),
							"las mallas sólidas actuales no deben fingirse como frond cards"
						)
				else:
					var rock_material := (
						instances.multimesh.mesh.surface_get_material(0)
						as StandardMaterial3D
					)
					_expect(
						rock_material != null
						and rock_material.uv1_triplanar
						and rock_material.normal_enabled
						and rock_material.normal_texture != null
						and rock_material.roughness_texture != null
						and rock_material.ao_texture != null,
						"las rocas deben usar StandardMaterial3D PBR triplanar"
					)
					if rock_material != null:
						_expect_near(
							rock_material.uv1_scale.x,
							0.55,
							0.0001,
							"escala triplanar de roca"
						)
	if controller != null:
		_expect(
			controller.character_asset_path == UnitController.DEFAULT_CHARACTER_PATH,
			"el paseo debe usar el aldeano TRELLIS por defecto"
		)
		_expect(controller.has_target, "el paseo automático debe arrancar al abrir la escena")
		_expect(
			showcase.get("_auto_walk_enabled"),
			"el trayecto hacia las rocas debe quedar activo por defecto"
		)
		_expect_near(
			controller._visual_root.scale.x,
			TerrainProfile.CHARACTER_RELATIVE_SCALE
				* float(showcase.CINEMATIC_CHARACTER_BOOST),
			0.0001,
			"el plano fijo debe mantener legible al aldeano en 1080p"
		)
		var initial_position := controller.position
		_expect(
			Vector2(initial_position.x, initial_position.z).distance_to(
				Vector2(-52.0, 288.0)
			) < 0.01,
			"el aldeano debe partir del extremo izquierdo de la isla"
		)
		if (
			showcase_camera != null
			and diorama_root != null
			and zoom_out_button != null
			and zoom_in_button != null
			and rotate_left_button != null
			and rotate_right_button != null
		):
			var base_camera_position := showcase_camera.global_position
			var view_pivot := diorama_root.global_position
			var base_camera_distance := base_camera_position.distance_to(view_pivot)
			zoom_in_button.pressed.emit()
			_expect(
				showcase_camera.global_position.distance_to(view_pivot)
					< base_camera_distance,
				"Acercar debe reducir la distancia al centro del diorama"
			)
			zoom_out_button.pressed.emit()
			_expect_near(
				showcase_camera.global_position.distance_to(view_pivot),
				base_camera_distance,
				0.0001,
				"Alejar debe recuperar la distancia anterior"
			)
			rotate_right_button.pressed.emit()
			_expect(
				showcase_camera.global_position.distance_to(base_camera_position)
					> 0.01,
				"Girar debe orbitar la cámara alrededor del eje vertical central"
			)
			_expect_near(
				showcase_camera.global_position.distance_to(view_pivot),
				base_camera_distance,
				0.0001,
				"el giro debe conservar la distancia al centro"
			)
			_expect_near(
				float(showcase.get("_viewer_yaw_rad")),
				float(showcase.VIEW_ROTATION_STEP_RAD),
				0.0001,
				"el botón de giro debe avanzar 15 grados"
			)
			rotate_left_button.pressed.emit()
			_expect_near(
				float(showcase.get("_viewer_yaw_rad")),
				0.0,
				0.0001,
				"los giros opuestos deben cancelarse"
			)
			var zoom_key := InputEventKey.new()
			zoom_key.pressed = true
			zoom_key.keycode = KEY_EQUAL
			_expect(
				bool(showcase.call("_handle_view_input", zoom_key)),
				"la tecla + debe activar el zoom"
			)
			_expect(
				float(showcase.get("_viewer_zoom")) < 1.0,
				"el atajo + debe acercar la vista"
			)
			showcase.call("_reset_view")
			_expect(
				showcase_camera.global_position.distance_to(base_camera_position)
					< 0.0001,
				"restaurar debe recuperar el encuadre base"
			)
		var initial_camera_position := showcase_camera.global_position
		var camera_inverse := showcase_camera.global_transform.affine_inverse()
		var start_in_camera: Vector3 = camera_inverse * showcase.calibration.simulation_to_world(
			Vector3(
				-52.0,
				TerrainProfile.height_at(Vector2(-52.0, 288.0)),
				288.0
			)
		)
		var destination_in_camera: Vector3 = (
			camera_inverse
			* showcase.calibration.simulation_to_world(Vector3(
				-22.0,
				TerrainProfile.height_at(Vector2(-22.0, 157.0)),
				157.0
			))
		)
		_expect(
			start_in_camera.x < destination_in_camera.x,
			"el plano fijo debe mostrar el paseo de izquierda a derecha"
		)
		for iteration in range(120):
			controller._process(1.0 / 60.0)
			showcase.call("_process", 1.0 / 60.0)
		_expect(
			controller.position.distance_to(initial_position)
				> controller.speed_mps * 1.8,
			"el aldeano debe avanzar por el paisaje durante la demostración"
		)
		_expect(
			showcase_camera.global_position.distance_to(
				initial_camera_position
			) < 0.0001,
			"el plano debe permanecer fijo mientras el aldeano cruza el terreno"
		)
		_expect(
			controller.ground_error_m() < 0.0001,
			"el paseo visible debe conservar los pies sobre el relieve"
		)
		var corrected_visual := controller._visual_root.get_node_or_null(
			"VillagerVisual"
		) as Node3D
		_expect(
			corrected_visual != null,
			"el paseo debe conservar el nodo visual orientado del aldeano"
		)
		if corrected_visual != null:
			# El frente autoral del GLB es +Z. Tras la corrección del asset y la
			# rotación del controlador, debe proyectarse hacia la derecha.
			var face_origin_screen := showcase_camera.unproject_position(
				corrected_visual.global_position
			)
			var authored_face_world := corrected_visual.global_basis.z.normalized()
			var face_direction_screen := showcase_camera.unproject_position(
				corrected_visual.global_position + authored_face_world * 0.05
			)
			_expect(
				face_direction_screen.x > face_origin_screen.x,
				"el rostro del aldeano debe mirar hacia la derecha de la pantalla"
			)
		var showcase_finish_steps := ceili(
			Vector2(controller.position.x, controller.position.z).distance_to(
				controller.target_xz
			) / controller.speed_mps * 60.0
		) + 120
		for iteration in range(showcase_finish_steps):
			controller._process(1.0 / 60.0)
			showcase.call("_process", 1.0 / 60.0)
			if not controller.has_target:
				break
		_expect(not controller.has_target, "el aldeano debe detenerse al llegar a las rocas")
		_expect(
			Vector2(controller.position.x, controller.position.z).distance_to(
				Vector2(-22.0, 157.0)
			) < 0.31,
			"el destino debe quedar frente al primer afloramiento central"
		)
		_expect(
			showcase.get("_journey_complete")
			and not showcase.get("_auto_walk_enabled"),
			"el trayecto debe terminar sin regresar al cabo"
		)
		_expect(
			controller._current_animation == "Idle",
			"el aldeano debe quedar quieto ante las rocas"
		)
	if controller != null and showcase_camera != null:
		var shot_distance := showcase_camera.global_position.distance_to(
			controller.global_position
		)
		_expect(
			shot_distance > 0.25 and shot_distance < 0.75,
			"el plano fijo debe abarcar el cabo y las rocas en un solo encuadre"
		)
	if biome_root != null:
		var outcrops := biome_root.get_node_or_null(
			"rock_outcrop"
		) as MultiMeshInstance3D
		_expect(outcrops != null, "el destino debe conservar el afloramiento central")
		# En headless, MultiMesh puede no conservar una copia legible de sus
		# transformaciones en CPU. Medimos la misma distribución determinista
		# que consume populate() para verificar la relación espacial real.
		var journey_route: Array[Vector2] = [
			Vector2(-52.0, 288.0),
			Vector2(-22.0, 157.0),
		]
		var generated_outcrops: Array[Dictionary] = []
		for definition in ISLAND_BIOME_BUILDER.ASSET_DEFINITIONS:
			if definition["key"] == "rock_outcrop":
				generated_outcrops = ISLAND_BIOME_BUILDER._generate_placements(
					definition, journey_route
				)
				break
		var destination := Vector2(-22.0, 157.0)
		var nearest_outcrop_distance := INF
		for placement in generated_outcrops:
			var transform: Transform3D = placement["transform"]
			nearest_outcrop_distance = minf(
				nearest_outcrop_distance,
				destination.distance_to(Vector2(
					transform.origin.x,
					transform.origin.z
				))
			)
		_expect(
			nearest_outcrop_distance > 5.0
				and nearest_outcrop_distance < 7.0,
			(
				"el aldeano debe parar a unos seis metros de la primera roca "
				+ "(distancia %.2f m)" % nearest_outcrop_distance
			)
		)
	showcase.queue_free()


func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)


func _expect_near(actual: float, expected: float, tolerance: float, message: String) -> void:
	if absf(actual - expected) > tolerance:
		failures.append("%s: esperado %.6f, recibido %.6f" % [message, expected, actual])
