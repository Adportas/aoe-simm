"""Generate optimized island props and photo-derived terrain textures.

Everything is authored in terrain metres with a ground-level pivot. Godot
applies the diorama's 1:400 presentation scale and instances the GLBs with
MultiMesh for mobile AR. Shrubs use curved alpha cards sampled from the shared
2 x 4 broadleaf atlas instead of faceted leaf-cluster polyhedra.
"""

from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector


TEXTURE_SIZE = 512
SHRUB_ATLAS_CELLS = {
    "dense": (0, 1, 2, 3),
    "wild": (4, 5, 6, 7),
}
# BBox alfa útil (x0, y0, x1, y1) en cada celda 1024 x 512 del atlas. Además
# de conservar la proporción, recortar el vacío evita perder la mitad de los
# texels de cada card en transparencia.
SHRUB_ALPHA_BOUNDS = (
    (282, 33, 726, 479),
    (299, 34, 742, 480),
    (264, 28, 730, 478),
    (292, 31, 750, 480),
    (259, 23, 767, 478),
    (265, 23, 772, 479),
    (253, 18, 764, 474),
    (245, 21, 781, 471),
)
ATLAS_COLUMNS = 2
ATLAS_ROWS = 4
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


@dataclass(frozen=True)
class AssetRecord:
    key: str
    family: str
    obj: bpy.types.Object
    output_path: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def output_root() -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if arguments:
        return Path(arguments[0]).expanduser().resolve()
    return project_root() / "assets" / "environment" / "island_biome"


def shrub_texture_root() -> Path:
    return (
        project_root()
        / "assets"
        / "environment"
        / "island_biome"
        / "textures"
        / "shrubs"
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


def make_shrub_foliage_material() -> bpy.types.Material:
    texture_root = shrub_texture_root()
    albedo_path = texture_root / "shrub_atlas_albedo_v1.png"
    normal_path = texture_root / "shrub_atlas_normal_v1.png"
    for path in (albedo_path, normal_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing shrub atlas texture {path}; run "
                "tools/build_shrub_atlas.sh first"
            )

    material = bpy.data.materials.new("Shrub_Foliage_Cards_Atlas")
    material.use_nodes = True
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
    material.use_backface_culling = False
    material["godot_card_mode"] = True
    material["alpha_clip"] = 0.31
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    if hasattr(material, "blend_method"):
        material.blend_method = "CLIP"
    if hasattr(material, "alpha_threshold"):
        material.alpha_threshold = 0.31

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (520.0, 0.0)
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.location = (220.0, 0.0)
    shader.inputs["Roughness"].default_value = 0.84
    shader.inputs["Specular IOR Level"].default_value = 0.28

    coordinates = nodes.new("ShaderNodeTexCoord")
    coordinates.location = (-760.0, 10.0)
    albedo_image = bpy.data.images.load(str(albedo_path), check_existing=True)
    albedo_image.colorspace_settings.name = "sRGB"
    albedo = nodes.new("ShaderNodeTexImage")
    albedo.name = "Shrub_Atlas_Albedo"
    albedo.label = "2x4 shrub-foliage atlas (RGBA)"
    albedo.image = albedo_image
    albedo.interpolation = "Linear"
    albedo.extension = "CLIP"
    albedo.location = (-500.0, 100.0)
    links.new(coordinates.outputs["UV"], albedo.inputs["Vector"])
    links.new(albedo.outputs["Color"], shader.inputs["Base Color"])
    links.new(albedo.outputs["Alpha"], shader.inputs["Alpha"])

    normal_image = bpy.data.images.load(str(normal_path), check_existing=True)
    normal_image.colorspace_settings.name = "Non-Color"
    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "Shrub_Atlas_Normal"
    normal_texture.image = normal_image
    normal_texture.interpolation = "Linear"
    normal_texture.extension = "CLIP"
    normal_texture.location = (-500.0, -220.0)
    normal_node = nodes.new("ShaderNodeNormalMap")
    normal_node.inputs["Strength"].default_value = 0.60
    normal_node.location = (-80.0, -180.0)
    links.new(coordinates.outputs["UV"], normal_texture.inputs["Vector"])
    links.new(normal_texture.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "rock_dark": make_material("Rock_Volcanic_Dark", (0.045, 0.035, 0.025, 1.0), 0.95),
        "rock_mid": make_material("Rock_Weathered_Mid", (0.090, 0.075, 0.055, 1.0), 0.93),
        "rock_pale": make_material("Rock_Mineral_Wear", (0.180, 0.150, 0.100, 1.0), 0.91),
        "stem": make_material("Shrub_Stem", (0.070, 0.030, 0.008, 1.0), 0.96),
        "shrub_foliage": make_shrub_foliage_material(),
        "grass_dark": make_material("Grass_Deep_Green", (0.012, 0.055, 0.012, 1.0), 0.94),
        "grass_mid": make_material("Grass_Muted_Green", (0.026, 0.095, 0.018, 1.0), 0.94),
        "grass_dry": make_material("Grass_Sun_Dry", (0.165, 0.110, 0.030, 1.0), 0.97),
    }


def mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    materials: list[bpy.types.Material],
    material_indices: list[int] | None = None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}.Mesh")
    mesh.from_pydata(vertices, [], faces)
    for material in materials:
        mesh.materials.append(material)
    if material_indices is not None:
        for polygon, material_index in zip(mesh.polygons, material_indices):
            polygon.material_index = material_index
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def normalize_ground_pivot(obj: bpy.types.Object) -> None:
    bpy.context.scene.cursor.location = Vector((0.0, 0.0, 0.0))
    select_only(obj)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    minimum_z = min(vertex.co.z for vertex in obj.data.vertices)
    for vertex in obj.data.vertices:
        vertex.co.z -= minimum_z
    obj.location = Vector((0.0, 0.0, 0.0))


