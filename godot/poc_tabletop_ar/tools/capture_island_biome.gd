extends SceneTree

const OVERVIEW_PATH := "res://previews/island_biome/in_game_landscape.png"
const CLOSEUP_PATH := "res://previews/island_biome/in_game_closeup.png"


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var packed := load("res://scenes/main.tscn") as PackedScene
	if packed == null:
		push_error("No se pudo cargar la escena principal")
		quit(1)
		return
	var scene := packed.instantiate()
	root.add_child(scene)
	await process_frame
	scene.call("_set_desktop_camera_mode", 1)
	var interface := scene.get_node_or_null("Interface") as CanvasLayer
	if interface != null:
		interface.visible = false
	for frame in range(4):
		await process_frame
	RenderingServer.force_sync()
	await process_frame
	if not _save_viewport(OVERVIEW_PATH):
		quit(1)
		return

	var camera := scene.get("camera") as Camera3D
	var calibration := scene.get("calibration") as TabletopCalibration
	var focus_xz := Vector2(78.0, 238.0)
	var focus := calibration.simulation_to_world(Vector3(
		focus_xz.x,
		TerrainProfile.height_at(focus_xz),
		focus_xz.y
	))
	camera.fov = 43.0
	camera.global_position = focus + Vector3(0.23, 0.17, 0.27)
	camera.look_at(focus + Vector3.UP * 0.012, Vector3.UP)
	for frame in range(3):
		await process_frame
	RenderingServer.force_sync()
	await process_frame
	if not _save_viewport(CLOSEUP_PATH):
		quit(1)
		return
	print("ISLAND_BIOME_CAPTURE_OK=", ProjectSettings.globalize_path(OVERVIEW_PATH))
	print("ISLAND_BIOME_CLOSEUP_OK=", ProjectSettings.globalize_path(CLOSEUP_PATH))
	quit(0)


func _save_viewport(output_path: String) -> bool:
	var image := root.get_viewport().get_texture().get_image()
	if image.is_empty():
		push_error("El renderer no devolvio una imagen")
		return false
	var absolute_path := ProjectSettings.globalize_path(output_path)
	var result := image.save_png(absolute_path)
	if result != OK:
		push_error("No se pudo guardar la captura: %s" % error_string(result))
		return false
	return true
