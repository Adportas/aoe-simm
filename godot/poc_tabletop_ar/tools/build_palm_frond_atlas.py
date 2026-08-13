#!/usr/bin/env python3
"""Build the runtime palm-frond texture set from the checked-in RGBA source.

The authored source is a 2 x 4 grid.  This tool preserves that cell order,
re-packs it into a square 2K atlas, pads transparent texels to prevent dark
mipmap fringes, and derives lightweight tangent normal and leaf masks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


ATLAS_SIZE = 2048
GRID_COLUMNS = 2
GRID_ROWS = 4
CARD_CELL_SIZE = (ATLAS_SIZE // GRID_COLUMNS, ATLAS_SIZE // GRID_ROWS)
SOURCE_CELL_EXPECTED = (512, 384)
REPACKED_SOURCE_SIZE = (640, 480)
ALPHA_CLIP = 0.42


def parse_arguments() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    source_root = project_root / "art" / "source" / "palm_fronds"
    texture_root = (
        project_root
        / "assets"
        / "environment"
        / "island_biome"
        / "textures"
        / "palms"
    )
    preview_root = project_root / "previews" / "island_biome"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=source_root / "frond_atlas_alpha_raw_v1.png",
    )
    parser.add_argument("--output-root", type=Path, default=texture_root)
    parser.add_argument("--preview-root", type=Path, default=preview_root)
    return parser.parse_args()


def repack_source(source: Image.Image) -> Image.Image:
    expected_size = (
        SOURCE_CELL_EXPECTED[0] * GRID_COLUMNS,
        SOURCE_CELL_EXPECTED[1] * GRID_ROWS,
    )
    if source.size != expected_size:
        raise ValueError(
            f"Expected a {expected_size[0]}x{expected_size[1]} source, "
            f"got {source.width}x{source.height}"
        )
    if source.mode != "RGBA":
        source = source.convert("RGBA")

    atlas = Image.new("RGBA", (ATLAS_SIZE, ATLAS_SIZE), (0, 0, 0, 0))
    cell_width, cell_height = CARD_CELL_SIZE
    resized_width, resized_height = REPACKED_SOURCE_SIZE
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            crop = source.crop(
                (
                    column * SOURCE_CELL_EXPECTED[0],
                    row * SOURCE_CELL_EXPECTED[1],
                    (column + 1) * SOURCE_CELL_EXPECTED[0],
                    (row + 1) * SOURCE_CELL_EXPECTED[1],
                )
            )
            crop = crop.resize(
                (resized_width, resized_height),
                Image.Resampling.LANCZOS,
            )
            destination = (
                column * cell_width + (cell_width - resized_width) // 2,
                row * cell_height + (cell_height - resized_height) // 2,
            )
            atlas.alpha_composite(crop, destination)
    return atlas


def dilate_transparent_rgb(image: Image.Image, iterations: int = 16) -> Image.Image:
    """Extend edge colours under transparent texels for stable mipmaps."""
    pixels = np.asarray(image, dtype=np.uint8).copy()
    alpha = pixels[:, :, 3]
    rgb = pixels[:, :, :3].astype(np.float32)
    filled = alpha > 4
    rgb[~filled] = 0.0

    for _ in range(iterations):
        colour_sum = np.zeros_like(rgb)
        sample_count = np.zeros(filled.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour_mask = np.roll(filled, (dy, dx), axis=(0, 1))
            neighbour_rgb = np.roll(rgb, (dy, dx), axis=(0, 1))
            if dy < 0:
                neighbour_mask[dy:, :] = False
            elif dy > 0:
                neighbour_mask[:dy, :] = False
            if dx < 0:
                neighbour_mask[:, dx:] = False
            elif dx > 0:
                neighbour_mask[:, :dx] = False
            colour_sum += neighbour_rgb * neighbour_mask[:, :, None]
            sample_count += neighbour_mask
        to_fill = (~filled) & (sample_count > 0.0)
        if not np.any(to_fill):
            break
        rgb[to_fill] = colour_sum[to_fill] / sample_count[to_fill, None]
        filled[to_fill] = True

    pixels[:, :, :3] = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(pixels, "RGBA")


def derive_normal_map(albedo: Image.Image) -> Image.Image:
    pixels = np.asarray(albedo, dtype=np.float32) / 255.0
    alpha = pixels[:, :, 3]
    luminance = (
        pixels[:, :, 0] * 0.2126
        + pixels[:, :, 1] * 0.7152
        + pixels[:, :, 2] * 0.0722
    )
    height = np.asarray(
        Image.fromarray(
            np.clip(luminance * alpha * 255.0, 0.0, 255.0).astype(np.uint8),
            "L",
        ).filter(ImageFilter.GaussianBlur(radius=1.15)),
        dtype=np.float32,
    ) / 255.0
    gradient_y, gradient_x = np.gradient(height)
    strength = 18.0
    normal = np.dstack(
        (-gradient_x * strength, gradient_y * strength, np.ones_like(height))
    )
    normal /= np.maximum(
        np.linalg.norm(normal, axis=2, keepdims=True),
        1.0e-6,
    )
    encoded = np.clip(normal * 0.5 + 0.5, 0.0, 1.0)
    encoded[alpha <= 0.001] = (0.5, 0.5, 1.0)
    return Image.fromarray((encoded * 255.0 + 0.5).astype(np.uint8), "RGB")


def derive_leaf_mask(albedo: Image.Image) -> Image.Image:
    pixels = np.asarray(albedo, dtype=np.float32) / 255.0
    alpha = pixels[:, :, 3]
    luminance = (
        pixels[:, :, 0] * 0.2126
        + pixels[:, :, 1] * 0.7152
        + pixels[:, :, 2] * 0.0722
    )
    roughness = np.clip(0.76 + (1.0 - luminance) * 0.16, 0.70, 0.94)
    translucency = np.clip(0.58 + (1.0 - luminance) * 0.30, 0.58, 0.88)
    mask = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    mask[:, :, 0] = np.where(alpha > 0.001, roughness * 255.0, 255.0)
    mask[:, :, 1] = translucency * alpha * 255.0
    mask[:, :, 2] = alpha * 255.0
    mask[:, :, 3] = 255
    return Image.fromarray(mask, "RGBA")


def build_preview(albedo: Image.Image, output_path: Path) -> None:
    tile = 32
    y, x = np.indices((ATLAS_SIZE, ATLAS_SIZE))
    checker = ((x // tile + y // tile) & 1).astype(np.uint8)
    background = np.where(checker[:, :, None] == 0, 72, 112).astype(np.uint8)
    background = np.repeat(background, 3, axis=2)
    background_rgba = np.dstack(
        (background, np.full((ATLAS_SIZE, ATLAS_SIZE), 255, dtype=np.uint8))
    )
    composite = Image.alpha_composite(
        Image.fromarray(background_rgba, "RGBA"),
        albedo,
    )
    composite.resize((1024, 1024), Image.Resampling.LANCZOS).save(
        output_path,
        optimize=True,
    )


def validation_report(albedo: Image.Image, source_path: Path) -> dict[str, object]:
    pixels = np.asarray(albedo, dtype=np.uint8)
    alpha = pixels[:, :, 3]
    visible = alpha >= round(ALPHA_CLIP * 255.0)
    partial = (alpha > 0) & (alpha < 255)
    cells: list[dict[str, object]] = []
    cell_width, cell_height = CARD_CELL_SIZE
    labels = (
        "fan_green",
        "fan_yellow_green",
        "date_arching",
        "date_dense",
        "date_warm",
        "coconut_long",
        "coconut_open",
        "coconut_brown_tip",
    )
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            index = row * GRID_COLUMNS + column
            cell_alpha = alpha[
                row * cell_height : (row + 1) * cell_height,
                column * cell_width : (column + 1) * cell_width,
            ]
            coverage = np.count_nonzero(cell_alpha >= round(ALPHA_CLIP * 255.0))
            cells.append(
                {
                    "index": index,
                    "label": labels[index],
                    "column": column,
                    "row_from_top": row,
                    "alpha_clip_coverage_percent": round(
                        coverage * 100.0 / cell_alpha.size,
                        3,
                    ),
                }
            )

    rgb = pixels[:, :, :3].astype(np.float32)
    suspicious_magenta = (
        visible
        & (rgb[:, :, 0] > rgb[:, :, 1] * 1.35 + 10.0)
        & (rgb[:, :, 2] > rgb[:, :, 1] * 1.35 + 10.0)
    )
    return {
        "source": source_path.as_posix(),
        "atlas_size": [ATLAS_SIZE, ATLAS_SIZE],
        "grid": [GRID_COLUMNS, GRID_ROWS],
        "alpha_clip": ALPHA_CLIP,
        "visible_percent": round(np.count_nonzero(visible) * 100.0 / alpha.size, 3),
        "partial_alpha_percent": round(
            np.count_nonzero(partial) * 100.0 / alpha.size,
            3,
        ),
        "suspicious_magenta_visible_percent": round(
            np.count_nonzero(suspicious_magenta) * 100.0
            / max(np.count_nonzero(visible), 1),
            5,
        ),
        "cells": cells,
    }


def main() -> None:
    arguments = parse_arguments()
    arguments.output_root.mkdir(parents=True, exist_ok=True)
    arguments.preview_root.mkdir(parents=True, exist_ok=True)
    source = Image.open(arguments.input).convert("RGBA")
    atlas = dilate_transparent_rgb(repack_source(source))
    normal = derive_normal_map(atlas)
    mask = derive_leaf_mask(atlas)

    albedo_path = arguments.output_root / "palm_frond_atlas_albedo_v1.png"
    normal_path = arguments.output_root / "palm_frond_atlas_normal_v1.png"
    mask_path = arguments.output_root / "palm_frond_atlas_mask_v1.png"
    report_path = arguments.output_root / "palm_frond_atlas_report.json"
    preview_path = arguments.preview_root / "palm_frond_atlas.png"
    atlas.save(albedo_path, optimize=True)
    normal.save(normal_path, optimize=True)
    mask.save(mask_path, optimize=True)
    build_preview(atlas, preview_path)
    report = validation_report(atlas, arguments.input)
    report.update(
        {
            "albedo": albedo_path.as_posix(),
            "normal": normal_path.as_posix(),
            "mask": mask_path.as_posix(),
            "preview": preview_path.as_posix(),
        }
    )
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("PALM_FROND_ATLAS_OK")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
