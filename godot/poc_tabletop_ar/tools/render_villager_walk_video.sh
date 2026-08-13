#!/bin/zsh

set -euo pipefail
setopt NULL_GLOB

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
OUTPUT_DIR="${PROJECT_DIR}/../../output/godot-walk-verification"
FINAL_VIDEO="${OUTPUT_DIR}/aldeano-isla-rocas-1080p.mp4"
TEMP_VIDEO="${OUTPUT_DIR}/.aldeano-isla-rocas-1080p.tmp.mp4"
CONCAT_LIST="$(mktemp /private/tmp/aoe-villager-concat.XXXXXX)"
FFMPEG="/opt/homebrew/bin/ffmpeg"
PORT=45821
TOTAL_FRAMES=937
SEGMENT_FRAMES=48
PARTS=()

mkdir -p "${OUTPUT_DIR}"
rm -f "${FINAL_VIDEO}" "${TEMP_VIDEO}"

cleanup() {
	rm -f \
		"${TEMP_VIDEO}" \
		"${CONCAT_LIST}"
}
trap cleanup EXIT INT TERM

segment_start=0
segment_index=0
while (( segment_start < TOTAL_FRAMES )); do
	segment_count=$(( TOTAL_FRAMES - segment_start ))
	if (( segment_count > SEGMENT_FRAMES )); then
		segment_count=${SEGMENT_FRAMES}
	fi
	part_path="${OUTPUT_DIR}/.aldeano-isla-parte-${(l:2::0:)segment_index}.mp4"
	PARTS+=("${part_path}")
	if [[ -s "${part_path}" ]]; then
		segment_start=$(( segment_start + segment_count ))
		segment_index=$(( segment_index + 1 ))
		continue
	fi
	rm -f "${part_path}"

	"${FFMPEG}" \
		-hide_banner -loglevel error -y \
		-f rawvideo -pixel_format rgba -video_size 1920x1080 -framerate 24 \
		-i "tcp://127.0.0.1:${PORT}?listen=1" -an \
		-c:v h264_videotoolbox -realtime true \
		-b:v 3500k -maxrate 4500k -bufsize 9000k \
		-profile:v high -pix_fmt yuv420p -tag:v avc1 \
		-g 48 -movflags +frag_keyframe+empty_moov+default_base_moof \
		"${part_path}" &
	encoder_pid=$!

	VIDEO_SEGMENT_START=${segment_start} \
	VIDEO_SEGMENT_COUNT=${segment_count} \
		godot --path "${PROJECT_DIR}" \
		--script "${PROJECT_DIR}/tools/render_villager_walk_video.gd"
	wait ${encoder_pid}

	segment_start=$(( segment_start + segment_count ))
	segment_index=$(( segment_index + 1 ))
	if (( segment_start < TOTAL_FRAMES )); then
		print -r -- "VILLAGER_VIDEO_RESUME_AT=${segment_start}"
		exit 0
	fi
done

for part_path in "${PARTS[@]}"; do
	print -r -- "file ${part_path}" >> "${CONCAT_LIST}"
done
"${FFMPEG}" \
	-hide_banner -loglevel error -y \
	-f concat -safe 0 -i "${CONCAT_LIST}" \
	-c copy -movflags +faststart "${TEMP_VIDEO}"

mv "${TEMP_VIDEO}" "${FINAL_VIDEO}"
trap - EXIT INT TERM
rm -f "${OUTPUT_DIR}"/.aldeano-isla-parte-*.mp4
rm -f "${CONCAT_LIST}"
print -r -- "VILLAGER_VIDEO_OK=${FINAL_VIDEO}"
