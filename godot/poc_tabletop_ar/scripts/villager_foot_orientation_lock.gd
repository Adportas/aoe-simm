class_name VillagerFootOrientationLock
extends SkeletonModifier3D

var controller: UnitController


func _process_modification_with_delta(_delta: float) -> void:
	if not is_instance_valid(controller) or not controller.has_target:
		return
	var skeleton := get_skeleton()
	if not is_instance_valid(skeleton):
		return
	var phase := controller._current_walk_cycle_phase()
	_lock_foot(skeleton, "Foot.L", phase, 0.0)
	_lock_foot(skeleton, "Foot.R", phase, 0.5)


func _lock_foot(
	skeleton: Skeleton3D,
	bone_name: String,
	cycle_phase: float,
	contact_phase: float
) -> void:
	var local_phase := fposmod(cycle_phase - contact_phase, 1.0)
	if local_phase > 0.375:
		return
	var bone := skeleton.find_bone(bone_name)
	if bone < 0:
		return
	var contact_basis: Basis = (
		controller._left_foot_contact_basis
		if bone_name.ends_with(".L")
		else controller._right_foot_contact_basis
	)
	var parent := skeleton.get_bone_parent(bone)
	var parent_basis := skeleton.get_bone_global_pose(parent).basis
	var weight := controller._foot_stance_weight(
		cycle_phase, contact_phase
	)
	var animated_rotation := skeleton.get_bone_pose_rotation(bone)
	var locked_rotation := (
		parent_basis.inverse() * contact_basis
	).get_rotation_quaternion()
	skeleton.set_bone_pose_rotation(
		bone,
		animated_rotation.slerp(locked_rotation, weight)
	)
