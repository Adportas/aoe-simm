"""Bake the island coastline, terrain and biome fields used by Godot.

The coast is authored as a domain-warped implicit form with explicit bays and
capes, then converted to a true Euclidean signed-distance field. The heightmap
uses a ridged central spine, separated peaks and a deterministic hydraulic
erosion pass. CPU placement and GPU materials consume these exact same maps.

No third-party image package is required: NumPy builds the fields, writes the
native-metre float32 runtime maps and emits the remaining PNG data textures.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path

import numpy as np


MAP_WIDTH_M = 400.0
MAP_LENGTH_M = 720.0
IMAGE_WIDTH = 576
IMAGE_HEIGHT = 1024
PIXEL_SIZE_M = MAP_WIDTH_M / IMAGE_WIDTH
SEA_LEVEL_M = 0.75
HEIGHT_MIN_M = -16.0
HEIGHT_MAX_M = 64.0
SDF_MIN_M = -96.0
SDF_MAX_M = 224.0
EROSION_ITERATIONS = 220


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def spectral_noise(shape: tuple[int, int], seed: int, exponent: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    radius = np.sqrt(fx * fx + fy * fy)
    amplitude = np.zeros(shape, dtype=np.float64)
    valid = radius > 0.0
    amplitude[valid] = 1.0 / np.power(radius[valid], exponent)
    spectrum = (
        rng.normal(size=shape) + 1j * rng.normal(size=shape)
    ) * amplitude
    noise = np.fft.ifft2(spectrum).real
    low, high = np.percentile(noise, (0.5, 99.5))
    return np.clip((noise - low) / max(high - low, 1e-9), 0.0, 1.0).astype(
        np.float32
    )


def fbm(shape: tuple[int, int], seed: int) -> np.ndarray:
    layers = (
        (1.58, 0.52),
        (1.22, 0.26),
        (0.92, 0.14),
        (0.62, 0.08),
    )
    result = np.zeros(shape, dtype=np.float32)
    total = 0.0
    for index, (exponent, weight) in enumerate(layers):
        result += spectral_noise(shape, seed + index * 37, exponent) * weight
        total += weight
    return result / total


def bilinear_sample(
    field: np.ndarray,
    x_m: np.ndarray,
    z_m: np.ndarray,
) -> np.ndarray:
    u = np.clip((x_m / MAP_WIDTH_M + 0.5) * (IMAGE_WIDTH - 1), 0, IMAGE_WIDTH - 1)
    v = np.clip((z_m / MAP_LENGTH_M + 0.5) * (IMAGE_HEIGHT - 1), 0, IMAGE_HEIGHT - 1)
    x0 = np.floor(u).astype(np.int32)
    y0 = np.floor(v).astype(np.int32)
    x1 = np.minimum(x0 + 1, IMAGE_WIDTH - 1)
    y1 = np.minimum(y0 + 1, IMAGE_HEIGHT - 1)
    tx = u - x0
    ty = v - y0
    top = field[y0, x0] * (1.0 - tx) + field[y0, x1] * tx
    bottom = field[y1, x0] * (1.0 - tx) + field[y1, x1] * tx
    return top * (1.0 - ty) + bottom * ty


def gaussian(
    x_m: np.ndarray,
    z_m: np.ndarray,
    center_x: float,
    center_z: float,
    sigma_x: float,
    sigma_z: float,
) -> np.ndarray:
    return np.exp(
        -(
            np.square((x_m - center_x) / sigma_x)
            + np.square((z_m - center_z) / sigma_z)
        )
    )


def edt_1d(values: np.ndarray) -> np.ndarray:
    """Felzenszwalb/Huttenlocher exact squared distance transform."""
    count = values.size
    sites = np.zeros(count, dtype=np.int32)
    boundaries = np.zeros(count + 1, dtype=np.float64)
    output = np.empty(count, dtype=np.float64)
    k = 0
    sites[0] = 0
    boundaries[0] = -np.inf
    boundaries[1] = np.inf
    for q in range(1, count):
        q_value = values[q] + q * q
        while True:
            site = sites[k]
            crossing = (q_value - (values[site] + site * site)) / (2.0 * (q - site))
            if crossing > boundaries[k] or k == 0:
                break
            k -= 1
        if crossing <= boundaries[k] and k == 0:
            sites[0] = q
            boundaries[0] = -np.inf
            boundaries[1] = np.inf
        else:
            k += 1
            sites[k] = q
            boundaries[k] = crossing
            boundaries[k + 1] = np.inf
    k = 0
    for q in range(count):
        while boundaries[k + 1] < q:
            k += 1
        offset = q - sites[k]
        output[q] = offset * offset + values[sites[k]]
    return output


def euclidean_distance_to_false(binary: np.ndarray) -> np.ndarray:
    huge = 1.0e12
    initial = np.where(binary, huge, 0.0).astype(np.float64)
    horizontal = np.empty_like(initial)
    for row in range(initial.shape[0]):
        horizontal[row, :] = edt_1d(initial[row, :])
    squared = np.empty_like(horizontal)
    for column in range(horizontal.shape[1]):
        squared[:, column] = edt_1d(horizontal[:, column])
    return np.sqrt(squared).astype(np.float32) * PIXEL_SIZE_M


def shift(array: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    result = np.full_like(array, fill)
    source_y = slice(max(0, -dy), min(array.shape[0], array.shape[0] - dy))
    source_x = slice(max(0, -dx), min(array.shape[1], array.shape[1] - dx))
    target_y = slice(max(0, dy), min(array.shape[0], array.shape[0] + dy))
    target_x = slice(max(0, dx), min(array.shape[1], array.shape[1] + dx))
    result[target_y, target_x] = array[source_y, source_x]
    return result


def hydraulic_erosion(
    original_height: np.ndarray,
    land: np.ndarray,
    sdf_m: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """Deterministic shallow-water erosion with sediment transport."""
    height = original_height.astype(np.float32).copy()
    water = np.zeros_like(height)
    sediment = np.zeros_like(height)
    erosion_zone = land & (sdf_m > 5.0)
    rainfall_pattern = 0.72 + fbm(height.shape, 1701) * 0.56
    directions = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1),
    )
    rows, columns = np.indices(height.shape, dtype=np.int32)
    destination_candidates: list[np.ndarray] = []
    for dy, dx in directions:
        # shift(surface, dy, dx) places the neighbour from (row - dy,
        # column - dx) at the current cell, so transported material must use
        # that same source coordinate as its destination.
        destination = np.clip(rows - dy, 0, height.shape[0] - 1) * height.shape[1]
        destination += np.clip(columns - dx, 0, height.shape[1] - 1)
        destination_candidates.append(destination.astype(np.int32))
    destination_stack = np.stack(destination_candidates, axis=0)

    for _ in range(iterations):
        water[land] += 0.026 * rainfall_pattern[land]
        surface = height + water
        neighbours = np.stack(
            [shift(surface, dy, dx, np.inf) for dy, dx in directions], axis=0
        )
        choice = np.argmin(neighbours, axis=0)
        lowest = np.take_along_axis(neighbours, choice[None, ...], axis=0)[0]
        drop = np.maximum(surface - lowest, 0.0)
        flow = np.minimum(water * 0.52, drop * 0.18)
        flow *= erosion_zone
        capacity = flow * (0.45 + np.minimum(drop / PIXEL_SIZE_M, 3.0) * 3.2)
        delta = (capacity - sediment) * 0.075
        eroded = np.clip(delta, 0.0, 0.055) * erosion_zone
        deposited = np.clip(-delta, 0.0, 0.045) * erosion_zone
        height -= eroded
        sediment += eroded
        height += deposited
        sediment -= deposited

        ratio = np.clip(flow / np.maximum(water, 1e-7), 0.0, 1.0)
        sediment_flow = sediment * ratio * 0.62
        destination = np.take_along_axis(
            destination_stack, choice[None, ...], axis=0
        )[0]
        incoming_water = np.zeros_like(water)
        incoming_sediment = np.zeros_like(sediment)
        np.add.at(incoming_water.ravel(), destination.ravel(), flow.ravel())
        np.add.at(
            incoming_sediment.ravel(), destination.ravel(), sediment_flow.ravel()
        )
        water = (water - flow + incoming_water) * 0.86
        sediment = sediment - sediment_flow + incoming_sediment
        water[~land] = 0.0
        sediment[~land] = 0.0

    # Preserve the authored shoreline and prevent numerical pits.
    blend = smoothstep(2.0, 12.0, sdf_m) * land
    height = original_height * (1.0 - blend) + height * blend
    height[land] = np.maximum(height[land], 0.20)
    return height.astype(np.float32)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def save_png8(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if image.ndim == 2:
        image = image[..., None]
    channels = image.shape[2]
    color_types = {1: 0, 3: 2, 4: 6}
    if channels not in color_types:
        raise ValueError(f"Unsupported channel count: {channels}")
    pixels = np.rint(np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
    rows = b"".join(b"\x00" + pixels[row].tobytes() for row in range(pixels.shape[0]))
    header = struct.pack(
        ">IIBBBBB", pixels.shape[1], pixels.shape[0], 8, color_types[channels], 0, 0, 0
    )
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(rows, level=7))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def save_png16_gray(path: Path, normalized: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.rint(np.clip(normalized, 0.0, 1.0) * 65535.0).astype(">u2")
    rows = b"".join(b"\x00" + pixels[row].tobytes() for row in range(pixels.shape[0]))
    header = struct.pack(">IIBBBBB", pixels.shape[1], pixels.shape[0], 16, 0, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(rows, level=7))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def save_float32_map(path: Path, values: np.ndarray) -> None:
    """Write a headerless row-major RF image for Godot's PCK-safe loader."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.asarray(values, dtype="<f4").tobytes(order="C"))