def join_objects(parts: list[bpy.types.Object], name: str) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.hide_set(False)
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    result = bpy.context.object
    result.name = name
    result.data.name = f"{name}.Mesh"
    normalize_ground_pivot(result)
    return result


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
    shrub_material = bpy.data.materials.get("Shrub_Foliage_Cards_Atlas")
    uses_shrub_atlas = any(
        material == shrub_material for material in obj.data.materials
    )
    albedo_node = None
    normal_node = None
    original_albedo = None
    original_normal = None
    if uses_shrub_atlas:
        albedo_node = shrub_material.node_tree.nodes.get("Shrub_Atlas_Albedo")
        normal_node = shrub_material.node_tree.nodes.get("Shrub_Atlas_Normal")
        original_albedo = albedo_node.image
        original_normal = normal_node.image
        albedo_node.image = export_placeholder_image(
            "Shrub_GLTF_Transport_Albedo",
            (0.22, 0.52, 0.13, 1.0),
        )
        normal_node.image = export_placeholder_image(
            "Shrub_GLTF_Transport_Normal",
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
            export_tangents=uses_shrub_atlas,
            export_cameras=False,
            export_lights=False,
            export_animations=False,
        )
    finally:
        if uses_shrub_atlas:
            albedo_node.image = original_albedo
            normal_node.image = original_normal


def make_single_rock(
    name: str,
    location: Vector,
    scale: Vector,
    seed: int,
    materials: dict[str, bpy.types.Material],
    subdivisions: int = 2,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=1.0, location=location)
    rock = bpy.context.object
    rock.name = name
    rng = random.Random(seed)
    for vertex in rock.data.vertices:
        direction = vertex.co.normalized()
        angular = (
            math.sin(direction.x * 7.1 + seed * 0.31)
            + math.sin(direction.y * 5.3 - seed * 0.17)
            + math.sin(direction.z * 8.7 + seed * 0.11)
        )
        factor = 1.0 + angular * 0.045 + rng.uniform(-0.055, 0.055)
        vertex.co.x *= scale.x * factor
        vertex.co.y *= scale.y * factor
        vertex.co.z *= scale.z * factor
    for material_key in ("rock_dark", "rock_mid", "rock_pale"):
        rock.data.materials.append(materials[material_key])
    for polygon in rock.data.polygons:
        center_height = polygon.center.z / max(scale.z, 0.001)
        if polygon.normal.z > 0.52 and center_height > 0.15:
            polygon.material_index = 2 if (polygon.index + seed) % 5 == 0 else 1
        else:
            polygon.material_index = 0
        polygon.use_smooth = False
    return rock


