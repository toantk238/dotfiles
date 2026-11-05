#!/usr/bin/env bash
# retrace_log — turn an R8/ProGuard-obfuscated log back into readable names,
# using the mapping.txt from the same build.
#
# Usage:
#   retrace_log <mapping.txt> <log-file>       print the retraced log
#   retrace_log <mapping.txt> <log-file> -o out.txt
#   adb logcat -d | retrace_log <mapping.txt>  read the log from stdin
#
# Flags:
#   -o FILE     write to FILE instead of stdout
#   --verbose   print full method signatures (return type and arguments)
#
# Stack frames, exception classes and "Caused by:" lines are retraced, with or
# without a logcat prefix, as are logger call sites, and traces flattened onto one line with tabs are split
# back into frames. A mapping that fails its hash check (e.g. a cut-off download)
# gets a warning on stderr. Other log messages are left as they are: obfuscated
# names in free text can't be told apart from ordinary words.
set -euo pipefail

usage() { sed -n '2,/^$/{s/^# \{0,1\}//;/^set /d;p}' "$0"; }
die() { echo "retrace_log: $1" >&2; exit 1; }

# retrace's default only rewrites a class at the very start of a line, which
# misses logcat-prefixed and "Caused by:" lines. Alternatives, in order:
# a stack frame, a logger call site ("Class.method(file:line) - message", with the
# line number required so free text isn't mistaken for one), a bare class, a class
# after a "prefix: ".
REGEX='(?:.*?\bat\s+%c\.%m\s*\(%S\)\p{Z}*(?:~\[.*\])?)|(?:(?:.*?\s)?%c\.%m\(%s:%l\)\s+-\s.*)|(?:%c(?::.*)?)|(?:.*?[:"]\s+%c(?::.*)?)'

find_retrace() {
  local sdk
  if command -v retrace >/dev/null 2>&1; then
    command -v retrace
    return
  fi
  for sdk in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}"; do
    if [ -n "$sdk" ] && [ -x "$sdk/cmdline-tools/latest/bin/retrace" ]; then
      echo "$sdk/cmdline-tools/latest/bin/retrace"
      return
    fi
  done
  return 1
}

OUTPUT=""
EXTRA=()
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o)
      [ $# -ge 2 ] || die "-o needs a file"
      OUTPUT="$2"
      shift
      ;;
    --verbose) EXTRA+=(--verbose) ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*) die "unknown option: $1" ;;
    *) POSITIONAL+=("$1") ;;
  esac
  shift
done

if [ "${#POSITIONAL[@]}" -lt 1 ] || [ "${#POSITIONAL[@]}" -gt 2 ]; then
  usage >&2
  exit 1
fi
MAPPING="${POSITIONAL[0]}"
LOG="${POSITIONAL[1]:-}"

[ -f "$MAPPING" ] || die "mapping file not found: $MAPPING"
grep -qm1 -- ' -> ' "$MAPPING" || die "not an R8/ProGuard mapping file: $MAPPING"
if [ -n "$LOG" ]; then
  [ -f "$LOG" ] || die "log file not found: $LOG"
elif [ -t 0 ]; then
  die "no log given: pass a file or pipe one in"
fi

RETRACE=$(find_retrace) ||
  die "retrace not found: install the Android SDK cmdline-tools and set ANDROID_HOME"

# A cut-off download still parses, but every class past the cut stays obfuscated.
VERIFY=$("$RETRACE" --quiet --verify-mapping-file-hash "$MAPPING" </dev/null 2>&1 || true)
case "$VERIFY" in
  *'Mismatching map hash'*)
    echo "retrace_log: warning: mapping file hash mismatch, the file is truncated or" \
      "modified, so results will be incomplete or wrong: $MAPPING" >&2
    ;;
esac

# Crash reporters often flatten a stack trace onto one line, and retrace would
# read it as a single frame. One "\tat" is just a logcat-prefixed frame.
split_frames() {
  awk '{ line = $0; print (gsub(/\tat /, "\n\tat ", line) > 1 ? line : $0) }'
}

# --quiet keeps the "Waiting for stack-trace input..." banner out of the log.
CMD=("$RETRACE" --quiet --regex "$REGEX" ${EXTRA[@]+"${EXTRA[@]}"} "$MAPPING")

if [ -n "$OUTPUT" ]; then
  split_frames <"${LOG:-/dev/stdin}" | "${CMD[@]}" >"$OUTPUT"
else
  split_frames <"${LOG:-/dev/stdin}" | "${CMD[@]}"
fi
