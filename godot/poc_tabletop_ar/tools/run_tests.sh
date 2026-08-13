#!/bin/zsh
set -euo pipefail

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
test_log="$(mktemp -t tabletop_poc_tests)"

function cleanup {
	rm -f "$test_log"
}
trap cleanup EXIT

godot --headless --path "$project_directory" --import
godot --headless --path "$project_directory" --script res://tests/test_runner.gd 2>&1 | tee "$test_log"
if rg -q "SCRIPT ERROR|SHADER ERROR|Shader compilation failed" "$test_log"; then
	print -u2 "TABLETOP_POC_RUNTIME_OR_SHADER_FAILED"
	exit 1
fi
