extends SceneTree

const OUTPUT_DIRECTORY := "res://previews/villager_trellis/walk_cycle"
const REVIEW_PHASES := [
	["01_left_contact", 0.0],
	["02_left_down", 0.125],
	["03_right_passing", 0.25],
	["04_right_up", 0.375],
	["05_right_contact", 0.5],
	["06_right_down", 0.625],
	["07_left_passing", 0.75],
	["08_left_up", 0.875],
]


func _initialize() -> void:
	call_deferred("_capture")


func _capture() -> void:
	var viewport := root.get_viewport()
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.positional_shadow_atlas_size = 4096
	RenderingServer.directional_shadow_atlas_set_size(4096, true)

	var packed := load("res://scenes/main.tscn") as PackedScene
	if packed == null:
		push_error("No se pudo cargar la escena principal")
		quit(1)
		return
	var scene := packed.instantiate()
	root.add_child(scene)
	var controller := scene.get("unit") as UnitController
	var interface := scene.get_node_or_null("Interface") as CanvasLayer
	if interface != null:
		interface.visible = false
	for frame in range(4):
		await process_frame
	if controller == null or controller._animation_player == null:
		push_error("No se encontró el aldeano animado")
		quit(1)
		return

	scene.set_process(false)
	controller.set_process(false)
	var player := controller._animation_player
	player.process_mode = Node.PROCESS_MODE_DISABLED
	# Move far enough into the shot that the character is fully readable.
	for frame in range(96):
		controller._process(1.0 / 24.0)
		player.advance(1.0 / 24.0)
	_prepare_close_up(scene, controller)
	var walk := player.get_animation("Walk")
	var output_path := ProjectSettings.globalize_path(OUTPUT_DIRECTORY)
	DirAccess.make_dir_recursive_absolute(output_path)

	for phase_definition in REVIEW_PHASES:
		var label := String(phase_definition[0])
		var phase := float(phase_definition[1])
		player.seek(phase * walk.length, true)
		controller._update_foot_ik(phase)
		await process_frame
		RenderingServer.force_sync()
		var image := viewport.get_texture().get_image()
		if image == null or image.is_empty():
			push_error("El renderer no devolvió imagen para %s" % label)
			quit(1)
			return
		var phase_path := output_path.path_join("%s.png" % label)
		var save_error := image.save_png(phase_path)
		if save_error != OK:
			push_error("No se pudo guardar %s: %s" % [
				phase_path,
				error_string(save_error),
			])
			quit(1)
			return
		print("VILLAGER_WALK_PHASE=", phase_path)
	print("VILLAGER_WALK_PHASES_OK=", output_path)
	quit(0)


func _prepare_close_up(scene: Node3D, controller: UnitController) -> void:
	# This capture is an animation review plate, not a beauty shot. Remove the
	# biome clutter so knees, feet, arms, and head remain legible in every phase.
	var diorama_root := scene.get("diorama_root") as Node3D
	if diorama_root != null:
		for child in diorama_root.get_children():
			if child != controller and child is Node3D:
				(child as Node3D).visible = false

		var review_ground := MeshInstance3D.new()
		review_ground.name = "WalkReviewGround"
		var ground_mesh := PlaneMesh.new()
		ground_mesh.size = Vector2(18.0, 18.0)
		review_ground.mesh = ground_mesh
		review_ground.position = Vector3(
			controller.position.x,
			TerrainProfile.height_at(Vector2(
				controller.position.x,
				controller.position.z
			)),
			controller.position.z
		)
		var ground_material := StandardMaterial3D.new()
		ground_material.albedo_color = Color("7b806f")
		ground_material.roughness = 0.94
		review_ground.material_override = ground_material
		diorama_root.add_child(review_ground)

	var camera := scene.get("camera") as Camera3D
	if camera == null:
		return
	var character_origin := controller.global_position
	var walk_forward := -controller.global_transform.basis.z.normalized()
	var walk_side := walk_forward.cross(Vector3.UP).normalized()
	var look_target := character_origin + Vector3.UP * 0.0105
	camera.fov = 26.0
	camera.near = 0.002
	camera.global_position = (
		look_target
		- walk_forward * 0.004
		+ walk_side * 0.058
		+ Vector3.UP * 0.003
	)
	camera.look_at(look_target, Vector3.UP)
