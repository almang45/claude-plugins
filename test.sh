#!/usr/bin/env bash
# Asserts the exact bytes the hook emits, raw and DCS-wrapped. TABCOLOR_TTY
# redirects them to a file, so none of this needs a tmux server or a pty, and
# nothing can repaint the real pane the tests are running in.
set -euo pipefail
cd "$(dirname "$0")"

out=$(mktemp "${TMPDIR:-/tmp}/tabcolor-test.XXXXXX")
trap 'rm -f "$out"' EXIT

# 4a9eff -> 74 158 255, ff9f0a -> 255 159 10, 30d158 -> 48 209 88.
BUSY=$'\033]6;1;bg;red;brightness;74\a\033]6;1;bg;green;brightness;158\a\033]6;1;bg;blue;brightness;255\a'
ATTN=$'\033]6;1;bg;red;brightness;255\a\033]6;1;bg;green;brightness;159\a\033]6;1;bg;blue;brightness;10\a'
IDLE=$'\033]6;1;bg;red;brightness;48\a\033]6;1;bg;green;brightness;209\a\033]6;1;bg;blue;brightness;88\a'
DEFAULT=$'\033]6;1;bg;*;default\a'

# Outside tmux: the sequence goes out verbatim.
plain() {
  : >"$out"
  env -u TMUX_PANE TABCOLOR_NO_ADOPT=1 TABCOLOR_TTY="$out" ./hooks/tabcolor.sh "$1"
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

# Inside tmux: same payload wrapped in a DCS passthrough with every ESC doubled,
# terminated by ST. Without this tmux swallows the sequence and the tab never
# changes, which is the entire bug this plugin existed-but-did-nothing for.
WRAPPED=$'\033Ptmux;\033\033]6;1;bg;red;brightness;74\a\033\033]6;1;bg;green;brightness;158\a\033\033]6;1;bg;blue;brightness;255\a\033\\'
: >"$out"
TMUX_PANE=%1 TABCOLOR_NO_ADOPT=1 TABCOLOR_TTY="$out" ./hooks/tabcolor.sh busy
check wrapped "$WRAPPED"

# Guard the two properties that make the wrapper work, so a refactor that
# flattens the escaping fails loudly rather than silently painting nothing.
grep -q $'\033\033]6' "$out" || { echo "FAIL wrapped: ESC not doubled"; exit 1; }
[[ $(tail -c2 "$out") == $'\033\\' ]] || { echo "FAIL wrapped: missing ST terminator"; exit 1; }

# No controlling tty (hook run headless): must be silent and exit 0. /dev/tty is
# world-writable even then, so a [[ -w /dev/tty ]] guard would let this through.
# setsid(2) via python3, since macOS ships no setsid(1).
for state in busy reset; do
  err=$(env -u TMUX_PANE -u TABCOLOR_TTY TABCOLOR_NO_ADOPT=1 python3 -c \
    'import os,subprocess,sys; os.setsid(); sys.exit(subprocess.call(sys.argv[1:]))' \
    ./hooks/tabcolor.sh "$state" 2>&1 >/dev/null </dev/null) || {
      echo "FAIL headless $state exited non-zero"; exit 1; }
  [[ -z $err ]] || { echo "FAIL headless $state wrote to stderr: $err"; exit 1; }
done

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
