#!/usr/bin/env bash
# Renders a Japanese phrase pack into the chime recordings directory.
#
# Pre-rendered with `say -o` rather than run through CHIME_SAY, because the
# synthesiser costs ~2s per line and these fire on every turn. Playback of a
# rendered aiff is instant, and rendering is also the only way to give each
# phrase its own timbre.
#
#   ./packs/anime-ja.sh                 # Kyoko, standard
#   ./packs/anime-ja.sh Otoya           # any voice from: say -v '?' | grep ja_JP
#   ./packs/anime-ja.sh Kyoko --ecchi   # tsundere register for the loud state
#   ./packs/anime-ja.sh --clean         # remove the pack, keep your own files
set -euo pipefail

# ── timbre presets ──────────────────────────────────────────────────────────
# A line reads as a different character depending on pitch and pace, so each
# phrase is tagged with one of these. Measured on Kyoko: [[pbas]] shifts pitch
# without touching duration, -r is words per minute, and [[pmod]] is ignored
# entirely by the modern voices, so there is no vibrato knob to reach for.
#
# These are calibration knobs, not constants. Voices differ and so do ears, so
# override from the environment and re-render until it sounds right:
#   KOUHAI_PBAS=80 ./packs/anime-ja.sh Kyoko --ecchi
#
# pbas is 0-127 and Kyoko sits near 45. ..._VOICE empty means the CLI voice.
ONEESAN_PBAS=${ONEESAN_PBAS:-28}   # mature, lower and unhurried
ONEESAN_RATE=${ONEESAN_RATE:-125}
ONEESAN_VOICE=${ONEESAN_VOICE:-}   # try 'Grandma (Japanese (Japan))' for older still
KOUHAI_PBAS=${KOUHAI_PBAS:-68}     # junior, higher and eager
KOUHAI_RATE=${KOUHAI_RATE:-190}
KOUHAI_VOICE=${KOUHAI_VOICE:-}
PLAIN_PBAS=${PLAIN_PBAS:-45}       # the voice as shipped
PLAIN_RATE=${PLAIN_RATE:-165}

# Full name, not awk $1: "Kyoko (Enhanced)" and "Grandma (Japanese (Japan))"
# both carry spaces, and truncating them rejected two perfectly good voices.
voice_exists() {
  say -v '?' | LC_ALL=C sed 's/[[:space:]]*[a-z][a-z]_[A-Z][A-Z].*//' | grep -qxF "$1"
}

# Same voice, better model. Downloaded via System Settings > Accessibility >
# Spoken Content > Manage Voices, so it is only sometimes present.
voice=Kyoko
if voice_exists 'Kyoko (Enhanced)'; then voice='Kyoko (Enhanced)'; fi
ecchi=""
clean=""
for arg in "$@"; do
  case "$arg" in
    --ecchi) ecchi=1 ;;
    --clean) clean=1 ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) voice=$arg ;;
  esac
done

dir=${CHIME_DIR:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/chime}
prefix=anime   # namespaced, so re-runs never touch recordings you made yourself

if [[ -n $clean ]]; then
  rm -f "$dir"/*/"$prefix"-*.aiff
  echo "removed $prefix-*.aiff from $dir"
  exit 0
fi

# Checked before anything is deleted: a typo used to wipe the installed pack.
# say also falls back to the system voice silently, giving an English-accented
# pack with no warning.
voice_exists "$voice" \
  || { echo "no such voice: $voice (try: say -v '?' | grep ja_JP)" >&2; exit 1; }

rm -f "$dir"/*/"$prefix"-*.aiff

# Sets pbas/rate/pvoice for the caller. Dynamic scope, so render's locals win.
set_preset() {
  case $1 in
    oneesan) pbas=$ONEESAN_PBAS; rate=$ONEESAN_RATE; pvoice=$ONEESAN_VOICE ;;
    kouhai)  pbas=$KOUHAI_PBAS;  rate=$KOUHAI_RATE;  pvoice=$KOUHAI_VOICE ;;
    *)       pbas=$PLAIN_PBAS;   rate=$PLAIN_RATE;   pvoice="" ;;
  esac
}

# Entries are "preset:phrase", or a bare phrase for the plain preset. Japanese
# text has no ASCII colon, so the split is unambiguous.
render() {
  local state=$1; shift
  mkdir -p "$dir/$state"
  local i=0 entry preset phrase pbas rate pvoice out
  for entry in "$@"; do
    case $entry in
      oneesan:*|kouhai:*) preset=${entry%%:*}; phrase=${entry#*:} ;;
      *)                  preset=plain;        phrase=$entry ;;
    esac
    set_preset "$preset"
    i=$((i + 1))
    out="$dir/$state/$prefix-$i.aiff"
    say -v "${pvoice:-$voice}" -r "$rate" -o "$out" "[[pbas $pbas]] $phrase"
    # A silent or missing render is worse than no pack, it makes a state mute.
    [[ -s $out ]] || { echo "FAIL: empty render for '$phrase'" >&2; exit 1; }
  done
  echo "  $state: $i lines"
}

# Fires once per tool call, so these stay to a syllable or two. Delete
# $dir/busy if a voice on every tool call turns out to be too much.
render busy \
  "はい" \
  "うん" \
  "にゃ" \
  "がんば" \
  "kouhai:先輩〜"

# Turn finished, your move.
render idle \
  "kouhai:終わりましたよ、先輩" \
  "kouhai:おまたせ！" \
  "kouhai:できたよ〜" \
  "君の番だよ" \
  "kouhai:ふふん、どう？" \
  "完璧です！" \
  "oneesan:あらあら" \
  "oneesan:あらあら、もう終わり？"

# Stopped, wants an answer. The loud one.
if [[ -n $ecchi ]]; then
  render attention \
    "ちょっと待って！" \
    "kouhai:助けて、先輩！" \
    "kouhai:ばか！何してるの！" \
    "kouhai:えっち！" \
    "kouhai:すけべ！" \
    "kouhai:ばか、へんたい！" \
    "kouhai:どこ触ってるの！" \
    "kouhai:もう、変態！" \
    "oneesan:あらあら、うふふ" \
    "oneesan:あら、ダメですよ先輩" \
    "kouhai:先輩、こっち見て"
else
  render attention \
    "ちょっと待って！" \
    "kouhai:助けて、先輩！" \
    "ねえ、聞いてる？" \
    "許可をください！" \
    "kouhai:ばか！何してるの！" \
    "困ってるんだけど…" \
    "kouhai:先輩、こっち見て" \
    "oneesan:あらあら"
fi

echo "rendered with $voice into $dir"
echo "  oneesan: pbas $ONEESAN_PBAS rate $ONEESAN_RATE${ONEESAN_VOICE:+ voice $ONEESAN_VOICE}"
echo "  kouhai:  pbas $KOUHAI_PBAS rate $KOUHAI_RATE${KOUHAI_VOICE:+ voice $KOUHAI_VOICE}"
