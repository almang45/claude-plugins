#!/usr/bin/env bash
# Stubs afplay and say on PATH, so every assertion is about the exact command
# the hook would run and nothing ever reaches a speaker.
set -euo pipefail
cd "$(dirname "$0")"

tmp=$(mktemp -d "${TMPDIR:-/tmp}/chime-test.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
log="$tmp/log"
mkdir -p "$tmp/bin" "$tmp/sounds"

for b in afplay say; do
  cat > "$tmp/bin/$b" <<STUB
#!/usr/bin/env bash
echo "$b \$*" >> "\$CHIME_LOG"
STUB
  chmod +x "$tmp/bin/$b"
done

export PATH="$tmp/bin:$PATH" CHIME_LOG="$log" CHIME_DIR="$tmp/sounds"

# The hook backgrounds the player, so the write races the parent exiting.
fire() {
  local before after
  before=$(wc -l <"$log" 2>/dev/null || echo 0)
  /bin/bash ./hooks/chime.sh "$1"   # bash 3.2, the one macOS actually runs
  for _ in $(seq 1 50); do
    after=$(wc -l <"$log" 2>/dev/null || echo 0)
    [[ $after -gt $before ]] && return 0
    sleep 0.02
  done
  return 1
}

# Fires a state 30 times: every call must start with the expected prefix, and
# the tail must actually vary, otherwise the "pool" is a constant.
sweep() {
  local label=$1 state=$2 prefix=$3
  : >"$log"
  for _ in $(seq 1 30); do fire "$state" || { echo "FAIL $label: nothing ran"; exit 1; }; done
  awk -v p="$prefix" 'index($0,p)!=1{print "  bad call: "$0; bad=1} END{exit bad}' "$log" \
    || { echo "FAIL $label: call did not match: $prefix"; exit 1; }
  local distinct
  distinct=$(sort -u "$log" | wc -l | tr -d ' ')
  [[ $distinct -gt 1 ]] || { echo "FAIL $label: always the same, not a pool"; exit 1; }
  echo "ok   $label ($distinct variants)"
}

# 1. Built-in system sounds: one pool per state. busy sits under the music at
# 0.2; idle and attention share 0.8, so neither voice clip startles the other.
sweep "busy      -> quiet system tick" busy      "afplay -v 0.2 /System/Library/Sounds/"
sweep "idle      -> system chime"      idle      "afplay -v 0.8 /System/Library/Sounds/"
sweep "attention -> system alert"      attention "afplay -v 0.8 /System/Library/Sounds/"

# Read out of the script rather than duplicated here, so editing a pool cannot
# leave this list asserting sounds nothing plays any more.
count=0
for name in $(LC_ALL=C sed -n 's/.*pool=(\([^)]*\)).*/\1/p' hooks/chime.sh); do
  [[ -f "/System/Library/Sounds/$name.aiff" ]] || { echo "FAIL: missing $name.aiff"; exit 1; }
  count=$((count + 1))
done
# Guards the sed itself: a parse that matches nothing would pass vacuously.
[[ $count -ge 3 ]] || { echo "FAIL: only parsed $count sound names from chime.sh"; exit 1; }
echo "ok   all $count system sounds named in chime.sh exist"

# 2. Recordings in CHIME_DIR/<state>/ take over that state, and only that state.
mkdir -p "$tmp/sounds/idle"
touch "$tmp/sounds/idle/a.wav" "$tmp/sounds/idle/b.m4a" "$tmp/sounds/idle/c.aiff"
sweep "idle      -> custom recordings" idle "afplay -v 0.8 $tmp/sounds/idle/"
: >"$log"; fire busy
grep -q '/System/Library/Sounds/' "$log" || { echo "FAIL: custom idle leaked into busy"; exit 1; }
echo "ok   custom dir is per-state, busy untouched"

# An empty state dir must fall through, not go silent. This is what a fresh
# ~/.claude/chime looks like before you record anything.
mkdir -p "$tmp/sounds/attention"
: >"$log"; fire attention
grep -q '^afplay -v 0.8 /System/Library/Sounds/' "$log" || { echo "FAIL: empty custom dir silenced the state"; exit 1; }
echo "ok   empty custom dir falls through to system sounds"

# 3. Speech is opt-in and carries the state's volume. attention has no custom
#    dir, so this is the speech path proper.
export CHIME_SAY=1
sweep "attention -> spoken phrase" attention "say [[volm 0.8]] "

# 4. A recording you bothered to make outranks the synthesised voice.
: >"$log"; fire idle
grep -q "^afplay -v 0.8 $tmp/sounds/idle/" "$log" || { echo "FAIL: speech overrode custom recording"; exit 1; }
echo "ok   custom recordings beat speech"

# 5. busy has no phrases on purpose: a voice per tool call is unlivable.
: >"$log"; fire busy
grep -q '^afplay -v 0.2 /System/Library/Sounds/' "$log" || { echo "FAIL: busy spoke instead of ticking"; exit 1; }
echo "ok   busy stays a tick even in speech mode"

# 6. CHIME_VOICE picks the voice, and only when set.
: >"$log"; CHIME_VOICE=Samantha fire attention
grep -q '^say -v Samantha \[\[volm 0.8\]\] ' "$log" || { echo "FAIL: CHIME_VOICE ignored: $(cat "$log")"; exit 1; }
echo "ok   CHIME_VOICE selects the voice"
unset CHIME_SAY

# 7. Unknown or missing state is silent, not an error.
: >"$log"
/bin/bash ./hooks/chime.sh
/bin/bash ./hooks/chime.sh nonsense
sleep 0.1
[[ ! -s $log ]] || { echo "FAIL: unknown state played something"; exit 1; }
echo "ok   unknown state stays silent"

# 8. The hook wiring has to be valid JSON and point at the real script.
python3 -c '
import json, pathlib
h = json.load(open("hooks/hooks.json"))["hooks"]
states = set()
for event, entries in h.items():
    for entry in entries:
        for hook in entry["hooks"]:
            cmd = hook["command"]
            assert "${CLAUDE_PLUGIN_ROOT}/hooks/chime.sh" in cmd, cmd
            states.add(cmd.rsplit(" ", 1)[1])
assert states == {"busy", "idle", "attention"}, states
assert pathlib.Path("hooks/chime.sh").stat().st_mode & 0o111, "chime.sh not executable"
json.load(open(".claude-plugin/plugin.json"))
print("ok   hooks.json wires all three states")
'
echo "PASS"
