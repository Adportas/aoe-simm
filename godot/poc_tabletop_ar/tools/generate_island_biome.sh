#!/bin/zsh
set -euo pipefail

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
blender_executable="${BLENDER_BIN:-}"
python_executable="${PYTHON_BIN:-/usr/bin/python3}"

if [[ -z "$blender_executable" ]] && [[ -x /Applications/Blender.app/Contents/MacOS/Blender ]]; then
	blender_executable="/Applications/Blender.app/Contents/MacOS/Blender"
fi
if [[ -z "$blender_executable" ]] && command -v blender >/dev/null 2>&1; then
	blender_executable="$(command -v blender)"
fi
if [[ -z "$blender_executable" ]]; then
	print -u2 "Blender no esta accesible. Instalalo o define BLENDER_BIN con su ruta."
	exit 2
fi

asset_root="$project_directory/assets/environment/island_biome"

"$python_executable" -B "$project_directory/tools/generate_island_world.py"

"$blender_executable" \
	--background \
	--python-exit-code 1 \
	--python "$project_directory/tools/blender/bake_island_world_exr.py" \
	-- "$asset_root/source/world" "$asset_root/world"

"$project_directory/tools/build_palm_frond_atlas.sh"

"$blender_executable" \
	--background \
	--python-exit-code 1 \
	--python "$project_directory/tools/blender/generate_palms.py" \
	-- "$asset_root/palms"

"$python_executable" -B "$project_directory/tools/generate_island_textures.py"

"$project_directory/tools/build_shrub_atlas.sh"

"$blender_executable" \
	--background \
	--python-exit-code 1 \
	--python "$project_directory/tools/blender/generate_island_props.py" \
	-- "$asset_root"

print "ISLAND_BIOME_ASSETS_OK"
