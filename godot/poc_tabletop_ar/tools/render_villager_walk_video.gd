extends SceneTree

const FPS := 24.0
const START_HOLD_FRAMES := 12
const END_HOLD_FRAMES := 30
const WALK_CAPTURE_FRAMES := 895
const TOTAL_FRAMES := START_HOLD_FRAMES + WALK_CAPTURE_FRAMES + END_HOLD_FRAMES
const VIDEO_STREAM_HOST := "127.0.0.1"
const VIDEO_STREAM_PORT := 45821


func _initialize() -> void:
	# Congela agua y follaje para que el paisaje permanezca inmóvil y para que
	# los tramos renderizados sean visualmente continuos.
	Engine.time_scale = 0.0
	call_deferred("_render_video")


func _render_video() -> void:
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
	scene.set_process(false)
	controller.set_process(false)
	var animation_player := controller._animation_player as AnimationPlayer
	if animation_player != null:
		animation_player.process_mode = Node.PROCESS_MODE_DISABLED

	for frame in range(5):
		await process_frame
	RenderingServer.force_sync()

	var segment_start := clampi(
		int(OS.get_environment("VIDEO_SEGMENT_START")), 0, TOTAL_FRAMES
	)
	var requested_count := int(OS.get_environment("VIDEO_SEGMENT_COUNT"))
	var segment_count := (
		requested_count
		if requested_count > 0
		else TOTAL_FRAMES - segment_start
	)
	segment_count = mini(segment_count, TOTAL_FRAMES - segment_start)
	for global_frame in range(segment_start):
		_advance_timeline(controller, animation_player, global_frame)
	await process_frame
	RenderingServer.force_sync()
	print(
		"VILLAGER_VIDEO_SEGMENT_READY=",
		segment_start,
		"+",
		segment_count
	)

	var video_stream := StreamPeerTCP.new()
	for attempt in range(600):
		if video_stream.get_status() == StreamPeerTCP.STATUS_NONE:
			var connect_error := video_stream.connect_to_host(
				VIDEO_STREAM_HOST, VIDEO_STREAM_PORT
			)
			if connect_error != OK:
				video_stream = StreamPeerTCP.new()
				await process_frame
				continue
		video_stream.poll()
		if video_stream.get_status() == StreamPeerTCP.STATUS_CONNECTED:
			break
		if video_stream.get_status() == StreamPeerTCP.STATUS_ERROR:
			video_stream = StreamPeerTCP.new()
		await process_frame
	if video_stream.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		push_error("FFmpeg no aceptó la conexión de video")
		quit(1)
		return
	video_stream.set_no_delay(true)

	var frame_count := 0
	for global_frame in range(segment_start, segment_start + segment_count):
		_advance_timeline(controller, animation_player, global_frame)
		await process_frame
		if not _write_frame(video_stream):
			video_stream.disconnect_from_host()
			quit(1)
			return
		frame_count += 1

	video_stream.disconnect_from_host()
	print(
		"VILLAGER_VIDEO_SEGMENT_OK=",
		segment_start,
		"+",
		frame_count
	)
	quit(0)


func _advance_timeline(
	controller: UnitController,
	animation_player: AnimationPlayer,
	global_frame: int
) -> void:
	if global_frame < START_HOLD_FRAMES:
		return
	if controller.has_target:
		controller._process(1.0 / FPS)
	if animation_player != null:
		animation_player.advance(1.0 / FPS)


func _write_frame(video_stream: StreamPeerTCP) -> bool:
	var image := root.get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		push_error("El renderer no devolvió imagen")
		return false
	if image.get_format() != Image.FORMAT_RGBA8:
		image.convert(Image.FORMAT_RGBA8)
	if image.get_width() != 1920 or image.get_height() != 1080:
		push_error("Resolución inesperada: %sx%s" % [image.get_width(), image.get_height()])
		return false
	var frame_data := image.get_data()
	var write_error := video_stream.put_data(frame_data)
	frame_data.clear()
	if write_error != OK:
		push_error("No se pudo enviar un fotograma a FFmpeg: %s" % error_string(write_error))
		return false
	return true
