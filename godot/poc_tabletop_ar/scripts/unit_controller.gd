class_name UnitController
extends Node3D

signal target_reached

const DEFAULT_CHARACTER_PATH := "res://scenes/units/villager_asset.tscn"
const LEGACY_CHARACTER_PATH := "res://assets/units/human_base.glb"
const VILLAGER_FORWARD_CORRECTION_RAD := PI

@export var speed_mps := 3.6
@export var foot_offset_m := 0.08
@export var turn_speed_rad_per_s := 7.5
@export var walk_animation_speed := 1.0
@export var walk_stride_m := 3.34
@export var enable_foot_ik := true
@export_range(0.0, 1.0, 0.05) var foot_ik_influence := 1.0
@export var foot_ik_pole_distance_m := 0.9
@export_file("*.tscn", "*.glb") var character_asset_path := DEFAULT_CHARACTER_PATH

var target_xz := Vector2.ZERO
var has_target := false
var distance_walked_m := 0.0
var _walk_phase := 0.0
var _walk_cycle_start_distance_m := 0.0
var _visual_root: Node3D
var _left_leg: Node3D
var _right_leg: Node3D
var _animation_player: AnimationPlayer
var _skeleton: Skeleton3D
var _left_foot_ik: TwoBoneIK3D
var _right_foot_ik: TwoBoneIK3D
var _left_foot_target: Marker3D
var _right_foot_target: Marker3D
var _left_knee_pole: Marker3D
var _right_knee_pole: Marker3D
var _foot_plant_driver: VillagerFootPlantDriver
var _foot_orientation_lock: VillagerFootOrientationLock
var _left_foot_contact_basis := Basis.IDENTITY
var _right_foot_contact_basis := Basis.IDENTITY
var _left_foot_plant_xz := Vector2.ZERO
var _right_foot_plant_xz := Vector2.ZERO
var _left_foot_planted := false
var _right_foot_planted := false
var _current_animation := ""


func _ready() -> void:
	_build_visual()
	_snap_to_ground()


func set_target(new_target_xz: Vector2) -> void:
	if not has_target:
		_walk_cycle_start_distance_m = distance_walked_m
		_reset_foot_plants()
	target_xz = TerrainProfile.clamp_to_bounds(new_target_xz, 4.0)
	has_target = true
	_play_animation("Walk")


func teleport(new_position_xz: Vector2) -> void:
	var clamped := TerrainProfile.clamp_to_bounds(new_position_xz, 4.0)
	position = Vector3(clamped.x, TerrainProfile.height_at(clamped) + foot_offset_m, clamped.y)
	target_xz = clamped
	has_target = false
	_reset_foot_plants()
	_set_foot_ik_influence(0.0, 0.0)
	_play_animation("Idle")


func stop() -> void:
	target_xz = Vector2(position.x, position.z)
	has_target = false
	_set_leg_swing(0.0)
	_reset_foot_plants()
	_set_foot_ik_influence(0.0, 0.0)
	_play_animation("Idle")


func _process(delta: float) -> void:
	if not has_target:
		_set_leg_swing(0.0)
		_reset_foot_plants()
		_set_foot_ik_influence(0.0, 0.0)
		_play_animation("Idle")
		return

	var current_xz := Vector2(position.x, position.z)
	var to_target := target_xz - current_xz
	var remaining := to_target.length()
	if remaining <= 0.3:
		has_target = false
		_set_leg_swing(0.0)
		_reset_foot_plants()
		_set_foot_ik_influence(0.0, 0.0)
		_play_animation("Idle")
		target_reached.emit()
		return

	var step_distance := minf(speed_mps * delta, remaining)
	var direction := to_target / remaining
	var next_xz := current_xz + direction * step_distance
	position = Vector3(
		next_xz.x,
		TerrainProfile.height_at(next_xz) + foot_offset_m,
		next_xz.y
	)
	distance_walked_m += step_distance
	var cycle_phase := fposmod(
		(distance_walked_m - _walk_cycle_start_distance_m)
			/ maxf(walk_stride_m, 0.001),
		1.0
	)
	_walk_phase = cycle_phase * TAU
	var target_yaw := atan2(-direction.x, -direction.y)
	rotation.y = rotate_toward(
		rotation.y,
		target_yaw,
		turn_speed_rad_per_s * delta
	)
	_set_leg_swing(sin(_walk_phase) * 0.42)
	_play_animation("Walk")


func play_attack() -> void:
	_play_animation("Attack", true)


func ground_error_m() -> float:
	var current_xz := Vector2(position.x, position.z)
	return absf(position.y - foot_offset_m - TerrainProfile.height_at(current_xz))


