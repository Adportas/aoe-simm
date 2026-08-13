#!/bin/zsh
set -euo pipefail

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
preset_template="$project_directory/export_presets.web.example"
active_preset="$project_directory/export_presets.cfg"
output_directory="${1:-$project_directory/exports/web-preview}"
preset_backup="$(mktemp "${TMPDIR:-/tmp}/tabletop_web_preset.XXXXXX")"
had_active_preset=false

function cleanup {
	if $had_active_preset; then
		cp "$preset_backup" "$active_preset"
	else
		rm -f "$active_preset"
	fi
	rm -f "$preset_backup"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ -f "$active_preset" ]]; then
	cp "$active_preset" "$preset_backup"
	had_active_preset=true
fi
cp "$preset_template" "$active_preset"

if [[ -n "${GODOT_WEB_TEMPLATE_RELEASE:-}" ]]; then
	if [[ ! -f "$GODOT_WEB_TEMPLATE_RELEASE" ]]; then
		print -u2 "No existe GODOT_WEB_TEMPLATE_RELEASE=$GODOT_WEB_TEMPLATE_RELEASE"
		exit 1
	fi
	template_value="${GODOT_WEB_TEMPLATE_RELEASE//\\/\\\\}"
	template_value="${template_value//\"/\\\"}"
	if sed --version >/dev/null 2>&1; then
		sed -i "s|custom_template/release=\"\"|custom_template/release=\"$template_value\"|" "$active_preset"
	else
		sed -i '' "s|custom_template/release=\"\"|custom_template/release=\"$template_value\"|" "$active_preset"
	fi
fi

mkdir -p "$output_directory"
godot --headless --path "$project_directory" \
	--export-release "Web Preview" "$output_directory/index.html"
mkdir -p "$output_directory/quicklook"
cp "$project_directory/web/quicklook/isla-aoe.usdz" \
	"$output_directory/quicklook/isla-aoe.usdz"
cp "$project_directory/web/quicklook/isla-aoe-preview.png" \
	"$output_directory/quicklook/isla-aoe-preview.png"
touch "$output_directory/.nojekyll"

for required_file in \
	index.html \
	index.js \
	index.wasm \
	index.pck \
	quicklook/isla-aoe.usdz \
	quicklook/isla-aoe-preview.png; do
	if [[ ! -s "$output_directory/$required_file" ]]; then
		print -u2 "Falta el archivo Web exportado: $required_file"
		exit 1
	fi
done

print "Vista web exportada en $output_directory/index.html"
print "Servir localmente: python3 '$script_directory/serve_web_preview.py' --directory '$output_directory'"
