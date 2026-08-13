#!/usr/bin/env python3
"""Build the shared 2K shrub-card texture set from the checked-in RGBA source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from build_palm_frond_atlas import (
    ALPHA_CLIP,
    ATLAS_SIZE,
    CARD_CELL_SIZE,
    GRID_COLUMNS,
    GRID_ROWS,
    build_preview,
    derive_leaf_mask,
    derive_normal_map,
    dilate_transparent_rgb,
    repack_source,
)


CELL_LABELS = (
    "dense_deep_green",
    "dense_fresh_green",
    "dense_round",
    "dense_sun_exposed",
    "wild_branching",
    "wild_open",
    "wild_yellow_green",
    "wild_brown_tips",
)


def parse_arguments() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            project_root
            / "art"
            / "source"
            / "shrub_foliage"
            / "shrub_atlas_alpha_raw_v1.png"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            project_root
            / "assets"
            / "environment"
            / "island_biome"
            / "textures"
            / "shrubs"
        ),
    )
    parser.add_argument(
        "--preview-root",
        type=Path,
        default=project_root / "previews" / "island_biome",
    )
    return parser.parse_args()


def validation_report(albedo: Image.Image, source_path: Path) -> dict[str, object]:
    pixels = np.asarray(albedo, dtype=np.uint8)
    alpha = pixels[:, :, 3]
    threshold = round(ALPHA_CLIP * 255.0)
    visible = alpha >= threshold
    partial = (alpha > 0) & (alpha < 255)
    cell_width, cell_height = CARD_CELL_SIZE
    cells: list[dict[str, object]] = []
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            index = row * GRID_COLUMNS + column
            cell_alpha = alpha[
                row * cell_height : (row + 1) * cell_height,
                column * cell_width : (column + 1) * cell_width,
            ]
            coverage = np.count_nonzero(cell_alpha >= threshold)
            cells.append(
                {
                    "index": index,
                    "label": CELL_LABELS[index],
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
        "visible_percent": round(
            np.count_nonzero(visible) * 100.0 / alpha.size,
            3,
        ),
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

    albedo_path = arguments.output_root / "shrub_atlas_albedo_v1.png"
    normal_path = arguments.output_root / "shrub_atlas_normal_v1.png"
    mask_path = arguments.output_root / "shrub_atlas_mask_v1.png"
    report_path = arguments.output_root / "shrub_atlas_report.json"
    preview_path = arguments.preview_root / "shrub_foliage_atlas.png"
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
    print("SHRUB_ATLAS_OK")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
