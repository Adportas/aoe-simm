"""Turn the TRELLIS.2 villager master into an animated Godot game asset.

The high-resolution GLB remains untouched.  This reproducible preparation pass
normalizes scale and orientation, makes a game-resolution mesh, extracts and
downsamples its PBR textures, bakes normal/AO detail, binds the existing AoE
18-bone humanoid rig, adds Idle/Walk/Attack actions, and exports a Godot-ready
GLB plus an editable Blender source.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]
DEFAULT_MASTER = (
    REPO_ROOT
    / "artifacts"
    / "villager-3dgen-20260811"
    / "villager_trellis2_master.glb"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "units" / "villager_trellis.glb"
DEFAULT_SOURCE = PROJECT_ROOT / "assets" / "units" / "source" / "villager_trellis.blend"
DEFAULT_TEXTURES = PROJECT_ROOT / "assets" / "units" / "textures" / "villager_trellis"
DEFAULT_PREVIEWS = PROJECT_ROOT / "previews" / "villager_trellis"
DEFAULT_REPORT = (
    PROJECT_ROOT / "assets" / "units" / "source" / "villager_trellis_report.json"
)
TARGET_HEIGHT_M = 1.82
TARGET_TRIANGLES = 72_000
GAME_TEXTURE_SIZE = 2048
WALK_MOTION_REFERENCE = "Quaternius Universal Animation Library / Walk_Loop"
WALK_MOTION_REFERENCE_URL = "https://quaternius.com/packs/universalanimationlibrary.html"


def stamp(message: str) -> None:
    print(f"[VILLAGER {time.strftime('%H:%M:%S')}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES)
    parser.add_argument("--previews", type=Path, default=DEFAULT_PREVIEWS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-triangles", type=int, default=TARGET_TRIANGLES)
    parser.add_argument("--texture-size", type=int, default=GAME_TEXTURE_SIZE)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.armatures,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def mesh_triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def object_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    minimum = Vector(
        (
            min(point.x for point in points),
            min(point.y for point in points),
            min(point.z for point in points),
        )
    )
    maximum = Vector(
        (
            max(point.x for point in points),
            max(point.y for point in points),
            max(point.z for point in points),
        )
    )
    return minimum, maximum


def activate_only(*objects: bpy.types.Object, active: bpy.types.Object | None = None) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[-1]


def import_and_normalize(master_path: Path) -> bpy.types.Object:
    if not master_path.is_file():
        raise FileNotFoundError(master_path)
    bpy.ops.import_scene.gltf(filepath=str(master_path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one TRELLIS mesh, found {len(meshes)}")
    mesh = meshes[0]
    mesh.name = "Villager_Master_High"
    mesh.data.name = "Villager_Master_High_Mesh"
    minimum, maximum = object_bounds(mesh)
    source_height = maximum.z - minimum.z
    scale = TARGET_HEIGHT_M / source_height
    mesh.scale = Vector((scale, scale, scale))
    bpy.context.view_layer.update()
    minimum, _ = object_bounds(mesh)
    mesh.location.z -= minimum.z
    activate_only(mesh, active=mesh)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mesh["source_generator"] = "Microsoft TRELLIS.2-4B"
    mesh["source_pipeline"] = "1024_cascade"
    mesh["source_seed"] = 42
    mesh["source_master"] = str(master_path)
    mesh["normalized_height_m"] = TARGET_HEIGHT_M
    return mesh


def upstream_image(socket, seen: set[int] | None = None):
    if socket is None or not socket.is_linked:
        return None
    seen = seen or set()
    for link in socket.links:
        node = link.from_node
        pointer = node.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        if node.type == "TEX_IMAGE" and node.image is not None:
            return node.image
        for input_socket in node.inputs:
            image = upstream_image(input_socket, seen)
            if image is not None:
                return image
    return None


def material_shader(material: bpy.types.Material):
    if not material or not material.use_nodes:
        raise RuntimeError("TRELLIS material has no node graph")
    shaders = [node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"]
    if not shaders:
        raise RuntimeError("TRELLIS material has no Principled BSDF")
    return shaders[0]


def save_image(image: bpy.types.Image, path: Path, file_format: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(path)
    image.file_format = file_format
    image.save()


def duplicate_scaled_image(
    source: bpy.types.Image,
    name: str,
    size: int,
    path: Path,
    *,
    non_color: bool,
):
    source_path = Path(bpy.path.abspath(source.filepath_raw)).resolve()
    working = bpy.data.images.load(str(source_path), check_existing=False)
    working.name = f"{name}_Resize_Working"
    if non_color:
        working.colorspace_settings.name = "Non-Color"
    _ = working.pixels[0]
    working.scale(size, size)
    save_image(working, path, "WEBP")
    bpy.data.images.remove(working)
    result = bpy.data.images.load(str(path), check_existing=False)
    result.name = name
    if non_color:
        result.colorspace_settings.name = "Non-Color"
    if tuple(result.size) != (size, size):
        raise RuntimeError(
            f"Texture resize failed for {path}: got {tuple(result.size)}, expected {(size, size)}"
        )
    return result


def extract_and_prepare_textures(
    high: bpy.types.Object,
    low: bpy.types.Object,
    texture_dir: Path,
    size: int,
) -> dict:
    if not high.data.materials:
        raise RuntimeError("TRELLIS mesh has no material")
    high_material = high.data.materials[0]
    shader = material_shader(high_material)
    base_image = upstream_image(shader.inputs.get("Base Color"))
    roughness_image = upstream_image(shader.inputs.get("Roughness"))
    metallic_image = upstream_image(shader.inputs.get("Metallic"))
    mr_image = roughness_image or metallic_image
    if base_image is None or mr_image is None:
        raise RuntimeError("Could not resolve TRELLIS base-color and metallic/roughness maps")

    texture_dir.mkdir(parents=True, exist_ok=True)
    base_master_path = texture_dir / "villager_basecolor_4k.webp"
    mr_master_path = texture_dir / "villager_metallic_roughness_4k.webp"
    save_image(base_image, base_master_path, "WEBP")
    save_image(mr_image, mr_master_path, "WEBP")

    base_game_path = texture_dir / "villager_basecolor_2k.webp"
    mr_game_path = texture_dir / "villager_metallic_roughness_2k.webp"
    base_game = duplicate_scaled_image(
        base_image,
        "Villager_BaseColor_2K",
        size,
        base_game_path,
        non_color=False,
    )
    mr_game = duplicate_scaled_image(
        mr_image,
        "Villager_MetallicRoughness_2K",
        size,
        mr_game_path,
        non_color=True,
    )

    low_material = high_material.copy()
    low_material.name = "Villager_PBR_Game"
    low.data.materials.clear()
    low.data.materials.append(low_material)
    for node in low_material.node_tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        if node.image == base_image:
            node.image = base_game
        elif node.image == mr_image:
            node.image = mr_game

    return {
        "material": low_material,
        "base_game": base_game,
        "mr_game": mr_game,
        "base_master_path": base_master_path,
        "mr_master_path": mr_master_path,
        "base_game_path": base_game_path,
        "mr_game_path": mr_game_path,
    }


def decimate_game_mesh(high: bpy.types.Object, target_triangles: int) -> bpy.types.Object:
    low = high.copy()
    low.data = high.data.copy()
    bpy.context.collection.objects.link(low)
    low.name = "Villager_Game"
    low.data.name = "Villager_Game_Mesh"
    source_triangles = mesh_triangles(low)
    ratio = min(1.0, max(0.01, target_triangles / source_triangles))
    modifier = low.modifiers.new("Game triangle budget", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = ratio
    modifier.use_collapse_triangulate = True
    activate_only(low, active=low)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    for polygon in low.data.polygons:
        polygon.use_smooth = True
    low["target_triangle_budget"] = target_triangles
    low["source_triangles"] = source_triangles
    low["lod_policy"] = "Godot import-generated LODs from LOD0"
    return low


def new_bake_image(name: str, size: int, color: tuple[float, float, float, float]):
    image = bpy.data.images.new(name, width=size, height=size, alpha=False)
    image.generated_color = color
    image.colorspace_settings.name = "Non-Color"
    return image


def active_bake_node(material: bpy.types.Material, image: bpy.types.Image, name: str):
    node = material.node_tree.nodes.get(name)
    if node is None:
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = name
    node.image = image
    node.label = name
    material.node_tree.nodes.active = node
    node.select = True
    return node


def configure_cycles_bake() -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.bake.margin = 16
    scene.render.bake.use_clear = True
    scene.render.bake.use_cage = False
    scene.render.bake.cage_extrusion = 0.006
    scene.render.bake.max_ray_distance = 0.018


def bake_detail_maps(
    high: bpy.types.Object,
    low: bpy.types.Object,
    material: bpy.types.Material,
    texture_dir: Path,
    size: int,
) -> dict:
    configure_cycles_bake()
    normal_path = texture_dir / "villager_normal_2k.png"
    ao_path = texture_dir / "villager_ao_2k.png"
    errors: list[str] = []

    normal_image = new_bake_image(
        "Villager_Normal_2K",
        size,
        (0.5, 0.5, 1.0, 1.0),
    )
    normal_texture = active_bake_node(
        material, normal_image, "Villager_Normal_Bake_Target"
    )
    high.hide_render = False
    try:
        activate_only(high, low, active=low)
        scene = bpy.context.scene
        scene.render.bake.use_selected_to_active = True
        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
    except Exception as error:
        errors.append(f"normal: {error!r}")
        stamp(f"Normal bake fallback: {error!r}")
    save_image(normal_image, normal_path, "PNG")

    shader = material_shader(material)
    normal_map = material.node_tree.nodes.new("ShaderNodeNormalMap")
    normal_map.name = "Villager_Tangent_Normal"
    normal_map.space = "TANGENT"
    normal_map.inputs["Strength"].default_value = 0.8
    material.node_tree.links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
    material.node_tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])

    ao_image = new_bake_image("Villager_AO_2K", size, (1.0, 1.0, 1.0, 1.0))
    ao_texture = active_bake_node(material, ao_image, "Villager_AO_Bake_Target")
    try:
        activate_only(low, active=low)
        bpy.context.scene.render.bake.use_selected_to_active = False
        bpy.ops.object.bake(type="AO")
    except Exception as error:
        errors.append(f"ao: {error!r}")
        stamp(f"AO bake fallback: {error!r}")
    save_image(ao_image, ao_path, "PNG")

    group = bpy.data.node_groups.get("glTF Material Output")
    if group is None:
        group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        group.interface.new_socket(
            name="Occlusion",
            in_out="INPUT",
            socket_type="NodeSocketFloat",
        )
    group_node = material.node_tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = group
    group_node.name = "Godot_GLTF_Occlusion"
    material.node_tree.links.new(ao_texture.outputs["Color"], group_node.inputs["Occlusion"])
    high.hide_render = True
    return {
        "normal_path": normal_path,
        "ao_path": ao_path,
        "errors": errors,
    }


def load_guard_module():
    source = Path(__file__).with_name("generate_frontier_guard.py")
    specification = importlib.util.spec_from_file_location("frontier_guard_rig", source)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Could not load rig module {source}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def build_skin_animations(guard_module, rig: bpy.types.Object) -> dict:
    """Adapt the Quaternius CC0 walk phases to the fused generated mesh.

    The reference Walk_Loop uses contact/down/passing/up twice per cycle and
    reaches about 80 degrees of swing-knee flexion. The timing is preserved,
    while flexion is capped at 64 degrees for this simpler 18-bone skin.
    """
    actions = guard_module.build_animations(rig)
    for name in ("Walk", "Attack"):
        old_action = actions[name]
        if rig.animation_data.action == old_action:
            rig.animation_data.action = None
        bpy.data.actions.remove(old_action)

    # frame, phase, thighs L/R, shins L/R, feet L/R, upper arms L/R,
    # lower arms L/R, torso side, root lateral/up, pelvis pitch, head pitch.
    walk_phases = [
        (1, "left_contact", -24, 20, 8, 18, -8, 12, 14, -14, 16, 12, 1.0, -0.008, 0.000, 0.0, -1.0),
        (5, "left_down", -14, 14, 18, 44, -2, 18, 11, -11, 16, 14, 0.75, -0.015, -0.010, -1.0, -0.5),
        (9, "right_passing", 2, -10, 10, 64, 0, 14, 5, -5, 15, 16, 0.25, -0.012, 0.006, 0.2, -1.2),
        (13, "right_up", 18, -32, 15, 58, 4, -2, -7, 7, 14, 17, -0.5, -0.005, 0.018, 1.0, -0.6),
        (17, "right_contact", 20, -24, 18, 8, 12, -8, -14, 14, 12, 16, -1.0, 0.008, 0.000, 0.0, -1.0),
        (21, "right_down", 14, -14, 44, 18, 18, -2, -11, 11, 14, 16, -0.75, 0.015, -0.010, -1.0, -0.5),
        (25, "left_passing", -10, 2, 64, 10, 14, 0, -5, 5, 16, 15, -0.25, 0.012, 0.006, 0.2, -1.2),
        (29, "left_up", -32, 18, 58, 15, -2, 4, 7, -7, 17, 14, 0.5, 0.005, 0.018, 1.0, -0.6),
        (33, "left_contact", -24, 20, 8, 18, -8, 12, 14, -14, 16, 12, 1.0, -0.008, 0.000, 0.0, -1.0),
    ]
    walk_poses = []
    phase_names = []
    for (
        frame,
        phase_name,
        thigh_left,
        thigh_right,
        shin_left,
        shin_right,
        foot_left,
        foot_right,
        arm_left,
        arm_right,
        elbow_left,
        elbow_right,
        torso_side,
        root_lateral,
        root_up,
        pelvis_pitch,
        head_pitch,
    ) in walk_phases:
        phase_names.append(phase_name)
        rotations = {
            "Pelvis": (pelvis_pitch, 2.0 * torso_side, -2.0 * torso_side),
            "Spine": (1.0, -1.2 * torso_side, 0.6 * torso_side),
            "Chest": (1.8, -3.0 * torso_side, 1.2 * torso_side),
            "Neck": (-0.4, 0.8 * torso_side, -0.5 * torso_side),
            # Counter-rotation keeps the head quieter than the chest.
            "Head": (head_pitch, 1.2 * torso_side, -0.7 * torso_side),
            "Thigh.L": (thigh_left, 0.0, 0.0),
            "Thigh.R": (thigh_right, 0.0, 0.0),
            "Shin.L": (shin_left, 0.0, 0.0),
            "Shin.R": (shin_right, 0.0, 0.0),
            "Foot.L": (foot_left, 0.0, 0.0),
            "Foot.R": (foot_right, 0.0, 0.0),
            "UpperArm.L": (arm_left, 0.0, 0.0),
            "UpperArm.R": (arm_right, 0.0, 0.0),
            "LowerArm.L": (elbow_left, 0.0, 0.0),
            "LowerArm.R": (elbow_right, 0.0, 0.0),
        }
        # Root.location Y is vertical for this bone. The old cycle used Z,
        # so its supposed bob actually pushed the rig forward and backward.
        locations = {"Root": (root_lateral, root_up, 0.0)}
        walk_poses.append((frame, rotations, locations))

    walk = guard_module.make_action(
        rig,
        "Walk",
        33,
        walk_poses,
    )
    walk["motion_reference"] = WALK_MOTION_REFERENCE
    walk["motion_reference_url"] = WALK_MOTION_REFERENCE_URL
    walk["motion_reference_license"] = "CC0 1.0"
    walk["cycle_phases"] = ",".join(phase_names)
    walk["maximum_knee_flexion_degrees"] = 64.0
    walk["in_place"] = True
    walk["sagittal_axis_correction"] = "Blender -Y forward to Godot -Z forward"
    attack = guard_module.make_action(
        rig,
        "Attack",
        31,
        [
            (1, {}, {}),
            (
                9,
                {
                    "Chest": (-3.0, 0.0, -4.0),
                    "UpperArm.R": (16.0, -3.0, 3.0),
                    "LowerArm.R": (20.0, 0.0, 0.0),
                    "Head": (0.0, 0.0, 3.0),
                },
                {},
            ),
            (
                16,
                {
                    "Chest": (6.0, 0.0, 5.0),
                    "UpperArm.R": (-30.0, 2.0, -4.0),
                    "LowerArm.R": (-32.0, 0.0, 2.0),
                    "UpperArm.L": (-3.0, 0.0, -2.0),
                    "Head": (-2.0, 0.0, -3.0),
                },
                {"Root": (0.0, -0.012, -0.006)},
            ),
            (
                23,
                {
                    "Chest": (3.0, 0.0, 2.0),
                    "UpperArm.R": (-14.0, 0.0, -2.0),
                    "LowerArm.R": (-16.0, 0.0, 1.0),
                },
                {},
            ),
            (31, {}, {}),
        ],
        loop=False,
    )
    actions["Walk"] = walk
    actions["Attack"] = attack
    for action in actions.values():
        # Preserve all clips in the editable source even while Idle is active.
        action.use_fake_user = True
    rig.animation_data.action = actions["Idle"]
    return actions


def create_fitted_rig(guard_module):
    rig = guard_module.add_armature()
    rig.name = "VillagerRig"
    rig.data.name = "VillagerRig"
    rig["asset_name"] = "AoE Villager TRELLIS 2"
    rig["height_m"] = TARGET_HEIGHT_M
    rig["skeleton_profile"] = "AoE 18-bone humanoid"
    rig["generator"] = "TRELLIS.2 + Blender production pass"
    activate_only(rig, active=rig)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone in rig.data.edit_bones:
        if any(token in bone.name for token in ("UpperArm", "LowerArm", "Hand")):
            bone.head.x *= 0.86
            bone.tail.x *= 0.86
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def procedural_weights(mesh: bpy.types.Object, rig: bpy.types.Object) -> None:
    for group in list(mesh.vertex_groups):
        mesh.vertex_groups.remove(group)
    groups = {bone.name: mesh.vertex_groups.new(name=bone.name) for bone in rig.data.bones}

    def add_blend(vertex_index: int, names: list[str], values: list[float]) -> None:
        total = sum(values)
        for name, value in zip(names, values):
            groups[name].add([vertex_index], value / total, "REPLACE")

    for vertex in mesh.data.vertices:
        point = vertex.co
        z = point.z
        side = "L" if point.x < 0.0 else "R"
        horizontal = abs(point.x)
        if z < 0.16:
            add_blend(vertex.index, [f"Foot.{side}", f"Shin.{side}"], [0.92, 0.08])
        elif z < 0.48:
            t = (z - 0.16) / 0.32
            add_blend(vertex.index, [f"Shin.{side}", f"Thigh.{side}"], [1.0 - 0.2 * t, 0.2 * t])
        elif z < 0.88 and horizontal > 0.07:
            t = (z - 0.48) / 0.40
            add_blend(vertex.index, [f"Thigh.{side}", "Pelvis"], [1.0 - 0.28 * t, 0.28 * t])
        elif z > 1.47 and horizontal < 0.23:
            t = min(1.0, max(0.0, (z - 1.47) / 0.12))
            add_blend(vertex.index, ["Neck", "Head"], [1.0 - t, t])
        elif horizontal > 0.245 and z > 0.84:
            if z > 1.24:
                add_blend(vertex.index, [f"UpperArm.{side}", "Chest"], [0.88, 0.12])
            elif z > 1.03:
                add_blend(
                    vertex.index,
                    [f"LowerArm.{side}", f"UpperArm.{side}"],
                    [0.82, 0.18],
                )
            else:
                add_blend(
                    vertex.index,
                    [f"Hand.{side}", f"LowerArm.{side}"],
                    [0.9, 0.1],
                )
        elif z < 1.0:
            add_blend(vertex.index, ["Pelvis", "Spine"], [0.82, 0.18])
        elif z < 1.28:
            t = (z - 1.0) / 0.28
            add_blend(vertex.index, ["Spine", "Chest"], [1.0 - t, t])
        else:
            add_blend(vertex.index, ["Chest", "Neck"], [0.92, 0.08])
    mesh.parent = rig
    modifier = mesh.modifiers.new("Villager Armature", "ARMATURE")
    modifier.object = rig


def clear_binding(mesh: bpy.types.Object) -> None:
    mesh.parent = None
    for modifier in list(mesh.modifiers):
        if modifier.type in {"ARMATURE", "DATA_TRANSFER"}:
            mesh.modifiers.remove(modifier)
    for group in list(mesh.vertex_groups):
        mesh.vertex_groups.remove(group)


def bind_via_voxel_proxy(mesh: bpy.types.Object, rig: bpy.types.Object) -> dict:
    """Heat-bind a watertight proxy, then transfer its smooth weights."""
    proxy = mesh.copy()
    proxy.data = mesh.data.copy()
    proxy.name = "Villager_Weight_Proxy"
    proxy.data.name = "Villager_Weight_Proxy_Mesh"
    bpy.context.collection.objects.link(proxy)
    proxy.data.remesh_voxel_size = 0.018
    proxy.data.remesh_voxel_adaptivity = 0.0
    activate_only(proxy, active=proxy)
    bpy.ops.object.voxel_remesh()
    proxy_triangles = mesh_triangles(proxy)

    activate_only(proxy, rig, active=rig)
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    proxy_unweighted = sum(1 for vertex in proxy.data.vertices if not vertex.groups)
    if proxy_unweighted:
        clear_binding(proxy)
        activate_only(proxy, rig, active=rig)
        bpy.ops.object.parent_set(type="ARMATURE_ENVELOPE")
        proxy_unweighted = sum(1 for vertex in proxy.data.vertices if not vertex.groups)
    if proxy_unweighted:
        raise RuntimeError(
            f"Voxel proxy still has {proxy_unweighted} unweighted vertices"
        )

    proxy.parent = None
    for modifier in list(proxy.modifiers):
        if modifier.type == "ARMATURE":
            proxy.modifiers.remove(modifier)
    clear_binding(mesh)
    for source_group in proxy.vertex_groups:
        mesh.vertex_groups.new(name=source_group.name)
    transfer = mesh.modifiers.new("Transfer smooth skin weights", "DATA_TRANSFER")
    transfer.object = proxy
    transfer.use_vert_data = True
    transfer.data_types_verts = {"VGROUP_WEIGHTS"}
    transfer.vert_mapping = "POLYINTERP_NEAREST"
    transfer.layers_vgroup_select_src = "ALL"
    transfer.layers_vgroup_select_dst = "NAME"
    transfer.mix_mode = "REPLACE"
    activate_only(mesh, active=mesh)
    bpy.ops.object.modifier_apply(modifier=transfer.name)
    mesh.parent = rig
    armature_modifier = mesh.modifiers.new("Villager Armature", "ARMATURE")
    armature_modifier.object = rig

    proxy_mesh = proxy.data
    bpy.data.objects.remove(proxy, do_unlink=True)
    if proxy_mesh.users == 0:
        bpy.data.meshes.remove(proxy_mesh)
    return {
        "method": "voxel_proxy_bone_heat",
        "proxy_triangles": proxy_triangles,
    }


def bind_mesh(mesh: bpy.types.Object, rig: bpy.types.Object) -> dict:
    method = "automatic_bone_heat"
    error = None
    try:
        activate_only(mesh, rig, active=rig)
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as caught:
        error = repr(caught)
        method = "procedural_fallback"
        stamp(f"Automatic weights failed, using deterministic fallback: {error}")
        mesh.parent = None
        for modifier in list(mesh.modifiers):
            if modifier.type == "ARMATURE":
                mesh.modifiers.remove(modifier)
        procedural_weights(mesh, rig)

    activate_only(mesh, active=mesh)
    try:
        bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
        bpy.ops.object.vertex_group_normalize_all(
            group_select_mode="ALL",
            lock_active=False,
        )
    except Exception as caught:
        stamp(f"Weight cleanup warning: {caught!r}")

    unweighted = sum(1 for vertex in mesh.data.vertices if not vertex.groups)
    if unweighted:
        stamp(f"{unweighted} unweighted vertices found; building a watertight weight proxy")
        try:
            proxy_result = bind_via_voxel_proxy(mesh, rig)
            method = proxy_result["method"]
        except Exception as caught:
            stamp(f"Voxel proxy failed, using deterministic fallback: {caught!r}")
            clear_binding(mesh)
            procedural_weights(mesh, rig)
            method = "procedural_fallback"
            if error is None:
                error = repr(caught)
        unweighted = sum(1 for vertex in mesh.data.vertices if not vertex.groups)
    activate_only(mesh, active=mesh)
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=4)
    bpy.ops.object.vertex_group_normalize_all(
        group_select_mode="ALL",
        lock_active=False,
    )
    return {
        "method": method,
        "automatic_error": error,
        "unweighted_vertices": unweighted,
    }


def save_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)


def export_glb(path: Path, rig: bpy.types.Object, mesh: bpy.types.Object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    activate_only(mesh, rig, active=rig)
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_extra_animations=True,
        export_force_sampling=True,
        export_frame_range=False,
        export_materials="EXPORT",
        export_attributes=True,
        export_extras=True,
        export_cameras=False,
        export_lights=False,
        export_skins=True,
        export_def_bones=True,
        export_leaf_bone=False,
    )


def look_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    color: tuple[float, float, float],
    size: float,
    target: tuple[float, float, float] = (0.0, 0.0, 0.95),
) -> None:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)


def render_previews(
    directory: Path,
    mesh: bpy.types.Object,
    rig: bpy.types.Object,
) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 760
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    floor_material = bpy.data.materials.new("Villager_Preview_Floor")
    floor_material.diffuse_color = (0.025, 0.032, 0.043, 1.0)
    floor_material.roughness = 0.78
    bpy.ops.mesh.primitive_plane_add(size=16.0, location=(0.0, 0.0, -0.012))
    floor = bpy.context.object
    floor.data.materials.append(floor_material)

    camera_data = bpy.data.cameras.new("Villager_Preview_Camera")
    camera = bpy.data.objects.new("Villager_Preview_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = 78.0
    scene.camera = camera

    add_area_light("Villager_Key", (-3.2, -4.0, 4.5), 1150.0, (1.0, 0.76, 0.58), 3.0)
    add_area_light("Villager_Fill", (3.5, -2.0, 2.8), 720.0, (0.48, 0.66, 1.0), 3.4)
    add_area_light("Villager_Rim", (1.0, 3.6, 3.8), 1180.0, (0.58, 0.74, 1.0), 2.5)
    add_area_light(
        "Villager_Face",
        (-0.4, -2.1, 2.5),
        320.0,
        (1.0, 0.86, 0.72),
        1.0,
        target=(0.0, -0.05, 1.62),
    )
    scene.world.color = (0.005, 0.008, 0.014)
    rig.animation_data.action = bpy.data.actions.get("Idle")
    scene.frame_set(1)

    review = [
        (
            "villager_hero.png",
            (2.2, -4.4, 2.12),
            (0.0, -0.01, 0.92),
            "Idle",
            1,
        ),
        (
            "villager_front.png",
            (0.0, -4.5, 1.82),
            (0.0, -0.02, 0.92),
            "Idle",
            1,
        ),
        (
            "villager_rear.png",
            (0.0, 4.5, 1.82),
            (0.0, 0.02, 0.92),
            "Idle",
            1,
        ),
        (
            "villager_walk.png",
            (2.2, -4.4, 2.12),
            (0.0, -0.01, 0.92),
            "Walk",
            13,
        ),
        (
            "villager_attack.png",
            (2.2, -4.4, 2.12),
            (0.0, -0.01, 0.92),
            "Attack",
            16,
        ),
    ]
    output_paths = []
    for filename, location, target, action_name, frame in review:
        rig.animation_data.action = bpy.data.actions.get(action_name)
        scene.frame_set(frame)
        camera.location = location
        look_at(camera, target)
        path = directory / filename
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        output_paths.append(path)
    rig.animation_data.action = bpy.data.actions.get("Idle")
    scene.frame_set(1)
    floor.hide_render = True
    return output_paths


def deformed_height(mesh: bpy.types.Object) -> float:
    dependency_graph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh.evaluated_get(dependency_graph)
    evaluated_mesh = evaluated.to_mesh()
    try:
        points = [evaluated.matrix_world @ vertex.co for vertex in evaluated_mesh.vertices]
        return max(point.z for point in points) - min(point.z for point in points)
    finally:
        evaluated.to_mesh_clear()


def main() -> None:
    args = parse_args()
    for value in (args.master, args.output, args.source, args.textures, args.previews, args.report):
        value = value.expanduser().resolve()
    reset_scene()
    stamp(f"Importing master {args.master}")
    high = import_and_normalize(args.master)
    master_triangles = mesh_triangles(high)
    low = decimate_game_mesh(high, args.target_triangles)
    texture_data = extract_and_prepare_textures(
        high,
        low,
        args.textures,
        args.texture_size,
    )
    stamp(f"Baking normal and AO maps at {args.texture_size}px")
    bake_data = bake_detail_maps(
        high,
        low,
        texture_data["material"],
        args.textures,
        args.texture_size,
    )

    guard_module = load_guard_module()
    rig = create_fitted_rig(guard_module)
    stamp("Binding the decimated mesh to the AoE humanoid rig")
    binding = bind_mesh(low, rig)
    actions = build_skin_animations(guard_module, rig)
    rig.animation_data.action = actions["Idle"]
    bpy.context.scene.frame_set(1)

    game_triangles = mesh_triangles(low)
    minimum, maximum = object_bounds(low)
    rest_height = maximum.z - minimum.z
    if not 1.79 <= rest_height <= 1.83:
        raise RuntimeError(f"Unexpected rest height {rest_height:.4f} m")
    if game_triangles > args.target_triangles * 1.08:
        raise RuntimeError(
            f"Game mesh has {game_triangles} triangles, over budget {args.target_triangles}"
        )
    if binding["unweighted_vertices"]:
        raise RuntimeError("Rig contains unweighted vertices")

    high.hide_set(True)
    high.hide_render = True
    stamp(f"Saving editable source {args.source}")
    save_source(args.source)
    stamp(f"Exporting Godot GLB {args.output}")
    export_glb(args.output, rig, low)
    stamp("Rendering review views")
    previews = render_previews(args.previews, low, rig)

    animation_lengths = {
        name: round((action.frame_end - action.frame_start) / 24.0, 4)
        for name, action in actions.items()
    }
    report = {
        "asset": "AoE Villager TRELLIS 2",
        "source_master": str(args.master),
        "generator": {
            "model": "microsoft/TRELLIS.2-4B",
            "pipeline_type": "1024_cascade",
            "seed": 42,
            "master_texture_size": 4096,
        },
        "geometry": {
            "master_triangles": master_triangles,
            "game_triangles": game_triangles,
            "game_vertices": len(low.data.vertices),
            "height_m": round(rest_height, 5),
            "bounds_min": [round(value, 5) for value in minimum],
            "bounds_max": [round(value, 5) for value in maximum],
            "target_triangle_budget": args.target_triangles,
        },
        "rig": {
            "bones": len(rig.data.bones),
            "bone_names": [bone.name for bone in rig.data.bones],
            "binding": binding,
            "animations_seconds": animation_lengths,
            "walk_motion": {
                "reference": WALK_MOTION_REFERENCE,
                "reference_url": WALK_MOTION_REFERENCE_URL,
                "license": "CC0 1.0",
                "adaptation": "8-phase in-place cycle for AoE 18-bone fused mesh",
                "phases": actions["Walk"]["cycle_phases"].split(","),
                "maximum_knee_flexion_degrees": actions["Walk"][
                    "maximum_knee_flexion_degrees"
                ],
                "terrain_correction": "Godot TwoBoneIK3D during stance",
            },
        },
        "textures": {
            "basecolor_master": str(texture_data["base_master_path"]),
            "metallic_roughness_master": str(texture_data["mr_master_path"]),
            "basecolor_game": str(texture_data["base_game_path"]),
            "metallic_roughness_game": str(texture_data["mr_game_path"]),
            "normal_game": str(bake_data["normal_path"]),
            "ao_game": str(bake_data["ao_path"]),
            "bake_errors": bake_data["errors"],
        },
        "outputs": {
            "godot_glb": str(args.output),
            "blender_source": str(args.source),
            "previews": [str(path) for path in previews],
        },
        "validation": {
            "rest_height_ok": 1.79 <= rest_height <= 1.83,
            "triangle_budget_ok": game_triangles <= args.target_triangles * 1.08,
            "unweighted_vertices": binding["unweighted_vertices"],
            "idle_deformed_height_m": round(deformed_height(low), 5),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    stamp(f"Complete: {game_triangles} triangles, {len(rig.data.bones)} bones")
    print(f"VILLAGER_GAME_ASSET={args.output}")
    print(f"VILLAGER_SOURCE={args.source}")
    print(f"VILLAGER_REPORT={args.report}")
    print(f"VILLAGER_TRIANGLES={game_triangles}")
    print(f"VILLAGER_HEIGHT_M={rest_height:.4f}")
    print(f"VILLAGER_ANIMATIONS={','.join(actions.keys())}")


if __name__ == "__main__":
    main()
