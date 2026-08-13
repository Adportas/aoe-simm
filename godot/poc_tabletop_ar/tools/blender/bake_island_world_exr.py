"""Convert baked NumPy island fields to standards-compliant float32 EXR."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import OpenImageIO as oiio


def arguments() -> tuple[Path, Path]:
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(values) != 2:
        raise SystemExit("Expected source and output directories")
    return Path(values[0]).resolve(), Path(values[1]).resolve()


def save_field(source_path: Path, output_path: Path, name: str) -> None:
    values = np.load(source_path).astype(np.float32, copy=False)
    height, width = values.shape

    spec = oiio.ImageSpec(width, height, 1, oiio.FLOAT)
    spec.channelnames = ["R"]
    spec.attribute("compression", "zip")
    spec.attribute("oiio:ColorSpace", "scene_linear")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = oiio.ImageOutput.create(str(output_path))
    if output is None or not output.open(str(output_path), spec):
        error = oiio.geterror() if output is None else output.geterror()
        raise RuntimeError(f"Cannot open {output_path}: {error}")
    if not output.write_image(values[..., np.newaxis]):
        raise RuntimeError(f"Cannot write {output_path}: {output.geterror()}")
    output.close()

    image_input = oiio.ImageInput.open(str(output_path))
    if image_input is None:
        raise RuntimeError(f"Cannot reopen {output_path}: {oiio.geterror()}")
    verification = np.asarray(image_input.read_image(format=oiio.FLOAT))
    image_input.close()

    source_center = float(values[height // 2, width // 2])
    stored_center = float(verification[height // 2, width // 2, 0])
    tolerance = 1.0e-5
    if not np.isfinite(stored_center) or abs(stored_center - source_center) > tolerance:
        raise RuntimeError(
            f"EXR verification failed for {name}: "
            f"source={source_center}, stored={stored_center}"
        )
    print(
        f"{name}: source=[{float(values.min()):.3f}, {float(values.max()):.3f}] "
        f"stored=[{float(verification.min()):.3f}, {float(verification.max()):.3f}] "
        f"center={stored_center:.3f}"
    )


def main() -> None:
    source_root, output_root = arguments()
    save_field(
        source_root / "island_sdf_float.npy",
        output_root / "island_sdf.exr",
        "IslandSdfMetres",
    )
    save_field(
        source_root / "island_height_float.npy",
        output_root / "island_height.exr",
        "IslandHeightMetres",
    )
    print("ISLAND_WORLD_EXR_OK")


if __name__ == "__main__":
    main()