func _snap_to_ground() -> void:
	var current_xz := Vector2(position.x, position.z)
	position.y = TerrainProfile.height_at(current_xz) + foot_offset_m


func _set_leg_swing(angle: float) -> void:
	if is_instance_valid(_left_leg):
		_left_leg.rotation.x = angle
	if is_instance_valid(_right_leg):
		_right_leg.rotation.x = -angle


func _build_visual() -> void:
	_visual_root = Node3D.new()
	_visual_root.name = "VisualAtScale1To180"
	_visual_root.scale = Vector3.ONE * TerrainProfile.CHARACTER_RELATIVE_SCALE
	add_child(_visual_root)

	var candidate_paths := [character_asset_path, LEGACY_CHARACTER_PATH]
	for candidate_path in candidate_paths:
		if not ResourceLoader.exists(candidate_path):
			continue
		var packed := load(candidate_path) as PackedScene
		if packed != null:
			var blender_model := packed.instantiate()
			blender_model.name = "VillagerVisual"
			# El aldeano fue autorado mirando hacia -Y en Blender. La conversión
			# glTF Y-up deja su frente visual en +Z, opuesto al frente -Z de
			# Godot; corregimos el contenedor completo, incluido su rig.
			if candidate_path == DEFAULT_CHARACTER_PATH:
				blender_model.rotation.y = VILLAGER_FORWARD_CORRECTION_RAD
			_visual_root.add_child(blender_model)
			_animation_player = blender_model.find_child(
				"AnimationPlayer", true, false
			) as AnimationPlayer
			var skeletons := blender_model.find_children(
				"*", "Skeleton3D", true, false
			)
			if not skeletons.is_empty():
				_skeleton = skeletons[0] as Skeleton3D
				if candidate_path == DEFAULT_CHARACTER_PATH:
					VillagerWalkAnimation.install(
						_animation_player,
						_skeleton
					)
				_configure_foot_ik()
			_configure_looping_animations()
			_play_animation("Idle")
			return

	_build_fallback_human()


func _play_animation(animation_name: String, restart := false) -> void:
	if not is_instance_valid(_animation_player):
		return
	if not _animation_player.has_animation(animation_name):
		return
	var playback_speed := (
		_walk_playback_speed()
		if animation_name == "Walk"
		else 1.0
	)
	_animation_player.speed_scale = playback_speed
	if (
		not restart
		and _current_animation == animation_name
		and _animation_player.is_playing()
	):
		return
	_animation_player.play(animation_name, 0.16)
	_current_animation = animation_name


func _walk_playback_speed() -> float:
	if not is_instance_valid(_animation_player):
		return walk_animation_speed
	if not _animation_player.has_animation("Walk"):
		return walk_animation_speed
	var walk := _animation_player.get_animation("Walk")
	return maxf(
		0.01,
		(speed_mps * walk.length / maxf(walk_stride_m, 0.001))
			* walk_animation_speed
	)


func _configure_looping_animations() -> void:
	if not is_instance_valid(_animation_player):
		return
	for animation_name in ["Idle", "Walk"]:
		if not _animation_player.has_animation(animation_name):
			continue
		var animation := _animation_player.get_animation(animation_name)
		animation.loop_mode = Animation.LOOP_LINEAR


func _configure_foot_ik() -> void:
	if not enable_foot_ik or not is_instance_valid(_skeleton):
		return
	for required_bone in [
		"Thigh.L",
		"Shin.L",
		"Foot.L",
		"Thigh.R",
		"Shin.R",
		"Foot.R",
	]:
		if _skeleton.find_bone(required_bone) < 0:
			return
	var left_setup := _create_leg_ik(
		"Left",
		"Thigh.L",
		"Shin.L",
		"Foot.L"
	)
	_left_foot_ik = left_setup["ik"] as TwoBoneIK3D
	_left_foot_target = left_setup["target"] as Marker3D
	_left_knee_pole = left_setup["pole"] as Marker3D
	var right_setup := _create_leg_ik(
		"Right",
		"Thigh.R",
		"Shin.R",
		"Foot.R"
	)
	_right_foot_ik = right_setup["ik"] as TwoBoneIK3D
	_right_foot_target = right_setup["target"] as Marker3D
	_right_knee_pole = right_setup["pole"] as Marker3D
	_foot_plant_driver = VillagerFootPlantDriver.new()
	_foot_plant_driver.name = "FootPlantDriver"
	_foot_plant_driver.controller = self
	_skeleton.add_child(_foot_plant_driver)
	_skeleton.move_child(
		_foot_plant_driver,
		mini(
			_left_foot_ik.get_index(),
			_right_foot_ik.get_index()
		)
	)
	_foot_orientation_lock = VillagerFootOrientationLock.new()
	_foot_orientation_lock.name = "FootOrientationLock"
	_foot_orientation_lock.controller = self
	_skeleton.add_child(_foot_orientation_lock)
	_skeleton.move_child(
		_foot_orientation_lock,
		mini(
			_left_foot_ik.get_index(),
			_right_foot_ik.get_index()
		) + 1
	)


