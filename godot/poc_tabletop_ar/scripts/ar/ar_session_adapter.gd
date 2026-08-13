class_name ArSessionAdapter
extends Node

signal frame_ready(frame: Variant, camera: Variant)
signal status_changed(message: String)
signal plane_count_changed(count: int)
signal mesh_count_changed(count: int)

const PLANE_HORIZONTAL := 1
const SCENE_MESH_WITH_CLASSIFICATION := 3
const RUN_RESET_AND_REMOVE_ANCHORS := 3
const RAYCAST_EXISTING_PLANE_GEOMETRY := 1
const RAYCAST_ESTIMATED_PLANE := 3
const ALIGNMENT_HORIZONTAL := 0

var _session: Variant
var _configuration: Variant
var _latest_camera: Variant
var _plane_ids := {}
var _mesh_ids := {}
var _running := false


func is_available() -> bool:
	return (
		OS.get_name() == "iOS"
		and ClassDB.class_exists(&"ARSession")
		and ClassDB.class_exists(&"ARWorldTrackingConfiguration")
	)


func start() -> bool:
	if not is_available():
		status_changed.emit("ARKit no está disponible; usando simulador")
		return false

	_session = ClassDB.instantiate(&"ARSession")
	_configuration = ClassDB.instantiate(&"ARWorldTrackingConfiguration")
	if _session == null or _configuration == null:
		status_changed.emit("No fue posible crear la sesión ARKit")
		return false

	_configuration.set("world_alignment", 0)
	_configuration.set("plane_detection_mask", PLANE_HORIZONTAL)
	_configuration.set("scene_reconstruction", SCENE_MESH_WITH_CLASSIFICATION)
	_configuration.set("is_light_estimation_enabled", true)

	_connect_if_present(&"frame_updated", _on_frame_updated)
	_connect_if_present(&"anchors_added", _on_anchors_added)
	_connect_if_present(&"anchors_updated", _on_anchors_updated)
	_connect_if_present(&"anchors_removed", _on_anchors_removed)
	_connect_if_present(&"mesh_anchor_added", _on_mesh_added)
	_connect_if_present(&"mesh_anchor_updated", _on_mesh_updated)
	_connect_if_present(&"mesh_anchor_removed", _on_mesh_removed)
	_connect_if_present(&"session_failed", _on_session_failed)
	_connect_if_present(&"session_interrupted", _on_session_interrupted)
	_connect_if_present(&"interruption_ended", _on_interruption_ended)

	_session.call("run", _configuration, RUN_RESET_AND_REMOVE_ANCHORS)
	_running = true
	status_changed.emit("ARKit inicializando: mueve lentamente el iPhone")
	return true


func stop() -> void:
	if _running and _session != null:
		_session.call("pause")
	_running = false


func current_camera_transform() -> Transform3D:
	if _latest_camera == null:
		return Transform3D.IDENTITY
	return _latest_camera.get("transform") as Transform3D


func raycast_from_camera_center() -> Dictionary:
	if not _running or _session == null or _latest_camera == null:
		return {"ok": false, "reason": "No hay un cuadro AR válido"}
	if not ClassDB.class_exists(&"ARRaycastQuery"):
		return {"ok": false, "reason": "El complemento no expone ARRaycastQuery"}

	var camera_transform := current_camera_transform()
	var origin := camera_transform.origin
	var direction := -camera_transform.basis.z.normalized()
	var hit: Variant = _perform_raycast(origin, direction, RAYCAST_EXISTING_PLANE_GEOMETRY)
	if hit == null:
		hit = _perform_raycast(origin, direction, RAYCAST_ESTIMATED_PLANE)
	if hit == null:
		return {"ok": false, "reason": "No se encontró una superficie horizontal"}
	return {"ok": true, "position": hit.origin, "transform": hit}


func _perform_raycast(origin: Vector3, direction: Vector3, target: int) -> Variant:
	var query: Variant = ClassDB.instantiate(&"ARRaycastQuery")
	if query == null:
		return null
	query.set("origin", origin)
	query.set("direction", direction)
	query.set("target", target)
	query.set("target_alignment", ALIGNMENT_HORIZONTAL)
	var results: Variant = _session.call("raycast", query)
	if typeof(results) != TYPE_ARRAY or results.is_empty():
		return null
	var first: Variant = results[0]
	if first == null:
		return null
	return first.get("world_transform") as Transform3D


func _connect_if_present(signal_name: StringName, callback: Callable) -> void:
	if _session.has_signal(signal_name):
		_session.connect(signal_name, callback)


func _on_frame_updated(frame: Variant) -> void:
	if frame == null:
		return
	_latest_camera = frame.get("camera")
	if _latest_camera != null:
		var tracking_state: int = _latest_camera.get("tracking_state")
		if tracking_state == 2:
			status_changed.emit("Seguimiento AR normal")
		elif tracking_state == 1:
			status_changed.emit("Seguimiento AR limitado")
	frame_ready.emit(frame, _latest_camera)


func _on_anchors_added(anchors: Array) -> void:
	_update_plane_set(anchors, true)


func _on_anchors_updated(anchors: Array) -> void:
	_update_plane_set(anchors, true)


func _on_anchors_removed(anchors: Array) -> void:
	_update_plane_set(anchors, false)


func _update_plane_set(anchors: Array, present: bool) -> void:
	for anchor in anchors:
		if anchor == null or anchor.get_class() != "ARPlaneAnchor":
			continue
		var identifier: String = anchor.get("identifier")
		if present:
			_plane_ids[identifier] = true
		else:
			_plane_ids.erase(identifier)
	plane_count_changed.emit(_plane_ids.size())


func _on_mesh_added(mesh: Variant) -> void:
	_set_mesh_presence(mesh, true)


func _on_mesh_updated(mesh: Variant) -> void:
	_set_mesh_presence(mesh, true)


func _on_mesh_removed(mesh: Variant) -> void:
	_set_mesh_presence(mesh, false)


func _set_mesh_presence(mesh: Variant, present: bool) -> void:
	if mesh == null:
		return
	var identifier: String = mesh.get("identifier")
	if present:
		_mesh_ids[identifier] = true
	else:
		_mesh_ids.erase(identifier)
	mesh_count_changed.emit(_mesh_ids.size())


func _on_session_failed(message: String) -> void:
	status_changed.emit("ARKit falló: %s" % message)


func _on_session_interrupted() -> void:
	status_changed.emit("Sesión AR interrumpida")


func _on_interruption_ended() -> void:
	status_changed.emit("Sesión AR reanudada")
