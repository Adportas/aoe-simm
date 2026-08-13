"""Generate three mature coconut-palm variants for the tabletop RTS scene.

The palms are authored in terrain metres and keep their pivots at ground level.
Godot presents terrain at 1:400 while the villager is presented at 1:180, so
the 12 m authored height reads as roughly 3.0x the villager's visible height.
Each open 9 m crown uses 32-34 curved alpha cards sampled from the coconut
cells in the checked-in 2 x 4 frond atlas. Geometry, UV selection and preview
are deterministic.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


CHARACTER_HEIGHT_M = 1.82
CHARACTER_RELATIVE_SCALE = 400.0 / 180.0


@dataclass(frozen=True)
class PalmSpec:
    key: str
    label: str
    growth_form: str
    height_m: float
    trunk_height_m: float
    trunk_base_radius_m: float
    trunk_top_radius_m: float
    frond_length_m: float
    frond_count: int
    sway_x_m: float
    sway_y_m: float
    crown_rotation: float


PALM_SPECS = (
    PalmSpec(
        "small", "Palm_Coconut_Adult_A_12m", "coconut",
        12.0, 10.25, 0.36, 0.235, 4.35, 32, 0.62, -0.14, 0.18,
    ),
    PalmSpec(
        "medium", "Palm_Coconut_Adult_B_12m", "coconut",
        12.0, 10.20, 0.38, 0.240, 4.50, 34, -0.54, 0.32, 1.07,
    ),
    PalmSpec(
        "tall", "Palm_Coconut_Adult_C_12m", "coconut",
        12.0, 10.30, 0.40, 0.245, 4.42, 33, 0.24, -0.70, 2.21,
    ),
)

FROND_ATLAS_CELLS = {
    "fan": (0, 1),
    "date": (2, 3, 4),
    "coconut": (5, 6, 7),
}
ATLAS_COLUMNS = 2
ATLAS_ROWS = 4
ATLAS_INSET = 2.0 / 2048.0
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def output_root() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if arguments:
        return Path(arguments[0]).expanduser().resolve()
    return (
        project_root()
        / "assets"
        / "environment"
        / "island_biome"
        / "palms"
    )


def palm_texture_root() -> Path:
    return (
        project_root()
        / "assets"
        / "environment"
        / "island_biome"
        / "textures"
        / "palms"
    )


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color
    material.roughness = roughness
    material.use_backface_culling = False
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = roughness
    return material


def make_frond_material() -> bpy.types.Material:
    texture_root = palm_texture_root()
    albedo_path = texture_root / "palm_frond_atlas_albedo_v1.png"
    normal_path = texture_root / "palm_frond_atlas_normal_v1.png"
    for path in (albedo_path, normal_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing palm atlas texture {path}; run "
                "tools/build_palm_frond_atlas.sh first"
            )

    material = bpy.data.materials.new("Palm_Frond_Cards_Atlas")
    material.use_nodes = True
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    material.use_backface_culling = False
    material["godot_card_mode"] = True
    material["alpha_clip"] = 0.42
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    if hasattr(material, "blend_method"):
        material.blend_method = "CLIP"
    if hasattr(material, "alpha_threshold"):
        material.alpha_threshold = 0.42

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520.0, 0.0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (220.0, 0.0)
    shader.inputs["Roughness"].default_value = 0.82
    shader.inputs["Specular IOR Level"].default_value = 0.32

    albedo_image = bpy.data.images.load(str(albedo_path), check_existing=True)
    albedo_image.colorspace_settings.name = "sRGB"
    albedo = nodes.new("ShaderNodeTexImage")
    albedo.name = "Palm_Frond_Atlas_Albedo"
    albedo.label = "2x4 palm-frond atlas (RGBA)"
    albedo.image = albedo_image
    albedo.interpolation = "Linear"
    albedo.extension = "CLIP"
    albedo.location = (-500.0, 100.0)
    links.new(albedo.outputs["Color"], shader.inputs["Base Color"])
    links.new(albedo.outputs["Alpha"], shader.inputs["Alpha"])

    normal_image = bpy.data.images.load(str(normal_path), check_existing=True)
    normal_image.colorspace_settings.name = "Non-Color"
    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Palm_Frond_Atlas_Normal"
    normal_texture.image = normal_image
    normal_texture.interpolation = "Linear"
    normal_texture.extension = "CLIP"
    normal_texture.location = (-500.0, -220.0)
    normal_node = nodes.new("ShaderNodeNormalMap")
    normal_node.inputs["Strength"].default_value = 0.55
    normal_node.location = (-80.0, -180.0)
    texture_coordinates = nodes.new("ShaderNodeTexCoord")
    texture_coordinates.location = (-760.0, 10.0)
    links.new(texture_coordinates.outputs["UV"], albedo.inputs["Vector"])
    links.new(
        texture_coordinates.outputs["UV"],
        normal_texture.inputs["Vector"],
    )
    links.new(normal_texture.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "trunk": make_material(
            "Palm_Trunk_Coconut_GrayBrown", (0.24, 0.18, 0.12, 1.0), 0.92
        ),
        "ring": make_material(
            "Palm_Trunk_Coconut_Rings", (0.32, 0.25, 0.17, 1.0), 0.96
        ),
        "crown": make_material(
            "Palm_Crown_Fiber", (0.15, 0.085, 0.035, 1.0), 0.94
        ),
        "frond": make_frond_material(),
        "fruit_green": make_material(
            "Palm_Coconuts_Green", (0.24, 0.38, 0.08, 1.0), 0.82
        ),
        "fruit_gold": make_material(
            "Palm_Coconuts_Gold", (0.58, 0.38, 0.07, 1.0), 0.84
        ),
    }


def trunk_center(spec: PalmSpec, t: float) -> Vector:
    eased = t * t * (3.0 - 2.0 * t)
    organic_bend = math.sin(math.pi * t) * math.sin(
        spec.crown_rotation + t * 2.4
    )
    return Vector(
        (
            spec.sway_x_m * eased + organic_bend * 0.075,
            spec.sway_y_m * eased + organic_bend * 0.055,
            spec.trunk_height_m * t,
        )
    )


def build_trunk(
    spec: PalmSpec,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    sides = 12
    levels = 18
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    material_indices: list[int] = []

    for level in range(levels + 1):
        t = level / levels
        center = trunk_center(spec, t)
        base_falloff = max(0.0, 1.0 - t / 0.18) ** 2
        body_radius = spec.trunk_top_radius_m * (1.08 - 0.08 * t)
        radius = (
            body_radius
            + (spec.trunk_base_radius_m - body_radius) * base_falloff
        ) * (1.0 + 0.035 * math.sin(level * 2.35 + spec.crown_rotation))
        twist = level * 0.075
        for side in range(sides):
            angle = math.tau * side / sides + twist
            vertices.append(
                (
                    center.x + math.cos(angle) * radius,
                    center.y + math.sin(angle) * radius,
                    center.z,
                )
            )

    for level in range(levels):
        for side in range(sides):
            next_side = (side + 1) % sides
            lower = level * sides + side
            lower_next = level * sides + next_side
            upper = (level + 1) * sides + side
            upper_next = (level + 1) * sides + next_side
            faces.append((lower, lower_next, upper_next, upper))
            ring_phase = round(spec.crown_rotation * 3.0)
            material_indices.append(1 if (level + ring_phase) % 4 == 1 else 0)

    faces.append(tuple(reversed(range(sides))))
    material_indices.append(0)
    top_start = levels * sides
    faces.append(tuple(top_start + side for side in range(sides)))
    material_indices.append(0)

    mesh = bpy.data.meshes.new(f"{spec.label}.TrunkMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(materials["trunk"])
    mesh.materials.append(materials["ring"])
    for polygon, material_index in zip(mesh.polygons, material_indices):
        polygon.material_index = material_index
        polygon.use_smooth = True
    mesh.update()
    obj = bpy.data.objects.new(f"{spec.label}_Trunk", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def atlas_uv_rect(cell_index: int) -> tuple[float, float, float, float]:
    column = cell_index % ATLAS_COLUMNS
    row_from_top = cell_index // ATLAS_COLUMNS
    u_min = column / ATLAS_COLUMNS + ATLAS_INSET
    u_max = (column + 1) / ATLAS_COLUMNS - ATLAS_INSET
    v_min = 1.0 - (row_from_top + 1) / ATLAS_ROWS + ATLAS_INSET
    v_max = 1.0 - row_from_top / ATLAS_ROWS - ATLAS_INSET
    return u_min, u_max, v_min, v_max


def build_frond_cards(
    spec: PalmSpec,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    segment_count = 5
    crown = trunk_center(spec, 1.0) + Vector((0.0, 0.0, -0.08))
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    uv_coordinates: list[tuple[float, float]] = []
    cell_choices = FROND_ATLAS_CELLS[spec.growth_form]
    for index in range(spec.frond_count):
        ring = index % 4
        azimuth = (
            index * GOLDEN_ANGLE
            + spec.crown_rotation
            + ring * 0.085
            + math.sin(index * 1.77 + spec.crown_rotation) * 0.055
        )
        direction = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
        side = Vector((-math.sin(azimuth), math.cos(azimuth), 0.0))
        length = spec.frond_length_m * (
            0.90 + 0.14 * math.sin(index * 2.17 + spec.crown_rotation)
        )
        if ring == 3:
            length *= 0.72
        card_width = length * 0.48 * (
            0.94 + 0.08 * math.sin(index * 1.31 + spec.crown_rotation)
        )
        cell_index = cell_choices[index % len(cell_choices)]
        u_min, u_max, v_min, v_max = atlas_uv_rect(cell_index)
        vertex_start = len(vertices)

        for segment in range(segment_count + 1):
            t = segment / segment_count
            radial = length * t
            ring_lift = (-0.035, 0.035, 0.14, 0.34)[ring]
            droop = (0.66, 0.50, 0.35, 0.16)[ring]
            lift_factor = (0.09, 0.14, 0.20, 0.27)[ring]
            lift = (
                math.sin(math.pi * t) * length * lift_factor
                + t * length * ring_lift
            )
            droop_height = (t**1.68) * length * droop
            ripple = math.sin(
                t * math.pi * 2.0 + index * 0.9 + spec.crown_rotation
            ) * 0.045
            center = (
                crown
                + direction * radial
                + Vector((0.0, 0.0, lift - droop_height + ripple))
            )
            half_width = card_width * 0.5 * (
                0.92 + 0.08 * math.sin(math.pi * t)
            )
            fold = Vector((0.0, 0.0, half_width * 0.06 * math.sin(math.pi * t)))
            vertices.append(tuple(center - side * half_width + fold))
            vertices.append(tuple(center + side * half_width - fold))
            v = v_min + (v_max - v_min) * t
            uv_coordinates.append((u_min, v))
            uv_coordinates.append((u_max, v))

        for segment in range(segment_count):
            base = vertex_start + segment * 2
            # Winding towards +Z keeps the visible crown side front-facing.
            faces.append((base, base + 2, base + 3, base + 1))

    mesh = bpy.data.meshes.new(f"{spec.label}.FrondCardsMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(materials["frond"])
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = uv_coordinates[vertex_index]
    mesh.update()
    obj = bpy.data.objects.new(f"{spec.label}_FrondCards", mesh)
    obj["card_count"] = spec.frond_count
    obj["atlas_cells"] = ",".join(str(cell) for cell in cell_choices)
    bpy.context.collection.objects.link(obj)
    return obj


def add_ico_sphere(
    name: str,
    location: Vector,
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=1,
        radius=radius,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def add_coconut_cluster(
    spec: PalmSpec,
    materials: dict[str, bpy.types.Material],
    cluster_index: int,
) -> list[bpy.types.Object]:
    crown_center = trunk_center(spec, 1.0) + Vector((0.0, 0.0, -0.24))
    cluster_angle = (
        spec.crown_rotation + (cluster_index / 3.0) * math.tau + 0.38
    )
    cluster_direction = Vector(
        (math.cos(cluster_angle), math.sin(cluster_angle), 0.0)
    )
    parts: list[bpy.types.Object] = []
    for fruit_index in range(5):
        layer = fruit_index // 3
        spread_angle = cluster_angle + (fruit_index % 3 - 1) * 0.36
        spread_direction = Vector(
            (math.cos(spread_angle), math.sin(spread_angle), 0.0)
        )
        fruit_position = (
            crown_center
            + cluster_direction * (0.31 + layer * 0.09)
            + spread_direction * (fruit_index % 3 - 1) * 0.105
            + Vector((0.0, 0.0, -0.16 - layer * 0.24 - (fruit_index % 2) * 0.07))
        )
        material = (
            materials["fruit_gold"]
            if (cluster_index + fruit_index + round(spec.crown_rotation * 2.0)) % 4 == 0
            else materials["fruit_green"]
        )
        coconut = add_ico_sphere(
            f"{spec.label}_Coconut_{cluster_index:02d}_{fruit_index:02d}",
            fruit_position,
            0.19 + 0.015 * ((cluster_index + fruit_index) % 2),
            material,
        )
        coconut.scale.z = 1.18
        parts.append(coconut)
    return parts


def join_palm(
    spec: PalmSpec,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    parts: list[bpy.types.Object] = [build_trunk(spec, materials)]
    crown_center = trunk_center(spec, 1.0) + Vector((0.0, 0.0, -0.15))
    parts.append(
        add_ico_sphere(
            f"{spec.label}_Crown",
            crown_center,
            spec.trunk_top_radius_m * 1.55,
            materials["crown"],
        )
    )

    parts.append(build_frond_cards(spec, materials))

    for cluster_index in range(3):
        parts.extend(add_coconut_cluster(spec, materials, cluster_index))

    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    palm = bpy.context.object
    palm.name = spec.label
    palm.data.name = f"{spec.label}.Mesh"
    editable_mesh = bmesh.new()
    editable_mesh.from_mesh(palm.data)
    bmesh.ops.triangulate(editable_mesh, faces=list(editable_mesh.faces))
    editable_mesh.to_mesh(palm.data)
    editable_mesh.free()
    palm.data.update()
    palm["asset_family"] = "AoE-style tabletop tropical palms"
    palm["size_class"] = spec.key
    palm["growth_form"] = spec.growth_form
    palm["frond_geometry"] = "curved_alpha_clip_cards"
    palm["frond_card_count"] = spec.frond_count
    palm["frond_atlas_cells"] = ",".join(
        str(cell) for cell in FROND_ATLAS_CELLS[spec.growth_form]
    )
    palm["authored_height_m"] = spec.height_m
    palm["authored_crown_diameter_m"] = round(spec.frond_length_m * 2.0, 2)
    palm["coconut_cluster_count"] = 3
    palm["coconut_count"] = 15
    palm["visible_height_vs_villager"] = round(
        spec.height_m / (CHARACTER_HEIGHT_M * CHARACTER_RELATIVE_SCALE),
        3,
    )
    palm["pivot"] = "ground"
    return palm


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def export_placeholder_image(
    name: str,
    color: tuple[float, float, float, float],
) -> bpy.types.Image:
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.new(name, width=4, height=4, alpha=True)
        image.generated_color = color
    return image


def export_glb(obj: bpy.types.Object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    select_only(obj)
    # Godot binds the shared 2K maps by material name. Embedding them in each
    # of the three GLBs would duplicate ~12 MB, so the transport material keeps
    # tiny alpha/normal placeholders while retaining UV0 and tangent export.
    frond_material = bpy.data.materials.get("Palm_Frond_Cards_Atlas")
    albedo_node = frond_material.node_tree.nodes.get("Palm_Frond_Atlas_Albedo")
    normal_node = frond_material.node_tree.nodes.get("Palm_Frond_Atlas_Normal")
    original_albedo = albedo_node.image
    original_normal = normal_node.image
    albedo_node.image = export_placeholder_image(
        "Palm_Frond_GLTF_Transport_Albedo",
        (0.24, 0.55, 0.15, 1.0),
    )
    normal_node.image = export_placeholder_image(
        "Palm_Frond_GLTF_Transport_Normal",
        (0.5, 0.5, 1.0, 1.0),
    )
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_materials="EXPORT",
            export_tangents=True,
            export_cameras=False,
            export_lights=False,
            export_animations=False,
        )
    finally:
        albedo_node.image = original_albedo
        normal_node.image = original_normal


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (
        target - obj.location
    ).to_track_quat("-Z", "Y").to_euler()


def add_preview_human(
    location: Vector,
    materials: dict[str, bpy.types.Material],
) -> list[bpy.types.Object]:
    """Add a simple 4.04 m reference for the villager's in-game height."""
    height = CHARACTER_HEIGHT_M * CHARACTER_RELATIVE_SCALE
    parts: list[bpy.types.Object] = []
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=10,
        radius=0.48,
        depth=height * 0.58,
        location=location + Vector((0, 0, height * 0.43)),
    )
    torso = bpy.context.object
    torso.name = "VillagerVisibleScaleReference"
    torso.data.materials.append(materials["ring"])
    parts.append(torso)
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2,
        radius=0.48,
        location=location + Vector((0, 0, height * 0.85)),
    )
    head = bpy.context.object
    head.data.materials.append(materials["ring"])
    parts.append(head)
    return parts


