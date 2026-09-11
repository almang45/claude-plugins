#!/usr/bin/env bash
# Cuts a clip out of any audio or video file into a chime pool. A real
# recording beats anything the synthesiser can approximate, and the plugin
# already plays whatever is in the directory, so this is only ffmpeg plumbing.
#
#   ./packs/clip.sh attention araara.mp4 3.2 1.4
#   ./packs/clip.sh attention araara.mp4 3.2 1.4 araara-tiktok
#
# Namespaced clip-*, so `anime-ja.sh --clean` never touches these.
set -euo pipefail

[[ $# -ge 2 ]] || { echo "usage: $0 <state> <file> [start] [duration] [name]" >&2; exit 2; }
state=$1 src=$2 start=${3:-0} dur=${4:-2}
name=${5:-$(basename "${src%.*}")}

case $state in busy|idle|attention) ;; *) echo "state must be busy, idle or attention" >&2; exit 2 ;; esac
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed: brew install ffmpeg" >&2; exit 1; }
[[ -f $src ]] || { echo "no such file: $src" >&2; exit 1; }

dir=${CHIME_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/chime}
mkdir -p "$dir/$state"
out="$dir/$state/clip-$name.aiff"

# loudnorm because a phone recording is far hotter than a system sound, and the
# whole point of the volume tiering is that busy stays under the music.
#
# The fades matter more than they look: a cut that lands mid-waveform steps the
# signal from zero to full instantly, which is a click. 12ms is inaudible as a
# fade and removes it. FADE=0 to disable.
fade=${FADE:-0.012}
fadeout=$(LC_ALL=C awk -v d="$dur" -v f="$fade" 'BEGIN{o=d-f; print (o>0 ? o : 0)}')
filter="loudnorm=I=-18:TP=-2"
if [[ $fade != 0 ]]; then
  filter="$filter,afade=t=in:st=0:d=$fade,afade=t=out:st=$fadeout:d=$fade"
fi

ffmpeg -nostdin -loglevel error -y -ss "$start" -t "$dur" -i "$src" \
  -vn -ac 1 -ar 22050 -af "$filter" "$out"

[[ -s $out ]] || { echo "FAIL: ffmpeg produced nothing, check start/duration" >&2; exit 1; }
# LC_ALL=C: awk reads 1.59 as 1 under a comma-decimal locale, and printf then
# emits it back with a comma. The readout was wrong, not the clip.
echo "wrote $out ($(LC_ALL=C afinfo "$out" | LC_ALL=C awk '/duration/{printf "%.2fs", $(NF-1)}'))"
afplay "$out"
