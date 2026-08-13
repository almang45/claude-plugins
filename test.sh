#!/usr/bin/env bash
# End-to-end: drives tabcolor.sh against a throwaway tmux server and reads the
# option back. Also checks the iTerm2 OSC branch via a fake tty.
set -euo pipefail
cd "$(dirname "$0")"

sock=$(mktemp -u "${TMPDIR:-/tmp}/tabcolor-test.XXXXXX")
tmux -S "$sock" new-session -d -s t
trap 'tmux -S "$sock" kill-server 2>/dev/null || true' EXIT
pane=$(tmux -S "$sock" list-panes -t t -F '#{pane_id}')

run() { TMUX="$sock,0,0" TMUX_PANE="$pane" ./hooks/tabcolor.sh "$1"; }
style() { tmux -S "$sock" show-options -wqv -t "$pane" window-status-current-style; }

for state in busy:4a9eff attention:ff9f0a idle:30d158; do
  run "${state%%:*}"
  [[ $(style) == "bg=#${state##*:},fg=black,bold" ]] || { echo "FAIL ${state%%:*}: $(style)"; exit 1; }
done

run reset
[[ -z $(style) ]] || { echo "FAIL reset: $(style)"; exit 1; }

run bogus  # unknown state must be a no-op, not a crash
[[ -z $(style) ]] || { echo "FAIL bogus state changed style"; exit 1; }

# iTerm2 branch: no TMUX, run under a pty so /dev/tty exists and is capturable.
# 4a9eff -> 74 158 255.
osc=$(env -u TMUX -u TMUX_PANE script -q /dev/null ./hooks/tabcolor.sh busy | tr -d '\r')
for want in 'red;brightness;74' 'green;brightness;158' 'blue;brightness;255'; do
  [[ $osc == *"$want"* ]] || { echo "FAIL osc missing $want"; exit 1; }
done

echo "ok"
