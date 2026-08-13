"""Replace only the villager's actions and re-export its existing game asset.

This avoids repeating geometry decimation and texture baking when iteration is
limited to animation. Run through tools/update_villager_walk.sh.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy

import prepare_trellis_villager as villager


SOURCE = villager.DEFAULT_SOURCE.resolve()
OUTPUT = villager.DEFAULT_OUTPUT.resolve()
REPORT = villager.DEFAULT_REPORT.resolve()
SAMPLED_WALK_FRAMES = (1, 5, 9, 13, 17, 21, 25, 29, 33)


def replace_actions(rig: bpy.types.Object) -> dict:
    rig.animation_data_create()
    rig.animation_data.action = None
    for action in list(bpy.data.actions):
        if action.name in {"Idle", "Walk", "Attack"}:
            bpy.data.actions.remove(action)
    guard_module = villager.load_guard_module()
    return villager.build_skin_animations(guard_module, rig)


def validate_walk(
    rig: bpy.types.Object,
    mesh: bpy.types.Object,
    actions: dict,
) -> dict:
    rig.animation_data.action = actions["Walk"]
    maximum_knee_flexion = 0.0
    maximum_head_rotation = 0.0
    minimum_height = math.inf
    maximum_height = -math.inf
    for frame in SAMPLED_WALK_FRAMES:
        bpy.context.scene.frame_set(frame)
        maximum_knee_flexion = max(
            maximum_knee_flexion,
            math.degrees(rig.pose.bones["Shin.L"].rotation_euler.x),
            math.degrees(rig.pose.bones["Shin.R"].rotation_euler.x),
        )
        maximum_head_rotation = max(
            maximum_head_rotation,
            *(
                abs(math.degrees(angle))
                for angle in rig.pose.bones["Head"].rotation_euler
            ),
        )
        height = villager.deformed_height(mesh)
        minimum_height = min(minimum_height, height)
        maximum_height = max(maximum_height, height)

    if not 62.0 <= maximum_knee_flexion <= 66.0:
        raise RuntimeError(
            f"Unexpected maximum knee flexion: {maximum_knee_flexion:.3f}"
        )
    if maximum_head_rotation > 2.0:
        raise RuntimeError(
            f"Head stabilization exceeded 2 degrees: {maximum_head_rotation:.3f}"
        )
    bpy.context.scene.frame_set(1)
    left_contact_thigh = math.degrees(
        rig.pose.bones["Thigh.L"].rotation_euler.x
    )
    right_trailing_thigh = math.degrees(
        rig.pose.bones["Thigh.R"].rotation_euler.x
    )
    left_arm = math.degrees(
        rig.pose.bones["UpperArm.L"].rotation_euler.x
    )
    right_arm = math.degrees(
        rig.pose.bones["UpperArm.R"].rotation_euler.x
    )
    if left_contact_thigh > -20.0 or right_trailing_thigh < 16.0:
        raise RuntimeError(
            "Sagittal gait axis is reversed at left contact: "
            f"{left_contact_thigh:.3f}, {right_trailing_thigh:.3f}"
        )
    if left_arm < 12.0 or right_arm > -12.0:
        raise RuntimeError(
            "Arm counter-swing is reversed at left contact: "
            f"{left_arm:.3f}, {right_arm:.3f}"
        )
    if minimum_height < 1.45 or maximum_height > 1.95:
        raise RuntimeError(
            "Walk deformation left safe bounds: "
            f"{minimum_height:.3f}..{maximum_height:.3f} m"
        )
    rig.animation_data.action = actions["Idle"]
    bpy.context.scene.frame_set(1)
    return {
        "sampled_frames": list(SAMPLED_WALK_FRAMES),
        "maximum_knee_flexion_degrees": round(maximum_knee_flexion, 3),
        "maximum_head_rotation_degrees": round(maximum_head_rotation, 3),
        "left_contact_thigh_degrees": round(left_contact_thigh, 3),
        "right_trailing_thigh_degrees": round(right_trailing_thigh, 3),
        "sagittal_axis_forward": True,
        "deformed_height_range_m": [
            round(minimum_height, 4),
            round(maximum_height, 4),
        ],
    }


def update_report(actions: dict, validation: dict) -> None:
    report = json.loads(REPORT.read_text()) if REPORT.is_file() else {}
    rig_report = report.setdefault("rig", {})
    rig_report["animations_seconds"] = {
        name: round((action.frame_end - action.frame_start) / 24.0, 4)
        for name, action in actions.items()
    }
    rig_report["walk_motion"] = {
        "reference": villager.WALK_MOTION_REFERENCE,
        "reference_url": villager.WALK_MOTION_REFERENCE_URL,
        "license": "CC0 1.0",
        "adaptation": "8-phase in-place cycle for AoE 18-bone fused mesh",
        "phases": actions["Walk"]["cycle_phases"].split(","),
        "maximum_knee_flexion_degrees": actions["Walk"][
            "maximum_knee_flexion_degrees"
        ],
        "terrain_correction": "Godot TwoBoneIK3D during stance",
    }
    report.setdefault("validation", {})["walk_pose_validation"] = validation
    REPORT.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    current_source = Path(bpy.data.filepath).resolve()
    if current_source != SOURCE:
        raise RuntimeError(f"Expected {SOURCE}, opened {current_source}")
    rig = bpy.data.objects.get("VillagerRig")
    mesh = bpy.data.objects.get("Villager_Game")
    if rig is None or rig.type != "ARMATURE":
        raise RuntimeError("VillagerRig armature is missing from the source blend")
    if mesh is None or mesh.type != "MESH":
        raise RuntimeError("Villager_Game mesh is missing from the source blend")

    villager.stamp("Replacing Idle/Walk/Attack in the baked villager source")
    actions = replace_actions(rig)
    validation = validate_walk(rig, mesh, actions)
    villager.stamp(f"Walk validation: {validation}")
    villager.save_source(SOURCE)
    villager.export_glb(OUTPUT, rig, mesh)
    update_report(actions, validation)
    villager.stamp(f"Animation-only update complete: {OUTPUT}")


if __name__ == "__main__":
    main()
