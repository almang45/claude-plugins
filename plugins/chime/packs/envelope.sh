#!/usr/bin/env bash
# Prints an RMS envelope, so the part of a recording worth keeping can be found
# by reading levels instead of guessing timestamps. Silence between utterances
# shows up as a gap, which is where the cut belongs.
#
#   ./packs/envelope.sh clip.mp3              # whole file, 0.25s windows
#   ./packs/envelope.sh clip.mp3 9 11 0.05    # zoom in: from, to, window
set -euo pipefail

[[ $# -ge 1 ]] || { echo "usage: $0 <file> [from] [to] [window-seconds]" >&2; exit 2; }
src=$1 from=${2:-0} to=${3:-99999} win=${4:-0.25}
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed: brew install ffmpeg" >&2; exit 1; }
[[ -f $src ]] || { echo "no such file: $src" >&2; exit 1; }

# asetnsamples counts samples, so the rate has to be pinned or the window drifts
# with whatever the file happens to be.
n=$(LC_ALL=C awk -v w="$win" 'BEGIN{printf "%d", w * 44100}')

echo "$(basename "$src")  $(LC_ALL=C ffprobe -v error -show_entries format=duration -of csv=p=0 "$src" | LC_ALL=C awk '{printf "%.2fs", $1}')  windows of ${win}s"
LC_ALL=C ffmpeg -nostdin -v error -i "$src" \
  -af "aresample=44100,asetnsamples=n=$n,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-" \
  -f null - 2>/dev/null | LC_ALL=C awk -v lo="$from" -v hi="$to" '
  /pts_time:/ { split($3,a,":"); t=a[2]+0 }
  /RMS_level=/ {
    split($0,b,"="); r=b[2]+0
    if (t >= lo && t <= hi) {
      bar=""; n=int((r+60)/3); if (n<0) n=0
      for (i=0; i<n; i++) bar = bar "#"
      printf "%7.2f  %8.1f dB %s\n", t, r, bar
    }
  }'
