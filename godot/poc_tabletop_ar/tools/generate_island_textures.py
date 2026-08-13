"""Create seamless terrain layers from the supplied island reference.

This runs outside Blender because forking image decoders from Blender's
multithreaded macOS process can deadlock. The outputs are deterministic RGB
PNGs and need only NumPy plus the system ffmpeg executable for JPEG decoding.

The eight layer stacks are deliberately 1K rather than 4K: at the 1:400
presentation scale, strong normal/height information matters more than raw
texel count. ``layer_orm`` is packed as R=height, G=roughness, B=AO.
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import zlib
from pathlib import Path

import numpy as np


TEXTURE_SIZE = 1024
LAYER_ORDER = (
    "wet_sand",
    "dry_sand",
    "soil",
    "grass_green",
    "grass_dry",
    "rock",
    "litter",
    "pebbles",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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

    return {
        "grass": median_or(grass_mask, (0.22, 0.28, 0.13)),
        "soil": median_or(soil_mask, (0.12, 0.105, 0.085)),
        "sand": median_or(sand_mask, (0.72, 0.68, 0.54)),
    }


def normal_from_height(height: np.ndarray, strength: float) -> np.ndarray:
    derivative_x = np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)
    derivative_y = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    normal = np.stack(
        (-derivative_x * strength, -derivative_y * strength, np.ones_like(height)),
        axis=-1,
    )
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return normal * 0.5 + 0.5


def smoothstep(edge_low: float, edge_high: float, values: np.ndarray) -> np.ndarray:
    t = np.clip((values - edge_low) / (edge_high - edge_low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ambient_occlusion_from_height(height: np.ndarray) -> np.ndarray:
    """Cheap tileable cavity proxy for the blue channel of layer ORM maps."""
    neighbours = (
        np.roll(height, 1, axis=0)
        + np.roll(height, -1, axis=0)
        + np.roll(height, 1, axis=1)
        + np.roll(height, -1, axis=1)
        + np.roll(np.roll(height, 1, axis=0), 1, axis=1)
        + np.roll(np.roll(height, 1, axis=0), -1, axis=1)
        + np.roll(np.roll(height, -1, axis=0), 1, axis=1)
        + np.roll(np.roll(height, -1, axis=0), -1, axis=1)
    ) / 8.0
    cavity = np.clip(neighbours - height, 0.0, 1.0)
    return np.clip(1.0 - cavity * 3.2, 0.62, 1.0)


def png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    body = chunk_type + payload
    return (
        struct.pack(">I", len(payload))
        + body
        + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    )


def save_png(path: Path, rgb_or_gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rgb_or_gray.ndim == 2:
        rgb = np.repeat(rgb_or_gray[..., None], 3, axis=-1)
    else:
        rgb = rgb_or_gray
    pixels = np.rint(np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    height, width = pixels.shape[:2]
    scanlines = b"".join(
        b"\x00" + pixels[row].tobytes() for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(scanlines, level=7))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> None:
    root = project_root()
    asset_root = root / "assets" / "environment" / "island_biome"
    texture_root = asset_root / "textures"
    reference_path = root / "art" / "references" / "island_biome" / "foto_1.jpg"
    palette = load_reference_palette(reference_path)
    size = TEXTURE_SIZE
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / float(size)
    albedos: dict[str, np.ndarray] = {}

    grass_macro = spectral_noise(size, 101, 1.55)
    grass_fine = spectral_noise(size, 103, 0.58)
    grass_height = np.clip(grass_macro * 0.63 + grass_fine * 0.37, 0.0, 1.0)
    grass_albedo = palette["grass"][None, None, :] * np.array(
        [0.78, 0.91, 0.72], dtype=np.float32
    )
    grass_albedo = grass_albedo * (0.64 + grass_height[..., None] * 0.55)
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

    # Additional authored stand-ins for the eight splat layers. These keep the
    # complete material pipeline usable before production sets replace them
    # one-for-one.
    dry_grass_noise = spectral_noise(size, 353, 0.72)
    grass_dry_height = np.clip(
        grass_height * 0.58 + dry_grass_noise * 0.42, 0.0, 1.0
    )
    grass_dry_albedo = (
        grass_albedo * np.array([1.18, 0.96, 0.48], dtype=np.float32)
        + soil_albedo * np.array([0.34, 0.26, 0.12], dtype=np.float32)
    ) * 0.78
    dry_straw = spectral_noise(size, 359, 0.28) > 0.81
    grass_dry_albedo[dry_straw] = (
        grass_dry_albedo[dry_straw] * 0.38
        + np.array([0.58, 0.42, 0.14], dtype=np.float32) * 0.62
    )
    grass_dry_roughness = np.clip(
        0.93 + (dry_grass_noise - 0.5) * 0.08, 0.84, 0.99
    )

    rock_macro = spectral_noise(size, 401, 1.28)
    rock_fine = spectral_noise(size, 409, 0.34)
    rock_strata = (
        np.sin((xx * 9.0 + yy * 5.0) * math.tau + rock_macro * 2.7) * 0.5
        + 0.5
    )
    rock_height = np.clip(
        rock_macro * 0.46 + rock_fine * 0.28 + rock_strata * 0.26,
        0.0,
        1.0,
    )
    rock_base = palette["soil"] * 0.34 + palette["sand"] * 0.66
    rock_albedo = rock_base[None, None, :] * np.array(
        [0.82, 0.80, 0.74], dtype=np.float32
    )
    rock_albedo = rock_albedo * (0.63 + rock_height[..., None] * 0.55)
    mineral = spectral_noise(size, 419, 0.22) > 0.91
    rock_albedo[mineral] = np.minimum(
        1.0,
        rock_albedo[mineral] * np.array([1.18, 1.12, 1.02], dtype=np.float32),
    )
    rock_roughness = np.clip(0.82 + (rock_fine - 0.5) * 0.20, 0.64, 0.96)

    litter_field = spectral_noise(size, 503, 0.24)
    litter_shape = smoothstep(0.70, 0.88, litter_field)
    litter_height = np.clip(soil_height * 0.42 + litter_shape * 0.58, 0.0, 1.0)
    litter_albedo = soil_albedo * np.array([0.92, 0.80, 0.67], dtype=np.float32)
    orange_leaf = litter_field > 0.77
    brown_leaf = spectral_noise(size, 509, 0.20) > 0.85
    litter_albedo[orange_leaf] = (
        litter_albedo[orange_leaf] * 0.34
        + np.array([0.42, 0.22, 0.065], dtype=np.float32) * 0.66
    )
    litter_albedo[brown_leaf] = (
        litter_albedo[brown_leaf] * 0.42
        + np.array([0.22, 0.105, 0.035], dtype=np.float32) * 0.58
    )
    litter_roughness = np.clip(
        0.90 + (litter_field - 0.5) * 0.10, 0.79, 0.99
    )

    pebble_field = spectral_noise(size, 557, 0.18)
    pebble_shape = smoothstep(0.69, 0.86, pebble_field)
    pebbles_height = np.clip(
        sand_height * 0.28 + pebble_shape * 0.72, 0.0, 1.0
    )
    pebbles_albedo = sand_albedo * (1.0 - pebble_shape[..., None] * 0.48)
    pebbles_albedo += rock_albedo * pebble_shape[..., None] * 0.76
    pale_pebbles = spectral_noise(size, 563, 0.19) > 0.89
    pebbles_albedo[pale_pebbles] = np.minimum(
        1.0, pebbles_albedo[pale_pebbles] * 1.18
    )
    pebbles_roughness = np.clip(
        0.86 + (pebble_field - 0.5) * 0.13, 0.72, 0.97
    )

    texture_data = {
        "grass": (grass_albedo, grass_height, grass_roughness, 8.0),
        "soil": (soil_albedo, soil_height, soil_roughness, 9.5),
        "sand": (sand_albedo, sand_height, sand_roughness, 6.5),
    }
    for key, (albedo, height, roughness, normal_strength) in texture_data.items():
        save_png(texture_root / f"ground_{key}_albedo.png", albedo)
        save_png(
            texture_root / f"ground_{key}_normal.png",
            normal_from_height(height, normal_strength),
        )
        save_png(texture_root / f"ground_{key}_roughness.png", roughness)

    layer_data: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {
        "wet_sand": (
            sand_albedo * np.array([0.78, 0.81, 0.77], dtype=np.float32),
            np.clip(sand_height * 0.86, 0.0, 1.0),
            np.clip(0.53 + (sand_fine - 0.5) * 0.14, 0.38, 0.67),
            7.5,
        ),
        "dry_sand": (sand_albedo, sand_height, sand_roughness, 6.5),
        "soil": (soil_albedo, soil_height, soil_roughness, 9.5),
        "grass_green": (grass_albedo, grass_height, grass_roughness, 8.0),
        "grass_dry": (
            grass_dry_albedo,
            grass_dry_height,
            grass_dry_roughness,
            8.5,
        ),
        "rock": (rock_albedo, rock_height, rock_roughness, 14.0),
        "litter": (litter_albedo, litter_height, litter_roughness, 11.0),
        "pebbles": (pebbles_albedo, pebbles_height, pebbles_roughness, 15.0),
    }
    layer_root = texture_root / "layers"
    layer_albedos: list[np.ndarray] = []
    for layer_index, layer_name in enumerate(LAYER_ORDER):
        albedo, height, roughness, normal_strength = layer_data[layer_name]
        albedo = np.asarray(albedo, dtype=np.float32)
        height = np.asarray(height, dtype=np.float32)
        roughness = np.asarray(roughness, dtype=np.float32)
        ao = ambient_occlusion_from_height(height)
        orm = np.stack((height, roughness, ao), axis=-1)
        stem = f"{layer_index:02d}_{layer_name}"
        save_png(layer_root / f"{stem}_albedo.png", albedo)
        save_png(
            layer_root / f"{stem}_normal.png",
            normal_from_height(height, normal_strength),
        )
        save_png(layer_root / f"{stem}_orm.png", orm)
        layer_albedos.append(albedo)

    macro_noise = spectral_noise(size, 601, 1.05)
    detail_height = np.clip(
        spectral_noise(size, 607, 0.30) * 0.72
        + spectral_noise(size, 613, 0.72) * 0.28,
        0.0,
        1.0,
    )
    save_png(texture_root / "terrain_macro_noise.png", macro_noise)
    save_png(
        texture_root / "terrain_detail_normal.png",
        normal_from_height(detail_height, 7.5),
    )

    separator = np.full((size, 8, 3), 0.055, dtype=np.float32)
    preview = np.concatenate(
        (albedos["soil"], separator, albedos["grass"], separator, albedos["sand"]),
        axis=1,
    )
    save_png(root / "previews" / "island_biome" / "ground_materials.png", preview)
    layer_separator = np.full((size, 5, 3), 0.045, dtype=np.float32)
    layer_preview_parts: list[np.ndarray] = []
    for layer_index, albedo in enumerate(layer_albedos):
        if layer_index > 0:
            layer_preview_parts.append(layer_separator)
        layer_preview_parts.append(albedo)
    save_png(
        root / "previews" / "island_biome" / "terrain_layers.png",
        np.concatenate(layer_preview_parts, axis=1),
    )
    report = {
        "reference": str(reference_path.relative_to(root)),
        "texture_size": size,
        "layer_order": list(LAYER_ORDER),
        "layer_packing": {
            "albedo": "RGB sRGB",
            "normal": "RGB tangent-space",
            "orm": "R height, G roughness, B ambient occlusion",
        },
        "palette": {
            key: [round(float(value), 5) for value in color]
            for key, color in palette.items()
        },
    }
    (asset_root / "texture_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("ISLAND_TEXTURES_OK")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