def build_preview(
    palms: dict[str, bpy.types.Object],
    materials: dict[str, bpy.types.Material],
    preview_path: Path,
) -> None:
    positions = {"small": -10.0, "medium": 0.0, "tall": 10.0}
    for spec in PALM_SPECS:
        palms[spec.key].location.x = positions[spec.key]

    bpy.ops.object.light_add(
        type="AREA",
        location=(-6.0, -9.0, 18.0),
    )
    key = bpy.context.object
    key.name = "PreviewKey"
    key.data.energy = 1700.0
    key.data.shape = "DISK"
    key.data.size = 8.0
    look_at(key, Vector((0.0, 0.0, 5.0)))

    bpy.ops.object.light_add(
        type="AREA",
        location=(15.0, -2.0, 10.0),
    )
    fill = bpy.context.object
    fill.name = "PreviewFill"
    fill.data.energy = 900.0
    fill.data.size = 7.0
    look_at(fill, Vector((1.0, 0.0, 5.0)))

    bpy.ops.object.camera_add(location=(25.0, -39.0, 18.0))
    camera = bpy.context.object
    camera.name = "PreviewCamera"
    camera.data.lens = 58.0
    look_at(camera, Vector((0.0, 0.0, 5.8)))

    scene = bpy.context.scene
    scene.camera = camera
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True
    scene.render.filepath = str(preview_path)
    scene.world.color = (0.045, 0.075, 0.115)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    root = output_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "source").mkdir(parents=True, exist_ok=True)
    preview_path = (
        project_root()
        / "previews"
        / "island_biome"
        / "palms.png"
    )
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    reset_scene()
    materials = build_materials()
    palms: dict[str, bpy.types.Object] = {}
    for spec in PALM_SPECS:
        palm = join_palm(spec, materials)
        palms[spec.key] = palm
        export_glb(palm, root / f"palm_{spec.key}.glb")

    source_positions = {"small": -10.0, "medium": 0.0, "tall": 10.0}
    for spec in PALM_SPECS:
        palms[spec.key].location.x = source_positions[spec.key]
    bpy.ops.wm.save_as_mainfile(
        filepath=str(root / "source" / "palms_aoe_style.blend")
    )
    build_preview(palms, materials, preview_path)
    print("PALM_ASSETS_OK")
    for spec in PALM_SPECS:
        ratio = spec.height_m / (
            CHARACTER_HEIGHT_M * CHARACTER_RELATIVE_SCALE
        )
        print(
            f"{spec.key}: {spec.height_m:.1f} m, "
            f"visible ratio {ratio:.2f}x"
        )


if __name__ == "__main__":
    main()
