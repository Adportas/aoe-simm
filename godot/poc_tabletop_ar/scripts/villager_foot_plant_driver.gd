class_name VillagerFootPlantDriver
extends SkeletonModifier3D

var controller: UnitController


func _process_modification_with_delta(_delta: float) -> void:
	if not is_instance_valid(controller) or not controller.has_target:
		return
	controller._update_foot_ik(controller._current_walk_cycle_phase())
