#!/bin/zsh
set -euo pipefail

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
blender_executable="${BLENDER_BIN:-}"

if [[ -z "$blender_executable" ]] && [[ -x /Applications/Blender.app/Contents/MacOS/Blender ]]; then
	blender_executable="/Applications/Blender.app/Contents/MacOS/Blender"
fi
if [[ -z "$blender_executable" ]] && command -v blender >/dev/null 2>&1; then
	blender_executable="$(command -v blender)"
fi
if [[ -z "$blender_executable" ]]; then
	print -u2 "Blender no está accesible. Instálalo o define BLENDER_BIN con su ruta."
	exit 2
fi

"$blender_executable" --background --factory-startup --python-exit-code 1 --python "$project_directory/tools/blender/prepare_trellis_villager.py"
