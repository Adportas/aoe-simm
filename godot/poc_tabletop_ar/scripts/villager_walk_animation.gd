class_name VillagerWalkAnimation
extends RefCounted

## Runtime-safe adaptation of Quaternius' CC0 Universal Animation Library
## Walk_Loop. The reference's contact/down/passing/up timing is preserved,
## while swing-knee flexion is capped at 64 degrees for the fused TRELLIS mesh.
const MOTION_REFERENCE := "Quaternius Universal Animation Library / Walk_Loop"
const MOTION_REFERENCE_URL := "https://quaternius.com/packs/universalanimationlibrary.html"
const MOTION_REFERENCE_LICENSE := "CC0 1.0"
const MOTION_REVISION := 3
const FPS := 24.0
const LENGTH_SECONDS := 32.0 / FPS

# frame, thighs L/R, shins L/R, feet L/R, arms L/R, elbows L/R,
# torso side, root lateral/up, pelvis pitch, head pitch.
const PHASES := [
	[1, -24.0, 20.0, 8.0, 18.0, -8.0, 12.0, 14.0, -14.0, 16.0, 12.0, 1.0, -0.008, 0.000, 0.0, -1.0],
	[5, -14.0, 14.0, 18.0, 44.0, -2.0, 18.0, 11.0, -11.0, 16.0, 14.0, 0.75, -0.015, -0.010, -1.0, -0.5],
	[9, 2.0, -10.0, 10.0, 64.0, 0.0, 14.0, 5.0, -5.0, 15.0, 16.0, 0.25, -0.012, 0.006, 0.2, -1.2],
	[13, 18.0, -32.0, 15.0, 58.0, 4.0, -2.0, -7.0, 7.0, 14.0, 17.0, -0.5, -0.005, 0.018, 1.0, -0.6],
	[17, 20.0, -24.0, 18.0, 8.0, 12.0, -8.0, -14.0, 14.0, 12.0, 16.0, -1.0, 0.008, 0.000, 0.0, -1.0],
	[21, 14.0, -14.0, 44.0, 18.0, 18.0, -2.0, -11.0, 11.0, 14.0, 16.0, -0.75, 0.015, -0.010, -1.0, -0.5],
	[25, -10.0, 2.0, 64.0, 10.0, 14.0, 0.0, -5.0, 5.0, 16.0, 15.0, -0.25, 0.012, 0.006, 0.2, -1.2],
	[29, -32.0, 18.0, 58.0, 15.0, -2.0, 4.0, 7.0, -7.0, 17.0, 14.0, 0.5, 0.005, 0.018, 1.0, -0.6],
	[33, -24.0, 20.0, 8.0, 18.0, -8.0, 12.0, 14.0, -14.0, 16.0, 12.0, 1.0, -0.008, 0.000, 0.0, -1.0],
]


static func install(
	animation_player: AnimationPlayer,
	skeleton: Skeleton3D
) -> Animation:
	var library := animation_player.get_animation_library("")
	if library == null:
		library = AnimationLibrary.new()
		animation_player.add_animation_library("", library)
	if library.has_animation("Walk"):
		var installed := library.get_animation("Walk")
		if (
			installed.get_meta("motion_reference", "") == MOTION_REFERENCE
			and int(installed.get_meta("motion_revision", 0)) == MOTION_REVISION
		):
			return installed

	var animation := Animation.new()
	animation.resource_name = "Walk"
	animation.length = LENGTH_SECONDS
	animation.loop_mode = Animation.LOOP_LINEAR
	animation.set_meta("motion_reference", MOTION_REFERENCE)
	animation.set_meta("motion_reference_url", MOTION_REFERENCE_URL)
	animation.set_meta("motion_reference_license", MOTION_REFERENCE_LICENSE)
	animation.set_meta("motion_revision", MOTION_REVISION)
	animation.set_meta("cycle_phases", "contact/down/passing/up, mirrored")
	animation.set_meta("maximum_knee_flexion_degrees", 64.0)
	var animation_root := animation_player.get_node(
		animation_player.root_node
	) as Node
	var skeleton_path := animation_root.get_path_to(skeleton)
	_add_position_track(
		animation,
		skeleton,
		skeleton_path,
		"Root"
	)
	for bone_name in [
		"Pelvis",
		"Spine",
		"Chest",
		"Neck",
		"Head",
		"Thigh.L",
		"Shin.L",
		"Foot.L",
		"Thigh.R",
		"Shin.R",
		"Foot.R",
		"UpperArm.L",
		"LowerArm.L",
		"UpperArm.R",
		"LowerArm.R",
	]:
		_add_rotation_track(
			animation,
			skeleton,
			skeleton_path,
			bone_name
		)
	if library.has_animation("Walk"):
		library.remove_animation("Walk")
	library.add_animation("Walk", animation)
	return animation