func _create_leg_ik(
	label: String,
	root_bone_name: String,
	middle_bone_name: String,
	end_bone_name: String
) -> Dictionary:
	var target := Marker3D.new()
	target.name = "%sFootIKTarget" % label
	_skeleton.add_child(target)
	var pole := Marker3D.new()
	pole.name = "%sKneeIKPole" % label
	_skeleton.add_child(pole)

	var ik := TwoBoneIK3D.new()
	ik.name = "%sLegTerrainIK" % label
	_skeleton.add_child(ik)
	ik.set_setting_count(1)
	ik.set_target_node(0, NodePath("../%s" % target.name))
	ik.set_pole_node(0, NodePath("../%s" % pole.name))
	ik.set_root_bone_name(0, root_bone_name)
	ik.set_root_bone(0, _skeleton.find_bone(root_bone_name))
	ik.set_middle_bone_name(0, middle_bone_name)
	ik.set_middle_bone(0, _skeleton.find_bone(middle_bone_name))
	ik.set_end_bone_name(0, end_bone_name)
	ik.set_end_bone(0, _skeleton.find_bone(end_bone_name))
	ik.set_use_virtual_end(0, false)
	ik.set_extend_end_bone(0, false)
	ik.set_mutable_bone_axes(true)
	ik.set_active(true)
	ik.set_influence(0.0)
	ik.set_meta("terrain_driven", true)

	var end_bone := _skeleton.find_bone(end_bone_name)
	var middle_bone := _skeleton.find_bone(middle_bone_name)
	target.position = _skeleton.get_bone_global_pose(end_bone).origin
	pole.position = (
		_skeleton.get_bone_global_pose(middle_bone).origin
		+ Vector3(0.0, 0.1, -0.4)
	)
	return {"ik": ik, "target": target, "pole": pole}


func _update_foot_ik(cycle_phase: float) -> void:
	if not enable_foot_ik or not is_instance_valid(_skeleton):
		return
	var parent_3d := get_parent() as Node3D
	if not is_instance_valid(parent_3d):
		return
	var left_weight := _foot_stance_weight(cycle_phase, 0.0)
	var right_weight := _foot_stance_weight(cycle_phase, 0.5)
	var left_local_phase := fposmod(cycle_phase, 1.0)
	var right_local_phase := fposmod(cycle_phase - 0.5, 1.0)
	if left_local_phase < 0.50:
		if not _left_foot_planted:
			_left_foot_plant_xz = _foot_xz_in_parent(
				"Foot.L", parent_3d
			)
			_left_foot_contact_basis = _skeleton.get_bone_global_pose(
				_skeleton.find_bone("Foot.L")
			).basis
			_left_foot_planted = true
	else:
		_left_foot_planted = false
	if right_local_phase < 0.50:
		if not _right_foot_planted:
			_right_foot_plant_xz = _foot_xz_in_parent(
				"Foot.R", parent_3d
			)
			_right_foot_contact_basis = _skeleton.get_bone_global_pose(
				_skeleton.find_bone("Foot.R")
			).basis
			_right_foot_planted = true
	else:
		_right_foot_planted = false
	_update_leg_ik(
		_left_foot_ik,
		_left_foot_target,
		_left_knee_pole,
		"Shin.L",
		"Foot.L",
		_left_foot_plant_xz,
		_left_foot_planted,
		left_weight * foot_ik_influence
	)
	_update_leg_ik(
		_right_foot_ik,
		_right_foot_target,
		_right_knee_pole,
		"Shin.R",
		"Foot.R",
		_right_foot_plant_xz,
		_right_foot_planted,
		right_weight * foot_ik_influence
	)


func _current_walk_cycle_phase() -> float:
	return fposmod(
		(distance_walked_m - _walk_cycle_start_distance_m)
			/ maxf(walk_stride_m, 0.001),
		1.0
	)


func _foot_stance_weight(cycle_phase: float, contact_phase: float) -> float:
	var local_phase := fposmod(cycle_phase - contact_phase, 1.0)
	if local_phase <= 0.375:
		return 1.0
	if local_phase < 0.50:
		return 1.0 - smoothstep(0.375, 0.50, local_phase)
	if local_phase >= 0.875:
		return smoothstep(0.875, 1.0, local_phase)
	return 0.0


