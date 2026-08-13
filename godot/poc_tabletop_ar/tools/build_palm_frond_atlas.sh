#!/bin/zsh
set -euo pipefail

script_directory="${0:A:h}"
atlas_uv_cache="/tmp/aoe-vr-palm-frond-atlas-uv"

if ! command -v uv >/dev/null 2>&1; then
	print -u2 "Se necesita uv para ejecutar Pillow y NumPy sin modificar el Python del sistema."
	exit 2
fi

uv --cache-dir "$atlas_uv_cache" run \
	--with pillow \
	--with numpy \
	python "$script_directory/build_palm_frond_atlas.py" "$@"