def build_rocks(materials: dict[str, bpy.types.Material]) -> list[tuple[str, bpy.types.Object]]:
    boulder = make_single_rock(
        "Rock_Boulder", Vector((0.0, 0.0, 1.05)), Vector((1.65, 1.30, 1.18)), 13, materials
    )
    normalize_ground_pivot(boulder)
    outcrop_parts = [
        make_single_rock("Outcrop_Core", Vector((0.0, 0.0, 0.72)), Vector((2.05, 1.18, 0.82)), 29, materials),
        make_single_rock("Outcrop_Shard", Vector((1.20, 0.18, 0.55)), Vector((0.92, 0.76, 0.68)), 31, materials, 1),
    ]
    outcrop = join_objects(outcrop_parts, "Rock_Low_Outcrop")
    cluster_specs = (
        (Vector((-0.72, 0.10, 0.37)), Vector((0.64, 0.56, 0.42)), 41),
        (Vector((0.02, -0.12, 0.48)), Vector((0.82, 0.63, 0.54)), 43),
        (Vector((0.73, 0.18, 0.31)), Vector((0.51, 0.46, 0.36)), 47),
        (Vector((0.30, 0.58, 0.23)), Vector((0.38, 0.33, 0.26)), 53),
    )
    cluster = join_objects(
        [make_single_rock(f"Stone_{index:02d}", location, scale, seed, materials, 1)
         for index, (location, scale, seed) in enumerate(cluster_specs)],
        "Stone_Cluster",
    )
    return [("rock_boulder", boulder), ("rock_outcrop", outcrop), ("stone_cluster", cluster)]


