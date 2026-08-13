#!/bin/zsh
set -euo pipefail

plugin_revision="3781b9c19eaf69b2387eacecf4b6f88fc8d07e65"
archive_name="GodotApplePlugins-addons-${plugin_revision}.zip"
expected_sha256="f9128c17c2d0128c2d58168c5bb5c795d351cb1333364179fd7a26c39f95ce21"
download_url="https://github.com/migueldeicaza/GodotApplePlugins/releases/download/build-${plugin_revision}/${archive_name}"

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
temporary_directory="$(mktemp -d /tmp/tabletop-apple-plugins.XXXXXX)"
archive_path="${temporary_directory}/${archive_name}"
trap 'rm -rf "$temporary_directory"' EXIT

curl -fL "$download_url" -o "$archive_path"
actual_sha256="$(env LC_ALL=C LANG=C shasum -a 256 "$archive_path" | awk '{print $1}')"
if [[ "$actual_sha256" != "$expected_sha256" ]]; then
	print -u2 "Checksum inesperado: $actual_sha256"
	exit 1
fi

unzip -q "$archive_path" \
	'dist/addons/GodotApplePluginsARKit/*' \
	'dist/addons/GodotApplePluginsRuntime/*' \
	-d "$temporary_directory/extracted"
mkdir -p "$project_directory/addons"
cp -R "$temporary_directory/extracted/dist/addons/GodotApplePluginsARKit" "$project_directory/addons/"
cp -R "$temporary_directory/extracted/dist/addons/GodotApplePluginsRuntime" "$project_directory/addons/"
print "Complementos ARKit instalados en $project_directory/addons"