def bake_normal_map(height_m: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Bake the full-resolution terrain normal in local X/Z/up components.

    RGB stores X, Z and up. The terrain shader reconstructs the local-space
    vector explicitly, so its convention is independent from texture import
    normal-map flips.
    """
    dz, dx = np.gradient(height_m, PIXEL_SIZE_M, PIXEL_SIZE_M)
    normal_x = -dx * strength
    normal_z = dz * strength
    inverse = 1.0 / np.sqrt(normal_x ** 2 + normal_z ** 2 + 1.0)
    return np.stack(
        (
            normal_x * inverse * 0.5 + 0.5,
            normal_z * inverse * 0.5 + 0.5,
            inverse * 0.5 + 0.5,
        ),
        axis=-1,
    ).astype(np.float32)


def bake_ambient_occlusion(
    height_m: np.ndarray,
    steps: int = 14,
    reach_m: float = 26.0,
) -> np.ndarray:
    """Bake deterministic horizon occlusion over eight directions."""
    directions = (
        (0, 1), (1, 1), (1, 0), (1, -1),
        (0, -1), (-1, -1), (-1, 0), (-1, 1),
    )
    occlusion = np.zeros_like(height_m)
    for dy, dx in directions:
        horizon = np.zeros_like(height_m)
        for step in range(1, steps + 1):
            offset_m = reach_m * step / steps
            pixels = max(1, int(round(offset_m / PIXEL_SIZE_M)))
            sampled = shift(height_m, -dy * pixels, -dx * pixels, -1.0e4)
            span = offset_m * math.hypot(dy, dx)
            horizon = np.maximum(
                horizon,
                (sampled - height_m) / max(span, 1e-6),
            )
        occlusion += horizon / np.sqrt(1.0 + horizon * horizon)
    return np.clip(
        1.0 - occlusion / len(directions),
        0.0,
        1.0,
    ).astype(np.float32)


def connected_component_areas(mask: np.ndarray) -> list[int]:
    """Measure four-connected patches without an external image package."""
    visited = np.zeros(mask.shape, dtype=np.bool_)
    areas: list[int] = []
    height, width = mask.shape
    for row, column in np.argwhere(mask):
        row = int(row)
        column = int(column)
        if visited[row, column]:
            continue
        visited[row, column] = True
        stack = [(row, column)]
        area = 0
        while stack:
            current_row, current_column = stack.pop()
            area += 1
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_row = current_row + dy
                next_column = current_column + dx
                if (
                    0 <= next_row < height
                    and 0 <= next_column < width
                    and mask[next_row, next_column]
                    and not visited[next_row, next_column]
                ):
                    visited[next_row, next_column] = True
                    stack.append((next_row, next_column))
        areas.append(area)
    return areas


def build_world_fields() -> dict[str, np.ndarray]:
    z_m, x_m = np.mgrid[
        -MAP_LENGTH_M * 0.5 : MAP_LENGTH_M * 0.5 : complex(IMAGE_HEIGHT),
        -MAP_WIDTH_M * 0.5 : MAP_WIDTH_M * 0.5 : complex(IMAGE_WIDTH),
    ]
    shape = (IMAGE_HEIGHT, IMAGE_WIDTH)

    warp_x = (spectral_noise(shape, 101, 1.82) * 2.0 - 1.0) * 22.0
    warp_z = (spectral_noise(shape, 137, 1.78) * 2.0 - 1.0) * 31.0
    x_warped = x_m + warp_x
    z_warped = z_m + warp_z
    coast_noise = bilinear_sample(fbm(shape, 211), x_warped, z_warped) * 2.0 - 1.0
    ellipse = np.sqrt(np.square(x_warped / 164.0) + np.square(z_warped / 312.0))
    coast_field = 1.0 - ellipse + coast_noise * 0.145

    # Authorial macro-features: two bays, two rocky capes and a southern sand bar.
    coast_field -= gaussian(x_m, z_m, 132.0, 88.0, 44.0, 72.0) * 0.23
    coast_field -= gaussian(x_m, z_m, -142.0, -72.0, 38.0, 78.0) * 0.16
    coast_field += gaussian(x_m, z_m, 122.0, -176.0, 52.0, 72.0) * 0.20
    coast_field += gaussian(x_m, z_m, -92.0, 238.0, 58.0, 74.0) * 0.18
    coast_field += gaussian(x_m, z_m, -14.0, -312.0, 90.0, 36.0) * 0.12
    land = coast_field >= 0.0

    inside_distance = euclidean_distance_to_false(land)
    outside_distance = euclidean_distance_to_false(~land)
    sdf_m = inside_distance - outside_distance

    broad_noise = fbm(shape, 401)
    beach_width = 4.0 + broad_noise * 20.0
    # The small beach berm and the much longer inland rise are independent;
    # otherwise the first few metres of beach inherit the whole plateau lift.
    berm = smoothstep(0.0, beach_width, sdf_m) * (0.45 + broad_noise * 0.95)
    inland_run = 22.0 + broad_noise * 34.0
    inland = smoothstep(beach_width, beach_width + inland_run, sdf_m)
    rolling = (fbm(shape, 443) * 2.0 - 1.0) * 2.2 * smoothstep(12.0, 52.0, sdf_m)
    base_land = 0.24 + berm + inland * (4.4 + broad_noise * 2.2) + rolling

    ridge_center_x = 12.0 - z_m * 0.205 + np.sin((z_m + 32.0) * 0.018) * 9.0
    ridge_offset = x_m - ridge_center_x
    standard_cross = np.exp(-np.power(np.abs(ridge_offset) / 34.0, 1.24))
    cliff_cross = np.where(
        ridge_offset < 18.0,
        np.exp(-np.power(np.abs(ridge_offset) / 39.0, 1.30)),
        np.clip(1.0 - (ridge_offset - 18.0) / 8.0, 0.0, 1.0),
    )
    cliff_locality = gaussian(x_m, z_m, 36.0, -88.0, 82.0, 64.0)
    ridge_cross = standard_cross * (1.0 - cliff_locality) + cliff_cross * cliff_locality

    peak_specs = (
        (-148.0, 44.0, 38.0),
        (-66.0, 54.0, 34.0),
        (26.0, 46.0, 33.0),
        (112.0, 34.0, 31.0),
    )
    peak_long = np.zeros(shape, dtype=np.float32)
    for center_z, amplitude, sigma in peak_specs:
        peak_long = np.maximum(
            peak_long,
            amplitude * np.exp(-np.square((z_m - center_z) / sigma)),
        )
    spine = 7.5 * np.exp(-np.power(np.abs((z_m + 12.0) / 235.0), 4.0))
    ridge_noise = fbm(shape, 601)
    ridged = np.square(1.0 - np.abs(ridge_noise * 2.0 - 1.0))
    ridge_modulation = 0.76 + ridged * 0.34
    mountain_fade = smoothstep(18.0, 52.0, sdf_m)
    mountains = ridge_cross * (peak_long + spine) * ridge_modulation * mountain_fade
    ridge_cut = (fbm(shape, 677) - 0.5) * 5.4 * ridge_cross * mountain_fade

    sea_floor = (
        SEA_LEVEL_M
        - 0.45
        - np.minimum(np.maximum(-sdf_m, 0.0) * 0.19, 15.0)
        + (fbm(shape, 733) - 0.5) * 0.55
    )
    # La batimetría alcanza la misma profundidad que el fondo oceánico extendido
    # antes del borde del heightmap; así no delata un rectángulo bajo el agua.
    map_edge_distance = np.minimum(
        MAP_WIDTH_M * 0.5 - np.abs(x_m),
        MAP_LENGTH_M * 0.5 - np.abs(z_m),
    )
    outer_deepening = 1.0 - smoothstep(0.0, 72.0, map_edge_distance)
    sea_floor = sea_floor * (1.0 - outer_deepening) + (-14.8) * outer_deepening
    authored_height = np.where(land, base_land + mountains + ridge_cut, sea_floor)
    authored_height = np.minimum(authored_height, 60.0).astype(np.float32)
    height_m = hydraulic_erosion(authored_height, land, sdf_m, EROSION_ITERATIONS)
    height_m = np.where(land, np.minimum(height_m, 60.0), sea_floor).astype(np.float32)

    dz, dx = np.gradient(height_m, PIXEL_SIZE_M, PIXEL_SIZE_M)
    slope = np.sqrt(dx * dx + dz * dz)
    slope_degrees = np.degrees(np.arctan(slope))
    laplacian = (
        shift(height_m, -1, 0, 0.0)
        + shift(height_m, 1, 0, 0.0)
        + shift(height_m, 0, -1, 0.0)
        + shift(height_m, 0, 1, 0.0)
        - height_m * 4.0
    )

    rocky_coast = land * (1.0 - smoothstep(0.0, 18.0, sdf_m)) * np.clip(
        gaussian(x_m, z_m, 122.0, -176.0, 72.0, 96.0) * 0.96
        + gaussian(x_m, z_m, -92.0, 238.0, 78.0, 92.0) * 0.82
        + smoothstep(31.0, 51.0, slope_degrees) * 0.72,
        0.0,
        1.0,
    )
    sand_access = 1.0 - rocky_coast * 0.96
    wet_sand = land * (1.0 - smoothstep(1.8, 5.5, sdf_m)) * sand_access
    dry_sand = land * (
        smoothstep(1.2, 4.0, sdf_m)
        * (1.0 - smoothstep(0.62, 1.08, sdf_m / beach_width))
        * sand_access
    )
    interior = land * smoothstep(0.72, 1.04, sdf_m / beach_width)
    rock = np.maximum(rocky_coast, interior * np.maximum(
        smoothstep(24.0, 48.0, slope_degrees),
        smoothstep(28.0, 55.0, height_m) * (0.58 + ridged * 0.42),
    ))
    moisture = np.clip(fbm(shape, 811) * 1.15 + broad_noise * 0.30 - 0.22, 0.0, 1.0)
    dryness = np.clip(
        1.0 - moisture + (fbm(shape, 853) - 0.5) * 0.30 + height_m / 150.0,
        0.0,
        1.0,
    )
    canopy_raw = np.clip(0.18 + moisture * 1.10, 0.0, 1.0) * (
        1.0 - smoothstep(38.0, 55.0, slope_degrees)
    )

    # Percentiles keep the shade and bare-soil masks self-calibrating when the
    # deterministic noise fields or terrain profile change.
    def land_quantile(field: np.ndarray, quantile: float) -> float:
        return float(np.percentile(field[land], quantile))

    shade = smoothstep(
        land_quantile(canopy_raw, 62.0),
        land_quantile(canopy_raw, 97.0),
        canopy_raw,
    )
    grass_green = (
        interior
        * moisture
        * (1.0 - rock)
        * (1.0 - smoothstep(30.0, 42.0, slope_degrees))
        * (1.0 - shade * 0.78)
    )
    grass_dry = interior * dryness * (1.0 - rock) * (1.0 - shade * 0.45)
    litter = interior * shade * (1.0 - rock) * 0.92
    pebbles = land * (
        np.exp(-np.square((sdf_m - 4.5) / 2.4)) * (0.78 + rocky_coast * 0.38)
        + smoothstep(0.12, 1.10, -laplacian) * rock * 0.38
    )
    # Keep exposed soil in 15-40 m patches instead of one continent-sized
    # low-frequency FBM lobe.
    bare_noise = (
        spectral_noise(shape, 887, 0.85) * 0.62
        + fbm(shape, 887) * 0.38
    )
    bare = smoothstep(
        land_quantile(bare_noise, 72.0),
        land_quantile(bare_noise, 96.0),
        bare_noise,
    ) * (1.0 - shade * 0.5)
    soil = interior * np.clip(0.10 + bare * 0.95 - rock * 0.70, 0.05, 1.0)

    splat_a = np.stack((wet_sand, dry_sand, soil, grass_green), axis=-1)
    splat_b = np.stack((grass_dry, rock, litter, pebbles), axis=-1)
    splat_contrast = 2.6
    total = np.maximum(splat_a.sum(axis=-1) + splat_b.sum(axis=-1), 1e-6)
    splat_a /= total[..., None]
    splat_b /= total[..., None]
    splat_a = np.power(splat_a, splat_contrast)
    splat_b = np.power(splat_b, splat_contrast)
    total = np.maximum(splat_a.sum(axis=-1) + splat_b.sum(axis=-1), 1e-6)
    splat_a /= total[..., None]
    splat_b /= total[..., None]

    canopy_density = (
        land
        * smoothstep(2.0, 9.0, sdf_m)
        * (1.0 - smoothstep(38.0, 55.0, slope_degrees))
        * canopy_raw
    )
    # A coastal boost creates the beach -> scrub -> tree transition.
    canopy_density *= np.clip(1.0 + np.exp(-np.square((sdf_m - 11.0) / 9.0)) * 0.35, 0.0, 1.0)
    shrub_density = interior * (1.0 - smoothstep(34.0, 49.0, slope_degrees)) * np.clip(0.28 + moisture * 0.85, 0.0, 1.0)
    grass_density = interior * (1.0 - smoothstep(29.0, 43.0, slope_degrees)) * np.clip(0.34 + grass_green + grass_dry * 0.72, 0.0, 1.0)
    rock_density = land * np.clip(rock * 0.92 + smoothstep(6.0, 28.0, -laplacian) * 0.24 + pebbles * 0.25, 0.0, 1.0)
    density = np.stack(
        (canopy_density, shrub_density, grass_density, rock_density), axis=-1
    )

    detail = np.stack(
        (fbm(shape, 907), ridged, moisture, np.clip((laplacian + 4.0) / 8.0, 0.0, 1.0)),
        axis=-1,
    )
    return {
        "land": land,
        "sdf_m": sdf_m,
        "height_m": height_m,
        "splat_a": splat_a,
        "splat_b": splat_b,
        "density": density,
        "detail": detail,
        "slope_degrees": slope_degrees,
        "terrain_normal": bake_normal_map(height_m),
        "terrain_ao": bake_ambient_occlusion(height_m),
    }


def main() -> None:
    root = project_root()
    texture_root = root / "assets" / "environment" / "island_biome" / "world"
    source_root = root / "assets" / "environment" / "island_biome" / "source" / "world"
    preview_root = root / "previews" / "island_biome"
    fields = build_world_fields()
    sdf_normalized = (fields["sdf_m"] - SDF_MIN_M) / (SDF_MAX_M - SDF_MIN_M)
    height_normalized = (fields["height_m"] - HEIGHT_MIN_M) / (HEIGHT_MAX_M - HEIGHT_MIN_M)
    save_png16_gray(texture_root / "island_sdf_r16.png", sdf_normalized)
    save_png16_gray(texture_root / "island_height_r16.png", height_normalized)
    save_float32_map(texture_root / "island_sdf_f32.bin", fields["sdf_m"])
    save_float32_map(texture_root / "island_height_f32.bin", fields["height_m"])
    # Blender converts these floating-point sources into standards-compliant
    # float32 EXR authoring files after this process completes.
    source_root.mkdir(parents=True, exist_ok=True)
    np.save(source_root / "island_sdf_float.npy", fields["sdf_m"].astype(np.float32))
    np.save(source_root / "island_height_float.npy", fields["height_m"].astype(np.float32))
    save_png8(texture_root / "island_splat_a.png", fields["splat_a"])
    save_png8(texture_root / "island_splat_b.png", fields["splat_b"])
    save_png8(texture_root / "island_biome_density.png", fields["density"])
    save_png8(texture_root / "island_detail.png", fields["detail"])
    save_png8(
        texture_root / "island_terrain_normal.png",
        fields["terrain_normal"],
    )
    save_png8(texture_root / "island_terrain_ao.png", fields["terrain_ao"])

    height_preview = np.clip((fields["height_m"] - SEA_LEVEL_M) / 60.0, 0.0, 1.0)
    land = fields["land"]
    preview = np.stack(
        (
            np.where(land, 0.18 + height_preview * 0.46, 0.02),
            np.where(land, 0.24 + fields["density"][..., 0] * 0.52, 0.23),
            np.where(land, 0.10 + fields["splat_b"][..., 1] * 0.48, 0.34),
        ),
        axis=-1,
    )
    save_png8(preview_root / "island_world_fields.png", preview)

    land_area = float(land.sum()) * PIXEL_SIZE_M * PIXEL_SIZE_M
    maximum_slope = float(fields["slope_degrees"][land].max())
    coast_band = land & (fields["sdf_m"] <= 12.0)
    coast_slopes = fields["slope_degrees"][coast_band]
    layer_names = [
        "wet_sand", "dry_sand", "soil", "grass_green",
        "grass_dry", "rock", "litter", "pebbles",
    ]
    combined_splats = np.concatenate(
        (fields["splat_a"], fields["splat_b"]), axis=-1
    )
    dominant_layers = np.argmax(combined_splats[land], axis=-1)
    dominant_shares = {
        name: round(float(np.mean(dominant_layers == index) * 100.0), 2)
        for index, name in enumerate(layer_names)
    }
    dominant_soil = land & (np.argmax(combined_splats, axis=-1) == 2)
    soil_patch_areas = connected_component_areas(dominant_soil)
    largest_soil_patch_pixels = max(soil_patch_areas, default=0)
    total_soil_pixels = max(sum(soil_patch_areas), 1)
    normal_up = np.clip(
        fields["terrain_normal"][..., 2] * 2.0 - 1.0,
        0.0,
        1.0,
    )
    normal_tilt_degrees = np.degrees(np.arccos(normal_up))
    terrain_ao_land = fields["terrain_ao"][land]
    report = {
        "generator": "tools/generate_island_world.py",
        "resolution": [IMAGE_WIDTH, IMAGE_HEIGHT],
        "pixel_size_m": round(PIXEL_SIZE_M, 6),
        "map_size_m": [MAP_WIDTH_M, MAP_LENGTH_M],
        "runtime_encoding": "raw little-endian RF float32, native metres",
        "authoring_encoding": "OpenEXR float32, native metres",
        "preview_height_encoding_m": [HEIGHT_MIN_M, HEIGHT_MAX_M],
        "preview_sdf_encoding_m": [SDF_MIN_M, SDF_MAX_M],
        "land_area_m2": round(land_area, 1),
        "land_area_hectares": round(land_area / 10000.0, 3),
        "minimum_height_m": round(float(fields["height_m"].min()), 3),
        "maximum_height_m": round(float(fields["height_m"].max()), 3),
        "maximum_slope_degrees": round(maximum_slope, 3),
        "coast_slope_degrees": {
            "mean": round(float(np.mean(coast_slopes)), 3),
            "median": round(float(np.median(coast_slopes)), 3),
            "p95": round(float(np.percentile(coast_slopes, 95.0)), 3),
        },
        "cliff_pixels_over_55_degrees": int(
            np.count_nonzero(fields["slope_degrees"][land] > 55.0)
        ),
        "erosion_iterations": EROSION_ITERATIONS,
        "layers": layer_names,
        "dominant_layer_share_percent": dominant_shares,
        "terrain_detail_maps": {
            "normal_pixels_over_20_degrees_percent": round(
                float(np.mean(normal_tilt_degrees[land] > 20.0) * 100.0),
                2,
            ),
            "ao_p01": round(float(np.percentile(terrain_ao_land, 1.0)), 3),
            "ao_median": round(float(np.median(terrain_ao_land)), 3),
        },
        "dominant_soil_patches": {
            "count": len(soil_patch_areas),
            "largest_hectares": round(
                largest_soil_patch_pixels
                * PIXEL_SIZE_M
                * PIXEL_SIZE_M
                / 10000.0,
                3,
            ),
            "largest_share_percent": round(
                largest_soil_patch_pixels / total_soil_pixels * 100.0,
                2,
            ),
        },
        "density_channels": ["canopy", "shrubs", "groundcover", "rocks"],
    }
    (texture_root / "island_world_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("ISLAND_WORLD_OK")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