def build_grass_clump(
    name: str,
    seed: int,
    dry: bool,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    rng = random.Random(seed)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    material_indices: list[int] = []
    blade_count = 17 if dry else 21
    for blade_index in range(blade_count):
        angle = rng.random() * math.tau
        radius = math.sqrt(rng.random()) * (0.52 if dry else 0.46)
        base = Vector((math.cos(angle) * radius, math.sin(angle) * radius, 0.0))
        height = rng.uniform(0.42, 0.92) * (1.12 if dry else 1.0)
        width = rng.uniform(0.035, 0.072)
        side = Vector((-math.sin(angle), math.cos(angle), 0.0))
        bend = Vector((math.cos(angle), math.sin(angle), 0.0)) * rng.uniform(0.08, 0.23)
        start = len(vertices)
        for level in range(4):
            t = level / 3.0
            center = base + Vector((0.0, 0.0, height * t)) + bend * (t * t)
            half_width = width * (1.0 - t * 0.88)
            vertices.append(tuple(center - side * half_width))
            vertices.append(tuple(center + side * half_width))
        for level in range(3):
            base_index = start + level * 2
            faces.append((base_index, base_index + 1, base_index + 3, base_index + 2))
            material_indices.append((blade_index + level) % 2)
    material_keys = ("grass_dry", "grass_mid") if dry else ("grass_dark", "grass_mid")
    obj = mesh_object(
        name,
        vertices,
        faces,
        [materials[key] for key in material_keys],
        material_indices,
    )
    obj["asset_family"] = "island grass clumps"
    obj["pivot"] = "ground"
    return obj


def add_branch_between(
    name: str,
    start: Vector,
    end: Vector,
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    direction = end - start
    length = direction.length
    bpy.ops.mesh.primitive_cone_add(
        vertices=6,
        radius1=radius,
        radius2=radius * 0.34,
        depth=length,
        location=(start + end) * 0.5,
    )
    branch = bpy.context.object
    branch.name = name
    branch.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    branch.data.materials.append(material)
    return branch


def atlas_uv_rect(cell_index: int) -> tuple[float, float, float, float]:
    column = cell_index % ATLAS_COLUMNS
    row_from_top = cell_index // ATLAS_COLUMNS
    x_min, y_min, x_max, y_max = SHRUB_ALPHA_BOUNDS[cell_index]
    # Dos texels transparentes alrededor de la silueta alimentan correctamente
    # el filtro anisotrópico sin volver a introducir el gran margen de la celda.
    x_min = max(x_min - 2, 0)
    x_max = min(x_max + 2, 1024)
    y_min = max(y_min - 2, 0)
    y_max = min(y_max + 2, 512)
    u_min = (column * 1024 + x_min) / 2048.0
    u_max = (column * 1024 + x_max) / 2048.0
    # Pillow informa y desde arriba; UV de Blender/Godot crece desde abajo.
    atlas_y_min = row_from_top * 512 + y_min
    atlas_y_max = row_from_top * 512 + y_max
    v_min = 1.0 - atlas_y_max / 2048.0
    v_max = 1.0 - atlas_y_min / 2048.0
    return u_min, u_max, v_min, v_max


def build_shrub_cards(
    name: str,
    seed: int,
    airy: bool,
    material: bpy.types.Material,
) -> bpy.types.Object:
    rng = random.Random(seed + 701)
    form = "wild" if airy else "dense"
    cell_choices = SHRUB_ATLAS_CELLS[form]
    # Cinco planos laterales más una tapa casi horizontal conservan la
    # legibilidad desde la cámara de mesa sin apilar quince arbustos completos.
    card_count = 6
    segment_count = 2
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    uv_coordinates: list[tuple[float, float]] = []

    for index in range(card_count):
        azimuth = index * GOLDEN_ANGLE + rng.uniform(-0.10, 0.10)
        outward = Vector((math.cos(azimuth), math.sin(azimuth), 0.0))
        right = Vector((-math.sin(azimuth), math.cos(azimuth), 0.0))
        cell_index = cell_choices[index % len(cell_choices)]
        x_min, y_min, x_max, y_max = SHRUB_ALPHA_BOUNDS[cell_index]
        silhouette_aspect = (x_max - x_min) / float(y_max - y_min)
        if airy:
            base_radius = rng.uniform(0.02, 0.13)
            base_height = rng.uniform(0.00, 0.12)
            height = rng.uniform(1.28, 1.52)
            ordinary_lean = rng.uniform(0.06, 0.16)
        else:
            base_radius = rng.uniform(0.01, 0.12)
            base_height = rng.uniform(0.04, 0.14)
            height = rng.uniform(1.02, 1.20)
            ordinary_lean = rng.uniform(0.05, 0.13)
        width = height * silhouette_aspect * rng.uniform(0.92, 1.04)

        # Una tapa casi horizontal evita que la copa desaparezca en vista
        # cenital. Conserva la misma proporción del recorte, sin estirarlo.
        if index == card_count - 1:
            up_direction = (
                outward * 0.78 + Vector((0.0, 0.0, 0.63))
            ).normalized()
            base_height += 0.34 if airy else 0.31
            height *= 0.74
            width *= 1.02
        else:
            up_direction = (
                outward * ordinary_lean + Vector((0.0, 0.0, 1.0))
            ).normalized()

        base = (
            outward * base_radius
            + right * rng.uniform(-0.10, 0.10)
            + Vector((0.0, 0.0, base_height))
        )
        u_min, u_max, v_min, v_max = atlas_uv_rect(cell_index)
        vertex_start = len(vertices)
        curve = rng.uniform(0.018, 0.045)
        for segment in range(segment_count + 1):
            t = segment / segment_count
            center = (
                base
                + up_direction * height * t
                + outward * math.sin(math.pi * t) * curve
            )
            half_width = width * 0.5 * (
                0.96 + 0.04 * math.sin(math.pi * t)
            )
            vertices.append(tuple(center - right * half_width))
            vertices.append(tuple(center + right * half_width))
            v = v_min + (v_max - v_min) * t
            uv_coordinates.append((u_min, v))
            uv_coordinates.append((u_max, v))
        for segment in range(segment_count):
            base_index = vertex_start + segment * 2
            faces.append(
                (
                    base_index,
                    base_index + 2,
                    base_index + 3,
                    base_index + 1,
                )
            )

    mesh = bpy.data.meshes.new(f"{name}.FoliageCardsMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = uv_coordinates[vertex_index]
    mesh.update()
    cards = bpy.data.objects.new(f"{name}_FoliageCards", mesh)
    cards["card_count"] = card_count
    cards["atlas_cells"] = ",".join(str(cell) for cell in cell_choices)
    bpy.context.collection.objects.link(cards)
    return cards


def build_shrub(
    name: str,
    seed: int,
    airy: bool,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    rng = random.Random(seed)
    parts: list[bpy.types.Object] = []
    branch_count = 7 if airy else 6
    maximum_height = 1.68 if airy else 1.24
    for branch_index in range(branch_count):
        angle = math.tau * branch_index / branch_count + rng.uniform(-0.32, 0.32)
        outward = Vector((math.cos(angle), math.sin(angle), 0.0))
        tangent = Vector((-math.sin(angle), math.cos(angle), 0.0))
        start = outward * rng.uniform(0.00, 0.055)
        branch_height = maximum_height * rng.uniform(0.68, 0.98)
        radial_reach = (
            rng.uniform(0.26, 0.48) if airy else rng.uniform(0.16, 0.34)
        )
        end = (
            outward * radial_reach
            + tangent * rng.uniform(-0.10, 0.10)
            + Vector((0.0, 0.0, branch_height))
        )
        parts.append(
            add_branch_between(
                f"{name}_Branch_{branch_index:02d}",
                start,
                end,
                0.035 if airy else 0.045,
                materials["stem"],
            )
        )
    parts.append(
        build_shrub_cards(
            name,
            seed,
            airy,
            materials["shrub_foliage"],
        )
    )
    shrub = join_objects(parts, name)
    editable_mesh = bmesh.new()
    editable_mesh.from_mesh(shrub.data)
    bmesh.ops.triangulate(editable_mesh, faces=list(editable_mesh.faces))
    editable_mesh.to_mesh(shrub.data)
    editable_mesh.free()
    shrub.data.update()
    shrub["asset_family"] = "island shrubs"
    shrub["growth_form"] = "airy" if airy else "dense"
    shrub["foliage_geometry"] = "curved_alpha_clip_cards"
    shrub["foliage_card_count"] = 6
    shrub["foliage_atlas_cells"] = ",".join(
        str(cell) for cell in SHRUB_ATLAS_CELLS["wild" if airy else "dense"]
    )
    shrub["pivot"] = "ground"
    return shrub


def spectral_noise(size: int, seed: int, exponent: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    frequencies = np.fft.fftfreq(size)
    frequency_y, frequency_x = np.meshgrid(frequencies, frequencies, indexing="ij")
    radius = np.sqrt(frequency_x * frequency_x + frequency_y * frequency_y)
    amplitude = np.zeros_like(radius)
    nonzero = radius > 0.0
    amplitude[nonzero] = 1.0 / np.power(radius[nonzero], exponent)
    spectrum = (
        rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))
    ) * amplitude
    noise = np.fft.ifft2(spectrum).real
    noise -= noise.min()
    maximum = noise.max()
    return noise / maximum if maximum > 0.0 else noise


def load_reference_palette(reference_path: Path) -> dict[str, np.ndarray]:
    width = 320
    height = 180
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(reference_path),
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    rgb = (
        np.frombuffer(result.stdout, dtype=np.uint8)
        .reshape(height, width, 3)
        .astype(np.float32)
        / 255.0
    )
    flat = rgb.reshape(-1, 3)
    luminance = flat @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    grass_mask = (
        (flat[:, 1] > flat[:, 0] * 0.88)
        & (flat[:, 1] > flat[:, 2] * 0.82)
        & (luminance > 0.08)
        & (luminance < 0.52)
    )
    soil_mask = (
        (luminance > 0.035)
        & (luminance < 0.25)
        & (flat[:, 0] > flat[:, 2] * 0.82)
    )
    sand_mask = (
        (luminance > 0.46)
        & (flat[:, 0] > flat[:, 2] * 0.78)
        & (flat[:, 1] > flat[:, 2] * 0.78)
    )

    def median_or(mask: np.ndarray, fallback: tuple[float, float, float]) -> np.ndarray:
        values = flat[mask]
        if len(values) < 128:
            return np.array(fallback, dtype=np.float32)
        return np.median(values, axis=0).astype(np.float32)

    palette = {
        "grass": median_or(grass_mask, (0.22, 0.28, 0.13)),
        "soil": median_or(soil_mask, (0.12, 0.105, 0.085)),
        "sand": median_or(sand_mask, (0.72, 0.68, 0.54)),
    }
    return palette


def normal_from_height(height: np.ndarray, strength: float) -> np.ndarray:
    derivative_x = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    derivative_y = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    normal = np.stack(
        (-derivative_x * strength, -derivative_y * strength, np.ones_like(height)),
        axis=-1,
    )
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5


def save_png(path: Path, rgb_or_gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rgb_or_gray.ndim == 2:
        rgb = np.repeat(rgb_or_gray[..., None], 3, axis=-1)
    else:
        rgb = rgb_or_gray
    pixels = np.rint(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    height, width = pixels.shape[:2]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s:v",
            f"{width}x{height}",
            "-i",
            "-",
            "-frames:v",
            "1",
            str(path),
        ],
        input=pixels.tobytes(),
        check=True,
    )


def build_ground_textures(root: Path) -> dict[str, object]:
    reference_path = (
        project_root() / "art" / "references" / "island_biome" / "foto_1.jpg"
    )
    print("TEXTURES: sampling reference palette", flush=True)
    palette = load_reference_palette(reference_path)
    size = TEXTURE_SIZE
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    texture_root = root / "textures"
    albedos: dict[str, np.ndarray] = {}

    grass_macro = spectral_noise(size, 101, 1.55)
    grass_fine = spectral_noise(size, 103, 0.58)
    grass_height = np.clip(grass_macro * 0.63 + grass_fine * 0.37, 0.0, 1.0)
    grass_albedo = palette["grass"][None, None, :] * np.array(
        [0.82, 1.05, 0.72], dtype=np.float32
    )
    grass_albedo = grass_albedo * (0.68 + grass_height[..., None] * 0.62)
    straw = spectral_noise(size, 107, 0.32) > 0.865
    grass_albedo[straw] = (
        grass_albedo[straw] * 0.45 + np.array([0.46, 0.35, 0.12]) * 0.55
    )
    grass_roughness = np.clip(0.91 + (grass_fine - 0.5) * 0.08, 0.82, 0.98)
    albedos["grass"] = grass_albedo

    soil_macro = spectral_noise(size, 211, 1.42)
    soil_fine = spectral_noise(size, 223, 0.45)
    soil_height = np.clip(soil_macro * 0.72 + soil_fine * 0.28, 0.0, 1.0)
    soil_albedo = palette["soil"][None, None, :] * np.array(
        [1.06, 0.94, 0.82], dtype=np.float32
    )
    soil_albedo = soil_albedo * (0.66 + soil_height[..., None] * 0.62)
    grit = spectral_noise(size, 227, 0.26) > 0.91
    soil_albedo[grit] = (
        soil_albedo[grit] * 0.55 + np.array([0.34, 0.30, 0.23]) * 0.45
    )
    soil_roughness = np.clip(0.88 + (soil_fine - 0.5) * 0.10, 0.78, 0.97)
    albedos["soil"] = soil_albedo

    sand_macro = spectral_noise(size, 307, 1.72)
    sand_fine = spectral_noise(size, 311, 0.48)
    ripple_phase = xx * 13.0 + np.sin(yy * math.tau * 2.0) * 0.21
    ripples = np.sin(ripple_phase * math.tau) * 0.5 + 0.5
    sand_height = np.clip(
        sand_macro * 0.38 + sand_fine * 0.22 + ripples * 0.40, 0.0, 1.0
    )
    sand_albedo = palette["sand"][None, None, :] * np.array(
        [1.08, 1.03, 0.91], dtype=np.float32
    )
    sand_albedo = sand_albedo * (0.83 + sand_height[..., None] * 0.28)
    shell_grit = spectral_noise(size, 313, 0.20) > 0.94
    sand_albedo[shell_grit] = np.minimum(1.0, sand_albedo[shell_grit] * 1.17)
    sand_roughness = np.clip(0.94 + (sand_fine - 0.5) * 0.05, 0.88, 0.99)
    albedos["sand"] = sand_albedo

    texture_data = {
        "grass": (grass_albedo, grass_height, grass_roughness, 8.0),
        "soil": (soil_albedo, soil_height, soil_roughness, 9.5),
        "sand": (sand_albedo, sand_height, sand_roughness, 6.5),
    }
    for key, (albedo, height, roughness, normal_strength) in texture_data.items():
        print(f"TEXTURES: writing {key}", flush=True)
        save_png(texture_root / f"ground_{key}_albedo.png", albedo)
        save_png(
            texture_root / f"ground_{key}_normal.png",
            normal_from_height(height, normal_strength),
        )
        save_png(texture_root / f"ground_{key}_roughness.png", roughness)

    separator = np.full((size, 8, 3), 0.055, dtype=np.float32)
    preview = np.concatenate(
        (albedos["soil"], separator, albedos["grass"], separator, albedos["sand"]),
        axis=1,
    )
    save_png(
        project_root() / "previews" / "island_biome" / "ground_materials.png",
        preview,
    )
    print("TEXTURES: complete", flush=True)
    return {
        "reference": str(reference_path.relative_to(project_root())),
        "texture_size": size,
        "palette": {
            key: [round(float(value), 5) for value in color]
            for key, color in palette.items()
        },
    }


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_family(
    all_assets: list[AssetRecord],
    family: str,
    preview_path: Path,
    positions: list[float],
    camera_position: Vector,
    target: Vector,
) -> None:
    family_assets = [record for record in all_assets if record.family == family]
    transforms = {
        record.key: record.obj.matrix_world.copy() for record in family_assets
    }
    for record in all_assets:
        record.obj.hide_render = record.family != family
    for record, x_position in zip(family_assets, positions):
        record.obj.location = Vector((x_position, 0.0, 0.0))
        record.obj.rotation_euler = Vector((0.0, 0.0, 0.0))

    bpy.ops.object.light_add(type="AREA", location=(-6.0, -9.0, 12.0))
    key = bpy.context.object
    key.name = f"{family.title()}PreviewKey"
    key.data.energy = 1250.0
    key.data.shape = "DISK"
    key.data.size = 7.0
    look_at(key, target)

    bpy.ops.object.light_add(type="AREA", location=(8.0, -2.0, 8.0))
    fill = bpy.context.object
    fill.name = f"{family.title()}PreviewFill"
    fill.data.energy = 750.0
    fill.data.size = 6.0
    look_at(fill, target)

    bpy.ops.object.camera_add(location=camera_position)
    camera = bpy.context.object
    camera.name = f"{family.title()}PreviewCamera"
    camera.data.lens = 60.0
    look_at(camera, target)

    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True
    scene.render.filepath = str(preview_path)
    scene.world.color = (0.035, 0.055, 0.075)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(key, do_unlink=True)
    bpy.data.objects.remove(fill, do_unlink=True)
    for record in all_assets:
        record.obj.hide_render = False
    for record in family_assets:
        record.obj.matrix_world = transforms[record.key]


def mesh_report(record: AssetRecord) -> dict[str, object]:
    triangle_count = sum(
        len(polygon.vertices) - 2 for polygon in record.obj.data.polygons
    )
    dimensions = record.obj.dimensions
    report = {
        "key": record.key,
        "family": record.family,
        "file": str(record.output_path.relative_to(project_root())),
        "triangles": triangle_count,
        "dimensions_m": [round(float(value), 4) for value in dimensions],
        "pivot": "ground",
    }
    if "foliage_card_count" in record.obj:
        report["foliage_geometry"] = record.obj["foliage_geometry"]
        report["foliage_card_count"] = int(record.obj["foliage_card_count"])
        report["foliage_atlas_cells"] = [
            int(value)
            for value in str(record.obj["foliage_atlas_cells"]).split(",")
        ]
    return report


def main() -> None:
    root = output_root()
    root.mkdir(parents=True, exist_ok=True)
    reset_scene()
    materials = build_materials()
    assets: list[AssetRecord] = []

    for key, obj in build_rocks(materials):
        output_path = root / "rocks" / f"{key}.glb"
        export_glb(obj, output_path)
        assets.append(AssetRecord(key, "rocks", obj, output_path))

    vegetation = [
        ("grass_green", build_grass_clump("Grass_Clump_Green", 71, False, materials)),
        ("grass_dry", build_grass_clump("Grass_Clump_Dry", 73, True, materials)),
        ("shrub_dense", build_shrub("Shrub_Dense", 83, False, materials)),
        ("shrub_wild", build_shrub("Shrub_Wild", 89, True, materials)),
    ]
    for key, obj in vegetation:
        output_path = root / "vegetation" / f"{key}.glb"
        export_glb(obj, output_path)
        assets.append(AssetRecord(key, "vegetation", obj, output_path))

    texture_report_path = root / "texture_report.json"
    texture_report = json.loads(texture_report_path.read_text(encoding="utf-8"))
    preview_root = project_root() / "previews" / "island_biome"
    render_family(
        assets,
        "rocks",
        preview_root / "rocks_and_stones.png",
        [-3.2, 0.0, 3.25],
        Vector((10.5, -16.5, 8.4)),
        Vector((0.0, 0.0, 0.7)),
    )
    render_family(
        assets,
        "vegetation",
        preview_root / "shrubs_and_grasses.png",
        [-4.2, -1.55, 1.35, 4.15],
        Vector((11.2, -18.5, 9.2)),
        Vector((0.0, 0.0, 0.75)),
    )

    source_positions = {
        "rock_boulder": (-4.0, 0.0, 0.0),
        "rock_outcrop": (0.0, 0.0, 0.0),
        "stone_cluster": (4.0, 0.0, 0.0),
        "grass_green": (-4.5, 5.0, 0.0),
        "grass_dry": (-1.5, 5.0, 0.0),
        "shrub_dense": (1.5, 5.0, 0.0),
        "shrub_wild": (4.5, 5.0, 0.0),
    }
    for record in assets:
        record.obj.location = Vector(source_positions[record.key])
    source_path = root / "source" / "island_props.blend"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(source_path))

    report = {
        "generator": "tools/blender/generate_island_props.py",
        "source_reference": texture_report,
        "assets": [mesh_report(record) for record in assets],
        "runtime_strategy": (
            "GLB props instanced by Godot MultiMesh; 8-layer 1024px PBR arrays"
        ),
    }
    report_path = root / "asset_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ISLAND_PROPS_OK")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
