#!/usr/bin/env bash
# gen-densities.sh — generate other-dpi drawables from a source density folder.
# Auto-detects the source density from the folder you point at (or the cwd).
# Generates ALL lower densities; with --up also generates higher ones.
# Supports: png, webp, jpg/jpeg (keeps each file's original format).
# Each generated image is byte-optimized with the best available tool, with a
# safe ImageMagick fallback so it still works if no optimizer is installed.
#
# Flags:
#   --up        also generate higher densities (upscaling; off by default)
#   --no-opt    skip byte optimization
#   -q N        JPEG/WebP quality (default 85)
set -euo pipefail

UPSCALE=0; OPT=1; QUALITY=85
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --up) UPSCALE=1 ;;
    --no-opt) OPT=0 ;;
    -q) shift; QUALITY="$1" ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done

TARGET="${ARGS[0]:-.}"

declare -A DENSITY=(
  [ldpi]=0.75 [mdpi]=1.0 [hdpi]=1.5 [xhdpi]=2.0 [xxhdpi]=3.0 [xxxhdpi]=4.0
)
ORDER=(ldpi mdpi hdpi xhdpi xxhdpi xxxhdpi)

# --- Resolve the source folder ---
basename_t=$(basename "$TARGET")
if [[ "$basename_t" =~ ^(drawable|mipmap)-([a-z]+dpi)$ ]]; then
  SRC="$TARGET"; PREFIX="${BASH_REMATCH[1]}"; SRC_DPI="${BASH_REMATCH[2]}"
else
  SRC=""
  for pfx in drawable mipmap; do
    for ((i=${#ORDER[@]}-1; i>=0; i--)); do
      cand="$TARGET/${pfx}-${ORDER[i]}"
      if [ -d "$cand" ]; then SRC="$cand"; PREFIX="$pfx"; SRC_DPI="${ORDER[i]}"; break 2; fi
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

# --- Detect optimizers once ---
has() { command -v "$1" >/dev/null 2>&1; }
if (( OPT )); then
  has oxipng    && OX=1    || OX=0
  has pngquant  && PQ=1    || PQ=0
  has optipng   && OP=1    || OP=0
  has jpegoptim && JO=1    || JO=0
  has cwebp     && CW=1    || CW=0
fi

human() { awk "BEGIN{b=$1; u=\"B KB MB\"; split(u,a,\" \"); i=1; while(b>=1024&&i<3){b/=1024;i++} printf \"%.1f%s\", b, a[i]}"; }

optimize() {
  local f="$1" ext before after
  (( OPT )) || return 0
  before=$(stat -c%s "$f")
  ext="${f##*.}"; ext="${ext,,}"
  case "$ext" in
    png)
      if   (( PQ )); then pngquant --force --skip-if-larger --quality=65-90 --output "$f" -- "$f" 2>/dev/null || true; fi
      if   (( OX )); then oxipng -o4 --strip safe -q "$f" 2>/dev/null || true
      elif (( OP )); then optipng -o5 -strip all -quiet "$f" 2>/dev/null || true; fi
      ;;
    jpg|jpeg)
      if (( JO )); then jpegoptim -s -m"$QUALITY" -q "$f" 2>/dev/null || true; fi
      ;;
    webp)
      if (( CW )); then
        local tmp="${f}.tmp.webp"
        cwebp -quiet -q "$QUALITY" "$f" -o "$tmp" 2>/dev/null && mv "$tmp" "$f" || rm -f "$tmp"
      fi
      ;;
  esac
  after=$(stat -c%s "$f")
  if (( after < before )); then
    echo "   opt $(human $before) → $(human $after)"
  fi
}

# --- Collect source images ---
shopt -s nullglob nocaseglob
files=("$SRC"/*.png "$SRC"/*.webp "$SRC"/*.jpg "$SRC"/*.jpeg)
shopt -u nocaseglob
if [ ${#files[@]} -eq 0 ]; then
  echo "No png/webp/jpg images found in $SRC" >&2
  exit 1
fi

# warn if optimization requested but nothing available
if (( OPT )) && (( OX+PQ+OP+JO+CW == 0 )); then
  echo "Note: no optimizers found (oxipng/pngquant/optipng/jpegoptim/cwebp)."
  echo "      Falling back to ImageMagick's built-in stripping/quality only."
fi

# --- Generate targets ---
for dpi in "${ORDER[@]}"; do
  [ "$dpi" = "$SRC_DPI" ] && continue
  tgt_scale="${DENSITY[$dpi]}"
  if (( UPSCALE == 0 )) && awk "BEGIN{exit !($tgt_scale > $src_scale)}"; then continue; fi
  pct=$(awk "BEGIN{printf \"%.4f\", ($tgt_scale/$src_scale)*100}")
  out="$RES_DIR/${PREFIX}-${dpi}"; mkdir -p "$out"
  for img in "${files[@]}"; do
    name=$(basename "$img"); dst="$out/$name"
    if [ -f "$dst" ]; then
      echo "  skip ${PREFIX}-${dpi}/$name (already exists)"
      continue
    fi
    ext="${name##*.}"; ext="${ext,,}"
    # ImageMagick resize + built-in optimization (works even with no external tools)
    case "$ext" in
      png)       "$IM" "$img" -filter "$FILTER" -resize "${pct}%" -strip "$dst" ;;
      jpg|jpeg)  "$IM" "$img" -filter "$FILTER" -resize "${pct}%" -strip -interlace JPEG -quality "$QUALITY" "$dst" ;;
      webp)      "$IM" "$img" -filter "$FILTER" -resize "${pct}%" -strip -quality "$QUALITY" "$dst" ;;
      *)         "$IM" "$img" -filter "$FILTER" -resize "${pct}%" -strip "$dst" ;;
    esac
    echo "→ ${PREFIX}-${dpi}/$name (${pct%.*}%)"
    optimize "$dst"
  done
done

echo "Done."
