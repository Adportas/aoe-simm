#!/bin/zsh

set -euo pipefail
setopt NULL_GLOB

script_directory="${0:A:h}"
project_directory="${script_directory:h}"
output_directory="${project_directory}/../../output/godot-walk-verification"
final_video="${output_directory}/aldeano-marcha-corregida-isla-primer-plano-1080p.mp4"
temporary_video="${output_directory}/.aldeano-marcha-corregida.tmp.mp4"
concat_list="$(mktemp /private/tmp/aoe-villager-detail-concat.XXXXXX)"
ffmpeg_bin="/opt/homebrew/bin/ffmpeg"
port=45822
total_frames=240
segment_frames=48
parts=()

mkdir -p "${output_directory}"
rm -f "${final_video}" "${temporary_video}"

cleanup() {
	rm -f "${temporary_video}" "${concat_list}"
}
trap cleanup EXIT INT TERM

segment_start=0
segment_index=0
while (( segment_start < total_frames )); do
	segment_count=$(( total_frames - segment_start ))
	if (( segment_count > segment_frames )); then
		segment_count=${segment_frames}
	fi
	part_path="${output_directory}/.aldeano-marcha-v2-detalle-${(l:2::0:)segment_index}.mp4"
	parts+=("${part_path}")
	if [[ -s "${part_path}" ]]; then
		segment_start=$(( segment_start + segment_count ))
		segment_index=$(( segment_index + 1 ))
		continue
	fi
	rm -f "${part_path}"

	"${ffmpeg_bin}" \
		-hide_banner -loglevel error -y \
		-f rawvideo -pixel_format rgba -video_size 1920x1080 -framerate 24 \
		-i "tcp://127.0.0.1:${port}?listen=1" -an \
		-c:v h264_videotoolbox -realtime true \
		-b:v 5000k -maxrate 6500k -bufsize 13000k \
		-profile:v high -pix_fmt yuv420p -tag:v avc1 \
		-g 48 -movflags +frag_keyframe+empty_moov+default_base_moof \
		"${part_path}" &
	encoder_pid=$!

	VIDEO_SEGMENT_START=${segment_start} \
	VIDEO_SEGMENT_COUNT=${segment_count} \
		godot --path "${project_directory}" \
		--script "${project_directory}/tools/render_villager_walk_detail_video.gd"
	wait ${encoder_pid}

	segment_start=$(( segment_start + segment_count ))
	segment_index=$(( segment_index + 1 ))
	if (( segment_start < total_frames )); then
		print -r -- "VILLAGER_DETAIL_RESUME_AT=${segment_start}"
		exit 0
	fi
done

for part_path in "${parts[@]}"; do
	print -r -- "file ${part_path}" >> "${concat_list}"
done
"${ffmpeg_bin}" \
	-hide_banner -loglevel error -y \
	-f concat -safe 0 -i "${concat_list}" \
	-c copy -movflags +faststart "${temporary_video}"

mv "${temporary_video}" "${final_video}"
trap - EXIT INT TERM
rm -f "${output_directory}"/.aldeano-marcha-v2-detalle-*.mp4
rm -f "${concat_list}"
print -r -- "VILLAGER_DETAIL_VIDEO_OK=${final_video}"
