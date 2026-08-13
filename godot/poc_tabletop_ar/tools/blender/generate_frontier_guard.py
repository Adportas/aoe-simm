"""Build the tabletop AR frontier guard and export it as an animated GLB.

The asset stays at its authored height (about 1.80 m). Godot presents it at
character scale 1:180 over terrain authored at scale 1:400. Everything is
generated deterministically so art-direction changes remain reproducible.
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Vector


CHARACTER_HEIGHT_M = 1.835
PARTS: list[tuple[bpy.types.Object, str]] = []


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def requested_output() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if arguments:
        return Path(arguments[0]).expanduser().resolve()
    return project_root() / "assets" / "units" / "human_base.glb"


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


def make_material(name, color, *, roughness, metallic=0.0, coat=0.0):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    result.diffuse_color = color
    result.roughness = roughness
    result.metallic = metallic
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if "Coat Weight" in shader.inputs:
        shader.inputs["Coat Weight"].default_value = coat
    if "Coat Roughness" in shader.inputs:
        shader.inputs["Coat Roughness"].default_value = max(0.18, roughness * 0.65)
    return result


def build_materials():
    return {
        "skin": make_material("Skin_Warm", (0.50, 0.235, 0.115, 1.0), roughness=0.58),
        "skin_blush": make_material("Skin_Blush", (0.58, 0.20, 0.105, 1.0), roughness=0.62),
        "indigo": make_material("Wool_Indigo", (0.012, 0.032, 0.135, 1.0), roughness=0.86),
        "indigo_dark": make_material("Wool_Indigo_Shadow", (0.004, 0.010, 0.035, 1.0), roughness=0.90),
        "cream": make_material("Wool_Cream", (0.52, 0.37, 0.20, 1.0), roughness=0.90),
        "wrap": make_material("Linen_Wrap", (0.30, 0.20, 0.11, 1.0), roughness=0.95),
        "leather": make_material("Leather_Oiled", (0.050, 0.013, 0.004, 1.0), roughness=0.66, coat=0.10),
        "leather_light": make_material("Leather_Worn", (0.105, 0.030, 0.007, 1.0), roughness=0.75),
        "leather_dark": make_material("Leather_Dark", (0.018, 0.004, 0.002, 1.0), roughness=0.73),
        "iron": make_material("Iron_Hammered", (0.11, 0.13, 0.16, 1.0), roughness=0.42, metallic=0.86),
        "iron_dark": make_material("Iron_Oxidized", (0.025, 0.032, 0.042, 1.0), roughness=0.54, metallic=0.74),
        "bronze": make_material("Bronze_Aged", (0.16, 0.055, 0.012, 1.0), roughness=0.43, metallic=0.76),
        "wood": make_material("Shield_Wood", (0.095, 0.025, 0.006, 1.0), roughness=0.80),
        "hair": make_material("Hair_Chestnut", (0.045, 0.012, 0.004, 1.0), roughness=0.86),
        "eye": make_material("Eye_White", (0.72, 0.63, 0.50, 1.0), roughness=0.36, coat=0.18),
        "iris": make_material("Iris_GreyBlue", (0.055, 0.12, 0.16, 1.0), roughness=0.30, coat=0.24),
        "pupil": make_material("Pupil", (0.003, 0.002, 0.001, 1.0), roughness=0.32),
    }


def texture_noise(x, y, seed):
    value = math.sin((x + seed * 0.137) * 12.9898 + (y + seed * 0.071) * 78.233) * 43758.5453
    return value - math.floor(value)


def add_surface_textures(materials):
    size = 128
    for material in materials.values():
        name = material.name.lower()
        if any(token in name for token in ("eye_", "iris_", "pupil")):
            continue
        seed = sum((index + 1) * ord(character) for index, character in enumerate(material.name)) % 997
        base = tuple(material.diffuse_color[:3])
        pixels = []
        heights = []
        for y in range(size):
            for x in range(size):
                noise = texture_noise(x, y, seed)
                fine = texture_noise(x * 3, y * 3, seed + 41)
                factor = 0.92 + noise * 0.13 + fine * 0.035
                if "wool" in name or "linen" in name:
                    weave = math.sin(x * math.pi * 0.52) * math.sin(y * math.pi * 0.52)
                    factor += weave * 0.055
                elif "leather" in name or "wood" in name:
                    grain = math.sin((x * 0.42 + math.sin(y * 0.17) * 2.0) + seed) * 0.045
                    factor += grain
                    if (x * 17 + y * 29 + seed) % 233 == 0:
                        factor += 0.20
                elif "iron" in name or "bronze" in name:
                    brushed = math.sin(y * 2.4 + noise * 2.0) * 0.035
                    factor += brushed
                    if (x * 11 + y * 37 + seed) % 281 == 0:
                        factor += 0.30
                elif "skin" in name:
                    factor = 0.965 + noise * 0.045 + fine * 0.015
                heights.append(factor)
                pixels.extend((
                    max(0.0, min(1.0, base[0] * factor)),
                    max(0.0, min(1.0, base[1] * factor)),
                    max(0.0, min(1.0, base[2] * factor)),
                    1.0,
                ))

        image_name = f"{material.name}_BaseColor"
        image = bpy.data.images.get(image_name) or bpy.data.images.new(image_name, width=size, height=size, alpha=True, float_buffer=True)
        image.colorspace_settings.name = "sRGB"
        image.pixels[:] = pixels
        image.update()
        image.pack()

        nodes = material.node_tree.nodes
        texture = nodes.new("ShaderNodeTexImage")
        texture.name = "Embedded surface detail"
        texture.label = "Embedded surface detail"
        texture.image = image
        texture.interpolation = "Linear"
        texture.extension = "REPEAT"
        texture.location = (-420.0, 120.0)
        shader = nodes.get("Principled BSDF")
        material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])

        normal_pixels = []
        normal_scale = 2.0 if "skin" in name else 4.5
        if "wool" in name or "linen" in name:
            normal_scale = 6.0
        elif "leather" in name or "wood" in name:
            normal_scale = 5.0
        for y in range(size):
            for x in range(size):
                left = heights[y * size + (x - 1) % size]
                right = heights[y * size + (x + 1) % size]
                down = heights[((y - 1) % size) * size + x]
                up = heights[((y + 1) % size) * size + x]
                normal = Vector(
                    ((left - right) * normal_scale, (down - up) * normal_scale, 1.0)
                ).normalized()
                normal_pixels.extend(
                    (normal.x * 0.5 + 0.5, normal.y * 0.5 + 0.5, normal.z * 0.5 + 0.5, 1.0)
                )

        normal_image = bpy.data.images.new(
            f"{material.name}_Normal",
            width=size,
            height=size,
            alpha=True,
            float_buffer=True,
        )
        normal_image.colorspace_settings.name = "Non-Color"
        normal_image.pixels[:] = normal_pixels
        normal_image.update()
        normal_image.pack()
        normal_texture = nodes.new("ShaderNodeTexImage")
        normal_texture.name = "Embedded normal detail"
        normal_texture.label = "Embedded normal detail"
        normal_texture.image = normal_image
        normal_texture.interpolation = "Linear"
        normal_texture.extension = "REPEAT"
        normal_texture.location = (-420.0, -140.0)
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = 0.20 if "skin" in name else 0.42
        normal_map.location = (-170.0, -140.0)
        material.node_tree.links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
        material.node_tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])


def generate_uvs(meshes):
    for obj in meshes:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")


def apply_modifier(obj, modifier) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def finish_mesh(obj, material, *, bevel=0.0, smooth=True):
    obj.data.materials.append(material)
    if bevel > 0.0:
        modifier = obj.modifiers.new("Edge softness", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
        apply_modifier(obj, modifier)
    if smooth:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj


def register(obj, bone):
    PARTS.append((obj, bone))
    return obj


def add_box(name, dimensions, location, material, *, rotation=(0.0, 0.0, 0.0), bevel=0.01):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish_mesh(obj, material, bevel=bevel, smooth=bevel > 0.0)


def add_ellipsoid(name, location, scale, material, *, segments=24, rings=12, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=1.0,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish_mesh(obj, material, smooth=True)


def add_cylinder_between(
    name,
    start,
    end,
    radius_start,
    radius_end,
    material,
    *,
    vertices=18,
    bevel=0.006,
):
    start_v = Vector(start)
    end_v = Vector(end)
    direction = end_v - start_v
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius_start,
        radius2=radius_end,
        depth=direction.length,
        location=(start_v + end_v) * 0.5,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return finish_mesh(obj, material, bevel=bevel, smooth=True)


def add_torus(name, location, major_radius, minor_radius, material, *, axis=(0.0, 0.0, 1.0)):
    axis_v = Vector(axis).normalized()
    bpy.ops.mesh.primitive_torus_add(
        major_segments=32,
        minor_segments=8,
        major_radius=major_radius,
        minor_radius=minor_radius,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = axis_v.to_track_quat("Z", "Y")
    return finish_mesh(obj, material, smooth=True)


def add_mesh(name, vertices, faces, material, *, solidify=0.0, bevel=0.0, smooth=False):
    mesh = bpy.data.meshes.new(f"{name}.Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    if solidify > 0.0:
        modifier = obj.modifiers.new("Cloth thickness", "SOLIDIFY")
        modifier.thickness = solidify
        modifier.offset = 0.0
        apply_modifier(obj, modifier)
    if bevel > 0.0:
        modifier = obj.modifiers.new("Soft edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        apply_modifier(obj, modifier)
    if smooth:
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    return obj


def add_ring_body(name, rings, material, *, segments=20):
    vertices = []
    for z, radius_x, radius_y in rings:
        for index in range(segments):
            angle = math.tau * index / segments
            vertices.append((radius_x * math.cos(angle), radius_y * math.sin(angle), z))
    faces = []
    for ring_index in range(len(rings) - 1):
        lower = ring_index * segments
        upper = (ring_index + 1) * segments
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower + index, lower + following, upper + following, upper + index))
    faces.append(tuple(reversed(range(segments))))
    top_start = (len(rings) - 1) * segments
    faces.append(tuple(top_start + index for index in range(segments)))
    return add_mesh(name, vertices, faces, material, bevel=0.005, smooth=True)


def add_trapezoid_panel(name, top_z, bottom_z, top_half_width, bottom_half_width, y, thickness, material):
    front_y = y - thickness * 0.5
    back_y = y + thickness * 0.5
    vertices = [
        (-top_half_width, front_y, top_z),
        (top_half_width, front_y, top_z),
        (bottom_half_width, front_y, bottom_z),
        (-bottom_half_width, front_y, bottom_z),
        (-top_half_width, back_y, top_z),
        (top_half_width, back_y, top_z),
        (bottom_half_width, back_y, bottom_z),
        (-bottom_half_width, back_y, bottom_z),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    return add_mesh(name, vertices, faces, material, bevel=0.008)


def add_lamella(name, location, width, height, thickness, material, *, yaw=0.0):
    outline = [
        (-0.50 * width, 0.50 * height),
        (0.50 * width, 0.50 * height),
        (0.48 * width, -0.18 * height),
        (0.32 * width, -0.48 * height),
        (0.0, -0.62 * height),
        (-0.32 * width, -0.48 * height),
        (-0.48 * width, -0.18 * height),
    ]
    vertices = []
    for y in (-thickness * 0.5, thickness * 0.5):
        vertices.extend((x, y, z) for x, z in outline)
    count = len(outline)
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index, following, count + following, count + index))
    obj = add_mesh(name, vertices, faces, material, bevel=0.003, smooth=False)
    obj.location = location
    obj.rotation_euler[2] = yaw
    return obj


def add_shoulder_shell(name, center, material):
    center = Vector(center)
    columns = (-1.0, -0.5, 0.0, 0.5, 1.0)
    rows = (-1.0, 0.0, 1.0)
    vertices = []
    for row in rows:
        for column in columns:
            x = center.x + column * 0.108
            y = center.y + row * 0.090
            z = center.z + 0.052 * (1.0 - column * column) - 0.018 * abs(row)
            vertices.append((x, y, z))
    faces = []
    for row in range(len(rows) - 1):
        for column in range(len(columns) - 1):
            start = row * len(columns) + column
            faces.append(
                (start, start + 1, start + 1 + len(columns), start + len(columns))
            )
    return add_mesh(
        name,
        vertices,
        faces,
        material,
        solidify=0.014,
        bevel=0.006,
        smooth=True,
    )


def add_beard_shell(name, material):
    columns = (-1.0, -0.5, 0.0, 0.5, 1.0)
    rows = (
        (1.540, -0.151, 0.094),
        (1.515, -0.169, 0.104),
        (1.482, -0.173, 0.086),
        (1.448, -0.164, 0.030),
    )
    vertices = []
    for row_index, (z, front_y, half_width) in enumerate(rows):
        for column in columns:
            edge_recede = 0.014 * column * column
            top_jawline = 0.045 * abs(column) if row_index == 0 else 0.0
            lower_point = 0.026 * abs(column) if row_index == len(rows) - 1 else 0.0
            vertices.append(
                (
                    column * half_width,
                    front_y + edge_recede,
                    z + top_jawline + lower_point,
                )
            )
    faces = []
    for row in range(len(rows) - 1):
        for column in range(len(columns) - 1):
            start = row * len(columns) + column
            faces.append(
                (start, start + len(columns), start + 1 + len(columns), start + 1)
            )
    obj = add_mesh(name, vertices, faces, material, smooth=True)
    subdivision = obj.modifiers.new("Sculpted beard curvature", "SUBSURF")
    subdivision.subdivision_type = "CATMULL_CLARK"
    subdivision.levels = 2
    subdivision.render_levels = 2
    apply_modifier(obj, subdivision)
    thickness = obj.modifiers.new("Beard volume", "SOLIDIFY")
    thickness.thickness = 0.012
    thickness.offset = 0.0
    apply_modifier(obj, thickness)
    softness = obj.modifiers.new("Beard edge softness", "BEVEL")
    softness.width = 0.003
    softness.segments = 2
    apply_modifier(obj, softness)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def add_revolved_profile(name, profile, material, *, segments=32):
    vertices = []
    for radius, z in profile:
        for index in range(segments):
            angle = math.tau * index / segments
            vertices.append((radius * math.cos(angle), radius * math.sin(angle), z))
    faces = []
    for row in range(len(profile) - 1):
        lower = row * segments
        upper = (row + 1) * segments
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower + index, lower + following, upper + following, upper + index))
    faces.append(tuple(reversed(range(segments))))
    return add_mesh(name, vertices, faces, material, smooth=True)


def add_sector(name, center_x, center_z, radius, start_angle, end_angle, front_y, material):
    points = [(center_x, front_y, center_z)]
    steps = 4
    for index in range(steps + 1):
        angle = start_angle + (end_angle - start_angle) * index / steps
        points.append((center_x + radius * math.cos(angle), front_y, center_z + radius * math.sin(angle)))
    faces = [(0, index, index + 1) for index in range(1, len(points) - 1)]
    return add_mesh(name, points, faces, material, solidify=0.004, bevel=0.001)


def add_blade(name, start, tip, half_width, thickness, material):
    start_v = Vector(start)
    tip_v = Vector(tip)
    length = (tip_v - start_v).length
    vertices = [
        (-half_width, 0.0, 0.0), (0.0, -thickness, 0.0),
        (half_width, 0.0, 0.0), (0.0, thickness, 0.0),
        (-half_width * 0.72, 0.0, length * 0.78),
        (0.0, -thickness * 0.72, length * 0.78),
        (half_width * 0.72, 0.0, length * 0.78),
        (0.0, thickness * 0.72, length * 0.78),
        (0.0, 0.0, length),
    ]
    faces = [
        (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        (4, 5, 8), (5, 6, 8), (6, 7, 8), (7, 4, 8), (3, 2, 1, 0),
    ]
    obj = add_mesh(name, vertices, faces, material, bevel=0.002, smooth=True)
    obj.location = start_v
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (tip_v - start_v).to_track_quat("Z", "Y")
    return obj


def add_armature():
    armature_data = bpy.data.armatures.new("FrontierGuardRig")
    armature = bpy.data.objects.new("FrontierGuardRig", armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    definitions = [
        ("Root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.16), None),
        ("Pelvis", (0.0, 0.0, 0.78), (0.0, 0.0, 0.96), "Root"),
        ("Spine", (0.0, 0.0, 0.91), (0.0, 0.0, 1.25), "Pelvis"),
        ("Chest", (0.0, 0.0, 1.18), (0.0, 0.0, 1.45), "Spine"),
        ("Neck", (0.0, 0.0, 1.43), (0.0, 0.0, 1.54), "Chest"),
        ("Head", (0.0, 0.0, 1.51), (0.0, 0.0, 1.72), "Neck"),
        ("UpperArm.L", (-0.285, 0.0, 1.39), (-0.465, 0.0, 1.18), "Chest"),
        ("LowerArm.L", (-0.465, 0.0, 1.18), (-0.50, -0.012, 0.98), "UpperArm.L"),
        ("Hand.L", (-0.50, -0.012, 0.98), (-0.50, -0.02, 0.86), "LowerArm.L"),
        ("UpperArm.R", (0.285, 0.0, 1.39), (0.465, 0.0, 1.18), "Chest"),
        ("LowerArm.R", (0.465, 0.0, 1.18), (0.50, -0.012, 0.98), "UpperArm.R"),
        ("Hand.R", (0.50, -0.012, 0.98), (0.50, -0.02, 0.86), "LowerArm.R"),
        ("Thigh.L", (-0.13, 0.0, 0.84), (-0.14, 0.0, 0.48), "Pelvis"),
        ("Shin.L", (-0.14, 0.0, 0.48), (-0.14, -0.008, 0.13), "Thigh.L"),
        ("Foot.L", (-0.14, -0.008, 0.13), (-0.14, -0.19, 0.065), "Shin.L"),
        ("Thigh.R", (0.13, 0.0, 0.84), (0.14, 0.0, 0.48), "Pelvis"),
        ("Shin.R", (0.14, 0.0, 0.48), (0.14, -0.008, 0.13), "Thigh.R"),
        ("Foot.R", (0.14, -0.008, 0.13), (0.14, -0.19, 0.065), "Shin.R"),
    ]
    bones = {}
    for name, head, tail, parent in definitions:
        bone = armature_data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0
        if parent:
            bone.parent = bones[parent]
        bones[name] = bone
    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "XYZ"
    bpy.ops.object.mode_set(mode="OBJECT")

    armature.show_in_front = True
    armature.hide_render = True
    armature["asset_name"] = "Frontier Guard"
    armature["height_m"] = 1.80
    armature["maximum_visual_height_m"] = CHARACTER_HEIGHT_M
    armature["terrain_scale"] = "1:400"
    armature["presentation_scale"] = "1:180"
    armature["art_direction"] = "early medieval frontier guard; indigo, leather, iron, cream"
    return armature


def build_body(materials):
    register(
        add_ring_body(
            "Torso_Undertunic",
            [(0.91, 0.225, 0.135), (1.05, 0.255, 0.15), (1.27, 0.305, 0.17), (1.41, 0.29, 0.16)],
            materials["indigo_dark"],
        ),
        "Spine",
    )
    register(add_ellipsoid("Pelvis_Padded", (0.0, 0.015, 0.88), (0.245, 0.145, 0.19), materials["indigo_dark"]), "Pelvis")
    register(add_trapezoid_panel("Tabard_Front", 1.035, 0.70, 0.155, 0.205, -0.165, 0.025, materials["indigo"]), "Pelvis")
    register(add_trapezoid_panel("Tabard_Back", 1.025, 0.72, 0.15, 0.19, 0.145, 0.024, materials["indigo_dark"]), "Pelvis")

    for side in (-1.0, 1.0):
        register(
            add_cylinder_between(
                f"Tabard_Trim_{side:+.0f}",
                (side * 0.158, -0.184, 1.0),
                (side * 0.195, -0.184, 0.72),
                0.010,
                0.010,
                materials["cream"],
                vertices=12,
                bevel=0.002,
            ),
            "Pelvis",
        )
    register(add_box("Tabard_Hem", (0.39, 0.018, 0.026), (0.0, -0.185, 0.725), materials["cream"], bevel=0.006), "Pelvis")
    register(add_ring_body("War_Belt", [(0.955, 0.258, 0.162), (1.005, 0.258, 0.162)], materials["leather_dark"]), "Pelvis")
    register(add_box("Belt_Buckle", (0.075, 0.030, 0.067), (0.0, -0.174, 0.981), materials["bronze"], bevel=0.012), "Pelvis")
    register(add_box("Buckle_Inset", (0.038, 0.010, 0.032), (0.0, -0.193, 0.981), materials["leather_dark"], bevel=0.006), "Pelvis")

    for side in (-1.0, 1.0):
        register(
            add_cylinder_between(
                f"Armor_Strap_{side:+.0f}",
                (side * 0.225, -0.14, 1.40),
                (side * 0.17, -0.172, 1.06),
                0.025,
                0.023,
                materials["leather_dark"],
                vertices=12,
                bevel=0.003,
            ),
            "Spine",
        )

    for row in range(7):
        z = 1.335 - row * 0.050
        count = 9 if row % 2 == 0 else 8
        first_angle = -56.0 if count == 9 else -49.0
        for column in range(count):
            angle_degrees = first_angle + column * 14.0
            angle = math.radians(angle_degrees)
            x = 0.286 * math.sin(angle)
            y = -0.169 * math.cos(angle) - 0.010
            plate_material = (
                materials["leather_light"]
                if (row * 5 + column * 3) % 23 == 0
                else materials["leather"]
            )
            register(
                add_lamella(
                    f"Lamellar_R{row + 1}_C{column + 1}",
                    (x, y, z),
                    0.060,
                    0.057,
                    0.016,
                    plate_material,
                    yaw=angle,
                ),
                "Spine",
            )
            normal = Vector((math.sin(angle), -math.cos(angle), 0.0))
            position = Vector((x, y, z + 0.014)) + normal * 0.012
            register(
                add_ellipsoid(
                    f"Lamellar_Lacing_{row}_{column}",
                    position,
                    (0.0038, 0.0025, 0.0038),
                    materials["bronze"],
                    segments=10,
                    rings=5,
                ),
                "Spine",
            )
    register(
        add_cylinder_between(
            "Armor_Neckline",
            (-0.235, -0.183, 1.382),
            (0.235, -0.183, 1.382),
            0.012,
            0.012,
            materials["leather_dark"],
            vertices=14,
            bevel=0.003,
        ),
        "Spine",
    )

    register(add_ellipsoid("Tabard_Sun", (0.0, -0.196, 0.875), (0.055, 0.008, 0.055), materials["cream"], segments=24, rings=8), "Pelvis")
    for index in range(8):
        angle = math.tau * index / 8.0
        center = Vector((0.0, -0.197, 0.875)) + Vector((math.cos(angle), 0.0, math.sin(angle))) * 0.076
        register(
            add_box(
                f"Sun_Ray_{index + 1}",
                (0.033, 0.009, 0.012),
                center,
                materials["cream"],
                rotation=(0.0, angle, 0.0),
                bevel=0.004,
            ),
            "Pelvis",
        )


def build_legs(materials):
    for side, x in (("L", -0.14), ("R", 0.14)):
        thigh_bone = f"Thigh.{side}"
        shin_bone = f"Shin.{side}"
        foot_bone = f"Foot.{side}"
        register(add_cylinder_between(f"Trouser_{side}", (x * 0.93, 0.0, 0.84), (x, 0.0, 0.49), 0.112, 0.092, materials["indigo_dark"], vertices=20), thigh_bone)
        register(add_ellipsoid(f"Knee_{side}", (x, -0.014, 0.48), (0.088, 0.095, 0.078), materials["leather"], segments=20, rings=10), shin_bone)
        register(add_cylinder_between(f"Wrapped_Shin_{side}", (x, 0.0, 0.45), (x, -0.008, 0.135), 0.080, 0.060, materials["wrap"], vertices=18), shin_bone)
        for index, z in enumerate((0.18, 0.235, 0.29, 0.345, 0.40)):
            register(add_torus(f"Leg_Wrap_{side}_{index + 1}", (x, -0.004, z), 0.066 + (z - 0.18) * 0.04, 0.007, materials["cream"]), shin_bone)
        register(add_cylinder_between(f"Boot_Ankle_{side}", (x, -0.01, 0.19), (x, -0.03, 0.075), 0.068, 0.074, materials["leather_dark"], vertices=18), foot_bone)
        register(add_ellipsoid(f"Boot_Foot_{side}", (x, -0.090, 0.070), (0.086, 0.145, 0.058), materials["leather"], segments=24, rings=12), foot_bone)
        register(add_box(f"Boot_Sole_{side}", (0.158, 0.235, 0.018), (x, -0.100, 0.015), materials["leather_dark"], bevel=0.007), foot_bone)
        register(add_box(f"Boot_Toecap_{side}", (0.142, 0.092, 0.042), (x, -0.183, 0.075), materials["leather"], bevel=0.014), foot_bone)
        register(add_cylinder_between(f"Boot_Instep_Strap_{side}", (x - 0.070, -0.126, 0.097), (x + 0.070, -0.126, 0.097), 0.010, 0.010, materials["leather_light"], vertices=12, bevel=0.003), foot_bone)


def build_arms_and_hands(materials):
    for side, sign in (("L", -1.0), ("R", 1.0)):
        shoulder = Vector((0.285 * sign, 0.0, 1.39))
        elbow = Vector((0.465 * sign, 0.0, 1.18))
        wrist = Vector((0.50 * sign, -0.012, 0.98))
        upper_axis = (elbow - shoulder).normalized()
        forearm_axis = (wrist - elbow).normalized()

        register(add_cylinder_between(f"Quilted_UpperArm_{side}", shoulder, elbow, 0.086, 0.072, materials["cream"], vertices=24), f"UpperArm.{side}")
        register(add_cylinder_between(f"Quilted_Forearm_{side}", elbow, wrist, 0.075, 0.060, materials["cream"], vertices=22), f"LowerArm.{side}")
        for index, t in enumerate((0.22, 0.48, 0.74)):
            point = shoulder.lerp(elbow, t)
            register(add_torus(f"Sleeve_Quilt_{side}_{index + 1}", point, 0.078 - t * 0.010, 0.005, materials["wrap"], axis=upper_axis), f"UpperArm.{side}")

        bracer_start = elbow.lerp(wrist, 0.30)
        register(add_cylinder_between(f"Leather_Bracer_{side}", bracer_start, wrist, 0.080, 0.066, materials["leather"], vertices=24, bevel=0.008), f"LowerArm.{side}")
        for index, t in enumerate((0.42, 0.76)):
            point = elbow.lerp(wrist, t)
            register(add_torus(f"Bracer_Strap_{side}_{index + 1}", point, 0.071 - t * 0.008, 0.007, materials["bronze"], axis=forearm_axis), f"LowerArm.{side}")

        register(add_ellipsoid(f"Elbow_Pad_{side}", elbow, (0.078, 0.085, 0.073), materials["leather"], segments=20, rings=10), f"LowerArm.{side}")
        shell_center = shoulder + Vector((0.010 * sign, 0.008, 0.010))
        register(
            add_shoulder_shell(
                f"Shoulder_Mantle_{side}",
                shell_center,
                materials["indigo"] if side == "L" else materials["leather"],
            ),
            f"UpperArm.{side}",
        )
        register(
            add_cylinder_between(
                f"Shoulder_Trim_{side}",
                (shell_center.x - 0.100, -0.084, shoulder.z - 0.005),
                (shell_center.x + 0.100, -0.084, shoulder.z - 0.005),
                0.007,
                0.007,
                materials["cream"] if side == "L" else materials["bronze"],
                vertices=12,
                bevel=0.002,
            ),
            f"UpperArm.{side}",
        )
        if side == "R":
            for offset in (-0.052, 0.052):
                register(
                    add_ellipsoid(
                        f"Shoulder_Rivet_{offset:+.3f}",
                        (shell_center.x + offset, -0.093, shoulder.z + 0.012),
                        (0.007, 0.004, 0.007),
                        materials["bronze"],
                        segments=12,
                        rings=6,
                    ),
                    f"UpperArm.{side}",
                )

        hand_center = Vector((0.50 * sign, -0.018, 0.925))
        register(add_ellipsoid(f"Glove_Palm_{side}", hand_center, (0.048, 0.043, 0.071), materials["leather_light"], segments=24, rings=12), f"Hand.{side}")
        for index, z_offset in enumerate((0.028, 0.005, -0.018, -0.041)):
            finger_z = hand_center.z + z_offset
            register(
                add_cylinder_between(
                    f"Glove_Finger_{side}_{index + 1}",
                    (hand_center.x - 0.033, -0.052, finger_z),
                    (hand_center.x + 0.033, -0.052, finger_z),
                    0.010,
                    0.009,
                    materials["leather_light"],
                    vertices=14,
                    bevel=0.003,
                ),
                f"Hand.{side}",
            )
        thumb_start = hand_center + Vector((-0.038 * sign, -0.026, 0.027))
        thumb_end = hand_center + Vector((-0.054 * sign, -0.041, -0.016))
        register(add_cylinder_between(f"Glove_Thumb_{side}", thumb_start, thumb_end, 0.016, 0.012, materials["leather_light"], vertices=14, bevel=0.004), f"Hand.{side}")
        register(add_torus(f"Glove_Cuff_{side}", wrist + Vector((0.0, 0.0, -0.010)), 0.058, 0.009, materials["leather_dark"], axis=forearm_axis), f"Hand.{side}")

def append_cc0_head(materials):
    component_path = project_root() / "art" / "source" / "blender_human_head_cc0.blend"
    requested = ("CC0_Head", "CC0_Sclera.L", "CC0_Sclera.R", "CC0_Iris.L", "CC0_Iris.R")
    if not component_path.exists():
        raise RuntimeError(f"Missing CC0 Blender head component: {component_path}")
    with bpy.data.libraries.load(str(component_path), link=False) as (source, destination):
        missing = [name for name in requested if name not in source.objects]
        if missing:
            raise RuntimeError(f"CC0 head component is missing objects: {missing}")
        destination.objects = list(requested)

    for obj in destination.objects:
        bpy.context.collection.objects.link(obj)
        obj.data.materials.clear()
        if obj.name == "CC0_Head":
            obj.data.materials.append(materials["skin"])
        elif "Sclera" in obj.name:
            obj.data.materials.append(materials["eye"])
        else:
            obj.data.materials.append(materials["iris"])
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj["source_asset"] = "Blender Human Base Meshes v1.0.0"
        obj["source_license"] = "CC0"
        register(obj, "Head")

    for side, x in (("L", 0.034), ("R", -0.034)):
        register(add_ellipsoid(f"Eye_White_{side}", (x, -0.143, 1.650), (0.025, 0.003, 0.010), materials["eye"], segments=20, rings=10), "Head")
        register(add_ellipsoid(f"Iris_Overlay_{side}", (x, -0.147, 1.650), (0.0075, 0.002, 0.0075), materials["iris"], segments=16, rings=8), "Head")
        register(add_ellipsoid(f"Pupil_{side}", (x, -0.149, 1.650), (0.0034, 0.0015, 0.0034), materials["pupil"], segments=14, rings=7), "Head")
        register(add_ellipsoid(f"Eye_Glint_{side}", (x - 0.0015, -0.151, 1.653), (0.0013, 0.0008, 0.0013), materials["eye"], segments=10, rings=5), "Head")
    register(add_cylinder_between("Brow_L", (0.010, -0.145, 1.682), (0.062, -0.139, 1.678), 0.006, 0.004, materials["hair"], vertices=12, bevel=0.002), "Head")
    register(add_cylinder_between("Brow_R", (-0.010, -0.145, 1.682), (-0.062, -0.139, 1.678), 0.006, 0.004, materials["hair"], vertices=12, bevel=0.002), "Head")


def build_head(materials):
    register(add_ring_body("Mail_Aventail", [(1.425, 0.174, 0.132), (1.485, 0.160, 0.124), (1.555, 0.138, 0.108)], materials["iron_dark"], segments=28), "Neck")
    for index, z in enumerate((1.447, 1.475, 1.503)):
        register(add_torus(f"Mail_Row_{index + 1}", (0.0, 0.010, z), 0.142 - index * 0.007, 0.006, materials["iron"], axis=(0.0, 0.0, 1.0)), "Neck")

    append_cc0_head(materials)
    register(add_cylinder_between("Mouth_Shadow", (-0.030, -0.144, 1.548), (0.030, -0.144, 1.548), 0.0035, 0.0035, materials["hair"], vertices=10, bevel=0.001), "Head")
    register(add_ellipsoid("Lower_Lip", (0.0, -0.148, 1.557), (0.026, 0.003, 0.005), materials["skin_blush"], segments=18, rings=8), "Head")

    register(add_beard_shell("Beard_Sculpt", materials["hair"]), "Head")
    for side, sign in (("L", -1.0), ("R", 1.0)):
        register(
            add_cylinder_between(
                f"Moustache_{side}",
                (0.0, -0.166, 1.566),
                (0.052 * sign, -0.157, 1.551),
                0.007,
                0.003,
                materials["hair"],
                vertices=14,
                bevel=0.002,
            ),
            "Head",
        )
    for index, x in enumerate((-0.070, -0.035, 0.0, 0.035, 0.070)):
        end_z = 1.474 + abs(x) * 0.22
        register(
            add_cylinder_between(
                f"Beard_Lock_{index + 1}",
                (x, -0.176, 1.532),
                (x * 0.70, -0.168, end_z),
                0.006,
                0.0025,
                materials["hair"],
                vertices=10,
                bevel=0.002,
            ),
            "Head",
        )
    register(add_ellipsoid("Beard_Bead", (0.0, -0.171, 1.471), (0.010, 0.007, 0.011), materials["bronze"], segments=14, rings=7), "Head")

    helmet_profile = [
        (0.158, 1.672), (0.160, 1.695), (0.128, 1.738),
        (0.087, 1.782), (0.043, 1.818), (0.0, CHARACTER_HEIGHT_M),
    ]
    register(add_revolved_profile("Helmet_Cone", helmet_profile, materials["iron"], segments=48), "Head")
    register(add_torus("Helmet_Brow_Band", (0.0, 0.0, 1.694), 0.151, 0.010, materials["bronze"]), "Head")
    register(add_box("Helmet_Nasal", (0.025, 0.022, 0.148), (0.0, -0.162, 1.618), materials["iron"], bevel=0.006), "Head")
    register(add_cylinder_between("Helmet_Front_Ridge", (0.0, -0.158, 1.700), (0.0, -0.018, 1.823), 0.007, 0.004, materials["bronze"], vertices=12, bevel=0.002), "Head")
    for side, sign in (("L", -1.0), ("R", 1.0)):
        register(add_box(f"Helmet_Chin_Strap_{side}", (0.026, 0.018, 0.088), (0.124 * sign, -0.100, 1.596), materials["leather_dark"], rotation=(0.0, math.radians(7.0 * sign), math.radians(-8.0 * sign)), bevel=0.006), "Head")
    for index in range(7):
        angle = math.radians(-72.0 + index * 24.0)
        position = (0.152 * math.sin(angle), -0.152 * math.cos(angle), 1.695)
        register(add_ellipsoid(f"Helmet_Rivet_{index + 1}", position, (0.0075, 0.005, 0.0075), materials["bronze"], segments=12, rings=6), "Head")

def build_cape(materials):
    columns = (-1.0, -0.667, -0.333, 0.0, 0.333, 0.667, 1.0)
    rows = (
        (1.455, 0.070, 0.340),
        (1.340, 0.115, 0.350),
        (1.200, 0.155, 0.350),
        (1.040, 0.185, 0.340),
        (0.880, 0.170, 0.325),
        (0.720, 0.120, 0.300),
        (0.660, 0.092, 0.285),
    )
    vertices = []
    for row_index, (z, base_y, half_width) in enumerate(rows):
        for column_index, column in enumerate(columns):
            wave = 0.020 * math.sin(row_index * 1.25 + column_index * 1.35)
            center_fold = 0.016 * (1.0 - column * column)
            scallop = 0.018 * (column_index % 2) if row_index == len(rows) - 1 else 0.0
            vertices.append((column * half_width, base_y + wave + center_fold, z + scallop))
    faces = []
    for row in range(len(rows) - 1):
        for column in range(len(columns) - 1):
            start = row * len(columns) + column
            faces.append((start, start + 1, start + 1 + len(columns), start + len(columns)))
    register(add_mesh("Indigo_Cape", vertices, faces, materials["indigo"], solidify=0.012, bevel=0.006, smooth=True), "Chest")
    register(add_cylinder_between("Cape_Left_Border", (-0.34, 0.075, 1.45), (-0.285, 0.092, 0.67), 0.010, 0.010, materials["cream"], vertices=12, bevel=0.003), "Chest")
    register(add_cylinder_between("Cape_Right_Border", (0.34, 0.075, 1.45), (0.285, 0.092, 0.67), 0.010, 0.010, materials["cream"], vertices=12, bevel=0.003), "Chest")
    shoulder_flap = [(-0.35, -0.05, 1.48), (-0.17, -0.12, 1.48), (-0.01, -0.13, 1.44), (-0.05, -0.16, 1.27), (-0.20, -0.15, 1.23), (-0.32, -0.11, 1.25)]
    register(add_mesh("Cape_Shoulder_Flap", shoulder_flap, [(0, 5, 4, 3, 2, 1)], materials["indigo"], solidify=0.014, bevel=0.007, smooth=True), "Chest")
    register(add_ellipsoid("Cape_Clasp", (-0.185, -0.154, 1.43), (0.029, 0.008, 0.029), materials["bronze"], segments=20, rings=8), "Chest")
    register(add_torus("Cape_Clasp_Inlay", (-0.185, -0.162, 1.43), 0.020, 0.004, materials["iron_dark"], axis=(0.0, 1.0, 0.0)), "Chest")


def build_shield(materials):
    center = Vector((-0.565, -0.075, 1.065))
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.305, depth=0.045, location=center, rotation=(math.pi / 2.0, 0.0, 0.0))
    base = bpy.context.object
    base.name = "Shield_Wood_Core"
    register(finish_mesh(base, materials["wood"], bevel=0.006, smooth=True), "Hand.L")

    front_y = -0.101
    for index in range(12):
        start = math.tau * index / 12.0
        end = math.tau * (index + 1) / 12.0
        material = materials["indigo"] if index % 2 == 0 else materials["cream"]
        register(add_sector(f"Shield_Ray_{index + 1}", center.x, center.z, 0.268, start, end, front_y, material), "Hand.L")
    register(add_torus("Shield_Iron_Rim", (center.x, front_y - 0.009, center.z), 0.288, 0.019, materials["iron"], axis=(0.0, 1.0, 0.0)), "Hand.L")
    register(add_ellipsoid("Shield_Boss", (center.x, front_y - 0.029, center.z), (0.078, 0.039, 0.078), materials["iron"], segments=28, rings=14), "Hand.L")
    register(add_torus("Shield_Boss_Band", (center.x, front_y - 0.044, center.z), 0.076, 0.010, materials["bronze"], axis=(0.0, 1.0, 0.0)), "Hand.L")
    for index in range(8):
        angle = math.tau * index / 8.0
        position = (center.x + 0.262 * math.cos(angle), front_y - 0.018, center.z + 0.262 * math.sin(angle))
        register(add_ellipsoid(f"Shield_Rivet_{index + 1}", position, (0.011, 0.007, 0.011), materials["bronze"], segments=12, rings=6), "Hand.L")
    scratches = [
        ((-0.71, -0.125, 1.18), (-0.66, -0.125, 1.10)),
        ((-0.45, -0.125, 1.24), (-0.42, -0.125, 1.16)),
        ((-0.67, -0.125, 0.94), (-0.60, -0.125, 0.90)),
    ]
    for index, (start, end) in enumerate(scratches):
        register(add_cylinder_between(f"Shield_Scratch_{index + 1}", start, end, 0.006, 0.003, materials["leather_dark"], vertices=8, bevel=0.001), "Hand.L")


def build_sword(materials):
    pommel = Vector((0.478, -0.017, 1.025))
    grip_end = Vector((0.518, -0.040, 0.855))
    blade_start = Vector((0.526, -0.046, 0.825))
    blade_tip = Vector((0.675, -0.112, 0.205))
    register(add_cylinder_between("Sword_Grip", pommel, grip_end, 0.022, 0.021, materials["leather_dark"], vertices=16, bevel=0.004), "Hand.R")
    register(add_torus("Sword_Grip_Wrap_1", pommel.lerp(grip_end, 0.30), 0.024, 0.004, materials["bronze"], axis=(grip_end - pommel)), "Hand.R")
    register(add_torus("Sword_Grip_Wrap_2", pommel.lerp(grip_end, 0.68), 0.023, 0.004, materials["bronze"], axis=(grip_end - pommel)), "Hand.R")
    register(add_ellipsoid("Sword_Pommel", pommel + Vector((-0.008, 0.003, 0.015)), (0.038, 0.028, 0.038), materials["bronze"], segments=18, rings=9), "Hand.R")
    guard_center = Vector((0.522, -0.043, 0.84))
    register(add_cylinder_between("Sword_Crossguard", guard_center + Vector((-0.105, 0.0, 0.018)), guard_center + Vector((0.105, 0.0, -0.018)), 0.016, 0.016, materials["bronze"], vertices=14, bevel=0.004), "Hand.R")
    register(add_blade("Sword_Blade", blade_start, blade_tip, 0.043, 0.009, materials["iron"]), "Hand.R")
    register(add_cylinder_between("Sword_Fuller", blade_start + Vector((0.0, -0.010, 0.0)), blade_tip + Vector((0.0, -0.010, 0.025)), 0.005, 0.002, materials["iron_dark"], vertices=8, bevel=0.001), "Hand.R")
    register(add_cylinder_between("Scabbard", (0.19, 0.09, 0.98), (0.40, 0.11, 0.38), 0.044, 0.027, materials["leather_dark"], vertices=16, bevel=0.006), "Pelvis")
    register(add_torus("Scabbard_Throat", (0.19, 0.09, 0.98), 0.043, 0.009, materials["bronze"], axis=(0.21, 0.02, -0.60)), "Pelvis")
    register(add_ellipsoid("Scabbard_Chape", (0.40, 0.11, 0.38), (0.034, 0.028, 0.048), materials["bronze"], segments=16, rings=8, rotation=(0.0, math.radians(-18.0), 0.0)), "Pelvis")


def parent_to_bone(obj, armature, bone_name):
    world_matrix = obj.matrix_world.copy()
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world_matrix


def consolidate_parts(armature):
    groups = defaultdict(list)
    for obj, bone in PARTS:
        parent_to_bone(obj, armature, bone)
        groups[bone].append(obj)
    consolidated = []
    for bone, objects in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        if len(objects) > 1:
            bpy.ops.object.join()
        joined = bpy.context.object
        joined.name = f"FG_{bone.replace('.', '_')}"
        joined["rigid_attachment"] = bone
        consolidated.append(joined)
    return consolidated


def clear_pose(armature):
    for bone in armature.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def key_pose(armature, frame, rotations=None, locations=None):
    rotations = rotations or {}
    locations = locations or {}
    clear_pose(armature)
    for name, values in rotations.items():
        armature.pose.bones[name].rotation_euler = tuple(math.radians(value) for value in values)
    for name, values in locations.items():
        armature.pose.bones[name].location = values
    for bone in armature.pose.bones:
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        bone.keyframe_insert(data_path="location", frame=frame)


def make_action(armature, name, frame_end, poses, *, loop=True):
    action = bpy.data.actions.new(name)
    armature.animation_data_create()
    armature.animation_data.action = action
    for frame, rotations, locations in poses:
        key_pose(armature, frame, rotations, locations)
    action.use_frame_range = True
    action.frame_start = 1.0
    action.frame_end = float(frame_end)
    action["loop_mode"] = "linear" if loop else "none"
    action["fps"] = 24
    return action


def build_animations(armature):
    idle = make_action(
        armature,
        "Idle",
        49,
        [
            (
                1,
                {
                    "Pelvis": (0.0, 0.0, 1.4),
                    "Chest": (0.0, 0.0, -2.0),
                    "Head": (0.0, 0.0, 2.0),
                    "UpperArm.L": (2.0, 0.0, -2.0),
                    "UpperArm.R": (-2.0, 0.0, 2.0),
                    "Thigh.L": (1.5, 0.0, -1.0),
                    "Thigh.R": (-1.0, 0.0, 1.0),
                },
                {"Root": (0.0, 0.0, 0.0)},
            ),
            (
                25,
                {
                    "Pelvis": (0.0, 0.0, 1.0),
                    "Chest": (0.8, 0.0, 0.2),
                    "Head": (-0.7, 0.0, 0.0),
                    "UpperArm.L": (2.5, 0.0, -1.5),
                    "UpperArm.R": (-2.5, 0.0, 1.5),
                    "Thigh.L": (1.5, 0.0, -1.0),
                    "Thigh.R": (-1.0, 0.0, 1.0),
                },
                {"Root": (0.0, 0.0, 0.006)},
            ),
            (
                49,
                {
                    "Pelvis": (0.0, 0.0, 1.4),
                    "Chest": (0.0, 0.0, -2.0),
                    "Head": (0.0, 0.0, 2.0),
                    "UpperArm.L": (2.0, 0.0, -2.0),
                    "UpperArm.R": (-2.0, 0.0, 2.0),
                    "Thigh.L": (1.5, 0.0, -1.0),
                    "Thigh.R": (-1.0, 0.0, 1.0),
                },
                {"Root": (0.0, 0.0, 0.0)},
            ),
        ],
    )
    walk = make_action(
        armature,
        "Walk",
        25,
        [
            (1, {"Thigh.L": (28.0, 0.0, 0.0), "Thigh.R": (-28.0, 0.0, 0.0), "Shin.L": (8.0, 0.0, 0.0), "Shin.R": (22.0, 0.0, 0.0), "UpperArm.L": (-18.0, 0.0, 0.0), "UpperArm.R": (18.0, 0.0, 0.0), "Pelvis": (0.0, 0.0, -2.0)}, {"Root": (0.0, 0.0, 0.0)}),
            (7, {"Thigh.L": (3.0, 0.0, 0.0), "Thigh.R": (-4.0, 0.0, 0.0), "Shin.L": (4.0, 0.0, 0.0), "Shin.R": (32.0, 0.0, 0.0), "UpperArm.L": (-3.0, 0.0, 0.0), "UpperArm.R": (3.0, 0.0, 0.0)}, {"Root": (0.0, 0.0, 0.025)}),
            (13, {"Thigh.L": (-28.0, 0.0, 0.0), "Thigh.R": (28.0, 0.0, 0.0), "Shin.L": (22.0, 0.0, 0.0), "Shin.R": (8.0, 0.0, 0.0), "UpperArm.L": (18.0, 0.0, 0.0), "UpperArm.R": (-18.0, 0.0, 0.0), "Pelvis": (0.0, 0.0, 2.0)}, {"Root": (0.0, 0.0, 0.0)}),
            (19, {"Thigh.L": (-4.0, 0.0, 0.0), "Thigh.R": (3.0, 0.0, 0.0), "Shin.L": (32.0, 0.0, 0.0), "Shin.R": (4.0, 0.0, 0.0), "UpperArm.L": (3.0, 0.0, 0.0), "UpperArm.R": (-3.0, 0.0, 0.0)}, {"Root": (0.0, 0.0, 0.025)}),
            (25, {"Thigh.L": (28.0, 0.0, 0.0), "Thigh.R": (-28.0, 0.0, 0.0), "Shin.L": (8.0, 0.0, 0.0), "Shin.R": (22.0, 0.0, 0.0), "UpperArm.L": (-18.0, 0.0, 0.0), "UpperArm.R": (18.0, 0.0, 0.0), "Pelvis": (0.0, 0.0, -2.0)}, {"Root": (0.0, 0.0, 0.0)}),
        ],
    )
    attack = make_action(
        armature,
        "Attack",
        31,
        [
            (1, {"Chest": (0.0, 0.0, 0.0), "UpperArm.R": (0.0, 0.0, 0.0)}, {}),
            (9, {"Chest": (-6.0, 0.0, -12.0), "UpperArm.R": (50.0, -8.0, 32.0), "LowerArm.R": (25.0, 0.0, -10.0), "Head": (0.0, 0.0, 8.0)}, {}),
            (16, {"Chest": (10.0, 0.0, 12.0), "UpperArm.R": (-58.0, 4.0, -18.0), "LowerArm.R": (-18.0, 0.0, 5.0), "UpperArm.L": (-4.0, 0.0, -4.0)}, {"Root": (0.0, -0.025, -0.012)}),
            (23, {"Chest": (5.0, 0.0, 6.0), "UpperArm.R": (-25.0, 0.0, -10.0), "LowerArm.R": (-8.0, 0.0, 3.0)}, {}),
            (31, {"Chest": (0.0, 0.0, 0.0), "UpperArm.R": (0.0, 0.0, 0.0)}, {}),
        ],
        loop=False,
    )
    armature.animation_data.action = idle
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 49
    bpy.context.scene.render.fps = 24
    bpy.context.scene.frame_set(1)
    return {"Idle": idle, "Walk": walk, "Attack": attack}


def character_bounds(meshes):
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    for obj in meshes:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
    return minimum, maximum


def triangle_count(meshes):
    result = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        result += len(obj.data.loop_triangles)
    return result


def save_source(source_path, armature, meshes):
    source_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.wm.save_as_mainfile(filepath=str(source_path), check_existing=False)


def export_glb(path, armature, meshes):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = armature
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_area_light(name, location, energy, color, size, target=(0.0, 0.0, 1.0)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def render_preview(path, armature):
    scene = bpy.context.scene
    clear_pose(armature)
    armature.animation_data.action = bpy.data.actions.get("Idle")
    scene.frame_set(1)

    studio_floor = make_material("Studio_Floor", (0.028, 0.038, 0.052, 1.0), roughness=0.82)
    studio_plinth = make_material("Studio_Plinth", (0.065, 0.078, 0.095, 1.0), roughness=0.66)
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0.0, 0.0, -0.072))
    finish_mesh(bpy.context.object, studio_floor, smooth=False)
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=0.88, depth=0.075, location=(0.0, 0.0, -0.0375))
    finish_mesh(bpy.context.object, studio_plinth, bevel=0.018, smooth=True)

    camera_data = bpy.data.cameras.new("Hero_Camera")
    camera = bpy.data.objects.new("Hero_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (2.35, -4.55, 2.22)
    camera_data.lens = 82.0
    look_at(camera, (0.0, -0.02, 0.94))
    scene.camera = camera

    add_area_light("Key_Warm", (-3.2, -4.0, 4.8), 1050.0, (1.0, 0.72, 0.52), 3.0)
    add_area_light("Fill_Cool", (3.8, -2.2, 2.9), 720.0, (0.48, 0.65, 1.0), 3.4)
    add_area_light("Rim", (1.0, 3.6, 4.0), 1250.0, (0.55, 0.72, 1.0), 2.4)
    add_area_light("Face", (-0.5, -2.0, 2.5), 260.0, (1.0, 0.86, 0.72), 1.0, target=(0.0, 0.0, 1.62))

    scene.world.color = (0.006, 0.009, 0.015)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    path.parent.mkdir(parents=True, exist_ok=True)

    review_views = (
        (path, (2.35, -4.55, 2.22), (0.0, -0.02, 0.94)),
        (path.with_name("frontier_guard_front.png"), (0.0, -4.65, 1.92), (0.0, -0.02, 0.94)),
        (path.with_name("frontier_guard_rear.png"), (-2.45, 4.55, 2.18), (0.0, 0.04, 0.94)),
    )
    for view_path, camera_location, target in review_views:
        camera.location = camera_location
        look_at(camera, target)
        scene.render.filepath = str(view_path)
        bpy.ops.render.render(write_still=True)

    camera.location = (2.35, -4.55, 2.22)
    look_at(camera, (0.0, -0.02, 0.94))
    animated_views = (
        ("Walk", 13, path.with_name("frontier_guard_walk.png")),
        ("Attack", 16, path.with_name("frontier_guard_attack.png")),
    )
    for action_name, frame, view_path in animated_views:
        armature.animation_data.action = bpy.data.actions.get(action_name)
        scene.frame_set(frame)
        scene.render.filepath = str(view_path)
        bpy.ops.render.render(write_still=True)
    armature.animation_data.action = bpy.data.actions.get("Idle")
    scene.frame_set(1)


def normalize_character_height(armature, meshes, target_height=1.82):
    minimum, maximum = character_bounds(meshes)
    current_height = maximum.z - minimum.z
    scale_factor = target_height / current_height
    armature.scale = tuple(component * scale_factor for component in armature.scale)
    bpy.context.view_layer.update()
    minimum, maximum = character_bounds(meshes)
    armature["normalized_height_m"] = maximum.z - minimum.z
    armature["authoring_scale_factor"] = scale_factor


def build_character():
    materials = build_materials()
    armature = add_armature()
    build_body(materials)
    build_legs(materials)
    build_arms_and_hands(materials)
    build_head(materials)
    build_cape(materials)
    build_shield(materials)
    build_sword(materials)
    meshes = consolidate_parts(armature)
    generate_uvs(meshes)
    add_surface_textures(materials)
    normalize_character_height(armature, meshes)
    actions = build_animations(armature)
    return armature, meshes, actions


def main():
    reset_scene()
    armature, meshes, actions = build_character()
    output = requested_output()
    source = project_root() / "assets" / "units" / "source" / "frontier_guard.blend"
    preview = project_root() / "previews" / "frontier_guard_hero.png"
    minimum, maximum = character_bounds(meshes)
    authored_height = maximum.z - minimum.z
    if not 1.75 <= authored_height <= 1.85:
        raise RuntimeError(f"Character height {authored_height:.4f} m is outside the 1.80 m authoring envelope")
    save_source(source, armature, meshes)
    export_glb(output, armature, meshes)
    render_preview(preview, armature)
    print(f"TABLETOP_POC_EXPORTED={output}")
    print(f"TABLETOP_POC_SOURCE={source}")
    print(f"TABLETOP_POC_PREVIEW={preview}")
    print(f"TABLETOP_POC_CHARACTER_HEIGHT_M={authored_height:.4f}")
    print(f"TABLETOP_POC_TRIANGLES={triangle_count(meshes)}")
    print(f"TABLETOP_POC_MESHES={len(meshes)}")
    print(f"TABLETOP_POC_MATERIALS={len(bpy.data.materials) - 2}")
    print(f"TABLETOP_POC_ANIMATIONS={','.join(actions.keys())}")


if __name__ == "__main__":
    main()