func _update_leg_ik(
	ik: TwoBoneIK3D,
	target: Marker3D,
	pole: Marker3D,
	middle_bone_name: String,
	end_bone_name: String,
	plant_xz: Vector2,
	use_plant: bool,
	influence: float
) -> void:
	if (
		not is_instance_valid(ik)
		or not is_instance_valid(target)
		or not is_instance_valid(pole)
	):
		return
	var parent_3d := get_parent() as Node3D
	if not is_instance_valid(parent_3d):
		ik.set_influence(0.0)
		return
	var middle_bone := _skeleton.find_bone(middle_bone_name)
	var end_bone := _skeleton.find_bone(end_bone_name)
	var sole_position := _bone_position_in_parent(end_bone, parent_3d)
	var sole_xz := (
		plant_xz
		if use_plant
		else Vector2(sole_position.x, sole_position.z)
	)
	var target_in_parent := Vector3(
		sole_xz.x,
		TerrainProfile.height_at(sole_xz) + foot_offset_m,
		sole_xz.y
	)
	target.global_position = parent_3d.to_global(target_in_parent)

	var knee_position := _bone_position_in_parent(middle_bone, parent_3d)
	var forward := -transform.basis.z
	forward.y = 0.0
	if forward.length_squared() < 0.000001:
		forward = Vector3.FORWARD
	var pole_in_parent := (
		knee_position
		+ forward.normalized() * foot_ik_pole_distance_m
		+ Vector3.UP * 0.05
	)
	pole.global_position = parent_3d.to_global(pole_in_parent)
	ik.set_influence(clampf(influence, 0.0, 1.0))


func _foot_xz_in_parent(
	bone_name: String,
	parent_3d: Node3D
) -> Vector2:
	var bone := _skeleton.find_bone(bone_name)
	var bone_position := _bone_position_in_parent(bone, parent_3d)
	return Vector2(bone_position.x, bone_position.z)


func _reset_foot_plants() -> void:
	_left_foot_planted = false
	_right_foot_planted = false


func _bone_position_in_parent(
	bone: int,
	parent_3d: Node3D
) -> Vector3:
	var bone_in_world := _skeleton.to_global(
		_skeleton.get_bone_global_pose(bone).origin
	)
	return parent_3d.to_local(bone_in_world)


func _set_foot_ik_influence(left: float, right: float) -> void:
	if is_instance_valid(_left_foot_ik):
		_left_foot_ik.set_influence(clampf(left, 0.0, 1.0))
	if is_instance_valid(_right_foot_ik):
		_right_foot_ik.set_influence(clampf(right, 0.0, 1.0))


func _build_fallback_human() -> void:
	var cloth := StandardMaterial3D.new()
	cloth.albedo_color = Color("315b9b")
	cloth.roughness = 0.78
	var skin := StandardMaterial3D.new()
	skin.albedo_color = Color("d6a579")
	skin.roughness = 0.82
	var leather := StandardMaterial3D.new()
	leather.albedo_color = Color("322b28")
	leather.roughness = 0.9

	_left_leg = _box_part("LeftLeg", Vector3(0.17, 0.72, 0.18), Vector3(-0.115, 0.36, 0.0), cloth)
	_right_leg = _box_part("RightLeg", Vector3(0.17, 0.72, 0.18), Vector3(0.115, 0.36, 0.0), cloth)
	_visual_root.add_child(_left_leg)
	_visual_root.add_child(_right_leg)

	var torso_mesh := CylinderMesh.new()
	torso_mesh.top_radius = 0.23
	torso_mesh.bottom_radius = 0.29
	torso_mesh.height = 0.72
	_visual_root.add_child(_mesh_part("Torso", torso_mesh, Vector3(0.0, 1.02, 0.0), cloth))

	var head_mesh := SphereMesh.new()
	head_mesh.radius = 0.205
	head_mesh.height = 0.41
	_visual_root.add_child(_mesh_part("Head", head_mesh, Vector3(0.0, 1.585, 0.0), skin))
	_visual_root.add_child(_box_part(
		"Direction", Vector3(0.16, 0.08, 0.34), Vector3(0.0, 1.15, -0.30), leather
	))


func _box_part(
	part_name: String,
	size: Vector3,
	part_position: Vector3,
	part_material: Material
) -> MeshInstance3D:
	var box := BoxMesh.new()
	box.size = size
	return _mesh_part(part_name, box, part_position, part_material)


func _mesh_part(
	part_name: String,
	part_mesh: PrimitiveMesh,
	part_position: Vector3,
	part_material: Material
) -> MeshInstance3D:
	var part := MeshInstance3D.new()
	part.name = part_name
	part.mesh = part_mesh
	part.position = part_position
	part.material_override = part_material
	return part
