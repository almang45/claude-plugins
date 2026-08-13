#!/usr/bin/env bash
# Asserts the exact bytes the hook emits, in and out of tmux. TABCOLOR_TTY
# redirects them to a file, so none of this needs a tmux server or a pty, and
# nothing can repaint the real pane the tests are running in.
set -euo pipefail
cd "$(dirname "$0")"

out=$(mktemp "${TMPDIR:-/tmp}/tabcolor-test.XXXXXX")
trap 'rm -f "$out"' EXIT

# The andon-light lamp palette: green (0,255,0), yellow (255,150,0), red (255,0,0).
BUSY=$'\033]6;1;bg;red;brightness;0\a\033]6;1;bg;green;brightness;255\a\033]6;1;bg;blue;brightness;0\a'
ATTN=$'\033]6;1;bg;red;brightness;255\a\033]6;1;bg;green;brightness;0\a\033]6;1;bg;blue;brightness;0\a'
IDLE=$'\033]6;1;bg;red;brightness;255\a\033]6;1;bg;green;brightness;150\a\033]6;1;bg;blue;brightness;0\a'
DEFAULT=$'\033]6;1;bg;*;default\a'

# Outside tmux: the sequence goes out verbatim.
plain() {
  : >"$out"
  env -u TMUX_PANE -u CLAUDE_JOB_DIR TABCOLOR_TTY="$out" ./hooks/tabcolor.sh "$1"
}
check() {
  [[ $(cat "$out") == "$2" ]] || { echo "FAIL $1: bytes differ"; od -c "$out" | head -4; exit 1; }
}

plain busy;      check busy "$BUSY"
plain attention; check attention "$ATTN"
plain idle;      check idle "$IDLE"
plain reset;     check reset "$DEFAULT"

plain bogus  # unknown state must be a silent no-op, not a crash
[[ -z $(cat "$out") ]] || { echo "FAIL bogus state emitted output"; exit 1; }

# Inside tmux the payload is identical, only the destination changes: it goes to
# the pane's tty, and iTerm2's control-mode integration applies it to that pane's
# tab. Anything wrapping or escaping the sequence here would break -CC.
: >"$out"
TMUX_PANE=%1 TABCOLOR_TTY="$out" ./hooks/tabcolor.sh busy
check "inside tmux" "$BUSY"

# No controlling tty (hook run headless): must be silent and exit 0. /dev/tty is
# world-writable even then, so a [[ -w /dev/tty ]] guard would let this through.
# setsid(2) via python3, since macOS ships no setsid(1).
for state in busy reset; do
  err=$(env -u TMUX_PANE -u TABCOLOR_TTY -u CLAUDE_JOB_DIR python3 -c \
    'import os,subprocess,sys; os.setsid(); sys.exit(subprocess.call(sys.argv[1:]))' \
    ./hooks/tabcolor.sh "$state" 2>&1 >/dev/null </dev/null) || {
      echo "FAIL headless $state exited non-zero"; exit 1; }
  [[ -z $err ]] || { echo "FAIL headless $state wrote to stderr: $err"; exit 1; }
done

# Title matching against a session name that matches no pane must be a silent
# no-op. Which pane a real name resolves to is not covered here: resolution
# reads the live tmux server, so the only honest assertion would be against the
# developer's own tabs. Verify that by hand with tmux list-panes -F '#{pane_title}'.
fixture=$(mktemp -d "${TMPDIR:-/tmp}/tabcolor-job.XXXXXX")
trap 'rm -f "$out"; rm -rf "$fixture"' EXIT
cat >"$fixture/state.json" <<'JSON'
{
  "nameSource": "auto",
  "name": "a session name matching no pane whatsoever",
  "state": "working"
}
JSON
err=$(env -u TMUX_PANE -u TABCOLOR_TTY CLAUDE_JOB_DIR="$fixture" \
  ./hooks/tabcolor.sh busy 2>&1 >/dev/null </dev/null) || {
    echo "FAIL title match exited non-zero"; exit 1; }
[[ -z $err ]] || { echo "FAIL title match wrote to stderr: $err"; exit 1; }

# hooks/hooks.json is loaded automatically. Naming it in the manifest too makes
# the plugin fail to load with "Duplicate hooks file detected".
python3 - <<'PY' || exit 1
import json, sys
m = json.load(open(".claude-plugin/plugin.json"))
if "hooks" in m:
    sys.exit("FAIL plugin.json must not declare the auto-loaded hooks/hooks.json")
json.load(open("hooks/hooks.json"))
PY

echo "ok"
