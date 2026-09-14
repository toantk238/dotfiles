#!/usr/bin/env bash
# Shrink one or more videos to a max file size, optionally downscaling, as mp4 or webm.
#
# usage: ./shrink.sh [-x] [-m MAX_MB] [-s HEIGHT] [-f mp4|webm] [-o OUTDIR] file1 [file2 ...]
#   -x  fast mode: single pass, hardware H.264 (mp4) or VP9 realtime (webm)
#   -m  max size in MB            (default 100)
#   -s  scale to this height, e.g. 720 or 1080 (default: keep original)
#   -f  output format mp4 or webm (default mp4)
#   -o  output directory          (default: next to input)
# Output name: <input basename>_small.<ext>
# If an encode lands over the cap it is retried at a lower bitrate (max 3 tries).
set -euo pipefail

max_mb=100; height=""; fmt="mp4"; outdir=""; fast=0
while getopts "xm:s:f:o:h" opt; do
  case "$opt" in
    x) fast=1 ;;
    m) max_mb="$OPTARG" ;;
    s) height="$OPTARG" ;;
    f) fmt="$OPTARG" ;;
    o) outdir="$OPTARG" ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
  esac
done
shift $((OPTIND - 1))
[[ $# -ge 1 ]] || { sed -n '2,12p' "$0"; exit 1; }

hwdec=()
case "$fmt" in
  mp4)
    acodec="aac"; ext="mp4"; extra=(-movflags +faststart)
    if (( fast )); then vcodec="h264_videotoolbox"; hwdec=(-hwaccel videotoolbox)
    else vcodec="libx264"; extra+=(-preset medium); fi ;;
  webm)
    acodec="libopus"; ext="webm"; extra=(-row-mt 1); vcodec="libvpx-vp9"
    if (( fast )); then extra+=(-deadline realtime -cpu-used 8)
    else extra+=(-deadline good -cpu-used 2); fi ;;
  *) echo "unknown format: $fmt (use mp4 or webm)" >&2; exit 1 ;;
esac

vf=()
[[ -n "$height" ]] && vf=(-vf "scale=-2:${height}")
audio_k=128
max_bytes=$(( max_mb * 1000 * 1000 ))

encode() { # $1=in $2=out $3=video_kbps
  local in="$1" out="$2" vk="$3"
  if (( fast )); then
    ffmpeg -y -hide_banner -loglevel error -stats "${hwdec[@]}" -i "$in" "${vf[@]}" \
      -c:v "$vcodec" -b:v "${vk}k" -maxrate "${vk}k" -bufsize "$((vk*2))k" "${extra[@]}" \
      -c:a "$acodec" -b:a "${audio_k}k" "$out"
  else
    local logdir; logdir="$(mktemp -d)"
    ffmpeg -y -hide_banner -loglevel error -stats -i "$in" "${vf[@]}" \
      -c:v "$vcodec" -b:v "${vk}k" "${extra[@]}" -pass 1 -passlogfile "$logdir/p" -an -f null /dev/null
    ffmpeg -y -hide_banner -loglevel error -stats -i "$in" "${vf[@]}" \
      -c:v "$vcodec" -b:v "${vk}k" "${extra[@]}" -pass 2 -passlogfile "$logdir/p" \
      -c:a "$acodec" -b:a "${audio_k}k" "$out"
    rm -rf "$logdir"
  fi
}

for in in "$@"; do
  base="$(basename "${in%.*}")"
  dir="${outdir:-$(dirname "$in")}"
  mkdir -p "$dir"
  out="${dir}/${base}_small.${ext}"

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$in")
  # target kbps = MB * 8000 / seconds, with 10% headroom for container overhead / overshoot
  total_k=$(awk -v mb="$max_mb" -v d="$dur" 'BEGIN{printf "%d", mb*8000*0.90/d}')
  video_k=$(( total_k - audio_k ))
  if (( video_k < 100 )); then
    echo "SKIP $in: target too small (video would be ${video_k} kbps). Lower -s or raise -m." >&2
    continue
  fi

  for attempt in 1 2 3; do
    echo "==> $in -> $out  (${dur%.*}s, try $attempt: video ${video_k} kbps, audio ${audio_k} kbps)"
    encode "$in" "$out" "$video_k"
    size=$(stat -f %z "$out")
    printf "    result: %.1f MB\n" "$(awk -v b="$size" 'BEGIN{print b/1000000}')"
    (( size <= max_bytes )) && break
    # scale bitrate down by the overshoot ratio plus a little extra margin
    video_k=$(awk -v vk="$video_k" -v s="$size" -v m="$max_bytes" 'BEGIN{printf "%d", vk*m/s*0.93}')
    echo "    over ${max_mb} MB, retrying at ${video_k} kbps"
  done
done