static func _add_position_track(
	animation: Animation,
	skeleton: Skeleton3D,
	skeleton_path: NodePath,
	bone_name: String
) -> void:
	var bone := skeleton.find_bone(bone_name)
	if bone < 0:
		return
	var track := animation.add_track(Animation.TYPE_POSITION_3D)
	animation.track_set_path(
		track,
		NodePath("%s:%s" % [skeleton_path, bone_name])
	)
	animation.track_set_interpolation_type(
		track,
		Animation.INTERPOLATION_CUBIC
	)
	animation.track_set_interpolation_loop_wrap(track, true)
	var rest_position := skeleton.get_bone_rest(bone).origin
	for phase in PHASES:
		var frame := int(phase[0])
		var root_offset := Vector3(
			float(phase[12]),
			float(phase[13]),
			0.0
		)
		animation.position_track_insert_key(
			track,
			float(frame - 1) / FPS,
			rest_position + root_offset
		)


static func _add_rotation_track(
	animation: Animation,
	skeleton: Skeleton3D,
	skeleton_path: NodePath,
	bone_name: String
) -> void:
	var bone := skeleton.find_bone(bone_name)
	if bone < 0:
		return
	var track := animation.add_track(Animation.TYPE_ROTATION_3D)
	animation.track_set_path(
		track,
		NodePath("%s:%s" % [skeleton_path, bone_name])
	)
	animation.track_set_interpolation_type(
		track,
		Animation.INTERPOLATION_CUBIC
	)
	animation.track_set_interpolation_loop_wrap(track, true)
	var rest_rotation := (
		skeleton.get_bone_rest(bone).basis.get_rotation_quaternion()
	)
	var previous := Quaternion.IDENTITY
	var has_previous := false
	for phase in PHASES:
		var frame := int(phase[0])
		var euler_degrees := _bone_euler_degrees(bone_name, phase)
		var pose_rotation := Basis.from_euler(
			Vector3(
				deg_to_rad(euler_degrees.x),
				deg_to_rad(euler_degrees.y),
				deg_to_rad(euler_degrees.z)
			),
			EULER_ORDER_XYZ
		).get_rotation_quaternion()
		var value := (rest_rotation * pose_rotation).normalized()
		if has_previous and previous.dot(value) < 0.0:
			value = Quaternion(-value.x, -value.y, -value.z, -value.w)
		animation.rotation_track_insert_key(
			track,
			float(frame - 1) / FPS,
			value
		)
		previous = value
		has_previous = true


static func _bone_euler_degrees(
	bone_name: String,
	phase: Array
) -> Vector3:
	var torso_side := float(phase[11])
	match bone_name:
		"Pelvis":
			return Vector3(float(phase[14]), 2.0 * torso_side, -2.0 * torso_side)
		"Spine":
			return Vector3(1.0, -1.2 * torso_side, 0.6 * torso_side)
		"Chest":
			return Vector3(1.8, -3.0 * torso_side, 1.2 * torso_side)
		"Neck":
			return Vector3(-0.4, 0.8 * torso_side, -0.5 * torso_side)
		"Head":
			return Vector3(float(phase[15]), 1.2 * torso_side, -0.7 * torso_side)
		"Thigh.L":
			return Vector3(float(phase[1]), 0.0, 0.0)
		"Thigh.R":
			return Vector3(float(phase[2]), 0.0, 0.0)
		"Shin.L":
			return Vector3(float(phase[3]), 0.0, 0.0)
		"Shin.R":
			return Vector3(float(phase[4]), 0.0, 0.0)
		"Foot.L":
			return Vector3(float(phase[5]), 0.0, 0.0)
		"Foot.R":
			return Vector3(float(phase[6]), 0.0, 0.0)
		"UpperArm.L":
			return Vector3(float(phase[7]), 0.0, 0.0)
		"UpperArm.R":
			return Vector3(float(phase[8]), 0.0, 0.0)
		"LowerArm.L":
			return Vector3(float(phase[9]), 0.0, 0.0)
		"LowerArm.R":
			return Vector3(float(phase[10]), 0.0, 0.0)
	return Vector3.ZERO
