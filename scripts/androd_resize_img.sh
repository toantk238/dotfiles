#!/usr/bin/env bash
# gen-densities.sh — generate other-dpi drawables from a source density folder.
# Auto-detects the source density from the folder you point at (or the cwd).
# Generates ALL lower densities; with --up also generates higher ones.
# Supports: png, webp, jpg/jpeg (keeps each file's original format)
set -euo pipefail

UPSCALE=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --up) UPSCALE=1 ;;
    *) ARGS+=("$a") ;;
  esac
done

# Target: a specific drawable-*/mipmap-* folder, or a res dir, or cwd.
TARGET="${ARGS[0]:-.}"

# Absolute density scale factors (mdpi = 1.0 baseline)
declare -A DENSITY=(
  [ldpi]=0.75
  [mdpi]=1.0
  [hdpi]=1.5
  [xhdpi]=2.0
  [xxhdpi]=3.0
  [xxxhdpi]=4.0
)
ORDER=(ldpi mdpi hdpi xhdpi xxhdpi xxxhdpi)

# --- Resolve the source folder ---
# If TARGET itself is a drawable-<dpi>/mipmap-<dpi> folder, use it directly.
# Otherwise treat it as a res dir and look for the highest-density folder present.
basename_t=$(basename "$TARGET")
if [[ "$basename_t" =~ ^(drawable|mipmap)-([a-z]+dpi)$ ]]; then
  SRC="$TARGET"
  PREFIX="${BASH_REMATCH[1]}"
  SRC_DPI="${BASH_REMATCH[2]}"
else
  SRC=""
  for pfx in drawable mipmap; do
    for ((i=${#ORDER[@]}-1; i>=0; i--)); do
      cand="$TARGET/${pfx}-${ORDER[i]}"
      if [ -d "$cand" ]; then
        SRC="$cand"; PREFIX="$pfx"; SRC_DPI="${ORDER[i]}"
        break 2
      fi
    done
  done
  if [ -z "$SRC" ]; then
    echo "Could not find a drawable-*dpi or mipmap-*dpi folder under: $TARGET" >&2
    echo "Point me at a density folder directly, or at the res/ dir." >&2
    exit 1
  fi
fi

RES_DIR=$(dirname "$SRC")
echo "Source: $SRC  (detected density: $SRC_DPI)"

# --- ImageMagick command (v7 = magick, v6 = convert) ---
if command -v magick >/dev/null 2>&1; then IM=magick
elif command -v convert >/dev/null 2>&1; then IM=convert
else
  echo "ImageMagick not found. Install it (e.g. sudo pacman -S imagemagick)." >&2
  exit 1
fi

FILTER="Lanczos"
src_scale="${DENSITY[$SRC_DPI]}"

# --- Collect source images ---
shopt -s nullglob nocaseglob
files=("$SRC"/*.png "$SRC"/*.webp "$SRC"/*.jpg "$SRC"/*.jpeg)
shopt -u nocaseglob
if [ ${#files[@]} -eq 0 ]; then
  echo "No png/webp/jpg images found in $SRC" >&2
  exit 1
fi

# --- Generate targets ---
for dpi in "${ORDER[@]}"; do
  [ "$dpi" = "$SRC_DPI" ] && continue
  tgt_scale="${DENSITY[$dpi]}"
  # skip higher densities unless --up (upscaling loses quality)
  if (( UPSCALE == 0 )) && awk "BEGIN{exit !($tgt_scale > $src_scale)}"; then
    continue
  fi
  pct=$(awk "BEGIN{printf \"%.4f\", ($tgt_scale/$src_scale)*100}")
  out="$RES_DIR/${PREFIX}-${dpi}"
  mkdir -p "$out"
  for img in "${files[@]}"; do
    name=$(basename "$img")
    "$IM" "$img" -filter "$FILTER" -resize "${pct}%" "$out/$name"
    echo "→ ${PREFIX}-${dpi}/$name (${pct%.*}%)"
  done
done

echo "Done."
