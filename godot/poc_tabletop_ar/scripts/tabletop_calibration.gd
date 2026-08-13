class_name TabletopCalibration
extends RefCounted

## Convención vista desde un solo lado de la mesa:
## 0 frente-izquierda, 1 frente-derecha, 2 fondo-derecha, 3 fondo-izquierda.

const EXPECTED_WIDTH_M := 1.0
const EXPECTED_LENGTH_M := 1.8
const MAX_PLANAR_ERROR_M := 0.025

var corners_world := PackedVector3Array()
var table_transform := Transform3D.IDENTITY
var measured_width_m := 0.0
var measured_length_m := 0.0
var planar_error_m := 0.0
var is_valid := false
var validation_message := "Sin calibrar"


func clear() -> void:
	corners_world.clear()
	table_transform = Transform3D.IDENTITY
	measured_width_m = 0.0
	measured_length_m = 0.0
	planar_error_m = 0.0
	is_valid = false
	validation_message = "Sin calibrar"


func set_corners(points: PackedVector3Array) -> bool:
	clear()
	if points.size() != 4:
		validation_message = "Se necesitan exactamente cuatro esquinas"
		return false

	for point in points:
		corners_world.append(point)

	var edge_front := points[1] - points[0]
	var edge_back := points[2] - points[3]
	var edge_left := points[3] - points[0]
	var edge_right := points[2] - points[1]
	measured_width_m = (edge_front.length() + edge_back.length()) * 0.5
	measured_length_m = (edge_left.length() + edge_right.length()) * 0.5

	if measured_width_m < 0.25 or measured_length_m < 0.25:
		validation_message = "Las esquinas están demasiado cerca"
		return false

	var x_axis := (edge_front + edge_back).normalized()
	var z_hint := (edge_left + edge_right).normalized()
	var y_axis := z_hint.cross(x_axis).normalized()
	if y_axis.length_squared() < 0.9:
		validation_message = "Las esquinas no forman dos ejes distinguibles"
		return false
	if y_axis.dot(Vector3.UP) < 0.0:
		y_axis = -y_axis

	# Reortogonaliza para que la imprecisión de los toques no deforme la malla.
	var z_axis := x_axis.cross(y_axis).normalized()
	x_axis = y_axis.cross(z_axis).normalized()
	var center := (points[0] + points[1] + points[2] + points[3]) * 0.25

	planar_error_m = 0.0
	for point in points:
		planar_error_m = maxf(planar_error_m, absf((point - center).dot(y_axis)))

	var scale_x := measured_width_m / TerrainProfile.WIDTH_M
	var scale_z := measured_length_m / TerrainProfile.LENGTH_M
	var basis := Basis(
		x_axis * scale_x,
		y_axis * TerrainProfile.TERRAIN_PRESENTATION_SCALE,
		z_axis * scale_z
	)
	table_transform = Transform3D(basis, center)
	is_valid = planar_error_m <= MAX_PLANAR_ERROR_M
	validation_message = (
		"Calibración válida"
		if is_valid
		else "Las cuatro esquinas no están en el mismo plano"
	)
	return is_valid


func set_exact_simulation_table() -> void:
	set_corners(PackedVector3Array([
		Vector3(-EXPECTED_WIDTH_M * 0.5, 0.0, -EXPECTED_LENGTH_M * 0.5),
		Vector3(EXPECTED_WIDTH_M * 0.5, 0.0, -EXPECTED_LENGTH_M * 0.5),
		Vector3(EXPECTED_WIDTH_M * 0.5, 0.0, EXPECTED_LENGTH_M * 0.5),
		Vector3(-EXPECTED_WIDTH_M * 0.5, 0.0, EXPECTED_LENGTH_M * 0.5),
	]))


func simulation_to_world(simulation_position: Vector3) -> Vector3:
	return table_transform * simulation_position


func world_to_simulation(world_position: Vector3) -> Vector3:
	return table_transform.affine_inverse() * world_position


func width_error_m() -> float:
	return absf(measured_width_m - EXPECTED_WIDTH_M)


func length_error_m() -> float:
	return absf(measured_length_m - EXPECTED_LENGTH_M)
